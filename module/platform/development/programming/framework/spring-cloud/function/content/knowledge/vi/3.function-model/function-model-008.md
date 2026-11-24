# Vòng đời singleton, trạng thái dùng chung và an toàn luồng

Trong **SPRING_CLOUD_FUNCTION**, một hàm nghiệp vụ được biểu diễn bằng **Supplier<T>**, **Function<T, R>** hoặc **Consumer<T>** và thường được đăng ký dưới dạng Spring bean. Mặc định, bean có **scope singleton**: một đối tượng được Spring quản lý trong một application context và có thể được dùng lại cho nhiều lần gọi. Nếu cùng một bean được adapter HTTP, Spring Cloud Stream hoặc serverless kích hoạt nhiều lần, trạng thái nằm trong bean hoặc đối tượng được lambda giữ tham chiếu có thể bị nhiều lời gọi cùng truy cập.

Đó là lý do hiểu **vòng đời singleton, trạng thái dùng chung và an toàn luồng (thread safety)** là điều kiện quan trọng để tái sử dụng logic nghiệp vụ độc lập với giao thức. Bài thuộc chương **Mô hình hàm**, đi từ cách Spring tạo bean tới các lỗi race condition, giải pháp stateless, các trường hợp phải quản lý trạng thái và cách kiểm thử.

## 1. Singleton trong Spring nghĩa là gì?

Trong Spring, **singleton scope** có nghĩa Spring thông thường tạo và quản lý **một bean instance theo mỗi bean definition trong một application context**. Một tên bean không đồng nghĩa một instance duy nhất cho mọi tiến trình, máy chủ hoặc application context trên thế giới.

| Ngữ cảnh | Phạm vi của một singleton bean |
| --- | --- |
| Một Spring application context | Các lần lấy cùng bean thường nhận cùng instance |
| Hai Spring application context trong một JVM | Mỗi context có thể có singleton riêng |
| Hai replica của ứng dụng | Mỗi replica có application context và singleton riêng |
| Serverless cold start hoặc instance khác | Có thể khởi tạo context và bean mới |
| HTTP request, message mới | Không mặc định tạo lại bean singleton |

Trong trường hợp khai báo:

~~~java
@Bean("normalizeCode")
Function<String, String> normalizeCode() {
    return input -> input.trim().toUpperCase(java.util.Locale.ROOT);
}
~~~

Spring gọi phương thức **normalizeCode()** khi tạo bean (theo quá trình khởi tạo phù hợp), sau đó giữ đối tượng Function mà phương thức trả về. Khi adapter hoặc FunctionCatalog gọi **apply(...)**, phần thân lambda mới thực hiện phép chuẩn hóa.

~~~mermaid
flowchart TD
    A["ApplicationContext khởi tạo"] --> B["@Bean normalizeCode()"]
    B --> C["Một Function bean singleton"]
    C --> D["Lời gọi apply #1"]
    C --> E["Lời gọi apply #2"]
    C --> F["Lời gọi apply #3"]
~~~

**Singleton không có nghĩa là chỉ một lời gọi được xử lý tại một thời điểm.** Spring không tự đặt một khóa bao quanh **Function.apply(...)**, **Supplier.get()** hoặc **Consumer.accept(...)** chỉ vì đối tượng là bean singleton. Độ đồng thời thực tế phụ thuộc adapter, thread pool, scheduler, binder và cấu hình triển khai.

Cũng không được nhầm **singleton scope của bean** với **Singleton pattern trong Java**: Spring quản lý phạm vi đối tượng trong container, không yêu cầu lớp Java phải có private constructor hoặc static **getInstance()**.

## 2. Phân biệt ba mốc thời gian

Để phân tích bug về trạng thái, cần phân biệt:

1. **Tạo bean:** Spring thực thi factory method **@Bean** hoặc constructor và tiêm phụ thuộc.
2. **Tạo đối tượng hàm:** lambda, method reference hoặc lớp **implements Function** được trả về/đăng ký; với bean singleton, đối tượng này thường được dùng lại.
3. **Gọi hàm:** adapter hoặc mã Java kích hoạt **get()**, **apply(input)** hay **accept(input)**. Hoạt động này có thể diễn ra nhiều lần và đồng thời.

Ví dụ Supplier trả thời gian:

~~~java
@Bean
Supplier<Instant> startupTime(Clock clock) {
    Instant snapshot = clock.instant();
    return () -> snapshot;
}

@Bean
Supplier<Instant> currentTime(Clock clock) {
    return clock::instant;
}
~~~

Giả sử đã import **java.time.Clock**, **java.time.Instant** và **java.util.function.Supplier**:

