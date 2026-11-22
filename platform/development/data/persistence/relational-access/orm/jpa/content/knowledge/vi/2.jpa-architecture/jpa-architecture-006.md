# Phân biệt cơ chế do ứng dụng quản lý và do môi trường quản lý trong JPA

Khi sử dụng **Jakarta Persistence (JPA)**, mã Java không chỉ cần biết cách lưu một đối tượng bằng `persist()` hoặc đọc bằng `find()`. Ứng dụng còn phải xác định **ai tạo và quản lý `EntityManager`, ai quyết định thời gian tồn tại của persistence context, ai mở và kết thúc giao dịch**. Đây là những quyết định kiến trúc ảnh hưởng trực tiếp đến cách thiết kế tầng truy cập dữ liệu, xử lý lỗi và quản lý tài nguyên.

Hai cách thường được nhắc đến là:

- **Application-managed** (*do ứng dụng quản lý*): mã ứng dụng chủ động tạo `EntityManager` từ `EntityManagerFactory`, giữ tham chiếu và đóng nó khi hoàn thành công việc.
- **Container-managed** (*do môi trường/container quản lý*): một môi trường thực thi hỗ trợ Jakarta Persistence, điển hình là **Jakarta EE container**, cấp `EntityManager` cho thành phần ứng dụng và quản lý ngữ cảnh lưu trữ theo những quy tắc đã định.

Sự phân biệt này chủ yếu nói về **quyền sở hữu vòng đời `EntityManager` và persistence context**. Nó liên quan đến giao dịch nhưng **không đồng nghĩa** với hai kiểu giao dịch `RESOURCE_LOCAL` và JTA. Để không nhầm lẫn, cần xét từng khía cạnh riêng.

## 1. Ôn lại những thành phần trong kiến trúc JPA

| Thành phần | Ý nghĩa | Đặc điểm quan trọng |
| --- | --- | --- |
| `Entity` | Đối tượng nghiệp vụ được ánh xạ với dữ liệu quan hệ. | Ví dụ `Customer`, `Invoice`, `Order`. |
| `EntityManagerFactory` | Nhà máy tạo `EntityManager` cho một persistence unit. | Thường tương đối tốn chi phí khởi tạo, được tái sử dụng; có thể dùng đồng thời theo hợp đồng API. |
| `EntityManager` | API làm việc với thực thể: `persist`, `find`, `merge`, `remove`, `createQuery`... | Không an toàn để chia sẻ tùy tiện giữa nhiều luồng. |
| **Persistence context** | Tập các thực thể đang được quản lý cùng cơ chế định danh và theo dõi thay đổi. | Một thực thể có cùng loại và cùng định danh thường tương ứng một đối tượng được quản lý trong cùng context. |
| **Transaction** | Phạm vi công việc được cam kết hoặc hoàn tác tại database. | Có thể được quản lý bằng `EntityTransaction`, JTA hoặc tầng giao dịch của framework. |
| **Persistence unit** | Cấu hình tập thực thể, provider, nguồn dữ liệu và chiến lược giao dịch. | Được định danh bằng tên, chẳng hạn `shopPU`. |

Quan hệ khái quát giữa các thành phần:

```text
Ứng dụng Java
    |
    | dùng EntityManager
    v
EntityManager  ----->  Persistence context
    |                       |
    |                       +-- Customer#10 (managed)
    |                       +-- Order#25    (managed)
    |
    +-- ORM provider (ví dụ Hibernate)
              |
              v
         JDBC / DataSource
              |
              v
       Cơ sở dữ liệu quan hệ

EntityManagerFactory tạo EntityManager.
Giao dịch quy định khi nào thay đổi được commit/rollback.
```

Một *persistence context* không phải là một kết nối JDBC. Nó quản lý trạng thái đối tượng và có thể sử dụng tài nguyên database vào các thời điểm thích hợp. **`flush()` đồng bộ những thay đổi đang chờ xuống database, còn `commit()` kết thúc giao dịch thành công**; hai thao tác không có cùng ý nghĩa.

## 2. Cơ chế do ứng dụng quản lý (application-managed)

### 2.1. Ai kiểm soát vòng đời?

