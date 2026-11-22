# Document thread-safety contract cho public API trong Java

Một public API có thể trả về đúng giá trị khi được gọi tuần tự nhưng vẫn gây race condition, deadlock hoặc kết quả khó dự đoán khi nhiều thread gọi cùng lúc. Người dùng thư viện **không thể suy ra thread safety chỉ từ tên lớp, từ `synchronized` xuất hiện ở vài phương thức, hoặc từ việc mã chạy ổn trong kiểm thử đơn luồng**. Vì vậy, API công khai cần một **thread-safety contract**: lời cam kết có thể kiểm chứng về những kiểu truy cập đồng thời được hỗ trợ, kết quả quan sát được, nghĩa vụ của caller và giới hạn của chính implementation.

Một hợp đồng tốt trả lời rõ:

- **Ai được gọi đồng thời?** Nhiều thread có thể gọi cùng instance, cùng method, hay chỉ những phương thức nhất định?
- **Điều gì được bảo đảm?** Atomicity, visibility, ordering, snapshot consistency và các invariant nào?
- **Điều gì không được bảo đảm?** Thứ tự giữa các lời gọi concurrent, tính nguyên tử của chuỗi lời gọi, fairness hay thời gian phản hồi?
- **Caller có trách nhiệm gì?** Khóa bên ngoài, không sửa input trong khi API xử lý, không chia sẻ mutable object trả về, không tái nhập callback?
- **API có chờ, gọi callback, quản lý tài nguyên hoặc vòng đời không?** Có thể block, interrupt, đóng, hủy hoặc nhận kết quả sau khi đóng như thế nào?

Bài học này áp dụng cho **Java concurrency nói chung** (Java Memory Model, `java.lang`, `java.util.concurrent` và Javadoc). Không bàn về cơ chế concurrency riêng của Spring Framework.

## 1. Thread-safety contract là một phần của hợp đồng API

Một public API thường đã mô tả tham số, kiểu trả về, exception và tiền/hậu điều kiện. Nhưng trong chương trình đa luồng, điều đó chưa đủ.

Ví dụ:

```java
public interface Counter {
    long get();
    long incrementAndGet();
}
```

Đây chỉ là giao diện minh họa, chưa phải chương trình có `main`. Người dùng cần biết:

1. Có thể gọi `incrementAndGet()` từ hai thread cùng lúc không?
2. Nếu hai lời gọi bắt đầu khi bộ đếm bằng 5, chúng có trả về hai giá trị khác nhau (`6` và `7`) hay có thể cùng trả `6`?
3. `get()` đang chạy cùng một lần tăng được phép thấy giá trị nào?
4. Hai phép `get(); incrementAndGet();` có được coi là một giao dịch không?
5. Có thể dùng một `Counter` từ thread khác sau khi xây dựng xong mà cần thêm bước publication không?

Một tài liệu chỉ ghi "Thread-safe" không thể trả lời hết các câu hỏi đó. Hợp đồng nên nói **điểm tuyến tính hóa về mặt quan sát**, giới hạn của từng phương thức và điều không được cam kết.

**Thread safety là thuộc tính của một cách sử dụng cụ thể.** Một class có thể thread-safe với phương thức đọc và ghi đơn lẻ nhưng không đảm bảo giao dịch gồm nhiều lời gọi. Một class khác yêu cầu người gọi phải đặt tất cả thao tác dưới một lock. Không thể áp dụng một nhãn duy nhất cho mọi interaction mà không xét phạm vi cam kết.

## 2. Phân loại mức an toàn trước khi viết hợp đồng

Một bộ thuật ngữ thực hành giúp người viết nhất quán:

| Mức độ | Ý nghĩa đối với caller | Ví dụ cách mô tả |
| --- | --- | --- |
| **Immutable** | Sau khi xây dựng, trạng thái quan sát được không đổi; các thành phần bên trong cũng phải được xử lý đúng | "Instances are immutable and safe to share after construction." |
| **Thread-safe** | Các thao tác được chỉ định có thể được gọi đồng thời theo các cam kết ghi rõ | "All public methods support concurrent calls on the same instance." |
| **Conditionally thread-safe** | Chỉ an toàn nếu caller đáp ứng điều kiện về khóa, thứ tự, callback hoặc phạm vi | "Iteration requires the caller to hold the documented lock." |
| **Thread-compatible** | Nhiều thread có thể dùng nếu caller tự đồng bộ các truy cập xung đột | "Concurrent access requires external synchronization." |
| **Not thread-safe** | Không có bảo đảm truy cập đồng thời; thường giới hạn một owner | "Do not access an instance concurrently from multiple threads." |
| **Thread-confined** | Instance hoặc mutable state chỉ thuộc một thread trong một giai đoạn sở hữu | "Each instance must be accessed only from its creating thread." |

Đây là **thuật ngữ mô tả thiết kế**; Java SE không có một annotation chuẩn bắt buộc như `@ThreadSafe` cho mọi public API. Một số thư viện có annotation riêng, nhưng annotation chỉ hữu ích khi có định nghĩa và tài liệu đi kèm. Trong Javadoc, nên đặt lời cam kết rõ ràng bằng ngôn ngữ con người, kể cả khi dự án có annotation.

Cần phân biệt thêm:

- **Unmodifiable** không đồng nghĩa **immutable sâu (deeply immutable)**. `Collections.unmodifiableList(list)` có thể phản ánh sửa đổi của underlying list; một record chứa `ArrayList` vẫn có thể có state mutable.
- **Stateless** không tự chứng minh toàn bộ object graph an toàn. Phương thức không có field riêng vẫn có thể ghi một `static Map` hoặc sử dụng collaborator không thread-safe.
- **Synchronized từng method** chưa chứng minh tổ hợp nhiều method là atomic.
- **Có lock bên trong** không bảo đảm loại bỏ deadlock, reentrancy bất lợi hay starvation.

## 3. Ghi rõ đối tượng và phạm vi được bảo vệ

Hợp đồng cần chỉ rõ đang nói đến **một instance**, **nhiều instance có chung tài nguyên**, hay **trạng thái process-wide**.

Ví dụ hai instance `Counter` giữ hai `AtomicLong` riêng thì mỗi instance có thể thread-safe độc lập. Nhưng nếu cả hai instance dùng chung một mutable static cache, việc lock theo `this` ở mỗi instance không thể tự bảo vệ cache chung.

Một đoạn Javadoc mức class có thể viết:

```java
/**
 * A thread-safe counter.
 *
 * <p>All public methods may be called concurrently on the same instance.
 * Each increment is atomic, and get() observes a value from one atomic read.
 * Separate Counter instances have independent state.
 *
 * <p>A sequence such as get() followed by incrementAndGet()
 * is not an atomic transaction.
 */
public final class Counter {
    // Implementation goes here.
}
```

