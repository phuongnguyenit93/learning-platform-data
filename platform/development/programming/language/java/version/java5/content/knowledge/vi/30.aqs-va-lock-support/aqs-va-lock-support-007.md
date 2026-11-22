# LockSupport.park, unpark và giấy phép cho luồng

## 1. LockSupport giải quyết vấn đề gì?

Một luồng chưa thể làm tiếp vì điều kiện chưa đúng có hai lựa chọn cơ bản: liên tục kiểm tra, hoặc tạm chờ rồi kiểm tra lại khi có cơ hội. Kiểm tra liên tục có thể tiêu tốn CPU. `LockSupport` cung cấp các thao tác mức thấp để tạm chờ bằng `park` và tạo cơ hội tiếp tục bằng `unpark`.

Đây là vật liệu xây dựng khóa và công cụ đồng bộ, không phải một khóa hoàn chỉnh. Nó không tự biết “có dữ liệu”, “khóa đã rảnh” hay “công việc đã xong”. Chương trình phải lưu điều kiện đó bằng trạng thái được đồng bộ đúng; `park` chỉ hỗ trợ chờ khi chưa được đi tiếp.

Hình dung mỗi luồng có một ô giữ vé kích thước một. `unpark` đặt vé vào ô; `park` lấy vé nếu có, nếu chưa có thì có thể tạm chờ. Vé này chỉ là cơ chế hỗ trợ chờ, không phải giấy phép truy cập tài nguyên nghiệp vụ. [Tổng quan LockSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html)

Bài học tập trung vào API còn áp dụng trên Java hiện hành. Ví dụ chạy được trên Java 17 trở lên; không dựa vào cơ chế tạm dừng luồng cũ hay chi tiết triển khai riêng của một JDK.

## 2. Giấy phép gắn với luồng, tối đa một đơn vị

Giấy phép của `LockSupport` gắn với **luồng đích**. Nó không gắn với biến khóa, không gắn với đối tượng `blocker`, và không tăng thành một bộ đếm khi gọi `unpark` nhiều lần.

| Tình huống khái niệm | Trạng thái giấy phép sau đó |
| --- | --- |
| Luồng đang chạy, chưa có giấy phép; gọi `unpark(t)` | Có một giấy phép cho `t` |
| Đã có giấy phép; gọi tiếp `unpark(t)` | Vẫn chỉ có một giấy phép |
| `t` gọi `park` khi đang có giấy phép | Tiêu thụ giấy phép và trở về ngay |
| `t` gọi `park` khi không có giấy phép | Có thể tạm chờ |
| `t` đang park; luồng khác gọi `unpark(t)` | Có thể tiếp tục, nhưng thời điểm được chạy lại phụ thuộc bộ lập lịch |

Vì vậy, hai lần `unpark` không phải hai thông báo có thể đếm được. Nếu cần lưu số công việc, số tín hiệu hay số tài nguyên, phải có bộ đếm/hàng đợi riêng hoặc dùng công cụ thư viện thích hợp như `Semaphore` và `BlockingQueue`. `Semaphore` thực sự quản lý số giấy phép; không thể thay một bộ đếm giấy phép bằng các lệnh `unpark`. [Semaphore và giấy phép đếm được](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Semaphore.html)

