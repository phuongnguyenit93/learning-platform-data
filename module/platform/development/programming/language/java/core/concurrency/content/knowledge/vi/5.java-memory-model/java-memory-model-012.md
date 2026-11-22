# Double-checked locking và điều kiện dùng volatile trong Java

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

- Hiểu **double-checked locking (DCL)** là gì, giải thích hai lần kiểm tra `null` giải quyết những vấn đề khác nhau.
- Phân tích vai trò của **`synchronized`**, **`volatile`**, quan hệ *happens-before*, visibility, ordering và **safe publication** trong Java Memory Model (JMM).
- Viết đúng một bộ khởi tạo lazy sử dụng DCL trên **Java 17+**, biết lý do mẫu DCL không có `volatile` không được xem là an toàn theo JMM.
- Phân biệt **tránh tạo trùng đối tượng** với **công bố đối tượng đã xây dựng đầy đủ**; nhận ra vì sao chỉ `volatile` hoặc chỉ một lần kiểm tra ngoài khóa không đủ.
- Xác định **điều kiện áp dụng DCL**, giới hạn của mẫu thiết kế và những phương án đơn giản hơn như khởi tạo sớm, **initialization-on-demand holder**, enum và truy cập `synchronized`.
- Không nhầm DCL với bảo vệ trạng thái **mutable** trong đối tượng sau khi khởi tạo, hoặc cơ chế singleton trên nhiều JVM/process.

Phạm vi là **Java concurrency nói chung**. Bài không đề cập singleton container, lifecycle, dependency injection hoặc quản lý bean thuộc Spring.

## 2. Bài toán: lazy initialization dưới cạnh tranh

Giả sử một đối tượng dịch vụ có chi phí tạo đáng kể và chỉ cần khi được sử dụng lần đầu:

~~~java
// Đoạn minh họa đơn giản; chưa thread-safe:
private static Resource instance;

public static Resource getInstance() {
    if (instance == null) {
        instance = new Resource();
    }
    return instance;
}
~~~

Nếu hai thread cùng thấy `instance == null`, cả hai có thể tạo đối tượng. Ngoài chuyện **tạo trùng**, truy cập trường thông thường thiếu đồng bộ hóa còn có thể vi phạm yêu cầu **visibility** và **safe publication**.

Yêu cầu điển hình của một lazy singleton trong **một classloader của một JVM**:

1. Chưa tạo tài nguyên khi class được load, chỉ tạo ở lần sử dụng đầu tiên.
2. Dưới cạnh tranh, **chỉ một lần khởi tạo thành công** được công bố làm instance dùng chung.
3. Thread đọc được instance đã **được khởi tạo đúng**, thấy các ghi cần thiết từ quá trình xây dựng.
4. Sau khởi tạo, các lần gọi phổ biến không phải tranh chấp monitor mỗi lần.
5. Nếu constructor thất bại, không công bố một tham chiếu chưa có đối tượng hợp lệ.

DCL xuất phát từ yêu cầu **tránh lấy khóa ở đường truy cập nhanh sau khi khởi tạo**, trong khi vẫn khóa và kiểm tra lại khi thực sự cần tạo đối tượng.

Đừng dùng DCL chỉ vì có từ “singleton”: việc khởi tạo tài nguyên có side effect, thay đổi cấu hình, hủy/khởi tạo lại hoặc có nhiều chủ sở hữu cần hợp đồng riêng trước khi chọn mẫu này.

## 3. DCL đúng trong Java 17+

Mẫu thông dụng dùng **một trường static volatile**, **khóa cố định** và **hai lần kiểm tra giá trị null**:

~~~java
public final class LazyResource {
    private static volatile LazyResource instance;

    private final int value;

    private LazyResource() {
        value = 42;
    }

    public static LazyResource getInstance() {
        LazyResource result = instance; // Đọc volatile một lần.
        if (result == null) {           // Check 1: đường nhanh.
            synchronized (LazyResource.class) {
                result = instance;      // Đọc lại volatile dưới khóa.
                if (result == null) {   // Check 2: tránh tạo trùng.
                    result = new LazyResource();
                    instance = result;  // Ghi volatile: công bố instance.
                }
            }
        }
        return result;
    }

    public int value() {
        return value;
    }
}
~~~

Đây là **lớp hoàn chỉnh có thể biên dịch**, nhưng không phải ứng dụng chạy độc lập vì chưa có `main()`. Các ví dụ chương trình có `main()` xuất hiện ở phần tiếp theo.

Phân tích từng phần:

- **`private static volatile LazyResource instance`**: mọi thread truy cập đường DCL phải đọc/ghi cùng một trường volatile. Volatile tham gia đảm bảo visibility và ordering cần thiết cho việc công bố đối tượng trên JMM hiện đại.
- **`LazyResource result = instance`**: lấy snapshot từ đọc volatile. Dùng biến cục bộ để không phải đọc trường volatile nhiều lần trên đường thường gặp; đó là tối ưu nhỏ và làm luồng kiểm tra dễ hiểu.
- **`if (result == null)` đầu tiên**: nếu đã công bố instance, trả thẳng tham chiếu mà không phải lấy monitor.
- **`synchronized (LazyResource.class)`**: chỉ một thread tại một thời điểm có thể thực hiện phần khởi tạo được bảo vệ. Khóa này gắn với chính lớp, ổn định và được mọi thread dùng chung.
- **`result = instance` và `if (result == null)` bên trong**: sau khi một thread chờ lock, thread khác có thể đã tạo instance. Đọc lại volatile và kiểm tra lần hai để không tạo lại.
- **`new LazyResource()` trước `instance = result`**: constructor hoàn thành bình thường trước khi code thực hiện volatile write công bố tham chiếu. Thread khác quan sát tham chiếu từ volatile read tiếp theo có quan hệ happens-before phù hợp.
- **`return result`**: trả tham chiếu đã đọc hoặc khởi tạo, không cần thêm lần đọc volatile.

### Luồng cạnh tranh với hai thread

Giả sử cả A và B nhìn thấy `null` tại check 1:

~~~text
A: đọc instance == null
B: đọc instance == null
A: lấy monitor LazyResource.class
B: chờ monitor
A: đọc lại instance == null
A: new LazyResource() hoàn thành
A: ghi volatile instance = object
A: rời synchronized
B: lấy monitor
B: đọc lại instance -> object
B: check 2 thấy khác null, KHÔNG tạo thêm
B: trả cùng object
~~~

Nếu B vào khóa trước thì vai trò đảo lại; kết luận không đổi. Thread có thể chạy theo nhiều thứ tự, nhưng quy tắc khóa và check 2 giữ đúng việc tạo instance dùng chung.

DCL giải quyết **lazy initialization**. Nó không mặc nhiên làm mọi phương thức trong `LazyResource` thread-safe. Nếu đối tượng có trạng thái mutable sau khởi tạo, phần trạng thái ấy vẫn cần giao thức đồng bộ phù hợp.

## 4. Ba vấn đề khác nhau: mutual exclusion, publication và logic

Đừng đánh đồng những cơ chế này:

| Cơ chế | Nó bảo vệ điều gì? | Một mình có đủ cho DCL không? |
| --- | --- | --- |
| Check 1 ngoài khóa | Bỏ qua monitor khi instance đã sẵn sàng | Không: có thể hai thread cùng thấy null |
| `synchronized` quanh tạo instance | Mutual exclusion và thứ tự giữa các thread sử dụng **cùng khóa** | Không, nếu đường đọc nhanh ngoài khóa vẫn thiếu safe publication |
| Check 2 trong khóa | Không tạo trùng sau khi đã phải chờ thread khác tạo | Không, nếu reference công bố ngoài khóa không an toàn |
| `volatile instance` | Visibility, ordering và publish/read reference qua volatile | Không, nếu không bảo vệ quyết định “nếu null thì tạo” |
| `final` trong Resource | Ngữ nghĩa khởi tạo trường final khi đối tượng được xây dựng đúng | Không thay thế quy tắc tạo một instance và công bố đúng cho mọi trạng thái |

**Công thức của mẫu đúng:** volatile reference **và** critical section **và** hai lần kiểm tra. Bỏ bất kỳ phần nào phải có lập luận khác thay thế, chứ không thể dựa vào kết quả chạy thử.

## 5. Vì sao thiếu volatile là nguy hiểm?

Một phiên bản cũ thường thấy:

~~~java
// Mã minh họa lỗi, không dùng trong code concurrent:
private static Resource instance; // Thiếu volatile!

public static Resource getInstance() {
    if (instance == null) {
        synchronized (Singleton.class) {
            if (instance == null) {
                instance = new Resource();
            }
        }
    }
    return instance;
}
~~~

Đây là **mã giả minh họa nằm trong lớp tên Singleton**; `Resource` là kiểu giả định. Nó không phải file Java hoàn chỉnh có thể tự chạy.

Vấn đề: **đường đọc `instance` đầu tiên không đi qua cùng monitor**, cũng không đọc volatile. Vì thế việc thread tạo đối tượng đã ghi reference và việc thread khác đọc reference ngoài khóa **không được sắp thứ tự bằng happens-before** theo cách cần thiết. Thread đọc có thể quan sát dữ liệu không được công bố an toàn.

### “Thấy tham chiếu trước khi khởi tạo xong” nghĩa là gì?

Ta thường diễn tả bằng ba bước khái niệm:

~~~text
1. Cấp phát bộ nhớ cho Resource.
2. Gán dữ liệu/trạng thái khởi tạo của Resource.
3. Công bố địa chỉ đối tượng qua instance.
~~~

