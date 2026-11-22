# Quyền sở hữu giao dịch trong ứng dụng và trong môi trường quản lý JPA

Khi ứng dụng Java sử dụng JPA để ghi dữ liệu quan hệ, câu hỏi quan trọng không chỉ là **entity nào được lưu**, mà còn là **ai chịu trách nhiệm bắt đầu, kết thúc và hủy giao dịch**. Một phương thức gọi `entityManager.persist(order)` có thể được thực thi trong giao dịch do chính ứng dụng bắt đầu, trong giao dịch JTA do Jakarta EE container quản lý, hoặc trong giao dịch do Spring transaction manager mở và kết thúc.

Các mô hình này đều sử dụng JPA, nhưng **quyền sở hữu ranh giới giao dịch** (*transaction demarcation ownership*) rất khác nhau. Nếu không nhận diện đúng chủ sở hữu giao dịch, lập trình viên dễ gặp các lỗi:

- Gọi `EntityManager.getTransaction()` trên một EntityManager sử dụng JTA.
- Tự gọi `commit()` ngay trong service đang được container quản lý.
- Cho rằng `persist()` hoặc `flush()` đồng nghĩa giao dịch đã commit.
- Gọi một phương thức service có `@Transactional` nhưng không thực sự đi qua transaction proxy.
- Trả dữ liệu thành công cho client khi giao dịch bên ngoài còn có thể rollback.
- Quên rollback và đóng EntityManager trong ứng dụng tự quản lý.
- Xóa hoặc đóng tài nguyên persistence context mà framework còn đang sử dụng.

Mục tiêu bài học là phân biệt rõ **giao dịch do ứng dụng quản lý**, **giao dịch do môi trường quản lý**, và **vai trò tham gia giao dịch của EntityManager/persistence context**; sau đó thực hành với JPA resource-local, Jakarta Transactions (JTA), Jakarta Enterprise Beans và Spring Data JPA.

## 1. “Quyền sở hữu giao dịch” thực chất là quyền gì?

Một giao dịch database thường có các bước:

~~~text
BẮT ĐẦU GIAO DỊCH
        |
        v
  Đọc/ghi dữ liệu
        |
        +-- persist(entity)
        +-- thay đổi entity managed
        +-- remove(entity)
        +-- chạy JPQL/Criteria/SQL
        |
        v
    Đồng bộ (flush)
        |
        v
   Quyết định kết thúc
       /          \
      /            \
   COMMIT        ROLLBACK
      |              |
      v              v
 Dữ liệu được    Các thay đổi
   xác nhận      bị hủy theo DB
~~~

**Chủ sở hữu ranh giới giao dịch** là thành phần quyết định khi nào giao dịch bắt đầu và khi nào nó được xác nhận hoặc rollback. Thành phần này có thể là:

1. **Code ứng dụng** trực tiếp dùng `EntityTransaction` của JPA resource-local.
2. **Code ứng dụng** dùng `UserTransaction` trong môi trường cho phép bean-managed JTA transaction.
3. **Jakarta EE container** quản lý giao dịch quanh lời gọi EJB hoặc phương thức có cơ chế giao dịch do container cung cấp.
4. **Spring transaction manager** thực hiện giao dịch quanh phương thức `@Transactional` thông qua hạ tầng AOP/proxy hoặc cơ chế được cấu hình.

Điểm cần chú ý: **Đối tượng gọi `persist()` không nhất thiết là chủ sở hữu giao dịch**. Repository có thể thực hiện thao tác ghi, còn transaction được mở ở một service nghiệp vụ nằm bên ngoài repository.

### 1.1. Ba lớp trách nhiệm khác nhau

| Lớp | Trách nhiệm | Ví dụ |
|---|---|---|
| Ranh giới giao dịch | Begin, commit, rollback; đánh dấu rollback-only | `EntityTransaction`, JTA transaction manager, Spring `PlatformTransactionManager` |
| Persistence context | Quản lý entity, dirty checking, identity map, flush | `EntityManager` |
| Kết nối và tài nguyên DB | Truyền SQL và thực thi commit/rollback theo transaction | JDBC connection, database, JTA enlisted resource |

JPA kết nối ba lớp này, nhưng chúng **không phải một đối tượng duy nhất**.

Ví dụ `EntityManager.persist()` thường yêu cầu thêm entity vào context; transaction manager mới quyết định liệu SQL được xác nhận ở cuối unit of work hay bị rollback.

### 1.2. “Application-managed EntityManager” không đồng nghĩa “resource-local transaction”

Hai cách phân loại thường bị trộn lẫn:

- **Ai tạo/quản lý vòng đời EntityManager?** Ứng dụng gọi `EntityManagerFactory.createEntityManager()` hay container/framework cung cấp một managed EntityManager?
- **Ai điều phối transaction và cơ chế transaction là gì?** JPA `RESOURCE_LOCAL` dùng `EntityTransaction`, hay `JTA` dùng transaction coordinator của môi trường?

Một EntityManager do ứng dụng tạo **có thể** được cấu hình với JTA trong môi trường hỗ trợ. Ngược lại, một ứng dụng Spring có thể dùng resource-local JPA transaction được **Spring quản lý ở tầng service**. Vì vậy, không nên coi “application-managed vs container-managed EntityManager” và “RESOURCE_LOCAL vs JTA” là cùng một cặp khái niệm.

## 2. Bản đồ các mô hình quản lý giao dịch

| Bối cảnh | Ai mở/kết thúc transaction? | API chính | Ai tạo/đóng EntityManager? |
|---|---|---|---|
| Java SE, JPA `RESOURCE_LOCAL` | Code ứng dụng | `em.getTransaction().begin()/commit()/rollback()` | Thường ứng dụng dùng EMF và `em.close()` |
| Jakarta EE, bean-managed JTA | Code bean trong giới hạn container | `UserTransaction.begin()/commit()/rollback()` | Phụ thuộc EM ứng dụng tạo hay container inject |
| Jakarta EE, container-managed EJB | Container theo transaction attribute | `@TransactionAttribute`; không tự commit | Container quản lý EntityManager injected |
| Jakarta Transactions `@Transactional` | Interceptor của môi trường JTA | `jakarta.transaction.Transactional` | Phụ thuộc mô hình container/framework |
| Spring `@Transactional` + JPA | Spring transaction manager | `org.springframework.transaction.annotation.Transactional` | Thường Spring cấp proxy/EntityManager liên kết transaction |
| Spring Data repository không có outer service transaction | Repository/framework có thể cung cấp transaction quanh từng method | Spring Data JPA/Spring TX | Framework quản lý |
| Spring Data repository bên trong outer transaction | Outer service transaction | Spring `@Transactional` | Repository tham gia giao dịch đang có |

Trong mọi mô hình, JPA provider vẫn chịu trách nhiệm mapping entity thành thao tác persistence. Sự khác biệt là **ai có quyền kết thúc transaction** và ở đâu ranh giới được đặt.

## 3. Ví dụ nghiệp vụ dùng xuyên suốt bài học

Giả sử hệ thống đặt hàng có entity:

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    NEW,
    CONFIRMED,
    CANCELLED
}
~~~

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.math.BigDecimal;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Column(name = "customer_code", nullable = false, length = 40)
    private String customerCode;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status = OrderStatus.NEW;

    @Column(name = "total", nullable = false, precision = 14, scale = 2)
    private BigDecimal total;

    protected PurchaseOrder() {
        // Constructor cho JPA.
    }

    public PurchaseOrder(String customerCode, BigDecimal total) {
        if (customerCode == null || customerCode.isBlank()) {
            throw new IllegalArgumentException("Customer code is required");
        }
        if (total == null || total.signum() < 0) {
            throw new IllegalArgumentException("Invalid total");
        }
        this.customerCode = customerCode;
        this.total = total;
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void confirm() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException(
                "Only NEW orders can be confirmed"
            );
        }
        status = OrderStatus.CONFIRMED;
    }
}
~~~

Schema SQL tối thiểu:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    customer_code VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    total DECIMAL(14, 2) NOT NULL
);
~~~

SQL minh họa dùng cú pháp PostgreSQL. Khi dùng database khác, cột identity và DDL có thể khác. Các ví dụ giao dịch phía dưới tập trung vào **ai begin/commit/rollback**, không phải thiết kế toàn bộ quy trình đơn hàng như thanh toán hoặc tồn kho.

## 4. Ứng dụng tự quản lý giao dịch với `RESOURCE_LOCAL`

Đây là mô hình dễ nhìn thấy nhất vì code ứng dụng gọi trực tiếp API giao dịch của JPA.

### 4.1. Cấu hình persistence unit

