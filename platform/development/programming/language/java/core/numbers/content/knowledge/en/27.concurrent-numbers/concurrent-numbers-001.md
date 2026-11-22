# count++ là nhiều bước, không phải thao tác nguyên tử

## 1. Vấn đề: tăng một biến đếm chia sẻ

Trong Java, `count++` là cách viết ngắn gọn của thao tác tăng biến thêm 1. Ở chương trình tuần tự, đây là một biểu thức quen thuộc. Tuy nhiên, khi **hai hoặc nhiều luồng cùng tăng một biến đếm chia sẻ**, `count++` **không bảo đảm** rằng mỗi lần gọi đều làm tăng kết quả cuối cùng thêm đúng 1.

Nguyên nhân là **phép tăng gồm đọc giá trị cũ, tính giá trị mới và ghi lại** (*read–modify–write*). Những bước logic này không được bảo vệ như một thao tác nguyên tử (*atomic operation*). Hai luồng có thể cùng đọc một giá trị ban đầu rồi ghi đè kết quả của nhau. Hiện tượng ấy gọi là **lost update** (mất cập nhật).

Ví dụ, nếu `count = 0` và hai luồng mỗi luồng thực hiện một lần `count++`, ta mong đợi `count = 2`. Nhưng nếu không có đồng bộ hóa phù hợp, chương trình có thể chỉ lưu `1`. Việc một lần chạy cho ra `2` **không chứng minh** mã đúng, vì lịch xen kẽ giữa các luồng có thể khác ở lần chạy tiếp theo.

Bài học này giúp bạn phân biệt **tính nguyên tử**, **khả năng quan sát giá trị giữa các luồng** và **thứ tự thực thi**; từ đó dùng đúng `synchronized`, `AtomicInteger` và `LongAdder`.

## 2. Phân rã count++: đọc, tính, ghi

Xét biến `int count`, biểu thức:

```java
count++;
```

Có thể hình dung về mặt ngữ nghĩa như sau:

```java
int oldValue = count;          // (1) Đọc giá trị hiện tại
int nextValue = oldValue + 1;  // (2) Tính kết quả mới
count = nextValue;              // (3) Ghi kết quả
```

Đây là **mô hình giải thích**, không phải cam kết rằng mọi JVM thực thi đúng ba lệnh máy hoặc ba bytecode. JIT và CPU có thể tối ưu cách thực hiện; tuy vậy, Java **không cung cấp hợp đồng nguyên tử** cho thao tác tăng một field `int` chia sẻ bằng `count++`.

| Thời điểm | Luồng A | Luồng B | Giá trị chia sẻ |
|---|---|---|---|
| 1 | Đọc `count = 0` | Chưa chạy | `0` |
| 2 | Giữ bản sao `oldA = 0` | Đọc `count = 0` | `0` |
| 3 | Tính `0 + 1 = 1` | Tính `0 + 1 = 1` | `0` |
| 4 | Ghi `count = 1` | Chưa ghi | `1` |
| 5 | Đã xong | Ghi `count = 1` | `1` |

Hai lần tăng xảy ra, nhưng giá trị cuối chỉ là **1**. Luồng B đã ghi đè kết quả của A; đó chính là lost update.

Kịch bản khác cũng có thể xảy ra: A hoàn tất ghi `1` trước khi B đọc, nên B đọc `1` và ghi `2`. Vì vậy race condition có thể lúc đúng, lúc sai tùy lịch chạy.

### Phân biệt postfix và prefix

- `count++` (*postfix*) tăng biến rồi trả về **giá trị cũ** của biểu thức.
- `++count` (*prefix*) tăng biến rồi trả về **giá trị mới** của biểu thức.
- `count += 1` cũng cần đọc, tính rồi ghi.

Ba cách viết đều **không tự tạo thao tác nguyên tử** khi nhiều luồng đồng thời cập nhật cùng một biến `int` chia sẻ. Sự khác biệt giữa prefix và postfix liên quan đến giá trị của biểu thức, không liên quan đến an toàn luồng.

### Khi nào count++ bình thường là đủ?

