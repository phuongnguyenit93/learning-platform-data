# Phân biệt lỗi khởi động premain, lỗi agentmain và lỗi bytecode đã cài

## 1. Bản chất bài toán: phải xác định giai đoạn gây lỗi

Một Java agent có thể thất bại **trước khi ứng dụng vào main**, thất bại khi **attach vào JVM đang chạy**, hoặc được nạp thành công nhưng sau đó làm một class **không thể định nghĩa** hoặc khiến một method đã được instrument **lỗi khi thực thi**. Một exception name như `IllegalStateException`, `ClassFormatError` hay `NoClassDefFoundError` tự nó chưa chỉ ra được gốc lỗi.

Cần phân biệt ba nhóm:

1. **Lỗi khởi động `premain`:** Java agent được chỉ định qua `-javaagent:<jar>`. JVM đọc `Premain-Class`, gọi `premain` trước application `main`. Nếu entry point không load được hoặc method ném exception không bắt, **JVM abort trước application main**.
2. **Lỗi `agentmain` trong dynamic attach:** công cụ yêu cầu nạp agent vào **JVM đã chạy**. JVM gọi `agentmain` qua `Agent-Class`. Nếu lỗi khởi tạo hoặc method throw không bắt, **JVM đích không abort chỉ vì lỗi attach**, nhưng tool gọi `VirtualMachine.loadAgent` có thể nhận lỗi và JVM có thể ghi stack trace.
3. **Lỗi bytecode / class lifecycle:** agent đã vào hoạt động, transformer được gọi. Transformer có thể tự ném exception, trả bytes sai bị JVM từ chối ở bước định nghĩa, hoặc trả bytes hợp lệ được JVM cài thành công nhưng method mới phát sinh lỗi linkage/runtime ở lần gọi sau.

**Ngoại lệ không được bỏ qua:** `Launcher-Agent-Class` cũng gọi method tên `agentmain` nhưng là **launcher agent trong executable JAR**, chạy **trước application main**. Nếu method này throw không bắt, **JVM abort**. Vì vậy phải xác minh **cơ chế khởi chạy**, không phân loại chỉ theo tên method `agentmain`.

Trong bài, ta kiểm thử năm kết quả riêng bằng Java 17 target:

- `premain` throw → process không vào `Main.main`.
- `ClassFileTransformer.transform` throw → không bảo đảm ngăn class load; trong demo V1 vẫn chạy.
- Transformer trả `byte[]{1,2,3}` → `ClassFormatError` khi JVM định nghĩa class.
- Transformer trả classfile V2 **hợp lệ** nhưng V2 gọi helper **vắng mặt ở runtime** → class được định nghĩa, tới lúc gọi method mới có `NoClassDefFoundError`.
- `agentmain` dynamic attach throw → attach tool nhận `AgentInitializationException` nhưng JVM đích còn sống.

Cần nắm **định nghĩa class đã hoàn thành hay chưa**. Transformer callback được gọi và trả dữ liệu **không đồng nghĩa** dữ liệu đã được JVM verify, link, define và chạy thành công.

## 2. Dòng thời gian của ba cơ chế

### 2.1. Startup với premain

~~~text
java -javaagent:diag-agent.jar=options -cp app demo.Main
          |
       JVM bootstrap
          |
       agent JAR + Premain-Class
          |
       load agent class và dependencies
          |
       invoke premain(...)
          |
          +-- throw không bắt / lỗi khởi tạo --> JVM ABORT
          |
          +-- return bình thường
                  |
                  v
            application main()
                  |
            class load / transform / verify / invoke
~~~

Những nguyên nhân điển hình: manifest thiếu `Premain-Class`, sai binary class name, sai signature `premain`, thiếu dependency của agent hoặc lỗi parse config trong `premain`. Nếu JVM abort trong giai đoạn này, không thể kết luận bytecode Target đã bị cài sai vì ứng dụng chưa nhất thiết load Target.

### 2.2. Dynamic attach với agentmain

~~~text
JVM đích đã chạy main và threads
             |
Attach tool / VirtualMachine.loadAgent(...)
             |
Permission / provider / PID / policy
             |
Agent-Class trong agent JAR
             |
load agent class, invoke agentmain(...)
             |
             +-- throw không bắt
             |     JVM đích không abort do lỗi attach
             |     attach caller có thể nhận AgentInitializationException
             |     VM có thể log lỗi tại Attach Listener
             |
             +-- return bình thường
                   tool tiếp tục
                   phải xác minh agent có tác dụng mong đợi
~~~

Một lỗi trong `agentmain` **không mặc nhiên rollback side effects** đã xảy ra trước khi method throw. Agent có thể đã thêm transformer, thread hoặc module relationships rồi mới lỗi. Do đó “target process còn sống” cũng không chứng minh agent **không gây ảnh hưởng**.

### 2.3. Transformer, verify, define, execute

~~~text
Agent đã đăng ký transformer
          |
JVM cần define demo.Target
          |
transform(loader, "demo/Target", inputBytes)
          |
          +-- return null hoặc throw -->
          |     transformer này không thay đổi bytes
          |     những transformer khác vẫn có thể chạy
          |     JVM tiếp tục cố define
          |
          +-- return bytes sai -->
          |     ClassFormatError / VerifyError ở bước load/verify
          |     class có thể CHƯA được define
          |
          +-- return bytes hợp lệ -->
                JVM verify và define class
                        |
                        v
                 new Target() thành công
                        |
                        v
                 target.work() gọi MissingProbe.mark()
                        |
                        v
                 NoClassDefFoundError nếu helper không có
~~~

**Phân biệt ranh giới:** bytes **không hợp lệ** bị từ chối ở class definition, còn bytes đã được định nghĩa **có thể** chỉ phát sinh lỗi khi invoke do lazy resolution, helper visibility hoặc logic mới. Thời điểm resolution có thể khác nhau giữa JVM, nên phải dựa vào mốc runtime thực tế.

## 3. Hợp đồng Java SE 17 của premain

Manifest cho agent chạy bằng `-javaagent`:

~~~text
Premain-Class: demo.DiagAgent
~~~

JVM ưu tiên tìm entry point:

~~~java
public static void premain(
        String agentArgs,
        Instrumentation instrumentation) {
    // Khởi tạo agent.
}
~~~

