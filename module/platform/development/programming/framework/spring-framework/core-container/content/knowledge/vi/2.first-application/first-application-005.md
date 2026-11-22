# Lấy bean theo kiểu và thực hiện một luồng xử lý

## 1. Mục tiêu

Bài thực hành Spring Core Container này không dừng ở việc tạo `ApplicationContext`: ta lấy một bean đầu mối theo **kiểu Java** và thực sự gọi use case của nó.

Chuỗi công việc:

1. Định nghĩa một lớp nghiệp vụ `OrderService` cùng hai hợp đồng cộng tác `OrderRepository` và `Notifier`.
2. Đăng ký các bean bằng `@Configuration`/`@Bean`, để Spring nối dependency.
3. Khởi động `AnnotationConfigApplicationContext`.
4. Gọi `context.getBean(OrderService.class)` lấy bean service.
5. Gọi `service.place(request)`, theo dõi thao tác lưu, thông báo và giá trị trả về.
6. Đóng context đúng vòng đời.

~~~text
main()
  |-- ApplicationContext(AppConfig)
  |       +-- OrderRepository -> InMemoryOrderRepository
  |       +-- Notifier        -> ConsoleNotifier
  |       +-- OrderService(repository, notifier)
  |
  +-- getBean(OrderService.class)
          |
          +-- place(OrderRequest)
               +-- repository.save(...)
               +-- notifier.notifyPlaced(...) [nếu lưu mới]
               +-- trả trạng thái
~~~

**Phân biệt:** container tạo/nối bean; **lời gọi phương thức** trên bean mới thực hiện luồng nghiệp vụ. Đây là ứng dụng console, không phải HTTP endpoint, không có database transaction.

## 2. `getBean(Class<T>)` làm gì?

Ví dụ:

~~~java
OrderService service = context.getBean(OrderService.class);
~~~

Đây là **đoạn cú pháp minh họa**, giả sử `context` và `OrderService` đã được định nghĩa. `ApplicationContext` cung cấp khả năng lookup của `BeanFactory`:

- Có một bean tương thích với kiểu yêu cầu: trả về tham chiếu bean.
- Không có bean phù hợp: có thể ném `NoSuchBeanDefinitionException`.
- Nhiều bean cùng phù hợp nhưng không xác định được ứng viên duy nhất: có thể ném `NoUniqueBeanDefinitionException`.
- Bean hoặc dependency bị lỗi khi tạo: có thể gặp `BeanCreationException` hoặc lỗi injection khác, đôi khi **ngay khi context khởi động** do các singleton không lazy được tạo ở bước refresh.

`getBean` không tự quét tất cả class trên classpath rồi `new` class tùy ý. Muốn lấy được bean, phải đăng ký cấu hình thích hợp: `@Bean`, component scanning hoặc bean definition.

| API | Ý nghĩa |
| --- | --- |
| `getBean(OrderService.class)` | Tra cứu theo kiểu; thường dùng khi có một bean phù hợp |
| `getBean("orderService")` | Tra cứu theo tên; kiểu trả về là `Object` |
| `getBean("orderService", OrderService.class)` | Tra theo tên và yêu cầu đúng kiểu |
| `getBeanNamesForType(OrderService.class)` | Liệt kê các tên bean cùng kiểu để kiểm tra |
| `getBeanProvider(OrderService.class)` | Provider cho trường hợp cần lookup trì hoãn/động |

Trong ví dụ, tên bean mặc định là tên phương thức `@Bean`; tên và type là hai thứ khác nhau. Thông thường không cần lookup bằng name trong code nghiệp vụ.

## 3. Use case: tiếp nhận đơn hàng

Ta mô phỏng xử lý đơn hàng, trong đó:

