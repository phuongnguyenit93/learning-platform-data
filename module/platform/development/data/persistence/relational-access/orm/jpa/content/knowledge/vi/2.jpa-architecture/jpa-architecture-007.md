# Giao dịch cục bộ và giao dịch JTA trong kiến trúc JPA

## 1. Vì sao JPA cần giao dịch?

Khi ứng dụng làm việc với cơ sở dữ liệu quan hệ thông qua **Jakarta Persistence (JPA)**, một tác vụ nghiệp vụ thường gồm nhiều thao tác: tạo bản ghi, cập nhật các entity liên quan, kiểm tra điều kiện và cuối cùng xác nhận kết quả. **Transaction (giao dịch)** xác định ranh giới mà các thao tác dữ liệu phải được hoàn tất cùng nhau hoặc được hủy bỏ cùng nhau.

Ví dụ: hệ thống ghi một đơn hàng và các dòng chi tiết của đơn. Nếu việc lưu chi tiết thất bại, ứng dụng không muốn giữ lại một đơn hàng thiếu dữ liệu. Hai lần gọi `persist()` có thể nằm trong **cùng một transaction**, rồi toàn bộ thay đổi chỉ được xác nhận khi transaction `commit` thành công.

Các thuộc tính thường dùng để giải thích transaction là **ACID**:

- **Atomicity (nguyên tử):** toàn bộ công việc của transaction được commit hoặc bị rollback.
- **Consistency (nhất quán):** transaction đưa dữ liệu từ trạng thái hợp lệ này sang trạng thái hợp lệ khác, theo những ràng buộc và quy tắc được thực thi.
- **Isolation (cô lập):** các transaction đồng thời nhìn thấy thay đổi của nhau theo mức cô lập mà database áp dụng.
- **Durability (bền vững):** khi commit thành công, các thay đổi đã được ghi bền vững theo bảo đảm của hệ quản trị cơ sở dữ liệu.

JPA không tự thay thế transaction của database. Provider JPA (ví dụ Hibernate ORM, EclipseLink) quản lý các entity và biến thay đổi thành SQL; transaction quyết định khi nào những SQL đó được xác nhận hoặc hủy bỏ.

Có hai cách quản lý transaction chính khi dùng JPA:

1. **Giao dịch cục bộ / resource-local transaction:** ứng dụng điều khiển transaction thông qua `EntityTransaction` lấy từ `EntityManager`.
2. **Giao dịch JTA / Jakarta Transactions:** một **transaction manager** điều phối transaction; JPA `EntityManager` tham gia vào transaction đó.

Đây là lựa chọn về **người quản lý ranh giới transaction**, không phải hai phương thức truy vấn khác nhau. Các thao tác JPA như `persist()`, `find()`, `remove()` và JPQL vẫn quen thuộc trong cả hai mô hình.

## 2. Vị trí của giao dịch trong kiến trúc JPA

```text
                       Mã nghiệp vụ / Service
                               |
                 +-------------+-------------+
                 |                           |
          RESOURCE_LOCAL                    JTA
                 |                           |
     EntityTransaction.begin()    Container / JTA Transaction Manager
     EntityTransaction.commit()     @Transactional / EJB / UserTransaction
                 |                           |
                 +-------------+-------------+
                               |
                          EntityManager
                               |
                       Persistence Context
                               |
                         JPA Provider
                               |
                      JDBC / DataSource
                               |
                         RDBMS / SQL
```

Để hiểu đúng sơ đồ, cần phân biệt ba khái niệm:

- **`EntityManager`** là API thao tác entity; nó gắn với một **persistence context** quản lý các entity đang ở trạng thái `managed`.
- **Persistence context** theo dõi trạng thái entity và xác định những gì cần đồng bộ xuống database. Nó **không đồng nghĩa với transaction**. Một persistence context có thể tồn tại ngoài thời điểm thực thi SQL hoặc, tùy mô hình quản lý, có vòng đời khác ranh giới transaction.
- **Transaction** bao quanh đơn vị công việc có thể commit/rollback. Trong resource-local, ứng dụng dùng `EntityTransaction`; trong JTA, transaction manager của môi trường thực thi điều phối.

