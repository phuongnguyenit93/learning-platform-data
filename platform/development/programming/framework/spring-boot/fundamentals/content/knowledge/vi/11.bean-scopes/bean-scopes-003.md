# Bean singleton có trạng thái và vấn đề an toàn khi nhiều luồng truy cập

Trong Spring, **singleton** là scope mặc định của bean. Điều đó có nghĩa một bean definition thường được container tạo thành một instance dùng chung trong phạm vi **một ApplicationContext**. Khi nhiều request HTTP, tác vụ nền hoặc message listener cùng sử dụng bean đó, chúng có thể gọi phương thức của cùng một object gần như đồng thời.

Vì vậy, một hiểu nhầm nguy hiểm là: **bean singleton do Spring quản lý thì tự động an toàn khi nhiều luồng truy cập**. Điều này không đúng. Spring quản lý việc tạo, cung cấp và vòng đời của bean; Spring không tự khóa mọi field, không tự tuần tự hóa mọi lời gọi phương thức và không tự bảo vệ trạng thái có thể thay đổi bên trong object.

Bài học này giải thích vì sao singleton có thể gặp race condition, lost update và vấn đề visibility; cách tổ chức service stateless, dữ liệu bất biến, atomic operation, lock và concurrent collection; cùng những lưu ý khi ứng dụng chạy HTTP, @Async, scheduler hoặc nhiều instance.

## 1. Singleton scope có nghĩa gì?

Một bean có scope **singleton** được tạo và quản lý như một instance cho bean definition trong một Spring container. Khi nhiều thành phần inject cùng bean đó, chúng thường nhận tham chiếu tới cùng object:

~~~text
Spring ApplicationContext
        │
        ▼
   OrderService bean
   (một instance)
        ▲
        │
   ┌────┼─────────────┐
   │    │             │
   ▼    ▼             ▼
Request A          Request B       Scheduled job
Thread A           Thread B        Scheduler thread
   │                  │                │
   └──────────────┬───┴────────────────┘
                  ▼
          cùng OrderService object
~~~

Singleton **không có nghĩa**:

- Chỉ có một luồng được phép gọi bean.
- Các phương thức của bean luôn chạy tuần tự.
- Mọi field được tự động khóa.
- Object an toàn khi nhiều luồng cùng sửa trạng thái.
- Chỉ có một instance bean trên toàn bộ hệ thống phân tán.

Singleton là khái niệm về **số lượng instance trong container**, còn thread safety là tính chất của **cách object xử lý truy cập đồng thời**. Hai khái niệm này độc lập.

### Singleton của Spring khác singleton pattern toàn JVM

Spring singleton được giới hạn theo container và bean definition. Nếu ứng dụng tạo hai ApplicationContext độc lập, mỗi context có thể có một instance riêng của bean tương ứng. Nếu ứng dụng chạy ba process hoặc ba pod, mỗi process có container và singleton riêng.

~~~text
Process A / ApplicationContext A  → OrderService A
Process B / ApplicationContext B  → OrderService B
Process C / ApplicationContext C  → OrderService C
~~~

Vì vậy, không nên dựa vào field singleton trong Spring để lưu một trạng thái dùng chung giữa nhiều server. Muốn chia sẻ trạng thái giữa các instance, cần một hệ thống dùng chung như database, cache hoặc message broker cùng cơ chế nhất quán phù hợp.

## 2. Vì sao bean singleton có thể bị truy cập đồng thời?

Trong ứng dụng web, một HTTP server thường xử lý nhiều request bằng các luồng thực thi khác nhau. Spring MVC gọi controller và service cho từng request, nhưng những bean singleton được inject có thể là cùng một instance.

Ngoài request HTTP, một bean còn có thể được gọi từ:

- Phương thức chạy bất đồng bộ qua **@Async** hoặc executor.
- Công việc định kỳ qua **@Scheduled**.
- Message listener xử lý nhiều message.
- Nhiều service khác cùng gọi một dependency.
- Callback hoặc event handler được kích hoạt bởi những luồng khác nhau.

Ví dụ, controller và scheduler cùng sử dụng một service:

~~~java
@Service
public class ReportService {

    public Report generate() {
        // Đọc dữ liệu và tạo báo cáo.
        return new Report();
    }
}
~~~

Nếu **generate()** chỉ dùng biến cục bộ và các dependency được sử dụng an toàn khi đồng thời, service có thể được dùng chung. Nhưng nếu nó ghi dữ liệu vào field dùng chung cho từng lần chạy, nhiều luồng có thể can thiệp vào nhau.

Điều cần xem xét không phải chỉ là bean được gọi từ controller hay scheduler, mà là **có những luồng nào có thể truy cập cùng trạng thái tại cùng thời điểm**.

## 3. Stateful và stateless bean

Một bean **stateless** không giữ dữ liệu thay đổi riêng cho từng lần gọi trong các field dùng chung. Nó có thể có dependency bất biến và dùng biến cục bộ trong phương thức.