Nếu overload này không có, JVM tìm:

~~~java
public static void premain(String agentArgs) {
    // Không nhận Instrumentation qua tham số.
}
~~~

Hai đoạn trên **minh họa signature**, không phải hai method bắt buộc phải cùng tồn tại. `premain` cần `public static void` với đúng parameters. JVM gọi `premain` sau khi JVM bootstrap, **trước application main**, và method phải return thì startup mới tiếp diễn.

Theo đặc tả `java.lang.instrument` Java SE 17:

- Nếu JVM không khởi động được agent (class thiếu, method không conformant, manifest sai...), JVM **abort**.
- Nếu `premain` ném exception không bắt, JVM **abort**.
- Nhiều `-javaagent` trên command line được gọi `premain` theo thứ tự được chỉ định.
- Chỉ khai báo `Agent-Class` không khiến `-javaagent` tự chuyển sang gọi `agentmain`.

**Chẩn đoán:** nếu không thấy log ứng dụng bắt đầu, hãy kiểm tra **JAR thực đã deploy**, main manifest, loader của agent class, exception gốc và process exit code. Không dùng mỗi thông báo “Java application startup failed” để suy luận classfile lỗi.

### 3.1. Fail-fast và fail-open của premain

Một **agent policy bắt buộc** có thể chủ động fail-fast nếu không đủ khả năng instrument. Một **telemetry agent tùy chọn** có thể chọn ghi lỗi, disable probe và return an toàn để không chặn application startup. Đây là **quyết định vận hành**, không phải ngữ nghĩa tự động của JVM.

Tránh “catch Throwable rồi bỏ qua mọi lỗi” trong production; `OutOfMemoryError`, lỗi VM hoặc classloader recursion có thể khiến hệ thống ở trạng thái không đáng tin. Nếu chọn fallback, ghi rõ outcome `agent:disabled` và kiểm soát side effects đã tạo.

## 4. agentmain, Attach API và ngoại lệ launcher agent

Manifest cho agent dùng dynamic attach:

~~~text
Agent-Class: demo.DiagAgent
~~~

JVM ưu tiên:

~~~java
public static void agentmain(
        String agentArgs,
        Instrumentation instrumentation) {
    // Khởi tạo agent trong JVM đang chạy.
}
~~~

Nếu không có overload với `Instrumentation`, JVM tìm `agentmain(String)`.

### 4.1. Lỗi target và lỗi tool gọi attach không nằm cùng thread

Khi dynamic attach, JVM đích đã có `Main.main` và các thread nghiệp vụ. Nếu `agentmain` ném exception không bắt, theo Java SE 17 **JVM đích không abort vì lỗi đó**. Nhưng JVM có thể ghi stack trace, và phía tool dùng `VirtualMachine.loadAgent` có thể bị ném:

- `AgentLoadException` — JAR/agent không thể nạp như yêu cầu.
- `AgentInitializationException` — agent đã được yêu cầu nạp nhưng không khởi tạo được.
- `IOException` — lỗi giao tiếp, attach operation hoặc I/O.

**Không lẫn với application exception:** `AgentInitializationException` xảy ra cho **caller của `loadAgent`**, không tự trở thành exception trong business thread của JVM đích. Nếu dùng self-attach trong lab, main cũng chính là caller để ta nhìn thấy điều này.

### 4.2. Launcher-Agent-Class thay đổi kết luận

Java SE 17 có thể chạy executable JAR với main manifest:

~~~text
Launcher-Agent-Class: demo.DiagAgent
~~~

Launcher chọn `agentmain` nhưng gọi **trước application main**. Nếu class/method không thể load hoặc `agentmain` throw/error không bắt, **JVM abort**. Vì vậy:

| Cách bắt đầu | Manifest | JVM gọi | Lỗi entry point không bắt |
|---|---|---|---|
| `-javaagent` ở command line | `Premain-Class` | `premain` | **JVM abort trước main** |
| Dynamic attach sau khi JVM chạy | `Agent-Class` | `agentmain` | **JVM đích không abort chỉ vì lỗi attach** |
| Executable JAR launcher agent | `Launcher-Agent-Class` | `agentmain` | **JVM abort trước main** |

**Quy tắc:** đừng dùng chuỗi “agentmain” trong stack trace để kết luận lỗi attach nếu chưa kiểm tra manifest, command line và JVM lifecycle.

### 4.3. Runtime support cho attach là một câu hỏi khác

Dynamic attach còn phụ thuộc JDK vendor, module `jdk.attach`, quyền OS/PID, container policy và VM flags. Trên HotSpot, `-XX:+EnableDynamicAgentLoading` điều khiển dynamic agent loading; từ JDK 21 JVM có cảnh báo nếu agent được nạp động khi chưa opt-in theo hướng dẫn JEP 451. Self-attach trên một số HotSpot JDK cần property `-Djdk.attach.allowAttachSelf=true`.

Các flags này chỉ quyết định **có thể yêu cầu attach hay không**; chúng không sửa lỗi `agentmain`, không verify bytecode và không tự cho phép transformer thay schema tùy ý.

## 5. Transformer throw khác return bytes sai

`ClassFileTransformer` có callback `transform` để xử lý classfile trước khi JVM define, retransform hoặc redefine. Transformer có thể:

- Trả `null` nếu không có biến đổi.
- Trả một mảng `byte[]` chứa classfile **well-formed** đã biến đổi.
- Ném exception, bao gồm `IllegalClassFormatException` khi input classfile không đúng định dạng.

**Theo Javadoc**, nếu transformer throw exception không bắt, JVM vẫn gọi các transformers còn lại theo thứ tự và vẫn thử load/redefine/retransform class; với transformer đó, kết quả tương đương **return null**. Do đó **throw trong transformer không bảo đảm từ chối nạp class**.

### 5.1. Cùng một exception, hai vòng đời khác nhau

~~~java
throw new IllegalStateException("demo-failure");
~~~

Nếu dòng này thoát khỏi **`premain`** chưa bắt → JVM abort startup. Nếu nó thoát khỏi **`transform`** → JVM tiếp tục pipeline, và class vẫn có thể load bình thường. Nếu nó thoát khỏi **`agentmain` khi dynamic attach** → attach caller có thể nhận error nhưng target không abort do chính lỗi attach.