**Flush không phải commit.** Khi JPA `flush()`, provider đẩy các thay đổi đang chờ thành lệnh SQL trong transaction phù hợp; transaction vẫn có thể rollback. Ngược lại, commit thường kích hoạt đồng bộ những thay đổi chưa được flush trước khi transaction hoàn tất. Provider có thể phát lệnh SQL sớm hơn commit vì cơ chế sinh khóa, flush mode hoặc yêu cầu truy vấn.

## 3. Giao dịch cục bộ: `RESOURCE_LOCAL`

### 3.1. Khái niệm và phạm vi

**Resource-local transaction** là transaction gắn với tài nguyên cơ sở dữ liệu mà `EntityManager` sử dụng. Ứng dụng trực tiếp mở, commit hoặc rollback transaction bằng `jakarta.persistence.EntityTransaction`:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

tx.begin();
// em.persist(...); em.find(...); em.remove(...);
tx.commit();
```

Các thao tác được thực hiện trong phạm vi resource-local transaction đó; việc điều phối transaction thuộc về mã ứng dụng. Mô hình này phổ biến trong:

- Ứng dụng **Java SE** dùng JPA trực tiếp, không có Jakarta EE container quản lý JTA.
- Chương trình batch nhỏ, công cụ dòng lệnh hoặc bài thực hành chỉ làm việc với một cơ sở dữ liệu.
- Hệ thống chủ động quản lý transaction ở tầng hạ tầng hoặc repository thay vì thông qua transaction manager JTA.

Mặc dù gọi là *cục bộ*, transaction vẫn có đầy đủ ý nghĩa commit/rollback với database. Điểm giới hạn chính là **JPA resource-local không mặc nhiên điều phối một transaction nguyên tử trên nhiều tài nguyên độc lập** như hai database hoặc database kết hợp message broker.

### 3.2. Cấu hình persistence unit

Trong file `src/main/resources/META-INF/persistence.xml`, chỉ rõ `transaction-type="RESOURCE_LOCAL"`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="ordersLocalPU"
                      transaction-type="RESOURCE_LOCAL">
        <class>com.example.Invoice</class>
        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:orders;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password" value=""/>
            <property name="jakarta.persistence.schema-generation.database.action"
                      value="drop-and-create"/>
        </properties>
    </persistence-unit>
</persistence>
```

Ví dụ dùng H2 trong bộ nhớ để minh họa. Project phải có **Jakarta Persistence API**, **một JPA provider** tương thích và **H2 JDBC driver**. Thuộc tính `drop-and-create` xóa/tạo lại schema nên chỉ phù hợp với bài thực hành hoặc môi trường thử nghiệm; hệ thống thực tế nên dùng quy trình migration schema phù hợp.

`EntityManagerFactory` được khởi tạo từ persistence unit và có thể được dùng chung trong ứng dụng:

```java
EntityManagerFactory emf =
        Persistence.createEntityManagerFactory("ordersLocalPU");
```

`Persistence.createEntityManagerFactory()` dùng để **bootstrap** JPA; nó không bắt đầu transaction. Transaction được bắt đầu khi gọi `EntityTransaction.begin()` trên một `EntityManager` được tạo từ factory.

### 3.3. Ví dụ: hai bản ghi trong cùng transaction

Entity dùng cho các ví dụ:

```java
package com.example;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "invoices")
public class Invoice {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String customer;

    @Column(nullable = false)
    private BigDecimal amount;

    protected Invoice() {
        // JPA cần constructor không tham số.
    }

    public Invoice(String customer, BigDecimal amount) {
        this.customer = customer;
        this.amount = amount;
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
```

Một ứng dụng Java SE thao tác an toàn với `EntityManager` và `EntityTransaction` như sau:

```java
package com.example;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;
import java.math.BigDecimal;

public class LocalTransactionDemo {
    public static void main(String[] args) {
        EntityManagerFactory emf =
                Persistence.createEntityManagerFactory("ordersLocalPU");

        try {
            EntityManager em = emf.createEntityManager();

            try {
                EntityTransaction tx = em.getTransaction();

                try {
                    tx.begin();

                    em.persist(new Invoice(
                            "Khách A", new BigDecimal("120000")));
                    em.persist(new Invoice(
                            "Khách B", new BigDecimal("85000")));

                    // Hai bản ghi cùng thuộc một transaction.
                    tx.commit();
                } catch (RuntimeException ex) {
                    if (tx.isActive()) {
                        tx.rollback();
                    }
                    throw ex;
                }
            } finally {
                em.close();
            }
        } finally {
            emf.close();
        }
    }
}
```