~~~java
@Service
public class TaxCalculator {

    private final TaxPolicy taxPolicy;

    public TaxCalculator(TaxPolicy taxPolicy) {
        this.taxPolicy = taxPolicy;
    }

    public BigDecimal calculate(BigDecimal amount) {
        BigDecimal rate = taxPolicy.rateFor(amount);
        return amount.multiply(rate);
    }
}
~~~

Ở ví dụ này, **amount** và **rate** là biến cục bộ của từng lần gọi. Nếu **TaxPolicy** cũng an toàn khi chia sẻ, bean có thể phục vụ nhiều request mà không cần lưu trạng thái theo request trong field.

Một bean **stateful** giữ trạng thái có thể thay đổi giữa các lần gọi:

~~~java
@Service
public class ShoppingCartService {

    private final List<String> items = new ArrayList<>();

    public void add(String item) {
        items.add(item);
    }

    public List<String> getItems() {
        return items;
    }
}
~~~

Nếu bean này là singleton, mọi người dùng có thể đang thao tác trên cùng danh sách **items**. Giỏ hàng của người này có thể trộn với người khác; đồng thời, ArrayList không được thiết kế để nhiều luồng cùng sửa tùy ý.

~~~text
Customer A ── add("Book") ──┐
                            ▼
                     cùng items list
                            ▲
Customer B ── add("Phone") ─┘
~~~

Vấn đề ở đây gồm cả **sai ranh giới dữ liệu** (giỏ hàng thuộc về ai?) và **an toàn đồng thời** (nhiều thread cùng sửa ArrayList). Chỉ đổi ArrayList thành một collection thread-safe cũng không giải quyết được việc các khách hàng dùng chung một giỏ.

### Nơi đặt trạng thái theo request

Dữ liệu riêng của một lần gọi thường nên được truyền qua tham số hoặc object riêng:

~~~java
public Order calculateOrder(
        CustomerId customerId,
        List<OrderLine> lines) {
    // Xử lý dữ liệu của lần gọi hiện tại.
}
~~~

Nếu dữ liệu cần lưu lâu dài qua nhiều request, hãy lưu trong database/cache với khóa theo người dùng hoặc phiên làm việc. Nếu cần một object có vòng đời gắn với HTTP request, có thể cân nhắc request scope khi thực sự phù hợp; scope đó vẫn không thay thế việc thiết kế dữ liệu và đồng bộ khi có nhiều request cùng truy cập cùng session.

## 4. Race condition: khi kết quả phụ thuộc vào thứ tự thực thi

**Race condition** xảy ra khi kết quả chương trình phụ thuộc vào thứ tự hoặc thời điểm các luồng thực thi thao tác trên trạng thái dùng chung.

Ví dụ một bean đếm số request:

~~~java
@Service
public class VisitCounter {

    private int count = 0;

    public void increment() {
        count++;
    }

    public int currentValue() {
        return count;
    }
}
~~~

Dòng **count++** trông như một thao tác đơn giản, nhưng thực chất có thể được hiểu thành:

1. Đọc giá trị hiện tại của count.
2. Cộng thêm 1.
3. Ghi kết quả trở lại count.

Giả sử **count = 10** và hai luồng cùng gọi increment:

~~~text
Thread A                       Thread B
--------                       --------
Đọc count = 10
                               Đọc count = 10
Cộng 1 → 11
                               Cộng 1 → 11
Ghi count = 11
                               Ghi count = 11

Kết quả thực tế: 11
Kết quả mong đợi: 12
~~~

Một lần cập nhật bị mất, gọi là **lost update**. Dù cả hai lời gọi đều đã chạy, kết quả chỉ tăng một đơn vị.

### Một số dạng lỗi đồng thời thường gặp

| Vấn đề | Biểu hiện |
|---|---|
| **Race condition** | Kết quả phụ thuộc vào thứ tự xen kẽ của các luồng |
| **Lost update** | Một cập nhật ghi đè cập nhật khác |
| **Visibility problem** | Một luồng không quan sát được thay đổi mới nhất của luồng khác theo cách chương trình kỳ vọng |
| **Check-then-act race** | Hai luồng cùng kiểm tra điều kiện rồi cùng thực hiện thao tác vốn chỉ nên xảy ra một lần |
| **Compound operation race** | Nhiều thao tác riêng lẻ phải được xem là một đơn vị nhưng không được bảo vệ cùng nhau |
| **Deadlock** | Các luồng giữ lock và chờ lock của nhau, khiến không thể tiếp tục |

Không phải mọi lỗi đồng thời đều tạo exception. Nhiều lỗi chỉ làm dữ liệu sai trong một số thời điểm hoặc dưới tải đủ lớn, nên có thể khó tái hiện khi thử thủ công.

## 5. Visibility và Java Memory Model

Ngoài việc hai luồng cùng ghi, một luồng có thể ghi dữ liệu nhưng luồng khác không quan sát được thay đổi theo thứ tự mà lập trình viên kỳ vọng. Đây là vấn đề **visibility**.

