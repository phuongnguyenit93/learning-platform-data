# Các luồng của ứng dụng và các luồng nội bộ của JVM

Trong cùng một tiến trình Java, bạn có thể thấy `main`, `http-worker-1`, `pool-1-thread-1`, `Reference Handler`, `GC Thread#0` hoặc `C2 CompilerThread0`. Chúng đều liên quan đến hoạt động của chương trình, nhưng **không có cùng chủ sở hữu, nhiệm vụ hay vòng đời**. Phân biệt đúng các luồng này giúp giải thích vì sao JVM vẫn sống sau khi `main` kết thúc, vì sao bộ thu gom rác cần luồng riêng, và vì sao không nên đếm thread để kết luận mọi thread đều do ứng dụng tạo.

Bài học thuộc chủ đề **Vòng đời JVM**, tập trung vào: (1) luồng chạy công việc ứng dụng, (2) luồng hỗ trợ runtime/JVM, (3) daemon và điều kiện kết thúc tiến trình, (4) sự phối hợp giữa các luồng, (5) quan sát và chẩn đoán thực tế.

**Phạm vi triển khai:** khái niệm luồng/daemon dựa trên Java SE; ví dụ về GC workers, compiler threads, VM thread, safepoint và lệnh `jcmd` chủ yếu mô tả **HotSpot/OpenJDK trên JDK 17+**. Một số chi tiết, tên thread và số lượng thread phụ thuộc phiên bản, hệ điều hành, GC và tùy chọn JVM. Virtual thread của Java 21+ được giải thích riêng để tránh nhầm với luồng nền nội bộ.

## 1. Một JVM, nhiều luồng đang làm những việc khác nhau

Một tiến trình Java có thể đồng thời có:

- **Luồng chạy mã ứng dụng:** `main`, thread do `new Thread(...)` tạo, luồng pool `ExecutorService`, worker của web server hoặc thư viện. Chúng thực thi nhiệm vụ nghiệp vụ, có thể là **platform thread** hoặc (từ Java 21) **virtual thread**.
- **Luồng dịch vụ Java runtime / thư viện nền tảng:** ví dụ `Reference Handler` và một số cleaner/scheduler thread. Chúng có thể được biểu diễn bằng `java.lang.Thread`, thường là daemon, nhưng không phải tác vụ nghiệp vụ do bạn tự viết.
- **Luồng native nội bộ của VM:** ví dụ các GC worker, compiler worker và một số thread điều phối VM của HotSpot. Một số **không tương ứng với đối tượng `java.lang.Thread` bình thường**; danh sách `Thread.getAllStackTraces()` vì vậy không phải danh mục tuyệt đối mọi native thread của tiến trình.
- **Luồng OS từ thư viện native/JNI hoặc thành phần khác:** có thể tồn tại ngoài mô hình quản lý `java.lang.Thread` thông thường.

Đây là **phân nhóm theo trách nhiệm**, không phải bốn kiểu bắt buộc trong Java API. “Luồng của ứng dụng” và “luồng nội bộ” mô tả **ai dùng nó để làm gì**; “daemon/non-daemon”, “platform/virtual”, “Java-level/native VM” là **các trục phân loại khác nhau**.

```text
Một tiến trình JVM/HotSpot
│
├── Công việc ứng dụng
│   ├── main (platform thread)
│   ├── worker do ứng dụng tạo (platform thread)
│   ├── request/executor workers
│   └── virtual threads của ứng dụng (Java 21+)
│
├── Dịch vụ runtime nhìn thấy ở mức Java (tùy bản JDK)
│   ├── Reference Handler
│   └── Cleaner / dịch vụ nền khác
│
└── Hoạt động nội bộ VM (tùy HotSpot/cấu hình)
    ├── GC workers / concurrent GC threads
    ├── JIT compiler threads
    ├── VM / service / watcher / sampling threads
    └── thread phụ trợ khác
```

Một số hệ thống như HTTP server hoặc thư viện logging tự tạo worker nền. Dù tên nghe như “internal”, chúng vẫn là **thread phục vụ thành phần ứng dụng/thư viện**, không mặc nhiên là GC hoặc compiler thread của JVM.

## 2. Luồng ứng dụng: nơi chương trình thực hiện công việc