**Luôn xác định method/callback gốc từ stack trace và timestamp.**

### 5.2. Malformed bytes không phải installed bytes

~~~java
return new byte[] {1, 2, 3};
~~~

Mảng này không có magic `CAFEBABE` và cấu trúc classfile hợp lệ. Nếu đây là bytes cuối, JVM có thể báo `ClassFormatError` ở class definition. Trường hợp bytecode đúng định dạng nhưng verifier thấy stack frame hoặc operand stack sai có thể phát sinh `VerifyError`.

**Chỉ log transformer đã return bytes là chưa đủ.** Cần bằng chứng VM đã define class, hoặc với `redefineClasses/retransformClasses` thì thao tác API đã hoàn thành bình thường.

### 5.3. Valid bytes vẫn có thể sai linkage

Nếu V2 đã compile với `MissingProbe.mark()` nhưng JVM đích không nhìn thấy helper, quá trình class definition có thể thành công, rồi tới invocation của `Target.work()` mới gặp `NoClassDefFoundError`. Nếu helper có class nhưng sai method descriptor, `NoSuchMethodError` có thể xuất hiện. Nếu target không được quyền access helper, có thể xuất hiện `IllegalAccessError`.

**Đây là lỗi sau installation**, khác với `ClassFormatError` ở bước verify/define. Không phải mọi VM đều resolve dependencies ở một thời điểm giống nhau, nên cần giữ mốc `class-defined` và `method-invoked` riêng.

## 6. Bảng phân loại theo triệu chứng

| Triệu chứng | Nghi ngờ trước tiên | Bằng chứng cần lấy |
|---|---|---|
| Process abort, application `main` chưa in một dòng nào | `Premain-Class`, `premain` hoặc startup loader | Manifest, stderr, exception, exit code |
| Application đã chạy, `loadAgent` báo `AgentInitializationException` | `Agent-Class` / dynamic `agentmain` | Caller stack, Attach Listener logs, target PID vẫn sống |
| `agentmain` throw và JVM abort trước main | Có thể đang dùng `Launcher-Agent-Class` | Executable JAR manifest, cách launch |
| Transformer callback throw nhưng target V1 chạy | Callback exception được coi như return `null` | Callback log + class bytes/behavior thực |
| Transformer trả bytes, `ClassFormatError` | Bytes cuối malformed, class chưa define | Classfile, verifier, class definition marker |
| `VerifyError` | Invalid stack maps/instructions/frames | Bytecode dump, full verifier output |
| Object đã tạo, method báo `NoClassDefFoundError` | Helper thiếu hoặc không load được | Defining class loader/module, runtime classpath |
| Method báo `NoSuchMethodError` | Helper runtime khác version/descriptor | `javap -p -s`, dependency versions |
| Method báo `IllegalAccessError` | Runtime access/module/package visibility | Target/module identity và exports/opens |
| Instrumentation in đúng log nhưng kết quả sai | Bytecode đã cài làm đổi semantics | Return value, exception flow, side effects |
| Không thấy transformer callback | Target đã load trước hoặc filter/registration sai | Agent entry timestamps, class name/loader |
| JVM còn chạy nhưng probe không xuất hiện | Agent có thể fail-open hoặc transform bị bỏ qua | Entry log, callback outcome, runtime trace |

Mỗi hàng là **hướng chẩn đoán**, không phải quan hệ một-một. Ví dụ cùng `NoClassDefFoundError` có thể xảy ra ngay khi JVM load class của agent do agent JAR thiếu dependency, hoặc chỉ khi method đã instrument tham chiếu tới helper còn thiếu. **Thời điểm** quan trọng hơn tên exception.

## 7. Demo hoàn chỉnh: năm chế độ trong một bộ source Java 17

Bài thực hành sử dụng một agent JAR với cả `premain` và `agentmain`. Chúng ta dùng `javac --release 17` để compile, chạy thử với JDK 24.0.2 và `-Xverify:all`.

Cấu trúc thư mục:

~~~text
agent-diagnostics-lab/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── demo/DiagAgent.java
│   ├── app/
│   │   └── demo/Main.java
│   │   └── demo/Target.java        # V1
│   ├── v2/
│   │   └── demo/Target.java        # V2 thiếu helper ở runtime
│   └── helper/
│       └── demo/MissingProbe.java  # chỉ cung cấp khi compile V2
└── out/
    ├── agent/
    ├── app/
    ├── v2/
    └── diag-agent.jar
~~~

Hai source `demo.Target` cùng binary name có chủ đích, phải compile ra **hai output directories riêng**. Khi chạy JVM chỉ dùng `out/app` trên classpath; V2 được agent đọc thành bytes từ file `out/v2/demo/Target.class`. Không thêm cả `out/v2` vào runtime classpath, vì nếu làm vậy helper có thể được load và mất thí nghiệm runtime linkage.

### 7.1. Agent: src/agent/demo/DiagAgent.java

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class DiagAgent {
    public static void premain(String options, Instrumentation inst)
            throws Exception {

        String mode = options == null ? ""
                : options.split(":", 2)[0];
        System.out.println("agent:premain mode=" + mode);

        if ("fail".equals(mode)) {
            throw new IllegalStateException(
                    "premain-demo-failure");
        }

        if ("throws".equals(mode)
                || "badclass".equals(mode)
                || "installed".equals(mode)) {

            final byte[] replacement = "installed".equals(mode)
                    ? Files.readAllBytes(Path.of(
                            options.substring("installed:".length())))
                    : null;

            inst.addTransformer(new ClassFileTransformer() {
                @Override
                public byte[] transform(
                        ClassLoader loader,
                        String name,
                        Class<?> redefined,
                        ProtectionDomain domain,
                        byte[] original) {

                    if (!"demo/Target".equals(name)) {
                        return null;
                    }

                    System.out.println(
                            "agent:transform mode=" + mode);

                    if ("throws".equals(mode)) {
                        throw new IllegalStateException(
                                "transform-demo-failure");
                    }

                    if ("badclass".equals(mode)) {
                        return new byte[] {1, 2, 3};
                    }

                    return replacement;
                }
            }, false);
        }

        System.out.println("agent:premain-ready");
    }

    public static void agentmain(
            String options, Instrumentation inst) {
        System.out.println(
                "agent:agentmain mode=" + options);

        if ("fail".equals(options)) {
            throw new IllegalStateException(
                    "agentmain-demo-failure");
        }

        System.out.println("agent:agentmain-ready");
    }
}
~~~

