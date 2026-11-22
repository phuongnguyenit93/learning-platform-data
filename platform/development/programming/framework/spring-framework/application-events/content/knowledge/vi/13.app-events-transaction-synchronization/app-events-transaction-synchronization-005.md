# Persistence context sau commit trong Spring Framework Application Events

## 1. Vấn đề: commit xong, EntityManager còn dùng được không?

Khi một phương thức `@Transactional` lưu dữ liệu bằng JPA rồi phát sự kiện Spring, ứng dụng thường muốn xử lý sự kiện **chỉ sau khi giao dịch đã commit thành công**. Cách phổ biến là đăng ký listener:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    // Xử lý sau khi giao dịch phát sự kiện commit thành công.
}
~~~

*Đây là đoạn minh họa trong một bean Spring; `OrderCreated` là kiểu sự kiện do ứng dụng định nghĩa.*

Điều dễ gây nhầm: **“giao dịch đã commit” không có nghĩa “mọi tài nguyên JPA đã lập tức bị đóng và tháo khỏi luồng”**. Trong Spring, ở thời điểm callback sau commit, tài nguyên giao dịch như `EntityManager`, `Session` hoặc kết nối JDBC **có thể vẫn được gắn với luồng và còn truy cập được** trước khi Spring hoàn tất dọn dẹp. Theo Javadoc của `@TransactionalEventListener`, truy cập dữ liệu lúc này còn có thể “tham gia” ngữ cảnh giao dịch cũ, **nhưng những thay đổi mới sẽ không được commit vào tài nguyên đó**.

Vì vậy, hai nhận định sau **khác nhau**:

- **Có thể truy cập persistence context:** ví dụ lấy lại một entity đang được quản lý, đọc thuộc tính của nó hoặc thấy đối tượng trong cache cấp một.
- **Có một giao dịch còn khả năng commit thay đổi mới:** sau khi commit chính đã xong, không còn lượt commit tiếp theo cho những sửa đổi vừa tạo trong callback đó.

Quy tắc thực hành: dùng `AFTER_COMMIT` để quan sát kết quả đã commit hoặc kích hoạt hành động sau commit; nếu cần **ghi thêm dữ liệu vào cơ sở dữ liệu**, mở **một giao dịch mới** rõ ràng, thường bằng `@Transactional(propagation = Propagation.REQUIRES_NEW)` ở một bean riêng.

## 2. Persistence context và transaction là hai vòng đời liên quan nhưng không đồng nhất

**Persistence context** là tập những entity mà một `EntityManager` đang quản lý, kèm cơ chế nhận diện cùng một entity, cache cấp một và theo dõi thay đổi (dirty checking). **Transaction** là ranh giới quyết định việc thay đổi dữ liệu có được commit hay rollback hay không.

| Khái niệm | Ý nghĩa |
| --- | --- |
| `EntityManager` | API JPA để tìm, persist, merge, remove và truy vấn entity. |
| Persistence context | Trạng thái các entity được quản lý trong `EntityManager`, gồm cache cấp một và các thay đổi đang chờ đồng bộ. |
| Managed entity | Entity còn gắn với persistence context; `EntityManager.contains(entity)` có thể trả `true`. |
| Dirty checking | Cơ chế nhà cung cấp JPA, ví dụ Hibernate, phát hiện thay đổi của managed entity khi flush. |
| `flush()` | Đồng bộ các thao tác đang chờ thành SQL theo quy tắc của provider; **không đồng nghĩa commit**. |
| Commit | Hoàn tất giao dịch và xác nhận các thay đổi đã được đồng bộ hợp lệ với cơ sở dữ liệu. |
| Detached entity | Entity không còn gắn với persistence context; đổi trường của nó không tự tạo UPDATE. |

Trong trường hợp JPA transaction-scoped thông thường, persistence context được quản lý theo giao dịch. Tuy nhiên lúc Spring thực thi các callback sau commit, thứ tự dọn dẹp tài nguyên của transaction manager có thể khiến một `EntityManager` vẫn còn được dùng **trong khoảng thời gian ngắn**. Sau khi callback hoàn tất và tài nguyên được dọn, không nên tiếp tục giả định đối tượng vẫn được quản lý.

