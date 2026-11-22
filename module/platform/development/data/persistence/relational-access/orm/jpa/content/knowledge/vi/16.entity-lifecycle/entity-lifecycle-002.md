# Lưu entity mới bằng persist trong JPA

Trong Java Persistence API (JPA), đối tượng Java được tạo bằng `new` chưa tự động trở thành một hàng trong cơ sở dữ liệu. Khi ứng dụng muốn **tạo một entity mới**, phương thức trung tâm là **`EntityManager.persist(entity)`**. Lời gọi này là điểm chuyển từ trạng thái **new/transient** sang **managed** trong một **persistence context**.

Tuy nhiên, ba sự kiện sau **không đồng nghĩa**:

1. `persist`: JPA nhận quản lý một entity mới.
2. `INSERT`: provider gửi lệnh ghi dữ liệu vào database ở thời điểm thích hợp.
3. `COMMIT`: transaction được xác nhận thành công.

Hiểu đúng sự khác biệt giúp tránh các lỗi phổ biến: cho rằng có ID nghĩa là row đã lưu, quên mở transaction, gọi `persist` trên entity detached, không lưu được entity con do thiếu cascade, hoặc phát thông báo thành công trước khi database commit.

Bài học thuộc chương **Vòng đời entity** trong chủ đề *Data Persistence Relational Access ORM JPA*, tập trung vào cách sử dụng `persist` với entity mới, sinh định danh, transaction, persistence context, quan hệ và những tình huống triển khai thực tế.

## 1. Từ một Java object đến một managed entity

Giả sử ứng dụng tạo khách hàng:

```java
Customer customer = new Customer(
    "Nguyễn An",
    "an@example.com"
);
```

Sau lệnh `new`:

- Java đã cấp phát một đối tượng trong heap.
- Các field mang dữ liệu tên và email.
- Chưa có lời gọi persistence để quản lý đối tượng.
- Không có cơ sở để kết luận database đã có row tương ứng.
- Nếu dùng ID tự sinh, `customer.getId()` thường là `null`.

Khi gọi:

```java
entityManager.persist(customer);
```

đối tượng mới được chuyển sang trạng thái **managed** nếu thao tác hợp lệ. Provider biết cần lưu trạng thái persistent của đối tượng trong transaction thích hợp.

```text
             new Customer(...)
                    |
                    v
              NEW / TRANSIENT
           Chưa được JPA quản lý
                    |
                    | em.persist(customer)
                    v
                 MANAGED
           Thuộc persistence context
           Có thể đang chờ INSERT
                    |
                    | flush / INSERT (thời điểm tùy provider)
                    v
          ROW TRONG TRANSACTION
                /        \
               /          \
          rollback       commit
             |              |
             v              v
        Không xác nhận    Dữ liệu được
        thay đổi         xác nhận trong DB
```

**Kết luận quan trọng:** `persist` mô tả hành vi của **vòng đời entity**, không chỉ là cách viết khác của `INSERT INTO` trong SQL.

## 2. Khai báo entity Customer có thể persist

### 2.1. Entity đầy đủ

```java
package com.example.shop.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 150)
    private String fullName;

    @Column(name = "email", nullable = false, unique = true, length = 254)
    private String email;

    protected Customer() {
        // Constructor không tham số cho JPA.
    }

    public Customer(String fullName, String email) {
        if (fullName == null || fullName.isBlank()) {
            throw new IllegalArgumentException(
                "Tên khách hàng không hợp lệ"
            );
        }
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException(
                "Email không hợp lệ"
            );
        }

        this.fullName = fullName;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException(
                "Tên khách hàng không hợp lệ"
            );
        }
        this.fullName = newName;
    }
}
```

Các annotation có vai trò riêng:

| Annotation | Ý nghĩa |
|---|---|
| `@Entity` | Lớp được JPA ánh xạ thành entity |
| `@Table` | Tên bảng đích |
| `@Id` | Thuộc tính định danh entity |
| `@GeneratedValue` | ID được sinh theo chiến lược cấu hình |
| `@Column(nullable = false)` | Diễn đạt ràng buộc non-null cho mapping/schema |
| `@Column(unique = true)` | Diễn đạt uniqueness trên cột khi tạo schema |
| Constructor `protected Customer()` | Cho phép JPA tạo entity instance |
| Constructor nghiệp vụ | Bảo đảm dữ liệu ban đầu hợp lệ |

Với `@Id` đặt trên field, entity mặc định dùng **field access**; JPA có thể truy cập trực tiếp các field persistent thay vì cần setter công khai. Constructor không tham số public/protected là một phần hợp đồng cơ bản của JPA entity kiểu lớp thông thường.

### 2.2. Schema SQL minh họa

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(254) NOT NULL,
    CONSTRAINT uq_customer_email UNIQUE (email)
);
```

Đây là **DDL khái niệm**. Cú pháp identity, cách sinh sequence, loại cột và chi tiết SQL khác theo database và dialect. Trong dự án dùng migration (Flyway/Liquibase), schema thực tế phải tương thích với mapping entity.

Khi lưu thành công, row có thể là:

| id | full_name | email |
|---:|---|---|
| 101 | Nguyễn An | an@example.com |

Giá trị ID 101 chỉ để minh họa; không có cam kết JPA sẽ cấp đúng số đó.

## 3. Persist với resource-local transaction

Một ứng dụng Java SE dùng application-managed `EntityManager` có thể viết:

```java
package com.example.shop.service;

