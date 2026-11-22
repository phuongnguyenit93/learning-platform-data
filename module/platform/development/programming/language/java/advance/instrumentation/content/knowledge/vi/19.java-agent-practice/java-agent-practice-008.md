# Redefine thân phương thức khi một lời gọi cũ vẫn đang chạy

> **Ngữ cảnh:** Java Advance → Instrumentation → **Thực nghiệm agent**. Bài này kiểm chứng một hành vi quan trọng của JVM: khi `Instrumentation.redefineClasses(...)` cài **thân method mới**, một lời gọi đã có **active stack frame** vẫn tiếp tục thực thi **bytecode của phiên bản cũ**, trong khi **lời gọi mới sau redefinition** sử dụng bytecode mới. Chúng ta dùng Java agent khởi động bằng `-javaagent`, hai bản class độc lập có cùng cấu trúc, `CountDownLatch` để khóa chính xác thời điểm, rồi đọc kết quả `OLD`/`NEW`. Mã được biên dịch ở mức Java 17 và thực thi trên OpenJDK 24, cả với interpreter `-Xint`.

## 1. Câu hỏi của thí nghiệm

Giả sử một thread đã đi vào:

~~~java
public static String work(CountDownLatch entered, CountDownLatch release) {
    entered.countDown();
    release.await(); // Cú pháp giản lược: bản hoàn chỉnh có try/catch.
    return "OLD";
}
~~~

Ngay sau khi thread báo `entered` nhưng **chưa** vượt qua `release.await()`, agent cài phiên bản mới của **cùng class** với method:

~~~java
public static String work(CountDownLatch entered, CountDownLatch release) {
    entered.countDown();
    release.await(); // Cú pháp giản lược: bản hoàn chỉnh có try/catch.
    return "NEW";
}
~~~

**Dự đoán nào đúng?**

- **A:** Mọi lời gọi, kể cả lời gọi đang chờ ở `await()`, lập tức trả `NEW`.
- **B:** Lời gọi đang hoạt động tiếp tục theo method cũ và trả `OLD`; lời gọi bắt đầu sau redefinition dùng method mới và trả `NEW`.
- **C:** JVM bắt buộc đợi toàn bộ lời gọi cũ kết thúc mới trả về từ `redefineClasses`.
- **D:** JVM mặc định dừng thread và chạy lại method từ đầu.

**Đáp án theo đặc tả là B.** JVM TI `RedefineClasses` nói rằng bản method mới áp dụng với **new invokes**, còn các frames đã active vẫn chạy bytecodes gốc. `Instrumentation.redefineClasses` mô tả cùng semantics. Đây không phải “cảm giác race” hay quy tắc riêng của Java compiler; nó là hành vi của cơ chế redefinition được tài liệu hóa.

Điểm cốt lõi: **class definition mới** và **active invocation cũ** có thể đồng thời tồn tại trong cùng JVM trong một khoảng thời gian. Chúng không tạo hai `Class<?>` objects ứng dụng phải chọn, mà là các **method versions** khác nhau đối với lời gọi đã bắt đầu và lời gọi mới.

## 2. Hình dung thời gian: active stack frame và method version

Ta dùng hai threads:

- **Thread T1:** đã gọi `VersionedTarget.work(...)` V1. Nó đi tới `release.await()` và chưa return.
- **Thread T0 (main):** đợi T1 báo `entered`, gọi agent `redefineClasses` với bytes V2, sau đó gọi `work(...)` lần mới, cuối cùng cho T1 tiếp tục.

~~~text
Thời điểm     Thread T1: lời gọi cũ           Thread T0: main/agent
─────────     ──────────────────────────      ───────────────────────────
t0            enter work() V1                 tạo latch entered/release
t1            entered.countDown()             entered.await() thành công
t2            release.await()  [ĐANG CHỜ]    agent chuẩn bị V2 class-file bytes
t3            frame V1 còn active             redefineClasses(target, V2)
t4            frame V1 còn active             redefineDone (V2 đã được cài)
t5            frame V1 còn active             gọi work() mới -> "NEW"
t6            frame V1 còn active             release.countDown()
t7            tiếp tục thân V1 -> "OLD"       join(T1)
t8            kết thúc lời gọi cũ             in oldResult="OLD"
~~~

Ở `t3–t5`, JVM không cần “thay instruction pointer” của frame V1 sang vị trí tương ứng trong V2. Trên thực tế, map một program counter cũ sang bytecode mới có thể hoàn toàn không xác định: method body mới có thể khác nhánh, số instruction hoặc layout. JVM cho phép frame cũ hoàn tất theo **method version đã bắt đầu**.

### `active frame` không phải bản sao toàn bộ trạng thái

Một active frame có state thực thi của lời gọi như program counter, local variables và operand stack; nó không sao chép toàn bộ heap hay static fields. Vì vậy:

- **Bytecode:** frame V1 tiếp tục thực hiện bytecode V1.
- **Dữ liệu dùng chung:** nếu method V1 đọc một field sau khi redefinition, nó vẫn có thể quan sát những thay đổi dữ liệu thông thường từ threads khác theo Java Memory Model.
- **Class identity:** cùng `Class<?>` và type system của class đang được redefine; không tạo class có tên mới theo mặc định.
- **JIT:** JVM có thể cần xử lý/deoptimize compiled code khi đổi phiên bản method. Không suy ra semantics từ việc một frame đang interpreted hay compiled; quy tắc old/new method versions vẫn phải được tôn trọng.
- **Side effects:** mọi IO, mutation, external request đã xảy ra trước khi redefine **không được rollback**.

Do đó câu “lời gọi cũ chạy phiên bản cũ” có nghĩa **bytecodes của method đang active**, không có nghĩa toàn bộ environment và dữ liệu biến thành một snapshot cũ.

## 3. Redefinition là gì, và khác nạp class mới thế nào?

Trong Java Instrumentation:

~~~java
instrumentation.redefineClasses(
    new ClassDefinition(targetClass, replacementClassFileBytes)
);
~~~

`targetClass` là `Class<?>` đã load. `replacementClassFileBytes` là **toàn bộ bytes của file .class mới** có **cùng binary name** và cấu trúc hợp lệ theo giới hạn redefinition. Không đưa vào tên source `.java`, đường dẫn JAR hoặc một mảng chỉ chứa phần bytecode của method.

