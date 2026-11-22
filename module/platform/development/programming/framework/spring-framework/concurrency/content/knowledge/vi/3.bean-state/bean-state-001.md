# Bean singleton được nhiều luồng sử dụng và không tự trở nên an toàn luồng

## 1. Vấn đề cần hiểu

Trong Spring Framework, một bean có scope **singleton** thường được tạo một lần cho một bean definition trong một Spring IoC container. Khi nhiều thành phần cùng inject bean đó, chúng thường nhận **cùng tham chiếu** đến đối tượng. Nếu nhiều luồng gọi phương thức trên bean cùng lúc, chúng có thể cùng đọc hoặc thay đổi các field của đối tượng ấy.

**Singleton chỉ nói về số lượng và vòng đời instance do container quản lý; singleton không phải cam kết thread-safe.** Spring không tự động khóa mọi lời gọi, chuyển field thành atomic hoặc tuần tự hóa mọi request vào singleton bean. An toàn luồng là trách nhiệm của thiết kế và những cơ chế đồng bộ phù hợp.

Ví dụ thường gặp:

- Hai HTTP request vào cùng một singleton **@RestController** hoặc **@Service** trong ứng dụng Spring MVC có thể chạy trên hai request threads khác nhau.
- Một method của singleton bean được gọi từ executor qua **@Async**, đồng thời bị một request khác gọi.
- Một singleton service được gọi bởi **@Scheduled**, listener hoặc nhiều worker threads.
- Nhiều phần code inject cùng singleton và cùng tác động vào cache, counter hay cấu hình mutable bên trong bean.

Không phải ứng dụng Spring nào cũng có nhiều luồng hoạt động, và không phải mọi method trên singleton đều bị gọi đồng thời. Nhưng **mặc định của scope singleton không ngăn sự đồng thời** khi môi trường thực thi tạo ra nó.

> Quy tắc thiết kế: ưu tiên singleton service **không giữ trạng thái biến đổi theo request**. Khi buộc phải có shared mutable state, phải định nghĩa bất biến (invariant), mức độ nhất quán cần thiết, ranh giới đồng bộ và cách kiểm chứng.

## 2. Singleton của Spring thực sự có nghĩa gì?

### 2.1. Một instance được chia sẻ trong phạm vi container

Scope mặc định của bean trong Spring là singleton. Hai lần lấy **cùng bean definition** từ cùng ApplicationContext sẽ cùng trỏ tới một object, ví dụ:

~~~java
// Minh họa bên trong ứng dụng đã có ApplicationContext.
Object first = context.getBean("orderService");
Object second = context.getBean("orderService");
System.out.println(first == second); // true
~~~

Cần phân biệt:

| Nhận định | Đúng hay sai? | Lý do |
| --- | --- | --- |
| Một bean singleton có thể được inject vào nhiều consumer | Đúng | Consumer dùng chung target instance do container cung cấp |
| Spring singleton là một object duy nhất trong cả JVM | Sai | Singleton scope được quản lý trong từng IoC container và theo bean definition; nhiều context/definition có thể tạo instance khác |
| Mọi instance của cùng một class đều là một bean singleton duy nhất | Sai | Hai bean definitions khác nhau có thể tạo hai đối tượng cùng class |
| Singleton sẽ tự khóa các lời gọi method | Sai | Scope không có chức năng đồng bộ thread |
| Không có mutable shared state thì singleton thường dễ dùng đồng thời | Đúng, với điều kiện | Cần kiểm tra cả các dependency và đối tượng mutable được chia sẻ |
| Một bean là singleton thì luôn bị gọi bởi nhiều thread | Sai | Phụ thuộc runtime và đường đi của request/task |

Lưu ý về **proxy**: trong Spring AOP, caller có thể cầm một proxy thay cho target. Dù proxy can thiệp vào lời gọi, không được suy ra target tự trở nên thread-safe. Những cơ chế như **@Transactional**, **@Async** hay **@Cacheable** cũng không phải khóa chung bảo vệ toàn bộ field của bean.

