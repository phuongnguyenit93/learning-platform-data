# Thread.currentThread và phân biệt danh tính virtual thread với carrier

`Thread.currentThread()` trả về đối tượng `Thread` đại diện cho luồng Java đang thực thi đoạn mã hiện tại. Trong Java 21, nếu đoạn mã đang chạy trên virtual thread, phương thức này trả về chính virtual thread đó, không phải platform thread đang làm carrier. Virtual thread có thể được unmount khỏi một carrier khi chờ và sau đó mount lên carrier khác, nhưng danh tính của đối tượng virtual thread vẫn giữ nguyên.

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), cần phân biệt danh tính của tác vụ Java với luồng hệ điều hành đang tạm thời thực thi nó. Điều này ảnh hưởng đến logging, `ThreadLocal`, interruption và cách chẩn đoán ứng dụng. Không dùng tên hoặc ID của carrier để đại diện cho danh tính của virtual thread.

## Thread.currentThread trả về điều gì?

`Thread.currentThread()` là phương thức static của `Thread`. Nó trả về đối tượng `Thread` đang thực thi mã gọi phương thức:

```java
Thread current = Thread.currentThread();

System.out.println("Name: " + current.getName());
System.out.println("Thread ID: " + current.threadId());
System.out.println("Virtual: " + current.isVirtual());
```

Các thông tin này mô tả luồng Java hiện tại:

- `getName()` trả về tên của luồng. Tên hữu ích cho log và chẩn đoán, nhưng không bảo đảm duy nhất.
- `threadId()` trả về ID của luồng, giữ nguyên trong suốt vòng đời của luồng đó.
- `isVirtual()` cho biết luồng hiện tại có phải virtual thread hay không. API này có từ Java 21.

Trong Java 21, nên dùng `threadId()` để lấy ID. `getId()` đã bị deprecated từ Java 19 để chuyển sang API có tên rõ nghĩa hơn. Không nên bắt đầu mã mới dựa trên `getId()`.

`Thread.currentThread()` không tạo một thread mới. Nó chỉ cung cấp tham chiếu đến thread đang chạy, vì vậy có thể dùng để đọc thông tin hoặc thực hiện các thao tác hợp lệ trên chính luồng đó, chẳng hạn kiểm tra interrupt status.

## Phân biệt virtual thread và carrier thread

Virtual thread là đơn vị thực thi Java do JVM quản lý. Carrier là một platform thread mà scheduler dùng để chạy mã của virtual thread trong một khoảng thời gian. Carrier gắn với OS thread; virtual thread thì không có một OS thread riêng được gắn cố định trong suốt vòng đời.

Khi virtual thread đang chạy, nó được mount lên carrier. Nếu gặp thao tác blocking được JDK hỗ trợ và có thể unmount, virtual thread tạm dừng và nhường carrier. Khi sẵn sàng chạy tiếp, nó có thể được mount lên một carrier khác.

```text
Virtual thread V
  Thread.currentThread() -> V
          |
          | chạy trên carrier A
          v
      Carrier A
          |
          | V block và unmount
          v
      Carrier A chạy virtual thread khác

Sau khi V sẵn sàng chạy tiếp:
  Thread.currentThread() -> vẫn là V
          |
          | có thể mount lên carrier B
          v
      Carrier B
```

Điểm cần nhớ:

- `Thread.currentThread()` trong mã virtual thread luôn đại diện cho virtual thread đó.
- Carrier chỉ là phương tiện thực thi tạm thời; nó có thể thay đổi giữa các lần mount.
- Mã ứng dụng không nên giả định một virtual thread luôn chạy trên cùng một carrier.
- API công khai `Thread.currentThread()` không cung cấp đối tượng carrier hiện tại.

Vì vậy, không thể dùng `Thread.currentThread()` để lấy tên hoặc ID OS thread đang làm carrier khi mã chạy trên virtual thread. Nếu cần điều tra scheduler, pinning hoặc hoạt động mount/unmount, hãy dùng công cụ quan sát JVM như Java Flight Recorder và thread dump phù hợp, thay vì suy đoán carrier từ thông tin của thread hiện tại.

## So sánh Thread.currentThread trên platform thread và virtual thread

`Thread.currentThread()` hoạt động thống nhất cho cả hai loại thread. Khác biệt nằm ở loại đối tượng được trả về:

```java
public class CurrentThreadIdentity {
    public static void main(String[] args) throws InterruptedException {
        Thread platform = Thread.ofPlatform()
                .name("platform-worker")
                .start(CurrentThreadIdentity::printCurrent);

        Thread virtual = Thread.ofVirtual()
                .name("virtual-worker")
                .start(CurrentThreadIdentity::printCurrent);

        platform.join();
        virtual.join();
    }

    private static void printCurrent() {
        Thread current = Thread.currentThread();

        System.out.printf(
                "name=%s, id=%d, virtual=%s, sameObject=%s%n",
                current.getName(),
                current.threadId(),
                current.isVirtual(),
                current == Thread.currentThread());
    }
}
```

