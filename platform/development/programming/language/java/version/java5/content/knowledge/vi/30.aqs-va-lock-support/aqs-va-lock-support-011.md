# Kiểm tra hợp đồng bộ nhớ, tiến triển và hủy chờ

## Khái niệm: đúng kết quả cuối chưa đủ để kết luận bộ đồng bộ đúng

Một công cụ dựa trên AQS có thể trả kết quả đúng trong ví dụ đơn giản nhưng vẫn có lỗi khó thấy: luồng vừa lấy quyền đọc dữ liệu cũ, một người chờ bị bỏ lại sau khi tài nguyên đã rảnh, hoặc người đã hủy vẫn làm mất một giấy phép. Do đó cần kiểm tra riêng **hợp đồng bộ nhớ**, **khả năng tiến triển** và **hủy chờ**.

- **Hợp đồng bộ nhớ**: sau thao tác đồng bộ thành công, luồng nào phải nhìn thấy những ghi nào?
- **Tiến triển**: khi điều kiện đã cho phép, yêu cầu hợp lệ còn lại có tiếp tục được không?
- **Hủy chờ**: khi bị ngắt hoặc hết hạn, yêu cầu có rời đường chờ đúng cách, không chiếm nhầm quyền và không cản người khác không?

Ba mặt này bổ sung cho nhau. Thử hàng triệu lần mà không treo chưa chứng minh công bố dữ liệu đúng; một bài đọc được giá trị mong đợi chưa kiểm tra việc hủy nút chờ; kết thúc đúng thời gian chưa chứng minh không có hai luồng cùng giữ quyền độc quyền.

## Bắt đầu từ hợp đồng có thể quan sát

Trước khi viết bài kiểm tra, ghi rõ ý nghĩa trạng thái, điều kiện cấp quyền, ai được giải phóng, API có ngắt/thời hạn và kết quả nào hợp lệ. Không dùng thứ tự thực thi tình cờ của một lần chạy làm đặc tả.

| Mặt kiểm tra | Ví dụ mệnh đề cần xác minh |
| --- | --- |
| An toàn truy cập | Tối đa một luồng ở vùng độc quyền; số giấy phép không sai bất biến |
| Bộ nhớ | Ghi trước nhả khóa được thấy sau lấy thành công đúng khóa |
| Tiến triển | Sau khi nhả quyền, một yêu cầu hợp lệ còn lại có thể hoàn tất |
| Ngắt | API có ngắt báo hủy đúng; người hủy không coi như đã lấy quyền |
| Hết hạn | Yêu cầu không được cấp quyền báo thất bại; tài nguyên vẫn dùng được sau đó |
| Sở hữu | Luồng không sở hữu không được nhả một khóa yêu cầu sở hữu |
| Condition | Chờ nhả hoàn toàn, trở lại với quyền đúng và kiểm tra lại điều kiện |

