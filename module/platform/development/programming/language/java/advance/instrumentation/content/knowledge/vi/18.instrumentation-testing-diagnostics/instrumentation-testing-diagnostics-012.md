# Ghi ma trận JDK, JVM, cách khởi động và khả năng được hỗ trợ

Java Instrumentation không nên được mô tả bằng câu “agent này chạy trên mọi Java”. Một Java agent có thể **khởi động thành công** nhưng **không được cấp quyền retransform**, **không thể sửa một class cụ thể**, hoặc **không thể attach vào JVM đang chạy**. Ngược lại, một JVM hỗ trợ ba capability về lý thuyết chưa chắc đã cấp cả ba cho **agent JAR đang được nạp**, nếu manifest không yêu cầu chúng.

Vì vậy, khi kiểm thử và chẩn đoán Java agent, cần lập một **ma trận thực nghiệm (compatibility/capability matrix)** với ít nhất bốn trục:

1. **JDK/JRE và bản phân phối**: phiên bản thực thi, nhà cung cấp, kiến trúc, hệ điều hành và cấu hình Java runtime.
2. **JVM implementation**: tên/phiên bản VM như HotSpot/OpenJDK Server VM hoặc một VM khác; không suy luận implementation chỉ từ từ “JDK”.
3. **Cách khởi động agent và ứng dụng**: `-javaagent` với `-cp`, `-jar`, `--module`; `Launcher-Agent-Class`; nạp agent động bằng Attach API.
4. **Khả năng thực tế được cấp**: `Instrumentation.isRedefineClassesSupported()`, `isRetransformClassesSupported()`, `isNativeMethodPrefixSupported()`, `isModifiableClass(...)`, `isModifiableModule(...)`, tình trạng thành công/thất bại khi gọi API cụ thể.

**Mục tiêu bài học:** tạo được bảng có bằng chứng **PASS / FAIL / BLOCKED / NOT_TESTED**, chứ không điền “Supported” theo phỏng đoán; biết đặt lại cùng testcase trên các JDK/JVM khác nhau và tách rõ **launch support**, **manifest capability**, **class/module eligibility**, **operation success**.

Bài thực hành Java 17+ ở dưới sử dụng **cùng mã agent** cho nhiều phương thức khởi động, ghi lại ba capability và điều kiện sửa class/module. Đã kiểm thử thực tế trên **Zulu OpenJDK 24.0.2 (OpenJDK 64-Bit Server VM, VM vendor Azul Systems, Inc.)** với **bảy kịch bản**, bao gồm dynamic attach được cho phép hoặc bị chặn.

## 1. Vì sao phải có ma trận thay vì danh sách “Java 17: có, Java 21: có”?

Một hàng “JDK 21 / supported” che mất rất nhiều biến quan trọng:

- `java -javaagent:agent.jar -cp ...` gọi `premain` **trước application `main`**.
- `java -javaagent:agent.jar -jar app.jar` vẫn dùng **`Premain-Class`** của agent JAR; `-jar` không tự đổi thành `agentmain`.
- `java -javaagent:agent.jar --module app.module/...` vẫn là **startup agent**, nhưng code ứng dụng ở **named module**, ảnh hưởng khả năng truy cập package/module khi instrumentation.
- `java -jar executable-with-launcher-agent.jar` với **`Launcher-Agent-Class`** gọi **`agentmain` trước `main`**, dù đây là agent được khởi động cùng JVM, **không phải attach động**.
- Nạp vào JVM đang chạy qua Attach API cần **`Agent-Class`** và cơ chế attach/dynamic loading được **implementation, môi trường và chính sách** cho phép.
- Hai agent JAR giống bytecode nhưng khác **`Can-Retransform-Classes`** có thể trả hai giá trị `isRetransformClassesSupported()` khác nhau **trên cùng JVM**.
- `isModifiableClass(target) == true` **không đồng nghĩa** `isRedefineClassesSupported() == true`, cũng không bảo đảm phép redefine với bộ bytes bất kỳ thành công.

Vì vậy ma trận cần lưu đủ điều kiện đầu vào, các phép kiểm tra **ở runtime** và lỗi/đầu ra quan sát được.

## 2. Phân biệt JDK, runtime, JVM, vendor và chế độ nạp

| Thuật ngữ | Ý nghĩa cần lưu |
|---|---|
| **JDK release** | Ví dụ Java 17, 21, 24; ghi đầy đủ version/build từ `java -version` |
| **JDK vendor/distribution** | Ví dụ Oracle JDK, Eclipse Temurin, Azul Zulu; phải lấy từ bản chạy thật |
| **JVM implementation** | Giá trị `java.vm.name`, `java.vm.vendor`, `java.vm.version` |
| **Runtime configuration** | Architecture, OS, cgroup/CPU limits, JVM flags, security/attach policy |
| **Agent entrypoint** | `premain` hoặc `agentmain` được gọi thật, không suy từ tên JAR |
| **Application launcher** | `-cp`, `-jar`, `--module` và `Launcher-Agent-Class` |
| **Agent loader/target loader** | Class loader định nghĩa agent/target; rất quan trọng khi transform nhiều module hoặc plugin loaders |
| **Agent capability configuration** | Ba cờ `Can-*` trong manifest cộng với kết quả ba API `is*Supported()` |
| **Target eligibility** | `isModifiableClass(clazz)` / `isModifiableModule(module)` cho **đối tượng cụ thể** |
| **Observed result** | Agent load, callback được gọi, operation thành công/thất bại, lỗi và log |

**Không đồng nhất vendor của JDK với implementation của VM.** Một vendor có thể cung cấp bản phân phối dùng VM thuộc nhiều họ; các flags như `-XX:+EnableDynamicAgentLoading` là **implementation-specific**, không phải portable Java language options cho mọi VM.

**Không đồng nhất “có JDK” với “có Attach API được phép sử dụng”.** Vào Java 9+, Attach API nằm trong module **`jdk.attach`**; một runtime image bị rút gọn có thể không chứa module đó. Attach còn phụ thuộc OS/process permissions, PID namespace/container, chính sách JVM và việc target có cho phép dynamic agent loading hay không.

## 3. Mẫu ma trận nên dùng trong kiểm thử

Một mẫu hàng lưu dữ liệu rõ ràng:

| Cột | Ví dụ hoặc nguyên tắc |
|---|---|
| `run_id` | ID duy nhất để truy vết log |
| `timestamp_utc` | Thời điểm chạy, chuẩn UTC |
| `host_os_arch` | OS, architecture, CPU/container info |
| `java_home` | Đường dẫn Java runtime thực tế |
| `java_version` | Full version từ JVM đang chạy |
| `java_vendor` | `java.vendor` |
| `java_vm_name` | `java.vm.name` |
| `java_vm_vendor` | `java.vm.vendor` |
| `java_vm_version` | `java.vm.version` |
| `application_artifact` | Tên/hash của cùng app JAR |
| `agent_artifact` | Tên/hash agent JAR, entrypoints, `Can-*` |
| `launch_mode` | `classpath`, `jar`, `module`, `launcher`, `attach` |
| `command` | Câu lệnh đầy đủ đã sử dụng |
| `attach_policy` | Không áp dụng / allowed / denied / unknown |
| `agent_entry` | `premain`, `agentmain` hoặc **not invoked** |
| `redefine` | true / false / not observable |
| `retransform` | true / false / not observable |
| `native_prefix` | true / false / not observable |
| `class_modifiable` | true / false / không kiểm tra |
| `module_modifiable` | true / false / không kiểm tra |
| `operation_result` | PASS / FAIL / BLOCKED / NOT_TESTED |
| `evidence` | Exit code, stdout/stderr, error class, JFR/log location |

