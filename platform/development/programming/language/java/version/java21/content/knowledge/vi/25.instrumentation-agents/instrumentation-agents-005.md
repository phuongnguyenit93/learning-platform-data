# jdk.instrument.traceUsage để truy tìm việc dùng Instrumentation

`jdk.instrument.traceUsage` là system property của JDK dùng để chẩn đoán việc sử dụng API `java.lang.instrument`. Khi bật property này, các lần sử dụng API Instrumentation tạo trace message và stack trace. Stack trace giúp lần ngược từ lời gọi như đăng ký transformer hoặc retransformation về agent, thư viện hay công cụ đã thực hiện thao tác.

Trong Java 21, property này đặc biệt hữu ích khi điều tra cảnh báo agent được nạp động theo JEP 451. Ví dụ, một thư viện kiểm thử hoặc công cụ profiling có thể dùng Attach API để nạp agent vào JVM đang chạy. `jdk.instrument.traceUsage` giúp tìm đoạn mã sử dụng Instrumentation và xác định agent đó có thể được cấu hình khởi chạy ngay từ đầu bằng `-javaagent` hay không.

Property này chỉ quan sát việc sử dụng `java.lang.instrument`; nó không bật hoặc tắt việc nạp agent, không phải danh sách đầy đủ mọi agent trong JVM và không thay thế các biện pháp kiểm soát dynamic loading.

## 1. Instrumentation API và Java agent

Instrumentation cho phép agent làm việc với bytecode của lớp Java đang được JVM nạp hoặc đã được nạp. Các công cụ như profiler, coverage tool, mocking framework và runtime monitoring có thể dùng API này để đăng ký transformer hoặc thay đổi định nghĩa lớp trong giới hạn JVM cho phép.

Agent Java nhận một đối tượng `Instrumentation` theo một trong hai cách phổ biến:

- **Agent khởi chạy cùng JVM:** JVM nạp agent qua `-javaagent:<jar>` và gọi phương thức `premain`.
- **Agent nạp vào JVM đang chạy:** công cụ attach nạp agent JAR và JVM gọi phương thức `agentmain`.

Hai cách khởi chạy dùng manifest attribute khác nhau:

| Cách khởi chạy | Manifest attribute | Entry method |
|---|---|---|
| Startup agent qua `-javaagent` | `Premain-Class` | `premain(String, Instrumentation)` hoặc `premain(String)` |
| Dynamic agent qua Attach API | `Agent-Class` | `agentmain(String, Instrumentation)` hoặc `agentmain(String)` |

Ví dụ cấu trúc một startup agent:

```java
import java.lang.instrument.Instrumentation;

public final class ExampleAgent {
    public static void premain(String options, Instrumentation instrumentation) {
        System.out.println("Example agent started at JVM startup");
        instrumentation.addTransformer(
                (loader, className, classBeingRedefined, protectionDomain, classfileBuffer) -> null);
    }
}
```

Ví dụ cấu trúc một dynamic agent:

```java
import java.lang.instrument.Instrumentation;

public final class ExampleAgent {
    public static void agentmain(String options, Instrumentation instrumentation) {
        System.out.println("Example agent attached to running JVM");
        instrumentation.addTransformer(
                (loader, className, classBeingRedefined, protectionDomain, classfileBuffer) -> null,
                true);
    }
}
```

Hai ví dụ minh họa entry method và đăng ký một transformer không thay đổi bytecode (trả về `null`). Transformer thực tế phải triển khai logic xử lý bytecode đúng quy tắc; không nên dùng transformer rỗng này như mã instrument production.

## 2. Property jdk.instrument.traceUsage làm gì?

Khi bật `jdk.instrument.traceUsage`, JDK in thông báo trace và stack trace khi API `java.lang.instrument` được sử dụng. Ví dụ, stack trace có thể giúp tìm nơi gọi các phương thức như:

- `Instrumentation.addTransformer(...)`.
- `Instrumentation.removeTransformer(...)`.
- `Instrumentation.retransformClasses(...)`.
- `Instrumentation.redefineClasses(...)`.
- Các API Instrumentation khác được agent sử dụng.

Stack trace cho thấy đường gọi dẫn tới thao tác Instrumentation. Từ đó có thể tìm tên package, lớp agent, thư viện phụ thuộc hoặc framework thực hiện lời gọi.

Property này không chỉ dành cho dynamic agent. Một startup agent được nạp bằng `-javaagent` cũng có thể tạo trace khi gọi Instrumentation API. Vì vậy, hãy đọc stack trace để phân biệt ngữ cảnh `premain` với `agentmain` hoặc một luồng xử lý khác.

