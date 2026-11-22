# takeFirst, takeLast và chờ khi hàng đợi rỗng

## 1. Lấy phần tử ở hai đầu có ý nghĩa gì?

`BlockingDeque<E>` là hàng đợi hai đầu có các thao tác chờ. Bên tạo công việc đưa phần tử vào deque; bên xử lý lấy phần tử ra. `first` chỉ đầu deque, `last` chỉ cuối deque. Một lần lấy thành công vừa trả về phần tử vừa xóa nó khỏi deque.

```text
đầu (first)                         cuối (last)
    A  <------------>  B  <------------>  C

takeFirst() lấy A             takeLast() lấy C
```

Hai lời gọi trên minh họa hai lựa chọn đối với cùng trạng thái ban đầu; nếu thực hiện liên tiếp, lời gọi sau nhìn thấy trạng thái sau lần lấy trước.

`takeFirst()` chờ khi chưa có phần tử để lấy ở đầu; `takeLast()` làm tương tự ở cuối. Cả hai có chữ ký `E ...() throws InterruptedException`, không có tham số thời hạn và không trả `null` để báo rỗng. `BlockingDeque` không cho phép chứa `null`. Các hợp đồng này vẫn có trong Java hiện đại. [Tài liệu BlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingDeque.html)

Trong bài này, lớp triển khai là `LinkedBlockingDeque`. Không thay bằng `ArrayDeque`: có cùng hình dạng hai đầu không đồng nghĩa có khả năng chờ và an toàn khi nhiều luồng cùng truy cập.

## 2. Vì sao cần chờ thay vì liên tục kiểm tra?

Giả sử luồng xử lý sẵn sàng lúc 09:00:00 nhưng công việc chỉ đến lúc 09:00:02. Khoảng trống hai giây không phải lỗi; bên tạo và bên xử lý vốn chạy độc lập.

Một cách tự viết thường gặp là gọi `pollFirst()` trong vòng lặp cho đến khi nhận được dữ liệu. Khi hàng đợi rỗng lâu, vòng lặp tiếp tục thực hiện những lần kiểm tra không tạo ra tiến triển. Thêm `sleep` vào vòng lặp lại buộc ta chọn một khoảng nghỉ: quá ngắn thì kiểm tra nhiều, quá dài thì phản ứng chậm.

Với `takeFirst()`, ý định được diễn đạt trực tiếp: “tôi cần một phần tử ở đầu; nếu chưa có thì chờ”. Luồng gọi chưa thể đi tiếp đến câu lệnh xử lý cho đến khi lấy được phần tử hoặc lời gọi kết thúc bằng ngoại lệ. Các luồng khác vẫn có thể thêm/lấy công việc; toàn bộ chương trình không vì thế mà dừng lại.

```java
// Đoạn minh họa bên trong một phương thức cho phép ném InterruptedException.
String job = deque.takeFirst();
process(job); // Chỉ chạy sau khi đã lấy được job.
```

Trong đoạn này, `deque` và `process` do ứng dụng cung cấp; đây không phải chương trình độc lập. Cơ chế chờ thuộc lớp triển khai deque, vì vậy không cần tự bọc `takeFirst()` bằng `synchronized`, `wait()` hoặc `notify()`.

## 3. Diễn tiến khi deque rỗng

Xét một luồng xử lý C và một luồng tạo P:

1. C gọi `takeFirst()` khi chưa có công việc.
2. C chưa nhận được kết quả và phải chờ.
3. P đưa một phần tử vào deque.
4. Nếu C lấy được phần tử đó, lời gọi trả về và C tiếp tục xử lý.

Cụm “nếu C lấy được” có ý nghĩa khi có nhiều luồng xử lý. Một phần tử không được phát cho tất cả luồng đang đợi. Một luồng có thể lấy trước; các luồng còn lại vẫn cần chờ công việc khác. Không suy ra thứ tự đánh thức hay thứ tự hoàn thành từ thứ tự gọi `takeFirst()`.

