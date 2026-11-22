# Safepoint và nhu cầu phối hợp thao tác nội bộ JVM — nền tảng Thread-Local Handshakes (Java 10+)

## 1. Bối cảnh và mục tiêu học tập

Một JVM hiện đại vừa chạy các **Java application threads**, vừa phải thực hiện các **VM operations** như một số pha garbage collection (GC), quản lý code đã biên dịch JIT, kiểm tra stack, cập nhật metadata và những công việc chẩn đoán. Nhiều VM operations cần nhìn thấy trạng thái của các Java threads **ở một điểm đủ an toàn và nhất quán**. Không thể luôn tự ý đọc hoặc sửa stack, references và trạng thái mã máy khi một thread đang chạy tùy ý.

**Safepoint** là một cơ chế giúp HotSpot phối hợp Java threads để các hoạt động nội bộ diễn ra an toàn. **Thread-local handshakes**, được đưa vào **Java 10 theo JEP 312**, mở rộng mô hình đó: nếu công việc chỉ cần một hoặc một nhóm threads, JVM có thể thực hiện callback theo từng thread **mà không nhất thiết đưa cả JVM vào global safepoint**.

Cần phân biệt bốn khái niệm:

- **Global safepoint:** các Java threads liên quan trên toàn JVM được phối hợp để đạt trạng thái safepoint-safe trước khi một thao tác VM đòi hỏi điều kiện toàn cục chạy.
- **Thread-local handshake:** một hoặc nhiều Java threads mục tiêu được yêu cầu tham gia một callback nội bộ ở trạng thái an toàn, tránh global stop khi thao tác cho phép.
- **Safepoint poll/check:** các vị trí/đường chuyển trạng thái trong interpreter hoặc JIT-generated code nơi thread có thể nhận yêu cầu phối hợp.
- **Stop-the-world (STW):** khoảng thời gian các Java application threads bị tạm dừng để VM làm một công việc cần trạng thái toàn cục. Không phải mọi handshake hay mọi hoạt động GC đều là STW.

Safepoint và handshake thuộc **hạ tầng nội bộ HotSpot**, không phải public Java API. Chúng **không đồng nghĩa** với `Thread.sleep()`, `Thread.yield()`, `synchronized` hoặc `LockSupport.park()`.

## 2. Safepoint: trạng thái an toàn, không phải một dòng lệnh Java bất kỳ

Ở safepoint, HotSpot có điều kiện để hiểu **thread frames, object references, metadata và trạng thái thực thi** theo yêu cầu của VM operation đang được tiến hành. Với **global safepoint**, JVM đưa Java threads cần phối hợp về các trạng thái an toàn trước khi tiếp tục công việc VM toàn cục.

Một mô hình thời gian:

~~~text
Java threads đang chạy bình thường
        |
        | VM yêu cầu global safepoint
        v
SYNCHRONIZING
- Thông báo/polling và phân loại trạng thái threads
- Đợi những Java threads còn đang chạy đến trạng thái an toàn
        |
        v
AT SAFEPOINT
- VM thực hiện operation cần trạng thái toàn cục
- Java application threads không tiếp tục tùy ý chạy
        |
        v
LEAVING SAFEPOINT
- Hoàn tất operation, giải phóng điều kiện dừng
        |
        v
Java threads tiếp tục chạy
~~~

Trong tài liệu chẩn đoán HotSpot hiện hành, Oracle còn mô tả VM states như `not at a safepoint`, `synchronizing` và `at safepoint`. Đây là trạng thái **máy ảo**, không phải enum `java.lang.Thread.State`.

### Global safepoint có dừng toàn bộ hệ điều hành không?

**Không.** JVM phối hợp các **Java threads do nó quản lý** chứ không đóng băng mọi OS threads của máy, những chương trình khác hoặc kernel. Một số Java threads có thể ở native code, blocked hoặc waiting và được xem là đã ở trạng thái an toàn theo quy tắc HotSpot; điều đó không bắt buộc tất cả phải tự chạy thêm Java bytecode trước khi VM thực hiện operation.

Những thread đang chạy native/JNI phải tuân theo cơ chế chuyển trạng thái, đặc biệt **trước khi quay lại thực thi Java**, để không làm hỏng điều kiện global safepoint đang có.

## 3. Vì sao JVM phải phối hợp?

Xét đồ thị Java:

~~~java
final class Node {
    Node next;
    byte[] payload = new byte[1024];
}

Node a = new Node();
Node b = new Node();
a.next = b;
~~~

Đây là **mảnh mã minh họa đặt trong một phương thức**, không phải chương trình đầy đủ. Trong khi thread đang sửa `a.next`, VM có thể cần:

1. Xác định object nào reachable từ GC roots và những tham chiếu nào đang nằm trong stack/registers.
2. Xác định nơi nào chứa references để một collector có thể cập nhật nếu object bị di chuyển.
3. Biết frame của phương thức JIT-compiled đang ở trạng thái nào để deoptimization hoặc stack walk an toàn.
4. Đảm bảo thông tin metadata mà VM operations đọc hoặc cập nhật không rơi vào trạng thái bất nhất.
5. Giữ ngữ nghĩa thực thi đúng khi thread chuyển giữa Java, VM và native code.

Ở những điểm an toàn đã xác định, JIT/VM có thể sử dụng metadata mô tả vị trí object references, thường liên quan **oop maps**, để thực hiện phần việc cần thiết.

**Safepoint không phải khóa transaction của ứng dụng.** Nếu hai thread cùng cập nhật một biến Java không có đồng bộ hợp lệ, một safepoint xen giữa **không chữa data race** và không biến phép cập nhật thành atomic.

### Những công việc có thể cần phối hợp JVM

| Nhóm công việc | Nhu cầu phối hợp | Chú ý phạm vi |
| --- | --- | --- |
| Một số pha **GC stop-the-world** | Nhìn thấy roots/references nhất quán và thao tác với heap an toàn | Có thao tác cần global safepoint |
| **Concurrent GC** | Phối hợp với các threads đang cấp phát và sửa references | Không thể nói mọi pha đều STW |
| **Deoptimization/JIT/code maintenance** | Thông tin frame/code đang dùng phải an toàn khi chuyển/điều chỉnh | Có thể dùng nhiều cơ chế, tùy thao tác |
| **Thread stack inspection** | Đọc thông tin thread mục tiêu ở trạng thái thích hợp | Có thể dùng handshake, không luôn global |
| **JVMTI/serviceability** | Truy vấn runtime/threads một cách an toàn | Phụ thuộc công cụ và JDK |
| **Class metadata/VM structures** | Đảm bảo những cấu trúc cần thiết nhất quán | Không phải mọi class loading đều dừng toàn JVM |

**Kết luận:** mỗi VM operation cần phạm vi đồng bộ phù hợp. Một số thật sự cần toàn JVM; một số chỉ cần một thread. Chính sự khác nhau này dẫn đến JEP 312.

## 4. Safepoint polling: thread biết khi nào phải phối hợp bằng cách nào?

HotSpot đặt những **poll/check** tại các vị trí thích hợp trong interpreter, JIT-compiled code và những đường chuyển trạng thái. Tùy JDK/compiler, các vị trí thường liên quan **loop back edges**, **method returns** và những transition points.

Mô hình minh họa:

~~~text
while (running) {
    compute();              Java source
    [VM/compiler safepoint poll]  (không phải cú pháp Java)
}
~~~

**Dòng trong ngoặc vuông là chú thích**, không phải code để chép vào chương trình. Lập trình viên **không phải viết** `safepointPoll()` trong Java.

Khi JVM cần phối hợp, HotSpot có thể kích hoạt trạng thái poll. Thread đang chạy kiểm tra và đi vào đường xử lý safepoint/handshake tại một vị trí hợp lệ. Việc triển khai sử dụng **thread-local polling state** và các cấu trúc runtime phụ thuộc phiên bản, kiến trúc CPU, interpreter/JIT.

### Thread không chạy Java thì sao?

Một Java thread có thể:

- Đang thực thi bytecode trong interpreter.
- Đang chạy compiled Java code.
- Đang chờ monitor, `park` hoặc một sự kiện khác.
- Đang chạy native/JNI code, hoặc chuyển từ native về Java.

HotSpot phân biệt những trạng thái đó khi đánh giá **safepoint-safe**. Một thread đang blocked có thể được tính đã an toàn mà không cần chạy lại loop. Một thread đang native **không mặc nhiên là bị JVM dừng trong mọi lệnh native**, nhưng phải tuân thủ kiểm tra khi quay lại Java.

### Vì sao không dùng Thread.yield để tạo safepoint?

`Thread.yield()` chỉ là một **scheduling hint**. Nó không phải lời gọi yêu cầu global safepoint hoặc handshake. Tương tự, `Thread.sleep()` và `LockSupport.park()` có chức năng chờ/nhường thực thi ở cấp ứng dụng, không phải public API để điều khiển nội bộ safepoint.

## 5. Nhược điểm nếu mọi thao tác đều đòi global safepoint

Giả sử JVM có bốn Java threads:

~~~text
T1: xử lý request A
T2: xử lý request B
T3: chờ queue
T4: tính toán dài

VM cần một thao tác an toàn chỉ liên quan stack của T4.
~~~

Nếu mọi việc đều phải thực hiện bằng **global safepoint**, JVM có thể phải phối hợp cả **T1, T2, T3, T4** trước khi xử lý yêu cầu riêng của T4. Điều này gây overhead và có thể tạo pause không cần thiết cho T1/T2.

