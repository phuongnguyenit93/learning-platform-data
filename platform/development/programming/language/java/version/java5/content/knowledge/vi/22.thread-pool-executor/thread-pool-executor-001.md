# Các thành phần của bộ luồng thực thi

## 1. Bộ luồng không chỉ là một danh sách Thread

Giả sử ứng dụng xuất báo cáo nền. Nếu mỗi yêu cầu tự tạo một luồng, lượng luồng có thể tăng theo lượng yêu cầu. Nếu chỉ có một luồng, yêu cầu chậm có thể giữ toàn bộ việc phía sau.

`ThreadPoolExecutor` cho phép mô tả cách phân phối công việc: giữ một số luồng làm việc, xếp tác vụ chưa xử lý vào hàng đợi, mở rộng số luồng trong giới hạn và quyết định phản hồi khi không nhận thêm được.

Một cấu hình chỉ có ý nghĩa khi các thành phần phù hợp với nhau. Ví dụ, đặt `maximumPoolSize = 20` không bảo đảm bộ thực thi sẽ tăng tới 20 luồng nếu hàng đợi vẫn luôn nhận được tác vụ.

Bài này xây dựng mô hình các thành phần trước khi đi sâu vào từng tham số. Các ví dụ dùng Java 17+ và những cơ chế vẫn áp dụng trên Java hiện đại.

## 2. Bản đồ các thành phần

```text
Bên gửi công việc
    |
    +-- execute(Runnable) / submit(...)
            |
            v
    ThreadPoolExecutor
        |
        +-- trạng thái vòng đời: còn tiếp nhận hay đang dừng?
        +-- chính sách số luồng: corePoolSize / maximumPoolSize
        +-- hàng đợi công việc: BlockingQueue<Runnable>
        +-- tạo luồng: ThreadFactory
        +-- thu hồi luồng nhàn rỗi: keepAliveTime
        +-- không nhận được việc: RejectedExecutionHandler
        |
        v
    Luồng làm việc
        -> chạy một tác vụ
        -> lấy tác vụ tiếp theo nếu còn
        -> kết thúc khi chính sách/vòng đời yêu cầu
```

| Thành phần | Câu hỏi nó trả lời |
| --- | --- |
| Tác vụ | Công việc cần làm là gì? |
| Luồng làm việc | Ai đang thực thi phần mã đó? |
| Hàng đợi | Công việc chưa được thực hiện được giữ ở đâu? |
| Core/max | Bộ thực thi tạo và giữ bao nhiêu luồng? |
| Keep-alive | Luồng nhàn rỗi được giữ bao lâu theo chính sách? |
| ThreadFactory | Luồng mới được tạo và cấu hình thế nào? |
| Rejection handler | Phản hồi ra sao khi không nhận được tác vụ? |
| Vòng đời | Khi nào ngừng nhận việc và kết thúc? |
| Future/quan sát | Kết quả hoặc lỗi được ai theo dõi? |