import com.example.shop.persistence.Customer;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public class CustomerService {

    private final EntityManagerFactory emf;

    public CustomerService(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public Long register(String name, String email) {
        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                Customer customer = new Customer(name, email);
                em.persist(customer);

                // Đồng bộ có chủ đích trong ví dụ.
                em.flush();
                Long createdId = customer.getId();

                tx.commit();
                return createdId;
            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    tx.rollback();
                }
                throw ex;
            }
        } finally {
            em.close();
        }
    }
}
```

Luồng diễn ra:

1. `EntityManagerFactory` tạo `EntityManager` cho đơn vị công việc.
2. `tx.begin()` mở transaction resource-local.
3. Constructor tạo Customer ở trạng thái **new**.
4. `em.persist(customer)` đưa Customer vào trạng thái **managed**.
5. `em.flush()` đồng bộ các thay đổi chờ trong transaction với database.
6. `customer.getId()` đọc ID đã được provider cấp theo mapping.
7. `tx.commit()` xác nhận transaction.
8. `em.close()` kết thúc lifecycle của EntityManager do ứng dụng tạo.

Trong code thực tế, `EntityManagerFactory` thường được dùng chung lâu dài; không tạo/đóng factory mỗi lần đăng ký khách hàng.

### 3.1. Có phải luôn gọi flush trước commit?

**Không.** Trong giao dịch CRUD thông thường, JPA/provider đồng bộ dữ liệu khi transaction commit phù hợp. `flush` thủ công dùng khi cần điểm đồng bộ rõ ràng, chẳng hạn để phát hiện constraint violation sớm hơn hoặc lấy trạng thái từ database trước các thao tác kế tiếp.

Với `GenerationType.IDENTITY`, provider có thể phải **INSERT sớm** để lấy ID tự sinh. Vì vậy trong một số môi trường, SQL INSERT có thể xuất hiện ngay trong hoặc gần lời gọi `persist` mà không đợi `flush`.

Ngược lại, với cơ chế sequence hoặc cấp ID trước, provider có thể biết ID mà vẫn chưa INSERT row.

### 3.2. Vì sao phải xử lý lỗi bao quanh cả commit?

Một lỗi SQL hoặc ràng buộc thường **không nhất thiết ném ra tại dòng `persist`**. Nó có thể xuất hiện ở `flush` hoặc `commit`, nên ranh giới bắt lỗi phải bao trùm toàn bộ transaction.

Sau khi transaction rollback do lỗi persistence, không nên giữ nguyên EntityManager và mặc định state cũ tiếp tục an toàn cho một lượt ghi mới. Hãy kết thúc đơn vị công việc rồi tạo transaction/context mới theo thiết kế.

## 4. Phân biệt new, managed và dữ liệu đã commit

### 4.1. Các mốc thời gian

```text
T0: customer = new Customer(...)
    -> NEW / TRANSIENT

T1: em.persist(customer)
    -> MANAGED trong persistence context

T2: Provider thực thi SQL INSERT
    -> Thay đổi được DB xử lý trong transaction

T3: tx.commit() thành công
    -> Transaction được xác nhận
```

| Mốc | Có thể khẳng định | Chưa thể khẳng định |
|---|---|---|
| Sau `new` | Java instance đã được tạo | Có row mới trong database |
| Sau `persist` | Instance mới trở thành managed nếu hợp lệ | SQL đã chạy và được commit |
| Sau `flush` | Dữ liệu chờ được đồng bộ trong transaction | Transaction đã commit |
| Sau `commit` | Transaction được xác nhận thành công | Các side effect ở hệ thống ngoài DB đã tự động đồng bộ |

Ví dụ:

```java
tx.begin();

Customer customer = new Customer("An", "an@example.com");
em.persist(customer);
em.flush();

tx.rollback();
```

Dù `INSERT` có thể đã được thực thi, **rollback hủy kết quả ghi trong transaction**. Vì vậy `flush()` không phải `commit()`.

### 4.2. EntityManager.contains kiểm tra trạng thái managed

```java
Customer customer = new Customer("An", "an@example.com");

System.out.println(em.contains(customer)); // false.

em.persist(customer);

System.out.println(em.contains(customer)); // true.
```

`contains` trả lời câu hỏi **instance này có thuộc persistence context hiện tại không?**; nó không xác thực transaction đã commit.

Một object khác, dù có dữ liệu giống hệt, không tự được quản lý:

```java
Customer a = new Customer("An", "an@example.com");
Customer b = new Customer("An", "an@example.com");

em.persist(a);

System.out.println(em.contains(a)); // true.
System.out.println(em.contains(b)); // false.
```

Đừng nhầm sự bằng nhau của email hay tên với identity của entity trong JPA.

### 4.3. Identity map sau khi được cấp ID

```java
em.persist(customer);
em.flush();

Customer found = em.find(Customer.class, customer.getId());

System.out.println(found == customer); // true.
```

Trong cùng persistence context, mỗi persistent identity có một managed Java instance. `find` có thể trả lại chính entity đã persist, thay vì tạo thêm object khác.

Tuy nhiên, đọc lại ngay trong **cùng context** không phải bằng chứng row đã commit. Để kiểm chứng dữ liệu bền vững, commit rồi đọc từ một context mới.

## 5. Dirty checking sau persist

Một ưu điểm quan trọng của trạng thái managed:

```java
tx.begin();

Customer customer = new Customer(
    "An",
    "an@example.com"
);

em.persist(customer);

customer.rename("Nguyễn An");

tx.commit();
```

Sau `persist`, Customer được quản lý. Khi ứng dụng đổi `fullName`, provider có thể nhận ra state mới và đồng bộ khi flush/commit. Không cần gọi `persist` lần nữa sau mỗi setter.

SQL có thể khác tùy thời điểm INSERT:

```text
Trường hợp A: INSERT bị trì hoãn
    persist -> rename -> INSERT với full_name cuối

Trường hợp B: IDENTITY cần INSERT sớm
    persist -> INSERT ban đầu -> rename -> UPDATE nếu cần
```

Không suy ra rằng một lệnh gọi `persist` chắc chắn phát đúng một SQL statement. **Hành vi được quan tâm là state cuối được đồng bộ hợp lệ**, không phải số INSERT/UPDATE cố định.

### 5.1. Sau detach, sửa không tự lưu

```java
em.persist(customer);
em.flush();
em.detach(customer);

System.out.println(em.contains(customer)); // false.

customer.rename("Tên khi detached");
// Context cũ không tự dirty-check thay đổi này.
```

Tương tự, `em.clear()` detach mọi entity đang managed; khi application-managed `EntityManager` đóng, instance không còn được context đó quản lý. Muốn cập nhật detached entity, cần tìm managed instance hoặc dùng `merge` đúng mục đích.

## 6. Định danh và chiến lược sinh khóa

ID được ánh xạ bằng `@Id`. `@GeneratedValue` xác định cách provider sinh ID cho entity mới.

### 6.1. IDENTITY

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Cơ chế thường dùng identity/auto-increment của database. Một diễn biến có thể là:

```text
new Customer(id = null)
       |
       | persist
       v