Các cấu hình khác như `OpenEntityManagerInView`, persistence context mở rộng hoặc `EntityManager` do ứng dụng tự tạo có vòng đời riêng. Đừng suy từ một lần `em.contains(...) == true` rằng entity sẽ luôn còn managed sau khi phương thức kết thúc.

## 3. Thứ tự sự kiện: từ publishEvent đến callback AFTER_COMMIT

Giả sử một service lưu đơn hàng rồi phát `OrderCreated` trong giao dịch:

~~~text
Luồng xử lý giao dịch
  |
  | @Transactional createOrder()
  |    - EntityManager.persist(order)
  |    - publishEvent(new OrderCreated(orderId))
  |      => đăng ký xử lý theo pha transaction
  |
  | phương thức nghiệp vụ kết thúc
  v
Spring Transaction Manager
  |
  | flush dữ liệu cần thiết và COMMIT giao dịch chính
  |
  | gọi các synchronization callback sau hoàn tất
  |    - @TransactionalEventListener(AFTER_COMMIT)
  |    - resource có thể vẫn còn bound với luồng
  |    - không còn lượt commit dành cho thay đổi mới của tx cũ
  |
  | dọn dẹp/unbind/đóng tài nguyên của giao dịch chính
  v
trả quyền điều khiển cho bên gọi
~~~

Một vài điểm cần chính xác:

1. `@TransactionalEventListener` có pha mặc định là `AFTER_COMMIT`. Khi không có transaction đang hoạt động, listener mặc định **không được thực thi**, trừ khi đặt `fallbackExecution = true`.
2. Theo Javadoc của `TransactionPhase.AFTER_COMMIT`, đây là một biến thể của **`AFTER_COMPLETION`**. Nó diễn ra trong chuỗi callback hoàn tất giao dịch, **không phải chính phương thức `TransactionSynchronization.afterCommit()`**. Cả hai đều là thời điểm sau commit, nhưng không nên đánh đồng tên API hoặc thứ tự callback.
3. `AFTER_COMMIT` chỉ được gọi khi giao dịch hoàn tất thành công. Nếu rollback, listener này không chạy; có thể dùng `AFTER_ROLLBACK` khi muốn phản ứng với rollback.
4. Trong Spring dùng transaction gắn với luồng (`PlatformTransactionManager`), việc tài nguyên vẫn bound tại callback là tình huống mà Javadoc cảnh báo. Không được coi đây là một giao dịch ghi còn mở.

## 4. Cạm bẫy: sửa managed entity sau commit nhưng dữ liệu không đổi

Xét đoạn listener sau, dùng cùng persistence context còn truy cập được ở thời điểm callback:

~~~java
@PersistenceContext
private EntityManager entityManager;

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCreated(OrderCreated event) {
    OrderEntity order = entityManager.find(OrderEntity.class, event.orderId());
    order.setStatus("NOTIFIED");
}
~~~

*Đây là mã minh họa, cần đặt trong Spring bean và định nghĩa `OrderEntity`, `OrderCreated`; không phải chương trình độc lập.*

Đoạn code có thể không báo lỗi ngay: entity được tìm thấy, `setStatus(...)` thay đổi đối tượng trong bộ nhớ. Nhưng **giao dịch cũ đã commit**; dirty checking không tự tạo ra một lượt commit nữa. Nếu sau đó mở một transaction/persistence context mới để truy vấn cơ sở dữ liệu, giá trị lưu có thể vẫn là giá trị ban đầu.

Cần phân biệt ba lớp trạng thái:

| Quan sát | Có thể thấy gì? | Có chứng minh đã commit không? |
| --- | --- | --- |
| Đọc lại cùng đối tượng Java | Thấy `status = "NOTIFIED"` vì trường vừa được gán. | **Không.** |
| `EntityManager.find(...)` trong cùng persistence context đang còn sống | Có thể trả cùng managed instance từ cache cấp một. | **Không.** |
| Đọc bằng một transaction và persistence context mới sau khi callback đã kết thúc | Thấy dữ liệu thực tế đã commit trong DB. | Phù hợp để xác minh lưu trữ, với lưu ý về isolation/cache cấu hình. |