### 2.2. Phân biệt state theo từng lời gọi và state được chia sẻ

Quan sát hai method sau:

~~~java
@Service
public class InvoiceService {
    // Phần này không lưu dữ liệu của từng lời gọi vào field.
    public long calculate(long quantity, long unitPrice) {
        long subtotal = quantity * unitPrice;
        return subtotal;
    }
}
~~~

Đây là đoạn minh họa (chưa kèm import và cấu hình Spring độc lập). Biến **subtotal** là local variable, mỗi lần gọi có biến riêng. Nếu tham số là primitive hoặc dữ liệu immutable và không có dependency mutable bị sử dụng thiếu an toàn, các lời gọi đồng thời không tranh chấp field trong ví dụ này.

Ngược lại:

~~~java
@Service
public class OrderService {
    private String currentOrderId;

    public void process(String orderId) {
        currentOrderId = orderId;
        // Các bước tiếp theo đọc currentOrderId.
    }
}
~~~

Hai request A và B dùng chung **currentOrderId**. A có thể ghi "A", B ghi "B", rồi A đọc lại "B". Chương trình đã làm lẫn dữ liệu giữa các request dù mỗi method có tham số riêng.

Những dữ liệu thường **không nên** giữ trong field của singleton: request id hiện tại, user hiện tại, thông tin xác thực theo request, dữ liệu form đang xử lý, biến tạm tính toán, một request-scoped object lấy sai cách hoặc một buffer mutable tái sử dụng không có bảo vệ.

Giữ dữ liệu request trong tham số, local variable, giá trị trả về, hoặc chuyển sang cơ chế lưu trữ đúng scope và vòng đời. Local variable chỉ bảo vệ **tham chiếu cục bộ**: nếu nó trỏ đến một object mutable mà các luồng khác cũng dùng chung thì vẫn có race trên object đó.

## 3. Vì sao shared mutable state tạo race condition?

### 3.1. Lost update với phép tăng biến đếm

Giả sử singleton có field:

~~~java
private int count = 0;

public int next() {
    return ++count;
}
~~~

**++count** không phải một thao tác nguyên tử duy nhất. Về mặt logic, nó gồm đọc giá trị hiện tại, tính giá trị mới và ghi lại. Hai luồng có thể xen kẽ:

| Thời điểm | Thread A | Thread B | count lưu trong bean |
| --- | --- | --- | --- |
| 1 | Đọc 0 | | 0 |
| 2 | | Đọc 0 | 0 |
| 3 | Tính 1, ghi 1 | | 1 |
| 4 | | Tính 1, ghi 1 | 1 |
| 5 | Hoàn tất | Hoàn tất | **1 thay vì 2** |

Đây là **lost update**. Đồng thời còn có thể gặp **stale read** (đọc giá trị cũ), **check-then-act race** (kiểm tra điều kiện rồi hành động khi điều kiện đã đổi) và **vi phạm invariant** khi một thao tác cần cập nhật nhiều field nhất quán.

### 3.2. Visibility, atomicity và ordering là ba khái niệm riêng

- **Visibility:** khi thread A cập nhật, thread B có đảm bảo nhìn thấy cập nhật ấy đúng lúc không? Java Memory Model và quan hệ *happens-before* quyết định việc này.
- **Atomicity:** một thao tác ghép gồm nhiều bước có bị các thread khác xen vào giữa không?
- **Ordering:** compiler, CPU và runtime có thể tái sắp xếp các thao tác trong phạm vi được Java Memory Model cho phép; cơ chế đồng bộ đặt ra những ràng buộc quan trọng.

Đánh dấu field **volatile** tăng bảo đảm về visibility và ordering cho các truy cập tương ứng, nhưng **không biến count++ thành một phép tăng nguyên tử**. Hai thread vẫn có thể cùng đọc số cũ rồi cùng ghi số mới.

