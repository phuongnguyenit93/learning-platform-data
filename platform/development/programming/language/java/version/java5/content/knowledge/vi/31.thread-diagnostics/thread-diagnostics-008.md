# Đặt tên luồng để theo dõi tác vụ và bộ thực thi

## 1. Tên luồng giúp trả lời câu hỏi nào?

Khi một ứng dụng có nhiều bộ thực thi, các tên như `pool-3-thread-1` vẫn có giá trị kỹ thuật nhưng chưa cho biết nhóm đó đang phục vụ phần việc nào. Một dòng log lỗi chỉ có tên mặc định có thể khiến người đọc phải lần lại nơi tạo từng executor.

Tên có ý nghĩa hơn, chẳng hạn:

```text
orders-io-1-worker-3
report-export-2-worker-1
cache-refresh-1-worker-1
```

giúp liên hệ một dấu vết thực thi với trách nhiệm của nhóm luồng.

Tuy nhiên, **luồng và tác vụ không phải cùng một đối tượng**. Một luồng trong nhóm có thể chạy hàng nghìn tác vụ liên tiếp; một yêu cầu nghiệp vụ có thể đi qua nhiều luồng. Tên luồng nên giúp tìm “đang chạy trên nhóm nào”; mã tác vụ hoặc mã yêu cầu giúp tìm “đang xử lý việc nào”.

Đặt tên hỗ trợ chẩn đoán qua log, trình gỡ lỗi và dữ liệu chẩn đoán luồng. Nó không thay thế đồng bộ, thu nhận ngoại lệ hay quản lý vòng đời bộ thực thi.

## 2. Thiết kế quy ước tên dễ đọc

Một quy ước nhỏ thường đủ:

```text
<trách nhiệm>-<mã nhóm>-worker-<số luồng>
```

Ví dụ `orders-io-2-worker-7` có thể được hiểu là luồng thứ bảy do nhà máy của nhóm `orders-io` số hai tạo ra.

Mỗi thành phần có vai trò:

| Thành phần | Mục đích |
| --- | --- |
| Trách nhiệm | Liên hệ với một phần việc như xử lý đơn hàng hoặc xuất báo cáo |
| Mã nhóm | Phân biệt nhiều executor cùng vai trò trong một tiến trình |
| Số luồng | Phân biệt các luồng do cùng nhà máy tạo |

Nên giữ tên ngắn, ổn định và thống nhất dấu phân cách. Đừng nhét địa chỉ email, token, nội dung đầu vào, đường dẫn riêng tư hay toàn bộ thông tin khách hàng vào tên. Tên có thể xuất hiện trong log hoặc bản chẩn đoán được chia sẻ.

Số thứ tự chỉ là nhãn chẩn đoán. Không dùng tên luồng để quyết định quyền truy cập, phân vùng dữ liệu hay thứ tự nghiệp vụ. Java không áp đặt tính duy nhất cho tên: hai đối tượng Thread khác nhau có thể cùng tên.

Nếu cần phân biệt trên nhiều tiến trình hoặc nhiều lần khởi động, dùng thêm các trường như service, instance và thời gian trong hệ thống log. Không cố biến tên luồng thành một mã định danh toàn cục.

## 3. Luồng tạo trực tiếp: đặt tên khi khởi tạo

Ví dụ độc lập:

```java
public class NamedThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread task = new Thread(
                () -> System.out.println(Thread.currentThread().getName()),
                "catalog-warmup");

        task.start();
        task.join();
    }
}
```

Lưu thành `NamedThreadDemo.java`, chạy:

```shell
javac --release 17 NamedThreadDemo.java
java NamedThreadDemo
```

Stdout:

```text
catalog-warmup
```

`Thread.currentThread()` trả luồng đang thực thi đoạn mã. Nó khác với luồng đã tạo hoặc nộp tác vụ.

Đặt tên trước `start()` giúp luồng mang đúng nhãn ngay từ đầu. `setName` có thể đổi tên về sau, nhưng thay đổi tên của một luồng khác đang chạy dễ tạo log khó hiểu nếu không có giao thức rõ ràng.

Tên không bắt đầu luồng; vẫn cần `start()`. Gọi trực tiếp `run()` chỉ chạy phương thức trên luồng gọi và không tạo thực thi đồng thời.

## 4. Với executor, đặt tên qua ThreadFactory

`ThreadFactory` tạo đối tượng luồng mới cho bộ thực thi. Đây là nơi phù hợp để đặt quy ước tên cho các luồng trong nhóm:

```text
Nhiều tác vụ → ExecutorService → ThreadFactory tạo các luồng khi cần
```

Nhà máy được gọi khi cần tạo luồng, **không phải mỗi lần có một tác vụ**. Vì thế bộ đếm trong factory là số đối tượng luồng được tạo, không phải số công việc đã xử lý.

Có thể ủy quyền việc tạo ban đầu cho `Executors.defaultThreadFactory()`, rồi chỉ thay tên. Cách này tránh vô tình thay các thuộc tính khác trong khi mục đích chỉ là nhãn chẩn đoán.

Quy tắc khi viết factory:

- Trả về luồng chưa khởi chạy; executor chịu trách nhiệm khởi chạy.
- Dùng bộ đếm an toàn giữa các luồng nếu factory có thể được gọi đồng thời.
- Phân biệt từng nhóm và từng luồng.
- Không trả cùng một đối tượng Thread cho nhiều yêu cầu tạo.
- Không đổi daemon, độ ưu tiên hoặc bộ nạp lớp chỉ để đặt tên.

Một nhóm thực thi có thể tạo luồng thay thế nếu một luồng cũ kết thúc bất thường. Do đó, số thứ tự có thể tăng dù số luồng hoạt động đồng thời vẫn giữ nguyên. Điều đó không tự chứng minh rò rỉ luồng.

## 5. Ví dụ chạy được: tên nhóm ổn định và tên tác vụ tạm thời

Chương trình dưới đây dùng một nhóm một luồng để việc tái sử dụng luồng dễ quan sát. Nó chạy ba tác vụ: xem tên gốc, đổi tên tạm trong một phạm vi, rồi kiểm tra tên đã được khôi phục.

Lưu thành `ExecutorNamingDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ExecutorNamingDemo {
    static final class NamedThreadFactory implements ThreadFactory {
        private static final AtomicInteger NEXT_POOL = new AtomicInteger();
        private final AtomicInteger nextWorker = new AtomicInteger();
        private final ThreadFactory delegate =
                Executors.defaultThreadFactory();
        private final String prefix;

        NamedThreadFactory(String role) {
            prefix = role + "-" + NEXT_POOL.incrementAndGet() + "-worker-";
        }

        @Override
        public Thread newThread(Runnable task) {
            Thread thread = delegate.newThread(task);
            thread.setName(prefix + nextWorker.incrementAndGet());
            return thread;
        }
    }

    static <T> Callable<T> withTaskName(
            String taskLabel,
            Callable<T> task) {
        return () -> {
            Thread thread = Thread.currentThread();
            String originalName = thread.getName();
            thread.setName(originalName + "[" + taskLabel + "]");
            try {
                return task.call();
            } finally {
                thread.setName(originalName);
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                new NamedThreadFactory("orders-io"));

        try {
            Future<String> first = executor.submit(
                    () -> Thread.currentThread().getName());

            Future<String> second = executor.submit(
                    withTaskName("task-42",
                            () -> Thread.currentThread().getName()));

            Future<String> third = executor.submit(
                    () -> Thread.currentThread().getName());

            System.out.println("first=" + first.get());
            System.out.println("during=" + second.get());
            System.out.println("after=" + third.get());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Executor did not terminate");
                }
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 ExecutorNamingDemo.java
java ExecutorNamingDemo
```

Stdout khi chương trình chạy bình thường:

```text
first=orders-io-1-worker-1
during=orders-io-1-worker-1[task-42]
after=orders-io-1-worker-1
```

Trong chương trình độc lập này chỉ tạo một NamedThreadFactory nên mã nhóm là `1`. Trong ứng dụng có nhiều factory, không nên phụ thuộc một con số cụ thể để nhận diện nghiệp vụ.

Nhóm một luồng chạy tuần tự ba tác vụ trên cùng luồng khi không có sự cố. Tác vụ hai lưu tên gốc, đặt nhãn tạm rồi khôi phục trong `finally`. Tác vụ ba chứng minh nhãn `task-42` không bị lưu lại cho công việc tiếp theo.

Các dòng chỉ được in bởi luồng chính sau khi lấy kết quả từ future, nên không có cuộc đua thứ tự in giữa ba tác vụ.

Ví dụ dùng hàng đợi mặc định của executor cho ba tác vụ đã biết để tập trung vào đặt tên. Việc đặt tên không phải cấu hình giới hạn hàng đợi hoặc kiểm soát tải cho một hệ thống sản xuất.

