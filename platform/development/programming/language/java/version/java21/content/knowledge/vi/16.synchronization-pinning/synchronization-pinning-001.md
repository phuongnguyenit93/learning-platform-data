# Thread safety và Java Memory Model vẫn áp dụng với virtual thread

Virtual thread thay đổi cách JVM quản lý và lập lịch thread, nhưng không thay đổi các quy tắc an toàn luồng của Java. Một virtual thread vẫn đọc và ghi bộ nhớ dùng chung, vẫn có thể tạo data race và vẫn cần đồng bộ hóa khi nhiều tác vụ truy cập trạng thái mutable.

Các quy tắc của Java Memory Model (JMM) tiếp tục áp dụng: visibility, atomicity và ordering vẫn phải được bảo đảm bằng những cơ chế như synchronized, volatile, khóa, biến atomic hoặc cấu trúc dữ liệu concurrent. Việc một virtual thread được unmount khỏi carrier thread rồi mount lên carrier khác không tự tạo ra quan hệ happens-before.

## 1. Virtual thread không thay đổi Java Memory Model

Virtual thread là một đối tượng Thread do JVM lập lịch trên platform thread. Trong khi chạy, nó có thể được mount trên một carrier thread; khi thực hiện thao tác blocking có thể unmount, nó tạm nhường carrier để tác vụ khác chạy.

Việc mount/unmount là chi tiết lập lịch. Chương trình không được dựa vào nó để suy ra rằng dữ liệu đã được ghi sẽ tự động nhìn thấy ở thread khác. Quy tắc bộ nhớ vẫn dựa trên các quan hệ được JMM định nghĩa:

- **Visibility:** một thread nhìn thấy các ghi dữ liệu của thread khác khi có quan hệ đồng bộ thích hợp.
- **Atomicity:** một thao tác cần được xem là không thể chia cắt phải được bảo vệ bằng cơ chế phù hợp.
- **Ordering:** trình biên dịch, CPU và JVM có thể sắp xếp lại thao tác nếu không làm thay đổi hành vi được JMM bảo đảm; cần dùng quan hệ happens-before khi thứ tự quan sát có ý nghĩa.

Một virtual thread riêng cho mỗi request giúp cô lập luồng điều khiển và dữ liệu cục bộ của tác vụ. Nó không tự bảo vệ singleton, cache, collection hoặc object mutable được nhiều tác vụ cùng tham chiếu.

## 2. Data race vẫn xảy ra với virtual thread

Ví dụ sau có lỗi race condition:

~~~java
final class Counter {
    private int value;

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}
~~~

Toán tử value++ không phải một thao tác nguyên tử. Về bản chất, nó đọc giá trị, cộng một rồi ghi kết quả. Nếu hai virtual thread cùng thực hiện thao tác này, cả hai có thể đọc cùng một giá trị cũ và ghi đè kết quả của nhau.

~~~java
var counter = new Counter();

try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    List<Future<?>> tasks = IntStream.range(0, 10_000)
            .mapToObj(ignored -> executor.submit(counter::increment))
            .toList();

    for (Future<?> task : tasks) {
        task.get();
    }
}

System.out.println(counter.value()); // Không được bảo đảm là 10_000
~~~

Chờ tất cả Future hoàn tất bảo đảm các tác vụ đã kết thúc trước khi đọc kết quả, nhưng không làm cho những lần tăng counter trở thành nguyên tử. Đồng bộ hóa phải được đặt tại thao tác cập nhật dùng chung.

## 3. Bảo vệ trạng thái mutable bằng synchronized

synchronized vẫn cung cấp mutual exclusion và memory visibility như trước. Các virtual thread tranh cùng một monitor vẫn phải tuân theo cùng một quy tắc khóa:

~~~java
final class SafeCounter {
    private int value;

    synchronized void increment() {
        value++;
    }

    synchronized int value() {
        return value;
    }
}
~~~

Khi một thread thoát khỏi synchronized block hoặc method trên một monitor, thao tác unlock đó happens-before một lần lock tiếp theo trên cùng monitor. Vì vậy, các lần cập nhật được tuần tự hóa và thread lấy khóa sau có thể nhìn thấy những ghi trước đó.