- **startupTime** tính **snapshot** ngay khi bean được tạo, nên các lần gọi **get()** trả cùng thời điểm.
- **currentTime** giữ tham chiếu tới phương thức **clock.instant()**, được gọi ở mỗi lần **get()**.
- Cả hai bean vẫn có thể là singleton. **Độ mới của kết quả** phụ thuộc vị trí thực thi phép tính, không phụ thuộc việc chuyển sang scope prototype.

Tương tự, ở **Function<T, R>**, biến được khai báo bên trong thân **apply(...)** là biến cục bộ của mỗi lời gọi; còn đối tượng ở ngoài lambda được **capture** có thể được chia sẻ giữa những lời gọi.

## 3. Trạng thái dùng chung xuất hiện ở đâu?

Trạng thái dùng chung là dữ liệu có thể bị nhiều lời gọi đọc hoặc cập nhật thông qua cùng một đối tượng. Nó có thể nằm ở:

- Field mutable của một bean singleton.
- Biến cục bộ mutable ở phương thức **@Bean**, nhưng được lambda giữ tham chiếu (*captured variable*).
- Service, cache, repository hoặc client được inject vào Function.
- Collection dùng chung như **ArrayList**, **HashMap**, một DTO mutable hoặc bộ đếm.
- Bộ nhớ toàn cục (**static field**), singleton khác hoặc vùng nhớ chia sẻ trong cùng instance.

Ví dụ tạo một Function có lỗi:

~~~java
@Bean("unsafeCounter")
Function<String, Long> unsafeCounter() {
    long[] counter = {0L};

    return input -> {
        long next = counter[0] + 1;
        counter[0] = next;
        return next;
    };
}
~~~

Mặc dù **counter** là biến cục bộ của phương thức **unsafeCounter()**, mảng **long[]** được lambda giữ tham chiếu sau khi phương thức kết thúc. Các lời gọi tới cùng Function bean cập nhật **cùng một phần tử mảng**.

Khi có hai thread:

~~~text
Giá trị ban đầu: counter[0] = 8

Thread A                  Thread B
----------------------    ----------------------
đọc counter[0] = 8
                          đọc counter[0] = 8
tính next = 9
                          tính next = 9
ghi counter[0] = 9
                          ghi counter[0] = 9

Kết quả thực: 9; kỳ vọng sau hai lần tăng: 10
~~~

Đây là **lost update**, một dạng **race condition**. Phép toán đọc–cộng–ghi không phải một thao tác nguyên tử, dù cú pháp chỉ chiếm vài dòng.

## 4. Ba khía cạnh của thread safety

Một hàm có an toàn khi gọi đồng thời hay không phụ thuộc vào dữ liệu và những thao tác truy cập chúng.

| Khía cạnh | Câu hỏi | Ví dụ rủi ro |
| --- | --- | --- |
| **Atomicity** | Một chuỗi thao tác có cần xảy ra như một đơn vị không? | **counter++** gồm đọc, cộng, ghi |
| **Visibility** | Thread khác có nhìn thấy cập nhật đúng lúc không? | Field mutable thiếu quan hệ đồng bộ phù hợp |
| **Ordering** | Các bước có cần giữ thứ tự quan sát hay thực thi không? | Ghi trạng thái trước khi phát event nhưng hai thread xen kẽ |

**volatile** có thể giúp bảo đảm khả năng nhìn thấy và một số quy tắc thứ tự truy cập, nhưng **không làm cho counter++ trở thành phép tăng nguyên tử**. Thêm **volatile** vào field rồi giữ nguyên phép toán tăng vẫn không giải quyết lost update.

Tương tự, **Collections.synchronizedList(...)** bảo vệ từng thao tác theo hợp đồng collection đó; một chuỗi thao tác như “kiểm tra chưa tồn tại rồi thêm” vẫn có thể cần đồng bộ toàn bộ vùng thao tác. **ConcurrentHashMap** bảo vệ các phép toán đồng thời được hỗ trợ, nhưng không tự bảo đảm một workflow nhiều bước hoặc một transaction qua database/broker.

Phân biệt hai thuộc tính:

- **Thread-safe:** cấu trúc dữ liệu hoặc logic không bị hỏng và giữ các bất biến đã cam kết khi có nhiều thread truy cập.
- **Idempotent:** lặp lại cùng một yêu cầu/sự kiện không gây thêm tác dụng nghiệp vụ không mong muốn.

Một bộ đếm **AtomicLong** có thể thread-safe nhưng **không idempotent**: nếu cùng sự kiện bị gửi lại, nó vẫn tăng lần nữa.

## 5. Giải pháp ưu tiên: Function stateless với DTO bất biến

Trong phần lớn logic biến đổi nghiệp vụ, cách đơn giản và dễ kiểm thử nhất là **tránh trạng thái mutable chung**. Mỗi lời gọi nhận input, tính toán bằng biến cục bộ và trả output mới.

Ví dụ ứng dụng Java 17+ dùng Spring Boot và Spring Cloud Function. Để tiện học, các kiểu dữ liệu đặt trong cùng một file **SafeFunctionsApplication.java**:

~~~java
package example.function;

import java.math.BigDecimal;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SafeFunctionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeFunctionsApplication.class, args);
    }

    public record PriceRequest(
        String sku,
        int quantity
    ) {}

    public record PriceQuote(
        String sku,
        int quantity,
        BigDecimal unitPrice,
        BigDecimal total
    ) {}

    public static final class PriceCatalog {
        private final Map<String, BigDecimal> prices;

        public PriceCatalog(Map<String, BigDecimal> prices) {
            this.prices = Map.copyOf(prices);
        }

        public BigDecimal getUnitPrice(String sku) {
            BigDecimal price = prices.get(sku);
            if (price == null) {
                throw new IllegalArgumentException(
                    "Unknown SKU: " + sku);
            }
            return price;
        }
    }

    public static final class PriceService {
        private final PriceCatalog catalog;

        public PriceService(PriceCatalog catalog) {
            this.catalog = catalog;
        }

        public PriceQuote quote(PriceRequest request) {
            if (request == null
                    || request.sku() == null
                    || request.sku().isBlank()
                    || request.quantity() <= 0) {
                throw new IllegalArgumentException(
                    "Invalid price request");
            }

            String sku = request.sku()
                .trim().toUpperCase(Locale.ROOT);

            BigDecimal unitPrice =
                catalog.getUnitPrice(sku);

            // Tất cả biến sau đây thuộc một lời gọi.
            BigDecimal total = unitPrice.multiply(
                BigDecimal.valueOf(request.quantity()));

            return new PriceQuote(
                sku, request.quantity(), unitPrice, total);
        }
    }

    @Bean
    PriceCatalog priceCatalog() {
        return new PriceCatalog(Map.of(
            "BOOK", new BigDecimal("85000"),
            "PEN", new BigDecimal("12000")
        ));
    }

    @Bean
    PriceService priceService(PriceCatalog catalog) {
        return new PriceService(catalog);
    }

    @Bean("calculatePrice")
    Function<PriceRequest, PriceQuote> calculatePrice(
            PriceService service) {
        return service::quote;
    }

    // Demo cho trạng thái cần tăng nguyên tử trong MỘT instance.
    @Bean("newReference")
    Supplier<String> newReference() {
        AtomicLong counter = new AtomicLong();
        return () -> "demo-" + counter.incrementAndGet();
    }
}
~~~

Với input:

~~~json
{
  "sku": "book",
  "quantity": 3
}
~~~

**calculatePrice** trả dữ liệu tương đương:

~~~json
{
  "sku": "BOOK",
  "quantity": 3,
  "unitPrice": 85000,
  "total": 255000
}
~~~

Vì sao **calculatePrice** phù hợp cho các lời gọi đồng thời?

1. **PriceRequest** và **PriceQuote** là Java record; các thành phần trong ví dụ đều là kiểu bất biến hoặc được dùng như bất biến.
2. **PriceCatalog** giữ một **Map.copyOf(...)** bất biến với các giá trị **BigDecimal** bất biến.
3. **PriceService** có field **final**, tham chiếu tới catalog chỉ đọc; bản thân service không ghi lại request hiện tại.
4. Các biến **sku**, **unitPrice**, **total** nằm trong **quote(...)** và được tính riêng cho mỗi lời gọi.
5. Bean Function được dùng lại nhưng không chứa một bộ đếm hoặc danh sách mutable phục vụ tính giá.

Tính thread-safe ở đây xuất phát từ **thiết kế và các đối tượng liên quan**, không tự động đến từ **@Bean**, **final** hay **record**. Một record chứa **List mutable** hoặc một field **final** trỏ tới **HashMap mutable** vẫn có thể để lộ trạng thái dùng chung.

## 6. Khi cần trạng thái chung: chọn cơ chế phù hợp

Không phải mọi Function đều có thể stateless. Bộ đếm, cache, giới hạn đồng thời hoặc trạng thái một kết nối có thể cần chia sẻ giữa các lời gọi. Cơ chế bảo vệ phải khớp nhu cầu.

| Nhu cầu | Cách tiếp cận thường phù hợp | Giới hạn |
| --- | --- | --- |
| Tăng bộ đếm trong một JVM | **AtomicLong**, **LongAdder** | Chỉ có hiệu lực trong instance hiện tại |
| Ánh xạ key/value được truy cập đồng thời | **ConcurrentHashMap** và các thao tác nguyên tử thích hợp | Không thay thế transaction nhiều bước |
| Bảo vệ một bất biến nhiều field | **synchronized** hoặc **Lock** với vùng bảo vệ nhỏ, rõ ràng | Có thể tăng độ trễ, giảm throughput |
| Cache dữ liệu | Cache có thread safety, TTL và chính sách tải lại | Cache không tự đồng nhất giữa replica |
| Trình tự sự kiện nghiệp vụ | Cơ chế ordering/partition hoặc store có version | Không chỉ phụ thuộc synchronized trong một JVM |
| Số thứ tự duy nhất qua nhiều replica | Database sequence, bộ sinh ID phân tán phù hợp | AtomicLong trong một bean không bảo đảm toàn hệ thống |
| Dữ liệu nghiệp vụ phải bền vững | Database, giao dịch, unique constraint | Bộ nhớ singleton mất khi ứng dụng restart |

