# Tranh chấp dữ liệu, tính nguyên tử và khả năng nhìn thấy thay đổi

> **Phạm vi:** nền tảng lập trình đa luồng với Java 17+ và cách áp dụng trong ứng dụng Spring Framework. Trọng tâm là trạng thái được nhiều luồng cùng truy cập, điều kiện xảy ra lỗi, các bảo đảm của Java Memory Model (JMM) và lựa chọn công cụ đồng bộ đúng với bất biến cần bảo vệ.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **data race**, **race condition**, **atomicity** (tính nguyên tử) và **visibility** (khả năng nhìn thấy thay đổi).
2. Giải thích tại sao `counter++` có thể mất lượt tăng và tại sao thêm `volatile` không khắc phục được điều đó.
3. Dùng quan hệ **happens-before** để lý giải khi nào kết quả ghi của một luồng được bảo đảm hiển thị với luồng khác.
4. Chọn giữa dữ liệu bất biến, `synchronized`, `volatile`, `AtomicInteger`, lock và concurrent collection.
5. Nhận diện trạng thái chia sẻ nguy hiểm trong Spring singleton bean, công việc `@Async` và ứng dụng nhiều instance.

## 1. Trạng thái chia sẻ tạo ra vấn đề như thế nào?

Một **thread** (luồng) là đơn vị thực thi. Hai luồng có thể chạy xen kẽ hoặc song song. Biến cục bộ của một lần gọi phương thức thường thuộc riêng lần gọi đó; ngược lại, trường của một đối tượng được cả hai luồng tham chiếu tới là **shared mutable state** nếu có thể thay đổi.

Ví dụ, hai HTTP request cùng gọi một phương thức trên một Spring service mặc định có scope `singleton`. Chúng có thể thao tác trên **cùng một đối tượng service**. Nếu service lưu `int count` và cả hai request cùng thực hiện `count++`, kết quả phụ thuộc cách các thao tác xen kẽ.

**Data race** theo JMM xảy ra khi có hai truy cập xung đột tới cùng một biến (ít nhất một truy cập là ghi), thuộc các luồng khác nhau, mà không được sắp thứ tự bởi quan hệ happens-before. **Race condition** là khái niệm rộng hơn: kết quả chương trình phụ thuộc vào thời điểm hoặc thứ tự thực thi, đôi khi ngay cả khi từng truy cập dữ liệu đã được đồng bộ. Cách sửa phải dựa trên *bất biến nghiệp vụ* cần bảo vệ, không chỉ nhìn một biến riêng lẻ.

Một ví dụ đơn giản:

~~~java
class UnsafeCounter {
    private int count;

    void increment() {
        count++;
    }

    int get() {
        return count;
    }
}
~~~

Đây là **đoạn minh họa**, chưa có `main`. Cả `increment()` và `get()` truy cập `count` mà không đồng bộ. Lỗi có thể xuất hiện khi nhiều luồng cùng sử dụng một instance.

## 2. Tính nguyên tử: một phép tăng không phải một bước

**Atomicity** nghĩa là thao tác được quan sát như một đơn vị không thể bị chen vào ở giữa, trong phạm vi bảo đảm của thao tác đó. Câu lệnh `count++` về mặt logic gồm ba bước:

1. Đọc giá trị hiện tại.
2. Tính giá trị mới bằng giá trị cũ cộng 1.
3. Ghi giá trị mới.

Giả sử `count = 0`:

| Thời điểm | Luồng A | Luồng B | `count` |
| --- | --- | --- | ---: |
| 1 | Đọc 0 | | 0 |
| 2 | | Đọc 0 | 0 |
| 3 | Ghi 1 | | 1 |
| 4 | | Ghi 1 | 1 |

Hai lần tăng được yêu cầu nhưng kết quả cuối cùng chỉ là **1**. Đây là *lost update*. Thay `int` bằng `volatile int` vẫn không làm toàn bộ chuỗi đọc–sửa–ghi thành nguyên tử.

### Thí nghiệm tái hiện lost update có kiểm soát

Lưu đoạn sau vào tệp `LostUpdateDemo.java`. `CountDownLatch` buộc hai luồng đọc cùng giá trị ban đầu trước khi được phép ghi. Vì thế kết quả của **thí nghiệm này** là xác định; bản thân lỗi race trong chương trình thực tế thường xuất hiện không ổn định.

~~~java
import java.util.concurrent.CountDownLatch;

