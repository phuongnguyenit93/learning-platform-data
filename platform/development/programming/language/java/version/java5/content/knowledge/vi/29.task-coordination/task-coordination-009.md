# Chính sách công bằng của Semaphore

## 1. Giấy phép và thứ tự chờ là hai câu hỏi khác nhau

`Semaphore` quản lý một số giấy phép (permit). Tác vụ phải lấy giấy phép trước khi sử dụng một tài nguyên có giới hạn, rồi trả lại khi kết thúc.

Ví dụ, chỉ cho tối đa bốn tác vụ cùng thực hiện một loại công việc:

```java
Semaphore slots = new Semaphore(4, true);
```

Số `4` quyết định giới hạn đồng thời; `true` quyết định chính sách xét thứ tự khi có tranh chấp. Tăng số giấy phép không tự làm thứ tự công bằng hơn, và bật công bằng không làm tăng sức chứa.

Công bằng ở đây trả lời: **khi nhiều bên đang cạnh tranh, bên nào được xét lấy giấy phép trước?** Nó không phải cam kết chia đều CPU, chia đều số yêu cầu hay cho mọi tác vụ kết thúc theo một thứ tự tuyệt đối.

`Semaphore` có từ Java 5 và vẫn được dùng trong Java hiện đại. Bài dùng ví dụ Java 17 trở lên, tập trung vào hợp đồng công bằng hiện hành.

## 2. Khởi tạo fair và nonfair

```java
Semaphore defaultSlots = new Semaphore(2);
Semaphore nonfairSlots = new Semaphore(2, false);
Semaphore fairSlots = new Semaphore(2, true);
```

Hai dòng đầu dùng chính sách không công bằng (nonfair). Dòng cuối bật chính sách công bằng (fair).

Với nonfair, bên mới có thể lấy được giấy phép trước một bên đã chờ. Hiện tượng chen lên này thường gọi là barging. Nonfair không có nghĩa là mọi lần chạy đều đảo thứ tự; nó có nghĩa không có bảo đảm thứ tự FIFO cho việc cấp giấy phép.

Với fair, các lời gọi lấy giấy phép thuộc hợp đồng công bằng được xét theo thứ tự vào trước, ra trước (FIFO) tại điểm xác định bên trong phương thức.

Có thể kiểm tra cấu hình bằng `isFair()`. Cờ này không đổi sau khi tạo đối tượng; nó không phải số liệu đo được từ một lần chạy.

## 3. FIFO không dựa đơn thuần vào thời điểm gọi hay thứ tự start

Giả sử:

```text
Luồng A gọi acquire()
A bị tạm dừng trước điểm xếp thứ tự nội bộ
Luồng B gọi acquire() và đến điểm đó trước
```

B có thể được xét trước A dù A đã bắt đầu lời gọi sớm hơn trên đồng hồ.

Tương tự, một luồng đã lấy được giấy phép có thể bị bộ lập lịch tạm dừng trước khi in log. Dòng log của nó có thể xuất hiện sau log của luồng khác. Vì vậy không thể kết luận vi phạm công bằng chỉ từ:

- Thứ tự gọi `Thread.start()`.
- Thứ tự in “bắt đầu”.
- Thời gian ghi log trước hoặc sau lời gọi `acquire`.
- Thứ tự hoàn tất nghiệp vụ sau khi đã lấy giấy phép.

Công bằng điều khiển thứ tự xét cấp giấy phép ở điểm nội bộ; bộ lập lịch vẫn quyết định khi nào luồng được chạy. Nó không đưa ra một giới hạn thời gian chờ tuyệt đối nếu tài nguyên không được trả hoặc một luồng không được lập lịch.

## 4. Ngoại lệ quan trọng: tryAcquire không có thời gian chờ

Hai phương thức sau **không tuân thủ cờ fair**:

```java
boolean one = slots.tryAcquire();
boolean several = slots.tryAcquire(2);
```

Nếu đủ giấy phép ở thời điểm thử, chúng có thể lấy ngay dù có bên đang chờ. Do đó, một semaphore được tạo bằng `true` vẫn có thể bị đường gọi `tryAcquire()` chen ngang.

Đừng viết đường “thử nhanh trước, nếu thất bại mới chờ” rồi cho rằng toàn bộ hệ thống luôn theo FIFO:

```java
// Có thể chen ngang dù slots là fair.
if (!slots.tryAcquire()) {
    slots.acquire();
}
```

Nếu cần thử ngay nhưng vẫn tôn trọng chính sách fair, dùng biến thể có thời gian chờ bằng không:

```java
boolean acquired = slots.tryAcquire(0, TimeUnit.SECONDS);
```

Với nhiều giấy phép:

```java
boolean acquired = slots.tryAcquire(2, 0, TimeUnit.SECONDS);
```

Cần import `java.util.concurrent.TimeUnit` và xử lý `InterruptedException`. Đây là khác biệt nữa so với biến thể không có thời gian chờ: lời gọi có thời gian chờ vẫn phát hiện ngắt.

Thời gian bằng không có nghĩa không chờ thêm, không có nghĩa bỏ qua hàng đợi. Nếu không được phép lấy ngay theo chính sách fair, nó trả `false`.

| Cách lấy | Có xét cờ fair? | Cách báo không lấy được |
| --- | --- | --- |
| `acquire()`, `acquire(n)` | Có | Chờ; có thể bị ngắt |
| `tryAcquire()`, `tryAcquire(n)` | Không | Trả `false` ngay |
| `tryAcquire(timeout, unit)` và biến thể nhiều giấy phép | Có | Trả `false` khi hết thời gian; có thể bị ngắt |
| `acquireUninterruptibly` | Có xét chính sách cấp | Không thoát chờ bằng `InterruptedException` |

“Có xét cờ fair” nghĩa là dùng chế độ đã cấu hình, không phải biến thể có thời gian chờ tự biến một semaphore nonfair thành fair.

## 5. Yêu cầu nhiều giấy phép và việc chặn đầu hàng

Giả sử semaphore fair đang có hai giấy phép:

```text
A đã đứng trước, cần 3 giấy phép
B đứng sau, cần 1 giấy phép
available = 2
```

A chưa đủ ba giấy phép nên chưa lấy được. B dùng đường lấy tuân thủ công bằng sẽ không được bỏ qua A chỉ vì yêu cầu của B nhỏ hơn.

Đây là việc chặn ở đầu hàng (head-of-line blocking): một yêu cầu lớn ở trước có thể khiến giấy phép còn lại chưa được dùng bởi các yêu cầu nhỏ phía sau.

Với nonfair, B có thể lấy được, nhưng không có bảo đảm lựa chọn yêu cầu nhỏ trước. Semaphore không phải bộ lập lịch tối ưu kích thước yêu cầu.

Nếu B dùng `tryAcquire()` không có thời gian chờ thì ngay cả fair cũng có thể bị chen ngang. Phân tích chính sách phải xem **toàn bộ các đường lấy giấy phép**, không chỉ hàm khởi tạo.

Một yêu cầu `acquire(n)` lấy đủ n giấy phép như một lần cấp; nó không lấy một phần rồi giữ phần đó để đợi tiếp. Không thay nó máy móc bằng vòng lặp n lần `acquire()`: việc lấy từng phần có thể tạo hành vi khác và khiến nhiều bên cùng giữ một phần rồi chờ phần còn lại.

## 6. Ví dụ chạy được: thử theo fair và thử chen ngang

Thí nghiệm sau cố định một người đợi cần hai giấy phép. Khi mới có một giấy phép, thử ngay bằng biến thể có thời gian chờ tuân thủ fair phải nhường người đợi đó; thử không có thời gian chờ có thể lấy giấy phép.

