# Tiêm dựa trên hợp đồng thay vì tự tìm kiếm đối tượng trong Spring Core Container

## 1. Mục tiêu: service khai báo thứ mình cần, không tự đi tìm

Một class nghiệp vụ thường không thể hoạt động đơn lẻ: nó cần nơi lưu trữ, nơi gửi thông báo, bộ kiểm tra, đồng hồ hoặc một API ở hệ thống khác. Có hai hướng thiết kế trái ngược:

- **Tự tìm kiếm hoặc tự tạo collaborator:** service gọi `new SqlRepository()`, `ApplicationContext.getBean(...)` hoặc một registry toàn cục mỗi khi cần phụ thuộc.
- **Nhận collaborator theo hợp đồng (Dependency Injection / DI):** service khai báo rõ dependency qua constructor/factory method/setter và để bên ngoài cung cấp implementation phù hợp.

Ví dụ use case tiếp nhận đơn hàng cần đúng hai **năng lực**: giữ chỗ hàng trong kho và phát thông báo. Lớp xử lý đơn chỉ biết `InventoryPort` và `ReceiptPort`, không cần biết adapter lưu trên Map, JDBC hay một service từ xa.

~~~text
                  composition root
              Java main / Spring AppConfig
                   |              |
       chọn InMemoryInventory   ConsoleReceipt
                   |              |
                   v              v
           InventoryPort      ReceiptPort  <--- hợp đồng
                   \              /
                    \ constructor/
                     v          v
                      CheckoutService
                             |
                      place(Order)
                         /      \
                        v        v
                 reserve stock  publish receipt
~~~

**Đảo ngược quyền kiểm soát (IoC)** ở đây có nghĩa service không tự quyết định cách tạo và tìm đối tượng cộng tác. Đơn vị chịu trách nhiệm khởi động/lắp ráp quyết định concrete implementation, còn service tập trung vào quy tắc nghiệp vụ.

Sau bài này, bạn sẽ có thể:

1. Nhận diện Service Locator và việc tự `new` dependency làm ẩn hoặc khóa chặt mối quan hệ.
2. Thiết kế interface dựa trên **nhu cầu của bên sử dụng**, không theo API công nghệ cụ thể.
3. Viết constructor injection bằng Java 17, kiểm thử với fake mà không cần Spring.
4. Cấu hình Spring `@Bean` để lắp ráp cùng business class không import Spring.
5. Phân biệt lúc nào việc tra bean ở điểm khởi động hoặc dùng provider động vẫn hợp lý.
6. Giải thích các lỗi missing/multiple bean, scope và proxy mà không đánh đồng với bản chất của DI.

## 2. Vấn đề với tự tạo đối tượng cộng tác

### 2.1. Ghép chặt bằng `new` bên trong service

~~~java
// Minh họa: tên các class bên dưới cần định nghĩa ở project thực tế.
final class BadCheckoutService {
    private final JdbcInventory inventory = new JdbcInventory();
    private final SmtpReceipt receipt = new SmtpReceipt();

    String place(Order order) {
        inventory.reserve(order.sku(), order.quantity());
        receipt.publish(order.id());
        return "OK";
    }
}
~~~

Đoạn trên **không độc lập để biên dịch**, vì chưa định nghĩa `JdbcInventory`, `SmtpReceipt` và `Order`. Nó giúp thấy các vấn đề:

- Service chọn thẳng JDBC/SMTP, nên test đơn vị có thể vô tình chạm database/email thật.
- Thay adapter cần chỉnh code nghiệp vụ, hoặc thêm điều kiện môi trường vào service.
- Cấu hình connection pool, retry, credentials và lifecycle bị kéo vào một lớp không nên sở hữu chúng.
- Nếu service tự tạo nhiều instance không cần thiết, tài nguyên có thể bị lãng phí hoặc bị rò rỉ.
- API service che giấu các dependency quan trọng, khó nhìn object graph từ constructor.

**Không phải mọi `new` đều sai.** Tạo một value object như `new Order(...)` hay list cục bộ phục vụ tính toán không nhất thiết phải ủy quyền cho IoC container. Vấn đề là **service tự lựa chọn và xây dựng các collaborator có vai trò hệ thống** mà đáng ra phải nhận từ ranh giới lắp ráp.

### 2.2. Service Locator: tự tra bean trong business method

Một cách tưởng như bớt ghép chặt là giữ `ApplicationContext` rồi lookup:

~~~java
// Minh họa; giả sử đã khai báo CheckoutService và các interface.
final class LocatingCheckoutService {
    private final ApplicationContext context;

    LocatingCheckoutService(ApplicationContext context) {
        this.context = context;
    }

    String place(Order order) {
        InventoryPort inventory = context.getBean(InventoryPort.class);
        ReceiptPort receipt = context.getBean(ReceiptPort.class);
        // Logic dùng inventory và receipt...
        return "DONE";
    }
}
~~~

Đây cũng chỉ là **trích đoạn minh họa**, không phải file runnable. Nó loại bỏ việc tự `new` concrete adapters nhưng tạo vấn đề khác:

1. Constructor chỉ lộ dependency `ApplicationContext`, không cho thấy rõ service **cần** `InventoryPort` và `ReceiptPort`.
2. Service import Spring API; unit test Java thuần phải giả lập container hoặc cung cấp `ApplicationContext`.
3. Một lỗi thiếu bean có thể chỉ xuất hiện **khi nhánh nghiệp vụ chạy**, thay vì khi container dựng service.
4. Cách đặt tên/type/qualifier của bean len vào logic nghiệp vụ, dễ phát sinh fallback tùy ý hoặc lookup nhiều lần.
5. Nếu mỗi nơi tự `getBean`, việc hiểu quan hệ phụ thuộc và scope của object graph trở nên khó hơn.

Đó là cách dùng **Service Locator** trong lớp nghiệp vụ, trái với nguyên tắc “dependency được cung cấp cho đối tượng”. Nó không tự động làm ứng dụng sai chức năng, nhưng thường giảm khả năng test và khả năng thay implementation.

Đừng nhầm vấn đề này với việc **`main` hoặc adapter ở biên gọi `getBean(CheckoutService.class)` một lần** để bắt đầu use case: đó là lookup ở **composition root/entry point**, không phải nghiệp vụ tự đi tìm những dependency ẩn bên trong.

## 3. Hợp đồng tốt phản ánh nhu cầu của service

### 3.1. Hai hợp đồng nhỏ

Service tiếp nhận đơn cần các thao tác:

~~~java
public interface InventoryPort {
    boolean reserve(String sku, int quantity);
}

public interface ReceiptPort {
    void publish(String orderId);
}
~~~

Đây là minh họa API; chương trình Java 17 đầy đủ sẽ khai báo hai interface trong `ContractDemo` ở mục 5.

Contract `InventoryPort.reserve` được định nghĩa là:

- Trả `true` nếu đủ hàng và giữ chỗ thành công.
- Trả `false` nếu không đủ hàng; trong demo không thay đổi số lượng.
- Với đầu vào không hợp lệ, bên gọi/model phải kiểm tra; adapter thật cũng nên bảo vệ invariant.
- Với backend thật, còn cần mô tả chính sách concurrent reservation, idempotency và lỗi mạng/database.

Contract `ReceiptPort.publish` thông báo sau khi giữ chỗ thành công. Nó **không** bắt service biết email hay message broker cụ thể. Trong production, cần xác định thêm độ tin cậy, retry và semantics khi gửi thất bại; demo sẽ nói rõ giới hạn này.

**Hợp đồng không phải luôn là interface Java.** Có thể inject một class cụ thể khi đó là dependency hợp lý, ổn định và không cần thay bằng nhiều adapter. Tuy nhiên interface nhỏ rất có ích tại ranh giới giữa nghiệp vụ và hạ tầng, đặc biệt để thay fake trong unit test.

### 3.2. Tránh interface chỉ “đổi tên công nghệ”

Ví dụ contract chưa tốt:

~~~java
interface InventoryPort {
    java.sql.ResultSet executeSql(String sql);
}
~~~

Đây là trích đoạn minh họa. Dù mang tên `InventoryPort`, nó vẫn bắt service biết SQL và `ResultSet`; đây không phải ranh giới hướng nghiệp vụ tốt.

Hãy hỏi: “Bên sử dụng thực sự muốn làm gì?” Nếu là “giữ N đơn vị hàng hóa cho SKU”, `reserve(sku, n)` thể hiện ý nghĩa tốt hơn là `executeSql(...)`.

Một interface có hàng chục method không liên quan cũng gây khó khăn cho fake và testing. Nên tách theo nhu cầu của consumer (*interface segregation*) khi lợi ích rõ.

### 3.3. Constructor cho dependency bắt buộc

~~~java
public CheckoutService(InventoryPort inventory, ReceiptPort receipt) {
    this.inventory = java.util.Objects.requireNonNull(inventory);
    this.receipt = java.util.Objects.requireNonNull(receipt);
}
~~~

Đoạn này được triển khai trong file chạy ở mục 5. Hai field được khai báo `final` vì service không cần đổi dependency sau khi xây dựng. Nếu một dependency là bắt buộc, constructor giúp fail sớm khi không được cung cấp; dùng setter tùy chọn cho nó có thể để object ở trạng thái không hợp lệ.

**DI không đòi có Spring.** Constructor injection chỉ là cách một object nhận dependency từ nơi tạo nó. Spring Core Container tự động hóa cấu hình và quản lý bean graph, không phát minh ra nguyên tắc “nhận qua constructor”.

## 4. Trước và sau: ai kiểm soát lựa chọn triển khai?

| Câu hỏi | Tự tìm/tạo collaborator trong service | Tiêm theo hợp đồng |
| --- | --- | --- |
| Service biết class nào? | Concrete adapter hoặc Spring context API | Interface/abstraction nó thực sự cần |
| Ai chọn adapter? | Business service | `main`, factory, Spring configuration |
| Dependency có hiện rõ? | Dễ bị ẩn trong method hoặc singleton registry | Thường thể hiện trực tiếp ở constructor |
| Unit test phải làm gì? | Dựng I/O thật, mock container hoặc viết đường vòng | Truyền fake implementation thuần Java |
| Đổi database/email? | Có thể phải sửa service | Thay adapter và wiring nếu contract giữ nguyên |
| Khi thiếu dependency? | Có thể lỗi muộn ở một nhánh method | Constructor hoặc khởi tạo bean có thể fail sớm |
| Có tự động transaction/HTTP? | Không | Cũng không; cần hạ tầng riêng |
| Ai quản lý lifecycle collaborator? | Dễ bị phân tán | Composition root/container có chỗ quản lý rõ |