Có thể dùng cùng một object làm khóa trong một block:

~~~java
final class Inventory {
    private final Object lock = new Object();
    private int available = 10;

    boolean reserve(int quantity) {
        synchronized (lock) {
            if (quantity <= 0 || available < quantity) {
                return false;
            }
            available -= quantity;
            return true;
        }
    }
}
~~~

Điều quan trọng là tất cả đường đọc và ghi cần phối hợp phải dùng cùng một quy tắc đồng bộ hóa. Nếu một method đọc available bên ngoài khóa trong khi method khác cập nhật bên trong khóa, việc khóa một phía không đủ để bảo đảm visibility và tính nhất quán.

## 4. Dùng volatile khi cần visibility, không cần thao tác ghép

volatile phù hợp khi một thread công bố một giá trị và các thread khác chỉ cần quan sát giá trị mới, với điều kiện thao tác không đòi hỏi một chuỗi đọc-sửa-ghi nguyên tử.

~~~java
final class StopSignal {
    private volatile boolean stopped;

    void requestStop() {
        stopped = true;
    }

    void runTask() {
        while (!stopped) {
            doOneUnitOfWork();
        }
    }

    private void doOneUnitOfWork() {
        // Thực hiện một phần công việc ngắn.
    }
}
~~~

Ghi vào một volatile field happens-before những lần đọc tiếp theo của chính field đó. Vì vậy, runTask() có thể quan sát yêu cầu dừng được công bố qua requestStop().

Tuy nhiên, volatile không biến value++ thành nguyên tử:

~~~java
private volatile int count;

void increment() {
    count++; // Vẫn là thao tác đọc-sửa-ghi, có thể mất cập nhật.
}
~~~

Nếu cần cập nhật nguyên tử một giá trị đơn, dùng AtomicInteger, AtomicLong hoặc cơ chế khóa phù hợp.

## 5. Atomic và các cấu trúc concurrent

Với bộ đếm đơn giản, AtomicInteger cung cấp các phép cập nhật nguyên tử:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger();

try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    List<Future<Integer>> tasks = IntStream.range(0, 10_000)
            .mapToObj(ignored -> executor.submit(
                    () -> {
                        return counter.incrementAndGet();
                    }))
            .toList();

    for (Future<?> task : tasks) {
        task.get();
    }
}

System.out.println(counter.get()); // 10000
~~~

Nếu có rất nhiều cập nhật cạnh tranh và chỉ cần tổng cuối cùng, LongAdder có thể giảm contention trong một số workload:

~~~java
LongAdder requests = new LongAdder();

void recordRequest() {
    requests.increment();
}

long totalRequests() {
    return requests.sum();
}
~~~

LongAdder.sum() không phải snapshot nguyên tử đối với các cập nhật đồng thời đang diễn ra; nó phù hợp với thống kê và tổng hợp, không thay thế AtomicLong khi cần một giá trị tuyến tính hóa cho logic nghiệp vụ.

Khi nhiều tác vụ thao tác trên map hoặc set dùng chung, hãy cân nhắc ConcurrentHashMap hoặc cấu trúc concurrent thích hợp. Các collection này cung cấp bảo đảm đồng thời cho những thao tác được tài liệu hóa, nhưng không tự làm cho một chuỗi nhiều thao tác riêng lẻ trở thành giao dịch nguyên tử.

Ví dụ, mẫu kiểm tra rồi thêm sau đây không an toàn khi nhiều thread cùng chạy:

~~~java
if (!map.containsKey(key)) {
    map.put(key, value);
}
~~~

Với ConcurrentHashMap, dùng một thao tác kết hợp như putIfAbsent() nếu đó là ý định:

~~~java
map.putIfAbsent(key, value);
~~~

## 6. Happens-before khi khởi chạy và chờ tác vụ

JMM định nghĩa các quan hệ đồng bộ hóa không phụ thuộc thread là platform hay virtual:

| Quan hệ | Bảo đảm |
|---|---|
| Ghi dữ liệu trước Thread.start() | Happens-before các thao tác trong thread được khởi chạy |
| Các thao tác trong một thread trước khi thread kết thúc | Happens-before thread khác phát hiện thread kết thúc qua join() thành công |
| Unlock monitor | Happens-before lần lock tiếp theo trên cùng monitor |
| Ghi volatile field | Happens-before lần đọc tiếp theo của cùng field |
| Hành động trước khi submit tác vụ vào Executor | Happens-before hành động của tác vụ |
| Hành động trong tác vụ | Happens-before thao tác lấy kết quả thành công qua Future.get() |

Ví dụ, sau khi Future.get() trả về thành công, thread nhận kết quả có thể quan sát các ghi mà tác vụ đã thực hiện trước khi hoàn tất theo bảo đảm memory consistency của Future. Nhưng nếu nhiều tác vụ cùng cập nhật một biến mutable, chúng vẫn cần phối hợp để tránh race giữa chính các tác vụ đó.

Không dùng Thread.sleep() hoặc Thread.yield() để cố làm cho một ghi dữ liệu trở nên nhìn thấy ở thread khác. Hai lời gọi này không tạo quan hệ happens-before.

## 7. Chia sẻ dữ liệu và thread confinement

Một cách đơn giản để giảm nhu cầu đồng bộ hóa là để mỗi tác vụ sở hữu dữ liệu mutable riêng:

~~~java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<Result> result = executor.submit(() -> {
        var localBuffer = new StringBuilder();
        localBuffer.append("request data");
        return process(localBuffer.toString());
    });

    Result value = result.get();
}
~~~

localBuffer chỉ được tác vụ sử dụng, nên không cần khóa để bảo vệ nó. Cách này gọi là thread confinement: trạng thái mutable được giới hạn trong một thread hoặc một tác vụ và không bị chia sẻ đồng thời.

Khi dữ liệu cần được chuyển giữa các tác vụ, ưu tiên truyền object bất biến hoặc bản sao có quyền sở hữu rõ ràng. Nếu chia sẻ object mutable, phải xác định rõ ai được phép đọc, ai được phép ghi và cơ chế đồng bộ hóa nào bảo vệ nó.

Virtual thread phù hợp với mô hình một tác vụ trên một thread, nhưng không nên dùng ThreadLocal như một cách tạo pool tài nguyên. Số virtual thread có thể lớn, vì vậy một object lớn hoặc tài nguyên đắt tiền trong mỗi ThreadLocal có thể làm tăng đáng kể bộ nhớ và số tài nguyên được giữ. Dùng pool có giới hạn hoặc truyền dependency tường minh khi cần chia sẻ tài nguyên.

## 8. Safe publication và object bất biến

Một object cần được công bố cho thread khác theo cách an toàn. Các cách phổ biến gồm:

- Gán tham chiếu vào một field volatile.
- Ghi và đọc tham chiếu dưới cùng một monitor.
- Đưa object vào một concurrent collection theo bảo đảm của collection đó.
- Truyền object qua cơ chế đồng bộ như Executor và nhận kết quả qua Future.
- Khởi tạo object trước khi gọi Thread.start() cho thread nhận object.

Các field final có bảo đảm khởi tạo đặc biệt của JMM: nếu object được xây dựng đúng và không để this thoát ra trước khi constructor hoàn tất, thread khác có thể quan sát giá trị final đã được khởi tạo ngay cả khi tham chiếu được công bố qua một đường không đồng bộ. Tuy nhiên, bảo đảm này không thay thế safe publication cho trạng thái mutable khác của object và không làm cho object mutable trở nên thread-safe.

Record có component final và phù hợp để biểu diễn dữ liệu theo giá trị, nhưng tính bất biến của record là nông. Nếu component chứa List mutable hoặc object mutable khác, nội dung của component đó vẫn có thể thay đổi sau khi record được tạo.

## 9. synchronized, ReentrantLock và pinning trên Java 21

Trên Java 21, virtual thread có thể bị pin vào carrier thread khi thực hiện blocking trong một synchronized block hoặc synchronized method, hoặc trong khi chạy native method. Pinning là vấn đề khả năng mở rộng và hiệu năng; nó không làm mất hiệu lực của bảo đảm mutual exclusion hay happens-before do monitor cung cấp.

