# Phân biệt data race, race condition và logic race trong Java

## 1. Mục tiêu và phạm vi

Sau bài học, bạn có thể:

- Phân biệt **data race** theo quan hệ *happens-before* trong Java Memory Model (JMM), **race condition** theo tính đúng đắn của hành vi, và **logic race** ở cấp thao tác hoặc quy tắc nghiệp vụ.
- Giải thích vì sao có race condition **ngay cả khi không có data race**, cũng như vì sao data race có thể chưa biểu hiện thành lỗi trong một lần chạy.
- Nhận ra các mẫu lỗi **read–modify–write**, **check–then–act** và **time-of-check to time-of-use (TOCTOU)**.
- Chọn đúng cơ chế Java như **synchronized**, **AtomicInteger.compareAndSet()**, cấu trúc concurrent, hoặc giao thức trao tín hiệu để bảo vệ một *bất biến* (invariant).
- Tạo ví dụ có lịch xen kẽ được kiểm soát để tái hiện lỗi, hiểu giới hạn của stress test, và kiểm tra kết quả bằng điều kiện nghiệp vụ thay vì chỉ nhìn thứ tự log.

Phạm vi là **Java concurrency nói chung** ở mức JDK và JMM. Những cơ chế riêng của Spring thuộc chương khác.

## 2. Ba thuật ngữ có phạm vi khác nhau

### 2.1. Data race: các truy cập xung đột thiếu thứ tự happens-before

Trong thuật ngữ JMM, một **data race** xuất hiện khi có **hai truy cập xung đột** tới cùng một biến, do các thread khác nhau thực hiện, **ít nhất một truy cập là ghi**, và **không có quan hệ happens-before** sắp thứ tự giữa hai truy cập đó.

Ví dụ kinh điển là nhiều thread cùng thao tác một trường **int** thông thường mà không có cơ chế đồng bộ hóa thích hợp.

~~~java
// Đoạn minh họa, không phải chương trình độc lập:
int count = 0;
// Thread A và thread B cùng thực hiện:
count++; // Đọc, tính toán, rồi ghi; không phải phép tăng nguyên tử.
~~~

Kết quả có thể mất cập nhật (*lost update*). Một lịch thực thi có thể là:

~~~text
Ban đầu count = 0
Thread A: đọc count -> 0
Thread B: đọc count -> 0
Thread A: tính 0 + 1 -> 1
Thread B: tính 0 + 1 -> 1
Thread A: ghi count = 1
Thread B: ghi count = 1
Cuối cùng count = 1 dù đã yêu cầu tăng hai lần.
~~~

Đây là lịch minh họa lỗi; thread có thể xen kẽ theo các cách khác nhau. Hậu quả không chỉ là mất cập nhật: đọc dữ liệu cũ, vi phạm bất biến giữa các trường và hành vi khó dự đoán theo JMM cũng có thể xuất hiện.

**Data race là khái niệm về truy cập bộ nhớ và đồng bộ hóa**, không phải nhãn kết luận nghiệp vụ đã thất bại. Có data race trong chương trình là dấu hiệu thiết kế nguy hiểm; lỗi có thể không bộc lộ trong một lần thử.

### 2.2. Race condition: kết quả đúng hay sai phụ thuộc cách xen kẽ

**Race condition** là tình huống mà hành vi quan trọng của chương trình phụ thuộc vào thứ tự/thời điểm các hoạt động xảy ra, nhưng chương trình **không thực thi ràng buộc thứ tự hoặc điều kiện nguyên tử cần thiết**. Khi một lịch xen kẽ hợp lệ dẫn tới vi phạm yêu cầu, đó là race condition gây lỗi.

Ví dụ:

- Hai worker cùng xử lý một job cần **chỉ xử lý một lần**.
- Hai người cùng giữ chỗ cuối cùng dù kho chỉ còn một.
- Một thread kiểm tra tài nguyên tồn tại, nhưng thread khác thay đổi tài nguyên trước lúc sử dụng.
- Hai giao dịch cùng đọc số dư, mỗi giao dịch tự cho rằng vẫn đủ tiền.

**Race condition rộng hơn data race.** Nó có thể liên quan bộ nhớ chia sẻ thiếu đồng bộ, nhưng cũng có thể xảy ra với những thao tác riêng lẻ đều thread-safe, thậm chí giữa các tiến trình hoặc máy khác nhau.

