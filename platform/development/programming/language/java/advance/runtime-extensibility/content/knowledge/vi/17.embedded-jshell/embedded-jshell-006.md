# ExecutionControlProvider và ranh giới giữa JVM điều khiển với JVM thực thi

## 1. Vì sao JShell cần một execution engine?

JShell là API và công cụ tương tác Java xuất hiện từ JDK 9. Khi ứng dụng host nhúng `jdk.jshell.JShell` và gọi `eval(...)`, JShell phải biên dịch snippet, quản lý trạng thái các khai báo và **thực thi** bytecode sinh ra. Cơ chế thực thi được trừu tượng hóa qua `jdk.jshell.spi.ExecutionControl`, còn `jdk.jshell.spi.ExecutionControlProvider` là điểm mở rộng cho phép lựa chọn cách tạo execution engine.

Điểm cần phân biệt: **JVM điều khiển (controlling JVM)** chạy host, giữ đối tượng `JShell`, phân tích snippet và điều phối phiên làm việc. **JVM thực thi (execution JVM)** là nơi bytecode snippet chạy; nó có thể là một JVM process riêng, hoặc thực thi trong cùng process thông qua engine thích hợp. Tên gọi 'execution JVM' không luôn ám chỉ process khác: điều đó phụ thuộc provider được chọn.

### Sơ đồ khái niệm

```text
+----------------------------------------------+
| Controlling JVM                              |
| Host app -> JShell API -> compiler/state      |
|                  |                           |
|           ExecutionControl                   |
+------------------|---------------------------+
                   | invocation / class load
                   v
+----------------------------------------------+
| Execution environment                        |
| - Local engine: bên trong JVM host            |
| - Remote engine: JVM process riêng            |
| - Custom provider: cách thực thi do tác giả   |
|   provider định nghĩa                        |
+----------------------------------------------+
```

Execution engine không phải script engine JSR 223. JShell thực thi **Java snippet** theo cơ chế `jdk.jshell`, chứ không tìm `javax.script.ScriptEngineFactory` hay dùng ngôn ngữ JavaScript.

## 2. Các API liên quan

| API | Vai trò |
|---|---|
| `jdk.jshell.JShell` | Phiên tương tác lưu trạng thái snippet, cho phép `eval`, `drop`, `variables`, `methods`, `close` |
| `JShell.Builder.executionEngine(...)` | Chọn provider hoặc chỉ định execution engine khi tạo JShell |
| `jdk.jshell.spi.ExecutionControl` | Giao diện giao tiếp với runtime thực thi: tải class, gọi lệnh, dừng, truy vấn biến... |
| `jdk.jshell.spi.ExecutionControlProvider` | Service provider tạo `ExecutionControl` từ `ExecutionEnv` và parameters |
| `jdk.jshell.spi.ExecutionEnv` | Cầu nối cung cấp thông tin/luồng I/O và thiết lập cần thiết từ JShell tới execution provider |
| `jdk.jshell.execution.JdiExecutionControlProvider` | Provider hỗ trợ thực thi qua JVM khác theo cơ chế JDI |
| `jdk.jshell.execution.LocalExecutionControlProvider` | Provider thực thi cục bộ trong controlling JVM |
| `jdk.jshell.execution.FailOverExecutionControlProvider` | Cơ chế thử nhiều provider theo thứ tự cấu hình |

Những lớp provider thuộc module `jdk.jshell` và API Java 17+. Tên provider, tham số và đặc tính cụ thể cần được kiểm tra theo JDK/runtime triển khai; không được đoán rằng các provider có cùng khả năng dừng, cách ly hay phục hồi.

## 3. ExecutionControlProvider hoạt động như thế nào?

Về thiết kế, `ExecutionControlProvider` cung cấp:

- `name()`: tên provider được dùng trong cấu hình.
- `defaultParameters()`: map các tham số mặc định do provider công bố.
- `generate(ExecutionEnv env, Map<String,String> parameters)`: tạo một `ExecutionControl` theo môi trường và tham số.

JShell builder có thể chọn execution engine theo provider và tham số. Các thành phần của `ExecutionEnv` giúp provider giao tiếp với controlling JShell, ví dụ lấy output/error stream và cơ chế khởi tạo/khôi phục môi trường theo hợp đồng API. Provider phải chịu trách nhiệm về lifecycle của engine và lỗi khi môi trường thực thi không đáp ứng.

