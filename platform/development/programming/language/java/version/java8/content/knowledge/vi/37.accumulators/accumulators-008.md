# Hàm cập nhật có thể bị gọi lại khi CAS thất bại

## 1. Điều quan trọng nhất cần hiểu

Các biến nguyên tử (*atomic variables*) trong Java như `AtomicInteger`, `AtomicLong` và `AtomicReference` cho phép cập nhật dữ liệu dùng chung giữa nhiều luồng mà không phải đặt một khối `synchronized` quanh mọi phép cập nhật đơn giản. Từ Java 8, các lớp này hỗ trợ những hàm:

- `getAndUpdate(updateFunction)`;
- `updateAndGet(updateFunction)`;
- `getAndAccumulate(x, accumulatorFunction)`;
- `accumulateAndGet(x, accumulatorFunction)`.

Bốn hàm này có một hợp đồng dễ bị bỏ qua: **hàm cập nhật có thể được gọi lại khi lần cập nhật thử thất bại vì tranh chấp giữa các luồng**. Javadoc yêu cầu hàm được truyền vào phải **không có tác dụng phụ** (*side-effect-free*). Đây vẫn là yêu cầu hiện hành trong Java hiện đại, không phải một lưu ý chỉ dành cho Java 8.

Điều đó có nghĩa một thao tác `updateAndGet(v -> v + 1)` của một luồng có thể:

1. Đọc trạng thái cũ.
2. Tính giá trị đề xuất.
3. Thấy một luồng khác đã thay đổi giá trị nên không thể chốt đề xuất.
4. Đọc lại trạng thái mới.
5. **Gọi lại cùng lambda** với giá trị mới.
6. Sau đó mới chốt kết quả của một lần cập nhật nguyên tử.

Vì vậy không được đặt hành động như **gửi email, trừ tiền, ghi database, phát event hoặc tăng một bộ đếm nghiệp vụ bên ngoài** trong lambda rồi mặc định nó chỉ chạy một lần.

**Phân biệt cốt lõi:** Một lần gọi phương thức atomic có thể **chốt đúng một lần cập nhật**, nhưng **số lần đánh giá hàm tính có thể lớn hơn một**. CAS không đảm bảo *exactly-once execution* cho code ở bên trong hàm cập nhật.

Bài này giải thích cơ chế CAS, API trả giá trị cũ/mới, sự khác nhau giữa hàm thuần và hàm có tác dụng phụ, các ví dụ tranh chấp có thể kiểm thử lặp lại, biến tham chiếu, hàm tích lũy có tính giao hoán/kết hợp, ABA, cách đặt side effect ngoài vòng retry, cùng những giới hạn còn lại ở tầng hệ thống.

Các chương trình hoàn chỉnh được viết cho **JDK 17+**; phần API atomics trọng tâm đã có từ Java 8 và vẫn được hỗ trợ. Ví dụ dùng `record` cần Java 16+, vì vậy nếu dự án thực sự biên dịch với Java 8 có thể thay `record` bằng class bất biến thông thường.

## 2. CAS là gì?

CAS là viết tắt của **Compare-And-Set**. Với một biến nguyên tử `value`:

```java
// Đoạn minh họa:
boolean success = value.compareAndSet(
    expectedValue,
    newValue
);
```

Ý nghĩa:

- Nếu giá trị hiện tại đúng với `expectedValue` tại điểm thực hiện CAS, đặt `newValue` và trả `true`.
- Nếu giá trị đã thay đổi, không ghi `newValue` và trả `false`.

Tác vụ kiểm tra và đặt giá trị diễn ra như **một thao tác nguyên tử**, nên hai luồng không thể cùng “thắng” với cùng một trạng thái kỳ vọng đã bị thay đổi theo hai giá trị khác nhau.

### 2.1. Ví dụ timeline hai luồng

Giả sử `AtomicInteger number` ban đầu là `10`. Luồng A gọi `updateAndGet(n -> n + 1)`, luồng B sửa giá trị thành `100` đúng lúc A đang tính.

| Bước | Luồng A | Luồng B | Giá trị atomic |
| --- | --- | --- | --- |
| 1 | Đọc `10` | — | `10` |
| 2 | Tính `f(10) = 11` | — | `10` |
| 3 | Chưa thực hiện CAS | `compareAndSet(10,100)` thành công | `100` |
| 4 | `compareAndSet(10,11)` thất bại | — | `100` |
| 5 | Đọc lại `100` | — | `100` |
| 6 | **Gọi lại** `f(100) = 101` | — | `100` |
| 7 | `compareAndSet(100,101)` thành công | — | `101` |

Sau đó:

```text
Giá trị cuối:                  101
Số lần lambda của A được gọi:    2
Số lần cập nhật do A chốt:       1
```

Lần tính ra `11` **không được ghi vào atomic variable** vì CAS thua. Tuy nhiên, bất kỳ tác dụng phụ nào mà lambda đã thực hiện khi tính `11` vẫn có thể đã diễn ra.

### 2.2. Mô hình vòng lặp CAS

Có thể hình dung `updateAndGet` tương tự mã khái niệm:

```java
// Mô phỏng ý tưởng; không phải mã nguồn đặc tả
// hay cam kết chính xác chiến lược nội bộ của mọi JDK.
static int conceptualUpdate(
    AtomicInteger value,
    IntUnaryOperator update
) {
    for (;;) {
        int observed = value.get();
        int proposed = update.applyAsInt(observed);

        if (value.compareAndSet(
                observed, proposed)) {
            return proposed;
        }

        // CAS thất bại: tính lại từ trạng thái mới.
    }
}
```

Chính lệnh `update.applyAsInt(observed)` nằm **bên trong vòng retry**, do đó có thể được chạy lại. Javadoc quy định hành vi hợp đồng; nó **không cam kết đúng cú pháp vòng lặp này** hoặc một số lần thử cố định cho mọi triển khai.

**Lưu ý:** CAS có thể được thử lại vì một luồng khác thay đổi cùng biến. Không có bảo đảm rằng một lambda nhất định luôn chạy hai lần, hoặc mỗi operation luôn có ít nhất một lần retry. Khi không có tranh chấp, lambda thường chỉ chạy một lần; khi có tranh chấp, số lần thử phụ thuộc lịch thực thi và runtime.

## 3. Những API có cùng cảnh báo về callback

| Kiểu | API tiêu biểu | Loại hàm |
| --- | --- | --- |
| `AtomicInteger` | `getAndUpdate`, `updateAndGet` | `IntUnaryOperator` |
| `AtomicInteger` | `getAndAccumulate`, `accumulateAndGet` | `IntBinaryOperator` |
| `AtomicLong` | Các cặp phương thức tương ứng | `LongUnaryOperator`, `LongBinaryOperator` |
| `AtomicReference<V>` | Các cặp phương thức tương ứng | `UnaryOperator<V>`, `BinaryOperator<V>` |
| `AtomicIntegerArray` / `AtomicLongArray` | `updateAndGet(index, f)` và các hàm tương ứng | Hàm trên phần tử tại index |
| `AtomicReferenceArray<V>` | Các hàm cập nhật có index | Hàm trên tham chiếu phần tử |
| `AtomicIntegerFieldUpdater` / `AtomicLongFieldUpdater` / `AtomicReferenceFieldUpdater` | Các hàm cập nhật field của object | Hàm trên field được quản lý |
| `LongAccumulator` / `DoubleAccumulator` | `accumulate(x)` với hàm được cung cấp khi khởi tạo | Hàm tích lũy có thể được đánh giá lại |