Nếu `count` là **biến cục bộ của một luồng** và không bị chia sẻ cho luồng khác, không có hai luồng cùng sửa nó nên không có lost update do cạnh tranh. Nguy cơ thường nằm ở field của đối tượng chia sẻ, `static` field, hoặc một phần tử mảng được nhiều luồng đọc/ghi.

Ngay cả khi riêng lẻ các lần đọc và ghi một `int` được thực hiện nguyên tử, **tổ hợp đọc–tăng–ghi** vẫn không nguyên tử. Không nên lấy thuộc tính của một lần đọc/ghi riêng làm suy luận cho toàn biểu thức.

## 3. Chương trình Java 17+ tái hiện vấn đề một cách xác định

Thử chạy nhiều luồng cùng viết `count++` có thể cho kết quả thay đổi qua mỗi lần chạy; rất khó dự đoán stdout chính xác. Ví dụ dưới đây dùng `CountDownLatch` để **buộc cả hai luồng cùng đọc giá trị cũ trước khi ghi**, qua đó tái hiện được một lịch xen kẽ gây mất cập nhật.

Phần không an toàn dùng hai câu `snapshot = count` và `count = snapshot + 1` để **phơi bày** các bước của phép tăng; nó mô phỏng thành phần read–modify–write của `count++`, chứ không khẳng định mỗi lần chạy `count++` luôn bị xen ngang theo cùng một cách. Phần thứ hai dùng hai phương án sửa lỗi với 100.000 lần tăng trên mỗi luồng.

Tạo file **`IncrementDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class IncrementDemo {
    private static int count;
    private static int guardedCount;
    private static final Object LOCK = new Object();
    private static final AtomicInteger atomicCount = new AtomicInteger();

    private static void demonstrateLostUpdate()
            throws InterruptedException {
        count = 0;
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable unsafe = () -> {
            int snapshot = count;
            bothRead.countDown();

            try {
                allowWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            count = snapshot + 1;
        };

        Thread a = new Thread(unsafe);
        Thread b = new Thread(unsafe);
        a.start();
        b.start();

        bothRead.await();
        allowWrite.countDown();
        a.join();
        b.join();

        System.out.println("two increments, actual: " + count);
    }

    private static void demonstrateFixes()
            throws InterruptedException {
        guardedCount = 0;
        atomicCount.set(0);

        Runnable safe = () -> {
            for (int i = 0; i < 100_000; i++) {
                synchronized (LOCK) {
                    guardedCount++;
                }
                atomicCount.incrementAndGet();
            }
        };

        Thread a = new Thread(safe);
        Thread b = new Thread(safe);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("synchronized: " + guardedCount);
        System.out.println("AtomicInteger: " + atomicCount.get());
    }

    public static void main(String[] args)
            throws InterruptedException {
        demonstrateLostUpdate();
        demonstrateFixes();
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac IncrementDemo.java
java IncrementDemo
```

Kết quả:

```text
two increments, actual: 1
synchronized: 200000
AtomicInteger: 200000
```

**Giải thích chi tiết:**

1. Hai luồng `a` và `b` cùng giữ `snapshot = 0`. `bothRead.await()` ở luồng main đợi cả hai đã đọc, rồi mới gọi `allowWrite.countDown()` cho phép ghi.
2. Mỗi luồng ghi `snapshot + 1 = 1`. Hai lần ghi trùng nhau khiến kết quả cuối `count == 1`. Đây là minh họa quyết định một lịch gây lost update.
3. Với `synchronized (LOCK)`, mỗi lần `guardedCount++` được bảo vệ bởi cùng đối tượng khóa. Chỉ một luồng được ở trong vùng khóa trong cùng thời điểm.
4. `atomicCount.incrementAndGet()` thực hiện nguyên tử phép tăng trên `AtomicInteger`. Hai luồng cùng gọi 100.000 lần, nên kết quả `200000`.
5. `a.join()` và `b.join()` đảm bảo main chỉ đọc kết quả **sau khi hai luồng hoàn tất**. `join()` không làm cho những phép `count++` bên trong luồng trở thành nguyên tử; nó chỉ tạo điểm chờ và bảo đảm về thứ tự quan sát sau khi luồng kết thúc.

