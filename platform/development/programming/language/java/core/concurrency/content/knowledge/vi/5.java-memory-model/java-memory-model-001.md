# Atomicity, visibility và ordering trong Java

## 1. Ba bảo đảm khác nhau của Java Memory Model

Khi hai thread cùng sử dụng một trạng thái có thể thay đổi, lập trình viên cần trả lời ba câu hỏi:

- **Atomicity (tính nguyên tử):** một thao tác có được thực hiện như một đơn vị không thể xen vào giữa không? Thread khác có thể quan sát trạng thái cập nhật dở hay không?
- **Visibility (khả năng nhìn thấy):** khi thread A ghi một giá trị, điều gì bảo đảm thread B đọc được giá trị đã công bố?
- **Ordering (thứ tự):** các hành động có bắt buộc được quan sát theo quan hệ thứ tự nhất định không, dù compiler/JIT và CPU có thể tối ưu việc thực thi?

**Java Memory Model (JMM)** xác định kết quả đọc/ghi liên luồng nào hợp lệ theo ngôn ngữ Java, cùng những bảo đảm khi dùng `volatile`, `synchronized` và các API concurrency. Đây là mô hình ngôn ngữ; không nên giản lược mọi vấn đề thành “dữ liệu nằm ở CPU cache” vì JMM áp dụng trên các kiến trúc máy khác nhau.

Ba tính chất liên quan nhưng không thay thế nhau. Một biến `volatile` có thể bảo đảm visibility và ordering cho giao thức công bố dữ liệu, nhưng `counter++` trên chính biến đó vẫn không atomic. Một khóa bảo vệ việc cập nhật hai trường có thể giúp giữ bất biến, trong khi hai biến `AtomicInteger` độc lập không tự tạo một giao dịch chung.

### Bản đồ tư duy

| Thuộc tính | Câu hỏi cần kiểm tra | Cơ chế Java thường dùng |
| --- | --- | --- |
| Atomicity | Ai có thể chen vào giữa các bước cập nhật? | `synchronized`, `Lock`, `AtomicInteger.incrementAndGet()` |
| Visibility | Ghi từ thread này khi nào được thread kia nhìn thấy theo bảo đảm JMM? | `volatile`, monitor acquire/release, `join()`, `Future.get()` |
| Ordering | Tác động của các hành động được ràng buộc quan sát theo thứ tự nào? | Quan hệ happens-before, program order, volatile, lock/unlock |

Bài này chỉ xét concurrency và JMM của **Java nói chung**. Các cơ chế đồng bộ ở cấp framework không thuộc phạm vi ở đây.

## 2. Atomicity: “một câu lệnh” không nhất thiết là “một thao tác”

### 2.1. Vì sao `count++` có thể làm mất lần tăng?

~~~java
// Đoạn minh họa trong một đối tượng dùng chung; không phải chương trình độc lập.
int count = 0;

// Hai thread cùng thực thi:
count++;
~~~

Về logic, `count++` đọc giá trị cũ, cộng một, rồi ghi kết quả. Nếu A và B cùng đọc 0, cả hai có thể ghi 1. Hai lần tăng dự kiến cho kết quả 2 lại chỉ còn 1. Đây là **lost update**.

Một lần đọc hoặc ghi `int` là nguyên tử ở mức một thao tác, nhưng chuỗi **đọc–sửa–ghi** không mặc nhiên nguyên tử. `volatile int count` vẫn không làm `count++` thành atomic.

Với `long` và `double` *không khai báo volatile*, đặc tả ngôn ngữ còn cho phép một lần đọc/ghi 64 bit bị chia thành hai nửa 32 bit trên một số triển khai. Ngược lại, mọi lần đọc/ghi `volatile long` hay `volatile double` được bảo đảm nguyên tử. Không nên suy ra từ hành vi của một JVM hiện đại rằng mọi triển khai đều mạnh hơn quy định ngôn ngữ.

### 2.2. Ví dụ Java 17+: mô phỏng lost update có kiểm soát

Race condition ngẫu nhiên có thể không xuất hiện trong nhiều lượt chạy. Để nhìn thấy lỗi rõ ràng, ví dụ này dùng `CountDownLatch` để buộc cả hai worker **đọc giá trị cũ trước khi bất kỳ worker nào ghi**. Đây là thí nghiệm cố ý dựng một thứ tự xen kẽ; không phải cách cập nhật nên dùng trong ứng dụng.

