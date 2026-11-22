# Trạng thái đồng bộ và cơ chế xếp hàng chờ trong AQS

## 1. Hai câu hỏi mà bộ đồng bộ phải giải quyết

Khi nhiều luồng cùng muốn đi qua một điểm kiểm soát, bộ đồng bộ phải trả lời hai câu hỏi: **luồng này có được đi tiếp ngay không**, và **nếu chưa được thì chờ bằng cách nào**. Trong `AbstractQueuedSynchronizer` (AQS), lớp con định nghĩa điều kiện đi tiếp bằng trạng thái đồng bộ; AQS cung cấp khung xếp hàng, chờ, thử lại và xử lý kết thúc chờ. Nhờ đó, người viết một bộ đồng bộ không phải tự ghép mọi tình huống cạnh tranh giữa các luồng.

Ví dụ đời thường: cửa phòng có thể đang khóa hoặc mở; danh sách người chờ cửa là một thông tin khác. Cửa đang khóa không cho biết có bao nhiêu người chờ. Có người chờ cũng không có nghĩa người đầu danh sách đang sở hữu chìa khóa. Tách hai loại thông tin này giúp đọc AQS chính xác hơn.

Bài học tập trung vào mô hình và hợp đồng API còn áp dụng trên Java hiện hành. Không cần học thuộc tên trường riêng, mã trạng thái nút hay thuật toán nội bộ của một bản JDK cũ. Khi cần một khóa hoặc cổng chờ trong ứng dụng thông thường, ưu tiên `ReentrantLock`, `Semaphore`, `CountDownLatch` và các lớp thư viện phù hợp; tự kế thừa AQS là công việc xây dựng công cụ đồng bộ.

## 2. Trạng thái đồng bộ biểu diễn điều gì?

