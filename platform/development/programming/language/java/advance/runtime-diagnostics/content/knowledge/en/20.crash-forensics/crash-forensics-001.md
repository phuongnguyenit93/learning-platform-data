# 20.1 Phân biệt exception Java, OutOfMemoryError, StackOverflowError và fatal VM error

## 1. Mục tiêu: nhận diện đúng loại lỗi trước khi điều tra crash

Trong Java, dòng chữ **“error”**, stack trace trên `stderr` hay việc service biến mất **không đồng nghĩa** JVM đã crash. Bốn nhóm hiện tượng thường bị đánh đồng:

1. **Java exception**: ứng dụng/thư viện phát sinh một đối tượng `Throwable` thuộc nhánh `Exception`, ví dụ `IOException`, `SQLException`, `NullPointerException`, `IllegalArgumentException`. Nó có thể được xử lý, trả HTTP error, làm kết thúc một thread hoặc dẫn tới dừng ứng dụng tùy logic.
2. **`java.lang.OutOfMemoryError` (OOME)**: JVM hoặc môi trường thực thi không đáp ứng được một yêu cầu về bộ nhớ/tài nguyên. Đây là **`Error`**, không phải `Exception`, và có nhiều nguyên nhân khác nhau: heap, metaspace, native thread, vùng native/direct memory, giới hạn array...
3. **`java.lang.StackOverflowError` (SOE)**: một thread vượt giới hạn stack thực thi, thường vì đệ quy không có điểm dừng, đệ quy quá sâu hoặc chuỗi gọi hàm lặp. Nó cũng là **`Error`**, không phải exception thông thường.
4. **Fatal VM error**: HotSpot gặp sự cố không thể tiếp tục, ví dụ lỗi truy cập bộ nhớ ở native/JNI/JIT/VM code hoặc một internal VM error. JVM thường **chấm dứt tiến trình**, cố tạo **`hs_err_pid...log`** và có thể sinh core/minidump. Đây **không phải** một `Throwable` Java mà `catch` có thể xử lý.

Còn một trường hợp thứ năm quan trọng: **tiến trình bị hệ điều hành/container giết**, chẳng hạn Linux OOM killer hoặc `SIGKILL`. Khi đó có thể **không** xuất hiện `OutOfMemoryError`, `hs_err_pid`, heap dump hay `finally`. Vì vậy phải kết hợp bằng chứng phía JVM **và** phía OS/orchestrator.

Mục tiêu bài này là nhận diện bằng **hierarchy, dấu hiệu, artifact, scope ảnh hưởng, cơ chế phục hồi và quy trình postmortem**, không suy luận chỉ từ tên exception.

## 2. Sơ đồ phân cấp `Throwable`

Trong Java SE, cây lớp liên quan là:

```text
java.lang.Object
  └── java.lang.Throwable
        ├── java.lang.Exception
        │     ├── các checked exception, ví dụ IOException
        │     └── java.lang.RuntimeException
        │           ├── NullPointerException
        │           ├── IllegalArgumentException
        │           └── nhiều runtime exception khác
        └── java.lang.Error
              ├── java.lang.VirtualMachineError
              │     ├── OutOfMemoryError
              │     ├── StackOverflowError
              │     ├── InternalError
              │     └── UnknownError
              ├── AssertionError
              ├── LinkageError
              └── ...
```

**Lưu ý:** đây chỉ là nhánh rút gọn phục vụ bài học, không phải tất cả các subclass của `Throwable`.

- **`Throwable`** là gốc có `message`, `cause`, `stackTrace` và `suppressed exceptions`. Một `Throwable` đã được tạo ra có thể được xử lý bởi `try/catch` nếu execution còn chạy bình thường.
- **Checked exception**: subclass của `Exception` nhưng **không phải `RuntimeException`**. Java compiler yêu cầu catch hoặc khai báo `throws`; ví dụ `IOException`.
- **Unchecked exception**: `RuntimeException` và subclass. Không bắt buộc khai báo `throws`; thường thể hiện lỗi logic, tham số, trạng thái hoặc vi phạm contract. Một số exception có thể phản ánh I/O/remote failure được wrap thành runtime exception.
- **`Error`**: cũng là `Throwable` nhưng đại diện các vấn đề nghiêm trọng hoặc không nên xử lý như lỗi nghiệp vụ thông thường. Java không yêu cầu `catch` hoặc khai báo nó. `OutOfMemoryError`/`StackOverflowError` thuộc nhóm `VirtualMachineError`.
- **Fatal VM error** (như native `SIGSEGV`) **không nằm trong cây `Throwable`**: không có Java object bắt buộc phải tồn tại, không phải là một `Error` Java được `throw` theo đường thông thường.

Do đó, nhận định “`OutOfMemoryError` là exception vì tên có chữ Error/stack trace” là sai về **type hierarchy**. Nhận định “mọi `Error` đều khiến VM crash lập tức” cũng sai: `AssertionError`, `StackOverflowError` hoặc `OutOfMemoryError` có thể được throw trong Java rồi ứng dụng tiếp tục chạy một phần, mặc dù tình trạng vẫn có thể nguy hiểm.

## 3. Bảng phân biệt nhanh trước khi mở log