Tương tự, khai báo object là **final** giữ cố định tham chiếu field sau khởi tạo nhưng **không tự động làm cho nội dung của object được tham chiếu bất biến**. Ví dụ final List không đồng nghĩa mọi lần add/remove đều an toàn luồng.

## 4. Ví dụ chạy được: cùng một singleton bị hai luồng gọi

Ví dụ dưới đây dùng **Java 17+, Spring Framework 6.1.14 và Gradle 8.5+**. Không cần Spring Boot hay máy chủ web; một AnnotationConfigApplicationContext tạo hai bean singleton, rồi executor có hai worker gọi cùng instance. **CyclicBarrier** được đặt trong ví dụ lỗi chỉ để *buộc hai thread đều đọc giá trị cũ trước khi ghi*, qua đó tái hiện lost update một cách có kiểm soát. Trong nghiệp vụ thật không thêm barrier để tăng counter.

Cấu trúc project:

~~~text
singleton-race-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SingletonRaceDemo.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'singleton-race-demo'
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
}

application {
    mainClass = 'demo.SingletonRaceDemo'
}
~~~

**src/main/java/demo/SingletonRaceDemo.java** (một file Java hoàn chỉnh):

~~~java
package demo;

import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class SingletonRaceDemo {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(BeanConfig.class)) {

            UnsafeCounter unsafe = context.getBean(UnsafeCounter.class);
            SafeCounter safe = context.getBean(SafeCounter.class);

            System.out.println("same bean instance = " +
                    (unsafe == context.getBean(UnsafeCounter.class)));

            ExecutorService pool = Executors.newFixedThreadPool(2);
            try {
                // Cả hai task phải đọc cùng giá trị ban đầu rồi mới ghi.
                CyclicBarrier bothRead = new CyclicBarrier(2);
                Callable<Void> unsafeCall = () -> {
                    unsafe.incrementForDemo(bothRead);
                    return null;
                };

                Future<Void> first = pool.submit(unsafeCall);
                Future<Void> second = pool.submit(unsafeCall);
                first.get();
                second.get();

                System.out.println("unsafe updates = " + unsafe.value());

                // AtomicInteger thực hiện increment nguyên tử.
                Callable<Void> safeCall = () -> {
                    safe.increment();
                    return null;
                };

                Future<Void> third = pool.submit(safeCall);
                Future<Void> fourth = pool.submit(safeCall);
                third.get();
                fourth.get();

                System.out.println("atomic updates = " + safe.value());
            } finally {
                pool.shutdown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BeanConfig {
        @Bean
        UnsafeCounter unsafeCounter() {
            return new UnsafeCounter();
        }

        @Bean
        SafeCounter safeCounter() {
            return new SafeCounter();
        }
    }

    static final class UnsafeCounter {
        // volatile KHÔNG khiến đọc + tăng + ghi trở thành atomic.
        private volatile int count;

        void incrementForDemo(CyclicBarrier bothRead)
                throws InterruptedException, BrokenBarrierException {
            int before = count;
            bothRead.await(); // Dùng riêng cho minh họa race.
            count = before + 1;
        }

        int value() {
            return count;
        }
    }

    static final class SafeCounter {
        private final AtomicInteger count = new AtomicInteger();

        void increment() {
            count.incrementAndGet();
        }

        int value() {
            return count.get();
        }
    }
}
~~~

Tại thư mục **singleton-race-demo**, chạy:

~~~bash
gradle run
~~~

Nếu project có Gradle Wrapper, thay lệnh bằng **./gradlew run** (Linux/macOS) hoặc **gradlew.bat run** (Windows). Ba dòng do chương trình tự in sẽ là:

~~~text
same bean instance = true
unsafe updates = 1
atomic updates = 2
~~~

Gradle có thể in thêm thông báo build và logging phụ thuộc môi trường. Tại sao ba giá trị trên có thể dự đoán? **@Bean** mặc định dùng singleton scope; hai lần getBean trả cùng bean. Trong UnsafeCounter, barrier buộc hai tác vụ cùng giữ bản sao **0**, rồi cả hai đều ghi **1**. Trong SafeCounter, AtomicInteger.incrementAndGet() áp dụng hai lần tăng nguyên tử, nên kết quả cuối là **2**. Việc đợi Future.get() bảo đảm main chỉ đọc kết quả sau khi các task đã hoàn tất.

Ví dụ không nhằm đo throughput hay chứng minh một thuật toán có thể luôn tái hiện race ngoài production. Nó cố tình điều khiển thời điểm xen kẽ để cho thấy **scope singleton không ngăn mất cập nhật**.

## 5. Cách thiết kế singleton an toàn trong thực tế

### 5.1. Ưu tiên stateless service

Tốt nhất là để method nhận đủ đầu vào, tính toán và trả kết quả; field chỉ giữ những dependency được inject hoặc configuration cố định. Ví dụ minh họa:

~~~java
@Service
public class PriceService {
    public long total(long unitPrice, int quantity) {
        return Math.multiplyExact(unitPrice, quantity);
    }
}
~~~

Dữ liệu mỗi request đi qua tham số và giá trị trả về. Nếu có dependency được inject, vẫn phải xét tính thread-safe của dependency đó; một singleton stateless gọi một object mutable dùng chung thiếu đồng bộ **vẫn có thể không an toàn**. Đừng chuyển state từ field này sang một static field hoặc một shared cache chỉ để trông giống stateless.

### 5.2. Dùng immutable state khi cần chia sẻ cấu hình

Các đối tượng immutable (nội dung không thể thay đổi sau khi xây dựng) rất phù hợp để dùng chung, ví dụ String, record chứa thành phần immutable, hoặc một danh sách được sao chép phòng vệ rồi chỉ đọc. Hãy bảo đảm cả đối tượng lồng nhau cũng không bị thay đổi bởi nơi khác nếu invariant dựa vào chúng.

~~~java
public record FeePolicy(int percent, String currency) { }

// Cùng một FeePolicy bất biến có thể được nhiều request cùng đọc.
~~~

Nếu cần thay cả bộ cấu hình trong runtime, một cách là tạo **immutable snapshot** mới rồi thay tham chiếu bằng AtomicReference hoặc volatile, thay vì cập nhật lẻ tẻ nhiều field. Cần phân biệt atomic replacement của một reference với tính nguyên tử của nhiều tài nguyên độc lập.

### 5.3. Dùng nguyên tử và cấu trúc concurrent đúng thao tác

Một counter dùng chung có thể khai báo:

~~~java
private final AtomicLong requestCount = new AtomicLong();

public long nextNumber() {
    return requestCount.incrementAndGet();
}
~~~

AtomicLong phù hợp cho tăng, giảm, compare-and-set của **một giá trị** trong một JVM. Với thống kê tần suất ghi rất cao, LongAdder có thể giảm contention, nhưng **sum() không phải một snapshot nguyên tử** khi các cập nhật còn diễn ra. Không dùng nó cho số thứ tự cần duy nhất và tăng tuần tự từng lần gọi.

Với map được nhiều thread cập nhật, cân nhắc **ConcurrentHashMap** và các thao tác như compute, merge, putIfAbsent khi cần cập nhật một key một cách nguyên tử:

~~~java
private final ConcurrentHashMap<String, Long> counts =
        new ConcurrentHashMap<>();

public void record(String type) {
    counts.merge(type, 1L, Long::sum);
}
~~~

Đoạn trên là minh họa nằm trong class có import java.util.concurrent.ConcurrentHashMap. **ConcurrentHashMap** bảo vệ những thao tác được đặc tả của map; nó không làm cho một object mutable đặt trong value tự nhiên thread-safe, cũng không khiến nhiều thao tác trên nhiều key trở thành một transaction chung.

### 5.4. Dùng synchronized hoặc Lock khi có invariant nhiều bước

Khi cần kiểm tra điều kiện và cập nhật nhiều field theo một đơn vị logic, bảo vệ **cả vùng thao tác** bằng cùng một lock:

~~~java
public class BoundedInventory {
    private int available = 3;

    public synchronized boolean reserve() {
        if (available <= 0) {
            return false;
        }
        available--;
        return true;
    }

    public synchronized int remaining() {
        return available;
    }
}
~~~

Nếu mọi đường đọc/ghi **available** đều tuân thủ cùng monitor, invariant không bị hai thread tranh giành trong một instance. Có thể dùng ReentrantLock với try/finally và các tùy chọn lock khác khi thực sự cần. Khóa giúp bảo đảm tính đúng nhưng có chi phí về contention và có thể gây deadlock nếu khóa nhiều tài nguyên không nhất quán. Tránh giữ lock khi thực hiện I/O, gọi mạng hoặc chờ task khác nếu chưa đánh giá cẩn thận.

**@Transactional** là cơ chế transaction, không thay thế monitor lock trên field Java. Ngược lại, **synchronized** chỉ khóa một JVM/object, không tự cung cấp giao dịch hay điều phối dữ liệu trên nhiều bản sao ứng dụng.

### 5.5. Dữ liệu dùng chung giữa nhiều application instances phải đặt ở ranh giới phù hợp

Nếu chạy nhiều pod/instance, mỗi ApplicationContext có các singleton của riêng mình. AtomicInteger hay synchronized trong một instance **không làm bộ đếm chung của cluster** nhất quán. Với ví dụ số lượng hàng tồn, số thứ tự nghiệp vụ, hạn mức hay chống xử lý trùng, hãy dùng cơ chế thống nhất trên nguồn dữ liệu thực: transaction và cập nhật có điều kiện, optimistic/pessimistic locking của database, unique constraint, atomic operation của hệ lưu trữ phù hợp hoặc dịch vụ điều phối được thiết kế cho việc đó.

Đừng dùng static field hoặc Singleton pattern thuần Java như một "distributed lock": chúng cũng không vượt qua ranh giới tiến trình.

## 6. Scope khác có giải quyết thread-safety không?

| Scope/cơ chế | Thay đổi vòng đời hoặc việc cấp phát | Có tự bảo đảm thread-safe? |
| --- | --- | --- |
| **singleton** | Một bean instance cho một bean definition trong container | **Không** |
| **prototype** | Tạo instance mới mỗi lần container nhận yêu cầu lấy bean | **Không**; cùng prototype vẫn có thể bị chia sẻ sang nhiều thread |
| **request** | Một bean cho phạm vi HTTP request đang hoạt động (trong web context hỗ trợ) | **Không**; logic có thể có concurrent/asynchronous access trong request |
| **session** | Một bean theo HTTP session | **Không**; hai request của cùng session có thể đồng thời truy cập |
| **ObjectProvider<T>** | Cho phép yêu cầu bean theo nhu cầu, ví dụ lấy prototype mỗi lần | Chỉ giúp quản lý việc lấy instance; không tự đồng bộ state |

Một bẫy quan trọng: **inject prototype trực tiếp vào constructor của singleton không có nghĩa mỗi lần singleton gọi method sẽ tự được cấp prototype mới**. Dependency thường được resolve ở thời điểm xây dựng singleton và sau đó cùng tham chiếu được dùng lại; nếu cần mỗi lần lấy instance mới, dùng ObjectProvider, lookup method hoặc scoped proxy theo ngữ cảnh thích hợp.

Scope cũng không phải công cụ thay thế thiết kế dữ liệu: ngay cả một request-scoped bean vẫn có thể ghi vào một static map chung, gọi singleton mutable hoặc chia sẻ một object cho nhiều worker threads.

## 7. Các tương tác thường gây nhầm lẫn trong Spring Concurrency

**Spring MVC:** trong mô hình Servlet truyền thống, những request đồng thời có thể do những worker threads khác nhau xử lý. Singleton controller và service là những object được chia sẻ. Việc controller không tạo new service ở mỗi request là đặc tính của DI/scope, không phải bảo đảm serialization.

**@Async:** đưa lời gọi hợp lệ qua Spring proxy sang executor có thể tạo thêm luồng cùng dùng bean hoặc dependency. Nếu method @Async đọc/ghi field mutable của singleton, việc đổi sang async **làm tăng tình huống tranh chấp**, chứ không sửa race. Nếu cần dữ liệu của một request, truyền rõ dữ liệu cần thiết hoặc quản lý context propagation đúng cách.

**@Scheduled:** scheduler kích hoạt một method theo thời gian; cùng singleton cũng có thể được gọi từ nơi khác hoặc từ nhiều registrations. Không suy ra mỗi scheduled bean có "thread riêng" hoặc mọi lời gọi được khóa. Tính chồng lấp phụ thuộc scheduler, cách đăng ký, thời gian thực thi và việc có tách @Async hay không.

**@Transactional:** transaction thường gắn với luồng thực thi/cơ chế transaction manager và dữ liệu lưu trữ; nó không bảo vệ một biến int trong singleton khỏi hai luồng sửa đồng thời. Nếu hai transaction thay đổi cùng record, cần chiến lược concurrency control của data layer.

**ThreadLocal:** chứa dữ liệu theo thread, không phải theo Spring singleton hay tự động theo HTTP request. Với thread pool, thread có thể được tái sử dụng; cần quản lý set/remove và việc truyền context đúng cách. ThreadLocal không giải quyết race trên field shared, không thay thế việc truyền tham số, và không tự an toàn khi đổi thread bằng @Async.

**Reactive/WebFlux:** đừng mặc định xử lý luôn thuộc một thread cố định; callback có thể chạy trên các scheduler khác nhau. Một singleton với shared mutable state vẫn cần đồng bộ thích hợp, trong khi blocking lock/I/O trên event-loop có thể ảnh hưởng nghiêm trọng khả năng đáp ứng. Stateless và thiết kế không chặn thường là hướng ưu tiên.

## 8. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân đáng kiểm tra | Hướng khắc phục |
| --- | --- | --- |
| Counter đôi khi tăng thiếu | **count++** trong singleton gặp lost update | AtomicLong/AtomicInteger hoặc lock bao toàn bộ cập nhật |
| Dữ liệu user A xuất hiện trong xử lý user B | Lưu currentUser/currentRequest vào field singleton | Truyền request data qua tham số hoặc dùng scope/context đúng vòng đời |
| HashMap/ArrayList lỗi hoặc thiếu phần tử khi truy cập đồng thời | Collection mutable được chia sẻ không có bảo vệ | Chọn concurrent collection và đúng atomic operations; hoặc lock |
| Tính tổng sai dù field đã dùng volatile | Volatile không làm thao tác ghép nguyên tử | Chuyển sang Atomic*, lock, hoặc thuật toán không có shared update |
| Tạo prototype nhưng vẫn bị race | Prototype bị inject một lần vào singleton hoặc reference được chia sẻ | Kiểm tra thời điểm lấy instance, ownership và giới hạn chia sẻ |
| Đồng bộ đã đúng trong một instance nhưng nhiều pod vẫn mất cập nhật | Khóa/atomic chỉ bảo vệ bộ nhớ một JVM | Đưa invariant sang transaction, unique constraint hoặc atomic operation ở shared store |
| Thỉnh thoảng đọc cấu hình chắp vá | Ghi nhiều field riêng lẻ khi thread khác đọc | Dùng một immutable snapshot thay nguyên tử hoặc bảo vệ nhiều field cùng lock |

Lỗi khác dễ bỏ qua là gọi dependency *không* thread-safe từ singleton. Ví dụ chia sẻ một SimpleDateFormat mutable hoặc một buffer StringBuilder giữa các request mà không bảo vệ. Không phải mọi dependency đều cần khóa: trước hết xem tài liệu thread-safety và cách sử dụng thực tế của nó.

## 9. Cách kiểm tra một singleton trước khi đưa vào môi trường đồng thời

1. **Xác định instance và callers.** Bean thuộc context nào? Có bao nhiêu nơi inject? Có request, scheduler, listener, async task hoặc callback nào gọi đồng thời không?
2. **Liệt kê shared state.** Field mutable của chính bean, object mutable qua dependency, static state, cache, collection, biến cấu hình có thể reload.
3. **Phân tích thao tác.** Chỉ đọc? Một giá trị cần atomic update? Một invariant trải trên nhiều field? Có cơ chế publication/happens-before giữa writer và reader không?
4. **Chọn chiến lược phù hợp.** Ưu tiên stateless/immutable, tiếp theo Atomic* hoặc concurrent collection; khi invariant nhiều bước thì dùng cùng lock hoặc transaction của tầng dữ liệu tương ứng.
5. **Kiểm tra bằng tình huống đồng thời thật.** Dùng CountDownLatch, CyclicBarrier hay lệnh gọi đồng thời để ép interleaving và assert invariant; bổ sung stress test nếu cần. Một test chạy qua một lần **không chứng minh** không có race; test ngẫu nhiên nhiều lần cũng không thay thế phân tích bộ nhớ và khóa.
6. **Quan sát production.** Đo tỉ lệ lỗi, số lần retry, queue, độ trễ và các invariant bị vi phạm. Phân biệt lỗi concurrency trong JVM với xung đột dữ liệu ở database hoặc nhiều instance.

Khi một method chỉ trả về kết quả tính toán từ input độc lập, không giữ state theo request, đó thường là trường hợp singleton dễ dùng an toàn nhất. Khi nó phải lưu shared state, hãy làm rành mạch **ai sở hữu dữ liệu, thao tác nào nguyên tử và phạm vi bảo vệ có bao trùm tất cả callers hay không**.

## 10. Câu hỏi tự kiểm tra

1. Hai controller khác nhau inject cùng một singleton service. Chúng có dùng hai đối tượng service độc lập không? **Không**, nếu cả hai resolve cùng bean definition trong cùng container.
2. Đánh dấu **volatile int count** rồi gọi **count++** từ hai threads có bảo đảm kết quả tăng đúng hai lần không? **Không**, vì read-modify-write không nguyên tử.
3. Thay singleton bằng prototype có tự động sửa lỗi nếu cùng một object được chia sẻ cho nhiều worker không? **Không**. Scope điều khiển cách container tạo/cấp phát bean, không tự khóa thao tác.
4. Một singleton hoàn toàn stateless nhưng gọi chung một HashMap mutable thiếu bảo vệ: có chắc thread-safe không? **Không**. Phải xét cả dependency và shared objects.
5. Thêm **@Transactional** quanh method cập nhật field có chặn hai threads thay đổi field ấy cùng lúc không? **Không**. Transaction không phải monitor lock cho bộ nhớ Java.
6. AtomicInteger trong một instance có bảo đảm một business counter tăng đúng trên ba pod không? **Không**. Cần đặt quy tắc nhất quán tại hệ lưu trữ/điều phối chung.

**Ghi nhớ:** singleton quyết định **chia sẻ instance**, còn thread-safety quyết định **chia sẻ có đúng đắn khi thao tác xen kẽ hay không**. Spring cung cấp container, proxy và các tích hợp concurrency, nhưng thiết kế về mutable state, atomicity và invariant vẫn thuộc về mã ứng dụng.

Tài liệu tham khảo chính thức:
- [Spring Framework — Bean Scopes, Singleton Scope](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html#beans-factory-scopes-singleton)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Java SE — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)
