# Ý nghĩa @Service, @Repository và @Controller trong Spring Core Container

## 1. Mục tiêu và bối cảnh

Khi viết ứng dụng Spring Framework, chúng ta thường chia code thành các lớp xử lý HTTP, nghiệp vụ và truy cập dữ liệu. Ba annotation `@Controller`, `@Service`, `@Repository` giúp mô tả những vai trò ấy trong mã nguồn và cho phép Spring phát hiện lớp khi **quét thành phần (component scanning)**.

Sau bài học, bạn có thể:

- Giải thích vì sao cả ba annotation đều tạo **ứng viên bean** thông qua cơ chế `@Component`.
- Phân biệt **vai trò kiến trúc** và **hành vi runtime** của từng stereotype, tránh suy diễn rằng annotation tự tạo endpoint, transaction hoặc kết nối cơ sở dữ liệu.
- Mô tả quá trình `@ComponentScan` tìm lớp, đăng ký bean definition, khởi tạo bean và thực hiện dependency injection.
- Viết một ví dụ Spring Framework thuần Java có `@Repository`, `@Service`, `@Controller` được tìm thấy và tiêm đúng vào nhau.
- Phân tích điều kiện **dịch ngoại lệ persistence** của `@Repository` và điều kiện **định tuyến HTTP** của `@Controller`.
- Sử dụng tên bean, qualifier, scope và phạm vi scan đúng chỗ; xử lý các lỗi cấu hình thực tế.

Bài học tập trung vào **Spring Core Container và component scan**. Những ví dụ Spring MVC, dữ liệu và transaction được sử dụng để giải thích vai trò của stereotype, không thay thế cho khóa học chuyên sâu về web hoặc data access.

## 2. Stereotype là gì?

**Stereotype** là annotation phân loại vai trò một lớp trong ứng dụng. Spring cung cấp stereotype tổng quát `@Component` và các stereotype chuyên biệt:

- `@Controller`: lớp chịu trách nhiệm tại ranh giới tiếp nhận yêu cầu/presentation, thường là web controller.
- `@Service`: lớp thể hiện một dịch vụ xử lý nghiệp vụ hoặc điều phối use case.
- `@Repository`: lớp chịu trách nhiệm với thao tác lưu trữ, truy xuất và tìm kiếm dữ liệu (repository/DAO).

Điểm chung về khả năng được Spring quản lý là **cả ba đều được meta-annotate bằng `@Component`**.

```java
// Sơ đồ ý tưởng quan hệ annotation; không phải định nghĩa đầy đủ của Spring.
@Component
public @interface Service {}

@Component
public @interface Repository {}

@Component
public @interface Controller {}
```

Cú pháp ở trên chỉ minh họa ý tưởng về meta-annotation; định nghĩa thật còn có `@Target`, `@Retention`, `@Documented` và các thuộc tính khác. **Không copy đoạn phác họa này để thay thế annotation thật.**

Khi bật component scanning cho package phù hợp, Spring nhận diện các lớp đánh dấu `@Component` hoặc stereotype meta-annotated bởi `@Component`, rồi đăng ký bean definition cho chúng.

```text
Classpath có các class đã biên dịch
             |
             v
       @ComponentScan
             |
             +--> @Controller --> bean definition --> controller bean
             |
             +--> @Service ----> bean definition --> service bean
             |
             +--> @Repository -> bean definition --> repository bean
             |
             v
     IoC Container quản lý lifecycle, dependency, scope
```

Một annotation đánh dấu lớp làm ứng viên; việc bean có thực sự xuất hiện hay không còn tùy **phạm vi scan**, các bộ lọc, conditional configuration, xung đột tên và sự thành công của quá trình tạo bean. Không phải mọi class trên classpath đều tự động trở thành bean.

## 3. So sánh nhanh ba annotation

| Khía cạnh | `@Controller` | `@Service` | `@Repository` |
| --- | --- | --- | --- |
| Ý nghĩa chính | Presentation / đầu vào web | Nghiệp vụ, use case, orchestration | Truy cập và lưu trữ dữ liệu |
| Đều là specialization của | `@Component` | `@Component` | `@Component` |
| Được tìm qua component scan | Có | Có | Có |
| Có thể dùng constructor injection | Có | Có | Có |
| Scope mặc định | Singleton | Singleton | Singleton |
| Tự mở HTTP endpoint chỉ vì có annotation? | **Không** | Không | Không |
| Tự bắt đầu transaction? | Không | **Không** | Không |
| Dấu hiệu được hỗ trợ để dịch persistence exception | Không phải mục đích chính | Không phải mục đích chính | **Có, khi cấu hình hạ tầng dịch ngoại lệ tương ứng** |
| Thường được lớp nào gọi? | Dispatcher/handler hoặc caller khác | Controller, service khác, listener | Service hoặc thành phần nghiệp vụ khác |
| Lợi ích ngoài tạo bean | Nhận diện web component, tích hợp web infrastructure | Diễn đạt ý định kiến trúc, điểm cắt AOP | Diễn đạt lớp persistence, điểm cắt AOP, hỗ trợ exception translation |

