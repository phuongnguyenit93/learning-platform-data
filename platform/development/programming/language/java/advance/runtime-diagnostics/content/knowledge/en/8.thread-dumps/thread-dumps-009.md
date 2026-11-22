# 8.9 Nhận diện giới hạn của thread dump truyền thống đối với virtual thread

**Java 21** đưa **virtual threads** thành tính năng chính thức theo **JEP 444**. Chúng cho phép mô hình **mỗi tác vụ/request một thread** mở rộng đến rất nhiều tác vụ đang chờ I/O mà không cần tạo tương ứng một OS thread cho từng tác vụ. Đây là thay đổi lớn đối với cách đọc **thread dump**: một bản dump truyền thống nhìn rõ **platform threads / carrier threads**, nhưng **không phải danh sách đầy đủ của các virtual threads**. Vì vậy, khi thấy vài chục dòng thread trong jstack mà ứng dụng đang có hàng chục nghìn request chờ, không được vội kết luận rằng các request đó đã kết thúc hoặc JVM đang “không có thread”.

Trên **HotSpot/JDK 21**, cần phân biệt:

- **jstack, jcmd Thread.print, ThreadMXBean.dumpAllThreads, Thread.getAllStackTraces**: các cơ chế truyền thống/management tập trung vào **platform threads**; không dùng chúng để kiểm kê toàn bộ virtual threads.
- **jcmd PID Thread.dump_to_file**: cơ chế xuất **thread dump phù hợp virtual threads**, hỗ trợ **text/plain** và **JSON**, giúp xem stack của nhiều virtual threads trong cùng JVM, nhưng **không có mọi chi tiết khóa/monitor/JNI/heap** như dump truyền thống của JDK 21 và không thay thế phân tích deadlock.
- **JDK Flight Recorder (JFR)** cùng **application tracing/metrics**: theo dõi những sự kiện **xảy ra theo thời gian**, đặc biệt **pinning, start/end, submit failed**, thay vì chỉ chụp một khung hình tại thời điểm điều tra.

Bài viết giới hạn các khẳng định về pinning và định dạng dump ở **Java 21**. Các bản JDK mới hơn có thể thay đổi cơ chế đồng bộ, mức thông tin lock và cú pháp diagnostic command; **không dùng hành vi của JDK 25/26 để suy ngược mọi chi tiết sang JDK 21**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **platform thread, virtual thread, carrier, mounting và unmounting**.
2. Xác định loại thông tin mà **jstack** hoặc **Thread.print** cung cấp, và vì sao danh sách ấy thiếu nhiều virtual threads.
3. Hiểu chính xác **ThreadMXBean.getThreadCount(), getAllThreadIds(), dumpAllThreads(), getThreadInfo()** chỉ hỗ trợ **platform threads** ở Java 21.
4. Dùng **jcmd PID Thread.dump_to_file** với file **JSON** hoặc **text** để thu thêm thông tin về virtual threads, và kiểm tra khả năng thực tế bằng **jcmd PID help**.
5. Phân biệt **Java thread ID** với **OS native thread ID / nid**; không gán cố định virtual thread cho một carrier.
6. Biết vì sao dump virtual-aware không phải **snapshot nguyên tử chung** và trên JDK 21 thiếu những chi tiết khóa/object monitor của dump truyền thống.
7. Dùng **JFR jdk.VirtualThreadPinned** và **jdk.tracePinnedThreads** để chẩn đoán **pinning** theo đúng ngữ nghĩa Java 21.
8. Thiết kế cách lấy bằng chứng theo từng tình huống: request chờ, carrier starvation, CPU cao, pinning hay nghi ngờ deadlock.
9. Viết và chạy một ví dụ Java 21 tự xác nhận giới hạn của **ThreadMXBean**.
10. Báo cáo kết quả không đồng nhất số **platform threads**, số **virtual threads** và số **request/task**.

## 2. Mô hình thực thi: virtual thread không bằng OS thread

**Platform thread** là đối tượng **java.lang.Thread** được ánh xạ theo một OS/native thread và thường giữ ánh xạ ấy xuyên suốt vòng đời.

**Virtual thread** cũng là một đối tượng **java.lang.Thread**, nhưng do Java runtime quản lý; nó không có một OS/native thread dành riêng suốt đời. JVM **mount** virtual thread lên một platform thread gọi là **carrier** khi nó thực thi mã. Khi gặp một hoạt động có thể tạm ngưng hiệu quả, chẳng hạn I/O blocking được runtime hỗ trợ, virtual thread có thể **unmount**, nhường carrier để tác vụ khác chạy. Sau đó virtual thread có thể tiếp tục trên **carrier khác**.

~~~text
Ở một thời điểm:
    Virtual thread A --mounted--> Carrier platform thread #1
    Virtual thread B --parked / unmounted--> Không giữ OS thread
    Virtual thread C --mounted--> Carrier platform thread #2

Ở thời điểm sau:
    Virtual thread A --unmounted--> Không giữ OS thread
    Virtual thread B --mounted--> Carrier platform thread #1
    Virtual thread C --mounted--> Carrier platform thread #3
~~~

Đây là **mô hình khái niệm**, không phải mapping cố định trong một lần JVM chạy. Virtual thread không tự sở hữu một native **nid** cố định giống platform thread. Quan sát carrier ở thời điểm t1 không đủ để khẳng định nó đang chạy cùng virtual thread tại t2.

### 2.1. Trạng thái WAITING không chứng minh một OS thread bị giữ

Giả sử một virtual thread gọi **BlockingQueue.take()** và chưa có item. Nó có thể park/unmount, trong khi **carrier thread được giải phóng** để phục vụ tác vụ khác. Nếu thấy virtual thread đang chờ trong dump JSON, bạn không thể suy ra hệ điều hành cũng đang giữ một native thread cho virtual thread đó.

Ngược lại, một carrier ở trạng thái **RUNNABLE** không nhất thiết là “request đang chạy CPU liên tục”; có thể nó đang chạy một virtual task khác, hỗ trợ scheduler hoặc đang trong mã native. Cần đối chiếu **CPU per native thread**, **JFR**, request traces, trạng thái scheduler và workload.

### 2.2. Virtual threads mở rộng concurrency, không tăng tốc một phép tính

Mục tiêu chính của virtual threads là **để nhiều tác vụ I/O-bound cùng có khả năng chờ và tiếp tục**, không phải làm một đoạn tính toán CPU-bound chạy nhanh hơn. Nếu 10.000 request chờ socket nhưng JVM có 32 carrier, đó có thể là hoạt động bình thường; nếu 32 tác vụ CPU-bound chạy liên tục trên 8 lõi, chúng vẫn tranh tài nguyên CPU.

**Không lấy tỉ lệ virtual thread / carrier làm bằng chứng leak hoặc bottleneck**. Số lượng, trạng thái, tốc độ hoàn tất, latency và chính sách concurrency của ứng dụng mới tạo ngữ cảnh.

## 3. Vì sao thread dump truyền thống có giới hạn?

Thread dump truyền thống được thiết kế khi **số platform threads** thường chỉ ở hàng chục, hàng trăm hoặc nghìn. Nó thường chứa stack, Java/native thread identity, trạng thái, object monitor, lock information và một số dữ liệu JVM-internal. Với hàng trăm nghìn virtual threads, liệt kê như một danh sách phẳng đầy đủ kèm mọi chi tiết sẽ vừa **rất lớn** vừa không phù hợp cách virtual threads được runtime quản lý.

Trên JDK 21, các công cụ và API không cùng một phạm vi:

| Cơ chế | Thấy được gì ở JDK 21? | Không được kết luận |
| --- | --- | --- |
| **jstack PID** | Bức tranh thread dump kiểu truyền thống, chủ yếu platform/carrier và dữ liệu lock/native phù hợp. | Không thấy hàng nghìn virtual threads nghĩa là chúng không tồn tại. |
| **jcmd PID Thread.print -l** | Dump truyền thống thiên về platform threads, có thông tin synchronization/locks theo khả năng VM. | Không coi là kiểm kê toàn bộ virtual thread/task. |
| **SIGQUIT / Ctrl+\** trên Linux | Tùy cách JVM/terminal hoạt động, có thể xuất thread dump truyền thống ra stderr/stdout. | Không coi nội dung trong container log là đủ toàn bộ virtual threads. |
| **Thread.getAllStackTraces()** | Bản đồ stack của **live platform threads** theo Java 21 API. | Không liệt kê virtual threads đã park. |
| **ThreadMXBean.dumpAllThreads(...)** | **Live platform threads**, stack và thông tin synchronization được hỗ trợ. | Không bao gồm đầy đủ virtual threads. |
| **ThreadMXBean.getThreadCount()** | Số **live platform threads**. | Không phải tổng tất cả Java Thread hoặc concurrent requests. |
| **ps -L / top -H / /proc/PID/task** | Native/OS threads nhìn từ Linux theo namespace. | Không phải toàn bộ virtual threads trong heap. |
| **jcmd PID Thread.dump_to_file** | Thread dump chuyên dụng để quan sát **platform + virtual threads** dưới dạng text/JSON, tùy implementation. | Không có tất cả chi tiết object lock, JNI, heap hoặc deadlock như dump cũ. |
| **JFR** | Các events cấu hình được ghi theo thời gian, gồm virtual-thread events phù hợp. | Không tự cung cấp một ảnh đầy đủ của mọi virtual thread đã tồn tại từ trước khi bật. |
| **Application metrics/tracing** | Số task active/queued, request latency, span correlation theo instrumentation. | Không thay stack JVM khi cần xác định mã Java đang chờ. |

**Cẩn trọng với từ “all threads”.** Một số câu trong tài liệu hoặc help cũ dùng cụm “all threads” nhưng về ngữ nghĩa management ở Java 21, **ThreadMXBean chỉ hỗ trợ platform threads**. Hãy kiểm tra **loại command** và API thay vì đọc một dòng mô tả rồi mặc định mọi virtual thread được liệt kê.

### 3.1. Dump truyền thống vẫn rất có giá trị

Không nên loại bỏ **Thread.print** hoặc **jstack**. Chúng hữu ích khi:

- Điều tra **deadlock/monitor contention** giữa các platform threads.
- Cần native thread ID để đối chiếu OS CPU hoặc **perf**.
- Muốn biết carrier pool và worker threads của JVM có dấu hiệu chiếm CPU/đứng ở native call không.
- Cần một số thông tin **locked monitors, ownable synchronizers, JNI, heap statistics** mà dump virtual-aware ở JDK 21 không cung cấp.
- Một ứng dụng còn nhiều **platform threads** do thư viện, GC, compiler, scheduler, connector sử dụng.

**Kỹ thuật đúng là bổ sung, không thay thế tuyệt đối:** dùng dump truyền thống cho phạm vi platform/native, dùng dump virtual-aware/JFR/tracing cho phạm vi các virtual tasks.

## 4. ThreadMXBean: bằng chứng API rõ ràng nhất

Theo **Java SE 21 ThreadMXBean**, interface quản lý hệ thống platform threads; nó **không hỗ trợ giám sát/quản lý virtual threads**.

| Java API | Phạm vi của JDK 21 |
| --- | --- |
| **ManagementFactory.getThreadMXBean().getThreadCount()** | Đếm số platform threads đang sống. |
| **getPeakThreadCount()** | Peak platform threads, không tính virtual threads. |
| **getTotalStartedThreadCount()** | Tổng platform threads đã khởi động từ startup. |
| **getAllThreadIds()** | ID của live platform threads; bỏ qua virtual threads. |
| **getThreadInfo(virtualThreadId)** | Trả **null** cho virtual thread ID (kể cả khi nó đang sống). |
| **dumpAllThreads(true, true)** | Các live platform threads, không mở rộng thành inventory virtual threads. |
| **findDeadlockedThreads()** | Tìm chu trình deadlock trong phạm vi platform threads được API hỗ trợ. |
| **Thread.getAllStackTraces()** | Chỉ bản đồ stack các platform threads. |

**Hệ quả thực tế:** sau khi chuyển request handler sang virtual threads, dashboard JVM thường vẫn cho thấy **thread count chỉ vài chục/hàng trăm**. Điều đó có thể đúng với **platform thread gauge**, không phải tín hiệu request concurrency giảm tương ứng.

### 4.1. Đừng kết luận “không có deadlock” từ mỗi ThreadMXBean

Nếu **findDeadlockedThreads()** trả null, nó không chứng minh **mọi tình trạng kẹt, chờ vòng hoặc dependency cycle giữa virtual threads** đều không có. Trên JDK 21, API này được định nghĩa cho platform threads, trong khi một application-level hang có thể liên quan locks/queues/futures được virtual threads sử dụng.

Tương tự, lệnh **Thread.dump_to_file** không tự chạy một thuật toán deadlock detection đầy đủ cho mọi virtual threads. Nếu nghi ngờ deadlock của tasks, cần phân tích **waiting relationships, lock ownership, application-level correlation, executor queues** hoặc chọn một công cụ phù hợp hơn.

### 4.2. Thread ID của Java khác OS native thread ID

**Thread.threadId()** là ID của đối tượng Java Thread; JDK có thể tái sử dụng sau khi thread kết thúc. Một virtual thread có thể có ID Java riêng nhưng **không có một native TID cố định** khi nó unmount/remount.

Trong output platform thread dump, **nid=...** thường biểu diễn native thread ID ở dạng hex trên HotSpot. **Không tự diễn giải Thread.threadId() của virtual thread thành nid**, cũng không dùng nó làm PID cho jcmd.

~~~text
java pid       : danh tính process JVM theo một PID namespace
platform tid   : ID Java của platform Thread
native nid     : native/OS thread ID của platform thread
virtual tid    : ID Java của Virtual Thread; không có native nid cố định
request ID     : danh tính nghiệp vụ/tracing; không phải thread ID
~~~

Một request có thể đi qua các phase hoặc logical operations khác nhau, và một virtual thread có thể được mount trên các carrier khác nhau theo thời gian. Cần **request/trace ID và timestamp** khi đối chiếu hiện tượng giữa lớp ứng dụng và JVM.

## 5. Thread.dump_to_file: hướng đi dành cho virtual threads

Tài liệu Oracle Java 21 về virtual threads giới thiệu command **Thread.dump_to_file** với output text và JSON. Đối với HotSpot JDK 21, trước hết xác minh:

~~~bash
jcmd 12345 VM.version
jcmd 12345 help Thread.dump_to_file
~~~

**12345 là PID minh họa.** Command có thể không tồn tại trên một VM khác HotSpot, một build JDK cụ thể hoặc một runtime image thiếu jcmd. **jcmd -l** cũng có thể không liệt kê JVM trong Docker riêng; PID phải được lấy từ process/runtime phù hợp.

### 5.1. Xuất JSON

~~~bash
jcmd 12345 Thread.dump_to_file -format=json /diagnostics/vthreads-incident-001.json
~~~

