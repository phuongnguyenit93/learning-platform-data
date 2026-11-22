# drainTo và xử lý theo lô với BlockingQueue

Giả sử một luồng tiêu thụ lấy từng sự kiện từ hàng đợi rồi gửi từng yêu cầu ghi dữ liệu. Mỗi lần ghi có chi phí cố định: chuẩn bị câu lệnh, trao đổi qua mạng, chờ phản hồi. Khi hệ thống đích hỗ trợ xử lý theo lô (batch processing), ta có thể lấy một nhóm công việc rồi gửi chung để giảm số lần gọi.

`drainTo` là công cụ **lấy nhiều phần tử đang sẵn có ra khỏi hàng đợi và chuyển chúng vào một collection đích**. Nó không tự ghi dữ liệu, không đợi đủ một lô, và không biến quá trình xử lý phía sau thành giao dịch.

Bài dùng API vẫn áp dụng trong Java hiện đại và ví dụ chạy với Java 17 trở lên.

## 1. Hai dạng drainTo và giá trị trả về

```java
int moved = queue.drainTo(destination);
int movedAtMost = queue.drainTo(destination, maxElements);
```

Đây là hai lời gọi minh họa; `queue` là `BlockingQueue<E>`, còn `destination` là collection nhận được phần tử kiểu `E`.

| Dạng gọi | Mục tiêu |
|---|---|
| `drainTo(destination)` | Lấy các phần tử sẵn có, không đặt giới hạn số phần tử ngay trong lời gọi |
| `drainTo(destination, maxElements)` | Lấy tối đa `maxElements` phần tử sẵn có |

Giá trị trả về là số phần tử được chuyển trong lần gọi, không phải kích thước cuối của collection đích. `drainTo` thêm vào collection; nó không xóa dữ liệu cũ trong đó.

Ví dụ suy luận với hàng đợi FIFO, không có luồng khác can thiệp:

```text
Trước: queue = [A, B, C, D], destination = [X]
Gọi:   moved = queue.drainTo(destination, 2)
Sau:   moved = 2, queue = [C, D], destination = [X, A, B]
```

