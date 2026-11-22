# Đối chiếu hành vi khi dùng JPA thuần và tích hợp Spring

**Jakarta Persistence (JPA)** là đặc tả về cách ánh xạ entity, quản lý persistence context, thao tác truy vấn và đồng bộ dữ liệu với cơ sở dữ liệu. **Spring Data JPA** và **Spring ORM** cung cấp những lớp tích hợp giúp tạo repository, tiêm `EntityManager`, tổ chức giao dịch, dịch exception và cấu hình hạ tầng thuận tiện hơn.

Một nhầm lẫn phổ biến là coi “JPA thuần” và “Spring Data JPA” như **hai cơ chế persistence khác nhau**. Trong nhiều dự án, cả hai đều sử dụng **cùng JPA provider** (ví dụ Hibernate), cùng JDBC driver và cùng database. Điều thay đổi chủ yếu là **ai tạo/đóng EntityManager, ai bắt đầu/commit transaction, cách gọi repository và cách exceptions đi qua các lớp framework**.

Bài học thuộc chủ đề **Data Persistence Relational Access ORM JPA**, chương **Thực hành tổng hợp**, với đề mục trực tiếp **“Đối chiếu hành vi khi dùng JPA thuần và tích hợp Spring”**.

Sau bài, bạn sẽ biết cách:

1. Dựng cùng một mô hình entity cho JPA `RESOURCE_LOCAL` và Spring Boot + Spring Data JPA.
2. Phân biệt `EntityManagerFactory`, `EntityManager`, Spring-managed proxy và transaction-bound persistence context.
3. Viết một nghiệp vụ theo hai cách nhưng giữ cùng bất biến dữ liệu.
4. So sánh `persist`, `merge`, `remove`, dirty checking với `JpaRepository.save`, `saveAndFlush`, `delete`.
5. Phân biệt flush và commit khi tự quản lý transaction hoặc dùng `@Transactional`.
6. Hiểu rollback rules, propagation, self-invocation, `readOnly`, OSIV và lazy loading.
7. So sánh exception chuẩn JPA/provider với exception translation của Spring.
8. Kiểm thử bằng cùng database/schema, tránh những “khác biệt” thực ra do DDL/transaction test setup.
9. Đối chiếu SQL, concurrency, locks, versioning, performance, connection pool và caching.
10. Chọn API phù hợp mà không phụ thuộc quá mức vào hành vi riêng của framework.

**Ý chính:** *Spring không thay đổi các bảo đảm cốt lõi của JPA. Spring tổ chức và tự động hóa vòng đời resource, giao dịch và repository; muốn so sánh công bằng phải giữ nguyên entity mapping, provider, database và ranh giới transaction.*

---

## 1. Sơ đồ hai hướng triển khai

### 1.1. JPA thuần — application-managed `RESOURCE_LOCAL`

```text
Application service
      |
      | createEntityManager()
      v
EntityManagerFactory
      |
      v
EntityManager
      |
      | getTransaction().begin()
      | persist/find/flush
      | getTransaction().commit()
      | close()
      v
JPA provider (Hibernate, EclipseLink, ...)
      |
      v
JDBC/DataSource -> Database
```

Ứng dụng tự quyết định khi nào tạo và đóng `EntityManager`, bắt đầu/rollback/commit giao dịch, và xử lý lỗi.

### 1.2. Spring Boot + Spring ORM + Spring Data JPA

```text
HTTP endpoint / background job
             |
             v
Spring service bean
      @Transactional
             |
             v
Spring AOP transaction interceptor
             |
             v
JpaTransactionManager
             |
     +-------+-------------+
     |                     |
     v                     v
@PersistenceContext    JpaRepository
EntityManager proxy    implementation
     |                     |
     +----------+----------+
                |
                v
    Transaction-bound EntityManager
                |
                v
       JPA provider -> JDBC -> DB
```

Trong setup thông dụng, `JpaRepository` cũng dùng một `EntityManager` của JPA provider. Spring transaction manager điều phối transaction và persistence context; ứng dụng **không nên tự close** EntityManager được Spring quản lý.

### 1.3. Có thể dùng Spring mà không dùng Spring Data JPA

Bạn có thể dùng:

```java
@Repository
public class InventoryDao {

    @PersistenceContext
    private EntityManager em;
}
```

và gọi trực tiếp JPA `find`, `persist`, `merge`, JPQL, Criteria API. Đây vẫn là **JPA**, nhưng được Spring quản lý resource/transaction.

Do đó nên so sánh ba lớp, không chỉ hai:

| Cách triển khai | API thao tác chính | Ai quản lý transaction/resource? |
| --- | --- | --- |
| JPA thuần RESOURCE_LOCAL | `EntityManager` | Code ứng dụng |
| Spring ORM + JPA | `EntityManager` | Spring transaction manager |
| Spring Data JPA | Repository + JPA | Spring Data/Spring transaction manager |

### 1.4. “JPA thuần” không có nghĩa không được dùng container

Trong Jakarta EE, JPA có thể dùng **container-managed EntityManager** và JTA transaction. Bài dùng **Java SE + RESOURCE_LOCAL** làm phương án thuần để so sánh với Spring thông dụng. Không khẳng định mọi ứng dụng không có Spring đều tự quản lý transaction như Java SE.

---

# Phần I — Một mô hình dữ liệu, hai cách dùng

## 2. Use case: giữ hàng trong tồn kho

Giả sử API nhận lệnh giữ một lượng hàng:

```text
requestId = "req-001"
sku       = "SKU-RED"
quantity  = 3
```

Dữ liệu ban đầu:

```text
inventory_items
sku       | available | version
----------+-----------+--------
SKU-RED   | 100       | 0
```

Sau lần giữ thành công:

```text
inventory_items
sku       | available | version
----------+-----------+--------
SKU-RED   | 97        | 1

stock_movements
request_id | sku       | quantity
-----------+-----------+---------
req-001    | SKU-RED   | 3
```

Yêu cầu:

- Không cho lượng tồn kho âm.
- Không ghi movement nếu không giảm được tồn kho.
- Không giảm tồn kho hai lần khi request được gửi lại với cùng `requestId`.
- Không ghi duplicate `requestId`.
- Hai giao dịch cạnh tranh không được ghi đè sai số tồn.
- Thao tác chỉ thành công khi transaction commit thành công.
- Client không được tự chọn tenant/warehouse trái quyền nếu ứng dụng đa tenant (ví dụ đơn giản ở đây chưa có tenant).

### 2.1. Vì sao chọn use case này?

Nó buộc chúng ta kiểm tra **entity lifecycle, transaction atomicity, idempotency, concurrency và exception handling**, thay vì chỉ kiểm tra một lời gọi `findById`.

---

## 3. Schema PostgreSQL dùng chung

```sql
CREATE TABLE inventory_items (
    sku VARCHAR(100) PRIMARY KEY,
    available INTEGER NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT ck_inventory_nonnegative
        CHECK (available >= 0)
);

CREATE TABLE stock_movements (
    request_id VARCHAR(100) PRIMARY KEY,
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT fk_movement_inventory
        FOREIGN KEY (sku)
        REFERENCES inventory_items(sku),
    CONSTRAINT ck_movement_positive
        CHECK (quantity > 0)
);
```

Các ví dụ sau giả định schema trên do migration có kiểm soát tạo ra.

**Lưu ý:** Cột `version` cần giá trị hợp lệ khi chèn fixture; JPA provider thường quản lý initial version cho entity có `@Version` nhưng cách cụ thể có thể khác theo provider và strategy. Nếu chèn fixture bằng SQL trực tiếp, phải điền `version` thích hợp.

### 3.1. Không để mỗi framework tự sinh một schema khác

Nếu JPA thuần dùng Hibernate auto-create còn Spring dùng Flyway, một test khác nhau có thể xuất phát từ **DDL**, không phải do hai API persistence.

### 3.2. UNIQUE giúp idempotency có hiệu lực giữa replicas

`request_id` là primary key để ngăn việc cùng một request tạo hai movement rows. Đây là database invariant, không phải đặc điểm riêng của Spring hoặc JPA thuần.

---

## 4. Entity `InventoryItem` dùng chung

```java
package com.example.inventory.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    @Column(length = 100)
    private String sku;

    @Column(nullable = false)
    private int available;

    @Version
    @Column(nullable = false)
    private long version;

    protected InventoryItem() {
    }

    public InventoryItem(String sku, int available) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                "SKU is required"
            );
        }
        if (available < 0) {
            throw new IllegalArgumentException(
                "Available amount cannot be negative"
            );
        }
        this.sku = sku;
        this.available = available;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
        if (available < quantity) {
            throw new IllegalStateException(
                "Insufficient stock"
            );
        }
        available -= quantity;
    }

    public String getSku() {
        return sku;
    }

    public int getAvailable() {
        return available;
    }

    public long getVersion() {
        return version;
    }
}
```

Không phụ thuộc Spring: entity chỉ dùng annotations `jakarta.persistence`.

### 4.1. `@Version` có nghĩa gì?

Khi hai transactions cùng đọc một version và cùng update entity, JPA provider hỗ trợ optimistic locking theo version. Một transaction có thể bị optimistic conflict thay vì ghi đè silently.

### 4.2. Dirty checking không phụ thuộc Spring Data repository

Khi entity được quản lý trong persistence context và có transaction thích hợp:

```java
InventoryItem item =
    em.find(InventoryItem.class, "SKU-RED");

item.reserve(3);
```

JPA provider có thể phát hiện thay đổi và UPDATE khi flush. Không cần gọi `em.merge(item)` hoặc repository `save(item)` chỉ để bật dirty checking cho **managed entity**.

### 4.3. Một Java object không nhất thiết là managed

Entity vừa tạo bằng `new`, hoặc đã bị detach/đóng EM, không được dirty-check tự động trong context mới. Đây là JPA entity state semantics ở cả hai cách triển khai.

---

## 5. Entity `StockMovement` dùng chung

