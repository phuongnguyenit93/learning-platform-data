# 9.7. weakCompareAndSet, thất bại giả và điều kiện lặp lại thao tác

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **compare-and-set (CAS)** và điểm khác giữa `VarHandle.compareAndSet` với `VarHandle.weakCompareAndSet`.
2. Mô tả chính xác **thất bại giả** (*spurious failure*): một lần weak CAS có thể trả `false` dù giá trị thực tế lúc so sánh trùng `expectedValue`.
3. Viết vòng lặp **đọc → tính giá trị mới → weak CAS → nếu thất bại thì đọc lại và tính lại**, đảm bảo không làm mất cập nhật do nhiều luồng.
4. Nhận biết tình huống **không nên retry**, điều kiện dừng, rủi ro starvation/livelock, backoff và tác dụng giới hạn của `Thread.onSpinWait()`.
5. Chọn đúng biến thể memory ordering: `weakCompareAndSet`, `weakCompareAndSetPlain`, `weakCompareAndSetAcquire`, `weakCompareAndSetRelease`; tránh nhầm với API có tên tương tự trong `AtomicInteger`.
6. Phân biệt lỗi truy cập/kiểu của `VarHandle` với kết quả `false` bình thường của CAS, và hiểu giới hạn của việc kiểm thử spurious failure trên máy thật.

**Ngữ cảnh:** `VarHandle` trong `java.lang.invoke` là một handle có kiểu mạnh tới một biến: field instance, field static hoặc phần tử mảng. Nó hỗ trợ các chế độ đọc/ghi và cập nhật nguyên tử, với hiệu ứng bộ nhớ khác nhau. Weak CAS thường dùng trong thuật toán đồng thời có vòng lặp retry, nơi một lần thất bại không nhất thiết là kết quả cuối cùng.

## 1. CAS là gì và tại sao phải so sánh trước khi ghi?

Giả sử biến chung `counter` có giá trị `10`. Hai luồng cùng muốn tăng thêm `1`. Cách làm thuần túy:

```java
int old = counter.value;
counter.value = old + 1;
```

Đây chỉ là đoạn minh họa, **không phải thao tác nguyên tử**. Có thể cả hai luồng đọc `10` và cùng ghi `11`; một lần tăng đã bị mất (*lost update*).

CAS thực hiện một phép cập nhật có điều kiện ở một điểm nguyên tử:

```text
CAS(variable, expectedValue, newValue):
    Nếu giá trị hiện tại của variable trùng expectedValue:
        cập nhật nguyên tử thành newValue
        trả true
    Nếu không trùng:
        không cập nhật
        trả false
```

Trên `VarHandle`, chữ ký logic của một instance field kiểu `int` là:

```java
boolean success = VALUE.compareAndSet(holder, expectedValue, newValue);
```

Đây là dòng minh họa: `VALUE` phải là VarHandle tới field `int` của `holder`; các đối số phải có đúng kiểu ở call site. Với phần tử mảng, cần thêm array và index ở phần tọa độ, ví dụ `ARRAY_HANDLE.compareAndSet(array, i, expectedValue, newValue)`.

**Lợi ích của CAS:** một luồng chỉ ghi nếu điều kiện dựa trên snapshot cũ vẫn đúng ở thời điểm thực hiện CAS. Khi luồng khác đã thay đổi biến, lần cập nhật dùng snapshot cũ sẽ thất bại, cho phép ứng dụng đọc lại thay vì ghi đè tiến trình của luồng kia.

## 2. Strong CAS và weak CAS khác nhau ở điểm nào?

### 2.1. `compareAndSet` (strong CAS)

`VarHandle.compareAndSet(...)` cập nhật nguyên tử nếu giá trị chứng kiến (*witness value*) trùng `expectedValue`. Theo hợp đồng API, khi nó trả `false`, giá trị chứng kiến **không trùng** với expected. Strong CAS **không được phép thất bại giả** theo semantics của phương thức này.

Điều đó **không** có nghĩa lần gọi luôn thành công; trong hệ thống nhiều luồng, giá trị có thể bị luồng khác đổi giữa lần đọc trước đó và thao tác CAS.

### 2.2. `weakCompareAndSet` (weak CAS)

`VarHandle.weakCompareAndSet(...)` cũng thực hiện cập nhật **nguyên tử khi thành công** và trả boolean. Nhưng API cho phép nó **trả `false` ngay cả khi witness value trùng expected**. Đây chính là spurious failure. Khi weak CAS thất bại, lần gọi đó không thực hiện phép ghi dự kiến; nhưng các luồng khác có thể đã thay đổi biến.

