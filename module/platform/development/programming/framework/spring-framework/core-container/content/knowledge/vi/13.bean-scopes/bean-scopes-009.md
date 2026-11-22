# Trạng thái dùng chung và an toàn luồng của singleton trong Spring Framework

## 1. Singleton trong Spring thực sự có ý nghĩa gì?

Mặc định, một bean do Spring IoC Container quản lý có scope `singleton`. Khi cùng một bean definition (cùng định danh) được truy xuất nhiều lần trong **một Spring container**, Spring trả về cùng một đối tượng. Một service/controller singleton thường được nhiều lời gọi đồng thời sử dụng, đặc biệt khi ứng dụng phục vụ nhiều HTTP request, nhiều tác vụ từ executor hoặc nhiều message listener.

```text
                  Spring ApplicationContext
                            |
                  singleton bean: OrderService
                            |
           +----------------+----------------+
           |                |                |
       Thread A         Thread B         Thread C
       request #1       request #2       background job
           |                |                |
           +----------- cùng instance --------+
```

**Điểm cốt lõi:** singleton chỉ quyết định **số lượng và cách chia sẻ instance**. Singleton **không** có nghĩa là các phương thức được Spring tự động khóa, chạy lần lượt, hoặc được đảm bảo thread-safe. Spring không tự biến một field mutable thành atomic và không tự cô lập dữ liệu từng request.

Ranh giới Spring singleton là **per bean definition, per container**. Một lớp có thể được khai báo dưới hai bean name và nhận hai instance khác nhau; hai `ApplicationContext` độc lập hoặc hai JVM/pod không tự chia sẻ một singleton toàn hệ thống. Đây không phải singleton pattern kiểu static instance toàn JVM.

Phân biệt:

- **Stateless singleton**: không giữ dữ liệu thay đổi theo từng request trong field; chỉ dùng tham số, biến cục bộ, dependency an toàn, hoặc cấu hình bất biến. Đây là kiểu ưu tiên cho service nghiệp vụ.
- **Stateful singleton**: giữ field thay đổi trong lúc chạy, ví dụ `lastUserId`, `items`, `count`, cache, trạng thái giao dịch tạm. Cần thiết kế đồng thời rõ ràng nếu nhiều luồng truy cập.
- **Thread-safe**: việc gọi đối tượng đồng thời vẫn bảo toàn những invariant đã định, tránh data race gây sai logic, đồng thời có quy tắc nhìn thấy cập nhật giữa các luồng (memory visibility).
- **Reentrant**: phương thức có thể bị gọi lồng hoặc đồng thời mà vẫn xử lý đúng nhờ thiết kế riêng; từ này không đồng nghĩa mặc nhiên với singleton hay thread-safe.

Một singleton chứa `final Repository repository` không có nghĩa repository và các object nó trả về đều bất biến; độ an toàn phải xét **toàn bộ object graph và hành vi được gọi**.

## 2. Vì sao dễ xảy ra race condition?

Xét một service lưu người đang xử lý bằng field:

```java
import org.springframework.stereotype.Service;

@Service
public class UnsafeGreetingService {
    private String currentName;

    public String greet(String name) {
        currentName = name;             // Ghi field chia sẻ
        return "Hello " + currentName;  // Đọc field chia sẻ
    }
}
```

Đây là đoạn class minh họa; nó cần chạy trong Spring context có component scanning. Nếu hai request cùng gọi `greet`, một thứ tự thực thi hợp lệ có thể là:

| Thời điểm | Request A | Request B |
| --- | --- | --- |
| 1 | `currentName = "An"` | |
| 2 | | `currentName = "Bình"` |
| 3 | Đọc `currentName`, có thể nhận `"Bình"` | |
| 4 | | Đọc `currentName` |

Request A có thể trả `"Hello Bình"` dù tham số của A là `"An"`. Tình huống thực tế còn phụ thuộc lập lịch và quy tắc bộ nhớ JVM: **không phải mỗi lần chạy đều tái hiện được lỗi**. Ngay cả khi mỗi call chạy rất nhanh, vẫn có thể bị interleave giữa hai câu lệnh.