**Kết luận quan trọng:** ba annotation giúp Spring **nhận diện, đăng ký và phân loại bean**, nhưng không hình thành ba loại IoC Container khác nhau. Cùng một container vẫn quản lý chúng theo cơ chế bean definition, dependency injection và scope.

## 4. Cơ chế component scanning phía sau

Ba stereotype đều đi qua **cùng một** đường quét class của Spring:

```java
@Configuration
@ComponentScan(basePackages = "com.example.catalog")
class CatalogConfig { }
```

Sau khi `CatalogConfig` được đăng ký vào context, Spring xét các class trong `com.example.catalog` và các package con. Bộ lọc mặc định nhận `@Controller`, `@Service` và `@Repository` vì chúng có meta-annotation `@Component`. Với ứng viên hợp lệ, scanner tạo bean definition; container sau đó tạo instance và resolve dependency theo scope/lifecycle. Một class mang stereotype nhưng nằm ngoài root, bị condition/filter loại hoặc thiếu dependency vẫn có thể vắng mặt/thất bại.

`basePackageClasses = CatalogPackage.class` cũng cấu hình vùng quét, thông qua **package chứa class marker** thay vì chỉ quét marker. Phần đáng chú ý ở ba stereotype không phải các thuật toán quét khác nhau, mà là **trách nhiệm từng layer và hạ tầng chuyên biệt có thể diễn giải metadata ấy**.

## 5. @Service: đánh dấu lớp nghiệp vụ

### 5.1. Ý nghĩa

`@Service` là một specialization của `@Component`, thích hợp để thể hiện **service layer**: các hành động nghiệp vụ, use case, quy tắc domain hoặc việc điều phối nhiều cộng tác viên.

Một service có thể:

- Kiểm tra và áp dụng quy tắc nghiệp vụ.
- Điều phối nhiều repository, domain service hoặc cổng tích hợp.
- Tạo kết quả use case phục vụ controller, listener hoặc scheduled job.
- Là điểm đặt các chính sách cross-cutting thông qua annotation/aspect khác nếu được cấu hình.

Ví dụ cấu trúc:

```java
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final StockRepository stock;
    private final PaymentGateway payments;

    public CheckoutService(StockRepository stock, PaymentGateway payments) {
        this.stock = stock;
        this.payments = payments;
    }

    public Receipt checkout(Cart cart) {
        stock.reserve(cart);
        return payments.charge(cart);
    }
}
```

`StockRepository`, `PaymentGateway`, `Receipt`, `Cart` là các kiểu nghiệp vụ minh họa; đoạn này không phải chương trình độc lập. `@Service` làm cho lớp trở thành ứng viên bean khi được scan; những phụ thuộc vẫn cần bean tương ứng để inject.

### 5.2. @Service không tự tạo transaction, retry hoặc caching

Những kỳ vọng dưới đây **không đúng chỉ từ `@Service`**:

- Mỗi lời gọi method tự nằm trong transaction.
- Spring tự retry khi service ném lỗi.
- Giá trị trả về tự được cache.
- Method tự chạy bất đồng bộ.
- Mọi lần gọi method được AOP chặn để ghi log.

Các khả năng đó cần hạ tầng/annotation/cấu hình riêng, ví dụ `@Transactional` kết hợp transaction management, `@Cacheable` với caching infrastructure hoặc `@Async` với async execution. Việc đặt các annotation này trên service phải đáp ứng yêu cầu của cơ chế proxy, method invocation và hạ tầng tương ứng.

Ví dụ **không phải chương trình độc lập**:

```java
@Service
public class TransferService {
    @org.springframework.transaction.annotation.Transactional
    public void transfer(long fromId, long toId, long amount) {
        // Cần DAO, transaction manager và logic nghiệp vụ thực tế.
    }
}
```

`@Transactional` biểu đạt giao dịch nếu hạ tầng Spring transaction được kích hoạt đúng, không phải đặc quyền tự nhiên của `@Service`. Thậm chí không có `@Service`, một bean `@Component` hoặc `@Bean` vẫn có thể tham gia transaction khi được cấu hình tương ứng.

### 5.3. Vì sao không dùng @Component cho tất cả?

Cơ chế quét và dependency injection có thể vẫn hoạt động, nhưng `@Service` làm trách nhiệm code dễ hiểu, thuận tiện cho phân tích kiến trúc, tooling và pointcut AOP nhắm đến tầng service. Spring cũng có thể hỗ trợ thêm semantics dành cho các stereotype trong các phiên bản tương lai.

Dùng `@Service` khi class thực sự chịu trách nhiệm nghiệp vụ; đừng gắn lên data adapter hoặc request controller chỉ vì muốn Spring inject nó.

## 6. @Repository: đánh dấu lớp persistence / truy cập dữ liệu

### 6.1. Ý nghĩa