Luồng thực thi:

1. `Persistence` tạo một `EntityManagerFactory` từ `ordersLocalPU`.
2. Factory tạo `EntityManager` với persistence context riêng.
3. `em.getTransaction().begin()` bắt đầu transaction cục bộ.
4. Hai lời gọi `persist()` đưa các entity vào persistence context; provider có thể phát SQL tại `persist`, `flush` hoặc `commit` tùy chiến lược sinh khóa và tình huống cụ thể.
5. Nếu `commit()` thành công, cả hai bản ghi được xác nhận. Nếu có lỗi khiến transaction không thể hoàn tất, ứng dụng rollback transaction còn hoạt động.
6. `em.close()` kết thúc entity manager; `emf.close()` kết thúc factory khi ứng dụng dừng.

**Không tạo `EntityManagerFactory` cho mỗi thao tác**: factory thường tốn chi phí khởi tạo và được tái sử dụng. Ngược lại, một `EntityManager` không được dùng tùy tiện đồng thời từ nhiều thread và thường chỉ phục vụ một đơn vị công việc.

### 3.4. Khi gặp lỗi: rollback và trạng thái entity

Giả sử hai `persist()` ở trên đã được gọi nhưng transaction sau đó thất bại. Các SQL có thể đã được gửi tới database, song **rollback sẽ hủy các thay đổi chưa commit** theo bảo đảm transaction của database. Không được suy luận rằng vì ID đã được sinh ra hoặc `flush()` đã chạy thì transaction đã hoàn tất.

Sau rollback, trạng thái của các object trong persistence context có thể không còn phản ánh chính xác database, đặc biệt khi đã thay đổi nhiều entity. Cách làm đơn giản, an toàn với resource-local là **đóng entity manager của đơn vị công việc thất bại**, rồi dùng một entity manager mới cho lần xử lý tiếp theo.

### 3.5. Transaction và thao tác đọc

Không phải mọi lần gọi `find()` hoặc truy vấn đọc đều buộc mã Java SE phải mở transaction theo cùng cách như thao tác ghi. Tuy nhiên, chỉ đọc ngoài transaction có thể cho kết quả chịu ảnh hưởng của autocommit, mức cô lập và hành vi provider/database; một chuỗi nhiều lần đọc cần ảnh chụp dữ liệu nhất quán thường vẫn nên có transaction rõ ràng.

Trong các ví dụ thực hành, một quy tắc dễ áp dụng là **mọi thao tác ghi đều chạy trong transaction**, còn các trường hợp đọc nhiều bước cần đánh giá yêu cầu nhất quán dữ liệu.

## 4. Giao dịch JTA: `JTA`

### 4.1. JTA quản lý những gì?

**JTA (Jakarta Transactions)** cung cấp API và cơ chế quản lý transaction ở cấp ứng dụng/container. Thay vì mỗi repository tự mở và đóng transaction, **transaction manager** xác định ranh giới và cho phép nhiều thành phần tham gia cùng transaction.

Với JPA, persistence unit có kiểu `JTA` sẽ cung cấp entity manager làm việc trong transaction được quản lý bên ngoài `EntityTransaction`. JPA provider tham gia transaction để đồng bộ các thay đổi theo thời điểm transaction đó hoàn tất.

```text
HTTP request / EJB invocation / service method
                |
                v
  Container mở hoặc tham gia JTA transaction
                |
       +--------+--------+
       |                 |
  Service A          Service B
       |                 |
  EntityManager      EntityManager
       |                 |
       +--------+--------+
                |
          JTA transaction
                |
      Transaction Manager
                |
      DataSource(s) / DB(s)
                |
           commit / rollback
```

JTA thường xuất hiện trong **Jakarta EE application server**. Spring cũng có thể quản lý transaction cho các service, nhưng annotation `@Transactional` của Spring không tự có nghĩa là JTA: Spring có thể dùng transaction manager cục bộ (`JpaTransactionManager`) hoặc transaction manager JTA, tùy cấu hình.

**JTA không mặc nhiên yêu cầu nhiều database.** Nó có thể điều phối transaction chỉ có một tài nguyên. Khi nhiều tài nguyên đủ điều kiện (ví dụ các XA resource) cùng tham gia, transaction manager có thể phối hợp commit phân tán theo cơ chế thích hợp, thường gồm **two-phase commit (2PC)**. Điều này phụ thuộc khả năng của resource, driver, data source và cấu hình container; chỉ dùng `transaction-type="JTA"` không bảo đảm mọi tài nguyên tùy ý đều rollback cùng nhau.

