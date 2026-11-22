# Tài liệu hóa dữ liệu và điều kiện được từng khóa bảo vệ

## 1. Tài liệu về khóa phải trả lời “bảo vệ cái gì?”

Một khai báo `private final ReentrantLock lock` chưa cho người đọc biết trạng thái nào phải truy cập dưới khóa đó. Nếu không có hợp đồng rõ ràng, một phương thức mới có thể dùng khóa khác, một getter có thể đọc tự do, hoặc một condition có thể được báo ở sai nơi.

Tài liệu hóa khóa là mô tả giao thức mà mọi bên truy cập trạng thái phải tuân theo. Tối thiểu, người đọc cần tìm được:

1. Khóa cụ thể và phạm vi dữ liệu do nó bảo vệ.
2. Những quan hệ phải luôn đúng giữa các trường khi rời vùng tới hạn.
3. Biểu thức điều kiện mà mỗi nhóm luồng đang chờ.
4. Phương thức nào thay đổi điều kiện và phải báo cho nhóm nào.
5. Quy tắc lấy nhiều khóa, nếu có.
6. Chính sách khi bị ngắt, hết thời gian hoặc đóng đối tượng.

Tài liệu không thay thế khóa. Nó giúp người viết và người rà soát kiểm tra mã có thực hiện cùng một giao thức hay không.

Ví dụ một bộ quản lý tài nguyên có `available`, `reserved`, `closed`. Viết “thread-safe” ở đầu lớp là quá ít. Cần biết `available + reserved == capacity` được bảo vệ chung, việc đọc số liệu phải tạo một trạng thái nhất quán và đóng đối tượng có ảnh hưởng gì đến các bên đang chờ.

## 2. Ghi danh tính khóa, không chỉ ghi tên chung chung

Một mô tả có thể kiểm tra được:

```text
stateLock bảo vệ:
- available: số đơn vị còn có thể đặt giữ
- reserved: số đơn vị đang được đặt giữ
- closed: có còn nhận đặt giữ mới hay không
- mọi lần đọc/ghi ba trường, kể cả kiểm tra trước khi chờ
```

Các điểm cần ghi rõ thêm:

- `stateLock` là một trường ổn định, dùng chung cho toàn bộ vòng đời đối tượng.
- Nếu dùng monitor, nói rõ là `this`, một đối tượng khóa riêng hay monitor của lớp cho trạng thái tĩnh.
- Nếu dùng `ReentrantLock`, các bên dùng phương thức của khóa; `synchronized(stateLock)` là monitor khác, không thay thế giao thức ấy.
- Không có phương thức công khai trả khóa ra ngoài để mã tùy ý giữ nó.

[Hợp đồng Java SE `Lock`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html) nêu cả nghĩa đồng bộ bộ nhớ lẫn sự khác biệt giữa monitor của đối tượng khóa và các phương thức lấy khóa. Tài liệu của lớp ứng dụng phải chỉ ra nó chọn cơ chế nào.

Không tạo khóa mới trong từng lần gọi rồi vẫn chú thích “được bảo vệ bởi lock”: các luồng đang có những đối tượng khóa khác nhau nên không loại trừ nhau.

## 3. Ghi quan hệ bất biến và ranh giới phải khôi phục

Một bất biến (invariant) là quan hệ mà lớp phải giữ đúng ở những điểm đã cam kết. Với ví dụ kho tài nguyên:

```text
capacity > 0, không đổi sau khởi tạo
0 <= available <= capacity
0 <= reserved <= capacity
available + reserved == capacity
```

Các trường có liên quan cần được cập nhật trong cùng vùng tới hạn. Khi đặt giữ `n` đơn vị, giảm `available` và tăng `reserved` trước khi nhả khóa. Khi trả `n` đơn vị, làm ngược lại.

Tài liệu nên nói bất biến phải đúng trước khi nhả khóa và tại các điểm có thể chờ bằng condition. `await` tạm nhả khóa, nên không được gọi khi trạng thái còn đang cập nhật dở và bất biến bị phá vỡ.

Ví dụ cách đặt comment:

```java
// stateLock bảo vệ available và reserved.
// Trước khi nhả khóa: available + reserved == capacity.
private int available;
private int reserved;
```

Đây là khai báo minh họa để đặt trong một lớp có các trường liên quan. Comment chỉ rõ trách nhiệm; compiler không tự kiểm tra bất biến từ dòng chữ này.

Không chỉ mô tả riêng từng trường mà bỏ quan hệ giữa chúng. Hai trường nguyên tử độc lập không tự làm phép chuyển giữa chúng trở thành nguyên tử đối với người đọc cần cả hai giá trị.

## 4. Lập bảng condition từ biểu thức trạng thái

Tên `changed` hoặc `notEmpty` có thể gợi ý nhưng không đủ thay biểu thức cụ thể.

Với việc đặt giữ `amount` đơn vị, có thể ghi:

| Thành phần | Hợp đồng của ví dụ |
| --- | --- |
| Khóa liên quan | `stateLock` |
| Condition | `availabilityChanged`, được tạo từ `stateLock` |
| Khi còn phải chờ | `available < amount && !closed` |
| Khi có thể thành công | `!closed && available >= amount` |
| Khi phải từ chối do đóng | `closed == true` |
| Ai làm có thêm tài nguyên | `release(amount)` |
| Ai thay đổi đường thoát chờ | `close()` |
| Nơi phát tín hiệu | Trong hai phương thức đó, khi đang giữ `stateLock` |
| Cách báo | `signalAll`, vì mỗi bên có thể yêu cầu số lượng khác nhau; đóng cần đánh thức mọi bên |

Ở đây `amount` là tham số của từng lời gọi, không phải một trường chung được condition tự lưu. Mỗi luồng kiểm tra yêu cầu riêng sau khi lấy lại khóa.

Ví dụ nếu một bên chờ 5 đơn vị còn bên khác chờ 1, việc có thêm 1 đơn vị không giúp bên đầu tiến triển. Nếu chỉ chọn ngẫu nhiên một bên không phù hợp và không còn cập nhật nào khác, bên có thể tiến triển có thể vẫn ngủ. Việc chọn `signalAll` cần được giải thích từ các điều kiện khác nhau ấy, không phải theo thói quen.

Theo [Java SE `Condition`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/concurrent/locks/Condition.html), chờ gắn với khóa và phải kiểm tra lại biểu thức trong vòng lặp. Condition không tự hiểu hoặc giữ hộ biểu thức nghiệp vụ của ứng dụng.

## 5. Ví dụ Java 17+: hợp đồng đồng bộ đặt ngay cạnh mã

Lưu thành `LockContractDemo.java`. Mô hình chỉ đếm tài nguyên chung, chưa theo dõi chủ sở hữu từng lần đặt giữ. Vì thế `release` kiểm tra tổng đang giữ, không chứng minh bên gọi là chủ của một yêu cầu cụ thể.