public class LostUpdateDemo {
    private static int count = 0;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable increment = () -> {
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

        Thread first = new Thread(increment);
        Thread second = new Thread(increment);
        first.start();
        second.start();

        bothRead.await();
        allowWrite.countDown();
        first.join();
        second.join();

        System.out.println("count = " + count);
    }
}
~~~

Chạy:

~~~bash
javac LostUpdateDemo.java
java LostUpdateDemo
~~~

Kết quả:

~~~text
count = 1
~~~

Hai luồng đọc `0`, sau đó đều ghi `1`. Các latch chỉ tổ chức thứ tự các bước trong **thí nghiệm**; chúng không biến việc cập nhật `count` ở đây thành phép tăng nguyên tử. `join()` bảo đảm luồng `main` chỉ đọc kết quả sau khi cả hai luồng đã kết thúc.

**Điểm phân biệt:** một lần đọc/ghi đơn lẻ của một số kiểu có thể nguyên tử nhưng *chuỗi nhiều thao tác* vẫn không nguyên tử. Theo JLS, việc đọc/ghi `long` hoặc `double` **không volatile** có ngoại lệ lịch sử về tính nguyên tử, nên không nên suy ra mọi phép đọc/ghi primitive đều có bảo đảm giống nhau. Cách viết mã đa luồng an toàn là dựa vào cấu trúc đồng bộ có hợp đồng rõ ràng.

## 3. Visibility: một luồng có thấy giá trị mới không?

**Visibility** trả lời câu hỏi: sau khi luồng A thay đổi dữ liệu, luồng B có được bảo đảm quan sát thay đổi đó không? Trình biên dịch, JIT và CPU có thể dùng thanh ghi, cache và sắp xếp lại thao tác trong giới hạn JMM. Không có quan hệ đồng bộ phù hợp, B có thể quan sát dữ liệu cũ; không được giả định rằng “A đã ghi trước theo đồng hồ” đồng nghĩa với “B chắc chắn đọc được giá trị mới”.

Ví dụ về một cờ dừng:

~~~java
class WorkerLoop implements Runnable {
    private volatile boolean running = true;

    @Override
    public void run() {
        while (running) {
            Thread.onSpinWait();
        }
    }

    void stop() {
        running = false;
    }
}
~~~

Đây là **đoạn minh họa**, không phải ứng dụng độc lập. Với cờ chỉ cần đọc/ghi đơn lẻ, `volatile` tạo bảo đảm hiển thị phù hợp: ghi `running = false` của một luồng *happens-before* các lần đọc `running` về sau trong synchronization order. Nếu bỏ `volatile` và không dùng đồng bộ khác, luồng chạy vòng lặp không có bảo đảm sẽ quan sát lệnh dừng. `Thread.onSpinWait()` chỉ là gợi ý cho CPU, **không phải** công cụ đồng bộ. Trong ứng dụng thực, ưu tiên `interrupt()`, cơ chế chờ có chặn hoặc hủy task thay vì vòng lặp tiêu tốn CPU.

### Atomicity và visibility là hai yêu cầu khác nhau

| Câu hỏi | Ví dụ lỗi | Công cụ thường phù hợp |
| --- | --- | --- |
| **Atomicity**: Cả thao tác có diễn ra không bị chen ngang? | Hai `count++` mất một lần tăng | `synchronized` hoặc `AtomicInteger.incrementAndGet()` |
| **Visibility**: Luồng B có thấy cập nhật của A? | Cờ dừng không được quan sát | `volatile`, lock hoặc quan hệ happens-before khác |
| **Ordering**: Các thao tác có được quan sát theo thứ tự cần thiết? | Đọc trạng thái phụ thuộc trước khi nó được công bố an toàn | Công bố an toàn bằng lock, `volatile`, `final` đúng cách hoặc cấu trúc concurrency |
| **Invariant**: Nhiều trường có luôn nhất quán với nhau? | Trừ tiền và cập nhật sổ cái lệch nhau | Một miền khóa bao trọn thao tác, hoặc transaction/điều phối phù hợp |

`volatile` phù hợp với cờ trạng thái hoặc *một giá trị snapshot độc lập*. Nó **không** làm `x++`, `if (x == 0) x = 1` hoặc hai phép cập nhật ở hai trường thành một giao dịch nguyên tử.

## 4. Java Memory Model và quan hệ happens-before

