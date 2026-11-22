# Vấn đề ghép nối đối tượng khi tự khởi tạo bằng `new` — Spring Core Container

## 1. Tình huống: nghiệp vụ tự chọn và tự tạo cộng tác viên

Hãy xét một dịch vụ xử lý đơn hàng. Sau khi chấp nhận đơn, nó cần gọi một đối tượng khác để gửi thông báo. Cách viết trực tiếp thường gặp là:

~~~java
class OrderService {
    private final EmailNotifier notifier = new EmailNotifier();

    void placeOrder(String orderId) {
        // Xử lý đơn hàng ...
        notifier.send(orderId);
    }
}
~~~

Đây là **đoạn minh họa**, không phải chương trình biên dịch độc lập: `EmailNotifier` và `send` chưa được định nghĩa ở đây. Vấn đề cần nhận diện không nằm ở cú pháp `new`, mà ở việc **`OrderService` tự quyết định mình phụ thuộc vào lớp cụ thể nào và tự chịu trách nhiệm khởi tạo nó**.

Có hai mối liên hệ cần phân biệt:

- **Phụ thuộc khi sử dụng (*usage dependency*):** `OrderService` cần hành vi gửi thông báo. Đây là nhu cầu nghiệp vụ có thật.
- **Phụ thuộc khi khởi tạo (*construction dependency*):** `OrderService` còn biết tên lớp `EmailNotifier`, constructor, các tham số cấu hình và đôi khi cả chuỗi đối tượng mà `EmailNotifier` cần.

Khi hai việc bị trộn trong một lớp, lớp nghiệp vụ không chỉ **dùng** cộng tác viên mà còn **chọn và lắp ráp** cộng tác viên đó. Đây là một hình thức **ghép nối chặt (*tight coupling*)**.

> `new` không tự động là lỗi thiết kế. Vấn đề đáng chú ý là `new` một *dịch vụ/phụ thuộc có chính sách thay đổi* ở ngay bên trong lớp nghiệp vụ cần dùng nó.

## 2. Ghép nối xuất hiện chính xác ở đâu?

Ở dòng:

~~~java
private final EmailNotifier notifier = new EmailNotifier();
~~~

`OrderService` đã gắn với ít nhất ba quyết định:

1. **Loại triển khai:** phải là `EmailNotifier` thay vì SMS, thông báo nội bộ, gửi qua queue hoặc một bản fake dùng khi kiểm thử.
2. **Cách tạo:** phải có constructor phù hợp; nếu sau này constructor cần `HttpClient`, cấu hình máy chủ hoặc thông tin xác thực, mã tạo có thể phải thay đổi.
3. **Thời điểm và vòng đời:** đối tượng được tạo khi một `OrderService` được khởi tạo; lớp đang sử dụng vô tình chịu trách nhiệm về việc tạo và có thể cả việc dọn dẹp tài nguyên của nó.

Hệ quả thường gặp:

| Khi yêu cầu thay đổi | Nếu tạo phụ thuộc trực tiếp trong dịch vụ | Điều mong muốn |
| --- | --- | --- |
| Đổi cách thông báo | Sửa mã `OrderService` hoặc thêm nhiều `if` chọn triển khai | Thay cấu hình lắp ráp |
| Test đơn hàng không gửi thông báo thật | Khó thay `EmailNotifier` bằng fake | Tiêm đối tượng ghi nhận lời gọi |
| Triển khai cần cấu hình khác môi trường | Dịch vụ phải đọc/biết cấu hình khởi tạo | Tập trung cấu hình ở biên ứng dụng |
| Phụ thuộc tiếp tục cần phụ thuộc khác | Chuỗi `new` lan vào nhiều lớp | Một nơi chịu trách nhiệm dựng object graph |
| Cần quản lý close/lifecycle của cộng tác viên | Dịch vụ có thể không rõ ai sở hữu tài nguyên | Nơi tạo/quản lý quyết định vòng đời |

Một phép đổi tên lớp chưa chắc tạo ra vấn đề lớn. Nhưng với hệ thống có nhiều cộng tác viên, thay đổi quy tắc tạo ở nhiều lớp khiến mã **khó thay thế, khó kiểm thử và khó cấu hình**. Đây là lý do Spring Core Container giải quyết việc tạo và nối các đối tượng cần quản lý.

