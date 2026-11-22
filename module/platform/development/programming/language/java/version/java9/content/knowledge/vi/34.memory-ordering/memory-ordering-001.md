# Quan hệ happens-before và vấn đề công bố dữ liệu trong Java

Java Memory Model (JMM) quy định khi nào một thread được bảo đảm nhìn thấy các thay đổi do thread khác thực hiện. Quy tắc trung tâm là quan hệ **happens-before**: nếu hành động A happens-before hành động B, các hiệu ứng của A được bảo đảm hiển thị và có thứ tự đối với B theo JMM.

Một chương trình có thể tạo đối tượng hoàn toàn đúng trong một thread nhưng vẫn gặp lỗi khi đưa tham chiếu của đối tượng đó sang thread khác mà không có cơ chế công bố an toàn. Thread nhận có thể thấy tham chiếu nhưng không được bảo đảm nhìn thấy trạng thái mà thread tạo đã ghi trước đó.

Bài này trình bày quan hệ happens-before, các cạnh đồng bộ hiện hành của Java, data race, safe publication, final field semantics và cách chọn cơ chế đồng bộ phù hợp.

## 1. Visibility, ordering và atomicity

Khi nhiều thread truy cập cùng dữ liệu, cần phân biệt ba vấn đề:

- **Visibility (khả năng nhìn thấy):** một thread có nhìn thấy giá trị mà thread khác đã ghi hay không.
- **Ordering (thứ tự):** các thao tác bộ nhớ được phép quan sát theo thứ tự nào giữa các thread.
- **Atomicity (tính nguyên tử):** một thao tác có được thực hiện như một đơn vị không thể bị xen giữa hay không.

Ví dụ:

~~~java
int count = 0;
count++;
~~~

Phép tăng thực chất gồm đọc, tính toán và ghi. Nếu hai thread cùng thực hiện mà không đồng bộ, một lần tăng có thể bị mất. Chỉ bảo đảm nhìn thấy giá trị mới không tự biến một chuỗi đọc-sửa-ghi thành nguyên tử.

Tương tự, việc một thread ghi xong đối tượng không tự bảo đảm thread khác nhìn thấy mọi field đã khởi tạo. Cần một quan hệ đồng bộ tạo ra ordering và visibility giữa hai phía.

## 2. Happens-before là gì?

Happens-before (HB) là quan hệ thứ tự bộ nhớ được JMM định nghĩa. Nó không đơn giản là đồng hồ của hai thread cho biết hành động nào xảy ra trước theo thời gian thực.

Có hai nền tảng chính:

1. **Program order:** trong cùng một thread, hành động đứng trước trong thứ tự chương trình happens-before hành động đứng sau.
2. **Synchronizes-with:** một số thao tác đồng bộ tạo quan hệ giữa các thread, ví dụ unlock/lock cùng monitor hoặc ghi/đọc cùng biến volatile.

Happens-before là bao đóng bắc cầu của các quan hệ này. Nếu A happens-before B và B happens-before C, thì A happens-before C.

~~~text
Thread 1                         Thread 2
---------                         ---------
ghi payload = 42
      |
      | program order
      v
ghi volatile ready = true
      |
      | synchronizes-with
      v
                                  đọc volatile ready == true
                                            |
                                            | program order
                                            v
                                  đọc payload == 42
~~~

Trong ví dụ trên, việc ghi payload happens-before lần đọc payload. Thread nhận được bảo đảm thấy giá trị đã công bố, dù payload không phải volatile.

HB là bảo đảm về kết quả có thể quan sát theo JMM. Nó không yêu cầu CPU phải thực hiện mọi lệnh vật lý đúng thứ tự mã nguồn; compiler và CPU vẫn được phép tối ưu nếu kết quả quan sát tuân thủ JMM.

## 3. Các cạnh synchronizes-with quan trọng

### Unlock và lock cùng monitor

