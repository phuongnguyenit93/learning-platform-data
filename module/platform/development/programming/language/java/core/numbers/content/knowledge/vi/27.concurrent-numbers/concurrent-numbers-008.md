# BigInteger, BigDecimal bất biến nhưng cập nhật tham chiếu dùng chung vẫn cần phối hợp

## 1. Tình huống: giá trị an toàn, phép cập nhật có thể mất dữ liệu

`java.math.BigInteger` và `java.math.BigDecimal` là các kiểu số **bất biến** (*immutable*): sau khi tạo đối tượng, giá trị và biểu diễn của chính đối tượng đó không bị thay đổi bởi các phép cộng, trừ, nhân, chia. Phép toán tạo **đối tượng kết quả**, rồi trả về tham chiếu đến kết quả.

~~~java
BigInteger before = new BigInteger("100");
BigInteger after = before.add(BigInteger.ONE);

System.out.println(before); // 100
System.out.println(after);  // 101
~~~

Đây là đặc tính rất tốt khi chia sẻ **một đối tượng giá trị** cho nhiều luồng: các luồng có thể cùng đọc và tính toán trên đối tượng đó mà không phải khóa riêng chỉ để bảo vệ nội dung của `BigInteger` hay `BigDecimal`.

Tuy nhiên, có khác biệt quan trọng giữa hai thao tác:

1. **Đọc một số bất biến:** nhiều luồng cùng đọc `BigDecimal price` hoặc `BigInteger constant`, không ai thay đổi nội dung số.
2. **Cập nhật một tham chiếu dùng chung:** nhiều luồng chạy `balance = balance.add(delta)` để đặt tham chiếu `balance` sang một đối tượng mới.

Trường hợp thứ hai chứa chuỗi **đọc → tính → ghi**. Việc tính toán `add()` có thể an toàn, nhưng toàn bộ chuỗi đọc–sửa–ghi không tự động trở thành một hành động nguyên tử (*atomic*).

~~~java
// Đoạn minh họa: biến balance được chia sẻ giữa nhiều luồng.
balance = balance.add(new BigDecimal("1.00"));
~~~

Giả sử cả luồng A và B cùng thấy `balance = 10.00`:

| Thời điểm | Luồng A | Luồng B | Tham chiếu balance |
|---|---|---|---|
| 1 | Đọc đối tượng giá trị `10.00` | | `10.00` |
| 2 | | Đọc đối tượng giá trị `10.00` | `10.00` |
| 3 | Tạo đối tượng mới `11.00` | | `10.00` |
| 4 | | Tạo đối tượng mới `11.00` | `10.00` |
| 5 | Gán balance = `11.00` | | `11.00` |
| 6 | | Gán balance = `11.00` | `11.00` |

Sau hai lần cộng, giá trị cuối vẫn chỉ là **11.00**, trong khi mong đợi **12.00**. Đây là *lost update* (mất cập nhật). Không đối tượng `BigDecimal` nào bị sửa bên trong; lỗi nằm ở cách các luồng phối hợp cập nhật **tham chiếu chung**.

## 2. Phân biệt immutability, visibility và atomicity

Ba thuộc tính này giải quyết ba vấn đề khác nhau:

| Thuộc tính | Câu hỏi | BigInteger/BigDecimal giúp gì? |
|---|---|---|
| **Immutability** (bất biến) | Nội dung của một đối tượng có bị sửa sau khi tạo không? | Có: phép số học không thay đổi toán hạng |
| **Visibility** (khả năng nhìn thấy thay đổi) | Khi luồng A thay tham chiếu, luồng B có nhìn thấy tham chiếu mới đúng theo quy tắc bộ nhớ không? | Bản thân tính bất biến không tạo quan hệ happens-before cho việc thay một trường tham chiếu dùng chung |
| **Atomicity** (nguyên tử) | Phép cập nhật đọc–tính–ghi có diễn ra như một bước duy nhất đối với luồng khác không? | Không: phải phối hợp bằng khóa hoặc thao tác atomic |

Ví dụ:

~~~java
private BigDecimal balance = new BigDecimal("0.00");

// CẢNH BÁO: nếu gọi đồng thời từ nhiều luồng, không có atomicity.
void deposit(BigDecimal delta) {
    balance = balance.add(delta);
}
~~~

Không thể coi `BigDecimal` là "thread-safe" rồi kết luận phương thức `deposit` này cũng thread-safe. Khả năng sử dụng an toàn đối tượng bất biến **không truyền tự động** cho biến hoặc container chứa tham chiếu đến nó.

Tương tự, `BigInteger counter = counter.add(BigInteger.ONE)` không tương đương `AtomicInteger.incrementAndGet()` chỉ vì `BigInteger` bất biến.

