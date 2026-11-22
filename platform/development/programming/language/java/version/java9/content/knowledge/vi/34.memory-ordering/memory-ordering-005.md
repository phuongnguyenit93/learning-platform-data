# Thiết kế vòng lặp cập nhật nguyên tử với VarHandle

Một vòng lặp cập nhật nguyên tử thường thực hiện bốn bước: đọc giá trị hiện tại, tính giá trị mới từ snapshot đó, thử cập nhật bằng compare-and-set (CAS), rồi thử lại nếu một thread khác đã thay đổi biến. Đây là mẫu optimistic update: nhiều thread có thể cùng tính candidate, nhưng chỉ một thread thắng cho một trạng thái kỳ vọng; các thread còn lại phải lấy giá trị mới và tính lại.

Với VarHandle, có thể dùng `compareAndSet` hoặc `compareAndExchange` để thực hiện bước cập nhật có điều kiện. `compareAndExchange` đặc biệt hữu ích trong vòng lặp vì nó trả về giá trị đã quan sát tại thời điểm thao tác nguyên tử. Khi thất bại, vòng lặp có thể dùng chính giá trị đó làm snapshot kế tiếp thay vì đọc lại field ngay lập tức.

## 1. Mẫu đọc – tính – CAS – thử lại

Giả sử một field đang có giá trị `current` và ta muốn cộng thêm `delta`. Không thể chỉ đọc rồi ghi:

```java
int current = readValue();
writeValue(current + 1);
```

Hai thread có thể cùng đọc 10, cùng tính 11, rồi cùng ghi 11. Kết quả cuối chỉ tăng một đơn vị dù có hai yêu cầu tăng.

Vòng lặp CAS bảo đảm chỉ cập nhật nếu giá trị vẫn bằng snapshot đã đọc:

```java
for (;;) {
    int current = readValue();
    int next = current + 1;

    if (compareAndSet(current, next)) {
        return next;
    }

    // Một thread khác đã thay đổi giá trị.
    // Đọc lại và tính candidate mới.
}
```

CAS (compare-and-set) kiểm tra và cập nhật trong một thao tác nguyên tử. Nếu giá trị hiện tại vẫn bằng expected, nó ghi update và trả về `true`. Nếu giá trị không còn khớp, nó không ghi và trả về `false`.

Điểm quyết định là candidate phải được tính từ snapshot mới nhất mà vòng lặp đang dùng. Khi CAS thất bại, không được tiếp tục thử cùng một expected/update cũ vô hạn; cần lấy giá trị mới và tính lại.

## 2. compareAndSet và compareAndExchange trong vòng lặp

VarHandle cung cấp hai cách phổ biến để cập nhật có điều kiện:

| API | Kết quả trả về | Cách tiếp tục khi thất bại |
|---|---|---|
| `compareAndSet(expected, update)` | `true` nếu cập nhật thành công, `false` nếu expected không khớp | Đọc lại giá trị hiện tại rồi tính candidate mới |
| `compareAndExchange(expected, update)` | Giá trị witness được quan sát tại thời điểm thao tác nguyên tử | Nếu witness khác expected, dùng witness làm snapshot mới |

Với `compareAndSet`:

```java
int current = (int) VALUE.getVolatile(this);

for (;;) {
    int next = Math.addExact(current, delta);

    if (VALUE.compareAndSet(this, current, next)) {
        return next;
    }

    current = (int) VALUE.getVolatile(this);
    Thread.onSpinWait();
}
```

Với `compareAndExchange`:

```java
int current = (int) VALUE.getVolatile(this);

for (;;) {
    int next = Math.addExact(current, delta);
    int witness = (int) VALUE.compareAndExchange(this, current, next);

    if (witness == current) {
        return next;
    }

    // CAS thất bại: witness là giá trị tại thời điểm kiểm tra.
    current = witness;
    Thread.onSpinWait();
}
```

Cả hai đều thực hiện so sánh và cập nhật nguyên tử. `compareAndSet` trả về boolean nên sau thất bại thường cần thêm một lần đọc. `compareAndExchange` trả witness, nhờ đó có thể tái sử dụng giá trị đã quan sát trong lần CAS thất bại.

Witness là giá trị được quan sát tại điểm tuyến tính hóa của thao tác, không phải cam kết rằng field vẫn giữ nguyên giá trị đó khi thread tiếp tục chạy. Một thread khác vẫn có thể thay đổi field ngay sau đó; vòng lặp chỉ dùng witness làm expected cho lần thử tiếp theo.

## 3. Strong CAS, weak CAS và điều kiện kết thúc

`compareAndSet` và `compareAndExchange` là các thao tác strong: nếu expected không khớp thì thất bại; chúng không được phép báo thất bại giả khi giá trị vẫn khớp. Vì thế, vòng lặp với các thao tác này chỉ lặp lại khi có tranh chấp thực tế.

