# Khởi tạo helper trước và phòng nạp lớp đệ quy, class circularity hoặc deadlock

Trong **Java Advance – instrumentation**, phần **Đồng thời và hiệu năng**, Java agent có thể khiến ứng dụng gặp `LinkageError`, `ClassCircularityError` hoặc treo ở thời điểm nạp lớp, mặc dù bản thân transformer có vẻ chỉ xử lý vài bytecode. Nguyên nhân thường là code được gọi bên trong `ClassFileTransformer.transform(...)` làm JVM nạp thêm lớp, khởi tạo helper hoặc đợi một lock, ngay khi lớp mục tiêu **chưa hoàn tất quá trình định nghĩa**.

Một ví dụ điển hình: transformer gọi logger lần đầu để báo đã instrument `OrderService`; logger khởi tạo provider, provider nạp class khác; transformer được gọi lại và vô tình cần chính `OrderService` hoặc chờ một class loader lock. Sự cố đôi khi xuất hiện ở thread khác với nơi nguyên nhân bắt đầu.

Bài này giải thích **vì sao phải chuẩn bị helper trước khi đăng ký transformer**, cách thiết kế callback để hạn chế class loading đệ quy, và cách phân biệt **class circularity** với **deadlock** và vòng **static initialization**. Có hai ví dụ Java 17+ hoàn chỉnh và có thể chạy độc lập theo hướng dẫn.

## 1. Các mốc trong vòng đời một Java agent

Startup agent nhận `Instrumentation` qua `premain`. Khi gọi `Instrumentation.addTransformer`, agent đăng ký callback để JVM gọi lúc có class được nạp, redefine hoặc retransform tùy khả năng transformer. Với nạp lớp lần đầu, callback chạy **trước khi định nghĩa lớp hoàn tất**.

```text
JVM tải agent JAR và gọi premain
        |
        v
Khởi tạo helper + cấu hình + trạng thái cần cho transformer
        |
        v
addTransformer(transformer)
        |
        v
Application class loader bắt đầu nạp lớp C
        |
        v
ClassFileTransformer.transform(..., className=".../C", bytes)
        |
        v
JVM tiếp tục verify/link/define C
        |
        v
Ứng dụng sử dụng C
```

Không nên mặc định callback là một “sự kiện quan sát” độc lập, an toàn để gọi mọi API. Nó là một đoạn mã chạy **ngay trong đường nạp lớp của JVM**. Nhiều custom class loader giữ lock trong `loadClass`, trong khi những lớp được callback dùng có thể chưa nạp hoặc khởi tạo.

**Nguyên tắc:** xử lý ít nhất có thể trong callback: lọc sớm, sử dụng các lớp/cấu trúc đã chuẩn bị, biến đổi mảng bytes khi thật sự cần và trả `null` khi không thay đổi. Việc kết nối mạng, khởi tạo logger, tìm class bằng reflection hay chờ công việc của thread khác cần diễn ra ở giai đoạn riêng.

## 2. Nạp lớp, liên kết và khởi tạo là các khái niệm khác nhau

| Giai đoạn | Việc xảy ra | Vì sao liên quan đến instrumentation |
| --- | --- | --- |
| **Loading** | Class loader tìm bytes, JVM định nghĩa một lớp; transformer có thể được gọi trong quá trình này | Callback có thể yêu cầu JVM nạp lớp khác khi lớp hiện tại còn đang load |
| **Linking** | Verify, prepare và resolve symbolic references khi thích hợp | Lỗi trong class hierarchy, class file hoặc giải tên/phương thức có thể sinh `LinkageError` |
| **Initialization** | Chạy static field initializers và `<clinit>` | Helper có thể khởi tạo dependency, gọi code ứng dụng, hoặc chờ class khác đang khởi tạo ở thread khác |

Đừng gọi tất cả những hiện tượng này là “class loading”. Chẳng hạn `ProbeHooks.class` lấy `Class<?>` nhưng **không bắt buộc** chạy static initializer, trong khi `Class.forName("agent.ProbeHooks", true, loader)` yêu cầu khởi tạo class.

