# Integrator cùng cách đăng ký thành phần mở rộng

Hibernate ORM không chỉ ánh xạ các lớp Java sang bảng quan hệ. Nó còn cho phép các thư viện và ứng dụng **mở rộng hành vi ở thời điểm khởi tạo** thông qua hệ thống Service Provider Interface (SPI). Một SPI quan trọng là `org.hibernate.integrator.spi.Integrator`.

`Integrator` giúp một module gắn các thành phần của mình vào quá trình tạo `SessionFactory`, đặc biệt là **đăng ký Hibernate event listeners**. Những listener đó có thể quan sát hoặc can thiệp vào các sự kiện liên quan đến load, persist, update, delete, flush và persistent collections. Đây là cách những integration module có thể tham gia runtime Hibernate mà không buộc mọi entity hoặc service phải gọi chúng trực tiếp.

Điểm cần phân biệt ngay từ đầu:

> **Integrator là bootstrap hook, không phải callback trên từng entity.** Khi Hibernate xây dựng một `SessionFactory`, nó gọi `integrate(...)` của các Integrator được phát hiện. Integrator đăng ký listener; sau đó Hibernate mới gọi listener khi event xảy ra.

~~~text
Java application / thư viện mở rộng
                |
                v
Hibernate bootstrap + Metadata
                |
                v
Tạo SessionFactory
                |
                +── Integrator.integrate(...)
                |        |
                |        +── EventListenerRegistry
                |                 |
                |                 +── Đăng ký PostInsertEventListener
                |                 +── Đăng ký PreUpdateEventListener
                |
                v
SessionFactory sẵn sàng
                |
                v
Application persist/update/delete/load
                |
                v
Hibernate event listener được gọi
                |
                v
Đóng SessionFactory
                |
                v
Integrator.disintegrate(...) / cleanup
~~~

Bài thuộc chương **Sự kiện và mở rộng** trong module *Data Persistence Relational Access ORM Hibernate*. Chúng ta sẽ xây một ví dụ hoàn chỉnh, so sánh các cách đăng ký qua **Java ServiceLoader**, **BootstrapServiceRegistryBuilder**, **JPA IntegratorProvider** và **Spring Boot HibernatePropertiesCustomizer**, sau đó giải thích listener ordering, duplicate registration, lifecycle, transaction, khả năng tương thích giữa phiên bản và cách chọn SPI thích hợp.

Các ví dụ hướng đến Hibernate ORM **6.6 và 7.2**, sử dụng `jakarta.persistence`. `Integrator` là Hibernate-specific API, không phải API Jakarta Persistence portable. Với Hibernate 5.x hoặc các major versions mới, cần kiểm tra Javadocs của đúng phiên bản.

## 1. Vì sao ứng dụng cần mở rộng Hibernate?

Một ứng dụng nhỏ có thể ghi log trong service:

~~~java
@Transactional
public void createProduct(CreateProductCommand command) {
    Product product =
        new Product(command.sku(), command.name());

    entityManager.persist(product);

    log.info("Create product requested: {}", product.getSku());
}
~~~

Nếu chỉ một service cần log, không nhất thiết dùng Integrator. Tuy nhiên, một thư viện auditing/metrics muốn quan sát nhiều entity ở nhiều nơi, hoặc một reusable module muốn tự tham gia Hibernate khi được thêm vào classpath. Khi đó lặp logic trong mọi service không phù hợp.

Một module mở rộng có thể:

1. Viết listener theo một Hibernate event contract.
2. Viết Integrator để đăng ký listener vào đúng EventType.
3. Làm Hibernate phát hiện Integrator lúc bootstrap.
4. Để Hibernate gọi listener cho các event tiếp theo.
5. Dọn tài nguyên do module sở hữu khi factory đóng.

Cơ chế này giảm coupling giữa domain code và một plugin kỹ thuật, nhưng cũng có rủi ro nếu listener thực hiện nhiều tác dụng phụ trong transaction.

## 2. Phân biệt Integrator, event listener và entity callback

| Thành phần | Thời điểm thực thi | Nhiệm vụ |
| --- | --- | --- |
| `Integrator.integrate(...)` | Khi `SessionFactory` đang khởi tạo | Đăng ký/tham gia integration |
| `PostInsertEventListener.onPostInsert(...)` | Khi Hibernate đã thực hiện entity INSERT trong flow tương ứng | Quan sát một insert event |
| `PreUpdateEventListener.onPreUpdate(...)` | Trước thao tác update tương ứng | Quan sát hoặc veto theo contract |
| JPA `@PostPersist` | Entity lifecycle theo Jakarta Persistence | Callback gắn entity/listener JPA |
| `Integrator.disintegrate(...)` | Khi factory đóng, theo version contract | Cleanup tài nguyên của integration |
| Spring `ApplicationEvent` listener | Khi application phát event Spring | Không mặc định liên quan Hibernate SPI |

Một Integrator có thể được gọi **một lần khi tạo một SessionFactory**, trong khi listener được đăng ký từ đó có thể nhận hàng triệu events trong suốt vòng đời factory.

Không viết nghiệp vụ per-entity bên trong `integrate(...)`. Trong thời điểm này, factory **chưa fully initialized**, và Javadocs Hibernate cảnh báo nó đang ở trạng thái dễ bị ảnh hưởng bởi các lời gọi không phù hợp.

## 3. Những API/Hibernate SPI quan trọng

| Loại | Package | Vai trò |
| --- | --- | --- |
| `Integrator` | `org.hibernate.integrator.spi` | Lifecycle integration |
| `Metadata` | `org.hibernate.boot` | Mô hình mapping được xây dựng khi bootstrap |
| `BootstrapContext` | `org.hibernate.boot.spi` | Context/config/services bootstrap |
| `SessionFactoryImplementor` | `org.hibernate.engine.spi` | Contract của factory ở tầng SPI |
| `SessionFactoryServiceRegistry` | `org.hibernate.service.spi` | Registry gắn với factory |
| `EventListenerRegistry` | `org.hibernate.event.service.spi` | Quản lý event listener groups |
| `EventType` | `org.hibernate.event.spi` | Định danh từng event group |
| `PostInsertEventListener` | `org.hibernate.event.spi` | Contract nhận post-insert event |
| `IntegratorProvider` | `org.hibernate.jpa.boot.spi` | Cung cấp Integrators khi JPA bootstrap |
| `BootstrapServiceRegistryBuilder` | `org.hibernate.boot.registry` | Tạo bootstrap registry với Integrator thủ công |

Phần lớn các class này thuộc SPI, không phải những API nên xuất hiện tràn lan trong service/repository nghiệp vụ.

## 4. Contract `Integrator` trong Hibernate 6.6

Chữ ký chính:

~~~java
public interface Integrator {

    default void integrate(
            Metadata metadata,
            BootstrapContext bootstrapContext,
            SessionFactoryImplementor sessionFactory) {
        // Đăng ký integration.
    }

    void disintegrate(
            SessionFactoryImplementor sessionFactory,
            SessionFactoryServiceRegistry serviceRegistry);
}
~~~

Đây là bản giản lược để hiểu contract, không phải bản sao đầy đủ source Hibernate.

Trong Hibernate 6.6 còn một overload cũ:

~~~java
integrate(
    Metadata metadata,
    SessionFactoryImplementor sessionFactory,
    SessionFactoryServiceRegistry serviceRegistry
)
~~~

Overload này đã được đánh dấu **deprecated**; dùng signature có `BootstrapContext` trong code 6.x hiện đại.