Đây là **mẫu Javadoc minh họa**, không phải class độc lập để chạy. Mô tả class cho người đọc một nền chung; từng method vẫn cần diễn đạt những ngoại lệ hoặc bảo đảm hẹp hơn.

Nếu API dùng shared global resource, hãy ghi rõ. Ví dụ: "All instances share one cache; changes from one instance may be visible through another." Điều này quan trọng hơn việc chỉ viết "instances are thread-safe".

## 4. Những thuộc tính cần diễn đạt riêng

### Atomicity: thao tác logic có không bị xen giữa?

Nếu `incrementAndGet()` là atomic, hai thread cùng tăng một bộ đếm ban đầu 5 thì kết quả sẽ tương ứng hai bước tăng riêng biệt, cho dù thứ tự caller nhận kết quả phụ thuộc scheduling. Nhưng chuỗi:

```java
if (counter.get() < limit) {
    counter.incrementAndGet();
}
```

**không tự atomic**. Thread khác có thể thay đổi counter giữa `get()` và `incrementAndGet()`. Nếu có invariant "không vượt giới hạn", API nên cung cấp một phương thức như `tryIncrementWithinLimit(limit)` với bảo đảm atomic trên cả kiểm tra và thay đổi.

Một thread-safe class cần phân biệt **method atomicity** với **operation composition**.

### Visibility: lời gọi khác có nhìn thấy cập nhật?

Một contract có thể bảo đảm tác động của operation đã hoàn thành sẽ được các thao tác đồng bộ tiếp theo quan sát theo ngữ nghĩa của nó. Nếu chỉ ghi "synchronized" mà không giải thích đối tượng bảo vệ, caller vẫn có thể không biết ý nghĩa liên thread.

Java Memory Model định nghĩa các quan hệ **happens-before**. Ví dụ `synchronized` trên cùng monitor hoặc thao tác `AtomicLong` có semantics tương ứng giúp bảo đảm visibility, ordering. Tuy nhiên, contract nên ghi theo hành vi API mà caller cần, thay vì buộc caller biết implementation dùng loại lock nào.

### Ordering: kết quả đồng thời có thứ tự ra sao?

Một `ConcurrentHashMap` cho phép nhiều thread cập nhật, nhưng không cam kết iterator là một snapshot đóng băng hoặc duyệt key theo thứ tự chèn. Với một queue FIFO, cần mô tả FIFO được áp dụng cho **những lần enqueue có thứ tự xác định**, chứ không hứa thứ tự "theo giờ hệ thống" giữa hai producer chạy concurrent.

### Snapshot consistency

`snapshot()` có thể có nhiều nghĩa:

- Snapshot **nhất quán tại một điểm** của collection dưới cùng lock.
- Một view **unmodifiable** của dữ liệu vẫn đang thay đổi.
- Một iterator **weakly consistent**, có thể phản ánh một phần cập nhật concurrent theo hợp đồng.
- Một ảnh chụp chỉ gồm một số field, trong khi field khác có thể đổi độc lập.

Tên `snapshot` không thay thế cam kết về thời điểm, nội dung và tính bất biến của kết quả.

### Liveness và blocking

Một API được bảo vệ đúng dữ liệu vẫn có thể block vô hạn khi chờ tài nguyên. Đối với public API, hãy nói phương thức có thể block trong trường hợp nào, có timeout không, có hỗ trợ interruption/cancellation không, có giữ lock trong callback không và trạng thái có thể thay đổi khi thoát do exception không.

**Không cam kết lock-free/wait-free** chỉ vì dùng `AtomicInteger` hoặc concurrent collection ở một phần code: mức tiến triển phải xét **toàn operation**, các vòng retry và những lời gọi phụ thuộc.

## 5. Linearizability: ngôn ngữ chính xác cho nhiều API concurrent

Một operation được gọi là **linearizable** nếu mỗi lời gọi có thể được coi như có một thời điểm tác động đơn lẻ nằm giữa **lúc bắt đầu** và **lúc kết thúc** lời gọi, và thứ tự này tôn trọng thứ tự thực của các operation không chồng lấn. Đây là thuộc tính mạnh và rất hữu ích cho counter, map operation, atomic register và queue.

Ví dụ hai lần `incrementAndGet()` trên cùng `AtomicLong` là các thao tác atomic; nếu chúng trả `6` và `7`, có thể giải thích như một thứ tự tuần tự phù hợp, không cần chỉ định thread nào đi trước. Nếu một lời gọi kết thúc hoàn toàn trước lời gọi tiếp theo bắt đầu, thứ tự tuyến tính hóa phải phù hợp với quan hệ đó.

Cần viết contract đúng mức:

- "Each `incrementAndGet()` is atomic" là cam kết từng operation.
- "A call to `get()` returns the value from one atomic read" không có nghĩa hai lần `get` liên tiếp tạo snapshot cho cả chuỗi.
- "Concurrent calls may complete in either order" giải thích điều không có ordering guarantee.
- "The final count equals the number of completed successful increments" cần được hiểu khi **không còn increment concurrent hoặc các update khác** và tất cả task liên quan đã hoàn tất.

Không phải mọi API concurrent đều cam kết linearizability cho mọi phương thức. Một báo cáo aggregate từ nhiều counter độc lập có thể chỉ là trạng thái **eventually consistent** hoặc **weakly consistent** theo tài liệu. Hãy dùng đúng từ; "thread-safe" không tự đồng nghĩa "mọi read là global snapshot linearizable".

## 6. Ví dụ đầy đủ: public counter với contract Javadoc

Lưu thành `AtomicCounterContractDemo.java` (Java 17+):

```java
import java.util.concurrent.atomic.AtomicLong;

public class AtomicCounterContractDemo {

    /**
     * A counter safe for concurrent use by multiple threads.
     *
     * <p>Each incrementAndGet() and get() is an atomic operation.
     * Each completed increment contributes exactly one to the value.
     * Calls from different threads may be ordered differently.
     *
     * <p>Multiple calls do not form an atomic transaction.
     * In particular, get() followed by incrementAndGet() does not
     * reserve a value or enforce a maximum.
     */
    public static final class Counter {
        private final AtomicLong value = new AtomicLong();

        /**
         * Atomically increments the value and returns the updated value.
         * Concurrent invocations may return in any order to callers.
         *
         * @return the value after this increment
         */
        public long incrementAndGet() {
            return value.incrementAndGet();
        }

        /**
         * Returns one atomic observation of the current counter.
         * The value may change immediately after this method returns.
         *
         * @return the observed value
         */
        public long get() {
            return value.get();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();

        Runnable increment10k = () -> {
            for (int i = 0; i < 10_000; i++) {
                counter.incrementAndGet();
            }
        };

        Thread first = new Thread(increment10k);
        Thread second = new Thread(increment10k);

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("Total: " + counter.get());
    }
}
```

Biên dịch/chạy:

```bash
javac AtomicCounterContractDemo.java
java AtomicCounterContractDemo
```

Stdout chính xác:

```text
Total: 20000
```

