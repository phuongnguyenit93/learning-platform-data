# Hoàn thiện báo cáo JFR, kiểm thử hồi quy và hướng dẫn vận hành

Lab này đưa các kỹ thuật quan sát hiệu năng Java 21 vào một quy trình có thể lặp lại: tạo workload đại diện, ghi Java Flight Recorder (JFR), phân tích sự kiện và stack trace, viết báo cáo có bằng chứng, chạy kiểm thử hồi quy rồi chuẩn bị hướng dẫn vận hành. Mục tiêu là biến một recording thành quyết định kỹ thuật có thể kiểm chứng, thay vì chỉ đính kèm file JFR mà không giải thích nguyên nhân.

Lab dùng một chương trình nhỏ tạo ba tình huống: virtual thread bị pin trong synchronized khi blocking, nhiều task tranh explicit lock và nhiều task chờ một số lượng resource slot giới hạn. Đây là workload mô phỏng để học cách đọc JFR. Khi áp dụng cho production, cần thay resource slot mô phỏng bằng metric từ connection pool hoặc dependency thật.

## 1. Kết quả cần hoàn thành

Sau lab, cần có đủ các đầu ra sau:

| Đầu ra | Nội dung cần có |
|---|---|
| JFR recording | File .jfr được ghi trong workload có thể tái hiện |
| JFR analysis | Summary, event được lọc và stack trace liên quan |
| Performance report | Môi trường, workload, số liệu, phát hiện, nguyên nhân và khuyến nghị |
| Regression checks | Functional/integration tests và phép đo hiệu năng có thể so sánh |
| Operations guide | Cách ghi recording, kiểm tra, lưu trữ, điều tra và xác nhận khắc phục |

Không coi một file recording hoặc một con số latency là kết luận. Báo cáo phải liên kết triệu chứng, dữ liệu đo, stack trace, giả thuyết và kết quả sau thay đổi.

## 2. Chuẩn bị môi trường Java 21

Lab cần:

- JDK 21 có các công cụ javac, java, jcmd và jfr.
- Một thư mục làm việc riêng để lưu class file, recording và báo cáo.
- Quyền attach vào JVM nếu dùng jcmd để bắt đầu recording của tiến trình đang chạy.
- Đủ dung lượng đĩa để giữ recording và log.

Xác nhận công cụ:

~~~bash
java -version
javac -version
jcmd -h
jfr --version
~~~

Ghi lại vendor và phiên bản đầy đủ của JDK trong báo cáo. Không trộn recording lấy từ JDK 21 với kết luận dựa trên cấu hình event của JDK khác mà không ghi rõ khác biệt.

Tạo thư mục làm việc. Trên Linux/macOS:

~~~bash
mkdir -p build/reports/jfr
~~~

Trong PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/reports/jfr
~~~

## 3. Tạo workload có thể tái hiện

Tạo file JfrLab.java với nội dung sau. Chương trình dùng virtual-thread-per-task executor của Java 21 và chạy tuần tự ba giai đoạn. Mỗi giai đoạn in thời điểm bắt đầu/kết thúc để đối chiếu với timeline trong JFR.

~~~java
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.locks.ReentrantLock;

public final class JfrLab {
    private static final Object MONITOR = new Object();
    private static final ReentrantLock EXPLICIT_LOCK = new ReentrantLock();
    private static final Semaphore RESOURCE_SLOTS = new Semaphore(4);
    private static final int TASK_COUNT = 40;

    @FunctionalInterface
    private interface LabTask {
        void run() throws InterruptedException;
    }

    private JfrLab() {
    }

    public static void main(String[] args) throws Exception {
        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("JDK=" + Runtime.version());

        runPhase("PINNING", JfrLab::pinnedTask);
        runPhase("EXPLICIT_LOCK", JfrLab::explicitLockTask);
        runPhase("RESOURCE_SLOTS", JfrLab::resourceSlotTask);

        System.out.println("LAB_COMPLETE " + Instant.now());
    }

