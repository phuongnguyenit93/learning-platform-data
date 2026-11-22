# Tách tiến trình khi cần ranh giới bảo mật mạnh hơn ClassLoader

`ClassLoader` là một công cụ **nạp và cô lập tên kiểu Java**, không phải sandbox đáng tin cậy cho mã tùy ý. Nếu host nạp plugin bằng `URLClassLoader`, plugin vẫn **chạy trong cùng tiến trình JVM** với host: cùng heap/process, thường cùng quyền hệ điều hành, có thể tác động tới các tài nguyên dùng chung và không được cô lập khỏi sự cố JVM-level như làm cạn bộ nhớ hoặc dừng tiến trình.

Khi plugin, bộ xử lý tài liệu, script engine hoặc thư viện của đối tác **không hoàn toàn tin cậy**, một phương án mạnh hơn là **đưa phần chạy rủi ro sang JVM/tiến trình riêng**, giao tiếp với host qua một giao thức có kiểm soát, và áp dụng **giới hạn của hệ điều hành hoặc môi trường container/VM**. Tuy nhiên, **chỉ gọi `ProcessBuilder.start()` không biến chương trình con thành sandbox**. Nếu JVM con chạy cùng tài khoản OS, thấy cùng thư mục/secrets và không bị giới hạn mạng/CPU/bộ nhớ, ranh giới bảo mật vẫn yếu.

Bài Knowledge này thuộc **Java core – classloader / Ranh giới bảo mật**. Trọng tâm là **khi nào tách tiến trình, những gì ranh giới mới ngăn được và không ngăn được, cách thiết kế IPC, lifecycle, timeout, giới hạn tài nguyên, kiểm thử và cách áp dụng Java 17+**.

## 1. Phân biệt bốn mức cô lập

| Cơ chế | Cô lập chính | Không tự bảo đảm |
| --- | --- | --- |
| **Một `ClassLoader` khác trong cùng JVM** | Namespace class, phiên bản dependency, runtime class identity, một phần static state | Heap/process/OS permissions/secrets, chống mã độc, giới hạn CPU/RAM |
| **Một JVM process riêng** | Không gian địa chỉ/heap JVM riêng, GC và JVM crash phần lớn không trực tiếp phá heap host, luồng và exit status riêng | Quyền file/network, CPU/RAM toàn máy, dữ liệu bí mật nếu cùng OS identity |
| **Process riêng dưới OS account/sandbox/container có chính sách hạn chế** | Có thể giới hạn filesystem, network, CPU/memory/process count, credentials/capabilities | Không tự tuyệt đối: kernel/container escape, cấu hình sai, IPC vulnerabilities |
| **VM/máy riêng và policy mạng/storage nghiêm ngặt** | Biên giới kernel/máy độc lập hơn, blast radius có thể giảm mạnh | Không loại trừ lỗ hổng hypervisor, OS, protocol hoặc quyền cấu hình |

**Ranh giới không phải boolean.** Cần nhìn vào **threat model**: đối thủ kiểm soát bytecode, input, plugin dependency, payload giao thức hay chỉ là một thư viện có khả năng lỗi? Họ có thể đọc file nào, gọi mạng ra đâu, truy cập thông tin gì và gây thiệt hại tài nguyên ở mức nào?

Nếu mục tiêu chỉ là dùng hai phiên bản thư viện khác nhau trong một ứng dụng đáng tin cậy, `ClassLoader` có thể là lựa chọn nhẹ hơn. Nếu mục tiêu là **ngăn mã có thể độc hại đọc token của host hoặc gọi OS resources**, chỉ thay loader là không đủ.

## 2. Tại sao ClassLoader không phải boundary bảo mật hoàn chỉnh?

Một class được nạp qua child loader:

```java
Class<?> pluginType = pluginLoader.loadClass("plugin.Task");
Object plugin = pluginType.getDeclaredConstructor().newInstance();
```

Đây là **snippet**, giả định biến `pluginLoader` đã khai báo và caller xử lý các exceptions. Dù `pluginType.getClassLoader()` là loader riêng, code plugin vẫn thực thi **trong JVM process hiện tại**.

Những điều có thể xảy ra nếu plugin có khả năng gọi các API phù hợp với quyền runtime:

- Đọc/ghi những file và thư mục mà **process host** có quyền truy cập.
- Gọi network tới những destinations mà network policy cho phép.
- Xem system properties/environment variables được truyền vào process.
- Tạo thread/executor, giữ thread sống, sử dụng CPU và memory.
- Gọi `System.exit(...)` để yêu cầu dừng **JVM host**.
- Dùng reflection/method handles, native interfaces hoặc khả năng runtime khác trong những giới hạn thực tế của JDK và môi trường.
- Gây `OutOfMemoryError`, giữ các object references, khiến garbage collection hoặc JVM process bị quá tải.
- Giữ `ThreadLocal`/TCCL/callback references làm class loader không thể unload, gây memory leak.

Có thể giới hạn API mà host **tự trao qua interface**, nhưng đừng nhầm “API capability do host định nghĩa” với việc loại bỏ những OS/JDK capabilities mà plugin code đã có khi được chạy trong cùng process.

### Security Manager không còn là phương án sandbox lâu dài

Ở **JDK 17**, Security Manager đã **deprecated for removal** (JEP 411), không nên thiết kế sandbox mới phụ thuộc vào nó. Từ **JDK 24**, Security Manager đã **bị vô hiệu hóa vĩnh viễn** (JEP 486), không thể bật để khôi phục mô hình cấp quyền Java cũ.

Vì thế, khi cần một ranh giới thực sự cho code không đáng tin, hãy suy nghĩ tới **OS process identity, sandbox, container, VM, permission, firewall và giao thức giới hạn**, thay vì một `SecurityManager` do host cài trong JVM.

## 3. Khi nào nên chuyển plugin ra một tiến trình riêng?

Những tình huống có lý do rõ ràng:

1. **Chạy code của bên thứ ba có mức tin cậy thấp**: plugin từ marketplace, script hoặc bytecode do đối tác cung cấp.
2. **Phân tích input không tin cậy** bằng thư viện phức tạp: parser tài liệu, ảnh, media hoặc công cụ converter có khả năng crash/hang.
3. **Tác vụ có CPU/RAM khó dự đoán**: chạy thuật toán của khách hàng, máy chấm bài, batch processing.
4. **Cần giảm blast radius** khi native library, JNI, FFM hoặc JVM component lỗi: crash worker không làm sập luôn heap host.
5. **Tách credentials và network access**: worker chỉ được đọc dữ liệu được đưa qua IPC; host giữ database tokens/payment secrets trong môi trường khác.
6. **Giới hạn phiên bản runtime độc lập**: worker có thể chạy JDK/dependency versions khác trong một deployment được kiểm soát.
7. **Muốn thay/restart plugin độc lập**: có health check, process supervision, graceful shutdown và restart theo policy.

