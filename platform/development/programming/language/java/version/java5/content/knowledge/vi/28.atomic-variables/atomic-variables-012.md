# Tác động của tranh chấp và vòng lặp thử lại lên hiệu năng

## 1. Nguyên tử không có nghĩa là không phải chờ

Biến nguyên tử giúp nhiều luồng cập nhật một giá trị mà không làm mất tính đúng đắn của từng thao tác. Tuy nhiên, nếu nhiều luồng cùng sửa một biến, chúng vẫn phải cạnh tranh quyền làm cho cập nhật của mình có hiệu lực.

**Tranh chấp (contention)** xuất hiện khi nhiều luồng cùng cần tài nguyên dùng chung trong khoảng thời gian chồng lấn. Với biến nguyên tử, tài nguyên đó có thể là ô nhớ đang giữ bộ đếm hoặc tham chiếu trạng thái.

Một cách cập nhật bằng so sánh và cập nhật (compare-and-set, CAS) thường có dạng:

```java
// Mã minh họa: counter là AtomicInteger.
for (;;) {
    int before = counter.get();
    int after = before + 1;
    if (counter.compareAndSet(before, after)) {
        break;
    }
}
```

Nếu một luồng khác đổi giá trị sau `get()` và trước CAS, giá trị kỳ vọng có thể không còn đúng. Luồng hiện tại đọc lại, tính lại và thử lại. Tính đúng đắn vẫn được giữ, nhưng CPU đã thực hiện thêm công việc cho cùng một cập nhật thành công.

Bài học cần nắm: **số thao tác hoàn tất** và **số lần thử để hoàn tất chúng** có thể rất khác nhau.

## 2. Hai luồng cùng đọc một giá trị

Giả sử bộ đếm bằng 10:

| Thời điểm | Luồng T1 | Luồng T2 | Giá trị dùng chung |
| --- | --- | --- | --- |
| 1 | Đọc 10, tính 11 | | 10 |
| 2 | | Đọc 10, tính 11 | 10 |
| 3 | CAS(10, 11) thành công | | 11 |
| 4 | | CAS(10, 11) thất bại | 11 |
| 5 | | Đọc 11, tính 12, CAS thành công | 12 |

Kết quả đúng là 12. Để thực hiện hai lần tăng, có ba lần CAS, trong đó một lần thất bại.

Với ít luồng và khoảng tính toán ngắn, xung đột có thể ít. Khi nhiều luồng cùng cập nhật, nhiều luồng có thể giữ ảnh chụp vừa bị làm cũ. Mỗi luồng thua lại đọc và thử, tạo thêm hoạt động trên cùng điểm tranh chấp.

Không có quy luật “gấp đôi số luồng thì gấp đôi số lần thất bại”. Kết quả còn phụ thuộc số lõi CPU, bộ lập lịch, khoảng cách giữa các lần cập nhật, công việc xen kẽ và cách triển khai thao tác nguyên tử.

## 3. Chi phí phát sinh từ đâu?

### 3.1. Công việc bị thực hiện lại

Một lần CAS thất bại có thể khiến chương trình lặp lại:

- Đọc trạng thái hiện tại.
- Tính giá trị thay thế.
- Tạo đối tượng trạng thái mới nếu thuật toán dùng trạng thái bất biến.
- Thực hiện thao tác nguyên tử rồi rẽ nhánh về vòng lặp.

Với phép cộng một số nguyên, tính lại khá nhỏ. Với phép sao chép một cấu trúc hoặc xây một trạng thái lớn, phần tính và cấp phát bị bỏ đi có thể đáng kể.

Ví dụ minh họa:

```java
// Mã minh họa, không phải chương trình độc lập.
for (;;) {
    Snapshot before = state.get();
    Snapshot after = rebuild(before);  // Có thể tốn CPU và cấp phát.
    if (state.compareAndSet(before, after)) {
        return;
    }
}
```

Nếu thất bại, đối tượng `after` của lượt đó không được xuất bản qua CAS. Nó có thể trở thành rác nếu không còn nơi nào giữ tham chiếu. Vì vậy tỷ lệ thất bại còn có thể kéo theo áp lực lên bộ thu gom rác (GC).

Chỉ chuyển công việc ra ngoài vòng lặp nếu công việc đó thật sự độc lập với trạng thái vừa đọc. Tính `after` một lần rồi dùng mãi với các ảnh chụp mới có thể làm sai thuật toán.

### 3.2. Truy cập bộ nhớ dùng chung

Trên các hệ thống đa lõi thông thường, các lõi có bộ nhớ đệm (cache). Khi nhiều lõi cùng ghi vào một vị trí dùng chung, cơ chế duy trì nhất quán cache phải phối hợp các lần ghi đó.