**Phân tích contract:**

1. Mức class khẳng định nhiều thread có thể dùng **cùng một instance**.
2. `AtomicLong.incrementAndGet()` làm mỗi phép tăng atomic; chương trình không bị mất increment dù hai worker xen kẽ.
3. Không cam kết thread nào nhận một giá trị cụ thể khi chạy concurrent. Thứ tự thực hiện và nhận kết quả do scheduling.
4. `Thread.join()` thành công trước khi main đọc tổng, nên tại thời điểm đó cả hai worker đã hoàn tất. Việc in 20.000 có căn cứ từ number of increments và API atomic, không dựa vào timing.
5. `get()` đơn lẻ thread-safe; một tổ hợp `get` rồi `incrementAndGet` **không thành transaction**. Javadoc nhấn mạnh giới hạn để caller không tự chế kiểm tra giới hạn sai.

Không cần ghi trong Javadoc rằng implementation sử dụng `AtomicLong` nếu đó không phải phần giao diện mà caller được dựa vào. Quan trọng hơn là cam kết atomicity/ordering còn đúng nếu sau này thay implementation bằng lock thích hợp.

## 7. Hợp đồng của từng phương thức phải khớp logic nghiệp vụ

Giả sử một API quản lý danh sách entry có giới hạn dung lượng. Hai method riêng:

```java
int size();
void add(String entry);
```

dù đều `synchronized` **không tự bảo đảm** client thực hiện được:

```java
if (registry.size() < capacity) {
    registry.add(entry);
}
```

Nếu hai caller cùng thấy size bằng `capacity - 1`, cả hai có thể cố thêm. Một public API tốt nên trực tiếp biểu diễn bất biến:

```java
boolean tryAdd(String entry);
```

Trong tài liệu, ghi rõ:

- `tryAdd` **atomically checks capacity and adds** trong cùng operation.
- Trả `true` chỉ khi element được thêm thành công; `false` khi đã đầy ở điểm kiểm tra atomic.
- Hai caller cạnh tranh chỗ cuối có thể nhận kết quả khác nhau; không hứa caller khởi động trước nhất định thắng.
- Không thể dùng `size()` để "giữ chỗ". `size` chỉ quan sát tại một thời điểm, và giá trị có thể đổi ngay khi method trả về.

Điều này chuyển tính đúng đắn từ một chuỗi khó đồng bộ ở phía client vào một operation có hợp đồng rõ ràng.

## 8. Ví dụ đầy đủ: class thread-safe nhưng iterator/snapshot cũng phải được mô tả

Lưu thành `RegistryContractDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RegistryContractDemo {

    /**
     * A bounded, thread-safe collection of String entries.
     *
     * <p>All methods may be called concurrently on the same instance.
     * Each tryAdd() atomically checks the bound and adds an entry.
     * snapshot() returns an unmodifiable, independent list of values
     * captured while holding the same lock as the writers.
     *
     * <p>Entries may appear in either order when calls overlap.
     * Calling size() and then tryAdd() is not an atomic transaction.
     * Entries are immutable String objects.
     */
    public static final class Registry {
        private final int capacity;
        private final List<String> entries = new ArrayList<>();

        public Registry(int capacity) {
            if (capacity < 0) {
                throw new IllegalArgumentException("capacity < 0");
            }
            this.capacity = capacity;
        }

        /**
         * Atomically inserts a non-null entry if room remains.
         *
         * @return true if inserted, false if the registry is full
         * @throws NullPointerException if entry is null
         */
        public synchronized boolean tryAdd(String entry) {
            Objects.requireNonNull(entry, "entry");
            if (entries.size() >= capacity) {
                return false;
            }
            entries.add(entry);
            return true;
        }

        /**
         * Returns one atomic size observation.
         * The size may change immediately after this method returns.
         */
        public synchronized int size() {
            return entries.size();
        }

        /**
         * Returns an unmodifiable snapshot in insertion order as
         * observed while holding the lock.
         *
         * <p>The returned list is not a live view of this registry.
         * Later inserts do not change this snapshot.
         */
        public synchronized List<String> snapshot() {
            return List.copyOf(entries);
        }
    }

    public static void main(String[] args) throws Exception {
        Registry registry = new Registry(2_000);
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            @SuppressWarnings("unchecked")
            Future<?>[] jobs = new Future<?>[4];

            for (int worker = 0; worker < 4; worker++) {
                final int id = worker;
                jobs[worker] = pool.submit(() -> {
                    for (int i = 0; i < 500; i++) {
                        if (!registry.tryAdd(id + "-" + i)) {
                            throw new IllegalStateException("Unexpected full");
                        }
                    }
                });
            }

            for (Future<?> job : jobs) {
                job.get();
            }

            List<String> snapshot = registry.snapshot();
            System.out.println("Entries: " + registry.size());
            System.out.println("Snapshot size: " + snapshot.size());
            System.out.println("Can add more: " + registry.tryAdd("extra"));
        } finally {
            pool.shutdown();
        }
    }
}
```

Chạy:

```bash
javac RegistryContractDemo.java
java RegistryContractDemo
```

Stdout trên đường chạy bình thường:

```text
Entries: 2000
Snapshot size: 2000
Can add more: false
```

**Vì sao contract đáng tin?**

- `tryAdd` thực hiện cả kiểm tra capacity và thao tác `add` trong cùng monitor (`this`). Khi nhiều caller tranh chấp vị trí cuối, chỉ một caller có thể thêm, các caller còn lại thấy cập nhật.
- `size` và `snapshot` dùng **cùng monitor**, do đó thấy cấu trúc list nhất quán với thao tác `tryAdd`. Không để reference tới mutable `ArrayList` nội bộ thoát khỏi class.
- `List.copyOf` tạo một danh sách không cho chỉnh qua API và độc lập với những thêm mới về sau; trong ví dụ `String` immutable nên không có mutable element cần đồng bộ thêm.
- Bốn worker gửi 2.000 lần thêm rồi `Future.get()` được gọi cho cả bốn, do đó main không in số lượng trước khi các task thành công. Thứ tự chuỗi theo worker là không xác định, nhưng số lượng là xác định.
- `snapshot` có insertion order tại một thời điểm được khóa, song **không cam kết** các lời gọi của worker concurrent sẽ đi theo số id hoặc thứ tự bắt đầu thread.
- `size()` đọc hiện thời và `tryAdd()` là hai operation khác nhau; một client tự ghép chúng không thể suy ra có transaction.

**Thiết kế tài liệu phải nói đến ownership và mutable return value.** Nếu `snapshot()` trả về chính `entries` hoặc trả một unmodifiable *view* trên `entries`, lời hứa "independent snapshot" sẽ sai. Implementation và Javadoc phải khớp nhau.

## 9. Hợp đồng thread-safe khác với immutable và read-only view

So sánh ba API trả dữ liệu:

```java
List<String> directView();       // Trả reference mutable?
List<String> unmodifiableView(); // View phản ánh thay đổi của nguồn?
List<String> snapshot();         // Bản sao tại một thời điểm?
```

Đây là chữ ký minh họa, chưa nêu implementation. Nếu API trả một tham chiếu mutable mà caller có thể tự sửa, không thể tiếp tục khẳng định class giữ được invariant nội bộ trừ khi có cơ chế bảo vệ tương ứng.

Một `Collections.unmodifiableList(source)` chỉ chặn mutation **qua view**; nếu `source` còn được sửa ở nơi khác thì view cũng phản ánh thay đổi. Một `List.copyOf(source)` tạo list không chỉnh sửa được, nhưng việc copy chính `source` vẫn cần diễn ra trong điều kiện hợp lệ nếu source đang bị writer khác cập nhật.

Tài liệu nên ghi:

- Kết quả là **live view** hay **snapshot**?
- Kết quả có **unmodifiable** không? Khi nào nội dung có thể thay đổi?
- Nếu phần tử là object mutable, caller có được sửa phần tử hay không?
- Caller có được giữ kết quả và sử dụng trên thread khác không, và điều kiện safe publication là gì?
- API có cam kết ordering hoặc consistency khi lấy nhiều snapshot liên tiếp không?

Một collection thread-safe bao quanh mutable values **không tự làm mọi value thread-safe**. Ví dụ `ConcurrentHashMap<String, ArrayList<String>>` bảo vệ thao tác map theo hợp đồng nhưng các `ArrayList` bên trong vẫn cần chính sách riêng.

## 10. Compound actions: điều cần cảnh báo rõ nhất trong tài liệu

Ngay cả `ConcurrentHashMap` cũng cần phân biệt giữa **một phương thức atomic** với **chuỗi thao tác client tự ghép**.

```java
// Có race logic nếu hai thread cùng cập nhật một key.
Integer before = counts.get(key);
counts.put(key, before == null ? 1 : before + 1);
```

Với `ConcurrentHashMap`, từng thao tác `get` và `put` được hỗ trợ concurrent, nhưng **get-then-put** không tự là một transaction. Tài liệu API nên chỉ ra thao tác dành cho yêu cầu này:

```java
counts.merge(key, 1, Integer::sum);
```

`merge` là operation phối hợp theo key được `ConcurrentHashMap` bảo đảm theo hợp đồng. Tuy vậy, nếu cập nhật cần invariant xuyên **nhiều key**, `merge` trên một key không giải quyết transaction nhiều key.

Với listener list, thao tác "kiểm tra chưa đăng ký rồi đăng ký" cũng cần semantics rõ. Với registry giới hạn dung lượng, `tryAdd` phải kiểm tra và thêm trong cùng critical section. Với tài khoản, "đủ số dư rồi trừ" phải là một operation được bảo vệ như một đơn vị.

Đề nghị dùng cụm diễn đạt chính xác:

> "Individual operations are safe for concurrent calls. Client-composed sequences are not atomic unless explicitly documented."

Nếu public API cho phép callback hoặc iterator, cần nói cả những operation **vượt qua ranh giới của một lần gọi method**.

## 11. Iterator và stream: caller có cần khóa ngoài không?

Một phương thức trả `Iterator<E>`, `Stream<E>` hoặc live view có thể kéo việc đọc dữ liệu ra **sau** khi method tạo iterator đã trả về. Nếu lock chỉ được giữ trong method tạo iterator, nhiều bước duyệt tiếp theo vẫn có thể xảy ra khi writer đang sửa.

Ví dụ `Collections.synchronizedList(...)` cho phép đồng bộ nhiều operation đơn lẻ qua wrapper, nhưng caller thường **phải khóa thủ công trên wrapper trong suốt iteration** khi có writer concurrent:

```java
List<String> list =
        Collections.synchronizedList(new ArrayList<>());

synchronized (list) {
    for (String value : list) {
        use(value);
    }
}
```

Đây là đoạn minh họa; cần import `java.util.List`, `java.util.ArrayList`, `java.util.Collections`, và định nghĩa `use`. Nếu tài liệu API chỉ ghi "synchronized list" mà không nêu yêu cầu khóa khi iteration, client có thể dùng sai.

Một API với `ConcurrentHashMap` hoặc `CopyOnWriteArrayList` có **kiểu iteration khác**:

- `ConcurrentHashMap`: iterator weakly consistent; không phải snapshot atomic của toàn map.
- `CopyOnWriteArrayList`: iterator giữ một snapshot mảng tại lúc tạo; các mutation sau đó không xuất hiện trong lần duyệt này, và iterator không hỗ trợ `remove`.
- `Collections.synchronizedList`: phải đọc hợp đồng về manual synchronization khi iteration.

**Documentation phải nêu semantics thực sự của kiểu kết quả**, không chỉ tên implementation class. Nếu muốn người dùng khỏi quản lý lock, cân nhắc cung cấp `snapshot()` hoặc phương thức xử lý có scope được kiểm soát.

## 12. Callback và listener: điểm khó trong public contract

Một API có thể an toàn trong lúc cập nhật collection nội bộ nhưng vẫn gọi **mã của client** trong callback. Lúc ấy phải tài liệu hóa:

1. Callback chạy trên thread nào: caller thread, một worker riêng, hay một executor được cung cấp?
2. Có thể **nhiều callback chạy concurrent** trên cùng listener object không?
3. Callback có được gọi lại các method của API (reentrancy) không?
4. Có giữ lock nội bộ khi gọi callback không?
5. Nếu callback ném exception, xử lý tiếp các listener còn lại như thế nào?
6. Khi `removeListener` chạy concurrent với `publish`, listener đã bị xóa có thể vẫn nhận event đang diễn ra không?
7. Có bảo đảm ordering, exactly-once hoặc delivery trong trường hợp lỗi/hủy không?

Ví dụ API dùng `CopyOnWriteArrayList` và gọi callback ngay trên thread của người gọi. Đây là class minh họa đầy đủ (cần đặt vào file `ListenerRegistry.java` nếu sử dụng):

```java
import java.util.Objects;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Consumer;

/**
 * A thread-safe registry of listeners.
 *
 * <p>addListener, removeListener and publish may be called concurrently.
 * A publish call invokes callbacks synchronously on its caller's thread,
 * in the list order captured when its iteration begins.
 *
 * <p>Two concurrent publish calls may invoke the same listener
 * concurrently. A remove does not cancel a callback already included
 * in an in-progress publish snapshot.
 *
 * <p>Callbacks execute without an internal registry lock being held.
 * If a callback throws a RuntimeException, it propagates to the
 * publish caller and later callbacks in that publication are skipped.
 */
public final class ListenerRegistry {
    private final CopyOnWriteArrayList<Consumer<String>> listeners =
            new CopyOnWriteArrayList<>();

    public void addListener(Consumer<String> listener) {
        listeners.add(Objects.requireNonNull(listener));
    }

    public void removeListener(Consumer<String> listener) {
        listeners.remove(listener);
    }

    public void publish(String event) {
        for (Consumer<String> listener : listeners) {
            listener.accept(event);
        }
    }
}
```

