# Vai trò của AbstractQueuedSynchronizer trong công cụ đồng bộ

## Từ bài toán phối hợp luồng đến AQS

Khi nhiều luồng cùng cần một tài nguyên hoặc cùng chờ một điều kiện, công cụ đồng bộ phải trả lời hai câu hỏi: **luồng nào được đi tiếp** và **luồng chưa được đi tiếp sẽ chờ như thế nào**. Ví dụ, một cửa khởi động chỉ mở sau khi dữ liệu cấu hình sẵn sàng: trước thời điểm đó mọi tác vụ phải chờ; sau đó tất cả đều được chạy.

`AbstractQueuedSynchronizer` (AQS), thuộc `java.util.concurrent.locks`, là nền tảng để người viết thư viện xây dựng những công cụ như vậy. Lớp con định nghĩa quy tắc dựa trên trạng thái; AQS cung cấp cơ chế hàng đợi và chờ. Người viết ứng dụng thường dùng công cụ có sẵn như `ReentrantLock`, `Semaphore`, `CountDownLatch`; chỉ cần tự mở rộng AQS khi có một giao thức đồng bộ riêng thực sự cần thiết. Đây vẫn là API được duy trì trong Java hiện đại. [API AQS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

Để đọc bài, cần phân biệt ba ý:

- **Trạng thái đồng bộ**: thông tin quyết định một yêu cầu có được chấp nhận hay không.
- **Giành quyền / giải phóng** (*acquire / release*): các thao tác thử thay đổi hoặc kiểm tra trạng thái theo giao thức của công cụ.
- **Chờ và đánh thức**: cách một luồng nhường CPU khi chưa thể đi tiếp và thử lại khi có khả năng thành công.

Chữ `release` không nhất thiết có nghĩa là trả một ổ khóa. Với cửa khởi động, nó có thể mang nghĩa mở cửa vĩnh viễn; với bộ đếm hoàn thành, nó có thể mang nghĩa giảm số công việc còn thiếu.

## Vì sao cần tách quy tắc khỏi cơ chế chờ?

Giả sử tự viết cửa khởi động. Một biến boolean trả lời được câu hỏi cửa đã mở chưa, nhưng vẫn còn nhiều tình huống: luồng kiểm tra thấy cửa đóng rồi chuẩn bị ngủ đúng lúc luồng khác mở cửa; một luồng đang chờ bị ngắt; nhiều luồng thức cùng lúc; một lần thức dậy xảy ra dù điều kiện chưa đổi.

Giải quyết riêng từng tình huống trong mọi loại công cụ sẽ tạo ra nhiều mã khó kiểm chứng. AQS cho phép người thiết kế tập trung vào quy tắc nhỏ, còn phần tổ chức chờ được dùng chung. Đây là lợi ích về cách tổ chức và tính đúng đắn; không phải cam kết rằng mọi công cụ tự viết bằng AQS đều nhanh hoặc an toàn.

```text
Mã ứng dụng
    -> API công cụ: lock(), await(), acquire() ...
        -> lớp Sync nội bộ: quy tắc trạng thái
            -> AQS: tổ chức chờ và thử lại
                -> LockSupport: park / unpark
```

Không nên đặt logic nghiệp vụ như truy vấn cơ sở dữ liệu, gọi mạng hay xử lý đơn hàng vào các phương thức thử giành quyền. Những phương thức này có thể được gọi nhiều lần trong quá trình cạnh tranh.

## Trạng thái có ý nghĩa do công cụ quyết định

AQS có một trạng thái `int`, được thao tác qua `getState()`, `setState(int)` và `compareAndSetState(expected, update)`. CAS là phép so sánh rồi cập nhật nguyên tử: việc cập nhật chỉ thành công nếu giá trị hiện tại khớp giá trị dự kiến. `getState()` và `setState()` có ngữ nghĩa đọc/ghi `volatile`; nhiều thao tác riêng lẻ không tự biến thành một giao dịch nguyên tử. [Hợp đồng các phương thức trạng thái](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

Ví dụ, trong thiết kế cửa một lần của bài này:

| Trạng thái | Ý nghĩa | Thao tác được phép |
| --- | --- | --- |
| `0` | Cửa đóng | `await()` chưa được đi tiếp; `open()` chuyển sang `1` |
| `1` | Cửa mở | Mọi `await()` được đi tiếp; `open()` tiếp theo không đổi gì |

Điều kiện bất biến là trạng thái chỉ chuyển `0 -> 1`, không có thao tác đóng lại. Vì vậy việc kiểm tra cửa mở không cần lấy độc quyền và không tiêu thụ một lượt vào cửa.

Các công cụ khác có hợp đồng khác:

- `ReentrantLock` cho phép chính luồng đang giữ khóa lấy lại khóa; số lần giữ phải được nhả tương ứng. Luồng khác phải chờ đến khi khóa được nhả hết. Đây là hành vi của khóa có khả năng tái nhập. [ReentrantLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
- `Semaphore` biểu diễn số giấy phép còn sẵn; lấy giấy phép làm giảm khả năng cấp tiếp, trả giấy phép làm tăng khả năng đó. Nó không có khái niệm chủ sở hữu như khóa: một luồng khác có thể trả giấy phép. [Semaphore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Semaphore.html)
- `CountDownLatch` cho các luồng chờ đến khi bộ đếm về `0`. Sau thời điểm đó cửa chờ luôn mở; công cụ này không đặt lại bộ đếm để tái sử dụng một chu kỳ mới. [CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

Cùng là chờ, nhưng các thao tác không thể dùng thay thế chỉ vì tên gần giống nhau. Chọn công cụ từ quy tắc cần bảo đảm trước khi xem cách triển khai.

## Hai chế độ giành quyền

**Độc quyền** (*exclusive*) phù hợp với tình huống một luồng được giữ quyền tại một thời điểm. **Chia sẻ** (*shared*) cho phép nhiều yêu cầu cùng thành công nếu trạng thái cho phép. Cửa mở của bài là chia sẻ; mỗi người đi qua không làm cửa đóng lại.

| Lớp con định nghĩa | Giá trị trả về cần hiểu đúng |
| --- | --- |
| `tryAcquire(int)` | `true`: đã giành quyền độc quyền |
| `tryRelease(int)` | `true`: đã giải phóng đủ để có thể cho luồng chờ thử tiếp |
| `tryAcquireShared(int)` | Âm: thất bại; `0`: thành công nhưng chưa thể cho yêu cầu chia sẻ tiếp theo thành công; dương: thành công và yêu cầu chia sẻ tiếp theo có thể thành công |
| `tryReleaseShared(int)` | `true`: việc giải phóng có thể cho phép yêu cầu chia sẻ đang chờ tiến triển |

Giá trị dương của `tryAcquireShared` không phải một số giấy phép bắt buộc phải tiêu thụ, và không phải số luồng chắc chắn được đánh thức. Lớp con chỉ mở rộng những móc cần cho chế độ mình hỗ trợ; không cần tự triển khai lại hàng đợi. [Hợp đồng mở rộng AQS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

## Khi một yêu cầu chưa được chấp nhận

Xét trình tự minh họa: T1 gọi `await()` khi cửa đóng, sau đó T2 gọi `open()`. Trong lớp Sync, T1 kiểm tra trạng thái và thất bại. Phần AQS có thể tổ chức T1 vào hàng đợi rồi tạm dừng nó; sau khi T2 đổi trạng thái và báo giải phóng, T1 được tạo cơ hội thử lại. Trình tự thực tế phải xử lý cả trường hợp T2 mở cửa trước khi T1 kịp ngủ; không được suy luận rằng cứ kiểm tra thất bại là chắc chắn đã ngủ.

Ở tầng thấp, `LockSupport.park()` có thể dừng luồng, còn `unpark(thread)` cấp khả năng để luồng tiếp tục. Mỗi luồng có tối đa một giấy phép của LockSupport; các lần `unpark` không cộng dồn thành nhiều giấy phép. `park` có thể trở về vì ngắt hoặc thức dậy không do tín hiệu mong đợi, nên phải kiểm tra lại điều kiện. Giấy phép này khác với số giấy phép nghiệp vụ của `Semaphore`. [LockSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html)

AQS kết hợp việc thử giành quyền, hàng đợi và cơ chế đánh thức; nó không chỉ là một lời gọi `park`. Mã nguồn OpenJDK hiện đại cũng xử lý việc hủy chờ do ngắt/hết hạn. Chi tiết nút và thuật toán nội bộ có thể thay đổi giữa phiên bản JDK; khi học hợp đồng công khai, không nên phụ thuộc tên trường hay sơ đồ nút của một bản cũ. [Mã nguồn AQS trong OpenJDK 25](https://raw.githubusercontent.com/openjdk/jdk/jdk-25%2B36/src/java.base/share/classes/java/util/concurrent/locks/AbstractQueuedSynchronizer.java)

Với API chờ, lựa chọn phải rõ ràng:

- Chờ có ngắt cho phép yêu cầu bị hủy bằng `InterruptedException`; ví dụ dưới dùng `acquireSharedInterruptibly`.
- Chờ có hạn giúp bên gọi giới hạn thời gian chờ, nhưng hết hạn chờ không tự hủy công việc đang giữ tài nguyên.
- Chờ không phản hồi ngắt bằng cách kết thúc sớm có thể phù hợp với một hợp đồng khác; không nên âm thầm thay nó cho API có ngắt.

Hàng đợi FIFO bên trong cũng không tự tạo ra cam kết công bằng cho mọi công cụ. Chẳng hạn `ReentrantLock(true)` có chính sách ưu tiên luồng chờ lâu, nhưng `tryLock()` không có thời hạn vẫn có thể lấy khóa đang rảnh dù còn luồng chờ; công bằng của khóa không bảo đảm lịch chạy công bằng của hệ điều hành. [Chính sách công bằng của ReentrantLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)

## Minh chứng: cửa chỉ mở một lần

Chương trình Java 17+ dưới đây cố ý dùng một giao thức rất nhỏ để thấy vai trò của AQS. Trong ứng dụng thông thường, `CountDownLatch(1)` đáp ứng nhu cầu cửa một lần và nên được ưu tiên.

Quy tắc thiết kế: nhiều luồng có thể chờ; bất kỳ luồng nào cũng được mở cửa; mở lại không thay đổi trạng thái; không có chủ sở hữu và không có thao tác đóng.

```java
import java.util.concurrent.locks.AbstractQueuedSynchronizer;

public class GateDemo {
    static final class OneShotGate {
        private static final class Sync extends AbstractQueuedSynchronizer {
            @Override
            protected int tryAcquireShared(int ignored) {
                return getState() == 1 ? 1 : -1;
            }

            @Override
            protected boolean tryReleaseShared(int ignored) {
                return compareAndSetState(0, 1);
            }

            boolean isOpen() {
                return getState() == 1;
            }
        }

        private final Sync sync = new Sync();

        void await() throws InterruptedException {
            sync.acquireSharedInterruptibly(1);
        }

        void open() {
            sync.releaseShared(1);
        }

        boolean isOpen() {
            return sync.isOpen();
        }
    }

    static final class Payload {
        int value;
    }

    public static void main(String[] args) throws InterruptedException {
        OneShotGate gate = new OneShotGate();
        Payload payload = new Payload();
        int[] observed = new int[2];
        Thread[] workers = new Thread[2];

        System.out.println("before=" + gate.isOpen());

        for (int i = 0; i < workers.length; i++) {
            final int index = i;
            workers[i] = new Thread(() -> {
                try {
                    gate.await();
                    observed[index] = payload.value + index;
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            workers[i].start();
        }

        payload.value = 42;
        gate.open();
        gate.open();

        for (Thread worker : workers) {
            worker.join();
        }

        gate.await();
        System.out.println("sum=" + (observed[0] + observed[1]));
        System.out.println("after=" + gate.isOpen());
    }
}
```

Lưu đúng tên `GateDemo.java`, rồi chạy bằng JDK 17 trở lên:

```shell
javac GateDemo.java
java GateDemo
```

Stdout trong lần chạy bình thường, không có luồng bên ngoài can thiệp ngắt:

```text
before=false
sum=85
after=true
```

Các dòng in nằm trong `main`, nên thứ tự hoàn thành của hai tác vụ không làm đổi thứ tự stdout. Hai phần tử kết quả là `42` và `43`; `join()` chờ cả hai luồng kết thúc trước khi cộng.

### Phần nào là quy tắc riêng?

`tryAcquireShared` chỉ đọc cửa: `-1` khi đóng, `1` khi mở. Nó không tự ngủ, không tìm luồng kế tiếp và không sửa hàng đợi. `tryReleaseShared` dùng CAS để chỉ lần mở đầu tiên chuyển `0 -> 1`; lần `open()` thứ hai không tạo thêm một lượt qua cửa vì lượt qua cửa không phải tài nguyên bị tiêu thụ.

`await()` chuyển yêu cầu sang cơ chế chờ chia sẻ có ngắt của AQS. `open()` gọi `releaseShared`, để việc đổi trạng thái thành công được nối với cơ chế cho các luồng chờ tiến triển. Nếu chỉ gọi thẳng một hàm sửa trạng thái mà bỏ qua giao thức giải phóng, thiết kế sẽ thiếu bước cần thiết để thông báo cho những luồng đã ngủ.

Ví dụ không dùng `sleep` để buộc lịch chạy. Một tác vụ có thể tới `await()` trước hoặc sau lần mở đầu tiên; cả hai đều phải đọc đúng dữ liệu và đi tiếp. Vì thế stdout chứng minh kết quả giao thức trong lần chạy đó, không chứng minh rằng cả hai tác vụ nhất thiết từng bị park.

### Vì sao đọc được `payload.value` dù trường này không là volatile?

`main` ghi `42` trước khi công bố trạng thái cửa mở. Tác vụ chỉ đọc payload sau khi quan sát cửa mở qua trạng thái đồng bộ. Chuỗi ghi trước công bố, đọc trạng thái rồi đọc dữ liệu thiết lập quan hệ thấy dữ liệu theo mô hình bộ nhớ. Sau đó `join()` còn tạo thứ tự từ các ghi của tác vụ đến phần đọc kết quả trong `main`. Đây là các quan hệ đồng bộ; chờ một khoảng thời gian bằng `sleep` không thay thế được chúng. [JLS, quan hệ happens-before](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5)

Điều này chỉ bảo vệ việc công bố **trước lần mở đầu tiên**. Nếu `main` tiếp tục sửa payload sau khi cửa đã mở, các lần `await()` tiếp theo không khiến các ghi mới đó tự nhiên an toàn. Cửa một lần không thay thế khóa bảo vệ dữ liệu có thể thay đổi liên tục.

Trong nhánh bắt ngắt, tác vụ khôi phục cờ ngắt rồi kết thúc, thay vì đọc payload khi chưa vượt qua cửa. Chương trình minh họa không gửi ngắt; nếu phát triển thành chương trình nghiệp vụ, bên điều phối còn cần nhận biết tác vụ nào đã bị hủy và xử lý kết quả tương ứng.

## Chủ sở hữu và điều kiện chờ là các hợp đồng riêng

Với khóa độc quyền, theo dõi luồng sở hữu giúp kiểm tra ai được nhả khóa và hỗ trợ chẩn đoán. `getExclusiveOwnerThread` / `setExclusiveOwnerThread` cung cấp thông tin sở hữu; bản thân việc gán trường sở hữu không lấy khóa, không thay CAS và không tạo ra đồng bộ `volatile`. Công cụ phải duy trì thông tin đó nhất quán với giao thức trạng thái. Cửa chia sẻ của ví dụ không cần một luồng chủ. [AbstractOwnableSynchronizer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractOwnableSynchronizer.html)

`ConditionObject` phục vụ một nhu cầu khác: luồng đang giữ khóa độc quyền muốn nhả khóa để đợi điều kiện nghiệp vụ, rồi lấy lại khóa trước khi tiếp tục. `await()` lưu trạng thái, giải phóng khóa và sau đó giành lại trạng thái đã lưu; `signal()` chuyển luồng từ hàng đợi điều kiện sang hàng đợi giành khóa. Nó không chuyển ngay quyền sở hữu khóa cho luồng được báo. Chỉ dùng cơ chế này khi công cụ đáp ứng hợp đồng giải phóng hoàn toàn và khôi phục quyền giữ khóa. [ConditionObject](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.ConditionObject.html)

Với `Condition`, điều kiện nghiệp vụ vẫn phải kiểm tra bằng vòng `while` dưới khóa: sau khi được báo, trạng thái có thể đã bị luồng khác thay đổi, hoặc xảy ra thức dậy không do tín hiệu mong đợi. `signal()` không làm biểu thức điều kiện tự trở thành đúng. Không nên thêm `ConditionObject` vào cửa chia sẻ trên chỉ vì AQS có sẵn lớp đó. [Condition](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Condition.html)

## Lỗi thường gặp và cách tự kiểm tra

| Nhầm lẫn | Hậu quả hoặc cách sửa |
| --- | --- |
| Đặt ý nghĩa cố định cho `state`, chẳng hạn luôn là 0 rảnh / 1 bận | Viết rõ bất biến của từng công cụ trước; cửa trong bài dùng 1 là mở, không phải đang bận |
| Đọc rồi ghi `state` để thực hiện một cập nhật cạnh tranh | Hai luồng có thể cùng dựa trên giá trị cũ; dùng CAS khi giao thức cần chuyển trạng thái nguyên tử |
| Chỉ đổi cờ mà không gọi đường giải phóng phù hợp | Luồng đã chờ có thể không có cơ hội thử lại |
| Coi thức dậy là đã được cấp quyền | Luôn phải qua kiểm tra quy tắc; việc được chạy lại không chứng minh điều kiện đã đúng |
| Dùng cửa một lần làm khóa vùng tới hạn | Sau khi mở, tất cả luồng đi tiếp; nó không loại trừ truy cập đồng thời |
| Nuốt `InterruptedException` rồi tiếp tục xử lý như thành công | Tác vụ có thể dùng dữ liệu chưa sẵn sàng; truyền ngắt hoặc kết thúc theo hợp đồng rõ ràng |

Để luyện tập, hãy dự đoán trước khi sửa chương trình:

1. Chuyển `gate.open()` lên trước vòng tạo luồng: kết quả vẫn là `85`; các tác vụ đến sau không cần chờ cửa mở.
2. Bỏ lần gọi `open()` thứ hai: kết quả không đổi vì cửa chỉ cần chuyển trạng thái một lần.
3. Thay giá trị `42` thành `100`: kết quả thành `201`, vì hai vị trí lưu `100` và `101`.
4. Bỏ mọi lời gọi `open()`: các tác vụ không vượt qua cửa, nên `join()` không hoàn tất bình thường; hãy nêu chính sách hủy hoặc thời hạn cần có trước khi chạy biến thể này.

Khi đọc một công cụ dựa trên AQS, hãy xác định ý nghĩa trạng thái, điều kiện cho phép đi tiếp, thao tác mở khả năng tiến triển và chế độ chờ. Sau đó mới lần theo hàng đợi hoặc park/unpark. Cách đọc này giữ trọng tâm ở giao thức đồng bộ mà ứng dụng thực sự cần.