**Giải thích đầy đủ:**

- `premain` lấy `Instrumentation`, phân tích option `fail`, `throws`, `badclass` hoặc `installed:<path>`.
- `fail` throw **trong entry point**. JVM chưa chuyển sang application main.
- Ba mode còn lại đăng ký transformer lọc đúng class name `demo/Target`. `name` trong callback dùng dấu slash, không dùng `demo.Target`.
- `throws` throw unchecked exception trong **transform callback**, không phải entry point.
- `badclass` trả classfile bytes cố ý sai.
- `installed` trả V2 class bytes compile trước, có reference tới helper không sẵn ở runtime.
- `agentmain` được gọi qua dynamic attach, cố ý throw để thấy khác biệt với `premain`.
- Callback trả `null` cho các class khác để tránh self-instrument, bootstrap recursion.
- Không đăng ký retransformation; ví dụ chỉ instrument **khi target được load lần đầu**. Không cần `Can-Retransform-Classes` hay `Can-Redefine-Classes`.

**Không chạy mode `badclass` hoặc `throws` trên production.** Các lỗi này được đặt trong sandbox để minh họa hợp đồng transformer.

### 7.2. Target V1: src/app/demo/Target.java

~~~java
package demo;

public final class Target {
    public void work() {
        System.out.println("target:v1");
    }
}
~~~

Đây là class sẽ được app load khi `new Target()`. Nếu transformer không thay bytes, `work()` in `target:v1`.

### 7.3. Main: src/app/demo/Main.java

~~~java
package demo;

import com.sun.tools.attach.AgentInitializationException;
import com.sun.tools.attach.VirtualMachine;

public final class Main {
    public static void main(String[] args) throws Exception {
        String mode = args[0];
        System.out.println("main:begin mode=" + mode);

        if ("attach".equals(mode)) {
            VirtualMachine vm = VirtualMachine.attach(
                    Long.toString(ProcessHandle.current().pid()));

            try {
                vm.loadAgent(args[1], "fail");
                System.out.println("main:attach-returned");
            } catch (AgentInitializationException expected) {
                System.out.println("main:attach-error="
                        + expected.getClass().getSimpleName());
            } finally {
                vm.detach();
            }

            System.out.println("main:still-running");
            return;
        }

        try {
            System.out.println("main:before-target");
            Target target = new Target();
            System.out.println("main:target-defined");
            target.work();
            System.out.println("main:target-success");
        } catch (LinkageError expected) {
            System.out.println("main:linkage-error="
                    + expected.getClass().getSimpleName());
        }

        System.out.println("main:still-running");
    }
}
~~~

**Các mốc phải đọc:**

- `main:begin` = ứng dụng đã thật sự vào main. Với lỗi `premain`, dòng này không xuất hiện.
- `main:before-target` = chuẩn bị load/instantiate Target.
- `main:target-defined` = `new Target()` đã thành công. Nếu lỗi phát sinh sau đó, ta biết target object đã được tạo trong JVM.
- `main:linkage-error=...` = test harness cố tình bắt `LinkageError` để in loại lỗi và không chết process.
- `main:still-running` = JVM/application còn tiếp tục trong test; **không** tự chứng minh instrumentation đã thành công.
- `mode=attach` dùng JDK Attach API `com.sun.tools.attach.VirtualMachine`. Đây là JDK-specific API được tài liệu hóa trong module `jdk.attach`, không phải một phần portable Java SE core. Self-attach phụ thuộc quyền/runtime settings.

**Không nên bắt `LinkageError` toàn cục trong application production** như cách tránh hỏng hệ thống; đây là test harness cô lập để so sánh các pha.

### 7.4. Helper compile-time: src/helper/demo/MissingProbe.java

~~~java
package demo;

public final class MissingProbe {
    public static void mark() {
        System.out.println("probe:mark");
    }
}
~~~

### 7.5. V2: src/v2/demo/Target.java

~~~java
package demo;

public final class Target {
    public void work() {
        MissingProbe.mark();
        System.out.println("target:v2");
    }
}
~~~

V2 compile thành công vì `MissingProbe` có mặt trong **output `out/v2` lúc build**. Nhưng runtime classpath chỉ chứa `out/app`, nên `MissingProbe` **không được load từ `out/v2`**. Classfile của V2 vẫn hợp lệ; lỗi xảy ra khi instruction gọi helper cần resolve.

Tùy JVM và classloader, resolution có thể eager hoặc lazy ở các vị trí khác nhau; kết quả **cụ thể trong JDK 24.0.2 test** là instance được tạo rồi mới có `NoClassDefFoundError` khi gọi `work()`.

### 7.6. Agent JAR manifest

Tệp **`agent.mf`** với newline cuối:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.DiagAgent
Agent-Class: demo.DiagAgent

~~~

Không có `Launcher-Agent-Class` trong ví dụ để tập trung vào hai đường startup `-javaagent` và dynamic attach.

## 8. Build bằng JDK 17 hoặc JDK mới hơn

Tạo thư mục output. Bash:

~~~bash
mkdir -p out/agent out/app out/v2
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app, out/v2
~~~

Ở thư mục gốc `agent-diagnostics-lab`, compile:

~~~bash
javac --release 17 -d out/agent src/agent/demo/DiagAgent.java
javac --release 17 --add-modules jdk.attach -d out/app src/app/demo/Main.java src/app/demo/Target.java
javac --release 17 -d out/v2 src/v2/demo/Target.java src/helper/demo/MissingProbe.java
jar --create --file out/diag-agent.jar --manifest agent.mf -C out/agent .
~~~

**Giải thích build:**

- `--release 17` tạo classfiles tương thích Java 17 và giới hạn APIs theo release đó.
- `--add-modules jdk.attach` cần cho source `Main` tham chiếu Attach API trong môi trường JDK phù hợp.
- `out/app` chứa Main và Target V1.
- `out/v2` chứa Target V2 cùng helper để build, nhưng không phải runtime classpath.
- `out/agent` đóng thành JAR chứa `DiagAgent.class` và manifest.
- Agent và app được compile riêng; `DiagAgent` không phụ thuộc ASM/Byte Buddy nên không cần dependency khác.