| Tiêu chí | `compareAndSet` | `weakCompareAndSet` |
| --- | --- | --- |
| Ghi nguyên tử nếu thành công | Có | Có |
| Trả `true` | Cập nhật của lần gọi đã thành công | Cập nhật của lần gọi đã thành công |
| Trả `false` khi current khác expected | Có | Có |
| Được phép trả `false` khi current vẫn bằng expected | **Không** | **Có: spurious failure** |
| Có thể dùng một lần để khẳng định “expected không trùng”? | Có, cho giá trị witness lúc CAS | **Không** |
| Phù hợp vòng lặp đọc-lại/tính-lại/retry | Có | Có, và **bắt buộc xét spurious failure** |
| Hiệu ứng bộ nhớ của phương thức không hậu tố trên `VarHandle` | Volatile read/write | Volatile read/write |

Một weak CAS thành công không phải là “ghi yếu, chưa chắc đã ghi”. **Thành công vẫn bảo đảm cập nhật có điều kiện là nguyên tử**. “Weak” chủ yếu là việc **được phép thất bại giả**, không phải permission để cập nhật một phần hay trả `true` mà không làm gì.

### 2.3. Trả `false` không phải exception

Nếu `weakCompareAndSet(...)` trả `false`, đó là kết quả **được dự kiến trong hợp đồng API**, không phải `IllegalStateException`. Vì vậy không nên coi mọi `false` là lỗi hệ thống hay ném exception ngay lập tức. Ngược lại, `WrongMethodTypeException` hoặc `UnsupportedOperationException` khi gọi VarHandle thường là lỗi về cách dùng handle, không phải “một lần CAS chưa thắng” để retry vô hạn.

## 3. Thất bại giả (*spurious failure*) là gì?

Ví dụ biến chung đang là `7`, caller thử:

```java
boolean updated = VALUE.weakCompareAndSet(holder, 7, 8);
```

Hai loại tình huống làm `updated == false`:

1. **Expected mismatch:** vào thời điểm so sánh, giá trị đã là `9` (một luồng khác cập nhật), không còn là `7`.
2. **Spurious failure:** giá trị chứng kiến vẫn là `7`, nhưng phép **weak** CAS được phép báo thất bại mà không thực hiện ghi.

Caller **không thể** dựa trên một boolean `false` để biết chắc nguyên nhân nào xảy ra. Không có API báo kèm cờ “đây là thất bại giả”. Nếu cần biết giá trị hiện tại, phải thực hiện một lần đọc thích hợp; ngay cả giá trị đọc sau đó cũng có thể đã đổi, nên thường không thể tái dựng chính xác lịch sử của lần CAS cũ.

### 3.1. Vì sao API cho phép thất bại giả?

Trên một số kiến trúc/triển khai, primitive đồng bộ hóa mức thấp có thể báo thất bại khi cạnh tranh hoặc khi một cặp lệnh load-reserved/store-conditional không giữ được điều kiện nội bộ. Weak CAS cho phép triển khai tận dụng kiểu thao tác đó mà không bắt buộc che mọi thất bại bằng retry ở tầng thư viện.

Đây là **quyền được thất bại giả theo hợp đồng**, không phải cam kết rằng mọi JVM/mọi máy đều sẽ tạo ra spurious failure. Trên nhiều máy, thử hàng triệu lần vẫn có thể không quan sát thấy. Không được viết unit test bắt buộc phải nhìn thấy một thất bại giả để coi triển khai đúng.

### 3.2. Không suy ra “có cạnh tranh” chỉ từ `false`

Ngay cả khi chỉ có một luồng chạm biến, weak CAS **vẫn được phép** trả `false`. Ngược lại, khi nhiều luồng cạnh tranh, một lần CAS có thể thành công. Vì vậy:

- `false` không chứng minh có thread khác vừa ghi;
- `false` không chứng minh lỗi memory ordering;
- `true` chứng minh lần cập nhật có điều kiện của caller đã thành công, nhưng **không bảo đảm giá trị vẫn còn nguyên ở thời điểm đọc sau đó**, vì một luồng khác có thể cập nhật tiếp.

## 4. Mẫu retry đúng: đọc lại và tính lại giá trị mới

Một vòng lặp tăng biến `int` bằng weak CAS:

```java
static void increment(Holder holder) {
    for (;;) {
        int observed = (int) VALUE.getVolatile(holder);
        int next = observed + 1;

        if (VALUE.weakCompareAndSet(holder, observed, next)) {
            return;
        }

        Thread.onSpinWait();
    }
}
```

Đây là **method minh họa**, cần được đặt trong class có `Holder` và `VALUE` đã lookup đúng field. Phần 7 có chương trình chạy độc lập.

Luồng xử lý:

1. **Read:** đọc giá trị hiện tại bằng access mode phù hợp, ở đây là `getVolatile`.
2. **Compute:** tính giá trị đề xuất từ snapshot vừa đọc.
3. **Attempt:** `weakCompareAndSet(holder, observed, next)`.
4. **Success:** nếu `true`, thao tác tăng của **lần gọi này** đã được thực hiện; kết thúc.
5. **Failure:** nếu `false`, không kết luận tại sao; quay về bước **read** và tính lại.

