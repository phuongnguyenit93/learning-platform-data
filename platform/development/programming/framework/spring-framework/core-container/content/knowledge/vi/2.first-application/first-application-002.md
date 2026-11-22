# Tạo lớp nghiệp vụ và hợp đồng cho đối tượng cộng tác — ứng dụng Spring đầu tiên

## 1. Mục tiêu và bức tranh ứng dụng

Một ứng dụng có ích hiếm khi chỉ có một `main` chứa tất cả câu lệnh. Ta thường cần một **lớp nghiệp vụ** điều phối một ca sử dụng (*use case*), và các **đối tượng cộng tác** (*collaborators*) cung cấp thao tác lưu trữ, gửi thông báo hoặc gọi hệ thống bên ngoài.

Trong ví dụ đặt hàng tối giản:

- Người dùng gửi yêu cầu có mã đơn, mã hàng, số lượng.
- `OrderService` kiểm tra/điều phối nghiệp vụ tiếp nhận đơn.
- `OrderStore` là **hợp đồng** để lưu đơn, không buộc service biết dữ liệu nằm trong bộ nhớ hay database.
- `Notifier` là **hợp đồng** để thông báo khi đơn được tiếp nhận, không buộc service biết gửi console, email hay message queue.
- Một điểm khởi động tạo các triển khai thật, sau đó truyền chúng vào `OrderService`. Khi dùng Spring, `ApplicationContext` cùng `@Configuration`/`@Bean` có thể đảm trách bước lắp ráp này.

Bài học chính: **mô tả các lớp và hợp đồng trước; để vị trí lắp ráp quyết định triển khai sau**. Có thể thực hành hoàn toàn bằng Java 17 rồi mới thay bước lắp ráp bằng Spring Core Container.

~~~text
                request OrderRequest
                        |
                        v
                 +--------------+
                 | OrderService |        lớp nghiệp vụ / use case
                 +--------------+
                   |          |
          uses     |          |     uses
                   v          v
             OrderStore     Notifier      hợp đồng cộng tác
                  ^           ^
                  |           |
         InMemoryOrderStore  ConsoleNotifier
                       triển khai cụ thể
                              ^
                              |
                   main hoặc Spring @Configuration
                      chọn, tạo, nối đối tượng
~~~

Hợp đồng giúp giới hạn điều mà bên sử dụng **cần biết**, không phải một cơ chế tự động chặn mọi phụ thuộc. Giao diện vẫn có thể thiết kế tệ, quá rộng hoặc buộc domain biết chi tiết hạ tầng nếu đặt sai trách nhiệm.

## 2. Xác định vai trò trước khi viết code

| Thành phần | Vai trò | Nên biết | Không nên tự ôm |
| --- | --- | --- | --- |
| `OrderRequest` | Dữ liệu đầu vào hợp lệ, bất biến | Mã đơn, mã hàng, số lượng | Cách kết nối database hay gửi email |
| `OrderService` | Thực hiện hành vi tiếp nhận đơn | Quy tắc xử lý và các **hợp đồng** cần gọi | URL SMTP, tên driver, SQL tạo kết nối |
| `OrderStore` | Hợp đồng lưu đơn | Hàm lưu và ý nghĩa lỗi trùng mã | Định dạng bảng SQL cụ thể |
| `Notifier` | Hợp đồng thông báo | Hàm nhận thông tin cần gửi | Địa chỉ server cụ thể |
| `InMemoryOrderStore` | Triển khai demo lưu trong RAM | Cấu trúc Map và kiểm tra trùng mã | Quyết định nghiệp vụ của service |
| `ConsoleNotifier` | Triển khai demo in thông báo | Cách viết stdout | Điều kiện chấp nhận đơn |
| `main` / `AppConfig` | Composition root | Triển khai nào được chọn, object graph | Logic đặt hàng của `OrderService` |

**Lớp nghiệp vụ khác lớp dữ liệu:** một `record` chứa dữ liệu không tự biến thành service. `OrderService` không phải DTO vì nó có hành vi; `OrderStore` là contract chứ không phải service quản lý HTTP.