Kiểm tra artifact:

~~~bash
jar --list --file out/diag-agent.jar
javap -p -s -classpath out/app demo.Target
javap -p -s -classpath out/v2 demo.Target
javap -c -p -classpath out/v2 demo.Target
~~~

`javap -c` trên V2 cho thấy method `work` có bytecode gọi `MissingProbe.mark`. Đây là bằng chứng compile-time dependency tồn tại trong V2 classfile; nó **không bảo đảm** helper sẽ có trong runtime classloader.

## 9. Chạy thử bốn chế độ startup và bytecode

### 9.1. Test A — premain throw làm JVM abort

~~~bash
java -Xverify:all -javaagent:out/diag-agent.jar=fail -cp out/app demo.Main normal
~~~

**Dấu mốc stdout đã kiểm thử:**

~~~text
agent:premain mode=fail
~~~

Sau đó VM báo lỗi startup agent trên stderr; process có **exit code 1** trong test JDK 24.0.2. **Không có** `agent:premain-ready`, `main:begin`, `main:target-defined`.

Ý nghĩa: sự cố nằm ở **premain/agent startup**. Thông báo stderr/fatal detail của mỗi JVM có thể khác nhau; không cần exact-match toàn bộ fatal trace để phân loại.

### 9.2. Test B — transformer throw nhưng app vẫn chạy V1

~~~bash
java -Xverify:all -javaagent:out/diag-agent.jar=throws -cp out/app demo.Main normal
~~~

**Stdout đã kiểm thử:**

~~~text
agent:premain mode=throws
agent:premain-ready
main:begin mode=normal
main:before-target
agent:transform mode=throws
main:target-defined
target:v1
main:target-success
main:still-running
~~~

Agent entry point đã return. Transformer throw lúc Target load, nhưng JVM xem transformer này như return `null`; với pipeline đơn giản của lab, class V1 vẫn load và `work()` in `target:v1`.

**Không suy rộng** rằng mọi throwable từ mọi giai đoạn JVM được bỏ qua. Đây chỉ là hợp đồng callback transformer. Các transformer khác vẫn có thể trả bytes sai hoặc agent đã gây side effects riêng.

### 9.3. Test C — malformed bytes, class không được define

~~~bash
java -Xverify:all -javaagent:out/diag-agent.jar=badclass -cp out/app demo.Main normal
~~~

**Stdout đã kiểm thử:**

~~~text
agent:premain mode=badclass
agent:premain-ready
main:begin mode=normal
main:before-target
agent:transform mode=badclass
main:linkage-error=ClassFormatError
main:still-running
~~~

Không in `main:target-defined`. JVM không thể định nghĩa Target từ bytes sai; lỗi được test harness catch và application main tiếp tục. Nếu production không catch, thread/process có thể bị ảnh hưởng theo đường gọi.

**Đây không phải bằng chứng một method đã cài rồi mới ném lỗi.** Nó thất bại **trước mốc class definition**.

### 9.4. Test D — classfile hợp lệ đã define, invocation lỗi linkage

~~~bash
java -Xverify:all -javaagent:out/diag-agent.jar=installed:out/v2/demo/Target.class -cp out/app demo.Main normal
~~~

**Stdout đã kiểm thử:**

~~~text
agent:premain mode=installed
agent:premain-ready
main:begin mode=normal
main:before-target
agent:transform mode=installed
main:target-defined
main:linkage-error=NoClassDefFoundError
main:still-running
~~~

Dòng `main:target-defined` xuất hiện trước lỗi, chứng minh `new Target()` đã hoàn tất ở JVM kiểm thử. Sau đó `Target.work()` V2 gọi `MissingProbe.mark` và báo `NoClassDefFoundError` vì runtime không thấy helper.

**Cách sửa đúng:** bảo đảm helper class có trong loader/module mà target có thể liên kết hợp lệ, hoặc tránh chèn reference đó. Đổi `Premain-Class`, thêm `--add-opens` bừa bãi hoặc chỉ catch exception trong transformer không phải giải pháp cho một class helper bị thiếu.

## 10. Chạy thử agentmain dynamic attach

Self-attach chỉ là **phương tiện tạo demo với một process**. Trên JVM không hỗ trợ self-attach, chuyển sang tool process riêng và target PID theo Attach API. Với HotSpot JDK 24 đã kiểm thử, command cần cho phép self attach và dynamic loading.

**Bash:**

~~~bash
agentJar="$(pwd)/out/diag-agent.jar"
java -Xverify:all --add-modules jdk.attach -Djdk.attach.allowAttachSelf=true -XX:+EnableDynamicAgentLoading -cp out/app demo.Main attach "$agentJar"
~~~

**Windows PowerShell:**

~~~powershell
$agentJar = (Resolve-Path 'out/diag-agent.jar').Path
java -Xverify:all --add-modules jdk.attach '-Djdk.attach.allowAttachSelf=true' '-XX:+EnableDynamicAgentLoading' -cp out/app demo.Main attach $agentJar
~~~

Đưa flags `-D...`/`-XX...` trong single quotes như trên giúp PowerShell chuyển nguyên argument tới `java`. Với Bash, quote path agent JAR để xử lý thư mục có spaces. Agent JAR path được truyền cho `VirtualMachine.loadAgent` phải được JVM đích truy cập.

**Những dòng stdout cần đối chiếu:**

~~~text
main:begin mode=attach
agent:agentmain mode=fail
main:attach-error=AgentInitializationException
main:still-running
~~~

Trên JDK 24.0.2 test riêng, exit code là **0** vì `Main` bắt `AgentInitializationException` rồi trả về bình thường, đồng thời JVM ghi stack trace **Attach Listener** và thông báo agent failed to start trên stderr. Chi tiết log nội bộ không nên exact-match vì thay đổi theo build JDK/vendor.

**Kết luận đúng:** dynamic `agentmain` **không khởi tạo thành công**, nhưng JVM target **vẫn sống** sau lời gọi lỗi. Exit code 0 của **ứng dụng test** không chứng minh agent attach thành công.

