# Kiểm tra Thread.isVirtual và định danh thread trong chẩn đoán

Trong Java 21, `Thread.isVirtual()` cho biết một đối tượng `Thread` là virtual thread hay platform thread. Khi cần xác định thread đang thực thi một đoạn code, dùng `Thread.currentThread()` rồi kết hợp `isVirtual()`, `threadId()` và `getName()` để ghi thông tin chẩn đoán. Cách này đặc biệt hữu ích khi một ứng dụng sử dụng đồng thời platform thread và virtual thread.

Java 21 đã chuẩn hóa Virtual Threads theo JEP 444. Cả hai loại thread đều là đối tượng `java.lang.Thread`, vì vậy phần lớn API quan sát thread vẫn được dùng theo cùng một cách. Tuy nhiên, tên mặc định, định danh và công cụ giám sát có một số khác biệt cần hiểu đúng để log và thread dump không gây nhầm lẫn.

## 1. Phân biệt virtual thread và platform thread

`Thread.isVirtual()` là phương thức instance, trả về:

- `true` nếu đối tượng là virtual thread.
- `false` nếu đối tượng là platform thread.

Ví dụ:

```java
static void printThreadKind() {
    Thread current = Thread.currentThread();

    if (current.isVirtual()) {
        System.out.println("Đang chạy trên virtual thread");
    } else {
        System.out.println("Đang chạy trên platform thread");
    }
}
```

Có thể tạo hai loại thread để quan sát kết quả:

```java
Thread platform = Thread.ofPlatform()
        .name("platform-worker")
        .start(MyService::printThreadKind);

Thread virtual = Thread.ofVirtual()
        .name("virtual-worker")
        .start(MyService::printThreadKind);

platform.join();
virtual.join();
```

`isVirtual()` chỉ phân loại loại thread. Nó không cho biết virtual thread đang được mount trên carrier hay đang unmount để chờ; trạng thái mount/unmount thay đổi trong quá trình chạy và không phải mục đích của phương thức này.

## 2. Thread.currentThread() trả về thread nào?

`Thread.currentThread()` trả về đối tượng `Thread` đại diện cho thread đang thực thi lệnh gọi. Khi code chạy trong virtual thread, phương thức trả về chính virtual thread đó, không phải platform thread đang làm carrier.

```java
static void inspectCurrentThread() {
    Thread current = Thread.currentThread();

    System.out.println("virtual = " + current.isVirtual());
    System.out.println("name = " + current.getName());
    System.out.println("id = " + current.threadId());
}

public static void main(String[] args) throws InterruptedException {
    Thread.ofVirtual()
            .name("order-request")
            .start(MyService::inspectCurrentThread)
            .join();
}
```

Không nên dùng `Thread.currentThread()` trong virtual thread để suy ra OS thread hoặc carrier thread. Java quản lý việc gắn và tháo virtual thread khỏi carrier; ứng dụng nhìn thấy đối tượng virtual thread ở cấp Java.

## 3. Định danh thread bằng threadId()

`Thread.threadId()` trả về một số nguyên `long` dương định danh thread. ID được tạo khi thread được tạo và không thay đổi trong suốt vòng đời của thread.

```java
static void logCurrentThread() {
    Thread current = Thread.currentThread();

    System.out.printf(
            "threadId=%d, name=%s, virtual=%s%n",
            current.threadId(),
            current.getName(),
            current.isVirtual()
    );
}
```

`threadId()` có từ Java 19 và là API nên dùng trong Java 21. Phương thức `Thread.getId()` đã bị deprecated từ Java 19; tài liệu API khuyến nghị thay bằng `threadId()` vì `getId()` không phải final và có thể bị override để trả về một giá trị không phải thread ID thực.

Thread ID có các giới hạn quan trọng:

- ID chỉ duy nhất trong thời gian thread còn tồn tại.
- Sau khi thread kết thúc, JVM có thể tái sử dụng ID đó cho thread khác.
- Đây là Java thread ID, không phải OS thread ID hoặc carrier ID.
- Không dùng ID này làm request ID, transaction ID hoặc định danh bền vững trong cơ sở dữ liệu.

Khi cần theo dõi một request xuyên qua nhiều thread hoặc nhiều dịch vụ, hãy dùng correlation ID/trace ID của ứng dụng. Thread ID chỉ bổ sung thông tin cho biết đoạn code đang được thực thi trên thread nào tại thời điểm ghi log.

## 4. Đặt tên virtual thread để dễ đọc log

Virtual thread không có tên mặc định. Nếu chưa đặt tên, `getName()` trả về chuỗi rỗng. Vì vậy, log chỉ ghi tên thread có thể thiếu thông tin khi ứng dụng dùng virtual thread.

Có thể đặt tên khi tạo thread bằng `Thread.Builder`:

```java
Thread worker = Thread.ofVirtual()
        .name("payment-request-42")
        .start(MyService::logCurrentThread);

worker.join();
```

Với nhiều thread cùng loại, dùng tiền tố và bộ đếm để tạo tên dễ phân biệt:

```java
var builder = Thread.ofVirtual().name("http-request-", 0);

Thread first = builder.start(MyService::logCurrentThread);
Thread second = builder.start(MyService::logCurrentThread);

first.join();
second.join();
```

Tên được tạo lần lượt theo dạng `http-request-0`, `http-request-1`, ... Có thể tạo `ThreadFactory` từ builder để dùng với executor:

```java
ThreadFactory factory = Thread.ofVirtual()
        .name("job-", 0)
        .factory();

try (ExecutorService executor = Executors.newThreadPerTaskExecutor(factory)) {
    Future<?> future = executor.submit(MyService::logCurrentThread);
    future.get();
}
```

Tên thread là nhãn hỗ trợ con người đọc log và thread dump. Tên có thể thay đổi bằng `setName()` và không mặc nhiên là duy nhất giữa các factory hoặc process. Không dùng tên thread thay cho ID nghiệp vụ; cũng không đưa token, thông tin cá nhân hoặc dữ liệu nhạy cảm vào tên thread vì tên có thể xuất hiện trong log và công cụ giám sát.

## 5. Tạo một dòng log chẩn đoán hữu ích

Trong ứng dụng có cả hai loại thread, nên ghi đồng thời loại thread, tên và ID. Nếu ứng dụng có request ID hoặc trace ID, ghi thêm ID đó để liên kết log giữa các giai đoạn xử lý.

```java
static void logExecution(String traceId, String operation) {
    Thread current = Thread.currentThread();

    System.out.printf(
            "traceId=%s operation=%s threadType=%s threadName=%s threadId=%d%n",
            traceId,
            operation,
            current.isVirtual() ? "virtual" : "platform",
            current.getName(),
            current.threadId()
    );
}
```

Ví dụ kết quả (ID và tên cụ thể thay đổi theo lần chạy):

```text
traceId=tr-7a21 operation=load-order threadType=virtual threadName=order-request threadId=42
traceId=tr-7a21 operation=write-audit threadType=platform threadName=audit-worker threadId=31
```

Hai dòng log có cùng trace ID nhưng chạy trên hai thread khác nhau. Đây là lý do trace ID phù hợp để theo dõi toàn bộ request, còn thread ID chỉ giúp chẩn đoán thread thực thi từng bước.

## 6. Đọc trạng thái thread đúng mục đích

`Thread.getState()` trả về một giá trị `Thread.State`, chẳng hạn `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING` hoặc `TERMINATED`.

```java
Thread current = Thread.currentThread();
System.out.println(current.getState());
```

Trạng thái là ảnh chụp tại thời điểm gọi và có thể thay đổi ngay sau đó. Tài liệu API xác định `getState()` phục vụ monitoring, không dùng làm cơ chế đồng bộ hóa. Không viết logic nghiệp vụ kiểu "nếu thread đang WAITING thì gọi method X" vì trạng thái có thể thay đổi giữa lúc kiểm tra và lúc hành động.

`isVirtual()` và `getState()` trả lời hai câu hỏi khác nhau:

| Phương thức | Câu hỏi được trả lời |
|---|---|
| `isVirtual()` | Đây là virtual thread hay platform thread? |
| `getState()` | Thread đang ở trạng thái thực thi/chờ nào tại thời điểm quan sát? |
| `isAlive()` | Thread đã bắt đầu và chưa kết thúc hay chưa? |
| `isInterrupted()` | Cờ interrupt của thread đang được đặt hay không? |

Không suy luận loại thread từ `Thread.State`. Virtual thread và platform thread đều có thể ở các trạng thái như `RUNNABLE`, `WAITING` hoặc `TIMED_WAITING`.

## 7. Giới hạn của ThreadMXBean và getAllStackTraces()

Một điểm rất dễ gây hiểu nhầm khi chuyển sang virtual thread là các API giám sát thread truyền thống trong Java 21 không bao gồm virtual thread.

`ThreadMXBean` trong `java.lang.management` chỉ hỗ trợ giám sát và quản lý platform thread. Các số liệu như `getThreadCount()`, `getPeakThreadCount()`, `getAllThreadIds()` và các kết quả `dumpAllThreads()` không tính virtual thread. Các API đo CPU time của `ThreadMXBean` cũng là API cho platform thread.

Ví dụ:

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();

System.out.println("Platform thread count: " + bean.getThreadCount());
System.out.println("Platform thread IDs: " + Arrays.toString(bean.getAllThreadIds()));
```

Các con số trên không phải tổng số thread Java nếu ứng dụng đang chạy virtual thread. Tương tự, `Thread.getAllStackTraces()` chỉ trả stack trace của các platform thread còn sống; virtual thread không có trong map kết quả.

Vì vậy, không dùng riêng `ThreadMXBean` hoặc `Thread.getAllStackTraces()` để kết luận ứng dụng không có virtual thread, hoặc để thống kê toàn bộ request đang chạy.

## 8. Lấy thread dump có virtual thread bằng jcmd

Java 21 cung cấp lệnh `Thread.dump_to_file` trong `jcmd` để tạo thread dump bao gồm cả platform thread và virtual thread:

```bash
# Thread dump dạng text để đọc trực tiếp
jcmd <pid> Thread.dump_to_file -format=text threads.txt