Với code sửa lỗi, dù lịch chạy của hai luồng thay đổi, tổng cuối vẫn chính xác khi không có thao tác sửa thêm và không xảy ra tràn số. Bản mã sai cố tình trình bày các bước rời để bạn nhìn thấy nguyên nhân.

## 4. Atomicity, visibility và happens-before là ba vấn đề riêng

### Tính nguyên tử (atomicity)

Một phép tăng nguyên tử phải quan sát được như một cập nhật không thể bị phép tăng khác chen vào giữa làm mất kết quả. Nếu bộ đếm ban đầu 0 và có 200.000 lần tăng nguyên tử đã hoàn tất, kết quả là 200.000 (giả sử không có thao tác sửa khác và chưa tràn `int`).

`count++` trên field không đồng bộ không có bảo đảm ấy; `AtomicInteger.incrementAndGet()` có bảo đảm này. `synchronized` có thể biến một vùng đọc–tính–ghi thành vùng không bị luồng khác dùng **cùng khóa** xen vào.

### Khả năng nhìn thấy (visibility)

Một luồng có thể ghi dữ liệu nhưng luồng khác không nhất thiết nhìn thấy hiệu ứng ấy đúng lúc mong đợi nếu không có đồng bộ hóa thích hợp. Java Memory Model (JMM) quy định khi nào thay đổi của một luồng phải nhìn thấy đối với luồng khác.

Từ khóa `volatile` thiết lập một số bảo đảm visibility và ordering cho truy cập field; `synchronized` và các API đồng bộ cũng có quy tắc bộ nhớ riêng. Nhưng visibility **không tự bảo đảm** rằng hai thao tác đọc/ghi riêng lẻ được ghép thành một thao tác tăng nguyên tử.

### Thứ tự và quan hệ happens-before

Quan hệ **happens-before** của JMM diễn đạt bảo đảm thứ tự/khả năng quan sát giữa các thao tác. Ví dụ, sau khi `Thread.join()` hoàn tất thành công, luồng gọi `join()` có thể quan sát các hành động của luồng đã kết thúc theo hợp đồng JMM. Việc mở và giải phóng cùng monitor cũng tạo quan hệ đồng bộ hóa tương ứng.

Dùng `join()` để chờ các luồng là đúng khi đọc **kết quả cuối**, nhưng `join()` được gọi sau khi các lần tăng diễn ra **không thể khôi phục** những cập nhật đã mất trước đó.

## 5. Vì sao volatile không giải quyết count++?

Đây là đoạn mã **vẫn sai** khi nhiều luồng gọi đồng thời:

```java
private volatile int count = 0;

public void increment() {
    count++;
}
```

`volatile` cho tính chất của **mỗi lần đọc và ghi riêng**, nhưng `count++` có thể được xen kẽ như sau:

```text
A: đọc count -> 10
B: đọc count -> 10
A: tính 11 và ghi count = 11
B: tính 11 và ghi count = 11
```

Bộ đếm kết thúc ở `11` thay vì `12`. Hai luồng không có một thao tác “đọc+ghi” nguyên tử; cả hai chỉ dùng các lần đọc/ghi volatile riêng biệt. Vì vậy:

- `volatile int count; count++;` **không an toàn** như bộ đếm chia sẻ có nhiều updater.
- `volatile long count; count++;` cũng **không an toàn**.
- `count += 1` cũng không giải quyết được lỗi lost update.
- `volatile` phù hợp cho những giao thức chia sẻ giá trị/cờ trạng thái mà cập nhật không đòi hỏi read–modify–write nguyên tử.

Không nên phát biểu rằng chỉ cần “tránh cache CPU” là đủ để giải quyết. Đây là vấn đề về hợp đồng **atomicity** của toàn thao tác, không chỉ việc đọc dữ liệu mới nhất.

## 6. Cách sửa bằng synchronized

`synchronized` tạo một vùng được bảo vệ bởi **monitor**. Nếu tất cả đường đọc/ghi bộ đếm đều tuân thủ **cùng một khóa**, chỉ một luồng được thực thi phần được bảo vệ tại một thời điểm.