Mọi trường hợp có callback nằm trong cơ chế retry/đồng bộ đều cần xem **hợp đồng của đúng lớp**. Đặc biệt, với `LongAccumulator`/`DoubleAccumulator`, hàm tích lũy không chỉ cần không có tác dụng phụ mà còn cần **phù hợp với thứ tự gộp không xác định**.

### 3.1. Các overload trọng tâm

```java
// Chữ ký khái niệm của AtomicInteger:
int getAndUpdate(IntUnaryOperator updateFunction);

int updateAndGet(IntUnaryOperator updateFunction);

int getAndAccumulate(
    int x,
    IntBinaryOperator accumulatorFunction
);

int accumulateAndGet(
    int x,
    IntBinaryOperator accumulatorFunction
);
```

Cặp `getAnd...` trả **giá trị trước lần cập nhật thành công**, còn cặp `...AndGet` trả **giá trị sau khi cập nhật thành công**.

Đối với hàm nhị phân, thứ tự tham số là:

```java
(currentValue, suppliedUpdate) -> newValue
```

Không đảo thứ tự hai tham số nếu phép tính không giao hoán, chẳng hạn phép trừ, ghép chuỗi hoặc cập nhật một record nhiều trường.

### 3.2. getAndAdd/incrementAndGet khác gì?

`AtomicInteger.incrementAndGet()`, `getAndIncrement()`, `addAndGet(delta)` hoặc `getAndAdd(delta)` không nhận lambda do người dùng cung cấp, vì vậy không có rủi ro **callback chứa side effect bị gọi lại**. Đây thường là lựa chọn đơn giản hơn khi chỉ muốn tăng/giảm/cộng một số cố định.

Điều đó không biến mọi nghiệp vụ có increment thành exactly-once xuyên các request, DB hoặc nhiều máy. Nó chỉ loại bỏ **callback tùy ý** khỏi phép cập nhật atomic trong bộ nhớ.

## 4. Ví dụ 1 — nhận diện giá trị cũ/mới và thứ tự tham số

Tạo file **ApiBasicsDemo.java**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class ApiBasicsDemo {
    public static void main(String[] args) {
        AtomicInteger number = new AtomicInteger(10);

        System.out.println(
            "getAndUpdate.old=" +
            number.getAndUpdate(value -> value + 2)
        );

        System.out.println(
            "afterGetAndUpdate=" + number.get()
        );

        System.out.println(
            "updateAndGet.new=" +
            number.updateAndGet(value -> value * 2)
        );

        System.out.println(
            "getAndAccumulate.old=" +
            number.getAndAccumulate(
                3,
                (current, delta) -> current + delta
            )
        );

        System.out.println(
            "accumulateAndGet.new=" +
            number.accumulateAndGet(
                5,
                (current, delta) -> current - delta
            )
        );

        System.out.println("final=" + number.get());
    }
}
```

Biên dịch và chạy:

```bash
javac ApiBasicsDemo.java
java ApiBasicsDemo
```

Stdout đã kiểm thử:

```text
getAndUpdate.old=10
afterGetAndUpdate=12
updateAndGet.new=24
getAndAccumulate.old=24
accumulateAndGet.new=22
final=22
```

Từng bước:

1. `getAndUpdate(v -> v+2)` chuyển `10 → 12` nhưng trả `10`.
2. `updateAndGet(v -> v*2)` chuyển `12 → 24` và trả `24`.
3. `getAndAccumulate(3,(current,delta)->current+delta)` chuyển `24 → 27`, trả giá trị cũ `24`.
4. `accumulateAndGet(5,(current,delta)->current-delta)` chuyển `27 → 22`, trả giá trị mới `22`.

Ví dụ không có tranh chấp nên giúp hiểu return value. Khi có CAS retry, giá trị “cũ” được trả là giá trị ngay trước **lần cập nhật thực sự thành công**, không nhất thiết là giá trị đọc ở **lần đánh giá lambda đầu tiên**.

## 5. Ví dụ 2 — chứng minh lambda được gọi lại một cách xác định

Không nên kiểm thử retry bằng cách chạy hai thread thật nhanh và *hy vọng* chúng va chạm. Mỗi lần chạy có lịch thực thi khác nhau, nên có thể tình cờ không có CAS fail.

Thay vào đó, dùng `CountDownLatch` để buộc luồng A dừng **sau khi lambda đọc đầu vào nhưng trước khi CAS chốt**, rồi cho luồng chính thay đổi giá trị. Khi A được tiếp tục, CAS của lần đầu chắc chắn thất bại trong thí nghiệm có điều phối này.

**Đây là phương pháp kiểm thử, không phải code production.** Không đặt `await`/`sleep` trong callback atomic ở hệ thống thật.

Tạo file **CASRetryDeterministicDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CASRetryDeterministicDemo {
    public static void main(String[] args)
            throws Exception {
        AtomicInteger value = new AtomicInteger(10);
        AtomicInteger calls = new AtomicInteger();

        CountDownLatch firstRead =
            new CountDownLatch(1);
        CountDownLatch resume =
            new CountDownLatch(1);

        ExecutorService executor =
            Executors.newSingleThreadExecutor();

        try {
            Future<Integer> pending = executor.submit(
                () -> value.updateAndGet(old -> {
                    int attempt = calls.incrementAndGet();

                    if (attempt == 1) {
                        firstRead.countDown();
                        try {
                            if (!resume.await(
                                    3, TimeUnit.SECONDS)) {
                                throw new IllegalStateException(
                                    "timeout"
                                );
                            }
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(ex);
                        }
                    }

                    return old + 1;
                })
            );

            if (!firstRead.await(
                    3, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "not started"
                );
            }

            // A đã đọc old=10 nhưng chưa CAS.
            boolean changed =
                value.compareAndSet(10, 100);

            // Cho A đi tiếp: lần CAS với 10 sẽ thua.
            resume.countDown();

            System.out.println(
                "interferenceCAS=" + changed
            );

            System.out.println(
                "updated=" +
                pending.get(3, TimeUnit.SECONDS)
            );

            System.out.println(
                "callbackCalls=" + calls.get()
            );

            System.out.println(
                "stored=" + value.get()
            );
        } finally {
            resume.countDown();
            executor.shutdownNow();
        }
    }
}
```

```bash
javac CASRetryDeterministicDemo.java
java CASRetryDeterministicDemo
```

Stdout đã kiểm thử:

```text
interferenceCAS=true
updated=101
callbackCalls=2
stored=101
```

**Vì sao đúng hai lần trong thí nghiệm này?**

- A được đồng bộ để đọc `10` và chờ, nên callback tính lần đầu từ `10`.
- Luồng chính thực hiện `compareAndSet(10,100)` thành công.
- Sau release, A thử CAS `10 → 11` nhưng giá trị hiện tại là `100`; CAS thua.
- A đọc lại `100`, lambda chạy lần thứ hai và đề xuất `101`.
- Không còn luồng cạnh tranh mới, nên lần CAS thứ hai chốt `101`.

Điều phải rút ra **không phải** “lambda luôn chạy hai lần”. Điều quan trọng là **Java được phép gọi lại lambda**, và một callback đúng đắn phải an toàn khi điều đó xảy ra. Kết quả số lần trong sản xuất không thể suy ra chỉ từ số lượng luồng.

## 6. Tác dụng phụ (side effect) tại sao nguy hiểm?

Một lambda có tác dụng phụ là lambda thay đổi thứ gì đó ngoài giá trị đề xuất cho atomic variable:

- Gửi email, SMS, notification hoặc gọi webhook.
- Gọi API tạo đơn hàng, trừ tiền, cấp token hay tạo file.
- Ghi DB, phát event, đưa message vào queue.
- Ghi `List` mutable, sửa trường của object khác.
- Tăng metric/bộ đếm bên ngoài callback.
- Ghi log có ý nghĩa nghiệp vụ, ghi audit event.
- Lấy `Random`/clock hay đọc trạng thái bên ngoài thay đổi liên tục để quyết định giá trị.

Khi CAS thất bại, **giá trị đề xuất của lần tính thua bị bỏ qua**, nhưng tác dụng phụ đã thực hiện **không được rollback**.

### 6.1. Một lần cập nhật nhưng hai lần gửi sự kiện

```java
// Phản ví dụ; không đưa code này vào production.
AtomicInteger value = new AtomicInteger(10);

int updated = value.updateAndGet(old -> {
    emailService.send("updated");  // Tác dụng phụ!
    return old + 1;
});
```

Giả sử một lần CAS thua và lambda được gọi lại:

```text
Lambda lần 1: email gửi, đề xuất 11, CAS thất bại.
Lambda lần 2: email gửi, đề xuất 101, CAS thành công.

Kết quả: atomic variable nhận một lần cập nhật của
luồng gọi, nhưng có thể đã gửi hai email.
```

Lỗi này có thể xảy ra ngay cả khi chỉ có **một invocation** từ thread A: nguyên nhân là **retry nội bộ do tranh chấp**, không nhất thiết vì caller gọi API hai lần.

### 6.2. Vì sao idempotency quan trọng?

Một hàm không có tác dụng phụ không cần là **idempotent theo toán học**. Ví dụ `f(x)=x+1` **không idempotent** vì `f(f(x)) != f(x)`, nhưng lại **an toàn để đánh giá lại trong CAS loop**, do các kết quả thất bại không được ghi.

Điều cần là hàm **side-effect-free**, dựa trên đầu vào thích hợp, có thể tính lại theo trạng thái mới mà không thực hiện hành động bên ngoài lặp thừa.

Nếu business action là gửi event hoặc trừ tiền, idempotency ở hệ thống ngoài là yêu cầu bổ sung, không thể biến callback có side effect thành “thuần” chỉ bằng cách hy vọng callback ít retry.

## 7. Ví dụ 3 — đo số lần tác dụng phụ bị dư ra