### 2.1. `main` là điểm vào, không phải luồng duy nhất

Với chương trình thông thường chạy bằng `java Main`, Java launcher gọi `public static void main(String[] args)` trong một thread có tên thường là `main` và thông thường **không phải daemon**.

`main` có thể tạo thêm thread, giao task cho thread pool hoặc gọi thư viện tự tạo thread. Những luồng ấy có thể tiếp tục chạy sau khi phương thức `main` trả về. Vì vậy **“hết phương thức main” không đồng nghĩa “JVM dừng”**.

Platform thread trên HotSpot thông thường được hỗ trợ bởi một luồng hệ điều hành, nên việc tạo quá nhiều thread đồng thời làm tăng chi phí stack/native resources và scheduling. Đây là quan hệ thực thi phổ biến, không phải lý do để suy ra **mọi** Java thread phải có một OS thread riêng (virtual thread là ngoại lệ rõ ràng từ Java 21).

### 2.2. Tạo và hoàn tất một platform thread

```java
Thread worker = new Thread(() -> {
    // Công việc ứng dụng thực hiện trên thread riêng.
    doBusinessWork();
}, "application-worker");

worker.start(); // Yêu cầu bắt đầu thực thi đồng thời.
worker.join();  // Thread hiện tại đợi worker kết thúc.
```

Đoạn này là **minh họa**, vì `doBusinessWork()` là tên đại diện chưa được định nghĩa. Chương trình chạy đầy đủ được đưa ở phần 6.

- `new Thread(...)` tạo đối tượng thread ở trạng thái `NEW`; chưa thực sự bắt đầu tác vụ.
- `start()` yêu cầu JVM lên lịch thực thi `run()` trong luồng mới; **không đảm bảo** luồng mới chạy ngay trước câu lệnh tiếp theo của bên gọi.
- `join()` giúp thread đang gọi **đợi** thread đích chấm dứt; `join()` không “tự hủy” task trước hạn. `join()` có thể bị gián đoạn bằng `InterruptedException`.
- Gọi trực tiếp `worker.run()` chỉ gọi phương thức như thông thường trên **thread hiện tại**, không sinh đường thực thi song song.
- Không được gọi `start()` lần thứ hai trên cùng một đối tượng `Thread`; sẽ gặp `IllegalThreadStateException`.

Sử dụng `ExecutorService`, structured concurrency (khi khả dụng) hoặc công cụ cấp cao giúp quản lý số task và vòng đời tốt hơn so với tạo thread không giới hạn. `ExecutorService` là cơ chế dùng thread, **không phải loại internal GC thread**.

### 2.3. Trạng thái luồng ở mức Java

`Thread.State` có sáu giá trị:

| Trạng thái | Ý nghĩa ở mức Java |
| --- | --- |
| `NEW` | Đối tượng đã tạo, `start()` chưa gọi |
| `RUNNABLE` | Đang thực thi hoặc sẵn sàng thực thi theo mô hình JVM; không đảm bảo đang chiếm CPU |
| `BLOCKED` | Chờ giành monitor lock để vào `synchronized` |
| `WAITING` | Chờ không có thời hạn tường minh qua một thao tác như `Object.wait()` hoặc `Thread.join()` |
| `TIMED_WAITING` | Chờ có thời hạn như `Thread.sleep(...)`, timed `wait/join` |
| `TERMINATED` | Đã kết thúc `run()` |

Đây là **trạng thái quan sát tại một thời điểm**, có thể đổi ngay khi bạn kiểm tra. Không đánh đồng `RUNNABLE` của Java với trạng thái “running trên CPU” của scheduler OS. Và `BLOCKED` có nghĩa cụ thể là **chờ monitor lock**, không phải cách gọi chung cho mọi I/O chậm.

## 3. Daemon/non-daemon và điều kiện JVM kết thúc

### 3.1. Daemon là một thuộc tính vòng đời, không phải nhãn “JVM nội bộ”

Với **platform thread**:

- **Non-daemon:** thường là thread thực hiện công việc ứng dụng mà tiến trình cần đợi hoàn thành. Chừng nào còn non-daemon thread đang sống, JVM thông thường tiếp tục sống.
- **Daemon:** thường làm việc phụ trợ. Daemon thread **không tự mình ngăn trình tự JVM shutdown bắt đầu** khi mọi thread non-daemon đã kết thúc.
- Từ Java 17, khi tạo một `Thread` theo constructor thông thường, trạng thái daemon ban đầu được **kế thừa từ thread tạo nó**, trừ khi được thay đổi trước `start()`. Gọi `setDaemon(true/false)` **trước khi khởi động**; đổi khi thread đang chạy gây `IllegalThreadStateException`.

**Quy tắc quan trọng:** thread do ứng dụng tạo rồi gọi `setDaemon(true)` **vẫn là thread ứng dụng**, chỉ mang thuộc tính daemon. Ngược lại, thread hỗ trợ JVM có thể không có đối tượng `Thread` công khai để ứng dụng đọc `isDaemon()`; không nên áp dụng quy tắc daemon của `java.lang.Thread` để mô tả mọi native thread nội bộ.

### 3.2. Vòng đời quy ước khi khởi động từ launcher

```text
JVM khởi động
   │
   ├─► Dịch vụ cần thiết của VM được tạo theo nhu cầu
   │
   └─► Luồng main thực thi main()
             │
             ├─► tạo app-worker-A (non-daemon)
             ├─► tạo app-monitor (daemon)
             └─► main() trả về
                      │
                      ├─ app-worker-A còn sống?
                      │     ├─ Có → tiến trình tiếp tục chạy
                      │     └─ Không → có thể bắt đầu shutdown
                      └─ app-monitor còn chạy cũng không tự giữ tiến trình
```

Đối với Java app khởi chạy thông thường, nếu tất cả các **non-daemon threads đã bắt đầu** đều kết thúc thì trình tự shutdown có thể bắt đầu và daemon threads còn lại không được bảo đảm hoàn tất công việc. Runtime còn có **shutdown hooks** và những cách kết thúc tường minh như `System.exit(...)`; hook hợp lệ có thể chạy và kéo dài quá trình shutdown. Gọi `Runtime.halt(...)` hay tiến trình bị kết liễu cưỡng bức có hệ quả khác. Không nên diễn giải “mọi non-daemon chết thì OS tức khắc thu hồi tiến trình” mà bỏ qua pha shutdown.

**Hệ quả thiết kế:** công việc cần hoàn thành, flush hoặc đóng resource không nên phó mặc cho một daemon thread bất tận. Hãy cung cấp lifecycle rõ ràng: nhận yêu cầu dừng, đóng executor, `join`/`awaitTermination`, `close()` và shutdown hooks khi phù hợp.

## 4. Các luồng nội bộ JVM/HotSpot thực hiện những gì?

HotSpot cần thực hiện nhiều tác vụ song song với bytecode của ứng dụng. Các mục dưới đây là **ví dụ triển khai**, không phải cam kết mọi JVM hay mọi tiến trình đều có cùng tên/số lượng thread.

| Nhóm | Nhiệm vụ chủ yếu | Quan hệ với ứng dụng |
| --- | --- | --- |
| **GC worker threads** | Thực hiện các bước thu gom heap như đánh dấu, sao chép/di chuyển hoặc các pha song song, tùy collector | Giúp thu hồi bộ nhớ; một số pha cần phối hợp dừng luồng ứng dụng |
| **Concurrent GC threads** | Thực hiện những pha GC có thể tiến hành đồng thời với mã ứng dụng | Giảm một phần công việc trong khoảng dừng; không có nghĩa không còn pause |
| **JIT compiler threads** | Biên dịch/ tối ưu bytecode nóng thành mã máy, xử lý tác vụ biên dịch | Chạy nền và có thể dùng CPU, trong khi ứng dụng tiếp tục thực thi |
| **VM / service / watcher threads** | Điều phối công việc VM, theo dõi và xử lý sự kiện hoặc tác vụ quản trị nội bộ | Cấu trúc và tên cụ thể tùy HotSpot/JDK |
| **Reference Handler** | Xử lý cơ chế `Reference` theo thiết kế thư viện/runtime Java | Có thể xuất hiện như một Java daemon thread trong thread dump |
| **Cleaner và dịch vụ nền Java khác** | Thực hiện cleanup được đăng ký hoặc tác vụ runtime/thư viện | Không nên dùng cleanup nền làm thay thế cho đóng resource tường minh |
| **JFR / profiling / attach-related threads** | Thu thập quan sát, profiling, hoặc phục vụ attach tools khi bật/cần | Có thể xuất hiện theo cấu hình và công cụ đang sử dụng |