Các biểu hiện phải phân biệt:

- **Recursive class loading**: trong lúc `transform(C)`, callback hoặc dependency yêu cầu nạp/resolve lại `C` hoặc một nhóm class dẫn ngược về nó. Tùy tình huống có thể gặp `LinkageError`, recursion hoặc lỗi khác; không thể mặc định một exception duy nhất.
- **`ClassCircularityError`**: theo Javadoc, JVM phát hiện **chu trình trong superclass hierarchy** của một lớp đang nạp. Một cấu trúc kiểu `A extends B`, `B extends A` là bất hợp lệ; Java compiler có thể bắt lỗi nguồn, còn công cụ tạo bytecode/custom loader có thể đưa ra classfile không hợp lệ.
- **Deadlock**: các thread cùng giữ và đợi tài nguyên theo vòng, ví dụ loader lock A → B → A hoặc class initialization locks. Khi đó chương trình có thể **không ném exception**, mà chỉ đứng chờ.
- **Vòng static initialization cùng thread**: Java Language Specification có quy tắc riêng cho yêu cầu tái nhập của thread đang khởi tạo class. Nó không nhất thiết là `ClassCircularityError`; ví dụ cụ thể nằm ở mục 6.

## 3. Vì sao việc gọi helper trong transformer nguy hiểm?

Xét code minh họa sau, **không nên dùng nguyên dạng trong agent thực tế**:

```java
// Snippet anti-pattern, nằm trong transform(...):
Class<?> target = Class.forName(className.replace('/', '.'));
logger.info("Instrumenting {}", target.getName());
metricsRegistry.counter("transforms").increment();
bytecodeAnalyzer.inspect(target.getDeclaredMethods());
```

Có nhiều rủi ro khác nhau:

1. **`Class.forName` trên chính target** ép loader tìm/resolve class đang được JVM định nghĩa. Với load-time transform, `classBeingRedefined` thường là `null` vì `Class<?>` của lớp mới chưa sẵn sàng ở dạng có thể dùng an toàn. Thông tin `className`, `loader`, `module`, `classfileBuffer` đã được callback cung cấp; không cần “tìm lại” target qua class loader.
2. **Lần sử dụng logger đầu tiên** có thể nạp provider, formatter, service loader hoặc cấu hình. Những lớp mới đó cũng đi qua transformer nếu không lọc.
3. **Metrics registry** có thể khởi tạo thread, lock, lớp thư viện và I/O khi được gọi lần đầu.
4. **Reflection trên target** có thể ép JVM resolve thêm kiểu/method và phụ thuộc trong lúc target chưa hoàn tất.
5. Nếu callback giữ một `synchronized` global hoặc gọi `Future.join()`/latch, một luồng khác có thể đang chờ chính class loader mà callback giữ.

Không phải mọi lần gọi logger đều gây lỗi. Vấn đề là **khó chứng minh không có lazy class loading hoặc lock acquisition** ở những API phức tạp, đặc biệt khi JVM đã bắt đầu định nghĩa lớp.

## 4. Khởi tạo helper trước khi đăng ký

Thứ tự khởi động nên là:

```text
premain
  -> xác thực cấu hình/allowlist
  -> thiết lập đường nạp helper đúng class loader
  -> init helper và dependencies thật sự cần ở đường nóng
  -> tạo transformer, counters, guard
  -> kiểm tra trạng thái sẵn sàng
  -> addTransformer(...)
```

Ví dụ đoạn trích trong `premain`:

```java
// Ví dụ minh họa trong premain, không phải chương trình độc lập.
ClassLoader agentLoader = AgentEntry.class.getClassLoader();
Class.forName("agent.ProbeHooks", true, agentLoader);
instrumentation.addTransformer(transformer);
```

Ba biểu thức có ý nghĩa khác nhau:

| Cách | Bảo đảm khởi tạo `<clinit>`? |
| --- | --- |
| `ProbeHooks.class` | Không |
| `Class.forName("agent.ProbeHooks", false, loader)` | Không yêu cầu khởi tạo |
| `Class.forName("agent.ProbeHooks", true, loader)` | Có, yêu cầu khởi tạo nếu chưa khởi tạo |

**Đừng hiểu “khởi tạo helper trước” là “tải tất cả lớp của JVM”.** Chỉ warm-up những dependency thật sự cần để transform/hook hoạt động. Việc nạp trước hàng nghìn lớp tăng startup time và cũng có thể kích hoạt side effect không mong muốn.

Các lưu ý:

- Nếu static initializer của helper cần ứng dụng đã khởi động, đừng ép chạy nó quá sớm. Thiết kế helper thành bridge đơn giản, khởi tạo backend ở giai đoạn riêng khi đủ điều kiện.
- Warm-up **đúng loader**. Bản helper được system loader khởi tạo không đồng nghĩa một class cùng tên do plugin loader định nghĩa đã được khởi tạo.
- Warm-up phụ thuộc trực tiếp chưa chắc chạm tới mọi nhánh lazy-loading trong runtime. Vì vậy vẫn cần lọc class và giảm phụ thuộc trong callback.
- Nếu helper được chèn vào class bootstrap, phải bảo đảm helper có thể được bootstrap loader resolve; chỉ đặt nó trong agent JAR system loader không đủ.
- Nếu `Class.forName(..., true, ...)` thất bại, nên báo lỗi startup minh bạch và chưa đăng ký callback thiếu helper.

## 5. Ví dụ Java 17+ đầy đủ: warm-up, lọc sớm, guard cùng thread

Thí nghiệm dùng JDK chuẩn, không cần ASM. Transformer chỉ **quan sát** lần nạp `demo.Target` rồi trả `null`; nguồn của `Target.work()` chứa sẵn lời gọi `ProbeHooks.hit()` nhằm mô phỏng kết quả `invokestatic` mà một transformer thực tế có thể chèn. **Ví dụ này không thực hiện bytecode weaving**; nó tập trung vào thứ tự khởi tạo và an toàn callback.

Cấu trúc:

```text
safe-instrumentation/
├── agent.mf
├── src/
│   ├── agent/
│   │   ├── SafeAgent.java
│   │   └── ProbeHooks.java
│   └── demo/
│       ├── Target.java
│       └── Main.java
└── out/                       # tạo khi biên dịch
```

### 5.1. Helper có static initializer

Tệp `src/agent/ProbeHooks.java`:

```java
package agent;

import java.util.concurrent.atomic.AtomicInteger;

public final class ProbeHooks {
    private static final AtomicInteger HITS = new AtomicInteger();

    static {
        System.out.println("helper: initialized");
    }

    private ProbeHooks() {}

    public static void hit() {
        HITS.incrementAndGet();
    }

    public static int hits() {
        return HITS.get();
    }
}
```

Đặt static initializer để quan sát **đúng khi nào helper đã khởi tạo**. Một hook production nên giữ đường gọi gọn hơn, thường tránh in ra `System.out` hoặc làm I/O trên từng request.

### 5.2. Agent chỉ theo dõi một target

Tệp `src/agent/SafeAgent.java`:

```java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicInteger;

public final class SafeAgent {
    private static volatile TargetOnlyTransformer current;

    private SafeAgent() {}

    public static void premain(String options, Instrumentation inst)
            throws ClassNotFoundException {
        System.out.println("agent: preparing");

        // Bắt helper khởi tạo TRƯỚC khi có callback của transformer.
        Class.forName("agent.ProbeHooks", true,
                SafeAgent.class.getClassLoader());

        TargetOnlyTransformer transformer = new TargetOnlyTransformer();
        transformer.prepare();
        current = transformer;

        inst.addTransformer(transformer);
        System.out.println("agent: transformer registered");
    }

    public static int targetCallbacks() {
        TargetOnlyTransformer transformer = current;
        return transformer == null ? 0 : transformer.callbacks.get();
    }

    private static final class TargetOnlyTransformer
            implements ClassFileTransformer {
        private static final ThreadLocal<Boolean> ACTIVE = new ThreadLocal<>();
        private final AtomicInteger callbacks = new AtomicInteger();

        void prepare() {
            ACTIVE.get();
            callbacks.get();
        }

        @Override
        public byte[] transform(
                Module module,
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain protectionDomain,
                byte[] classfileBuffer) {

            // Không gọi helper, logger hoặc guard trước khi lọc.
            if (!"demo/Target".equals(className)) {
                return null;
            }
            // Chỉ ngăn tái nhập trên cùng thread.
            if (Boolean.TRUE.equals(ACTIVE.get())) {
                return null;
            }

            ACTIVE.set(Boolean.TRUE);
            try {
                callbacks.incrementAndGet();
                return null; // Quan sát class load, không sửa bytes.
            } finally {
                ACTIVE.remove();
            }
        }
    }
}
```

Giải thích:

- `Class.forName(..., true, ...)` thực sự yêu cầu JVM khởi tạo `ProbeHooks` trước khi `addTransformer` chạy.
- `new TargetOnlyTransformer()` và `prepare()` chuẩn bị các cấu trúc đơn giản dùng trong callback.
- Bộ lọc `"demo/Target".equals(className)` chạy **trước** guard/counter; agent không đụng vào class ngoài phạm vi, kể cả lớp của chính agent và JDK.
- `ThreadLocal<Boolean>` dùng để tránh callback tái nhập cùng thread trong trường hợp đường gọi phức tạp hơn. Nó **không** ngăn chặn vòng chờ giữa các thread.
- `finally` dọn trạng thái để một exception không làm thread ấy bị đánh dấu “đang transform” vĩnh viễn.
- `return null` là cách đúng để nói transformer **không thay đổi bytecode**. Counter chỉ đếm sự kiện callback cho target; không phải số bytecode đã được instrument.

### 5.3. Target và ứng dụng

Tệp `src/demo/Target.java`:

```java
package demo;

import agent.ProbeHooks;

public final class Target {
    public int work() {
        // Mô phỏng lời gọi được chèn bằng bytecode weaving.
        ProbeHooks.hit();
        return 7;
    }
}
```

Tệp `src/demo/Main.java`:

```java
package demo;

import agent.ProbeHooks;
import agent.SafeAgent;

public final class Main {
    public static void main(String[] args) {
        System.out.println("application: start");
        Target target = new Target();
        System.out.println("work=" + target.work());
        System.out.println("probe hits=" + ProbeHooks.hits());
        System.out.println("target callbacks=" + SafeAgent.targetCallbacks());
    }
}
```

### 5.4. Manifest, chạy và đầu ra

Tệp `agent.mf` (có dòng trống cuối file):

```text
Manifest-Version: 1.0
Premain-Class: agent.SafeAgent

```

Tạo thư mục `out` trên Linux/macOS:

```bash
mkdir -p out
```