Tại sao phải đọc lại? Giả sử luồng A đã đọc `10`, còn luồng B cập nhật biến thành `11`. Nếu A cứ cố `weakCompareAndSet(holder, 10, 11)` không đổi expected, nó sẽ tiếp tục thất bại chừng nào biến không trở lại `10`. Cập nhật đúng của A phải là đọc `11`, rồi đề xuất `12`.

### 4.1. Vòng lặp sai: giữ expected cũ mãi

```java
int expected = (int) VALUE.getVolatile(holder);
while (!VALUE.weakCompareAndSet(holder, expected, expected + 1)) {
    // SAI: expected không đổi; nếu giá trị thực đã đổi thì có thể lặp vô hạn.
}
```

Đoạn trên **không phải chương trình độc lập**, chỉ minh họa lỗi. Chỉ retry y nguyên có thể hữu ích trong một trường hợp rất đặc biệt khi có **bằng chứng không luồng nào thay đổi trạng thái và phép retry vẫn hợp lệ**, nhưng thường không đúng cho bài toán read-modify-write có cạnh tranh. Không thể viết thuật toán tổng quát dựa trên giả định đó.

### 4.2. Vòng lặp sai: bỏ qua `false`

```java
int snapshot = (int) VALUE.getVolatile(holder);
VALUE.weakCompareAndSet(holder, snapshot, snapshot + 1);
// SAI nếu yêu cầu phải hoàn tất một lần tăng: false bị bỏ qua.
```

Với nghiệp vụ yêu cầu “mỗi request đã được chấp nhận phải tăng đúng một lần”, bỏ qua kết quả có thể làm mất cập nhật, ngay cả khi không có cạnh tranh thực tế (do spurious failure).

### 4.3. Vòng lặp sai: fallback `set` trực tiếp sau khi thất bại

```java
int old = (int) VALUE.getVolatile(holder);
if (!VALUE.weakCompareAndSet(holder, old, old + 1)) {
    VALUE.setVolatile(holder, old + 1); // SAI: có thể ghi đè update của thread khác.
}
```

`setVolatile` là ghi volatile, **không** phải một read-modify-write có điều kiện. Nó không kiểm tra giá trị cũ còn đúng hay không. Mẫu đúng là đọc lại và thử CAS lại, hoặc chuyển sang một primitive atomic-update phù hợp như `getAndAdd`.

## 5. Khi nào được retry, khi nào phải dừng?

Không phải cứ thấy `false` là spin không giới hạn. Phải căn cứ vào **mục tiêu nghiệp vụ** và **tính đúng đắn của phép cập nhật**.

| Trường hợp | Hành động phù hợp |
| --- | --- |
| Tăng bộ đếm dùng snapshot cũ | Đọc lại giá trị; tính giá trị tăng mới; CAS lại |
| Cập nhật trạng thái có điều kiện “chỉ nếu state vẫn là OPEN” | Đọc lại; nếu state khác OPEN thì **dừng theo hợp đồng**, không ép nó quay lại |
| Một phép cập nhật optional/best-effort | Có thể ghi nhận thất bại mà không retry, **nếu** hợp đồng cho phép và hiểu rằng `false` có thể là spurious |
| Mỗi request bắt buộc được ghi một lần | Retry an toàn hoặc chọn atomic API mạnh hơn; **không bỏ qua `false`** |
| Có cancellation, deadline hay ngân sách thử | Kiểm tra điều kiện dừng và trả lỗi/đánh dấu chưa hoàn thành/fallback phù hợp |
| Vòng lặp có xử lý side effect bên ngoài | Không lặp lại side effect cùng với CAS; tách tính trạng thái thuần túy khỏi I/O hoặc hành động không idempotent |

### 5.1. Kiểm tra lại điều kiện nghiệp vụ

Ví dụ yêu cầu “chỉ chuyển `OPEN -> CLAIMED`”, trong đó `OPEN=0` và `CLAIMED=1`:

```java
static boolean claim(Job job) {
    for (;;) {
        int state = (int) STATE.getVolatile(job);
        if (state != 0) {
            return false; // Trạng thái không còn OPEN: không retry để ghi đè.
        }
        if (STATE.weakCompareAndSet(job, 0, 1)) {
            return true;
        }
        Thread.onSpinWait(); // Có thể là spurious failure: đọc lại và thử tiếp.
    }
}
```

Đây là **method minh họa** với `Job` và `STATE` tương ứng, không phải file Java độc lập. Sau `false`, phải quay về kiểm tra state. Nếu state chuyển sang `CANCELLED`, phép claim không còn hợp lệ; không được cứ retry nhằm “ép một lần thành công”.

