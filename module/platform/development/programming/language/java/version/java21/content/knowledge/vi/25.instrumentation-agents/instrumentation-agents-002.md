# Phân biệt agent nạp lúc JVM khởi động với dynamic attach

Java agent là thành phần có thể quan sát hoặc thay đổi hành vi class khi JVM nạp và chạy ứng dụng. Trong Java 21, có hai cách phổ biến để đưa một Java agent vào JVM: nạp ngay khi khởi động bằng `-javaagent` và nạp vào một JVM đang chạy bằng Attach API. Hai cách này dùng entry point và thời điểm thực thi khác nhau, vì vậy ảnh hưởng đến khả năng instrument class, cách triển khai và chính sách bảo mật.

Agent nạp lúc khởi động gọi phương thức `premain(...)` trước khi `main` của ứng dụng chạy. Dynamic attach gọi `agentmain(...)` sau khi JVM đã khởi động. Với agent dùng cho cấu hình production đã biết trước, startup loading thường dễ kiểm soát hơn. Dynamic attach hữu ích cho công cụ chẩn đoán hoặc instrumentation cần bật trong lúc hệ thống đang chạy, nhưng phải được cho phép và quản lý như một thao tác có quyền cao.

## 1. Hai cơ chế nạp agent

| Tiêu chí | Startup agent | Dynamic attach |
|---|---|---|
| Cách nạp | `-javaagent:<jar>[=<options>]` | Attach API, thường gọi `VirtualMachine.loadAgent(...)` |
| Entry point | `premain(String, Instrumentation)` hoặc `premain(String)` | `agentmain(String, Instrumentation)` hoặc `agentmain(String)` |
| Thời điểm | Trong quá trình khởi động JVM, trước `main` của ứng dụng | Sau khi JVM mục tiêu đã chạy |
| Manifest chính | `Premain-Class` | `Agent-Class` |
| Class chưa được nạp | Có thể đăng ký transformer trước khi application class được nạp | Có thể instrument các class sẽ được nạp sau khi attach |
| Class đã được nạp | Có thể retransform/redefine nếu hỗ trợ và class có thể sửa đổi | Cần retransform/redefine nếu muốn thay đổi class đã nạp; phải được hỗ trợ |
| Phù hợp | APM, coverage, profiling hoặc instrumentation luôn bật từ đầu | Điều tra sự cố, chẩn đoán hoặc bật agent theo yêu cầu vận hành |

Hai cơ chế đều có thể nhận đối tượng `java.lang.instrument.Instrumentation`. Khác biệt chính là thời điểm JVM gọi agent và khả năng quan sát các class đã được nạp trước khi agent bắt đầu.

## 2. Startup loading với -javaagent và premain()

JVM nhận Java agent qua option `-javaagent`. File JAR của agent phải có manifest attribute `Premain-Class` trỏ đến class chứa phương thức `premain`.

Ví dụ manifest:

```text
Manifest-Version: 1.0
Premain-Class: com.example.agent.StartupAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
```

Hai capability cuối chỉ khai báo nếu agent thực sự cần và triển khai các thao tác tương ứng. Nếu không khai báo, agent không được mặc định có quyền retransformation hoặc redefinition.

Class agent có thể khai báo một trong hai chữ ký sau:

```java
package com.example.agent;

import java.lang.instrument.Instrumentation;

public final class StartupAgent {
    public static void premain(String agentArgs, Instrumentation instrumentation) {
        System.out.println("Startup agent args: " + agentArgs);
        System.out.println("Retransform supported: "
                + instrumentation.isRetransformClassesSupported());
    }

    private StartupAgent() { }
}
```

JVM ưu tiên chữ ký hai tham số có `Instrumentation`. Nếu không có chữ ký đó, JVM tìm phiên bản chỉ nhận `String`. Tham số `agentArgs` là chuỗi được truyền sau dấu `=` trong option `-javaagent`; nó có thể là `null` nếu không có tham số.

Khởi chạy ứng dụng:

```bash
java -javaagent:startup-agent.jar=mode=observe -jar application.jar
```

Khi JVM xử lý option, agent được nạp và `premain` được gọi trước khi JVM gọi phương thức `main` của ứng dụng. Vì vậy agent có thể đăng ký `ClassFileTransformer` sớm để xử lý các class được nạp sau đó.

Có thể chỉ định nhiều option `-javaagent`; các agent được khởi tạo theo thứ tự xuất hiện trên command line. Mỗi agent cần manifest và class entry point hợp lệ. Nếu startup agent không khởi tạo được, JVM không thể tiếp tục khởi chạy ứng dụng theo cách thông thường; đây là lý do cần kiểm thử agent cùng đúng JDK và cấu hình production.

## 3. Đăng ký transformer trong startup agent

Agent thường đăng ký `ClassFileTransformer` để nhận bytecode trước khi JVM định nghĩa class. Transformer có thể trả bytecode đã biến đổi hoặc trả `null` nếu không muốn thay đổi class.

Ví dụ minh họa đăng ký transformer mà không thay đổi bytecode:

```java
public final class StartupAgent {
    public static void premain(String args, Instrumentation instrumentation) {
        ClassFileTransformer transformer = new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                if (className != null && className.startsWith("com/example/")) {
                    // Có thể phân tích bytecode hoặc chuyển cho thư viện
                    // instrumentation đã được kiểm thử.
                }

                return null; // Giữ nguyên class hiện tại.
            }
        };

        instrumentation.addTransformer(
                transformer,
                instrumentation.isRetransformClassesSupported()
        );
    }
}
```

Tên class trong `ClassFileTransformer` dùng dấu `/` thay cho dấu `.`. Transformer phải an toàn với nhiều class loader và không nên giả định mọi class đều thuộc application class loader. Với agent thực sự sửa bytecode, nên dùng thư viện bytecode đã được kiểm thử, giới hạn package cần xử lý và kiểm tra tương thích với class file version của JDK mục tiêu.

## 4. Dynamic attach với Attach API và agentmain()

Dynamic attach cho phép một process khác kết nối tới JVM đang chạy và yêu cầu JVM nạp một agent JAR. Agent JAR cần khai báo `Agent-Class` trong manifest:

```text
Manifest-Version: 1.0
Agent-Class: com.example.agent.LiveAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
```

Class agent cung cấp `agentmain`:

```java
package com.example.agent;

import java.lang.instrument.Instrumentation;

public final class LiveAgent {
    public static void agentmain(String agentArgs,
                                 Instrumentation instrumentation) {
        System.out.println("Dynamic agent args: " + agentArgs);
        System.out.println("Retransform supported: "
                + instrumentation.isRetransformClassesSupported());
    }

    private LiveAgent() { }
}
```

JVM gọi `agentmain` khi agent được load vào một process đang chạy. Nếu agent JAR có cả `Premain-Class` và `Agent-Class`, nó có thể hỗ trợ cả hai cơ chế; entry point nào được gọi phụ thuộc cách agent được nạp.

### Process điều khiển gọi VirtualMachine.loadAgent()

Attach API nằm trong module `jdk.attach`. Một chương trình điều khiển có thể kết nối đến process đích bằng PID, nạp agent JAR rồi detach:

```java
import com.sun.tools.attach.VirtualMachine;

public final class AttachClient {
    public static void main(String[] args) throws Exception {
        String pid = args[0];
        String agentJar = args[1];

        VirtualMachine vm = VirtualMachine.attach(pid);
        try {
            vm.loadAgent(agentJar, "mode=diagnostic");
        } finally {
            vm.detach();
        }
    }
}
```

Biên dịch và chạy chương trình điều khiển trên JDK có module `jdk.attach`:

```bash
javac --add-modules jdk.attach AttachClient.java
java --add-modules jdk.attach AttachClient <pid> /opt/agents/live-agent.jar
```