Những trường hợp **chưa chắc cần** tách tiến trình:

- Plugin nội bộ đáng tin, chỉ xung đột hai phiên bản JSON library.
- Call path cực kỳ nhạy latency và phụ thuộc nhiều object references đồng bộ.
- Cần chia sẻ object graph lớn, JVM heap state, `synchronized` monitors, không dễ thiết kế giao thức chuyển dữ liệu.
- Cơ chế phân quyền yêu cầu không quá mạnh và toàn bộ code đã được review.

Tách tiến trình có **chi phí startup, memory riêng, serialization, IPC latency, deployment/lifecycle**. Chỉ định threat model và giới hạn đáp ứng trước khi chọn kiến trúc.

## 4. Kiến trúc chuẩn: host giữ quyền, worker chỉ nhận job tối thiểu

```text
                        HOST PROCESS
             ┌──────────────────────────────┐
request ---> │ AuthN/AuthZ, business rules  │
             │ secrets / DB credentials     │
             │ validate + rate limit        │
             └────────────┬─────────────────┘
                          │ request đã thu hẹp
                          │ IPC có framing, size/time limits
                          ▼
             ┌──────────────────────────────┐
             │ WORKER PROCESS / JVM riêng    │
             │ low-privilege OS identity     │
             │ filesystem/network allowlist │
             │ CPU, memory, process quotas   │
             │ chạy plugin/parser/library   │
             └────────────┬─────────────────┘
                          │ kết quả không tin cậy
                          ▼
             ┌──────────────────────────────┐
             │ HOST: parse / validate       │
             │ policy check / persist       │
             └──────────────────────────────┘
```

**Nguyên tắc quyền tối thiểu:** worker không cần quyền trực tiếp tới database production, secret store hay host source tree để xử lý một đoạn text. Host có thể truyền **nội dung input đã giới hạn** thay vì mount toàn bộ filesystem chứa file gốc.

**Dữ liệu từ worker không tự đáng tin** chỉ vì worker là process con do host khởi động. Nếu worker chạy code không đáng tin, output phải được parse/validate như input từ một bên ngoài.

### Gợi ý về capability

Thay vì trao “đường dẫn file hệ thống” rồi để worker tự mở tùy ý, có thể thiết kế API:

```text
Host → Worker:
  job_id = "task-42"
  op = "parse-text"
  bounded_input = <nội dung có size limit>
  format = "plain"

Worker → Host:
  job_id = "task-42"
  status = "ok" | "error"
  bounded_result = <kết quả>
```

Đây là **mô hình giao thức**, không phải wire format đã triển khai. Bản production cần framing, validation, versioning, encoding, timeout và cơ chế xác thực/ủy quyền tương ứng kênh giao tiếp.

## 5. `ProcessBuilder` tạo một subprocess, không tự sandbox

Java SE cung cấp `java.lang.ProcessBuilder`:

```java
ProcessBuilder builder =
        new ProcessBuilder(javaExecutable, "-cp", classPath,
                           "worker.Main", "job-123");
Process process = builder.start();
```

Đây là **snippet**, cần các biến và xử lý `IOException`. Mỗi argument là **một phần tử riêng** của danh sách command, không phải ghép một shell command string rồi hy vọng dấu cách/quote được giải đúng.

Những cấu hình quan trọng:

- **`command(...)`**: executable và từng argument. Không chạy qua `cmd /c` hoặc `sh -c` trừ khi thực sự cần shell; truyền user input vào shell gây nguy cơ command injection.
- **`directory(File)`**: working directory của child, không phải sandbox root.
- **`environment()`**: map biến môi trường child. Mặc định là **bản sao** environment từ parent. Cần loại bỏ secrets và allowlist các biến thực sự cần, nhưng một vài biến hệ thống có thể cần để chạy.
- **`redirectInput`/`redirectOutput`/`redirectError`**: chỉ định nguồn/đích streams.
- **`redirectErrorStream(true)`**: trộn stderr vào stdout; tiện khi đọc log, **không phù hợp nếu stdout là giao thức máy đọc**.
- **`start()`**: khởi động subprocess, có thể ném `IOException`.
- **`Process.waitFor()`**, `waitFor(timeout, unit)`, `exitValue()`, `isAlive()`, `destroy()`, `destroyForcibly()`: quản lý lifecycle.
- **`ProcessHandle`**: PID, status và descendants ở mức API; việc quản lý **cả process tree** phụ thuộc hệ điều hành và chính sách sandbox.

**Cực kỳ quan trọng:** `ProcessBuilder` khởi động một tiến trình **với credentials/quyền OS mà launcher cung cấp**. Java không tự đổi sang user ít quyền hơn, tự bật seccomp, tự giới hạn network hay memory khi gọi `start()`. Những giới hạn đó cần đến cấu hình OS/container/orchestrator đáng tin cậy.

## 6. Thực hành A — JVM host gọi JVM worker độc lập

Bài này chứng minh luồng **launch → stdout → exit status** của một process Java riêng. Nó **không phải ví dụ sandbox**, chỉ đặt nền tảng về IPC/lifecycle.

Cấu trúc:

```text
process-lab/
└── src/
    └── demo/
        ├── EchoWorker.java
        └── ProcessHost.java
```

**`src/demo/EchoWorker.java`:**

```java
package demo;

public final class EchoWorker {
    public static void main(String[] args) {
        if (args.length != 1 || !"PING".equals(args[0])) {
            System.err.println("invalid request");
            System.exit(2);
        }

        System.out.println("PONG");
    }
}
```

**`src/demo/ProcessHost.java`:**

```java
package demo;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Locale;

public final class ProcessHost {
    private static String javaExecutable() {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).startsWith("windows");
        String file = windows ? "java.exe" : "java";
        return Path.of(System.getProperty("java.home"), "bin", file)
                .toString();
    }

    public static void main(String[] args) throws Exception {
        String classes = Path.of("out").toAbsolutePath().toString();

        Process process = new ProcessBuilder(
                javaExecutable(), "-cp", classes,
                "demo.EchoWorker", "PING")
                .redirectErrorStream(true)
                .start();

        String reply;
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        process.getInputStream(),
                        StandardCharsets.UTF_8))) {
            reply = reader.readLine();
        }

        int exit = process.waitFor();

        System.out.println("worker says=" + reply);
        System.out.println("exit=" + exit);
    }
}
```

Biên dịch và chạy từ thư mục `process-lab` với **JDK 17+**:

```sh
javac --release 17 -d out src/demo/EchoWorker.java src/demo/ProcessHost.java
java -cp out demo.ProcessHost
```

**Stdout của host trên hệ thống cho phép khởi động tiến trình con:**

```text
worker says=PONG
exit=0
```

### Điều bài thực hành chứng minh

