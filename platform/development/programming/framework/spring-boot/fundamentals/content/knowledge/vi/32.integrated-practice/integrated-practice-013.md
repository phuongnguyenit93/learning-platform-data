# Tổng hợp sơ đồ khởi động, đồ thị bean và bằng chứng hành vi ứng dụng

Khi một ứng dụng Spring Boot khởi động, nhiều thành phần cùng tham gia: Java launcher tạo JVM, Spring Boot chuẩn bị `Environment`, Spring container đọc bean definitions, resolve dependencies, tạo bean, chạy initialization callbacks, khởi động web server và cuối cùng chuyển ứng dụng sang trạng thái sẵn sàng.

Khi một request đi vào, controller gọi application service, service gọi các collaborator và kết quả được trả về. Khi cần chứng minh ứng dụng hoạt động đúng, một dòng log `Started ...` hoặc endpoint health trả `UP` chưa đủ. Ta cần bằng chứng phù hợp với từng câu hỏi:

- **Startup:** context đã được tạo và các bước bắt buộc đã hoàn tất chưa?
- **Wiring:** bean nào được đăng ký, dependency nào được inject và có implementation nào được chọn?
- **Behavior:** với input xác định, ứng dụng có trả kết quả đúng và tạo side effect đúng không?
- **Runtime:** request thật có được xử lý ổn định, đủ nhanh và có thể quan sát khi lỗi không?

Bài thực hành này kết hợp ba góc nhìn: **sơ đồ khởi động**, **đồ thị bean** và **bằng chứng hành vi ứng dụng**. Ta xây một ví dụ Order API nhỏ, theo dõi lifecycle, xác định dependency graph, viết các mức kiểm thử và liên hệ chúng với log, metrics, traces và health probes.

> Mỗi sơ đồ và phép kiểm tra chỉ chứng minh một phạm vi cụ thể. Startup thành công chứng minh các bước startup đã qua; bean graph cho biết cách object được lắp ghép; tests và runtime signals mới cung cấp bằng chứng về hành vi mà chúng thực sự kiểm tra.

## 1. Mục tiêu của bài thực hành

Sau bài này, bạn có thể:

1. Mô tả thứ tự chính của Spring Boot startup từ `SpringApplication.run()` đến `ApplicationReadyEvent`.
2. Phân biệt bean definition, bean instance, dependency graph và runtime call graph.
3. Vẽ dependency graph từ constructor injection và Java configuration.
4. Xác định bean nào được component scan, bean nào được tạo từ `@Bean`.
5. Chứng minh một chức năng bằng unit test, context test, MVC test và integration test.
6. Chọn bằng chứng phù hợp cho startup, wiring, HTTP behavior và business correctness.
7. Dùng log, metrics, traces và health endpoints để chẩn đoán mà không coi một tín hiệu là bằng chứng toàn diện.
8. Tổ chức một design review hoặc deployment review dựa trên bằng chứng có thể tái hiện.

## 2. Ba mô hình cần nhìn cùng nhau

Một ứng dụng có thể được mô tả qua ba mô hình khác nhau.

### 2.1. Startup timeline

Startup timeline trả lời câu hỏi: **Spring Boot đã đi qua những bước nào và theo thứ tự nào?**

```text
Java launcher
    |
    v
JVM starts
    |
    v
SpringApplication.run(...)
    |
    v
Prepare Environment
    |
    v
Create / prepare ApplicationContext
    |
    v
Load bean definitions
    |
    v
Refresh context
    |
    +--> Instantiate non-lazy singletons
    +--> Resolve dependencies
    +--> Initialize beans
    +--> Apply BeanPostProcessors / proxies
    +--> Start lifecycle components
    +--> Start embedded web server when applicable
    |
    v
ApplicationStartedEvent
    |
    v
ApplicationRunner / CommandLineRunner
    |
    v
ApplicationReadyEvent
    |
    v
Application available for normal traffic
```

Đây là sơ đồ khái quát. Một số chi tiết nội bộ và log cụ thể phụ thuộc Spring Boot version, loại ứng dụng và customization. Các mốc quan trọng cần nhớ là context refresh hoàn tất trước `ApplicationStartedEvent`; runners chạy sau đó; `ApplicationReadyEvent` được phát sau khi runners hoàn tất trong luồng startup thành công.

### 2.2. Bean dependency graph

Bean graph trả lời câu hỏi: **object nào cần object nào để được tạo và hoạt động?**

Ví dụ:

```text
OrderController
      |
      v
PlaceOrderService
    /       \
   v         v
OrderStore  Clock
   ^          ^
   |          |
InMemory   Java Configuration
OrderStore @Bean
```

Mũi tên thể hiện dependency: `PlaceOrderService` cần `OrderStore` và `Clock`. Spring dùng constructor/method parameters cùng bean definitions để resolve các dependency đó.

### 2.3. Runtime call graph

Runtime call graph trả lời câu hỏi: **khi một request cụ thể chạy, những method nào được gọi và theo thứ tự nào?**

```text
POST /orders
     |
     v
OrderController.create(...)
     |
     v
PlaceOrderService.place(...)
     |
     +--> OrderPolicy.validate(...)
     |
     +--> Clock.instant()
     |
     +--> OrderStore.save(...)
     |
     v
HTTP 201 + OrderResponse
```

Bean graph và call graph có liên quan nhưng không giống nhau. Một bean có thể được inject nhưng không được gọi trong một request cụ thể. Một method có thể gọi nhiều object khác trong runtime mà không làm thay đổi dependency graph đã tạo.

## 3. Phân biệt ba sơ đồ với ba loại bằng chứng

| Mô hình | Điều nó mô tả | Bằng chứng phù hợp |
| --- | --- | --- |
| Startup timeline | Các mốc lifecycle | Events, startup logs, context state |
| Bean dependency graph | Quan hệ wiring giữa beans | Context test, bean inspection, constructor graph |
| Runtime call graph | Luồng xử lý một use case | Unit/integration test, trace, structured logs |

Một ví dụ:

- Log `Started OrderApplication ...` không cho biết service inject implementation nào.
- Bean graph có `OrderStore -> InMemoryOrderStore` không chứng minh `save()` ghi đúng dữ liệu.
- Unit test `PlaceOrderService` pass không chứng minh Spring đã scan đúng controller.
- `GET /actuator/health` trả `UP` không chứng minh `POST /orders` trả 201 và lưu đúng đơn hàng.

Muốn đưa ra kết luận chính xác, hãy nêu **đã kiểm tra điều gì, bằng cách nào và giới hạn của phép kiểm tra**.

## 4. Xây ứng dụng mẫu Order API

Ta dùng một use case nhỏ:

> Nhận thông tin đơn hàng, xác thực dữ liệu, gắn thời điểm tạo và lưu đơn hàng; trả về mã đơn hàng cùng trạng thái.

Các thành phần:

```text
API layer
  OrderController

Application layer
  PlaceOrderService
  OrderPolicy
  OrderStore (port)

Infrastructure / wiring
  InMemoryOrderStore
  Clock bean
```

Đây là ứng dụng minh họa để học startup, wiring và evidence. `InMemoryOrderStore` lưu dữ liệu trong bộ nhớ của process; dữ liệu sẽ mất khi process kết thúc. Trong một hệ thống production, có thể thay bằng adapter JPA hoặc một persistence implementation phù hợp.

### 4.1. Cấu trúc package

```text
com.example.orders
├── OrderApplication.java
├── api
│   ├── CreateOrderRequest.java
│   ├── OrderResponse.java
│   └── OrderController.java
├── application
│   ├── PlaceOrderService.java
│   └── OrderPolicy.java
├── domain
│   ├── Order.java
│   └── OrderStatus.java
├── port
│   └── OrderStore.java
└── infrastructure
    ├── InMemoryOrderStore.java
    └── TimeConfiguration.java
```

Đặt application class tại package gốc giúp component scan mặc định tìm thấy các package con.

## 5. Tạo domain model

`OrderStatus.java`:

```java
package com.example.orders.domain;

public enum OrderStatus {
    CREATED
}
```

`Order.java`:

```java
package com.example.orders.domain;

import java.math.BigDecimal;
import java.time.Instant;

public record Order(
        String id,
        String customerId,
        BigDecimal amount,
        Instant createdAt,
        OrderStatus status
) {
}
```

Đây là domain data model thuần Java. Nó không cần là Spring bean vì mỗi order là dữ liệu của một giao dịch cụ thể, không phải collaborator dùng chung của application context.

### 5.1. Vì sao không autowire `Order`?

Một `Order` cụ thể được tạo cho mỗi yêu cầu:

```java
Order order = new Order(...);
```

Nó có lifecycle gắn với use case và dữ liệu. Đăng ký mọi order thành bean singleton là sai phạm vi. Spring bean phù hợp hơn với các collaborator như service, policy, repository adapter hoặc client dùng chung.

## 6. Định nghĩa persistence port

`OrderStore.java`:

```java
package com.example.orders.port;

import com.example.orders.domain.Order;
import java.util.Optional;

public interface OrderStore {

    Order save(Order order);

    Optional<Order> findById(String id);
}
```

`OrderStore` diễn tả khả năng mà application service cần: lưu và tìm đơn hàng.

Application layer không cần biết dữ liệu được lưu bằng:

- Map trong bộ nhớ.
- JPA repository.
- JDBC.
- Một remote order service.

Đây là một abstraction có ý nghĩa vì nó bảo vệ use case khỏi chi tiết persistence.

## 7. Tạo policy nghiệp vụ

`OrderPolicy.java`:

```java
package com.example.orders.application;

import com.example.orders.domain.Order;
import java.math.BigDecimal;
import org.springframework.stereotype.Component;

@Component
public class OrderPolicy {

    public void validate(String customerId, BigDecimal amount) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer ID is required"
            );
        }

        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Order amount must be positive"
            );
        }
    }
}
```

Trong ví dụ, `OrderPolicy` được đăng ký bằng component scan. Policy là collaborator dùng chung nên phù hợp làm bean.

Import `Order` chưa cần thiết trong class này và có thể bỏ nếu IDE báo unused import; đoạn code tập trung vào validation input.

## 8. Tạo persistence adapter

`InMemoryOrderStore.java`:

```java
package com.example.orders.infrastructure;

import com.example.orders.domain.Order;
import com.example.orders.port.OrderStore;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryOrderStore implements OrderStore {

    private final ConcurrentMap<String, Order> orders =
            new ConcurrentHashMap<>();

    @Override
    public Order save(Order order) {
        orders.put(order.id(), order);
        return order;
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }
}
```

`@Repository` là stereotype để component scan phát hiện adapter. Trong ứng dụng thật, một repository JPA có thể implement cùng port và chuyển đổi giữa domain object và persistence entity.

`ConcurrentHashMap` cho phép truy cập an toàn giữa nhiều request ở mức cấu trúc map. Nó không biến dữ liệu thành persistent storage và không thay thế transaction semantics của database.

## 9. Đăng ký `Clock` bằng Java configuration

`TimeConfiguration.java`:

```java
package com.example.orders.infrastructure;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Đây là ví dụ Java configuration:

- `@Configuration` khai báo một configuration class.
- `@Bean` đăng ký object trả về từ factory method.
- Bean name mặc định là `applicationClock`.
- `Clock` có thể được inject vào service.

`Clock` là abstraction của Java để đọc thời gian. Trong test, ta có thể thay bằng fixed clock để kết quả không phụ thuộc đồng hồ thật.

## 10. Tạo application service

`PlaceOrderService.java`:

```java
package com.example.orders.application;

import com.example.orders.domain.Order;
import com.example.orders.domain.OrderStatus;
import com.example.orders.port.OrderStore;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class PlaceOrderService {

    private final OrderStore orderStore;
    private final OrderPolicy orderPolicy;
    private final Clock clock;

    public PlaceOrderService(
            OrderStore orderStore,
            OrderPolicy orderPolicy,
            Clock clock) {
        this.orderStore = orderStore;
        this.orderPolicy = orderPolicy;
        this.clock = clock;
    }

    public Order place(String customerId, BigDecimal amount) {
        orderPolicy.validate(customerId, amount);

        Order order = new Order(
                UUID.randomUUID().toString(),
                customerId,
                amount,
                Instant.now(clock),
                OrderStatus.CREATED
        );

        return orderStore.save(order);
    }

    public Order findById(String id) {
        return orderStore.findById(id)
                .orElseThrow(() ->
                        new OrderNotFoundException(id)
                );
    }
}
```

Exception:

```java
package com.example.orders.application;

public class OrderNotFoundException extends RuntimeException {

    public OrderNotFoundException(String id) {
        super("Order not found: " + id);
    }
}
```

Service phụ thuộc vào ba collaborator qua constructor:

- `OrderStore`: persistence port.
- `OrderPolicy`: validation policy.
- `Clock`: nguồn thời gian.

Nó không tự tạo các collaborator bằng `new`. `UUID` và `Order` là value/data objects được tạo trong use case, không cần đăng ký thành Spring beans.

## 11. Tạo API request và response

`CreateOrderRequest.java`:

```java
package com.example.orders.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.math.BigDecimal;