Hibernate 7.2 vẫn có `integrate(Metadata, BootstrapContext, SessionFactoryImplementor)`, còn `disintegrate(...)` được khai báo default theo Javadocs 7.2. Để dễ nhận diện shutdown hook, ví dụ sẽ override cả hai.

### `Metadata` dùng để làm gì?

Nó chứa metadata mapping được Hibernate tổng hợp, chẳng hạn thông tin về các entities và collections. Đây không phải nơi chứa từng database row hoặc entity instances thuộc một transaction.

### `BootstrapContext` dùng để làm gì?

Nó cung cấp những thành phần có mặt trong quá trình bootstrap. Hibernate 6.6 User Guide có ví dụ lấy registry:

~~~java
EventListenerRegistry registry =
    bootstrapContext.getServiceRegistry()
                    .getService(EventListenerRegistry.class);
~~~

Một cách khác có thể dùng giữa các versions là lấy từ factory service registry:

~~~java
EventListenerRegistry registry =
    sessionFactory.getServiceRegistry()
                  .getService(EventListenerRegistry.class);
~~~

Trong Hibernate 7.x có convenience method:

~~~java
EventListenerRegistry registry =
    sessionFactory.getEventListenerRegistry();
~~~

Không mặc định `getEventListenerRegistry()` tồn tại trong Hibernate 6.x cũ; đây là điểm cần kiểm tra khi nâng cấp.

## 5. Vòng đời bootstrap: tại sao không mở Session trong Integrator?

Một thứ tự khái niệm:

~~~mermaid
flowchart TD
    A["ClassLoader / application bootstrap"] --> B["BootstrapServiceRegistry"]
    B --> C["StandardServiceRegistry"]
    C --> D["Build Metadata"]
    D --> E["Create SessionFactory"]
    E --> F["Integrator.integrate"]
    F --> G["Register event listeners"]
    G --> H["SessionFactory ready"]
    H --> I["Runtime Session events"]
    I --> J["SessionFactory.close"]
    J --> K["Integrator.disintegrate"]
~~~

Tại thời điểm `integrate`, Hibernate đang ở giữa quá trình tạo SessionFactory. Không nên gọi:

~~~java
@Override
public void integrate(
        Metadata metadata,
        BootstrapContext context,
        SessionFactoryImplementor factory) {

    // Sai về thời điểm:
    // factory.openSession().createQuery(...).getResultList();
    // factory.openSession().persist(...);
}
~~~

Làm vậy có thể đụng internal services chưa sẵn sàng hoặc gây reentrant bootstrap.

Integrator nên **đăng ký listener và integration metadata**, không thực thi query hoặc giao dịch nghiệp vụ.

## 6. Use case xuyên suốt: quan sát sự kiện INSERT Product

Giả sử có entity:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true)
    private String sku;

    @Column(name = "name", nullable = false)
    private String name;

    protected Product() {
    }

    public Product(String sku, String name) {
        this.sku = sku;
        this.name = name;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
}
~~~

Mục tiêu: tạo **technical log** khi Hibernate hoàn thành thao tác SQL INSERT cho Product.

Điều cần tránh: coi log này là một sự kiện business đã commit vĩnh viễn. Transaction vẫn có thể rollback sau INSERT.

## 7. Tạo `PostInsertEventListener`

Listener:

~~~java
package com.example.catalog.extension;

import com.example.catalog.domain.Product;
import org.hibernate.event.spi.PostInsertEvent;
import org.hibernate.event.spi.PostInsertEventListener;
import org.hibernate.persister.entity.EntityPersister;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class ProductInsertListener
        implements PostInsertEventListener {

    private static final Logger LOG =
        LoggerFactory.getLogger(ProductInsertListener.class);

    @Override
    public void onPostInsert(PostInsertEvent event) {
        if (!(event.getEntity() instanceof Product product)) {
            return;
        }

        LOG.debug(
            "Hibernate INSERT for Product id={}, sku={}",
            event.getId(),
            product.getSku()
        );
    }

    @Override
    public boolean requiresPostCommitHandling(
            EntityPersister persister) {
        return false;
    }
}
~~~

Giải thích:

- `onPostInsert` xử lý một Hibernate event liên quan INSERT.
- `event.getEntity()` cho phép kiểm tra entity type.
- `event.getId()` là identifier trong event.
- `requiresPostCommitHandling(...)` liên quan việc Hibernate có cần đăng ký after-transaction hook. Với listener ghi log tại INSERT, dùng `false`.
- Việc implement method cuối tường minh giúp code rõ ràng trên các bản Hibernate có sự khác nhau giữa abstract/default methods.

**Log khi POST_INSERT không phải bằng chứng commit.**

## 8. Tạo `CatalogIntegrator`

Integrator sẽ gắn listener vào event registry:

~~~java
package com.example.catalog.extension;

import org.hibernate.boot.Metadata;
import org.hibernate.boot.spi.BootstrapContext;
import org.hibernate.engine.spi.SessionFactoryImplementor;
import org.hibernate.event.service.spi.EventListenerRegistry;
import org.hibernate.event.spi.EventType;
import org.hibernate.integrator.spi.Integrator;
import org.hibernate.service.spi.SessionFactoryServiceRegistry;

public final class CatalogIntegrator implements Integrator {

    @Override
    public void integrate(
            Metadata metadata,
            BootstrapContext bootstrapContext,
            SessionFactoryImplementor sessionFactory) {

        EventListenerRegistry registry =
            sessionFactory.getServiceRegistry()
                          .getService(EventListenerRegistry.class);

        registry.appendListeners(
            EventType.POST_INSERT,
            new ProductInsertListener()
        );
    }

    @Override
    public void disintegrate(
            SessionFactoryImplementor sessionFactory,
            SessionFactoryServiceRegistry serviceRegistry) {
        // Không có integration-owned resource để đóng.
    }
}
~~~

Code sử dụng `SessionFactoryImplementor.getServiceRegistry()` và `EventListenerRegistry` thay vì convenience method chỉ có trong một số versions.

`appendListeners(...)` thêm listener vào cuối event group. Nhưng Hibernate phải **biết Integrator này** lúc bootstrap thì method `integrate(...)` mới được gọi.

Sau đây là những cơ chế đăng ký.

## 9. Cách 1 — Đăng ký tự động với Java `ServiceLoader`

Đây là cách Hibernate Javadocs khuyến nghị để một integration library có thể được phát hiện từ classpath.

Cấu trúc:

~~~text
src/main/java/
  com/example/catalog/extension/
    CatalogIntegrator.java
    ProductInsertListener.java

src/main/resources/
  META-INF/
    services/
      org.hibernate.integrator.spi.Integrator
~~~

Nội dung file:

~~~text
com.example.catalog.extension.CatalogIntegrator
~~~

**Điều kiện:**

1. File tên chính xác `org.hibernate.integrator.spi.Integrator`, không có `.txt`.
2. Resource nằm trong `META-INF/services` của runtime JAR/classpath.
3. Nội dung là tên đầy đủ class provider, mỗi dòng một provider.
4. Class là concrete, loadable và có no-argument constructor phù hợp ServiceLoader.
5. Classpath có Hibernate version tương thích.
6. Hibernate ClassLoaderService thấy resource và class.
7. Không có lỗi packaging/shading làm mất service descriptor.

Khi app khởi động và tạo SessionFactory, Hibernate phát hiện provider qua Java ServiceLoader và gọi `integrate(...)`.

### Vì sao chỉ viết class không đủ?

