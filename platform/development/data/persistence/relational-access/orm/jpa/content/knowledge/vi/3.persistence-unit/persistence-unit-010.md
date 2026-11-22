# Quản lý nhiều persistence unit trong cùng ứng dụng

> **Chủ đề:** Data Persistence – Relational Access, ORM, JPA  
> **Nhóm kiến thức:** Persistence Unit

Một ứng dụng Java không bắt buộc chỉ có một **persistence unit (PU)**. Chẳng hạn, hệ thống bán hàng có thể dùng một cơ sở dữ liệu cho đơn hàng, một cơ sở dữ liệu khác cho nhật ký kiểm toán; cùng ứng dụng cần truy cập cả hai nhưng với cấu hình kết nối, tập entity, transaction và chính sách vận hành khác nhau. JPA cho phép khai báo nhiều persistence unit, mỗi unit có một **EntityManagerFactory** và quản lý các **EntityManager** của riêng nó.

Bài học này hướng dẫn cách thiết kế, cấu hình, khởi tạo, sử dụng và vận hành nhiều persistence unit trong một ứng dụng. Nội dung áp dụng cho **Jakarta Persistence (JPA)** và minh họa bằng Java SE cùng Spring Boot. Những điểm đặc biệt quan trọng là **chọn đúng unit khi truy cập dữ liệu**, **đảm bảo entity thuộc đúng unit**, và **hiểu ranh giới transaction giữa các unit**.

## 1. Persistence unit là gì và vì sao cần nhiều unit?

Một persistence unit là một tập cấu hình persistence được đặt tên, bao gồm những thông tin như:

- **Tên unit:** tên logic để ứng dụng chọn đúng cấu hình, ví dụ **salesPU**, **auditPU**.
- **Các managed class:** entity và các loại được mapping mà provider quản lý trong unit.
- **Data source hoặc thông số kết nối:** nơi ORM đọc/ghi dữ liệu.
- **Loại transaction:** resource-local hoặc JTA.
- **Provider và thuộc tính vendor:** ví dụ Hibernate, cấu hình SQL, batch, cache, schema validation.
- **Mapping metadata:** annotation, XML mapping và các quy tắc về bảng, cột, quan hệ.

Khi ứng dụng tạo **EntityManagerFactory** từ unit có tên **salesPU**, factory ấy được cấu hình dựa trên metadata của **salesPU**. **EntityManager** được tạo từ factory đó quản lý các entity thuộc unit và làm việc với tài nguyên persistence tương ứng.

Ví dụ tổ chức một ứng dụng:

~~~text
                       Ứng dụng Java
                             |
                +------------+-------------+
                |                          |
            salesPU                     auditPU
                |                          |
     EntityManagerFactory A       EntityManagerFactory B
                |                          |
      EntityManager A1, A2...      EntityManager B1, B2...
                |                          |
         DataSource Sales             DataSource Audit
                |                          |
          sales_database             audit_database
                |                          |
      SalesOrder, OrderItem            AuditEvent
~~~

**Phân biệt các khái niệm:**

| Khái niệm | Phạm vi và vai trò |
|---|---|
| **Persistence unit** | Cấu hình logic được đặt tên, xác định tập mapping và tài nguyên persistence |
| **EntityManagerFactory (EMF)** | Factory tạo EntityManager theo cấu hình unit; thường tạo một lần và tái sử dụng |
| **EntityManager (EM)** | API thao tác với entity, query và persistence context; có vòng đời ngắn theo đơn vị công việc |
| **Persistence context** | Nơi quản lý identity và trạng thái các entity đang managed |
| **DataSource / Connection pool** | Cấp kết nối JDBC tới cơ sở dữ liệu; không đồng nghĩa persistence context |
| **Transaction** | Phạm vi nguyên tử của những thay đổi dữ liệu, do resource-local transaction hoặc transaction manager quản lý |

Một **EMF** có thể tạo rất nhiều **EM**; không tạo EMF mới cho mỗi HTTP request. **EntityManagerFactory** được thiết kế để dùng chung giữa các thread; **EntityManager không thread-safe** và không nên được chia sẻ tự do giữa các request hoặc thread.

### 1.1. Những trường hợp cần nhiều persistence unit

| Tình huống | Lý do tách unit | Điểm cần cân nhắc |
|---|---|---|
| Đơn hàng và kiểm toán ở hai database | Tách nguồn dữ liệu, quyền truy cập và vòng đời vận hành | Không có atomic commit xuyên hai DB theo mặc định |
| Hệ thống tích hợp database mới và database cũ | Hai schema, driver, cách mapping khác nhau | Quản lý migration, kiểu dữ liệu, encoding |
| Hai miền dữ liệu dùng provider/cấu hình ORM riêng | Tập entity, cache, schema hoặc setting riêng | Tăng số EMF, pool, cấu hình và giám sát |
| Ứng dụng đồng thời truy cập database tác nghiệp và database báo cáo | Tối ưu cấu hình truy cập, tách workload | Chú ý độ trễ sao chép và tính nhất quán dữ liệu |
| Một số nhóm tenant có database riêng | Cách ly tài nguyên và dữ liệu | Nhiều tenant động thường phù hợp cơ chế multitenancy hơn việc khai báo thủ công hàng trăm unit |

**Không cần tạo nhiều unit chỉ vì có nhiều bảng hoặc nhiều repository.** Một unit có thể quản lý rất nhiều entity/bảng trong cùng database. Nếu các module cùng dùng một transaction, cùng data source và cùng cấu hình ORM, một persistence unit thường đơn giản hơn.

Nhiều unit cũng không đồng nghĩa bắt buộc nhiều server vật lý: hai unit có thể trỏ tới hai schema hoặc cùng một database. Nhưng khi cùng trỏ tới một DB, cần có lý do cụ thể để chấp nhận sự tách biệt của persistence context, cache và transaction configuration.

## 2. Các ranh giới mà mỗi unit tạo ra

### 2.1. Managed entity được xác định theo từng unit

Giả sử:

- **salesPU** quản lý **SalesOrder**, **OrderItem**, **Customer**.
- **auditPU** quản lý **AuditEvent**.

Một EntityManager thuộc **salesPU** không được mặc nhiên dùng để persist **AuditEvent** chỉ vì class có **@Entity**. Entity phải thuộc tập managed types mà unit đó khai báo/khám phá. Nếu không, provider có thể ném lỗi như **Unknown entity**, **Not a managed type** hoặc **IllegalArgumentException** tùy API/provider.

