# Ranh giới trách nhiệm của container và mã nghiệp vụ

Một trong những điều dễ gây hiểu nhầm khi mới học Spring Boot là: **Spring tạo và kết nối các đối tượng cho chúng ta, vậy Spring có chịu trách nhiệm cả cách ứng dụng xử lý nghiệp vụ không?** Câu trả lời là không. Container giúp ứng dụng có những thành phần cần thiết để hoạt động; người phát triển vẫn phải xác định **ứng dụng cần làm gì**, các quy tắc nào phải được tuân thủ và dữ liệu phải thay đổi ra sao.

Trong một chương trình Java nhỏ, bạn có thể tự viết **new**, truyền dependency vào constructor rồi gọi phương thức. Khi chương trình lớn, các đối tượng có nhiều quan hệ phụ thuộc: controller dùng service, service dùng repository, repository dùng datasource, và nhiều thành phần lại dùng cấu hình chung. **Spring IoC container** đảm nhiệm việc quản lý và lắp ráp các thành phần được đăng ký với nó.

Bài này tập trung vào ranh giới giữa **hạ tầng quản lý đối tượng của container** và **mã nghiệp vụ do ứng dụng sở hữu**. Hiểu ranh giới này sẽ giúp bạn dùng dependency injection, bean lifecycle, scope, configuration và các tính năng Spring đúng mục đích.

## 1. IoC container giải quyết vấn đề gì?

**IoC (Inversion of Control)** là cách chuyển quyền điều khiển một số hoạt động của chương trình sang một thành phần hoặc framework khác. Trong Spring, ví dụ gần gũi nhất là **khởi tạo, quản lý và cung cấp dependency cho các đối tượng**.

Hãy xem cách viết Java thủ công:

~~~java
public class Main {

    public static void main(String[] args) {
        ProductRepository repository = new ProductRepository();
        ProductService service = new ProductService(repository);
        ProductController controller = new ProductController(service);

        // Chương trình tự quyết định tạo và nối từng object.
    }
}
~~~

Ở đây, mã trong **main()** sở hữu cách tạo từng object và thứ tự kết nối chúng. Khi số lượng component tăng, việc lắp ráp thủ công dễ trở thành một chuỗi constructor dài, khó thay đổi cấu hình và khó quản lý vòng đời tài nguyên.

Với Spring, các thành phần có thể được khai báo thành **bean**. Container đọc thông tin cấu hình, tạo những object cần quản lý và kết nối chúng:

~~~java
@Repository
public class ProductRepository {
    // Thành phần truy cập dữ liệu.
}

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }
}

@RestController
public class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }
}
~~~

Ví dụ trên minh họa ba class độc lập; trong project thực tế, mỗi public class nên có file tương ứng, các package/import cần được khai báo và class khởi động cần nằm ở phạm vi component scan phù hợp.

Khi ứng dụng khởi động, Spring có thể:

1. Tìm các class được đánh dấu bằng annotation phù hợp như **@Repository**, **@Service** và **@RestController**.
2. Đăng ký bean definition cho những component đó.
3. Tạo object theo vòng đời và scope được cấu hình.
4. Cung cấp **ProductRepository** cho **ProductService**, rồi cung cấp **ProductService** cho **ProductController**.
5. Quản lý một số callback khởi tạo, hủy bean và những tính năng hạ tầng được kích hoạt.

**Điều Spring không tự làm** là quyết định sản phẩm nào được bán, khi nào có thể hoàn tiền, đơn hàng được giảm giá bao nhiêu hoặc ai được quyền duyệt yêu cầu. Những quyết định đó phải xuất hiện trong mô hình và mã nghiệp vụ của ứng dụng.

### Sơ đồ hai lớp trách nhiệm

~~~text
                Spring IoC container
        ┌────────────────────────────────┐
        │ Đọc bean definitions            │
        │ Tạo object theo cấu hình/scope  │
        │ Resolve và inject dependency   │
        │ Quản lý lifecycle và hạ tầng   │
        └────────────────────────────────┘
                     │ cung cấp bean
                     ▼
              Mã ứng dụng hoạt động
        ┌────────────────────────────────┐
        │ Controller nhận yêu cầu         │
        │ Service thực hiện ca sử dụng    │
        │ Domain áp dụng quy tắc          │
        │ Repository/adapter truy cập I/O │
        └────────────────────────────────┘
                     │
                     ▼
              Kết quả nghiệp vụ
~~~

Container **làm cho các thành phần có thể hợp tác**, còn nội dung hợp tác do ứng dụng xác định.

## 2. Bean, ApplicationContext và mã nghiệp vụ

Trong Spring, **bean** là object được IoC container quản lý. **ApplicationContext** là giao diện container cấp cao thường được sử dụng trong ứng dụng Spring Boot; nó bao gồm khả năng quản lý bean, cấu hình và nhiều dịch vụ tích hợp khác.

Một object Java **không cần trở thành bean** mới có thể chứa nghiệp vụ. Ví dụ, **Money**, **Order**, **Address** hay **DiscountRule** có thể là class/record Java thông thường được tạo bằng **new** hoặc qua factory. Spring không cần quản lý từng giá trị dữ liệu trong mọi request.

| Loại đối tượng | Thường do ai tạo? | Lý do |
|---|---|---|
| **OrderService**, **PaymentGateway**, **OrderController** | Spring container | Thành phần hợp tác lâu dài, có dependency và cấu hình |
| **DataSource**, HTTP client được cấu hình, **Clock** dùng chung | Spring qua auto-configuration hoặc **@Bean** | Cần lắp ráp, tái sử dụng hoặc quản lý tài nguyên |
| **CreateOrderRequest** từ JSON | Cơ chế web deserialization cho từng request | Là dữ liệu đầu vào của từng lần gọi, không phải singleton service |
| **Order** domain object | Mã nghiệp vụ, mapper, persistence layer | Biểu diễn một đơn hàng cụ thể |
| **BigDecimal** tính tiền, danh sách dòng hàng | Mã nghiệp vụ | Giá trị dữ liệu ngắn hạn |

