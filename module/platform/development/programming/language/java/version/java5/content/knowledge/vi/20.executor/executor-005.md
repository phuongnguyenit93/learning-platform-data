# Các bộ thực thi tạo bởi Executors

## 1. Executors giúp chọn chính sách thực thi

Một tác vụ mô tả **công việc cần làm**; bộ thực thi (executor) quyết định **công việc được tổ chức chạy như thế nào**. Khi có nhiều tác vụ, các quyết định này ảnh hưởng trực tiếp đến tài nguyên và thời gian chờ:

- Cho phép bao nhiêu tác vụ chạy đồng thời?
- Tác vụ chưa chạy sẽ chờ ở đâu?
- Có tái sử dụng luồng hay tạo luồng mới?
- Có cần chạy sau một khoảng trễ hoặc lặp lại?
- Ai chịu trách nhiệm đóng bộ thực thi?

`java.util.concurrent.Executors` là lớp tiện ích có các phương thức tạo đối tượng (factory method). Nó cung cấp một số cấu hình sẵn để không phải tự lắp ghép mọi tham số ngay từ đầu.

Cần phân biệt các tên gần nhau:

| Tên | Vai trò |
|---|---|
| `Executor` | Giao diện cơ bản để nhận `Runnable` qua `execute` |
| `ExecutorService` | Giao diện bổ sung việc gửi tác vụ, theo dõi kết quả và quản lý vòng đời |
| `ScheduledExecutorService` | Giao diện hỗ trợ chạy trễ và chạy định kỳ |
| `Executors` | Lớp chứa phương thức tạo các đối tượng trên và một số tiện ích liên quan |

Ví dụ `Executors.newFixedThreadPool(4)` trả một `ExecutorService`; `Executors` không phải bản thân nhóm luồng.

Bài tập trung vào các API còn áp dụng trong Java hiện nay. Những factory nền tảng của chương này có từ Java 5; phần work-stealing và luồng ảo được đánh dấu phiên bản riêng để không nhầm khả năng của Java 17 với Java 21+.

## 2. Bản đồ lựa chọn ban đầu

| Factory | Mô hình chính | Phù hợp để bắt đầu xem xét | Điều cần kiểm soát |
|---|---|---|---|
| `newFixedThreadPool(n)` | Tái sử dụng tối đa `n` luồng xử lý tác vụ | Nhiều công việc độc lập với mức song song xác định | Hàng đợi không giới hạn dung lượng cấu hình sẵn |
| `newSingleThreadExecutor()` | Một luồng xử lý tuần tự | Chuỗi công việc cần không chồng lấp | Tắc nghẽn và hàng đợi tích tụ |
| `newCachedThreadPool()` | Tái sử dụng luồng rảnh, tạo thêm khi cần | Đợt công việc ngắn với tải đầu vào đã được kiểm soát | Không có giới hạn luồng hữu ích cho bảo vệ tải |
| `newScheduledThreadPool(n)` | Nhiều luồng với cơ chế lập lịch | Nhiều tác vụ trễ hoặc định kỳ | Thời gian chạy, lỗi và số công việc chờ |
| `newSingleThreadScheduledExecutor()` | Lập lịch bằng một luồng | Ít công việc định kỳ cần tuần tự | Một việc chậm làm trễ các việc khác |
| `newWorkStealingPool(...)` | Nhóm luồng phân phối lại công việc qua nhiều hàng đợi | Công việc tính toán có thể phân chia | Không dựa vào thứ tự thực thi |
| `newVirtualThreadPerTaskExecutor()` | Một luồng ảo mới cho mỗi tác vụ, Java 21+ | Nhiều công việc có thời gian chờ I/O | Tài nguyên bên ngoài và số tác vụ đang tồn tại |
| `newThreadPerTaskExecutor(factory)` | Một luồng mới cho mỗi tác vụ, Java 21+ | Khi cần chỉ định rõ cách tạo từng luồng | Không tự giới hạn số luồng |