Chỉ có:

~~~java
public class CatalogIntegrator implements Integrator {
    // ...
}
~~~

không tự khiến Hibernate quét tất cả class trong classpath để tìm Integrator. Cần descriptor hoặc một cơ chế đăng ký khác.

### Spring `@Component` cũng không tự đủ

~~~java
@Component
public class CatalogIntegrator implements Integrator {
    // ...
}
~~~

Spring có thể tạo bean nhưng Hibernate không mặc định lấy tất cả bean implement Integrator từ ApplicationContext. ServiceLoader và Spring bean scanning là hai hệ discovery khác nhau.

## 10. ServiceLoader trong library JAR và lỗi shading

Một JAR reusable:

~~~text
catalog-hibernate-extension.jar
  com/example/catalog/extension/CatalogIntegrator.class
  com/example/catalog/extension/ProductInsertListener.class
  META-INF/services/org.hibernate.integrator.spi.Integrator
~~~

Khi ứng dụng thêm JAR, Integrator có thể được tự phát hiện nếu Hibernate classloader thấy nó.

Một vấn đề khi build executable/fat/uber JAR là **nhiều dependencies cùng có service descriptor cùng tên**. Nếu shading plugin ghi đè một resource bằng resource khác, provider entries của thư viện có thể mất.

Kiểm tra:

- Final artifact chứa `META-INF/services/org.hibernate.integrator.spi.Integrator` không?
- File có đúng FQCN?
- Shading plugin có merge các ServiceLoader files không?
- Có relocate package nhưng quên rewrite service descriptor không?
- Có duplicate class/provider trên classpath không?

Thư viện chạy tốt trong IDE chưa chắc ServiceLoader được đóng gói đúng trong fat JAR. Runtime integration test nên chạy trên artifact thật.

## 11. Cách 2 — `BootstrapServiceRegistryBuilder.applyIntegrator`

Nếu ứng dụng **tự xây native SessionFactory**, có thể đăng ký Integrator instance trực tiếp:

~~~java
import org.hibernate.SessionFactory;
import org.hibernate.boot.MetadataSources;
import org.hibernate.boot.registry.BootstrapServiceRegistry;
import org.hibernate.boot.registry.BootstrapServiceRegistryBuilder;
import org.hibernate.boot.registry.StandardServiceRegistry;
import org.hibernate.boot.registry.StandardServiceRegistryBuilder;

BootstrapServiceRegistry bootstrapRegistry =
    new BootstrapServiceRegistryBuilder()
        .applyIntegrator(new CatalogIntegrator())
        .build();

StandardServiceRegistry standardRegistry =
    new StandardServiceRegistryBuilder(bootstrapRegistry)
        .configure("hibernate.cfg.xml")
        .build();

try {
    try (SessionFactory sessionFactory =
             new MetadataSources(standardRegistry)
                 .addAnnotatedClass(Product.class)
                 .buildMetadata()
                 .buildSessionFactory()) {

        // Dùng SessionFactory với listener đã đăng ký.
    }
} finally {
    StandardServiceRegistryBuilder.destroy(standardRegistry);
}
~~~

Ví dụ giả định file `hibernate.cfg.xml` và database đã được cấu hình đầy đủ.

Dùng cách này khi:

- Tự bootstrap native Hibernate (không nhờ Spring).
- Muốn truyền dependency cụ thể vào Integrator constructor.
- Muốn bật/tắt extension ở test hoặc theo config runtime.
- Muốn build factory với một set Integrators được chỉ định rõ.

### Chú ý tên method

Hibernate 6.x/7.x sử dụng `applyIntegrator(Integrator)` trên `BootstrapServiceRegistryBuilder`. Tài liệu Hibernate cũ có thể đề cập `with(Integrator)`; cần dùng đúng API của target version.

Phải đăng ký **trước khi build SessionFactory**. Khi factory đã hoạt động, thêm Integrator vào một builder khác không tác động ngược tới factory hiện tại.

## 12. Cách 3 — JPA `IntegratorProvider`

Khi ứng dụng dùng Hibernate như JPA provider, một property Hibernate cho phép cung cấp danh sách Integrators:

~~~text
hibernate.integrator_provider
~~~

Ví dụ:

~~~java
import java.util.List;
import java.util.Map;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;
import org.hibernate.jpa.boot.spi.IntegratorProvider;
import org.hibernate.jpa.boot.spi.JpaSettings;

Map<String, Object> properties = Map.of(
    JpaSettings.INTEGRATOR_PROVIDER,
    (IntegratorProvider) () ->
        List.of(new CatalogIntegrator())
);

EntityManagerFactory emf =
    Persistence.createEntityManagerFactory(
        "catalogPersistenceUnit",
        properties
    );

try {
    // Dùng EntityManager.
} finally {
    emf.close();
}
~~~

`JpaSettings.INTEGRATOR_PROVIDER` là constant cho key `hibernate.integrator_provider` trên các Hibernate versions hỗ trợ. Provider contract trả `List<Integrator>`.

**Đây là Hibernate-specific JPA bootstrap property**, không phải một key chuẩn Jakarta Persistence. Provider khác Hibernate không bắt buộc hiểu property này.

### Đừng nhầm text và instance

Một string trong `application.properties`:

~~~properties
hibernate.integrator_provider=com.example.CatalogIntegrator
~~~

không được bảo đảm tự chuyển thành `IntegratorProvider` object. Khi cần provider có constructor dependencies hoặc trả nhiều integrators, cung cấp object thông qua bootstrap properties/customizer.

## 13. Cách 4 — Spring Boot `HibernatePropertiesCustomizer`

Spring Boot cung cấp hook để tùy biến Hibernate vendor properties trước khi auto-configured EntityManagerFactory được tạo.

Với **Spring Boot 3.x**:

~~~java
package com.example.catalog.config;

import java.util.List;
import org.hibernate.jpa.boot.spi.IntegratorProvider;
import org.hibernate.jpa.boot.spi.JpaSettings;
import org.springframework.boot.autoconfigure.orm.jpa.HibernatePropertiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogHibernateConfiguration {

    @Bean
    HibernatePropertiesCustomizer integratorCustomizer() {
        return properties -> properties.put(
            JpaSettings.INTEGRATOR_PROVIDER,
            (IntegratorProvider) () ->
                List.of(new CatalogIntegrator())
        );
    }
}
~~~

Từ **Spring Boot 4.x**, package của `HibernatePropertiesCustomizer` đã được chuyển theo modular auto-configuration:

~~~java
import org.springframework.boot.hibernate.autoconfigure.HibernatePropertiesCustomizer;
~~~

Không dùng nhầm import Boot 4 với dự án Boot 3. Cấu hình phiên bản dependency và Spring Boot BOM cần tương thích Hibernate ORM version.

Khi có nhiều EntityManagerFactory tùy biến, phải bảo đảm customizer được áp dụng cho đúng factory. Không tự động giả định mọi factory đều nhận cùng một IntegratorProvider.

## 14. Truyền dependency của Spring vào listener

Một Integrator được tạo bởi ServiceLoader thường phải có no-arg constructor, vì vậy nó không tự nhận Spring constructor injection.

Nếu listener cần metrics service, có thể tạo Integrator bằng Java code và truyền dependency vào:

~~~java
public interface AuditSink {
    void observed(String entityName, Object entityId);
}