**JEP 312 (Java 10)** đưa ra cơ chế thay thế cho các thao tác thích hợp: **thread-local handshake**, cho phép chọn một hoặc nhiều JavaThread mục tiêu mà không buộc tất cả các Java threads cùng tham gia một điểm đồng bộ toàn cục.

Không được hiểu “JEP 312 loại bỏ global safepoints”. Những thao tác có phụ thuộc **toàn heap/toàn JVM** vẫn có thể cần global safepoint.

## 6. Thread-local handshake hoạt động theo nguyên tắc nào?

**Handshake operation** là một **callback nội bộ HotSpot** được thực thi liên quan đến JavaThread trong trạng thái **safepoint-safe**. Tùy tình huống, callback có thể:

- Được **chính JavaThread mục tiêu** chạy khi đi vào đường xử lý an toàn.
- Được **VM thread** thực hiện thay cho JavaThread khi VM xác nhận target đang trong trạng thái blocked/safe phù hợp.

JEP 312 đưa vào **thread-local polling**, cho phép yêu cầu riêng đến những thread mục tiêu. Khi thread hoàn tất phần việc handshake của nó, thread có thể tiếp tục, **không nhất thiết đợi các thread hoàn toàn không liên quan**.

~~~text
GLOBAL SAFEPOINT: cùng điều kiện toàn cục

T1: ==== RUN ==== | STOP | ==== RUN ====
T2: ==== RUN ==== | STOP | ==== RUN ====
T3: ==== RUN ==== | STOP | ==== RUN ====
VM:                [operation]

THREAD-LOCAL HANDSHAKE: chỉ target T2 (sơ đồ nguyên lý)

T1: ================= RUN =============
T2: ==== RUN ==== |callback| === RUN ===
T3: ================= RUN =============
VM:               [target T2]
~~~

**Hai sơ đồ này không biểu diễn chính xác toàn bộ cơ chế locking/scheduling**; chúng thể hiện vì sao phạm vi phối hợp nhỏ hơn có thể cải thiện latency.

### Handshake không có nghĩa zero-pause

Thread đích có thể phải dừng ngắn, phản hồi callback và cập nhật trạng thái. Nó cũng có thể phải đợi đến lúc an toàn. Vì vậy handshake **không cam kết hoàn thành tức thì** và **không thể thay thế global safepoint cho mọi VM operation**.

### Handshake có thể nhắm tới nhiều threads

Tên “thread-local” không giới hạn operation chỉ được xử lý trên đúng một thread. VM có thể yêu cầu callback trên **một tập Java threads**, để mỗi thread xử lý phần việc của nó khi an toàn. Phạm vi và cách đợi phụ thuộc callback/thuật toán cụ thể.

## 7. Bảng so sánh global safepoint và thread-local handshake

| Tiêu chí | Global safepoint | Thread-local handshake |
| --- | --- | --- |
| Phạm vi | Điều kiện phối hợp toàn JVM | Một/một nhóm JavaThreads mục tiêu |
| Mục đích | VM operation cần tính an toàn toàn cục | VM operation có thể xử lý theo thread |
| Thread không liên quan | Có thể bị dừng | Thường có thể tiếp tục |
| Thread mục tiêu | Đạt trạng thái safepoint-safe | Đạt trạng thái safepoint-safe cho callback |
| Các threads có phải dừng cùng lúc không? | Cần một cửa sổ global condition | Không bắt buộc một global barrier duy nhất |
| Có thể gây pause? | Có | Có, cho thread mục tiêu |
| Có từ thời điểm nào? | Có từ trước Java 10 | Hạ tầng được bổ sung từ Java 10 |
| API Java chuẩn để gọi trực tiếp? | Không | Không |
| Là giải pháp thay thế hoàn toàn cho GC STW? | Không áp dụng | Không |

**Điểm then chốt:** Thread-local handshake là **một mức phối hợp mịn hơn**, chứ không phải “safepoint bị xóa bỏ khỏi JVM”.

## 8. Thời gian đến safepoint và độ trễ

Khi một global safepoint được yêu cầu, tổng thời gian có thể chia thành:

1. **Reaching safepoint**: thời gian đưa các Java threads liên quan vào trạng thái an toàn.
2. **At safepoint**: thời gian VM thực hiện operation khi điều kiện safepoint đã đạt.
3. **Leaving safepoint**: thời gian hoàn tất và thả các threads trở lại.

Trên HotSpot hiện hành, `-Xlog:safepoint=info` có thể ghi dạng:

~~~text
Safepoint "G1CollectFull", Time since last: ...,
  Reaching safepoint: ... ns,
  At safepoint: ... ns,
  Leaving safepoint: ... ns,
  Total: ... ns
~~~

Dòng trên được **xuống dòng để dễ đọc** và các dấu ba chấm thay cho thời gian cụ thể. Đây không phải kết quả cố định cho mọi JVM.