### 4.2. Cấu hình persistence unit JTA

Một persistence unit do Jakarta EE container quản lý có thể khai báo:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="ordersJtaPU"
                      transaction-type="JTA">
        <jta-data-source>java:comp/env/jdbc/OrdersDS</jta-data-source>
        <class>com.example.Invoice</class>
    </persistence-unit>
</persistence>
```

Trong đó:

- `transaction-type="JTA"` chỉ định rằng transaction được quản lý theo JTA.
- `<jta-data-source>` tham chiếu đến **DataSource** mà container đã cấu hình và có thể tham gia transaction JTA. Tên `java:comp/env/jdbc/OrdersDS` là ví dụ JNDI; môi trường thực tế phải ánh xạ và cung cấp data source tương ứng.
- Cấu hình connection pool, thông tin truy cập database và khả năng XA thường do server/container quản lý, thay vì nhúng trực tiếp các thuộc tính JDBC vào persistence unit.

JTA không phải lựa chọn mà mọi ứng dụng Java SE mặc nhiên có sẵn. Nếu muốn dùng JTA trong Java SE, ứng dụng phải bổ sung và tích hợp một transaction manager thích hợp.

### 4.3. Ví dụ: Jakarta EE điều khiển transaction của service

Trong Jakarta EE hỗ trợ Enterprise Beans, một `@Stateless` session bean mặc định có transaction do container quản lý. Có thể khai báo `REQUIRED` một cách tường minh:

```java
package com.example;

import jakarta.ejb.Stateless;
import jakarta.ejb.TransactionAttribute;
import jakarta.ejb.TransactionAttributeType;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.math.BigDecimal;

@Stateless
public class InvoiceService {
    @PersistenceContext(unitName = "ordersJtaPU")
    private EntityManager em;

    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public void createPair() {
        em.persist(new Invoice(
                "Khách A", new BigDecimal("120000")));

        em.persist(new Invoice(
                "Khách B", new BigDecimal("85000")));
    }
}
```

Khi client gọi `createPair()` **qua cơ chế quản lý của container**:

1. Nếu chưa có transaction, container mở transaction JTA mới trước khi gọi phương thức vì thuộc tính `REQUIRED`.
2. Entity manager do `@PersistenceContext` cung cấp tham gia transaction của lời gọi.
3. Các thay đổi được đồng bộ và transaction commit khi phương thức kết thúc thành công.
4. Nếu lỗi dẫn đến rollback (ví dụ một unchecked system exception theo quy tắc EJB mặc định), container đánh dấu hoặc thực hiện rollback cho transaction.

Trong phương thức service này, **không gọi `em.getTransaction().begin()`, `commit()` hay `em.close()`**. Entity manager được container quản lý và ranh giới transaction không nằm trong tay `EntityTransaction`.

Một lựa chọn khác của Jakarta EE là dùng CDI cùng `jakarta.transaction.Transactional` để transaction interceptor quản lý ranh giới:

```java
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.transaction.Transactional;

@ApplicationScoped
public class InvoiceApplicationService {
    @PersistenceContext(unitName = "ordersJtaPU")
    private EntityManager em;

    @Transactional(Transactional.TxType.REQUIRED)
    public void save(Invoice invoice) {
        em.persist(invoice);
    }
}
```

Cơ chế `@Transactional` này cần runtime hỗ trợ Jakarta Transactions interceptor và phương thức phải được gọi qua đối tượng do container quản lý. Không nên tạo đối tượng service bằng `new` rồi kỳ vọng interceptor tự chạy.

### 4.4. Transaction lan truyền qua nhiều lớp nghiệp vụ

Trong JTA, transaction có thể **lan truyền** qua nhiều lời gọi service/repository được quản lý cùng ngữ cảnh. Ví dụ `checkout()` gọi service lưu đơn hàng và service cập nhật tồn kho:

```text
CheckoutService.checkout()  [JTA transaction REQUIRED]
    |
    +-- OrderService.createOrder()
    |       +-- em.persist(order)
    |
    +-- InventoryService.decreaseStock()
            +-- em.find(stock)
            +-- stock.decrease(quantity)
    |
    +-- Thành công: commit cả phần đơn hàng và tồn kho
    +-- Thất bại: rollback các thao tác đã tham gia transaction
