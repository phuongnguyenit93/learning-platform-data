# Biến cục bộ, trường đối tượng và dữ liệu dùng chung trong Spring bean

## 1. Vì sao trạng thái bean quan trọng khi có nhiều luồng?

Một ứng dụng Spring MVC thường nhận nhiều HTTP request cùng lúc. Mỗi request được servlet container phục vụ bởi một luồng; các luồng có thể đồng thời gọi **cùng một đối tượng** `@RestController`, `@Service` hoặc `@Repository`. Theo mặc định, bean Spring có scope `singleton`: Spring tạo **một instance cho mỗi bean definition trong mỗi `ApplicationContext`** và đưa cùng instance đó cho các thành phần cần dùng.

Điều này **không khiến mọi biến trong bean đều dùng chung**. Phải phân biệt:

- **Biến cục bộ (local variable):** được khai báo trong phương thức/khối; mỗi lần gọi phương thức có bộ biến cục bộ riêng. Giá trị nguyên thủy cục bộ không bị request khác sửa trực tiếp.
- **Trường đối tượng (instance field):** thuộc về một instance. Nếu đó là singleton bean, mọi luồng gọi bean đều nhìn thấy cùng trường ấy; trường có thể an toàn khi bất biến, hoặc có rủi ro khi bị cập nhật đồng thời.
- **Dữ liệu dùng chung (shared data):** bất kỳ đối tượng/trạng thái nào mà nhiều luồng cùng truy cập: có thể là field, đối tượng được tham chiếu từ local variable, static field, cache, collection, database, Redis hoặc file. Nơi khai báo **không quyết định toàn bộ** việc dữ liệu có được chia sẻ hay không.

Ví dụ: hai request cùng gọi `reportService.generate(id)`. Mỗi lời gọi có biến cục bộ `id` riêng, nhưng cả hai cùng gọi trên instance `reportService`. Nếu service giữ `private String currentReportId` và sửa field mỗi request, hai request có thể ghi đè nhau. Nếu service chỉ đọc một cấu hình bất biến và truyền `id` qua tham số xuống repository thì không có trạng thái nghiệp vụ dùng chung trong field.

### Bảng nhận diện trạng thái

| Vị trí dữ liệu | Thuộc về ai? | Có thể bị luồng khác chạm tới? | Thiết kế thường dùng |
| --- | --- | --- | --- |
| `int total` bên trong phương thức | Một lần gọi phương thức | Không đối với chính biến cục bộ ấy | Tính toán tạm thời |
| `List<Item> items` cục bộ | Biến tham chiếu của một lần gọi | **Có**, nếu list được lấy từ field/cache hoặc truyền ra ngoài | Xác định nguồn và ownership của đối tượng được tham chiếu |
| `private final Config config` trong singleton | Một instance bean | Cùng đối tượng được mọi lời gọi tham chiếu | Cấu hình bất biến, xây xong trước khi phục vụ request |
| `private long count` trong singleton | Một instance bean | **Có**, khi các request đọc/ghi | Không dùng `++` không đồng bộ; dùng atomic/lock khi phù hợp |
| `private static Map<...> cache` | Class trong classloader | Có thể chia sẻ qua nhiều bean instance | Quản lý an toàn như mọi trạng thái dùng chung khác |
| Hàng dữ liệu trong DB/Redis | Kho ngoài tiến trình | Có thể chia sẻ giữa **nhiều instance ứng dụng** | Transaction, khóa/điều kiện version, idempotency |

**Lưu ý về JVM:** cách nói “local ở stack, object ở heap” có ích để hình dung nhưng không nên dùng làm tiêu chuẩn an toàn luồng. Một local reference nằm trong lần gọi riêng nhưng vẫn trỏ đến *cùng object* trên heap; đối tượng ấy có thể thoát khỏi phương thức và được nhiều luồng dùng. JVM cũng có các tối ưu hóa nội bộ, nên phân tích theo **ai sở hữu và ai có thể truy cập object** mới chính xác.