Các biến thể weak CAS như `weakCompareAndSetPlain`, `weakCompareAndSetAcquire`, `weakCompareAndSetRelease` và `weakCompareAndSetVolatile` có thể thất bại giả (spurious failure) ngay cả khi giá trị vẫn khớp. Nếu chọn weak CAS để phù hợp với một thuật toán hoặc nền tảng cụ thể, vòng lặp phải chấp nhận thất bại giả và thử lại. Không dùng kết quả false của weak CAS như bằng chứng rằng một thread khác chắc chắn đã thay đổi field.

Một vòng lặp cập nhật phải có điều kiện kết thúc rõ ràng:

- Thành công: thao tác nguyên tử đã thay giá trị expected bằng update.
- Lỗi nghiệp vụ: phép tính candidate thất bại, ví dụ `Math.addExact` ném `ArithmeticException` khi tràn số.
- Hủy hoặc deadline: nếu nghiệp vụ có giới hạn thời gian, vòng lặp cần kiểm tra điều kiện hủy theo thiết kế.
- Tranh chấp kéo dài: cân nhắc backoff hoặc một cơ chế đồng bộ khác thay vì quay vòng vô hạn trên CPU.

Không thêm side effect vào mỗi lần thử CAS. Một lần tính candidate có thể được thực hiện nhiều lần; chỉ thực hiện side effect sau khi CAS thành công.

## 4. Memory ordering trong vòng lặp

VarHandle tách thao tác truy cập biến khỏi mức memory ordering. Các access mode thông dụng gồm:

| Mode | Ý nghĩa chính |
|---|---|
| Plain (`get` / `set`) | Truy cập thông thường, không tạo thêm bảo đảm đồng bộ giữa thread |
| Opaque (`getOpaque` / `setOpaque`) | Bảo đảm tính nhất quán/coherence ở mức opaque nhưng không cung cấp đầy đủ acquire/release |
| Acquire (`getAcquire`) | Đọc với acquire semantics; các thao tác sau không được di chuyển trước lần đọc theo quy tắc bộ nhớ |
| Release (`setRelease`) | Ghi với release semantics; các thao tác trước được công bố trước lần ghi theo quy tắc bộ nhớ |
| Volatile (`getVolatile` / `setVolatile`) | Ngữ nghĩa volatile, có thứ tự đồng bộ phù hợp giữa các truy cập volatile |

Với CAS, cần chọn access mode phù hợp với dữ liệu được bảo vệ. `compareAndSet` và `compareAndExchange` có volatile memory effects. Các biến thể `compareAndExchangeAcquire` và `compareAndExchangeRelease` cung cấp semantics yếu hơn theo hướng acquire hoặc release; chỉ dùng khi đã chứng minh thuật toán cần đúng mức ordering đó.

Ví dụ trong bài dùng `getVolatile` kết hợp `compareAndExchange`. Đây là lựa chọn dễ kiểm chứng: lần đọc snapshot và thao tác cập nhật đều dùng volatile semantics. Khi tối ưu xuống acquire/release, phải xem cả đường thành công lẫn đường thất bại, dữ liệu nào được publish và thread khác đọc dữ liệu đó bằng mode nào.

Không trộn tùy tiện truy cập plain với truy cập atomic/volatile lên cùng trạng thái được chia sẻ. Nếu một thread đọc field bằng plain trong khi thread khác thay đổi bằng CAS, chương trình có thể không có visibility/order mà thuật toán yêu cầu. Hãy quy định một chính sách truy cập nhất quán cho field đó.

## 5. Ví dụ chạy được: bộ đếm tăng nguyên tử từ nhiều thread

Chương trình sau dùng một field int và VarHandle. Mỗi thread thực hiện 50.000 lần tăng. Bốn thread chạy đồng thời, nhưng tổng cuối cùng phải là 200.000 vì mỗi lần cập nhật chỉ thành công khi expected vẫn khớp.