`@Repository` dành cho một thành phần phụ trách **lưu trữ, truy vấn, tìm kiếm và truy xuất dữ liệu**. Nhiều đội dùng nó cho DAO; trong Domain-Driven Design, repository thường biểu diễn một tập hợp đối tượng domain và che chi tiết persistence khỏi tầng nghiệp vụ.

```java
import org.springframework.stereotype.Repository;

@Repository
public class JdbcCustomerRepository {
    private final org.springframework.jdbc.core.JdbcTemplate jdbc;

    public JdbcCustomerRepository(
            org.springframework.jdbc.core.JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String findName(long id) {
        return jdbc.queryForObject(
            "select name from customer where id = ?",
            String.class,
            id
        );
    }
}
```

Đây là ví dụ DAO minh họa cần dependency `spring-jdbc`, `JdbcTemplate` đã cấu hình, `DataSource` và bảng `customer` trong DB thực tế; không phải chương trình chạy độc lập. `@Repository` cho phép component scan phát hiện class và cho biết nó thuộc lớp truy cập dữ liệu.

### 6.2. Exception translation: điểm khác đáng nhớ

Một vai trò đặc biệt của `@Repository` là **đánh dấu repository đủ điều kiện** cho cơ chế chuyển đổi persistence exception sang hệ ngoại lệ truy cập dữ liệu thống nhất của Spring, tiêu biểu là `org.springframework.dao.DataAccessException` và các subclass.

Ví dụ vendor persistence API có thể phát sinh ngoại lệ phụ thuộc công nghệ. Hệ thống dịch ngoại lệ cho phép tầng gọi phía trên xử lý theo các nhóm lỗi trung lập hơn như dữ liệu không tìm thấy, vi phạm toàn vẹn, khóa tranh chấp, v.v. Cách ánh xạ cụ thể do translator tương ứng quyết định.

Nhưng cần nhớ rõ **điều kiện**:

1. Bean repository có stereotype phù hợp, như `@Repository`.
2. Hạ tầng dịch ngoại lệ, tiêu biểu `PersistenceExceptionTranslationPostProcessor`, được đăng ký.
3. Có `PersistenceExceptionTranslator` phù hợp với công nghệ persistence để chuyển loại exception cần xử lý.
4. Lời gọi thực sự đi qua proxy/interceptor (khi cơ chế triển khai dùng proxy) và loại exception đó được translator hỗ trợ.

```text
Caller
  |
  v
Repository proxy / interceptor
  |
  v
@Repository target -> persistence API -> vendor exception
  |
  v
PersistenceExceptionTranslator phù hợp
  |
  +--> DataAccessException (nếu dịch được)
  |
  +--> exception gốc (nếu không có bản dịch phù hợp)
```

Ví dụ đăng ký cơ chế post-processing trong cấu hình phù hợp:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.annotation.PersistenceExceptionTranslationPostProcessor;

@Configuration
class DataAccessConfig {
    @Bean
    static PersistenceExceptionTranslationPostProcessor
            persistenceExceptionTranslationPostProcessor() {
        return new PersistenceExceptionTranslationPostProcessor();
    }
}
```

Ví dụ này cần `spring-tx` trên classpath và một translator thích hợp từ stack data-access; riêng class cấu hình **không bảo đảm dịch được mọi exception**. Việc khai báo `static @Bean` cho một `BeanPostProcessor` giúp đăng ký sớm trong vòng đời container. Nếu framework/data starter đã cấu hình translation, không đăng ký dư thừa mà không kiểm tra.

**Phân biệt thêm:**

- `JdbcTemplate` đã có cơ chế chuyển đổi nhiều loại `SQLException` sang `DataAccessException` từ thao tác của chính nó. Kết quả đó **không phải vì** người dùng đặt `@Repository` trên class DAO.
- `@Repository` không tự tạo `DataSource`, `EntityManager`, `JdbcTemplate`, schema hay connection pool.
- Một class `@Repository` không trở thành Spring Data repository tự động sinh truy vấn chỉ nhờ annotation. Spring Data repository interface và proxy factory của Spring Data là **cơ chế khác**.
- Không nên giả định mọi `RuntimeException` hay mọi lỗi SQL đều được dịch; chính hạ tầng và translator quyết định.

### 6.3. Ranh giới giữa repository và service

Thông thường repository định nghĩa thao tác như `findById`, `save` hoặc truy vấn phù hợp với nhu cầu nghiệp vụ; service kết hợp những thao tác ấy để giải quyết use case. Repository không nên nắm logic HTTP, response headers hay trực tiếp quyết định status code.

Ví dụ liên kết:

```text
OrderService.placeOrder()
    |
    +-- inventoryRepository.checkStock()
    +-- orderRepository.save()
    +-- paymentGateway.authorize()
    |
    +-- trả kết quả nghiệp vụ