Với ứng dụng JPA Java SE dùng local transaction, có thể cấu hình `persistence.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">
    <persistence-unit
        name="shopLocalPU"
        transaction-type="RESOURCE_LOCAL">

        <class>com.example.shop.domain.PurchaseOrder</class>

        <!-- JDBC connection properties/provider configuration
             được cấu hình theo môi trường ứng dụng. -->
    </persistence-unit>
</persistence>
~~~

Thông thường code khởi tạo factory một lần cho ứng dụng:

~~~java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("shopLocalPU");
~~~

Trong ứng dụng thực tế, `EntityManagerFactory` là thành phần có chi phí tạo tương đối lớn; không nên tạo mới cho từng request. Khi ứng dụng dừng, factory được đóng theo vòng đời ứng dụng.

### 4.2. Code tự begin, commit và rollback

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

import java.math.BigDecimal;

public final class LocalOrderService {

    private final EntityManagerFactory emf;

    public LocalOrderService(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public Long createOrder(
            String customerCode, BigDecimal total) {

        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            PurchaseOrder order =
                new PurchaseOrder(customerCode, total);

            em.persist(order);

            // Đọc id ở đây không đồng nghĩa đã commit.
            // SQL có thể đã chạy để lấy khóa IDENTITY.
            Long generatedId = order.getId();

            tx.commit(); // App sở hữu quyết định COMMIT.
            return generatedId;

        } catch (RuntimeException original) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackError) {
                    original.addSuppressed(rollbackError);
                }
            }
            throw original;
        } finally {
            em.close(); // App sở hữu EntityManager này.
        }
    }
}
~~~

Ở đây **code ứng dụng sở hữu cả ranh giới transaction và vòng đời EntityManager**:

1. Tạo `EntityManager` từ `EntityManagerFactory`.
2. Lấy `EntityTransaction` bằng `getTransaction()`.
3. Gọi `begin()`.
4. Thực hiện công việc persistence.
5. Gọi `commit()` khi thành công.
6. Nếu có lỗi trong transaction còn active, gọi `rollback()`.
7. Đóng `EntityManager` trong `finally`.

Nếu code bỏ `rollback()` hoặc `close()`, tài nguyên có thể bị giữ lâu và transaction có thể không được kết thúc như mong muốn.

### 4.3. Transaction bao trùm nhiều repository

Một lỗi thiết kế trong ứng dụng tự quản lý:

~~~java
orderRepository.insertOrder(order);    // Tự begin/commit.
inventoryRepository.reserveStock(...); // Tự begin/commit.
~~~

Nếu thao tác đặt hàng cần đồng bộ với cập nhật tồn kho trong **một transaction**, hai repository tự commit riêng có thể tạo ra dữ liệu không nhất quán.

Hướng thiết kế tốt hơn:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    orderRepository.insertOrder(em, order);
    inventoryRepository.reserveStock(em, productId, quantity);

    tx.commit(); // Một ranh giới cho toàn bộ nghiệp vụ.

} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Hai repository ở đây nhận cùng `EntityManager` và **không tự begin/commit**. Service nghiệp vụ sở hữu transaction; repository chỉ thực hiện persistence work.

> **Ranh giới transaction nên bao trùm một đơn vị nghiệp vụ cần nhất quán, không nhất thiết trùng với một phương thức CRUD.**

### 4.4. Điểm mạnh và hạn chế của resource-local

**Điểm mạnh:** dễ hiểu, thuận tiện với ứng dụng Java SE độc lập, ít phụ thuộc transaction container, quyền điều khiển begin/commit/rollback rõ ràng.

**Hạn chế:** code phải tự duy trì vòng đời transaction và EntityManager; khó điều phối nhiều resource khác nhau trong một distributed transaction; dễ có nhiều commit rời rạc nếu không thống nhất nơi sở hữu transaction; khó tái sử dụng logic khi service lồng nhau nếu mỗi tầng tự khởi tạo EntityManager.

Resource-local **không mặc định đồng nghĩa một cách “không an toàn”**. Nó là lựa chọn hợp lệ nếu ranh giới transaction được thiết kế cẩn thận và dữ liệu nằm trong phạm vi resource được hỗ trợ.

## 5. `EntityTransaction` thuộc môi trường resource-local

API JPA:

~~~java
EntityTransaction tx = entityManager.getTransaction();

tx.begin();
tx.commit();
tx.rollback();

boolean active = tx.isActive();
tx.setRollbackOnly();
boolean rollbackOnly = tx.getRollbackOnly();
~~~

Trong trường hợp resource-local, `EntityTransaction` là giao diện để ứng dụng tự quản lý transaction. Không nhất thiết dùng đủ mọi method trong mọi use case; code thường cần begin/commit/rollback và kiểm tra active khi xử lý lỗi.

### 5.1. Vì sao không dùng `getTransaction()` cho JTA EntityManager?

Với EntityManager sử dụng JTA transaction, API `EntityManager.getTransaction()` **không phải cách quản lý transaction**. Theo hợp đồng JPA, gọi `getTransaction()` trên JTA EntityManager không hợp lệ và có thể dẫn đến `IllegalStateException`.

Đoạn mã cần tránh trong Jakarta EE JTA:

~~~java
@PersistenceContext
private EntityManager em;

public void createOrder(...) {
    EntityTransaction tx = em.getTransaction(); // Sai mô hình JTA.
    tx.begin();
    // ...
}
~~~

Thay vào đó, dùng transaction của container hoặc API JTA phù hợp với kiểu bean và bối cảnh quản lý.

### 5.2. Không gọi begin trùng

Nếu code tự quản lý resource-local đã có transaction active, việc gọi `begin()` thêm một lần trên cùng `EntityTransaction` không phải cơ chế nested transaction. JPA resource-local không biến nested `begin()` thành savepoint một cách tự động.

Nếu cần chia công việc nhưng vẫn một transaction, cho các method con dùng cùng EntityManager/transaction hiện tại và để owner bên ngoài duy nhất quyết định commit/rollback.

### 5.3. Rollback-only khác rollback tức thời

`tx.setRollbackOnly()` đánh dấu transaction phải rollback, không thực hiện rollback ngay lập tức. Khi commit được yêu cầu, transaction không được kết thúc như một commit thành công.

Tính năng này hữu ích nếu tầng con phát hiện điều kiện không thể tiếp tục nghiệp vụ nhưng không sở hữu ranh giới cuối. Tuy nhiên, API rollback-only cần sử dụng theo đúng mô hình transaction đang áp dụng: `EntityTransaction` cho resource-local; transaction coordinator/container API cho JTA.

## 6. Jakarta EE quản lý giao dịch bằng JTA

Trong Jakarta EE, các thành phần doanh nghiệp có thể chạy trong transaction được container quản lý. Thay vì service tự tạo EntityManager và gọi `begin()/commit()`, môi trường quản lý ranh giới theo annotation và quy tắc transaction.

### 6.1. Persistence unit JTA

Ví dụ `persistence.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">
    <persistence-unit
        name="shopJtaPU"
        transaction-type="JTA">

        <jta-data-source>java:comp/env/jdbc/ShopDS</jta-data-source>

        <class>com.example.shop.domain.PurchaseOrder</class>
    </persistence-unit>
</persistence>
~~~

Tên datasource, binding JNDI và cách triển khai resource do môi trường Jakarta EE cung cấp. Đây là cấu hình định hướng; dự án thực cần cấu hình phù hợp application server, database và provider.

Trong JTA, **transaction manager điều phối việc enlist resource**. `EntityManager` tham gia transaction để JPA đồng bộ persistence work, nhưng không tự sở hữu commit.

### 6.2. Container-managed transaction trong Jakarta Enterprise Beans

Một stateless session bean:

~~~java
package com.example.shop.service;

import jakarta.ejb.Stateless;
import jakarta.ejb.TransactionAttribute;
import jakarta.ejb.TransactionAttributeType;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import java.math.BigDecimal;

@Stateless
public class OrderService {

    @PersistenceContext(unitName = "shopJtaPU")
    private EntityManager em;

    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public Long createOrder(
            String customerCode, BigDecimal total) {

        PurchaseOrder order =
            new PurchaseOrder(customerCode, total);

        em.persist(order);

        // Không gọi em.getTransaction().commit().
        // Container xử lý ranh giới transaction.
        return order.getId();
    }
}
~~~

Với `TransactionAttributeType.REQUIRED`:

- Nếu lời gọi chưa có transaction, container sẽ tạo transaction cho lời gọi nghiệp vụ.
- Nếu đã có transaction, method thường **tham gia transaction hiện có**.
- Khi container là owner của transaction mới và method hoàn tất bình thường, container xử lý commit.
- Nếu method đang tham gia transaction bên ngoài, commit thuộc nơi mở transaction ngoài.

**Trong thân phương thức, `return order.getId()` chưa phải commit.** Nếu method tự mở transaction do container quản lý, caller nhận kết quả sau khi hạ tầng hoàn tất xử lý transaction. Nếu method chỉ tham gia transaction có sẵn, caller bên trong transaction ngoài có thể nhận ID trước khi transaction tổng thể commit.

### 6.3. Container-managed EntityManager

`@PersistenceContext` thường inject một **container-managed EntityManager** được gắn với persistence context theo cơ chế của môi trường.

Trong bối cảnh này:

~~~java
@PersistenceContext(unitName = "shopJtaPU")
private EntityManager em;
~~~

không có nghĩa bean tự sở hữu tài nguyên underlying và được phép đóng bất cứ lúc nào.

Các việc **không nên làm** với container-managed EntityManager:

~~~java
em.close();             // Container quản lý lifecycle, không tự close.
em.getTransaction();    // Không quản lý JTA theo kiểu resource-local.
~~~

Phương thức trong bean tập trung vào nghiệp vụ/persistence operations. Container chịu trách nhiệm khởi tạo/đóng tài nguyên theo lifecycle cấu hình và đồng bộ context với transaction.

### 6.4. Container quản lý không có nghĩa mọi lời gọi luôn có transaction

Phải xem transaction attribute đang có hiệu lực. Method với `NOT_SUPPORTED` sẽ thực thi ngoài JTA transaction; `SUPPORTS` có thể có hoặc không có transaction theo caller; `MANDATORY` yêu cầu transaction đã tồn tại.

Nếu code cố thực hiện `flush()` hoặc thao tác ghi cần transaction khi không có transaction hợp lệ, có thể phát sinh `TransactionRequiredException` hay exception phù hợp.

Không suy luận “được inject EntityManager là luôn ghi được bất cứ lúc nào”.

## 7. Các transaction attribute của EJB