    private static void runPhase(String name, LabTask action) throws Exception {
        System.out.printf("BEGIN %s %s%n", name, Instant.now());

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<?>> futures = new ArrayList<>();

            for (int i = 0; i < TASK_COUNT; i++) {
                futures.add(executor.submit(() -> {
                    action.run();
                    return null;
                }));
            }

            for (Future<?> future : futures) {
                future.get();
            }
        }

        System.out.printf("END %s %s%n", name, Instant.now());
    }

    private static void pinnedTask() throws InterruptedException {
        synchronized (MONITOR) {
            // Trên JDK 21, virtual thread có thể bị pin khi blocking
            // trong synchronized region.
            Thread.sleep(100);
        }
    }

    private static void explicitLockTask() throws InterruptedException {
        EXPLICIT_LOCK.lock();
        try {
            // ReentrantLock có thể park virtual thread trong lúc chờ.
            // Giữ lock trong lúc sleep để tạo contention có thể quan sát.
            Thread.sleep(100);
        } finally {
            EXPLICIT_LOCK.unlock();
        }
    }

    private static void resourceSlotTask() throws InterruptedException {
        RESOURCE_SLOTS.acquire();
        try {
            // Semaphore mô phỏng resource pool chỉ có bốn slot.
            Thread.sleep(100);
        } finally {
            RESOURCE_SLOTS.release();
        }
    }
}
~~~

Ba giai đoạn mô phỏng ba loại chờ khác nhau:

1. PINNING: một virtual thread giữ intrinsic monitor trong lúc sleep. Trên Java 21, thao tác blocking này có thể giữ carrier và tạo event jdk.VirtualThreadPinned nếu vượt threshold.
2. EXPLICIT_LOCK: các task tranh cùng ReentrantLock. Task chờ lock có thể park và unmount khỏi carrier; JFR có thể ghi jdk.ThreadPark.
3. RESOURCE_SLOTS: Semaphore giới hạn bốn task được dùng resource đồng thời. Các task còn lại chờ permit. Đây chỉ là mô hình giới hạn concurrency, không phải JDBC connection pool.

Chương trình cố ý dùng sleep để tạo thời gian chờ đủ dài cho recording. Không dùng workload này làm benchmark hiệu năng thực tế hoặc làm tiêu chuẩn latency của production.

Lab này tái hiện hành vi pinning của Java 21. Từ JDK 24, JEP 491 thay đổi cơ chế monitor để virtual thread có thể unmount khi chờ trong synchronized code thông thường; do đó không kỳ vọng cùng một event pinning từ giai đoạn PINNING khi chạy trên JDK mới hơn. Native method và foreign function vẫn có thể gây pinning. Ghi rõ runtime version khi so sánh recording giữa các môi trường.

### Compile

Trên Linux/macOS:

~~~bash
mkdir -p build/classes
~~~

Trong PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/classes
~~~

Sau đó biên dịch:

~~~bash
javac --release 21 -d build/classes JfrLab.java
~~~

Kiểm tra class file nếu cần:

~~~bash
javap -verbose build/classes/JfrLab.class
~~~

Class file Java 21 có major version 65.

## 4. Ghi JFR khi khởi chạy chương trình

Cách đơn giản nhất cho lab là bật recording ngay khi khởi chạy:

~~~bash
java -XX:StartFlightRecording=filename=build/reports/jfr/lab.jfr,settings=profile,dumponexit=true -cp build/classes JfrLab
~~~

JVM bắt đầu recording trước khi workload chạy và ghi file khi tiến trình kết thúc. Profile configuration thu thập nhiều chi tiết hơn cấu hình default, phù hợp cho một lần điều tra có giới hạn. Recording có overhead; không mặc định bật profile recording với mọi ứng dụng production trong thời gian dài.

Nếu muốn kiểm soát thời lượng hoặc cần lấy recording từ một service đang chạy, có thể attach bằng jcmd. Tìm PID từ log chương trình hoặc:

~~~bash
jcmd -l
~~~

Bắt đầu recording:

~~~bash
jcmd <pid> JFR.start name=PracticalLab settings=profile disk=true maxage=10m maxsize=256m
~~~

Kiểm tra recording:

~~~bash
jcmd <pid> JFR.check
~~~

Dump dữ liệu ra file:

~~~bash
jcmd <pid> JFR.dump name=PracticalLab filename=build/reports/jfr/practical-lab.jfr
~~~

Sau khi lấy đủ dữ liệu, dừng recording:

~~~bash
jcmd <pid> JFR.stop name=PracticalLab
~~~

Các lệnh jcmd cần được chạy với quyền phù hợp đối với tiến trình JVM đích, thường là cùng user và cùng môi trường/container. Nếu dùng tên recording khác, thay đúng tên ở các lệnh check, dump và stop.

## 5. Kiểm tra recording trước khi phân tích

Không mở ngay một file lớn trong công cụ GUI. Trước tiên kiểm tra file tồn tại, kích thước hợp lý và đọc được:

~~~bash
jfr summary build/reports/jfr/lab.jfr
~~~

Summary cho biết khoảng thời gian recording, số lượng event theo loại và thông tin tổng quát. Kiểm tra:

- Recording có bao phủ cả ba giai đoạn không.
- Các event mong đợi có được ghi không.
- File có bị quá ngắn hoặc không có event do dừng recording quá sớm không.
- Event count có hợp lý với workload và threshold không.

Nếu dùng jcmd, có thể kiểm tra file practical-lab.jfr thay cho lab.jfr.

### Lưu ý về event threshold

Trong Java 21, jdk.VirtualThreadPinned được bật mặc định với threshold 20 ms. Event pinning ngắn hơn threshold có thể không xuất hiện. Nhiều event ứng dụng khác trong profile cũng có threshold; Oracle ghi nhận phần lớn event ứng dụng chỉ được ghi khi thời lượng vượt 20 ms theo cấu hình tương ứng.

Không thấy event không đồng nghĩa chắc chắn không có hiện tượng. Kiểm tra recording configuration, threshold, thời điểm ghi và stack trace trước khi kết luận. jdk.VirtualThreadStart và jdk.VirtualThreadEnd bị tắt mặc định; nếu báo cáo cần số lượng virtual thread bắt đầu/kết thúc, hãy bật chúng trong custom JFR configuration trước khi chạy.

## 6. Lọc các event liên quan

In các event chính để đọc nhanh:

~~~bash
jfr print --events jdk.VirtualThreadPinned,jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.SocketRead,jdk.SocketWrite --stack-depth 20 build/reports/jfr/lab.jfr
~~~

Nếu cần dữ liệu máy đọc được:

~~~bash
jfr print --json --events jdk.VirtualThreadPinned,jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark build/reports/jfr/lab.jfr
~~~

Không nên in tất cả event ra terminal ngay từ đầu nếu recording lớn. Lọc theo event và tăng stack depth khi cần thêm ngữ cảnh.

### Đọc event theo từng giai đoạn

| Giai đoạn | Event/dấu hiệu cần tìm | Cách diễn giải |
|---|---|---|
| PINNING | jdk.VirtualThreadPinned, stack có Thread.sleep và synchronized caller | Virtual thread bị pin trong thời gian blocking trên JDK 21 |
| EXPLICIT_LOCK | jdk.ThreadPark, stack có ReentrantLock/AbstractQueuedSynchronizer | Task đang park để chờ explicit lock |
| RESOURCE_SLOTS | jdk.ThreadPark, stack có Semaphore/AbstractQueuedSynchronizer | Task đang chờ permit của resource slot mô phỏng |

JFR có thể ghi các event tương tự ở nhiều giai đoạn. Dùng timestamp BEGIN/END trong stdout để gắn event vào giai đoạn tương ứng. Trong ứng dụng thực tế, nên bổ sung request ID hoặc custom JFR event có metadata an toàn để liên kết workload với trace.

