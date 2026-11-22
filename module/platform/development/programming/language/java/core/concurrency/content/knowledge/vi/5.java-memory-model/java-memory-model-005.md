# Quy tắc write/read của `volatile` trong Java Memory Model

## 1. Mục tiêu và phạm vi

Trong Java concurrency, một thread có thể ghi vào biến chung trong khi thread khác đọc. Nếu thiếu cơ chế đồng bộ, việc một thread **đã thực hiện phép gán** không tự bảo đảm thread kia sẽ quan sát đúng giá trị đó hoặc các thay đổi dữ liệu liên quan. Từ khóa `volatile` cung cấp những quy tắc đặc biệt cho thao tác **ghi (write)** và **đọc (read)** một trường: bảo đảm visibility, tham gia vào synchronization order và tạo quan hệ **happens-before**.

Sau bài này, bạn có thể:
- Phát biểu chính xác quy tắc `volatile write` **synchronizes-with** những `volatile read` tiếp theo trên **cùng một biến**, theo synchronization order.
- Giải thích bằng chuỗi happens-before vì sao các ghi thông thường **trước** khi publish một cờ `volatile` có thể được nhìn thấy sau khi thread khác đọc cờ.
- Phân biệt volatile visibility/ordering với atomicity và mutual exclusion; nhận diện vì sao `volatile count++` hoặc “kiểm tra rồi cập nhật” vẫn sai.
- Sử dụng `volatile boolean` cho cờ thông báo một lần, `volatile` reference để publish một immutable snapshot, và biết khi nào phải dùng `synchronized`, atomic API hoặc công cụ phối hợp thread.
- Đọc được ví dụ Java 17+ chạy độc lập, biết điều kiện để output đúng và các giới hạn về liveness, CPU và cập nhật đồng thời.

Phạm vi chỉ gồm **Java SE, Java Memory Model (JMM) và thư viện JDK**. Các diễn giải và ví dụ dưới đây không phụ thuộc framework.

## 2. Phát biểu quy tắc chính thức

Theo Java Language Specification, §17.4.4–§17.4.5:

> Một thao tác **ghi vào biến `volatile v`** *synchronizes-with* mọi thao tác **đọc `v` tiếp theo**, trong đó “tiếp theo” được xác định theo **synchronization order**.

Từ quy tắc đó, có hệ quả: volatile write **happens-before** các volatile read tiếp theo trên cùng biến. `synchronizes-with` là một trong các quan hệ tạo thành `happens-before`; `happens-before` còn bao gồm **program order** trong mỗi thread và tính **bắc cầu**.

Điều kiện cần đọc chính xác:
1. Phải là truy cập **volatile** và cùng một **field/biến `v`**. Hai biến khác nhau không tự có một `synchronizes-with` edge trực tiếp giữa chúng.
2. “Sau” được xét trong **synchronization order** của mô hình bộ nhớ, không đơn thuần dựa vào một đồng hồ tường hoặc timestamp từ log.
3. Một volatile read quan sát giá trị theo các quy tắc hợp lệ của JMM; không cần và không nên mô tả nó như lệnh “đọc trực tiếp RAM”.
4. Một thread có thể vẫn chưa thực hiện volatile read, chưa được scheduler chạy hoặc đang bị chặn vì lý do khác. Quy tắc **visibility/ordering không bảo đảm thời gian hoàn tất** hay đánh thức thread.
5. Nếu sau khi publish, dữ liệu thông thường tiếp tục bị thay đổi đồng thời mà không có giao thức bảo vệ mới, lần read volatile trước đó **không tự biến mọi truy cập dữ liệu tương lai thành an toàn**.

Có thể dùng cách nói “**volatile write tương tự release; volatile read tương tự acquire**” để nhớ hướng truyền thông tin giữa threads. Tuy nhiên đây là cách giải thích thực hành, còn hợp đồng chính xác của Java vẫn là các quy tắc synchronization order và happens-before của JMM.

## 3. Vì sao thread khác thấy được dữ liệu thông thường trước volatile write?

Giả sử có các trường dùng chung:

~~~java
int payload;               // không volatile
volatile boolean ready;    // cờ đồng bộ
~~~

Thread producer:

~~~java
payload = 42; // A: normal write
ready = true; // B: volatile write
~~~