Đây là điểm xuất phát để phân tích, không phải quy tắc chọn máy móc. Chẳng hạn tên “fixed” giới hạn luồng nhưng không đồng nghĩa giới hạn mọi tài nguyên mà tác vụ tiêu thụ.

Danh sách factory và các overload nhận `ThreadFactory` được mô tả trong [Executors API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html).

## 3. Nhóm luồng cố định: newFixedThreadPool

```java
ExecutorService pool = Executors.newFixedThreadPool(4);
```

Đây là đoạn khai báo minh họa, cần import `ExecutorService` và `Executors` từ `java.util.concurrent`.

Khi có nhiều việc, tối đa bốn luồng xử lý các tác vụ ở cùng thời điểm; các việc còn lại chờ trong hàng đợi chung. Luồng được tái sử dụng cho các tác vụ tiếp theo. Việc tạo executor không có nghĩa mọi luồng đã được khởi động ngay; triển khai tiêu chuẩn tạo luồng theo nhu cầu.

Ví dụ có 1.000 phép tính độc lập không có nghĩa cần tạo 1.000 luồng hệ điều hành. Có thể chia thành tác vụ rồi cho nhóm luồng xử lý dần.

### Giới hạn luồng chưa đủ để giới hạn tải

Factory này sử dụng hàng đợi không giới hạn dung lượng cấu hình sẵn. Nếu đầu vào trung bình nhanh hơn tốc độ xử lý, số việc chờ tăng dần:

```text
Tác vụ đến liên tục
        |
        v
Hàng đợi tích tụ --> 4 luồng xử lý --> Tác vụ hoàn tất
```

Hệ quả có thể là tăng bộ nhớ, tăng thời gian chờ và kết quả đến quá muộn. Không nên xem “chỉ có bốn luồng” là bảo đảm chống quá tải.

Khi cần giới hạn cả luồng lẫn số việc chờ, có thể cấu hình `ThreadPoolExecutor` trực tiếp với hàng đợi có dung lượng hữu hạn và chính sách từ chối phù hợp. Đây là lý do cần hiểu cấu hình mà factory che đi, không phải lý do xem factory là lỗi thời.

### Chọn n dựa trên loại công việc

Với tính toán chủ yếu dùng CPU, số lõi khả dụng là thông tin khởi đầu hữu ích; thêm quá nhiều luồng không tạo thêm năng lực tính toán. Với công việc thường chờ I/O, phải cân nhắc thêm giới hạn kết nối, thời gian chờ và tải hệ thống. Không có công thức cố định đúng cho mọi ứng dụng; đo đạc bằng tải thực.

## 4. Thực thi tuần tự: newSingleThreadExecutor

```java
ExecutorService serial = Executors.newSingleThreadExecutor();
```

Các tác vụ được xử lý tuần tự, không có hai tác vụ của executor này cùng chạy. Điều này hữu ích khi công việc tự nhiên tạo thành một dòng xử lý, chẳng hạn xử lý các thay đổi được gửi lần lượt cho một tài nguyên.

Nếu một tác vụ kéo dài, những tác vụ sau phải chờ. Hàng đợi mặc định cũng không có giới hạn dung lượng cấu hình sẵn.

### Một tác vụ tại một thời điểm không có nghĩa một Thread sống mãi

Nếu luồng xử lý bị kết thúc vì thất bại trong quá trình thực thi, bộ thực thi có thể tạo luồng thay thế khi cần. Không dùng danh tính của một đối tượng `Thread` làm định danh nghiệp vụ lâu dài.

Với nhiều bên gửi đồng thời, cần định nghĩa rõ thứ tự đầu vào ở cấp ứng dụng; “tuần tự” không tự tạo ra thứ tự nghiệp vụ theo đồng hồ của các bên gửi.

### Khác newFixedThreadPool(1) ở cam kết cấu hình