Trong platform worker, `isVirtual()` trả về `false`; trong virtual worker, nó trả về `true`. Biểu thức `current == Thread.currentThread()` là `true` vì cả hai tham chiếu đều trỏ đến đối tượng thread đang thực thi. Tên và ID ở đây nhận diện thread Java, không phải carrier của virtual thread.

Nếu dùng `Executors.newVirtualThreadPerTaskExecutor()`, mỗi tác vụ được submit chạy trên một virtual thread. Vì vậy, khi gọi `Thread.currentThread()` bên trong tác vụ, kết quả cũng là virtual thread tương ứng với tác vụ đó.

## Danh tính không đổi khi virtual thread chuyển carrier

Một virtual thread là một đối tượng `Thread` có vòng đời riêng. Khi nó unmount rồi mount lại, đối tượng thread không bị thay thế. Các thông tin như tên và `threadId()` vẫn thuộc về cùng virtual thread.

```java
import java.util.concurrent.CountDownLatch;

public class VirtualThreadIdentity {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch done = new CountDownLatch(1);

        Thread worker = Thread.ofVirtual().name("request-42").start(() -> {
            try {
                Thread before = Thread.currentThread();
                long idBefore = before.threadId();

                Thread.sleep(100);

                Thread after = Thread.currentThread();
                System.out.printf(
                        "sameObject=%s, sameId=%s, virtual=%s%n",
                        before == after,
                        idBefore == after.threadId(),
                        after.isVirtual());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        });

        done.await();
        worker.join();
    }
}
```

`Thread.sleep()` tạo một khoảng chờ để minh họa điểm virtual thread có thể unmount. Khi tiếp tục, `Thread.currentThread()` vẫn trả về cùng đối tượng `worker`. Ví dụ không cố đọc carrier trước và sau, vì carrier không phải danh tính của virtual thread và không được cung cấp qua API này.

Không nên dựa vào việc virtual thread chắc chắn đổi carrier sau mỗi lần blocking. Scheduler có quyền quyết định carrier tiếp theo; điều được bảo đảm ở cấp ứng dụng là danh tính của virtual thread vẫn ổn định, không phải carrier nào sẽ chạy nó.

## ThreadLocal thuộc về virtual thread, không thuộc carrier

`ThreadLocal` gắn dữ liệu với đối tượng `Thread` hiện tại. Khi mã chạy trên virtual thread, giá trị `ThreadLocal` thuộc về virtual thread đó. Nếu virtual thread unmount khỏi carrier A rồi mount lên carrier B, giá trị vẫn đi cùng virtual thread vì nó không được lưu như trạng thái riêng của carrier.

```java
public class RequestContextExample {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    static void handle(String requestId) {
        REQUEST_ID.set(requestId);
        try {
            callService();
        } finally {
            REQUEST_ID.remove();
        }
    }

    static void callService() {
        System.out.println(
                Thread.currentThread().getName()
                        + " handles " + REQUEST_ID.get());
    }
}
```

Nếu `handle()` chạy trên virtual thread, `REQUEST_ID` là giá trị của virtual thread xử lý yêu cầu đó. Nó không bị thay bằng giá trị `ThreadLocal` của carrier. Đây là một lý do mã dựa trên `ThreadLocal` thường vẫn hoạt động theo ý nghĩa luồng Java khi chuyển từ platform thread sang virtual thread.

Tuy nhiên, virtual thread có thể được tạo với số lượng lớn. Nếu mỗi virtual thread giữ nhiều giá trị `ThreadLocal` hoặc các giá trị đó giữ object graph lớn, mức dùng bộ nhớ có thể tăng đáng kể. Hãy chỉ lưu context thực sự cần thiết, dọn dẹp bằng `remove()` khi vòng đời giá trị kết thúc và tránh dùng `ThreadLocal` để giữ tài nguyên đắt tiền theo mô hình pool như trước.

`InheritableThreadLocal` cũng có thể truyền giá trị từ thread tạo sang virtual thread mới theo quy tắc kế thừa. Nếu tạo nhiều virtual thread, cần cân nhắc chi phí sao chép context và chỉ truyền những dữ liệu cần thiết. Không giả định rằng dữ liệu gắn với carrier sẽ tự động trở thành context của virtual thread.

## Dùng Thread.currentThread cho interruption và trạng thái hiện tại

Vì `Thread.currentThread()` trả về virtual thread khi đang chạy trong virtual thread, các thao tác trên đối tượng đó áp dụng cho virtual thread hiện tại:

```java
static void doWork() {
    Thread current = Thread.currentThread();

    if (current.isInterrupted()) {
        return;
    }

    System.out.println("Working on " + current.getName());
}
```