Với cách này, mã ứng dụng trực tiếp gọi `EntityManagerFactory.createEntityManager()` và nhận một `EntityManager` cụ thể. Ứng dụng chịu trách nhiệm:

1. Tạo hoặc nhận `EntityManagerFactory` khi khởi động thành phần thích hợp.
2. Tạo `EntityManager` khi bắt đầu một đơn vị công việc.
3. Sử dụng `EntityManager` để đọc, tạo, sửa hoặc xóa thực thể.
4. Đảm bảo giao dịch được xử lý đúng theo loại persistence unit.
5. Gọi `close()` trên `EntityManager` dù công việc thành công hay xảy ra lỗi.
6. Đóng `EntityManagerFactory` khi ứng dụng hoặc thành phần sở hữu nó kết thúc.

Trong một ứng dụng Java SE đơn giản, đây là cách sử dụng phổ biến:

```text
Khởi động ứng dụng
    |
    +-- Persistence.createEntityManagerFactory("shopLocalPU")
              |
              +-- createEntityManager()  [bắt đầu công việc A]
              |       |
              |       +-- begin()
              |       +-- persist/find/update...
              |       +-- commit() hoặc rollback()
              |       +-- close()
              |
              +-- createEntityManager()  [bắt đầu công việc B]
              |       +-- ...
              |       +-- close()
              |
              +-- close()               [khi ngừng ứng dụng]
```

Thông thường, mỗi yêu cầu hoặc đơn vị công việc cần một `EntityManager` riêng. Không nên tạo một `EntityManager` dùng chung cho nhiều request hay nhiều luồng: JPA không bảo đảm `EntityManager` an toàn cho truy cập đồng thời.

### 2.2. Ví dụ đầy đủ với giao dịch `RESOURCE_LOCAL`

Giả sử ứng dụng quản lý khách hàng, có thực thể:

```java
package com.example.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Customer() {
        // JPA cần constructor không tham số với quyền truy cập phù hợp.
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Nếu sử dụng PostgreSQL, database có thể có bảng:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);
```

Một `persistence.xml` minh họa **persistence unit thuộc loại `RESOURCE_LOCAL`** (đặt tại `META-INF/persistence.xml`) như sau:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="shopLocalPU"
                      transaction-type="RESOURCE_LOCAL">
        <class>com.example.domain.Customer</class>
        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.postgresql.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:postgresql://localhost:5432/shop"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="shop_app"/>
        </properties>
    </persistence-unit>
</persistence>
```

Đây là cấu hình minh họa: cần có JDBC driver, JPA provider và thông tin xác thực phù hợp với môi trường triển khai. Mật khẩu nên được cung cấp qua cấu hình an toàn bên ngoài mã nguồn. Có thể cần khai báo provider hoặc các thuộc tính khác tùy môi trường chạy.

Đối với đơn vị công việc tạo khách hàng, ứng dụng trực tiếp quản lý `EntityManager` và `EntityTransaction`:

```java
package com.example.persistence;

import com.example.domain.Customer;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public final class CustomerWriter {
    private final EntityManagerFactory entityManagerFactory;

    public CustomerWriter(EntityManagerFactory entityManagerFactory) {
        this.entityManagerFactory = entityManagerFactory;
    }

    public void createCustomer(String name) {
        EntityManager entityManager =
                entityManagerFactory.createEntityManager();

        try {
            EntityTransaction transaction = entityManager.getTransaction();

            try {
                transaction.begin();
                entityManager.persist(new Customer(name));
                transaction.commit();
            } catch (RuntimeException exception) {
                if (transaction.isActive()) {
                    transaction.rollback();
                }
                throw exception;
            }
        } finally {
            entityManager.close();
        }
    }
}
```

Ở thời điểm khởi động/kết thúc ứng dụng, mã sở hữu factory có thể viết:

```java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

EntityManagerFactory factory =
        Persistence.createEntityManagerFactory("shopLocalPU");