**Điểm tinh tế:** `return false` trong ví dụ này có nghĩa **nghiệp vụ không claim được vì trạng thái đã không còn OPEN**, không phải phép weak CAS đơn lẻ trả `false`. Hai loại boolean này có ngữ nghĩa khác nhau.

### 5.2. Không lặp lại I/O hoặc side effect không an toàn

Đừng viết:

```java
for (;;) {
    int old = (int) VALUE.getVolatile(holder);
    sendPayment(); // SAI: có thể chạy nhiều lần khi weak CAS thất bại.
    if (VALUE.weakCompareAndSet(holder, old, old + 1)) {
        break;
    }
}
```

Đây chỉ là **phản ví dụ**. Hàm `sendPayment()` tượng trưng cho side effect bên ngoài; không tồn tại trong chương trình hoàn chỉnh. Weak CAS có thể thất bại vì cạnh tranh **hoặc** spurious failure; việc gọi lại thanh toán sẽ bị lặp. Thay vào đó, dùng CAS để **giành quyền thực hiện** trước, bảo đảm trạng thái thống nhất; phần side effect được quản lý bằng idempotency key, transaction/outbox hoặc cơ chế đáng tin tùy yêu cầu.

### 5.3. Tiến triển và giới hạn vòng lặp

Weak CAS **không bảo đảm** rằng thử lại sẽ luôn thành công sau một số lần cố định. Tại mức hợp đồng, có thể xảy ra liên tiếp các spurious failures. Với cạnh tranh mạnh, một thread có thể liên tục bị luồng khác thắng; không nên khẳng định “mỗi thread chắc chắn thành công” chỉ vì dùng CAS.

- **Safety:** mỗi lần `weakCompareAndSet` báo `true` có cập nhật nguyên tử đúng expected.
- **Liveness:** khả năng **cuối cùng** đạt `true` phụ thuộc tiến triển của hệ thống, cạnh tranh, scheduling và thuật toán bao quanh. Không tự suy từ safety ra fairness hoặc wait-freedom.
- Nếu caller có deadline, cân nhắc giới hạn số lần retry, timeout hoặc fallback. Khi thoát vòng lặp mà chưa thành công, **phải** trả về trạng thái chưa hoàn tất; đừng giả thành công.

`Thread.onSpinWait()` (Java 9+) là *hint* cho runtime/CPU khi đang spin. Nó **không** ngủ theo thời lượng xác định, **không** bảo đảm yield CPU, **không** làm CAS mạnh lên và **không** thay được một thuật toán backoff/blocking đúng. Nếu đợi lâu hoặc có contention lớn, có thể cân nhắc backoff có giới hạn, `Thread.yield()`/`LockSupport.parkNanos(...)` hay một primitive đồng bộ hóa khác sau khi đo đạc; đừng thêm delay ngẫu nhiên nếu chưa có lý do.

## 6. Memory ordering: đừng chỉ nhìn chữ “weak”

`VarHandle` tách biệt hai trục:

1. **CAS yếu hay mạnh:** có được phép spurious failure không?
2. **Memory ordering:** đọc/ghi theo hiệu ứng Plain, Acquire, Release hay Volatile?

Với Java SE 17, các biến thể weak CAS là:

| Access mode của `VarHandle` | Hiệu ứng đọc witness | Hiệu ứng ghi khi CAS thành công | Có thể thất bại giả? |
| --- | --- | --- | --- |
| `weakCompareAndSetPlain` | Tương tự `get` (plain) | Tương tự `set` (plain) | Có |
| `weakCompareAndSetAcquire` | Tương tự `getAcquire` | Tương tự `set` (plain) | Có |
| `weakCompareAndSetRelease` | Tương tự `get` (plain) | Tương tự `setRelease` | Có |
| `weakCompareAndSet` | Tương tự `getVolatile` | Tương tự `setVolatile` | Có |
| `compareAndSet` | Tương tự `getVolatile` | Tương tự `setVolatile` | **Không** |

Bảng mô tả các **hiệu ứng bộ nhớ theo đặc tả VarHandle**, không có nghĩa Java thực thi thao tác bằng hai lời gọi `get` rồi `set` tách rời: CAS thành công vẫn là cập nhật **nguyên tử**.

### 6.1. Vì sao ví dụ chính dùng `getVolatile` và `weakCompareAndSet`?

Bài toán counter có nhiều luồng truy cập cần semantics chia sẻ rõ ràng. Mẫu chính dùng `getVolatile` để đọc snapshot và `weakCompareAndSet` (volatile semantics) để thử ghi nguyên tử. Mẫu đó đơn giản để học và không phụ thuộc vào một protocol publication yếu hơn.

