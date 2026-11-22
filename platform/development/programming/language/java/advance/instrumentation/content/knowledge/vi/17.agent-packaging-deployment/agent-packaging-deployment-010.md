# Khả năng cùng tồn tại với nhiều agent, coverage tool và chế độ CDS hoặc AOT

Trong ứng dụng Java hiện đại, một JVM có thể đồng thời chạy nhiều thành phần can thiệp bytecode: agent **APM/tracing**, **profiler**, **coverage** như JaCoCo, framework mocking, agent phục vụ bảo mật, và một agent nội bộ. Cùng lúc đó, deployment có thể bật **Class Data Sharing (CDS/AppCDS)** để tăng tốc khởi động, hoặc dùng **Ahead-of-Time (AOT) cache** trên JDK mới để chuẩn bị một số công việc trước khi chạy production.

Các tính năng này **không mặc định loại trừ nhau**, nhưng **cùng tồn tại** không có nghĩa chúng chắc chắn tương thích trên mọi JVM, mọi thứ tự agent và mọi cache. Một transformer có thể thay classfile bytes trước transformer khác; coverage có thể tính class ID từ phiên bản class khác với phiên bản dùng để dựng báo cáo; hai agent có thể chèn cùng loại hook hoặc helper; retransform có quy tắc gọi lại khác load; một CDS/AOT archive có thể bị JVM bỏ qua vì cấu hình không tương thích.

Mục tiêu của bài học là xây dựng **quy trình đóng gói và kiểm thử tương thích** chứ không đưa một “cờ thần kỳ”. Ta sẽ đi từ hợp đồng `-javaagent`/`ClassFileTransformer`, cách phối hợp với **JaCoCo**, khác biệt **CDS so với AOT cache**, tới demo Java 17+ có **hai agent cùng tham gia một JVM**, thử đổi thứ tự trên command line, retransform, `-Xshare:off`/`-Xshare:auto` và kế hoạch test JDK 24+ với AOT.

## 1. “Cùng tồn tại” phải kiểm tra nhiều tầng khác nhau

Cần phân biệt ít nhất năm tầng:

| Tầng | Câu hỏi | Ví dụ sự cố |
| --- | --- | --- |
| **Khởi động** | Mọi agent được nạp và gọi `premain`/`agentmain` đúng không? | Sai `Premain-Class`, thiếu helper JAR, agent ném lỗi khiến startup abort. |
| **Pipeline bytecode** | Các transformer nhận đúng bytes và tạo kết quả hợp lệ không? | Một agent xóa attribute, agent sau ghi đè biến đổi trước, class verifier lỗi. |
| **Khả năng sửa lớp** | Các capability redefine/retransform và từng class có phù hợp không? | Agent yêu cầu retransform nhưng thiếu `Can-Retransform-Classes`, class không modifiable. |
| **Semantics của tool** | Coverage/tracing/profiling có còn thu được dữ liệu đúng không? | JaCoCo thấy class khác với bản báo cáo, mất coverage dù test có chạy. |
| **Tối ưu JVM/cache** | CDS/AOT archive có được JVM chấp nhận và có còn cải thiện startup không? | JVM fallback sang load thông thường, hoặc fail-fast khi yêu cầu cache bắt buộc. |

Đừng dùng duy nhất “application trả HTTP 200” để kết luận tất cả ổn: ứng dụng có thể chạy nhưng **coverage sai**, **spans thiếu**, **startup chậm hơn** hoặc **cache không được sử dụng**. Một checklist tốt phải xác minh **cả output của app lẫn output/health của các công cụ**.

Đường đi khái quát:

```text
java launcher / service wrapper
    |
    +-- -javaagent:coverage.jar
    +-- -javaagent:tracing.jar
    +-- -javaagent:custom.jar
    |
    v
premain cho từng agent
    |
    v
đăng ký nhiều ClassFileTransformer / helper modules
    |
    v
class load / redefine / retransform
    |
    v
các transformer chạy theo nhóm + thứ tự đăng ký
    |
    v
JVM verify/link định nghĩa class cuối cùng
    |
    +--> ứng dụng chạy nghiệp vụ
    +--> coverage/tracing/profiling phát event
    +--> CDS/AOT có thể được dùng, bỏ qua hoặc từ chối
```

**Thứ tự của các bước không phải một lời hứa mọi transformer đều hoạt động hoàn hảo.** Cần hiểu hợp đồng API rồi kiểm chứng tổ hợp agent thực tế.

## 2. Nhiều `-javaagent`: thứ tự `premain` và phạm vi quyền

Theo đặc tả `java.lang.instrument`, JVM cho phép chỉ định **nhiều** tùy chọn `-javaagent`; các phương thức `premain` được gọi **theo thứ tự agent xuất hiện trên command line**.

Ví dụ mô tả deployment (các đường dẫn phải trỏ tới JAR có thật):

```bash
java \
  -javaagent:/opt/agents/coverage.jar \
  -javaagent:/opt/agents/tracing.jar \
  -javaagent:/opt/agents/custom.jar \
  -jar service.jar
```

Nếu hệ thống dùng startup agent, JAR phải có `Premain-Class` hợp lệ. Nếu agent hỗ trợ attach động, manifest cần `Agent-Class` và class triển khai `agentmain` tương ứng. **Attach policy** và **khả năng retransform** là hai vấn đề riêng; attach thành công chưa khẳng định class có thể retransform.

Một manifest Java agent thường có:

```text
Manifest-Version: 1.0
Premain-Class: com.example.agent.AgentEntry
Can-Retransform-Classes: true
Can-Redefine-Classes: true

```

Đây chỉ là **manifest mô tả**, không phải file agent của demo. Hai capability ở đây **độc lập và tùy chọn**:

- `Can-Retransform-Classes: true`: yêu cầu được gọi `retransformClasses(...)` và đăng ký transformer `canRetransform=true`, vẫn tùy JVM hỗ trợ.
- `Can-Redefine-Classes: true`: yêu cầu `redefineClasses(...)`, vẫn tùy JVM hỗ trợ.
- Không có cờ, giá trị mặc định là `false`; **không tự bật** do agent khác đã khai báo.
- Đối tượng `Instrumentation` được JVM đưa tới entry point phải được kiểm tra bằng `isRetransformClassesSupported()` và/hoặc `isRedefineClassesSupported()`.

**Không trộn lẫn ba loại thứ tự:** thứ tự **`premain`**, thứ tự **đăng ký transformer**, và thứ tự **callback transformer**. Chúng liên quan nhưng không hoàn toàn trùng nhau.

### 2.1. Nhiều lần dùng cùng một JAR là hợp lệ

Tài liệu API cho phép nhiều `-javaagent` cùng chỉ đến một JAR. Ví dụ bài thực hành sẽ dùng:

```text
-javaagent:trace-agent.jar=A
-javaagent:trace-agent.jar=B
```

JVM gọi `premain` hai lần, mỗi lần nhận tùy chọn riêng. Mã agent đăng ký **hai đối tượng transformer khác nhau** theo hai chế độ A/B. Đây là cách cô lập quy tắc thứ tự mà không cần tải thư viện ngoài. Trong production, coverage/APM/custom agent thường dùng **các JAR riêng**, nhưng nguyên tắc đăng ký transformer vẫn áp dụng.

### 2.2. Chú ý option ghép từ môi trường

Trong ứng dụng thực tế, command-line có thể được ghép từ:

- `JAVA_TOOL_OPTIONS` / `JDK_JAVA_OPTIONS` và các biến tương tự (được JVM/launcher xử lý theo quy tắc riêng).
- Shell scripts, Docker entrypoint, Kubernetes init/container config.
- Gradle/Maven test runner, Surefire/FailSafe `argLine` hoặc IDE run configuration.
- Một APM launcher tự thêm `-javaagent`.