Khi deque rỗng, đầu và cuối đều không có phần tử. Vì thế luồng đang gọi `takeLast()` vẫn có thể được phục vụ bởi một phần tử mà bên tạo thêm qua `putFirst()`. Tên đầu thêm và đầu lấy không bắt buộc phải giống nhau; chúng quyết định chính sách sắp xếp công việc.

| Bên tạo và bên lấy | Cách hiểu khi không có thao tác xen vào |
| --- | --- |
| Thêm liên tiếp bằng `putLast`, lấy bằng `takeFirst` | Thứ tự vào trước ra trước (FIFO) |
| Thêm liên tiếp bằng `putLast`, lấy bằng `takeLast` | Thứ tự vào sau ra trước (LIFO) |
| Trộn thêm/lấy ở cả hai đầu | Phải xét từng thao tác; không tự gán nhãn FIFO |

Với nhiều luồng, thứ tự lấy ra cũng không quyết định thứ tự hoàn thành: một công việc lấy trước có thể xử lý lâu hơn công việc lấy sau.

## 4. Chương trình chạy được: lấy hai đầu và chờ công việc mới

Lưu toàn bộ mã sau thành `TakeEndsDemo.java`. Ví dụ dùng API có trên Java 17+, không cần thư viện ngoài. `Future.get` có thời hạn ở đây chỉ phục vụ quan sát chương trình; nó không biến `takeFirst()` thành một phương thức có thời hạn.

```java
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class TakeEndsDemo {
    public static void main(String[] args) throws Exception {
        BlockingDeque<String> deque = new LinkedBlockingDeque<>(4);
        deque.putLast("A");
        deque.putLast("B");
        deque.putLast("C");

        System.out.println("first=" + deque.takeFirst());
        System.out.println("last=" + deque.takeLast());
        System.out.println("remaining=" + deque.takeFirst());
        System.out.println("empty=" + deque.isEmpty());

        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        try {
            Future<String> result = executor.submit(() -> {
                started.countDown();
                return deque.takeFirst();
            });

            started.await();
            try {
                result.get(100, TimeUnit.MILLISECONDS);
                throw new AssertionError("Deque is empty; no result expected");
            } catch (TimeoutException expected) {
                System.out.println("result-not-ready");
            }

            deque.putLast("NEW");
            System.out.println("received=" + result.get());
            System.out.println("empty=" + deque.isEmpty());
        } finally {
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 TakeEndsDemo.java
java TakeEndsDemo
```

Đầu ra:

```text
first=A
last=C
remaining=B
empty=true
result-not-ready
received=NEW
empty=true
```

Ba lần lấy đầu tiên chứng minh thao tác thực sự xóa phần tử: sau A và C chỉ còn B, sau B deque rỗng. Tác vụ tiếp theo gọi `takeFirst()` trên deque đó. Không có bên nào thêm dữ liệu trước dòng `result-not-ready`, nên tác vụ chưa thể trả về một phần tử.

`started` chỉ xác nhận tác vụ đã bắt đầu và đi đến điểm báo hiệu; nó không chứng minh tại đúng một thời điểm luồng đang ở trạng thái `WAITING`. Bài không dựa vào việc đọc `Thread.State` hoặc đo chính xác 100 ms. Khi `result.get(100, ...)` hết thời hạn, tác vụ vẫn tồn tại; `Future.get` không tự hủy nó. Sau khi luồng chính thêm `NEW`, lần `get()` tiếp theo nhận kết quả từ cùng tác vụ.

`result.get()` không có thời hạn trong ví dụ là có chủ đích: chỉ một bên lấy đang chạy và luồng chính vừa cung cấp đúng một phần tử. Trong một hệ thống thật, cần thiết kế đường hủy và xử lý lỗi của bên tạo thay vì mặc định rằng dữ liệu chắc chắn sẽ đến.

## 5. Chọn phương thức theo cách muốn xử lý lúc rỗng