Đây **không phải ba câu lệnh bytecode cố định** của mọi constructor/JIT. Nó là cách diễn giải về quyền quan sát các hiệu ứng bộ nhớ. Khi thiếu ràng buộc JMM, một thread khác có thể nhìn thấy reference qua truy cập không đồng bộ nhưng không có bảo đảm nó quan sát đầy đủ trạng thái đã được thiết lập trong thread tạo.

Điều này đặc biệt quan trọng nếu Resource có các trường **không final** được constructor gán. JMM có các bảo đảm riêng cho **final fields** của đối tượng được xây dựng đúng cách, nhưng chúng không biến đoạn DCL thiếu volatile thành mẫu an toàn tổng quát, cũng không đảm bảo mọi trạng thái phụ thuộc và mọi yêu cầu singleton.

Không nên cố tạo một demo “lúc nào cũng in giá trị 0” để chứng minh lỗi này. Những lỗi do **publication/ordering** có thể không xuất hiện trong phần lớn lần chạy trên một CPU/JVM nhất định. **Thiếu happens-before đã đủ để bác bỏ tính đúng đắn**; việc một bài test pass không tạo ra bảo đảm JMM.

### Volatile write/read thiết lập happens-before

Theo quy tắc Java Memory Model, một **volatile write** tới một biến *happens-before* với các **volatile read kế tiếp của chính biến đó** trong synchronization order.

Khi thread A hoàn thành việc tạo object và ghi `instance = result` vào trường volatile:

1. Những ghi trước volatile write trong A, bao gồm khởi tạo object đúng cách, được sắp trước việc công bố theo program order.
2. Thread B đọc reference không-null từ cùng trường volatile sau đó có thứ tự nhớ cần thiết để thấy các hiệu ứng được công bố.
3. Những hành động sau volatile read trong B có thể dựa vào trạng thái được khởi tạo trước volatile write.

Diễn đạt theo sự kiện:

~~~text
Thread A                         Thread B
---------                        ---------
new Resource()
  constructor khởi tạo fields
volatile write: instance = r
          └──── happens-before ──> volatile read: r = instance
                                   đọc r.fields đã công bố
~~~

**Volatile ở trường chứa tham chiếu**, không phải cứ gắn volatile vào một trường bất kỳ trong Resource là đủ. Việc đặt `instance` volatile là phần thiết yếu của mẫu DCL chuẩn trong Java 17+.

## 6. Vì sao phải kiểm tra null lần hai?

Kể cả `instance` đã là volatile, cả A và B vẫn có thể cùng đọc `null` trước khi có thread nào ghi một tham chiếu hợp lệ. Nếu code chỉ kiểm tra ngoài khóa, rồi tạo đối tượng vô điều kiện khi vào khóa, sẽ có **hai lần tạo**.

Phiên bản thiếu check 2:

~~~java
// Minh họa lỗi logic:
if (instance == null) {
    synchronized (LockHolder.class) {
        instance = new Resource(); // Chưa kiểm tra lại sau khi chờ khóa.
    }
}
~~~

Đây là đoạn code minh họa, với `instance`, `LockHolder` và `Resource` cần được định nghĩa trong chương trình thật.

Vấn đề không nhất thiết là data race: ngay cả với reference volatile, các thao tác đọc/ghi riêng lẻ đúng hợp đồng bộ nhớ, **chuỗi check rồi khởi tạo vẫn bị race condition**. Check 2 biến việc kiểm tra và quyết định tạo thành một critical section thống nhất.

### Ví dụ chạy được: thiếu check 2 vẫn khởi tạo hai lần

Dùng latch để cả hai worker đều vượt qua check ngoài trước khi thread nào được tạo object. Nhờ vậy ví dụ có kết quả xác định, tránh suy luận từ thời gian `sleep()`.