Trong Jakarta Enterprise Beans container-managed transaction, `@TransactionAttribute` cho phép quy định cách method tương tác với transaction của caller.

| Giá trị | Caller đã có transaction | Caller chưa có transaction |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện có | Container tạo transaction mới |
| `REQUIRES_NEW` | Tạm treo transaction caller và tạo transaction mới | Container tạo transaction mới |
| `MANDATORY` | Tham gia transaction hiện có | Bị từ chối theo quy tắc container |
| `SUPPORTS` | Tham gia transaction hiện có | Chạy không có transaction |
| `NOT_SUPPORTED` | Tạm treo transaction caller, chạy không có transaction | Chạy không có transaction |
| `NEVER` | Bị từ chối | Chạy không có transaction |

Trong CMT EJB, mặc định thường là `REQUIRED` nếu không cấu hình khác theo quy tắc của EJB.

Ví dụ:

~~~java
@TransactionAttribute(TransactionAttributeType.MANDATORY)
public void updateStock(Long productId, int quantity) {
    // Yêu cầu caller đã có transaction.
}
~~~

Method này chủ động yêu cầu được gọi bên trong transaction đã tồn tại, phù hợp khi cập nhật tồn kho phải nằm trong cùng transaction với đặt hàng.

Một ví dụ khác:

~~~java
@TransactionAttribute(TransactionAttributeType.REQUIRES_NEW)
public void recordIndependentAudit(String message) {
    // Giao dịch độc lập với transaction bị tạm treo của caller.
}
~~~

Cần dùng `REQUIRES_NEW` cẩn thận: nếu audit commit thành công, sau đó transaction chính rollback, audit vẫn có thể tồn tại. Điều này có thể là đúng cho “ghi nhận attempt” nhưng không đúng cho “ghi nhận đơn hàng đã commit”.

### 7.1. Ranh giới ownership trong lời gọi lồng nhau

~~~text
Controller / REST endpoint
          |
          v
OrderFacade.createCheckout()     Transaction T1 được mở
          |
          +--> OrderRepository.persist()       Tham gia T1
          |
          +--> InventoryService.reserve()      Tham gia T1
          |
          +--> AuditService.recordAttempt()    Có thể REQUIRES_NEW -> T2
          |
          v
OrderFacade kết thúc
          |
          v
Container commit T1 hoặc rollback T1
~~~

Điều quyết định không phải method nào gọi `persist`, mà là method nào mở transaction và propagation/attribute nào có hiệu lực.

### 7.2. Giao dịch mới không đồng nghĩa an toàn hơn

`REQUIRES_NEW` tạo boundary độc lập, có thể phải dùng thêm connection và tạo khả năng commit một phần khi transaction ngoài thất bại. Nó không nên được áp dụng chỉ để “chắc chắn có commit” khi nghiệp vụ đòi tính nguyên tử trên tất cả bước.

Nếu đơn hàng và giữ hàng phải thành công hoặc thất bại cùng nhau trong một database transaction, thường nên để chúng tham gia cùng transaction.

## 8. Đánh dấu rollback trong container-managed transaction

Trong CMT, code không tự gọi `EntityTransaction.rollback()`. Khi phát hiện lỗi nghiệp vụ, có thể:

- Ném exception để hạ tầng áp dụng chính sách rollback phù hợp.
- Dùng API container chuyên biệt để đánh dấu transaction rollback-only.
- Với Jakarta Transactions `@Transactional`, cấu hình các loại exception gây rollback khi cần.

Ví dụ EJB:

~~~java
import jakarta.annotation.Resource;
import jakarta.ejb.SessionContext;
import jakarta.ejb.Stateless;
import jakarta.ejb.TransactionAttribute;
import jakarta.ejb.TransactionAttributeType;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

@Stateless
public class ReservationService {

    @Resource
    private SessionContext sessionContext;

    @PersistenceContext
    private EntityManager em;

    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public void reserveStock(Long productId, int quantity) {
        if (quantity <= 0) {
            sessionContext.setRollbackOnly();
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }

        // Thao tác ghi vào DB trong transaction hiện tại.
    }
}
~~~

`SessionContext.setRollbackOnly()` dùng trong bối cảnh container-managed transaction phù hợp. Nó đánh dấu giao dịch không được phép commit, **không thực thi rollback ngay tại dòng đó**.

### 8.1. Checked exception không phải lúc nào gây rollback

Quy tắc rollback theo exception khác nhau giữa EJB CMT, Jakarta Transactions interceptors và Spring.

Ví dụ EJB có `@ApplicationException` và thuộc tính `rollback` để điều chỉnh chính sách đối với application exception. Trong Spring, `@Transactional` mặc định rollback đối với unchecked exception và `Error`, còn checked exception cần cấu hình nếu muốn rollback.

**Không suy luận từ câu “method ném exception” rằng mọi framework chắc chắn rollback.** Phải xem loại exception, annotation, cách catch/rethrow và trạng thái rollback-only.

### 8.2. Bắt lỗi nhưng không đánh dấu rollback

Đoạn logic:

~~~java
try {
    inventoryService.reserveStock(...);
} catch (OutOfStockException ex) {
    // Chỉ log, không throw, không setRollbackOnly.
}
~~~

có thể để transaction tiếp tục và commit những thay đổi trước đó nếu framework không tự đánh dấu rollback-only. Nếu thiếu hàng khiến **toàn bộ checkout phải thất bại**, service owner cần thể hiện điều này bằng chính sách rollback thích hợp.

Ngược lại, nếu thiếu hàng là một nhánh nghiệp vụ đã được xử lý và không có thay đổi sai cần rollback, có thể cho transaction tiếp tục; lựa chọn phải được quyết định từ business invariant.

## 9. JTA do code điều khiển: Bean-managed transaction

Có một mô hình thứ ba nằm giữa “resource-local do code quản lý” và “CMT do container quản lý”: **Bean-managed transaction (BMT)**.

Trong Jakarta Enterprise Beans, bean có thể tự điều khiển JTA transaction bằng `UserTransaction` khi được cấu hình thích hợp.

### 9.1. Ví dụ BMT với `UserTransaction`

~~~java
package com.example.shop.service;

import jakarta.annotation.Resource;
import jakarta.ejb.Stateless;
import jakarta.ejb.TransactionManagement;
import jakarta.ejb.TransactionManagementType;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.transaction.UserTransaction;

import java.math.BigDecimal;

@Stateless
@TransactionManagement(TransactionManagementType.BEAN)
public class BeanManagedOrderService {

    @Resource
    private UserTransaction userTransaction;

    @PersistenceContext(unitName = "shopJtaPU")
    private EntityManager em;

    public Long createOrder(
            String customerCode, BigDecimal total) throws Exception {

        boolean began = false;

        try {
            userTransaction.begin();
            began = true;

            // Với JTA persistence context, tham gia transaction
            // đúng cách; joinTransaction có thể cần trong
            // trường hợp context không tự tham gia.
            em.joinTransaction();

            PurchaseOrder order =
                new PurchaseOrder(customerCode, total);

            em.persist(order);
            em.flush();

            Long id = order.getId();

            userTransaction.commit();
            began = false;

            return id;

        } catch (Exception original) {
            if (began) {
                try {
                    userTransaction.rollback();
                } catch (Exception rollbackError) {
                    original.addSuppressed(rollbackError);
                }
            }
            throw original;
        }
    }
}
~~~

Đây là ví dụ mô hình BMT. Chính sách transaction thực tế có thể đòi xử lý thêm các trạng thái JTA khi commit gặp exception, chẳng hạn transaction đã hoàn tất hay trạng thái chưa xác định. Khi kết nối mất đúng lúc commit, không được khẳng định rollback chắc chắn thành công chỉ từ việc phương thức ném exception.

Điểm then chốt:

- Bean kiểm soát `begin` và `commit` bằng JTA `UserTransaction`.
- Resource tham gia là JTA, **không dùng `em.getTransaction()`**.
- EntityManager được inject vẫn có thể do container quản lý vòng đời.
- BMT khác CMT: container không tự kết thúc transaction theo các transaction attribute của CMT cho method này.
- BMT stateless bean phải tuân thủ các giới hạn transaction lifecycle của môi trường, không để transaction tùy tiện “treo” xuyên qua nhiều lời gọi.

### 9.2. Không nhầm BMT với việc gọi `getTransaction()`

RESOURCE_LOCAL:

~~~java
EntityTransaction tx = em.getTransaction();
tx.begin();
// ...
tx.commit();
~~~

JTA bean-managed:

~~~java
@Resource
UserTransaction utx;

utx.begin();
// EntityManager JTA tham gia transaction.
utx.commit();
~~~

JTA container-managed:

~~~java
@TransactionAttribute(TransactionAttributeType.REQUIRED)
public void work() {
    // Không gọi begin/commit.
}
~~~

Ba đoạn đều có thể dẫn tới một transaction database, nhưng **API và người chịu trách nhiệm kết thúc transaction khác nhau**.

### 9.3. Khi nào cân nhắc BMT?

BMT có thể phù hợp khi logic cần nhiều ranh giới JTA đặc biệt trong một lời gọi hoặc mô hình container-managed chuẩn không biểu diễn được yêu cầu, và môi trường cho phép.

Tuy vậy, nó tăng trách nhiệm xử lý trạng thái transaction, lỗi và kết thúc tài nguyên. Với phần lớn service CRUD/nghiệp vụ thông thường trong Jakarta EE, CMT thường dễ duy trì hơn.

## 10. Jakarta `@Transactional` và Spring `@Transactional` không phải cùng annotation

Cả Jakarta Transactions và Spring đều có annotation tên `Transactional`:

~~~java
// Jakarta Transactions:
import jakarta.transaction.Transactional;
~~~

~~~java
// Spring Framework:
import org.springframework.transaction.annotation.Transactional;
~~~

Chúng có nguồn gốc và cấu hình khác nhau.

### 10.1. Jakarta Transactions `@Transactional`

Ví dụ trong môi trường Jakarta EE phù hợp:

~~~java
import jakarta.transaction.Transactional;

@Transactional(Transactional.TxType.REQUIRED)
public void createOrder(...) {
    // Method chạy theo giao dịch JTA do interceptor quản lý.
}
~~~

`jakarta.transaction.Transactional` có các giá trị `TxType` như `REQUIRED`, `REQUIRES_NEW`, `MANDATORY`, `SUPPORTS`, `NOT_SUPPORTED` và `NEVER`; đồng thời có cấu hình rollback theo exception như `rollbackOn` và `dontRollbackOn`.

### 10.2. Spring `@Transactional`

Ví dụ:

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void createOrder(...) {
    // Spring transaction manager xử lý boundary.
}
~~~

Spring annotation hỗ trợ cấu hình như propagation, isolation, readOnly, timeout, rollbackFor và noRollbackFor. Tập lựa chọn phụ thuộc transaction manager và cơ chế tài nguyên.

### 10.3. Vì sao phải phân biệt?

Không nên chỉ nhìn chữ `@Transactional` rồi giả định:

- JTA container đang quản lý.
- Spring đang quản lý.
- Một transaction XA/distributed đã được thiết lập.
- Mọi exception đều dẫn đến rollback.
- Cách transaction propagation và proxy/interceptor giống nhau.

Cần xem **import**, môi trường chạy, cấu hình transaction manager và cách gọi method.

## 11. Spring quản lý ranh giới transaction trên ứng dụng JPA

Trong ứng dụng Spring Boot/Spring Data JPA, một cách phổ biến là đặt `@Transactional` ở service nghiệp vụ.

~~~java
package com.example.shop.service;

import com.example.shop.domain.PurchaseOrder;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;

@Service
public class OrderApplicationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long createOrder(
            String customerCode, BigDecimal total) {

        PurchaseOrder order =
            new PurchaseOrder(customerCode, total);

        em.persist(order);

        // Không tự em.getTransaction().begin()/commit().
        // Spring xử lý transaction theo manager cấu hình.
        return order.getId();
    }
}
~~~

Spring có thể sử dụng `JpaTransactionManager` cho giao dịch một EntityManagerFactory cùng resource-local JPA, hoặc `JtaTransactionManager` khi ứng dụng tích hợp JTA. Vì vậy, đây là ví dụ quan trọng cho thấy:

> **Transaction do framework quản lý không nhất thiết là JTA.** Spring có thể cung cấp boundary declarative ngay cả khi persistence unit dùng `RESOURCE_LOCAL`.

### 11.1. Ai là owner trong ví dụ Spring?

Khi request gọi phương thức qua Spring transaction proxy và không có transaction trước đó:

~~~text
Controller
    |
    v
Spring transaction interceptor
    |
    +-- Bắt đầu transaction
    |
    v
OrderApplicationService.createOrder()
    |
    +-- EntityManager.persist()
    |
    +-- Return ID từ method body
    |
    v
Spring transaction interceptor
    |
    +-- Flush/commit theo transaction manager
    |
    v
Controller nhận kết quả thành công
~~~

Method body không gọi commit. Transaction manager commit **trên đường trả về** nếu nó là owner của transaction vừa mở.

Nếu commit thất bại, lời gọi có thể ném exception ra controller thay vì trả ID thành công, dù method body đã thực thi `return`.

### 11.2. Spring service tham gia transaction ngoài

~~~java
@Service
public class CheckoutService {

    private final OrderApplicationService orderService;
    private final InventoryService inventoryService;

    public CheckoutService(
            OrderApplicationService orderService,
            InventoryService inventoryService) {

        this.orderService = orderService;
        this.inventoryService = inventoryService;
    }

    @Transactional
    public void checkout(
            String customerCode, BigDecimal total) {

        Long orderId =
            orderService.createOrder(customerCode, total);

        inventoryService.reserveForOrder(orderId);

        // Giao dịch có thể chỉ commit khi checkout() kết thúc.
    }
}
~~~

Với propagation `REQUIRED` mặc định, `createOrder()` thông thường tham gia transaction của `checkout()`. ID trả từ `createOrder()` **không chứng minh** giao dịch tổng thể đã commit; nếu `reserveForOrder()` ném exception gây rollback, thao tác lưu order trước đó bị rollback cùng transaction.

### 11.3. Chọn boundary ở service nghiệp vụ

Thường nên:

- Đặt ranh giới transaction tại use case hoặc service ứng dụng.
- Cho repository xử lý persistence operations và tham gia transaction hiện có.
- Tránh mỗi repository tự mở giao dịch mới nếu nghiệp vụ cần nguyên tử trên nhiều bảng.
- Xác định propagation một cách có chủ đích khi gọi service con.
- Không để controller hoặc serializer điều khiển lazy loading/transaction tùy tiện nếu không có thiết kế rõ.

Không có quy tắc “mọi method public đều phải `@Transactional`”. Các query đơn giản, orchestration nhiều hệ thống hoặc tác vụ kéo dài có thể cần boundary khác. Nhưng owner của transaction cần được định nghĩa rõ.

## 12. Spring propagation và ai thực sự commit

Một số giá trị propagation của Spring:

| Propagation | Khi caller đã có transaction | Khi caller chưa có transaction |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện có | Mở transaction mới |
| `REQUIRES_NEW` | Tạm treo transaction ngoài và mở transaction độc lập | Mở transaction mới |
| `MANDATORY` | Tham gia | Báo lỗi nếu thiếu transaction |
| `SUPPORTS` | Tham gia | Chạy không có transaction |
| `NOT_SUPPORTED` | Tạm treo transaction hiện có | Chạy không có transaction |
| `NEVER` | Báo lỗi nếu caller có transaction | Chạy không có transaction |
| `NESTED` | Dùng savepoint khi manager/resource hỗ trợ | Thường hoạt động tương tự REQUIRED khi không có transaction |

`NESTED` không tương đương `REQUIRES_NEW` và không được mọi JPA transaction manager hỗ trợ như nhau. `NESTED` thường gắn với JDBC savepoint; savepoint DB không tự giải quyết mọi trạng thái đã được giữ trong JPA persistence context.

### 12.1. Ví dụ `REQUIRES_NEW`

~~~java
@Service
public class AuditService {

    @Transactional(
        propagation = Propagation.REQUIRES_NEW
    )
    public void recordAttempt(String operationId) {
        // Ghi nhận một lần thử nghiệp vụ độc lập.
    }
}
~~~

Nếu CheckoutService đang ở transaction T1 và gọi AuditService qua Spring proxy, Spring có thể tạm treo T1 và mở T2 cho audit. Khi T2 commit, dữ liệu audit độc lập có thể tồn tại dù T1 về sau rollback.

Đây là ý nghĩa rất khác so với việc audit “đơn hàng đã thành công”. Nếu nghiệp vụ chỉ muốn ghi nhận đơn đã commit, REQUIRES_NEW trước commit có thể tạo audit sai trạng thái.

### 12.2. Rollback-only và `UnexpectedRollbackException`

Một tình huống thường gặp:

~~~text
OuterService @Transactional REQUIRED       --> T1
     |
     +-- InnerService @Transactional REQUIRED
     |      |
     |      +-- Ném exception, transaction bị đánh dấu rollback-only
     |
     +-- OuterService bắt exception và tiếp tục
     |
     +-- OuterService kết thúc bình thường
            |
            +-- Spring thử commit T1
                   |
                   +-- Phát hiện rollback-only
                   +-- Rollback và có thể báo
                       UnexpectedRollbackException
~~~

Điều này xảy ra vì **inner service không sở hữu một transaction commit độc lập**; nó tham gia T1. Ngay cả khi outer service bắt exception, transaction đã bị đánh dấu rollback-only không thể commit như một transaction thành công.

Phản ứng đúng là thiết kế lại chính sách lỗi và boundary, không “ép” commit bằng cách gọi thủ công `EntityManager.getTransaction()` bên trong Spring-managed service.

### 12.3. Self-invocation trong Spring

Với cơ chế Spring proxy phổ biến:

~~~java
@Service
public class OrderService {

    public void outer() {
        inner(); // Lời gọi trên chính this.
    }

    @Transactional
    public void inner() {
        // ...
    }
}
~~~

Lời gọi `outer() -> inner()` trên cùng instance có thể **không đi qua transaction proxy**, do đó annotation ở `inner` không khởi tạo transaction theo mong đợi.

Khi cần một transaction boundary độc lập, gọi qua bean/proxy phù hợp hoặc tổ chức lại service. Không mặc định mọi annotation có hiệu lực chỉ vì đã xuất hiện trên source code.

### 12.4. Checked và unchecked exception

Với Spring `@Transactional` theo mặc định thông dụng, transaction rollback khi method ném `RuntimeException` hoặc `Error`; checked exception thường không gây rollback trừ khi cấu hình như:

~~~java
@Transactional(rollbackFor = IOException.class)
public void importOrders() throws IOException {
    // ...
}
~~~

Nếu service bắt lỗi rồi không ném lại, Spring interceptor có thể không thấy exception. Khi đó cần quyết định có đánh dấu rollback-only hay không, thay vì hy vọng framework đoán được nghiệp vụ thất bại.

## 13. Quyền sở hữu EntityManager khác quyền sở hữu transaction

Đây là một trong những điểm dễ nhầm nhất.