try {
    new CustomerWriter(factory).createCustomer("Lan");
} finally {
    factory.close();
}
```

Ví dụ trên sử dụng `jakarta.persistence.*` của Jakarta Persistence phiên bản hiện đại. Ứng dụng thực tế có thể tích hợp transaction handling, cấu hình DataSource, logging và quản lý lifecycle ở tầng framework hoặc infrastructure riêng.

**Vì sao phải đóng `EntityManager`?** Việc đóng kết thúc persistence context do ứng dụng sở hữu và giải phóng những tài nguyên liên quan. Nếu bỏ qua, tài nguyên có thể bị giữ không cần thiết và vòng đời thực thể trở nên khó kiểm soát. `EntityManagerFactory` thường được duy trì lâu hơn và tái sử dụng cho nhiều đơn vị công việc.

### 2.3. Context tồn tại bao lâu?

Với application-managed `EntityManager`, persistence context thông thường sống cùng `EntityManager` cho đến khi nó bị đóng. Việc `commit()` một giao dịch **không tự động đóng** `EntityManager` do ứng dụng tạo.

```text
EntityManager:    |------------- mở -------------------| close
Giao dịch A:       | begin -> commit |
Giao dịch B:                          | begin -> commit |
Persistence context: có thể tiếp tục giữ managed entity trong suốt đời EntityManager
```

Do đó, trong những tác vụ chạy lâu hoặc xử lý nhiều bản ghi, ứng dụng phải cân nhắc thời gian sống của context, bộ nhớ dùng cho các thực thể đang được quản lý, và thời điểm `clear()`/`detach()` nếu cần. Context kéo dài qua nhiều giao dịch có ý nghĩa khác với việc mỗi giao dịch tạo một `EntityManager` mới.

## 3. Cơ chế do môi trường quản lý (container-managed)

### 3.1. Container chịu trách nhiệm gì?

Trong môi trường **Jakarta EE** có hỗ trợ Jakarta Persistence, một thành phần ứng dụng có thể khai báo rằng nó cần một `EntityManager` thông qua `@PersistenceContext`. Container cung cấp một tham chiếu phù hợp và quản lý các persistence context bên dưới.

Khi dùng persistence context loại **transaction-scoped** (mặc định), container thường gắn một persistence context với giao dịch JTA hiện hành. Trong những lần gọi thuộc cùng giao dịch, các hoạt động persistence có thể tham gia cùng ngữ cảnh. Khi giao dịch kết thúc, context của giao dịch đó kết thúc và những thực thể tương ứng không còn được quản lý bởi context ấy.

```text
Jakarta EE container
    |
    +-- Quản lý transaction (JTA)
    +-- Cung cấp EntityManager qua @PersistenceContext
    +-- Gắn persistence context với transaction khi thích hợp
    +-- Hoàn tất/giải phóng context theo vòng đời quy định
    |
    v
@Stateless CustomerService
    |
    +-- entityManager.persist(customer)
    |
    v
ORM provider -> DataSource -> Database
```

Thành phần ứng dụng **không tự gọi `close()`** trên container-managed `EntityManager`. Tài nguyên và ngữ cảnh do container quản lý; cố gắng đóng đối tượng được container cấp là sử dụng API sai vòng đời.

### 3.2. Ví dụ với Jakarta EE và `@PersistenceContext`

Giả sử persistence unit được khai báo sử dụng JTA và nguồn dữ liệu do môi trường cung cấp:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="shopJtaPU" transaction-type="JTA">
        <jta-data-source>java:comp/env/jdbc/ShopDS</jta-data-source>
        <class>com.example.domain.Customer</class>
    </persistence-unit>
</persistence>
```

Tên `java:comp/env/jdbc/ShopDS` chỉ minh họa một DataSource được cấu hình trước; cách khai báo và tên JNDI phụ thuộc máy chủ Jakarta EE. Trong mã nghiệp vụ, một session bean có thể dùng:

```java
package com.example.service;

import com.example.domain.Customer;
import jakarta.ejb.Stateless;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

@Stateless
public class CustomerService {

    @PersistenceContext(unitName = "shopJtaPU")
    private EntityManager entityManager;

    public void createCustomer(String name) {
        entityManager.persist(new Customer(name));
    }
}
```

Với EJB `@Stateless`, phương thức nghiệp vụ mặc định sử dụng **container-managed transaction**, có thuộc tính giao dịch mặc định tương đương `REQUIRED` nếu không cấu hình khác. Khi gọi `createCustomer()` thông qua EJB container:

1. Container sử dụng giao dịch hiện hành hoặc tạo giao dịch mới theo thuộc tính giao dịch.
2. `EntityManager` được cấp qua `@PersistenceContext` hoạt động trong bối cảnh giao dịch phù hợp.
3. Lệnh `persist()` chuyển đối tượng mới sang trạng thái được quản lý; SQL chèn thực tế được thực thi theo cơ chế flush và chiến lược cấp khóa.
4. Khi phương thức kết thúc thành công, giao dịch do container khởi tạo được commit; nếu xảy ra lỗi làm giao dịch phải rollback, container xử lý theo quy tắc giao dịch EJB.

Không có `entityManager.getTransaction().begin()`, `commit()` hay `entityManager.close()` trong phương thức. **Đó là kết quả của các trách nhiệm đã được giao cho môi trường**, không có nghĩa mọi hoạt động persistence tự động an toàn nếu thiết kế giao dịch sai. Nếu một phương thức được gọi bên ngoài transaction và không có transaction phù hợp, thao tác ghi có thể bị từ chối hoặc chưa được đồng bộ như mong đợi.

### 3.3. Transaction-scoped và extended persistence context

Container-managed không chỉ có một kiểu thời gian tồn tại của persistence context. Jakarta Persistence phân biệt hai dạng chính:

| Loại | Khai báo | Vòng đời | Trường hợp điển hình |
| --- | --- | --- | --- |
| **Transaction-scoped** | `@PersistenceContext(type = PersistenceContextType.TRANSACTION)`; đây là mặc định | Ngữ cảnh gắn với giao dịch JTA, kết thúc cùng giao dịch. | Yêu cầu nghiệp vụ độc lập, stateless service. |
| **Extended** | `@PersistenceContext(type = PersistenceContextType.EXTENDED)` | Ngữ cảnh tồn tại cùng thành phần được phép sở hữu extended context, điển hình stateful session bean; có thể đi qua nhiều giao dịch. | Quy trình hội thoại nhiều bước cần giữ trạng thái thực thể. |

Ví dụ một stateful session bean có thể khai báo:

```java
import jakarta.ejb.Stateful;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.PersistenceContextType;

@Stateful
public class DraftOrderWorkflow {
    @PersistenceContext(
        unitName = "shopJtaPU",
        type = PersistenceContextType.EXTENDED
    )
    private EntityManager entityManager;

    // Các phương thức của workflow sử dụng context kéo dài.
}
```

Extended persistence context cần được sử dụng có chủ đích vì nó giữ thực thể được quản lý qua nhiều bước và có nguy cơ gây tiêu thụ bộ nhớ, trạng thái cũ hoặc xung đột cập nhật. Nó **không làm một giao dịch kéo dài qua nhiều yêu cầu**: giao dịch vẫn có điểm bắt đầu và kết thúc riêng. Các thay đổi chỉ được đồng bộ khi context tham gia một giao dịch phù hợp theo quy tắc JPA.

## 4. Bảng so sánh hai cơ chế

| Tiêu chí | Application-managed | Container-managed (Jakarta EE) |
| --- | --- | --- |
| Nhận `EntityManager` | Mã gọi `entityManagerFactory.createEntityManager()`. | Container cấp qua `@PersistenceContext`. |
| Ai sở hữu vòng đời? | Ứng dụng. | Container. |
| Đóng `EntityManager` | Ứng dụng gọi `close()` đúng thời điểm. | Ứng dụng không đóng đối tượng được container cấp. |
| Persistence context | Thường tồn tại theo `EntityManager` do ứng dụng tạo. | Thường theo giao dịch; cũng có kiểu extended. |
| Cấu hình phổ biến | Java SE; `RESOURCE_LOCAL` hoặc một trường hợp JTA có chủ đích. | Jakarta EE dùng JTA và DataSource do môi trường quản lý. |
| Kiểm soát giao dịch | Với `RESOURCE_LOCAL`, dùng `EntityTransaction`; với JTA, dùng cơ chế JTA phù hợp. | Thường tích hợp container-managed JTA transaction, có thể được định nghĩa bằng thuộc tính giao dịch của EJB. |
| Mã nghiệp vụ | Nhiều thao tác về cấp phát/giải phóng tài nguyên hơn. | Tập trung hơn vào thao tác nghiệp vụ. |
| Rủi ro nếu dùng sai | Quên đóng `EntityManager`, chia sẻ giữa các luồng, quên rollback. | Nhầm vòng đời context, gọi API giao dịch/đóng không phù hợp, hiểu sai ranh giới giao dịch. |
| Lựa chọn thường gặp | Chương trình Java SE độc lập, tác vụ CLI hoặc ứng dụng cần kiểm soát cụ thể. | Dịch vụ chạy trong Jakarta EE container. |