Nếu tự attach bị chặn **trước khi gọi `agentmain`**, có thể gặp `AttachNotSupportedException` hoặc `IOException`; đó là lỗi **attach transport/policy**. Không được coi tình huống này là phép thử cho hợp đồng uncaught `agentmain`.

## 11. Lỗi “bytes đã cài” và nguyên nhân khác nhau

### 11.1. Không đồng nhất format/verification với runtime linkage

| Loại lỗi | Thời điểm điển hình | Nguyên nhân |
|---|---|---|
| `ClassFormatError` | Đọc classfile khi define | Magic/constant pool/structure malformed |
| `VerifyError` | Bytecode verification trước execution | Stack maps, operand stack, control flow/types sai |
| `NoClassDefFoundError` | Class resolution/linkage, có thể ở invocation | Class helper thiếu hoặc không load được |
| `NoSuchMethodError` | Method resolution | Runtime class không có descriptor được gọi |
| `IllegalAccessError` | Access check/linkage | Type/member/package/module không accessible |
| `ExceptionInInitializerError` | Class initialization | Static initializer ném exception |
| `NullPointerException` trong probe | Execution | Logic bytecode/helper không xử lý null |
| `StackOverflowError` trong probe | Execution | Instrumented method gọi helper, helper gọi lại method gây recursion |
| `UnsupportedClassVersionError` | Load/define class | Classfile major mới hơn VM hỗ trợ |
| `UnmodifiableClassException` | Retransform/redefine API | Class không modifiable |
| `UnsupportedOperationException` | Retransform/redefine API | VM không hỗ trợ capability/schema change |

Cùng một class có thể qua verify và define, nhưng resolution của các symbolic references được trì hoãn. Vì vậy **một dòng `ClassFileTransformer.transform` thành công không phải xác nhận business method an toàn**.

### 11.2. Có nhiều transformers

Nếu một transformer throw, các transformers khác vẫn có thể được gọi. Những bytes cuối của chain mới là thứ VM kiểm tra. Khi điều tra, ghi lại:

- transformer registration order và `canRetransform`;
- target binary name và class loader;
- hash/size của bytes input và bytes output (không log raw bytes tùy tiện);
- transformer nào trả `null`, exception, hay bytes mới;
- bước cuối verify/redefine return thành công hay thất bại;
- có new invocation dùng definition mới hay không.

Không bao giờ in `class-defined=true` ngay trong callback trước khi VM verify/define.

### 11.3. Class loader, module và helper visibility

Nếu target class từ bootstrap loader, helper ở system classloader không tự nhiên được nhìn thấy. Nếu target thuộc named module, có thể cần đọc module helper và được export package; `Instrumentation.redefineModule` chỉ thay relations, không tự làm helper class xuất hiện. Nếu shading relocate package helper, bytecode injected phải dùng đúng internal names/descriptors đã đóng gói.

Trước khi sửa bằng launcher flags, kiểm tra **class có thực sự tồn tại** và được loader của target nhìn thấy chưa.

## 12. Quy trình điều tra theo năm dấu mốc

### Mốc 1 — entry point nào được gọi?

Kiểm tra cách chạy:

~~~text
-javaagent:...             -> Premain-Class -> premain
VirtualMachine.loadAgent   -> Agent-Class   -> agentmain
Launcher-Agent-Class       -> agentmain trong startup executable JAR
~~~

Đọc **manifest bên trong JAR thực**, không dùng file manifest source chưa đóng gói. Với nhiều agents, ghi thứ tự `-javaagent` và versions.

### Mốc 2 — application main đã bắt đầu chưa?

Có dấu mốc `main:start` không? Nếu không, kiểm tra `premain` và JVM launcher. Nếu đã có, chuyển tiếp sang attach/class loading/probe. Không vì thấy stack của agent mà quy lỗi luôn cho startup.

### Mốc 3 — agentmain có chạy trong JVM đích không?

Thu thập caller exception `AgentLoadException`/`AgentInitializationException`/`IOException` và stderr của **target JVM**, xác định permission, PID, provider, vendor/runtime policy. Nếu `agentmain` đã chạy rồi throw, kiểm tra **side effects đã xảy ra trước throw**.

### Mốc 4 — class đã được verify/defined chưa?

- Transformer nào được gọi?
- Có trả bytes sai, return null hoặc throw?
- JVM báo `ClassFormatError`/`VerifyError` trước object creation không?
- Với `redefineClasses/retransformClasses`, API có return bình thường không?
- Object creation có thành công không?
- Invocation mới đã chạy chưa?

Nếu bytes đã install, xem xét **linkage và business semantics**, không chỉ verifier.

### Mốc 5 — method/probe lỗi ở đâu?

Nếu target instance được tạo nhưng method lỗi, kiểm tra symbolic references tới helper, method descriptors, module reads/exports, classloader visibility, recursion, exception flow và return value. Dùng `javap` để xem bytecode build artifact; nếu cần độ chính xác tuyệt đối về bytes runtime, thu bằng diagnostics được cho phép.

Công cụ:

~~~bash
jar --list --file out/diag-agent.jar
javap -v -p out/v2/demo/Target.class
jdeps --jdk-internals out/diag-agent.jar
~~~

Với HotSpot, unified logging như `-Xlog:class+load=info` có thể hữu ích khi debug class loading. Đầu ra có thể rất lớn; chỉ bật trong môi trường hoặc khoảng thời gian có kiểm soát.

## 13. Sau lỗi cần xử lý hậu quả và rollback thế nào?

### 13.1. Uncaught premain error: có thể không có ứng dụng cần rollback

Vì `premain` throw làm startup abort, cần sửa agent JAR/config và khởi động lại process. Nhưng nếu `premain` đã sửa file, mở socket hoặc tạo side effects bên ngoài trước throw, startup abort không tự hoàn tác những tác động đó.

### 13.2. agentmain error: process còn sống chưa chắc sạch

Một dynamic agent có thể đã đăng ký transformer, thay module relationships hoặc thay definition rồi mới ném exception. JVM không abort theo hợp đồng attach, nhưng không tự rollback side effects. Agent production nên tổ chức init theo giai đoạn, báo trạng thái `ready/failed/degraded` và có cleanup rõ ràng cho resource có thể cleanup.

### 13.3. Transformer throw: không có biến đổi từ callback đó