~~~java
public class WorkerSwitch {

    private boolean running = true;

    public void stop() {
        running = false;
    }

    public void work() {
        while (running) {
            // Tiếp tục làm việc.
        }
    }
}
~~~

Nếu một luồng chạy **work()** và luồng khác gọi **stop()**, không có cơ chế đồng bộ thích hợp, luồng đang chạy không được bảo đảm quan sát thay đổi theo cách cần thiết. Trình biên dịch hoặc runtime có thể tối ưu hóa việc đọc; Java Memory Model quy định những quan hệ visibility và ordering mà chương trình được bảo đảm.

### volatile cho trạng thái đơn giản

Có thể khai báo:

~~~java
public class WorkerSwitch {

    private volatile boolean running = true;

    public void stop() {
        running = false;
    }

    public void work() {
        while (running) {
            // Tiếp tục làm việc.
        }
    }
}
~~~

**volatile** bảo đảm các lần đọc/ghi biến đó có semantics visibility và ordering theo Java Memory Model. Khi một luồng ghi **false**, luồng khác đọc biến volatile sẽ quan sát giá trị đã được ghi theo quy tắc happens-before.

Nhưng **volatile không làm mọi thao tác trên biến trở thành atomic**. Ví dụ:

~~~java
private volatile int count;

public void increment() {
    count++;
}
~~~

vẫn có race condition vì **count++** là thao tác đọc-sửa-ghi gồm nhiều bước. Volatile phù hợp với cờ trạng thái hoặc reference được thay thế theo quy tắc đơn giản; nó không thay thế lock hoặc atomic operation cho cập nhật kết hợp.

## 6. Cách 1: thiết kế bean stateless và dùng dữ liệu bất biến

Giải pháp thường đơn giản nhất là tránh giữ trạng thái thay đổi theo request trong field của singleton. Dùng tham số phương thức và biến cục bộ:

~~~java
@Service
public class DiscountService {

    private final DiscountPolicy policy;

    public DiscountService(DiscountPolicy policy) {
        this.policy = policy;
    }

    public BigDecimal apply(
            BigDecimal amount,
            CustomerTier customerTier) {
        BigDecimal rate = policy.rateFor(customerTier);
        return amount.multiply(rate);
    }
}
~~~

Nếu **DiscountPolicy** bất biến hoặc thread-safe, service này có thể phục vụ nhiều luồng. Dữ liệu đầu vào thuộc về mỗi lần gọi và không được lưu vào field chung.

### Dùng immutable object

Một object bất biến không cho phép thay đổi trạng thái sau khi tạo. Ví dụ:

~~~java
public record DiscountPolicy(
        BigDecimal standardRate,
        BigDecimal premiumRate) {

    public BigDecimal rateFor(CustomerTier tier) {
        return tier == CustomerTier.PREMIUM
                ? premiumRate
                : standardRate;
    }
}
~~~

Nếu các giá trị bên trong cũng bất biến, object có thể được nhiều luồng đọc an toàn mà không cần khóa cho từng lần truy cập.

**Lưu ý:** record chỉ làm các component field final và cung cấp API record; nếu một component là List, Map hoặc object mutable khác, record không tự biến object bên trong thành immutable. Cần sao chép phòng thủ (defensive copy) hoặc dùng collection/value type bất biến khi cần.

### Final có ý nghĩa gì?

Field **final** chỉ được gán một lần sau khi object được tạo. Nó giúp ngăn việc thay reference sau đó và hỗ trợ thiết kế dependency ổn định:

~~~java
private final OrderRepository repository;
~~~

Nhưng nếu reference trỏ tới một object mutable như **ArrayList**, việc khai báo field final không làm các phần tử trong list bất biến và không làm thao tác trên list thread-safe.

~~~java
private final List<String> names = new ArrayList<>();
~~~

Field **names** không thể trỏ sang list khác sau khi constructor hoàn tất, nhưng nhiều luồng vẫn có thể đồng thời thêm/xóa phần tử trong chính ArrayList đó. **Final bảo vệ việc gán lại reference, không bảo vệ trạng thái mutable của object được tham chiếu.**

## 7. Cách 2: dùng AtomicInteger và atomic classes

Với các thao tác đơn giản như tăng bộ đếm, **AtomicInteger** cung cấp thao tác nguyên tử:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class VisitCounter {

    private final AtomicInteger count = new AtomicInteger();

    public int increment() {
        return count.incrementAndGet();
    }

    public int currentValue() {
        return count.get();
    }
}
~~~

**incrementAndGet()** thực hiện tăng và trả giá trị mới theo thao tác atomic, tránh lost update của ví dụ int thông thường.

Các lớp atomic phổ biến:

| Class | Công dụng |
|---|---|
| **AtomicInteger** | Cập nhật nguyên tử một số nguyên |
| **AtomicLong** | Cập nhật nguyên tử một số long |
| **AtomicBoolean** | Trạng thái boolean |
| **AtomicReference<T>** | Thay thế/đọc một reference nguyên tử |
| **LongAdder** | Bộ cộng phù hợp cho thống kê nhiều luồng với tần suất cập nhật cao |