Tạo tệp `AtomicityDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicityDemo {
    private static int ordinary = 0;

    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch bothRead = new CountDownLatch(2);
        AtomicInteger safe = new AtomicInteger(0);

        Runnable job = () -> {
            int snapshot = ordinary;
            bothRead.countDown();

            try {
                bothRead.await();
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                return;
            }

            ordinary = snapshot + 1;
            safe.incrementAndGet();
        };

        Thread first = new Thread(job, "writer-1");
        Thread second = new Thread(job, "writer-2");
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("ordinary = " + ordinary);
        System.out.println("atomic = " + safe.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AtomicityDemo.java
java AtomicityDemo
~~~

Stdout khi các worker hoàn tất:

~~~text
ordinary = 1
atomic = 2
~~~

Cả hai đọc `ordinary == 0` rồi mới được phép ghi 1, nên mất một lần tăng. Trong khi đó, `AtomicInteger.incrementAndGet()` thực hiện thao tác đọc–sửa–ghi nguyên tử, nên giá trị cuối là 2. `join()` bảo đảm thread `main` chờ cả hai worker hoàn tất trước khi in kết quả.

Ví dụ cố tình tách thao tác thành hai pha. Trong chương trình thực, nếu việc cập nhật một biến không có khóa hoặc atomic, kết quả sai có thể chỉ xuất hiện với một số lịch chạy nhất định.

### 2.3. Chọn atomic classes khi nào?

Các loại `AtomicInteger`, `AtomicLong`, `AtomicBoolean`, `AtomicReference<T>` cho phép các phép toán nguyên tử trên một trạng thái tương ứng. Ví dụ:

~~~java
// Đoạn minh họa, không phải chương trình độc lập.
AtomicInteger requests = new AtomicInteger();
int current = requests.incrementAndGet();
boolean changed = requests.compareAndSet(1, 2);
~~~

`compareAndSet(expected, update)` (CAS) chỉ cập nhật nếu giá trị hiện tại khớp kỳ vọng. Một thuật toán CAS có thể phải thử lại khi nhiều thread tranh chấp; với `updateAndGet(...)`, hàm cập nhật cũng có thể bị gọi lại. Hàm đó nên không tạo side effect như gửi email, ghi tệp hoặc giao dịch mạng.

Atomic cho **một biến** không bảo vệ một bất biến trải trên **nhiều biến**: trừ số dư tài khoản A rồi cộng tài khoản B bằng hai thao tác atomic riêng vẫn để thread khác có thể quan sát trạng thái ở giữa. Khi cần một đơn vị cập nhật xuyên nhiều trường, hãy dùng một khóa chung hoặc thay thế nguyên tử toàn bộ một snapshot bất biến theo thiết kế phù hợp.

CAS còn có thể gặp **ABA**: một giá trị đi A → B → A và phép so sánh chỉ nhìn thấy A, mặc dù trạng thái đã thay đổi ở giữa. Nếu lịch sử thay đổi là một phần của bất biến, phải chọn giao thức khác hoặc phiên bản hóa trạng thái.

## 3. Visibility: ghi rồi chưa chắc thread khác đọc thấy đúng

### 3.1. Tình huống cờ dừng không an toàn

~~~java
// Minh họa không an toàn: running là biến thường được dùng bởi hai thread.
boolean running = true;

// Worker:
while (running) {
    processWork();
}

// Thread điều khiển:
running = false;
~~~

Nếu không có đồng bộ giữa hai bên, JMM không bảo đảm worker sẽ quan sát lần ghi `false` của thread điều khiển. Compiler/JIT và CPU có thể tối ưu trong phạm vi JMM, và việc quan sát thấy code “chạy đúng” trên một máy không chứng minh chương trình đúng theo đặc tả.

Với giao thức cờ đơn giản, có thể dùng:

~~~java
// Đoạn minh họa trong class chia sẻ giữa hai thread:
private volatile boolean running = true;
~~~

`volatile` thiết lập bảo đảm visibility và ordering khi hai thread ghi/đọc biến này theo đúng giao thức. Nhưng **visibility không phải liveness**: nếu worker đang block trên I/O không kiểm tra cờ hoặc không được lập lịch, chỉ đổi cờ không khiến nó dừng ngay. Đối với thao tác chờ dài, nên sử dụng primitive điều phối hoặc interrupt phù hợp thay vì spin vô thời hạn.

### 3.2. Happens-before: cách diễn đạt chính xác

**Happens-before (HB)** là quan hệ thứ tự logic của JMM. Nó cho phép xác định liệu một hành động được bảo đảm diễn ra trước hành động khác trong mô hình quan sát bộ nhớ hay không. Không nên xem HB chỉ là thứ tự trên đồng hồ hoặc thứ tự các dòng log.

Những cạnh HB quan trọng:

| Quy tắc | Bảo đảm |
| --- | --- |
| **Program order** | Trong một thread, các hành động trước trong thứ tự chương trình HB hành động sau |
| **Monitor** | Unlock trên một monitor HB lần lock tiếp theo của thread khác trên cùng monitor |
| **Volatile** | Ghi volatile synchronizes-with lần đọc volatile tương ứng sau đó theo thứ tự đồng bộ |
| **Start** | Lời gọi `Thread.start()` HB các hành động của thread được khởi chạy |
| **Join** | Các hành động của worker HB hành động của thread khác sau khi `join()` hoàn thành thành công |
| **CountDownLatch** | Hành động trước `countDown()` HB hành động sau `await()` trả về thành công |
| **Executor/Future** | Theo hợp đồng memory consistency của API, hành động trước submit HB task; hành động của task HB hành động tiếp theo sau `Future.get()` |

HB có tính **bắc cầu**: nếu A HB B và B HB C thì A HB C. Điều này đặc biệt quan trọng trong cơ chế **safe publication**: ghi dữ liệu trước rồi công bố một cờ volatile, thread khác đọc cờ đó và sau đó đọc dữ liệu.

Thấy một giá trị mới mà không có giao thức HB đáng tin cậy không chứng minh mọi lần chạy tiếp theo đều đúng. Ngược lại, `Thread.sleep(...)` không tự tạo quan hệ HB; việc chờ một khoảng thời gian chỉ là ảnh hưởng đến lịch chạy.

### 3.3. Ví dụ Java 17+: công bố dữ liệu qua volatile

Tạo tệp `VolatilePublicationDemo.java`:

~~~java
public class VolatilePublicationDemo {
    private static int payload;
    private static volatile boolean ready;

    public static void main(String[] args)
            throws InterruptedException {
        Thread reader = new Thread(() -> {
            while (!ready) {
                Thread.onSpinWait();
            }
            System.out.println("payload = " + payload);
        }, "reader");

        reader.start();

        payload = 42;
        ready = true;

        reader.join();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac VolatilePublicationDemo.java
java VolatilePublicationDemo
~~~

Khi reader được lập lịch thực thi và đọc thấy `ready == true`, stdout là:

~~~text
payload = 42
~~~

Luồng `main` ghi `payload = 42` trước khi ghi `ready = true`. Thread reader chỉ đọc `payload` sau khi quan sát lần ghi volatile đó. Các quan hệ program order, synchronizes-with và tính bắc cầu tạo HB từ ghi `payload` tới đọc `payload`. Vì vậy dữ liệu được công bố an toàn mặc dù `payload` không khai báo volatile.

`Thread.onSpinWait()` chỉ là một gợi ý CPU/JVM cho vòng chờ ngắn; **không tự tạo đồng bộ hoặc HB**. Ví dụ nhằm minh họa giao thức công bố một lần. Trong ứng dụng thực, dùng `CountDownLatch`, `BlockingQueue`, `Future` hoặc điều kiện có khả năng chờ/hủy thích hợp, thay vì để vòng spin vô hạn. Không tự tái sử dụng bằng cách liên tục đặt `ready = false` rồi bật lại mà không thiết kế thêm giao thức trạng thái.

## 4. Ordering: thứ tự mã nguồn và quan sát liên luồng

### 4.1. Optimizer có thể đổi cách thực thi trong phạm vi JMM

Trong một thread, Java giữ ngữ nghĩa phù hợp với **as-if-serial**: tối ưu không được làm sai kết quả mà thread đơn lẻ được phép quan sát. Điều đó không có nghĩa mọi câu lệnh phải được CPU thực hiện vật lý theo đúng trình tự nguồn.

Khi các thread truy cập shared mutable state mà thiếu đồng bộ, những kết quả quan sát liên luồng có thể rộng hơn tập kết quả mà người đọc mã tuần tự dự đoán. Không nên suy luận rằng “dòng 1 xuất hiện trước dòng 2” đương nhiên tạo quan hệ visibility cho thread khác.

### 4.2. Bài toán hai biến và kết quả khó trực giác

Giả sử `x = 0` và `y = 0` ban đầu. Hai thread thực hiện:

~~~java
// Minh họa tư duy, không phải chương trình độc lập.
// Thread A:               // Thread B:
// x = 1;                  y = 1;
// r1 = y;                 r2 = x;
~~~

Nếu `x` và `y` là biến thường, không có HB giữa hai luồng, JMM cho phép execution trong đó `r1 == 0` **và** `r2 == 0`. Nếu mọi hành động phải xen kẽ hoàn toàn theo một thứ tự tuần tự tổng thể mà vẫn giữ program order của mỗi thread, kết quả đó sẽ không xảy ra. Đây là ví dụ giúp nhận ra hệ quả của data race và thiếu ràng buộc ordering.

Nếu cả `x` và `y` đều khai báo `volatile`, các truy cập volatile tham gia một thứ tự đồng bộ tổng nhất quán với program order; kết quả cả hai đọc 0 không còn hợp lệ với trình tự nêu trên.

**Lưu ý quan trọng:** “Được JMM cho phép” không có nghĩa một lần chạy trên máy cụ thể chắc chắn sẽ hiển thị kết quả đó. Đừng viết test kỳ vọng nhất định thấy hiệu ứng reordering; bài học phải dựa trên hợp đồng của mô hình bộ nhớ.

### 4.3. Data race và sequential consistency

Hai hành động truy cập **cùng một biến**, ít nhất một là ghi, và không được sắp thứ tự bằng HB, tạo nên một **data race**. Ví dụ hai thread cùng thực hiện `count++` trên một biến thường có thể tạo data race.

Với chương trình **được đồng bộ đúng** (không có data race theo tiêu chuẩn JMM), Java cung cấp bảo đảm mạnh về **sequential consistency**: có thể hiểu execution như một sự xen kẽ các hành động theo một thứ tự tổng thể, giữ thứ tự chương trình của mỗi thread.

Sequential consistency không nói thread nào chạy trước, không loại bỏ deadlock, starvation hoặc lỗi logic nghiệp vụ. Nó chỉ thu hẹp tập hành vi bộ nhớ hợp lệ để lập trình viên suy luận một cách nhất quán.

## 5. `volatile` giải quyết và không giải quyết điều gì?

`volatile` thường phù hợp cho cờ trạng thái một chiều hoặc công bố dữ liệu theo một giao thức được thiết kế. Nó bảo đảm các lần đọc/ghi riêng lẻ của biến volatile có ngữ nghĩa visibility và ordering tương ứng; đọc/ghi `volatile long/double` cũng luôn nguyên tử.

Nhưng các câu sau đều **không được `volatile` tự bảo đảm**:

- `volatileCounter++` là một read–modify–write atomic.
- Cập nhật hai trường có thể được quan sát như một transaction.
- `volatile List` biến `ArrayList` được tham chiếu thành thread-safe.
- Thread khác đang block sẽ tự thức dậy ngay sau khi cờ đổi.
- Mọi dữ liệu mutable đằng sau một reference volatile trở thành bất biến hoặc tự bảo vệ khỏi concurrent modification.
- Side effect lên database, file hoặc mạng được rollback khi thread gặp lỗi.

~~~java
// Minh họa sai: dù volatile nhưng phép tăng không nguyên tử.
private volatile int counter = 0;

void increment() {
    counter++;
}
~~~

Muốn đếm chính xác, hãy dùng `AtomicInteger.incrementAndGet()` hoặc synchronized/lock. Với thuật toán cần đọc tình trạng rồi quyết định cập nhật, cần bảo vệ toàn bộ **check-then-act**. Không thể chỉ đặt volatile vào một biến rồi mong chuỗi điều kiện và cập nhật trở thành atomic.

### Safe publication và final fields

Một object nên được khởi tạo hoàn toàn trước khi thread khác dùng nó. Những mẫu công bố an toàn thường là gán tham chiếu qua volatile/atomic, đưa object qua concurrent queue, truy cập dưới khóa hoặc tạo dữ liệu trước khi gọi `Thread.start()`.

Các trường `final` được JMM trao bảo đảm khởi tạo đặc biệt khi constructor thực thi đúng và tham chiếu `this` không thoát trong quá trình xây dựng. Tuy nhiên, `final List<String> items` chỉ khiến **tham chiếu** `items` không thể gán lại, không làm danh sách bên trong bất biến. Nếu một object mutable vẫn có nhiều writer, cần phối hợp những writer đó.

Tránh đăng ký callback, đưa `this` vào cấu trúc dùng chung hoặc khởi chạy thread trong constructor trước khi object được khởi tạo xong.

## 6. `synchronized`: loại trừ lẫn nhau và bảo đảm HB

Một khối `synchronized` dùng **monitor lock**. Những thread tuân thủ cùng khóa nhận được:

1. **Mutual exclusion:** một thread giữ khóa, thread khác không thể đồng thời vào vùng khóa dùng cùng monitor.
2. **Visibility:** unlock từ thread trước có quan hệ HB với lock sau trên cùng monitor.
3. **Ordering:** quan hệ acquire/release giúp những hành động trong critical section được công bố theo giao thức khóa.

Cần bảo đảm mọi đường đọc/ghi cùng một bất biến đều tuân thủ **cùng khóa**. Nếu writer khóa nhưng reader đọc trực tiếp một trường từ bên ngoài, việc reader có được snapshot đúng không còn do khóa đó bảo đảm.

### Ví dụ Java 17+: bảo vệ bất biến hai biến

Tạo tệp `SynchronizedInvariantDemo.java`:

~~~java
public class SynchronizedInvariantDemo {
    static final class Balances {
        private int left = 100;
        private int right = 0;

        synchronized void move(int amount) {
            if (amount < 0 || amount > left) {
                throw new IllegalArgumentException("Invalid amount");
            }
            left -= amount;
            right += amount;
        }

        synchronized String snapshot() {
            return "left=" + left
                + ", right=" + right
                + ", total=" + (left + right);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Balances balances = new Balances();
        Thread first = new Thread(() -> balances.move(40));
        Thread second = new Thread(() -> balances.move(60));

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println(balances.snapshot());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SynchronizedInvariantDemo.java
java SynchronizedInvariantDemo
~~~

Stdout khi cả hai worker hoàn tất:

~~~text
left=0, right=100, total=100
~~~

Vì mỗi `move` giữ khóa trong cả kiểm tra và hai thao tác cập nhật, mọi thứ tự thực hiện của hai thread đều hợp lệ: cả 40 và 60 đều chuyển được, tổng luôn 100. `snapshot()` cũng có cùng monitor, nên khi được gọi, nó không quan sát một lần chuyển đang cập nhật dở. `join()` giúp `main` in kết quả sau khi worker hoàn tất.

Ví dụ này chỉ mô tả dữ liệu **trong bộ nhớ một JVM**. `synchronized` không phải transaction database và không tự bảo vệ trạng thái nằm ở tiến trình khác.

### `Lock` và giới hạn của vùng khóa

`ReentrantLock` là một lựa chọn khác khi cần `tryLock()`, tính năng interruptible lock hoặc điều kiện chờ linh hoạt. Luôn giải phóng khóa trong `finally`:

~~~java
// Minh họa bên trong một phương thức; lock đã khai báo trước.
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

Đừng giữ khóa khi thực hiện I/O chặn lâu nếu có thể tránh. Một vùng khóa quá rộng tăng contention; nhiều khóa lấy theo thứ tự khác nhau có thể gây deadlock. Tính đúng đắn của bất biến cần được xác lập trước, sau đó mới đo và tinh chỉnh hiệu năng.

## 7. Các API khác cũng có hợp đồng memory consistency

### 7.1. `Thread.start()` và `Thread.join()`

Các hành động trong caller trước khi gọi `thread.start()` HB những hành động của worker. Sau khi worker hoàn tất, caller đợi `thread.join()` thành công nhận bảo đảm HB đối với các hành động của worker.

~~~java
// Minh họa, không phải chương trình độc lập.
int[] result = new int[1];
Thread worker = new Thread(() -> result[0] = 99);
worker.start();
worker.join();  // Cần xử lý hoặc khai báo InterruptedException.
System.out.println(result[0]);  // 99 sau join thành công.
~~~

Không thay `join()` bằng `Thread.sleep(100)` chỉ vì bạn đoán worker đã có đủ thời gian chạy; sleep không phải cạnh HB giữa hai thread.

### 7.2. Executor và Future

Theo hợp đồng của `ExecutorService`, các hành động trước khi gửi task HB các hành động của task; các hành động của task HB hành động sau khi kết quả được lấy qua `Future.get()`. Dù vậy, **hai task độc lập** cùng chạy trong executor vẫn cần cơ chế riêng nếu chúng cập nhật chung một biến.

`Future.get()` có thể chặn và có thể ném `ExecutionException` khi task lỗi. `get(timeout, unit)` giới hạn thời gian caller chờ, không tự hủy một task đang chạy. Cần quản lý cancellation, timeout và exception rõ ràng.

### 7.3. CountDownLatch và BlockingQueue

`CountDownLatch` thiết lập quan hệ memory consistency từ hành động trước `countDown()` đến hành động sau `await()` thành công. `BlockingQueue` cung cấp cơ chế truyền phần tử và hợp đồng công bố dữ liệu phù hợp giữa producer và consumer. Các primitive này thường rõ ràng hơn việc tự chia sẻ nhiều cờ boolean bình thường rồi đoán trạng thái của nhau.

## 8. Thiết kế theo yêu cầu, không theo thói quen thêm volatile

| Trường hợp | Công cụ phù hợp | Cần kiểm tra |
| --- | --- | --- |
| Cờ dừng đơn giản, worker chủ động kiểm tra | `volatile boolean` | Thread có thực sự quay lại đọc cờ hoặc được đánh thức không? |
| Đếm số event độc lập | `AtomicInteger` hoặc `LongAdder` khi phù hợp | Có cần snapshot chính xác trong khi cập nhật không? |
| Chuyển giá trị giữa hai trường, giữ invariant | `synchronized` hoặc `Lock` | Tất cả đường đọc/ghi có theo cùng giao thức không? |
| Công bố dữ liệu đã khởi tạo xong | Volatile reference, immutable snapshot, queue, start/join | Có để reference thoát trước khi khởi tạo xong không? |
| Nhiều thread sửa collection | Concurrent collection phù hợp | Một chuỗi thao tác “kiểm tra rồi ghi” có cần atomic không? |
| Không cần trạng thái chia sẻ | Thread confinement, immutable values, message passing | Có thể thiết kế tránh lock ngay từ đầu không? |

`LongAdder` giúp giảm tranh chấp cho nhiều phép cộng trong những trường hợp thống kê. Tuy nhiên, `sum()` không phải snapshot nguyên tử khi các update vẫn đang diễn ra; không dùng nó như bộ đếm transaction cần kiểm tra điều kiện chính xác tức thời.

Với dữ liệu chia sẻ, điều quan trọng là thiết kế **giao thức sở hữu và công bố** trước khi chọn công cụ; code có thể không có data race nhưng vẫn có deadlock, starvation hoặc lỗi nghiệp vụ.

## 9. Sai lầm phổ biến

**“Một câu lệnh Java thì atomic.”** Không đúng với `count++`, `map.get(k)` rồi `map.put(k, v)` hoặc các chuỗi check-then-act.

**“Có volatile là đủ thread-safe.”** Không đúng với nhiều biến phải nhất quán hoặc một object mutable được sửa đồng thời.

**“Một lần đọc đã thấy giá trị mới chứng minh visibility được bảo đảm.”** Chạy thử đúng không thay thế được phân tích HB; tối ưu JIT và lịch chạy có thể khác ở lần khác.

**“Thread.sleep tạo ordering.”** Sleep ảnh hưởng lịch chạy chứ không tạo quan hệ đồng bộ HB cần thiết.

**“Lúc ghi dùng synchronized, lúc đọc không cần.”** Reader có thể quan sát trạng thái không nhất quán nếu đọc ngoài giao thức khóa.

**“Dùng hai AtomicInteger là một transaction.”** Mỗi lần cập nhật một biến là atomic; hai cập nhật chưa chắc được người khác quan sát cùng lúc.

**“Không thấy race trong stress test nghĩa là đã chứng minh đúng.”** Test có thể phát hiện lỗi nhưng không kiểm tra được mọi execution hợp lệ. Cần lập luận theo JMM và rà soát mọi đường truy cập.

**“Data-race-free nghĩa là ứng dụng không còn lỗi concurrency.”** Không đúng: deadlock, logic thứ tự nghiệp vụ, timeout và liveness vẫn có thể sai dù mỗi truy cập bộ nhớ được đồng bộ.

## 10. Kiểm thử và quan sát hành vi

Khi kiểm tra các tính chất của JMM, hãy đo **bất biến**, không chỉ đo chương trình có ném exception hay không:

1. Với **atomicity**, tổ chức nhiều writer cùng cập nhật, so kết quả với tổng dự kiến. Có thể dùng latch/barrier để chủ động tạo điều kiện tranh chấp, như `AtomicityDemo`.
2. Với **visibility**, xác định cạnh HB nào công bố dữ liệu. Test không nên dùng sleep làm tín hiệu duy nhất; cần timeout và cơ chế phối hợp đúng.
3. Với **ordering**, phân tích những execution được/không được JMM cho phép. Kết quả “có thể xảy ra” không nhất thiết xuất hiện trên mọi JVM.
4. Với **invariant nhiều trường**, thử reader quan sát trong lúc writer cập nhật, rồi kiểm tra toàn bộ snapshot có hợp lệ không.
5. Với hiệu năng, theo dõi lock contention, CPU, throughput, latency, thời gian chờ queue và thread states bằng profiler, thread dump hoặc Java Flight Recorder khi phù hợp.

Stress test và công cụ chuyên biệt như JCStress có thể giúp phát hiện một số hành vi liên luồng. Chúng hỗ trợ lập luận đúng đắn, không thay thế chứng minh theo các quy tắc JMM. Cũng cần phân biệt phép đo hiệu năng với kiểm thử an toàn bộ nhớ.

## 11. Câu hỏi tự kiểm tra

**1.** Vì sao `volatile int counter` vẫn có thể mất cập nhật khi hai thread cùng chạy `counter++`?

Vì `volatile` không biến tổ hợp đọc–cộng–ghi thành một phép atomic; hai thread có thể cùng đọc giá trị cũ. Sử dụng `AtomicInteger.incrementAndGet()` hoặc khóa phù hợp.

**2.** Một thread ghi `payload = 42` rồi `ready = true` với `ready` là volatile; thread khác đọc `ready == true` rồi đọc `payload`. Bảo đảm nào làm phép công bố an toàn?

Program order, quy tắc synchronizes-with của volatile và tính bắc cầu của happens-before tạo quan hệ HB từ ghi payload đến đọc payload.

**3.** Hai biến `AtomicInteger` quản lý hai số dư có tự bảo đảm tổng luôn đúng khi chuyển một lượng tiền giữa chúng không?

Không. Một phép update của từng biến nguyên tử, nhưng hai update không phải một transaction chung. Cần khóa hoặc biểu diễn snapshot bất biến có cập nhật nguyên tử phù hợp.

**4.** Vì sao chạy code thành công nhiều lần vẫn chưa chứng minh code thiếu đồng bộ là thread-safe?

Vì những lần chạy chỉ khám phá một phần lịch thực thi. Data race có thể chưa bộc lộ; tính đúng đắn phải được lập luận bằng các bảo đảm JMM và bất biến của chương trình.

**5.** Một thread chờ `Thread.sleep(200)` sau khi khởi động worker rồi đọc kết quả có chắc chắn thấy mọi cập nhật của worker không?

Không. Sleep không đợi worker hoàn tất và không tự tạo cạnh happens-before. Dùng `join()`, `Future.get()` hoặc primitive phù hợp với bài toán.

**Kết luận:** **Atomicity** bảo vệ tính toàn vẹn của một thao tác; **visibility** bảo đảm công bố dữ liệu; **ordering** ràng buộc thứ tự quan sát. Thiết kế concurrency đúng trong Java cần tạo đủ quan hệ happens-before và bảo vệ toàn bộ bất biến dùng chung, thay vì chỉ thêm `volatile` hoặc `synchronized` mà không hiểu phạm vi của chúng.