## 6. Tác vụ có mã riêng; đừng để tên luồng gánh mọi thông tin

Một định dạng log minh họa:

```text
service=orders instance=api-2 thread=orders-io-1-worker-3 taskId=task-42 event=started
service=orders instance=api-2 thread=orders-io-1-worker-3 taskId=task-42 event=completed
```

Các dòng trên là ví dụ cấu trúc trường, không phải stdout của chương trình trước.

Tên luồng trả lời nhóm thực thi nào đã chạy đoạn mã. `taskId` trả lời công việc nào. Khi một tác vụ chuyển sang nhóm khác, mã tác vụ vẫn có thể theo nó trong ngữ cảnh đã truyền rõ ràng.

Nếu dùng ngữ cảnh chẩn đoán gắn với luồng như MDC của thư viện log, cần truyền ngữ cảnh sang tác vụ và khôi phục/xóa đúng khi kết thúc. Nhóm luồng tái sử dụng luồng nên dữ liệu còn sót có thể bị gắn nhầm vào công việc tiếp theo.

Không giả định mọi ngữ cảnh được tự động sao chép theo mỗi lần submit. Một cơ chế kế thừa ở lúc tạo Thread không đồng nghĩa kế thừa ngữ cảnh ở lúc tái sử dụng Thread cho một tác vụ mới.

Nếu hệ thống log đã có `taskId`, `requestId` hoặc `traceId` đúng cách, thường nên giữ tên luồng ổn định thay vì đổi theo từng yêu cầu. Đổi tên tạm chỉ là một công cụ bổ sung khi nó giúp chẩn đoán và bạn sở hữu rõ phạm vi thực hiện.

## 7. Khi đổi tên tạm, phải khôi phục đúng phạm vi

Mẫu cần tránh:

```java
executor.submit(() -> {
    Thread.currentThread().setName("task-42");
    processTask();
});
```

Đây là mã minh họa có `processTask` đại diện cho nghiệp vụ. Sau khi chạy, luồng vẫn mang tên `task-42`. Công việc kế tiếp có thể bị log dưới nhãn sai dù hoàn toàn không liên quan.

Cách khôi phục trong ví dụ dùng `finally` để áp dụng cả khi Callable ném ngoại lệ. Nếu có nhiều lớp bọc lồng nhau, mỗi lớp phải lưu và trả về đúng tên nó đã nhận lúc vào phạm vi, thay vì tự suy ra một tên gốc cố định.

Một ngoại lệ nữa là việc thực thi không nhất thiết xảy ra ở luồng bạn tưởng. Một executor có thể có chính sách chạy tác vụ ngay trên luồng nộp khi quá tải; một tác vụ có thể được gọi trực tiếp trong thử nghiệm. Dùng `Thread.currentThread()` ở **lúc thực thi** và khôi phục theo phạm vi giúp tránh đổi nhầm luồng.

Dù vậy, không đổi tên tùy ý các luồng thuộc thư viện hoặc bộ thực thi dùng chung khi bạn không kiểm soát hợp đồng của nó. Với các trường hợp đó, các trường log và ngữ cảnh tác vụ thường là lựa chọn ít gây ảnh hưởng hơn.

## 8. Đọc log và dữ liệu chẩn đoán theo tên luồng

Quy trình thực tế có thể bắt đầu từ một lỗi có tên `report-export-2-worker-4`:

1. Tìm nơi cấu hình factory cho vai trò `report-export`.
2. Xem nhóm đó nhận loại công việc nào, cấu hình đồng thời và hàng đợi ra sao.
3. Dùng mã tác vụ hoặc mã yêu cầu để tìm các sự kiện liên quan.
4. Nếu cần, đối chiếu tên với trạng thái và ngăn xếp trong dữ liệu chẩn đoán luồng.
5. Xem bằng chứng theo thời gian, không kết luận từ một dòng tên đơn lẻ.

Tên `worker-4` không cho biết luồng đang bận. Luồng có tên nghiệp vụ vẫn có thể đang đợi hàng đợi, chờ khóa, chờ I/O hoặc chạy tính toán. Cần đọc trạng thái, stack và ngữ cảnh đi kèm.

Tên cũng không phải lịch sử. Nếu một nhóm đổi tên tạm theo tác vụ, ảnh chụp chỉ thể hiện nhãn tại thời điểm chụp. Nếu hệ thống hiển thị cắt ngắn tên, hai nhãn dài có thể nhìn giống nhau; đặt phần vai trò dễ phân biệt ở gần đầu tên.