### Trường final không có nghĩa trạng thái luôn bất biến

~~~java
final BigDecimal taxRate = new BigDecimal("0.10");
// taxRate = new BigDecimal("0.20"); // Không biên dịch: không thể gán lại biến final.
~~~

Một trường `final BigDecimal` không thể được gán lại qua trường đó sau khi khởi tạo; kết hợp tính bất biến của `BigDecimal`, đây là mô hình tốt để chia sẻ giá trị cố định khi đối tượng được tạo và công bố đúng.

Nhưng:

~~~java
final AtomicReference<BigDecimal> balance =
        new AtomicReference<>(BigDecimal.ZERO);

balance.set(new BigDecimal("1.00")); // Hợp lệ!
~~~

`final` ở đây chỉ giữ cố định **tham chiếu đến đối tượng AtomicReference**, không khóa trạng thái bên trong `AtomicReference`.

## 3. Vì sao volatile chưa giải quyết mất cập nhật?

Có thể khai báo:

~~~java
private volatile BigDecimal balance = BigDecimal.ZERO;
~~~

`volatile` đảm bảo các thao tác đọc/ghi của **trường tham chiếu** có quy tắc visibility/ordering do Java Memory Model quy định; với các thao tác `volatile`, một lần ghi xảy ra trước các lần đọc tiếp sau trong thứ tự đồng bộ thích hợp. Đọc/ghi một tham chiếu riêng lẻ cũng là thao tác nguyên tử ở cấp truy cập tham chiếu.

Nhưng đoạn sau vẫn **không nguyên tử**:

~~~java
balance = balance.add(BigDecimal.ONE);
~~~

Thực chất nó gồm:

~~~java
BigDecimal old = balance;            // volatile read
BigDecimal next = old.add(BigDecimal.ONE); // tính toán cục bộ
balance = next;                      // volatile write
~~~

Hai luồng hoàn toàn có thể đọc cùng `old` rồi cùng ghi một `next` bằng nhau. `volatile` giúp luồng thấy các lần ghi đúng theo memory model; nó **không khóa ba bước lại thành một giao dịch**.

Khi chỉ có **một luồng ghi** và nhiều luồng đọc cấu hình/snapshot bất biến, một trường `volatile` có thể đủ nếu nhu cầu thực sự chỉ là xuất bản giá trị mới và không có bất biến đa trường. Với **nhiều luồng cùng cập nhật dựa trên giá trị cũ**, cần cơ chế phối hợp toàn bộ chuỗi read–modify–write.

## 4. Cách 1: synchronized bao trùm đọc–tính–ghi

Giải pháp rõ ràng nhất cho đối tượng có trạng thái chia sẻ là bảo vệ thao tác cập nhật bằng cùng một monitor:

~~~java
import java.math.BigDecimal;

public final class SynchronizedBalance {
    private BigDecimal balance = new BigDecimal("0.00");

    public synchronized void deposit(BigDecimal amount) {
        balance = balance.add(amount);
    }

    public synchronized BigDecimal snapshot() {
        return balance;
    }
}
~~~

`synchronized` trên hai phương thức instance sử dụng khóa monitor của **cùng instance** `SynchronizedBalance`:

- Chỉ một luồng có thể chạy các đoạn được bảo vệ bởi monitor ấy tại một thời điểm.
- Luồng đang gọi `deposit` phải hoàn thành toàn bộ đọc–tính–ghi trước khi luồng khác đi vào một phương thức được bảo vệ bởi cùng khóa.
- Việc mở và đóng monitor thiết lập quan hệ happens-before liên quan, giúp các lần đọc thông qua cùng khóa thấy trạng thái được cập nhật đúng cách.

`snapshot()` trả một `BigDecimal` bất biến. Luồng khác có thể giữ lại đối tượng trả về mà không sợ nó bị sửa bên trong; nhưng đó là **ảnh chụp tại thời điểm đọc**, không tự phản ánh các lần nạp tiền tiếp theo.

Có thể dùng khối `synchronized(lock)` thay vì khóa trên `this`:

~~~java
private final Object lock = new Object();
private BigInteger total = BigInteger.ZERO;

void add(BigInteger delta) {
    synchronized (lock) {
        total = total.add(delta);
    }
}

BigInteger snapshot() {
    synchronized (lock) {
        return total;
    }
}
~~~

Khóa riêng giúp kiểm soát rõ ai có quyền phối hợp. Điều thiết yếu là **mọi đường đọc/ghi tham gia cùng quy tắc đồng bộ**: nếu một phương thức bỏ qua khóa, các bảo đảm nhất quán của lớp có thể bị phá vỡ.

