# Ghép Supplier với Consumer và kết quả tương đương Runnable

## 1. Mục tiêu bài học

Trong Spring Cloud Function, logic nghiệp vụ được mô hình hóa bằng các giao diện Java như `Supplier<T>`, `Function<T, R>` và `Consumer<T>`. Các hàm này có thể được đăng ký vào `FunctionCatalog`, ghép lại và sử dụng trong Java hoặc qua adapter HTTP, sự kiện, serverless. Mục tiêu là **tái sử dụng cùng logic mà không gắn chặt với cách kích hoạt nó**.

Ở chương **Ghép hàm**, trường hợp đặc biệt là nối một nguồn tạo dữ liệu với một bước tiêu thụ dữ liệu:

~~~text
Supplier<T> ──get()──> T ──accept(T)──> Consumer<T>
                            |
                            v
                   Hành động cuối cùng
~~~

Đầu vào của cả chuỗi **không cần được truyền từ bên ngoài**, vì Supplier tự tạo dữ liệu. Đầu ra của cả chuỗi cũng **không có giá trị trả về**, vì Consumer chỉ thực hiện hành động. Do đó, hành vi tổng thể tương đương với giao diện `Runnable` của Java:

~~~text
Supplier<T> | Consumer<T>  ⇒  Runnable

runnable.run():
    value = supplier.get()
    consumer.accept(value)
~~~

Sau bài học, bạn sẽ biết:

- Phân biệt hợp đồng của `Supplier`, `Consumer` và `Runnable`.
- Tự tạo `Runnable` từ một Supplier và Consumer trong Java thuần.
- Ghép theo tên thông qua `FunctionCatalog.lookup("nguon|dich")`.
- Phân tích cách cấu hình `spring.cloud.function.definition` và vì sao không được mặc định Runnable sẽ được mọi adapter tự kích hoạt.
- Nhận diện vấn đề về tương thích kiểu, ngoại lệ, tác dụng phụ, retry, dữ liệu rỗng và reactive.
- Viết unit test và integration test kiểm tra thứ tự gọi, kết quả side effect và trường hợp lỗi.

## 2. Hợp đồng của Supplier, Consumer và Runnable

`Supplier<T>` có phương thức `T get()`: tạo hoặc lấy một giá trị kiểu `T` mà không nhận đối số. `Consumer<T>` có phương thức `void accept(T value)`: nhận một giá trị, thực hiện hành động và không trả kết quả. `Runnable` có phương thức `void run()`: không nhận đối số và không trả kết quả.

~~~java
import java.util.function.Supplier;
import java.util.function.Consumer;

Supplier<String> source = () -> "ORDER-42";
Consumer<String> sink = value -> System.out.println(value);

String orderId = source.get(); // "ORDER-42"
sink.accept(orderId);          // in ORDER-42
~~~

Dựa trên hai thành phần đó, có thể tạo một Runnable:

~~~java
Runnable job = () -> sink.accept(source.get());
job.run(); // in ORDER-42
~~~

| Giao diện | Phương thức | Có tham số đầu vào? | Có giá trị trả về? |
|---|---|---|---|
| `Supplier<T>` | `T get()` | Không | Có, kiểu `T` |
| `Consumer<T>` | `void accept(T)` | Có, kiểu `T` | Không |
| `Runnable` | `void run()` | Không | Không |
| Supplier + Consumer đã ghép | `void run()` | Không | Không |

**Runnable không có nghĩa là tự tạo thread hoặc tự chạy song song.** Trong Java, lời gọi `job.run()` thực thi trên thread hiện tại. Muốn chạy bất đồng bộ, phải dùng một cơ chế lập lịch/thực thi phù hợp, chẳng hạn `Executor`. Việc Spring Cloud Function tạo ra một Runnable cũng không tự lên lịch để gọi nó.

### 2.1. Tại sao không trả lại kiểu Consumer?

Một Consumer bình thường cần người gọi truyền giá trị vào `accept(value)`. Nhưng trong chuỗi `Supplier<T> → Consumer<T>`, giá trị đã được Supplier tạo bên trong, nên người gọi không còn phải cung cấp đối số.

Tương tự, chuỗi cũng không thể được mô tả hợp lý như `Supplier<T>` có đầu ra `T`: giá trị `T` đã được đưa vào Consumer cuối cùng và tác vụ tổng thể không có kết quả trả về.

Vì thế, `Runnable` diễn tả chính xác **không đầu vào, không đầu ra** của tổ hợp này.

## 3. Tự ghép trong Java thuần

Xét ví dụ một nguồn tạo mã sự kiện và một Consumer ghi lại mã đã xử lý:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Supplier;

public class SupplierConsumerExample {

    public static void main(String[] args) {
        Supplier<String> nextEvent =
                () -> "EVENT-1001";

        List<String> processed = new ArrayList<>();
        Consumer<String> recordEvent = processed::add;

        Runnable processOneEvent =
                () -> recordEvent.accept(nextEvent.get());

        System.out.println(processed); // []
        processOneEvent.run();
        System.out.println(processed); // [EVENT-1001]
    }
}
~~~

