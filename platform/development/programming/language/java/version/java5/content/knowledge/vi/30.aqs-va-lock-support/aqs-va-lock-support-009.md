# Đánh thức giả, tín hiệu ngắt và kiểm tra điều kiện

## Khái niệm: thức dậy chưa có nghĩa là được đi tiếp

Trong chương trình đồng thời, một luồng có thể ngừng chờ mà điều kiện nó cần vẫn chưa đúng. Hãy hình dung một người đợi hộp có dữ liệu: việc người đó tỉnh dậy chỉ cho phép nhìn lại hộp, không tự làm hộp có dữ liệu.

Ba khái niệm cần tách:

- **Điều kiện cho phép đi tiếp** (*predicate*): biểu thức như `ready`, `queue không rỗng` hoặc `lấy được khóa`.
- **Thức dậy**: lời gọi chờ trở về, tạo cơ hội kiểm tra lại điều kiện.
- **Ngắt** (*interrupt*): yêu cầu hợp tác để luồng thay đổi cách xử lý, thường nhằm hủy việc chờ hoặc kết thúc tác vụ.

**Đánh thức giả** (*spurious wakeup*) là việc lời gọi chờ trở về mà không có tín hiệu đánh thức thông thường mà chương trình đang mong đợi. API cho phép hiện tượng này; không nên đặt tính đúng đắn của chương trình trên giả định nó không xảy ra. [LockSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html)

Đây là kiến thức vẫn cần thiết khi dùng AQS, `LockSupport` và `Condition` trong Java hiện đại. Nguyên tắc cốt lõi là: **quyết định từ trạng thái và chính sách hủy, không quyết định chỉ từ việc đã thức**.

## Những nguyên nhân khác nhau có thể dẫn đến cùng một lần trở về

| Sự kiện | Có chắc điều kiện nghiệp vụ đúng không? | Việc cần làm |
| --- | --- | --- |
| Có bên báo `signal` / `unpark` | Không | Kiểm tra lại trạng thái theo giao thức |
| Có tín hiệu ngắt | Không | Xử lý theo hợp đồng hủy của API |
| Hết thời hạn chờ | Không | Kiểm tra ngân sách thời gian và trạng thái |
| Đánh thức giả | Không | Kiểm tra lại trạng thái, chờ tiếp nếu hợp lệ |

Ngay cả **tín hiệu thật** cũng không bảo đảm điều kiện còn đúng: hai người cùng được báo hộp có một món, nhưng người thứ nhất có thể lấy món đó trước khi người thứ hai lấy lại khóa. Người thứ hai đã nhận tín hiệu hợp lệ nhưng vẫn phải chờ tiếp.

Cần phân biệt trường hợp này với đánh thức giả. Không phải cứ thức dậy rồi thấy điều kiện sai là đã chứng minh JVM tạo một lần đánh thức giả; có thể dữ liệu bị bên khác lấy mất, hoặc chương trình gửi một tín hiệu không làm thay đổi điều kiện.

## Vì sao kiểm tra bằng while thay vì if?

Với dữ liệu được bảo vệ bằng khóa, trình tự đúng là giữ khóa, kiểm tra điều kiện, chờ nếu chưa đúng rồi kiểm tra lại sau khi đã lấy lại khóa.

```text
Lấy khóa
Trong khi điều kiện còn sai:
    await() -> nhả khóa và chờ -> lấy lại khóa
Kiểm tra đã qua -> xử lý dữ liệu dưới khóa
Nhả khóa trong finally
```

`if` chỉ kiểm tra một lần trước khi chờ. Nếu lần chờ trở về mà điều kiện còn sai, mã sau `if` vẫn chạy. `while` kiểm tra ở mỗi vòng, nên cả tín hiệu không đủ điều kiện, thay đổi do luồng khác và đánh thức giả đều không khiến mã sử dụng dữ liệu chưa hợp lệ.

Cùng một khóa phải bảo vệ cả việc đọc và cập nhật điều kiện. Dùng `while` không sửa được việc bên ghi thay đổi dữ liệu ngoài giao thức khóa hoặc bên đọc dùng một khóa khác. `Condition.await()` nhả khóa gắn với condition và phải lấy lại khóa trước khi trở về bình thường. [Condition](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Condition.html)

## LockSupport.park và cờ ngắt

`LockSupport.park()` có thể trở về khi có giấy phép, khi luồng bị ngắt hoặc do đánh thức giả. Lời gọi không trả một mã nguyên nhân và không ném `InterruptedException`. Khi ngắt làm nó trở về, cờ ngắt vẫn còn đặt; `park` không tự xóa cờ đó.