| Tiêu chí | Java exception | `OutOfMemoryError` | `StackOverflowError` | Fatal VM error |
| --- | --- | --- | --- | --- |
| Kiểu sự cố | `Exception`/`RuntimeException` | `Error → VirtualMachineError` | `Error → VirtualMachineError` | Lỗi runtime/native **ngoài `Throwable`** |
| Bằng chứng ban đầu | Exception class, message, stack trace, `Caused by` | `java.lang.OutOfMemoryError: <detail>`, GC/memory metrics | `java.lang.StackOverflowError`, frames lặp, depth lớn | `A fatal error has been detected...`, `SIGSEGV`/`EXCEPTION_ACCESS_VIOLATION`, `hs_err_pid` |
| Dữ liệu quan trọng nhất | Root cause, stack, input/trace ID, ứng dụng context | **Detail message**, heap/non-heap/native/container metrics | Stack frames lặp và thuật toán đệ quy, call graph | Signal/exception, **problematic frame**, native stack, JVM build, core |
| Có thể `catch` Java? | Có | Về mặt cú pháp có, nhưng khó bảo đảm phục hồi an toàn | Về mặt cú pháp có, nhưng không nên dựa vào phục hồi | **Không** bằng `try/catch` Java |
| Có tự dừng toàn JVM? | Không nhất thiết | Không nhất thiết; chính sách JVM hoặc resource pressure có thể kết thúc JVM | Không nhất thiết; thread có thể kết thúc | Thường **kết thúc JVM/process** |
| `hs_err_pid` mặc định? | Không | Thường **không** đối với Java OOME thuần; có ngoại lệ ở native/fatal failures | Thường **không** đối với SOE Java thuần | **Có thể được tạo** nếu fatal reporter còn hoạt động |
| Heap dump khi bật `HeapDumpOnOutOfMemoryError`? | Không chỉ vì exception thường | Có thể, tùy nguyên nhân/build và khả năng ghi | Không chỉ vì SOE | Không thể coi đây là artifact mặc định |
| Trọng tâm khắc phục | Bug/validation/retry/contract | Pool bộ nhớ cụ thể, allocation/retention, giới hạn OS/cgroup | Đệ quy, vòng gọi hàm, stack depth, cấu trúc giải thuật | Native/JNI/JIT/VM, build, library và môi trường |

Các cột “có thể” là có chủ đích: hệ thống đang thiếu RAM, đĩa đầy, process bị kill hoặc VM đã hỏng có thể không kịp tạo artifact. **Không thấy `hs_err_pid` không chứng minh không có fatal error**; phải kiểm tra nơi lưu, quyền ghi và OS logs.

## 4. Java exception: lỗi ở tầng ngôn ngữ/thư viện, không đồng nghĩa JVM crash

### Checked exception

Ví dụ `java.io.IOException` khi thao tác I/O, `java.sql.SQLException` khi xử lý JDBC. Code cần bắt hoặc khai báo:

```java
import java.io.IOException;

public class CheckedExample {
    static void readConfig() throws IOException {
        throw new IOException("configuration unavailable");
    }

    public static void main(String[] args) {
        try {
            readConfig();
        } catch (IOException ex) {
            System.out.println("handled=" + ex.getClass().getSimpleName());
        }
        System.out.println("still_running");
    }
}
```

Chạy `javac --release 17 CheckedExample.java` rồi `java CheckedExample`. Output do `System.out.println`:

```text
handled=IOException
still_running
```

Ví dụ có `catch` hợp lệ và tiến trình đi tiếp. **Không suy** cứ bắt được exception là dữ liệu nghiệp vụ an toàn; transaction đã commit một phần, file đã ghi dở hoặc remote operation có thể đã hoàn thành mặc dù client nhận lỗi. Cần rollback, idempotency và retry policy phù hợp.

### Runtime exception

```java
int port = Integer.parseInt("not-a-number");
// java.lang.NumberFormatException (một RuntimeException)
```

Đây là **mảnh minh họa**, không phải file Java độc lập. `NumberFormatException` không bắt buộc khai báo `throws`; nếu không xử lý, thread hiện tại có thể kết thúc và in stack trace. **Uncaught exception trong một worker thread không tự chứng minh toàn process đã chết**; thread khác còn sống, event loop hoặc supervisor có thể tiếp tục. Nếu main thread chết và không còn non-daemon threads, process có thể kết thúc.

### Tại sao không bắt mọi lỗi bằng `catch (Throwable)`?

```java
try {
    executeRequest();
} catch (Throwable problem) {
    // Không nên coi mọi Throwable đều là lỗi HTTP 500 có thể phục hồi.
}
```

Đây là **mảnh minh họa thiếu định nghĩa `executeRequest()`**, không phải chương trình chạy hoàn chỉnh. Cách catch quá rộng nuốt cả `OutOfMemoryError`, `StackOverflowError` và các `Error` nghiêm trọng. Sau resource exhaustion, việc tạo response/log stack trace hoặc cấp phát buffer mới có thể tiếp tục thất bại. Handler ứng dụng thông thường nên phân biệt lỗi nghiệp vụ, I/O có thể retry và lỗi hệ thống nghiêm trọng; **đừng che mất trạng thái không lành mạnh của process**.

## 5. `OutOfMemoryError`: một tên lớp, nhiều nguyên nhân khác nhau

**`java.lang.OutOfMemoryError`** thường cho biết một allocation hoặc resource request không thể thực hiện. Nhưng **điều kiện cạn tài nguyên có thể thuộc nhiều vùng**:

| Detail message trên HotSpot/JDK điển hình | Nhóm tài nguyên/gợi ý | Hướng điều tra |
| --- | --- | --- |
| `Java heap space` | Không cấp phát được object/array trong Java heap | `-Xmx`, GC logs, heap usage/histogram/dump, retained objects, cache/list/map tăng |
| `GC overhead limit exceeded` | JVM tốn phần lớn thời gian cho GC, rất ít bộ nhớ được giải phóng (khi cơ chế này áp dụng) | GC frequency, heap pressure, allocation rate, retained live set |
| `Metaspace` | Class metadata vùng native/metaspace | Classloader retention, dynamic proxy/bytecode generation, `MaxMetaspaceSize` |
| `Compressed class space` | Vùng compressed class pointers/class metadata (khi bật cơ chế liên quan) | Classloading, class metadata, `CompressedClassSpaceSize` |
| `Requested array size exceeds VM limit` | Array request vượt giới hạn implementation | Input size/length calculation; **không phải** cứ tăng `-Xmx` là giải được |
| `unable to create native thread` hoặc thông điệp tương tự | JVM/OS không tạo được native/platform thread | Process/thread count, `ulimit`, cgroup PIDs, native stack memory, memory pressure |
| `Direct buffer memory` hoặc lỗi reserve direct buffer | Off-heap direct buffer limit / native reservation | Direct buffer usage, `MaxDirectMemorySize` nếu có, reference retention, RSS |
| `request ... bytes for ... Out of swap space?` hoặc native allocation failure | Native memory/OS allocation, đôi khi có fatal VM handling | Native Memory Tracking, OS mapping, swap/cgroup, core/`hs_err_pid` nếu có |

