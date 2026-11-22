# Lấy thread dump và nhận diện luồng bị chặn, chờ hoặc tranh chấp tài nguyên

## 1. Thread dump giúp trả lời câu hỏi gì?

Khi ứng dụng Spring Boot vẫn chạy nhưng yêu cầu phản hồi chậm hoặc không hoàn tất, cần biết các luồng đang thực hiện đoạn mã nào và đang đợi điều gì. **Thread dump** là bản chụp thông tin luồng của một JVM tại thời điểm thu thập: trạng thái, ngăn xếp lời gọi và thông tin khóa mà công cụ quan sát được.

Hãy hình dung một quầy xử lý có nhiều nhân viên:

- Có người đang làm việc.
- Có người chưa có việc nên đang đợi.
- Có người có việc nhưng phải đợi người khác nhả một tài nguyên.
- Có thể có hai người giữ hai tài nguyên khác nhau và cùng đợi tài nguyên của nhau.

Chỉ đếm số người đang đợi không đủ tìm nguyên nhân. Với luồng Java cũng vậy: cần ghép **trạng thái → vị trí trong mã → điều kiện hoặc tài nguyên đang chờ → luồng giữ tài nguyên → khả năng tiến triển**.

Trong nhóm kiến thức “Log và bộ nhớ”, thread dump bổ sung bằng chứng về thực thi đồng thời. Log kể lại các sự kiện đã ghi; thread dump cho thấy vị trí thực thi đang được quan sát. Nó không phải bản sao toàn bộ đối tượng trên heap và không tự chứng minh có rò rỉ bộ nhớ.

Sau bài này, người học có thể lấy bản dump qua Actuator, phân biệt chờ bình thường với tranh chấp khóa, lần theo luồng giữ khóa và xây dựng giả thuyết có thể kiểm chứng. Bài dùng Spring Boot 3.3.x; ví dụ Java độc lập tương thích Java 17+, có lưu ý riêng cho JDK 21.

## 2. Lấy thread dump từ Spring Boot Actuator

### 2.1. Điều kiện và cấu hình cho môi trường thực hành

Ứng dụng đã có một web starter phù hợp, chẳng hạn Spring MVC, và phụ thuộc Actuator. Trong dự án Gradle đã cấu hình Spring Boot cùng quản lý phiên bản phụ thuộc, thêm đoạn sau vào khối `dependencies` hiện có:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

Đây là phần bổ sung phụ thuộc cho một ứng dụng có sẵn, không phải toàn bộ dự án Spring Boot.