`unpark(thread)` cấp tối đa một giấy phép cho luồng. Nếu giấy phép đã có, các lần gọi tiếp không xếp thêm nhiều giấy phép; nếu cấp trước khi luồng park, lần park tiếp theo có thể dùng giấy phép đó. Vì vậy không được đếm số thông điệp bằng số lần `unpark`. [Ngữ nghĩa park/unpark](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html)

Để đọc cờ ngắt, phải phân biệt:

| Lệnh | Hỏi trạng thái của ai? | Có xóa cờ không? |
| --- | --- | --- |
| `thread.isInterrupted()` | Đối tượng `thread` được gọi | Không |
| `Thread.interrupted()` | Luồng đang thực thi lệnh | Có |
| `thread.interrupt()` | Gửi yêu cầu ngắt đến `thread` | Đặt yêu cầu; tác động cụ thể tùy trạng thái/API |

`Thread.interrupted()` là phương thức tĩnh. Gọi nó không phải chỉ quan sát; nó còn thay đổi trạng thái. Nếu chỉ cần xem cờ để báo cáo, dùng `isInterrupted()`. Nếu chủ động lấy và xóa yêu cầu để xử lý, phải có chính sách rõ ràng cho yêu cầu đó. [Thread: interrupt, interrupted và isInterrupted](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html)

### Một vòng lặp có thể đúng về điều kiện nhưng vẫn ngốn CPU

Giả sử mã cứ `while (!ready) park()` mà không xử lý ngắt. Khi luồng bị ngắt, `park()` trở về, nhưng cờ vẫn còn. Nếu `ready` tiếp tục sai, lần park kế tiếp cũng có thể trở về ngay; vòng lặp chạy liên tục.

Chính sách thường gặp ở tầng xây công cụ là:

1. **Cho phép hủy:** phát hiện ngắt, bỏ việc chờ đúng cách rồi trả trạng thái hủy hoặc ném ngoại lệ.
2. **Phải hoàn tất thao tác dù có ngắt:** ghi nhận ngắt, xóa cờ trong lúc vẫn phải tiếp tục chờ, rồi khôi phục cờ khi rời thao tác.

Cách thứ hai cần thuật toán phối hợp đầy đủ, không phải cứ xóa cờ để tránh tốn CPU. Nếu vừa khôi phục cờ rồi quay ngay vào vòng park, hiện tượng trở về tức thì có thể lặp lại. Với mã ứng dụng, nên dùng công cụ cấp cao đã có chính sách chờ rõ ràng thay vì tự ghép hàng đợi và park.

`park` cũng không tự nhả các khóa mà luồng đang giữ. Đây là khác biệt quan trọng với `Condition.await()` trên khóa gắn cùng condition. Giữ một khóa mà bên tạo điều kiện cần lấy rồi tự park có thể làm cả hai bên chờ nhau.

## Condition.await xử lý ngắt khác park

Đối với condition của `ReentrantLock`, `await()` hỗ trợ ngắt bằng `InterruptedException`; khi ném ngoại lệ do ngắt, cờ ngắt bị xóa. Khi đã nhả khóa để chờ, nó phải lấy lại khóa trước khi rời đường chờ theo hợp đồng. Nếu cờ đã đặt trước lúc gọi, việc kiểm tra ngắt có thể khiến nó ném ngay mà chưa bắt đầu chờ.

Do đó bên bắt ngoại lệ cần quyết định rõ: truyền `InterruptedException` lên trên, kết thúc tác vụ, hoặc khôi phục cờ bằng `Thread.currentThread().interrupt()` khi không truyền ngoại lệ được. Không được bắt rỗng rồi xử lý tiếp như dữ liệu đã sẵn sàng.

`awaitUninterruptibly()` có mục tiêu khác: tiếp tục chờ dù có ngắt, giữ thông tin ngắt để bên gọi xử lý sau. Không nên dùng nó chỉ để tránh phải viết `catch`. Các API chờ có ngắt và không kết thúc sớm vì ngắt mang hợp đồng khác nhau. [ReentrantLock.newCondition](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)

Ngắt không phải lệnh cưỡng bức dừng luồng. Bên gửi phải dựa vào giao thức hợp tác của tác vụ; đối tượng bị gọi `interrupt()` không tự động ngừng mọi phép tính đang chạy. Không suy luận rằng gọi ngắt xong thì luồng đã kết thúc; nếu cần đợi kết thúc, phải có bước phối hợp phù hợp.

## Minh chứng Java: báo tín hiệu khi điều kiện vẫn sai

Chương trình Java 17+ sau làm hai thí nghiệm độc lập: gửi một tín hiệu condition khi chưa có dữ liệu; sau đó kiểm tra trực tiếp sự khác nhau giữa ngắt trong `park` và ngắt trong `await`.