INSERT vào database -> database sinh id
       |
       v
customer.id = 101
```

Provider có thể cần phát INSERT sớm để lấy ID. Điều này có thể ảnh hưởng khả năng JDBC batch insert.

### 6.2. SEQUENCE

```java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "customer_gen"
)
@SequenceGenerator(
    name = "customer_gen",
    sequenceName = "customer_sequence",
    allocationSize = 50
)
private Long id;
```

Với database hỗ trợ sequence, provider có thể cấp ID trước INSERT, đôi khi lấy trước một vùng ID để giảm round trip.

`allocationSize` cần phù hợp schema/sequence thật. Các khoảng trống trong chuỗi ID sau rollback hoặc khi provider cấp phát trước là bình thường; không dùng ID làm số thứ tự liên tục của nghiệp vụ.

### 6.3. TABLE

```java
@Id
@GeneratedValue(strategy = GenerationType.TABLE)
private Long id;
```

Provider sử dụng bảng phát định danh; cách này có thể tạo thêm tranh chấp và thao tác database so với sequence/identity, tùy hệ quản trị.

### 6.4. AUTO

```java
@Id
@GeneratedValue(strategy = GenerationType.AUTO)
private Long id;
```

Provider lựa chọn chiến lược phù hợp. Không thể đoán chính xác DDL, thời điểm cấp ID hay SQL nếu chưa biết provider/dialect.

### 6.5. UUID

Trong các phiên bản Jakarta Persistence hỗ trợ chiến lược UUID, chẳng hạn Jakarta Persistence 3.1 trở lên, có thể dùng:

```java
@Id
@GeneratedValue(strategy = GenerationType.UUID)
private java.util.UUID id;
```

Không giả định `GenerationType.UUID` tồn tại trong mọi dự án dùng JPA cũ/`javax.persistence`. ID UUID có thể xuất hiện trong Java trước khi SQL INSERT, nhưng entity vẫn cần `persist` và commit thành công để lưu dữ liệu.

### 6.6. Bảng so sánh

| Strategy | Nguồn ID điển hình | Điểm ảnh hưởng đến persist |
|---|---|---|
| `IDENTITY` | DB sinh lúc INSERT | Có thể cần INSERT sớm; có thể hạn chế insert batching |
| `SEQUENCE` | DB sequence/cấp phát trước | Có thể có ID trước INSERT; hỗ trợ batching trong một số môi trường |
| `TABLE` | Bảng phát ID | Thêm thao tác/khả năng contention |
| `AUTO` | Provider chọn | Không cố định hành vi giữa DB |
| `UUID` | Provider sinh UUID | Phụ thuộc phiên bản, kiểu cột và mapping |

**ID khác null không có nghĩa transaction đã commit.** Ngay cả ID được ứng dụng gán trước vẫn không làm entity tự managed.

## 7. Lưu entity có ID do ứng dụng gán

Không phải mọi ID đều phải tự sinh. Ví dụ mã quốc gia:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "country")
public class Country {

    @Id
    @Column(length = 2)
    private String code;

    @Column(nullable = false)
    private String displayName;

    protected Country() {
    }

    public Country(String code, String displayName) {
        this.code = code;
        this.displayName = displayName;
    }
}
```

Tạo mới:

```java
Country country = new Country("VN", "Việt Nam");
em.persist(country);
```

Lời gọi `persist` vẫn cần thiết, bởi object có ID thủ công **không tự trở thành managed**.

Nếu database đã có `Country(code="VN")`, gọi persist một entity mới cùng ID có thể khiến provider ném `EntityExistsException` ngay hoặc `PersistenceException` khi flush/commit do ràng buộc khóa chính. Không dùng `persist` như một “insert nếu chưa có, update nếu đã có”.

Lưu ý khóa nghiệp vụ như `code` phải được thiết kế **ổn định**; việc tùy ý thay primary key của managed entity không phải phương thức sửa một thuộc tính thông thường.

## 8. Persist và merge khác nhau như thế nào?

### 8.1. Trạng thái đầu vào và instance đầu ra

| Thao tác | Đầu vào điển hình | Instance managed sau lời gọi | Mục đích |
|---|---|---|---|
| `em.persist(x)` | New entity | **Chính x** | Bắt đầu persistent lifecycle của entity mới |
| `em.merge(x)` | Detached hoặc new entity | **Instance trả về**, có thể khác x | Copy state sang managed instance |
| `em.find(T.class, id)` | Entity type + ID | Instance được trả về | Tải/tìm managed entity |
| `em.remove(x)` | Managed entity | Đưa vào removed lifecycle | Yêu cầu xóa row |

`EntityManager.persist` có kiểu trả về **`void`**:

```java
em.persist(customer);

// Không hợp lệ: persist không trả về Customer.
// Customer saved = em.persist(customer);
```

Khác `merge`:

```java
Customer managed = em.merge(detached);
```

`merge` không “chuyển chính detached instance đầu vào thành managed” một cách tổng quát, mà trả instance managed để tiếp tục thao tác.

### 8.2. Vì sao không dùng merge làm upsert mặc định?

`merge` có thể nhận một entity new và tạo managed copy, nhưng điều đó không biến merge thành upsert atomic trong mọi tình huống. Với detached object có ID, provider phải giải quyết identity và trạng thái hiện hữu. Cascade graph cũng có thể ảnh hưởng nhiều entity.

Một service có mục đích **tạo khách hàng mới** nên dùng `persist` để diễn đạt ý định rõ ràng. Service có mục đích **sửa khách hàng đã có** thường nên tải managed entity theo ID rồi áp những field được phép sửa.

### 8.3. Persist entity detached có thể lỗi

```java
Customer detached = loadInPreviousRequest();

em.persist(detached); // Không phải cách reattach portable.
```

Provider có thể ném exception vì detached entity đã có persistent identity. Để cập nhật, dùng:

```java
Customer managed = em.find(
    Customer.class,
    detached.getId()
);

managed.rename(newName);
```

hoặc `merge` khi thật sự cần copy detached state, nhưng không bỏ qua validation, authorization và optimistic locking.