Không phải trường hợp nào cũng nên chờ vô hạn. Câu hỏi thực tế là: “Nếu chưa có việc, luồng này được phép làm gì tiếp?”

| Nhu cầu | Ở đầu deque | Ở cuối deque |
| --- | --- | --- |
| Phải chờ đến khi có việc, nhưng vẫn cho phép ngắt | `takeFirst()` | `takeLast()` |
| Không chờ; rỗng thì nhận `null` | `pollFirst()` | `pollLast()` |
| Chờ có giới hạn; hết thời gian thì nhận `null` | `pollFirst(timeout, unit)` | `pollLast(timeout, unit)` |
| Chỉ xem, không lấy khỏi deque | `peekFirst()` | `peekLast()` |

Đây là các lựa chọn khác nhau về hợp đồng khi chưa có phần tử. Với phiên bản `poll` có thời hạn, vẫn phải xử lý `InterruptedException`. [So sánh các nhóm thao tác của BlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingDeque.html)

Ví dụ minh họa lựa chọn thời hạn, không phải chương trình độc lập:

```java
String job = deque.pollLast(2, TimeUnit.SECONDS);
if (job == null) {
    // Chưa nhận được công việc trong thời gian cho phép.
    // Ứng dụng quyết định thử lại, báo hết thời gian hoặc làm việc khác.
} else {
    process(job);
}
```

Đừng thay `takeFirst()` bằng `removeFirst()` rồi bắt ngoại lệ trong vòng lặp để mô phỏng chờ. Làm như vậy diễn đạt sai một trạng thái bình thường của hệ thống thành chuỗi lỗi và vẫn cần tự giải quyết việc chờ.

## 6. Ngắt luồng là một đường thoát cần thiết

`takeFirst()` và `takeLast()` có thể kết thúc bằng `InterruptedException`. Việc ngắt (interrupt) là cơ chế phối hợp để yêu cầu tác vụ dừng chờ; ứng dụng vẫn phải quyết định xử lý và kết thúc tác vụ như thế nào. Không coi đây là một phần tử nhận được, và không bắt rồi bỏ qua.

Nếu phương thức đang viết có thể khai báo `throws InterruptedException`, hãy để ngoại lệ truyền lên nơi quản lý vòng đời tác vụ. Nếu đang ở biên `Runnable` và muốn kết thúc vòng lặp, có thể dùng mẫu sau. Đây là đoạn minh họa bên trong `run()`, cần `deque` và `process` của ứng dụng:

```java
try {
    while (true) {
        String job = deque.takeFirst();
        process(job);
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Thoát run(); không tiếp tục vòng lặp lấy công việc.
}
```