Nếu transformer throw, nó tương đương `null` đối với bước transform ấy; tuy nhiên đã có thể có logging hoặc side effects trước throw. Các transformers khác có thể vẫn tạo bytes mới; không kết luận toàn bộ class không bị sửa.

### 13.4. Classfile bytes sai bị từ chối

Khi class definition thất bại vì `ClassFormatError`, instance có thể chưa được tạo; không “undo bytecode đã cài” bằng `removeTransformer`. Cần sửa transformer/replacement bytes và tái hiện trong một class loading attempt hợp lệ, thường bằng JVM mới hoặc class loader mới trong môi trường test.

### 13.5. Bytes đã cài nhưng method lỗi

Gỡ transformer không tự đưa class về V1. Nếu muốn rollback definition trên class đã load, cần capabilities và bytes baseline phù hợp cho `redefineClasses`/`retransformClasses`. Với method đang chạy, active frames có thể giữ bytecode cũ, new invocations dùng definition mới. Phải test cả trạng thái field và các requests đang hoạt động.

**Không báo `instrumentation=SUCCESS` chỉ vì agent entry point return**; cần xác minh class definition/update và invocation thực sự đúng.

## 14. Chính sách fail-fast, fail-open và log nên có

### 14.1. Fail-fast hay fail-open tùy mục tiêu

| Loại agent | Nguyên tắc ưu tiên |
|---|---|
| Bảo mật bắt buộc / kiểm soát chính sách | Fail-fast nếu không đảm bảo điều kiện an toàn; không âm thầm bỏ kiểm tra |
| Telemetry/metrics tùy chọn | Có thể fail-open có kiểm soát, log agent disabled và không làm hỏng business |
| Hotfix thay logic nghiệp vụ | Chỉ công bố successful cutover sau khi API update thành công và new invocations đạt smoke test |
| Dynamic troubleshooting agent | Hạn chế phạm vi, kiểm soát quyền attach, ghi lại partial side effects |
| Agent xử lý nhiều class | Phân biệt lỗi class riêng lẻ với lỗi toàn phiên agent; kiểm tra atomicity của từng API |

Một mẫu **minh họa**, không độc lập vì helper chưa khai báo:

~~~java
public static void premain(String args, Instrumentation inst) {
    try {
        installOptionalProbes(inst);
        reportStatus("READY");
    } catch (Exception e) {
        reportError(e);
        if (requiredByPolicy()) {
            throw new IllegalStateException(
                    "Required instrumentation failed", e);
        }
        reportStatus("DISABLED");
    }
}
~~~

Không “catch Throwable và bỏ qua tất cả” nếu có `OutOfMemoryError`/VM failures. Khi fail-open, cần bảo đảm những hooks đã được cài một phần không làm ứng dụng chạy ở trạng thái nguy hiểm.

### 14.2. Log correlation theo lifecycle

Một cấu trúc sự kiện gợi ý:

~~~text
agent.jar.sha256=...
agent.mode=PREMAIN | AGENTMAIN | LAUNCHER_AGENTMAIN
agent.phase=ENTER | READY | ERROR
agent.pid=...
agent.jvm.version=...
target.class=demo.Target
target.loader=...
transform.phase=CALLBACK | RETURN_NULL | RETURN_BYTES | CALLBACK_ERROR
define.phase=REJECTED | DEFINED
invoke.method=demo.Target.work()V
invoke.outcome=SUCCESS | LINKAGE_ERROR | BUSINESS_ERROR
~~~

Đây là **mẫu log**, không phải output lab. Không tạo event `define.phase=DEFINED` trong callback nếu chưa có bằng chứng JVM thực sự define class. Giới hạn log volume, tránh recursion ở class loading path và không đẩy raw bytecode/secrets vào log.

### 14.3. Điều cần test trong CI

- Agent JAR có đúng manifest entry points.
- Agent dependencies thực sự được đóng gói/visible ở loader đích.
- `premain` validation fail cho outcome rõ ràng trước application main.
- `agentmain` lỗi có cảnh báo/caller exception nhưng target process tồn tại.
- Transformer throw không bị nhầm thành policy enforcement.
- Malformed bytes bị verifier từ chối trong **sandbox**.
- Valid transformed bytes không có unresolved helpers hoặc method descriptors sai.
- Test trên JVM runtime matrix và đúng module/classloader topology.
- Run với `-Xverify:all`, kiểm tra stdout/stderr, exit code và service behavior.

## 15. Những hiểu nhầm phổ biến

**1. “Chỉ cần thấy `premain` print log là startup agent đã thành công.”** Sai: `premain` có thể print rồi throw, làm JVM abort.

**2. “`agentmain` lỗi thì ứng dụng đích luôn chết.”** Sai với dynamic attach; đúng là phải lưu ý launcher agent mode riêng nếu nó chạy trước main.

**3. “Exit code 0 nghĩa là agent đã attach thành công.”** Sai: application có thể catch `AgentInitializationException` rồi return bình thường.

**4. “Transformer throw sẽ ngăn class load.”** Sai: callback exception tương đương return null cho transformer ấy.

**5. “Transformer return bytes là JVM đã cài bytes.”** Sai: parser/verifier có thể từ chối chúng.

**6. “Class đã được định nghĩa thì mọi method luôn chạy được.”** Sai: symbolic resolution và helper loading có thể fail khi invoke.

**7. “`ClassFormatError` luôn là lỗi sau khi method chạy.”** Sai: nó thường liên quan classfile structure trong quá trình define.

**8. “`NoClassDefFoundError` chỉ là thiếu jar của agent.”** Sai: lỗi có thể là dependency của app, injected helper hoặc vấn đề classloader/module.

**9. “Remove transformer là rollback bytecode hiện có.”** Sai: chỉ thay future registration/pipeline; definition đang được sử dụng không tự undo.

**10. “Chỉ cần thêm `--add-opens` để sửa mọi linkage error.”** Sai: flags module access không tạo helper class còn thiếu.

**11. “Có `Agent-Class` thì `-javaagent` gọi `agentmain`.”** Sai: `-javaagent` dùng `Premain-Class`.

**12. “Thử attach trên JDK này thành công nghĩa là mọi JDK/container đều cho attach.”** Sai: attach là cơ chế phụ thuộc implementation và policy, cần kiểm thử runtime đích.