**Vì sao cách ghi này quan trọng?** `CopyOnWriteArrayList` bảo vệ cấu trúc danh sách và iterator snapshot, nhưng **không tự bảo vệ mã callback**. Hai caller cùng gọi `publish` có thể khiến cùng listener nhận hai callback đồng thời. Nếu listener tự sửa state thường, nó phải tự bảo vệ state hoặc API cần thay đổi cách dispatch.

Ví dụ này không có `main` nên không có stdout. Nó biên dịch độc lập với JDK 17+, và thể hiện một contract cụ thể: callbacks trên caller thread, có thể đồng thời, không có lock nội bộ lúc gọi callback, exception lan ra và dừng lượt publish đó. Nếu đổi implementation sang executor async, hợp đồng về thread, ordering, completion và lỗi cũng phải đổi.

**Lưu ý:** Tự gọi mã client trong một vùng `synchronized` có thể kéo dài thời gian giữ lock, tạo reentrancy khó phân tích hoặc deadlock khi callback gọi ngược vào một API khác. Cần chủ động thiết kế thời điểm callback được gọi và công bố ràng buộc đó.

## 13. Thread ownership, aliasing và tham số mutable

Một public API có thể nhận `List<T>`, `byte[]` hoặc một object mutable từ caller. Hợp đồng phải làm rõ API:

- **Copy ngay** để sở hữu dữ liệu riêng?
- **Giữ reference** và dùng về sau?
- **Chuyển quyền sở hữu** trong một pipeline producer–consumer?
- **Cho phép caller sửa input** trong khi method đang chạy hay không?
- Có đồng bộ với những thread khác đang sửa input không?

Ví dụ:

```java
public final class TaskBatch {
    private final List<String> tasks;

    public TaskBatch(List<String> tasks) {
        this.tasks = List.copyOf(tasks);
    }

    public List<String> tasks() {
        return tasks;
    }
}
```

Class này dùng `List` nên cần import `java.util.List` nếu viết thành file độc lập. Constructor tạo snapshot của danh sách đầu vào (với những `String` immutable), sau đó không sửa. Nhưng **caller không được đồng thời sửa một ordinary ArrayList đầu vào trong lúc constructor đang copy** nếu muốn kết quả có ý nghĩa. Một contract nên ghi rằng constructor yêu cầu đầu vào ổn định trong quá trình copy và cấm null theo hợp đồng `List.copyOf`.

Nếu không copy mà giữ raw reference, Javadoc cần cảnh báo caller phải duy trì bất biến và quy tắc đồng bộ cho alias đó. Đặt field `final` chỉ ngăn gán lại tham chiếu, không làm nội dung mutable an toàn.

### Safe publication

Một object được xây dựng đúng và mang immutable state giúp giảm nhiều race, nhưng vẫn nên nói **caller phải công bố instance đúng cách** giữa các thread khi thiết kế có data chia sẻ phức tạp. Các cơ chế như thread start, volatile reference, lock, concurrent queue hoặc completion primitive có quy tắc happens-before.

Với immutable class được xây dựng đúng, các `final` fields có bảo đảm đặc biệt theo JMM nếu constructor không làm `this` thoát quá sớm. Tuy vậy, chúng không "đóng băng" một mutable object graph được đưa ra ngoài.

## 14. Blocking, timeout, interruption và cancellation thuộc public contract

Một API thread-safe vẫn có thể **block**, và tính đúng của caller phụ thuộc cách method trả về hay dừng.

Ví dụ nếu `take()` chờ queue có phần tử, tài liệu cần nêu:

- `take()` **có thể block vô thời hạn** khi queue rỗng.
- Phương thức có phản hồi `Thread.interrupt()` bằng `InterruptedException` không?
- API có overload timeout không; timeout tính theo đơn vị nào?
- Khi timeout xảy ra, có item nào đã bị tiêu thụ không?
- Khi cancel một task đang chạy, state đã thay đổi một phần có được rollback không?
- Khi thread bị ngắt, caller có cần khôi phục interrupt flag không?

Không được hứa "cancellation luôn dừng ngay". `Future.cancel(true)` thường chỉ gửi yêu cầu interruption khi có thể; task phải hợp tác với cancellation, và thao tác I/O có hợp đồng riêng.

Một đoạn Javadoc cho phương thức blocking nên có dạng:

```java
/**
 * Waits for the next message.
 *
 * <p>Concurrent producers and consumers are supported.
 * This method may block while the queue is empty.
 *
 * @return the next available message
 * @throws InterruptedException if interrupted while waiting
 */
public String take() throws InterruptedException {
    return queue.take();
}
```

Đây là **một method minh họa** trong class giả định có field `queue` kiểu `BlockingQueue<String>`; không phải chương trình độc lập. Hợp đồng về `InterruptedException` đến từ API được dùng bên trong. Nếu implementation sau này đổi sang busy-wait hoặc nuốt interruption, Javadoc không còn đúng.

**Timeout** và **fairness** là hai khái niệm khác nhau. Một phương thức có timeout chỉ giới hạn thời gian đợi theo hợp đồng, không cam kết người gọi nào thắng tranh chấp hoặc được xử lý theo thứ tự đăng ký.

## 15. Close và lifecycle: thread-safe không đồng nghĩa dùng được mọi lúc

Khi một public API có `close()`, `shutdown()`, `start()` hoặc `stop()`, cần định nghĩa state machine đủ rõ.

Ví dụ:

```text
NEW -> OPEN -> CLOSING -> CLOSED
```

Đây chỉ là một mô hình minh họa; không phải API nào cũng có đủ bốn state.

Các câu hỏi phải tài liệu hóa:

- Có được gọi `close()` đồng thời từ nhiều thread không, có **idempotent** không?
- Khi `close` bắt đầu, một `submit` vừa chạy song song được chấp nhận hay từ chối dựa vào **điểm quyết định atomic** nào?
- Các task đã nhận trước `close` có hoàn thành không? Có bị hủy không?
- Thread đang block trong `take` hoặc `await` được đánh thức thế nào?
- `close` tự block đợi mọi task hay chỉ gửi tín hiệu?
- Sau khi đóng, `getSnapshot` có còn dùng được? Nếu không, ném exception nào?
- Callback đã bắt đầu trước khi đóng có thể tiếp tục sau khi `close` trả về không?

**Không suy ra semantics từ tên method.** `ExecutorService.shutdown()` chẳng hạn ngừng nhận task mới nhưng thường cho task đã gửi chạy đến hoàn tất; `shutdownNow()` cố gắng dừng các task đang chạy và trả lại các task chưa bắt đầu, không bảo đảm tất cả thread dừng ngay. Nếu viết wrapper cho executor, tài liệu của wrapper phải nói chính sách lifecycle riêng của nó.