**Không phải tất cả nhóm đều “chạy Java” như `new Thread(() -> ...)`.** Trong mã nguồn HotSpot tồn tại cả nhóm `JavaThread` và `NonJavaThread`; ví dụ compiler/GC/VM machinery có thể dùng cấu trúc runtime native. Vì thế `Thread.getAllStackTraces()`, JMX hay một thread dump mức Java **không nhất thiết liệt kê mọi luồng native nội bộ**.

### 4.1. GC và luồng ứng dụng

Khi ứng dụng tạo đối tượng, heap nhận áp lực cấp phát; collector có thể thực hiện chu kỳ GC tùy thuật toán và cấu hình. GC phải phối hợp với **mutator threads** (các luồng thay đổi đồ thị object), xác định GC roots, xử lý tham chiếu và có thể di chuyển đối tượng. Các ứng dụng thường quan sát kết quả như thời gian pause, throughput hoặc CPU tiêu thụ.

- **Stop-the-world (STW):** tại một số pha, JVM cần tạm dừng tiến triển thông thường của thread ứng dụng để lấy một trạng thái nhất quán; các thread GC có thể tiếp tục thực hiện công việc thu gom trong quãng đó.
- **Concurrent GC:** một phần công việc chạy đồng thời với ứng dụng, nhưng vẫn có thể cần các pha dừng hoặc handshake/safepoint.
- **Safepoint:** điểm/trạng thái mà VM có thể phối hợp thao tác cần ràng buộc nhất định trên các thread; không phải tín hiệu “GC luôn dừng mọi thread ở mọi thời điểm”.
- **Tham chiếu đang sống:** stack frame và những root khác góp phần quyết định khả năng truy cập của object. Một thread vẫn giữ reference trong `ThreadLocal` hoặc collection có thể làm object còn reachable và ảnh hưởng retention.

Các collector như G1, Parallel hoặc ZGC có chiến lược và luồng hỗ trợ khác nhau. Số thread GC thường phụ thuộc số CPU có sẵn, cờ cấu hình và bản JDK. **Không lấy tên hay con số mẫu trên mạng làm quy tắc cố định.**

### 4.2. JIT compiler và luồng ứng dụng

Ứng dụng có thể đang thực thi bytecode theo interpreter trong lúc HotSpot nhận diện phương thức/đoạn chạy thường xuyên. Compiler threads biên dịch mã đã quan sát thành native machine code; lần thực thi sau có thể dùng bản biên dịch đã tạo. Tối ưu hóa, deoptimization và lựa chọn tầng compiler là quyết định của JVM.

JIT có thể dùng CPU nền ngay khi thread nghiệp vụ vẫn chạy bình thường. Đừng nhầm việc thấy `CompilerThread` trong công cụ chẩn đoán với việc ứng dụng tự gọi `javac`: **`javac` là compiler trước runtime**, còn JIT compiler là thành phần runtime của VM.

### 4.3. Reference processing và cleanup

Java có các loại tham chiếu đặc biệt như `WeakReference`, `SoftReference` và `PhantomReference`. GC và cơ chế reference processing phối hợp để xử lý các tham chiếu này, với các hoạt động hỗ trợ ở runtime/Java library. Thread tên `Reference Handler` trong HotSpot/OpenJDK là một ví dụ quen thuộc.

Không nên kết luận “Reference Handler là GC worker” chỉ vì có chữ “Reference”, hoặc “Cleaner sẽ đóng socket đúng thời hạn”. Cleanup tự động có tính **không xác định về thời điểm**; còn file, socket, connection có vòng đời nên được quản lý bằng `try-with-resources` hoặc `close()` rõ ràng.

## 5. Hai chiều phân loại thường bị trộn lẫn