## 16. Bài tập và câu hỏi ôn luyện

### Bài A — nhận biết premain failure

Chạy mode `fail`. Vì sao không in `main:begin`? Nếu agent là telemetry tùy chọn, nên thay cách xử lý config/exception như thế nào để JVM có thể chạy trong trạng thái degraded **đã được thiết kế**?

### Bài B — phân biệt callback throw với fail-fast

Chạy mode `throws` và tìm `target:v1`. Vì sao một exception trong transformer không phải cơ chế chặn class được hỗ trợ? Nếu agent là thành phần bắt buộc của chính sách, điều kiện nào phải được kiểm tra trước khi công bố app sẵn sàng?

### Bài C — định nghĩa class hay thực thi method?

So stdout `badclass` và `installed`. Dòng nào chứng minh JVM đã tạo instance của Target? Vì sao `ClassFormatError` và `NoClassDefFoundError` ở hai chế độ này phải điều tra theo hai hướng khác nhau?

### Bài D — sửa helper visibility

Ở lab `installed`, thử thêm helper `MissingProbe.class` vào classpath runtime có thể nhìn thấy từ Target. Nếu mọi điều kiện khác đúng, method V2 có thể in `probe:mark` rồi `target:v2`. Điều này cho thấy classfile V2 ban đầu **không sai định dạng**, chỉ thiếu dependency khi chạy.

### Bài E — lỗi attach và target health

Chạy mode `attach` trong JDK hỗ trợ self-attach. Tại sao `AgentInitializationException` xuất hiện nhưng vẫn in `main:still-running`? Đó có chứng minh agent đã hoàn toàn không để lại side effects không?

### Bài F — Launcher-Agent-Class

Nếu một executable JAR có `Launcher-Agent-Class` và `agentmain` ném exception không bắt trước application main, kết quả khác dynamic attach thế nào? **Đáp án:** launcher JVM abort startup.

### Bài G — lỗi sau redeﬁnition

Một agent gọi `redefineClasses` thành công rồi new invocation bị `NoSuchMethodError`. Có nên báo `premain startup failed` không? **Không**: lỗi ở linkage của code đã cài. Cần kiểm tra helper method descriptor, loader/module và rollback strategy.

### Câu hỏi nhanh

1. **Entry point `-javaagent`?** — `premain`.
2. **Entry point dynamic attach?** — `agentmain` từ `Agent-Class`.
3. **Uncaught `premain` exception?** — JVM abort trước main.
4. **Uncaught dynamic `agentmain` exception?** — Target JVM không abort vì lỗi attach; caller có thể nhận exception.
5. **`Launcher-Agent-Class` dùng method nào?** — `agentmain` nhưng ở startup.
6. **Transformer throw có tương đương gì?** — Return `null` đối với transformer đó.
7. **Trả classfile bytes sai?** — Có thể `ClassFormatError`/`VerifyError` trước definition.
8. **Define thành công nhưng thiếu helper lúc invoke?** — Có thể `NoClassDefFoundError`.
9. **Class loader của target có quan trọng không?** — Có; nó quyết định helper visibility.
10. **`-Xverify:all` có chứng minh không có runtime linkage errors không?** — Không.
11. **`AgentInitializationException` xuất hiện ở đâu?** — Phía gọi `VirtualMachine.loadAgent`.
12. **`removeTransformer` có undo bytecode đã cài?** — Không.
13. **Cần kiểm tra điều gì trước khi nói rollback thành công?** — Update result, new invocations, active frames và app state.

## 17. Checklist chốt và nguồn tài liệu

### Preflight kỹ thuật

- [ ] Xác định `-javaagent`, dynamic attach hay executable launcher agent.
- [ ] Đọc manifest trong final JAR; đúng `Premain-Class`, `Agent-Class` hoặc `Launcher-Agent-Class`.
- [ ] Kiểm tra signature của entry point và dependencies.
- [ ] Ghi status `premain/agentmain enter/ready/fail` với PID/JVM version.
- [ ] Thu thập stdout, stderr, exit code và process liveness.
- [ ] Kiểm tra runtime/permission support cho dynamic attach.
- [ ] Chỉ định rõ transformer order, class loader, module và target name.
- [ ] Phân biệt callback exception, malformed class bytes, verify/define và invocation linkage.
- [ ] Kiểm tra helper class và method descriptors trong JVM đích.
- [ ] Chạy integration tests với `-Xverify:all`.
- [ ] Không coi callback return bytes là xác nhận class installation.
- [ ] Không để test malformed bytecode chạy trên service production.
- [ ] Nếu agent đã thay code, chuẩn bị rollback đúng API, không dựa vào removeTransformer.
- [ ] Báo success theo **bằng chứng chính xác của pha đã thành công**, không dùng một boolean chung.

**Kết luận:** điều tra Java Instrumentation đúng nghĩa là phân loại **lỗi entry point**, **lỗi class transform/definition** và **lỗi method linkage/execution**. `premain` thất bại có thể ngăn JVM vào application main; `agentmain` dynamic attach thất bại không abort target theo hợp đồng; transformer throw có thể bị bỏ qua; bytes malformed có thể bị từ chối trước định nghĩa; còn bytes hợp lệ đã cài vẫn có thể thất bại ở invocation. Chỉ khi xác định chính xác pha và bằng chứng, bạn mới chọn được cách sửa hoặc rollback.

### Tài liệu chính thức

- [Java SE 17 — java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, `agentmain`, `Launcher-Agent-Class`, manifest và semantics lỗi startup.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback, return `null`, unchecked exceptions, transformer chain.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): registration, class retransform/redefine, capability checks.
- [JDK 17 — Attach API VirtualMachine](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): `loadAgent`, agent initialization, attach/detach.
- [JDK 17 — AgentInitializationException](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/AgentInitializationException.html): lỗi nạp/khởi tạo ở target JVM.
- [JEP 451 — Prepare to Disallow Dynamic Loading of Agents](https://openjdk.org/jeps/451): warnings và HotSpot opt-in khi dynamic loading.
- [JVMS Java SE 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): định dạng classfile, verifier constraints.
- [JVMS Java SE 17 — Loading, Linking, Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): verification, resolution và linkage timing.
