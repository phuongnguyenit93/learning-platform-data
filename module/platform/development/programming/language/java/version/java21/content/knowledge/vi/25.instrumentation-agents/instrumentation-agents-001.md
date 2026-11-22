# Mục đích thay đổi chính sách nạp agent trong JDK 21

JDK 21 triển khai JEP 451: **phát cảnh báo khi Java agent hoặc JVM TI agent được nạp động vào một JVM đang chạy**. Thay đổi này chuẩn bị cho định hướng tăng tính toàn vẹn của JVM: trong một bản phát hành tương lai, việc nạp agent động dự kiến sẽ không còn được cho phép mặc định. Agent được nạp ngay lúc khởi động JVM bằng các tùy chọn dòng lệnh như `-javaagent`, `-agentlib` hoặc `-agentpath` không bị cảnh báo bởi thay đổi này.

Trong JDK 21, dynamic agent loading vẫn được cho phép mặc định trên HotSpot; cảnh báo không đồng nghĩa tính năng đã bị vô hiệu hóa. Có thể chủ động cho phép bằng `-XX:+EnableDynamicAgentLoading`, hoặc tắt nạp agent động bằng `-XX:-EnableDynamicAgentLoading` để kiểm tra khả năng tương thích. Mục tiêu là làm rõ ứng dụng nào thực sự cần thay đổi bytecode sau khi JVM đã chạy và chuyển các agent cần thiết sang cấu hình khởi động có thể kiểm soát.

## 1. Agent là gì và vì sao có quyền mạnh?

Java agent là thành phần chạy bên trong tiến trình JVM và có thể quan sát hoặc thay đổi bytecode của lớp. Java Instrumentation API nằm trong package `java.lang.instrument`; JVM TI (JVM Tool Interface) cung cấp giao diện native cho các công cụ cấp thấp hơn như profiler, debugger và công cụ chẩn đoán.

Agent thường được dùng cho:

- Thu thập thông tin hiệu năng, thời gian gọi method và số liệu runtime.
- Theo dõi tracing, coverage hoặc quan sát hành vi ứng dụng.
- Thay đổi bytecode để thêm instrumentation, hỗ trợ mocking hoặc kiểm tra hành vi.
- Hỗ trợ debugger, profiler và công cụ serviceability.

Agent có thể đăng ký `ClassFileTransformer` để biến đổi bytecode khi lớp được nạp hoặc khi được retransformation; tùy khả năng JVM và manifest, agent còn có thể redefine/retransform các lớp đã nạp. Vì agent chạy trong cùng tiến trình và có quyền truy cập rất rộng, việc nạp agent tương đương đưa thêm mã có quyền cao vào ứng dụng.

Do đó, cần xác minh nguồn gốc, phiên bản, chữ ký và nội dung agent JAR/native library trước khi cho phép chạy. Agent không phải sandbox và không nên được xem như plugin không đáng tin cậy.

## 2. Phân biệt nạp agent lúc khởi động và nạp động

Có hai thời điểm chính để đưa agent vào JVM:

| Cách nạp | Thời điểm | Cơ chế thường dùng | Entry point |
|---|---|---|---|
| Startup Java agent | Khi JVM khởi động, trước `main` | `-javaagent:<jar>[=<options>]` | `premain(...)` |
| Startup JVM TI agent | Khi JVM khởi động | `-agentlib:<name>` hoặc `-agentpath:<path>` | `Agent_OnLoad(...)` |
| Dynamic Java agent | Sau khi JVM đã chạy | Attach API, ví dụ `VirtualMachine.loadAgent(...)` | `agentmain(...)` |
| Dynamic JVM TI agent | Sau khi JVM đã chạy | Attach API hoặc công cụ tương ứng | `Agent_OnAttach(...)` |

JEP 451 tập trung vào việc nạp agent sau khi JVM đã chạy. Agent được cấu hình tường minh từ đầu tiến trình vẫn là cách phù hợp khi ứng dụng hoặc môi trường triển khai biết trước cần công cụ instrumentation nào.

## 3. Startup Java agent với -javaagent

Startup Java agent được khai báo trên command line:

```shell
java -javaagent:observability-agent.jar=service=orders -jar app.jar
```