Nếu không có phần tử lấy được, kết quả là 0. Đây không phải tín hiệu rằng bên sản xuất đã dừng vĩnh viễn. `drainTo` không chờ phần tử mới như `take()`, nhưng cũng không có bảo đảm thời gian thực hay “không bao giờ phải chờ khóa nội bộ”. Hợp đồng chi tiết ở [BlockingQueue.drainTo](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html#drainTo(java.util.Collection,int)).

## 2. Lấy tối đa N khác với chờ đủ N

Nếu hàng đợi mới có hai phần tử, `drainTo(batch, 100)` không đợi thêm 98 phần tử. Lô thực tế có thể nhỏ hơn giới hạn. Điều này phù hợp khi muốn xử lý ngay phần đã sẵn có.

Cách gọi lặp sau là lỗi dễ gặp:

```java
// Đoạn minh họa lỗi: có thể liên tục quay vòng khi hàng đợi rỗng.
while (running) {
    List<Job> batch = new ArrayList<>();
    queue.drainTo(batch, 100);
    process(batch);
}
```

`Job`, `running`, `queue` và `process` thuộc ngữ cảnh ứng dụng, nên đoạn này không phải chương trình độc lập. Khi không có việc, vòng lặp vẫn chạy và có thể tiêu tốn CPU vô ích.

Một chính sách thường hữu ích là:

1. Chờ **một phần tử đầu tiên** bằng `take()`.
2. Lấy thêm ngay các phần tử sẵn có bằng `drainTo`.
3. Xử lý lô vừa nhận, dù chưa đạt kích thước tối đa.

Phần tử đầu đã được tính vào lô, nên phần lấy thêm phải là `maxBatchSize - 1`. Nếu dùng `drainTo(batch, maxBatchSize)`, lô có thể vượt giới hạn một phần tử.

## 3. Chương trình chạy đầy đủ

Lưu thành `DrainToDemo.java`. Ví dụ dùng `ArrayBlockingQueue` để thấy thứ tự FIFO và không có luồng khác sửa hàng đợi, nên stdout xác định.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class DrainToDemo {
    static <E> List<E> takeBatch(
            BlockingQueue<E> queue, int maxBatchSize)
            throws InterruptedException {
        if (maxBatchSize < 1) {
            throw new IllegalArgumentException("maxBatchSize must be positive");
        }

        List<E> batch = new ArrayList<>(maxBatchSize);
        batch.add(queue.take());
        if (maxBatchSize > 1) {
            queue.drainTo(batch, maxBatchSize - 1);
        }
        return batch;
    }

    static void processBatch(List<Integer> batch) {
        int sum = batch.stream().mapToInt(Integer::intValue).sum();
        System.out.println("processed: " + batch + ", sum=" + sum);
    }

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(6);
        for (int i = 1; i <= 5; i++) {
            queue.put(i);
        }

        List<Integer> destination = new ArrayList<>();
        destination.add(100);
        int moved = queue.drainTo(destination, 3);
        System.out.println("moved: " + moved);
        System.out.println("destination: " + destination);
        System.out.println("remaining: " + queue);
        System.out.println("free slots: " + queue.remainingCapacity());

        List<Integer> batch = takeBatch(queue, 4);
        System.out.println("batch size: " + batch.size());
        System.out.println("queue empty before processing: " + queue.isEmpty());
        processBatch(batch);

        List<Integer> emptyBatch = new ArrayList<>();
        System.out.println("drained from empty: "
                + queue.drainTo(emptyBatch, 4));
        System.out.println("empty batch: " + emptyBatch);

        queue.put(9);
        System.out.println("single-item batch: " + takeBatch(queue, 1));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 DrainToDemo.java
java DrainToDemo
```

Stdout:

```text
moved: 3
destination: [100, 1, 2, 3]
remaining: [4, 5]
free slots: 4
batch size: 2
queue empty before processing: true
processed: [4, 5], sum=9
drained from empty: 0
empty batch: []
single-item batch: [9]
```

Giải thích từng ranh giới:

- `moved` bằng 3 nhưng `destination.size()` bằng 4, vì đích đã có phần tử 100.
- Hàng đợi dung lượng 6 còn hai phần tử sau lần chuyển đầu, nên có bốn chỗ trống. `ArrayBlockingQueue` giữ thứ tự FIFO; xem [ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).
- `takeBatch(queue, 4)` lấy phần tử 4 bằng `take()`, rồi lấy thêm phần tử 5. Nó trả lô có hai phần tử thay vì đợi đủ bốn.
- Lúc bắt đầu `processBatch`, hàng đợi đã rỗng nhưng công việc vừa nhận mới bắt đầu được xử lý. **Đã lấy khỏi hàng đợi khác với đã xử lý xong.**
- `drainTo` trên hàng đợi rỗng trả 0; `takeBatch` trên hàng đợi rỗng sẽ chờ ở `take()`.

`processBatch` trong ví dụ chỉ tính tổng để minh họa vị trí xử lý sau khi đã thu thập lô. Gửi lô tới cơ sở dữ liệu hoặc dịch vụ khác cần dùng API theo lô thực sự của hệ thống đó; chỉ gom vào `List` rồi vẫn gọi từng yêu cầu mạng không tự loại bỏ chi phí của từng yêu cầu.

## 4. Chọn collection đích và quyền sở hữu lô

Dùng một `ArrayList` mới, chỉ do luồng tiêu thụ hiện tại sở hữu, là lựa chọn dễ hiểu:

```java
List<Event> batch = new ArrayList<>(batchLimit);
int moved = queue.drainTo(batch, batchLimit);
```

Đoạn trên cần có kiểu `Event`, hàng đợi và giới hạn hợp lệ trong ứng dụng. `ArrayList` hỗ trợ thêm phần tử nhưng không tự đồng bộ hóa; an toàn ở đây đến từ việc mỗi luồng giữ lô riêng, không phải vì nó nằm cạnh một hàng đợi an toàn luồng. Xem [ArrayList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayList.html).

Cần tránh:

- Đích là chính hàng đợi nguồn: lời gọi ném `IllegalArgumentException`.
- Đích là `null`: ném `NullPointerException`.
- Đích không hỗ trợ thêm phần tử, chẳng hạn một danh sách bất biến.
- Nhiều luồng cùng thay đổi đích trong lúc `drainTo` đang chạy; hợp đồng không xác định hành vi trong trường hợp này.
- Dùng `Set` khi phải giữ mọi lần xuất hiện của sự kiện: đích dạng tập hợp có thể gộp các phần tử bằng nhau theo quy tắc của nó.

Nếu chuyển lô sang một luồng khác để xử lý bất đồng bộ, cần cơ chế bàn giao an toàn và không được `clear()` hoặc tái sử dụng cùng danh sách khi bên nhận còn đang đọc. Có thể tạo bản sao bất biến cho việc bàn giao nếu phù hợp; điều này chỉ bảo vệ cấu trúc danh sách, không tự biến các đối tượng sự kiện bên trong thành bất biến.

Không dùng collection có phương thức thêm thực hiện I/O chậm để biến `drainTo` thành nơi xử lý nghiệp vụ. Hãy chuyển vào một cấu trúc bộ nhớ đơn giản rồi xử lý sau; phương thức thêm chậm hoặc có ngoại lệ sẽ làm quá trình chuyển khó kiểm soát.

## 5. Không coi chuyển lô là giao dịch

Có hai loại lỗi khác nhau cần phân biệt.

### Lỗi ngay trong quá trình chuyển

Nếu việc thêm vào collection đích ném ngoại lệ, hợp đồng `drainTo` cho phép một số phần tử có thể nằm ở nguồn, ở đích, ở cả hai hoặc không còn ở bên nào. Không được suy luận rằng mọi thay đổi sẽ được hoàn tác hoặc chỉ cần gọi lại là chắc chắn đúng.

Chọn collection đích đơn giản làm giảm các nguyên nhân thất bại thông thường, nhưng không tạo bảo đảm giao dịch. Khi dữ liệu quan trọng, cần định danh sự kiện và cơ chế đối soát/khôi phục phù hợp thay vì đặt toàn bộ độ tin cậy vào một lần chuyển bộ nhớ.

### Lỗi sau khi đã nhận lô

Giả sử lấy được `[A, B, C]` rồi ghi dữ liệu:

```text
A: đã ghi thành công
B: lỗi kết nối, chưa biết phía nhận đã ghi hay chưa
C: chưa xử lý
```

Đưa lại cả lô có thể làm A bị xử lý trùng; bỏ cả lô có thể làm mất C. Ngay cả với B, lỗi kết nối không đủ để khẳng định giao dịch phía xa chưa xảy ra.

Thiết kế ứng dụng cần quyết định một trong các chính sách phù hợp: giao dịch theo lô tại hệ thống đích, xác nhận từng phần tử, định danh chống xử lý trùng, ghi nhận phần chưa hoàn tất hoặc hàng đợi bền vững có cơ chế xác nhận. `drainTo` không cung cấp bảo đảm “xử lý đúng một lần”.

Cũng không mặc nhiên đưa lại bằng `put` ngay trong mọi nhánh lỗi. Với hàng đợi có giới hạn dung lượng, bên sản xuất có thể đã lấp đầy chỗ trống sau khi lô được lấy ra; nếu mọi bên tiêu thụ cùng chờ đưa lại thì hệ thống có thể mắc kẹt. Chính sách thử lại cần tính cả sức chứa và khả năng tiếp tục tiến triển.

## 6. Nhiều bên tiêu thụ và kích thước lô

`take()` rồi `drainTo()` là **hai thao tác riêng**, không phải một lần nhận nguyên khối. Trong khoảng giữa chúng, bên tiêu thụ khác có thể lấy phần tử hoặc bên sản xuất có thể thêm dữ liệu.

Vì vậy, `takeBatch` chỉ hứa nhận ít nhất một phần tử khi kết thúc bình thường và không vượt `maxBatchSize`. Nó không hứa rằng một lô sẽ chứa một đoạn liên tiếp của toàn bộ lịch gửi khi nhiều luồng cùng nhận.

Thứ tự phụ thuộc loại hàng đợi: ví dụ FIFO trong chương trình đến từ `ArrayBlockingQueue`; không được áp dụng giả định FIFO cho mọi `BlockingQueue`. Nhiều luồng xử lý các lô cũng có thể hoàn thành khác thứ tự nhận.

Nên dùng giới hạn lô hữu hạn trong vòng xử lý dài:

| Tăng giới hạn lô | Ảnh hưởng cần cân nhắc |
|---|---|
| Có thể giảm số lần gọi hệ thống đích nếu đích hỗ trợ API theo lô | Thông lượng có thể cải thiện |
| Mỗi lô giữ nhiều dữ liệu hơn | Tăng bộ nhớ đang được xử lý ngoài hàng đợi |
| Một luồng nhận nhiều việc hơn | Có thể làm các luồng khác nhận ít việc hoặc tăng thời gian chờ |
| Một lần lỗi ảnh hưởng nhiều phần tử hơn | Khôi phục và theo dõi kết quả phức tạp hơn |

Đo kích thước lô thực tế, thời gian xử lý lô, tuổi công việc và tỉ lệ lỗi. Không có kích thước tối ưu áp dụng cho mọi hệ thống.

Đặc biệt, sức chứa hàng đợi chỉ giới hạn phần đang chờ trong hàng đợi. Nếu có `W` bên tiêu thụ, mỗi bên giữ tối đa `B` công việc, có thể có thêm tới `W × B` công việc đã lấy ra nhưng chưa xong, chưa kể các bộ đệm khác. Nếu tiếp tục đẩy các lô sang một bộ thực thi không giới hạn, hàng đợi đầu vào có giới hạn cũng chưa đủ kiểm soát bộ nhớ toàn hệ thống.

## 7. Khi cần chờ gom lô trong một khoảng thời gian

Có hai chính sách cần gọi tên rõ:

- **Lấy ngay phần sẵn có:** `take()` một phần tử, `drainTo()` phần còn lại như ví dụ.
- **Chờ gom thêm tới một thời hạn:** sau phần tử đầu, dùng `poll(remaining, unit)` cho từng phần tử tiếp theo đến khi đủ số lượng hoặc hết ngân sách.

Chính sách thứ hai tăng cơ hội có lô lớn nhưng tăng độ trễ khi lưu lượng thấp. Cần xác định thời hạn bắt đầu từ lúc gọi hàm hay lúc nhận phần tử đầu. Khi lặp, tính phần thời gian còn lại bằng đồng hồ đo khoảng thời gian như `System.nanoTime()`; không cấp lại toàn bộ thời gian chờ sau mỗi phần tử. `drainTo` tự nó không thực hiện việc chờ gom này.

## 8. Ngắt luồng và dừng bên tiêu thụ

`takeBatch` truyền `InterruptedException` từ `take()` để bên gọi quyết định hủy. `drainTo` không có tham số thời hạn và không khai báo ngoại lệ ngắt; đừng dùng nó như một điểm chắc chắn sẽ phản ứng với mọi yêu cầu ngắt.

Ngắt đến sau khi đã nhận phần tử đầu không tự hoàn tác phần tử đó. Luồng sở hữu lô phải có chính sách hoàn thành, ghi nhận hoặc bàn giao phần đã nhận trước khi dừng. Khi bắt `InterruptedException` tại biên `Runnable`, thường khôi phục cờ ngắt rồi thoát; tránh bắt và tiếp tục chờ vô hạn.

Nếu ứng dụng dùng phần tử đánh dấu kết thúc, `drainTo` có thể lấy cả dấu đó và các phần tử khác trong một lô. Cần thiết kế riêng cách nhận diện dấu, xử lý phần còn lại và phối hợp nhiều bên tiêu thụ; không để một lô lấy hết các dấu dành cho các luồng khác.

## 9. Tự kiểm tra

1. `drainTo(batch, 100)` có đợi đủ 100 phần tử không? — Không.
2. Đích đã có 10 phần tử, chuyển thêm 3 thì giá trị trả về là 3 hay 13? — Là 3.
3. Vì sao sau `take()` chỉ drain tối đa `B - 1`? — Phần tử đầu đã chiếm một vị trí trong lô tối đa B.
4. Hàng đợi rỗng sau khi drain có chứng minh mọi công việc đã thành công không? — Không; công việc có thể đang nằm trong lô chờ xử lý.
5. Việc ghi lô thất bại có tự đưa các phần tử về hàng đợi không? — Không; đó là trách nhiệm của giao thức xử lý và khôi phục.
