# Giới hạn tài nguyên ở hệ điều hành và giới hạn của ngắt luồng Java

Một ứng dụng Java có khả năng nạp plugin, chạy script hay thực thi mã mở rộng phải giải quyết hai vấn đề khác nhau: **làm sao đề nghị tác vụ dừng**, và **làm sao bảo đảm mã đang chạy không vượt quá ngân sách tài nguyên**. Chúng không thể thay thế cho nhau.

- `Thread.interrupt()`, `Future.cancel(true)` và các timeout ở mức Java chủ yếu thuộc nhóm **hủy hợp tác** (*cooperative cancellation*). Chúng có thể khiến tác vụ nhận tín hiệu ngắt, nhưng không phải cơ chế cưỡng chế dừng mọi bytecode đang chạy.
- Cgroup, container quota, giới hạn process/job của hệ điều hành và các chính sách cô lập cấp OS mới là nơi đặt **trần CPU, bộ nhớ, số process/thread, file descriptor, dung lượng đĩa hoặc quyền truy cập tài nguyên** theo điều kiện nền tảng hỗ trợ.
- `ProcessBuilder` giúp host khởi động và quản lý vòng đời một tiến trình con; `Process.destroyForcibly()` có thể cưỡng chế kết thúc tiến trình. Tuy nhiên, **quản lý timeout của process không tự thiết lập hạn mức CPU/RAM** và cũng không mặc nhiên dọn mọi tiến trình cháu.

Đối với **ranh giới tin cậy** của cơ chế mở rộng Java, nguyên tắc là: mã đủ tin cậy có thể dùng `interrupt` để đóng tác vụ gọn gàng; mã không tin cậy hoặc có thể không hợp tác cần được đặt trong **ranh giới process/OS độc lập** có quota, quyền tối thiểu và cơ chế thu hồi.

Bài học dùng Java 17+ và một chương trình chạy được để quan sát: một thread hợp tác dừng khi bị ngắt; một task cố ý bỏ qua interrupt vẫn sống dù `Future` báo đã hủy; một tiến trình con bị host kết thúc sau deadline. Các ví dụ cố tình giới hạn thời gian, không chạy vòng lặp vô hạn trong JVM host mà không có đường dọn dẹp.

## 1. Vì sao plugin hay script tạo ra rủi ro tài nguyên?

Giả sử một server nhận request và gọi một plugin qua SPI:

```text
HTTP request
     |
     v
Host Java server
     |
     v
Plugin API / ScriptEngine / dynamically loaded class
     |
     +--> CPU loop
     +--> Cấp phát heap và direct memory
     +--> Tạo thread/process mới
     +--> Mở file/socket
     +--> Gọi native library hoặc I/O vô hạn
```

Ngay cả plugin không có chủ đích xấu cũng có thể vô tình:

1. Lặp vô hạn vì một điều kiện sai.
2. Tạo cấu trúc dữ liệu không có giới hạn.
3. Giữ quá nhiều thread, socket hoặc file descriptor.
4. Gọi API ngoài bị treo.
5. Cố truy cập tài nguyên không thuộc phạm vi công việc.

Nếu plugin chạy **trong cùng JVM** với host, nó dùng chung không gian tiến trình, heap và nhiều tài nguyên process. Một plugin gây `OutOfMemoryError` hoặc làm cạn CPU có thể ảnh hưởng các request không liên quan. Cùng class loader hay tách class loader **không biến plugin thành sandbox**.

Đối với script/plugin do bên ngoài cung cấp, nên đặt câu hỏi về **ranh giới tin cậy** trước khi chọn API timeout. Chỉ thêm `Future.get(2, TimeUnit.SECONDS)` không tạo giới hạn CPU, RAM hoặc quyền hệ điều hành.

## 2. Ba lớp kiểm soát — ba loại bảo đảm khác nhau

| Lớp kiểm soát | Công cụ điển hình | Có thể bảo đảm gì? | Không nên kỳ vọng gì? |
|---|---|---|---|
| **Hợp tác trong Java** | `Thread.interrupt()`, cờ dừng, `Future.cancel(true)`, API interruptible | Tác vụ **được viết đúng** nhận tín hiệu và chủ động thoát, cleanup | Buộc mã cố tình bỏ qua interrupt phải dừng |
| **Quản lý vòng đời process** | `ProcessBuilder`, `Process.waitFor(timeout, unit)`, `destroy()`, `destroyForcibly()` | Host có thể giám sát và chấm dứt **tiến trình con** đang quản lý | Tự áp quota CPU/RAM hay chắc chắn chấm dứt mọi process cháu |
| **Cô lập và quota của OS** | Linux cgroups, namespaces, container/VM, Windows Job Objects, process limits, access policy | Giới hạn/quan sát tài nguyên và quyền trong phạm vi OS/cấu hình được áp dụng | Cứ có một Java thread là OS sẽ riêng biệt giới hạn nó theo request |

Phải phân biệt thêm **wall-clock deadline** (thời gian trôi qua) và **CPU quota** (lượng CPU được tiêu thụ theo chu kỳ đo). Một process bị chờ I/O có thể gần như không dùng CPU mà vẫn vượt deadline. Một process bị bóp CPU quota vẫn có thể sống mãi nếu host không thực thi timeout.

Tương tự, giới hạn heap `-Xmx` chỉ giới hạn phần **Java heap** được JVM quản lý, không giới hạn đầy đủ RSS, metaspace, direct buffers, code cache, native allocations và thread stacks.

## 3. Java `interrupt` thực sự hoạt động thế nào?

### 3.1. Interrupt là tín hiệu, không phải lệnh giết thread

Lời gọi:

```java
worker.interrupt();
```

gửi **yêu cầu ngắt** tới một `Thread`. JVM không được yêu cầu kết thúc thread ngay tại chỗ. Phản ứng phụ thuộc vào trạng thái và mã đang chạy:

- Nếu thread đang thực hiện thao tác **có hỗ trợ interruption** như `Thread.sleep`, `Object.wait`, `Thread.join` hoặc một số phương thức trong `java.util.concurrent`, nó có thể nhận `InterruptedException`.
- Nếu thread đang chạy code tính toán thông thường, interrupt thường chỉ làm cờ interruption của thread được đặt. Mã cần kiểm tra cờ và tự thoát ở thời điểm phù hợp.
- Một số thao tác I/O/channel hoặc đồng bộ có cách phản ứng với interruption riêng, ví dụ đóng channel hoặc ném exception đặc thù. Không nên coi mọi lời gọi I/O đều dừng tức thì khi interrupt.
- Nếu mã bắt `InterruptedException` rồi bỏ qua và tiếp tục vô hạn, `interrupt()` **không cưỡng chế** được nó.
- Nếu đang chờ chiếm monitor của `synchronized`, việc chờ monitor không trở thành interruptible chỉ vì thread bị ngắt.

Ví dụ vòng tính toán **hợp tác**:

```java
while (!Thread.currentThread().isInterrupted()) {
    processOneBoundedChunk();
}
```

Đây là **đoạn minh họa**, `processOneBoundedChunk()` phải do ứng dụng định nghĩa. Điều kiện quan trọng là mỗi vòng có phạm vi công việc hữu hạn, được kiểm tra thường xuyên; nếu một lần gọi bên trong không bao giờ trả, vòng ngoài không có cơ hội đọc cờ.

### 3.2. `isInterrupted()` khác `Thread.interrupted()`

Hai API dễ bị nhầm:

```java
boolean stillSet = Thread.currentThread().isInterrupted();
boolean beforeClearing = Thread.interrupted();
```

- `isInterrupted()` kiểm tra cờ của đối tượng thread, **không xóa** cờ.
- `Thread.interrupted()` là static method, kiểm tra **thread hiện tại** và **xóa cờ** sau khi đọc.

Dùng `Thread.interrupted()` trong điều kiện lặp có thể vô tình “nuốt” tín hiệu nếu phần mã còn phải truyền việc hủy lên tầng trên. Trong vòng tác vụ, thường dùng `isInterrupted()` để kiểm tra mà vẫn giữ tín hiệu.

### 3.3. `InterruptedException` và việc khôi phục cờ

Một số thao tác blocking khi ném `InterruptedException` **xóa interrupt status**. Nếu tầng xử lý không thể `throws InterruptedException` cho caller, cách thường dùng là dọn tài nguyên rồi **đặt lại cờ** để tầng trên biết yêu cầu hủy:

```java
try {
    Thread.sleep(1_000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

Trong một phương thức đã khai báo `throws InterruptedException`, có thể để exception truyền lên sau cleanup thích hợp, không nhất thiết phải tự khôi phục cờ rồi lại ném.

Không nên dùng:

```java
// PHẢN VÍ DỤ: nuốt interrupt và tiếp tục mãi.
try {
    Thread.sleep(1_000);
} catch (InterruptedException ignored) {
    // Tiếp tục chạy bất chấp yêu cầu hủy.
}
```

Bài demo ở phần 7 **cố tình** dùng phản ví dụ này ở một task hữu hạn để chứng minh vì sao không được xem interrupt như cơ chế cưỡng chế.

### 3.4. Tài nguyên vẫn cần cleanup

Nếu một task đã mở file, connection, lock hoặc đăng ký callback, phản hồi interrupt đúng không chỉ là `return`. Tùy nghiệp vụ, có thể dùng `try/finally`, `try-with-resources` và chiến lược rollback/compensation thích hợp:

```java
try {
    doWorkWithResource();
} finally {
    closeOrReleaseResource();
}
```

Đây là **mã ý tưởng**, không phải Java chạy độc lập; `doWorkWithResource` và `closeOrReleaseResource` tượng trưng cho các thao tác nghiệp vụ. Cần tránh gọi cleanup không có deadline hoặc có thể treo vô hạn khi hệ thống đang cố hủy.

## 4. Các API timeout/cancel **không** phải hạn mức thực thi

Một số nhầm lẫn rất phổ biến:

| API | Ý nghĩa thực tế | Giới hạn cần nhớ |
|---|---|---|
| `Future.get(2, SECONDS)` | Luồng **gọi get** chỉ đợi tối đa khoảng thời gian chỉ định | Timeout không tự hủy task đang chạy |
| `Future.cancel(true)` | Cố hủy `Future`, **có thể yêu cầu interrupt** nếu task đã chạy | `isCancelled()==true` không chứng minh code đã thoát |
| `Future.cancel(false)` | Hủy theo trạng thái Future, không yêu cầu interrupt thread đang chạy | Tác vụ đang chạy có thể tiếp tục |
| `ExecutorService.shutdownNow()` | Thử dừng task đang chạy và ngăn task chờ | Thường thực hiện bằng interrupt; **không bảo đảm** mọi task kết thúc |
| `Thread.join(timeout)` | Thread gọi `join` đợi có thời hạn | Thread được đợi không bị kill khi hết giờ |
| `CompletableFuture.orTimeout(...)` | Hoàn tất future theo lỗi timeout nếu chưa có kết quả | Không tự dừng công việc trong thread đang thực thi |
| `CompletableFuture.cancel(true)` | Chuyển trạng thái completion sang canceled | Với `CompletableFuture`, tham số `mayInterruptIfRunning` **không điều khiển việc interrupt tác vụ** như Future của executor |

**Cờ `cancelled` là trạng thái của abstraction Future, không phải phép kiểm tra sống/chết của OS thread.** Nếu plugin cố ý bỏ qua cờ interruption, một future có thể đã bị hủy trong khi thread thực thi vẫn giữ CPU, bộ nhớ hoặc lock.

Không dùng `Thread.stop()` như biện pháp khắc phục. API này không an toàn: việc dừng bất ngờ có thể để object trong trạng thái không nhất quán và phá vỡ những bất biến đồng bộ. Trong các JDK hiện đại, nó còn bị hạn chế hơn; đây không phải cơ chế kill plugin đáng tin cậy.

### `synchronized`, I/O và native code

Một task có thể không phản hồi nhanh với interrupt dù developer đã viết một số chỗ kiểm tra cờ. Chẳng hạn:

- Vòng tính toán xử lý một phần việc rất dài mà không quay về điểm kiểm tra.
- Thread đợi chiếm một monitor `synchronized` của thread khác.
- Một API native/driver cũ không có cơ chế cancellation rõ ràng.
- Một lời gọi mạng/đĩa không được cấu hình timeout hoặc có semantics interrupt khác mong đợi.
- Code giữ một lock ở vị trí khiến cleanup hoặc shutdown không thể tiếp tục.

Nếu cần đáp ứng deadline, hãy ưu tiên **API có timeout riêng** (socket connect/read timeout, HTTP client deadline, database statement timeout, `Lock.lockInterruptibly()`...) bên cạnh interrupt. Nhưng với **mã không tin cậy**, cả hai vẫn phải nằm sau ranh giới thực thi cưỡng chế ở cấp process/OS.

## 5. Vì sao không thể đặt hạn mức CPU/RAM đáng tin cậy cho plugin chỉ bằng một thread?

Nhiều plugin Java được nạp trong cùng JVM. Những thread đó thường chia sẻ:

- Một **Java heap**, trong đó object của plugin và host cùng được cấp phát.
- Metaspace/class metadata, JIT code cache và các vùng native khác.
- File descriptors, sockets, environment, system properties và tài nguyên của tiến trình.
- Các native libraries hoặc singleton/static state liên quan đến class loaders.
- Ngân sách CPU và giới hạn process-level mà OS áp cho **toàn JVM**.

Không có API Java SE 17 chuẩn nào cho phép nói: “Thread plugin A chỉ được cấp phát tối đa 64 MiB heap, nếu vượt thì kill duy nhất thread A và thu hồi an toàn mọi object của nó”. Ngắt thread không thu hồi bytecode đã thực thi, không quay lại mọi side effect và không tự hoàn tác object graph.

`ThreadMXBean` hay các công cụ profiling có thể giúp **đo** CPU time theo thread trong những điều kiện được hỗ trợ, nhưng đo lường không đồng nghĩa OS quota có hiệu lực. Một bộ monitor Java có thể phát hiện dấu hiệu vượt ngân sách và yêu cầu dừng, nhưng vẫn phụ thuộc vào mã thực thi hợp tác.

### `-Xmx` không phải giới hạn tổng memory

Ví dụ:

```bash
java -Xms64m -Xmx192m -jar plugin-runner.jar
```

`-Xmx192m` đặt kích thước tối đa Java heap của JVM đó. **Nó không giới hạn toàn bộ RSS ở 192 MiB** và không giới hạn riêng một script trong tiến trình. JVM còn dùng metaspace, direct buffers, stack, JIT, JNI và memory allocator của OS.

Nếu container/process có hạn mức memory thấp hơn tổng nhu cầu, process có thể bị OS cắt khi vượt quota. Khi đó **không được kỳ vọng luôn bắt được `OutOfMemoryError` và chạy được `finally`/cleanup trong Java**. Tài nguyên của worker cần được thiết kế để OS có thể thu hồi mà host vẫn tồn tại.

## 6. Những giới hạn tài nguyên cần áp tại hệ điều hành

| Loại ngân sách | Nguồn tiêu thụ | Cơ chế kiểm soát theo môi trường | Quan sát quan trọng |
|---|---|---|---|
| **CPU** | Tính toán, JIT, vòng lặp | Cgroup CPU quota, giới hạn container, Windows Job CPU controls | CPU quota giảm throughput; deadline vẫn cần theo dõi riêng |
| **RAM / memory** | Heap, metaspace, direct/native memory, stack | Cgroup memory limit/container memory, Job memory limits | Hạn mức áp cho process/group; `-Xmx` chỉ là một phần |
| **Số process/thread** | Tạo process, thread hoặc subprocess không giới hạn | Cgroup `pids.max`, container `--pids-limit`, Job process controls, RLIMIT theo môi trường | Tạo process phụ cũng phải nằm trong nhóm bị giới hạn |
| **File descriptors / handles** | File, socket, pipe, nhiều file mở | `RLIMIT_NOFILE`, OS/container policy, Windows handle monitoring và hạn chế khác | Tài nguyên không được đóng có thể làm cả worker lỗi |
| **Đĩa / I/O** | Log, file tạm, cache, upload | Filesystem quota, tmpfs size, container storage policy, I/O controller | Read-only filesystem khác với quota dung lượng; cần giới hạn file tạm |
| **Network** | HTTP, kết nối nội bộ, truy cập dữ liệu | Network namespace, firewall/egress policy, service identity | CPU/RAM limit **không** chặn việc đọc dữ liệu qua mạng |
| **Thời gian chạy** | Task treo, sleep, chờ I/O | Deadline trong supervisor + terminate process | Không thể thay bằng CPU quota nếu process đang block |
| **Tốc độ/tần suất** | Hàng loạt task song song | Admission control, queue cap, rate limit | Cần chặn quá nhiều worker trước khi hệ thống cạn tài nguyên |

Từng cơ chế có phạm vi riêng. Ví dụ hạn mức ở mức container áp lên các process nằm **trong container đó**; nếu một plugin có thể gọi sang dịch vụ ngoài hoặc thực thi side effect, tài nguyên và quyền của các hệ thống khác cần kiểm soát riêng.

### Linux: cgroups và namespaces

Trên hệ thống Linux hiện đại, **cgroups** cung cấp các controller cho tài nguyên ở mức nhóm tiến trình, ví dụ:

```text
memory.max   -> trần bộ nhớ cgroup
cpu.max      -> quota CPU theo chu kỳ
pids.max     -> trần số process/task trong cgroup
io.max       -> điều tiết một số loại block I/O
```

Đây là tên giao diện cgroup v2 **minh họa**, không phải các file bạn nên ghi trực tiếp trong host một cách tùy tiện. Việc cấu hình thường nên được giao cho container runtime hoặc service manager có quyền và lifecycle rõ ràng.

**Namespaces** giúp tách các không gian như process IDs, mount/network; **seccomp**, AppArmor/SELinux và quyền OS bổ sung các ràng buộc về hành vi. Cgroup chỉ là quota tài nguyên, **không phải toàn bộ cơ chế bảo mật**.

### Windows: process và Job Objects

Trên Windows, có thể dùng **Job Objects** để nhóm process và áp các giới hạn phù hợp với tính năng hệ điều hành (ví dụ memory/process count hoặc một số chính sách CPU), đồng thời cấu hình cleanup khi job kết thúc. Việc dùng Job Objects thường đòi hỏi native API/orchestration tương ứng; `ProcessBuilder` của Java SE **không tự tạo Job Object có quota**.

Không nên cố thay thế chính sách job bằng một Java thread “canh” riêng: nếu JVM host bị lỗi, thread canh cũng có thể không còn hoạt động.

### Ví dụ cấu hình container mang tính triển khai

Sau khi đã đóng gói một worker **đã kiểm tra** vào image, một kiểu lệnh triển khai Linux với Docker có thể có dạng:

```bash
docker run --rm \
  --cpus=1 \
  --memory=256m \
  --memory-swap=256m \
  --pids-limit=64 \
  --network=none \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --user=65534:65534 \
  my-plugin-runner:17
