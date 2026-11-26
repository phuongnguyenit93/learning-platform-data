# Dự án thực hành: Bootstrap module với collaborator được thay thế

> **Chủ đề:** Spring Modulith Verification & Testing — kiểm chứng module bằng `ApplicationModules`, khởi tạo một module qua `@ApplicationModuleTest` và thay collaborator nằm ngoài ranh giới module để kiểm thử độc lập.

## 1. Bối cảnh, mục tiêu và kết quả cần đạt

Một ứng dụng bán hàng dạng modular monolith có hai application module: `orders` tiếp nhận đơn hàng và `stock` quản lý tồn kho. Khi tạo đơn, `orders` cần hỏi `stock` có thể giữ số lượng hàng yêu cầu hay không. Nếu chạy cả ứng dụng để kiểm thử `orders`, bài test vô tình phụ thuộc vào cấu hình và trạng thái của `stock`. Ta cần **bootstrap riêng `orders`**, thay collaborator `StockGateway` bằng một mock kiểm soát được và vẫn dùng **Spring Context thật, transaction thật, repository JPA thật** của `orders`.

Đây là một lát cắt trong kỹ năng *Spring Modulith Verification & Testing*: vừa kiểm chứng ranh giới kiến trúc và quy tắc phụ thuộc giữa module, vừa dùng `@ApplicationModuleTest`, sự kiện ứng dụng, cơ sở dữ liệu và quality gate trong CI để ngăn phụ thuộc sai và hồi quy.

**Sau bài thực hành, bạn có thể:**

1. Tách API công khai của module `stock` khỏi phần triển khai nội bộ và khai báo `allowedDependencies` của `orders`.
2. Dùng `ApplicationModules.of(...).verify()` phát hiện truy cập vào package nội bộ, phụ thuộc không được cho phép hoặc chu trình module.
3. Giải thích vì sao `@ApplicationModuleTest(mode = STANDALONE)` thất bại khi còn thiếu một bean collaborator bên ngoài module.
4. Dùng `@MockitoBean` để cung cấp collaborator có hành vi xác định và khởi tạo thành công đúng module đích.
5. Xác nhận cả nhánh thành công và từ chối: số lần gọi collaborator, bản ghi trong H2/JPA và sự kiện `OrderPlaced`.
6. Đặt kiểm chứng kiến trúc cùng module integration tests vào quality gate của CI.

**Tiêu chí nghiệm thu:** test `orders` chạy ở chế độ `STANDALONE` khi có mock; bỏ mock thì context không tạo được do thiếu `StockGateway`; luồng hợp lệ ghi đúng một đơn và phát đúng một sự kiện; luồng hết hàng không ghi đơn và không phát sự kiện; bài kiểm chứng kiến trúc chạy thành công.

## 2. Ranh giới kiến trúc và hợp đồng nghiệp vụ

```mermaid
flowchart LR
    Test[OrderModuleTest] -->|bootstrap STANDALONE| Orders[orders module]
    Orders -->|chỉ tham chiếu public API| Gateway[stock.StockGateway]
    Gateway -. runtime thực tế .-> Stock[stock.internal.DemoStockGateway]
    Test -->|@MockitoBean thay collaborator| Mock[Mock StockGateway]
    Mock -. bean dùng trong test .-> Orders
    Orders --> Repo[(orders JPA repository)]
    Orders --> Event[OrderPlaced event]
```

Với class khởi động đặt tại `dev.example.shop.ShopApplication`, Spring Modulith mặc định nhận các package con trực tiếp `dev.example.shop.orders` và `dev.example.shop.stock` làm application module. Public type nằm ở **package gốc của module** là API mặc định; package `internal` là phần triển khai không được module khác gọi trực tiếp. `orders` chỉ được phép phụ thuộc vào `stock` qua hợp đồng `StockGateway`.