Một entity class có thể được mapping trong **nhiều unit** nếu được cấu hình như vậy; khi ấy không nên hiểu rằng object đang managed trong unit A cũng được unit B quản lý. Mỗi persistence context vẫn có identity map và vòng đời riêng.

### 2.2. Entity relationship không băng qua hai unit độc lập

Ví dụ class **SalesOrder** thuộc **salesPU**, **AuditEvent** thuộc **auditPU**. Không nên viết mapping trực tiếp:

~~~java
// Sai ý tưởng nếu AuditEvent chỉ được quản lý trong auditPU.
@OneToMany
private List<AuditEvent> auditEvents;
~~~

JPA association như **@OneToMany** hay **@ManyToOne** phải được provider giải quyết trong phạm vi metadata của unit đang chứa entity liên quan. Muốn liên hệ dữ liệu thuộc hai database, thông thường lưu một **business identifier**:

~~~java
@Entity
@Table(name = "audit_events")
public class AuditEvent {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_reference", nullable = false)
    private String orderReference; // ID nghiệp vụ; không phải JPA association sang salesPU

    // Các thuộc tính khác...
}
~~~

Ứng dụng chủ động tra cứu bằng identifier và ghép dữ liệu ở service/DTO. Một FK thông thường ở database không thể dùng làm ràng buộc tham chiếu xuyên hai database độc lập trong đa số RDBMS; việc kiểm tra tính hợp lệ và bù trừ phải được thiết kế ở lớp nghiệp vụ.

### 2.3. Transaction không tự động gộp lại

Hai resource-local EntityManager thuộc hai unit có **hai transaction riêng**. Việc gọi **begin** ở cả hai không tạo ra một transaction phân tán.

~~~text
salesPU transaction:  BEGIN ── INSERT order ── COMMIT       ✓
auditPU transaction:  BEGIN ── INSERT audit ── COMMIT       ✗

Kết quả có thể: order đã tồn tại, audit chưa tồn tại.
~~~

Ngay cả khi cả hai unit trỏ tới cùng database, hai EntityManager với hai connection/resource-local transaction khác nhau cũng không tự động chia sẻ một giao dịch. Nếu cần nguyên tử giữa nhiều tài nguyên, phải dùng transaction coordinator phù hợp, ví dụ **JTA + XA** khi môi trường và driver hỗ trợ; hoặc thiết kế bất đồng bộ với **transactional outbox** khi phù hợp.

## 3. Khai báo nhiều unit trong persistence.xml

Trong JPA chuẩn, file cấu hình thường đặt tại:

~~~text
src/main/resources/
└── META-INF/
    └── persistence.xml
~~~

Một file có thể chứa nhiều phần tử **persistence-unit**, mỗi phần tử có **name** khác nhau. Ví dụ sau dùng **Jakarta Persistence 3.1**, provider Hibernate và hai H2 in-memory database, chỉ để minh họa khả năng khởi tạo độc lập trong Java SE. Trong một ứng dụng thật, thay URL, tài khoản và nguồn cấp credential bằng cấu hình theo môi trường.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="https://jakarta.ee/xml/ns/persistence
                 https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
             version="3.1">

    <persistence-unit name="salesPU" transaction-type="RESOURCE_LOCAL">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>

        <class>com.example.sales.SalesOrder</class>
        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:salesdb;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password" value=""/>

            <!-- Chỉ phục vụ ví dụ tạm thời; tạo lại schema khi khởi động -->
            <property name="hibernate.hbm2ddl.auto" value="create"/>
            <property name="hibernate.show_sql" value="true"/>
        </properties>
    </persistence-unit>

    <persistence-unit name="auditPU" transaction-type="RESOURCE_LOCAL">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>

        <class>com.example.audit.AuditEvent</class>
        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:auditdb;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password" value=""/>

            <!-- Chỉ phục vụ ví dụ tạm thời; tạo lại schema khi khởi động -->
            <property name="hibernate.hbm2ddl.auto" value="create"/>
            <property name="hibernate.show_sql" value="true"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

### 3.1. Giải thích từng thành phần

| Cấu hình | Ý nghĩa |
|---|---|
| **name="salesPU"** | Tên logic dùng trong **Persistence.createEntityManagerFactory("salesPU")** |
| **transaction-type="RESOURCE_LOCAL"** | Mỗi EntityManager điều khiển transaction bằng **EntityTransaction** |
| **provider** | Chỉ rõ triển khai JPA; có thể để cơ chế bootstrap chọn provider nếu môi trường cấu hình phù hợp |
| **class** | Liệt kê entity thuộc unit; không phải tên bảng |
| **exclude-unlisted-classes=true** | Không tự thu nạp thêm các lớp entity chưa liệt kê theo cơ chế khám phá của unit |
| **jakarta.persistence.jdbc.*** | Thuộc tính kết nối JDBC chuẩn cho cấu hình Java SE |
| **hibernate.hbm2ddl.auto** | Thuộc tính riêng của Hibernate điều khiển DDL; **create** có thể xóa/tạo lại bảng |

Hai unit phải được khai báo khác tên để chọn được chính xác. Trong ví dụ, **salesdb** và **auditdb** là hai H2 database trong bộ nhớ khác nhau. Chúng cần dependency **jakarta.persistence-api**, triển khai **Hibernate ORM** tương thích và driver **H2** trong runtime classpath. Tên package/class phải khớp với mã Java thực tế.

**Đặc biệt:** giá trị **hibernate.hbm2ddl.auto=create** là lựa chọn thuận tiện cho ví dụ độc lập, **không dùng với dữ liệu cần giữ**. Trong dự án thật, quản lý schema bằng migration (Flyway/Liquibase hoặc công cụ tương đương); nếu dùng Hibernate để kiểm tra, **validate** là lựa chọn hay gặp và vẫn phụ thuộc khả năng của provider.

### 3.2. Khai báo với DataSource do container quản lý

Khi triển khai trong Jakarta EE, server thường cung cấp các JNDI DataSource:

~~~xml
<persistence-unit name="salesPU" transaction-type="JTA">
    <jta-data-source>java:app/jdbc/SalesDS</jta-data-source>
    <class>com.example.sales.SalesOrder</class>
</persistence-unit>

<persistence-unit name="auditPU" transaction-type="JTA">
    <jta-data-source>java:app/jdbc/AuditDS</jta-data-source>
    <class>com.example.audit.AuditEvent</class>
</persistence-unit>
~~~