**Một dòng ma trận đại diện một tổ hợp điều kiện đã chạy**, không phải mọi phiên bản JDK có thể có. Nếu chưa chạy OpenJ9 hoặc một bản JDK khác, để **NOT_TESTED**, không tự điền theo kết quả HotSpot.

Dùng trạng thái tách biệt:

- **PASS:** thao tác/kết quả được kiểm chứng đúng trong môi trường ghi.
- **FAIL:** testcase chạy được nhưng không đạt kỳ vọng; cần kèm lỗi và expected/actual.
- **BLOCKED:** chính sách/môi trường không cho phép thực hiện testcase, ví dụ dynamic agent loading bị chặn; không kết luận API instrumentation bên trong JVM là thiếu.
- **NOT_TESTED:** chưa có thực nghiệm; không điền “không hỗ trợ”.
- **N/A:** trường không có ý nghĩa cho kịch bản, ví dụ `isRetransformClassesSupported` không thể hỏi khi agent chưa nạp thành công.

Với kiểm thử mang tính pháp chứng, nên ghi cả `java -version`, manifest của JAR thực tế, SHA-256 của app/agent, JVM command line, flags, PID và logs tương ứng.

## 4. Ba capability chính: manifest yêu cầu nhưng runtime quyết định

Ba API của `Instrumentation`:

~~~java
boolean redefine = inst.isRedefineClassesSupported();
boolean retransform = inst.isRetransformClassesSupported();
boolean nativePrefix = inst.isNativeMethodPrefixSupported();
~~~

Trong đó `inst` được JVM cung cấp cho agent. **Cả ba đều không được tạo bằng `new Instrumentation()`**.

| Manifest attribute | API kiểm tra | Công việc liên quan |
|---|---|---|
| `Can-Redefine-Classes: true` | `isRedefineClassesSupported()` | Thay định nghĩa class đã load qua `redefineClasses` |
| `Can-Retransform-Classes: true` | `isRetransformClassesSupported()` | Gọi lại transformer capable qua `retransformClasses` |
| `Can-Set-Native-Method-Prefix: true` | `isNativeMethodPrefixSupported()` | Native JNI name resolution fallback của transformer |

Cả ba thuộc tính **không bắt buộc** và **mặc định false** nếu bị bỏ khỏi agent manifest. Một manifest `true` chỉ có ý nghĩa “**agent yêu cầu**”, JVM còn phải hỗ trợ. Không có một cờ chung `Can-Instrument-Everything`.

Ví dụ manifest yêu cầu cả ba:

~~~text
Manifest-Version: 1.0
Premain-Class: agent.MatrixAgent
Agent-Class: agent.MatrixAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
Can-Set-Native-Method-Prefix: true

~~~

Đặc tả còn nói rằng giá trị của capability booleans không phân biệt hoa/thường; các giá trị khác `true` được hiểu như `false`.

**Ngược lại**, agent JAR thiếu ba dòng `Can-*` vẫn có thể:

- Được JVM nạp qua `-javaagent`.
- Đăng ký `ClassFileTransformer` **không capable** để biến đổi class khi load ban đầu.
- Gọi một số API quan sát hoặc chỉnh module khi có điều kiện phù hợp.

Nhưng các API `is*Supported()` tương ứng vẫn có thể trả false dù JVM implementation về nguyên tắc hỗ trợ các capability đó.

## 5. `isModifiableClass` khác hoàn toàn capability đã yêu cầu

Kiểm tra:

~~~java
Class<?> target = Class.forName(
        "lab.Target", false, ClassLoader.getSystemClassLoader());

boolean modifiable = inst.isModifiableClass(target);
System.out.println(modifiable);
~~~

Đây là fragment chạy bên trong agent, giả định app có `lab.Target` trong system loader.

`isModifiableClass(target)` hỏi **class cụ thể có thể sửa** bằng cơ chế redefine/retransform phù hợp hay không; không đồng nghĩa agent đã xin/có capability tương ứng. Trên một JVM HotSpot, có thể quan sát:

~~~text
REDEFINE=false
RETRANSFORM=false
NATIVE_PREFIX=false
TARGET_MODIFIABLE=true
~~~

Đó là kết quả **không mâu thuẫn**. JVM có khả năng hỗ trợ sửa target class về mặt cấu trúc, nhưng agent hiện tại không được cấp quyền redefine/retransform vì manifest không yêu cầu.

Ngoài ra:

- Primitive hoặc array classes không modifiable theo `Instrumentation`.
- Có những class đặc biệt bị JVM từ chối sửa.
- `isModifiableClass==true` **không bảo đảm bộ bytes mới hợp lệ**; thao tác có thể lỗi do class format, schema, verifier hoặc các giới hạn JVM TI.
- Việc truyền `Class<?>` đúng loader quan trọng. Hai class cùng binary name nhưng khác defining loader là **hai class khác nhau**.
- Đừng lấy `isModifiableClass` làm bằng chứng thao tác retransform đã chạy; muốn chứng minh phải gọi thật và kiểm tra kết quả khi testcase yêu cầu.

Tương tự, với Java 9+:

~~~java
boolean modifiableModule =
        inst.isModifiableModule(Object.class.getModule());
~~~

Đây là phép kiểm tra **module `java.base` cụ thể**. `true` chỉ nói module này cho phép chỉnh runtime relationships qua `redefineModule`, **không** tự mở/export mọi package, và không nói class nào trong module đó cũng có thể sửa tùy ý.

## 6. Cách khởi động agent: chọn entrypoint chính xác

### 6.1. Startup agent qua `-javaagent`

Cú pháp:

~~~text
-javaagent:<agent-jar>[=<agent-options>]
~~~

Trong agent JAR cần **`Premain-Class`** và method:

~~~java
public static void premain(String agentArgs, Instrumentation inst) {
    // Được gọi trước application main.
}
~~~

JVM có thể chấp nhận overload chỉ có `String`; ở bài này dùng overload hai tham số để nhận `Instrumentation`.

**Ví dụ khởi động app bằng classpath:**

~~~bash
java -javaagent:agent-all.jar=from-cp -cp app.jar lab.MatrixApp
~~~

**Ví dụ ứng dụng executable JAR:**

~~~bash
java -javaagent:agent-all.jar=from-jar -jar app.jar
~~~

**Ví dụ named module:**

~~~bash
java -javaagent:agent-all.jar=from-module \
     --module-path out/mods --module lab.app/lab.MatrixApp
~~~

Cả ba đều gọi **`premain`**, không phải `agentmain`, vì điều kiện chọn callback là **cách nạp agent** (`-javaagent`), không phải cách gọi `main`.

Nếu khai báo nhiều `-javaagent`, JVM gọi `premain` theo **thứ tự các tùy chọn** trên command line. Thứ tự này có thể làm khác chuỗi `ClassFileTransformer`, nên khi lập ma trận cần lưu **thứ tự agent JARs**, không chỉ tập tên.

Agent `premain` ném lỗi không được xử lý có thể làm JVM **abort startup** trước `main`; ghi rõ exit code và stderr, không ghi nhầm thành “capability false”.

### 6.2. Executable JAR có `Launcher-Agent-Class`

Manifest trong **chính executable app JAR**:

~~~text
Manifest-Version: 1.0
Main-Class: lab.MatrixApp
Launcher-Agent-Class: agent.MatrixAgent

~~~

Chạy:

~~~bash
java -jar launcher.jar
~~~