**Không dùng `save(...)`, `saveAndFlush(...)` hoặc `entityManager.flush()` như một cách thay thế commit.** `flush` chỉ đồng bộ trạng thái với cơ sở dữ liệu trong các điều kiện giao dịch phù hợp; gọi sau khi transaction hoàn tất có thể không lưu được như mong muốn hoặc ném lỗi tùy API/provider. Nó không tạo một commit mới cho giao dịch đã đóng.

## 5. Ví dụ thực hành Java 17+ với Spring Boot, JPA và H2

Ví dụ này cho thấy hai hành vi trong **cùng một listener `AFTER_COMMIT`**:

- Listener sửa thuộc tính của managed entity trong persistence context cũ; giá trị sửa **không được commit**.
- Listener gọi một service khác dùng `REQUIRES_NEW` để ghi dòng audit; thay đổi trong **giao dịch mới** được commit độc lập.

### 5.1. Tạo ứng dụng tối thiểu

Cần Java 17+, Maven và kết nối Maven Central để tải thư viện lần đầu. Tạo cấu trúc:

~~~text
after-commit-demo/
├── pom.xml
└── src/main/
    ├── java/demo/AfterCommitDemo.java
    └── resources/application.properties
~~~

Nội dung `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>after-commit-demo</artifactId>
    <version>1.0.0</version>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Nội dung `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:aftercommit;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.root=ERROR
~~~

### 5.2. Mã nguồn đầy đủ

Nội dung `src/main/java/demo/AfterCommitDemo.java`:

~~~java
package demo;

import jakarta.persistence.Entity;
import jakarta.persistence.EntityManager;
import jakarta.persistence.Id;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.Table;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@SpringBootApplication
public class AfterCommitDemo implements CommandLineRunner {

    private final OrderService orders;
    private final ReportService report;

    public AfterCommitDemo(OrderService orders, ReportService report) {
        this.orders = orders;
        this.report = report;
    }

    public static void main(String[] args) {
        SpringApplication.run(AfterCommitDemo.class, args);
    }

    @Override
    public void run(String... args) {
        orders.createOrder(42L);
        report.printDatabaseState(42L);
    }

    public record OrderCreated(long orderId) {}
}

@Entity
@Table(name = "demo_orders")
class DemoOrder {

    @Id
    private Long id;
    private String status;

    protected DemoOrder() {}

    public DemoOrder(long id, String status) {
        this.id = id;
        this.status = status;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}

@Entity
@Table(name = "demo_audit")
class DemoAudit {

    @Id
    private Long id;
    private String action;

    protected DemoAudit() {}

    public DemoAudit(long id, String action) {
        this.id = id;
        this.action = action;
    }

    public String getAction() {
        return action;
    }
}

@Service
class OrderService {

    @PersistenceContext
    private EntityManager em;

    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void createOrder(long id) {
        em.persist(new DemoOrder(id, "CREATED"));
        events.publishEvent(new AfterCommitDemo.OrderCreated(id));
        System.out.println("Service: da phat su kien " + id);
    }
}

@Component
class OrderCommittedListener {

    @PersistenceContext
    private EntityManager em;

    private final AuditService audits;

    public OrderCommittedListener(AuditService audits) {
        this.audits = audits;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(AfterCommitDemo.OrderCreated event) {
        DemoOrder order = em.find(DemoOrder.class, event.orderId());
        System.out.println("Listener: managed=" + em.contains(order));

        order.setStatus("CHANGED_AFTER_COMMIT");
        System.out.println("Listener: memory=" + order.getStatus());

        audits.writeAudit(event.orderId());
    }
}

@Service
class AuditService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(long id) {
        em.persist(new DemoAudit(id, "SAVED"));
        System.out.println("AuditService: da ghi audit trong tx moi");
    }
}

@Service
class ReportService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public void printDatabaseState(long id) {
        DemoOrder order = em.find(DemoOrder.class, id);
        DemoAudit audit = em.find(DemoAudit.class, id);
        System.out.println("DB: order=" + order.getStatus());
        System.out.println("DB: audit=" + (audit == null ? "NONE" : audit.getAction()));
    }
}
~~~

Các lớp entity và service trong ví dụ là các lớp cùng package `demo`, được khai báo trong một tệp để dễ sao chép. Entity có constructor không tham số `protected`, không `final`; chỉ lớp `AfterCommitDemo` là `public` để Java biên dịch đúng với tên tệp.

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q spring-boot:run
~~~