**Collaborator không nhất thiết là interface.** Trong Java/Spring vẫn có thể inject một class cụ thể, đặc biệt khi đó là dependency ổn định và không cần nhiều triển khai. Ta dùng interface ở đây vì muốn thay `ConsoleNotifier` bằng fake trong kiểm thử, hoặc đổi phương án lưu đơn mà không sửa quy tắc trong `OrderService`.

## 3. Thiết kế hợp đồng có nghĩa

Một hợp đồng tốt tập trung vào việc lớp nghiệp vụ **muốn thực hiện**, thay vì mô tả cách một công nghệ cụ thể vận hành.

~~~java
public interface OrderStore {
    void save(OrderRequest order);
}

public interface Notifier {
    void notifyPlaced(String orderId);
}
~~~

Đây là **trích đoạn minh họa**, chưa phải file Java độc lập: `OrderRequest` được định nghĩa ở phần chương trình đầy đủ bên dưới.

Hai phương thức có ý nghĩa rõ:

- `save(order)`: lưu một đơn; nếu có mã trùng trong demo sẽ báo lỗi, không âm thầm ghi đè.
- `notifyPlaced(id)`: báo rằng đơn đã được tiếp nhận; client không cần biết cách truyền thông điệp.

Tránh thiết kế hợp đồng quá mơ hồ kiểu `void doSomething(Object input)`, hoặc quá gắn hạ tầng như `void executeSql(String sql)` nếu dịch vụ chỉ cần `save(order)`. Mức trừu tượng nên phù hợp nhu cầu thật, không tạo interface một cách máy móc cho tất cả class.

**Định nghĩa semantics và lỗi:** giao diện phải được các triển khai hiểu nhất quán. Ví dụ bên gọi cần biết `save` có tạo mới, cập nhật hay cấm trùng; việc đổi triển khai không được tùy tiện làm mất các quy tắc đó. Nếu cần trả trạng thái hoặc xử lý lỗi đặc biệt, có thể mở rộng contract bằng kiểu trả về và ngoại lệ chuyên biệt khi thiết kế hệ thống thật.

### Ranh giới kiểm tra dữ liệu

Chọn hai cấp kiểm tra:

1. `OrderRequest` bảo đảm trạng thái không vô nghĩa (`id`/`sku` không trống, `quantity` dương).
2. `OrderService` điều phối bước lưu và thông báo, không lặp lại mọi kiểm tra đã được constructor `OrderRequest` thực hiện.

Ví dụ này **chưa có thanh toán, tồn kho, database transaction**. Tách phạm vi như vậy giúp người học nhìn rõ DI và thiết kế collaborator trước khi học hạ tầng phức tạp hơn.

## 4. Chương trình Java 17 độc lập, chưa cần Spring

Tạo thư mục dự án như sau. Cùng file `PlainJavaDemo.java` sẽ được dùng lại ở ví dụ Spring phần 6; không cần sao chép domain sang project khác.

~~~text
first-business-app/
├── pom.xml                         # tạo ở mục Spring; Java thuần chưa cần
└── src/
    └── main/
        └── java/
            └── demo/
                ├── PlainJavaDemo.java
                └── SpringBusinessApp.java  # tạo ở mục Spring
~~~

Tệp đầu tiên: **`src/main/java/demo/PlainJavaDemo.java`**.