1. Host và worker là **hai JVM processes**; worker có `main`, heap, threads và process exit status riêng.
2. `ProcessBuilder` nhận đường dẫn tới executable `java` từ `java.home` của host, tránh phụ thuộc `PATH` shell. Tên file khác trên Windows và Unix-like platforms.
3. `-cp` trỏ tới **đường dẫn tuyệt đối của `out`**, nên worker thấy `demo.EchoWorker`.
4. `"PING"` là argument cố định. `EchoWorker` xác thực nó rồi trả `PONG` ra stdout.
5. `ProcessHost` đọc một dòng UTF-8, chờ child kết thúc và in exit code 0.
6. Dữ liệu được đưa qua **stdout pipe**, **không phải gọi trực tiếp method trong cùng heap**.

**Giới hạn chủ động:** ví dụ chỉ có một dòng output nhỏ từ worker tin cậy. Với worker tùy ý, `readLine()` **không có giới hạn độ dài**, và đọc đến EOF có thể block nếu worker không đóng stdout. Cần size limit, timeout, pumping stdout/stderr, quy tắc hủy/cleanup như phần sau.

**Lưu ý về deployment:** việc tìm `java.home/bin/java` hoạt động trong nhiều JDK/JRE thông thường; container/custom runtime image có thể không kèm executable hoặc không cho phép exec. Application thực tế cần đường dẫn worker runtime **được cấu hình và xác thực**, không tự giả định luôn có đủ quyền spawn process.

## 7. Vì sao không truyền Java object references trực tiếp qua process?

Ở **cùng JVM**, host có thể gọi:

```java
String result = pluginService.execute(request);
```

Đây là snippet minh họa. Host và plugin cùng dùng object references, heap và runtime types tương ứng.

Ở **hai JVMs**, một object reference kiểu `MyRequest` **không thể** được dereference trực tiếp ở process kia. Cần **serialization/protocol**:

- JSON/CBOR/Protobuf/Avro theo schema được phiên bản hóa;
- newline-delimited messages cho demo đơn giản;
- length-prefixed binary frames khi cần chính xác và giới hạn kích thước;
- HTTP/gRPC qua Unix domain sockets/loopback có authentication phù hợp;
- file/queue được kiểm soát về quyền và lifecycle nếu job có dung lượng lớn.

**Không mặc định Java native serialization `ObjectInputStream` là lựa chọn an toàn** cho dữ liệu không tin cậy; nó có bề mặt deserialization nguy hiểm và phụ thuộc class versions. Ưu tiên schema nhỏ, validation rõ và tránh tự instantiate các classes do đối phương chọn.

### Giao thức tối thiểu phải quy định

| Thuộc tính | Câu hỏi cần chốt |
| --- | --- |
| **Framing** | Một message dài bao nhiêu, kết thúc/length-prefix ở đâu? |
| **Encoding** | UTF-8, cấm/làm rõ ký tự newline, NUL, invalid UTF-8 ra sao? |
| **Version** | Phải đổi client/server thế nào khi schema thay đổi? |
| **IDs** | Ghép response đúng request nào, tránh replay/cross-tenant confusion? |
| **Validation** | Field bắt buộc, range, length, enum, payload limits? |
| **Errors** | Phân biệt bad input, worker crash, timeout, protocol violation? |
| **Authentication** | Ai được kết nối tới IPC endpoint? Dựa vào peer identity hay credential nào? |
| **Resource bounds** | Giới hạn message count, bytes, nested objects, parsing time? |

Một process riêng **giảm shared-memory attacks**, nhưng **IPC parser của host** là bề mặt tấn công mới. Giữ nó đơn giản, có giới hạn và fuzz/test với malformed messages.

## 8. Thực hành B — giao thức stdin/stdout không trộn log

Ví dụ sau chạy một worker lâu hơn một request. Giao thức text chỉ chấp nhận `PING`, `UPPER:...` và `QUIT`; stdout chỉ dùng cho **protocol replies**, còn diagnostics thuộc stderr.

Cấu trúc:

```text
ipc-lab/
└── src/demo/
    ├── ProtocolWorker.java
    └── ProtocolHost.java
```

**`src/demo/ProtocolWorker.java`:**

```java
package demo;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public final class ProtocolWorker {
    public static void main(String[] args) throws Exception {
        try (BufferedReader input = new BufferedReader(
                new InputStreamReader(
                        System.in, StandardCharsets.UTF_8));
             PrintWriter output = new PrintWriter(
                        System.out, true, StandardCharsets.UTF_8)) {

            output.println("READY 1");

            String request;
            while ((request = input.readLine()) != null) {
                if ("PING".equals(request)) {
                    output.println("PONG");
                } else if (request.startsWith("UPPER:")
                           && request.length() <= 106) {
                    String value = request.substring(6);
                    output.println("DATA:" +
                            value.toUpperCase(Locale.ROOT));
                } else if ("QUIT".equals(request)) {
                    output.println("BYE");
                    break;
                } else {
                    output.println("ERR");
                }
            }
        }
    }
}
```

**`src/demo/ProtocolHost.java`:**

```java
package demo;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Locale;

public final class ProtocolHost {
    static String executable() {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).startsWith("windows");
        return Path.of(System.getProperty("java.home"), "bin",
                        windows ? "java.exe" : "java")
                .toString();
    }

    public static void main(String[] args) throws Exception {
        String cp = Path.of("out").toAbsolutePath().toString();
        ProcessBuilder builder = new ProcessBuilder(
                executable(), "-cp", cp, "demo.ProtocolWorker");

        // stderr là diagnostics riêng, không lẫn vào stdout protocol.
        builder.redirectError(ProcessBuilder.Redirect.INHERIT);
        Process process = builder.start();

        try (BufferedReader fromWorker = new BufferedReader(
                    new InputStreamReader(
                            process.getInputStream(),
                            StandardCharsets.UTF_8));
             PrintWriter toWorker = new PrintWriter(
                    process.getOutputStream(), true,
                    StandardCharsets.UTF_8)) {

            System.out.println(fromWorker.readLine());

            toWorker.println("PING");
            System.out.println(fromWorker.readLine());

            toWorker.println("UPPER:java");
            System.out.println(fromWorker.readLine());

            toWorker.println("QUIT");
            System.out.println(fromWorker.readLine());
        }

        System.out.println("exit=" + process.waitFor());
    }
}
```

Biên dịch/chạy từ thư mục `ipc-lab`:

```sh
javac --release 17 -d out src/demo/ProtocolWorker.java src/demo/ProtocolHost.java
java -cp out demo.ProtocolHost
```

**Stdout khi worker và host chạy theo đúng giao thức:**

```text
READY 1
PONG
DATA:JAVA
BYE
exit=0
```

### Phân tích