### Atomic không tự bảo vệ nhiều biến cùng lúc

Giả sử cần duy trì cả **available** và **reserved** sao cho tổng không đổi. Dùng hai AtomicInteger riêng lẻ không làm một thao tác cập nhật cả hai biến trở thành atomic:

~~~java
available.decrementAndGet();
reserved.incrementAndGet();
~~~

Luồng khác có thể quan sát trạng thái ở giữa hai thao tác. Nếu một invariant cần được duy trì trên nhiều field, phải bảo vệ toàn bộ thao tác bằng một lock, một cấu trúc dữ liệu atomic phù hợp hoặc thiết kế lại trạng thái thành một object được cập nhật nguyên tử qua AtomicReference.

### LongAdder cho thống kê

Nếu chỉ cần thống kê số lần xảy ra dưới tải cập nhật cao, **LongAdder** có thể giảm tranh chấp so với một biến atomic đơn:

~~~java
private final LongAdder requests = new LongAdder();

public void recordRequest() {
    requests.increment();
}

public long requestCount() {
    return requests.sum();
}
~~~

LongAdder phù hợp cho số liệu thống kê mà việc đọc tổng có thể phản ánh một ảnh chụp gần đúng trong lúc cập nhật đồng thời đang diễn ra. Nếu cần một giá trị tuyến tính hóa chính xác tại một thời điểm cho quyết định nghiệp vụ, hãy chọn cơ chế phù hợp hơn.

## 8. Cách 3: synchronized để bảo vệ thao tác kết hợp

Khi một thao tác gồm nhiều bước phải được thực hiện như một đơn vị, có thể dùng **synchronized**:

~~~java
@Service
public class VisitCounter {

    private int count;

    public synchronized int increment() {
        count++;
        return count;
    }

    public synchronized int currentValue() {
        return count;
    }
}
~~~

Với instance method synchronized, thread phải lấy monitor lock của **this** trước khi chạy phần thân phương thức. Các synchronized instance method khác dùng cùng monitor sẽ không thực thi đồng thời trên cùng object.

~~~text
Thread A ── lấy lock ── increment() ── nhả lock
Thread B ── chờ lock ── lấy lock ── increment() ── nhả lock
~~~

Khi nhiều luồng cùng gọi trên một singleton instance, thao tác được bảo vệ bởi cùng monitor.

### Đồng bộ hóa một đoạn mã

Không nhất thiết khóa toàn bộ phương thức. Có thể dùng một lock cụ thể:

~~~java
public class Inventory {

    private final Object lock = new Object();
    private int available;
    private int reserved;

    public void reserve(int quantity) {
        synchronized (lock) {
            if (quantity <= 0 || available < quantity) {
                throw new IllegalArgumentException(
                        "Không đủ hàng");
            }

            available -= quantity;
            reserved += quantity;
        }
    }
}
~~~

Hai cập nhật nằm trong cùng critical section, nên những lời gọi khác dùng cùng lock không thể chen vào giữa. Ví dụ chỉ minh họa đồng bộ trong một JVM; nếu tồn kho được chia sẻ giữa nhiều application instance, monitor lock của một process không bảo vệ được dữ liệu trên toàn hệ thống.

### Chọn lock nào?

**synchronized** thường đủ cho một vùng tới hạn đơn giản. Khi cần khả năng nâng cao như thử lấy lock có timeout, interruptible acquisition, nhiều condition hoặc fairness option, có thể dùng **ReentrantLock**:

~~~java
private final ReentrantLock lock = new ReentrantLock();

public void update() {
    lock.lock();
    try {
        // Thay đổi trạng thái được bảo vệ.
    } finally {
        lock.unlock();
    }
}
~~~

Luôn đặt **unlock()** trong **finally** để tránh giữ lock khi có exception. Lock cần được dùng nhất quán bởi mọi đoạn mã truy cập trạng thái được bảo vệ; nếu một nơi đọc/ghi mà không lấy lock, invariant có thể vẫn bị phá vỡ.

### Không khóa quá rộng

Giữ lock trong lúc gọi HTTP API, đọc file lớn hoặc chờ một dịch vụ ngoài có thể làm các thread khác phải đợi lâu, giảm throughput và tạo nguy cơ deadlock. Critical section nên ngắn, rõ ràng và chỉ bao quanh thao tác cần đồng bộ.

## 9. Cách 4: dùng concurrent collections

Nếu cần cấu trúc dữ liệu chia sẻ giữa nhiều luồng, hãy cân nhắc collection trong **java.util.concurrent** thay vì tự dùng collection không thread-safe.