| Thành phần | Thuộc module | Vai trò khi chạy `STANDALONE` |
| --- | --- | --- |
| `OrderService`, `OrderRepository`, `OrderEntity` | `orders.internal` | Có bean/repository/entity thực tế, xử lý nghiệp vụ và lưu H2 |
| `OrderPlaced` | `orders` | Sự kiện công khai để kiểm tra hành vi sau khi tạo đơn |
| `StockGateway` | `stock` | Kiểu API mà `orders` được phép phụ thuộc ở mức mã nguồn |
| `DemoStockGateway` | `stock.internal` | Bean triển khai thực, không được scan khi test riêng `orders` |
| `@MockitoBean StockGateway` | test của `orders` | Cung cấp bean thay thế trong context và cho phép định nghĩa kết quả từng trường hợp |

Phân biệt hai lớp bảo vệ: **kiểm chứng cấu trúc** (`ApplicationModules.verify()`) xét quan hệ giữa các kiểu Java; **module integration test** (`@ApplicationModuleTest`) giới hạn bean/entity/repository được khởi tạo và kiểm tra hành vi trong runtime. Mock giúp dựng context, nhưng không khiến một phụ thuộc kiến trúc sai trở thành hợp lệ.

## 3. Tạo project và khai báo dependency

Ví dụ dùng **Java 21, Spring Boot 3.5.x, Spring Modulith 1.4.x, JUnit 5, Mockito, Spring Data JPA và H2**. Đây là một cặp phiên bản tương thích; dự án đã có BOM riêng thì dùng phiên bản được quản lý thống nhất, không phối trộn nhánh Spring Boot 4.x với Modulith 1.4.x.

`build.gradle` (Gradle Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain { languageVersion = JavaLanguageVersion.of(21) }
}

repositories { mavenCentral() }

