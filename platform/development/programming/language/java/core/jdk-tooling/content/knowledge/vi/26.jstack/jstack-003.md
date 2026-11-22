# Thread state trong Java và cách đọc thread dump

**Thread state** mô tả trạng thái của một thread tại một thời điểm trong JVM. Khi ứng dụng chậm, treo, không phản hồi hoặc có dấu hiệu deadlock, thread dump giúp xác định thread đang chạy, chờ monitor, chờ tín hiệu hay chờ hết thời gian. Hai công cụ thường dùng là `jstack` và `jcmd Thread.print`.

Java định nghĩa sáu trạng thái trong `java.lang.Thread.State`: `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING` và `TERMINATED`. Đây là trạng thái ở mức JVM, không phải bản sao trực tiếp trạng thái thread của hệ điều hành.

## 1. Vì sao cần hiểu thread state?

Một ứng dụng Java có thể tạo hàng chục, hàng trăm hoặc hàng nghìn thread. Khi hệ thống gặp sự cố, chỉ nhìn CPU hoặc số lượng thread thường không đủ để tìm nguyên nhân.

Thread state giúp trả lời các câu hỏi:

- Thread đang thực thi code hay đang chờ?
- Thread có bị chặn khi cố vào một vùng `synchronized` không?
- Thread đang chờ một điều kiện, một thread khác hay một khoảng thời gian?
- Thread nào đang giữ monitor mà các thread khác cần?
- Có chu trình chờ khóa tạo thành deadlock không?
- Các thread trong thread pool đang chờ công việc bình thường hay bị mắc kẹt?

Thread dump là ảnh chụp trạng thái tại thời điểm lấy dump. Nó giúp tìm vị trí và quan hệ khóa, nhưng không tự giải thích toàn bộ logic nghiệp vụ. Để xác định xu hướng, thường cần lấy nhiều dump cách nhau vài giây và so sánh stack trace, state, lock owner cùng CPU time.

## 2. Sáu trạng thái của Thread.State

Java định nghĩa đúng sáu trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| `NEW` | Thread đã được tạo nhưng chưa gọi `start()`. |
| `RUNNABLE` | Thread đang thực thi trong JVM hoặc sẵn sàng chạy; có thể đang chờ tài nguyên của hệ điều hành như CPU. |
| `BLOCKED` | Thread đang chờ lấy monitor lock để vào hoặc vào lại một synchronized block/method. |
| `WAITING` | Thread chờ vô thời hạn một thread khác thực hiện một hành động cụ thể. |
| `TIMED_WAITING` | Thread chờ một hành động trong một khoảng thời gian có giới hạn. |
| `TERMINATED` | Phương thức `run()` đã kết thúc bình thường hoặc kết thúc do exception không được xử lý. |

Một thread chỉ ở một trong sáu trạng thái tại một thời điểm. Trạng thái thay đổi theo tiến trình thực thi và các thao tác đồng bộ.

## 3. NEW — thread chưa được khởi chạy

Thread mới tạo có trạng thái `NEW`:

~~~java
Thread worker = new Thread(() -> System.out.println("working"));
System.out.println(worker.getState());
~~~

Output:

~~~text
NEW
~~~

Sau khi gọi:

~~~java
worker.start();
~~~

JVM bắt đầu lập lịch cho thread và nó rời trạng thái `NEW`. Không gọi `run()` trực tiếp nếu mục đích là khởi chạy một thread mới; gọi `run()` như một method thông thường sẽ thực thi trên thread hiện tại.

Thread ở trạng thái `NEW` chưa chạy nên thường không xuất hiện trong thread dump của JVM đang hoạt động. Có thể kiểm tra trạng thái này bằng `Thread.getState()` trong chương trình.

## 4. RUNNABLE — đang chạy hoặc sẵn sàng chạy

`RUNNABLE` là trạng thái của thread đang thực thi trong JVM. Thread có thể đang dùng CPU hoặc đang chờ hệ điều hành cấp tài nguyên để tiếp tục.

Ví dụ:

~~~java
Thread worker = new Thread(() -> {
    while (!Thread.currentThread().isInterrupted()) {
        doSmallUnitOfWork();
    }
});
worker.start();
~~~

Trong thread dump:

~~~text
"worker-1" #31 ... 
   java.lang.Thread.State: RUNNABLE
    at com.acme.Worker.run(Worker.java:18)
~~~

Không nên hiểu `RUNNABLE` đồng nghĩa với việc thread chắc chắn đang tiêu thụ CPU tại đúng thời điểm chụp dump. Trạng thái Java không mô tả đầy đủ trạng thái scheduler, CPU hoặc I/O của hệ điều hành. Khi điều tra CPU cao, hãy so sánh nhiều dump và đối chiếu CPU time hoặc công cụ hệ điều hành.

Một thread `RUNNABLE` liên tục xuất hiện ở cùng một dòng code trong nhiều dump có thể đang chạy vòng lặp nóng, xử lý quá nhiều dữ liệu hoặc quay vòng do contention. Tuy nhiên, một dòng `RUNNABLE` đơn lẻ không đủ kết luận có lỗi.

## 5. BLOCKED — chờ monitor lock

`BLOCKED` có ý nghĩa hẹp: thread đang chờ monitor lock để vào một synchronized block hoặc synchronized method, hoặc để lấy lại monitor sau khi `Object.wait()` kết thúc.

Ví dụ:

~~~java
private static final Object LOCK = new Object();

static void update() {
    synchronized (LOCK) {
        // Critical section
    }
}
~~~

Nếu thread A đã giữ `LOCK` và thread B gọi `update()`, thread B có thể chuyển sang `BLOCKED` cho tới khi A nhả monitor.

Trong thread dump:

~~~text
"blocked-on-monitor" #38 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.acme.Service.update(Service.java:42)
    - waiting to lock <0x000000011f01af90> (a java.lang.Object)
~~~

Dòng `waiting to lock` cho biết object monitor mà thread đang chờ. Tìm thread khác có dòng `locked <cùng địa chỉ>` để xác định thread giữ monitor.

`BLOCKED` không có nghĩa mọi thao tác chờ đều mang trạng thái này. Ví dụ, thread chờ `ReentrantLock` thường được park và có thể xuất hiện là `WAITING` hoặc `TIMED_WAITING`, tùy cách gọi. Không dùng số lượng `BLOCKED` làm đại diện cho mọi loại lock contention.

## 6. WAITING — chờ vô thời hạn

Thread ở trạng thái `WAITING` khi chờ một hành động từ thread khác mà không đặt timeout. Các API phổ biến tạo trạng thái này:

- `Object.wait()` không truyền timeout.
- `Thread.join()` không truyền timeout.
- `LockSupport.park()`.

Ví dụ:

~~~java
synchronized (signal) {
    signal.wait();
}
~~~

Thread sẽ chờ cho tới khi được `notify()`, `notifyAll()`, bị interrupt hoặc điều kiện chờ thay đổi theo cơ chế tương ứng.

Thread dump có thể hiển thị:

~~~text
"waiting-on-object" #39 ...
   java.lang.Thread.State: WAITING (on object monitor)
    at java.lang.Object.wait(...)
    - waiting on <0x000000011f01afa0> (a java.lang.Object)
~~~

Với `LockSupport.park()` hoặc các cấu trúc dựa trên synchronizer, stack có thể cho thấy thread đang park và chờ một synchronizer thay vì chờ object monitor.

Nhiều thread `WAITING` trong thread pool có thể hoàn toàn bình thường: worker đang đợi queue có task. Cần đọc stack trace và biết thread đang chờ điều kiện nào trước khi coi đó là sự cố.

## 7. TIMED_WAITING — chờ có thời hạn

`TIMED_WAITING` tương tự `WAITING` nhưng có thời gian chờ giới hạn. Các API thường gặp:

- `Thread.sleep(timeout)`.
- `Object.wait(timeout)`.
- `Thread.join(timeout)`.
- `LockSupport.parkNanos(timeout)`.
- `LockSupport.parkUntil(deadline)`.

Ví dụ:

~~~java
Thread.sleep(2_000);
~~~

Thread dump:

~~~text
"timer-worker" #40 ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.lang.Thread.sleep(...)
~~~

Một thread đang ngủ theo lịch hoặc đợi timeout thường không phải lỗi. Nếu nhiều thread cùng `TIMED_WAITING` ở một điểm chờ, hãy xác định đó là retry/backoff, timer, polling hay timeout nghiệp vụ.

### WAITING và TIMED_WAITING khác nhau

| WAITING | TIMED_WAITING |
|---|---|
| Không có timeout hữu hạn trong thao tác chờ. | Có thời hạn chờ được chỉ định. |
| Ví dụ `Object.wait()`, `join()`, `park()`. | Ví dụ `sleep()`, `wait(timeout)`, `join(timeout)`. |
| Cần một tín hiệu hoặc hành động khác để tiếp tục, hoặc interrupt. | Có thể tiếp tục khi được báo hiệu, bị interrupt hoặc hết timeout. |

## 8. Những khác biệt dễ nhầm giữa các trạng thái

### BLOCKED không đồng nghĩa với WAITING

- `BLOCKED`: đang cố lấy monitor để vào synchronized block/method.
- `WAITING`: đã gọi một thao tác chờ vô thời hạn, chẳng hạn `Object.wait()` hoặc `LockSupport.park()`.

Một thread chờ `ReentrantLock.lock()` thường không có trạng thái `BLOCKED` vì `ReentrantLock` dựa trên cơ chế park/synchronizer.

### Object.wait() và Thread.sleep() không giống nhau

`Object.wait()` phải được gọi khi thread đang sở hữu monitor của object. Khi chờ, nó nhả monitor đó và sẽ phải lấy lại monitor trước khi tiếp tục sau khi được đánh thức.

`Thread.sleep()` không nhả bất kỳ monitor nào mà thread đang giữ. Vì vậy, thread có thể ở `TIMED_WAITING` nhưng vẫn giữ monitor và khiến thread khác `BLOCKED`.

Ví dụ:

~~~java
synchronized (LOCK) {
    Thread.sleep(5_000);
}
~~~

Trong khoảng ngủ, thread khác muốn vào `synchronized (LOCK)` vẫn phải đợi. Đây là nguyên nhân thường gặp khiến một thread dump cho thấy thread giữ monitor đang `TIMED_WAITING` còn các thread khác `BLOCKED`.

## 9. Vòng đời và chuyển trạng thái

Một luồng điển hình:

1. Tạo đối tượng `Thread` → `NEW`.
2. Gọi `start()` → thread bắt đầu hoạt động và chuyển sang `RUNNABLE`.
3. Chờ monitor → `BLOCKED`.
4. Gọi `wait()` hoặc `park()` → `WAITING`.
5. Gọi `sleep()` hoặc thao tác chờ có timeout → `TIMED_WAITING`.
6. Tiếp tục thực thi → thường trở lại `RUNNABLE`.
7. `run()` kết thúc → `TERMINATED`.

Không phải mọi thread đều đi qua tất cả trạng thái. Trạng thái có thể thay đổi rất nhanh; một thread có thể được đánh thức và chạy tiếp trước khi công cụ chụp dump.

`Thread.getState()` được thiết kế cho mục đích giám sát. Không dùng kết quả của nó để làm cơ chế đồng bộ hoặc quyết định rằng một thread chắc chắn sẽ còn ở trạng thái đó sau khi kiểm tra.

## 10. Thread dump là gì?

Thread dump là bản ghi stack trace và thông tin trạng thái của các thread tại thời điểm lấy mẫu. Nó thường gồm:

- Tên thread.
- Java thread ID và native thread ID nếu có.
- Thông tin daemon và priority.
- Trạng thái Java, ví dụ `RUNNABLE` hoặc `BLOCKED`.
- Stack trace với class, method và số dòng nếu có.
- Thông tin monitor/synchronizer khi bật chế độ hiển thị lock.
- Thông tin bổ sung phụ thuộc JDK và công cụ.