Việc tạo lambda `processOneEvent` **không gọi** `nextEvent.get()` hoặc `recordEvent.accept(...)`. Trong một lần `run()` đồng bộ:

1. Java gọi `nextEvent.get()` để nhận `"EVENT-1001"`.
2. Java gọi `recordEvent.accept("EVENT-1001")`.
3. Consumer lưu sự kiện vào danh sách, sau đó `run()` kết thúc mà không trả object.

### 3.1. Helper generic cho phép ghép nhiều nguồn và đích

Java `Supplier` không có `andThen(Consumer)`. Nếu cần ghép thường xuyên trong Java thuần, ta có thể viết:

~~~java
import java.util.function.Consumer;
import java.util.function.Supplier;

public final class RunnableComposition {

    private RunnableComposition() {}

    public static <T> Runnable combine(
            Supplier<? extends T> source,
            Consumer<? super T> sink) {

        return () -> sink.accept(source.get());
    }
}
~~~

Sử dụng:

~~~java
Supplier<Integer> source = () -> 5;
Consumer<Number> output =
        value -> System.out.println("Gia tri: " + value);

Runnable task = RunnableComposition.combine(source, output);
task.run(); // Gia tri: 5
~~~

`Integer` là kiểu con của `Number`, nên kết quả `Integer` từ Supplier dùng được cho Consumer nhận `Number`. Các wildcard `? extends T` và `? super T` trong helper giúp biểu diễn tính linh hoạt này bằng generic Java.

### 3.2. Khác với Consumer.andThen

Giao diện `Consumer<T>` có phương thức `andThen` để gọi **hai Consumer** lần lượt với cùng một giá trị:

~~~java
Consumer<String> first =
        text -> System.out.println("FIRST: " + text);

Consumer<String> second =
        text -> System.out.println("SECOND: " + text);

Consumer<String> both = first.andThen(second);
both.accept("DATA");
~~~

Ở đây cả `first` và `second` nhận `"DATA"` do người gọi cung cấp. Kết quả vẫn là `Consumer<String>`. Còn ghép `Supplier<String>` với `Consumer<String>` sẽ tạo hành vi `Runnable`: **đầu vào đến từ Supplier và không cần đối số ở lời gọi cuối**.

Không thể viết `source.andThen(sink)` trên `Supplier` chuẩn Java; cũng không thể coi `Runnable` là `Function<Void, Void>` rồi tùy tiện gọi `apply(null)`.

## 4. Thứ tự gọi và số lần thực thi

Công thức thực thi là:

~~~text
Runnable.run()
   |
   v
Supplier.get()
   |
   | Giá trị T
   v
Consumer.accept(T)
   |
   v
Kết thúc (void)
~~~

Ví dụ cho thấy rõ số lần gọi:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Supplier;

AtomicInteger sequence = new AtomicInteger();
List<String> accepted = new ArrayList<>();

Supplier<String> nextCode =
        () -> "CODE-" + sequence.incrementAndGet();

Consumer<String> save = accepted::add;

Runnable task = () -> save.accept(nextCode.get());

task.run();
task.run();
task.run();

System.out.println(accepted);
// [CODE-1, CODE-2, CODE-3]
~~~

Mỗi lần `run()` ở ví dụ này gọi nguồn **một lần**, rồi gọi đích **một lần**. Tuy nhiên, đây là cách triển khai đồng bộ với lambda đã viết, không phải lời hứa rằng mọi adapter sẽ tự kích hoạt một Runnable bao nhiêu lần như nhau.

Nếu nguồn luôn trả cùng một giá trị, ba lần `run()` có thể khiến Consumer xử lý cùng dữ liệu ba lần. Với Consumer ghi database hoặc gửi sự kiện, đây là vấn đề về **idempotency** và trạng thái nguồn, không phải vấn đề cú pháp composition.

## 5. Ví dụ nghiệp vụ trong Spring Cloud Function

Giả sử hệ thống cần tạo một yêu cầu giao hàng, rồi ghi nhận yêu cầu đó. Hai bước độc lập:

- `nextShipment: Supplier<Shipment>`: lấy hoặc tạo yêu cầu cần xử lý.
- `recordShipment: Consumer<Shipment>`: ghi nhận yêu cầu.

Chúng ta dùng nguồn và kho lưu trong bộ nhớ để có thể minh họa mà không cần database thật.

### 5.1. Đăng ký Supplier và Consumer bean

Ví dụ sau dùng Java 17 và Spring Boot:

~~~java
package example.functions;

