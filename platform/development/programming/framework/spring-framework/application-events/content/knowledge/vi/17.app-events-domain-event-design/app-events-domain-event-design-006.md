# Phát domain event từ aggregate trong Spring Framework và Spring Data

Trong Domain-Driven Design (DDD), **aggregate** là một ranh giới nhất quán của mô hình nghiệp vụ: các entity/value object thuộc cùng aggregate phải duy trì những bất biến (invariants) của nghiệp vụ khi có một thao tác làm thay đổi trạng thái. **Aggregate root** là đối tượng mà bên ngoài sử dụng để yêu cầu thay đổi. **Domain event** mô tả một sự thật nghiệp vụ *đã xảy ra trong mô hình*, ví dụ "đơn hàng đã được đặt", "thanh toán đã được xác nhận", "hạn mức đã bị thay đổi".

Phát domain event **từ aggregate** thường có hai bước tách biệt:

1. **Aggregate ghi nhận event khi quy tắc nghiệp vụ đã được thực hiện thành công.** Aggregate biết *điều gì* vừa thay đổi, nhưng không cần biết ai sẽ lắng nghe, gửi email hay cập nhật chỉ mục tìm kiếm.
2. **Lớp ứng dụng/infrastructure phát các event đã ghi nhận** thông qua `ApplicationEventPublisher`, thường ở ranh giới repository. Các listener xử lý phản ứng phù hợp, còn transaction quyết định khi nào xử lý phụ thuộc commit.

Spring Data hỗ trợ cơ chế thuận tiện bằng `@DomainEvents`, `@AfterDomainEventPublication` và `AbstractAggregateRoot`. Cần hiểu rõ **ghi nhận**, **phát** và **xác nhận transaction** là ba thời điểm khác nhau. Spring application events là cơ chế trong tiến trình; việc phát thành công tự nó không bảo đảm message được lưu bền vững hay gửi đến hệ thống ngoài.

## 1. Vì sao aggregate nên là nơi quyết định có event?

Giả sử có aggregate `PurchaseOrder` với thao tác `place()`. Nếu application service tự phát `OrderPlaced` trước khi gọi quy tắc nghiệp vụ, một listener có thể nhận thông báo về đơn hàng chưa hề hợp lệ. Nếu application service cố suy luận lại từ các field sau khi lưu, logic nhận biết "đã đặt đơn" có thể bị lặp lại ở nhiều nơi.

Cách biểu diễn tự nhiên hơn:

```text
Application Service             Aggregate Root               Repository / Spring
       |                               |                               |
       |---- place(orderNo) ---------->|                               |
       |                               |-- kiểm tra bất biến            |
       |                               |-- cập nhật trạng thái          |
       |                               |-- registerEvent(OrderPlaced)  |
       |<--- aggregate ---------------|                               |
       |                                                               |
       |---- repository.save(aggregate) ------------------------------>|
       |                                       lưu aggregate           |
       |                                       đọc danh sách events    |
       |                                       publish events          |
       |                                       clear events            |
       |<----------------------------- save trả về --------------------|
       |                                                               |
       +-- transaction kết thúc: COMMIT hoặc ROLLBACK                  |
```

Aggregate chỉ biết sự kiện nghiệp vụ xảy ra khi nó chuyển trạng thái hợp lệ. Infrastructure quyết định cách phát event. Điều này giữ quy tắc nghiệp vụ trong mô hình, giúp test aggregate mà không cần khởi động Spring, và tránh nhúng SMTP/Kafka/HTTP client vào đối tượng domain.

Một vài nguyên tắc khi thiết kế event:

- **Tên ở thì quá khứ:** `OrderPlaced`, `PaymentCaptured`, `SubscriptionCancelled`; sự kiện là điều đã xảy ra trong mô hình, không phải mệnh lệnh như `SendEmail`.
- **Dữ liệu đủ rõ để xử lý:** ví dụ `orderNumber`, `customerId`, `occurredAt` hoặc phiên bản aggregate nếu nghiệp vụ cần. Không nhất thiết đưa cả entity JPA đang managed vào payload.
- **Bất biến khi phát:** Java `record` là lựa chọn dễ đọc cho event đơn giản.
- **Không rò rỉ domain qua hạ tầng:** aggregate không cần gọi `ApplicationEventPublisher`; việc gọi publisher trực tiếp trong aggregate làm mô hình phụ thuộc container và khó kiểm thử hơn.
- **Một thay đổi có thể tạo nhiều event:** lưu danh sách theo thứ tự đăng ký; không giả định thứ tự hoàn tất giữa các listener bất đồng bộ.