Sửa tốt nhất ở đây là xóa field chứa trạng thái của lời gọi:

```java
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        String message = "Hello " + name;
        return message;
    }
}
```

Biến `message` và tham số `name` thuộc từng lần gọi method, không phải field của bean. Hai thread có stack và lời gọi riêng. Chuỗi `String` bất biến, vì thế ví dụ này không tạo trạng thái dùng chung mutable. Tuy nhiên, nếu một biến local trỏ tới một collection hoặc object **đã dùng chung** thì việc biến đó là local chưa đủ bảo đảm thread-safe.

### Ba loại lỗi cần phân biệt

1. **Race condition / lost update:** nhiều luồng sửa cùng một trạng thái; kết quả phụ thuộc interleaving. Ví dụ `count++` khi chạy đồng thời có thể mất lượt tăng.
2. **Visibility:** một luồng đã ghi nhưng luồng khác không được đảm bảo nhìn thấy cập nhật đúng thời điểm nếu thiếu quan hệ happens-before; compiler/CPU/JVM có thể tối ưu hoặc sắp xếp lại theo Java Memory Model.
3. **Invariant bị phá vỡ:** mỗi field hoặc thao tác riêng có thể an toàn, nhưng tổ hợp nhiều bước không atomic. Ví dụ kiểm tra số dư rồi trừ tiền, hoặc kiểm tra key rồi `put`, có thể sai khi các bước xen kẽ.

`count++` tương đương ý nghĩa với **đọc → cộng → ghi** và không phải một thao tác nguyên tử. `volatile int count` chỉ cung cấp các guarantee về visibility và ordering của đọc/ghi field; `count++` trên `volatile` vẫn không atomic.

## 3. Chọn thiết kế stateless trước khi thêm khóa

Một Spring service thường chỉ nên phối hợp các dependency và xử lý input thành output:

```java
package edu.example.design;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
public class PriceService {
    private static final BigDecimal TAX_RATE = new BigDecimal("0.10");

    public BigDecimal totalWithTax(BigDecimal subtotal) {
        return subtotal.multiply(BigDecimal.ONE.add(TAX_RATE));
    }
}
```

Đoạn trên là class Spring component, không phải một chương trình `main` độc lập. `BigDecimal` bất biến; không giữ subtotal của khách hàng trên field. Có thể gọi `totalWithTax` từ nhiều thread với các giá trị khác nhau.

Một vài hướng giảm chia sẻ mutable state:

- **Constructor injection + `final`** cho dependency cần thiết; tránh cập nhật dependency giữa các request.
- **Immutable value object/record** cho dữ liệu trao đổi; mỗi lời gọi tạo giá trị mới khi cần.
- **Local variable** cho intermediate state trong một lần xử lý, thay vì đặt ở field singleton.
- **Dữ liệu nghiệp vụ lâu dài** đưa vào repository/database và quy định transaction/concurrency phù hợp.
- **Per-request state** mang theo tham số hoặc scoped context khi hợp lý; không gắn request DTO vào field singleton.

`final` khóa **reference của field**, không làm object mà nó trỏ tới tự động immutable:

```java
private final java.util.List<String> names = new java.util.ArrayList<>();
// Không thể gán names = listKhac, nhưng names.add("An") vẫn sửa ArrayList.
```

Với dữ liệu chỉ đọc, có thể xây một snapshot rồi công bố bất biến qua `List.copyOf`/`Map.copyOf`. Cần đảm bảo các phần tử cũng bất biến hoặc được sử dụng an toàn nếu muốn bảo đảm toàn bộ dữ liệu không đổi.

## 4. Khi buộc phải giữ trạng thái dùng chung: chọn công cụ đúng