Có thể tối ưu bằng một số access mode Acquire/Release/Plain **chỉ khi** thiết kế JMM cho toàn bộ dữ liệu chia sẻ đã được chứng minh đúng. Đổi `weakCompareAndSet` sang `weakCompareAndSetPlain` trong một thuật toán đã dùng volatile để phối hợp luồng có thể **làm yếu memory ordering** và tạo bug khó tái hiện. Không phải vì nó vẫn CAS nguyên tử mà nó tự bảo đảm publication/visibility của mọi dữ liệu liên quan.

### 6.2. Acquire/Release không giống Volatile toàn phần

- **Acquire** ở phía đọc giúp ràng buộc những truy cập theo sau với publication bằng Release tương ứng.
- **Release** ở phía ghi giúp đưa những truy cập trước đó vào quan hệ ordering phù hợp khi phía nhận dùng Acquire.
- **Plain** không cung cấp các ràng buộc ordering liên luồng tương ứng.
- **Volatile** cung cấp semantics mạnh hơn, bao gồm các bảo đảm ordering theo JMM cho volatile accesses.

Một CAS **Release** thành công không tự cho phép caller suy ra nó cũng có Acquire semantics ở phía đọc. Ngược lại một CAS **Acquire** không tự cung cấp Release semantics cho bước ghi. Đừng phối hợp các mode chỉ dựa trên tên phương thức; phải xác định rõ dữ liệu nào được publish, luồng nào consume, và quan hệ happens-before cần có.

### 6.3. Đặc biệt: `AtomicInteger.weakCompareAndSet` KHÁC `VarHandle.weakCompareAndSet`

Đây là bẫy API quan trọng trong Java 17:

- `VarHandle.weakCompareAndSet(...)`: **volatile** memory effects theo đặc tả `VarHandle`.
- `AtomicInteger.weakCompareAndSet(expected, update)`: phương thức tên cũ đã **deprecated từ Java 9** vì **plain** memory effects nhưng tên dễ khiến người đọc tưởng là volatile.
- Trong `AtomicInteger`, cách đặt tên rõ nghĩa là `weakCompareAndSetPlain`, `weakCompareAndSetAcquire`, `weakCompareAndSetRelease` và `weakCompareAndSetVolatile`.
- Không sao chép ghi chú “weakCompareAndSet có plain semantics” từ `AtomicInteger` rồi gán cho `VarHandle.weakCompareAndSet`.

Phân biệt này cần thiết khi chuyển code giữa hai API hoặc kiểm tra tác dụng memory ordering của thuật toán. Dù có tên gần giống, **hợp đồng từng phương thức cụ thể mới là nguồn xác nhận**.

## 7. Chương trình Java 17+ hoàn chỉnh: concurrent weak CAS với retry

Tạo file **`WeakCasGuide.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class WeakCasGuide {
    static final class Counter {
        volatile int value;
    }

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup().findVarHandle(
                    Counter.class, "value", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    static void increment(Counter counter) {
        for (;;) {
            int observed = (int) VALUE.getVolatile(counter);
            if (VALUE.weakCompareAndSet(counter, observed, observed + 1)) {
                return;
            }
            Thread.onSpinWait();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        boolean wrongExpected = VALUE.weakCompareAndSet(counter, 1, 99);
        System.out.println("wrongExpected=" + wrongExpected);

        int workers = 4;
        int incrementsPerWorker = 10_000;
        Thread[] threads = new Thread[workers];
        for (int i = 0; i < workers; i++) {
            threads[i] = new Thread(() -> {
                for (int j = 0; j < incrementsPerWorker; j++) {
                    increment(counter);
                }
            });
            threads[i].start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        System.out.println("afterWeak=" + (int) VALUE.getVolatile(counter));
        boolean strong = VALUE.compareAndSet(counter, 40_000, 40_001);
        System.out.println("strong=" + strong);
        System.out.println("final=" + (int) VALUE.getVolatile(counter));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 WeakCasGuide.java
java WeakCasGuide
```

**Stdout khi các worker hoàn tất thành công (đã được kiểm chứng):**

```text
wrongExpected=false
afterWeak=40000
strong=true
final=40001
```

**Phân tích:**