~~~java
package demo;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class PlainJavaDemo {
    private PlainJavaDemo() {
    }

    // Value object bất biến, tự kiểm tra điều kiện hợp lệ.
    public record OrderRequest(String id, String sku, int quantity) {
        public OrderRequest {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id must not be blank");
            }
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku must not be blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
        }
    }

    // Hợp đồng của các cộng tác viên.
    public interface OrderStore {
        void save(OrderRequest order);
    }

    public interface Notifier {
        void notifyPlaced(String orderId);
    }

    // Triển khai lưu trong RAM để ví dụ không cần database.
    public static final class InMemoryOrderStore implements OrderStore {
        private final Map<String, OrderRequest> orders = new HashMap<>();

        @Override
        public void save(OrderRequest order) {
            Objects.requireNonNull(order, "order");
            if (orders.putIfAbsent(order.id(), order) != null) {
                throw new IllegalStateException("duplicate order: " + order.id());
            }
        }

        public boolean contains(String id) {
            return orders.containsKey(id);
        }
    }

    // Triển khai gửi thông báo bằng console.
    public static final class ConsoleNotifier implements Notifier {
        @Override
        public void notifyPlaced(String orderId) {
            System.out.println("NOTICE " + orderId);
        }
    }

    // Lớp nghiệp vụ: KHÔNG tự new InMemoryOrderStore/ConsoleNotifier.
    public static final class OrderService {
        private final OrderStore store;
        private final Notifier notifier;

        public OrderService(OrderStore store, Notifier notifier) {
            this.store = Objects.requireNonNull(store, "store");
            this.notifier = Objects.requireNonNull(notifier, "notifier");
        }

        public String place(OrderRequest order) {
            Objects.requireNonNull(order, "order");
            store.save(order);
            notifier.notifyPlaced(order.id());
            return "ACCEPTED " + order.id();
        }
    }

    public static void main(String[] args) {
        // Composition root Java thuần: chọn và lắp ráp dependency.
        InMemoryOrderStore store = new InMemoryOrderStore();
        Notifier notifier = new ConsoleNotifier();
        OrderService service = new OrderService(store, notifier);

        String result =
                service.place(new OrderRequest("O-101", "BOOK", 2));
        System.out.println(result);
        System.out.println("FOUND " + store.contains("O-101"));

        // Fake dùng trong unit test: không gửi thông báo thật.
        List<String> calls = new ArrayList<>();
        Notifier fake = id -> calls.add(id);
        OrderService tested = new OrderService(new InMemoryOrderStore(), fake);

        String testedResult =
                tested.place(new OrderRequest("T-9", "PEN", 1));
        System.out.println(testedResult);
        System.out.println("FAKE_CALLS " + calls);

        if (!calls.equals(List.of("T-9"))) {
            throw new AssertionError("Notifier contract was not called once");
        }
        System.out.println("TEST PASS");
    }
}
~~~

### Biên dịch và chạy Java 17+

Mở terminal tại thư mục **`first-business-app`**, dùng JDK 17 trở lên. PowerShell/CMD/Linux/macOS đều chạy được các lệnh sau (dấu `/` trong đường dẫn được Java tooling hỗ trợ):

~~~bash
javac --release 17 -encoding UTF-8 -d out src/main/java/demo/PlainJavaDemo.java
java -cp out demo.PlainJavaDemo
~~~

**Stdout chính xác từ chương trình `PlainJavaDemo`:**

~~~text
NOTICE O-101
ACCEPTED O-101
FOUND true
ACCEPTED T-9
FAKE_CALLS [T-9]
TEST PASS
~~~

Phân tích theo thứ tự:

1. `main` tạo `InMemoryOrderStore`, `ConsoleNotifier` rồi truyền vào constructor `OrderService`.
2. `OrderService.place` gọi `store.save`, sau đó `notifier.notifyPlaced`; thông báo thật in `NOTICE O-101`.
3. `main` in giá trị trả về `ACCEPTED O-101` và xác nhận đơn tồn tại trong store.
4. Ở phép thử, `fake` là lambda thực hiện hợp đồng `Notifier` bằng cách ghi lại mã đơn vào list. Do đó **không có dòng `NOTICE T-9`**.
5. Test so sánh các lời gọi với `List.of("T-9")`, chứng minh service đã gửi chính xác một thông báo cho mã đơn mong đợi.

**Vì sao dùng `record`?** `OrderRequest` là dữ liệu đầu vào có các component truy cập qua `id()`, `sku()`, `quantity()`. Record được hỗ trợ ổn định ở Java 17; *compact constructor* `public OrderRequest { ... }` kiểm tra dữ liệu đầu vào và không phải tự gán lại từng field khi điều kiện hợp lệ.

**Lưu ý về thứ tự side effect:** demo lưu rồi thông báo. Nếu thông báo lỗi sau khi lưu, thao tác lưu đã xảy ra; Java thuần không tự rollback `Map`. Ứng dụng thật cần chính sách rõ như retry, idempotency, transaction/outbox khi liên quan tới nhiều hệ thống. Đó là chủ đề nâng cao, không nên ngầm tuyên bố ví dụ này “atomic”.

