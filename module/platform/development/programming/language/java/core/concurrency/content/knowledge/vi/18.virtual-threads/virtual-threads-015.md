# JDK 21 so với JDK 24+: synchronized thông thường không còn gây pinning kiểu cũ

## Mục tiêu

**JDK 24 triển khai JEP 491 — Synchronize Virtual Threads without Pinning.** Thay đổi này cho phép virtual thread đang đi qua cơ chế monitor của Java (gồm `synchronized`, chờ lấy monitor và `Object.wait()`) nhường carrier thread trong các tình huống blocking mà trước đây dễ gây pinning ở JDK 21. **Không có thay đổi về cú pháp hoặc ý nghĩa loại trừ tương hỗ của `synchronized`.**

Bài học dành cho Java concurrency nói chung, chỉ sử dụng JDK và Java SE. Nội dung cần nắm:

1. Phân biệt **virtual thread**, **carrier**, **mount/unmount**, **blocking**, **pinning** và **monitor contention**.
2. Hiểu chính xác lỗi hiệu năng của JDK 21 khi virtual thread block trong `synchronized` và phần JEP 491 sửa từ JDK 24.
3. Biết trường hợp nào vẫn có thể pin dù đã lên JDK 24+, cách đọc JFR và cách quyết định giữ `synchronized` hay đổi sang `ReentrantLock`.
4. Tự chạy một chương trình **Java 21+** để so sánh kết quả giữa các phiên bản JDK mà không cần thư viện bên ngoài.

## 1. Virtual thread và carrier: lúc nào xảy ra pinning?

Từ Java 21 (JEP 444), virtual thread là một `Thread` do JVM quản lý, thích hợp khi một tác vụ thường phải **đợi** I/O hoặc tín hiệu đồng bộ. Một virtual thread không giữ cố định một OS thread suốt vòng đời. Khi được chạy, virtual thread được **mount** lên một platform thread của scheduler, gọi là **carrier**; khi đợi tại điểm mà JVM hỗ trợ, nó có thể **unmount**, trả carrier lại để thực thi virtual thread khác.

~~~text
                  Khi runnable
Virtual thread A ──────────────► Carrier #1 ─► CPU
       │                              │
       └─ blocking I/O / sleep ───────┤
          (có thể unmount)            └─ Carrier #1 chạy virtual thread B

Nếu bị pinned lúc blocking:
Virtual thread A ──────────────► Carrier #1 ─► chờ cùng A
                                               (không được dùng cho B)
~~~

**Pinning** xảy ra khi virtual thread phải tiếp tục gắn với carrier tại thời điểm nó thực hiện thao tác blocking. Tác động đáng lo là **chiếm một OS thread để chờ** trong khi nhiều virtual thread khác cần carrier. Tình trạng này có thể làm giảm throughput và khả năng mở rộng, nhưng **không tự nó làm kết quả chương trình sai**.

Phân biệt ba hiện tượng:

- **Blocked virtual thread:** tác vụ đang đợi; hoàn toàn bình thường nếu carrier được giải phóng.
- **Pinned virtual thread:** tác vụ đang đợi mà carrier không thể được giải phóng; tốn tài nguyên platform thread.
- **Monitor contention:** nhiều thread tranh cùng một khóa; dù không pin carrier, các thread vẫn phải chờ tới lượt vào critical section. JDK 24 không biến một monitor thành khóa cho phép chạy song song.

Virtual thread không làm một đoạn CPU-bound chạy nhanh hơn. Điểm mạnh là khả năng phục vụ nhiều tác vụ chủ yếu chờ I/O với số carrier có giới hạn.

## 2. JDK 21: vì sao synchronized có thể gây pinning?

Trên JDK 21, khi virtual thread **đang ở trong một `synchronized` block hoặc method** và gọi một thao tác blocking như `Thread.sleep()`, `BlockingQueue.take()` hoặc một lời gọi I/O có khả năng nhường carrier, JVM thường **không unmount được virtual thread** vì nó đang giữ monitor. Carrier bị giữ lại cho thời gian đợi.