## 2. Spring Data tự phát event của aggregate như thế nào?

Spring Data Commons có hai annotation:

```java
@DomainEvents
Collection<?> domainEvents() {
    return events;
}

@AfterDomainEventPublication
void clearEvents() {
    events.clear();
}
```

Đây là **đoạn API minh họa**, giả định `events` là danh sách các domain event của aggregate.

- `@DomainEvents` đánh dấu một phương thức **không nhận tham số**, trả về một event hoặc collection các event để repository công bố.
- `@AfterDomainEventPublication` đánh dấu callback chạy **sau khi Spring Data đã công bố các event**; thường dùng để xóa danh sách đã phát và tránh phát lặp ở lần lưu tiếp theo.
- Spring Data gắn cơ chế này với những lời gọi repository được hỗ trợ như `save(aggregate)`, `saveAll(...)` và một số biến thể `delete(...)` nhận chính đối tượng aggregate.
- `deleteById(id)` **không được bảo đảm phát domain event của aggregate**, vì repository có thể không có sẵn instance aggregate để lấy event.
- Các truy vấn cập nhật/xóa trực tiếp như JPQL `@Modifying`, SQL bulk update, hoặc chỉ sửa một JPA entity đang managed rồi để dirty checking tự flush **không phải** lời gọi repository thu thập domain events từ aggregate. Nếu dùng đường này, không thể mặc định các event đã được Spring Data phát.

Đặc biệt, **`@AfterDomainEventPublication` không có nghĩa `AFTER_COMMIT`**. Các event có thể đã được phát, danh sách trong aggregate đã xóa, nhưng transaction ghi database vẫn chưa commit. Nếu transaction sau đó rollback, không có cơ chế tự động "trả event về danh sách".

### 2.1. Cách ngắn gọn: kế thừa `AbstractAggregateRoot`

Thay vì tự viết hai annotation và quản lý danh sách, Spring Data cung cấp:

```java
import org.springframework.data.domain.AbstractAggregateRoot;

public class PurchaseOrder extends AbstractAggregateRoot<PurchaseOrder> {

    public void place() {
        // Kiểm tra nghiệp vụ và chuyển trạng thái trước.
        registerEvent(new OrderPlaced("PO-42"));
    }
}
```

Đây là **đoạn minh họa API**, chưa phải entity có thể lưu độc lập. `AbstractAggregateRoot` đã có sẵn:

| API | Vai trò |
| --- | --- |
| `registerEvent(event)` | Ghi thêm event vào danh sách chờ phát, trả về chính event |
| `andEvent(event)` | Ghi event rồi trả về aggregate, hữu ích với fluent API |
| `domainEvents()` | Trả về danh sách event; được đánh dấu `@DomainEvents` |
| `clearDomainEvents()` | Xóa danh sách sau publication; được đánh dấu `@AfterDomainEventPublication` |
| `andEventsFrom(otherAggregate)` | Chuyển/thu thập event từ aggregate khác khi cần |

Danh sách này thuộc **bộ nhớ của instance aggregate**, không phải cột dữ liệu được persist và không phải durable message queue. `AbstractAggregateRoot` đánh dấu storage nội bộ của event là transient để tránh lưu nó như thuộc tính domain.

Lưu ý thiết kế: dùng kế thừa sẽ tạo một mức phụ thuộc của mô hình domain vào Spring Data. Nếu dự án muốn domain hoàn toàn độc lập framework, có thể tự chứa danh sách event trong aggregate và để lớp application/infrastructure lấy, phát, làm sạch sau khi xử lý theo hợp đồng riêng.

## 3. Ví dụ đầy đủ có thể chạy bằng Java 17+: aggregate phát `OrderPlaced` qua Spring Data JPA

Ví dụ tạo đơn hàng với một aggregate root. Khi application service gọi `repository.save(order)`, Spring Data lấy `OrderPlaced` đã được `registerEvent(...)` ghi lại và phát vào Spring event multicaster.

Hai listener minh họa sự khác biệt:

- `@EventListener` chạy **khi event được publish** (trong ví dụ là lúc `save(...)` đang được xử lý, transaction ứng dụng chưa kết thúc).
- `@TransactionalEventListener(phase = AFTER_COMMIT)` chỉ xử lý **sau khi transaction tạo đơn commit thành công**.

Dự án sử dụng Spring Boot 3.3, Spring Data JPA, H2 và Java 17+, không cần web server.

### 3.1. Cấu trúc

```text
aggregate-events-demo/
├── pom.xml
└── src/main/
    ├── java/example/aggregate/
    │   ├── DomainEventsApplication.java
    │   ├── PurchaseOrder.java
    │   ├── OrderPlaced.java
    │   ├── PurchaseOrderRepository.java
    │   ├── PlaceOrderService.java
    │   └── OrderEventListeners.java
    └── resources/application.properties
```

### 3.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>aggregate-events-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.aggregate.DomainEventsApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot parent quản lý phiên bản Spring Data JPA, Hibernate và H2 tương thích.

### 3.3. `src/main/java/example/aggregate/OrderPlaced.java`

```java
package example.aggregate;

public record OrderPlaced(String orderNumber) {
}
```

`OrderPlaced` là một event bất biến chứa mã đơn hàng nghiệp vụ ổn định. Listener không phải đọc ngược toàn bộ entity JPA từ event.

### 3.4. `src/main/java/example/aggregate/PurchaseOrder.java`

```java
package example.aggregate;

import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import org.springframework.data.domain.AbstractAggregateRoot;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder extends AbstractAggregateRoot<PurchaseOrder> {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String orderNumber;

    @Column(nullable = false)
    private String status;

    protected PurchaseOrder() {
        // JPA cần constructor không tham số.
    }

    private PurchaseOrder(String orderNumber) {
        this.orderNumber = Objects.requireNonNull(orderNumber);
        this.status = "PLACED";
    }

    public static PurchaseOrder place(String orderNumber) {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException("Order number is required");
        }

        PurchaseOrder order = new PurchaseOrder(orderNumber);
        order.registerEvent(new OrderPlaced(orderNumber));
        return order;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }
}
```

Điểm chính: `PurchaseOrder.place(...)` thực hiện quy tắc tạo đơn hợp lệ rồi **ghi nhận** `OrderPlaced`. Nó chưa trực tiếp gọi `ApplicationEventPublisher`. Event được lưu trong bộ nhớ của instance cho đến khi Spring Data lấy ra ở bước repository.

`id` là khóa kỹ thuật do database tạo; `orderNumber` là mã nghiệp vụ đã biết trước khi lưu, nên event không phụ thuộc việc lấy khóa tự sinh từ database.

### 3.5. `src/main/java/example/aggregate/PurchaseOrderRepository.java`

```java
package example.aggregate;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
```

Repository được Spring Data tạo proxy. Khi `save(...)` nhận aggregate có domain events, cơ chế repository sẽ phát các event của nó theo hợp đồng `@DomainEvents`.

### 3.6. `src/main/java/example/aggregate/PlaceOrderService.java`

```java
package example.aggregate;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {

    private final PurchaseOrderRepository repository;

    public PlaceOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void place(String orderNumber) {
        PurchaseOrder order = PurchaseOrder.place(orderNumber);
        repository.save(order);
        System.out.println("service: repository save returned");
    }
}
```

`@Transactional` đặt trên service giúp **bao trọn cả thao tác lưu và phần phát event của repository trong một transaction**. Transaction chưa commit chỉ vì `repository.save(...)` trả về; khi phương thức service thoát bình thường, interceptor của Spring mới hoàn tất transaction.

### 3.7. `src/main/java/example/aggregate/OrderEventListeners.java`

```java
package example.aggregate;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderEventListeners {

    @EventListener
    public void whenPublished(OrderPlaced event) {
        System.out.println("listener: published " + event.orderNumber());
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void whenCommitted(OrderPlaced event) {
        System.out.println("listener: after commit " + event.orderNumber());
    }
}
```

Phương thức `whenPublished` chỉ xác nhận thời điểm publication; không nên gửi tác vụ bên ngoài không thể hoàn tác ở đây khi transaction còn có khả năng rollback. Phương thức `whenCommitted` chỉ chạy nếu transaction nguồn commit thành công.

