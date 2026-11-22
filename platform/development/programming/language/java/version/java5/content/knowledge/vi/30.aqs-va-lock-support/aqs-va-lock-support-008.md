# Giấy phép không tích lũy và khả năng unpark trước park

## 1. Vì sao cần một tín hiệu có thể đến trước lúc bắt đầu chờ?

Một luồng làm việc kiểm tra thấy chưa có dữ liệu, rồi chuẩn bị ngủ để nhường CPU. Đúng trong khoảng giữa hai hành động đó, luồng cung cấp dữ liệu đã hoàn thành công việc và gửi tín hiệu đánh thức.

Nếu tín hiệu chỉ có tác dụng khi bên nhận đang ngủ, luồng làm việc có thể ngủ sau khi tín hiệu đã đi qua và không bao giờ được đánh thức nữa. Đây là dạng lỗi bỏ lỡ tín hiệu trong giao thức chờ.

`LockSupport` giải quyết một phần quan trọng của vấn đề bằng một **giấy phép (permit)** gắn với luồng. `unpark(thread)` có thể chuẩn bị giấy phép cho lần `park` tiếp theo ngay cả khi luồng đích chưa bắt đầu chờ.

Tuy nhiên, giấy phép này không phải một bộ đếm công việc. Mỗi luồng chỉ có thể có tối đa một giấy phép đang chờ được dùng. Hiểu đồng thời hai đặc điểm — tín hiệu có thể đến sớm nhưng không tích lũy — là điều kiện để đọc đúng các thuật toán chờ của AQS và tránh tự xây một giao thức đánh thức sai.

Các cơ chế trong bài vẫn áp dụng trong Java hiện đại. Ví dụ dùng Java 17 trở lên, không dùng API nội bộ JVM.

## 2. Mô hình giấy phép có sức chứa một

### 2.1. Hai trạng thái khái niệm

Có thể hình dung mỗi luồng có một ô giấy phép:

| Giá trị khái niệm | Ý nghĩa |
| --- | --- |
| `P = 0` | Chưa có giấy phép chờ được dùng |
| `P = 1` | Có một giấy phép cho một lần chờ |

Đây là mô hình để suy luận, không phải một trường mà chương trình được phép đọc hoặc ghi trực tiếp.

Các chuyển đổi cơ bản:

| Thao tác | Trước | Sau | Ý nghĩa |
| --- | --- | --- | --- |
| `unpark(t)` | `P = 0` | `P = 1` | Cung cấp giấy phép cho t |
| `unpark(t)` | `P = 1` | `P = 1` | Giấy phép đã có, không cộng thêm |
| `park()` khi giấy phép có sẵn | `P = 1` | `P = 0` | Dùng giấy phép và trở về |
| `park()` khi chưa có giấy phép | `P = 0` | Không có phép chuyển thành “số âm” | Có thể phải chờ |

Do `park` còn có thể trở về vì ngắt hoặc thức dậy giả, bảng không có ý nghĩa “P=0 thì chắc chắn ngủ cho đến khi có unpark”. Đó chỉ là phần hành vi gắn với giấy phép.

Theo hợp đồng `LockSupport`, giấy phép không cộng dồn, và việc chờ cần đi cùng biến điều kiện có đồng bộ phù hợp. [Tài liệu LockSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html)

### 2.2. Không tích lũy nghĩa là gì?

Giả sử luồng T chưa thực hiện lần `park` nào trong đoạn xét:

```text
Ban đầu:      P = 0
unpark(T):    P = 1
unpark(T):    P = 1
unpark(T):    P = 1
T gọi park:  dùng giấy phép, P = 0
```

Ba lần `unpark` ở đây không chuẩn bị ba lượt đi qua `park`. Hai tín hiệu sau đã được gộp vào trạng thái “có giấy phép”.

Điều này không có nghĩa “mọi chuỗi ba unpark chỉ có thể làm một park trở về”. Nếu T kịp dùng giấy phép giữa các lần gửi, một lần gửi sau có thể cung cấp giấy phép mới:

```text
unpark(T) → T park, dùng giấy phép
unpark(T) → T park, dùng giấy phép
```

Sức chứa tối đa là một **tại một thời điểm**, không phải giới hạn tổng số lần luồng được đánh thức trong suốt chương trình.

### 2.3. Giấy phép thuộc luồng, không thuộc blocker

`park(blocker)` cho phép ghi nhận đối tượng mô tả lý do chờ. Hai lời gọi `park(lockA)` và `park(lockB)` trên cùng một luồng không có hai kho giấy phép độc lập.

Nếu một phần khác trên cùng luồng thực hiện `park` và dùng mất giấy phép, lần `park` mà ta đang quan tâm không được hưởng một giấy phép riêng. Vì vậy, không nên coi `unpark` như gửi một thông điệp có địa chỉ “đúng lần chờ này”.

Tham số blocker hữu ích khi chẩn đoán; nó không biến một giấy phép theo luồng thành giấy phép theo đối tượng khóa.

## 3. Unpark trước park hoạt động như thế nào?

### 3.1. Đến sớm nhưng vẫn còn tác dụng

Với luồng đã chạy và còn sống:

```text
Luồng báo hiệu                    Luồng chờ T

unpark(T) → P của T thành 1
                                  ... chưa gọi park ...
                                  park()
                                  dùng P=1, trở về
```

Luồng gửi không cần chờ T chuyển sang trạng thái `WAITING` rồi mới gọi `unpark`. Việc cố đồng bộ bằng cách liên tục kiểm tra `Thread.getState()` vừa không cần thiết vừa tạo ra thêm một quan sát có thể thay đổi ngay sau khi kiểm tra.

Không mở rộng kết luận thành “unpark trước khi start cũng chắc chắn có hiệu lực”. Hợp đồng không bảo đảm hiệu lực của `unpark` đối với luồng chưa được khởi động. Nếu sự kiện có thể xảy ra trước khi luồng bắt đầu chạy, hãy lưu sự kiện trong trạng thái bền vững của giao thức, để luồng đọc được khi khởi động.

### 3.2. Tín hiệu đến đúng khoảng giữa kiểm tra và ngủ

Giao thức chờ thường có hình dạng:

```java
// Đoạn minh họa: ready phải có bảo đảm nhìn thấy giữa các luồng.
while (!ready) {
    LockSupport.park(blocker);
}
```

Xét trường hợp khó:

1. T đọc `ready == false`.
2. Bên cung cấp đặt `ready = true`.
3. Bên cung cấp gọi `unpark(T)`.
4. T mới gọi `park(blocker)`.

Giấy phép có sẵn giúp lần chờ ở bước 4 trở về. T lặp lại kiểm tra và nhìn thấy `ready == true` theo giao thức đồng bộ của biến đó.

Như vậy, `unpark` đến sớm không nhất thiết bị mất chỉ vì bên nhận chưa kịp ngủ. Nhưng toàn bộ giao thức vẫn cần cập nhật điều kiện đúng thứ tự, biết đúng luồng phải đánh thức và tránh một thao tác chờ trung gian dùng mất giấy phép.

### 3.3. Không cần giấy phép nếu điều kiện đã đủ

Nếu T kiểm tra và thấy `ready == true` ngay từ đầu, nó không cần `park`. Một giấy phép còn dư không làm sai điều kiện nghiệp vụ; nó chỉ có thể khiến một lần chờ sau trở về sớm hơn dự kiến.

Đây là một lý do quan trọng khiến thuật toán không được suy luận “park trở về nghĩa là đúng sự kiện tôi chờ vừa xảy ra”. Luồng có thể dùng một giấy phép được cung cấp từ trước, thậm chí phục vụ một mục đích chờ khác.

## 4. Giấy phép đánh thức và dữ liệu phải được lưu riêng

### 4.1. Tín hiệu không chứa số lượng hay nội dung công việc

Giả sử luồng sản xuất tạo ba công việc rồi gọi `unpark(worker)` ba lần. Nếu worker chưa dùng giấy phép giữa các lần gửi, nó chỉ giữ một giấy phép chờ.