Không nên đưa ra tuyên bố “không sửa một dòng mã nào suốt đời”: nếu yêu cầu nghiệp vụ hoặc semantics contract thay đổi thì service vẫn phải thay đổi. Lợi ích là **giảm tác động của việc thay cách triển khai một năng lực**, không phải phủ nhận những thay đổi nghiệp vụ thật.

## 5. Ví dụ Java 17 hoàn chỉnh: contract-first và fake test

Đầu tiên chạy hoàn toàn bằng Java 17 để chứng minh DI **không phụ thuộc Spring**. File Java ở mục này cũng được dùng lại trong ví dụ Maven/Spring mục 6, vì thế không tạo bản sao business service.

### 5.1. Cấu trúc

~~~text
contract-di-demo/
├── pom.xml                         # thêm cho Spring ở mục 6
└── src/
    └── main/
        └── java/
            └── demo/
                ├── ContractDemo.java
                └── SpringWiringDemo.java  # thêm ở mục 6
~~~

Tạo `src/main/java/demo/ContractDemo.java`:

~~~java
package demo;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.ArrayList;

public final class ContractDemo {
    private ContractDemo() {}

    public record Order(String id, String sku, int quantity) {
        public Order {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id is required");
            }
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku is required");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
        }
    }

    public interface InventoryPort {
        boolean reserve(String sku, int quantity);
    }

    public interface ReceiptPort {
        void publish(String orderId);
    }

    // Adapter demo trong RAM, không thay thế database thực.
    public static final class InMemoryInventory implements InventoryPort {
        private final Map<String, Integer> available = new HashMap<>();

        public InMemoryInventory(Map<String, Integer> initial) {
            Objects.requireNonNull(initial, "initial");
            available.putAll(initial);
        }

        @Override
        public boolean reserve(String sku, int quantity) {
            Integer current = available.get(sku);
            if (current == null || current < quantity) {
                return false;
            }
            available.put(sku, current - quantity);
            return true;
        }
    }

    // Adapter demo: phát sự kiện bằng dòng console.
    public static final class ConsoleReceipt implements ReceiptPort {
        @Override
        public void publish(String orderId) {
            System.out.println("EVENT " + orderId);
        }
    }

    public static final class CheckoutService {
        private final InventoryPort inventory;
        private final ReceiptPort receipt;

        public CheckoutService(InventoryPort inventory, ReceiptPort receipt) {
            this.inventory = Objects.requireNonNull(inventory, "inventory");
            this.receipt = Objects.requireNonNull(receipt, "receipt");
        }

        public String place(Order order) {
            Objects.requireNonNull(order, "order");
            if (!inventory.reserve(order.sku(), order.quantity())) {
                return "REJECTED " + order.id();
            }
            receipt.publish(order.id());
            return "ACCEPTED " + order.id();
        }
    }

    public static void main(String[] args) {
        // Composition root thuần Java: lựa chọn concrete adapter ở ngoài service.
        InventoryPort stock = new InMemoryInventory(Map.of("BOOK", 3));
        ReceiptPort receipts = new ConsoleReceipt();
        CheckoutService service = new CheckoutService(stock, receipts);

        System.out.println(service.place(new Order("O-1", "BOOK", 2)));
        System.out.println(service.place(new Order("O-2", "BOOK", 2)));

        // Fake dùng ngay trong test, không cần Spring, DB hoặc email.
        List<String> events = new ArrayList<>();
        InventoryPort alwaysAvailable = (sku, quantity) -> true;
        ReceiptPort fakeReceipt = events::add;
        CheckoutService tested =
                new CheckoutService(alwaysAvailable, fakeReceipt);

        String testResult = tested.place(new Order("T-1", "PEN", 1));
        System.out.println("TEST_ACCEPTED " + testResult);
        System.out.println("TEST_EVENTS " + events);

        if (!"ACCEPTED T-1".equals(testResult)
                || !events.equals(List.of("T-1"))) {
            throw new AssertionError("Unexpected collaborator calls");
        }
        System.out.println("TEST PASS");
    }
}
~~~

### 5.2. Lệnh `javac`/`java`

Mở terminal tại thư mục `contract-di-demo`, cần JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/main/java/demo/ContractDemo.java
java -cp out demo.ContractDemo
~~~

**Stdout chính xác của chương trình Java thuần:**

~~~text
EVENT O-1
ACCEPTED O-1
REJECTED O-2
TEST_ACCEPTED ACCEPTED T-1
TEST_EVENTS [T-1]
TEST PASS
~~~

Giải thích:

1. `Map.of("BOOK", 3)` cung cấp 3 đơn vị hàng. Đơn `O-1` muốn 2 đơn vị: `reserve` trừ còn 1, rồi `ConsoleReceipt.publish` in `EVENT O-1`.
2. `place` trả `ACCEPTED O-1`; `main` in giá trị trả về sau khi lời gọi hoàn tất.
3. Đơn `O-2` muốn thêm 2 nhưng chỉ còn 1: `reserve` trả `false`; service trả `REJECTED O-2` **không phát sự kiện**.
4. Phép thử dùng `InventoryPort` lambda luôn trả `true` và `ReceiptPort` lambda ghi mã đơn vào `events`.
5. Service `tested` không thay đổi mã so với service thực, nhưng đã được cấp **collaborators khác**. `TEST_EVENTS [T-1]` kiểm tra thông báo đi qua fake, không có dòng `EVENT T-1`.
6. `List.of("T-1")` là danh sách kỳ vọng, `AssertionError` chỉ ném nếu hành vi sai. Trường hợp đúng in `TEST PASS`.

**Điểm then chốt:** `CheckoutService` chỉ gọi `inventory.reserve` và `receipt.publish`. Nó không tạo `InMemoryInventory`, không gọi `new ConsoleReceipt` và không hề import Spring. Việc chọn implementation diễn ra ở `main`.

### 5.3. Đánh giá độ an toàn của ví dụ

- `InMemoryInventory` dùng `HashMap` mutable và **không thread-safe**; khi có nhiều concurrent requests, tồn kho có thể bị sai nếu không có cơ chế đồng bộ/database thích hợp.
- Demo không xử lý trùng order ID, expiration của reservation hay retry: đó là các quy tắc quan trọng trong hệ thống thật, không nằm trong hợp đồng tối giản của bài này.
- Nếu `receipt.publish` ném exception **sau khi reserve**, stock đã giảm. Java thuần không tự rollback; Spring DI cũng không tự thêm database transaction.
- Một `boolean reserve` quá đơn giản cho mọi hệ thống thật, nhưng phù hợp để tập trung vào ranh giới DI; trong production có thể cần reservation ID và trạng thái rõ hơn.
- Validate đầu vào ở `Order` giúp giữ invariant, nhưng adapter vẫn cần bảo vệ khi bị gọi từ code khác; đừng lấy demo làm bảo đảm chống gọi quantity âm trực tiếp vào adapter.

## 6. Cùng business class, Spring chỉ thay bước lắp ráp

Sau khi chương trình Java thuần chạy, giữ nguyên `ContractDemo.java`. Bây giờ chỉ thêm Spring configuration và main để **container quyết định object graph**, không sửa implementation của `CheckoutService`.

### 6.1. Maven configuration

Spring Framework 6.2.0 tương thích Java 17. Bài chạy bằng `spring-context`, **không dùng Spring Boot**, web server, AOP hoặc database. Tạo `pom.xml` tại thư mục `contract-di-demo`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>contract-di-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                    <mainClass>demo.SpringWiringDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. `@Configuration` và `@Bean` với tham số interface

Tạo `src/main/java/demo/SpringWiringDemo.java`:

~~~java
package demo;

import java.util.Map;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class SpringWiringDemo {
    private SpringWiringDemo() {}

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public ContractDemo.InventoryPort inventory() {
            return new ContractDemo.InMemoryInventory(
                    Map.of("BOOK", 3));
        }

        @Bean
        public ContractDemo.ReceiptPort receipt() {
            return new ContractDemo.ConsoleReceipt();
        }

        @Bean
        public ContractDemo.CheckoutService checkoutService(
                ContractDemo.InventoryPort inventory,
                ContractDemo.ReceiptPort receipt) {
            return new ContractDemo.CheckoutService(inventory, receipt);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            // Lookup hợp lý ở biên khởi động để gọi một entry-point service.
            ContractDemo.CheckoutService service =
                    context.getBean(ContractDemo.CheckoutService.class);

            System.out.println("SERVICE_BEANS "
                    + context.getBeanNamesForType(
                            ContractDemo.CheckoutService.class).length);

            System.out.println(service.place(
                    new ContractDemo.Order("S-1", "BOOK", 1)));
            System.out.println(service.place(
                    new ContractDemo.Order("S-2", "BOOK", 3)));

            System.out.println("SAME_BEAN "
                    + (service == context.getBean(
                            ContractDemo.CheckoutService.class)));
        }
    }
}
~~~

Từ thư mục `contract-di-demo` có `pom.xml`, chạy:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

**Stdout do `SpringWiringDemo` tự in đúng thứ tự:**

~~~text
SERVICE_BEANS 1
EVENT S-1
ACCEPTED S-1
REJECTED S-2
SAME_BEAN true
~~~

`mvn -version` và Maven/plugin có thể in thêm phiên bản, quá trình tải dependency hoặc log riêng. Khối trên liệt kê **stdout do mã ứng dụng chủ động tạo**, không hứa terminal chỉ có các dòng đó.

### 6.3. Theo dõi cơ chế container