### 8.4. Spring Data save không phải EntityManager.persist

`customerRepository.save(customer)` thuộc Spring Data JPA, không phải API `EntityManager` chuẩn. Tùy chiến lược xác định entity mới (ID, version, `Persistable`...), repository có thể chọn persist hoặc merge.

Do đó không đồng nhất:

```java
repository.save(customer);
```

với:

```java
em.persist(customer);
```

trong mọi trường hợp. Nếu dùng ID tự gán hoặc entity không có version, cần xem cách repository nhận diện entity mới.

## 9. Transaction trong Spring hoặc Jakarta EE

### 9.1. Jakarta EE và JTA

Trong môi trường container-managed JTA:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.transaction.Transactional;

public class CustomerRegistrationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long register(String fullName, String email) {
        Customer customer = new Customer(fullName, email);
        em.persist(customer);

        // Có thể flush nếu use case cần đồng bộ sớm.
        em.flush();

        return customer.getId();
    }
}
```

Transaction được quản lý bởi container. Không gọi `em.getTransaction().begin()/commit()` hoặc `em.close()` trên container-managed EntityManager như ở resource-local.

Ngay cả khi phương thức trả về ID, việc commit có thể diễn ra ở interceptor/container sau khi body phương thức kết thúc. Nếu commit thất bại, ngoại lệ phải được xử lý theo contract của service.

### 9.2. Spring service

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerRegistrationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long register(String fullName, String email) {
        Customer customer = new Customer(fullName, email);
        em.persist(customer);
        return customer.getId();
    }
}
```

`@Transactional` ở đây là annotation Spring, không phải một phương thức JPA. Framework phối hợp transaction và EntityManager/context.

Trong thiết lập Spring dùng proxy-based transaction, **self-invocation** (một phương thức trong cùng bean gọi trực tiếp phương thức khác có `@Transactional`) có thể không đi qua transaction interceptor. Khi đó code tưởng có transaction nhưng thực tế không được kích hoạt như mong muốn. Đây là vấn đề về transaction boundary, không phải hành vi đặc biệt của persist.

### 9.3. Transaction scope và thời gian sống của managed entity

Một entity được persist trong một transaction-scoped persistence context có thể trở thành detached khi transaction/context kết thúc. Nếu trả entity ra khỏi service, việc sửa nó ở request khác không còn được context cũ tự dirty-check.

Đừng giữ application-managed `EntityManager` làm singleton giữa nhiều request. `EntityManager` không được thiết kế thread-safe như `EntityManagerFactory`; trong Spring/Jakarta EE, một proxy được inject có thể điều phối context theo transaction/thread khác với việc giữ một EntityManager instance dùng chung.

## 10. Cascade PERSIST: lưu entity mới có entity con

Giả sử hệ thống tạo một `PurchaseOrder` cùng các dòng hàng `OrderLine`. Khi một đơn được tạo, những dòng hàng mới thuộc về chính đơn đó.

### 10.1. Entity PurchaseOrder

```java
package com.example.shop.persistence;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true)
    private String orderCode;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderCode) {
        this.orderCode = Objects.requireNonNull(orderCode);
    }

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line);

        if (line.getOrder() != null && line.getOrder() != this) {
            throw new IllegalStateException(
                "Dòng hàng đã thuộc đơn hàng khác"
            );
        }

        if (!lines.contains(line)) {
            lines.add(line);
        }
        line.assignOrder(this);
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }
}
```

### 10.2. Entity OrderLine

```java
package com.example.shop.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(String sku, int quantity) {
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException(
                "Dữ liệu dòng hàng không hợp lệ"
            );
        }
        this.sku = sku;
        this.quantity = quantity;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    void assignOrder(PurchaseOrder order) {
        this.order = order;
    }
}
```

Phân tích:

- `OrderLine.order` là **owning side** của khóa ngoại `order_id`.
- `PurchaseOrder.lines` là phía inverse với `mappedBy = "order"`.
- `cascade = PERSIST` cho phép thao tác persist Order truyền sang các `OrderLine` mới.
- Cascade **không** có nghĩa JPA tự gán owner. Helper `addLine` phải thiết lập `line.order`.

### 10.3. Persist một aggregate mới

```java
PurchaseOrder order = new PurchaseOrder("PO-001");

OrderLine line1 = new OrderLine("BOOK-01", 2);
OrderLine line2 = new OrderLine("PEN-02", 4);

order.addLine(line1);
order.addLine(line2);

em.persist(order);

// Cascade PERSIST đưa cả line1 và line2 mới
// vào lifecycle managed theo mapping.
```

SQL khái niệm:

```sql
INSERT INTO purchase_order(order_code)
VALUES ('PO-001');

INSERT INTO order_line(order_id, sku, quantity)
VALUES (?, 'BOOK-01', 2);

INSERT INTO order_line(order_id, sku, quantity)
VALUES (?, 'PEN-02', 4);
```

Provider điều phối thứ tự SQL và ID để thỏa FK, chứ không nhất thiết chạy INSERT đúng thứ tự Java constructor xuất hiện.

Nếu bỏ cascade PERSIST, gọi `em.persist(order)` **không mặc định** persist các OrderLine mới. Khi đó cần persist riêng từng child hoặc cấu hình cascade phù hợp với vòng đời nghiệp vụ.

## 11. Cascade không nên đặt bừa lên mọi association

Giả sử OrderLine tham chiếu Product:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "product_id")
private Product product;
```

`Product` thường là entity danh mục **đã tồn tại**. Tạo OrderLine mới không đồng nghĩa tạo Product mới.

Hướng làm rõ ràng:

```java
Product product = em.find(Product.class, productId);

if (product == null) {
    throw new IllegalArgumentException("Sản phẩm không tồn tại");
}