Ví dụ lớp counter:

```java
public final class SynchronizedCounter {
    private int count;

    public synchronized void increment() {
        count++;
    }

    public synchronized int get() {
        return count;
    }
}
```

Hai phương thức instance `synchronized` trên **cùng đối tượng `SynchronizedCounter`** cùng khóa `this`. Khi `increment()` khóa monitor, luồng khác gọi `get()` hoặc `increment()` trên chính instance đó phải chờ. Với cùng giao thức khóa, phép tăng được bảo vệ và kết quả đọc có bảo đảm visibility phù hợp.

Cũng có thể viết:

```java
private final Object lock = new Object();
private int count;

public void increment() {
    synchronized (lock) {
        count++;
    }
}
```

Hai đoạn này là **ví dụ thành phần lớp**, không phải chương trình chạy độc lập có `main()`. Nếu ghép vào một lớp, dùng một kiểu khóa thống nhất cho mọi truy cập liên quan.

Những điều kiện để sửa đúng:

- **Mọi updater** đều sử dụng cùng khóa; không có đoạn khác tăng `count++` bên ngoài vùng khóa.
- Nếu cần quan sát nhất quán, **mọi reader** cũng phải tuân thủ giao thức tương ứng.
- Không tạo một đối tượng `new Object()` riêng trong mỗi lần gọi để khóa; khóa khác nhau không loại trừ lẫn nhau.
- Giữ vùng khóa đủ nhỏ khi hợp lý, đặc biệt không chèn I/O kéo dài mà không cần thiết vào khối khóa.

`synchronized` phù hợp khi cần bảo vệ **nhiều bước hoặc nhiều field** theo một bất biến chung, ví dụ cập nhật counter đồng thời cập nhật một cấu trúc dữ liệu khác mà cả hai phải nhất quán.

## 7. Cách sửa bằng AtomicInteger

`java.util.concurrent.atomic.AtomicInteger` cung cấp giá trị `int` cùng các API cập nhật nguyên tử:

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger count = new AtomicInteger(0);

int afterFirst = count.incrementAndGet(); // Tăng, trả giá trị mới: 1
int beforeSecond = count.getAndIncrement(); // Tăng, trả giá trị cũ: 1
int afterAdd = count.addAndGet(5);         // Tăng thêm 5, trả 7
int current = count.get();                // Đọc 7
```

`incrementAndGet()` có ngữ nghĩa **trả về giá trị sau khi tăng**, tương tự `++count`; `getAndIncrement()` **trả về giá trị trước khi tăng**, tương tự `count++`. Điểm khác quyết định là cả hai phương thức `AtomicInteger` cung cấp **cập nhật nguyên tử** đối với instance đó.

Ví dụ khi hai luồng cùng gọi `getAndIncrement()` và bộ đếm ban đầu 0: hai giá trị trả về tương ứng là `0` và `1` (không thể xác định trước luồng nào nhận giá trị nào); sau khi cả hai hoàn tất, `get()` là `2`.

**Đừng tách cập nhật thành hai lời gọi:**

```java
count.set(count.get() + 1); // VẪN CÓ THỂ LOST UPDATE
count.incrementAndGet();    // CẬP NHẬT NGUYÊN TỬ
```

`get()` và `set()` riêng lẻ có bảo đảm của API, nhưng ghép chúng bằng một biểu thức Java **không tạo thành một cập nhật nguyên tử**. Nếu logic phức tạp phụ thuộc giá trị cũ, xét `updateAndGet(...)`, `getAndUpdate(...)`, `compareAndSet(expected, update)` hoặc `accumulateAndGet(...)`.

Nhiều thuật toán atomic dựa trên compare-and-set (CAS) và có thể thử lại khi cạnh tranh. Vì vậy, hàm cập nhật truyền vào `updateAndGet`/`accumulateAndGet` nên không chứa side effect ngoài việc tính giá trị mới: hàm có thể được chạy lại khi cập nhật chưa thành công.

**Giới hạn:** `AtomicInteger` bảo vệ **một giá trị `int`**, không tự biến một chuỗi cập nhật nhiều field hoặc nhiều đối tượng thành một giao dịch nguyên tử. Nếu cần cấp số thứ tự duy nhất và tăng nguyên tử, `getAndIncrement()` thường phù hợp; nếu cần nhiều field đồng bộ, nên có giao thức khóa bao quát.

## 8. LongAdder dành cho bộ đếm thống kê có tranh chấp cao

`java.util.concurrent.atomic.LongAdder` hữu ích khi **rất nhiều luồng cùng tăng bộ đếm thống kê**. Nó có thể phân tán cập nhật vào nhiều thành phần nội bộ để giảm tranh chấp, thay vì buộc tất cả tranh chấp một giá trị như `AtomicInteger`.

```java
import java.util.concurrent.atomic.LongAdder;