~~~java
private final Object monitor = new Object();

void process() throws InterruptedException {
    synchronized (monitor) {
        // Minh họa một thao tác chờ lâu.
        Thread.sleep(200);
    }
}
~~~

Đây là **đoạn mã nằm trong một class**, không phải chương trình chạy độc lập. Trên JDK 21, nếu `process()` được gọi từ virtual thread và `Thread.sleep(200)` thực sự chờ, nó có thể giữ carrier khoảng 200 ms. Nhiều request độc lập dùng **những monitor khác nhau** nhưng đều block trong synchronized vẫn có thể chiếm nhiều carrier đồng thời.

Có một số điểm dễ hiểu sai:

- `synchronized` chỉ thực thi vài phép gán hoặc phép tính trong bộ nhớ **không phải tình huống đáng sợ**: phần quan trọng là blocking **dài và thường xuyên** trong monitor.
- Việc chương trình chờ lock do contention không đồng nghĩa với pinning; cần xem khả năng **unmount** trong lần chờ đó.
- Pinning không làm monitor bị bỏ qua: `synchronized` vẫn bảo đảm mutual exclusion, quan hệ happens-before giữa unlock/lock phù hợp và tính tái nhập của Java monitor.
- Pinning khác deadlock. Deadlock là các vòng phụ thuộc khóa không thể tiến triển; JEP 491 không tự giải deadlock, lost notification hay race condition.

### Cách giảm pinning trên JDK 21

Nếu profiling cho thấy một vùng `synchronized` **thường xuyên giữ carrier khi đợi lâu**, bạn có thể:

1. **Đưa I/O hoặc thao tác chờ ra ngoài critical section** khi bất biến dữ liệu cho phép.
2. **Rút ngắn thời gian giữ monitor** và kiểm tra lại atomicity.
3. **Dùng `ReentrantLock`** cho đúng vùng cần bảo vệ khi không thể tránh blocking bên trong: cách đợi của AQS/`LockSupport` hỗ trợ virtual-thread-friendly parking, tránh hạn chế *do monitor* vốn có trên JDK 21.
4. **Nâng JDK lên 24+** nếu phù hợp vòng đời sản phẩm và kiểm thử, vì JEP 491 giải quyết trực tiếp nguồn pinning của Java monitor.

Không nên thay mọi `synchronized` thành `ReentrantLock` theo kiểu máy móc: đổi khóa có thể kéo theo thay đổi cách dùng `wait/notify`, điều kiện chờ, xử lý interrupt, quy tắc unlock và độ phức tạp code.

## 3. JDK 24+: JEP 491 thay đổi chính xác điều gì?

JEP 491 được đưa vào **JDK 24**. Việc dùng monitor thông thường không còn khiến một virtual thread nhất thiết phải giữ carrier trong khi nó bị block. JVM hỗ trợ **unmount** virtual thread trong các tình huống quan trọng sau:

| Tình huống | JDK 21 | JDK 24+ |
| --- | --- | --- |
| Virtual thread gọi `Thread.sleep` hoặc blocking API trong `synchronized` | Có thể pin carrier vì monitor đang được giữ | Monitor thông thường không còn là lý do pin |
| Virtual thread chờ vào `synchronized` do lock đang bị thread khác giữ | Hạn chế triển khai monitor cũ có thể giữ carrier trong một số đường chờ | Cơ chế monitor được điều chỉnh để chờ mà giải phóng carrier |
| Virtual thread gọi `Object.wait()` trong vùng sở hữu monitor | Có thể pin carrier do monitor | Có thể chờ mà unmount carrier trong đường thực thi bình thường |
| Critical section chỉ thực hiện tính toán ngắn | Thường không ảnh hưởng đáng kể bởi pinning | Vẫn cần monitor để bảo đảm mutual exclusion |
| Blocking trong native/foreign frame | Vẫn có thể pin | **Vẫn có thể pin**; JEP 491 không xóa mọi nguyên nhân |