import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.function.Consumer;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ShipmentFunctions {

    public record Shipment(String shipmentId, int packageCount) {}

    public static final class ShipmentLedger {

        private final Queue<Shipment> records =
                new ConcurrentLinkedQueue<>();

        public void record(Shipment shipment) {
            records.add(shipment);
        }

        public List<Shipment> snapshot() {
            return List.copyOf(records);
        }
    }

    @Bean
    public ShipmentLedger shipmentLedger() {
        return new ShipmentLedger();
    }

    @Bean
    public Supplier<Shipment> nextShipment() {
        return () -> new Shipment("SHP-204", 2);
    }

    @Bean
    public Consumer<Shipment> recordShipment(
            ShipmentLedger ledger) {

        return shipment -> {
            if (shipment == null
                    || shipment.shipmentId() == null
                    || shipment.shipmentId().isBlank()
                    || shipment.packageCount() <= 0) {
                throw new IllegalArgumentException(
                        "Shipment khong hop le");
            }
            ledger.record(shipment);
        };
    }
}
~~~

Các tên bean mặc định sẽ là `nextShipment` và `recordShipment`. Khi Spring Cloud Function hiện diện và chúng nằm trong phạm vi được phát hiện, framework có thể đăng ký hai hàm vào `FunctionCatalog`.

`ShipmentLedger` là bean phụ thuộc của Consumer để lưu thông tin thử nghiệm, không phải thành phần `Function`/`Supplier`/`Consumer` của pipeline. Dữ liệu trong `ConcurrentLinkedQueue` chỉ tồn tại trong bộ nhớ, không có transaction, durability hay chống ghi trùng.

| Tên bean | Kiểu Java | Mục đích |
|---|---|---|
| `nextShipment` | `Supplier<Shipment>` | Tạo một yêu cầu |
| `recordShipment` | `Consumer<Shipment>` | Kiểm tra và ghi nhận yêu cầu |
| Hai bean đã ghép | `Runnable` về mặt hợp đồng | Tự lấy dữ liệu rồi ghi nhận |

### 5.2. Ghép bằng FunctionCatalog.lookup

Spring Cloud Function có cơ chế composition theo tên: dấu `|` nối các bean theo thứ tự từ trái sang phải. Trong trường hợp `Supplier → Consumer` được framework hỗ trợ, hợp đồng kết quả là `Runnable`:

~~~java
package example.functions;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

@Service
public class ShipmentProcessingService {

    private final FunctionCatalog catalog;

    public ShipmentProcessingService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public void processOneShipment() {
        Runnable task =
                catalog.lookup("nextShipment|recordShipment");

        if (task == null) {
            throw new IllegalStateException(
                    "Khong tim thay shipment pipeline");
        }

        task.run();
    }
}
~~~

Hành vi của `task.run()` tương đương với:

~~~java
ShipmentFunctions.Shipment shipment = nextShipment.get();
recordShipment.accept(shipment);
~~~

Hai biến `nextShipment` và `recordShipment` trong đoạn Java minh họa là các đối tượng hàm đã có; khi dùng catalog, code tra cứu chúng bằng tên bean thay vì giữ trực tiếp các biến này.

**Không gọi `task.get()` hoặc `task.accept(...)`** trong ví dụ trên: kết quả tổng thể là `Runnable`, nên phương thức gọi phù hợp là `run()`.

> Lưu ý phiên bản: ví dụ dựa trên cơ chế composition `Supplier + Consumer → Runnable` của Spring Cloud Function. Hãy xác minh bằng integration test trên đúng phiên bản framework đang sử dụng; support của adapter dành cho loại composition này có thể không giống khả năng tra cứu trực tiếp từ `FunctionCatalog`.

### 5.3. Lớp ứng dụng Spring Boot

Đặt lớp ứng dụng ở cùng package với các bean để dễ component scan:

~~~java
package example.functions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShipmentApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShipmentApplication.class, args);
    }
}
~~~

Sau khi ứng dụng có Spring Cloud Function context và dependency phù hợp, service có thể sử dụng `FunctionCatalog` được inject từ Spring.

## 6. Ghép thêm Function ở giữa

Một pipeline thực tế có thể cần chuẩn hóa hoặc làm giàu dữ liệu trước khi Consumer thực hiện hành động. Ví dụ:

~~~text
Supplier<Shipment>
         |
         v
Function<Shipment, String>
         |
         v
Consumer<String>
         |
         v
Runnable
~~~

Bổ sung hai bean vào lớp cấu hình:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;

@Bean
public Function<Shipment, String> shipmentLabel() {
    return shipment ->
            shipment.shipmentId() + ":"
            + shipment.packageCount();
}

@Bean
public Consumer<String> auditLabel() {
    return value -> System.out.println("AUDIT " + value);
}
~~~

Khi khai báo các method trên bên trong `ShipmentFunctions`, kiểu `Shipment` là record đã định nghĩa ở mục 5.1. Nếu viết ở lớp khác, cần import hoặc dùng `ShipmentFunctions.Shipment`.

Tra cứu chuỗi:

~~~java
Runnable task =
        catalog.lookup("nextShipment|shipmentLabel|auditLabel");

if (task == null) {
    throw new IllegalStateException("Thieu audit pipeline");
}

task.run(); // AUDIT SHP-204:2
~~~

Các hợp đồng trung gian:

| Bước | Kiểu đầu vào | Kiểu đầu ra |
|---|---|---|
| `nextShipment` | Không có | `Shipment` |
| `shipmentLabel` | `Shipment` | `String` |
| `auditLabel` | `String` | Không có |
| Toàn chuỗi | Không có | Không có — `Runnable` |

Một chuỗi bắt đầu bằng `Supplier` rồi đi qua nhiều `Function` và kết thúc bằng `Consumer` vẫn có hành vi **không cần input và không trả output**, miễn những cặp bước trung gian có hợp đồng tương thích và phiên bản framework hỗ trợ tổ hợp.

### 6.1. Thứ tự không thể đảo tùy tiện

Không nên đổi thành `"recordShipment|nextShipment"`: Consumer ở đầu không tạo dữ liệu cho Supplier ở sau; trong khi Supplier không nhận đầu vào từ bước trước. Cũng không thể ghép `nextShipment|auditLabel` nếu không có bước chuyển từ `Shipment` sang `String` mà Consumer đó mong đợi.

Đừng dựa vào việc hai kiểu có thể chuyển đổi thành chuỗi kỹ thuật để bỏ qua thiết kế nghiệp vụ. Chữ ký `Supplier<Shipment>`, `Function<Shipment, String>` và `Consumer<String>` giúp xác nhận ý nghĩa của từng điểm nối.

## 7. Cấu hình spring.cloud.function.definition