// Tạo OrderLine có tham chiếu product, rồi persist Order/Line.
// Không cần persist lại Product đã managed.
```

Không thêm `cascade = PERSIST` lên Product chỉ để “tránh lỗi transient”, vì nó có thể khiến provider cố tạo Product ngoài ý định. Với entity dùng chung như Product/Role/Category, quản lý vòng đời độc lập thường an toàn hơn.

Trong `@ManyToMany` giữa các entity độc lập, càng cần thận trọng với `CascadeType.ALL` vì ALL bao gồm REMOVE: xóa một User không nên xóa cả Role được các User khác sử dụng.

### 11.1. Cascade và owning side trả lời câu hỏi khác nhau

| Cơ chế | Câu hỏi |
|---|---|
| Cascade PERSIST | Persist entity chủ có lan truyền tới entity liên quan không? |
| Owning side | Thuộc tính nào quyết định FK hoặc join table khi ghi? |
| `optional = false` | Association có bắt buộc tồn tại theo mapping? |
| `nullable = false` | Cột FK có yêu cầu non-null ở DB schema? |
| Orphan removal | Loại entity con khỏi quan hệ sở hữu vòng đời có xóa child không? |

`cascade = PERSIST` không thay đổi phía ownership, không sửa object graph hai chiều và không vượt qua FK/unique constraints.

## 12. Persist với entity liên kết đã tồn tại

Tạo một đơn hàng mới cho Customer đã có:

```java
Customer existingCustomer =
    em.find(Customer.class, customerId);

if (existingCustomer == null) {
    throw new IllegalArgumentException(
        "Khách hàng không tồn tại"
    );
}

// Giả định Order có constructor phù hợp nhận Customer.
Order order = new Order("PO-002", existingCustomer);

em.persist(order);
```

`existingCustomer` đang managed; `order` mới cần persist. Không gọi `em.persist(existingCustomer)` lần nữa chỉ để gán FK.

Trong trường hợp chỉ cần FK và đã biết ID, có thể dùng:

```java
Customer reference =
    em.getReference(Customer.class, customerId);
```

Provider có thể sử dụng reference/proxy mà chưa SELECT đầy đủ Customer. Nhưng `getReference` không thay thế xác thực dữ liệu/quyền truy cập và có thể chỉ báo lỗi không tồn tại khi truy cập reference hoặc flush FK. Nếu nghiệp vụ yêu cầu kiểm tra customer hiện hữu, dùng `find` hoặc kiểm tra rõ ràng.

## 13. @PrePersist và @PostPersist trong vòng đời tạo mới

### 13.1. @PrePersist điền metadata trước khi lưu

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;

import java.time.Instant;

@Entity
public class Note {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String content;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Note() {
    }

    public Note(String content) {
        this.content = content;
    }

    @PrePersist
    void beforePersist() {
        if (createdAt == null) {
            createdAt = Instant.now();
        }
    }
}
```

`@PrePersist` có thể được dùng để khởi tạo trạng thái đơn giản như `createdAt`. Không nên viết callback phụ thuộc việc đã có ID từ IDENTITY: ID do database tạo có thể chưa sẵn ở thời điểm callback.

### 13.2. @PostPersist không phải after commit

```java
@PostPersist
void afterPersist() {
    // Sự kiện lifecycle post-persist,
    // KHÔNG bảo đảm transaction đã commit.
}
```

`@PostPersist` được gọi theo lifecycle persistence, nhưng thời điểm gọi có thể gắn với việc provider thực thi INSERT trong `persist`, `flush` hoặc quá trình trước commit. Sau callback, transaction vẫn có thể rollback.

Vì thế không dùng `@PostPersist` làm cơ chế phát email, thực hiện thanh toán hoặc publish sự kiện ngoài DB rồi mặc định chúng có thể rollback cùng transaction. Khi cần phát sau commit, dùng transaction synchronization, outbox hoặc thiết kế event tương ứng.

Lifecycle callbacks cũng không phải nơi phù hợp để tự thực hiện query và các `EntityManager` operation phức tạp. Nên giữ callback đơn giản với state của chính entity.

### 13.3. Bean Validation là một tầng khác

Nếu ứng dụng tích hợp Jakarta Bean Validation:

```java
@NotBlank
@Column(nullable = false)
private String fullName;

@Email
@Column(nullable = false, unique = true)
private String email;
```

các constraint với import `jakarta.validation.constraints` có thể giúp kiểm tra state. Nhưng:

- Bean Validation không thay business authorization.
- `@Column(nullable = false)` không tự kiểm tra mọi request trước persist.
- Unique constraint tại database vẫn cần để chống race condition.
- Lỗi có thể chỉ xuất hiện tại flush/commit.

## 14. Những lỗi persist thường gặp

### 14.1. Persist entity đã tồn tại

```java
Country country = new Country("VN", "Việt Nam");

// DB đã có row Country("VN").
em.persist(country);
```

Provider có thể ném `EntityExistsException` ngay hoặc `PersistenceException` khi flush/commit. Không dùng persist để ghi đè row cũ.

### 14.2. Persist detached entity

```java
Customer detached = loadInOldContext();

em.persist(detached); // Không phải thao tác reattach portable.
```

Nếu muốn cập nhật, tìm managed Customer rồi sửa hoặc dùng merge khi phù hợp.

### 14.3. Thiếu transaction

```java
EntityManager em = emf.createEntityManager();
em.persist(new Customer("An", "an@example.com"));

// Không mở/commit transaction resource-local.
```

Không thể xem thao tác là lưu bền vững. Với một số lifecycle/context, lời gọi persist có thể thay đổi managed state mà chưa được đồng bộ; transaction hợp lệ vẫn là điều kiện để ghi commit.

### 14.4. UNIQUE/NOT NULL violation

Hai Customer có cùng email có thể đều được `persist` nhận vào context, rồi chỉ một INSERT thành công khi DB kiểm tra uniqueness. Lỗi có thể phát sinh ở `flush` hoặc `commit`, không nhất thiết tại `persist`.

### 14.5. FK tới entity chưa persist

Nếu new OrderLine tham chiếu new Product nhưng không persist/cascade Product phù hợp, flush có thể báo lỗi transient reference hoặc FK. Hãy xác định Product được tạo mới cùng transaction hay đã tồn tại để chọn cách quản lý.

### 14.6. Constructor JPA không phù hợp

Entity thiếu constructor không tham số public/protected theo hợp đồng entity thông thường có thể không được provider khởi tạo đúng. Hãy giữ constructor phù hợp, dù constructor nghiệp vụ có kiểm tra điều kiện riêng.

### 14.7. Rollback xong tiếp tục dùng context cũ