| Nhu cầu | Công cụ thường hợp lý | Giới hạn/điểm cần xét |
| --- | --- | --- |
| Cấu hình chỉ đọc sau khởi tạo | `final` + immutable object | Object bên trong cũng phải bất biến hoặc được quản lý đúng |
| Một counter/sequence đơn giản trong JVM | `AtomicLong`/`AtomicInteger` | Không tự gom nhiều field thành transaction |
| Nhiều thread đếm tần suất với contention lớn | `LongAdder` | `sum()` khi có cập nhật đồng thời không phải snapshot atomic |
| Bảo vệ một invariant nhiều bước | `synchronized`, `ReentrantLock` | Giữ cùng một lock cho mọi bước liên quan; tránh I/O lâu trong lock |
| Một map truy cập đồng thời | `ConcurrentHashMap` | Chuỗi thao tác riêng `get` rồi `put` chưa đủ atomic |
| Cờ trạng thái đọc/ghi đơn giản | `volatile` hoặc `AtomicBoolean` | `volatile` không bảo vệ phép read-modify-write |
| Trạng thái mỗi HTTP request | Tham số/local variable hoặc `@RequestScope` | Không mang theo tự động vào executor thread |
| Trạng thái cho một HTTP session | `@SessionScope` nếu thật sự cần | Hai request cùng session vẫn có thể chạy song song |
| Dữ liệu nhất quán trên nhiều process/pod | DB transaction, optimistic locking, Redis/atomic op thích hợp | JVM lock/atomic chỉ bảo vệ bộ nhớ của một process |

Không có một annotation Spring duy nhất giải quyết mọi trường hợp. Công cụ phải tương ứng với invariant thực tế: đếm, kiểm tra điều kiện, thay đổi nhiều field, truy cập bên ngoài JVM hay cô lập theo request.

### 4.1. AtomicLong: bộ đếm nhất quán trong một JVM

```java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class RequestCounter {
    private final AtomicLong count = new AtomicLong();

    public long next() {
        return count.incrementAndGet();
    }

    public long current() {
        return count.get();
    }
}
```

Mỗi `incrementAndGet()` là một cập nhật nguyên tử và trả số sau khi tăng. Ví dụ nếu chỉ có một instance counter, 8 thread gọi 1.000 lần/thread, tổng giá trị cuối cùng **chắc chắn là 8.000**, miễn không có lần gọi khác và tất cả tác vụ hoàn tất thành công. Thứ tự các số trả về giữa các thread không được đảm bảo; giá trị cuối thì đúng.

Khi cần hai field luôn biến đổi cùng nhau, không thể coi hai `AtomicLong` độc lập là một transaction. Có thể dùng một immutable record lưu vào `AtomicReference` và cập nhật bằng CAS trên **cả record**, hoặc dùng lock bảo vệ invariant.

### 4.2. synchronized: bảo vệ nhiều bước bằng cùng lock

```java
public final class StockCounter {
    private int available = 10;

    public synchronized boolean reserveOne() {
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
```

Hai method `synchronized` instance này dùng cùng monitor `this`. Với mọi truy cập vào `available` đều đi qua các method có khóa, điều kiện `available > 0` và phép giảm nằm trong cùng critical section. Câu lệnh `synchronized` tạo quan hệ happens-before giữa unlock và lần lock sau trên **cùng monitor**, đồng thời bảo vệ tính atomic của cả block.

Không tự ý đọc/ghi trực tiếp `available` từ method không synchronized nếu muốn bảo toàn invariant. Cũng không dùng hai lock riêng cho hai bước của cùng một quy tắc. Với logic gọi I/O, database, service mạng, nên giảm thời gian giữ lock và cân nhắc đặt tính nhất quán tại data store.

### 4.3. ConcurrentHashMap và compound operations

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public final class MetricsByRoute {
    private final ConcurrentHashMap<String, LongAdder> hits =
            new ConcurrentHashMap<>();

    public void record(String route) {
        hits.computeIfAbsent(route, key -> new LongAdder()).increment();
    }

    public long approximateCount(String route) {
        LongAdder adder = hits.get(route);
        return adder == null ? 0L : adder.sum();
    }
}
```

`computeIfAbsent` atomically thiết lập giá trị khi key vắng mặt; các adder là counters riêng theo key. `LongAdder.sum()` hữu ích cho metrics/telemetry, nhưng khi các thread đang cập nhật, tổng đọc được có thể không là snapshot tuyến tính tại một thời điểm. Nếu cần chính xác và nhất quán cho giao dịch, nên dùng công cụ khác.

Đừng dùng `if (!map.containsKey(key)) map.put(key, value)` để kỳ vọng cả hai bước atomic; giữa hai thao tác, một thread khác có thể insert. Tránh tạo side effect ngoài ý muốn trong lambda của `computeIfAbsent` hoặc `compute`, vì hàm có thể được chạy trong quy trình đồng bộ nội bộ và không nên thực hiện tác vụ kéo dài.

### 4.4. volatile dùng ở đâu?

```java
public final class ShutdownSignal {
    private volatile boolean stopping;