```

Các method ở đây là hình minh họa quan hệ cộng tác, không phải API cụ thể có sẵn trong Spring.

## 7. @Controller: đánh dấu lớp presentation/web

### 7.1. Ý nghĩa trong Core Container

`@Controller` cũng là stereotype của `@Component`. Khi được scan, controller được đăng ký làm Spring bean, tham gia injection và lifecycle như các bean khác.

```java
import org.springframework.stereotype.Controller;

@Controller
public class CatalogController {
    private final CatalogService service;

    public CatalogController(CatalogService service) {
        this.service = service;
    }

    public String lookup(int id) {
        return service.findTitle(id);
    }
}
```

`CatalogService` là kiểu nghiệp vụ minh họa. Trong **ApplicationContext thuần**, method `lookup` chỉ là method Java. Đặt `@Controller` không tự tạo HTTP endpoint hay bắt buộc mở server.

### 7.2. Tại sao Spring MVC có thể nhận diện controller?

Trong ứng dụng đã bật hạ tầng Spring MVC, các bean `@Controller` có thể được xem là **handler**. Spring MVC sử dụng các thành phần như `RequestMappingHandlerMapping` và `RequestMappingHandlerAdapter` để tìm request mapping và gọi handler method.

Muốn ánh xạ HTTP, còn cần cấu hình web MVC/`DispatcherServlet` và annotation định tuyến chẳng hạn `@RequestMapping`, `@GetMapping`, `@PostMapping`.

```java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/catalog")
public class CatalogPageController {
    private final CatalogService catalogService;

    public CatalogPageController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable int id, Model model) {
        model.addAttribute("title", catalogService.findTitle(id));
        return "catalog/detail";
    }
}
```

Đây là ví dụ MVC minh họa, **không chạy độc lập** nếu thiếu `CatalogService`, Spring MVC servlet infrastructure và view resolver/template. Với controller MVC trả về `String` như trên, chuỗi `"catalog/detail"` thường được hiểu là **tên view**. Không phải mọi chuỗi trả về từ method trong `@Controller` đều được đưa nguyên văn vào HTTP response body.

### 7.3. @RestController liên hệ thế nào với @Controller?

`@RestController` trong Spring MVC là một annotation tổng hợp mang semantics `@Controller` **và `@ResponseBody`**. Nó thường phù hợp cho API trả dữ liệu vào response body, thay vì một tên view:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/catalog")
public class CatalogApiController {
    private final CatalogService catalogService;

    public CatalogApiController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/{id}")
    public CatalogDto detail(@PathVariable int id) {
        return new CatalogDto(id, catalogService.findTitle(id));
    }

    public record CatalogDto(int id, String title) {}
}
```

Đoạn minh họa cần `CatalogService` và hạ tầng Spring Web MVC. Khi được cấu hình đúng, response body được ghi qua các `HttpMessageConverter` thích hợp. JSON thường được tạo nếu có converter (chẳng hạn Jackson) và negotiation phù hợp. Bản thân `@RestController` **không tự tải thư viện JSON, mở cổng HTTP hay cấu hình server**.

### 7.4. Cẩn thận ranh giới web

Một bean `@Controller` vẫn có thể được tạo trong context chỉ chứa Spring Core, nhưng sẽ **không xử lý HTTP** nếu không có DispatcherServlet hoặc handler infrastructure phù hợp. Ngược lại, chỉ thêm `@RequestMapping` trên một class không được đăng ký vào context cũng không tự khiến ứng dụng nhận được request.

Trong Spring WebFlux, annotated controllers cũng tồn tại, nhưng luồng dispatch/handler thuộc hạ tầng reactive và không nên đánh đồng với MVC Servlet. Câu hỏi về stereotype ở Core Container chỉ yêu cầu hiểu **cách bean được phát hiện** và **vai trò mà hạ tầng web có thể dùng tiếp**.

## 8. Ví dụ chạy được: ba stereotype cùng một Spring ApplicationContext

Để quan sát cơ chế component scan mà không phải dựng HTTP server hay database, ví dụ này dùng **Spring Framework 6.2.19**, **Java 17+**, và Java configuration `AnnotationConfigApplicationContext`.

Ta có ba lớp: repository cung cấp dữ liệu giả lập, service gọi repository, controller gọi service. Tên bean được khai báo rõ để kết quả không phụ thuộc quy tắc đặt tên của **nested class** trong Java.

Cấu trúc dự án:

```text
spring-stereotype-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── StereotypeDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'spring-stereotype-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.StereotypeDemo'
}
```

`spring-context` đủ cho demo Core Container: ba annotation thuộc `org.springframework.stereotype`; không cần dependency MVC, JDBC hoặc Spring Boot chỉ để quan sát bean scanning.

**`src/main/java/demo/StereotypeDemo.java`**