API:

- **`redefineClasses`:** lấy trực tiếp bytes của class replacement, ví dụ sau khi build phiên bản V2. Không cần dựa vào cách đọc original bytes trong transformer.
- **`retransformClasses`:** yêu cầu JVM chạy lại transformer pipeline trên class đã load, phù hợp cho instrumentation chỉnh dựa trên class bytes. Nó cũng có quy tắc tương ứng về **active frames cũ** và **new invokes mới**, nhưng cơ chế cung cấp bytes khác.
- **`ClassFileTransformer.transform`:** callback nhận class bytes khi định nghĩa/tái định nghĩa/tái biến đổi class, **không phải** callback trên mỗi method invocation.

Một phần quan trọng trong manifest:

~~~text
Can-Redefine-Classes: true
~~~

Và tại runtime:

~~~java
boolean supported = instrumentation.isRedefineClassesSupported();
boolean modifiable = instrumentation.isModifiableClass(targetClass);
~~~

Nếu `supported=false` hoặc `modifiable=false`, không chạy thí nghiệm theo đường này. Redefinition là **capability tùy chọn**, và `Can-Redefine-Classes` cần được khai trong agent manifest. Không dùng `Can-Retransform-Classes` để thay thế capability của `redefineClasses`.

### Những giới hạn class schema

Ở Java 17+ theo JVM TI, khi redefinition thông thường, không được tùy tiện:

- Thêm, xóa hoặc đổi tên field/method.
- Đổi method signatures/descriptors, access modifiers, staticness và superclass/interfaces.
- Thay các class-file attributes liên quan đến cấu trúc `NestHost`, `NestMembers`, `Record` và `PermittedSubclasses`.
- Đưa bytes không hợp lệ, version quá mới cho JVM, hoặc class name khác target.

Có thể **thay thân method** và những nội dung được JVM cho phép, như hằng string trả về trong bài. Hai phiên bản V1/V2 bên dưới có **cùng package, tên class, một field, constructor và method signatures**; chỉ thay literal trả về trong `work` và giá trị khởi tạo static để chứng minh initializer không chạy lại.

## 4. Thiết kế bài lab tránh race và output ngẫu nhiên

Một thí nghiệm yếu thường viết:

~~~java
new Thread(() -> oldCall()).start();
Thread.sleep(100);
redefine();
~~~

Cách này **không xác nhận thread đã vào oldCall** trước khi redefine. Trên máy bận, thread có thể được scheduler chạy muộn; kết quả tình cờ NEW rồi người học rút ra kết luận sai.

Ta dùng **hai `CountDownLatch`**:

1. `entered = new CountDownLatch(1)`: thread T1 gọi `entered.countDown()` **sau khi đã vào method V1**.
2. `release = new CountDownLatch(1)`: thread T1 đợi trong method V1, frame chưa return.
3. Main gọi `entered.await(timeout)`, nên biết T1 đã đi vào method và chạm cổng `entered`.
4. Main redefine class, gọi method mới bằng các latches không chặn, rồi cho T1 tiếp tục qua `release.countDown()`.
5. Main `join(timeout)`, xác nhận T1 hoàn tất trước khi đọc `AtomicReference<String> oldResult`.

Không cần dựa vào sleep, timing của CPU, độ trễ network hay giao diện debugger. `CountDownLatch` và `Thread.join` còn có các quan hệ đồng bộ/happens-before được Java API quy định, giúp đọc kết quả an toàn trong chương trình test.

**Không dùng `Thread.stop()`, suspend thủ công hay `PopFrame`** để tạo điều kiện thử nghiệm; ta muốn quan sát JVM redefinition bình thường, không ép stack frame thay đổi bằng debugging control.

## 5. Cấu trúc dự án và cách giữ V2 ngoài runtime classpath

Một class Java cùng binary name xuất hiện trong **hai source folders** để compile tách biệt:

~~~text
redefine-live-frame-lab/
├── manifest.mf
├── src/
│   ├── v1/
│   │   └── demo/target/VersionedTarget.java
│   ├── v2/
│   │   └── demo/target/VersionedTarget.java
│   ├── agent/
│   │   └── demo/agent/RedefineAgent.java
│   └── app/
│       └── demo/app/Main.java
└── out/                              # được tạo khi build
    ├── v1/demo/target/VersionedTarget.class
    ├── v2/demo/target/VersionedTarget.class
    ├── agent/demo/agent/RedefineAgent.class
    ├── app/demo/app/Main.class
    └── redefine-agent.jar
~~~

Trong lần chạy:

- **Chỉ `out/v1`** thuộc application classpath và được JVM load lần đầu.
- **`out/v2` không nằm trong classpath**; agent đọc file V2 **bằng `Files.readAllBytes(Path)`** rồi dùng `ClassDefinition` để yêu cầu redefine class đã load.
- Agent classes nằm trong agent JAR kích hoạt bằng `-javaagent`; ứng dụng có thể gọi public static method của agent trong thí nghiệm này vì Java instrumentation đưa agent JAR vào cơ chế tìm kiếm của system class loader. Trong production, ứng dụng nghiệp vụ thường **không** nên phụ thuộc trực tiếp class của agent như thiết kế học tập này.
- Các nguồn V1 và V2 **không compile cùng một invocation `javac`** do trùng binary name.

Nếu vô tình đưa `out/v2` vào runtime classpath trước `out/v1`, JVM có thể định nghĩa V2 ngay từ đầu; thí nghiệm mất ý nghĩa. Cần giữ chính xác phần classpath trong lệnh chạy.

## 6. Java 17+ source: V1 và V2

### 6.1 V1 — lời gọi cũ sẽ trả OLD

File `src/v1/demo/target/VersionedTarget.java`:

~~~java
package demo.target;

import java.util.concurrent.CountDownLatch;

public final class VersionedTarget {
    public static int marker = 41;

    private VersionedTarget() {}

    public static String work(CountDownLatch entered, CountDownLatch release) {
        entered.countDown();

        try {
            release.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return "INTERRUPTED";
        }

        return "OLD";
    }
}
~~~

Method V1:

1. Count down `entered` để main biết frame đã active.
2. Đợi `release`; frame `work` vẫn nằm trên stack của T1 trong khi code thực thi đang ở `CountDownLatch.await`.
3. Nếu được release bình thường, trả string `OLD`.
4. Nếu thread bị interrupt, khôi phục interrupt flag và trả `INTERRUPTED` để không giả vờ đó là kết quả V1 bình thường.

Field `marker` được khởi tạo thành 41 bởi class initialization của V1. Vì là `static int` **không phải compile-time constant `static final`**, việc đọc field ở app là một field access thực tế chứ không bị compiler inline giá trị literal từ source.

### 6.2 V2 — lời gọi bắt đầu sau redefine sẽ trả NEW

File `src/v2/demo/target/VersionedTarget.java`:

~~~java
package demo.target;

import java.util.concurrent.CountDownLatch;

public final class VersionedTarget {
    public static int marker = 99;

    private VersionedTarget() {}

    public static String work(CountDownLatch entered, CountDownLatch release) {
        entered.countDown();

        try {
            release.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return "INTERRUPTED";
        }

        return "NEW";
    }
}
~~~

So V1/V2:

| Thành phần | V1 | V2 | Có làm class schema thay đổi? |
|---|---|---|---|
| Binary name | `demo.target.VersionedTarget` | Y hệt | Không |
| Class modifiers | `public final` | Y hệt | Không |
| Constructor | `private VersionedTarget()` | Y hệt | Không |
| Field | `public static int marker` | Y hệt | Không |
| Method | `public static String work(CountDownLatch, CountDownLatch)` | Y hệt | Không |
| Method body result | `"OLD"` | `"NEW"` | **Thay bytecode/hằng**, hợp lệ |
| Static initializer assigned value | 41 | 99 | Body initializer khác, nhưng **không chạy lại** khi redefine |

**Điều quan trọng:** `marker = 99` nằm trong bytecode class initialization của V2 nhưng redefining **không chạy lại class initializer `<clinit>`**. JVM giữ nguyên giá trị static đã thiết lập (41). Ta thêm khác biệt này để người học không nhầm “cài class file mới” với “load một class mới từ đầu”.

Không thêm field/method nào ở V2: yêu cầu đổi thân method là trọng tâm, không thử phá cấu trúc.

## 7. Java agent sử dụng `ClassDefinition`

File `src/agent/demo/agent/RedefineAgent.java`:

~~~java
package demo.agent;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.IOException;

public final class RedefineAgent {
    private static Instrumentation inst;

    private RedefineAgent() {}

    public static void premain(String args, Instrumentation instrumentation) {
        inst = instrumentation;
        System.out.println("[AGENT] redefineSupported="
                + inst.isRedefineClassesSupported());
    }

    public static void replace(Class<?> target, Path classFile)
            throws IOException, ClassNotFoundException, UnmodifiableClassException {
        if (inst == null || !inst.isRedefineClassesSupported()) {
            throw new IllegalStateException("Class redefinition not supported");
        }
        if (!inst.isModifiableClass(target)) {
            throw new IllegalStateException("Class not modifiable");
        }

        byte[] bytes = Files.readAllBytes(classFile);
        inst.redefineClasses(new ClassDefinition(target, bytes));

        System.out.println("[AGENT] redefineDone");
    }
}
~~~

Đây là class agent đầy đủ, dùng API chuẩn **`java.lang.instrument`**:

- `premain(String, Instrumentation)` được JVM gọi khi bắt đầu với `-javaagent`.
- `isRedefineClassesSupported()` kiểm tra capability. Việc manifest xin `Can-Redefine-Classes: true` là **cần nhưng chưa đủ** nếu JVM không hỗ trợ.
- `isModifiableClass(target)` là kiểm tra trước; `true` **không bảo đảm** mọi replacement bytes đều hợp lệ.
- `Files.readAllBytes(classFile)` đọc **đúng file `VersionedTarget.class` V2** đã compile từ trước, không load V2 bằng class loader.
- `new ClassDefinition(target, bytes)` ghép `Class<?>` hiện có với bytes thay thế.
- `inst.redefineClasses(...)` là điểm JVM **kiểm tra, verify và cài định nghĩa mới** (có thể qua transformer chain của JVM nếu agent khác đăng ký transformer phù hợp).
- Chỉ sau khi API **trả về bình thường**, code in `redefineDone`. Nếu có exception, không được in thành công giả.

**Không cần đăng ký `ClassFileTransformer`** cho cách demo dùng class-file bytes thay thế trực tiếp. Trong một hệ thống nhiều agents, registered transformers có thể ảnh hưởng class bytes cuối cùng; nên test với agents thực tế cùng JVM.

**Về trạng thái `inst`:** field static được set trong `premain` trước khi `main` chạy trong lab, do đó app có thể gọi method `replace`. Trong production có dynamic Attach, nhiều class loaders hoặc race với startup, cần thiết kế lifecycle/visibility cẩn thận hơn; không sao chép static global này thành một API công khai không có synchronization mà không đánh giá.

## 8. Ứng dụng giữ một frame V1 đang chạy

File `src/app/demo/app/Main.java`:

~~~java
package demo.app;

import demo.agent.RedefineAgent;
import demo.target.VersionedTarget;
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class Main {
    public static void main(String[] args) throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicReference<String> oldResult = new AtomicReference<>("UNSET");

        Thread active = new Thread(
                () -> oldResult.set(VersionedTarget.work(entered, release)),
                "active-v1");
        active.start();

        try {
            if (!entered.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Old method did not enter");
            }
            System.out.println("[APP] oldActive=true");
            System.out.println("[APP] markerBefore=" + VersionedTarget.marker);

            RedefineAgent.replace(
                    VersionedTarget.class,
                    Path.of("out", "v2", "demo", "target", "VersionedTarget.class"));

            String fresh = VersionedTarget.work(
                    new CountDownLatch(1), new CountDownLatch(0));
            System.out.println("[APP] freshResult=" + fresh);
            System.out.println("[APP] markerAfter=" + VersionedTarget.marker);
        } finally {
            release.countDown();
        }

        active.join(10000);
        if (active.isAlive()) {
            throw new IllegalStateException("Active call did not finish");
        }
        System.out.println("[APP] oldResult=" + oldResult.get());
    }
}
~~~