Cả hai ban đầu đều chạy tối đa một tác vụ. Tuy nhiên, `newSingleThreadExecutor()` bảo đảm không thể cấu hình lại executor trả về để dùng thêm luồng thông qua API riêng của triển khai. Không nên ép kiểu đối tượng trả về chỉ để thay đổi số luồng.

Tránh tác vụ A trong executor một luồng gửi tác vụ B vào chính executor ấy rồi chờ `B.get()`: A giữ luồng duy nhất, B chờ luồng, nên không có bên nào tiến lên. Tăng thời gian chờ không giải quyết sự phụ thuộc này.

## 5. Nhóm luồng co giãn: newCachedThreadPool

```java
ExecutorService cached = Executors.newCachedThreadPool();
```

Bộ thực thi cố gắng giao công việc cho luồng đang rảnh; nếu không có luồng sẵn để nhận, nó có thể tạo thêm luồng. Luồng rảnh không sử dụng trong khoảng thời gian mặc định sẽ được thu hồi; với factory tiêu chuẩn, mốc này là 60 giây.

Khác với nhóm cố định, cấu hình này giao việc trực tiếp qua `SynchronousQueue`, thay vì tích trữ một danh sách việc chờ như hàng đợi thông thường.

Lợi ích là có thể tái sử dụng luồng và đáp ứng những đợt công việc ngắn. Giới hạn thực tế cần chú ý: nếu tác vụ chặn lâu hoặc đầu vào tăng mạnh, số luồng nền tảng có thể tăng rất lớn, tiêu thụ bộ nhớ và tài nguyên hệ điều hành.

Vì vậy, không chọn cached pool chỉ vì “không biết nên đặt bao nhiêu luồng”. Trước hết phải hiểu tải vào và có cách giới hạn nó.