```java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Controller;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;

public class StereotypeDemo {

    @Configuration
    @ComponentScan(basePackageClasses = StereotypeDemo.class)
    public static class Config {
    }

    @Repository("catalogRepository")
    public static class CatalogRepository {
        public String findTitle(int id) {
            return "Product-" + id;
        }
    }

    @Service("catalogService")
    public static class CatalogService {
        private final CatalogRepository repository;

        public CatalogService(CatalogRepository repository) {
            this.repository = repository;
        }

        public String findTitle(int id) {
            return repository.findTitle(id);
        }
    }

    @Controller("catalogController")
    public static class CatalogController {
        private final CatalogService service;

        public CatalogController(CatalogService service) {
            this.service = service;
        }

        public String show(int id) {
            return service.findTitle(id);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("repository-bean="
                    + context.containsBean("catalogRepository"));
            System.out.println("service-bean="
                    + context.containsBean("catalogService"));
            System.out.println("controller-bean="
                    + context.containsBean("catalogController"));

            CatalogController controller =
                    context.getBean(CatalogController.class);
            System.out.println("result=" + controller.show(7));

            CatalogService first = context.getBean(CatalogService.class);
            CatalogService second = context.getBean(CatalogService.class);
            System.out.println("service-singleton=" + (first == second));
        }
    }
}
```

**Chạy** từ thư mục `spring-stereotype-demo` bằng Gradle có JDK 17+:

```bash
gradle run --quiet
```

Nếu dự án đã có Gradle Wrapper, chạy `./gradlew run --quiet` (Linux/macOS) hoặc `gradlew.bat run --quiet` (Windows). Không chạy `javac StereotypeDemo.java` riêng lẻ nếu chưa đưa `spring-context` và dependency transitives lên classpath; Gradle tự xử lý compile và runtime dependencies.

**Các dòng từ chương trình (stdout):**

```text
repository-bean=true
service-bean=true
controller-bean=true
result=Product-7
service-singleton=true
```

**Giải thích:**

1. `@ComponentScan(basePackageClasses = StereotypeDemo.class)` quét package `demo`, nơi các lớp `static` có stereotype của ví dụ được biên dịch.
2. Scanner nhận `CatalogRepository` qua `@Repository`, `CatalogService` qua `@Service`, `CatalogController` qua `@Controller`; các tên bean explicit tương ứng được đăng ký.
3. Spring constructor-inject `CatalogRepository` vào service, rồi service vào controller. Constructor đơn không cần thêm `@Autowired`.
4. `context.containsBean("...")` trả `true` cho cả ba bean, chứng minh chúng cùng hiện diện trong container.
5. Lời gọi Java trực tiếp `controller.show(7)` trả `Product-7`. **Đây không phải HTTP request** và chương trình không dựng Spring MVC.
6. Hai lời gọi `getBean(CatalogService.class)` trả cùng instance, phù hợp singleton scope mặc định.

Ví dụ có thể mở rộng bằng `@Scope("prototype")` trên service để quan sát các lần `getBean` cho instance khác nhau. Tuy vậy, nếu prototype đã được inject vào singleton controller, tham chiếu controller giữ vẫn là đối tượng được giải quyết cho controller tại thời điểm khởi tạo. Đây là quy tắc scope chung, không phụ thuộc việc lớp được đánh dấu `@Service` hay `@Component`.

## 9. Từ một request thực tế đến chuỗi controller → service → repository

Ở ứng dụng Spring Web MVC đã cấu hình đúng, luồng xử lý thường là:

```text
HTTP Client
    |
    v
DispatcherServlet / HandlerMapping
    |
    v
@Controller / @RestController
    |  nhận request, bind/validate dữ liệu và chuyển lời gọi
    v
@Service
    |  thực thi use case, điều phối quy tắc nghiệp vụ
    v
@Repository
    |  truy cập storage thông qua JDBC/JPA/... hoặc adapter riêng
    v
Database / external persistence
```

Chiều trả về là repository → service → controller → HTTP response. Đây là **mẫu tổ chức thường dùng**, không phải chuỗi bắt buộc do container ép cho mọi dự án. Ví dụ có service gọi service khác, controller gọi query service, repository truy cập cache hoặc các lớp domain riêng.

Một ứng dụng không có web vẫn có thể dùng `@Service` và `@Repository`; một ứng dụng không dùng cơ sở dữ liệu vẫn có thể có `@Controller`, và service không nhất thiết phải gọi repository. Spring IoC quản lý bean theo dependency thật, không tự tạo cạnh dependency chỉ vì tên annotation.

**Vai trò thiết kế hợp lý:**

- Controller: chuyển request và biểu diễn kết quả cho client; giữ logic nghiệp vụ chính trong service.
- Service: quyết định nghiệp vụ/use case, có thể ràng buộc giao dịch khi cấu hình.
- Repository: ẩn cơ chế tìm kiếm/truy xuất/lưu dữ liệu khỏi tầng trên.

Việc chia trách nhiệm giúp kiểm thử từng tầng và giảm phụ thuộc trực tiếp từ nghiệp vụ vào framework web hoặc chi tiết persistence.

## 10. Bean naming và injection có khác giữa các stereotype?