1. `AnnotationConfigApplicationContext(AppConfig.class)` đọc metadata `@Configuration` và `@Bean`, tạo các singleton không lazy khi refresh.
2. Bean `inventory` công bố một `InventoryPort`, thực tế là `InMemoryInventory` với 3 cuốn BOOK ban đầu.
3. Bean `receipt` công bố `ReceiptPort`, thực tế là `ConsoleReceipt`.
4. `checkoutService(InventoryPort inventory, ReceiptPort receipt)` khai báo hai dependency bằng **parameter type**, không cần tự `getBean` trong factory body.
5. Spring giải quyết những bean tương ứng và gọi factory method tạo `CheckoutService`. Trong service, các field vẫn là hai interface Java.
6. `main` gọi `getBean(CheckoutService.class)` để lấy **một entry point**. Đây là nơi thích hợp để dùng context. Sau đó xử lý nghiệp vụ qua `service.place`; service **không giữ `ApplicationContext`**.
7. Đơn `S-1` giữ chỗ 1, còn 2; in `EVENT S-1` rồi `ACCEPTED S-1`. `S-2` yêu cầu 3 nên bị từ chối và không gửi event.
8. Bean `CheckoutService` mặc định singleton trong context, nên lần lookup tiếp theo trả cùng reference và in `SAME_BEAN true`.
9. `try-with-resources` đóng context; Spring thực thi những callback dọn dẹp phù hợp cho bean do mình quản lý.

**Không bắt buộc có `@Autowired` trên constructor `CheckoutService`** trong ví dụ này vì bean được tạo qua `@Bean` factory method nhận dependencies. Cũng không cần gắn `@Service` trên class business hoặc bật component scan; `@Bean` đã đăng ký instance cho container.

### 6.4. Nếu muốn dùng `@Component` và constructor injection tự động?

Một cách khác (không dùng đồng thời với `@Bean checkoutService` nếu không muốn trùng bean) là đánh dấu class là component:

~~~java
@Component
public final class CheckoutService {
    private final InventoryPort inventory;
    private final ReceiptPort receipt;

    public CheckoutService(InventoryPort inventory, ReceiptPort receipt) {
        this.inventory = inventory;
        this.receipt = receipt;
    }
}
~~~

Đây là **đoạn minh họa thiết kế thay thế**, không phải mã sửa vào `ContractDemo.java` ở mục 5. Với component scanning bật cho đúng package và có bean hai interface, Spring có thể chọn **constructor duy nhất** mà không cần `@Autowired` (trên Spring Framework hiện đại). Khi đó business class có annotation Spring, nhưng vẫn không cần tự `getBean`.

Nếu mục tiêu là giữ tầng nghiệp vụ hoàn toàn không biết Spring, cấu hình `@Bean` như ví dụ chính phù hợp hơn; cả hai đều là cách DI, không có cơ chế nào bắt buộc mọi class triển khai contract phải là `@Component`.

## 7. Sai lầm phổ biến: nhìn thấy interface nhưng vẫn bị khóa vào adapter

Ví dụ:

~~~java
final class NotActuallyDecoupled {
    private final InventoryPort inventory =
            new InMemoryInventory(java.util.Map.of("BOOK", 3));
}
~~~

Đây là **mã minh họa không độc lập**: dù field có kiểu `InventoryPort`, class này vẫn quyết định `new InMemoryInventory`. Như vậy đổi adapter vẫn phải sửa class đang tiêu thụ.

Muốn tiêm dựa trên hợp đồng, **constructor nhận `InventoryPort`** chứ không tự tạo nó. Đừng nhầm “biến khai báo interface” với “quyền lựa chọn implementation ở bên ngoài”.

Tương tự, một class có tham số `ApplicationContext context` rồi gọi `getBean(InventoryPort.class)` trong mỗi method vẫn biết nhiều chi tiết container hơn mức cần thiết, dù không nhắc class adapter.

## 8. Thiếu hoặc có nhiều bean cùng contract

### 8.1. Không có ứng viên

Nếu Spring cần tạo `CheckoutService` qua `@Bean checkoutService(InventoryPort,ReceiptPort)` nhưng context không đăng ký `ReceiptPort`, quá trình khởi tạo bean có thể thất bại với lỗi dependency như `UnsatisfiedDependencyException`. Với singleton non-lazy, lỗi có thể xuất hiện **ngay khi refresh context**, trước khi `main` gọi `getBean(CheckoutService.class)`.

Điều này thường tốt hơn lỗi xảy ra muộn ở một nhánh xử lý mà service tự tra `ReceiptPort` khi cần. Nhưng cũng cần nhớ Spring không thể phát hiện hết mọi lỗi nghiệp vụ hoặc tài nguyên chỉ nhờ DI.

### 8.2. Có hai triển khai cùng interface

Giả sử có `ConsoleReceipt` và `EmailReceipt`, đều là bean `ReceiptPort`. Spring có thể không biết bean nào phải được inject nếu không có quy tắc chọn duy nhất.

Một cách chọn rõ trong Java configuration:

~~~java
@Bean
CheckoutService checkoutService(
        InventoryPort inventory,
        @Qualifier("consoleReceipt") ReceiptPort receipt) {
    return new CheckoutService(inventory, receipt);
}
~~~

Đây là **minh họa**, giả định đã định nghĩa các kiểu và bean name tương ứng. Cần import `org.springframework.beans.factory.annotation.Qualifier`.

- `@Qualifier` thu hẹp bean candidates ở injection point cần chỉ định.
- `@Primary` có thể đánh dấu một bean làm ứng viên ưu tiên mặc định.
- Nếu muốn dùng **tất cả** các implementation (ví dụ nhiều notification channels), có thể inject `List<ReceiptPort>` hoặc `Map<String,ReceiptPort>` và xây chiến lược phù hợp, thay vì tùy tiện chọn bean đầu tiên.
- Nếu phải chọn theo dữ liệu runtime từng đơn (email hay SMS), đó là yêu cầu **strategy/router nghiệp vụ**. `@Primary` không quyết định lựa chọn theo dữ liệu của mỗi request.