### 3.8. `src/main/java/example/aggregate/DomainEventsApplication.java`

```java
package example.aggregate;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DomainEventsApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(DomainEventsApplication.class);
        app.setBannerMode(Banner.Mode.OFF);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            context.getBean(PlaceOrderService.class).place("PO-42");

            long count = context.getBean(PurchaseOrderRepository.class).count();
            System.out.println("main: saved orders=" + count);
        }
    }
}
```

Việc gọi `PlaceOrderService` qua Spring bean bảo đảm `@Transactional` được áp dụng bởi Spring proxy. Không gọi trực tiếp `new PlaceOrderService(...)` nếu muốn transaction interceptor hoạt động.

### 3.9. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:aggregate_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.root=ERROR
```

H2 là database trong bộ nhớ; cấu hình `create-drop` tạo schema cho buổi thực hành và xóa khi ứng dụng tắt. Không sử dụng cấu hình này để quản lý schema dữ liệu production.

### 3.10. Chạy và quan sát

Từ thư mục có `pom.xml`, cần Java 17+ và Maven:

```bash
mvn -q compile exec:java
```

Các dòng do **chương trình** in ra, theo thứ tự (không tính output riêng của framework hoặc Maven):

```text
listener: published PO-42
service: repository save returned
listener: after commit PO-42
main: saved orders=1
```

Giải thích chi tiết:

1. `PurchaseOrder.place("PO-42")` tạo aggregate và gọi `registerEvent(...)`. **Chưa có listener được gọi** ở dòng này.
2. `repository.save(order)` đi qua Spring Data repository; repository lấy danh sách event đã ghi nhận rồi công bố qua cơ chế Spring application events. Vì multicaster mặc định gọi đồng bộ, `@EventListener` in `listener: published PO-42` trong thao tác repository.
3. Sau khi `save(...)` trả về, service in `service: repository save returned`. Transaction bên ngoài **chưa kết thúc** cho đến khi service trả về qua interceptor.
4. Spring commit transaction; `@TransactionalEventListener(AFTER_COMMIT)` in `listener: after commit PO-42`.
5. Phương thức `place(...)` trả về cho `main`; truy vấn `count()` thấy **1** đơn đã lưu.

Kết luận từ ví dụ là **thời điểm Spring Data phát domain event gắn với lời gọi repository**, còn **thời điểm thực thi listener phụ thuộc kiểu listener và phase transaction**. Không nên xem một callback `@AfterDomainEventPublication` là bằng chứng database đã commit.

## 4. Làm cách nào khi không muốn kế thừa `AbstractAggregateRoot`?

Nếu mô hình domain muốn tránh base class Spring Data, có thể khai báo danh sách event và annotation trực tiếp:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;

public class PureStyleOrder {
    private final List<Object> pendingEvents = new ArrayList<>();

    public void place(String orderNumber) {
        // Kiểm tra bất biến, thay đổi trạng thái...
        pendingEvents.add(new OrderPlaced(orderNumber));
    }

    @DomainEvents
    protected Collection<Object> domainEvents() {
        return List.copyOf(pendingEvents);
    }

    @AfterDomainEventPublication
    protected void clearDomainEvents() {
        pendingEvents.clear();
    }
}
```

Đây là **đoạn minh họa API**, chưa phải entity JPA có mapping đầy đủ, và vẫn dùng annotation của Spring Data. Điểm khác với kế thừa là quyền tự quản lý collection. Không khai báo tham số cho phương thức `@DomainEvents`; đừng trả trực tiếp một collection có thể bị sửa ngoài ý muốn.

Nếu yêu cầu **domain thuần Java, không phụ thuộc Spring Data ở cả annotation**, hãy cho aggregate chỉ cung cấp một API domain như `drainDomainEvents()` và để một adapter/application service lấy event, phát qua `ApplicationEventPublisher` trong transaction sau khi lưu. Adapter phải định nghĩa rõ lúc nào lấy, xóa event và xử lý lỗi; trong trường hợp đó Spring Data sẽ **không tự động** phát event chỉ vì aggregate chứa danh sách.

Một ví dụ tách trách nhiệm ở tầng ứng dụng (**mã minh họa, không độc lập**):