### Time To Safepoint (TTSP)

`Reaching safepoint` thường được quan tâm khi phân tích **Time To Safepoint** — thời gian JVM chờ các threads đạt điều kiện an toàn. Nó không nhất thiết bằng thời gian GC operation.

Ví dụ **số giả định**:

~~~text
Reaching safepoint : 40,000,000 ns (40 ms)
At safepoint       :  2,000,000 ns ( 2 ms)
Leaving safepoint  :    100,000 ns ( 0.1 ms)
Total              : 42,100,000 ns (42.1 ms)
~~~

Nếu ứng dụng chỉ tối ưu VM operation mất 2 ms mà bỏ qua 40 ms chờ phối hợp, nó có thể không xử lý đúng nguyên nhân latency.

**Không suy ngay từ TTSP cao rằng ứng dụng deadlock.** Native/JNI transitions, thread scheduling, những threads bận, các đoạn code có đặc tính polling khác nhau và hoạt động VM khác đều có thể ảnh hưởng. Cần phân tích logs tương ứng và các công cụ chẩn đoán.

### JEP 312 có giúp gì cho latency?

Khi chỉ cần xử lý một thread, không phải đợi mọi Java threads cùng vào global safepoint có thể giảm chi phí và số lần ứng dụng phải chịu các pauses toàn cục. Tuy vậy, **không có cam kết thời gian phản hồi cố định** cho mọi handshake.

## 9. Chương trình Java hoàn chỉnh để quan sát một safepoint thật

Bài demo tạo hai platform threads có hành vi khác nhau:

- `busy-worker` liên tục chạy Java code và đọc biến `volatile`.
- `parked-worker` chờ tín hiệu bằng `LockSupport.park()`.
- `main` đợi cả hai khởi động, phát **yêu cầu GC**, sau đó giải phóng threads và `join()`.

**Giới hạn:** demo **không gọi API handshake trực tiếp**. Java SE không công bố một phương thức `Thread.handshake()` hay `Thread.safepoint()`. Ta dùng GC log của HotSpot để **quan sát global safepoint**, sau đó hiểu tại sao JEP 312 hữu ích cho những việc chỉ cần một thread.