File được **JVM đích** tạo trong filesystem/mount namespace của nó. Với JSON, công cụ có thể phân tích **thread containers, thread identity và stack traces** mà không phải regex từng dòng console; cấu trúc cụ thể và kiểu của trường có thể thay đổi theo version/JDK.

**Không hardcode parser JDK 21 để bắt mọi version**. Ví dụ, định dạng JSON ở các JDK đời sau có thể thay đổi kiểu trường **tid** hoặc cách biểu diễn thread container. Một parser phải kiểm tra format/schema thực tế và có test cho bản JDK được hỗ trợ.

### 5.2. Xuất text/plain

Một cách ít phụ thuộc biến thể tên format là dùng **format mặc định** và file đuôi .txt:

~~~bash
jcmd 12345 Thread.dump_to_file /diagnostics/vthreads-incident-001.txt
~~~

Tài liệu hướng dẫn Java 21 còn minh họa **-format=text**; tuy nhiên với một số help/build của HotSpot, tên format có thể được mô tả là **plain** thay cho **text**. Hãy **dùng kết quả jcmd PID help Thread.dump_to_file của chính JVM đích** làm chuẩn; nếu cần định dạng text và command hỗ trợ mặc định plain, bỏ -format như ví dụ trên là lựa chọn đơn giản.

**Không nhầm với chuyển hướng shell**:

~~~bash
jcmd 12345 Thread.print -l > ./platform-threads.txt
~~~

Ở lệnh cuối, dấu **>** được shell chạy **jcmd** xử lý; file **./platform-threads.txt** nằm theo thư mục hiện tại của **shell**, không phải đường dẫn output file do JVM mở. Trong khi đó đường dẫn **/diagnostics/...** trong **Thread.dump_to_file** thuộc filesystem của **JVM target**.

### 5.3. Giới hạn của dump virtual-aware ở JDK 21

Dù hữu ích hơn khi quan sát virtual threads, format này ở JDK 21 có các giới hạn:

1. **Không bao gồm object addresses và nhiều chi tiết monitor/lock** mà bản dump truyền thống thể hiện; vì vậy thiếu dữ liệu để vẽ toàn bộ lock ownership theo cách jstack -l thường dùng.
2. **Không cung cấp JNI statistics, heap statistics hay một native-thread-to-virtual-thread mapping cố định.**
3. **Không phải snapshot nguyên tử của mọi thread tại cùng một nanosecond.** Java threads vẫn biến động khi dữ liệu được lấy; một virtual thread có thể kết thúc giữa quá trình tạo dump.
4. **Phạm vi virtual thread được liệt kê phụ thuộc implementation và cách threads được tổ chức/track.** API **HotSpotDiagnosticMXBean.dumpThreads** trong JDK 21 chỉ bảo đảm all platform threads và có thể gồm **some or all virtual threads**. Không lấy số dòng/threads trong file làm con số tồn tại chính xác 100% cho mọi triển khai.
5. **Dữ liệu xuất ra có thể rất lớn** khi JVM có nhiều virtual threads; việc tạo và ghi file có chi phí CPU/I/O/bộ nhớ cùng rủi ro disk full.
6. **Không chứng minh nguyên nhân nhân quả.** Thấy nhiều stack đang chờ trên một method không tự cho biết thread đã chờ bao lâu hoặc có đang gây saturation.

Chính vì vậy, trong incident cần giữ **cả dump truyền thống và dump virtual-aware** khi câu hỏi liên quan đồng thời native lock/carrier và virtual task. Nếu JDK đã được nâng cấp sau Java 21, hãy đọc lại help/tài liệu đúng phiên bản trước khi áp dụng giới hạn trên.

## 6. Một ví dụ Java 21 có thể biên dịch: nhìn thấy khoảng trống của API cũ

Đoạn chương trình tạo **6 virtual threads** bằng **Executors.newVirtualThreadPerTaskExecutor()** và giữ chúng chờ một **CountDownLatch** để tiện chụp thread dump. Chương trình đồng thời tự kiểm chứng rằng **ThreadMXBean.getThreadInfo(virtualThreadId)** không cung cấp ThreadInfo cho virtual thread, và **Thread.getAllStackTraces()** không chứa chúng.

**Tệp VirtualThreadVisibilityLab.java:**

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class VirtualThreadVisibilityLab {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(6);
        CountDownLatch release = new CountDownLatch(1);
        ConcurrentLinkedQueue<Thread> observed =
                new ConcurrentLinkedQueue<>();

        ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor();
        try {
            for (int i = 0; i < 6; i++) {
                executor.submit(() -> {
                    observed.add(Thread.currentThread());
                    ready.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }
                });
            }

            ready.await();
            Thread sample = observed.peek();
            ThreadMXBean bean =
                    ManagementFactory.getThreadMXBean();

            System.out.println("virtualTasks=6");
            System.out.println("sampleIsVirtual="
                    + sample.isVirtual());
            System.out.println("threadInfoIsNull="
                    + (bean.getThreadInfo(sample.threadId()) == null));
            System.out.println("legacyStackMapContainsSample="
                    + Thread.getAllStackTraces().containsKey(sample));
            System.out.println("platformThreadCount="
                    + bean.getThreadCount());
            System.out.println("pid="
                    + ProcessHandle.current().pid());
            System.out.println("captureWindowSeconds=45");

            Thread.sleep(45_000L);
        } finally {
            release.countDown();
            executor.close();
        }
        System.out.println("DONE");
    }
}
~~~

Biên dịch và chạy với JDK 21:

~~~bash
javac --release 21 VirtualThreadVisibilityLab.java
java VirtualThreadVisibilityLab
~~~

**Bốn dòng đầu có giá trị xác định theo Java SE 21 khi chương trình chạy bình thường:**

~~~text
virtualTasks=6
sampleIsVirtual=true
threadInfoIsNull=true
legacyStackMapContainsSample=false
~~~

Sau đó các dòng **platformThreadCount=...** và **pid=...** có giá trị **phụ thuộc JVM/hệ điều hành**, rồi **captureWindowSeconds=45**. Cuối cửa sổ chờ (khoảng 45 giây), chương trình kết thúc với **DONE**. **Không có PID hay số platform-thread cố định** và thời gian thực có thể sai lệch do scheduling.

**Vì sao code an toàn hơn một demo thiếu đồng bộ?**

- **ready.await()** bảo đảm cả 6 task đã bắt đầu và đăng ký thread object trước khi chương trình đo.
- **CountDownLatch.await()** cho các virtual threads chờ một cách hợp lý; trong HotSpot JDK 21, dạng chờ này có thể **unmount**, nên không nhất thiết giữ 6 carriers.
- **ConcurrentLinkedQueue** lưu tham chiếu tới đối tượng Thread để kiểm tra chính xác virtual ID; không cần tự liệt kê bằng MXBean.
- **finally** giải phóng các task khi có interrupt/lỗi và **executor.close()** chờ chúng hoàn tất.
- **getThreadInfo** trả null theo hợp đồng ThreadMXBean đối với virtual thread ID, không phải vì chương trình “đánh rơi” task.

**Giới hạn:** demo không phải load test, không bảo đảm dump luôn ghi đúng 6 entry virtual từ mọi implementation. Nó minh họa rõ **API cũ không nhìn thấy đối tượng virtual thread đang tồn tại**.

### 6.1. Chụp bằng hai cách trong cửa sổ 45 giây

Từ terminal thứ hai, **thay PID bằng số thực in trong stdout**. Ví dụ giả định JVM PID trong cùng môi trường là **24680**:

~~~bash
jcmd 24680 VM.version
jcmd 24680 help Thread.dump_to_file
jcmd 24680 Thread.print -l
jcmd 24680 Thread.dump_to_file -format=json /tmp/vt-lab-24680.json
~~~

**/tmp** chỉ dùng cho lab có dung lượng/quyền phù hợp; trong container, /tmp của JVM có thể khác /tmp của shell. Với file JSON, hãy mở file trong đúng filesystem của JVM. Nếu dùng app production, chọn một volume chẩn đoán được provision, không đẩy dump lớn vào writable layer nhỏ.

**Kết quả định tính mong đợi:** Thread.print thể hiện chủ yếu platform threads/carriers; dump JSON có cơ chế quan sát virtual threads, thường có các threads từ executor trong lab. Tên thread, stack, ID, container hierarchy và số entry cụ thể là **phụ thuộc HotSpot build và thời điểm**. Nếu command vắng hoặc attach lỗi, không khẳng định Java 21 không có virtual threads: kiểm tra VM vendor, PID, quyền, JDK tools và phiên bản thực tế.

### 6.2. Đọc một dump JSON có phương pháp

Thay vì chỉ đếm tổng entry, người phân tích nên tìm:

1. **Thông tin process và runtime version**: đúng JVM đã gây incident chưa?
2. **Thread containers/hierarchy** nếu format hỗ trợ: virtual threads được tạo trong executor hoặc nhóm tác vụ nào?
3. **Thread names/IDs**: đã cấu hình tên hữu ích hay chỉ thấy generic/default?
4. **Nhóm stack top frames tương đồng**: nhiều task cùng chờ socket read, queue take, lock acquisition, sleep hay Future.get?
5. **Mốc thời gian dump và request span tương ứng**: snapshot có bắt đúng giai đoạn tăng latency không?
6. **Dữ liệu thiếu**: lock ownership/native details, event duration và tasks đã kết thúc trước snapshot; cần bổ sung JFR và ứng dụng.

**Không giả định format JSON hiện đại có luôn các trường thread state hoặc lock owner giống JDK 25/26.** Viết parser gắn với version/spec của file, không nội suy từ một ảnh chụp hoặc một sample JSON trên Internet.

## 7. Khi thread dump thiếu dữ liệu: ghép nguồn quan sát

| Câu hỏi | Công cụ ưu tiên | Bằng chứng cần kết hợp |
| --- | --- | --- |
| Bao nhiêu **platform/carrier threads**? | ThreadMXBean, jstack/Thread.print, OS threads | CPU, host/cgroup limits, JVM process identity. |
| Bao nhiêu **virtual tasks** đang chờ? | Thread.dump_to_file, application active/queued metrics | Executor/task lifecycle, sampling, request tracing. |
| Tại sao virtual task đang chờ? | Virtual-aware stacks, app logs/traces | Dependency latency, socket/DB pool, queue lengths. |
| **Pinning** có giữ carrier khi blocking? | JFR jdk.VirtualThreadPinned, tracePinnedThreads | Duration, stack site, traffic/concurrency, CPU. |
| Có **native thread CPU hot**? | OS top -H / perf kết hợp Thread.print | Native TID, carrier stacks, sampling profiler. |
| Nghi **deadlock** giữa tasks? | Lock graphs, application-level correlation, Thread.print cho platform | Virtual-aware stacks, dependency/lock ownership ngoài dump JDK21. |
| Có lỗi submit/unpark virtual threads? | JFR jdk.VirtualThreadSubmitFailed | Resource saturation, scheduler activity, errors. |
| Có quá nhiều virtual threads sống lâu? | Application metrics + repeated virtual-aware dumps | Request lifecycle, pool/connection resources, heap growth. |

**Một ảnh chụp không trả lời cả lịch sử.** Thread dump mô tả các thread tại giai đoạn chụp; JFR mô tả events trong recording window; tracing nối các hành động nghiệp vụ. Kết luận mạnh thường cần ít nhất hai nguồn độc lập.

## 8. Pinning trên Java 21: trường hợp carrier không được giải phóng

Trong triển khai virtual threads của **JDK 21**, virtual thread có thể bị **pinned** vào carrier khi chạy trong một số tình huống, đặc biệt:

- Virtual thread thực hiện blocking operation **bên trong synchronized block hoặc synchronized method**.
- Virtual thread đang ở **native method hoặc foreign function** và không thể unmount như blocking I/O Java thông thường.

**Pinning không tự là bug correctness.** Nó chủ yếu có thể làm giảm khả năng scale khi **nhiều lần và thời gian dài**: nhiều carriers bị giữ trong hoạt động blocking khiến scheduler có ít carrier cho virtual threads khác.

~~~text
Hoạt động thông thường trên JDK 21:
Virtual A -- I/O block --> unmount; Carrier 1 rảnh
Virtual B -- ready    --> mount lên Carrier 1

Khi virtual C pinned:
Virtual C -- blocking trong synchronized --> Carrier 2 bị giữ
Virtual D -- ready --> có thể phải chờ carrier khác
~~~

Không dùng **số carrier nhỏ** tự động kết luận scheduler thiếu thread; xem **throughput, queue, latency, blocking duration** và chứng cứ pinning.

### 8.1. JFR VirtualThreadPinned

JDK 21 hỗ trợ JFR events:

| JFR event | Ý nghĩa | Mặc định được Oracle mô tả |
| --- | --- | --- |
| **jdk.VirtualThreadStart** | Virtual thread bắt đầu. | **Disabled** mặc định. |
| **jdk.VirtualThreadEnd** | Virtual thread kết thúc. | **Disabled** mặc định. |
| **jdk.VirtualThreadPinned** | Virtual thread bị pinned khi một hoạt động blocking vượt threshold. | **Enabled** mặc định, threshold **20 ms**. |
| **jdk.VirtualThreadSubmitFailed** | Việc bắt đầu hoặc unpark virtual thread gặp lỗi, thường liên quan tài nguyên. | **Enabled** mặc định. |

Các default trên **thuộc hướng dẫn JDK 21 của Oracle**, không phải bảo đảm mọi recording/profile cấu hình độc lập giống hệt nhau. Kiểm tra event settings của recording thật nếu cần.

Ví dụ một recording JFR có thời lượng hữu hạn (đường dẫn thuộc filesystem JVM):

~~~bash
jcmd 24680 JFR.start \
  name=vt-triage \
  settings=profile \
  duration=60s \
  filename=/diagnostics/vt-triage.jfr
~~~

Lệnh chỉ dùng khi JVM đúng PID, có quyền và người vận hành đã đánh giá disk/overhead. Recording có thể không có file xuất cuối cho đến khi kết thúc theo cấu hình. **JFR.start** không đồng nghĩa tự động bật **jdk.VirtualThreadStart/End**; nếu cần chúng, phải cấu hình event riêng qua JMC hoặc custom JFR settings.

Khi file đã được thu hồi về nơi có **jfr CLI**:

~~~bash
jfr print \
  --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed \
  /path/to/vt-triage.jfr
~~~

Để thêm Start/End nếu đã được bật:

~~~bash
jfr print \
  --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed \
  /path/to/vt-triage.jfr
~~~

**/path/to/vt-triage.jfr** là file tại **máy gọi jfr**, không tự là path container của JVM khi đã sao chép. Dữ liệu JFR được ghi theo thời gian; nó giúp thấy **duration và stack event** tốt hơn một dump tại một thời điểm nhưng chỉ bao phủ những event **đã bật và vượt threshold**.