```

Điều kiện quan trọng: các thao tác đó **thực sự tham gia cùng một transaction**; chỉ việc đặt nhiều `@Transactional` hoặc nhiều `EntityManager` trong cùng ứng dụng không tự bảo đảm điều này nếu transaction mode, proxy/interceptor hoặc resource configuration không phù hợp.

Trong Jakarta Transactions, các kiểu transaction thường gặp gồm:

| `TxType` với `jakarta.transaction.Transactional` | Ý nghĩa |
|---|---|
| `REQUIRED` | Tham gia transaction đang có; nếu chưa có thì mở mới. |
| `REQUIRES_NEW` | Tạm ngưng transaction hiện có (nếu có), tạo transaction mới cho phương thức rồi khôi phục transaction trước đó. |
| `MANDATORY` | Bắt buộc phải có transaction hiện tại; nếu không có thì lỗi. |
| `SUPPORTS` | Có transaction thì tham gia; không có thì chạy không có transaction. |
| `NOT_SUPPORTED` | Chạy không có transaction; tạm ngưng transaction hiện tại nếu có. |
| `NEVER` | Chỉ chạy khi không có transaction; có transaction hiện tại thì lỗi. |

Các tên gần giống cũng xuất hiện trong EJB transaction attributes và Spring transaction propagation, nhưng annotation, mặc định và quy tắc rollback **không hoàn toàn giống nhau**. Khi dùng một framework cụ thể, cần đọc semantics của chính framework đó.

### 4.5. Quy tắc rollback trong JTA

Transaction manager không tự đoán mọi lỗi nghiệp vụ đều cần rollback. Tùy API:

- Với **`jakarta.transaction.Transactional`**, mặc định `RuntimeException` và các lớp con thường đánh dấu rollback; checked exception mặc định không tự kích hoạt rollback, trừ khi cấu hình `rollbackOn` hoặc đánh dấu rollback bằng API thích hợp.
- Với **EJB container-managed transaction**, system exception thường dẫn đến rollback; application exception tuân theo quy tắc của `@ApplicationException` và thuộc tính `rollback`.
- Khi muốn hủy transaction vì một điều kiện nghiệp vụ không được biểu diễn bằng exception thích hợp, ứng dụng có thể dùng API do container cung cấp để **đánh dấu transaction rollback-only**, như `EJBContext.setRollbackOnly()` trong EJB hoặc `TransactionSynchronizationRegistry.setRollbackOnly()` trong môi trường tương ứng.

Không được trộn quy tắc rollback của EJB, Jakarta Transactions interceptor và Spring thành một mặc định chung.

## 5. So sánh `RESOURCE_LOCAL` và `JTA`

| Tiêu chí | Resource-local | JTA |
|---|---|---|
| Ai quyết định bắt đầu/kết thúc? | Mã ứng dụng gọi `EntityTransaction.begin()/commit()/rollback()`. | Transaction manager; ranh giới thường khai báo bằng interceptor/EJB hoặc API JTA. |
| Cấu hình JPA | `transaction-type="RESOURCE_LOCAL"`. | `transaction-type="JTA"`. |
| API transaction ở tầng JPA | `em.getTransaction()`. | Không quản lý bằng `em.getTransaction()`. |
| Môi trường phổ biến | Java SE, batch nhỏ, công cụ độc lập, ứng dụng muốn tự quản lý transaction. | Jakarta EE, hệ thống tích hợp transaction manager JTA. |
| EntityManager | Thường do ứng dụng tạo bằng `emf.createEntityManager()` và tự đóng. | Thường được container cấp bằng `@PersistenceContext` và quản lý vòng đời. |
| Phạm vi tài nguyên | Thường một tài nguyên dữ liệu gắn với entity manager. | Có khả năng điều phối nhiều tài nguyên tương thích nếu được cấu hình đúng. |
| Tổ chức ranh giới nghiệp vụ | Đặt `try/catch` và `begin/commit/rollback` tại đơn vị công việc. | Đặt transaction boundary tại service/container; hỗ trợ transaction propagation. |
| Độ phức tạp vận hành | Ít hạ tầng hơn, nhưng mã phải quản lý transaction và tài nguyên. | Có hạ tầng transaction manager, yêu cầu cấu hình data source/enlistment chính xác. |
| Lựa chọn thích hợp | Tác vụ đơn giản với một database và chủ động kiểm soát vòng đời. | Nhiều service/cấu phần cùng tham gia một transaction hoặc cần cơ chế transaction do container điều phối. |

**Không có quy tắc “cứ dùng Spring là JTA”.** Spring Data JPA/Spring Framework có thể mở transaction bằng `JpaTransactionManager` cho một persistence unit/database. Chỉ khi cấu hình transaction manager JTA tương ứng, transaction đó mới do JTA điều phối. Ngược lại, một application server Jakarta EE có thể cung cấp JTA ngay cả khi mã nghiệp vụ không gọi trực tiếp API JTA nào.

## 6. Persistence context liên quan đến transaction như thế nào?

Vì hai khái niệm dễ bị đánh đồng, nên cần xem sự khác nhau giữa persistence context và transaction trong hai cơ chế.

### 6.1. Resource-local và application-managed entity manager

Với `EntityManager` do ứng dụng tạo từ `EntityManagerFactory`:

```text
em = emf.createEntityManager()
|
+-- Persistence context của em bắt đầu tồn tại
|
+-- tx.begin()
|     +-- persist/find/modify entity
|     +-- flush (có thể xảy ra tại các thời điểm phù hợp)
+-- tx.commit()
|
+-- Có thể bắt đầu transaction khác với em còn mở
|
+-- em.close() -> kết thúc persistence context
```

Một `EntityManager` có thể tồn tại qua nhiều transaction. Dù vậy, để quản lý tài nguyên và lỗi đơn giản, nhiều ứng dụng sử dụng **một entity manager cho một đơn vị công việc**. Mỗi lần mở một entity manager khác nhau thường có một persistence context khác nhau.

### 6.2. JTA và transaction-scoped persistence context

Trong Jakarta EE, `@PersistenceContext` mặc định cung cấp **transaction-scoped persistence context**. Context gắn với JTA transaction hiện hành, các thành phần được container quản lý có thể phối hợp làm việc trong cùng transaction, và context kết thúc theo vòng đời transaction.

```text
Container bắt đầu JTA transaction T1
    |
    +-- Service A dùng EntityManager / persistence context tham gia T1
    |
    +-- Service B tham gia T1, làm việc với persistence context theo quy tắc JPA
    |