dependencyManagement {
    imports {
        mavenBom 'org.springframework.modulith:spring-modulith-bom:1.4.13'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.modulith:spring-modulith-starter-core'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
}

tasks.named('test') { useJUnitPlatform() }
```

Trong `src/test/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:modulith-orders;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.springframework.modulith=DEBUG
```

`create-drop` chỉ dành cho môi trường test/demo; ở môi trường thực dùng migration (Flyway/Liquibase) và một database phù hợp. Bài tập này kiểm tra được database integration bằng H2, nhưng **không thay thế** kiểm thử riêng với database sản xuất nếu khác biệt dialect, isolation hoặc transaction là quan trọng.

## 4. Bố trí package và điểm khởi động

Tạo cấu trúc sau (mỗi tên `.java` là một file; các đoạn mã ở những mục tiếp theo tương ứng đúng tên file):

```text
src/
├── main/java/dev/example/shop/
│   ├── ShopApplication.java
│   ├── orders/
│   │   ├── package-info.java
│   │   ├── OrderPlaced.java
│   │   └── internal/
│   │       ├── OrderEntity.java
│   │       ├── OrderRepository.java
│   │       └── OrderService.java
│   └── stock/
│       ├── StockGateway.java
│       └── internal/DemoStockGateway.java
├── test/java/dev/example/shop/
│   ├── ArchitectureVerificationTest.java
│   └── orders/internal/OrderModuleTest.java
└── test/resources/application.properties
```

`ShopApplication.java`:

```java
package dev.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

`orders/package-info.java` khai báo rằng module này chỉ phụ thuộc vào `stock`:

```java
@org.springframework.modulith.ApplicationModule(allowedDependencies = "stock")
package dev.example.shop.orders;
```

Không đặt `ShopApplication` bên trong `orders`: Spring Modulith xác định các module dựa trên các package con của package ứng dụng chính. Test `orders` được đặt trong `orders.internal` để có quyền gọi các class package-private trong chính module mà vẫn được `@ApplicationModuleTest` nhận diện là test của `orders`.

## 5. Xây collaborator thuộc module `stock`

`stock/StockGateway.java` là giao diện công khai duy nhất mà `orders` cần biết:

```java
package dev.example.shop.stock;

public interface StockGateway {
    boolean reserve(String sku, int quantity);
}
```

Để ứng dụng mẫu có thể khởi động khi chạy đầy đủ, bổ sung `stock/internal/DemoStockGateway.java`:

```java
package dev.example.shop.stock.internal;

import dev.example.shop.stock.StockGateway;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
class DemoStockGateway implements StockGateway {
    private final Map<String, Integer> available =
            new ConcurrentHashMap<>(Map.of("PEN-01", 10));

    @Override
    public synchronized boolean reserve(String sku, int quantity) {
        int current = available.getOrDefault(sku, 0);
        if (quantity <= 0 || current < quantity) {
            return false;
        }
        available.put(sku, current - quantity);
        return true;
    }
}
```

Đây là adapter **demo trong bộ nhớ**, không phải thiết kế tồn kho production: nó không tham gia transaction của database đơn hàng và không có cơ chế bù trừ nếu lưu đơn thất bại. Trong hệ thống thật cần giữ tồn kho bằng giao dịch/điều kiện cập nhật nguyên tử hoặc thiết kế reservation/compensation phù hợp. Đối với bài này, `orders` chỉ thấy `StockGateway`; implementation nằm trong `stock.internal` và **không được đưa vào** context của test `STANDALONE`.

## 6. Cài đặt luồng tạo đơn, lưu trữ và phát sự kiện

`orders/OrderPlaced.java` là event thuộc API module:

```java
package dev.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId, String sku, int quantity) {}
```

`orders/internal/OrderEntity.java`:

```java
package dev.example.shop.orders.internal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.util.UUID;

@Entity
@Table(name = "purchase_orders")
class OrderEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected OrderEntity() {} // JPA yêu cầu constructor không đối số

    OrderEntity(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    UUID id() { return id; }
    String sku() { return sku; }
    int quantity() { return quantity; }
}
```

`orders/internal/OrderRepository.java`:

```java
package dev.example.shop.orders.internal;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.UUID;

interface OrderRepository extends JpaRepository<OrderEntity, UUID> {}
```

`orders/internal/OrderService.java`:

```java
package dev.example.shop.orders.internal;

import dev.example.shop.orders.OrderPlaced;
import dev.example.shop.stock.StockGateway;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
class OrderService {
    private final StockGateway stock;
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    OrderService(StockGateway stock, OrderRepository orders,
                 ApplicationEventPublisher events) {
        this.stock = stock;
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public UUID place(String sku, int quantity) {
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("INVALID_ORDER");
        }
        if (!stock.reserve(sku, quantity)) {
            throw new IllegalStateException("OUT_OF_STOCK");
        }

        OrderEntity saved = orders.save(new OrderEntity(sku, quantity));
        events.publishEvent(new OrderPlaced(saved.id(), sku, quantity));
        return saved.id();
    }
}
```

Luồng thành công: kiểm tra input → gọi collaborator `stock.reserve` → lưu `OrderEntity` bằng JPA → phát `OrderPlaced` → trả ID. Luồng hết hàng kết thúc trước thao tác database và phát event. `@Transactional` điều khiển transaction JPA của `orders`; việc gọi `stock.reserve` qua API là một tương tác sang module khác, cần quy ước nhất quán khi triển khai production.

## 7. Đặt cổng kiểm chứng kiến trúc bằng `ApplicationModules`

`src/test/java/dev/example/shop/ArchitectureVerificationTest.java`:

```java
package dev.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureVerificationTest {
    @Test
    void applicationModulesRespectBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Test này không cần bootstrap Spring Context. `verify()` kiểm tra ít nhất ba loại vi phạm: chu trình phụ thuộc giữa module; phụ thuộc trực tiếp vào type nội bộ của module khác (thay vì public API/named interface); và phụ thuộc ngoài danh sách `allowedDependencies` nếu đã khai báo. Trong ví dụ, `orders.internal.OrderService` được phép tham chiếu `stock.StockGateway` vì đây là API public ở package gốc `stock` và `orders` cho phép phụ thuộc `stock`.

**Thử nghiệm lỗi có kiểm soát:** giả sử bạn thêm một `public` class trong `stock.internal`, rồi import trực tiếp class đó từ `orders.internal`; chạy `ArchitectureVerificationTest` phải báo vi phạm ranh giới. Tương tự, thêm tham chiếu từ `orders` sang một module `billing` không được khai báo cũng phải làm test đỏ. Hoàn nguyên những sửa đổi gây lỗi trước khi kiểm tra ca thành công. Đừng dùng mock để bỏ qua một cảnh báo kiến trúc: mock chỉ giải quyết **wiring bean** ở runtime.

## 8. Tái hiện lỗi bootstrap thiếu collaborator

Tạo ban đầu test skeleton trong `src/test/java/dev/example/shop/orders/internal/OrderModuleTest.java`:

```java
package dev.example.shop.orders.internal;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest // STANDALONE là mặc định
class OrderModuleTest {
    @Test
    void startsOrdersModule() {}
}
```

Chạy `./gradlew test --tests '*OrderModuleTest'` ở trạng thái **chưa có collaborator thay thế**. `@ApplicationModuleTest` chỉ scan bean/entity/repository của `orders`, vì vậy `OrderService` không được tạo: constructor cần `StockGateway` nhưng implementation thực nằm trong `stock.internal` và chưa được nạp. Thông báo thường có chuỗi `UnsatisfiedDependencyException` hoặc `NoSuchBeanDefinitionException` kèm kiểu `StockGateway`.

Đây là **lỗi có chủ đích** của bước thực hành, không phải lý do chuyển vội sang `@SpringBootTest` hoặc `ALL_DEPENDENCIES`. Nó cho thấy module đích có một *efferent dependency* (phụ thuộc hướng ra ngoài). Bước tiếp theo cung cấp bean thay thế tại chính ranh giới ấy.

## 9. Thay collaborator và kiểm thử end-to-end trong phạm vi module

Thay toàn bộ skeleton bằng `OrderModuleTest.java` dưới đây. Import đúng `@MockitoBean` của Spring Framework (`org.springframework.test.context.bean.override.mockito.MockitoBean`); đừng dùng `@Mock` thuần của Mockito vì `@Mock` không đăng ký bean trong Spring Context.

```java
package dev.example.shop.orders.internal;

import dev.example.shop.orders.OrderPlaced;
import dev.example.shop.stock.StockGateway;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

@ApplicationModuleTest(mode = ApplicationModuleTest.BootstrapMode.STANDALONE)
class OrderModuleTest {
    @Autowired OrderService service;
    @Autowired OrderRepository repository;

    @MockitoBean StockGateway stock;

    @BeforeEach
    void cleanDatabase() {
        repository.deleteAll();
    }

    @Test
    void placesOrderPersistsItAndPublishesEvent(PublishedEvents published) {
        given(stock.reserve("PEN-01", 2)).willReturn(true);

        UUID orderId = service.place("PEN-01", 2);

        assertThat(repository.findById(orderId))
                .isPresent()
                .get()
                .satisfies(order -> {
                    assertThat(order.sku()).isEqualTo("PEN-01");
                    assertThat(order.quantity()).isEqualTo(2);
                });

        assertThat(published.ofType(OrderPlaced.class)
                .matching(event -> event.orderId().equals(orderId)
                        && event.sku().equals("PEN-01")
                        && event.quantity() == 2))
                .hasSize(1);

        verify(stock).reserve("PEN-01", 2);
    }

    @Test
    void rejectsOutOfStockWithoutDataOrEvent(PublishedEvents published) {
        given(stock.reserve("MISSING-01", 3)).willReturn(false);

        assertThatThrownBy(() -> service.place("MISSING-01", 3))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("OUT_OF_STOCK");

        assertThat(repository.count()).isZero();
        assertThat(published.ofType(OrderPlaced.class)).isEmpty();
        verify(stock).reserve("MISSING-01", 3);
    }

    @Test
    void rejectsInvalidInputBeforeCallingStock(PublishedEvents published) {
        assertThatThrownBy(() -> service.place("PEN-01", 0))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("INVALID_ORDER");

        assertThat(repository.count()).isZero();
        assertThat(published.ofType(OrderPlaced.class)).isEmpty();
        org.mockito.Mockito.verifyNoInteractions(stock);
    }
}
```

**Vì sao đây là integration test của module?** `OrderService` là Spring bean thật; Spring Data repository và EntityManager làm việc với H2 thật; transaction và `ApplicationEventPublisher` thật; chỉ `StockGateway` là mock. `PublishedEvents` do Spring Modulith cấp cho phương thức test, ghi nhận event phát ra để assertion. `@MockitoBean` thêm hoặc thay bean theo kiểu cần thiết trong test context; nó cho phép `OrderService` được khởi tạo ngay cả khi `stock` không nằm trong phạm vi scan.

Đọc kết quả theo ba tầng:

| Tầng | Assertion/quan sát | Hồi quy được phát hiện |
| --- | --- | --- |
| Collaborator | `verify(stock).reserve(sku, quantity)`; stub `true`/`false` | Sai tham số, bỏ quên gọi API, nhánh hết hàng xử lý sai |
| Database | `findById`, `repository.count()` | Không lưu đơn, lưu sai SKU/số lượng, ghi đơn dù giữ hàng thất bại |
| Event | `published.ofType(OrderPlaced.class)` và predicate | Không phát event, phát sai dữ liệu, phát event cho đơn bị từ chối |

`@BeforeEach` xóa dữ liệu giữa các test vì lời gọi service tạo transaction đã commit. Không mặc định cho rằng `@ApplicationModuleTest` tự rollback toàn bộ test như khi thêm `@Transactional` lên test. Nếu cần kiểm chứng event listener bất đồng bộ hoặc hành vi *sau commit*, xem `Scenario` của Spring Modulith và dọn dữ liệu chủ động; assertion `PublishedEvents` ở trên chỉ chứng minh **event được publish**, chưa chứng minh downstream listener đã xử lý thành công.

## 10. Chọn bootstrap mode và loại collaborator thay thế

| Chế độ `@ApplicationModuleTest` | Bean được nạp | Khi nên dùng |
| --- | --- | --- |
| `STANDALONE` (mặc định) | Module đang test | Kiểm chứng nghiệp vụ và persistence của một module; mock các bean phụ thuộc từ module khác |
| `DIRECT_DEPENDENCIES` | Module đang test và các module mà nó phụ thuộc trực tiếp | Kiểm chứng tích hợp với collaborator thật của các module kề nhau |
| `ALL_DEPENDENCIES` | Module đang test và toàn bộ cây phụ thuộc hướng ra ngoài | Kiểm chứng luồng rộng hơn khi cần nhiều module cùng hoạt động |

Ví dụ mở rộng kiểm thử tích hợp thật:

```java
@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES
)
class OrdersWithRealStockIntegrationTest {
    // Không khai báo @MockitoBean StockGateway ở lớp này.
    // Chuẩn bị fixture tồn kho và dọn trạng thái sau mỗi test.
}
```

Đoạn trên là **phác thảo một lớp test khác**, không phải đoạn cần gộp vào `OrderModuleTest`. Khi đổi mode, bạn thay đổi phạm vi test chứ không tự động sửa dependency sai; hãy chạy `ApplicationModules.verify()` trong mọi trường hợp.

Nếu collaborator có trạng thái phức tạp, một fake bằng `@TestConfiguration` + `@Import` và `@Bean StockGateway` cũng là lựa chọn hợp lý trong **một lớp test riêng**; fake diễn tả quy tắc ổn định, mock diễn tả kỳ vọng tương tác. Không đăng ký fake và `@MockitoBean` cùng kiểu trong cùng context khi không có chủ đích rõ ràng, vì kết quả thay bean sẽ gây khó đọc.

## 11. Quy trình chạy, diễn giải lỗi và quality gate CI

Thực hiện theo thứ tự tại project demo có Gradle Wrapper:

```bash
./gradlew test --tests '*ArchitectureVerificationTest'
./gradlew test --tests '*OrderModuleTest'
./gradlew clean test
```

Trên Windows PowerShell có thể dùng `./gradlew.bat` tương đương. Bật DEBUG log `org.springframework.modulith` để quan sát Spring Modulith chọn module `orders` và thu hẹp phạm vi scan. Không dựa vào việc log tình cờ in tên package để thay thế assertion: bài test phải xác minh hành vi thật.

Thiết lập `.github/workflows/modulith-quality-gate.yml` trong **project demo**:

```yaml
name: modulith-quality-gate