### Phân biệt monitor enter và monitor wait

- jdk.JavaMonitorEnter mô tả thời gian chờ để vào intrinsic monitor đang được giữ bởi thread khác.
- jdk.JavaMonitorWait mô tả thời gian thread chờ qua Object.wait().
- jdk.ThreadPark thường liên quan explicit lock và các cấu trúc concurrency dựa trên LockSupport.
- jdk.VirtualThreadPinned chỉ ghi trường hợp virtual thread bị pin lâu hơn threshold; đây không phải event đo mọi loại lock contention.

Không gộp các event này thành một chỉ số “lock time” duy nhất. Mỗi event mô tả một thao tác chờ khác nhau.

## 7. Phân tích bằng JDK Mission Control

Mở file JFR trong JDK Mission Control (JMC) tương thích với recording. Bắt đầu từ các view tổng quan rồi đi sâu vào event:

1. Xác nhận khoảng thời gian và phiên bản runtime.
2. Xem CPU load, execution samples và garbage collection.
3. Lọc Virtual Thread Pinned để tìm stack trace và duration dài.
4. Lọc Java Monitor Enter để xác định monitor contention.
5. Lọc Thread Park để tìm explicit lock, semaphore hoặc queue wait.
6. Xem Socket Read/Write khi nghi ngờ dependency mạng chậm.
7. Đối chiếu timestamp với log ứng dụng và workload phase.

Khi phân tích, ưu tiên tổng thời gian chờ và tần suất lặp lại theo request path. Một event đơn lẻ kéo dài không nhất thiết là bottleneck chính; nhiều event ngắn nhưng lặp lại trên đường xử lý nóng cũng có thể ảnh hưởng throughput.

## 8. Hoàn thiện báo cáo JFR

Báo cáo nên trả lời năm câu hỏi: điều gì xảy ra, xảy ra khi nào, bằng chứng nào hỗ trợ kết luận, thay đổi nào được đề xuất và kết quả sau thay đổi ra sao.

### Mẫu báo cáo

~~~markdown
# Báo cáo hiệu năng: <tên dịch vụ hoặc workload>

## 1. Tóm tắt
- Triệu chứng:
- Ảnh hưởng đến người dùng:
- Nguyên nhân đã xác nhận:
- Hành động đề xuất:

## 2. Môi trường
- JDK vendor/version:
- OS/container và CPU limit:
- Heap/JVM flags:
- Build/commit:
- Dependency versions:

## 3. Workload
- Kịch bản:
- Số request/task:
- Concurrency:
- Warm-up:
- Thời lượng đo:
- Dữ liệu đầu vào:

## 4. Kết quả
| Metric | Baseline | Candidate | Thay đổi |
|---|---:|---:|---:|
| Throughput | | | |
| p50 latency | | | |
| p95 latency | | | |
| p99 latency | | | |
| Error rate | | | |
| CPU utilization | | | |
| Allocation rate | | | |
| GC pause | | | |

## 5. Bằng chứng JFR
| Event | Count | Tổng duration | Stack/request path |
|---|---:|---:|---|
| jdk.VirtualThreadPinned | | | |
| jdk.JavaMonitorEnter | | | |
| jdk.ThreadPark | | | |
| jdk.SocketRead | | | |

## 6. Phân tích
- Quan sát:
- Giả thuyết:
- Bằng chứng xác nhận/bác bỏ:
- Bottleneck chính:
- Yếu tố chưa xác định:

## 7. Thay đổi
- Code/config thay đổi:
- Rủi ro:
- Kế hoạch rollback:

## 8. Kiểm thử hồi quy
- Functional tests:
- Integration tests:
- Performance workload:
- Kết quả baseline/candidate:
- Kết luận:

## 9. Vận hành
- Dashboard/alert:
- Lệnh lấy JFR:
- Vị trí lưu recording:
- Owner:
- Thời hạn lưu:
~~~

Không điền số liệu giả định vào báo cáo. Nếu một metric không được ghi, ghi “không thu thập” và giải thích lý do; không suy ra số liệu từ stack trace.

### Viết kết luận có bằng chứng

Một kết luận tốt có cấu trúc:

> Trong workload X ở commit Y, p99 latency tăng từ A lên B. Recording cho thấy event Z xuất hiện N lần, tổng thời gian D; các stack trace tập trung tại phương thức M. Sau khi thay đổi C, chạy lại cùng workload cho kết quả E và event Z giảm còn F. Kết luận này được giới hạn trong cấu hình và tải đã đo.

Không viết “JFR chứng minh database chậm” nếu recording chỉ cho thấy thread chờ socket. Cần đối chiếu database metrics, query duration, connection pool và network để xác định phía gây chậm.

## 9. Thiết kế kiểm thử hồi quy

Kiểm thử hồi quy có hai mục tiêu khác nhau:

- **Functional regression:** bảo đảm thay đổi tối ưu không làm sai kết quả, thứ tự, transaction, concurrency hoặc xử lý lỗi.
- **Performance regression:** phát hiện throughput giảm, latency tăng, CPU/allocation tăng hoặc thời gian chờ tài nguyên dài hơn.

Không dùng JFR event count làm assertion chức năng. JFR hỗ trợ tìm nguyên nhân; test xác nhận hợp đồng và giới hạn hiệu năng ở cấp phù hợp.

### Tầng 1: unit test

Kiểm tra logic không phụ thuộc thời gian máy:

- Kết quả nghiệp vụ đúng với input đại diện và edge case.
- Dữ liệu chia sẻ vẫn nhất quán khi nhiều task đồng thời.
- Semaphore/lock luôn được release trong finally khi task thành công hoặc thất bại.
- Exception và cancellation được truyền/quan sát đúng.
- Không có connection hoặc resource bị giữ sau khi thao tác hoàn tất.

Ví dụ kiểm tra giới hạn concurrency và bảo đảm permit được trả lại. Đây là test cho semaphore gate; với connection pool thật, hãy kiểm tra thêm pool metrics và vòng đời JDBC connection:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class ResourceGateTest {
    @Test
    void respectsConcurrencyLimitAndReturnsEveryPermit() throws Exception {
        int limit = 3;
        Semaphore slots = new Semaphore(limit);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<?>> futures = new ArrayList<>();

            for (int i = 0; i < 20; i++) {
                futures.add(executor.submit(() -> {
                    slots.acquire();
                    try {
                        int current = active.incrementAndGet();
                        peak.accumulateAndGet(current, Math::max);
                        Thread.sleep(20);
                    } finally {
                        active.decrementAndGet();
                        slots.release();
                    }
                    return null;
                }));
            }

            for (Future<?> future : futures) {
                future.get();
            }
        }

        assertTrue(peak.get() <= limit);
        assertEquals(limit, slots.availablePermits());
    }
}
~~~

Test không khẳng định thời gian chạy phải nhỏ hơn một con số cố định. Nó kiểm tra hai bất biến có ý nghĩa: concurrency không vượt giới hạn và mọi permit được trả lại sau khi các task hoàn tất.

### Tầng 2: integration test

Chạy với dependency thật hoặc môi trường tương đương:

- Database, connection pool, transaction và query.
- HTTP client với timeout và response body được đóng đúng cách.
- Queue/broker và giới hạn concurrency.
- Shutdown của executor và xử lý request đang chạy.

Test cần tự tạo dữ liệu, có timeout, dọn tài nguyên và không phụ thuộc thứ tự chạy. Nếu test chạy song song, cô lập schema, tenant hoặc namespace.

### Tầng 3: performance regression workload

Chọn workload đại diện với:

- Tải bình thường, tải đỉnh dự kiến và một mức vượt tải có kiểm soát.
- Tỷ lệ request theo endpoint hoặc operation.
- Payload và phân bố dữ liệu tương tự thực tế.
- Warm-up đủ để JIT và connection pool ổn định.
- Thời gian đo đủ dài để giảm ảnh hưởng của dao động ngắn.
- Cùng cấu hình JDK, CPU, heap, container limit và dependency khi so sánh.

Đo throughput, p50/p95/p99 latency, error rate, CPU, allocation, GC, queue wait, connection acquisition time và các event JFR liên quan.

## 10. So sánh baseline và candidate

Quy trình so sánh:

1. Chọn commit baseline đang được xem là tốt và commit candidate có thay đổi.
2. Dùng cùng JDK 21 vendor/version, JVM flags, heap, CPU limit và dependency.
3. Dùng cùng dataset, workload profile, concurrency và thời lượng.
4. Chạy warm-up trước khi bắt đầu đo.
5. Chạy nhiều lượt độc lập và lưu kết quả từng lượt.
6. Ghi JFR cho baseline và candidate theo cùng settings.
7. So sánh phân vị latency, throughput, lỗi và tài nguyên; không chỉ so sánh average.
8. Đọc JFR để giải thích khác biệt lớn, không dùng recording thay cho load-test metrics.

Một bảng so sánh có thể dùng:

| Metric | Baseline | Candidate | Ngưỡng dự án | Kết quả |
|---|---:|---:|---:|---|
| Throughput | | | | |
| p95 latency | | | | |
| p99 latency | | | | |
| Error rate | | | | |
| CPU per request | | | | |
| Allocation per request | | | | |
| Pool acquisition p95 | | | | |
| Pinning total duration | | | | |

Ngưỡng chấp nhận phải dựa trên SLO, độ biến thiên đã đo và đặc điểm hệ thống. Không áp dụng một phần trăm regression chung cho mọi service. Trên CI runner dùng chung, latency có thể dao động do noisy neighbor; chạy performance gate nghiêm ngặt trên runner chuyên dụng hoặc môi trường tải được kiểm soát.

### Khi cần benchmark vi mô

Nếu thay đổi nằm trong một method hoặc thuật toán nhỏ, dùng Java Microbenchmark Harness (JMH) thay vì viết vòng lặp thời gian thủ công. JMH xử lý warm-up, fork, measurement iteration và tối ưu hóa của JIT tốt hơn một bài test thông thường.

Benchmark vi mô không thay thế load test của service. Một method nhanh hơn chưa chắc làm request nhanh hơn nếu bottleneck nằm ở database, network hoặc connection pool.

## 11. Đưa kiểm thử hồi quy vào CI

Pipeline nên chia theo chi phí:

| Job | Khi chạy | Nội dung |
|---|---|---|
| Compile + unit test | Mỗi pull request | Compile Java 21 và test logic |
| Integration test | Mỗi pull request hoặc theo chính sách | Database, HTTP, messaging, resource lifecycle |
| Performance smoke | Pull request quan trọng hoặc nightly | Workload ngắn, phát hiện regression lớn |
| Full performance comparison | Nightly/release candidate | Nhiều lượt, tải đại diện, JFR và báo cáo |
| Production observation | Sau deploy | Theo dõi latency, error, saturation và JFR khi cần |

CI nên lưu:

- Test reports và log phiên bản JDK/build.
- Baseline/candidate metrics ở định dạng có thể so sánh.
- JFR recording khi cần điều tra.
- Commit, build ID, workload config và checksum của artifact.

Không làm job CI thông thường thất bại chỉ vì một JFR event đơn lẻ xuất hiện. Dùng metric ổn định và SLO làm gate; dùng JFR để tìm nguyên nhân của regression.

## 12. Hướng dẫn vận hành khi có sự cố

### Khi latency tăng

