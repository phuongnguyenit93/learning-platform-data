# Đặc điểm bộ thực thi một luồng và số luồng cố định

## 1. Chọn số luồng là chọn cách công việc được tiến hành

Một ứng dụng nhận nhiều yêu cầu không nhất thiết phải tạo một luồng mới cho mỗi yêu cầu. Bộ thực thi giữ các luồng làm việc (worker thread), giao tác vụ cho luồng sẵn sàng và xếp phần chưa xử lý vào hàng đợi.

Hai lựa chọn thường gặp:

- `Executors.newSingleThreadExecutor()`: thực thi các tác vụ tuần tự, tối đa một tác vụ hoạt động tại một thời điểm.
- `Executors.newFixedThreadPool(n)`: dùng bộ luồng có kích thước cố định, tối đa `n` tác vụ được các luồng của bộ thực thi xử lý cùng lúc.

Ví dụ, cập nhật một bộ trạng thái theo từng lệnh có thể cần xử lý tuần tự. Tính nhiều phần báo cáo độc lập có thể tận dụng nhiều luồng. Cần xác định sự phụ thuộc giữa công việc trước khi chọn con số.

Các factory này xuất hiện từ Java 5 và vẫn áp dụng trên Java hiện đại. Toàn bộ chương trình trong bài dùng API có thể biên dịch với Java 17+.

## 2. So sánh hành vi

| Đặc điểm | Một luồng | Số luồng cố định |
| --- | --- | --- |
| Khởi tạo | `newSingleThreadExecutor()` | `newFixedThreadPool(n)`, với `n > 0` |
| Tác vụ hoạt động đồng thời | Tối đa 1 | Tối đa `n` |
| Khi tất cả luồng bận | Tác vụ mới chờ trong hàng đợi | Tác vụ mới chờ trong hàng đợi |
| Hàng đợi do factory tạo | Không đặt giới hạn dung lượng riêng | Không đặt giới hạn dung lượng riêng |
| Tác vụ chậm ảnh hưởng | Chặn tiến độ mọi tác vụ phía sau | Chiếm một vị trí; các vị trí khác có thể tiếp tục |
| Mục đích điển hình | Tuần tự hóa công việc | Xử lý nhiều công việc độc lập |
| Cam kết không tăng thành nhiều luồng | Có | `newFixedThreadPool(1)` không có cùng cam kết chống cấu hình lại |

Luồng được tạo khi cần; gọi `newFixedThreadPool(8)` không có nghĩa ngay lập tức có tám luồng đang chạy. Con số tám cũng không bảo đảm tám phép tính đồng thời dùng tám lõi CPU: tác vụ có thể chờ I/O, chờ khóa hoặc tranh chấp tài nguyên.