public record CreateOrderRequest(
        @NotBlank String customerId,
        @NotNull @Positive BigDecimal amount
) {
}
```

Để dùng `@Valid` với Spring Boot, cần dependency validation phù hợp, thường là `spring-boot-starter-validation`.

`OrderResponse.java`:

```java
package com.example.orders.api;

import com.example.orders.domain.Order;
import java.math.BigDecimal;
import java.time.Instant;

public record OrderResponse(
        String id,
        String customerId,
        BigDecimal amount,
        Instant createdAt,
        String status
) {
    public static OrderResponse from(Order order) {
        return new OrderResponse(
                order.id(),
                order.customerId(),
                order.amount(),
                order.createdAt(),
                order.status().name()
        );
    }
}
```

Response DTO giúp API không phải expose trực tiếp mọi chi tiết domain object.

## 12. Tạo controller

`OrderController.java`:

```java
package com.example.orders.api;

import com.example.orders.application.PlaceOrderService;
import com.example.orders.domain.Order;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final PlaceOrderService placeOrderService;

    public OrderController(PlaceOrderService placeOrderService) {
        this.placeOrderService = placeOrderService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public OrderResponse create(
            @Valid @RequestBody CreateOrderRequest request) {

        Order order = placeOrderService.place(
                request.customerId(),
                request.amount()
        );

        return OrderResponse.from(order);
    }

    @GetMapping("/{id}")
    public OrderResponse findById(@PathVariable String id) {
        return OrderResponse.from(
                placeOrderService.findById(id)
        );
    }
}
```

Ở đây controller được đăng ký qua component scan nhờ `@RestController`. Nó nhận request, gọi application service và chuyển domain result thành response DTO.

### 12.1. Xử lý lỗi not found

Có thể thêm exception handler:

```java
package com.example.orders.api;

import com.example.orders.application.OrderNotFoundException;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public Map<String, String> handleNotFound(
            OrderNotFoundException exception) {

        return Map.of(
                "error", "ORDER_NOT_FOUND",
                "message", exception.getMessage()
        );
    }
}
```

Trong API thực tế, cần cân nhắc mức chi tiết của message để không lộ dữ liệu nội bộ. Ví dụ này dùng message không nhạy cảm.

## 13. Application class và phạm vi component scan

`OrderApplication.java`:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

Application class nằm ở `com.example.orders`, vì vậy component scan mặc định có thể tìm:

- `api.OrderController`.
- `api.ApiExceptionHandler`.
- `application.PlaceOrderService`.
- `application.OrderPolicy`.
- `infrastructure.InMemoryOrderStore`.
- `infrastructure.TimeConfiguration`.

`TimeConfiguration` cung cấp bean `Clock` qua Java configuration.

## 14. Đồ thị bean của ứng dụng mẫu

Từ constructor parameters và configuration, có thể vẽ:

```text
OrderController (@RestController)
        |
        v
PlaceOrderService (@Service)
        |
        +--------------------+
        |                    |
        v                    v
OrderPolicy (@Component)   OrderStore (interface)
                             ^
                             |
                    InMemoryOrderStore
                       (@Repository)

PlaceOrderService
        |
        v
Clock
  ^
  |
TimeConfiguration
  @Bean applicationClock()
```

### 14.1. Đọc graph theo chiều dependency

`PlaceOrderService` yêu cầu `OrderStore`, `OrderPolicy` và `Clock`. Spring tìm bean phù hợp theo type, qualifier, primary và các điều kiện đăng ký.

Trong cấu hình hiện tại:

- `OrderStore` có một implementation: `InMemoryOrderStore`.
- `OrderPolicy` có một component.
- `Clock` có một bean được tạo bởi `TimeConfiguration`.

Vì mỗi constructor dependency có đúng một ứng viên, Spring có thể tạo `PlaceOrderService`.

### 14.2. Bean graph không phải sơ đồ package

Package tree cho biết file nằm ở đâu. Bean graph cho biết object nào cần object nào. Hai sơ đồ trả lời câu hỏi khác nhau.

Ví dụ `TimeConfiguration` nằm trong package `infrastructure`, nhưng `PlaceOrderService` phụ thuộc `Clock`, không phụ thuộc trực tiếp `TimeConfiguration`.

### 14.3. Bean graph không phải object allocation graph đầy đủ

Graph tập trung vào Spring-managed dependencies. Những object như `Order`, `UUID`, `OrderResponse` được tạo trong method không nhất thiết là Spring beans và không cần xuất hiện trong bean graph.

## 15. Startup timeline của ứng dụng mẫu

Khi chạy:

```bash
java -jar order-service.jar
```

Spring Boot thực hiện một chuỗi bước khái quát:

```text
1. Java launcher tạo JVM
2. Gọi OrderApplication.main(args)
3. SpringApplication.run(...)
4. Chuẩn bị Environment và property sources
5. Tạo ApplicationContext
6. Đăng ký/đọc configuration và bean definitions
7. Component scan phát hiện stereotype classes
8. Xử lý @Bean methods trong TimeConfiguration
9. Refresh ApplicationContext
10. Resolve dependencies và tạo singleton beans eager
11. Khởi tạo bean, chạy callbacks và post-processors
12. Khởi động embedded web server
13. Phát ApplicationStartedEvent
14. Chạy ApplicationRunner / CommandLineRunner
15. Phát ApplicationReadyEvent
16. Readiness chuyển sang accepting traffic theo lifecycle
```

Một số hoạt động như auto-configuration, proxy creation và lifecycle component startup nằm trong quá trình refresh; danh sách trên là trình tự học tập ở mức khái niệm, không phải danh sách từng method nội bộ.

### 15.1. Context refresh

Đây là giai đoạn quan trọng khi Spring tạo các singleton beans không lazy và resolve dependency graph. Nếu constructor hoặc initialization callback của một bean bắt buộc thất bại, context refresh có thể thất bại và ứng dụng không đi tới trạng thái ready.

### 15.2. `ApplicationStartedEvent`

Event này được phát sau khi context đã refresh. Runners chưa được gọi ở thời điểm event này trong luồng Spring Boot thông thường.

### 15.3. Runners

`ApplicationRunner` nhận `ApplicationArguments`; `CommandLineRunner` nhận `String... args`.

Chúng thường dùng cho một số bước sau context refresh như validation hoặc khởi tạo cần thiết. Nếu runner ném exception không được xử lý, startup có thể thất bại và không phát `ApplicationReadyEvent` trong luồng thành công.

### 15.4. `ApplicationReadyEvent`

Event này biểu thị ứng dụng đã hoàn thành bước startup theo lifecycle Spring Boot và sẵn sàng phục vụ theo thiết kế. Nó không chứng minh mọi business workflow đều đúng hoặc mọi background task bất đồng bộ đã hoàn tất.

## 16. Quan sát startup events

Có thể đăng ký listener để ghi lại mốc lifecycle.

```java
package com.example.orders.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupEventLogger {

    private static final Logger log =
            LoggerFactory.getLogger(StartupEventLogger.class);

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        log.info("event=application.started");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        log.info("event=application.ready");
    }
}
```

Ví dụ log:

```text
INFO event=application.started
INFO event=application.ready
```

### 16.1. Ghi event có ý nghĩa

Log nên cho biết:

- Tên event hoặc lifecycle phase.
- Application/service name.
- Deployment version nếu có.
- Thời gian hoặc duration phù hợp.
- Instance identifier nếu cần phân biệt replica.

Không ghi password, token hoặc toàn bộ environment properties.

### 16.2. Đừng tự suy luận từ một dòng `Started ...`

Startup log format và vị trí log có thể khác theo phiên bản, listener và cấu hình. Nếu cần biết runners đã hoàn tất, dùng event/lifecycle signal phù hợp và kiểm tra log của runner.

### 16.3. Event ready không phải synthetic test

`ApplicationReadyEvent` là bằng chứng lifecycle. Nó không tự gửi HTTP request qua ingress, không kiểm tra authorization và không xác nhận order được lưu chính xác.

## 17. Kiểm tra bean graph bằng ApplicationContext

Trong test hoặc môi trường chẩn đoán nội bộ, có thể xem bean names theo type:

```java
String[] names =
        context.getBeanNamesForType(OrderStore.class);