Đặc tả `java.lang.instrument` quy định class ở `Launcher-Agent-Class` được gọi bằng **`agentmain` trước application `main`**, với `agentArgs` là **chuỗi rỗng**. Nó là một **startup mechanism**, **không phải dynamic attach** chỉ vì tên callback là `agentmain`.

**Khác biệt với external `-javaagent`:**

| Trường hợp | Manifest cần đọc | Callback |
|---|---|---|
| `java -javaagent:agent.jar -jar app.jar` | `Premain-Class` trong `agent.jar` | `premain` |
| `java -jar launcher.jar` có `Launcher-Agent-Class` | `Launcher-Agent-Class` trong `launcher.jar` | **`agentmain` trước `main`** |
| Attach agent JAR sau khi app đã chạy | `Agent-Class` trong agent JAR | **`agentmain` sau startup** |

Đừng nhầm `Launcher-Agent-Class` với `Agent-Class` khi điền ma trận. Hai cơ chế gọi cùng tên method `agentmain` nhưng thời điểm, cách khởi động và yêu cầu môi trường khác nhau.

### 6.3. Nạp agent động vào JVM đang chạy

Nếu JVM hỗ trợ, có thể dùng `com.sun.tools.attach.VirtualMachine` hoặc công cụ phù hợp:

~~~java
VirtualMachine vm = VirtualMachine.attach(pid);
try {
    vm.loadAgent(pathToAgentJar, "some-options");
} finally {
    vm.detach();
}
~~~

Đây là fragment; phải import `com.sun.tools.attach.VirtualMachine`, cung cấp PID và JAR đúng.

Agent JAR cần `Agent-Class`, class có method:

~~~java
public static void agentmain(String agentArgs, Instrumentation inst) {
    // Nạp muộn vào JVM đang chạy.
}
~~~

Dynamic attach **không đảm bảo** sửa được mọi class đã tải: có thể cần `Can-Retransform-Classes` hoặc `Can-Redefine-Classes`, và class cụ thể phải modifiable. Attach thành công chỉ xác nhận **agent được nạp** và `agentmain` chạy; muốn chứng minh đã transform class đang chạy, cần testcase thực hiện và xác minh tiếp.

**Giới hạn môi trường:** Có bản runtime image không có `jdk.attach`; quyền OS hoặc container PID namespace ngăn attach; HotSpot có cờ `-XX:+/-EnableDynamicAgentLoading`; security policy có thể chặn attach. Đừng ghi “JDK 21 always attachable”.

## 7. JEP 451 và chính sách dynamic agent loading

**JEP 451**, được đưa vào JDK 21, hướng tới **cảnh báo** việc nạp agent động và chuẩn bị cho thay đổi chính sách mặc định trong một phiên bản tương lai. Các điểm cần nhớ:

- **Startup `-javaagent` không đồng nghĩa dynamic attach.** Cảnh báo dynamic loading không phải lý do để cho rằng `-javaagent` startup không hỗ trợ.
- Trong HotSpot, `-XX:+EnableDynamicAgentLoading` dùng để **cho phép nạp agent động** và thể hiện opt-in rõ ràng; với các bản có cảnh báo, nó cũng có thể làm mất warning.
- `-XX:-EnableDynamicAgentLoading` dùng để **chặn dynamic loading** và kiểm thử đường lỗi.
- **Không đồng nhất khả năng attach tới PID với khả năng load agent.** Một client có thể lấy `VirtualMachine` attach được nhưng lời gọi `loadAgent` vẫn bị từ chối.
- Giá trị mặc định/chính sách và text warning phụ thuộc **version + VM implementation + cấu hình deploy**, phải đo ở runtime. **Không suy rằng mọi JDK sau 21 đều đã chặn mặc định**, hoặc sẽ chặn ở một ngày phát hành cố định, nếu chưa kiểm chứng chính JDK đó.

Trong bảng thử nghiệm, nên có **hai cột riêng**:

~~~text
attach_api_connection = SUCCESS / FAIL / NOT_TESTED
dynamic_agent_load    = SUCCESS / BLOCKED / FAIL / NOT_TESTED
~~~

Nếu `loadAgent` bị từ chối vì `-XX:-EnableDynamicAgentLoading`, không được kết luận ba capability `redefine/retransform/nativePrefix` là false; **đã không có đối tượng `Instrumentation` để hỏi**.

## 8. Chọn tổ hợp ma trận có giá trị kiểm thử

Thay vì kiểm mọi tổ hợp hàng nghìn biến, hãy bắt đầu bằng các case tiêu biểu:

| Case | JVM | Launcher | Agent manifest | Điều cần chứng minh |
|---|---|---|---|---|
| C1 | JDK mục tiêu | `-javaagent` + `-cp` | all `Can-* = true` | `premain`, ba API capability |
| C2 | Cùng JVM | `-javaagent` + `-jar` | all true | `premain`, executable app chạy |
| C3 | Cùng JVM | `-javaagent` + `--module` | all true | `premain`, named module target |
| C4 | Cùng JVM | `-javaagent` + `-cp` | ba cờ **vắng** | ba API capability thường false |
| C5 | Cùng JVM | `-jar` + `Launcher-Agent-Class` | all true | `agentmain` trước `main`, args rỗng |
| C6 | Cùng JVM | dynamic Attach API, opt-in | all true | `agentmain` trong JVM đang chạy |
| C7 | Cùng JVM | dynamic Attach API, opt-out | all true | load agent bị chặn, phân biệt attach |
| C8 | JDK/vendor/JVM khác | Lặp C1–C7 | Giữ JAR, source tương thích | Chỉ ghi thực nghiệm mới |
| C9 | Custom loader/module | Target thuộc loader/layer riêng | Phù hợp agent | Class/modifiable và access thực |

Đặc biệt, **C4 là negative control quan trọng**: cùng VM có thể trả `isModifiableClass(target)=true` nhưng ba capability `false` vì manifest không yêu cầu. Tách biệt **implementation support** và **agent-granted support**.

**Trạng thái trước khi chạy:** C8/C9 phải là **NOT_TESTED**, không dùng kết quả của C1–C7 để điền “PASS” cho một JVM khác.

## 9. Ví dụ Java 17+ hoàn chỉnh: `MatrixAgent` ghi runtime capabilities

Thí nghiệm gồm một **Java agent dùng được cả `premain` và `agentmain`**, app JAR độc lập, executable JAR có `Launcher-Agent-Class`, named module và một test harness Attach API.

Cấu trúc thư mục:

~~~text
instrumentation-matrix/
├── src/
│   ├── agent/agent/MatrixAgent.java
│   ├── app/lab/Target.java
│   ├── app/lab/MatrixApp.java
│   ├── app/lab/TargetWait.java
│   ├── attach/AttachHarness.java
│   └── module/module-info.java
├── APP.MF
├── AGENT-ALL.MF
├── AGENT-OFF.MF
├── LAUNCHER.MF
└── out/
    ├── app/
    ├── agent/
    ├── attach/
    └── mods/lab.app/
~~~

Ví dụ **không gọi `redefineClasses` hoặc `retransformClasses` lên một target class**. Nó kiểm tra support + eligibility và bảo đảm entrypoint; muốn chấm `operation_success` phải có testcase riêng. Nhờ vậy dễ phân biệt cấp capability với chính hành động biến đổi class.

### 9.1. `src/agent/agent/MatrixAgent.java`

~~~java
package agent;

import java.lang.instrument.Instrumentation;

public final class MatrixAgent {
    public static void premain(String args, Instrumentation inst) {
        report("premain", args, inst);
    }