Không nên hiểu “Spring Boot application” là “mọi object đều phải được inject”. **Mã nghiệp vụ thuần Java** thường dễ kiểm thử và biểu diễn quy tắc hơn khi nó không phụ thuộc vào container.

### Sự khác biệt giữa bean và class có annotation

Một class có **@Service** chỉ là ứng viên để được đăng ký thành bean. Nó phải được **component scanning** phát hiện hoặc được khai báo/nhập qua cơ chế cấu hình phù hợp. Nếu class nằm ngoài phạm vi quét hoặc bị điều kiện cấu hình loại bỏ, container có thể không có bean tương ứng.

Ngược lại, một class không có annotation stereotype vẫn có thể được tạo thành bean:

~~~java
@Configuration
public class AppConfiguration {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

**Clock** là class của Java, không có **@Service**. Phương thức **@Bean** yêu cầu container quản lý object được trả về. Điều này đặc biệt hữu ích với các đối tượng từ thư viện mà bạn không thể sửa mã nguồn.

## 3. Những việc container thực sự chịu trách nhiệm

| Trách nhiệm | Container làm gì? | Ứng dụng vẫn cần quyết định gì? |
|---|---|---|
| **Bean registration** | Tìm hoặc nhận bean definition qua scanning, configuration, import, auto-configuration | Thành phần nào là bean; module nào nên được kích hoạt |
| **Bean creation** | Gọi constructor/factory method đúng theo định nghĩa bean | Constructor có tham số nào, object mang ý nghĩa gì |
| **Dependency injection** | Tìm bean phù hợp và đưa vào dependency cần thiết | Hợp đồng dependency, cách sử dụng và luồng nghiệp vụ |
| **Bean scope** | Quản lý số lượng/vòng đời instance theo scope | State nào được phép chia sẻ; có an toàn đồng thời không |
| **Lifecycle** | Gọi callback khởi tạo/hủy của bean theo cơ chế hỗ trợ | Cần mở/đóng tài nguyên nào, tránh làm công việc nghiệp vụ không phù hợp lúc startup |
| **Cấu hình** | Bind properties và tạo bean theo các cấu hình đã khai báo | Giá trị nào có nghĩa, điều kiện nào là quy tắc kinh doanh |
| **Hạ tầng AOP** | Tạo proxy và áp dụng interceptor được cấu hình | Chọn ranh giới transaction, hành vi cache và ý nghĩa của thao tác |

**Container không “hiểu” tên OrderService để tự suy ra luồng đặt hàng.** Nó biết một bean cần dependency gì và một phương thức có annotation/cấu hình nào liên quan tới hạ tầng; nội dung nghiệp vụ của phương thức vẫn là mã Java được người phát triển viết.

### Container không thay thế trách nhiệm sau

- **Quy tắc nghiệp vụ:** giá bán, hạn mức, điều kiện phê duyệt, tính hợp lệ của trạng thái.
- **Kết quả nghiệp vụ:** khi nào tạo đơn thành công; khi nào từ chối; lỗi nào cần thông báo cho người dùng.
- **Thiết kế dữ liệu:** dữ liệu nào cần lưu, quan hệ dữ liệu, ràng buộc, migration và cách xử lý lỗi cạnh tranh.
- **Tính nhất quán xuyên hệ thống:** retry, idempotency, outbox, bù trừ khi gọi nhiều dịch vụ độc lập.
- **Quy tắc phân quyền nghiệp vụ:** ai được thao tác trên một đơn hàng cụ thể, dựa trên vai trò và quan hệ với đơn đó.
- **Hành vi khi lỗi:** lỗi có được thử lại không, có nên hoàn tiền không, giao dịch có phải hủy không.

Spring Boot cung cấp công cụ cho một số vấn đề trên, nhưng **sử dụng công cụ không đồng nghĩa công cụ tự quyết định quy tắc đúng cho sản phẩm**.

## 4. Dependency injection: ai tạo dependency, ai sử dụng dependency?

Giả sử service cần một nơi lưu đơn hàng:

~~~java
public interface OrderStore {
    Order save(Order order);
}
~~~

Service có thể khai báo dependency qua constructor:

~~~java
@Service
public class OrderService {

    private final OrderStore store;

    public OrderService(OrderStore store) {
        this.store = store;
    }

