# ThreadFactory và việc đặt tên luồng

## 1. Luồng nào đang xử lý công việc này?

Khi đọc nhật ký hoặc bản chụp trạng thái luồng (thread dump), tên như `pool-4-thread-2` cho biết một luồng thuộc bộ thực thi nào đó, nhưng chưa cho biết vai trò của nó. Tên như `invoice-export-pool-1-worker-2` giúp liên hệ ngay với nhóm công việc xuất hóa đơn.

`ThreadFactory` là nơi tập trung chính sách **tạo luồng**. Bộ thực thi yêu cầu factory tạo luồng khi cần; factory khởi tạo tên và các thuộc tính phù hợp rồi trả luồng về.

Cần tách ba khái niệm:

| Khái niệm | Trách nhiệm |
| --- | --- |
| `Runnable` hoặc `Callable` | Mô tả công việc cần làm |
| `ThreadFactory` | Tạo một luồng chưa khởi chạy |
| `ExecutorService` | Điều phối tác vụ, quản lý luồng và vòng đời thực thi |

Factory không quyết định dung lượng hàng đợi, số tác vụ được nhận hay thời điểm ứng dụng đóng bộ thực thi. Đặt tên tốt giúp quan sát; nó không làm thuật toán tự an toàn khi chạy đồng thời.

Các ví dụ chính chạy trên Java 17+. Phần cuối giới thiệu cách khai báo factory ngắn hơn trên Java 21+; các cơ chế được trình bày vẫn dùng trong Java hiện đại.

## 2. Hợp đồng của ThreadFactory

Giao diện có một phương thức:

```java
Thread newThread(Runnable runnable);
```

Factory phải tạo **luồng mới, chưa khởi chạy**, gắn đúng `Runnable` được cung cấp và trả luồng đó. Bộ thực thi chịu trách nhiệm gọi `start()`.

Những lỗi dễ gặp:

- Gọi `start()` bên trong factory rồi trả luồng đang chạy.
- Trả lại cùng một đối tượng `Thread` cho nhiều lần yêu cầu; một luồng không thể được khởi động hai lần.
- Bỏ qua `Runnable` được truyền vào và thay bằng công việc khác.
- Tạo tên bằng biến đếm dùng chung không an toàn khi nhiều luồng gọi factory đồng thời.

Giao diện cho phép trả `null` khi từ chối tạo luồng. Tuy nhiên, đây không phải cách thuận tiện để giới hạn tải: bộ thực thi có thể không có đủ luồng xử lý tác vụ. Hãy quản lý tải bằng chính sách tiếp nhận và hàng đợi phù hợp. [Tài liệu ThreadFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadFactory.html)

Đặc biệt, `Runnable` mà `ThreadPoolExecutor` truyền cho factory thường là công việc nội bộ của **luồng làm việc**, bao gồm vòng lặp nhận nhiều tác vụ. Factory không được gọi một lần cho mỗi tác vụ gửi vào.

## 3. Bắt đầu từ factory mặc định

`Executors.defaultThreadFactory()` cung cấp cách tạo luồng nền tảng với các thuộc tính mặc định đã xác định: non-daemon, mức ưu tiên thông thường trong giới hạn nhóm luồng và cách đặt tên theo mẫu `pool-N-thread-M`.

Có thể **bọc factory mặc định** rồi đổi phần cần thay đổi, thay vì vô tình kế thừa các thuộc tính của luồng đang gửi công việc.