Trong ví dụ **newReference**, mỗi **Supplier.get()** gọi **AtomicLong.incrementAndGet()**; giá trị tăng an toàn khi nhiều thread cùng truy cập **cùng một Supplier instance**.

~~~java
Supplier<String> ref = new SafeFunctionsApplication().newReference();

String first = ref.get();  // "demo-1"
String second = ref.get(); // "demo-2"
~~~

Tuy nhiên, **demo-1** có thể xuất hiện lần nữa ở một replica khác hoặc khi ứng dụng khởi động lại. Vì vậy, **không dùng bộ đếm này làm mã giao dịch hoặc ID toàn cục trong hệ thống nhiều instance**. Nếu thay **AtomicLong** bằng **LongAdder**, việc cộng và đọc có thể phù hợp thống kê throughput, nhưng **sum()** không phải snapshot nguyên tử đồng thời với các update.

### synchronized không tự giải quyết hệ thống phân tán

Ví dụ:

~~~java
public final class LocalSequence {
    private long current;

    public synchronized long next() {
        return ++current;
    }
}
~~~

**next()** an toàn nếu tất cả lời gọi truy cập **cùng một LocalSequence trong một JVM**. Khi chạy ba instance ứng dụng, mỗi instance lại có biến **current** riêng. Một khóa Java không tự khóa những JVM ở các máy khác nhau.

## 7. Bẫy thường gặp khi lambda capture trạng thái

Một lambda có vẻ là một hàm thuần vì không có field của lớp, nhưng vẫn có thể capture một đối tượng mutable:

~~~java
@Bean
Function<String, Integer> countRequests() {
    java.util.List<String> requests =
        new java.util.ArrayList<>();

    return value -> {
        requests.add(value);
        return requests.size();
    };
}
~~~

Ở đây, **requests** tồn tại lâu bằng đối tượng Function bean do lambda giữ tham chiếu. **ArrayList** không được thiết kế để các thread thêm phần tử đồng thời mà thiếu đồng bộ phù hợp. Kết quả có thể sai, trạng thái nội bộ bị ảnh hưởng hoặc xuất hiện exception.

Một cách sửa nếu nghiệp vụ thực sự chỉ cần đếm lời gọi:

~~~java
@Bean
Function<String, Long> countRequestsSafely() {
    AtomicLong calls = new AtomicLong();
    return ignored -> calls.incrementAndGet();
}
~~~

Nhưng nếu chỉ cần **thống kê vận hành**, nên sử dụng cơ chế metrics phù hợp thay vì đặt bộ đếm nghiệp vụ trong hàm. Nếu cần lưu toàn bộ request, phải xét yêu cầu bảo mật, bộ nhớ, độ bền, concurrency và retention; đổi sang **Collections.synchronizedList** chưa xử lý tất cả vấn đề đó.

**Quy tắc xem code:** kiểm tra cả field, dependency được inject và biến bị lambda capture. Việc không có field trong lớp **@Configuration** chưa đủ để kết luận Function stateless.

## 8. Lời gọi từ HTTP, sự kiện và serverless có thể khác nhau

Cùng một Function bean có thể được các adapter gọi với chiến lược concurrency khác nhau.

| Môi trường | Điều có thể xảy ra | Vấn đề cần kiểm soát |
| --- | --- | --- |
| **HTTP** | Nhiều request được xử lý bởi nhiều thread trên cùng instance | Shared mutable state, request context, timeout |
| **Spring Cloud Stream** | Binder gọi hàm theo cơ chế consumer, có thể cấu hình đồng thời hoặc chạy nhiều instance | Thứ tự message, retry, partition, idempotency |
| **Serverless** | Runtime có thể tái sử dụng instance hoặc tạo nhiều instance song song | State bị reset, dữ liệu khác nhau giữa instance, retry |
| **Reactive adapter** | Các phần tử xử lý qua publisher và có thể đổi scheduler/thread | Shared state, subscription, backpressure, thread hopping |

Từ **chữ ký Function<T, R>** không thể kết luận số thread hoặc giới hạn concurrency. Một binder có thể mặc định tiêu thụ theo một luồng trong một cấu hình, nhưng khi thay binder, partition hoặc số instance, điều kiện đó có thể thay đổi.

**Thiết kế đúng nên được kiểm chứng dưới cấu hình triển khai thực tế** và tránh phụ thuộc vào giả định rằng adapter sẽ luôn gọi tuần tự.