**Main.java**

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class Main {
    static final class AtomicCounter {
        private int value;
        private static final VarHandle VALUE;

        static {
            try {
                VALUE = MethodHandles.lookup().findVarHandle(
                        AtomicCounter.class, "value", int.class);
            } catch (ReflectiveOperationException exception) {
                throw new ExceptionInInitializerError(exception);
            }
        }

        int addAndGet(int delta) {
            int current = (int) VALUE.getVolatile(this);

            for (;;) {
                int next = Math.addExact(current, delta);
                int witness = (int) VALUE.compareAndExchange(
                        this, current, next);

                if (witness == current) {
                    return next;
                }

                // Một cập nhật khác đã thắng. Dùng witness làm snapshot mới.
                current = witness;
                Thread.onSpinWait();
            }
        }

        int get() {
            return (int) VALUE.getVolatile(this);
        }
    }

    public static void main(String[] args) throws Exception {
        final int threadCount = 4;
        final int incrementsPerThread = 50_000;

        AtomicCounter counter = new AtomicCounter();
        ExecutorService pool = Executors.newFixedThreadPool(threadCount);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int i = 0; i < threadCount; i++) {
                tasks.add(pool.submit(() -> {
                    start.await();

                    for (int j = 0; j < incrementsPerThread; j++) {
                        counter.addAndGet(1);
                    }

                    return null;
                }));
            }

            start.countDown();

            for (Future<?> task : tasks) {
                task.get();
            }
        } finally {
            start.countDown();
            pool.shutdown();

            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();

                if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Worker threads did not stop");
                }
            }
        }

        int expected = threadCount * incrementsPerThread;
        System.out.println("Expected: " + expected);
        System.out.println("Actual: " + counter.get());
        System.out.println("Threads: " + threadCount);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all Main.java
java Main
```

Kết quả stdout:

```text
Expected: 200000
Actual: 200000
Threads: 4
```

Kết quả ổn định vì mỗi lần tăng là một thao tác đọc-modify-write nguyên tử. Nếu hai thread cùng đọc giá trị 100, chỉ một thread có thể đổi 100 thành 101. Thread còn lại nhận witness 101 từ `compareAndExchange`, tính lại candidate 102 và tiếp tục. Không có lần tăng nào bị ghi đè mất.

`Math.addExact` giúp ví dụ phát hiện overflow thay vì âm thầm quay vòng số nguyên. Nếu phép tính tràn, exception xảy ra trước CAS nên lần cập nhật đó không ghi giá trị mới.

## 6. Vì sao phải tính lại candidate sau mỗi lần thất bại?

Một lỗi phổ biến là giữ nguyên candidate cũ rồi thử CAS lại:

```java
int current = (int) VALUE.getVolatile(this);
int next = current + 1;