Phân tích từng mốc:

1. `active.start()` tạo T1. T1 bắt đầu method V1, count down `entered`, rồi đợi `release`.
2. `entered.await(10, TimeUnit.SECONDS)` trên T0 bảo đảm T1 đã đi qua mốc entry **trước redefinition**. Nếu timeout, chương trình báo lỗi, không tiếp tục đo với giả định sai.
3. `markerBefore=41` xác nhận V1 đã được class initialization.
4. Agent redefine target với bytes V2.
5. T0 gọi `VersionedTarget.work(new CountDownLatch(1), new CountDownLatch(0))`. Latch release ở **0** không block, vì vậy invocation bắt đầu sau redefine và trả `NEW` ngay.
6. `markerAfter=41` xác nhận class initializer V2 **không** chạy lại; giá trị static đang tồn tại vẫn giữ 41.
7. `finally { release.countDown(); }` thả thread T1 ngay cả khi thao tác redefine/nội dung in có exception. Đây là cleanup quan trọng để lab không bỏ thread treo.
8. `active.join(10000)` đợi T1 kết thúc, sau đó đọc `oldResult`. Kết quả mong đợi là `OLD` vì frame T1 vẫn chạy bytecode V1.
9. `AtomicReference` bảo đảm lưu/đọc kết quả an toàn giữa threads. Dù `join` cũng có happens-before theo JMM, dạng này làm rõ ý định chia sẻ kết quả.

Với môi trường bất thường nếu T1 bị interrupt, `work` trả `INTERRUPTED`. Đây là một outcome **khác** với semantics old/new nên phải điều tra nếu xuất hiện; không kết luận redefinition “đã đổi frame” chỉ vì một thread bị interrupt.

## 9. Manifest, compile và chạy

### 9.1 `manifest.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.RedefineAgent
Can-Redefine-Classes: true

~~~

Manifest có newline và dòng trống sau các thuộc tính. Một số lỗi phổ biến:

- Viết sai tên binary class `demo.agent.RedefineAgent`.
- Thiếu `Can-Redefine-Classes: true` hoặc dùng nhầm `Can-Retransform-Classes: true`.
- Đặt manifest bên ngoài JAR nhưng không truyền qua `jar --manifest`.
- Đóng gói thiếu `RedefineAgent.class`.
- Truyền path replacement tới file V1 hoặc đặt V2 trong runtime classpath.

### 9.2 Build trên macOS/Linux (Bash)

Chạy từ thư mục gốc `redefine-live-frame-lab`:

~~~bash
mkdir -p out/v1 out/v2 out/agent out/app

javac --release 17 -d out/v1 src/v1/demo/target/VersionedTarget.java
javac --release 17 -d out/v2 src/v2/demo/target/VersionedTarget.java
javac --release 17 -d out/agent src/agent/demo/agent/RedefineAgent.java
javac --release 17 -cp out/v1:out/agent -d out/app src/app/demo/app/Main.java

jar --create --file out/redefine-agent.jar --manifest manifest.mf -C out/agent .

java -javaagent:out/redefine-agent.jar -cp out/app:out/v1 demo.app.Main
~~~

Các dấu `:` trong classpath là phân cách trên macOS/Linux. Ở **compile time**, app cần biết class `RedefineAgent` và `VersionedTarget` nên `-cp out/v1:out/agent`. Ở **runtime**, agent JAR đi qua `-javaagent`; app chỉ dùng `out/app:out/v1` và agent classes được system loader tìm từ agent JAR theo hợp đồng instrumentation.

### 9.3 Build trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force -Path out/v1, out/v2, out/agent, out/app | Out-Null

javac --release 17 -d out/v1 src/v1/demo/target/VersionedTarget.java
javac --release 17 -d out/v2 src/v2/demo/target/VersionedTarget.java
javac --release 17 -d out/agent src/agent/demo/agent/RedefineAgent.java
javac --release 17 -cp "out/v1;out/agent" -d out/app src/app/demo/app/Main.java

jar --create --file out/redefine-agent.jar --manifest manifest.mf -C out/agent .

java "-javaagent:out/redefine-agent.jar" -cp "out/app;out/v1" demo.app.Main
~~~

Trên Windows classpath dùng dấu `;`, trong khi `-javaagent:...` là một **JVM option riêng**. Lệnh runtime **cố ý không chứa `out/v2`**. Dù V2 class file tồn tại trên đĩa, JVM không tự định nghĩa thêm class cùng binary name để thay V1; agent chỉ sử dụng bytes V2 làm replacement.

### 9.4 Stdout thực nghiệm

Biên dịch bằng `javac --release 17`, chạy trên OpenJDK 24.0.2 (một phiên bản Java 24):

~~~text
[AGENT] redefineSupported=true
[APP] oldActive=true
[APP] markerBefore=41
[AGENT] redefineDone
[APP] freshResult=NEW
[APP] markerAfter=41
[APP] oldResult=OLD
~~~

**Giải thích theo thứ tự log:**

| Mốc | Ai in | Chứng minh |
|---|---|---|
| `redefineSupported=true` | Agent `premain` | JVM thử nghiệm cung cấp capability redefinition được yêu cầu |
| `oldActive=true` | Main sau latch | Lời gọi T1 đã vào V1 và đang chờ release, chưa return |
| `markerBefore=41` | Main | Class đã initialized theo V1 |
| `redefineDone` | Agent sau API call | JVM đã chấp nhận V2 bytes và cài định nghĩa mới |
| `freshResult=NEW` | Main sau lời gọi mới | **New invocation** dùng method body V2 |
| `markerAfter=41` | Main | Static field value được giữ, V2 class initializer không chạy lại |
| `oldResult=OLD` | Main sau release/join | **Active invocation V1** hoàn tất bằng bytecode cũ |

Có thể máy/vm khác không hỗ trợ redefinition; khi `redefineSupported=false`, bài thử sẽ dừng bằng exception với guard trong agent thay vì tuyên bố tính năng tồn tại. Chỉ báo PASS khi JVM báo capability và toàn bộ stdout có kết quả như trên.

