# RejectedExecutionHandler và tình huống từ chối tác vụ

## 1. Từ chối là một kết quả tiếp nhận, không phải lỗi bên trong tác vụ

Một dịch vụ đã có đủ luồng đang chạy và hàng đợi đã đầy. Người dùng gửi thêm yêu cầu xuất báo cáo. Hệ thống cần trả lời rõ: có nhận việc này không, có xử lý ngay trên luồng gửi không hay có cơ chế khác?

`RejectedExecutionHandler` là chính sách được `ThreadPoolExecutor` gọi khi không thể tiếp nhận tác vụ theo đường thực thi thông thường.

Cần phân biệt:

- **Từ chối:** công việc không được bộ thực thi nhận theo chính sách hiện tại.
- **Lỗi tác vụ:** công việc đã chạy nhưng phần thân ném ngoại lệ.
- **Hủy:** công việc hoặc Future được yêu cầu chuyển sang trạng thái hủy.

Không thể thay thế ba ý nghĩa này bằng một thông báo chung “xử lý thất bại” mà vẫn giữ đủ thông tin điều phối.

Các API trong bài có từ Java 5 và vẫn áp dụng trên Java hiện đại. Các chương trình minh họa chạy với Java 17+.

## 2. Khi nào handler được gọi?

Hai tình huống điển hình:

1. **Bão hòa:** đã đạt giới hạn luồng và không xếp thêm được vào hàng đợi.
2. **Vòng đời đã đóng tiếp nhận:** bộ thực thi đã được shutdown.

Mô hình gửi việc thường gặp:

```text
execute / submit
    |
    +-- còn tiếp nhận và có thể tạo luồng? -> tạo luồng
    |
    +-- có thể xếp vào hàng đợi? ----------> xếp chờ
    |
    +-- có thể tạo thêm tới max? ----------> tạo luồng bổ sung
    |
    +-- không thể tiếp nhận ---------------> rejection handler
```

Triển khai còn kiểm tra lại trạng thái để xử lý cạnh tranh. Ví dụ bộ thực thi có thể chuyển sang shutdown ngay khi một luồng khác đang gửi công việc; đừng dùng phép kiểm tra `isShutdown()` trước đó làm bảo đảm lần gửi sẽ được nhận.

Chữ ký handler:

```java
void rejectedExecution(Runnable task, ThreadPoolExecutor executor);
```

Nó nhận tác vụ không được tiếp nhận và bộ thực thi liên quan. Handler có thể ném `RejectedExecutionException` để báo cho luồng gửi. Không có một “luồng xử lý từ chối” riêng tự động được tạo ra cho callback này. [Tài liệu RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html)

## 3. Bốn chính sách có sẵn

| Chính sách | Khi bão hòa | Sau shutdown |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` | Ném `RejectedExecutionException` |
| `CallerRunsPolicy` | Chạy tác vụ ngay trên luồng gọi | Bỏ tác vụ |
| `DiscardPolicy` | Bỏ tác vụ | Bỏ tác vụ |
| `DiscardOldestPolicy` | Lấy bỏ phần tử kế tiếp ở đầu hàng đợi rồi thử execute lại | Bỏ tác vụ mới |

`AbortPolicy` là chính sách mặc định của các constructor ThreadPoolExecutor khi không truyền handler riêng.

“Không ném lỗi” không tự có nghĩa công việc đã được nhận hoặc sẽ hoàn thành. Hai chính sách bỏ việc có thể làm đường gửi trả về bình thường nhưng không có kết quả thực thi.

Các chính sách này vẫn tồn tại trong API hiện đại, nhưng không phải mọi chính sách đều phù hợp với công việc quan trọng cần kết quả. Chọn theo hợp đồng công việc và cách bên gọi quan sát trạng thái. [Tài liệu ThreadPoolExecutor: Rejected tasks](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

## 4. Thí nghiệm: cùng một ngoại lệ, hai nguyên nhân khác nhau

Cấu hình một luồng và một vị trí chờ. Chốt giữ A đang chạy; B nằm trong hàng đợi; C không còn chỗ. Sau đó gọi shutdown rồi gửi D.

Tệp **RejectionCausesDemo.java**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class RejectionCausesDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.SECONDS,
                new ArrayBlockingQueue<Runnable>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> a = pool.submit(() -> {
                started.countDown();
                release.await();
                return "A";
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("A did not start");
            }
            Future<String> b = pool.submit(() -> "B");

            try {
                pool.submit(() -> "C");
            } catch (RejectedExecutionException ex) {
                System.out.println("saturated=RejectedExecutionException");
            }

            pool.shutdown();
            try {
                pool.submit(() -> "D");
            } catch (RejectedExecutionException ex) {
                System.out.println("afterShutdown=RejectedExecutionException");
            }

            release.countDown();
            System.out.println("acceptedResults=" + a.get() + "," + b.get());

            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
            System.out.println("terminated=" + pool.isTerminated());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```shell