public final class TechnicalInsertListener
        implements PostInsertEventListener {

    private final AuditSink sink;

    public TechnicalInsertListener(AuditSink sink) {
        this.sink = sink;
    }

    @Override
    public void onPostInsert(PostInsertEvent event) {
        sink.observed(
            event.getPersister().getEntityName(),
            event.getId()
        );
    }

    @Override
    public boolean requiresPostCommitHandling(
            EntityPersister persister) {
        return false;
    }
}
~~~

Integrator:

~~~java
public final class AuditIntegrator implements Integrator {

    private final AuditSink sink;

    public AuditIntegrator(AuditSink sink) {
        this.sink = sink;
    }

    @Override
    public void integrate(
            Metadata metadata,
            BootstrapContext context,
            SessionFactoryImplementor factory) {

        EventListenerRegistry registry =
            factory.getServiceRegistry()
                   .getService(EventListenerRegistry.class);

        registry.appendListeners(
            EventType.POST_INSERT,
            new TechnicalInsertListener(sink)
        );
    }

    @Override
    public void disintegrate(
            SessionFactoryImplementor factory,
            SessionFactoryServiceRegistry registry) {
    }
}
~~~

Spring:

~~~java
@Bean
HibernatePropertiesCustomizer auditIntegratorCustomizer(
        AuditSink sink) {

    return properties -> properties.put(
        JpaSettings.INTEGRATOR_PROVIDER,
        (IntegratorProvider) () ->
            List.of(new AuditIntegrator(sink))
    );
}
~~~

Ở đây `AuditSink` cần thread-safe nếu listener được chia sẻ cho nhiều Sessions. Nếu nó gửi HTTP/message bên ngoài DB, còn phải xử lý vấn đề transaction rollback và exactly-once/durable delivery; xem các phần tiếp theo.

### Vì sao tránh static ApplicationContextHolder?

Một Integrator gọi:

~~~java
ApplicationContextHolder.getBean(AuditSink.class)
~~~

ở bootstrap tạo coupling với Spring global state, tăng nguy cơ lỗi initialization order, làm khó test hoặc sử dụng plugin trong ứng dụng không chạy Spring. Constructor injection từ provider object thường rõ ràng hơn.

## 15. Ba cách đăng ký trong `EventListenerRegistry`

`EventListenerRegistry` quản lý các event groups theo `EventType`.

~~~java
EventListenerRegistry registry =
    factory.getServiceRegistry()
           .getService(EventListenerRegistry.class);
~~~

Các thao tác:

~~~java
registry.appendListeners(
    EventType.POST_INSERT,
    new ProductInsertListener()
);

registry.prependListeners(
    EventType.PRE_UPDATE,
    new CustomPreUpdateListener()
);

registry.setListeners(
    EventType.PERSIST,
    new CompletePersistReplacementListener()
);
~~~

Các class ngoài `ProductInsertListener` trong đoạn trên là **placeholder cho implementations theo đúng listener interface**. Ba câu là minh họa riêng biệt, không nên copy đồng thời.

| API | Tác động | Nên dùng khi |
| --- | --- | --- |
| `appendListeners(type, ...)` | Thêm cuối listener group | Quan sát/đăng ký thêm hành vi |
| `prependListeners(type, ...)` | Thêm đầu listener group | Có lý do về thứ tự |
| `setListeners(type, ...)` | Thay toàn bộ group | Cực kỳ hiếm; biết rõ default contract |
| `addDuplicationStrategy(...)` | Xử lý listeners đăng ký trùng | Nhiều nguồn registration |

**Ưu tiên append/prepend thay vì setListeners** nếu chỉ thêm một listener. Thay listeners có sẵn có thể loại các default handlers cần thiết để Hibernate hoạt động.

## 16. Tại sao `setListeners` nguy hiểm?

Hibernate default event listeners thực thi hoặc hỗ trợ nhiều logic cốt lõi:

- Entity state transition.
- Persist, merge, delete và cascade.
- Flush/action queue.
- Loading và session bookkeeping.
- JPA callbacks.
- Interceptor invocation đúng điểm.
- Một số integration của Hibernate modules.

Ví dụ không nên làm chỉ để log:

~~~java
registry.setListeners(
    EventType.PERSIST,
    new MyLoggingPersistListener()
);
~~~

Nếu `MyLoggingPersistListener` không tái hiện hành vi mặc định, persist/cascade hoặc callback khác có thể hỏng.

Thay bằng listener ở event thích hợp:

~~~java
registry.appendListeners(
    EventType.POST_INSERT,
    new ProductInsertListener()
);
~~~

Dùng `setListeners` chỉ khi bạn đang **chủ động thay implementation gốc** và hiểu toàn bộ contract của Hibernate version tương ứng. Việc kế thừa/delegate default listener cũng phải được kiểm thử, không bảo đảm tự động tương đương về mọi side effect.

## 17. Duplicate registration và duplication strategy

Có thể xảy ra:

~~~text
META-INF/services
    -> CatalogIntegrator
         -> ProductInsertListener

Spring IntegratorProvider
    -> CatalogIntegrator
         -> ProductInsertListener
~~~

Nếu hai integration paths cùng được dùng, một INSERT có thể kích hoạt listener hai lần hoặc gây lỗi duplicate registration tùy EventListenerRegistry strategy.

Hibernate hỗ trợ thêm một `DuplicationStrategy`:

~~~java
registry.addDuplicationStrategy(
    new CustomDuplicationStrategy()
);
~~~

`CustomDuplicationStrategy` là implementation của `org.hibernate.event.service.spi.DuplicationStrategy`. Nó định nghĩa thế nào là listener trùng và chọn cách xử lý như báo lỗi, giữ bản gốc hoặc thay bản gốc theo contract.

Không phải mọi app cần custom strategy. Thường giải pháp đơn giản nhất là **đăng ký một Integrator theo đúng một đường**. Nếu plugin system cần nhiều đường, hãy có chính sách duplicate rõ ràng.

### Không dùng static flag toàn JVM

Anti-pattern:

~~~java
private static boolean registered;

@Override
public void integrate(...) {
    if (registered) {
        return;
    }
    registered = true;
}
~~~

Một JVM có thể có nhiều SessionFactories. Static flag có thể khiến factory thứ hai **không được đăng ký listener**; còn có race condition nếu nhiều factories bootstrap đồng thời.

Listener registration thuộc phạm vi **factory/registry**, không phải một global boolean.

## 18. Thứ tự listeners và module độc lập

Nếu một event group có:

~~~text
EventType.POST_INSERT
    DefaultListener
    MetricsListener
    AuditListener
~~~

thứ tự thực thi có thể ảnh hưởng kết quả khi listeners phụ thuộc nhau. `appendListeners` thêm cuối, `prependListeners` thêm đầu.

Nhưng không được xây business rule dựa trên thứ tự discovery của **nhiều independent Integrators từ nhiều JAR** nếu không có contract bảo đảm.

Nếu AuditListener phải chạy trước MetricsListener, có thể:

- Đăng ký cả hai theo thứ tự tường minh từ một Integrator.
- Tạo một composite listener điều phối.
- Không đặt dependency quan trọng giữa hai plugins độc lập.
- Test với version/classpath thực tế.
- Không để hai listeners cùng thay entity state bất đồng.

Việc listener ở đầu hoặc cuối group còn ảnh hưởng nó quan sát trạng thái trước/sau default handler. Phải chọn EventType và thời điểm chính xác.

## 19. Những EventType thường dùng