Một thread dump không phải bản ghi lịch sử. Nó không cho biết đầy đủ thread đã ở trạng thái hiện tại bao lâu hoặc trạng thái trước đó là gì, trừ khi công cụ bổ sung các chỉ số thời gian. Để phân biệt chờ bình thường với sự cố, hãy so sánh các dump liên tiếp.

## 11. Lấy thread dump bằng jstack

`jstack` in stack trace của các Java thread trong một process Java.

Tìm PID bằng:

~~~bash
jcmd -l
~~~

Hoặc:

~~~bash
jps -l
~~~

Lấy dump:

~~~bash
jstack <pid>
~~~

Dùng `-l` để in thêm thông tin lock:

~~~bash
jstack -l <pid>
~~~

Trong Azul OpenJDK 24.0.2 đã kiểm chứng, `jstack -h` còn hiển thị `-e` để in thông tin thread mở rộng:

~~~bash
jstack -e <pid>
~~~

Tùy chọn `-e` không xuất hiện trong trang man Oracle JDK 24 đã tham khảo; hãy kiểm tra `jstack -h` của đúng vendor/JDK đang dùng trước khi đưa nó vào script.

`jstack` được Oracle đánh dấu experimental và unsupported; công cụ có thể thay đổi hoặc không còn trong bản JDK tương lai. Với workflow chẩn đoán mới, ưu tiên `jcmd Thread.print`.

## 12. Lấy thread dump bằng jcmd

`jcmd` gửi diagnostic command tới JVM đang chạy. Liệt kê JVM local:

~~~bash
jcmd -l
~~~

Xem các command mà JVM hỗ trợ:

~~~bash
jcmd <pid> help
~~~

In thread dump:

~~~bash
jcmd <pid> Thread.print
~~~

Thêm thông tin lock:

~~~bash
jcmd <pid> Thread.print -l
~~~

Trong JDK 24.0.2 đã kiểm chứng, `Thread.print` còn hỗ trợ `-e` để in thông tin mở rộng:

~~~bash
jcmd <pid> Thread.print -e
~~~

`jcmd` là lựa chọn nên ưu tiên trong quy trình chẩn đoán hiện đại. Danh sách command và option phụ thuộc JVM đích, vì vậy hãy chạy `jcmd <pid> help Thread.print` trên đúng process.

## 13. Lưu thread dump thành file plain hoặc JSON

JDK 24.0.2 cung cấp diagnostic command `Thread.dump_to_file` để ghi thread dump ra file.

Ghi định dạng plain:

~~~bash
jcmd <pid> Thread.dump_to_file -format=plain threads.txt
~~~

Ghi định dạng JSON:

~~~bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
~~~

Nếu file đã tồn tại, có thể dùng `-overwrite` khi chủ động cho phép ghi đè:

~~~bash
jcmd <pid> Thread.dump_to_file -overwrite -format=json threads.json
~~~

Trong lần kiểm thử, cả hai dạng plain và JSON đều được tạo và đọc thành công. JSON phù hợp khi muốn xử lý dữ liệu bằng công cụ tự động; plain phù hợp để đọc nhanh bằng editor hoặc tìm kiếm văn bản.

Thread dump có thể chứa tên class, đường dẫn, thông tin request hoặc dữ liệu nội bộ trong stack. Hãy giới hạn quyền truy cập file và rà soát trước khi chia sẻ.

## 14. Cách đọc một đoạn thread dump

Ví dụ rút gọn:

~~~text
"blocked-on-monitor" #38 ... daemon prio=5 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.acme.Service.update(Service.java:42)
    - waiting to lock <0x000000011f01af90> (a java.lang.Object)
~~~

Ý nghĩa:

- `"blocked-on-monitor"` là tên thread.
- `#38` là Java thread number trong dump.
- `daemon` cho biết thread là daemon.
- `java.lang.Thread.State: BLOCKED` là trạng thái Java.
- `Service.java:42` cho biết vị trí code đang chờ.
- `waiting to lock <...>` là monitor mà thread muốn lấy.

Tìm thread khác có dòng:

~~~text
- locked <0x000000011f01af90> (a java.lang.Object)
~~~

Thread đó đang giữ monitor cùng địa chỉ. So sánh stack trace của cả thread chờ và thread giữ khóa để xác định nguyên nhân.

Với synchronizer dựa trên park, có thể gặp dòng:

~~~text
- parking to wait for <0x...> (a java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject)
~~~

Địa chỉ và class cụ thể phụ thuộc lock implementation. Hãy đọc tên thread, trạng thái, stack trace và thông tin lock cùng nhau.

## 15. Phát hiện deadlock bằng thread dump

Deadlock xảy ra khi các thread tạo thành một chu trình chờ tài nguyên mà không thread nào có thể tiếp tục. Ví dụ:

- Thread A giữ lock X và chờ lock Y.
- Thread B giữ lock Y và chờ lock X.

Trong code, tình huống có thể xảy ra khi hai luồng lấy cùng một cặp lock theo thứ tự ngược nhau:

~~~java
synchronized (lockA) {
    synchronized (lockB) {
        // work
    }
}
~~~

Trong thread dump, dấu hiệu thường thấy là nhiều thread `BLOCKED`, mỗi thread đang chờ một monitor do thread khác giữ.

Khi chạy `jstack -l`, JDK 24.0.2 trong lần kiểm thử đã in phần báo cáo:

~~~text
Found one Java-level deadlock:
=============================
"deadlock-one":
  waiting to lock monitor ..., which is held by "deadlock-two"
"deadlock-two":
  waiting to lock monitor ..., which is held by "deadlock-one"
Found 1 deadlock.
~~~

Đây là bằng chứng của chu trình monitor cụ thể. Không phải mọi thread `BLOCKED` đều là deadlock; một thread có thể chỉ đang chờ lock trong thời gian ngắn. Ngược lại, deadlock nghiệp vụ hoặc deadlock liên quan tài nguyên ngoài JVM có thể không được bộ phát hiện Java-level nhận diện.

Cách phòng tránh:

- Lấy nhiều lock theo cùng một thứ tự ở mọi nơi.
- Giữ vùng synchronized ngắn.
- Tránh gọi code bên ngoài, I/O hoặc callback khi đang giữ monitor.
- Ưu tiên cấu trúc concurrency cấp cao như executor, concurrent collections và lock có timeout khi phù hợp.
- Thiết kế timeout, cancellation và quy trình phục hồi cho thao tác chờ lâu.

## 16. Phân tích các mẫu state thường gặp

| Mẫu quan sát | Khả năng cần kiểm tra |
|---|---|
| Một hoặc vài thread `RUNNABLE` có cùng stack trong nhiều dump và CPU cao | Vòng lặp nóng, tính toán quá nhiều, retry không có backoff hoặc contention dạng spin. |
| Nhiều thread `BLOCKED` chờ cùng một monitor | Lock contention; tìm thread giữ monitor và vị trí code đang giữ khóa. |
| Hai hay nhiều thread `BLOCKED` tạo chu trình owner/waiter | Có thể deadlock; kiểm tra phần deadlock report và địa chỉ monitor. |
| Nhiều thread `WAITING` trong executor | Có thể là worker idle đang đợi task; kiểm tra queue, stack và số lượng task. |
| Nhiều thread `TIMED_WAITING` trong sleep | Có thể là scheduler, retry/backoff hoặc polling; xác minh thời hạn và tần suất. |
| Thread chờ `Object.wait()` lâu | Xác định thread nào phải gọi notify/notifyAll và điều kiện đánh thức có thể bị bỏ lỡ không. |
| Thread park trong lock/condition | Kiểm tra synchronizer, điều kiện, queue và thread chịu trách nhiệm unpark/signal. |

Một dump đơn lẻ thường không đủ để kết luận. Nếu một thread giữ nguyên stack và state trong nhiều dump liên tiếp, khả năng bị mắc kẹt cao hơn. Đối chiếu thêm CPU, request latency, queue depth, GC và log ứng dụng để xác định tác động thực tế.

## 17. Giới hạn và lưu ý khi dùng thread state