Container commit hoặc rollback T1
    |
Transaction-scoped persistence context kết thúc
```

JPA còn hỗ trợ **extended persistence context** trong những mô hình container-managed thích hợp, chẳng hạn stateful session bean. Extended context có thể tồn tại qua nhiều transaction; đây là lựa chọn vòng đời persistence context, **không phải một transaction kéo dài qua nhiều request**. Cần thiết kế cẩn thận để tránh giữ nhiều entity managed và dữ liệu cũ quá lâu.

Ngoài ra có loại **unsynchronized persistence context** (trong môi trường/API hỗ trợ) không tự tham gia transaction chỉ vì transaction đang hoạt động. Khi cần đồng bộ thay đổi vào JTA transaction, ứng dụng có thể phải gọi `em.joinTransaction()`. Với synchronized transaction-scoped persistence context thông dụng, container/provider thường thực hiện việc tham gia transaction phù hợp, không cần gọi thủ công.

### 6.3. Khi nào SQL thực sự chạy?

Xét đoạn mã:

```java
em.persist(new Invoice("Khách C", new BigDecimal("95000")));
em.flush();
// Một lỗi nghiệp vụ xảy ra ở bước tiếp theo.
// Transaction được rollback.
```

Sau `flush()`, câu lệnh `INSERT` có thể đã được thực thi và database có thể đã cấp ID, nhưng rollback sẽ hủy tác động của transaction chưa commit. `flush` không thay thế `commit` và cũng không bảo đảm transaction chắc chắn có thể commit; lỗi ràng buộc hoặc lỗi khác vẫn có thể phát sinh.

Ngay cả khi không gọi `flush()`, provider cũng có thể tự flush trước truy vấn hoặc khi commit tùy chế độ flush. Phân tích transaction cần dựa vào **ranh giới commit/rollback**, không dựa vào số lần gọi `persist()` hoặc thời điểm log SQL xuất hiện.

## 7. Những nhầm lẫn và lỗi triển khai thường gặp

### 7.1. Dùng `getTransaction()` trên JTA EntityManager

```java
// Không phù hợp với entity manager kiểu JTA:
EntityTransaction tx = em.getTransaction();
tx.begin();
```

`getTransaction()` chỉ dùng cho resource-local entity manager. Gọi trên JTA entity manager sẽ gây lỗi `IllegalStateException` theo hợp đồng API. Hãy để container/JTA manager điều phối transaction hoặc sử dụng API JTA phù hợp với môi trường.

### 7.2. Quên rollback khi dùng resource-local

```java
tx.begin();
em.persist(entity);
tx.commit();
```

Đoạn mã trên không xử lý ngoại lệ. Nếu thao tác ghi hoặc `commit()` thất bại, transaction có thể vẫn hoạt động hoặc ở trạng thái cần xử lý. Cần bao quanh bằng `try/catch`, kiểm tra `tx.isActive()` rồi rollback, và đóng `EntityManager` bằng `finally` như ví dụ ở phần 3.

### 7.3. Đóng EntityManager do container quản lý

Trong Jakarta EE, `@PersistenceContext` thường inject entity manager do container quản lý. Không nên tự gọi `em.close()` trên đối tượng đó; vòng đời và sự tham gia transaction của nó do container xử lý. Ngược lại, với entity manager do chính mã Java SE tạo, ứng dụng có trách nhiệm đóng.

### 7.4. Dùng chung một EntityManager giữa nhiều thread

`EntityManagerFactory` có thể chia sẻ trong ứng dụng. **`EntityManager` không được bảo đảm thread-safe**, nên không sử dụng một instance làm biến singleton chung cho các request song song. Container thường cung cấp cơ chế tham chiếu/proxy để các lời gọi dùng context đúng phạm vi.

### 7.5. Nhầm một transaction JTA với mọi hệ thống bên ngoài

JTA có thể điều phối nhiều resource được enlist đúng cách, nhưng **không tự biến lời gọi REST/HTTP đến dịch vụ ngoài thành thao tác có thể rollback**. Nếu transaction database commit rồi service ngoài thất bại, cần thiết kế xử lý như outbox, idempotency hoặc saga, tùy yêu cầu nghiệp vụ.

Với hai database, phải kiểm tra cả khả năng XA, transaction manager, cấu hình datasource và enlistment. Hai kết nối JDBC độc lập được tạo tùy ý không tự nhiên nằm trong một transaction phân tán chỉ vì ứng dụng dùng JPA.

### 7.6. Nhầm JPA entity lifecycle với transaction lifecycle

Sau rollback, đối tượng Java vẫn có thể đang giữ giá trị mới dù thay đổi database bị hủy. Tương tự, entity chuyển sang `detached` khi đóng persistence context không có nghĩa database đã rollback. Hai vòng đời liên quan nhưng không đồng nhất.

### 7.7. Cho rằng transaction tự giải quyết cạnh tranh dữ liệu

Cả RESOURCE_LOCAL và JTA đều phụ thuộc mức cô lập và khả năng khóa của database. Ví dụ, hai transaction cùng đọc một số dư hoặc số lượng tồn kho có thể gây **lost update** nếu không kiểm soát cạnh tranh. Các biện pháp JPA có thể gồm `@Version` để **optimistic locking** hoặc `LockModeType.PESSIMISTIC_WRITE` khi phù hợp; chúng giải quyết bài toán đồng thời, không thay thế lựa chọn transaction manager.

### 7.8. Dùng transaction quá dài

Một transaction dài giữ nhiều khóa, kết nối và tài nguyên hơn cần thiết, tăng rủi ro lock contention hoặc timeout. Nên đặt ranh giới transaction quanh **đơn vị nghiệp vụ cần tính nguyên tử**, tránh giữ transaction mở trong lúc chờ người dùng nhập liệu hoặc gọi mạng không cần thiết.

## 8. Chọn cơ chế và tổ chức lớp ứng dụng

Một cách quyết định thực tế:

- **Ứng dụng Java SE làm việc với một database:** `RESOURCE_LOCAL` thường đủ và dễ hiểu. Tập trung mã bắt đầu/commit/rollback transaction ở service hoặc một lớp điều phối đơn vị công việc để tránh repository nào cũng tự commit riêng.
- **Ứng dụng Jakarta EE với nhiều bean/service cần chung transaction:** `JTA` và container-managed transaction thường tự nhiên hơn. Dùng `@TransactionAttribute` hoặc `jakarta.transaction.Transactional` theo loại thành phần đang chạy.
- **Ứng dụng Spring dùng JPA:** xác định transaction manager thực tế (`JpaTransactionManager` hay `JtaTransactionManager`), thay vì suy luận từ `@Transactional`. Khi chỉ có một database, transaction manager cục bộ có thể là lựa chọn hợp lý; nhiều resource cần đánh giá hạ tầng và yêu cầu bảo đảm nhất quán.
- **Nhiều database/resource yêu cầu atomic commit:** đánh giá JTA, XA và sự hỗ trợ của mọi resource liên quan; cân nhắc cả chi phí, timeout và tình huống lỗi phân tán.

Ví dụ với hai repository, nếu mỗi repository dùng resource-local và tự commit trước khi trả về:

```text
CheckoutService
  +-- orderRepository.saveAndCommit()  -> commit thành công
  +-- stockRepository.saveAndCommit()  -> thất bại