javac --release 17 RejectionCausesDemo.java
java RejectionCausesDemo
```

Stdout:

```text
saturated=RejectedExecutionException
afterShutdown=RejectedExecutionException
acceptedResults=A,B
terminated=true
```

Hai ngoại lệ đều xuất hiện ngay ở lời gọi gửi việc. Không có Future được trả về cho C hoặc D để sau đó gọi `get()` và nhận ExecutionException.

A và B đã được nhận trước shutdown vẫn hoàn tất. D bị từ chối vì vòng đời tiếp nhận đã kết thúc; tăng số luồng không phải cách sửa đúng cho trường hợp này.

Trong vận hành, cần kết hợp trạng thái bộ thực thi, thời điểm dừng và số đo tải để tìm nguyên nhân. Không phân tích message của ngoại lệ như một giao thức phân loại ổn định.

## 5. CallerRunsPolicy thay đổi nơi chạy và độ trễ bên gửi

Khi bộ thực thi chưa shutdown và không nhận thêm được, CallerRunsPolicy gọi chạy tác vụ trên luồng đang gửi. Điều này có thể làm chậm tốc độ gửi, vì luồng đó phải làm việc thay vì tiếp tục phát thêm yêu cầu.

Nhưng hệ quả không chỉ là giảm tốc:

- Luồng HTTP có thể phải xử lý công việc nền nặng.
- Luồng giao diện có thể bị giữ lâu.
- Tác vụ có thể chạy trong ngữ cảnh ThreadLocal của bên gửi.
- Luồng gửi có thể đang giữ khóa mà tác vụ không nên phụ thuộc.
- Số tác vụ đang chạy trên toàn ứng dụng có thể vượt số luồng của bộ thực thi.

Với `submit`, đối tượng bao tác vụ thường giữ kết quả/lỗi trong Future ngay cả khi chạy trên luồng gửi. Vì thế, không mặc định lỗi nghiệp vụ sẽ thoát trực tiếp ra khỏi submit chỉ vì dùng CallerRunsPolicy.

Sau shutdown, CallerRunsPolicy **bỏ tác vụ**, không chạy trên bên gửi và không tự ném lỗi. Đây là khác biệt quan trọng khi mã gọi vẫn mong có kết quả. [Tài liệu CallerRunsPolicy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.CallerRunsPolicy.html)

## 6. Thí nghiệm: submit trả Future chưa chắc công việc sẽ có kết quả

Chương trình so sánh hai tình huống:

- CallerRunsPolicy chạy việc bị từ chối do bão hòa trên main, nhưng bỏ việc sau shutdown.
- DiscardPolicy bỏ việc khi bão hòa; Future vẫn chưa hoàn tất.

Tệp **PolicyFutureDemo.java**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class PolicyFutureDemo {
    private static ThreadPoolExecutor create(
            java.util.concurrent.RejectedExecutionHandler policy) {
        return new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.SECONDS,
                new ArrayBlockingQueue<Runnable>(1), policy);
    }

    public static void main(String[] args) throws Exception {
        inspectCallerRuns();
        inspectDiscard();
    }

    private static void inspectCallerRuns() throws Exception {
        ThreadPoolExecutor pool =
                create(new ThreadPoolExecutor.CallerRunsPolicy());
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<?> running = pool.submit(() -> {
                started.countDown();
                release.await();
                return null;
            });
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }
            Future<Integer> queued = pool.submit(() -> 2);

            Thread sender = Thread.currentThread();
            Future<Boolean> extra =
                    pool.submit(() -> Thread.currentThread() == sender);
            System.out.println("callerRuns.sameThread=" + extra.get());

            pool.shutdown();
            Future<Integer> late = pool.submit(() -> 4);
            System.out.println("callerRuns.lateDone=" + late.isDone());

            late.cancel(false);
            System.out.println("callerRuns.lateCancelledAfterCleanup="
                    + late.isCancelled());

            release.countDown();
            running.get();
            queued.get();
        } finally {
            release.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }

    private static void inspectDiscard() throws Exception {
        ThreadPoolExecutor pool =
                create(new ThreadPoolExecutor.DiscardPolicy());
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<?> running = pool.submit(() -> {
                started.countDown();
                release.await();
                return null;
            });
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }
            Future<Integer> queued = pool.submit(() -> 2);
            Future<Integer> dropped = pool.submit(() -> 3);

            System.out.println("discard.done=" + dropped.isDone());
            try {
                dropped.get(10, TimeUnit.MILLISECONDS);
            } catch (TimeoutException ex) {
                System.out.println("discard.get=TimeoutException");
            }

            dropped.cancel(false);
            System.out.println("discard.cancelledAfterCleanup="
                    + dropped.isCancelled());

            release.countDown();
            running.get();
            queued.get();
        } finally {
            release.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 PolicyFutureDemo.java
java PolicyFutureDemo
```

