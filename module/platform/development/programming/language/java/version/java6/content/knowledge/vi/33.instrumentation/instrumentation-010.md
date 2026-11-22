# Instrumentation — Cấu hình agent tường minh theo chính sách của JDK hiện đại

## Mục tiêu

Java agent có thể quan sát hoặc thay đổi cách JVM load và thực thi classes thông qua **`java.lang.instrument`**; JVM TI agents có thể hoạt động ở mức native. Quyền nạp agent cần một ranh giới tin cậy rõ ràng: **ai đã cho phép, agent đến từ đâu, nó được nạp lúc nào, và JVM mục tiêu đã được cấu hình để chấp nhận hành động đó chưa?**

Đề bài **“Cấu hình agent tường minh theo chính sách của JDK hiện đại”** thuộc chủ đề *Instrumentation*. Bài này tập trung vào **cấu hình tại JVM startup, cơ chế dynamic loading, cảnh báo JEP 451, lựa chọn policy và quy trình triển khai** — không phải khóa học chi tiết về chỉnh sửa bytecode.

Sau bài học, bạn có thể:
1. Phân biệt **startup agent** (`-javaagent`/`-agentlib`) với **dynamic agent** được nạp sau startup vào JVM đang chạy.
2. Giải thích **integrity by default** và JEP 451: JDK 21 bắt đầu phát cảnh báo với dynamic loading; việc chặn mặc định là định hướng cho **một bản JDK tương lai**, không được tự khẳng định nó đã xảy ra trên mọi JDK 26.
3. Phân biệt ba lựa chọn HotSpot quan trọng: `-XX:+EnableDynamicAgentLoading`, `-XX:-EnableDynamicAgentLoading` và `-XX:+DisableAttachMechanism`.
4. Hiểu việc bật/tắt **dynamic agent loading** khác với việc có thể **attach** vào JVM để thực hiện các tác vụ khác; một JVM có thể cho attach nhưng từ chối `loadAgent`.
5. Hiểu `Premain-Class` và `Agent-Class` của JAR manifest, điểm vào `premain`/`agentmain`, và các cờ `Can-*` không thay thế chính sách cho phép dynamic loading.
6. Đặt `-javaagent:path/to/agent.jar[=args]` vào startup command, Docker/Kubernetes/CI/deployment config do owner quản lý; không dùng self-attach ngầm để tránh quyết định triển khai.
7. Dùng `VirtualMachine.loadAgent` từ module `jdk.attach` **chỉ khi được ủy quyền** và target process hỗ trợ attach/agent policy.
8. Nhận diện warning, `AgentLoadException` và `AttachNotSupportedException`; chẩn đoán lỗi theo từng tầng thay vì tắt hết cơ chế bảo vệ.
9. Biết `-Djdk.instrument.traceUsage` giúp theo dõi các lời gọi Instrumentation API và `-Djdk.attach.allowAttachSelf` là một vấn đề khác, không phải cách cấp phép phổ quát.
10. Có **ví dụ Java 17+ thực chạy**: build agent JAR, kiểm tra startup khi dynamic loading bị tắt, và kiểm thử bốn chính sách của **JVM con do chương trình tự tạo**.
11. Hiểu sự khác nhau giữa chính sách **HotSpot**, một implementation khác như OpenJ9 và contract Java SE; kiểm chứng exact version/vendor trước khi quyết định.
12. Thiết kế rollout, audit, rollback, security và bộ kiểm thử để một instrumentation agent không được nạp ngoài ý muốn.

**Special Note:** Chỉ áp dụng kiến thức còn hiệu lực hiện nay, theo ghi chú nguyên văn của module: “Note : Hãy chỉ lấy các kiến thức vẫn còn áp dụng đến hiện giờ, không lấy các kiến thức lỗi thời hoặc đã legacy hiện nay”. Dựa trên **Java SE/JDK 26 official docs**, JEP 451 và các APIs hiện hành; không đề xuất `Thread.stop`, các APIs nội bộ `sun.*` hoặc thủ thuật vượt quyền hệ điều hành. Những thực nghiệm trong bài chạy **Windows OpenJDK 24**, biên dịch `javac --release 17`; tuyệt đối không gán kết quả một JVM thử nghiệm cho mọi JDK/provider.

## 1. Vấn đề: Ai cho phép agent sửa behavior của JVM?

Instrumentation có khả năng thay đổi bytecode của các classes được load, thậm chí đã load nếu các điều kiện runtime cho phép. Một agent có thể là công cụ quan sát hữu ích như profiler, coverage hoặc tracing, nhưng cũng là **mã được thực thi trong chính process** của ứng dụng mục tiêu, với tầm ảnh hưởng lớn.

Có hai cách tiếp nhận chính:

```text
[A] Startup: owner khai báo agent trước khi JVM chạy application
    Deployment config / command line
         |
         +-- java -javaagent:trusted-agent.jar=options -jar app.jar
         |
         +-- JVM đọc Premain-Class -> premain(...)
         |
         +-- app main(...)

[B] Dynamic: JVM đã chạy, tool đề nghị đưa agent vào
    Serviceability/Attach API tool
         |
         +-- Có quyền kết nối đến JVM đích?
         |
         +-- JVM đích cho phép attach mechanism?
         |
         +-- JVM đích cho phép dynamic loading of agents?
         |
         +-- Agent JAR có Agent-Class, agentmain(...) hợp lệ?
         |
         +-- loadAgent(...) -> JVM đích gọi agentmain(...)
```

Điểm cốt lõi là **chủ JVM/application nên biết và đồng ý trước khi một agent có thể thay đổi code đang chạy**. Startup agent khiến quyền này được diễn đạt rõ trong deployment config. Dynamic loading được giữ cho các công cụ quản trị phù hợp, nhưng cần một quyết định policy tường minh khi rủi ro cao.

### 1.1. Startup agent không có nghĩa agent “bị giới hạn” tuyệt đối

`-javaagent` cũng là thực thi code mạnh trong ứng dụng. Việc đặt nó ở startup command làm quá trình **minh bạch và có thể kiểm soát**; vẫn cần xác minh nguồn JAR, ít quyền nhất, kiểm thử tương thích và audit. Không coi bất cứ agent nào là an toàn chỉ vì không được nạp động.

### 1.2. Agent không giống logging library thông thường

Một logging library được application gọi qua API. Agent nhận `Instrumentation` và có thể register transformers, thay đổi class load behavior, hoặc chỉnh sửa module relationships khi được JVM cho phép. Nó không nên được triển khai như một dependency ẩn không có release process. Đặc biệt với agent thao tác class bytes, lỗi có thể xảy ra ở thời điểm khởi động của toàn ứng dụng.

## 2. JEP 451: cảnh báo và hướng tới integrity-by-default

[JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451) giới thiệu warning khi một Java/JVM TI agent được **nạp động vào JVM đang chạy** từ JDK 21. Mục tiêu của warning là yêu cầu hệ sinh thái kiểm soát agent loading minh bạch trước khi một JDK tương lai chuyển sang **không cho phép dynamic agent loading theo mặc định**.

**Phân biệt rõ ba tầng thông tin:**

| Nội dung | Trạng thái/ý nghĩa |
| --- | --- |
| Kể từ JDK 21 | Dynamic agent loading có thể tạo warning khi chưa explicit opt-in |
| JDK 26 Java SE/Javadoc hiện hành | Document vẫn mô tả dynamic agent loading, warning và HotSpot opt-in option |
| JDK 26 có mặc định chặn toàn bộ dynamic agents chưa? | **Không được suy ra** từ JEP 451; hãy kiểm chứng runtime/release notes cụ thể |
| Dự định về tương lai | Có thể chuyển default sang disallow, owner cần explicit opt-in |
| Startup `-javaagent` | **Không phải** dynamic agent loading; JEP 451 không thêm warning kiểu này cho startup agents |
| Attach cho tác vụ khác | Không nhất thiết bị đồng nhất với dynamic **loadAgent** |

**Điểm quan trọng:** JEP 451 chuẩn bị thay đổi **default**, không phải tuyên bố loại bỏ hoàn toàn công cụ serviceability hay Attach API. Chủ JVM vẫn có đường opt-in có chủ đích trên JVM hỗ trợ. Nếu một bản JDK mới đổi chính sách, quy trình test/rollout phải thấy lỗi rõ và có đường giải quyết được phê duyệt.

### 2.1. Cảnh báo thường thấy

Một output từ JVM theo JEP 451 có thể gồm:

```text
WARNING: A Java agent has been loaded dynamically
WARNING: If a serviceability tool is in use, please run with -XX:+EnableDynamicAgentLoading
WARNING: If a serviceability tool is not in use, please run with -Djdk.instrument.traceUsage
WARNING: Dynamic loading of agents will be disallowed by default in a future release
```

Đây là **dạng lược trích minh họa**, không phải exact full output mọi runtime. Text/đường dẫn/định dạng tùy JDK/provider. Không viết unit test phụ thuộc toàn bộ warning message. Trong fixture OpenJDK 24, chúng tôi chỉ tìm **cụm `A Java agent has been loaded dynamically`**, thay vì bắt mọi dòng phải giống nhau.

### 2.2. Warning không đồng nghĩa load thất bại

Trong JDK 24 fixture, khi JVM đích **không** khai báo `-XX:+EnableDynamicAgentLoading` hay `-XX:-EnableDynamicAgentLoading`:
- External attach vẫn thành công.
- `VirtualMachine.loadAgent` vẫn thành công.
- JVM đích in warning về dynamic agent loading.
- `agentmain` được gọi và application thấy property do agent đặt.

Vì vậy một test chạy **xanh nhưng có warning** không nên được âm thầm chấp nhận mãi; hãy định danh dependency nào đang dynamic attach và xem xét chuyển sang startup agent hoặc explicit policy.

### 2.3. Tại sao chính sách này cần thiết?

Nếu một library có khả năng tự attach trong cùng process rồi instrument JVM bất ngờ, nó có thể vượt ngoài những gì người vận hành tưởng rằng đã deploy. Integrity-by-default hướng tới việc một thay đổi lớn như nạp agent phải có **sự chấp thuận chủ ý từ người khởi động JVM**. Với monitoring/testing tooling hợp pháp, đổi sang `-javaagent` ngay từ đầu là một thiết kế dễ giải thích, review, reproduce và audit hơn.

## 3. Chính sách HotSpot — ý nghĩa từng JVM option

Đây là các lựa chọn **implementation-specific của HotSpot**, không phải Java language syntax. Với OpenJ9 hay các JVM khác, tra tài liệu của provider/version riêng. Không đặt kỳ vọng mọi JVM phải chấp nhận mọi `-XX` option.

### 3.1. `-XX:+EnableDynamicAgentLoading`: explicit opt-in

```bash
java -XX:+EnableDynamicAgentLoading -jar app.jar
```

Đây là ví dụ cấu hình **JVM do bạn vận hành**, với `app.jar` là đường dẫn JAR thật tại deployment. Nó diễn đạt **chủ JVM chủ động cho phép dynamic loading agents** theo HotSpot policy. Với JDK 21–26 HotSpot implementation note, option này đồng thời **tắt JEP 451 warning** cho dynamic agent load.

Tuy nhiên, nó **không**:
- Cấp OS permission để attach vào một process khác.
- Tự kích hoạt Attach API nếu target đã dùng `-XX:+DisableAttachMechanism`.
- Bổ sung `Agent-Class` cho JAR không có header đó.
- Bảo đảm target class có thể retransform/redefine.
- Bắt buộc một external tool được phép quản trị application.
- Tự xác thực nguồn agent JAR.
- Tự nạp agent. Vẫn phải có attach caller thực sự yêu cầu `loadAgent`.

Chỉ bật khi có use case đã được phê duyệt và access controls phù hợp.

### 3.2. `-XX:-EnableDynamicAgentLoading`: từ chối dynamic loadAgent

```bash
java -XX:-EnableDynamicAgentLoading -jar app.jar
```

Đây là cách **kiểm thử khả năng sống chung với chính sách tương lai** hoặc làm cứng workload không cần live-agent injection. Trên HotSpot, nó ngăn nạp mới Java/JVM TI agents vào JVM đang chạy.

Điểm dễ nhầm: **nó không nhất thiết chặn Attach API connection**. Một tool vẫn có thể attach và làm các tác vụ được JVM cho phép, nhưng gọi `loadAgent` sẽ bị từ chối. Trong fixture, parent `VirtualMachine.attach` thành công còn `loadAgent` ném **`AgentLoadException`** trên OpenJDK 24.

Và quan trọng nhất: **nó không chặn startup `-javaagent`**. Bài thực tế đã chạy cùng một JVM với cả:

```bash
java -XX:-EnableDynamicAgentLoading \
  -javaagent:policy-agent.jar=mode=startup \
  -cp out PolicyTarget startup
```

Các dấu `\` cuối dòng trong snippet là cú pháp **POSIX shell**; trên Windows PowerShell, dùng **một dòng lệnh** hoặc continuation theo cú pháp PowerShell. Startup agent vẫn `premain` trước `main` dù dynamic loading off.

### 3.3. `-XX:+DisableAttachMechanism`: chặn cơ chế attach

```bash
java -XX:+DisableAttachMechanism -jar app.jar
```

Lựa chọn HotSpot này mang ý nghĩa khác: **vô hiệu hóa attach mechanism**. Bằng chứng thực nghiệm: `VirtualMachine.attach` từ external process bị từ chối trên OpenJDK 24, với `AttachNotSupportedException`. Khi không thể attach, hiển nhiên không thể tiếp tục gọi `loadAgent` qua handle đó.

**Lưu ý vận hành:** Attach mechanism được nhiều công cụ quản trị/serviceability dùng; tắt nó có thể làm **`jcmd`, `jstack` hoặc các luồng chẩn đoán phụ thuộc attach** không còn hoạt động như trước. Cần sự đồng ý của SRE/ops và một kế hoạch chẩn đoán thay thế nếu production cần JVM attach. Không dùng flag này theo phản xạ ở mọi môi trường.

### 3.4. `-Djdk.attach.allowAttachSelf` không phải policy thay thế

Một số tooling cố dùng self-attach (client process attach tới **chính PID của nó**). HotSpot có property `jdk.attach.allowAttachSelf` liên quan điều kiện self-attach; nhưng:
- Nó **không** thay `-XX:+EnableDynamicAgentLoading` ở target.
- Nó **không** vượt `-XX:+DisableAttachMechanism`.
- Nó **không** cấp quyền OS/security hay cung cấp Agent-Class.
- Nó **không** làm một tool không đáng tin thành được ủy quyền.
- Cách dùng và default của nó tùy implementation/version.

Không đề xuất bật self-attach chỉ để làm warning JEP 451 biến mất. Nếu đang viết ứng dụng mà owner muốn startup instrumentation, hãy truyền `-javaagent` tường minh.

### 3.5. `-Djdk.instrument.traceUsage` là chẩn đoán, không phải opt-in

```bash
java -Djdk.instrument.traceUsage -jar app.jar
```

Property này khiến những usages của Instrumentation API được trace (theo implementation/JEP 451) nhằm giúp xác định nguồn instrumentation. Nó **không** thay đổi agent loading policy. Khi bật, output có thể nhiều và lộ chi tiết stack/implementation, chỉ dùng trong môi trường được phép rồi tắt. Không coi traceUsage là cách bảo vệ khi một dependency cố âm thầm nạp agent.

## 4. Ma trận chính sách: Attach và loadAgent không phải cùng thao tác

| Target JVM config | `VirtualMachine.attach` (fixture JDK 24) | `loadAgent` | Warning JEP 451 | `-javaagent` startup |
| --- | --- | --- | --- | --- |
| `-XX:+EnableDynamicAgentLoading` | Thành công | Thành công | Không in warning | Có thể dùng |
| `-XX:-EnableDynamicAgentLoading` | Thành công | **Từ chối** | Không có load-warning vì agent không load | **Có thể dùng** |
| Không chỉ rõ flag trên JDK 24 test | Thành công | Thành công | **Có warning** | Có thể dùng |
| `-XX:+DisableAttachMechanism` | **Từ chối attach** | Không đến bước gọi | Không có load-warning | Là cơ chế riêng |
| JVM khác/vendor khác | Phụ thuộc implementation | Phụ thuộc policy | Phụ thuộc version | Tra runtime docs |

**Quan trọng về scope:** Bảng là **thực nghiệm trên OpenJDK 24 Windows**, không phải tuyên bố trạng thái default của mọi JDK 26/vendor. Năm 2026, Oracle Java SE 26 Javadoc và JEP 451 vẫn nhấn mạnh owner opt-in và warning, nên bài không ghi sai “JDK 26 luôn chặn attach”.

### 4.1. Ba tầng kiểm tra cần độc lập

```text
Có executable của Attach tool?
        |
        v
Attach provider + OS/container/user cho phép kết nối?
        |                  \
        | NO                -> Fail attach (ví dụ AttachNotSupportedException)
        v
