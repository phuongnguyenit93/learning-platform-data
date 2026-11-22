# Chờ kết quả bằng get và get có thời hạn

## 1. Future là lời hẹn về kết quả, get là điểm chờ và nhận kết quả

Sau khi giao một `Callable<V>` cho `ExecutorService`, nơi gọi thường nhận một `Future<V>`. Future không phải chính giá trị `V`: nó đại diện cho trạng thái của một lần thực thi, có thể chưa bắt đầu, đang chạy hoặc đã kết thúc.

`get()` giúp nơi gọi đợi đến khi có thể xác định kết quả. `get(timeout, unit)` cũng thực hiện việc đó nhưng giới hạn khoảng thời gian chờ của lời gọi hiện tại. Hai phương thức đều có thể trả kết quả hoặc báo trạng thái không thành công.

```text
Giao tác vụ → nhận Future → có thể làm việc khác
                                ↓
                             gọi get
                  ├─ đã xong bình thường → trả kết quả
                  ├─ đã thất bại/hủy → báo ngoại lệ tương ứng
                  └─ chưa xong → chờ theo hợp đồng của dạng get
```

Điểm cần nắm ngay: **`get` không phải lệnh bắt đầu tác vụ, và hết thời gian chờ không phải lệnh hủy tác vụ.** Khi dùng executor thông thường, công việc có thể đã chạy trước khi nơi gọi gọi `get`.

Các API trong bài vẫn áp dụng trong Java hiện nay. Ví dụ hoàn chỉnh dùng Java 17 trở lên.

## 2. Hợp đồng của hai dạng get

```java
V get() throws InterruptedException, ExecutionException;

V get(long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;
```

Đây là các chữ ký để đối chiếu, cần các kiểu trong `java.util.concurrent` khi dùng trong mã.

| Thuộc tính | `get()` | `get(timeout, unit)` |
|---|---|---|
| Khi kết quả đã sẵn sàng | Nhận kết quả, không phải chờ tác vụ chạy lại | Nhận kết quả, không phải dùng hết thời gian đã cấp |
| Khi tác vụ chưa hoàn thành | Có thể chờ không có giới hạn thời gian do nơi gọi đặt | Chờ tối đa theo khoảng thời gian được yêu cầu |
| Khi tác vụ thất bại | `ExecutionException` | `ExecutionException` |
| Khi luồng chờ bị ngắt | `InterruptedException` | `InterruptedException` |
| Khi Future bị hủy | `CancellationException` | `CancellationException` |
| Khi chờ quá hạn | Không có cơ chế hết hạn riêng | `TimeoutException` |