**Detail string thay đổi theo JDK/vendor/nguồn cấp phát**; không dùng chính xác bảng này như enum API. Phải đọc **nguyên văn dòng lỗi** trước khi chỉnh flag.

### 5.1 Heap đầy khác memory leak

`OutOfMemoryError: Java heap space` **không tự chứng minh leak**. Có ít nhất bốn khả năng:

1. `-Xmx` đặt quá nhỏ so với live set hợp lệ;
2. tải, payload hay concurrency tăng làm allocation/live data tăng theo nhu cầu;
3. chương trình giữ tham chiếu không cần thiết (unbounded cache, static collection, listener, queue), tức leak logic;
4. workload có một request tạo object/array rất lớn, hoặc allocation burst.

Cách phân biệt: so sánh heap **sau GC**, allocation rate, request concurrency, tuổi object và dominator/retained size trong heap dump. Nếu heap sau các đợt GC cứ tăng mãi với cùng workload, leak khả nghi hơn; nếu tăng rồi ổn định, có thể là cache/working set bình thường. **Tăng `-Xmx` chỉ để che triệu chứng** có thể đẩy incident chậm hơn, không sửa retention leak.

### 5.2 Metaspace và classloader

Metaspace là bộ nhớ **native quản lý class metadata**, không phải Java object heap theo cách đếm thông thường. Nếu `Metaspace` tăng bền vững, điều tra số class loaded/unloaded, module hot-reload, agent, proxy factory, classloader còn được giữ. Có thể dùng `jcmd <PID> VM.classloader_stats`/`VM.metaspace` trên HotSpot hỗ trợ, phối hợp NMT. `ClassLoader` objects còn trong heap có thể giữ cả hệ sinh thái class metadata.

### 5.3 Native thread không tạo được

Thông báo `unable to create native thread` có thể vì thiếu memory cho thread stacks, OS process/thread limit, container `pids.max` hoặc các resource constraints. **Đừng chỉ tăng Java heap**; tăng `-Xmx` đôi khi còn giảm không gian còn lại cho native memory. Xem số platform threads, executor creation, `-Xss` (nếu có áp dụng), RSS, OS ulimit và cgroup limits. Virtual threads (JDK 21+) không ánh xạ mỗi virtual thread thành một kernel thread cố định, nhưng **không loại bỏ** giới hạn carrier/platform threads và những tài nguyên native khác.

### 5.4 Cạn memory không có nghĩa Java báo OOME

Trên Linux/Kubernetes, khi cgroup vượt giới hạn, **OOM killer có thể gửi `SIGKILL`** cho process mà Java không kịp throw `OutOfMemoryError`. Khi đó JVM thường không ghi heap dump và không chạy shutdown hooks. Container có thể báo `reason=OOMKilled`, exit status điển hình 137, nhưng **137 tự nó chỉ cho biết termination liên quan SIGKILL**, không xác nhận nguyên nhân là cgroup OOM; cần đối chiếu container events/kernel logs.

## 6. `StackOverflowError`: lỗi chiều sâu call stack, không phải heap leak

**`java.lang.StackOverflowError`** xảy ra khi một thread vượt khả năng stack được cấp cho nó, thường do đệ quy quá sâu hoặc vòng gọi không có điểm dừng:

```java
// Mảnh code minh họa lỗi, KHÔNG chạy trực tiếp trên production.
static void recurseForever() {
    recurseForever(); // Không có base case.
}
```

Với một stack trace điển hình, bạn sẽ thấy các frame phương thức lặp lại rất nhiều lần:

```text
java.lang.StackOverflowError
    at com.example.Tree.walk(Tree.java:42)
    at com.example.Tree.walk(Tree.java:42)
    at com.example.Tree.walk(Tree.java:42)
    ...
```

Đây là **output minh họa rút gọn**, không phải stdout cố định; JDK có thể giới hạn số frame trong stack trace. Cũng có lỗi do **mutual recursion** giữa hai/hơn hai phương thức hoặc tuần hoàn trong cấu trúc object, ví dụ `toString()` gọi sang nested object rồi quay lại, Jackson serialization trên graph có cycle, visitor đi cây quá sâu.

### Cách sửa ưu tiên

- Xác định **base case** và điều kiện tiến tới base case; phát hiện cycle bằng tập visited/identity khi duyệt graph.
- Với input có thể sâu do người dùng điều khiển, áp **depth limit hợp lý**, báo lỗi validation khi vượt thay vì dùng stack như giới hạn nghiệp vụ.
- Chuyển DFS/recursive traversal cực sâu sang **iterative algorithm** với `Deque` hoặc cơ chế stream/chunk phù hợp.
- Với `equals()`, `hashCode()`, `toString()`, serializer/deserializer, kiểm tra quan hệ object hai chiều.
- `-Xss` có thể thay đổi stack size của platform threads trên HotSpot, nhưng **chỉ là tham số thực thi**, không sửa thuật toán đệ quy vô hạn. Tăng `-Xss` cũng tăng chi phí reservation/stack của threads; cần benchmark và cân nhắc native memory.

Với **virtual threads**, cơ chế quản lý stack không giống platform thread (stack có thể lưu theo stack chunks trên heap); không áp một công thức cứng “mỗi virtual thread dùng `-Xss` bytes”. Tuy nhiên recursion quá sâu vẫn có thể gây lỗi nghiêm trọng, và ứng dụng vẫn phải bảo vệ algorithm/input.

### `StackOverflowError` có luôn làm JVM chết?

**Không.** Nó là Java `Error` được throw trong một thread khi stack overflow. VM có thể vẫn chạy, nhưng thread/operation có thể thất bại; trạng thái application/transaction có thể đã dang dở. Dùng `catch (StackOverflowError)` để “tiếp tục logic như bình thường” không phải chiến lược phục hồi đáng tin. Ưu tiên sửa đệ quy/call graph và để supervisor khởi động lại workload đã hỏng khi cần.