## 5. Từng quyết định thiết kế đang giải quyết vấn đề gì?

### 5.1. Lớp nghiệp vụ chỉ biết contract

~~~java
public OrderService(OrderStore store, Notifier notifier) {
    this.store = Objects.requireNonNull(store, "store");
    this.notifier = Objects.requireNonNull(notifier, "notifier");
}
~~~

Đây là trích đoạn đã nằm trong `PlainJavaDemo.java`. Constructor thể hiện **dependency bắt buộc**. Dùng `final` bảo đảm reference không được gán lại sau khi tạo object, không mặc nhiên biến đối tượng phụ thuộc thành bất biến hay thread-safe.

Lớp nghiệp vụ **không phụ thuộc vào tên các implementation**. Khi muốn in ra file thay vì console hoặc lưu vào database thay vì Map, chính điểm lắp ráp sẽ thay triển khai tương ứng (với điều kiện các implementation giữ contract).

### 5.2. Phân biệt `uses` với `creates`

Hai cách viết:

~~~java
// Ghép chặt: dịch vụ tự chọn và tạo cộng tác viên.
final class BadOrderService {
    private final ConsoleNotifier notifier = new ConsoleNotifier();
}
~~~

~~~java
// Tiêm dependency: dịch vụ chỉ khai báo thứ nó cần.
final class BetterOrderService {
    private final Notifier notifier;

    BetterOrderService(Notifier notifier) {
        this.notifier = Objects.requireNonNull(notifier);
    }
}
~~~

Hai khối **minh họa thiết kế**, không runnable độc lập vì `ConsoleNotifier` và `Notifier` ở phần này dùng lại từ ví dụ chính. Điểm cần nhớ không phải cấm `new`, mà là **đưa quyền chọn và dựng collaborator đến nơi có trách nhiệm lắp ráp**.

Một object dữ liệu ngắn hạn như `new ArrayList<>()` trong nội bộ method không nhất thiết phải thành Spring bean. Trái lại, một HTTP client, mail sender hoặc repository cần cấu hình/lifecycle thường là ứng viên tốt để truyền từ ngoài vào.

### 5.3. Hợp đồng không có nghĩa mọi thay đổi đều miễn phí

Thay implementation là thuận lợi khi giữ đúng hành vi đã thỏa thuận. Nếu nghiệp vụ đổi từ “chỉ lưu đơn” sang “trừ tồn kho, thu tiền, có kiểm tra rủi ro”, chính `OrderService` và contract có thể cần thay đổi. Tránh quảng cáo interface như cách không bao giờ phải sửa business code.

Nếu một interface phình ra với hàng chục method không liên quan, hãy chia theo năng lực consumer cần dùng (Interface Segregation). Nếu chỉ có một triển khai ổn định và không cần abstraction, constructor injection của concrete class vẫn có thể hợp lý.

### 5.4. Nên tổ chức file thế nào khi ứng dụng lớn hơn?

Trong dự án thật, nên tách `OrderRequest`, `OrderService`, `OrderStore`, `Notifier` và implementation thành các file/package rõ ràng. Ví dụ:

~~~text
demo.order/
    OrderRequest.java
    OrderService.java
    OrderStore.java
    Notifier.java
demo.adapters/
    InMemoryOrderStore.java
    ConsoleNotifier.java
demo.config/
    AppConfig.java
~~~

Đây là **mẫu tổ chức package**, không phải cấu trúc cần tạo để chạy demo một file. Các package có thể được đặt tên khác tùy module boundaries; đừng để domain phụ thuộc vào adapter chỉ vì chúng nằm cùng thư mục trong bài thực hành.

## 6. Thay bước lắp ráp bằng Spring Core Container

Vẫn dùng nguyên file `PlainJavaDemo.java` ở mục 4. Chỉ thêm **`pom.xml`** và **`SpringBusinessApp.java`**. Điều này cho thấy ứng dụng **không cần viết lại service để “chuyển sang Spring”**: ta chỉ thay nơi tạo và đưa các dependency vào.