on: [push, pull_request]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: gradle
      - run: ./gradlew clean test --no-daemon
```

CI sẽ có **một cổng đỏ** nếu vi phạm kiến trúc, context module không khởi tạo được, dữ liệu sai hoặc event sai. Trong dự án thực tế nên tách một lớp kiểm thử contract với database giống production (ví dụ Testcontainers PostgreSQL) khỏi H2 smoke test khi SQL dialect, constraint hoặc transaction có khác biệt; chỉ mock ở ranh giới cần cách ly, tránh mock chính repository hoặc service đang được kiểm chứng.

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: StockGateway` | `STANDALONE` loại bean của `stock`, chưa có replacement | Đặt `@MockitoBean StockGateway` tại lớp test và kiểm tra đúng import |
| Vẫn nạp cả `stock.internal` | Dùng `@SpringBootTest` rộng hoặc `DIRECT_DEPENDENCIES` | Trở về `@ApplicationModuleTest(mode = STANDALONE)`, đọc DEBUG bootstrap |
| Mock có mặt nhưng `reserve(...)` trả `false` | Mockito mặc định trả `false` cho `boolean` chưa stub | `given(stock.reserve(...)).willReturn(true)` ở ca thành công |
| Assertion repository sai qua các lượt chạy | Dữ liệu thử nghiệm tồn tại giữa test | Dùng database tách biệt; dọn bằng `@BeforeEach`, hoặc transaction/fixture có kiểm soát |
| `verify()` báo violation | Truy cập nội bộ module khác, allowedDependencies sai, cycle | Sửa API/ràng buộc module; không tắt `verifyAutomatically` để che lỗi |
| Không thấy downstream side effect sau event | `PublishedEvents` chỉ xác nhận publish, listener có thể chạy async/sau commit | Dùng `Scenario`/integration test có chờ điều kiện và cơ chế cleanup |