Một contract tránh deadlock phải xác định client có được gọi `close` từ callback/worker do chính API quản lý hay không. Một `close` chờ tất cả worker kết thúc có thể deadlock nếu gọi từ chính worker cần được đợi.

## 16. Điều kiện external synchronization cần được viết chính xác

Với một public API **không tự thread-safe**, chỉ nói "synchronize access externally" vẫn thiếu thông tin. Caller cần biết **khóa nào** và **phạm vi nào**.

Mẫu hợp đồng tốt:

> "Instances are not thread-safe. If an instance is accessed from multiple threads, the caller must synchronize all accesses to its mutable state, including reads, writes, iteration and compound operations, using the same lock. No mutable reference to internal state may be modified outside that lock."

Nếu class cung cấp một lock công khai, phải cân nhắc rủi ro cho client khi dùng lock đó cho logic khác. Nếu object nội bộ không bị lộ, dễ hơn là class tự bọc mọi thao tác bằng một lock riêng hoặc cung cấp các operation atomic mức nghiệp vụ.

Hãy tránh hứa "thread-safe if caller synchronizes" mà không định nghĩa cách phối hợp với những thread writer nội bộ do class tự tạo: caller có thể khóa trên `this` trong khi implementation dùng một lock riêng, khiến khóa ngoài không thực sự đồng bộ với worker.

### Điều kiện safe publication không phải khóa cho mọi mutation

Nếu object chỉ được khởi tạo rồi **không bao giờ thay đổi**, nó có thể được chia sẻ để đọc sau publication đúng. Nhưng nếu caller sau đó gọi một setter, các read khác cần quy tắc thêm. Hợp đồng nên phân biệt "safely published immutable state" và "concurrent mutation supported".

## 17. Memory consistency effects: mô tả ở mức hành vi

JMM dùng quan hệ **happens-before** để xác định các đảm bảo về visibility và ordering. Một class public không nhất thiết phải phơi bày chi tiết internal locking, nhưng tài liệu nên dựa vào các hiệu ứng memory consistency đã được bảo đảm bởi Java:

| Cơ chế | Liên hệ với public contract |
| --- | --- |
| `synchronized` cùng monitor | Unlock happens-before lần lock tiếp theo trên monitor đó |
| `volatile` write/read đúng giao thức | Volatile write happens-before volatile read tiếp theo phù hợp với cùng biến |
| `AtomicLong` operations | Có ngữ nghĩa atomic/volatile tương ứng cho field giá trị |
| `Thread.start()` | Những hành động trước `start()` happens-before hành động trong thread mới |
| `Thread.join()` thành công | Hành động của worker happens-before hành động của caller sau khi join |
| `ExecutorService.submit` và `Future.get` | Hành động trước submit HB task; task actions HB caller sau get |
| `BlockingQueue` | Hành động trước khi đưa item vào queue HB hành động sau khi consumer lấy item ra |
| `CountDownLatch` | Hành động trước `countDown()` HB hành động sau `await()` trả về phù hợp |

**Cạnh happens-before khác với scheduling guarantee.** HB giúp giải thích visibility/order. Nó không hứa task chạy trong một số mili giây xác định hay sẽ không bị starvation. Một API có thể đúng về memory safety mà vẫn cần timeout/backpressure và chính sách liveness.

Đối với public API, nên chuyển những cơ chế này thành điều caller cần: "Sau khi `awaitCompletion()` trả về bình thường, các kết quả của những tác vụ đã hoàn tất trước tín hiệu được công bố an toàn cho thread gọi", **nếu implementation thực sự bảo đảm** điều đó theo cơ chế sử dụng.

## 18. Error handling và exception khi gọi đồng thời

Khi một method ném exception, caller cần biết **tác động lên state**:

- Nếu `tryAdd` ném `NullPointerException` do input null, operation có để lại thay đổi gì không?
- Nếu callback ném exception, những listener đã được gọi trước đó có tạo side effect rồi không?
- Nếu một operation ghi qua nhiều tài nguyên và bị interrupt, có **partial commit** không?
- Nếu có retry, operation có **idempotent** theo key hoặc request id không?
- Exception từ worker có được lưu vào future hay bị bỏ qua?

"Thread-safe" không đồng nghĩa "mọi operation đều rollback khi có lỗi". **Atomicity** về tác động đồng thời và **exception safety** là hai thuộc tính cần tách riêng. Một API có thể linearizable trên các operation thành công nhưng vẫn cần tài liệu trạng thái khi operation thất bại.

Ví dụ trong `RegistryContractDemo`, `Objects.requireNonNull(entry)` chạy trước kiểm tra/thêm; input null ném `NullPointerException` mà không thêm item. Tài liệu method xác nhận điều này. Với method có callback trước khi commit, yêu cầu khác và cần cam kết rõ.

Nếu exception xảy ra trong task được gửi qua `ExecutorService.submit`, `Future.get()` thường phản ánh thất bại thông qua `ExecutionException`. Một API bọc future không nên âm thầm biến thất bại thành "completed successfully".

## 19. Tài liệu interface và extension points: ai chịu trách nhiệm thread safety?

Khi public API là interface hoặc abstract class được người khác implement, contract phải chỉ ra:

- **Caller có thể dựa vào điều gì** khi sử dụng một implementation bất kỳ?
- **Implementer bắt buộc bảo đảm điều gì** để tuân thủ interface?
- Những default methods có giả định về thread safety của primitive operations không?
- Callback hoặc extension hooks có được gọi concurrent không?
- Một implementation được phép chọn locking strategy khác nhưng vẫn giữ semantics không?

Nếu interface nói mọi implementation phải thread-safe, một implementation dùng `ArrayList` ordinary mà không đồng bộ sẽ **vi phạm interface contract**, dù code biên dịch hợp lệ.

Có thể dùng Javadoc `@implSpec` để mô tả yêu cầu dành cho implementation khi thích hợp; `@apiNote` để bổ sung hướng dẫn sử dụng và `@implNote` cho lưu ý triển khai. Tuy nhiên, các bảo đảm caller phải biết nên xuất hiện rõ trong **Javadoc công khai chính**, không bị giấu trong chú thích riêng về implementation.

Một mẫu mô tả trách nhiệm:

```java
/**
 * Concurrent key-value store.
 *
 * <p>Implementations must support concurrent invocations of get()
 * and put() on the same instance.
 * Each operation must be atomic for the specified key.
 * A read-modify-write sequence spanning two calls is not atomic.
 *
 * @param <K> key type
 * @param <V> value type
 */
public interface ConcurrentStore<K, V> {
    V get(K key);
    V put(K key, V value);
}
```

Đây là ví dụ hợp đồng interface, không có `main`. Một API thực tế cũng phải xác định nghĩa của null, thông báo lỗi, ordering và phạm vi key tương đương. Tránh hứa atomicity cấp key mà implementation không bảo đảm hoặc không có cách kiểm chứng.