`jdk.instrument.traceUsage` là property chẩn đoán riêng của JDK, không phải API Java SE mà ứng dụng có thể dựa vào như một hợp đồng portable giữa mọi JVM vendor. Hành vi và định dạng trace cần được kiểm tra trên JDK thực tế.

## 3. Bật traceUsage khi khởi chạy JVM

Cách trực tiếp nhất là truyền system property bằng `-D` khi khởi chạy ứng dụng:

```bash
java -Djdk.instrument.traceUsage -jar application.jar
```

Có thể ghi giá trị `true` tường minh:

```bash
java -Djdk.instrument.traceUsage=true -jar application.jar
```

Nếu ứng dụng khởi chạy startup agent, đặt property cùng với `-javaagent`:

```bash
java \
  -Djdk.instrument.traceUsage=true \
  -javaagent:monitoring-agent.jar=profile \
  -jar application.jar
```

Các JVM option phải nằm trước `-jar` hoặc tên main class. Bật property trong lần khởi chạy chẩn đoán để ghi lại các lần sử dụng Instrumentation ngay từ đầu vòng đời ứng dụng.

Với ứng dụng được khởi chạy bởi service manager, container hoặc test runner, cần đặt option vào cấu hình JVM của đúng tiến trình Java cần quan sát. Đặt property cho tiến trình Maven/Gradle điều phối không bảo đảm nó được truyền sang JVM fork riêng để chạy test.

## 4. Đọc trace để xác định agent hoặc thư viện

Khi trace xuất hiện, lần theo stack trace từ lời gọi Instrumentation về phía caller:

1. Tìm frame thuộc `java.lang.instrument` hoặc implementation của JDK để xác định API được gọi.
2. Tìm frame đầu tiên thuộc package không phải JDK; đây thường là lớp agent hoặc thư viện gọi API.
3. Kiểm tra các frame phía trên để tìm entrypoint, chẳng hạn `premain`, `agentmain`, mã khởi tạo framework hoặc mã attach.
4. Xác định JAR và phiên bản dependency sở hữu lớp đó bằng classpath, dependency report hoặc thông tin triển khai.
5. Kiểm tra cấu hình để biết agent được khai báo qua `-javaagent` hay được nạp sau khi JVM đã chạy.

Ví dụ minh họa một stack trace rút gọn (tên lớp và thứ tự thực tế phụ thuộc agent/JDK):

```text
java.lang.instrument.Instrumentation.addTransformer(...)
com.vendor.agent.TransformerInstaller.install(...)
com.vendor.agent.AgentMain.agentmain(...)
```

Frame `agentmain` gợi ý agent được khởi tạo qua cơ chế dynamic attach. Nếu stack trace đi qua `premain`, agent đang thực hiện thao tác từ đường khởi chạy lúc JVM start. Đây là manh mối để điều tra; cần xác nhận với cấu hình launch và dependency thực tế.

Không chỉ nhìn tên thư viện trong stack trace rồi kết luận thư viện đó tự attach agent. Một framework có thể gọi một adapter, plugin hoặc service provider khác; hãy lần tiếp qua các frame và cấu hình để xác định thành phần thực sự chịu trách nhiệm.

## 5. Kết hợp với cảnh báo dynamic agent của JEP 451

JEP 451 được đưa vào JDK 21 để chuẩn bị cho việc tăng cường integrity của JVM. Khi Java agent hoặc JVM TI agent được nạp động vào một JVM đang chạy, HotSpot phát cảnh báo. Agent khởi chạy ngay từ đầu qua option dòng lệnh như `-javaagent` hoặc `-agentlib` không tạo cảnh báo dynamic loading này.

Cảnh báo của JDK 21 hướng người vận hành đến hai hành động khác nhau:

- Nếu agent được nạp động là cần thiết và đó là hành vi đã được chấp thuận, có thể chủ động opt in bằng `-XX:+EnableDynamicAgentLoading` trên HotSpot. Trong JDK 21, option này cho phép dynamic loading và suppress cảnh báo.
- Nếu không biết vì sao agent được nạp động, bật `-Djdk.instrument.traceUsage` để thu thập stack trace và tìm thành phần sử dụng Instrumentation.

Property và VM option có vai trò khác nhau:

| Cấu hình | Loại | Tác dụng |
|---|---|---|
| `-Djdk.instrument.traceUsage` | System property | Trace việc sử dụng `java.lang.instrument` API và in stack trace |
| `-Djdk.instrument.traceUsage=true` | System property | Bật cùng chức năng, ghi giá trị rõ ràng |
| `-XX:+EnableDynamicAgentLoading` | HotSpot VM option | Cho phép dynamic agent loading; trong JDK 21 suppress cảnh báo |
| `-XX:-EnableDynamicAgentLoading` | HotSpot VM option | Từ chối dynamic agent loading trên HotSpot để kiểm tra ứng dụng có phụ thuộc cơ chế này không |
| `-javaagent:<jar>` | JVM launch option | Nạp agent ngay lúc JVM khởi động |

`traceUsage` không phải cách suppress warning, cũng không phải cách bật dynamic loading. Ngược lại, `EnableDynamicAgentLoading` không cung cấp stack trace về nơi gọi Instrumentation.

## 6. Phân biệt startup agent và dynamic agent trong điều tra

Startup agent được khai báo trực tiếp trong command line hoặc cấu hình launcher:

```bash
java -javaagent:observability-agent.jar -jar application.jar
```

JVM gọi `premain` trước khi gọi `main` của ứng dụng. Với cách này, agent và thứ tự khởi chạy có thể được kiểm tra từ script, service definition, container command hoặc cấu hình runtime.

Dynamic agent được nạp sau khi JVM đã chạy. Một công cụ bên ngoài có thể dùng Attach API để kết nối đến JVM và gọi `loadAgent`:

```java
import com.sun.tools.attach.VirtualMachine;

static void attachAgent(String pid, String agentJar) throws Exception {
    VirtualMachine vm = VirtualMachine.attach(pid);
    try {
        vm.loadAgent(agentJar, "diagnostic=true");
    } finally {
        vm.detach();
    }
}
```

Đây là mã của tiến trình attach bên ngoài, không phải mã chạy bên trong agent. API thuộc module JDK `jdk.attach`; cơ chế attach phụ thuộc nền tảng, quyền của người dùng và cấu hình JVM đích. Agent JAR cần khai báo `Agent-Class` và có `agentmain` phù hợp.

Khi điều tra, kết hợp trace với command line và cấu hình triển khai:

- Nếu tìm thấy `-javaagent`, kiểm tra agent có đang khởi chạy đúng cách dự kiến không.
- Nếu stack trace cho thấy `agentmain`, tìm công cụ hoặc dependency gọi Attach API.
- Nếu không tìm thấy frame Java tương ứng, kiểm tra liệu thành phần đang dùng native JVM TI agent hoặc cơ chế khác ngoài phạm vi trace của `java.lang.instrument`.

## 7. Quy trình truy tìm Instrumentation trong ứng dụng

Một quy trình thực tế có thể thực hiện theo các bước sau:

1. **Xác nhận cảnh báo:** ghi lại JVM version, warning đầy đủ và thời điểm xuất hiện.
2. **Bật trace:** khởi chạy lại môi trường chẩn đoán với `-Djdk.instrument.traceUsage=true`.
3. **Tái hiện:** chạy test, khởi động service hoặc thực hiện thao tác thường làm xuất hiện cảnh báo.
4. **Thu thập output:** lưu log có trace message và stack trace, kèm thời gian và phiên bản runtime.
5. **Xác định caller:** tìm agent class, `agentmain`/`premain`, package và JAR trong stack.
6. **Truy nguồn dependency:** kiểm tra dependency tree, plugin, test framework, profiler, APM agent hoặc công cụ phát triển.
7. **Chọn cách khởi chạy:** nếu agent cần thiết, ưu tiên cấu hình khởi chạy rõ ràng bằng `-javaagent` khi agent hỗ trợ; nếu không cần, cập nhật hoặc cấu hình lại thư viện gây attach.
8. **Kiểm tra lại:** chạy lại với cấu hình mới và xác nhận trace/warning không còn xuất hiện ngoài dự kiến.

Trong môi trường test, các mocking framework hoặc công cụ bytecode generation có thể nạp agent để hỗ trợ một số tính năng. Không nên xóa dependency ngay khi thấy trace; trước tiên xác định tính năng nào cần agent và cách cấu hình chính thức của thư viện đó.

## 8. Những gì traceUsage không làm

`jdk.instrument.traceUsage` là công cụ chẩn đoán hẹp. Không nên xem nó như audit log hoàn chỉnh hoặc cơ chế bảo vệ JVM.