Lưu ý rằng các dòng trong bảng nói về **kiểu quản lý thực thể** và các kết hợp thường gặp, không phải quy tắc buộc mọi ứng dụng-managed `EntityManager` đều phải dùng `RESOURCE_LOCAL`.

## 5. Phân biệt ba quyết định dễ bị gộp làm một

Trong kiến trúc JPA, có ít nhất ba câu hỏi độc lập:

**Câu hỏi 1 — Ai tạo và đóng `EntityManager`?**

- Mã ứng dụng gọi `createEntityManager()` → **application-managed EntityManager**.
- Môi trường cung cấp thông qua `@PersistenceContext` → **container-managed EntityManager**.

**Câu hỏi 2 — Ai điều phối transaction?**

- `RESOURCE_LOCAL` → mã sử dụng `EntityManager.getTransaction()` và `EntityTransaction` để `begin`, `commit`, `rollback`.
- JTA → giao dịch được điều phối thông qua JTA transaction manager; container hoặc tầng hạ tầng có thể mở/kết thúc giao dịch theo quy tắc riêng.

**Câu hỏi 3 — Persistence context sống đến khi nào?**

- Application-managed context thường theo thời gian sống của `EntityManager` do ứng dụng tạo.
- Container-managed **transaction-scoped** context theo giao dịch.
- Container-managed **extended** context có thể tồn tại qua nhiều giao dịch trong thành phần có vòng đời hỗ trợ, chẳng hạn stateful EJB.

Nhờ tách ba câu hỏi này, có thể hiểu một tình huống ít gặp nhưng hợp lệ: **ứng dụng tự tạo `EntityManager` từ `EntityManagerFactory` được inject trong Jakarta EE và dùng persistence unit JTA**. Khi đó `EntityManager` vẫn là application-managed về vòng đời, trong khi transaction thuộc JTA.

Ví dụ về mặt API:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.PersistenceUnit;

public class ManualEntityManagerExample {
    @PersistenceUnit(unitName = "shopJtaPU")
    private EntityManagerFactory entityManagerFactory;

    public void executeInsideManagedTransaction() {
        EntityManager entityManager =
                entityManagerFactory.createEntityManager();
        try {
            // Dùng entityManager trong giao dịch JTA hiện hành.
            // Khi cần, có thể dùng joinTransaction() theo quy tắc JPA.
        } finally {
            entityManager.close();
        }
    }
}
```

Ví dụ giả định mã thực thi trong một thành phần mà môi trường hỗ trợ tiêm `@PersistenceUnit`. Muốn có hành vi giao dịch cụ thể, thành phần vẫn phải được gọi trong JTA transaction phù hợp. Với JTA, **không dùng `entityManager.getTransaction()` để trực tiếp điều khiển transaction** như trong ví dụ `RESOURCE_LOCAL`.

Một phân biệt khác: **container-managed persistence context** và **container-managed transaction** không phải hai tên cho cùng một đối tượng. Cơ chế đầu tiên quản lý trạng thái của entity; cơ chế thứ hai quản lý ranh giới commit/rollback của công việc database.

## 6. Spring và Spring Data JPA nằm ở đâu?

Trong ứng dụng Spring hoặc Spring Boot, việc quản lý thường do **Spring framework** thực hiện thay cho mã nghiệp vụ. Một service có thể trông tương tự ví dụ Jakarta EE:

```java
package com.example.service;