Nếu dùng Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
```

Biên dịch và đóng JAR bằng JDK 17+:

```bash
javac --release 17 -encoding UTF-8 -d out src/agent/ProbeHooks.java src/agent/SafeAgent.java src/demo/Target.java src/demo/Main.java
jar --create --file safe-agent.jar --manifest agent.mf -C out .
java -javaagent:safe-agent.jar -cp safe-agent.jar demo.Main
```

Đầu ra kỳ vọng khi chạy sạch chỉ với agent này:

```text
agent: preparing
helper: initialized
agent: transformer registered
application: start
work=7
probe hits=1
target callbacks=1
```

`helper: initialized` xuất hiện trước `agent: transformer registered`: đó là bằng chứng helper được khởi tạo trước khi callback hoạt động. `target callbacks=1` cho thấy target đã đi qua transformer một lần. `probe hits=1` đến từ lời gọi trực tiếp trong `Target.work()` mô phỏng bytecode được chèn. Hai counter này đo **hai việc khác nhau**.

Ví dụ gộp agent và ứng dụng vào một JAR dùng system loader để tập trung vào thứ tự chuẩn bị. Khi đưa agent vào hệ thống có plugin class loader/JPMS/bootstrap, phải xác nhận đường tìm helper riêng; warm-up ở agent loader không tự khắc phục `NoClassDefFoundError` của target loader.

## 6. Static initialization đệ quy chưa chắc là `ClassCircularityError`

Theo JLS §12.4.2, khi **cùng một thread** yêu cầu khởi tạo class mà chính nó đang khởi tạo, JVM xử lý đây là yêu cầu tái nhập. Vì thế có trường hợp vòng đọc field static không tạo lỗi liên kết, nhưng làm chương trình đọc được giá trị mặc định trước khi initializer hoàn tất.

Ví dụ Java 17+ độc lập, tệp `InitOrderDemo.java`:

```java
public final class InitOrderDemo {
    static final class A {
        static int value = B.value + 1;
    }

    static final class B {
        static int value = A.value + 1;
    }

    public static void main(String[] args) {
        System.out.println("A=" + A.value);
        System.out.println("B=" + B.value);
    }
}
```

Chạy:

```bash
javac --release 17 InitOrderDemo.java
java InitOrderDemo
```

Đầu ra:

```text
A=2
B=1
```

Giải thích theo thứ tự:
1. Truy cập `A.value` khiến JVM bắt đầu khởi tạo `A`.
2. Biểu thức của `A.value` cần `B.value` → JVM khởi tạo `B`.
3. `B.value` đọc `A.value` trong lúc **chính thread hiện tại** đang khởi tạo `A` → thấy giá trị mặc định `0`.
4. `B.value = 0 + 1 = 1`; sau đó `A.value = 1 + 1 = 2`.

Vòng phụ thuộc trên **không phải** một vòng superclass hierarchy. Vì thế đừng kết luận đó là `ClassCircularityError`. Cũng không nên sử dụng kiểu phụ thuộc này trong helper: code có thể hoạt động mà trả dữ liệu khởi tạo sai kỳ vọng.

**`ClassCircularityError`** xảy ra khi JVM phát hiện chu trình superclass hierarchy khi nạp class. Java source với `A extends B` và `B extends A` sẽ bị compiler từ chối; nhưng transformer phát ra class file sai hoặc custom loader sai có thể dẫn tới lỗi tương ứng. Recursive resolution khi transformer thử tìm lại một class đang được định nghĩa có thể cho `LinkageError` khác, tùy ngữ cảnh.

**`ExceptionInInitializerError`** là một nhóm vấn đề khác: nếu `<clinit>` thất bại do exception, lần dùng đầu thường ném lỗi này; các lần dùng sau có thể ném `NoClassDefFoundError: Could not initialize class ...`. Cần đọc **cause gốc** thay vì kết luận JAR bị thiếu.

## 7. Deadlock trong lớp nạp và khởi tạo class

`ClassLoader.loadClass(String, boolean)` mặc định đồng bộ trên kết quả `getClassLoadingLock(className)`. Với loader không **parallel-capable**, lock thường là chính đối tượng loader; với loader hỗ trợ parallel class loading, JVM/loader có thể dùng lock theo class name để tăng song song.

Hãy xét một custom loader có delegation chéo:

```text
Thread T1                               Thread T2
---------------------------------       ---------------------------------
Giữ loading lock loader A               Giữ loading lock loader B
đang nạp ClassA                          đang nạp ClassB
-> transformer A cần dependency B        -> initializer B cần dependency A
-> đợi loader B                          -> đợi loader A
                \                        /
                 \----- vòng chờ --------/