Chi phí không chỉ là câu lệnh `before + 1`. Vị trí dùng chung trở thành điểm mà nhiều lõi phải phối hợp. Phần cứng và JVM có thể triển khai từng thao tác theo những cách khác nhau, nên không nên suy ra một chi phí nano giây cố định từ mã Java.

Ngay cả khi dùng API không có vòng CAS viết trực tiếp trong mã ứng dụng, một bộ đếm dùng chung vẫn có thể chịu giới hạn do nhiều lõi cùng cập nhật.

### 3.3. Nhiều luồng hơn số tài nguyên thực thi hữu ích

Thêm luồng có thể giúp tận dụng CPU lúc đầu, nhưng không tạo thêm khả năng cập nhật đồng thời cho một trạng thái cần thứ tự nhất quán.

Khi đã bão hòa, thêm luồng có thể làm tăng:

- Số lần tính toán bị bỏ.
- Thời gian tranh giành CPU và chi phí lập lịch.
- Thời gian một luồng phải đợi đến khi cập nhật thành công.
- Điện năng dùng cho các vòng thử không tạo thêm kết quả.

Việc dùng luồng ảo cũng không loại bỏ điểm tranh chấp của bộ nhớ dùng chung. Mô hình thực thi có thể thay đổi, nhưng mọi bên vẫn cập nhật cùng trạng thái.

## 4. Thực nghiệm xác định: hai cập nhật, ba lần thử

Chương trình dưới đây cố ý cho hai luồng cùng đọc 0 trước khi bất kỳ luồng nào CAS. `CyclicBarrier` chỉ tạo ra lịch thực thi cần quan sát. Sau đó một luồng thắng, luồng còn lại thất bại một lần rồi đọc lại và thành công.

Đây là minh chứng cho **cơ chế thử lại**, không phải benchmark tốc độ.

Tệp `CasContentionDemo.java`, chạy trên JDK 17 trở lên:

```java
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.atomic.AtomicInteger;

public class CasContentionDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger counter = new AtomicInteger();
        CyclicBarrier bothHaveRead = new CyclicBarrier(2);
        long[] attemptsByThread = new long[2];
        Throwable[] errors = new Throwable[2];
        Thread[] workers = new Thread[2];

        for (int i = 0; i < workers.length; i++) {
            final int index = i;
            workers[i] = new Thread(() -> {
                try {
                    int before = counter.get();
                    bothHaveRead.await();

                    long attempts = 0;
                    for (;;) {
                        attempts++;
                        if (counter.compareAndSet(before, before + 1)) {
                            break;
                        }
                        before = counter.get();
                    }
                    attemptsByThread[index] = attempts;
                } catch (Exception failure) {
                    errors[index] = failure;
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }
        for (Throwable error : errors) {
            if (error != null) {
                throw new AssertionError("Worker failed", error);
            }
        }

        long attempts = attemptsByThread[0] + attemptsByThread[1];
        System.out.println("value=" + counter.get());
        System.out.println("successfulUpdates=2");
        System.out.println("casAttempts=" + attempts);
        System.out.println("casFailures=" + (attempts - 2));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CasContentionDemo.java
java CasContentionDemo
```

Kết quả chính xác:

```text
value=2
successfulUpdates=2
casAttempts=3
casFailures=1
```

Mỗi luồng chỉ tăng bộ đếm một lần thành công. Cả hai bắt đầu với `before = 0`, nên chỉ một CAS từ 0 sang 1 thành công. Luồng còn lại đọc 1 và chuyển thành 2. Không có luồng ghi thứ ba và chương trình dùng CAS mạnh `compareAndSet`, nên tổng số lần thử là 3.

Số lần thử được đếm trong biến cục bộ của từng luồng và chỉ ghi vào phần tử kết quả sau khi vòng lặp xong. Luồng chính tổng hợp sau `join()`. Nếu mỗi lần thất bại lại tăng một bộ đếm nguyên tử chung khác, chính bộ đo có thể tạo thêm tranh chấp.

Không dùng thời gian chạy ví dụ này để kết luận CAS nhanh hay chậm hơn khóa. Tạo luồng và chờ tại hàng rào là một phần lớn của chương trình; đây không phải mô hình tải đại diện.

## 5. Những chỉ số phải phân biệt

Gọi:

- `S`: số cập nhật thành công.
- `F`: số CAS thất bại.
- `A = S + F`: tổng số lần CAS.

Trong một vòng lặp mà mỗi lượt gọi đúng một CAS và mỗi thao tác hoàn tất với đúng một CAS thành công:

```text
Số lần thử trung bình trên một cập nhật = A / S
Số lần thất bại trung bình trên một cập nhật = F / S
Tỷ lệ CAS thất bại = F / A
```

Ở ví dụ: `S = 2`, `F = 1`, `A = 3`. Trung bình cần 1,5 lần thử cho một cập nhật; tỷ lệ thất bại là 1/3.