```java
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class LockContractDemo {
    record Snapshot(int available, int reserved, boolean closed) {}

    static final class ResourcePool {
        private final int capacity;
        private final ReentrantLock stateLock = new ReentrantLock();
        private final Condition availabilityChanged = stateLock.newCondition();

        // stateLock bảo vệ mọi lần đọc/ghi các trường bên dưới.
        // Bất biến trước khi nhả khóa hoặc await:
        // 0 <= available, 0 <= reserved, available + reserved == capacity.
        private int available;
        private int reserved;
        private boolean closed;

        ResourcePool(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
            this.available = capacity;
        }

        // Tự lấy khóa. Chờ khi thiếu tài nguyên và chưa đóng.
        // Đóng: trả false. Ngắt: truyền InterruptedException, chưa đặt giữ.
        boolean reserve(int amount) throws InterruptedException {
            checkAmount(amount);
            stateLock.lockInterruptibly();
            try {
                while (available < amount && !closed) {
                    availabilityChanged.await();
                }
                if (closed) {
                    return false;
                }
                available -= amount;
                reserved += amount;
                return true;
            } finally {
                stateLock.unlock();
            }
        }

        // Cho phép trả cả sau khi đóng; báo mọi bên có yêu cầu khác nhau.
        void release(int amount) {
            checkAmount(amount);
            stateLock.lock();
            try {
                if (amount > reserved) {
                    throw new IllegalArgumentException("exceeds reserved amount");
                }
                reserved -= amount;
                available += amount;
                availabilityChanged.signalAll();
            } finally {
                stateLock.unlock();
            }
        }

        // Đóng chỉ ngừng đặt giữ mới, không thu hồi phần đã đặt giữ.
        void close() {
            stateLock.lock();
            try {
                closed = true;
                availabilityChanged.signalAll();
            } finally {
                stateLock.unlock();
            }
        }

        // Trả ảnh chụp giá trị, không lộ trạng thái có thể sửa của lớp.
        Snapshot snapshot() {
            stateLock.lock();
            try {
                return snapshotUnderLock();
            } finally {
                stateLock.unlock();
            }
        }

        // Yêu cầu bên gọi đã giữ stateLock; không tự lấy/nhả khóa.
        private Snapshot snapshotUnderLock() {
            if (!stateLock.isHeldByCurrentThread()) {
                throw new IllegalStateException("stateLock must be held");
            }
            return new Snapshot(available, reserved, closed);
        }

        // Chỉ đọc capacity bất biến, không cần đọc trạng thái dưới khóa.
        private void checkAmount(int amount) {
            if (amount <= 0 || amount > capacity) {
                throw new IllegalArgumentException("invalid amount");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ResourcePool pool = new ResourcePool(5);
        pool.reserve(3);
        System.out.println("initial: " + pool.snapshot());

        FutureTask<Boolean> request = new FutureTask<>(() -> pool.reserve(4));
        Thread requester = new Thread(request, "requester");
        requester.start();
        try {
            pool.release(2);
            System.out.println("second reservation: "
                    + request.get(5, TimeUnit.SECONDS));
            System.out.println("after reservation: " + pool.snapshot());

            pool.close();
            System.out.println("reserve after close: " + pool.reserve(1));
            pool.release(5);
            System.out.println("final: " + pool.snapshot());
        } finally {
            request.cancel(true);
            requester.join(1_000);
            if (requester.isAlive()) {
                throw new IllegalStateException("requester did not stop");
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 LockContractDemo.java
java LockContractDemo
```

Stdout khi tác vụ hoàn tất trong thời hạn kiểm tra:

```text
initial: Snapshot[available=2, reserved=3, closed=false]
second reservation: true
after reservation: Snapshot[available=0, reserved=5, closed=false]
reserve after close: false
final: Snapshot[available=5, reserved=0, closed=true]
```

Những gì ví dụ kiểm chứng và những gì cần đọc từ mã:

- Sau khi trả 2 đơn vị, có đủ để đặt giữ thêm 4. Luồng phụ có thể đã chờ hoặc được lập lịch sau lúc trả; stdout không khẳng định nó chắc chắn từng ngủ trong `await`.
- Dù hai bước đó chạy theo thứ tự nào, kiểm tra trạng thái dưới cùng khóa giúp lời đặt giữ không bỏ lỡ điều kiện đã đúng trước khi bắt đầu chờ.
- Sau `Future.get`, yêu cầu đã hoàn tất trước khi chụp trạng thái. Ba trường của mỗi `Snapshot` được đọc trong cùng một vùng khóa.
- Đóng không trả các tài nguyên đang giữ; việc trả vẫn hợp lệ sau đóng. Hai điểm này được ghi thành chính sách, không để người dùng tự suy ra từ tên phương thức.
- Trường `capacity` bất biến được kiểm tra riêng trước khóa; kiểm tra `reserved` phụ thuộc trạng thái hiện tại nên nằm trong khóa.

Đây là ví dụ về hợp đồng và cách tổ chức mã, không phải một cơ chế cấp tài nguyên đầy đủ theo người dùng hoặc một kiểm chứng mọi lịch chạy có thể xảy ra.

## 6. Phân biệt phương thức tự lấy khóa với phương thức đòi hỏi đã giữ khóa