- Trạng thái là ảnh chụp tại một thời điểm; thread có thể đổi trạng thái ngay sau đó.
- Sáu trạng thái của Java không phản ánh đầy đủ trạng thái OS thread.
- `RUNNABLE` không đồng nghĩa CPU luôn cao.
- `BLOCKED` chỉ mô tả chờ monitor, không bao gồm mọi dạng lock contention.
- `WAITING` và `TIMED_WAITING` có thể là hành vi bình thường của thread pool, timer hoặc scheduler.
- `NEW` và `TERMINATED` thường không xuất hiện trong dump của các thread đang hoạt động.
- Thread dump không thay thế profiler, JFR, log, metrics hoặc phân tích heap.
- `jstack` là công cụ experimental/unsupported trong tài liệu JDK 24; ưu tiên `jcmd` cho quy trình mới.
- `jcmd` phải chạy trên cùng máy và cùng effective user/group đã khởi chạy JVM đích. Trong container, cần dùng đúng PID namespace; `jcmd -l` không liệt kê JVM nằm trong process Docker riêng.
- Dump có thể chứa thông tin nội bộ; bảo vệ file và giới hạn người được phép đọc.

## 18. Ví dụ hoàn chỉnh: tạo các thread state để kiểm tra

Ví dụ Java 17+ dưới đây tạo thread ở các trạng thái khác nhau để quan sát trong thread dump:

- `NEW`: thread được tạo nhưng chưa start.
- `TERMINATED`: thread chạy xong và đã join.
- `BLOCKED`: thread chờ monitor do thread khác giữ.
- `WAITING`: thread gọi `Object.wait()` không timeout.
- `TIMED_WAITING`: thread gọi `Thread.sleep()`.
- `RUNNABLE`: thread chạy vòng lặp có `Thread.yield()`.

Tạo tệp `src/com/acme/ThreadStateDemo.java`:

~~~java
package com.acme;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class ThreadStateDemo {
    private static final Object LOCK = new Object();
    private static final Object WAIT_MONITOR = new Object();
    private static volatile boolean keepRunning = true;

    private static void awaitState(Thread thread, Thread.State expected)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (thread.getState() != expected && System.nanoTime() < deadline) {
            Thread.sleep(10);
        }
        if (thread.getState() != expected) {
            throw new IllegalStateException(thread.getName() + " expected "
                    + expected + " but was " + thread.getState());
        }
    }

    public static void main(String[] args) throws Exception {
        Thread neverStarted = new Thread(() -> { }, "never-started");
        Thread alreadyFinished = new Thread(() -> { }, "already-finished");
        alreadyFinished.start();
        alreadyFinished.join();

        CountDownLatch lockHeld = new CountDownLatch(1);
        Thread holder = new Thread(() -> {
            synchronized (LOCK) {
                lockHeld.countDown();
                try {
                    Thread.sleep(30_000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "monitor-holder");
        holder.setDaemon(true);
        holder.start();
        if (!lockHeld.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("monitor was not acquired");
        }

        Thread blocked = new Thread(() -> {
            synchronized (LOCK) {
                System.out.println("blocked thread acquired monitor");
            }
        }, "blocked-on-monitor");
        blocked.setDaemon(true);
        blocked.start();
        awaitState(blocked, Thread.State.BLOCKED);

        Thread waiting = new Thread(() -> {
            synchronized (WAIT_MONITOR) {
                try {
                    WAIT_MONITOR.wait();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "waiting-on-object");
        waiting.setDaemon(true);
        waiting.start();
        awaitState(waiting, Thread.State.WAITING);

        Thread timed = new Thread(() -> {
            try {
                Thread.sleep(30_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "timed-sleep");
        timed.setDaemon(true);
        timed.start();
        awaitState(timed, Thread.State.TIMED_WAITING);

        Thread runnable = new Thread(() -> {
            while (keepRunning) {
                Thread.yield();
            }
        }, "cpu-runnable");
        runnable.setDaemon(true);
        runnable.start();
        awaitState(runnable, Thread.State.RUNNABLE);

        System.out.println("NEW=" + neverStarted.getState());
        System.out.println("TERMINATED=" + alreadyFinished.getState());
        System.out.println("READY");
        Thread.sleep(20_000);
        keepRunning = false;
    }
}
~~~

### Bước 1: biên dịch

Từ thư mục gốc dự án:

~~~bash
javac --release 17 -d out src/com/acme/ThreadStateDemo.java
~~~

### Bước 2: chạy chương trình

~~~bash
java -cp out com.acme.ThreadStateDemo
~~~

Stdout chính xác:

~~~text
NEW=NEW
TERMINATED=TERMINATED
READY
~~~

Chương trình giữ JVM hoạt động khoảng 20 giây để có thời gian chụp dump. Mở terminal thứ hai và tìm PID:

~~~bash
jcmd -l
~~~

### Bước 3: lấy dump

~~~bash
jstack -l <pid>
~~~

Hoặc:

~~~bash
jcmd <pid> Thread.print -l
~~~

Trong output cần tìm các tên:

| Thread name | State mong đợi |
|---|---|
| `monitor-holder` | `TIMED_WAITING` |
| `blocked-on-monitor` | `BLOCKED` |
| `waiting-on-object` | `WAITING` |
| `timed-sleep` | `TIMED_WAITING` |
| `cpu-runnable` | `RUNNABLE` |

`monitor-holder` ngủ trong khi vẫn ở bên trong `synchronized (LOCK)`, vì vậy nó giữ monitor. `blocked-on-monitor` muốn lấy cùng monitor nên ở trạng thái `BLOCKED`. `waiting-on-object` chờ trên monitor khác và nhả monitor đó trong thời gian `wait()`. Ví dụ minh họa vì sao chỉ nhìn tên state mà không đọc stack và lock details có thể dẫn tới kết luận sai.

Vòng lặp `Thread.yield()` chỉ phục vụ việc tạo một thread `RUNNABLE` để chụp dump. Không dùng vòng lặp bận kiểu này thay cho cơ chế chờ hoặc đồng bộ trong ứng dụng thực tế.

## 19. Quy trình chẩn đoán khuyến nghị

Khi ứng dụng chậm hoặc có dấu hiệu treo:

1. Tìm đúng JVM bằng `jcmd -l` hoặc `jps -l`.
2. Lấy thread dump đầu tiên bằng `jcmd <pid> Thread.print -l`.
3. Lặp lại thêm hai hoặc ba lần, cách nhau vài giây nếu sự cố còn tồn tại.
4. So sánh state, stack trace, lock address và thread owner qua các dump.
5. Kiểm tra thread `RUNNABLE` có CPU cao hay lặp ở cùng stack không.
6. Với `BLOCKED`, tìm thread giữ monitor và chu trình chờ khóa.
7. Với `WAITING`/`TIMED_WAITING`, xác định điều kiện, timeout và thread chịu trách nhiệm đánh thức.
8. Dùng deadlock report nếu có; xác minh từng owner/waiter trước khi kết luận.
9. Đối chiếu metrics, logs, CPU, GC và request latency.
10. Lưu dump ở nơi có kiểm soát truy cập và xóa theo chính sách lưu trữ.

Thread state giúp hiểu thread đang làm gì trong JVM, còn thread dump cung cấp stack trace và thông tin khóa để truy ra nguyên nhân. Hãy phân biệt đúng sáu trạng thái, hiểu sự khác nhau giữa monitor contention và các dạng waiting, rồi dùng nhiều dump cùng dữ liệu runtime để xác định vấn đề. Trong JDK hiện đại, `jcmd Thread.print` là lựa chọn ưu tiên cho việc thu thập thread dump; `jstack` vẫn hữu ích khi cần công cụ quen thuộc hoặc kiểm tra nhanh trên môi trường hỗ trợ.

## 20. Tài liệu tham khảo

- Oracle JDK 24 — [Thread.State API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Thread.State.html).
- Oracle JDK 24 — [The jstack Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstack.html).
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html).
- Oracle JDK 24 — [Troubleshooting Guide](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf).