### 8.2. jdk.tracePinnedThreads cho JDK 21

Trong JDK 21 HotSpot, có thể dùng startup property:

~~~bash
java -Djdk.tracePinnedThreads=full -jar application.jar
~~~

hoặc chế độ **short**:

~~~bash
java -Djdk.tracePinnedThreads=short -jar application.jar
~~~

**application.jar** chỉ là placeholder tên ứng dụng khi triển khai, không phải file được tạo bởi bài. **full** yêu cầu in stack chi tiết khi virtual thread bị block trong tình huống pinned; **short** in những frame liên quan trực tiếp hơn. Đây là công cụ hỗ trợ điều tra của **JDK 21**, thường cần cấu hình lúc startup; nó có thể sinh nhiều log, nên không bật vô hạn ở production.

**Không suy ra “không có output tracePinnedThreads” tức là không có mọi hình thức pinning**. Còn threshold/event semantics, mức hoạt động, khu vực code và các hạn chế của cơ chế tracing. Ưu tiên JFR để thống kê thời lượng/tần suất, kết hợp source code và workload.

### 8.3. Minh họa đoạn synchronized có thể gây pinning

Đoạn **minh họa, không phải chương trình độc lập**:

~~~java
synchronized (sharedLock) {
    // Một lệnh I/O có thể block lâu trên JDK 21.
    callBlockingRemoteService();
}
~~~

Nếu **callBlockingRemoteService()** khiến virtual thread block trong synchronized ở JDK 21, carrier có thể bị giữ. Một hướng điều chỉnh khi phù hợp là dùng **ReentrantLock** cho vùng đồng bộ, kèm **try/finally**:

~~~java
lock.lock();
try {
    callBlockingRemoteService();
} finally {
    lock.unlock();
}
~~~

**Không thay mọi synchronized bằng ReentrantLock theo phong trào**. Hai cơ chế khác nhau về semantics (fairness, condition, lock ownership, hành vi monitor), phải bảo đảm tính đúng, test concurrency, đo trước/sau và chỉ sửa vùng **blocking lâu, xảy ra thường xuyên**.

**Phạm vi phiên bản:** pinning quanh synchronized là đặc trưng quan trọng cần chú ý ở **Java 21**. Các bản JDK mới hơn có thay đổi cơ chế virtual threads và synchronization; nếu nâng JDK, phải đọc tài liệu đúng version thay vì bê nguyên mô tả pinning của JDK 21.

## 9. Điểm mù của snapshot: không biết một thread đã chờ bao lâu

Giả sử dump tại 12:00 thấy 4.000 virtual threads với stack top liên quan:

~~~text
java.util.concurrent.CountDownLatch.await(...)
com.example.service.DownstreamClient.waitForResult(...)
com.example.service.RequestHandler.handle(...)
~~~

Đây là **sample giả định**, không bảo đảm tên class/stack thật. Có ít nhất ba cách giải thích khác nhau:

1. **Lưu lượng cao nhưng bình thường**: nhiều request chờ ngắn, completion rate vẫn tốt.
2. **Upstream/downstream chậm**: request tích tụ vì DB/socket/remote API, latency tăng.
3. **Hệ thống không hoàn tất task**: latch/queue/future không bao giờ được giải phóng, số task sống tăng liên tục.

**Cùng một snapshot không phân biệt đủ ba trường hợp.** Cần đo:

- Số active requests theo từng thời điểm.
- Throughput và completion/failure rate.
- Waiting duration/histogram, timeout rate.
- Connection pool, queue depth, socket timeouts, lock metrics.
- JFR events và lần lấy dump thứ hai/thứ ba.
- Application span IDs/logs gắn instance/trace.

**Bẫy survivorship bias:** dump nhìn những threads **còn sống khi chụp**; những task đã hoàn tất không được đại diện trong đó. Nhìn một nhóm WAITING lớn không cho biết tỉ lệ trong **toàn bộ request đã đi qua**. Tương tự, nếu một virtual thread bị kẹt nhiều phút, nó có xác suất xuất hiện trong mọi snapshot cao hơn task chỉ sống vài ms.

## 10. Ví dụ phân tích số học: không suy ra virtual count từ carrier count

Giả sử ở một thời điểm:

~~~text
Platform threads trong ThreadMXBean : 48
Carrier threads quan sát            : 16
Virtual threads đang sống theo metric ứng dụng: 12.000
Virtual threads trong một file dump : 11.760
~~~

Đây là **số giả định**, không phải output thật. Bạn **không được** tính:

~~~text
12.000 - 48 = 11.952 virtual threads bị thiếu trong JVM
~~~

vì **ThreadMXBean count và virtual task count là hai tổng thể khác nhau**; platform count có JVM/GC/service threads, còn dump virtual-aware có độ bao phủ và thời điểm lấy mẫu khác nhau. Cũng không kết luận 240 thread chênh giữa metric và file dump là **240 “mất”**: có thể các tasks hoàn tất/bắt đầu giữa sampling, một số virtual threads được dump theo cơ chế khác hoặc metric định nghĩa active tasks chứ không phải live Thread objects.

Một cách ghi báo cáo trung thực:

~~~text
12:00:00.000Z app.activeTasks = 12.000 (theo instrumentation)
12:00:00.200Z JVM platformThreadCount = 48
12:00:01.700Z file dump hoàn tất; parser đọc 11.760 virtual entries

Kết luận: Các nguồn quan sát khác phạm vi và khác thời điểm.
Cần so định nghĩa/độ bao phủ trước khi nói tăng/giảm thread.
~~~

Không dùng tỷ lệ **12.000/16 = 750** làm ngưỡng cảnh báo phổ quát. Một carrier có thể phục vụ nhiều virtual threads **theo thời gian**, không phải đang chạy song song 750 virtual threads trên một OS thread.

## 11. Điều tra CPU cao: carrier nóng không có nghĩa có một request cố định

Với platform thread truyền thống, người vận hành thường làm:

~~~bash
top -H -p 24680
jcmd 24680 Thread.print -l
~~~

Rồi chuyển native TID từ decimal sang hex để tìm **nid=...** trong dump. Cách đó vẫn có thể hữu ích với **platform threads/carriers**, nhưng không xây dựng được một bảng **OS TID -> virtual thread** cố định.

**Lý do:** virtual thread có thể unmount và sau đó tiếp tục trên carrier khác. Tại thời điểm lấy CPU sample, carrier có thể đang chạy một task; lúc chụp dump nó đã chạy một task khác. Do đó, đối chiếu bằng TID sau nhiều giây có thể sai ngữ cảnh.

Khi CPU cao:

1. Dùng **OS tools** để xác định native carrier/platform threads nóng.
2. Dùng **sampling profiler/JFR ExecutionSample** (nếu cấu hình tương thích virtual threads) để lấy stack theo thời gian.
3. Lấy **Thread.print** khi cần hiểu carrier/native state, **Thread.dump_to_file** để thấy virtual stacks còn sống.
4. Đối chiếu **timestamp, thread name, trace ID**, VM version và workload.
5. Nếu các virtual tasks làm tính toán CPU dài, virtual threads không làm phép tính tự nhanh hơn; điều tra thuật toán/CPU budget, không chỉ scheduler.

**Đừng gắn nhãn “carrier thread nóng = virtual thread X gây CPU suốt 5 phút” nếu không có sampling evidence liên tục.**

## 12. Những loại câu hỏi mà dump virtual-aware vẫn chưa giải quyết đủ