Target policy cho phép DYNAMIC AGENT LOADING?
        |                  \
        | NO                -> Fail loadAgent (ví dụ AgentLoadException)
        v
Agent JAR hợp lệ và có Agent-Class?
        |                  \
        | NO                -> Fail load agent / initialization
        v
agentmain(...) chạy; kiểm tra result và observability
```

Lỗi không ở cùng tầng thì không có một flag “sửa tất cả”. Đừng sửa thiếu `Agent-Class` bằng cách bật `EnableDynamicAgentLoading`; đừng sửa thiếu attach permission bằng cách thay manifest.

### 4.2. Agent capabilities là chiều chính sách thứ tư

Ngay cả khi `agentmain` chạy, `Instrumentation.isRetransformClassesSupported()` có thể `false` nếu manifest thiếu `Can-Retransform-Classes` hoặc JVM không hỗ trợ. Bài test cố ý dùng agent không xin thêm Can-* nên **retransform=false** trong startup.

| Cơ chế | Quyết định điều gì? |
| --- | --- |
| `-XX:+/-EnableDynamicAgentLoading` | Target JVM có cho agent nạp sau startup hay không |
| `-XX:+DisableAttachMechanism` | Có cho external tool attach vào target JVM qua mechanism không |
| `Agent-Class` trong manifest | Agent class nào được gọi khi dynamic load |
| `Premain-Class` trong manifest | Agent class nào được gọi khi startup -javaagent |
| `Can-Retransform-Classes` | Agent **yêu cầu** retransformation capability |
| `Instrumentation.isRetransformClassesSupported()` | Runtime thực tế cho agent capability này không |
| `Instrumentation.isModifiableClass(clazz)` | Class cụ thể có thể bị modified theo VM rules không |
| OS/file/network/container permissions | Ai được kết nối/đọc JAR/khởi động JVM |

Không gộp các tầng này thành một Boolean `agentEnabled`.

## 5. Manifest và điểm vào: khai báo rõ ở artifact

Một Java agent JAR được JVM đọc `META-INF/MANIFEST.MF`. Với bài test:

```text
Manifest-Version: 1.0
Premain-Class: AgentPolicyDemo
Agent-Class: AgentPolicyDemo

```

`Premain-Class` được dùng khi startup với `-javaagent` và gọi `premain`. `Agent-Class` được dùng nếu target nạp agent sau startup và gọi `agentmain`. JAR có thể khai báo **cả hai**, nhưng mỗi cách khởi động **chỉ chọn callback tương ứng**.

### 5.1. Callback hợp lệ

```java
public static void premain(String agentArgs, Instrumentation instrumentation)
public static void agentmain(String agentArgs, Instrumentation instrumentation)
```

Hai dòng trên là **signatures minh họa**, không phải Java methods có body. Package specification còn cho phép overload không có tham số `Instrumentation`, nhưng nếu cần dùng API thì chọn bản có tham số. Agent options được truyền như **một String**, không phải Map được JVM parse sẵn.

Nếu startup `Premain-Class` không có hoặc method lỗi fatal, JVM có thể abort trước application main. Với dynamic agent, lỗi được báo cho attach caller và không nên coi là thành công chỉ vì target process vẫn đang chạy.

### 5.2. Không xin quyền không cần

Bài dùng một agent chỉ in callback và đặt system property. Nó **không cần**:
- `Can-Redefine-Classes`
- `Can-Retransform-Classes`
- `Can-Set-Native-Method-Prefix`

Các thuộc tính `Can-*` không xuất hiện, mặc định false. Điều này kiểm tra đúng nguyên tắc least privilege. Nếu sau này instrumentation agent cần sửa bytecode, cấp riêng quyền phù hợp và kiểm tra `Instrumentation` runtime; dynamic loading opt-in không tự cấp các Can-*.

### 5.3. Startup agent JAR có thể là dependency của quan sát

Một monitoring/profiling agent có thể cần bản agent riêng tương thích JDK, ứng dụng và runtime. Với startup:

```bash
java -javaagent:/opt/agents/trusted-telemetry.jar=env=prod -jar service.jar
```

Đường dẫn trên là **minh họa deployment path**, không phải tên agent JAR của bài. Chỉ dùng agent được owner và security review duyệt. Đối với đường dẫn có spaces, quote theo shell/launcher; tránh để secrets trong `=options`.

## 6. Ví dụ Java 17+ đã chạy thật — agent tự công bố điểm vào

### 6.1. Tạo ba file trong một thư mục thử nghiệm mới

```text
agent-policy-demo/
  AgentPolicyDemo.java
  AgentPolicyHarness.java
  agent.mf
  out/                 (sinh ra)
  policy-agent.jar     (sinh ra)
```

Mọi file được tạo trong **thư mục test**, không sửa module/repository của ứng dụng. Bài đã chạy trên **Windows OpenJDK 24**, dùng `javac --release 17`. Mã không dùng ASM/Byte Buddy/JNI, không sửa bytecode thực tế.

### 6.2. File `AgentPolicyDemo.java` — một agent có cả premain và agentmain

```java
import java.lang.instrument.Instrumentation;

public final class AgentPolicyDemo {
    private static void run(String entry, String args,
                            Instrumentation instrumentation) {
        if (instrumentation == null)
            throw new AssertionError("missing Instrumentation");

        System.setProperty("demo.policy.agent", entry);
        System.out.println("agent.entry=" + entry);
        System.out.println("agent.args=" + args);
        System.out.println("agent.retransform=" +
                instrumentation.isRetransformClassesSupported());
    }

    public static void premain(String args, Instrumentation instrumentation) {
        run("premain", args, instrumentation);
    }

    public static void agentmain(String args, Instrumentation instrumentation) {
        run("agentmain", args, instrumentation);
    }
}
```

Đây là **file source hoàn chỉnh**. Agent chỉ:
- Xác nhận JVM đã truyền `Instrumentation`.
- Đặt system property `demo.policy.agent` trong **JVM nơi callback chạy**, để app đích quan sát được.
- In entry/callback, options và runtime retransform capability.
- Không đăng ký transformer, không sửa bytecode, không yêu cầu permissions mạnh.
- Không chuyển tham số mật khẩu hay thông tin nhạy cảm qua output.

**`System.setProperty(...)` chỉ là dấu hiệu test**. Một production agent không nên dùng property toàn cục tùy ý để giao tiếp nếu có thể xung đột với ứng dụng.

### 6.3. File `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: AgentPolicyDemo
Agent-Class: AgentPolicyDemo