    public Order create(Order order) {
        return store.save(order);
    }
}
~~~

Với một bean duy nhất hiện thực **OrderStore** trong context, Spring có thể inject nó vào **OrderService**. Service nhận một **hợp đồng lưu trữ**, không phải tự quyết định lúc chạy phải tạo loại database client nào.

**Phân chia trách nhiệm:**

- **Container:** tìm implementation phù hợp, tạo object và truyền vào constructor.
- **OrderService:** quyết định khi nào gọi **store.save**, cần kiểm tra dữ liệu gì trước đó, kết quả trả về có ý nghĩa gì.
- **OrderStore implementation:** thực hiện lưu trữ theo công nghệ cụ thể, xử lý ánh xạ dữ liệu và lỗi hạ tầng thuộc phạm vi của nó.

### Tại sao ưu tiên constructor injection?

Constructor làm rõ những dependency bắt buộc. Class có thể được tạo trong test bằng cách truyền dependency thay thế mà không cần bật toàn bộ Spring context.

~~~java
OrderStore fakeStore = order -> order;
OrderService service = new OrderService(fakeStore);
~~~

Ở đây code Java tự tạo service để kiểm tra hành vi. **Không cần Spring container cho mỗi unit test**. Chính việc service chỉ yêu cầu một interface giúp test có thể thay phần lưu trữ.

Với class chỉ có một constructor, Spring thường inject constructor đó mà không cần annotation **@Autowired**. Nếu có nhiều constructor hoặc nhiều bean ứng viên, cần xác định cách Spring chọn dependency thích hợp bằng cấu hình rõ ràng.

### Khi dependency không có hoặc có quá nhiều

Nếu service yêu cầu **OrderStore** nhưng context không có implementation phù hợp, Spring thường báo lỗi khi tạo bean. Nếu context có hai implementation cùng kiểu, Spring có thể không biết chọn bean nào.

Các công cụ như **@Qualifier**, **@Primary** hoặc cấu hình điều kiện có thể giải quyết việc chọn implementation. Nhưng **chọn công nghệ lưu trữ để dùng** là quyết định cấu hình của ứng dụng; container chỉ áp dụng quy tắc lựa chọn đã được cung cấp.

## 5. Ví dụ xuyên suốt: cùng một nghiệp vụ, Spring chỉ lắp ráp

Ta xây dựng ví dụ nhỏ: một hệ thống nhận số lượng hàng được đặt và tính tổng tiền. Một sản phẩm có đơn giá cấu hình trước; khi mua từ **10 đơn vị** trở lên, đơn hàng được giảm **10%**. Để tập trung vào IoC, dữ liệu đơn được lưu trong bộ nhớ. Đây là ví dụ học tập, không phải hệ thống thanh toán thật.

Cấu trúc ứng dụng:

~~~text
src/main/java/com/example/checkout/
├── CheckoutApplication.java
├── domain/
│   ├── Order.java
│   └── PricingPolicy.java
├── application/
│   ├── OrderService.java
│   └── OrderStore.java
├── infrastructure/
│   ├── InMemoryOrderStore.java
│   ├── ShopProperties.java
│   └── BusinessConfiguration.java
└── web/
    ├── OrderController.java
    └── OrderErrorHandler.java

src/main/resources/
└── application.yml
~~~

Trong ứng dụng Spring Initializr, dependency **Spring Web** đủ cho phần HTTP và cấu hình cơ bản trong ví dụ. Các class Java dùng **Java 21**; không cần thêm database starter vì dữ liệu chỉ tồn tại trong memory.

### 5.1. Domain object: dữ liệu cụ thể không phải bean

File **domain/Order.java**:

~~~java
package com.example.checkout.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record Order(
        UUID id,
        int quantity,
        BigDecimal total,
        Instant createdAt) {
}
~~~

Mỗi **Order** đại diện cho một đơn hàng cụ thể. Nó là **giá trị nghiệp vụ**, không phải một singleton bean chia sẻ giữa nhiều request.

### 5.2. Quy tắc giá: Java thuần

File **domain/PricingPolicy.java**:

~~~java
package com.example.checkout.domain;

import java.math.BigDecimal;

public final class PricingPolicy {

    private static final BigDecimal BULK_RATE =
            new BigDecimal("0.90");

    private final BigDecimal unitPrice;

    public PricingPolicy(BigDecimal unitPrice) {
        if (unitPrice == null || unitPrice.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Đơn giá phải lớn hơn 0");
        }
        this.unitPrice = unitPrice;
    }

    public BigDecimal calculateTotal(int quantity) {
        if (quantity <= 0 || quantity > 100) {
            throw new IllegalArgumentException(
                    "Số lượng phải từ 1 đến 100");
        }

        BigDecimal subtotal =
                unitPrice.multiply(BigDecimal.valueOf(quantity));

        // Quy tắc nghiệp vụ: mua từ 10 đơn vị được giảm 10%.
        return quantity >= 10
                ? subtotal.multiply(BULK_RATE)
                : subtotal;
    }
}
~~~

**PricingPolicy** không có annotation Spring. Quy tắc “mua từ 10 đơn vị giảm 10%” là mã Java thuần. Spring không biết và không tự thực hiện quy tắc đó; nó chỉ có thể quản lý một instance **PricingPolicy** nếu ta khai báo thành bean.

Vì **PricingPolicy** giữ một giá trị **BigDecimal bất biến** và phương thức chỉ dùng biến cục bộ, việc dùng một bean singleton cho chính sách này là phù hợp trong ví dụ.

### 5.3. Configuration: tạo bean từ giá trị cấu hình

Ta dùng Spring Boot **@ConfigurationProperties** để đọc đơn giá từ cấu hình ngoài mã nguồn, thay vì viết một giá trị cố định trực tiếp trong class cấu hình. Trong ứng dụng thật, đơn giá cũng có thể đến từ database hoặc hệ thống quản lý giá phù hợp với nghiệp vụ.

File **infrastructure/ShopProperties.java**:

~~~java
package com.example.checkout.infrastructure;

import java.math.BigDecimal;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shop")
public record ShopProperties(BigDecimal unitPrice) {
}
~~~

File **infrastructure/BusinessConfiguration.java**:

~~~java
package com.example.checkout.infrastructure;

import java.time.Clock;

import com.example.checkout.domain.PricingPolicy;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(ShopProperties.class)
public class BusinessConfiguration {

    @Bean
    public PricingPolicy pricingPolicy(ShopProperties properties) {
        return new PricingPolicy(properties.unitPrice());
    }

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Và file **application.yml**:

~~~yaml
shop:
  unit-price: 250000
~~~

Spring Boot bind khóa **shop.unit-price** thành **unitPrice**, rồi container truyền **ShopProperties** cho factory method để tạo **PricingPolicy**.

Tại đây, ranh giới rất rõ:

- **Spring** đọc cấu hình, bind object và gọi phương thức **@Bean**.
- **BusinessConfiguration** chỉ mô tả cách tạo **PricingPolicy** và **Clock**.
- **PricingPolicy.calculateTotal** vẫn tự thực hiện quy tắc giảm giá.

### 5.4. Hợp đồng và adapter lưu trữ

File **application/OrderStore.java**:

~~~java
package com.example.checkout.application;

import java.util.Optional;
import java.util.UUID;

import com.example.checkout.domain.Order;

public interface OrderStore {

