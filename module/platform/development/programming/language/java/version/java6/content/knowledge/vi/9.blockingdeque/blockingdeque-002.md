# LinkedBlockingDeque có giới hạn dung lượng

## 1. Vì sao một deque đồng thời cần giới hạn?

`LinkedBlockingDeque<E>` là một hàng đợi hai đầu, hỗ trợ nhiều luồng thêm/lấy phần tử và có các thao tác chờ khi chưa thể thực hiện ngay.

Nếu bên tạo công việc nhanh hơn bên xử lý, số công việc đang chờ có thể tăng liên tục. Đặt giới hạn dung lượng giúp ứng dụng kiểm soát lượng **phần tử nằm trong deque**, rồi chọn cách phản ứng khi hết chỗ:

- Không chờ và báo không nhận được phần tử.
- Chờ đến khi có chỗ.
- Chờ trong một thời hạn rồi báo thất bại.
- Xem đầy là trạng thái lỗi và ném ngoại lệ.

Giới hạn dung lượng là một phần của cơ chế phản hồi áp lực tải (backpressure): tốc độ nhận thêm việc phải gắn với khả năng giải phóng chỗ trống. Nó không tự làm bên xử lý nhanh hơn.

Đây vẫn là API hiện hành; xem [LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html).

## 2. Tạo deque có dung lượng cố định

```java
BlockingDeque<String> jobs = new LinkedBlockingDeque<>(100);
```

Đoạn minh họa tạo deque chứa tối đa 100 phần tử tại một thời điểm.

- Tham số capacity phải lớn hơn 0.
- Dung lượng là giới hạn cố định của đối tượng, không phải “sức chứa ban đầu rồi tự tăng”.
- Hai đầu dùng chung một giới hạn; không phải 100 phần tử mỗi đầu.
- Phần tử null không được chấp nhận.
- `clear()` xóa dữ liệu nhưng không đổi giới hạn đã cấu hình.

Constructor không truyền dung lượng dùng `Integer.MAX_VALUE`. Đây là một giới hạn rất lớn, không phải một chính sách bảo vệ bộ nhớ phù hợp cho mọi ứng dụng.

Constructor nhận một collection cũng dùng dung lượng `Integer.MAX_VALUE`, không tự biến kích thước collection đầu vào thành giới hạn nhỏ. Nếu muốn giới hạn rõ, tạo bằng constructor nhận capacity rồi nạp dữ liệu theo quy tắc đã chọn. Xem [các constructor LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html).

Lớp dùng các nút liên kết được tạo khi chèn. Đặt capacity không có nghĩa đã đặt trước toàn bộ bộ nhớ cho capacity đối tượng công việc.

## 3. Chọn phương thức theo cách xử lý khi đầy

Hai đầu có các họ phương thức tương ứng:

| Khi thêm mà deque đầy | Đầu trước | Đầu sau |
| --- | --- | --- |
| Ném `IllegalStateException` | `addFirst(e)` | `addLast(e)` |
| Báo false, không chờ có chỗ | `offerFirst(e)` | `offerLast(e)` |
| Chờ có chỗ | `putFirst(e)` | `putLast(e)` |
| Chờ có chỗ với thời hạn | `offerFirst(e, t, unit)` | `offerLast(e, t, unit)` |

`putFirst/putLast` và các overload có thời hạn có thể ném `InterruptedException`. Khi thời hạn chờ thêm kết thúc mà chưa chèn được, timed offer trả false.

Đây là khác biệt về **chính sách chờ chỗ trống**. Không nên dùng từ “không bao giờ chặn” cho offer rồi suy rằng nó không có bất kỳ tranh chấp nội bộ nào. Xem [bảng hợp đồng BlockingDeque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingDeque.html).

Khi lấy dữ liệu cũng có các lựa chọn tương ứng: remove ném ngoại lệ nếu rỗng, poll trả null, take chờ có phần tử, timed poll chờ trong thời hạn. Trong bài, chúng chủ yếu được dùng để giải phóng chỗ cho bên thêm.

## 4. Ví dụ đầy đủ chạy trên Java 17+

Chương trình kiểm tra trạng thái đầy theo cách xác định, sau đó dùng một bên tạo và một bên tiêu thụ để chuyển ba công việc qua deque dung lượng 2.