```java
package com.example.inventory.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "stock_movements")
public class StockMovement {

    @Id
    @Column(name = "request_id", length = 100)
    private String requestId;

    @Column(nullable = false, length = 100)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected StockMovement() {
    }

    public StockMovement(
            String requestId,
            String sku,
            int quantity,
            Instant createdAt) {

        if (requestId == null || requestId.isBlank() ||
                sku == null || sku.isBlank() ||
                quantity <= 0 || createdAt == null) {
            throw new IllegalArgumentException(
                "Invalid movement"
            );
        }
        this.requestId = requestId;
        this.sku = sku;
        this.quantity = quantity;
        this.createdAt = createdAt;
    }

    public String getRequestId() {
        return requestId;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

`StockMovement` có **assigned ID** (`requestId`), không dùng generated ID. Điều này giúp so sánh rõ `persist` và Spring Data `save` vì cách framework xác định entity mới có thể ảnh hưởng đường gọi `persist`/`merge`.

### 5.1. Không dựa vào Java `equals/hashCode` để chống duplicate request

Hai JVM instances có thể nhận cùng request ID. Database primary key mới là hàng rào cuối cho uniqueness.

### 5.2. Foreign key chưa có multi-tenant policy

Trong hệ thống đa tenant, `sku`/`requestId` nên có scope và authorization thích hợp, có thể cần composite key/tenant-aware constraints. Example đơn giản không thay quy tắc phân quyền production.

---

## 6. Command và result không phụ thuộc framework

```java
package com.example.inventory.application;

public record ReserveCommand(
    String requestId,
    String sku,
    int quantity
) {
}
```

```java
package com.example.inventory.application;

public record ReservationResult(
    String requestId,
    String sku,
    int quantity,
    boolean previouslyProcessed
) {
}
```

Validation nghiệp vụ:

```java
public static void validate(ReserveCommand command) {
    if (command == null ||
            command.requestId() == null ||
            command.requestId().isBlank() ||
            command.sku() == null ||
            command.sku().isBlank() ||
            command.quantity() <= 0) {
        throw new IllegalArgumentException(
            "Invalid reservation request"
        );
    }
}
```

Hai cách triển khai sẽ cùng áp dụng hợp đồng này; nếu một cách bỏ validation thì đó là **khác biệt code ứng dụng**, không phải khác biệt giữa JPA và Spring.

---

# Phần II — JPA thuần RESOURCE_LOCAL

## 7. Bootstrapping `EntityManagerFactory`

Trong Java SE, ứng dụng có thể tạo factory:

```java
Map<String, Object> settings = new HashMap<>();

settings.put(
    "jakarta.persistence.jdbc.driver",
    "org.postgresql.Driver"
);
settings.put(
    "jakarta.persistence.jdbc.url",
    config.jdbcUrl()
);
settings.put(
    "jakarta.persistence.jdbc.user",
    config.username()
);
settings.put(
    "jakarta.persistence.jdbc.password",
    config.password()
);

EntityManagerFactory emf =
    Persistence.createEntityManagerFactory(
        "inventory-pu",
        settings
    );
```

Các imports:

```java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;
import java.util.HashMap;
import java.util.Map;
```

`config` là application configuration abstraction, không phải API JPA. Production secrets phải đến từ nguồn bảo mật, không commit password vào Java source.

### 7.1. `persistence.xml`

File `META-INF/persistence.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit
        name="inventory-pu"
        transaction-type="RESOURCE_LOCAL">

        <provider>
            org.hibernate.jpa.HibernatePersistenceProvider
        </provider>

        <class>
            com.example.inventory.domain.InventoryItem
        </class>
        <class>
            com.example.inventory.domain.StockMovement
        </class>

        <exclude-unlisted-classes>true</exclude-unlisted-classes>
    </persistence-unit>
</persistence>
```

Cần JPA provider, JDBC driver và Jakarta APIs tương thích trong runtime.

### 7.2. Factory và manager có vòng đời khác nhau

- `EntityManagerFactory` thường được tạo một lần cho một persistence unit và có thể share.
- `EntityManager` đại diện cho một persistence context; **không thread-safe**.
- `emf.close()` khi ứng dụng shutdown.
- Mỗi `EntityManager` do ứng dụng tự tạo phải được close đúng lúc.

### 7.3. RESOURCE_LOCAL transaction

Trong cấu hình này, ứng dụng dùng:

```java
EntityTransaction transaction =
    em.getTransaction();

transaction.begin();
// JPA operations
transaction.commit();
```

Không dùng `EntityTransaction` cho một JTA container-managed EntityManager chỉ vì thấy API tương tự. JTA và RESOURCE_LOCAL là hai transaction management models khác nhau.

---

## 8. JPA thuần: một unit of work đầy đủ

```java
package com.example.inventory.application;

import com.example.inventory.domain.InventoryItem;
import com.example.inventory.domain.StockMovement;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import java.time.Clock;

public final class PureJpaReservationService {

    private final EntityManagerFactory emf;
    private final Clock clock;

    public PureJpaReservationService(
            EntityManagerFactory emf,
            Clock clock) {
        this.emf = emf;
        this.clock = clock;
    }

    public ReservationResult reserve(
            ReserveCommand command) {

        validate(command);

        EntityManager em = emf.createEntityManager();

        try {
            em.getTransaction().begin();

            StockMovement previous = em.find(
                StockMovement.class,
                command.requestId()
            );

            if (previous != null) {
                ensureSamePayload(previous, command);

                em.getTransaction().commit();

                return new ReservationResult(
                    previous.getRequestId(),
                    previous.getSku(),
                    previous.getQuantity(),
                    true
                );
            }

            InventoryItem item = em.find(
                InventoryItem.class,
                command.sku()
            );

            if (item == null) {
                throw new IllegalArgumentException(
                    "Unknown SKU"
                );
            }

            item.reserve(command.quantity());

            em.persist(new StockMovement(
                command.requestId(),
                command.sku(),
                command.quantity(),
                clock.instant()
            ));

            em.flush();
            em.getTransaction().commit();

            return new ReservationResult(
                command.requestId(),
                command.sku(),
                command.quantity(),
                false
            );

        } catch (RuntimeException failure) {
            try {
                if (em.getTransaction().isActive()) {
                    em.getTransaction().rollback();
                }
            } catch (RuntimeException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }

            throw failure;

        } finally {
            em.close();
        }
    }

    private static void validate(ReserveCommand c) {
        if (c == null || c.requestId() == null ||
                c.requestId().isBlank() ||
                c.sku() == null || c.sku().isBlank() ||
                c.quantity() <= 0) {
            throw new IllegalArgumentException(
                "Invalid request"
            );
        }
    }

    private static void ensureSamePayload(
            StockMovement m, ReserveCommand c) {

        if (!m.getSku().equals(c.sku()) ||
                m.getQuantity() != c.quantity()) {
            throw new IllegalStateException(
                "Request ID used for different command"
            );
        }
    }
}
```

### 8.1. Điều gì do JPA đảm bảo?

- `find` tìm entity theo primary key.
- Managed entity được theo dõi thay đổi.
- `persist` đưa new entity vào persistence lifecycle.
- `flush` đồng bộ pending changes theo transaction.
- `commit` hoàn tất transaction nếu thành công.
- Optimistic locking thông qua `@Version` theo JPA semantics.
- Exceptions có thể phát sinh ở `persist`, `flush` hoặc `commit`.

### 8.2. Điều gì do code ứng dụng đảm nhiệm?

- Tạo `EntityManager`.
- Mở transaction.
- Xác định scope một unit of work.
- Rollback/cleanup sau lỗi.
- Đóng EM.
- Điều phối retry bên ngoài transaction.
- Chọn response và phân loại business errors.

### 8.3. Vì sao flush không thay commit?

```java
em.flush();
```

giúp phát hiện một số lỗi trước khi ra khỏi service, nhưng dữ liệu vẫn chưa committed cho đến khi transaction thành công.

### 8.4. Lưu ý concurrent requests cùng request ID

Code đã đọc `StockMovement` trước khi insert; hai threads có thể đều thấy “not found”. **Primary key constraint** là hàng rào cuối. Khi một transaction gặp unique violation, cần rollback/close EM rồi đọc lại bằng transaction mới và đối chiếu payload, không tiếp tục dùng cùng context lỗi.

### 8.5. Commit outcome unknown

Nếu mất kết nối tại commit, response có thể lỗi dù DB đã commit. Cả phương án thuần và Spring đều cần idempotency/reconciliation; framework không tự biết ý định nghiệp vụ.

---

## 9. JPA thuần: thao tác đọc

```java
public int currentStock(String sku) {
    EntityManager em = emf.createEntityManager();

    try {
        InventoryItem item =
            em.find(InventoryItem.class, sku);

        if (item == null) {
            throw new IllegalArgumentException(
                "Unknown SKU"
            );
        }

        return item.getAvailable();

    } finally {
        em.close();
    }
}
```

Đối với một số read operations thuần RESOURCE_LOCAL, provider có thể cho phép đọc ngoài transaction theo JPA/environment rules; **không dùng ví dụ này để suy rằng mọi loại lazy loading, query lock hoặc consistency requirement đều hoạt động giống nhau ngoài transaction**.

### 9.1. Khi cần snapshot/locking rõ

Dùng transaction phù hợp. Đặc biệt `LockModeType.PESSIMISTIC_WRITE` có transaction requirements và database-specific lock semantics.

### 9.2. Trả DTO trước khi đóng context

Nếu return entity rồi controller truy cập lazy association sau khi EM đã close, có thể gặp lazy-load exception. Mapping thành DTO ngay trong scope EM là cách rõ ràng.

---

# Phần III — Spring ORM dùng trực tiếp EntityManager

## 10. Spring Boot configuration

Với Spring Boot và `spring-boot-starter-data-jpa`, thường có auto-configuration cho:

- `DataSource`/connection pool.
- Hibernate/JPA provider.
- `EntityManagerFactory`.
- `JpaTransactionManager` hoặc transaction management phù hợp.
- Repository infrastructure.

Ví dụ:

```yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
```

Cấu hình trên chỉ minh họa: secrets phải được cấp bảo mật ở runtime, DB migration phải được chạy riêng, pool size cần đo workload.

### 10.1. Không coi autoconfiguration là một JPA API chuẩn

Các thuộc tính `spring.datasource.*` và `spring.jpa.*` thuộc Spring Boot. Thuần Jakarta Persistence không bắt buộc hiểu các properties này.

### 10.2. Provider vẫn là Hibernate

Nếu cả hai hướng dùng Hibernate giống phiên bản/dialect và mapping như nhau, JPA entity state và SQL generation về cơ bản dựa trên cùng provider. Sự khác nhau lớn thường đến từ boundary/configuration, không phải cách SQL “được viết bởi Spring”.

---

## 11. Spring-managed EntityManager

Ví dụ:

```java
@Repository
public class StockMovementDao {

    @PersistenceContext
    private EntityManager em;

    public StockMovement find(String requestId) {
        return em.find(
            StockMovement.class,
            requestId
        );
    }