### 13.1. Application-managed EntityManager

~~~java
EntityManager em = emf.createEntityManager();

try {
    // Thao tác trong transaction phù hợp.
} finally {
    em.close();
}
~~~

Ứng dụng tạo và đóng EntityManager. Nếu persistence unit resource-local, ứng dụng thường cũng tự điều khiển `EntityTransaction`. Nếu persistence unit JTA, transaction có thể do JTA coordinator quản lý dù EntityManager do ứng dụng tạo.

### 13.2. Container-managed EntityManager

~~~java
@PersistenceContext
private EntityManager em;
~~~

Container quản lý lifecycle của EntityManager được inject. Bean không tự đóng nó. Trong JTA, việc join/enlist persistence context vào transaction theo quy tắc của môi trường quyết định thời điểm đồng bộ.

### 13.3. Spring-managed EntityManager

Trong Spring, injection `@PersistenceContext` hoặc repository abstraction thường cung cấp một EntityManager proxy/tham chiếu gắn với persistence context đúng của transaction. Hạ tầng tạo/đóng EntityManager thực tế theo cấu hình.

Tự gọi `em.close()` trên đối tượng được hạ tầng quản lý không phải cách kết thúc transaction. Lời gọi có thể bị từ chối hoặc làm hỏng kỳ vọng lifecycle tùy proxy/provider.

### 13.4. Một EntityManager không được chia sẻ tùy tiện giữa nhiều thread

`EntityManager` không được thiết kế như một object thread-safe để nhiều request đồng thời cùng thao tác. Trong application-managed code, không đặt một EntityManager sống lâu trong singleton rồi dùng cho mọi request.

Thay vào đó:

- `EntityManagerFactory` có thể được chia sẻ theo vòng đời ứng dụng.
- Mỗi unit of work/transaction có EntityManager hoặc persistence context đúng phạm vi.
- Container/Spring quản lý EntityManager theo transaction/request phù hợp.
- Không chuyển một EntityManager active tùy tiện sang background thread.

Nếu một entity được detach hoặc được truyền sang thread khác, trạng thái managed/lazy-loading không còn giống trường hợp dùng trong persistence context ban đầu.

## 14. Transaction-scoped và extended persistence context

Ngoài quyền sở hữu transaction, còn phải hiểu **phạm vi sống của persistence context**.

### 14.1. Transaction-scoped persistence context

Trong môi trường Jakarta EE, injection thông dụng:

~~~java
@PersistenceContext(
    unitName = "shopJtaPU",
    type = PersistenceContextType.TRANSACTION
)
private EntityManager em;
~~~

Persistence context được gắn với transaction theo mô hình container-managed. Khi transaction kết thúc, các entity không còn được quản lý trong transaction-scoped context đó theo cùng vòng đời cũ.

Phù hợp cho request/service ngắn:

~~~text
Request
   |
   v
Transaction T1
   |
   +-- Persistence context P1
   +-- Persist/Find/Flush
   |
   v
Commit/Rollback
   |
   v
Kết thúc transaction-scoped context
~~~

### 14.2. Extended persistence context

Một số mô hình Jakarta EE, đặc biệt stateful session bean, cho phép **extended persistence context**:

~~~java
@Stateful
public class EditWizardBean {

    @PersistenceContext(
        unitName = "shopJtaPU",
        type = PersistenceContextType.EXTENDED
    )
    private EntityManager em;

    // Có thể giữ managed objects qua nhiều lời gọi
    // theo lifecycle của stateful bean.
}
~~~

Extended context có thể sống qua nhiều transaction, nhưng **không có nghĩa một transaction duy nhất kéo dài qua nhiều request**. Các thay đổi trong context vẫn phải tham gia transaction phù hợp để được đồng bộ/commit.

Ví dụ ý tưởng:

~~~text
Stateful conversation:
    Request 1: tải form và chỉnh sửa object trong extended context
    Request 2: tiếp tục chỉnh sửa
    Request 3: bắt đầu transaction, xác nhận lưu
        |
        v
      Commit
~~~

Đây là mô hình nâng cao, cần quản lý concurrency, state size, thời gian sống và stale data. Không nên dùng extended context chỉ để tránh `LazyInitializationException` trong REST.

### 14.3. Extended context không thay thế transaction

Nếu entity tồn tại lâu trong context nhưng chưa có transaction tham gia, gọi flush có thể không hợp lệ. Khi commit transaction thích hợp, provider mới đồng bộ những thay đổi được quản lý theo quy tắc của loại persistence context.

Do đó luôn phân biệt:

- **Persistence context sống bao lâu?**
- **Transaction bắt đầu/kết thúc khi nào?**
- **Context đã tham gia transaction chưa?**

## 15. Tham gia JTA transaction: `joinTransaction()`

Với JTA, một EntityManager có thể cần tham gia transaction trước khi flush hoặc đồng bộ các thay đổi.

API:

~~~java
entityManager.joinTransaction();
~~~

Trong container-managed, transaction-scoped persistence context với cấu hình synchronized, việc tham gia transaction thường được hạ tầng quản lý tự động.

Trong một số tình huống nâng cao, chẳng hạn application-managed JTA EntityManager hoặc unsynchronized persistence context, cần xem rõ cơ chế join. Không nên gọi `joinTransaction()` như một cách “tạo transaction”, vì nó **không bắt đầu transaction mới**.

### 15.1. Unsynchronized persistence context

JPA hỗ trợ:

~~~java
@PersistenceContext(
    unitName = "shopJtaPU",
    synchronization = SynchronizationType.UNSYNCHRONIZED
)
private EntityManager em;
~~~

Một unsynchronized persistence context có thể không tự tham gia JTA transaction. Khi cần đồng bộ:

~~~java
em.joinTransaction();
// Sau khi tham gia transaction đang hoạt động,
// JPA có thể flush theo quy tắc thích hợp.
~~~

Không thể mặc định rằng mỗi lần gọi `persist` trên unsynchronized context là dữ liệu được ghi ngay vào transaction hiện tại. Mô hình này được dùng có chủ đích cho các kịch bản conversation/phạm vi context đặc biệt, không phải mặc định của mọi ứng dụng.

### 15.2. Join khác commit

~~~text
joinTransaction() -> Cho persistence context tham gia giao dịch JTA
flush()           -> Đồng bộ SQL vào giao dịch
commit()          -> Transaction coordinator xác nhận giao dịch
~~~

Trong CMT, bean không tự gọi commit dù đã gọi join. Quyền sở hữu transaction vẫn thuộc container/framework hoặc chủ sở hữu JTA phù hợp.

## 16. Transaction và flush không phải cùng một quyền sở hữu

Một repository có thể gọi:

~~~java
em.persist(order);
em.flush();
~~~

Nhưng nó không nhất thiết là transaction owner. `flush()` chỉ yêu cầu đồng bộ thay đổi trong transaction hiện tại.

Ví dụ:

~~~text
OuterService @Transactional  --> Transaction T1
       |
       +-- Repository.persistOrder()
       |       |
       |       +-- persist()
       |       +-- flush()
       |
       +-- InventoryService.reserve()
               |
               +-- Throw RuntimeException
       |
       v
Rollback T1
~~~

Dù repository đã flush thành công, SQL của order vẫn có thể bị rollback cùng T1.

### 16.1. Cấp khóa không chứng minh commit

`@GeneratedValue(strategy = GenerationType.IDENTITY)` có thể khiến provider thực thi INSERT sớm để nhận ID. `SEQUENCE` có thể cấp ID trước INSERT. Trong cả hai trường hợp, ID đã tồn tại **không chứng minh giao dịch đã kết thúc thành công**.

Đối với application-managed code, chỉ trả kết quả lưu thành công sau khi `tx.commit()` thành công. Đối với managed transaction, caller phải hiểu result chỉ được xác nhận khi transaction owner hoàn tất; một method con có thể trả ID khi transaction ngoài vẫn còn mở.

### 16.2. Flush ở CMT không có nghĩa bean được quyền commit

~~~java
@TransactionAttribute(TransactionAttributeType.REQUIRED)
public void createOrder(...) {
    em.persist(order);
    em.flush();
    // Container vẫn sở hữu COMMIT/ROLLBACK.
}
~~~

Flush hữu ích để phát hiện sớm một số lỗi SQL nhưng không trao quyền điều khiển transaction cho bean.

### 16.3. Không mọi lỗi được phát hiện ở flush

Một số constraint có thể được kiểm tra muộn ở commit, và có thể có lỗi serialization, deadlock hoặc kết nối. Vì vậy, flush thành công không phải bảo đảm transaction sẽ commit.

## 17. Kết quả commit có thể không xác định khi mất kết nối

Một tình huống đặc biệt:

~~~text
Ứng dụng                       Database
   |                              |
   |---- COMMIT request --------->|
   |                              | có thể đã commit
   X<--- response bị mất ----------|
   |
   v
Ứng dụng thấy exception / timeout
~~~

Trong tình huống này, việc ứng dụng nhận lỗi chưa đủ để kết luận DB chắc chắn rollback. Điều này áp dụng cho cả resource-local và managed transaction.

Nếu API tạo đơn hàng có retry, nên có:

- Khóa nghiệp vụ duy nhất hoặc idempotency key.
- UNIQUE constraint phù hợp để chống tạo trùng.
- Logic tra cứu trạng thái giao dịch khi kết quả chưa xác định.
- Chính sách retry dựa trên **trạng thái nghiệp vụ**, không chỉ dựa trên exception class.
- Ghi log/correlation ID để đối chiếu.

Không giải quyết được trường hợp này chỉ bằng việc chuyển từ resource-local sang CMT hay Spring `@Transactional`.