Không dùng số lượng tên khác nhau trong log như số tác vụ hoàn tất. Một luồng chạy nhiều tác vụ; một luồng thay thế lại làm xuất hiện tên mới mà không đại diện cho một phần việc nghiệp vụ mới.

## 9. Tên đẹp không thay việc báo lỗi và dừng executor

Một tên có ích chỉ làm lỗi dễ truy vết hơn khi lỗi được thu nhận đúng.

- Với tác vụ submit trả về Future, ngoại lệ thường được lưu trong future để get báo bằng `ExecutionException`. Nếu bỏ qua future, đặt tên luồng không làm lỗi tự hiện ra đầy đủ.
- Một uncaught exception handler không phải nơi bắt mọi lỗi của mọi kiểu nộp tác vụ. Cơ chế bọc tác vụ có thể đã thu nhận ngoại lệ.
- Tên luồng không chứng minh executor đã shutdown hoặc hết công việc. Cần quản lý shutdown, chờ kết thúc và chính sách hủy riêng.

Không đặt daemon bằng true chỉ để chương trình “đỡ bị treo”. Điều đó thay vòng đời JVM, có thể khiến công việc nền không được hoàn tất khi tiến trình kết thúc. Hãy sửa việc dừng và thu hồi tác vụ thay vì gắn thay đổi vòng đời vào một factory vốn chỉ định đặt tên.

Độ ưu tiên luồng cũng không phải mức ưu tiên nghiệp vụ đáng tin cho hàng đợi tác vụ. Giữ các quyết định đó tách khỏi quy ước nhãn chẩn đoán.

## 10. Ghi chú cho Java hiện đại

Các constructor Thread, ThreadFactory, ExecutorService và cách lấy tên trong ví dụ vẫn phù hợp. Không cần dùng API đã lỗi thời để có tên hữu ích.

Từ Java 21, API dựng luồng hỗ trợ cấu hình tên cho cả luồng nền tảng và luồng ảo. Ví dụ minh họa chỉ dành cho JDK 21 trở lên:

```java
ThreadFactory factory =
        Thread.ofVirtual().name("orders-vt-", 1).factory();
```

Đây chỉ là cách tạo factory có quy ước tên, không phải yêu cầu chuyển mọi chương trình sang luồng ảo. Đoạn này không thuộc các chương trình biên dịch với `--release 17` ở trên.

Với luồng ảo, `Thread.currentThread()` trong tác vụ trả luồng ảo đang thực hiện công việc, không phải luồng nền tảng đang mang nó. Do đó vẫn phân biệt nhãn luồng và mã tác vụ; đừng suy ra tên luồng mang từ tên mà tác vụ quan sát được.

Quan trọng nhất là giữ đúng quy ước tương ứng với mô hình thực thi đang dùng, thay vì giả định mọi executor là một nhóm luồng nền tảng được tái sử dụng theo cùng cách.

## 11. Tự kiểm tra

1. Một ThreadFactory tạo mười luồng có chứng minh executor đã chạy đúng mười tác vụ không?
2. Hai luồng có thể trùng tên không?
3. Vì sao đặt tên luồng theo taskId mà không khôi phục lại gây log sai trong nhóm luồng?
4. Có thể dùng tên luồng làm mã yêu cầu xuyên suốt nhiều bộ thực thi không?
5. Vì sao không chỉ thêm uncaught exception handler rồi bỏ qua mọi Future?

Đáp án:

1. Không; factory được gọi theo nhu cầu tạo luồng, không theo từng tác vụ.
2. Có; ứng dụng tự thiết kế tính dễ phân biệt.
3. Luồng được dùng lại, nhãn cũ có thể lọt sang công việc mới.
4. Không đáng tin; cần truyền mã yêu cầu như một ngữ cảnh riêng.
5. Tác vụ submit có thể lưu lỗi vào Future thay vì để lỗi thoát khỏi luồng.

Một quy ước tốt giúp biết nhóm nào thực thi, còn ngữ cảnh tác vụ giúp biết việc gì đang diễn ra. Kết hợp hai nguồn thông tin đó với thu nhận lỗi và quản lý vòng đời sẽ tạo dấu vết chẩn đoán hữu ích.

## Tài liệu đối chiếu

- [ThreadFactory — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadFactory.html): hợp đồng tạo luồng chưa khởi chạy.
- [Executors — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html): các factory và bộ thực thi dùng ThreadFactory.
- [Thread — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): tên luồng, currentThread và API dựng luồng hiện đại.