1. Ghi nhận thời điểm bắt đầu, endpoint bị ảnh hưởng, p95/p99 và error rate.
2. Kiểm tra traffic, CPU, heap/GC và dependency latency.
3. Lấy JFR recording có giới hạn thời gian và dung lượng.
4. Lấy thread dump có virtual thread nếu ứng dụng dùng virtual threads.
5. Kiểm tra pinning, monitor wait, thread park và socket I/O.
6. Kiểm tra pool metrics: active, idle, pending, acquisition time và timeout.
7. Liên kết stack trace với request path và trace ID đã được làm sạch.
8. Thử thay đổi có phạm vi nhỏ trong môi trường an toàn; so sánh lại với baseline.

### Lệnh vận hành cơ bản

Liệt kê JVM:

~~~bash
jcmd -l
~~~

Kiểm tra recording:

~~~bash
jcmd <pid> JFR.check
~~~

Tạo recording ngắn:

~~~bash
jcmd <pid> JFR.start name=Incident settings=profile duration=2m filename=incident.jfr
~~~

Tóm tắt và lọc event:

~~~bash
jfr summary incident.jfr
jfr print --events jdk.VirtualThreadPinned,jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.SocketRead,jdk.SocketWrite incident.jfr
~~~

Lấy thread dump có virtual thread trên JDK 21:

~~~bash
jcmd <pid> Thread.dump_to_file -format=text threads.txt
~~~

Lệnh recording có thể chạy trong môi trường production nếu quyền attach, chính sách vận hành và giới hạn tài nguyên cho phép. Chọn thời lượng/dung lượng phù hợp; không chạy nhiều profile recording nặng cùng lúc khi hệ thống đang quá tải.

## 13. Hướng dẫn ứng phó theo bằng chứng

| Bằng chứng | Điều cần xác minh | Hướng xử lý ban đầu |
|---|---|---|
| VirtualThreadPinned kéo dài trên Java 21 | Stack có blocking trong synchronized hoặc native/foreign call? | Thu hẹp synchronized region; xem xét explicit lock hoặc API không blocking phù hợp |
| JavaMonitorEnter tăng | Nhiều request tranh cùng monitor? | Giảm thời gian giữ khóa, chia vùng dữ liệu hoặc giảm shared mutable state |
| ThreadPark tăng | Thread đang chờ lock, semaphore, queue hay pool? | Xác định owner và metric của resource tương ứng |
| SocketRead/SocketWrite kéo dài | Dependency, network hay timeout? | Đối chiếu downstream latency, timeout, retry và connection reuse |
| Pool active chạm max và pending tăng | Connection bị giữ lâu, leak hay DB quá tải? | Kiểm tra usage time, leak detection, query/transaction và database capacity |
| CPU execution samples tập trung một method | Hot path tính toán hay vòng lặp không tiến triển? | Profile method, thuật toán, allocation và dữ liệu đầu vào |

Không tăng số carrier, connection pool size hoặc timeout chỉ để làm triệu chứng biến mất. Trước tiên xác định tài nguyên đang bị giới hạn và hệ quả khi tăng giới hạn đó.

## 14. Vận hành recording an toàn

JFR recording có thể chứa class/package nội bộ, thread name, stack trace, endpoint, đường dẫn file và metadata vận hành. Cần xem recording là dữ liệu chẩn đoán nội bộ:

- Lưu ở vị trí có quyền truy cập hạn chế.
- Không commit recording vào repository hoặc đưa vào artifact ứng dụng.
- Không gửi recording lên ticket hoặc dịch vụ công khai nếu chưa rà soát.
- Đặt thời hạn lưu và xóa theo chính sách incident/data retention.
- Ghi kèm build ID, thời gian, JDK và workload để giữ khả năng truy vết.
- Trước khi chia sẻ, lọc event không cần thiết bằng công cụ phù hợp và kiểm tra lại file đầu ra.

JDK có lệnh jfr scrub để lọc event, category hoặc thread trong recording. Việc lọc này giúp giảm dữ liệu cần chia sẻ nhưng không phải cam kết tự động xóa mọi thông tin nhạy cảm khỏi nội dung event còn lại.