Với Boot 3.3, bật một endpoint và cho phép truy cập endpoint qua HTTP là hai việc khác nhau. Mặc định chỉ `health` được công bố qua HTTP. Cấu hình thực hành sau chỉ công bố `health` và `threaddump`; `exclude` nếu có vẫn được ưu tiên hơn `include`. Nếu Spring Security hiện diện, việc công bố endpoint không thay thế quy tắc xác thực/phân quyền. [Tài liệu endpoint Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Ghép vào cấu hình dành cho môi trường thực hành, tránh tạo hai khóa YAML `management` trùng nhau:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: "health,threaddump"
  endpoint:
    threaddump:
      enabled: true
```

Cổng quản trị riêng ở `8081` và địa chỉ loopback giúp thực hành từ cùng máy. `management.server.address` được dùng cùng cổng quản trị tách biệt; đường dẫn mặc định là `/actuator`. Nếu dự án đã đổi base path hoặc ánh xạ đường dẫn endpoint, dùng địa chỉ hiệu lực của dự án. Trong container, `127.0.0.1` thuộc không gian mạng của container; một lệnh từ máy chủ bên ngoài có thể không truy cập được. [Cấu hình HTTP quản trị Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

Bản dump có thể lộ tên lớp, cấu trúc hệ thống và vị trí thực thi. Với môi trường dùng chung, dùng cơ chế truy cập quản trị đã được phê duyệt và bảo vệ cả tệp dump; không công bố endpoint này tùy ý ra Internet.

### 2.2. Chọn JSON hoặc văn bản

Endpoint nhận yêu cầu `GET`. Dùng `Accept: application/json` để xử lý có cấu trúc; dùng `Accept: text/plain` để đọc ngăn xếp trực tiếp. JSON có danh sách `threads`; dữ liệu thực tế phụ thuộc JVM và thời điểm chụp. [API threaddump Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/threaddump.html).

Trong PowerShell, gọi `curl.exe` để dùng đúng chương trình curl:

```powershell
curl.exe --fail --silent --show-error --connect-timeout 2 --max-time 15 -H "Accept: application/json" -o threads.json "http://127.0.0.1:8081/actuator/threaddump"

curl.exe --fail --silent --show-error --connect-timeout 2 --max-time 15 -H "Accept: text/plain" -o threads.txt "http://127.0.0.1:8081/actuator/threaddump"
```

Hai lệnh lưu hai bản chụp ở hai thời điểm khác nhau, không phải hai cách tuần tự hóa của cùng một lần chụp. Trên shell Unix, dùng `curl` với các đối số tương ứng.

Các lệnh giả định truy cập nội bộ đã được cho phép. Nếu dùng HTTP Basic, có thể thêm `--user operator` để curl hỏi mật khẩu; tên tài khoản phải là tài khoản quản trị thực tế. Với cơ chế xác thực khác, dùng cách của hệ thống. Không ghi mật khẩu hoặc token vào bài học, tên tệp hay lịch sử lệnh dùng chung.

Thành công thường nhận HTTP `200` và nội dung dump; không có một stdout cố định cho ứng dụng thật. `--fail` làm curl trả mã lỗi khi HTTP lỗi, nên cần kiểm tra mã thoát trước khi dùng tệp.

### 2.3. Lấy nhiều mẫu khi sự cố đang diễn ra

Một ảnh chụp không cho biết luồng đã ở vị trí đó bao lâu. Có thể lấy ba mẫu cách nhau khoảng ba giây trên **cùng một tiến trình/instance**. Đây là lựa chọn thực hành, không phải khoảng lấy mẫu bắt buộc.

```powershell
$baseUri = "http://127.0.0.1:8081"
for ($sample = 1; $sample -le 3; $sample++) {
    $capturedAt = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ")
    $outputFile = "threads-$sample-$capturedAt.json"
    curl.exe --fail --silent --show-error --connect-timeout 2 --max-time 15 -H "Accept: application/json" -o $outputFile "$baseUri/actuator/threaddump"
    if ($LASTEXITCODE -ne 0) {
        throw "Thu thap thread dump that bai: $outputFile"
    }
    if ($sample -lt 3) {
        Start-Sleep -Seconds 3
    }
}
```

Với ứng dụng nhiều bản sao, cố định đích đến một instance; gọi liên tiếp qua bộ cân bằng tải có thể lấy ba JVM khác nhau. Ghi kèm thời gian, instance, phiên bản triển khai, hiện tượng chậm và tải đang có. Nếu tiến trình đã khởi động lại, không nối chuỗi thread ID giữa hai lần chạy.

Không lấy dump dồn dập trong vòng lặp không nghỉ. Chi phí phụ thuộc số luồng và công cụ; chỉ lấy đủ mẫu để kiểm tra giả thuyết.

## 3. Phân biệt các trạng thái trước khi kết luận

`Thread.State` mô tả trạng thái trong JVM, không đồng nhất với trạng thái luồng của hệ điều hành:

| Trạng thái | Ý nghĩa cần nhớ |
| --- | --- |
| `NEW` | Chưa gọi `start()`. |
| `RUNNABLE` | Có thể thực thi; không bảo đảm đang dùng CPU. |
| `BLOCKED` | Đợi lấy monitor của `synchronized`. |
| `WAITING` | Chờ không đặt thời hạn, như `wait()`, `join()`, `park()`. |
| `TIMED_WAITING` | Chờ có thời hạn, như `sleep()` hoặc `parkNanos()`. |
| `TERMINATED` | Đã kết thúc. |

Một dump các luồng đang sống thường không có `NEW` hoặc `TERMINATED`. Chờ vào `synchronized` và chờ điều kiện là hai cơ chế khác nhau. [Định nghĩa Thread.State trên Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html).

**“Bị chặn” trong lời nói thông thường rộng hơn hằng `BLOCKED`.** Trong ví dụ ở phần 6, luồng chờ `ReentrantLock` ở `WAITING` dù vẫn đang tranh chấp khóa. Ngược lại, luồng chờ hàng đợi rỗng cũng ở `WAITING` nhưng có thể hoàn toàn bình thường.

Một luồng `RUNNABLE` xuất hiện trong hàm đọc socket hoặc hàm native cũng chưa đủ chứng minh nó đang tính toán liên tục. Muốn kết luận dùng CPU cao, cần đối chiếu CPU của tiến trình/luồng hoặc bản ghi JFR/profiler đúng thời gian.

### Chờ có nhả khóa hay không?

`Object.wait()` nhả monitor của chính đối tượng được gọi `wait` và phải lấy lại monitor trước khi trở về. Nó không tự nhả tất cả các khóa khác mà luồng đang giữ. Vì vậy luồng có thể chuyển sang `BLOCKED` khi đang lấy lại monitor sau khi được đánh thức. Luôn kiểm tra điều kiện trong vòng lặp khi sử dụng `wait`. [Hợp đồng Object.wait](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#wait()).

Trong thí nghiệm bên dưới, `CountDownLatch.await()` bên trong một khối `synchronized` không nhả monitor bao ngoài. Quan sát `monitor-owner` ở `WAITING` vẫn thấy nó giữ monitor mà `monitor-contender` cần. Đây là lý do không thể suy luận “đang chờ nên không giữ tài nguyên nào”.

## 4. Đọc một luồng: trạng thái, ngăn xếp và quan hệ giữ khóa

### 4.1. Những thông tin cần ghép với nhau

| Thông tin | Cách sử dụng |
| --- | --- |
| `threadId`, `threadName` | Nhận diện luồng trong lần chạy đang xét. |
| `threadState` | Điểm bắt đầu phân loại. |
| `stackTrace` | Tìm thao tác chờ và vị trí mã ứng dụng dẫn tới thao tác ấy. |
| `lockInfo`, `lockName` | Đối tượng khóa hoặc đối tượng mà luồng đang đợi, nếu có. |
| `lockOwnerId`, `lockOwnerName` | Lần sang luồng giữ khóa khi thông tin khả dụng. |
| `lockedMonitors` | Monitor mà luồng đang giữ. |
| `lockedSynchronizers` | Bộ đồng bộ có chủ sở hữu mà luồng đang giữ, như khóa của `ReentrantLock`. |

Thông tin này phục vụ quan sát, không dùng làm cơ chế điều phối luồng. Chủ sở hữu có thể không xác định được; `lockOwnerId = -1` hoặc thiếu tên chủ sở hữu không chứng minh hệ thống không có chờ tài nguyên. [ThreadInfo trên Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html).

Đọc ngăn xếp từ frame trên cùng để thấy vị trí thực thi, sau đó lần xuống frame ứng dụng để hiểu vì sao đi đến đó. Ví dụ, chỉ thấy `Unsafe.park` chưa cho biết đang chờ khóa, chờ hàng đợi hay chờ latch; phải xem các frame gọi nó.

### 4.2. Ví dụ lần từ người chờ sang người giữ

JSON dưới đây là **mô hình rút gọn để đọc quan hệ**, không phải phản hồi đầy đủ. ID và mã nhận diện khóa được chọn để minh họa; các trường khác được lược bỏ.

```json
{
  "threads": [
    {
      "threadId": 31,
      "threadName": "monitor-owner",
      "threadState": "WAITING",
      "stackTrace": [
        {
          "className": "java.util.concurrent.CountDownLatch",
          "methodName": "await"
        }
      ],
      "lockedMonitors": [
        {
          "className": "java.lang.Object",
          "identityHashCode": 305441741
        }
      ]
    },
    {
      "threadId": 32,
      "threadName": "monitor-contender",
      "threadState": "BLOCKED",
      "lockOwnerId": 31,
      "lockOwnerName": "monitor-owner",
      "lockInfo": {
        "className": "java.lang.Object",
        "identityHashCode": 305441741
      }
    }
  ]
}
```

Cách đọc:

1. `monitor-contender` đợi vào monitor, có `lockOwnerId = 31`.
2. Tìm luồng `31` trong cùng mẫu: đó là `monitor-owner`.
3. Đối chiếu khóa đang chờ với danh sách monitor mà chủ sở hữu đang giữ.
4. Chủ sở hữu đang chờ `CountDownLatch.await`, vì vậy cần tìm đoạn mã hoặc sự kiện sẽ mở latch.
5. Chưa có bằng chứng vòng chờ. Tại đây mới thấy một cạnh phụ thuộc.

Có thể ghi quan hệ bằng văn bản:

```text
monitor-contender
    -> đợi monitor M
    -> monitor-owner đang giữ M
    -> monitor-owner đợi latch được mở
```

Tên luồng có thể trùng; ưu tiên ID trong cùng JVM và cùng lần chụp. Mã nhận diện khóa trong JSON và địa chỉ hiển thị của công cụ văn bản không phải số đo dung lượng bộ nhớ. Không so sánh chúng như một định danh toàn cục giữa các JVM.

### 4.3. Đọc số lần và thời gian chờ đúng nghĩa

`blockedCount` liên quan các lần đợi vào/lấy lại monitor; `blockedTime` là thời gian tích lũy tương ứng khi chức năng theo dõi tranh chấp được bật. `waitedTime` cũng là số tích lũy, không phải tuổi của lần chờ hiện tại. Giá trị `-1` ở các trường thời gian có thể cho biết chức năng theo dõi đang tắt, không phải “âm một mili giây” hoặc “không từng chờ”. Bật lại chức năng theo dõi có thể đặt lại thống kê thời gian. [Thống kê ThreadInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html#getBlockedTime()).

Không xem `blockedCount = 500` là 500 luồng đang chặn một tài nguyên. Không dùng riêng `blockedTime` để đo thời gian xếp hàng của mọi kiểu khóa; phần đợi `ReentrantLock` không đồng nhất với trạng thái monitor `BLOCKED`.

## 5. Nhận diện các mẫu thường gặp trong ứng dụng

| Mẫu quan sát | Giả thuyết ban đầu | Bằng chứng cần bổ sung |
| --- | --- | --- |
| Nhiều `BLOCKED` cùng trỏ tới một chủ sở hữu | Điểm nghẽn ở một monitor dùng chung | Chủ sở hữu làm gì, phạm vi khóa, nhiều mẫu có lặp lại không. |
| `WAITING` qua `ReentrantLock.lock` | Tranh chấp khóa tường minh | Luồng giữ khóa và `lockedSynchronizers`. |
| Worker đợi `BlockingQueue.take` khi không có việc | Luồng rảnh | Độ dài hàng đợi, tải đầu vào, tác vụ có đang được xử lý không. |
| Nhiều yêu cầu đợi lấy kết nối | Pool tài nguyên có thể đã cạn | Số kết nối bận/chờ, truy vấn chậm, timeout, luồng đang giữ kết nối. |
| Nhiều ngăn xếp dừng ở đọc socket | Đợi dịch vụ bên ngoài hoặc I/O | Độ trễ phụ thuộc, timeout mạng, trace và log cùng thời điểm. |
| Luồng lặp lại ở một đoạn tính toán và CPU cao | Tính toán nặng hoặc vòng lặp bất thường | CPU theo luồng và hồ sơ thực thi. |

Đây là **giả thuyết chẩn đoán**, không phải kết luận tự động từ tên phương thức. Ví dụ, một worker rảnh ở `take()` có thể là bình thường, nhưng mọi worker đều chờ kết quả của tác vụ khác đang nằm trong chính pool đã kín lại là dấu hiệu đáng điều tra.

### 5.1. Tranh chấp, bế tắc và cạn pool khác nhau thế nào?

- **Tranh chấp khóa (lock contention):** nhiều luồng cần cùng khóa; chủ sở hữu vẫn có thể hoàn tất và nhả khóa.
- **Bế tắc (deadlock):** tồn tại vòng chờ mà các bên không tự phá được bằng luồng thực thi hiện tại.
- **Cạn pool hoặc thiếu cơ hội thực thi:** các tác vụ không lấy được tài nguyên/worker cần thiết; có thể xảy ra dù không thấy vòng khóa monitor.

Ví dụ vòng chờ hai khóa:

```text
Luồng A giữ L1, đợi L2 do B giữ
Luồng B giữ L2, đợi L1 do A giữ

A -> L2 -> B -> L1 -> A
```

Không kết luận deadlock chỉ vì nhiều luồng cùng `BLOCKED`. Nếu chủ sở hữu sau đó nhả khóa và các tác vụ hoàn tất, đó có thể là tranh chấp kéo dài. Ngược lại, vòng chờ liên quan `ReentrantLock` có thể gồm các luồng `WAITING`.

Với luồng nền tảng, `ThreadMXBean.findDeadlockedThreads()` hỗ trợ tìm vòng chờ monitor và bộ đồng bộ có chủ sở hữu; `findMonitorDeadlockedThreads()` chỉ xét monitor. Kết quả `null` không loại trừ việc tác vụ chờ I/O, chờ logic nghiệp vụ hoặc thiếu worker. Các API quản lý này không hỗ trợ quan sát luồng ảo trên JDK 21. [ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html).

Không mặc định rằng văn bản của Actuator sẽ luôn có dòng `Found one Java-level deadlock` như một số công cụ chẩn đoán JVM. Quan hệ chờ và dữ liệu công cụ cụ thể mới là bằng chứng cần đọc.

## 6. Thí nghiệm Java chạy được: cùng là chờ nhưng nguyên nhân khác nhau

### 6.1. Mục đích và cách chạy

Chương trình tạo sáu **luồng nền tảng (platform thread)**:

- Một luồng giữ monitor trong khi chờ latch; một luồng khác đợi monitor đó.
- Một luồng đợi lấy phần tử từ hàng đợi rỗng.
- Một luồng giữ `ReentrantLock` trong khi chờ latch; một luồng khác đợi khóa đó.
- Một luồng đang ngủ có thời hạn.

Latch xác nhận chủ sở hữu đã lấy khóa trước khi khởi động bên tranh chấp. Chương trình kiểm tra trạng thái với thời hạn năm giây, thay vì đoán rằng ngủ một khoảng ngắn là đủ. Các thao tác này chỉ dùng để tạo thí nghiệm có thể quan sát; không dùng việc thăm dò `getState()` để điều phối nghiệp vụ.

Lưu toàn bộ mã vào `ThreadDumpLab.java`. Cần JDK có mô-đun `java.management`; ví dụ đã biên dịch với `--release 17` và chạy kiểm chứng trên Java 17 và Java 21.

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class ThreadDumpLab {
    @FunctionalInterface
    interface Work {
        void run() throws InterruptedException;
    }

    private static Thread thread(String name, Work work) {
        return new Thread(() -> {
            try {
                work.run();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, name);
    }

    private static void awaitState(Thread thread, Thread.State expected)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (thread.getState() != expected) {
            if (!thread.isAlive() || System.nanoTime() >= deadline) {
                throw new IllegalStateException(
                        thread.getName() + ": " + thread.getState());
            }
            Thread.sleep(10);
        }
    }

    private static void awaitReady(CountDownLatch ready)
            throws InterruptedException {
        if (!ready.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Owner did not become ready");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Object monitor = new Object();
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch monitorReady = new CountDownLatch(1);
        CountDownLatch lockReady = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        LinkedBlockingQueue<String> queue = new LinkedBlockingQueue<>();

        Thread monitorOwner = thread("monitor-owner", () -> {
            synchronized (monitor) {
                monitorReady.countDown();
                release.await();
            }
        });
        Thread monitorContender = thread("monitor-contender", () -> {
            synchronized (monitor) {
                // Chỉ vào được sau khi monitor-owner nhả monitor.
            }
        });
        Thread queueConsumer = thread("queue-consumer", () -> queue.take());
        Thread lockOwner = thread("lock-owner", () -> {
            lock.lock();
            try {
                lockReady.countDown();
                release.await();
            } finally {
                lock.unlock();
            }
        });
        Thread lockContender = thread("lock-contender", () -> {
            lock.lock();
            try {
                // Chỉ vào được sau khi lock-owner gọi unlock().
            } finally {
                lock.unlock();
            }
        });
        Thread sleeper = thread("sleeper", () -> Thread.sleep(300_000));

        List<Thread> threads = List.of(monitorOwner, monitorContender,
                queueConsumer, lockOwner, lockContender, sleeper);
        try {
            monitorOwner.start();
            awaitReady(monitorReady);
            monitorContender.start();
            queueConsumer.start();
            lockOwner.start();
            awaitReady(lockReady);
            lockContender.start();
            sleeper.start();

            awaitState(monitorOwner, Thread.State.WAITING);
            awaitState(monitorContender, Thread.State.BLOCKED);
            awaitState(queueConsumer, Thread.State.WAITING);
            awaitState(lockOwner, Thread.State.WAITING);
            awaitState(lockContender, Thread.State.WAITING);
            awaitState(sleeper, Thread.State.TIMED_WAITING);

            ThreadMXBean bean = ManagementFactory.getThreadMXBean();
            long[] ids = threads.stream().mapToLong(Thread::getId).toArray();
            ThreadInfo[] infos = bean.getThreadInfo(ids, true, true);
            for (ThreadInfo info : infos) {
                if (info == null) {
                    throw new IllegalStateException("Thread disappeared");
                }
                String owner = info.getLockOwnerName();
                System.out.println(info.getThreadName() + " | "
                        + info.getThreadState() + " | owner="
                        + (owner == null ? "-" : owner));
            }
            if (args.length > 0 && args[0].equals("--hold")) {
                Thread.sleep(30_000);
            }
        } finally {
            release.countDown();
            queue.offer("stop");
            sleeper.interrupt();
            for (Thread thread : threads) {
                thread.join(5_000);
                if (thread.isAlive()) {
                    throw new IllegalStateException(
                            "Thread did not finish: " + thread.getName());
                }
            }
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 ThreadDumpLab.java
java ThreadDumpLab
```

### 6.2. Stdout của lần chạy mặc định

Trên các JDK HotSpot 17/21 đã kiểm chứng, chương trình in đúng sáu dòng sau, theo thứ tự danh sách đã định, rồi tự giải phóng các luồng:

```text
monitor-owner | WAITING | owner=-
monitor-contender | BLOCKED | owner=monitor-owner
queue-consumer | WAITING | owner=-
lock-owner | WAITING | owner=-
lock-contender | WAITING | owner=lock-owner
sleeper | TIMED_WAITING | owner=-
```

Dấu `-` chỉ có nghĩa `getLockOwnerName()` không trả về tên chủ sở hữu cho đối tượng mà luồng đang chờ. Nó không có nghĩa luồng đó không giữ khóa khác.

Những quan sát cần giải thích được:

1. `monitor-owner` đợi latch nhưng vẫn giữ monitor bao ngoài. `monitor-contender` vì vậy ở `BLOCKED` và trỏ đúng về chủ sở hữu.
2. `queue-consumer` ở `WAITING` vì hàng đợi rỗng. Trong thí nghiệm, chưa có công việc nên đây là chờ có chủ đích.
3. `lock-owner` đợi cùng latch nhưng vẫn giữ `ReentrantLock`. `lock-contender` ở `WAITING` và có chủ sở hữu là `lock-owner`.
4. `sleeper` ở `TIMED_WAITING` vì `sleep` có thời hạn.
5. Khi `finally` mở latch, hai chủ sở hữu đi tiếp và nhả khóa; hai bên tranh chấp có thể hoàn tất. Hàng đợi nhận phần tử kết thúc và luồng ngủ được ngắt. Không có deadlock trong chương trình này.

Mẫu `lock()` → `try` → `finally { unlock(); }` bảo đảm nhả `ReentrantLock` khi kết thúc vùng bảo vệ. Chính sách khóa công bằng cũng không thay thế việc rút ngắn thao tác chậm trong vùng khóa. [Hợp đồng ReentrantLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html).

### 6.3. Lấy dump từ chương trình bằng jcmd

Để có khoảng thời gian quan sát, chạy:

```shell
java ThreadDumpLab --hold
```

Chương trình vẫn in sáu dòng, sau đó giữ thí nghiệm thêm khoảng 30 giây trước khi dọn dẹp. Mở terminal thứ hai trong khoảng thời gian đó:

```shell
jcmd -l
```

Tìm tiến trình có lớp chính `ThreadDumpLab`. Sau đó, trong PowerShell, thay `12345` bằng PID thực tế vừa tìm được:

```powershell
$javaProcessId = 12345
jcmd $javaProcessId Thread.print -l > lab-threads.txt
```

Dùng JDK phù hợp với JVM đích, cùng máy và quyền người dùng thích hợp. `Thread.print -l` bổ sung thông tin khóa `java.util.concurrent`; tác động của lệnh phụ thuộc số luồng. `jcmd -l` có thể không liệt kê JVM trong container ở không gian tiến trình khác. [Hướng dẫn jcmd JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).

Trong bản dump thực của thí nghiệm, tìm `monitor-contender` rồi đối chiếu đối tượng ở dòng `waiting to lock` với dòng `locked` của `monitor-owner`. Với `lock-contender`, tìm đối tượng `ReentrantLock$NonfairSync` và đối chiếu với phần `Locked ownable synchronizers` của `lock-owner`.

Các dấu hiệu dưới đây là **trích đoạn đã rút gọn và thay địa chỉ bằng nhãn**, chỉ để chỉ vị trí cần tìm; không phải stdout đầy đủ hoặc định dạng HTTP Actuator:

```text
"monitor-contender"
   java.lang.Thread.State: BLOCKED (on object monitor)
   - waiting to lock <M> (a java.lang.Object)

"monitor-owner"
   java.lang.Thread.State: WAITING (parking)
   at java.util.concurrent.CountDownLatch.await(...)
   - locked <M> (a java.lang.Object)

"lock-contender"
   java.lang.Thread.State: WAITING (parking)
   - parking to wait for <R> (a ReentrantLock$NonfairSync)
   at java.util.concurrent.locks.ReentrantLock.lock(...)

"lock-owner"
   java.lang.Thread.State: WAITING (parking)
   at java.util.concurrent.CountDownLatch.await(...)
   Locked ownable synchronizers:
   - <R> (a ReentrantLock$NonfairSync)
```

Địa chỉ, thread ID, tên frame nội bộ và số dòng phụ thuộc lần chạy/JDK. Điều cần bảo toàn khi phân tích là quan hệ giữa bên chờ và bên giữ, không phải những con số của một ví dụ.

Ví dụ này chạy độc lập để học cơ chế JVM. Không cần thêm endpoint nghiệp vụ giả chỉ để tạo dữ liệu cho bài. Trong ứng dụng Spring Boot, Actuator giúp thu thập dữ liệu từ JVM của ứng dụng đang chạy; cách đọc quan hệ vẫn dựa trên cùng các khái niệm.

## 7. Quy trình điều tra một yêu cầu bị treo

1. **Khoanh đúng thời điểm và instance.** Ghi nhận API bị ảnh hưởng, độ trễ, tải, CPU và tài nguyên phụ thuộc. Một dump ngoài thời điểm lỗi có thể không chứa luồng cần tìm.
2. **Thu thập một nhóm mẫu.** Giữ bản gốc và thời gian; kiểm tra HTTP/mã thoát để tránh phân tích tệp phản hồi lỗi.
3. **Chọn nhóm luồng liên quan.** Bắt đầu từ tên pool, frame ứng dụng hoặc nơi đợi; tên luồng chỉ là gợi ý, không phải mã yêu cầu.
4. **Lần theo phụ thuộc.** Với khóa, theo chủ sở hữu; với queue/latch/future, tìm tác vụ hoặc sự kiện phải làm nó tiến triển.
5. **So sánh các mẫu.** Xem cùng luồng và nhóm ngăn xếp có lặp lại, chủ sở hữu có thay đổi, công việc có hoàn tất không. Cùng một vị trí ở ba mẫu là dấu hiệu cần điều tra, chưa phải bằng chứng tuyệt đối rằng không hề tiến triển giữa các mẫu.
6. **Đối chiếu nguồn bằng chứng khác.** Tranh chấp monitor cần kiểm tra vùng khóa; chờ kết nối cần số liệu pool/DB; nghi tính toán nặng cần CPU/profiler; nghi dịch vụ bên ngoài cần trace và timeout.
7. **Sửa đúng cơ chế rồi kiểm chứng lại.** So sánh độ trễ và khả năng hoàn tất dưới tải tương đương, không chỉ so số luồng `WAITING`.

Ví dụ một giả thuyết có thể kiểm chứng:

```text
Quan sát:
Nhiều request thread đợi cùng monitor.
Chủ sở hữu nhiều lần dừng trong lời gọi HTTP ra ngoài.

Giả thuyết:
Lời gọi HTTP chậm đang kéo dài thời gian giữ monitor,
khiến các yêu cầu khác phải xếp hàng.

Kiểm chứng:
Đọc vùng synchronized, đối chiếu trace/timeout của lời gọi,
đo lại dưới tải sau khi thiết kế lại phạm vi bảo vệ trạng thái.
```

Đưa I/O ra khỏi vùng khóa chỉ phù hợp khi vẫn bảo đảm tính đúng đắn của dữ liệu dùng chung. Không xóa `synchronized` hoặc đổi cấu trúc đồng bộ chỉ để làm biến mất các dòng `BLOCKED`.

Nếu tất cả worker trong một pool đều chờ tác vụ được xếp vào chính pool đó, kiểm tra cấu trúc phụ thuộc tác vụ trước khi chỉ tăng kích thước pool. Tăng số luồng hoặc số kết nối có thể chuyển áp lực sang CPU, bộ nhớ hay cơ sở dữ liệu mà chưa giải quyết nguyên nhân.

## 8. Giới hạn với luồng ảo trên JDK 21

Trên JDK 21, `ThreadMXBean` quản lý luồng nền tảng. Actuator 3.3 dựa trên thông tin quản lý luồng này, nên không xem dump HTTP là danh sách đầy đủ mọi luồng ảo của ứng dụng.

Khi cần quan sát luồng ảo, dùng khả năng dump dành cho chúng. Ví dụ sau là lệnh PowerShell cho một tiến trình JDK 21; `12345` phải được thay bằng PID thực tế:

```powershell
$javaProcessId = 12345
jcmd $javaProcessId Thread.dump_to_file -format=json "C:\diagnostics\threads-virtual.json"
```

Thư mục đích phải tồn tại và JVM đích phải ghi được. Tệp được tạo trong môi trường của JVM đích; với máy Unix/container, dùng đường dẫn tuyệt đối phù hợp tại đó.

Kiểu dump `Thread.dump_to_file` có thể liệt kê cả luồng nền tảng và luồng ảo, nhưng không mang toàn bộ thông tin khóa/địa chỉ như dump truyền thống. Vì vậy không áp nguyên xi cách ghép monitor ở phần trước vào mọi định dạng. Khi cần thêm bằng chứng về thực thi luồng ảo, phối hợp JFR phù hợp phiên bản JDK. [Quan sát luồng ảo trên Java 21](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html).

Phân biệt rõ “không xuất hiện trong loại dump này” với “không tồn tại”. Cũng không suy ra hàng nghìn luồng ảo đang chờ đồng nghĩa với hàng nghìn luồng hệ điều hành bị chiếm giữ.

## 9. Lỗi thường gặp khi thu thập và diễn giải

| Hiện tượng hoặc lỗi suy luận | Cách xử lý |
| --- | --- |
| HTTP `404` | Kiểm tra đúng instance, cổng/base path, endpoint bật và được công bố; xem `exclude`. |
| HTTP `401` hoặc `403` | Kiểm tra cơ chế xác thực/phân quyền và lớp proxy; không mở toàn bộ endpoint để né lỗi. |
| Kết nối bị từ chối hoặc timeout | Kiểm tra tiến trình, bind address, mạng/container; nếu HTTP không phục vụ được, cân nhắc jcmd nội bộ có quyền. |
| Tệp `.json` chứa HTML hoặc thông báo lỗi | Kiểm tra HTTP, mã thoát và cấu trúc `threads` trước khi phân tích. |
| Thấy `WAITING` là kết luận treo | Đọc thao tác chờ, điều kiện đánh thức và tải thực tế. |
| Thấy `RUNNABLE` là kết luận CPU cao | Đối chiếu CPU theo thời gian và hồ sơ thực thi. |
| Chỉ đếm `BLOCKED` để đo mọi tranh chấp | Kiểm tra cả `ReentrantLock`, điều kiện chờ và pool tài nguyên. |
| Thấy chủ sở hữu `WAITING` là bỏ qua nó | Kiểm tra các khóa nó đang giữ và điều kiện nó đang đợi. |
| Một mẫu giống lần trước là kết luận deadlock | Tìm vòng chờ và kiểm chứng tiến triển; có thể là xử lý lặp lại hợp lệ. |

Dump cũng là một yêu cầu công việc. Khi ứng dụng quá tải, endpoint HTTP có thể chậm, cần xác thực hoặc không phản hồi; không có phản hồi HTTP không đồng nghĩa đã chứng minh deadlock. Nếu dùng jcmd, quyền attach và khả năng quan sát tiến trình trong môi trường triển khai phải phù hợp.

Một yêu cầu có thể chuyển qua nhiều luồng khi dùng xử lý bất đồng bộ. Khi đó cần log có mã tương quan/trace để nối các giai đoạn; không gán toàn bộ yêu cầu cho một tên luồng chỉ vì tên ấy xuất hiện trong một mẫu.

## 10. Tự kiểm tra bằng bằng chứng

**Tình huống 1:** `queue-consumer` ở `WAITING` và hàng đợi đang rỗng, không có tác vụ đầu vào. Có cần sửa?

Chưa có dấu hiệu lỗi. Thí nghiệm cho thấy đây có thể là worker đang rảnh. Nếu có tác vụ chờ nhưng không được xử lý, cần xem lại đường đưa việc vào queue và nhóm worker thực tế.

**Tình huống 2:** `monitor-contender` ở `BLOCKED`, chủ sở hữu ở `WAITING`. Chủ sở hữu có thể là nguyên nhân gây xếp hàng không?

Có. Trong ví dụ, chủ sở hữu đợi latch trong khi giữ monitor. Cần tìm điều kiện mở latch, không bỏ qua chủ sở hữu chỉ vì nó cũng đang chờ.

**Tình huống 3:** Hai luồng đều ở `WAITING` trong `ReentrantLock.lock` và mỗi luồng giữ khóa mà luồng còn lại cần. Có thể deadlock không?

Có thể. Bằng chứng quyết định là vòng chờ giữa hai khóa, không phải sự hiện diện của hằng `BLOCKED`.

**Tình huống 4:** Một luồng `RUNNABLE` xuất hiện ở cùng phương thức trong ba mẫu. Đã chứng minh vòng lặp vô hạn chưa?

Chưa. Phải đối chiếu CPU, mã nguồn, thời gian xử lý và dấu hiệu hoàn tất công việc. Lấy mẫu có thể bắt gặp cùng một vị trí trong hoạt động lặp bình thường.

**Bài thực hành:** chạy `ThreadDumpLab --hold`, tự chỉ ra hai cạnh “bên chờ → bên giữ khóa”, một trường hợp chờ công việc và một trường hợp chờ có thời hạn. Sau khi chương trình tự kết thúc, giải thích vì sao mẫu có cả `BLOCKED` lẫn `WAITING` mà không có deadlock.