import com.example.domain.Customer;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void createCustomer(String name) {
        entityManager.persist(new Customer(name));
    }
}
```

Trong cấu hình Spring thông thường, `@PersistenceContext` đưa vào một tham chiếu/proxy do Spring quản lý để truy cập `EntityManager` thích hợp với ngữ cảnh giao dịch. `@Transactional` của Spring xác định ranh giới giao dịch khi phương thức được gọi qua cơ chế transaction interception; giao dịch có thể do `JpaTransactionManager` hoặc một transaction manager khác phụ trách, tùy cấu hình.

Điều đó đem lại trải nghiệm **môi trường quản lý tài nguyên** cho mã nghiệp vụ. Tuy nhiên, Spring không mặc nhiên là một Jakarta EE container và **`@Transactional` của Spring không đồng nghĩa hệ thống đang dùng JTA**. Phần lớn ứng dụng Spring Boot đơn database dùng giao dịch cục bộ do Spring quản lý thông qua JPA. Khi dùng `JpaRepository`, các phương thức repository tiếp tục làm việc trên nền `EntityManager` và cơ chế transaction đã cấu hình.

Trong ví dụ Spring này, không nên tự đóng `entityManager` được inject, cũng không nên gọi `getTransaction().begin()` bên trong phương thức đang được quản lý bằng `@Transactional`.

Một lưu ý thực hành: `@Transactional` dùng cơ chế proxy phổ biến của Spring; một lời gọi tự thân bên trong cùng object (*self-invocation*) thường không đi qua proxy và có thể không kích hoạt transaction như mong đợi. Ranh giới transaction cần được thiết kế tại lời gọi service phù hợp.

## 7. Trạng thái entity ở hai cơ chế

Cho dù cơ chế quản lý là gì, thực thể JPA vẫn trải qua các trạng thái quen thuộc:

```text
new / transient
    |
    | persist()
    v
managed  -------------------------> removed
    |                                  ^
    | close context / detach()         | remove()
    v                                  |
detached ---- merge() ----> managed ---+
```

Sơ đồ trên chỉ mô tả những chuyển đổi thường gặp, không biểu diễn toàn bộ quy tắc vòng đời. Với cả hai cơ chế, thay đổi của **managed entity** được ORM theo dõi; còn đối tượng **detached** không tự đồng bộ thay đổi vào database.

Điều khác nhau nằm ở **thời điểm context chấm dứt**:

- Với `EntityManager` do ứng dụng tự tạo, `close()` chấm dứt context tương ứng; sau đó các entity từng được quản lý trở thành detached.
- Với container-managed transaction-scoped context, khi giao dịch đã hoàn thành, những entity gắn với context đó thường trở thành detached, trừ trường hợp thực thể được quản lý trong một context khác theo quy tắc của nhà cung cấp.
- Với extended context, các entity có thể tiếp tục ở trạng thái managed sau khi một giao dịch kết thúc, cho đến khi context kết thúc hoặc entity bị tách khỏi nó.

Ví dụ, nếu tầng web nhận `Customer` sau khi transaction-scoped context đã kết thúc rồi gọi `customer.setName(...)`, thao tác sửa đối tượng Java **không đủ** để cập nhật bảng `customers`. Cần một giao dịch và quy trình cập nhật phù hợp, chẳng hạn tải lại entity managed rồi thay đổi hoặc dùng `merge()` với hiểu biết rõ về trạng thái và dữ liệu cần đồng bộ.

## 8. Các lỗi thực tế khi chọn sai trách nhiệm

### Quên `close()` với application-managed `EntityManager`

```java
// Vấn đề: tạo EntityManager nhưng không có finally để đóng.
EntityManager entityManager = factory.createEntityManager();
Customer customer = entityManager.find(Customer.class, id);
return customer;
```

Nếu công việc bị lặp lại nhiều lần, ngữ cảnh và các tài nguyên liên quan có thể tích lũy. Đối với EntityManager do ứng dụng tạo, nên đặt đóng tài nguyên trong `finally` và xác định rõ kết quả trả về có còn cần trạng thái managed hay không.

### Đóng `EntityManager` do container hoặc Spring cấp

```java
@PersistenceContext
private EntityManager entityManager;

public void wrong() {
    entityManager.close(); // Sai quyền sở hữu tài nguyên.
}
```

Khi môi trường cấp và quản lý `EntityManager`, application code không được can thiệp đóng nó. Tài nguyên sẽ được quản lý theo giao dịch và vòng đời của môi trường.

### Gọi `getTransaction()` trên JTA `EntityManager`

```java
@PersistenceContext(unitName = "shopJtaPU")
private EntityManager entityManager;