Process đích phải hỗ trợ attach và process điều khiển phải có quyền hệ điều hành phù hợp. `VirtualMachine.attach(pid)` không phải cơ chế kết nối từ xa tùy ý qua mạng; nó sử dụng cơ chế attach của nền tảng để giao tiếp với JVM mục tiêu trên cùng môi trường hệ thống được hỗ trợ.

Trong code vận hành thực tế, cần xử lý riêng các lỗi attach, load agent và detach. Không được giả định `loadAgent` thành công chỉ vì `attach` thành công. Agent JAR phải có `Agent-Class` hợp lệ, tương thích với JDK đích và được phép nạp.

## 5. Thời điểm nạp ảnh hưởng đến class instrumentation

Startup agent có cơ hội đăng ký transformer trước khi phần lớn application class được nạp. Dynamic agent bắt đầu muộn hơn, khi ứng dụng có thể đã chạy và nhiều class đã được định nghĩa.

| Trạng thái class | Startup agent | Dynamic agent |
|---|---|---|
| Class chưa được nạp | Transformer có thể xử lý trong lần nạp đầu tiên | Transformer mới có thể xử lý nếu class được nạp sau khi agent đăng ký |
| Class đã được nạp | Có thể yêu cầu retransform/redefine nếu capability và class cho phép | Cũng cần retransform/redefine nếu muốn thay đổi bytecode hiện tại |
| Class không modifiable | Không thể sửa bằng retransform/redefine | Không thể sửa bằng retransform/redefine |
| Class đã chạy method trước khi agent được nạp | Agent không thể đảo ngược các hành vi đã xảy ra | Dynamic attach không thể quan sát lại lịch sử thực thi trước đó |

Dynamic attach không có nghĩa JVM tự động chạy lại mọi class qua transformer. Sau khi đăng ký transformer, agent có thể yêu cầu retransformation các class đã nạp nếu:

- Manifest và JVM cho phép retransformation.
- `Instrumentation.isRetransformClassesSupported()` trả `true`.
- Từng class được chọn cho phép sửa đổi, kiểm tra bằng `isModifiableClass(clazz)`.
- Transformer được đăng ký với khả năng retransformation nếu cần tham gia vào quy trình đó.

Ví dụ kiểm tra trước khi yêu cầu retransformation:

```java
static void retransformIfSupported(
        Instrumentation instrumentation,
        Class<?> target) throws UnmodifiableClassException {

    if (!instrumentation.isRetransformClassesSupported()) {
        throw new UnsupportedOperationException("Retransformation is not supported");
    }

    if (!instrumentation.isModifiableClass(target)) {
        throw new UnmodifiableClassException(target.getName());
    }

    instrumentation.retransformClasses(target);
}
```

`retransformClasses` yêu cầu JVM chạy lại các transformer có tham gia retransformation đối với class đã nạp. Transformer có thể nhận bytecode đầu vào theo quy tắc retransformation của JVM; không nên giả định bytecode truyền vào luôn là kết quả đã biến đổi bởi chính lần chạy trước của transformer.

## 6. Giới hạn của redefine và retransform

Instrumentation API không phải công cụ thay thế tùy ý cấu trúc class đang chạy. Với HotSpot/JVM tương thích Java 21, class retransformation/redefinition có các giới hạn cấu trúc quan trọng. Thông thường, agent có thể thay đổi method body, nhưng không thể tự do:

- Thêm, xóa hoặc đổi tên field hay method.
- Thay đổi chữ ký method hoặc kiểu field.
- Thay đổi superclass hoặc danh sách interface đã triển khai.
- Thay đổi các thuộc tính cấu trúc class bị JVM giới hạn trong quy trình redefine/retransform.

Nếu transformer trả về bytecode vi phạm giới hạn, thao tác có thể thất bại bằng `UnmodifiableClassException`, `UnsupportedOperationException` hoặc lỗi định dạng/định nghĩa class tùy trường hợp. Kiểm tra tài liệu `Instrumentation` và `ClassFileTransformer` của đúng JDK đích trước khi dựa vào một thay đổi bytecode cụ thể.