### 9.5 Kiểm tra V1/V2 có cùng API schema

Sau compile:

~~~bash
javap -public out/v1/demo/target/VersionedTarget.class
javap -public out/v2/demo/target/VersionedTarget.class
~~~

Hai lần cho cùng public API tiêu biểu:

~~~text
public final class demo.target.VersionedTarget {
  public static int marker;
  public static java.lang.String work(
      java.util.concurrent.CountDownLatch,
      java.util.concurrent.CountDownLatch);
}
~~~

**Chú ý:** ví dụ trên được **xuống dòng để dễ đọc**; `javap` thường in method signature trên một dòng. Constructor private không hiển thị với `-public`. Muốn xem đủ hơn:

~~~bash
javap -p out/v1/demo/target/VersionedTarget.class
javap -p out/v2/demo/target/VersionedTarget.class
~~~

Muốn kiểm tra bytecode cụ thể:

~~~bash
javap -c -p out/v1/demo/target/VersionedTarget.class
javap -c -p out/v2/demo/target/VersionedTarget.class
~~~

Tìm đường trả literal `OLD` trong V1, `NEW` trong V2 và giá trị trong `<clinit>`. Đừng so raw class-file bytes rồi thấy khác để kết luận sai: body, constant pool và initializer bodies **được phép khác** theo giới hạn redefinition; điều quan trọng là schema/method semantics hợp lệ.

## 10. Thử nghiệm bổ sung: `-Xint` và lặp nhiều lần

### 10.1 Chạy interpreted mode

Nếu muốn phân biệt với tối ưu JIT, chạy:

**Bash:**

~~~bash
java -Xint -javaagent:out/redefine-agent.jar -cp out/app:out/v1 demo.app.Main
~~~

**PowerShell:**

~~~powershell
java -Xint "-javaagent:out/redefine-agent.jar" -cp "out/app;out/v1" demo.app.Main
~~~

Trong thử nghiệm trên OpenJDK 24, stdout **giống hệt** mục 9.4, bao gồm `freshResult=NEW` và `oldResult=OLD`. Điều này phù hợp với đặc tả, không phải do JIT cache method cũ một cách tình cờ.

### 10.2 Lặp để loại bỏ một race ngẫu nhiên

Chạy lại lệnh default vài lần và bảo đảm cả hai dòng:

~~~text
[APP] freshResult=NEW
[APP] oldResult=OLD
~~~

vẫn xuất hiện. Bản lab đã được kiểm tra ba lần lặp default và một lần với `-Xint`; cả bốn đều cho kết quả mong đợi.

**Điểm lưu ý:** chạy lặp không thay thế chứng minh theo đặc tả, nhưng là QA hữu ích để bắt lỗi setup như đặt nhầm V2 trong classpath hoặc thiếu latch. Bằng chứng chính vẫn đến từ **hợp đồng JVM TI và Instrumentation**.

## 11. Tại sao JVM không làm “replace frame” tự động?

Một active frame đang chứa:

- Reference tới version method mà thread đã enter.
- Local variables và operand stack của invocation đó.
- Program counter tương ứng với instruction position của method version hiện hành với frame.

Nếu body mới được compile từ code thay đổi tự do, vị trí “tương đương” với instruction hiện tại có thể không tồn tại. Một old frame có thể đang nằm giữa `try/finally`, monitor, native call, hoặc một chuỗi side effects. Việc chạy từ giữa V2 có thể vi phạm semantics hoặc chạy side effects sai.

Do đó JVM TI mô tả **old method versions có thể trở thành obsolete** khi redefinition cài method version mới. Một frame đã active **cứ chạy code cũ**, còn new invocation vào version mới.

### “Obsolete method” không có nghĩa thread bị kill

Trong JVMTI, method version cũ có thể được đánh dấu obsolete. Điều đó không tự:

- Tắt thread, ném exception hoặc sửa `Thread.State`.
- Chuyển local variables sang một frame mới.
- Chạy lại method từ đầu.
- Gọi lại constructor/static initializer.
- Undo database transaction hoặc outgoing HTTP requests đã thực hiện.

**Debugger có công cụ đặc biệt** như JVMTI `PopFrame` để pop một frame trong điều kiện được hỗ trợ và sau đó thực thi lại logic theo quyền điều khiển debugger. Đây là một cơ chế **khác** với `Instrumentation.redefineClasses`, có constraints riêng và có thể ảnh hưởng side effects. Không dùng `PopFrame` như một “fix” tự động cho hot production traffic.

### Trường hợp V1 frame gọi method khác sau redefinition

Giả sử frame V1 chạy tiếp và thực hiện **một invocation mới** tới một method vừa được redefine. Invocation mới đó có thể sử dụng **version mới** của method được gọi, dù **frame caller** vẫn đang thực thi bytecode V1. Do đó trong một transaction đang chạy có thể quan sát **mixed-version behavior** (old code ở caller, new code ở callee).

Không nên từ câu “active frame giữ method body cũ” suy ra **toàn bộ call tree** đóng băng ở V1. JVM không cung cấp transaction-level code-version snapshot cho request. Nếu cần thay đổi đồng bộ trên nhiều service methods, phải thiết kế backward-compatible behavior hoặc quiescence/drain strategy.

## 12. Redefine không reset object hay static state

Theo `Instrumentation.redefineClasses`:

- Redefine **không tạo mới Class object** của target theo kiểu load một binary name trong class loader mới.
- **Không tự khởi tạo lại class** và không chạy lại initializer.
- Giá trị static fields **giữ nguyên**; object instances hiện có không bị “tạo lại”.
- Class schema changes bị ràng buộc để những object/stack frames đã tồn tại tiếp tục hợp lệ.

Trong ví dụ, V2 viết `marker = 99` nhưng sau redefine `markerAfter=41`. Sự khác biệt này rất quan trọng khi hotfix một bug trong code khởi tạo:

~~~java
// V1
public static int marker = 41;

// V2
public static int marker = 99;
~~~

Chỉ đổi bytecode của `<clinit>` **không** sửa giá trị 41 đã nằm trong static field. Nếu nghiệp vụ thật sự cần state migration, phải thiết kế thao tác migration riêng, đồng bộ an toàn, xét dữ liệu đang sử dụng, và không trông chờ redefine tự làm nó.