Có thể đặt tên chuỗi trong `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: "nextShipment|recordShipment"
~~~

Hoặc trong `application.properties`:

~~~properties
spring.cloud.function.definition=nextShipment|recordShipment
~~~

Giá trị cấu hình mô tả **tên các hàm cần ghép**, tương tự cách gọi trực tiếp `catalog.lookup("nextShipment|recordShipment")`.

Cần phân biệt:

- `FunctionCatalog.lookup(...)`: code Java chủ động lấy Runnable hợp thành và gọi `run()`.
- `spring.cloud.function.definition`: chọn tên hàm/chuỗi cho lớp tích hợp hoặc adapter, nếu adapter hỗ trợ kiểu đó.
- Cơ chế kích hoạt thực tế: do lời gọi Java, scheduler, HTTP, message binder hoặc serverless handler phù hợp quyết định.

Thuộc tính `definition` **không tự lên lịch gọi Runnable, không tự tạo HTTP endpoint và không tự kết nối message broker**.

### 7.1. Runnable có phải chức năng được mọi adapter tự kích hoạt?

Không. Một pipeline `Function<A,B>` có input/output, `Supplier<T>` là nguồn tạo dữ liệu và `Consumer<T>` là nơi nhận dữ liệu; chúng có hợp đồng phù hợp với nhiều mô hình transport. Nhưng `Runnable` **không có input lẫn output**. Vì vậy một adapter thiết kế để ánh xạ request body hoặc binding inbound/outbound có thể không có quy tắc tự nhiên để kích hoạt nó.

Trong Spring Cloud Stream, không nên mặc định chuỗi `Supplier|Consumer` sẽ được binder cấu hình thành một luồng message như một `Supplier` hoặc `Consumer` thông thường. Tùy phiên bản/integration, loại Runnable hợp thành có thể không phải definition thích hợp để bind tự động.

Nếu mục tiêu là “mỗi sự kiện broker đến phải qua một bước biến đổi rồi được lưu”, nên dùng `Function<T,R>|Consumer<R>` bắt đầu bằng input nhận từ broker. Nếu mục tiêu là “định kỳ tạo dữ liệu và gửi đến broker”, một `Supplier` (có thể ghép với các `Function`) thường phù hợp hơn và để adapter chịu trách nhiệm output binding. Với Runnable không có input/output, có thể cần **lời gọi Java hoặc lịch kích hoạt tường minh**.

### 7.2. Ví dụ kích hoạt Runnable từ Java

Một cách rõ ràng là dùng service và gọi khi nghiệp vụ cần thực thi:

~~~java
@Service
public class ShipmentJobFacade {

    private final ShipmentProcessingService service;

    public ShipmentJobFacade(ShipmentProcessingService service) {
        this.service = service;
    }

    public void processOne() {
        service.processOneShipment();
    }
}
~~~

Đoạn này minh họa lời gọi đồng bộ. Nếu ứng dụng muốn chạy định kỳ, cần cơ chế lịch thực tế (ví dụ `@Scheduled` cùng cấu hình scheduling) và quy tắc xử lý trùng, lỗi, trạng thái nguồn. Chỉ có `Runnable` hoặc `spring.cloud.function.definition` không tự làm những việc này.

## 8. Kiểu dữ liệu và ý nghĩa nghiệp vụ giữa hai bước

### 8.1. Cặp tương thích

~~~java
Supplier<Integer> count = () -> 7;
Consumer<Number> display =
        number -> System.out.println("Count: " + number);

Runnable job = () -> display.accept(count.get());
job.run(); // Count: 7
~~~

`Integer` là kiểu con của `Number`, nên dữ liệu từ nguồn phù hợp với Consumer.

### 8.2. Cặp không tương thích

~~~java
Supplier<String> nextOrderId = () -> "ORD-42";
Consumer<Integer> updateQuantity = value -> {};

// Không biên dịch vì String không truyền cho Consumer<Integer> được.
// Runnable invalid = () ->
//         updateQuantity.accept(nextOrderId.get());
~~~

Nếu sử dụng chuỗi theo tên, chẳng hạn `"nextOrderId|updateQuantity"`, trình biên dịch Java không thấy được hợp đồng của các bean dựa trên tên chuỗi. Lỗi có thể lộ ra lúc `lookup` hoặc lúc thực thi ở runtime. Vì vậy, hãy kiểm tra generic của mỗi bean và có integration test với catalog.

### 8.3. Khớp kiểu nhưng sai nghiệp vụ

Hai bean có thể cùng dùng `String` nhưng đại diện hai khái niệm khác nhau: Supplier tạo **mã đơn hàng** trong khi Consumer nhận `String` và coi đó là **email**. Pipeline có thể chạy nhưng ghi hoặc gửi sai dữ liệu. Có thể dùng các record riêng:

~~~java
record OrderId(String value) {}
record EmailAddress(String value) {}
~~~

Khi đó `Supplier<OrderId>` và `Consumer<EmailAddress>` không tương thích trực tiếp, giúp phát hiện sớm một số lỗi thiết kế.

## 9. Dữ liệu rỗng, null và ngoại lệ

### 9.1. Khi Supplier không có dữ liệu mới

Một Supplier dùng để đọc hàng đợi hoặc database có thể tạm thời không có bản ghi. Nếu tự trả `null`, Consumer phía sau có thể nhận giá trị không hợp lệ:

~~~java
Supplier<String> source = () -> null;
Consumer<String> consumer =
        text -> System.out.println(text.length());

Runnable task = () -> consumer.accept(source.get());

// task.run() sẽ ném NullPointerException tại Consumer.
~~~

`Runnable` không tự có cơ chế “không có dữ liệu thì bỏ qua”. Hợp đồng trả dữ liệu của Supplier phải mô tả rõ trường hợp này. Trong Java nội bộ có thể dùng `Optional<T>` và một Consumer phù hợp:

~~~java
import java.util.Optional;
import java.util.function.Consumer;
import java.util.function.Supplier;

Supplier<Optional<String>> source = Optional::empty;

Consumer<Optional<String>> sink =
        value -> value.ifPresent(System.out::println);

Runnable task = () -> sink.accept(source.get());

task.run(); // Không in gì, không lỗi
~~~

Nếu đưa qua adapter message, `Optional.empty()` không tự động đồng nghĩa “không phát message” trong mọi framework. Hãy tuân theo hợp đồng thích hợp của adapter thay vì áp dụng nguyên ví dụ Java thuần.

### 9.2. Supplier ném lỗi thì Consumer không chạy

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger accepted = new AtomicInteger();

Supplier<String> broken = () -> {
    throw new IllegalStateException("Nguon khong san sang");
};

Consumer<String> sink = value -> accepted.incrementAndGet();

Runnable task = () -> sink.accept(broken.get());

try {
    task.run();
} catch (IllegalStateException expected) {
    System.out.println("Khong lay duoc du lieu");
}

System.out.println(accepted.get()); // 0
~~~

Vì nguồn thất bại, Consumer chưa được gọi. Với Java đồng bộ, ngoại lệ thường lan ra từ `run()` nếu không được xử lý.

### 9.3. Consumer ném lỗi thì dữ liệu có thể đã được lấy

~~~java
Supplier<String> source = () -> "ORD-42";

Consumer<String> failingSink = value -> {
    throw new IllegalStateException("Khong ghi duoc ket qua");
};

Runnable task = () -> failingSink.accept(source.get());

// task.run() ném IllegalStateException.
~~~

Nguồn có thể đã đọc, đánh dấu hoặc loại bản ghi khỏi hệ thống trước khi Consumer thất bại. Composition **không tự rollback** thay đổi trạng thái nguồn. Cần thiết kế acknowledgement, giao dịch, cơ chế retry hoặc khôi phục phù hợp với loại nguồn thực tế.

## 10. Tác dụng phụ, retry và xử lý trùng

Giả sử `nextShipment` đọc một bản ghi từ hàng đợi, `recordShipment` lưu kết quả vào database. Có thể xảy ra các tình huống:

1. Supplier chưa lấy được dữ liệu: Consumer không chạy.
2. Supplier lấy dữ liệu thành công, Consumer ghi thất bại: cần biết dữ liệu có thể thử lại không.
3. Consumer ghi thành công nhưng lỗi xảy ra trước khi hệ thống xác nhận: khi retry, có nguy cơ ghi cùng yêu cầu thêm lần nữa.
4. Runnable được kích hoạt nhiều lần đồng thời: các lần gọi có thể cùng xử lý một bản ghi nếu nguồn không có cơ chế khóa/claim phù hợp.

`Supplier|Consumer` **không tự cung cấp** giao dịch xuyên hệ thống, exactly-once hoặc idempotency. Những biện pháp thường dùng gồm khóa duy nhất theo `shipmentId`, thao tác ghi idempotent, trạng thái claim/ack, transactional outbox khi cần và chính sách retry phù hợp.

### 10.1. Không mặc định Runnable chạy bất đồng bộ

~~~java
Runnable task = () -> System.out.println(
        Thread.currentThread().getName());

task.run(); // Chạy trên thread đang gọi.
~~~

Sử dụng `new Thread(task).start()` hoặc `ExecutorService` mới đưa công việc sang thread khác; trong hệ thống Spring, việc quản lý executor, giới hạn song song và lỗi còn cần phù hợp kiến trúc ứng dụng. Việc ghép thành Runnable chỉ tạo **hợp đồng thực thi**, không tạo thread mới.

### 10.2. Tránh trạng thái mutable không an toàn

Function bean là đối tượng có thể được dùng chung trong Spring context. Nếu Supplier hoặc Consumer giữ trạng thái mutable, phải cân nhắc khả năng được gọi đồng thời và cơ chế đồng bộ tương ứng. Ví dụ `ConcurrentLinkedQueue` trong bài là kho thử nghiệm an toàn ở mức thao tác hàng đợi; nó vẫn không giải quyết transaction, khử trùng dữ liệu hoặc lưu bền vững.

## 11. Trường hợp reactive Supplier và Consumer

Trong Reactor, cần phân biệt **kiểu phần tử** và **kiểu Publisher**. Một nguồn có thể có chữ ký:

~~~text
Supplier<Flux<String>>
~~~

Còn đích có thể nhận:

~~~text
Consumer<Flux<String>>
~~~

Nếu viết trực tiếp trong Java, ta có thể tạo:

~~~java
import java.util.function.Consumer;
import java.util.function.Supplier;
import reactor.core.publisher.Flux;

Supplier<Flux<String>> source =
        () -> Flux.just("A", "B");

Consumer<Flux<String>> sink =
        flux -> flux.subscribe(System.out::println);

Runnable task = () -> sink.accept(source.get());

task.run(); // In A và B trong ví dụ đơn giản này.
~~~

Ở đây, `run()` giao một `Flux` cho Consumer; các phần tử `A` và `B` được xử lý sau khi có subscription. Trong mô hình Reactor, thời điểm xử lý phần tử có thể phụ thuộc scheduler, demand và operator, không nhất thiết đồng nhất với thời điểm tạo Publisher.

### 11.1. Tại sao không mặc định mọi tổ hợp reactive đều là Runnable?

Một `Supplier<Flux<T>>` có đầu ra kiểu `Flux<T>`. Một `Consumer<T>` thông thường nhận **một phần tử `T`**, không nhận cả `Flux<T>`. Hai chữ ký này khác với `Consumer<Flux<T>>`.

Spring Cloud Function và adapter có thể có cơ chế adaptation reactive/imperative tùy phiên bản và loại hàm, nhưng không nên giả định `Supplier<Flux<T>>|Consumer<T>` luôn là phép ghép tự động được hỗ trợ hoặc giữ nguyên các tính chất về subscription. Hãy xem hợp đồng thực tế của framework và kiểm thử tại ranh giới adapter.

### 11.2. Quản lý subscription và lỗi

Ví dụ `flux.subscribe(...)` minh họa ý tưởng; với ứng dụng production, tự gọi `subscribe` bên trong Consumer có thể khiến việc quản lý lỗi, backpressure và vòng đời subscription khó hơn. Nên để tầng reactive/adapter phù hợp quản lý subscription khi framework quy định như vậy. Ngoài ra, một lời gọi `run()` chỉ tạo Publisher hoặc bắt đầu subscription, chưa chắc có nghĩa mọi phần tử đã xử lý xong.

## 12. FunctionCatalog và adapter là hai tầng khác nhau

| Nhu cầu | Cách thực hiện | Cần lưu ý |
|---|---|---|
| Java gọi một Runnable đã ghép | `catalog.lookup("nextShipment|recordShipment")` rồi `run()` | Kiểm tra phiên bản, tên bean và kiểu |
| Java tự ghép Supplier/Consumer | `() -> sink.accept(source.get())` | Không cần Spring Cloud Function |
| Chọn pipeline cho adapter | `spring.cloud.function.definition` | Adapter phải hỗ trợ kiểu pipeline |
| Phát sự kiện từ một nguồn | `Supplier<T>` và binding outbound phù hợp | Lịch poll, retry, serializer |
| Nhận sự kiện và ghi dữ liệu | `Consumer<T>` hoặc `Function<T,R>|Consumer<R>` | Input binding, ack, lỗi |
| Chạy định kỳ không cần input/output | Runnable được gọi qua scheduler/service | Cấu hình kích hoạt tường minh |

Sơ đồ khái niệm:

~~~text
                   Spring Cloud Function
               +---------------------------+
Bean Supplier ─┤                           │
               │       FunctionCatalog     ├──> Runnable
Bean Consumer ─┤        "source|sink"      │        │
               +---------------------------+        │ run()
                                                    ▼
                                           Side effect cuối
                                                    ▲
                                        Lời gọi Java / lịch
                                        kích hoạt phù hợp
~~~

Nếu có một adapter HTTP, event hoặc serverless, hãy kiểm tra cách adapter đó nhận diện, chọn và kích hoạt chức năng. **Không có kết nối tự động phổ quát giữa Runnable và HTTP request/message broker.**

## 13. Kiểm thử phép ghép

### 13.1. Unit test thứ tự và số lần gọi

Bài kiểm thử JUnit 5 sau chạy hoàn toàn bằng Java:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Supplier;

import org.junit.jupiter.api.Test;

class SupplierConsumerOrderTest {

    @Test
    void runsSupplierBeforeConsumerOnEveryRun() {
        List<String> calls = new ArrayList<>();

        Supplier<String> source = () -> {
            calls.add("get");
            return "ORD-42";
        };

        Consumer<String> sink = value -> {
            calls.add("accept:" + value);
        };

        Runnable task = () -> sink.accept(source.get());

        assertEquals(List.of(), calls);

        task.run();
        assertEquals(
                List.of("get", "accept:ORD-42"),
                calls);

        task.run();
        assertEquals(
                List.of(
                    "get", "accept:ORD-42",
                    "get", "accept:ORD-42"),
                calls);
    }
}
~~~

Bài kiểm thử xác nhận việc tạo Runnable chưa kích hoạt các bước và mỗi lần `run()` của lambda này đi qua `get` rồi `accept`.

### 13.2. Kiểm thử nguồn lỗi chặn Consumer

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Supplier;
import org.junit.jupiter.api.Test;

class SupplierConsumerFailureTest {

    @Test
    void doesNotCallConsumerWhenSourceFails() {
        AtomicInteger accepted = new AtomicInteger();

        Supplier<String> source = () -> {
            throw new IllegalStateException("missing source");
        };

        Consumer<String> sink =
                value -> accepted.incrementAndGet();

        Runnable task = () -> sink.accept(source.get());

        assertThrows(IllegalStateException.class, task::run);
        assertEquals(0, accepted.get());
    }
}
~~~

### 13.3. Integration test với FunctionCatalog

Khi Spring Boot context đã có `ShipmentApplication`, `ShipmentFunctions` và Spring Cloud Function, ta có thể kiểm tra composition thực sự theo tên:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = ShipmentApplication.class)
class SupplierConsumerCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    ShipmentFunctions.ShipmentLedger ledger;

    @Test
    void catalogComposesSupplierAndConsumerAsRunnable() {
        Runnable task =
                catalog.lookup("nextShipment|recordShipment");

        assertNotNull(task);
        task.run();

        assertEquals(
                List.of(
                    new ShipmentFunctions.Shipment(
                        "SHP-204", 2)),
                ledger.snapshot());
    }
}
~~~

Test này kiểm tra việc đăng ký tên, ghép thành Runnable và tác dụng phụ trong Spring context. Cần dependency `spring-boot-starter-test` và Spring Cloud Function phù hợp. Nếu store dùng chung giữa nhiều test, nên reset hoặc cô lập context/dữ liệu để tránh test phụ thuộc thứ tự.

### 13.4. Kiểm thử thực tế khi tích hợp transport

Nếu ứng dụng có lịch chạy, broker hoặc adapter cụ thể, nên kiểm tra thêm:

- Runnable có được kích hoạt như thiết kế hay không, với **số lần mong đợi**?
- Supplier không có dữ liệu hoặc gặp lỗi thì hệ thống xử lý ra sao?
- Consumer ghi thành công rồi mất kết nối thì retry có ghi trùng không?
- Có giới hạn song song, timeout và cơ chế quan sát lỗi hay chưa?
- Adapter có thực sự hỗ trợ định nghĩa Runnable không, hay cần orchestration riêng?
- Với reactive, subscription/lỗi và vòng đời stream có được quản lý đúng?

Kiểm thử Java thuần chỉ xác nhận nguyên lý `get → accept`; kiểm thử catalog xác nhận framework ghép theo tên; kiểm thử adapter mới xác nhận hành vi vận hành ở môi trường triển khai.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `supplier.andThen(consumer)` không biên dịch | `Supplier` chuẩn Java không có `andThen` | Dùng lambda hoặc composition theo tên trong Spring |
| Gọi `pipeline.get()` thất bại | Pipeline Supplier + Consumer có hợp đồng Runnable | Tra cứu `Runnable` và gọi `run()` |
| Gọi `pipeline.accept(input)` thất bại | Runnable không có tham số input | Dùng `run()`, không truyền dữ liệu |
| `lookup` không có kết quả | Sai tên bean hoặc phiên bản/cấu hình không hỗ trợ | Kiểm tra `@Bean`, catalog và dependency |
| Không thấy task chạy tự động | Runnable không tự có scheduler | Gọi rõ ràng trong Java hoặc thiết lập lịch thích hợp |
| Không thấy binding HTTP/broker | Adapter không tự bind Runnable như Function/Supplier/Consumer | Chọn kiến trúc phù hợp hoặc dùng orchestration tường minh |
| Consumer xử lý bản ghi trùng | Nguồn trả cùng dữ liệu hoặc retry chạy lại task | Khóa nghiệp vụ, idempotency, trạng thái nguồn |
| Runtime lỗi kiểu | Supplier trả kiểu không tương thích Consumer | Kiểm tra hợp đồng trung gian và test catalog |
| Reactive không phát kết quả | Chưa subscribe hoặc stream lỗi | Kiểm tra Publisher, subscription và backpressure |

## 15. Bài tập thực hành

**Bài 1 — Ghép Java thuần.** Viết `Supplier<Integer>` trả về `7` và `Consumer<Integer>` ghi giá trị vào một `List<Integer>`. Ghép thành `Runnable`, gọi `run()` hai lần và cho biết danh sách cuối.

**Bài 2 — Phân biệt các hợp đồng.** Giải thích vì sao `Supplier<String>|Consumer<String>` tương đương `Runnable`, trong khi `Function<String,Integer>|Consumer<Integer>` tương đương `Consumer<String>`.

**Bài 3 — Nối thêm một Function.** Cho `Supplier<String> raw`, `Function<String,Integer> parse` và `Consumer<Number> sink`. Viết biểu thức Java để tạo một `Runnable`; xác định chuỗi tên tương ứng nếu ba bean được đăng ký trong `FunctionCatalog`.

**Bài 4 — Tương thích kiểu.** Vì sao `Supplier<OrderId>` không thể ghép trực tiếp với `Consumer<EmailAddress>`? Hãy đề xuất một bước biến đổi có ý nghĩa nghiệp vụ nếu cần gửi email dựa trên mã đơn hàng.

**Bài 5 — Triển khai qua sự kiện.** Bạn muốn mỗi message từ broker kích hoạt một Consumer để lưu dữ liệu. Có nên chọn `Supplier|Consumer` rồi kỳ vọng broker tự gọi `run()` cho từng message không? Nêu hợp đồng nào phù hợp hơn với message inbound.

**Bài 6 — Nguồn không có dữ liệu.** Một Supplier đôi khi trả `null`. Mô tả rủi ro khi Consumer không kiểm tra `null`; thiết kế một cách biểu diễn/truyền xử lý trường hợp rỗng trong Java.

**Bài 7 — Lặp và retry.** Một nguồn liên tục trả cùng `Shipment("SHP-204", 2)`, Consumer lưu vào database, job chạy mỗi phút. Nêu hai vấn đề có thể xảy ra và cách ngăn dữ liệu trùng.

### Gợi ý đáp án

- **Bài 1:** `Runnable task = () -> sink.accept(source.get());`; danh sách cuối `[7, 7]`.
- **Bài 2:** Supplier không cần input, Consumer không tạo output, nên tổng thể không có input/output. Function nhận input từ người gọi nên tổng thể vẫn là Consumer.
- **Bài 3:** `() -> sink.accept(parse.apply(raw.get()))`; biểu thức catalog có dạng `"raw|parse|sink"`.
- **Bài 4:** Cần bước chuyển từ `OrderId` sang `EmailAddress` dựa trên dữ liệu có thật và quy tắc nghiệp vụ phù hợp.
- **Bài 5:** Dùng `Consumer<MessageType>` hoặc `Function<MessageType,R>|Consumer<R>` với input binding của adapter.
- **Bài 6:** Không dùng `null` không kiểm soát; có thể dùng `Optional<T>` cùng Consumer nhận `Optional<T>` trong Java thuần.
- **Bài 7:** Phát trùng qua lịch chạy/retry và ghi trùng khi chạy song song; cần idempotency, unique key, claim/ack nguồn và lịch chạy phù hợp.

## 16. Ghi nhớ

- `Supplier<T>` tạo dữ liệu qua `get()`, `Consumer<T>` nhận dữ liệu qua `accept(T)` và không trả kết quả.
- Ghép `Supplier<T> → Consumer<T>` cho hành vi **`Runnable`**: `() -> sink.accept(source.get())`.
- Trong Spring Cloud Function, `FunctionCatalog.lookup("source|sink")` có thể cung cấp Runnable hợp thành khi loại composition được hỗ trợ; lời gọi tương ứng là `run()`.
- `Runnable.run()` không tự chạy song song, không tự lập lịch và không tự kích hoạt khi ứng dụng khởi động.
- `spring.cloud.function.definition` chọn tên chuỗi cho tích hợp nhưng adapter phải hỗ trợ kiểu Runnable; không mặc định mọi HTTP hoặc message binder đều bind được composition này.
- Tương thích kiểu là điều kiện cần; còn cần thiết kế rõ dữ liệu rỗng, lỗi nguồn, side effect, retry và chống xử lý trùng để dùng trong hệ thống thực tế.