Cần nói chính xác: **JDK 24+ loại bỏ pinning do synchronized thông thường**, chứ không tuyên bố một virtual thread sẽ *không bao giờ* bị pinned. Ví dụ, nếu lời gọi ở bên trong synchronized còn đi qua native/foreign frame có vấn đề, nó vẫn có thể bị pin vì **nguyên nhân khác**.

### Minh họa trình tự

~~~text
Ví dụ: virtual thread thực thi synchronized(lock) { Thread.sleep(250); }

JDK 21:
  A được mount trên carrier-1
  A vào monitor lock
  A ngủ 250 ms
  carrier-1 bị giữ trong lúc A ngủ (monitor-related pinning)
  A thức dậy, ra khỏi monitor, kết thúc

JDK 24+:
  A được mount trên carrier-1
  A vào monitor lock
  A ngủ 250 ms, được unmount (trong trường hợp thông thường)
  carrier-1 có thể chạy B
  A sẵn sàng, được remount, tiếp tục giữ logic monitor đúng như cũ
  A ra khỏi monitor, kết thúc
~~~

Việc **unmount** không có nghĩa `lock` được release khi `A` ngủ. Với `Thread.sleep` trong `synchronized`, A vẫn **giữ monitor**; các thread khác muốn vào cùng monitor phải chờ A ra khỏi critical section. Riêng `Object.wait()` vốn có ngữ nghĩa **tạm nhả monitor, chờ rồi giành lại monitor** khi thức dậy; quy tắc này vẫn giữ nguyên.

JEP 491 cải thiện việc sử dụng carrier, **không** xóa tính tuần tự của critical section, **không** nâng throughput nếu bản thân khóa hoặc downstream service là nút thắt.

## 4. Ví dụ đầy đủ chạy trên Java 21 và Java 24+