Ví dụ lưu số lần xử lý theo loại sự kiện:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public class EventStatistics {

    private final ConcurrentHashMap<String, LongAdder> counts =
            new ConcurrentHashMap<>();

    public void record(String eventType) {
        counts.computeIfAbsent(
                eventType,
                key -> new LongAdder())
              .increment();
    }

    public long countFor(String eventType) {
        LongAdder counter = counts.get(eventType);
        return counter == null ? 0L : counter.sum();
    }
}
~~~

**ConcurrentHashMap** hỗ trợ thao tác map an toàn khi nhiều luồng truy cập. **computeIfAbsent** giúp tạo giá trị cho key khi chưa có theo semantics đồng thời của map. **LongAdder** hỗ trợ cập nhật bộ đếm.

Các collection đồng thời khác:

| Collection | Khi phù hợp |
|---|---|
| **ConcurrentHashMap** | Map được nhiều luồng đọc/ghi |
| **CopyOnWriteArrayList** | Danh sách đọc rất nhiều, thay đổi ít |
| **ConcurrentLinkedQueue** | Queue không chặn, nhiều producer/consumer |
| **BlockingQueue** | Producer/consumer cần chờ khi queue rỗng hoặc đầy |
| **ConcurrentSkipListMap** | Map có thứ tự với thao tác đồng thời |

### Thread-safe collection không làm toàn bộ logic thread-safe

Đoạn sau vẫn có thể sai:

~~~java
if (!map.containsKey(key)) {
    map.put(key, createValue());
}
~~~

Ngay cả khi **map** là ConcurrentHashMap, chuỗi **containsKey** rồi **put** là hai thao tác riêng. Hai thread có thể cùng thấy key chưa tồn tại và cùng tạo value.

Nếu muốn tính toán và đưa giá trị vào map theo một thao tác phối hợp, có thể dùng:

~~~java
map.computeIfAbsent(key, this::createValue);
~~~

Hoặc API atomic phù hợp với yêu cầu. Nhưng cần xem xét tác dụng phụ trong mapping function: không nên thực hiện một quy trình bên ngoài tốn thời gian hoặc không thể lặp an toàn bên trong thao tác map nếu semantics của nó không phù hợp.

## 10. ConcurrentHashMap không giải quyết ranh giới dữ liệu người dùng

Quay lại ví dụ giỏ hàng:

~~~java
private final Map<String, List<String>> carts =
        new ConcurrentHashMap<>();
~~~

Map ngoài có thể thread-safe, nhưng mỗi giá trị **List<String>** vẫn là ArrayList mutable. Hai request của cùng một khách hàng có thể cùng sửa list đó; collection bên trong vẫn không an toàn khi truy cập đồng thời.

~~~text
ConcurrentHashMap
  ├── customer-A → ArrayList  ← nhiều thread có thể cùng sửa
  └── customer-B → ArrayList
~~~

Có thể dùng collection đồng thời bên trong hoặc khóa theo từng giỏ, nhưng vẫn phải thiết kế thao tác nghiệp vụ như thêm sản phẩm, đổi số lượng và checkout thành những đơn vị nhất quán. Một ConcurrentHashMap không tự bảo đảm tổng số lượng, giá và trạng thái đơn hàng luôn đồng bộ.

Nếu giỏ hàng là dữ liệu cần tồn tại qua restart hoặc được chia sẻ giữa nhiều server, database/cache phân tán có thể là nơi lưu phù hợp hơn. Khi đó cần transaction, optimistic locking, distributed lock hoặc cơ chế cập nhật nguyên tử phù hợp với mô hình dữ liệu.

## 11. Scope khác nhau có giải quyết được thread safety không?

Spring có nhiều bean scope:

| Scope | Vòng đời instance | Có tự bảo đảm thread safety không? |
|---|---|---|
| **singleton** | Một instance cho bean definition trong container | Không |
| **prototype** | Container tạo instance mới mỗi lần được yêu cầu | Không; instance vẫn có thể được chia sẻ sau khi tạo |
| **request** | Một instance gắn với HTTP request trong web context | Không tự bảo vệ nếu instance được truyền sang nhiều thread hoặc chia sẻ qua async |
| **session** | Một instance gắn với HTTP session | Không; một session có thể có nhiều request đồng thời |

### Prototype không phải instance theo request

Một bean prototype được yêu cầu từ container sẽ tạo instance mới theo lần resolve. Nhưng nếu singleton inject trực tiếp prototype vào constructor, singleton thường giữ instance prototype được tạo tại thời điểm inject; nó không tự nhận instance mới cho mỗi lời gọi phương thức.

Nếu cần tạo instance prototype theo từng lần sử dụng, có thể inject **ObjectProvider<T>** hoặc một factory phù hợp:

~~~java
@Service
public class JobCoordinator {

    private final ObjectProvider<JobContext> contexts;