Ngoài ra, việc retransform class không hoàn tác side effect đã xảy ra, không khởi chạy lại static initializer và không làm các object hiện có được tạo lại. Agent cần có kế hoạch tương thích với object và code đã tồn tại trong heap.

## 7. Khả năng của agent và manifest attributes

Manifest của agent khai báo entry point và các capability mà agent muốn JVM cung cấp:

| Manifest attribute | Ý nghĩa |
|---|---|
| `Premain-Class` | Class chứa `premain` cho startup loading |
| `Agent-Class` | Class chứa `agentmain` cho dynamic loading |
| `Can-Redefine-Classes: true` | Agent yêu cầu khả năng redefine class đã nạp |
| `Can-Retransform-Classes: true` | Agent yêu cầu khả năng retransformation class đã nạp |
| `Can-Set-Native-Method-Prefix: true` | Agent yêu cầu khả năng đặt prefix cho native method khi dùng transformer phù hợp |

Khai báo `true` trong manifest là yêu cầu capability, không bảo đảm mọi JVM hoặc mọi class đều có thể thực hiện mọi thay đổi. Kiểm tra các phương thức `isRedefineClassesSupported()`, `isRetransformClassesSupported()`, `isNativeMethodPrefixSupported()` và `isModifiableClass()` trước khi sử dụng.

Chỉ yêu cầu capability thật sự cần. Điều này giúp agent có phạm vi quyền nhỏ hơn và giảm lỗi khi chạy trên các runtime khác nhau.

## 8. Dynamic attach trong Java 21 và cảnh báo JEP 451

JDK 21 vẫn cho phép dynamic loading Java agent theo cơ chế Attach API, nhưng phát ra cảnh báo khi agent được nạp động. Đây là thay đổi được đưa vào qua JEP 451 nhằm chuẩn bị cho việc hạn chế dynamic loading theo mặc định trong một bản JDK tương lai.

Thông điệp cảnh báo có thể cho biết agent được nạp động và đề nghị người vận hành dùng `-XX:+EnableDynamicAgentLoading` nếu việc nạp agent là chủ đích. Cần hiểu đúng:

- Cảnh báo trong JDK 21 không có nghĩa dynamic attach đã bị vô hiệu hóa.
- `-XX:+EnableDynamicAgentLoading` thể hiện rằng việc nạp agent động được dự kiến trong cấu hình JVM và tránh cảnh báo tương ứng.
- Option này không tự nạp agent; process điều khiển vẫn phải thực hiện attach và gọi `loadAgent`.
- Nếu không có nhu cầu dynamic attach, không cần bật option này chỉ để làm mất cảnh báo của một công cụ không rõ nguồn gốc.

Ví dụ khởi chạy JVM cho một môi trường được thiết kế để nhận agent động:

```bash
java \
  -XX:+EnableDynamicAgentLoading \
  -jar application.jar
```

Đối với ứng dụng không cần dynamic attach, có thể chủ động tắt Attach Mechanism bằng `-XX:+DisableAttachMechanism`. Cần đánh giá ảnh hưởng trước khi áp dụng vì các công cụ vận hành dựa trên attach, chẳng hạn một số thao tác `jcmd` hoặc profiler, cũng có thể không hoạt động như mong muốn.

JEP 451 là lý do nên rà soát công cụ APM, profiler, debugger và agent triển khai trong môi trường thật. Nếu agent là thành phần bắt buộc của ứng dụng, startup loading làm rõ dependency ngay trong cấu hình khởi chạy. Nếu vẫn cần dynamic attach, hãy ghi nhận rõ lý do và cấu hình quyền cho phép.

## 9. Rủi ro bảo mật và vận hành

Agent chạy trong tiến trình JVM mục tiêu và có thể có quyền quan sát hoặc thay đổi hành vi code của ứng dụng. Vì vậy, quyền nạp agent gần tương đương quyền can thiệp sâu vào process.