Ví dụ cần kiểm tra trên runtime Java 21:

~~~java
synchronized (lock) {
    remoteClient.callBlockingService();
}
~~~

Nếu lời gọi bên trong block chờ lâu, carrier thread có thể bị giữ trong thời gian virtual thread bị pin. Hãy giữ vùng khóa ngắn và tránh gọi I/O chậm trong khi đang giữ intrinsic monitor nếu có thể bảo toàn tính đúng đắn bằng cách tổ chức lại thao tác.

ReentrantLock có thể hữu ích trong thiết kế phù hợp vì thao tác chờ khóa dựa trên cơ chế park, cho phép virtual thread chờ mà không nhất thiết giữ carrier. Tuy nhiên, thay synchronized bằng ReentrantLock không tự sửa race condition và cũng không loại bỏ mọi dạng pinning, chẳng hạn native call. Phải luôn giải phóng khóa trong finally:

~~~java
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

Theo JEP 491, từ JDK 24 virtual thread không còn bị pin chỉ vì blocking trong synchronized block hoặc method. Nếu ứng dụng chạy bằng JDK 21, vẫn cần đánh giá monitor pinning theo hành vi Java 21; nếu chạy bằng JDK mới hơn, hãy dùng tài liệu và công cụ chẩn đoán đúng phiên bản runtime. Native method và các trường hợp pinning khác vẫn cần được kiểm tra riêng.

## 10. Cách kiểm tra thread safety trước khi triển khai

Khi chuyển một đường xử lý sang virtual thread, hãy rà soát:

1. **Trạng thái dùng chung:** xác định singleton, cache, collection, counter và object mutable nào được nhiều tác vụ truy cập.
2. **Quy tắc đồng bộ hóa:** kiểm tra mọi đường đọc/ghi của cùng trạng thái có cùng cơ chế bảo vệ hay không.
3. **Tính nguyên tử:** tìm các chuỗi đọc-sửa-ghi như count++, kiểm tra rồi cập nhật map, hoặc cập nhật nhiều field cần nhất quán.
4. **Visibility:** xác định dữ liệu được công bố qua volatile, monitor, concurrent collection, Executor/Future hoặc cơ chế happens-before nào.
5. **Thread confinement:** giữ buffer, builder và dữ liệu tạm trong phạm vi tác vụ khi có thể.
6. **Tài nguyên theo thread:** kiểm tra ThreadLocal có giữ object lớn, connection hoặc tài nguyên cần đóng hay không.
7. **Pinning:** trên Java 21, kiểm tra blocking trong synchronized và native method; đo trên đúng runtime triển khai.
8. **Kiểm thử cạnh tranh:** dùng tải đồng thời đại diện, kiểm tra invariant nghiệp vụ và quan sát lỗi race, deadlock, starvation cùng mức contention.

Không dựa vào việc chạy thử nhiều lần mà không thấy lỗi để kết luận code an toàn luồng. Race condition có thể phụ thuộc lịch thực thi và chỉ xuất hiện dưới tải hoặc timing cụ thể. Hãy dựa vào JMM, cấu trúc đồng bộ hóa và kiểm thử có chủ đích.

## 11. Những kết luận cần nhớ

- Virtual thread vẫn là thread Java và tuân theo cùng Java Memory Model.
- Mount, unmount hoặc đổi carrier không tự tạo visibility hay happens-before.
- synchronized, volatile, atomic và concurrent collections vẫn là công cụ bảo đảm thread safety.
- Một virtual thread cho mỗi tác vụ không làm cho singleton, cache hay mutable state dùng chung tự an toàn.
- Future.get(), Thread.start(), join() và các cơ chế đồng bộ khác có những bảo đảm happens-before được JMM định nghĩa.
- Trên Java 21, monitor pinning có thể ảnh hưởng hiệu năng khi blocking trong synchronized; pinning không thay đổi tính đúng đắn của cơ chế khóa.

Thiết kế thread-safe cho virtual thread về bản chất vẫn là thiết kế thread-safe cho Java: xác định quyền sở hữu dữ liệu, bảo vệ trạng thái chia sẻ và dựa vào những quan hệ happens-before được bảo đảm.