    public void requestStop() {
        stopping = true;
    }

    public boolean isStopping() {
        return stopping;
    }
}
```

Khi một thread gọi `requestStop()`, các thread khác đọc `isStopping()` có guarantee visibility phù hợp theo Java Memory Model. Dùng được cho cờ stop đơn giản. Nhưng nếu logic là "đọc nếu false, rồi đặt true sao cho chỉ một thread thắng", hãy dùng `AtomicBoolean.compareAndSet(false, true)` để kết hợp điều kiện và cập nhật atomically.

## 5. Ví dụ thực hành Spring Core chạy trên Java 17+

Dự án này minh họa trực tiếp singleton của **Spring Core Container**, không cần web server. Sử dụng Java 17+, Maven 3.9+ và dependency `spring-context:6.2.18`. Ta tạo một bean singleton `SafeCounter`, lấy bean đó hai lần từ context và tăng nó đồng thời bằng tám thread. Chạy đầy đủ chương trình để có output xác định.

Cấu trúc:

```text
spring-singleton-concurrency/
├── pom.xml
└── src/main/java/edu/example/concurrency/
    ├── AppConfig.java
    ├── SafeCounter.java
    └── App.java
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>spring-singleton-concurrency</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>edu.example.concurrency.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/edu/example/concurrency/AppConfig.java**

```java
package edu.example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AppConfig {
    @Bean // Mặc định là singleton trong ApplicationContext này.
    public SafeCounter safeCounter() {
        return new SafeCounter();
    }
}
```

**src/main/java/edu/example/concurrency/SafeCounter.java**

```java
package edu.example.concurrency;

import java.util.concurrent.atomic.AtomicLong;

public final class SafeCounter {
    private final AtomicLong value = new AtomicLong();

    public long increment() {
        return value.incrementAndGet();
    }

    public long get() {
        return value.get();
    }
}
```

**src/main/java/edu/example/concurrency/App.java**