LongAdder requests = new LongAdder();
requests.increment();
requests.add(5L);
long currentEstimate = requests.sum();
```

Điểm cần phân biệt:

- `LongAdder.increment()` cho phép tích lũy các lần tăng đồng thời.
- **`sum()` không phải snapshot nguyên tử** khi các luồng khác vẫn đang cập nhật. Kết quả trong lúc chạy có thể không phản ánh một trạng thái tuyến tính duy nhất.
- Sau khi các updater đã kết thúc và có đồng bộ hóa để đợi chúng hoàn tất, `sum()` có thể dùng để lấy tổng cuối.
- `LongAdder` không cung cấp một kết quả `getAndIncrement()` để cấp ID tăng tuần tự; không dùng nó nếu mọi lần tăng phải trả về số thứ tự nguyên tử độc nhất.

`LongAdder` thích hợp với bộ đếm request, sự kiện, đo thống kê thông lượng cao. `AtomicInteger` phù hợp hơn khi cần một counter cập nhật nguyên tử với giá trị đọc/ghi theo từng thao tác. Không mặc định `LongAdder` luôn nhanh hơn: hiệu năng phụ thuộc mức cạnh tranh và khối lượng công việc; hãy đo khi tối ưu hóa thực tế.

## 9. Bảng lựa chọn và những lỗi thường gặp

| Cách viết | An toàn với nhiều luồng cùng tăng? | Lý do |
|---|---|---|
| `int count; count++;` | Không, nếu cùng chia sẻ mà thiếu đồng bộ | Read–modify–write có thể xen kẽ |
| `volatile int count; count++;` | Không | Visibility không tạo cập nhật nguyên tử |
| `count += 1` hoặc `++count` | Không, khi biến chia sẻ không đồng bộ | Cùng nguyên nhân |
| `synchronized (sameLock) { count++; }` | Có, nếu mọi truy cập tuân thủ khóa | Bảo vệ cả đoạn đọc–tính–ghi |
| `AtomicInteger.incrementAndGet()` | Có | Phép tăng nguyên tử |
| `AtomicInteger.set(get() + 1)` | Không | Hai lời gọi riêng lẻ, có thể bị xen ngang |
| `LongAdder.increment()` | Có thể dùng để tích lũy đồng thời | `sum()` không là snapshot nguyên tử giữa các cập nhật |
| Biến đếm cục bộ chỉ do một luồng sử dụng | Có với mục đích tăng thông thường | Không có race do chia sẻ |

### Sai lầm: “Chạy thử vẫn thấy đủ”

Race phụ thuộc lịch luồng. Một lượt thực thi có kết quả đúng không đủ chứng minh an toàn. Hãy xây dựng phép thử cho các **lịch xen kẽ gây nguy cơ**, như ví dụ dùng latch. Với bộ đếm đúng, kiểm tra tổng sau khi tất cả tác vụ hoàn tất.

### Sai lầm: khóa mỗi nơi một object

`synchronized(lockA)` không bảo vệ khỏi luồng khác dùng `synchronized(lockB)` nếu `lockA != lockB`. Hai luồng sẽ chạy đồng thời trên hai monitor khác nhau. Khi một trạng thái dùng chung được bảo vệ bằng khóa, quy tắc khóa phải thống nhất trên mọi đường truy cập.

### Sai lầm: tưởng mọi hành động với AtomicInteger đều nguyên tử như một nhóm

`incrementAndGet()` là cập nhật nguyên tử, nhưng hai lời gọi liên tiếp, chẳng hạn `get()` rồi `set()` hoặc cập nhật hai đối tượng `AtomicInteger`, không tự tạo một giao dịch nguyên tử tổng thể. Nếu bất biến trải qua nhiều trạng thái, cần cơ chế thiết kế/khóa phù hợp.

### Sai lầm: đọc tổng trước khi nhiệm vụ hoàn tất

Ngay cả một counter nguyên tử vẫn đang tăng khi các worker đang chạy. `get()` giữa chừng không nhất thiết bằng kết quả cuối dự kiến. Đợi tất cả nhiệm vụ xong (`join()`, `Future.get()` hoặc primitive tương đương), rồi đọc.

### Sai lầm: quên giới hạn miền int

`int` có phạm vi từ `-2_147_483_648` đến `2_147_483_647`. `count++` và `AtomicInteger.incrementAndGet()` đều tuân theo ngữ nghĩa tràn của số nguyên 32-bit; tăng quá `Integer.MAX_VALUE` sẽ quay về `Integer.MIN_VALUE`. Nếu tổng có thể lớn hơn, cân nhắc `AtomicLong`, `LongAdder` và chính sách kiểm tra ngưỡng nghiệp vụ. **Tính nguyên tử không đồng nghĩa chống tràn số**.

### Sai lầm: đọc/ghi không tuân thủ cùng giao thức

Nếu một method `synchronized` tăng `count` nhưng method khác trực tiếp gán `count = 0` mà không khóa, bộ đếm không còn có bảo đảm nhất quán. Giữ field ở mức `private` và tập trung các thao tác vào các method cùng giao thức khóa hoặc cùng đối tượng atomic.

## 10. Quy trình ứng dụng

1. **Xác định quyền sở hữu biến:** nó chỉ sống trong một thread hay được nhiều thread đọc/ghi?
2. **Xác định yêu cầu:** chỉ cần tổng cuối cùng; cần trả ID tăng từng lần; hay cần giữ nhiều field đồng bộ?
3. **Một bộ đếm chia sẻ với thao tác tăng đơn lẻ:** dùng `AtomicInteger` hoặc `AtomicLong` và các method cập nhật nguyên tử.
4. **Đoạn cập nhật nhiều bước hoặc nhiều field:** dùng `synchronized` hoặc cơ chế khóa phù hợp, nhất quán ở mọi đường truy cập.
5. **Thống kê có rất nhiều updater và không đòi snapshot nguyên tử khi chạy:** cân nhắc `LongAdder`.
6. **Kiểm thử:** mô phỏng được tình huống race, xác nhận nguyên nhân; sau sửa, đợi worker hoàn tất và kiểm tra tổng cuối cùng cùng các bất biến liên quan.

**Tự kiểm tra 1:** Hai luồng đều gọi `count++` trên `volatile int count = 0` đúng một lần. Có chắc `count == 2` không? **Không**, vì cả hai vẫn có thể đọc 0 trước khi ghi 1.

**Tự kiểm tra 2:** Với `AtomicInteger` ban đầu bằng 0, hai lần `getAndIncrement()` trả giá trị nào? Theo một thứ tự cập nhật nguyên tử, chúng trả `0` rồi `1`; kết quả cuối là `2`. Không xác định trước **luồng nào** nhận từng giá trị.

**Tự kiểm tra 3:** Main gọi `join()` sau khi hai worker tăng `int count` không đồng bộ. Điều đó tự sửa được lost update không? **Không**. `join()` giúp chờ và quan sát sau khi các luồng kết thúc; nó không bảo vệ phần tăng đã diễn ra.

**Ghi nhớ:** `count++` là biểu thức đọc – tính – ghi, **không phải cập nhật nguyên tử** khi nhiều luồng cùng sửa một biến chia sẻ. `volatile` xử lý vấn đề quan sát bộ nhớ, còn `synchronized` và `AtomicInteger` tạo bảo đảm cập nhật phù hợp; `LongAdder` dành cho bộ đếm thống kê tranh chấp cao với giới hạn khác về việc lấy tổng.