Vì thế **file cấu hình bạn xem chưa chắc là command line thực tế**. Cần kiểm tra các JVM flags/command line đã được truyền vào process, nhưng không log token/password hoặc dữ liệu nhạy cảm có thể nằm trong options.

## 3. Thứ tự của `ClassFileTransformer` là theo NHÓM, không chỉ `-javaagent`

Một transformer được đăng ký bằng:

```java
instrumentation.addTransformer(transformer, canRetransform);
```

Khi nhiều transformer tham gia, một transformer nhận **bytes đầu ra của transformer đứng trước**. Transformer trả `null` nếu không sửa lớp; nếu sửa, phải tạo mảng `byte[]` mới với class file hợp lệ và **không chỉnh sửa trực tiếp buffer đầu vào**.

Theo Java SE 17, thứ tự toàn bộ các transformer gồm bốn **nhóm ưu tiên**:

| Thứ tự nhóm | Transformer | Khả năng retransform |
| --- | --- | --- |
| **1** | Java transformers | `canRetransform=false` |
| **2** | Native/JVMTI transformers | Không hỗ trợ retransform |
| **3** | Java transformers | `canRetransform=true` |
| **4** | Native/JVMTI transformers | Hỗ trợ retransform |

**Trong mỗi nhóm**, transformer chạy theo **thứ tự đăng ký**. Nhưng một transformer Java ở **nhóm 1** vẫn có thể chạy **trước** transformer Java ở **nhóm 3**, **dù agent nhóm 3 đã đăng ký trước**. Đây là lý do không được khẳng định “đổi thứ tự `-javaagent` luôn đổi cùng chiều thứ tự bytes transformations”.

Sơ đồ:

```text
classfile input
    |
    v
[Java incapable transforms]   group 1, registration order
    |
    v
[Native incapable transforms] group 2
    |
    v
[Java capable transforms]     group 3, registration order
    |
    v
[Native capable transforms]   group 4
    |
    v
final transformed classfile
    |
    v
JVM verification / definition
```

Với một class được **load lần đầu**, các transformer đăng ký phù hợp có thể nhận callback. Với **redefine**, các nhóm phù hợp cũng có thể tham gia vào định nghĩa mới. Với **retransform**, quy tắc khác: các transformer đã đăng ký `canRetransform=false` **không được gọi lại**, nhưng JVM **tái áp dụng hiệu ứng lần load/redefine trước**; các transformer `true` được gọi lại.

**Không được hiểu “A không được callback lúc retransform” là “mọi biến đổi trước đây của A bị xóa”.** Nếu A thực sự đã thay bytes lúc load, hiệu ứng ấy có thể được tái áp dụng theo hợp đồng.

### 3.1. Không bắt classfile buffer phải bất biến theo cách đoán

API hướng dẫn không sửa `classfileBuffer` tại chỗ; nếu cần thay đổi, hãy parse/rewrite vào một mảng mới rồi trả về. Khi không cần đổi, trả `null`. Không dùng cách:

```java
// SAI về contract: minh họa anti-pattern, không chạy độc lập.
classfileBuffer[0] = 0;
return classfileBuffer;
```

Đây có thể phá magic bytes và còn vi phạm hợp đồng không mutate input. Hãy dùng bytecode API/thư viện xử lý constant pool, stack map frames, method bodies và attributes một cách có kiểm soát.

### 3.2. Khi transformer ném lỗi

Theo `ClassFileTransformer`, nếu `transform(...)` ném exception mà không được bắt, JVM vẫn tiếp tục gọi các transformer còn lại; tác động của transformer lỗi tương tự trả `null`. Vì thế **ném exception không phải cơ chế chặn an toàn cả chain**. Trả bytes không hợp lệ có thể khiến class verification/loading thất bại; logging chi tiết phải có guard chống đệ quy vì logger cũng có thể kích hoạt class loading.

### 3.3. Tránh transform lại hai lần một class theo cùng một logic

Nhiều agent hoặc một agent đăng ký trùng transformer có thể:

- Chèn hai đoạn code đo thời gian vào cùng method.
- Tạo hai lần metric/span cho một lần gọi nghiệp vụ.
- Chèn helper call vào method vốn đã được instrument, dẫn đến đệ quy hoặc overhead quá lớn.
- Sửa stack map frames không đúng khi rewrite lần thứ hai.
- Vi phạm hạn chế schema của retransform/redefine nếu lần đầu đã thêm field/method nhưng lần sau bytes khác.

Nên lọc theo **class loader, module, package, class name và phiên bản classfile**; thiết kế transform có khả năng nhận biết instrumentation marker, hoặc chỉ cho phép một thành phần chịu trách nhiệm cho một loại hook. Tránh chỉ dựa vào một `Set<String>` global để quyết định đã instrument: cùng class name trong **hai defining loaders** có thể là hai class khác nhau.

## 4. Một demo Java 17+ kiểm chứng thứ tự thật trong JVM

Demo chỉ dùng **Java chuẩn**, không cần ASM, Byte Buddy hay JaCoCo. Hai lần nạp cùng một JAR được đặt tên **A** và **B** qua agent options:

- A đăng ký transformer bằng `addTransformer(..., false)`.
- B đăng ký transformer bằng `addTransformer(..., true)`.
- Manifest JAR khai báo `Can-Retransform-Classes: true` để JVM thử cấp capability; trong chương trình A **cố ý** chọn `false` dù capability chung có thể hỗ trợ.
- Cả hai transformer chỉ log khi gặp `demo/app/Target` và trả `null`. Mã của Target **không bị sửa**, nên hành vi ứng dụng luôn `OK`.

Nhờ không có bytecode rewrite, demo cô lập hai câu hỏi: **thứ tự gọi callback** và **sự khác biệt callback khi retransform**.

### 4.1. Cấu trúc thư mục

```text
multi-agent-demo/
├── src/demo/
│   ├── agent/
│   │   └── TraceAgent.java
│   └── app/
│       ├── Target.java
│       └── App.java
└── agent.mf

Sau build:
├── out/
└── trace-agent.jar
```

### 4.2. `src/demo/agent/TraceAgent.java`

```java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.security.ProtectionDomain;

public final class TraceAgent {
    private static volatile Instrumentation instrumentation;

    private TraceAgent() {}

    public static void premain(String argument, Instrumentation inst) {
        if (!"A".equals(argument) && !"B".equals(argument)) {
            throw new IllegalArgumentException("Expected agent argument A or B");
        }
        String id = argument;
        boolean canRetransform = "B".equals(id);
        instrumentation = inst;
        System.out.println("[" + id + "] premain capable=" + canRetransform);
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader,
                    String className, Class<?> classBeingRedefined,
                    ProtectionDomain domain, byte[] bytes) {
                if ("demo/app/Target".equals(className)) {
                    String phase = classBeingRedefined == null
                            ? "load" : "retransform";
                    System.out.println("[" + id + "] transform phase=" + phase);
                }
                return null;
            }
        }, canRetransform);
    }

    public static void retransform(Class<?> target)
            throws UnmodifiableClassException {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Run using -javaagent");
        }
        boolean supported = inst.isRetransformClassesSupported();
        boolean modifiable = inst.isModifiableClass(target);
        System.out.println("[app] supported=" + supported
                + " modifiable=" + modifiable);
        if (supported && modifiable) {
            inst.retransformClasses(target);
            System.out.println("[app] retransform complete");
        }
    }
}
```

Giải thích:

1. JVM gọi `premain` với tham số `A` hoặc `B` tùy phần sau dấu `=` trong `-javaagent`.
2. Chỉ `B` chọn `canRetransform=true`, còn `A` chọn `false`.
3. Callback chỉ in log khi tên class ở **định dạng internal** `demo/app/Target`; tên này dùng dấu `/`, không phải dấu `.`.
4. `classBeingRedefined == null` cho biết callback do load lớp mới trong demo; khi khác null, trong demo biết đó là retransform vì chỉ gọi `retransformClasses(...)`, không gọi redefine.
5. `return null` nghĩa là không biến đổi bytes. Đây là công cụ quan sát pipeline, không phải agent coverage/tracing thực sự.
6. `retransform(...)` kiểm tra capability và modifiability, sau đó gọi API để quan sát transformer B.

Với thí nghiệm này, `instrumentation` được cập nhật khi `premain` được gọi hai lần trên cùng class agent. Điều này **chỉ phù hợp cho demo**; các agent production độc lập cần quản lý lifecycle, helper class loader, thông số và dữ liệu riêng, không dùng một static field không xác định để phối hợp nhiều agent của các nhà cung cấp.

### 4.3. `src/demo/app/Target.java`

```java
package demo.app;

public final class Target {
    private Target() {}

    public static String message() {
        return "OK";
    }
}
```

Target không biết gì về Instrumentation. Đây là class được quan sát lúc định nghĩa lần đầu và lúc retransform.

### 4.4. `src/demo/app/App.java`

```java
package demo.app;

import demo.agent.TraceAgent;

public final class App {
    private App() {}

    public static void main(String[] args) throws Exception {
        System.out.println("[app] first=" + Target.message());
        TraceAgent.retransform(Target.class);
        System.out.println("[app] second=" + Target.message());
    }
}
```

Vì app gọi `TraceAgent.retransform(...)`, **thí nghiệm này yêu cầu JVM chạy với `-javaagent`** và class agent có thể nạp từ JAR của startup agent. Với ứng dụng production, không nên buộc business code phụ thuộc vào tên class của tool; agent có thể tự quản lý yêu cầu retransform.

### 4.5. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.TraceAgent
Can-Retransform-Classes: true

```

Chỉ cần manifest này cho demo, không cần khai báo `Can-Redefine-Classes`. **Đối số `canRetransform=false/true` của từng lần `addTransformer` khác với capability manifest** của agent: manifest cho phép JVM cung cấp khả năng, còn transformer chủ động chọn loại đăng ký.

Giữ ký tự xuống dòng cuối file manifest. JAR phải chứa `TraceAgent.class` **và** class ẩn danh `TraceAgent$1.class` sinh ra từ callback.

### 4.6. Biên dịch và đóng gói

Từ thư mục `multi-agent-demo/`:

```bash
mkdir -p out

javac --release 17 -d out \
  src/demo/agent/TraceAgent.java \
  src/demo/app/Target.java \
  src/demo/app/App.java

jar --create --file trace-agent.jar --manifest agent.mf \
  -C out demo/agent
```

Trong Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out src/demo/agent/TraceAgent.java src/demo/app/Target.java src/demo/app/App.java
jar --create --file trace-agent.jar --manifest agent.mf -C out demo/agent
```

`-C out demo/agent` đưa **toàn bộ package agent** vào JAR, gồm class ẩn danh. Application `Target.class`/`App.class` vẫn nằm trong `out` và được tải bằng `-cp out`. Không đặt nhầm một bản `TraceAgent.class` khác trên classpath/runtime.

Lệnh `javac --release 17` và `jar` đã được kiểm tra thành công trên Zulu OpenJDK 24.0.2; mã chỉ sử dụng Java 17 API. Trên JVM thực thi Java 17 phù hợp, khả năng retransform vẫn là optional capability; nếu không có thì chương trình đã kiểm tra và bỏ qua thao tác.

## 5. Kết quả chạy: đổi thứ tự agent nhưng nhóm transformer không đổi

### 5.1. Lệnh A rồi B

```bash
java -javaagent:trace-agent.jar=A \
     -javaagent:trace-agent.jar=B \
     -cp out demo.app.App
```

PowerShell tương đương trên một dòng:

```powershell
java -javaagent:trace-agent.jar=A -javaagent:trace-agent.jar=B -cp out demo.app.App
```

**Stdout kiểm chứng trên OpenJDK 24.0.2:**

```text
[A] premain capable=false
[B] premain capable=true
[A] transform phase=load
[B] transform phase=load
[app] first=OK
[app] supported=true modifiable=true
[B] transform phase=retransform
[app] retransform complete
[app] second=OK
```

Diễn giải:

- `premain(A)` chạy trước `premain(B)`.
- Khi JVM định nghĩa Target, transformer **A (incapable)** nhận callback trước **B (capable)**.
- Khi App gọi `retransformClasses(Target.class)`, chỉ B được callback lại.
- B trả `null`, không sửa bytes; method vẫn trả `OK`.

### 5.2. Đổi thành B rồi A

```bash
java -javaagent:trace-agent.jar=B \
     -javaagent:trace-agent.jar=A \
     -cp out demo.app.App
```

Stdout đã kiểm chứng:

```text
[B] premain capable=true
[A] premain capable=false
[A] transform phase=load
[B] transform phase=load
[app] first=OK
[app] supported=true modifiable=true
[B] transform phase=retransform
[app] retransform complete
[app] second=OK
```

**Kết luận từ hai lần chạy:**

1. **Thứ tự `premain` đổi** đúng theo command line: A→B hoặc B→A.
2. **Thứ tự callback của hai Java transformers vẫn là A→B**, vì JVM xếp group `canRetransform=false` trước group `true`, không phụ thuộc thứ tự `premain` ở **hai nhóm khác nhau**.
3. **Chỉ B nhận callback retransform**. A thuộc nhóm incapable, và trong ví dụ này A đã trả `null` ở load ban đầu nên không có hiệu ứng bytes nào để tái áp dụng.
4. `Target.message()` vẫn là `OK`: demo chỉ kiểm tra orchestration, **không kiểm tra khả năng compose của hai bytecode transformations thực sự**.

Vì vậy câu “JaCoCo nên đứng đầu danh sách `-javaagent`” chỉ có thể hiểu theo **quy tắc và hoàn cảnh cụ thể**, không phải bảo đảm JaCoCo luôn nhận bản bytecode gốc trước mọi native/capable transformer. Khi có agent phức tạp, phải biết nó đăng ký transformer thuộc nhóm nào và kiểm tra bytes thực tế.

### 5.3. Nếu cả hai transformer cùng nhóm?

Nếu A và B cùng dùng `addTransformer(transformer, false)` hoặc cùng đăng ký `true` (với capability được cấp), các Java transformers trong **cùng nhóm** được gọi theo **thứ tự đăng ký**. Nếu mỗi agent đăng ký ngay trong `premain`, thứ tự đó thường khớp thứ tự agent trên command line.

Nhưng một agent có thể đăng ký transformer muộn hơn ở thread khác, hoặc đăng ký thêm nhiều transformer sau startup. Vì vậy phải ghi log **thời điểm đăng ký/nhóm**, không chỉ tên agent.

### 5.4. Không suy ra “retransform lần hai sẽ khởi động lại mọi agent”

`retransformClasses(...)` không chạy lại `premain`, không gọi lại các transformer `false` và không khởi tạo lại static state theo cách reset. Nó yêu cầu JVM áp dụng lại chuỗi bytecode theo quy tắc retransform. Nếu nhiều agent đã chèn mã thì có thể cần xử lý schema/frames/tương tác từ những transform đã có; không thể chỉ “bật retransform” để mọi tool tự chạy từ đầu.