### 12.1. Deadlock và lock ownership

Trong **JDK 21**, dump virtual-aware không giữ đủ thông tin monitors/locks để thay thế hoàn toàn **Thread.print -l** khi cần phân tích quan hệ sở hữu khóa. Đồng thời **ThreadMXBean.findDeadlockedThreads()** chỉ có ngữ nghĩa platform. Với các deadlock/tình trạng chờ vòng của virtual tasks, cần thêm **application-level lock/dependency graph**, tracing và các công cụ hỗ trợ.

### 12.2. Thread-local context

Virtual threads hỗ trợ **ThreadLocal** và **InheritableThreadLocal**, nhưng có thể tạo rất nhiều thread object. Dump không tự cung cấp danh sách mọi ThreadLocal value hoặc chứng minh memory leak trong context. Nếu nghi ngờ retention, cần xem heap/allocations/lifecycle và logging đã được redact, không cố lấy secret từ dump.

### 12.3. Tình trạng scheduler và queue

Một file JSON có nhiều stack **waiting** không tự cho biết scheduler có bao nhiêu pending tasks, queue backlog hay có starvation. Java 21 không nên bị giả định có sẵn mọi command/MXBean chuyên dụng của JDK mới hơn, chẳng hạn những lệnh virtual-thread scheduler xuất hiện trong tài liệu Java 25/26. **Hãy kiểm tra jcmd PID help và tài liệu đúng JDK 21 đang chạy**, dùng metrics riêng của framework và JFR nếu công cụ thiếu.

### 12.4. Lịch sử và thời lượng blocking

Dump là hình ảnh tại cửa sổ thu. **Nó không đo trực tiếp** virtual thread đã bị park bao nhiêu lần, pinned bao lâu, I/O call mất bao nhiêu ms hoặc request nào chờ nhiều nhất. JFR và application traces có trường duration/timestamp phù hợp hơn cho các câu hỏi này khi event đã được bật.

### 12.5. Thread đã chết trước lúc lấy dump

Không có entry thread trong file không chứng minh nó **chưa từng tồn tại**. Một task có thể được tạo và kết thúc giữa hai lần lấy mẫu. Nếu cần đếm lifecycle, dùng metrics **started/completed/active** và JFR Start/End events được bật có kiểm soát.

## 13. Quy trình chụp bằng chứng production theo từng mức độ xâm lấn

Khi điều tra ứng dụng Java 21 dùng virtual threads, không cần lập tức lấy một dump hàng trăm MB. Hãy đi theo mục tiêu:

**Giai đoạn A — Xác nhận đối tượng và bối cảnh.**

- Xác định Pod/container/service instance, full Java version và VM implementation.
- Kiểm tra PID **theo namespace nơi jcmd chạy**. Java PID trong container có thể khác PID host.
- Ghi workload: request rate, latency p95/p99, active tasks, queue, CPU, memory và downstream errors.
- Xác minh runtime hỗ trợ **Thread.dump_to_file** và file output target có quyền/dung lượng.

**Giai đoạn B — Lấy bằng chứng ít nhiễu hơn.**

~~~bash
jcmd 24680 VM.version
jcmd 24680 help Thread.print
jcmd 24680 help Thread.dump_to_file
~~~

Các lệnh help/VM.version giúp xác định khả năng công cụ. Nếu mục tiêu chỉ là số platform threads hoặc current CPU, không cần đổ ngay toàn bộ virtual threads ra file.

**Giai đoạn C — Khi thật sự cần stacks.**

~~~bash
jcmd 24680 Thread.print -l > ./platform-24680.txt
jcmd 24680 Thread.dump_to_file -format=json /diagnostics/virtual-24680.json
~~~

Trong lệnh đầu, file nằm theo cwd của **shell**; lệnh thứ hai, file do **JVM** tạo. Không mặc định cả hai xuất hiện ở cùng filesystem. Chọn tên file mới tránh overwrite; xác nhận disk/ephemeral-storage và policy thu hồi.

**Giai đoạn D — Thu theo thời gian khi cần.**

Nếu nghi pinning/throttle/submit failure, thiết kế JFR 30–120 giây hoặc khoảng thời gian phù hợp, kiểm tra events enabled/thresholds. Không bật VirtualThreadStart/End tràn lan trên hàng triệu short-lived threads mà chưa đo event overhead.

**Giai đoạn E — Xác minh và kết luận.**

- File có tồn tại và mở được theo version/tool không?
- Các bản chụp có cùng instance, cùng workload và đủ mốc thời gian không?
- Stack nhóm nào đáng điều tra, nhưng có là hiện tượng hay nguyên nhân?
- Còn thiếu lock/native/JFR duration/transaction IDs nào?
- Thu hồi file/tắt temporary debug config và bảo vệ dữ liệu chẩn đoán.

### 13.1. Không lấy quá nhiều thread dumps liên tục

Mỗi lần dump có **chi phí quét/serialize stack và I/O**. Với 100.000 virtual threads, một file JSON có thể lớn và gây disk pressure hoặc latency của chính JVM. Chọn số snapshot phù hợp, ví dụ **hai hoặc ba mẫu trong incident**, với khoảng cách đủ thấy xu hướng; **đây không phải cadence cố định phù hợp mọi hệ thống**.

Không chạy thread dump trong vòng lặp 100 ms trên production chỉ vì muốn “nhìn realtime”. Với diễn biến liên tục, dùng metrics/JFR có sampling hoặc event controls rõ ràng.

## 14. Docker/Kubernetes: vị trí file, quyền và bí mật

Trong container, ba ranh giới có thể khác nhau:

| Ranh giới | Tình huống | Cách xử lý |
| --- | --- | --- |
| **PID namespace** | JVM PID 1 trong container, host PID 48210. | Chọn PID đúng theo vị trí chạy jcmd; không cộng/trừ PID. |
| **Mount namespace** | JVM thấy /diagnostics, host thấy /srv/diag/app. | Dùng **/diagnostics/...** làm đối số Thread.dump_to_file nếu đó là mount JVM. |
| **Quyền** | jcmd chạy root nhưng JVM chạy UID 10001. | JVM cần quyền tạo file ở path đích; quyền shell không thay thế quyền JVM. |
| **Ephemeral/PVC storage** | Dump lớn làm đầy writable layer/emptyDir. | Kiểm tra df -h, df -i, quota, ephemeral-storage, PVC limit và retention. |
| **Logging/identity** | SIGQUIT dump vào container logs hoặc file copy ra laptop. | Biết stream/file ở đâu; bảo vệ stack traces/metadata nhạy cảm. |

Ví dụ khi image có JDK tools và JVM đã được xác định có **PID 1 bên trong container**:

~~~bash
docker exec java-service jcmd 1 VM.version
docker exec java-service jcmd 1 Thread.dump_to_file \
  -format=json /diagnostics/vthreads-incident.json
~~~

**JVM không luôn là PID 1**: shell, tini, supervisor hoặc shareProcessNamespace có thể làm Java PID khác. Với Kubernetes cần chọn đúng container:

~~~bash
kubectl exec java-pod -c app -- jcmd 1 VM.version
kubectl exec java-pod -c app -- jcmd 1 Thread.dump_to_file \
  -format=json /diagnostics/vthreads-incident.json
~~~

Các lệnh chỉ là ví dụ điều kiện; thay Pod/namespace/container/PID/path thật, xác minh image có jcmd, JVM cùng quyền attach và file mount hợp lệ. **kubectl exec** không làm /diagnostics trên laptop trở thành /diagnostics của JVM.