### StackOverflowError khác native stack overflow gây fatal

Có tình huống lỗi stack trong JNI/native code hoặc VM runtime gây **fatal crash**, không chỉ `StackOverflowError` Java. Dấu hiệu là signal/`hs_err_pid` và native/problematic frame; đừng dùng tên nguyên nhân “stack overflow” để suy luôn loại throwable. **Artifact mới quyết định nhánh điều tra.**

## 7. Fatal VM error: khi HotSpot không thể tiếp tục

HotSpot VM fatal error thường xuất hiện sau lỗi **native/JNI, JVM runtime, JIT compiled code, internal assertion hoặc không thể phục hồi tài nguyên native**. Trên Linux/macOS có thể có `SIGSEGV` (segmentation fault), `SIGBUS`, `SIGILL` hoặc `SIGABRT`; trên Windows có thể thấy `EXCEPTION_ACCESS_VIOLATION`. Dấu hiệu điển hình:

```text
# A fatal error has been detected by the Java Runtime Environment:
#
#  SIGSEGV (0xb) at pc=0x..., pid=12345, tid=12346
#
# JRE version: ...
# Java VM: ...
# Problematic frame:
# C  [libexample.so+0x...]
#
# An error report file with more information is saved as:
# /var/log/java/hs_err_pid12345.log
```

Đây là **đoạn minh họa**, không phải kết quả từ một vụ crash thật; text, layout và frames thay đổi theo JDK/OS. Có thể xuất hiện Java compiled frame `J`, VM frame `V`/`v` hoặc native frame `C`. `Problematic frame` gợi ý điểm fault, **chưa chứng minh root cause cuối cùng**: memory corruption từ trước đó có thể chỉ biểu hiện khi một thư viện khác dereference pointer.

Fatal VM error:

- thường khiến **process chấm dứt** và không thể được xử lý bằng `try/catch` Java;
- có thể ghi file **`hs_err_pid<pid>.log`**, đôi khi core/minidump tùy cấu hình OS và dung lượng;
- có thể xảy ra khi dùng JNI/JNA, FFM/native interop, agents/profilers, native drivers, JVM bugs, CPU instruction set/memory problems;
- không luôn là “lỗi JVM của Oracle/OpenJDK”: phải xem địa chỉ/libraries/frames và xây dựng reproducer trước khi quy kết.

**Không phải mọi native signal đều là fatal**; HotSpot sử dụng một số signal cho mục đích nội bộ. Kết luận phải dựa trên **fatal report/process termination** chứ không chỉ số lượng signal trong `strace`.

## 8. `hs_err_pid` chứa gì và đọc theo thứ tự nào?

File fatal error của HotSpot thường có tên `hs_err_pid<PID>.log` ở working directory JVM hoặc địa điểm cấu hình bằng `-XX:ErrorFile=...`. Nếu ghi tại đó thất bại, JVM có thể tìm nơi fallback như OS temporary directory, **nhưng không có bảo đảm sẽ tạo file trong mọi crash**.

Khi đã có `hs_err`, đọc:

1. **Header**: loại signal/exception, program counter (pc), PID/TID, JVM build và `Problematic frame`.
2. **Current thread / thread state**: tên và trạng thái thread gặp lỗi; Java frames, native frames, compiled/interpreted modes.
3. **Native stack và dynamic libraries**: tên `.so`/`.dll`/`.dylib`, offsets; so với phiên bản thư viện native/JNI/agent có trong deployment.
4. **VM arguments / environment**: `-Xmx`, `-Xss`, GC, command line, `JAVA_HOME`, library paths, container/OS version, memory/cpu availability.
5. **Heap/GC/metaspace, memory map và các threads khác**: có memory pressure hay vấn đề đồng thời hay không.
6. **Error reporting warnings**: nếu log tự ghi “error occurred during error reporting” hoặc thiếu một phần, coi report **không đầy đủ**, không tự bịa frame còn thiếu.

Một `Problematic frame: C [libmyjni.so+...]` thường nên bắt đầu điều tra từ **native library/JNI**. Một frame `J` hay `V` cần xem thêm JIT/VM stack và crash reproducer; **không có nghĩa Java source ở frame là thủ phạm chắc chắn**. Địa chỉ native chỉ có giá trị khi đối chiếu đúng **binary build và debug symbols**.

## 9. Chuẩn bị thu bằng chứng trước khi incident xảy ra

Các JVM flags sau dành cho **HotSpot có hỗ trợ**, đặt trước `-jar` hoặc main class. Đây là ví dụ cấu hình **startup** của service, không phải thứ có thể thêm vào process đang chạy mà không restart.

```bash
java \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/diagnostics \
  -XX:ErrorFile=/var/diagnostics/hs_err_pid%p.log \
  -Xlog:gc*:file=/var/diagnostics/gc.log:time,uptime,level,tags \
  -jar application.jar
```

Ví dụ dùng cú pháp tiếp dòng của shell Unix/Linux; trên PowerShell cần đặt options trên **một dòng** hoặc dùng ký tự tiếp dòng của PowerShell. Thư mục `/var/diagnostics` phải tồn tại, process Java có quyền ghi, đủ disk; trong container phải mount volume phù hợp nếu muốn giữ artifact sau restart.

### Phân biệt các option