## 6. Cùng tồn tại với JaCoCo và coverage tools

**JaCoCo** sử dụng Java agent để chèn **coverage probes** vào classfile khi load; khi test thực thi, các probes ghi nhận execution data, thường được xuất ra file `jacoco.exec` hoặc qua phương thức cấu hình khác. Vì JaCoCo không chỉ nhìn tên class mà còn gắn execution data với **class ID**, những thay đổi bytecode ở nơi khác có thể khiến báo cáo sai.

### 6.1. Vấn đề class ID mismatch

Theo tài liệu JaCoCo, class ID hiện được tính từ **raw class-file bytes** bằng CRC64. Nếu JaCoCo thấy một version bytes tại runtime nhưng report generator phân tích version bytes khác, dữ liệu có thể **không match** và class hiển thị như không được cover dù test đã chạy.

Ví dụ:

```text
app.jar trên disk:            OrderService.class V1
agent custom transformer:     tạo OrderService.class V2
JaCoCo transformer:           tính coverage class ID từ V2
report generator:             phân tích file V1
                               |
                               v
                     class ID mismatch, missing/0% coverage
```

Những nguyên nhân thực tế:

- Another Java agent sửa class **trước JaCoCo** trong transformer chain.
- Class loader/framework tạo/patch bytes động: mocking, persistence weaving, app server.
- File dùng để tạo report khác compiler/compiler settings với file runtime.
- Obfuscation, shading, AspectJ hoặc post-processing thay bytes giữa runtime và report.
- Chạy nhiều phiên bản cùng binary name nhưng đưa nhầm version vào cùng report group.

Không nên kết luận “coverage report 0% = test chưa chạy” trước khi đối chiếu **JaCoCo Sessions page và class IDs**.

### 6.2. Các biện pháp JaCoCo công bố

Tài liệu JaCoCo khuyến nghị:

1. **Đặt JaCoCo trước agent sửa class khác trên command line** để JaCoCo có cơ hội thấy **original bytes** (trong những cấu hình pipeline phù hợp).
2. Dùng `classdumpdir` của JaCoCo để lưu những class bytes mà agent thấy, rồi dùng đúng dữ liệu đó khi tạo report nếu class runtime đã bị sửa; lưu ý chỉ có các class thực sự được load mới được dump.
3. Cân nhắc **offline instrumentation** nếu runtime transformation xung đột; report phải phân tích **original class files**, còn runtime cần JaCoCo runtime/agent tương ứng trên classpath.

Ví dụ **minh họa**, yêu cầu có JAR thật:

```bash
java \
  -javaagent:jacocoagent.jar=destfile=build/jacoco.exec,classdumpdir=build/jacoco-dump \
  -javaagent:custom-agent.jar \
  -jar application.jar
```

Đây không phải lệnh có thể chạy trong demo vì bài không kèm `jacocoagent.jar` hay `custom-agent.jar`. Khi dùng thực tế cần phiên bản JaCoCo **hỗ trợ class-file version** của JDK mục tiêu và đường dẫn output writable.

**Cảnh báo về thứ tự nhóm:** đặt JaCoCo đầu command line là khuyến nghị cụ thể của JaCoCo, **không thay thế** hiểu biết về bốn nhóm transformers. Với các agent đăng ký native hooks hoặc `canRetransform` khác nhau, vẫn phải kiểm tra JaCoCo thực sự thấy bytes nào.

### 6.3. Không instrument cùng class hai lần mà không kiểm soát

Khi dùng coverage tool cùng custom instrumentation:

- Không để custom agent vô tình chèn lại JaCoCo probes hoặc xóa field/method/attribute do JaCoCo tạo ra.
- Không bật JaCoCo **online và offline** cùng một lúc cho **cùng class** trừ khi tài liệu/version cụ thể yêu cầu một cấu hình khác; thông thường double-instrument gây lỗi.
- Nếu custom transformer dùng thư viện rewrite classfile, nó phải giữ những thành phần do tool trước đã thêm mà JVM yêu cầu.
- Không sửa class từ một bản bytes cũ trên disk rồi trả nó ra transformer sau: làm vậy **đè mất** các modifications ở input do agent trước tạo.
- Khi dùng `retransformClasses`, phải tuân hạn chế schema và quy tắc tái áp dụng effect của transformer incapable.
- Cẩn trọng với classes generated/lambda/proxy và classloader khác nhau; đừng chỉ lọc bằng tên class đơn giản.

### 6.4. Metadata và kiểm tra báo cáo

Coverage phụ thuộc debug info như `LineNumberTable` để tính line coverage chính xác. Bytecode rewrite làm mất line numbers hoặc source metadata có thể khiến report thiếu/khó đối chiếu. JaCoCo còn yêu cầu classfiles hợp lệ (đặc biệt stack map frames trên class version mới).

Checklist cho coverage:

```text
[ ] JaCoCo version tương thích JVM/classfile version
[ ] Build report sử dụng đúng original/runtime input classfile theo mode
[ ] Không double-instrument online + offline
[ ] Không bỏ LineNumberTable và class metadata cần thiết
[ ] JaCoCo Sessions page có class ID match?
[ ] File jacoco.exec có dữ liệu mới, đúng session và đúng path?
[ ] Includes/excludes và class loader selection phù hợp?
[ ] Đã thử cả thứ tự JaCoCo trước/sau tool khác?
[ ] Không có custom agent/bytecode rewrite làm mất probes?
```

**Phân biệt hai bộ lọc:** `includes/excludes` của JaCoCo agent điều khiển việc **thu thập execution data**, còn việc class nào được hiển thị trong coverage report còn phụ thuộc input classfiles/report configuration. Không đồng nhất hai khâu.

## 7. Tracing/APM, Mockito/Byte Buddy và profiler

JaCoCo là ví dụ dễ nhìn vì có class IDs, nhưng nhiều công cụ khác cũng thay bytecode hoặc làm việc ở tầng JVMTI.

| Công cụ | Điểm thường cần kiểm tra |
| --- | --- |
| **Tracing/APM agent** | Chèn hook cùng method với custom agent; nguy cơ double spans, latency hoặc context propagation sai. |
| **Byte Buddy instrumentation** | Có thể làm load-time weaving và retransformation, cần xem transformer group và cách tự phát hiện đã transform. |
| **Mockito inline/mock frameworks** | Có thể redefine/retransform class phục vụ mocking; tương tác với coverage/class IDs và những class không modifiable. |
| **Profiler native/JVMTI** | Có native class-file hooks, thuộc nhóm callback khác Java transformers; không dựa chỉ vào `-javaagent` order. |
| **Security/audit agent** | Có thể yêu cầu đầy đủ sự kiện, không được drop như telemetry best-effort; cần kiểm soát overhead và xung đột hook. |
| **Custom internal agent** | Nên có package/classloader filters, idempotence, module helper access và mode tắt từng biến đổi. |

Với **Byte Buddy AgentBuilder**, đừng mặc định một số API/cờ cụ thể luôn được bật cho mọi version; xác minh cấu hình retransformation, method matcher, classloader matcher, listener errors và SDK/library version thực tế. Với Mockito inline, không xem khả năng mocking là một tính chất cố định của mọi JVM/container; attach policy và agent configuration có thể khác nhau.

Một thử nghiệm tương thích nên có **ít nhất một method bị hai tool quan tâm đồng thời**. Nếu chỉ test một class mà agent A theo dõi, còn tool B không chạm tới, sẽ không phát hiện phần lớn xung đột bytecode.

## 8. Đóng gói agent cho deployment nhiều công cụ

Khả năng cùng tồn tại bắt đầu từ **JAR và classloader**, không chỉ từ transformer.