Đây là hai đoạn **persistence-unit** minh họa thay cho cấu hình Java SE ở trên. Tên JNDI và cách cung cấp DataSource phụ thuộc server. **jta-data-source** dùng để tích hợp với transaction manager JTA; **non-jta-data-source** dành cho truy cập không được JTA quản lý, thường gặp trong resource-local hoặc nhu cầu đặc thù. Không nên thay máy móc **transaction-type** mà không thay cấu hình transaction manager và DataSource tương ứng.

## 4. Ví dụ Java SE đầy đủ: hai database, hai unit

Mục tiêu: lưu đơn hàng vào **salesPU**, lưu nhật ký vào **auditPU** và chứng minh hai EntityManager truy cập hai tập entity độc lập.

### 4.1. Entity dành cho salesPU

File **com/example/sales/SalesOrder.java**:

~~~java
package com.example.sales;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "sales_orders")
public class SalesOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "reference_code", nullable = false, unique = true)
    private String referenceCode;

    @Column(name = "total_amount", nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount;

    protected SalesOrder() {
        // JPA cần constructor không tham số.
    }

    public SalesOrder(String referenceCode, BigDecimal totalAmount) {
        this.referenceCode = Objects.requireNonNull(referenceCode);
        this.totalAmount = Objects.requireNonNull(totalAmount);
    }

    public Long getId() { return id; }
    public String getReferenceCode() { return referenceCode; }
    public BigDecimal getTotalAmount() { return totalAmount; }
}
~~~

### 4.2. Entity dành cho auditPU

File **com/example/audit/AuditEvent.java**:

~~~java
package com.example.audit;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "audit_events")
public class AuditEvent {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "event_type", nullable = false)
    private String eventType;

    @Column(name = "entity_reference", nullable = false)
    private String entityReference;

    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;

    protected AuditEvent() {
    }

    public AuditEvent(String eventType, String entityReference, Instant occurredAt) {
        this.eventType = Objects.requireNonNull(eventType);
        this.entityReference = Objects.requireNonNull(entityReference);
        this.occurredAt = Objects.requireNonNull(occurredAt);
    }

    public Long getId() { return id; }
    public String getEventType() { return eventType; }
    public String getEntityReference() { return entityReference; }
}
~~~

Ở đây **entityReference** là chuỗi dùng để liên hệ sự kiện kiểm toán với đơn hàng, không phải **@ManyToOne** tới một entity thuộc unit khác.

### 4.3. Bootstrap hai EntityManagerFactory

File **com/example/MultipleUnitDemo.java**:

~~~java
package com.example;

import com.example.audit.AuditEvent;
import com.example.sales.SalesOrder;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public class MultipleUnitDemo {
    public static void main(String[] args) {
        // Hai lần bootstrap độc lập, mỗi lần chọn đúng tên persistence-unit.
        EntityManagerFactory salesEmf =
                Persistence.createEntityManagerFactory("salesPU");
        EntityManagerFactory auditEmf = null;

        try {
            auditEmf = Persistence.createEntityManagerFactory("auditPU");

            writeSalesOrder(salesEmf);
            writeAuditEvent(auditEmf);
            readBack(salesEmf, auditEmf);
        } finally {
            if (auditEmf != null) {
                auditEmf.close();
            }
            salesEmf.close();
        }
    }

    private static void writeSalesOrder(EntityManagerFactory factory) {
        EntityManager em = factory.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();
            em.persist(new SalesOrder(
                    "ORDER-2026-001", new BigDecimal("150000.00")));
            tx.commit();
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        } finally {
            em.close();
        }
    }

    private static void writeAuditEvent(EntityManagerFactory factory) {
        EntityManager em = factory.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();
            em.persist(new AuditEvent(
                    "ORDER_CREATED", "ORDER-2026-001", Instant.now()));
            tx.commit();
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        } finally {
            em.close();
        }
    }

    private static void readBack(
            EntityManagerFactory salesEmf,
            EntityManagerFactory auditEmf
    ) {
        EntityManager salesEm = salesEmf.createEntityManager();
        EntityManager auditEm = auditEmf.createEntityManager();
        try {
            List<SalesOrder> orders = salesEm.createQuery(
                    "select o from SalesOrder o", SalesOrder.class)
                    .getResultList();

            List<AuditEvent> events = auditEm.createQuery(
                    "select a from AuditEvent a", AuditEvent.class)
                    .getResultList();

            System.out.println("salesPU orders: " + orders.size());
            System.out.println("auditPU events: " + events.size());
        } finally {
            auditEm.close();
            salesEm.close();
        }
    }
}
~~~

Đoạn chương trình minh họa sẽ in số lượng đơn hàng và sự kiện theo từng unit nếu classpath/cấu hình H2/Hibernate và schema được thiết lập như trên. JPA không quy định **EntityManagerFactory** phải hỗ trợ **try-with-resources**, nên ví dụ đóng factory rõ ràng trong **finally**.

**Quan sát quan trọng:** **writeSalesOrder** đã commit trước khi **writeAuditEvent** bắt đầu. Nếu tạo audit thất bại, đơn hàng vẫn được lưu. Đó là hệ quả giao dịch độc lập, không phải lỗi JPA.

### 4.4. Điểm thường sai khi tự bootstrap

- Gọi **Persistence.createEntityManagerFactory("salePU")** trong khi file khai báo **salesPU**: unit không được tìm thấy.
- Đặt **persistence.xml** sai chỗ, ví dụ **src/main/java/persistence.xml** thay vì **META-INF/persistence.xml** trên classpath.
- Chỉ có **jakarta.persistence-api** mà thiếu JPA provider hoặc JDBC driver.
- Khai báo **javax.persistence** entity nhưng dùng bootstrap theo Jakarta hoặc ngược lại; cần nhất quán phiên bản API/provider.
- Khai báo class entity trong unit A nhưng tạo EntityManager từ unit B để persist.
- Tạo EMF trong mỗi method/request, làm tăng chi phí metadata/bootstrap và cạn pool connection.
- Dùng chung một EntityManager cho nhiều thread hoặc giữ persistence context quá lâu, làm tăng bộ nhớ và nguy cơ trạng thái cũ.

## 5. Java SE: tổ chức mã nguồn và vòng đời hợp lý

Một cấu trúc dự án giúp tách ranh giới:

~~~text
src/main/java/com/example/
├── sales/
│   ├── SalesOrder.java
│   ├── SalesOrderRepository.java
│   └── SalesService.java
├── audit/
│   ├── AuditEvent.java
│   ├── AuditEventRepository.java
│   └── AuditService.java
├── persistence/
│   └── PersistenceFactories.java
└── MultipleUnitDemo.java