- `OrderRequest` là record giữ mã đơn, mã sản phẩm và số lượng, kiểm tra điều kiện đầu vào.
- `OrderRepository` định nghĩa contract lưu và kiểm tra mã đã tồn tại.
- `Notifier` định nghĩa contract thông báo sau khi lưu thành công.
- `OrderService` chỉ biết hai contract, nhận qua constructor.
- `InMemoryOrderRepository` dùng `Map` để demo, `ConsoleNotifier` in stdout.
- `AppConfig` quyết định triển khai cụ thể và tạo các bean.
- `main` lấy `OrderService` từ context rồi gọi use case.

Quy tắc xử lý đơn giản: **mã mới thì lưu và thông báo; mã đã tồn tại thì trả trạng thái duplicate và không thông báo thêm**. Khác `OrderStore.save(...)` trong bài thiết kế hợp đồng (ném lỗi khi trùng mã), `OrderRepository.save(...)` ở bài này trả boolean để chính service quyết định nhánh `ALREADY_EXISTS`. Hai contract thể hiện hai lựa chọn nghiệp vụ khác nhau.

Hợp đồng:

~~~java
interface OrderRepository {
    boolean save(OrderRequest order);
    boolean contains(String id);
}

interface Notifier {
    void notifyPlaced(String id);
}
~~~

Khối trên chỉ là **minh họa**, chưa độc lập vì `OrderRequest` chưa có định nghĩa tại đây. Contract của `save` được quy định: trả `true` khi thêm mã mới, `false` khi mã đã có. Trong hệ thống thật có thể dùng kiểu trả về hoặc exception domain khác, nhưng mỗi implementation phải giữ cùng ý nghĩa.

| Thành phần | Trách nhiệm |
| --- | --- |
| `OrderService` | Thực hiện thứ tự `save → notify`, trả kết quả |
| `OrderRepository` | Hợp đồng lưu/tra cứu |
| `InMemoryOrderRepository` | Cách lưu bằng Map |
| `Notifier` | Hợp đồng phát thông báo |
| `ConsoleNotifier` | Cách in ra console |
| `AppConfig` | Chọn và nối concrete collaborators |
| `main` | Khởi động và lấy entry-point bean |

Dùng interface ở đây giúp giả lập repository/notifier trong unit test. **Không bắt buộc mọi dependency của Spring đều phải có interface**; một concrete class cũng có thể được inject nếu hợp lý.

## 4. Project Spring Framework 7 / Java 17 runnable

### 4.1. Chuẩn bị

Yêu cầu JDK 17+, Maven. Ví dụ dùng Spring Framework `7.0.9` qua dependency `spring-context`; không dùng Spring Boot, server, database hoặc AOP.

~~~text
first-bean-flow/
├── pom.xml
└── src/main/java/demo/FirstBeanFlow.java
~~~

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>first-bean-flow</artifactId>
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
                    <mainClass>demo.FirstBeanFlow</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. Lớp Java đầy đủ

Tạo file `src/main/java/demo/FirstBeanFlow.java`:

~~~java
package demo;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class FirstBeanFlow {
    private FirstBeanFlow() {}

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

    public interface OrderRepository {
        boolean save(OrderRequest request);
        boolean contains(String id);
    }

    public interface Notifier {
        void notifyPlaced(String orderId);
    }

    public static final class InMemoryOrderRepository
            implements OrderRepository {
        private final Map<String, OrderRequest> orders =
                new LinkedHashMap<>();

        @Override
        public boolean save(OrderRequest request) {
            Objects.requireNonNull(request, "request");
            return orders.putIfAbsent(request.id(), request) == null;
        }

        @Override
        public boolean contains(String id) {
            return orders.containsKey(id);
        }
    }

    public static final class ConsoleNotifier implements Notifier {
        @Override
        public void notifyPlaced(String orderId) {
            System.out.println("NOTIFY " + orderId);
        }
    }

    public static final class OrderService {
        private final OrderRepository repository;
        private final Notifier notifier;

        public OrderService(OrderRepository repository, Notifier notifier) {
            this.repository = Objects.requireNonNull(repository, "repository");
            this.notifier = Objects.requireNonNull(notifier, "notifier");
        }

        public String place(OrderRequest request) {
            Objects.requireNonNull(request, "request");
            if (!repository.save(request)) {
                return "ALREADY_EXISTS " + request.id();
            }
            notifier.notifyPlaced(request.id());
            return "ACCEPTED " + request.id();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public OrderRepository orderRepository() {
            return new InMemoryOrderRepository();
        }

        @Bean
        public Notifier notifier() {
            return new ConsoleNotifier();
        }

        @Bean
        public OrderService orderService(
                OrderRepository repository, Notifier notifier) {
            return new OrderService(repository, notifier);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);

            System.out.println("SERVICE_BEANS "
                    + context.getBeanNamesForType(OrderService.class).length);
            System.out.println("SAME_SINGLETON "
                    + (service == context.getBean(OrderService.class)));

            OrderRequest request = new OrderRequest("O-101", "BOOK", 2);
            System.out.println(service.place(request));
            System.out.println(service.place(request));

            OrderRepository repository =
                    context.getBean(OrderRepository.class);
            System.out.println("STORED " + repository.contains("O-101"));
        }
    }
}
~~~