Ví dụ dạng **minh họa**, dùng provider được cấu hình từ trước:

```java
ExecutionControlProvider provider = ...; // provider phù hợp
Map<String, String> options = provider.defaultParameters();
try (JShell js = JShell.builder()
        .executionEngine(provider, options)
        .build()) {
    js.eval("int answer = 42;");
}
```

Cần import `jdk.jshell.JShell`, `jdk.jshell.spi.ExecutionControlProvider`, `java.util.Map`. Đoạn này **không chạy độc lập** vì chưa có giá trị `provider`. Khi viết host thực tế, có thể cung cấp instance của `LocalExecutionControlProvider` hoặc provider riêng, thay vì để dấu ba chấm.

Trong thiết kế plugin, chọn provider **trước khi tạo JShell instance**. Không nên thay execution provider giữa một phiên đang chứa state snippet và kỳ vọng state tự chuyển sang engine khác. Quy trình chuyển trạng thái cần được thiết kế hoặc tạo phiên mới và đánh giá lại mã phù hợp.

## 4. Ví dụ Java 17+: JShell mặc định và local engine

Ví dụ này không yêu cầu plugin ngoài và giúp thấy API điều khiển snippets. Tạo `InspectJShell.java`:

```java
import java.util.List;
import jdk.jshell.JShell;
import jdk.jshell.SnippetEvent;
import jdk.jshell.execution.LocalExecutionControlProvider;

public final class InspectJShell {
    static void run(JShell shell, String title) {
        List<SnippetEvent> events = shell.eval("int n = 6 * 7;");
        System.out.println(title + " events: " + events.size());
        for (SnippetEvent event : events) {
            System.out.println(event.status() + ": " + event.value());
        }
    }

    public static void main(String[] args) {
        try (JShell defaultShell = JShell.create()) {
            run(defaultShell, "default");
        }

        try (JShell localShell = JShell.builder()
                .executionEngine(new LocalExecutionControlProvider(), null)
                .build()) {
            run(localShell, "local");
        }
    }
}
```

Biên dịch và chạy (JDK 17+):

```bash
javac --add-modules jdk.jshell InspectJShell.java
java --add-modules jdk.jshell InspectJShell
```

Đầu ra kỳ vọng:

```text
default events: 1
VALID: 42
local events: 1
VALID: 42
```

Đoạn này tạo **hai phiên JShell riêng**. Một phiên dùng execution engine mặc định của JShell, phiên còn lại chọn explicit local provider. Sự giống nhau của kết quả `42` không có nghĩa hai phiên có ranh giới process hoặc mô hình lỗi giống nhau.

**Lưu ý quan trọng:** Tham số thứ hai `null` của `executionEngine(provider, parameters)` cho phép builder sử dụng default parameters theo cơ chế cấu hình phiên tương ứng. Trong ứng dụng cần chính sách rõ ràng, có thể truyền một bản sao có điều chỉnh của `provider.defaultParameters()` thay vì giả định mọi provider chấp nhận cùng một map.

## 5. Remote execution: JVM con và ranh giới tiến trình

Một engine thực thi từ xa (ví dụ provider dùng JDI để khởi chạy JVM phụ) có thể đặt snippet trong **process riêng** với heap, static fields và threads độc lập. Điều này đem lại lợi ích về cô lập lỗi và quản lý tài nguyên, nhưng không tự tạo sandbox an toàn:

- Snippet trong JVM con không trực tiếp chia sẻ object references trong heap của JVM điều khiển. Muốn truyền dữ liệu phải dùng giao thức/serialization/bridge được thiết kế.
- Class path, module path, system properties, môi trường OS và version Java của JVM con có thể khác JVM điều khiển; cần xác định rõ launch options.
- Stdout/stderr của snippet có thể được chuyển về controlling process theo cấu hình `ExecutionEnv`; không nên giả định chúng luôn là cùng stream hoặc cùng thread.
- Process con có thể crash, treo hoặc bị kill; host cần xử lý lỗi execution engine, thời gian chờ, cleanup và tái tạo session khi cần.
- Tách process làm giảm một số nguy cơ hỏng heap host, **nhưng không mặc nhiên giới hạn network, file system, CPU hoặc dữ liệu nhạy cảm** nếu process vẫn chạy cùng quyền OS.