Lưu thành `SemaphoreFairnessDemo.java`:

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class SemaphoreFairnessDemo {
    private static void waitForQueuedThread(
            Semaphore gate,
            Thread waiter) {
        long started = System.nanoTime();
        long limit = TimeUnit.SECONDS.toNanos(5);

        while (!gate.hasQueuedThreads()) {
            if (!waiter.isAlive()) {
                throw new IllegalStateException("Waiter terminated");
            }
            if (System.nanoTime() - started > limit) {
                throw new IllegalStateException("Waiter was not queued in time");
            }
            Thread.onSpinWait();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Semaphore gate = new Semaphore(0, true);
        String[] outcome = new String[1];

        Thread largeRequest = new Thread(() -> {
            try {
                gate.acquire(2);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                outcome[0] = "interrupted";
                return;
            }
            try {
                outcome[0] = "acquired-2";
            } finally {
                gate.release(2);
            }
        });

        largeRequest.start();
        try {
            waitForQueuedThread(gate, largeRequest);

            gate.release();
            int beforeTry = gate.availablePermits();

            boolean fairTry =
                    gate.tryAcquire(1, 0, TimeUnit.NANOSECONDS);
            if (fairTry) {
                gate.release();
            }

            boolean untimedTry = gate.tryAcquire();
            if (untimedTry) {
                gate.release();
            }

            gate.release();
            largeRequest.join();

            System.out.println("fair=" + gate.isFair());
            System.out.println("beforeTry=" + beforeTry);
            System.out.println("fairTry=" + fairTry);
            System.out.println("untimedTry=" + untimedTry);
            System.out.println("large=" + outcome[0]);
            System.out.println("remaining=" + gate.availablePermits());
        } finally {
            largeRequest.interrupt();
            largeRequest.join();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 SemaphoreFairnessDemo.java
java SemaphoreFairnessDemo
```

Stdout khi luồng đợi được lập lịch vào hàng trong giới hạn thí nghiệm và chương trình không bị ngắt từ bên ngoài:

```text
fair=true
beforeTry=1
fairTry=false
untimedTry=true
large=acquired-2
remaining=2
```

Giải thích:

1. `largeRequest` cần hai giấy phép; ban đầu không có giấy phép nào.
2. Sau khi nó đã xếp hàng, luồng chính cấp một giấy phép. Người đợi chưa thể lấy một phần.
3. Biến thể có thời gian chờ bằng không tuân thủ fair nên không vượt người đợi phía trước; kết quả là `false`.
4. `tryAcquire()` không có thời gian chờ lấy ngay một giấy phép; kết quả là `true`.
5. Luồng chính trả lại giấy phép vừa lấy, rồi cấp thêm một giấy phép mới. Khi đủ hai giấy phép, yêu cầu lớn được đáp ứng và sau đó trả cả hai.

`hasQueuedThreads()` trong ví dụ là dụng cụ quan sát **chỉ dành cho thí nghiệm có một người đợi đã biết, không có timeout hoặc hủy tự phát**. Nó không phải cách thiết kế thứ tự nghiệp vụ tổng quát. Giới hạn năm giây giúp thí nghiệm báo lỗi nếu môi trường không cho luồng đợi chạy kịp, thay vì quay vô hạn.

Trong hệ thống thật, hàng đợi thay đổi do ngắt và hủy; không dùng `hasQueuedThreads`, `getQueueLength` hay `availablePermits` để thay thao tác cấp giấy phép. Độ an toàn vẫn phải do chính `acquire`/`tryAcquire` quyết định.

Lệnh ngắt trong `finally` giúp thu hồi người đợi nếu bước thiết lập thí nghiệm thất bại. Nó không tham gia tạo kết quả bình thường ở trên.

## 7. Bảo đảm công bằng chỉ có ích nếu quản lý giấy phép đúng

Mẫu giới hạn tài nguyên thường dùng:

```java
// Mã bên trong phương thức có thể ném InterruptedException.
slots.acquire();
try {
    useLimitedResource();
} finally {
    slots.release();
}
```

Phải vào `try/finally` sau khi lấy giấy phép thành công. Nếu `acquire` bị ngắt trước khi lấy được, không trả một giấy phép chưa lấy.

Với thử có thời gian chờ:

```java
boolean acquired = slots.tryAcquire(1, TimeUnit.SECONDS);
if (!acquired) {
    return;
}
try {
    useLimitedResource();
} finally {
    slots.release();
}
```

Đây là đoạn minh họa trong phương thức void có chính sách truyền ngắt lên. `useLimitedResource` đại diện cho phần nghiệp vụ thực tế.

Semaphore không có khái niệm chủ sở hữu giống một khóa tái nhập. Một luồng khác có thể gọi `release`; thư viện không tự kiểm tra nó có từng lấy giấy phép tương ứng hay chưa. Nếu trả thừa, giới hạn tài nguyên có thể bị tăng sai. Nếu quên trả, người đứng đầu hàng vẫn không thể tiến triển dù fair đã bật.

Không giữ một khóa khác khi chờ semaphore nếu bên trả giấy phép cần chính khóa đó. Công bằng không loại bỏ bế tắc.

## 8. Công bằng, chống đói và thông lượng

Chính sách fair giúp hạn chế việc yêu cầu đã chờ bị các bên mới liên tục vượt qua, miễn là các bên dùng đường cấp tuân thủ công bằng. Nó hữu ích khi cần thứ tự chờ dễ dự đoán hơn cho tài nguyên dùng chung.

Tuy nhiên, không suy ra một cam kết vô điều kiện rằng mỗi yêu cầu luôn hoàn tất trong thời gian hữu hạn:

- Tác vụ đang giữ giấy phép có thể không trả.
- Yêu cầu phía trước có thể đòi nhiều hơn lượng giấy phép mà hệ thống có thể cung cấp.
- Một luồng có thể không được bộ lập lịch cho chạy kịp.
- Những đường `tryAcquire` không có thời gian chờ có thể tiếp tục chen ngang.
- Hệ thống có thể đã bị bế tắc bởi tài nguyên khác.

Nonfair có thể cho thông lượng tốt hơn trong một số tải vì cho phép bên đang chạy lấy giấy phép sẵn có mà không phải chờ thứ tự. Fair có thể làm thời gian chờ ổn định hơn nhưng tăng chi phí phối hợp hoặc để trống tạm thời một phần tài nguyên khi yêu cầu đầu hàng quá lớn.

Đây là các đánh đổi cần đo bằng tải thực tế, không phải định luật “fair luôn chậm” hay “nonfair luôn nhanh”. Khi đánh giá, xem cả tổng thông lượng, phân bố thời gian chờ và số yêu cầu bị hết hạn.

## 9. Fair không tạo ưu tiên nghiệp vụ hay chia suất theo khách hàng

Một semaphore fair không tự biết:

- Người dùng nào là khách hàng trả phí.
- Một khách hàng đã gửi nhiều yêu cầu hơn khách khác.
- Yêu cầu nào có hạn chót gần hơn.
- Tài nguyên nào phù hợp hơn với một yêu cầu cụ thể.

Nếu một khách hàng gửi hàng nghìn tác vụ vào trước, FIFO theo lần lấy giấy phép vẫn có thể khiến khách hàng khác phải chờ lâu. Công bằng theo luồng/lần gọi không đồng nghĩa công bằng theo tài khoản.

Khi cần chính sách như hạn mức riêng từng khách hàng, ưu tiên hoặc luân phiên giữa nhóm, cần thiết kế hàng đợi và bộ điều phối ở tầng ứng dụng. Semaphore vẫn có thể đóng vai trò giới hạn số công việc đang thực hiện, nhưng không thay thế toàn bộ chính sách phân phối.

## 10. Tự kiểm tra

1. `new Semaphore(3)` có bật fair không?
2. Một semaphore fair có bảo đảm log sau acquire xuất hiện đúng thứ tự gọi start không?
3. `tryAcquire()` có phải nhường người đang đợi khi đã bật fair không?
4. Muốn thử ngay và vẫn xét fair, dùng biến thể nào?
5. A cần ba giấy phép ở đầu hàng; B cần một giấy phép phía sau; hiện có hai giấy phép. Với đường lấy fair, B có được ưu tiên vì yêu cầu nhỏ hơn không?
6. Bật fair có sửa được lỗi quên release không?

Đáp án:

1. Không; mặc định là nonfair.
2. Không; còn có điểm xếp thứ tự nội bộ và bộ lập lịch.
3. Không; biến thể không có thời gian chờ cho phép chen ngang.
4. `tryAcquire(0, unit)` hoặc `tryAcquire(n, 0, unit)`, đồng thời xử lý ngắt.
5. Không; FIFO không phải chính sách ưu tiên yêu cầu nhỏ.
6. Không; phải sửa giao thức quản lý giấy phép.

Khi lựa chọn chính sách, hãy xác định công bằng đối với ai, kiểm tra mọi đường lấy giấy phép và bảo đảm từng giấy phép được trả đúng theo vòng đời tài nguyên.

## Tài liệu đối chiếu

- [Semaphore — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Semaphore.html): mô tả fairness, điểm FIFO nội bộ, ngoại lệ của tryAcquire không có thời gian chờ và các biến thể nhiều giấy phép.