Sau lỗi persistence/rollback, state trong context có thể khác DB. Không mặc định retry ngay trên cùng context và object graph; cần tạo unit of work mới khi thiết kế retry.

### 14.8. `persist` lặp lại trên cùng managed instance

```java
em.persist(customer);
em.persist(customer);
```

Nếu entity đã managed, lời gọi thêm không có nghĩa tạo thêm một row. Tuy nhiên cascade PERSIST có thể vẫn được áp dụng theo mapping; không cần gọi persist lặp lại mỗi lần sửa.

## 15. Unique constraint và tạo entity đồng thời

Giả sử hai request cùng tạo email `an@example.com`:

```text
Transaction A                  Transaction B
----------------------------   ----------------------------
SELECT kiểm tra email rỗng     SELECT kiểm tra email rỗng
new Customer A                 new Customer B
persist(A)                     persist(B)
INSERT email trùng             INSERT email trùng
commit                         commit hoặc UNIQUE conflict
```

Việc kiểm tra `existsByEmail` trước persist không bảo đảm tính duy nhất khi có concurrency. Cần:

1. Unique constraint ở DB.
2. Validation thân thiện ở service nhưng không coi pre-check là bảo đảm tuyệt đối.
3. Xử lý constraint conflict tại transaction boundary, quy đổi thành lỗi nghiệp vụ.
4. Không retry mù quáng trên context đã lỗi.
5. Nếu cần upsert thực sự, dùng cơ chế DB/locking/transaction được thiết kế riêng.

`persist` không phải atomic upsert. Nó có nghĩa “tạo mới entity” trong lifecycle JPA.

## 16. Flush mode và thời điểm INSERT

JPA có:

```java
em.setFlushMode(FlushModeType.AUTO);
em.setFlushMode(FlushModeType.COMMIT);
```

Tổng quan:

| Flush mode | Ý nghĩa |
|---|---|
| `AUTO` | Provider bảo đảm thay đổi liên quan được phản ánh trong những query phù hợp, có thể flush trước query hoặc dùng cơ chế khác |
| `COMMIT` | Đồng bộ ở commit là trọng tâm; cách query trước commit thấy thay đổi chưa flush không được xác định hoàn toàn portable |

Ví dụ:

```java
em.persist(new Customer("An", "an@example.com"));

long count = em.createQuery(
    "select count(c) from Customer c",
    Long.class
).getSingleResult();
```

Không suy ra chính xác query có thấy row mới hay đã phát SQL nào mà không biết transaction, strategy, flush mode và provider. `FlushModeType.AUTO` giúp bảo đảm ngữ nghĩa truy vấn theo contract, nhưng không quy định một danh sách SQL cố định.

**Điều không đổi:** transaction phải commit thành công để thay đổi được xác nhận; flush mode không tạo autocommit cho persist.

## 17. Persist số lượng lớn và quản lý persistence context

Import hàng chục nghìn entity:

```java
for (int i = 0; i < 100_000; i++) {
    em.persist(new Customer(
        "Customer " + i,
        "user" + i + "@example.com"
    ));
}
```

Nếu tất cả được giữ managed trong một context, bộ nhớ có thể tăng vì entity instances, identity map, snapshots và pending operations.

Một hướng với transaction đang mở:

```java
int batchSize = 100;

for (int i = 1; i <= 10_000; i++) {
    em.persist(new Customer(
        "Customer " + i,
        "batch" + i + "@example.com"
    ));

    if (i % batchSize == 0) {
        em.flush();
        em.clear();
    }
}

em.flush();
em.clear();
```

`flush` đồng bộ pending changes; `clear` detach managed entities để hạn chế kích thước context. Tuy nhiên:

- `clear` trước khi flush có thể làm mất pending changes.
- `clear` detach **mọi** entity, kể cả instance khác service còn cần.
- Flush/clear không commit hoặc rút ngắn một transaction dài.
- Nếu chia thành nhiều transaction theo batch, phải chấp nhận commit từng phần.
- IDENTITY có thể làm giảm lợi ích JDBC insert batching trong một số provider.
- Batch size tối ưu phụ thuộc database, driver, schema và workload; cần đo thay vì đoán.

## 18. Tạo entity và side effect ngoài database

Một ví dụ nguy hiểm:

```java
em.persist(customer);
emailService.sendWelcome(customer.getEmail());
tx.commit();
```

Email gửi ra hệ thống ngoài không rollback cùng transaction DB. Nếu commit thất bại, email có thể vẫn được gửi.

Các hướng giải quyết:

- Phát side effect sau khi transaction commit thành công bằng cơ chế synchronization của framework.
- Dùng **transactional outbox**: ghi row sự kiện vào DB cùng transaction tạo Customer; worker phát message sau.
- Dùng idempotency và retry để tránh gửi lặp.
- Với hệ thống phân tán phức tạp, thiết kế compensation/saga theo nghiệp vụ.

`@PostPersist` không phải after-commit hook; không dựa vào callback để bảo đảm hệ thống ngoài đồng bộ nguyên tử với database.

## 19. Kiểm thử trạng thái managed và dữ liệu đã lưu

### 19.1. Chỉ kiểm tra contains là chưa đủ

```java
Customer customer = new Customer("An", "an@example.com");

boolean before = em.contains(customer); // false
em.persist(customer);
boolean after = em.contains(customer);   // true
```

Đây là kiểm tra **lifecycle state**, không phải chứng minh row đã commit.

### 19.2. Đọc lại trong cùng context có thể lấy first-level cache

```java
em.persist(customer);
em.flush();

Customer same = em.find(Customer.class, customer.getId());
System.out.println(same == customer); // true
```

`find` có thể lấy chính managed instance từ persistence context. Để kiểm chứng dữ liệu bền vững:

1. Commit transaction tạo mới.
2. Kết thúc hoặc clear context phù hợp.
3. Mở EntityManager mới.
4. Đọc lại theo ID và so sánh dữ liệu.
5. Kiểm tra constraint và relationship thực tế khi cần.

### 19.3. Mẫu kiểm tra sau commit