src/main/resources/META-INF/persistence.xml
~~~

Có thể gom bước bootstrap trong một class quản lý hai factory:

~~~java
public final class PersistenceFactories implements AutoCloseable {
    private final EntityManagerFactory sales;
    private final EntityManagerFactory audit;

    public PersistenceFactories() {
        this.sales = Persistence.createEntityManagerFactory("salesPU");
        try {
            this.audit = Persistence.createEntityManagerFactory("auditPU");
        } catch (RuntimeException ex) {
            this.sales.close();
            throw ex;
        }
    }

    public EntityManager openSales() {
        return sales.createEntityManager();
    }

    public EntityManager openAudit() {
        return audit.createEntityManager();
    }

    @Override
    public void close() {
        try {
            audit.close();
        } finally {
            sales.close();
        }
    }
}
~~~

Đây là đoạn mã minh họa phần quản lý lifecycle; cần **import jakarta.persistence.EntityManager**, **EntityManagerFactory** và **Persistence**. Sử dụng một instance **PersistenceFactories** cho vòng đời ứng dụng, tạo EntityManager trong phạm vi thao tác và đóng sau khi hoàn tất. Khi đóng ứng dụng, lần lượt đóng các EMF để giải phóng tài nguyên.

Nếu ứng dụng có dependency injection container như Spring hoặc Jakarta EE, nên để container quản lý factory và transaction thay vì tự làm toàn bộ lifecycle.

## 6. Spring Boot với hai persistence unit

Spring Boot thường tự cấu hình một **DataSource**, một **EntityManagerFactory** và một **transaction manager** cho bài toán một database. Khi có nhiều nguồn dữ liệu, ứng dụng cần chỉ rõ:

1. **DataSource** nào thuộc sales và audit.
2. **EntityManagerFactory** nào chứa những entity nào.
3. **JpaTransactionManager** nào gắn với factory nào.
4. **Repository package** nào dùng factory và transaction manager nào.
5. Service chọn đúng transaction manager khi thực hiện thao tác.

Ví dụ sau sử dụng Spring Boot 3.x (Jakarta Persistence), Spring Data JPA và PostgreSQL. Cấu trúc package dự kiến:

~~~text
com.example
├── config/
│   ├── DataSourceConfig.java
│   ├── SalesJpaConfig.java
│   └── AuditJpaConfig.java
├── sales/
│   ├── SalesOrder.java
│   └── repository/SalesOrderRepository.java
└── audit/
    ├── AuditEvent.java
    └── repository/AuditEventRepository.java
~~~

### 6.1. Thuộc tính kết nối

**application.yml**:

~~~yaml
app:
  datasource:
    sales:
      url: jdbc:postgresql://localhost:5432/salesdb
      username: sales_app
      password: replace-with-secret
      driver-class-name: org.postgresql.Driver
    audit:
      url: jdbc:postgresql://localhost:5432/auditdb
      username: audit_app
      password: replace-with-secret
      driver-class-name: org.postgresql.Driver
~~~

Credential trong ví dụ chỉ là placeholder; dự án thật dùng secret manager hoặc biến môi trường. Cần có PostgreSQL JDBC driver, hai database tương ứng và bảng được tạo bằng migration riêng. Không đưa mật khẩu thật vào repository.

### 6.2. Tạo hai DataSource

**DataSourceConfig.java**:

~~~java
package com.example.config;

import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration
public class DataSourceConfig {
    @Bean("salesDataSourceProperties")
    @Primary
    @ConfigurationProperties("app.datasource.sales")
    public DataSourceProperties salesDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean("salesDataSource")
    @Primary
    public DataSource salesDataSource(
            @Qualifier("salesDataSourceProperties") DataSourceProperties props) {
        return props.initializeDataSourceBuilder().build();
    }

    @Bean("auditDataSourceProperties")
    @ConfigurationProperties("app.datasource.audit")
    public DataSourceProperties auditDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean("auditDataSource")
    public DataSource auditDataSource(
            @Qualifier("auditDataSourceProperties") DataSourceProperties props) {
        return props.initializeDataSourceBuilder().build();
    }
}
~~~

**@Primary** chọn một bean mặc định khi có nhiều ứng viên cùng loại; nó không kết nối các transaction với nhau. Dùng **DataSourceProperties** giúp Spring Boot xử lý thuộc tính **url** trước khi xây dựng pool (ví dụ Hikari). Với nhiều nguồn dữ liệu, có thể bổ sung cấu hình pool, health check và metrics riêng cho từng nguồn.

### 6.3. EntityManagerFactory và repository cho sales

**SalesJpaConfig.java**:

~~~java
package com.example.config;

import com.example.sales.SalesOrder;
import jakarta.persistence.EntityManagerFactory;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.orm.jpa.EntityManagerFactoryBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.sales.repository",
    entityManagerFactoryRef = "salesEntityManagerFactory",
    transactionManagerRef = "salesTransactionManager"
)
public class SalesJpaConfig {
    @Bean("salesEntityManagerFactory")
    @Primary
    public LocalContainerEntityManagerFactoryBean salesEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("salesDataSource") DataSource dataSource) {
        return builder
                .dataSource(dataSource)
                .packages(SalesOrder.class)
                .persistenceUnit("salesPU")
                .build();
    }

    @Bean("salesTransactionManager")
    @Primary
    public PlatformTransactionManager salesTransactionManager(
            @Qualifier("salesEntityManagerFactory") EntityManagerFactory emf) {
        return new JpaTransactionManager(emf);
    }
}
~~~

**.packages(SalesOrder.class)** chỉ package chứa SalesOrder để tìm các managed types; trong dự án thật cần bảo đảm tất cả entity, embeddable và converter cần thiết được phát hiện. **.persistenceUnit("salesPU")** đặt tên unit do Spring tạo. **EntityManagerFactoryBuilder** do cơ chế cấu hình JPA của Spring Boot cung cấp khi có đủ điều kiện; tùy phiên bản và mức độ tùy biến, ứng dụng có thể phải tự tạo builder/bean vendor adapter tương ứng.

### 6.4. EntityManagerFactory và repository cho audit

**AuditJpaConfig.java**:

~~~java
package com.example.config;