    public void insert(StockMovement movement) {
        em.persist(movement);
    }
}
```

`@PersistenceContext` đến từ Jakarta Persistence. Trong Spring, đối tượng inject thường là **shared EntityManager proxy** điều phối sang actual EM gắn với transaction đang hoạt động.

### 11.1. Không tự close injected EntityManager

Sai:

```java
em.close();
```

trong một DAO được Spring quản lý.

Spring chịu trách nhiệm lifecycle của transaction-bound EM. Tự close proxy hoặc giữ actual EM vượt scope có thể gây lỗi và phá transaction management.

### 11.2. Một proxy không đồng nghĩa một persistence context toàn ứng dụng

Bean DAO có thể là singleton chứa một proxy EM, nhưng mỗi transaction dùng underlying context phù hợp. Không coi mọi request trên singleton DAO cùng chia sẻ một L1 cache.

### 11.3. Không gọi getTransaction trong Spring JPA managed context

Sai về mô hình thông thường:

```java
em.getTransaction().begin();
```

trong service đã có `@Transactional`.

Spring transaction manager chịu trách nhiệm begin/commit/rollback, thường không cho phép application tùy tiện điều khiển `EntityTransaction` trên shared EM proxy.

---

## 12. Spring service cùng nghiệp vụ với JPA thuần

```java
package com.example.inventory.application;

import com.example.inventory.domain.InventoryItem;
import com.example.inventory.domain.StockMovement;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Clock;

@Service
public class SpringJpaReservationService {

    @PersistenceContext
    private EntityManager em;

    private final Clock clock;

    public SpringJpaReservationService(Clock clock) {
        this.clock = clock;
    }

    @Transactional
    public ReservationResult reserve(
            ReserveCommand command) {

        validate(command);

        StockMovement previous = em.find(
            StockMovement.class,
            command.requestId()
        );

        if (previous != null) {
            ensureSamePayload(previous, command);

            return new ReservationResult(
                previous.getRequestId(),
                previous.getSku(),
                previous.getQuantity(),
                true
            );
        }

        InventoryItem item = em.find(
            InventoryItem.class,
            command.sku()
        );

        if (item == null) {
            throw new IllegalArgumentException(
                "Unknown SKU"
            );
        }

        item.reserve(command.quantity());

        em.persist(new StockMovement(
            command.requestId(),
            command.sku(),
            command.quantity(),
            clock.instant()
        ));

        return new ReservationResult(
            command.requestId(),
            command.sku(),
            command.quantity(),
            false
        );
    }

    private static void validate(ReserveCommand c) {
        if (c == null || c.requestId() == null ||
                c.requestId().isBlank() ||
                c.sku() == null || c.sku().isBlank() ||
                c.quantity() <= 0) {
            throw new IllegalArgumentException(
                "Invalid request"
            );
        }
    }

    private static void ensureSamePayload(
            StockMovement m, ReserveCommand c) {

        if (!m.getSku().equals(c.sku()) ||
                m.getQuantity() != c.quantity()) {
            throw new IllegalStateException(
                "Request ID used for different command"
            );
        }
    }
}
```

### 12.1. Khác biệt chính với phương án thuần

Không có:

```java
emf.createEntityManager();
em.getTransaction().begin();
em.getTransaction().commit();
em.close();
```

Spring interceptor/transaction manager sẽ quản lý những bước tương ứng tại boundary `@Transactional`.

### 12.2. Không cần `em.flush()` để “lưu dữ liệu”

Với managed item, Hibernate dirty checking và pending INSERT sẽ được đồng bộ trong transaction khi thích hợp, thường trước commit. Có thể gọi `flush()` nếu cần phát hiện constraint error trước một bước phụ thuộc, nhưng **flush không commit**.

### 12.3. Service return không nhất thiết là commit hoàn tất

Trong proxy-based `@Transactional`, transaction interceptor thường **commit sau khi method body trả về nhưng trước khi caller nhận kết quả bình thường**. Vì vậy exception ở commit có thể được ném ở ngoài body method.

Không catch toàn bộ commit failures bằng `try/catch` **bên trong** `reserve` rồi mong xử lý xong, vì commit có thể xảy ra sau khi method body kết thúc.

### 12.4. Thiếu transaction là khác biệt quan trọng

Nếu bỏ `@Transactional`, một số read methods vẫn chạy, nhưng write dirty checking hoặc `persist` có thể ném `TransactionRequiredException`/không được commit theo cách mong muốn. Cần đặt transaction ở **service unit-of-work boundary**, không dựa vào các transaction nhỏ tình cờ của repository.

---

## 13. Spring Data JPA với JpaRepository

Repository:

```java
package com.example.inventory.repository;

import com.example.inventory.domain.InventoryItem;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryItemRepository
        extends JpaRepository<InventoryItem, String> {
}
```

```java
package com.example.inventory.repository;

import com.example.inventory.domain.StockMovement;
import org.springframework.data.jpa.repository.JpaRepository;

public interface StockMovementRepository
        extends JpaRepository<StockMovement, String> {
}
```

Một service:

```java
@Service
public class SpringDataReservationService {

    private final InventoryItemRepository items;
    private final StockMovementRepository movements;
    private final Clock clock;

    public SpringDataReservationService(
            InventoryItemRepository items,
            StockMovementRepository movements,
            Clock clock) {
        this.items = items;
        this.movements = movements;
        this.clock = clock;
    }

    @Transactional
    public ReservationResult reserve(ReserveCommand command) {
        validate(command);

        var previous =
            movements.findById(command.requestId());

        if (previous.isPresent()) {
            StockMovement m = previous.get();
            ensureSamePayload(m, command);

            return new ReservationResult(
                m.getRequestId(), m.getSku(),
                m.getQuantity(), true
            );
        }

        InventoryItem item = items.findById(command.sku())
            .orElseThrow(() ->
                new IllegalArgumentException(
                    "Unknown SKU"
                )
            );

        item.reserve(command.quantity());

        movements.save(new StockMovement(
            command.requestId(),
            command.sku(),
            command.quantity(),
            clock.instant()
        ));

        return new ReservationResult(
            command.requestId(),
            command.sku(),
            command.quantity(),
            false
        );
    }
}
```

`validate`/`ensureSamePayload` là cùng các helpers ở service trước; trong project thật có thể đưa vào domain/application utility chung.

### 13.1. `save` không phải tên chuẩn của EntityManager

Jakarta Persistence có `persist`, `merge`, `remove`, không có `EntityManager.save`.

`JpaRepository.save` do Spring Data JPA định nghĩa, và implementation có thể chọn `persist` hoặc `merge` dựa trên cách xác định entity mới.

### 13.2. Assigned ID là tình huống cần chú ý

`StockMovement` có `requestId` được gán trước khi lưu. Một implementation Spring Data có thể xem entity có non-null ID là **không mới** và gọi `merge`, thay vì `persist` như code Spring ORM thuần. Điều này có thể tạo thêm SELECT hoặc hành vi khác về returned managed instance.

Muốn kiểm soát chính xác newness, có thể dùng `Persistable<ID>` hoặc một custom repository/DAO gọi `em.persist` rõ ràng, nhưng phải triển khai lifecycle flag đúng — không tự trả `isNew=true` mãi mãi.

### 13.3. Business outcome nên giống nhau

Ngay cả khi implementation dùng `merge` thay `persist`, nếu thiết kế đúng, database phải giữ cùng business invariant: một movement mỗi request ID và stock không âm. Những khác biệt về SQL count/performance thuộc provider/implementation cần đo riêng.

---

# Phần IV — `persist`, `merge`, `save` và dirty checking

## 14. Đối chiếu lời gọi

| Nhu cầu | JPA thuần | Spring ORM + JPA | Spring Data JPA |
| --- | --- | --- | --- |
| Tìm theo khóa | `em.find(Entity.class,id)` | `em.find(...)` | `repository.findById(id)` |
| New entity | `em.persist(entity)` | `em.persist(entity)` | `repository.save(entity)` |
| Detached entity | `em.merge(entity)` | `em.merge(entity)` | `repository.save(entity)` |
| Xóa managed entity | `em.remove(entity)` | `em.remove(entity)` | `repository.delete(entity)` |
| Query JPQL | `em.createQuery(...)` | `em.createQuery(...)` | `@Query` hoặc custom repository |
| Flush | `em.flush()` | `em.flush()` | `repository.flush()` |
| Save + flush | `persist/merge` rồi `flush` | tương tự | `saveAndFlush(entity)` |
| Commit | `EntityTransaction.commit()` | transaction interceptor | transaction interceptor |
| Read-only query | JPA query/DTO | `@Transactional(readOnly=true)` + JPA | repository/service read methods |

**Bảng này so sánh mục đích sử dụng, không khẳng định `save` luôn đồng nghĩa `persist` hoặc `merge` trong mọi tình huống.**

---

## 15. `persist` và `merge` khác nhau bản chất

### 15.1. `persist`

```java
em.persist(newEntity);
```

Là lời gọi lifecycle cho new entity. Entity trở thành managed theo JPA semantics.

### 15.2. `merge`

```java
InventoryItem managed =
    em.merge(detached);
```

Tạo/trả về managed representation của state từ object truyền vào, theo JPA merge semantics. **Object detached ban đầu không tự trở thành managed.**

```java
InventoryItem managed = em.merge(detached);

assertNotSame(detached, managed);
```

Đây là hình dung thường gặp với detached instance; không nên assert object identity khác nhau cho **mọi** input (ví dụ input đã managed có thể được trả chính nó).

### 15.3. Không gọi merge vô điều kiện với managed entity

```java
InventoryItem item = em.find(InventoryItem.class, sku);
item.reserve(2);
```

Với active transaction/context, dirty checking đủ để đồng bộ. `em.merge(item)` không phải thao tác bắt buộc.

### 15.4. `JpaRepository.save` trả kết quả cần chú ý

```java
InventoryItem saved =
    repository.save(detached);