Thí nghiệm đầu **không giả vờ tạo được đánh thức giả của JVM**. Nó chủ động gửi một tín hiệu có thật mà không thay đổi điều kiện, để chứng minh vì sao trở về từ chờ chưa đủ cho phép dùng dữ liệu.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.LockSupport;
import java.util.concurrent.locks.ReentrantLock;

public class WakeupChecksDemo {
    static final class Box {
        boolean ready;
        boolean consumed;
        int value;
    }

    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        Condition changed = lock.newCondition();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch rechecked = new CountDownLatch(1);
        Box box = new Box();
        int[] observed = new int[1];

        Thread reader = new Thread(() -> {
            lock.lock();
            try {
                entered.countDown();
                while (!box.ready) {
                    changed.await();
                    if (!box.ready) {
                        rechecked.countDown();
                    }
                }
                observed[0] = box.value;
                box.consumed = true;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                lock.unlock();
            }
        });
        reader.start();

        entered.await();
        lock.lock();
        try {
            changed.signal();
        } finally {
            lock.unlock();
        }

        rechecked.await();
        lock.lock();
        try {
            System.out.println("afterUnrelatedSignal=" + box.consumed);
            box.value = 7;
            box.ready = true;
            changed.signal();
        } finally {
            lock.unlock();
        }
        reader.join();
        System.out.println("value=" + observed[0]);

        Thread.currentThread().interrupt();
        LockSupport.park();
        System.out.println("park.flag=" + Thread.currentThread().isInterrupted());
        System.out.println("clear.returned=" + Thread.interrupted());
        System.out.println("afterClear=" + Thread.currentThread().isInterrupted());