Một lần mở khóa monitor happens-before mọi lần khóa tiếp theo trên cùng monitor:

~~~java
final class SharedState {
    private int value;

    public synchronized void publish(int newValue) {
        value = newValue;
    }

    public synchronized int read() {
        return value;
    }
}
~~~

Khi thread A rời khỏi synchronized method `publish`, nó nhả monitor. Thread B sau đó vào `read` và lấy cùng monitor. Việc ghi value trong A được bảo đảm hiển thị cho B.

Tất cả thread phải phối hợp trên cùng monitor. Nếu một thread ghi ngoài synchronized còn thread khác chỉ khóa monitor khi đọc, không có cạnh unlock/lock bao phủ lần ghi đó.

### Ghi và đọc cùng biến volatile

Một lần ghi vào biến volatile synchronizes-with các lần đọc tiếp theo của chính biến đó theo synchronization order:

~~~java
private static int payload;
private static volatile boolean ready;

// Thread producer
payload = 42;
ready = true;

// Thread consumer
if (ready) {
    System.out.println(payload);
}
~~~

Nếu consumer đọc được `ready == true`, lần ghi volatile đó tạo cạnh đồng bộ tới lần đọc. Theo program order và tính bắc cầu, lần ghi payload happens-before lần đọc payload.

Cạnh này gắn với cùng biến volatile. Một volatile khác không tự tạo quan hệ tương đương giữa hai thao tác.

### start() và hành động đầu tiên của thread

Mọi hành động trong thread gọi `Thread.start()` trước khi start thành công happens-before hành động đầu tiên trong thread mới:

~~~java
int initialValue = 42;

Thread worker = new Thread(() ->
    System.out.println(initialValue)
);

worker.start();
~~~

Việc khởi tạo initialValue trước `start()` được công bố cho worker theo quy tắc này. Nếu thread cha tiếp tục thay đổi dữ liệu sau khi gọi start, cần một cơ chế đồng bộ khác cho những thay đổi tiếp theo.

### Kết thúc thread và join()

Mọi hành động của một thread happens-before một thread khác phát hiện thread đó đã kết thúc, chẳng hạn bằng cách `join()` trả về thành công:

~~~java
int[] result = new int[1];

Thread worker = new Thread(() -> result[0] = 99);
worker.start();
worker.join();

System.out.println(result[0]); // 99
~~~

Không cần đặt result[0] thành volatile trong ví dụ này: join tạo quan hệ cần thiết giữa việc ghi trong worker và việc đọc sau join.

### Khởi tạo mặc định

Các giá trị mặc định của biến (0, false, null, ...) được công bố trước các hành động khác của chương trình theo quy tắc khởi tạo mặc định của JMM. Điều đó không có nghĩa các lần ghi sau khi khởi tạo mặc định cũng tự động được công bố giữa các thread.

### Interrupt

Lời gọi `interrupt()` trên một thread synchronizes-with thời điểm thread khác xác định rằng nó đã bị interrupt. Quy tắc này hỗ trợ phối hợp trạng thái interrupt; nó không biến interrupt thành cơ chế công bố mọi dữ liệu tùy ý nếu ứng dụng không có quan hệ đồng bộ phù hợp.

### Khởi tạo lớp

Việc khởi tạo một class/interface được đồng bộ bởi JVM. Các hành động trong static initializer được công bố an toàn cho những thread sử dụng lớp sau khi quá trình khởi tạo hoàn tất. Đây là nền tảng của initialization-on-demand holder idiom.

## 4. Data race và chương trình được đồng bộ đúng

Một data race xuất hiện khi hai hành động xung đột truy cập cùng một biến, ít nhất một hành động là ghi, và hai hành động không được sắp thứ tự bởi happens-before.

Ví dụ có data race:

~~~java
final class UnsafeCounter {
    int value;

    void increment() {
        value++;
    }

    int get() {
        return value;
    }
}
~~~