Ví dụ dùng cùng **calculatePrice** qua HTTP với Spring Cloud Function Web starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

Chọn bean:

~~~yaml
spring:
  cloud:
    function:
      definition: calculatePrice
~~~

Gọi HTTP POST khi ứng dụng chạy ở cổng 8080:

~~~bash
curl -i -X POST http://localhost:8080/calculatePrice \
  -H "Content-Type: application/json" \
  -d '{"sku":"book","quantity":3}'
~~~

Nhiều client có thể gửi request đồng thời. Adapter gọi cùng logic **calculatePrice.apply(...)** ở nhiều request; không có bảo đảm tự động rằng nó tạo một **PriceService** mới cho từng request.

Với Spring Cloud Stream và binder phù hợp, có thể chọn cùng bean:

~~~yaml
spring:
  cloud:
    function:
      definition: calculatePrice
    stream:
      bindings:
        calculatePrice-in-0:
          destination: price-requests
        calculatePrice-out-0:
          destination: price-quotes
~~~

Cần dependency Spring Cloud Stream, binder, broker và cấu hình kết nối thực tế. Logic **PriceService.quote** giữ nguyên. Thứ tự message, độ đồng thời và retry phụ thuộc binder cùng cấu hình; **không được xem một singleton Function là cơ chế tuần tự hóa toàn bộ sự kiện**.

## 9. Scope prototype và request không phải cách sửa mặc định

Spring hỗ trợ các scope khác singleton, nhưng cần hiểu ranh giới của chúng.

**Prototype** tạo một bean mới khi bean được Spring container yêu cầu tạo/lấy trong một lần phân giải dependency. Nó **không đồng nghĩa** “mỗi lần Function.apply(...) Spring tự tạo một đối tượng mới”.

Ví dụ gây nhầm lẫn:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
class Worker {
    private int count;

    int execute() {
        return ++count;
    }
}

@Bean
Function<String, Integer> useWorker(Worker worker) {
    return ignored -> worker.execute();
}
~~~

Trong ngữ cảnh các import và cấu hình Spring thích hợp, nếu **useWorker** là singleton, dependency **worker** được Spring cấp khi tạo singleton. Lambda có thể giữ **cùng một Worker** cho mọi lần gọi **apply(...)**, dù định nghĩa **Worker** có scope prototype.

Nếu thực sự cần instance mới cho từng lời gọi:

~~~java
@Bean
Function<String, Integer> useFreshWorker(
        org.springframework.beans.factory.ObjectProvider<Worker> workers) {
    return ignored -> workers.getObject().execute();
}
~~~

**ObjectProvider.getObject()** lấy một instance prototype mới khi lambda chạy. Dù vậy, cách này có chi phí tạo đối tượng và vòng đời quản lý tài nguyên; đối với logic biến đổi ngắn và stateless, việc tạo worker cho mỗi invocation thường không cần thiết.

**Request scope** phụ thuộc một request context (thường là HTTP), nên không nên dựa vào nó cho một Function muốn tái sử dụng không đổi qua broker hoặc serverless. Scoped proxy có hành vi riêng; vẫn cần kiểm tra context khả dụng ở thời điểm gọi và không được giả định mọi adapter đều có HTTP request scope.

> Nên sửa **nguyên nhân shared mutable state** trước khi đổi scope. Singleton stateless thường đơn giản, tiết kiệm tài nguyên và thích hợp với Spring Cloud Function.

## 10. Supplier, Function, Consumer: rủi ro trạng thái khác nhau

| Mô hình | Ví dụ trạng thái có thể bị dùng chung | Cách phòng ngừa |
| --- | --- | --- |
| **Supplier<T>** | Bộ đếm, cache, thời điểm tạo bean | Tính giá trị mới trong **get()**, dùng cơ chế đồng bộ khi cần |
| **Function<T, R>** | Field **lastRequest**, danh sách kết quả, biến capture | Ưu tiên biến cục bộ, DTO bất biến, dependency stateless |
| **Consumer<T>** | Buffer, tập ID đã xử lý, kết nối và tác dụng phụ | Idempotency, transaction, quản lý tài nguyên, kiểm soát concurrency |

Ví dụ Consumer ghi audit:

~~~java
public record AuditEvent(String eventId, String action) {}

public interface AuditRepository {
    // Implementation phải đảm bảo thao tác idempotent/bền vững theo eventId.
    void insertIfAbsent(AuditEvent event);
}

@Bean("recordAudit")
java.util.function.Consumer<AuditEvent> recordAudit(
        AuditRepository repository) {
    return repository::insertIfAbsent;
}
~~~

Đây là **mẫu thiết kế**, giả sử có implementation của **AuditRepository** được inject. Bean **recordAudit** vẫn có thể là singleton; sự an toàn phụ thuộc hợp đồng của repository và triển khai thao tác **insertIfAbsent**.