## 18. Isolation và consistency không tự xuất hiện từ `@Transactional`

`@Transactional` giúp khai báo transaction boundary, nhưng không tự giải quyết mọi lỗi dữ liệu đồng thời.

Ví dụ hai request:

~~~text
Request A                                Request B
-----------------------------------      --------------------------------
Đọc tồn kho = 1                         Đọc tồn kho = 1
Trừ tồn kho còn 0                       Trừ tồn kho còn 0
Commit                                  Commit
~~~

Nếu không có cơ chế concurrency phù hợp, hệ thống có thể bán vượt số lượng cho phép dù mỗi request đều có transaction.

Cần cân nhắc:

- Locking optimistic bằng `@Version`.
- Locking pessimistic khi phù hợp.
- Cập nhật có điều kiện ở DB.
- Unique/check constraints.
- Isolation level theo yêu cầu.
- Quy tắc retry khi xung đột.

**Quyền sở hữu transaction xác định ranh giới nguyên tử; không tự suy ra mọi invariant concurrency đều được bảo vệ.**

### 18.1. Isolation do database và transaction manager quản lý

JPA chuẩn không cung cấp một API duy nhất trên `EntityManager` để đặt mọi isolation level của DB theo cách portable.

Spring `@Transactional(isolation = ...)` có thể cấu hình isolation trên transaction manager/resource được hỗ trợ. Trong Jakarta EE JTA, điều chỉnh isolation có thể phụ thuộc datasource/server hoặc thiết lập vendor-specific.

Không dùng `FlushModeType.AUTO/COMMIT` như một cách thay đổi isolation; flush mode điều chỉnh thời điểm đồng bộ truy vấn, không thay thế READ COMMITTED/REPEATABLE READ/SERIALIZABLE.

## 19. Giao dịch một database và giao dịch nhiều resource

### 19.1. Resource-local thường gắn với một persistence resource

JPA resource-local transaction thường làm việc với resource JDBC liên quan tới EntityManager. Nó không tự điều phối một giao dịch nguyên tử giữa nhiều database độc lập và hệ thống message broker.

Nếu code làm:

~~~text
Begin local DB transaction
  |
  +-- INSERT order
  |
  +-- HTTP gọi dịch vụ thanh toán
  |
  +-- Commit DB
~~~

HTTP request không trở thành một phần của transaction JPA chỉ vì nó được gọi trong khoảng giữa begin và commit. Nếu thanh toán đã thành công nhưng commit DB thất bại, cần cơ chế xử lý bù hoặc thiết kế nghiệp vụ khác.

### 19.2. JTA có thể điều phối nhiều resource khi được hỗ trợ

JTA có thể điều phối transaction với những resource được enlist và hỗ trợ mô hình transaction thích hợp (bao gồm XA khi cấu hình đúng). Tuy nhiên, chỉ bật JTA **không tự biến mọi REST API, email hoặc queue bất kỳ thành participant XA**.

Cần xác nhận:

- Resource có hỗ trợ enlistment/XA không?
- Transaction manager được cấu hình ra sao?
- Resource driver/datasource có tương thích không?
- Hành vi recovery khi transaction coordinator hoặc resource lỗi?
- Những tác vụ ngoài transaction được xử lý thế nào?

Distributed transaction làm tăng độ phức tạp và không phải lựa chọn mặc định cho mọi hệ thống microservices.

### 19.3. Transactional outbox cho sự kiện sau commit

Một mô hình thường dùng khi cần phát event sau khi tạo đơn hàng:

~~~text
Trong cùng DB transaction:
    INSERT purchase_order
    INSERT outbox_event
    COMMIT

Sau commit:
    Outbox worker đọc event chưa gửi
    Gửi tới message broker
    Đánh dấu/ghi nhận kết quả, retry khi cần
~~~

Vì order và outbox row được ghi trong cùng DB transaction, rollback sẽ hủy cả hai; một worker độc lập gửi sự kiện sau khi commit.

Outbox vẫn cần retry, idempotency và cơ chế xử lý trùng lặp. Nhưng nó giúp tránh gửi message thông báo đơn hàng thành công **trước khi transaction DB được xác nhận**.

## 20. Rủi ro khi giữ transaction mở quá lâu

Quyền sở hữu transaction còn bao gồm trách nhiệm giữ transaction **đúng phạm vi thời gian**.

Không nên để transaction DB mở trong khi:

- Chờ người dùng nhập nhiều màn hình.
- Gọi API bên ngoài có latency không kiểm soát.
- Thực hiện upload file rất lớn.
- Ngủ, retry mạng hoặc đợi kết quả xử lý bất đồng bộ.
- Thực hiện tính toán CPU kéo dài không cần khóa DB.

Transaction dài có thể giữ lock, connection và tài nguyên database, làm tăng contention hoặc timeout.

### 20.1. Sắp xếp công việc trước và sau transaction

Một flow có thể thiết kế:

~~~text
1. Validate request (không cần transaction DB dài)
2. Chuẩn bị dữ liệu nghiệp vụ
3. Bắt đầu transaction
4. Lưu order, cập nhật tồn kho, ghi outbox
5. Commit hoặc rollback nhanh
6. Gửi event qua worker sau commit
~~~

Tùy yêu cầu, một số bước validation cần đọc DB và concurrency control trong transaction; không nên đẩy mọi kiểm tra ra ngoài một cách máy móc. Mục tiêu là ranh giới gọn nhưng vẫn bảo vệ invariant.

### 20.2. Transaction không được “truyền” sang thread khác tùy tiện

Transaction context của Spring/JTA trong các mô hình thông dụng gắn với luồng thực thi và cơ chế môi trường. Một task được chạy bằng `CompletableFuture` hoặc thread pool không tự động tham gia đúng transaction của caller.

Ví dụ nguy hiểm:

~~~java
@Transactional
public void createOrder() {
    entityManager.persist(order);

    CompletableFuture.runAsync(() -> {
        // Không được giả định thread này tham gia
        // transaction và EntityManager của thread gọi.
    });
}
~~~

Nếu cần xử lý bất đồng bộ, hãy thiết kế transaction boundary riêng và truyền **ID/DTO**, không chia sẻ một EntityManager managed không thread-safe giữa các thread. Nếu có cơ chế context propagation đặc biệt, phải hiểu hợp đồng của môi trường.

## 21. Xử lý exception ở đúng chủ sở hữu giao dịch

### 21.1. Resource-local: Owner phải rollback và close

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    performBusinessWork(em);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Trong code sản xuất, khi rollback bản thân cũng có thể ném exception, nên cân nhắc giữ nguyên root cause và gắn rollback exception làm suppressed, như ví dụ ở phần 4.

Sau khi gặp lỗi persistence nghiêm trọng, không nên giả định có thể tiếp tục dùng EntityManager và transaction như chưa có gì xảy ra.

### 21.2. Container-managed: Owner hạ tầng xử lý

~~~java
@TransactionAttribute(TransactionAttributeType.REQUIRED)
public void performBusinessWork() {
    // Tập trung vào nghiệp vụ và JPA calls.
    // Ném exception/đánh dấu rollback-only khi cần.
}
~~~

Bean không tự gọi `tx.rollback()` bằng `EntityTransaction`. Container sẽ áp dụng quy tắc giao dịch và exception.

### 21.3. Spring: Để interceptor nhìn thấy tín hiệu lỗi

~~~java
@Transactional
public void performBusinessWork() {
    if (invalidBusinessState) {
        throw new IllegalStateException(
            "Invalid business state"
        );
    }

    // ...
}
~~~

Một unchecked exception đi qua Spring transaction interceptor thường làm transaction rollback theo mặc định. Nhưng nếu code bắt rồi nuốt exception, Spring có thể không biết nghiệp vụ đã thất bại.

Trong trường hợp cần rollback với checked exception hoặc xử lý lỗi đặc biệt, cấu hình rõ `rollbackFor` hay đánh dấu rollback-only theo API Spring đúng ngữ cảnh.

### 21.4. Không ép commit khi transaction đã rollback-only

Nếu transaction manager đánh dấu rollback-only, không thể biến nó thành commit hợp lệ chỉ bằng cách gọi `flush()` hoặc đổi `FlushModeType`. Cần kết thúc transaction bằng rollback rồi bắt đầu unit of work mới nếu nghiệp vụ yêu cầu retry.

## 22. Quản lý transaction trong các tầng kiến trúc

Một phân tầng phổ biến:

~~~text
HTTP Controller
       |
       v
Application Service / Use Case
       |
       +-- Domain logic
       |
       +-- Repository A
       |
       +-- Repository B
       |
       v
Persistence / Database
~~~

Thông thường:

- Controller nhận input, xác thực và trả response.
- Application service quyết định **đơn vị nghiệp vụ cần tính nguyên tử**.
- Transaction manager thực thi begin/commit/rollback quanh service.
- Repository tham gia transaction và xử lý persistence operations.
- Domain entity bảo vệ các invariant bên trong object; DB constraint bảo vệ dữ liệu trên mọi đường ghi.

### 22.1. Một transaction cho toàn bộ use case

Ví dụ đặt hàng phải lưu đơn và trừ tồn kho cùng DB:

~~~text
checkout()
    |
    +-- validate
    +-- create PurchaseOrder
    +-- decrease Inventory
    +-- insert OutboxEvent
    |
    +-- commit tất cả hoặc rollback tất cả
~~~

Nếu mỗi repository commit riêng, có thể lưu đơn nhưng chưa trừ tồn kho. Đặt transaction ở use case làm ownership rõ ràng hơn.

### 22.2. Transaction cho từng thao tác độc lập