| Option | Dùng khi nào | Không nên kỳ vọng |
| --- | --- | --- |
| `-XX:+HeapDumpOnOutOfMemoryError` | Cần heap snapshot khi HotSpot báo `OutOfMemoryError` và có thể ghi | Không bảo đảm trên mọi loại native OOM, container OOM kill hoặc fatal VM crash |
| `-XX:HeapDumpPath=<path>` | Đặt file/đường dẫn tạo heap dump (HPROF) | Không tự kích hoạt heap dump khi thiếu flag trên |
| `-XX:ErrorFile=<path>` | Đặt file fatal error report, hỗ trợ token `%p` là PID | Không tạo `hs_err` cho một Java exception thông thường |
| `-Xlog:gc*...` | Theo dõi GC và heap pressure trước OOME | Không trực tiếp chỉ ra retained object graph |
| `-XX:NativeMemoryTracking=summary` | Cần quan sát native memory JVM từ startup | Không bao phủ mọi native allocation của third-party libraries |
| `-XX:+ExitOnOutOfMemoryError` | Chính sách vận hành muốn JVM thoát khi phát hiện OOME | Không thay thế việc phân tích nguyên nhân; phải có supervisor |
| `-XX:+CrashOnOutOfMemoryError` | Chính sách đặc biệt muốn VM abort/crash khi OOME để có artifacts crash phù hợp | Có thể tạo core rất lớn, tăng downtime/disk; không nên bật vô điều kiện |

`ExitOnOutOfMemoryError` và `CrashOnOutOfMemoryError` là hai **chính sách phản ứng khác nhau**. Không bật bừa hoặc kết hợp chúng như một “bộ flags bắt buộc”; kiểm tra hành vi trên đúng JDK, staging và hệ orchestration. Nếu crash/exit quá nhanh, dump hoặc log có thể không kịp ghi hoàn chỉnh. **Quan trọng:** `HeapDumpOnOutOfMemoryError` phục vụ **Java heap evidence**, không phải native core dump; `ErrorFile` phục vụ **fatal VM report**, không phải file `.hprof`.

### JFR trước crash

Nếu cần lịch sử những giây/phút trước sự cố, có thể bật **continuous JFR** từ startup:

```bash
java -XX:StartFlightRecording=name=ring,settings=default,disk=true,maxage=1h,maxsize=256m -jar application.jar
```

Khi process còn sống, dùng `jcmd <PID> JFR.dump name=ring filename=/var/diagnostics/before-incident.jfr`. Khi process bị kill/crash, **không mặc định** sẽ có file JFR hoàn chỉnh; có thể cần tìm repository chunks hoặc artifact đã được hệ quan sát lưu trước đó. Hãy bảo vệ dữ liệu quan trọng bằng cơ chế dump theo lịch hoặc trigger phù hợp nếu policy cho phép.

## 10. Bộ lệnh chẩn đoán khi process còn sống

Nếu service có dấu hiệu OOM/stack issue nhưng JVM chưa chết, xác định PID và đọc bằng chứng có kiểm soát:

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> GC.heap_info
jcmd <PID> Thread.print -l
jcmd <PID> JFR.check
```

Với JVM đã bật NMT từ startup:

```bash
jcmd <PID> VM.native_memory summary scale=MB
```

Các command cần runtime HotSpot tương thích, quyền attach, PID namespace và JDK tools. `VM.native_memory` không thể tự tạo số liệu quá khứ nếu NMT chưa được bật. `jcmd <PID> Thread.print` trên JVM nhiều thread có thể in output rất lớn.

### Heap dump chủ động

```bash
jcmd <PID> GC.heap_dump /var/diagnostics/heap-before-restart.hprof
```

Đây là **lệnh có chi phí/impact cao**; thường yêu cầu dừng tạm thời/safepoint hoặc công việc nặng và có thể tốn rất nhiều RAM/disk. Không tự chạy trên production đang cạn tài nguyên mà không cân nhắc rủi ro; chọn đúng thời điểm/có quyền và bảo đảm dung lượng. `.hprof` thường chứa object data nhạy cảm.

**Không thể chạy các lệnh này sau khi process đã chết.** Khi JVM biến mất, ưu tiên log đã lưu, `hs_err`, core dump, `.hprof` đã tạo, orchestrator/container status và OS kernel logs.

## 11. Java 17+ runnable: kiểm tra hierarchy và cách exception được xử lý

Lưu chương trình sau thành **`FailureTaxonomyDemo.java`**:

```java
import java.io.IOException;

public class FailureTaxonomyDemo {
    static void failChecked() throws IOException {
        throw new IOException("disk unavailable");
    }

    public static void main(String[] args) {
        try {
            Integer.parseInt("not-a-number");
        } catch (NumberFormatException ex) {
            System.out.println(
                    "runtime_exception=" + ex.getClass().getSimpleName());
        }

        try {
            failChecked();
        } catch (IOException ex) {
            System.out.println(
                    "checked_exception=" + ex.getClass().getSimpleName());
        }

        System.out.println("oome_is_error=" +
                Error.class.isAssignableFrom(OutOfMemoryError.class));
        System.out.println("soe_is_vm_error=" +
                VirtualMachineError.class.isAssignableFrom(
                        StackOverflowError.class));
    }
}
```

Biên dịch/chạy với Java 17+:

```bash
javac --release 17 FailureTaxonomyDemo.java
java FailureTaxonomyDemo
```

**Stdout chính xác của chương trình:**

```text
runtime_exception=NumberFormatException
checked_exception=IOException
oome_is_error=true
soe_is_vm_error=true
```

Chương trình **không** tạo OOME, SOE hoặc fatal error. Nó kiểm tra quan hệ type system một cách an toàn:

- `NumberFormatException` là nhánh `RuntimeException`, có thể catch cụ thể.
- `IOException` là checked exception, phương thức `failChecked()` khai báo `throws`, caller phải xử lý/khai báo.
- `OutOfMemoryError` là subclass của `Error`; `StackOverflowError` là subclass của `VirtualMachineError`.
- Hai dòng cuối **không nói** OOME/SOE “an toàn để tiếp tục” mà chỉ chứng minh inheritance.

### Tại sao không tạo thật một JVM crash trong bài thực hành?

Một demo cố tình cấp phát vô hạn, đệ quy vô hạn hoặc làm JVM `SIGSEGV` có thể gây thiếu RAM, làm chậm máy hoặc tạo dump rất lớn. **Không chạy những thử nghiệm đó trên production hoặc máy dùng chung**. Khi cần tái hiện, dùng môi trường cô lập, cgroup/memory/CPU/disk limits, timeouts, artifacts và quyền thích hợp. Không coi một bài test có OOME nhỏ trong sandbox là bằng chứng root cause cho OOME production khác.

## 12. Quy trình postmortem: phân loại theo bằng chứng đầu tiên

### Bước 1 — tìm sự thật về lifecycle process

Ghi timestamp tuyệt đối, timezone, PID/container ID, hostname, deployment SHA/JDK build, memory limits, exit code/reason và log cuối cùng. Phân biệt:

- **Java stack trace có `Exception`/`Error`** nhưng process còn sống: bắt đầu từ throwable detail, request context, lỗi logic hoặc memory pool.
- **Có `hs_err_pid` và header fatal signal/internal VM error**: bắt đầu từ fatal VM report, native frames, JVM/vendor/library versions.
- **Không có Java stack trace, process bị `OOMKilled` hoặc `SIGKILL`**: bắt đầu từ OS/cgroup/kube events, memory graphs, RSS, page cache/native memory và container limits; đừng bịa ra `OutOfMemoryError`.
- **Ứng dụng tự gọi `System.exit` hoặc supervisor gửi SIGTERM**: có thể là dừng có chủ đích hoặc health-policy, không phải lỗi memory. Kiểm tra application logs, deploy events và shutdown handler.

### Bước 2 — đọc **thông báo đầy đủ**, không chỉ top-level summary

Ví dụ các stack traces dạng rút gọn:

```text
java.lang.NumberFormatException: For input string: "abc"
    at ...