`ThreadPoolExecutor` triển khai `ExecutorService`. Giao diện cung cấp thao tác gửi và quản lý vòng đời; lớp cụ thể này cung cấp thêm chính sách bộ luồng, hàng đợi và điểm mở rộng. [Tài liệu ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

## 3. Tác vụ khác luồng làm việc

Một tác vụ thường được mô tả bằng:

- `Runnable`: thực hiện công việc, không trả giá trị nghiệp vụ.
- `Callable<T>`: thực hiện công việc và trả giá trị kiểu `T`, có thể ném checked exception.

Một luồng làm việc có thể thực hiện **nhiều tác vụ nối tiếp nhau** trong suốt đời sống của nó. Do đó, không có quan hệ “mỗi tác vụ tương ứng một luồng mới” trong mô hình bộ luồng.

Khi gọi `submit`, tác vụ thường được bao thành một đối tượng có khả năng vừa chạy vừa lưu kết quả/trạng thái, chẳng hạn `FutureTask`. Vì vậy:

- Phần tử trong hàng đợi có thể là đối tượng bao tác vụ.
- Tác vụ lỗi có thể được lưu trong Future để bên gọi quan sát.
- Tên luồng không phải mã định danh của tác vụ.
- Dữ liệu ngữ cảnh đặt trên luồng có thể tồn tại tới tác vụ sau nếu không dọn đúng cách.

Bộ thực thi điều phối việc chạy nhưng không tự làm mọi dữ liệu của tác vụ trở nên an toàn khi dùng chung. Hai tác vụ cùng sửa một collection không an toàn vẫn cần thiết kế đồng bộ hoặc phân quyền sở hữu dữ liệu riêng.

## 4. Các tham số chính của constructor

Dạng constructor thể hiện đủ các lựa chọn cơ bản:

```java
ThreadPoolExecutor(
        int corePoolSize,
        int maximumPoolSize,
        long keepAliveTime,
        TimeUnit unit,
        BlockingQueue<Runnable> workQueue,
        ThreadFactory threadFactory,
        RejectedExecutionHandler handler)
```

Đây là sơ đồ chữ ký, không phải câu lệnh khởi tạo có thể chạy riêng.

### Core và maximum

`corePoolSize` là ngưỡng luồng cốt lõi dùng trong chính sách tạo/giữ luồng. Mặc định, các luồng được tạo khi có nhu cầu; core bằng 4 không tự có nghĩa đã tồn tại bốn luồng ngay sau constructor. Có phương thức prestart khi cần khởi tạo sớm.

`maximumPoolSize` là giới hạn trên của số luồng trong bộ. Nó phối hợp với hàng đợi: khi đã đạt core, bộ thực thi thường ưu tiên xếp việc vào hàng đợi trước khi tạo thêm luồng tới max.

Điều kiện cấu hình cơ bản gồm core không âm, max dương và max không nhỏ hơn core. Một con số hợp lệ về cú pháp chưa chứng minh cấu hình phù hợp với tải thực tế.

### Keep-alive và đơn vị thời gian

`keepAliveTime` mô tả thời gian nhàn rỗi trước khi một số luồng được thu hồi theo chính sách. Mặc định nó áp dụng cho các luồng vượt core; có thể cho core timeout bằng cấu hình riêng với keep-alive dương.

Nó **không phải** thời hạn chạy của một tác vụ. Tác vụ chạy 10 phút không tự bị hủy chỉ vì keep-alive đặt 30 giây.

## 5. Hàng đợi và số luồng phải được đọc cùng nhau

Ở trạng thái còn tiếp nhận, mô hình gửi việc có thể tóm tắt:

1. Nếu số luồng nhỏ hơn core, thử tạo luồng để nhận tác vụ.
2. Nếu đã đạt core, thử xếp tác vụ vào hàng đợi.
3. Nếu hàng đợi không nhận được, thử tạo thêm luồng tới max.
4. Nếu vẫn không nhận được hoặc bộ thực thi đã dừng, dùng chính sách từ chối.

Đây là mô hình giải thích cho cấu hình thông thường; triển khai còn phải kiểm tra lại trạng thái và xử lý cạnh tranh giữa các luồng. Không dùng phép đọc `getPoolSize()` rồi tự thao tác hàng đợi để mô phỏng thuật toán bên ngoài.

| Loại hàng đợi | Ảnh hưởng điển hình |
| --- | --- |
| Có giới hạn, như `ArrayBlockingQueue` | Có thể đầy; sau core, max có cơ hội được dùng khi không xếp thêm được |
| Không đặt giới hạn dung lượng riêng, như `LinkedBlockingQueue` mặc định | Có thể tiếp tục tích tác vụ chờ; max thường không giúp mở rộng vượt core |
| Chuyển giao trực tiếp, như `SynchronousQueue` | Không có vùng lưu công việc chờ; cần một bên nhận hoặc khả năng tạo luồng |

Tên `BlockingQueue` không có nghĩa `execute` luôn chặn bên gửi để chờ hàng đợi có chỗ. Giao diện hàng đợi có nhiều kiểu thao tác, gồm `offer` trả ngay và `put` có chờ; chính cách bộ thực thi dùng nó mới quyết định hành vi. [Tài liệu BlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

Hàng đợi giới hạn 100 phần tử chỉ giới hạn số phần tử, không giới hạn chính xác số byte. Một tác vụ giữ vùng dữ liệu lớn có thể tốn bộ nhớ hơn nhiều tác vụ nhỏ.

## 6. Thí nghiệm: nhìn thấy luồng, hàng đợi và từ chối cùng phối hợp

Cấu hình:

```text
core = 1
max = 2
queue capacity = 1
rejection = AbortPolicy
```

Ta giữ hai tác vụ đang chạy bằng chốt:

- A tạo luồng cốt lõi rồi chờ.
- B vào hàng đợi.
- C không vào được hàng đợi đã đầy, nên tạo luồng thứ hai rồi chờ.
- D không còn chỗ trong hàng đợi hoặc bộ luồng, nên bị từ chối.

Tệp **PoolPartsDemo.java**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PoolPartsDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger createdThreads = new AtomicInteger();
        AtomicInteger rejections = new AtomicInteger();
        ThreadFactory base = Executors.defaultThreadFactory();

        ThreadFactory namedFactory = runnable -> {
            Thread thread = base.newThread(runnable);
            thread.setName("report-worker-" + createdThreads.incrementAndGet());
            return thread;
        };

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 2,
                30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<Runnable>(1),
                namedFactory,
                (task, executor) -> {
                    rejections.incrementAndGet();
                    new ThreadPoolExecutor.AbortPolicy()
                            .rejectedExecution(task, executor);
                }
        );

        CountDownLatch aStarted = new CountDownLatch(1);
        CountDownLatch cStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> a = pool.submit(() -> {
                aStarted.countDown();
                release.await();
                return "A";
            });

            if (!aStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("A did not start");
            }

            Future<String> b = pool.submit(() -> "B");
            Future<String> c = pool.submit(() -> {
                cStarted.countDown();
                release.await();
                return "C";
            });

            if (!cStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("C did not start");
            }

            System.out.println("createdThreads=" + createdThreads.get());
            System.out.println("poolSize=" + pool.getPoolSize());
            System.out.println("queueSize=" + pool.getQueue().size());

            try {
                pool.submit(() -> "D");
            } catch (RejectedExecutionException ex) {
                System.out.println("D=rejected");
            }
            System.out.println("rejections=" + rejections.get());

            release.countDown();
            System.out.println("results=" + a.get() + "," + b.get() + "," + c.get());

            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
            System.out.println("terminated=" + pool.isTerminated());
        } finally {
            release.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Executor termination was not confirmed");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 PoolPartsDemo.java
java PoolPartsDemo
```

Stdout khi hoàn tất bình thường:

```text
createdThreads=2
poolSize=2
queueSize=1
D=rejected
rejections=1
results=A,B,C
terminated=true
```

Các chốt giữ A và C chưa thể hoàn tất, nên B vẫn ở hàng đợi khi chụp số đo. Chương trình không dùng `sleep` để đoán trạng thái.

C được gửi sau B nhưng bắt đầu trước B vì nó được giao trực tiếp cho luồng bổ sung. Vì vậy, dù hàng đợi có thứ tự FIFO, không suy ra toàn bộ bộ thực thi nhiều luồng sẽ bắt đầu hoặc hoàn thành mọi tác vụ theo thứ tự gửi.

Dòng `results=A,B,C` do mã lấy Future theo thứ tự đó, không phải nhật ký thứ tự thực thi.

Số 30 giây trong constructor không giữ chương trình chờ 30 giây lúc đóng: keep-alive và quy trình shutdown là các cơ chế khác nhau.

## 7. ThreadFactory tạo tài nguyên thực thi

`ThreadFactory` nhận một `Runnable`, trả luồng mới chưa khởi chạy. Bộ thực thi sẽ khởi chạy luồng đó. Factory có thể đặt tên, chính sách daemon, mức ưu tiên hoặc handler lỗi thoát khỏi luồng.

Trong chương trình, `createdThreads` tăng khi cần luồng mới, không tăng cho mỗi tác vụ. Một luồng có thể xử lý nhiều công việc; luồng thay thế cũng là một lần tạo mới.

Factory không được gọi `start()` trước khi trả luồng hoặc tái sử dụng cùng một đối tượng Thread đã chạy. Nếu factory không tạo được luồng, khả năng xử lý công việc có thể bị ảnh hưởng; không dùng cách trả null như cơ chế kiểm soát tải tùy tiện. [Tài liệu ThreadFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadFactory.html)

Tên theo vai trò như `report-worker-2` giúp đọc log/thread dump. Mã báo cáo cụ thể nên nằm trong trường nhật ký riêng. Đổi tên không giải quyết tranh chấp dữ liệu hay giới hạn tốc độ xử lý.

## 8. RejectedExecutionHandler là phần của hợp đồng tiếp nhận

Khi bộ thực thi không nhận được việc, phải có phản hồi rõ ràng. Handler được gọi ở tình huống như hết chỗ hoặc bộ thực thi đã shutdown. [Tài liệu RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html)

| Chính sách có sẵn | Hành vi chính | Cần hiểu gì? |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` | Bên gửi phải xử lý trạng thái không được nhận |
| `CallerRunsPolicy` | Bên gửi chạy tác vụ nếu bộ thực thi chưa shutdown | Có thể làm chậm luồng gửi; sau shutdown tác vụ bị bỏ |
| `DiscardPolicy` | Bỏ tác vụ | Không phù hợp khi bên gọi cần chắc chắn có kết quả |
| `DiscardOldestPolicy` | Bỏ phần tử đầu hàng đợi rồi thử nhận lại nếu chưa shutdown | Có thể làm mất công việc đã nhận; cần thiết kế rất cẩn thận |

Chọn chính sách không chỉ là chọn cách in lỗi. Nó thay đổi nơi tác vụ chạy, độ trễ của bên gửi và việc công việc có được thực hiện hay không.

Ví dụ dùng `AbortPolicy` để D bị từ chối một cách quan sát được. Nếu đổi sang `CallerRunsPolicy`, D có thể chạy trên luồng `main` thay vì một luồng trong bộ. Do đó, max là giới hạn luồng của bộ, không phải trong mọi cấu hình đều là giới hạn tuyệt đối số tác vụ trên toàn ứng dụng.

Một handler bỏ tác vụ mà không hoàn tất/hủy đối tượng Future có thể khiến bên gọi chờ kết quả vô hạn. Không dùng chính sách bỏ qua rồi vẫn báo tác vụ đã được tiếp nhận thành công.

## 9. Vòng đời bảo vệ ranh giới tiếp nhận

Các thành phần trên chỉ hoạt động trong vòng đời của bộ thực thi:

- Khi hoạt động, áp dụng chính sách tạo luồng/xếp hàng/từ chối.
- `shutdown()` ngừng nhận mới, cho việc đã nhận tiếp tục.
- `shutdownNow()` cố dừng việc đang chạy và trả việc chưa bắt đầu.
- `awaitTermination` dùng để chờ và xác nhận kết thúc.

Hàng đợi không có nghĩa tự đóng chung với tài nguyên ứng dụng. `BlockingQueue` không có thao tác shutdown nội tại; bộ thực thi điều phối trạng thái dừng của chính nó.

Đóng bộ luồng không tự đóng kết nối dữ liệu mà tác vụ sử dụng. Bên sở hữu ứng dụng cần dừng tiếp nhận, chờ/hủy công việc theo chính sách rồi xử lý tài nguyên phụ thuộc.

Quên đóng một bộ thực thi với luồng non-daemon có thể khiến tiến trình chưa thoát. Chuyển luồng thành daemon không thay thế trách nhiệm hoàn tất hoặc hủy công việc.

## 10. Quan sát đúng thành phần để tìm đúng vấn đề

| Quan sát | Điều có thể cần kiểm tra |
| --- | --- |
| Hàng đợi tăng liên tục | Tốc độ nhận vượt xử lý; tác vụ chậm; tài nguyên phụ thuộc |
| Số luồng không tăng tới max | Hàng đợi vẫn nhận được việc; cấu hình core/queue |
| Luồng hoạt động nhiều nhưng CPU thấp | Chờ I/O, chờ khóa hoặc giới hạn dịch vụ ngoài |
| Rejection tăng | Bão hòa, đã shutdown hoặc chính sách tiếp nhận không phù hợp |
| Future không có kết quả lâu | Tác vụ bị treo, phụ thuộc nhau, bị bỏ qua hoặc thiếu thời hạn |

`getPoolSize()`, `getActiveCount()`, số tác vụ hoàn thành và kích thước hàng đợi là thông tin quan sát, không phải một giao dịch chụp trạng thái nguyên tử chung. Giá trị có thể thay đổi ngay khi đọc.

Thí nghiệm giữ các tác vụ tại chốt nên những số đo cụ thể ổn định ở mốc kiểm tra. Trong vận hành, không dùng phép kiểm tra “queue còn một chỗ” rồi tự kết luận lần gửi tiếp chắc chắn được nhận.

`getQueue()` nên phục vụ quan sát/chẩn đoán. Không chèn công việc trực tiếp qua queue để tránh API tiếp nhận của bộ thực thi; cách đó bỏ qua chính sách vòng đời và tạo luồng.

Có các hook như `beforeExecute`, `afterExecute`, `terminated` cho nhu cầu mở rộng. Không cần kế thừa chỉ để có một cấu hình cơ bản. Nếu dùng hook để quan sát lỗi, cần nhớ tác vụ gửi qua submit có thể giữ lỗi trong Future; tham số Throwable của hook không tự chứa mọi lỗi nghiệp vụ.

## 11. Chọn cấu hình bằng quan hệ giữa các thành phần

Không bắt đầu từ “nên dùng bao nhiêu luồng” tách rời khỏi hệ thống. Trước hết cần biết:

1. Tác vụ chủ yếu tính toán hay chờ I/O?
2. Tài nguyên ngoài có bao nhiêu kết nối hoặc hạn mức?
3. Bao nhiêu công việc chờ là chấp nhận được?
4. Khi không nhận được việc, phản hồi nghiệp vụ nào là đúng?
5. Ai quan sát Future/lỗi và ai đóng bộ thực thi?

Một hàng đợi lớn có thể hấp thụ đợt tải ngắn nhưng tăng thời gian chờ. Một bộ luồng lớn có thể tăng lượng truy cập đồng thời tới dịch vụ ngoài. Giới hạn cả hai giúp biểu đạt ngân sách tài nguyên, nhưng các con số cần được kiểm chứng bằng đo đạc.

Bộ luồng nền tảng như trong bài vẫn có giá trị. Trên Java 21+, mô hình luồng ảo theo từng tác vụ là lựa chọn khác cho một số loại công việc; không vì đổi mô hình luồng mà bỏ qua giới hạn tài nguyên, chính sách tiếp nhận và vòng đời.

## 12. Tự giải thích một cấu hình

Với core bằng 2, max bằng 5 và hàng đợi có dung lượng 10, hãy mô tả đường đi của tác vụ khi:

- Chưa có luồng nào.
- Đã có hai luồng đang chạy và hàng đợi còn chỗ.
- Hai luồng đều bận, hàng đợi đầy và bộ luồng vẫn dưới max.
- Bộ luồng đã đạt max, hàng đợi đầy.
- Bộ thực thi đã được shutdown.

Một câu trả lời đầy đủ phải nói tới cả luồng, hàng đợi, khả năng tạo luồng và handler. Đó là cách đọc ThreadPoolExecutor như một hệ thống tiếp nhận và thực hiện công việc, thay vì một tập tham số rời rạc.