import com.example.audit.AuditEvent;
import jakarta.persistence.EntityManagerFactory;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.orm.jpa.EntityManagerFactoryBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.audit.repository",
    entityManagerFactoryRef = "auditEntityManagerFactory",
    transactionManagerRef = "auditTransactionManager"
)
public class AuditJpaConfig {
    @Bean("auditEntityManagerFactory")
    public LocalContainerEntityManagerFactoryBean auditEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("auditDataSource") DataSource dataSource) {
        return builder
                .dataSource(dataSource)
                .packages(AuditEvent.class)
                .persistenceUnit("auditPU")
                .build();
    }

    @Bean("auditTransactionManager")
    public PlatformTransactionManager auditTransactionManager(
            @Qualifier("auditEntityManagerFactory") EntityManagerFactory emf) {
        return new JpaTransactionManager(emf);
    }
}
~~~

Lúc này các repository nằm trong **com.example.sales.repository** sẽ sử dụng sales factory và sales transaction manager; repository trong **com.example.audit.repository** sử dụng audit factory và audit transaction manager. Tránh package quét chồng nhau hoặc để mặc định scan tự tạo một tập repository trùng lặp.

Khác với ví dụ Java SE, cấu hình Spring dùng **LocalContainerEntityManagerFactoryBean**, có thể tạo unit từ annotation/package scanning; không bắt buộc phải tạo thêm **persistence.xml**. Nếu dự án đồng thời có persistence.xml cũ, cần hiểu nguồn metadata/config nào được Spring chọn để tránh unit hay entity mapping ngoài ý muốn.

### 6.5. Repository và transaction tại service

~~~java
package com.example.sales.repository;

import com.example.sales.SalesOrder;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SalesOrderRepository
        extends JpaRepository<SalesOrder, Long> {
}
~~~

~~~java
package com.example.audit.repository;

import com.example.audit.AuditEvent;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AuditEventRepository
        extends JpaRepository<AuditEvent, Long> {
}
~~~

Phía service, chọn transaction manager có tên:

~~~java
@Service
public class SalesService {
    private final SalesOrderRepository orders;

    public SalesService(SalesOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional("salesTransactionManager")
    public Long createOrder(String ref, BigDecimal amount) {
        SalesOrder saved = orders.save(new SalesOrder(ref, amount));
        return saved.getId();
    }
}
~~~

~~~java
@Service
public class AuditService {
    private final AuditEventRepository audit;

    public AuditService(AuditEventRepository audit) {
        this.audit = audit;
    }

    @Transactional("auditTransactionManager")
    public void record(String eventType, String reference) {
        audit.save(new AuditEvent(eventType, reference, Instant.now()));
    }
}
~~~

Các đoạn service là **phần mã minh họa**: cần thêm package/import tương ứng như **@Service**, **@Transactional**, **BigDecimal** và **Instant**. Spring thường mở transaction khi lời gọi đi qua proxy được quản lý; tự gọi method trong cùng object (**self-invocation**) thường không kích hoạt advice transaction của Spring ở chế độ proxy thông dụng.

**@Transactional("salesTransactionManager")** chỉ gắn transaction với sales manager; thêm lời gọi **AuditService.record(...)** vào đó không tự biến audit và sales thành một transaction toàn cục. AuditService có thể mở/commit transaction audit riêng.

### 6.6. Inject EntityManager đúng unit

Khi không dùng Spring Data repository, có thể inject EntityManager theo **unitName**:

~~~java
@Repository
public class SalesQueryDao {
    @PersistenceContext(unitName = "salesPU")
    private EntityManager salesEntityManager;

    public List<SalesOrder> findAll() {
        return salesEntityManager.createQuery(
                "select o from SalesOrder o", SalesOrder.class)
                .getResultList();
    }
}
~~~

Trong môi trường Spring, tham chiếu được inject thường là proxy thích nghi với EntityManager gắn theo transaction/thread hiện tại. Không đóng proxy do container inject bằng **close()**. Các operation ghi cần transaction phù hợp; khai báo **unitName** trùng với tên unit được cấu hình.

### 6.7. Hibernate properties và schema migrations theo từng unit

Khi có hai EntityManagerFactory, các thuộc tính như **hibernate.default_schema**, **hibernate.jdbc.batch_size**, **hibernate.show_sql**, cache, DDL và cách xử lý tên bảng có thể cần áp dụng cho từng factory. Nếu chỉ cấu hình **spring.jpa.properties.***, hãy kiểm tra xem cấu hình đó được truyền vào cả hai factory tự xây dựng hay chưa. Với thiết lập phức tạp, thêm properties cụ thể vào builder:

~~~java
Map<String, Object> salesJpaProperties = Map.of(
        "hibernate.hbm2ddl.auto", "validate",
        "hibernate.jdbc.batch_size", 30
);

return builder
        .dataSource(dataSource)
        .packages(SalesOrder.class)
        .persistenceUnit("salesPU")
        .properties(salesJpaProperties)
        .build();
~~~

Đây là đoạn thay thế phần **return builder...** trong factory sales, cần import **java.util.Map**. Cấu hình tương ứng cho audit có thể khác.

Migration cũng phải chạy trên **đúng DataSource**: ví dụ **sales migrations** đi vào salesdb và **audit migrations** đi vào auditdb. Không giả định Spring Boot mặc định tự chạy mọi migration cho mọi DataSource nếu không có cấu hình. Với Flyway/Liquibase đa nguồn, tạo bean hoặc cấu hình migration riêng và chỉ rõ schema/location từng bộ script.

## 7. Chọn transaction đúng khi có nhiều unit

### 7.1. Resource-local transaction: đơn vị quản lý riêng biệt

Trong Java SE, mỗi EM tạo từ EMF resource-local có **getTransaction()**:

~~~java
EntityManager salesEm = salesEmf.createEntityManager();
EntityTransaction salesTx = salesEm.getTransaction();
try {
    salesTx.begin();
    salesEm.persist(order);
    salesTx.commit();
} catch (RuntimeException ex) {
    if (salesTx.isActive()) {
        salesTx.rollback();
    }
    throw ex;
} finally {
    salesEm.close();
}
~~~

**Không gọi getTransaction() trên JTA-managed EntityManager** để tự điều phối transaction; trong mô hình JTA, transaction được quản lý bởi JTA/container.

Nếu một business operation cần ghi cả sales và audit, thực hiện hai resource-local transaction nối tiếp không đáp ứng thuộc tính nguyên tử xuyên hai database. Cần xác định rõ yêu cầu nghiệp vụ:

| Yêu cầu | Hướng giải quyết |
|---|---|
| Chỉ cần bảo đảm từng database nhất quán độc lập | Transaction riêng cho mỗi unit; xử lý thất bại và retry có chủ đích |
| Cần đồng bộ hai database với khả năng eventual consistency | Transactional outbox + consumer idempotent hoặc quy trình saga |
| Cần atomic commit xuyên nhiều transactional resource và hạ tầng hỗ trợ | JTA/XA với transaction manager và tài nguyên XA thật sự được enlist |
| Có thể để toàn bộ thay đổi trong một database/transaction | Cân nhắc thiết kế một unit/DB transaction chung để đơn giản hóa |

### 7.2. JTA và distributed transaction (XA)

**JTA** cho phép transaction manager điều phối các tài nguyên tham gia cùng một transaction. Với hai database, tính nguyên tử xuyên tài nguyên thường đòi hỏi:

1. Một **JTA transaction manager** có khả năng điều phối transaction phân tán.
2. **XA-capable DataSource/driver**, được khai báo đúng và enlist vào transaction.
3. Hai persistence unit có **transaction-type=JTA**, dùng các DataSource được quản lý phù hợp.
4. Một transaction boundary chung; provider và container cùng tham gia đúng transaction ấy.

Không phải cứ có **@Transactional** hoặc đặt **transaction-type=JTA** là đủ để có commit nguyên tử trên hai database. Hệ thống XA có thêm chi phí, khả năng chờ khóa, log phục hồi và tình huống lỗi phân tán. Cần chọn theo yêu cầu nhất quán thực tế và hạ tầng đang có.

### 7.3. Outbox pattern khi dữ liệu cần đồng bộ giữa hai unit

Giả sử tạo đơn ở **salesdb** và cần ghi sự kiện sang **auditdb**. Một cách tránh mất sự kiện khi auditdb tạm thời không sẵn sàng:

~~~mermaid
flowchart LR
    A["Checkout request"] --> B["Sales transaction"]
    B --> C["INSERT sales_orders"]
    B --> D["INSERT outbox_events"]
    C --> E["COMMIT salesdb"]
    D --> E
    E --> F["Outbox publisher"]
    F --> G["Audit consumer"]
    G --> H["INSERT audit_events (auditdb)"]
~~~

Trong **một transaction salesdb**, lưu cả đơn hàng và một bản ghi outbox. Sau commit, một worker đọc outbox và gửi/áp dụng sự kiện vào auditdb. Nếu gửi thất bại, worker retry; phía audit cần xử lý **idempotency** để một sự kiện nhận nhiều lần không tạo bản ghi trùng.

Ví dụ cấu trúc outbox:

~~~sql
CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    aggregate_reference VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE
);
~~~