## 15. Mẫu operations guide cho service

Mỗi service nên duy trì một trang hướng dẫn ngắn, có thể dùng mẫu sau:

~~~markdown
# Operations guide: <service>

## Runtime
- JDK vendor/version:
- JVM flags:
- Container CPU/memory:
- JFR policy:

## SLO và dashboard
- Availability:
- p95/p99 latency:
- Throughput:
- Error rate:
- CPU/GC:
- Connection pool:

## Khi có latency regression
1. Xác nhận thời điểm và endpoint.
2. Kiểm tra dashboard và dependency.
3. Lấy JFR trong thời lượng đã quy định.
4. Lấy thread dump nếu cần.
5. Đối chiếu pool/DB/network metrics.
6. Lưu report và quyết định mitigation.

## Lệnh chẩn đoán
- jcmd -l
- jcmd <pid> JFR.check
- jcmd <pid> JFR.start ...
- jfr summary ...
- jfr print ...
- jcmd <pid> Thread.dump_to_file ...

## Mitigation và rollback
- Thay đổi có thể bật/tắt:
- Người phê duyệt:
- Điều kiện rollback:
- Cách xác nhận phục hồi:

## Artifact và dữ liệu
- Vị trí recording:
- Quyền truy cập:
- Retention:
- Owner:
~~~

Điền các giá trị thật của service, không để placeholder trong tài liệu vận hành đã phát hành. Lệnh phải được thử trong staging hoặc môi trường có quyền tương đương trước khi đưa vào runbook production.

## 16. Tiêu chí hoàn thành lab

- [ ] Chương trình lab compile bằng javac --release 21.
- [ ] Recording bao phủ ba giai đoạn workload.
- [ ] jfr summary đọc được file recording.
- [ ] Đã lọc event pinning, monitor/park và đối chiếu timestamp.
- [ ] Báo cáo ghi rõ JDK, workload, event, stack và giới hạn kết luận.
- [ ] Functional/integration regression checks được xác định.
- [ ] Baseline/candidate được đo trong điều kiện có thể so sánh.
- [ ] Ngưỡng performance gate dựa trên SLO và độ biến thiên của môi trường.
- [ ] Operations guide có lệnh capture, phân tích, bảo mật và rollback.
- [ ] Recording và report được lưu đúng nơi, có owner và retention.

## 17. Tổng kết

Quy trình hoàn thiện báo cáo JFR cần bắt đầu bằng workload có thể tái hiện, recording có thời lượng và cấu hình rõ ràng, sau đó lọc event và đọc stack trace trong đúng ngữ cảnh. Báo cáo phải nối dữ liệu JFR với latency, throughput, error rate và metric dependency; ghi rõ điều đã xác nhận và điều vẫn còn là giả thuyết.

Kiểm thử hồi quy cần giữ functional correctness, integration behavior và performance trend thành các lớp riêng. So sánh baseline với candidate trên cùng runtime và workload, dùng SLO làm tiêu chí chấp nhận, còn JFR dùng để giải thích nguyên nhân. Cuối cùng, operations guide phải cho người trực ca biết cách lấy recording, bảo vệ dữ liệu, tìm bottleneck, xác nhận mitigation và rollback.

## Tài liệu tham khảo

- [Oracle Java 21 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html) — event duration, monitor wait, thread park, sleep và I/O.
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) — event JFR cho virtual thread, threshold pinning và công cụ chẩn đoán.
- [Java SE 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html) — start, check, dump và stop JFR recording trong JVM đang chạy.
- [Java SE 21 — jfr command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html) — summary, print, view, metadata và scrub recording.
- [Java SE 21 — JFR API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/module-summary.html) — API ghi và cấu hình event bằng Java.
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) — thay đổi monitor pinning bắt đầu từ JDK 24.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/) — công cụ benchmark vi mô cho JVM.