    Order save(Order order);

    Optional<Order> findById(UUID id);
}
~~~

File **infrastructure/InMemoryOrderStore.java**:

~~~java
package com.example.checkout.infrastructure;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import com.example.checkout.application.OrderStore;
import com.example.checkout.domain.Order;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryOrderStore implements OrderStore {

    private final Map<UUID, Order> orders =
            new ConcurrentHashMap<>();

    @Override
    public Order save(Order order) {
        orders.put(order.id(), order);
        return order;
    }

    @Override
    public Optional<Order> findById(UUID id) {
        return Optional.ofNullable(orders.get(id));
    }
}
~~~

**@Repository** cho phép class được phát hiện như một Spring component trong package được quét. Container có thể tạo **một instance** lưu trữ dùng chung; bản thân **put**, **findById** và cách lưu **ConcurrentHashMap** là mã Java do ứng dụng viết.

Store này chỉ giữ dữ liệu trong memory và bị mất khi ứng dụng dừng. Container không tự biến nó thành database bền vững, không lưu dữ liệu qua restart và không tự bảo đảm các ràng buộc nghiệp vụ của thao tác thanh toán thật.

### 5.5. Application service: điều phối ca sử dụng

File **application/OrderService.java**:

~~~java
package com.example.checkout.application;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import com.example.checkout.domain.Order;
import com.example.checkout.domain.PricingPolicy;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final PricingPolicy pricingPolicy;
    private final OrderStore store;
    private final Clock clock;

    public OrderService(
            PricingPolicy pricingPolicy,
            OrderStore store,
            Clock clock) {
        this.pricingPolicy = pricingPolicy;
        this.store = store;
        this.clock = clock;
    }

    public Order createOrder(int quantity) {
        BigDecimal total = pricingPolicy.calculateTotal(quantity);

        Order order = new Order(
                UUID.randomUUID(),
                quantity,
                total,
                Instant.now(clock));

        return store.save(order);
    }

    public Optional<Order> findById(UUID id) {
        return store.findById(id);
    }
}
~~~

Spring inject ba dependency mà service cần, nhưng **không quyết định thời điểm nào tạo đơn**, **không tính tổng tiền thay PricingPolicy**, và **không tự gọi store.save**. Những lời gọi đó nằm trong **OrderService.createOrder(...)**, tức mã nghiệp vụ do ứng dụng sở hữu.

### 5.6. Web adapter: đưa HTTP vào ca sử dụng

File **web/OrderController.java**:

~~~java
package com.example.checkout.web;

import java.net.URI;
import java.util.UUID;

import com.example.checkout.application.OrderService;
import com.example.checkout.domain.Order;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<Order> create(
            @RequestBody CreateOrderRequest request) {
        Order order = service.createOrder(request.quantity());

        return ResponseEntity
                .created(URI.create("/orders/" + order.id()))
                .body(order);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Order> get(@PathVariable UUID id) {
        return service.findById(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    public record CreateOrderRequest(int quantity) {
    }
}
~~~

File **web/OrderErrorHandler.java**:

~~~java
package com.example.checkout.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class OrderErrorHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    public ProblemDetail invalidOrder(
            IllegalArgumentException exception) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                exception.getMessage());
    }
}
~~~

**OrderController** quyết định HTTP method, đường dẫn, response status và cách gọi service. **OrderErrorHandler** chuyển lỗi đầu vào được ném ra từ nghiệp vụ thành HTTP 400 cho client. Container phát hiện và đăng ký controller/advice như bean, còn các phương thức trong đó được Spring MVC gọi khi request tương ứng xảy ra.

Với dự án lớn, response DTO có thể được tách riêng thay vì trả thẳng domain model. Ví dụ sử dụng domain record trực tiếp để người đọc tập trung vào ranh giới container và nghiệp vụ.

### 5.7. Khởi động và thử yêu cầu

File **CheckoutApplication.java**:

~~~java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CheckoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
~~~

Các package **domain**, **application**, **infrastructure** và **web** nằm dưới **com.example.checkout**, vì vậy component scanning mặc định có thể tìm các class được đăng ký. Spring Boot khởi động ApplicationContext và, do project có Spring Web, chuẩn bị hạ tầng HTTP thích hợp.

Gửi request:

~~~bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -d '{"quantity":10}'
~~~

Ví dụ response:

~~~http
HTTP/1.1 201 Created
Location: /orders/6a3514cd-93e2-4b54-9e58-614e12bf798d
Content-Type: application/json

{
  "id": "6a3514cd-93e2-4b54-9e58-614e12bf798d",
  "quantity": 10,
  "total": 2250000.00,
  "createdAt": "2026-01-01T00:00:00Z"
}
~~~

UUID và thời điểm trong response chỉ là dữ liệu minh họa. Tổng tiền là kết quả quy tắc trong **PricingPolicy**: 250.000 × 10 × 0,90 = 2.250.000.

Với số lượng **0**, **PricingPolicy** ném **IllegalArgumentException**; web adapter chuyển lỗi thành HTTP 400. Container không tự sáng tạo giới hạn 1–100 hay chính sách giảm giá đó.

### 5.8. Container và nghiệp vụ tham gia ở hai thời điểm khác nhau

~~~text
KHỞI ĐỘNG ỨNG DỤNG

Spring Boot tạo ApplicationContext
        │
        ├── Đọc cấu hình shop.unit-price
        ├── Bind ShopProperties
        ├── Gọi @Bean tạo PricingPolicy và Clock
        ├── Tạo InMemoryOrderStore
        ├── Inject các bean vào OrderService
        └── Inject OrderService vào OrderController
                                      │
                                      ▼
                              Ứng dụng sẵn sàng

KHI CÓ HTTP REQUEST POST /orders

Spring MVC nhận và giải mã JSON
        │
        ▼