## 12. Checklist nghiệm thu và bài tập mở rộng

Đối chiếu kết quả mong đợi (đây là tiêu chí để **bạn tự chạy và kiểm tra** trong project demo):

- [ ] `ArchitectureVerificationTest` xanh khi `orders` chỉ phụ thuộc public API `stock.StockGateway`.
- [ ] Cố tình tham chiếu vào `stock.internal` làm `verify()` đỏ, sau đó hoàn nguyên.
- [ ] Bỏ `@MockitoBean` khi chạy `STANDALONE` gây lỗi thiếu `StockGateway`; khôi phục mock làm context khởi tạo được.
- [ ] Ca `reserve(...) == true` lưu được một đơn có đúng `sku`/`quantity`, phát đúng một `OrderPlaced`, gọi gateway đúng một lần.
- [ ] Ca `reserve(...) == false` không lưu đơn, không phát `OrderPlaced`.
- [ ] Ca input không hợp lệ không gọi gateway, không ghi database, không phát event.
- [ ] `./gradlew clean test` trả exit code 0 và CI chạy cùng tập test như trên.

**Nâng độ khó:** bổ sung `@ApplicationModuleTest(mode = DIRECT_DEPENDENCIES)` để đối chiếu adapter thật; thêm test với Testcontainers cho database production; hoặc thay việc gọi đồng bộ `StockGateway` bằng event `OrderRequested` và xây cơ chế reservation bất đồng bộ. Khi thay đổi kiến trúc, cập nhật rõ hợp đồng module và viết thêm bài kiểm chứng kiến trúc tương ứng.

**Tài liệu đối chiếu chính thức:** [Spring Modulith — Module integration tests](https://docs.spring.io/spring-modulith/reference/1.4/testing.html), [Verifying application module structure](https://docs.spring.io/spring-modulith/reference/1.4/verification.html), [Fundamentals / module boundaries](https://docs.spring.io/spring-modulith/reference/1.4/fundamentals.html), [Working with application events](https://docs.spring.io/spring-modulith/reference/1.4/events.html).