**Một interface chưa chắc đồng nghĩa chỉ có một bean.** Luôn nghĩ tới tên/qualifier hoặc một chiến lược rõ khi module phát triển.

## 9. Scope, lifecycle và vì sao không nên lookup mỗi lần xử lý

Spring bean mặc định scope `singleton`, thường là một instance cho bean definition trong mỗi container. Gọi `getBean(InventoryPort.class)` nhiều lần trên singleton không tạo mới adapter mỗi lần; nhưng việc lookup rải rác vẫn tạo coupling và che giấu dependency.

Với `prototype`, lời gọi `getBean` có thể tạo object mới mỗi lần được yêu cầu. Đây là một trường hợp khiến nhiều người nghĩ phải truyền nguyên `ApplicationContext` vào service để “tự lấy prototype”.

Thường có lựa chọn tốt hơn: truyền **factory/provider có contract rõ** hoặc `ObjectProvider<T>` ở tầng hạ tầng phù hợp, tùy mục đích.

Ví dụ minh họa:

~~~java
public interface TaskSessionFactory {
    TaskSession newSession();
}

public final class TaskExecutor {
    private final TaskSessionFactory sessions;

    public TaskExecutor(TaskSessionFactory sessions) {
        this.sessions = sessions;
    }

    public void execute() {
        TaskSession session = sessions.newSession();
        // Sử dụng session theo lifecycle đã định nghĩa.
    }
}
~~~

Đây là **mã minh họa**, thiếu định nghĩa `TaskSession`. Ý tưởng: nghiệp vụ cần “tạo session mới” thì khai báo **hợp đồng factory**. Adapter của factory có thể sử dụng Spring `ObjectProvider<TaskSession>` hoặc một cơ chế cấp phát khác, nhưng nghiệp vụ không cần biết `getBean("taskSession")`.

Các ngoại lệ hợp lý để lookup trực tiếp gồm:

- `main` hoặc lớp khởi động lấy một entry-point service.
- Mã framework/infrastructure như factory, plugin registry, extension processor cần truy cập container có chủ đích.
- Tình huống cần dynamic resolution thật sự nhưng đã giới hạn rõ vào một adapter thay vì rải khắp domain.

Đừng biến nguyên tắc “tránh Service Locator trong nghiệp vụ” thành khẩu hiệu “cấm tuyệt đối `getBean`”; vấn đề là **vị trí và mức coupling**.

## 10. Test độc lập Spring và test wiring qua container

### 10.1. Unit test nghiệp vụ

`ContractDemo.main` đã dùng fake cho hai interface. Một unit test thực tế (JUnit hoặc framework khác) có thể tách thành:

- **Happy path:** inventory trả true, receipt được gọi đúng một lần với ID chính xác, result accepted.
- **Không đủ hàng:** inventory trả false, receipt không được gọi, result rejected.
- **Input invalid:** `new Order("X", "BOOK", 0)` ném `IllegalArgumentException`.
- **Dependency thiếu:** `new CheckoutService(null, receipt)` ném `NullPointerException` ở constructor.
- **Lỗi collaborator:** inventory ném exception thì receipt không chạy; receipt ném exception sau reserve thì cần chính sách khôi phục rõ ràng.
- **Lựa chọn implementation:** thay fake bằng adapter thực không đòi sửa cách service gọi contract.

Những test này **không cần khởi động Spring**. Đó là lợi ích lớn của việc giữ service nhận interface qua constructor và không import `ApplicationContext`.

### 10.2. Integration test cấu hình

Để xác minh container thực sự nối bean đúng, tạo context từ `AppConfig`, lấy `CheckoutService` và thử một use case. Với nhiều profiles/implementations, kiểm tra các trường hợp thiếu dependency hoặc mơ hồ có lỗi sớm/đúng kỳ vọng.

Không nên viết mọi unit test bằng cách khởi động toàn bộ Spring context nếu code cần test thuần túy là Java business logic; việc đó làm test chậm, khó cô lập lỗi và phụ thuộc cấu hình ngoài hơn mức cần thiết.

### 10.3. Không nhầm DI với transaction hay tính nhất quán nghiệp vụ

Constructor injection chỉ xác định **ai sử dụng dependency nào**. Nếu use case phải ghi database và phát message bảo đảm không mất sự kiện, cần transaction/outbox/idempotency theo kiến trúc phù hợp. `@Bean` hay `@Autowired` **không tự** bảo đảm hai thao tác reserve/publish atomic.

## 11. Thay implementation theo môi trường

Hợp đồng `InventoryPort` cho phép thay adapter qua Spring configuration. Ví dụ:

~~~java
// Đây là ví dụ cấu hình minh họa, không phải file runnable độc lập.
@Bean
InventoryPort inventory(DataSource dataSource) {
    return new JdbcInventory(dataSource);
}
~~~

Với mã này cần định nghĩa `JdbcInventory`, cấu hình `DataSource` và JDBC driver thật; nó **không** thể chạy chỉ bằng dependency `spring-context` của ví dụ chính.

Những cách lựa chọn adapter hay gặp:

1. **Khai báo `@Bean` theo môi trường**: dự án local dùng RAM, production dùng JDBC hoặc API client.
2. **`@Profile` / `@Conditional`**: đăng ký bean tùy profile/điều kiện; phải kiểm tra dependency candidates và môi trường thực tế.
3. **`@Primary` / `@Qualifier`**: chọn mặc định hoặc một ứng viên cụ thể khi nhiều implementation cùng type.
4. **Cấu hình factory riêng**: nếu adapter cần credentials/client pool, đặt construction và lifecycle ở configuration/infrastructure.
5. **Adapter qua interface nghiệp vụ**: tránh đưa `DataSource` hoặc `ApplicationContext` thẳng vào service chỉ để tự quyết định adapter bên trong.

Thay implementation không đảm bảo hành vi tương đương nếu semantics đổi. Một adapter mới phải giữ những điều hợp đồng đã hứa: `reserve` true/false khi nào, có side effect nào, lỗi được báo thế nào.

## 12. Nguyên tắc thiết kế chi tiết

### 12.1. Dependency Inversion Principle (DIP) và DI

- **DIP** là nguyên tắc thiết kế: module cấp cao không nên phụ thuộc chặt vào module hạ tầng cấp thấp; cả hai hướng tới abstraction thích hợp.
- **DI** là kỹ thuật cung cấp dependency cho object từ bên ngoài, có thể thực hiện với Java thuần hoặc container như Spring.
- **IoC container** là một công cụ tổ chức object creation/configuration/lifecycle; không đồng nghĩa DIP hoặc DI.
- **Interface** là một phương tiện mô tả contract trong Java, không tự động tạo DI.

Có thể dùng constructor injection vào **class concrete** mà vẫn có DI; và cũng có thể khai báo interface nhưng tự tạo implementation bên trong service, khiến coupling còn nguyên. Chất lượng thiết kế phụ thuộc **ranh giới trách nhiệm**, không chỉ số lượng interface.

### 12.2. Dependency nên “chỉ thứ bạn cần”

Nếu một service chỉ cần đọc trạng thái hàng tồn, đừng buộc nó phụ thuộc một interface quản trị kho với hàng trăm method. Tạo contract tối thiểu phù hợp consumer, chẳng hạn `InventoryQuery`, khi điều đó có lợi.

Không có lý do bắt mọi value object như `Order`, `Money` hay `Address` trở thành singleton Spring beans. Chúng thường chứa dữ liệu từng use case, được tạo theo đời sống nghiệp vụ của chúng.

### 12.3. Composition root là nơi được phép biết concrete implementation

Composition root có quyền biết cả `InMemoryInventory` lẫn `CheckoutService`, vì nhiệm vụ của nó là **lắp object graph**. Nếu dùng Spring, `@Configuration`/`@Bean` ở lớp hạ tầng là một cách biểu diễn composition root đó.

Không nên áp dụng nguyên tắc “domain không biết concrete adapter” thành “configuration cũng không được biết adapter”, vì khi đó chẳng còn ai quyết định implementation được dùng.

## 13. Sai lầm thường gặp và cách nhận diện

| Sai lầm / triệu chứng | Cách hiểu và hướng xử lý |
| --- | --- |
| Dùng `new JdbcRepository()` bên trong mọi service | Service chọn hạ tầng; hãy tiêm collaborator từ cấu hình |
| Đổi field thành interface nhưng vẫn tự `new Concrete()` | Interface alone không làm thay đổi nơi lựa chọn implementation |
| Tiêm `ApplicationContext` vào toàn bộ domain | Dễ tạo Service Locator; khai báo dependency thực bằng constructor |
| Tưởng `getBean` tự xấu ở mọi vị trí | Lookup ở entry point/factory hạ tầng có thể hợp lý |
| Interface thiết kế theo SQL/client API | Contract nên biểu diễn năng lực consumer cần |
| Constructor có hàng chục collaborator không liên quan | Cần xem lại trách nhiệm service, tách use case/aggregator |
| Bean thiếu nhưng lỗi chỉ xảy ra khi xử lý đơn cụ thể | Kiểm tra hidden lookup/lazy dependencies, cho required dependency ra constructor |
| `NoSuchBeanDefinitionException` | Xem bean registration, type, profile và context đúng |
| `NoUniqueBeanDefinitionException` | Xem các ứng viên, `@Primary`/`@Qualifier` hoặc chiến lược |
| Bean được tạo tay rồi mong có AOP/transaction | Object ngoài Spring container không tự được proxy/intercept |
| `@Bean` trả một interface rồi lookup concrete class luôn đúng | Bean metadata/proxy/type exposure có thể khiến lookup concrete không phù hợp; ưu tiên contract đã đăng ký |
| Singleton bean được hiểu là thread-safe | Scope không bảo đảm concurrency; xem mutable state |
| Fake chỉ assert không ném exception | Phải assert result, số lần gọi và đúng argument |
| Adapter thật lỗi rồi tưởng DI tự rollback | Transaction/consistency là cơ chế khác |
| Service tự lấy prototype bằng `getBean` mỗi lần | Cân nhắc factory/provider injected có phạm vi rõ |
| Tất cả class trong dự án đều cần `@Component` | Bean registration chỉ cần cho những object container phải quản lý |

## 14. Bài tập kèm đáp án