public void wrongAgain() {
    entityManager.getTransaction().begin();
    // Không phải cách điều khiển giao dịch JTA.
}
```

Trong một transaction-managed component, ranh giới giao dịch phải nằm ở cơ chế giao dịch tương ứng, như EJB transaction attributes, Jakarta Transactions hay `@Transactional` của Spring tùy môi trường.

### Giữ `EntityManager` dùng chung giữa nhiều luồng

```java
// Không nên giữ một EntityManager application-managed làm singleton chung.
static EntityManager sharedEntityManager;
```

`EntityManager` chứa trạng thái của persistence context, không được thiết kế để chia sẻ giữa những luồng chạy song song. Đối với application-managed, cần tạo context phù hợp cho mỗi đơn vị công việc. Với container/framework-managed, sử dụng tham chiếu được cung cấp đúng cơ chế của môi trường để mỗi giao dịch được điều phối chính xác.

### Nhầm phạm vi context với phạm vi transaction

Một `EntityManager` do ứng dụng tạo có thể sống qua nhiều giao dịch; một extended persistence context cũng có thể kéo dài qua nhiều giao dịch. Điều đó **không có nghĩa** thay đổi đối tượng được commit ngay tại lúc gọi setter hoặc giao dịch được kéo dài vô hạn. Khi cần lưu bền vững, vẫn phải có transaction hợp lệ và hiểu thời điểm flush/commit.

## 9. Chọn cơ chế phù hợp trong dự án thực tế

| Bối cảnh | Hướng tiếp cận | Trách nhiệm cần nhớ |
| --- | --- | --- |
| Công cụ dòng lệnh Java SE chạy độc lập | Application-managed `EntityManager` + thường là `RESOURCE_LOCAL` | Khởi tạo/tái sử dụng factory, `begin`/`commit`/`rollback`, `close`. |
| Ứng dụng Jakarta EE với EJB service | Container-managed `EntityManager` bằng `@PersistenceContext`, giao dịch JTA | Khai báo thuộc tính giao dịch phù hợp, để container quản lý context. |
| Quy trình Jakarta EE nhiều bước cần giữ entity managed | Extended context trên thành phần hỗ trợ, ví dụ `@Stateful` | Quản lý vòng đời stateful component và các giao dịch riêng lẻ. |
| Ứng dụng Spring Boot dùng JPA hoặc Spring Data JPA | Để Spring quản lý `EntityManager` và giao dịch bằng `@Transactional` | Đặt transaction ở service boundary, không tự đóng injected manager. |
| Môi trường đặc thù cần tự điều khiển context nhưng sử dụng JTA | Application-managed `EntityManager` với JTA | Ứng dụng quản lý context, JTA quản lý commit/rollback; cần hiểu việc tham gia transaction. |

Khi thiết kế, hãy trả lời lần lượt: **Ai tạo `EntityManager`? Ai đóng nó? Context tồn tại bao lâu? Ai commit hoặc rollback?** Nếu bốn câu hỏi này có câu trả lời rõ ràng, cách triển khai JPA thường dễ hiểu và ít lỗi về vòng đời hơn.

## 10. Tổng kết kiến thức trọng tâm

**Application-managed** đặt trách nhiệm tạo, sở hữu và đóng `EntityManager` ở mã ứng dụng. Cách này giúp kiểm soát vòng đời trực tiếp, nhưng lập trình viên phải cẩn thận với transaction, lỗi và tài nguyên.

**Container-managed** giao việc cấp `EntityManager` và quản lý persistence context cho môi trường Jakarta EE; mã nghiệp vụ thường sử dụng `@PersistenceContext` và tham gia giao dịch JTA được điều phối bởi container. Spring có cơ chế quản lý tương tự ở tầng framework, nhưng cách tổ chức transaction phụ thuộc cấu hình Spring.

Điểm cần nhớ là **quản lý `EntityManager`, quản lý persistence context và quản lý transaction là các chiều khác nhau trong kiến trúc JPA**. Hiểu đúng sự phân chia này giúp lựa chọn mô hình phù hợp, tránh gọi API sai phạm vi, ngăn rò rỉ tài nguyên và xác định chính xác thời điểm dữ liệu thực sự được lưu vào database.