`CancellationException` là ngoại lệ không được kiểm tra nên không nhất thiết xuất hiện trong phần `throws` của chữ ký, nhưng vẫn là một kết quả phải xét khi thiết kế xử lý. [Hợp đồng Future.get](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html#get()).

Kết quả `V` có thể là `null` nếu tác vụ thành công với `null`, hoặc nếu dùng `submit(Runnable)` và tác vụ hoàn thành bình thường. Không dùng việc “nhận null” để mặc định kết luận hết thời gian chờ; khi chờ quá hạn, dạng get có thời hạn báo bằng ngoại lệ.

## 3. Giới hạn thời gian chờ được tính cho việc gì?

Xét đoạn minh họa trong một phương thức đã có `ExecutorService pool` và `Callable<Integer> task`:

```java
Future<Integer> future = pool.submit(task);
Integer result = future.get(2, TimeUnit.SECONDS);
```

Hai giây là giới hạn chờ của **lời gọi get đó**. Nó không tự là:

- thời hạn tồn tại của Future kể từ khi tạo;
- thời gian CPU tối đa tác vụ được dùng;
- thời hạn của lời gọi HTTP hoặc truy vấn cơ sở dữ liệu bên trong tác vụ;
- thời điểm tác vụ chắc chắn bị dừng hoặc bị xóa khỏi hàng đợi.

Nếu tác vụ còn nằm trong hàng đợi, khoảng chờ này vẫn trôi trong lúc chờ tác vụ được chạy. Nếu đã gửi việc từ lâu rồi mới gọi `get(2, SECONDS)`, lời gọi get không tự biết một “ngân sách hai giây kể từ lúc submit” mà ứng dụng mong muốn.

Sau `TimeoutException`, tác vụ có thể tiếp tục chạy và Future có thể thành công về sau. Một lời gọi `get(2, SECONDS)` khác lại đặt một khoảng chờ mới; không nên lặp vô hạn rồi cho rằng toàn bộ thao tác đã có giới hạn hai giây.

Cũng không nên kiểm thử rằng phương thức chắc chắn trả về đúng tại mốc hai giây trên đồng hồ thực. Lập lịch luồng và xử lý sau khi được đánh thức ảnh hưởng thời điểm nơi gọi tiếp tục chạy. Hợp đồng cung cấp thời hạn chờ, không phải bảo đảm thời gian phản hồi cứng của toàn hệ điều hành.

## 4. TimeoutException nói gì và không nói gì?

`TimeoutException` báo rằng thao tác chờ có thời hạn chưa thu được kết quả trong khoảng được cấp. [TimeoutException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/TimeoutException.html).

Đây là một kết quả tại phía **đợi**, không đủ để kết luận trạng thái nghiệp vụ của công việc. Ví dụ một yêu cầu thanh toán có thể đã đến dịch vụ phía sau nhưng nơi gọi không chờ được phản hồi. Tự gửi lại ngay có thể tạo giao dịch lặp nếu không có cơ chế nhận dạng và xử lý lặp an toàn.

Sau timeout, ứng dụng phải chọn chính sách phù hợp:

- Cho công việc tiếp tục và thu nhận kết quả về sau bằng một thành phần có trách nhiệm rõ ràng.
- Yêu cầu hủy bằng Future nếu công việc còn giá trị ít và tác vụ hỗ trợ hủy hợp tác.
- Trả trạng thái “chưa xác định/đang xử lý” theo hợp đồng ứng dụng, đồng thời lưu nhận dạng để tra cứu.

`future.cancel(true)` là thao tác riêng. Nó cố yêu cầu ngắt công việc đang chạy khi triển khai hỗ trợ; không bảo đảm mọi tác dụng phụ đã ngừng. Kết quả của timeout và kết quả của yêu cầu hủy không nên gộp thành một trạng thái chung mơ hồ.

## 5. Ví dụ đầy đủ: hết hạn rồi vẫn nhận được kết quả

Chương trình dùng một tác vụ bị giữ ở latch. Nó không thể tự hoàn thành trước khi luồng `main` cho phép. Vì vậy, lời get 50 mili giây chắc chắn đi theo đường timeout trong điều kiện chạy bình thường; không phải chỉ hy vọng rằng tác vụ đủ chậm.

Lưu thành `FutureGetDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class FutureGetDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger executions = new AtomicInteger();

        try {
            Future<Integer> future = pool.submit(() -> {
                started.countDown();
                release.await();
                executions.incrementAndGet();
                return 42;
            });

            if (!started.await(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Task did not start");
            }

            try {
                future.get(50, TimeUnit.MILLISECONDS);
                throw new AssertionError("Expected TimeoutException");
            } catch (TimeoutException ex) {
                System.out.println("timed get: timeout");
            }

            System.out.println("done after timeout: " + future.isDone());
            System.out.println("cancelled after timeout: "
                    + future.isCancelled());

            release.countDown();
            System.out.println("plain get result: " + future.get());
            System.out.println("completed timed get: "
                    + future.get(0, TimeUnit.MILLISECONDS));
            System.out.println("executions: " + executions.get());
        } finally {
            release.countDown();
            shutdown(pool);
        }
    }

    private static void shutdown(ExecutorService pool) {
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
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 FutureGetDemo.java
java FutureGetDemo
```

Stdout khi thí nghiệm hoàn thành bình thường:

```text
timed get: timeout
done after timeout: false
cancelled after timeout: false
plain get result: 42
completed timed get: 42
executions: 1
```

Giải thích:

1. `get(50, MILLISECONDS)` hết hạn vì tác vụ còn bị giữ ở latch.
2. Future chưa done và chưa cancelled: timeout không tự hủy hay hoàn thành nó.
3. `release.countDown()` cho phép tác vụ tiếp tục; `get()` không thời hạn chờ và nhận `42`.
4. Lần `get(0, MILLISECONDS)` vẫn nhận được `42` vì Future đã thành công, không cần chờ thêm.
5. Biến đếm bằng 1 cho thấy lấy kết quả lần nữa không chạy lại tác vụ.

Lời get không thời hạn được dùng có chủ đích sau khi chương trình đã mở latch và tác vụ chỉ còn phần tính toán rất ngắn. Trong ứng dụng có công việc hoặc dịch vụ phụ thuộc không chắc chắn, phải cân nhắc hạn chót thay vì sao chép lời get không thời hạn theo thói quen.

## 6. Phân biệt bốn đường không thành công

### Tác vụ ném lỗi: ExecutionException

`get()` báo `ExecutionException` nếu lần thực thi đã kết thúc bằng lỗi. Dùng `getCause()` để hiểu nguyên nhân, thay vì nhầm rằng bản thân việc chờ gặp lỗi I/O chẳng hạn. [ExecutionException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutionException.html).

Ví dụ một Callable ném `IOException`: `get()` không trực tiếp khai báo ném IOException của tác vụ. Nơi gọi bắt lớp bọc rồi xử lý nguyên nhân theo hợp đồng ứng dụng. Giữ chuỗi nguyên nhân khi chuyển lỗi sang tầng khác để không mất khả năng chẩn đoán.

### Luồng đang chờ bị ngắt: InterruptedException

Đây là tín hiệu đối với luồng gọi `get()`. Nó không tự kết luận tác vụ đang chạy bị ngắt. Nơi gọi có thể truyền `InterruptedException` lên cấp cao hơn hoặc khôi phục trạng thái ngắt bằng `Thread.currentThread().interrupt()` khi đã bắt và kết thúc thích hợp.

Nếu muốn ngừng cả công việc, phải quyết định việc hủy riêng. Không nuốt ngắt rồi tiếp tục lặp chờ vô hạn; điều đó làm hệ thống khó dừng.

### Future bị hủy: CancellationException

`get()` không cung cấp kết quả thành công của một Future đã bị hủy. Việc hủy thường làm Future chuyển trạng thái xong từ góc nhìn API, nhưng mã tác vụ có thể còn đang phản hồi tín hiệu hủy. Không dùng `isDone()` để chứng minh mọi tác dụng phụ đã dừng.

### Chưa có kết quả kịp hạn: TimeoutException

Lần chờ kết thúc mà chưa lấy được kết quả; công việc không nhất thiết đã kết thúc. Nếu chỉ bắt `Exception` rồi trả giá trị mặc định cho mọi trường hợp, ứng dụng sẽ mất khác biệt giữa lỗi tính toán, bị ngắt, bị hủy và còn đang chạy.

Các trạng thái có thể cạnh tranh ở sát thời hạn: tác vụ có thể hoàn thành ngay sau lúc timeout. Không suy từ một lần timeout rằng `isDone()` ở câu lệnh kế tiếp chắc chắn luôn là `false`. Trong ví dụ, giá trị đó cố định vì latch vẫn chưa được mở.

## 7. Hạn chót chung cho nhiều lời chờ

Giả sử cần lấy ba kết quả trong một ngân sách tổng hai giây. Cấp `get(2, SECONDS)` cho từng Future có thể làm tổng thời gian chờ gần sáu giây trong trường hợp xấu. Cần phân biệt **thời gian cho mỗi lần chờ** và **hạn chót chung**.

Cách khái niệm:

```text
Ghi nhận mốc bắt đầu bằng nanoTime
    → trước mỗi lời chờ, tính thời gian đã trôi
    → lấy ngân sách tổng trừ phần đã trôi
    → chỉ cấp phần còn lại cho get tiếp theo
    → hết ngân sách thì xử lý quá hạn theo chính sách
```

Ví dụ minh họa trong một phương thức đã có danh sách `futures`, `results` và khai báo/xử lý các ngoại lệ từ get:

```java
long budget = TimeUnit.SECONDS.toNanos(2);
long start = System.nanoTime();

for (Future<Integer> future : futures) {
    long remaining = budget - (System.nanoTime() - start);
    if (remaining <= 0) {
        throw new TimeoutException("Total wait budget exhausted");
    }
    results.add(future.get(remaining, TimeUnit.NANOSECONDS));
}
```

Ở đây chính sách là không bắt đầu lấy kết quả tiếp khi ngân sách đã hết. Mã này không tự hủy Future còn lại; cần quyết định cách xử lý chúng. Nếu ngân sách tính từ lúc nhận yêu cầu hoặc trước khi submit, phải ghi mốc bắt đầu tại đúng ranh giới đó, thay vì chỉ trước vòng lặp.

Dùng `System.nanoTime()` để đo khoảng thời gian trong cùng một JVM; không xem giá trị của nó là ngày giờ, không dùng nó làm timestamp trao đổi giữa máy. Cách lấy hiệu giữa hai lần đọc tránh phụ thuộc việc đồng hồ lịch bị điều chỉnh. [System.nanoTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()).

Nhận Future theo thứ tự gửi có thể làm nơi gọi chờ một tác vụ chậm trong khi tác vụ khác đã xong. Nếu yêu cầu cần xử lý theo thứ tự hoàn thành, nên chọn cơ chế thu kết quả phù hợp thay vì quay vòng kiểm tra `isDone()` liên tục.

## 8. get là điểm đồng bộ, không phải phép sao chép dữ liệu

Hợp đồng Future có quan hệ bộ nhớ: các hành động của công việc bất đồng bộ xảy ra-trước (happens-before) các hành động sau lời `get()` tương ứng ở luồng khác. Nhờ đó, nhận kết quả thành công là điểm trao đổi dữ liệu có hợp đồng, không phải chỉ “đợi đủ lâu rồi hy vọng nhìn thấy giá trị”.

Không suy rằng điều này tự bảo vệ mọi dữ liệu chia sẻ. Nếu kết quả là một danh sách có thể thay đổi và một luồng khác tiếp tục sửa nó sau khi công việc đã hoàn thành, vẫn cần bất biến, chuyển quyền sở hữu hoặc đồng bộ phù hợp. `get()` trả kết quả, không tự tạo bản sao sâu.

Tránh thay get bằng một vòng lặp bận:

```java
while (!future.isDone()) {
    // Vòng lặp rỗng này có thể tiêu tốn CPU không cần thiết.
}
```

Đây là minh họa cách không nên dùng. `isDone()` còn bao gồm thất bại và hủy, nên ra khỏi vòng lặp vẫn không chứng minh tác vụ thành công. Gọi get theo chính sách chờ thích hợp vừa giúp chờ đúng cơ chế vừa phân biệt được kết quả.

## 9. Lựa chọn vị trí chờ và tránh tự làm nghẽn hệ thống

Một tác vụ trong executor một luồng không nên gửi tác vụ con vào chính executor đó rồi gọi `get()` không thời hạn. Luồng duy nhất đang chờ nên tác vụ con không thể chạy. Get có thời hạn giúp nơi gọi thoát chờ khi hết hạn, nhưng không tự sửa thiết kế phụ thuộc đó.

Tương tự, không giữ một khóa mà tác vụ cần rồi chờ Future của nó: tác vụ phải lấy được khóa mới hoàn thành, còn nơi gọi giữ khóa và chờ tác vụ. Cần tổ chức ranh giới chờ để không giữ tài nguyên mà công việc phụ thuộc phải dùng.

Trong giao diện đồ họa hoặc luồng xử lý sự kiện, một lời get chặn có thể làm ngưng phản hồi. Chuyển việc chờ sang cơ chế phù hợp với mô hình ứng dụng. Chọn thời hạn không làm một lời gọi chặn dài trở thành không chặn.

Nếu có nhiều tác vụ độc lập, gửi một tác vụ rồi gọi get ngay trong từng vòng lặp thường làm việc thực thi trở thành tuần tự từ góc nhìn nơi giao việc. Có thể giao một nhóm công việc có giới hạn trước rồi thu kết quả, đồng thời kiểm soát hàng đợi và tài nguyên; không gửi vô hạn chỉ để “tận dụng song song”.

## 10. Lỗi phổ biến và tự kiểm tra

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| get bắt đầu chạy Callable | Future thường theo dõi công việc đã được giao thực thi |
| get có thời hạn luôn chờ đủ thời gian | Nếu kết quả đã có thì không cần đợi hết hạn |
| Timeout đồng nghĩa thất bại của tác vụ | Chỉ xác nhận lần chờ chưa lấy được kết quả kịp hạn |
| Timeout tự hủy tác vụ | Hủy là thao tác/chính sách riêng |
| isDone là thành công | Cũng có thể là thất bại hoặc hủy |
| Gọi get lần hai chạy lại tác vụ | Lấy lại kết quả của cùng một lần thực thi |
| Mỗi get hai giây nghĩa toàn bộ thao tác tối đa hai giây | Cần tính ngân sách/hạn chót chung |
| Bắt InterruptedException rồi bỏ qua là vô hại | Có thể làm mất yêu cầu dừng của luồng điều phối |

Tự kiểm tra:

1. Một tác vụ xong trong một giây; gọi `get(10, SECONDS)` có chờ đủ mười giây không? **Không**, có thể nhận kết quả ngay khi nó sẵn sàng.
2. `get(1, SECONDS)` timeout, sau đó tác vụ thành công. Có lấy kết quả được nữa không? **Có**, nếu Future không bị hủy và vẫn được giữ để quan sát.
3. Trong ví dụ, nếu bỏ `release.countDown()` rồi gọi get không thời hạn thì sao? **Luồng main có thể chờ mãi**, vì chỉ nó mới mở latch cho tác vụ.
4. Future đã hoàn thành bình thường; `get(0, MILLISECONDS)` có nhất thiết timeout không? **Không**, kết quả đã sẵn sàng.

Thực hành: sau lần timeout trong ví dụ, gọi `future.cancel(true)` thay cho việc cho phép tác vụ hoàn thành bình thường. Sửa phần quan sát để bắt `CancellationException`, rồi giải thích sự khác nhau giữa timeout, yêu cầu hủy và việc mã tác vụ phản hồi ngắt. Giữ phần giải phóng latch và dừng executor để mọi đường thử nghiệm đều được dọn dẹp.