### 6.1. Maven dependency

Dùng cùng mốc Spring Framework 7.0.9/Java 17 như bài chuẩn bị thư viện. Ví dụ là ứng dụng console với `spring-context`, **không sử dụng Spring Boot, web server hay database**.

Tạo `pom.xml` tại thư mục `first-business-app`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>first-business-app</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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
                    <mainClass>demo.SpringBusinessApp</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. Cấu hình bean và chương trình Spring

Tạo `src/main/java/demo/SpringBusinessApp.java`:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class SpringBusinessApp {
    private SpringBusinessApp() {
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public PlainJavaDemo.InMemoryOrderStore orderStore() {
            return new PlainJavaDemo.InMemoryOrderStore();
        }

        @Bean
        public PlainJavaDemo.Notifier notifier() {
            return new PlainJavaDemo.ConsoleNotifier();
        }

        @Bean
        public PlainJavaDemo.OrderService orderService(
                PlainJavaDemo.OrderStore store,
                PlainJavaDemo.Notifier notifier) {
            return new PlainJavaDemo.OrderService(store, notifier);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            PlainJavaDemo.OrderService service =
                    context.getBean(PlainJavaDemo.OrderService.class);

            String result = service.place(
                    new PlainJavaDemo.OrderRequest("S-202", "NOTEBOOK", 3));

            System.out.println(result);
            System.out.println("FOUND "
                    + context.getBean(
                            PlainJavaDemo.InMemoryOrderStore.class
                      ).contains("S-202"));
        }
    }
}
~~~

Từ thư mục `first-business-app` (có `pom.xml`), chạy:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

**Các dòng stdout do `SpringBusinessApp` in, theo thứ tự:**

~~~text
NOTICE S-202
ACCEPTED S-202
FOUND true
~~~

`mvn -version` và Maven/plugin có thể in các dòng riêng (phiên bản, log hoặc tiến trình tải dependency). Khối stdout trên chỉ là **ba dòng do logic ví dụ tạo ra**. Lần đầu cần Maven có khả năng tải dependency nếu cache chưa có.

### 6.3. Spring đã làm gì thay `main` Java thuần?

1. `AnnotationConfigApplicationContext(AppConfig.class)` đọc lớp cấu hình và khởi tạo context.
2. `@Bean orderStore()` tạo `InMemoryOrderStore`; `@Bean notifier()` tạo `ConsoleNotifier`. Chúng trở thành bean được quản lý bởi container.
3. `@Bean orderService(OrderStore store, Notifier notifier)` khai báo hai dependency bằng kiểu hợp đồng. Spring giải quyết các bean phù hợp và truyền chúng vào tham số phương thức factory.
4. `new PlainJavaDemo.OrderService(store, notifier)` vẫn hiện diện **trong configuration**, nhưng `OrderService` không tự `new` những collaborator đó.
5. `context.getBean(OrderService.class)` lấy service đã nối đầy đủ; hành vi `place` và dữ liệu `OrderRequest` giữ nguyên.
6. `try-with-resources` đóng context. Đối với bean thuộc quản lý Spring, các callback hủy phù hợp được xử lý theo vòng đời của context.

**Không cần `@Autowired` ở các tham số `@Bean`**: Spring giải quyết dependency của factory method. Cũng không cần `@ComponentScan` vì tất cả bean đã được đăng ký qua `@Bean` trong `AppConfig`.

**Không cần đặt `@Service` lên `PlainJavaDemo.OrderService`**: bản thân class có thể là Java class thông thường; container quản lý instance mà `@Bean` trả về. Annotation Spring nên dùng vì nó phục vụ một cơ chế cụ thể, không phải để làm cho domain “trông giống Spring”.

## 7. Ranh giới giữa bản Java và bản Spring