    public JobCoordinator(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    public void runJob() {
        JobContext context = contexts.getObject();
        context.execute();
    }
}
~~~

Đoạn ví dụ giả định **JobContext** được khai báo với prototype scope và có phương thức execute. Container tạo instance khi **getObject()** được gọi. Vòng đời cleanup của prototype bean không được container quản lý đầy đủ như singleton; nếu object sở hữu tài nguyên, ứng dụng cần có kế hoạch đóng tài nguyên.

### Request scope cũng cần được dùng đúng mục đích

Một bean request-scoped có thể giữ dữ liệu gắn với một HTTP request. Tuy nhiên:

- Nó không phải nơi lưu dữ liệu bền vững qua request.
- Nếu request được xử lý qua async thread hoặc truyền object sang luồng khác, cần hiểu cơ chế context propagation và vòng đời request.
- Nó không giải quyết truy cập đồng thời vào cùng dữ liệu trong database.

### Session scope có thể có nhiều request cùng lúc

Người dùng mở nhiều tab hoặc gửi nhiều request gần như đồng thời trong cùng session. Một bean session-scoped có thể được nhiều request truy cập trong cùng thời điểm. Vì vậy, state mutable bên trong session bean vẫn cần thiết kế đồng bộ nếu có truy cập đồng thời.

**Đổi scope chỉ thay đổi vòng đời và phạm vi chia sẻ object. Nó không tự thay thế thiết kế thread safety.**

## 12. @Async và @Scheduled: thêm luồng truy cập vào singleton

Một service có thể được gọi từ luồng request và luồng nền:

~~~java
@Service
public class NotificationService {

    private final EmailSender emailSender;

    public NotificationService(EmailSender emailSender) {
        this.emailSender = emailSender;
    }