Manifest chính của agent JAR phải khai báo `Premain-Class`:

```text
Manifest-Version: 1.0
Premain-Class: com.example.agent.ObservabilityAgent
Can-Retransform-Classes: true
```

JVM gọi phương thức `premain` trước khi gọi `main` của ứng dụng. Agent có thể nhận `Instrumentation` để đăng ký transformer hoặc sử dụng các chức năng được hỗ trợ:

```java
package com.example.agent;

import java.lang.instrument.Instrumentation;

public final class ObservabilityAgent {
    public static void premain(String agentArgs, Instrumentation instrumentation) {
        System.out.println("Agent options: " + agentArgs);
        instrumentation.addTransformer(new ObservabilityTransformer(), true);
    }
}
```

`ObservabilityTransformer` ở ví dụ là lớp triển khai `ClassFileTransformer` của agent. Ví dụ tập trung vào điểm vào `premain`; transformer thực tế cần xử lý bytecode đúng quy tắc, tránh thay đổi lớp không cần thiết và không làm chậm quá trình nạp lớp.

Một agent có thể cung cấp overload `premain(String, Instrumentation)` hoặc `premain(String)`. Nếu có cả hai, JVM ưu tiên overload nhận `Instrumentation`. Có thể khai báo nhiều `-javaagent` trên cùng command line; các `premain` được gọi theo thứ tự agent xuất hiện.

## 4. Startup JVM TI agent với -agentlib và -agentpath

JVM TI agent là thư viện native, thường được viết bằng C/C++. Có thể nạp lúc khởi động bằng:

```shell
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005 -jar app.jar
```

Ví dụ dùng `jdwp` minh họa một JVM TI agent có sẵn trong JDK. Với native agent riêng, `-agentlib:<name>` tìm thư viện theo quy tắc tìm kiếm của nền tảng; `-agentpath:<path>` chỉ định đường dẫn thư viện cụ thể:

```shell
java -agentpath:/opt/agents/libmonitor.so=mode=observe -jar app.jar
```

Các agent startup này được nạp như một phần cấu hình JVM ngay từ đầu và không thuộc trường hợp dynamic loading mà JEP 451 cảnh báo. Khi vận hành, vẫn phải xác thực thư viện native, kiểm tra tương thích kiến trúc/OS/JDK và giới hạn quyền truy cập file.

## 5. Dynamic Java agent và phương thức agentmain

Dynamic Java agent được đưa vào một JVM đang chạy. Agent JAR phải khai báo `Agent-Class` trong manifest và có phương thức `agentmain`:

```text
Manifest-Version: 1.0
Agent-Class: com.example.agent.LiveDiagnosticsAgent
Can-Retransform-Classes: true
```

```java
package com.example.agent;

import java.lang.instrument.Instrumentation;

public final class LiveDiagnosticsAgent {
    public static void agentmain(String agentArgs, Instrumentation instrumentation) {
        System.out.println("Dynamic agent options: " + agentArgs);
        instrumentation.addTransformer(new DiagnosticsTransformer(), true);
    }
}
```

JVM gọi `agentmain` khi agent được nạp vào tiến trình đang chạy. Phương thức này cần khởi tạo phần cần thiết rồi trả về; không nên giữ quá trình attach trong thời gian dài hoặc thực hiện công việc nặng đồng bộ ngay trong entry point.

Một agent JAR có thể khai báo cả `Premain-Class` và `Agent-Class` nếu muốn hỗ trợ cả startup lẫn dynamic loading. Khi dùng `-javaagent`, JVM gọi `premain`; khi attach vào JVM đang chạy, JVM gọi `agentmain`.

## 6. Attach API và ví dụ nạp agent động

Trong JDK, `com.sun.tools.attach.VirtualMachine` thuộc module `jdk.attach`. Công cụ có thể attach tới một JVM đang chạy, yêu cầu nạp agent JAR, rồi detach:

```java
import com.sun.tools.attach.VirtualMachine;

public class AttachAgent {
    public static void main(String[] args) throws Exception {
        String targetPid = args[0];
        String agentJar = args[1];
        String agentOptions = "mode=observe";

        VirtualMachine vm = VirtualMachine.attach(targetPid);
        try {
            vm.loadAgent(agentJar, agentOptions);
        } finally {
            vm.detach();
        }
    }
}
```