1. `Counter.value` khởi tạo mặc định bằng `0`. `weakCompareAndSet(counter, 1, 99)` dùng expected `1` nên chắc chắn trả `false` khi chưa có thread nào khác thay đổi biến. Dòng `wrongExpected=false` là ví dụ **expected mismatch**, không chứng minh đã có thất bại giả.
2. Mỗi thread thực hiện 10.000 lần gọi `increment`. Bên trong, nếu một lần weak CAS không thành công vì expected mismatch **hoặc** spurious failure, thread đọc lại và tính `observed + 1` từ dữ liệu mới. Tổng có 4 × 10.000 cập nhật thành công, nên sau khi các thread kết thúc, giá trị là `40000`.
3. `Thread.join()` bảo đảm main chờ các thread hoàn tất, nên sau đó không còn writer từ các thread demo này. `compareAndSet(counter, 40000, 40001)` thành công với expected đã biết, kết quả `true` và giá trị cuối `40001`.
4. `Counter` được đặt nested trong `WeakCasGuide`, và `MethodHandles.lookup().findVarHandle` tìm đúng field instance `int`. Với handle này, call-site signature tương ứng là `(Counter, int expected, int newValue)boolean`.
5. Chương trình không có output cho số lần spurious failure vì API không phân loại nguồn thất bại; số lần `false` do contention cũng phụ thuộc lịch chạy nên không in ra để tránh khẳng định sai.

**Lưu ý về liveness:** mẫu code cho một tác vụ counter không ngừng thử cho tới khi cập nhật thành công. Trên JVM/hardware thực tế, chương trình này đã chạy với kết quả trên. Tuy nhiên đặc tả cho phép weak CAS liên tục thất bại giả, nên không được suy từ demo rằng thời gian hoàn tất hoặc số lần retry được bảo đảm về mặt hình thức. Trong production, đặt deadline, giới hạn contention và fallback theo hợp đồng hệ thống khi cần.

## 8. Trường hợp bổ sung: atomic array và reference

`VarHandle` không chỉ áp dụng cho field instance. Với mảng, có thể lấy handle như sau:

```java
VarHandle element = MethodHandles.arrayElementVarHandle(int[].class);
int[] scores = {10, 20};
boolean ok = element.weakCompareAndSet(scores, 0, 10, 11);
```

Đây là **đoạn minh họa** trong class đã import `MethodHandles` và `VarHandle`. Vì weak CAS có thể thất bại giả, `ok` có thể là `false` ngay cả khi phần tử còn `10`; nếu nghiệp vụ yêu cầu cập nhật, phải retry theo điều kiện thích hợp. Mỗi call tới array element VarHandle phải có tọa độ array + index, khác với tọa độ receiver của instance field.

### 8.1. Reference CAS so sánh identity, không gọi `equals`

Với field kiểu reference, giá trị witness được so với expected theo **identity `==`**, không tự gọi `equals()`:

```java
String a = new String("x");
String b = new String("x");
// a.equals(b) == true, nhưng a == b là false.
```

Đây là minh họa độc lập. Nếu state hiện tại là reference `a` còn expected là `b`, CAS có thể không thành công dù `a.equals(b)` là `true`. Khi thiết kế lock-free structure dựa trên object identity, phải hiểu chính xác invariant này.

### 8.2. Vấn đề ABA không được giải quyết chỉ bằng weak CAS

Giả sử một biến tham chiếu đi từ `A → B → A`. Một thread quan sát `A` từ trước có thể thử CAS với expected `A` và thành công sau khi biến quay lại `A`, dù đã có **thay đổi trung gian**. Đây là *ABA problem*, xảy ra với cả strong và weak CAS. Retry do spurious failure **không** ngăn được ABA.

Nếu ứng dụng phải phân biệt các phiên bản khác nhau của trạng thái, hãy cân nhắc dữ liệu bất biến gắn version, `AtomicStampedReference` hoặc thuật toán có cơ chế nhận diện thay đổi phù hợp. Việc thêm stamp phải là một phần của protocol đúng, không chỉ là biến phụ ghi không nguyên tử.

## 9. Điều kiện để retry an toàn trong hệ thống thực

### 9.1. Hàm cập nhật cần có tính thuần túy

CAS loop thường phải tính `newValue = f(observedValue)`. Hàm `f` nên **deterministic/không tạo side effect không thể lặp** với một snapshot. Khi CAS thất bại và retry, việc chạy `f` lần nữa phải an toàn.

Đặc biệt tránh:
- trừ tiền / gửi email / ghi file / gọi API bên ngoài **trước khi** giành được quyền bằng CAS;
- sinh một sự kiện external duy nhất bên trong vòng lặp mà không có cơ chế idempotency;
- giữ tài nguyên/lock trong vòng lặp spin khiến thread khác không thể tạo tiến triển.

### 9.2. Tách retryable conflict và business rejection

Giả sử trạng thái ban đầu là `PENDING`. Nếu một luồng khác đã chuyển nó sang `CANCELLED`, một cập nhật “chuyển từ PENDING sang RUNNING” **phải từ chối** chứ không cứ retry với expected mới để ghi thành RUNNING. Vòng lặp đúng cần kiểm tra **điều kiện nghiệp vụ sau mỗi lần đọc** trước khi thử CAS.

Sự thất bại giả cũng yêu cầu không từ chối nghiệp vụ quá sớm khi state vẫn còn đáp ứng điều kiện. Như vậy có hai câu hỏi riêng:

1. **Điều kiện nghiệp vụ vẫn hợp lệ?** Nếu không, dừng.
2. **CAS có thành công chưa?** Nếu chưa nhưng điều kiện vẫn hợp lệ, có thể thử lại.

### 9.3. Khi contention cao hoặc deadline ngắn

- Không spin nóng không giới hạn trên một tác vụ có thời hạn chặt.
- Có thể đếm số lần thất bại, áp dụng backoff hoặc chuyển sang cơ chế khóa phù hợp.
- Nếu giới hạn retry đạt ngưỡng, cần **trả kết quả chưa hoàn tất** hoặc dùng fallback có khả năng hoàn tất thao tác; tuyệt đối không báo success giả.
- Nếu mỗi thread có ưu tiên khác nhau, chọn policy công bằng ở cấp hệ thống. Weak CAS riêng lẻ không có fairness guarantee.
- Benchmark cần mô hình nhiều luồng, mức contention và hành vi GC hợp lý; không kết luận weak CAS luôn nhanh hơn strong CAS trên mọi kiến trúc.

### 9.4. Có nên dùng `getAndAdd` thay vì viết CAS loop?

Nếu mục tiêu đơn thuần là cộng `delta` vào một field nguyên, `VarHandle.getAndAdd(...)` hoặc `AtomicInteger.incrementAndGet()` thường đơn giản hơn và tránh phải viết lại retry policy. CAS loop hữu ích khi `newValue` phụ thuộc một phép kiểm tra hoặc chuyển đổi phức tạp hơn, không có atomic primitive trực tiếp.

Lựa chọn dựa trên **bảo đảm cần có**, mức độ rõ ràng của contract và kết quả đo hiệu năng, không dựa chỉ trên chữ “weak”.

## 10. Kiểm thử spurious failure và logic retry

### 10.1. Điều gì có thể kiểm chứng trực tiếp?

Có thể viết test:

- Với expected **chắc chắn sai** trong điều kiện không writer, `weakCompareAndSet` phải trả `false` và không thay đổi giá trị.
- Với thuật toán retry và nhiều thread, sau khi hoàn tất, tổng cập nhật không bị mất.
- Kiểm thử điều kiện nghiệp vụ: khi state không còn phù hợp, hàm phải dừng thay vì update sai.
- Kiểm thử timeout, cancellation, fallback và bảo toàn dữ liệu khi hết retry budget.
- Kiểm thử memory ordering bằng phương pháp stress test/JMM phù hợp nếu thiết kế dùng Plain/Acquire/Release.

### 10.2. Điều gì không thể dựa vào một lần chạy?

Không thể bắt buộc `weakCompareAndSet` **phải** thất bại giả. Một JVM có thể hoàn thành mọi lần weak CAS với expected trùng trong test. Vì vậy test cần kiểm tra **hành vi khi attempt trả `false`**, chứ không chờ JVM tự phát ra spurious failure để đi qua nhánh retry.

Một cách kiểm thử logic độc lập là đặt **lớp trừu tượng cho thao tác CAS** rồi tiêm một implementation giả định trả `false` ở một vài lần đầu ngay cả khi state chưa thay đổi, sau đó trả thành công. Test này chứng minh **mã retry của ứng dụng** không phụ thuộc false == mismatch; nó không khẳng định JVM đã tạo spurious failure thật. Với concurrent algorithm phức tạp, cần thêm linearizability test, stress/interleaving test hoặc công cụ nghiên cứu mô hình bộ nhớ thích hợp.

### 10.3. Không đếm tất cả false thành spurious

Khi log `attempts` và `failures`, số `false` là **tổng** false do expected mismatch và false giả. Ngay cả khi đọc lại cùng giá trị sau một `false`, không thể chắc chắn đó là spurious failure: một luồng khác có thể thay đổi qua lại giữa hai lần đọc (ABA). Vì vậy không có phép thống kê tỷ lệ spurious chính xác chỉ từ số lần false trong code tổng quát.