AQS cung cấp các đường lấy/nhả và cơ chế chờ; lớp con vẫn phải định nghĩa các móc trạng thái đúng và chọn đường chờ phù hợp. Kết quả build thành công chỉ kiểm tra được việc tạo chương trình, không thay thế những hợp đồng đồng thời này. [Hợp đồng mở rộng AQS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

## Kiểm tra bộ nhớ: phải chỉ ra đường happens-before

Với một triển khai `Lock`, lấy và nhả thành công phải có ngữ nghĩa bộ nhớ tương ứng với monitor. Một thao tác thử lấy thất bại không được xem là đã có hiệu ứng đồng bộ của một lần lấy thành công. [Lock: Memory Synchronization](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html)

Một kịch bản công bố dữ liệu phù hợp với khóa là:

```text
Bên ghi đang giữ khóa
    ghi payload = 42
    nhả khóa
        -> bên đọc lấy thành công cùng khóa
           đọc payload và ghi lại kết quả quan sát
```

Bài kiểm tra phải phân biệt **giá trị mong đợi theo hợp đồng** với **giá trị hay xuất hiện trên máy hiện tại**. Theo đường trên, đọc `0` là vi phạm. Nếu không có quan hệ buộc bên đọc chạy sau lần ghi, đọc `0` có thể chỉ là bên đọc đã vào trước, không phải lỗi bộ nhớ.

### Tránh đồng bộ phụ che mất lỗi

Giả sử muốn kiểm tra việc nhả/lấy khóa công bố payload, nhưng lại ghi payload rồi mới gọi `countDown()` trên một latch mà bên đọc đợi trước khi đọc. Latch đó có thể tự tạo đường công bố dữ liệu, khiến bài kiểm tra vẫn qua ngay cả khi khóa đang thử có lỗi.

Những cơ chế cần rà soát gồm `volatile`, biến nguyên tử, latch, hàng đợi an toàn luồng, khởi động luồng, `join` và cả lời gọi ghi log có đồng bộ. Chúng không xấu; vấn đề là chúng có vô tình tạo thêm đường **từ lần ghi đang thử đến lần đọc đang thử** hay không.

Ở ví dụ phía dưới, luồng đọc được khởi động **trước** khi payload được ghi. Latch báo từ bên đọc sang bên ghi rằng nó sắp lấy khóa; latch không nhận một lần công bố payload từ bên ghi. `join` chỉ diễn ra sau khi bên đọc đã ghi kết quả, giúp luồng kiểm tra đọc kết quả đó. Cần vẽ đúng chiều các quan hệ này. [JLS: happens-before, start và join](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5)

`sleep` không tạo hiệu ứng đồng bộ để sửa một phép đọc dữ liệu không an toàn. Nếu bài kiểm tra chỉ qua sau khi thêm ngủ hoặc ghi log, đó là dấu hiệu cần xem lại lịch chạy và đường công bố, không phải bằng chứng thuật toán đã đúng.

## Kiểm tra tiến triển: đặt đúng điều kiện cho phép hoàn tất

Một luồng chưa lấy được khóa khi chủ sở hữu vẫn giữ nó là hành vi đúng. Để kiểm tra tiến triển, phải tạo một mốc mà quyền đã được giải phóng hoặc điều kiện đã đổi, rồi quan sát bên hợp lệ còn lại.

Các kịch bản có giá trị:

- Nhả quyền trước khi bên chờ bắt đầu: bên đến sau phải nhận ra trạng thái đã cho phép, không đợi một tín hiệu sẽ không xuất hiện nữa.
- Nhả khi bên chờ đang chuyển từ kiểm tra sang đăng ký chờ: không được bỏ mất cơ hội tiến triển.
- Có nhiều người chờ và người phía trước hủy: người còn lại vẫn phải có thể giành quyền.
- Với chế độ chia sẻ, cấp đủ điều kiện cho nhiều yêu cầu: việc tiến triển không được dừng vô cớ sau người đầu tiên.

Trong kiểm tra thực nghiệm, dùng giới hạn thời gian để biến tình trạng treo thành thất bại có thể chẩn đoán. Giới hạn đó là ngân sách vận hành của bài kiểm tra; nó không chứng minh một thời hạn toán học cho mọi lịch cấp CPU và mọi môi trường.

Cũng cần tách công bằng và tiến triển. Một khóa không công bằng có thể cho người mới vượt một người chờ mà vẫn đúng đặc tả của nó. Không áp thứ tự FIFO vào mọi công cụ chỉ vì AQS có hàng đợi; chính sách cấp quyền thuộc hợp đồng của công cụ. [AQS và chính sách hàng đợi](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

## Hủy chờ phải kiểm tra cả kết quả và hậu quả

Đối với đường chờ có ngắt, không chỉ xác nhận một `InterruptedException` đã xảy ra. Còn phải xác minh người đó không xử lý như đã sở hữu quyền, tài nguyên không bị mất và một người chờ khác vẫn tiến triển.

Cần ít nhất các vị trí hủy sau:

| Thời điểm | Mục đích kiểm tra |
| --- | --- |
| Cờ ngắt đã đặt trước khi gọi | Kiểm tra ngữ nghĩa ngắt lúc vào API |
| Yêu cầu đang chờ, quyền chưa thể cấp | Tách rõ hủy khỏi một lần lấy thành công |
| Ngắt đua với lần giải phóng | Xác minh kết quả phù hợp với thứ tự thực tế và hợp đồng ưu tiên ngắt |
| Hết hạn khi vẫn chưa đủ điều kiện | Xác minh báo không lấy được quyền và phục hồi trạng thái |
| Hủy xong rồi tiếp tục dùng công cụ | Phát hiện rò giấy phép hoặc hàng đợi không còn hoạt động |

Trong cuộc đua giữa ngắt và giành quyền, không thể coi mọi kết quả thành công hay mọi ngoại lệ đều sai. Phải xem ngắt được phát hiện trước hay sau khi thao tác đã hoàn tất và API cam kết ưu tiên ra sao. Nếu muốn một kết quả hủy xác định, giữ khóa ở bên điều khiển để người thử không thể lấy quyền trong suốt lúc gửi ngắt.

Với `LockSupport.park`, trở về do ngắt không tự ném ngoại lệ và không xóa cờ. Do đó một công cụ tự viết còn phải có chính sách rời chờ hoặc ghi nhận ngắt; nếu chỉ quay lại park với cờ còn đặt, nó có thể chạy vòng lặp tốn CPU. Bài kiểm tra hủy cần phát hiện cả trường hợp không kết thúc và trường hợp quay vòng không làm việc hữu ích. [LockSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html)

## Minh chứng Java: một khung kiểm tra có giới hạn

Chương trình Java 17+ dưới đây dùng `ReentrantLock` làm **mốc tham chiếu hành vi**, minh họa cách đặt kiểm tra công bố dữ liệu, hủy do ngắt, người chờ tiếp theo và hết hạn. Nó chưa phải bộ kiểm chứng toàn bộ AQS và chưa kiểm tra một lớp AQS tự viết nào.

Muốn áp dụng cho một khóa tùy chỉnh, phải điều chỉnh API và cách quan sát hàng đợi đúng khả năng mà khóa đó cung cấp, rồi giữ nguyên các mệnh đề hợp đồng cần xác minh. Không thay đối tượng mà bỏ qua khác biệt về tái nhập, công bằng hay hỗ trợ ngắt.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class SyncContractsCheck {
    static final long LIMIT_MS = 5000;

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static Thread worker(Runnable action) {
        Thread thread = new Thread(action);
        thread.setDaemon(true);
        return thread;
    }

    static void finish(Thread thread) throws InterruptedException {
        thread.join(LIMIT_MS);
        if (thread.isAlive()) {
            thread.interrupt();
            throw new AssertionError("Worker did not finish");
        }
    }

    static void awaitQueued(ReentrantLock lock, Thread thread) {
        long start = System.nanoTime();
        long budget = TimeUnit.MILLISECONDS.toNanos(LIMIT_MS);
        while (!lock.hasQueuedThread(thread)) {
            require(thread.isAlive(), "Worker ended before queue observation");
            require(System.nanoTime() - start < budget, "Queue observation timed out");
            Thread.yield();
        }
    }

    static void checkPublication() throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch attempting = new CountDownLatch(1);
        int[] payload = new int[1];
        int[] seen = new int[1];

        Thread reader = worker(() -> {
            attempting.countDown();
            lock.lock();
            try {
                seen[0] = payload[0];
            } finally {
                lock.unlock();
            }
        });

        lock.lock();
        try {
            reader.start();
            require(attempting.await(LIMIT_MS, TimeUnit.MILLISECONDS),
                    "Reader did not start");
            payload[0] = 42;
        } finally {
            lock.unlock();
        }

        finish(reader);
        require(seen[0] == 42, "Publication contract failed");
        System.out.println("publication=PASS");
    }

    static void checkCancellationAndSuccessor() throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        boolean[] cancelled = new boolean[1];
        boolean[] progressed = new boolean[1];

        Thread cancelledWaiter = worker(() -> {
            try {
                lock.lockInterruptibly();
                try {
                    // Reaching here would fail the expected cancellation result.
                } finally {
                    lock.unlock();
                }
            } catch (InterruptedException expected) {
                cancelled[0] = true;
            }
        });

        Thread successor = worker(() -> {
            try {
                lock.lockInterruptibly();
                try {
                    progressed[0] = true;
                } finally {
                    lock.unlock();
                }
            } catch (InterruptedException unexpected) {
                Thread.currentThread().interrupt();
            }
        });

        lock.lock();
        try {
            cancelledWaiter.start();
            awaitQueued(lock, cancelledWaiter);
            successor.start();
            awaitQueued(lock, successor);
            cancelledWaiter.interrupt();
            finish(cancelledWaiter);
            require(cancelled[0], "Waiter did not report cancellation");
        } finally {
            lock.unlock();
        }

        finish(successor);
        require(progressed[0], "Successor did not acquire after cancellation");
        System.out.println("interruptCancellation=PASS");
        System.out.println("successorProgress=PASS");
    }

    static void checkTimeout() throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        boolean[] timedOut = new boolean[1];

        Thread waiter = worker(() -> {
            try {
                boolean acquired = lock.tryLock(30, TimeUnit.MILLISECONDS);
                timedOut[0] = !acquired;
                if (acquired) {
                    lock.unlock();
                }
            } catch (InterruptedException unexpected) {
                Thread.currentThread().interrupt();
            }
        });

        lock.lock();
        try {
            waiter.start();
            finish(waiter);
            require(timedOut[0], "Timed acquire did not fail while lock was held");
        } finally {
            lock.unlock();
        }
        System.out.println("timedCancellation=PASS");
    }

    public static void main(String[] args) throws InterruptedException {
        checkPublication();
        checkCancellationAndSuccessor();
        checkTimeout();
    }
}
```

Lưu thành `SyncContractsCheck.java`, rồi chạy:

```shell
javac SyncContractsCheck.java
java SyncContractsCheck
```

Stdout trên lần chạy đáp ứng các kiểm tra:

```text
publication=PASS
interruptCancellation=PASS
successorProgress=PASS
timedCancellation=PASS
```

Nếu điều kiện kiểm tra thất bại, chương trình ném `AssertionError` thay vì in đủ bốn dòng. Các kiểm tra dùng hàm `require`, nên không phụ thuộc việc bật tùy chọn `-ea` của JVM.

### Phần công bố dữ liệu đo điều gì?

`main` lấy khóa trước khi khởi động bên đọc. Sau khi bên đọc báo đang chuẩn bị lấy, `main` mới ghi `42` rồi nhả. Vì bên đọc không thể lấy khóa trước lần nhả đó, đọc `42` là kết quả bắt buộc theo hợp đồng của khóa.

Payload cố ý là phần tử `int[]` thông thường để không thêm một biến `volatile` công bố giá trị đó. Bên đọc không in trong đoạn thử; nó lưu kết quả rồi kết thúc. Chỉ sau `join`, `main` mới đánh giá kết quả.

Đây là một lịch kiểm tra có định hướng. Việc nó qua không chứng minh mọi tối ưu JIT, mọi kiến trúc CPU và mọi lịch khác đều đúng; nó chỉ là một trường hợp cần có trong chiến lược rộng hơn.

### Phần hủy và tiến triển đo điều gì?

`main` giữ khóa trong suốt lúc hai yêu cầu được quan sát trên hàng đợi và lúc gửi ngắt cho yêu cầu đầu. Do đó yêu cầu đầu không thể hợp lệ lấy khóa trước khi báo hủy. Sau khi nó kết thúc, `main` nhả khóa rồi yêu cầu thứ hai phải lấy được quyền trong ngân sách kiểm tra.

`hasQueuedThread` ở đây là quan sát phục vụ dựng tình huống kiểm tra, không phải điều kiện cấp quyền của chương trình nghiệp vụ. Quan sát đó cho biết yêu cầu đã có mặt trong quá trình chờ; không chứng minh luồng đã thật sự ngủ trong `park`. Vòng quan sát có giới hạn thời gian, không thay bằng giả định sau một lần `sleep` thì chắc chắn đã xếp hàng. [Các phương thức quan sát của ReentrantLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)

Luồng kiểm tra được đặt daemon để một bản triển khai lỗi không giữ tiến trình sống vô hạn sau khi bài đã ném lỗi. Cờ daemon không được dùng làm tiêu chí thành công: `finish` vẫn kiểm tra từng luồng đã kết thúc, và các biến kết quả phải đúng.

### Phần hết hạn đo điều gì?

`main` tiếp tục giữ khóa trong lúc bên thử gọi `tryLock(30, MILLISECONDS)`. Yêu cầu phải báo không lấy được quyền. Không có kiểm tra kiểu tổng thời gian bắt buộc đúng 30 ms: lịch cấp CPU và chi phí chạy có thể làm kết thúc muộn.

Ngân sách 5 giây trong ví dụ là giới hạn kiểm tra có thể điều chỉnh theo môi trường. Nếu máy quá tải làm hết ngân sách, cần phân loại lại nguyên nhân bằng bằng chứng thực thi; không tự kéo dài vô hạn hoặc khẳng định ngay thư viện sai.

## Mở rộng từ ví dụ thành bộ kiểm tra một bộ đồng bộ

Với khóa độc quyền, có thể thêm bộ đếm số luồng trong vùng tới hạn và xác minh đỉnh không vượt `1`. Với giấy phép chia sẻ, kiểm tra tổng số đang dùng không vượt giới hạn, đồng thời không có giấy phép bị mất sau hủy. Trường hợp tái nhập phải kiểm tra nhả một phần chưa mở quyền cho luồng khác.

Với `ConditionObject`, thêm tình huống đang giữ khóa nhiều lần rồi await: khi chờ phải nhả hoàn toàn, khi trở lại phải khôi phục số lần giữ. Ngắt hoặc hết hạn không được làm bên gọi bỏ qua quyền lấy lại theo hợp đồng. Sau khi đánh thức, biểu thức nghiệp vụ vẫn cần kiểm tra trong `while`; một tín hiệu không chứng minh dữ liệu đã hợp lệ. [ConditionObject](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.ConditionObject.html)

Một ma trận nhỏ nên bao gồm không cạnh tranh, có cạnh tranh, giải phóng trước/sau đăng ký chờ, ngắt trước/trong chờ, hết hạn, nhiều người hủy và một người còn lại. Mỗi hàng cần mệnh đề kết quả rõ và cách dọn tác vụ nếu thất bại.

Đối với cuộc đua khó đặt lịch từ ngoài API, có thể dùng điểm móc kiểm tra trong mã riêng để tạm dừng ở ranh giới cần quan sát. Phải phân tích chính điểm móc đó có thêm quan hệ bộ nhớ che lỗi hay không. Không phụ thuộc tên trường nút AQS của một bản JDK cũ để viết tiêu chí đúng sai cho API hiện tại.

## Khi cần stress và jcstress

Một chương trình `main` hoặc kiểm tra đơn vị có định hướng giúp tái hiện những trình tự biết trước. Khi cần khảo sát các kết quả bộ nhớ hiếm, jcstress của OpenJDK cung cấp bộ khung chạy các tác nhân đồng thời và thu thập kết quả. Trước khi chạy, phải phân loại kết quả nào chấp nhận được, kết quả nào bị cấm và giải thích từ hợp đồng. [Hướng dẫn jcstress](https://github.com/openjdk/jcstress/blob/master/README.md)

Không tự gán mọi giá trị khác kỳ vọng trực giác thành lỗi. Ví dụ dữ liệu không có đường đồng bộ có thể cho nhiều kết quả hợp lệ hơn chương trình tuần tự; các mẫu JMM chính thức giúp luyện cách diễn giải điều đó. [Mẫu jcstress về data race](https://github.com/openjdk/jcstress/blob/master/jcstress-samples/src/main/java/org/openjdk/jcstress/samples/jmm/basic/BasicJMM_01_DataRaces.java)

Chạy nhiều cấu hình, thời lượng đủ lớn và ghi rõ JDK/CPU làm tăng cơ hội phát hiện lỗi; không tìm thấy kết quả cấm vẫn chưa phải chứng minh toán học. Ngược lại, một kết quả bất thường cần được kiểm tra cả thiết kế bài thử, phân loại kết quả và hạ tầng, không quy ngay cho thuật toán.

Stress về tính đúng đắn cũng không thay phép đo hiệu năng. Số lần thao tác lớn không cho biết thông lượng có công bằng, độ trễ có ổn định hay một luồng có bị bỏ đói lâu không.

## Những sai lầm làm kết luận kiểm tra mất giá trị

| Sai lầm | Vì sao kết luận yếu hoặc sai |
| --- | --- |
| `sleep` rồi khẳng định bên kia đã park | Chỉ biết thời gian trôi, chưa có bằng chứng trạng thái cần thử |
| Ghi payload rồi dùng latch khác để phát cho người đọc | Có thể che mất lỗi công bố của công cụ chính |
| Dựa vào log trong các tác nhân | Có thể thêm khóa, đổi lịch và che kết quả hiếm |
| Không có thời hạn ở thao tác chờ của bài kiểm tra | Một lỗi tiến triển làm treo cả bộ kiểm tra |
| Chỉ xác nhận người bị hủy kết thúc | Bỏ sót giấy phép bị rò hoặc người chờ sau bị chặn |
| Kiểm tra thời gian hết hạn bằng số mili giây chính xác | Đánh đồng ngân sách chờ với lịch chạy thực tế |
| Ép thứ tự FIFO lên công cụ không cam kết | Báo lỗi hành vi vốn hợp lệ |
| Một lần qua rồi kết luận mọi lịch đều đúng | Vượt quá phạm vi bằng chứng đã thu được |

Để thực hành, hãy bổ sung vào khung trên một trường hợp ngắt đã đặt từ trước, một trường hợp dùng lại khóa sau khi hết hạn và một phép đo số luồng tối đa trong vùng độc quyền. Trước khi viết, hãy nêu riêng trạng thái ban đầu, tác nhân, mốc phối hợp, kết quả hợp lệ và cách dọn luồng khi thất bại.

Kiểm tra có giá trị khi mỗi kết luận đi kèm một hợp đồng và một kịch bản quan sát rõ: dữ liệu được công bố qua đâu, điều kiện nào đã cho phép tiến triển và hủy chờ có để công cụ tiếp tục hoạt động đúng hay không.