Biên dịch và chạy công cụ attach trong môi trường có module `jdk.attach`:

```shell
javac --add-modules jdk.attach AttachAgent.java
java --add-modules jdk.attach AttachAgent 12345 diagnostics-agent.jar
```

`12345` là PID minh họa của JVM đích. Người dùng chạy công cụ phải có quyền attach phù hợp với hệ điều hành và chính sách runtime. Attach có thể thất bại nếu JVM đích không hỗ trợ, tiến trình bị giới hạn quyền, cơ chế attach bị tắt hoặc agent không khởi tạo được.

Dynamic attach có ích cho chẩn đoán sau khi ứng dụng đã chạy, nhưng cũng cho phép thay đổi mã trong tiến trình mà không cần khởi động lại. Đây chính là khả năng JEP 451 muốn làm rõ và đặt dưới sự chấp thuận tường minh hơn.

## 7. Cảnh báo mới trong JDK 21 theo JEP 451

Khi một Java agent hoặc JVM TI agent được nạp động vào JVM đang chạy mà chưa bật `-XX:+EnableDynamicAgentLoading`, HotSpot phát cảnh báo ra standard error. Nội dung điển hình:

```text
WARNING: A Java agent has been loaded dynamically (...)
WARNING: If a serviceability tool is in use, please run with -XX:+EnableDynamicAgentLoading to hide this warning
WARNING: If a serviceability tool is not in use, please run with -Djdk.instrument.traceUsage for more information
WARNING: Dynamic loading of agents will be disallowed by default in a future release
```

Thông điệp có thể khác đôi chút theo loại agent, provider JDK và phiên bản update. Ý nghĩa chính:

- Agent đã được nạp vào một JVM đang chạy.
- JDK nhắc người vận hành xác nhận việc nạp agent có chủ đích.
- Nếu đây là công cụ serviceability được cho phép, có thể opt-in rõ ràng bằng JVM flag.
- Nếu không biết thành phần nào nạp agent, có thể bật trace để tìm nơi sử dụng Instrumentation API.

Trong JDK 21, dynamic loading vẫn được cho phép mặc định; warning là cảnh báo chuẩn bị cho thay đổi chính sách trong tương lai, không phải thông báo agent đã bị chặn. Agent nạp lúc startup bằng command-line options không phát cảnh báo này.

## 8. EnableDynamicAgentLoading: cho phép hoặc tắt dynamic loading

Trên HotSpot, tùy chọn `EnableDynamicAgentLoading` kiểm soát dynamic agent loading:

| Tùy chọn | Hành vi trong JDK 21 |
|---|---|
| Không chỉ định | Dynamic loading được cho phép; khi nạp agent động, JVM phát cảnh báo |
| `-XX:+EnableDynamicAgentLoading` | Opt-in cho phép nạp agent động và suppress warning |
| `-XX:-EnableDynamicAgentLoading` | Từ chối nạp agent động vào JVM đang chạy |

Cho phép tường minh khi công cụ vận hành thực sự cần attach:

```shell
java -XX:+EnableDynamicAgentLoading -jar app.jar
```

Tắt dynamic loading để kiểm tra ứng dụng và công cụ có còn hoạt động khi không thể attach agent sau startup:

```shell
java -XX:-EnableDynamicAgentLoading -jar app.jar
```

Flag này phải được đặt khi khởi chạy JVM đích. Thêm flag vào command line của chương trình attach không thay đổi chính sách của tiến trình đích. Đây là tùy chọn triển khai HotSpot, không phải một API Java SE portable áp dụng giống nhau cho mọi JVM implementation.

Không nên thêm `-XX:+EnableDynamicAgentLoading` một cách máy móc chỉ để xóa warning. Trước tiên cần xác định agent nào đang được nạp, ai yêu cầu nó và vì sao không thể nạp ở startup. Nếu agent là thành phần cần thiết và được quản lý, opt-in là quyết định vận hành có chủ đích; nếu agent xuất hiện ngoài dự kiến, cần điều tra thay vì che cảnh báo.