OrderController.create(...)
        │
        ▼
OrderService.createOrder(...)
        │
        ├── PricingPolicy.calculateTotal(...)  ← quy tắc nghiệp vụ
        ├── Tạo Order                        ← dữ liệu nghiệp vụ
        └── OrderStore.save(...)              ← thao tác lưu
        │
        ▼
OrderController trả 201 + kết quả
~~~

Phân biệt được **startup/lắp ráp bean** với **runtime/xử lý nghiệp vụ** là một trong những chìa khóa hiểu IoC container.

## 6. Scope: container quản lý instance, nghiệp vụ quản lý state

Theo mặc định, bean trong Spring có **singleton scope**: trong phạm vi một Spring container, thường có **một instance của bean definition** được dùng chung khi inject nhiều nơi. Điều này khác với khái niệm “singleton toàn JVM” và cũng không có nghĩa một instance được chia sẻ giữa nhiều tiến trình ứng dụng.

Một **@Service** singleton có thể được nhiều request gọi đồng thời. Vì thế:

~~~java
@Service
public class UnsafeOrderService {

    private String currentCustomerId;

    public void process(String customerId) {
        currentCustomerId = customerId;
        // Request khác có thể ghi đè field này.
    }
}
~~~

Field **currentCustomerId** là state riêng của từng request nhưng lại nằm trên bean chia sẻ. Khi nhiều request chạy đồng thời, dữ liệu có thể bị ghi đè hoặc rò rỉ giữa các lần xử lý.

Cách tổ chức phù hợp hơn:

~~~java
@Service
public class OrderService {

    public void process(String customerId) {
        // customerId là biến tham số của lần gọi hiện tại.
        // Dependency dùng chung được giữ bằng final field.
    }
}
~~~

**Container chịu trách nhiệm số lượng và vòng đời instance theo scope**, nhưng **ứng dụng chịu trách nhiệm thiết kế state có an toàn đồng thời hay không**. Spring không tự thêm khóa bảo vệ mọi field có thể thay đổi.

### Các scope phổ biến

| Scope | Ý nghĩa | Cân nhắc |
|---|---|---|
| **singleton** | Một instance bean definition trong mỗi Spring container | Phù hợp với service stateless và cấu hình dùng chung |
| **prototype** | Tạo instance mới khi container được yêu cầu cung cấp bean | Không tự có nghĩa một instance cho mỗi HTTP request; container không quản lý đầy đủ giai đoạn hủy của từng instance như singleton |
| **request** | Instance theo HTTP request trong web-aware context | Phù hợp state thực sự gắn với request, chỉ dùng khi có web context thích hợp |
| **session** | Instance theo HTTP session trong web-aware context | Cần xem xét vòng đời session, bộ nhớ và triển khai phân tán |

Không nên chuyển mọi service thành **prototype** hoặc **request scope** để chữa việc lưu state sai chỗ. Ưu tiên service ít state, dữ liệu của mỗi request được truyền qua tham số hoặc đối tượng chuyên biệt.

Một bean singleton inject trực tiếp bean prototype thường nhận instance được tạo tại thời điểm resolve dependency, **không tự động nhận instance mới ở mỗi lần gọi phương thức**. Nếu thực sự cần tạo instance động, có thể dùng **ObjectProvider** hoặc factory thích hợp.

## 7. Lifecycle: container biết lúc nào gọi callback, nghiệp vụ biết callback làm gì

Đối với bean được Spring quản lý, vòng đời đơn giản có thể hình dung:

~~~text
Đọc bean definition
        │
        ▼
Khởi tạo object / constructor
        │
        ▼
Inject dependencies và cấu hình
        │
        ▼
Các bước BeanPostProcessor và init callbacks
        │
        ▼
Bean sẵn sàng phục vụ ứng dụng
        │
        ▼
Context đóng
        │
        ▼
Destroy callbacks đối với bean được quản lý phù hợp
~~~

Spring hỗ trợ callback như **@PostConstruct** và **@PreDestroy** cho những bean có vòng đời được quản lý phù hợp:

~~~java
@Component
public class ConnectionMonitor {

    @PostConstruct
    public void initialize() {
        // Chuẩn bị trạng thái kỹ thuật cần thiết.
    }

    @PreDestroy
    public void cleanup() {
        // Giải phóng tài nguyên nếu component sở hữu tài nguyên.
    }
}
~~~

Với Spring Boot 3.x, các annotation lifecycle trong ví dụ thuộc package **jakarta.annotation**. Các import đã được lược bớt trong đoạn minh họa.

**Container quyết định khi nào gọi callback** theo lifecycle, còn **nội dung callback** do class định nghĩa. Nó không tự biết “cần gửi email cho khách hàng” hay “cần khóa đơn hàng đã thanh toán”.

### Có nên đưa nghiệp vụ lớn vào @PostConstruct?

Thông thường không. **@PostConstruct** phục vụ khởi tạo bean và chạy trong quá trình context được thiết lập. Nếu thực hiện nhập hàng triệu bản ghi, gọi một dịch vụ ngoài không ổn định hoặc phát thông báo kinh doanh tại đây, việc khởi động ứng dụng có thể bị chậm, thất bại hoặc tạo tác dụng phụ khó kiểm soát.

Spring Boot có **ApplicationRunner** và **CommandLineRunner** để chạy logic sau khi context đã được khởi tạo; scheduler, message listener hoặc công cụ điều phối job có thể phục vụ các nhiệm vụ nền. Nhưng ngay cả với những cơ chế đó, ứng dụng vẫn phải thiết kế retry, idempotency, trạng thái công việc và kết quả nghiệp vụ phù hợp.

**Object lifecycle không đồng nghĩa business lifecycle.** Việc bean được tạo/hủy khác hẳn việc một đơn hàng đổi trạng thái **CREATED → PAID → SHIPPED**. Chuỗi trạng thái và điều kiện chuyển trạng thái là nghiệp vụ.