Stdout:

```text
callerRuns.sameThread=true
callerRuns.lateDone=false
callerRuns.lateCancelledAfterCleanup=true
discard.done=false
discard.get=TimeoutException
discard.cancelledAfterCleanup=true
```

Chốt giữ công việc đang chạy và vị trí chờ vẫn bị chiếm, nên các nhánh bão hòa được tạo một cách xác định. Không dùng độ dài tác vụ ngẫu nhiên để đoán lúc hàng đợi đã đầy.

Future bị bỏ không tự trở thành “thất bại”. Nếu dùng `get()` không timeout, bên gọi có thể chờ vô hạn. Thí nghiệm chủ động hủy các Future đó để kết thúc trạng thái, không coi việc bỏ tác vụ là cách viết ứng dụng thông thường.

Hủy Future của công việc chưa chạy trong ví dụ không đóng bộ thực thi; công việc A/B vẫn được giải phóng và lấy kết quả riêng.

## 7. DiscardOldestPolicy bỏ công việc nào?

Tên “oldest” cần đọc theo hàng đợi: chính sách lấy bỏ phần tử kế tiếp mà bộ thực thi sẽ lấy từ queue, rồi thử lại việc mới, nếu chưa shutdown.

Với hàng đợi FIFO, đó thường là công việc chờ lâu nhất. Nó không phải tác vụ đang chạy lâu nhất và cũng không phải công việc ít quan trọng nhất.

Các rủi ro:

- Bên gửi công việc cũ có thể đã được báo tiếp nhận.
- Future của phần tử bị lấy bỏ không tự có trạng thái kết thúc.
- Với hàng đợi có thứ tự khác FIFO, phần tử đầu có thể có ý nghĩa khác.
- Lần execute thử lại vẫn có thể thất bại; không có bảo đảm nó nhận ngay.
- Không phải mọi loại queue đều phù hợp với việc bỏ đầu rồi thử lại.

Đây là lựa chọn hiếm khi phù hợp nếu phải theo dõi hoàn tất hoặc lưu lỗi. Tài liệu chính sách cũng nhấn mạnh trách nhiệm hủy/ghi nhận phần việc bị loại. [Tài liệu DiscardOldestPolicy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardOldestPolicy.html)

Không dùng nó cho hóa đơn hay báo cáo đã cam kết xử lý chỉ vì muốn ưu tiên yêu cầu mới hơn. Nếu nghiệp vụ cho phép thay thế “bản cập nhật trạng thái cũ” bằng bản mới, hãy biểu đạt quy tắc gộp/thay thế có danh tính và kết quả rõ ràng.

## 8. Handler tùy chỉnh: giữ phản hồi tường minh

Một handler có thể thêm số đo rồi từ chối bằng ngoại lệ:

```java
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.atomic.AtomicLong;

AtomicLong rejectedCount = new AtomicLong();

RejectedExecutionHandler handler = (task, executor) -> {
    rejectedCount.incrementAndGet();
    throw new RejectedExecutionException(
            executor.isShutdown()
                    ? "Executor no longer accepts work"
                    : "Executor could not accept work");
};
```

Đây là đoạn khai báo trong phương thức, không phải chương trình độc lập. Sau đó truyền `handler` vào constructor ThreadPoolExecutor.

Nó không âm thầm bỏ công việc, và không cố chạy I/O nặng trong callback. `AtomicLong` hỗ trợ cập nhật bộ đếm khi nhiều luồng đồng thời bị từ chối.

Thông báo dựa trên trạng thái quan sát tại callback hỗ trợ chẩn đoán, không phải bằng chứng nguyên nhân tuyệt đối trong mọi cạnh tranh: shutdown có thể xảy ra đồng thời với bão hòa. Giữ số đo và ngữ cảnh vận hành thay vì xây hợp đồng nghiệp vụ bằng cách parse chuỗi message.

Nếu handler quyết định bỏ hoặc thay thế Future, phải thiết kế cách hoàn tất/hủy handle mà bên gọi đang giữ. Không giả định mọi Runnable truyền tới handler đều có kiểu Future; các cơ chế bao công việc có thể khác nhau.

## 9. Những cách “chữa” dễ tạo vấn đề mới

### Chờ vô hạn trong handler

Tự gọi `getQueue().put(task)` để tránh mất việc có thể giữ luồng gửi rất lâu và bỏ qua quy trình kiểm tra vòng đời của bộ thực thi. Nếu chính các luồng làm việc đang gửi tác vụ con rồi bị giữ chờ queue, còn có thể làm hệ thống không tiến triển.

Muốn tiếp nhận có thời hạn, hãy thiết kế điều tiết ở tầng thích hợp với hợp đồng timeout và shutdown rõ ràng; không lén biến callback từ chối thành hàng đợi vô hạn khác.