Tại thư mục `first-bean-flow`, dùng:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

Maven có thể tải dependencies lần đầu. **Stdout của các lệnh `println` trong chương trình:**

~~~text
SERVICE_BEANS 1
SAME_SINGLETON true
NOTIFY O-101
ACCEPTED O-101
ALREADY_EXISTS O-101
STORED true
~~~

`mvn -version` cùng Maven/plugin có thể in thông tin phiên bản và log khác; sáu dòng là **đầu ra do code chủ động in**, không phải toàn bộ text terminal ở mọi môi trường.

### 4.3. Truy vết từng bước

1. `AnnotationConfigApplicationContext(AppConfig.class)` xử lý cấu hình, đăng ký và tạo các singleton bean không lazy khi refresh.
2. `orderRepository()` tạo repository; `notifier()` tạo notifier.
3. `orderService(OrderRepository, Notifier)` nhận bean dependency từ Spring và tạo service. Không cần `main` tự tra từng dependency trước.
4. `getBean(OrderService.class)` trả bean phù hợp. Trong demo có đúng một service nên in `SERVICE_BEANS 1`.
5. Bean service mặc định singleton trong context. Hai lần lookup lấy cùng reference, nên in `SAME_SINGLETON true`.
6. Lần gọi `place` thứ nhất: Map chưa có id, `putIfAbsent` trả `null`; service gửi một thông báo và trả `ACCEPTED O-101`.
7. Lần thứ hai: repository trả `false` do trùng id; service trả `ALREADY_EXISTS O-101` và **không gửi thông báo**.
8. `getBean(OrderRepository.class)` nhận cùng repository singleton đã inject vào service; `contains` trả `true`.
9. `try-with-resources` đóng context và cho phép Spring xử lý các callback hủy bean tương ứng.

**Giới hạn của ví dụ:** `LinkedHashMap` chỉ giữ dữ liệu trong RAM, không thread-safe, không bền vững. Không có database transaction. Nếu notifier gặp lỗi sau khi repository lưu, dữ liệu có thể đã thay đổi; Core Container không tự rollback.

## 5. Lấy bean và dependency injection là hai công việc khác nhau

`main` gọi `getBean(OrderService.class)` ở **ranh giới khởi chạy**. Đó là thao tác lookup hợp lý. Tuy nhiên, `OrderService` không tự gọi `context.getBean(OrderRepository.class)` trong phương thức `place`.

Thay vào đó, dependency rõ ràng ngay trong constructor:

~~~java
public OrderService(OrderRepository repository, Notifier notifier) {
    this.repository = Objects.requireNonNull(repository);
    this.notifier = Objects.requireNonNull(notifier);
}
~~~

Đoạn này trích từ file chạy đầy đủ. Cách làm giúp viết unit test với fake, đồng thời tránh **Service Locator**, tức giấu các phụ thuộc bằng cách cho mọi class tự giữ container rồi tra bean lúc sử dụng.