```java
package edu.example.concurrency;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            SafeCounter first = context.getBean(SafeCounter.class);
            SafeCounter second = context.getBean(SafeCounter.class);
            System.out.println("same singleton: " + (first == second));

            int threadCount = 8;
            int callsPerThread = 1_000;
            ExecutorService executor = Executors.newFixedThreadPool(threadCount);
            CountDownLatch start = new CountDownLatch(1);
            List<Future<?>> futures = new ArrayList<>();

            try {
                for (int t = 0; t < threadCount; t++) {
                    futures.add(executor.submit(() -> {
                        start.await();
                        for (int i = 0; i < callsPerThread; i++) {
                            first.increment();
                        }
                        return null;
                    }));
                }
                start.countDown();
                for (Future<?> future : futures) {
                    future.get();  // Chờ hoàn tất, đồng thời phát hiện lỗi task.
                }
                System.out.println("counter: " + first.get());
            } finally {
                executor.shutdown();
            }
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

**stdout của chương trình:**

```text
same singleton: true
counter: 8000
```

Các log Maven/Spring phát ra môi trường có thể khác nhau; hai dòng trên là output của `System.out.println`. Giá trị `8000` xác định do `AtomicLong` bảo đảm mọi increment và chương trình `Future.get()` đợi đủ tám task. Tác vụ này chỉ có một context, một bean definition `safeCounter` và không có thread khác thay đổi bean. Thời điểm/tên thread thực thi không xác định nhưng không ảnh hưởng giá trị cuối.

**Thử nghiệm đối chiếu:** Nếu thay field `AtomicLong` trong `SafeCounter` bằng `private long value;` rồi đổi `increment()` thành `return ++value;`, chương trình có data race. Giá trị kết thúc **có thể** nhỏ hơn 8000, nhưng cũng có lần vẫn ra 8000 do lịch chạy; không được dùng một lần thấy đúng để chứng minh mã an toàn. Bản chạy chính ở trên cố ý chỉ dùng cách an toàn để có output đáng tin.

> Khi dùng production, chọn phiên bản Spring được dự án hỗ trợ và cập nhật theo chính sách bảo trì; số phiên bản trong POM ở đây nhằm tái hiện ví dụ.

## 6. Vì sao constructor injection, final và @PostConstruct vẫn cần hiểu đúng?

```java
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final PricePolicy pricePolicy;

    public CheckoutService(PricePolicy pricePolicy) {
        this.pricePolicy = pricePolicy;
    }

    public Money checkout(Order order) {
        return pricePolicy.calculate(order);
    }
}
```

Đây là mã minh họa một component; `PricePolicy`, `Money` và `Order` là các kiểu miền nghiệp vụ cần được định nghĩa trong ứng dụng, không phải chương trình chạy độc lập. Field `pricePolicy` là `final` và được gán trong constructor. Điều đó giúp giữ dependency nhất quán trong cả vòng đời bean và tránh một số vấn đề publication từ khởi tạo không đúng. Nhưng nếu `PricePolicy` chứa `HashMap` bị sửa không đồng bộ, `checkout` vẫn có thể không an toàn.

Vòng đời điển hình của Spring bean là **construct → inject dependencies → initialization callbacks / BeanPostProcessor → publish để sử dụng bình thường**. Có thể khởi tạo cache trong `@PostConstruct`, nhưng không nên để state đang thay đổi tùy tiện sau đó nếu nhiều thread có thể dùng bean. Tránh làm `this` escape từ constructor, chẳng hạn đăng ký vào một global registry hoặc khởi động thread dùng instance chưa khởi tạo xong. Circular dependencies và early references cũng có thể phá giả định về thứ tự khởi tạo đơn giản.

Nếu cache cần cập nhật sau startup, dùng immutable snapshots được publish qua `volatile`/`AtomicReference` hoặc một cơ chế lock phù hợp. Ví dụ:

```java
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

public final class SettingsSnapshot {
    private final AtomicReference<Map<String, String>> current =
            new AtomicReference<>(Map.of());

    public void replace(Map<String, String> fresh) {
        current.set(Map.copyOf(fresh));
    }

    public String lookup(String key) {
        return current.get().get(key);
    }
}
```

`Map.copyOf` tạo bản đồ không cho sửa qua API của nó; `AtomicReference.set/get` publish nguyên snapshot. Nếu key/value là object mutable thì phải kiểm soát chúng riêng; ở đây `String` là immutable. Mỗi lần `lookup` nhìn thấy **một snapshot** hoàn chỉnh; không có bước `clear` rồi `putAll` khiến người đọc nhìn thấy map nửa cập nhật.

## 7. Các scope khác có giải quyết mọi vấn đề đồng thời không?

| Scope | Bean được chia sẻ giữa những ai? | Gợi ý |
| --- | --- | --- |
| `singleton` | Những nơi tham chiếu cùng bean trong cùng container | Chọn stateless, immutable hoặc synchronization rõ ràng |
| `prototype` | Mỗi lần container được yêu cầu tạo bean nhận target mới | Tránh chia sẻ target nếu state có tính riêng tư; lifetime do nơi nhận quản lý |
| `request` | Các thành phần cùng một HTTP request | Tách trạng thái request, nhưng không thay thế quy tắc khi cố ý chia sẻ object |
| `session` | Những HTTP request trong cùng HttpSession | Session có thể xử lý **nhiều request đồng thời**, vẫn cần bảo vệ mutable state |
| `application` | Một ServletContext | State dùng chung, chịu concurrency và giới hạn một application instance |
| `websocket` | Một WebSocket/STOMP session tương ứng | Nhiều message trong cùng session vẫn có thể đòi hỏi đồng bộ tùy luồng xử lý |

Đổi bean sang `prototype` chưa chắc sửa được lỗi:

```java
@Component
@Scope("prototype")
class RequestBuffer {
    private final StringBuilder builder = new StringBuilder();