Nếu nhiều thread gọi `increment()` và `get()` đồng thời mà không có lock, volatile, atomic hoặc cơ chế đồng bộ khác, các truy cập xung đột không được sắp thứ tự.

Hậu quả có thể gồm:

- Đọc giá trị cũ hoặc không nhìn thấy cập nhật mong đợi.
- Mất cập nhật do thao tác đọc-sửa-ghi không nguyên tử.
- Quan sát trạng thái một phần khi đối tượng được khởi tạo hoặc thay đổi đồng thời.
- Compiler/CPU áp dụng các tối ưu hợp lệ theo JMM nhưng gây bất ngờ nếu chương trình giả định có ordering không được thiết lập.

Không nên dựa vào việc thử nghiệm thường xuyên cho kết quả đúng. Data race có thể chỉ bộc lộ dưới tải, trên CPU khác hoặc sau một thay đổi tối ưu hóa.

Một chương trình được đồng bộ đúng (correctly synchronized) có thể được hiểu theo mô hình tuần tự nhất quán cho các hành động liên thread. Thiết kế tốt thường loại bỏ data race trên trạng thái mutable được chia sẻ, thay vì cố dự đoán cách một data race sẽ biểu hiện.

## 5. Công bố dữ liệu (safe publication)

Publication là hành động làm cho một thread khác có thể lấy được tham chiếu tới một đối tượng. Safe publication bảo đảm các ghi khởi tạo xảy ra trước khi thread nhận sử dụng đối tượng.

Mục tiêu thường là:

1. Tạo đối tượng và thiết lập trạng thái ban đầu.
2. Thiết lập cạnh happens-before từ thread tạo sang thread nhận.
3. Thread nhận lấy tham chiếu sau cạnh đó và sử dụng trạng thái đã khởi tạo.
4. Nếu đối tượng tiếp tục mutable, đồng bộ mọi lần thay đổi sau publication.

### Công bố qua volatile reference

~~~java
final class Config {
    final int version;
    int limit;

    Config(int version, int limit) {
        this.version = version;
        this.limit = limit;
    }
}

private static volatile Config published;

// Thread producer
published = new Config(9, 100);

// Thread consumer
Config config = published;
if (config != null) {
    System.out.println(config.limit);
}
~~~

Ghi volatile reference xảy ra sau khi constructor hoàn tất. Thread đọc reference qua volatile read sẽ nhìn thấy các ghi khởi tạo trước lần ghi volatile đó.

Không cần biến mọi field trong Config thành volatile. Cạnh publication có thể công bố các ghi thường đã xảy ra trước đó. Nhưng nếu producer tiếp tục sửa `limit` sau publication, lần sửa mới cần được đồng bộ riêng.

### Công bố qua synchronized

~~~java
final class ConfigRegistry {
    private Config config;

    public synchronized void publish(Config value) {
        config = value;
    }

    public synchronized Config get() {
        return config;
    }
}
~~~

Việc ghi và đọc reference dưới cùng monitor tạo quan hệ unlock/lock. Đây là cách phù hợp khi publication là một phần của thao tác cập nhật trạng thái lớn hơn cần bảo vệ bằng lock.

### Công bố qua static initialization

~~~java
final class Defaults {
    static final Config CONFIG = new Config(9, 100);
}
~~~

Khi lớp Defaults được khởi tạo lần đầu, JVM bảo đảm các thread sử dụng lớp sau khi khởi tạo hoàn tất nhìn thấy trạng thái đã thiết lập trong static initializer.

Initialization-on-demand holder:

~~~java
final class ServiceProvider {
    private ServiceProvider() {
    }

    private static class Holder {
        static final Service INSTANCE = new Service();
    }

    static Service getInstance() {
        return Holder.INSTANCE;
    }
}
~~~

Đây là cách lazy initialization an toàn dựa trên cơ chế khởi tạo lớp của JVM; không cần tự viết lock hoặc kiểm tra volatile.

