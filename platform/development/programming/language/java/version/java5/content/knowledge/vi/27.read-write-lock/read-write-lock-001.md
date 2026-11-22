# Mục đích tách khóa đọc và khóa ghi

## 1. Đọc cùng lúc có thể an toàn, ghi xen vào thì có thể sai

Giả sử một hệ thống giữ bảng cấu hình hoặc danh mục trong bộ nhớ. Nhiều luồng thường chỉ tra cứu, còn cập nhật xảy ra ít hơn. Nếu tất cả thao tác đều dùng cùng một khóa loại trừ, hai luồng chỉ đọc cũng phải chờ nhau dù không bên nào sửa dữ liệu.

`ReadWriteLock` biểu diễn hai chế độ truy cập phối hợp trên cùng một trạng thái: khóa đọc (read lock) cho các thao tác chỉ đọc, và khóa ghi (write lock) cho các thao tác có thay đổi. Nhiều reader có thể giữ khóa đọc cùng lúc khi không có writer; writer cần quyền truy cập độc quyền.

Mục tiêu là giữ tính đúng đắn khi có ghi, đồng thời cho phép những thao tác đọc không xung đột được chồng lấp. Đây không phải cách làm mọi hoạt động chạy song song, cũng không tự bảo đảm nhanh hơn một khóa thông thường.

Bài dùng `ReentrantReadWriteLock` làm triển khai cụ thể, với ví dụ Java 17 trở lên. Cơ chế này vẫn áp dụng trong Java hiện đại.

## 2. Đây là một cặp khóa liên kết, không phải hai khóa độc lập

```java
// Đoạn khai báo trong một lớp.
private final ReadWriteLock rw = new ReentrantReadWriteLock();
private final Lock read = rw.readLock();
private final Lock write = rw.writeLock();
```

`read` và `write` do cùng một đối tượng `rw` tạo, nên chúng biết phối hợp quyền truy cập. Không thay chúng bằng hai `new ReentrantLock()` độc lập: nếu một bên chỉ lấy khóa riêng cho đọc và bên khác chỉ lấy khóa riêng cho ghi, hai bên không loại trừ được nhau.

Với các luồng khác nhau, bảng tương thích cơ bản là:

| Đang có luồng giữ | Luồng khác xin đọc | Luồng khác xin ghi |
| --- | --- | --- |
| Không ai giữ | Có thể được cấp theo chính sách khóa | Có thể được cấp theo chính sách khóa |
| Khóa đọc | Có thể cùng đọc theo chính sách khóa | Phải chờ các reader nhả |
| Khóa ghi | Phải chờ writer nhả | Phải chờ writer nhả |

Chữ “có thể” lưu ý rằng chính sách công bằng và các luồng đã chờ cũng có thể ảnh hưởng việc cấp. Không suy rằng một reader mới luôn được chen vào chỉ vì đang có reader khác.

Hợp đồng cặp khóa và công bố dữ liệu từ ghi sang đọc được định nghĩa trong [ReadWriteLock — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReadWriteLock.html).

## 3. Thế nào là đọc, thế nào là ghi?

Phân loại theo tác động thật lên trạng thái dùng chung, không chỉ theo tên phương thức:

| Thao tác | Chế độ thường cần | Lý do |
| --- | --- | --- |
| Tra một mục mà không sửa dữ liệu | Đọc | Có thể cùng tồn tại với các reader khác |
| Tính tổng vài trường liên quan, không sửa | Đọc trong suốt lần lấy dữ liệu cần nhất quán | Không để writer chen giữa các trường |
| Thêm/xóa mục hoặc đổi cấu hình | Ghi | Làm thay đổi dữ liệu mà reader đang dùng |
| `get` nhưng tự cập nhật thống kê/cache dùng chung | Có yếu tố ghi, phải thiết kế đồng bộ tương ứng | Tên `get` không làm tác động sửa trở thành chỉ đọc |
| Đọc điều kiện rồi quyết định trừ kho/cập nhật | Ghi cho cả quy tắc kiểm tra–thay đổi | Phải tránh bên khác thay trạng thái giữa hai bước |