    public void append(String s) { builder.append(s); }
    public String result() { return builder.toString(); }
}

@Service
class WrongSingletonConsumer {
    private final RequestBuffer buffer;

    WrongSingletonConsumer(RequestBuffer buffer) {
        this.buffer = buffer; // Prototype được resolve một lần khi singleton được tạo.
    }
}
```

Đoạn trên cần các import `org.springframework.stereotype.Component`, `Service` và `org.springframework.context.annotation.Scope`. `WrongSingletonConsumer` vẫn dùng **một** `RequestBuffer` được inject lúc tạo singleton; các thread dùng consumer có thể cùng chạm buffer mutable. Nếu thật sự cần instance mới mỗi lần, inject `ObjectProvider<RequestBuffer>` rồi gọi `getObject()` tại thời điểm thao tác, hoặc áp dụng thiết kế scope phù hợp. Đừng giải quyết race condition bằng thay scope ngẫu nhiên.

Với `@RequestScope` và `@SessionScope`, Spring có thể dùng scoped proxy để singleton gọi đúng target của scope đang hoạt động. Scoped proxy **không** tự bảo đảm target thread-safe và không tự chuyển request context sang một tác vụ `@Async`. Trạng thái của HTTP session còn có thể bị hai HTTP request cùng session cập nhật cùng lúc. Nếu cả hai request sửa chung một giỏ hàng/session bean, cần xác định invariant tương tự singleton.

## 8. Những chỗ dễ tưởng nhầm rằng Spring sẽ đồng bộ

**Spring MVC controller:** `@RestController`/`@Controller` thường là singleton bean. Servlet container có thể dùng nhiều request thread gọi handler trên **cùng object controller**. Không giữ biến instance `currentRequest`, `loggedInUser`, request DTO hay response builder trong controller. Dùng parameter của handler, request attributes, model hoặc service có thiết kế phù hợp.

```java
@RestController
class HelloController {
    // Không lưu lastName ở field singleton.
    @GetMapping("/hello")
    String hello(@RequestParam String name) {
        return "Hello " + name;
    }
}
```

Snippet cần các import Spring MVC (`RestController`, `GetMapping`, `RequestParam`) và web starter; nó minh họa một endpoint đơn giản. Mỗi request có tham số `name` riêng.

**@Transactional:** Transaction được quản lý theo invocation và resource context phù hợp. Nó **không khóa một instance singleton Java**; nó cũng không biến `count++` trên field service thành atomic. Tính nhất quán dữ liệu tại DB còn phụ thuộc isolation level, row/version locking và transaction boundaries. Không giữ JPA `EntityManager`/entity mutable dùng trực tiếp xuyên request theo cách chia sẻ không an toàn.

**@Async, @Scheduled, message listeners:** Cùng bean có thể được gọi từ nhiều task/thread. `@Async` có thể chạy song song; `@Scheduled` có thể tương tác với tác vụ khác, và các cơ chế async không làm field shared tự an toàn. Request context gắn thread theo cách thông thường không tự truyền vào thread pool. Tránh dùng `ThreadLocal` như nơi lưu trạng thái thay cho request scope mà không có cleanup `remove()` trong `finally`, vì worker threads được tái sử dụng.

**@Cacheable:** Cache provider có thể bảo vệ cấu trúc lưu trữ cache, nhưng không tự làm các value object mutable được trả về trở thành thread-safe. Nhiều lời gọi đồng thời cũng có thể cùng tính toán cache miss trừ khi cấu hình/engine hỗ trợ coalescing thích hợp; không dựa vào annotation cache để bảo vệ bất kỳ critical section chung nào.

**Prototype, proxy và @Lazy:** Các cơ chế này quyết định cách tạo, resolve hoặc trì hoãn bean; không tự tạo thread confinement cho mutable field của singleton. Spring AOP proxy cũng không mặc nhiên tuần tự hóa method call.

## 9. Kiểm soát đồng thời nhiều cấp độ

Một thay đổi logic có thể cần bảo vệ tại nhiều tầng:

```text
Request thread A --                   +--> singleton service -- AtomicLong / synchronized
Request thread B --/              |
                                  +--> repository / database
                                               |
                                      transaction + version check
                                               |
                                        nhiều instance/pod