- Worker in `READY 1` (protocol version) rồi chờ request trên stdin.
- `PrintWriter(..., true, UTF_8)` auto-flush sau `println`, tránh host đợi message chưa được flush.
- Host ghi từng request, đọc một reply tương ứng, đóng streams và chờ exit code.
- `redirectError(INHERIT)` cho worker diagnostics đi tới stderr của host process; stdout tiếp tục chỉ có protocol.
- `Locale.ROOT` làm phép uppercase cho command data không phụ thuộc locale mặc định của máy.
- `QUIT` khiến worker trả `BYE` rồi thoát bình thường.

**Không dùng giao thức demo này cho input bất kỳ mà chưa harden:** `BufferedReader.readLine()` có thể nhận dòng quá dài trước khi code kiểm tra `request.length()`; đây **không phải giới hạn RAM thật sự**. Production phải giới hạn **số bytes trước hoặc trong lúc đọc**, dùng bounded parser/frame, deadline, schema, request ID và quy tắc EOF/partial response.

**Không dùng stdout cho debug print trong worker** nếu stdout là protocol. Một thư viện vô tình `System.out.println("debug")` có thể làm host coi log là reply và phá state machine. Log đi stderr hoặc kênh riêng.

## 9. Bảo vệ stdout/stderr pipes để tránh deadlock

Một lỗi phổ biến:

```java
Process process = builder.start();
int code = process.waitFor();
byte[] output = process.getInputStream().readAllBytes();
```

Đây là **mẫu dễ deadlock**, không phải khuyến nghị production. Nếu child liên tục ghi stdout/stderr và pipe buffer đầy, child có thể block khi ghi, còn host đang chờ child exit trong `waitFor()`. Kết quả là cả hai cùng chờ.

Cách thiết kế:

1. **Drain stdout và stderr liên tục** bằng threads/async tasks; hoặc redirect đến file/đích phù hợp.
2. Đặt **giới hạn output** theo bytes, không chỉ số dòng; cắt/kill nếu quá quota.
3. Đặt **deadline tổng thể** cho job, không chỉ `readLine` hoặc `waitFor` riêng lẻ.
4. Khi stdout là protocol, **không merge stderr vào stdout**; xử lý/ghi log stderr riêng.
5. Đóng stdin khi không cần gửi thêm requests để worker nhận EOF.
6. Nếu child cần tiếp tục xử lý, đọc output qua **bounded queues** và backpressure rõ ràng.
7. Đừng giữ toàn bộ output bằng `readAllBytes()` khi worker có thể xuất vô hạn dữ liệu.

Có thể dùng `redirectOutput(ProcessBuilder.Redirect.DISCARD)` nếu output **không cần**, hoặc `redirectOutput(file)` trong môi trường đã giới hạn dung lượng file/log. Redirect tới file mà không có quota vẫn có thể làm đầy disk.

### Chi tiết về charset

Text protocol phải thống nhất UTF-8 trên **cả hai chiều**. `InputStreamReader(..., UTF_8)` và `PrintWriter(..., UTF_8)` tránh phụ thuộc platform default charset. Nhưng UTF-8 **không tự xác thực cấu trúc JSON/message**; vẫn cần parser, schema và length limits.

## 10. Timeout là điều kiện cần, nhưng không đủ

Một worker có thể:

- treo do deadlock hoặc vòng lặp;
- mất kết nối;
- bị OS scheduler trì hoãn;
- fork thêm child processes;
- tiêu thụ CPU/memory trước khi host phát hiện timeout;
- hoàn tất tác vụ nhưng không gửi response do protocol error.

`Process.waitFor(long timeout, TimeUnit unit)` trả **`boolean`**: `true` khi process đã kết thúc trong khoảng chờ; `false` khi hết thời gian. Nó **không tự kill worker**.

Pattern lifecycle:

```java
boolean finished = process.waitFor(2, TimeUnit.SECONDS);
if (!finished) {
    process.destroy();
    if (!process.waitFor(500, TimeUnit.MILLISECONDS)) {
        process.destroyForcibly();
        process.waitFor();
    }
    throw new java.util.concurrent.TimeoutException(
            "Worker exceeded deadline");
}
int exitCode = process.exitValue();
```

Đây là **snippet**, cần import `TimeUnit`, biến `process` và caller xử lý `InterruptedException`. Với input/output streams còn mở, host vẫn phải có **đọc/ghi có giới hạn và cleanup**. Không đọc một dòng blocking mãi rồi mới bắt đầu chờ timeout, vì như vậy `waitFor(timeout)` có thể không bao giờ được gọi.

`destroy()` yêu cầu dừng theo cơ chế của nền tảng; `destroyForcibly()` là yêu cầu mạnh hơn nhưng quá trình kết thúc có thể không xảy ra tức thời. Sau đó nên `waitFor`/cleanup, kiểm tra lifecycle thực tế.

## 11. Thực hành C — giết worker vượt deadline

Ví dụ độc lập này **không chờ stdout**. Child cố ngủ lâu, host có timeout ngắn, làm sạch process rồi báo trạng thái.

**`src/demo/SlowWorker.java`:**

```java
package demo;

public final class SlowWorker {
    public static void main(String[] args) throws Exception {
        Thread.sleep(30_000);
    }
}
```

**`src/demo/TimeoutHost.java`:**

```java
package demo;

import java.nio.file.Path;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public final class TimeoutHost {
    static String javaExecutable() {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).startsWith("windows");
        return Path.of(System.getProperty("java.home"), "bin",
                        windows ? "java.exe" : "java").toString();
    }

    public static void main(String[] args) throws Exception {
        String cp = Path.of("out").toAbsolutePath().toString();

        Process process = new ProcessBuilder(
                javaExecutable(), "-cp", cp, "demo.SlowWorker")
                .redirectOutput(ProcessBuilder.Redirect.DISCARD)
                .redirectError(ProcessBuilder.Redirect.DISCARD)
                .start();

        boolean finished = process.waitFor(
                250, TimeUnit.MILLISECONDS);

        if (!finished) {
            process.destroyForcibly();
            process.waitFor();
        }

        System.out.println("timed out=" + !finished);
        System.out.println("alive after cleanup=" +
                process.isAlive());
    }
}
```

Biên dịch/chạy từ thư mục chứa `src/demo`:

```sh
javac --release 17 -d out src/demo/SlowWorker.java src/demo/TimeoutHost.java
java -cp out demo.TimeoutHost
```

**Stdout dự kiến trong điều kiện không có can thiệp từ ngoài:**

```text
timed out=true
alive after cleanup=false
```

Tại sao?

- `SlowWorker` ngủ 30 giây nếu không bị dừng.
- Host chỉ chờ tối đa 250 ms, nên trong môi trường bình thường worker chưa thoát.
- `destroyForcibly()` yêu cầu dừng child process, `waitFor()` đợi cleanup hoàn tất.
- `isAlive()` sau `waitFor()` là `false`.
- `Redirect.DISCARD` tránh tồn tại pipe output chưa được drain trong ví dụ worker không trả dữ liệu.