```

Nếu Spring Data chọn merge, `saved` có thể là managed copy trong transaction, không phải `detached` input. Không tiếp tục sửa input detached rồi mặc định thay đổi sẽ được lưu.

### 15.5. `saveAll` không bảo đảm JDBC batching

`saveAll` xử lý nhiều entities qua repository API; batching phụ thuộc Hibernate settings, SQL shapes, identifier strategy, driver và transaction. Cũng như JPA thuần, `saveAll` không tự tạo một transaction nghiệp vụ cho toàn use case nếu service boundaries bị chia sai.

---

## 16. Spring Data xác định entity “mới” như thế nào?

Một cách thường gặp của Spring Data JPA là kiểm tra:

1. Version field non-primitive/nullability thích hợp, nếu có.
2. Identifier null/non-null theo strategy.
3. `Persistable.isNew()` hoặc custom EntityInformation nếu được cấu hình.

Các quy tắc cụ thể có thể thay theo Spring Data version và mapping.

### 16.1. Trường hợp manually assigned ID

```java
@Id
private String requestId;
```

`requestId` không null ngay từ constructor. Spring Data có thể **không** nhận diện entity là new theo default ID-null check.

### 16.2. Dùng `Persistable<String>` khi cần

Một chiến lược minh họa:

```java
@Entity
class StockMovement implements Persistable<String> {

    @Id
    private String requestId;

    @Transient
    private boolean isNew = true;

    @Override
    public String getId() {
        return requestId;
    }

    @Override
    public boolean isNew() {
        return isNew;
    }

    @PostLoad
    @PostPersist
    private void markNotNew() {
        isNew = false;
    }
}
```

Đây là sketch phải tích hợp đầy đủ với entity/mapping/constructors; annotations `@Transient`, `@PostLoad`, `@PostPersist` là Jakarta Persistence, `Persistable` là Spring Data. Không copy nửa sketch vào production mà không xử lý serialization/detachment, constructors và lifecycle tests.

### 16.3. Nếu cần portable JPA API

Custom repository gọi `em.persist(newMovement)` trực tiếp là phương án rõ nếu operation luôn là create và business đã kiểm tra idempotency key.

### 16.4. Không dùng `save` như UPSERT portable

`JpaRepository.save` không phải một database `INSERT ... ON CONFLICT DO UPDATE` chuẩn; nó có thể chọn merge, thực hiện SELECT và vẫn gặp unique violation khi concurrent transactions. UPSERT là một cơ chế SQL/database-specific khác.

---

## 17. Dirty checking: không cần gọi save trên managed entity

Trong Spring:

```java
@Transactional
public void reserveOne(String sku) {
    InventoryItem item = items.findById(sku)
        .orElseThrow();

    item.reserve(1);

    // Trong transaction, entity managed.
    // Không bắt buộc items.save(item).
}
```

Điều này dựa trên dirty checking của JPA provider, không phải phép màu riêng của Spring Data.

### 17.1. Bị tách khỏi transaction thì khác

```java
InventoryItem detached =
    items.findById(sku).orElseThrow();

detached.reserve(1);
```

Nếu repository method đã trả và không có outer transaction, EntityManager sử dụng cho method có thể đã kết thúc. Object `detached` không còn được dirty check tự động.

Đừng suy rằng `JpaRepository.findById` làm object managed vĩnh viễn.

### 17.2. OSIV có thể khiến tình huống khó nhìn hơn

Khi Open Session in View bật, persistence context có thể còn trong web request dù service transaction đã kết thúc. Đọc lazy associations có thể thành công nhưng không chứng minh field mutation ngoài transaction sẽ được tự động commit đúng business semantics.

---

# Phần V — Transaction boundaries và propagation

## 18. Ai begin, commit, rollback?

### 18.1. RESOURCE_LOCAL

```java
em.getTransaction().begin();

try {
    doWork(em);
    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
}
```

### 18.2. Spring

```java
@Transactional
public void doWork() {
    // JPA operations.
}
```

Spring transaction interceptor quản lý boundary khi method được gọi qua proxy/transaction infrastructure đúng cách.

### 18.3. Bảng đối chiếu

| Sự kiện | RESOURCE_LOCAL JPA | Spring @Transactional |
| --- | --- | --- |
| Trước unit of work | `createEntityManager()` | Tiêm EM proxy/repository |
| Mở transaction | `.begin()` | Interceptor bắt đầu/join |
| Thao tác | `em.find/persist...` | `em.*` hoặc repository |
| Flush | Manual/automatic theo JPA | JPA flush theo transaction/provider |
| Commit | `.commit()` rõ | Interceptor commit khi thoát thành công |
| Runtime exception | Application rollback | Mặc định rollback nếu exception thoát |
| Checked exception | Application quyết định | Default không rollback, tùy policy |
| Close EM | Application close | Framework xử lý |
| Retry | Transaction/context mới thủ công | Outer coordinator/new transaction |

**Không có nghĩa Spring có giao dịch mạnh hơn**. Nếu cả hai dùng cùng database và transaction design, ACID guarantees thuộc database/transaction infrastructure tương ứng.

---

## 19. Spring rollback rules

Spring `@Transactional` mặc định thường rollback khi unchecked `RuntimeException`/`Error` thoát khỏi transactional invocation, nhưng **không tự rollback cho mọi checked exception**.

Ví dụ:

```java
@Transactional
public void process() throws IOException {
    updateDatabase();
    throw new IOException("Downstream unavailable");
}
```

Nếu dùng default rollback rules, checked exception này có thể khiến DB transaction **commit** dù method ném lỗi. Cần quyết định theo nghiệp vụ:

```java
@Transactional(rollbackFor = IOException.class)
public void process() throws IOException {
    updateDatabase();
    throw new IOException("Downstream unavailable");
}
```

### 19.1. JPA thuần do application quyết định

Ở RESOURCE_LOCAL, catch/rollback/commit code quyết định; không có Spring default rollback rule.

### 19.2. Exception bị catch và không propagate

```java
@Transactional
public void process() {
    try {
        doWrite();
    } catch (RuntimeException ex) {
        log.warn("ignored", ex);
    }
}
```

Nếu transaction đã bị marked rollback-only bởi provider/transaction manager, method return bình thường vẫn có thể dẫn đến rollback và `UnexpectedRollbackException`.

Đừng coi việc catch exception là “hủy bỏ” trạng thái lỗi của JPA transaction.

### 19.3. Business validation exception

Nếu `InsufficientStockException` kế thừa `RuntimeException`, default Spring có thể rollback. Nếu bạn muốn một loại checked business exception vẫn rollback, khai báo policy cụ thể. Với JPA thuần, catch/rollback logic phải tương ứng.

---

## 20. `Propagation.REQUIRED` và `REQUIRES_NEW`

Một service:

```java
@Transactional
public void outer() {
    serviceB.updateItem();
}
```

`serviceB.updateItem()` nếu `@Transactional` với propagation `REQUIRED` thường join outer transaction khi được gọi qua proxy.

### 20.1. REQUIRED

```text
Outer TX begins
    |
    +--> Inner method joins same TX
    |
Outer commits or rolls back entire unit
```

### 20.2. REQUIRES_NEW

```text
Outer TX begins
    |
    +--> Suspend outer TX
          Begin new TX
          Commit/Rollback inner
    |
    +--> Resume outer TX
Outer finishes
```

Một inner `REQUIRES_NEW` có thể commit độc lập dù outer rollback sau đó. Điều này thay đổi **atomicity** của business workflow.

### 20.3. Không có `REQUIRES_NEW` trong EntityTransaction API

JPA thuần RESOURCE_LOCAL không cung cấp một phương thức `Propagation.REQUIRES_NEW`. Có thể tạo **một EntityManager/connection và transaction khác** theo thiết kế, nhưng không phải tự động tương đương với các propagation rules của Spring, đặc biệt khi có outer transactions/locks/resource constraints.

### 20.4. Cẩn thận connection pool

`REQUIRES_NEW` có thể cần connection khác khi outer transaction đang giữ resources. Pool quá nhỏ dễ deadlock/resource starvation nếu dùng lồng nhiều mức.

---

## 21. Spring self-invocation và proxy boundary

Một ví dụ sai:

```java
@Service
class ExampleService {

    public void launch() {
        this.writeInNewTransaction();
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW
    )
    public void writeInNewTransaction() {
        // ...
    }
}
```

Trong Spring proxy-based transaction management, lời gọi `this.writeInNewTransaction()` thường **không đi qua proxy**, nên transaction advice trên method đích có thể không được áp.

### 21.1. Giải pháp

- Tách transactional method sang Spring bean khác.
- Gọi qua proxy hợp lệ nếu thiết kế cho phép.
- Dùng `TransactionTemplate`.
- Dùng transaction management mode khác có chủ ý (ví dụ AspectJ mode nếu cấu hình đúng).

### 21.2. Không chỉ đặt annotation rồi giả định có transaction

Test transaction thực bằng DB state sau commit/rollback, không chỉ kiểm tra method có `@Transactional`.

### 21.3. Private methods cũng không nên là transaction boundary proxy

Ở proxy-based approach, annotations trên private helper thường không tạo independent transaction advice như người mới mong đợi. Public service boundary dễ reasoning hơn.

---

## 22. `@Transactional(readOnly = true)` là gợi ý/điều phối

```java
@Transactional(readOnly = true)
public StockDto getStock(String sku) {
    InventoryItem item = em.find(
        InventoryItem.class, sku
    );
    return new StockDto(
        item.getSku(), item.getAvailable()
    );
}
```

### 22.1. Không phải bảo đảm DB sẽ chặn mọi UPDATE

`readOnly=true` của Spring có thể ảnh hưởng transaction definition/provider flush behavior và connection flags tùy manager/driver/database. **Không dùng như một cơ chế authorization hoặc ràng buộc portable cấm writes**.

Nếu cần chặn writes tuyệt đối, cấp read-only DB role và quyền tối thiểu.

### 22.2. Dirty checking optimization là provider-specific

Hibernate có thể tối ưu flush/dirty checking cho read-only transactional context theo phiên bản/config. Không lấy đây làm chuẩn JPA.

### 22.3. Dù readOnly, vẫn cần transaction khi nhất quán dữ liệu quan trọng

Một DTO read có thể chạy trong transaction để kiểm soát consistency/fetching; `readOnly` không phải cam kết snapshot isolation.

---

# Phần VI — Persistence context và lazy loading

## 23. Identity map giống nhau ở hai hướng

Trong một `EntityManager`:

```java
InventoryItem a =
    em.find(InventoryItem.class, "SKU-RED");

InventoryItem b =
    em.find(InventoryItem.class, "SKU-RED");