### 8.1. Manifest và helper dependencies

Kiểm tra JAR agent thực tế có các trường đúng cơ chế:

```text
Manifest-Version: 1.0
Premain-Class: com.example.agent.StartupAgent
Agent-Class: com.example.agent.DynamicAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true

```

Đây là cấu hình minh họa **nếu agent thực sự có cả hai entry points/capabilities**; đừng copy nguyên rồi dùng class không tồn tại.

- `Premain-Class` dùng với startup `-javaagent`, `Agent-Class` dùng với attach nếu hỗ trợ.
- Tất cả dependencies của agent phải nạp được ở thời điểm cần; class loading vòng lặp trong transformer có thể dẫn đến `LinkageError`.
- Khi shade/relocate ASM/Byte Buddy dependencies, tránh va chạm thư viện và tránh đổi package API dùng chung của ứng dụng một cách tùy tiện.
- Kiểm tra `META-INF/MANIFEST.MF` **trong JAR được deploy**, không chỉ file manifest nguồn hoặc tên artifact.
- Đừng lẫn **agent JAR** với **application JAR**: app có thể được chạy bằng `-jar`, còn agent được chỉ định riêng với `-javaagent:...`.

### 8.2. Tên package và tránh phụ thuộc chéo

Hai agent dùng chung package/helper tên giống nhau nhưng phiên bản khác có thể nạp nhầm class, dẫn tới `NoSuchMethodError`, `ClassCastException` hoặc dữ liệu bị trộn. Relocation có thể hữu ích cho dependency nội bộ, nhưng phải thử trong classloaders và module system thực tế.

Nếu agent chèn lời gọi tới helper, class đã instrument phải có thể resolve helper từ loader/module của nó. Trên Java 9+, cần xét **named/unnamed module readability** và exports/opens thích hợp. `Instrumentation.redefineModule(...)` có thể thêm module reads/exports/opens, nhưng **không tự thêm JAR vào đường tìm kiếm của class loader**.

### 8.3. Giới hạn scope instrument

Agent nên có cơ chế **include/exclude** theo class name, classloader, module và code source. Exclude agent code, exporter/logger, bytecode library và những class cốt lõi không chủ định can thiệp.

Instrumentation đệ quy vào chính logger/exporter có thể gây:

- Event mới tạo event khác, logging storm hoặc StackOverflowError.
- Gọi helper khi class chưa sẵn sàng, gây class loading circularity.
- Khóa/IO chậm ngay trong transform callback.
- Conflicts với Java agent khác vốn cũng instrument logger hoặc networking classes.

Không biến exclusions thành danh sách cứng thiếu kiểm thử. Khi loại trừ một class, phải kiểm tra xem business telemetry/coverage cần nó hay không.

## 9. CDS và AppCDS: tối ưu startup không phải tính năng agent

**Class Data Sharing (CDS)** dùng các archive chứa dữ liệu class đã được xử lý trước, giúp một số lớp được load nhanh hơn và có thể chia sẻ metadata giữa JVM processes. **AppCDS** mở rộng tới những lớp ứng dụng phù hợp. Đây là **cơ chế tối ưu load/startup/footprint**, không phải Java agent và cũng không tương đương retransform/redefine.

Những cờ launcher thường dùng trên HotSpot/JDK tương ứng:

| Cờ | Mục đích |
| --- | --- |
| `-Xshare:off` | Tắt CDS để có baseline chẩn đoán. |
| `-Xshare:auto` | Cho JVM dùng archive nếu phù hợp; có thể fallback nếu không thể sử dụng. |
| `-Xshare:on` | Chế độ thử nghiệm yêu cầu sharing; có thể thoát khi archive không dùng được, **không nên dùng mặc định production**. |
| `-Xlog:cds=info` | Log hoạt động/quyết định về archive trên HotSpot, dùng để xác minh sharing thực sự. |
| `-XX:SharedArchiveFile=...` | Chỉ định archive thích hợp theo JDK/OS/format. |

### 9.1. Đừng tưởng app chạy nghĩa là CDS đã được dùng

Trên nhiều JVM, chế độ `auto` có thể chạy ứng dụng bình thường **dù cache/archive không được sử dụng**. Muốn xác minh, phải xem **log JVM và hiệu quả startup/memory**. Chạy thử cả `-Xshare:off` và `-Xshare:auto` giúp tách lỗi **bytecode/tool** khỏi vấn đề **CDS archive**.

Trong môi trường có nhiều agent, đặc biệt khi class được instrument ngay từ load, những class bị biến đổi hoặc điều kiện archive có thể khiến một số lợi ích CDS không đạt như baseline. Mức độ phụ thuộc JDK version, archive content, classloader, module path và loại transformation; **không được khẳng định “bật agent là CDS luôn bị tắt”** hoặc “CDS luôn dùng được với mọi agent”.

### 9.2. Kiểm thử demo với `-Xshare:off` và `-Xshare:auto`

```bash
java -Xshare:off \
  -javaagent:trace-agent.jar=A -javaagent:trace-agent.jar=B \
  -cp out demo.app.App

java -Xshare:auto \
  -javaagent:trace-agent.jar=A -javaagent:trace-agent.jar=B \
  -cp out demo.app.App
```

Hai lượt chạy trên Zulu/OpenJDK 24.0.2 **đều in cùng stdout ứng dụng/agent** như trường hợp A rồi B:

```text
[A] premain capable=false
[B] premain capable=true
[A] transform phase=load
[B] transform phase=load
[app] first=OK
[app] supported=true modifiable=true
[B] transform phase=retransform
[app] retransform complete
[app] second=OK
```

**Diễn giải đúng:** cùng behavior trong hai chế độ là dấu hiệu chức năng agent và app không bị hỏng khi đổi CDS mode **trong JVM thử nghiệm**. Nó **không chứng minh** ở lượt `-Xshare:auto` archive thực sự được sử dụng. Để xác nhận CDS hit/fallback, thêm log VM:

```bash
java -Xshare:auto -Xlog:cds=info \
  -javaagent:trace-agent.jar=A -javaagent:trace-agent.jar=B \
  -cp out demo.app.App
```

Các thông điệp logging cụ thể thay đổi theo JDK/cấu hình, vì vậy không đưa stdout “chuẩn” cố định cho chế độ verbose.

### 9.3. CDS archive có điều kiện hiệu lực

Archive thường gắn với phiên bản JDK, đường dẫn/classpath/module path và cấu hình được tạo. Thay app JAR, thay helper/agent JAR, thay flags, dùng module options không tương thích hoặc chuyển JDK có thể làm archive không còn hợp lệ hoặc không còn lợi ích kỳ vọng.

Thử nghiệm deployment cần ghi lại **cách tạo archive** và **cách JVM quyết định dùng archive lúc chạy**. Không đưa archive tạo trên một JVM/version khác vào production rồi tự coi là tương thích.

## 10. AOT cache JDK 24+ khác CDS và khác native image

Từ **JDK 24**, OpenJDK có **Ahead-of-Time Class Loading & Linking** theo JEP 483: một AOT cache chuẩn bị một số tối ưu dựa trên quá trình **training/recording**, sau đó **assembly/create** và **production/on/auto**. CDS là một thành phần/tư tưởng liên quan tới tối ưu trước khi chạy, nhưng AOT cache có thể chứa nhiều dữ liệu tối ưu hơn tùy JDK release.

**Không đánh đồng ba điều:**