```java
Long createdId;
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();
    try {
        tx.begin();

        Customer customer =
            new Customer("An", "an@example.com");

        em.persist(customer);
        em.flush();

        createdId = customer.getId();
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

EntityManager verifyEm = emf.createEntityManager();

try {
    Customer reloaded =
        verifyEm.find(Customer.class, createdId);

    if (reloaded == null) {
        throw new AssertionError(
            "Không tìm thấy Customer sau commit"
        );
    }
} finally {
    verifyEm.close();
}
```

Đây là mã minh họa, chưa thay thế test framework, cleanup hoặc transaction isolation của môi trường kiểm thử. Test thực tế cũng cần dữ liệu đầu vào duy nhất giữa các lần chạy và xử lý rollback như mong muốn.

### 19.4. Quan sát SQL log

SQL logging của Hibernate hoặc provider khác giúp thấy:

- Provider lấy ID khi nào.
- `INSERT` xảy ra ở persist, flush hay commit.
- Có thêm SQL sequence/table generator không.
- Cascade có ghi entity con không.
- Constraint violation xuất hiện tại bước nào.

Các log khác nhau giữa Hibernate/EclipseLink, phiên bản và dialect là bình thường. Đừng biến log một môi trường thành “luật chung” của JPA.

## 20. Những ngộ nhận phổ biến về persist

### 20.1. “Persist luôn INSERT và commit ngay”

**Sai.** Persist đưa entity mới vào managed lifecycle. SQL và commit là các bước riêng.

### 20.2. “Persist trả entity được lưu”

**Sai.** `EntityManager.persist` trả `void`; chính instance được truyền vào trở thành managed nếu hợp lệ.

### 20.3. “Đã có ID là đã commit”

**Sai.** ID có thể đến từ sequence, UUID, IDENTITY trước commit hoặc do ứng dụng tự gán.

### 20.4. “Phải gọi persist mỗi khi sửa entity”

**Sai.** Managed entity được dirty-check, không cần persist lại sau mỗi setter.

### 20.5. “Có thể dùng persist để cập nhật detached entity”

**Sai.** Persist dành cho new entity; detached cần find/merge và logic cập nhật đúng.

### 20.6. “Persist và merge khác nhau chỉ ở tên”

**Sai.** Persist quản lý instance mới; merge trả managed instance đã copy state.

### 20.7. “Flush rồi thì rollback không thể hủy row”

**Sai.** Flush không đồng nghĩa commit.

### 20.8. “Không cần transaction khi persist”

**Sai về kết quả bền vững.** Phải có transaction hợp lệ để ghi/commit dữ liệu.

### 20.9. “Mọi object liên kết sẽ tự persist”

**Sai.** Chỉ những entity được persist rõ ràng hoặc cascade phù hợp mới vào lifecycle managed theo thao tác đó.

### 20.10. “Cascade PERSIST quyết định phía sở hữu FK”

**Sai.** Cascade và owning side khác mục đích; FK vẫn dựa trên owning association.

### 20.11. “CascadeType.ALL luôn thuận tiện và an toàn”

**Sai.** Nó gồm REMOVE, có thể xóa nhầm entity độc lập như Product/Role.

### 20.12. “@PrePersist chắc chắn có ID do IDENTITY sinh”

**Sai.** Với IDENTITY, ID có thể chưa sẵn ở `@PrePersist`.

### 20.13. “@PostPersist là sau commit”

**Sai.** Callback lifecycle có thể chạy trước commit, transaction vẫn có thể rollback.

### 20.14. “Unique constraint luôn được kiểm tra ở lời gọi persist”

**Sai.** Lỗi có thể chỉ xuất hiện ở flush/commit khi thực thi SQL.

### 20.15. “contains true chứng minh row tồn tại”

**Sai.** `contains` kiểm tra managed instance trong context.

### 20.16. “Hai new Customer cùng email sẽ được JPA tự gộp”

**Sai.** JPA không dùng email tự gộp new instances. Uniqueness thuộc DB constraint/business logic.

### 20.17. “Rollback xong cứ retry trên cùng context”

**Không nên giả định.** Exception persistence có thể khiến context/transaction không còn trạng thái đáng tin cho lần ghi mới.

### 20.18. “Clear sau persist sẽ lưu mọi thứ rồi dọn bộ nhớ”

**Sai.** `clear` detach entities; pending changes chưa flush có thể mất.

### 20.19. “Có thể gọi persist trong callback để orchestration cả graph”

**Không portable và khó kiểm soát.** Nên để orchestration nhiều entity ở service/domain.

### 20.20. “Một test gọi persist không lỗi thì dữ liệu đã lưu bền vững”

**Sai.** Cần kiểm tra commit và đọc lại từ context mới khi mục tiêu là persistence.

## 21. Quy trình tạo mới entity trong ứng dụng thực tế

```text
           Nhận yêu cầu tạo mới
                    |
                    v
       Kiểm tra dữ liệu và quyền
                    |
                    v
       Bắt đầu transaction phù hợp
                    |
                    v
        Tải các reference đã tồn tại
        (Customer/Product/Role...) nếu có
                    |
                    v
             new Entity(...)
                    |
                    v
         Thiết lập association hợp lệ
         + cập nhật owning side
                    |
                    v
              em.persist(root)
                    |
           +--------+--------+
           |                 |
           v                 v
    cascade PERSIST    persist rõ ràng entity
    với thành phần     mới độc lập nếu cần
    cùng lifecycle
           |                 |
           +--------+--------+
                    |
                    v
          flush nếu thật sự cần
                    |
                    v
             commit thành công?
               /           \
             Không         Có
              |             |
              v             v
        rollback và      Trả ID/DTO
        xử lý lỗi       /phát event sau commit
```

Khi xây dựng service, hãy tách rõ trách nhiệm:

- Constructor/factory tạo trạng thái ban đầu hợp lệ.
- Service kiểm tra quyền và những business invariant cần query database.
- JPA quản lý managed state, cascade và SQL đồng bộ.
- Database constraints bảo vệ tính toàn vẹn trước cạnh tranh.
- Transaction boundary quyết định xác nhận hay rollback.
- API trả DTO hoặc ID sau thao tác thành công; không dựa vào entity được persist như bằng chứng commit khi transaction chưa kết thúc.

## 22. Bài tập thực hành

### Bài 1: Chọn thao tác để tạo Customer