## 2. Ví dụ sai: lưu trạng thái từng request vào field singleton

~~~java
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    // Demo anti-pattern: request này có thể ghi đè request khác.
    private String currentUser;

    public String greet(String user) {
        currentUser = user;
        // Giữa hai dòng, luồng khác có thể sửa currentUser.
        return "Xin chào " + currentUser;
    }
}
~~~

Nếu request A gọi `greet("Mai")` và tạm dừng sau phép gán, request B gọi `greet("Linh")` rồi gán vào `currentUser`, khi A chạy tiếp nó **có thể** trả “Xin chào Linh”. Không cần có hai controller instance; chính việc chia sẻ một `GreetingService` singleton là đủ để tạo race. Đoạn trên minh họa một service class, chưa phải chương trình Java độc lập.

Thay bằng thiết kế **không giữ dữ liệu request trong field**:

~~~java
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String user) {
        String normalized = user.strip(); // Cục bộ cho mỗi invocation.
        return "Xin chào " + normalized;
    }
}
~~~

Các lời gọi không ghi vào trạng thái chung. Nhưng nếu `user` được thay bằng một `List` hoặc DTO mutable lấy từ cache, local reference **không sao chép** đối tượng. Ví dụ sau vẫn sửa list chung:

~~~java
// Trích đoạn minh họa trong một phương thức (không độc lập).
List<String> localAlias = sharedList; // sharedList là field.
localAlias.add("report");             // Thực chất sửa sharedList.
~~~

Với dữ liệu cần chỉnh sửa, chọn rõ một trong các hướng: tạo bản sao mỗi request, dùng giá trị bất biến, đồng bộ hóa truy cập, hoặc thực hiện cập nhật nguyên tử tại kho dữ liệu.

## 3. Race condition và Java Memory Model

### 3.1. `count++` gồm nhiều bước

Lệnh `count++` tương đương về logic với đọc giá trị, cộng một, rồi ghi lại. Hai luồng có thể cùng đọc 0 và cùng ghi 1; đáng lẽ sau hai lần tăng là 2 nhưng thực tế chỉ còn 1 (**lost update**). `private` không ngăn hai phương thức của cùng singleton truy cập field; `final` chỉ cấm gán lại field tham chiếu chứ không tự bảo vệ nội dung của object; `volatile` bảo đảm một số quan hệ *visibility/ordering*, **không biến `count++` thành phép tăng nguyên tử**.