| Tiêu chí | Java thuần | Spring Core Container |
| --- | --- | --- |
| Ai gọi `new` collaborator? | `main`, factory hoặc composition root | `@Bean` factory/configuration hoặc cơ chế tạo bean |
| Ai truyền `OrderStore` và `Notifier` vào service? | Mã lắp ráp thủ công | Container giải quyết tham số `@Bean` |
| Service có phải import Spring? | Không | **Không**, nếu dùng domain độc lập như ví dụ |
| Có thể thay fake khi test? | Có, truyền qua constructor | Có, và có thể test service **không cần** context |
| Đối tượng có thành Spring bean? | Không, trừ khi tự đăng ký vào container | Có với instance tạo/đăng ký qua `@Bean` |
| Lifecycle chính | Người tạo/chủ sở hữu tự quản | Container phối hợp lifecycle cho bean thuộc quản lý |
| Có tự động REST endpoint/transaction? | Không | **Không**; cần hạ tầng riêng nếu muốn |

**DI không đồng nghĩa Spring**; constructor injection đã xuất hiện trong ví dụ Java thuần. Spring giúp cấu hình và quản lý object graph khi hệ thống lớn lên. Ngược lại, dùng Spring không tự làm thiết kế hợp đồng trở nên đúng: nếu đặt logic nghiệp vụ vào `@Configuration` hay dùng `ApplicationContext.getBean(...)` khắp nơi, kiến trúc vẫn có thể khó kiểm thử và khó bảo trì.

### Tránh nhầm singleton

Mặc định, `@Bean` thường có scope `singleton` trong *một* container. Điều này nói về một instance của bean theo định nghĩa trong context, **không đồng nghĩa an toàn đa luồng**. `InMemoryOrderStore` ở đây dùng `HashMap` để demo; **không thích hợp làm kho lưu trữ production đa luồng** nếu không có cơ chế đồng bộ/chọn storage phù hợp. Đừng dùng nó như database thật.

## 8. Kiểm thử contract và lớp nghiệp vụ

### 8.1. Unit test không cần Spring

Với dependency qua constructor, một fake có thể thay thế `Notifier`. Mục 4 đã minh họa `List<String> calls` để xác nhận service phát ra đúng mã đơn. Ta cũng có thể kiểm tra rằng đối số không hợp lệ bị từ chối trước khi truy cập store.

Một phép thử bổ sung **độc lập về ý tưởng**, có thể chèn vào `main` Java thuần (không thêm vào chương trình chính nếu muốn giữ stdout mục 4):

~~~java
try {
    new PlainJavaDemo.OrderRequest("BAD", "BOOK", 0);
    throw new AssertionError("Expected validation failure");
} catch (IllegalArgumentException expected) {
    System.out.println("VALIDATION PASS");
}
~~~

Nếu đặt khối trên vào `main` sau các ví dụ, sẽ **in thêm** `VALIDATION PASS`. Không coi nó là một phần stdout đã công bố ở mục 4.

Có thể thử tiếp:

- `new OrderService(null, notifier)` phải ném `NullPointerException` do `requireNonNull`.
- Gọi `save` hai lần với cùng `id` trên một `InMemoryOrderStore` phải từ chối lần thứ hai.
- Khi `Notifier` fake ném exception, theo thiết kế demo, store đã lưu đơn. Test nên làm rõ giới hạn này thay vì giả định có rollback.
- Thay implementation `OrderStore` bằng fake ghi nhận input, kiểm tra service chuyển đúng `OrderRequest`.

### 8.2. Integration test với Spring Context

Unit test của `OrderService` không nhất thiết phải khởi động Spring. Nhưng để kiểm tra *wiring*, có thể dựng context từ `AppConfig` trong một test, lấy `OrderService` bằng `getBean` và xác minh dependency/cách gọi.

Điều cần kiểm tra ở integration test:

- Có đúng một ứng viên `OrderStore` và `Notifier` phù hợp để inject.
- Cấu hình context khởi động thành công.
- Bean của `OrderService` lấy được và không có dependency bị thiếu.
- Nếu thêm nhiều implementation cùng interface, cơ chế lựa chọn (`@Primary`, `@Qualifier`, tên...) rõ ràng.
- Không test “chính xác có một bean trong toàn JVM”: singleton là theo container.

Khi test wiring với data source/email thật, cần tách môi trường test để tránh phát sinh tác dụng phụ ngoài ý muốn.

## 9. Hướng phát triển từ ví dụ đầu tiên

Khi triển khai thành ứng dụng có ích hơn, có thể phát triển từng phần:

1. **Domain model:** thêm trạng thái đơn, giá và ràng buộc có ý nghĩa. Chọn kiểu số tiền thích hợp; tránh dùng `double` cho tính toán tiền yêu cầu chính xác.
2. **Repository:** thay `InMemoryOrderStore` bằng triển khai database, giữ đúng hợp đồng lưu và lỗi trùng mã.
3. **Notifier:** thêm email/queue, chính sách retry và idempotency thích hợp; tuyệt đối không hard-code secret vào business class.
4. **Service:** tách các quy tắc tồn kho, thanh toán, xét duyệt nếu use case yêu cầu; không dồn mọi hành vi vào một “God Service”.
5. **Cấu hình:** dồn việc chọn triển khai, tạo client và quản lý tài nguyên về adapter/configuration.
6. **Transaction:** nếu cần tính nhất quán nhiều bước lưu dữ liệu, cấu hình transaction manager và ranh giới giao dịch. `@Bean` đơn thuần không cung cấp database transaction.
7. **Web API:** khi cần HTTP, thêm controller và Spring Web MVC hoặc WebFlux. `spring-context` một mình không tự mở cổng HTTP.
8. **Quan sát lỗi:** đưa ra exception/log rõ ràng; xác định chính sách retry nếu gửi thông báo thất bại.
9. **Kiểm thử:** unit test service bằng fake, integration test wiring và persistence, acceptance test cho luồng end-to-end.

Lưu ý thứ tự thiết kế: **hợp đồng phản ánh yêu cầu của lớp sử dụng**, sau đó lựa chọn công nghệ adapter. Không nên để tên thư viện/hạ tầng chi phối toàn bộ API nghiệp vụ.

## 10. Lỗi phổ biến và cách nhận diện

| Triệu chứng | Nguyên nhân / hướng xử lý |
| --- | --- |
| Service vừa xử lý đơn vừa tự `new JdbcConnection` | Trộn nghiệp vụ và construction detail; đưa collaborator ra constructor |
| Trường khai báo `OrderStore` nhưng khởi tạo `new SqlOrderStore()` ngay trong service | Vẫn khóa cách tạo triển khai cụ thể; interface ở biến chưa đủ |
| Constructor có 10–15 dependency không liên quan | Xem lại trách nhiệm service; cân nhắc tách use case/aggregator thay vì che bằng injection |
| Service gọi `ApplicationContext.getBean(...)` mọi nơi | Service Locator làm dependency ẩn; ưu tiên constructor injection |
| `@Bean orderService` không tìm thấy `OrderStore` | Chưa đăng ký bean, sai type hoặc profile; kiểm tra configuration |
| Có 2 bean `Notifier` và injection mơ hồ | Chọn triển khai bằng `@Qualifier`/`@Primary` hoặc thiết kế cấu hình rõ |
| Tự `new OrderService(...)` ngoài context rồi chờ bean lifecycle | Object ngoài container không tự được quản lý như bean |
| Dùng `HashMap` store của demo để phục vụ nhiều request đồng thời | Mutable state không thread-safe; cần storage/synchronization phù hợp |
| Fake test chỉ kiểm tra không ném lỗi, không kiểm tra lời gọi | Nên assert mã đơn được gửi và số lần gọi |
| Gọi `Notifier` fail rồi tin rằng store tự rollback | Không có transaction/compensation; thiết kế policy nhất quán rõ ràng |
| Bỏ qua kiểm tra `id`/`quantity` | Dữ liệu invalid lan sâu vào collaborator; đặt invariant ở đúng đối tượng |
| Viết interface chỉ để “đúng mẫu” dù không có mục đích | Tránh abstractions dư thừa; thiết kế hướng tới khả năng thay thế/ranh giới cụ thể |

## 11. Bài tập tự luyện có đáp án

**Bài 1 — xác định phụ thuộc bị khóa.** Vì sao đoạn này khó test hơn?

~~~java
class OrderService {
    private final SmtpNotifier notifier = new SmtpNotifier();
}
~~~