### Công bố qua thread start

Nếu thread cha tạo đối tượng rồi truyền nó cho thread con trước khi gọi `start()`, các ghi trước start được công bố cho thread mới:

~~~java
Config config = new Config(9, 100);
Thread worker = new Thread(() -> use(config));
worker.start();
~~~

Không tiếp tục thay đổi config từ thread cha đồng thời với worker nếu chưa có cơ chế phối hợp.

### Công bố qua thư viện đồng thời

Các API đồng thời của JDK định nghĩa memory consistency effects. Có thể dựa vào hợp đồng của chúng thay vì tự tạo cờ đồng bộ:

| Cơ chế | Bảo đảm phối hợp |
|---|---|
| `BlockingQueue` | Ghi trước khi đưa phần tử vào queue happens-before hành động truy cập hoặc lấy phần tử đó ở thread khác |
| `ConcurrentMap` | Ghi trước khi đặt đối tượng vào map happens-before lần truy cập/loại bỏ tương ứng ở thread khác |
| `ExecutorService` | Hành động trước khi submit task happens-before task bắt đầu; hành động trong task happens-before kết quả được lấy qua Future.get |
| `Future.get()` | Tính toán bất đồng bộ happens-before các hành động sau get trả về ở thread khác |
| `CountDownLatch` | Hành động trước countDown happens-before hành động sau await thành công |
| Atomic variables | Các thao tác có memory effects được quy định như volatile hoặc theo access mode tương ứng |

Dùng đúng abstraction cấp cao thường dễ kiểm tra và bảo trì hơn việc tự xây dựng protocol bằng nhiều cờ.

## 6. Final field semantics

Java có quy tắc đặc biệt cho field `final`. Khi constructor hoàn tất, một freeze action được áp dụng cho final field. Nếu đối tượng được xây dựng đúng và `this` không thoát ra ngoài trước khi constructor hoàn tất, thread khác có thể nhận được bảo đảm mạnh hơn về giá trị final đã thiết lập trong constructor, kể cả khi tham chiếu đối tượng được truyền mà không có safe publication thông thường.

Ví dụ:

~~~java
final class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
~~~

Nếu một thread nhìn thấy tham chiếu tới Point được tạo đúng cách, JMM bảo đảm nó thấy các giá trị final x và y được gán trong constructor. Quy tắc final-field cũng có bảo đảm liên quan tới trạng thái được truy cập thông qua reference final tại thời điểm constructor hoàn tất.

Tuy nhiên, final-field semantics có phạm vi cụ thể:

- Chúng không làm mọi field mutable khác trong đối tượng tự động an toàn.
- Chúng không đồng bộ các thay đổi xảy ra sau constructor.
- Chúng không thay thế safe publication khi đối tượng có trạng thái mutable cần chia sẻ.
- Chúng phụ thuộc việc constructor không để `this` thoát ra ngoài trước khi hoàn tất.

Vì vậy, ưu tiên immutable object với final fields và vẫn công bố qua volatile, lock, queue, executor hoặc một cơ chế đồng bộ rõ ràng.

## 7. Constructor escape: lỗi công bố trước khi khởi tạo xong

Không để `this` thoát ra ngoài constructor. Nếu tham chiếu được chia sẻ trước khi các field được thiết lập đầy đủ, thread khác có thể quan sát đối tượng trong trạng thái chưa hoàn chỉnh và các bảo đảm final-field bị suy yếu.

Ví dụ nguy hiểm:

~~~java
final class Listener {
    private final int id;
    private int state;

    Listener(Registry registry) {
        registry.register(this); // this thoát ra ngoài quá sớm
        id = 10;
        state = 1;
    }
}
~~~

Registry có thể chuyển tham chiếu sang thread khác ngay khi đăng ký. Thread đó có thể gọi callback trước khi constructor gán xong id và state.