Nếu cần đánh dấu thread hiện tại bị interrupt, có thể gọi `Thread.currentThread().interrupt()`. Với virtual thread, trạng thái interrupt thuộc về virtual thread đó; không phải một carrier bất kỳ. Khi một thao tác blocking ném `InterruptedException`, trạng thái interrupt thường đã được xóa theo hợp đồng của thao tác đó. Nếu phương thức không thể truyền exception lên, hãy khôi phục trạng thái bằng cách gọi `Thread.currentThread().interrupt()` trước khi kết thúc hoặc tiếp tục xử lý.

Không nên dùng carrier thread để truyền cancellation hoặc interrupt cho tác vụ. Hãy giữ tham chiếu tới virtual thread hoặc dùng cơ chế quản lý tác vụ như `Future`/`ExecutorService` để hủy đúng công việc.

## Logging và quan sát danh tính thread

Trong log, nên ghi thông tin nhận diện virtual thread ở nơi cần truy vết tác vụ. Tên thread có thể được đặt có chủ đích khi tạo:

```java
Thread worker = Thread.ofVirtual()
        .name("order-request-" + requestId)
        .start(() -> {
            Thread current = Thread.currentThread();
            logger.info("threadName={}, threadId={}, virtual={}",
                    current.getName(),
                    current.threadId(),
                    current.isVirtual());
            processOrder(requestId);
        });
```

Tên giúp đọc log thuận tiện, nhưng không nên dùng tên làm khóa định danh duy nhất vì tên có thể trùng hoặc thay đổi. `threadId()` giữ nguyên trong vòng đời thread và hữu ích để liên kết log trong cùng vòng đời đó. Với tracing qua nhiều thread hoặc nhiều dịch vụ, nên dùng request ID hoặc trace ID riêng của nghiệp vụ thay vì dựa hoàn toàn vào thread ID.

Java Flight Recorder cung cấp các sự kiện liên quan virtual thread, chẳng hạn bắt đầu, kết thúc và pinning. Các sự kiện như `jdk.VirtualThreadPinned` giúp xác định nơi virtual thread bị giữ trên carrier khi blocking. Thread dump của JVM cũng hữu ích khi cần xem các virtual thread và trạng thái của chúng. Những công cụ này quan sát runtime; chúng không thay đổi ý nghĩa của `Thread.currentThread()` trong mã ứng dụng.

## Những giả định cần tránh

| Giả định sai | Cách hiểu đúng |
| --- | --- |
| `Thread.currentThread()` trả về carrier khi mã chạy trên virtual thread | Nó trả về đối tượng virtual thread đang thực thi |
| Một virtual thread luôn chạy trên cùng một carrier | Carrier có thể thay đổi sau khi virtual thread unmount và mount lại |
| ThreadLocal lưu trên carrier | ThreadLocal gắn với đối tượng virtual thread hiện tại |
| Thread name là ID duy nhất | Tên có thể trùng; dùng `threadId()` cho định danh thread trong vòng đời của nó và trace ID cho nghiệp vụ |
| Có thể suy ra số virtual thread từ số OS thread | Virtual thread và OS thread có quan hệ multiplex, không phải một-một |
| Cần lấy carrier để hủy virtual thread | Hủy hoặc interrupt đúng virtual thread/task thông qua tham chiếu hay executor |

## Quy trình sử dụng trong dự án Java 21

1. **Lấy đúng thread hiện tại.** Dùng `Thread.currentThread()` tại nơi cần kiểm tra hoặc thao tác với luồng Java đang chạy.
2. **Phân biệt loại thread.** Dùng `isVirtual()` khi cần chẩn đoán hoặc ghi log; tránh rẽ nhánh nghiệp vụ không cần thiết chỉ dựa vào loại thread.
3. **Ghi danh tính phù hợp.** Dùng tên để đọc log, `threadId()` để liên kết thông tin trong vòng đời thread và request/trace ID để theo dõi nghiệp vụ.
4. **Không phụ thuộc carrier.** Không giả định virtual thread gắn với một carrier cố định và không tìm carrier qua `Thread.currentThread()`.
5. **Quản lý ThreadLocal theo vòng đời tác vụ.** Giữ context nhỏ, xóa giá trị khi hoàn tất và cân nhắc chi phí của `InheritableThreadLocal` khi tạo nhiều virtual thread.
6. **Điều khiển cancellation trên đúng tác vụ.** Interrupt virtual thread hoặc hủy `Future`/task tương ứng, không thao tác trên carrier.
7. **Dùng công cụ quan sát khi cần.** Dùng JFR và thread dump để điều tra mount/unmount, pinning và trạng thái virtual thread.
8. **Dùng API hiện hành của Java 21.** Dùng `threadId()` thay cho `getId()` đã deprecated; `isVirtual()` và các builder `Thread.ofVirtual()`/`Thread.ofPlatform()` là API ổn định.

`Thread.currentThread()` luôn nhận diện luồng Java đang thực thi. Khi đó là virtual thread, đối tượng được trả về vẫn là virtual thread dù JVM có thể chuyển nó giữa các carrier trong suốt vòng đời. Giữ rõ ranh giới này giúp logging, ThreadLocal, interruption và chẩn đoán hoạt động đúng với mô hình virtual thread của Java 21.