Các công thức này là cách đếm hoạt động, không phải công thức dự đoán thời gian. Một lần thử có thể chứa rất nhiều hoặc rất ít công việc.

| Chỉ số | Câu hỏi nó trả lời |
| --- | --- |
| Thông lượng (throughput) | Mỗi giây hoàn tất được bao nhiêu thao tác hữu ích? |
| Độ trễ (latency) | Một thao tác mất bao lâu từ lúc bắt đầu đến lúc hoàn tất? |
| Độ trễ p95/p99 | Những thao tác chậm ở phần đuôi phân bố mất bao lâu? |
| CPU dùng trên mỗi kết quả | Để tạo ra một cập nhật, hệ thống tiêu tốn bao nhiêu công tính? |
| Số CAS thất bại | Đã bỏ đi bao nhiêu lần thử cập nhật? |
| Mức phân bố thành công giữa các luồng | Có luồng nào thường xuyên thua và bị chậm kéo dài không? |

Thông lượng tổng thể có thể còn khá tốt trong khi một số luồng liên tục thất bại. Do đó không thể kết luận tính công bằng từ một con số tổng.

Một thuật toán được chứng minh **không khóa (lock-free)** có bảo đảm tiến triển ở cấp hệ thống theo mô hình của nó, không đồng nghĩa từng luồng được phục vụ trong một thời gian giới hạn. Chỉ nhìn thấy một vòng CAS chưa đủ để kết luận toàn bộ thuật toán có tính chất đó: phần tính toán, cấp phát và các lời gọi khác cũng cần được xem xét.

## 6. Giảm chi phí bằng cách nào?

### 6.1. Chọn thao tác có sẵn khi đúng ý nghĩa cần dùng

Nếu yêu cầu chỉ là tăng bộ đếm, ưu tiên API phù hợp:

```java
int oldValue = counter.getAndIncrement();
```

Không cần tự viết vòng CAS chỉ để thực hiện cùng một thao tác đã được API cung cấp. Tuy nhiên, không nên mô tả `getAndIncrement()` như chắc chắn dùng đúng vòng CAS trong mã nguồn minh họa; JVM và phần cứng có thể dùng cơ chế khác. Điểm tranh chấp của một bộ đếm chung vẫn tồn tại.

Với `updateAndGet()` hoặc `getAndUpdate()`, hàm cập nhật có thể được áp dụng lại khi tranh chấp làm thất bại một lần cập nhật. Hàm cần không có tác dụng phụ. Xem [hợp đồng cập nhật AtomicInteger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html).

```java
// Phù hợp: chỉ tính giá trị mới từ giá trị đầu vào.
counter.updateAndGet(value -> value + 1);
```

Không gửi email, ghi giao dịch bên ngoài hoặc tăng một bộ đếm khác bên trong hàm cập nhật với kỳ vọng hàm chỉ chạy đúng một lần cho mỗi kết quả.

### 6.2. Giảm số lần chạm vào trạng thái dùng chung

Nếu yêu cầu cho phép, mỗi luồng có thể cộng dồn cục bộ rồi gộp một lần theo lô. Ví dụ, thay vì cập nhật chung cho từng sự kiện, cộng 100 sự kiện ở biến cục bộ rồi gọi `addAndGet(100)`.

Đổi lại, trạng thái chung chưa phản ánh các phần chưa gộp. Khi luồng kết thúc phải xử lý phần dư; khi có lỗi phải xác định rõ dữ liệu cục bộ còn lại được xử lý thế nào. Cách này phù hợp với thống kê cho phép độ trễ, không tự động phù hợp với kiểm tra hạn mức hoặc cấp số thứ tự.

Một lựa chọn khác là chia trạng thái theo nhóm độc lập: mỗi tài khoản, mỗi phân vùng hoặc mỗi khóa dữ liệu có vùng cập nhật riêng. Việc chia phải giữ được bất biến nghiệp vụ; nếu mọi thao tác vẫn cần một bộ đếm tổng tức thời, điểm tranh chấp đó vẫn còn.

### 6.3. Dùng LongAdder cho thống kê phù hợp

`LongAdder` phân tán cập nhật trên nhiều biến nội bộ khi có tranh chấp rồi tổng hợp khi đọc. Nó phù hợp với nhiều luồng cùng cộng số liệu thống kê; đổi lại có thể dùng nhiều bộ nhớ hơn. `sum()` không cung cấp ảnh chụp nguyên tử trong lúc có cập nhật đồng thời. Xem [LongAdder và giới hạn của sum()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html).

Vì vậy không thay máy móc một `AtomicLong` dùng để kiểm tra “còn đúng một chỗ trống thì dành chỗ đó” bằng `LongAdder`. Điều kiện kiểm tra và việc dành chỗ cần một giao thức nguyên tử phù hợp. Bộ đếm thống kê số yêu cầu đã xử lý có yêu cầu khác.