Tạo file **`MonitorPinningDemo.java`**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class MonitorPinningDemo {
    private static final Object MONITOR = new Object();
    private static final ReentrantLock LOCK = new ReentrantLock();

    private static void pause() {
        try {
            Thread.sleep(250);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        }
    }

    private static void runWithMonitor() {
        synchronized (MONITOR) {
            pause();
        }
    }

    private static void runWithReentrantLock() {
        LOCK.lock();
        try {
            pause();
        } finally {
            LOCK.unlock();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual().name("pinning-demo").start(() -> {
            System.out.println("virtual=" + Thread.currentThread().isVirtual());
            runWithMonitor();
            System.out.println("monitor finished");
            runWithReentrantLock();
            System.out.println("lock finished");
        });
        worker.join();
    }
}
~~~

Chạy với **bất kỳ JDK 21+**:

~~~bash
javac MonitorPinningDemo.java
java MonitorPinningDemo
~~~

Output của riêng chương trình (không tính log khởi động JVM/JFR nếu bật công cụ chẩn đoán):

~~~text
virtual=true
monitor finished
lock finished
~~~

Cùng một chương trình có output như nhau trên JDK 21 và JDK 24+, vì **ngữ nghĩa khóa và kết quả của hai lời gọi không đổi**. Điểm khác nhau cần kiểm chứng bằng **JDK Flight Recorder (JFR)** hoặc đo hiệu năng dưới tải đại diện: trên JDK 21, thao tác sleep trong `synchronized` thường tạo sự kiện pinning; trên JDK 24+, riêng việc giữ monitor không còn gây loại pinning này.

Vì chỉ tạo một virtual thread, chương trình này **minh họa cơ chế và cách đo**, không phải benchmark để khẳng định JDK 24 có throughput cao hơn bao nhiêu. Thời gian sleep thực tế và event có thể thay đổi theo JDK, JFR settings và môi trường.

## 5. Xác minh pinning bằng JFR

JFR ghi sự kiện `jdk.VirtualThreadPinned` khi virtual thread bị pin trên carrier lâu hơn ngưỡng cấu hình. Trên các bản JDK nêu trong tài liệu chính thức, sự kiện này mặc định được bật với ngưỡng thường là **20 ms**. Hãy đo với workload đủ dài và chạy cùng bài thử trên hai runtime **đã xác định rõ version/vendor/build**.

Chạy chương trình với JFR (lần lượt bằng lệnh `java` của JDK 21 rồi JDK 24+):

~~~bash
java -version
java -XX:StartFlightRecording=filename=pinning.jfr,dumponexit=true,settings=profile MonitorPinningDemo
jfr print --events jdk.VirtualThreadPinned pinning.jfr
~~~

Lệnh `java -XX:StartFlightRecording=...` có thể in thêm log khởi động JFR. File `pinning.jfr` được tạo khi recording kết thúc. Dùng tên file riêng cho từng JDK nếu muốn so sánh song song.

**Kỳ vọng hợp lý:**

- **JDK 21:** Khi `runWithMonitor()` ngủ khoảng 250 ms trong monitor, bạn có thể thấy `jdk.VirtualThreadPinned` gắn với `MonitorPinningDemo` và đường gọi `Thread.sleep`. `runWithReentrantLock()` không gây pinning *chỉ bởi monitor*, vì không dùng Java monitor cho lock đó.
- **JDK 24+:** Tình huống `Thread.sleep` thông thường bên trong `synchronized` sẽ không còn tạo sự kiện pinned do monitor theo JEP 491. **Điều này không có nghĩa JFR sẽ không có bất kỳ sự kiện pinning nào** khi chạy chương trình phức tạp khác.

Trên **JDK 21**, còn có chế độ chẩn đoán nhanh:

~~~bash
java -Djdk.tracePinnedThreads=full MonitorPinningDemo
~~~

Nếu phát hiện blocking trong vùng monitor, JVM có thể in stack trace với thông tin monitor. Tùy chọn `-Djdk.tracePinnedThreads` là công cụ chẩn đoán gắn với cách triển khai cũ; **không dùng nó làm phép kiểm tra chính trên JDK 24+**, nơi công cụ này đã bị loại bỏ. Ưu tiên JFR cho bản mới.

### Đọc kết quả sao cho đúng

Một trace JFR đáng xem cần ít nhất các yếu tố: sự kiện **VirtualThreadPinned**, **duration** (độ dài), stack trace (đường gọi) và, nếu runtime hỗ trợ, **blockingOperation**, **pinnedReason**, **carrierThread**. Trên các JDK mới, trường nguyên nhân giúp phân biệt native/VM frame với các tình huống khác.

**Không thấy event** có nhiều cách giải thích:

- Không có pinning.
- Pinning ngắn hơn threshold cấu hình.
- Workload không đi qua đường code gây pinning, hoặc tác vụ kết thúc trước recording.
- Cấu hình event/stack trace/recording không phản ánh workload đang chạy.

Không kết luận “không pin” chỉ vì một lần chạy cục bộ không có event. Với hệ thống thực, hãy thu thập JFR dưới tải đại diện, đối chiếu số carrier, độ trễ hàng đợi, throughput và các blocking operation đang thực sự xảy ra.

Dùng `jcmd` để tạo thread dump khi cần khảo sát virtual thread đang chờ:

~~~bash
jcmd <PID> Thread.dump_to_file -format=json threads.json
~~~

Thay `<PID>` bằng process ID JVM; dump giúp thấy các thread và stack đang chờ, nhưng **không thay thế** dữ liệu thời lượng pinning của JFR. `jcmd` cần đúng JVM, quyền truy cập và khả năng attach.

## 6. Những trường hợp JDK 24+ vẫn có thể pin

JEP 491 nhằm giải quyết pinning **do Java monitor**. Các đường sau vẫn cần điều tra:

| Nguồn tiềm năng | Vì sao còn vấn đề | Hướng xử lý |
| --- | --- | --- |
| **JNI/native methods** | Native frame có thể ngăn virtual thread unmount khi phát sinh blocking | Profiling native boundary; tránh đợi lâu trong đường native hoặc dùng kiến trúc phù hợp |
| **Foreign Function & Memory API / lời gọi foreign** | Chuyển điều khiển vào mã native theo FFM vẫn có thể tạo ràng buộc carrier | Kiểm tra thời gian/blocking và khả năng đặt việc đó ở đường thực thi khác |
| **Khởi tạo/lấy khóa class initialization** | Một số đường JVM phục vụ class initialization và chờ class khởi tạo có thể giữ carrier | Khởi tạo trước tài nguyên quan trọng; điều tra trace/JFR |
| **Từng dạng I/O hoặc thao tác JVM không unmount được** | Phụ thuộc đường API và runtime; không phải mọi thao tác chờ đều là virtual-thread-aware | Đo bằng JFR và quan sát thời gian carrier thực tế |

Sự tồn tại của các nguồn này không có nghĩa mọi đoạn có JNI, file I/O hay class loading **đều** pin. Cần nhìn vào **đường thực thi và thao tác block thực sự**. Tương tự, việc JFR báo `jdk.VirtualThreadPinned` trong một chương trình dùng `synchronized` trên JDK 24+ **không chứng minh** JEP 491 thất bại: nguyên nhân có thể là native/VM frame bên dưới.

## 7. Vì sao vẫn cần thiết kế synchronized cẩn thận?

**Không pin carrier** chỉ giải quyết một trong các chi phí khi concurrency cao. Ví dụ dưới đây vẫn có điểm nghẽn trên cả JDK 21 lẫn JDK 24+:

~~~java
private final Object shared = new Object();

void slowCriticalSection() throws InterruptedException {
    synchronized (shared) {
        // Mọi caller dùng cùng "shared" vẫn phải tuần tự chờ nhau.
        Thread.sleep(500);
    }
}
~~~

Với nhiều virtual thread cạnh tranh **cùng shared**, mỗi lần chỉ một thread vào critical section, tạo hàng chờ lớn ngay cả khi các thread chờ không giữ carrier. Nếu điều kiện nghiệp vụ không yêu cầu giữ khóa trong thời gian chờ, đặt lệnh chờ ra ngoài monitor và chỉ khóa phần cập nhật state:

~~~java
private final Object shared = new Object();
private int completed;

void improvedStructure() throws InterruptedException {
    Thread.sleep(500); // Chờ ngoài monitor nếu không cần bảo vệ bởi shared.
    synchronized (shared) {
        completed++;
    }
}
~~~

Hai ví dụ là **đoạn thành viên class**, không phải chương trình độc lập. Việc chuyển lệnh ra ngoài monitor **chỉ hợp lệ khi vẫn bảo đảm bất biến/atomicity** của nghiệp vụ: chẳng hạn nếu kết quả I/O và cập nhật state bắt buộc phải được khóa cùng nhau, việc tách có thể tạo race.

Đối với throughput thực tế, quan sát cả:

- **Độ dài critical section** và contention trên monitor.
- **Số kết nối/tài nguyên downstream** như database pool, HTTP connection cap, API rate limit.
- **Số tác vụ đang chờ** và throughput, không chỉ số virtual thread.
- **Blocking native** và scheduler starvation.
- **Bộ nhớ** của các tác vụ đang chờ và các biến `ThreadLocal` tạo mới theo task.

Virtual threads thường **không cần pool thread theo kích thước cố định**. Khi cần giới hạn truy cập tài nguyên khan hiếm, dùng ràng buộc trực tiếp như `Semaphore` hoặc giới hạn connection pool thay vì cố tình gom virtual thread vào pool nhỏ.

## 8. Có còn cần ReentrantLock trong JDK 24+?

**Có**, nhưng lựa chọn giờ dựa trên **tính năng khóa và cấu trúc code**, không phải quy tắc “virtual thread luôn tránh synchronized”.

| Nhu cầu | `synchronized` | `ReentrantLock` |
| --- | --- | --- |
| Critical section ngắn, cần mutual exclusion đơn giản | Rất phù hợp; tự unlock khi thoát block | Cũng được nhưng phải `unlock` trong `finally` |
| JDK 21, block lâu trong monitor và profiling thấy pinned | Có thể cần refactor | Có thể tránh loại pinning do monitor |
| JDK 24+, block trong monitor thông thường | Không còn pin do monitor theo JEP 491 | Không bắt buộc phải thay chỉ để tránh pinning cũ |
| Thử lock không chờ `tryLock()` | Không có phương thức trực tiếp tương đương | Có |
| Lấy lock hỗ trợ interrupt `lockInterruptibly()` | Chờ vào monitor không có API trực tiếp tương đương | Có |
| Nhiều điều kiện chờ độc lập | `wait/notify/notifyAll` trên cùng monitor | `Condition` hỗ trợ nhiều wait set |
| Fairness tùy chọn | Không có fairness constructor | Có optional fairness policy |

Ví dụ chuyển khóa để hỗ trợ yêu cầu cụ thể (có thể chạy trong class chứa trường `lock`):

~~~java
import java.util.concurrent.locks.ReentrantLock;

private final ReentrantLock lock = new ReentrantLock();

void updateWithInterruptibleLock() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        // Cập nhật state chia sẻ hoặc tác vụ phải bảo vệ.
    } finally {
        lock.unlock();
    }
}
~~~