`@Controller`, `@Service` và `@Repository` dùng cơ chế bean naming/injection/scope như component thông thường. `@Service class CheckoutService` thường nhận tên `checkoutService`, trừ khi đặt `@Service("checkoutWorkflow")` hoặc dùng `BeanNameGenerator` tùy chỉnh. Class dạng acronym `URLClient` có thể giữ nguyên chữ đầu theo JavaBeans naming; kiểm tra tên thật bằng context thay vì đoán.

Khi constructor cần một interface có nhiều implementations, cần `@Qualifier`, `@Primary` hoặc tập hợp phù hợp. Cả ba stereotype đều mặc định singleton trong một container; không lưu mutable state theo request vào field singleton nếu chưa có thiết kế concurrency/scope đúng. Bean naming là danh tính trong registry, còn annotation stereotype diễn đạt vai trò kiến trúc.

## 11. Phân biệt stereotype với @Bean và @Configuration

Component scanner đăng ký definition từ **class có stereotype**; `@Bean` đăng ký definition từ **factory method** của configuration được Spring xử lý. Class bên ngoài codebase có thể thành bean mà không mang stereotype:

```java
@Configuration(proxyBeanMethods = false)
class IntegrationConfig {
    @Bean
    ExternalClient externalClient() {
        return new ExternalClient("endpoint");
    }
}
```

`ExternalClient` là kiểu giả định trong đoạn minh họa; bean name mặc định ở đây là `externalClient` theo method. Một class được scan rồi còn được `@Bean` tạo lần nữa có thể gây trùng registration hoặc nhiều bean cùng type, tùy tên/cấu hình. Dù từ scanner hay factory method, instance được Spring quản lý vẫn có thể nhận annotation injection và lifecycle khi có processor phù hợp. `@Service` không phải điều kiện bắt buộc để một bean được inject.

## 12. Stereotype, AOP và các cơ chế mở rộng

Stereotype giúp các công cụ và aspect phân loại bean theo trách nhiệm. Ví dụ muốn ghi metric cho các method service, một aspect có thể chọn các lớp gắn `@Service` bằng pointcut phù hợp.

Tuy nhiên, hãy tách ba tầng khái niệm:

1. **Phát hiện bean:** component scanning nhìn thấy stereotype/meta-annotation.
2. **Tạo bean và injection:** IoC Container quản lý object và dependency.
3. **Hành vi bổ sung:** cơ chế khác, như post-processor, Spring MVC hoặc AOP, diễn giải stereotype/method annotation nếu chúng được bật.

`@Service` không trực tiếp sinh proxy; `@Repository` không bảo đảm một proxy dịch ngoại lệ nếu thiếu post-processor/translator; `@Controller` không tự thiết lập DispatcherServlet.

### Tại sao phân biệt ba tầng này quan trọng?

Giả sử một ứng dụng chạy được `context.getBean(MyController.class)` nhưng đường dẫn HTTP trả 404. Điều đó chứng minh có bean trong context nhưng **không chứng minh** Spring MVC đã quét mapping, có handler hoặc đường dẫn khớp.

Ngược lại, một repository được inject thành công nhưng exception vendor không đổi thành `DataAccessException` có thể do thiếu translator, post-processor hoặc lời gọi không qua proxy. Việc bean có trong context và việc behavior tích hợp hoạt động là **hai phép kiểm tra khác nhau**.

## 13. Lỗi thường gặp và cách chẩn đoán

### Lỗi 1 — Đặt @Service rồi tưởng Spring tự tìm dù ngoài package scan

**Triệu chứng:** `NoSuchBeanDefinitionException` hoặc `UnsatisfiedDependencyException` khi inject service.

Kiểm tra package chứa class, `@ComponentScan(basePackages=...)`, lớp cấu hình đang được load và các include/exclude filters. Đừng sửa bằng cách tùy tiện mở rộng scan đến toàn bộ classpath; nên chọn package gốc nhất quán.

### Lỗi 2 — Đặt @Controller rồi chờ HTTP endpoint xuất hiện

**Triệu chứng:** Bean tồn tại nhưng HTTP route không có.

Kiểm tra đây có phải ứng dụng Spring MVC/WebFlux đang chạy đúng hạ tầng hay không, có `@RequestMapping`/`@GetMapping` tương ứng, có servlet/reactive handler mapping, context chứa bean đúng và path/method có khớp request không. `@Controller` trong `AnnotationConfigApplicationContext` thuần chỉ là managed bean.

### Lỗi 3 — Đánh dấu @Repository là mọi SQLException sẽ được dịch

**Triệu chứng:** Caller vẫn thấy exception gốc hoặc không có hạ tầng translation.

Kiểm tra data-access library có cơ chế dịch riêng không; nếu dùng `PersistenceExceptionTranslationPostProcessor` thì bảo đảm post-processor và `PersistenceExceptionTranslator` phù hợp đã đăng ký và lời gọi qua bean/proxy. Không bắt mọi exception rồi tự đổi thành `DataAccessException` mà bỏ mất nguyên nhân lỗi.