assertSame(a, b);
```

JPA định nghĩa identity của managed entity trong persistence context. Cùng entity identity trong một context thường tương ứng cùng managed Java instance.

### 23.1. Thuần JPA

Application quyết định EM scope.

### 23.2. Spring

Transaction manager và Spring proxy quyết định underlying EM scope theo transaction/request configuration.

### 23.3. Transaction khác, Java object khác

Không assert cùng Java reference sau hai transactions độc lập. Cùng DB row có thể được load thành hai instances khác nhau.

---

## 24. `flush`, `clear`, `detach`, `refresh`

| API JPA | Ý nghĩa | Spring thay đổi semantics? |
| --- | --- | --- |
| `em.flush()` | Đồng bộ pending changes | Không |
| `em.clear()` | Detach toàn bộ managed entities | Không |
| `em.detach(entity)` | Detach một entity | Không |
| `em.refresh(entity)` | Reload state từ DB trong context | Không |
| `em.contains(entity)` | Kiểm tra managed membership | Không |
| `em.close()` | Đóng application-managed EM | Spring quản lý injected EM lifecycle |
| `em.merge(detached)` | Copy state sang managed instance | Không |

Điểm khác biệt thực tế là **ai được phép/được yêu cầu gọi** `close()` và transaction boundaries của những API này.

### 24.1. Lỗi khi dùng `clear()` trong service

`clear()` detach mọi managed entities của transaction hiện tại. Với Spring, một repository khác cùng transaction có thể bất ngờ mất managed state nếu bạn clear context giữa chừng.

### 24.2. Flush không tự giải phóng L1

Nếu nhập hàng loạt, có thể cần `flush/clear` theo chunk để giới hạn memory. Cả JPA thuần và Spring đều phải hiểu vấn đề này, không tự biến `saveAll` thành memory-safe stream.

---

## 25. Lazy loading sau khi transaction kết thúc

Giả sử thêm association:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Warehouse warehouse;
```

Nếu controller trả entity rồi JSON serializer truy cập:

```java
item.getWarehouse().getName()
```

ngoài usable persistence context, Hibernate có thể ném `LazyInitializationException`.

### 25.1. JPA thuần

Một EM đã close không thể lazy-load ngoài context; cần load các dữ liệu cần thiết trước close, dùng join fetch, entity graph hoặc DTO projection.

### 25.2. Spring với OSIV

Open Session in View có thể giữ persistence context đến hết web request và khiến lazy loading tại controller/serializer **tình cờ chạy được**.

Nhưng điều đó có tradeoffs:

- Query phát sinh ngoài service transaction.
- N+1 queries từ serializer.
- Kéo dài resource lifetime.
- Hidden data access trong presentation layer.
- Khó quản lý database consistency.

### 25.3. Cách rõ ràng: DTO bên trong service transaction

```java
@Transactional(readOnly = true)
public StockDto getStock(String sku) {
    InventoryItem item = em.find(
        InventoryItem.class, sku
    );

    if (item == null) {
        throw new IllegalArgumentException(
            "Unknown SKU"
        );
    }

    return new StockDto(
        item.getSku(),
        item.getAvailable()
    );
}
```

```java
public record StockDto(
    String sku,
    int available
) {
}
```

Không nên trả entity cho API rồi phụ thuộc OSIV để load associations ngoài service.

---

# Phần VII — Query API, repository và exception translation

## 26. JPQL và Criteria vẫn là JPA

### 26.1. JPA thuần

```java
Long lowStockCount = em.createQuery(
    """
    SELECT COUNT(i)
    FROM InventoryItem i
    WHERE i.available < :threshold
    """,
    Long.class
)
.setParameter("threshold", 10)
.getSingleResult();
```

### 26.2. Spring ORM

```java
@PersistenceContext
private EntityManager em;
```

Gọi chính JPQL ở trên. Cú pháp query không đổi vì Spring không tạo một ngôn ngữ JPQL khác.

### 26.3. Spring Data repository method

```java
public interface InventoryItemRepository
        extends JpaRepository<InventoryItem, String> {

    List<InventoryItem> findByAvailableLessThan(
        int threshold
    );
}
```

Spring Data sinh query từ method name theo convention.

### 26.4. `@Query`

```java
@Query(
    """
    SELECT i
    FROM InventoryItem i
    WHERE i.available < :threshold
    ORDER BY i.sku
    """
)
List<InventoryItem> lowStock(
    @Param("threshold") int threshold
);
```

Cần import `org.springframework.data.jpa.repository.Query` và `org.springframework.data.repository.query.Param`.

**Các giá trị không tin cậy vẫn phải được bind**, dù dùng JPA thuần, Spring ORM hay Spring Data. Không ghép raw input vào JPQL/native SQL.

---

## 27. So sánh `find` và `findById`

JPA:

```java
InventoryItem item =
    em.find(InventoryItem.class, sku);
```

Có thể trả `null` nếu không tìm thấy.

Spring Data:

```java
Optional<InventoryItem> item =
    inventoryRepository.findById(sku);
```

Trả `Optional`.

### 27.1. Optional là API-level convenience

Điều này không đổi entity identity, managed state hoặc transaction semantics của JPA.

### 27.2. `getReference` / `getReferenceById`

Cả hai có thể lấy một reference/proxy chưa fully initialized, tùy provider. Không dùng chúng như một check “row chắc chắn tồn tại” khi chưa truy cập/verify dữ liệu.

### 27.3. `findAll` có thể không phù hợp bảng lớn

Spring Data `findAll()` không tự biến full-table load thành streaming paginated query. Với datasets lớn, dùng `Pageable`, projections, keyset pagination hoặc batch processing có giới hạn.

---

## 28. Exception JPA so với Spring translation

JPA và provider có thể phát:

```java
jakarta.persistence.PersistenceException
jakarta.persistence.EntityNotFoundException
jakarta.persistence.OptimisticLockException
jakarta.persistence.TransactionRequiredException
```

Hibernate có các exceptions riêng như SQL grammar/constraint errors. JDBC có `SQLException`.

Spring có hệ phân loại:

```java
org.springframework.dao.DataAccessException
org.springframework.dao.DataIntegrityViolationException
org.springframework.dao.OptimisticLockingFailureException
org.springframework.dao.DataAccessResourceFailureException
```

### 28.1. Spring `@Repository` và translation

Spring có persistence exception translation cho beans đúng loại/cấu hình, và Spring Data repositories thường được translation theo infrastructure của Spring.

**Không khẳng định mọi exception trong bất kỳ method @Service nào tự động biến thành `DataAccessException`**. Translation phụ thuộc interception/path/provider.

### 28.2. Phân biệt lỗi theo cause và transaction phase

Một `DataIntegrityViolationException` có thể là UNIQUE, FK, CHECK hoặc NOT NULL. Một `PersistenceException` có thể bọc JDBC connection failure. Cần xác định root cause/SQLSTATE khi cần policy retry hoặc trả API error cụ thể.

### 28.3. Vị trí lỗi commit

JPA thuần:

```java
em.getTransaction().commit();
```

là dòng code của application nên có thể bao trong `try/catch`.

Spring:

```java
@Transactional
public void method() {
    // Method body kết thúc
}
```

Commit có thể xảy ra trong interceptor sau method body; caller nhận exception ngoài service method. Đặt exception translation/error handling ở boundary phù hợp.

---

# Phần VIII — Cùng một transaction hay nhiều transactions?

## 29. Repository transaction nhỏ không thay service transaction lớn

Giả sử:

```java
items.save(item);
movements.save(movement);
```

Nếu không có outer service transaction và mỗi operation tham gia transaction riêng, có thể xảy ra:

1. `items.save(item)` commit.
2. `movements.save(movement)` thất bại.
3. Stock thay đổi nhưng movement không tồn tại.

Điều này phá atomicity.

### 29.1. Bao toàn bộ business operation

```java
@Transactional
public void reserve(...) {
    items.save(item);
    movements.save(movement);
}
```

Trong setup đúng, cả hai tham gia cùng service transaction.

### 29.2. Không mặc định mọi repository method được transaction giống nhau

Spring Data `SimpleJpaRepository` có defaults cho các CRUD methods, nhưng declared query methods có thể cần explicit transaction configuration. Đừng thay service transaction boundary bằng suy luận mơ hồ về annotation mặc định của repository.

### 29.3. `saveAndFlush` không commit outer transaction

```java
movements.saveAndFlush(movement);
```

có thể giúp phát hiện UNIQUE conflict trước khi service method trả, nhưng nếu outer transaction rollback thì dữ liệu vẫn không committed.

---

## 30. Isolation, optimistic locking và concurrency giống nhau về cốt lõi

Với `@Version`, cả hai cách triển khai cần phát hiện lost update.

Kịch bản:

```text
TX A đọc SKU-RED version=3, available=100
TX B đọc SKU-RED version=3, available=100

TX A giảm 2 -> commit version=4
TX B giảm 5 -> cố commit, version không còn là 3
```

Một transaction có thể bị optimistic locking conflict.

### 30.1. JPA thuần

Exception có thể đến tại flush hoặc commit; application rollback/close và quyết định retry.

### 30.2. Spring

Exception có thể được translation thành `OptimisticLockingFailureException` hoặc subtype/cause chain phù hợp; transaction manager rollback theo policy.

### 30.3. Retry phải làm lại toàn unit of work

Không retry cùng `EntityManager`/managed object đã lỗi. Mở transaction/context mới, load version mới và kiểm tra business invariant trước khi ghi.

### 30.4. `@Transactional(isolation=...)` là Spring abstraction

Spring có thuộc tính isolation khi transaction được **tạo mới** theo transaction manager/DB capabilities. JPA `EntityTransaction` không định nghĩa cùng annotation/API isolation levels. Với JPA thuần, isolation thường được điều khiển bằng DataSource/JDBC/database configuration.

### 30.5. DB quyết định nhiều behavior

Dirty reads, nonrepeatable reads, phantoms, deadlocks và serializable failures phụ thuộc database/transaction configuration, không phải bản chất “có Spring thì isolation tốt hơn”.

---

# Phần IX — Kiểm thử so sánh công bằng

## 31. Nguyên tắc thử nghiệm

Muốn đối chiếu hai cách triển khai, giữ cố định:

- **Cùng entity classes**.
- **Cùng JPA provider và phiên bản**.
- **Cùng PostgreSQL version/driver**.
- **Cùng schema/migrations**.
- **Cùng dữ liệu fixture**.
- **Cùng transaction isolation/propagation mục tiêu**.
- **Cùng use case/invariants**.
- **Cùng clock/UUID generation policy**.
- **Cùng cấu hình JDBC batching/fetch/caches** khi so sánh hiệu năng.
- **Cùng cách đọc lại committed state**.
- **Cùng logic retry/idempotency** nếu kiểm thử lỗi.

Nếu một bên có OSIV, một bên không; một bên auto-generates schema, một bên dùng Flyway; hoặc một bên commit từng method, bên kia có transaction lớn, kết quả khác không chứng minh bản chất JPA khác Spring.