### 6.4. Điều chỉnh việc thử lại khi có bằng chứng cần thiết

Thử lại ngay có thể phù hợp khi xung đột ít và khoảng cập nhật ngắn. Với tranh chấp cao, một khoảng lùi có giới hạn, đôi khi kèm ngẫu nhiên, có thể giảm việc nhiều luồng thử cùng lúc. Nhưng nó cũng có thể tăng độ trễ hoặc làm giảm thông lượng nếu chờ quá lâu.

`Thread.onSpinWait()` là gợi ý cho môi trường thực thi rằng luồng đang quay chờ; nó không tự nhường CPU, không chặn luồng và không thay thế cơ chế đồng bộ. Xem [Thread.onSpinWait](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#onSpinWait()).

Không thêm `sleep()`, `yield()` hoặc một số lần thử cố định rồi giả định đã giải quyết hiệu năng và công bằng. Nếu giới hạn thử lại, phải xác định kết quả sau khi hết lượt: báo thất bại, đưa vào hàng chờ hay chuyển sang cơ chế phối hợp khác. Mọi đường đi phải giữ tính đúng đắn.

### 6.5. So sánh với khóa khi giao dịch lớn hoặc tranh chấp kéo dài

Khóa có thể tránh việc nhiều luồng cùng tính rồi bỏ cùng một kết quả. Nó cũng có chi phí phối hợp và có thể chặn các luồng khác.

Không có quy tắc “CAS luôn nhanh hơn `synchronized`” hoặc “tranh chấp cao thì khóa chắc chắn thắng”. Cần so sánh cùng chức năng, cùng mức nhất quán và cùng loại tải. Đặc biệt, giao dịch nhiều biến không thể được thay bằng một CAS đơn lẻ nếu làm mất bất biến.

## 7. Đo hiệu năng mà không tự đánh lừa mình

Khi cần quyết định triển khai:

1. Xác nhận mọi phương án tạo đúng kết quả và đáp ứng cùng yêu cầu nhất quán.
2. Đo cả ít luồng lẫn nhiều luồng; ghi số lõi và giới hạn CPU thực tế của môi trường chạy.
3. Tách trường hợp cùng sửa một biến với trường hợp mỗi luồng sửa trạng thái riêng.
4. Thử tỷ lệ đọc/ghi và lượng công việc giữa các lần ghi giống ứng dụng.
5. Quan sát thông lượng, CPU và phân bố độ trễ; nếu có số CAS thất bại, xem nó như một lời giải thích bổ sung.
6. Đo chi phí cấp phát/GC nếu mỗi lượt thử tạo đối tượng.
7. Lặp lại phép đo và ghi phiên bản JDK, cấu hình JVM, phần cứng, số luồng.

Với benchmark nhỏ trên JVM, dùng [JMH của OpenJDK](https://github.com/openjdk/jmh) để tổ chức khởi động làm nóng, lượt đo và các tiến trình đo độc lập. Vẫn cần thiết kế trạng thái chia sẻ đúng: nếu mỗi luồng có một bộ đếm riêng, benchmark không đo tranh chấp trên cùng bộ đếm.

Tránh `println()` trong vòng đo, tạo luồng cho từng lần tăng, hoặc chỉ đo một lần bằng đồng hồ rồi xếp hạng các phương án. Mã đo và bộ lập lịch có thể lấn át chính công việc cần đánh giá. Một kết quả tốt trên máy cá nhân cũng chưa đủ để suy ra độ trễ khi hệ thống chịu tải thực tế.

## 8. Bài tập suy luận

- Trong ví dụ, bỏ `CyclicBarrier`: còn chắc chắn đúng một CAS thất bại không? Không. Hai cập nhật vẫn đúng, nhưng số lần thử phụ thuộc lịch chạy; có thể cả hai thành công ngay.
- Tại sao không chỉ thử CAS một lần rồi bỏ qua nếu thất bại? Vì khi đó yêu cầu “mỗi luồng tăng một lần” không còn được bảo đảm.
- Nếu `rebuild(before)` mất nhiều thời gian hơn, có thể xảy ra điều gì? Khoảng từ đọc đến CAS dài hơn có thể làm ảnh chụp dễ hết hiệu lực; mỗi thất bại cũng lãng phí nhiều công tính hơn. Mức ảnh hưởng phải được đo.
- Nếu CPU tăng mạnh nhưng số cập nhật mỗi giây gần như không tăng khi thêm luồng, hãy kiểm tra điểm ghi dùng chung, công việc bị tính lại và chi phí phối hợp thay vì chỉ tăng thêm luồng.

Mục tiêu tối ưu là giảm công việc và thời gian cần để tạo ra **kết quả đúng**, trong khi giữ nguyên yêu cầu nhất quán của bài toán.