```

Kết quả mong đợi trong ứng dụng mẫu:

```text
inMemoryOrderStore
```

Tương tự:

```java
String[] clocks =
        context.getBeanNamesForType(Clock.class);
```

Kết quả mong đợi:

```text
applicationClock
```

### 17.1. Kiểm tra bean count

```java
assertThat(context.getBeansOfType(OrderStore.class))
        .hasSize(1);
```

Điều này chứng minh context có đúng một bean thuộc type được kiểm tra trong context test cụ thể.

Nó không chứng minh method `save()` lưu đúng nghiệp vụ. Đó là một câu hỏi behavior khác.

### 17.2. Không expose bean inventory công khai tùy tiện

Danh sách bean names có thể tiết lộ module, vendor hoặc cấu trúc nội bộ. Dùng trong test hoặc endpoint nội bộ được bảo vệ khi cần; không đưa toàn bộ inventory vào API public.

## 18. Bằng chứng hành vi: chọn đúng cấp độ kiểm thử

Không có một test duy nhất chứng minh toàn bộ ứng dụng. Hãy chọn test theo phạm vi:

| Mức | Kiểm tra | Bằng chứng chính |
| --- | --- | --- |
| Unit test | Logic của một class | Input/output, exception, side effect qua fake/mock |
| Context test | Bean registration và wiring | Context tạo được, bean type/name đúng |
| Slice test | Một phần framework, ví dụ MVC | Routing, validation, serialization, controller behavior |
| Integration test | Tương tác giữa nhiều thành phần | Persistence, transaction, configuration |
| Contract test | API giữa hai module/service | Schema và semantics request/response |
| End-to-end test | User journey qua nhiều layer | Hành vi tổng hợp trong môi trường test |
| Synthetic monitoring | Một số journey lặp định kỳ trên runtime | Khả năng thực hiện flow cụ thể tại thời điểm đo |
| Production telemetry | Traffic thật theo thời gian | Availability, latency, errors, business outcomes |

Các mức này bổ sung cho nhau. Unit test nhanh và cô lập; E2E test gần hành vi người dùng hơn nhưng đắt hơn và phụ thuộc môi trường.

## 19. Unit test cho application service

`PlaceOrderService` có ba dependencies. Unit test có thể dùng fake `OrderStore`, `OrderPolicy` thật và fixed `Clock`.

### 19.1. Fake store

```java
class FakeOrderStore implements OrderStore {

    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public Order save(Order order) {
        orders.put(order.id(), order);
        return order;
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }
}
```

### 19.2. Test thành công

```java
class PlaceOrderServiceTest {

    private final FakeOrderStore store = new FakeOrderStore();

    private final Clock clock = Clock.fixed(
            Instant.parse("2026-01-15T10:00:00Z"),
            ZoneOffset.UTC
    );

    private final PlaceOrderService service =
            new PlaceOrderService(
                    store,
                    new OrderPolicy(),
                    clock
            );

    @Test
    void createsAndStoresAnOrder() {
        Order order = service.place(
                "customer-1",
                new BigDecimal("125000")
        );

        assertThat(order.id()).isNotBlank();
        assertThat(order.customerId()).isEqualTo("customer-1");
        assertThat(order.amount())
                .isEqualByComparingTo("125000");
        assertThat(order.createdAt())
                .isEqualTo(Instant.parse("2026-01-15T10:00:00Z"));
        assertThat(order.status()).isEqualTo(OrderStatus.CREATED);
        assertThat(store.findById(order.id())).contains(order);
    }
}
```

Test này cung cấp bằng chứng rằng với input đã chọn:

- Policy chấp nhận dữ liệu.
- Service tạo order với thời gian xác định.
- Store nhận và trả lại order.
- Status ban đầu là `CREATED`.

Nó không khởi tạo Spring context và không chứng minh component scan/`@Bean` wiring hoạt động.

### 19.3. Test validation

```java
@Test
void rejectsNonPositiveAmount() {
    assertThatThrownBy(() ->
            service.place(
                    "customer-1",
                    BigDecimal.ZERO
            )
    ).isInstanceOf(IllegalArgumentException.class)
     .hasMessage("Order amount must be positive");
}
```

Test này chứng minh quy tắc validation cụ thể. Nó không kiểm tra HTTP validation của request body; phần đó cần MVC test.

### 19.4. Vì sao dùng `Clock`?

Nếu service gọi `Instant.now()` trực tiếp, test phụ thuộc thời gian thực và khó assert chính xác. Inject `Clock` cho phép dùng `Clock.fixed(...)` trong test, trong khi production dùng `Clock.systemUTC()`.

Đây là ví dụ về dependency có ích để kiểm soát behavior.

## 20. Context test: chứng minh wiring

Unit test ở trên tự tạo service bằng `new`. Để chứng minh Spring có thể đăng ký và inject beans, cần khởi tạo context.

### 20.1. Test với `ApplicationContextRunner`

`ApplicationContextRunner` phù hợp cho một context nhỏ:

```java
class OrderWiringTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(OrderTestConfiguration.class);

    @Test
    void wiresOrderServiceAndItsDependencies() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(PlaceOrderService.class);
            assertThat(context).hasSingleBean(OrderStore.class);
            assertThat(context).hasSingleBean(Clock.class);
        });
    }

    @Configuration(proxyBeanMethods = false)
    @Import({
            PlaceOrderService.class,
            OrderPolicy.class,
            InMemoryOrderStore.class,
            TimeConfiguration.class
    })
    static class OrderTestConfiguration {
    }
}
```

Đây là skeleton test; cần imports cho Spring Boot test context runner, Spring `@Configuration`, `@Import`, JUnit 5 và AssertJ. Trong một project thực tế, cấu hình test có thể import đúng các configuration/component cần thiết.

### 20.2. Điều test này chứng minh

- Context nhỏ có thể refresh.
- Có đúng một bean `PlaceOrderService`.
- Có bean `OrderStore` và `Clock`.
- Constructor dependencies có thể được resolve.

### 20.3. Điều test này chưa chứng minh

- HTTP route `/api/orders` được đăng ký.
- JSON request được deserialize.
- Bean validation hoạt động.
- Error mapping trả status đúng.
- Một request qua web server thật được xử lý.

Đó là các tầng khác.

## 21. Full application context test

`@SpringBootTest` khởi tạo application context của ứng dụng theo cấu hình test.

```java
@SpringBootTest
class OrderApplicationContextTest {