**Bài 1.** `CheckoutService` chỉ cần gọi `inventory.reserve`; tại sao nó không nên nhận trực tiếp `DataSource` rồi tự chạy SQL?

**Đáp án:** Khi đó service phải biết chi tiết persistence. `InventoryPort` mô tả đúng năng lực cần, còn adapter có thể dùng JDBC bên ngoài nghiệp vụ.

**Bài 2.** Chuyển field từ `JdbcInventory` sang `InventoryPort` nhưng vẫn `new JdbcInventory()` trong service đã là DI chưa?

**Đáp án:** Chưa đúng mục tiêu DI ở ranh giới này. Service vẫn tự chọn và tạo collaborator; nên nhận `InventoryPort` từ constructor hoặc injection point khác.

**Bài 3.** `main` gọi `context.getBean(CheckoutService.class)` có phá nguyên tắc tránh Service Locator không?

**Đáp án:** Không nhất thiết. `main` là entry point/composition boundary; một lookup có chủ đích để bắt đầu use case khác với business service liên tục tự tìm các dependency ẩn.

**Bài 4.** Tại sao `ReceiptPort fakeReceipt = events::add` trong mã Java 17 là hợp lệ?

**Đáp án:** `ReceiptPort` có một abstract method `void publish(String)`. Method reference tới `List.add(String)` trả boolean nhưng Java có thể sử dụng method invocation đó trong ngữ cảnh hàm trả void, bỏ qua giá trị trả về. Vì thế mã dùng được như một implementation của functional interface.

**Bài 5.** Nếu có hai bean cùng kiểu `ReceiptPort`, Spring chắc chắn chọn bean khai báo trước chứ?

**Đáp án:** Không. Cần cơ chế lựa chọn rõ, ví dụ qualifier/primary hoặc thiết kế injection nhiều bean có chủ đích.

**Bài 6.** Nếu service có `InventoryPort` và `ReceiptPort` qua constructor, unit test có cần Spring context không?

**Đáp án:** Không. Truyền fake implementations bằng Java thuần và assert output/calls.

**Bài 7.** Nếu thêm database adapter làm thay đổi chính sách trả true/false của `reserve`, có phải service chắc chắn vẫn đúng?

**Đáp án:** Không. Thay implementation chỉ an toàn khi contract/semantics thực sự được giữ; kiểm thử adapter là cần thiết.

**Bài 8.** Nếu cần một object `TaskSession` mới cho mỗi lần xử lý, giải pháp duy nhất là tiêm `ApplicationContext` vào domain đúng không?

**Đáp án:** Không. Có thể tiêm `TaskSessionFactory` interface hoặc một provider được bọc trong adapter hạ tầng. Domain chỉ cần chức năng “tạo session mới”.

**Bài 9.** Vì sao Spring `@Bean` factory method không phải nơi vi phạm quy tắc “service không tự `new` collaborator”?

**Đáp án:** Configuration/composition root có trách nhiệm tạo và chọn implementation; `new` ở factory method là hợp lý. Điều tránh là **business service** tự ôm nhiệm vụ hạ tầng này.

## 15. Checklist áp dụng

- [ ] Liệt kê những collaborator service thật sự cần để thực hiện một use case.
- [ ] Đặt contract theo nghiệp vụ consumer, không theo API SQL/SMTP/HTTP chi tiết.
- [ ] Cho required dependencies xuất hiện trực tiếp ở constructor.
- [ ] Kiểm tra không null/invariant khi tạo service nếu cần.
- [ ] Không tự `new` adapter hạ tầng trong service.
- [ ] Không dùng `ApplicationContext.getBean` rải trong các business methods.
- [ ] Cho composition root/`@Configuration` quyền quyết định concrete adapters.
- [ ] Bảo đảm mỗi contract có đúng bean phù hợp hoặc quy tắc chọn rõ.
- [ ] Dùng fake để unit test service không cần Spring context.
- [ ] Kiểm thử wiring của Spring riêng với kiểm thử nghiệp vụ.
- [ ] Nếu cần tạo instance theo yêu cầu, ưu tiên factory/provider contract thay việc phát tán container API vào domain.
- [ ] Xác định scope/lifecycle của collaborator và tài nguyên có state.
- [ ] Không mặc định DI cung cấp transaction, locking, retry hoặc rollback.
- [ ] Test semantics và lỗi của mỗi implementation, không chỉ kiểm tra interface compile được.
- [ ] Không tạo abstraction thừa cho mọi class chỉ để “đúng pattern”.

### Tài liệu Spring để đối chiếu

- [Dependency Injection và collaborators](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [ApplicationContextAware và giới hạn coupling](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html)
- [Java-based bean configuration](https://docs.spring.io/spring-framework/reference/core/beans/java/basic-concepts.html)

**Kết luận:** Với DI dựa trên hợp đồng, `CheckoutService` nhận `InventoryPort` và `ReceiptPort` từ bên ngoài, không tự tạo/tìm chúng. Java constructor injection giúp dependency hiện rõ và unit test dễ; Spring Core Container chỉ thay composition root thủ công bằng cấu hình bean và lifecycle quản lý. Service Locator đôi khi hữu ích ở ranh giới hạ tầng, nhưng tránh để các lớp nghiệp vụ biết container khi chỉ cần những năng lực được mô tả bằng interface.