### Lỗi 4 — Nhầm @Service với @Transactional

**Triệu chứng:** Operation service không rollback dù class có `@Service`.

Spring chỉ dùng transaction khi được cấu hình đúng (`@Transactional`, transaction manager, interceptor/proxy phù hợp, v.v.). Kiểm tra transaction boundary, phương thức được gọi qua Spring proxy và những giới hạn như self-invocation với proxy mode mặc định. Không thêm `@Service` lần nữa để giải quyết.

### Lỗi 5 — Có hai bean cùng interface, không xác định được candidate

**Triệu chứng:** `NoUniqueBeanDefinitionException`.

Đặt qualifier rõ ràng cho injection point hoặc dùng `@Primary` khi một implementation thật sự là mặc định; trong trường hợp nghiệp vụ cần tất cả implementations, inject collection `List<T>`. Không đổi hết `@Repository` thành `@Component` vì việc đó không giải quyết xung đột theo type.

### Lỗi 6 — Hai class khác package nhưng sinh cùng bean name

**Triệu chứng:** lỗi xung đột bean definition/name trong quá trình scan.

Ví dụ `catalog.CustomerService` và `billing.CustomerService` có thể cùng sinh tên mặc định `customerService`. Dùng tên explicit, bean name generator phù hợp hoặc điều chỉnh ranh giới scan nếu thực sự có hai bean độc lập.

### Lỗi 7 — Nghĩ @Controller mặc định trả JSON

`@Controller` trả một `String` trong Spring MVC có thể biểu đạt tên view. Để trả response body, dùng `@ResponseBody` trên method/type hoặc `@RestController` khi muốn mọi handler method theo mô hình ấy; cần message converter tương ứng để serialize đối tượng.

### Lỗi 8 — Viết annotation trên class rồi tự tạo đối tượng bằng new

```java
CatalogService service = new CatalogService(new CatalogRepository());
```

Đây là Java object được tạo thủ công, **không tự tham gia** container injection, lifecycle, proxy hoặc BeanPostProcessor chỉ vì class mang `@Service`/`@Repository`. Muốn sử dụng managed bean, nhận nó qua dependency injection hoặc `context.getBean(...)` trong mã hạ tầng/test.

### Lỗi 9 — Đưa business state của từng request vào singleton service/controller

Các stereotype đều là singleton mặc định. Không lưu mutable data của request/caller vào field singleton nếu có nhiều request đồng thời. Đưa trạng thái vào biến cục bộ, tham số hoặc bean đúng scope và thiết kế đồng bộ hóa khi cần.

### Lỗi 10 — Thấy annotation là cho rằng kiến trúc đã được thực thi

Stereotype giúp người đọc và tooling hiểu role, nhưng Spring không mặc định kiểm tra rằng controller không gọi trực tiếp SQL hay repository không xây HTTP response. Duy trì ranh giới kiến trúc bằng thiết kế package, code review, test kiến trúc và các quy tắc dự án.

## 14. Kiểm thử và quan sát thực tế

### 14.1. Test sự hiện diện của bean

Đối với container thuần:

```java
try (AnnotationConfigApplicationContext ctx =
        new AnnotationConfigApplicationContext(Config.class)) {
    assert ctx.containsBean("catalogRepository");
    assert ctx.containsBean("catalogService");
    assert ctx.containsBean("catalogController");
}
```

Đây là snippet dựa trên `Config` của `StereotypeDemo`; khi dùng ở file khác cần khai báo/import đúng tên class và bật assertion `-ea`, hoặc dùng JUnit assertions. Để test độc lập và thông báo lỗi rõ, `assertTrue` của JUnit thường phù hợp hơn Java `assert`.

### 14.2. Test luồng constructor injection

Ví dụ đầy đủ ở mục 8 cho phép quan sát `CatalogController` gọi `CatalogService` và `CatalogRepository` mà không khởi tạo thủ công từng collaborator trong `main`. Trong bài kiểm thử, thay repository bằng fake/test bean khi muốn cô lập nghiệp vụ khỏi dữ liệu thật.

### 14.3. Test riêng hành vi web và persistence

- Để xác thực HTTP mapping, chạy integration test trong **web application context** có MVC/WebFlux infrastructure; với MVC có thể dùng `MockMvc`. Kiểm tra path, HTTP method, response body, status và validation.
- Để xác thực exception translation, tạo test với persistence technology và translator/post-processor đúng, gọi qua Spring-managed repository bean, rồi assert ngoại lệ đầu ra phù hợp.
- Để xác thực transaction của service, dùng test có transaction manager và tài nguyên transactional thật hoặc integration fixture phù hợp; chỉ test bean scanning sẽ không chứng minh commit/rollback.

Một phép thử `containsBean` chứng minh đăng ký bean, **không chứng minh** một HTTP endpoint chạy hay persistence exception đã được dịch.

## 15. Checklist thiết kế

Trước khi đánh dấu một class:

1. Class này chịu trách nhiệm chính là **presentation, nghiệp vụ hay data access**? Chọn `@Controller`, `@Service` hoặc `@Repository` tương ứng; nếu không thuộc nhóm ấy, `@Component` tổng quát có thể phù hợp hơn.
2. Package của class có nằm trong phạm vi `@ComponentScan` không? Có filter hoặc condition làm loại bean không?
3. Dependency được inject qua constructor và có một bean hợp lệ cho mỗi tham số chưa? Nếu nhiều candidate, đã dùng qualifier/primary đúng chưa?
4. Bean có state mutable không? Scope mặc định singleton có phù hợp tính đồng thời và vòng đời không?
5. Nếu dùng `@Repository` để kỳ vọng exception translation, đã có infrastructure và translator cần thiết chưa?
6. Nếu dùng `@Controller` để xử lý HTTP, ứng dụng đã bật đúng web stack, handler mapping và route annotations chưa?
7. Nếu dùng `@Service` với transaction/cache/async, từng tính năng đó đã được bật, cấu hình và kiểm thử riêng chưa?

## 16. Câu hỏi ôn tập và đáp án

**Câu 1.** Tại sao Spring có thể scan cùng lúc `@Service`, `@Repository` và `@Controller`?

**Đáp:** Vì chúng là các stereotype chuyên biệt, meta-annotated bằng `@Component`. Bộ lọc mặc định của component scanner tìm các lớp phù hợp trong package được cấu hình.

**Câu 2.** Nếu `@Controller` được phát hiện trong một `AnnotationConfigApplicationContext` thuần thì đã có HTTP endpoint chưa?

**Đáp:** Chưa. Bean tồn tại trong IoC Container; cần hạ tầng web và mapping cho HTTP request. Method có thể được gọi như method Java bình thường.

**Câu 3.** `@Service` có tự áp transaction khi gọi method không?

**Đáp:** Không. Transaction là cơ chế khác cần annotation/hạ tầng thích hợp, chẳng hạn `@Transactional` và transaction manager. Stereotype service chỉ diễn đạt vai trò và hỗ trợ được scan.

**Câu 4.** `@Repository` có dịch mọi exception thành `DataAccessException` không?

**Đáp:** Không. Nó là marker cho việc dịch persistence exception khi post-processor, translator và lời gọi qua cơ chế phù hợp đã được thiết lập. Chỉ những exception được translator hỗ trợ mới được chuyển đổi.

**Câu 5.** Khi hai class ở hai package cùng tên `CustomerService` được scan, điều gì có thể xảy ra?

**Đáp:** Tên bean mặc định có thể trùng. Có thể giải quyết bằng tên explicit, bean name generator phù hợp hoặc tổ chức phạm vi scan hợp lý. Việc cả hai dùng `@Service` không tự phân biệt tên.

**Câu 6.** Một class có thể trở thành Spring bean mà không có stereotype không?

**Đáp:** Có. Ví dụ method `@Bean` trong `@Configuration` trả về đối tượng tương ứng. Component scanning chỉ là một trong các cơ chế đăng ký bean.

**Câu 7.** Vì sao không nên chỉ dựa vào `containsBean("catalogController")` để khẳng định GET `/catalog/7` hoạt động?

**Đáp:** Vì phép kiểm tra chỉ xác nhận bean đã đăng ký; route hoạt động đòi hỏi context web, handler mapping, mapping annotation, request method/path và các thành phần MVC tương ứng.

**Câu 8.** Spring có bắt buộc controller gọi service, rồi service gọi repository không?

**Đáp:** Không. Đây là mô hình phân tầng thường dùng để quản lý trách nhiệm và dependency, không phải luật runtime của IoC Container.

## 17. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): `@Component`, các stereotype, meta-annotation, bean naming và scope scan.
- [Spring Framework 6.2 — DAO Support](https://docs.spring.io/spring-framework/reference/6.2/data-access/dao.html): repository, Spring `DataAccessException` và exception translation.
- [Spring Framework 6.2 — Spring MVC Annotated Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann.html): `@Controller` trong MVC và điều kiện ứng dụng web.
- [Spring Framework 6.2 — Mapping Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html): các mapping annotation và điều kiện match request.
- [Spring Framework 6.2 — Spring Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans.html): định nghĩa bean, quản lý dependency, phạm vi trách nhiệm IoC Container.
- [Spring Framework 6.2 API — Repository](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/stereotype/Repository.html): hợp đồng stereotype và điều kiện liên quan `PersistenceExceptionTranslationPostProcessor`.

**Ghi nhớ:** `@Service`, `@Repository` và `@Controller` trước hết xác định **vai trò class** để Spring Core Container phát hiện và quản lý bean. `@Repository` có điểm tích hợp exception translation trong hạ tầng persistence thích hợp; `@Controller` được web framework dùng để nhận diện handler. Những tính năng như HTTP routing, transaction và SQL processing vẫn cần các thành phần của chúng được cấu hình rõ ràng.