## 9. Truy tìm thành phần sử dụng Instrumentation API

JDK 21 cung cấp system property `jdk.instrument.traceUsage`. Khi bật, việc sử dụng các API trong `java.lang.instrument` sẽ tạo trace và stack trace, giúp xác định thư viện hoặc thành phần gọi API instrumentation:

```shell
java -Djdk.instrument.traceUsage -jar app.jar
```

Hoặc:

```shell
java -Djdk.instrument.traceUsage=true -jar app.jar
```

Property này phục vụ điều tra, không bật/tắt dynamic loading và không tự ngăn agent được nạp. Nó có thể tạo nhiều log nếu ứng dụng hoặc thư viện gọi Instrumentation API thường xuyên; chỉ bật khi cần truy tìm nguồn sử dụng.

Trace có thể giúp tìm thư viện như agent framework, profiler hoặc mocking tool đang sử dụng Instrumentation API. Với JVM TI native agent không đi qua Java Instrumentation API, property này không thay thế log/cơ chế chẩn đoán riêng của native agent.

## 10. Vì sao JDK thay đổi chính sách?

JEP 451 cân bằng hai mục tiêu:

- **Serviceability:** profiler, debugger, monitoring và công cụ chẩn đoán đôi khi cần gắn vào JVM đang chạy để thu thập thông tin hoặc instrument code mà không khởi động lại.
- **Integrity by default:** ứng dụng và người vận hành nên biết trước mã nào có quyền thay đổi bytecode trong tiến trình. Việc một tiến trình khác âm thầm attach và nạp agent có thể làm thay đổi hành vi của ứng dụng sau khi đã khởi chạy.

Nạp agent lúc startup giúp việc triển khai dễ kiểm kê hơn: agent xuất hiện trong command line, cấu hình container/service hoặc manifest của ứng dụng. Dynamic attach vẫn có chỗ dùng cho serviceability, nhưng cần được cho phép tường minh thay vì trở thành khả năng mặc định không được chú ý.

Thay đổi này không loại bỏ Java Instrumentation API, không cấm startup agents và không làm mọi profiler/debugger ngừng hoạt động. Các công cụ có thể chuyển sang startup agent, hoặc yêu cầu người vận hành opt-in khi thật sự cần dynamic attach.

## 11. Cách chuẩn bị ứng dụng và công cụ

Khi nâng ứng dụng lên JDK 21, nên kiểm kê agent và cách chúng được nạp:

1. Kiểm tra command line của service để tìm `-javaagent`, `-agentlib` và `-agentpath`.
2. Tìm thư viện hoặc plugin có dùng Attach API để tự attach vào JVM hiện tại hoặc JVM khác.
3. Chạy thử với `-Djdk.instrument.traceUsage` nếu cần truy tìm thành phần sử dụng `java.lang.instrument`.
4. Chạy thử với `-XX:-EnableDynamicAgentLoading` trong môi trường kiểm thử để phát hiện phụ thuộc vào dynamic loading.
5. Với agent cần thiết lâu dài, cấu hình nó ngay lúc startup nếu công cụ hỗ trợ.
6. Nếu cần dynamic attach trong production, ghi nhận lý do, chủ sở hữu công cụ, quyền truy cập và quy trình phê duyệt; bật `-XX:+EnableDynamicAgentLoading` trên JVM đích một cách có chủ đích.
7. Cập nhật agent/tool lên phiên bản tương thích với JDK 21 và kiểm thử các chức năng redefine/retransform mà agent cần.

Ví dụ cấu hình startup agent cho ứng dụng:

```shell
java -javaagent:/opt/agents/apm-agent.jar=service=checkout -jar checkout-service.jar
```

Ví dụ kiểm thử không phụ thuộc dynamic attach:

```shell
java -XX:-EnableDynamicAgentLoading -jar checkout-service.jar
```

Nếu ứng dụng vẫn khởi động và chạy các chức năng cần thiết trong cấu hình thứ hai, đó là tín hiệu tốt cho khả năng tương thích với chính sách chặt hơn trong tương lai. Tuy nhiên, cần kiểm tra riêng các công cụ chẩn đoán mà nhóm vận hành sử dụng; có thể chúng cần startup agent hoặc một quy trình attach được cho phép.