    public static void agentmain(String args, Instrumentation inst) {
        report("agentmain", args, inst);
    }

    private static void report(
            String entry, String args, Instrumentation inst) {
        System.out.println("ENTRY=" + entry);
        System.out.println("ARGS=" + args);
        System.out.println("JDK="
                + System.getProperty("java.version"));
        System.out.println("VM="
                + System.getProperty("java.vm.name"));
        System.out.println("VM_VENDOR="
                + System.getProperty("java.vm.vendor"));

        System.out.println("REDEFINE="
                + inst.isRedefineClassesSupported());
        System.out.println("RETRANSFORM="
                + inst.isRetransformClassesSupported());
        System.out.println("NATIVE_PREFIX="
                + inst.isNativeMethodPrefixSupported());

        try {
            Class<?> target = Class.forName(
                    "lab.Target",
                    false,
                    ClassLoader.getSystemClassLoader());
            System.out.println("TARGET_MODIFIABLE="
                    + inst.isModifiableClass(target));
            System.out.println("TARGET_LOADER="
                    + target.getClassLoader()
                            .getClass().getSimpleName());
        } catch (Exception exception) {
            System.out.println("TARGET_LOOKUP="
                    + exception.getClass().getSimpleName());
        }

        System.out.println("JAVA_BASE_MODULE_MODIFIABLE="
                + inst.isModifiableModule(
                        Object.class.getModule()));
    }
}
~~~

**Giải thích:**

1. **Cùng class có cả hai entrypoints**, nên phép thử xác định rõ JVM gọi `premain` hay `agentmain`.
2. Các system properties `java.version`, `java.vm.name`, `java.vm.vendor` giúp ghi **runtime thực** thay vì dựa vào tên file JAR.
3. Ba API `is*Supported()` được hỏi ngay trong callback agent.
4. `Class.forName(..., false, systemLoader)` chọn **class mục tiêu `lab.Target`**, không chạy static initializer của class ấy chỉ vì tra class object. Trong demo classpath/named-module với system loader, class có sẵn. Production dùng loader thích hợp.
5. `isModifiableClass(target)` kiểm tra **target**, không suy từ capability.
6. `Object.class.getModule()` lấy `java.base` (named module trên JDK 17+), để kiểm tra `isModifiableModule`.
7. `TARGET_LOADER=AppClassLoader` là **tên lớp loader được ghi trên runtime đã thử**; tên loader cụ thể không phải API portable để assert trên mọi JVM.
8. Đây là **probe thu thập khả năng**, không phải bằng chứng `redefineClasses` đã áp dụng thành công.

Khi ghi vào ma trận production, có thể bổ sung `System.getProperty("java.runtime.version")`, `java.vm.version`, `java.vendor`, `os.name`, `os.arch`, `java.home` và các VM input arguments. Nhưng đừng in **secrets** trong `-D...` flags hoặc environment ra log không kiểm soát.

### 9.2. `src/app/lab/Target.java`

~~~java
package lab;

public final class Target {
    public static String work() {
        return "ok";
    }
}
~~~

Class mục tiêu đơn giản, không có giới hạn đặc biệt. API `isModifiableClass` trong ví dụ nhận đúng đối tượng `Class<?>` của `lab.Target`.

### 9.3. `src/app/lab/MatrixApp.java`

~~~java
package lab;

public final class MatrixApp {
    public static void main(String[] args) {
        System.out.println("MAIN=" + Target.work());
    }
}
~~~

`MAIN=ok` giúp kiểm tra application `main` đã chạy, sau callback `premain` hoặc `agentmain` startup. Nếu `agentmain` được attach động vào một process đã chạy, thứ tự callback phụ thuộc thời điểm attach và **không thể giả định agent chạy trước application main**.

### 9.4. `src/app/lab/TargetWait.java`

~~~java
package lab;

import java.io.BufferedReader;
import java.io.InputStreamReader;

public final class TargetWait {
    public static void main(String[] args) throws Exception {
        System.out.println("TARGET_READY");
        new BufferedReader(
                new InputStreamReader(System.in)).readLine();
        System.out.println("TARGET_DONE");
    }
}
~~~

Process này chỉ **in `TARGET_READY` rồi đợi một dòng stdin**. Nó giúp `AttachHarness` điều khiển chính xác khi nào thử attach, không phải chờ `Thread.sleep` và hy vọng process vẫn còn sống.

### 9.5. `src/module/module-info.java`

~~~java
module lab.app {
    exports lab;
}
~~~

Named module `lab.app` cho phép lệnh `--module lab.app/lab.MatrixApp`. Trong demo, class target được system/application loader nạp. Với real-world modules, có thể cần bổ sung read edges/exports/opens riêng cho việc instrument code trong package. **Capability=true không tự cấp mọi quyền truy cập module**.

## 10. Attach API harness: tự tạo process đích và nạp agent

File `src/attach/AttachHarness.java`:

~~~java
import com.sun.tools.attach.VirtualMachine;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.file.Path;
import java.io.OutputStreamWriter;

public final class AttachHarness {
    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "args: mode appJar agentJar");
        }

        String javaBin = Path.of(
                System.getProperty("java.home"),
                "bin",
                System.getProperty("os.name")
                        .toLowerCase().contains("win")
                        ? "java.exe" : "java").toString();

        String mode = args[0];
        String appJar = args[1];
        String agentJar = args[2];
        String flag = mode.equals("allow")
                ? "-XX:+EnableDynamicAgentLoading"
                : "-XX:-EnableDynamicAgentLoading";

        Process target = new ProcessBuilder(
                javaBin, flag, "-cp", appJar, "lab.TargetWait")
                .redirectErrorStream(true)
                .start();

        BufferedReader output = new BufferedReader(
                new InputStreamReader(target.getInputStream()));
        System.out.println("CASE=" + mode);

        try {
            String ready = output.readLine();
            System.out.println(ready);

            VirtualMachine vm = VirtualMachine.attach(
                    Long.toString(target.pid()));
            try {
                vm.loadAgent(agentJar, "from-attach");
                System.out.println("ATTACH=success");
            } catch (Exception error) {
                System.out.println("ATTACH_ERROR="
                        + error.getClass().getSimpleName());
            } finally {
                vm.detach();
            }
        } finally {
            OutputStreamWriter writer =
                    new OutputStreamWriter(target.getOutputStream());
            writer.write("\n");
            writer.flush();

            for (String line;
                    (line = output.readLine()) != null; ) {
                System.out.println("TARGET_OUT=" + line);
            }
            target.waitFor();
            System.out.println("TARGET_EXIT="
                    + target.exitValue());
        }
    }
}
~~~

**Đây là mã test sử dụng HotSpot option**, không phải một API portable cho mọi JVM. Khi chạy trên JVM khác thiếu flags `-XX:+/-EnableDynamicAgentLoading`, cần thay cách cài chính sách hoặc ghi `BLOCKED`/`NOT_TESTED`, **không gọi đó là lỗi của Java Instrumentation chung**.

Giải thích:

1. `ProcessBuilder` tạo một **JVM mới** có cùng `java.home` với harness.
2. Target `TargetWait` in `TARGET_READY` để harness biết process đã bắt đầu.
3. Harness dùng `VirtualMachine.attach(pid)` từ module `jdk.attach` để kết nối target.
4. `vm.loadAgent(agentJar, "from-attach")` yêu cầu nạp agent JAR. **`Agent-Class`** được đọc và `agentmain` được gọi nếu thành công.
5. `-XX:+EnableDynamicAgentLoading` cho phép đường success trên HotSpot được thử; flag âm ngăn nạp agent trong case bị chặn.
6. `vm.detach()` hoàn tất kết nối. Sau đó harness gửi newline để target thoát và đọc output.
7. Khi `loadAgent` ném exception, in tên class lỗi **nhưng không mặc định target JVM bị crash**.
8. Script demo không có **timeout/forced destroy** cho process treo. Khi biến nó thành test CI, cần bổ sung timeout, kill/cleanup và ghi PID/exit code.