**File dump có thể chứa stack, class/package name, đường dẫn, metadata request**. Không gửi lên kênh công khai, giới hạn quyền đọc và xóa theo chính sách sau sự cố. Khi copy về máy phân tích, kiểm tra file đã hoàn tất, size/checksum và dung lượng nơi nhận.

## 15. Kịch bản xử lý lỗi: request đang treo nhưng jstack chỉ thấy 40 threads

Một service Java 21 sử dụng **Executors.newVirtualThreadPerTaskExecutor()** báo p99 tăng và 8.000 active requests; lệnh **jstack** cho thấy 40–60 threads, nhiều carrier có trạng thái WAITING/RUNNABLE.

**Sai lầm đầu tiên:** kết luận có 8.000 task nhưng chỉ 40 thread nên ứng dụng “thiếu thread” hoặc metric active request sai.

**Phân tích đúng:**

1. Kiểm tra số **platform threads** từ jstack/ThreadMXBean có thể chỉ 40–60, hoàn toàn bình thường dù có nhiều virtual threads.
2. Ghi số active requests từ app metric, xem queue depth/timeout/completion rate: 8.000 là **task count**, không phải native-thread count.
3. Dùng **Thread.dump_to_file -format=json** để xem những virtual stacks đang sống trong thời điểm điều tra. Có thể thấy phần lớn chờ **socket I/O**, queue, future hoặc lock; không tự coi số entry là chính xác toàn bộ 8.000.
4. Nếu stack nhóm lớn chờ DB connection, kiểm tra **pool limits, DB latency, pending queue, timeouts**. Nếu nhóm lớn pinned, dùng **JFR VirtualThreadPinned** để xem vị trí và duration.
5. Dùng **Thread.print -l** bổ sung khi cần biết carrier/native lock hoặc platform-thread deadlocks; dump JSON JDK 21 không có hết dữ liệu đó.
6. Sau khi thay đổi downstream/pool/concurrency, đo lại **throughput, p99, active task count và pinning event rate** trong workload so sánh được.

**Ví dụ kết luận có căn cứ:** “Số platform threads ổn định; phần lớn virtual tasks đang chờ một dependency chậm theo tracing và virtual-aware stacks; chưa có bằng chứng carrier exhaustion.” Đây là kết luận mạnh hơn “JVM không có thread”, vì nó giữ đúng phạm vi mỗi nguồn dữ liệu.

## 16. Tình huống đối chiếu pinning, blocked I/O và CPU

| Hiện tượng | Dump truyền thống | Dump virtual-aware | Nguồn quan trọng khác |
| --- | --- | --- | --- |
| **10.000 request đang chờ socket** | Có thể chỉ thấy carriers và system threads. | Có thể thấy nhiều virtual stacks chờ I/O. | Active request metrics, socket/DB latency, timeout rate. |
| **Carrier pool bị giữ vì pinned blocking** | Carrier/native stacks có thể chỉ ra hoạt động blocking. | Virtual stacks chỉ ra vùng code hiện tại, thiếu duration. | JFR VirtualThreadPinned, tracePinnedThreads JDK21. |
| **Nhiều tác vụ CPU-bound** | Native CPU samples/Thread.print phản ánh carriers. | Virtual stacks tại snapshot, không đo lượng CPU từng task theo thời gian. | JFR/sampling profiler, throughput, CPU cgroup throttling. |
| **Nghi deadlock virtual tasks** | Thread.print -l hữu ích cho platform locks nhưng không hoàn chỉnh. | Có waiting stacks, chưa đủ lock ownership/deadlock detection JDK21. | App lock graphs, tracing, lock metrics, heap/JFR khi cần. |
| **Request hoàn tất quá nhanh để thấy trong dump** | Không thấy trong snapshot. | Cũng có thể không thấy. | Start/end/latency metrics, JFR Start/End khi bật. |
| **JVM process không attach được** | jstack/jcmd thất bại. | Cũng có thể thất bại vì cùng attach mechanism. | Runtime permissions, container identity, log/JFR đã bật trước. |

**Không đồng nhất pinning với RUNNABLE.** Một pinned virtual thread có thể đang block trong synchronized/native, giữ carrier; còn một CPU-bound virtual thread đang chạy liên tục trên carrier không nhất thiết là trường hợp pinning. Tách nguyên nhân bằng event và stack.

## 17. Bài tập có đáp án

**Câu 1.** ThreadMXBean báo 64 threads, nhưng framework có 20.000 active tasks dùng virtual threads. Hai số có mâu thuẫn?

**Đáp án:** không. ThreadMXBean chỉ đếm live **platform threads** trong Java 21; active task metric thuộc lớp ứng dụng và có thể bao gồm nhiều virtual threads.

**Câu 2.** jstack chỉ hiển thị carrier ForkJoinPool và vài worker threads. Có thể kết luận không còn virtual threads đang chờ?

**Đáp án:** không. Những virtual threads đã unmount không có một native stack/OS thread riêng để xuất trong dump truyền thống. Dùng **Thread.dump_to_file** hoặc metrics/tracing phù hợp.

**Câu 3.** Thread.getAllStackTraces() không có một Thread object đã được kiểm tra **isVirtual() == true**. Đây là bug?

**Đáp án:** không, đó là hành vi theo Java SE 21: phương thức trả stack cho live **platform threads**, không đưa virtual threads vào.

**Câu 4.** ThreadMXBean.getThreadInfo(virtualId) trả null dù virtual thread còn sống. Vì sao?

**Đáp án:** interface chỉ hỗ trợ platform threads; null là kết quả được mô tả cho virtual ID, không phải bằng chứng thread đã chết.

**Câu 5.** Dùng Thread.dump_to_file JSON rồi thấy 10.000 entries virtual. Có thể nói JVM đang có chính xác 10.000 virtual threads tại một thời điểm nguyên tử?

**Đáp án:** không chắc. Cần xét implementation/coverage, thời điểm thu và threads thay đổi trong khi dump. Đối chiếu app metrics và thông tin version.

**Câu 6.** Dump JSON JDK 21 thiếu monitor owner, nên bạn kết luận không có lock contention. Đúng không?

**Đáp án:** sai. Dump virtual-aware JDK21 không mang đầy đủ monitor/lock details của dump truyền thống. Cần Thread.print -l, JFR/monitoring khác và dữ liệu từ ứng dụng.

**Câu 7.** Một virtual thread đã chạy trên carrier TID=721 rồi sau đó TID=744. Có nhất thiết là JVM clone thread mới?

**Đáp án:** không. Virtual thread có thể unmount/remount trên các carrier khác nhau. Native TID không phải danh tính bất biến của virtual thread.

**Câu 8.** JFR không có VirtualThreadPinned event trong một phút. Có chứng minh pinning tuyệt đối không xảy ra?

**Đáp án:** không. Event phải được bật và vượt threshold (mặc định hướng dẫn JDK21 nêu 20 ms); một số tình huống ngắn hoặc khác ngữ nghĩa không được phản ánh. Kiểm tra JFR settings/workload.

**Câu 9.** Bạn thấy synchronized quanh một remote call và Java 21 virtual threads có latency cao. Có nên thay mọi synchronized trong ứng dụng bằng ReentrantLock?

**Đáp án:** không. Điều tra hotspot **blocking lâu và thường xuyên** bằng JFR/stack; chỉ thay vùng phù hợp sau khi kiểm tra semantics và test concurrency.