| EventType | Ý nghĩa tổng quát |
| --- | --- |
| `PERSIST` | Xử lý yêu cầu persist entity |
| `MERGE` | Xử lý merge entity state |
| `DELETE` | Xử lý yêu cầu delete |
| `LOAD` | Xử lý entity load |
| `PRE_INSERT` | Trước SQL INSERT |
| `POST_INSERT` | Sau SQL INSERT |
| `PRE_UPDATE` | Trước SQL UPDATE |
| `POST_UPDATE` | Sau SQL UPDATE |
| `PRE_DELETE` | Trước SQL DELETE |
| `POST_DELETE` | Sau SQL DELETE |
| `POST_LOAD` | Entity đã load |
| `FLUSH` | Flush processing |
| `AUTO_FLUSH` | Auto-flush decision/processing |
| `PRE_COLLECTION_UPDATE` | Trước collection update |
| `POST_COLLECTION_UPDATE` | Sau collection update |
| `POST_COLLECTION_RECREATE` | Sau collection create |
| `POST_COLLECTION_REMOVE` | Sau collection remove |

Không phải mọi Hibernate event tương ứng một public Session method. Một `persist` call có thể dẫn đến INSERT sau đó trong flush; cascade còn có thể tạo thêm operations.

Collection events có thể quan trọng khi muốn audit ManyToMany membership, vì thay đổi liên kết không nhất thiết gây entity `POST_UPDATE` trên mỗi phía.

## 20. Veto semantics của `PreInsertEventListener`

Một ví dụ:

~~~java
import org.hibernate.event.spi.PreInsertEvent;
import org.hibernate.event.spi.PreInsertEventListener;

public final class ProductInsertGuard
        implements PreInsertEventListener {

    @Override
    public boolean onPreInsert(PreInsertEvent event) {
        if (!(event.getEntity() instanceof Product product)) {
            return false;
        }

        if (product.getSku() == null
                || product.getSku().isBlank()) {
            return true;  // veto
        }

        return false;     // không veto
    }
}
~~~

Có thể đăng ký:

~~~java
registry.prependListeners(
    EventType.PRE_INSERT,
    new ProductInsertGuard()
);
~~~

**`true` trong `onPreInsert` nghĩa là veto INSERT.** Không nhầm nó với boolean “validation passed”.

Chú ý: Hibernate veto cơ chế cấp thấp không thay thế validation ở service/domain hoặc Jakarta Bean Validation. Nếu yêu cầu nghiệp vụ cần lỗi rõ cho người dùng, validation exception thường phù hợp hơn việc âm thầm veto một database operation.

## 21. POST_INSERT không phải sau commit

Luồng đơn giản:

~~~text
transaction.begin()
    |
    v
session.persist(product)
    |
    v
flush() / SQL INSERT
    |
    v
POST_INSERT listener
    |
    +── technical log hoặc metric
    |
    v
transaction.commit() hoặc rollback()
~~~

Ví dụ:

~~~java
Transaction tx = session.beginTransaction();

Product product = new Product("P-001", "Notebook");
session.persist(product);
session.flush();

tx.rollback();
~~~

Listener có thể đã log rằng SQL INSERT được thực hiện, nhưng transaction rollback khiến row không tồn tại sau cùng. Với IDENTITY generator, một số INSERT có thể diễn ra sớm để lấy generated ID.

**Không dùng callback POST_INSERT như một sự kiện nghiệp vụ “đã lưu thành công và commit”**. Đó là hai thời điểm khác nhau.

## 22. Post-commit listener và giới hạn delivery

Hibernate cung cấp các post-commit event contracts như `PostCommitInsertEventListener` trên các phiên bản có hỗ trợ.

Nhưng kể cả một callback chạy sau commit:

- Nếu process chết ngay sau DB commit nhưng trước callback, message có thể không được gửi.
- Nếu gửi message xong mà client không nhận acknowledgment, retry có thể tạo duplicate.
- Lỗi mạng hoặc broker outage có thể làm delivery thất bại.
- Không tự có exactly-once cross-system guarantee.

Với sự kiện cần bền vững, dùng **transactional outbox** hoặc một hệ thống transaction/CDC phù hợp:

~~~text
Business transaction
    |
    +── INSERT/UPDATE domain rows
    |
    +── INSERT outbox event row
    |
    v
Database COMMIT
    |
    v
Outbox relay/CDC
    |
    v
Message broker
    |
    v
Consumer idempotent
~~~

Integrator có thể hỗ trợ instrumentation, nhưng không tự biến Hibernate POST_INSERT thành một hệ thống event bus bền vững.

## 23. Listener concurrency và thread-safety

Một listener gắn với factory có thể được gọi bởi nhiều Sessions/threads. Vì Hibernate Session không thread-safe, listener cũng không nên giữ Session/entity references dùng chéo request.

Anti-pattern:

~~~java
public final class BadListener implements PostInsertEventListener {
    private long count;

    @Override
    public void onPostInsert(PostInsertEvent event) {
        count++; // Race condition.
    }

    @Override
    public boolean requiresPostCommitHandling(
            EntityPersister persister) {
        return false;
    }
}
~~~

Dùng `LongAdder` hoặc metrics backend thread-safe nếu cần đếm events:

~~~java
private final LongAdder count = new LongAdder();

@Override
public void onPostInsert(PostInsertEvent event) {
    count.increment();
}
~~~

Lưu ý bộ đếm này đếm **POST_INSERT events**, không nhất thiết đếm rows đã committed sau transaction rollback.

Không lưu object `event.getEntity()` vào static list/global cache, vì có thể giữ object graph lớn và trộn dữ liệu giữa tenants/requests.

## 24. Tránh thao tác reentrant trong Hibernate listener

Listener có thể chạy khi Hibernate đang flush action queue. Đừng tùy tiện:

~~~java
@Override
public void onPostInsert(PostInsertEvent event) {
    // Nguy cơ:
    // event.getSession().persist(new AuditRecord(...));
    // event.getSession().flush();
}
~~~

Những hành động trên có thể tạo:

- Reentrant flush.
- Recursive event calls.
- Action queue modification trong khi đang xử lý.
- Cascade bất ngờ.
- Session inconsistent state.
- Transaction kéo dài hoặc deadlock.

Nếu cần audit entities, cân nhắc Hibernate Envers. Nếu muốn gửi domain events bền vững, cân nhắc service + outbox thay vì viết JDBC/network trong callback.

Nếu thật sự phải mutate state trong pre-event contract, cần hiểu Hibernate state array/entity state synchronization, versioning và listeners chain theo đúng phiên bản.

## 25. Bulk mutation và native SQL có phát entity events không?

Một câu bulk HQL:

~~~java
int updated = session.createMutationQuery(
    "update Product p " +
    "set p.name = :name " +
    "where p.id = :id"
)
.setParameter("name", "Changed")
.setParameter("id", 42L)
.executeUpdate();
~~~

không đi qua entity-by-entity dirty checking giống việc load Product, set field và flush. Vì vậy **không được mặc định `POST_UPDATE` listener chạy cho từng Product**.

Native SQL và JDBC trực tiếp cũng không tự kích hoạt Hibernate entity lifecycle callbacks tương ứng.

Nếu yêu cầu nghiệp vụ là audit **mọi dữ liệu thay đổi ở database**, cần thêm hướng database audit trigger, CDC hoặc kiểm soát tất cả writers, không chỉ Hibernate listener.

Collection changes cũng có event types riêng, không nhất thiết phát entity update cho tất cả linked entities.

## 26. Integrator và `@EntityListeners` của JPA

Nếu chỉ muốn thao tác đơn giản ở một entity:

~~~java
@Entity
@EntityListeners(ProductLifecycleListener.class)
public class Product {
    // ...
}
~~~

~~~java
public class ProductLifecycleListener {

    @PrePersist
    public void beforePersist(Product product) {
        // JPA callback.
    }

    @PostPersist
    public void afterPersist(Product product) {
        // JPA callback.
    }
}
~~~

**JPA callbacks** có ưu điểm:

- Portable giữa các JPA providers.
- Dễ gắn với từng entity/hierarchy.
- Không cần ServiceLoader hoặc Integrator.
- Phù hợp normalization/validation đơn giản.

**Hibernate Integrator/event listeners** phù hợp hơn khi:

- Muốn extension hoạt động ở cấp SessionFactory.
- Viết reusable library tách khỏi entity annotations.
- Cần Hibernate-specific event metadata.
- Cần collection events, listener ordering hoặc registry access.
- Muốn đăng ký cùng lúc nhiều event types.

Không dùng SPI cấp thấp chỉ vì có thể dùng; chọn abstraction đơn giản nhất đáp ứng use case.

## 27. Integrator và `Interceptor`

Hibernate `org.hibernate.Interceptor` cung cấp một bộ callbacks liên quan tới Session/entity events.

| Tiêu chí | `Integrator` | `Interceptor` | Hibernate event listener |
| --- | --- | --- | --- |
| Vai trò chính | Đăng ký integration khi bootstrap | Hook hoạt động Session/ORM | Xử lý event type cụ thể |
| Thời điểm chính | SessionFactory construction | Runtime | Runtime |
| Đăng ký plugin | Có | Không phải vai trò chính | Do plugin/registry đăng ký |
| Dữ liệu event | Metadata/registry | Interceptor callback arguments | Event-specific objects |
| Portable JPA | Không | Không | Không |

Nếu đã có một Interceptor hook đáp ứng nhu cầu, có thể không cần Integrator. Nếu cần nhiều listener groups hoặc đóng gói một plugin tự đăng ký, Integrator là cơ chế phù hợp.

## 28. Integrator khác ServiceContributor và TypeContributor

Hibernate có nhiều extension points cho **các giai đoạn bootstrap khác nhau**:

| Nhu cầu | Cơ chế nên cân nhắc |
| --- | --- |
| Đăng ký event listeners lúc factory khởi tạo | `Integrator` |
| Thêm service vào registry | `ServiceContributor` / service initiator phù hợp |
| Đăng ký custom Java/JDBC types | `TypeContributor` |
| Đăng ký SQL/HQL functions | `FunctionContributor` |
| Đóng góp mappings trước metadata completion | `AdditionalMappingContributor` hoặc boot mapping SPI |
| Đăng ký short-name strategy | `StrategyRegistrationProvider` |
| Xử lý callback entity theo JPA | `@EntityListeners` |
| Giao tiếp cross-system sau commit | Transactional outbox/message relay |

**Integrator không phải hook để sửa tất cả metadata sau khi nó đã được compiled.** Nếu muốn metadata builder nhìn thấy một type/function/mapping, phải đăng ký ở giai đoạn sớm phù hợp.

Đừng dùng `Integrator.integrate` để chạy DDL, thêm cột hoặc thay thế migration tool.

## 29. Các registry trong Hibernate

Khái niệm:

~~~text
BootstrapServiceRegistry
  - ClassLoaderService
  - Integrator discovery
  - Strategy selection
          |
          v
StandardServiceRegistry
  - Infrastructure services
  - JDBC services
          |
          v
Metadata / mappings
          |
          v
SessionFactoryServiceRegistry
  - Services gắn SessionFactory
  - EventListenerRegistry
          |
          v
Runtime SessionFactory
~~~

Đây là sơ đồ tổ chức khái niệm. Chi tiết service placement có thể khác theo Hibernate version.

Ý nghĩa kiến trúc:

- Một số services cần có **trước** metadata building.
- Một số components chỉ có ý nghĩa khi SessionFactory được tạo.
- Integrator được gọi khi factory đang khởi tạo, không phải ngay khi application JVM launch.
- Runtime listeners được giữ bởi registry của factory, không phải bởi mỗi EntityManager độc lập.

## 30. `disintegrate` và cleanup

Nếu Integrator sở hữu tài nguyên riêng, dùng shutdown hook:

~~~java
public final class MetricsIntegrator implements Integrator {

    private MetricsCollector collector;

    @Override
    public void integrate(
            Metadata metadata,
            BootstrapContext context,
            SessionFactoryImplementor factory) {

        collector = new MetricsCollector();

        factory.getServiceRegistry()
               .getService(EventListenerRegistry.class)
               .appendListeners(
                   EventType.POST_INSERT,
                   new MetricsInsertListener(collector)
               );
    }

    @Override
    public void disintegrate(
            SessionFactoryImplementor factory,
            SessionFactoryServiceRegistry registry) {

        if (collector != null) {
            collector.close();
            collector = null;
        }
    }
}
~~~

`MetricsCollector`/`MetricsInsertListener` là classes minh họa do ứng dụng định nghĩa.

**Ownership quan trọng:** nếu collector được inject từ Spring và dùng chung với nơi khác, Integrator không được tự đóng nó. Nếu một Integrator instance được chia sẻ giữa nhiều factories, một field `collector` duy nhất có thể gây nhầm lẫn lifecycle; nên thiết kế state theo factory hoặc tránh mutable state.

Không lưu SessionFactory vào static map sống mãi nếu không có cơ chế cleanup.

## 31. Tích hợp nhiều SessionFactory

Một ứng dụng có thể có:

~~~text
Catalog SessionFactory
  -> Catalog Integrator
  -> Registry A

Reporting SessionFactory
  -> Reporting Integrator
  -> Registry B
~~~

Mỗi factory cần listeners của chính nó. Một `registered` flag global có thể khiến factory thứ hai không được đăng ký.

Ngoài ra:

- JPA `IntegratorProvider` có thể phải được áp dụng riêng cho từng factory.
- Spring customizers không nhất thiết áp dụng cho factories tự tạo không đi qua auto-config.
- Event listener instance có thể được gọi đồng thời ở nhiều threads.
- Không mặc định shutdown factory A được phép đóng shared service do factory B đang dùng.

Registration và cleanup phải gắn với **đúng lifecycle**.

## 32. Bật/tắt extension theo cấu hình

Ví dụ Spring Boot 3.x, dùng một configuration object do app định nghĩa:

~~~java
@Configuration(proxyBeanMethods = false)
public class HibernateExtensionConfiguration {

    @Bean
    HibernatePropertiesCustomizer integratorCustomizer(
            ExtensionSettings settings) {

        return properties -> {
            if (!settings.enabled()) {
                return;
            }

            properties.put(
                JpaSettings.INTEGRATOR_PROVIDER,
                (IntegratorProvider) () ->
                    List.of(new CatalogIntegrator())
            );
        };
    }
}
~~~

`ExtensionSettings` là type minh họa của ứng dụng. Việc chọn Integrator diễn ra **trước khi SessionFactory được xây**, không thể dùng cùng customizer để bật/tắt listener của factory đang hoạt động giữa requests.

Nếu cần runtime feature toggle, có thể để listener đọc feature flag thread-safe, nhưng phải xử lý consistency, performance và business semantics. Không tùy tiện chỉnh EventListenerRegistry sau bootstrap khi nhiều Sessions đang dùng nó.

### Nhiều customizers cùng ghi một key

Nếu hai modules đều:

~~~java
properties.put(
    JpaSettings.INTEGRATOR_PROVIDER,
    provider
);
~~~

Map value có thể bị ghi đè, không tự merge. Một ứng dụng phức tạp nên có một aggregator:

~~~java
List<Integrator> integrators = List.of(
    new CatalogIntegrator(),
    new MetricsIntegrator()
);

properties.put(
    JpaSettings.INTEGRATOR_PROVIDER,
    (IntegratorProvider) () -> integrators
);
~~~

`MetricsIntegrator` là class minh họa. Cách này rõ ràng hơn hai beans cùng ghi property key và phụ thuộc order.

## 33. Classloading và JPMS

ServiceLoader discovery phụ thuộc classloader visibility.

Các môi trường có thể khác nhau:

- Java classpath.
- Spring Boot executable JAR.
- Application server modules.
- OSGi.
- Java Platform Module System.
- Plugin classloaders riêng.

Ở classpath truyền thống, descriptor `META-INF/services/...` là cách phổ biến. Với explicit Java modules, có thể cần khai báo `provides ... with ...` ở `module-info.java`:

~~~java
module com.example.catalog.extension {
    requires org.hibernate.orm.core;

    provides org.hibernate.integrator.spi.Integrator
        with com.example.catalog.extension.CatalogIntegrator;
}
~~~

Tên module thực tế cần xác nhận theo Hibernate artifact/version. Đoạn này minh họa nguyên tắc `provides` của JPMS, không phải cấu hình JPMS universal cho mọi app.

Nếu gặp ServiceLoader không tìm thấy provider, kiểm tra module path/classpath, resource packaging, no-arg constructor, FQCN và provider visibility.

## 34. Hibernate 5.x, 6.x và 7.x không có SPI hoàn toàn giống nhau

| Khía cạnh | Hibernate 5.x | Hibernate 6.6 | Hibernate 7.2 |
| --- | --- | --- | --- |
| Integrator lifecycle | Có | Có | Có |
| Signature mới có `BootstrapContext` | Tùy minor/version | Có | Có |
| Overload cũ nhận service registry | Phổ biến ở các bản cũ | Deprecated | Có thể thay đổi/loại bỏ |
| `sessionFactory.getEventListenerRegistry()` | Không mặc định | Không phải method tương tự 7.x | Có |
| `disintegrate` abstract/default | Tùy version | Abstract | Default |
| ServiceLoader discovery | Có | Được khuyến nghị | Được khuyến nghị |
| Registry/event SPI | Theo phiên bản | 6.x | 7.x |

Không sao chép code Hibernate 5.x sang 7.x chỉ bằng cách đổi `javax.persistence` thành `jakarta.persistence`. Integrator, event contracts và bootstrap service registry cũng có thay đổi.

Một library extension nên công bố rõ Hibernate version range đã được kiểm thử.

## 35. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `integrate` không chạy | Chưa đăng ký provider | Kiểm tra ServiceLoader, bootstrap builder hoặc IntegratorProvider |
| `@Component` nhưng Hibernate không thấy | Spring bean scanning khác Hibernate SPI discovery | Cung cấp HibernatePropertiesCustomizer |
| `ServiceConfigurationError` | FQCN sai, class không load được, thiếu ctor | Kiểm tra META-INF/services và classpath |
| Chạy trong IDE, lỗi packaged JAR | Service descriptors bị mất khi shade | Merge/rewrite service files |
| Code 5.x không compile ở 6.x | Signature deprecated/removed | Đối chiếu Javadocs |
| `getEventListenerRegistry()` không có | Dùng convenience API ở version cũ | Lấy registry từ service registry |
| Listener không gọi khi persist | Chưa flush, chọn sai EventType hoặc dùng bulk/native SQL | Kiểm tra lifecycle |
| Một event bị log hai lần | Provider/Integrator đăng ký trùng | Một cơ chế chính hoặc duplication strategy |
| Spring dependency null | ServiceLoader không có DI | Truyền dependency qua IntegratorProvider |
| Persist/merge/cascade hỏng | `setListeners` xóa default handler | Chuyển append/prepend và kiểm thử |
| Message đã gửi nhưng DB rollback | POST_INSERT không phải after-commit | Outbox/transaction-aware design |
| POST_UPDATE không chạy cho bulk HQL | Bulk mutation bypass entity callbacks | Audit ở đường khác |
| Listener gọi flush gây lỗi | Reentrant event handling | Tránh mutate/flush trong listener |
| Lỗi chỉ ở factory thứ hai | Static registered flag | Registration theo mỗi factory |
| Memory leak khi restart | Giữ SessionFactory/listener/classloader reference | Cleanup/disintegrate |
| Nhiều thread cập nhật counter sai | Listener mutable state không thread-safe | Atomic/LongAdder hoặc metrics backend |
| Query từ Integrator lỗi startup | Factory chưa initialized | Chỉ register ở integrate |
| Listener gửi network quá chậm | Blocking I/O trong transaction event | Outbox/async relay |

## 36. Quy trình chọn extension point

~~~mermaid
flowchart TD
    A["Cần mở rộng Hibernate"] --> B{"Chỉ là business code của service?"}
    B -- "Có" --> C["Dùng service/domain"]
    B -- "Không" --> D{"JPA lifecycle callback đủ không?"}
    D -- "Có" --> E["@PrePersist / @PostUpdate / EntityListeners"]
    D -- "Không" --> F{"Cần type, function, mapping trước metadata?"}
    F -- "Có" --> G["TypeContributor / FunctionContributor / mapping SPI"]
    F -- "Không" --> H{"Cần custom service registry?"}
    H -- "Có" --> I["ServiceContributor hoặc service initiator"]
    H -- "Không" --> J{"Cần Hibernate event listener?"}
    J -- "Có" --> K["Listener + Integrator"]
    J -- "Không" --> L["Cân nhắc Interceptor/API khác"]
    K --> M{"Cách bootstrap?"}
    M --> N["ServiceLoader"]
    M --> O["JPA IntegratorProvider / Spring"]
    M --> P["BootstrapServiceRegistryBuilder"]
    N --> Q["Test lifecycle/duplicate/transaction"]
    O --> Q
    P --> Q
~~~

## 37. Bài tập tình huống

**Bài 1.** `integrate(...)` được gọi với mỗi INSERT?

**Đáp án:** Không. Nó được gọi trong bootstrap của SessionFactory; listener `onPostInsert` mới được gọi theo insert events.

**Bài 2.** File nào để ServiceLoader thấy Integrator?

**Đáp án:** `META-INF/services/org.hibernate.integrator.spi.Integrator` chứa FQCN của implementation.

**Bài 3.** Chỉ có `@Component` trên CatalogIntegrator đã đủ chưa?

**Đáp án:** Chưa. Phải đăng ký với Hibernate, ví dụ qua ServiceLoader hoặc IntegratorProvider.

**Bài 4.** Native Hibernate bootstrap dùng method nào?

**Đáp án:** `BootstrapServiceRegistryBuilder.applyIntegrator(integrator)` trước khi build factory.

**Bài 5.** JPA bootstrap property để truyền danh sách Integrators?

**Đáp án:** `hibernate.integrator_provider`, nhận `IntegratorProvider` phù hợp Hibernate version.

**Bài 6.** Spring Boot 3 dùng import customizer nào?

**Đáp án:** `org.springframework.boot.autoconfigure.orm.jpa.HibernatePropertiesCustomizer`. Với Boot 4, package chuyển sang `org.springframework.boot.hibernate.autoconfigure`.