Lưu tệp **`SafepointCoordinationDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.LockSupport;

public final class SafepointCoordinationDemo {

    private static volatile boolean running = true;
    private static volatile boolean releaseParked = false;
    private static volatile long checksum;

    public static void main(String[] args)
            throws InterruptedException {

        CountDownLatch started = new CountDownLatch(2);

        Thread busy = new Thread(() -> {
            started.countDown();

            long sum = 0;
            while (running) {
                sum += 3;
                if (sum >= 1_000_000) {
                    sum = 0;
                }
            }
            checksum = sum;
        }, "busy-worker");

        Thread parked = new Thread(() -> {
            started.countDown();
            while (!releaseParked) {
                LockSupport.park();
            }
        }, "parked-worker");

        busy.start();
        parked.start();
        started.await();

        System.out.println("workersStarted=2");
        System.out.println("busyAlive=" + busy.isAlive());
        System.out.println("parkedAlive=" + parked.isAlive());

        // Đây chỉ là yêu cầu GC, không phải lời hứa Full GC.
        System.gc();
        System.out.println("gcRequestReturned=true");

        running = false;
        releaseParked = true;
        LockSupport.unpark(parked);

        busy.join();
        parked.join();
        System.out.println("workersStopped="
                + (!busy.isAlive() && !parked.isAlive()));
    }
}
~~~

**Biên dịch** bằng JDK 17+:

~~~bash
javac SafepointCoordinationDemo.java
~~~

**Chạy có log**, ví dụ HotSpot G1:

~~~bash
java -XX:+UseG1GC -XX:-ExplicitGCInvokesConcurrent -Xms64m -Xmx64m -Xlog:gc=info,safepoint=info SafepointCoordinationDemo
~~~

Với bash/zsh hoặc PowerShell, lệnh được viết trên **một dòng**, không cần ký tự nối dòng.

**Đầu ra phần chương trình (không kể log JVM) đã kiểm thử trên JDK 24:**

~~~text
workersStarted=2
busyAlive=true
parkedAlive=true
gcRequestReturned=true
workersStopped=true
~~~

Chương trình đã chạy thử **cả với các flags trên và không có flags**, năm dòng application output giống nhau.

### Mẫu GC/safepoint log đã quan sát trong bài test JDK 24

~~~text
[info][gc] Using G1
...
GC(0) Pause Full (System.gc()) 3M->1M(64M) ...
[safepoint] Safepoint "G1CollectFull",
  Reaching safepoint: ... ns,
  At safepoint: ... ns,
  Leaving safepoint: ... ns,
  Total: ... ns
~~~

Số MB, thời gian và timestamps **có thể khác** khi chạy trên hệ thống khác. Trong cấu hình này, yêu cầu GC thực tế dẫn đến **G1 Full GC** và safepoint. Tuy nhiên **`System.gc()` không phải cam kết Java SE rằng luôn có Full GC**; ví dụ, flags khác như `-XX:+DisableExplicitGC` hoặc collector khác có thể làm hành vi thay đổi.

### Đọc chính xác năm dòng

1. `workersStarted=2`: `CountDownLatch` xác nhận hai worker đã báo khởi động.
2. `busyAlive=true`: thread tính toán đang còn sống khi main kiểm tra.
3. `parkedAlive=true`: thread thứ hai đang còn sống; nó dùng `park()` để chờ, không nhất thiết phải chạy Java loop liên tục.
4. `gcRequestReturned=true`: lời gọi `System.gc()` đã trả về trong lần chạy này. Không suy ra từ riêng dòng này rằng một Full GC đã xảy ra; cần **GC log** để xác nhận.
5. `workersStopped=true`: `volatile`, `LockSupport.unpark` và `join` giúp main chờ cả hai kết thúc.

**Điểm quan sát quan trọng:** thread đang chạy và thread đang chờ có thể được VM phối hợp theo những cách khác nhau. Điều đó không có nghĩa `park` tự là “handshake call” hay `volatile` tự tạo safepoint.

### Vì sao dùng volatile và vòng lặp khi park?

`running` và `releaseParked` là các biến điều khiển chia sẻ. `volatile` bảo đảm các threads nhìn thấy những cập nhật phù hợp theo Java Memory Model. `LockSupport.park()` có thể trả về giả (*spurious wakeup*), nên dùng vòng `while (!releaseParked)` để tiếp tục đợi nếu chưa được giải phóng.

## 10. Cách bật log safepoint trên JDK hiện đại

**Chỉ log safepoint:**

~~~bash
java -Xlog:safepoint=info -jar app.jar
~~~

**Log GC và safepoint:**

~~~bash
java -Xlog:gc=info,safepoint=info -jar app.jar
~~~

**Kiểm tra những tags được JDK hiện tại hỗ trợ:**

~~~bash
java -Xlog:help
~~~

Trên JDK 24 được thử, danh sách có **`safepoint`** và **`handshake`**. Có thể thử `-Xlog:handshake=debug` để chẩn đoán khi cần, nhưng **không được hứa một chương trình Java nhỏ sẽ in ra mọi handshake callback** hoặc log global safepoint thể hiện đầy đủ số callback.

**Dùng Unified Logging `-Xlog`** thay vì những cách bật safepoint/GC logging đời cũ đã không còn phù hợp với JDK hiện hành.

### Phân biệt log GC và log safepoint

- `-Xlog:gc=info`: báo sự kiện GC, có thể kèm thời gian pause và thông tin heap.
- `-Xlog:safepoint=info`: báo safepoint events, tên VM operation và thời gian điều phối.
- Số lần `Safepoint ...` **không phải** số lần thread-local handshake.
- **Không phải safepoint nào cũng do GC**; các VM operations khác có thể yêu cầu điều kiện safepoint.

Nếu thu thập logs ra file cho production, cần chọn lượng dữ liệu hợp lý và cơ chế rotation. Không bật trace cực chi tiết liên tục khi chưa đánh giá overhead.

## 11. Safepoint và ứng dụng Java: đừng lẫn với synchronization

Ví dụ rủi ro lost update:

~~~java
final class Counter {
    long value;

    void increment() {
        value++;
    }
}
~~~

Khi hai threads gọi `increment()` đồng thời, phép cập nhật không được bảo vệ bởi đồng bộ phù hợp. **Việc JVM đôi lúc có global safepoint không sửa data race đó**.

Một cách dùng primitive Java đúng là:

~~~java
final class SafeCounter {
    private final java.util.concurrent.atomic.AtomicLong value =
            new java.util.concurrent.atomic.AtomicLong();

    void increment() {
        value.incrementAndGet();
    }

    long get() {
        return value.get();
    }
}
~~~

Hai đoạn là **mã minh họa cấp lớp**, không phải hai chương trình có `main`.

| Mục tiêu | Cơ chế |
| --- | --- |
| VM cần stack/heap/code state an toàn | Safepoint/handshake/cơ chế VM phù hợp |
| Java threads cần mutual exclusion | `synchronized` hoặc `Lock` |
| Java threads cần số đếm atomic | `AtomicLong`, `LongAdder` theo nhu cầu |
| Threads cần chờ tín hiệu | `CountDownLatch`, `Condition`, `LockSupport`... |
| Cần transactional updates qua nhiều bản ghi | Database transactions |
| Cần quan sát VM pause | `-Xlog:safepoint`, GC logs/JFR phù hợp |

**Không gọi `System.gc()` để “làm đồng bộ” state của Java threads**, và không nghĩ `Thread.yield()` có thể thay thế `synchronized`.

## 12. Tại sao một thread đang chờ vẫn liên quan tới phối hợp VM?

Một thread `WAITING` hoặc `TIMED_WAITING` theo `Thread.State` có thể đã nhường execution, nhưng JVM vẫn cần biết nó có những stack frames/references nào và cách thread trở lại chạy Java.

Ví dụ:

~~~java
LockSupport.park();
~~~

Đây là **mảnh mã nằm trong một phương thức**. Nó có ý nghĩa **đợi permit**; không phải lệnh “đóng băng VM”. Vì `park()` có thể thức dậy do `unpark()`, interrupt hoặc spurious return, application logic phải kiểm tra lại điều kiện chờ.

Nếu VM cần global safepoint khi một thread đang blocked, có thể phối hợp theo **thread state/transition** mà không buộc thread ấy chạy một câu lệnh safepoint poll ở Java loop ngay lúc đó.

**Không suy từ `Thread.State.WAITING` rằng tất cả điều kiện VM an toàn đã được bảo đảm** trong mọi collector/JVM. Đây là chi tiết VM state; HotSpot tự xác định theo implementation.

## 13. Safepoint polling trong code JIT và vòng lặp

Một vòng lặp tính toán Java có thể tiếp tục chạy rất lâu:

~~~java
while (running) {
    // Xử lý phép tính
}
~~~

HotSpot cần đặt/check cơ chế polling ở những vị trí thích hợp để VM có thể đưa thread đó tới safepoint khi cần. Những vị trí thực tế phụ thuộc interpreter, C1/C2 JIT, kiểu loop, optimizations và CPU.

**Đừng làm ba việc sau:**

1. Tự thêm `Thread.sleep(0)` hoặc `Thread.yield()` vào mọi loop vì nghĩ rằng đó là “cách bật safepoint chuẩn”.
2. Tự diễn giải JIT-compiled code như một chuỗi Java source statements 1-1; HotSpot có thể optimize/chuyển cấu trúc loop.
3. Xem một safepoint poll như đồng bộ nghiệp vụ để kiểm tra dữ liệu shared có đúng hay không.

Những điều lập trình viên **nên** làm: viết loop đúng Java Memory Model (`volatile`, atomics, khóa phù hợp), tránh busy-spin vô ích, và khi thấy pause bất thường thì dùng GC/safepoint logs để tìm nguyên nhân cụ thể.

## 14. Các trường hợp VM operation vẫn cần global safepoint

Dù thread-local handshakes giảm nhu cầu phải dừng mọi thread cho **những công việc có thể thực hiện theo thread**, vẫn có những hoạt động thực sự cần một trạng thái toàn cục.

Ví dụ, một số **stop-the-world GC operations** yêu cầu JVM biết các threads liên quan đã được phối hợp để truy xuất roots/heap, và thực hiện công việc không cho ứng dụng tiếp tục thay đổi heap trong khoảng STW đó.

**Không kết luận sai:**

- “Java 10 bỏ global safepoints”: **sai**.
- “Thread-local handshakes làm G1 Full GC thành concurrent”: **sai**.
- “Mọi GC đều phải global safepoint”: **sai** vì nhiều pha GC có thể concurrent.
- “Mọi hoạt động chẩn đoán đều handshake”: **sai** vì tùy JDK/lệnh.

**Nguyên tắc chọn cơ chế là tính đúng đắn của VM operation**, không chỉ tối ưu số threads bị dừng.

## 15. Một số VM operations phục vụ observability

Các công cụ như **JFR** hoặc **jcmd** có thể giúp quan sát JVM và Java threads. Khi lấy thread dump, stack samples hoặc runtime diagnostics, implementation cần một cách thu thập dữ liệu đúng đắn. Handshakes là hạ tầng có thể hỗ trợ một số thao tác này.

Nhưng việc một công cụ **có thể** dùng handshake **không có nghĩa mọi phiên bản/lệnh của nó luôn dùng handshake**. Ví dụ, những đường thread dump khác nhau có thể có cách phối hợp VM khác nhau theo release.

### Khi điều tra production

1. Ghi lại JDK release, vendor, collector và tham số JVM.
2. Thu thập GC/safepoint logs hoặc JFR nếu được phép.
3. Xác định **op name** và thời gian **Reaching/At/Leaving**.
4. Phân biệt chi phí công việc VM với chi phí ứng dụng như lock contention, I/O, CPU starvation.
5. Không bật quá nhiều diagnostics cấp trace trên production mà không đánh giá overhead.
6. Đo lại sau khi điều chỉnh, so sánh cùng workload/hardware.

Không suy ra thread nào “có lỗi” chỉ từ một dòng thời gian TTSP lớn: cần bằng chứng bổ sung.

## 16. Virtual threads trên Java hiện đại

Từ Java 21, **virtual threads** là một phần tiêu chuẩn của Java. Chúng có thể chạy trên **carrier platform threads** do scheduler quản lý và có khả năng mount/unmount qua cơ chế continuation.

Vì vậy, khi học hạ tầng JVM:

- Không được suy “mỗi virtual thread tương đương một OS thread có polling page riêng giống platform thread”.
- Không được coi virtual threads là cách xóa bỏ mọi safepoint/handshake.
- Khi đo observability trên JDK hiện đại, cần biết công cụ/collector đang diễn giải **virtual threads, carriers và frames** ra sao.

Bài demo dùng **platform threads** để minh họa cơ chế có từ Java 10. Nó không dựa vào preview features hay các chi tiết implementation chưa ổn định của virtual threads.

## 17. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Safepoint là câu lệnh Java có thể gọi.” | Đó là cơ chế VM/interpreter/JIT, không có public `Thread.safepoint()`. |
| “Global safepoint dừng tất cả OS processes.” | Chỉ phối hợp Java threads liên quan trong JVM. |
| “JVM ngắt Java threads đúng ở bất kỳ machine instruction nào.” | Cần các safepoint-safe states/polls/transitions phù hợp. |
| “Thread ngủ/park là global safepoint.” | `park`/`sleep` là hành vi chờ của ứng dụng, khác VM coordination. |
| “Handshake có nghĩa không dừng thread nào.” | Target thread có thể tạm dừng ngắn để callback. |
| “Handshake chỉ thực hiện trên đúng một thread.” | Có thể nhắm đến một tập threads. |
| “Từ Java 10 mọi global safepoints bị loại bỏ.” | Global vẫn cần cho một số VM ops. |
| “Java GC luôn dừng toàn bộ chương trình.” | Nhiều collectors có concurrent phases. |
| “Safepoint tự làm `balance++` atomic.” | Không; dùng atomics/locks cho dữ liệu ứng dụng. |
| “`Thread.yield()` bảo đảm đáp ứng handshake tức thì.” | Không, đó là scheduling hint. |
| “`System.gc()` luôn phải tạo Full GC.” | Chỉ là yêu cầu GC, tùy HotSpot/JVM config. |
| “`-Xlog:safepoint` đếm mọi callback handshake.” | Không phải nhật ký tất cả per-thread callbacks. |
| “GC pause chỉ bằng At safepoint.” | Còn chi phí Reaching/Leaving khi phân tích sự kiện. |
| “TTSP cao luôn nghĩa là deadlock.” | Có nhiều nguyên nhân cần kiểm chứng. |
| “Virtual threads làm safepoints không còn cần thiết.” | JVM vẫn cần phối hợp runtime, nhưng mô hình chi tiết khác. |

## 18. Bài tập tự kiểm tra

### Câu 1 — mục đích safepoint

Tại sao JVM không đọc mọi stack và references tùy ý khi Java threads chạy?

**Đáp án:** Một số VM operations cần trạng thái thread/metadata đủ an toàn và nhất quán. Safepoint là cách phối hợp tạo điều kiện đó.

### Câu 2 — global hay handshake?

VM chỉ cần kiểm tra một trạng thái thread-local của T2. Hạ tầng nào từ Java 10 có thể giúp tránh dừng T1/T3?

**Đáp án:** `Thread-local handshakes` của JEP 312, nếu thao tác phù hợp để xử lý per-thread.

### Câu 3 — handshake có thể pause không?

**Đáp án:** Có. Thread mục tiêu có thể phải đến safe state và thực thi callback, nhưng không nhất thiết làm các threads không liên quan cùng dừng.

### Câu 4 — TTSP

Log cho biết `Reaching safepoint=50ms` và `At safepoint=1ms`. Có nên chỉ điều chỉnh thời gian GC op 1ms không?

**Đáp án:** Không. Cần điều tra 50ms phối hợp thread trước, rồi đánh giá toàn bộ pause theo sự kiện.

### Câu 5 — thread đang chờ

Một Java thread đang ở `LockSupport.park()` có phải tự chạy Java loop liên tục để VM có thể phối hợp không?

**Đáp án:** Không nhất thiết. HotSpot có thể xét blocked/safe thread states và các transition points. `park` không phải public handshake API.

### Câu 6 — application synchronization

Hai threads cập nhật cùng `long value` không có happens-before phù hợp. Có safepoint giữa chừng có chắc ngăn lost update không?

**Đáp án:** Không. Dùng `AtomicLong` hoặc đồng bộ khác theo Java Memory Model.

### Câu 7 — chương trình demo

Vì sao ví dụ `SafepointCoordinationDemo` gọi `started.await()` trước `System.gc()`?

**Đáp án:** Để cả hai worker đã được khởi động theo đồng bộ ứng dụng trước khi main phát yêu cầu GC. Nó không tự tạo một safepoint.

### Câu 8 — chẩn đoán

Log nào giúp đọc thời gian JVM đến global safepoint?

**Đáp án:** `-Xlog:safepoint=info` trên HotSpot hiện hành, thường có các trường Reaching/At/Leaving.

### Câu 9 — bộ thu gom

G1 Full GC STW có mâu thuẫn với việc G1 có concurrent phases không?

**Đáp án:** Không. Các pha khác nhau của collector có chiến lược phối hợp khác nhau; Full GC STW vẫn tồn tại.

### Câu 10 — thread-local polling

Tại sao thread-local polling là nền tảng của JEP 312?

**Đáp án:** VM có thể yêu cầu một hoặc một nhóm JavaThreads đến vị trí an toàn để xử lý callback mà không bắt buộc cả JVM phải đáp ứng một global barrier duy nhất.

### Câu 11 — cờ chẩn đoán

Tại sao không sao chép flags `TraceSafepoint`/`PrintGCApplicationStoppedTime` từ những hướng dẫn cũ?

**Đáp án:** Chúng không phải lựa chọn logging khuyến nghị cho JDK hiện đại; nên dùng `-Xlog` và kiểm tra hỗ trợ bằng `java -Xlog:help`.

### Câu 12 — Java mới

Một ứng dụng dùng virtual threads có còn liên quan safepoints không?

**Đáp án:** Có. HotSpot vẫn phải đảm bảo trạng thái VM an toàn, nhưng mô hình carrier/continuation khiến không thể áp dụng máy móc một polling page cho mỗi virtual thread như platform thread.

## 19. Checklist áp dụng khi chẩn đoán

1. Xác định **JDK và JVM implementation** thực tế.
2. Phân biệt global safepoint với per-thread handshake.
3. Bật `-Xlog:safepoint=info` khi cần đo global safepoints.
4. Kết hợp `-Xlog:gc=info,safepoint=info` để đối chiếu GC.
5. Tìm VM operation name và thời gian Reaching/At/Leaving.
6. Không quy mọi safepoint thành GC hay mọi GC thành global STW.
7. Không đánh đồng TTSP với thời gian toàn bộ VM operation.
8. Khi thời gian Reaching cao, xét native transitions, polling, scheduling, CPU pressure.
9. Không sử dụng `Thread.yield` hoặc `System.gc` như công cụ đồng bộ nghiệp vụ.
10. Dùng locks/atomics/transactions cho trạng thái ứng dụng.
11. Khi cần kiểm tra handshake logs, dùng `java -Xlog:help` của JDK hiện hành.
12. Dùng benchmark và logs cùng workload để đánh giá độ trễ.
13. Với virtual threads, đọc tài liệu đúng release về carriers và stack observability.

## 20. Kết luận và nguồn tham khảo

**Safepoint** là một trong những cơ chế quan trọng để HotSpot có thể phối hợp Java threads thực hiện VM operations cần trạng thái an toàn. **Global safepoint** tạo điều kiện toàn JVM nhưng có thể làm các Java threads dừng và tăng pause latency. **Thread-local handshakes (JEP 312, Java 10)** cho phép điều phối công việc phù hợp theo từng thread, giảm nhu cầu phải dùng global safepoint khi không cần thiết.

Không phải mọi thao tác nội bộ JVM đều dùng safepoint hoặc handshake, không phải mọi GC đều STW, và hạ tầng handshakes **không xóa bỏ** những global safepoints vẫn cần thiết. Trên HotSpot hiện đại, hãy dùng **`-Xlog:safepoint`** cùng GC logs để phân biệt chi phí phối hợp threads với chi phí VM operation, rồi tối ưu dựa trên số liệu.

### Tài liệu chính thức và hiện hành

1. [OpenJDK — JEP 312: Thread-Local Handshakes](https://openjdk.org/jeps/312) — mục tiêu callback theo JavaThread không nhất thiết cần global safepoint, bắt đầu từ Java 10.
2. [OpenJDK HotSpot — `safepoint.cpp`](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/safepoint.cpp) — cách phối hợp safepoint trong HotSpot.
3. [OpenJDK HotSpot — `handshake.cpp`](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/handshake.cpp) — implementation handshakes, chỉ là code nội bộ VM.
4. [Oracle Java SE 26 — java launcher và Unified Logging](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — `-Xlog:safepoint`, `-Xlog:gc,safepoint` và cách dùng tags.
5. [Oracle Java SE 26 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-guide.pdf) — giải thích VM states liên quan safepoint.
6. [OpenJDK JEP 312 implementation review](https://cr.openjdk.org/~rehn/8185640/v10/Coleen-n-Test-Cleanup-4/webrev/src/hotspot/share/runtime/handshake.hpp.sdiff.html) — mô tả callback target thread hoặc VM thread trong trạng thái an toàn.