```

Có **dòng trống kết thúc main section**. Không thêm `Can-Retransform-Classes` vì agent không thực hiện retransformation. `Agent-Class` có mặt để kiểm thử authorized dynamic loading trong JVM con.

### 6.4. Lệnh build Java 17+

```bash
mkdir out
javac --release 17 --add-modules jdk.attach -d out AgentPolicyDemo.java AgentPolicyHarness.java
jar --create --file policy-agent.jar --manifest agent.mf -C out AgentPolicyDemo.class
jar --list --file policy-agent.jar
```

`AgentPolicyHarness.java` nằm ở mục 7, cần lưu trước khi chạy lệnh biên dịch trên. Nếu chỉ muốn kiểm tra startup trước, có thể compile riêng `AgentPolicyDemo.java` và class `PolicyTarget` từ cùng harness source.

`--release 17` kiểm tra source compatibility với Java 17. `jdk.attach` là **JDK-specific module**, không được cam kết nằm trong mọi trimmed runtime image. Với named modules cần cấu hình `requires jdk.attach` trong module controller, và `requires java.instrument` cho module khai báo agent code nếu đóng thành named module; ví dụ classpath này **không cần module-info.java**.

`jar --create --manifest` tạo manifest trong artifact thực, không phải JVM đọc file `agent.mf` bên ngoài khi chạy. `jar --list` phải cho thấy `META-INF/MANIFEST.MF` và `AgentPolicyDemo.class`.

### 6.5. Kiểm tra baseline: chưa bật agent

```bash
java -cp out PolicyTarget startup
```

Stdout chính xác đã chạy:

```text
target.agent=none
```

Không có agent callback, property chưa được set.

### 6.6. Startup agent vẫn hoạt động khi dynamic loading bị tắt

```bash
java -XX:-EnableDynamicAgentLoading -javaagent:policy-agent.jar=mode=startup -cp out PolicyTarget startup
```

Stdout chính xác trên OpenJDK 24:

```text
agent.entry=premain
agent.args=mode=startup
agent.retransform=false
target.agent=premain
```

Đây là một kiểm chứng quan trọng nhất của bài: **từ chối dynamic loadAgent không tương đương từ chối startup agent**. Startup `premain` chạy trước `PolicyTarget.main` và app thấy property mà agent đặt. Không cần bật `Can-*` để agent được gọi.

### 6.7. Vì sao chọn run child JVM thay vì attach chính nó?

Kiểm thử chính sách bằng cách attach vào process đang hoạt động thực sự giúp:
- Mỗi thử nghiệm có JVM startup flag **riêng**.
- Parent test process không cần tự cho phép self-attach.
- Không gắn agent vào JVM nghiệp vụ.
- Dễ quan sát JVM stderr warning và application output.
- Dễ cleanup subprocess kể cả khi có lỗi.
- Kiểm tra rõ từng tầng: external attach, dynamic load agent, callback, process shutdown.

Tuy nhiên, đây vẫn là **bộ kiểm thử về khả năng và policy**, không phải một phương pháp để truy cập JVM của người khác. Test harness chỉ dùng child process nó tự tạo và biết PID.

## 7. Chương trình kiểm thử policy đầy đủ `AgentPolicyHarness.java`

### 7.1. Những tình huống sẽ chạy

| Scenario label | Child JVM flag | Expected attach | Expected loadAgent | Expected warning |
| --- | --- | --- | --- | --- |
| `explicitOptIn` | `-XX:+EnableDynamicAgentLoading` | Yes | Yes | No |
| `explicitOptOut` | `-XX:-EnableDynamicAgentLoading` | Yes | **No** | No |
| `jdk24Default` | Không truyền flag dynamic policy | Yes trên JDK 24 | Yes trên JDK 24 | **Yes** |
| `attachMechanismOff` | `-XX:+DisableAttachMechanism` | **No** | No | No |

Mọi child JVM có:
- `PolicyTarget` được chạy với tham số `wait` và hai đường dẫn file signals trong test directory.
- `ready-<label>.txt` được child tạo để báo đã sẵn sàng.
- Parent test chờ sẵn sàng rồi mới `VirtualMachine.attach(child.pid())`.
- `release-<label>.txt` được parent ghi để child kết thúc tự nhiên.
- `Process.waitFor` có timeout.
- `finally` gọi `destroyForcibly` nếu còn sống và dọn signal files, không để lại JVM chạy vô thời hạn.

**Không có việc liệt kê tất cả PIDs trên máy hoặc chọn một process từ bên ngoài test.**

### 7.2. Toàn bộ mã `AgentPolicyHarness.java`

```java
import com.sun.tools.attach.VirtualMachine;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public final class AgentPolicyHarness {
    private static int passed = 0;

    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        passed++;
        System.out.println(name + "=true");
    }

    private static boolean await(Path ready) throws Exception {
        long deadline =
                System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
        while (!Files.exists(ready)) {
            if (System.nanoTime() > deadline) return false;
            Thread.sleep(20);
        }
        return true;
    }

    private static String test(String label, String flag, String jar,
                               boolean shouldLoad, boolean expectedWarning,
                               boolean allowAttach) throws Exception {
        Path ready = Path.of("ready-" + label + ".txt");
        Path release = Path.of("release-" + label + ".txt");
        Files.deleteIfExists(ready);
        Files.deleteIfExists(release);

        Path java = Path.of(
                System.getProperty("java.home"), "bin", "java");
        List<String> command = new ArrayList<>();
        command.add(java.toString());
        if (flag != null) command.add(flag);
        command.add("-cp");
        command.add(System.getProperty("java.class.path"));
        command.add("PolicyTarget");
        command.add("wait");
        command.add(ready.toString());
        command.add(release.toString());

        Process child = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .start();
        String result;

        try {
            check(label + ".ownedChild",
                    child.pid() != ProcessHandle.current().pid());
            check(label + ".childReady", await(ready));

            boolean attached = false;
            boolean loaded = false;
            String failure = "";
            try {
                VirtualMachine vm = VirtualMachine.attach(
                        Long.toString(child.pid()));
                attached = true;
                try {
                    vm.loadAgent(
                            Path.of(jar).toAbsolutePath().toString(),
                            "mode=" + label);
                    loaded = true;
                } finally {
                    vm.detach();
                }
            } catch (Exception expected) {
                failure = expected.getClass().getSimpleName();
            }

            check(label + ".attachAllowed",
                    attached == allowAttach);
            check(label + ".loadExpected",
                    loaded == shouldLoad);
            if (!shouldLoad) {
                check(label + ".deniedHasFailure",
                        !failure.isBlank());
            }

            Files.writeString(release, "done",
                    StandardCharsets.UTF_8);
            check(label + ".childExited",
                    child.waitFor(12, TimeUnit.SECONDS));
            check(label + ".childExitZero",
                    child.exitValue() == 0);

            result = new String(
                    child.getInputStream().readAllBytes(),
                    StandardCharsets.UTF_8)
                    .replace("\r\n", "\n");

            check(label + ".agentObservation",
                    result.contains("target.agent=" +
                            (shouldLoad ? "agentmain" : "none")
                            + "\n"));
            check(label + ".warningExpected",
                    result.contains(
                            "A Java agent has been loaded dynamically")
                            == expectedWarning);

            if (shouldLoad) {
                check(label + ".agentCallback",
                        result.contains(
                                "agent.entry=agentmain\n"));
                check(label + ".argsPassed",
                        result.contains(
                                "agent.args=mode=" + label + "\n"));
            } else {
                check(label + ".noAgentCallback",
                        !result.contains(
                                "agent.entry=agentmain\n"));
            }

            System.out.println("scenario." + label + ".failure=" +
                    (failure.isBlank() ? "none" : failure));
            System.out.println("scenario." + label + ".warning=" +
                    expectedWarning);
        } finally {
            child.destroyForcibly();
            child.waitFor(5, TimeUnit.SECONDS);
            Files.deleteIfExists(ready);
            Files.deleteIfExists(release);
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1)
            throw new IllegalArgumentException("agent jar");
        test("explicitOptIn",
                "-XX:+EnableDynamicAgentLoading",
                args[0], true, false, true);
        test("explicitOptOut",
                "-XX:-EnableDynamicAgentLoading",
                args[0], false, false, true);
        test("jdk24Default",
                null,
                args[0], true, true, true);
        test("attachMechanismOff",
                "-XX:+DisableAttachMechanism",
                args[0], false, false, false);
        System.out.println("checksPassed=" + passed);
    }
}

class PolicyTarget {
    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("startup")) {
            System.out.println("target.agent=" +
                    System.getProperty(
                            "demo.policy.agent", "none"));
            return;
        }
        if (args.length != 3 || !args[0].equals("wait"))
            throw new IllegalArgumentException(
                    "wait readyFile releaseFile");

        Path ready = Path.of(args[1]);
        Path release = Path.of(args[2]);
        Files.writeString(
                ready, "ready", StandardCharsets.UTF_8);
        long deadline =
                System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
        while (!Files.exists(release)) {
            if (System.nanoTime() > deadline)
                throw new AssertionError("test timeout");
            Thread.sleep(25);
        }
        System.out.println("target.agent=" +
                System.getProperty(
                        "demo.policy.agent", "none"));
    }
}
```

Toàn bộ source ở trên có thể biên dịch với Java 17. `PolicyTarget` là một **top-level class không public** được đặt cùng file `AgentPolicyHarness.java` để tiện build. `ProcessBuilder` nhận các arguments dạng list, không ghép thành một shell command, nên tránh lỗi quotes với các đường dẫn có spaces.

**Giới hạn của fixture:** Test tập trung vào HotSpot/OpenJDK Windows JDK 24. Nếu đổi sang OpenJ9, JDK tương lai hoặc môi trường attach bị firewall/container/OS policy giới hạn, các expected booleans có thể khác và test fail hợp lệ. Không “sửa” test bằng cách bật quyền ngoài ý muốn trong production. Khi đổi runtime, đổi expectations theo release documentation và security policy.

### 7.3. Biên dịch, đóng JAR, chạy baseline và ma trận

Sau khi đã tạo `AgentPolicyDemo.java`, `AgentPolicyHarness.java`, `agent.mf`:

```bash
mkdir out
javac --release 17 --add-modules jdk.attach -d out \
  AgentPolicyDemo.java AgentPolicyHarness.java

jar --create --file policy-agent.jar \
  --manifest agent.mf -C out AgentPolicyDemo.class

java -cp out PolicyTarget startup

java -XX:-EnableDynamicAgentLoading \
  -javaagent:policy-agent.jar=mode=startup \
  -cp out PolicyTarget startup

java --add-modules jdk.attach \
  -cp out AgentPolicyHarness policy-agent.jar