- **Không liệt kê toàn bộ agent đã nạp:** nó trace API usage, không phải một API truy vấn registry agent.
- **Không chỉ trace dynamic agent:** startup agent cũng có thể tạo trace khi gọi Instrumentation API.
- **Không thay thế trace cho toàn bộ JVM TI:** property mô tả việc dùng `java.lang.instrument`, không phải bộ trace mọi lời gọi native JVM TI.
- **Không ngăn agent nạp:** property không thay đổi quyền dynamic loading.
- **Không xác thực độ tin cậy của agent:** người triển khai vẫn phải kiểm tra nguồn gốc và nội dung agent JAR.
- **Không chứng minh không có agent khi không thấy trace:** agent có thể chưa gọi API được trace, dùng JVM TI native hoặc không chạy trong khoảng thời gian quan sát.

Để có bức tranh đầy đủ hơn, kết hợp trace với command line, cấu hình service, dependency inventory, log cảnh báo và kiểm soát quyền attach.

## 9. Ảnh hưởng vận hành và bảo vệ log

Trace có thể tạo nhiều output nếu agent gọi Instrumentation API thường xuyên. Stack trace cũng làm tăng chi phí chẩn đoán so với chạy bình thường. Vì vậy:

- Bật trong môi trường phát triển, kiểm thử hoặc một khoảng chẩn đoán có kiểm soát.
- Chỉ giữ trace trong thời gian cần tìm nguyên nhân; tắt property sau khi điều tra nếu không còn nhu cầu.
- Theo dõi dung lượng log và tránh để output tăng không giới hạn.
- Bảo vệ log vì stack trace có thể tiết lộ tên class nội bộ, package, đường dẫn JAR và cấu trúc triển khai.
- Không đưa log chẩn đoán chứa đường dẫn hoặc thông tin nội bộ lên hệ thống công khai.

Nếu cần giám sát liên tục agent đang hoạt động, hãy dùng cơ chế quản lý cấu hình và inventory phù hợp; không giữ `traceUsage` bật như một giải pháp audit dài hạn.

## 10. Lưu ý theo phiên bản JDK

`jdk.instrument.traceUsage` được ghi nhận trong JDK 21 Release Notes cùng thay đổi JEP 451. Nội dung cốt lõi vẫn hữu ích khi chẩn đoán các ứng dụng sử dụng `java.lang.instrument`, nhưng đây là property triển khai của JDK chứ không phải cam kết API Java SE cho mọi JVM.

JEP 451 mô tả hướng thay đổi chính sách dynamic agent loading trong các bản phát hành tương lai. Không nên suy luận rằng chỉ vì chạy trên Java 21 thì dynamic loading đã bị tắt: trong HotSpot JDK 21, dynamic loading vẫn được cho phép mặc định nhưng phát cảnh báo; `-XX:-EnableDynamicAgentLoading` có thể dùng để kiểm tra khả năng chạy khi không cho phép dynamic attach.

Khi ứng dụng chạy trên JDK mới hơn hoặc JVM vendor khác, kiểm tra release notes và tài liệu của đúng runtime về `jdk.instrument.traceUsage`, `EnableDynamicAgentLoading` và Attach API. Hãy tách riêng ba câu hỏi: API có được trace không, dynamic agent có được phép nạp không, và agent được khởi chạy ở thời điểm nào.

## 11. Tổng kết

`-Djdk.instrument.traceUsage` hoặc `-Djdk.instrument.traceUsage=true` bật trace message và stack trace cho việc sử dụng API `java.lang.instrument`. Khi một agent hoặc thư viện gọi Instrumentation, stack trace giúp tìm package, lớp và đường gọi chịu trách nhiệm. Đây là công cụ hữu ích để điều tra agent được nạp động sau cảnh báo JEP 451 hoặc để hiểu hoạt động của startup agent.

Hãy phân biệt property này với `-XX:+/-EnableDynamicAgentLoading` và `-javaagent`: một bên quan sát API usage, một bên kiểm soát dynamic loading trên HotSpot, còn một bên nạp agent lúc JVM khởi động. Dùng trace trong khoảng chẩn đoán có kiểm soát, bảo vệ log và xác nhận lại cấu hình sau khi tìm được agent hoặc dependency liên quan.

## Tài liệu tham khảo

- [JDK 21 Release Notes — Warning Printed When an Agent Is Loaded into a Running VM](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html) — mô tả `jdk.instrument.traceUsage`, dynamic agent warning và `EnableDynamicAgentLoading`.
- [JEP 451: Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451) — mục tiêu, cảnh báo và hướng thay đổi chính sách dynamic agent loading.
- [Java SE 21 API — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html) — startup agent, dynamic agent, manifest attributes và entry methods.
- [Java SE 21 API — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html) — các thao tác Instrumentation mà agent có thể gọi.
- [Java SE 21 API — Attach API VirtualMachine](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html) — attach vào JVM đang chạy và nạp agent.