Các dòng do chương trình tự in ra stdout trong cấu hình minh họa, không tính log của Maven/Hibernate:

~~~text
Service: da phat su kien 42
Listener: managed=true
Listener: memory=CHANGED_AFTER_COMMIT
AuditService: da ghi audit trong tx moi
DB: order=CREATED
DB: audit=SAVED
~~~

### 5.3. Vì sao có kết quả đó?

1. `OrderService.createOrder(...)` chạy qua Spring proxy `@Transactional`, tạo `DemoOrder(42, "CREATED")` trong persistence context của giao dịch chính và phát event. `@TransactionalEventListener` đăng ký xử lý sau khi transaction commit.
2. Khi phương thức service kết thúc, transaction manager flush các thay đổi cần thiết và commit dòng đơn hàng vào H2.
3. Tại thời điểm `AFTER_COMMIT`, theo luồng JPA transaction manager thông thường, `EntityManager` vẫn còn gắn với giao dịch vừa hoàn tất. `em.find(...)` có thể lấy entity managed từ persistence context và `em.contains(order)` trả `true`.
4. `order.setStatus("CHANGED_AFTER_COMMIT")` chỉ thay đổi đối tượng trong bộ nhớ. Vì commit chính đã hoàn tất, thay đổi này không có lượt commit tương ứng. Đây là ý nghĩa của dòng `Listener: memory=...`.
5. `AuditService.writeAudit(...)` được gọi qua **bean khác** nên proxy `@Transactional(propagation = REQUIRES_NEW)` có hiệu lực. Spring tạm ngưng tài nguyên cũ, tạo transaction mới cho dòng `DemoAudit` rồi commit khi method kết thúc bình thường.
6. `ReportService.printDatabaseState(...)` cũng chạy qua một bean được proxy, trong giao dịch đọc mới với persistence context riêng. Nó nhìn thấy `order=CREATED` trong DB, còn dòng audit được tạo ở giao dịch mới có `action=SAVED`.

**Kết luận của ví dụ:** `managed=true` là thông tin về trạng thái đối tượng trong persistence context tại một thời điểm, **không phải bằng chứng rằng mọi thay đổi sau commit đã được lưu**. Cần kiểm chứng qua một giao dịch/persistence context mới khi muốn biết dữ liệu thực sự đã commit.

## 6. Cách đúng để ghi dữ liệu sau commit: REQUIRES_NEW

Khi yêu cầu là “chỉ ghi audit nếu tạo đơn hàng đã commit thành công”, có thể chuyển logic ghi sang một service độc lập:

~~~java
@Component
class OrderCreatedListener {

    private final AuditWriter auditWriter;

    OrderCreatedListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onCreated(OrderCreated event) {
        auditWriter.record(event.orderId());
    }
}

@Service
class AuditWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(long orderId) {
        // Tìm dữ liệu trong persistence context mới khi cần.
        // Ghi audit/outbox vào DB rồi commit transaction mới.
    }
}
~~~

*Đoạn trên chỉ minh họa mô hình phân chia bean. `OrderCreated`, phần repository/`EntityManager` và import cần được định nghĩa trong ứng dụng thực tế; ví dụ chạy hoàn chỉnh nằm ở phần 5.*

Vì sao phải tách bean? Trong cơ chế proxy mặc định của Spring, nếu listener gọi `this.record(...)` đến một phương thức `@Transactional(REQUIRES_NEW)` **trong cùng đối tượng**, lời gọi nội bộ không đi qua transaction proxy; annotation có thể không tạo transaction mới như mong đợi. Gọi sang một Spring bean khác bảo đảm phương thức được interceptor xử lý.

`Propagation.REQUIRES_NEW` yêu cầu một giao dịch vật lý độc lập; nếu một transaction đang được gắn với luồng, Spring sẽ tạm ngưng và khôi phục tài nguyên cũ theo khả năng của transaction manager. Điều này cần thêm tài nguyên kết nối; ứng dụng có lượng callback lớn phải chú ý cấu hình connection pool và thời gian giữ giao dịch.