---

## 32. JPA thuần: test `RESOURCE_LOCAL` có commit thật

Một test với JUnit 5:

```java
@Test
void pureJpaReservationCommitsAtomically() {
    String sku = "SKU-" + UUID.randomUUID();

    inTransaction(em -> {
        em.persist(new InventoryItem(sku, 10));
        return null;
    });

    ReserveCommand command =
        new ReserveCommand(
            "REQ-" + UUID.randomUUID(),
            sku,
            3
        );

    PureJpaReservationService service =
        new PureJpaReservationService(
            emf,
            Clock.systemUTC()
        );

    ReservationResult result =
        service.reserve(command);

    assertFalse(result.previouslyProcessed());

    try (EntityManagerScope verify =
            new EntityManagerScope(emf)) {

        InventoryItem stock = verify.em().find(
            InventoryItem.class, sku
        );

        StockMovement movement = verify.em().find(
            StockMovement.class,
            command.requestId()
        );

        assertEquals(7, stock.getAvailable());
        assertNotNull(movement);
        assertEquals(3, movement.getQuantity());
    }
}
```

`EntityManagerScope` trong ví dụ là test utility cần định nghĩa, ví dụ:

```java
public final class EntityManagerScope
        implements AutoCloseable {

    private final EntityManager em;

    public EntityManagerScope(
            EntityManagerFactory emf) {
        this.em = emf.createEntityManager();
    }

    public EntityManager em() {
        return em;
    }

    @Override
    public void close() {
        em.close();
    }
}
```

`inTransaction` là helper RESOURCE_LOCAL tạo EM, begin, commit, rollback/close tương tự service trước.

### 32.1. Đây là test integration, không phải unit test mock

Nó cần một `EntityManagerFactory` và database thực.

### 32.2. EntityManager mới để verify

Không dùng entity instance cũ hoặc context của transaction vừa ghi. Khi test success, phải thấy committed rows bằng EM mới.

---

## 33. Spring Data `@DataJpaTest`: bẫy rollback mặc định

```java
@DataJpaTest
class InventoryRepositoryTest {

    @Autowired
    InventoryItemRepository items;

    @Test
    void createsItem() {
        items.save(
            new InventoryItem("SKU-TEST", 10)
        );

        assertTrue(
            items.findById("SKU-TEST").isPresent()
        );
    }
}
```

Spring Boot `@DataJpaTest` **thường chạy mỗi test trong transaction và rollback khi test kết thúc**.

### 33.1. Điều bài test chứng minh

Repository có thể persist/load entity **trong transaction thử nghiệm**.

### 33.2. Điều bài test không tự chứng minh

Nó không chứng minh dữ liệu được commit và transaction khác thấy row; cũng không chứng minh service `@Transactional` boundary ngoài test chạy đúng.

### 33.3. Dùng `flush` và `clear` trong test

```java
testEntityManager.flush();
testEntityManager.clear();
```

giúp đọc lại qua persistence context sạch trong cùng test transaction, nhưng **không biến dữ liệu thành committed state**.

### 33.4. Nếu test unique/constraint ở commit

Một constraint deferred hoặc lỗi xảy ra khi commit có thể không xuất hiện chỉ bởi `flush`. Cần test transaction boundary thật.

---

## 34. Spring service: test commit thật

Ví dụ cấu trúc với Spring Boot:

```java
@SpringBootTest
class SpringReservationIT {

    @Autowired
    SpringJpaReservationService service;

    @Autowired
    InventoryItemRepository items;

    @Autowired
    PlatformTransactionManager transactionManager;

    @Autowired
    EntityManagerFactory emf;

    private TransactionTemplate tx;

    @BeforeEach
    void setUp() {
        tx = new TransactionTemplate(transactionManager);
    }

    @Test
    void commitsReservation() {
        String sku =
            "SKU-" + UUID.randomUUID();

        tx.executeWithoutResult(status ->
            items.save(new InventoryItem(sku, 10))
        );

        ReserveCommand command =
            new ReserveCommand(
                "REQ-" + UUID.randomUUID(),
                sku,
                3
            );

        service.reserve(command);

        EntityManager verify =
            emf.createEntityManager();

        try {
            InventoryItem persisted =
                verify.find(InventoryItem.class, sku);

            StockMovement movement =
                verify.find(
                    StockMovement.class,
                    command.requestId()
                );

            assertEquals(
                7, persisted.getAvailable()
            );
            assertNotNull(movement);

        } finally {
            verify.close();
        }
    }
}
```

### 34.1. Không đặt outer test @Transactional cho test này

Nếu test class/method có outer transactional test boundary, service có thể join transaction đó và chưa commit khi assertions chạy. Muốn xác minh commit thật, test phải tổ chức boundary độc lập.

### 34.2. Testcontainers/database thật

Spring Boot test nên dùng cùng PostgreSQL migrations/schema, không mặc định H2 chỉ vì `@DataJpaTest` auto-config.

### 34.3. So sánh cùng command/invariant

Nếu test JPA thuần và Spring dùng cùng fixture/clock/DB version, cả hai phải cho kết quả business tương đương.

---

## 35. Test rollback khi movement INSERT lỗi

Thiết kế test:

1. Tạo stock item `available=10`, commit.
2. Tạo movement có `requestId=REQ-1`, commit.
3. Gọi lệnh mới **cùng** `REQ-1` nhưng payload khác, hoặc tạo race duplicate theo một fixture có kiểm soát.
4. Application phải từ chối lệnh, stock vẫn là 10 sau commit/rollback.
5. Đọc lại bằng context mới.

### 35.1. Phân biệt business validation và DB conflict

Nếu service detect existing movement rồi ném `IllegalStateException`, test chỉ chứng minh validation path. Muốn test **UNIQUE constraint** ở DB, cần concurrent attempts hoặc native SQL/controlled insert path gây duplicate thực.

### 35.2. Exception timing khác giữa hai hướng

JPA thuần có thể thấy lỗi ở `em.flush()` hoặc `commit()`; Spring có thể báo từ repository `save`, explicit flush hoặc transaction interceptor commit. Test không nên assert lỗi phải xảy ra ở cùng một dòng nếu mục tiêu là portability.

### 35.3. Kết quả DB phải atomic

Dù exception nằm ở API nào, không được có movement mới mà stock thiếu cập nhật hoặc stock giảm nhưng movement không được lưu, nếu cả hai thuộc một transaction được rollback.

---

## 36. Test managed identity và dirty checking

Ở cả hai hướng, trong một transaction:

```java
InventoryItem first =
    em.find(InventoryItem.class, sku);

InventoryItem second =
    em.find(InventoryItem.class, sku);

assertSame(first, second);

first.reserve(1);
```

Sau commit, mở EM mới và assert số tồn giảm 1.

### 36.1. Cần cùng underlying context

Với Spring, gọi repository trong một service `@Transactional` để các lời gọi dùng cùng transaction-bound EM. Nếu mỗi method ngoài transaction tạo context khác nhau, `assertSame` có thể không đúng.

### 36.2. Không lấy query count làm JPA contract

Provider có thể cache/fetch khác nhau. JPA identity map semantics không hứa số SQL statements chính xác.

---

## 37. Test `persist` so với `save` trên assigned ID

Một thí nghiệm riêng:

**JPA thuần:**

```java
em.persist(
    new StockMovement(
        "REQ-" + UUID.randomUUID(),
        sku, 1, clock.instant()
    )
);
```

**Spring Data JPA:**

```java
movements.save(
    new StockMovement(
        "REQ-" + UUID.randomUUID(),
        sku, 1, clock.instant()
    )
);
```

### 37.1. Cùng committed rows

Nếu schema và data hợp lệ, cả hai có thể lưu movement như kỳ vọng.

### 37.2. SQL thực thi có thể khác

`save` có thể chọn `merge` dựa trên newness detection của assigned identifier. Khi muốn kết luận có SELECT trước INSERT, dùng SQL/JDBC instrumentation và ghi rõ Spring Data/Hibernate version; không biến một log cụ thể thành lời hứa vĩnh viễn của Spring Data.

### 37.3. Test object identity sau merge

Nếu `save` dùng merge, entity trả về có thể là instance khác. Không tiếp tục sửa tham số đầu vào detached rồi nghĩ Spring luôn lưu các thay đổi.

---

## 38. Test optimistic locking với hai transactions

Dùng hai EntityManagers độc lập hoặc hai Spring threads/transaction boundaries đúng:

```text
TX A reads SKU-RED version 0
TX B reads SKU-RED version 0
TX A reserve 1, commits
TX B reserve 2, attempts commit
```

Expected: provider phát hiện conflict theo `@Version`, không silently commit cả hai trên stale version.

### 38.1. JPA thuần

Hai EM được tạo riêng, begin transactions riêng; có cleanup/rollback nếu conflict.

### 38.2. Spring

Hai @Transactional service invocations độc lập trong hai threads hoặc test dùng `TransactionTemplate` với boundaries rõ, không cùng outer test transaction.

### 38.3. Không dựa vào thread scheduling ngẫu nhiên

Dùng `CountDownLatch`/barriers để bảo đảm cả hai transactions đã đọc version cũ trước khi một bên commit. Test có timeout để tránh treo.

### 38.4. Assert actual DB state

Đọc bằng fresh context; số tồn cuối phải phản ánh một commit hợp lệ hoặc business retry theo policy.

---

# Phần X — Thực hành kiểm thử đồng nhất

## 39. Các tình huống cần so sánh

| Hành vi | JPA thuần | Spring ORM/JPA | Kỳ vọng business |
| --- | --- | --- | --- |
| New entity persist | `em.persist` | `em.persist` hoặc `save` | Row tồn tại sau commit |
| Managed update | Dirty checking | Dirty checking | UPDATE đúng giá trị |
| Detached update | `em.merge` | `merge`/repository.save | Managed copy đúng |
| Rollback khi lỗi | Code rollback | Interceptor rollback theo rules | DB không có partial commit |
| Checked exception | Code quyết định | `rollbackFor` nếu cần | Theo hợp đồng |
| Duplicate key | DB constraint | DB constraint + translation | Không tạo duplicate |
| Optimistic conflict | JPA exception | JPA/Spring translated exception | Không lost update |
| Lazy outside scope | Context closed | OSIV có thể ảnh hưởng | DTO không cần lazy ở API |
| Flush | `em.flush` | `em.flush`/repo.flush | Chưa commit |
| Commit | Explicit | At proxy boundary | Dữ liệu visible sau success |
| Retry | App orchestration | `RetryTemplate`/outer coordinator | New transaction, idempotent |
| Repository convenience | DAO/custom code | JpaRepository | Không đổi JPA invariants |
| SQL batching | Provider config | Provider config | Đo thực tế |
| Exception handling | JPA/provider/JDBC | DataAccessException translation | Phân loại đúng lỗi |
| Test fixture | Explicit transactions | Spring test transactions | Đọc committed state độc lập |