Một quy ước hữu ích là đặt hậu tố như `UnderLock` cho helper chỉ được gọi khi đã giữ khóa, rồi ghi rõ:

```text
snapshot(): tự lấy/nhả stateLock
snapshotUnderLock(): yêu cầu bên gọi đang giữ stateLock, không tự nhả
checkAmount(): chỉ dùng dữ liệu bất biến, không đọc trạng thái được khóa bảo vệ
```

Điều này giúp tránh một helper âm thầm nhả khóa của bên gọi hoặc được gọi từ nơi chưa có quyền truy cập trạng thái.

`isHeldByCurrentThread()` trong ví dụ kiểm tra quyền sở hữu của luồng hiện tại, phù hợp để phát hiện dùng sai helper. [Java SE `ReentrantLock`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html#isHeldByCurrentThread()) mô tả phương thức kiểm tra này.

Kiểm tra đó không tự lấy khóa và không thay thế hợp đồng. `isLocked()` chỉ cho biết khóa có thể đang do một luồng nào đó giữ, không chứng minh chính bên gọi đang được phép truy cập.

Có thể dùng `assert` cho kiểm tra nội bộ theo chính sách dự án, nhưng assertion có thể bị tắt khi chạy. Không đặt một hành vi cần thiết để chương trình đúng chỉ vào phần biểu thức `assert`.

## 7. Ghi rõ đường đọc và cách trả dữ liệu

Chú thích “writes guarded by lock” nhưng để getter đọc tự do thường làm hợp đồng thiếu một nửa. Nếu trường cần khóa để bảo vệ hiển thị bộ nhớ hoặc quan hệ nhiều trường, ghi rõ cả đọc lẫn ghi.

Một đối tượng kết quả bất biến như `Snapshot` có thể giúp bên ngoài dùng dữ liệu mà không cần giữ khóa nội bộ của lớp. Nhưng phải hiểu phạm vi: ảnh chụp đúng lúc tạo, không cam kết số liệu giữ nguyên đến khi bên gọi thực hiện hành động tiếp theo.

Không trả trực tiếp một danh sách nội bộ có thể sửa rồi nghĩ khóa của getter sẽ bảo vệ mọi lần dùng sau đó. Khi phương thức đã nhả khóa, bên nhận vẫn còn tham chiếu và có thể sửa ngoài giao thức. Nếu cần bản sao, hãy nói đó là bản sao cấu trúc hay sao chép sâu phần tử.

Nếu dùng `volatile`, kiểu nguyên tử hoặc dữ liệu bất biến bên cạnh khóa, tài liệu cần nêu phạm vi của từng cơ chế. Không dùng hai cơ chế rời rạc để đọc/ghi cùng quan hệ nhiều trường rồi mặc định chúng tạo thành một giao thức chung.

## 8. Khi có nhiều khóa, thêm thứ tự và phạm vi trạng thái chung

Một bảng phân công có thể là:

| Khóa | Trạng thái | Quy tắc phối hợp |
| --- | --- | --- |
| `stateLock` | tồn tài nguyên, yêu cầu đang giữ, trạng thái đóng | Mọi lần đọc/ghi theo khóa này |
| `listenerLock` | danh sách bên nhận thông báo | Không gọi callback khi còn giữ khóa này |
| Cần cả hai | một bước cập nhật thật sự liên quan cả hai nhóm | Quy định một thứ tự thống nhất, chẳng hạn `stateLock` trước `listenerLock`, nếu thiết kế cần giữ đồng thời |

Đây là ví dụ tài liệu thiết kế, không khuyến nghị thêm khóa thứ hai vào chương trình trên. Chỉ chia khóa khi có nhu cầu và có lập luận về các quan hệ giữa nhóm dữ liệu.

Nếu một bất biến trải qua hai nhóm, phải giải thích cách giữ nó đúng. Không đơn giản chia từng trường sang một khóa khác để “giảm tranh chấp” rồi bỏ mất cập nhật chung.

Ngoài thứ tự lấy, ghi rõ:

- Những lời gọi bên ngoài hoặc I/O không được thực hiện khi giữ khóa.
- Có được gọi lại đối tượng từ callback hay không.
- Khi `await` nhả một khóa, còn khóa khác nào đang giữ và có thể chặn bên tạo điều kiện không.
- Các đường thất bại, ngắt hoặc timeout nhả những khóa nào.

Quy tắc thứ tự chỉ hữu ích khi mọi đường mã thật sự tuân theo. Viết “không deadlock” không có giá trị kiểm tra bằng một thứ tự cụ thể và một danh sách đường lấy khóa.

## 9. Chú thích, annotation và công cụ không có cùng vai trò

Có dự án dùng annotation kiểu `@GuardedBy`, nhưng cần biết annotation đến từ thư viện hoặc bộ công cụ nào và công cụ kiểm tra có thật sự được chạy hay không. Không có một annotation như vậy tự động khiến mọi trường được khóa ở runtime.

Với bài học Java độc lập, comment rõ nghĩa là đủ để trình bày hợp đồng mà không thêm phụ thuộc tùy ý. Nếu dự án đã có chuẩn annotation và kiểm tra tĩnh, dùng theo chuẩn ấy và kiểm tra cấu hình thay vì chỉ thêm một tên annotation để trông có bảo đảm hơn.

Các cấp kiểm tra nên bổ sung nhau:

- Tài liệu mô tả ý định và phạm vi bảo vệ.
- Mã lấy/nhả khóa thực hiện giao thức.
- Kiểm tra nội bộ bắt một số đường dùng sai.
- Kiểm thử và công cụ phân tích tìm lỗi trong phạm vi chúng hỗ trợ.

Một lần kiểm thử chạy thành công không chứng minh không có lỗi tranh chấp. Ngược lại, tài liệu đẹp nhưng getter bỏ khóa vẫn là một lỗi cần sửa ở mã.

## 10. Cập nhật tài liệu cùng thay đổi hành vi

Khi thêm một trường, thay một điều kiện chờ hoặc bổ sung phương thức đóng, phải xem lại bảng bảo vệ. Những thay đổi hay làm hợp đồng cũ sai gồm:

- Thêm một getter nhưng không lấy khóa.
- Chuyển biến từ “chỉ một luồng dùng” sang dùng chung.
- Thêm trạng thái lỗi làm một vòng chờ cần thoát thêm điều kiện.
- Đổi từ yêu cầu đồng nhất sang mỗi bên chờ một số lượng khác nhau, khiến chính sách báo cần xem lại.
- Trả tham chiếu nội bộ thay vì ảnh chụp.
- Gọi helper dưới khóa từ một đường mới không giữ khóa.

Giữ tài liệu ngắn nhưng cụ thể ngay cạnh khai báo và phương thức. Với thuật toán nhiều khóa, có thể có một mô tả cấp lớp rồi dẫn người đọc đến các bất biến cục bộ; tránh sao chép cùng hợp đồng vào quá nhiều nơi dễ lệch nhau.

## 11. Tự kiểm tra khi đọc một lớp dùng khóa

1. Có thể chỉ ra chính xác khóa bảo vệ từng trường được sửa dùng chung không?
2. Getter có tuân theo cùng giao thức như setter không?
3. Bất biến nhiều trường có được khôi phục trước `unlock` và trước `await` không?
4. Với mỗi condition, có biểu thức chờ, bên thay đổi nó và nơi phát tín hiệu không?
5. Helper yêu cầu giữ khóa có được phân biệt với phương thức tự lấy khóa không?
6. Người đọc biết rõ việc đóng, ngắt và timeout có làm thay đổi trạng thái hay không không?
7. Dữ liệu trả ra có cho bên ngoài sửa trạng thái nội bộ ngoài giao thức không?
8. Nếu có nhiều khóa, thứ tự lấy và những lời gọi bị cấm khi giữ khóa đã cụ thể chưa?

Nếu phải đoán các câu trả lời từ tên biến hoặc từ một chữ “thread-safe”, tài liệu chưa đủ để bảo trì giao thức đồng thời một cách tin cậy.