Có thể dùng `TransactionTemplate` với propagation `REQUIRES_NEW` khi muốn tạo ranh giới giao dịch bằng code; hai cách cùng nhằm tạo một commit thật sự mới cho công việc sau commit.

## 7. Những cách viết dễ sai

### 7.1. Ghi trực tiếp trong AFTER_COMMIT rồi tin vào save

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCreated(OrderCreated event) {
    OrderEntity order = repository.findById(event.orderId()).orElseThrow();
    order.setStatus("NOTIFIED");
    repository.save(order);
}
~~~

*Đây là đoạn minh họa không độc lập; cần entity, repository và bean Spring tương ứng.*

Có thể thấy lời gọi `save` kết thúc bình thường nhưng không có commit thêm của giao dịch cũ. Hãy chuyển ghi vào phương thức `REQUIRES_NEW` trên bean khác, đồng thời tải lại entity trong persistence context của giao dịch mới.

### 7.2. Thêm @Transactional mặc định rồi nghĩ đã tạo transaction mới

~~~java
@Transactional
public void markNotified(long id) {
    // Mặc định propagation = REQUIRED.
}
~~~

Nếu gọi ở thời điểm tài nguyên giao dịch cũ vẫn bound, `REQUIRED` có thể “tham gia” ngữ cảnh vừa commit, không tạo ranh giới commit mới như mong muốn. Chọn `REQUIRES_NEW` khi bài toán thật sự yêu cầu thao tác DB riêng sau commit.

### 7.3. Truyền trực tiếp managed entity vào sự kiện

~~~java
events.publishEvent(new OrderCreatedEntity(order));
~~~

*`OrderCreatedEntity` là kiểu event giả định.*

Sau commit, entity có thể trở thành detached; nếu callback chạy ở luồng khác hoặc sau khi persistence context bị đóng, thuộc tính lazy chưa tải có thể gây `LazyInitializationException` với Hibernate. Thay vào đó, thường nên đưa **ID và dữ liệu tối thiểu, bất biến** vào event rồi truy vấn lại trong transaction mới khi cần.

### 7.4. Cho rằng AFTER_COMMIT tự bảo đảm giao sự kiện

Nếu tiến trình dừng ngay sau DB commit nhưng trước khi callback xử lý xong, Spring Application Events mặc định không có hàng đợi bền vững để phát lại. Nếu việc ghi audit, tích hợp bên ngoài hoặc gửi thông điệp là bắt buộc và không được mất, xem xét transactional outbox, hàng đợi đáng tin cậy và xử lý idempotent.

## 8. Phân biệt AFTER_COMMIT với các pha khác và @Async

| Cơ chế | Thời điểm | Có thể kỳ vọng điều gì? |
| --- | --- | --- |
| `@EventListener` đồng bộ | Ngay khi `publishEvent(...)` gọi listener | Nếu publisher đang trong transaction, listener có thể làm việc trước commit và lỗi có thể ảnh hưởng giao dịch chính. |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Trước commit | Có thể chuẩn bị/sửa dữ liệu trong giao dịch đang hoạt động theo chính sách flush/commit. |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau commit thành công, trong chuỗi hoàn tất | Hành động sau commit; ghi DB mới phải có transaction độc lập. |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Sau rollback | Dọn dẹp hoặc thông báo thất bại; không có transaction cũ để commit thay đổi mới. |
| `@TransactionalEventListener(AFTER_COMPLETION)` | Sau commit hoặc rollback | Chạy bất kể kết quả hoàn tất, cần xem trạng thái nghiệp vụ nếu muốn hành động có điều kiện. |
| `@Async` kết hợp listener | Có thể chuyển thân xử lý sang luồng executor | Không tự kế thừa transaction hoặc persistence context gắn với luồng phát; phải thiết kế quản lý dữ liệu và lỗi riêng. |

Lưu ý: một listener `@TransactionalEventListener(AFTER_COMMIT)` thông thường vẫn chạy đồng bộ trong chuỗi callback hoàn tất của thread phát sự kiện. **“Sau commit” mô tả thời điểm, không đồng nghĩa “chạy bất đồng bộ”.** Gắn thêm `@Async` làm thay đổi ranh giới luồng, cách quản lý exception, và khả năng truy cập persistence context ban đầu.