Cách an toàn là hoàn tất khởi tạo trước rồi đăng ký:

~~~java
Listener listener = new Listener();
registry.register(listener);
~~~

Nếu cần truyền callback hoặc khởi chạy thread, hãy thực hiện sau khi constructor hoàn tất và sau khi trạng thái cần công bố đã ổn định.

## 8. Double-checked locking và volatile

Double-checked locking chỉ an toàn khi reference singleton được khai báo volatile:

~~~java
final class Singleton {
    private static volatile Singleton instance;

    private Singleton() {
    }

    static Singleton getInstance() {
        Singleton local = instance;
        if (local == null) {
            synchronized (Singleton.class) {
                local = instance;
                if (local == null) {
                    local = new Singleton();
                    instance = local;
                }
            }
        }
        return local;
    }
}
~~~

Ghi volatile công bố đối tượng sau khi constructor hoàn tất. Các thread đọc instance qua volatile có ordering cần thiết để nhìn thấy trạng thái khởi tạo.

Nếu bỏ volatile, chỉ dùng synchronized ở nhánh tạo nhưng đọc instance bên ngoài lock, publication không được bảo đảm theo cách này. Trong nhiều trường hợp, initialization-on-demand holder ở phần trước đơn giản hơn.

## 9. Những cách không tạo happens-before

Một số thao tác thường bị hiểu nhầm là cơ chế đồng bộ:

- `Thread.sleep()` chỉ tạm dừng thread; nó không tự tạo quan hệ happens-before với thread khác.
- `Thread.yield()` chỉ là gợi ý scheduler; nó không công bố dữ liệu.
- Đọc/ghi một field thường nhiều lần không tự tạo ordering liên thread.
- Việc một thread thường hoàn tất trước theo quan sát thời gian không đủ nếu không có cạnh đồng bộ.
- `System.out.println()` không nên được dùng làm protocol publication cho dữ liệu ứng dụng.
- Một volatile flag không bảo vệ mọi dữ liệu nếu thread nhận không đọc flag đó hoặc không dùng đúng biến volatile được chia sẻ.

Nếu cần phối hợp, dùng volatile, cùng monitor, thread start/join, latch, queue, Future hoặc abstraction đồng thời có memory consistency contract.

## 10. Chọn cơ chế publication phù hợp

| Yêu cầu | Cơ chế nên cân nhắc |
|---|---|
| Công bố một trạng thái hoặc reference đơn giản | volatile field hoặc AtomicReference |
| Cập nhật nhiều field như một invariant | synchronized hoặc Lock |
| Chuyển dữ liệu giữa producer và consumer | BlockingQueue hoặc concurrent collection |
| Gửi công việc và lấy kết quả | ExecutorService và Future.get |
| Chờ nhiều bước hoàn tất | CountDownLatch, Phaser hoặc cơ chế đồng bộ phù hợp |
| Đối tượng bất biến, khởi tạo một lần | final fields và safe publication |
| Singleton lazy | Initialization-on-demand holder hoặc volatile double-checked locking |
| Giao thức low-level cần ordering cụ thể | VarHandle với access mode phù hợp |

Đừng chọn volatile chỉ vì muốn "nhanh hơn synchronized". Trước hết hãy xác định invariant dữ liệu, những thread nào đọc/ghi và cạnh happens-before nào bảo vệ từng lần truy cập.

## 11. Ví dụ Java chạy được: công bố an toàn bằng volatile

Chương trình dưới đây tạo Config trong producer thread rồi công bố reference qua biến volatile. Reader chờ reference xuất hiện và đọc cả final field lẫn field thường được gán trong constructor.

~~~java
public class HappensBeforeExample {
    private static volatile Config published;

    private static final class Config {
        final int version;
        int limit;