1. **CDS/AppCDS**: archive class metadata/related data phục vụ load nhanh/chia sẻ.
2. **JDK 24+ AOT cache (Project Leyden)**: quy trình training → tạo cache → dùng cache để cải thiện startup/warm-up, phụ thuộc version và flags.
3. **GraalVM Native Image** hoặc một **AOT-compiled native executable**: mô hình closed-world/binary khác, không mặc nhiên hỗ trợ `-javaagent` và các API thay class runtime như một HotSpot JVM. Phải xem tài liệu của chính runtime/build tool đó.

### 10.1. Cơ chế AOT cache theo Java launcher

Trong JDK 24+ có các tùy chọn dạng:

| Tùy chọn | Pha |
| --- | --- |
| `-XX:AOTMode=record` + `-XX:AOTConfiguration=app.aotconfig` | Training: chạy app, ghi cấu hình AOT. |
| `-XX:AOTMode=create` + `-XX:AOTConfiguration=app.aotconfig` + `-XX:AOTCache=app.aot` | Assembly: xây cache, **không chạy logic ứng dụng thông thường**. |
| `-XX:AOTCache=app.aot` hoặc `-XX:AOTMode=auto` | Production: cố dùng cache, có thể fallback nếu cache không tương thích. |
| `-XX:AOTMode=on` + `-XX:AOTCache=app.aot` | Diagnostic fail-fast: nếu không thể dùng cache thì VM **có thể dừng trước `main`**. |

Tùy JDK release, danh sách cờ, mặc định và thứ được lưu trong cache có thể tiến triển. Khi sử dụng phải dựa vào **hướng dẫn đúng version JDK của deployment**. Để so sánh công bằng, training/create/run phải dùng cùng JDK release, OS/CPU architecture, cấu hình application/classpath và môi trường đại diện; khi build thay đổi, **tạo lại cache**.

**Đặc biệt với nhiều agent:** agent và transformer có thể thay class loading, thứ tự bytes, module opens/reads, classpath search hoặc bật JVMTI capabilities. Một số tổ hợp có thể không tương thích với AOT cache, nhất là các tùy chọn hỗ trợ diagnostic sửa class tuỳ ý. Vì thế **AOT cache tồn tại trên đĩa không chứng minh JVM đã map/dùng nó**.

### 10.2. Kiểm chứng từ một thử nghiệm trên OpenJDK 24.0.2

Thử nghiệm phụ với chính agent demo đã chạy trên **Zulu/OpenJDK 24.0.2**:

- `AOTMode=record` với hai startup agent **chạy app thành công** và tạo file cấu hình.
- `AOTMode=create` tạo file cache; khi classpath chỉ dùng thư mục `out`, VM cảnh báo một số class không archive được vì **Unsupported location**. Khi dùng application JAR nhưng không cung cấp helper/agent classes trong classpath của pha assembly, VM còn cảnh báo **ClassNotFoundException** cho các class agent đã thấy lúc training.
- Khi dùng cache ấy với **hai startup agent**, `AOTMode=auto` **tiếp tục chạy ứng dụng** sau khi VM báo không thể dùng archived AOT-linked classes vì full module graph không phù hợp.
- Với **cùng cache/cùng startup agent** và `AOTMode=on`, VM in lỗi archive và **dừng khởi động** trong thử nghiệm.

Thông báo chẩn đoán tiêu biểu khi cache và runtime không nhất quán:

```text
CDS archive has aot-linked classes. It cannot be used when archived full module graph is not used.
```

**Kết luận:** đây là **một kết quả cụ thể**, không phải quy tắc bắt buộc rằng mọi Java agent làm mọi AOT cache thất bại. Và **auto chạy app thành công là fallback**, chưa phải bằng chứng AOT optimization có hiệu lực. Cần dùng `-Xlog:cds` hoặc logging AOT tương ứng JDK để xác nhận.

### 10.3. Hướng dẫn vận hành AOT + agent

Đối với production có AOT cache:

1. Trước hết xác minh app và tất cả agents chạy đúng **không cần cache**.
2. Giữ **cùng phiên bản/binary/order/config** của agents giữa training và production khi cần sự nhất quán; kiểm soát mọi thao tác sửa class động.
3. Ưu tiên **JAR classpath ổn định** thay vì thư mục build tạm và đường dẫn không tái lập, theo khuyến nghị JDK tương ứng.
4. Tạo cache trong môi trường đáp ứng yêu cầu JDK release, OS/CPU, application bytecode và classpath/module path.
5. Thử `AOTMode=auto` với logging để xác nhận **cache thật sự được load**, không chỉ quan sát ứng dụng vẫn chạy.
6. Thử `AOTMode=on` **chỉ trong staging/diagnostics** để phát hiện cấu hình không tương thích; cân nhắc fail-fast nếu chính sách deployment đòi cache.
7. Khi đổi JDK, agent binary, classpath, module options hoặc patch application, tái tạo cache và chạy lại ma trận kiểm thử.
8. Nếu cache không dùng được, đo startup/footprint của fallback thay vì nói “AOT đã tối ưu hiệu năng”.

Ví dụ **chỉ minh họa cờ** (cần cache `app.aot` **được tạo hợp lệ cho ứng dụng/VM này**, không tự chạy được với demo khi thiếu cache):

```bash
# JDK 24+, ưu tiên chạy được ngay cả khi cache không phù hợp:
java -XX:AOTMode=auto -XX:AOTCache=app.aot \
  -javaagent:coverage.jar -javaagent:custom.jar -jar service.jar

# Staging / chẩn đoán: bắt buộc cache phải dùng được:
java -XX:AOTMode=on -XX:AOTCache=app.aot \
  -javaagent:coverage.jar -javaagent:custom.jar -jar service.jar
```

Để dùng cho một dự án cụ thể, thay đúng đường dẫn JAR, manifest, dependency và quy trình record/create. **Không dùng lệnh fail-fast AOTMode=on ở production khi chưa chứng minh đầy đủ tính tương thích.**

## 11. Ma trận kiểm thử tương thích cho deployment

Bắt đầu từ **hai chiều độc lập**: số lượng/nhóm agent và chế độ CDS/AOT. Một ma trận tối thiểu:

| Test | Agent configuration | JVM/archive mode | Điều cần kiểm chứng |
| --- | --- | --- | --- |
| **T0** | Không agent | `-Xshare:off` | Baseline chức năng/startup/latency. |
| **T1** | Custom agent | `-Xshare:off` | Class transformation, helpers, app behavior. |
| **T2** | Coverage agent | `-Xshare:off` | Execution data, report class ID, line/branch coverage. |
| **T3** | Coverage + custom | `-Xshare:off` | Hai transformer cùng chạm method; không lỗi/coverage loss. |
| **T4** | Custom + coverage | `-Xshare:off` | Thay thứ tự; giải thích khác biệt theo nhóm callback. |
| **T5** | Coverage + custom + APM/profiler | `-Xshare:auto` | Phân tích p99, drop/duplicate spans, classload errors. |
| **T6** | Cùng bộ agents production | `-Xshare:off` và `auto` | CDS behavior và JVM logs, startup delta. |
| **T7** | Cùng bộ agents production | AOT cache auto (JDK phù hợp) | App chạy, cache có được load, fallback có bị che giấu. |
| **T8** | Cùng bộ agents production | AOT cache on (staging) | Fail-fast nếu cache incompatible, log đủ để debug. |
| **T9** | Cùng bộ agents | Cache/agent JAR đã thay đổi | Tạo lại archive, xác minh reproducibility. |

Tùy dự án, bổ sung:

- JDK baseline LTS và JDK deployment thực tế; nhiều vendor/OS/architecture nếu môi trường yêu cầu.
- Class load qua system/platform/bootstrap và các custom class loaders.
- Named modules, sealed packages, dynamic proxies, lambdas, hidden classes.
- Frameworks dùng bytecode weaving, hot reload hoặc mocking inline.
- Test retransform/redefine khi các class đã được load và app đang có active frames.
- Startup under stress, GC/heap pressure, concurrent class load và shutdown.
- Compatibility với security posture, attach policy và giới hạn container.