## 20. Chọn vị trí viết và cấu trúc Javadoc

Nên viết thread-safety contract ở **cấp class/interface**, sau đó bổ sung ở method khi có khác biệt.

| Vị trí | Nên mô tả |
| --- | --- |
| Javadoc của class/interface | Phân loại mức thread safety; phạm vi instance/global; các bảo đảm chung; điều kiện caller |
| Constructor/factory | Input ownership; safe publication; có copy hay giữ reference; instance đã usable ngay chưa |
| Method state-changing | Atomicity; ordering; kết quả tranh chấp concurrent; lỗi; điều kiện sau khi method trả về |
| Method read/snapshot/iterator | Snapshot hay live view; consistency; ordering; mutable elements; có cần lock ngoài không |
| Callback/subscription | Thread gọi callback; concurrent/reentrant; ordering; exception; removal semantics |
| Blocking/lifecycle method | Blocking/timeout/interruption; close/cancel/stop; idempotency và công việc đang chạy |
| Extension point | Nghĩa vụ implementer; được gọi đồng thời hay chỉ một thread; cách propagate errors |

Một mẫu câu cấp class ngắn và hữu ích:

> "Instances are safe for concurrent use. Each method performs one atomic operation as documented. No atomicity is guaranteed across multiple calls. Returned snapshots are unmodifiable and do not reflect later updates. Callbacks may run concurrently on caller threads and must themselves be thread-safe."

Câu này **chỉ đúng** nếu implementation thực sự có những hành vi đó. Không copy nguyên văn cho mọi class; hãy chọn đúng lời cam kết, thay vì hứa quá rộng.

## 21. Public API chỉ cung cấp read operations có cần contract không?

Có. Một API tưởng chỉ đọc vẫn có thể:

- **Lazy initialize** cache lần đầu, ghi vào field hoặc map nội bộ.
- Cập nhật thống kê truy cập trong mỗi lần đọc.
- Đọc một mutable resource bên ngoài mà thread khác đang sửa.
- Trả iterator/live view bị writer khác thay đổi.
- Gọi callback/logging collaborator có trạng thái mutable.
- Lưu kết quả vào một bộ nhớ đệm theo instance/global.

Ví dụ `public List<String> getNames()` có thể tạo snapshot mỗi lần gọi, hoặc trả live list. Hai cách có contract rất khác nhau. **Không có setter trong public API không chứng minh implementation không có mutation**.

Ngược lại, một class chỉ giữ immutable state và có constructor đúng, không để tham chiếu mutable thoát ra ngoài, thường dễ chứng minh thread-safe hơn. Tài liệu vẫn nên nói rõ input/output ownership và publication assumption.

## 22. Đặt tên method để phản ánh semantics, rồi ghi contract chi tiết

Tên method giúp người dùng dự đoán nhưng không thay thế tài liệu:

- `snapshot()` gợi ý bản sao độc lập ở một điểm; cần nói rõ mức nhất quán và mutable elements.
- `tryAdd(...)` gợi ý trả kết quả khi cạnh tranh; cần nói atomicity và điều kiện false.
- `await(...)` gợi ý có thể block; cần nói timeout/interruption và điều kiện đã đạt khi trả về.
- `submit(...)` gợi ý không nhất thiết hoàn tất ngay; cần nói executor, ordering, rejection và lifecycle.
- `close()` gợi ý giải phóng tài nguyên; cần nói concurrency với ongoing operations và tính idempotent.
- `addListener/removeListener` gợi ý đăng ký callback; cần nói snapshot, concurrency, exception và số lần delivery.

Nếu method có tên rất mạnh như `getConsistentSnapshot()`, implementation phải chứng minh tính nhất quán của toàn bộ tập dữ liệu. Tránh đặt tên dựa trên mong muốn khi chưa có cơ chế bảo đảm.

## 23. Kiểm tra contract bằng các trường hợp concurrent

Một tài liệu tốt phải có khả năng **đối chiếu với implementation và kiểm thử**, dù stress test không thay thế proof về JMM.

Nhóm tình huống nên kiểm tra:

1. **Hai writer trên cùng instance:** không lost update, duplicate ngoài ý muốn hoặc violation invariant.
2. **Reader và writer concurrent:** read trả một trạng thái cho phép bởi contract; snapshot không bị phá khi writer tiếp tục.
3. **Hai call ghép:** kiểm tra tài liệu có cảnh báo không atomic; nếu cần transaction, có operation đúng cấp độ không.
4. **Race với close/cancel:** xác định điểm chấp nhận/reject task và cách đánh thức waiter.
5. **Callback reentrant:** callback gọi ngược API có deadlock, xếp hàng không mong muốn hoặc vi phạm ordering không.
6. **Callback concurrent:** cùng listener có bị gọi đồng thời không, và tài liệu có mô tả điều đó không.
7. **Input mutable và alias:** caller sửa input sau khi gửi có làm API đổi kết quả không; khi copy concurrent có hành vi không được bảo đảm không.
8. **Failure/interrupt/timeout:** trạng thái còn đúng, permit/lock được giải phóng, kết quả lỗi được truyền về đúng nơi không.
9. **Visibility:** caller sử dụng proper publication/completion primitive và đọc được dữ liệu đã cam kết sau điểm chờ.
10. **Đổi implementation:** kiểm tra hợp đồng hành vi vẫn đúng nếu thay `synchronized` bằng `Lock`, thay cấu trúc lưu trữ hay đổi executor.

Đừng viết test chỉ "chạy 1.000 lần và không có exception" rồi kết luận thread-safe. Race condition phụ thuộc scheduling; một test pass không có nghĩa mọi kết quả không hợp lệ đã bị loại trừ. Lập luận về invariant và happens-before là nền tảng, test nhằm kiểm tra và phát hiện vi phạm.

### Kiểm tra contract như checklist review

Khi review một public API, hãy đọc Javadoc **như người chỉ biết tài liệu mà không được xem code**:

- Có biết được có thể gọi đồng thời trên **cùng instance** hay không?
- Có biết được thao tác nào atomic, thao tác nào chỉ thread-safe riêng lẻ?
- Có biết kết quả trả về thuộc snapshot, live view hay eventual consistency không?
- Có biết contract của callback, iterator, close và failure không?
- Có biết phải cung cấp external lock hoặc ownership discipline nào không?
- Có thể thay implementation mà không làm hỏng lời hứa đã công bố không?

Nếu thiếu câu trả lời cho một hành vi thường gặp, public contract cần bổ sung. Nếu tài liệu hứa điều implementation chưa bảo đảm, cần sửa logic hoặc thu hẹp lời hứa trước khi phát hành.

## 24. Những lỗi thường gặp khi document thread safety

**Lỗi 1 — Chỉ ghi "Thread-safe".** Không chỉ rõ method nào atomic, callback có thể concurrent hay không, snapshot có nhất quán không. Người đọc dễ suy luận quá mức.