### Gọi lại execute không giới hạn

Handler gọi ngay `executor.execute(task)` khi tình trạng chưa thay đổi có thể tiếp tục bị từ chối và gọi lại chính handler. Không xây vòng thử lại vô hạn hoặc đệ quy không giới hạn.

Thử lại cần giới hạn số lượt, thời hạn, khoảng chờ phù hợp và kiểm tra quyền chạy lại công việc. Nếu hệ thống đang shutdown, thử lại trên cùng instance không thể khôi phục vòng đời tiếp nhận.

### Tạo luồng mới cho mọi tác vụ bị từ chối

Cách này có thể phá vỡ chính giới hạn tài nguyên mà bộ luồng được tạo để áp dụng. Chuyển việc sang một bộ thực thi khác cũng chỉ hữu ích nếu nơi đó có ngân sách và chính sách tiếp nhận độc lập; nếu không, bạn chỉ chuyển điểm tích tụ tải.

### Bắt ngoại lệ rồi vẫn báo thành công

Nếu bên gọi nhận RejectedExecutionException nhưng trả “đã nhận báo cáo” cho người dùng, hệ thống đã tạo lời hứa không có công việc tương ứng. Phản hồi phải phân biệt chưa nhận, đã nhận và đã hoàn tất.

## 10. Đặt xử lý nghiệp vụ ở ranh giới gửi

Handler biết bộ thực thi, nhưng thường không có đủ ngữ cảnh để quyết định mọi chính sách nghiệp vụ. Tầng gửi biết người dùng, thời hạn và loại thao tác.

Một cách phân chia:

- Handler: ghi số đo gọn và phản hồi không nhận được công việc.
- Tầng gửi: chuyển thành trạng thái bận/đã dừng theo hợp đồng API.
- Tầng quản lý công việc: lưu định danh, kết quả, thử lại hoặc lịch chạy nếu có yêu cầu.
- Bên sở hữu vòng đời: quyết định lúc đóng và xử lý việc đã nhận.

Ví dụ, công việc nền “làm mới dữ liệu gợi ý” có thể được bỏ theo quy tắc riêng; yêu cầu xuất báo cáo có người đang chờ thì cần trạng thái thất bại tiếp nhận rõ ràng. Không dùng cùng một chính sách chỉ vì cả hai đều là Runnable.

Nếu cần bảo đảm công việc được tiếp nhận bền vững qua việc tiến trình dừng, phải có cơ chế lưu công việc bền vững phù hợp. Bộ luồng và hàng đợi RAM không tự cung cấp bảo đảm đó.

## 11. Quan sát để phân biệt quá tải với lỗi vòng đời

Theo dõi số lần từ chối cùng các thông tin:

- Bộ thực thi đang hoạt động, shutdown hay terminating.
- Số luồng và mức hoạt động.
- Kích thước hàng đợi, thời gian chờ và thời gian xử lý.
- Loại công việc và mã theo dõi thích hợp.
- Tốc độ gửi, hoàn thành và phản hồi từ tài nguyên phụ thuộc.

Các số đo đọc riêng lẻ không phải một ảnh chụp nguyên tử của toàn hệ thống. Không chờ queue size bằng 0 rồi cho rằng lần gửi kế tiếp chắc chắn được nhận, cũng không cho rằng cứ queue đầy là phải tăng max.

Nếu rejection tăng đúng khi dừng ứng dụng, hãy xem việc ngừng nguồn gửi và quyền sở hữu bộ thực thi. Nếu rejection tăng trong giờ tải cao, hãy xét ngân sách xử lý, độ trễ tác vụ và chính sách tiếp nhận.

Không ghi toàn bộ đối tượng tác vụ vào log nếu nó chứa dữ liệu nhạy cảm hoặc dữ liệu lớn. Định danh thao tác và số đo thường hữu ích hơn.

## 12. Tự kiểm tra hợp đồng từ chối

Với một tác vụ gửi qua submit:

1. Nếu dùng AbortPolicy và bị từ chối, Future có được trả về không?
2. Nếu dùng CallerRunsPolicy lúc bão hòa, luồng nào có thể chạy công việc?
3. Nếu cùng chính sách đó sau shutdown, Future có chắc hoàn tất không?
4. Nếu bỏ tác vụ, ai báo cho người đang chờ?
5. Nếu thử lại, làm sao giới hạn thời gian và tránh trùng tác dụng phụ?
6. Số lần từ chối đến từ thiếu tài nguyên hay từ vòng đời đã đóng?

Một chính sách từ chối tốt không chỉ giúp bộ luồng giữ giới hạn. Nó còn giữ lời hứa tiếp nhận công việc rõ ràng với người gọi và tránh để kết quả bị bỏ lửng.