**Lưu ý tính thực nghiệm:** timeout 250 ms là giá trị để quan sát, **không phải SLA hay ngân sách khởi động JVM được khuyên dùng**. Máy rất chậm hoặc process bị can thiệp có thể cho hiện tượng khác; production dùng deadline phù hợp, xử lý launch failure/interrupt và có thể dùng process supervisor. Một tiến trình con cũng có thể **spawn descendants** mà việc kill một PID không dọn sạch hết; cần group/job/cgroup/process-tree policy của OS.

## 12. Giới hạn CPU/RAM không nên chỉ dựa vào flags Java

Dù worker là một JVM riêng, cùng host vẫn có thể tranh tài nguyên vật lý. Các biện pháp:

| Rủi ro | Kiểm soát mạnh hơn |
| --- | --- |
| Dùng heap quá lớn | `-Xmx` giới hạn Java heap, cộng với **OS/container memory limit** cho native/off-heap/metaspace/stacks |
| CPU dùng vô hạn | CPU quota/cgroups/job limits và timeout/watchdog |
| Sinh quá nhiều threads/processes | pids/task quotas, process/job limits, runtime worker pool |
| Ghi output/log không giới hạn | quota disk/output bytes, bounded pipes, log rotation |
| Mở quá nhiều file/socket | file descriptor limits, network policy, quotas |
| Đọc secrets/host files | OS permissions, mount read-only/allowlist, tách UID/credential |
| Gọi mạng ngoài không kiểm soát | egress firewall/network namespace/allowlist |
| Fork bomb/descendant escape | process groups/cgroups/container PID namespace, supervisor dọn cả cây |
| Gây nghẽn IPC | kích thước frame, request deadline, backpressure, concurrent-job quota |

**`-Xmx256m` không có nghĩa tiến trình Java chỉ dùng 256 MB RAM**: heap không gồm mọi native memory, thread stacks, metaspace, JIT/code cache và một số memory mappings. Cần giới hạn **toàn process/container** ở OS layer.

Ví dụ command **minh họa** khi khởi động worker:

```text
java -Xmx256m -cp worker.jar worker.Main
```

Đây chỉ là **cấu hình heap**. Nó không cấp network/filesystem sandbox và không tạo CPU quota. Đặt flags phù hợp JVM version, load và kiểm tra `java -XshowSettings:vm -version` khi debug thực tế.

## 13. Quyền hệ điều hành: tách process cùng user vẫn nguy hiểm

So sánh:

```text
Host PID 1000, user=app-prod
Worker PID 1001, user=app-prod
```

Dù heap khác nhau, nếu OS permissions cho `app-prod` đọc `/srv/secrets`, worker chạy cùng user cũng có thể đọc những files đó. Worker còn có thể hưởng environment variables, home directory và những mount/network routes của host.

Muốn **ranh giới quyền mạnh hơn**, triển khai có thể cần:

- User/UID riêng chỉ có quyền với các files cần thiết.
- Work directory và writable filesystem riêng, read-only root khi phù hợp.
- Chặn kế thừa credentials/environment không cần thiết.
- Không mount Docker socket, host root directory, SSH keys hoặc cloud credentials vào worker.
- Network egress deny-by-default, chỉ allow đúng endpoints.
- Giảm Linux capabilities, bật `no-new-privileges`, sandbox policy như seccomp/AppArmor/SELinux nếu nền tảng hỗ trợ.
- Windows: dùng identity/token/job objects/app container hoặc cơ chế tương đương theo threat model.
- Resource controls cấp OS (cgroups/rlimits/Windows Job Objects), giới hạn pids và thời gian.
- Isolate worker có nguy cơ cao bằng VM hoặc máy riêng khi container không đạt mức tin cậy cần thiết.

**Không có một lời gọi Java SE 17 chuẩn duy nhất** tự bật tất cả các cơ chế này trên mọi OS. Chúng là trách nhiệm của **launcher đáng tin, hệ điều hành và hạ tầng triển khai**.

### Một cấu hình “có process riêng” nhưng vẫn sai

```text
Host và worker:
  user = root
  volume = toàn bộ /var/run và /etc
  cloud env keys được copy đầy đủ
  network = unrestricted
  không có memory/pids quotas
```

Đây là ví dụ **cấu hình cần tránh**. Trong đó tách JVM giảm rủi ro corruption của heap host, nhưng worker vẫn có quyền quá lớn tới máy/hạ tầng. Đừng đánh dấu nó “sandbox an toàn” trong review.

## 14. Environment và tham số: không vô tình đưa bí mật sang worker

Mặc định `ProcessBuilder.environment()` bắt đầu từ một **bản sao môi trường của parent**. Nếu host chứa `DATABASE_PASSWORD`, `CLOUD_TOKEN` hoặc proxy credentials trong environment, worker có thể thừa hưởng chúng.

```java
ProcessBuilder builder = new ProcessBuilder(command);
java.util.Map<String, String> env = builder.environment();

// Chỉ minh họa; chính sách allowlist cần hiểu các biến OS cần thiết.
env.remove("DATABASE_PASSWORD");
env.remove("CLOUD_TOKEN");
```

Đây là **snippet**, cần `command` đã khai báo. Loại vài biến tên biết trước là chưa đủ: có thể còn `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, `HOME`, `PATH`, `SSH_AUTH_SOCK`, credentials do thư viện tự tạo và những giá trị cần để runtime/loader hoạt động.

Trong triển khai thật:

1. Xác định **danh sách biến tối thiểu** worker phải nhận.
2. Tạo môi trường đã kiểm soát, giữ những biến hệ điều hành/runtime cần thiết.
3. Tránh đưa secrets vào **command-line arguments** vì process listing/logs có thể nhìn thấy.
4. Nếu cần secret cho worker, cung cấp **secret riêng phạm vi hẹp, TTL ngắn** qua kênh phù hợp.
5. Kiểm tra cả **inherited file handles, working directory, volumes, container service account và network routes**.
6. Không tin rằng `environment().clear()` làm worker thành sandbox; process vẫn có OS identity và quyền filesystem/network.

`ProcessBuilder.directory(...)` chỉ đổi working directory, **không hạn chế worker đi ra các đường dẫn khác**. Cần OS/filesystem policy cho điều đó.

## 15. IPC authentication, authorization và request validation

Với một pipe riêng do host tạo cho child, người dùng thường có ít nguy cơ client ngoài kết nối nhầm, nhưng protocol vẫn phải chống output không hợp lệ và worker giả mạo thành công. Với **Unix domain socket, TCP localhost hoặc HTTP/gRPC**, vấn đề authentication và authorization càng quan trọng:

- Chỉ endpoint đáng tin được kết nối.
- Mỗi request có tenant/job identity và giới hạn quyền riêng.
- Messages có version, type và length hợp lệ.
- Worker chỉ được yêu cầu một **tập operation allowlisted**.
- Output được kiểm tra signature/schema khi cần; không coi response là source of truth cho authorization.
- Host không làm việc nguy hiểm chỉ vì worker trả `"allow": true`.
- Có cơ chế rate limit, replay protection và mTLS/peer credentials nếu hạ tầng đòi hỏi.
- Loại bỏ input control characters hoặc dùng encoding/framing an toàn để tránh log/protocol injection.

### Không biến IPC thành remote shell

Một API nguy hiểm:

```text
Host → Worker: {"command": "execute arbitrary OS command"}
```

Nếu worker hoặc caller có thể tùy ý định nghĩa command, sandbox rất dễ bị phá vỡ trong phạm vi quyền hiện có. Thay vì generic exec, cho phép các operation tường minh như `CONVERT_DOCUMENT`, `PARSE_METADATA`, `VALIDATE_JSON` với typed arguments và size quotas.

Ngay cả khi worker đã bị giới hạn quyền, **đừng cấp generic commands nếu không cần**. Nguyên tắc least authority nên áp dụng cho cả OS permissions lẫn protocol capabilities.

## 16. Quan hệ ClassLoader bên trong worker và process isolation

Tách JVM không loại bỏ nhu cầu class loading:

```text
HOST JVM
  HostAppLoader → host API, business code