Một luồng batch xử lý 100.000 bản ghi có thể không muốn giữ một transaction khổng lồ. Khi đó có thể chia thành nhiều unit of work/chunk có ranh giới riêng.

Đây là sự đánh đổi giữa tính nguyên tử toàn batch và tài nguyên/khả năng retry. Nếu nghiệp vụ cần tất cả 100.000 bản ghi được xử lý như một giao dịch nguyên tử, không tự chia chunk và commit riêng mà không thay đổi hợp đồng nghiệp vụ.

### 22.3. Không nên để repository tự quyết định chuyện nghiệp vụ toàn cục

Repository có thể có transaction mặc định cho thao tác đơn lẻ, nhưng khi được gọi trong outer transaction với propagation thích hợp nó phải tham gia transaction đó. Đừng buộc repository luôn `REQUIRES_NEW` chỉ để “dễ lưu”, vì có thể phá vỡ tính nguyên tử của use case.

## 23. Kiểm thử quyền sở hữu transaction

Các bài test JPA dễ tạo ra cảm giác “đã lưu” trong khi transaction bị rollback ở cuối test.

### 23.1. Test Spring có `@Transactional`

~~~java
@SpringBootTest
@Transactional
class OrderRepositoryTest {

    @Autowired
    private EntityManager em;

    @Test
    void canPersistOrder() {
        PurchaseOrder order =
            new PurchaseOrder(
                "CUST-01",
                new BigDecimal("100000.00")
            );

        em.persist(order);
        em.flush();

        assertNotNull(order.getId());
    }
}
~~~

Nhiều test Spring có `@Transactional` được rollback mặc định sau khi test. Assertion trên ID chỉ chứng minh đã cấp khóa; `flush()` chỉ đồng bộ SQL trong transaction test, không chứng minh record còn ở DB sau test.

### 23.2. Test commit thực tế

Nếu muốn xác minh service thật sự commit, cần tổ chức transaction phù hợp với môi trường test:

1. Gọi service qua Spring proxy hoặc container như khi chạy thật.
2. Đảm bảo lời gọi đó mở và kết thúc transaction như mong muốn, không bị một outer test transaction bao lại rồi rollback.
3. Mở một persistence context/transaction mới.
4. Truy vấn bằng identity hoặc khóa nghiệp vụ để kiểm tra record đã được commit.
5. Làm sạch dữ liệu test theo phương án cô lập đã thiết kế.

Không dùng `em.find` trong cùng persistence context vừa `persist` để chứng minh commit, vì JPA có thể trả lại entity từ first-level cache.

### 23.3. Test lỗi làm rollback

Một integration test nên chứng minh:

- Lưu order và cập nhật tồn kho cùng transaction.
- Giả lập lỗi sau khi lưu order nhưng trước khi kết thúc nghiệp vụ.
- Xác minh cả order và cập nhật tồn kho không được commit.
- Nếu có outbox record trong cùng transaction, xác minh nó cũng không được commit.
- Nếu audit dùng `REQUIRES_NEW` theo chủ đích, xác minh nó có thể tồn tại độc lập.

### 23.4. Test propagation cần gọi qua boundary thật

Với Spring, test trực tiếp method nội bộ qua `this.inner()` có thể không kiểm tra đúng proxy behavior. Với EJB, gọi method nội bộ trên cùng instance cũng có thể không đi qua container interception như lời gọi qua component boundary.

Vì vậy khi test transaction attribute/propagation, cần gọi qua đối tượng được container/framework quản lý hoặc sử dụng một integration test phản ánh đúng kiến trúc runtime.

## 24. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “EntityManager nào gọi persist thì EntityManager đó sở hữu commit.” | EntityManager thực hiện persistence work; transaction owner có thể là service/container/framework. |
| “Application-managed EntityManager luôn là RESOURCE_LOCAL.” | EntityManager do app tạo có thể được cấu hình JTA; lifecycle và transaction type là hai trục khác nhau. |
| “Spring `@Transactional` luôn là JTA.” | Spring có thể quản lý giao dịch resource-local qua JpaTransactionManager hoặc JTA qua JtaTransactionManager. |
| “Inject `@PersistenceContext` rồi tự `em.close()`.” | Container/framework thường sở hữu lifecycle của EntityManager injected. |
| “JTA EntityManager dùng `em.getTransaction()`.” | Không đúng; cần CMT hoặc JTA UserTransaction trong môi trường phù hợp. |
| “Method được đánh dấu `@Transactional` tức chắc chắn đã có transaction.” | Còn phụ thuộc interception/proxy, propagation, cấu hình transaction manager và caller. |
| “Nested begin tạo transaction lồng nhau.” | Resource-local JPA không biến begin lần hai thành nested transaction. |
| “Method service con trả ID nghĩa là đã commit.” | Có thể nó đang tham gia transaction ngoài chưa commit. |
| “Flush là commit.” | Flush đồng bộ SQL; rollback vẫn có thể hủy dữ liệu. |
| “Transaction CMT rollback với mọi exception.” | Phụ thuộc loại exception và quy tắc container/Jakarta Transactions. |
| “Bắt exception ở outer service thì chắc vẫn commit.” | Inner service có thể đã đánh dấu transaction rollback-only. |
| “REQUIRES_NEW giúp toàn bộ nghiệp vụ nguyên tử hơn.” | Nó tạo giao dịch độc lập, có thể commit một phần khi transaction ngoài rollback. |
| “JTA tự giao dịch hóa email và REST call.” | Chỉ resource được enlist/hỗ trợ transaction phù hợp mới tham gia; hiệu ứng ngoài DB cần chiến lược riêng. |
| “Extended persistence context là extended transaction.” | Context có thể sống lâu hơn nhiều transaction; không phải một transaction kéo dài. |
| “Có ID là dữ liệu đã lưu thành công.” | ID có thể được cấp trước commit, thậm chí trước INSERT. |
| “Transaction trên thread cha được tự động dùng ở CompletableFuture.” | Context giao dịch/EntityManager thường không tự truyền sang thread khác. |
| “Đổi FlushModeType thành COMMIT là đã xác nhận transaction.” | Flush mode không phải operation commit. |
| “Có transaction thì không cần UNIQUE/FK/locking.” | Transaction boundary không thay thế toàn vẹn dữ liệu và concurrency control. |

## 25. Quy trình xác định transaction owner trong dự án thật

Khi đọc một đoạn code JPA mà chưa rõ ai sở hữu transaction, có thể lần theo các bước.

### Bước 1: Xác định môi trường chạy

Ứng dụng Java SE tự tạo EntityManagerFactory? Jakarta EE container? Spring Boot với Spring Data JPA? Có kết hợp nhiều framework không?

### Bước 2: Kiểm tra persistence unit và transaction manager

Tìm cấu hình `transaction-type="RESOURCE_LOCAL"` hay `"JTA"`, datasource và transaction manager có hiệu lực. Với Spring, xem dùng `JpaTransactionManager` hay `JtaTransactionManager` hoặc manager khác.

### Bước 3: Xác định EntityManager được tạo thế nào

Ứng dụng gọi `emf.createEntityManager()` và tự close, hay dùng `@PersistenceContext`/repository injection? Đừng suy ra transaction mode chỉ từ điểm này.

### Bước 4: Xác định nơi begin hoặc annotation mở boundary

Tìm:

~~~java
tx.begin();
~~~

hoặc:

~~~java
userTransaction.begin();
~~~

hoặc annotation:

~~~java
@TransactionAttribute(TransactionAttributeType.REQUIRED)
@Transactional
~~~

Sau đó xem transaction attribute/propagation được áp dụng ở lời gọi thực tế nào.

### Bước 5: Xác định caller bên ngoài

Một method `REQUIRED` có thể **không sở hữu transaction mới** nếu caller đã mở transaction. Muốn biết ai commit, phải lần tới boundary ngoài cùng hoặc phần transaction được khởi tạo độc lập bởi `REQUIRES_NEW`.

### Bước 6: Kiểm tra rollback policy

Xác định checked/unchecked exception, `rollbackFor`, `rollbackOn`, `setRollbackOnly`, catch/rethrow và tình huống exception bị nuốt.

### Bước 7: Kiểm tra context và thread

EntityManager có nằm trong đúng transaction/persistence context không? Method có được gọi qua proxy/container không? Có async thread không? Context có synchronized/unsynchronized hay không?

### Bước 8: Xem log SQL cùng mốc transaction

Đừng chỉ xem `INSERT`/`UPDATE`. Cần hiểu nó nằm trong transaction nào, đã commit hay rollback. Với JDBC/DB log hoặc tracing thích hợp, đối chiếu ID/correlation để tránh trộn các request song song.

### Bước 9: Kiểm tra bằng integration test

Test transaction thật với DB/provider và cấu hình đang dùng: một flow thành công và ít nhất một flow rollback sau khi đã có SQL. Xác nhận trạng thái ở persistence context/transaction mới.

### Bước 10: Định nghĩa rõ ownership trong thiết kế

Nếu không ai chịu trách nhiệm kết thúc transaction, đó là lỗ hổng thiết kế. Nếu nhiều tầng cùng tự commit, đó có thể là xung đột ownership. Chỉ định một ranh giới rõ cho từng unit of work và để các tầng bên trong tham gia theo quy tắc nhất quán.

## 26. Bài tập thực hành

### Bài 1. Nhận diện resource-local transaction

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

tx.begin();
em.persist(new PurchaseOrder("C01", new BigDecimal("10.00")));
tx.commit();
em.close();
~~~

**Câu hỏi:** Ai sở hữu transaction, ai sở hữu EntityManager và ai quyết định rollback khi lỗi?