## 12. Các trường hợp dễ nhầm

| Hiểu nhầm | Thực tế |
|---|---|
| JDK 21 đã cấm nạp agent động | JDK 21 vẫn cho phép mặc định nhưng phát warning khi agent được nạp vào JVM đang chạy |
| Tất cả agent đều phát warning | Agent nạp lúc startup qua command-line options không bị warning theo JEP 451 |
| `-XX:+EnableDynamicAgentLoading` là cách nạp agent | Đây là flag opt-in cho chính sách dynamic loading; agent vẫn cần được công cụ attach nạp vào |
| `-Djdk.instrument.traceUsage` chặn agent | Property này chỉ trace việc dùng Instrumentation API, không chặn dynamic loading |
| `-XX:-EnableDynamicAgentLoading` chặn `-javaagent` | Flag này kiểm soát agent nạp động vào JVM đang chạy; startup agent vẫn được hỗ trợ |
| JEP 451 loại bỏ Instrumentation API | JEP thay đổi cảnh báo/chính sách nạp agent động, không loại bỏ API instrumentation |
| Warning chứng minh agent độc hại | Warning chỉ cho biết agent được nạp động; cần xác minh nguồn gốc và mục đích |
| Có thể thêm flag vào tiến trình attach để sửa JVM đích | Flag phải được đặt trên command line của JVM đích từ lúc khởi chạy |

## 13. Lưu ý khi vận hành và bảo mật

- Chỉ cho phép agent từ nguồn đáng tin cậy, đã được kiểm tra chữ ký, checksum, phiên bản và quyền phân phối.
- Bảo vệ quyền truy cập vào PID, Attach API, socket/serviceability endpoint và thư mục chứa agent JAR/native library.
- Không cho phép user hoặc workload không tin cậy ghi đè agent JAR trên filesystem của service.
- Ưu tiên startup agent cho monitoring/profiling cố định để cấu hình được quản lý cùng ứng dụng.
- Giữ dynamic attach cho tình huống chẩn đoán cần thiết và có quy trình phê duyệt.
- Đánh giá tác động của transformer đến startup, class loading, CPU, latency và tính tương thích của framework.
- Không bật `-XX:+EnableDynamicAgentLoading` chỉ để ẩn warning nếu chưa xác định được ai đang nạp agent.

## 14. Checklist áp dụng JDK 21

- Phân biệt startup Java agent (`-javaagent`) với startup JVM TI agent (`-agentlib`, `-agentpath`).
- Hiểu `premain` là entry point startup và `agentmain` là entry point dynamic Java agent.
- Kiểm tra manifest có `Premain-Class` hoặc `Agent-Class` đúng với cách nạp.
- Nhận biết warning JEP 451 khi agent được nạp vào JVM đang chạy.
- Biết dynamic loading vẫn được cho phép mặc định trên HotSpot JDK 21.
- Dùng `-XX:+EnableDynamicAgentLoading` khi đã quyết định opt-in cho dynamic attach.
- Dùng `-XX:-EnableDynamicAgentLoading` trong môi trường thử nghiệm để phát hiện phụ thuộc.
- Dùng `-Djdk.instrument.traceUsage` để truy tìm nơi sử dụng Java Instrumentation API khi cần.
- Chuyển agent cố định sang startup configuration nếu công cụ hỗ trợ.
- Xác minh tính đáng tin cậy và quyền truy cập của agent trước khi triển khai.

JEP 451 trong JDK 21 không xóa agent hay Instrumentation API. Thay đổi cốt lõi là cảnh báo khi agent được nạp động vào một JVM đang chạy và cung cấp cơ chế opt-in/disable để ứng dụng kiểm soát khả năng này. Hiểu rõ hai đường nạp startup và dynamic giúp nhóm phát triển chuẩn bị công cụ, giảm phụ thuộc attach không cần thiết và giữ tính toàn vẹn của tiến trình JVM.

## Tài liệu tham khảo

- [JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451)
- [JDK 21 Release Notes — Prepare to Disallow the Dynamic Loading of Agents](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html)
- [Java SE 21 API — Package java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Java SE 21 API — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java SE 21 API — Attach API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html)