Không nên gọi mọi thứ tự bất định là lỗi. Ví dụ hai worker chỉ in hai dòng log không phụ thuộc nhau, rồi cùng hoàn thành, có thể cho hai thứ tự hợp lệ mà vẫn đúng đặc tả.

### 2.3. Logic race: đứt gãy ở quy tắc phối hợp nhiều bước

**Logic race** là cách gọi thường dùng cho race condition ở **logic ứng dụng**: mỗi thao tác nhỏ có thể an toàn, nhưng **chuỗi thao tác** không được bảo vệ như một quyết định thống nhất.

Mẫu điển hình:

~~~text
1. Kiểm tra điều kiện P có đúng không?
2. Một thread khác thay đổi trạng thái liên quan.
3. Tiếp tục hành động dựa trên kết quả kiểm tra cũ.
~~~

Ví dụ: **stock.get()** và **stock.decrementAndGet()** đều là thao tác thread-safe của **AtomicInteger**, nhưng **“nếu còn hàng thì trừ đúng một đơn vị”** không tự trở thành một giao dịch nguyên tử khi tách thành hai lời gọi.

**Lưu ý thuật ngữ:** *Data race* có định nghĩa kỹ thuật trong JMM. *Race condition* là khái niệm rộng về tính đúng đắn. *Logic race* không phải một loại enum hay thuật ngữ chuẩn được JMM định nghĩa độc lập; ở bài này nó chỉ các race condition làm sai **bất biến và quy trình nhiều bước**. Tên gọi có thể thay đổi giữa các tài liệu, nhưng mẫu lỗi và cách sửa vẫn vậy.

## 3. So sánh ngắn và quan hệ giữa chúng

| Góc nhìn | Data race | Race condition | Logic race |
| --- | --- | --- | --- |
| Điều đang xét | Truy cập cùng biến thiếu thứ tự happens-before | Kết quả phụ thuộc lịch thực thi và có thể vi phạm yêu cầu | Quy tắc nhiều bước bị xen kẽ làm sai |
| Định nghĩa | Có cơ sở hình thức trong JMM | Phụ thuộc đặc tả và yêu cầu đúng đắn | Một cách gọi thực hành của race condition |
| Bắt buộc có dữ liệu chung bị đọc/ghi không an toàn? | Có truy cập xung đột không được HB sắp thứ tự | Không | Không; có thể dùng toàn API atomic/thread-safe |
| Phát hiện từ code? | Xem read/write, synchronization và happens-before | Xem bất biến, hợp đồng nghiệp vụ, lịch xen kẽ | Xem check–then–act và transition |
| Ví dụ | Ghi chung trường int không đồng bộ | Hai đơn cùng nhận suất cuối cùng | Kiểm tra stock.get() rồi decrementAndGet() |
| Cách xử lý | Tạo đồng bộ hóa/atomicity/ownership đúng | Chốt tính nguyên tử, thứ tự hoặc giao thức theo đặc tả | Gộp quyết định thành thao tác nguyên tử/transaction |

Quan hệ thường gặp:

~~~text
               RACE CONDITIONS
              /               \
     Có data race         Không có data race
      (truy cập bộ nhớ)    (ví dụ logic check-then-act
                            trên các biến atomic)
                        \
                         LOGIC RACE là tên gọi
                         cho lỗi quy tắc nhiều bước
~~~

Đừng hiểu sơ đồ này như các tập hợp loại trừ nhau: **một logic race có thể đồng thời chứa data race** nếu cả thao tác lẫn dữ liệu chung đều thiếu đồng bộ. Ngược lại, một data race không nhất thiết tạo ra vi phạm nghiệp vụ quan sát được ở mọi lịch thực thi.

### Ba tình huống để tự phân loại

| Tình huống | Nhận xét |
| --- | --- |
| Hai thread thực hiện **plainCounter++** không đồng bộ để cộng tổng chính xác | Có data race và có race condition gây mất cập nhật |
| Hai thread dùng **AtomicInteger.get()** rồi **decrementAndGet()** nếu còn hàng | Không thiếu an toàn ở từng thao tác atomic, nhưng có logic race và race condition |
| Hai thread độc lập cùng log “finished”, thứ tự dòng đổi qua các lần chạy | Thứ tự bất định; không phải bug nếu đặc tả không yêu cầu thứ tự |

## 4. Nền tảng JMM: visibility, atomicity và ordering

Một chương trình concurrency phải phân biệt ba câu hỏi:

1. **Visibility**: một thread có nhìn thấy cập nhật từ thread khác không?
2. **Atomicity**: thao tác nhiều bước có bị thread khác chen vào phần giữa không?
3. **Ordering**: những thao tác nào phải xảy ra trước những thao tác khác?

JMM dùng quan hệ **happens-before** để định nghĩa các bảo đảm nhìn thấy bộ nhớ và thứ tự. Những quy tắc thường dùng:

- Các thao tác trước **Thread.start()** trong thread tạo có happens-before tới thao tác trong thread được khởi động.
- Các hành động của worker có happens-before các hành động của thread khác sau khi **join()** trả về thành công vì worker đã kết thúc.
- **Unlock** một monitor có happens-before với **lock** tiếp theo trên cùng monitor.
- Ghi vào biến **volatile** có happens-before với lần đọc volatile tiếp theo tương ứng trong synchronization order.
- Các thao tác của **AtomicInteger**, **AtomicReference** có hợp đồng bộ nhớ và tính nguyên tử tương ứng; **compareAndSet()** còn kiểm tra và thay đổi trong một thao tác có điều kiện.
- Các tiện ích concurrent như **CountDownLatch** và **BlockingQueue** cung cấp quan hệ bộ nhớ được quy định trong hợp đồng API khi dùng đúng.

**Thread.sleep()**, **Thread.yield()** và thứ tự xuất hiện của log không tạo happens-before cho dữ liệu chia sẻ. Tăng thời gian ngủ chỉ làm lỗi ít/tăng khả năng xuất hiện theo lịch chạy, không chứng minh chương trình đã đúng.

### volatile giúp gì và không giúp gì?

~~~java
// Đoạn minh họa, không phải chương trình độc lập:
volatile boolean stopRequested = false;
volatile int counter = 0;
~~~

- **stopRequested** có thể dùng làm cờ yêu cầu dừng đơn giản nếu mọi đọc/ghi có liên quan đều theo giao thức đã thiết kế.
- Tuy nhiên, **counter++** vẫn gồm đọc, cộng và ghi; khai báo **volatile** không biến ba bước đó thành một phép tăng nguyên tử.
- Nếu cần cộng chính xác dưới cạnh tranh, dùng **AtomicInteger.incrementAndGet()**, **LongAdder** khi phù hợp, hoặc khóa bảo vệ trạng thái.

**Không có data race** là điều kiện quan trọng cho lập luận dựa trên JMM, nhưng vẫn **chưa đủ** để kết luận bất biến nghiệp vụ đúng. Ta còn phải xét tính nguyên tử của **cả chuỗi quyết định**.

## 5. Ví dụ Java 17+: tái hiện data race có kiểm soát

Thử chạy vòng lặp **counter++** hàng triệu lần là cách hay nhìn thấy lost update, nhưng đôi khi kết quả tình cờ vẫn đúng. Để minh họa một lịch lỗi có kết quả xác định, ta sử dụng **CountDownLatch** chỉ nhằm buộc cả hai thread **đọc giá trị cũ trước khi ghi**.