Khóa đọc không tự cấm Java thực hiện phép gán. Nếu hai luồng cùng lấy read lock rồi tăng một biến dùng chung, cả hai vẫn có thể cùng sửa và gây tranh chấp. Nó là quyền đọc trong giao thức của ứng dụng, không phải bộ kiểm tra tính bất biến của mọi câu lệnh.

Nếu một thống kê được bảo vệ bằng công cụ nguyên tử riêng, cần mô tả rõ nó không thuộc cùng ràng buộc dữ liệu; không ngầm cho rằng read lock đã bảo vệ một phép ghi như vậy.

## 4. Bảo vệ một trạng thái gồm nhiều trường

Xét kho có `available` và `reserved`, với tổng luôn bằng 10. Một lần đặt giữ 3 đơn vị phải giảm `available` và tăng `reserved` như một thay đổi được bảo vệ.

Writer giữ khóa ghi trong cả hai phép cập nhật. Reader giữ khóa đọc trong cả hai phép đọc để không nhìn thấy một trường đã đổi còn trường kia chưa đổi. Sau đó có thể trả một đối tượng bất biến chứa kết quả, thay vì làm lộ dữ liệu mutable nội bộ.

```text
Trước: available=10, reserved=0
Writer giữ write lock:
    available = 7
    reserved  = 3
Writer nhả write lock.
Reader lấy read lock và đọc: available=7, reserved=3
```

Không tách lần đọc thành hai phương thức tự lấy/nhả khóa riêng rồi cộng kết quả ở bên ngoài nếu cần một trạng thái thống nhất. Writer có thể cập nhật giữa hai lời gọi.

Lần nhả khóa ghi và lần lấy khóa đọc sau đó còn phối hợp việc nhìn thấy dữ liệu theo mô hình bộ nhớ. Chỉ bảo vệ writer mà để reader đọc trực tiếp ngoài giao thức không đạt cùng bảo đảm.

## 5. Chương trình chạy đầy đủ

Ví dụ gồm lớp kho nhỏ có phương thức chụp hai trường và phương thức đặt giữ. Phần `main` cố ý kiểm tra cặp khóa bằng cách giữ một read lock trong lúc cho luồng khác đọc và thử ghi.