## 11. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Cho rằng weak CAS false luôn là cạnh tranh | API cho phép spurious failure | Retry khi nghiệp vụ còn hợp lệ; đọc lại snapshot |
| Chỉ thử một lần rồi kết luận “không còn quyền cập nhật” | False không chứng minh expected mismatch | Kiểm tra state hiện tại/điều kiện nghiệp vụ |
| Dùng expected cũ mãi trong vòng lặp | Khi state đổi, CAS có thể thất bại vô hạn | Đọc lại và tính lại new value |
| Ghi `setVolatile` để “bù” cho CAS thất bại | Ghi trực tiếp có thể đè cập nhật của thread khác | Retry CAS hoặc atomic RMW khác |
| Dùng `weakCompareAndSetPlain` như Volatile | Plain không có ordering của Volatile | Chọn đúng access mode theo JMM |
| Nhầm `AtomicInteger.weakCompareAndSet` với `VarHandle.weakCompareAndSet` | API AtomicInteger cũ là deprecated/plain, VarHandle không hậu tố có volatile semantics | Đọc đúng đặc tả từng API |
| In log mỗi lần false là “spurious” | Không tách được hai nguyên nhân | Ghi nhận CAS failure chung |
| Chạy side effect trước CAS rồi retry | Side effect có thể bị lặp nhiều lần | Giành quyền trước; idempotency cho external effects |
| Tuyên bố weak CAS luôn cuối cùng sẽ thành công | Không có bounded retry/fairness guarantee | Thiết kế cancellation/budget/fallback |
| Cho rằng Thread.onSpinWait làm thread ngủ hoặc bảo đảm fairness | Chỉ là performance hint | Dùng backoff/blocking khi cần |
| Bỏ qua ABA | Cả strong/weak CAS không tự phát hiện A→B→A | Version/stamp hoặc thuật toán có kiểm soát |
| Bắt `WrongMethodTypeException` rồi retry CAS mãi | Lỗi call-site/typing không phải false do cạnh tranh | Sửa chữ ký VarHandle và kiểu đối số |

## 12. Bài tập củng cố

**Bài 1 — Giải thích hai lần false.** Biến hiện là `5`. Lần thử `weakCompareAndSet(holder, 5, 6)` trả `false`. Có thể kết luận một luồng khác đã đổi biến không?

**Đáp án:** Không. False có thể do witness khác expected **hoặc** thất bại giả dù witness vẫn `5`.

**Bài 2 — Sửa vòng lặp.** Hãy sửa đoạn sau để mỗi request tăng đúng một lần khi thành công:

```java
int original = (int) VH.getVolatile(holder);
while (!VH.weakCompareAndSet(holder, original, original + 1)) {
    Thread.onSpinWait();
}
```

**Gợi ý:** Đưa lần đọc `getVolatile` và phép tính `original + 1` **vào trong vòng lặp**; chỉ thoát khi một lần CAS trả `true`. Đây là đoạn trích minh họa, không phải file độc lập.

**Bài 3 — Chọn access mode.** Một protocol cần đảm bảo publication theo Release và phía nhận đọc bằng Acquire. Chỉ dùng `weakCompareAndSetPlain` để publish liệu có tự bảo đảm cần thiết không?

**Đáp án:** Không. Plain không tương đương Release; cần chọn mode phù hợp như `weakCompareAndSetRelease` và thiết kế đúng phía đọc Acquire, đồng thời xác thực toàn bộ protocol.

**Bài 4 — So sánh API.** Trong Java 17, `VarHandle.weakCompareAndSet` và `AtomicInteger.weakCompareAndSet` có cùng memory effects không?

**Đáp án:** Không. Phương thức VarHandle không hậu tố có volatile effects. Phương thức cùng tên cũ của AtomicInteger là deprecated và có plain effects; thay bằng `weakCompareAndSetVolatile` nếu thật sự cần volatile ordering trong AtomicInteger.

**Bài 5 — Progress và safety.** Một thread spin bằng weak CAS, luôn tính đúng và không ghi sai dữ liệu; có chứng minh thread đó sẽ kết thúc trong tối đa 1.000 lần thử không?

**Đáp án:** Không. Tính nguyên tử/safety của CAS không tự tạo bounded liveness. Spurious failure và contention đều có thể trì hoãn thành công; cần thêm policy tiến triển nếu hệ thống có giới hạn thời gian.

## Tài liệu chính thức

- [Java SE 17 — java.lang.invoke.VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): `compareAndSet`, `weakCompareAndSet`, các biến thể Plain/Acquire/Release và memory semantics.
- [Java SE 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): phân biệt `weakCompareAndSet` cũ (deprecated/plain) với `weakCompareAndSetVolatile`.
- [Java Language Specification, Java SE 17 — Chapter 17, Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): nền tảng happens-before và memory model.

## Kết luận

`VarHandle.weakCompareAndSet` là phép cập nhật **nguyên tử có điều kiện**, nhưng được phép báo `false` do **thất bại giả**, ngay cả khi witness trùng expected. Vì vậy một boolean false **không đủ** để kết luận có cạnh tranh, và thuật toán cần retry phải **đọc lại, kiểm tra lại điều kiện nghiệp vụ, tính lại giá trị mới rồi mới CAS tiếp**. Hãy tách tính đúng đắn của cập nhật khỏi tính sống của vòng lặp, giữ side effect bên ngoài retry, chọn memory ordering phù hợp và không nhầm semantics của `VarHandle.weakCompareAndSet` với phương thức deprecated cùng tên trong `AtomicInteger`.