    @Autowired
    PlaceOrderService placeOrderService;

    @Autowired
    OrderStore orderStore;

    @Test
    void applicationWiresOrderUseCase() {
        Order order = placeOrderService.place(
                "customer-2",
                new BigDecimal("50000")
        );

        assertThat(orderStore.findById(order.id()))
                .contains(order);
    }
}
```

Test này kiểm tra wiring qua context thật của application và một luồng service/store.

### 21.1. Lợi ích

- Phát hiện component scan sai.
- Phát hiện thiếu bean hoặc nhiều bean ambiguity.
- Phát hiện configuration không được import.
- Phát hiện một số lỗi auto-configuration và property binding.

### 21.2. Chi phí

Full context test thường chậm hơn unit test và có thể cần database, broker hoặc service giả lập tùy ứng dụng. Không cần dùng nó cho mọi quy tắc nghiệp vụ nhỏ.

## 22. MVC slice test: chứng minh HTTP contract

`@WebMvcTest` tập trung vào Spring MVC layer. Có thể dùng `@MockBean` hoặc cơ chế mock bean phù hợp với Spring Boot version để thay application service.

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    PlaceOrderService placeOrderService;

    @Test
    void createsOrderAndReturnsCreated() throws Exception {
        Order order = new Order(
                "order-1",
                "customer-1",
                new BigDecimal("125000"),
                Instant.parse("2026-01-15T10:00:00Z"),
                OrderStatus.CREATED
        );

        given(placeOrderService.place(
                "customer-1",
                new BigDecimal("125000")
        )).willReturn(order);

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerId": "customer-1",
                                  "amount": 125000
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("order-1"))
                .andExpect(jsonPath("$.customerId").value("customer-1"))
                .andExpect(jsonPath("$.status").value("CREATED"));
    }
}
```

Test cần các imports Mockito BDD, MockMvc request builders, `MediaType`, `jsonPath`, JUnit 5 và Spring test annotations. Tên annotation mock bean có thể thay đổi giữa các Spring Boot generations; dùng API tương thích version project.

### 22.1. Test validation HTTP

Nếu request thiếu `customerId` hoặc amount không hợp lệ, MVC validation có thể trả 400 khi:

- Có dependency validation.
- Controller dùng `@Valid`.
- Request model có constraints.
- MVC validation infrastructure được cấu hình.

Ví dụ:

```java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "customerId": "",
                  "amount": 0
                }
                """))
        .andExpect(status().isBadRequest());
```

Đây là bằng chứng cho request validation và HTTP response trong MVC slice test.

### 22.2. Mock service làm test có giới hạn

Vì service được mock, test này không chứng minh `PlaceOrderService` lưu order. Nó chỉ chứng minh controller gọi service theo input và ánh xạ kết quả thành response.

Để chứng minh persistence flow, cần integration test hoặc full context test với store phù hợp.

## 23. Integration test: chứng minh các thành phần phối hợp

Integration test kết hợp nhiều thành phần thật:

```text
MockMvc / HTTP client
       |
       v
OrderController
       |
       v
PlaceOrderService
       |
       +--> OrderPolicy
       |
       +--> OrderStore adapter
       |
       v
Response
```

Với ví dụ in-memory, có thể khởi tạo full context và gọi service/controller. Với persistence thật, thay `InMemoryOrderStore` bằng adapter JPA và database test.

### 23.1. Khi dùng `@DataJpaTest`

Nếu ứng dụng có JPA adapter, `@DataJpaTest` tập trung kiểm tra entity mapping, repository và database interactions. Nó không load toàn bộ web/application layer.

### 23.2. Khi dùng Testcontainers

Nếu cần xác nhận hành vi với đúng loại database, Testcontainers có thể khởi chạy database container cho integration tests. Test đó cung cấp bằng chứng gần môi trường hơn H2 khi khác biệt SQL dialect/schema có ý nghĩa.

### 23.3. Kiểm tra transaction và constraints

Integration tests có thể kiểm tra:

- Unique constraints.
- Foreign keys.
- Transaction rollback.
- Mapping.
- Query behavior.
- Concurrency semantics cần thiết.

Một unit test với fake map không chứng minh những điều này.

## 24. End-to-end test: chứng minh luồng qua nhiều layer

E2E test kiểm tra một hành trình gần với cách client sử dụng ứng dụng:

```text
HTTP POST /api/orders
        |
        v
Request parsing / validation
        |
        v
Controller
        |
        v
Application service
        |
        v
Persistence adapter
        |
        v
HTTP 201 + response body
        |
        v
HTTP GET /api/orders/{id}
        |
        v
HTTP 200 + stored order
```

Một E2E test có thể:

1. Khởi động ứng dụng với môi trường test.
2. Gửi POST tạo đơn.
3. Đọc `id` từ response.
4. Gửi GET với `id`.
5. So sánh dữ liệu trả về với dữ liệu đã gửi.

### 24.1. Điều E2E test chứng minh

Với môi trường và input cụ thể, các thành phần được đi qua trong test phối hợp để thực hiện hành vi mong đợi.

### 24.2. Điều E2E test chưa chứng minh

- Mọi input đều hợp lệ.
- Mọi role/tenant đều hoạt động.
- Hệ thống chịu được tải production.
- Mọi replica đều giống nhau.
- Không có lỗi hiếm hoặc lỗi phụ thuộc thời gian.

E2E test là bằng chứng mạnh cho một flow cụ thể, không phải chứng minh tổng quát mọi behavior.

## 25. Bằng chứng từ log

Log giúp tái dựng sự kiện theo thời gian. Trong ứng dụng mẫu, có thể ghi log ở ranh giới use case:

```java
log.info(
        "event=order.created orderId={} customerId={}",
        order.id(),
        order.customerId()
);
```

Trong môi trường thật, cân nhắc việc customer ID có được phép ghi log hay không. Có thể dùng reference đã được pseudonymize hoặc một correlation identifier an toàn.

### 25.1. Log chứng minh điều gì?

Một log event đáng tin cậy có thể cho biết code đã đi qua một điểm và ghi nhận dữ liệu tại thời điểm đó.

Ví dụ:

```text
event=order.created orderId=... traceId=...
```

Nó không tự chứng minh dữ liệu đã commit bền vững nếu log được ghi trước transaction commit hoặc store chỉ là in-memory.

### 25.2. Đặt log ở đúng thời điểm

Nếu cần ghi nhận kết quả đã commit, đặt event ở vị trí phù hợp với transaction boundary hoặc dùng cơ chế after-commit event. Log trước commit có thể tồn tại dù transaction sau đó rollback.

### 25.3. Không log toàn bộ request

Tránh ghi:

- Password.
- Access token.
- Payment credentials.
- Raw personal data không cần thiết.
- Toàn bộ request/response body nếu chứa dữ liệu nhạy cảm.

Log nên ghi event, outcome, duration, error code và correlation ID cần thiết.

## 26. Bằng chứng từ metrics

Metrics mô tả số liệu được tổng hợp theo thời gian.

Các metric hữu ích cho Order API:

- Request count theo route và status.
- Error count theo failure category.
- Request latency histogram.
- Số đơn tạo thành công.
- Tỷ lệ tạo đơn thất bại theo nguyên nhân.
- Số request đang xử lý.

Ví dụ với Micrometer:

```java
@Service
public class OrderMetrics {

    private final Counter createdOrders;

    public OrderMetrics(MeterRegistry registry) {
        this.createdOrders = Counter.builder("orders.created")
                .description("Number of orders created")
                .register(registry);
    }

    public void recordCreated() {
        createdOrders.increment();
    }
}
```

Service có thể gọi `recordCreated()` sau khi store trả kết quả thành công theo semantics mong muốn.

### 26.1. Chọn thời điểm tăng counter

Nếu tăng counter trước khi persistence hoàn tất, số liệu có thể đếm cả đơn thất bại. Hãy xác định metric đang đo:

- Request được nhận.
- Validation thành công.
- Lệnh ghi được gọi.
- Giao dịch commit.
- Đơn hàng được xác nhận.

Tên metric và vị trí instrument phải phản ánh đúng sự kiện.

### 26.2. Không dùng ID làm metric tag

Không thêm `orderId`, `customerId` hoặc request ID làm label/tag của metric. Những giá trị có cardinality cao làm tăng chi phí lưu trữ và có thể gây vấn đề vận hành.

Dùng metric tags có tập giá trị nhỏ như route, outcome hoặc error category đã chuẩn hóa.

## 27. Bằng chứng từ tracing

Distributed tracing cho thấy một request đã đi qua các span nào và thời gian ở từng đoạn.

Ví dụ:

```text
HTTP POST /api/orders
    |
    +--> OrderController.create
            |
            +--> PlaceOrderService.place
                    |
                    +--> OrderPolicy.validate
                    |
                    +--> OrderStore.save
```

Nếu persistence là remote hoặc database, trace có thể cho biết span tương ứng chậm hoặc lỗi.

### 27.1. Trace giúp tìm vị trí, không tự chứng minh business correctness

Một trace có status OK có thể vẫn đi cùng response sai nếu code không phát hiện logic bug.

Ví dụ:

```text
HTTP status = 201
trace status = OK
order amount = 0
```

Nếu amount bằng 0 vi phạm nghiệp vụ nhưng không có validation, trace vẫn có thể hoàn tất bình thường.

Cần kết hợp assertions và business invariants.

### 27.2. Correlation giữa logs và traces

Khi có trace ID, log của controller, service và adapter có thể được liên kết với cùng request. Điều này giúp điều tra một giao dịch cụ thể mà không cần log raw payload.

## 28. Health check và readiness trong bức tranh evidence

Spring Boot Actuator có thể cung cấp:

```text
/actuator/health
/actuator/health/liveness
/actuator/health/readiness
```

Các endpoint và cấu hình probes phụ thuộc version và thiết lập ứng dụng.

### 28.1. Health UP chứng minh điều gì?

Health status phản ánh các contributors trong health group theo aggregation policy. Nó không mặc định chạy mọi controller hoặc business use case.

### 28.2. Readiness UP chứng minh điều gì?

Readiness cho biết instance hiện được đánh giá là có thể nhận traffic theo các điều kiện đã cấu hình. Nó không chứng minh request tiếp theo chắc chắn thành công.

### 28.3. Liveness UP chứng minh điều gì?

Liveness cho biết instance đáp ứng tiêu chí còn khả năng vận hành theo chính sách liveness. Nó không nên phụ thuộc bừa bãi vào mọi remote dependency, vì điều đó có thể tạo restart storm khi một dependency dùng chung gặp sự cố.

### 28.4. Không dùng health check làm thay thế E2E

Health probe cần nhanh, an toàn và có thể gọi lặp lại. Business workflow sâu cần test/synthetic riêng với dữ liệu kiểm soát và không gây side effects không mong muốn.

## 29. Bảng tổng hợp: câu hỏi nào cần bằng chứng nào?

| Câu hỏi | Bằng chứng ưu tiên | Kết luận có thể đưa ra |
| --- | --- | --- |
| JVM đã chạy? | Process/container state | Process tồn tại tại thời điểm quan sát |
| Context đã refresh? | Startup event/context test | Context đi qua mốc refresh |
| Runners đã hoàn tất? | `ApplicationReadyEvent` và runner outcomes | Startup lifecycle thành công theo runners |
| Bean được wiring đúng? | Context test, bean type assertions | Context resolve đúng dependencies trong test |
| Logic tính toán đúng? | Unit test với expected values | Quy tắc cụ thể pass với input đã thử |
| HTTP route đúng? | MVC test/MockMvc | Routing, validation và response contract được kiểm tra |
| Persistence đúng? | Integration test với database | Mapping/query/transaction được kiểm tra trong môi trường test |
| User journey đúng? | E2E/synthetic | Flow cụ thể hoàn tất theo điều kiện test |
| Người dùng production có lỗi? | Metrics, logs, traces, business events | Hành vi thực tế trong cửa sổ quan sát |
| Instance nên nhận traffic? | Readiness probe | Instance pass các readiness conditions đã định nghĩa |
| Service có đáng tin cậy theo thời gian? | SLI/SLO và lịch sử metrics | Chất lượng phục vụ theo định nghĩa và cửa sổ đo |