Spring tạo bean bằng `@Bean` factory method và giải quyết tham số bằng type, sau đó gọi constructor `OrderService`. **Java vẫn dùng `new` bên trong configuration**; điều được tách là quyết định tạo các collaborator ra khỏi nghiệp vụ.

Không cần `@Autowired` trên tham số `@Bean` trong cấu hình này. Cũng không cần `@ComponentScan` vì cả ba bean đã được khai báo tường minh.

## 6. Tra bean khi có nhiều ứng viên hoặc không có ứng viên

**Không tìm thấy:** nếu bỏ `@Bean orderService` và không có component registration khác, `getBean(OrderService.class)` có thể ném `NoSuchBeanDefinitionException`. Nếu thiếu một dependency của service, lỗi còn có thể xảy ra khi khởi động context vì singleton không lazy được tạo sớm.

**Nhiều ứng viên:** giả sử có hai bean implement `Notifier`. Khi `OrderService` nhận `Notifier` qua constructor, Spring có thể không xác định được nên chọn bean nào. Cần quy tắc rõ bằng `@Qualifier`, `@Primary`, hoặc cấu hình ứng viên thích hợp.

Ví dụ **minh họa, không thuộc file chạy mục 4**:

~~~java
@Bean("consoleNotifier")
Notifier consoleNotifier() {
    return new ConsoleNotifier();
}

@Bean("otherNotifier")
Notifier otherNotifier() {
    return new OtherNotifier();
}
~~~

`OtherNotifier` là tên minh họa chưa định nghĩa. Hai bean cùng interface có thể gây `NoUniqueBeanDefinitionException`. Lookup theo tên và kiểu giải quyết lựa chọn chủ động:

~~~java
Notifier chosen = context.getBean("consoleNotifier", Notifier.class);
~~~

Đừng dựa vào “bean đăng ký trước sẽ được chọn”.

**Scope:** mặc định bean singleton là một instance theo bean definition **trong một context**. Prototype thường có instance mới khi yêu cầu. Việc prototype được inject một lần vào singleton không khiến dependency tự đổi ở mọi method call.

**Proxy:** nếu sau này bật AOP hoặc `@Transactional`, bean lấy từ Spring có thể là proxy. Khi dùng JDK dynamic proxy, lookup theo interface thường phù hợp hơn concrete implementation; class-based proxy chịu giới hạn như `final` method/class. Demo này không bật AOP.

## 7. Test use case độc lập với Spring

Constructor injection cho phép tạo service bằng Java thuần, ví dụ:

~~~java
java.util.List<String> sent = new java.util.ArrayList<>();

FirstBeanFlow.OrderRepository fakeRepository =
        new FirstBeanFlow.OrderRepository() {
            public boolean save(FirstBeanFlow.OrderRequest r) {
                return true;
            }
            public boolean contains(String id) {
                return false;
            }
        };

FirstBeanFlow.Notifier fakeNotifier = sent::add;

FirstBeanFlow.OrderService service =
        new FirstBeanFlow.OrderService(fakeRepository, fakeNotifier);

String result = service.place(
        new FirstBeanFlow.OrderRequest("T-1", "PEN", 1));

if (!"ACCEPTED T-1".equals(result)
        || !sent.equals(java.util.List.of("T-1"))) {
    throw new AssertionError("Unexpected call sequence");
}
~~~

Đoạn này minh họa viết **test trong cùng project**; không phải file độc lập với `main` và không tạo thêm dòng vào stdout ở mục 4. Để test nhánh duplicate, fake repository phải trả `false` khi mã đã tồn tại và assert notifier **không** được gọi thêm.

Nên tách: unit test kiểm tra logic service bằng fake; integration test khởi động context để xác nhận wiring; test database hoặc message broker thật cho phần hạ tầng.