Đây là **trích đoạn class**, không thể biên dịch độc lập vì đặt field/method ở top level. `ReentrantLock` không tự làm thao tác bên trong nhanh hơn. Dù dùng loại lock nào, phần critical section dài và contention vẫn ảnh hưởng latency. Việc đổi `wait/notify` sang `Condition.await/signal` phải thiết kế lại đúng vòng điều kiện và tín hiệu, không đơn giản thay tên API.

## 9. Hướng xử lý khi nâng ứng dụng từ JDK 21 lên JDK 24+

Một lộ trình kiểm chứng hợp lý:

1. **Chốt phiên bản runtime** của từng môi trường, không chỉ `sourceCompatibility` hoặc `--release`. Lúc chạy trên JDK 21 vẫn có giới hạn pinning của 21, dù mã được biên dịch bằng toolchain khác.
2. **Lấy baseline với JDK 21**: JFR `jdk.VirtualThreadPinned`, throughput, độ trễ p95/p99 và số carrier đang hoạt động dưới workload đại diện.
3. **Thử cùng workload trên JDK 24+**: giữ code, khối lượng công việc và cấu hình so sánh nhất quán; xác nhận các event do monitor thông thường giảm/mất.
4. **Điều tra event còn lại**: tra stack trace, nguyên nhân native/VM, class initialization và đường I/O thực tế trước khi sửa code.
5. **Review các workaround cũ**: từng trường hợp đã đổi `synchronized` sang `ReentrantLock` *chỉ để tránh pinning* có thể không còn cần thiết về mặt performance trên 24+, nhưng không buộc phải đổi lại khi code đang tốt.
6. **Kiểm tra bottleneck kế tiếp**: cùng một monitor vẫn serialize truy cập, database pool vẫn có giới hạn, CPU-bound tasks không được tăng tốc bởi virtual thread.