| Câu hỏi | Phân loại đúng | Điều nó **không** chứng minh |
| --- | --- | --- |
| Thread thực hiện nghiệp vụ hay hỗ trợ JVM? | Application/runtime/internal role | Không suy ra daemon status |
| Thread giữ JVM sống khi `main` đã xong? | Daemon hay non-daemon (platform threads, cùng quy tắc shutdown) | Không suy ra do ai tạo |
| Thread gắn với OS thread 1–1? | Platform hoặc virtual trong Java 21+ | Không suy ra “GC” hay “application” |
| Thread có đối tượng `java.lang.Thread`? | Java-level hoặc nội bộ native HotSpot | Không suy ra mọi OS thread sẽ hiện trong Java API |
| Task được xử lý đồng thời? | Scheduling/threading behavior | Không bảo đảm thực sự chạy song song trên nhiều core |

Đặc biệt, **daemon != JVM internal** và **JVM internal != tất cả daemon Java threads**. Một chương trình web có thể tự tạo daemon scheduling threads, còn HotSpot có native VM threads mà `Thread.isDaemon()` không phải API mô tả trực tiếp.

## 6. Ví dụ Java 17 chạy được: ứng dụng tạo hai loại thread

Tạo file **`ThreadRolesDemo.java`**:

```java
public class ThreadRolesDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(
                () -> System.out.println("worker: task completed"),
                "application-worker"
        );
        worker.setDaemon(false); // Cần hoàn tất trước khi JVM có thể tự kết thúc.

        Thread helper = new Thread(
                () -> System.out.println("helper: task completed"),
                "application-helper"
        );
        helper.setDaemon(true);  // Luồng do ứng dụng tạo nhưng là daemon.

        System.out.println("worker before start = " + worker.getState());
        System.out.println("worker daemon = " + worker.isDaemon());
        System.out.println("helper daemon = " + helper.isDaemon());

        worker.start();
        worker.join();           // Chốt thứ tự output, đợi worker kết thúc.
        System.out.println("worker after join = " + worker.getState());

        helper.start();
        helper.join();           // Cố ý đợi helper để demo luôn đủ output.
        System.out.println("main: done");
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac ThreadRolesDemo.java
java ThreadRolesDemo
```

**Stdout xác định của ví dụ:**

```text
worker before start = NEW
worker daemon = false
helper daemon = true
worker: task completed
worker after join = TERMINATED
helper: task completed
main: done
```

**Vì sao thứ tự này ổn định?** Hai thread riêng chỉ được `start()` tuần tự, sau mỗi `start()` đều có `join()` trước bước tiếp theo. `join` hoàn tất khi thread đích đã chấm dứt; vì vậy không phụ thuộc vào việc OS cấp CPU cho worker sớm hay muộn. Các dòng in trong ví dụ không phản ánh tên/số lượng GC threads thực tế, vì JVM thực hiện các hoạt động nội bộ độc lập với log nghiệp vụ này.

Ví dụ này chứng minh:

1. Một ứng dụng tự tạo **non-daemon worker** và **daemon helper**; cả hai đều là **application threads**.
2. `worker` từ `NEW` đi đến `TERMINATED` sau `start()/join()`.
3. `helper` là daemon nhưng **vẫn chạy đến hết** ở ví dụ vì `main` chủ động `join()`; nếu bỏ `join()`, không có bảo đảm helper in kịp hoặc hoàn tất trước shutdown.
4. Dòng `main: done` không khẳng định mọi thread nội bộ VM đã biến mất trước khi chương trình trả về. Runtime tự quản lý chúng trong quá trình kết thúc.

**Thay đổi thử nghiệm:** bỏ `helper.join()` rồi chạy nhiều lần. Output từ helper có thể vẫn hiện hoặc không, tùy scheduling. Không dùng sự có mặt/vắng mặt ngẫu nhiên của một dòng để kết luận daemon luôn hoặc không bao giờ chạy.

## 7. Java 21+: virtual thread không đồng nghĩa JVM background thread

Kể từ Java 21, ứng dụng có thể tạo **virtual threads**: `Thread.startVirtualThread(runnable)` hoặc `Thread.ofVirtual()...`. Chúng là luồng logic do Java runtime lập lịch trên các **carrier platform threads**. Chúng thường tiết kiệm tài nguyên hơn platform thread khi có nhiều task chờ I/O, nhưng không thay thế tất cả nhu cầu điều khiển concurrent workload.