```

Các dấu `\` để xuống dòng là syntax POSIX. Nếu chạy trên Windows PowerShell 5.1, viết mỗi command thành **một dòng**, không paste `\` để nối. Lượt QA đã chạy toàn bộ với Java 24 trên Windows PowerShell và các lệnh một dòng tương đương.

**Khi chạy trong workspace có dữ liệu thật**, đừng dùng một signal-file path đã tồn tại; harness chủ động xóa `ready-*.txt`/`release-*.txt` tại working directory dành cho bài test. Vì vậy hãy luôn chạy từ thư mục test **mới và riêng biệt** (không chứa files cùng tên có giá trị). Đây là lý do lượt QA sử dụng random directory dưới TEMP rồi dọn sau khi xong.

### 7.4. Stdout thực tế của 40 checks trên OpenJDK 24

```text
explicitOptIn.ownedChild=true
explicitOptIn.childReady=true
explicitOptIn.attachAllowed=true
explicitOptIn.loadExpected=true
explicitOptIn.childExited=true
explicitOptIn.childExitZero=true
explicitOptIn.agentObservation=true
explicitOptIn.warningExpected=true
explicitOptIn.agentCallback=true
explicitOptIn.argsPassed=true
scenario.explicitOptIn.failure=none
scenario.explicitOptIn.warning=false
explicitOptOut.ownedChild=true
explicitOptOut.childReady=true
explicitOptOut.attachAllowed=true
explicitOptOut.loadExpected=true
explicitOptOut.deniedHasFailure=true
explicitOptOut.childExited=true
explicitOptOut.childExitZero=true
explicitOptOut.agentObservation=true
explicitOptOut.warningExpected=true
explicitOptOut.noAgentCallback=true
scenario.explicitOptOut.failure=AgentLoadException
scenario.explicitOptOut.warning=false
jdk24Default.ownedChild=true
jdk24Default.childReady=true
jdk24Default.attachAllowed=true
jdk24Default.loadExpected=true
jdk24Default.childExited=true
jdk24Default.childExitZero=true
jdk24Default.agentObservation=true
jdk24Default.warningExpected=true
jdk24Default.agentCallback=true
jdk24Default.argsPassed=true
scenario.jdk24Default.failure=none
scenario.jdk24Default.warning=true
attachMechanismOff.ownedChild=true
attachMechanismOff.childReady=true
attachMechanismOff.attachAllowed=true
attachMechanismOff.loadExpected=true
attachMechanismOff.deniedHasFailure=true
attachMechanismOff.childExited=true
attachMechanismOff.childExitZero=true
attachMechanismOff.agentObservation=true
attachMechanismOff.warningExpected=true
attachMechanismOff.noAgentCallback=true
scenario.attachMechanismOff.failure=AttachNotSupportedException
scenario.attachMechanismOff.warning=false
checksPassed=40
```

Các dòng `*.attachAllowed=true` hoặc `*.loadExpected=true` là kết quả **assertion** khớp với kỳ vọng, không phải biến raw `attached` hoặc `loaded`! Ví dụ ở `explicitOptOut`, output `explicitOptOut.loadExpected=true` nghĩa là phép kiểm `loaded == shouldLoad` đã PASS, với **shouldLoad=false**. Đừng giải thích nhầm nó thành “loadAgent thành công” trong opt-out scenario.

**40/40 assertions PASS**, không phải con số thay cho số JDK scenarios. Script chạy trên OpenJDK 24, chương trình kết thúc exit code 0. Bốn child JVM được chạy/cleanup dưới quyền test. Error class names `AgentLoadException`, `AttachNotSupportedException` là kết quả quan sát trên implementation này, **không phải** mọi JVM phải ném cùng exception cho mọi chính sách.

### 7.5. Từng kết quả nói gì?

| Scenario | Output key | Cách hiểu |
| --- | --- | --- |
| `explicitOptIn` | `scenario.explicitOptIn.failure=none` | Attach + loadAgent thành công |
| `explicitOptIn` | `scenario.explicitOptIn.warning=false` | Explicit opt-in không sinh JEP 451 warning |
| `explicitOptOut` | `scenario.explicitOptOut.failure=AgentLoadException` | Attach được nhưng JVM từ chối loadAgent |
| `explicitOptOut` | `scenario.explicitOptOut.warning=false` | Không nạp agent, nên không có warning “agent loaded” |
| `jdk24Default` | `scenario.jdk24Default.failure=none` | JDK 24 default cho loadAgent |
| `jdk24Default` | `scenario.jdk24Default.warning=true` | JDK 24 default phát JEP 451 warning |
| `attachMechanismOff` | `scenario.attachMechanismOff.failure=AttachNotSupportedException` | Attach mechanism bị tắt, không đến bước loadAgent |
| `all cases` | `*.agentObservation=true` | Target JVM xác nhận agentmain có/không chạy đúng kỳ vọng |
| `all cases` | `*.childExitZero=true` | Target JVM hoàn tất bình thường |
| `all cases` | `checksPassed=40` | Tổng 40 lần check guard thành công |

Đây là bằng chứng có phạm vi rõ ràng về **chính sách của một runtime**. Nếu chạy JDK 26 khác, không ép kết quả y hệt JDK 24 mà cần đối chiếu target release notes và JVM options được hỗ trợ.

## 8. Triển khai agent trong môi trường vận hành

### 8.1. Startup options phải nằm tại lệnh khởi động JVM thật

Đừng thêm `-javaagent` vào **application arguments sau tên main class** rồi nghĩ JVM sẽ xử lý:

```bash
# SAI: phía sau app main class chỉ là application argument
java -jar service.jar -javaagent:trusted-agent.jar

# ĐÚNG: truyền option cho JVM trước -jar
java -javaagent:trusted-agent.jar -jar service.jar
```

Hai dòng có chữ `service.jar` và `trusted-agent.jar` là **ví dụ minh họa, cần files thật**. Agent JAR phải có `Premain-Class` hợp lệ. `-javaagent` được JVM parse như VM option, do đó thứ tự rất quan trọng.

### 8.2. Docker

Với image/app do bạn sở hữu và đã copy approved agent JAR vào image:

```dockerfile
FROM eclipse-temurin:25-jre
WORKDIR /app
COPY service.jar /app/service.jar
COPY approved-agent.jar /opt/agents/approved-agent.jar
ENTRYPOINT ["java","-XX:-EnableDynamicAgentLoading","-javaagent:/opt/agents/approved-agent.jar","-jar","/app/service.jar"]
```

Đây là **Dockerfile snippet minh họa**, không được QA bằng container build trong lượt này. Dòng `FROM` dùng một base-image tag có thể đổi theo registry; khi dùng thật nên pin digest, quét vulnerabilities và verify signatures của cả image/agent. Chỉ chạy với những artifacts mà bạn kiểm soát, không tự thêm agent tùy tiện vào production services.

Ý đồ của ví dụ: **khóa dynamic loading** nhưng vẫn **cho startup agent đã phê duyệt**. Hai choices không mâu thuẫn. Nếu ứng dụng cần authorized live attach, policy có thể khác và phải được owner quyết định.

### 8.3. Kubernetes

Với container spec do nhóm vận hành quản trị, JVM flags cần nằm trong `command/args`, hoặc cơ chế injection được approved. Ví dụ ý tưởng:

```yaml
containers:
  - name: service
    image: registry.example/internal/service:approved
    command: ["java"]
    args:
      - "-XX:-EnableDynamicAgentLoading"
      - "-javaagent:/opt/agents/approved-agent.jar"
      - "-jar"
      - "/app/service.jar"