Nếu worker xử lý đúng một công việc mỗi lần `park` trở về, nó có thể xử lý việc đầu rồi ngủ trong khi hai việc còn lại vẫn chưa được xử lý. Lỗi nằm ở việc dùng số lần trở về của `park` thay cho số công việc thật.

Cách thiết kế đúng là:

- Lưu công việc vào một hàng đợi an toàn luồng.
- Dùng tín hiệu để nhắc worker kiểm tra hàng đợi.
- Worker xử lý theo trạng thái hàng đợi, không theo số tín hiệu đã nhận.

Trong mã ứng dụng, `BlockingQueue` thường đã cung cấp cả việc lưu phần tử và cơ chế chờ, tránh nhu cầu ghép hàng đợi riêng với `LockSupport`. [Tài liệu BlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

### 4.2. “Có thể tiếp tục” phải là một điều kiện có đồng bộ

Một cặp trường thông thường:

```java
// Ví dụ sai nếu hai luồng truy cập mà không có giao thức đồng bộ khác.
int value;
boolean ready;
```

không trở nên an toàn chỉ vì luồng ghi gọi `unpark` và luồng đọc gọi `park`. Đừng dựa vào các thao tác đó như một hợp đồng công bố mọi truy cập không volatile.

Với sự kiện một lần, có thể ghi dữ liệu trước rồi công bố cờ bằng `volatile` hoặc `AtomicBoolean`. Luồng chờ đọc cờ theo cùng giao thức trước khi đọc dữ liệu:

```java
// Đoạn minh họa cho một lần công bố, một bên ghi.
value = 42;
ready.set(true);           // AtomicBoolean.set
LockSupport.unpark(worker);
```

`AtomicBoolean.set` và `get` có hiệu ứng bộ nhớ tương ứng với ghi/đọc volatile. Chúng tạo nền tảng công bố trạng thái; `unpark` giúp bên chờ có cơ hội quay lại kiểm tra. [Tài liệu AtomicBoolean](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html)

Không tự đổi sang `getPlain` hoặc một truy cập yếu hơn rồi vẫn giữ nguyên lập luận. Mỗi cách truy cập có hợp đồng bộ nhớ riêng.

### 4.3. Ghi điều kiện trước, đánh thức sau

Trình tự này sai với một vòng chờ không có cơ chế sửa chữa khác:

```text
Bên báo hiệu: unpark(T)
T:            park trở về
T:            đọc ready vẫn false
T:            gọi park lần nữa
Bên báo hiệu: ready = true
Bên báo hiệu: không gửi thêm tín hiệu
```

T có thể ngủ sau khi đã dùng giấy phép duy nhất. Đặt điều kiện thành đúng trước rồi mới đánh thức, để mỗi lần đánh thức tương ứng với một cơ hội nhìn thấy trạng thái đã được công bố.

## 5. Vì sao một lần park trở về không chứng minh đã có sự kiện?

Một lần chờ có thể trở về do:

- Giấy phép đã có sẵn từ trước.
- Một luồng gọi `unpark` trong lúc chờ.
- Luồng hiện tại bị ngắt.
- Hết khoảng chờ với phiên bản có thời hạn.
- Thức dậy giả (spurious return).

Không có giá trị trả về của `park()` cho biết trường hợp nào vừa xảy ra. Phải kiểm tra lại điều kiện thật và chính sách ngắt/thời hạn của thuật toán.

Dùng `if (!ready) park()` rồi đọc dữ liệu ngay là sai: một lần trở về không bảo đảm `ready` đã đúng.

Với một thuật toán cho phép hủy:

```java
// Đoạn minh họa.
while (!ready.get()) {
    if (Thread.currentThread().isInterrupted()) {
        throw new InterruptedException();
    }
    LockSupport.park(blocker);
}
```

Khác với một số API ném `InterruptedException`, `park` không tự ném ngoại lệ này và không xóa trạng thái ngắt khi trở về. Nếu bỏ qua trạng thái ngắt rồi gọi `park` liên tục, các lần chờ có thể trở về ngay, làm vòng lặp tiêu tốn CPU. Thuật toán phải quyết định thoát, truyền tín hiệu hoặc xử lý ngắt theo hợp đồng đã định.

## 6. Ví dụ hoàn chỉnh: giấy phép đến sớm và công bố dữ liệu một lần

Chương trình có ba phần:

1. Luồng main cấp hai giấy phép cho chính nó trước một lần `park`. Vì main đang chạy, không có vấn đề gọi `unpark` trên luồng chưa start.
2. Main gọi thêm một lần `parkNanos` có thời hạn. Không in hoặc khẳng định số mili giây đã ngủ.
3. Một luồng chờ đọc dữ liệu dựa trên cờ `AtomicBoolean`; main có thể gửi tín hiệu thừa nhưng chỉ một lần công bố giá trị. Cuối cùng, chương trình đối chiếu với semaphore có đếm.

Tạo tệp `PermitDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.LockSupport;

public class PermitDemo {
    static final class Slot {
        int value;
        final AtomicBoolean ready = new AtomicBoolean(false);
    }

    static int awaitPayload(Slot slot, long timeoutNanos)
            throws InterruptedException, TimeoutException {
        long started = System.nanoTime();
        while (!slot.ready.get()) {
            if (Thread.currentThread().isInterrupted()) {
                throw new InterruptedException("consumer interrupted");
            }
            long remaining = timeoutNanos - (System.nanoTime() - started);
            if (remaining <= 0) {
                throw new TimeoutException("payload not published");
            }
            LockSupport.parkNanos(slot, remaining);
        }
        return slot.value;
    }

    public static void main(String[] args) throws Exception {
        Thread current = Thread.currentThread();

        LockSupport.unpark(current);
        LockSupport.unpark(current);
        LockSupport.park(PermitDemo.class);
        System.out.println("preissuedParkReturned=true");

        LockSupport.parkNanos(
                PermitDemo.class, TimeUnit.MILLISECONDS.toNanos(20));
        System.out.println("secondTimedParkReturned=true");

        Slot slot = new Slot();
        CountDownLatch consumerStarted = new CountDownLatch(1);
        AtomicReference<Integer> received = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread consumer = new Thread(() -> {
            consumerStarted.countDown();
            try {
                received.set(awaitPayload(
                        slot, TimeUnit.SECONDS.toNanos(5)));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                failure.set(e);
            } catch (TimeoutException e) {
                failure.set(e);
            }
        }, "payload-consumer");

        consumer.start();
        try {
            if (!consumerStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("consumer did not start");
            }

            // Redundant wake-up hints are not payload publications.
            LockSupport.unpark(consumer);
            LockSupport.unpark(consumer);

            slot.value = 42;
            slot.ready.set(true);
            LockSupport.unpark(consumer);

            consumer.join(6_000);
            if (consumer.isAlive()) {
                throw new IllegalStateException("consumer did not finish");
            }
            if (failure.get() != null) {
                throw new IllegalStateException(
                        "consumer failed", failure.get());
            }
            System.out.println("payload=" + received.get());
        } finally {
            consumer.interrupt();
            consumer.join(2_000);
            if (consumer.isAlive()) {
                throw new IllegalStateException("cleanup incomplete");
            }
        }

        Semaphore counted = new Semaphore(0);
        counted.release();
        counted.release();
        counted.acquire();
        counted.acquire();
        System.out.println("semaphoreAfterTwoAcquires="
                + counted.availablePermits());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 PermitDemo.java
java PermitDemo
```

Stdout trong điều kiện chạy thông thường:

```text
preissuedParkReturned=true
secondTimedParkReturned=true
payload=42
semaphoreAfterTwoAcquires=0
```

Chỉ main in kết quả nên thứ tự stdout ổn định. Một môi trường bị treo lâu vẫn có thể làm các bước có thời hạn kết thúc bằng ngoại lệ.

### 6.1. Không suy ra điều gì từ dòng secondTimedParkReturned?

Dòng đó chỉ chứng minh lời gọi có thời hạn đã trở về. Nó không chứng minh lần chờ thứ hai đã ngủ đủ 20 mili giây, và cũng không chứng minh còn một giấy phép thứ hai.

Theo mô hình, hai `unpark` liên tiếp trước lần chờ đầu chỉ lưu tối đa một giấy phép. Nhưng một lần chờ tiếp theo vẫn có thể trở về sớm do nguyên nhân khác. Muốn giải thích tính không tích lũy, phải dựa vào hợp đồng giấy phép, không dựa vào một con số đo thời gian trong một lần chạy.

Cũng không nên thay `parkNanos` thứ hai bằng `park()` vô thời hạn rồi xem chương trình có “treo đúng như mong đợi” hay không. Nó có thể treo, và một lần thức dậy giả cũng có thể làm kết quả thử nghiệm bị hiểu sai.

### 6.2. Vì sao payload luôn dựa trên cờ, không dựa trên tín hiệu?

Hai lần `unpark` thừa có thể xảy ra trước, trong hoặc sau một lần chờ của consumer. Mã không cần đếm chúng. Nếu consumer thức dậy mà cờ còn `false`, nó tiếp tục vòng kiểm tra.

Main ghi `value` trước khi đặt `ready` thành `true`. Consumer chỉ trả `value` sau khi đọc được cờ đúng bằng `AtomicBoolean.get()`. Chính giao thức công bố đó làm dữ liệu sẵn sàng; tín hiệu chỉ tránh phải chờ thụ động đến hết thời hạn.

Nếu main đã công bố xong trước khi consumer kiểm tra lần đầu, consumer bỏ qua việc park và đọc giá trị. Nếu tín hiệu đến vào khe giữa kiểm tra và park, giấy phép cho phép lần chờ trở về. Nếu có lần trở về không liên quan, vòng lặp kiểm tra lại vẫn giữ tính đúng.

### 6.3. Vì sao không đặt ready về false để dùng lại ngay?

Ví dụ là một lần công bố và một lần đọc. Tái sử dụng cặp `value/ready` cho nhiều vòng đòi hỏi giao thức bổ sung: ai được ghi vòng kế tiếp, người đọc đã dùng xong chưa và làm sao phân biệt hai thế hệ dữ liệu.

Đặt lại cờ tùy ý có thể làm bên đọc bỏ lỡ một lượt hoặc đọc dữ liệu đã bị ghi đè. Khi cần nhiều phần tử, dùng hàng đợi; khi cần nhiều vòng phối hợp, chọn bộ đồng bộ phù hợp thay vì kéo dài ví dụ một lần thành một giao thức chưa được chứng minh.

## 7. So sánh với semaphore, hàng đợi và điều kiện

| Nhu cầu | Nơi lưu ý nghĩa thật | Cơ chế thích hợp |
| --- | --- | --- |
| Nhắc một luồng kiểm tra lại điều kiện | Biến điều kiện hoặc cấu trúc dữ liệu an toàn luồng | `LockSupport` ở tầng xây bộ đồng bộ |
| Tích lũy số quyền có thể nhận | Bộ đếm giấy phép | `Semaphore` |
| Giữ từng công việc và nội dung của nó | Các phần tử hàng đợi | `BlockingQueue` |
| Chờ một điều kiện gắn với khóa | Dữ liệu được khóa bảo vệ | `Condition` |
| Đợi một sự kiện một lần | Trạng thái sự kiện | `CountDownLatch`, future hoặc cơ chế tương đương |

Semaphore có thể giữ hai giấy phép sau hai lần `release()` và cho hai lần `acquire()` thành công khi không có bên khác cùng nhận. Nó vẫn không lưu nội dung hai công việc; muốn giữ nội dung phải có cấu trúc dữ liệu tương ứng. [Tài liệu Semaphore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Semaphore.html)

Điểm khác biệt nằm ở hợp đồng lưu trạng thái, không nằm ở việc API nào “đánh thức mạnh hơn”. Nhiều primitive cấp cao có thể dùng các kỹ thuật chờ ở tầng dưới, nhưng chúng bổ sung trạng thái và quy tắc để cung cấp ý nghĩa mà một giấy phép đơn lẻ không có.

## 8. Quan hệ với AQS: trạng thái quyết định, đánh thức chỉ tạo cơ hội

Trong một khóa dựa trên AQS, quyền đi vào vùng tới hạn phụ thuộc việc nhận thành công trạng thái đồng bộ. Luồng vừa được đánh thức phải thử nhận lại; nó không đương nhiên sở hữu khóa.

Nếu một luồng mới giành trạng thái trước, luồng vừa thức dậy có thể phải chờ tiếp. Một giấy phép còn dư chỉ làm một lần chờ trở về nhanh; nó không cho phép bỏ qua kiểm tra và thao tác nguyên tử quyết định quyền nhận.

Với semaphore dựa trên AQS, số giấy phép có thể tích lũy nằm trong trạng thái của semaphore, không phải trong các giấy phép `LockSupport` của từng luồng. Hai lớp trạng thái này không được đánh đồng:

```text
Trạng thái cấp cao:  còn bao nhiêu quyền, có dữ liệu hay chưa, khóa đang rảnh?
Giấy phép theo luồng: một lần park có thể phải chờ hay có thể trở về ngay?
```

Khi đọc mã AQS, đừng đếm số lần `unpark` để suy ra số lượt nhận khóa. Hãy tìm chỗ kiểm tra trạng thái, chỗ giành quyền nguyên tử và điều kiện phải quay lại hàng đợi.

## 9. Những giới hạn phải giữ khi thiết kế giao thức thấp tầng

### 9.1. Đăng ký người chờ trước khi có thể bị bỏ qua

Bên báo hiệu phải biết đúng luồng cần đánh thức. Nếu một thiết kế đặt tham chiếu người chờ quá muộn, có thể xảy ra: bên báo hiệu kiểm tra thấy “chưa ai chờ”, không đánh thức; sau đó bên chờ mới đăng ký rồi ngủ.

Một giao thức thường cần đăng ký trước, kiểm tra lại điều kiện sau khi đăng ký, rồi mới chờ. Khi thay thế người chờ hoặc hủy chờ cũng phải tránh xóa nhầm tham chiếu của một lượt khác.

Ví dụ trong bài chỉ có một consumer đã được main giữ tham chiếu trực tiếp, nên không triển khai một danh sách đăng ký chung.

### 9.2. Không chen thao tác chờ khác vào khe nhạy cảm

Vì giấy phép thuộc luồng, một lời gọi trung gian có thể dùng `park` và tiêu thụ giấy phép. Các đường tải/khởi tạo lớp hoặc cơ chế đồng bộ khác có thể tạo hành vi chờ không hiển nhiên khi chỉ nhìn một đoạn mã ngắn.

Do đó, thuật toán thấp tầng phải giữ đường từ kiểm tra điều kiện đến `park` ngắn và kiểm soát được. Không chèn log tùy ý, chờ khóa khác hoặc gọi hàm có thể chặn trong khe đó rồi vẫn giữ nguyên lập luận “unpark sớm luôn còn giấy phép cho đúng park này”.

Việc tải sẵn những lớp cần thiết có thể giảm một rủi ro cụ thể; nó không thay thế chứng minh toàn bộ giao thức. Đây cũng là lý do nên dùng AQS và bộ đồng bộ có sẵn khi chúng đáp ứng nhu cầu.

### 9.3. Dùng một ngân sách thời gian chung cho các lần chờ lại

Nếu mỗi lần thức dậy giả đều gọi `parkNanos` với toàn bộ thời gian ban đầu, tổng thời gian có thể dài hơn hợp đồng. Ví dụ dùng `System.nanoTime()` để tính phần còn lại của cùng một ngân sách.

Thời hạn chờ cũng không phải cam kết luồng được CPU đúng tại thời điểm đó. Sau khi hết thời gian, luồng còn phụ thuộc lập lịch mới chạy tiếp để kiểm tra trạng thái.

Trong `awaitPayload`, điều kiện được kiểm tra trước việc kiểm tra hết thời gian ở mỗi vòng. Nếu cờ đã đúng khi vòng mới bắt đầu, phương thức có thể trả dữ liệu thay vì báo hết thời gian. Muốn hợp đồng khác, phải quy định và triển khai thứ tự quyết định khác; không để hành vi này vô tình trở thành một cam kết thời hạn cứng.

## 10. Lỗi thường gặp và cách nhận diện

| Nhận định hoặc cách viết | Vấn đề | Cách sửa |
| --- | --- | --- |
| Gọi unpark ba lần để lưu ba việc | Giấy phép không đếm sự kiện | Lưu việc vào hàng đợi hoặc dùng bộ đếm đúng nghĩa |
| Park trở về thì đọc dữ liệu ngay | Có thể trở về do nhiều nguyên nhân | Kiểm tra lại điều kiện trong vòng lặp |
| Unpark trước khi ghi ready | Có thể dùng hết giấy phép rồi chờ lại trước khi cờ đổi | Công bố điều kiện trước, đánh thức sau |
| Ready là boolean thường, không có đồng bộ khác | Không có hợp đồng công bố dữ liệu cần thiết | Dùng volatile, atomic hoặc khóa đúng cách |
| Gọi unpark trước start rồi trông chờ nó được nhớ | Không có bảo đảm cho luồng chưa khởi động | Lưu sự kiện trong trạng thái mà luồng đọc khi chạy |
| Mỗi blocker có một giấy phép riêng | Giấy phép gắn với luồng | Kiểm soát mọi đường chờ trên cùng luồng |
| Park liên tục sau khi bị ngắt | Có thể thành vòng lặp tiêu tốn CPU | Thực hiện chính sách ngắt rõ ràng |
| Dùng thời gian ngủ đo được làm chứng minh | Thức dậy giả và lập lịch làm phép đo không xác định | Kiểm chứng điều kiện và dựa trên hợp đồng API |
| Dùng Thread.getState để quyết định lúc unpark | Quan sát có thể đổi ngay | Thiết kế đăng ký và công bố trạng thái đúng |
| Đồng nhất được đánh thức với có quyền nhận khóa | Giấy phép không trao quyền sở hữu | Thử nhận quyền theo trạng thái đồng bộ |

## 11. Bài tập vận dụng

1. Vẽ trạng thái P cho chuỗi `unpark, unpark, park, unpark, park`. Chỉ rõ lúc nào phép gộp tín hiệu xảy ra.
2. Tạo lịch xen kẽ chứng minh vì sao “unpark trước, ready sau” có thể để người chờ ngủ lại. Sau đó đảo thứ tự và giải thích vai trò của giấy phép đến sớm.
3. Đổi ví dụ thành main công bố `value/ready` trước khi start consumer. Phân biệt “consumer không cần park vì cờ đã đúng” với lời khẳng định không hợp lệ rằng unpark trước start luôn được giữ lại.
4. Thiết kế yêu cầu nhận ba công việc. Chỉ ra cấu trúc lưu nội dung và điều kiện vòng lặp, rồi giải thích vì sao số lần unpark không cần bằng ba.
5. Thêm tình huống ngắt consumer trong khi chưa có dữ liệu. Xác minh kết quả là hủy chờ theo chính sách, không phải trả giá trị mặc định 0.
6. Giải thích tại sao hai lần park liên tiếp trở về nhanh không đủ để kết luận giấy phép đã tích lũy thành hai.

Điểm cần giữ trong mọi lời giải là sự tách biệt giữa **trạng thái cho phép tiếp tục**, **dữ liệu cần xử lý** và **tín hiệu giúp luồng kiểm tra lại**. Giấy phép một ô xử lý được tín hiệu đến sớm; nó không thay thế hai phần trạng thái còn lại.