Tương tự, một instance đang giữ field values không tự trở thành object mới sau redefine. Khi gọi **một method mới** trên instance cũ sau redefine, method có thể dùng bytecode mới nhưng vẫn đọc các **field values cũ** của instance.

**Lưu ý dữ liệu:** bài lab dùng static field đơn giản, không chứng minh cơ chế migration hoặc atomic update nhiều fields. Một agent product cần xét Java Memory Model, happens-before và concurrency của dữ liệu nếu hotfix thay đổi nghĩa của fields.

## 13. Giới hạn và đường lỗi của `redefineClasses`

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `isRedefineClassesSupported() == false` | Manifest thiếu `Can-Redefine-Classes: true` hoặc JVM không hỗ trợ | Dừng/thông báo capability; đừng gọi redefine |
| `isModifiableClass(target) == false` | Class nằm trong nhóm JVM không cho sửa | Không cố thay; dùng fallback |
| `UnmodifiableClassException` | API từ chối class không modifiable | Kiểm tra đúng `Class<?>` và VM support |
| `UnsupportedOperationException` | JVM không hỗ trợ redefinition hoặc bytes đổi schema/attribute bị cấm | So field/method descriptors/modifiers, hierarchy, nest/record/sealed attributes |
| `ClassFormatError`/`VerifyError` | Replacement bytes không phải class hợp lệ hoặc verification lỗi | Build đúng, kiểm tra class-file/stack maps bằng javap/test |
| `NoClassDefFoundError` | Binary name trong replacement bytes không khớp target hoặc linkage khác | Đọc đúng file V2 class name |
| `UnsupportedClassVersionError` | File V2 cần JDK mới hơn JVM chạy | Compile `--release` phù hợp và kiểm tra dependency versions |
| `IOException` khi đọc replacement | Path `out/v2/...` không tồn tại, quyền file hoặc CWD sai | Chạy từ project root, kiểm tra file |
| `IllegalStateException` từ guard trong lab | inst chưa sẵn sàng hoặc capability/target không thỏa | Xem `premain`, manifest, `isModifiableClass` |
| `oldActive=false` hoặc timeout | T1 chưa chạm latch trong thời gian cho phép | Kiểm tra thread start/deadlock, không bỏ qua precondition |
| `oldResult=INTERRUPTED` | T1 bị interrupt khi đợi `release` | Điều tra actor interrupt và test setup |
| `oldResult=NEW` | Có thể V2 được load ngay từ đầu hoặc test không thật sự giữ frame V1 | Kiểm tra classpath, latch, output trình tự, V1 source |
| `freshResult=OLD` | JVM chưa cài V2 hoặc đọc sai file replacement | Kiểm tra `redefineDone`, V2 bytes/path, transformers |
| `markerAfter=99` | Có thể chạy V2 từ đầu hoặc đã mutate static state riêng | Đối chiếu classpath và log trước/sau, không quy kết initializer chạy lại nếu chưa kiểm tra |

**Atomicity:** `redefineClasses` nhận nhiều `ClassDefinition` trong một call. Theo Javadoc, nếu method ném exception thì **không có class nào** trong tập bị redefine. Đừng viết quy trình rollout dựa trên giả định “một số classes có thể đã thay” trong một batch API thất bại. Tuy nhiên những side effects của code chạy trước đó hoặc các redefinitions ở **lời gọi API khác** không được rollback.

**Thread safety:** Không coi redefinition như transaction đồng bộ trạng thái ứng dụng. Nó thay **code được gọi sau điểm cài**, không tự chờ mọi thread kết thúc operation. Cần bảo đảm V1/V2 tương thích trong giai đoạn chúng cùng có active frames.

**JIT/safepoints:** JVM có thể cần công việc nội bộ để cài method versions. Đừng hiểu kết quả bài là khẳng định `redefineClasses` không bao giờ pause threads hay có overhead. Nó chỉ chứng minh API có thể hoàn tất **khi một frame cũ vẫn active** và frame ấy khi tiếp tục sẽ dùng bytecode cũ.

## 14. So sánh với retransformation và debugger hot swap

| Tiêu chí | `redefineClasses` | `retransformClasses` | Debugger hot swap |
|---|---|---|---|
| Đầu vào | Bytes replacement class files qua `ClassDefinition` | Các `Class<?>` cần chạy lại transformer chain | Debugger/VM wire protocol & capabilities |
| Capability | `Can-Redefine-Classes`, `isRedefineClassesSupported()` | `Can-Retransform-Classes`, `isRetransformClassesSupported()` | JDWP/JVM TI capabilities của target VM |
| Giới hạn class schema | Không tự do thêm/đổi fields/methods, inheritance... | Tương tự với những thay đổi hỗ trợ | Tùy VM, thường tuân theo giới hạn của redefinition |
| Active frames | Tiếp tục code cũ | Tiếp tục code cũ | Theo VM; debugger có thể hiển thị obsolete frames |
| New invocations | Dùng body mới | Dùng body sau transformer pipeline | Dùng body mới sau hot swap |
| Có chạy lại `<clinit>`? | Không | Không | Không theo redefinition thông thường |
| Mục tiêu phù hợp | Cài class bytes mới từ build/hotfix lab | Instrument/reinstrument class đã load | Debug fix-and-continue trên môi trường an toàn |

**Đừng dùng `redefineClasses` như bản nâng cấp “mạnh hơn, xóa mọi hạn chế” so với retransform.** Hai API có workflows khác nhau nhưng cùng phải tuân thủ những class schema restrictions trong Java 17+/JVM TI. Và dù redefinition thành công, old active frames vẫn tiếp tục bản cũ.

## 15. Tình huống production: mixed-version windows và hotfix có giới hạn

Một service có thể chạy request kéo dài vài giây. Tại thời điểm agent redefine một method để sửa bug:

- Request A đã enter method cũ: có thể **tiếp tục code cũ** đến khi return.
- Request B bắt đầu method sau redefine: chạy **code mới**.
- Request A có thể gọi tiếp **một method khác bằng invocation mới** và nhận version mới của method đó.
- Cả hai request có thể thấy/ghi cùng fields, database, caches, queues. **Chúng không được tự động tách state theo version**.