JMM là hợp đồng quy định những giá trị nào một luồng có thể đọc và các hiệu ứng đồng bộ giữa luồng. Quan hệ **happens-before (HB)** là công cụ chính để suy luận về visibility và thứ tự: nếu hành động A *happens-before* hành động B thì hiệu ứng của A được đảm bảo về mặt hiển thị/thứ tự đối với B theo quy tắc JMM. HB là quan hệ thứ tự logic, **không đơn thuần** là thứ tự thời gian thực.

Những quy tắc cần nhớ:

- **Program order:** trong cùng một luồng, một hành động happens-before các hành động đứng sau nó theo thứ tự chương trình.
- **Monitor:** thao tác mở khóa của `synchronized` happens-before lần khóa tiếp theo trên **chính monitor đó**.
- **Volatile:** một lần ghi vào trường `volatile` happens-before lần đọc tiếp theo của chính trường đó trong synchronization order.
- **Thread.start():** các hành động trước lời gọi `start()` happens-before hành động trong luồng vừa được khởi chạy.
- **Thread.join():** các hành động của luồng đã kết thúc happens-before việc luồng khác trở về thành công từ `join()` đối với luồng ấy.
- **Tính bắc cầu:** nếu A HB B và B HB C thì A HB C. `Future.get()` và nhiều cấu trúc trong `java.util.concurrent` cũng cung cấp các bảo đảm memory consistency được mô tả trong API.

Hình dung thứ tự an toàn của một thông điệp:

~~~text
Luồng A:  data = "ready"  ->  ready = true (volatile write)
                                       |
                                  happens-before
                                       v
Luồng B:                       if (ready) (volatile read)
                                 -> đọc data
~~~

Nếu B quan sát `ready == true` từ thao tác công bố đó, dữ liệu đã ghi trước lần ghi volatile được công bố đúng cho các đọc tiếp theo của B. Khi dùng mẫu này, phải giữ đúng thứ tự ghi dữ liệu rồi mới ghi cờ, và không được tiếp tục sửa dữ liệu chung mà không có giao thức đồng bộ.

**Sự thật quan trọng:** thứ tự xuất hiện của log, thời gian ngủ (`Thread.sleep`), các mức ưu tiên luồng hoặc “máy tôi chạy đúng” **không tạo ra** quan hệ happens-before cho trạng thái chia sẻ. Tránh diễn giải HB thành cam kết scheduler phải thực thi A hoàn toàn trước B.

## 5. Các cách bảo vệ dữ liệu chia sẻ

### 5.1. Ưu tiên không chia sẻ trạng thái có thể thay đổi

Một phương thức chỉ sử dụng tham số, biến cục bộ và các đối tượng bất biến không bị lộ ra ngoài thường dễ cho nhiều request gọi đồng thời. Dùng `record`, trường `final`, defensive copy và giá trị trả về mới khi thích hợp.

`final` giúp ổn định tham chiếu và có quy tắc công bố đặc biệt khi đối tượng được xây dựng đúng, nhưng **không làm bản thân một `ArrayList`/`HashMap` được tham chiếu trở nên bất biến**. Đừng để `this` thoát ra từ constructor trước khi khởi tạo xong.

### 5.2. `synchronized`: vừa loại trừ đồng thời, vừa tạo visibility

~~~java
final class Wallet {
    private long balance;

    Wallet(long openingBalance) {
        this.balance = openingBalance;
    }

    synchronized boolean withdraw(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (balance < amount) {
            return false;
        }
        balance -= amount;
        return true;
    }

    synchronized long balance() {
        return balance;
    }
}
~~~

Đây là **định nghĩa lớp để minh họa**, không có `main`. Mọi truy cập vào `balance` được thực hiện qua cùng monitor là đối tượng `Wallet`. Việc *kiểm tra số dư rồi trừ* nằm trong cùng vùng khóa, nên hai luồng không thể đồng thời rút dựa trên một số dư cũ; khi một luồng nhả khóa, luồng lấy khóa tiếp theo nhìn thấy cập nhật. Điều này giải quyết tính nhất quán **của một đối tượng trong một JVM**; nó không tự giải quyết giao dịch CSDL hay nhiều instance dịch vụ.