        Config(int version, int limit) {
            this.version = version;
            this.limit = limit;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread reader = new Thread(() -> {
            Config config;
            while ((config = published) == null) {
                Thread.yield();
            }
            System.out.println("version=" + config.version);
            System.out.println("limit=" + config.limit);
        });

        Thread writer = new Thread(() -> {
            Config config = new Config(9, 100);
            published = config;
        });

        reader.start();
        writer.start();

        writer.join();
        reader.join();

        System.out.println("published=" + (published != null));
    }
}
~~~

Lưu trong tệp `HappensBeforeExample.java`, biên dịch và chạy với Java 9 trở lên:

~~~shell
javac --release 9 -Xlint:all HappensBeforeExample.java
java HappensBeforeExample
~~~

Kết quả stdout chính xác:

~~~text
version=9
limit=100
published=true
~~~

Giải thích:

1. Producer tạo Config và ghi version, limit trong constructor.
2. Sau constructor, producer ghi reference vào biến volatile published.
3. Reader liên tục đọc published. Khi đọc được reference khác null, volatile write và volatile read tạo quan hệ synchronizes-with.
4. Các ghi trong constructor xảy ra trước volatile write theo program order; nhờ tính bắc cầu, chúng happens-before các lần đọc field trong reader.
5. `Thread.yield()` không phải cơ chế đồng bộ trong ví dụ. Cơ chế publication là volatile read/write.
6. `join()` cho thread main biết writer và reader đã kết thúc trước khi main tiếp tục.

Ví dụ không phụ thuộc vào việc reader chạy trước hay sau writer. Nếu writer chạy trước, reader đọc ngay reference đã công bố; nếu reader chạy trước, nó tiếp tục đọc volatile cho tới khi thấy reference.

## 12. Lỗi thường gặp

- **Nghĩ rằng thứ tự thời gian thực tự tạo visibility:** cần cạnh happens-before theo JMM.
- **Nghĩ volatile làm mọi thao tác compound nguyên tử:** `count++` vẫn là đọc-sửa-ghi; dùng atomic hoặc lock khi cần.
- **Dùng hai biến volatile khác nhau để công bố mà không có quan hệ:** cạnh volatile gắn với biến được ghi/đọc tương ứng.
- **Khóa khi đọc nhưng không khóa khi ghi:** hai phía phải phối hợp trên cùng monitor hoặc lock.
- **Dùng sleep để đợi thread kia ghi xong:** sleep không tạo happens-before.
- **Công bố this trong constructor:** listener hoặc thread khác có thể nhìn thấy trạng thái chưa hoàn chỉnh.
- **Cho rằng final thay thế mọi đồng bộ:** final-field semantics không bảo vệ các lần mutation sau constructor.
- **Công bố volatile reference rồi sửa object không đồng bộ:** volatile chỉ công bố trạng thái trước lần ghi reference; các thay đổi sau cần cơ chế riêng.
- **Dùng plain shared flag để chờ:** thread có thể không quan sát cập nhật; dùng volatile, lock hoặc primitive đồng bộ.
- **Tự xây protocol bằng nhiều cờ khi có abstraction JDK:** BlockingQueue, Future, CountDownLatch và executor đã có memory consistency contract.
- **Cho rằng mọi field phải là volatile để đọc an toàn:** một cạnh publication có thể công bố nhiều field thường được ghi trước đó; chỉ những thay đổi mutable tiếp theo mới cần phối hợp riêng.

## 13. Tài liệu tham khảo chính thức

- [Java Language Specification — Chapter 17: Threads and Locks](https://docs.oracle.com/javase/specs/jls/se26/html/jls-17.html): memory model, program order, synchronizes-with, happens-before, data race và final-field semantics.
- [JLS §12.4.2: Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html#jls-12.4.2): đồng bộ và công bố kết quả khởi tạo lớp.
- [java.util.concurrent package — Memory Consistency Properties](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/package-summary.html): memory consistency effects của executor, queue, synchronizers và concurrent collections.
- [Future — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html): quan hệ happens-before của tính toán bất đồng bộ và Future.get.