```java
@Transactional
public void placeOrder(String orderNumber) {
    PurchaseOrder aggregate = PurchaseOrder.place(orderNumber);
    repository.save(aggregate);

    // Nếu không dùng Spring Data @DomainEvents, adapter tự publish
    // những event được aggregate trả về.
    for (Object event : aggregate.drainDomainEvents()) {
        applicationEventPublisher.publishEvent(event);
    }
}
```

Đoạn này **không áp dụng trực tiếp** cho `PurchaseOrder extends AbstractAggregateRoot` ở mục 3; nó minh họa một thiết kế thay thế có API `drainDomainEvents()` tự định nghĩa. Đừng dùng cả tự phát lẫn `@DomainEvents` cho cùng một event, vì sẽ tạo **publication trùng**.

## 5. Transaction boundary: event được phát khác với dữ liệu đã commit

Khi Spring Data phát event trong một lời gọi `save(...)`, commit của transaction bao ngoài có thể chưa xảy ra. Một event vừa được phát có thể đi kèm transaction sẽ rollback sau đó.

| Tình huống | `@EventListener` đồng bộ | `@TransactionalEventListener(AFTER_COMMIT)` |
| --- | --- | --- |
| Transaction tạo đơn commit thành công | Được gọi ngay lúc publish | Được gọi sau commit |
| Transaction tạo đơn rollback **sau** khi event đã publish | Có thể đã chạy và tạo side effect | Không chạy vì không có commit thành công |
| Event publish ngoài transaction | Chạy theo cơ chế listener thường | Mặc định bỏ qua vì `fallbackExecution = false` |
| Listener đồng bộ ném exception trước commit | Có thể làm `save`/service thất bại, dẫn tới rollback | Không áp dụng nếu chưa tới giai đoạn commit |
| Listener sau commit gặp lỗi | Không liên quan | Không thể rollback transaction nguồn đã commit |

Vì vậy:

- Dùng `@EventListener` khi logic xử lý tức thời **được phép tham gia transaction hiện tại** hoặc chỉ làm việc đồng bộ, an toàn nếu transaction rollback.
- Dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` khi chỉ được xử lý **sau commit**, chẳng hạn gửi notification hoặc kích hoạt một quy trình khác. Lỗi sau commit không rollback transaction gốc.
- Nếu listener sau commit muốn ghi database, thường cần một **transaction mới rõ ràng**, ví dụ service `@Transactional(propagation = Propagation.REQUIRES_NEW)` được gọi qua Spring proxy. Các resource cũ đôi khi vẫn hiện diện sau commit nhưng không còn commit mới cho giao dịch cũ.
- `@TransactionalEventListener` có pha `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`; chọn theo nghĩa nghiệp vụ, không chỉ theo thứ tự callback.

**Lưu ý rất quan trọng:** `AbstractAggregateRoot` làm sạch event sau **publication**, không sau **commit**. Nếu giao dịch rollback, event đã publish trong bộ nhớ không được tự động đưa về queue. Nếu ứng dụng cần phát sự kiện bền vững chính xác theo trạng thái commit thì phải thiết kế cơ chế khác.

## 6. Những giới hạn hay bị bỏ qua

### 6.1. Thay đổi entity không đồng nghĩa Spring Data repository phát event

Trường hợp:

```java
@Transactional
public void changeOrder(Long id) {
    PurchaseOrder order = repository.findById(id).orElseThrow();
    order.changeSomething(); // Giả định method tạo một domain event.
    // Không gọi repository.save(order).
    // Hibernate có thể dirty-check để UPDATE khi flush.
}
```

Đây là **mã minh họa**; `changeSomething()` không có trong class mục 3. JPA dirty checking có thể lưu field thay đổi lúc flush, nhưng cơ chế `@DomainEvents` của Spring Data gắn với **lời gọi repository**, nên event ghi nhận chưa chắc đã được phát. Nếu thiết kế dựa vào `@DomainEvents`, cần bảo đảm các đường ghi dữ liệu thực tế đi qua các repository method hỗ trợ publication, ngay cả khi JPA có thể tự flush một entity managed.

### 6.2. `deleteById(...)` và bulk update/delete không bảo đảm publication

Không suy luận “mọi thay đổi database đều có domain event”. Spring Data document `deleteById(...)` như một trường hợp không thể dựa vào để lấy event vì phương thức có thể thực thi xóa mà không nhận aggregate instance. JPQL/SQL bulk operations và truy vấn sửa trực tiếp còn dễ bỏ qua cơ chế repository event hơn.

Khi thao tác xóa mang ý nghĩa nghiệp vụ cần event, hãy mô hình hóa thao tác trên aggregate rồi gọi repository method phù hợp có nhận instance, hoặc công bố event từ orchestration rõ ràng.

### 6.3. Lưu cùng aggregate nhiều lần không được mặc định sinh cùng event nhiều lần

Sau một lần publish, `AbstractAggregateRoot` xóa danh sách đã ghi nhận qua `@AfterDomainEventPublication`. Do đó, nếu gọi `save(order)` lần nữa mà **không có thay đổi nghiệp vụ mới**, đừng kỳ vọng event cũ được tự phát lại. Ngược lại, nếu ứng dụng tự thêm event mới trước lần lưu sau, repository có thể phát event mới.

Đây là cơ chế làm sạch **trong cùng instance**, không bảo đảm exactly-once giữa nhiều request, nhiều replica hoặc các lần retry. Một yêu cầu nghiệp vụ có thể bị xử lý lại và tạo event khác; consumer vẫn cần idempotency khi cần.

### 6.4. Không xem domain event là command

`OrderPlaced` mô tả chuyện đã xảy ra; `SendConfirmationEmail` là một yêu cầu thực thi công việc. Domain event có thể dẫn tới một command trong application layer, nhưng aggregate không nên biết dịch vụ email nào tồn tại.

Một event có thể có nhiều listener tương đối độc lập: cập nhật số liệu, ghi audit, thông báo. Nếu B **phải thành công sau A**, thay vì chỉ dựa vào thứ tự listener, hãy tạo một luồng phối hợp rõ ràng. `@Order` chỉ đặt ưu tiên gọi trong điều kiện phù hợp; nó không bảo đảm thứ tự hoàn tất của tác vụ bất đồng bộ.

### 6.5. Không truyền entity JPA sống sang listener bất đồng bộ

Một entity managed có thể đang gắn với persistence context của transaction và không còn hợp lệ khi callback chạy trên thread khác hoặc sau khi context đóng. Lazy association có thể gây `LazyInitializationException`; đổi trạng thái entity trong listener cũng khó xác định thuộc transaction nào.

Nên tạo event bất biến chứa các giá trị/snapshot thiết yếu và ID để listener truy vấn lại theo transaction riêng khi cần. Không gửi toàn bộ graph đối tượng hoặc thông tin nhạy cảm không cần thiết.

### 6.6. Spring application event chỉ là event trong tiến trình

Spring Data không tự tạo Kafka topic, RabbitMQ message, retry durable, idempotency key hay transactional outbox. Nếu ứng dụng dừng ngay **sau khi database commit nhưng trước khi listener thực hiện tác vụ ngoài**, phản ứng có thể bị mất. Nếu listener đã gửi thành công nhưng tiến trình ngừng trước khi ghi trạng thái, retry có thể gây trùng.

Đối với tích hợp giữa dịch vụ, cần xem xét:

1. Trong **cùng transaction** với dữ liệu aggregate, ghi một bản ghi `outbox` có `eventId`, `aggregateId`, `eventType` và payload.
2. Một dispatcher/worker độc lập đọc outbox, gửi tới broker hoặc dịch vụ khác và đánh dấu hoàn tất.
3. Khi lỗi, worker retry có backoff; consumer xử lý idempotency theo event ID.
4. Không xóa outbox event chỉ vì đã gọi API publish một lần; phải có trạng thái gửi và phương án phục hồi.

Cơ chế trên giúp phục hồi lỗi giữa database commit và xuất message. Nó không biến mọi hệ thống thành giao nhận exactly-once tuyệt đối.

## 7. Kiểm thử aggregate và cơ chế publication

Nên tách kiểm thử theo trách nhiệm:

### 7.1. Unit test của aggregate: không cần Spring

Kiểm thử rằng `PurchaseOrder.place(...)`:

- Chấp nhận mã đơn hợp lệ, tạo state `PLACED` và ghi nhận đúng một `OrderPlaced`.
- Từ chối mã rỗng, không tạo aggregate hợp lệ và không phát event nghiệp vụ.
- Không tự gửi email hoặc gọi database chỉ vì đăng ký event.

Vì `registerEvent(...)` là protected và danh sách được quản lý bởi `AbstractAggregateRoot`, nếu muốn unit test danh sách event không qua reflection, có thể thiết kế aggregate cung cấp một API test phù hợp hoặc kiểm tra thông qua một lớp adapter/contract trong test. Mục đích là xác nhận **điều kiện tạo event nằm trong hành vi domain**, không phải ép test biết chi tiết nội bộ Spring Data.

### 7.2. Integration test repository: có Spring Data JPA

Trong một test có database và Spring context:

1. Tạo aggregate rồi gọi `repository.save(...)` dưới transaction thật.
2. Dùng một listener thu thập sự kiện để kiểm tra `OrderPlaced` được publish bởi repository.
3. Kiểm tra lưu lại aggregate **mà không đăng ký event mới** không làm lặp event cũ trong instance.
4. Với một transaction chủ động rollback sau khi đã publish, xác nhận listener `AFTER_COMMIT` **không chạy**.
5. Với commit thành công, xác nhận listener `AFTER_COMMIT` chạy, rồi query dữ liệu từ một transaction/kết nối độc lập để kiểm chứng commit.

Đừng kết luận chỉ từ `repository.save(...)` trả về rằng transaction đã commit: `save` có thể thao tác với persistence context trước khi commit thật. Cũng đừng dùng `Thread.sleep(...)` để khẳng định thứ tự; dùng cơ chế thu thập event đồng bộ hoặc latch cho tác vụ async.

### 7.3. Integration test lỗi và idempotency

Mô phỏng hai lần xử lý cùng business request ID. Dùng unique constraint phù hợp hoặc idempotency key trong service để bảo vệ trạng thái và event ở cấp nghiệp vụ. Nếu có outbox, kiểm thử tình huống worker gửi thành công rồi chết trước khi đánh dấu sent, để bảo đảm consumer nhận trùng vẫn không thực hiện side effect hai lần.

## 8. Câu hỏi tự đánh giá

**1. Ai quyết định `OrderPlaced` có thực sự xảy ra?**  
Aggregate root, thông qua một phương thức nghiệp vụ kiểm tra bất biến và ghi nhận event.

**2. `registerEvent(...)` có gửi ngay event tới listener không?**  
Không. Nó thêm event vào danh sách của aggregate. Với Spring Data, publication xảy ra khi đi qua repository method được hỗ trợ, ví dụ `save(...)`.

**3. `@AfterDomainEventPublication` có chờ database commit không?**  
Không. Callback được gắn với việc event đã **publish**, khác với pha `AFTER_COMMIT` của transaction.

**4. Đổi entity managed rồi chờ JPA dirty checking có luôn phát event không?**  
Không. Dirty checking và Spring Data repository event publication là hai cơ chế khác nhau.

**5. Có nên dùng `@TransactionalEventListener(AFTER_COMMIT)` cho gửi thông báo sau khi lưu đơn không?**  
Có thể, nếu phản ứng chỉ nên xảy ra sau commit. Nhưng nó vẫn không bảo đảm giao event bền vững qua sự cố tiến trình. Khi cần retry đáng tin cậy, nên dùng outbox.

**6. Nếu gọi `save(order)` hai lần thì domain event luôn xuất hiện hai lần không?**  
Không. `AbstractAggregateRoot` xóa danh sách event sau publication; muốn event mới phải có hành vi nghiệp vụ mới đăng ký event. Quy tắc này vẫn không thay thế idempotency khi xử lý yêu cầu lặp.

## 9. Tài liệu chính thức

- [Spring Data JPA Reference — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/jpa/reference/repositories/core-domain-events.html)
- [Spring Data Commons Javadoc — AbstractAggregateRoot](https://docs.spring.io/spring-data/commons/docs/3.3.12/api/org/springframework/data/domain/AbstractAggregateRoot.html)
- [Spring Data Commons Javadoc — DomainEvents](https://docs.spring.io/spring-data/commons/docs/3.3.12/api/org/springframework/data/domain/DomainEvents.html)
- [Spring Data Commons Javadoc — AfterDomainEventPublication](https://docs.spring.io/spring-data/commons/docs/3.3.12/api/org/springframework/data/domain/AfterDomainEventPublication.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)