Nếu auditdb có cột **source_event_id UNIQUE**, consumer có thể bỏ qua sự kiện trùng bằng upsert/constraint. Outbox đảm bảo không có đơn được commit mà thiếu thông tin cần để phát sự kiện, nhưng **auditdb có thể cập nhật trễ**; UI và nghiệp vụ phải chấp nhận hoặc xử lý độ trễ đó.

### 7.4. Phân biệt read-only với transaction thực sự

Gắn **@Transactional(readOnly = true)** vào một phương thức thường là gợi ý tối ưu cho transaction/provider, không phải biện pháp kiểm soát quyền database. Muốn đảm bảo nguồn báo cáo không bị sửa, dùng credential chỉ đọc và quyền DB tương ứng. Hơn nữa, một query cần nhất quán nhiều lần đọc vẫn phải hiểu isolation của database.

## 8. Quản lý entity class trùng hoặc nằm ở cùng package

### 8.1. Tách package là biện pháp rõ ràng nhất

Để tránh quét nhầm, nên tổ chức:

~~~text
com.example.sales.entity.*
com.example.sales.repository.*
com.example.audit.entity.*
com.example.audit.repository.*
~~~

Mỗi EMF quét đúng entity package; mỗi **@EnableJpaRepositories** quét đúng repository package. Nếu cùng một package chứa đủ loại entity, có thể liệt kê class cụ thể trong **persistence.xml** hoặc cấu hình package-scanning cẩn thận, nhưng khả năng nhầm sẽ cao hơn.

### 8.2. Cùng một class trong hai persistence unit

Tình huống đồng bộ hai database có cùng schema có thể dùng một class **CustomerSnapshot** ở cả hai unit. Điều này hợp lệ nếu cả hai unit chứa mapping của class và schema phù hợp. Tuy nhiên:

- Một **CustomerSnapshot** managed bởi sales EM không tự nhiên managed trong audit EM.
- **entity.getId()** giống nhau không chứng minh dữ liệu ở hai database đã đồng bộ.
- **merge** vào unit kia có thể tạo tác động không mong muốn nếu ID, version hoặc dữ liệu ở đích khác nguồn.
- Persistence context cache cấp 1 và cache cấp 2 có phạm vi riêng theo factory; không trông chờ một unit tự refresh unit khác.
- Nên dùng DTO, snapshot hoặc sự kiện rõ ràng để truyền dữ liệu giữa hai miền, thay vì chuyển trực tiếp managed entity giữa factory.

### 8.3. Một unit không phải một tenant mặc định

Nếu có 10.000 tenant, việc dựng 10.000 EMF có thể tốn bộ nhớ, metadata và connection pool quá lớn. Nhiều provider hỗ trợ **multitenancy** theo discriminator, schema hoặc database resolver. Cần phân biệt:

- **Nhiều unit cố định:** số nguồn dữ liệu nhỏ, biết trước, mỗi unit có cấu hình rõ.
- **Multitenancy động:** số tenant lớn/thay đổi liên tục, chọn tenant theo request/context có cơ chế kiểm soát.

Trong hệ thống multitenant, việc kiểm soát tenant context, connection và cache cực kỳ quan trọng để tránh trả dữ liệu nhầm tenant. Quyết định thiết kế phải dựa trên yêu cầu cách ly, quy mô và khả năng vận hành.

## 9. Những lỗi điển hình và cách xác định nguyên nhân