Factory một luồng bảo đảm các tác vụ không chồng lấn khi thực thi. Nếu luồng làm việc kết thúc bất thường trước khi bộ thực thi bị đóng, nó có thể được thay thế để xử lý công việc tiếp theo. Vì vậy, “một luồng” không phải cam kết dùng mãi cùng một đối tượng `Thread`. [Tài liệu Executors](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html#newSingleThreadExecutor())

## 3. Thí nghiệm: tác vụ dư phải chờ

Chương trình sau dùng chốt đồng bộ (`CountDownLatch`) giữ tất cả luồng làm việc ở trạng thái bận, rồi gửi thêm một tác vụ. Nhờ vậy, quan sát không dựa vào `Thread.sleep` hay tốc độ máy.

Tệp **PoolCapacityDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PoolCapacityDemo {
    public static void main(String[] args) throws Exception {
        inspect("single", Executors.newSingleThreadExecutor(), 1);
        inspect("fixed-3", Executors.newFixedThreadPool(3), 3);
    }

    private static void inspect(
            String label, ExecutorService pool, int capacity) throws Exception {
        CountDownLatch started = new CountDownLatch(capacity);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        List<Future<?>> work = new ArrayList<>();

        try {
            for (int i = 0; i < capacity; i++) {
                work.add(pool.submit(() -> {
                    int current = active.incrementAndGet();
                    peak.accumulateAndGet(current, Math::max);
                    started.countDown();
                    try {
                        release.await();
                    } finally {
                        active.decrementAndGet();
                    }
                    return null;
                }));
            }

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not start");
            }

            Future<Integer> extra = pool.submit(() -> 99);

            System.out.println(label + ": active=" + active.get());
            System.out.println(label + ": extraDone=" + extra.isDone());

            release.countDown();
            for (Future<?> task : work) {
                task.get();
            }

            System.out.println(label + ": extraResult=" + extra.get());
            System.out.println(label + ": peak=" + peak.get());
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

Biên dịch và chạy:

```shell
javac --release 17 PoolCapacityDemo.java
java PoolCapacityDemo
```

Stdout khi hoàn tất bình thường:

```text
single: active=1
single: extraDone=false
single: extraResult=99
single: peak=1
fixed-3: active=3
fixed-3: extraDone=false
fixed-3: extraResult=99
fixed-3: peak=3
```

Cách đọc:

1. Các tác vụ đầu chưa được mở chốt nên tiếp tục chiếm hết vị trí.
2. `extraDone=false` cho thấy tác vụ thêm chưa có kết quả; trong tình huống này nó phải chờ một vị trí rảnh.
3. Mở chốt cho phép các tác vụ đầu kết thúc và tác vụ thêm nhận luồng làm việc.
4. `peak` đo số tác vụ trong nhóm đầu cùng hoạt động. Nó minh họa giới hạn 1 và 3, không phải số lõi CPU đã được sử dụng.

`AtomicInteger` được dùng vì nhiều luồng cùng cập nhật bộ đếm trong lần thử `fixed-3`. Thay bằng `int[]` rồi tăng phần tử từ nhiều luồng sẽ tạo truy cập tranh chấp.

## 4. Một luồng: tuần tự hóa không đồng nghĩa an toàn mọi nơi

Giả sử mỗi tác vụ là một lệnh cập nhật số dư. Khi mọi thao tác đọc/ghi số dư đều đi qua cùng bộ thực thi một luồng, các lệnh không thực hiện đồng thời. Đây là cách **giới hạn quyền truy cập trạng thái vào một luồng xử lý tại mỗi thời điểm**.

Nhưng giả thiết đó bị phá vỡ nếu:

- Luồng HTTP đọc trực tiếp số dư trong khi tác vụ đang cập nhật.
- Một bộ thực thi khác cũng sửa cùng trạng thái.
- Tác vụ tự tạo luồng phụ để sửa dữ liệu rồi trả về ngay.
- Mã giữ tham chiếu tới đối tượng có thể thay đổi và sửa nó ở bên ngoài.

Có một luồng trong bộ thực thi không có nghĩa cả ứng dụng chỉ còn một luồng. Cần duy trì ranh giới sở hữu dữ liệu; có thể gửi một tác vụ đọc và lấy kết quả bằng `Future.get()`, hoặc dùng cơ chế đồng bộ phù hợp nếu buộc phải chia sẻ.

Cũng không dùng `ThreadLocal` như kho trạng thái nghiệp vụ duy nhất mà ngầm cho rằng luồng làm việc sẽ không bao giờ đổi. Luồng thay thế không phải đối tượng luồng cũ. Ngược lại, khi luồng được tái sử dụng, dữ liệu ngữ cảnh để lại trong `ThreadLocal` có thể lọt sang tác vụ sau nếu không dọn dẹp đúng cách.

### Hiểu đúng thứ tự

Với một nơi gửi lần lượt các lệnh, cách xử lý tuần tự rất dễ suy luận. Khi nhiều nơi gửi đồng thời, thứ tự lời gọi trong các đoạn mã riêng biệt không tự hình thành thứ tự nghiệp vụ toàn cục. Nếu cần “lệnh số 12 luôn sau lệnh số 11”, phải có cách xác định và kiểm soát trình tự đó.

Không suy luận từ giao diện `Executor` rằng mọi lớp triển khai đều có cùng chính sách hàng đợi hoặc thứ tự. Chính giao diện này cho phép nhiều cách thực thi khác nhau. [Tài liệu Executor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executor.html)

## 5. Nhiều luồng: thứ tự gửi khác thứ tự hoàn thành

Với bộ thực thi cố định nhiều luồng, tác vụ gửi sau có thể xong trước. Lệnh lấy các `Future` theo thứ tự gửi chỉ sắp xếp việc **đọc kết quả**, không sắp xếp lại việc thực thi.

Tệp **ResultOrderDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ResultOrderDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch allowFirst = new CountDownLatch(1);

        try {
            Future<String> first = pool.submit(() -> {
                allowFirst.await();
                return "A";
            });
            Future<String> second = pool.submit(() -> "B");

            System.out.println("completedFirst=" + second.get());
            System.out.println("firstDoneBeforeRelease=" + first.isDone());

            allowFirst.countDown();
            System.out.println("submissionOrder=" + first.get() + "," + second.get());
        } finally {
            allowFirst.countDown();
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
javac --release 17 ResultOrderDemo.java
java ResultOrderDemo
```

Stdout:

```text
completedFirst=B
firstDoneBeforeRelease=false
submissionOrder=A,B
```

Chốt giữ tác vụ A chưa thể hoàn thành. B chạy trên luồng còn lại, hoàn thành trước, rồi luồng chính mới cho A tiếp tục. Dòng cuối đọc A trước B nên in `A,B`, dù đó không phải thứ tự hoàn thành.

Nếu đổi bộ thực thi thành một luồng nhưng giữ nguyên logic chờ B trước khi mở chốt A, chương trình sẽ kẹt: B không có luồng để chạy. Không chạy biến thể này như một thí nghiệm vô hạn; trước hết hãy vẽ quan hệ chờ.

## 6. Số luồng hữu hạn có thể làm lộ quan hệ chờ vòng

Một lỗi thường gặp:

```text
Tác vụ cha giữ một luồng
    -> gửi tác vụ con vào cùng bộ thực thi
    -> gọi get() để chờ con
Tác vụ con
    -> nằm trong hàng đợi, chờ một luồng rảnh
```

Với bộ thực thi một luồng, cha giữ vị trí duy nhất nên con không thể bắt đầu. Với bộ thực thi `n` luồng, nếu cả `n` vị trí đều bị các tác vụ cha giữ để chờ con, tình huống tương tự vẫn xuất hiện.

Tăng số luồng chỉ có thể trì hoãn lỗi nếu quan hệ phụ thuộc không thay đổi. Các hướng thiết kế gồm:

- Làm phép tính con trực tiếp nếu không cần tách tác vụ.
- Đặt việc điều phối chờ kết quả ở ngoài bộ thực thi đang chạy công việc.
- Thiết kế chuỗi xử lý không chiếm luồng trong khi chờ công việc phụ thuộc.
- Tách bộ thực thi theo vai trò khi có lý do rõ ràng và vẫn kiểm tra quan hệ chờ giữa chúng.

Một timeout giúp bên chờ thoát theo thời gian, nhưng không tự giải quyết mọi tác vụ còn treo hoặc hủy công việc chưa hoàn thành.

## 7. Giới hạn luồng chưa giới hạn lượng công việc đã nhận

Cả hai factory đều dùng hàng đợi không có giới hạn dung lượng được cấu hình riêng. “Không giới hạn” không có nghĩa bộ nhớ vô tận: số tác vụ chờ vẫn bị giới hạn bởi tài nguyên thực tế.

Ví dụ giả định tốc độ gửi là 300 tác vụ/giây và tốc độ xử lý duy trì là 200 tác vụ/giây. Trong trạng thái đó, hàng đợi có xu hướng tăng khoảng 100 tác vụ mỗi giây. Giới hạn bộ thực thi ở bốn luồng không ngăn đà tăng này.

Tác vụ chờ có thể giữ dữ liệu báo cáo, đối tượng yêu cầu hoặc vùng nhớ lớn. Vì vậy cần quan sát cả thời gian nằm trong hàng đợi, số việc chờ, thời gian xử lý và mức sử dụng tài nguyên; chỉ nhìn số luồng là chưa đủ.

Nếu cần giới hạn công việc chờ, có thể cấu hình `ThreadPoolExecutor` tường minh. Ví dụ sau là **đoạn khởi tạo**, đặt trong phương thức của ứng dụng sau khi nhập các lớp tương ứng:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ExecutorService bounded = new ThreadPoolExecutor(
        2, 2,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<Runnable>(100),
        Executors.defaultThreadFactory(),
        new ThreadPoolExecutor.AbortPolicy()
);
```

Cấu hình này có hai luồng và tối đa 100 phần tử trong hàng đợi. Khi không thể nhận thêm, `AbortPolicy` ném `RejectedExecutionException`; ứng dụng phải quyết định trả lỗi bận, thử lại có giới hạn hay giảm tốc độ gửi. Không tùy tiện bỏ công việc rồi vẫn báo thành công.

Đây là lựa chọn khi có yêu cầu kiểm soát tải, không phải lời khuyên thay mọi factory bằng cùng một cấu hình. Dung lượng 100 và số luồng 2 chỉ minh họa cách biểu đạt chính sách. [Tài liệu ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

## 8. Chọn số luồng theo tài nguyên bị giới hạn

**Công việc chủ yếu tính toán:** bắt đầu từ mức gần số bộ xử lý khả dụng, đo tải thực tế rồi điều chỉnh. Quá nhiều luồng không tạo thêm lõi; có thể tăng chuyển ngữ cảnh và tranh chấp bộ nhớ.

**Công việc thường chờ I/O:** có thể cần nhiều tác vụ đồng thời hơn để tận dụng khoảng chờ, nhưng phải xét giới hạn kết nối cơ sở dữ liệu, dịch vụ ngoài, bộ nhớ và thời hạn yêu cầu.

**Công việc yêu cầu tuần tự:** dùng một luồng khi việc không chồng lấn là chủ đích. Nếu một tác vụ có thể chờ mạng rất lâu, tác vụ sau cũng chịu ảnh hưởng; cần timeout và cân nhắc tách vai trò.

Trên Java 21+, luồng ảo là lựa chọn khác cho nhiều công việc thường xuyên chờ I/O. `newFixedThreadPool(n)` vẫn là bộ luồng nền tảng với giới hạn nêu trong bài; nó không tự chuyển thành bộ thực thi luồng ảo theo từng tác vụ. Luồng ảo cũng không tự mở rộng dung lượng cơ sở dữ liệu hay giới hạn của dịch vụ bên ngoài.

Không có một con số cố định đúng cho mọi máy và mọi loại công việc. Hãy dùng phép đo gồm thông lượng, độ trễ, hàng đợi và sức khỏe tài nguyên phụ thuộc để chọn.

## 9. Quản lý vòng đời và lỗi

Bên tạo và sở hữu bộ thực thi phải chịu trách nhiệm đóng khi hết vòng đời sử dụng:

1. Ngừng tiếp nhận công việc từ tầng ứng dụng.
2. Gọi `shutdown()` để ngừng nhận tác vụ mới và cho việc đã nhận tiếp tục.
3. Chờ bằng `awaitTermination` với ngân sách phù hợp.
4. Nếu cần, yêu cầu `shutdownNow()` rồi kiểm tra kết thúc; tác vụ phải hợp tác với ngắt.

Hai ví dụ dùng `finally` để dọn tài nguyên thí nghiệm. Không tự đóng bộ thực thi dùng chung do thành phần khác quản lý sau mỗi yêu cầu.

Luồng mặc định của các factory này là non-daemon; quên đóng có thể khiến tiến trình chưa thoát. Cũng không giả định một tác vụ lỗi sẽ đóng cả bộ thực thi. Đặc biệt, lỗi của tác vụ gửi qua `submit` phải được quan sát qua `Future` hoặc cơ chế theo dõi phù hợp.

## 10. Tự chọn cho ba tình huống

| Tình huống | Hướng lựa chọn | Điều cần xác minh |
| --- | --- | --- |
| Áp dụng lần lượt lệnh cập nhật một trạng thái | Bộ thực thi một luồng | Mọi truy cập trạng thái có đi qua cùng ranh giới không? |
| Tính độc lập nhiều phần của một báo cáo | Bộ thực thi cố định nhiều luồng | Các tác vụ có sửa chung dữ liệu hoặc chờ lẫn nhau không? |
| Nhận tải tăng liên tục từ khách hàng | Thiết kế giới hạn tải và hàng đợi | Khi đầy, phản hồi và hoàn tất/hủy công việc ra sao? |

Khi giải thích lựa chọn, hãy nêu cả số tác vụ có thể hoạt động, công việc nào phải chờ và tài nguyên nào giới hạn hệ thống. Chỉ nói “một luồng an toàn” hoặc “nhiều luồng nhanh hơn” là chưa đủ để đánh giá thiết kế.