**Lỗi 2 — Ghi "Not thread-safe" nhưng không nói caller phải làm gì.** Nếu cần external synchronization, phải xác định những truy cập nào cùng chịu khóa, kể cả iteration và compound operations.

**Lỗi 3 — Coi `synchronized` là toàn bộ contract.** `synchronized` trên mỗi method không bảo đảm chuỗi nhiều method atomic; mã có thể còn callback hoặc alias ngoài khóa.

**Lỗi 4 — Hứa FIFO cho hai producer concurrent mà không định nghĩa thứ tự.** FIFO chỉ có nghĩa trên một thứ tự enqueue có thể xác định; không đồng nghĩa "caller A bắt đầu trước thì event A luôn tới trước".

**Lỗi 5 — Hứa snapshot trong khi trả unmodifiable view.** View có thể đổi theo underlying collection. Snapshot phải có đường copy và publication phù hợp.

**Lỗi 6 — Cho rằng concurrent collection bảo vệ mutable values.** `ConcurrentHashMap<K, ArrayList<V>>` không khiến value `ArrayList` thread-safe.

**Lỗi 7 — Không nêu threading model của callback.** Listener có thể bị gọi concurrent trên cùng instance từ nhiều caller; state của listener cần tự bảo vệ.

**Lỗi 8 — Không nêu block/interrupt.** Caller không biết phương thức có thể chờ vô hạn, hay hủy task có làm operation hoàn tất không.

**Lỗi 9 — Ghi "lock-free" hoặc "non-blocking" theo cảm tính.** Đó là thuộc tính tiến triển có định nghĩa riêng; không thể suy từ một biến `volatile` hoặc một atomic field.

**Lỗi 10 — Lộ internal mutable state.** Getter trả raw list/map giúp client bỏ qua lock, vi phạm invariants và làm lời hứa thread-safe không còn đúng.

**Lỗi 11 — Bỏ quên constructor hoặc static shared state.** Một instance có thể được dùng an toàn sau construction nhưng constructor giữ reference tới mutable input, hoặc nhiều instance chia sẻ cache global chưa được bảo vệ.

**Lỗi 12 — Tài liệu không cập nhật khi đổi implementation.** Chuyển từ callback đồng bộ sang async, hoặc từ snapshot sang weakly consistent iterator là thay đổi hành vi mà caller có thể phụ thuộc; cần xem như thay đổi contract.

## 25. Mẫu thread-safety contract có thể áp dụng

Đây là **khung nội dung** để áp dụng cho một public class Java, không phải template phải điền đầy đủ bằng mọi giá:

```text
Thread safety:
  [Thread-safe | Conditionally thread-safe | Thread-confined | Not thread-safe]

Scope:
  Safe for concurrent calls on [the same instance | independent instances |
  shared global state]. Specify any exceptions.

Operation semantics:
  [Method A] is atomic with respect to [...]
  [Method B] returns [a snapshot | a live view | weakly consistent data].
  Multi-call sequences are [not atomic | atomic under documented protocol].

Input/output ownership:
  Inputs are [copied | retained | transferred].
  Returned values are [immutable snapshots | mutable caller-owned |
  shared views]. Specify mutable element responsibilities.

Blocking and callbacks:
  [Method] may block under [...], supports interruption/timeout [...]
  Callbacks run on [...], may be concurrent/reentrant [...],
  and exceptions are handled by [...].

Lifecycle:
  Concurrent close/submit/cancel is defined by [...]
  Accepted work and waiters after close behave as [...]

Caller obligations:
  [No external lock | Lock X around reads/writes/iteration |
  Do not mutate input while processing | Confine instances to thread X]

Unsupported guarantees:
  No guarantee of [cross-call atomicity | callback total order |
  fairness | a globally consistent aggregate snapshot | ...].
```

Giá trị của mẫu này là **làm lộ các giả định** trước khi khách hàng sử dụng API. Khi một hạng mục không áp dụng (ví dụ class không có callback), không cần thêm section vô nghĩa vào Javadoc. Nhưng nếu API có operation blocking hoặc trả mutable value, những điểm đó cần được diễn đạt rõ.

## 26. Tổng kết và câu hỏi tự kiểm tra

**Câu 1:** Class có `synchronized void add(...)` và `synchronized int size()`. Client gọi `if (size() < max) add(x)` có bảo đảm không vượt max?

**Không.** Hai lời gọi được bảo vệ riêng, nhưng có khoảng xen kẽ. Cần một operation atomic gói cả check và update, như `tryAdd`.

**Câu 2:** `ConcurrentHashMap` thread-safe, vậy `map.get(key).add(value)` khi value là `ArrayList` có thread-safe không?

**Không tự động.** Contract map chỉ bảo vệ các operation trên map theo API; mutable value vẫn cần protection hoặc ownership riêng.

**Câu 3:** Một API gọi callback trên caller thread. Hai caller gọi `publish` cùng lúc có thể chạy cùng một callback đồng thời không?

**Có thể**, nếu implementation cho phép và không áp đặt serialization. Phải ghi rõ việc callback có thể concurrent, và người viết callback phải đảm bảo state của mình an toàn.

**Câu 4:** Javadoc ghi "returns an unmodifiable list" đã đủ để caller suy ra snapshot không đổi theo nguồn chưa?

**Chưa.** Unmodifiable *view* có thể phản ánh mutation của nguồn. Hãy ghi rõ live view hay independent snapshot, và semantics của mutable elements.

**Câu 5:** Một API thread-safe có thể block vô thời hạn không?

**Có.** Thread safety liên quan tính đúng của concurrent access; blocking/liveness là thuộc tính khác. Cần tài liệu riêng về chờ, timeout, interruption và lifecycle.

**Câu 6:** Vì sao annotation `@ThreadSafe` không thay cho Javadoc?

Vì annotation không tự xác định ranh giới atomicity, ordering, snapshot, callback, input ownership hoặc shutdown. Hơn nữa Java SE không cung cấp một annotation chuẩn duy nhất bắt buộc cho tất cả API.

**Câu 7:** Khi thay implementation từ lock sang atomic variable, có được giữ nguyên contract không?

**Được nếu** tất cả semantics đã hứa cho caller vẫn đúng, gồm atomicity, visibility, ordering, error behavior, lifecycle và output ownership. Contract mô tả điều caller được dựa vào, không cần cố định chi tiết khóa nội bộ.

Một public API hữu ích là API cho phép người gọi trả lời được: **tôi có thể gọi đồng thời hay không, thao tác nào là một đơn vị nguyên tử, kết quả nào được cam kết và nghĩa vụ đồng bộ nào thuộc về tôi?** Khi trả lời được các câu đó bằng Javadoc chính xác và implementation tuân thủ, thread-safety contract trở thành một công cụ ngăn race condition và bảo vệ khả năng thay thế implementation trong tương lai.