Ví dụ, `new Thread(runnable)` kế thừa một số thuộc tính của luồng tạo ra nó. Nếu tạo bộ thực thi ở nhiều ngữ cảnh khác nhau mà không chủ động kiểm soát, chính sách luồng có thể khó nhận biết. Dùng factory mặc định làm nền giúp thể hiện rõ ý định. [Tài liệu Executors.defaultThreadFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html#defaultThreadFactory())

### Chọn tên có cấu trúc

Một mẫu hữu ích:

```text
<vai-trò>-pool-<số-bộ>-worker-<số-luồng>
```

Ví dụ:

```text
invoice-export-pool-1-worker-1
invoice-export-pool-1-worker-2
search-refresh-pool-2-worker-1
```

Tên nên diễn tả vai trò ổn định của tài nguyên. Mã yêu cầu và mã tác vụ thay đổi theo từng công việc nên đặt trong trường nhật ký hoặc ngữ cảnh truy vết riêng.

Số thứ tự giúp phân biệt các luồng được tạo, không phải độ ưu tiên, thứ tự hoàn thành hoặc mã định danh duy nhất trên mọi tiến trình. Java cho phép các luồng trùng tên; quy ước đặt tên của ứng dụng mới tạo ra tính dễ phân biệt.

## 4. Ví dụ đầy đủ: đặt tên và quan sát tái sử dụng

Tệp **NamedFactoryDemo.java**:

```java
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class NamedFactoryDemo {
    static final class NamedThreadFactory implements ThreadFactory {
        private static final AtomicInteger POOL_IDS = new AtomicInteger();
        private final AtomicInteger threadIds = new AtomicInteger();
        private final ThreadFactory delegate = Executors.defaultThreadFactory();
        private final String prefix;

        NamedThreadFactory(String role) {
            String cleanRole = Objects.requireNonNull(role, "role").strip();
            if (cleanRole.isEmpty()) {
                throw new IllegalArgumentException("role must not be blank");
            }
            prefix = cleanRole + "-pool-" + POOL_IDS.incrementAndGet() + "-worker-";
        }

        @Override
        public Thread newThread(Runnable runnable) {
            Thread thread = delegate.newThread(
                    Objects.requireNonNull(runnable, "runnable"));
            thread.setName(prefix + threadIds.incrementAndGet());
            return thread;
        }
    }

    public static void main(String[] args) throws Exception {
        ThreadFactory factory = new NamedThreadFactory("invoice-export");
        ExecutorService pool = Executors.newFixedThreadPool(2, factory);
        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> first = pool.submit(() -> {
                started.countDown();
                release.await();
                return Thread.currentThread().getName();
            });
            Future<String> second = pool.submit(() -> {
                started.countDown();
                release.await();
                return Thread.currentThread().getName();
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not start");
            }

            release.countDown();
            String firstName = first.get();
            String secondName = second.get();

            System.out.println(firstName);
            System.out.println(secondName);

            String thirdName = pool.submit(
                    () -> Thread.currentThread().getName()).get();
            System.out.println("reusedWorker="
                    + (thirdName.equals(firstName) || thirdName.equals(secondName)));
            System.out.println("daemon="
                    + pool.submit(() -> Thread.currentThread().isDaemon()).get());
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
javac --release 17 NamedFactoryDemo.java
java NamedFactoryDemo
```

Stdout khi chạy riêng chương trình và hoàn tất bình thường:

```text
invoice-export-pool-1-worker-1
invoice-export-pool-1-worker-2
reusedWorker=true
daemon=false
```

Hai lần gửi đầu được thực hiện lần lượt từ `main`; chúng tạo hai luồng làm việc trong bộ thực thi mới. Chốt giữ chúng cùng tồn tại trước khi lấy kết quả. Vì lấy `Future` theo thứ tự gửi, hai tên đầu được in theo thứ tự đó; tác vụ không tự tranh nhau in ra màn hình.

Tác vụ thứ ba có thể chạy trên một trong hai luồng. Chương trình chỉ kiểm tra nó dùng lại một tên đã biết, không đoán chắc là luồng số 1 hay số 2.

### Vì sao cần hai bộ đếm?

- `POOL_IDS` phân biệt những instance factory do lớp này tạo ra trong cùng phạm vi nạp lớp.
- `threadIds` phân biệt các luồng do một instance factory tạo.
- `AtomicInteger` bảo vệ thao tác tăng số khi nhiều luồng yêu cầu tạo luồng cùng lúc.

Nếu chia sẻ cùng một factory cho nhiều bộ thực thi, các luồng của chúng cùng mang một prefix và dùng chung dãy số. Nếu muốn tên phản ánh ranh giới từng bộ thực thi, tạo một instance factory cho mỗi bộ.

Factory được gọi lúc cần **luồng mới**, kể cả luồng thay thế. Nó không đổi tên lại cho mỗi tác vụ. Số tác vụ đã xử lý vì thế có thể lớn hơn rất nhiều so với số tên luồng đã tạo.

## 5. Handler ngoại lệ không thay thế việc đọc Future

Factory có thể gắn `Thread.UncaughtExceptionHandler` để ghi nhận lỗi thoát ra khỏi luồng. Nhưng không phải mọi lỗi nghiệp vụ đều đi tới handler này.

Với bộ luồng tiêu chuẩn dựa trên `ThreadPoolExecutor`:

- Tác vụ gửi bằng `execute` ném ngoại lệ không được bắt có thể làm luồng làm việc kết thúc bất thường; handler của luồng được gọi.
- Tác vụ gửi bằng `submit` có lớp bao giữ ngoại lệ trong `Future`; bên gọi nhận lỗi qua `get()`.
- Không đọc `Future` rồi chỉ dựa vào uncaught handler có thể làm bỏ sót lỗi tác vụ.

Đây là quan hệ giữa cách bao tác vụ và cơ chế báo lỗi, không phải do tên luồng gây ra. [Tài liệu ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

Tệp **FactoryFailureDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class FactoryFailureDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger ids = new AtomicInteger();
        AtomicInteger uncaughtCount = new AtomicInteger();
        AtomicReference<String> uncaught = new AtomicReference<>();
        CountDownLatch handlerCalled = new CountDownLatch(1);
        ThreadFactory base = Executors.defaultThreadFactory();

        ThreadFactory factory = runnable -> {
            Thread thread = base.newThread(runnable);
            thread.setName("report-worker-" + ids.incrementAndGet());
            thread.setUncaughtExceptionHandler((failedThread, error) -> {
                uncaught.set(failedThread.getName() + ":"
                        + error.getClass().getSimpleName());
                uncaughtCount.incrementAndGet();
                handlerCalled.countDown();
            });
            return thread;
        };

        ExecutorService pool = Executors.newSingleThreadExecutor(factory);
        try {
            pool.execute(() -> {
                throw new IllegalStateException("execute failed");
            });

            if (!handlerCalled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Handler was not called");
            }
            System.out.println("uncaught=" + uncaught.get());

            Future<?> failed = pool.submit(() -> {
                throw new IllegalArgumentException("submit failed");
            });
            try {
                failed.get();
            } catch (ExecutionException ex) {
                System.out.println("futureFailure="
                        + ex.getCause().getClass().getSimpleName());
            }

            System.out.println("uncaughtCount=" + uncaughtCount.get());
            System.out.println("executorStillUsable="
                    + pool.submit(() -> "OK").get());
        } finally {
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
javac --release 17 FactoryFailureDemo.java
java FactoryFailureDemo
```

Stdout:

```text
uncaught=report-worker-1:IllegalStateException
futureFailure=IllegalArgumentException
uncaughtCount=1
executorStillUsable=OK
```

Handler trong thí nghiệm chỉ lưu bằng chứng rồi báo chốt; ứng dụng thực tế có thể ghi nhật ký và số đo. Handler cần gọn, tránh chờ vô hạn hoặc ném thêm lỗi.

Một tác vụ `execute` làm chết luồng làm việc không có nghĩa bộ thực thi tự đóng. Bộ thực thi có thể tạo luồng thay thế để tiếp tục. Đừng dùng tên hoặc danh tính luồng cũ làm điều kiện đúng đắn của nghiệp vụ.

## 6. Thuộc tính nào nên điều chỉnh?

| Thuộc tính | Mục đích | Điểm cần lưu ý |
| --- | --- | --- |
| Tên | Nhận diện vai trò khi quan sát | Không thay thế mã tác vụ/truy vết |
| Daemon | Tham gia điều kiện kết thúc JVM | Không phải cơ chế hoàn tất công việc |
| Uncaught handler | Quan sát lỗi thoát khỏi luồng | Không thu mọi lỗi nằm trong Future |
| Priority | Mức ưu tiên luồng nền tảng | Không bảo đảm thứ tự hay thời hạn xử lý |

Giữ non-daemon thường phù hợp khi công việc cần hoàn tất theo vòng đời ứng dụng. Chuyển thành daemon chỉ để tiến trình thoát nhanh có thể làm tác vụ chưa hoàn thành bị bỏ khi JVM kết thúc. Cần đóng bộ thực thi theo đúng vòng đời và chờ theo ngân sách.

Không tăng priority để chữa hàng đợi quá tải. Nó không cấp thêm CPU, không vượt qua khóa mà luồng đang chờ và không cung cấp cam kết ưu tiên nghiệp vụ. Các ưu tiên nghiệp vụ nên được thiết kế ở tầng điều phối.

Factory cũng không tự truyền đúng ngữ cảnh của **từng yêu cầu**. Luồng có thể được tạo trong một yêu cầu rồi tái sử dụng cho nhiều yêu cầu khác. Ngữ cảnh kế thừa lúc tạo luồng và ngữ cảnh cần cho mỗi tác vụ là hai việc khác nhau. Nếu dùng ngữ cảnh nhật ký hoặc truy vết, hãy gắn và dọn theo phạm vi tác vụ.

## 7. Đừng dùng tên luồng làm dữ liệu nghiệp vụ

Một tên như `invoice-export-pool-1-worker-2` nói “luồng này thuộc vai trò xuất hóa đơn”, không nói hóa đơn nào đang chạy. Trong nhật ký, nên kết hợp:

```text
thread=invoice-export-pool-1-worker-2
taskId=export-1042
operation=invoice-export
status=completed
```

Đây là ví dụ cấu trúc trường nhật ký, không phải stdout của hai chương trình trên.

Tránh đưa token, mật khẩu, dữ liệu cá nhân hoặc nội dung yêu cầu vào tên luồng. Tên có thể xuất hiện trong công cụ chẩn đoán và nhiều dòng nhật ký.

Nếu buộc phải đổi tên tạm thời trong một tác vụ, lưu tên cũ và khôi phục trong `finally`. Nếu không, tác vụ sau có thể tiếp tục mang tên công việc trước. Tuy nhiên, một trường nhật ký riêng thường thể hiện đúng quan hệ hơn và giảm việc sửa thuộc tính luồng dùng chung.

Cũng không lựa chọn nhánh xử lý bằng cách kiểm tra tên bắt đầu bằng một prefix. Việc đổi quy ước tên để hỗ trợ vận hành không nên làm thay đổi kết quả nghiệp vụ.

## 8. Java 21+: dùng Thread.Builder để tạo factory

Với JDK 21+, có thể khai báo factory luồng nền tảng ngắn hơn:

```java
ThreadFactory factory = Thread.ofPlatform()
        .name("invoice-export-", 1)
        .daemon(false)
        .factory();
```

Đây là đoạn khai báo trong phương thức; cần nhập `java.util.concurrent.ThreadFactory`. Factory tạo các luồng với tên tăng dần như `invoice-export-1`, `invoice-export-2`. Nếu tạo hai factory độc lập với cùng prefix và cùng số bắt đầu, tên vẫn có thể trùng giữa hai nhóm.

`Thread.Builder` dùng để cấu hình không bảo đảm an toàn khi chia sẻ cho nhiều luồng; factory được nó tạo ra được thiết kế để dùng đồng thời. Sau khi cấu hình, hãy truyền factory cho bộ thực thi. [Tài liệu Thread.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.Builder.html)

Muốn tạo luồng ảo theo từng tác vụ trên Java 21+, có thể dùng:

```java
ThreadFactory virtualFactory = Thread.ofVirtual()
        .name("invoice-task-", 1)
        .factory();
ExecutorService executor = Executors.newThreadPerTaskExecutor(virtualFactory);
```

Đây là đoạn khởi tạo, cần nhập `ThreadFactory`, `ExecutorService` và `Executors`; bên sở hữu vẫn phải đóng bộ thực thi.

Luồng ảo là daemon và có mức ưu tiên cố định. Không áp dụng máy móc chính sách daemon/priority của luồng nền tảng cho chúng. Cũng không đổi factory sang luồng ảo rồi cho rằng `newFixedThreadPool(n, factory)` sẽ chạy một luồng mới cho mỗi tác vụ: vòng lặp luồng làm việc của bộ thực thi cố định vẫn giữ cách tái sử dụng luồng. [Tài liệu Thread](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html)

## 9. Tự kiểm tra

Một hệ thống có bộ thực thi gửi thư và bộ thực thi tạo báo cáo. Khi xem thread dump, tất cả luồng đều mang tên `worker`.

Hãy xác định:

1. Prefix nào giúp phân biệt hai vai trò và nhiều instance của cùng vai trò?
2. Biến đếm tên có an toàn nếu nhiều nơi đồng thời gửi công việc?
3. Factory có trả luồng chưa chạy và giữ đúng Runnable không?
4. Lỗi từ `submit` được quan sát ở đâu?
5. Ai đóng từng bộ thực thi khi ứng dụng dừng?
6. Mã yêu cầu đang nằm trong trường nhật ký riêng hay bị gắn vào tên luồng?

Một thiết kế tốt làm rõ tên tài nguyên, danh tính công việc và quyền sở hữu vòng đời. Nhờ đó, khi có tác vụ chậm hoặc thất bại, tên luồng giúp tìm đúng khu vực xử lý mà không trở thành điều kiện điều khiển chương trình.