### Khi chọn synchronized?

`synchronized` phù hợp khi có nhiều bất biến phải duy trì cùng lúc: kiểm tra số dư rồi trừ, cộng nhiều trường, hoặc đọc một snapshot gồm các giá trị liên quan. Nó cũng làm mã dễ hiểu khi số thao tác không nhiều.

Ví dụ, chuyển tiền giữa hai số dư được lưu trong **cùng một đối tượng** phải cập nhật cả hai dưới một khóa phù hợp, nếu yêu cầu cả hai thay đổi nguyên tử. Hai `AtomicReference<BigDecimal>` độc lập không tự tạo một giao dịch nguyên tử gồm cả hai tài khoản. Trong hệ thống dùng cơ sở dữ liệu hoặc nhiều tiến trình, khóa Java trong một JVM cũng **không thay thế** transaction/locking của kho dữ liệu chung.

## 5. Cách 2: AtomicReference<BigInteger> và CAS

`AtomicReference<T>` giữ một tham chiếu với các thao tác atomic. Kết hợp với giá trị bất biến `BigInteger` hoặc `BigDecimal`, nó giúp thực hiện cập nhật kiểu copy-on-write:

~~~java
import java.math.BigInteger;
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<BigInteger> counter =
        new AtomicReference<>(BigInteger.ZERO);

counter.updateAndGet(old -> old.add(BigInteger.ONE));
BigInteger result = counter.get();
~~~

`updateAndGet` làm cập nhật nguyên tử đối với các luồng cùng sử dụng `AtomicReference` đó. Logic của nó có thể hình dung như một vòng lặp **compare-and-set (CAS)**:

~~~java
BigInteger previous;
BigInteger next;
do {
    previous = counter.get();
    next = previous.add(BigInteger.ONE);
} while (!counter.compareAndSet(previous, next));
~~~

Nếu luồng khác đã đổi tham chiếu giữa `get()` và `compareAndSet()`, CAS thất bại; vòng lặp đọc giá trị mới rồi tính lại, **không ghi đè cập nhật của luồng khác**.

### Phân biệt phương thức AtomicReference

| Phương thức | Ngữ nghĩa |
|---|---|
| `get()` | Đọc tham chiếu hiện tại theo ngữ nghĩa bộ nhớ của atomic variable |
| `set(newValue)` | Ghi tham chiếu mới; **không** tự bảo vệ chuỗi read–modify–write được viết bên ngoài |
| `compareAndSet(expected, update)` | Chỉ đổi nếu tham chiếu hiện tại chính là `expected` |
| `updateAndGet(operator)` | Tính hàm cập nhật và trả **giá trị mới** sau lần cập nhật thành công |
| `getAndUpdate(operator)` | Cập nhật theo hàm rồi trả **giá trị cũ** của lần cập nhật thành công |
| `accumulateAndGet(value, operator)` | Gộp giá trị hiện tại và tham số bằng hàm, trả giá trị mới |
| `getAndAccumulate(value, operator)` | Tương tự nhưng trả giá trị cũ của lần cập nhật thành công |

Một lỗi rất phổ biến là viết:

~~~java
AtomicReference<BigDecimal> balance =
        new AtomicReference<>(new BigDecimal("0.00"));

// SAI khi nhiều luồng cùng cập nhật:
balance.set(balance.get().add(new BigDecimal("1.00")));
~~~

Đoạn trên vẫn là get → add → set; `get()` và `set()` riêng lẻ an toàn **không khiến sự kết hợp trở thành nguyên tử**. Dùng:

~~~java
BigDecimal delta = new BigDecimal("1.00");
balance.updateAndGet(old -> old.add(delta));
~~~

Chỉ những writer cùng tuân thủ nguyên tắc atomic update/CAS mới bảo toàn tính đúng đắn của cập nhật đó. Một writer khác tự ý gọi `set` bằng giá trị cũ có thể phá chính sách cộng dồn của hệ thống.

### CAS so sánh tham chiếu, không so sánh giá trị BigDecimal

`compareAndSet` kiểm tra nhận dạng tham chiếu (`==`), **không gọi `equals()`** và cũng không dùng `compareTo()` của `BigDecimal`:

~~~java
AtomicReference<BigDecimal> ref =
        new AtomicReference<>(new BigDecimal("1.0"));

BigDecimal another = new BigDecimal("1.0");
boolean updated =
        ref.compareAndSet(another, new BigDecimal("2.0"));
// updated == false: another khác đối tượng đang được lưu.
~~~