**Bài 7.** Muốn thêm một listener log, chọn `appendListeners` hay `setListeners`?

**Đáp án:** Thường `appendListeners`; `setListeners` có thể loại default listeners.

**Bài 8.** Cùng Integrator đăng ký cả ServiceLoader và Spring provider?

**Đáp án:** Có nguy cơ duplicate listener; chọn một đường chính hoặc policy duplication cụ thể.

**Bài 9.** POST_INSERT đã xảy ra nhưng rollback. Audit log có thể tồn tại không?

**Đáp án:** Có. Event xảy ra trước commit, nên log không chứng minh row được commit.

**Bài 10.** `PreInsertEventListener.onPreInsert` trả true nghĩa gì?

**Đáp án:** Veto insert, không phải validation pass.

**Bài 11.** Có nên gửi Kafka từ PostInsertEventListener nếu cần message durable?

**Đáp án:** Không nên; dùng transactional outbox/relay và consumer idempotent.

**Bài 12.** Bulk HQL update có phát POST_UPDATE từng entity?

**Đáp án:** Không mặc định. Bulk mutation bypass entity-by-entity lifecycle.

**Bài 13.** Static boolean `registered` có tốt khi app có nhiều factories?

**Đáp án:** Không, vì mỗi factory có registry riêng.

**Bài 14.** Cần đăng ký custom SQL function trước metadata compilation, dùng Integrator?

**Đáp án:** Nên dùng `FunctionContributor` hoặc boot extension phù hợp, không chờ integrate.

**Bài 15.** Trong `integrate` mở Session để query metadata ứng dụng có an toàn không?

**Đáp án:** Không; factory chưa fully initialized. Dùng boot metadata/registry và chỉ đăng ký components.

**Bài 16.** Listener tăng shared `long count++` có an toàn không?

**Đáp án:** Không khi nhiều threads gọi; cần thread-safe counter và đặt tên metric đúng event semantics.

**Bài 17.** Vì sao listener có thể làm Hibernate persist bị hỏng?

**Đáp án:** Nếu `setListeners` thay default group, những handler core bị loại, khiến state transitions/cascades/callbacks thay đổi.

**Bài 18.** Khi đóng factory, Integrator phải đóng một Spring singleton được inject không?

**Đáp án:** Không. Chỉ đóng resources do chính integration sở hữu; shared dependency do owner khác quản lý.

## 38. Checklist triển khai

Trước khi viết:

- Xác định use case cần Hibernate SPI hay chỉ service/JPA callback.
- Chọn đúng EventType và điểm thời gian (before SQL, after SQL, after commit).
- Xác định entity/collection events và bulk/native SQL exclusions.
- Kiểm tra tác dụng phụ của callback khi transaction rollback.
- Tránh network I/O hoặc reentrant flush.

Khi tạo listener:

- Triển khai đúng listener contract của Hibernate version.
- Giữ listener thread-safe và ngắn gọn.
- Không lưu managed entities/Session references toàn cục.
- Tránh làm thay đổi business data khi chưa hiểu state array/action queue.
- Không dùng callback như message broker thay thế.

Khi tạo Integrator:

- Dùng `integrate` signature phù hợp.
- Không mở Session/query tại bootstrap.
- Lấy EventListenerRegistry chính xác.
- Ưu tiên `appendListeners`/`prependListeners`.
- Xác định duplicate behavior.
- Cleanup tài nguyên owned ở `disintegrate` khi cần.

Khi đăng ký:

- Chọn một cách chính: ServiceLoader, native builder, JPA provider hoặc Spring customizer.
- Kiểm tra descriptors và fat JAR resource merge.
- Kiểm tra Spring Boot major package.
- Nếu nhiều EntityManagerFactories, đặt provider cho đúng factory.
- Không dùng static global guard sai scope.

Khi phát hành:

- Test Hibernate version được hỗ trợ và đường registration trong artifact thật.
- Kiểm tra persist/merge/cascade default behavior còn hoạt động.
- Kiểm tra duplicate registration và lifecycle nhiều factories.
- Kiểm tra rollback, concurrency, external side effects.
- Quan sát logs/metrics nhưng tránh lộ dữ liệu nhạy cảm.

## 39. Tổng kết

**`Integrator` là điểm tích hợp SPI khi Hibernate tạo `SessionFactory`.** Nó không phải entity callback và không phải nơi thực hiện nghiệp vụ trong transaction.

Những điều quan trọng:

1. `integrate(Metadata, BootstrapContext, SessionFactoryImplementor)` dùng để đăng ký integration, thường qua `EventListenerRegistry`.
2. Hibernate 6.6 và 7.2 có khác biệt nhỏ ở API/overloads; phải kiểm tra đúng Javadocs.
3. `appendListeners` thêm listener; `setListeners` thay group, có thể phá default persistence behavior.
4. ServiceLoader discovery dựa vào `META-INF/services/org.hibernate.integrator.spi.Integrator`.
5. Native bootstrap có `BootstrapServiceRegistryBuilder.applyIntegrator`.
6. JPA Hibernate bootstrap có `hibernate.integrator_provider` và `IntegratorProvider`.
7. Spring Boot có `HibernatePropertiesCustomizer`, với package khác nhau giữa Boot 3 và Boot 4.
8. Một listener phải thread-safe và có lifecycle/transaction semantics rõ ràng.
9. POST_INSERT không tương đương COMMIT, và bulk HQL/native SQL không đi qua mọi entity event hooks.
10. Tránh duplicate registration, static global flags và side effects khó rollback.
11. Nếu cần custom type/function/service/metadata, chọn extension SPI đúng giai đoạn thay vì dùng Integrator cho mọi thứ.
12. Với notification bền vững, dùng outbox/relay phù hợp; Integrator không tự cung cấp delivery guarantee.

Một thiết kế tốt xác định rõ **cần mở rộng ở giai đoạn nào, event nào phải quan sát, ai sở hữu tài nguyên, và ứng dụng sẽ hoạt động ra sao khi transaction rollback hoặc nhiều SessionFactories cùng tồn tại**. Khi trả lời được những câu hỏi đó, Integrator cho phép đóng gói các extension Hibernate linh hoạt mà vẫn bảo toàn những cơ chế cốt lõi của ORM.

## Tài liệu tham khảo

- [Hibernate ORM 6.6 — Integrator Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/integrator/spi/Integrator.html)
- [Hibernate ORM 7.2 — Integrator Javadocs](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/integrator/spi/Integrator.html)
- [Hibernate ORM 6.6 User Guide — Event listeners](https://docs.hibernate.org/orm/6.6/userguide/html_single/)
- [Hibernate ORM 7.2 User Guide — Event listeners](https://docs.hibernate.org/orm/7.2/userguide/html_single/)
- [Hibernate ORM 6.6 — EventListenerRegistry](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/event/service/spi/EventListenerRegistry.html)
- [Hibernate ORM 7.2 — PostInsertEventListener](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/event/spi/PostInsertEventListener.html)
- [Hibernate ORM 6.6 — IntegratorProvider](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/jpa/boot/spi/IntegratorProvider.html)
- [Hibernate ORM Integration Guide](https://docs.hibernate.org/orm/7.2/integrationguide/html_single/)
- [Spring Boot 3.5 — HibernatePropertiesCustomizer](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/orm/jpa/HibernatePropertiesCustomizer.html)
- [Spring Boot 4 — HibernatePropertiesCustomizer](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/hibernate/autoconfigure/HibernatePropertiesCustomizer.html)