## 8. Xử lý lỗi và sai lầm thường gặp

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| `getBean` tưởng là `new` | Bean phải được đăng ký/quản lý; lookup không tự khởi tạo class bất kỳ |
| `getBean` xong không có kết quả nghiệp vụ | Phải gọi method trên service |
| `NoSuchBeanDefinitionException` | Sai context, thiếu bean definition, profile/scanning sai |
| `NoUniqueBeanDefinitionException` | Có nhiều ứng viên; cần xác định bean rõ |
| `UnsatisfiedDependencyException` | Dependency của bean không giải quyết được |
| `BeanCreationException` | Factory/constructor/init ném lỗi |
| Bean được `new` bên ngoài và mong hưởng AOP/transaction | Instance ngoài container không tự được proxy |
| Nhầm tên bean với class name | Tên mặc định `@Bean` thường là tên phương thức |
| Cho rằng singleton là thread-safe | Scope không bảo đảm tính đồng thời của mutable Map |
| Repository lưu xong nhưng notifier lỗi | Không có rollback tự động; cần chiến lược consistency |
| Lạm dụng `context.getBean` trong mọi service | Dependency bị ẩn; ưu tiên constructor injection |

Không nên dùng exception do `getBean` để âm thầm tạo một service thủ công thay thế mà không xem xét mục tiêu quản lý bean và lifecycle.

## 9. Bài tập tự luyện

**1.** Nếu chỉ lấy `OrderService` nhưng chưa gọi `place` thì có đơn nào được lưu bởi use case không?

**Đáp án:** Không. Bean có thể được tạo trước, nhưng các thao tác `save` được viết bên trong `place`.

**2.** Vì sao có hai dòng trả kết quả nhưng chỉ một dòng `NOTIFY O-101`?

**Đáp án:** Lần đầu lưu thành công và thông báo. Lần hai id trùng, `save` trả false, service trả `ALREADY_EXISTS` ngay.

**3.** Hai lần `getBean(OrderService.class)` có luôn trả cùng reference?

**Đáp án:** Chỉ trong cấu hình singleton tương ứng của ví dụ này. Prototype có thể trả instance khác.

**4.** Mã gọi `context.getBean("orderService", OrderService.class)` có phù hợp không?

**Đáp án:** Có, vì factory method trong `AppConfig` mang tên `orderService`, trừ khi đổi cấu hình bean name.

**5.** Nếu có hai bean `Notifier` thì sửa gì?

**Đáp án:** Chỉ rõ cách chọn bằng `@Qualifier`, `@Primary` hoặc cấu hình phù hợp; tránh chọn tùy thứ tự.

**6.** Có cần Spring context để unit test `OrderService` không?

**Đáp án:** Không. Các dependency được inject qua constructor nên test có thể dùng fake thuần Java.

## 10. Checklist cuối bài

- [ ] Đã có JDK 17+, Maven và `spring-context`.
- [ ] File đặt đúng `src/main/java/demo/FirstBeanFlow.java` với package `demo`.
- [ ] `@Configuration` chứa đúng ba bean liên quan.
- [ ] Context khởi tạo được, dependency không mơ hồ.
- [ ] Lấy service bằng `getBean(OrderService.class)`.
- [ ] Gọi `service.place(request)` sau lookup.
- [ ] Hiểu thứ tự `save → notify → return` và nhánh duplicate.
- [ ] Phân biệt output của ứng dụng với log Maven.
- [ ] Đóng context khi không sử dụng nữa.
- [ ] Không suy ra `Map` là database hay Core Container tự tạo giao dịch.
- [ ] Kiểm thử nghiệp vụ bằng fake và kiểm thử wiring bằng Spring context khi cần.

**Kết luận:** `getBean(OrderService.class)` đưa mã khởi động tới entry point của **object graph đã được Spring lắp ráp**. Phần tạo và inject dependency do container tổ chức; `OrderService` thực hiện quy tắc nghiệp vụ và phối hợp repository/notifier. Phân biệt đúng các vai trò đó là bước cốt lõi của ứng dụng Spring đầu tiên.