Không tối ưu chỉ bằng một con số `jdk.VirtualThreadPinned`: có thể pin đã hết nhưng contention hoặc downstream limit vẫn chi phối tổng throughput.

## 10. Sai lầm phổ biến

1. **“JDK 24 làm synchronized không cần khóa nữa.”** Sai. Mutual exclusion, visibility/happens-before và tính tái nhập vẫn giữ nguyên.
2. **“Một virtual thread bị blocked tức là nó pin.”** Sai. Blocked nhưng đã unmount là cách virtual thread hoạt động hiệu quả.
3. **“JDK 24 loại bỏ mọi pinning.”** Sai. Native/foreign và một số đường VM vẫn có thể pin.
4. **“Có synchronized trong stack thì pinning event trên JDK 24 chắc do monitor.”** Sai. Cần đọc **pinnedReason/stack trace**; monitor có thể chỉ là khung gọi bên ngoài.
5. **“Nâng JDK sẽ chữa deadlock.”** Sai. Deadlock, lock ordering và race là vấn đề correctness khác.
6. **“Không có JFR event tức là không có pinning.”** Chưa chắc. Threshold, thời điểm bắt đầu recording và workload có thể che khuất.
7. **“Phải đổi toàn bộ synchronized sang ReentrantLock khi dùng virtual threads.”** Sai, nhất là từ JDK 24+. Trên JDK 21 cũng chỉ nên đổi những vùng thực sự gây pinning đáng kể.
8. **“Đã không pin thì có thể giữ monitor xuyên I/O dài tùy ý.”** Sai. Monitor vẫn chặn các thread muốn cùng truy cập dữ liệu.
9. **“Virtual thread làm request nhanh hơn.”** Không trực tiếp. Mục tiêu chính là khả năng scale khi nhiều request đang chờ I/O.
10. **“Kiểm chứng bằng JDK compile là đủ.”** Không đủ. Hành vi monitor pinning phụ thuộc phiên bản **JVM thực thi** và phải đo khi chạy.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Trên JDK 21, tại sao `synchronized(lock) { Thread.sleep(300); }` có thể giảm khả năng scale khi có nhiều virtual thread?