Một **HashSet<String> seenIds** trong bean singleton có thể chặn trùng trong vài tình huống của một JVM, nhưng không bền vững qua restart và không phối hợp giữa replica. Thao tác kiểu **if (!seen.contains(id)) { seen.add(id); save(); }** cũng không nguyên tử nếu nhiều thread chạy đồng thời.

Nếu event có thể được gửi lại, nên dùng khóa nghiệp vụ ổn định và unique constraint/giao dịch ở hệ thống lưu trữ phù hợp. **Thread safety trong JVM không thay thế idempotency ở hệ thống phân tán.**

## 11. Reactive: subscription, scheduler và trạng thái chia sẻ

Spring Cloud Function cũng có thể dùng **Supplier<Flux<T>>** hoặc **Function<Flux<T>, Flux<R>>** với Project Reactor. Cần phân biệt hai thời điểm: tạo publisher và publisher được **subscribe**.

Ví dụ:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.function.Supplier;
import reactor.core.publisher.Flux;

@Bean
Supplier<Flux<Instant>> streamCurrentTime(Clock clock) {
    return () -> Flux.defer(() -> Flux.just(clock.instant()));
}
~~~

Với publisher này, **clock.instant()** được đánh giá khi có subscription vào Flux được trả về, nhờ **Flux.defer(...)**. Nếu viết:

~~~java
@Bean
Supplier<Flux<Instant>> streamSnapshotTime(Clock clock) {
    Instant snapshot = clock.instant();
    return () -> Flux.just(snapshot);
}
~~~

giá trị **snapshot** được tạo khi bean được khởi tạo; gọi lại Supplier hoặc subscribe thêm cũng vẫn thấy cùng giá trị đã lưu.

Ngữ nghĩa kích hoạt **Supplier reactive** qua adapter cụ thể cần kiểm chứng: có adapter subscribe một lần vào publisher lâu sống, còn adapter khác có quy tắc khác. **Đừng tự suy rằng Supplier.get() sẽ được gọi một lần cho mỗi phần tử Flux**.

Một lỗi khác:

~~~java
java.util.List<String> shared = new java.util.ArrayList<>();

Function<Flux<String>, Flux<Integer>> unsafeStream = inputs ->
    inputs.map(value -> {
        shared.add(value);
        return shared.size();
    });
~~~

Khi nhiều subscription/luồng cùng dùng đối tượng Function này, **shared** có thể được cập nhật đồng thời. Reactor không tự làm cho một **ArrayList** ở ngoài publisher thành thread-safe. Chọn toán tử xử lý trạng thái trong phạm vi subscription, dùng cấu trúc đồng bộ phù hợp hoặc tách hẳn state thành một component có hợp đồng concurrency rõ ràng.

**ThreadLocal cũng không phải nơi giữ request context an toàn cho mọi pipeline reactive.** Khi async boundary hoặc scheduler đổi thread, ThreadLocal có thể không được truyền theo; thread trong pool có thể được dùng lại. Với metadata cần đi cùng request/message, cân nhắc **Message<T> headers** hoặc cơ chế context propagation phù hợp với thư viện sử dụng, kèm kiểm thử ở các ranh giới bất đồng bộ.

## 12. Bảo vệ metadata và dữ liệu đầu vào

Ở adapter Spring Cloud Function, dữ liệu đầu vào đôi khi có dạng **Message<T>** chứa payload và headers. Đừng sửa payload hoặc Map headers dùng chung nếu đối tượng được tái sử dụng.

~~~java
@Bean
Function<
        org.springframework.messaging.Message<String>,
        org.springframework.messaging.Message<String>> normalizeMessage() {

    return input ->
        org.springframework.messaging.support.MessageBuilder
            .withPayload(input.getPayload().trim())
            .copyHeaders(input.getHeaders())
            .build();
}
~~~

Đây là một ví dụ tạo **Message mới**. Nó giữ tham chiếu tới header values được sao chép; nếu các giá trị là đối tượng mutable, cần xem xét kỹ ranh giới sở hữu dữ liệu. **copyHeaders(...)** không đồng nghĩa deep copy mọi đối tượng nested.

Thông điệp nghiệp vụ nên được thiết kế rõ kiểu; một **record** có field bất biến về tham chiếu không tự làm List hoặc Map bên trong trở thành bất biến. Để giảm chia sẻ mutable state, có thể sử dụng **List.copyOf(...)**, **Map.copyOf(...)** trong constructor hoặc DTO factory khi phù hợp.

Với metadata đi qua HTTP, Stream hoặc serverless, adapter có thể ánh xạ header theo cách khác nhau. Không dựa vào header do client tự khai báo như một cơ chế xác thực/ủy quyền nếu chưa xác minh ở tầng an ninh thích hợp.