**Mục tiêu không phải chạy hết tổ hợp vô hạn**, mà là chọn những tổ hợp có thay đổi behavior/capability/archive đáng kể, đặc biệt lớp mà **hai công cụ cùng muốn instrument**.

### 11.1. Trường hợp đổi thứ tự agents trong Maven/Gradle

Nếu test runner ghép thêm JaCoCo `argLine`, đừng vô tình ghi đè nó khi thêm custom agent. Một ví dụ **mang tính cấu hình**:

```text
jvmArgs = [JaCoCo argument generated by build tool]
        + [custom -javaagent argument]
        + [other necessary JVM options]
```

Dạng cụ thể phụ thuộc plugin build/version; không copy nguyên pseudocode trên thành cấu hình Maven hay Gradle. Việc xác minh quan trọng là **command line cuối cùng của forked test JVM** có JaCoCo và custom agent đúng thứ tự, không phải chỉ nhìn khai báo trong build script.

### 11.2. Test fixtures cần phản ánh tương tác thật

Một test chỉ in `premain` chưa phát hiện classfile conflict. Nên có một **fixture class** được JaCoCo và agent custom cùng biến đổi, gọi method đủ nhánh để tạo coverage data, rồi:

1. Kiểm tra không có `VerifyError`/`ClassFormatError`/`LinkageError`.
2. Kiểm tra behavior phương thức giữ nguyên, kể cả exception path.
3. Kiểm tra dữ liệu JaCoCo và report có class ID khớp.
4. Kiểm tra tracing/metrics không nhân đôi và context đúng.
5. Kiểm tra sau retransform nếu agent yêu cầu khả năng này.
6. Kiểm tra startup and archive logs ở cả CDS/AOT modes.

## 12. Những sự cố điển hình và cách chẩn đoán

| Triệu chứng | Khả năng nguyên nhân | Bước xử lý |
| --- | --- | --- |
| JVM abort ngay ở startup | `Premain-Class` sai hoặc agent `premain` ném exception | Kiểm tra main manifest, entry point, classpath, stacktrace. |
| Một `-javaagent` không chạy | Launcher/wrapper/argLine ghi đè option | Xác minh command-line hiệu dụng, không chỉ build config. |
| Đổi thứ tự `-javaagent` nhưng transformer vẫn chạy A trước B | A/B thuộc **hai nhóm canRetransform khác nhau** | Đọc docs bốn nhóm, log registration/capability. |
| `retransformClasses` không gọi lại coverage/custom transformer | Nó được đăng ký `canRetransform=false` | Đây là semantics: hiệu ứng cũ tái áp dụng, callback không chạy lại. |
| Báo `UnsupportedOperationException` khi đăng ký capable | Thiếu `Can-Retransform-Classes` hoặc JVM không hỗ trợ | Kiểm tra manifest và `isRetransformClassesSupported()`. |
| `VerifyError`/`ClassFormatError` sau khi thêm agent thứ hai | Bytecode rewrite phá stack map/constant pool hoặc hợp đồng giữa hai transform | Kiểm tra bytes đầu vào/đầu ra từng transformer, classfile validator, version library. |
| `NoClassDefFoundError`/`NoSuchMethodError` liên quan helper | Helper JAR thiếu/đụng version hoặc classloader/module không nhìn thấy | Xác minh JAR, loader, module reads/exports/opens, package relocation. |
| JaCoCo ghi exec nhưng report 0% | Class ID mismatch: bytes runtime khác bytes report | Kiểm tra Sessions, thứ tự JaCoCo, `classdumpdir`, offline rules. |
| JaCoCo lỗi khi instrument lại | Double instrumentation hoặc classfile đã bị biến đổi không phù hợp | Không bật offline và online trùng; chọn một pipeline duy nhất. |
| Tracing tạo hai span giống nhau | Cả custom/APM cùng instrument cùng method | Filters, instrumentation marker, một chủ thể sở hữu hook, integration test. |
| Agent gây `StackOverflowError`/load vòng lặp | Instrument class logger/helper của chính mình | Exclude packages, guard reentrancy, tránh load class trong transformer. |
| CDS bật nhưng startup không nhanh | Archive không dùng được hoặc ít class phù hợp; agent/classpath thay | Bật `-Xlog:cds`, so sánh `-Xshare:off/auto`. |
| `AOTMode=auto` vẫn chạy dù archive incompatibility | JVM fallback không dùng cache | Kiểm tra diagnostics và startup timing; tái tạo cache đúng config. |
| `AOTMode=on` dừng trước `main` | Cache không map được, class linking/VM options không tương thích | Thử auto/off để xác định phạm vi; xem JVM logs, rebuild cache. |
| Test qua JDK khác báo class version unsupported | Agent ASM/coverage tool chưa hỗ trợ classfile version mới | Nâng tool/library lên bản hỗ trợ JDK mục tiêu, chạy compatibility tests. |
| Production không attach được agent | Attach policy, quyền OS/JVM, container/runtime hạn chế | Ưu tiên startup `-javaagent` khi phù hợp; đừng coi attach là mặc định. |

### 12.1. Debug theo phương pháp “giảm dần tổ hợp”

Nếu pipeline ba agent hỏng:

```text
No agent
  -> Agent A only
  -> Agent B only
  -> Agent C only
  -> A+B
  -> A+C
  -> B+C
  -> A+B+C
  -> swap startup order for suspected pair
  -> repeat under -Xshare:off / auto
  -> repeat under AOT auto / on (staging)
```

Ở mỗi bước giữ nguyên app JAR, JDK, flags và workload, trừ một biến cần kiểm tra. Khi lỗi chỉ xuất hiện với A+B, xem **class thật sự bị cả hai instrument** và đặc điểm bytecode; khi chỉ xuất hiện với AOT on, xem cache compatibility trước khi đổi source.

## 13. Checklist phát hành agent và rollback

Trước khi phát hành một custom agent đi cùng coverage/APM:

**Đóng gói:**

- Manifest đúng `Premain-Class`/`Agent-Class` và capabilities thật sự cần.
- Có đủ dependency của agent/transformer ở đúng loader; không đụng thư viện của app.
- JAR version, checksums, JVM minimum version, classfile target và module policy được ghi lại.
- Có cấu hình include/exclude, chống duplicate instrumentation, không tự instrument exporter/logger.
- Không cần quyền `opens`/exports rộng hơn cần thiết chỉ vì muốn “cho chạy được”.

**Kiểm thử:**

- Chạy agent standalone và từng cặp agent, sau đó toàn bộ bộ công cụ.
- Đổi agent order và ghi nhận callback groups.
- Có fixture test cả class mới load lẫn retransform/redefine khi cần.
- Chạy JaCoCo với report thật, check class IDs và line/branch coverage.
- So sánh startup/throughput/p99 khi thêm từng tool.
- Thử `-Xshare:off/auto` và theo dõi log thực sự dùng CDS.
- Với AOT cache, ghi chính xác training/create/runtime options; test auto fallback và staging on fail-fast.

**Vận hành:**

- Không để exception của probe ghi đè exception nghiệp vụ.
- Giới hạn memory/CPU/I/O của worker telemetry; queue full có policy.
- Theo dõi mức lỗi exporter, dropped spans, coverage gaps và retransform failures.
- Có feature flag tắt một nhóm instrumentation mà không tắt toàn bộ dịch vụ khi có sự cố.
- Có quy trình rollback agent binary/config và **tạo lại/loại bỏ cache** nếu thay đổi app/JDK/archive compatibility.
- Nếu cần tắt một transformer, `Instrumentation.removeTransformer(...)` chỉ dừng các callback tương lai, **không tự đảo ngược bytecode đã áp dụng** vào class; có thể phải retransform/redefine phù hợp hoặc restart.