**Phân biệt:** khai báo trường kiểu interface nhưng vẫn viết `new EmailNotifier()` bên trong dịch vụ chỉ giảm sự phụ thuộc ở **kiểu biến**; nó **chưa tách quyết định khởi tạo** khỏi dịch vụ.

## 3. Ví dụ Java 17 chạy độc lập: thấy sự khác biệt

Ví dụ này dùng thông báo in console, không cần server hay Internet. Cả cách ghép nối chặt và cách nhận phụ thuộc từ bên ngoài đều chạy được, nhưng cách thứ hai cho phép đưa vào một fake khi test.

Lưu tệp **`ManualWiringDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ManualWiringDemo {
    interface Notifier {
        void send(String orderId);
    }

    static final class ConsoleNotifier implements Notifier {
        @Override
        public void send(String orderId) {
            System.out.println("CONSOLE " + orderId);
        }
    }

    // Dịch vụ tự chọn lớp triển khai và tự tạo phụ thuộc.
    static final class HardWiredOrderService {
        private final ConsoleNotifier notifier = new ConsoleNotifier();

        void place(String orderId) {
            System.out.println("ORDER " + orderId);
            notifier.send(orderId);
        }
    }

    // Dịch vụ chỉ phụ thuộc vào hợp đồng hành vi.
    static final class OrderService {
        private final Notifier notifier;

        OrderService(Notifier notifier) {
            this.notifier = Objects.requireNonNull(notifier, "notifier");
        }

        void place(String orderId) {
            System.out.println("ORDER " + orderId);
            notifier.send(orderId);
        }
    }

    // Fake kiểm thử: chỉ ghi lại các lời gọi, không gửi gì ra ngoài.
    static final class RecordingNotifier implements Notifier {
        private final List<String> events = new ArrayList<>();

        @Override
        public void send(String orderId) {
            events.add(orderId);
        }

        List<String> events() {
            return events;
        }
    }

    public static void main(String[] args) {
        System.out.println("-- hard-wired --");
        new HardWiredOrderService().place("A01");

        System.out.println("-- injected --");
        new OrderService(new ConsoleNotifier()).place("B02");

        RecordingNotifier fake = new RecordingNotifier();
        new OrderService(fake).place("T03");
        if (!fake.events().equals(List.of("T03"))) {
            throw new AssertionError("Notifier was not called as expected");
        }
        System.out.println("events=" + fake.events());
        System.out.println("test=PASS");
    }
}
~~~

Mở terminal tại thư mục chứa file, dùng **JDK 17+** (PowerShell/CMD hoặc bash):

~~~bash
javac --release 17 -encoding UTF-8 ManualWiringDemo.java
java ManualWiringDemo
~~~

**Stdout chính xác:**

~~~text
-- hard-wired --
ORDER A01
CONSOLE A01
-- injected --
ORDER B02
CONSOLE B02
ORDER T03
events=[T03]
test=PASS
~~~

Giải thích từng phần:

1. `HardWiredOrderService` luôn tạo `ConsoleNotifier`. Muốn thay cách gửi, thường phải sửa chính lớp dịch vụ hoặc thiết kế lại điểm tạo.
2. `OrderService` nhận `Notifier` từ **constructor**. Nó chỉ biết lời gọi `send(orderId)`, không biết cách khởi tạo lớp triển khai.
3. Ở `main`, `new OrderService(new ConsoleNotifier())` vẫn hợp lệ: `main` đang đóng vai trò **composition root**, nơi lắp ráp ứng dụng.
4. Ở phép thử, ta truyền `RecordingNotifier`. Việc kiểm tra `events=[T03]` chứng minh dịch vụ đã gọi đúng cổng thông báo, **không cần** email, kết nối mạng hay Spring context.
5. Ví dụ in `ORDER` để mô tả một thao tác nghiệp vụ mô phỏng; nó **không ghi database thật**. Trong hệ thống thực, bước lưu đơn hàng phải được thực hiện bằng cộng tác viên riêng nếu cần.

Để test thêm nhánh lỗi hoặc thay cách thông báo, chỉ cần đưa vào một triển khai `Notifier` khác. Không cần sửa `OrderService` cho từng môi trường kiểm thử.

## 4. Constructor injection giải quyết được gì?

Trong bản cải tiến:

~~~java
final class OrderService {
    private final Notifier notifier;

    OrderService(Notifier notifier) {
        this.notifier = java.util.Objects.requireNonNull(notifier);
    }

    void place(String id) {
        notifier.send(id);
    }
}
~~~

Đây là **mẫu minh họa**, tách riêng khỏi file hoàn chỉnh ở mục 3. Ba quyết định thiết kế quan trọng:

- **Hợp đồng hành vi:** `Notifier` mô tả *cần làm gì*; các lớp cụ thể quyết định *làm như thế nào*.
- **Injection:** tham chiếu cộng tác viên được truyền vào qua constructor thay vì được tạo trong dịch vụ. Với dependency bắt buộc, trường `final` và constructor thể hiện rõ yêu cầu.
- **Tách nơi lắp ráp:** lớp nghiệp vụ không phải tự tìm, tạo hoặc chọn phương án triển khai.

Đây là ứng dụng của **Dependency Inversion Principle (DIP)** khi tầng nghiệp vụ hướng tới abstraction phù hợp, thay vì hướng thẳng tới chi tiết hạ tầng. **Dependency Injection (DI)** là một kỹ thuật cung cấp cộng tác viên từ bên ngoài; bản thân DI không bắt buộc có Spring hay interface trong mọi trường hợp. Có thể inject cả một lớp cụ thể khi hợp lý, dù abstraction thường có ích nếu thật sự cần thay thế triển khai.

Điểm khác biệt cốt lõi là:

~~~text
Tạo cứng trong dịch vụ:
OrderService ──new──> ConsoleNotifier

Nhận từ ngoài:
Composition root ──new──> ConsoleNotifier
        │
        └──new OrderService(notifier)──> OrderService ──uses──> Notifier
~~~

**Không phải “xóa mọi `new`”:** ta *chuyển quyền quyết định tạo và nối* ra khỏi lớp nghiệp vụ. Một nơi nào đó vẫn phải tạo các đối tượng.

## 5. Kiểm tra mức độ tách phụ thuộc

Đổi kiểu trường sang `Notifier` **chưa đủ** nếu bên trong `OrderService` vẫn gọi `new EmailNotifier()`: dịch vụ vẫn quyết định triển khai và cách khởi tạo. Phép thử thiết kế là hỏi **“ai chọn và tạo collaborator?”**. Với `OrderService(Notifier notifier)`, câu trả lời nằm ở caller/composition root; dịch vụ chỉ gọi hợp đồng `send`.

Đưa việc chọn triển khai ra ngoài giúp thay notifier hoặc cấu hình mà ít phải sửa nghiệp vụ. Nếu hợp đồng hoặc quy tắc xử lý đơn hàng thay đổi, `OrderService` vẫn có thể cần sửa — DI tách trách nhiệm tạo đối tượng, không bảo đảm mã nghiệp vụ bất biến.

## 6. Spring Core Container tham gia ở đâu?

Java thuần đã có thể làm constructor injection như mục 3. Spring thêm một **IoC container** để quản lý các đối tượng được đăng ký là **bean** và lắp ráp chúng dựa trên cấu hình.

- **IoC (*Inversion of Control*):** quyền điều phối tạo, cấu hình và liên kết các bean chuyển từ mã nghiệp vụ sang container/điểm cấu hình.
- **DI (*Dependency Injection*):** một cơ chế để cung cấp các phụ thuộc vào đối tượng; trong ví dụ này là constructor parameter.
- **Bean:** đối tượng được Spring container đăng ký và quản lý trong `ApplicationContext`.
- **Object graph:** mạng các đối tượng phụ thuộc vào nhau, ví dụ `OrderService → Notifier`.

Spring không “biến mất” `new`. Nó chỉ giúp **tập trung các quyết định tạo và nối bean**. Đối tượng được tạo bằng `new` ở nơi tùy ý **không tự động trở thành bean** chỉ vì project sử dụng Spring.

Có thể cung cấp bean qua `@Configuration` + `@Bean` hoặc qua component scanning (`@Component`/`@Service` và constructor injection). Bài này chọn **`@Bean` rõ ràng** để nhìn thấy nơi lắp ráp. Không cần nhầm `@Bean` với code nghiệp vụ và không cần đưa annotation Spring vào chính `OrderService`.

## 7. Chương trình Spring chạy được: chuyển lắp ráp sang configuration

Yêu cầu **JDK 17+**, Apache Maven, khả năng tải dependency Maven khi chạy lần đầu. Ví dụ dùng **Spring Framework 6.2.0** với `spring-context`, không dùng Spring Boot và không cần web server. Spring 6.x yêu cầu Java 17 trở lên.

Tạo cấu trúc:

~~~text
coupling-spring/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SpringCouplingDemo.java
~~~

File **`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>coupling-spring</artifactId>
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
                    <mainClass>demo.SpringCouplingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File **`src/main/java/demo/SpringCouplingDemo.java`**:

~~~java
package demo;

import java.util.Objects;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SpringCouplingDemo {
    public interface Notifier {
        void send(String orderId);
    }

    public static final class ConsoleNotifier implements Notifier {
        @Override
        public void send(String orderId) {
            System.out.println("NOTIFY " + orderId);
        }
    }

    public static final class OrderService {
        private final Notifier notifier;

        public OrderService(Notifier notifier) {
            this.notifier = Objects.requireNonNull(notifier, "notifier");
        }

        public void place(String orderId) {
            System.out.println("ORDER " + orderId);
            notifier.send(orderId);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public Notifier notifier() {
            return new ConsoleNotifier();
        }

        @Bean
        public OrderService orderService(Notifier notifier) {
            return new OrderService(notifier);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(OrderService.class).place("S04");
        }
    }
}
~~~

Từ thư mục `coupling-spring`, chạy:

~~~bash
mvn -q compile exec:java
~~~

**Các dòng stdout do chương trình in:**

~~~text
ORDER S04
NOTIFY S04
~~~

Lệnh Maven có thể phát sinh thông báo khác tùy phiên bản, plugin, môi trường hoặc việc tải dependency; hai dòng trên là **stdout được in bởi logic ví dụ**, không khẳng định toàn bộ output của Maven luôn chỉ có hai dòng.

### Theo vết việc tạo và nối bean

1. `new AnnotationConfigApplicationContext(AppConfig.class)` tạo context và xử lý cấu hình.
2. `@Bean notifier()` trả về một `ConsoleNotifier`. `new` **vẫn tồn tại**, nhưng ở lớp cấu hình thay vì trong `OrderService`.
3. `@Bean orderService(Notifier notifier)` khai báo nhu cầu một bean kiểu `Notifier`; Spring tìm bean phù hợp và truyền nó vào tham số.
4. Spring trả `OrderService` đã được nối phụ thuộc; `context.getBean(OrderService.class)` lấy bean từ container.
5. `place("S04")` gọi đúng hành vi; `try-with-resources` đóng context sau khi dùng.

Mặc định, bean trong Spring có scope `singleton` **theo từng container**. Đây không phải bảo đảm rằng toàn bộ JVM chỉ có đúng một đối tượng cho mọi context. Nếu một kiểu có nhiều bean cùng phù hợp, phải cấu hình rõ lựa chọn (chẳng hạn `@Qualifier`/`@Primary` hoặc inject bằng tên thích hợp); Spring không tự đoán ý định nghiệp vụ.

Trong ví dụ này, nếu đổi `notifier()` để tạo một triển khai khác cùng hợp đồng `Notifier`, phần xử lý `OrderService` không cần đổi. Việc cấu hình vẫn là mã ứng dụng và phải được kiểm thử phù hợp.

## 8. So sánh ba cách lắp ráp

| Tiêu chí | `new` ngay trong dịch vụ | Tự inject bằng Java | Inject qua Spring container |
| --- | --- | --- | --- |
| Dịch vụ biết lớp notifier cụ thể? | Có | Không nếu nhận interface | Không nếu nhận interface |
| Chọn triển khai ở đâu? | Trong dịch vụ | `main`/factory/composition root | `@Configuration`/component setup |
| Cần Spring để hoạt động? | Không | Không | Có cho phần container |
| Thay fake khi unit test | Thường khó hơn | Dễ: truyền qua constructor | Có thể test service thuần bằng constructor; integration test có context |
| Ai quản lý bean lifecycle? | Mã tự tạo | Người lắp ráp/chủ sở hữu | Spring quản lý những bean thuộc context |
| Có hoàn toàn xóa `new` không? | Không | Không | Không |

**Điểm mấu chốt:** Spring là công cụ tổ chức việc tạo/nối các phụ thuộc; ưu điểm về thiết kế xuất phát trước hết từ việc lớp nghiệp vụ **nhận phụ thuộc rõ ràng** thay vì tự khóa vào một triển khai.

Không nhất thiết phải khởi động Spring cho mọi unit test. Với `OrderService(Notifier)`, test logic nghiệp vụ có thể chỉ dùng `RecordingNotifier` như chương trình Java thuần. Integration test của Spring cần kiểm tra cấu hình context và kết nối bean nếu đây là điều cần xác nhận.

## 9. Khi nào `new` hoàn toàn hợp lý?

**`new` không bị cấm** trong ứng dụng Spring. Phân biệt theo mục đích và quyền sở hữu:

- **Value object hoặc dữ liệu tạm:** `new BigDecimal("12.50")`, `new ArrayList<>()`, đối tượng kết quả ngắn hạn... thường không cần làm Spring bean.
- **Đối tượng nội bộ thuộc sở hữu lớp:** nếu chỉ là một chi tiết hiện thực đơn giản và việc tạo không cần cấu hình/thay thế, `new` tại chỗ có thể rõ ràng nhất.
- **Composition root hoặc `@Bean` factory:** `new` để tạo cộng tác viên bên ngoài lớp nghiệp vụ là điều bình thường.
- **Cộng tác viên hạ tầng cần cấu hình, chia sẻ, mock/test, lifecycle:** thường là ứng viên tốt để truyền từ ngoài hoặc đăng ký bean.
- **Đối tượng do thư viện tạo:** không nhất thiết có quyền chọn constructor hay biến thành bean; có thể cần adapter/factory ở đúng lớp biên.

Đừng biến *mọi đối tượng* thành singleton bean: dữ liệu theo một lần yêu cầu, trạng thái thay đổi và tài nguyên có vòng đời riêng cần scope/lifecycle phù hợp. Trái lại, tự `new` một client kết nối ở mỗi lần xử lý mà không quản lý dọn dẹp cũng có thể gây lãng phí hoặc rò rỉ tài nguyên.

Một câu hỏi hữu ích: **“Nếu ngày mai thay cách triển khai hoặc kiểm thử phần này, tôi cần sửa lớp nghiệp vụ hay chỉ đổi cách lắp ráp?”** Nếu luôn phải sửa lớp nghiệp vụ chỉ để đổi hạ tầng, ghép nối thường đang cao hơn mức cần thiết.

## 10. Những hiểu nhầm và lỗi thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Mọi `new` đều phá DI.” | Chỉ việc lớp nghiệp vụ tự chọn/tạo *phụ thuộc cần tách* mới thường gây vấn đề; tạo value object là bình thường. |
| “Chỉ cần khai báo interface là đã decouple.” | Nếu trong dịch vụ vẫn `new ConcreteNotifier()` thì quyết định tạo vẫn nằm ở đó. |
| “Dùng Spring là không viết `new` nữa.” | `@Bean` factory thường vẫn dùng `new`; thay đổi là nơi điều phối object graph. |
| “Một đối tượng tạo thủ công tự thành Spring bean.” | Không. Chỉ những đối tượng được container đăng ký/quản lý mới nhận các cơ chế container tương ứng. |
| “Bất cứ lớp nào cũng nên `@Autowired` vào field.” | Constructor injection thường rõ dependency bắt buộc hơn và hỗ trợ unit test không cần context. |
| “Spring tự lựa chọn đúng khi có nhiều bean cùng interface.” | Cần quy tắc lựa chọn rõ nếu có nhiều ứng viên; cấu hình mơ hồ có thể làm context khởi động lỗi. |
| “Tách DI là không bao giờ đổi code nghiệp vụ.” | Thay hành vi/hợp đồng nghiệp vụ vẫn cần sửa; DI chủ yếu tách thay đổi chi tiết triển khai/khởi tạo. |
| “Constructor injection tự tránh mọi lỗi vòng phụ thuộc.” | Nếu A cần B và B cần A ngay khi tạo, đó vẫn là vấn đề thiết kế; nên phá vòng thay vì tìm mẹo ẩn nó. |
| “Bean singleton tức là thread-safe.” | Scope không tự bảo đảm an toàn với state thay đổi đồng thời. |
| “Unit test phải bật Spring.” | Logic được inject rõ ràng có thể test với fake thuần Java; chỉ bật context khi cần kiểm thử wiring. |

Một rủi ro bổ sung: đưa `ApplicationContext` vào mỗi lớp rồi tự gọi `getBean(...)` khắp nơi sẽ chuyển phụ thuộc thành **tra cứu ẩn** (Service Locator). Điều đó có thể làm các dependency khó thấy và khó test. Trong dịch vụ nghiệp vụ thông thường, ưu tiên khai báo cộng tác viên bằng constructor.

## 11. Bài tập và đáp án giải thích

**Bài 1 — nhận diện quyết định bị khóa.**

~~~java
class ReportService {
    private final PdfExporter exporter = new PdfExporter();

    void export() {
        exporter.write();
    }
}
~~~

`PdfExporter` ở đây là kiểu minh họa, chưa được định nghĩa. Hỏi: vấn đề chính là gì?

**Đáp án:** `ReportService` quyết định luôn *loại exporter* và *cách tạo exporter*. Khi muốn chuyển sang cách xuất khác hoặc mock trong test, phải thay mã hoặc thiết kế lại lớp. Tạo `Exporter` abstraction và nhận qua constructor là một hướng cải tiến nếu có nhu cầu thay thế thực sự.

**Bài 2 — sửa vị trí tạo.** Với `Notifier` và `OrderService` trong mục 3, muốn dùng fake ở test mà không mở Spring context thì làm thế nào?

**Đáp án:** tạo `RecordingNotifier fake = new RecordingNotifier();` rồi `new OrderService(fake)`. Đối chiếu `fake.events()` để xác nhận tương tác. Test không phải gọi `ConsoleNotifier` thật.

**Bài 3 — tìm `new` hợp lệ.** Tại sao `return new ConsoleNotifier();` trong phương thức `@Bean` không mâu thuẫn với mục tiêu giảm coupling?

**Đáp án:** vị trí này **có nhiệm vụ lắp ráp** và chọn triển khai. Dịch vụ nghiệp vụ chỉ nhận `Notifier`; chi tiết tạo được cô lập ở configuration. Spring quản lý bean trả về.

**Bài 4 — phân biệt cách làm.** Nếu một class nhận `Notifier` qua constructor nhưng chính `main` lại `new ConsoleNotifier()`, đã dùng DI chưa?

**Đáp án:** **Có.** Một đối tượng được truyền từ ngoài vào constructor chính là constructor injection; Spring không phải điều kiện bắt buộc.

**Bài 5 — quyết định có cần bean không.** Một phương thức tạo `new ArrayList<String>()` để gom kết quả tạm thời có nên chuyển thành bean singleton?

**Đáp án:** Thường không. Danh sách tạm mang state theo lời gọi, không phải cộng tác viên hạ tầng chia sẻ. Biến nó thành singleton có thể làm lẫn trạng thái giữa nhiều lần gọi và tăng rủi ro đồng thời.

## 12. Checklist khi gặp mã có nhiều `new`

1. Xác định **lớp nghiệp vụ nào** đang cần hành vi và **lớp cụ thể nào** đang bị tự khởi tạo.
2. Phân biệt giá trị tạm với **service/collaborator** có khả năng thay thế hoặc cần cấu hình.
3. Tìm xem constructor/lifecycle của collaborator có kéo thêm database, network, file hay bí mật cấu hình vào lớp nghiệp vụ không.
4. Thiết kế **hợp đồng nhỏ, có nghĩa** nếu thực sự có nhiều cách triển khai; không tạo interface chỉ vì khuôn mẫu.
5. Dùng **constructor injection** để đưa dependency bắt buộc vào lớp.
6. Chuyển việc chọn/tạo implementation tới **composition root**, factory hoặc Spring `@Configuration`.
7. Test lớp nghiệp vụ với fake đơn giản, kiểm tra hành vi chứ không dựa trên hệ thống ngoài.
8. Test cấu hình Spring riêng khi cần biết các bean được tạo và nối đúng.
9. Kiểm soát vòng đời bean, trạng thái mutable, lỗi cấu hình và các trường hợp có nhiều implementation.
10. Chỉ refactor nơi đem lại lợi ích rõ ràng; tránh biến `new` các đối tượng dữ liệu đơn giản thành cơ chế phức tạp.

**Kết luận:** Điều làm tăng ghép nối không phải riêng từ khóa `new`, mà là để lớp nghiệp vụ **vừa dùng vừa tự quyết định và tạo phụ thuộc cụ thể**. Constructor injection tách hai vai trò này ngay cả trong Java thuần. Spring Core Container tiếp tục hỗ trợ quản lý và nối các bean tại một nơi cấu hình rõ ràng, giúp thay cách triển khai, viết test và quản lý vòng đời dễ hơn khi dự án phát triển.