## 8. @Transactional: ranh giới giữa khai báo nghiệp vụ và cơ chế thực thi

**@Transactional** là ví dụ rõ về cách framework và mã ứng dụng phối hợp. Giả sử việc đặt hàng phải vừa tạo đơn vừa trừ tồn kho trong cùng database. Application service quyết định hai thao tác này phải thành một đơn vị nhất quán:

~~~java
@Service
public class CheckoutService {

    @Transactional
    public void checkout(CheckoutCommand command) {
        stockRepository.decrease(command.productId(),
                                 command.quantity());
        orderRepository.save(newOrder(command));
    }
}
~~~

Đoạn trên chỉ minh họa ranh giới transaction; các type và phương thức như **CheckoutCommand**, **stockRepository** và **newOrder** cần được định nghĩa trong ứng dụng tương ứng.

Ở đây:

- **Người viết nghiệp vụ** quyết định thao tác nào phải nằm cùng transaction và thứ tự thực hiện chúng.
- **Spring transaction infrastructure** thông qua transaction manager và thường là proxy/interceptor sẽ mở, hoàn tất hoặc rollback giao dịch theo cấu hình và quy tắc rollback.
- **Database/persistence provider** thực hiện các bảo đảm giao dịch mà công nghệ đó hỗ trợ.

Framework **không tự biết** rằng “trừ hàng phải đi cùng tạo đơn” nếu ca sử dụng không được tổ chức đúng. Nó cũng không tự giải quyết mọi dạng consistency phân tán.

### Ba giới hạn rất đáng nhớ

**1. Transaction thường hoạt động qua proxy.** Nếu bean gọi một phương thức **@Transactional** khác của chính nó bằng **this.method(...)**, lời gọi nội bộ có thể không đi qua proxy và không kích hoạt interception theo cách mong đợi.

**2. Rollback có quy tắc.** Mặc định, Spring thường rollback với **RuntimeException** và **Error**, nhưng không mặc định rollback mọi checked exception; cần cấu hình riêng nếu ca sử dụng yêu cầu.

**3. Transaction database không tự bao trùm HTTP/email/queue.** Nếu đã ghi database rồi gửi email thất bại, annotation **@Transactional** trên service không tự hoàn tác email hoặc biến hai hệ thống thành một giao dịch phân tán. Ứng dụng cần chiến lược phù hợp như outbox, retry an toàn hoặc điều phối nghiệp vụ.

**@Transactional(readOnly = true)** là chỉ dẫn cho hạ tầng transaction/persistence, không phải cách áp đặt quy tắc nghiệp vụ rằng người dùng bị cấm sửa dữ liệu.

## 9. Validation: framework có thể kiểm tra điều kiện, nhưng ai đặt ra điều kiện?

Spring và Bean Validation có thể giúp kích hoạt kiểm tra từ những ràng buộc mà lập trình viên khai báo:

~~~java
public record CreateAccountRequest(
        @NotBlank String customerName,
        @Email String email) {
}
~~~

Khi request body được đánh dấu **@Valid** trong controller và có hạ tầng validation phù hợp, framework có thể kiểm tra **@NotBlank**, **@Email** và tạo lỗi khi dữ liệu không đáp ứng.

Tuy nhiên, ràng buộc “email có cú pháp hợp lệ” khác với các quy tắc như:

- Một khách hàng không được mở hai tài khoản đang hoạt động cho cùng một sản phẩm.
- Hạn mức tín dụng thay đổi theo lịch sử giao dịch.
- Đơn hàng chỉ được hủy trước khi bàn giao cho đơn vị vận chuyển.
- Khuyến mãi chỉ áp dụng khi khách hàng đáp ứng nhiều điều kiện.

Những quy tắc sau có thể cần domain/application service, dữ liệu từ repository, cơ chế đồng thời và transaction thích hợp. **Validation infrastructure thực thi ràng buộc được khai báo; nó không tự suy ra toàn bộ chính sách của sản phẩm.**

Vì vậy, nên phân biệt:

| Vấn đề | Nơi thường xử lý |
|---|---|
| JSON có đúng định dạng để chuyển thành DTO không? | HTTP framework / message converter |
| Trường bắt buộc có rỗng không? | Bean Validation ở ranh giới đầu vào, hoặc nghiệp vụ khi cần |
| Người dùng có được hủy đơn này không? | Authorization và quy tắc nghiệp vụ |
| Đơn hàng đã SHIPPED có được trở về CREATED không? | Domain/application logic |
| Một transaction có rollback đúng không? | Transaction infrastructure áp dụng theo cấu hình và luồng nghiệp vụ |

## 10. Configuration và @Profile không phải là quy tắc kinh doanh

Spring hỗ trợ **@Configuration**, **@Bean**, **@Conditional**, **@Profile**, **@ConfigurationProperties** và nhiều cơ chế để tạo hoặc chọn bean theo môi trường. Chúng phù hợp với câu hỏi:

> Ứng dụng này đang chạy ở môi trường nào, cần dùng implementation nào và cần cấu hình dependency ra sao?

Ví dụ, có thể dùng một implementation gửi email giả ở môi trường phát triển và một adapter thật ở môi trường được cấu hình để gửi email.

Nhưng các câu hỏi:

> Khách hàng A có được miễn phí vận chuyển không? Đơn hàng B có đủ điều kiện hoàn tiền không?

là các quyết định theo dữ liệu nghiệp vụ và trạng thái thực tế, không phải lý do để tạo một Spring bean khác cho **mỗi khách hàng** bằng **@Profile**.

**Phân biệt rõ:**

- **Cấu hình bean** chủ yếu là lựa chọn và lắp ráp component cho một application context.
- **Quyết định nghiệp vụ** được thực hiện khi xử lý một ca sử dụng, thường phụ thuộc input, dữ liệu và trạng thái tại thời điểm đó.