Tệp `BoundedDequeDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.TimeUnit;

public class BoundedDequeDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingDeque<String> deque = new LinkedBlockingDeque<>(2);
        deque.addLast("A");
        deque.addLast("B");
        System.out.println("full=" + deque);
        System.out.println("remaining when full=" + deque.remainingCapacity());
        System.out.println("offerFirst when full=" + deque.offerFirst("C"));

        try {
            deque.addLast("C");
            throw new AssertionError("addLast should fail when full");
        } catch (IllegalStateException expected) {
            System.out.println("addLast when full=IllegalStateException");
        }

        System.out.println("timed offer when full="
                + deque.offerLast("C", 20, TimeUnit.MILLISECONDS));
        System.out.println("removeFirst=" + deque.removeFirst());
        System.out.println("offerFirst after removal=" + deque.offerFirst("C"));
        System.out.println("after replacement=" + deque);
        deque.clear();
        System.out.println("remaining after clear=" + deque.remainingCapacity());

        List<String> consumed = new ArrayList<>();
        Thread consumer = new Thread(() -> {
            try {
                for (int i = 0; i < 3; i++) {
                    consumed.add(deque.takeFirst());
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        deque.putLast("job-1");
        deque.putLast("job-2");
        deque.putLast("job-3");
        consumer.join();

        if (!consumed.equals(List.of("job-1", "job-2", "job-3"))) {
            throw new AssertionError("Unexpected consumed order");
        }
        System.out.println("consumed=" + consumed);
        System.out.println("final size=" + deque.size());
        System.out.println("final remaining=" + deque.remainingCapacity());

        try {
            new LinkedBlockingDeque<String>(0);
            throw new AssertionError("capacity zero should fail");
        } catch (IllegalArgumentException expected) {
            System.out.println("capacity zero=IllegalArgumentException");
        }
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```shell
javac -encoding UTF-8 BoundedDequeDemo.java
java BoundedDequeDemo
```

Kết quả chính xác:

```text
full=[A, B]
remaining when full=0
offerFirst when full=false
addLast when full=IllegalStateException
timed offer when full=false
removeFirst=A
offerFirst after removal=true
after replacement=[C, B]
remaining after clear=2
consumed=[job-1, job-2, job-3]
final size=0
final remaining=2
capacity zero=IllegalArgumentException
```

## 5. Điều gì diễn ra khi đã đầy?

### Hai đầu không có hai kho chỗ trống riêng

Sau khi thêm A và B vào cuối, dung lượng 2 đã đầy. `offerFirst("C")` vẫn thất bại dù đang thêm ở đầu khác.

Dung lượng xét toàn deque. Thêm đầu hay thêm cuối chỉ quyết định vị trí trong dãy, không tạo thêm chỗ.

### add và offer biểu diễn thất bại khác nhau

`addLast("C")` ném `IllegalStateException`; `offerFirst("C")` trả false. Không được bỏ qua false rồi coi công việc đã được nhận.

Chương trình bắt đúng loại ngoại lệ mong đợi. Nếu add không ném lỗi khi đầy, nó chủ động ném `AssertionError` để ca kiểm tra thất bại.

### Timed offer không tự xóa phần tử cũ

Trong giai đoạn kiểm tra đầy chưa có luồng tiêu thụ. Vì không ai giải phóng chỗ, timed offer trả false sau khi không chèn được trong thời hạn.

Nó không bỏ A hoặc B để lấy chỗ cho C. Giới hạn dung lượng không tự chọn chính sách loại bỏ việc cũ hay việc mới.

Mốc 20 mili giây trong ví dụ chỉ là thời hạn yêu cầu của API. Không dùng stdout để suy rằng thời gian thực tế luôn chính xác 20 mili giây trên mọi máy và lịch chạy.

### Lấy ra một phần tử tạo lại chỗ trống

`removeFirst()` trả A, còn `[B]`. `offerFirst("C")` sau đó thành công, dãy là `[C, B]`.

Ví dụ này cho thấy thứ tự hai đầu hoạt động độc lập với giới hạn dung lượng: khi có chỗ, có thể thêm đúng phía cần dùng.

## 6. put và take phối hợp qua khả năng chờ

Giai đoạn thứ hai bắt đầu sau `clear()`, với dung lượng còn lại là 2.

Luồng chính gọi `putLast` cho job-1, job-2 và job-3. Luồng consumer gọi `takeFirst` ba lần.

- Khi deque rỗng, consumer có thể chờ ở take.
- Khi deque đầy, bên tạo có thể chờ ở put.
- Một lần lấy giải phóng chỗ cho bên thêm.
- Một lần thêm cung cấp dữ liệu cho bên lấy.

Lịch chạy thực tế quyết định lời gọi nào đã phải đợi và đợi bao lâu. Chương trình không dùng sleep và không giả định put thứ ba chắc chắn phải bị chặn trong mọi lần chạy.

Với một bên tạo thêm cuối theo thứ tự cố định và một bên lấy đầu, kết quả được tiêu thụ là FIFO: `job-1, job-2, job-3`. Nếu có nhiều bên tạo, thứ tự xen kẽ giữa các bên phụ thuộc những lần chèn thực sự thành công; không suy ra thứ tự từ tên luồng.

Danh sách `consumed` trong ví dụ chỉ được consumer sửa. Luồng chính đọc nó sau `join()`, khi consumer đã kết thúc, nên không có truy cập sửa/đọc đồng thời vào `ArrayList` đó.

Khả năng bàn giao dữ liệu giữa các luồng là một phần của hợp đồng `BlockingDeque`; xem [BlockingDeque: memory consistency effects](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingDeque.html).

## 7. remainingCapacity không phải một quyền đặt chỗ

Với deque dung lượng C và một trạng thái ổn định:

```text
remainingCapacity = C - số phần tử hiện có
```

Nhưng trong mã nhiều luồng, quan sát chỗ trống rồi chèn là hai thao tác riêng:

```java
// Khong dung de bao dam chac chan lan them se thanh cong.
if (jobs.remainingCapacity() > 0) {
    jobs.addLast(job);
}
```

Một luồng khác có thể lấy mất chỗ trống trước lần add. Mỗi phép gọi vẫn đúng hợp đồng, nhưng chuỗi quyết định của ứng dụng chưa nguyên tử.

Hãy gọi trực tiếp phương thức có chính sách mong muốn:

```java
// jobs la BlockingDeque<Job>, job la mot cong viec hop le.
boolean accepted = jobs.offerLast(job);
if (!accepted) {
    // Xu ly viec khong duoc nhan theo chinh sach cua ung dung.
}
```

Đây là mã minh họa, không phải chương trình độc lập.

Dùng `remainingCapacity` hoặc `size` để quan sát, giám sát và chẩn đoán; không coi số vừa đọc là một suất trống đã được giữ riêng cho luồng đó. Xem [BlockingQueue.remainingCapacity](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

## 8. Giới hạn số phần tử không phải giới hạn toàn bộ bộ nhớ

Capacity đếm các phần tử còn nằm trong deque. Nó không đo:

- Kích thước dữ liệu mà từng phần tử tham chiếu tới.
- Công việc đã được lấy ra nhưng vẫn đang xử lý.
- Candidate mà các luồng tạo đã dựng xong và đang giữ trong lúc chờ put.
- Công việc được lưu ở bộ đệm khác hoặc hàng đợi khác của hệ thống.

Vì vậy capacity 100 không chứng minh ứng dụng chỉ dùng bộ nhớ cho đúng 100 công việc. Nếu cần kiểm soát cả số công việc đang xử lý, kích thước tải hoặc tổng tài nguyên, phải thiết kế thêm cơ chế quản lý phù hợp.

Tương tự, nhận thành công vào deque chỉ nghĩa là phần tử đã được xếp vào đó. Nó không có nghĩa công việc đã xử lý xong, đã lưu bền hay có thể phục hồi sau khi tiến trình dừng.

## 9. Chọn phản ứng khi hết chỗ

### Chờ bằng put

Phù hợp khi bên tạo có thể chậm lại và có một bên khác chắc chắn tiếp tục giải phóng chỗ. Cần có chính sách ngắt/hủy và theo dõi thời gian chờ nếu nghiệp vụ yêu cầu.

Không gọi put vô thời hạn trên một luồng không được phép chờ lâu mà chưa thiết kế rõ hậu quả.

### Offer không chờ hoặc có thời hạn

Phù hợp khi nơi gọi phải đưa ra quyết định tiếp nhận trong một thời gian giới hạn. Khi nhận false, ứng dụng phải chủ động chọn báo bận, thử lại theo chính sách, chuyển hướng hoặc một hành vi khác.

Đừng thử lại ngay trong vòng lặp nóng vô hạn khi consumer đang quá tải. Bounded deque chỉ hữu ích nếu nơi gọi xử lý kết quả tiếp nhận một cách có ý nghĩa.

### Add khi đầy là lỗi theo giả định chương trình

Add hợp lý nếu hợp đồng của đoạn mã cho rằng chắc chắn còn chỗ và đầy là một sai lệch cần phát hiện. Nếu đầy là trạng thái bình thường của tải, offer thường biểu diễn nhánh ấy rõ hơn việc dùng ngoại lệ làm luồng điều khiển chính.

Không tự động xóa dữ liệu cũ để “chữa đầy” trừ khi nghiệp vụ đã định nghĩa rõ chính sách loại bỏ.

## 10. Vòng đời luồng và ngắt

Dung lượng hữu hạn tạo ra khả năng chờ, nên cũng có thể làm lộ lỗi phối hợp:

- Một luồng tự thêm nhiều hơn capacity mà không có ai lấy có thể dừng ở put.
- Nếu chỉ khởi động producer, chờ producer xong rồi mới chạy consumer, producer có thể không bao giờ xong.
- Nếu mọi worker trong một nhóm đều đang chờ thêm và không còn worker lấy, hệ thống không tiến triển.
- Giữ một khóa ngoài trong lúc chờ put, trong khi consumer cần khóa ấy để lấy hoặc xử lý, có thể tạo vòng chờ.

Ví dụ khởi động consumer trước khi luồng chính đưa ba việc vào. Số lần lấy được thỏa thuận trước là ba; không giả vờ rằng deque tự biết khi nào đã hết công việc của toàn hệ thống.

`BlockingQueue/BlockingDeque` không tự có một thao tác đóng tổng quát để báo không còn phần tử nào được thêm nữa. Ứng dụng thực tế cần quy tắc kết thúc/hủy phù hợp; xem [BlockingQueue và vòng đời](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

Khi bắt `InterruptedException` mà không truyền tiếp, cần có chính sách hủy và thường khôi phục trạng thái ngắt bằng `Thread.currentThread().interrupt()`. Ví dụ minh họa đường chạy bình thường không phát sinh ngắt; hệ thống thật còn cần phối hợp hủy producer và consumer để không để một phía chờ mãi.

## 11. Chọn dung lượng và kiểm thử

Dung lượng nên dựa trên nhịp tạo/tiêu thụ, mức tăng tải ngắn hạn có thể chấp nhận, độ trễ chờ và giới hạn tài nguyên. Dung lượng lớn có thể giữ được đợt tăng tải lâu hơn nhưng cũng giữ nhiều công việc chờ hơn; nó không giải quyết một tình trạng bên tạo luôn nhanh hơn bên xử lý trong dài hạn.

Các ca kiểm thử cần có:

1. Capacity bằng 1 hoặc 2 để dễ đi qua trạng thái rỗng/đầy.
2. Thêm ở cả hai đầu khi giới hạn chung đã đầy.
3. Offer false, add đúng ngoại lệ và timed offer hết thời hạn.
4. Lấy một phần tử rồi thêm lại thành công.
5. Clear giữ nguyên khả năng chứa tối đa đã cấu hình.
6. Producer và consumer cùng tiến triển, kiểm tra số lượng/thứ tự theo mô hình sử dụng.
7. Ngắt hoặc hủy khi đang chờ, với chính sách kết thúc rõ ràng.
8. Khởi tạo capacity không dương bị từ chối.

Bài tập: đổi capacity của ví dụ từ 2 xuống 1, cập nhật phần chuẩn bị dữ liệu đầy cho phù hợp rồi chạy lại giai đoạn producer–consumer. Giải thích vì sao vẫn có thể chuyển ba công việc nhưng không bao giờ cần chứa đồng thời cả ba trong deque.