```

Đây là **mô hình rủi ro**, không phải kết quả bắt buộc của mọi `ClassLoader`. Thứ tự lock, chính sách delegation và thời điểm JVM cần resolve class quyết định liệu có tạo vòng chờ thật hay không.

Cũng có deadlock khi **hai thread khởi tạo hai class**: T1 đang khởi tạo helper A, chờ B do T2 giữ; T2 đang khởi tạo B lại chờ A do T1 giữ. Quy tắc tái nhập **cùng thread** của JLS không xóa được mọi vòng chờ giữa nhiều thread.

Bảo vệ phù hợp:
- Không gọi `Future.get()`, `CompletableFuture.join()`, latch/blocking I/O hoặc đợi một thread làm việc trong `transform`.
- Không bao cả callback trong một monitor global mà bên trong tiếp tục nạp lớp khác.
- Không gọi `Class.forName(targetName)`/reflection trên target trong load-time callback.
- Giữ thứ tự lock và class loader delegation nhất quán nếu sở hữu custom loader.
- Cân nhắc `ClassLoader.registerAsParallelCapable()` khi triển khai loader không phân cấp và hiểu đầy đủ hợp đồng của nó; đây **không phải thuốc chữa mọi deadlock**.

## 8. Preload helper vẫn phải đúng class loader

Giả sử agent nạp `agent.ProbeHooks` bằng system loader rồi chèn lệnh:

```text
invokestatic agent/ProbeHooks.hit:()V
```

vào class JDK do **bootstrap loader** định nghĩa. JVM sẽ resolve symbolic reference theo loader của **lớp mục tiêu** và các quy tắc liên kết, chứ không mặc nhiên chuyển sang loader đã chạy transformer. Vì vậy helper được system loader khởi tạo không có nghĩa bootstrap target gọi được helper. Hệ thống còn phải kiểm tra JPMS access nếu có named module.

Các lựa chọn tương ứng:

| Mục tiêu | Cách tiếp cận |
| --- | --- |
| Target và agent cùng system loader, đủ delegation | Helper có thể nằm trong agent JAR; warm-up ở system loader trước khi đăng ký |
| Target thuộc bootstrap | Helper JAR tối giản trong bootstrap search qua `appendToBootstrapClassLoaderSearch` trước khi target sử dụng; warm-up đúng bootstrap definition |
| Plugin class loader cô lập | Cung cấp helper trong đúng loader hoặc một bridge nhìn thấy được; kiểm tra class identity và phụ thuộc |
| Target trong named module | Đánh giá class visibility, read edges, package exports và method access riêng biệt |

Với bootstrap bridge, đừng đặt toàn bộ bytecode library, logger, HTTP client và application dependencies vào bootstrap để “tiện tìm”. Một helper mỏng dùng API bootstrap-visible, gọi tiếp sang dispatcher đã sẵn sàng qua cơ chế có kiểm soát sẽ giảm rủi ro tạo vòng nạp lớp.

## 9. Thiết kế callback an toàn và chính sách lỗi

Một callback trong hệ thống thật nên được thiết kế theo thứ tự sau:

```text
transform(module, loader, className, bytes)
    |
    +-- className null hoặc ngoài allowlist? -> return null
    |
    +-- class agent/helper/library? -> return null
    |
    +-- reentrancy guard cùng thread đang bật? -> return null
    |
    +-- chỉ xử lý bytecode trên dữ kiện đầu vào
    |
    +-- tạo byte[] mới hợp lệ, hoặc return null
    |
    +-- dọn guard bằng finally