WORKER JVM
  WorkerAppLoader
       └── optional PluginURLClassLoader → plugin.jar, private deps
```

Worker vẫn có thể dùng `URLClassLoader` để cô lập các phiên bản library **trong worker**. Tuy nhiên, ý nghĩa security vẫn đến từ **process/sandbox boundary**; URLClassLoader chỉ tổ chức namespace nội bộ.

**Không chia sẻ trực tiếp `Class<?>` hoặc `Method` giữa hai JVMs.** Host có thể biết tên service trong giao thức, nhưng không có cùng runtime class identity với worker:

- `Class<?>` chỉ có ý nghĩa trong JVM của nó.
- Plugin implementation trong worker không thể được host ép kiểu trực tiếp sang host `api.Plugin`.
- Cách giao tiếp nên qua **serialized request/response**, không qua Java object references.
- Có thể dùng **shared protocol schema** được compile độc lập cho hai JVMs, nhưng bytes/messages mới là đường truyền, không phải cùng object.
- Worker có thể chạy JDK/runtime mới hơn nhưng protocol phải tương thích.

**So sánh chi phí:** class loader trong cùng JVM có method invocation gần như trực tiếp nhưng thiếu security boundary mạnh; IPC giữa tiến trình tốn serialization/copy/scheduling, đổi lại kiểm soát failure domain và quyền rõ hơn.

## 17. ClassLoader identity, serialization và vấn đề type confusion

Trong một JVM, hai `ClassLoader` định nghĩa `com.example.Message` có thể khiến cast lỗi vì type identity khác. Khi tách process, vấn đề đổi dạng:

- Type `Message` phía host và type `Message` phía worker là **hai runtime types** độc lập ngay cả khi source giống nhau.
- Protocol cần xác định **schema** và mapping, ví dụ JSON object với `type`/`version` được allowlist.
- Không giải mã một chuỗi tên class từ worker rồi gọi `Class.forName(userSuppliedName)` để tự instantiate arbitrary types trong host.
- Không dùng Java serialization của object do worker trả nếu bạn không kiểm soát chặt whitelist/filter và gadget surface.
- Kiểm tra maximum nesting/depth, collection counts, scalar ranges, integer overflow, Unicode normalization khi cần.

Nếu worker trả metadata về tệp nguy hiểm, host vẫn cần kiểm chứng trước khi lưu hoặc thực hiện thao tác hệ thống. Process boundary giúp tách quyền, không thay thế **input validation**.

## 18. Lifecycle: restart, cancellation và graceful shutdown

Một worker dài hạn có thể xử lý nhiều requests. Host phải có trạng thái vận hành:

```text
CREATED → STARTING → READY → BUSY → IDLE
                     │       │
                     ▼       ▼
                   FAILED   STOPPING
                              │
                              ▼
                            EXITED