## 30. Thực hành chạy ứng dụng

Sau khi hoàn thiện các class, chạy project bằng Gradle hoặc Maven theo cấu hình hiện có.

Ví dụ Gradle:

```bash
./gradlew bootRun
```

Hoặc build executable JAR:

```bash
./gradlew bootJar
java -jar build/libs/order-service.jar
```

Tên JAR thực tế phụ thuộc `project.name`, version và cấu hình archive.

### 30.1. Tạo order

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customerId":"customer-1","amount":125000}'
```

Response minh họa:

```http
HTTP/1.1 201
Content-Type: application/json
```

```json
{
  "id": "generated-order-id",
  "customerId": "customer-1",
  "amount": 125000,
  "createdAt": "2026-01-15T10:00:00Z",
  "status": "CREATED"
}
```

Thời điểm thực tế được lấy từ `Clock.systemUTC()` nên response thực tế sẽ phản ánh thời gian chạy, không phải timestamp cố định trong ví dụ.

### 30.2. Đọc order vừa tạo

```bash
curl -i http://localhost:8080/api/orders/<order-id>
```

Thay `<order-id>` bằng ID thực tế từ response POST.

### 30.3. Kiểm tra input sai

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customerId":"","amount":0}'
```

Với validation dependency và `@Valid` được cấu hình đúng, request có thể bị từ chối ở MVC layer trước khi gọi service.

Nếu validation không được bật, service policy vẫn có thể từ chối dữ liệu khi method được gọi. Hai tầng kiểm tra có mục đích khác nhau.

## 31. Một deployment có thể startup thành công nhưng behavior vẫn sai

Xem các tình huống:

### Tình huống A — Sai implementation được inject

Hai bean cùng implement `OrderStore`, nhưng qualifier/primary chọn nhầm adapter. Context vẫn có thể khởi động nếu wiring hợp lệ; dữ liệu được lưu vào nơi không mong muốn.

**Bằng chứng cần:** context assertions về bean lựa chọn, configuration test và integration test xác nhận persistence target.

### Tình huống B — Service logic sai

`PlaceOrderService` tạo order nhưng gán sai amount hoặc status.

**Bằng chứng cần:** unit test với expected values và business invariants.

### Tình huống C — HTTP mapping sai

Service hoạt động đúng nhưng controller trả 200 thay vì 201 hoặc serialize sai field.

**Bằng chứng cần:** MVC test hoặc HTTP integration test.

### Tình huống D — Persistence không bền vững

In-memory store trả order đúng nhưng dữ liệu mất sau restart.

**Bằng chứng cần:** integration test với persistence thật và kiểm tra sau khi mở lại transaction/context/process phù hợp.

### Tình huống E — Runtime degradation

Một replica có thread pool cạn hoặc database latency cao dù readiness vẫn UP.

**Bằng chứng cần:** metrics theo route, traces, pool metrics và request outcomes.

### Tình huống F — Startup log cũ

Log `Started ...` thuộc pod trước rollout, trong khi pod mới đang crash loop.

**Bằng chứng cần:** timestamp, instance ID, restart count và trạng thái hiện tại của đúng replica.

## 32. Cách lập một evidence package cho thay đổi

Khi review một thay đổi trong Spring Boot, có thể gom bằng chứng theo bốn phần:

### 32.1. Startup evidence

- Application context khởi động được.
- Profile và cấu hình quan trọng đúng.
- Runners bắt buộc hoàn tất.
- Readiness chuyển sang accepting theo policy.

### 32.2. Wiring evidence

- Bean definitions cần thiết tồn tại.
- Dependency được resolve đúng.
- Không có bean ambiguity ngoài ý muốn.
- Implementation được chọn đúng theo profile/property.

### 32.3. Behavior evidence

- Unit tests cho quy tắc nghiệp vụ.
- MVC tests cho HTTP contract.
- Integration tests cho persistence và transaction.
- E2E tests cho user journey quan trọng.

### 32.4. Runtime evidence

- Request rate/error rate/latency.
- Dependency health và resource pool metrics.
- Structured logs có correlation.
- Traces cho request chậm/lỗi.
- Synthetic checks và business outcome metrics.

Không cần chạy mọi loại test cho mọi thay đổi nhỏ. Hãy chọn evidence theo vùng code và rủi ro mà thay đổi ảnh hưởng.

## 33. Đọc một lỗi từ startup đến behavior

Giả sử deployment mới có:

```text
INFO  event=application.started
INFO  event=application.ready
INFO  readiness=UP
```

Nhưng POST order trả 500.

Một quy trình điều tra:

1. Xác nhận log thuộc đúng instance và version.
2. Xem controller/service exception theo trace ID.
3. Kiểm tra bean implementation được inject cho `OrderStore`.
4. Xem lỗi ở policy, store adapter hay dependency ngoài.
5. Đối chiếu input và expected business result.
6. Tạo test tái hiện ở đúng tầng.
7. Sửa nguyên nhân và bổ sung test để ngăn tái diễn.

Không cần kết luận startup log sai. Startup có thể thành công trong khi behavior request gặp lỗi runtime; đó là hai kết luận thuộc hai phạm vi khác nhau.

## 34. Chẩn đoán lỗi wiring từ bean graph

Nếu startup fail:

```text
No qualifying bean of type 'OrderStore'
```

Kiểm tra:

- `InMemoryOrderStore` có stereotype không?
- Package có nằm trong component scan không?
- Có profile/condition nào loại bean không?
- Có configuration đăng ký adapter khác không?
- Có lỗi constructor/init khiến bean không tạo được không?

Nếu lỗi:

```text
NoUniqueBeanDefinitionException
```

Kiểm tra các bean names:

```java
context.getBeanNamesForType(OrderStore.class)
```

Sau đó:

- Bỏ registration trùng nếu không cần.
- Dùng `@Qualifier` nếu có nhiều adapter có vai trò khác nhau.
- Dùng `@Primary` khi thật sự có một implementation mặc định.
- Xác định profile/condition rõ ràng.

### 34.1. Bean graph có thể được vẽ từ constructor

Ví dụ:

```java
public PlaceOrderService(
        OrderStore orderStore,
        OrderPolicy orderPolicy,
        Clock clock) {
}
```

Đọc constructor là cách nhanh để biết dependency bắt buộc của service. Với `@Bean` method, đọc các method parameters để thấy dependencies của bean được tạo.