---

## 40. Không so sánh performance qua một request tùy ý

Một câu hỏi phổ biến:

> “Spring Data JPA chậm hơn JPA thuần bao nhiêu?”

Không có một hệ số chung. Overhead có thể đến từ:

- Repository method dispatch/proxy.
- EntityManager factory bootstrap.
- Connection acquisition.
- Query construction.
- Hibernate flush/dirty checking.
- SQL plan/index/DB latency.
- Fetch plan/N+1.
- Network round trips.
- Transaction boundaries.
- Session-per-request/OSIV.
- Batch size/generator strategy.
- SQL logging/instrumentation.
- Hikari connection pool tuning.

### 40.1. Cần đo ở đúng cấp

Đo end-to-end latency (p50/p95), DB round trips, SQL executions, rows read/written, heap allocations, connection occupancy và transaction duration.

### 40.2. Warm-up và schema

Benchmark chạy trên hai configs khác nhau về DDL/index/driver/pool size không có ý nghĩa so sánh overhead framework.

### 40.3. `saveAll` không chứng minh batching

Spring Data `saveAll` chỉ cung cấp API tập hợp; JDBC batching là optimization của provider/driver.

### 40.4. Một method call không luôn tương đương một SQL

Một `save` có thể dẫn tới SELECT/INSERT/UPDATE tùy state/newness, một `find` có thể hit L1, một `persist` có thể delay INSERT. Cần đo SQL thực chứ không đếm Java calls.

---

# Phần XI — Khi nào dùng mỗi cách?

## 41. JPA thuần RESOURCE_LOCAL phù hợp khi nào?

Có thể phù hợp:

- Java SE/CLI/batch nhỏ không dùng Spring.
- Cần full control về EntityManager lifecycle.
- Một công cụ migration/import riêng biệt.
- Test tối giản JPA provider độc lập framework.
- Môi trường đã có transaction orchestration riêng.

Tradeoffs:

- Nhiều code begin/commit/rollback/close.
- Dễ quên cleanup.
- Khó giữ transaction boundaries nhất quán khi nhiều services gọi nhau.
- Cần tự cấu hình DataSource/pool/observability.
- Dễ tạo mỗi method một transaction quá nhỏ nếu không thiết kế tốt.

### 41.1. Thuần JPA không đồng nghĩa kém an toàn hoặc kém hiệu năng

Với cùng provider/DB/schema/transactions, các bảo đảm entity mapping và ACID không kém chỉ vì không dùng Spring.

---

## 42. Spring ORM + EntityManager phù hợp khi nào?

Phù hợp khi:

- Đang dùng Spring DI/transactions.
- Cần JPA query/Criteria API linh hoạt.
- Có custom aggregate operations.
- Muốn chủ động `persist`, `merge`, `remove` semantics.
- Không muốn tự quản lý EntityManager lifetime.

Tradeoffs:

- Cần hiểu proxy và transaction boundaries.
- Có thể bị self-invocation.
- Dễ lạm dụng OSIV.
- Annotation `@Transactional` không thay được tư duy về isolation/idempotency.
- Exception translation phụ thuộc cách cấu hình bean/path.

---

## 43. Spring Data JPA phù hợp khi nào?

Phù hợp khi:

- Có nhiều CRUD/query methods chuẩn.
- Muốn type-safe repository interfaces.
- Sử dụng paging/sorting/projections.
- Tích hợp Spring Boot/transactions.
- Giảm code boilerplate cho truy cập dữ liệu.

Tradeoffs:

- Cần hiểu `save` có thể gọi persist/merge.
- Assigned IDs và newness detection.
- Query derivation có thể tạo SQL không tối ưu cho một số workloads.
- Repository methods không thay service transaction boundary.
- Có thể dùng sai `findAll`/paging, gây memory/DB load.
- Không tự loại N+1, cache stale, concurrent writes hay idempotency problems.

**Chọn công cụ để giảm code không cần thiết; không chọn để né hiểu JPA.**

---

# Phần XII — Lỗi thường gặp

## 44. “Spring Data JPA không còn là JPA”

Sai. Spring Data JPA sử dụng JPA provider, EntityManager, entity mappings và transaction integration để triển khai repositories.

## 45. “`save()` luôn INSERT”

Sai. `save` có thể dùng persist hoặc merge tùy entity newness. Với assigned ID phải cẩn thận.

## 46. “`save()` luôn UPDATE nếu ID khác null”

Không luôn. `merge` có thể tạo bản ghi mới nếu entity chưa tồn tại theo mapping/DB state. Không coi đây là UPSERT atomic portable.

## 47. “Managed entity phải gọi `save` sau setter”

Không bắt buộc trong active JPA transaction; dirty checking đồng bộ thay đổi. Điều kiện là entity thực sự managed và transaction đúng.

## 48. “Spring tự commit ngay khi `saveAndFlush`”

Sai. Flush khác commit. Outer transaction có thể rollback.

## 49. “Có `@Transactional` thì nested method luôn có transaction riêng”

Sai. `REQUIRED` thường join existing transaction; `REQUIRES_NEW` cần đi qua proxy/manager phù hợp.

## 50. “`this.methodWithTransactional()` kích hoạt proxy”

Trong proxy-based Spring, self-invocation có thể bypass advice.

## 51. “Mọi checked exception đều rollback với Spring”

Không phải default rollback rules. Dùng `rollbackFor` khi business cần.

## 52. “`readOnly=true` là DB-level security guarantee”

Không. Đây chủ yếu là transaction hint/optimization có behavior tùy manager/provider/DB. Muốn security cần DB grants.

## 53. “Spring @PersistenceContext EM là một EM singleton thật”

Không. Thường là proxy điều phối đến transaction-bound actual EM.

## 54. “Cần close EM được Spring inject”

Không. Spring quản lý; tự close có thể sai lifecycle.

## 55. “Open Session in View giải quyết toàn bộ lazy loading”

Không. Nó có thể che việc fetch sai chỗ và dẫn tới N+1/consistency problems.

## 56. “@DataJpaTest xanh nghĩa là dữ liệu đã commit”

Không. Test thường rollback; cần kiểm tra ranh giới transaction thật khi quan sát committed state.

## 57. “JPA thuần và Spring có SQL khác thì do Spring đổi JPQL”

Không nhất thiết. Có thể do `save` chọn merge, config provider, schema, flush mode, transaction/fetch plan, cache hoặc session boundaries khác nhau.

## 58. “Spring tự sửa optimistic locking conflict”

Không. Provider/DB phát hiện conflict; application quyết định retry/merge nghiệp vụ trong transaction mới.

## 59. “Một exception từ `commit()` chứng minh rollback”

Không luôn, nhất là khi mất xác nhận commit qua network. Cần idempotency/reconciliation cho writes có rủi ro lặp.

## 60. “Chuyển framework là đủ để hết N+1”

Không. Cần fetch plans, projections, batching và đo SQL.

---

# Phần XIII — Bài tập tổng hợp

## 61. Bộ bài tập có lời giải

### Bài 1. Entity có cần extends `JpaRepository` không?

**Lời giải:** Không. Entity là `@Entity`; repository interface riêng extends `JpaRepository<InventoryItem,String>`.

### Bài 2. JPA thuần ai close EntityManager?

**Lời giải:** Code tạo EM phải close theo lifecycle, kể cả khi exception.

### Bài 3. Spring @PersistenceContext có cần gọi `em.close()` không?

**Lời giải:** Không trong setup container/Spring-managed thông thường; framework chịu trách nhiệm.

### Bài 4. Hai lần find cùng ID trong cùng persistence context?

**Lời giải:** Managed identity map bảo đảm một representation trong context; đừng suy SQL count.

### Bài 5. Hai lần find ở hai transactions độc lập?

**Lời giải:** Có thể là hai Java instances khác nhau dù cùng row.

### Bài 6. Update field managed entity không gọi save?

**Lời giải:** Dirty checking của JPA có thể đồng bộ khi flush/commit.

### Bài 7. Update detached entity không merge?

**Lời giải:** Thay đổi không tự được đồng bộ trong context mới; cần load managed entity rồi sửa hoặc merge đúng cách.

### Bài 8. `em.merge(detached)` trả object nào?

**Lời giải:** Trả managed representation; detached input không tự trở thành managed.

### Bài 9. `JpaRepository.save(new StockMovement(requestId))` tạo SELECT?

**Lời giải:** Có thể, vì assigned ID làm newness detection chọn merge. Cần đo trên Spring Data/provider version thực.

### Bài 10. `saveAll` tự JDBC batch?

**Lời giải:** Không có bảo đảm; tùy provider/driver/mapping/transaction.

### Bài 11. JPA thuần `flush()` rồi rollback?

**Lời giải:** SQL đã flush không đồng nghĩa committed; rollback undo transaction theo DB semantics.

### Bài 12. Spring `saveAndFlush()` trong outer transaction?

**Lời giải:** Vẫn thuộc outer transaction, chưa tự commit.

### Bài 13. Checked IOException trong `@Transactional` method?

**Lời giải:** Default Spring rollback có thể không áp; dùng `rollbackFor` nếu cần.

### Bài 14. Ném unchecked exception từ service?

**Lời giải:** Spring thường rollback theo default khi exception thoát qua transactional interceptor; JPA thuần cần catch/rollback code.

### Bài 15. Catch exception rồi return bình thường?

**Lời giải:** Transaction có thể đã rollback-only. Đừng tiếp tục dùng failed context.

### Bài 16. `REQUIRES_NEW` có luôn cùng transaction outer?

**Lời giải:** Không; nó tạo independent transaction khi được áp đúng; có thể commit dù outer rollback.

### Bài 17. `this.requiresNewMethod()`?

**Lời giải:** Có thể bypass Spring proxy, không có transaction advice như mong muốn.

### Bài 18. `@Transactional(readOnly=true)` có ngăn SQL UPDATE chắc chắn?

**Lời giải:** Không portable như authorization enforcement; dùng DB read-only permissions nếu yêu cầu.