Mẫu này khôi phục cờ ngắt để giữ lại tín hiệu cho tầng quan sát bên ngoài rồi kết thúc tác vụ. Chỉ đặt lại cờ và lập tức quay vào vòng lặp chờ có thể khiến tác vụ liên tục gặp ngắt mà không tiến triển. [Ngắt luồng trong Java](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#interrupt())

Khi công việc mới và yêu cầu ngắt xuất hiện gần nhau, không tự hứa rằng “gọi interrupt là chắc chắn không lấy phần tử”. Có thể thao tác lấy đã hoàn tất trước khi tín hiệu được xử lý. Vì thế dừng hệ thống còn cần chính sách cho công việc đã lấy ra: xử lý xong, hoàn trả hay lưu để thử lại. Cờ ngắt không tự thực hiện những chính sách đó.

## 7. Những lỗi dễ làm chương trình chờ mãi

### Kiểm tra rỗng rồi mới lấy

```java
// Không dùng kiểm tra này như điều kiện bảo đảm lần take sẽ không chờ.
if (!deque.isEmpty()) {
    String job = deque.takeFirst();
    process(job);
}
```

`isEmpty()` chỉ phản ánh trạng thái tại lần kiểm tra. Một luồng khác có thể lấy phần tử cuối cùng trước khi luồng hiện tại gọi `takeFirst()`. Nếu yêu cầu là không chờ, dùng trực tiếp `pollFirst()` và xử lý `null`; nếu yêu cầu là chờ, dùng trực tiếp `takeFirst()`.

### Bên tạo và bên lấy bị xếp vào cùng một luồng thực thi

Giả sử một executor chỉ có một luồng. Tác vụ thứ nhất chờ `takeFirst()` trên deque rỗng, còn tác vụ thứ hai trong chính executor đó mới chịu trách nhiệm thêm phần tử. Tác vụ thứ hai không có luồng để chạy, nên chương trình có thể không tiến triển.

Trong ví dụ hoàn chỉnh, bên thêm `NEW` là luồng chính, độc lập với executor có một luồng. Khi tổ chức hệ thống thật, cần bảo đảm bên tạo có thể chạy trong lúc bên lấy đang đợi.

### Mong deque tự biết “đã hết việc”

Rỗng chỉ có nghĩa chưa có phần tử tại thời điểm đó. Nó không biểu thị “sẽ không còn công việc nào nữa”. `BlockingDeque` không cung cấp thao tác đóng để mọi `take` tự kết thúc. Không dùng `null` làm tín hiệu kết thúc vì deque không nhận `null`.

Có thể thiết kế tín hiệu kết thúc riêng hoặc dùng ngắt do thành phần quản lý tác vụ điều phối. Nếu có nhiều bên lấy hoặc trộn hai đầu, tín hiệu kết thúc cũng phải có quy tắc phân phối và thứ tự rõ ràng; đặt một phần tử báo dừng vào deque không mặc nhiên dừng được tất cả luồng.

### Giữ khóa ngoài trong khi chờ

Nếu bên lấy giữ một khóa của ứng dụng rồi gọi `takeFirst()`, trong khi bên tạo cần chính khóa đó mới thêm được công việc, hai bên có thể khóa cứng lẫn nhau. Không giữ khóa ngoài chỉ để bọc một thao tác deque vốn đã an toàn đồng thời. An toàn của deque không tự giải quyết những khóa mà ứng dụng giữ bên ngoài.

### Nhầm thời gian chờ với độ phức tạp của thao tác

`LinkedBlockingDeque` thực hiện phần lớn thao tác trong thời gian hằng số khi không tính thời gian bị chặn. Một lần `take` vẫn có thể chờ rất lâu vì chưa có công việc; không dùng ký hiệu độ phức tạp để suy ra giới hạn độ trễ. [Đặc điểm LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html)

## 8. Tự kiểm tra trước khi dùng

- Muốn lấy ở đầu hay cuối? Chọn theo quy tắc sắp xếp công việc của ứng dụng.
- Luồng có được chờ đến khi có phần tử không? Nếu không, chọn `poll`; nếu chỉ được chờ có giới hạn, chọn `poll` có thời hạn.
- Ai có thể thêm công việc trong lúc luồng này đang đợi? Bên đó có đủ tài nguyên để chạy không?
- Khi hệ thống dừng, ai yêu cầu ngắt hoặc phát tín hiệu kết thúc? Công việc đã lấy ra sẽ được xử lý thế nào?
- Có kiểm tra `isEmpty()` hoặc khóa ngoài nào đang được dùng như một bảo đảm sai về lần lấy tiếp theo không?

Bài tập: trong phần đầu của `TakeEndsDemo`, đổi lần lấy thứ nhất thành `takeLast()` và lần thứ hai thành `takeFirst()`. Dự đoán ba giá trị được lấy trước khi chạy: C, A, B. Tiếp theo, đổi lời gọi chờ trong tác vụ thành `takeLast()`: chương trình vẫn nhận `NEW` vì lúc thêm chỉ có duy nhất một phần tử. Hai thử nghiệm giúp tách biệt việc chọn đầu lấy với việc chờ khi rỗng.