## 35. Những sai lầm khi đọc sơ đồ

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| Xem package tree như bean graph | Package tree chỉ mô tả vị trí file |
| Xem bean graph như call graph | Dependency được inject không có nghĩa mọi method đều được gọi |
| Xem `Started ...` là bằng chứng mọi runner hoàn tất | Dùng lifecycle events và runner outcomes |
| Xem `ApplicationReadyEvent` là E2E pass | Event chỉ phản ánh startup lifecycle |
| Xem health `UP` là mọi API đúng | Health chỉ đánh giá contributors trong group |
| Xem unit test pass là Spring wiring đúng | Unit test có thể không khởi tạo context |
| Xem context test pass là database transaction đúng | Cần integration test cho persistence behavior |
| Xem HTTP 201 là order đã được lưu bền vững | Cần xác nhận adapter/storage semantics |
| Xem trace OK là business result đúng | Cần expected values và invariants |
| Xem một replica khỏe là cả deployment khỏe | Quan sát từng instance/version/zone khi cần |

## 36. Bài tập thực hành

### Bài 1 — Vẽ startup timeline

Vẽ timeline từ `SpringApplication.run()` đến `ApplicationReadyEvent`.

Đánh dấu:

- Environment preparation.
- Context refresh.
- Singleton creation.
- ApplicationStartedEvent.
- ApplicationRunner.
- ApplicationReadyEvent.

Giải thích một runner ném exception ảnh hưởng thế nào tới trạng thái startup.

### Bài 2 — Vẽ bean dependency graph

Với `OrderController`, `PlaceOrderService`, `OrderPolicy`, `OrderStore`, `InMemoryOrderStore` và `Clock`, vẽ dependency graph.

Phân biệt bean được component scan với bean được tạo bởi `@Bean`.

### Bài 3 — Vẽ runtime call graph

Với `POST /api/orders`, vẽ thứ tự method được gọi từ controller đến store.

Nêu object nào là Spring bean và object nào là dữ liệu được tạo trong method.

### Bài 4 — Thay implementation

Tạo một `JpaOrderStore` hoặc fake adapter khác implement `OrderStore`.

Chọn implementation bằng profile hoặc condition. Xác nhận context chỉ có implementation phù hợp.

### Bài 5 — Unit test service

Viết fake store và fixed clock. Kiểm tra:

- Order ID không rỗng.
- Customer ID đúng.
- Amount đúng.
- Created time đúng.
- Status đúng.
- Order có thể được đọc lại từ fake store.

### Bài 6 — Test validation

Kiểm tra customer ID rỗng, amount null và amount bằng 0.

Assert đúng exception và message/contract mà application quy định.

### Bài 7 — Context wiring test

Dùng `ApplicationContextRunner` để xác nhận có đúng một `OrderStore`, một `Clock` và một `PlaceOrderService`.

Sau đó cố ý đăng ký thêm adapter thứ hai và quan sát ambiguity.

### Bài 8 — MVC test

Dùng `@WebMvcTest` và `MockMvc` để kiểm tra:

- POST hợp lệ trả 201.
- Response JSON có field đúng.
- Input không hợp lệ trả 400.
- GET order trả 200 khi service tìm thấy.

Nhớ rằng service mock không chứng minh persistence thật.

### Bài 9 — Full context test

Dùng `@SpringBootTest` để tạo order qua service được Spring inject và đọc lại từ store bean.

Giải thích test này bao phủ điều gì mà unit test không bao phủ.

### Bài 10 — Integration test với database

Thay in-memory adapter bằng JPA adapter và database test.

Kiểm tra mapping, transaction, unique constraint và dữ liệu vẫn tồn tại sau khi kết thúc transaction.

### Bài 11 — Startup event test

Ghi nhận `ApplicationStartedEvent` và `ApplicationReadyEvent`.

Thêm runner thành công rồi runner thất bại. Quan sát event nào được phát trong từng trường hợp.

### Bài 12 — Kiểm tra readiness

Bật Actuator probes theo Spring Boot version của project.

Quan sát liveness/readiness và giải thích tại sao readiness UP không chứng minh POST order thành công.

### Bài 13 — Structured logging

Thêm log event khi order được tạo và khi validation thất bại.

Gắn correlation/trace ID phù hợp. Không log raw request body hoặc secret.

### Bài 14 — Metrics

Tạo counter cho số order được xác nhận và timer cho thời gian xử lý.

Xác định rõ thời điểm increment và cách tránh high-cardinality tags.

### Bài 15 — Trace một request

Bật tracing/instrumentation phù hợp với stack hiện tại.

Gửi POST order và xác định các span từ HTTP tới application service và persistence adapter.

Giải thích vì sao trace hoàn tất không tự chứng minh amount đúng.

### Bài 16 — Điều tra deployment giả định

Cho:

```text
ApplicationReadyEvent: present
Readiness: UP
POST /api/orders: 500
```

Lập danh sách bằng chứng cần thu thập từ đúng instance, logs, traces, metrics, bean wiring và test tái hiện.

### Bài 17 — Tạo evidence package

Với một thay đổi ở `PlaceOrderService`, chọn test cần chạy và runtime signals cần theo dõi.

Giải thích vì sao không cần chạy mọi E2E test nếu thay đổi chỉ ảnh hưởng một quy tắc nội bộ, nhưng vẫn phải có bằng chứng tương xứng với rủi ro.

### Bài 18 — Review sơ đồ

Một tài liệu chỉ có package tree và startup log. Hãy bổ sung:

- Startup timeline.
- Bean dependency graph.
- Runtime call graph.
- Test evidence.
- Runtime telemetry.

Đánh dấu rõ kết luận nào được hỗ trợ bởi từng loại bằng chứng.

## 37. Ghi nhớ

Một ứng dụng Spring Boot có thể được hiểu rõ hơn khi nhìn qua ba mô hình: **startup timeline** cho biết lifecycle đã đi qua những mốc nào; **bean dependency graph** cho biết Spring lắp ghép object ra sao; **runtime call graph** cho biết một use case thực sự gọi những thành phần nào.

Mỗi mô hình cần bằng chứng riêng. Events và startup logs giúp xác nhận các mốc lifecycle. Context tests giúp xác nhận bean registration và dependency wiring. Unit tests chứng minh quy tắc cụ thể; MVC tests chứng minh HTTP contract; integration và E2E tests kiểm tra các thành phần phối hợp. Logs, metrics và traces cung cấp góc nhìn về hành vi runtime, còn health/readiness hỗ trợ quyết định vận hành instance.

Đừng dùng một dòng `Started ...`, một bean inventory, một HTTP 200 hoặc một health `UP` để kết luận toàn bộ ứng dụng hoạt động đúng. Hãy mô tả rõ input, điều kiện, hành vi mong đợi, phép kiểm tra đã chạy và giới hạn của kết quả. **Bằng chứng tốt là bằng chứng gắn trực tiếp với câu hỏi cần trả lời và có thể tái hiện hoặc quan sát lại.**