### Chỉ định remote provider

Đoạn sau minh họa cách chọn một provider JDI hiện có:

```java
import jdk.jshell.JShell;
import jdk.jshell.execution.JdiExecutionControlProvider;

JdiExecutionControlProvider jdi = new JdiExecutionControlProvider();
try (JShell shell = JShell.builder()
        .executionEngine(jdi, jdi.defaultParameters())
        .build()) {
    shell.eval("System.out.println(\"run in execution environment\");");
}
```

Đây là **mảnh mã**, không phải file độc lập (các statement phải nằm trong method). Việc khởi động JVM phụ có thể thất bại do quyền tạo process, port, JDI, chính sách hệ thống hoặc JDK runtime image thiếu module; cần bắt và xử lý lỗi thích hợp. Tránh coi ví dụ này là bằng chứng mọi môi trường sẽ chạy được remote provider.

## 6. Local execution: cùng JVM và rủi ro chia sẻ tài nguyên

`LocalExecutionControlProvider` cho phép JShell thực thi snippet trong controlling JVM. Đây là lựa chọn tiện cho ứng dụng kiểm soát chặt nội dung và muốn giảm chi phí tạo JVM phụ, nhưng đánh đổi khả năng cô lập.

Hệ quả:

- Snippet có thể tác động đến trạng thái chung của process, ví dụ system properties và tài nguyên JVM nếu code có quyền truy cập.
- Threads, memory, native library, class loader và static state cần quản lý kỹ; việc đóng JShell không đảm bảo mã tùy ý đã được thực thi không để lại thread hay resource.
- Lỗi nghiêm trọng trong snippet có thể ảnh hưởng tới chính host.
- Khả năng dừng snippet bất hợp tác có giới hạn; không được hứa hẹn timeout tuyệt đối chỉ nhờ gọi API JShell.

Trong ứng dụng chạy mã người dùng hoặc mã không đáng tin cậy, **không dùng local engine như một ranh giới bảo mật**. Với remote engine, vẫn cần isolation ở OS/container, giới hạn quyền và tài nguyên để đạt yêu cầu an toàn.

## 7. ExecutionControl không phải ClassLoader

Phân biệt hai lớp trừu tượng:

| Khía cạnh | ClassLoader | ExecutionControl |
|---|---|---|
| Mục tiêu | Tìm và định nghĩa class | Điều phối thực thi snippet được JShell biên dịch |
| Đối tượng chính | `Class<?>`, package, bytecode | Trạng thái snippets, invoke, class installation, stop, execution lifecycle |
| Scope | Một JVM process | Có thể xuyên ranh giới JVM/process |
| Có tự tạo sandbox? | Không | Không |

JShell thường sinh class từ snippet. Provider cần đưa class bytes tới execution environment theo hợp đồng `ExecutionControl`. Khi dùng remote JVM, bytecode/commands được chuyển qua một giao thức nội bộ tùy implementation. Không đồng nhất loader mà host sử dụng để nạp `ExecutionControlProvider` với loader thực sự nạp class snippet trong môi trường thực thi.

Ví dụ một host chọn provider từ class path bằng `ServiceLoader<ExecutionControlProvider>` không chứng minh tất cả provider đều chạy local. Provider có thể khởi tạo JVM khác hoặc cơ chế remote riêng. Cần đọc contract/provider configuration và kiểm chứng bằng quan sát process/lifecycle, thay vì suy đoán từ class loader.

## 8. Viết custom ExecutionControlProvider: khi nào cần?

Các use case có thể gồm:

- Phân phối việc chạy snippet tới một JVM worker do host quản lý.
- Có transport/protocol riêng tới execution environment.
- Muốn cấu hình class path, khởi động, logging, giới hạn tài nguyên và reconnect theo môi trường triển khai.
- Cần ghi nhận rõ ràng lifecycle và phục hồi khi worker thất bại.

Không nên tự viết provider chỉ để thực thi một đoạn Java đơn giản: API compiler/class loader hoặc provider có sẵn thường đủ. Nếu tự triển khai `ExecutionControl`, phải tuân thủ các phương thức và exception contract của SPI, bao gồm quản lý class bytes, invoke, biến, stop và close. Đây là lớp tích hợp có độ phức tạp cao, không chỉ là việc viết một hàm `eval(String)`.