Lưu ý: khóa của `synchronized` gắn với **đối tượng monitor**. Hai instance `Wallet` khác nhau có hai monitor khác nhau. Tránh khóa trên chuỗi công khai, `this` bị lộ tùy tiện, hoặc đối tượng mà mã bên ngoài có thể tự khóa. Một `private final Object lock = new Object();` thường giúp kiểm soát miền khóa rõ hơn. Giữ vùng khóa vừa đủ để bảo vệ bất biến và tránh I/O chậm trong khóa.

### 5.3. `AtomicInteger`, `AtomicLong` và CAS

Với bộ đếm độc lập, Java cung cấp các phép tăng, cộng và compare-and-set nguyên tử. `AtomicInteger.incrementAndGet()` là **một phép cập nhật nguyên tử**, trái với `count++`.

Lưu đoạn sau vào `AtomicCounterDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        final int threadCount = 4;
        final int incrementsPerThread = 50_000;
        AtomicInteger count = new AtomicInteger();
        Thread[] workers = new Thread[threadCount];

        for (int i = 0; i < threadCount; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < incrementsPerThread; j++) {
                    count.incrementAndGet();
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("count = " + count.get());
    }
}
~~~

Chạy:

~~~bash
javac AtomicCounterDemo.java
java AtomicCounterDemo
~~~

Kết quả chính xác:

~~~text
count = 200000
~~~

`incrementAndGet()` thực hiện tăng nguyên tử; `join()` bảo đảm mọi luồng đã hoàn thành trước khi in. Không dựa vào `sleep()` để “chờ đủ lâu”. Một `AtomicInteger` chỉ bảo đảm các thao tác nguyên tử được công bố trên **chính biến đó**; nó không tự bảo vệ bất biến trải trên số dư, lịch sử giao dịch và nhiều đối tượng khác.

**CAS** (compare-and-set) cập nhật giá trị nếu vẫn bằng giá trị mong đợi, giúp nhiều cấu trúc không cần monitor cho từng cập nhật. Với tính toán cập nhật bằng `updateAndGet`, hàm được truyền vào có thể được áp dụng lại khi tranh chấp, vì vậy nên là hàm **không có side effect**. `LongAdder` hữu ích cho bộ đếm bị tranh chấp mạnh, nhưng kết quả `sum()` trong lúc đang cập nhật không phải một snapshot nguyên tử toàn cục.

### 5.4. Lock tường minh và collections đồng thời

`ReentrantLock` dùng khi cần `tryLock`, khóa có timeout, khả năng ngắt khi chờ khóa hoặc nhiều `Condition`. Luôn nhả trong `finally`:

~~~java
lock.lock();
try {
    // Đọc và sửa mọi trạng thái nằm trong cùng bất biến.
} finally {
    lock.unlock();
}
~~~

Đoạn trên là **mẫu cấu trúc**, giả định `lock` đã được khai báo là `ReentrantLock`. Một lock không giúp gì nếu còn đường đọc/ghi cùng dữ liệu đi vòng qua lock đó.

- `ConcurrentHashMap` hỗ trợ nhiều thao tác đồng thời và các thao tác nguyên tử **theo key**, chẳng hạn `compute`, `merge`, `putIfAbsent`. Hai lời gọi độc lập `containsKey` rồi `put` **không** phải một thao tác nguyên tử tổng hợp.
- `CopyOnWriteArrayList` hữu ích khi đọc nhiều và cập nhật ít, vì mỗi lần sửa phải sao chép cấu trúc.
- `Collections.synchronizedList(...)` đồng bộ từng phương thức, nhưng khi duyệt bằng iterator vẫn phải tự đồng bộ quanh quá trình duyệt theo hợp đồng API.
- `BlockingQueue` phù hợp cho mô hình producer–consumer; thao tác đưa/lấy phần tử kết hợp với việc chờ có điều kiện, tránh tự viết vòng lặp polling với cờ volatile.
- `ThreadLocal` lưu giá trị theo luồng, không làm trạng thái chia sẻ bên ngoài an toàn. Với thread pool, luồng được tái sử dụng nên cần dọn `ThreadLocal.remove()` nếu tự quản lý.

Chọn cấu trúc theo **thao tác cần nguyên tử**, không theo tên “concurrent”. Map đồng thời không tự tạo transaction nhất quán trên nhiều key.

## 6. Bảng chọn công cụ cho từng yêu cầu

| Nhu cầu thực tế | Lựa chọn đầu tiên | Giới hạn cần nhớ |
| --- | --- | --- |
| Dữ liệu chỉ đọc sau khi cấu hình | Immutable object, `final`, công bố an toàn | `final` không biến object mutable bên trong thành immutable |
| Cờ hủy hoặc trạng thái độc lập | `volatile boolean` hoặc `AtomicBoolean` | Không thực hiện check-then-act tổng hợp |
| Bộ đếm một instance JVM | `AtomicInteger` / `AtomicLong` | Không đại diện counter toàn hệ thống nhiều node |
| Bộ đếm ghi nhiều, đọc thống kê | `LongAdder` | `sum()` không là snapshot nguyên tử giữa các cập nhật |
| Kiểm tra rồi thay đổi nhiều trường | `synchronized` / `ReentrantLock` | Tất cả đường truy cập phải theo cùng quy tắc khóa |
| Tra cứu/cập nhật theo key | `ConcurrentHashMap.compute` / `merge` | Atomic theo thao tác key, không trên nhiều key |
| Trao đổi task giữa các luồng | `BlockingQueue`, `ExecutorService` | Đóng executor và xử lý cancel/lỗi đúng cách |
| Dữ liệu nhất quán qua nhiều service instance | Transaction/conditional update/lock phân tán phù hợp | Lock trong JVM chỉ bảo vệ một tiến trình |

## 7. Liên hệ trực tiếp với Spring Framework

### 7.1. Singleton bean có thể được nhiều luồng gọi cùng lúc

Trong Spring, scope mặc định `singleton` nghĩa là một instance cho một bean definition trong một Spring container. Nó **không đồng nghĩa thread-safe**. Hai request, tác vụ scheduler hoặc `@Async` có thể dùng cùng một service.

Mẫu dễ lỗi:

~~~java
import org.springframework.stereotype.Service;

@Service
public class UnsafeTicketSequence {
    private long lastId;

    public long nextId() {
        return ++lastId; // có thể mất số khi nhiều request gọi đồng thời
    }
}
~~~

Nếu yêu cầu chỉ là số thứ tự duy nhất **trong một instance JVM**, có thể sửa thành:

~~~java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class TicketSequence {
    private final AtomicLong lastId = new AtomicLong();

    public long nextId() {
        return lastId.incrementAndGet();
    }
}
~~~

Hai đoạn trên yêu cầu thư viện Spring Framework để biên dịch, **không phải chương trình Java SE độc lập**. Bản sửa chỉ giải quyết đếm trong một đối tượng/JVM. Nếu có nhiều pod/instance, mỗi nơi sẽ có bộ đếm riêng; nếu ID phải duy nhất trên toàn hệ thống, hãy dùng chiến lược ở CSDL hoặc dịch vụ cấp ID phù hợp.

Đối với service xử lý đơn hàng, cách đơn giản hơn thường là **stateless service**: không lưu user hiện tại, request body hay danh sách kết quả từng request vào trường của singleton. Nhận dữ liệu qua tham số, tạo đối tượng cục bộ, trả kết quả. Đổi bean sang `prototype` hoặc `request` chỉ để né race condition không thay thế việc xác định dữ liệu nào thực sự bị chia sẻ, nhất là khi tham chiếu mutable được truyền sang luồng khác.

### 7.2. `@Async` và thread pool không tự đồng bộ dữ liệu

Spring có `TaskExecutor` và hỗ trợ `@Async` (khi đã bật `@EnableAsync`). Một phương thức `@Async` được gọi qua proxy Spring sẽ gửi công việc tới executor phù hợp; nhiều task có thể chạy đồng thời và cùng tham chiếu tới bean singleton. Nếu một phương thức cùng class tự gọi phương thức `@Async` của chính nó theo kiểu mặc định dùng proxy, lời gọi nội bộ không đi qua proxy để kích hoạt async.

Ví dụ **minh họa trong ứng dụng Spring đã cấu hình async**, không phải tệp chạy độc lập:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportJobService {
    private final AtomicInteger finished = new AtomicInteger();

    @Async("applicationExecutor")
    public CompletableFuture<Integer> finishOneReport() {
        int completed = finished.incrementAndGet();
        return CompletableFuture.completedFuture(completed);
    }
}
~~~

`applicationExecutor` phải là tên của một executor bean đã cấu hình; `@EnableAsync` phải được bật. Mỗi invocation qua proxy được lập lịch bất đồng bộ, còn `AtomicInteger` bảo vệ counter nếu nhiều task chạy cùng lúc. Nếu báo cáo cần ghi CSDL, logic phải xử lý transaction/đồng bộ dữ liệu ở tầng lưu trữ; bộ đếm JVM không thay thế điều đó.

**Ba ranh giới cần phân biệt:**

- `@Async` thay đổi cách công việc được lên lịch, **không** biến mọi trường trong bean thành thread-safe.
- `@Transactional` điều phối giao dịch với tài nguyên được transaction manager quản lý, **không** tự khóa trường Java của singleton bean. Transaction context thông thường gắn với luồng; không mặc định được mang sang luồng `@Async`.
- `synchronized` hoặc `AtomicInteger` chỉ phối hợp các luồng chia sẻ **cùng bộ nhớ JVM**. Không dùng chúng để kết luận rằng dữ liệu giữa nhiều pod, server hay process được cập nhật nguyên tử.

### 7.3. Xuất bản cấu hình nhất quán giữa các luồng

Khi cần thay thế một *snapshot* cấu hình nhiều trường, có thể dùng đối tượng bất biến và một tham chiếu `volatile`:

~~~java
record Limits(int maxJobs, int maxRetries) {}

class LimitsHolder {
    private volatile Limits current = new Limits(10, 3);

    Limits snapshot() {
        return current;
    }

    void replace(int maxJobs, int maxRetries) {
        current = new Limits(maxJobs, maxRetries);
    }
}
~~~

Đây là **đoạn minh họa Java 17**, không có `main`. Mỗi lần `snapshot()` nhận một tham chiếu tới toàn bộ bộ giá trị bất biến thay vì đọc riêng lẻ hai trường mutable có thể bị cập nhật lệch thời điểm. Đọc một lần vào biến cục bộ rồi dùng snapshot đó trong toàn bộ nghiệp vụ. Ví dụ này không tự giải quyết trường hợp nhiều writer cần phối hợp kiểm tra rồi ghi; khi đó phải thiết kế cơ chế cập nhật tương ứng.

## 8. Những lỗi suy luận thường gặp

1. **“`volatile int count` làm `count++` thread-safe.”** Sai: volatile có bảo đảm visibility/order, nhưng chuỗi đọc–cộng–ghi vẫn có thể bị chen ngang. Dùng atomic RMW hoặc lock.
2. **“`final Map` không bao giờ đổi.”** Sai: `final` giữ nguyên tham chiếu, không chặn thêm/xóa entry của map.
3. **“Mỗi thao tác `ConcurrentHashMap` an toàn nên hai thao tác ghép lại cũng nguyên tử.”** Sai: phải dùng API atomic phù hợp như `compute` hoặc một giao thức đồng bộ rộng hơn.
4. **“Tôi đã dùng lock lúc ghi; đọc không cần lock.”** Không đủ nếu đường đọc cần nhìn trạng thái nhất quán và không có quan hệ HB khác.
5. **“Thêm `Thread.sleep(100)` là hết race.”** Sai: sleep chỉ ảnh hưởng lịch thực thi, không đặt ra bảo đảm đồng bộ dữ liệu.
6. **“Spring tạo singleton nên tự xử lý race.”** Sai: container quản lý vòng đời và dependency injection; logic mutable của ứng dụng vẫn do tác giả bảo vệ.
7. **“Transaction của database bảo vệ trường Java trong service.”** Sai: hai phạm vi nhất quán khác nhau.
8. **“Kết quả chạy 1.000 lần đều đúng thì mã thread-safe.”** Không đủ: race có thể hiếm, phụ thuộc JVM, CPU và lịch thực thi.
9. **“`AtomicInteger` giúp cập nhật hai biến cùng lúc.”** Sai: atomicity của một biến không bao phủ bất biến trên nhiều biến.
10. **“Thêm khóa vào mọi phương thức là tối ưu.”** Không nhất thiết: khóa quá rộng làm tăng tranh chấp và có thể gây deadlock; ưu tiên bỏ shared mutable state khi có thể.

## 9. Cách phân tích và kiểm thử vấn đề trong dự án

1. **Xác định dữ liệu chia sẻ:** trường `static`, mutable field trong singleton, cache, map, list, session object, tham chiếu được truyền vào task.
2. **Ghi rõ bất biến:** chẳng hạn “số dư không âm” hay “mỗi đơn hàng chỉ xử lý một lần”, thay vì chỉ ghi “không race”.
3. **Liệt kê đường đọc/ghi và luồng thực thi:** HTTP handlers, `@Async`, scheduler, event listener, executor. Xác định phạm vi một JVM hay nhiều instance.
4. **Chứng minh quan hệ HB hoặc tính atomic:** với mỗi cạnh giao tiếp giữa hai luồng, chỉ ra lock nào, volatile nào, atomic operation nào, hoặc API concurrency nào mang bảo đảm.
5. **Tạo bài test cạnh tranh có chủ đích:** dùng `CountDownLatch`/`CyclicBarrier` để bắt đầu đồng thời hoặc ép một interleaving, đo invariant cuối cùng. Thử nhiều vòng và tải đủ lớn; kết quả pass không là chứng minh không có race. Với vấn đề JMM cấp thấp, có thể nghiên cứu công cụ `jcstress`.
6. **Đo và rà soát sau khi sửa:** xác nhận correctness trước, rồi mới đo contention, latency, throughput; xem thread dump khi nghi deadlock hoặc chờ lock kéo dài. Không tối ưu bằng cách tháo khóa nếu chưa có chứng cứ về an toàn.

### Bài tập tự kiểm tra

**Tình huống A:** Một `@Service` singleton có `private int activeRequests`. Trong `begin()` gọi `activeRequests++`, `end()` gọi `activeRequests--`. Điều gì sai?  
**Gợi ý đáp án:** mất cập nhật vì RMW không nguyên tử; `volatile` không chữa. Với yêu cầu chỉ đếm độc lập trong một JVM, có thể dùng `AtomicInteger`, đồng thời phải bảo đảm mọi đường begin/end cân bằng (kể cả lỗi) qua `try/finally`.

**Tình huống B:** Một luồng đổi `stopped = true`, luồng khác vòng lặp kiểm tra `stopped`. Cần bảo đảm gì?  
**Gợi ý đáp án:** visibility/happens-before; `volatile boolean` có thể đủ cho cờ đơn, nhưng nếu đang chờ I/O hoặc blocking queue thì nên dùng cơ chế hủy/interrupt phù hợp.

**Tình huống C:** Hai request đều kiểm tra `balance >= amount` rồi trừ, dùng `AtomicLong` cho balance. Đã chắc chắn đúng chưa?  
**Gợi ý đáp án:** chưa nếu kiểm tra và trừ là hai atomic calls rời; một request có thể trừ theo số dư cũ. Dùng vòng lặp CAS đúng cách hoặc miền khóa bao cả kiểm tra và cập nhật; với tài khoản trong CSDL/multi-instance cần cơ chế transaction/conditional update ở nơi lưu trữ dữ liệu.

**Tình huống D:** Hai bản sao ứng dụng Spring đều có `AtomicLong nextId`. Có bảo đảm ID không trùng không?  
**Gợi ý đáp án:** không; mỗi bản sao có bộ nhớ riêng. Chọn bộ sinh ID/sequence được phối hợp trên toàn hệ thống.

## 10. Ghi nhớ

- **Data race**: truy cập xung đột không được sắp thứ tự HB; **race condition**: kết quả phụ thuộc thứ tự/thời điểm thực thi rộng hơn.
- **Atomicity** bảo vệ một thao tác/bất biến khỏi interleaving; **visibility** bảo đảm quan sát cập nhật; **ordering** giải thích thứ tự hiệu ứng mà các luồng được phép thấy.
- `volatile`: visibility và ordering cho cờ/giá trị độc lập; **không** làm phép cộng hoặc check-then-act nguyên tử.
- `synchronized`: loại trừ đồng thời và HB trên cùng monitor; `AtomicInteger`: phép RMW nguyên tử trên một biến; concurrent collection: bảo đảm phụ thuộc API cụ thể.
- Trong Spring, **singleton ≠ thread-safe**, **`@Async` ≠ synchronization**, và **transaction database ≠ khóa trường Java**. Đề xuất đầu tiên thường là loại bỏ trạng thái mutable dùng chung, sau đó mới chọn cơ chế bảo vệ đúng bất biến.

## Tài liệu tham khảo chính thức

- Java Language Specification, `17 — Threads and Locks, đặc biệt `17.4.5 về happens-before: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- Java SE 17, `java.util.concurrent` và các memory consistency properties: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html
- Java SE 17, `AtomicInteger` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- Spring Framework, Bean Scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework, Task Execution and Scheduling / `@Async`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