Các biện pháp cần áp dụng:

1. Chỉ nạp agent JAR từ nguồn tin cậy; kiểm tra checksum, chữ ký và quy trình phát hành artifact.
2. Giới hạn user/role hệ điều hành có thể attach vào process.
3. Không mở quyền attach cho người dùng hoặc workload không đáng tin cậy.
4. Dùng `-XX:+DisableAttachMechanism` nếu môi trường không cần attach và đã kiểm tra tác động tới công cụ vận hành.
5. Ghi audit về ai nạp agent, vào process nào, thời điểm nào và agent version nào.
6. Tránh nạp nhiều agent cùng instrument một framework hoặc cùng biến đổi một class nếu chưa kiểm thử thứ tự transformer.
7. Kiểm thử overhead, tương thích class loader, memory leak và khả năng shutdown trước khi triển khai.

Không tải agent JAR trực tiếp từ URL hoặc đường dẫn do request bên ngoài cung cấp. Attach client phải xác thực PID, đường dẫn agent và quyền thao tác từ một kênh quản trị tin cậy.

## 10. Chọn startup agent hay dynamic attach?

| Nhu cầu | Lựa chọn nên cân nhắc | Lý do |
|---|---|---|
| APM hoặc telemetry luôn cần từ đầu request đầu tiên | Startup agent | Transformer có thể được đăng ký trước khi application class được nạp |
| Code coverage cho toàn bộ vòng đời test | Startup agent | Tránh bỏ sót class đã chạy trước khi agent được gắn |
| Bật instrumentation tạm thời khi điều tra production | Dynamic attach | Có thể nạp vào process đang chạy mà không cần khởi động lại, nếu môi trường cho phép |
| Thay đổi method body của class đã nạp | Cả hai, nếu capability và class cho phép | Cần retransform/redefine và tuân thủ giới hạn cấu trúc class |
| Thay đổi field, method signature hoặc superclass của class đã nạp | Không phù hợp với Instrumentation redefine/retransform thông thường | Các thay đổi cấu trúc này bị giới hạn |
| Môi trường không cho phép attach | Startup agent | Agent được nạp qua cấu hình khởi chạy |

Nếu yêu cầu là luôn quan sát mọi class từ đầu, không chọn dynamic attach chỉ vì nó tiện triển khai. Các class đã nạp và hành vi đã xảy ra trước thời điểm attach không thể được quan sát hồi tố.

## 11. Checklist triển khai agent

1. Xác định agent cần chạy từ trước `main` hay chỉ cần bật sau khi JVM hoạt động.
2. Chọn manifest entry point: `Premain-Class` cho `-javaagent`, `Agent-Class` cho dynamic attach.
3. Chỉ khai báo capability redefine/retransform/native prefix khi thực sự cần.
4. Với startup agent, đặt `-javaagent` trong startup command và kiểm tra thứ tự khi có nhiều agent.
5. Với dynamic attach, xác nhận module `jdk.attach`, PID, quyền hệ điều hành, attach mechanism và manifest của agent.
6. Trên JDK 21, xử lý cảnh báo JEP 451 bằng quyết định rõ ràng; chỉ dùng `-XX:+EnableDynamicAgentLoading` khi dynamic loading là chủ đích.
7. Kiểm tra class đã nạp bằng `isModifiableClass` và kiểm tra capability trước khi retransform/redefine.
8. Giữ thay đổi bytecode trong giới hạn cấu trúc class mà JVM cho phép.
9. Kiểm thử trên đúng JDK, provider, framework và class loader của môi trường đích.
10. Ghi audit agent version, thời điểm nạp, process mục tiêu và kết quả thao tác.

## Tài liệu tham khảo chính thức

- [Java SE 21 API — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java SE 21 API — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Java SE 21 API — Attach API VirtualMachine](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html)
- [Java SE 21 — Package java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451)
- [Java SE 21 — java launcher and -javaagent option](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