Ví dụ Java 17 độc lập sau chủ động dùng hai latch để ép hai luồng cùng đọc giá trị ban đầu, nhờ đó kết quả rõ ràng chứ không dựa vào may rủi lập lịch. Lưu thành `LostUpdateDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public class LostUpdateDemo {
    static class Counter {
        private int value;
        final CountDownLatch bothRead = new CountDownLatch(2);
        final CountDownLatch continueWriting = new CountDownLatch(1);

        void increment() {
            int snapshot = value;  // Cả hai đọc 0 trước khi ghi.
            bothRead.countDown();
            try {
                continueWriting.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            value = snapshot + 1;
        }

        int get() {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        Thread first = new Thread(counter::increment);
        Thread second = new Thread(counter::increment);

        first.start();
        second.start();
        counter.bothRead.await();
        counter.continueWriting.countDown();
        first.join();
        second.join();

        System.out.println("Expected = 2");
        System.out.println("Actual   = " + counter.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LostUpdateDemo.java
java LostUpdateDemo
~~~

Stdout chính xác:

~~~text
Expected = 2
Actual   = 1
~~~

Trong ứng dụng thật, thứ tự chạy không được ép như ví dụ, vì vậy một phép thử tuần tự có thể **không lộ ra lỗi**. Hai `join()` trong demo bảo đảm main đọc kết quả sau khi các luồng kết thúc. Hai latch chỉ giúp tái hiện lost update; chúng không phải cách xây counter production.

### 3.2. Phân biệt ba vấn đề

- **Atomicity (nguyên tử):** một thao tác gồm nhiều bước không bị xen vào theo cách tạo trạng thái sai. `AtomicLong.incrementAndGet()` thực hiện phép tăng nguyên tử cho *một* biến.
- **Visibility (khả năng nhìn thấy):** thay đổi do luồng A thực hiện trở nên quan sát được ở luồng B theo quy tắc *happens-before* của Java Memory Model (JMM); `volatile`, monitor lock, atomics và một số cơ chế đồng bộ tạo ra quan hệ cần thiết.
- **Ordering (thứ tự):** compiler và CPU có thể tối ưu sắp xếp thao tác miễn giữ ngữ nghĩa được JMM cho phép; đồng bộ đúng tạo các ràng buộc thứ tự cần thiết.

`synchronized` cung cấp loại trừ tương hỗ và quan hệ visibility khi dùng **cùng một monitor**. Atomic classes phù hợp với cập nhật độc lập như bộ đếm. `volatile boolean shutdownRequested` phù hợp với tín hiệu một luồng ghi/luồng khác đọc, nhưng không giải quyết phép cập nhật ghép như “kiểm tra rồi thêm” trên nhiều field.

## 4. Ví dụ Spring Boot 3: đặt local, field và request-scoped state đúng chỗ

Ví dụ có thể chạy bằng **Java 17+ và Maven**, dùng Spring Boot 3.3.5 để khởi động web server. Chỉ định nghĩa field unsafe ở đây **để quan sát lỗi**, không dùng endpoint đó cho số liệu production.

Cấu trúc:

~~~text
spring-bean-state/
├── pom.xml
└── src/main/java/com/example/beanstate/
    ├── BeanStateApplication.java
    ├── CounterService.java
    ├── RequestStamp.java
    └── VisitController.java
~~~

### 4.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>spring-bean-state</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. Boot application

`src/main/java/com/example/beanstate/BeanStateApplication.java`:

~~~java
package com.example.beanstate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BeanStateApplication {
    public static void main(String[] args) {
        SpringApplication.run(BeanStateApplication.class, args);
    }
}
~~~

### 4.3. Một singleton chứa cả field an toàn và không an toàn

`src/main/java/com/example/beanstate/CounterService.java`:

~~~java
package com.example.beanstate;

import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class CounterService {
    // Chỉ để minh họa race: đọc/cộng/ghi không nguyên tử.
    private long unsafeTotal;

    // Cùng là field singleton, nhưng phép tăng là nguyên tử.
    private final AtomicLong safeTotal = new AtomicLong();

    // Dữ liệu chỉ đọc, giá trị String bất biến.
    private final Map<String, String> labels = Map.of(
            "report", "Báo cáo",
            "sync", "Đồng bộ"
    );

    public long unsafeIncrement() {
        return ++unsafeTotal;
    }

    public long safeIncrement() {
        return safeTotal.incrementAndGet();
    }

    public String labelFor(String type) {
        return labels.getOrDefault(type, "Khác");
    }
}
~~~

Việc cùng singleton chia sẻ `safeTotal` là **có chủ đích**: mọi request tăng cùng bộ đếm và `AtomicLong` bảo vệ phép tăng. `final` bảo đảm không gán lại tham chiếu `safeTotal`; chính `AtomicLong` mới bảo vệ cập nhật. `labels` không bị sửa sau khi tạo và dùng `Map.of` với các `String` bất biến, nên có thể đọc đồng thời an toàn khi bean được Spring khởi tạo và công bố bình thường.

### 4.4. Một bean mới theo mỗi HTTP request

`src/main/java/com/example/beanstate/RequestStamp.java`:

~~~java
package com.example.beanstate;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestStamp {
    private final String id = UUID.randomUUID().toString();

    public String id() {
        return id;
    }
}
~~~

`@RequestScope` tạo đối tượng `RequestStamp` mới cho mỗi HTTP request. Annotation này mặc định sử dụng scoped proxy, vì thế singleton controller có thể inject `RequestStamp`: thực chất nó giữ **proxy**, còn proxy tìm đối tượng thuộc request hiện tại khi được gọi. Hai lần gọi `id()` trong cùng request cho cùng giá trị; hai request mới gần như chắc chắn có ID khác nhau.

`@RequestScope` không mặc nhiên khả dụng ở luồng chạy `@Async`, `@Scheduled` hoặc trong một test không có HTTP request context. Trước khi rời luồng HTTP, hãy trích xuất dữ liệu cụ thể (ví dụ request ID) rồi truyền bằng tham số cho worker.

### 4.5. Controller singleton nhưng local thuộc từng lần gọi

`src/main/java/com/example/beanstate/VisitController.java`:

~~~java
package com.example.beanstate;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VisitController {
    private final CounterService counters;
    private final RequestStamp requestStamp;

    public VisitController(CounterService counters, RequestStamp requestStamp) {
        this.counters = counters;
        this.requestStamp = requestStamp;
    }

    @GetMapping("/visit")
    public Map<String, Object> visit(
            @RequestParam(defaultValue = "Mai") String name) {
        String normalized = name.strip().toLowerCase(Locale.ROOT);
        int length = normalized.length();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("name", normalized);
        result.put("length", length);
        result.put("requestId", requestStamp.id());
        result.put("label", counters.labelFor("report"));
        return result;
    }

    @GetMapping("/counter/unsafe")
    public Map<String, Long> unsafe() {
        return Map.of("value", counters.unsafeIncrement());
    }

    @GetMapping("/counter/safe")
    public Map<String, Long> safe() {
        return Map.of("value", counters.safeIncrement());
    }
}
~~~

`normalized`, `length` và `result` là local của từng lần gọi `visit()`; mỗi request tạo map mới. `counters` là field của controller, nhưng nó tham chiếu cùng service singleton; `requestStamp` cũng là field nhưng tham chiếu **scoped proxy** phục vụ dữ liệu riêng của mỗi request. Không thể nhìn mỗi chữ `private` hoặc `final` mà kết luận object được tham chiếu luôn thread-safe.

### 4.6. Chạy và quan sát

Trong thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Trong terminal khác:

~~~bash
curl "http://localhost:8080/visit?name=%20Mai%20"
curl "http://localhost:8080/visit?name=%20Mai%20"
curl http://localhost:8080/counter/safe
curl http://localhost:8080/counter/safe
curl http://localhost:8080/counter/unsafe
~~~

Phản hồi của `/visit` có dạng:

~~~json
{
  "name": "mai",
  "length": 3,
  "requestId": "550e8400-e29b-41d4-a716-446655440000",
  "label": "Báo cáo"
}
~~~

UUID ở đây chỉ là **ví dụ**; mỗi request nhận ID mới. Trong một ứng dụng mới khởi động, không có request nào khác, hai lần gọi tuần tự đầu tiên đến `/counter/safe` sẽ trả `{"value":1}` rồi `{"value":2}`. Bộ đếm unsafe cũng *có thể* cho kết quả đúng khi gọi tuần tự; lỗi mất cập nhật chỉ xuất hiện dưới các lịch xen kẽ nhất định. Hai bộ đếm bắt đầu độc lập từ 0 và mất trạng thái khi khởi động lại.

Nếu chạy nhiều request song song, `unsafeTotal` có thể bỏ sót lần tăng, trong khi `safeTotal.incrementAndGet()` không mất lần tăng **trong cùng instance**. Không dùng giá trị trả về của endpoint unsafe như một metric có độ tin cậy. Thử nghiệm hai latch ở mục 3 cung cấp bằng chứng lost update có kết quả xác định.

## 5. Chọn chiến lược phù hợp với dạng trạng thái

### 5.1. Ưu tiên singleton stateless và immutable input/output

Thiết kế dễ bảo trì nhất là bean giữ những dependency/cấu hình dùng chung, còn dữ liệu thay đổi theo request nằm trong tham số, local variable, DTO bất biến hoặc DB. Với Java 17, có thể dùng `record` cho kết quả, ví dụ `record ReportResult(String id, long total) {}`. Record chỉ bảo đảm các thành phần tham chiếu là `final`; nếu chứa `List` mutable thì **không tự trở thành deeply immutable**. Dùng `List.copyOf`, `Map.copyOf` và các phần tử bất biến khi cần snapshot thực sự.

### 5.2. Khi cần counter hoặc cờ trạng thái trong một instance

| Nhu cầu | Công cụ thường dùng | Giới hạn |
| --- | --- | --- |
| Tăng ID/counter của **một instance** | `AtomicLong.incrementAndGet()` | Không chia sẻ qua các pod, mất khi restart |
| Thu thập metric đếm tần suất ghi lớn | `LongAdder.increment()` | `sum()` dưới tải đồng thời không phải snapshot nguyên tử |
| Cờ bật/tắt một luồng quan sát | `volatile boolean` hoặc `AtomicBoolean` | Không bảo vệ đồng thời nhiều trường |
| Cập nhật nhiều trường phải nhất quán | `synchronized`, `ReentrantLock` hoặc immutable snapshot thay nguyên tử | Khóa chỉ trong tiến trình/instance |
| Map cùng sửa từ nhiều luồng | `ConcurrentHashMap`, `compute`, `putIfAbsent` | Các thao tác nhiều bước ngoài map vẫn cần phối hợp |

Ví dụ bộ đếm theo loại công việc trong cùng một service (đoạn phương thức không độc lập):

~~~java
private final java.util.concurrent.ConcurrentMap<String,
        java.util.concurrent.atomic.AtomicLong> byType =
        new java.util.concurrent.ConcurrentHashMap<>();

public long record(String type) {
    return byType.computeIfAbsent(type,
            ignored -> new java.util.concurrent.atomic.AtomicLong())
            .incrementAndGet();
}
~~~

`ConcurrentHashMap` bảo vệ cấu trúc map và `AtomicLong` bảo vệ biến đếm của từng key. Đừng thay bằng mẫu `if (!map.containsKey(k)) map.put(k, new Counter())` nếu nhiều luồng có thể cùng khởi tạo một key. Khi một cập nhật phải sửa *nhiều thuộc tính liên quan*, các atomic riêng lẻ không bảo đảm một transaction tổng thể: cân nhắc lock hoặc cấu trúc trạng thái bất biến được thay nguyên tử.

### 5.3. Snapshot dữ liệu dùng chung kiểu đọc nhiều/ghi ít

Để công bố một bộ cấu hình đã xây dựng đầy đủ cho nhiều luồng đọc, có thể thay **cả tham chiếu**:

~~~java
// Trích đoạn nằm trong class quản lý cấu hình.
private volatile Map<String, String> snapshot = Map.of();

public void replaceSnapshot(Map<String, String> next) {
    snapshot = Map.copyOf(next);
}

public String find(String key) {
    return snapshot.get(key);
}
~~~

Với `String` key/value bất biến, từng lần `find` thấy một snapshot nhất quán. `volatile` hỗ trợ visibility khi thay tham chiếu; `Map.copyOf` tạo bản sao không thể sửa qua API của map. Nhưng hai writer cùng dựa vào snapshot cũ có thể ghi đè lần thay của nhau; cần version, CAS hoặc lock nếu phép thay phải kiểm tra điều kiện. Nếu giá trị là object mutable, sao chép map **không tự sao chép sâu** các giá trị.

### 5.4. Scope không thay thế bảo đảm an toàn luồng

| Spring scope | Vòng đời | Cần chú ý |
| --- | --- | --- |
| `singleton` (mặc định) | Một instance mỗi bean definition trong context | Có thể bị nhiều request gọi đồng thời; tốt nhất stateless |
| `prototype` | Spring tạo bean khi được yêu cầu | Inject trực tiếp vào singleton thường **chỉ tạo một lần tại lúc inject**; cần `ObjectProvider<T>` hoặc provider khi muốn lấy instance mới mỗi lần |
| `request` | Một instance mỗi HTTP request có scope hoạt động | Phù hợp request state; có thể không tồn tại trên luồng async/scheduled |
| `session` | Một instance mỗi HTTP session | Hai tab hoặc hai request cùng session vẫn có thể chạy đồng thời; mutable session state vẫn cần chú ý |

Scope kiểm soát **vòng đời và cách tra cứu bean**, không mang lại tự động các bảo đảm atomicity, visibility, transaction hay đồng bộ giữa nhiều instance. `@Scope("prototype")` cũng không có nghĩa Spring tự dọn mọi tài nguyên của prototype; thành phần sử dụng phải quản lý vòng đời thích hợp.

### 5.5. `ThreadLocal` là trạng thái gắn với luồng, không đồng nghĩa request

`ThreadLocal<T>` giữ giá trị riêng theo **Java thread**. Servlet container và `TaskExecutor` thường tái sử dụng luồng cho nhiều request/công việc, nên một giá trị quên xóa có thể rò sang lần xử lý sau. Nếu thật sự dùng, cần `remove()` trong `finally`:

~~~java
// Trích đoạn minh họa, không phải chương trình độc lập.
private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

void withTrace(String traceId, Runnable work) {
    TRACE_ID.set(traceId);
    try {
        work.run();
    } finally {
        TRACE_ID.remove();
    }
}
~~~

Không dùng `ThreadLocal` để thay database cho trạng thái nghiệp vụ; cũng không giả định giá trị `ThreadLocal` tự đi theo sang luồng `@Async` hoặc `CompletableFuture`. Logging MDC, SecurityContext và transaction context thường gắn với luồng và cần cơ chế propagation được cấu hình phù hợp; cách đơn giản nhất cho job nền là truyền dữ liệu thiết yếu như ID qua tham số.

## 6. Dữ liệu dùng chung vượt khỏi một bean và một JVM

Dữ liệu trong Java field, `AtomicLong` hay `synchronized` chỉ bảo vệ tình huống **trong một instance/proccess** như đã thiết kế. Nếu triển khai 3 pod, mỗi pod có `CounterService` và `safeTotal` riêng; client được load balancer chuyển qua pod khác có thể thấy giá trị đếm khác. `static` cũng không làm cho biến trở thành trạng thái phân tán.

Khi cần một tổng số đơn hàng nhất quán trên toàn hệ thống, lưu tổng trong DB hoặc kho phù hợp và bảo đảm cập nhật nguyên tử ở đó. Ví dụ SQL đơn giản cho một dòng:

~~~sql
UPDATE report_stats
SET processed_count = processed_count + 1
WHERE id = 1;
~~~

Trong một DB giao dịch phù hợp, câu UPDATE được thực thi với cơ chế đồng thời của DB, thay vì đọc số lên Java rồi ghi đè bằng giá trị cũ. Với nghiệp vụ kiểm tra số dư, tồn kho, hoặc thay đổi nhiều dòng, cần transaction, điều kiện cập nhật, isolation/locking hoặc optimistic version tùy quy tắc dữ liệu; `synchronized` của một bean không khóa được các process khác.

Với JPA, entity managed và `EntityManager` gắn với persistence context/transaction; **không lưu entity mutable đang managed hoặc `EntityManager` như trạng thái tùy ý chia sẻ xuyên request**. Spring Data repository có thể là singleton proxy nhưng operations phải dùng đúng transaction/persistence context, khác với việc tự giữ một object JPA dùng chung. Cần phân biệt cơ chế đồng bộ trong Java với giao dịch và isolation ở database.

## 7. Những hiểu lầm phổ biến và cách kiểm tra

| Hiểu lầm/triệu chứng | Điều cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| “Controller là singleton nên local bị request khác sửa” | Local thuộc từng invocation; có tham chiếu đến object shared hay không? | Giữ dữ liệu request trong local/DTO, không lưu `currentUser` vào field |
| “Field `private final List` là thread-safe” | `final` chỉ cố định tham chiếu, `List` có còn bị mutate? | Dùng collection bất biến hoặc cơ chế đồng bộ thích hợp |
| “Đặt `volatile int counter` là đủ” | Có phép `++` hoặc check-then-act không? | `AtomicInteger`, `synchronized` hoặc update DB nguyên tử |
| “`ConcurrentHashMap` giúp mọi thao tác an toàn” | Có quy trình `get → sửa object → put` gồm nhiều bước? | Dùng `compute`, immutable value, lock/transaction phù hợp |
| “`@RequestScope` chạy trong mọi worker” | Worker có request context đang active không? | Truyền dữ liệu request cần thiết vào tác vụ |
| “`prototype` được inject mỗi lời gọi” | Bean prototype được inject trực tiếp vào singleton khi nào? | Dùng provider mỗi khi cần bean mới |
| “Một counter đúng trên dev sẽ đúng trên cluster” | Có nhiều process/pod hoặc restart không? | Dùng kho chia sẻ, transaction/version, idempotency |
| “Test 10 request đều qua nên không có race” | Test có chạy thực sự đồng thời và có xác minh invariant không? | Thử concurrency có kiểm soát/latches, stress test, theo dõi lỗi |

### Cách tự đánh giá một bean

1. Liệt kê từng **instance/static field**: ai gán, khi nào, có sửa sau khi startup không, object được tham chiếu có mutable không?
2. Với mỗi public method, phân biệt **dữ liệu riêng của lời gọi** với những tham chiếu thoát ra service/cache/entity bên ngoài.
3. Đánh dấu mọi thao tác “đọc → kiểm tra → ghi”, “nếu chưa có thì thêm”, “tăng bộ đếm”: chúng có cần nguyên tử không?
4. Xác định phạm vi chia sẻ: **một lời gọi**, **một request**, **một singleton trong một context**, **một JVM**, hay **toàn cụm**.
5. Chọn biện pháp nhỏ nhất đáp ứng invariant: local/immutable trước; sau đó atomic, lock hoặc DB transaction khi thực sự cần. Đo hiệu năng nếu dùng lock trên đường xử lý nóng.
6. Kiểm thử nhiều request cùng lúc; xác minh trạng thái cuối, không chỉ mã HTTP. Thử chạy nhiều instance nếu dữ liệu cần đồng bộ toàn cụm.

### Tự kiểm tra kiến thức

- Một singleton `@Service` chỉ có các dependency `final` và phương thức dùng local variable đã chắc chắn an toàn luồng chưa? Những dependency đó có thể tự giữ mutable state không?
- Biến local `List<String> copied = cache.get(key)` có chắc là danh sách riêng? Phải làm gì nếu cần thay đổi danh sách?
- Vì sao `volatile long total; total++;` vẫn có thể mất lần tăng, còn `AtomicLong.incrementAndGet()` thì không?
- `@RequestScope` và `@SessionScope` khác nhau thế nào khi hai request cùng đến? Scope nào bảo đảm tự động thread-safe?
- Khi chuyển từ một instance sang ba pod, vì sao counter trong bean không còn là bộ đếm toàn hệ thống? Thiết kế DB/Redis cần thêm điều kiện gì để retry không tính trùng?

**Quy tắc thiết kế:** giữ Spring singleton bean càng *stateless* càng tốt; phân biệt biến cục bộ với **object mà biến đó trỏ tới**; bất kỳ mutable state nào mà nhiều luồng có thể chạm tới đều phải có ownership và cơ chế phối hợp rõ ràng.