| Dấu hiệu | Nguyên nhân thường gặp | Điều cần kiểm tra |
|---|---|---|
| **No Persistence provider for EntityManager named salesPU** | Sai tên unit, sai vị trí persistence.xml, thiếu provider | Classpath, META-INF/persistence.xml, đúng tên, dependency |
| **Not a managed type: SalesOrder** | Repository được nối với EMF không chứa SalesOrder | packages(), @EnableJpaRepositories, class list trong unit |
| **No qualifying bean of type EntityManagerFactory/TransactionManager** | Nhiều bean ứng viên, thiếu qualifier/primary | Tên bean, @Primary, @Qualifier, transactionManagerRef |
| **No bean named 'entityManagerFactory'** | Framework/bean kỳ vọng tên mặc định, trong khi cấu hình có tên khác | Nơi inject/tự động cấu hình; gán đúng bean hoặc chỉ rõ reference |
| **Table not found / relation does not exist** | Kết nối nhầm DB/schema, migration chưa chạy | URL, user, schema mặc định, DB thật sự, migration của từng nguồn |
| **TransactionRequiredException** | Thao tác ghi ngoài transaction thích hợp | @Transactional chọn manager nào, resource-local/JTA |
| **LazyInitializationException** (Hibernate) | Truy cập quan hệ lazy sau khi context đã đóng | Vị trí fetch, DTO/projection, phạm vi transaction |
| Ghi được sales nhưng không có audit | Hai transaction độc lập, audit thất bại hoặc chạy sai unit | Commit order, log/metrics, retry/outbox |
| Repository khai báo trùng / bean conflict | Quét trùng repository packages hoặc auto-config chồng nhau | basePackages, package tổ chức, bean names |
| Quá nhiều connection, khởi động chậm | Quá nhiều EMF/pool, cấu hình pool quá lớn | Số EMF, pool size mỗi DataSource, lifecycle, metrics |

Khi điều tra lỗi, đi từ cấu hình đến đường đi thực tế của một thao tác:

~~~text
Service method
  └── @Transactional(managerName)
        └── Repository hoặc @PersistenceContext(unitName)
              └── EntityManagerFactory(beanName / persistenceUnitName)
                    └── Entity package/mapping
                    └── DataSource(beanName)
                          └── JDBC URL / schema / DB user
~~~

Ghi log tên DataSource, URL không có credential, unit name và SQL theo từng nguồn giúp phát hiện cấu hình nhầm. Tránh bật SQL log chứa tham số nhạy cảm trong môi trường thật; chú ý log/trace mỗi pool và query được gắn nhãn nguồn dữ liệu.

## 10. Vận hành: tài nguyên, migration, quyền truy cập và hiệu năng

### 10.1. Chi phí khởi tạo và connection pools

Mỗi EntityManagerFactory thường giữ metadata ORM và có thể có cache, cấu trúc quản lý query và tham chiếu tới pool connection. Hai factory, mỗi factory có pool tối đa 20 connections, có thể tạo nhu cầu lên tới 40 connections chỉ từ một instance ứng dụng nếu cả hai pool đạt đỉnh. Với nhiều replica, số connection có thể tăng theo số replica.

Ví dụ ba instance ứng dụng, hai pool với cấu hình max 10 và max 8:

~~~text
Tối đa theo cấu hình pool
= 3 instance × (10 kết nối sales + 8 kết nối audit)
= 54 connection
~~~

Đây là **giới hạn lý thuyết theo tổng pool**, không phải con số kết nối luôn được mở. Cần tính cả công cụ migration, monitoring, batch job và các ứng dụng khác trước khi chọn pool size.

### 10.2. Migration và kiểm soát schema

Mỗi database phải có vòng đời migration rõ ràng:

- **salesdb:** bảng order, order_item, payment và các index/constraint của sales.
- **auditdb:** bảng audit_event, policy lưu trữ và index phục vụ tra cứu audit.

Không dùng **hibernate.hbm2ddl.auto=create/update** như chiến lược thay thế migration cho dữ liệu production. Khi triển khai nhiều unit, lỗi phổ biến là migration chỉ chạy cho **@Primary DataSource**, còn database phụ vẫn thiếu bảng.

### 10.3. Quyền truy cập và bảo mật

Nên dùng credential độc lập cho sales và audit, chỉ cấp quyền DB cần thiết. Một unit phục vụ báo cáo có thể dùng tài khoản SELECT-only; unit ghi audit có thể chỉ cần INSERT, SELECT hạn chế. Secret phải được quản lý theo môi trường và không đưa vào log.

Ranh giới unit ở ứng dụng không tự tạo hàng rào bảo mật database. Nếu hai unit dùng cùng user với quyền rộng trên cùng server, mã truy cập sai nguồn vẫn có thể thao tác dữ liệu không mong muốn. Phải kết hợp **role/privilege** ở database và kiểm soát ở ứng dụng.

### 10.4. Cache, fetch và chỉ số cần theo dõi

Persistence context thuộc một EntityManager; cache cấp 2 (nếu bật) thường thuộc phạm vi một EMF/provider configuration. Không trông chờ cập nhật ở auditPU làm sạch cache salesPU. Nếu hai unit dùng cùng bảng, cần xác định cache invalidation và consistency trước khi bật cache cấp 2.

Các chỉ số hữu ích cho từng unit:

- Số connection đang dùng/chờ, timeout pool, thời gian lấy connection.
- Thời gian query, số SQL statement và tỉ lệ N+1.
- Số transaction thành công/rollback, deadlock, serialization failure.
- Mức tăng của bảng, index, log và thời gian migration.
- Độ trễ của outbox/event nếu hai nguồn dùng eventual consistency.

## 11. Kiểm thử ứng dụng có nhiều persistence unit

Kiểm thử phải xác nhận không chỉ “lưu được dữ liệu”, mà còn **đúng database và đúng transaction boundary**.

### 11.1. Trường hợp kiểm thử quan trọng

| Kiểm thử | Kỳ vọng |
|---|---|
| Persist SalesOrder qua sales repository | Hàng chỉ xuất hiện trong salesdb |
| Persist AuditEvent qua audit repository | Hàng chỉ xuất hiện trong auditdb |
| Truy vấn repository khi hai DB có các ID trùng nhau | Không truy vấn nhầm bảng/nguồn |
| Cố persist entity audit qua sales EntityManager | Provider báo không thuộc managed types (nếu class không nằm trong salesPU) |
| Audit transaction rollback, sales đã commit | Sales vẫn giữ dữ liệu, phản ánh transaction độc lập |
| Migration chạy cho cả hai nguồn | Cả salesdb/auditdb có đúng bảng và constraint |
| Không kết nối được auditdb | Ứng dụng báo lỗi hoặc dùng chiến lược retry/outbox theo thiết kế |
| Gửi lặp cùng outbox event | Audit chỉ ghi một kết quả logic nhờ idempotency |

Với Spring, **@DataJpaTest** là slice test thường tối ưu cho trường hợp một nguồn dữ liệu và có thể thay DataSource bằng embedded database. Kiểm thử nhiều factory/transaction manager thường dễ kiểm soát hơn bằng **@SpringBootTest** hoặc cấu hình test riêng, tạo đúng hai database. Không mặc định kết luận rằng một bài test repository đơn lẻ đã kiểm tra hết wiring đa unit.