Đây là mã minh họa (thiếu class `SmtpNotifier`). **Đáp án:** service tự chọn triển khai SMTP và tự khởi tạo. Nếu muốn thay bằng fake để test, phải sửa mã hoặc tạo đường vòng; constructor injection giải quyết bằng cách nhận contract `Notifier`.

**Bài 2 — thêm lựa chọn triển khai.** Giả sử có `RecordingNotifier implements Notifier`. Có cần sửa `OrderService.place` để dùng fake không?

**Đáp án:** Không, nếu fake tuân thủ contract. Chỉ truyền `RecordingNotifier` khi tạo service hoặc thay bean `Notifier` trong cấu hình dùng cho test.

**Bài 3 — trách nhiệm của `@Bean`.** Vì sao code `return new PlainJavaDemo.InMemoryOrderStore();` trong `@Bean` không phải vi phạm quy tắc tránh `new` ở lớp nghiệp vụ?

**Đáp án:** `@Configuration` có trách nhiệm **chọn và tạo dependency**. `OrderService` không biết lớp concrete và không phải nơi tạo adapter.

**Bài 4 — phân biệt contract và data.** `OrderRequest` có nên được tạo làm singleton Spring bean để tái sử dụng ở mọi đơn không?

**Đáp án:** Không. `OrderRequest` chứa dữ liệu từng lần gọi. Dùng record immutable mới cho từng yêu cầu; biến nó thành singleton bean thường tạo ràng buộc vòng đời sai.

**Bài 5 — quy tắc xử lý lỗi.** Nếu đơn lưu thành công nhưng gửi thông báo thất bại, trong ví dụ hiện tại có rollback không?

**Đáp án:** Không. `save` đã chạy trước `notifyPlaced`, không có transaction hoặc cơ chế bù trừ. Cần policy rõ khi muốn xử lý trường hợp này trong ứng dụng thật.

**Bài 6 — đổi persistence.** Nếu chuyển từ `InMemoryOrderStore` sang `JdbcOrderStore`, phần nào sẽ thay?

**Đáp án:** Viết adapter mới tuân thủ `OrderStore`, cấu hình bean/factory và bổ sung datasource/driver/test thích hợp. `OrderService` không cần đổi nếu contract và quy tắc nghiệp vụ giữ nguyên.

## 12. Checklist trước khi hoàn thành ứng dụng đầu tiên

- [ ] Xác định một ca sử dụng có hành vi rõ (ví dụ tiếp nhận đơn).
- [ ] Đặt lớp nghiệp vụ theo hành vi: `OrderService.place`.
- [ ] Xác định dữ liệu đầu vào và invariant: `OrderRequest`.
- [ ] Chỉ tạo contract collaborator thực sự cần: `OrderStore`, `Notifier`.
- [ ] Cho mỗi implementation thực hiện một trách nhiệm chính, không “nhét” nghiệp vụ vào adapter.
- [ ] Khai báo dependency bắt buộc trong constructor, kiểm tra không null.
- [ ] Lắp ráp bằng `main` Java thuần trước, kiểm tra đầu ra và lỗi cơ bản.
- [ ] Tạo fake để test service không cần I/O thật.
- [ ] Khi thêm Spring, dùng `@Configuration`/`@Bean` để lắp object graph, không sửa business rules.
- [ ] Xác nhận `mvn compile exec:java` chạy được và phân biệt stdout chương trình với log Maven.
- [ ] Rà trường hợp duplicate id, input invalid, collaborator exception và side effect không atomic.
- [ ] Không coi IoC Container đồng nghĩa với database transaction, HTTP server hoặc unit test framework.

**Kết luận:** Khi xây dựng ứng dụng Spring đầu tiên, hãy tách **lớp nghiệp vụ** khỏi **hợp đồng của đối tượng cộng tác**. `OrderService` biểu đạt hành vi tiếp nhận đơn; `OrderStore` và `Notifier` biểu đạt năng lực mà service cần. Java 17 đã hỗ trợ constructor injection và fake test. Spring Core Container giúp tạo/nối các bean theo `@Configuration`/`@Bean` mà không buộc domain phụ thuộc trực tiếp vào Spring — đây là nền tảng để mở rộng ứng dụng mà vẫn kiểm soát được trách nhiệm từng lớp.