Quan hệ giữa kích thước nhóm luồng, hàng đợi và việc từ chối tác vụ được trình bày trong [ThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

## 6. Bộ thực thi có lịch: ScheduledExecutorService

Hai factory thường dùng:

```java
ScheduledExecutorService scheduler =
        Executors.newScheduledThreadPool(2);

ScheduledExecutorService singleScheduler =
        Executors.newSingleThreadScheduledExecutor();
```

Đoạn trên chỉ minh họa hai lựa chọn; không có yêu cầu phải tạo đồng thời cả hai trong ứng dụng.

### Chạy một lần sau khoảng trễ

```java
ScheduledFuture<String> future = scheduler.schedule(
        () -> "ready",
        200,
        TimeUnit.MILLISECONDS);
```

Tác vụ được phép bắt đầu sau khoảng trễ yêu cầu. Không bảo đảm nó thực sự chạy đúng tại mốc 200 ms: luồng đang bận, tải hệ thống và cơ chế lập lịch có thể làm nó chạy muộn hơn. Đây không phải công cụ bảo đảm thời gian thực.

`schedule` dùng khoảng trễ tương đối, không phải biểu thức cron hoặc thời điểm lịch theo múi giờ.

### Chạy lặp: fixed rate và fixed delay

```java
ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(
        () -> refreshMetrics(),
        0,
        5,
        TimeUnit.SECONDS);
```

Đây là mã minh họa; `refreshMetrics()` là phương thức do ứng dụng cung cấp.

- `scheduleAtFixedRate`: các mốc dự kiến tính từ thời điểm bắt đầu ban đầu, chẳng hạn 0, 5, 10, 15 giây.
- `scheduleWithFixedDelay`: sau khi một lần chạy kết thúc, đợi thêm khoảng delay rồi mới bắt đầu lần tiếp theo.

Nếu một lần chạy mất 8 giây và fixed delay là 5 giây, lần sau chỉ được bắt đầu sau khi lần trước kết thúc thêm 5 giây. Fixed rate có thể bị trễ so với các mốc ban đầu; các lần chạy của **cùng một tác vụ định kỳ** không chồng lấp, kể cả khi scheduler có nhiều luồng. Những tác vụ khác nhau vẫn có thể chạy đồng thời.

Nếu thân tác vụ định kỳ ném ngoại lệ ra ngoài, các lần thực thi tiếp theo của tác vụ ấy bị dừng. Cần quan sát lỗi và quyết định cách xử lý; không bắt rồi bỏ qua mọi ngoại lệ chỉ để lịch tiếp tục chạy.

`handle.cancel(false)` có thể được dùng khi không còn muốn các lần chạy tiếp theo. `get()` của một công việc định kỳ không trả về bình thường sau mỗi lần lặp; không dùng nó như cách lấy “kết quả của lần chạy thứ ba”.

Xem hợp đồng chi tiết tại [ScheduledExecutorService API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html).

### Chọn một luồng hay nhiều luồng cho lịch?

Dùng single scheduler khi tải nhỏ và việc tuần tự là phù hợp. Một việc chặn lâu trên luồng duy nhất sẽ làm trễ các lịch khác. Với nhiều việc độc lập, xem xét scheduler nhiều luồng, đồng thời vẫn giới hạn số lịch và thời gian chạy.

Đưa công việc từ scheduler sang executor khác có thể giữ luồng lập lịch nhẹ hơn, nhưng khi đó ứng dụng phải tự kiểm soát hàng đợi và khả năng các lần xử lý nghiệp vụ chồng lấp.

## 7. Work-stealing: newWorkStealingPool, từ Java 8

```java
ExecutorService compute = Executors.newWorkStealingPool(4);
```

Mô hình này có thể dùng nhiều hàng đợi để giảm tranh chấp. Luồng đang rảnh có thể lấy công việc từ nơi khác trong nhóm, giúp cân bằng tải khi thời gian xử lý các việc không đồng đều.

Tham số là **mức song song mục tiêu**; không nên diễn giải nó như cam kết tổng số luồng luôn đúng bằng bốn trong mọi tình huống. Overload không truyền số sử dụng số bộ xử lý khả dụng làm mức mục tiêu.

Factory này không bảo đảm thứ tự thực thi theo thứ tự gửi. Nó phù hợp để xem xét với các công việc tính toán độc lập hoặc có thể chia nhỏ; không mặc định dùng làm nơi chứa hàng loạt thao tác chặn lâu.

Triển khai dùng `ForkJoinPool`. Nếu cần thiết kế công việc chia để trị và phối hợp các nhánh con, cần hiểu thêm mô hình Fork/Join; đổi tên factory không tự biến một thuật toán tuần tự thành thuật toán song song hiệu quả.

## 8. Một luồng cho mỗi tác vụ và luồng ảo, từ Java 21

### newVirtualThreadPerTaskExecutor

```java
ExecutorService io = Executors.newVirtualThreadPerTaskExecutor();
```

Mỗi tác vụ chạy trên một luồng ảo mới. Đây không phải nhóm cố định tái sử dụng một số lượng nhỏ luồng ảo. Mô hình hữu ích cho nhiều tác vụ có thời gian chờ I/O, khi muốn giữ cách viết mã chặn dễ đọc.

Luồng ảo không làm phép tính CPU chạy nhanh hơn. Nó cũng không làm cơ sở dữ liệu chấp nhận vô hạn kết nối. Vẫn cần giới hạn các tài nguyên như số truy vấn đồng thời, lời gọi tới dịch vụ ngoài hoặc bộ nhớ dành cho yêu cầu đang xử lý.

Không dùng factory Java 21 này trong chương trình biên dịch với `--release 17`. Đây là lựa chọn hiện đại bổ sung; các factory nền tảng vẫn có vai trò riêng.

Ví dụ hoàn chỉnh, lưu thành **`VirtualExecutorDemo.java`**, cần JDK 21+:

```java
import java.util.concurrent.Executors;

public class VirtualExecutorDemo {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var result = executor.submit(
                    () -> Thread.currentThread().isVirtual());
            System.out.println("virtual: " + result.get());
        }
    }
}
```

Chạy:

```shell
javac --release 21 VirtualExecutorDemo.java
java VirtualExecutorDemo
```

Stdout:

```text
virtual: true
```

Ví dụ chỉ xác minh loại luồng; không phải phép đo hiệu năng I/O. Hướng sử dụng và giới hạn được giải thích trong [hướng dẫn Virtual Threads của Oracle](https://docs.oracle.com/en/java/javase/25/core/virtual-threads.html).

### newThreadPerTaskExecutor(ThreadFactory)

Factory này cũng tạo một `Thread` mới cho mỗi tác vụ, nhưng loại luồng do `ThreadFactory` quyết định. Số luồng tạo ra không bị giới hạn bởi một kích thước pool cấu hình ở factory này.

Nếu factory tạo luồng nền tảng thì mỗi tác vụ dùng một luồng nền tảng mới; nếu tạo luồng ảo thì dùng luồng ảo. Chọn nó khi cần kiểm soát cách tạo từng luồng, không hiểu nhầm đây là cơ chế tự động giới hạn tải.

## 9. Chương trình Java 17+: gửi nhiều phép tính vào nhóm cố định

Lưu thành **`ExecutorsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExecutorsDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            List<Future<Integer>> results = new ArrayList<>();
            for (int i = 1; i <= 4; i++) {
                int value = i;
                results.add(pool.submit(() -> value * value));
            }

            for (Future<Integer> result : results) {
                System.out.println(result.get());
            }
        } finally {
            stop(pool);
        }
    }

    private static void stop(ExecutorService pool)
            throws InterruptedException {
        pool.shutdown();
        try {
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Executor did not terminate");
                }
            }
        } catch (InterruptedException e) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
            throw e;
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ExecutorsDemo.java
java ExecutorsDemo
```

Stdout chính xác:

```text
1
4
9
16
```

Những điểm cần quan sát:

1. Bốn tác vụ được gửi trước khi vòng lặp lấy kết quả bắt đầu.
2. Nhóm có hai luồng xử lý, không tạo bốn luồng chỉ vì có bốn việc.
3. `value` là biến cục bộ không bị gán lại, nên có thể được lambda sử dụng.
4. `main` in kết quả theo thứ tự các `Future` trong danh sách. Thứ tự in không chứng minh thứ tự hoàn tất của tác vụ.
5. Tài nguyên executor được đóng trong `finally`.

`main` khai báo `throws Exception` để ví dụ tập trung vào factory và vòng đời. Trong ứng dụng thực, cần quy định cách phản hồi khi lấy kết quả thất bại, bị ngắt hoặc quá thời gian chờ.

## 10. ThreadFactory, đối tượng bọc và quyền sở hữu vòng đời

Một số factory có overload nhận `ThreadFactory` để ứng dụng đặt cách tạo luồng, chẳng hạn tên luồng giúp nhận diện trên log. `Executors.defaultThreadFactory()` tạo luồng nền tảng không phải daemon với mức ưu tiên thông thường. Không dùng độ ưu tiên luồng làm cơ chế bảo đảm thứ tự nghiệp vụ.

`unconfigurableExecutorService(executor)` và `unconfigurableScheduledExecutorService(executor)` trả đối tượng bọc để chỉ lộ API giao diện tương ứng, che các phương thức cấu hình riêng của triển khai. Chúng không tạo thêm một nhóm luồng độc lập.

Đối tượng bọc vẫn chuyển tiếp các phương thức vòng đời như `shutdown()`; nó không phải cơ chế ngăn người nhận đóng executor. Nếu chia sẻ executor giữa nhiều thành phần, phải xác định rõ thành phần nào sở hữu và chịu trách nhiệm đóng nó.

## 11. Quản lý tài nguyên và các lỗi thường gặp

### Quên đóng executor

Các luồng nền tảng không phải daemon của nhiều factory thông thường có thể giữ JVM tiếp tục sống sau khi `main` kết thúc. Thời điểm và cách đóng phải thuộc thiết kế ứng dụng.

- `shutdown()`: ngừng nhận việc mới, cho công việc đã nhận tiếp tục; không tự chờ hoàn tất.
- `awaitTermination(...)`: chờ sau yêu cầu đóng trong một khoảng thời gian.
- `shutdownNow()`: cố gắng ngắt công việc đang chạy và lấy ra các việc chưa bắt đầu; không bảo đảm ép mọi công việc dừng.

Trên Java 19+, `ExecutorService` hỗ trợ `AutoCloseable`, nên có thể dùng try-with-resources; khi đóng, nó chờ việc đã gửi kết thúc. Đó không phải một thời hạn chờ cố định. Ví dụ Java 17 trong bài dùng cách đóng tường minh để tương thích phiên bản.

Chi tiết vòng đời được quy định trong [ExecutorService API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html).

### Tạo executor cho từng công việc nhỏ

Tạo rồi đóng một nhóm luồng cho từng lời gọi nhỏ thường làm mất lợi ích tái sử dụng. Với nhóm luồng nền tảng, thường quản lý executor theo vòng đời của thành phần hoặc ứng dụng. Với mô hình luồng ảo, executor vẫn cần phạm vi sở hữu rõ ràng; mỗi tác vụ đã có một luồng ảo riêng.

### Bỏ qua lỗi trong Future

Gửi bằng `submit` rồi bỏ luôn `Future` có thể khiến lỗi trong tác vụ không được quan sát tại nơi gọi. Phải có cách theo dõi kết quả, ghi nhận thất bại hoặc chuyển lỗi lên tầng chịu trách nhiệm.

### Giả định mọi executor đều tạo một nhóm luồng giống nhau

Nhóm cố định, cached pool, work-stealing và mô hình mỗi tác vụ một luồng có chính sách khác nhau. Đặt tên biến là `pool` không thay đổi các cam kết của đối tượng thực tế.

### Tăng luồng để chữa mọi tình huống chậm

Nếu điểm nghẽn là khóa dùng chung, cơ sở dữ liệu hoặc giới hạn dịch vụ ngoài, tăng số luồng có thể tăng tranh chấp và làm chậm hơn. Cần đo thời gian chờ, số việc đang chạy, số việc chờ và mức sử dụng tài nguyên trước khi chỉnh cấu hình.

## 12. Tự kiểm tra lựa chọn

1. `newFixedThreadPool(8)` có bảo đảm chỉ có tám tác vụ tồn tại trong hệ thống không?
2. Một công việc trong single executor chờ công việc khác được gửi vào chính executor đó có vấn đề gì?
3. Tại sao cached pool có thể gặp vấn đề khi nhiều tác vụ chặn lâu?
4. Công việc kéo dài 8 giây với chu kỳ 5 giây: fixed rate và fixed delay khác nhau thế nào?
5. Khi dùng luồng ảo, vì sao vẫn phải giới hạn số yêu cầu tới cơ sở dữ liệu?
6. Nếu cần giới hạn hàng đợi và có chính sách từ chối rõ ràng, nên tìm hiểu lớp nào?

**Gợi ý:** (1) Không, hàng đợi còn có thể chứa nhiều việc. (2) Luồng duy nhất bị giữ trong khi việc phụ chờ được chạy. (3) Có thể tạo quá nhiều luồng nền tảng. (4) Fixed rate theo mốc dự kiến và có thể trễ; fixed delay chờ thêm sau khi lần trước kết thúc. (5) Kết nối và khả năng xử lý của cơ sở dữ liệu vẫn hữu hạn. (6) `ThreadPoolExecutor`.

Khi chọn một factory, hãy trả lời được cả ba câu: **nó giới hạn điều gì, công việc chưa chạy chờ ở đâu, và ai sẽ đóng nó**.