Tệp **DataRaceDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class DataRaceDemo {
    static class Counter {
        int value = 0; // Trạng thái chung không được bảo vệ.
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch releaseWrites = new CountDownLatch(1);

        Runnable increment = () -> {
            int next = counter.value + 1;
            bothRead.countDown();

            try {
                releaseWrites.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            counter.value = next; // Hai ghi xung đột, không có thứ tự HB.
        };

        Thread a = new Thread(increment, "counter-a");
        Thread b = new Thread(increment, "counter-b");
        a.start();
        b.start();

        bothRead.await();
        releaseWrites.countDown();

        a.join();
        b.join();
        System.out.println("counter = " + counter.value);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 DataRaceDemo.java
java DataRaceDemo
~~~

Stdout (không có interrupt bên ngoài):

~~~text
counter = 1
~~~

**Diễn giải từng bước:**

1. Cả A và B lấy **counter.value = 0** để tính **next = 1** trước khi main giải phóng latch **releaseWrites**.
2. Sau tín hiệu, mỗi worker gán **counter.value = 1**. Hai phép ghi này không được sắp thứ tự bằng happens-before với nhau, nên là các truy cập xung đột thuộc **data race**.
3. **a.join()** và **b.join()** bảo đảm main chỉ đọc sau khi hai worker đã hoàn thành; giá trị cuối là **1**, trong khi yêu cầu tăng hai lần lẽ ra phải cho **2**.
4. Các latch **chỉ ép lịch xen kẽ để tái hiện lỗi**, không bảo vệ phần ghi và không giải quyết bất biến “mỗi lần tăng phải được cộng”.

Mặc dù ví dụ in kết quả xác định, **data race không bắt buộc luôn in sai** trong các chương trình thông thường. Lịch chạy khác có thể cho kết quả đúng tình cờ. Việc hai thread cùng viết một giá trị hoặc nhiều lần test không phát hiện lỗi không chứng minh an toàn.

### Sửa bằng phép tăng nguyên tử

Tệp **AtomicCounterDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger counter = new AtomicInteger(0);
        Runnable increment = counter::incrementAndGet;

        Thread a = new Thread(increment, "counter-a");
        Thread b = new Thread(increment, "counter-b");
        a.start();
        b.start();

        a.join();
        b.join();
        System.out.println("counter = " + counter.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicCounterDemo.java
java AtomicCounterDemo
~~~

Stdout:

~~~text
counter = 2
~~~

Hai phép **incrementAndGet()** có tính nguyên tử; không còn lost update cho bộ đếm này. **join()** bảo đảm main đọc sau khi cả hai tăng. Nếu bất biến cần bảo vệ **nhiều trường cùng lúc**, một AtomicInteger đơn lẻ không tự giải quyết toàn bộ vấn đề.

## 6. Ví dụ logic race dù mọi thao tác riêng lẻ đều atomic

Một kho còn **1 sản phẩm**. Quy tắc nghiệp vụ yêu cầu:

> Chỉ nhận đặt hàng nếu kho còn hàng; không bao giờ nhận hai đơn khi chỉ còn một sản phẩm.

Mã sai:

~~~java
// Đoạn minh họa: stock là một AtomicInteger đã được tạo trước đó.
if (stock.get() > 0) {
    stock.decrementAndGet();
    acceptOrder(); // Hàm nghiệp vụ giả định, chưa được định nghĩa.
}
~~~

**get()**, **decrementAndGet()** đều thread-safe, nhưng **cặp thao tác kiểm tra rồi trừ** không nguyên tử. Hai thread có thể cùng đọc stock = 1 rồi mỗi thread trừ một lần. Kết quả **stock = -1** và hai đơn được chấp nhận. Đây là **logic race** và **race condition**, dù không cần data race trên biến stock.

### Ví dụ 2: ép cả hai cùng vượt qua điều kiện kiểm tra

Tệp **LogicRaceDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class LogicRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger stock = new AtomicInteger(1);
        AtomicInteger accepted = new AtomicInteger(0);
        CountDownLatch bothChecked = new CountDownLatch(2);

        Runnable reserve = () -> {
            if (stock.get() > 0) {
                bothChecked.countDown();
                try {
                    bothChecked.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }

                stock.decrementAndGet();
                accepted.incrementAndGet();
            }
        };

        Thread a = new Thread(reserve, "buyer-a");
        Thread b = new Thread(reserve, "buyer-b");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("accepted = " + accepted.get());
        System.out.println("stock = " + stock.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LogicRaceDemo.java
java LogicRaceDemo
~~~

Stdout (không có interrupt từ bên ngoài):

~~~text
accepted = 2
stock = -1
~~~

**Vì sao ví dụ đáng chú ý?**

- Trước khi có decrement, cả hai thread đều thấy stock = 1. Latch khiến mỗi thread chờ thread kia sau khi đã vượt qua kiểm tra, nên lịch vi phạm bất biến được tái hiện có chủ đích.
- **AtomicInteger** giữ mỗi lần cập nhật riêng lẻ nguyên tử, nên không bị lost update theo kiểu plain int: cả hai lần decrement đều có hiệu lực và kho đi từ 1 xuống -1.
- Lỗi nằm ở khoảng trống giữa **đọc điều kiện** và **hành động**. Đây là **time-of-check to time-of-use (TOCTOU)**.
- Việc tăng số thread, thêm **sleep()** hoặc **yield()** có thể đổi xác suất lỗi nhưng không sửa quy tắc.

**Không nên dùng đoạn code trên để đặt hàng thật**; đây là ví dụ cố ý vi phạm nghiệp vụ nhằm nhận ra logic race.

## 7. Sửa logic race bằng CAS bảo vệ cả quyết định

Ta thay **check rồi decrement** bằng một chu trình **compare-and-set (CAS)**: đọc số lượng hiện tại, từ chối nếu bằng 0, và chỉ trừ khi giá trị vẫn đúng bằng số đã đọc. Nếu thread khác đã thay đổi stock, thử lại.

Tệp **SafeReservationDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class SafeReservationDemo {

    static boolean tryReserve(AtomicInteger stock) {
        while (true) {
            int observed = stock.get();
            if (observed <= 0) {
                return false;
            }
            if (stock.compareAndSet(observed, observed - 1)) {
                return true;
            }
            // Một thread khác đã đổi stock; đọc lại và thử lại.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger stock = new AtomicInteger(1);
        AtomicInteger accepted = new AtomicInteger(0);

        Runnable reserve = () -> {
            if (tryReserve(stock)) {
                accepted.incrementAndGet();
            }
        };

        Thread a = new Thread(reserve, "buyer-a");
        Thread b = new Thread(reserve, "buyer-b");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("accepted = " + accepted.get());
        System.out.println("stock = " + stock.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeReservationDemo.java
java SafeReservationDemo
~~~

Stdout:

~~~text
accepted = 1
stock = 0
~~~

Hai thread có thể thử CAS cùng lúc, nhưng chỉ một phép chuyển **1 → 0** thành công; thread còn lại thấy 0 và từ chối. Kết quả đúng bất biến trong phạm vi **một AtomicInteger trong một JVM**, với giả định các cập nhật stock khác cũng đi qua giao thức tương thích.

**Điều kiện quan trọng:** Ví dụ chỉ giữ **số lượng hàng trong bộ nhớ**. Nếu thao tác còn gồm ghi đơn hàng, trừ tiền hoặc ghi DB, một CAS trên stock **không làm các side effect bên ngoài nguyên tử**. Cần thiết kế transaction, idempotency, hoặc cơ chế commit/compensation phù hợp tại ranh giới dữ liệu thật.

### Có thể dùng synchronized khi quyết định liên quan nhiều trường

Ví dụ minh họa API lớp, không phải chương trình độc lập:

~~~java
final class Inventory {
    private int stock;
    private int reserved;

    Inventory(int initialStock) {
        stock = initialStock;
    }

    synchronized boolean reserveOne() {
        if (stock <= 0) {
            return false;
        }
        stock--;
        reserved++;
        return true;
    }

    synchronized int remaining() {
        return stock;
    }

    synchronized int reservedCount() {
        return reserved;
    }
}
~~~

Phương thức **reserveOne()** giữ cùng một monitor trong suốt bước kiểm tra và cập nhật cả hai trường. Những phương thức khác truy cập hai trường cũng phải dùng giao thức khóa tương thích. Nếu chỉ khóa quanh **stock--** mà để **if (stock > 0)** ngoài khóa, logic race vẫn còn.

Với bộ nhớ chia sẻ, điểm mấu chốt là **phạm vi atomicity của bất biến**, không phải số lượng từ khóa **synchronized** hay số lượng trường khai báo **volatile**.

## 8. Mẫu lỗi check–then–act trong API concurrent

Sử dụng một cấu trúc thread-safe không có nghĩa **mọi tổ hợp nhiều lời gọi** trên nó tự nguyên tử.

### ConcurrentHashMap: containsKey() rồi put()

~~~java
// Đoạn minh họa logic race:
// map là ConcurrentHashMap<String, String> đã được khai báo.
if (!map.containsKey("job-42")) {
    map.put("job-42", "RUNNING");
}
~~~

Mỗi lời gọi **containsKey()** và **put()** là thread-safe, nhưng hai thread có thể cùng thấy khóa chưa tồn tại rồi cùng làm việc. Nếu chỉ muốn **ghi một giá trị khi khóa chưa có**, dùng:

~~~java
// Đoạn minh họa: putIfAbsent là thao tác có điều kiện nguyên tử.
String previous = map.putIfAbsent("job-42", "RUNNING");
if (previous == null) {
    // Lần ghi này đã thành công với key chưa có trước đó.
}
~~~

Lưu ý: nếu cả hai thread đã **gọi tác vụ tốn kém hoặc side effect ở trước putIfAbsent()**, putIfAbsent không thể hoàn tác hoặc ngăn việc bên ngoài đã chạy trùng. Cần đặt quyết định cấp quyền làm việc đúng vị trí trong giao thức. Khi cần khởi tạo giá trị theo key, **computeIfAbsent()** có ngữ nghĩa khác với cặp **get/put**, nhưng mapping function phải tuân thủ hợp đồng của collection và không nên chứa side effect không kiểm soát.

### Concurrent collection: kiểm tra rỗng rồi lấy

~~~java
// Minh họa logic race, queue đã khai báo trước:
if (!queue.isEmpty()) {
    Object item = queue.poll();
    // item vẫn có thể null nếu thread khác lấy phần tử trước.
}
~~~

Nếu phải nhận đúng một phần tử, hãy làm việc với kết quả **poll()** và xử lý **null** khi rỗng; nếu cần đợi có phần tử, cân nhắc **BlockingQueue.take()**. Hai lời gọi **isEmpty() + poll()** không biến thành một quyết định giao hàng nguyên tử.

### Data race và logic race có thể cùng tồn tại

Nếu **stock** là plain int không được khóa, đoạn **if(stock > 0) stock--;** có thể chứa **cả data race** lẫn logic race. Thay nó bằng AtomicInteger nhưng giữ nguyên hai bước **get() rồi decrementAndGet()** chỉ sửa khía cạnh truy cập đồng bộ hóa của từng thao tác, **chưa sửa bất biến**.

## 9. Race condition không chỉ nằm trong RAM

TOCTOU cũng tồn tại trong hệ thống file, database, mạng và các quy trình liên tiến trình:

- Kiểm tra file tồn tại, sau đó mở file: một tác nhân khác có thể xóa/thay thế file trong khoảng giữa.
- Đọc đơn hàng đang PENDING, sau đó cập nhật RUNNING: worker khác có thể đã nhận cùng đơn trước khi cập nhật.
- Kiểm tra số lượng trong DB rồi phát sinh đơn ở một transaction khác: hai request có thể cùng qua kiểm tra.
- Nhận một thông điệp rồi xử lý; khi thông điệp được gửi lại, side effect có thể bị thực hiện lần hai nếu không có idempotency.

Các trường hợp này có thể xảy ra **giữa hai tiến trình/JVM**, không cần hai thread chia sẻ cùng một trường Java. **AtomicInteger**, **synchronized** trong một JVM không bảo vệ dữ liệu đã được các process khác cùng thao tác.

Giải pháp phải nằm ở **nơi bất biến được quản lý**:

| Ranh giới tranh chấp | Cơ chế thường phù hợp |
| --- | --- |
| Một biến nguyên tử trong cùng JVM | AtomicInteger/AtomicReference CAS |
| Nhiều biến chia sẻ trong cùng JVM | synchronized/Lock hoặc thiết kế trạng thái bất biến |
| Hàng đợi giữa các thread | BlockingQueue và hợp đồng giao tiếp của nó |
| Dữ liệu chung giữa nhiều instance | Transaction, unique constraint, optimistic concurrency/version hoặc cập nhật có điều kiện tại DB |
| Thao tác có side effect lặp do retry | Idempotency key, trạng thái attempt, chống xử lý trùng theo hợp đồng |

Đây là các lựa chọn về **bảo toàn điều kiện đúng đắn**, không phải phép thay thế máy móc lẫn nhau. Ví dụ, ràng buộc duy nhất (*unique constraint*) bảo vệ tính duy nhất ở DB, nhưng không tự bảo đảm một cuộc gọi dịch vụ bên ngoài được thực hiện đúng một lần.

## 10. Điều kiện đúng đắn: hãy viết invariant trước khi chọn khóa

Trước khi sửa một race condition, viết ra điều gì **phải luôn đúng**:

- Bộ đếm nhận đủ hai lần tăng phải cho **2**.
- Nếu kho ban đầu có 1 sản phẩm, **accepted <= 1** và **stock >= 0**.
- Một job chỉ được một worker chuyển từ **PENDING** sang **RUNNING** tại mỗi lượt xử lý.
- Sau khi nhận yêu cầu hủy, một tác vụ không được tự đánh dấu **SUCCEEDED** nếu chính sách hủy đã thắng cuộc cạnh tranh.

Sau đó xác định **điểm tuyến tính hóa (linearization point)**: một điểm logic mà thao tác có thể coi như diễn ra nguyên tử đối với các thread khác.

Trong ví dụ **SafeReservationDemo**, phép **compareAndSet(1, 0)** thành công là điểm xác nhận quyền giữ một sản phẩm. Với một transaction ở database, điểm cấp quyền có thể là lệnh cập nhật có điều kiện **ảnh hưởng đúng một bản ghi** được commit theo giao thức của hệ thống lưu trữ. Điểm tuyến tính hóa không được tùy tiện gán bằng một dòng log hay lời gọi **sleep()**.

Không phải mọi bài toán đều cần linearizability toàn phần; một số phép tính dùng eventual consistency hoặc xử lý chấp nhận lặp. Nhưng **quy tắc chấp nhận sai số và thứ tự nào** phải được đặc tả rõ, không để lịch chạy tình cờ quyết định.

### Phân biệt atomicity, thread safety và business correctness

- **Atomicity của phép đơn:** một incrementAndGet() không bị chia thành các bước nhìn thấy riêng đối với biến AtomicInteger đó.
- **Thread safety của thành phần:** ConcurrentHashMap giữ đúng các bảo đảm của từng operation đã tài liệu hóa.
- **Atomicity của chuỗi nghiệp vụ:** “đọc tồn kho, giữ hàng, ghi đơn, trả xác nhận” cần giao thức nhiều bước riêng.
- **Correctness:** kết quả cuối tuân thủ đặc tả ngay cả khi có cạnh tranh, timeout, retry, hủy hoặc crash (nếu chúng thuộc phạm vi yêu cầu).

Không thể suy ra mục thứ ba và thứ tư chỉ từ hai mục đầu.

## 11. Tại sao sleep(), yield(), log và một lần test không đủ?

Phát sinh lỗi race có thể phụ thuộc một cửa sổ thời gian rất ngắn. Khi thêm **System.out.println(...)**, JIT, I/O và scheduler có thể làm lịch chạy thay đổi. Một lỗi mất đi khi bật logging không chứng minh đã sửa.

Các cách sau **không phải giải pháp đúng**:

~~~java
// Mã minh họa anti-pattern; không phải chương trình độc lập:
if (ready) {
    Thread.sleep(10); // Không làm check-then-act nguyên tử.
    doWork();
}

while (!ready) {
    Thread.yield(); // Không đảm bảo visibility hoặc progress.
}
~~~

Trong ví dụ trên, **ready**, **doWork()** là thành phần giả định; lệnh sleep có checked exception cần xử lý. Nếu ready là plain field được sửa từ thread khác, cả việc quan sát cờ cũng có thể thiếu bảo đảm bộ nhớ.

Để kiểm thử có cơ sở:

1. **Viết invariant** và liệt kê các tình huống đồng thời có thể vi phạm.
2. **Kiểm soát xen kẽ bằng latch/barrier**, ép hai thread cùng đến vị trí nhạy cảm như các ví dụ trong bài. Dùng các công cụ này để tái hiện lỗi, không coi barrier tự sửa tính nguyên tử của thao tác.
3. **Lặp stress test** với nhiều thread và tải khác nhau; ghi lại seed/cấu hình nếu có. Mọi lượt pass vẫn không phải chứng minh chương trình không có race.
4. **Kiểm tra trạng thái cuối** và đếm side effect, thay vì chỉ kiểm tra “không ném exception”.
5. **Rà soát happens-before và critical section**: lock nào bảo vệ trường nào, đường cập nhật nào chưa đi qua lock/CAS, phần check/use có bị tách không?
6. **Xét retry, cancellation và side effect muộn** nếu công việc có nhiều lượt thử hoặc nhiều process. Không để kết quả attempt cũ ghi đè trạng thái attempt mới.

Lập luận tính đúng đắn dựa trên hợp đồng đồng bộ hóa và invariant là yếu tố chính; test là công cụ phát hiện và củng cố, không thay thế lập luận đó.

## 12. Sai lầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Data race và race condition là một | Data race nói về truy cập bộ nhớ thiếu HB; race condition nói về phụ thuộc lịch gây vi phạm yêu cầu |
| Mọi race condition đều có data race | Logic race với toàn thao tác atomic vẫn có thể sai |
| Dùng AtomicInteger thì cả nghiệp vụ an toàn | Mỗi operation atomic không khiến chuỗi check–then–act atomic |
| Một lần chạy ra giá trị đúng nghĩa là không có data race | Có thể chỉ do lịch chạy tình cờ |
| Hai dòng log đảo thứ tự luôn là lỗi race | Chỉ là lỗi nếu thứ tự đó vi phạm đặc tả |
| volatile làm **count++** nguyên tử | volatile không gộp read–modify–write |
| sleep/yield bảo đảm thread khác cập nhật xong | Không cung cấp giao thức đồng bộ hoặc bảo đảm scheduler |
| ConcurrentHashMap làm mọi cặp get/put an toàn như một transaction | Chỉ các thao tác có hợp đồng nguyên tử tương ứng mới có bảo đảm đó |
| synchronized trên từng hàm riêng là đủ | Nếu bất biến trải qua hai hàm, vẫn có khe xen kẽ giữa hai lần khóa |
| AtomicInteger bảo vệ tồn kho được chia sẻ giữa nhiều JVM | AtomicInteger chỉ quản lý biến trong một JVM |
| Test nhiều lần không lỗi tức là không còn race | Lịch chưa gây lỗi có thể chưa xuất hiện; cần chứng minh theo invariant và HB |

## 13. Bài tập suy luận

**Bài 1.** Hai thread cùng tăng một **plain int** 1.000 lần nhưng kết quả lần chạy này đúng 2.000. Có chứng minh không có data race?  
**Đáp án:** Không. Các phép đọc/ghi xung đột vẫn không có đồng bộ hóa phù hợp; lịch chạy tình cờ có thể không làm mất cập nhật. Dùng atomic increment hoặc khóa bảo vệ toàn phép tăng.

**Bài 2.** Hai thread gọi **stock.get() > 0** rồi **stock.decrementAndGet()**, mỗi lời gọi atomic. Tại sao stock vẫn có thể âm?  
**Đáp án:** Điều kiện được kiểm tra trên một snapshot, nhưng không có bảo đảm giữ giá trị cho đến lần trừ. Cần CAS loop hoặc critical section bao quanh cả check và update.

**Bài 3.** Một thread dùng **synchronized** quanh hàm kiểm tra, thread khác dùng synchronized quanh hàm trừ, đều trên cùng lock. Đã đủ ngăn oversell chưa?  
**Đáp án:** Chưa nếu check và trừ ở hai critical section riêng biệt. Thread khác có thể chen vào khoảng giữa. Toàn bộ quyết định phải nằm trong cùng một critical section hoặc thao tác có điều kiện nguyên tử tương đương.

**Bài 4.** Hai worker ghi vào **ConcurrentHashMap** và không có data race trên các operation. Vậy có thể chắc chắn một job chỉ chạy một lần không?  
**Đáp án:** Không. Nếu check job chưa có và thực thi trước bước cấp quyền, hai worker vẫn có thể cùng làm việc. Phải thiết kế cấp quyền nguyên tử và điều kiện xử lý lại/idempotency.

**Bài 5.** Nếu chương trình không dùng shared mutable state mà chỉ nhận hai phản hồi mạng đến theo thứ tự bất định, còn có race condition không?  
**Đáp án:** Có thể, nếu kết quả nghiệp vụ đòi thứ tự hoặc tính duy nhất nhưng code xử lý tùy theo phản hồi đến trước mà không có luật. Nó không nhất thiết là JMM data race.

**Bài 6.** Vì sao cần CountDownLatch trong **LogicRaceDemo**?  
**Đáp án:** Để ép hai thread đi qua bước kiểm tra khi stock vẫn là 1 rồi mới cho phép trừ. Nhờ vậy kết quả oversell tái hiện chắc chắn. Latch không sửa bất biến check–then–act.

**Bài 7.** Một biến **AtomicInteger** cho kết quả đúng sau khi hai worker join. Join có phải thứ đã ngăn lost update không?  
**Đáp án:** Không. **incrementAndGet()/CAS** bảo đảm cập nhật nguyên tử; **join()** chỉ giúp caller đợi các worker kết thúc rồi quan sát kết quả đã hoàn thành.

## 14. Tổng kết

- **Data race**: truy cập xung đột từ nhiều thread trên cùng biến, ít nhất một ghi, thiếu thứ tự happens-before theo JMM.
- **Race condition**: lịch xen kẽ có thể làm kết quả vi phạm một yêu cầu đúng đắn; không nhất thiết có data race.
- **Logic race**: race condition trong cách phối hợp nhiều bước của quy tắc ứng dụng, điển hình là **check–then–act/TOCTOU**.
- **Cách sửa** phải xuất phát từ invariant: xác định dữ liệu và phạm vi quyết định cần nguyên tử, dùng synchronization/CAS/transaction hoặc giao thức trao quyền ở đúng ranh giới.
- **Hãy kiểm chứng lịch xen kẽ và trạng thái cuối**, nhưng đừng dùng sleep, yield hoặc test may mắn để thay thế hợp đồng đồng bộ hóa.