# Thread dump dạng JSON để công cụ có thể phân tích
jcmd <pid> Thread.dump_to_file -format=json threads.json
```

Thay `<pid>` bằng process ID của JVM cần kiểm tra. Dùng đúng bản JDK tương thích và quyền truy cập tới process đó. JSON phù hợp để công cụ đọc và tổng hợp khi có số lượng virtual thread lớn.

Thread dump này liệt kê cả platform thread và virtual thread. Tuy nhiên, nó không cung cấp object address, lock information, JNI statistics, heap statistics và một số thông tin có trong thread dump truyền thống. Đây là định dạng bổ sung để quan sát lượng lớn thread; khi điều tra lock hoặc deadlock, cần kết hợp công cụ và dữ liệu chẩn đoán phù hợp thay vì chỉ dựa vào file này.

Các API và lệnh giám sát cần phân biệt:

| Công cụ | Có bao gồm virtual thread trong Java 21? | Ghi chú |
|---|---|---|
| `Thread.isVirtual()` | Có, kiểm tra từng đối tượng | Cách trực tiếp để phân loại thread hiện tại hoặc thread đã có tham chiếu |
| `ThreadMXBean` | Không | Chỉ quản lý và giám sát platform thread |
| `Thread.getAllStackTraces()` | Không | Chỉ trả stack trace của platform thread |
| `jcmd <pid> Thread.dump_to_file` | Có | Dump cả platform và virtual thread; thiếu một số dữ liệu lock/JVM có trong dump truyền thống |

## 9. Dùng JFR để quan sát vòng đời virtual thread

JDK Flight Recorder (JFR) có các event hỗ trợ chẩn đoán virtual thread:

| Event | Ý nghĩa | Mặc định trong Java 21 |
|---|---|---|
| `jdk.VirtualThreadStart` | Virtual thread bắt đầu chạy | Tắt |
| `jdk.VirtualThreadEnd` | Virtual thread kết thúc | Tắt |
| `jdk.VirtualThreadPinned` | Virtual thread bị pin trên carrier trong thời gian vượt ngưỡng | Bật, ngưỡng mặc định 20 ms |
| `jdk.VirtualThreadSubmitFailed` | Không thể submit/start hoặc unpark virtual thread do vấn đề tài nguyên | Bật |

Có thể xem các event đã được ghi trong file JFR:

```bash
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed recording.jfr
```

Hai event Start và End cần được bật trong cấu hình JFR hoặc qua JDK Mission Control nếu muốn ghi lại. Event `VirtualThreadPinned` hữu ích khi điều tra trường hợp virtual thread thực hiện blocking nhưng không thể unmount khỏi carrier, ví dụ blocking trong một vùng `synchronized` hoặc native/foreign call theo điều kiện của JDK 21.

JFR bổ sung góc nhìn về vòng đời và pinning; nó không thay thế việc ghi trace ID, tên thread có ý nghĩa hoặc thread dump khi cần điều tra một request cụ thể.

## 10. Quy trình chẩn đoán thực tế

Khi một log hoặc thread dump khiến bạn chưa rõ task đang chạy trên loại thread nào, có thể làm theo trình tự:

1. Gọi `Thread.currentThread()` tại điểm thực thi để lấy đúng đối tượng thread của task.
2. Ghi `isVirtual()`, `threadId()` và `getName()`; bổ sung trace ID/request ID của ứng dụng.
3. Nếu cần trạng thái tức thời, đọc `getState()` nhưng không dùng kết quả đó để điều khiển đồng bộ hóa.
4. Nếu cần xem toàn bộ virtual thread, dùng `jcmd <pid> Thread.dump_to_file` thay vì chỉ dựa vào `ThreadMXBean` hoặc `Thread.getAllStackTraces()`.
5. Nếu nghi ngờ pinning hoặc lỗi vòng đời virtual thread, thu JFR và xem các event `jdk.VirtualThread*` phù hợp.
6. Khi so sánh log giữa nhiều process hoặc nhiều request, dùng trace ID; không coi thread ID là định danh toàn cục hoặc lâu dài.

## 11. Những điều cần nhớ

- `isVirtual()` xác định loại thread; nó không cho biết virtual thread đang mount hay unmount.
- `Thread.currentThread()` trong virtual thread trả về virtual thread, không trả về carrier.
- Dùng `threadId()` thay cho `getId()`; `getId()` deprecated từ Java 19.
- Virtual thread không có tên mặc định; hãy đặt tên bằng `Thread.ofVirtual().name(...)` nếu tên giúp ích cho chẩn đoán.
- Thread ID chỉ duy nhất trong vòng đời thread và có thể được tái sử dụng sau khi thread kết thúc.
- `ThreadMXBean` và `Thread.getAllStackTraces()` trong Java 21 chỉ bao gồm platform thread.
- Dùng `jcmd Thread.dump_to_file` để lấy dump có cả virtual thread; dùng JFR để quan sát start/end/pinning/submit failure.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 21 API — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
- [Oracle Java SE 21 API — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [Oracle Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [Java SE 21 API — Thread.threadId()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#threadId())