Lưu thành `ReadWritePurposeDemo.java`:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ReadWritePurposeDemo {
    record Snapshot(int available, int reserved) {}

    static final class Inventory {
        private final ReentrantReadWriteLock lock =
                new ReentrantReadWriteLock();
        private final Lock read = lock.readLock();
        private final Lock write = lock.writeLock();
        private int available = 10;
        private int reserved;

        Snapshot snapshot() {
            read.lock();
            try {
                return new Snapshot(available, reserved);
            } finally {
                read.unlock();
            }
        }

        void reserve(int amount) {
            write.lock();
            try {
                if (amount < 0 || amount > available) {
                    throw new IllegalArgumentException("Invalid amount");
                }
                available -= amount;
                reserved += amount;
            } finally {
                write.unlock();
            }
        }
    }

    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected lock result");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Inventory inventory = new Inventory();
        AtomicBoolean secondReaderEntered = new AtomicBoolean(false);
        AtomicBoolean writerEntered = new AtomicBoolean(true);

        inventory.read.lock();
        try {
            Thread reader = new Thread(() -> {
                Snapshot value = inventory.snapshot();
                check(value.available() + value.reserved() == 10);
                secondReaderEntered.set(true);
            }, "reader");
            reader.start();
            reader.join();

            Thread writer = new Thread(() -> {
                boolean acquired = inventory.write.tryLock();
                writerEntered.set(acquired);
                if (acquired) {
                    inventory.write.unlock();
                }
            }, "writer");
            writer.start();
            writer.join();

            check(secondReaderEntered.get());
            check(!writerEntered.get());
            System.out.println("another reader entered: "
                    + secondReaderEntered.get());
            System.out.println("writer entered while read held: "
                    + writerEntered.get());
        } finally {
            inventory.read.unlock();
        }

        inventory.reserve(3);
        Snapshot current = inventory.snapshot();
        check(current.equals(new Snapshot(7, 3)));
        System.out.println("after reserve: " + current);
        System.out.println("total: " + (current.available() + current.reserved()));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ReadWritePurposeDemo.java
java ReadWritePurposeDemo
```

Stdout:

```text
another reader entered: true
writer entered while read held: false
after reserve: Snapshot[available=7, reserved=3]
total: 10
```

Trong phép thử đầu, main đang giữ read lock và chưa có writer nào chờ, nên reader khác vẫn có thể vào `snapshot()` rồi kết thúc. Điều đó cho thấy khóa đọc được chia sẻ giữa nhiều luồng.

Writer trong phép thử dùng `tryLock()` một lần, không chờ, nên trả `false` khi main còn giữ read lock. `join()` ở vị trí này chỉ hợp lệ cho cấu trúc kiểm tra đã chọn. Nếu đổi writer thành một lần lấy khóa ghi chặn rồi vẫn để main giữ read lock và đợi writer, hai bên có thể chờ nhau mãi.

Sau khi main nhả read lock, `reserve(3)` có thể lấy write lock và thay cả hai trường. Phương thức `snapshot()` tạo một `record` chứa hai số nguyên đã được đọc dưới cùng read lock; bên gọi dùng kết quả ấy sau khi nhả khóa mà không sửa được các trường của record.

Việc `main` truy cập trường khóa private của lớp lồng là để thử cơ chế trong một tệp ví dụ. API sử dụng của kho vẫn là `snapshot` và `reserve`; ứng dụng thông thường nên giấu giao thức khóa trong lớp sở hữu dữ liệu.

## 6. Khi tách đọc/ghi có thể có lợi

Tách khóa có tiềm năng giúp ích khi nhiều reader thật sự tranh truy cập cùng lúc, phần đọc đủ đáng kể để lợi ích chồng lấp vượt chi phí quản lý khóa, và phần ghi không chiếm phần lớn thời gian.

Ví dụ một danh mục lớn đã nạp sẵn, được nhiều luồng tìm kiếm và chỉ cập nhật theo đợt có thể phù hợp để đánh giá. Nhưng chỉ nói “đọc nhiều hơn ghi” chưa đủ. Cần xét thời gian giữ khóa, số luồng, kích thước dữ liệu và tài nguyên máy.

Với một phép đọc vài nanosecond hoặc mức tranh chấp thấp, chi phí lấy/nhả read lock có thể lớn hơn lợi ích. Nếu ghi thường xuyên hoặc writer giữ khóa quá lâu, các reader vẫn phải chờ và phần chia sẻ không còn nhiều giá trị.

Đừng giữ read lock xuyên qua gọi mạng hoặc callback không kiểm soát chỉ vì nó cho phép nhiều reader. Writer vẫn phải đợi tất cả những reader ấy nhả, nên độ trễ cập nhật có thể tăng mạnh. Nên lấy dữ liệu cần thiết thành một kết quả an toàn rồi xử lý bên ngoài khi ngữ nghĩa cho phép.

Chỉ số cần đo gồm thông lượng, độ trễ đọc, độ trễ ghi, thời gian giữ khóa và những trường hợp chờ cao. Ví dụ cơ chế ở trên không phải benchmark và không chứng minh lựa chọn này nhanh hơn `ReentrantLock` hay `synchronized`.

## 7. Những điều cặp khóa không tự giải quyết

### Không làm đối tượng trả về tự bất biến

Nếu một getter trả trực tiếp tham chiếu tới map/list hoặc đối tượng mutable nội bộ rồi nhả khóa, bên gọi có thể sử dụng hoặc sửa nó ngoài vùng được bảo vệ. Trả một bản sao phù hợp, giá trị bất biến hoặc API truy cập rõ ràng giúp giữ ranh giới bảo vệ.

`record` chỉ bất biến ở mức các trường tham chiếu không được gán lại. Nếu record chứa một list mutable, vẫn phải quyết định cách bảo vệ/sao chép list đó; ví dụ dùng hai `int` để không có vấn đề này.

### Không làm chuỗi đọc rồi ghi trở thành một giao dịch

Nếu đọc dưới read lock, nhả, rồi mới lấy write lock, trạng thái có thể đổi trong khoảng trống. Bên ghi phải kiểm tra lại điều kiện cần thiết sau khi có quyền ghi.

Với `ReentrantReadWriteLock`, không giữ read lock rồi chờ trực tiếp write lock để mong nâng cấp tự động. Khóa ghi cần các reader nhả, kể cả quyền đọc của chính luồng đó; kiểu nâng cấp này không được hỗ trợ. Đây là một điểm phải biết trước khi đưa quyết định ghi vào một phương thức đọc.

### Không bảo đảm công bằng cho mọi tải

Triển khai cụ thể quyết định chính sách cấp đọc/ghi. `ReentrantReadWriteLock` có chế độ công bằng tùy chọn; mặc định không quy định thứ tự phục vụ chắc chắn và có thể làm một số luồng chờ lâu trong tranh chấp liên tục. Công bằng cũng không bảo đảm lịch chạy của hệ điều hành hoặc thứ tự hoàn tất công việc.

Các đặc điểm tái nhập, chính sách và giới hạn chuyển chế độ nằm trong [ReentrantReadWriteLock — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html).

## 8. Chọn so với những cách tổ chức khác

| Nhu cầu | Hướng có thể cân nhắc |
| --- | --- |
| Dữ liệu chỉ có một luồng sử dụng | Quyền sở hữu riêng, không thêm khóa chỉ vì dự đoán |
| Vùng tới hạn đơn giản, mức tranh chấp thấp | `synchronized` hoặc một khóa loại trừ |
| Nhiều thao tác chỉ đọc dài vừa đủ trên trạng thái chung, ghi ít | Đánh giá `ReadWriteLock` |
| Các mục map độc lập và muốn nhiều cập nhật theo khóa | Concurrent collection với thao tác nguyên tử phù hợp |
| Cấu hình thay theo phiên bản hoàn chỉnh | Công bố một trạng thái bất biến để reader giữ phiên bản |

Concurrent collection không tự tạo ảnh chụp nhất quán của nhiều mục, còn read/write lock không tự có mọi đặc tính của một map đồng thời. Lựa chọn phải theo yêu cầu dữ liệu và thao tác, rồi mới đánh giá chi phí.

## 9. Nguyên tắc áp dụng

Xác định rõ vùng dữ liệu được bảo vệ và những bất biến cần giữ. Phân loại các đường truy cập thật sự chỉ đọc với các đường có ghi, dùng cùng một cặp lock, và ghép mỗi lần lấy thành công với `finally` nhả đúng khóa.

Giữ toàn bộ lần đọc cần nhất quán trong cùng một phạm vi read lock; giữ toàn bộ quy tắc kiểm tra–cập nhật trong phạm vi write lock. Không làm lộ tham chiếu mutable khiến bên ngoài bỏ qua giao thức. Sau đó đo xem khả năng chồng lấp đọc có đem lại lợi ích với tải thực tế hay không.

## 10. Tự kiểm tra

1. Có hai reader đang giữ read lock; writer có được sửa ngay không? Không; nó phải lấy được quyền ghi độc quyền.
2. Hai `ReentrantLock` độc lập, một cho đọc và một cho ghi, có thay thế cặp ReadWriteLock không? Không.
3. Một phương thức tên `get` nhưng sửa cache nội bộ có chắc được gọi chỉ dưới read lock không? Không; phải xét phần ghi thực tế.
4. ReadWriteLock có bảo đảm luôn nhanh hơn một khóa loại trừ không? Không; phải đo theo tải.
5. Nhả read lock rồi lấy write lock có giữ nguyên kết quả quan sát trước đó không? Không; cần kiểm tra lại.
6. Trả đối tượng mutable nội bộ sau khi nhả read lock có khiến mọi lần dùng tiếp tự an toàn không? Không.
