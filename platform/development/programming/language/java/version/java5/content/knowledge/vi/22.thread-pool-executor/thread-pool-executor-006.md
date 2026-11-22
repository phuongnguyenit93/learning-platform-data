# ThreadFactory trong bộ luồng tùy chỉnh

## 1. Vì sao cần tách cách tạo luồng khỏi cách chạy công việc?

Một `ThreadPoolExecutor` phải quyết định khi nào cần thêm luồng và luồng đó sẽ xử lý những công việc nào. Ứng dụng lại có nhu cầu riêng về tên luồng, trạng thái daemon, độ ưu tiên hoặc nơi ghi nhận lỗi chưa được bắt.

`ThreadFactory` là điểm tách hai trách nhiệm đó:

- Executor quản lý kích thước nhóm, hàng đợi, giao việc và vòng đời thực thi.
- Factory tạo một đối tượng Thread mới theo cấu hình cần thiết khi executor yêu cầu.

Nhờ đó, có thể nhận diện luồng của từng nhóm trong log hoặc thread dump mà không tự viết lại cơ chế quản lý nhóm luồng.

ThreadFactory vẫn là API được dùng trong Java hiện nay. Ví dụ chính dùng luồng nền tảng (platform thread) và chạy bằng Java 17 trở lên.

## 2. Hợp đồng newThread: trả luồng mới chưa khởi động

ThreadFactory có phương thức:

```java
Thread newThread(Runnable task);
```

Đối tượng trả về phải là một luồng **chưa khởi động** để chạy Runnable được cung cấp. Executor sẽ chịu trách nhiệm khởi động nó tại thời điểm thích hợp. [ThreadFactory.newThread](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadFactory.html).

Đoạn minh họa hợp lệ về ý tưởng:

```java
ThreadFactory factory = task -> new Thread(task, "background-worker");
```

Đoạn này cần import `ThreadFactory`. Trong ứng dụng thực tế cần tên có số thứ tự thay vì đặt mọi luồng cùng một tên.

Các việc không được làm trong factory dùng cho ThreadPoolExecutor:

- Không gọi `thread.start()` trước khi trả luồng về.
- Không gọi trực tiếp `task.run()` rồi trả một Thread không thực hiện công việc được giao.
- Không trả lại cùng một Thread cũ cho nhiều lần yêu cầu; một đối tượng Thread không thể được khởi động nhiều lần.
- Không bỏ Runnable được cung cấp và thay bằng công việc không liên quan.

Hợp đồng cho phép trả `null` khi từ chối tạo luồng. Tuy nhiên, với ThreadPoolExecutor, việc không tạo được luồng có thể làm công việc không tiến triển. Đây không phải một cơ chế giới hạn tải nên lạm dụng; giới hạn nhóm/hàng đợi và chính sách từ chối là các công cụ cần thiết kế ở đúng tầng.

## 3. Runnable mà factory nhận thường không phải một yêu cầu nghiệp vụ

Một luồng trong nhóm có thể xử lý nhiều tác vụ liên tiếp. Runnable được ThreadPoolExecutor đưa cho ThreadFactory là phần thực thi của luồng trong nhóm, bao gồm vòng nhận công việc; nó không nhất thiết là chính Runnable do một người dùng vừa submit.

```text
Executor cần thêm một luồng
    → factory.newThread(Runnable của luồng thực thi)
    → nhận Thread chưa start
    → executor khởi động Thread
    → luồng xử lý tác vụ A, rồi B, rồi C...
```

Vì thế factory được gọi **theo nhu cầu tạo luồng**, không phải được gọi cho từng tác vụ. Một nhóm đã có đủ luồng có thể nhận hàng nghìn công việc mà không gọi factory thêm lần nào.

Điều này giải thích hai hệ quả quan trọng:

1. Số lần factory tạo luồng không bằng số tác vụ đã thực hiện.
2. Bọc Runnable ở factory bằng `try/finally` chỉ bọc vòng đời của luồng thực thi; phần finally đó không tự chạy sau từng tác vụ nghiệp vụ.

Nếu cần gán hoặc thu dọn dữ liệu cho mỗi yêu cầu, hãy đặt nó quanh chính tác vụ hoặc ở các điểm móc phù hợp của executor, thay vì nhầm factory là bộ chặn từng tác vụ. [ThreadPoolExecutor: Creating new threads và Hook methods](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

## 4. Những thuộc tính thường cấu hình

| Thuộc tính | Mục đích | Giới hạn cần hiểu |
|---|---|---|
| Tên luồng | Nhận diện nhóm và số thứ tự trong log/thread dump | Không dùng tên như mã định danh bảo mật hoặc định danh tác vụ |
| Daemon | Chọn việc luồng có giữ JVM tiếp tục sống hay không | Không thay thế shutdown hoặc bảo đảm ghi xong dữ liệu |
| Độ ưu tiên | Đặt mức ưu tiên của luồng nền tảng khi có nhu cầu cụ thể | Không bảo đảm thứ tự, công bằng hay thời gian hoàn thành |
| UncaughtExceptionHandler | Nhận lỗi thoát ra khỏi luồng mà không được bắt | Không quan sát được mọi lỗi do FutureTask giữ bên trong |
| Ngữ cảnh lớp/trạng thái kế thừa | Phù hợp môi trường chạy hoặc lớp thư viện | Dễ giữ dữ liệu/ngữ cảnh lâu hơn vòng đời yêu cầu nếu không quản lý |

Tên nên thể hiện nhóm trách nhiệm, chẳng hạn `report-worker-1`, thay vì tên chung `Thread-0`. Nếu một ứng dụng có nhiều nhóm cùng loại, có thể thêm một mã nhóm cấu hình ổn định để phân biệt chúng. Không đưa mật khẩu, token hoặc dữ liệu người dùng nhạy cảm vào tên luồng.

### Daemon không phải “luồng chạy nhẹ hơn”

Luồng daemon khác ở điều kiện giữ tiến trình JVM hoạt động. Khi không còn luồng non-daemon đang chạy, JVM có thể bắt đầu kết thúc; công việc daemon không được bảo đảm sẽ ghi xong dữ liệu trước đó.

Chuyển nhóm sang daemon chỉ để chương trình thoát mà không cần dừng executor là đang bỏ qua quản lý vòng đời. Với công việc cần hoàn tất, chủ sở hữu vẫn phải shutdown và chờ theo chính sách. [Thread: Platform threads và vòng đời JVM](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html).

### Ưu tiên không thay lịch nghiệp vụ

`Thread.NORM_PRIORITY` là lựa chọn nền tảng dễ hiểu. Không tăng lên MAX_PRIORITY rồi kỳ vọng mọi tác vụ quan trọng được chạy đúng thứ tự hoặc nhanh hơn. Giới hạn đồng thời, hàng đợi và phân chia tài nguyên mới là các phần cần thiết kế để thể hiện yêu cầu phục vụ.

## 5. Bắt đầu từ defaultThreadFactory

`Executors.defaultThreadFactory()` cung cấp cấu hình nền rõ ràng: tạo luồng non-daemon, có quy tắc đặt tên và độ ưu tiên mặc định theo hợp đồng của factory. Có thể ủy quyền tạo Thread rồi chỉ sửa những thuộc tính ứng dụng cần. [Executors.defaultThreadFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html#defaultThreadFactory()).

Ví dụ minh họa trong một phương thức:

```java
AtomicInteger sequence = new AtomicInteger();
ThreadFactory base = Executors.defaultThreadFactory();
ThreadFactory named = task -> {
    Thread thread = base.newThread(task);
    thread.setName("report-worker-" + sequence.incrementAndGet());
    thread.setDaemon(false);
    return thread;
};
```

Đoạn cần import các kiểu tương ứng. `AtomicInteger` giúp việc phát số thứ tự an toàn khi factory bị gọi đồng thời. Nếu có thể dùng cùng factory từ nhiều nhóm, không giả định mọi lời gọi đều đã được một executor tuần tự hóa.

Ủy quyền cho default factory không có nghĩa mọi ngữ cảnh tự động sạch cho mọi yêu cầu. Cần phân tích riêng trạng thái theo luồng và việc kế thừa từ luồng tạo.

## 6. Chương trình đầy đủ: luồng được cấu hình và tái sử dụng

Ví dụ dùng một nhóm chỉ có một luồng và hai tác vụ trả ảnh chụp thông tin của luồng đang chạy. Do không có lỗi hoặc timeout luồng, hai tác vụ dùng lại cùng luồng. Thí nghiệm còn kiểm tra factory đã tạo luồng ở trạng thái NEW trước khi executor khởi động.

Lưu thành `ThreadFactoryDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ThreadFactoryDemo {
    record WorkerInfo(String name, boolean daemon, int priority) { }

    static final class NamedFactory implements ThreadFactory {
        private final ThreadFactory base = Executors.defaultThreadFactory();
        private final AtomicInteger created = new AtomicInteger();

        @Override
        public Thread newThread(Runnable task) {
            Thread thread = base.newThread(task);
            int number = created.incrementAndGet();
            thread.setName("report-worker-" + number);
            thread.setDaemon(false);
            thread.setPriority(Thread.NORM_PRIORITY);
            thread.setUncaughtExceptionHandler((failed, error) ->
                    System.err.println("uncaught in " + failed.getName()
                            + ": " + error.getClass().getSimpleName()));
            if (thread.getState() != Thread.State.NEW) {
                throw new IllegalStateException("Factory must return a new thread");
            }
            return thread;
        }

        int createdCount() {
            return created.get();
        }
    }

    private static WorkerInfo currentInfo() {
        Thread thread = Thread.currentThread();
        return new WorkerInfo(thread.getName(), thread.isDaemon(),
                thread.getPriority());
    }

    public static void main(String[] args) throws Exception {
        NamedFactory factory = new NamedFactory();
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(4),
                factory,
                new ThreadPoolExecutor.AbortPolicy());

        try {
            Future<WorkerInfo> first = pool.submit(ThreadFactoryDemo::currentInfo);
            WorkerInfo a = first.get(10, TimeUnit.SECONDS);
            Future<WorkerInfo> second = pool.submit(ThreadFactoryDemo::currentInfo);
            WorkerInfo b = second.get(10, TimeUnit.SECONDS);

            System.out.println("first worker: " + a.name());
            System.out.println("second worker: " + b.name());
            System.out.println("daemon: " + a.daemon());
            System.out.println("priority: " + a.priority());
            System.out.println("threads created: " + factory.createdCount());
        } finally {
            pool.shutdown();
            try {
                if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                    if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Executor did not terminate");
                    }
                }
            } catch (InterruptedException ex) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 ThreadFactoryDemo.java
java ThreadFactoryDemo
```

Stdout trên môi trường chạy thông thường cho phép ưu tiên NORM_PRIORITY:

```text
first worker: report-worker-1
second worker: report-worker-1
daemon: false
priority: 5
threads created: 1
```

Nếu môi trường giới hạn ưu tiên của nhóm luồng thấp hơn mức yêu cầu, giá trị ưu tiên thực có thể thấp hơn; không coi việc đặt ưu tiên là cam kết vượt giới hạn của môi trường. Ví dụ được thiết kế cho môi trường JDK thông thường, không phụ thuộc việc tăng ưu tiên để đúng.

Cách đọc bằng chứng:

1. Factory trả Thread ở trạng thái NEW; executor mới là bên khởi động nó.
2. Tên và thuộc tính được đặt trước khi tác vụ quan sát luồng đang chạy.
3. Hai tác vụ được gửi nhưng factory chỉ tạo một luồng; nó không phải factory cho từng công việc.
4. Phần cuối vẫn dừng executor dù luồng đã được cấu hình non-daemon rõ ràng.
5. Handler được cài để nhận lỗi chưa bắt, nhưng ví dụ không cố tạo lỗi nên không có stderr dự kiến.

## 7. UncaughtExceptionHandler không phải nơi thu mọi lỗi tác vụ

Handler được gọi khi luồng kết thúc do một lỗi không được bắt thoát khỏi phần chạy của luồng. Trong ThreadPoolExecutor thông thường, một Runnable được giao trực tiếp bằng execute và không tự bắt lỗi có thể gây ra đường này; executor có thể tạo luồng thay thế khi còn cần phục vụ công việc.

Nhưng khi gửi bằng submit, lỗi tính toán thường được lớp bọc FutureTask giữ lại. Khi đó nó không nhất thiết thoát ra làm luồng chết, nên handler không được gọi chỉ vì tác vụ thất bại. Nơi gọi cần quan sát Future bằng get hoặc có cơ chế giám sát kết quả rõ ràng.

Điểm này cũng áp dụng khi dùng execute với một FutureTask tự tạo: phương thức giao việc là execute nhưng chính đối tượng công việc giữ lỗi. Đừng kết luận dựa riêng vào tên phương thức.

Handler nên làm công việc ngắn và đáng tin: ghi nhận lỗi, thông tin nhận diện nhóm/luồng, rồi trả về. Không chạy một quy trình nghiệp vụ dài hoặc tự tạo tác vụ thử lại vô hạn ngay trong handler. Tên luồng giúp chẩn đoán; nó không thay mã công việc để xác định tác vụ nào thất bại.

## 8. Trạng thái theo luồng và bẫy kế thừa ngữ cảnh

Luồng nhóm thường tồn tại qua nhiều yêu cầu. Dữ liệu lưu trong ThreadLocal có thể theo luồng đến công việc tiếp theo nếu không được thu dọn.

Một factory có thể cấu hình thuộc tính lúc tạo luồng, nhưng không tự cập nhật ngữ cảnh theo từng tác vụ được gửi về sau. Với `InheritableThreadLocal`, việc kế thừa gắn với thời điểm tạo luồng; trong nhóm luồng, thời điểm đó có thể là lúc yêu cầu đầu tiên khiến executor bổ sung luồng, không phải thời điểm mỗi công việc được thực hiện.

Vì vậy:

- Không dựa vào factory để tự truyền người dùng hoặc mã theo dõi mới cho từng tác vụ.
- Nếu cần ngữ cảnh theo yêu cầu, chụp dữ liệu được phép truyền ở ranh giới giao việc và gán/thu dọn quanh tác vụ.
- Dùng `finally` để khôi phục hoặc remove trạng thái đúng cách sau mỗi công việc.
- Không đưa dữ liệu riêng của yêu cầu vào một cấu hình giữ suốt vòng đời luồng.

Nếu cần tùy chỉnh context class loader trong môi trường có nhiều bộ nạp lớp, phải có mục đích và quyền sở hữu rõ ràng. Giữ một bộ nạp lớp hoặc đối tượng gắn với một mô-đun đã hết vòng đời qua luồng sống lâu có thể cản giải phóng tài nguyên. Không tùy tiện thay ngữ cảnh chỉ vì factory cho phép.

## 9. Khi factory thay đổi hoặc không tạo được luồng

`setThreadFactory` của ThreadPoolExecutor ảnh hưởng các luồng được tạo về sau; nó không tự đổi tên/thuộc tính những luồng đang tồn tại. Muốn hiểu log sau thay đổi phải biết có thể có luồng cũ và mới cùng tồn tại.

Nếu factory trả null hoặc tạo luồng sai hợp đồng, việc xử lý có thể không tiến triển như dự kiến. Nếu nó ném lỗi hoặc hệ điều hành không cấp thêm tài nguyên, không thể chỉ nhìn queue còn chỗ rồi kết luận chắc chắn tác vụ sẽ chạy. Factory nên nhẹ, dễ dự đoán và được kiểm tra tại cấu hình ứng dụng.

Không dùng factory để giả vờ đặt trần số luồng bằng cách “từ lần tạo thứ n trở đi trả null”. `corePoolSize`, `maximumPoolSize`, workQueue và chính sách từ chối mới là nơi mô tả giới hạn thực thi. Bộ đếm trong factory nên là thông tin đặt tên/đo lường, không thay cơ chế nhận việc.

## 10. Java mới: Thread.Builder tạo factory, nhưng mô hình vẫn cần rõ

Trên Java 21 trở lên, có thể tạo factory cho platform thread qua builder, chẳng hạn một nhóm tên có số thứ tự. Đây là một cách biểu đạt mới hơn cho cùng trách nhiệm cấu hình luồng; ví dụ Java 17 của bài vẫn dùng hợp đồng ThreadFactory thông thường.

Java mới còn có factory cho virtual thread và executor một virtual thread mỗi tác vụ. Không nên tự thay ThreadFactory của một nhóm platform thread bằng factory virtual thread rồi coi đó là thiết kế tương đương. Virtual thread hướng tới mô hình dùng theo từng tác vụ; giới hạn truy cập tài nguyên phía sau cần được quản lý đúng với tài nguyên đó. Bài tập trung ThreadFactory trong nhóm luồng tùy chỉnh, không yêu cầu chuyển mô hình thực thi. [Thread.Builder và các loại luồng](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html).

## 11. Tự kiểm tra và thực hành

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| Factory vừa tạo vừa phải start luồng | Trả luồng mới chưa khởi động; executor start |
| Mỗi submit gọi factory một lần | Chỉ khi cần tạo luồng |
| Runnable truyền vào factory là đúng một yêu cầu người dùng | Nó thường là phần thực thi của luồng nhóm, có thể xử lý nhiều tác vụ |
| Đặt handler là thấy mọi lỗi submit | Cần quan sát Future vì lớp bọc có thể giữ lỗi |
| Daemon giúp tự hoàn thành công việc khi JVM thoát | Không bảo đảm công việc hoàn tất |
| Đổi factory sẽ sửa mọi luồng đang chạy | Thường chỉ ảnh hưởng luồng tạo sau đó |
| Dùng biến int tăng đơn giản luôn đủ đặt tên | Factory dùng chung/đồng thời cần phát số an toàn |

Tự trả lời:

1. Vì sao không gọi start trong newThread? **Executor cần nhận Thread chưa khởi động để quản lý việc chạy.**
2. Hai tác vụ trong ví dụ dùng cùng tên luồng có nghĩa chúng là cùng tác vụ không? **Không.** Một luồng xử lý hai công việc riêng.
3. Gắn finally quanh Runnable ở factory có tự thu dọn ThreadLocal sau mỗi tác vụ không? **Không**, vì đó thường là vòng đời luồng nhóm; phải thu dọn ở ranh giới tác vụ.
4. Có nên chọn daemon chỉ để khỏi viết shutdown không? **Không.** Đây là hai quyết định khác nhau về vòng đời.

Thực hành: đổi tiền tố tên thành `invoice-worker-` và kiểm tra hai tác vụ vẫn dùng lại cùng một luồng. Sau đó tạo một executor thứ hai dùng cùng factory, thu kết quả từ mỗi nhóm để thấy số thứ tự do factory quản lý chung. Dừng cả hai executor trong mọi đường thoát; không dựa vào giá trị ưu tiên hay thời gian chạy để dự đoán thứ tự công việc giữa hai nhóm.