### 13.1. Quy tắc tái lập

Khi thấy lỗi lẻ tẻ, hãy ghi nhận:

```text
JDK vendor/version/OS/architecture
effective command line, -javaagent order and options (redacted)
agent JAR checksums/versions
target class name + defining loader + module
transformer group/canRetransform registration order
classfile major version + pre/post transform hashes
JaCoCo class ID, exec/report artifact versions
CDS/AOT flags, archive/cache origin, JVM archive logs
app behavior, errors, p99 latency and shutdown conditions
```

Hash classfile bytes có thể giúp phát hiện một agent âm thầm thay class, nhưng **không được dùng hash làm thay thế cho việc hiểu classfile semantics**; retransform có thể sắp xếp một số constant pool/attribute khác theo implementation.

## 14. Bài tập tự kiểm tra

**Câu 1.** Lệnh có `-javaagent:B.jar -javaagent:A.jar`. Có phải transformer của B luôn chạy trước A?

**Đáp án:** Không. `premain(B)` được gọi trước `premain(A)`, nhưng transformers chạy theo nhóm retransformation incapable/capable và native/Java, rồi theo thứ tự đăng ký **trong từng nhóm**.

**Câu 2.** Vì sao demo đảo B rồi A mà log load Target vẫn A trước B?

**Đáp án:** A dùng `addTransformer(..., false)` nên ở nhóm Java incapable; B dùng `true` nên ở nhóm Java capable. Nhóm incapable được xử lý trước capable.

**Câu 3.** Khi `retransformClasses(Target.class)`, có cần JVM gọi lại transformer A `false`?

**Đáp án:** Không. Nếu A đã sửa bytes ở load/redefine trước, JVM tái áp dụng hiệu ứng cũ mà không gọi callback A; transformer capable B mới được gọi lại.

**Câu 4.** Test có chạy qua class nhưng JaCoCo report hiện 0% và có execution data. Nên kiểm tra gì?

**Đáp án:** JaCoCo Sessions/class IDs, class bytes runtime so với input report, other agent order, `classdumpdir` và xung đột offline/online instrumentation.

**Câu 5.** “Đặt JaCoCo trước mọi agent” có bảo đảm nó luôn chạy trước các native/capable transformers?

**Đáp án:** Không tuyệt đối. Đây là khuyến nghị JaCoCo để có cơ hội thấy original class files; hợp đồng transformer **ưu tiên nhóm**, không chỉ thứ tự command line.

**Câu 6.** Bật `-Xshare:auto` và ứng dụng chạy bình thường có chứng minh CDS archive được sử dụng không?

**Đáp án:** Không. Auto có thể fallback. Dùng JVM logging như `-Xlog:cds=info` và đo startup/footprint.

**Câu 7.** JDK 24 AOT cache được tạo rồi. Vì sao lúc chạy với agent mới có thể không được dùng?

**Đáp án:** Cache phụ thuộc application/JDK/OS/CPU và options; agent có thể thay class/module graph hoặc kích hoạt các điều kiện không tương thích. Xem log, dùng auto fallback và tạo lại cache đúng cấu hình.

**Câu 8.** `AOTMode=auto` và `AOTMode=on` khác nhau thế nào khi cache không thể map?

**Đáp án:** Trên JDK 24 launcher, auto cho phép chạy không dùng cache; on là chế độ diagnostic fail-fast và JVM có thể dừng ngay.

**Câu 9.** `return null` trong transformer nghĩa là hủy mọi biến đổi của các agent trước?

**Đáp án:** Không. Nó chỉ cho biết transformer hiện tại không thay bytes. Pipeline vẫn mang theo bytes đã được transformer trước tạo ra.

**Câu 10.** Muốn kiểm tra hai agent thật sự compose an toàn, chỉ nhìn log `premain` có đủ không?

**Đáp án:** Không. Cần fixture mà cả hai cùng transform, verify classfile, behavior, coverage IDs, tracing output, retransform và kết quả với CDS/AOT modes.

**Câu 11.** Nếu đã gỡ transformer và đóng agent control connection, tất cả class đã đổi có tự về classfile gốc?

**Đáp án:** Không. Việc gỡ transformer không tự hoàn tác các biến đổi đã cài. Cần cơ chế khôi phục phù hợp hoặc restart.

**Câu 12.** AOT cache của JDK 24 có phải là GraalVM native-image và mặc nhiên có cùng hợp đồng `Instrumentation` không?

**Đáp án:** Không. HotSpot AOT cache là tối ưu cho JVM còn chạy bình thường; native-image có mô hình compilation/runtime khác, cần kiểm tra tài liệu và giới hạn của tool tương ứng.

## 15. Tổng kết và nguồn chuẩn

**Các nguyên tắc nên nhớ:**

1. **Nhiều agent được hỗ trợ**, nhưng phải phân biệt thứ tự `premain`, thứ tự đăng ký và **thứ tự nhóm transform**.
2. Java transformers có hai nhóm `canRetransform=false/true`, xen với native/JVMTI hooks; trong mỗi nhóm mới xét thứ tự đăng ký.
3. Retransformation **chỉ gọi lại transformer capable**, nhưng hiệu ứng incapable trước đó có thể được JVM tái áp dụng; không tự khởi tạo lại mọi agent.
4. JaCoCo dùng **class IDs từ raw class bytes**; các tool sửa bytes trước JaCoCo hoặc report dùng class khác có thể làm coverage mất dù app chạy đúng.
5. Tránh double instrumentation, mất frames/attributes, helper collision, recursive instrumentation và mismatch ở named modules.
6. CDS/AppCDS là **tối ưu có thể fallback**, không phải một chế độ thay semantics của `ClassFileTransformer`; xác minh bằng JVM logs.
7. JDK 24+ AOT cache thêm yêu cầu **nhất quán training/create/runtime**, JDK/OS/CPU và options; `auto` có thể chạy mà không dùng cache, `on` giúp bắt lỗi tương thích.
8. **Không có một thứ tự agent cố định nào bảo đảm mọi tool đều tương thích.** Ma trận kiểm thử app behavior + coverage/tracing + startup/cache mới là tiêu chí deployment.

**Tài liệu tham khảo chính thức:**

- [Java SE 17 — `java.lang.instrument`, nhiều `-javaagent` và thứ tự `premain`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Java SE 17 — `ClassFileTransformer`, bốn nhóm callback và hợp đồng `transform`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Java SE 17 — `Instrumentation.addTransformer` và `retransformClasses`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [JaCoCo — Class Ids, những nguyên nhân mismatch và cách khắc phục](https://www.jacoco.org/jacoco/trunk/doc/classids.html)
- [JaCoCo — Java Agent options, `classdumpdir`, includes/excludes](https://www.jacoco.org/jacoco/trunk/doc/agent.html)
- [JaCoCo — Offline Instrumentation](https://www.jacoco.org/jacoco/trunk/doc/offline.html)
- [JaCoCo — FAQ và tương thích công cụ khác](https://www.jacoco.org/jacoco/trunk/doc/faq.html)
- [Java SE 17 — Java launcher, AppCDS và `-Xshare`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [JDK 24 — Java launcher, AOT cache record/create/auto/on và cache fallback](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483)
- [Inside Java — AOT caching, training/assembly/deployment consistency](https://inside.java/2026/01/09/run-aot-cache/)