- Một virtual thread là **thread của ứng dụng** nếu application tạo nó, dù được hỗ trợ bởi scheduler/runtime.
- Virtual threads luôn có **daemon status**; chúng **không giữ JVM sống** chỉ nhờ tồn tại.
- Carrier thread là platform thread phục vụ scheduling; **không phải chính virtual thread**, và cũng không nên gộp carrier với các worker chuyên trách của GC/JIT.
- `Thread.currentThread()` khi chạy bên trong một virtual thread trả về **virtual thread**, không trả carrier đang thực thi nó.
- Một virtual thread có thể lần lượt chạy trên các carrier khác nhau. Vì vậy không giả định mỗi virtual thread có một OS thread tương ứng.

Ví dụ nhỏ dành riêng **Java 21+**, không biên dịch được trên Java 17:

```java
public class VirtualThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread task = Thread.ofVirtual().name("request-virtual").start(() -> {
            Thread current = Thread.currentThread();
            System.out.println("name = " + current.getName());
            System.out.println("virtual = " + current.isVirtual());
            System.out.println("daemon = " + current.isDaemon());
        });
        task.join();
        System.out.println("main: done");
    }
}
```

Chạy:

```bash
javac VirtualThreadDemo.java
java VirtualThreadDemo
```

Stdout:

```text
name = request-virtual
virtual = true
daemon = true
main: done
```

Dòng `task.join()` khiến chương trình đợi task hoàn tất. Nếu ứng dụng tạo virtual threads xử lý việc dài hạn mà không có cơ chế quản lý vòng đời, khi hết non-daemon platform threads, JVM vẫn có thể bắt đầu shutdown. **Đừng dùng daemon status để định nghĩa nguồn gốc hay mức quan trọng của tác vụ.**

## 8. Vai trò của thread trong vòng đời JVM: từ khởi động đến shutdown

| Mốc | Luồng ứng dụng | Luồng nội bộ/runtime |
| --- | --- | --- |
| **Khởi động** | Launcher đưa ứng dụng tới `main` theo mô hình khởi chạy | VM khởi tạo runtime, cấu trúc quản lý thread và các service cần thiết |
| **Tải/làm nóng ứng dụng** | `main` gọi code, tạo workers, chạm tới thư viện | Class loading, compiler threads và dịch vụ nền có thể được kích hoạt theo nhu cầu |
| **Xử lý tải** | Request/task threads xử lý dữ liệu; phát sinh allocation | GC có thể chạy, JIT tối ưu mã nóng, các service phối hợp liên tục |
| **Chờ I/O/khóa** | Có thể ở `WAITING`, `TIMED_WAITING`, `BLOCKED` hoặc còn `RUNNABLE` tùy thao tác | Runtime/OS phối hợp đánh thức, I/O, điều phối và một số pha GC |
| **Ứng dụng yêu cầu dừng** | Ngừng nhận task, hủy/đóng pools, chờ work quan trọng, đóng tài nguyên | VM xử lý shutdown hooks/sự kiện kết thúc theo cơ chế runtime |
| **Tiến trình kết thúc** | Không còn task chạy trong tiến trình | VM dừng hoạt động, hệ điều hành thu hồi tài nguyên của tiến trình |

**Trách nhiệm của người viết ứng dụng** là quản lý những thread/task mình tạo ra: đặt giới hạn concurrency hợp lý, phản hồi interruption, đóng executor/resource, kiểm soát rò rỉ ThreadLocal và đảm bảo công việc thiết yếu được hoàn tất khi shutdown. **Trách nhiệm của JVM** là lập lịch/thực thi theo runtime, quản lý bộ nhớ/GC/JIT và duy trì dịch vụ VM nội bộ. Không nên “stop GC thread” hay thao tác trực tiếp lên thread internal dựa trên tên tìm thấy trong dump.

## 9. Quan sát và chẩn đoán bằng công cụ

Trong ứng dụng Java, `Thread.currentThread()`, `Thread.getState()`, `Thread.isDaemon()` và `ThreadMXBean` giúp quan sát các **Java threads** ở mức API. Khi vận hành HotSpot:

```bash
# Chạy ví dụ có log GC và safepoint (có thể không phát sinh GC trong chương trình nhỏ)
java -Xlog:gc*,safepoint ThreadRolesDemo

# Liệt kê PID Java của tiến trình đang chạy
jcmd -l

# Lấy thread dump Java của tiến trình (thay <pid> bằng PID thực tế)
jcmd <pid> Thread.print -l

# Xem thông tin heap do HotSpot hỗ trợ
jcmd <pid> GC.heap_info
```

`jcmd` thường nằm trong JDK và cần có quyền/khả năng attach phù hợp. Một JVM ngắn như `ThreadRolesDemo` có thể thoát trước khi bạn kịp chạy `jcmd`; hãy dùng ứng dụng lâu hơn để khảo sát thực tế.

**Cách đọc an toàn:**

- Tìm `main` và thread của framework/application bằng **stack trace và nơi tạo thread**, chứ không chỉ dựa vào tên `pool-N-thread-M`.
- Nhận diện những thread hỗ trợ runtime như `Reference Handler` hoặc `Common-Cleaner` nếu chúng xuất hiện; không mặc định mọi JDK đều hiển thị cùng tên.
- GC và compiler threads có thể xuất hiện trong **OS-level/native diagnostics** hoặc các chế độ/log riêng, nhưng có thể **không hiện đầy đủ trong `Thread.print`**. Vì vậy một Java thread dump **không chứng minh** “JVM không có GC worker”.
- So sánh nhiều snapshot theo thời gian để phân biệt thread đang làm việc bình thường với thread kẹt lâu. `RUNNABLE` riêng lẻ chưa phải bằng chứng CPU cao; `WAITING` riêng lẻ chưa phải lỗi.
- Nếu phân tích chi phí native thread stacks/metaspace/code cache, HotSpot cung cấp **Native Memory Tracking (NMT)** khi bật từ lúc khởi động, chẳng hạn `-XX:NativeMemoryTracking=summary`, rồi dùng `jcmd <pid> VM.native_memory summary`. NMT tiêu tốn overhead và chỉ tổng hợp loại bộ nhớ nó theo dõi.

```bash
# Khi cần theo dõi native memory; bật từ lúc khởi động ứng dụng
java -XX:NativeMemoryTracking=summary ThreadRolesDemo
# Sau đó với ứng dụng còn sống:
jcmd <pid> VM.native_memory summary
```

Các lệnh là ví dụ cho HotSpot/JDK tương thích; không có stdout cố định vì phụ thuộc PID, cấu hình, tuổi tiến trình và hoạt động runtime.

### Dấu hiệu thường gặp và hướng kiểm tra

| Triệu chứng | Điều cần kiểm tra trước |
| --- | --- |
| `main` đã in “done” nhưng tiến trình chưa thoát | Non-daemon worker/executor/server đang sống, shutdown hooks hoặc luồng của thư viện |
| Ứng dụng thoát khi còn tác vụ nền | Có phải chỉ còn daemon/virtual threads? Có `join`/shutdown coordination cho công việc cần hoàn tất không? |
| Số lượng thread tăng không ngừng | Thread pool cấu hình thiếu giới hạn, task bị kẹt, thread leak, server framework tạo worker |
| `OutOfMemoryError: unable to create native thread` | Giới hạn OS/process, memory dành cho thread stacks, số platform/native threads; không vội quy nguyên nhân cho Java heap |
| Pause đáng kể hoặc CPU dùng bởi collector | Thu thập GC logs/JFR, allocation pressure, collector và safepoint |
| CPU dùng nhiều tại thread JIT hoặc lúc warm-up | Phân tích compilation activity và workload; không suy ra code nghiệp vụ sai chỉ từ tên thread |
| Thread dump có nhiều `WAITING` hoặc `BLOCKED` | Đọc stack, lock owners, wait/notification và snapshot nhiều lần; phân biệt idle pool với deadlock |
| Rò rỉ bộ nhớ gắn với thread | `ThreadLocal` giữ tham chiếu, queues, listeners và lifetime của executor/container |

**Cảnh báo thực hành:** không gọi `Thread.stop()` để “diệt” một luồng kẹt, vì phương thức này đã lỗi thời và không an toàn. Ưu tiên cơ chế hủy hợp tác: `interrupt()`, `Future.cancel(true)` khi phù hợp, timeout, đóng tài nguyên và xử lý interruption đúng cách.