## 13. Kiểm thử tính đúng đắn trong môi trường đồng thời

Một unit test thông thường gọi **apply(...)** một lần chỉ kiểm tra nghiệp vụ; nó chưa chắc phát hiện race condition khi nhiều lời gọi chạy đồng thời.

### 13.1. Unit test cho Function stateless

Dựa trên **SafeFunctionsApplication**:

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class SafeFunctionsApplicationTest {

    private final SafeFunctionsApplication app =
        new SafeFunctionsApplication();

    @Test
    void quoteUsesLocalValuesAndImmutableCatalog() {
        var service = app.priceService(app.priceCatalog());
        var function = app.calculatePrice(service);

        var quote = function.apply(
            new SafeFunctionsApplication.PriceRequest("book", 3));

        assertEquals("BOOK", quote.sku());
        assertEquals(new BigDecimal("255000"), quote.total());
    }

    @Test
    void rejectsInvalidQuantity() {
        var function = app.calculatePrice(
            app.priceService(app.priceCatalog()));

        assertThrows(IllegalArgumentException.class,
            () -> function.apply(
                new SafeFunctionsApplication.PriceRequest("BOOK", 0)));
    }
}
~~~

### 13.2. Kiểm thử bộ đếm nguyên tử khi nhiều thread gọi chung một bean

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.HashSet;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import java.util.function.Supplier;
import java.util.stream.IntStream;

import org.junit.jupiter.api.Test;

class ConcurrentSupplierTest {