```

**Thực hiện allowlist trước mọi thứ đắt tiền.** Nếu callback được gọi cho hàng nghìn lớp JDK và framework, nhiều helper/counter/logging class chưa khởi tạo cũng có thể bị chạm tới. Lọc sớm tránh làm phình phạm vi tác động.

Nếu cần sử dụng ASM hoặc Byte Buddy, khởi tạo các class/lõi cần thiết ngoài callback khi có thể. Tránh gọi loader của target để “check” class hiện tại. Nếu cần inspect method, đọc từ `classfileBuffer`; với class đang nạp, bytes đã là dữ liệu mà JVM gửi cho transformer.

Về exception, Javadoc `ClassFileTransformer` nêu rõ exception chưa bắt thoát khỏi `transform` **không tự chặn** các transformer còn lại hoặc toàn bộ quá trình load. Nó có thể được đối xử tương tự `return null` với transformer ấy. Vì vậy:
- Báo lỗi qua counter/telemetry đã chuẩn bị sẵn; tránh khởi tạo logger mới ngay trong error path.
- Phân biệt `callback_seen`, `transform_attempted`, `bytes_returned`, `target_loaded` và `probe_executed`.
- Có chính sách fail-open/fail-closed phù hợp yêu cầu observability, tránh coi “không thấy exception” là thành công.
- Không nuốt lỗi nghiêm trọng như `OutOfMemoryError` rồi báo hệ thống vẫn an toàn.

`removeTransformer` ngừng những lần callback tương lai; nó không tự loại bỏ bytecode đã chèn vào lớp trước đó. Nếu thiết kế khả năng dừng, cần cơ chế retransform hợp lệ hoặc hard/soft toggle được xây dựng từ đầu.

## 10. Chẩn đoán khi JVM treo hoặc báo lỗi liên kết

### 10.1. Tập dữ kiện cần thu thập

Ghi lại JVM vendor/version, manifest agent, thứ tự `-javaagent`, loader/module của target, tên lớp đang transform, thời điểm helper init, phiên bản cấu hình, số callback và stack trace nguyên nhân đầu tiên.

Đừng chỉ đọc exception cuối: một lỗi resolve do callback gây ra có thể xuất hiện lại khi ứng dụng về sau chạm tới symbolic reference liên quan.

### 10.2. Thread dump và class loading log

Nếu JVM vẫn chạy, kiểm tra thread bằng JDK:

```bash
jcmd PID Thread.print -l
```

Hoặc:

```bash
jstack -l PID
```

Thay `PID` bằng ID tiến trình thực. Tìm các thread với stack `ClassLoader.loadClass`, `getClassLoadingLock`, `<clinit>`, `ClassFileTransformer.transform`, `Future.get`, monitor chờ và các phương thức provider/logger. Cần phân biệt `BLOCKED`, `WAITING` và stack native. Trình phát hiện deadlock tự động có thể bỏ sót một số kiểu chờ trong class initialization/native runtime; **thread dump là bằng chứng để phân tích**, không thay thế suy luận về các lock.

Khi kiểm thử, có thể bật thống kê class loading:

```bash
java -Xlog:class+load=info -javaagent:safe-agent.jar -cp safe-agent.jar demo.Main
```

Log có thể rất dài và không trực tiếp cho biết tất cả lock, nhưng giúp quan sát lớp nào bị nạp bất ngờ quanh thời điểm transformer hoạt động.

### 10.3. Dấu hiệu và hướng xử lý

| Dấu hiệu | Kiểm tra |
| --- | --- |
| `ClassCircularityError` | Superclass hierarchy của class file mới, cấu trúc bytes, loader định nghĩa class |
| `LinkageError` khác trong/ngoài transformer | Recursive resolution, class identity, constraint, classfile và cause gốc |
| `ExceptionInInitializerError` | Static initializer của helper/dependency, nguyên nhân bên trong |
| `NoClassDefFoundError: Could not initialize class` | Lần khởi tạo trước đã lỗi; class ở trạng thái erroneous |
| `NoClassDefFoundError` cho helper | Target loader không resolve được helper/dependency |
| Thread đứng ở `ClassLoader.loadClass` | Loading lock, delegation chéo, callback đang yêu cầu dependency |
| Thread đứng ở `<clinit>` | Static initialization lock hoặc dependency liên thread |
| Callback tăng đột biến | Bộ lọc rộng, helper/library cũng bị instrument, recursive load |
| Bật probe nhưng không có hit | Callback chưa phù hợp, biến đổi trả `null`, lỗi bị che hoặc loader/helper không đúng |

## 11. Quy trình thử nghiệm và triển khai production

1. **Thiết kế graph phụ thuộc:** liệt kê transformer, helper, bytecode engine, logger, metrics và loader chứa mỗi class. Loại bỏ đường phụ thuộc ngược vào ứng dụng đang instrument.
2. **Chuẩn bị an toàn trong `premain`:** cấu hình, allowlist, helper-only JAR cần thiết, khởi tạo helper và đường nóng thiết yếu trước khi đăng ký transformer.
3. **Giai đoạn quan sát:** đăng ký callback chỉ đọc `className`, trả `null`, không chèn bytes. Kiểm tra số lần callback và thread dump nếu có chờ.
4. **Giai đoạn một mục tiêu:** instrument đúng một class/method với loader/module xác định và code path thật; kiểm tra helper loadable, invocation, bytecode verifier và latency.
5. **Thêm guard và phương án lỗi:** guard tái nhập cùng luồng, counters nhẹ, dọn `finally`; không giả định guard giải quyết deadlock giữa luồng.
6. **Mở rộng có giới hạn:** tăng allowlist theo lô, đo p95/p99 của ứng dụng, số lần transform, thời gian load, số lỗi liên kết và thời gian warm-up.
7. **Thử tải đồng thời:** nhiều thread cùng nạp class, plugin loader hoặc delegation không phân cấp; xác minh không có chờ lock và reentrancy bất thường.
8. **Có cách tắt:** cấu hình cho phép ngừng transform mới và loại bỏ hook theo cơ chế hợp lệ khi có capability; không kỳ vọng `removeTransformer` tự sửa những class đã nạp.
9. **Ghi nhận môi trường:** chạy thử trên JDK/vendor/version mục tiêu; hành vi cụ thể của loader và các dependency có thể khác giữa container/framework.

## 12. Câu hỏi tự kiểm tra

1. Vì sao `Class.forName("agent.ProbeHooks", true, agentLoader)` nên thực hiện trước `addTransformer`?
2. Sự khác nhau giữa `ProbeHooks.class`, `Class.forName(..., false, ...)` và `Class.forName(..., true, ...)` là gì?
3. Vì sao không nên gọi `Class.forName` trên **chính lớp đang transform**?
4. Vì sao nạp class đệ quy không luôn tạo `ClassCircularityError`? Lỗi này liên quan đến cấu trúc nào?
5. Vì sao ví dụ `InitOrderDemo` có `A=2`, `B=1` mà không bị class circularity?
6. `ThreadLocal<Boolean>` guard giúp gì và **không** giúp gì cho hai thread cùng giữ loader lock?
7. Cách nào để xác minh helper đã khởi tạo trước khi transformer được đăng ký?
8. Tại sao `target callbacks=1` trong ví dụ không chứng minh bytecode target đã bị thay đổi?
9. Nếu chèn helper vào class do bootstrap loader định nghĩa, còn phải giải quyết vấn đề gì ngoài warm-up?
10. Khi ứng dụng treo mà không ném exception, làm sao dùng thread dump để tìm vòng chờ và phân biệt vấn đề của class loader với static initialization?

## 13. Tài liệu tham khảo

- [Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer chạy trước khi lớp được định nghĩa, `null` và quy tắc exception.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `retransformClasses`, `removeTransformer`.
- [Java SE 21 — `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, agent JAR và cách JVM khởi động agent.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `getClassLoadingLock`, delegation, parallel-capable.
- [Java SE 21 — `ClassCircularityError`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassCircularityError.html): vòng superclass hierarchy.
- [Java SE 21 — `ExceptionInInitializerError`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ExceptionInInitializerError.html): lỗi trong static initializer.
- [Java Language Specification 21 — §12.4.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4.2): tái nhập khởi tạo trên cùng thread và chờ khi class đang được thread khác khởi tạo.
