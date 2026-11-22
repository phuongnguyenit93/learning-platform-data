# Tách mã không tin cậy sang tiến trình riêng với giao thức trao đổi rõ ràng

## 1. Vì sao phải tách tiến trình?

Trong hệ thống Java mở rộng động, plugin có thể được nạp bằng `URLClassLoader`, `ServiceLoader`, `ModuleLayer`, biên dịch trong bộ nhớ hoặc JShell. Những kỹ thuật này giúp cô lập *tên class, dependency và vòng đời logic*, nhưng không tự giới hạn quyền hệ điều hành của code được chạy trong cùng JVM. Một plugin độc hại hoặc lỗi có thể đọc file mà tiến trình được phép đọc, tạo kết nối mạng, thay `System` properties, làm cạn heap/CPU, tạo thread vô hạn hoặc gây crash qua native code.

Ranh giới thích hợp hơn với **mã không tin cậy** là chạy mã đó ở **process riêng** dưới quyền OS giới hạn, giao tiếp qua một giao thức có định dạng và hạn mức rõ ràng. Process riêng cho phép tách heap, threads, static state, system properties và lỗi JVM, nhưng chỉ trở thành ranh giới an toàn khi kết hợp OS permissions, filesystem/network isolation và resource limits.

```text
                 Trust boundary
Host JVM               |         Worker JVM / sandbox
business logic         |         code plugin không tin cậy
    |                   |                   |
    +-- request ------->| IPC codec ------->|
    |                   |                   |
    +<-- response ------| IPC codec <-------+
    |                   |
timeout / circuit      |     quyền OS tối thiểu, giới hạn CPU/RAM
breaker / audit        |     namespace/container/VM tùy mức rủi ro
```

**Điểm chính:** IPC không làm plugin đáng tin; IPC chỉ thu hẹp bề mặt tương tác. Host vẫn phải coi response từ plugin là dữ liệu không tin cậy, validate mọi trường và xử lý trường hợp process chết, treo hoặc trả sai định dạng.

## 2. Định nghĩa ranh giới quyền trước khi chọn công nghệ IPC

Một process mới thường kế thừa quyền của user chạy process tạo ra nếu không có cấu hình OS/container khác. Vì vậy **`new ProcessBuilder(...)` không tự sandbox**. Cần lựa chọn cơ chế triển khai phù hợp:

| Mục tiêu | Biện pháp cần xem xét |
| --- | --- |
| Không đọc bí mật của host | Chạy với OS user riêng, filesystem permissions, mount hạn chế |
| Không truy cập mạng tùy ý | Network policy, namespace, firewall/egress allowlist |
| Không chiếm hết CPU/RAM | cgroups/container limits, job objects, process quotas |
| Không tạo process con không kiểm soát | Policy sandbox, process limits, cleanup process tree |
| Không làm hỏng JVM host | Process boundary và kiểm soát input/output |
| Không khai thác API đặc quyền của host | Chỉ công bố IPC operations tối thiểu; kiểm tra authorization từng request |
| Không kéo host vào deadlock | Timeout, bounded queue, cancellation, process kill policy |

Chạy process con dưới cùng tài khoản OS, cùng mount và toàn quyền mạng có thể chỉ đạt **cô lập lỗi**, chưa đủ **cô lập quyền**. Trên Linux có thể dùng user/container/namespace, seccomp và cơ chế MAC; trên Windows cân nhắc restricted token, job objects, AppContainer hoặc VM; lựa chọn thực tế phụ thuộc môi trường. Không tự tuyên bố sandbox an toàn chỉ vì có một JAR khác.

## 3. Thiết kế giao thức: càng nhỏ, càng rõ

Một giao thức IPC nên có những trường và quy tắc tường minh:

- **Version:** `protocolVersion` hoặc loại message có thể nâng cấp có kiểm soát.
- **Request ID:** ghép request với response, nhất là khi concurrency hoặc retry.
- **Operation:** allowlist các lệnh như `ECHO`, `CALCULATE`, `TRANSFORM`; không cho worker nhận lệnh shell tùy ý.
- **Payload:** schema rõ, kiểu và kích thước tối đa; validation trước khi gửi và sau khi nhận.
- **Status/error:** phân biệt thành công, lỗi nghiệp vụ, lỗi schema và lỗi worker.
- **Framing:** cách tách các message, ví dụ newline-delimited JSON hoặc length-prefixed frames.
- **Deadline/cancellation:** timeout từng request; chiến lược kill/restart worker khi không phản hồi.
- **Encoding:** UTF-8 và quy tắc escape, newline, null bytes.
- **Backpressure:** bounded queue/giới hạn concurrent requests.

Ví dụ JSON Lines có thể là:

```json
{"version":1,"requestId":"r-123","op":"ECHO","payload":{"text":"hello"}}
{"version":1,"requestId":"r-123","ok":true,"result":{"text":"hello"}}
```

Đây là **hai message riêng**, không phải một JSON object: request từ host và response từ worker. Nếu dùng JSON Lines, payload chứa ký tự xuống dòng phải được escape bên trong JSON, không được tự ghép raw newline. Với production, nên dùng JSON parser/schema validator đáng tin thay vì phân tích JSON bằng `split` hoặc regex.

### Vì sao cần version?

Worker cũ có thể hiểu trường `payload.text` nhưng không hiểu `payload.encoding`. Nếu host gửi schema mới mà không negotiation, worker có thể xử lý sai dữ liệu thay vì từ chối. Quy tắc tốt là fail closed khi `version` không được hỗ trợ, hoặc xác định rõ trường nào optional và backward-compatible.

## 4. Demo Java 17+ runnable: hai JVM, giao thức dòng tối giản

Ví dụ này chủ ý dùng **giao thức text một dòng** (`PING`/`ECHO`/`QUIT`) để chạy chỉ với Java SE, không cần JSON library. Nó minh họa process boundary và tương tác qua stdin/stdout, **không phải sandbox bảo mật hoàn chỉnh**. Phiên bản production nên thay bằng schema có version/request ID, framing và codec thực thụ.

File `WorkerMain.java` chạy trong tiến trình con:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;

public final class WorkerMain {
    public static void main(String[] args) throws Exception {
        BufferedReader in = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));
        PrintWriter out = new PrintWriter(
                new java.io.OutputStreamWriter(System.out, StandardCharsets.UTF_8), true);
        String line;
        while ((line = in.readLine()) != null) {
            if (line.equals("PING")) {
                out.println("OK:PONG");
            } else if (line.startsWith("ECHO:")) {
                String payload = line.substring(5);
                if (payload.length() > 100) {
                    out.println("ERR:TOO_LONG");
                } else {
                    out.println("OK:" + payload);
                }
            } else if (line.equals("QUIT")) {
                out.println("OK:BYE");
                return;
            } else {
                out.println("ERR:UNKNOWN_COMMAND");
            }
        }
    }
}
```

File `HostMain.java` khởi tạo một JVM khác, gửi request và chờ response:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.concurrent.*;

public final class HostMain {
    public static void main(String[] args) throws Exception {
        String javaBinary = Path.of(System.getProperty("java.home"),
                "bin", "java").toString();
        Process process = new ProcessBuilder(
                javaBinary, "-cp", ".", "WorkerMain")
                .redirectError(ProcessBuilder.Redirect.INHERIT)
                .start();
        ExecutorService readerThread = Executors.newSingleThreadExecutor();
        try (BufferedWriter toWorker = new BufferedWriter(
                    new OutputStreamWriter(
                            process.getOutputStream(), StandardCharsets.UTF_8));
             BufferedReader fromWorker = new BufferedReader(
                    new InputStreamReader(
                            process.getInputStream(), StandardCharsets.UTF_8))) {

            String[] requests = {"PING", "ECHO:hello", "QUIT"};
            for (String request : requests) {
                toWorker.write(request);
                toWorker.newLine();
                toWorker.flush();

                Future<String> response = readerThread.submit(fromWorker::readLine);
                String line = response.get(3, TimeUnit.SECONDS);
                if (line == null) throw new IllegalStateException("Worker EOF");
                System.out.println(request + " -> " + line);
            }
            if (!process.waitFor(3, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                throw new IllegalStateException("Worker did not exit");
            }
            if (process.exitValue() != 0) {
                throw new IllegalStateException("Worker exit=" + process.exitValue());
            }
        } catch (TimeoutException timeout) {
            process.destroyForcibly();
            throw new IllegalStateException("Worker response timed out", timeout);
        } finally {
            if (process.isAlive()) process.destroyForcibly();
            readerThread.shutdownNow();
        }
    }
}
```

Chạy cả hai file trong cùng thư mục trên JDK 17+:

```bash
javac --release 17 WorkerMain.java HostMain.java
java HostMain
```

Output:

```text
PING -> OK:PONG
ECHO:hello -> OK:hello
QUIT -> OK:BYE
```

Giải thích: `ProcessBuilder` khởi chạy một JVM khác; host ghi UTF-8 vào stdin và nhận một dòng từ stdout. Mỗi response có timeout 3 giây. `QUIT` kết thúc worker; host kiểm tra exit code. Để tối giản, request được gửi tuần tự, chỉ một request outstanding, không có request ID; vì thế **không thể** dùng demo này nguyên trạng cho concurrency nhiều request.