### Mẫu skeleton minh họa

```java
import java.util.Map;
import jdk.jshell.spi.ExecutionControl;
import jdk.jshell.spi.ExecutionControlProvider;
import jdk.jshell.spi.ExecutionEnv;

public final class MyProvider implements ExecutionControlProvider {
    @Override
    public String name() { return "my-engine"; }

    @Override
    public Map<String, String> defaultParameters() {
        return Map.of();
    }

    @Override
    public ExecutionControl generate(ExecutionEnv env,
                                     Map<String, String> parameters)
            throws Throwable {
        throw new UnsupportedOperationException(
                "Cần cung cấp ExecutionControl hoàn chỉnh");
    }
}
```

**Không phải implementation sử dụng được**: phương thức `generate` cố ý chưa tạo engine. Đoạn này chỉ minh họa giao diện provider; không nên đăng ký nó làm plugin đang hoạt động vì JShell build sẽ thất bại. Khi xây dựng provider thực tế, hãy bắt đầu từ tài liệu API SPI và một implementation tham chiếu phù hợp JDK mục tiêu.

## 9. Lifecycle, lỗi và ngắt thực thi

Host cần phân biệt các nhóm lỗi:

| Nhóm | Dấu hiệu | Phản ứng phù hợp |
|---|---|---|
| Snippet bị compiler từ chối | `SnippetEvent.status()` là trạng thái rejected | Hiển thị diagnostics, không coi là lỗi engine |
| Snippet ném exception | `SnippetEvent.exception()` chứa thông tin exception | Báo lỗi chạy snippet, không đồng nhất với crash JVM |
| Engine/provider không tạo được | Lỗi khi `JShell.Builder.build()` hoặc `ExecutionControlProvider.generate` | Ghi nguyên nhân, hủy session, fallback theo policy |
| Remote JVM chết hoặc mất kết nối | Execution control lỗi, engine không phản hồi hoặc bị terminate | Dọn process/socket, tạo session mới khi phù hợp |
| Snippet treo/vòng lặp vô hạn | Không kết thúc trong thời gian mong đợi | Áp dụng timeout/cancellation ở tầng quản lý phù hợp, có cơ chế kill worker độc lập |

`JShell.stop()` được thiết kế để yêu cầu dừng việc thực thi snippet đang chạy, nhưng khả năng thực thi và thời điểm dừng còn tùy provider và hoạt động của mã đang chạy. Không dùng nó làm cơ chế giới hạn thời gian cứng cho mã không tin cậy.

Dùng `try-with-resources` để gọi `JShell.close()` khi kết thúc phiên. Với remote engine cần đảm bảo lifecycle của subprocess, connections và tài nguyên phụ không bị bỏ lại. Với local engine cần kiểm tra thread/resource do snippet tự tạo; `close()` không thể tự hoàn tác mọi tác dụng phụ.

## 10. Checklist chọn execution provider

1. Xác định snippet là mã nội bộ tin cậy hay mã không tin cậy.
2. Kiểm tra runtime có module `jdk.jshell`, compiler và provider cần thiết.
3. Chọn rõ local/remote/custom engine theo nhu cầu hiệu năng, cô lập và debug.
4. Với remote: cấu hình Java executable/JVM options/class path/module path và quyền OS phù hợp.
5. Thiết kế xử lý input/output, lỗi, timeout, worker crash và cleanup.
6. Không truyền trực tiếp Java object host xuyên JVM boundary; dùng giao thức dữ liệu có schema.
7. Kiểm thử restart/failover và bảo đảm không dùng lại state JShell của engine đã chết một cách mù quáng.
8. Đánh giá an toàn theo OS/process, không mặc định class loader hoặc subprocess là sandbox.

**Kết luận:** `ExecutionControlProvider` quyết định cách JShell tạo execution engine và vì vậy là nơi xác định ranh giới thực thi. Controlling JVM giữ phiên JShell và logic quản lý; engine có thể chạy cục bộ hoặc trong JVM riêng. Chọn provider là quyết định kiến trúc về độ trễ, tài nguyên, khả năng phục hồi và an toàn, không chỉ là một tham số trong `JShell.Builder`.