Do đó redefinition là **cơ chế thay code**, không phải một phương án deployment an toàn, transaction migration hay rollback strategy tự động.

Nếu nghiệp vụ đòi toàn bộ request phải nhất quán cùng một version:

1. Có thể cần **drain/quiesce** đường vào request mới và đợi in-flight tasks hoàn thành theo SLA trước khi chuyển version.
2. Hoặc thiết kế V1/V2 **backward-compatible** ở boundary và chia sẻ state, chịu được giai đoạn mixed-version frames.
3. Phân biệt rollout **code** và rollout **schema/database/config**. Thay method body không đổi trường dữ liệu hay tự chạy migrations.
4. Ghi rõ ranh giới kiểm thử: exact method đã redefine, target classloader/module, JVM version, method stack frames có thể còn active.
5. Có cách rollback/disable khác (ví dụ restart process với build đã được kiểm thử) nếu JVM không hỗ trợ hoặc bytes không hợp lệ; đừng trông chờ hot swap giải quyết mọi vấn đề.
6. Với agents thứ ba, nhớ transformer chain có thể tương tác và thay đổi final bytes; kiểm tra trên môi trường tương tự production.

### Ví dụ đổi return value nhưng không sửa lỗi đã xảy ra

Nếu method cũ đã gửi email hoặc trừ tiền trước khi dừng ở latch, thay return string thành `NEW` không undo email hoặc transaction. Một hotfix không thể biến side effects cũ thành “chưa từng xảy ra”. Bài lab cố ý chỉ trả string để không có external side effects.

### Class loader identity

Nếu ứng dụng có hai class loaders cùng định nghĩa `demo.target.VersionedTarget`, chúng là hai `Class<?>` khác nhau. `redefineClasses(new ClassDefinition(targetA,bytes))` chỉ áp dụng lên **class targetA** được cung cấp, không tự sửa targetB ở loader khác chỉ vì cùng binary name. Khi tìm target, phải log/kiểm tra đúng defining loader chứ không chọn class theo tên chuỗi một cách mù quáng.

## 16. Bài tập mở rộng sau khi lab chính chạy đúng

**Bài 1 — Thay thứ tự release:** Gọi `release.countDown()` **trước** khi redefine. Khi đó thread T1 có thể hoàn tất bằng V1 trước redefinition. Thử nghiệm này **không** còn chứng minh hành vi “active frame tại lúc redefine” vì precondition đã bị phá; cần quan sát timing và không rút ra kết luận tương tự.

**Bài 2 — Nhiều lời gọi đồng thời:** Tạo hai hoặc nhiều T1 threads, mỗi thread có entered latch và tất cả cùng đợi một release latch. Sau khi cả hai đã báo entered, redefine, gọi một invocation mới, rồi release. Kỳ vọng các old active frames tiếp tục V1. Cần dùng `CountDownLatch(count=N)` và kiểm tra đúng N threads đã vào method trước khi redefine.

**Bài 3 — Thay logic trong method body:** V2 đổi `return "NEW"` thành một phép tính/nhánh khác, nhưng giữ y nguyên method descriptor và schema. So sánh active V1 và new V2 invocations.

**Bài 4 — Thử thêm field vào V2 (negative test):** Thêm `public int extra;` vào V2 rồi compile. Theo JVM TI restrictions cho Java 17+, `redefineClasses` thông thường phải từ chối việc thêm field. Không chạy trường hợp này trên service thật; nếu thử trong lab, xử lý `UnsupportedOperationException`/lỗi tương ứng theo JVM. **Không** coi một lần reject là bằng chứng capability luôn không hỗ trợ: lỗi có thể do schema.

**Bài 5 — Quan sát initializer:** Thay `marker = 99` ở V2 thành 1000, compile lại rồi chạy. `markerAfter` vẫn phải phản ánh giá trị 41 đã được khởi tạo từ V1 trong chương trình lab.

**Bài 6 — Dùng `-Xint`:** Chạy cùng test với interpreter và so stdout. Nếu một giả thuyết chỉ đúng trong JIT mode mà không đúng trong interpreter, cần kiểm tra race/optimization/testing assumption trước khi kết luận về JVM spec.

**Bài 7 — Đổi sang `retransformClasses`:** Viết một `ClassFileTransformer` có `canRetransform=true` thay body method khi retransform, bật đúng manifest capability và phân biệt “đọc bytes replacement” với “transform pipeline”. So sánh semantics old/new frames với lab. Đây là bài riêng; không đổi ngầm `redefineClasses` sang retransform trong lab gốc.

## 17. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Sửa thế nào |
|---|---|---|
| “Sau `redefineDone`, mọi frame phải chạy V2 ngay” | Active frames tiếp tục original method bytecodes | Phân biệt frame active vs new invoke |
| “JVM phải chờ old calls kết thúc mới redefine trả về” | API có thể cài method mới khi old frames còn active | Dùng latch để chứng minh, không dựa vào timing |
| “`Thread.sleep` đủ đồng bộ thread” | Scheduler không bảo đảm entry method trước redefine | Dùng `CountDownLatch` handshake |
| “Sau redefine, `marker=99` vì code V2 khởi tạo vậy” | Class initializer không chạy lại | Kiểm tra static field persisted |
| “V2 phải có tên class khác” | `ClassDefinition` yêu cầu replacement cho **cùng target** | Giữ binary name, schema, chỉ body khác |
| “Để V2 ở runtime classpath là điều kiện bắt buộc” | Agent đọc bytes V2, không cần loader định nghĩa V2 | Chỉ `out/v1` ở runtime classpath |
| “Để cả V1/V2 vào classpath không sao” | Có thể nạp V2 ngay từ đầu, hỏng precondition | Tách output paths rõ ràng |
| “`isModifiableClass == true` cho phép thêm method” | Modifiability khác schema restrictions | Giữ field/method schema |
| “`Can-Retransform-Classes` thay cho `Can-Redefine-Classes`” | Hai capabilities khác nhau | Dùng đúng manifest và API |
| “Nếu lời gọi cũ thấy giá trị field mới thì nó đang dùng V2 bytecode” | Bytecode cũ vẫn có thể đọc shared mutable fields | Tách code version và data state |
| “Redefine tự rollback side effects request cũ” | Không undo DB/IO/heap mutations | Thiết kế migration/rollback riêng |
| “Không cần quan sát error vì redefine chỉ thay string” | Có thể path sai, class name sai, bytes hỏng, unsupported JVM | Preflight, catch/report lỗi, read output |
| “Debugger PopFrame là hành vi mặc định” | PopFrame là thao tác debugger/JVMTI khác | Không kết hợp khi test redefinition |
| “Một agent thay cùng FQCN ở mọi plugin loaders” | Class identity gồm defining loader | Target đúng `Class<?>` ở từng loader |
| “Một callback transformer chứng minh method được gọi” | Transformer callback ở classfile event | Dùng execution output/latch và body method |