## 10. Những nhầm lẫn thường gặp

1. **“Đóng `main` thì JVM kết thúc.”** Sai khi vẫn còn non-daemon thread đang chạy hoặc hệ thống đang trong quá trình shutdown.
2. **“Daemon chính là thread nội bộ JVM.”** Sai; ứng dụng cũng có thể tạo daemon threads, như `application-helper` trong ví dụ.
3. **“Mọi tên thread trong dump đều do JVM tự tạo.”** Sai; server, logging frameworks và thread pools tạo nhiều tên riêng.
4. **“Java thread dump liệt kê toàn bộ OS/native threads.”** Không được bảo đảm. HotSpot có các thread nội bộ không trình bày dưới dạng Java `Thread` thông thường.
5. **“Thread `RUNNABLE` chắc chắn ăn CPU.”** Sai; nó có thể đang sẵn sàng hoặc tham gia thao tác native phụ thuộc ngữ cảnh.
6. **“GC thread luôn chạy đồng thời, không bao giờ dừng application.”** Sai; chiến lược GC có những pha dừng và pha concurrent khác nhau.
7. **“JIT compiler thread biên dịch mã Java nguồn như `javac`.”** Sai; JIT là tối ưu runtime từ bytecode tới mã máy.
8. **“Tạo một virtual thread Java 21 tương đương tạo một OS thread.”** Sai; virtual thread thường chạy lần lượt qua carrier platform threads.
9. **“Dùng `setDaemon(true)` giải quyết hoàn toàn chuyện đóng ứng dụng.”** Sai; có thể khiến tác vụ quan trọng kết thúc dở dang và không thay thế đóng resource rõ ràng.
10. **“Nhiều thread là chắc chắn chạy nhanh.”** Sai; vẫn có contention, scheduling overhead, giới hạn CPU/memory và khối lượng công việc không thể song song.

## 11. Tự kiểm tra

1. Nếu `main` trả về trong khi một `ExecutorService` vẫn duy trì non-daemon workers, JVM có bắt buộc thoát ngay không? Cần đóng executor thế nào?
2. Trong `ThreadRolesDemo`, vì sao helper là daemon nhưng vẫn luôn in dòng của nó? Điều gì thay đổi khi bỏ `helper.join()`?
3. Khi thread dump Java không hiện các tên “GC Thread”, có thể kết luận JVM không chạy GC không? Cần loại quan sát nào khác?
4. Vì sao `Reference Handler` và `C2 CompilerThread` là hai ví dụ dịch vụ runtime khác nhau? Luồng nào có thể là `java.lang.Thread`?
5. Nếu ứng dụng Java 21 tạo hàng nghìn virtual threads, tại sao số OS threads thường nhỏ hơn rất nhiều? Tại sao virtual threads ấy vẫn là luồng ứng dụng?
6. Một thread có trạng thái `BLOCKED` và một thread `WAITING` khác nhau ở điểm nào? Vì sao chỉ số lượng thread chưa đủ để chẩn đoán deadlock?

**Điểm cốt lõi:** JVM khởi tạo và vận hành **những luồng phục vụ chính bản thân runtime** trong khi **luồng ứng dụng** thực thi công việc của người dùng. Daemon status chỉ ảnh hưởng quy tắc giữ tiến trình sống; nó **không** xác định chủ sở hữu luồng. Khi vận hành, phải quan sát đúng mức Java-level, native VM và OS, rồi quản lý lifecycle thread ứng dụng một cách tường minh.

### Tài liệu gốc

- [Java SE 17 — `java.lang.Thread`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): tạo thread, `start()`, `join()` và daemon behavior.
- [Java SE 17 — `Thread.State`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): sáu trạng thái được quan sát từ Java.
- [JVM Specification 17 — Runtime Data Areas, Threads (`2.5)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5): nền tảng đặc tả ngữ cảnh chạy và dữ liệu của thread.
- [JVM Specification 21 — JVM Termination (`5.7)](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.7): termination và shutdown.
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): virtual threads, carrier, scheduling.
- [Oracle JDK 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): mô hình thực thi virtual thread.