Không nên thiết kế một annotation cấu hình phức tạp để thay thế một phương thức nghiệp vụ rõ ràng. Công cụ của Spring nên phục vụ logic của ứng dụng, không che giấu nó.

## 11. Khi nào container thực sự gọi mã do bạn viết?

Container và các framework tích hợp có thể gọi mã ứng dụng tại nhiều thời điểm:

| Thời điểm | Ai bắt đầu lời gọi? | Mã ứng dụng làm gì? |
|---|---|---|
| Tạo bean | IoC container | Constructor/factory method khởi tạo object |
| Khởi tạo xong | Lifecycle infrastructure | Callback khởi tạo nguồn lực cần thiết |
| HTTP request tới | Spring MVC/WebFlux infrastructure | Controller xử lý request và gọi service |
| Lịch kích hoạt | Scheduling infrastructure | Phương thức **@Scheduled** thực thi nhiệm vụ được viết |
| Message tới | Messaging integration | Listener chuyển message thành một ca sử dụng |
| Transactional method được gọi qua proxy | AOP/transaction interceptor | Service thực thi nghiệp vụ trong ranh giới transaction |
| Dừng ứng dụng | ApplicationContext lifecycle | Callback cleanup giải phóng nguồn lực |

**IoC không chỉ là “Spring gọi constructor thay bạn”**, vì framework còn có thể điều phối vòng đời và những điểm vào được cấu hình. Nhưng **thứ được gọi vẫn là mã ứng dụng** với quy tắc, điều kiện và kết quả do lập trình viên định nghĩa.

Trong một ứng dụng web, chẳng hạn:

~~~text
Spring MVC chọn đúng controller method
                   │
                   ▼
Controller gọi OrderService
                   │
                   ▼
OrderService kiểm tra quy tắc
                   │
                   ▼
Repository lưu dữ liệu
                   │
                   ▼
Spring MVC chuyển kết quả sang HTTP response
~~~

Spring MVC quản lý **dispatch và HTTP mechanics**; service quản lý **ý nghĩa nghiệp vụ** của việc xử lý.

## 12. Không dùng ApplicationContext như “kho tra cứu” trong mọi service

Một lỗi thiết kế dễ gặp là inject container vào service rồi yêu cầu bean theo tên trong mọi phương thức:

~~~java
@Service
public class PaymentService {

    private final ApplicationContext context;

    public PaymentService(ApplicationContext context) {
        this.context = context;
    }

    public void pay() {
        PaymentGateway gateway =
                context.getBean(PaymentGateway.class);
        gateway.charge();
    }
}
~~~

Mã trên minh họa sự phụ thuộc trực tiếp vào container. Khi đọc constructor, ta không biết service thực sự cần **PaymentGateway**; chỉ khi đọc thân phương thức mới thấy. Điều này làm dependency khó quan sát và việc kiểm thử dễ bị kéo theo Spring context.

Thông thường nên viết:

~~~java
@Service
public class PaymentService {

    private final PaymentGateway gateway;

    public PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public void pay() {
        gateway.charge();
    }
}
~~~

Ví dụ giả định **PaymentGateway** có phương thức **charge()** và có bean implementation phù hợp. Container vẫn làm việc chọn và inject dependency, nhưng business service chỉ phụ thuộc vào **hợp đồng mà nó cần**.

Việc sử dụng **ApplicationContext** trực tiếp không phải lúc nào cũng sai: code khởi tạo framework, plugin host, dynamic bean discovery hoặc tooling đôi khi có nhu cầu thực sự. Nhưng với một service nghiệp vụ thông thường, **constructor injection** là cách biểu diễn dependency minh bạch hơn.

## 13. Một số hiểu nhầm phổ biến

### “Thêm @Service thì Spring sẽ tự hiểu chức năng của class”

Không. **@Service** giúp đăng ký bean theo cơ chế Spring. Tên class, annotation và container không thay thế được việc triển khai phương thức nghiệp vụ.

### “Container quản lý bean nghĩa là container quản lý tất cả dữ liệu của ứng dụng”

Không. Container quản lý các **bean**; dữ liệu đơn hàng, thông tin request, entity database và domain object có vòng đời khác nhau. Đừng lưu thông tin thay đổi theo từng người dùng vào field của singleton service chỉ vì nó là Spring bean.

### “Chỉ cần dependency injection thì không cần thiết kế ranh giới”

Không. Dependency injection có thể lắp ráp cả một thiết kế phụ thuộc vòng vèo, nhiều trách nhiệm hoặc khó bảo trì nếu code vẫn phụ thuộc sai hướng. Container không tự lựa chọn kiến trúc đúng cho ứng dụng.

### “@Transactional làm mọi tác vụ tự nhất quán”

Không. Transaction được áp dụng theo phạm vi và công nghệ hỗ trợ, với những quy tắc proxy và rollback cụ thể. Tính nhất quán của nghiệp vụ xuyên nhiều hệ thống vẫn cần được thiết kế.

### “Bean singleton chắc chắn an toàn đồng thời”

Không. Singleton là **scope**, không phải bảo đảm thread safety. Mutable state của singleton cần được thiết kế cẩn thận.

### “Dùng @PostConstruct để chạy tất cả nghiệp vụ một lần”

Không nên mặc định như vậy. Callback init là phần vòng đời bean. Công việc nghiệp vụ chạy một lần, chạy theo lịch hoặc cần trạng thái bền vững thường có cơ chế điều phối thích hợp hơn.

### “Cứ thêm package vào component scan là Spring tìm được mọi dependency”

Không. Class phải có mặt trên runtime classpath, phải được đăng ký theo cơ chế phù hợp và không bị điều kiện cấu hình loại bỏ. Entity JPA, repository proxy và configuration properties có những cơ chế đăng ký riêng.

### “Bỏ Spring thì toàn bộ mã nghiệp vụ phải viết lại”