```java
Customer customer = new Customer(
    "Lan",
    "lan@example.com"
);
```

**Câu hỏi:** Thao tác JPA nào phù hợp để tạo row mới?

**Gợi ý:** Trong transaction hợp lệ, gọi `em.persist(customer)`. Sau persist hợp lệ, instance customer trở thành managed; commit xác nhận row.

### Bài 2: Đã có ID có phải đã commit?

```java
tx.begin();
Customer customer = new Customer("Lan", "lan@example.com");
em.persist(customer);
Long id = customer.getId();
tx.rollback();
```

**Gợi ý:** Không. ID có thể có trước commit. Rollback không xác nhận row.

### Bài 3: Hai Customer trùng email

```java
em.persist(new Customer("Lan A", "lan@example.com"));
em.persist(new Customer("Lan B", "lan@example.com"));
```

**Gợi ý:** Unique constraint ở DB có thể khiến một INSERT thất bại. JPA không gộp theo email.

### Bài 4: Persist detached

```java
Customer detached = loadInAnotherRequest();
em.persist(detached);
```

**Gợi ý:** Persist dành cho new entity; cập nhật detached bằng find managed rồi áp thay đổi hoặc merge phù hợp.

### Bài 5: Persist Order cùng OrderLine

```java
@OneToMany(mappedBy = "order", cascade = CascadeType.PERSIST)
private List<OrderLine> lines;
```

**Câu hỏi:** Vì sao cần `line.order = order` khi đã có cascade?

**Gợi ý:** Cascade truyền lifecycle persist. FK `order_id` do owning side `OrderLine.order` quyết định.

### Bài 6: Product đã tồn tại

`OrderLine` mới tham chiếu Product hiện hữu.

**Gợi ý:** Tìm Product managed/reference theo ID, không cascade PERSIST vào Product danh mục chỉ để tạo OrderLine mới.

### Bài 7: Số INSERT với IDENTITY

```java
em.persist(customer);
customer.rename("Tên cuối");
em.flush();
```

**Gợi ý:** Không chắc chỉ một INSERT. Provider có thể INSERT sớm để lấy ID rồi UPDATE sau khi đổi name; phải quan sát SQL thật.

### Bài 8: @PrePersist có dùng gửi email không?

**Gợi ý:** Không nên. Callback không bảo đảm transaction commit. Dùng after-commit hoặc transactional outbox.

### Bài 9: Kiểm tra exists trước persist đã đủ?

Hai transaction đều thấy email chưa tồn tại rồi cùng insert.

**Gợi ý:** Chưa đủ; cần DB unique constraint và xử lý conflict.

### Bài 10: Đọc lại trong cùng context

```java
em.persist(customer);
em.flush();
Customer same = em.find(Customer.class, customer.getId());
```

**Gợi ý:** `find` có thể trả managed instance từ first-level cache. Muốn chứng minh đã commit, dùng context mới đọc sau commit.

### Bài 11: Clear trước flush

```java
em.persist(customer);
em.clear();
```

**Gợi ý:** Clear có thể làm mất pending changes chưa flush. Với batch processing, cần flush rồi clear và quản lý transaction.

### Bài 12: Persist khác upsert

Database đã có Country code VN, ứng dụng tạo Country mới cũng có code VN.

**Gợi ý:** Persist không tự update row cũ; có thể gây lỗi khóa chính. Upsert đòi hỏi workflow hoặc cơ chế DB phù hợp.

### Bài 13: Ý nghĩa contains

```java
boolean before = em.contains(customer);
em.persist(customer);
boolean after = em.contains(customer);
```

**Gợi ý:** Với entity mới hợp lệ, trước false và sau true. Đây là trạng thái managed, không phải trạng thái commit.

### Bài 14: Spring Data save

```java
customerRepository.save(customer);
```

**Gợi ý:** `save` không phải method chuẩn của EntityManager; Spring Data có thể chọn persist hoặc merge theo metadata nhận biết entity mới.

### Bài 15: Phát thông báo trước commit

Service persist Customer, gửi mail chào mừng rồi commit thất bại.

**Gợi ý:** Phát sau commit hoặc ghi outbox trong cùng transaction, sau đó phát message có retry/idempotency.

## 23. Ghi nhớ cuối bài

| Câu hỏi | Câu trả lời |
|---|---|
| Đối tượng mới có state gì? | New/transient |
| Dùng API nào để lưu entity mới? | `EntityManager.persist(entity)` |
| `persist` trả về gì? | `void` |
| Instance nào trở thành managed? | Chính instance được persist nếu hợp lệ |
| SQL INSERT có luôn chạy tại persist? | Không; phụ thuộc ID strategy, provider, flush và transaction |
| ID có thể có trước commit không? | Có |
| `contains(entity)` có chứng minh commit? | Không |
| Lúc nào dữ liệu được xác nhận? | Commit transaction thành công |
| Sau persist sửa field có phải persist lại? | Không nếu entity vẫn managed |
| Entity detached có nên dùng persist để cập nhật? | Không; dùng find/merge phù hợp |
| Persist entity con như thế nào? | Persist rõ ràng hoặc cascade PERSIST được cấu hình đúng |
| Cascade có tự đặt FK? | Không; owning side phải đúng |
| `@PostPersist` có phải after commit? | Không |
| `flush` có thay commit không? | Không |
| Cần DB unique constraint dù đã validate? | Có, để bảo vệ concurrency |
| Persist nhiều row có thể tăng bộ nhớ? | Có; cân nhắc flush/clear theo batch |

**Kết luận:** `EntityManager.persist` là thao tác cốt lõi để **đưa một entity mới vào persistence context** và bắt đầu vòng đời managed của nó trong JPA. Từ đó provider có thể theo dõi state, sinh ID và thực thi INSERT theo mapping/transaction. Tuy nhiên, **managed không đồng nghĩa INSERT đã chạy, INSERT không đồng nghĩa commit và có ID không đồng nghĩa lưu thành công**. Khi kết hợp transaction hợp lệ, cascade có chủ đích, owning side nhất quán, ràng buộc database và kiểm tra kết quả sau commit, việc tạo entity mới bằng `persist` sẽ rõ ràng, dễ dự đoán và an toàn hơn.