Thread consumer:

~~~java
if (ready) {             // C: volatile read quan sát true
    int answer = payload; // D: normal read
}
~~~

Giả sử **producer là bên duy nhất ghi `payload`**, giá trị `ready` bắt đầu `false`, producer gán `payload` trước khi publish `ready=true`, và không có ghi cạnh tranh vào `payload` sau đó. Nếu consumer đi vào nhánh `if (ready)` nhờ đọc giá trị `true` từ bản publish này thì **`answer` phải là 42**. Điều này không đòi hỏi `payload` cũng phải khai báo volatile.

Chuỗi quan hệ:

~~~text
Producer:   A: payload = 42
                     |
               program order
                     v
            B: ready = true     (volatile WRITE)
                     |
               synchronizes-with
                     v
Consumer:   C: read ready=true  (volatile READ)
                     |
               program order
                     v
            D: read payload
~~~

Kết hợp:
- `A happens-before B` vì cùng producer và A đứng trước B theo program order.
- `B synchronizes-with C` vì C là một volatile read phù hợp trên chính biến `ready`, sau B trong synchronization order.
- `C happens-before D` vì cùng consumer và C đứng trước D theo program order.
- Do tính bắc cầu, **`A happens-before D`**.

Đây chính là **mẫu publication bằng volatile flag**: ghi dữ liệu trước, rồi **publish** thông qua volatile write; bên nhận **đọc cờ trước**, rồi mới đọc dữ liệu. Đặt thứ tự ngược lại sẽ thay đổi hoàn toàn lập luận.

## 4. Ví dụ độc lập Java 17+: publication một lần

Lưu tệp **VolatileWriteReadDemo.java**:

~~~java
public class VolatileWriteReadDemo {
    private static int payload;
    private static volatile boolean ready;