**Hai tình huống lỗi rất khác nhau**:

- Không attach được tới PID (`VirtualMachine.attach` lỗi): xem permission, module `jdk.attach`, process ownership, container policy.
- Attach thành công nhưng `loadAgent` bị chặn (`AgentLoadException` trong case kiểm thử): JVM không cho phép **dynamic agent load**. Không suy đoán ba capability bên trong agent vì `agentmain` chưa được gọi.

## 11. Bốn manifest để kiểm chứng đúng lifecycle

`APP.MF` — executable app JAR thông thường:

~~~text
Manifest-Version: 1.0
Main-Class: lab.MatrixApp

~~~

`AGENT-ALL.MF` — external agent yêu cầu cả ba:

~~~text
Manifest-Version: 1.0
Premain-Class: agent.MatrixAgent
Agent-Class: agent.MatrixAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
Can-Set-Native-Method-Prefix: true

~~~

`AGENT-OFF.MF` — cùng bytecode agent, **không yêu cầu** ba capability:

~~~text
Manifest-Version: 1.0
Premain-Class: agent.MatrixAgent
Agent-Class: agent.MatrixAgent

~~~

`LAUNCHER.MF` — agent đóng chung trong executable JAR:

~~~text
Manifest-Version: 1.0
Main-Class: lab.MatrixApp
Launcher-Agent-Class: agent.MatrixAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
Can-Set-Native-Method-Prefix: true

~~~

Mỗi manifest phải có **dòng trống kết thúc**. Không nhầm:

- `Premain-Class`: agent nạp từ **`-javaagent`** ở JVM startup.
- `Agent-Class`: agent nạp **vào JVM đã chạy**.
- `Launcher-Agent-Class`: agent nằm **trong executable JAR**, được khởi động trước app `main` qua `agentmain`.
- `Main-Class`: class ứng dụng chính được launcher gọi.

Không cần đổi bytecode của `MatrixAgent` để thay `Can-*`. Dùng hai JAR có **cùng class files nhưng manifest khác**, nhờ vậy test C1/C4 cô lập được ảnh hưởng của manifest.

## 12. Build bằng JDK 17+: app JAR, agent JAR và named module

Chạy từ thư mục `instrumentation-matrix`. Trên Bash/Git Bash:

~~~bash
mkdir -p out/app out/agent out/attach out/mods/lab.app
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force `
  out/app, out/agent, out/attach, out/mods/lab.app | Out-Null
~~~

Biên dịch app và agent:

~~~bash
javac --release 17 -d out/app \
  src/app/lab/Target.java \
  src/app/lab/MatrixApp.java \
  src/app/lab/TargetWait.java

javac --release 17 -d out/agent \
  src/agent/agent/MatrixAgent.java
~~~

Biên dịch Attach API harness (cần module `jdk.attach`):

~~~bash
javac --release 17 --add-modules jdk.attach \
  -d out/attach src/attach/AttachHarness.java
~~~

Biên dịch riêng ứng dụng thành named module:

~~~bash
javac --release 17 -d out/mods/lab.app \
  src/module/module-info.java \
  src/app/lab/Target.java \
  src/app/lab/MatrixApp.java
~~~

**Tạo các JAR:**

~~~bash
jar --create --file app.jar \
  --manifest APP.MF -C out/app .

jar --create --file agent-all.jar \
  --manifest AGENT-ALL.MF -C out/agent .

jar --create --file agent-off.jar \
  --manifest AGENT-OFF.MF -C out/agent .

jar --create --file launcher.jar \
  --manifest LAUNCHER.MF -C out/app . -C out/agent .
~~~

`app.jar` và `agent-all.jar` riêng biệt là mẫu startup phổ biến. `launcher.jar` là **một executable JAR chứa cả ứng dụng và `agent.MatrixAgent`**. Đừng giả định chỉ đặt `Launcher-Agent-Class` trong `app.jar` là đủ nếu class agent không có trong JAR/loader path được dùng.

**Kiểm tra manifest bên trong JAR thật** thay vì chỉ file nguồn `.MF`. Ví dụ dùng:

~~~bash
jar --describe-module --file app.jar
jar --list --file agent-all.jar
jar --list --file launcher.jar
~~~

`app.jar` là **JAR không khai báo module-info**, nên `jar --describe-module` có thể mô tả nó là automatic module; lệnh này không thay thế việc kiểm tra manifest. Có thể dùng công cụ ZIP/JAR phù hợp để mở `META-INF/MANIFEST.MF` hoặc kiểm tra bằng Java `java.util.jar.JarFile`.

**Lưu ý tính di động:** `--release 17` cho class files tương thích Java 17 trở lên, nhưng những JVM cũ hoặc native-image runtimes không nhất thiết chạy được mẫu này. Cần compile lại cho target release tương thích nếu ma trận có dòng Java 8, và khi đó `Module` API (`Object.class.getModule`) không tồn tại.

## 13. Chạy bộ case khởi động

### C1 — Startup `-javaagent` + classpath

~~~bash
java -javaagent:agent-all.jar=from-cp \
  -cp app.jar lab.MatrixApp
~~~

Quan sát trên Zulu OpenJDK 24.0.2:

~~~text
ENTRY=premain
ARGS=from-cp
JDK=24.0.2
VM=OpenJDK 64-Bit Server VM
VM_VENDOR=Azul Systems, Inc.
REDEFINE=true
RETRANSFORM=true
NATIVE_PREFIX=true
TARGET_MODIFIABLE=true
TARGET_LOADER=AppClassLoader
JAVA_BASE_MODULE_MODIFIABLE=true
MAIN=ok
~~~

### C2 — Startup `-javaagent` + `-jar`

~~~bash
java -javaagent:agent-all.jar=from-jar -jar app.jar
~~~

Kết quả cùng JVM: `ENTRY=premain`, `ARGS=from-jar`, ba capability `true`, target và `java.base` được báo modifiable, rồi `MAIN=ok`. **Không gọi `agentmain`** chỉ vì app được chạy bằng `-jar`.

### C3 — Startup `-javaagent` + named module

~~~bash
java -javaagent:agent-all.jar=from-module \
  --module-path out/mods --module lab.app/lab.MatrixApp
~~~

Đã kiểm chứng `ENTRY=premain`, `ARGS=from-module`, ba capability `true`, `TARGET_MODIFIABLE=true`, `JAVA_BASE_MODULE_MODIFIABLE=true`, `MAIN=ok`.

**Giới hạn diễn giải:** Điều này không chứng minh agent có thể reflect vào mọi package riêng tư của named modules hoặc transformer có thể thêm method tùy ý. Để làm như vậy còn phải xét module exports/opens/reads và class-file constraints.

### C4 — Cùng JVM nhưng agent manifest **không có ba `Can-*`**

~~~bash
java -javaagent:agent-off.jar=from-off \
  -cp app.jar lab.MatrixApp
~~~

Stdout quan trọng:

~~~text
ENTRY=premain
ARGS=from-off
REDEFINE=false
RETRANSFORM=false
NATIVE_PREFIX=false
TARGET_MODIFIABLE=true
JAVA_BASE_MODULE_MODIFIABLE=true
MAIN=ok
~~~

**Case này xác minh sự khác nhau giữa capability được cấp và class eligibility.** Không nên đọc `TARGET_MODIFIABLE=true` rồi tự ghi cả `REDEFINE=true` và `RETRANSFORM=true`.

### C5 — `Launcher-Agent-Class` trong executable JAR

~~~bash
java -jar launcher.jar
~~~

Các dòng chính quan sát:

~~~text
ENTRY=agentmain
ARGS=
REDEFINE=true
RETRANSFORM=true
NATIVE_PREFIX=true
MAIN=ok
~~~

`ARGS=` là **chuỗi rỗng**, không phải literal `null`. `ENTRY=agentmain` xuất hiện **trước** `MAIN=ok`. Đây **không** phải attach động sau startup.

### C6 — Dynamic attach với opt-in trên HotSpot

~~~bash
java --add-modules jdk.attach \
  -cp out/attach AttachHarness allow app.jar agent-all.jar
~~~

Các dòng chính quan sát:

~~~text
CASE=allow
TARGET_READY
ATTACH=success
TARGET_OUT=ENTRY=agentmain
TARGET_OUT=ARGS=from-attach
TARGET_OUT=REDEFINE=true
TARGET_OUT=RETRANSFORM=true
TARGET_OUT=NATIVE_PREFIX=true
TARGET_OUT=TARGET_MODIFIABLE=true
TARGET_OUT=JAVA_BASE_MODULE_MODIFIABLE=true
TARGET_OUT=TARGET_DONE
TARGET_EXIT=0
~~~

Agent nạp **sau khi target in `TARGET_READY`**, nên đúng là dynamic attach. `VirtualMachine.attach`/`loadAgent` đã thành công; target tiếp tục chạy và kết thúc sạch.

### C7 — Dynamic attach bị từ chối

~~~bash
java --add-modules jdk.attach \
  -cp out/attach AttachHarness deny app.jar agent-all.jar
~~~

Các dòng chính quan sát:

~~~text
CASE=deny
TARGET_READY
ATTACH_ERROR=AgentLoadException
TARGET_OUT=TARGET_DONE
TARGET_EXIT=0
~~~

`-XX:-EnableDynamicAgentLoading` nằm ở **target JVM** của harness; Attach API kết nối có thể thực hiện, nhưng **nạp agent bị chặn**. Ở dòng này `ENTRY`, `REDEFINE`, `RETRANSFORM`, `NATIVE_PREFIX` đều **N/A** vì không có callback `agentmain`.

## 14. Ma trận quan sát thực nghiệm của ví dụ

**Môi trường đã thử thực tế:** Azul Zulu OpenJDK **24.0.2**, `java.vm.name=OpenJDK 64-Bit Server VM`, Windows, JDK 17 bytecode target (`javac --release 17`). Những thông tin này là **điều kiện của một máy thử**, không phải bản tuyên bố hỗ trợ mọi JVM.

| Case | Launch mode | Callback / tình trạng | Redefine | Retransform | Native prefix | Target modifiable | Kết quả |
|---|---|---|---|---|---|---|---|
| C1 | `-javaagent` + `-cp` | `premain` | true | true | true | true | **PASS** |
| C2 | `-javaagent` + `-jar` | `premain` | true | true | true | true | **PASS** |
| C3 | `-javaagent` + `--module` | `premain` | true | true | true | true | **PASS** |
| C4 | `-javaagent`, no `Can-*` | `premain` | **false** | **false** | **false** | true | **PASS** (negative control) |
| C5 | `Launcher-Agent-Class` + `-jar` | `agentmain` trước `main` | true | true | true | true | **PASS** |
| C6 | Attach + `EnableDynamicAgentLoading=+` | `agentmain` sau startup | true | true | true | true | **PASS** |
| C7 | Attach + `EnableDynamicAgentLoading=-` | `agentmain` **không chạy** | N/A | N/A | N/A | N/A | **BLOCKED** (`AgentLoadException`) |

Các case có callback thành công cũng quan sát `JAVA_BASE_MODULE_MODIFIABLE=true` trong environment này. Case C7 không thể kiểm tra module eligibility, vì agent không được nạp. `MAIN=ok` đã xác minh cho startup app (C1–C5); C6/C7 sử dụng target đợi stdin với dấu mốc `TARGET_READY`/`TARGET_DONE`.

**Không ngoại suy** từ bảng này sang JDK 17, 21, 25, 26 hoặc OpenJ9/GraalVM mà chưa chạy trên JVM tương ứng. Khi thử một JDK khác, hãy tạo **hàng dữ liệu mới** gồm vendor/build, command, manifest, kết quả capability và stderr đầy đủ.

**Điểm chính mà ma trận cho thấy:** trong cùng một VM HotSpot/OpenJDK, manifest có thể đổi kết quả capability; một phương thức startup khác có thể đổi callback; còn dynamic loading policy có thể chặn hoàn toàn trước khi bất kỳ capability nào được hỏi.

## 15. Bảng mở rộng nhiều JDK/JVM: ghi “chưa thử” đúng cách

Khi kiểm trên các runtime khác, dùng bảng như sau **trước khi có kết quả**:

| JDK/VM cần kiểm | `-javaagent` | `Launcher-Agent-Class` | Dynamic attach | Ba capability | Kết luận |
|---|---|---|---|---|---|
| JDK 17 HotSpot cụ thể | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | Chờ thực nghiệm |
| JDK 21 HotSpot cụ thể | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | Chờ thực nghiệm |
| JDK 24 Zulu OpenJDK 24.0.2 | PASS theo C1–C5 | PASS theo C5 | PASS/BLOCKED theo C6/C7 | Quan sát true/false theo manifest | Đã có bằng chứng môi trường nêu trên |
| JDK 25/26 runtime cụ thể | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | Chờ thực nghiệm |
| OpenJ9 bản phân phối cụ thể | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | Chờ thực nghiệm |
| Runtime image jlink/custom | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | Kiểm tra `java.instrument`, `jdk.attach` và options |
| Native-image runtime | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | Không tự xem là HotSpot JVM tương đương |

Ở các JDK mới hơn, chính sách dynamic agents và các launcher options có thể phát triển. Tài liệu Oracle/JEP chỉ là căn cứ cho **kỳ vọng và test plan**, không thay thế kết quả đã chạy của **version/build thực tế**.

Đối với Java 8: instrumentation startup đã có từ trước JPMS, nhưng ví dụ này dùng **Java 17 API** như `Module` và `ProcessHandle`; **không biên dịch/chạy trực tiếp trên Java 8**. Nếu cần kiểm Java 8, viết phiên bản probe riêng, chỉ hỏi những API có mặt ở release ấy, và để các trường module-related là **N/A**.

## 16. Thêm kiểm thử hoạt động thật sau capability probe

Ma trận ở trên cho biết **agent đã khởi động và các capability báo gì**. Muốn chứng minh thao tác Instrumentation thực sự hoạt động, cần testcase độc lập cho từng tính năng.

### 16.1. Class load transformation

Đăng ký một `ClassFileTransformer` **trước khi class đích được định nghĩa**. Cho transformer trả `byte[]` class file hợp lệ; kiểm tra hành vi class thay đổi. Đây là đường kiểm thử có thể không yêu cầu `Can-Redefine-Classes` hay `Can-Retransform-Classes`.

### 16.2. Retransform

~~~java
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(targetClass)) {
    inst.retransformClasses(targetClass);
}
~~~

Fragment này nằm trong agent có `Instrumentation inst`, `Class<?> targetClass`. Để testcase có ý nghĩa, cần transformer capable đăng ký bằng `addTransformer(t, true)` **và** kiểm tra được output/hành vi trước-sau. `isRetransformClassesSupported=true` **không chứng minh** một bộ bytes lỗi vẫn được JVM chấp nhận.

### 16.3. Redefine

~~~java
if (inst.isRedefineClassesSupported()
        && inst.isModifiableClass(targetClass)) {
    ClassDefinition definition =
            new ClassDefinition(targetClass, newClassBytes);
    inst.redefineClasses(definition);
}
~~~

Đây là **fragment**: cần import `java.lang.instrument.ClassDefinition`; `newClassBytes` phải là **class-file bytes hợp lệ** và tuân giới hạn schema. Với class đã tải, không thể giả định có thể thêm/xóa method/field hoặc đổi hierarchy tùy ý.

### 16.4. Native method prefix

~~~java
if (inst.isNativeMethodPrefixSupported()) {
    inst.addTransformer(transformer, false);
    inst.setNativeMethodPrefix(transformer, "$MyAgent$");
}
~~~

Đây là fragment với `transformer` do agent định nghĩa, chưa đăng ký trước. Prefix chỉ thay đổi **JNI native resolution fallback** khi cách tìm bình thường thất bại; không tự tạo Java wrapper hay native library. Muốn chấm `native_prefix_operation=PASS`, cần **JNI integration test thực sự**, không chỉ boolean capability.

### 16.5. Module instrumentation

~~~java
if (inst.isModifiableModule(targetModule)) {
    // Gọi redefineModule với extraReads/extraExports/
    // extraOpens/extraUses/extraProvides phù hợp.
}
~~~

Fragment này không thay module vì chưa gọi API. Để test thật cần tạo phép bổ sung read/exports/opens/uses/provides có thể kiểm tra, không thử trên module sản phẩm tùy ý nếu không có quyền.

**Ghi cột riêng** cho `capability_result` và `operation_result`. Đừng dùng một `PASS` chung cho cả hai.

## 17. Cách ghi thông tin môi trường đủ tái lập

Các lệnh hữu ích trên JDK 17+:

~~~bash
java -version
java --version
javac -version
jar --version
java --list-modules
~~~

`java -version` thường được hỗ trợ cả trên JDK cũ; `--version`, module-related options và công cụ `jar` tùy release/image. `java --list-modules` xác minh module `java.instrument` và `jdk.attach` có mặt ở runtime image được kiểm.

Lưu manifest của **agent JAR thực tế**:

~~~bash
jar --list --file agent-all.jar
~~~

`jar --list` chỉ kiểm tra **thành phần archive**, không in nội dung manifest. Dùng ZIP/JAR inspection hoặc `java.util.jar.JarFile` để xác nhận `Premain-Class`, `Agent-Class`, `Can-*`, `Launcher-Agent-Class` ở **`META-INF/MANIFEST.MF`**.

Chẩn đoán VM/proc (khi JDK có công cụ):

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
~~~

Đây là **cú pháp ví dụ**, không thể chạy nguyên xi với `<pid>`; thay bằng PID số thực và xác nhận process permissions. `jcmd` có thể không có trong runtime image bị cắt giảm và không luôn truy cập được process từ container khác.

Một dạng **bản ghi máy đọc được**:

~~~json
{
  "runId": "C1-2026-10-31T01:00:00Z",
  "javaVersion": "24.0.2",
  "vmName": "OpenJDK 64-Bit Server VM",
  "vmVendor": "Azul Systems, Inc.",
  "launch": "-javaagent + -cp",
  "agentManifest": "all-true",
  "entry": "premain",
  "redefine": true,
  "retransform": true,
  "nativePrefix": true,
  "targetModifiable": true,
  "javaBaseModuleModifiable": true,
  "operationTested": false,
  "status": "PASS",
  "evidence": "stdout and exit=0"
}
~~~

**`runId` và timestamp của JSON trên là minh họa cấu trúc, không phải timestamp thực của lần thử**; các trường capability/VM name là giá trị đã quan sát trên môi trường ví dụ. Trong CI, hãy cấp **thời gian thật tại lúc chạy**, giữ output raw và SHA của JAR.

### CSV có nên đủ?

CSV rất hữu ích để lọc/so sánh nhiều dòng. Nhưng các trường **JVM flags, list of agents, stderr stack trace, manifest contents** có thể dài hoặc nhiều dòng. Có thể lưu **một hàng CSV tóm tắt và một JSON/artifact log per run**, rồi link bằng `run_id`. Tránh nhét toàn bộ stack trace vào một ô kết quả khiến khó đọc và dễ mất quoting.

## 18. Các lỗi thường gặp khi điền ma trận

| Dấu hiệu | Diễn giải sai | Cách ghi đúng |
|---|---|---|
| `-javaagent` chạy thành công | “Redefine chắc chắn hỗ trợ” | Ghi `premain` thành công, hỏi riêng capability |
| `isModifiableClass=true`, `isRetransformClassesSupported=false` | “JVM mâu thuẫn” | Class eligibility khác agent capability |
| `Launcher-Agent-Class` gọi `agentmain` | “Đây là dynamic attach” | Đây là **startup**, gọi `agentmain` trước `main` |
| JAR chứa cả `Premain-Class` và `Agent-Class` | “JVM sẽ chạy cả hai callback” | Chỉ gọi entrypoint tương ứng cách nạp agent |
| Attach API kết nối được nhưng `loadAgent` lỗi | “JVM không có instrumentation” | Nạp động bị chặn hoặc lỗi agent; capabilities chưa quan sát |
| `AgentLoadException` với flag deny | “Cả ba capability false” | Ghi **BLOCKED**, capability **N/A** |
| `-XX:+EnableDynamicAgentLoading` hoạt động trên HotSpot | “Flag chạy trên mọi JVM” | Ghi implementation-specific |
| JDK 21 có JEP 451 warning | “JDK 21 cấm dynamic agents mặc định” | Phân biệt warning với denial; kiểm runtime/flags |
| Agent thiếu `Can-*` | “JVM implementation không hỗ trợ” | Có thể JVM hỗ trợ nhưng **agent không yêu cầu** |
| `isNativeMethodPrefixSupported=true` | “JNI method wrapper chạy được” | Cần integration test JNI thật |
| `-javaagent` trong app nhưng app chạy `--module` | “Agent nằm trong named module đó” | Agent class thường ở module/loader khác, kiểm thực tế |
| App dùng custom class loader | “System loader luôn tìm target” | Dùng đúng `Class<?>`/loader, ghi runtime identity |
| Test A build JDK khác B | “Kết quả khác do launch mode” | Giữ binary/JVM giống nhau, chỉ thay mode |
| Đọc manifest nguồn `.MF` nhưng đóng JAR sai | “Capability đã yêu cầu” | Inspect manifest **nằm trong agent JAR thực chạy** |
| JVM crash khi `premain` lỗi | “Class không modifiable” | Lỗi startup agent, phải đọc stderr/stack trace |
| Dùng `-jar` rồi thêm `-cp` tưởng có tác dụng | “Classpath bổ sung đã áp dụng” | `-jar` có quy tắc classpath riêng; kiểm launcher config |
| Dùng `--release 17` rồi thử Java 8 | “Java 8 không support Instrumentation” | Class-file version/API không tương thích, test riêng |
| Không chạy case ở OpenJ9 | “OpenJ9 không hỗ trợ” | Ghi NOT_TESTED |

**Một runtime matrix hữu ích là một bảng bằng chứng, không phải một bảng mong muốn.**

## 19. Checklist kiểm thử ma trận thực tế

1. **Chọn cụ thể các JVM/JDK build** cần hỗ trợ, không chỉ “Java 17+”.
2. **Ghi vendor, VM name/version**, OS/arch/container limits và `java.home`.
3. **Đóng gói app+agent đúng** và ghi SHA-256 của mỗi JAR.
4. **Kiểm manifest trong JAR**, không tin file `.MF` đang nằm cạnh source.
5. **Lặp startup modes**: `-javaagent` với classpath, executable jar, named module nếu sản phẩm dùng.
6. **Lặp `Launcher-Agent-Class`** nếu sản phẩm phân phối executable JAR có agent tích hợp.
7. **Lặp dynamic attach** với allowed/denied policy nếu sản phẩm cần nạp muộn; chạy trong môi trường được phép.
8. **Ghi chính xác callback** `premain`/`agentmain`, options string và thời điểm so với app `main`.
9. **Hỏi riêng ba `is*Supported`**, lưu true/false cùng manifest/cấu hình.
10. **Hỏi target-specific `isModifiableClass`**, ghi loader/module identity, không lấy class đại diện cho tất cả.
11. **Hỏi `isModifiableModule`** cho module thực sự phải sửa; không suy từ `java.base` sang mọi module.
12. **Chạy operation tests** cho redefine/retransform/prefix/module edits ở lớp thử an toàn, ghi lỗi/bytes output.
13. **Đánh dấu BLOCKED/N/A** khi nạp agent không được cho phép, không tự điền false.
14. **Ghi exit code và cả stderr**, tránh xem warning JEP 451 là failure nếu thao tác vẫn thành công.
15. **Lưu raw evidence** và lệnh chạy; khi môi trường thay đổi, chạy lại toàn bộ subset liên quan.
16. **Đặt supported policy**: PASS theo build/cấu hình đã thử, FAIL/BLOCKED có lý do, NOT_TESTED cần kế hoạch kiểm tiếp.
17. **So sánh với tài liệu chính thức**, nhưng coi runtime observations là cơ sở của hàng kết quả.
18. **Không thay đổi system/runtime policy trên máy production** chỉ để làm test pass; opt-in attach hoặc module opens cần được phê duyệt theo chính sách triển khai.

## 20. Tự kiểm tra kiến thức

1. **JDK vendor và JVM implementation có phải cùng một trường?** Không; ghi `java.vendor`/`java.vm.vendor` và `java.vm.name` riêng.
2. **`java -javaagent:agent.jar -jar app.jar` gọi method nào?** `premain`, theo `Premain-Class` trong agent JAR.
3. **`Launcher-Agent-Class` gọi method nào và khi nào?** `agentmain`, trước app `main` trong executable JAR startup.
4. **Dynamic attach dùng manifest nào?** `Agent-Class` cùng `agentmain`.
5. **Agent có cả `Premain-Class` và `Agent-Class`, JVM có gọi cả hai một lần không?** Không; chọn theo cách nạp.
6. **Một manifest không có `Can-Retransform-Classes` nhưng JVM có capability thì boolean trả gì?** `false` đối với cấu hình agent đó.
7. **`isModifiableClass(target)=true` chứng minh `redefineClasses` được phép không?** Không, cần capability riêng.
8. **Manifest all-true trên một JVM không hỗ trợ capability có buộc API trả true?** Không.
9. **Gọi `VirtualMachine.attach(pid)` thành công có chứng minh `loadAgent` được cho phép?** Không.
10. **Attach bị chặn trước `agentmain`: ba capability nên ghi gì?** `N/A`, không phải false.
11. **JEP 451 liên quan gì?** Warning và thay đổi chính sách dynamic agent loading, cần phân biệt startup với attach.
12. **`-XX:+EnableDynamicAgentLoading` có portable trên mọi JVM?** Không; đây là HotSpot implementation option.
13. **Một named module target có thể cần gì ngoài `isModifiableClass`?** Module readability/exports/opens và class-loader linkage khi injected code gọi helper.
14. **`isModifiableModule(java.base)=true` chứng minh mọi module khác modifiable?** Không.
15. **Vì sao không đánh dấu PASS toàn bộ OpenJ9 từ kết quả Zulu 24?** Khác VM build/implementation, phải test cụ thể.
16. **Tại sao cùng agent class, manifest khác có thể trả capability khác?** Vì booleans là khả năng agent yêu cầu và JVM cấp trong cấu hình.
17. **Ghi ma trận nên có trạng thái nào khi chưa chạy?** NOT_TESTED, không tự giả định FAIL.
18. **Ghi `status=PASS` sau capability probe có đồng nghĩa redefine thật đã hoạt động?** Không; operation test là một cột riêng.
19. **Vì sao cần SHA-256 của JAR?** Đảm bảo đúng artifact đã thử, phát hiện rebuild/manifest khác.
20. **Vì sao phải ghi nguyên command line?** Một option như `--module` hoặc `-XX:-EnableDynamicAgentLoading` có thể thay đổi entrypoint/chính sách và kết quả.
21. **Nếu chạy Java 8 với code dùng `Module`, lỗi có chứng minh Java 8 không có agent?** Không; code probe không tương thích API Java 8.
22. **Sự khác nhau giữa `BLOCKED` và `FAIL`?** BLOCKED là test không được thực hiện vì môi trường/chính sách; FAIL là testcase đã chạy nhưng không đạt kỳ vọng.
23. **`Launcher-Agent-Class` có tham số `agentArgs` nào trong demo?** Chuỗi rỗng.
24. **Nên kết luận gì từ C4?** Class modifiable có thể true khi cả ba capability đều false do manifest không yêu cầu.
25. **Muốn đo độ tương thích sản phẩm thực sự thì bổ sung gì?** Operation tests có hiệu ứng kiểm chứng được, trên các JDK/JVM, launch modes và policies đã định.

### Tài liệu chuẩn

- [Oracle Java SE 21 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Premain-Class`, `Agent-Class`, `Launcher-Agent-Class`, `Can-*` flags, cảnh báo dynamic loading và sự khác nhau giữa callback.
- [Oracle Java SE 21 — `Instrumentation` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): ba `is*Supported()`, `isModifiableClass`, `isModifiableModule`, `retransformClasses`, `redefineClasses`.
- [Oracle Java SE 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): cùng mô hình entrypoints trên Java 17.
- [Oracle Java SE 21 — JDK Attach API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): `attach`, `loadAgent`, `detach`, exceptions và constraints.
- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451): warning, `-XX:+EnableDynamicAgentLoading`/`-XX:-EnableDynamicAgentLoading`, định hướng chính sách.
- [Oracle JDK 21 Release Notes — Dynamic Agent Loading](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): JEP 451 và flags trong HotSpot.
- [Oracle Java SE 21 — `java` launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-javaagent`, `-cp`, `-jar`, module mode và các JVM flags.
- [Oracle Java SE 21 — `Module` và `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): module runtime relationships, defining loaders và class identity.

**Ghi nhớ:** Để kiểm thử Java instrumentation đáng tin cậy, hãy ghi **mỗi tổ hợp JDK build + VM implementation + launch mode + manifest + attach policy** thành **một hàng ma trận có log kiểm chứng**. Tách ba câu hỏi **agent có được nạp không**, **capability có được cấp không**, **thao tác trên target có thành công không**. Không biến một lần chạy PASS trên một HotSpot build thành lời hứa hỗ trợ cho mọi JDK/JVM.