**Câu 10.** Dùng jcmd ở host, output file Thread.dump_to_file là /diagnostics/vt.json bên trong container. Bạn tìm file ở đâu?

**Đáp án:** đường dẫn được **JVM đích** mở trong mount namespace của nó. Tìm trong container/mount tương ứng, không mặc định /diagnostics trên host có cùng file.

**Câu 11.** Thread.print -l giúp xem platform lock owner. Có thể thay thế hoàn toàn JSON virtual-aware dump không?

**Đáp án:** không. Chúng bổ sung: truyền thống mạnh về platform/native/lock, dump_to_file mở rộng quan sát virtual threads nhưng ít chi tiết lock/JNI hơn trên JDK 21.

**Câu 12.** VirtualThreadStart/End mặc định không xuất trong JFR recording. Có nghĩa JFR không hỗ trợ virtual threads?

**Đáp án:** không. JFR hỗ trợ các event này nhưng chúng **disabled mặc định** theo tài liệu hướng dẫn JDK21; có thể bật với custom settings/JMC khi cần, hiểu rằng lượng event có thể lớn.

## 18. Lỗi tư duy và anti-pattern thường gặp

1. **“Một virtual thread = một OS native thread.”** Sai: runtime mount/unmount trên carriers.
2. **“ThreadMXBean.getThreadCount là số mọi Java Thread.”** Sai ở Java21: nó đếm platform threads.
3. **“getAllStackTraces liệt kê mọi virtual thread còn sống.”** Sai theo API.
4. **“jstack không có thread X nghĩa là task X không tồn tại.”** Sai khi task chạy virtual.
5. **“Thread.print -l là cách kiểm kê virtual threads đầy đủ.”** Không đúng.
6. **“Thread.dump_to_file đầy đủ object locks/JNI/heap như Thread.print.”** Không đúng trên JDK21.
7. **“JSON thread dump là snapshot nguyên tử, số entry là số threads chính xác.”** Không có bảo đảm đó.
8. **“Không có deadlock report nghĩa là mọi virtual dependency đều an toàn.”** Không đủ dữ liệu.
9. **“Thread ID Java và nid của Linux luôn quy đổi 1:1.”** Không đúng cho virtual threads.
10. **“Carrier đang hot tức một virtual task cố định chạy trên nó cả phút.”** Mounting thay đổi.
11. **“Virtual WAITING luôn giữ OS thread.”** Có thể đã unmount.
12. **“Pinning luôn là bug và phải xóa mọi synchronized.”** Không; chỉ nguy hiểm khi blocking lâu/thường xuyên.
13. **“Không có VirtualThreadPinned event là không có bất kỳ pinning.”** Còn threshold và config.
14. **“Bật VirtualThreadStart/End không tốn tài nguyên.”** Có thể rất nhiều events khi task short-lived.
15. **“Một snapshot đủ xác định latency root cause.”** Cần timeline/metrics.
16. **“Chụp thread dump hàng trăm lần không ảnh hưởng hệ thống.”** Có overhead và disk/network risk.
17. **“File Thread.dump_to_file nằm ở cwd của jcmd caller.”** File do target JVM tạo.
18. **“Không có jcmd trong image nghĩa JVM không hỗ trợ virtual threads.”** Tooling khác runtime capability.
19. **“Dùng command của JDK26 trên JDK21 chắc chắn chạy.”** Không; kiểm tra phiên bản đích.
20. **“Một con số activeTasks giống số Java virtual thread ở mọi thời điểm.”** Task lifecycle/instrumentation có thể khác.
21. **“Thread count ổn định nghĩa request concurrency ổn định.”** Phạm vi đo khác nhau.
22. **“Virtual threads giúp mọi CPU-bound operation nhanh hơn.”** Chúng tăng concurrency của hoạt động blocking I/O, không đổi tốc độ tính toán đơn luồng.
23. **“PID in container cũng là PID host.”** Không nếu khác PID namespace.
24. **“Không thể debug virtual thread.”** Có thể dùng virtual-aware dumps, JFR, debugger, metrics và traces với phạm vi phù hợp.

## 19. Checklist trước và sau khi lấy bằng chứng

| Câu hỏi | Xác minh |
| --- | --- |
| JDK/VM là gì? | Full Java 21 version/vendor, HotSpot hay implementation khác. |
| Có thật sự dùng virtual threads? | Code/deployment flags, executor config, trace/metrics. |
| PID và namespace đã đúng? | Container/host context, VM.version, cùng user/attach quyền. |
| ThreadMXBean đang đếm nhóm nào? | Platform-only theo Java SE 21. |
| Cần native lock/carrier hay virtual task stack? | Chọn Thread.print hoặc Thread.dump_to_file hoặc cả hai. |
| Thread.dump_to_file có hỗ trợ? | jcmd PID help Thread.dump_to_file trên chính target. |
| File có lưu đúng filesystem không? | Path tuyệt đối trong JVM, owner/quota/disk, mount. |
| Thu tại thời điểm nào? | Incident timestamp, workload baseline, nhiều mẫu phù hợp. |
| Có yêu cầu duration/history không? | JFR events/thresholds và tracing bên cạnh snapshot. |
| Có nghi pinning? | JDK21 synchronized/native blocking; JFR VirtualThreadPinned. |
| Có nghi deadlock? | Đánh giá phạm vi thiếu lock trong JSON và ThreadMXBean, bổ sung graph. |
| Dữ liệu có chứa thông tin nhạy cảm? | Giới hạn quyền và retention của dump/JFR. |
| Có khôi phục cấu hình chẩn đoán không? | Dừng/tắt temporary recording/logs, thu hồi file an toàn. |

## Tài liệu tham khảo

- [Oracle Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): platform/virtual model, mounting, pinning, JFR events, Thread.dump_to_file.
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): lý do thiết kế và hạn chế của truyền thống thread dumps ở Java21.
- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): hợp đồng platform-only, getAllThreadIds, dumpAllThreads và deadlock detection.
- [Java SE 21 — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): isVirtual, threadId, getAllStackTraces.
- [Java SE 21 — Executors.newVirtualThreadPerTaskExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html#newVirtualThreadPerTaskExecutor()): virtual thread per task executor.
- [Java SE 21 — HotSpotDiagnosticMXBean.dumpThreads](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html#dumpThreads(java.lang.String,com.sun.management.HotSpotDiagnosticMXBean.ThreadDumpFormat)): phạm vi platform và virtual threads, file output và giới hạn API.
- [JDK 21 — The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): VM.version, help, Thread.print, JFR.start và yêu cầu attach.
- [Oracle Java 21 — JFR Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): cách xem events trong file recording.
- [Inside Java — Managing Throughput with Virtual Threads](https://inside.java/2024/02/04/sip094/): ví dụ virtual thread dump/JFR và quan sát throughput.
- [Oracle Java SE 21 — Flight Recorder API Guide](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-api-programmers-guide.pdf): thiết kế recording, event settings, stacks và chi phí quan sát.

**Kết luận:** thread dump truyền thống trên Java 21 vẫn rất quan trọng để điều tra **platform threads, native TID và lock-related evidence**, nhưng **không được diễn giải nó như danh sách đầy đủ của virtual threads**. Khi workload dùng nhiều virtual threads, cần **Thread.dump_to_file**, JFR và dữ liệu task/request theo thời gian; khi nghi pinning/deadlock/CPU, ghép thêm **Thread.print -l, OS profiling và bằng chứng từ ứng dụng**. Chỉ so những số liệu có **cùng định nghĩa, đúng JVM, đúng thời gian và phạm vi quan sát**.