    @Test
    void oneSupplierProducesDistinctLocalSequenceValues()
            throws Exception {

        Supplier<String> supplier =
            new SafeFunctionsApplication().newReference();

        var executor = Executors.newFixedThreadPool(8);

        try {
            List<Callable<String>> calls =
                IntStream.range(0, 100)
                    .mapToObj(i -> (Callable<String>) supplier::get)
                    .toList();

            var futures = executor.invokeAll(calls);
            var unique = new HashSet<String>();

            for (var future : futures) {
                unique.add(future.get());
            }

            assertEquals(100, unique.size());
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Bài test này có giá trị giới hạn: nó kiểm tra **100 lời gọi đồng thời tới cùng một Supplier instance** và mong đợi 100 giá trị khác nhau. Nó không chứng minh thứ tự trả về trùng với thứ tự gửi task, không chứng minh tính duy nhất qua replica và không bảo đảm mọi trường hợp concurrency khác của ứng dụng đều an toàn.

Một test cố tình cho nhiều thread chạy **unsafeCounter** có thể đôi khi vẫn pass vì lịch chạy thuận lợi. Vì thế không nên dùng “test stress chạy một lần” làm bằng chứng duy nhất; cần kết hợp phân tích dữ liệu dùng chung, chọn thao tác nguyên tử và kiểm thử những tình huống quan trọng.

### 13.3. Kiểm thử vòng đời bean trong Spring context

Khi cần xác minh singleton thực tế và FunctionCatalog, có thể dùng **Spring Boot Test**:

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class SingletonRegistrationTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    FunctionCatalog catalog;

    @Test
    void oneContextReusesBeanAndCatalogCanFindIt() {
        Object first = context.getBean("calculatePrice");
        Object second = context.getBean("calculatePrice");

        assertSame(first, second);
        assertNotNull(catalog.lookup("calculatePrice"));
    }
}
~~~

Chú ý **catalog.lookup(...)** có thể trả về wrapper phục vụ chuyển đổi và composition; không dùng **assertSame** giữa đối tượng catalog và bean gốc để chứng minh singleton. Kiểm tra **assertSame** với hai lần lấy **bean từ cùng ApplicationContext** mới trực tiếp kiểm tra singleton trong ví dụ.

Các test trên cần dependencies JUnit 5/Spring Boot Test và Spring Cloud Function thích hợp. Chưa cần chạy HTTP server hoặc broker cho unit test; bổ sung integration test ở adapter thực sự dùng nếu cần xác minh concurrency, conversion và cấu hình binder.

## 14. Những lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Hai request nhận cùng mã thứ tự | **counter++** trên biến dùng chung, lost update | **AtomicLong** nếu chỉ trong JVM; ID bền vững nếu toàn hệ thống |
| Hàm trả dữ liệu của request trước | Lưu **lastRequest** trong field singleton | Dùng biến cục bộ hoặc input/output bất biến |
| Supplier luôn cho timestamp cũ | Giá trị được tính lúc tạo bean | Đưa phép lấy thời gian vào **get()** hoặc publisher đúng vòng đời |
| Một bài test đơn luồng pass nhưng production sai | Race chỉ xảy ra khi concurrency thực tế tăng | Rà shared state, test đồng thời và cấu hình adapter |
| Đổi scope prototype mà state vẫn chia sẻ | Prototype được inject một lần vào singleton | Dùng **ObjectProvider** theo lời gọi nếu thật sự cần instance mới |
| Dữ liệu biến mất sau restart | Lưu business state trong singleton/in-memory map | Dùng storage bền vững |
| Nhiều replica phát ID trùng | Mỗi instance có bộ đếm riêng | Database sequence hoặc ID phân tán phù hợp |
| Retry khiến Consumer ghi trùng | Thread-safe nhưng không idempotent | Unique constraint theo eventId và chính sách retry |
| Reactive pipeline bị lỗi data race | Dùng collection mutable ngoài subscription | Tách state theo subscription hoặc đồng bộ rõ ràng |
| Giá trị ThreadLocal bị thiếu/sai khi chuyển scheduler | Context không được lan truyền qua async boundary | Truyền metadata tường minh/context propagation được hỗ trợ |
| Sửa Message headers gây exception | Header map có thể là read-only | Tạo Message mới bằng MessageBuilder |
| Sau composition header thất lạc | Không định nghĩa propagation | Xác định header contract và kiểm thử conversion |

Một cách kiểm tra nhanh khi code review là hỏi: **dữ liệu nào tồn tại lâu hơn một lời gọi apply/get/accept, có thể bị nhiều lời gọi cùng truy cập, và cơ chế nào bảo vệ bất biến của nó?**

## 15. Bài tập vận dụng

**Bài tập 1 — Nhận diện race condition.** Đọc bean **unsafeCounter** ở phần 3, vẽ thứ tự hai thread làm mất một lần tăng. Giải thích vì sao đổi **long[]** thành một field **volatile long** nhưng vẫn dùng **counter++** không đủ để xử lý.

**Bài tập 2 — Function stateless.** Viết **Function<ShippingRequest, ShippingFee>** tính phí từ trọng lượng và bảng giá bất biến. Đăng ký bean singleton, kiểm thử cùng một function xử lý nhiều request khác nhau mà không giữ field chứa “request gần nhất”.

**Bài tập 3 — Chọn công cụ đồng bộ.** Một ứng dụng cần (a) đếm số lần gọi trong một JVM, (b) lưu cấu hình sản phẩm chỉ đọc, (c) tạo mã đơn hàng duy nhất qua nhiều replica. Chọn lần lượt công cụ phù hợp và giải thích tại sao **AtomicLong** không giải quyết yêu cầu (c).

**Bài tập 4 — Prototype injection.** Tạo class **Worker** scope prototype với bộ đếm nội bộ. So sánh **@Bean Function<Input, Output>** nhận trực tiếp Worker với Function nhận **ObjectProvider<Worker>**, rồi giải thích thời điểm Spring tạo Worker.

**Bài tập 5 — Consumer và gửi lại sự kiện.** Một **Consumer<OrderPaid>** ghi database rồi nhận lại cùng **eventId** sau khi ack thất bại. Thiết kế khóa idempotency, unique constraint và xử lý retry; chỉ ra vì sao synchronized quanh accept trong một instance không bảo đảm không ghi trùng qua nhiều instance.

**Bài tập 6 — Reactive context.** Xây dựng **Supplier<Flux<Instant>>** trả thời điểm theo subscription với **Flux.defer**. So sánh với Supplier capture **Instant** ở lúc tạo bean, rồi giải thích vai trò của scheduler và rủi ro khi dùng ThreadLocal để giữ correlation ID.

**Bài tập 7 — Kiểm thử tích hợp.** Dùng **FunctionCatalog.lookup("calculatePrice")**, chạy thử HTTP POST qua adapter web và kiểm tra hai request được xử lý độc lập. Sau đó mô tả những kiểm thử cần bổ sung khi chuyển sang Spring Cloud Stream và thay cấu hình concurrency/binder.

### Ghi nhớ

- **Spring singleton** là một bean instance được quản lý trong **một application context**; nó có thể nhận nhiều lời gọi và không tự bảo đảm thread safety.
- **Stateless + immutable input/output + dependency chỉ đọc** thường là thiết kế đơn giản nhất cho các hàm nghiệp vụ tái sử dụng.
- Khi phải chia sẻ trạng thái, chọn thao tác nguyên tử hoặc đồng bộ thích hợp; **AtomicLong**, **synchronized** và các collection concurrent chỉ bảo vệ trong phạm vi chúng được thiết kế.
- **Thread safety khác idempotency và độ bền**. Nhiều replica, restart và retry cần storage/giao dịch/khóa nghiệp vụ ở tầng phù hợp.
- **Scope**, **subscription reactive** và **adapter HTTP/Stream/serverless** ảnh hưởng thời điểm tạo và gọi đối tượng; phải kiểm tra thực tế thay vì giả định framework tự cô lập mỗi request.
- Kiểm thử cả **logic đơn lẻ**, **truy cập đồng thời** và **integration qua adapter** để phát hiện vấn đề ở đúng ranh giới.