```

Các bước:

1. Khởi động worker với **cấu hình quyền và resource quotas trước khi giao job**.
2. Thực hiện handshake `READY` có protocol version và timeout.
3. Dùng bounded queue để không nhận vô hạn jobs.
4. Theo dõi per-job deadline, overall worker age và health.
5. Khi timeout/cancel: gửi graceful cancel nếu protocol hỗ trợ; nếu không phản hồi, kill theo policy.
6. Với worker sinh con, supervisor phải xử lý **process group/tree** và hậu quả process orphan.
7. Kiểm tra exit status, stderr bounded logs, và phân biệt crash với lỗi business.
8. Không restart vô hạn theo vòng lặp nóng; dùng backoff, giới hạn attempts và alert.
9. Không reuse worker đã vi phạm protocol hoặc tình trạng memory/FD vượt quota.
10. Khi nâng phiên bản, tạo **new worker process** với artifact mới, drain worker cũ rồi dừng.

**Không hứa “kill là rollback toàn bộ side effects”.** Worker có thể đã ghi file hoặc gọi network trước khi bị kill. Nếu cần atomicity, host phải dùng transaction, staging directory, temp files/rename và idempotency keys.

## 19. Theo dõi lỗi: exception vs exit code vs timeout

| Tình huống | Host nhận được gì? | Cách xử lý |
| --- | --- | --- |
| Provider Java trong cùng JVM ném exception | Java exception, cùng stack/call | Phân loại lỗi và cô lập ở application layer |
| Worker subprocess chủ động báo lỗi nghiệp vụ | Structured response, exit có thể vẫn 0 hoặc nonzero theo protocol | Parse code/message; không suy thành lỗi hạ tầng |
| Worker JVM bị crash hoặc bị OS kill | Exit code, EOF/pipe broken, có thể thiếu response | Fail job, giữ diagnostics an toàn, supervisor restart |
| Worker treo | Không nhận response trước deadline | Timeout, cancel/kill, dọn process tree, báo service unavailable |
| Host–worker protocol sai | Malformed/extra/missing frames | Reject, không tiếp tục state machine không an toàn |
| Host không spawn được worker | `IOException` từ `ProcessBuilder.start()` | Kiểm tra executable, permission, cwd, quota |
| Output vượt size quota | Bounded reader phát hiện | Cắt/hủy job, không nạp toàn bộ bytes vào heap host |
| Worker trả hợp lệ nhưng nội dung sai | Business/schema validation failure | Không commit, báo lỗi có context |
| Worker cố truy cập file bị sandbox deny | OS-level permission failure | Coi là policy violation, kiểm tra audit |
| Container OOM killed | Exit hoặc orchestration reason, không nhất thiết Java `OutOfMemoryError` | Resource metrics, quota, design input |

**Đừng chỉ đọc exit code bằng `waitFor()` rồi suy rằng kết quả an toàn.** Cần cả validation của nội dung và tiêu chí business; worker có thể cố tình trả exit 0 với dữ liệu sai.

### Observability tối thiểu

Ghi log có kiểm soát: `jobId`, worker generation, image/JDK version, sandbox policy version, duration, exit status, deadline, input/output sizes và mã lỗi. Không log raw secrets hay nguyên văn input nhạy cảm theo mặc định. Giới hạn stderr và sanitize log để tránh newline/control-character injection.

## 20. Giới hạn của process separation trong cùng host OS

Process riêng vẫn chia sẻ **kernel** với host. Nếu cả hai chạy chung node:

- Worker có thể làm đầy disk hoặc network throughput nếu không có quotas.
- Một lỗ hổng kernel/container có thể vượt isolation.
- CPU/memory pressure trên toàn máy có thể ảnh hưởng host nếu resource controls chưa đủ.
- Docker/container mặc định có các quyền/mount/network khác nhau tùy cấu hình; “đã dùng Docker” **không tự chứng minh** sandbox an toàn.
- Các tài nguyên được host intentionally share qua mount/socket/credentials có thể trở thành đường tấn công.
- Nếu host chạy với quyền root rồi khởi động worker cùng quyền, privilege boundary hầu như không được cải thiện.

**VM riêng** có kernel khác và có thể tăng mức cách ly, nhưng vẫn phụ thuộc cấu hình, patching, networking, secrets handling. Với hostile code, defense in depth là cần thiết: VM/namespace, allowlist network, OS permissions, quotas, logging và protocol validation.

### Tránh “security theater”

`new ProcessBuilder(...).start()` cộng với `-Xmx` và timeout là **điều kiện tốt để tăng khả năng phục hồi**, nhưng chưa đủ để gọi “mã không tin cậy không thể truy cập tài nguyên host”. Đánh giá riêng **confidentiality, integrity, availability**.

## 21. Deployment patterns: one-shot, worker pool và remote worker

| Mẫu | Ưu điểm | Hạn chế | Phù hợp |
| --- | --- | --- | --- |
| Một JVM cho mỗi request | Cleanup bằng process exit, dễ giới hạn thời gian/memory theo job | Startup/GC overhead lớn | Tác vụ hiếm, độ rủi ro cao, batch |
| Worker JVM dài hạn | Amortize startup, cache parser/JIT/dependencies | State leak, lifecycle phức tạp, nhiều requests chung tiến trình | Throughput cao, input tin cậy hơn |
| Pool N workers hạn chế | Kiểm soát concurrency, chọn version, rolling restart | Scheduler/queue/health complexity | Service production tải vừa/lớn |
| Container/VM mỗi job | Isolation/quotas tường minh hơn nếu OS cấu hình đúng | Cold start, resource/orchestration cost | Thực thi code khách hàng ít tin cậy |
| Remote worker trên node khác | Tách cả máy/kernel, có network policy rõ | Network/ops latency, mTLS, service discovery | Boundary mạnh, dữ liệu và quyền cần cách ly |

Một worker pool vẫn phải chặn **cross-tenant state leakage** giữa jobs: state static trong worker JVM, temp files, cached data hoặc những token còn trong RAM có thể rò sang job tiếp theo. Nếu yêu cầu multi-tenant isolation cao, cân nhắc **mỗi tenant/job một process/VM riêng** thay vì reuse worker toàn cục.

## 22. Những nhầm lẫn phổ biến

- **“Custom ClassLoader sandbox được plugin.”** Sai: nó quản lý loading/namespace, không tự đặt quyền OS.
- **“Plugin không thấy host package thì không gọi file/network được.”** Sai: visibility class khác OS capabilities; nhiều JDK APIs vẫn có sẵn.
- **“Chạy JVM con đã an toàn tuyệt đối.”** Sai nếu cùng UID/mount/network/secrets và không có quotas.
- **“`-Xmx128m` giới hạn tổng memory process ở 128 MB.”** Sai: còn native/off-heap/metaspace/thread stacks.
- **“`directory(...)` khiến worker không thể truy cập đường dẫn khác.”** Sai: nó chỉ đặt current working directory.
- **“`environment().clear()` tạo process không quyền.”** Sai: OS identity và các permissions khác vẫn còn.
- **“`ProcessBuilder` nên nhận một chuỗi shell command có nối user input.”** Không; dùng argument list và tránh shell injection.
- **“Chỉ `waitFor()` rồi mới đọc stdout luôn ổn.”** Sai nếu pipes đầy và child block.
- **“Có timeout nghĩa Java tự kill worker.”** Sai: `waitFor(timeout)` chỉ báo kết quả chờ; cần cleanup.
- **“`destroyForcibly()` tự kill toàn bộ descendants.”** Không bảo đảm; cần OS process group/job handling.
- **“Stdout worker có thể vừa log vừa trả JSON không sao.”** Không nếu stdout là kênh protocol có framing nghiêm ngặt.
- **“Đã có process isolation thì không cần validate response.”** Sai: worker output vẫn không tin cậy.
- **“Java serialization là lựa chọn IPC mặc định an toàn.”** Không nên mặc định dùng cho untrusted data.
- **“Security Manager sẽ thay thế OS sandbox trên JDK mới.”** Sai; JDK 24 đã permanently disable Security Manager.
- **“Kill worker sẽ rollback mọi thay đổi nó thực hiện.”** Sai: external side effects có thể đã xảy ra.
- **“Docker mặc định tương đương VM riêng.”** Sai: container thường chia sẻ kernel và quyền phụ thuộc cấu hình.
- **“Tách process khiến Java ClassLoader không còn cần thiết.”** Sai: worker vẫn có classpath/module loading riêng.
- **“Hai JVM có thể truyền trực tiếp `Class<?>`/object reference.”** Sai: phải có serialization/protocol và schema.

## 23. Checklist trước khi đánh dấu một worker là ‘isolated’

**Threat model và quyền:**

1. Input/code nào được xem là không tin cậy?
2. Worker có chạy dưới OS identity **khác host** không?
3. Worker có nhìn thấy host secrets, config, mounts, sockets không?
4. Network policy có **deny-by-default** nếu workload không cần network không?
5. Có giới hạn CPU/memory/PIDs/FD/disk/output bytes thực sự ở OS/orchestrator không?
6. Có quyền chỉnh sửa host filesystem hoặc dùng Docker socket không?

**IPC và hành vi:**

7. Protocol có version, bounded framing, schema validation và request ID không?
8. Có chặn command injection, deserialization gadgets, path traversal và log injection không?
9. Host coi **mọi response là dữ liệu không tin cậy** và xác thực lại không?
10. Stdout protocol có tách stderr diagnostics, cả hai đều bounded không?
11. Timeout có bao trùm spawn, handshake, request, read/write và shutdown không?
12. Worker có thể spawn grandchildren; OS policy có dọn cả process group/cgroup không?
13. Retry có idempotency/transaction để tránh double side effects không?

**Vòng đời và vận hành:**

14. Có startup readiness, health, cancellation, versioning và exit reason không?
15. Có audit logs/metrics không làm lộ secrets?
16. Worker cũ có thể leak state giữa tenants/jobs không?
17. Có thể rolling restart khi JAR/JDK version đổi mà không làm gián đoạn toàn host không?
18. Security controls có được **kiểm thử bằng hành vi bị từ chối**, không chỉ bằng tài liệu cấu hình không?

Nếu nhiều mục quan trọng chưa đáp ứng, hãy ghi nhận boundary hiện tại là **“separate JVM / fault isolation”**, chưa gọi là **“secure sandbox”**.

## 24. Bài tập mở rộng và kiểm thử

### Bài tập 1 — lỗi runtime trong worker

Đổi `EchoWorker` ở thực hành A để ném `RuntimeException` hoặc `System.exit(7)`. Quan sát host **vẫn chạy**, nhận exit khác 0 hoặc EOF/diagnostics, rồi có thể trả lỗi cho request thay vì sập JVM host. Không dùng exit code 0 để coi mọi kết quả là đúng; phải validate response.

### Bài tập 2 — giới hạn output

Thay worker bằng đoạn code liên tục in nhiều MB dữ liệu. Viết một **bounded stream consumer** trong host, dừng sau ví dụ 64 KiB output, hủy worker và đảm bảo không `readAllBytes()` toàn bộ stream. Đồng thời drain stderr nếu cần, có deadline để không bị block.

### Bài tập 3 — cấm network/file

Đưa worker vào một OS sandbox/container đã cấu hình chỉ cho đọc một input directory và ghi một output directory, chặn network. Yêu cầu worker thử đọc một file ngoài allowlist hoặc kết nối tới destination bị chặn, rồi kiểm tra **thực sự bị OS từ chối**. Đừng dựa vào Java ClassLoader để mô phỏng permission.

### Bài tập 4 — worker protocol sai

Cho `ProtocolWorker` cố tình trả `UNKNOWN 1`, một dòng dài quá quota hoặc đóng stdout giữa reply. Host phải **reject** và dọn process theo deadline, không coi đó là kết quả hợp lệ. Trong thiết kế production, frame decoder phải enforce size **trước khi allocate payload lớn**.

### Bài tập 5 — crash, timeout và retry

Cho worker kết thúc đột ngột rồi test host có phân biệt crash với timeout không, có backoff khi restart không, và có bảo vệ idempotency khi job đã gây side effects. Mục tiêu là vận hành có kiểm soát, không chỉ “gọi lại Java process” mỗi lần lỗi.

## 25. Câu hỏi tự kiểm tra

**1. URLClassLoader cô lập chủ yếu điều gì?** Runtime class namespace/defining loader, dependency versions; không tự cô lập heap/process hay OS permissions.

**2. Tại sao tiến trình riêng là boundary mạnh hơn loader?** Nó có address space/JVM heap/lifecycle độc lập và OS có thể cấp identity/quotas khác.

**3. Tại sao hai JVMs cùng OS user chưa đủ an toàn?** Worker vẫn có thể đọc file/network/secrets mà user đó được phép truy cập.

**4. `ProcessBuilder.start()` có tự bật sandbox không?** Không; nó chỉ khởi động process theo cấu hình command/environment/IO/cwd đã cung cấp.

**5. Có nên ghép `"sh -c " + userInput` để chạy tác vụ worker không?** Không; dễ command injection. Dùng fixed executable + argument list và operation allowlist.

**6. Vì sao không đọc stdout sau `waitFor()` trong mọi trường hợp?** Pipes có thể đầy khiến child block khi ghi và host block chờ exit.

**7. `waitFor(timeout, unit)` có tự kill không?** Không; khi trả `false` caller cần cancellation/destroy/cleanup.

**8. `-Xmx` có giới hạn toàn bộ RAM của JVM không?** Không; còn native/off-heap/metaspace/stacks.

**9. Có thể truyền object Java trực tiếp giữa hai processes không?** Không; cần serialize/protocol hoặc shared-memory mechanism có hợp đồng cụ thể.

**10. Tại sao response của worker vẫn cần validate?** Worker có thể bị compromise, trả dữ liệu sai hoặc gây protocol injection.

**11. `destroyForcibly()` có chắc kill process tree không?** Không; cần OS supervisor/group/cgroup handling khi worker sinh process con.

**12. Đổi `ProcessBuilder.directory` có cô lập filesystem không?** Không; chỉ đổi working directory.

**13. Java Security Manager có dùng được để sandbox trên JDK 24 không?** Không; từ JDK 24 nó permanently disabled.

**14. Khi nào nên dùng VM/container riêng mỗi job?** Khi threat model đòi tách kernel/tenant/credentials hoặc quotas mạnh hơn một process cùng quyền, và chi phí cho phép.

**15. Điều quan trọng nhất khi chọn boundary là gì?** Xác định **đối tượng đe dọa, tài nguyên cần bảo vệ và quyền worker thật sự có**, rồi kiểm thử giới hạn bằng hành vi thực.

## 26. Tài liệu chuẩn và tham khảo

- [Java SE 17 — `ProcessBuilder` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html): command arguments, environment, working directory, IO redirects và start.
- [Java SE 17 — `Process` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html): streams, `waitFor`, timeout, `destroy`, `destroyForcibly`.
- [Java SE 17 — `ProcessHandle` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessHandle.html): process identity, descendants và lifecycle observations.
- [Java SE 17 — `ClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): class loading, namespace và delegation.
- [OpenJDK JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): Java 17 deprecation và định hướng tách khỏi Security Manager.
- [OpenJDK JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): thay đổi JDK 24.
- [Oracle Java SE 24 — The Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html): hành vi từ JDK 24 trở đi.
- [OWASP — Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html): validate schema, allowlist và boundary input.
- [OWASP — OS Command Injection Defense Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html): tránh shell injection và xây command safely.

**Kết luận:** **ClassLoader** giải quyết chủ yếu bài toán **class identity/dependency visibility**, không cô lập quyền hệ điều hành. **Tiến trình JVM riêng** cô lập heap và failure domain tốt hơn, nhưng chỉ trở thành ranh giới bảo mật thực tế khi chạy với **OS identity/permissions/quota/network/filesystem limits** phù hợp, dùng **IPC có kiểm soát**, có **timeout/supervision** và coi kết quả worker là **dữ liệu không tin cậy**. Nếu cần mức bảo đảm cao hơn, cân nhắc **container/VM/máy riêng** theo threat model, thay vì chỉ tăng độ phức tạp của custom ClassLoader.