```

Đây là **snippet**, không phải toàn bộ Deployment YAML runnable. Nó giả định image đã chứa JAR ở đúng paths. Đừng coi một env var như `JAVA_TOOL_OPTIONS` là không ai nhìn thấy; command-line/JVM logs có thể lộ flags và agent options. Secret agent configs nên được truyền theo cơ chế bảo mật đã duyệt, tránh đưa trực tiếp vào process args.

### 8.4. CI và unit/integration tests

Các frameworks mock/profiler/code coverage có thể tự dùng instrumentation. Khi JDK 21+ báo dynamic load warning:
1. Xác định dependency/agent chính xác; xem logs và `-Djdk.instrument.traceUsage` nếu được phép.
2. Kiểm tra version thư viện/testing tool có hỗ trợ startup agent tường minh chưa.
3. Đưa `-javaagent` vào cấu hình forked JVM test khi thực sự cần; đừng để một library tự attach ngầm.
4. Chạy bộ test dưới `-XX:-EnableDynamicAgentLoading` để phát hiện hidden dependency.
5. Không chỉ thêm `-XX:+EnableDynamicAgentLoading` để “làm warning biến mất” mà không đánh giá mục đích và độ tin cậy.
6. Giữ JDK matrix (ví dụ LTS đang hỗ trợ + JDK mới định triển khai) và ghi chính xác runtime/vendor.

Nếu testing framework quản lý JVM forks, config options ở **forked test JVM**, không nhất thiết ở Maven/Gradle daemon đang điều phối. Kiểm tra process tree/actual Java command để tránh sửa nhầm JVM.

### 8.5. APM/observability agent rollout

Một APM agent có thể chèn tracing vào network clients hoặc database drivers. Trước rollout:
- Verify artifact integrity (checksum/signature/release provenance).
- Review tương thích JDK/GC/library versions và startup time overhead.
- Cấu hình explicit `-javaagent` ở process owner.
- Chỉ thêm `Can-*` capabilities nếu agent vendor thật sự yêu cầu.
- Kiểm thử stack traces, latency, exceptions và data collection.
- Xác định payload nào có thể chứa secrets/PII.
- Giữ rollback path: startup JAR/flag có thể gỡ bằng deployment revision.
- Không ẩn agent injection như một “side effect” không có trong config.

## 9. Không trộn lẫn Agent-Class, Launcher-Agent-Class và JVM policy

Có ba cách khởi động Java agent hiện hành:

| Mechanism | Manifest attribute | Callback | Phụ thuộc `EnableDynamicAgentLoading`? |
| --- | --- | --- | --- |
| `java -javaagent:agent.jar ...` | `Premain-Class` | `premain` trước app main | **Không**, vì là startup |
| `VirtualMachine.loadAgent(agent.jar)` trên JVM đang chạy | `Agent-Class` | `agentmain` sau startup | **Có**, với HotSpot target policy |
| `java -jar app-with-agent.jar` | `Launcher-Agent-Class`, thêm `Main-Class` | `agentmain` trước app main | Là **startup bundled** mechanism, không phải external dynamic attach |

**Dù callback là `agentmain`**, bundled launcher không đồng nghĩa dynamic attach: `Launcher-Agent-Class` được launcher dùng lúc startup. Chính thời điểm và mechanism khởi chạy mới quyết định JEP 451 policy path.

### 9.1. Trạng thái của agent JAR không thể suy từ filename

Một file `observability.jar` có thể vừa có Premain-Class vừa có Agent-Class hoặc chỉ một trong hai. Nếu `-javaagent` báo thiếu Premain-Class, bạn phải build/chọn đúng artifact chứ không bật thêm `EnableDynamicAgentLoading`. Nếu `loadAgent` báo Agent-Class missing, cũng không sửa bằng cách truyền `-javaagent` vào running JVM — JVM options phải được chọn ở startup.

### 9.2. Java agents và native JVM TI agents

JEP 451 áp dụng cảnh báo cho **Java** và **JVM TI** agents nạp động. Một JVM TI agent có thể dùng `-agentlib`/`-agentpath` lúc startup và các thao tác load native tương ứng được provider hỗ trợ. Không coi `-javaagent` là dạng duy nhất của mọi agents, hoặc nghĩ rằng flag dynamic policy chỉ liên quan tới Java bytecode JARs. Ví dụ Java trong bài kiểm thử **Java agent JAR**, không thử native library/JNI; không diễn giải output thay cho native agents.

## 10. Tác dụng của các công cụ serviceability

### 10.1. Attach API rộng hơn loadAgent

Module `jdk.attach` cung cấp `com.sun.tools.attach.VirtualMachine`. Ngoài `loadAgent`, một VM implementation có thể hỗ trợ các tác vụ đọc system properties, kích hoạt management agents hoặc những thao tác serviceability khác. Vì vậy:

`-XX:-EnableDynamicAgentLoading` **không tương đương** `-XX:+DisableAttachMechanism`.

Trong fixture opt-out, chính chương trình đã:
- Kết nối được với child (`VirtualMachine.attach` không ném).
- Bị từ chối `vm.loadAgent(...)`.
- Gọi `vm.detach()` sau thất bại trong `finally`.

Đó là tình huống rất quan trọng để giải thích error logs. Một tool có thể nói “Attached to JVM” nhưng không đồng nghĩa agent code đã chạy.

### 10.2. Chính sách tắt attach ảnh hưởng các công cụ khác

Khi dùng `-XX:+DisableAttachMechanism`, một số commands như `jcmd <pid> ...` hoặc `jstack <pid>` có thể không dùng được vì phụ thuộc Attach mechanism. Không dùng flag này khi ứng dụng cần on-demand heap/thread dump/diagnostics mà chưa thiết kế đường thay thế. Giải pháp thay thế có thể là JFR đã cấu hình, JVM logs, monitoring endpoints có access controls, hoặc startup diagnostics; lựa chọn tùy requirements và JVM vendor.

### 10.3. Remote JMX không tự là dynamic agent load

Một remote JMX connection và một Java agent là các khái niệm khác nhau. JMX có authentication/network/TLS policy riêng, còn Instrumentation agent là code chạy **trong target JVM**. Không dùng access tới JMX như bằng chứng người dùng có quyền `loadAgent`, và không dùng Attach API như cách cấu hình remote JMX không xác thực.

## 11. Chính sách JDK mới: cách tránh phụ thuộc vào mặc định

### 11.1. Test cả “explicitly allowed” và “explicitly denied”

Một CI check hữu ích:
- **Opt-in scenario:** Target JVM chạy với `-XX:+EnableDynamicAgentLoading`, attach tool được phép, authorized Java agent load thành công.
- **Opt-out scenario:** Target JVM chạy với `-XX:-EnableDynamicAgentLoading`, tool attach được nhưng `loadAgent` bị từ chối.
- **Startup scenario:** Target JVM chạy `-XX:-EnableDynamicAgentLoading` nhưng có `-javaagent`, agent `premain` vẫn thành công.
- **Attach-off scenario:** Target dùng `-XX:+DisableAttachMechanism`, external attach bị từ chối.

**Không phụ thuộc mặc định** vì đó chính là điều có thể thay đổi theo phiên bản. Trong code fixture có một case default riêng `jdk24Default` để minh họa hành vi JDK 24, nhưng kết luận deployment nên lấy từ explicit options.

### 11.2. Phân biệt Java SE contract với HotSpot implementation note

Java SE `java.lang.instrument` specification định nghĩa callback/manifest semantics. Nó cho phép implementation có hoặc không có cơ chế nạp agent vào JVM đang chạy. HotSpot cung cấp `-XX:+EnableDynamicAgentLoading` như một tùy chọn implementation-specific để opt in và suppress warning. OpenJ9 cũng tài liệu hóa tên flag tương tự, nhưng defaults và provider behaviors vẫn cần tra version cụ thể. Không coi mọi `-XX` option là tiêu chuẩn Java SE.

### 11.3. Default JDK 24 là kết quả quan sát, không là chân lý vĩnh viễn

Bài thực chạy trên OpenJDK 24 Windows: nếu không chỉ định `EnableDynamicAgentLoading`, dynamic loading **vẫn hoạt động** và có warning. Oracle JDK 26 package documentation vẫn mô tả warning/opt-in. Nhưng nếu bạn nâng cấp lên một JDK tương lai đổi default, điều đó không làm bài “sai” — tài liệu đã phân biệt chính sách hiện hành theo version với kỳ vọng future-proof: **explicit owner decision**.

### 11.4. Nên có một cấu hình agent inventory

Trước khi cập nhật JDK:
1. Liệt kê startup agent flags đã được phê duyệt trong deployment manifest.
2. Định danh tools có khả năng attach sau startup (profiler, test mocking, on-demand instrumentation).
3. Kiểm tra có library nào tự attach không kiểm soát.
4. Ghi chính sách target JVM cho phép/không cho dynamic load.
5. Ghi runtime build/vendor/JDK module requirements, không chỉ major version.
6. Xây ma trận test startup/opt-in/opt-out/attach-off.
7. Bố trí change approval, artifact provenance, migration và rollback.

## 12. Các lỗi thực tế và cách đọc đúng

| Triệu chứng | Tầng nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `WARNING: A Java agent has been loaded dynamically` | JEP 451 default warning | Xác định agent + chủ sở hữu; chuyển startup hoặc opt-in được phê duyệt |
| `AgentLoadException` với `-XX:-EnableDynamicAgentLoading` | JVM đã từ chối dynamic agent loading | Không bypass policy; owner quyết định có cần opt-in không |
| `AttachNotSupportedException` với `-XX:+DisableAttachMechanism` | Mechanism tắt trước bước loadAgent | Review target JVM config và operational requirements |
| Attach thành công nhưng application không đổi | `loadAgent` thất bại hoặc agent callback không chạy | Kiểm tra event/callback log + target property, không chỉ “attached” |
| `-javaagent` chạy dù dynamic off | Không phải lỗi | Startup agents là cơ chế khác |
| Agent JAR thiếu `Premain-Class` | Sai manifest cho startup | Dùng artifact có Premain-Class hợp lệ |
| Agent JAR thiếu `Agent-Class` | Sai manifest cho dynamic path | Chỉ dùng authorized dynamic load với đúng Agent-Class |
| Agent class not found | Packaging/classloader issue | `jar --list`, binary names, dependencies |
| Agentmain ném exception | Initialization error trong target | Trace failure, rollback; đừng coi process còn chạy là success |
| Agent đăng ký transformer nhưng không retransform được | `Can-Retransform-Classes` thiếu, VM không hỗ trợ, hoặc class không modifiable | Probe capability và class-specific restrictions |
| `java.lang.instrument` API không có trong runtime image | Missing `java.instrument` module | Kiểm tra `jlink` image/module graph |
| `com.sun.tools.attach` không tìm thấy | Missing `jdk.attach` hoặc dùng JRE-like image | Dùng JDK có module, hoặc bỏ phụ thuộc attach khỏi app |
| Self-attach bị từ chối | HotSpot self-attach policy khác external attach | Ưu tiên startup; không giả định self attach được phép |
| Application vẫn hoạt động nhưng test có dynamic warning | Test dependency đang attach | Xác định framework, cấu hình forked JVM explicit |
| Warning biến mất sau bật +flag | Warning bị suppress do opt-in | **Không có nghĩa artifact đã được security review** |
| `jcmd` không kết nối vào JVM | Có thể attach mechanism disabled | Kiểm tra JVM flags, OS/container permissions |
| Dùng một `-XX` flag trên JVM vendor khác bị lỗi | Implementation-specific flag | Tra provider docs và supported version |
| Kết quả CLI test khác CI | Khác actual target JVM/options | In JVM startup config được sanitize và Java version |
| Error class name khác JDK 24 | Provider/version khác | Test error *category*, không hardcode toàn bộ message |
| Thread/process leaked sau attach test | Child không được cleanup | Timeout, `destroyForcibly`/`waitFor`, finally, temp-dir cleanup |

### 12.1. Đừng chữa một lỗi security bằng cách xóa hết flags

Ví dụ ai đó thấy warning rồi thêm cả:

```text
-XX:+EnableDynamicAgentLoading
-Djdk.attach.allowAttachSelf=true
```

vào mọi JVM mà không đánh giá: đó **không phải** cấu hình mặc định an toàn. Nếu chỉ cần một coverage/tracing agent, chuyển sang `-javaagent` được quản trị có thể giải quyết gốc rễ. Nếu cần authorized on-demand profiler, chính chủ JVM phải phê duyệt opt-in và quyền thao tác cụ thể.

### 12.2. Triệu chứng “app không start khi cài agent”

Khi `premain` lỗi, JVM startup có thể abort. Phải kiểm tra artifact version/signature, class path, module graph, agent options và compatibility JDK. `-XX:+EnableDynamicAgentLoading` không sửa được lỗi startup `premain`. Có thể rollback bằng cách gỡ agent startup flag theo release process, không nên để service tự bắt exception silently nếu telemetry/agent là dependency cần thiết.

### 12.3. Không lấy output stderr làm bằng chứng duy nhất

Một số providers suppress warning khi opt-in, nhưng absence of warning **không chứng minh một agent chưa được nạp**. Để có bằng chứng tốt hơn, dùng audited deployment configs, manifest inventory, startup logs có kiểm soát, agent health metrics và instrumentation-specific probes. Ngược lại, JEP 451 warning thể hiện một dynamic load attempt/path, không tự đánh giá agent độc hại.

## 13. Quy trình cấu hình an toàn theo vai trò

### 13.1. Developer

- Xác định use case agent: tracing, profiling, mocking, coverage, performance diagnostics.
- Chọn đúng startup/dynamic mechanism và artifact.
- Đo overhead và đảm bảo Java class/module compatibility.
- Không viết library tự self-attach nếu có cấu hình startup hợp lệ.
- Không in secrets trong agentArgs hay system properties.

### 13.2. SRE/platform owner

- Quy định JVM flags và có documentation/approval path.
- Chọn mặc định workload không cần live loading là `-XX:-EnableDynamicAgentLoading` nếu phù hợp.
- Chỉ dùng `-XX:+DisableAttachMechanism` khi đã đánh giá tác động lên serviceability.
- Có plan chẩn đoán JVM khi incident mà không phá security policy.
- Audit startup agent images, mounted JARs, checksums, permissions.
- Giữ đường rollback rollout nếu agent gây startup crash/perf regressions.

### 13.3. Security reviewer

- Đánh giá provenance/supply chain và capability request của agent.
- Kiểm tra ai có quyền thay agent JAR hoặc process JVM flags.
- Xem dynamic attach có thực sự cần, ai có quyền thực hiện, có audit log không.
- Kiểm tra data exposure: stacks, HTTP headers, tokens, PII từ instrumented methods.
- Đánh giá cả native agents, không chỉ Java agent JARs.
- Không coi flag suppress warning là một chứng chỉ an toàn.

### 13.4. QA/CI owner

- Test startup -javaagent ở runtime production-compatible.
- Chạy opt-out test để phát hiện hidden dynamic instrumentation.
- Test opt-in dùng only authorized target process như harness của bài.
- Test failure modes và expected exit statuses.
- So sánh version changes/release notes thay vì hardcode default.
- Dọn child processes/test artifacts để test không ảnh hưởng máy developer.

## 14. Checklist áp dụng trên JDK hiện đại

- [ ] Xác định rõ version/vendor của **JVM đích**, không chỉ Java CLI hiện tại của terminal.
- [ ] Biết agent là Java Instrumentation JAR hay native JVM TI library.
- [ ] Có owner/approval cho artifact và runtime invocation.
- [ ] Nếu startup agent, có `Premain-Class` và `-javaagent` trong JVM options trước application main.
- [ ] Nếu dùng bundled launcher, hiểu `Launcher-Agent-Class` là startup mechanism riêng.
- [ ] Nếu phải dynamic attach, có `Agent-Class` và `agentmain` hợp lệ.
- [ ] Dùng explicit `-XX:+EnableDynamicAgentLoading` **chỉ khi owner quyết định cho phép**.
- [ ] Dùng `-XX:-EnableDynamicAgentLoading` cho workloads không cần live agent injection khi phù hợp.
- [ ] Không nhầm `-XX:-EnableDynamicAgentLoading` với `-XX:+DisableAttachMechanism`.
- [ ] Đánh giá tác động `DisableAttachMechanism` tới tools vận hành.
- [ ] Không dùng `jdk.attach.allowAttachSelf` như shortcut trái policy.
- [ ] Không dùng `jdk.instrument.traceUsage` như một permission switch.
- [ ] Với cờ `Can-*`, chỉ xin capabilities thực sự cần.
- [ ] Với class cụ thể, kiểm tra `isModifiableClass`/VM restrictions trước khi retransform.
- [ ] Có artifact integrity verification và rollback plan.
- [ ] Ghi agent/version/options vào deployment inventory (sanitize secrets).
- [ ] Không bật dynamic agents trong ứng dụng người khác chỉ để chạy test.
- [ ] Test trên JDK/provider/runtime flags mục tiêu.
- [ ] Kiểm thử warning behavior và attach/agent failures theo categories.
- [ ] Dùng JFR/logging/metrics có access control cho operational visibility.
- [ ] Có CI test với `-XX:-EnableDynamicAgentLoading` để không lệ thuộc default tương lai.

## 15. Bài tập thực hành

**Bài 1 — Startup policy:** Dùng `-XX:-EnableDynamicAgentLoading` cùng `-javaagent:policy-agent.jar`. Vì sao `premain` vẫn chạy? Kiểm tra `target.agent=premain`.

**Bài 2 — Xác nhận policy opt-in:** Đổi child JVM thành `-XX:+EnableDynamicAgentLoading`. Cho parent đã được ủy quyền `loadAgent` và xác nhận không có warning JEP 451.

**Bài 3 — Opt-out:** Đổi thành `-XX:-EnableDynamicAgentLoading`. Phân biệt việc `VirtualMachine.attach` thành công với `loadAgent` bị từ chối.

**Bài 4 — Disable attach:** Dùng `-XX:+DisableAttachMechanism` trên child JVM riêng. Vì sao lúc này không đến được bước `loadAgent`?

**Bài 5 — Default warning:** Chạy child JVM trên JDK 24 không chỉ định dynamic flag. Xác nhận cảnh báo JEP 451, sau đó thử một JDK khác để ghi nhận behavior version-specific thay vì sửa bằng hardcode.

**Bài 6 — Manifest capability:** Thêm `Can-Retransform-Classes: true` vào agent manifest trong thư mục thử. Kiểm tra runtime `isRetransformClassesSupported`, giải thích tại sao vẫn không suy ra mọi class modifiable.

**Bài 7 — Thiếu Agent-Class:** Tạo JAR chỉ có `Premain-Class`, chạy authorized dynamic `loadAgent` trong child; kiểm tra lỗi và nguyên nhân manifest.

**Bài 8 — Trace usage:** Chạy JVM test với `-Djdk.instrument.traceUsage`; kiểm tra log và tắt property sau khi debug. Không log secrets.

**Bài 9 — Shell quoting:** Cấu hình một đường dẫn agent JAR có spaces trong thư mục test, so Windows PowerShell và POSIX shell quoting mà không đưa secret vào options.

**Bài 10 — CI:** Viết test build `policy-agent.jar`, chạy baseline/startup/opt-in/opt-out/attach-off. Đảm bảo child JVM timeout và cleanup trong `finally`.

**Bài 11 — Production readiness:** Lập checklist review nếu một APM agent cần startup `-javaagent`; chọn least-privilege Can-* flags và rollback deployment.

**Bài 12 — Mocking tool:** Tìm library có hidden dynamic attach trong test suite. Đánh giá chuyển sang startup agent tường minh trong forked test JVM.

**Bài 13 — Serviceability tradeoff:** Đánh giá nhu cầu `jcmd`/`jstack` khi muốn bật `DisableAttachMechanism`. Thiết kế cách thu thread dump/JFR khác được phê duyệt.

**Bài 14 — Provider comparison:** So HotSpot và OpenJ9 docs về dynamic agent loading flag. Không áp mặc định một provider sang provider khác.

## 16. Câu hỏi ôn tập

**1. Startup agent khác dynamic agent ở đâu?** Startup được JVM khai báo trước app main; dynamic load thêm agent sau startup vào JVM đang chạy.

**2. JEP 451 được giới thiệu ở JDK nào?** JDK 21.

**3. JEP 451 có yêu cầu mọi JDK 26 mặc định tắt agent không?** Không; phải đọc trạng thái đúng version/provider.

**4. `-XX:+EnableDynamicAgentLoading` nghĩa gì?** HotSpot owner opt-in cho dynamic agent loading và suppress JEP 451 warning tương ứng.

**5. `-XX:-EnableDynamicAgentLoading` có ngăn `-javaagent` lúc startup không?** Không, hai paths khác nhau.

**6. Có attach thành công rồi bị từ chối loadAgent không?** Có, demonstrated với explicit opt-out.

**7. `-XX:+DisableAttachMechanism` làm gì?** Tắt attach mechanism của HotSpot, có thể ảnh hưởng serviceability.

**8. `AgentLoadException` và `AttachNotSupportedException` là cùng lỗi không?** Không; khác layer.

**9. `-Djdk.attach.allowAttachSelf` có tự cấp quyền nạp agent không?** Không.

**10. `-Djdk.instrument.traceUsage` có bật loading policy không?** Không, dùng để trace các instrumentation API usages.

**11. Agent startup cần manifest attr nào?** `Premain-Class`.

**12. Dynamic Java agent cần attr nào?** `Agent-Class`.

**13. Bundled JAR agent dùng attr nào?** `Launcher-Agent-Class`, cùng app `Main-Class`.

**14. `Launcher-Agent-Class` gọi method nào?** `agentmain` trước main, nhưng là startup path.

**15. `Can-Retransform-Classes: true` có tự bật dynamic agent loading không?** Không.

**16. JVM true `isRetransformClassesSupported` có bảo đảm retransform mọi class không?** Không.

**17. Agent options có nên chứa password không?** Không, command line/logs có thể lộ.

**18. Một JDK 24 mặc định tải agent động thì một JDK tương lai có luôn như vậy không?** Không.

**19. “Không có warning” nghĩa là không có agent?** Không; opt-in suppress warning.

**20. Trong bài, child process nào được attach?** JVM con do harness chủ động khởi chạy.

**21. Ai nên quyết định bật dynamic attach trên production?** Owner/operator JVM theo security policy.

**22. Có nên disable attach mechanism mà không hỏi SRE không?** Không, có thể mất công cụ chẩn đoán.

**23. Có cách giảm phụ thuộc hidden self-attach không?** Dùng startup `-javaagent` minh bạch cho agent được phê duyệt.

**24. Java SE có buộc mọi JVM hỗ trợ Attach API không?** Không, `jdk.attach` là khả năng JDK/provider-specific.

**25. `java.lang.instrument` thuộc module nào?** `java.instrument`.

**26. `com.sun.tools.attach.VirtualMachine` thuộc module nào?** `jdk.attach`.

**27. Nếu warning xuất hiện trong test dù test pass, nên làm gì?** Xác định nguồn dynamic instrumentation và owner-approved deployment path.

**28. 40/40 checks có bảo đảm production an toàn không?** Không, chỉ kiểm chứng fixture chính sách trên OpenJDK 24.

## 17. Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — java.lang.instrument package specification](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent lifecycle, startup/late loading, warning, manifest attributes, HotSpot option note.
- [Oracle Java SE 26 — Instrumentation](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): runtime support, transformers, redefine/retransform/modifiability.
- [Oracle Java SE 26 — VirtualMachine (Attach API)](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): `attach`, `loadAgent`, `detach` và loại lỗi.
- [Oracle Java SE 26 — AgentLoadException](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.attach/com/sun/tools/attach/AgentLoadException.html): lỗi không thể load agent.
- [Oracle Java SE 26 — AttachNotSupportedException](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.attach/com/sun/tools/attach/AttachNotSupportedException.html): lỗi không hỗ trợ attach.
- [Oracle Java SE 26 — jdk.attach module](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.attach/module-summary.html): Attach API platform/JDK module.
- [Oracle Java SE 26 — java.instrument module](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/module-summary.html): Java agent instrumentation module.
- [Oracle Java SE 26 — JAR manifest specification](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html): main attributes, manifest sections.
- [Oracle Java SE 26 — jar command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html): packaging và manifest.
- [OpenJDK JEP 451](https://openjdk.org/jeps/451): integrity-by-default và warning dynamic agent loading.
- [Oracle JDK 21 Release Notes — JEP 451 behavior](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): `-XX:+/-EnableDynamicAgentLoading` và `-Djdk.instrument.traceUsage`, historical default.
- [Inside Java — Evolving Integrity by Default](https://inside.java/2025/01/03/evolving-default-integrity/): vì sao nên startup agent minh bạch.
- [OpenJ9 — EnableDynamicAgentLoading option](https://eclipse.dev/openj9/docs/xxenabledynamicagentloading/): so sánh provider-specific policy.

## Kết luận

Trong JDK hiện đại, **đúng chính sách** quan trọng hơn việc một API `loadAgent` có thể gọi được. Khi chủ ứng dụng **muốn dùng agent đã phê duyệt**, `-javaagent` lúc startup diễn đạt rõ ràng lựa chọn đó. Khi cần **on-demand dynamic loading**, owner của **JVM đích** phải opt in và hệ thống phải có quyền attach, manifest `Agent-Class` hợp lệ, cùng logging/audit/rollback. `-XX:-EnableDynamicAgentLoading` từ chối dynamic load nhưng **không chặn `-javaagent` startup**; `-XX:+DisableAttachMechanism` lại chặn tầng attach và ảnh hưởng nhiều tooling serviceability hơn. **Đừng nhầm ba `Can-*` của agent manifest với quyền dynamic loading của target JVM**.

Bộ Java 17+ hoàn chỉnh trong bài đã thực hiện **40/40 checks PASS** trên OpenJDK 24 Windows, chứng minh chính xác bốn hành vi: explicit opt-in thành công không warning; opt-out attach được nhưng loadAgent bị từ chối; JDK 24 default load thành công nhưng warning; attach mechanism off từ chối ngay tại attach. Startup `premain` vẫn chạy khi dynamic policy off. Những quan sát này có giới hạn theo runtime — ưu tiên cấu hình tường minh, không dựa vào default sẽ thay đổi trong các JDK tương lai.