while (!VALUE.compareAndSet(this, current, next)) {
    // Sai: current và next không được cập nhật.
}
```

Nếu một thread khác đã đổi current, expected cũ không còn khớp. Lặp lại cùng cặp expected/update không giúp tiến triển. Cần đọc lại giá trị hoặc lấy witness từ `compareAndExchange`, sau đó tính candidate mới từ snapshot mới.

Cũng không được chỉ cập nhật expected mà giữ candidate cũ. Ví dụ current đổi từ 10 thành 15, candidate cũ là 11; nếu thử CAS expected=15, update=11 thì thuật toán có thể ghi lùi và làm mất cập nhật của thread khác. Candidate phải được tính lại từ current mới.

## 7. Tránh side effect trong vùng retry

Hàm cập nhật trong CAS loop có thể được gọi nhiều lần. Vì vậy phép tính candidate nên thuần (pure), hoặc ít nhất không tạo side effect không thể lặp lại.

Không nên làm như sau:

```java
for (;;) {
    int current = readValue();
    int next = current + 1;

    auditLog("increment requested"); // Có thể chạy nhiều lần.
    sendNotification(next);          // Có thể gửi trùng.

    if (compareAndSet(current, next)) {
        return next;
    }
}
```

Hãy chỉ commit side effect sau khi CAS thành công:

```java
int updated = atomicAddAndGet(1);
auditLog("value updated to " + updated);
sendNotification(updated);
```

Nếu side effect cần cùng tính nguyên tử với cập nhật trạng thái, CAS đơn lẻ không thể tạo transaction xuyên qua hệ thống log, message broker hoặc database. Khi đó cần thiết kế idempotency, transactional outbox hoặc một giao dịch phù hợp.

Tương tự, nếu dùng `IntUnaryOperator` hoặc một hàm update truyền vào vòng lặp, hãy giả định hàm đó có thể được gọi nhiều lần do tranh chấp. Không tăng biến đếm bên ngoài, ghi file hoặc gửi message bên trong hàm tính candidate.

## 8. Tranh chấp, backoff và tiến triển

CAS loop không chờ bằng monitor, nhưng điều đó không có nghĩa mọi thread đều chắc chắn hoàn tất trong thời gian hữu hạn. Một thread có thể liên tục thua các thread khác. Đây là starvation ở mức thread; thuật toán vẫn có thể có tiến triển toàn cục trong khi một thread cụ thể không tiến triển.

`Thread.onSpinWait` (có từ Java 9) là một hint cho runtime/CPU rằng thread đang trong vòng spin. Nó không khóa thread khác, không nhường CPU theo một bảo đảm cụ thể và không thay thế cơ chế đồng bộ. Có thể đặt nó sau một lần CAS thất bại, nhưng không cần chèn một cách máy móc vào mọi vòng lặp.

Khi contention cao:

- Giảm số lần cập nhật bằng batching nếu nghiệp vụ cho phép.
- Chia dữ liệu thành nhiều counter độc lập (striping) nếu không cần một thứ tự toàn cục.
- Dùng backoff có giới hạn để giảm các lần thử đồng thời.
- Cân nhắc lock hoặc queue nếu workload kéo dài, có nhiều side effect hoặc cần fairness.
- Đo throughput và tail latency trên workload thực tế; không kết luận từ một microbenchmark đơn giản.

CAS loop là công cụ cho cập nhật ngắn, có thể tính lại và có thể biểu diễn bằng một trạng thái nguyên tử. Nó không phải lựa chọn mặc định tốt nhất cho mọi cấu trúc dữ liệu.

## 9. ABA và trạng thái gồm nhiều field

CAS so sánh giá trị hiện tại với expected. Nếu trạng thái đổi A → B → A giữa hai lần quan sát, CAS có thể thấy A và thành công dù đã có thay đổi trung gian. Đây là vấn đề ABA.

Với bộ đếm chỉ tăng và không cho phép quay vòng (ví dụ chỉ nhận delta dương và dùng `Math.addExact`), ABA thường không phải vấn đề thực tế. Nhưng với bộ đếm có thể tăng/giảm, stack, free list, con trỏ hoặc trạng thái có ý nghĩa lịch sử, việc giá trị quay lại giống hệt có thể làm thuật toán sai.

Một cách xử lý là gắn version/stamp vào trạng thái. Mỗi lần cập nhật tăng version, để A ở version 1 khác A ở version 3. Với nhiều field cần thay đổi như một invariant, đóng gói chúng vào một object trạng thái bất biến rồi CAS trên tham chiếu đến object đó; không cập nhật từng field riêng lẻ nếu cần tính nguyên tử cho cả nhóm.

Đối với reference VarHandle, so sánh CAS dựa trên identity của tham chiếu, không gọi `equals` để so sánh nội dung. Tạo một object mới có cùng dữ liệu không làm nó trở thành cùng expected reference.

## 10. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Đọc rồi ghi trực tiếp | Mất cập nhật khi nhiều thread chạy đồng thời | Dùng thao tác RMW nguyên tử |
| Retry với expected cũ | Vòng lặp có thể không tiến triển | Lấy giá trị mới hoặc dùng witness |
| Cập nhật expected nhưng giữ candidate cũ | Có thể ghi đè giá trị mới bằng candidate lỗi thời | Tính lại candidate từ snapshot mới |
| Side effect trước CAS | Log/message có thể bị lặp dù CAS thất bại | Chỉ thực hiện sau khi CAS thành công |
| Bỏ qua overflow | Giá trị có thể quay vòng ngoài ý muốn | Xác định rõ semantics hoặc dùng phép tính kiểm tra overflow |
| Dùng weak CAS như strong CAS | Có thể retry dù không có tranh chấp | Xử lý spurious failure trong vòng lặp |
| Chọn memory mode quá yếu | Thiếu visibility/ordering cần thiết | Bắt đầu bằng volatile semantics rồi tối ưu có chứng minh |
| Chia nhỏ invariant thành nhiều CAS độc lập | Người đọc có thể quan sát trạng thái nửa cũ nửa mới | CAS trên một object trạng thái bất biến |
| Bỏ qua ABA | CAS thành công trên trạng thái đã đổi qua lại | Gắn version hoặc dùng thiết kế chống ABA |

## 11. Checklist thiết kế CAS loop

- Giá trị đọc ban đầu có đúng kiểu và đúng coordinate của VarHandle không?
- Candidate có được tính hoàn toàn từ snapshot hiện tại không?
- CAS có kiểm tra expected và cập nhật trong cùng một thao tác nguyên tử không?
- Khi thất bại, vòng lặp có lấy giá trị mới hoặc witness không?
- Có điều kiện kết thúc, xử lý overflow và chính sách hủy phù hợp không?
- Side effect chỉ chạy sau khi cập nhật thành công chưa?
- Memory mode có đáp ứng cả visibility và ordering của thuật toán không?
- Các field thuộc cùng invariant có được đóng gói thành một trạng thái nguyên tử không?
- ABA có thể xảy ra và có cần version/stamp không?
- Đã đo contention, starvation, throughput và latency trên tải thực tế chưa?

Một vòng lặp cập nhật nguyên tử đúng phải đọc snapshot, tính candidate từ snapshot đó, thực hiện CAS và tính lại sau khi thất bại. `compareAndExchange` giúp vòng lặp tận dụng witness trả về để tiếp tục nhanh hơn; memory mode quyết định bảo đảm thứ tự bộ nhớ; còn side effect, ABA, overflow và contention phải được xử lý như một phần của thiết kế thuật toán.