Tệp **MissingSecondCheckDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class MissingSecondCheckDemo {
    private static volatile Resource instance;
    private static final CountDownLatch bothSawNull = new CountDownLatch(2);
    private static final AtomicInteger created = new AtomicInteger();

    static final class Resource {
        final int id;

        Resource(int id) {
            this.id = id;
        }
    }

    static Resource getInstance() throws InterruptedException {
        Resource result = instance;
        if (result == null) {
            bothSawNull.countDown();
            bothSawNull.await();

            synchronized (MissingSecondCheckDemo.class) {
                // Sai: thiếu kiểm tra lại instance ở trong khóa.
                result = new Resource(created.incrementAndGet());
                instance = result;
            }
        }
        return result;
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Resource> first =
                    pool.submit(MissingSecondCheckDemo::getInstance);
            Future<Resource> second =
                    pool.submit(MissingSecondCheckDemo::getInstance);

            Resource one = first.get();
            Resource two = second.get();

            System.out.println("constructed = " + created.get());
            System.out.println("same instance = " + (one == two));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 MissingSecondCheckDemo.java
java MissingSecondCheckDemo
~~~

Stdout:

~~~text
constructed = 2
same instance = false
~~~

**Vì sao chắc chắn?** Thread đầu đã đọc null phải chờ `bothSawNull` đạt 0 trước khi tạo object; thread thứ hai vì vậy cũng đọc null. Sau đó hai thread lần lượt lấy monitor, **nhưng không kiểm tra lại**, nên mỗi thread tạo một Resource khác nhau. `result` là biến cục bộ lưu riêng object mỗi thread vừa tạo, vì thế hai kết quả từ Future là hai reference khác nhau.

- `volatile` chỉ giữ hợp đồng bộ nhớ cho reference.
- `synchronized` đảm bảo mỗi lần khởi tạo ở trong monitor không diễn ra cùng lúc.
- Thiếu check 2 vẫn cho phép **hai lần khởi tạo nối tiếp** sau khi cả hai đã đi qua check 1.

Trong ví dụ có latch, đó là **công cụ kiểm soát lịch test để tái hiện lỗi**, không phải một phần cần dùng trong implementation DCL đúng.

## 7. Ví dụ DCL hoàn chỉnh có thể chạy trên Java 17+

Dưới đây là bản runnable áp dụng cả ba điều kiện: volatile, khóa, kiểm tra lại null. Ví dụ dùng các thread đồng thời nhưng kết quả cuối vẫn xác định.

Tệp **VolatileDclDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class VolatileDclDemo {
    private static volatile Resource instance;
    private static final AtomicInteger constructions = new AtomicInteger();

    static final class Resource {
        final int value;

        Resource(int value) {
            this.value = value;
            constructions.incrementAndGet();
        }
    }

    static Resource getInstance() {
        Resource result = instance;
        if (result == null) {
            synchronized (VolatileDclDemo.class) {
                result = instance;
                if (result == null) {
                    result = new Resource(42);
                    instance = result;
                }
            }
        }
        return result;
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch start = new CountDownLatch(1);
        AtomicReference<Resource> first = new AtomicReference<>();
        AtomicReference<Resource> second = new AtomicReference<>();

        Thread a = new Thread(() -> {
            try {
                start.await();
                first.set(getInstance());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "caller-a");

        Thread b = new Thread(() -> {
            try {
                start.await();
                second.set(getInstance());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "caller-b");

        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        System.out.println("constructed = " + constructions.get());
        System.out.println("same instance = " + (first.get() == second.get()));
        System.out.println("value = " + first.get().value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 VolatileDclDemo.java
java VolatileDclDemo
~~~

Stdout trong điều kiện chạy bình thường, không có yêu cầu interrupt từ ngoài:

~~~text
constructed = 1
same instance = true
value = 42
~~~

**Lập luận chính xác:**

1. `start.await()` chỉ điều phối điểm bắt đầu của hai worker; nó không bắt buộc hai thread cùng thấy null. DCL phải đúng dù một thread tới trước hay cả hai tới cùng lúc.
2. Cả hai đọc `instance` thông qua volatile.
3. Thread giành monitor trước tạo object một lần rồi ghi `instance` volatile.
4. Thread vào monitor sau đọc lại `instance`; thấy object đã công bố và không tạo thêm.
5. `join()` khiến main chờ hai worker kết thúc rồi quan sát kết quả. `AtomicReference` và `AtomicInteger` cũng cung cấp các thao tác chia sẻ thread-safe cho dữ liệu quan sát.
6. `Resource.value` là final và được đặt trong constructor trước lúc công bố reference; chương trình không sửa đối tượng sau khởi tạo.

Với demo xử lý nghiệp vụ thật, nên truyền lỗi từ worker về caller hoặc ghi nhận trạng thái lỗi; ví dụ này tập trung vào quy tắc công bố instance khi không có interrupt hay exception bất thường.

### Lưu ý về exception khi khởi tạo

Nếu `new Resource(...)` ném exception **trước câu lệnh gán** `instance = result`, bản DCL trên không công bố object thất bại; `instance` vẫn null và lần gọi sau có thể thử tạo lại. Có thể cần chính sách cụ thể nếu khởi tạo có side effect đã xảy ra một phần, hoặc nếu lỗi không nên được retry.

DCL không tạo tính nguyên tử cho các side effect ngoài constructor (ví dụ ghi file, tạo kết nối từ xa, gọi dịch vụ). Hãy thiết kế cleanup, retry và idempotency khi những yêu cầu đó thực sự có mặt.

## 8. Điều kiện áp dụng volatile trong DCL

### 8.1. Reference phải volatile trong mô hình DCL chuẩn

Trong Java 17+, lựa chọn đơn giản và rõ ràng là:

~~~java
private static volatile Resource instance;
~~~

Toàn bộ đường đọc ngoài khóa, đọc lại trong khóa và ghi công bố phải dùng cùng trường đó. Nếu có cache tham chiếu ở một trường **không volatile** hay đọc qua đường tắt khác, cần phân tích lại happens-before cho đường ấy.

### 8.2. Đừng để this thoát khỏi constructor

Ví dụ dưới đây là **anti-pattern** minh họa, không phải chương trình độc lập:

~~~java
class EscapingResource {
    EscapingResource(EventBus bus) {
        bus.register(this); // this bị công bố ra ngoài trong constructor!
        // Các bước khởi tạo quan trọng có thể chưa xong.
    }
}
~~~

`EventBus` là kiểu giả định. Đây là vấn đề **this escape**: thread khác có thể nhận reference trước khi constructor hoàn thành thông qua kênh công bố khác. DCL chỉ công bố instance **sau khi constructor trả về**, nhưng nó không sửa được việc constructor tự gửi `this` sang thread khác sớm hơn.

Một thiết kế tốt cần xây dựng đối tượng đầy đủ trước khi chia sẻ; tránh gọi callback, đăng ký listener làm lộ `this`, hoặc khởi chạy thread từ constructor nếu chúng có thể dùng trạng thái chưa hoàn chỉnh.

### 8.3. Volatile không bảo vệ trạng thái mutable sau khởi tạo

Giả sử singleton có field:

~~~java
final class CounterService {
    int count;

    void increment() {
        count++;
    }
}
~~~

Đây là một lớp minh họa không có `main()`. Nếu được công bố bằng DCL volatile, đối tượng có thể **được tạo và công bố an toàn**, nhưng hai thread gọi `increment()` đồng thời vẫn có data race trên `count` và có thể mất cập nhật.

Muốn an toàn cho `count`, phải dùng khóa, atomic counter hoặc thiết kế không mutable state. **Volatile của reference chỉ bảo đảm publication**, không “lây” tính thread-safe cho tất cả phương thức, cấu trúc dữ liệu hay trường bên trong đối tượng.

Tương tự, nếu cấu hình được thay đổi sau khởi tạo, việc giữ reference volatile **không tự khiến nhiều field trong cấu hình được cập nhật nguyên tử như một snapshot**. Khi cần thay đổi toàn cấu hình, có thể tạo **đối tượng immutable mới** rồi công bố toàn reference qua một volatile/AtomicReference; đó là mô hình khác với lazy DCL tạo instance duy nhất.

### 8.4. Final fields hỗ trợ thiết kế immutable nhưng không thay thế DCL

Đánh dấu các thành phần trạng thái của Resource là `final` và không sửa chúng sau constructor giúp dễ suy luận. Tuy nhiên:

- `final` có ngữ nghĩa đặc biệt trong JMM khi object được xây dựng đúng, nhưng không tự bảo đảm **chỉ một thread tạo object**.
- Một reference final tại nơi khác không biến **check-null-then-create** trên field thường thành nguyên tử.
- Mutable object được trỏ từ final field vẫn cần bảo vệ nếu có nhiều thread cập nhật nó.

### 8.5. Nếu không cần lazy, đừng sử dụng DCL

Nếu chi phí khởi tạo thấp và việc tạo tài nguyên không cần trì hoãn, dùng khởi tạo static/class initialization thường đơn giản hơn. DCL có nhiều điều kiện hơn, dễ bị sửa sai và cần bài test/invariant rõ ràng.

## 9. Các phương án thay thế đơn giản hơn

### 9.1. Khởi tạo sớm bằng static final

~~~java
public final class EagerSingleton {
    private static final EagerSingleton INSTANCE = new EagerSingleton();

    private EagerSingleton() {}

    public static EagerSingleton getInstance() {
        return INSTANCE;
    }
}
~~~

Đây là lớp hoàn chỉnh có thể biên dịch. **JVM class initialization** có bảo đảm đồng bộ hóa cho việc khởi tạo class. Đối tượng được tạo khi class được khởi tạo, không nhất thiết vào đúng thời điểm पहली tiên gọi `getInstance()`, và không có kiểm tra null trong getter.

Ưu điểm: ít mã, khó mắc lỗi về publication. Nhược điểm: tạo object khi class được khởi tạo, có thể sớm hơn lúc tài nguyên thật sự cần.

### 9.2. Initialization-on-demand holder

Đây là cách thường được ưu tiên cho lazy singleton **static**, khi không cần tùy biến chính sách khởi tạo:

Tệp **HolderSingletonDemo.java**:

~~~java
public class HolderSingletonDemo {
    static final class Resource {
        final int value;

        Resource(int value) {
            this.value = value;
        }
    }

    private static final class Holder {
        static final Resource INSTANCE = new Resource(42);
    }

    static Resource getInstance() {
        return Holder.INSTANCE;
    }

    public static void main(String[] args) {
        Resource first = getInstance();
        Resource second = getInstance();

        System.out.println("same instance = " + (first == second));
        System.out.println("value = " + first.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 HolderSingletonDemo.java
java HolderSingletonDemo
~~~

Stdout:

~~~text
same instance = true
value = 42
~~~

**Cơ chế:** class `Holder` được khởi tạo khi lần đầu sử dụng trường static không phải constant variable `INSTANCE`. Quy tắc class initialization của JVM bảo đảm an toàn trước nhiều thread mà code người dùng không phải tự viết khóa hoặc volatile. Lần gọi sau chỉ đọc tham chiếu đã được khởi tạo.

Giới hạn: đây vẫn là **một instance theo classloader đã khởi tạo class tương ứng**, không phải singleton toàn bộ hệ thống phân tán. Nếu initialization của holder thất bại theo cơ chế khởi tạo class, JLS có hành vi lỗi khởi tạo riêng; không giống mọi lần gọi DCL đều thử constructor lại.

### 9.3. Enum singleton

Tệp **EnumSingletonDemo.java**:

~~~java
public class EnumSingletonDemo {
    enum Service {
        INSTANCE;

        int calculate() {
            return 6 * 7;
        }
    }

    public static void main(String[] args) {
        Service first = Service.INSTANCE;
        Service second = Service.INSTANCE;

        System.out.println("same instance = " + (first == second));
        System.out.println("value = " + first.calculate());
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumSingletonDemo.java
java EnumSingletonDemo
~~~

Stdout:

~~~text
same instance = true
value = 42
~~~

Enum có cơ chế khởi tạo do JVM quản lý, đồng thời có hành vi serialization dành riêng cho enum. Đây thường là lựa chọn tốt nếu cần một instance cho một enum type và không có yêu cầu kế thừa lớp thông thường. Như các lựa chọn singleton khác, các trường mutable bên trong enum vẫn cần bảo vệ khi truy cập đồng thời.

### 9.4. Getter synchronized đơn giản

~~~java
public final class SynchronizedSingleton {
    private static SynchronizedSingleton instance;

    private SynchronizedSingleton() {}

    public static synchronized SynchronizedSingleton getInstance() {
        if (instance == null) {
            instance = new SynchronizedSingleton();
        }
        return instance;
    }
}
~~~

Lớp này có thể biên dịch độc lập; không có `main()`. Vì **mọi lần gọi getter đều phải qua cùng monitor**, code có mutual exclusion và quy tắc happens-before mà không cần volatile riêng cho `instance`.

Ưu điểm là rõ ràng, dễ bảo trì. Nhược điểm là phải vào `synchronized` ở mọi lần gọi, dù singleton đã được tạo. Không tự đoán chi phí này là đáng kể: hãy đo trong bối cảnh ứng dụng thật nếu hiệu năng là một yêu cầu có chứng cứ.

## 10. Bảng lựa chọn: DCL và các phương án khác

| Cách | Lazy theo lần dùng đầu? | Cơ chế an toàn khi công bố | Chi phí/độ phức tạp | Khi nào chọn |
| --- | --- | --- | --- | --- |
| Static final/eager | Không cần chờ getter; khởi tạo khi class initialization | JVM class initialization | Đơn giản | Tạo sớm chấp nhận được |
| Holder idiom | Có, theo lần dùng Holder | JVM class initialization | Đơn giản | Lazy singleton static thông thường |
| Enum singleton | Theo initialization của enum | JVM class initialization; semantics enum | Đơn giản | Singleton biểu diễn bằng enum phù hợp |
| Synchronized getter | Có | Monitor mỗi lần gọi | Dễ hiểu, có khóa lặp lại | Getter không cần tối ưu đường nhanh |
| Volatile DCL | Có | Volatile write/read + monitor + check 2 | Phức tạp hơn | Cần lazy và đường đọc sau khởi tạo không khóa |

**Quy tắc quyết định thực tế:**

1. Có thật sự cần khởi tạo lazy không? Nếu không, xem static final.
2. Có cần một instance static với constructor không tham số hoặc tự quản lý được không? Xem Holder.
3. Có thể mô hình hóa singleton bằng enum mà không vướng ràng buộc class/API không? Xem enum.
4. Getter được gọi đủ nhiều để chi phí monitor có ý nghĩa trong đo đạc không? Nếu chưa, synchronized getter thường đủ.
5. Nếu vẫn cần DCL, dùng mẫu đầy đủ **volatile + check 1 + lock + check 2 + publish** và document invariant.

## 11. Các lỗi thường gặp khi dùng DCL

| Cách viết/lập luận sai | Vấn đề | Cách sửa |
| --- | --- | --- |
| `instance` là field thông thường | Đường đọc ngoài khóa thiếu safe publication | Cho reference thành `volatile` hoặc chọn phương án có toàn bộ truy cập đồng bộ hóa |
| Chỉ kiểm tra `null` ngoài khóa | Nhiều thread vượt check và tạo nhiều object | Kiểm tra lại **bên trong** cùng monitor |
| Chỉ dùng `volatile` và `if (null) new` | Volatile không làm check–then–act nguyên tử | Thêm đồng bộ hóa/CAS đúng quy tắc |
| Đọc/ghi qua các lock khác nhau | Không có mutual exclusion chung cho khởi tạo | Dùng **cùng một monitor cố định** |
| Đưa `this` ra callback trong constructor | Có thể bị quan sát trước khi hoàn tất xây dựng | Tránh `this escape` |
| Khởi tạo xong rồi cập nhật các trường thường từ nhiều thread | DCL chỉ bảo vệ công bố ban đầu | Tách đồng bộ hóa cho trạng thái mutable |
| Suy ra DCL đúng vì test 1.000 lần không lỗi | Các lịch lỗi có thể hiếm, JIT/CPU khác nhau | Lập luận theo JMM, invariant và kiểm thử có kiểm soát |
| Dùng `Thread.sleep()` trước khi đọc `instance` | Sleep không tạo happens-before cho reference | Dùng volatile/synchronized/class initialization |
| Khởi tạo object rồi thay instance trong lúc chạy nhưng vẫn coi là singleton cố định | Luật lifetime khác hẳn lazy DCL | Thiết kế reload, version, atomic swap riêng |
| Nghĩ singleton là một instance cho cả nhiều JVM | Mỗi process/classloader có phạm vi trạng thái riêng | Dùng coordination ngoài JVM nếu cần một tài nguyên toàn hệ thống |

### Có thể sửa DCL không volatile bằng cách khóa chỉ khi null?

Không. Vấn đề nằm ở **đường đọc nhanh không khóa**: dù constructor/ghi reference diễn ra trong synchronized, thread đọc khi `instance != null` vẫn bỏ qua monitor, nên không nhận được bảo đảm đọc cùng khóa. Nếu không muốn volatile, mọi đường đọc dùng cùng monitor (như synchronized getter) hoặc dùng class initialization đúng hợp đồng.

### Có nên dùng `AtomicReference` thay `volatile`?

`AtomicReference` hỗ trợ đọc/ghi và CAS nguyên tử, nhưng **không tự biến một phép “nếu null thì tạo đối tượng” thành đúng một lần gọi constructor**. Ví dụ hai thread cùng tạo candidate rồi một CAS thắng: reference công bố cuối có thể chỉ có một nhưng **constructor đã chạy hai lần**. Nếu constructor có side effect hoặc việc tạo rất đắt, điều đó có thể vi phạm yêu cầu.

DCL dùng synchronized để **chặn việc tạo trùng**, không chỉ chọn reference chiến thắng. Nếu dùng CAS cần phân tích cả side effect của tạo candidate và policy bỏ candidate thua.

### Volatile có ngăn dữ liệu bị thay đổi đồng thời không?

Không. Nó cung cấp visibility/ordering cho field và đọc/ghi riêng lẻ đúng với hợp đồng, nhưng không làm một giao dịch trên nhiều trường trở nên nguyên tử. Ví dụ `volatile int count; count++;` vẫn có read–modify–write race. Nếu singleton quản lý bộ đếm, hãy dùng AtomicInteger hoặc khóa bảo vệ hành động đó.

## 12. Những giới hạn cần biết

### Phạm vi “một instance”

Một trường `static` thuộc về class được định nghĩa bởi **classloader** trong một JVM. Các classloader khác nhau có thể nạp các bản định nghĩa class riêng, nên DCL không bảo đảm “duy nhất toàn hệ thống”. Nhiều process, container hay instance ứng dụng cũng có trạng thái riêng.

Nếu cần **một công việc toàn hệ thống**, một khóa cục bộ Java hoặc singleton không đủ: phải thiết kế cơ chế coordination ở mức nguồn dữ liệu chung/hạ tầng tương ứng. Đây là nguyên tắc Java concurrency tổng quát, không phải cơ chế của một framework cụ thể.

### Constructor, callback và vòng phụ thuộc

DCL chỉ đơn giản khi constructor hoàn tất trước publication và không vòng phụ thuộc. Nếu `Resource` tự gọi lại `getInstance()` trong constructor, hoặc gọi dependency cũng gọi ngược lại singleton này, có thể xảy ra recursion, vòng khởi tạo hoặc trạng thái chưa được công bố. Đồng bộ hóa không tự giải quyết vòng phụ thuộc logic.

Nếu constructor tạo thread phụ hoặc phát callback tham chiếu `this`, thread khác có thể quan sát object trước khi constructor kết thúc. Hạn chế làm việc có side effect trong constructor và tách bước start/registration khi cần.

### Reflection, serialization và cloning

DCL thông thường chỉ đảm bảo đường **`getInstance()`** không tạo trùng trong cùng phạm vi lớp/khóa. Nếu lớp có các đường khởi tạo hay sao chép khác (constructor truy cập từ nơi khác, serialization không xử lý singleton, clone...), những đường đó phải được xem xét độc lập nếu “một instance” là yêu cầu chặt. Enum giúp quản lý một số vấn đề thuộc ngữ nghĩa enum, nhưng lựa chọn cần phù hợp API đang thiết kế.

### Retry khi initialization thất bại

Nếu constructor ném exception, DCL không gán reference và lần gọi tiếp có thể thử lại. Nhưng nếu đã tạo tài nguyên bên ngoài trước khi lỗi, lần sau có thể tạo thêm side effect. Trước khi áp dụng lazy initialization cho tài nguyên quan trọng, hãy quyết định: **retry, lưu lỗi, đóng tài nguyên từng phần, hay coi lỗi là không thể phục hồi**. DCL không tự có chính sách này.

## 13. Kiểm thử DCL như thế nào?

**Kiểm thử có ích:**

1. Đặt đếm trong constructor qua **AtomicInteger**, tạo nhiều thread cùng gọi getter và kiểm tra số lần tạo bằng 1 khi các lời gọi thành công.
2. Dùng **CountDownLatch** hoặc barrier để tăng cạnh tranh tại cùng một mốc (không dựa vào `sleep()`).
3. So sánh reference trả về bằng **`==`** khi hợp đồng yêu cầu cùng instance trong một classloader.
4. Kiểm tra các field được constructor thiết lập trước công bố và chạy các phương thức theo hợp đồng.
5. Test lỗi constructor, retry và cleanup nếu code có yêu cầu xử lý lỗi.
6. Khi có mutable state, test riêng đường đọc/ghi cạnh tranh của chính state ấy; không xem test singleton là test thread safety của object.

**Kiểm thử không thể chứng minh** mọi lịch trên mọi JVM/CPU đều đúng. Kết luận an toàn phải dựa vào cấu trúc đồng bộ hóa và quy tắc JMM. Demo `MissingSecondCheckDemo` tái hiện một lỗi logic bằng điều phối có chủ đích; còn lỗi missing volatile thường không thể dựa vào một stdout bắt buộc để chứng minh trong runtime cụ thể.

Nếu dùng benchmark đo `synchronized` so với DCL, cần công cụ đo phù hợp, thời gian warmup/JIT, phân biệt throughput và latency. Chi phí tối ưu hóa chỉ có ý nghĩa khi được đo, không nên đánh đổi tính đúng đắn lấy suy đoán.

## 14. Câu hỏi tự kiểm tra

**1. Vì sao cần `volatile` dù có `synchronized`?**  
Vì đường đọc nhanh có thể không lấy khóa. Volatile mang hợp đồng publication và visibility cho các thread nhìn thấy reference ngoài synchronized.

**2. Vì sao check 2 vẫn bắt buộc khi instance volatile?**  
Hai thread có thể cùng đọc null trước khi một thread công bố instance. Sau khi chờ khóa, phải đọc lại reference để tránh tạo trùng.

**3. Nếu dùng `private static final Resource INSTANCE = new Resource()`, có cần DCL không?**  
Không. JVM class initialization đã quản lý an toàn việc khởi tạo static; đổi lại instance có thể được tạo lúc class initialization thay vì lúc getter được gọi.

**4. Nếu singleton có trường `int count` và nhiều thread cùng gọi `count++`, DCL volatile có bảo vệ giá trị count không?**  
Không. DCL bảo vệ công bố reference ban đầu. Counter mutable cần atomicity/synchronization riêng.

**5. Nếu constructor thất bại trước câu lệnh `instance = result`, DCL có lưu một object thành công không?**  
Không; câu lệnh volatile write chưa chạy. Lần gọi sau có thể thử lại, nhưng side effect dở dang cần chính sách cleanup/retry riêng.

**6. Có thể thay synchronized bằng CAS trên một AtomicReference để chắc chắn constructor chỉ chạy một lần?**  
Không nhất thiết. Nhiều thread có thể tạo candidate trước CAS, dù chỉ một candidate được công bố.

**7. Một singleton trong một JVM có đồng nghĩa một singleton trong toàn hệ thống không?**  
Không. Process và classloader khác nhau có thể có các instance riêng. DCL chỉ bảo vệ phạm vi trường static/monitor tương ứng.

**8. Khi nào holder idiom phù hợp hơn DCL?**  
Khi cần một lazy static singleton thông thường và không cần tự kiểm soát đường khởi tạo bằng lock/policy đặc biệt. JVM class initialization cung cấp thread safety với mã ít hơn.

## 15. Ghi nhớ

Đối với mẫu **double-checked locking chuẩn trên Java 17+**, ba điều kiện đi cùng nhau là **trường instance volatile**, **một monitor chung khi khởi tạo**, và **kiểm tra lại null sau khi đã lấy khóa**. Volatile xử lý phần **safe publication/visibility**; synchronized và check 2 xử lý phần **không tạo trùng trong cạnh tranh**. DCL chỉ đảm bảo khởi tạo và công bố reference ban đầu; an toàn của trạng thái mutable, tài nguyên ngoài JVM và lifecycle phức tạp phải được thiết kế riêng.

Khi không có yêu cầu rõ ràng khiến DCL hữu ích, cân nhắc **holder**, **enum** hoặc **khởi tạo static** để giảm độ phức tạp và giảm nguy cơ sửa sai.