## 18. Câu hỏi tự kiểm tra

1. **Nếu frame V1 đang chờ latch và agent redefine sang V2, frame V1 trả gì khi được release?** Theo lab: `OLD`, vì nó tiếp tục original bytecodes.
2. **Invocation bắt đầu sau khi redefine thành công trả gì?** `NEW` nếu nó gọi đúng method của class đã redefine và không bị transformer khác thay.
3. **Tại sao phải dùng `entered` latch?** Xác nhận thread đã vào old method trước khi cài V2.
4. **Tại sao cần `release` latch?** Giữ frame V1 active trong suốt lúc redefinition.
5. **Có thể thay CountDownLatch bằng `Thread.sleep(50)` để đảm bảo đúng?** Không; sleep không chứng minh frame active.
6. **`redefineClasses` nhận Java source hay class file bytes?** Toàn bộ class-file bytes, kèm target `Class<?>` qua `ClassDefinition`.
7. **Vì sao V2 không xuất hiện ở runtime classpath?** Agent đọc V2 bytes từ file, không load V2 thành class riêng.
8. **Manifest nào cần cho API?** `Premain-Class` và `Can-Redefine-Classes: true` cho startup agent.
9. **`isRedefineClassesSupported == true` có cho phép thêm field vào V2?** Không; schema restrictions vẫn áp dụng.
10. **`markerAfter=41` có bất thường khi V2 khai `marker=99`?** Không; static initializer không chạy lại.
11. **Một frame cũ có thể gọi một method mới khác sau redefine không?** Có; invocation mới sử dụng method version mới theo đặc tả.
12. **Old frame có làm heap biến về trạng thái V1 không?** Không; heap/static state được chia sẻ theo luật bình thường.
13. **JIT có được phép phá quy tắc old frames chạy old code không?** Không; JVM phải giữ observable semantics, dù deopt/recompile nội bộ.
14. **Nếu đổi tên class trong V2 thì sao?** `redefineClasses` phải từ chối class file không khớp target, có thể `NoClassDefFoundError`.
15. **Nếu `redefineClasses` ném exception cho batch nhiều classes thì có một số classes được cài không?** Theo Javadoc: không class nào trong batch được redefine.
16. **Có thể dùng debugger `PopFrame` để ép chạy lại code?** Đây là tính năng khác có điều kiện; không phải hành vi mặc định của Instrumentation.
17. **Làm sao test với nhiều threads cũ?** Đồng bộ xác nhận tất cả đã vào V1 rồi mới redefine.
18. **Có nên dùng hot redefinition thay thế rollout/restart production không?** Không mặc định; phải xét mixed-version execution, state, side effects và rollback.

## 19. Checklist trước khi gọi `redefineClasses` trong thực tế

- [ ] Bài toán thực sự cần cài code mới vào class đã load, không chỉ quan sát hoặc log.
- [ ] Target `Class<?>` thuộc đúng defining loader/module; không chỉ trùng binary name.
- [ ] Agent có manifest `Can-Redefine-Classes: true` và `isRedefineClassesSupported() == true`.
- [ ] `isModifiableClass(target)` trả `true`; vẫn kiểm tra classfile/schema restrictions.
- [ ] Replacement bytes là **một class file hoàn chỉnh**, đúng target name/version, không phải source.
- [ ] V1/V2 cùng field/method signatures, modifiers, superclass/interfaces và restricted class attributes.
- [ ] Các agent/transformers khác được tính vào kiểm thử final class bytes.
- [ ] Có preconditions và synchronization xác thực những active calls cần quan sát.
- [ ] Có output/metrics phân biệt old in-flight invocation với new invocation.
- [ ] Không trông chờ static initializer hoặc constructors chạy lại hay object data reset.
- [ ] Nếu đổi nghĩa shared fields, thiết kế data migration và concurrency compatibility riêng.
- [ ] Không làm JNI/IO/DB side effects với giả định redefinition rollback chúng.
- [ ] Có đường lỗi cho `UnmodifiableClassException`, `UnsupportedOperationException`, classfile/linkage errors, thiếu file.
- [ ] Kiểm chứng trên JDK/vendor mà ứng dụng sẽ chạy; không chỉ chạy JDK compile.
- [ ] Có khả năng dừng/deploy rollback có kiểm soát và cách xử lý requests đang active.
- [ ] Không dùng debugger frame operations khi muốn đo semantics redefinition mặc định.

## 20. Tài liệu chuẩn

- [Java SE 21 — `Instrumentation.redefineClasses`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineClasses(java.lang.instrument.ClassDefinition...)): quy tắc **active stack frames chạy original bytecodes**, new invokes dùng redefined methods, static values không reset, class initializer không chạy lại, batch failure atomicity và exceptions.
- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): API/capabilities hoạt động trên Java 17+.
- [Java SE 21 — `ClassDefinition`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): class cùng replacement class-file bytes.
- [Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Premain-Class`, `Can-Redefine-Classes`, agent startup.
- [JVM TI 21 — Redefine Classes](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#RedefineClasses): obsolete method versions, old active frames, new invokes, schema restrictions.
- [JVM TI 21 — Retransform Classes](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#RetransformClasses): mechanism và active frame semantics tương ứng của retransformation.
- [Java SE 21 — `CountDownLatch`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ entry/release, memory consistency effects.
- [Java SE 21 — `Thread.join`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#join()): đợi thread hoàn tất.
- [Java SE 21 — JVMS §5.3 Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): runtime class identity và defining loader.