        lock.lock();
        try {
            Thread.currentThread().interrupt();
            try {
                changed.await();
            } catch (InterruptedException e) {
                System.out.println("await.caught=true");
                System.out.println("await.flag="
                        + Thread.currentThread().isInterrupted());
                System.out.println("await.holdsLock=" + lock.isHeldByCurrentThread());
            }
        } finally {
            lock.unlock();
        }
    }
}
```

Lưu thành `WakeupChecksDemo.java`, rồi chạy bằng JDK 17 trở lên:

```shell
javac WakeupChecksDemo.java
java WakeupChecksDemo
```

Stdout khi không có tác động ngắt khác từ bên ngoài:

```text
afterUnrelatedSignal=false
value=7
park.flag=true
clear.returned=true
afterClear=false
await.caught=true
await.flag=false
await.holdsLock=true
```

### Giải thích lần kiểm tra điều kiện

`entered` cho `main` biết bên đọc đã vào phần giữ khóa. Nếu bên đọc chưa kịp `await`, `main` vẫn chưa lấy được khóa để gửi tín hiệu. Bên đọc phải nhả khóa qua await thì `main` mới vào được vùng signal.

Lần báo đầu tiên không đặt `ready`. Khi bên đọc trở về và vẫn thấy điều kiện sai, nó báo `rechecked` rồi tiếp tục vòng `while`. `main` sau đó lấy lại khóa và thấy chưa tiêu thụ dữ liệu: `afterUnrelatedSignal=false`. Trường hợp có đánh thức giả cũng chỉ dẫn đến kiểm tra lại điều kiện; không làm bên đọc bỏ qua vòng lặp.

Chỉ sau khi `main` đặt giá trị `7` và `ready = true` dưới khóa, bên đọc mới được đi tiếp. Sau `join`, kết quả quan sát là `7`. Việc gửi `signal` không giữ riêng dữ liệu cho một luồng; chính điều kiện dưới khóa mới quyết định.

### Giải thích các cờ ngắt

`main` tự đặt cờ trước khi park nên park không thể trở thành một lần chờ không hạn vô cớ trong thí nghiệm đó. Nó trở về mà cờ vẫn là `true`. `Thread.interrupted()` lấy giá trị `true` rồi xóa, nên lần xem sau là `false`.

Ở phần cuối, `main` giữ khóa, tự đặt cờ rồi gọi `await()`. Ngoại lệ được bắt và cờ đã xóa, trong khi khóa vẫn thuộc `main`. Nhờ vậy `finally` nhả khóa đúng cách. Ví dụ chủ động tiêu thụ yêu cầu ngắt để quan sát API rồi kết thúc; đó không phải mẫu cho một tác vụ nghiệp vụ bỏ qua yêu cầu hủy.

Tất cả dòng in ở `main` và các bước được phối hợp bằng latch/khóa/join, không dùng `sleep` để đoán luồng đã vào trạng thái chờ. Các biến hộp được bảo vệ bằng cùng khóa, còn mảng kết quả chỉ đọc sau khi bên ghi kết thúc. [JLS, quan hệ happens-before](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5)

## Liên hệ với AQS: trở về từ park chưa phải lấy được quyền

Trong công cụ dựa trên AQS, hàng đợi và việc tạm dừng chỉ phục vụ quá trình giành quyền. Luồng có thể được đánh thức nhưng vẫn phải thử lại `tryAcquire` hoặc `tryAcquireShared`. Một công cụ công bằng còn có thể phải kiểm tra lượt chờ trước khi cấp quyền.

`acquire` và `acquireInterruptibly` không có hợp đồng hủy giống nhau. Ở chế độ chia sẻ cũng có các đường tương ứng. Lớp triển khai cần chọn đúng đường chờ cho API công khai của mình; việc tầng thấp park không ném ngoại lệ không có nghĩa API cấp cao phải bỏ qua ngắt. [AQS: các biến thể acquire](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

Không tự thêm một vòng `park` vào `tryAcquire` để xử lý đánh thức giả. Móc thử giành quyền phải ngắn, an toàn luồng và thường không chặn; AQS mới điều phối việc thử lại và chờ. Tương tự, sau `ConditionObject.await`, điều kiện nghiệp vụ của bên dùng vẫn phải được kiểm tra bằng `while`; AQS không biết biểu thức `box.ready` có nghĩa gì.

## Hết hạn cũng cần kiểm tra trạng thái

Đối với chờ có thời hạn, mỗi lần trở về đều cần kiểm tra cả điều kiện lẫn thời gian còn lại. Nếu cứ cho một thời hạn đầy đủ mới sau mỗi lần thức, một loạt tín hiệu không liên quan có thể kéo dài tổng thời gian chờ vượt ý định.

Với `Condition.awaitNanos`, có thể truyền phần thời gian còn lại mà phương thức trả về vào lần chờ kế tiếp. Khi hết ngân sách, đọc lại điều kiện dưới khóa trước khi quyết định kết quả. Với cơ chế thấp dùng `parkNanos`, thường tính thời gian đã trôi bằng đồng hồ đơn điệu `System.nanoTime()` để tránh phụ thuộc việc chỉnh đồng hồ lịch.

Hết thời hạn chờ không tự hủy bên đang tạo dữ liệu hay tự nhả khóa mà bên khác đang giữ. Bên chờ condition vẫn phải lấy lại khóa, nên thời gian thực tế rời phương thức có thể muộn hơn mốc chờ mong muốn. [ConditionObject: chờ có thời hạn](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.ConditionObject.html)

## Các lỗi cần nhận ra

| Mẫu sai | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Dùng `if` trước await rồi đọc ngay | Trở về không chứng minh điều kiện đúng | Dùng `while` dưới đúng khóa |
| Sau park coi như đã có quyền | Có thể ngắt, đánh thức giả hoặc mất lượt tranh quyền | Thử lại điều kiện cấp quyền |
| Bắt ngắt rồi tiếp tục dùng dữ liệu | Đường chờ bị hủy nhưng xử lý như thành công | Truyền ngoại lệ hoặc kết thúc theo chính sách |
| Chỉ gọi `Thread.interrupted()` để ghi log | Vô tình xóa yêu cầu ngắt | Dùng `isInterrupted()` nếu chỉ quan sát |
| Khôi phục cờ rồi tiếp tục park không hạn | Park có thể cứ trở về ngay | Rời thao tác hoặc dùng thuật toán ghi nhận/khôi phục phù hợp |
| Chờ bằng sleep để dữ liệu tự nhìn thấy | Thời gian trôi không tạo giao thức công bố dữ liệu | Dùng khóa, volatile/atomic và công cụ đồng bộ thích hợp |
| Coi nhiều unpark là nhiều thông điệp | Giấy phép không cộng dồn | Lưu thông điệp/số lượng trong trạng thái hoặc hàng đợi riêng |

Để luyện tập, hãy trả lời trước khi sửa mã:

1. Xóa `box.ready = true` nhưng vẫn signal lần cuối: bên đọc có được sử dụng giá trị `7` không? **Không**; điều kiện vẫn sai nên nó tiếp tục chờ, và `join()` có thể không hoàn tất.
2. Đổi `Thread.interrupted()` trong phần park thành `isInterrupted()`: cờ sau khi xem có bị xóa không? **Không**; các bước tiếp theo phải tính đến cờ còn đặt.
3. Một bên được signal rồi lấy lại khóa nhưng dữ liệu đã bị bên khác lấy: có chứng minh đánh thức giả không? **Không**; tín hiệu có thể hoàn toàn thật.
4. Gửi ngắt cho một tác vụ có được coi là đã dừng tác vụ không? **Không**; tác vụ phải phản hồi theo chính sách và bên điều phối phải xác minh hoàn tất nếu cần.

Một vòng chờ đúng cần có trạng thái nhìn thấy an toàn, điều kiện được kiểm tra lại và chính sách ngắt/thời hạn rõ ràng. Đánh thức chỉ giúp luồng có cơ hội đánh giá ba phần đó lần nữa.