Vì khi đang giữ monitor, virtual thread không thể unmount theo cơ chế cũ; mỗi lần blocking giữ một carrier/OS thread. Nếu số thao tác này lớn và thường xuyên, scheduler có ít carrier rảnh để chạy task khác.

**Câu 2.** Cùng code trên JDK 24+, thread khác có thể vào cùng monitor trong lúc thread đầu ngủ không?

**Không.** JEP 491 cho phép giải phóng *carrier*, không giải phóng *monitor* của `synchronized` khi sleep. Thread khác phải chờ đến lúc monitor được unlock.

**Câu 3.** Trên JDK 24+, vì sao native blocking vẫn có thể làm JFR ghi `VirtualThreadPinned`?

Vì JEP 491 giải quyết pinning do Java monitor, không thể bảo đảm unmount an toàn trong mọi native/foreign hoặc VM frame.

**Câu 4.** Khi nào nên giữ `ReentrantLock` dù đã lên JDK 24?

Khi cần `tryLock`, `lockInterruptibly`, `Condition`, fairness hoặc khi cấu trúc hiện tại đã ổn định. Không có yêu cầu thay tất cả về `synchronized`.

**Câu 5.** Tại sao việc không còn `VirtualThreadPinned` không đồng nghĩa throughput chắc chắn tăng?

Vì chương trình vẫn có thể giới hạn bởi CPU, contention trên cùng monitor, connection pool, rate limit, bộ nhớ hoặc downstream service.

## Nguồn tài liệu chuẩn

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): nền tảng virtual thread, carrier và pinning ở các bản đầu.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): cơ chế thay đổi monitor vào JDK 24.
- [Oracle — Virtual Threads trên JDK 21](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): giới hạn `synchronized` cũ, `ReentrantLock`, JFR và `jdk.tracePinnedThreads`.
- [Oracle — Significant Changes in JDK 24](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html): xác nhận JEP 491 nằm trong JDK 24.
- [Oracle — Virtual Threads trên JDK 24](https://docs.oracle.com/en/java/javase/24/core/virtual-threads.html): pinning còn lại từ native/foreign, JFR và hướng dùng virtual threads.
- [OpenJDK — RFR triển khai JEP 491](https://mail.openjdk.org/pipermail/core-libs-dev/2024-November/134311.html): ba đường thay đổi quan trọng gồm unmount khi giữ monitor, chờ vào monitor và `Object.wait()`.

**Kết luận kỹ thuật:** trên **JDK 21**, blocking dài bên trong `synchronized` là một nguồn pinning cần đo và có thể phải xử lý. Từ **JDK 24**, JEP 491 sửa cơ chế đó, cho phép giữ cách viết synchronized thông thường mà không giữ carrier chỉ vì monitor. Hãy tiếp tục quan sát JFR cho native/VM pinning và kiểm soát contention, tài nguyên downstream theo đúng nhu cầu thực tế.