    @Async
    public CompletableFuture<Void> sendAsync(String address) {
        emailSender.send(address);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Khi **@EnableAsync** được bật và phương thức được gọi qua Spring proxy, công việc có thể được gửi tới executor. Những lần gọi đồng thời vẫn có thể sử dụng cùng singleton **NotificationService**. Nếu service giữ field mutable cho từng email, các lần chạy có thể đè dữ liệu lên nhau.

Tương tự:

~~~java
@Component
public class DailyJob {

    @Scheduled(fixedRate = 60_000)
    public void run() {
        // Công việc định kỳ.
    }
}
~~~

Scheduler gọi phương thức theo lịch. Nếu job chạy lâu hơn chu kỳ hoặc có nhiều instance ứng dụng, cần hiểu cấu hình scheduler và cách job được kích hoạt. Không nên giả định chỉ vì phương thức được đánh dấu **@Scheduled** thì mọi truy cập đều tuần tự trên toàn hệ thống.

### @Async không phải thuốc chữa race condition

Chạy bất đồng bộ có thể tăng khả năng xử lý song song, nhưng điều đó còn làm nhiều lời gọi đồng thời hơn. Nếu các task dùng chung singleton có state mutable, nguy cơ race condition tăng lên.

Hãy truyền dữ liệu của task qua tham số hoặc command object bất biến:

~~~java
@Async
public CompletableFuture<Void> sendAsync(
        NotificationCommand command) {
    emailSender.send(command.address(), command.message());
    return CompletableFuture.completedFuture(null);
}
~~~

Không lưu **currentAddress** hoặc **currentMessage** vào field singleton trước khi gửi.

## 13. @Transactional không làm field singleton thread-safe

Một hiểu nhầm khác là: nếu phương thức service có **@Transactional**, mọi thao tác trong bean đã an toàn khi nhiều thread gọi. Không đúng.

Transaction thường quản lý ranh giới thao tác với tài nguyên như database thông qua transaction manager. Nó không tự khóa mọi field Java trong singleton bean:

~~~java
@Service
public class UnsafeSequenceService {

    private int nextNumber;

    @Transactional
    public int next() {
        return ++nextNumber;
    }
}
~~~

Hai transaction có thể cùng gọi **next()** trên một object và cùng cập nhật field **nextNumber**. Database transaction không biến phép tăng int trong heap thành atomic operation.

Nếu số thứ tự cần duy nhất giữa nhiều instance, field singleton còn không đủ vì mỗi process có biến riêng. Nên dùng sequence/identity của database, atomic update hoặc cơ chế cấp số tập trung có tính nhất quán phù hợp.

**Transaction và thread safety giải quyết những phạm vi khác nhau:**

- Transaction bảo vệ tính nhất quán của thao tác trên tài nguyên có hỗ trợ giao dịch.
- Lock/atomic/concurrent structure bảo vệ truy cập đồng thời tới trạng thái trong bộ nhớ theo phạm vi của chúng.
- Constraint/transaction/locking ở database bảo vệ dữ liệu chia sẻ giữa các transaction và các process theo cơ chế database.

## 14. Đồng bộ trong một JVM khác đồng bộ giữa nhiều instance

Ví dụ:

~~~java
private final AtomicInteger counter = new AtomicInteger();
~~~

Biến này an toàn cho các thread cùng truy cập **instance chứa nó**. Nhưng khi ứng dụng chạy trên ba server, mỗi server có một AtomicInteger riêng:

~~~text
Server A: counter = 10
Server B: counter = 10
Server C: counter = 10
~~~

Tăng counter trên server A không làm biến trên B và C thay đổi. **synchronized**, **ReentrantLock**, **AtomicInteger** và **ConcurrentHashMap** trong bộ nhớ process không tự tạo distributed synchronization.

Khi trạng thái được chia sẻ giữa nhiều instance, có thể dùng:

- Database với transaction, unique constraint, optimistic/pessimistic locking hoặc atomic update.
- Redis hoặc một hệ thống lưu trữ chia sẻ với primitive đồng bộ phù hợp.
- Message broker/queue để tuần tự hóa xử lý theo key hoặc partition khi mô hình cho phép.
- Distributed lock với lease, timeout, xử lý mất kết nối và fencing token nếu yêu cầu cần lock phân tán.

Không nên chọn distributed lock chỉ vì ứng dụng có nhiều server. Đôi khi transaction hoặc constraint database đơn giản và đáng tin cậy hơn. Hãy bắt đầu từ invariant cần bảo vệ và chọn cơ chế phù hợp với tài nguyên thực sự được chia sẻ.

## 15. Cách xác định giải pháp phù hợp

| Nhu cầu | Cách tiếp cận nên cân nhắc |
|---|---|
| Service chỉ tính toán từ input và dependency bất biến | Stateless service |
| Cấu hình dùng chung, không thay đổi sau startup | Immutable configuration object, final dependency |
| Cờ dừng/chạy đơn giản giữa các thread | volatile hoặc AtomicBoolean |
| Bộ đếm đơn giản trong một JVM | AtomicInteger/AtomicLong |
| Bộ đếm thống kê có nhiều lần cập nhật | LongAdder |
| Cập nhật nhiều field phải cùng nhau | synchronized hoặc Lock |
| Map chia sẻ nhiều thread | ConcurrentHashMap, đồng thời thiết kế thao tác compound |
| Dữ liệu riêng từng request | Biến cục bộ/command object/request scope phù hợp |
| Trạng thái cần tồn tại qua restart | Database hoặc storage bền vững |
| Trạng thái dùng chung giữa nhiều process | Database/cache/message broker với cơ chế phối hợp phù hợp |

Không có một annotation nào biến mọi class thành thread-safe. Giải pháp phải xuất phát từ **state được chia sẻ, thao tác nào cần atomic và phạm vi các luồng/process có thể truy cập**.

## 16. Ví dụ thực hành: sửa bộ đếm trong singleton

Giả sử có service:

~~~java
@Service
public class RequestCounter {

    private int total;

    public int increment() {
        total++;
        return total;
    }

    public int getTotal() {
        return total;
    }
}
~~~

Nếu 20 thread cùng gọi **increment()** 1.000 lần, tổng kỳ vọng là 20.000. Nhưng vì **total++** không atomic, kết quả có thể nhỏ hơn. Kết quả lỗi phụ thuộc lịch thực thi, nên có lần chạy tình cờ vẫn ra đúng.

### Phương án AtomicInteger

~~~java
@Service
public class RequestCounter {

    private final AtomicInteger total = new AtomicInteger();

    public int increment() {
        return total.incrementAndGet();
    }

    public int getTotal() {
        return total.get();
    }
}
~~~

Trong một JVM, những lần tăng trên cùng AtomicInteger không bị mất cập nhật.

### Phương án synchronized

~~~java
@Service
public class RequestCounter {

    private int total;

    public synchronized int increment() {
        return ++total;
    }

    public synchronized int getTotal() {
        return total;
    }
}
~~~

Cả đọc và ghi đều dùng cùng monitor. Nếu chỉ đồng bộ increment mà đọc total không đồng bộ và không có cơ chế visibility khác, việc đọc vẫn chưa được bảo vệ như thiết kế mong muốn.

### Phác thảo kiểm thử đồng thời

Có thể dùng **ExecutorService**, **CountDownLatch** và JUnit để khởi chạy nhiều task, chờ tất cả hoàn tất rồi kiểm tra tổng:

~~~java
int threadCount = 20;
int incrementsPerThread = 1_000;

ExecutorService executor =
        Executors.newFixedThreadPool(threadCount);
CountDownLatch start = new CountDownLatch(1);
CountDownLatch done = new CountDownLatch(threadCount);

for (int i = 0; i < threadCount; i++) {
    executor.submit(() -> {
        try {
            start.await();
            for (int j = 0; j < incrementsPerThread; j++) {
                counter.increment();
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        } finally {
            done.countDown();
        }
    });
}

start.countDown();
done.await();
executor.shutdown();

assertEquals(
        threadCount * incrementsPerThread,
        counter.getTotal());
~~~

Đây là phần thân minh họa cho một test; cần tạo **counter** trước, thêm import JUnit/concurrent và xử lý timeout/shutdown phù hợp trong test thực tế. Test đồng thời có thể giúp phát hiện lỗi nhưng một lần chạy thành công không chứng minh mọi interleaving đều an toàn. Với race condition, cần hiểu cơ chế đồng bộ và có kiểm thử lặp lại hoặc công cụ chuyên biệt khi rủi ro cao.

## 17. Những sai lầm phổ biến

### Cho rằng singleton mặc định đã thread-safe

Spring singleton chỉ nói về scope. Một bean singleton chứa **ArrayList**, **HashMap** hoặc field mutable vẫn có thể bị nhiều thread truy cập đồng thời.

### Đổi ArrayList thành Vector hoặc synchronizedList rồi dừng lại

Collection đồng bộ bảo vệ một số thao tác riêng lẻ, nhưng một chuỗi như **if (!list.contains(x)) list.add(x)** vẫn có thể cần một critical section chung. Ngoài ra, thread-safe collection không giải quyết việc dữ liệu có thuộc về đúng người dùng hay không.

### Đặt dữ liệu request vào field service

Field **currentUser**, **currentOrder** hoặc **currentRequest** trong singleton có thể bị request khác ghi đè. Hãy truyền dữ liệu qua tham số hoặc object theo request.

### Dùng volatile cho phép tăng biến

Volatile giúp visibility, không làm **count++** atomic. Dùng AtomicInteger hoặc lock nếu cần cập nhật không mất dữ liệu.

### Dùng synchronized nhưng không thống nhất lock

Nếu phương thức A khóa **this** nhưng phương thức B khóa một object khác, chúng không bảo vệ cùng trạng thái. Mọi đường đọc/ghi invariant phải tuân theo cùng một cơ chế.

### Giữ lock khi gọi hệ thống bên ngoài

Một lời gọi HTTP chậm trong synchronized block có thể giữ lock lâu, làm nhiều thread chờ và giảm khả năng phục vụ. Thu hẹp vùng critical section và tránh gọi code không kiểm soát trong khi đang giữ lock.

### Dùng local lock để bảo vệ dữ liệu phân tán

Lock trong một JVM không phối hợp với process khác. Nếu nhiều instance cùng sửa một bản ghi database, cần cơ chế ở tầng dữ liệu hoặc distributed coordination.

### Cho rằng @Transactional bảo vệ mọi field

Transaction không phải Java object monitor. Field mutable trong singleton vẫn cần atomic/lock hoặc được thiết kế lại.

### Cho rằng request/session scope tự thread-safe

Một session có thể có nhiều request đồng thời. Request-scoped object có thể được truyền sang async execution. Scope không tự giải quyết mọi truy cập chéo luồng.

## 18. Các nguyên tắc thiết kế cho singleton bean

**Giữ service stateless khi có thể.** Dùng field final cho dependency và biến cục bộ cho dữ liệu của từng lần gọi.

**Ưu tiên object bất biến.** Cấu hình, policy và value object bất biến dễ chia sẻ hơn object mutable.

**Nếu cần state mutable, xác định invariant trước.** Viết rõ điều kiện nào phải luôn đúng và thao tác nào phải được xem là một đơn vị.

**Chọn primitive đồng bộ đúng với thao tác.** Atomic cho cập nhật đơn giản, lock cho thao tác kết hợp, concurrent collection cho cấu trúc dữ liệu chia sẻ.

**Tách trạng thái người dùng khỏi service singleton.** Dùng database/cache hoặc context có vòng đời phù hợp.

**Xem xét mọi nguồn gọi song song.** HTTP, @Async, scheduler, listener và callback đều có thể tạo truy cập đồng thời.

**Phân biệt trong process và giữa process.** Atomic/lock trong heap không thay thế transaction hay cơ chế chia sẻ dữ liệu giữa nhiều server.

**Không dựa vào thử nghiệm thủ công để kết luận thread-safe.** Lỗi race có thể chỉ xuất hiện dưới tải, trên một runtime hoặc một thứ tự xen kẽ hiếm gặp.

## Kết luận

**Singleton scope của Spring không đồng nghĩa với thread safety.** Một bean singleton thường được nhiều request và tác vụ nền sử dụng chung trong cùng ApplicationContext. Nếu bean giữ trạng thái mutable mà không có cơ chế đồng bộ, nhiều luồng có thể gây race condition, lost update hoặc lỗi visibility.

Hướng thiết kế nên ưu tiên là **service stateless, dependency bất biến và dữ liệu theo từng lần gọi nằm trong biến cục bộ hoặc object riêng**. Khi thật sự cần state chia sẻ, hãy chọn Atomic classes, synchronized/Lock hoặc concurrent collections theo loại thao tác và invariant cần bảo vệ. Nếu dữ liệu được chia sẻ giữa nhiều process, cần cơ chế ở tầng lưu trữ hoặc phối hợp phân tán.

Spring chịu trách nhiệm quản lý vòng đời và cung cấp bean; **người phát triển chịu trách nhiệm thiết kế trạng thái và tính an toàn đồng thời của mã bean**. Giữ rõ ranh giới đó giúp ứng dụng Spring Boot hoạt động ổn định khi có nhiều request, thread và instance.