Dù `another.equals(ref.get())` đúng ở đầu ví dụ, CAS thất bại vì `another` là một instance khác. Với CAS loop, cách đúng là lấy `expected` từ chính `ref.get()` rồi thử đổi. Tránh dựa vào so sánh biểu diễn số để quyết định tính đúng của CAS.

## 6. Rất quan trọng: hàm truyền cho updateAndGet có thể chạy nhiều lần

Ở mức triển khai, `AtomicReference.updateAndGet` có thể gọi hàm cập nhật nhiều lần khi xảy ra tranh chấp. Do đó lambda nên là **hàm không có side effect**, chỉ tính kết quả mới từ đầu vào:

~~~java
AtomicReference<BigDecimal> total =
        new AtomicReference<>(new BigDecimal("0.00"));
BigDecimal price = new BigDecimal("10.25");

// ĐÚNG: hàm tính toán, không thực hiện side effect.
BigDecimal updated = total.updateAndGet(current -> current.add(price));
~~~

Không nên ghi log sự kiện nghiệp vụ, gửi email, gọi API thanh toán, tăng bộ đếm ngoài hoặc ghi database bên trong lambda cập nhật, vì lambda đó **có thể được thử lại**:

~~~java
// KHÔNG NÊN: side effect có thể xảy ra nhiều lần khi CAS bị tranh chấp.
// total.updateAndGet(current -> {
//     externalPaymentService.charge(price);
//     return current.add(price);
// });
~~~

Lưu ý quan trọng: điều này **không có nghĩa** mọi lần gọi `updateAndGet` sẽ thực hiện cập nhật nhiều lần. Một lời gọi thành công cập nhật giá trị một lần, nhưng phần **tính toán lambda** có thể lặp lại nhiều lần. Đó là lý do callback phải không gây side effect và nên dựa duy nhất trên giá trị hiện tại cùng các tham số bất biến.

Trong nghiệp vụ thật, hãy hoàn tất thay đổi trạng thái rồi mới phát sự kiện theo một cơ chế đảm bảo *exactly-once* hoặc idempotency thích hợp. Nếu cập nhật cần có giao dịch với hệ thống bên ngoài, một CAS trên bộ nhớ JVM chưa đủ.

## 7. Ví dụ đầy đủ: tái hiện lost update và sửa bằng AtomicReference, synchronized

Chương trình sau chủ ý dùng hai `CountDownLatch` để **bắt buộc** hai luồng cùng đọc một giá trị trước khi ghi, do đó tái hiện mất cập nhật một cách có kiểm soát, tránh dựa vào thời điểm chạy ngẫu nhiên. Sau đó, chương trình dùng `updateAndGet` cho `BigInteger` và `BigDecimal`, đồng thời dùng `synchronized` cho số dư.

Tạo tệp `ImmutableNumbersConcurrencyDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;

public class ImmutableNumbersConcurrencyDemo {
    private static final BigDecimal DELTA = new BigDecimal("0.10");

    static final class SynchronizedWallet {
        private BigDecimal balance = new BigDecimal("0.00");

        public synchronized void deposit(BigDecimal amount) {
            balance = balance.add(amount);
        }

        public synchronized BigDecimal balance() {
            return balance;
        }
    }

    public static void main(String[] args) throws Exception {
        BigInteger original = new BigInteger("100");
        BigInteger computed = original.add(BigInteger.ONE);
        System.out.println("immutable: " + original + " -> " + computed);

        AtomicReference<BigInteger> shared = new AtomicReference<>(BigInteger.ZERO);
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch mayWrite = new CountDownLatch(1);

        Runnable unsafe = () -> {
            BigInteger old = shared.get();
            bothRead.countDown();
            try {
                mayWrite.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            shared.set(old.add(BigInteger.ONE));
        };

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> first = pool.submit(unsafe);
            Future<?> second = pool.submit(unsafe);
            bothRead.await();
            mayWrite.countDown();
            first.get();
            second.get();
            System.out.println("lost update: " + shared.get());

            shared.set(BigInteger.ZERO);
            Runnable correctCount = () -> {
                for (int i = 0; i < 1_000; i++) {
                    shared.updateAndGet(old -> old.add(BigInteger.ONE));
                }
            };
            first = pool.submit(correctCount);
            second = pool.submit(correctCount);
            first.get();
            second.get();
            System.out.println("atomic count: " + shared.get());

            SynchronizedWallet wallet = new SynchronizedWallet();
            Runnable lockedDeposit = () -> {
                for (int i = 0; i < 100; i++) {
                    wallet.deposit(DELTA);
                }
            };
            first = pool.submit(lockedDeposit);
            second = pool.submit(lockedDeposit);
            first.get();
            second.get();
            System.out.println("locked balance: " + wallet.balance().toPlainString());

            AtomicReference<BigDecimal> atomicBalance =
                    new AtomicReference<>(new BigDecimal("0.00"));
            Runnable atomicDeposit = () -> {
                for (int i = 0; i < 100; i++) {
                    atomicBalance.updateAndGet(old -> old.add(DELTA));
                }
            };
            first = pool.submit(atomicDeposit);
            second = pool.submit(atomicDeposit);
            first.get();
            second.get();
            System.out.println("atomic balance: " +
                    atomicBalance.get().toPlainString());
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac ImmutableNumbersConcurrencyDemo.java
java ImmutableNumbersConcurrencyDemo
~~~

**Kết quả stdout chính xác:**

~~~text
immutable: 100 -> 101
lost update: 1
atomic count: 2000
locked balance: 20.00
atomic balance: 20.00
~~~

Giải thích từng phần:

1. `original` không đổi từ 100: `add()` tạo kết quả mới 101.
2. Hai luồng đọc `shared = 0` trước khi được phép ghi; cả hai tính `0 + 1` và dùng `set(1)`. Dù `shared` là `AtomicReference`, phép cập nhật **do người viết tách thành get + set** khiến kết quả bằng 1 thay vì 2.
3. Với `updateAndGet(old -> old.add(ONE))`, mỗi luồng tăng 1.000 lần nên tổng đúng bằng 2.000.
4. `SynchronizedWallet.deposit()` dùng chung monitor cho mỗi thao tác cộng `BigDecimal("0.10")`. Hai luồng mỗi luồng 100 lần cho đúng 20.00.
5. `AtomicReference<BigDecimal>.updateAndGet()` tạo số mới từ snapshot hiện tại rồi CAS; cũng cho đúng 20.00.

Kết quả của phần `lost update` được tạo có chủ đích nhờ latch; nó không chứng minh `AtomicReference.set()` có lỗi. Phần sai là sử dụng **hai thao tác atomic riêng lẻ** thay cho một phép update atomic. Ví dụ cũng không cần dùng `Thread.sleep` để hy vọng race xảy ra.

Các phép tính dùng `BigDecimal("0.10")` được tạo từ chuỗi để biểu diễn thập phân chính xác. Không dùng `new BigDecimal(0.1)` cho ví dụ này vì `double 0.1` không biểu diễn chính xác số thập phân một phần mười.

## 8. AtomicReference hay synchronized: nên chọn thế nào?

| Nhu cầu | Cách tiếp cận hợp lý | Giới hạn cần nhớ |
|---|---|---|
| Chia sẻ một hằng số `BigDecimal` giữa nhiều luồng chỉ đọc | Trường `final` / công bố đối tượng đúng | Không có trạng thái cộng dồn cần cập nhật |
| Một writer công bố snapshot số mới, nhiều reader chỉ đọc | `volatile BigDecimal` hoặc `AtomicReference<BigDecimal>` | Chưa giải quyết nhiều writer cùng read–modify–write |
| Nhiều writer tăng một số nguyên lớn | `AtomicReference<BigInteger>.updateAndGet` hoặc khóa | Hàm cập nhật thuần, có thể bị gọi lại; tranh chấp cao có thể tốn CAS |
| Nhiều writer cộng dồn một giá trị thập phân | `AtomicReference<BigDecimal>.updateAndGet` hoặc khóa | Chọn scale/rounding đúng theo nghiệp vụ |
| Cập nhật nhiều trường hoặc kiểm tra rồi thay đổi nhiều giá trị liên quan | `synchronized`/`ReentrantLock` hay snapshot bất biến được đổi nguyên tử | Bảo vệ toàn bộ invariant, mọi đường truy cập theo cùng giao thức |
| Bộ đếm `int`/`long` đơn giản | `AtomicInteger`/`AtomicLong`; có thể xem `LongAdder` cho chỉ số thống kê | Không cần `BigInteger` nếu miền giá trị nhỏ; LongAdder.sum() không là snapshot nguyên tử khi có ghi đồng thời |
| Giao dịch trải nhiều JVM hoặc database | Transaction/locking/conditional update phù hợp kho dữ liệu | Khóa và atomic ở một JVM không đảm bảo đồng bộ liên tiến trình |

Không có lớp `AtomicBigDecimal` hay `AtomicBigInteger` chuẩn trong `java.util.concurrent.atomic`. `AtomicReference<T>` hỗ trợ làm việc với các loại đối tượng bất biến như vậy.

`AtomicReference` không có khóa truyền thống nhưng không đồng nghĩa luôn nhanh hơn `synchronized`. Càng nhiều luồng tranh chấp, CAS có thể thất bại và phải tính lại `BigDecimal`/`BigInteger` nhiều lần, phát sinh thêm đối tượng. Với phép cập nhật phức tạp hoặc invariant nhiều trường, khóa có thể đơn giản và hiệu quả hơn. Chọn cơ chế theo tính đúng đắn trước, sau đó benchmark bằng workload thực.

## 9. Khi cập nhật phụ thuộc điều kiện: kiểm tra và thay đổi phải cùng một bước

Không chỉ phép cộng mới gặp race. Ví dụ rút tiền:

~~~java
// SAI: get và set tách rời; hai luồng có thể đều vượt qua điều kiện.
if (balance.get().compareTo(withdrawal) >= 0) {
    balance.set(balance.get().subtract(withdrawal));
}
~~~

Đối với `AtomicReference<BigDecimal>`, kiểm tra và thay đổi có thể đặt chung trong một phép cập nhật có điều kiện, ví dụ:

~~~java
BigDecimal withdrawal = new BigDecimal("7.00");
AtomicReference<BigDecimal> balance =
        new AtomicReference<>(new BigDecimal("10.00"));

BigDecimal after = balance.updateAndGet(current -> {
    if (current.compareTo(withdrawal) < 0) {
        throw new IllegalStateException("Insufficient funds");
    }
    return current.subtract(withdrawal);
});
~~~

Ở đây điều kiện được **đánh giá lại trên giá trị hiện tại** mỗi lần lambda bị chạy lại do CAS không thành công. Nếu trong lần thử mới tiền đã không đủ, thao tác sẽ ném lỗi thay vì ghi đè trạng thái của người khác.

Tuy nhiên, ví dụ trên chỉ cho thấy một chính sách đơn giản của **một biến số dư trong bộ nhớ**. Nghiệp vụ thật còn cần kiểm tra số âm, đơn vị tiền tệ, tính hợp lệ của `withdrawal`, giới hạn, audit, idempotency, persistence và xử lý chuyển tiền giữa các tài khoản. Khi một giao dịch yêu cầu cập nhật đồng thời nhiều tài khoản, CAS trên riêng từng số dư không đủ để bảo đảm tính nguyên tử của toàn giao dịch.

Có thể đưa nhiều trường cần nhất quán vào một **snapshot bất biến**, rồi dùng một `AtomicReference` chứa toàn bộ snapshot để thay thế nguyên tử:

~~~java
record LedgerSnapshot(BigDecimal balance, BigInteger operations) {}

AtomicReference<LedgerSnapshot> state = new AtomicReference<>(
        new LedgerSnapshot(new BigDecimal("0.00"), BigInteger.ZERO));

BigDecimal delta = new BigDecimal("1.00");

state.updateAndGet(old -> new LedgerSnapshot(
        old.balance().add(delta),
        old.operations().add(BigInteger.ONE)
));
~~~

Các reader dùng một lần `state.get()` sẽ thấy một snapshot chứa **cả hai trường thuộc cùng một phiên bản**. Nếu lấy `get()` hai lần cách nhau bởi update thì có thể đọc hai phiên bản khác nhau; nên giữ snapshot vào một biến cục bộ khi cần một trạng thái nhất quán. `record` giúp truyền dữ liệu theo dạng bất biến nếu mọi thành phần bên trong cũng bất biến, như hai kiểu số trong ví dụ.

## 10. Phân biệt snapshot cũ với "đối tượng bị thay đổi"

Một reader có thể giữ tham chiếu cũ:

~~~java
AtomicReference<BigDecimal> price =
        new AtomicReference<>(new BigDecimal("12.00"));

BigDecimal snapshot = price.get(); // 12.00
price.set(new BigDecimal("15.00"));

System.out.println(snapshot);   // 12.00
System.out.println(price.get()); // 15.00
~~~

Cả hai giá trị hợp lệ. `snapshot` không được cập nhật vì `BigDecimal` bất biến; `price` chỉ được đổi để trỏ đến một số mới. Nếu ứng dụng muốn reader **luôn lấy giá trị mới nhất**, nó phải truy cập lại holder đúng thời điểm. Nếu muốn tính một chuỗi nghiệp vụ dựa trên **cùng một phiên bản**, hãy giữ snapshot cục bộ và chỉ đọc một lần tại đầu công đoạn, hoặc dùng giao thức cập nhật nhất quán.

Không nhầm lẫn hai đặc tính:

- Bảo đảm không bị sửa nội dung của `snapshot`.
- Bảo đảm `snapshot` là giá trị mới nhất hoặc phù hợp với các trường khác.

Tính bất biến chỉ giải quyết đặc tính thứ nhất.

## 11. An toàn khi dùng BigDecimal trong nhiều luồng không đồng nghĩa tự động đúng nghiệp vụ

Với `BigDecimal`, còn có yêu cầu về **precision, scale, rounding** độc lập với synchronization:

~~~java
BigDecimal a = new BigDecimal("0.10");
BigDecimal b = new BigDecimal("0.20");
BigDecimal total = a.add(b); // chính xác, giá trị 0.30
~~~

Nếu dùng `divide` với phép chia thập phân vô hạn, Java cần một rounding mode/`MathContext` thích hợp. Cơ chế `AtomicReference` hoặc `synchronized` không sửa lỗi dùng sai precision hoặc rounding. Ngược lại, tạo số tiền từ `new BigDecimal(0.1)` có thể mang sai lệch do đầu vào `double`, dù tất cả cập nhật đều được khóa đúng.

Ví dụ cập nhật được làm tròn sau mỗi lần cộng:

~~~java
BigDecimal delta = new BigDecimal("0.005");
AtomicReference<BigDecimal> total =
        new AtomicReference<>(new BigDecimal("0.00"));

total.updateAndGet(current ->
        current.add(delta).setScale(2, java.math.RoundingMode.HALF_UP));
~~~

Đây là một quy tắc **làm tròn mỗi giao dịch** có chủ đích. Nếu nghiệp vụ muốn cộng mọi giá trị chính xác rồi làm tròn **một lần cuối**, kết quả có thể khác. Trước khi viết callback atomic, phải chọn điểm làm tròn đúng; concurrency chỉ bảo đảm việc áp dụng chính sách nhất quán, không tự chọn chính sách cho bạn.

Khi lambda update chạy lại do cạnh tranh, nó cũng không nên đọc dữ liệu thay đổi độc lập từ bên ngoài. Hãy chuẩn hóa đầu vào (`delta`, đơn vị, điều kiện) thành biến cục bộ bất biến trước khi vào lambda, hoặc thiết kế snapshot chứa các dữ liệu cần đọc nguyên tử cùng nhau.

## 12. Kiểm thử lỗi đồng thời

Với cập nhật tham chiếu dùng chung, một bài test chỉ chạy một luồng hầu như không thể phát hiện lost update. Cách kiểm tra hữu ích:

1. **Test có điều phối:** dùng `CountDownLatch` hoặc cơ chế phối hợp để buộc hai luồng đọc cùng snapshot, sau đó thử ghi; chương trình ở mục 7 thực hiện điều này.
2. **Test kết quả cuối:** hai luồng mỗi luồng tăng 1.000 lần phải cho đúng 2.000; với `BigDecimal("0.10")` hai luồng mỗi luồng cộng 100 lần phải cho đúng `20.00` theo scale đã chọn.
3. **Test thông điệp thất bại và ngoại lệ:** tác vụ trong `ExecutorService.submit` có thể ném exception; gọi `Future.get()` để nhận lỗi thay vì kết luận thành công chỉ vì thread pool đã nhận tác vụ.
4. **Test xử lý shutdown và interruption:** chờ tác vụ hoàn tất và giải phóng pool. Với code sản xuất, đặt timeout phù hợp và xử lý gián đoạn theo thiết kế.
5. **Kiểm tra mọi đường cập nhật:** nếu có cả `updateAndGet` và một đường `get + set` không được bảo vệ, hệ thống vẫn có thể mất dữ liệu.

Test lặp lại nhiều lần với nhiều thread có thể tăng khả năng bộc lộ race, nhưng **không chứng minh tuyệt đối** hệ thống không có lỗi đồng thời. Cần dựa thêm vào lập luận về atomicity, happens-before và giao thức truy cập. Để kiểm tra hiệu năng, đo bằng benchmark phù hợp thay vì coi thời gian một lần chạy test đồng thời là kết luận.

## 13. Các lỗi phổ biến cần tránh

| Lỗi | Vì sao sai | Cách giải quyết |
|---|---|---|
| "BigDecimal immutable nên balance += delta chắc chắn thread-safe" | Việc thay tham chiếu là đọc–tính–ghi, có thể mất cập nhật | Khóa hoặc atomic update |
| Dùng `volatile` rồi kết luận phép cộng atomic | `volatile` cung cấp visibility/ordering chứ không gộp ba bước | `synchronized` hoặc `AtomicReference.updateAndGet` |
| Gọi `ref.set(ref.get().add(x))` | Hai thao tác atomic rời rạc không tạo cập nhật nguyên tử | `updateAndGet(old -> old.add(x))` |
| Gọi dịch vụ ngoài trong lambda CAS | Callback có thể chạy lại khi cạnh tranh | Lambda thuần; side effect sau theo giao thức đáng tin |
| Dùng `compareAndSet` với đối tượng mới có giá trị bằng nhau | CAS kiểm tra cùng tham chiếu | Lấy expected từ `get()` |
| Bảo vệ writer bằng lock nhưng reader bỏ qua lock | Reader có thể nhìn trạng thái không theo giao thức đã định | Đồng bộ cả đường đọc/ghi hoặc công bố snapshot bằng volatile/atomic đúng cách |
| Sử dụng hai atomic field và kỳ vọng snapshot cả hai nhất quán | Hai biến độc lập không thay thế nguyên tử cùng lúc | Khóa hoặc một immutable snapshot trong một AtomicReference |
| Tưởng trường `final AtomicReference` không thể thay số | Chỉ tham chiếu đến holder là final | Phân biệt tính bất biến của field và trạng thái holder |
| Tin rằng `AtomicReference` làm phép toán rẻ hơn | Tranh chấp CAS có thể tính lại và tạo nhiều số mới | Đo, so với khóa |
| Dùng `double`/làm tròn sai cho số tiền | Đúng concurrency vẫn có thể sai số học | Dùng BigDecimal từ chuỗi, chọn scale/rounding chuẩn |
| Test concurrency không đợi Future kết thúc | Có thể bỏ qua lỗi của task | Gọi `Future.get()` và kiểm tra giá trị cuối |
| Coi synchronized cục bộ thay thế database transaction | Chỉ phối hợp các luồng theo khóa trong một JVM | Dùng giao dịch/khóa phù hợp hệ thống lưu trữ |

## 14. Tự kiểm tra

**Câu 1.** Hai luồng cùng gọi `shared = shared.add(BigInteger.ONE)` với `shared` là một trường `BigInteger`. Có chắc cộng được hai lần không?

**Đáp án:** Không. Mỗi `add()` tạo kết quả bất biến riêng, nhưng hai luồng có thể đọc cùng tham chiếu cũ và một update bị ghi đè. Cần bảo vệ phép read–modify–write.

**Câu 2.** Nếu đổi trường đó thành `volatile BigInteger shared`, đã đủ chưa?

**Đáp án:** Chưa. `volatile` bảo đảm visibility theo Java Memory Model, không làm `shared = shared.add(ONE)` trở thành một phép atomic.

**Câu 3.** Với `AtomicReference<BigDecimal> ref`, mã `ref.set(ref.get().add(amount))` có giải quyết mất cập nhật không?

**Đáp án:** Không; dùng `ref.updateAndGet(old -> old.add(amount))` hoặc khóa phù hợp.

**Câu 4.** Vì sao không gọi API thanh toán trong lambda của `updateAndGet`?

**Đáp án:** Hàm cập nhật có thể được gọi lại khi CAS không thành công; side effect có thể xảy ra nhiều lần dù cập nhật state chỉ thành công một lần.

**Câu 5.** Một snapshot gồm `balance` và `count` phải luôn tương ứng cùng phiên bản. Có nên dùng hai `AtomicReference` tách biệt không?

**Đáp án:** Hai atomic riêng không bảo đảm một lần đọc sẽ thu được cặp giá trị cùng phiên bản. Có thể dùng một đối tượng snapshot bất biến trong một `AtomicReference`, hoặc khóa bảo vệ toàn bộ invariant.

**Câu 6.** Luồng A giữ một `BigDecimal snapshot`, luồng B đổi holder từ `12.00` sang `15.00`. Giá trị trong snapshot cũ có đổi thành `15.00` không?

**Đáp án:** Không. Đối tượng `BigDecimal` cũ vẫn bất biến. Chỉ tham chiếu trong holder được thay bằng đối tượng mới.

**Câu 7.** CAS `compareAndSet(expected, update)` dùng `BigDecimal.compareTo()` để xác định expected phải không?

**Đáp án:** Không. Nó so sánh **nhận dạng tham chiếu**; hai `BigDecimal` khác instance dù có cùng giá trị vẫn không phải cùng expected reference.

---

**Ghi nhớ:** `BigInteger` và `BigDecimal` an toàn để chia sẻ dưới dạng **giá trị bất biến**. Nhưng cập nhật **biến tham chiếu dùng chung** vẫn cần điều phối các bước đọc–tính–ghi. Dùng `synchronized`/khóa khi bảo vệ invariant hoặc nhiều trường; dùng `AtomicReference.updateAndGet` khi trạng thái cần cập nhật được biểu diễn trong một snapshot bất biến và hàm cập nhật thuần. Luôn tách bạch tính đúng đắn đồng thời với quy tắc precision, scale và rounding của phép tính.