Không nhất thiết. Mã nghiệp vụ thuần Java được tách khỏi HTTP, database và API container có thể tiếp tục chạy với dependency được truyền thủ công hoặc trong môi trường kiểm thử khác. Càng gắn chặt nghiệp vụ với API framework và service locator, việc tái sử dụng càng khó.

## 14. Thử nghiệm phân biệt trách nhiệm của container và nghiệp vụ

Sau khi hiểu ví dụ **PricingPolicy** và **OrderService**, thử các thay đổi dưới đây và dự đoán kết quả trước khi chạy:

| Thay đổi | Thành phần cần sửa | Điều quan sát |
|---|---|---|
| Đổi đơn giá từ 250.000 sang 300.000 | **application.yml** hoặc nguồn cấu hình giá | Tổng tiền thay đổi, service vẫn gọi cùng policy |
| Đổi ngưỡng giảm 10 đơn vị thành 5 | **PricingPolicy** | Thay đổi quy tắc tính tiền, không cần thay cách Spring inject bean |
| Dùng một store lưu database thay cho in-memory | **OrderStore implementation** và cấu hình persistence | Nghiệp vụ có thể giữ nguyên hợp đồng, hạ tầng lưu trữ thay đổi |
| Bổ sung HTTP endpoint đọc đơn hàng | **OrderController** | Web adapter thay đổi, service/repository được tái sử dụng |
| Thiếu bean **Clock** | Configuration | Container không thể thỏa mãn dependency của OrderService |
| Tạo hai bean **OrderStore** cùng kiểu không có quy tắc chọn | Configuration/bean registration | Spring có thể báo mơ hồ dependency |
| Đặt currentOrderId vào field singleton OrderService | Thiết kế state của service | Request đồng thời có thể ảnh hưởng nhau; container không tự bảo vệ |
| Gọi chính một method @Transactional từ method khác cùng object | Thiết kế transaction boundary | Có nguy cơ không đi qua transaction proxy như kỳ vọng |

Mỗi tình huống giúp trả lời câu hỏi: **đây là thay đổi về cách hệ thống được lắp ráp, hay thay đổi về quy tắc và hành vi khi một ca sử dụng chạy?**

### Unit test quy tắc mà không cần Spring

Vì **PricingPolicy** là class thuần Java, có thể dùng JUnit để kiểm tra trực tiếp:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import com.example.checkout.domain.PricingPolicy;

class PricingPolicyTest {

    @Test
    void appliesDiscountForTenOrMoreItems() {
        PricingPolicy policy =
                new PricingPolicy(new BigDecimal("250000"));

        BigDecimal actual = policy.calculateTotal(10);

        assertEquals(
                0,
                new BigDecimal("2250000.00").compareTo(actual));
    }
}
~~~

Test này kiểm tra **quy tắc giảm giá**, không kiểm tra container. Nếu muốn kiểm tra **@ConfigurationProperties**, bean registration, constructor injection hoặc việc khởi tạo context, khi đó mới cần test có Spring context phù hợp.

Đó là lợi ích thực tế của ranh giới rõ ràng: **quy tắc được kiểm tra độc lập với framework; phần lắp ráp được kiểm tra ở nơi cần sự tham gia của framework**.

## 15. Những câu hỏi giúp xác định đúng ranh giới

Khi cân nhắc một đoạn mã nên nằm ở đâu, tự hỏi:

1. **Nếu đổi từ REST API sang CLI, quy tắc này có còn đúng không?** Nếu còn, nhiều khả năng đó là logic nghiệp vụ, không nên gắn chặt vào controller hoặc HttpServletRequest.
2. **Đoạn mã đang quyết định một bean được tạo như thế nào, hay quyết định một đơn hàng được xử lý thế nào?** Việc đầu thường thuộc configuration/container, việc sau thuộc service/domain.
3. **Giá trị này tồn tại trong suốt đời ứng dụng hay chỉ trong một request?** Dependency dùng chung có thể là singleton; dữ liệu riêng của request nên có vòng đời thích hợp.
4. **Khi thất bại, ai biết hành động đúng về mặt kinh doanh?** Framework biết báo exception hoặc rollback theo quy tắc kỹ thuật; ứng dụng biết có phải hủy đơn, hoàn tiền, thử lại hay thông báo người dùng không.
5. **Có thể kiểm tra quy tắc bằng Java thuần không?** Nếu có, mã nghiệp vụ đã tương đối độc lập với hạ tầng và dễ kiểm thử hơn.
6. **Mở rộng component scan hoặc thêm annotation có thực sự sửa nguyên nhân?** Nếu thiếu bean do classpath, điều kiện cấu hình hoặc sai loại dependency, sửa scan không giải quyết đúng vấn đề.

## Kết luận

**Spring IoC container chịu trách nhiệm quản lý và lắp ráp các bean:** phát hiện/đăng ký, khởi tạo, inject dependency, áp dụng scope, lifecycle và những khả năng hạ tầng được cấu hình. Container giúp ứng dụng vận hành có tổ chức khi số lượng component tăng.

**Mã nghiệp vụ chịu trách nhiệm ý nghĩa và kết quả của từng ca sử dụng:** dữ liệu nào hợp lệ, quy tắc nào được áp dụng, thao tác nào phải thực hiện và điều gì cần xảy ra khi thành công hoặc thất bại. Spring có thể hỗ trợ validation, transaction, web dispatch và nhiều cơ chế khác, nhưng chúng không tự định nghĩa chính sách kinh doanh.

Hãy để **container trả lời “những thành phần nào được tạo, kết nối và quản lý như thế nào?”** và để **service/domain trả lời “ứng dụng phải xử lý công việc này ra sao?”**. Khi giữ được ranh giới đó, Spring Boot phát huy sức mạnh của dependency injection mà mã nghiệp vụ vẫn rõ ràng, dễ kiểm thử và dễ phát triển.