**Đáp án:** Ứng dụng trực tiếp sở hữu ranh giới `EntityTransaction` và tạo/đóng EntityManager; code ứng dụng phải thực hiện rollback thích hợp khi lỗi. Ví dụ này thiếu try/catch/finally nên chưa phải mẫu production an toàn.

### Bài 2. JTA EntityManager và `getTransaction()`

~~~java
@PersistenceContext
private EntityManager em;

public void execute() {
    em.getTransaction().begin();
}
~~~

Giả sử persistence unit là JTA trong container-managed EJB.

**Câu hỏi:** Sai ở đâu?

**Đáp án:** `getTransaction()` không được dùng để quản lý JTA EntityManager. Trong CMT, container quản lý transaction theo transaction attribute; trong BMT phù hợp, code dùng `UserTransaction`, không dùng `EntityTransaction` của resource-local.

### Bài 3. Repository có được commit không?

~~~java
@Transactional
public void checkout() {
    orderRepository.saveOrder();
    stockRepository.reserve();
}
~~~

**Câu hỏi:** Nếu hai repository cùng tham gia transaction và cần thành công cùng nhau, nên để chúng tự commit từng method không?

**Đáp án:** Không. Transaction owner của use case nên giữ một ranh giới chung; các repository tham gia và không commit độc lập. Nếu reserve thất bại, toàn bộ thao tác DB trong transaction cần rollback theo chính sách lỗi.

### Bài 4. Inner REQUIRED trả ID

~~~java
@Transactional
public void outer() {
    Long id = orderService.createOrder();
    shippingService.reserve(id); // Ném RuntimeException.
}
~~~

Giả sử `createOrder()` có `@Transactional` mặc định REQUIRED và cùng transaction manager.

**Câu hỏi:** ID trả ra từ service con có chứng minh order đã commit không?

**Đáp án:** Không. Service con tham gia transaction ngoài. Khi outer rollback, order cũng bị rollback nếu các thao tác cùng transaction.

### Bài 5. REQUIRES_NEW và audit

~~~java
@Transactional
public void checkout() {
    auditService.recordAttemptRequiresNew();
    createOrderAndReserve();
}
~~~

AuditService dùng REQUIRES_NEW và đã commit, sau đó checkout rollback.

**Câu hỏi:** Audit có thể còn tồn tại không, và có sai không?

**Đáp án:** Có thể tồn tại. Đây là đúng nếu audit ghi nhận **đã thử thực hiện**; sẽ sai nếu audit tuyên bố **checkout đã thành công**. Mô hình transaction phải phù hợp ý nghĩa bản ghi audit.

### Bài 6. Checked exception trong Spring

~~~java
@Transactional
public void importOrders() throws IOException {
    em.persist(order);
    throw new IOException("File parse failure");
}
~~~

**Câu hỏi:** Có chắc transaction rollback theo mặc định không?

**Đáp án:** Không. Với Spring `@Transactional` mặc định, checked exception như `IOException` thường không làm rollback trừ khi đã cấu hình. Nếu lỗi này phải hủy toàn bộ nhập liệu, thêm `rollbackFor = IOException.class` hoặc thiết kế exception policy phù hợp.

### Bài 7. Self-invocation

~~~java
public void first() {
    second();
}

@Transactional
public void second() {
    em.persist(order);
}
~~~

**Câu hỏi:** Vì sao transaction có thể không được mở?

**Đáp án:** Với Spring proxy AOP thông thường, `first()` gọi `second()` qua `this`, bỏ qua proxy transaction của method second. Nên gọi qua boundary bean/proxy phù hợp hoặc tổ chức lại transaction ở method được gọi từ bên ngoài.

### Bài 8. Extended context

Một stateful bean giữ entity managed qua ba màn hình nhập liệu.

**Câu hỏi:** Có nghĩa một transaction DB mở suốt thời gian người dùng đi qua ba màn hình không?

**Đáp án:** Không. Extended persistence context có thể sống qua nhiều transaction; muốn đồng bộ vào DB vẫn cần transaction phù hợp. Không nên giữ transaction DB dài chỉ để phục vụ UI conversation.

### Bài 9. Flush trước rollback

~~~java
tx.begin();
em.persist(order);
em.flush();
tx.rollback();
~~~

**Câu hỏi:** Vì sao có `INSERT` trong log mà bản ghi không có sau khi transaction kết thúc?

**Đáp án:** Flush đã gửi SQL trong transaction; rollback hủy tác động. Flush không cam kết dữ liệu.

### Bài 10. Spring transaction manager

Ứng dụng Spring Boot dùng resource-local persistence unit cùng JpaTransactionManager, service dùng `@Transactional`.

**Câu hỏi:** Đây là application-managed hay managed transaction?

**Đáp án:** Ở tầng service, đây là **transaction được Spring quản lý declaratively**. Tài nguyên JPA bên dưới là resource-local, cho thấy phân loại “JTA vs RESOURCE_LOCAL” khác với “app code tự begin/commit vs framework quản lý boundary”.

### Bài 11. Async task và EntityManager

Một service đang ở transaction T1 gọi `CompletableFuture.runAsync(...)`, rồi truyền EntityManager sang thread worker để cập nhật entity.

**Câu hỏi:** Có nên kỳ vọng task tự tham gia T1 không?

**Đáp án:** Không. Transaction context/EntityManager thường không tự truyền sang thread khác, và EntityManager không thread-safe. Thiết kế một operation bất đồng bộ độc lập với ID/DTO và transaction boundary riêng.

### Bài 12. Chọn điểm đặt transaction

Nghiệp vụ tạo đơn, trừ kho và ghi outbox trong cùng DB; sau đó cần gửi message qua broker.

**Câu hỏi:** Nên đặt transaction ở repository hay service use case? Gửi message ở đâu?

**Đáp án:** Đặt transaction quanh toàn bộ phần DB ở service use case để order, stock và outbox commit/rollback cùng nhau. Gửi message qua worker xử lý outbox sau commit, kèm retry/idempotency. Không gửi message trước khi commit chỉ vì entity đã có ID.

## 27. Tổng kết

~~~text
                      JPA APPLICATION
                             |
               Ai sở hữu ranh giới?
                             |
          +------------------+------------------+
          |                  |                  |
      ỨNG DỤNG           JAKARTA EE          SPRING
      TỰ QUẢN LÝ         CONTAINER          FRAMEWORK
          |                  |                  |
   RESOURCE_LOCAL        CMT EJB /          @Transactional
   EntityTransaction     JTA interceptor    + TransactionManager
          |                  |                  |
   begin / commit        Interceptor/       Interceptor/
   rollback trong code   container quyết    manager quyết
          |              định commit        định commit
          |                  |                  |
          +------------------+------------------+
                             |
                             v
                     EntityManager
                 persist/find/remove/flush
                             |
                             v
                  Transaction / Database
                             |
                        COMMIT hoặc
                         ROLLBACK

Ngoài ra: BMT dùng UserTransaction để code điều khiển JTA,
không dùng EntityTransaction cho JTA EntityManager.
~~~

Những nguyên tắc cần nhớ:

1. **Quyền sở hữu transaction là quyền bắt đầu, commit và rollback**, không phải quyền gọi `persist()` hay `flush()`.
2. **RESOURCE_LOCAL dùng `EntityTransaction`** khi ứng dụng tự điều khiển JPA transaction; owner cần xử lý lỗi, rollback và đóng application-managed EntityManager.
3. **JTA EntityManager không được quản lý bằng `getTransaction()`**; dùng transaction container hoặc `UserTransaction` trong bối cảnh bean-managed phù hợp.
4. **Container-managed transaction** dùng transaction attribute/interceptor để tham gia hoặc mở transaction và xử lý commit ngoài method body.
5. **Spring `@Transactional` quản lý ranh giới ở tầng framework**, dù JPA bên dưới có thể dùng RESOURCE_LOCAL hoặc JTA; cần xem propagation và transaction manager cụ thể.
6. **Application-managed EntityManager và application-managed transaction không đồng nghĩa tuyệt đối.** Lifecycle EntityManager và transaction demarcation là hai trục riêng.
7. **Method con trả về không có nghĩa transaction ngoài đã commit.** `REQUIRED` tham gia transaction hiện có; `REQUIRES_NEW` tạo ranh giới độc lập cần được sử dụng thận trọng.
8. **Flush khác commit; ID khác trạng thái đã lưu thành công.** Các SQL đã chạy vẫn có thể rollback.
9. **Rollback policy phụ thuộc framework và loại exception.** Cần hiểu rollback-only, checked/unchecked exceptions, proxy interception và transaction propagation.
10. **Persistence context scope không phải transaction scope trong mọi trường hợp.** Extended context không có nghĩa giao dịch kéo dài.
11. **Một transaction không tự bao trùm side effect ngoài DB**; cần outbox/idempotency/saga hoặc resource transaction thực sự tham gia khi phù hợp.
12. **Ranh giới đúng phải theo unit of work nghiệp vụ**, đồng thời đủ ngắn để không giữ lock/connection lâu và đủ rộng để bảo vệ các thay đổi phải nguyên tử cùng nhau.
13. **Luôn xác định owner thực tế qua cấu hình và đường gọi**, sau đó kiểm chứng bằng integration test trên transaction và DB thật.

Khi hiểu đúng ai sở hữu giao dịch trong ứng dụng và trong môi trường được quản lý, code JPA trở nên dễ kiểm soát hơn: entity và repository tập trung vào persistence, service tập trung vào nghiệp vụ, còn thành phần transaction owner chịu trách nhiệm xác nhận hoặc hủy toàn bộ đơn vị công việc một cách nhất quán.