AQS quản lý một giá trị `int` làm trạng thái đồng bộ. Ý nghĩa của con số do lớp con quy định; AQS không tự hiểu `0` là mở hay đóng. Ba thao tác nền tảng là `getState()`, `setState(int)` và `compareAndSetState(expected, update)`. Lớp con phải duy trì quy tắc hợp lệ của mình khi có nhiều luồng truy cập. [Tài liệu AQS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

Xét ba thiết kế minh họa độc lập:

| Thiết kế | Quy ước trạng thái | Khi nào được đi tiếp? |
| --- | --- | --- |
| Khóa đơn không tái nhập | `0` là rảnh, `1` là đã chiếm | Chuyển thành công từ `0` sang `1` |
| Cổng mở một lần | `0` là đóng, `1` là mở | Đọc thấy `1`; không cần đóng cổng lại |
| Bộ đếm giấy phép đơn giản | `n` là số giấy phép còn lại | Trừ đủ số giấy phép cần lấy mà không âm |

Đây là các quy ước thiết kế, không phải bảng ý nghĩa chung cho mọi lớp kế thừa AQS. Cùng giá trị `1` có thể là “khóa đang bận” hoặc “cổng đã mở”. Vì vậy, khi đọc mã, luôn bắt đầu từ quy tắc trạng thái và điều kiện thành công của lớp con.

### Đọc/ghi nguyên tử chưa đủ cho thao tác đọc–sửa–ghi

Giả sử hai luồng cùng thấy một giấy phép. Nếu cả hai đều đọc `1`, tính `0` rồi gọi `setState(0)`, cả hai có thể tưởng mình đã lấy được giấy phép duy nhất. Cần một phép chuyển có điều kiện: CAS chỉ ghi giá trị mới khi trạng thái vẫn bằng giá trị đã đọc. Khi CAS thất bại, phải đọc lại và quyết định lại theo quy tắc của bộ đồng bộ.

`setState` vẫn có chỗ dùng, chẳng hạn khởi tạo đối tượng trước khi chia sẻ hoặc cập nhật trong đường đi mà quyền độc quyền đã bảo vệ thao tác đó. Không thay mọi phép ghi bằng vòng CAS một cách máy móc; xác định trước ai được phép thay đổi trạng thái ở từng thời điểm.

Trạng thái AQS cũng khác **chủ sở hữu**: một khóa tái nhập cần biết luồng nào đang giữ khóa và số lần luồng đó giữ. Một cổng mở một lần không có chủ sở hữu; nhiều luồng chỉ cùng quan sát điều kiện mở. Các trường hỗ trợ bổ sung phải có quy tắc an toàn luồng riêng. Nếu thiết kế cần trạng thái 64 bit, thư viện còn có `AbstractQueuedLongSynchronizer`. [Tài liệu AQLS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedLongSynchronizer.html)

## 3. Từ thử lấy quyền đến xếp hàng

Ở chế độ độc quyền, lớp con cung cấp `tryAcquire(arg)` và `tryRelease(arg)`. AQS gọi các điểm mở rộng này từ những thao tác cấp cao như `acquire(arg)` và `release(arg)`. Điểm mở rộng nên ngắn, an toàn luồng và không tự chặn luồng; nếu cần chờ, hãy để khung AQS đảm nhiệm. [Hợp đồng mở rộng AQS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

Luồng xử lý khái niệm sau **không phải mã nguồn của một JDK cụ thể**:

```text
Yêu cầu lấy quyền
    → thử điều kiện/trạng thái
        → thành công: tiếp tục
        → thất bại: đăng ký chờ trong hàng đợi AQS
            → thử lại khi có cơ hội
            → còn chưa được: có thể park
            → được đánh thức: kiểm tra và thử lấy quyền lại
```

Hãy theo dõi một tình huống minh họa với khóa đơn:

1. Luồng A chuyển trạng thái từ rảnh sang bận và vào vùng được bảo vệ.
2. Luồng B muốn vào nhưng điều kiện chưa thỏa; B đi vào đường chờ.
3. Luồng C cũng muốn vào; nó có thể phải chờ. Thứ tự được lấy khóa còn phụ thuộc chính sách của khóa.
4. A cập nhật trạng thái khi nhả khóa. Cơ chế chờ tạo cơ hội cho luồng phù hợp thử lại.
5. B chỉ được vào sau khi phép thử lấy quyền của B thành công. Việc được đánh thức chưa xác nhận bước này.

Hàng đợi không phải khóa bảo vệ dữ liệu nghiệp vụ. Nó tổ chức các yêu cầu chưa hoàn thành. Cũng không nên xem mỗi phần tử vật lý trong cấu trúc nội bộ là một luồng đang ngủ: cấu trúc triển khai có thể chứa nút điều phối và yêu cầu đang bị hủy. Khi quan sát hệ thống, số luồng chờ là thông tin giám sát thay đổi liên tục, không phải căn cứ để tự cấp quyền truy cập tài nguyên.

## 4. Vai trò của `LockSupport`: tạm chờ và đánh thức

`LockSupport.park` hỗ trợ tạm dừng việc thực thi của luồng; `unpark(thread)` tạo giấy phép cho luồng đó tiếp tục. Mỗi luồng có tối đa một giấy phép kiểu này, không phải bộ đếm cộng dồn. Nếu `unpark` đến trước lần `park` kế tiếp, giấy phép có thể giúp lần `park` đó trở về ngay. [Tài liệu LockSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html)

Giấy phép của `LockSupport` **khác** trạng thái nghiệp vụ của bộ đồng bộ. Một luồng có thể trở lại từ `park` vì được đánh thức, bị ngắt hoặc tự trở về dù điều kiện chưa đổi. Vì thế cần kiểm tra lại điều kiện trong vòng lặp. AQS phối hợp phần đăng ký chờ và thử lại; không nên chèn thêm lệnh `park` vào `tryAcquire` để “giúp” AQS chờ. [Các nguyên nhân park trở về](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html#park(java.lang.Object))

Ví dụ suy luận: B được đánh thức khi A nhả khóa, nhưng một luồng khác có thể lấy khóa trước lúc B được hệ điều hành cho chạy lại. B phải chờ thêm. Nếu B coi đánh thức là bằng chứng đã giữ khóa, hai luồng có thể cùng sửa dữ liệu. Quyền truy cập luôn đến từ phép lấy quyền thành công theo giao thức của bộ đồng bộ.

## 5. Độc quyền và chia sẻ khác nhau ở điều kiện thành công

Độc quyền phù hợp khi chỉ một luồng được sở hữu tài nguyên tại một thời điểm. Chế độ chia sẻ cho phép nhiều yêu cầu cùng thành công nếu điều kiện cho phép. Một cổng đã mở là ví dụ dễ hiểu: luồng đầu tiên đi qua không làm cổng đóng lại đối với luồng sau.

Với `tryAcquireShared(arg)`, kết quả âm biểu thị thất bại; `0` là thành công nhưng không còn khả năng cấp chia sẻ tiếp theo; số dương là thành công và có thể còn khả năng đó. `tryReleaseShared(arg)` trả về liệu lần nhả này có thể cho phép yêu cầu chờ thành công. AQS dùng thông tin này để phối hợp tiến trình chia sẻ. [API acquire/release chia sẻ](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

Kết quả dương không phải số luồng chắc chắn sẽ được đánh thức hay thứ tự chúng sẽ hoàn tất. Trong ví dụ cổng bên dưới, trả `1` chỉ diễn đạt rằng cổng mở cho các yêu cầu tiếp tục thử; nó không biểu thị “còn đúng một vé”.

## 6. FIFO, công bằng, ngắt và hết thời gian

**Có hàng đợi FIFO không đồng nghĩa mọi lời gọi sẽ được cấp quyền tuyệt đối theo thứ tự đến.** Chính sách của bộ đồng bộ và đường gọi API quyết định việc một luồng mới có được chen lên hay không. `ReentrantLock(true)` ưu tiên luồng đợi lâu khi cạnh tranh; `tryLock()` không thời hạn của chính khóa đó vẫn có thể lấy ngay khi khóa rảnh. Công bằng của khóa cũng không bảo đảm công bằng của bộ lập lịch luồng. [Quy tắc công bằng ReentrantLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)

Cần xác định rõ hợp đồng chờ trước khi dùng:

| Nhu cầu | Nhóm API AQS tương ứng | Ý nghĩa với bên gọi |
| --- | --- | --- |
| Chờ lấy quyền độc quyền, không hủy vì ngắt | `acquire` | Ngắt không làm lời gọi lập tức ném `InterruptedException` |
| Cho phép hủy chờ vì ngắt | `acquireInterruptibly` | Có thể kết thúc bằng `InterruptedException` |
| Chờ có thời hạn | `tryAcquireNanos` | Có thể trả `false` khi hết thời gian, hoặc ném ngoại lệ ngắt |
| Chờ chia sẻ | Các biến thể `acquireShared...` | Cần chọn chính sách ngắt/thời hạn tương ứng |

Một yêu cầu hết thời gian hoặc bị ngắt cần được loại khỏi đường cạnh tranh theo cơ chế AQS. Đừng tự sửa liên kết hàng đợi hay viết thuật toán đánh thức kế tiếp trong lớp con. Thời hạn chờ cũng không bảo đảm lời gọi trở về đúng chính xác từng nano giây; việc luồng được chạy lại còn phụ thuộc bộ lập lịch. [Các thao tác chờ AQS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html), [Quy tắc thời gian java.util.concurrent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html)

## 7. Minh chứng: cổng mở một lần với trạng thái 0/1

Thiết kế sau có hai quy tắc: cổng bắt đầu đóng; một lần mở thành công làm nó mở vĩnh viễn. Không có thao tác đóng lại. Vì mọi luồng đều được đi qua sau khi mở, ta dùng chế độ chia sẻ. Đây là bài thực nghiệm để hiểu AQS; với nhu cầu ứng dụng tương tự, có thể dùng `CountDownLatch(1)`.

Lưu toàn bộ mã vào `AqsStateQueueDemo.java`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.AbstractQueuedSynchronizer;

public class AqsStateQueueDemo {
    static final class OneShotGate {
        private static final class Sync extends AbstractQueuedSynchronizer {
            private static final long serialVersionUID = 1L;

            @Override
            protected int tryAcquireShared(int ignored) {
                return getState() == 1 ? 1 : -1;
            }

            @Override
            protected boolean tryReleaseShared(int ignored) {
                return compareAndSetState(0, 1);
            }
        }

        private final Sync sync = new Sync();

        void await() throws InterruptedException {
            sync.acquireSharedInterruptibly(1);
        }

        boolean await(long timeout, TimeUnit unit) throws InterruptedException {
            return sync.tryAcquireSharedNanos(1, unit.toNanos(timeout));
        }

        void open() {
            sync.releaseShared(1);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        OneShotGate gate = new OneShotGate();
        System.out.println("before=" + gate.await(20, TimeUnit.MILLISECONDS));

        int[] payload = {0};
        Thread producer = new Thread(() -> {
            payload[0] = 42;
            gate.open();
        });
        producer.start();

        gate.await();
        System.out.println("value=" + payload[0]);
        producer.join();
        System.out.println("after=" + gate.await(0, TimeUnit.NANOSECONDS));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac AqsStateQueueDemo.java
java AqsStateQueueDemo
```

Stdout:

```text
before=false
value=42
after=true
```

### Đọc kết quả theo trạng thái và hàng chờ

- `before=false`: chưa có luồng nào mở cổng, nên lời chờ có thời hạn không lấy được quyền và kết thúc. Thử lấy quyền thất bại không biến trạng thái thành mở.
- Luồng `producer` ghi `42` rồi gọi `open()`. CAS `0 → 1` là chuyển trạng thái một chiều; các lần `open()` sau không chuyển lại trạng thái.
- `gate.await()` của luồng chính chỉ hoàn thành bình thường khi điều kiện cổng mở đã thỏa. Nếu luồng chính đã chờ, AQS phối hợp để nó thử lại; nếu nhà sản xuất mở trước, lời chờ có thể thành công ngay.
- `value=42`: dữ liệu được ghi trước thao tác công bố trạng thái mở. Việc đọc trạng thái đồng bộ khi chờ thành công tạo liên hệ khả kiến cần thiết; không cần lấy `Thread.sleep` làm cơ chế truyền dữ liệu. Các thao tác trạng thái AQS có ngữ nghĩa bộ nhớ tương ứng truy cập `volatile`. [Ngữ nghĩa getState/setState/CAS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)
- `after=true`: cổng đã mở, nên lời chờ mới có thể thành công ngay cả với thời hạn bằng `0`. Cổng không tiêu thụ quyền sau mỗi lần đi qua.

`producer.join()` nằm sau lần đọc `payload[0]`, nên ví dụ không dựa vào `join` để làm lần đọc ấy thấy `42`. Mảng dữ liệu chỉ được một luồng ghi một lần trước khi mở; không được suy rộng thành quyền sửa mảng tùy ý sau khi cổng mở.

Thời gian 20 ms chỉ đặt giới hạn chờ của lần kiểm tra cổng đóng; stdout không phụ thuộc vào việc nhà sản xuất có chạy trong 20 ms đó, vì nhà sản xuất chưa được tạo ở thời điểm ấy. Ví dụ không kiểm chứng thứ tự cấp quyền giữa nhiều luồng, không đo hiệu năng và không bảo đảm lần chờ thứ hai thực sự phải park.

Không thêm `close()` bằng `setState(0)` vào thiết kế này: luồng đã đi qua không bị thu hồi quyền, còn luồng đang chờ có thể thuộc một thế hệ cổng khác. Cổng tái sử dụng cần một giao thức riêng để phân biệt các vòng hoạt động.

## 8. Hàng đợi AQS khác hàng đợi điều kiện

Với một khóa hỗ trợ `ConditionObject`, chờ điều kiện có thêm một giai đoạn. `await()` lưu trạng thái giữ khóa, nhả khóa và chờ điều kiện. `signal()` chuyển một yêu cầu chờ sang hàng đợi lấy lại khóa; nó không trao ngay quyền chạy trong vùng được bảo vệ. Luồng được báo hiệu phải lấy lại khóa trước khi `await()` hoàn thành theo hợp đồng. [Cơ chế ConditionObject](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.ConditionObject.html)

```text
Chờ điều kiện nghiệp vụ
    → nhận signal
    → chờ lấy lại khóa trong hàng đợi đồng bộ
    → lấy lại khóa thành công
    → kiểm tra lại điều kiện nghiệp vụ
```

Ví dụ hàng đợi tác vụ trống: người tiêu thụ cần chờ “có tác vụ”, còn sau khi được báo hiệu nó vẫn cần khóa để đọc/xóa tác vụ an toàn. Hai điều kiện này trả lời hai câu hỏi khác nhau. Bài thực nghiệm cổng mở một lần không có khóa độc quyền, nên không tự thêm `ConditionObject` chỉ vì AQS có lớp này.

## 9. Lỗi phổ biến và cách tự kiểm tra thiết kế

| Hiểu nhầm | Hậu quả | Cách kiểm tra |
| --- | --- | --- |
| Trạng thái luôn là số luồng đang chờ | Điều kiện lấy quyền sai | Viết rõ từng giá trị trạng thái có nghĩa gì |
| `setState(getState() - 1)` luôn an toàn | Hai luồng có thể lấy cùng một giấy phép | Tìm thao tác đọc–sửa–ghi chưa được bảo vệ |
| Được đánh thức là đã có khóa | Có thể sửa dữ liệu khi chưa sở hữu khóa | Xác nhận đường đi vẫn thử lấy quyền lại |
| Hàng đợi FIFO tự bảo đảm mọi API công bằng | Suy luận thứ tự chạy sai | Đọc chính sách cụ thể và từng biến thể API |
| Số luồng chờ quyết định được phép truy cập | Cạnh tranh giữa lúc quan sát và sử dụng | Dùng phép acquire để quyết định quyền |
| `tryAcquire` tự gọi `park` hoặc thao tác chậm | Làm sai giao thức chờ và khó phân tích tiến trình | Giữ điểm mở rộng ngắn, không chặn |
| Mở lại/đóng lại tùy ý trên cổng một lần | Trộn các vòng chờ và quyền đã cấp | Đặc tả vòng đời trước khi đổi mã |

Trước khi viết lớp con, thử trả lời bằng ví dụ cụ thể: bất biến trạng thái là gì; thao tác nào là điểm cấp quyền; có chủ sở hữu hay không; dùng độc quyền hay chia sẻ; chờ có ngắt/thời hạn ra sao; nhả quyền ở thời điểm nào cho phép người chờ tiến lên. Nếu chưa trả lời được, hãy hoàn thiện giao thức trước khi xử lý chi tiết triển khai.

## 10. Thực hành và đáp án định hướng

1. **Đổi `tryAcquireShared` để trả `0` khi mở có còn đúng với cổng này không?** Điều kiện cổng cho phép nhiều luồng cùng đi tiếp. Trả dương diễn đạt phù hợp khả năng tiếp tục cấp chia sẻ; không nên đổi máy móc thành `0` vì nghĩ đây là quy ước thành công chung.
2. **Đưa `gate.open()` lên trước `payload[0] = 42` có giữ bảo đảm `value=42` không?** Không. Luồng chờ có thể thấy cổng mở và đọc mảng trước phép ghi; thứ tự công bố dữ liệu là một phần của giao thức.
3. **Một yêu cầu chờ hết thời gian có mở cổng không?** Không. Nó chỉ kết thúc yêu cầu chờ của mình; trong ví dụ chỉ `open()` thực hiện chuyển `0 → 1`.
4. **Nếu thấy hàng đợi trống, có thể bỏ qua acquire không?** Không. Chưa có ai chờ không chứng minh tài nguyên đang rảnh hoặc điều kiện đang đúng.
5. **Vì sao không dùng `Thread.sleep(20)` thay cho lần await đầu?** Ngủ chỉ làm thời gian trôi qua; nó không thử điều kiện lấy quyền, không thực hiện giao thức AQS và không kiểm tra việc hết thời hạn chờ.