```

Đây là **mẫu cấu hình minh họa**, không phải lệnh của demo Java và không thể chạy nếu chưa có image `my-plugin-runner:17`, runtime và chính sách quyền tương thích. Giá trị `256m`, `64`, `1 CPU` chỉ là ngân sách **ví dụ**, phải kiểm tra trên workload thực. Một số tùy chọn hoặc mức cưỡng chế phụ thuộc Linux kernel, cgroup mode, runtime và quyền của daemon.

Đọc ý nghĩa:

- `--cpus=1`: hạn chế ngân sách CPU của container.
- `--memory=256m`: đặt trần memory được container runtime áp theo cơ chế nền tảng.
- `--memory-swap=256m`: trong cấu hình hỗ trợ, cố đặt trần tổng memory+swap cùng mức memory; không thể suy ra mọi host đều cưỡng chế swap như nhau.
- `--pids-limit=64`: hạn chế số task/process trong container theo cấu hình runtime.
- `--network=none`, `--read-only`, `--tmpfs`: hạn chế mạng và đường ghi filesystem thông thường, vẫn cần đánh giá mount/host sharing và quyền đặc biệt.
- `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--user=...`: giảm quyền, không thay nhu cầu seccomp/policy và isolation thực tế.

Một container **không tự động là sandbox tuyệt đối**. Với mã có mức độ tin cậy rất thấp, cân nhắc boundary mạnh hơn như microVM/VM, tách host và identity, cùng chính sách egress, secret và dữ liệu đầu vào.

## 7. Ví dụ Java 17: hợp tác, bỏ qua interrupt và deadline của process

Ta viết một chương trình duy nhất `RuntimeBoundaryDemo.java`, **không cần thư viện ngoài**. Nó chạy ba phép thử có kiểm soát:

1. Một thread `sleep` trong vòng lặp, bắt `InterruptedException`, khôi phục cờ và thoát: **cooperative cancellation**.
2. Một task trong `ExecutorService` cố tình nuốt `InterruptedException`. Sau `Future.cancel(true)`, Future báo cancelled nhưng task **vẫn còn sống**. Sau đó host đặt một cờ stop riêng để dọn sạch và kết thúc thử nghiệm.
3. Tạo một **JVM con** bằng `ProcessBuilder`; nếu vượt 300 ms, host dừng process bằng `destroy()` và nếu cần leo thang lên `destroyForcibly()`. Đây là **quản lý deadline tiến trình**, không áp RAM/CPU quota.

Chương trình được thiết kế để **không giữ task cố ý bỏ qua interrupt chạy vô hạn** sau demo. Nó sẽ thu hồi task bằng stop flag và chờ executor kết thúc. Worker con trong chế độ `child` sẽ đợi lâu, nhưng luôn được host xử lý trong nhánh `finally` nếu demo bình thường tiếp tục chạy. Nếu host bị kill đột ngột, cleanup bằng `finally` không phải bảo đảm OS; các hệ thống production cần process group/cgroup/Job Object tương ứng.

### 7.1. Mã nguồn hoàn chỉnh

Tệp `RuntimeBoundaryDemo.java`:

```java
import java.nio.file.Path;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class RuntimeBoundaryDemo {
    private static void interruptibleWorker() throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        Thread worker = new Thread(() -> {
            started.countDown();
            try {
                for (;;) {
                    Thread.sleep(1_000);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "cooperative");

        worker.start();
        started.await();
        worker.interrupt();
        worker.join(2_000);
        if (worker.isAlive()) {
            throw new IllegalStateException("Cooperative worker did not stop");
        }
        System.out.println("Cooperative interrupt stopped thread: true");
    }

    private static void ignoringInterruptWorker() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        AtomicBoolean stop = new AtomicBoolean(false);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);

        try {
            Future<?> future = executor.submit(() -> {
                started.countDown();
                try {
                    while (!stop.get()) {
                        try {
                            Thread.sleep(100);
                        } catch (InterruptedException ignored) {
                            // DEMO ONLY: intentionally ignore cancellation.
                        }
                    }
                } finally {
                    finished.countDown();
                }
            });

            started.await();
            future.cancel(true);
            System.out.println("Future cancelled: " + future.isCancelled());
            System.out.println("Ignored interrupt task still alive: "
                    + (finished.getCount() != 0));

            stop.set(true);
            executor.shutdownNow();
            if (!executor.awaitTermination(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Demo executor did not stop");
            }
            System.out.println("Explicit stop flag ended task: "
                    + (finished.getCount() == 0));
        } finally {
            stop.set(true);
            executor.shutdownNow();
        }
    }

    private static void timedChildProcess() throws Exception {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win");
        Path javaExecutable = Path.of(System.getProperty("java.home"),
                "bin", windows ? "java.exe" : "java");

        Process process = new ProcessBuilder(
                javaExecutable.toString(),
                "-cp", System.getProperty("java.class.path"),
                RuntimeBoundaryDemo.class.getName(), "child")
                .redirectOutput(ProcessBuilder.Redirect.DISCARD)
                .redirectError(ProcessBuilder.Redirect.DISCARD)
                .start();

        try {
            boolean timedOut = !process.waitFor(300, TimeUnit.MILLISECONDS);
            if (!timedOut) {
                throw new IllegalStateException("Child ended unexpectedly");
            }
            System.out.println("Child process timed out: " + timedOut);

            process.destroy();
            if (!process.waitFor(2, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                if (!process.waitFor(3, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Child still alive");
                }
            }
            System.out.println("Child process stopped: " + !process.isAlive());
        } finally {
            if (process.isAlive()) {
                process.destroyForcibly();
                process.waitFor(3, TimeUnit.SECONDS);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("child")) {
            for (;;) {
                Thread.sleep(60_000);
            }
        }
        interruptibleWorker();
        ignoringInterruptWorker();
        timedChildProcess();
    }
}
```

### 7.2. Biên dịch và chạy

Yêu cầu **JDK 17 trở lên**; trong thư mục có `RuntimeBoundaryDemo.java`, chạy:

```bash
javac --release 17 -encoding UTF-8 RuntimeBoundaryDemo.java
java RuntimeBoundaryDemo
```

Hai lệnh này dùng được trên Linux, macOS và Windows PowerShell khi `java`/`javac` nằm trong `PATH`. Khi chạy, Java tạo một JVM con bằng executable trong `java.home`; do đó môi trường cần cho phép khởi động process con.

### 7.3. Stdout chuẩn

Khi môi trường cho phép khởi động và kết thúc process bình thường:

```text
Cooperative interrupt stopped thread: true
Future cancelled: true
Ignored interrupt task still alive: true
Explicit stop flag ended task: true
Child process timed out: true
Child process stopped: true
```

Chương trình cố ý in giá trị boolean thay vì PID/exit code, vì PID, timing chi tiết, exit code và hình thức tín hiệu hủy phụ thuộc hệ điều hành.

Nếu process con không được phép spawn, hoặc host bị đình chỉ/bị can thiệp khiến `waitFor` trả kết quả khác, chương trình có thể ném exception; các dòng trên là kết quả của **đường chạy thành công**, không phải cam kết mọi máy đều luôn chạy được. Môi trường chạy thật phải có khả năng tạo, theo dõi và chấm dứt JVM con.

## 8. Diễn giải thí nghiệm: vì sao kết quả như vậy?

### 8.1. Thread hợp tác

Đoạn `interruptibleWorker()` tạo thread rồi chờ `CountDownLatch` xác nhận thread bắt đầu. Nó gửi `interrupt()` và chờ tối đa hai giây bằng `join(2_000)`. Nếu thread vẫn sống thì báo lỗi.

`Thread.sleep` phản ứng với interrupt bằng `InterruptedException`. Worker không tiếp tục vòng lặp nữa; nó khôi phục cờ và đi tới cuối lambda để kết thúc. **Ở đây thread dừng vì mã đã chủ động thoát**, không phải JVM tự kill thread.

Đối với một worker thực tế, hãy đưa logic cleanup vào `finally` và cho interruption propagage theo thiết kế API.

### 8.2. `Future` đã hủy nhưng task vẫn đang chạy

Task thứ hai có điều kiện `while (!stop.get())`. Nó cố ý bắt `InterruptedException` và **không thoát**, nên `future.cancel(true)` không có quyền ép vòng lặp kết thúc.

Sau `future.cancel(true)`, chương trình quan sát:

```text
Future cancelled: true
Ignored interrupt task still alive: true
```

Trong ví dụ, `CountDownLatch finished` chỉ được giảm khi task **thật sự kết thúc**. Tính toán `finished.getCount() != 0` khác với `future.isCancelled()`. Đây là cách tránh đánh đồng trạng thái Future với sự sống của công việc bên dưới.

Khi host đặt `stop.set(true)` và gọi `shutdownNow()`, task có đường thoát rõ ràng; `awaitTermination(...)` cho phép xác minh executor đã kết thúc trong ngân sách. Trong mã thực tế, `shutdownNow` vẫn chỉ cố interrupt nên không thể thay cờ stop đối với worker cố ý bỏ qua interrupt.

**Không lấy phản ví dụ này làm mẫu viết task production.** Task tốt phải tôn trọng interrupt, exit path và cleanup; phản ví dụ chỉ cho thấy giới hạn của cancellation trong Java.

### 8.3. Tiến trình khác là đơn vị có thể chấm dứt độc lập

`timedChildProcess()` khởi chạy cùng chương trình ở mode `"child"` trong **một JVM riêng**. Worker con chỉ đợi trong vòng lặp `Thread.sleep(...)` dài; nó không nhận `Thread.interrupt()` từ JVM host.

Host theo dõi:

```java
boolean finished = process.waitFor(300, TimeUnit.MILLISECONDS);
```

Trong mã đầy đủ, logic tương đương được viết thành `timedOut = !process.waitFor(...)`. Timeout chỉ cho biết **host đã hết thời gian chờ**; bản thân `waitFor(timeout)` không hủy tiến trình.

Host sau đó **chủ động** gọi `destroy()` và, nếu tiến trình không kết thúc kịp, leo thang `destroyForcibly()` rồi `waitFor(...)` để xác nhận tiến trình đã chấm dứt. Lựa chọn tín hiệu/chi tiết terminate phụ thuộc hệ điều hành. Mã có `finally` để cố dọn tiến trình nếu phát sinh lỗi khi đang xử lý.

**Giới hạn ví dụ:** chỉ có một process con và process đó không tạo cháu. Với process tự tạo subprocess, `Process.destroyForcibly()` trên process cha không bảo đảm toàn bộ process tree đều bị chấm dứt. Trong hệ thống thật, nên đặt nhóm process của plugin dưới OS cgroup/Job Object/container phù hợp và dọn **cả nhóm** khi hết hạn.

## 9. Tách deadline với quota trong thiết kế supervisor

Một supervisor của plugin nên có hai lớp kiểm soát độc lập:

```text
                       Host (trusted)
                             |
                    Submit plugin work
                             |
                             v
                  Admission / rate limit
                             |
                             v
                    Create worker process
                   (OS quota & least privilege)
                             |
                 +-----------+-----------+
                 |                       |
             Monitor wall time      Monitor health
                 |                       |
            Deadline over?        Memory/CPU/PIDs signals
                 |                       |
                 +-----------+-----------+
                             |
                Graceful stop if possible
                             |
                    Wait bounded grace
                             |
                  Terminate worker group
                             |
                   Reap/verify cleanup
                             |
                Return timeout / failure
```

Các giới hạn cần được quyết định theo workload:

- **Wall time:** ví dụ 2 giây cho một phép tính ngắn, bao gồm thời gian xếp hàng hay chỉ thời gian thực thi phải được định nghĩa rõ.
- **CPU budget:** có thể giới hạn bằng quota CPU OS, nhưng quota không tự hủy process khi vượt một lượng tổng CPU time trừ khi hệ thống giám sát còn thiết kế cơ chế hành động.
- **Memory:** chọn cgroup/job limit đủ cho cả JVM (heap + native + thread stacks), phối hợp `-Xmx` với tổng memory. Nếu tổng memory quá sát `-Xmx`, worker có thể bị OS kill trước khi JVM tự báo OOM.
- **PIDs/threads:** tính cả native threads/JVM worker threads, subprocess và số worker trong cùng nhóm.
- **I/O/temporary files:** dùng thư mục tạm riêng, quota storage và hạn chế mount; tránh để plugin ghi bừa vào thư mục host.
- **Network:** mặc định từ chối egress không cần thiết; nếu cho gọi API ngoài, đặt timeout, allowlist và secret scope.
- **Cleanup:** khi timeout xảy ra, đừng để request mới tái sử dụng worker có trạng thái không rõ. Có thể chọn bỏ cả process và tạo worker mới.

OS resource limit **chỉ áp nếu worker thực sự được đưa vào phạm vi chịu limit**. Chạy `java -jar plugin.jar` bằng `ProcessBuilder` mà không đặt vào cgroup/Job Object phù hợp **không** tạo quota tự động.

### Vì sao chỉ dùng thread pool trong host không đủ?

Một `ExecutorService` giúp giới hạn **số task được xếp/chạy** theo số thread và queue capacity, nhưng **không giới hạn memory của từng task** và **không cưỡng chế dừng mã không hợp tác**. Một task treo có thể giữ thread pool slot, connection hoặc lock; đến khi pool cạn, các request khác cũng bị ảnh hưởng.

Ngay cả khi tăng số thread để bù, hành động đó có thể làm tình hình tệ hơn do tài nguyên process-level bị dùng nhiều hơn. Cần admission control, queue bounded và ranh giới worker process cho mã không tin cậy.

## 10. Thiết kế ranh giới tin cậy theo mức độ kiểm soát mã

| Loại mã chạy | Cách tổ chức thường phù hợp | Cảnh báo |
|---|---|---|
| Business logic nội bộ đã review, có test | Cùng JVM, `ExecutorService`, interrupt/timeout ở API liên quan | Bug vẫn có thể gây OOM hoặc treo process |
| Plugin do đối tác tin cậy nhưng có dependency phức tạp | Cân nhắc process riêng để tách lỗi và dependency; dùng SPI/protocol rõ | Tách class loader một mình không bảo vệ CPU/RAM |
| Script theo user nội bộ với quyền hạn nhất định | Tùy rủi ro, process worker riêng, restricted API, quota, deadline | `ScriptEngine`/Bindings không phải sandbox |
| Java/script không tin cậy từ internet | Process/container/VM được cô lập mạnh, least privilege, no secrets, OS quota, network policy | Không chạy trực tiếp trong JVM host chỉ dựa vào `Thread.interrupt()` |

Mục tiêu là tách **fault containment** khỏi **API extensibility**. SPI/ModuleLayer/ClassLoader giải quyết bài toán kết nối và nạp mã; container/OS policy giải quyết an toàn tài nguyên và quyền. Chúng có thể được phối hợp nhưng không thể thay thế cho nhau.

### Một ranh giới process cần có protocol

Khi plugin chạy khác JVM, host không thể đơn giản truyền một object Java từ class loader của host và gọi trực tiếp method trong process kia. Cần một giao thức giao tiếp có hợp đồng như:

```text
Host Java  --request ID + JSON/Protobuf-->  Worker Java
Host Java  <--status + result/error-------  Worker Java
```

Tùy độ phức tạp có thể dùng stdin/stdout đóng khung dữ liệu, local socket, gRPC hoặc message queue. Giao thức nên có version, giới hạn size, deadline, cancellation request, quyền truy cập và chính sách idempotency.

Nếu plugin thực hiện side effect như ghi database hoặc gửi email, **kill process không tự rollback giao dịch ngoài**. Khi timeout, host có thể không biết thao tác đã thành công hay chưa; nên thiết kế idempotency key, trạng thái request và cơ chế hòa giải thay vì retry vô điều kiện.

## 11. Vòng đời đúng khi worker hết thời hạn

Một quy trình thực tế:

1. **Tạo nhóm tài nguyên**: container/cgroup/Job Object/worker process với quyền tối thiểu và quota.
2. **Đăng ký deadline**: bắt đầu đếm từ thời điểm được định nghĩa (nhận request, bắt đầu thực thi hay sau warm-up).
3. **Gửi hủy hợp tác**: nếu protocol hỗ trợ, yêu cầu worker dừng; cho một khoảng grace hữu hạn.
4. **Theo dõi liveness**: đừng chỉ nhìn `Future.isCancelled()` hay timeout từ phía client; kiểm tra process/group còn sống.
5. **Cưỡng chế kết thúc**: terminate/kill đúng **nhóm worker** qua cơ chế OS phù hợp khi hết grace.
6. **Thu dọn**: đóng pipe, handle, file tạm, rút worker khỏi registry, hoàn trả quota/slot; tránh zombie/leak.
7. **Công bố trạng thái**: timeout, bị giới hạn tài nguyên, lỗi child process hoặc bị hủy bởi client là những nguyên nhân khác nhau.
8. **Phòng retry sai**: giữ request ID và semantics idempotency khi kết quả không chắc chắn.

Một `finally` trong host là cần thiết nhưng không đủ khi chính host bị crash. Nếu cần bảo đảm cleanup ngay cả khi supervisor chết, hãy dùng lifecycle control của OS/container orchestrator có chính sách phù hợp.

### Cần kiểm tra cả process tree

Java cung cấp `ProcessHandle` và `ProcessHandle.descendants()` để **quan sát** những process con/cháu vào một thời điểm nhất định, nhưng liệt kê descendants chỉ là snapshot: cây process có thể đổi trong lúc dọn. Không thể mặc định `destroyForcibly()` một PID bảo đảm tất cả descendants đều chết.

Nếu yêu cầu cleanup cưỡng chế đáng tin, nên tổ chức worker trong **process group/cgroup/container/Job Object** mà OS kiểm soát, dùng thao tác dừng cả nhóm theo nền tảng. Đừng để worker tự thoát khỏi nhóm hay tạo process có quyền cao hơn nếu policy không cho phép.

## 12. Các loại lỗi và tín hiệu giám sát nên phân biệt

| Sự kiện | Triệu chứng | Hành động gợi ý |
|---|---|---|
| Thread hợp tác nhận interrupt | Task thoát qua `InterruptedException` hoặc cờ dừng | Cleanup, trả trạng thái canceled |
| Future timeout | Thread client dừng chờ; task có thể chưa dừng | Quyết định cancel và xác nhận task hoàn tất |
| Future cancelled nhưng thread tiếp tục | `isCancelled=true` nhưng worker vẫn chạy | Không xem Future status là kill; với mã không tin cậy dùng process boundary |
| Process vượt deadline | `waitFor(timeout)` trả `false` | Gửi terminate, chờ grace, cưỡng chế kill và xác minh |
| Memory quota bị vượt | Worker có thể bị OS/container kill | Ghi nhận tín hiệu OOM từ orchestrator/cgroup, không giả định Java cleanup đã chạy |
| Hết CPU quota | Worker bị throttling hoặc chậm đi | Theo dõi throttling, deadline và sizing |
| Hết PIDs/threads | Tạo thread/process mới thất bại | Giới hạn concurrency, xử lý lỗi tài nguyên, điều chỉnh ngân sách |
| File descriptor quá nhiều | `Too many open files` hoặc I/O thất bại | Theo dõi leaks, cấu hình limit và cleanup |
| Mã worker gọi mạng trái phép | Truy cập bị chặn theo policy | Xác minh network namespace/firewall và identity; audit |
| Worker chết giữa thao tác có side effect | Host không chắc operation đã commit chưa | Truy vấn/truy nguyên trạng thái, idempotency, reconciliation |

Đừng hard-code một exit code như `"137"` là dấu hiệu OOM duy nhất. Các platform/container runtime có thể báo trạng thái kill theo nhiều cách; hãy đọc **trạng thái orchestrator, event của cgroup, log và thông tin process** cùng nhau.

Tương tự, việc không có exception trong log Java **không chứng minh** không có lỗi: OS kill có thể chấm dứt process mà không cho JVM chạy shutdown hook hay `finally`.

## 13. Các lỗi thiết kế thường gặp

| Nhận định sai | Vì sao sai? | Cách làm đúng hơn |
|---|---|---|
| “`Thread.interrupt()` giết thread bất kỳ” | Interrupt là tín hiệu hợp tác | Thiết kế điểm kiểm tra/hủy và ranh giới process cho mã không hợp tác |
| “`Future.cancel(true)` trả true tức là task dừng” | Future status không phản ánh chắc chắn trạng thái thread | Theo dõi task kết thúc, resource và process liveness |
| “`get(timeout)` tự hủy việc đang chạy” | Nó chỉ giới hạn thời gian caller chờ | Gọi cancel và thực hiện shutdown có xác nhận |
| “`shutdownNow()` có thể kill mọi task” | Nó chỉ cố interrupt | Giới hạn task hợp tác, hoặc dùng OS process termination |
| “`Thread.stop()` là phương án cuối an toàn” | Có thể phá bất biến và bỏ cleanup | Không dùng; thiết kế cooperative cancellation/process isolation |
| “`-Xmx` là trần tổng memory” | Còn native, stacks, metaspace, direct buffers | Đặt memory limit ở OS, sizing heap trong ngân sách ấy |
| “Tách class loader nghĩa là tách quyền, CPU và heap” | Các loader vẫn ở chung process | Dùng OS/container/VM boundary với least privilege |
| “`ProcessBuilder` tự tạo cgroup/quota” | Process mới chưa tự có hạn mức riêng | Supervisor/orchestrator phải gắn worker vào quota thích hợp |
| “Kill PID cha sẽ dọn mọi process cháu” | Descendants có thể tiếp tục sống | Quản lý cả worker group bằng OS |
| “Container có memory limit là đủ an toàn” | Vẫn còn network, filesystem, privileges, syscall | Phối hợp namespace, seccomp/MAC, quyền tối thiểu, egress policy |
| “Sau timeout có thể retry mọi request” | Thao tác bên ngoài có thể đã commit | Định nghĩa idempotency và trạng thái không chắc chắn |
| “Nếu có interrupt check thì không cần timeout I/O” | Gọi API có thể không trả về để check cờ | Cấu hình timeout cấp API và deadline ngoài |
| “Đóng thread đồng nghĩa thu hồi toàn bộ memory” | Object có thể còn được tham chiếu; native resource có vòng đời riêng | Quản lý resource/lifetime, hoặc hủy process worker |

## 14. Kiểm thử cần thực hiện trong môi trường an toàn

Nên dựng một **worker thử nghiệm được cách ly và có quota thấp** rồi kiểm tra các trường hợp:

1. **Tác vụ hợp tác:** task `sleep`/queue wait bị interrupt, thoát sạch và đóng resource; thread không còn sống sau deadline.
2. **Tác vụ bỏ qua interrupt:** Future đã canceled nhưng task vẫn chạy; supervisor vẫn có thể kết thúc worker process có kiểm soát.
3. **Vòng CPU bận:** workload thử nghiệm có thời lượng bounded, quan sát CPU throttling và deadline, **không** chạy vòng vô hạn chưa có process quota.
4. **Bộ nhớ vượt ngân sách:** chỉ thử trong môi trường có memory limit và cơ chế thu hồi được xác nhận; ghi nhận worker bị OS kill hay báo OOM theo nền tảng.
5. **Nhiều thread/process:** dùng workload bounded để xác minh PID/thread quota và admission control; không chạy chương trình tạo tiến trình vô hạn.
6. **I/O chậm:** kiểm tra read/connect timeout, cleanup socket và xử lý request bị bỏ dở.
7. **Worker spawn subprocess:** xác minh việc kết thúc worker có dọn cả nhóm theo OS hay không.
8. **Host supervisor restart/crash:** kiểm tra worker mồ côi có bị orchestrator/Job Object/cgroup quản lý và thu hồi không.
9. **Side effect khi timeout:** chứng minh retry với idempotency key không ghi trùng.
10. **Tenant khác cùng lúc:** một plugin bị kill/oom không làm các request của tenant khác mất tài nguyên hoặc lộ dữ liệu nếu đúng isolation.

Mọi thử nghiệm giới hạn tài nguyên nên diễn ra trên máy/thùng thử có quyền phù hợp; tránh dùng môi trường production chung hoặc cố gây quá tải host để “xem limit có hoạt động” khi chưa có biện pháp cách ly.

## 15. Checklist triển khai ranh giới tin cậy cho Java runtime extensibility

Trước khi cho phép plugin/script chạy:

- **Trust:** ai cung cấp mã, có quyền truy cập secrets/network/host filesystem nào?
- **Boundary:** chạy cùng JVM, classloader riêng, process riêng, container hay VM? Lý do chọn đủ mạnh?
- **Quota:** CPU, RAM, PIDs, disk/tmpfs, FD/handles, network, số request đồng thời đã được kiểm soát ở đúng scope?
- **Timeout:** deadline tính từ đâu, grace period bao lâu, khi hết grace ai kill worker group?
- **Concurrency:** queue và worker count có bounded; việc tăng worker không vượt tổng ngân sách host?
- **Cancellation:** task có kiểm tra interrupt, dọn resource, truyền signal hủy qua protocol khi có thể?
- **Process cleanup:** biết process/subprocess nào thuộc worker, có xác minh sau terminate không?
- **Heap sizing:** `-Xmx` có được chọn dưới OS memory limit, chừa chỗ cho native memory không?
- **Isolation:** có least privilege, seccomp/AppArmor/SELinux/Job policy theo môi trường, cấm mount/egress không cần thiết?
- **Recovery:** nếu process chết, hệ thống có phân biệt timeout, crash, OOM, manual cancellation, và tránh retry side effect mù quáng?
- **Observability:** theo dõi deadline, CPU throttling, memory high/OOM, task count và trạng thái process với request ID không nhạy cảm?
- **Test:** đã thử code hợp tác, bỏ qua interrupt và lỗi cleanup ở môi trường cách ly chưa?

## 16. Bài tập củng cố

1. **Hiểu interrupt:** trong demo, thay `catch (InterruptedException ignored)` của task thứ hai bằng `Thread.currentThread().interrupt(); return;` và xem `finished` thay đổi thế nào. Vì sao khi đó `Future.cancel(true)` có thể khiến task thoát đúng?
2. **Hiểu Future:** gọi `future.cancel(false)` trên một task đã chạy và quan sát vì sao trạng thái canceled không đồng nghĩa đã có yêu cầu interrupt tới worker.
3. **Hiểu timeout:** bỏ lệnh `process.destroy()` và `destroyForcibly()` trong một **bản thử nghiệm có supervisor bên ngoài**. Dự đoán `waitFor(300ms)` có tự dừng child không; tuyệt đối không để worker treo lại sau thử nghiệm.
4. **Ước lượng memory:** một JVM có `-Xmx=192m`, metaspace, direct buffers, thread stacks và native libraries. Giải thích vì sao container `--memory=192m` có thể không đủ.
5. **Chọn giới hạn OS:** cho một worker không cần network, chỉ nhận JSON và trả JSON, đề xuất quyền file/network và memory/CPU/PIDs limit.
6. **Quản lý process tree:** giả sử plugin gọi một subprocess. So sánh kill PID cha với kill cả worker group bằng cgroup/Job Object; cách nào phù hợp với yêu cầu cleanup?
7. **Phân biệt trách nhiệm:** đánh dấu mỗi mục thuộc Java cooperative, supervisor deadline hay OS quota: `Thread.interrupt`, `Future.get(timeout)`, `Process.destroyForcibly`, cgroup `memory.max`, Windows Job Objects, network namespace.
8. **Thiết kế giao thức:** bổ sung deadline, request ID, trạng thái `COMPLETED/TIMED_OUT/FAILED/CANCELLED` và idempotency key vào protocol host↔worker.

**Kết luận:** `Thread.interrupt()` là **cơ chế yêu cầu hợp tác**; các Future timeout/cancel không phải nút kill thread; `ProcessBuilder` là **cơ chế quản lý tiến trình**, không tự áp tài nguyên; và **OS quotas cùng process isolation** mới là nền tảng của ranh giới tài nguyên đáng tin cậy khi chạy plugin hoặc script không tin cậy. Đừng giao nhiệm vụ bảo vệ host khỏi mã không hợp tác cho một interrupt flag trong chính JVM đang bị đe dọa.