**Giới hạn demo:** reader task nếu đã kẹt ở `readLine()` và timed out sẽ được giải quyết bằng việc hủy/đóng process streams khi process bị kill; trong môi trường production nên thiết kế một reader loop độc lập và bounded queue để quản lý cancellation chắc chắn. Demo cũng chạy worker cùng tài khoản OS và không tạo sandbox: muốn dùng với mã chưa tin cậy, phải launch nó trong môi trường bị hạn chế quyền.

## 5. Vì sao không trộn stderr vào stdout?

Nếu stdout là kênh protocol, mọi dòng log từ worker ghi vào stdout có thể bị hiểu nhầm thành response, phá framing. Cần quy ước:

- **stdout**: chỉ protocol messages.
- **stderr**: diagnostics/log, có giới hạn dung lượng và chính sách redaction.
- Nếu stdout dùng binary frames, không ghi bất kỳ text tùy tiện nào vào stream này.

`redirectErrorStream(true)` thuận tiện cho chạy shell đơn giản nhưng **không nên** dùng với protocol chỉ dựa trên stdout, vì stderr sẽ trộn vào response. Demo dùng `.redirectError(INHERIT)` để tránh đụng protocol; production có thể capture stderr riêng trong buffer giới hạn và gửi sang logging pipeline.

## 6. Timeout, cancellation, retries và process lifecycle

Process có thể treo do deadlock, vòng lặp vô tận, chờ I/O, garbage collection hoặc mã độc cố tình không phản hồi. Một protocol an toàn cần hai timeout riêng:

1. **Request deadline:** tối đa bao lâu chờ một response.
2. **Shutdown deadline:** tối đa bao lâu đợi worker thoát sau lệnh dừng.

Khi timeout:

- Đánh dấu request thất bại; đừng nhận response muộn như response của request mới.
- Gửi cancellation nếu protocol hỗ trợ; nếu không đáng tin hoặc hết deadline, kill process.
- Reap/cleanup process, đóng input/output streams, hủy reader/writer tasks.
- Nếu worker giữ state, xác định có thể retry an toàn hay không; request có side effect cần idempotency key hoặc transaction ID.
- Circuit breaker có thể tạm dừng gửi tới plugin đang lỗi liên tục, nhưng phải có recovery policy.

Quyết định retry phải dựa trên semantics. `ECHO` là tác vụ không side effect, dễ retry; `TRANSFER_FUNDS` có thể cần deduplication và exactly-once *business semantics* thông qua durable storage, không thể chỉ retry sau timeout.

### Khi worker crash giữa request

Host cần phân biệt EOF, broken pipe, nonzero exit code, protocol violation và timeout. Một EOF không chứng minh tác vụ đã hoàn tất hay rollback: nếu worker đã ghi dữ liệu bên ngoài trước khi crash, trạng thái có thể không xác định. Contract phải định nghĩa kết quả `UNKNOWN`/reconciliation cho operation có side effects.

## 7. Kiểm tra input/output, message size và framing

Với JSON Lines, mỗi dòng là một JSON document. Cần giới hạn kích thước trước khi parse: `BufferedReader.readLine()` không áp giới hạn bytes mặc định, nên nếu worker cố ý gửi dòng cực lớn, host có thể tiêu tốn bộ nhớ. Với length-prefixed binary protocol, giới hạn frame length trước khi cấp phát buffer.

Thiết lập ít nhất:

| Hạng mục | Quy tắc ví dụ |
| --- | --- |
| Protocol version | Từ chối version lạ |
| Request ID | Unique trong session, không tái sử dụng khi còn pending |
| Operation | Allowlist enum, không thực thi raw shell expression |
| Payload | Schema validation và byte limit |
| Response | Parse nghiêm ngặt, kiểm tra ID, status và size |
| Deadlines | Per-request timeout và shutdown timeout |
| Concurrency | Bounded inflight requests và queue length |
| Encoding | UTF-8, escaping phù hợp cho JSON |
| Logging | stderr riêng, không chứa secret không cần thiết |

Đừng dùng `ObjectInputStream` Java serialization như một lựa chọn IPC mặc định với dữ liệu không tin cậy: deserialization có rủi ro gadget/object graph và coupling chặt class versions. JSON/Protobuf/CBOR với schema và validator rõ ràng thường dễ kiểm soát hơn; vẫn phải cấu hình parser an toàn, giới hạn nesting/size và kiểm tra trường bắt buộc.

## 8. Thỏa thuận phiên bản và capability

Host cần biết worker nói protocol nào trước khi gửi yêu cầu nghiệp vụ. Có thể mở đầu với handshake:

```json
{"version":1,"requestId":"init-1","op":"HELLO","payload":{"supportedVersions":[1]}}
{"version":1,"requestId":"init-1","ok":true,"result":{"selectedVersion":1,"capabilities":["ECHO"]}}
```