```

- **Trong một JVM:** `synchronized`, `Lock`, `Atomic*`, concurrent collection hoặc thiết kế stateless giữ invariant của object.
- **Qua nhiều JVM/pod:** JVM monitor/AtomicLong không phối hợp giữa hai process. Đối với số tồn kho, số dư, uniqueness, idempotency và giới hạn toàn hệ thống, cần biện pháp tại shared store: unique constraint, optimistic locking (`@Version` với JPA), conditional update, database lock, atomic Redis operation khi phù hợp.
- **Tính nhất quán giữa nhiều hệ thống:** một lock Java không mở rộng ra message broker hay dịch vụ khác. Cần thiết kế idempotency, retry và eventual/strong consistency theo yêu cầu thật.

Ví dụ `AtomicLong` làm bộ đếm trong `SafeCounter` ở mục 5 chính xác **cho bean đó**. Nếu deploy hai bản ứng dụng, mỗi bản có counter riêng; tổng ở cả cluster cần thu thập/đồng bộ bên ngoài JVM.

## 10. Kiểm thử race condition và thread safety

Các bài test đơn luồng không kiểm chứng code concurrent. Với object có invariant rõ ràng, thiết kế test có nhiều task, đồng bộ thời điểm bắt đầu bằng `CountDownLatch` hoặc `CyclicBarrier` và **đợi tất cả Future** trước khi assert trạng thái cuối. Ví dụ `App.java` ở mục 5 làm đúng điều này. Một test an toàn về counter có thể kiểm `finalCount == threadCount * incrementsPerThread`.

Cần phân biệt:

- Test đi qua một số interleaving thực tế, **không chứng minh tổng quát** rằng mọi lịch chạy đều đúng.
- Không dựa vào `Thread.sleep` để ép thứ tự thread; giấc ngủ không bảo đảm giao điểm mong muốn.
- Data race có thể không biểu lộ ở máy dev nhưng xuất hiện khi production tăng traffic, đổi CPU/JVM hoặc điều kiện scheduler.
- Dùng stress testing và các công cụ chuyên biệt như **jcstress** khi cần đánh giá các hành vi Java Memory Model ở mức thấp; riêng bài nghiệp vụ nên bắt đầu bằng invariant và integration/concurrency tests đại diện.
- Kiểm tra việc xử lý exception từ task: `submit` lưu exception vào `Future`; nếu không gọi `get`, test có thể bỏ sót lỗi.
- Đánh giá contention và latency: phương án khóa đúng về kết quả nhưng giữ lock quá lâu có thể gây nghẽn; chỉ tối ưu khi có bằng chứng profiling/load test.

Một checklist review ngắn cho bất kỳ singleton nào có field:

1. Field có thay đổi **sau thời điểm khởi tạo** không?
2. Có đường đi nào cho hai thread cùng truy cập, gồm MVC, scheduled, async, listener, websocket không?
3. Có invariant liên quan nhiều thao tác hoặc nhiều object không?
4. Ai sở hữu state? Đây là dữ liệu của request, session, toàn instance hay toàn cluster?
5. Có guarantee publication/visibility/happens-before không? Mọi đường đọc/ghi có tuân theo cùng cơ chế đồng bộ không?
6. Test đồng thời có kiểm được invariant và lấy exception của các task không?

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Tại sao sai | Cách khắc phục |
| --- | --- | --- |
| `@Service` singleton giữ `currentUser` | Request ghi đè trạng thái của nhau | Dùng method parameter hoặc request context phù hợp |
| `volatile long count; count++;` | `++` không atomic | `AtomicLong.incrementAndGet()` hoặc lock |
| Dùng `HashMap` rồi sửa từ nhiều thread | Cấu trúc và visibility không được bảo vệ | `ConcurrentHashMap` và operation atomic phù hợp |
| Dùng `Collections.synchronizedMap` nhưng kiểm tra-rồi-put ngoài lock | Các method riêng an toàn không làm chuỗi thao tác atomic | Bao toàn bộ compound operation trong cùng lock hoặc dùng `computeIfAbsent` |
| `final List` nên cho rằng bất biến | `final` chỉ cố định reference | Dùng immutable copy hoặc bảo vệ cập nhật |
| Dùng `@Scope("prototype")` để chữa singleton state | Prototype có thể vẫn bị giữ bởi singleton nhận inject một lần | Tách state; lookup prototype tại runtime khi cần |
| Giữ `@SessionScope` mutable mà không khóa | Request song song có thể chia sẻ cùng session bean | Chọn invariant và dùng synchronization phù hợp |
| Cho rằng `@Transactional` tự bảo vệ Java field | Transaction DB không tạo monitor lock cho singleton | Phân biệt Java concurrency với DB consistency |
| Dùng `synchronized` để giữ tổng counter trong nhiều pod | Lock chỉ nằm trong JVM đó | Dùng shared storage/atomic update ngoài JVM |
| Sửa nhiều field bằng nhiều `Atomic*` và coi như một transaction | Không bảo toàn invariant giữa các field | Dùng một atomic snapshot hoặc lock |
| Test với một lần chạy không thấy race | Không quan sát được race không đồng nghĩa không tồn tại | Stress test, invariant-based assertions, review JMM |

## 12. Bài tập tự đánh giá

1. Hai request gọi cùng `@Service` và đều ghi `private String lastUser`. Bean singleton này có an toàn không? Vì sao?
2. Nếu `private final AtomicLong counter` nằm trong singleton, 16 thread mỗi thread gọi `incrementAndGet()` 250 lần, giá trị sau khi tất cả task thành công là bao nhiêu?
3. Vì sao `volatile int counter` chưa đủ để `counter++` chính xác? Nêu một cách sửa.
4. `@SessionScope` có thể bị nhiều thread cùng truy cập không? Lấy ví dụ hai request cùng cookie.
5. Một singleton inject trực tiếp một prototype mutable: khi bean singleton được tạo, có phải mỗi request sử dụng prototype mới không?
6. Hai replica dùng `synchronized` trên các singleton riêng để quản lý cùng SKU còn 1 sản phẩm. Liệu hệ thống tránh được oversell không?
7. Bạn muốn thay một map cấu hình trong runtime mà mọi request luôn đọc trọn một phiên bản nhất quán. Dùng immutable snapshot + `AtomicReference` như thế nào?
8. Khi nào chọn `LongAdder` thay `AtomicLong` và vì sao `sum()` không phù hợp nếu cần một snapshot tuyệt đối chính xác giữa các update?

**Gợi ý đáp án:** (1) Không, field shared mutable tạo race/data leak. (2) 4.000. (3) Read-modify-write gồm nhiều bước; `AtomicInteger.incrementAndGet()` hoặc lock. (4) Có, trình duyệt có thể gửi hai request cùng session đồng thời. (5) Không, prototype được resolve một lần ở lúc injection trừ khi dùng lookup/provider. (6) Không, mỗi lock chỉ trong một JVM; dùng shared store với bảo vệ nhất quán. (7) Tạo immutable `Map.copyOf` rồi publish qua `set`; mỗi reader `get` một snapshot. (8) Dùng cho counters thống kê cập nhật nhiều; `sum` không snapshot atomic khi có cập nhật.

## Tài liệu tham khảo

- Spring Framework Reference — Bean Scopes (singleton, prototype và web scopes): https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework Reference — Using `@PostConstruct` and `@PreDestroy`: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html
- Java SE 17 — `AtomicLong`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html
- Java SE 17 — `ConcurrentHashMap`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html
- Java Language Specification — Chapter 17: Threads and Locks (happens-before, synchronization, volatile): https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