Với reactive transaction của Spring (từ 6.1 được hỗ trợ cho transactional event listener), transaction nằm trong Reactor context chứ không phải `ThreadLocal`. Hướng dẫn về `EntityManager` bound theo luồng ở bài này chủ yếu áp dụng cho **JPA + `PlatformTransactionManager` đồng bộ**; không dùng máy móc cho reactive pipeline.

## 9. Quy tắc thực tế và cách tự kiểm chứng

1. **Định nghĩa rõ thời điểm:** nếu dữ liệu phải được sửa **trước khi commit** và cùng chịu rollback, cân nhắc xử lý trong transaction chính hoặc pha `BEFORE_COMMIT`; nếu chỉ sau commit thành công, dùng `AFTER_COMMIT`.
2. **Dùng transaction mới cho ghi DB sau commit:** đặt logic ở bean riêng với `REQUIRES_NEW` hoặc `TransactionTemplate` tương đương.
3. **Đừng kiểm tra thành công bằng entity đang managed:** giá trị trong RAM hoặc cache cấp một có thể chưa phản ánh dữ liệu đã được commit. Kiểm tra bằng truy vấn mới phù hợp với transaction và cache.
4. **Giữ payload event gọn và an toàn:** ưu tiên ID, thời điểm và dữ liệu bất biến cần thiết; tránh phụ thuộc vào lazy relation từ entity cũ.
5. **Đừng dựa vào thứ tự dọn dẹp để giữ session:** callback có thể thấy tài nguyên còn bound theo implementation hiện tại, nhưng ứng dụng không nên giả định nó tồn tại mãi.
6. **Nhận diện tính chất mất mát của event nội bộ:** công việc bắt buộc cần retry, idempotency và cơ chế lưu bền vững.
7. **Kiểm thử bằng DB thực sự:** với H2, PostgreSQL hoặc DB thử nghiệm, xác minh trạng thái sau khi listener chạy bằng một giao dịch mới; không chỉ dựa vào log `setter`.

### Câu hỏi tự kiểm tra

**Câu 1.** Trong `AFTER_COMMIT`, `em.contains(order) == true` có chứng minh `order.setStatus(...)` sẽ được ghi vào DB không?

**Đáp án:** Không. Managed entity còn truy cập được không tạo thêm lượt commit. Những thay đổi sau khi transaction chính đã commit không tự được commit.

**Câu 2.** Tại sao thêm `@Transactional` không tham số vào một phương thức ghi DB chưa chắc giải quyết được vấn đề?

**Đáp án:** Propagation mặc định là `REQUIRED`, có thể tham gia tài nguyên của giao dịch cũ còn bound tại callback. Cần yêu cầu rõ transaction mới và thực sự gọi qua proxy Spring.

**Câu 3.** Cách nào an toàn hơn khi sau commit phải ghi thêm một bản ghi audit?

**Đáp án:** Để listener gọi một service độc lập có `@Transactional(propagation = REQUIRES_NEW)` hoặc dùng `TransactionTemplate` có propagation tương đương; xác minh bằng truy vấn ở giao dịch mới.

**Câu 4.** `@TransactionalEventListener(AFTER_COMMIT)` có tự phát lại event khi JVM chết không?

**Đáp án:** Không. Event nội bộ mặc định không có cơ chế durable delivery/retry; nếu cần bảo đảm giao nhận phải bổ sung thiết kế phù hợp.

## Tài liệu tham khảo

- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html): thời điểm gọi `@TransactionalEventListener`, `fallbackExecution` và các pha giao dịch.
- [Spring Framework Javadoc — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): cảnh báo tài nguyên giao dịch còn truy cập được nhưng thay đổi không còn được commit.
- [Spring Framework Javadoc — TransactionPhase](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionPhase.html): quan hệ `AFTER_COMMIT` và `AFTER_COMPLETION`.
- [Spring Framework Javadoc — TransactionSynchronization](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): callback sau commit và khuyến nghị `REQUIRES_NEW`.
- [Spring Framework Reference — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED` và `REQUIRES_NEW`.
- [Hibernate ORM User Guide — Persistence Context](https://docs.hibernate.org/orm/8.0/userguide/html_single/): managed/detached entity, dirty checking, flush và vòng đời persistence context.