### Bài 19. Controller lazy-load sau service transaction?

**Lời giải:** Có thể lỗi nếu context đóng; OSIV có thể che vấn đề. Nên fetch/map DTO trong transaction.

### Bài 20. Spring Data repository không có outer transaction, save hai bảng?

**Lời giải:** Có thể tạo nhiều transactions, không atomic. Đặt business transaction ở service.

### Bài 21. Optimistic conflict giữa hai updates?

**Lời giải:** JPA `@Version` semantics giống nhau; exception wrapper/boundary có thể khác.

### Bài 22. `@DataJpaTest` persistAndFlush rồi query thấy row?

**Lời giải:** Có thể chỉ là row uncommitted trong test transaction. Không tự chứng minh commit.

### Bài 23. Test Spring và JPA thuần khác DB engine?

**Lời giải:** Không so sánh công bằng. Cần cùng schema/provider/driver/database.

### Bài 24. H2 cho nullable UNIQUE kết quả khác PostgreSQL?

**Lời giải:** Đây là khác biệt DB semantics, không phải “Spring vs JPA”.

### Bài 25. JPA thuần bật Hibernate SQL logs, Spring không bật?

**Lời giải:** Không so SQL count trực tiếp khi instrumentation khác nhau; cấu hình thống nhất.

### Bài 26. Repository `findAll()` load triệu rows?

**Lời giải:** Dùng pagination/streaming/projection và giới hạn fetch. Framework không tự đảm bảo memory-safe.

### Bài 27. `@Repository` có thể dịch mọi exception ở mọi nơi?

**Lời giải:** Translation phụ thuộc bean/path/interceptor. Không suy rộng cho mọi exception từ bất kỳ code nào.

### Bài 28. API trả HTTP 500 sau mất kết nối lúc commit?

**Lời giải:** Outcome có thể unknown; dùng requestId/idempotency và đối soát.

### Bài 29. Cùng requestId được gửi bởi hai threads?

**Lời giải:** Pre-check chưa đủ; DB primary key ngăn duplicate, application xử lý conflict/retry đúng.

### Bài 30. Application restart làm mất idempotency Set?

**Lời giải:** Dùng durable DB record/unique constraint hoặc store bền vững khác.

### Bài 31. Có thể dùng Spring ORM nhưng bỏ Spring Data repositories?

**Lời giải:** Có. `@PersistenceContext` + `EntityManager` trong Spring-managed transactions.

### Bài 32. JPA thuần trong Jakarta EE có thể dùng JTA?

**Lời giải:** Có, khi container-managed. Bài dùng RESOURCE_LOCAL làm một trường hợp so sánh cụ thể.

### Bài 33. TransactionTemplate có giải quyết self-invocation không?

**Lời giải:** Nó có thể tạo transaction programmatically theo cấu hình và tránh phụ thuộc method proxy, nhưng vẫn cần xác định propagation/outer boundary.

### Bài 34. SQL khác vì `save` gọi merge thay persist?

**Lời giải:** Có thể; tìm hiểu entity newness, assigned IDs, provider SQL logs/JDBC metrics.

### Bài 35. Đọc lại sau commit bằng cùng EM?

**Lời giải:** Có thể bị L1 cache che state; dùng fresh EM/transaction để xác minh committed state.

### Bài 36. Cấu hình Spring `ddl-auto=update` trong production?

**Lời giải:** Không nên mặc định dùng thay migration có kiểm soát; cần Flyway/Liquibase và test DDL thực.

### Bài 37. Mục tiêu chuyển từ JPA thuần sang Spring là đổi schema?

**Lời giải:** Không. Nên giữ entity/schema/domain contract, thay hạ tầng orchestration có kiểm soát.

### Bài 38. N+1 vẫn xảy ra sau migration sang Spring Data?

**Lời giải:** Có thể; cần fetch joins/EntityGraph/projections và kiểm thử SQL.

### Bài 39. Service trả detached entity rồi sửa field?

**Lời giải:** Không có dirty checking ngoài context; cần explicit application operation với new transaction.

### Bài 40. Khi nào chọn custom DAO thay JpaRepository?

**Lời giải:** Khi cần kiểm soát rõ persist/merge, dynamic query phức tạp, batch/native SQL hoặc performance requirements; vẫn có thể dùng Spring transaction infrastructure.

---

## 62. Checklist đối chiếu hai triển khai

### Cấu hình

1. Cả hai dùng cùng entity classes?
2. Cùng JPA provider/version/dialect?
3. Cùng database engine/version/JDBC driver?
4. Cùng migrations/DDL/indexes/constraints?
5. Cùng datasource pool và connection limits khi benchmark?
6. Cùng second-level/query cache settings?
7. Cùng JDBC batching và ID generation?
8. Cùng clock/timezone behavior?

### Entity và API

9. Đã phân biệt `persist` và `merge`?
10. Có biết `JpaRepository.save` dùng newness detection?
11. Assigned IDs có strategy phù hợp?
12. Có tránh merge managed entity vô ích?
13. Có phân biệt managed/detached objects?
14. Có giữ domain invariants trong cả hai implementations?
15. Có dùng bound parameters khi query?
16. Có kiểm tra lazy fetching/DTO mapping?

### Transaction

17. RESOURCE_LOCAL có begin/commit/rollback/close?
18. Spring service `@Transactional` có đi qua proxy?
19. Có tránh self-invocation cho transactional boundaries?
20. Có hiểu default rollback rules cho checked exception?
21. Có hiểu REQUIRED/REQUIRES_NEW và atomicity?
22. Có phân biệt flush và commit?
23. Có đảm bảo nhiều repository calls thuộc cùng business transaction?
24. Có tránh retry bên trong transaction đã lỗi?
25. Có idempotency khi commit ACK thất lạc?

### Kiểm thử

26. Có test JPA thuần và Spring với same DB fixture?
27. Có dùng fresh EM sau commit để verify?
28. Có biết `@DataJpaTest` rollback mặc định?
29. Có test actual transaction boundary của service?
30. Có test optimistic concurrency?
31. Có test duplicate requestId/UNIQUE?
32. Có test rollback khi movement insert lỗi?
33. Có test lazy loading sau service boundary?
34. Có phân biệt JPA/provider exceptions với Spring translation?
35. Có test `save` assigned ID semantics?
36. Có so sánh SQL trên cùng provider/configuration?
37. Có đo latency/DB round trips thay vì suy từ Java calls?
38. Có tránh test xanh do L1 cache?
39. Có test error ở commit, không chỉ ở persist?
40. Có mô tả những điểm vendor-specific chưa thể kết luận?

---

## 63. Sơ đồ lựa chọn cách triển khai

```text
                      JPA application
                             |
                             v
                   Cần Spring platform?
                      /           \
                    Không          Có
                     |             |
                     v             v
           Java SE / Jakarta   Spring transaction
           EE integration      infrastructure
                     |             |
                     |             v
                     |       CRUD/query conventions
                     |       có phù hợp không?
                     |           /        \
                     |         Có         Không
                     |          |           |
                     |          v           v
                     |      Spring Data    Spring ORM
                     |      JpaRepository  EntityManager DAO
                     |          |           |
                     +----------+-----------+
                                |
                                v
                     Same JPA provider/entity
                                |
                                v
                    Transaction boundary đúng
                                |
                                v
                    Commit + fresh EM verification
                                |
                                v
                  Business invariant được giữ
```

**Quyết định dùng framework không được thay thế việc hiểu JPA.** Một ứng dụng Spring được thiết kế sai transaction/relationship vẫn có thể làm mất dữ liệu như một ứng dụng JPA thuần được thiết kế sai.

---

## 64. Tổng kết

Khi đối chiếu JPA thuần và tích hợp Spring, điều quan trọng là tách ba lớp:

**Lớp JPA chuẩn:**

- Entity state và persistence context.
- `persist`, `merge`, `remove`, `find`, JPQL/Criteria.
- Dirty checking, flush, versioning.
- Mapping relationship, cascade, orphan removal.
- Transaction integration semantics theo môi trường.

**Lớp provider/database:**

- SQL generation, batching, fetch strategies.
- JDBC/driver behavior.
- Constraints, locks, isolation.
- Cache implementation và SQL timings.

**Lớp Spring:**

- DI/configuration/auto-configuration.
- Transaction interceptors, `@Transactional`, propagation/rollback rules.
- Shared EntityManager proxy và lifecycle.
- Spring Data repositories, `save` newness detection, paging/query derivation.
- Exception translation, integration testing utilities.

Những nguyên tắc thực hành quan trọng nhất:

1. **Spring Data JPA vẫn dùng JPA**, không phải một ORM đặc tả khác.
2. **JPA thuần RESOURCE_LOCAL tự quản lý EM/transaction; Spring thường quản lý chúng qua transaction infrastructure.**
3. **Entity mới dùng `persist`, detached dùng `merge` theo ngữ nghĩa JPA; repository `save` chọn đường phù hợp theo newness detection.**
4. **Managed entity được dirty-check**, không bắt buộc gọi repository `save` sau mọi setter.
5. **`flush()` và `saveAndFlush()` không phải commit.**
6. **`@Transactional` có proxy boundary, propagation và rollback rules**, phải hiểu trước khi dùng.
7. **Spring `readOnly=true` và OSIV không thay domain consistency, security hoặc fetch planning.**
8. **EntityManager proxy không phải một persistence context toàn cục**; không close injected EM thủ công.
9. **Mọi writes cùng một nghiệp vụ phải nằm trong transaction boundary thích hợp.**
10. **Kiểm thử commit thật với EntityManager mới**, nhất là khi Spring tests mặc định rollback.
11. **Đối chiếu trên cùng provider/driver/DB/schema**, tránh quy lỗi configuration khác nhau cho framework.
12. **Khi gặp concurrency hoặc connection failure, cả hai cần rollback/discard context và idempotent retry/reconciliation phù hợp.**
13. **Tối ưu hiệu năng phải dựa trên số đo** về SQL, round trips và transaction duration, không phải tên API.
14. **Chọn công cụ theo nhu cầu**, dùng JPA thuần cho những chương trình cần control tối giản, Spring ORM cho custom JPA operations, Spring Data JPA cho repository convenience.

**JPA quyết định ngữ nghĩa persistence; Spring giúp tổ chức việc sử dụng JPA trong ứng dụng. Khi entity mapping, transaction boundaries, database và nghiệp vụ giống nhau, cả hai phải giữ cùng dữ liệu đúng — và mọi khác biệt cần được giải thích ở đúng tầng của hệ thống.**