```

Không còn cách rollback thao tác đã commit ở repository thứ nhất như một transaction đơn lẻ. Để đạt tính nguyên tử trong **cùng một database**, nên có một transaction chung bao quanh cả hai thao tác (có thể là resource-local được service điều phối hoặc transaction do framework quản lý). Khi sử dụng JTA với nhiều resource, các resource cũng phải tham gia chung transaction và được cấu hình đúng.

## 9. Câu hỏi tự kiểm tra

**1. `RESOURCE_LOCAL` có nghĩa là JPA không dùng database transaction?**  
Không. Nó vẫn sử dụng transaction của tài nguyên database; chỉ khác ở việc ứng dụng trực tiếp gọi `EntityTransaction` để bắt đầu và kết thúc.

**2. Có thể gọi `em.getTransaction().commit()` trên entity manager được `@PersistenceContext` inject trong JTA không?**  
Không. Với JTA entity manager, ranh giới transaction do container/JTA manager quản lý; `getTransaction()` không dành cho trường hợp này.

**3. Hai phương thức service cùng đánh dấu `@Transactional` có chắc dùng chung transaction không?**  
Không thể kết luận chỉ từ annotation. Cần xem đó là annotation của Jakarta Transactions hay Spring, kiểu propagation, cách gọi qua interceptor/proxy, cấu hình manager và việc resource tham gia transaction.

**4. `flush()` đã chạy thì rollback còn hiệu lực?**  
Có. Flush đồng bộ SQL nhưng chưa commit transaction; database vẫn có thể rollback những thay đổi chưa được xác nhận.

**5. Dùng JTA có bắt buộc cấu hình XA không?**  
Không phải mọi transaction JTA đều cần XA hoặc 2PC, nhất là khi chỉ có một resource. Nhưng khi cần atomic commit trên nhiều resource, phải xác định rõ khả năng tham gia distributed transaction và cấu hình thích hợp.

**6. Có thể tiếp tục sửa entity sau khi transaction kết thúc không?**  
Phụ thuộc vào entity còn `managed` trong persistence context hay đã `detached`. Với transaction-scoped persistence context của container, context thường kết thúc cùng transaction; thay đổi object sau đó không được JPA tự theo dõi. Với application-managed entity manager còn mở, context có thể tồn tại qua nhiều transaction nhưng cần quản lý nhất quán trạng thái và tài nguyên.

## 10. Ghi nhớ mối quan hệ trong kiến trúc JPA

- **JPA provider và `EntityManager`** quản lý entity, persistence context, SQL phát sinh và việc đồng bộ thay đổi.
- **RESOURCE_LOCAL** đặt quyền điều khiển transaction vào mã ứng dụng qua `EntityTransaction`.
- **JTA** đặt quyền điều khiển transaction vào transaction manager và có thể hỗ trợ nhiều thành phần cùng tham gia một transaction.
- **`commit` và `rollback`** quyết định số phận transaction; **`flush`** chỉ đồng bộ thay đổi và không thay thế commit.
- **Một transaction cho một đơn vị công việc cần nguyên tử**, cùng với vòng đời entity manager, ranh giới service và cấu hình tài nguyên đúng đắn, là cơ sở để ứng dụng JPA lưu dữ liệu tin cậy.