### 11.2. Ví dụ integration test xác nhận đúng nguồn

Giả sử cấu hình test khởi tạo hai database rỗng và hai repository:

~~~java
@SpringBootTest
class MultiplePersistenceUnitsIT {
    @Autowired
    SalesOrderRepository salesOrders;

    @Autowired
    AuditEventRepository auditEvents;

    @Test
    void eachRepositoryWritesToItsOwnDatabase() {
        SalesOrder order = salesOrders.save(
                new SalesOrder("TEST-ORDER-001", new BigDecimal("500.00")));

        AuditEvent event = auditEvents.save(
                new AuditEvent("ORDER_CREATED", "TEST-ORDER-001", Instant.now()));

        assertNotNull(order.getId());
        assertNotNull(event.getId());
        assertEquals(1L, salesOrders.count());
        assertEquals(1L, auditEvents.count());
    }
}
~~~

Ví dụ cần import JUnit, Spring Test, repository/entity và các kiểu Java tương ứng; mỗi repository dự kiến dùng transaction manager đã cấu hình. Để chứng minh **hai database vật lý** hoàn toàn cách biệt, có thể dùng hai Testcontainers PostgreSQL instance hoặc hai database/schema tách riêng, đồng thời query trực tiếp từng DataSource để xác nhận. Dùng ID trùng không phải bằng chứng truy cập nhầm, vì mỗi database có sequence riêng.

Nếu test muốn mô phỏng thất bại giữa hai transaction, phải tạo điều kiện lỗi có kiểm soát. Kết quả quan sát quan trọng là **partial commit** có thể xảy ra với local transaction, từ đó xác định cần outbox, retry hoặc distributed transaction.

## 12. Bài tập thực hành

### Bài 1: Xác định ranh giới unit

Ứng dụng có **inventorydb** và **billingdb**:

- **inventoryPU:** Product, StockMovement.
- **billingPU:** Invoice, Payment.
- Yêu cầu: khi mua hàng, giảm tồn kho và tạo hóa đơn.

Hãy trả lời:

1. EntityManager của billingPU có persist **StockMovement** được không nếu class đó không được mapping trong billingPU?
2. Nếu trừ kho commit thành công rồi tạo invoice thất bại, dữ liệu có tự rollback ở inventorydb không?
3. Có thể dùng **@ManyToOne** từ Invoice đến Product chỉ khi Product thuộc unit còn Invoice chỉ thuộc unit khác không?
4. Nếu nghiệp vụ chấp nhận eventual consistency, bạn thiết kế outbox ở đâu và consumer làm gì?

**Gợi ý:** hai unit có metadata và transaction riêng; một transaction local không rollback transaction đã commit ở unit khác. Có thể ghi invoice và outbox trong billingdb rồi consumer cập nhật tồn kho với idempotency, hoặc chọn trừ kho và outbox tại inventorydb tùy điểm xác nhận nghiệp vụ.

### Bài 2: Phát hiện cấu hình sai

~~~java
@EnableJpaRepositories(
    basePackages = "com.example.audit.repository",
    entityManagerFactoryRef = "salesEntityManagerFactory",
    transactionManagerRef = "salesTransactionManager"
)
class AuditConfig { }
~~~

Trong khi **AuditEvent** chỉ nằm trong auditPU, repository audit sẽ gặp vấn đề gì? Hãy sửa lại hai thuộc tính **entityManagerFactoryRef** và **transactionManagerRef** để trỏ tới **auditEntityManagerFactory** và **auditTransactionManager**.

### Bài 3: Transaction có thật sự nguyên tử?

~~~java
@Transactional("salesTransactionManager")
public void createOrderWithAudit() {
    salesRepository.save(new SalesOrder("A-1", amount));
    auditService.record("ORDER_CREATED", "A-1");
}
~~~

Giả sử **auditService.record** được gọi qua Spring proxy và dùng **@Transactional("auditTransactionManager")**:

- Transaction sales và audit có phải cùng một transaction không?
- Nếu audit commit xong nhưng sales rollback ở bước sau, audit record có tự biến mất không?
- Cần giải pháp nào nếu muốn tránh audit ghi sự kiện cho một order chưa commit?

**Gợi ý:** hai transaction manager local tách biệt; audit có thể commit trước rồi sales rollback, tạo orphan event. Outbox lưu trong cùng transaction sales giúp chỉ phát sự kiện sau khi order commit; consumer cần idempotent.

### Bài 4: Thiết kế kiểm thử nhiều unit

Viết integration test thực hiện: lưu **SalesOrder** vào salesdb, lưu **AuditEvent** vào auditdb, truy vấn trực tiếp cả hai DataSource và kiểm tra rằng mỗi bảng nằm đúng database. Thử cho auditdb ngừng nhận kết nối và quan sát ứng dụng xử lý theo thiết kế. Với H2 in-memory, dùng **hai JDBC URL khác nhau** và đừng vô tình tạo lại schema bằng **create** sau khi test đã ghi dữ liệu.

## 13. Nguyên tắc quyết định trước khi triển khai

Khi chuẩn bị tách persistence unit, trả lời tuần tự:

1. **Vì sao phải tách?** Khác database, schema, provider, policy bảo mật, ownership hay chỉ khác nhóm repository?
2. **Entity nào thuộc unit nào?** Các quan hệ object có cần nằm trong cùng unit để được mapping không?
3. **Ai tạo factory?** Java SE tự bootstrap hay container/Spring quản lý lifecycle?
4. **Ai quản lý transaction?** Resource-local, Spring JpaTransactionManager hay JTA? Có nhu cầu atomic commit xuyên tài nguyên không?
5. **Làm sao chọn đúng unit?** Tên persistence-unit, bean qualifier, repository package, transactionManagerRef và **@PersistenceContext(unitName)** phải thống nhất.
6. **Dữ liệu đi giữa hai unit thế nào?** Business identifier, DTO/event, outbox hoặc cơ chế giao dịch phân tán được triển khai rõ.
7. **Ai quản lý schema và vận hành?** Migration, connection pool, quyền DB, log, metrics, backup và phục hồi riêng theo nguồn.

Nắm vững các câu hỏi này giúp dùng nhiều persistence unit đúng với mục đích: **mỗi unit có cấu hình mapping, vòng đời EntityManager và đường truy cập database rõ ràng**, trong khi tính nhất quán liên nguồn luôn được giải quyết bằng một thiết kế transaction có chủ đích.