Nếu không có version giao nhau hoặc thiếu capability bắt buộc, **không kích hoạt worker**. Cần phân biệt protocol version (định dạng và semantics IPC) với phiên bản plugin implementation hoặc contract nghiệp vụ.

Không để worker tự ý yêu cầu host mở file/URL bất kỳ: nếu protocol có operation `READ_FILE`, host phải kiểm tra allowlist/path canonicalization/quyền trên từng request và không cấp quyền rộng hơn cần thiết. Khi worker là bên nhận request từ host, host cũng cần xác thực responses và không tin metadata worker tự khai.

## 9. Một số kiến trúc IPC và lựa chọn

| Phương án | Phù hợp | Rủi ro cần quản lý |
| --- | --- | --- |
| stdin/stdout | Worker cục bộ, startup đơn giản | Framing, backpressure, stderr isolation, reader threads |
| Unix domain socket / named pipe | IPC máy cục bộ, nhiều request | Filesystem/pipe permissions, authentication |
| HTTP/gRPC loopback | API rõ và hỗ trợ tooling tốt | Bind address, mTLS/token auth, port leakage, timeouts |
| Message queue | Worker phân tán, retry/durability | Duplicate delivery, idempotency, ordering, poison messages |

Không có transport nào tự giải quyết trust boundary. Lựa chọn dựa trên latency, nhu cầu concurrency, portability, auth và operational complexity.

## 10. Kiểm thử hợp đồng và kiểm thử phá hoại

Những test nên có trước khi chạy mã chưa tin cậy:

- **Happy path:** request/response đúng schema, version, ID và kết quả.
- **Malformed frame:** worker gửi JSON lỗi, trường thiếu, version sai, ID không khớp.
- **Large payload/output:** vượt byte limits, nesting sâu, output spam.
- **Timeout/hang:** worker không trả lời; host kill và cleanup đúng deadline.
- **Crash:** worker exit nonzero hoặc chết giữa message.
- **Concurrency:** nhiều request cùng lúc không bị ghép nhầm response.
- **Retry/idempotency:** timeout sau side effect không tạo thao tác kép.
- **Permission test:** worker không đọc được secret path, không mở egress bị cấm.
- **Resource quota:** worker tiêu CPU/memory vượt mức bị hạn chế.
- **Restart/reload:** worker version khác được handshake lại; process cũ được drain.

Kiểm thử quyền trong **môi trường triển khai thực tế**, không chỉ unit test Java. Một policy container bị cấu hình sai có thể khiến worker vẫn đọc được filesystem của host dù protocol được viết đúng.

## 11. Những lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Coi `ClassLoader` là sandbox | Code vẫn dùng quyền tiến trình | Tách process và áp OS isolation |
| Coi `ProcessBuilder` tự giới hạn quyền | Worker chạy cùng user và quyền | Restricted OS identity/container policy |
| Dùng stdout cho cả log và protocol | Parsing nhầm response | Tách stderr, framing chặt |
| Không giới hạn message length | OOM từ payload/output lớn | Bounded decoding |
| Không có request ID/version | Nhầm response, khó nâng giao thức | Handshake và correlation |
| Retry mọi request sau timeout | Lặp side effects | Idempotency keys và reconciliation |
| Dùng Java object deserialization mặc định | Rủi ro bảo mật và coupling | Codec/schema validation |
| Không kill process bị treo | Rò rỉ tài nguyên và queue | Deadlines và process-tree cleanup |
| Tin kết quả worker không kiểm chứng | Injection/data corruption | Validate output và authorization |

## 12. Checklist triển khai

- [ ] Đặt mã không tin cậy trong process/container/VM với quyền tối thiểu.
- [ ] Giới hạn CPU, RAM, file/network/process resources của worker.
- [ ] Định nghĩa protocol version, request ID, operations, schema và framing.
- [ ] Giới hạn input/output bytes, depth, concurrency và queue.
- [ ] Dùng stdout riêng cho protocol và stderr cho logs.
- [ ] Áp timeout, cancellation, kill/restart và process cleanup.
- [ ] Xác thực mọi response, không nhận raw data làm command đặc quyền.
- [ ] Thỏa thuận capability trước khi route request.
- [ ] Thiết kế retry dựa trên idempotency, phân biệt UNKNOWN outcome.
- [ ] Test crash, malformed output, hang, quota, permission denial.

**Kết luận:** tách plugin không tin cậy sang JVM/process riêng là bước cần thiết để tạo ranh giới lỗi và cơ hội áp quyền OS. Muốn trở thành giải pháp an toàn, cần **sandbox ở cấp OS/container** và **giao thức IPC nhỏ, có version, schema, framing, deadline, validation và error handling rõ ràng**. Không một classloader hoặc giao thức text đơn giản nào tự bảo đảm an toàn cho mã không tin cậy.