```

```text
java.lang.OutOfMemoryError: Java heap space
    at ...
```

```text
java.lang.StackOverflowError
    at com.example.Tree.walk(Tree.java:42)
    at com.example.Tree.walk(Tree.java:42)
    ...
```

Đây là **mẫu minh họa**, không phải log thật. Java exception cần xem `Caused by:`, nested/suppressed exceptions và request ID. OOME cần **detail string** trước khi mở heap dump; SOE cần frames lặp, input gây recursion và JVM stack configuration. Fatal signal cần `hs_err`/core.

### Bước 3 — gom đúng artifacts

| Nhóm nghi vấn | Artifact cần ưu tiên |
| --- | --- |
| Checked/runtime exception | Application logs, trace ID, payload đã ẩn dữ liệu nhạy cảm, stack trace/cause, release, transaction status |
| Heap OOME | `.hprof` nếu có, GC logs, heap metrics/trends, `-Xmx`, load/concurrency, class histogram |
| Metaspace OOME | `VM.metaspace`, `VM.classloader_stats`, class counts, reload patterns, native memory metrics |
| Native/thread/direct OOME | NMT, RSS/cgroup, PID/thread limits, direct buffer pools, OS maps, kernel/container events |
| SOE | Stack trace depth/repeated methods, input graph, recursion base case, `-Xss`, code version |
| Fatal VM error | `hs_err_pid`, core/minidump nếu có, problematic/native frames, native libraries, JDK/vendor/build, JVM flags, environment |
| OOM kill/SIGKILL | Pod/container exit reason, kernel OOM logs/cgroup events, memory limit/usage, RSS graph; thường **không** có Java dump |

### Bước 4 — ưu tiên an toàn và phục hồi dịch vụ

Thu bằng chứng tự động hóa nếu đã cấu hình, nhưng **không trì hoãn khôi phục dịch vụ chỉ để chờ dump vô hạn**. Khi nghi trạng thái process đã bị hỏng sau `VirtualMachineError`, dùng chính sách health/restart phù hợp. Không bắt OOME và tiếp tục phục vụ request như bình thường chỉ vì code biên dịch được.

### Bước 5 — đối chiếu và kiểm chứng

Một giả thuyết tốt phải khớp cả **error type + message + tài nguyên + thời gian + repro/điều kiện tải**. Sửa bằng chứng ở đúng tầng:

- OOME heap → quản lý object lifetime/heap sizing/GC/concurrency;
- OOME native → native allocations, thread/pid limits, off-heap usage, cgroup;
- SOE → base case, cycle detection, iterative algorithm;
- native fatal → điều tra JNI/library/JIT/VM và versions;
- Java exception → input contract, exception handling, transactions/retries.

Sau thay đổi, xác minh error rate, memory trend sau GC, RSS, thread counts, latency và khả năng phục hồi dưới tải tương đương.

## 13. Bốn incident thực tế để luyện phân biệt

### Tình huống A — API trả HTTP 500, service vẫn nhận request

Log có `NullPointerException` ở mapper, cùng request ID, process PID vẫn nguyên. **Nhánh xử lý:** runtime exception (application bug). Xác định input thiếu dữ liệu hoặc object không được khởi tạo, kiểm tra stack/cause, validate hợp lệ, thêm test cho request tương ứng. **Không** tìm `hs_err_pid` như artifact chính, không bật heap dump OOME để giải quyết NPE.

**Cần lưu ý:** một exception không được xử lý có thể khiến **thread** kết thúc. Process có tiếp tục hay không tùy thread lifecycle/framework; không phải “exception không bao giờ làm service chết”.

### Tình huống B — Sau 8 giờ tải, `OutOfMemoryError: Java heap space`

Logs cho thấy heap after GC tăng dần, GC thường xuyên, `.hprof` tồn tại do bật flag. **Nhánh xử lý:** heap OOME. Phân tích dominator tree/histogram, static cache, retained collections, queue size và tác động release mới. `-Xmx` có thể tạm thay đổi để giảm áp lực nhưng phải chứng minh memory footprint phù hợp container limit, tránh OOM kill do tổng heap+native vượt cgroup.

**Không kết luận:** tên class nhiều nhất theo shallow bytes **không tự là leak owner**; xem retained references và allocation/lifecycle.

### Tình huống C — Một batch job crash `StackOverflowError` ở cây dữ liệu

Stack trace lặp `Tree.visit` hàng nghìn frame, input có cycle hoặc độ sâu vượt thiết kế. **Nhánh xử lý:** SOE. Repro bằng dữ liệu đã ẩn danh, thêm visited set/depth guard hoặc chuyển sang iterative DFS/BFS; tránh tăng `-Xss` như “bản vá cuối cùng” cho recursion vô hạn. Nếu cùng lúc có `hs_err`/native SIGSEGV, kiểm tra liệu đang gặp **fatal native stack failure** thay vì chỉ SOE Java.

### Tình huống D — Container chết, không có Java throwable, exit 137

Orchestrator báo `OOMKilled`, RSS/cgroup memory usage tăng; không có `.hprof` và `hs_err`. **Nhánh xử lý:** kernel/container OOM kill. Điều tra memory limit, off-heap/direct/native buffers, thread stacks, process heap size, shared page cache và monitoring của cgroup. **Không** kết luận JVM đã throw `OutOfMemoryError`; kill có thể đến trước khi JVM nhận ra hoặc không đi qua code path OOME.

Nếu chỉ có exit 137 mà không có `OOMKilled` reason, kiểm tra ai gửi `SIGKILL`, timeout, deploy/operator actions và kernel logs trước khi kết luận cạn RAM.

### Tình huống E — `SIGSEGV`, `hs_err_pid` có `Problematic frame: C [libnative.so...]`

**Nhánh xử lý:** fatal VM/native crash. Kiểm tra đúng `libnative.so` build, JNI callsite, native memory safety, version JDK/OS, reproduction, core dump và thread involved. Một crash trong native frame **không tự chứng minh bug của chính thư viện tại frame đó**: memory corruption có thể bắt đầu từ chỗ khác; cần trace/coredump để kết luận.

## 14. Kỹ thuật đọc crash artifacts mà không tạo kết luận giả

### `.hprof`

Heap dump là snapshot object graph của Java heap. Dùng Eclipse MAT/VisualVM/JDK tools phù hợp để xem dominator tree, retained sizes, leak suspects. **Không phải native core**: heap dump không cho biết mọi `malloc` trong JNI, OS stack hay mọi địa chỉ cấp phát native. Dump có thể rất lớn, chứa mật khẩu/session/token/PII trong object graph, phải được mã hóa và giới hạn truy cập.

### `hs_err_pid*.log`

Là **fatal VM log** của HotSpot: signal, thread, native frames, VM arguments, memory map và trạng thái thu được lúc crash. Có thể không có vì disk/permission/OS kill hoặc reporting cũng gặp lỗi. Không nhầm file này với **Java application log** do Logback/Log4j/SLF4J ghi.

### Core dump/minidump

Là artifact **OS-level** chứa trạng thái tiến trình phục vụ native debugger, có thể rất lớn và nhạy cảm. Khả năng thu phụ thuộc `ulimit -c`, `core_pattern`, `systemd-coredump`, Windows WER, container security và disk quota. Một `.core` không phải `.hprof` và không mở được như heap dump. Không chia sẻ công khai core dumps production.

### GC logs

Cho biết heap occupancy/GC pauses trước khi OOME; giúp phân biệt allocation burst, live-set bền vững và collector pressure. **Không tự chỉ ra Java object nào giữ reference**; cần heap dump/tracing tương ứng.

### NMT và OS metrics

Native Memory Tracking dùng `-XX:NativeMemoryTracking=summary/detail` từ lúc startup; `jcmd VM.native_memory` cho số reserved/committed theo HotSpot categories. Không phải tổng RSS của process, không bao phủ hết third-party native libraries. Đối chiếu `RSS`/`cgroup memory`, direct buffer pool, OS mapping và thread count.

### JFR

JFR giúp thấy trước crash: allocation, GC, thread scheduling, locking và application events. Nếu chỉ kích hoạt sau sự cố thì không thể hồi cứu; continuous recording cần retention và dump khi process còn sống. `.jfr` là artifact khác `.hprof`/`hs_err`; đừng kỳ vọng một loại thay thế hoàn toàn loại khác.

## 15. Những lỗi phổ biến khi chọn phương án sửa

| Ngộ nhận | Vì sao sai | Hướng đúng |
| --- | --- | --- |
| “Bất kỳ stack trace nào cũng là JVM crash” | Java exception có thể được catch và service tiếp tục | Kiểm tra PID/process lifecycle, loại throwable |
| “`Error` nghĩa là OS process đã chết” | `Error` là Java `Throwable`, không nhất thiết dừng cả JVM | Đọc thread/service state; xét policy restart |
| “OOME luôn do Java heap” | Metaspace, native threads, direct/native allocations và limits khác | Phân biệt theo **detail message** + metrics |
| “OOME luôn là leak” | Có thể do heap sizing, payload burst, concurrency | So sánh live set sau GC, retained size, workload |
| “Tăng `-Xmx` chữa mọi memory issue” | Có thể giảm native headroom và gây cgroup OOM kill | Tính budget heap + non-heap + native + OS |
| “Có exit 137 thì chắc Java OOME” | 137 thường do SIGKILL, không chứng minh `OutOfMemoryError` | Xem OOMKilled reason, kernel/event history |
| “SOE = bộ nhớ heap đầy” | Là giới hạn stack/call depth, không đồng nhất heap | Kiểm tra recursive frames/cycles, code logic |
| “Tăng `-Xss` là sửa SOE” | Recursion không base case vẫn vô hạn; tăng stack còn tốn native memory | Sửa thuật toán; nếu hợp lý mới tuning stack |
| “`catch (Throwable)` là robust” | Nuốt lỗi VM nghiêm trọng, có thể tiếp tục trạng thái sai | Catch các loại có khả năng phục hồi, surface fatal signal |
| “`finally` chắc chắn chạy trước mọi crash” | `SIGKILL` và fatal abort có thể chặn Java cleanup | Dùng external supervisor/durable logging |
| “Không có `hs_err` thì không phải VM crash” | Reporter có thể không ghi được; OS có thể kill | Xem stderr, location, permission, OS diagnostics |
| “Có `hs_err` là do một Java exception” | Fatal report thuộc VM/native layer, không phải Throwable thường | Phân tích header/problematic frame/native stack |
| “Problematic frame = bug chắc chắn ở thư viện đó” | Memory corruption có thể xảy ra từ trước | Core, symbols, reproducer, native diagnostics |
| “Heap dump thấy ít object nên không có native leak” | Heap dump không theo dõi mọi native allocations | NMT + RSS/cgroup + native profiling |
| “Tự gây OOME ngay trên production để test flags” | Có thể ảnh hưởng cả host/pod và dữ liệu khác | Test có memory/disk/time limits trong sandbox |
| “CrashOnOutOfMemoryError và ExitOnOutOfMemoryError là giống nhau” | Một hướng abort/crash, một hướng exit | Chọn policy có kiểm thử và artifact requirements |

## 16. Quy tắc vận hành an toàn sau lỗi

**Với Java exception có thể phục hồi:** kiểm tra transactional safety, idempotency, retry với exponential backoff/jitter, timeout và circuit breaker theo yêu cầu nghiệp vụ. Không retry mọi `RuntimeException`; một `NullPointerException` do bug logic thường không cải thiện sau retry.

**Với OOME:** cảnh báo khả năng JVM thiếu tài nguyên để logging, tạo thread hoặc response. Ghi bằng chứng từ trước và dùng policy fail-fast/restart có supervisor khi thích hợp. Tránh catch rồi tạo collection lớn, format stack trace không giới hạn hoặc cố nâng tải trong process vừa cạn tài nguyên.

**Với SOE:** sửa logic recursion. Nếu hệ thống nhận input không tin cậy, kiểm soát depth và cycle ở biên; batch job có thể đánh dấu job failed và đưa vào retry queue **sau khi sửa dữ liệu/giới hạn**, không tiếp tục recursion cũ.

**Với fatal VM error:** coi tiến trình không còn đáng tin cậy; ưu tiên khôi phục qua orchestration, bảo toàn logs/core theo policy, tìm root cause bằng reproducer được cô lập. Không thể dựa vào Java exception handler để phục hồi native segmentation fault.

**Với OS kill:** triển khai các budget/cgroup/limit phù hợp, metrics dự phòng, pod restart và readiness/liveness theo nhu cầu; không mong chờ dump Java nếu kernel đã `SIGKILL`.

## 17. Checklist phân loại trong 60 giây đầu của incident

- [ ] Process còn sống hay đã chết? PID/container restart count có thay đổi?
- [ ] Có **Java throwable stack trace**, `hs_err_pid` hay chỉ là exit event?
- [ ] Nếu `OutOfMemoryError`: ghi **nguyên văn detail message**, không lược bỏ phần sau dấu `:`.
- [ ] Nếu `StackOverflowError`: tìm methods lặp, input, cycle và call depth.
- [ ] Nếu fatal VM: ghi signal/exception, problematic frame, JDK build và native library versions.
- [ ] Nếu container exit `137`: kiểm tra `reason=OOMKilled` và kernel/cgroup events, không chỉ exit code.
- [ ] Có GC logs, `.hprof`, JFR, NMT, memory/CPU/thread metrics trước lúc lỗi không?
- [ ] Kiểm tra `-Xmx`/`-Xss`/`MaxMetaspaceSize`/`MaxDirectMemorySize` và container memory/PID limits trên process đích.
- [ ] Đã bảo toàn artifact có timestamp, PID, release, host/container ID và directory đúng?
- [ ] Đã kiểm tra filesystem đủ chỗ/permission cho fatal logs và heap/core dumps?
- [ ] Đã chọn chính sách restart/fail-fast phù hợp thay vì nuốt mọi `Error`?
- [ ] Sau khắc phục, đã đối chiếu error rate, memory trend, GC, RSS, throughput với cùng workload?

## 18. Tài liệu chính thức nên đối chiếu

1. Java SE 21, `Throwable` — khái niệm exception/error, cause và stack trace: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html
2. Java SE 21, `Exception` và `Error` — quy tắc checked/unchecked và lỗi nghiêm trọng: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Exception.html và https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Error.html
3. Java SE 21, `VirtualMachineError` — cha của `OutOfMemoryError` và `StackOverflowError`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/VirtualMachineError.html
4. Java SE 21, `OutOfMemoryError` — Javadoc: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/OutOfMemoryError.html
5. Java SE 21, `StackOverflowError` — Javadoc: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StackOverflowError.html
6. Oracle JDK 21 Troubleshooting Guide, *Troubleshoot Memory Leaks* — OOME detail messages và phân loại heap/native: https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html
7. Oracle JDK 24, *Location of Fatal Error Log* — `hs_err_pid` và ý nghĩa header/problematic frame: https://docs.oracle.com/en/java/javase/24/troubleshoot/location-fatal-error-log.html
8. Oracle JDK 22, *Troubleshoot System Crashes* — native/JNI/JIT/VM crash diagnosis: https://docs.oracle.com/en/java/javase/22/troubleshoot/troubleshoot-system-crashes.html
9. Oracle JDK 21 `java` manual — `-XX:+HeapDumpOnOutOfMemoryError`, `-XX:HeapDumpPath`, `-XX:ErrorFile`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
10. Oracle JDK 21, *Prepare Java for Troubleshooting* — thu core, fatal logs, GC/JFR và diagnostic artifacts: https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html
11. Oracle JDK 21, *Diagnostic Tools* — `jcmd`, heap dump và postmortem options: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html

**Kết luận:** đừng gom mọi sự cố thành “Java crash”. Java exception thường là **lỗi được biểu diễn bằng `Throwable`**; `OutOfMemoryError` là **cạn một loại tài nguyên, cần đọc detail**; `StackOverflowError` là **vượt stack/call depth**; fatal VM error là **đứt gãy ở JVM/native runtime** có thể để lại `hs_err_pid`/core; OS OOM kill lại là **tác động bên ngoài JVM**. Chọn đúng loại trước thì mới biết cần **stack trace, heap dump, GC/NMT, core dump hay container/kernel logs** để tìm nguyên nhân thực sự.
