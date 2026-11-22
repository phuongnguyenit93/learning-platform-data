# Chế độ chiếm hữu độc quyền và chia sẻ trong AQS

## Khái niệm: được đi tiếp theo quy tắc nào?

Một công cụ đồng bộ phải quyết định khi nào một luồng được đi tiếp. Có bài toán chỉ một luồng được sửa dữ liệu; có bài toán cho tối đa vài tác vụ sử dụng tài nguyên; cũng có bài toán cho mọi tác vụ đi tiếp sau một tín hiệu. Khác biệt nằm ở **quyền được cấp**, không chỉ ở việc luồng có phải chờ hay không.

`AbstractQueuedSynchronizer` (AQS) hỗ trợ hai chế độ giành quyền: **độc quyền** (*exclusive*) và **chia sẻ** (*shared*). Khi xây dựng công cụ, lớp con định nghĩa điều kiện thành công; AQS tổ chức việc chờ nếu yêu cầu chưa thể được đáp ứng. Cả hai chế độ vẫn được dùng trong Java hiện đại. [API AQS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

Để hiểu đúng, hãy bắt đầu từ hai tình huống:

- Một thao tác cập nhật số dư phải loại trừ thao tác cập nhật khác trên cùng dữ liệu: cần quyền độc quyền.
- Một dịch vụ chỉ được gọi đồng thời tối đa ba lần: mỗi tác vụ cần một giấy phép trong tổng số ba, nên có thể dùng cơ chế chia sẻ có giới hạn.

Chia sẻ không có nghĩa là mọi yêu cầu đều thành công, và độc quyền không có nghĩa là một luồng không bao giờ được lấy lại chính khóa nó đang giữ. Đây là hai điểm cần tách trước khi đọc các phương thức AQS.

## So sánh từ ý nghĩa, không từ tên lớp

| Câu hỏi | Độc quyền | Chia sẻ |
| --- | --- | --- |
| Có thể có nhiều luồng cùng được cấp quyền không? | Không theo quyền độc quyền đang giữ | Có thể, nếu trạng thái cho phép |
| Điều gì xảy ra khi chưa đủ điều kiện? | Yêu cầu chờ hoặc thất bại theo API được gọi | Cũng có thể chờ hoặc thất bại |
| Ví dụ trực quan | Quyền sửa độc quyền một bản ghi | Vài chỗ truy cập tài nguyên hoặc cửa chờ đã mở |
| Có tự bảo đảm tính công bằng không? | Không | Không |
| Có bắt buộc quyền gắn với chủ sở hữu không? | Khóa thường theo dõi luồng sở hữu; lớp con phải định nghĩa và kiểm tra | Phụ thuộc công cụ; semaphore không có chủ sở hữu |

Chế độ là một phần giao thức của công cụ, không phải một tùy chọn chung mà mã ứng dụng bật trên mọi đối tượng AQS. Người dùng `Semaphore` gọi API của semaphore; người dùng `ReentrantLock` gọi API khóa. Khi đọc triển khai, ta mới nhận ra đường AQS nào được dùng.

## Độc quyền: ngăn luồng khác vào, nhưng có thể tái nhập

`ReentrantLock` cho phép một luồng giữ khóa để thực hiện vùng tới hạn. Luồng khác chưa được cấp khóa cho đến khi bên giữ nhả hết quyền. Chính luồng đang giữ có thể gọi `lock()` thêm lần nữa: đó là **khả năng tái nhập** (*reentrancy*). Mỗi lần lấy thành công phải được cân bằng bằng một lần `unlock()`. Nhả một trong hai lần giữ chưa khiến khóa trở thành rảnh. [Hợp đồng ReentrantLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)

Ví dụ thiết kế khóa tái nhập có thể diễn giải trạng thái như sau:

```text
state=0: chưa có ai giữ khóa
T1 lấy khóa: state 0 -> 1, chủ sở hữu là T1
T1 lấy lại: state 1 -> 2, chủ sở hữu vẫn là T1
T2 xin khóa: chưa được cấp
T1 nhả một lần: state 2 -> 1, T2 vẫn chưa được cấp
T1 nhả lần cuối: state 1 -> 0, có thể cho bên chờ thử lấy
```

Đây là mô hình giải thích quyền giữ, không phải yêu cầu mọi khóa độc quyền đều phải đếm tái nhập. Một khóa không tái nhập có thể chỉ có hai trạng thái rảnh/bận. Nếu luồng giữ gọi một API chờ lấy lại khóa không tái nhập, nó có thể tự chờ mãi vì chưa nhả quyền cũ.

Thông tin luồng sở hữu giúp phát hiện `unlock()` từ sai luồng và hỗ trợ chẩn đoán. Các phương thức theo dõi sở hữu không tự lấy khóa hay tự tạo đồng bộ; lớp triển khai phải duy trì chúng phù hợp với cập nhật trạng thái. Không thể thay thao tác giành quyền nguyên tử bằng việc chỉ gán tên luồng sở hữu. [AbstractOwnableSynchronizer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractOwnableSynchronizer.html)

## Chia sẻ: có nhiều kiểu cấp quyền

### Giấy phép bị tiêu thụ khi được cấp

`Semaphore(3)` bắt đầu với ba giấy phép. Mỗi lần lấy một giấy phép thành công làm giảm số còn sẵn; khi hết, yêu cầu tiếp theo phải chờ hoặc thất bại. Trả giấy phép mở thêm khả năng cho một yêu cầu khác. Một luồng cũng có thể lấy nhiều giấy phép nếu hợp đồng API và số lượng còn sẵn cho phép. Semaphore không theo dõi ai đã lấy nên một luồng khác có thể gọi `release()`. Mã ứng dụng chịu trách nhiệm cân bằng số giấy phép; trả thừa có thể làm sai giới hạn tài nguyên dự định. [Semaphore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Semaphore.html)

```text
Giấy phép còn sẵn: 3
T1 lấy 1 -> còn 2
T2 lấy 1 -> còn 1
T3 lấy 1 -> còn 0
T4 muốn lấy 1 -> chưa được cấp
Một giấy phép được trả -> một yêu cầu chờ có thể thử lấy
```

Chế độ chia sẻ chỉ điều phối quyền. Nếu ba tác vụ cùng sửa một `ArrayList` không có bảo vệ thích hợp, semaphore ba giấy phép không biến những phép sửa đó thành an toàn.

### Chờ một điều kiện mà không tiêu thụ quyền

`CountDownLatch` minh họa kiểu khác: các luồng chờ cho đến khi bộ đếm về `0`; khi đó mọi luồng đang chờ hoặc đến sau đều có thể vượt qua. Một luồng vượt qua không làm bộ đếm tăng trở lại. Đây là cửa một lần, không phải kho giấy phép lấy ra rồi trả vào. [CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

Cùng là shared nhưng ý nghĩa `state` trái ngược cũng có thể hợp lệ: với một bộ giới hạn, `0` có thể nghĩa là hết giấy phép; với latch, `0` nghĩa là đã đủ điều kiện để tất cả đi tiếp. Không được đoán hành vi từ giá trị số mà chưa đọc bất biến của công cụ.

## Các đường acquire/release trong AQS

AQS phân biệt phương thức điều phối với phương thức lớp con cung cấp:

| Chế độ | Phương thức điều phối tiêu biểu | Móc quy tắc của lớp con |
| --- | --- | --- |
| Độc quyền, lấy | `acquire(arg)`, `acquireInterruptibly(arg)`, `tryAcquireNanos(arg, nanos)` | `tryAcquire(arg)` |
| Độc quyền, nhả | `release(arg)` | `tryRelease(arg)` |
| Chia sẻ, lấy | `acquireShared(arg)`, `acquireSharedInterruptibly(arg)`, `tryAcquireSharedNanos(arg, nanos)` | `tryAcquireShared(arg)` |
| Chia sẻ, nhả | `releaseShared(arg)` | `tryReleaseShared(arg)` |

Các móc thử lấy không phải nơi tự đặt vòng chờ bằng `sleep`, tự park hay gọi một thao tác mạng. Chúng cần kiểm tra/cập nhật trạng thái an toàn và trả kết quả cho phần điều phối. Lớp con chỉ cần hỗ trợ những móc phù hợp với chế độ thực sự dùng. [Hợp đồng mở rộng AQS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

### Đọc đúng giá trị trả về

- `tryAcquire` trả `true` khi đã lấy quyền; `false` khi chưa lấy được.
- `tryRelease` trả `true` khi đã giải phóng đủ để luồng chờ có cơ hội đi tiếp. Với một khóa tái nhập, nhả bớt số lần giữ có thể là thao tác hợp lệ nhưng vẫn trả `false` vì chưa nhả hết.
- `tryAcquireShared` trả số âm khi thất bại; `0` khi thành công nhưng yêu cầu chia sẻ tiếp theo không thể thành công; số dương khi thành công và yêu cầu chia sẻ tiếp theo có thể thành công.
- `tryReleaseShared` trả `true` nếu việc nhả có thể giúp một yêu cầu chia sẻ đang chờ tiến triển.

Điểm dễ sai nhất là **`tryAcquireShared` trả `0` vẫn là thành công**. Với một thiết kế đếm giấy phép, lấy giấy phép cuối cùng có thể để lại `0` giấy phép nhưng yêu cầu hiện tại đã được đáp ứng.

Giá trị dương cũng không cam kết số luồng nhất định sẽ chạy ngay. Sau khi được tạo cơ hội, luồng tiếp theo vẫn phải kiểm tra trạng thái; một luồng khác có thể đã thay đổi trạng thái trước nó. Cơ chế chia sẻ có thể truyền khả năng tiến triển cho các yêu cầu kế tiếp, nhưng chính quy tắc vẫn quyết định ai lấy được. [Mã nguồn AQS trong OpenJDK 25](https://raw.githubusercontent.com/openjdk/jdk/jdk-25%2B36/src/java.base/share/classes/java/util/concurrent/locks/AbstractQueuedSynchronizer.java)

Không nhầm `tryAcquireShared` là móc `protected` trong lớp con AQS với `Semaphore.tryAcquire()` là API `public` trả boolean. Tên gần giống nhau nhưng mức trừu tượng và kiểu kết quả khác nhau.

## Một hàng đợi không đồng nghĩa một chính sách cố định

Trong AQS, yêu cầu exclusive và shared có thể cùng dùng cơ chế hàng đợi đồng bộ. Tên chế độ không có nghĩa tự có hai hàng độc lập và cũng không có nghĩa shared được ưu tiên vượt mọi yêu cầu độc quyền.

Thử lấy thành công ngay, chờ có ngắt, chờ có thời hạn và công bằng là các lựa chọn khác với exclusive/shared. `ReentrantLock` có cấu hình công bằng, nhưng `tryLock()` không thời hạn không tuân theo cấu hình đó. Ngay cả khóa công bằng cũng không quyết định thứ tự hệ điều hành cấp CPU cho các luồng. [Công bằng trong ReentrantLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)

Ở tầng chờ, `LockSupport` chỉ cung cấp khả năng park/unpark; một lần trở về từ park không tự cấp quyền truy cập. Luồng có thể thức do ngắt hoặc thức dậy không do tín hiệu mong đợi. Vì vậy cơ chế đồng bộ phải kiểm tra lại điều kiện. Đây là lý do không thể suy luận rằng một luồng được đánh thức thì chắc chắn đã sở hữu khóa hoặc có giấy phép. [LockSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html)

## Minh chứng Java: tái nhập, giới hạn và quyền nhả

Ví dụ Java 17+ dùng hai công cụ chuẩn để quan sát hợp đồng. Không tự tạo hàng đợi AQS và không phụ thuộc lịch chạy nhờ `sleep`.

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.locks.ReentrantLock;

public class AcquireModesDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        boolean[] otherAcquired = new boolean[1];

        lock.lock();
        try {
            Thread contender = new Thread(() -> {
                boolean acquired = lock.tryLock();
                otherAcquired[0] = acquired;
                if (acquired) {
                    lock.unlock();
                }
            });
            contender.start();
            contender.join();
            System.out.println("exclusive.other=" + otherAcquired[0]);

            lock.lock();
            try {
                System.out.println("exclusive.holdCount=" + lock.getHoldCount());
            } finally {
                lock.unlock();
            }
        } finally {
            lock.unlock();
        }

        Semaphore permits = new Semaphore(2);
        permits.acquire(2);
        System.out.println("shared.remaining=" + permits.availablePermits());
        System.out.println("shared.extra=" + permits.tryAcquire());

        Thread releaser = new Thread(permits::release);
        releaser.start();
        releaser.join();
        System.out.println("shared.afterOtherRelease=" + permits.availablePermits());

        boolean acquiredAgain = permits.tryAcquire();
        System.out.println("shared.acquireAgain=" + acquiredAgain);
        System.out.println("shared.afterAcquire=" + permits.availablePermits());

        permits.release(2);
        System.out.println("shared.restored=" + permits.availablePermits());
    }
}
```

Lưu thành `AcquireModesDemo.java`, rồi chạy:

```shell
javac AcquireModesDemo.java
java AcquireModesDemo
```

Stdout khi chương trình không bị ngắt từ bên ngoài:

```text
exclusive.other=false
exclusive.holdCount=2
shared.remaining=0
shared.extra=false
shared.afterOtherRelease=1
shared.acquireAgain=true
shared.afterAcquire=0
shared.restored=2
```

### Vì sao kết quả xác định?

Trong phần khóa, `main` giữ khóa trong toàn bộ lúc luồng `contender` gọi `tryLock()`. Do đó luồng kia thất bại ngay; nó không gọi một phương thức chờ lấy khóa. `main` đợi `contender` kết thúc rồi mới in kết quả. Việc lấy lại khóa của chính `main` tăng số lần giữ lên hai, cho thấy tái nhập vẫn tương thích với độc quyền.

Trong phần semaphore, `main` lấy hết hai giấy phép trước khi thử lấy thêm; lần thử thêm trả `false`. Sau đó một luồng khác trả một giấy phép dù nó chưa từng lấy từ semaphore này. `join()` bảo đảm luồng ấy đã hoàn tất trước khi `main` quan sát số còn sẵn. Lần thử kế tiếp tiêu thụ giấy phép vừa được trả, đưa số còn sẵn về `0`.

Phép cân bằng trong ví dụ là: bắt đầu `2`, lấy `2`, trả `1`, lấy `1`, trả `2`, kết thúc `2`. Việc luồng khác trả giấy phép chỉ nhằm minh họa không có sở hữu; trong chương trình nghiệp vụ, việc chuyển trách nhiệm trả giấy phép cần được thiết kế rõ để không trả thiếu hoặc trả hai lần.

`boolean[] otherAcquired` có thể được đọc sau `join()` mà không cần thêm `volatile` vì hoàn tất luồng và join tạo quan hệ thứ tự nhìn thấy dữ liệu. Đây không phải lý do để đọc mảng ấy tùy ý khi tác vụ còn đang chạy. [JLS, happens-before](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5)

Không thay `lock.tryLock()` trong `contender` bằng `lock.lock()` rồi giữ nguyên `main` chờ `join()` trong vùng khóa: lúc đó `main` đợi luồng con kết thúc, luồng con lại đợi `main` nhả khóa. Chính việc dùng API thử không chờ làm ví dụ tránh vòng phụ thuộc đó.

## Một công cụ có thể kết hợp cả hai chế độ

`ReentrantReadWriteLock` kết hợp quyền đọc chia sẻ và quyền ghi độc quyền. Nhiều bên đọc có thể cùng giữ quyền khi giao thức cho phép; bên ghi cần loại trừ bên đọc khác và bên ghi khác. Không có nghĩa cứ là yêu cầu đọc thì được vượt qua mọi bên ghi đang chờ: chính sách công bằng còn ảnh hưởng quyết định cấp quyền. [ReentrantReadWriteLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html)

Trong công cụ này, luồng đang giữ quyền ghi có thể lấy quyền đọc rồi nhả quyền ghi để hạ cấp. Luồng đang giữ quyền đọc không thể đơn giản chờ nâng lên quyền ghi trong khi vẫn giữ đọc; phải nhả đọc và xử lý khoảng thay đổi trạng thái trước khi lấy ghi. `Condition` chỉ được hỗ trợ ở khóa ghi; `readLock().newCondition()` ném `UnsupportedOperationException`. Những đặc điểm đó thuộc hợp đồng của công cụ cụ thể, không phải lời hứa chung cho mọi công cụ shared/exclusive. [Quy tắc đọc/ghi và Condition](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html)

## Cách chọn và lỗi cần tránh

| Nhu cầu | Hướng chọn | Điều cần kiểm tra |
| --- | --- | --- |
| Sửa dữ liệu mà chỉ một luồng được vào | Khóa độc quyền như `ReentrantLock` | Cùng một khóa có bảo vệ mọi truy cập liên quan không? |
| Cho tối đa N tác vụ dùng tài nguyên | `Semaphore` | Mỗi yêu cầu lấy/trả bao nhiêu; ai chịu trách nhiệm trả? |
| Đợi một nhóm công việc hoàn thành một lần | `CountDownLatch` | Bộ đếm có phản ánh đúng số mốc hoàn thành không? |
| Nhiều đọc, ghi phải loại trừ | Xem xét khóa đọc/ghi | Có đúng là phần giữ quyền đọc không sửa trạng thái chung không? |

Không dùng số giấy phép hiện tại làm quyết định theo kiểu `if (availablePermits() > 0) acquire()`: luồng khác có thể lấy giữa hai thao tác. Khi cần thử ngay, dùng API thử lấy nguyên tử theo hợp đồng công cụ.

Không xem semaphore một giấy phép là hoàn toàn tương đương khóa tái nhập. Cùng giới hạn một quyền có thể tạo loại trừ, nhưng khác biệt về sở hữu, tái nhập và kiểm tra nhả sai vẫn quan trọng. Không xem nhiều người đọc là quyền cho phép họ sửa dữ liệu chung.

Để tự kiểm tra kiến thức:

1. Một yêu cầu shared để lại `0` giấy phép sau khi lấy: yêu cầu đó thành công hay thất bại? **Thành công**; chỉ yêu cầu tiếp theo mới thiếu giấy phép trong tình huống này.
2. T1 giữ khóa tái nhập hai lần và mới nhả một lần: T2 đã được vào chưa? **Chưa**, vì vẫn còn một lần giữ.
3. Luồng chưa lấy semaphore có được gọi `release()` không? **Có theo API**, nhưng tính đúng đắn của số giấy phép vẫn là trách nhiệm giao thức ứng dụng.
4. Có phải shared luôn tốt hơn exclusive về hiệu năng? **Không**; trước hết phải đúng quy tắc truy cập, sau đó mới đo tải thực tế.

Muốn giải thích một công cụ dựa trên AQS, hãy nói được quyền đang cấp là gì, khi nào nó khả dụng, có bị tiêu thụ không và ai được nhả. Khi bốn câu hỏi đó rõ, sự khác biệt giữa độc quyền và chia sẻ sẽ gắn trực tiếp với hành vi chương trình.