Tạo file **SideEffectOvercountDemo.java**. `AtomicInteger events` mô phỏng số lần side effect xảy ra; nó **không phải** mẫu khuyến khích gửi event bên trong callback.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class SideEffectOvercountDemo {
    public static void main(String[] args)
            throws Exception {
        AtomicInteger value = new AtomicInteger(10);
        AtomicInteger events = new AtomicInteger();

        CountDownLatch first =
            new CountDownLatch(1);
        CountDownLatch release =
            new CountDownLatch(1);

        ExecutorService pool =
            Executors.newSingleThreadExecutor();

        try {
            Future<Integer> pending = pool.submit(
                () -> value.updateAndGet(old -> {
                    // Cố tình đặt side effect sai chỗ.
                    int call = events.incrementAndGet();

                    if (call == 1) {
                        first.countDown();

                        try {
                            if (!release.await(
                                    3, TimeUnit.SECONDS)) {
                                throw new IllegalStateException(
                                    "timeout"
                                );
                            }
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(ex);
                        }
                    }

                    return old + 1;
                })
            );

            if (!first.await(
                    3, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "not called"
                );
            }

            System.out.println(
                "otherCAS=" +
                value.compareAndSet(10, 100)
            );

            release.countDown();

            System.out.println(
                "workerResult=" +
                pending.get(3, TimeUnit.SECONDS)
            );

            System.out.println(
                "sideEffects=" + events.get()
            );

            System.out.println(
                "workerCommittedUpdates=1"
            );
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

```bash
javac SideEffectOvercountDemo.java
java SideEffectOvercountDemo
```

Stdout:

```text
otherCAS=true
workerResult=101
sideEffects=2
workerCommittedUpdates=1
```

Ở đây, luồng worker chốt **một** lần cập nhật từ `100` lên `101`, nhưng callback của nó đã chạy hai lần. Bộ đếm ngoài map/atomic mục tiêu nhận **hai** lần tăng. Một hệ thống đặt thanh toán/email ngay trong callback có thể dẫn đến ghi nhận sai.

Chỉ dùng các latch trong bài kiểm thử để tạo một lịch thực thi có kiểm soát. Khi chạy thật, lambda có thể được đánh giá một, hai hoặc nhiều lần tùy tranh chấp; **đừng đặt nghiệp vụ đúng đắn vào giả định số lần callback**.

## 8. Cách đúng: tính thuần trong lambda, hành động sau khi thành công

Khi thao tác chỉ cần cộng/tính state, giữ lambda **thuần**:

```java
// Đoạn minh họa, atomic đã được khởi tạo.
int committed = atomic.updateAndGet(
    old -> Math.addExact(old, 1)
);

// Chỉ thực hiện sau khi lời gọi atomic đã trả về.
auditLogger.recordCommittedValue(committed);
```

`Math.addExact` cho phép phát hiện overflow thay vì lặng lẽ wrap số nguyên. Đoạn này an toàn hơn việc log bên trong lambda vì một lần gọi `updateAndGet` thành công trả về **một lần** rồi mới log.

Tuy nhiên, phải phân biệt hai mức độ bảo đảm:

- **Không bị nhân số lần vì CAS retry nội bộ:** Khi side effect chạy sau `updateAndGet` trả về, retry nội bộ không tự làm side effect ấy chạy lại.
- **Không có exactly-once toàn hệ thống:** Nếu process crash sau khi cập nhật atomic nhưng trước khi gửi event, event có thể mất. Nếu caller retry sau timeout hoặc request đến hai lần, side effect ngoài map vẫn có thể lặp. Atomic update và DB/email không phải một transaction chung.

Với thao tác nghiệp vụ có tiền hoặc dữ liệu bền vững, cần thiết kế transaction, idempotency key, outbox hoặc cơ chế xác nhận tương ứng.

### Ví dụ 4 — PureAfterCommitDemo.java

Tạo file sau để minh họa cùng tình huống CAS thua, nhưng counter thông báo nằm **sau** khi hàm atomic trả về:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PureAfterCommitDemo {
    public static void main(String[] args)
            throws Exception {
        AtomicInteger value = new AtomicInteger(10);
        AtomicInteger calls = new AtomicInteger();
        AtomicInteger notifications =
            new AtomicInteger();

        CountDownLatch first =
            new CountDownLatch(1);
        CountDownLatch release =
            new CountDownLatch(1);

        ExecutorService pool =
            Executors.newSingleThreadExecutor();

        try {
            Future<Integer> pending = pool.submit(() -> {
                int updated = value.updateAndGet(old -> {
                    int attempt = calls.incrementAndGet();

                    if (attempt == 1) {
                        first.countDown();

                        try {
                            if (!release.await(
                                    3, TimeUnit.SECONDS)) {
                                throw new IllegalStateException(
                                    "timeout"
                                );
                            }
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(ex);
                        }
                    }

                    return old + 1;
                });

                // Bên ngoài vòng CAS: chỉ chạy khi
                // updateAndGet đã hoàn tất bình thường.
                notifications.incrementAndGet();
                return updated;
            });

            if (!first.await(
                    3, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "not called"
                );
            }

            value.compareAndSet(10, 100);
            release.countDown();

            System.out.println(
                "result=" +
                pending.get(3, TimeUnit.SECONDS)
            );

            System.out.println(
                "callbackCalls=" + calls.get()
            );

            System.out.println(
                "notifications=" +
                notifications.get()
            );
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

```bash
javac PureAfterCommitDemo.java
java PureAfterCommitDemo
```

Stdout:

```text
result=101
callbackCalls=2
notifications=1
```

**Giới hạn của ví dụ:** `calls.incrementAndGet()` và các latch **vẫn là side effect bên trong lambda**, được đặt ở đó **chỉ để đo và ép một CAS fail trong test**. Trong code thực tế, callback nên chỉ tính `old + 1` hoặc một kết quả thuần khác. Điểm chứng minh là **thông báo ngoài callback không bị nhân lên theo số lần thử CAS nội bộ**.

## 9. Nhiều luồng: đúng kết quả nhưng không biết trước số lần tính

Với một `AtomicLong`, có thể nhiều luồng cùng `updateAndGet(v -> v + 1)`. Tổng cuối cùng vẫn đúng nếu mọi lời gọi hoàn tất và không overflow, còn số lần đánh giá callback là **biến thiên theo contention**.

### Ví dụ 5 — ParallelIncrementDemo.java

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

public class ParallelIncrementDemo {
    public static void main(String[] args)
            throws Exception {
        AtomicLong count = new AtomicLong();
        AtomicLong evaluations =
            new AtomicLong();

        ExecutorService executor =
            Executors.newFixedThreadPool(4);

        try {
            List<Future<?>> jobs =
                new ArrayList<>();

            for (int i = 0; i < 4; i++) {
                jobs.add(executor.submit(() -> {
                    for (int j = 0; j < 1000; j++) {
                        count.updateAndGet(old -> {
                            evaluations.incrementAndGet();
                            return old + 1;
                        });
                    }
                }));
            }

            for (Future<?> job : jobs) {
                job.get(5, TimeUnit.SECONDS);
            }

            System.out.println(
                "final=" + count.get()
            );

            System.out.println(
                "callbackAtLeastOperations=" +
                (evaluations.get() >= 4000)
            );
        } finally {
            executor.shutdownNow();
        }
    }
}
```

```bash
javac ParallelIncrementDemo.java
java ParallelIncrementDemo
```

Stdout không phụ thuộc chính xác vào lịch thực thi, khi mọi task hoàn tất:

```text
final=4000
callbackAtLeastOperations=true
```

4 thread × 1000 operations = 4000 cập nhật được chốt. `evaluations` phải có ít nhất 4000 (mỗi update thành công cần đánh giá lambda), và **có thể nhiều hơn** khi tranh chấp làm CAS thua.

Không in số lần callback **chính xác** trong một benchmark ngẫu nhiên rồi coi đó là stdout cố định; con số ấy không được bảo đảm. Demo dùng `>= 4000` để kiểm tra invariant, còn bài kiểm thử có latch ở phần 5 tạo retry một cách chắc chắn.

**Lưu ý hiệu năng:** Với mục tiêu thuần túy chỉ tăng một bộ đếm, `count.incrementAndGet()` hoặc `count.addAndGet(1)` thường đơn giản hơn. `LongAdder` có thể phù hợp khi nhiều luồng tăng bộ đếm tần suất và cần throughput cao, nhưng có khác biệt về snapshot sẽ được nói ở phần sau.

## 10. Hàm thuần nên có các đặc điểm nào?

Một hàm cập nhật tốt trong CAS loop nên:

1. **Tính từ old value và input bất biến**, không tùy tiện đọc/truy cập state có thể thay đổi ngoài atomic.
2. **Không gây side effect quan sát được** ngoài việc trả giá trị mới.
3. **Có thể gọi lại** với old value mới sau CAS fail mà không làm thay đổi ý nghĩa nghiệp vụ.
4. Không gọi I/O, không chờ khóa, future, sleep hoặc timer.
5. Không sửa object mutable mà nhiều luồng đã có thể nhìn thấy.
6. Không đòi số lần callback chính xác một để thực hiện nghiệp vụ.
7. Có chi phí tính toán giới hạn, tránh thêm latency khi contention.
8. Xử lý overflow, null, validation một cách rõ ràng.
9. Không gọi recursive update của chính state theo cách gây can thiệp khó đoán.
10. Trả **giá trị mới** để CAS công bố, chứ không trực tiếp công bố state từ trong lambda.

Ví dụ thích hợp:

```java
// Đoạn minh họa: cộng an toàn khi overflow không được phép.
AtomicLong counter = new AtomicLong(0L);

long after = counter.updateAndGet(
    old -> Math.addExact(old, 5L)
);
```

`Math.addExact` là hàm thuần trên input. Nếu overflow, nó ném `ArithmeticException`; lần gọi không chốt kết quả tính sai. Đây không phải retry do CAS thất bại: một exception từ lambda được truyền ra caller theo contract.

### 10.1. Hàm thuần không cần là idempotent

Một nhầm lẫn phổ biến là yêu cầu `f(f(x)) == f(x)`. Đó là *idempotence* theo toán học, **không phải điều kiện bắt buộc** với CAS update.

`f(x)=x+1` không idempotent nhưng **an toàn để đánh giá lại** vì lần CAS thất bại không commit kết quả trước đó. Điều cần tránh là side effect hoặc lệ thuộc các giá trị ngoài không được kiểm soát.

### 10.2. Hàm đọc thời gian/Random có được không?

Ví dụ:

```java
// Không phù hợp nếu mỗi retry phải tuân một quyết định ổn định.
atomic.updateAndGet(old ->
    old + (int) (System.currentTimeMillis() % 3)
);
```

Mỗi lần CAS retry có thể nhận thời gian mới, làm thay đổi đề xuất theo một đầu vào **không được ghi rõ**. Không có side effect ghi state, nhưng kết quả có thể khó tái lập hoặc sai contract business. Nếu timestamp/random value thuộc ý định của một request, tạo nó **một lần bên ngoài** rồi capture giá trị bất biến:

```java
// Đoạn minh họa.
final int increment = computeDeltaOnceOutside();

atomic.updateAndGet(
    old -> Math.addExact(old, increment)
);
```

Cách này giữ cùng input request qua các lần retry, nhưng chỉ đúng khi business muốn delta cố định.

## 11. AtomicReference: tránh sửa object đang được chia sẻ

`AtomicReference<V>` bảo đảm cập nhật **tham chiếu** bằng CAS. Nó không tự làm mọi trường của object V trở thành thread-safe, cũng không bảo đảm snapshot nếu callback sửa object cũ tại chỗ.

Phản ví dụ:

```java
// Sai: old là object có thể đã được luồng khác quan sát.
reference.updateAndGet(old -> {
    old.items.add(newItem); // Sửa object cũ trước CAS.
    return old;
});
```

Dù CAS thất bại, `old.items.add(...)` đã sửa state có thể nhìn thấy ở ngoài. Thậm chí khi trả lại **cùng một tham chiếu**, CAS không có cơ hội kiểm soát cách các field mutable bị thay đổi. Nếu lambda bị gọi lại, cùng một object có thể bị sửa thêm lần nữa.

**Cách khắc phục:** Dùng **immutable value** và trả về **object mới** chứa trạng thái cập nhật. Không mutate object `old`.

### Ví dụ 6 — ImmutableReferenceDemo.java

```java
import java.util.concurrent.atomic.AtomicReference;

public class ImmutableReferenceDemo {
    record State(int count, String status) {}

    public static void main(String[] args) {
        AtomicReference<State> reference =
            new AtomicReference<>(
                new State(5, "OPEN")
            );

        State previous =
            reference.getAndUpdate(
                old -> new State(
                    old.count() + 1,
                    old.status()
                )
            );

        State latest = reference.get();

        System.out.println("old=" + previous);
        System.out.println("new=" + latest);

        System.out.println("differentObjects=" +
            (previous != latest));
    }
}
```

```bash
javac ImmutableReferenceDemo.java
java ImmutableReferenceDemo
```

Stdout:

```text
old=State[count=5, status=OPEN]
new=State[count=6, status=OPEN]
differentObjects=true
```

Đây là mẫu update một **immutable snapshot**. CAS chỉ công bố object mới khi trạng thái cũ vẫn là tham chiếu được mong đợi. Nếu CAS thua, lambda có thể dựng **một object mới khác** từ snapshot mới. Object dựng ra trong lần thử thua có thể bị bỏ đi để GC, **không gây thay đổi trạng thái được chia sẻ**.

**Trade-off:** Nếu mỗi retry cấp phát object lớn, contention cao có thể gây overhead CPU/GC. Hãy cân nhắc cấu trúc value, lượng cấp phát và tần suất cập nhật, nhưng không đánh đổi tính đúng đắn bằng cách mutate old object.

## 12. LongAccumulator và DoubleAccumulator: thêm yêu cầu về thứ tự

`LongAccumulator` và `DoubleAccumulator` cũng là **biến tích lũy concurrent**, nhưng khác `AtomicLong.updateAndGet` ở cách tối ưu cập nhật.

Một `LongAccumulator` nhận hàm nhị phân và identity lúc tạo:

```java
// Đoạn minh họa.
LongAccumulator maximum =
    new LongAccumulator(
        Long::max,
        Long.MIN_VALUE
    );
```

Các luồng gọi `maximum.accumulate(x)`. Tài liệu Java yêu cầu:

- Hàm tích lũy **không có tác dụng phụ**, vì nó có thể được tính lại khi CAS thất bại.
- **Thứ tự kết hợp giá trị không được bảo đảm** giữa hoặc trong các luồng.
- Để kết quả dự đoán được, hàm nên **kết hợp** (*associative*) và **giao hoán** (*commutative*).
- Cần một **identity** phù hợp để `f(identity, x)=x` theo ý nghĩa phép gộp.

Ví dụ phù hợp: `Long::sum` với identity `0L`, `Long::max` với `Long.MIN_VALUE`, `Long::min` với `Long.MAX_VALUE`.

Ví dụ dễ sai: `(a,b)->a-b`, vì phép trừ không có tính giao hoán/kết hợp theo yêu cầu gộp không xác định thứ tự.

### 12.1. LongAdder khác gì?

`LongAdder` tối ưu trường hợp phổ biến: **đếm và tổng**. Nó không nhận callback do bạn cung cấp cho từng phép `increment`/`add`, vì thế không có vấn đề callback tự viết bị chạy lại. Dưới tranh chấp cao, nó thường đạt throughput tốt hơn một atomic counter duy nhất, đánh đổi bằng không gian và cách lấy tổng.

**`LongAdder.sum()` và `LongAccumulator.get()` không phải snapshot nguyên tử** nếu có các cập nhật concurrent đang diễn ra. `reset()` hoặc `getThenReset()` cần thận trọng khi cập nhật đồng thời; nếu business đòi một kết quả tuyệt đối nhất quán tại một điểm thời gian, cần mô hình đồng bộ khác.

### Ví dụ 7 — AccumulatorDemo.java

```java
import java.util.concurrent.atomic.LongAccumulator;
import java.util.concurrent.atomic.LongAdder;

public class AccumulatorDemo {
    public static void main(String[] args) {
        LongAccumulator maximum =
            new LongAccumulator(
                Long::max,
                Long.MIN_VALUE
            );

        maximum.accumulate(7);
        maximum.accumulate(3);
        maximum.accumulate(9);

        System.out.println("max=" +
            maximum.get());

        System.out.println("getThenReset=" +
            maximum.getThenReset());

        System.out.println("afterReset=" +
            maximum.get());

        LongAdder sum = new LongAdder();
        sum.add(3);
        sum.increment();

        System.out.println("sum=" + sum.sum());
    }
}
```

```bash
javac AccumulatorDemo.java
java AccumulatorDemo
```

Stdout khi không có cập nhật concurrent tại thời điểm đọc:

```text
max=9
getThenReset=9
afterReset=-9223372036854775808
sum=4
```

`Long.MIN_VALUE` là identity của phép lấy maximum; sau reset giá trị trở về identity. Không đọc `getThenReset` như “snapshot transaction” trong lúc nhiều luồng còn cập nhật.

**Lưu ý về số thực:** `DoubleAccumulator` với phép cộng số thực có thể có những khác biệt do rounding của floating-point khi thứ tự gộp đổi. Nếu nghiệp vụ yêu cầu kết quả tiền tệ chính xác, không mặc định phép cộng `double` concurrent là phù hợp; chọn biểu diễn số và yêu cầu nhất quán riêng.

## 13. Atomic arrays và field updaters: cùng nguy cơ retry

Cảnh báo callback chạy lại cũng có ở các phương thức cập nhật phần tử:

```java
// Đoạn minh họa, array đã khởi tạo.
AtomicLongArray slots = new AtomicLongArray(2);

long previous = slots.getAndUpdate(
    0, old -> old * 3
);

long newValue = slots.accumulateAndGet(
    1, 7L, (current, delta) -> current + delta
);
```

Phép cập nhật nguyên tử này áp dụng cho **phần tử tại index được chọn**, không phải một transaction cho cả array. Nếu cần thay đổi đồng thời nhiều index với invariant chung, hai lời gọi atomic riêng biệt không tự bảo đảm trạng thái nhất quán xuyên các phần tử.

### Ví dụ 8 — AtomicArrayDemo.java

```java
import java.util.concurrent.atomic.AtomicLongArray;

public class AtomicArrayDemo {
    public static void main(String[] args) {
        AtomicLongArray values =
            new AtomicLongArray(2);

        values.set(0, 4);

        System.out.println("old=" +
            values.getAndUpdate(
                0, value -> value * 3
            ));

        System.out.println("slot0=" +
            values.get(0));

        System.out.println("slot1=" +
            values.accumulateAndGet(
                1, 7,
                (current, delta) -> current + delta
            ));
    }
}
```

```bash
javac AtomicArrayDemo.java
java AtomicArrayDemo
```

Stdout:

```text
old=4
slot0=12
slot1=7
```

Tương tự, các `AtomicIntegerFieldUpdater`, `AtomicLongFieldUpdater` và `AtomicReferenceFieldUpdater` cập nhật field có điều kiện theo CAS và có thể đánh giá lại lambda khi tranh chấp. Chúng có điều kiện riêng về kiểu field, `volatile`, quyền truy cập và cách tạo updater. Đừng dùng updater chỉ để thay một local counter đơn giản; chọn cấu trúc ít phức tạp nhất đáp ứng đúng nhu cầu.

## 14. Khi hàm cập nhật ném exception

Điều gì xảy ra nếu callback **tự ném exception**?

```java
// Minh họa:
AtomicInteger value = new AtomicInteger(5);

value.updateAndGet(old -> {
    throw new IllegalArgumentException("bad");
});
```

Nếu exception xuất hiện trước khi hàm trả một proposed value, invocation đó **không chốt cập nhật đề xuất**, và exception đi ra caller. Đây **không phải** một tình huống CAS fail rồi tự retry thông thường.

Nhưng nếu callback đã thực hiện side effect trước khi ném exception, side effect không được undo:

```java
// Phản ví dụ:
value.updateAndGet(old -> {
    externalService.writeSomething(); // Có thể đã thành công.
    throw new IllegalStateException("failed");
});
```

`AtomicInteger` không thể rollback external service. Nếu caller retry invocation, action có thể bị gọi lại. Điều này bổ sung thêm lý do phải để callback thuần.

### Ví dụ 9 — FailedFunctionDemo.java

```java
import java.util.concurrent.atomic.AtomicInteger;

public class FailedFunctionDemo {
    public static void main(String[] args) {
        AtomicInteger value =
            new AtomicInteger(5);

        AtomicInteger calls =
            new AtomicInteger();

        try {
            value.updateAndGet(old -> {
                calls.incrementAndGet();

                throw new IllegalArgumentException(
                    "bad"
                );
            });
        } catch (IllegalArgumentException ex) {
            System.out.println("error=" +
                ex.getMessage());
        }

        System.out.println("value=" +
            value.get());

        System.out.println("calls=" +
            calls.get());
    }
}
```

```bash
javac FailedFunctionDemo.java
java FailedFunctionDemo
```

Stdout:

```text
error=bad
value=5
calls=1
```

Không có cạnh tranh khác trong ví dụ: lambda chạy một lần rồi ném exception, nên giá trị vẫn `5`. Không suy luận từ đây rằng mọi callback lỗi đều chỉ chạy một lần trong mọi hoàn cảnh — nếu đã có một số retry thành công về mặt tính toán nhưng thua CAS trước khi một lần đánh giá sau đó ném exception, side effect ở các lần trước có thể vẫn đã xảy ra.

## 15. ABA: CAS có thể thành công dù state từng đổi

Đây là một vấn đề liên quan nhưng **khác** việc lambda bị gọi lại.

CAS chỉ so giá trị kỳ vọng với giá trị hiện tại (với `AtomicReference`, là **tham chiếu object**). Nếu trạng thái đổi:

```text
A -> B -> A
```

thì một CAS dựa trên giá trị kỳ vọng `A` có thể thành công vì hiện tại lại là `A`. CAS không tự biết state đã từng ở `B`.

### Ví dụ 10 — AbaDemo.java

```java
import java.util.concurrent.atomic.AtomicReference;

public class AbaDemo {
    public static void main(String[] args) {
        AtomicReference<String> reference =
            new AtomicReference<>("A");

        String first = reference.get();

        System.out.println("toB=" +
            reference.compareAndSet("A", "B"));

        System.out.println("backA=" +
            reference.compareAndSet("B", "A"));

        System.out.println("staleCAS=" +
            reference.compareAndSet(first, "C"));

        System.out.println("final=" +
            reference.get());
    }
}
```

```bash
javac AbaDemo.java
java AbaDemo
```

Stdout:

```text
toB=true
backA=true
staleCAS=true
final=C
```

Các string literal `"A"` trong ví dụ cùng tham chiếu được intern, nên CAS tham chiếu có thể nhận ra cùng object khi state trở về A.

**Bài học:** CAS chỉ kiểm tra trạng thái hiện tại, không tự kiểm tra lịch sử. Nếu invariant của hệ thống yêu cầu phát hiện một trạng thái đã bị thay đổi rồi khôi phục, cân nhắc **version/stamp**, chẳng hạn `AtomicStampedReference` hoặc immutable state có version được cập nhật cùng CAS.

Không dùng ABA làm giải thích mặc định cho mọi lần CAS fail. Chủ đề chính của bài là: **khi CAS fail thì update function có thể được đánh giá lại**; ABA là một tình huống khác, khi CAS có thể thành công dù đã có thay đổi trung gian.

## 16. Chọn đúng công cụ cho biến tích lũy

| Bài toán | Công cụ nên cân nhắc | Tại sao |
| --- | --- | --- |
| Tăng một số nguyên một đơn vị | `AtomicInteger.incrementAndGet()` | Không cần lambda người dùng |
| Cộng một delta vào một giá trị | `AtomicLong.addAndGet(delta)` | Cập nhật atomic không cần user callback |
| Giá trị mới phụ thuộc vào giá trị hiện tại | `updateAndGet(old -> pureFunction(old))` | CAS retry an toàn nếu function thuần |
| Muốn biết giá trị cũ của cập nhật | `getAndUpdate` | Trả state trước CAS thành công |
| Gộp current với một input cụ thể | `accumulateAndGet`/`getAndAccumulate` | Hàm nhị phân được gọi lại nếu cần |
| Cập nhật một object state | `AtomicReference<ImmutableState>` | Không mutate shared old object |
| Cập nhật phần tử array | `AtomicLongArray` và các lớp tương ứng | Atomic theo index |
| Tính tổng nhiều luồng, thống kê cao tải | `LongAdder` | Throughput tốt; `sum()` không atomic snapshot |
| Tích lũy max/min có thứ tự gộp bất kỳ | `LongAccumulator` với hàm associative/commutative | Phù hợp với phép gộp không có thứ tự |
| External DB/email/payment | Transaction/idempotency/outbox ở tầng nghiệp vụ | CAS trong JVM không bảo đảm exactly-once giữa các hệ thống |
| Phát hiện A→B→A | Version/stamp, `AtomicStampedReference` | CAS thuần không phát hiện lịch sử |
| Bất biến xuyên nhiều biến/key | Thiết kế state/transaction/lock phù hợp | Một atomic variable không tạo transaction đa state |

### 16.1. AtomicInteger hay LongAdder?

`AtomicLong` tiện khi cần **một giá trị atomic đơn nhất** và các phép `get`/CAS có semantics trực tiếp. `LongAdder` thường tốt cho thống kê nhiều luồng cập nhật nhưng `sum()` không phải snapshot nguyên tử khi có write.

Đừng chọn `LongAdder` chỉ vì throughput nếu business cần **kiểm tra ngưỡng và chốt quyết định chính xác** dựa vào state. Cân nhắc tiêu chí nhất quán, ordering và precision trước khi chọn.

### 16.2. Có cần lock không?

CAS thường hiệu quả với phép tính ngắn, nhưng không phải mọi invariant đều phù hợp CAS. Nếu cần giữ đồng nhất nhiều trường mutable hoặc phối hợp với resource khác, một thiết kế bất biến, lock có thứ tự, database transaction hoặc actor/event loop có thể dễ chứng minh đúng hơn. Không cố đưa I/O dài vào CAS lambda để “tránh synchronized”.

## 17. Chi phí contention và độ dài hàm tính

Một lambda tốn nhiều CPU không nhất thiết làm CAS sai, nhưng sẽ **tăng cửa sổ giữa lần đọc old và lần thử CAS**. Trong thời gian tính, các luồng khác có thêm cơ hội thay đổi giá trị, làm CAS thua và yêu cầu tính lại toàn bộ.

Ví dụ:

```java
// Phản ví dụ về chi phí cao.
atomic.updateAndGet(old -> {
    BigDecimal complicated =
        expensiveCalculation(old);

    return complicated.longValueExact();
});
```

Nếu `expensiveCalculation` rất đắt, nó có thể chạy lại nhiều lần dưới tranh chấp. Hệ quả:

- CPU và allocation tăng.
- Latency p95/p99 có thể lớn hơn nhiều so với thời gian chạy một lần.
- Không có giới hạn số lần retry hay cam kết fairness cố định.
- Một thread có thể phải retry lâu dưới tải cao.

**Hướng cải thiện:**

1. Tách phần tính độc lập với old value ra ngoài lambda.
2. Chỉ giữ phép chuyển `old → proposed` ngắn và thuần.
3. Dùng built-in `addAndGet`/`incrementAndGet` nếu chỉ làm số học đơn giản.
4. Khi cần nhiều counter hot, xem xét `LongAdder`/`LongAccumulator` và yêu cầu snapshot.
5. Với invariant phức tạp, cân nhắc cấu trúc dữ liệu/lock khác thay vì CAS loop dài.
6. Đo contention bằng benchmark phù hợp; không tự tạo một con số “callback luôn tối đa N lần” nếu không có policy retry do ứng dụng kiểm soát.

### 17.1. Đừng dùng callback để chờ I/O

Một lambda gọi HTTP/database hoặc `Future.get` có thể mất hàng giây, dễ bị tính lại khi CAS thua. Ngoài side effect, nó còn giữ CPU/task bị chiếm dụng và làm tăng khả năng contention. Nếu cần dữ liệu bên ngoài:

- Lấy dữ liệu với timeout **trước** khi vào callback.
- Snapshot input cần thiết.
- Trong callback chỉ kiểm tra state hiện tại và tạo output nhanh.
- Nếu state đã thay đổi trong lúc I/O, quyết định chấp nhận dữ liệu cũ hay retry I/O theo version/contract.
- Gửi side effect bên ngoài sau khi commit hoặc qua cơ chế transaction/outbox có bảo đảm thích hợp.

**Timeout của I/O không phải timeout của CAS retry.** `updateAndGet` không có tham số timeout cho callback hoặc giới hạn số lần thử.

## 18. Checklist code review

Khi xem một lời gọi `getAndUpdate`, `updateAndGet`, `getAndAccumulate`, `accumulateAndGet` hoặc `LongAccumulator.accumulate`, hãy hỏi:

1. Callback có thể được gọi lại khi CAS fail không? **Có — giả định điều đó luôn có thể xảy ra.**
2. Callback có gửi email, gọi API, ghi DB hoặc phát event không?
3. Callback có thay đổi một biến mutable bên ngoài không?
4. Callback có ghi log/audit theo nghĩa “một event mỗi cập nhật” không?
5. Callback có đọc thời gian/random ngoài để tạo quyết định biến thiên không?
6. Callback có phụ thuộc vào input đã bị thay đổi giữa những lần retry không?
7. Callback có tạo/mutate object cũ đang được các luồng khác chia sẻ không?
8. Có thể chuyển side effect ra **sau** lời gọi atomic khi thành công không?
9. Nếu chuyển ra ngoài, đã xét crash giữa commit và external action chưa?
10. External action có idempotency key/transaction/outbox phù hợp chưa?
11. Phép tính có ngắn và giới hạn thời gian CPU/nhớ không?
12. Có biết sự khác biệt giữa `getAndUpdate` và `updateAndGet` không?
13. Hàm nhị phân có hiểu thứ tự `(current, update)` không?
14. Nếu chỉ cộng 1/delta, có thể dùng `incrementAndGet`/`addAndGet` không?
15. Nếu dùng `LongAccumulator`, phép gộp có associative và commutative không?
16. Identity của accumulator có đúng không?
17. Có hiểu `LongAdder.sum`/`LongAccumulator.get` không là atomic snapshot khi có write không?
18. Nếu cần cùng lúc nhiều state, thiết kế có vượt quá khả năng một atomic variable không?
19. Có xử lý overflow và lỗi validation một cách có chủ đích không?
20. Có test CAS retry **có điều phối**, không chỉ test bằng sleep ngẫu nhiên không?
21. Có test exception xảy ra trước CAS và tác dụng phụ trước exception không?
22. Nếu dùng `AtomicReference`, có cân nhắc ABA và version khi domain yêu cầu không?
23. Benchmark có phản ánh hot-key contention và tải đa luồng không?
24. Hệ thống có giả định callback “đúng một lần” ở lớp atomic khác JDK hay không?

## 19. Anti-pattern thường gặp

### 19.1. Gửi thông báo ngay trong lambda

`atomic.updateAndGet(old -> { sendEmail(); return old+1; })` có thể gửi nhiều email khi CAS thất bại. **Đặt thông báo ngoài lambda**, dùng cơ chế nghiệp vụ để chống phát lại nếu cần.

### 19.2. Trừ tiền trong lambda

`chargeCreditCard()` nằm trong update function là sai về mô hình giao dịch. CAS không rollback khoản thanh toán khi update thất bại. **Đặt thanh toán trong transaction/workflow có idempotency**.

### 19.3. Ghi DB rồi trả về trạng thái mới

Nếu CAS thua, DB đã ghi nhưng atomic chưa commit. **Không dùng atomic variable làm transaction xuyên database**.

### 19.4. Gọi `AtomicInteger.incrementAndGet` trên metric ngoài trong callback

Nếu metric được hiểu là “số business updates thành công”, nó có thể đếm **số lần đánh giá lambda**, không phải số commits. Trong demo, cách đo này có chủ đích để lộ lỗi, **không phải thống kê giao dịch đúng**.

### 19.5. Mutate object cũ rồi return old trong AtomicReference

CAS kiểm tra tham chiếu, không bảo vệ các field đã thay đổi trước CAS. **Dùng immutable state và tạo object mới**.

### 19.6. Tin f(x)=x+1 không an toàn vì không idempotent

Đây là nhầm lẫn. Hàm không idempotent nhưng **thuần** có thể được đánh giá lại đúng trong CAS loop. **Đừng thay điều kiện side-effect-free bằng điều kiện idempotence toán học**.

### 19.7. Tin mỗi update gọi lambda chính xác một lần

Javadoc cho phép reapply khi CAS fail. **Đừng dựa vào số lần callback để tạo ID, gửi log hay cấp quyền**.

### 19.8. Tin callback ném exception vẫn được CAS retry như thường

Exception từ callback được truyền ra; nó không phải một lần CAS thất bại cần thử lại. **Xử lý lỗi theo hợp đồng API**, không mong retry tự động.

### 19.9. Đo kết quả test bằng `Thread.sleep` và ép gọi lambda hai lần

Lịch thực thi thread không bảo đảm tương tác như mong muốn. **Dùng latch/barrier** để tạo interleaving có kiểm soát.

### 19.10. So sánh LongAdder với AtomicLong mà quên snapshot

`LongAdder.sum` có throughput tốt nhưng không nhất thiết là snapshot atomic dưới cập nhật concurrent. **Chọn theo ngữ nghĩa đọc giá trị**.

### 19.11. Dùng phép trừ làm hàm LongAccumulator

Thứ tự tích lũy có thể khác nhau; phép trừ không associative/commutative theo yêu cầu kết quả ổn định. **Dùng phép gộp toán học phù hợp**, ví dụ max/min/sum.

### 19.12. Quên identity khi tạo LongAccumulator

Identity sai có thể làm sai kết quả, đặc biệt với max/min và số âm. **Chọn identity trung tính đúng cho toán tử**.

### 19.13. Dùng callback phụ thuộc clock hoặc random mỗi retry

Đầu ra có thể biến thiên ngoài ý định. **Tạo input ổn định một lần nếu business muốn cố định**, rồi dùng callback thuần.

### 19.14. Gộp hai biến atomic rồi cho rằng transaction nguyên tử

Hai CAS trên hai biến không tự tạo commit chung. **Thiết kế state chung bất biến hoặc transaction riêng** nếu có invariant.

### 19.15. Dùng callback CPU rất nặng

Tăng thời gian giữa read và CAS, dễ fail/recompute dưới contention. **Rút ngắn callback, precompute phần độc lập hoặc thay mô hình**.

### 19.16. Coi CAS thành công chứng minh state chưa từng thay đổi

ABA cho phép giá trị trở về trạng thái cũ. Nếu lịch sử thay đổi quan trọng, **dùng version/stamp**.

### 19.17. In kết quả không ổn định như thể luôn đúng

Số lần retry và thời gian hoàn tất thay đổi theo scheduling. **Test invariant và dùng latch khi cần chứng minh retry**.

### 19.18. Dùng AtomicReference làm an toàn mọi object mutable

Atomic reference chỉ bảo vệ **việc thay tham chiếu**, không làm cấu trúc object bên trong thread-safe. **Dùng immutable snapshots hoặc đồng bộ value**.

## 20. Câu hỏi kiểm tra hiểu biết

**Câu 1.** Vì sao hàm truyền vào `AtomicInteger.updateAndGet` có thể chạy nhiều hơn một lần?

**Đáp án:** Vì một phép CAS có thể thất bại khi luồng khác thay đổi giá trị, nên method phải đọc lại và đánh giá lại hàm trên trạng thái mới.

**Câu 2.** Có phải nếu lambda chạy hai lần thì giá trị bị cộng hai lần bởi cùng invocation không?

**Đáp án:** Không. Các giá trị đề xuất từ lần CAS thất bại không được commit; một invocation hoàn tất thành công chốt một cập nhật.

**Câu 3.** Khi CAS thất bại, email gửi trong lambda có được rollback không?

**Đáp án:** Không. CAS chỉ kiểm soát trạng thái atomic, không rollback side effect ngoài.

**Câu 4.** `getAndUpdate` trả giá trị của lần đọc đầu tiên hay giá trị trước CAS thành công?

**Đáp án:** Giá trị **ngay trước lần cập nhật thành công**.

**Câu 5.** `updateAndGet` trả gì?

**Đáp án:** Giá trị mới đã được cập nhật nguyên tử.

**Câu 6.** Trong `accumulateAndGet(x, f)`, f nhận hai tham số theo thứ tự nào?

**Đáp án:** `(currentValue, suppliedX)`.

**Câu 7.** `f(x)=x+1` có an toàn trong updateAndGet dù không idempotent không?

**Đáp án:** Có, nếu nó thuần, không có side effect và xử lý overflow đúng yêu cầu.

**Câu 8.** Muốn tăng một bộ đếm 1 đơn vị, API đơn giản hơn là gì?

**Đáp án:** `incrementAndGet` hoặc `getAndIncrement`.

**Câu 9.** Vì sao đo “số business commits” bằng cách tăng counter trong lambda là sai?

**Đáp án:** Nó có thể đếm cả các lần đánh giá thất bại do CAS contention.

**Câu 10.** Callback ném exception có tự được retry như CAS fail không?

**Đáp án:** Không. Exception từ hàm tính được truyền ra, lời gọi đó không chốt đề xuất mới.

**Câu 11.** Trong ví dụ có latch, vì sao callback chạy đúng hai lần?

**Đáp án:** Vì lượt đọc đầu được chặn, luồng kia đổi 10→100, khiến CAS đầu của worker thua và nó tính lại từ 100.

**Câu 12.** `AtomicReference` có bảo vệ việc mutate một `ArrayList` được lưu trong reference không?

**Đáp án:** Không. Nó bảo vệ thay tham chiếu, không tự đồng bộ nội dung mutable.

**Câu 13.** Cách cập nhật state phức tạp nào thích hợp với AtomicReference?

**Đáp án:** Dùng immutable value/snapshot và trả object mới từ lambda thuần.

**Câu 14.** `LongAccumulator` yêu cầu gì thêm với hàm gộp?

**Đáp án:** Không có side effect; để kết quả dự đoán được, hàm nên associative, commutative và có identity đúng.

**Câu 15.** `LongAdder.sum()` có phải atomic snapshot dưới concurrent updates không?

**Đáp án:** Không.

**Câu 16.** Có thể lấy thời gian/random trong lambda mà vẫn đúng theo mọi lần retry không?

**Đáp án:** Không nên mặc định. Mỗi retry có thể đọc một giá trị khác; nếu business cần input cố định, tạo ngoài rồi capture.

**Câu 17.** Side effect ngoài lambda sau khi method trả về có bảo đảm exactly-once DB/email không?

**Đáp án:** Không. Nó tránh lặp do CAS retry nội bộ, nhưng không tạo transaction xuyên các hệ thống hoặc loại bỏ retry request.

**Câu 18.** `AtomicLongArray.updateAndGet(index,f)` có cập nhật nguyên tử toàn bộ array không?

**Đáp án:** Không; tính nguyên tử áp dụng cho phần tử được chỉ định.

**Câu 19.** ABA là gì?

**Đáp án:** State thay A→B→A, làm CAS so A có thể thành công dù có thay đổi trung gian.

**Câu 20.** Khi nào dùng `AtomicStampedReference`?

**Đáp án:** Khi logic cần biết state đã thay đổi qua version/stamp, không chỉ giá trị hiện tại.

**Câu 21.** Dưới contention cao, callback tính rất lâu gây vấn đề gì?

**Đáp án:** Tăng thời gian chờ, xác suất CAS thua, số lần tính lại và CPU/GC overhead.

**Câu 22.** Làm sao kiểm thử việc reapply chắc chắn thay vì phụ thuộc scheduling?

**Đáp án:** Dùng `CountDownLatch`/barrier để chặn một callback sau lần đọc, cho thread khác cập nhật rồi thả để ép CAS fail.

## 21. Tài liệu Java chính thức

- [Oracle Java SE 27 — AtomicInteger](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): contract `getAndUpdate`, `updateAndGet`, `getAndAccumulate` và `accumulateAndGet`, cảnh báo reapply và side-effect-free.
- [Oracle Java SE 27 — AtomicLong](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): các overload tương ứng cho số nguyên dài.
- [Oracle Java SE 27 — AtomicReference](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): CAS trên object reference và cập nhật qua `UnaryOperator`/`BinaryOperator`.
- [Oracle Java SE 27 — AtomicLongArray](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicLongArray.html): cập nhật theo index và cảnh báo callback có thể được đánh giá lại.
- [Oracle Java SE 27 — LongAccumulator](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/LongAccumulator.html): điều kiện side-effect-free, associative/commutative và vấn đề không bảo đảm thứ tự gộp.
- [Oracle Java SE 27 — LongAdder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counter phân tán, `sum()` không phải snapshot nguyên tử khi còn update.
- [Oracle Java SE 27 — AtomicStampedReference](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicStampedReference.html): dùng stamp/version khi ABA cần được phát hiện.
- [Oracle Java SE 27 — java.util.concurrent.atomic](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/package-summary.html): tổng quan atomic variables và concurrent accumulators.

**Kết luận:** Một phương thức cập nhật CAS có thể **đánh giá lại lambda nhiều lần** nhưng **chỉ chốt giá trị của lần CAS thành công**. Vì vậy lambda cần **không có tác dụng phụ**, có thể tính lại từ state mới và không mutate object đã công bố. Các phép toán cộng đơn giản nên dùng API atomic có sẵn; các accumulator chuyên dụng cần toán tử phù hợp. External event/DB/email phải được xử lý theo transaction và idempotency riêng, không phụ thuộc số lần chạy callback của CAS.