`unpark(null)` không làm gì. Với một đối tượng `Thread` chưa được bắt đầu, không có bảo đảm lời gọi `unpark` sẽ có tác dụng. Hãy phân biệt **luồng đã chạy nhưng chưa gọi park** với **luồng còn chưa start**. [Hợp đồng unpark](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html#unpark(java.lang.Thread))

## 3. Vì sao unpark có thể đến trước park?

Xét một luồng B đã hoạt động:

```text
Luồng A: unpark(B)
Luồng B: ... chạy một đoạn không tiêu thụ giấy phép ...
Luồng B: park()
         → có giấy phép nên không phải chờ ở lần này
```

Tính chất đó xử lý được cuộc đua hẹp giữa “đánh thức trước” và “bắt đầu chờ sau”. Không cần đoán chính xác thời điểm B đã đi vào trạng thái chờ để mới gọi `unpark`.

Nhưng nó không miễn cho chương trình khỏi giao thức đăng ký người chờ. Nếu A chưa biết luồng nào cần đánh thức, `unpark` không thể tự tìm đúng B. Nếu một thao tác `park` khác trên chính B đã tiêu thụ vé ở giữa, lần `park` dự kiến sau đó không còn vé ấy. Cần giữ phần đăng ký, kiểm tra điều kiện và chờ ngắn, có kiểm soát; tránh lời gọi trung gian có thể chặn hoặc dùng `park`. Tài liệu API cũng lưu ý các thao tác trung gian, kể cả tải lớp trong một số tình huống, có thể ảnh hưởng giao thức dùng một giấy phép. [Giao thức chờ LockSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html)

## 4. park trở về không chứng minh điều kiện đã đúng

`park` có thể trở về do được `unpark`, do trạng thái ngắt của luồng, hoặc tự trở về dù không có tín hiệu mong đợi (spurious return). Biến thể có thời hạn còn có thể trở về vì thời gian chờ đã hết. Phương thức không trả một mã cho biết nguyên nhân nào đã xảy ra. [Các nguyên nhân park trở về](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html#park(java.lang.Object))

Do đó, một bộ đồng bộ cần hình dạng khái niệm như sau:

```text
Đăng ký luồng chờ để bên báo hiệu có thể nhìn thấy
Lặp:
    xử lý yêu cầu ngắt theo hợp đồng
    nếu điều kiện nghiệp vụ đúng: đi tiếp
    nếu chưa đúng: park
Dọn đăng ký khi kết thúc chờ
```

Sai lầm thường gặp là dùng `if (!ready) park()` rồi đọc dữ liệu ngay. Một lần trở về sớm có thể làm chương trình đi tiếp khi `ready` vẫn sai. Vòng lặp không dùng để chờ cho đủ số lần đánh thức; nó dùng để kiểm tra lại điều kiện thật.

Trong khóa, điều kiện thật thường là **thao tác lấy khóa thành công**, không chỉ là thấy ai đó vừa nhả. Một luồng khác có thể lấy được khóa trước khi luồng được đánh thức chạy lại. Trong một thông điệp mở một lần, điều kiện thật có thể là cờ `ready` đã được công bố.

## 5. Trạng thái dùng để truyền dữ liệu phải được đồng bộ

Không dùng `unpark` như một phép công bố tùy ý mọi trường thường. Giao thức đáng tin cần trạng thái `volatile`, thao tác nguyên tử hoặc cơ chế đồng bộ thích hợp. Với ví dụ thông điệp một lần:

```text
Bên gửi: ghi value → ghi volatile ready = true → unpark người chờ
Bên nhận: đọc thấy volatile ready == true → đọc value
```

Quan hệ ghi/đọc `volatile` cung cấp thứ tự khả kiến cần thiết. Dữ liệu được ghi trước lần công bố `ready = true`, nên bên nhận thấy điều kiện đúng mới đọc dữ liệu. Nếu ghi cờ trước rồi mới ghi dữ liệu, bên nhận có thể chạy vào khoảng giữa và đọc giá trị cũ. [JLS: quan hệ happens-before](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5)

Vòng lặp có `park` không tự sửa được một trường điều kiện thiếu đồng bộ. Thêm `sleep`, in log hoặc “đợi lâu hơn” cũng không tạo ra hợp đồng công bố dữ liệu đúng. Tách hai nhiệm vụ: trạng thái xác định tính đúng; `park`/`unpark` hỗ trợ tiến trình chờ.

## 6. Chương trình hoàn chỉnh: vé đến sớm, nhận dữ liệu và ngắt

Lưu thành `LockSupportPermitDemo.java`. `OneShotMessage` chỉ hỗ trợ **một luồng gọi await và một lần complete**; ví dụ không phải hộp thư tổng quát cho nhiều người nhận hoặc nhiều lần gửi.

```java
import java.util.concurrent.locks.LockSupport;

public class LockSupportPermitDemo {
    static final class OneShotMessage {
        private volatile boolean ready;
        private volatile Thread waiter;
        private int value;

        int await() throws InterruptedException {
            // This example allows exactly one waiting thread.
            waiter = Thread.currentThread();
            try {
                for (;;) {
                    if (Thread.interrupted()) {
                        throw new InterruptedException();
                    }
                    if (ready) {
                        return value;
                    }
                    LockSupport.park(this);
                }
            } finally {
                waiter = null;
            }
        }

        void complete(int newValue) {
            // This example allows exactly one producer call.
            value = newValue;
            ready = true;
            LockSupport.unpark(waiter);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        // Initialize LockSupport before registering any waiter.
        LockSupport.unpark(null);

        Object blocker = new Object();
        Thread current = Thread.currentThread();
        LockSupport.unpark(current);
        LockSupport.park(blocker);
        System.out.println("earlyPermit=consumed");

        OneShotMessage message = new OneShotMessage();
        Thread consumer = new Thread(() -> {
            try {
                System.out.println("message=" + message.await());
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                System.out.println("message=interrupted");
            }
        });
        consumer.start();
        message.complete(42);
        consumer.join();

        Thread interruptDemo = new Thread(() -> {
            Thread.currentThread().interrupt();
            LockSupport.park(blocker);
            System.out.println("interruptStillSet="
                    + Thread.currentThread().isInterrupted());
            Thread.interrupted();
        });
        interruptDemo.start();
        interruptDemo.join();
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac LockSupportPermitDemo.java
java LockSupportPermitDemo
```

Stdout:

```text
earlyPermit=consumed
message=42
interruptStillSet=true
```

### Phần 1: giấy phép đến trước lần park

Luồng chính đang hoạt động tự nhận một giấy phép bằng `unpark(current)`, rồi gọi thẳng `park(blocker)`. Không có thao tác chờ trung gian trong đoạn đó. `park` tiêu thụ giấy phép và trở về; chương trình không cần luồng phụ đánh thức lần này. Ví dụ không đo độ trễ và không dùng thời gian chạy để suy ra bảo đảm lập lịch.

Lời gọi `unpark(null)` ở đầu chương trình chủ động làm `LockSupport` được khởi tạo trước khi đăng ký người chờ. Nó không cấp giấy phép cho một luồng nào.

### Phần 2: complete và await có thể xảy ra theo nhiều thứ tự

`consumer.start()` không bảo đảm `consumer` đã đăng ký hoặc đã park trước khi luồng chính gọi `complete(42)`. Thiết kế phải đúng ở các trường hợp:

1. **Complete trước đăng ký:** `waiter` có thể còn `null`, nên chưa có ai được unpark. Tuy vậy, `ready = true` được lưu lại. Người nhận đăng ký sau và nhìn thấy `ready`, nên không cần park.
2. **Đăng ký trước complete, chưa park:** người gửi thấy `waiter`, ghi dữ liệu/cờ và gọi `unpark`. Nếu người nhận vẫn đi đến park sau đó, giấy phép giúp nó trở lại rồi kiểm tra điều kiện.
3. **Người nhận đã park:** người gửi công bố dữ liệu rồi unpark đúng luồng; người nhận chạy lại và kiểm tra `ready` trong vòng lặp.

Đó là lý do vừa cần cờ `ready`, vừa cần đăng ký `waiter`. Một tín hiệu không có trạng thái không thể thay cho thông tin “đã hoàn tất”; một cờ đúng không có cơ chế đánh thức lại có thể để người đã ngủ chờ mãi.

`value` là trường thường nhưng chỉ được bên gửi ghi một lần trước cờ `ready`. Bên nhận đọc nó sau khi thấy cờ đúng. Không được mở rộng ví dụ bằng cách ghi `value` nhiều lần tùy ý sau complete rồi vẫn cho rằng nó có cùng bảo đảm.

### Phần 3: park giữ nguyên trạng thái ngắt

Luồng `interruptDemo` đặt cờ ngắt cho chính nó trước khi park. `park` trở về nhưng không ném `InterruptedException` và không xóa cờ; vì vậy `isInterrupted()` in `true`. Lời gọi `Thread.interrupted()` sau đó chủ động đọc và xóa cờ của luồng hiện tại. [API ngắt Thread](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#interrupted())

`OneShotMessage.await()` có hợp đồng khác được viết ở tầng trên: mỗi vòng nó dùng `Thread.interrupted()` để phát hiện yêu cầu hủy, rồi tự ném `InterruptedException`. `finally` dọn đăng ký người chờ. Nếu ngắt và hoàn tất xảy ra cạnh tranh, kết quả phụ thuộc thời điểm các phép kiểm tra; ví dụ chỉ ưu tiên ngắt khi phép kiểm tra đầu vòng đã quan sát thấy ngắt, không cam kết một thứ tự tuyệt đối giữa hai sự kiện.

## 7. Chọn chính sách ngắt, tránh vòng lặp bận

Nếu cờ ngắt đang bật mà vòng lặp cứ gọi `park` lại, lời gọi có thể trở về ngay liên tiếp. Chương trình trông như đang chờ nhưng thực ra có thể chạy vòng lặp nhanh và tiêu tốn CPU.

Cần chọn một trong các hợp đồng rõ ràng:

- **Chờ có thể hủy:** phát hiện ngắt, dọn đăng ký rồi kết thúc bằng ngoại lệ hoặc kết quả hủy đã quy định.
- **Chờ không hủy vì ngắt:** ghi nhận việc đã bị ngắt, xóa cờ trong thời gian tiếp tục chờ nếu cần để park có hiệu lực, rồi khôi phục cờ khi rời phương thức. Chính sách này cần cẩn thận với toàn bộ giao thức.

`Thread.currentThread().isInterrupted()` chỉ quan sát cờ; `Thread.interrupted()` quan sát và xóa cờ của luồng hiện tại. Không đổi hai thao tác này cho nhau mà bỏ qua tác dụng phụ. Ví dụ chờ có thể hủy dùng thao tác xóa cờ khi chuyển sang ném `InterruptedException`; chỗ bắt ngoại lệ trong tác vụ khôi phục cờ trước khi kết thúc.

## 8. parkNanos và parkUntil không thay thế vòng kiểm tra

| API | Đối số thời gian | Điều cần nhớ |
| --- | --- | --- |
| `park(blocker)` | Không đặt hạn | Vẫn có thể trở về sớm |
| `parkNanos(blocker, nanos)` | Khoảng thời gian tương đối, nano giây | `nanos <= 0` thì không làm gì; có thể trở về trước hạn |
| `parkUntil(blocker, deadlineMillis)` | Mốc thời gian tuyệt đối tính theo mili giây từ epoch | Khác đơn vị và ý nghĩa với `parkNanos` |

Khi viết một thao tác chờ có thời hạn, mỗi lần trở lại phải kiểm tra điều kiện và tính thời gian **còn lại**. Nếu mỗi lần lặp lại park với nguyên thời hạn ban đầu, một số lần trở về sớm có thể làm tổng thời gian chờ dài hơn dự định.

```text
Ghi nhận ngân sách thời gian bằng đồng hồ đơn điệu
Lặp:
    kiểm tra ngắt
    nếu điều kiện đúng: thành công
    tính lại thời gian còn lại
    nếu hết thời gian: kết thúc chờ
    parkNanos với phần thời gian còn lại
```

Để đo khoảng thời gian trong Java, thường dùng `System.nanoTime()` theo một phép tính thời gian đã xử lý giới hạn phù hợp; không trộn giá trị nanoTime với mốc epoch của `parkUntil`. Thời gian hết không có nghĩa luồng sẽ được chạy đúng ngay nanô giây ấy. Khi không xây công cụ đồng bộ, dùng các API có sẵn như `await(timeout, unit)` của công cụ thư viện giúp tránh tự viết sai việc ngắt, thời hạn và dọn người chờ. [Các biến thể park](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html)

## 9. blocker để chẩn đoán, không phải đối tượng khóa

`park(this)` hoặc `park(blocker)` ghi nhận một đối tượng mô tả lý do chờ. Công cụ chẩn đoán có thể dùng `LockSupport.getBlocker(thread)` để quan sát nó. Điều này giúp nhận ra luồng đang chờ bộ đồng bộ nào. Kết quả chỉ là ảnh chụp tức thời; luồng có thể đã thức hoặc chờ ở nơi khác ngay sau khi quan sát. [Thông tin blocker](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html#getBlocker(java.lang.Thread))

`blocker` không chia không gian giấy phép thành nhiều kênh. Hai đối tượng blocker khác nhau vẫn không tạo ra hai vé độc lập cho cùng một luồng. `unpark` nhận `Thread`, không nhận blocker; cùng một blocker cũng không khiến mọi luồng dùng nó được đánh thức cùng lúc.

Đừng dùng `getBlocker` làm bước quyết định “đã ngủ rồi mới được gửi tín hiệu”. Đó là dữ liệu chẩn đoán, còn tiến trình đúng phải dựa trên đăng ký người chờ và điều kiện có đồng bộ như ở ví dụ.

## 10. park không tự nhả khóa đang giữ

`Object.wait()` yêu cầu người gọi giữ monitor tương ứng; thao tác chờ nhả monitor đó rồi lấy lại trước khi kết thúc. `Condition.await()` phối hợp với khóa gắn với điều kiện. `LockSupport.park()` không cung cấp giao thức nhả/lấy lại khóa như vậy. [Object.wait](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html#wait()), [Condition.await](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Condition.html)

Ví dụ một luồng giữ khóa L rồi park để chờ dữ liệu, trong khi bên tạo dữ liệu cần khóa L mới cập nhật được điều kiện. Vì park không nhả L, hai bên có thể không tiến lên được. Đổi từ `await` sang `park` bằng cách thay tên phương thức sẽ phá giao thức này.

| Công cụ | Vai trò điển hình |
| --- | --- |
| `LockSupport.park/unpark` | Nền tảng tạm chờ/cho cơ hội tiếp tục theo luồng; tự quản lý điều kiện và đăng ký |
| `Object.wait/notify` | Chờ với monitor và tập chờ của đối tượng |
| `Condition.await/signal` | Chờ điều kiện gắn với một khóa |
| `Semaphore` | Quản lý số giấy phép có thể lấy/trả |
| `Thread.sleep` | Tạm ngừng theo thời gian; không có cơ chế unpark bằng giấy phép và không nhả monitor đang giữ |

[Hợp đồng sleep](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#sleep(long))

## 11. Quan hệ với AQS và giới hạn của ví dụ

Trong một bộ đồng bộ dựa trên AQS, các điểm thử lấy quyền quyết định trạng thái; khung AQS tổ chức người chờ, thử lại và phối hợp việc tạm chờ/đánh thức. Không cần tự ghép `park` vào `tryAcquire` để làm nó “chờ tốt hơn”. `LockSupport` là tầng thấp hơn, nên người tự dùng trực tiếp phải gánh phần giao thức mà AQS thường đảm nhiệm.

`OneShotMessage` chỉ minh họa đăng ký và tín hiệu một lần. Nó không hỗ trợ nhiều waiter, xếp hàng công bằng, gửi nhiều thông điệp, đặt lại cờ, thời hạn hoặc báo kết quả hoàn tất cho nhiều người. Nếu có hai người nhận cùng ghi `waiter`, một người có thể bị thay khỏi đăng ký và không được đánh thức. Không sửa bằng cách gọi `unpark` nhiều lần cho cùng một biến; phải đổi cấu trúc quản lý người chờ hoặc dùng công cụ thư viện thích hợp.

## 12. Thực hành tự kiểm tra

1. **Hai lần unpark trước một lần park tạo ra hai vé không?** Không. Số giấy phép của mỗi luồng tối đa một; lần park tiếp theo tiêu thụ vé đó, lần park sau nữa có thể phải chờ nếu không có tín hiệu/ngắt/lần trở về sớm khác.
2. **Có thể bỏ volatile khỏi ready vì đã gọi unpark không?** Không nên suy luận như vậy. Ví dụ dựa vào quan hệ công bố `volatile` để kiểm tra điều kiện và đọc dữ liệu đúng.
3. **Nếu complete xảy ra trước khi waiter được đăng ký, vì sao không treo?** Vì trạng thái `ready = true` đã được lưu; người nhận kiểm tra điều kiện sau đăng ký và có thể không cần park.
4. **park trở về có cho biết chắc đã nhận một tín hiệu complete không?** Không. Phải kiểm tra điều kiện; có thể do ngắt hoặc trở về sớm.
5. **Đổi park(this) thành park(new Object()) có tạo giấy phép mới không?** Không. Đối tượng chỉ hỗ trợ chẩn đoán; giấy phép gắn với luồng.
6. **Muốn nhận mười công việc có nên gọi unpark mười lần rồi park mười lần không?** Không. Hãy lưu các công việc trong hàng đợi hoặc dùng cơ chế đếm phù hợp; unpark chỉ giúp người chờ có cơ hội đọc lại trạng thái.