    public static void main(String[] args) throws InterruptedException {
        Thread consumer = new Thread(() -> {
            while (!ready) {
                Thread.onSpinWait();
            }
            System.out.println("payload=" + payload);
        }, "consumer");

        Thread producer = new Thread(() -> {
            payload = 42;
            ready = true;
        }, "producer");

        consumer.start();
        producer.start();

        producer.join();
        consumer.join();
        System.out.println("completed=true");
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac VolatileWriteReadDemo.java
java VolatileWriteReadDemo
~~~

Kết quả khi các threads được scheduler chạy bình thường và không có sự can thiệp khác:

~~~text
payload=42
completed=true
~~~

**Vì sao có thể tin kết quả?**
- Biến tĩnh `ready` được khởi tạo mặc định là `false` và `payload` là 0; producer duy nhất ghi `payload=42`, sau đó volatile write `ready=true`.
- Consumer chỉ đi qua vòng chờ khi volatile read quan sát `true`. Read đó thiết lập quan hệ synchronization cần thiết với lần publish.
- Sau khi read `ready=true`, các hành động trước khi producer publish (trong đó có `payload=42`) happens-before phép đọc payload của consumer.
- `join()` ở main đợi worker kết thúc, giúp main chỉ in `completed=true` sau khi tất cả công việc hoàn tất. **Join không phải lý do payload có giá trị 42 trong consumer**; lý do là volatile publication.
- `Thread.onSpinWait()` chỉ là gợi ý tối ưu cho vòng đợi ngắn, **không tự tạo happens-before**; volatile read trong điều kiện while mới là điểm quan trọng.

**Cảnh báo thực hành:** Vòng `while (!ready)` là **busy-wait**, có thể dùng CPU và không có timeout hoặc hủy. Chỉ dùng để minh họa ngữ nghĩa bộ nhớ hoặc đợi cực ngắn khi có cân nhắc. Nếu cần thread ngủ/được đánh thức, dùng `CountDownLatch`, `BlockingQueue`, `Condition`, `Future` hoặc cơ chế chặn phù hợp. Volatile không thay thế các cơ chế này.

## 5. Volatile write và volatile read bảo đảm những gì?

| Khía cạnh | Ý nghĩa chính xác | Không nên hiểu thành |
|---|---|---|
| **Visibility** | Các ghi thích hợp trước volatile write được sắp xếp happens-before các truy cập sau volatile read tương ứng. | Mọi thread luôn thấy trạng thái mới ngay tức khắc, dù không thực hiện read. |
| **Ordering** | JMM không cho phép các reorder tạo hành vi vi phạm happens-before đã thiết lập. | Máy luôn phát lệnh theo đúng thứ tự nguồn hoặc không bao giờ tối ưu. |
| **Atomicity của truy cập volatile** | Một lần đọc/ghi volatile của field là thao tác nguyên tử theo quy định JMM, kể cả `volatile long` và `volatile double`. | Biểu thức gồm nhiều lần đọc/tính/ghi như `count++` cũng atomic. |
| **Synchronization** | Volatile accesses là synchronization actions; write-read trên cùng field có quan hệ synchronizes-with. | Volatile lock được tài nguyên, đảm bảo mutual exclusion hoặc fairness. |
| **Happens-before** | Program order + synchronizes-with + bắc cầu cho phép chứng minh thứ tự quan sát. | Cùng lệnh gọi, cùng tên field hoặc hai timestamp gần nhau tự tạo happens-before. |
| **Liveness** | Volatile không ngăn compiler giữ mãi một bản cũ của flag trong ví dụ có truy cập volatile đúng cách. | Thread chắc chắn sẽ có CPU, được đánh thức, hay nhận kết quả trong N ms. |

### 5.1. Volatile read nào “thấy” giá trị nào?

Các volatile reads/writes nằm trong một **synchronization order** nhất quán với program order của mỗi thread. Một volatile read phải tuân theo các quy tắc của đồng bộ hóa đối với những volatile writes của **chính field đó**. Nếu có nhiều writer viết `true`, `false` hoặc giá trị số khác nhau, consumer có thể gặp các trạng thái khác nhau tùy interleaving hợp lệ. Không có bảo đảm mọi lần gán được biến thành một “sự kiện” mà mọi consumer phải nhận đủ.

Ví dụ `ready=true` rồi `ready=false` rất nhanh có thể khiến một consumer chưa được chạy **không bao giờ quan sát thấy true**, dù cả hai phép gán đều volatile. Đây là lý do một cờ volatile không phù hợp để biểu diễn **hàng đợi các sự kiện** hoặc đếm số thông báo.

### 5.2. Visibility không có nghĩa “flush nguyên cache về RAM”

Đôi khi volatile được mô tả sơ lược là “writer flush cache, reader đọc main memory”. Cách nói này thiếu chính xác và dễ khiến bạn suy diễn sai trên các CPU/JVM. JMM là **hợp đồng hành vi quan sát được**; JVM/JIT/CPU có quyền chọn instruction và memory barrier phù hợp trên từng kiến trúc, miễn giữ hợp đồng đó. Khi giải thích code, hãy lập luận bằng `happens-before`, không dựa vào một mô hình cache cố định.

### 5.3. Một lần đọc/ghi long và double

JLS cho phép một số thao tác đọc/ghi **non-volatile long/double** bị xử lý theo hai nửa 32 bit trong những triển khai nhất định; đánh dấu `volatile` loại bỏ nguy cơ đọc/ghi “rách” (tearing) đối với **một lần truy cập**. Tuy vậy `volatile long counter; counter++;` vẫn là compound operation gồm read–modify–write, và **có thể lost update** khi có nhiều writer.

## 6. Sai thứ tự publication: đặt ready trước dữ liệu

Xét mã lỗi:

~~~java
// PRODUCER — SAI thứ tự publish:
ready = true;  // volatile WRITE
payload = 42;  // normal WRITE thực hiện sau
~~~

Consumer vẫn:

~~~java
if (ready) {
    System.out.println(payload);
}
~~~

Consumer có thể đọc `ready=true` rồi đọc `payload=0`, vì producer chưa chắc đã gán 42. Không thể áp dụng lập luận “mọi ghi trước volatile write” cho một thao tác **xảy ra sau** volatile write.

~~~text
Producer: ready=true ─────────────► payload=42
              │
              └─ Consumer quan sát ready=true
                                  └─ có thể đọc payload=0
~~~

Chỉ sửa khai báo `payload` thành volatile **không làm thứ tự nghiệp vụ đúng lên**: vẫn có thể đọc trước khi producer ghi 42. Hãy sắp xếp khởi tạo dữ liệu hoàn tất rồi mới publish một tín hiệu được định nghĩa rõ, hoặc dùng một immutable snapshot được publish nguyên tử.

## 7. Safe publication bằng volatile reference

Thay vì dùng nhiều trường mutable cùng cờ, một thiết kế thường rõ ràng hơn là tạo **object không thay đổi**, rồi công bố **tham chiếu volatile** tới object đó.

Ví dụ:

~~~java
public final class ConfigStore {
    public record Config(String endpoint, int retries) {}

    private volatile Config current = new Config("primary", 2);

    public void update(String endpoint, int retries) {
        Config next = new Config(endpoint, retries);
        current = next; // volatile WRITE: publish snapshot mới
    }

    public Config snapshot() {
        return current; // volatile READ: lấy cùng một snapshot
    }
}
~~~

Đây là class Java 17+ độc lập nhưng chưa có `main`; có thể đưa vào dự án và sử dụng như một component lưu cấu hình. Bản thân record giữ hai thành phần `String` và `int`; `String` bất biến. Bên đọc phải **đọc tham chiếu một lần** rồi sử dụng object đó:

~~~java
ConfigStore.Config c = store.snapshot();
use(c.endpoint(), c.retries());
~~~

Đây là đoạn mã minh họa nằm trong một method nơi `store` và `use(...)` đã được khai báo.

Lợi ích:
- Mỗi snapshot chứa các thuộc tính đã được xác lập trước khi `current` được cập nhật.
- Volatile write của reference publish các thay đổi trước đó; volatile read lấy reference và nhận được dữ liệu đã khởi tạo an toàn.
- Reader có thể sử dụng các trường của **cùng snapshot**, tránh đọc `endpoint` của phiên bản A và `retries` của phiên bản B do đọc nhiều field riêng lẻ.

**Ranh giới của lời hứa:** `volatile Config current` chỉ làm reference được đọc/ghi với volatile semantics. Nó **không** khiến nội dung mọi object mutable mà reference trỏ tới trở thành bất biến hay tự động thread-safe. Nếu object chứa `List` mutable và thread khác tiếp tục sửa list không đồng bộ, vẫn có nguy cơ data race. Dùng immutable/deeply immutable state hoặc giao thức đồng bộ cho mutation tiếp theo.

### 7.1. Cẩn thận khi đọc hai lần

~~~java
String endpoint = store.snapshot().endpoint();
int retries = store.snapshot().retries();
~~~

Nếu writer publish snapshot mới giữa hai lần gọi `snapshot()`, hai giá trị có thể đến từ **hai phiên bản khác nhau**. Từng phép đọc volatile đều đúng, nhưng nhóm hai lần đọc không phải một transaction. Muốn các trường nhất quán, đọc **một tham chiếu một lần**, giữ local variable và dùng tất cả thuộc tính từ cùng object.

## 8. Volatile không bảo vệ count++ hoặc check-then-act

Ví dụ sai:

~~~java
class BrokenCounter {
    volatile int count = 0;

    void increment() {
        count++; // vẫn có thể lost update
    }
}
~~~

Hai thread có thể:
1. Cùng volatile read `count = 5`.
2. Cùng tính `5 + 1 = 6`.
3. Cùng volatile write `count = 6`.

Kết quả là 6 thay vì 7. Mỗi đọc/ghi riêng có volatile semantics; **toàn bộ phép tăng** vẫn không atomic. Volatile không nắm lock và không ngăn một thread khác đi vào phần tính toán.

Nếu cần một counter nguyên tử:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class SafeCounter {
    private final AtomicInteger count = new AtomicInteger();

    void increment() {
        count.incrementAndGet();
    }

    int get() {
        return count.get();
    }
}
~~~

Một biến chỉ để quan sát “công việc đã kết thúc chưa” có thể dùng `volatile boolean done`; một biến “đã xử lý được bao nhiêu yêu cầu” cần `AtomicInteger`, `AtomicLong`, `LongAdder` (với điều kiện đọc phù hợp) hoặc lock tùy mô hình cập nhật.

### 8.1. Check-then-act trên volatile cũng không atomic

~~~java
volatile int tickets = 1;

// Hai thread cùng chạy:
if (tickets > 0) {
    tickets--; // có thể cả hai đều tin rằng mình mua được vé
}
~~~

Ngay cả khi phép `tickets--` tình cờ chỉ giảm một đơn vị tổng cộng do lost update, **hai luồng đều có thể đi vào nhánh**. Việc cần bảo vệ ở đây là **cả kiểm tra điều kiện lẫn thay đổi trạng thái**, không chỉ phép giảm. Có thể dùng một monitor/lock chung hoặc CAS loop trên `AtomicInteger`.

### 8.2. Volatile array khác với volatile elements

~~~java
volatile int[] numbers = {0};

// Thao tác này cập nhật phần tử mảng bình thường:
numbers[0]++;
~~~

Khai báo `volatile int[] numbers` chỉ đặt volatile semantics lên **trường tham chiếu `numbers`**, không khiến mọi truy cập tới `numbers[i]` là volatile hay atomic. Mọi truy cập phần tử cạnh tranh vẫn cần giao thức an toàn. Có thể chọn `AtomicIntegerArray`, lock hoặc immutable array snapshot tùy trường hợp.

Cũng tương tự, `volatile Map<K,V>` không làm các thao tác trên một mutable Map trở nên thread-safe.

## 9. Một volatile flag không phải message queue

Đối với một thay đổi trạng thái duy nhất (từ `false` sang `true`), volatile flag có thể biểu thị “đã sẵn sàng”. Nhưng khi cần gửi nhiều thông báo liên tiếp:

~~~java
volatile boolean changed;

// Producer:
changed = true;
changed = false;
changed = true;
~~~

Consumer đọc không nhất thiết phải quan sát đủ hai lần `true`. Tương tự, `volatile int eventId` có thể bị “nhảy số” khi writer cập nhật nhanh hơn reader xử lý. Volatile giúp nhìn thấy trạng thái phù hợp với ordering, **không lưu mọi chuyển đổi** và không xác nhận mỗi event đã được xử lý.

Nếu yêu cầu nhận đúng từng sự kiện, dùng `BlockingQueue`, `Channel` phù hợp (nếu có thư viện), semaphore đếm hoặc message/queue abstraction có hợp đồng giữ thông báo. Nếu chỉ cần báo hiệu hoàn thành một lần, `CountDownLatch` hoặc `CompletableFuture` thường tránh busy-wait và truyền kết quả/lỗi rõ ràng hơn.

## 10. Quy tắc write/read khi có nhiều volatile fields

Không nên khẳng định “write `volatile a` synchronizes-with read `volatile b`” nếu `a` và `b` là **hai field khác nhau**. Tuy nhiên, thông qua **program order** và các cạnh happens-before khác, volatile field có thể đóng vai trò *cầu nối* để thấy các thao tác trên những field thông thường khác.

Ví dụ:

~~~java
int x;
int y;
volatile boolean published;

// Producer:
x = 10;
y = 20;
published = true;

// Consumer:
if (published) {
    int a = x;
    int b = y;
}
~~~

Khi consumer đã đọc bản publish `true` và không có writer cạnh tranh khác, các ghi `x=10`, `y=20` happens-before các đọc tương ứng. Chúng **không phải volatile** vẫn được bảo vệ theo đường truyền của happens-before.

Ngược lại, ví dụ có hai trường volatile độc lập `volatile boolean a` và `volatile boolean b` không tự tạo “giao dịch” cập nhật hai biến như một cặp. Nếu bất biến yêu cầu `a` và `b` luôn thuộc cùng phiên bản, hãy publish một object chứa cả hai hoặc đồng bộ trên lock chung.

### Không giả định đọc volatile thấy mọi “giá trị mới nhất” của các field khác

Sau khi consumer đọc `published=true`, các write sau thời điểm producer publish (ví dụ writer tiếp tục sửa `x`) không được bảo vệ bởi lần volatile read đó. Nếu nhiều writer cập nhật `x` và `y`, việc thiếu giao thức đồng bộ trên các cập nhật tiếp theo vẫn có thể tạo data race hoặc trạng thái kết hợp sai. Một chiều publication một lần khác với stream cập nhật liên tục.

## 11. Volatile và vòng lặp chờ

Một ứng dụng đôi khi có worker chạy tới khi nhận lệnh dừng:

~~~java
class Worker implements Runnable {
    private volatile boolean stopRequested;

    public void requestStop() {
        stopRequested = true;
    }

    @Override
    public void run() {
        while (!stopRequested) {
            doOneUnitOfWork();
        }
    }

    private void doOneUnitOfWork() {
        // Một đơn vị công việc hữu hạn, tôn trọng lifecycle.
    }
}
~~~

Đây là class minh họa, **không phải chương trình độc lập có main**. Nếu `doOneUnitOfWork()` luôn kết thúc hữu hạn và vòng lặp tiếp tục đọc flag volatile, worker có thể quan sát yêu cầu dừng theo các quy tắc visibility. Nhưng `volatile` **không thể cưỡng bức** một lệnh blocking I/O hoặc wait vô thời hạn hoàn tất, cũng không bảo đảm scheduler cấp CPU trong khoảng thời gian xác định.

Đối với worker đang chờ trên API có thể interrupt:
- Kết hợp trạng thái dừng với `Thread.interrupt()`, timeout hoặc cơ chế hủy được API hỗ trợ.
- Bắt `InterruptedException` đúng hợp đồng: thường thoát hoặc khôi phục interrupt flag qua `Thread.currentThread().interrupt()` khi không ném tiếp.
- Khi shutdown, chờ `join()`, `Future.get()` hoặc đóng executor có kiểm soát để biết công việc thật sự kết thúc.

Không dùng `Thread.sleep()` hay `Thread.yield()` để thay thế quan hệ happens-before; chúng không cung cấp sự đồng bộ cần thiết cho một trường không volatile.

## 12. Trường hợp kinh điển: double-checked locking cần volatile

Một ví dụ sử dụng **safe publication** khác là lazy initialization, khi nhiều thread cần truy cập cùng một instance:

~~~java
public final class LazyService {
    private static volatile LazyService instance;

    private final String label;

    private LazyService() {
        label = "ready";
    }

    public static LazyService getInstance() {
        LazyService result = instance;
        if (result == null) {
            synchronized (LazyService.class) {
                result = instance;
                if (result == null) {
                    result = new LazyService();
                    instance = result;
                }
            }
        }
        return result;
    }

    public String label() {
        return label;
    }
}
~~~

**Phân tích:**
- `instance` là volatile reference; xây dựng object hoàn chỉnh trước lần publish vào trường volatile.
- Đường vào đầu tiên đọc volatile vào biến local. Nếu khác null, caller có thể dùng instance đã được publish an toàn mà không cần lock.
- Nếu null, khóa trên `LazyService.class` chỉ cho một thread vào vùng khởi tạo tại một thời điểm. Kiểm tra lần thứ hai **bên trong lock** ngăn thread đến sau tạo lại instance.
- Sau lần publish, các lần đọc instance non-null phù hợp nhận được các ghi trước volatile write. Constructor ở đây không làm `this` thoát ra nơi khác trước khi xây dựng xong.
- Cấu hình này an toàn theo JMM hiện đại; code phức tạp hơn nhiều so với các lựa chọn đơn giản như **initialization-on-demand holder idiom** hoặc eager singleton. Không chọn double-checked locking chỉ để “thể hiện volatile” nếu không có nhu cầu lazy initialization và fast path thật.

**Lưu ý:** Nếu class này có trạng thái mutable về sau, volatile reference không làm các thao tác trên trạng thái đó tự thread-safe. Cần một hợp đồng concurrency riêng cho trạng thái thay đổi sau khởi tạo.

## 13. Ví dụ biên dịch thứ hai: đọc một snapshot được publish

Chương trình này tạo snapshot bất biến trước khi volatile write và đọc nó sau volatile read. Nó minh họa trường tham chiếu volatile, không yêu cầu mọi field bên trong cũng volatile.

Lưu tệp **VolatileSnapshotDemo.java**:

~~~java
public class VolatileSnapshotDemo {
    record Snapshot(String status, int code) {}

    private static volatile Snapshot latest;

    public static void main(String[] args) throws InterruptedException {
        Thread consumer = new Thread(() -> {
            Snapshot observed;
            do {
                observed = latest; // volatile read
                if (observed == null) {
                    Thread.onSpinWait();
                }
            } while (observed == null);

            System.out.println("status=" + observed.status());
            System.out.println("code=" + observed.code());
        }, "consumer");

        Thread producer = new Thread(() -> {
            Snapshot prepared = new Snapshot("READY", 200);
            latest = prepared; // volatile write
        }, "producer");

        consumer.start();
        producer.start();
        producer.join();
        consumer.join();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac VolatileSnapshotDemo.java
java VolatileSnapshotDemo
~~~

Output xác định với các thread được chạy bình thường:

~~~text
status=READY
code=200
~~~

Mỗi vòng chỉ đọc `latest` một lần vào biến local. Sau khi nhận được tham chiếu non-null, consumer chỉ đọc cùng một snapshot. Việc producer tạo `Snapshot` trước khi publish và consumer đọc `latest` sau khi publish thiết lập happens-before cho quá trình khởi tạo. Cả hai ví dụ runnable dùng spin để làm rõ nguyên lý và **không nên copy nguyên vòng chờ vào production** khi thời gian đợi có thể dài.

## 14. Phân biệt volatile, synchronized và atomic classes

| Nhu cầu | Giải pháp thường phù hợp | Tại sao |
|---|---|---|
| Flag trạng thái được một thread publish, nhiều thread đọc | `volatile boolean` | Read/write và visibility/ordering đủ cho trạng thái đơn giản. |
| Publish một snapshot bất biến hoàn chỉnh | `volatile Snapshot` | Có điểm cập nhật tham chiếu nguyên tử, thấy khởi tạo trước publish. |
| Nhiều writer cùng tăng biến đếm chính xác | `AtomicInteger.incrementAndGet()` hoặc lock | Cần atomic **read–modify–write**; volatile count++ không đủ. |
| Check-then-act và nhiều trường phải tuân theo bất biến | `synchronized`, `Lock` hoặc CAS phù hợp | Cần bảo vệ cả chuỗi hành động logic. |
| Đợi một sự kiện không dùng CPU polling | `CountDownLatch`, `Future`, `BlockingQueue`, `Condition` | Có cơ chế chặn, đánh thức/đợi và thường có cách xử lý lỗi/hủy. |
| Tổng metric có nhiều writer, đọc tổng quan sát | `LongAdder` | Tối ưu contention nhưng `sum()` không phải snapshot nguyên tử khi còn writer. |

Không nên coi `volatile` là “khóa nhẹ”. Một lock cung cấp **mutual exclusion** để cô lập critical section; volatile không bảo vệ chuỗi nhiều hành động khỏi interleaving. Trái lại, khi chỉ cần publish flag/snapshot đúng nghĩa, đưa mọi thứ vào synchronized có thể tăng mức phối hợp không cần thiết. Chọn công cụ theo bất biến và hành vi cần bảo đảm, sau đó đo trong workload thật nếu hiệu năng quan trọng.

## 15. Các lỗi thường gặp khi review code

**Lỗi A — Chỉ publisher dùng volatile nhưng consumer đọc từ đường khác.** Các lời đọc phải truy cập đúng field volatile hoặc dùng một cơ chế đồng bộ tương thích. Một cờ khác cùng tên hoặc bản copy trong biến không volatile không tạo cạnh synchronizes-with mong muốn.

**Lỗi B — Ghi flag trước payload.** Consumer có thể thấy cờ đã bật khi payload còn chưa được ghi. Publish dữ liệu trước, flag sau, và không sửa payload thiếu đồng bộ sau publish.

**Lỗi C — Đặt volatile trên reference rồi sửa object mutable không kiểm soát.** Volatile reference không biến các phần tử `ArrayList`, `HashMap` hoặc field trong object thành atomic/thread-safe.

**Lỗi D — Dùng `volatile count++`.** Bảo đảm đọc/ghi riêng lẻ không kéo theo atomic compound update. Dùng atomic increment hoặc lock.

**Lỗi E — Dùng `volatile` làm notification queue.** Cờ có thể bị ghi đè, và reader có thể bỏ lỡ các chuyển đổi nhanh. Dùng queue hoặc cơ chế đếm/đồng bộ có hợp đồng lưu event khi cần.

**Lỗi F — Đồng nhất happens-before với thời gian thật.** Một volatile write không làm thread khác được scheduler chạy ngay, và một thread không đọc cờ thì không thể nhận tín hiệu chỉ vì biến đã đổi.

**Lỗi G — Cho rằng volatile read đảm bảo mọi dữ liệu mãi nhất quán.** Publication đưa các ghi *trước* tín hiệu tới bên đọc. Những cập nhật *sau* tín hiệu vẫn cần một protocol riêng hoặc snapshot mới.

**Lỗi H — Đọc snapshot nhiều lần và trộn phiên bản.** Với state có nhiều trường, giữ một tham chiếu snapshot local rồi đọc đủ trường từ đó.

**Lỗi I — Dùng sleep để “đợi volatile có hiệu lực”.** `sleep()` không tạo synchronization action cho những biến thông thường; nó chỉ làm thay đổi lịch chạy và không sửa data race.

**Lỗi J — Dựa vào một bài stress test để chứng minh không có lỗi.** JIT, runtime, OS và interleaving đa dạng; không xuất hiện sai số trong một lần chạy không biến code thành đúng theo JMM.

## 16. Cách tự chứng minh một đoạn mã dùng volatile có đúng

Với mỗi trường hợp, ghi rõ bốn mốc:

1. **W(data):** writer tạo và ghi dữ liệu gì?
2. **W(v):** writer có ghi vào **chính volatile field v** sau dữ liệu hay không?
3. **R(v):** reader có thực hiện volatile read từ cùng field và quan sát trạng thái publish phù hợp không?
4. **R(data):** reader chỉ đọc dữ liệu sau R(v), và có writer nào tiếp tục sửa dữ liệu không được đồng bộ không?

Nếu xác lập được `W(data) →program-order W(v) →synchronizes-with R(v) →program-order R(data)` thì kết luận `W(data) happens-before R(data)` là hợp lý. Nếu một mũi tên thiếu, hãy tìm một cơ chế đồng bộ khác **thực sự tồn tại**, đừng tự suy đoán dựa trên thời gian.

### Bài tập nhanh

**Câu 1.** Producer viết `data=10`, rồi `ready=true` (ready volatile). Consumer đọc ready là true rồi đọc data; không có writer nào khác. Data có thể là 0 không?

**Đáp án:** Không, trong điều kiện đã mô tả và quan hệ read/write phù hợp. Ghi data happens-before lần đọc data sau read ready.

**Câu 2.** Đảo thứ tự producer thành `ready=true`; `data=10`. Consumer vẫn đọc ready rồi data. Có thể gặp 0 không?

**Đáp án:** Có. Ghi data xảy ra sau volatile write nên không được bảo đảm bởi lần read flag đó.

**Câu 3.** `volatile int n`; hai thread cùng gọi `n++`. Hai lần tăng có chắc tăng tổng cộng 2 không?

**Đáp án:** Không. Có thể lost update. Phải dùng atomic read–modify–write hoặc lock.

**Câu 4.** Một thread ghi `volatile boolean a=true`; thread kia đọc `volatile boolean b`, với a và b không liên quan. Đọc b có trực tiếp synchronizes-with ghi a không?

**Đáp án:** Không. Quy tắc write/read trực tiếp yêu cầu **cùng field v**; muốn có happens-before cho dữ liệu liên quan phải tìm các cạnh hợp lệ khác.

**Câu 5.** `volatile List<String> list`; sau khi publish list, một writer tiếp tục `list.add(...)` và reader gọi `list.size()` không lock. Reference volatile đã làm việc này an toàn chưa?

**Đáp án:** Chưa. Các mutation đồng thời trên mutable list vẫn phải dùng đúng thiết kế thread-safe/immutable snapshot hoặc synchronization thích hợp.

## 17. Tài liệu đối chiếu

- **Java Language Specification §17.4.4 — Synchronization Order:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4.4
- **Java Language Specification §17.4.5 — Happens-before Order:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4.5
- **Java Language Specification §8.3.1.4 — volatile Fields:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.3.1.4
- **AtomicInteger API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- **CountDownLatch API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- **Thread.onSpinWait API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#onSpinWait()

**Ghi nhớ:** *Ghi dữ liệu trước volatile write; reader thực hiện volatile read cùng field trước khi đọc dữ liệu.* Chuỗi program order → synchronizes-with → program order tạo happens-before, giúp publication có visibility/ordering đúng. Nhưng volatile **không làm compound update atomic**, không khóa thread, không lưu đủ mọi sự kiện và không bảo vệ những mutation xảy ra thiếu đồng bộ sau publication.
