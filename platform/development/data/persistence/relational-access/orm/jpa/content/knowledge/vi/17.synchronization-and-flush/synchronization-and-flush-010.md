# Phối hợp flush và clear khi xử lý nhiều entity

> **Chủ đề:** Data Persistence – Relational Access ORM JPA  
> **Nhóm kiến thức:** Đồng bộ và flush

Khi một ứng dụng Java sử dụng JPA để nhập hàng chục nghìn bản ghi, cập nhật nhiều entity hoặc xử lý từng phần dữ liệu lớn, hai thao tác **EntityManager.flush()** và **EntityManager.clear()** thường được dùng cùng nhau. Nhưng chúng có **hai vai trò hoàn toàn khác nhau**:

- **flush()** yêu cầu JPA đồng bộ những thay đổi đang chờ trong **persistence context** xuống cơ sở dữ liệu bằng các câu lệnh SQL thích hợp.
- **clear()** loại các entity đang được quản lý khỏi **persistence context**, khiến chúng trở thành **detached** và không còn được dirty checking tự động trong context ấy.

Thứ tự thông thường cho một lô công việc là:

~~~java
entityManager.flush();
entityManager.clear();
~~~

Cách phối hợp này giúp **không giữ quá nhiều managed entities và snapshot trong bộ nhớ** khi duyệt một khối dữ liệu lớn. Tuy nhiên, **flush không phải commit**, **clear không phải rollback**, và **flush + clear không tự làm các INSERT nhanh hơn bằng JDBC batching**.

Bài học giải thích cơ chế persistence context, thứ tự thực thi, cách chia lô an toàn, transaction, entity states, quan hệ và cascade, ID generation, hiệu năng, xử lý lỗi và các ví dụ đầy đủ với JPA thuần cùng Spring Data JPA.

## 1. Vì sao xử lý nhiều entity gây áp lực lên persistence context?

Giả sử ứng dụng cần nhập **100.000 Customer**:

~~~java
for (CustomerInput input : inputs) {
    Customer customer = new Customer(input.code(), input.name());
    em.persist(customer);
}
~~~

Một entity được gọi **persist** thường sẽ trở thành **managed** trong persistence context. Tùy provider và mapping, context giữ:

- Identity và reference tới entity;
- Thông tin quản lý trạng thái;
- Snapshot hoặc cơ chế theo dõi thay đổi phục vụ dirty checking;
- Các action INSERT/UPDATE/DELETE đang chờ;
- Thông tin liên quan đến collection, association và cascade.

Nếu duyệt một số lượng rất lớn entity mà không có chiến lược quản lý, **bộ nhớ Java có thể tăng**, dirty checking và flush có thể tốn nhiều thời gian, nhiều đối tượng được giữ lại lâu hơn mức cần thiết.

~~~text
EntityManager / Persistence Context
│
├── Customer#1   (managed)
├── Customer#2   (managed)
├── Customer#3   (managed)
│     ...
└── Customer#100000 (managed)
       │
       ├── quản lý identity / state
       ├── dirty checking
       └── SQL đang chờ đồng bộ
~~~

Không phải cứ 100.000 entity thì luôn hết bộ nhớ: lượng RAM phụ thuộc mapping, provider, kích thước object, fetch plan, collection, LOB và JVM. Nhưng việc để persistence context lớn dần không giới hạn là rủi ro rõ ràng của những batch jobs dài.

### 1.1. Persistence context không phải một danh sách Java thông thường

Nó là môi trường quản lý entity theo identity. Trong cùng một context:

~~~java
Customer a = em.find(Customer.class, customerId);
Customer b = em.find(Customer.class, customerId);

System.out.println(a == b);       // true trong cùng context.
System.out.println(em.contains(a)); // true.
~~~

Cùng một hàng database được đại diện bằng một managed instance trong context. Khi entity managed thay đổi, provider có thể phát hiện qua dirty checking tại flush.

~~~java
Customer customer = em.find(Customer.class, customerId);
customer.changeName("Tên mới");

// Không cần UPDATE ngay tại dòng setter.
// Khi flush/commit, provider đồng bộ thay đổi phù hợp.
~~~

Vì context cần theo dõi managed entities, số lượng entity và graph đã nạp cũng ảnh hưởng bộ nhớ.

### 1.2. Persistence context và transaction không phải cùng một thứ

**Transaction** xác định phạm vi atomicity/commit/rollback của dữ liệu. **Persistence context** xác định những Java instances nào được JPA quản lý.

Một EntityManager resource-local có thể tiếp tục tồn tại sau commit nếu chưa đóng, trong khi một transaction-scoped context do container quản lý có vòng đời gắn với transaction. Điều quan trọng là:

- **flush** không kết thúc transaction;
- **clear** không kết thúc transaction;
- **commit** không nhất thiết là lệnh clear trên mọi kiểu EntityManager;
- **rollback** không tự hoàn nguyên field Java của tất cả những object đang giữ tham chiếu.

Cần hiểu cả hai phạm vi trước khi chia lô.

## 2. EntityManager.flush() thực sự làm gì?

Phương thức:

~~~java
em.flush();
~~~

yêu cầu JPA đồng bộ trạng thái pending của persistence context với database trong transaction thích hợp.

Ví dụ:

~~~java
em.persist(new Customer("C001", "Lan"));
em.persist(new Customer("C002", "Minh"));
em.flush();
~~~

Provider có thể phát:

~~~sql
INSERT INTO customers (code, name) VALUES ('C001', 'Lan');
INSERT INTO customers (code, name) VALUES ('C002', 'Minh');
~~~

Chi tiết SQL phụ thuộc ID strategy, provider, batching, schema và trạng thái entity. Với **GenerationType.IDENTITY**, một INSERT có thể chạy sớm ngay khi persist để lấy generated key, nên không được hiểu rằng “mọi INSERT chỉ diễn ra khi flush”.

### 2.1. Flush có thể gửi INSERT, UPDATE và DELETE

| Thao tác trên managed entity | SQL có thể được thực thi khi flush |
|---|---|
| persist entity mới | INSERT |
| Sửa basic field | UPDATE khi dirty checking phát hiện thay đổi cần ghi |
| remove managed entity | DELETE |
| Đổi owning side của association | UPDATE FK hoặc thao tác bảng nối |
| Thêm/xóa collection theo mapping | INSERT/DELETE bảng nối, UPDATE FK hoặc DELETE orphan theo lifecycle |
| @Version | SQL liên quan đến kiểm tra/tăng version của entity |

Không thể suy ra **một entity luôn sinh một SQL**: cascade, inheritance, collection, generated values, trigger và provider có thể tạo số statement khác nhau.

### 2.2. Flush không phải commit

~~~java
EntityTransaction tx = em.getTransaction();
tx.begin();

em.persist(new Customer("C003", "An"));
em.flush(); // SQL đã được gửi trong transaction.

tx.rollback(); // DB không giữ thay đổi chưa commit.
~~~

Sau flush, những thay đổi có thể đã được DB kiểm tra và ghi trong **giao dịch chưa commit**, nhưng transaction vẫn có thể rollback. Không được dùng flush như bằng chứng bản ghi đã được commit và có thể nhìn thấy bởi mọi transaction khác.

### 2.3. Tại sao chủ động flush trước khi clear?

Nếu ứng dụng có nhiều managed entities với thay đổi pending, gọi:

~~~java
em.clear();
~~~

mà **chưa flush** sẽ làm chúng detached khỏi context; những thay đổi chưa được đồng bộ có thể không được ghi xuống database.

Thứ tự an toàn khi cần giữ pending changes:

~~~java
em.flush();
em.clear();
~~~

Thao tác thứ nhất yêu cầu gửi các thay đổi; thao tác thứ hai giải phóng các managed references và tracking state của context.

### 2.4. Thời điểm flush tự động

JPA có flush mode phổ biến:

- **FlushModeType.AUTO**: provider phải bảo đảm tác động của pending changes lên kết quả query theo semantics của flush mode, và có thể thực hiện flush trước query khi cần.
- **FlushModeType.COMMIT**: chủ yếu đồng bộ ở commit; việc pending changes có được phản ánh vào query trước commit có semantics không được xác định đầy đủ bởi mode này.

Vì vậy một query giữa vòng lặp có thể kích hoạt flush sớm tùy flush mode và provider:

~~~java
em.persist(customer);

Long count = em.createQuery(
    "select count(c) from Customer c", Long.class
).getSingleResult();
~~~

Không nên đặt query lặp không cần thiết trong mỗi iteration và giả định SQL chỉ chạy đúng ở chunk boundary. **Flush mode không thay thế explicit flush trước clear**, và **COMMIT không có nghĩa có thể commit mà không flush các thay đổi phù hợp**.

## 3. EntityManager.clear() thực sự làm gì?

Phương thức:

~~~java
em.clear();
~~~

**detaches toàn bộ entities hiện đang managed trong persistence context**. Nó không xóa database records, không rollback transaction và không tự xóa biến Java.

Trước clear:

~~~java
Customer customer = em.find(Customer.class, customerId);

System.out.println(em.contains(customer)); // true.
~~~

Sau clear:

~~~java
em.clear();

System.out.println(em.contains(customer)); // false.
~~~

Object **customer** vẫn tồn tại trong Java nếu biến còn tham chiếu, nhưng nó là **detached** đối với context ấy.

### 3.1. Clear không phải DELETE

~~~java
Customer customer = em.find(Customer.class, customerId);
em.clear();

// Bản ghi customer vẫn tồn tại trong database.
~~~

SQL DELETE chỉ đến từ thao tác remove/bulk delete/constraint cascade hoặc đường ghi khác; **clear** không có nghĩa “xóa tất cả entity khỏi database”.

### 3.2. Clear không giải phóng mọi bộ nhớ trong ứng dụng

Nếu caller vẫn giữ:

~~~java
List<Customer> allCustomers = new ArrayList<>();

for (...) {
    Customer customer = ...;
    em.persist(customer);
    allCustomers.add(customer);
}

em.flush();
em.clear();
~~~

thì **allCustomers** vẫn giữ hàng loạt object Java. Clear chỉ bỏ references/tracking được context giữ; object sẽ chỉ được GC thu hồi khi không còn strong references khác và theo lifecycle GC.

Để thực sự giảm peak memory, phải đồng thời:
- tránh giữ toàn bộ entity trong list bên ngoài;
- xử lý input theo streaming/pagination/chunk khi có thể;
- giới hạn associations đã load;
- không tích lũy các DTO, log buffers hoặc byte arrays/LOB vô hạn.

### 3.3. Clear không tự xóa second-level cache

JPA persistence context thường được gọi là **first-level cache**. **em.clear()** tác động đến context hiện tại, không đồng nghĩa xóa **second-level cache** của EntityManagerFactory hay query cache của provider.

Muốn evict second-level cache, API và phạm vi khác:

~~~java
emf.getCache().evict(Customer.class, customerId);
// Ví dụ API để evict entry L2 cache; không thay em.clear().
~~~

Không nên làm evict L2 hàng loạt như một bước mặc định sau mỗi chunk vì có thể làm giảm hiệu quả caching và ảnh hưởng các request khác.

### 3.4. Clear khiến các thay đổi tiếp theo không được tracked

~~~java
Customer c = em.find(Customer.class, customerId);

em.flush();
em.clear();

c.changeName("Sau clear");

// c detached: thay đổi này không tự được ghi khi commit.
~~~

Nếu cần sửa tiếp, hãy nạp lại managed entity:

~~~java
Customer managedAgain = em.find(Customer.class, customerId);
managedAgain.changeName("Sau clear");
~~~

Hoặc merge detached source và **dùng instance trả về**:

~~~java
Customer managedAgain = em.merge(c);
managedAgain.changeName("Sau clear");
~~~

Merge có những rủi ro khi source cũ chứa state không phù hợp; nếu chỉ biết ID và vài field cần sửa, **find rồi cập nhật đúng field** thường dễ kiểm soát hơn.

## 4. Flush rồi clear: thứ tự và vòng đời của một chunk

Kỹ thuật batch phổ biến:

~~~java
for (int i = 0; i < inputs.size(); i++) {
    em.persist(new Customer(
        inputs.get(i).code(),
        inputs.get(i).name()
    ));

    if ((i + 1) % BATCH_SIZE == 0) {
        em.flush();
        em.clear();
    }
}
~~~

Nếu batch size bằng 100, lần flush/clear diễn ra sau 100, 200, 300... entities.

~~~text
Chunk 1:  Customer 1  ... Customer 100
            persist
            persist
              ...
            flush  → SQL cần thiết tới DB
            clear  → những entities vừa xử lý trở thành detached

Chunk 2:  Customer 101 ... Customer 200
            persist ...
            flush
            clear

Chunk 3:  Customer 201 ... Customer 300
            ...
~~~

### 4.1. Vì sao flush trước clear?

Sai:

~~~java
if (count % 100 == 0) {
    em.clear();
    em.flush();
}
~~~

Pending changes có thể đã bị tách ra trước khi flush, khiến thiếu INSERT/UPDATE. Đúng:

~~~java
if (count % 100 == 0) {
    em.flush();
    em.clear();
}
~~~

Đây là quy tắc trọng tâm của bài học: **muốn giữ các thay đổi đang chờ, phải flush trước khi clear**.

### 4.2. Xử lý lô cuối ít hơn batch size

Nếu có 250 records và batch size 100:

~~~text
100  → flush + clear
200  → flush + clear
250  → phần dư 50 records
~~~

Không được bỏ quên phần dư:

~~~java
if (count % BATCH_SIZE != 0) {
    em.flush();
    em.clear();
}
~~~

Ngoài ra, transaction **commit()** có thể tự flush những thay đổi chưa đồng bộ, nhưng explicit flush phần cuối giúp lỗi SQL có thể xuất hiện tại boundary do code xác định. Không cần clear cuối cùng chỉ vì commit sẽ đóng transaction-scoped context; thêm clear khi muốn đảm bảo context gọn cho việc xử lý tiếp theo trong cùng EntityManager.

### 4.3. Nên chọn batch size bao nhiêu?

Không có con số luôn đúng. Một số lựa chọn thử nghiệm phổ biến là **25, 50, 100 hoặc 500 entities mỗi lần flush/clear**, tùy kích thước graph, DB, provider, memory và workload.

**Batch size ở vòng lặp Java không nhất thiết bằng JDBC batch size.** Cần phân biệt:
- **Flush/clear interval:** số entity hoặc đơn vị công việc giữ managed trước khi đồng bộ/detach.
- **JDBC batch size:** số statements tương thích gom vào một batch ở tầng driver khi provider hỗ trợ.
- **Transaction chunk size:** số đơn vị công việc commit trong một transaction.

Ba con số này có thể bằng nhau hoặc khác nhau tùy mục tiêu.

## 5. Ví dụ JPA thuần: nhập nhiều Customer bằng một transaction

Entity đơn giản:

~~~java
package com.example.batch;

import jakarta.persistence.*;

@Entity
@Table(
    name = "customers",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customers_code",
        columnNames = "external_code"
    )
)
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "customer_seq")
    @SequenceGenerator(
        name = "customer_seq",
        sequenceName = "customer_seq",
        allocationSize = 50
    )
    private Long id;

    @Column(name = "external_code", nullable = false, length = 40)
    private String externalCode;

    @Column(name = "name", nullable = false, length = 120)
    private String name;

    protected Customer() { }

    public Customer(String externalCode, String name) {
        if (externalCode == null || externalCode.isBlank()) {
            throw new IllegalArgumentException("externalCode bắt buộc");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name bắt buộc");
        }
        this.externalCode = externalCode;
        this.name = name;
    }

    public Long getId() { return id; }

    public void rename(String nextName) {
        if (nextName == null || nextName.isBlank()) {
            throw new IllegalArgumentException("name không hợp lệ");
        }
        this.name = nextName;
    }
}
~~~

DTO đầu vào:

~~~java
public record CustomerInput(String externalCode, String name) { }
~~~

Batch service sử dụng **EntityManagerFactory** và **EntityManager resource-local**:

~~~java
package com.example.batch;

import jakarta.persistence.*;
import java.util.List;
import java.util.Objects;

public class CustomerImporter {
    private static final int FLUSH_INTERVAL = 100;

    private final EntityManagerFactory emf;

    public CustomerImporter(EntityManagerFactory emf) {
        this.emf = Objects.requireNonNull(emf);
    }

    public int importAll(List<CustomerInput> inputs) {
        Objects.requireNonNull(inputs);

        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();
        int processed = 0;

        try {
            tx.begin();

            for (CustomerInput input : inputs) {
                Customer customer = new Customer(
                    input.externalCode(),
                    input.name()
                );

                em.persist(customer);
                processed++;

                if (processed % FLUSH_INTERVAL == 0) {
                    em.flush();
                    em.clear();
                }
            }

            if (processed % FLUSH_INTERVAL != 0) {
                em.flush();
                em.clear();
            }

            tx.commit();
            return processed;
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackEx) {
                    ex.addSuppressed(rollbackEx);
                }
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
~~~

Ví dụ nêu rõ semantics: **toàn bộ importAll là một transaction**. Nếu flush chunk thứ 8 thất bại và transaction rollback, các INSERT đã flush ở chunk 1–7 trong cùng transaction cũng bị rollback. Không có commit từng 100 hàng ở đây.

### 5.1. Kết quả trong từng bước

~~~text
Input 1..100
  em.persist(Customer)
  em.flush()   → DB nhận các statement trong transaction
  em.clear()   → context không giữ Customer 1..100

Input 101..200
  em.persist(Customer)
  em.flush()
  em.clear()

...
Cuối cùng
  tx.commit()  → commit toàn bộ những statement đã flush nếu thành công
~~~

Vì entity dùng **GenerationType.SEQUENCE** với allocationSize 50, provider có thể tối ưu việc cấp ID so với INSERT lấy ID từng bản ghi, tùy hỗ trợ và cấu hình. **Sequence và JDBC batching là hai cơ chế riêng**; cần kiểm chứng provider/driver/database, không cho rằng allocationSize tự bật JDBC batching.

### 5.2. Schema tương ứng

Ví dụ PostgreSQL:

~~~sql
CREATE SEQUENCE customer_seq START WITH 1 INCREMENT BY 50;

CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    external_code VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL
);
~~~

**Quan trọng:** cách tăng sequence vật lý và chiến lược phân bổ ID phải tương thích với provider và cấu hình allocationSize thực tế. Không tự chạy script trên một schema cũ dùng sequence increment khác mà chưa kiểm tra migration/generator. Code được dùng để minh họa việc có thể chọn pooled sequence trong batch imports.

### 5.3. Input List vẫn có thể giữ nhiều bộ nhớ

Ví dụ nhận **List<CustomerInput>**, nên caller vẫn có thể giữ toàn bộ 100.000 DTO trong RAM. Flush/clear chỉ giới hạn lượng **managed entity state**; để giảm tổng peak memory hơn nữa, đọc input bằng parser streaming hoặc iterator/pagination và đưa từng phần vào importer. Không tích lũy toàn bộ entity output trong một collection nếu mục tiêu là tiết kiệm RAM.

### 5.4. Không lạm dụng flush sau mỗi entity

~~~java
for (CustomerInput input : inputs) {
    em.persist(new Customer(input.externalCode(), input.name()));
    em.flush();
}
~~~

Gọi flush sau từng record có thể làm giảm khả năng nhóm công việc, tăng số lần đồng bộ và chi phí round-trip. Ngoại lệ là khi nghiệp vụ thật sự cần kiểm tra constraint hoặc nhận dữ liệu ngay từng record. Nếu chỉ muốn tiết kiệm bộ nhớ, dùng chunk interval phù hợp thay vì flush từng dòng.

## 6. Flush/clear có giảm bộ nhớ nhưng chưa chắc giảm chi phí database

Phải phân biệt các lớp hiệu năng:

~~~text
Java input generation / parsing
          ↓
JPA persistence context (managed entities, dirty checking)
          ↓
Hibernate/EclipseLink SQL action queue
          ↓
JDBC driver batching (nếu được cấu hình/hỗ trợ)
          ↓
Database constraints / indexes / log / locks
          ↓
Transaction commit
~~~

Flush/clear xử lý chủ yếu hai lớp đầu. Tốc độ thực tế còn phụ thuộc:
- Network round trips và JDBC batching;
- ID strategy;
- Số index và FK constraints;
- Triggers, generated columns;
- Kích thước dữ liệu;
- Batch insert/update ordering;
- Transaction log, locks và concurrent workloads;
- Throughput của DB/server;
- Số SQL statements do cascade/relationship mapping sinh.

Nếu bottleneck là database đã quá tải, giảm số managed entities không tự tăng throughput. Nếu bottleneck là JVM heap do persistence context quá lớn, flush/clear có thể giúp rất đáng kể.

## 7. Cấu hình JDBC batching với Hibernate

**Hibernate là một JPA provider** và có những cấu hình tối ưu riêng. Chúng **không thuộc JPA chuẩn**, nên cần kiểm tra tên property và khả năng hỗ trợ ở phiên bản Hibernate/driver đang sử dụng.

Ví dụ Spring Boot properties:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
~~~

Ý nghĩa chung:

- **hibernate.jdbc.batch_size**: yêu cầu Hibernate gom các statement tương thích thành JDBC batches với kích thước tối đa phù hợp.
- **hibernate.order_inserts**: có thể sắp INSERT theo entity/table để tạo các nhóm statement dễ batch hơn, tùy chi phí và đặc điểm provider.
- **hibernate.order_updates**: có thể sắp UPDATE để tối ưu batching và giảm một số dạng tranh chấp lock trong những workload nhất định.

Một vòng lặp flush/clear mỗi 100 entity **không tự bật** những property này. Ngược lại, chỉ bật JDBC batch size nhưng duy trì context với hàng triệu entity cũng chưa giải quyết được memory pressure.

### 7.1. GenerationType.IDENTITY có thể hạn chế insert batching

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Với Hibernate, INSERT dùng IDENTITY thường cần được thực thi sớm để lấy generated key. Điều này **thường hạn chế hoặc vô hiệu JDBC insert batching** cho entity tương ứng trong những cấu hình thông dụng.

Đối với khối lượng INSERT lớn, có thể cân nhắc:
- Sequence phù hợp với pooled allocation;
- Assigned identifiers nếu domain và chiến lược collision cho phép;
- Khả năng batching theo driver và provider hiện tại;
- JDBC bulk loader, COPY hoặc phương án DB chuyên biệt nếu ORM không phải công cụ tối ưu.

Đừng đổi ID generator trên database production chỉ để tăng tốc mà chưa thiết kế migration, sequence state, foreign keys và compatibility.

### 7.2. Flush interval và JDBC batch size có thể khác nhau

Ví dụ:
- Flush interval: 200 entities;
- JDBC batch size: 50 statements.

Trong một flush, provider có thể tổ chức nhiều nhóm JDBC batch, hoặc có các statement không đủ điều kiện gộp (vì SQL khác nhau, IDENTITY, cascades, constraints...). Không bảo đảm “200 entities = chính xác 4 JDBC batches”.

### 7.3. Quan sát SQL/statistics thay vì suy đoán

Khi cần hiệu năng:
1. Đo thời gian toàn job và throughput.
2. Theo dõi heap, GC và độ lớn context.
3. Quan sát số SQL statements, số JDBC batch executions nếu provider hỗ trợ statistics.
4. Kiểm tra database wait/locks/IO.
5. Thử các mức flush interval và JDBC batch size khác nhau.
6. Chọn cấu hình dựa trên workload thật.

Log một dòng SQL cho mỗi statement không nhất thiết cho biết driver có gom batch hay không. Cần dùng statistics hoặc công cụ đo thích hợp.

## 8. Transaction: một giao dịch lớn hay nhiều giao dịch nhỏ?

Đây là quyết định **độc lập với flush/clear**.

### 8.1. Một transaction cho toàn bộ job

~~~text
begin transaction
  chunk 1 → flush + clear
  chunk 2 → flush + clear
  chunk 3 → flush + clear
commit transaction
~~~

Ưu điểm:
- Toàn bộ job **atomic**: thành công hết hoặc rollback hết.
- Không cần quy trình resume nửa chừng phức tạp.
- Dữ liệu trung gian chưa commit không bị công bố như kết quả cuối cho transaction khác, tùy isolation.

Nhược điểm:
- Database có thể giữ transaction log, locks, MVCC state hoặc resource lâu.
- Nếu lỗi muộn, toàn bộ khối lượng công việc bị rollback.
- Flush/clear không giảm độ dài transaction.
- Query trong transaction dài có thể chịu tác động isolation và concurrent writes.

### 8.2. Một transaction cho mỗi chunk

~~~text
chunk 1: begin → persist → flush → commit
chunk 2: begin → persist → flush → commit
chunk 3: begin → persist → flush → commit
~~~

Ưu điểm:
- Giảm thời gian mỗi transaction;
- Cho phép checkpoint/resume nếu thiết kế phù hợp;
- Lỗi ở chunk sau không tự rollback những chunk đã commit.

Nhược điểm:
- **Không còn atomicity cho toàn bộ job**.
- Nếu chunk thứ 3 lỗi, chunk 1 và 2 có thể đã tồn tại.
- Cần idempotency, tracking offset/lastId, xử lý retry và reconciliation.
- Không thể giả định đơn giản rằng clear sau commit đủ để kết thúc mọi EntityManager/context trong Spring.

Chọn transaction chunking theo **yêu cầu nghiệp vụ**. Nếu toàn bộ import phải hoặc thành công hết hoặc không có gì, một transaction lớn có thể cần thiết dù đắt. Nếu cho phép nhập dần, commit từng chunk có thể phù hợp nhưng phải xử lý partial success.

### 8.3. Không cố bắt lỗi từng entity rồi tiếp tục cùng transaction đã lỗi

Ví dụ dễ sai:

~~~java
try {
    em.persist(customer);
    em.flush();
} catch (PersistenceException ex) {
    // Bỏ qua lỗi và tiếp tục persist customer khác?
}
~~~

Một lỗi SQL hoặc persistence exception có thể làm transaction bị **rollback-only** hoặc context không còn nhất quán. Không nên tiếp tục sử dụng transaction ấy như không có gì xảy ra.

Nếu nghiệp vụ muốn bỏ qua các record sai và tiếp tục:
- Validate dữ liệu trước khi persist;
- Tách record/chunk vào transaction riêng;
- Lưu bảng lỗi và resume checkpoint;
- Dùng DB staging table hoặc batch import workflow phù hợp;
- Không quên unique constraints và idempotent retry.

## 9. Ví dụ Spring Data JPA: cập nhật từng lô

Một service Spring dùng EntityManager được inject:

~~~java
@Service
public class CustomerBatchService {
    private static final int FLUSH_INTERVAL = 100;

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void renameCustomers(List<Long> customerIds, String suffix) {
        int processed = 0;

        for (Long id : customerIds) {
            Customer customer = em.find(Customer.class, id);
            if (customer == null) {
                continue;
            }

            customer.rename(customer.getName() + suffix);
            processed++;

            if (processed % FLUSH_INTERVAL == 0) {
                em.flush();
                em.clear();
            }
        }

        if (processed % FLUSH_INTERVAL != 0) {
            em.flush();
            em.clear();
        }
    }
}
~~~

Để snippet biên dịch, entity Customer cần thêm method:

~~~java
public String getName() {
    return name;
}
~~~

Các annotation Spring dùng package của Spring tương ứng; **@PersistenceContext** thuộc Jakarta Persistence.

Ví dụ nhấn mạnh:
- Entity được **find** và đang managed khi gọi rename;
- Dirty checking ghi update khi flush;
- Clear detaches những Customer đã xử lý;
- Transaction vẫn là **một transaction lớn** vì một @Transactional method bao toàn bộ vòng lặp.

### 9.1. Không phải cứ saveAll là đã chia flush/clear

~~~java
customerRepository.saveAll(customers);
~~~

Phương thức saveAll thực hiện lưu nhiều entity theo repository semantics, nhưng **không có hợp đồng rằng nó sẽ tự flush/clear mỗi 100 entity hoặc cấu hình JDBC batch tối ưu**. saveAllAndFlush có ý nghĩa flush sau xử lý theo API tương ứng, nhưng cũng **không thay clear**, không tự commit một transaction bao ngoài, và không tự bảo đảm bounded persistence context.

Nếu muốn kiểm soát batch ingestion ở quy mô lớn, dùng EntityManager hoặc repository/service được thiết kế cho chunks, hiểu rõ persist/merge và transaction scope.

### 9.2. @Transactional phải thực sự được áp dụng

Spring proxy thông dụng có giới hạn self-invocation: một method gọi method annotated @Transactional trên **chính cùng instance** có thể không đi qua proxy.

Nếu cần một transaction mới cho mỗi chunk:
- Đặt phương thức xử lý chunk trong một Spring bean riêng và gọi qua bean đó;
- Hoặc dùng TransactionTemplate / transaction API phù hợp;
- Xác định rõ Propagation.REQUIRES_NEW nếu contract yêu cầu.

Không chỉ thêm @Transactional lên một method private rồi giả định mỗi lần gọi nội bộ sẽ commit.

## 10. Dùng flush/clear khi cập nhật, không chỉ khi INSERT

Batch updates cũng có thể tạo context lớn:

~~~java
for (Long id : customerIds) {
    Customer customer = em.find(Customer.class, id);
    customer.rename("Customer-" + id);
}
~~~

Các Customer được tải sẽ managed và giữ trong context đến khi clear/đóng. Có thể áp dụng:

~~~java
int processed = 0;

for (Long id : customerIds) {
    Customer customer = em.find(Customer.class, id);
    if (customer == null) {
        continue;
    }

    customer.rename("Customer-" + id);
    processed++;

    if (processed % 100 == 0) {
        em.flush();
        em.clear();
    }
}

if (processed % 100 != 0) {
    em.flush();
    em.clear();
}
~~~

### 10.1. Cẩn thận với source objects từ danh sách bên ngoài

Nếu code giữ:

~~~java
List<Customer> customers = ...; // Managed lúc ban đầu.

for (int i = 0; i < customers.size(); i++) {
    customers.get(i).rename(...);

    if ((i + 1) % 100 == 0) {
        em.flush();
        em.clear();
    }
}
~~~

Sau clear lần đầu, những Customer tiếp theo **nếu đã được load và nằm trong list từ trước** cũng bị detach, dù vòng lặp chưa xử lý chúng! Các lần rename tiếp theo chỉ sửa object detached và có thể không tạo SQL UPDATE.

Đây là bẫy trọng tâm khi xử lý nhiều entity: **clear tách toàn bộ context**, không chỉ 100 entity “vừa xử lý”.

Giải pháp:
- Tránh load tất cả entity managed trước khi bắt đầu;
- Duyệt IDs hoặc từng trang ID, tìm managed entity theo nhu cầu trong chunk;
- Nếu đã giữ detached instances, nạp lại managed target hoặc merge có kiểm soát và dùng return value;
- Không giả định clear chỉ ảnh hưởng những entity cuối cùng đã thao tác.

### 10.2. Không giữ tham chiếu managed xuyên chunk boundary

~~~java
Customer first = em.find(Customer.class, 1L);

em.flush();
em.clear();

first.rename("Đổi lần nữa"); // first detached.
~~~

Nếu cần sửa lại Customer#1:

~~~java
Customer managedAgain = em.find(Customer.class, 1L);
managedAgain.rename("Đổi lần nữa");
~~~

Dù hai biến cùng database ID, chúng có thể khác Java reference sau clear. Điều đó là bình thường.

## 11. Phân trang theo ID và flush/clear khi xử lý dữ liệu lớn

Nếu cần cập nhật mọi Customer trong database, tải toàn bộ entity bằng:

~~~java
List<Customer> all = em.createQuery(
    "select c from Customer c", Customer.class
).getResultList();
~~~

rồi mới xử lý và clear có thể **không đạt mục tiêu**: danh sách all vẫn giữ references, và sau lần clear đầu, những phần tử còn lại cũng trở thành detached.

Thay vào đó, có thể phân trang **chỉ lấy ID**, rồi nạp managed entities cho từng chunk.

### 11.1. Keyset pagination theo khóa chính ổn định

~~~java
public int normalizeNames(EntityManager em, int pageSize) {
    long lastId = 0L;
    int changed = 0;

    while (true) {
        List<Long> ids = em.createQuery(
            """
            select c.id
            from Customer c
            where c.id > :lastId
            order by c.id asc
            """,
            Long.class
        )
        .setParameter("lastId", lastId)
        .setMaxResults(pageSize)
        .getResultList();

        if (ids.isEmpty()) {
            break;
        }

        for (Long id : ids) {
            Customer customer = em.find(Customer.class, id);
            if (customer != null) {
                customer.rename(customer.getName().trim());
                changed++;
            }
        }

        em.flush();
        em.clear();

        lastId = ids.get(ids.size() - 1);
    }

    return changed;
}
~~~

Phương thức này **phải được gọi trong transaction thích hợp**. Code giả định Customer có getName/rename và ID dương. Nếu dùng UUID, composite key hoặc khóa âm, phải điều chỉnh cursor và cách sắp xếp.

**Ưu điểm**:
- Không tải toàn bộ managed graph một lúc;
- Chỉ giữ một trang scalar IDs và entities trong trang;
- Thứ tự theo ID không đổi khi chỉ sửa name;
- Tránh nhiều vấn đề hiệu năng của OFFSET lớn.

### 11.2. Keyset không tự bảo đảm snapshot dữ liệu

Nếu transaction khác đồng thời INSERT/DELETE/UPDATE:
- Row mới có ID lớn hơn lastId có thể xuất hiện;
- Row bị xóa có thể không còn tìm thấy;
- Điều kiện lọc thay đổi có thể khiến row vào/ra tập kết quả;
- Isolation level quyết định các dữ liệu transaction đang nhìn thấy.

Nếu cần xử lý tập cố định tại một thời điểm, phải chọn snapshot/isolation hoặc cách ghi nhận tập IDs phù hợp. Có thể cố định maxId ban đầu để giới hạn tập mới, nhưng maxId **không giải quyết tất cả concurrent deletes/updates**.

### 11.3. Offset pagination có thể bỏ sót bản ghi

Giả sử query lấy Customer status=PENDING và sau xử lý chuyển status=DONE. Nếu dùng:

~~~java
query.setFirstResult(pageIndex * 100)
     .setMaxResults(100);
~~~

trang đầu đã rời tập PENDING sau flush; trang thứ hai với OFFSET 100 có thể **bỏ qua 100 bản ghi còn lại**. Keyset dựa trên ID bất biến giúp tránh sự phụ thuộc vào vị trí OFFSET khi trạng thái filter thay đổi theo hướng ấy, dù vẫn phải xét isolation và concurrent writes.

### 11.4. Stream/cursor và clear không tự portable

Provider có thể hỗ trợ stream hoặc scrolling results. Nhưng **clear khi iterator/cursor đang mở** có thể tác động tới object state, fetch, JDBC cursor hoặc việc tiếp tục duyệt. Với JPA portable, cách dễ điều khiển là phân trang IDs hoặc chunk input ngoài ORM, xử lý trang, flush/clear, rồi đọc trang tiếp theo.

Nếu dùng Hibernate ScrollableResults/StatelessSession hoặc driver cursor, phải theo API và lifecycle tài nguyên của phiên bản đó. Không mặc định Query.getResultStream với hàng triệu managed entities rồi clear giữa stream sẽ luôn an toàn.

## 12. Quan hệ và khóa ngoại sau clear

Khi batch ghi child rows tham chiếu một parent đã tồn tại, clear có thể biến parent reference cũ thành detached. Điều này dễ dẫn tới lỗi **detached entity passed to persist**, hoặc associations bị ghi sai khi cascade/state không phù hợp.

Ví dụ:

~~~java
@Entity
@Table(name = "departments")
public class Department {
    @Id
    private Long id;
    // ...
}
~~~

~~~java
@Entity
@Table(name = "employees")
public class Employee {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "department_id", nullable = false)
    private Department department;

    protected Employee() { }

    public Employee(Department department) {
        this.department = Objects.requireNonNull(department);
    }
}
~~~

### 12.1. Bẫy: giữ parent reference xuyên chunk

~~~java
Department department = em.find(Department.class, departmentId);

for (int i = 0; i < employees.size(); i++) {
    Employee employee = new Employee(department);
    em.persist(employee);

    if ((i + 1) % 100 == 0) {
        em.flush();
        em.clear();
        // department giờ detached.
    }
}
~~~

Sau chunk đầu tiên, **department không còn managed** trong context. Có provider/mapping vẫn ghi FK dựa trên ID reference detached, nhưng cascade và lifecycle có thể gây lỗi. Đừng xây workflow với giả định parent vẫn managed sau clear.

### 12.2. Nạp lại managed reference trong chunk mới

~~~java
Department managedDepartment = em.getReference(
    Department.class, departmentId);

em.persist(new Employee(managedDepartment));
~~~

Có thể lấy lại reference sau mỗi clear:

~~~java
Department managedDepartment = null;
int processed = 0;

for (EmployeeInput input : inputs) {
    if (managedDepartment == null) {
        managedDepartment = em.getReference(
            Department.class, departmentId);
    }

    em.persist(new Employee(managedDepartment));
    processed++;

    if (processed % 100 == 0) {
        em.flush();
        em.clear();
        managedDepartment = null;
    }
}
~~~

**getReference** có thể chưa query database ngay, nên không phải phép kiểm tra tồn tại. Một ID sai có thể chỉ gây lỗi khi truy cập thuộc tính hoặc FK bị DB từ chối. Nếu service phải kiểm tra quyền/trạng thái Department trước khi ghi, dùng find hoặc query rõ ràng phù hợp hơn.

### 12.3. Không cascade persist sang parent độc lập

~~~java
@ManyToOne(cascade = CascadeType.PERSIST)
private Department department;
~~~

Không nên thêm cascade PERSIST vào Department đã tồn tại chỉ để “dễ lưu Employee”. Nếu new Employee trỏ tới detached Department, cascade persist có thể gây lỗi. Dùng managed parent hoặc managed reference của parent và chọn cascade theo ownership nghiệp vụ.

### 12.4. Không clear giữa lúc dựng aggregate chưa hoàn chỉnh

Với Order–OrderLine:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Nếu một Order có nhiều Lines, đừng clear giữa lúc chưa hoàn thiện graph rồi tiếp tục thêm Line vào Order đã detached và mong cascade tự áp dụng.

Có thể:
1. Xây Order aggregate có kích thước hợp lý.
2. Gán cả owning/inverse sides qua helper.
3. Persist root và children theo cascade.
4. Flush sau khi aggregate hoàn tất.
5. Clear trước khi bắt đầu aggregate khác.

Nếu một Order có hàng triệu child, cần ingestion design riêng: persist root, lấy managed references và ghi child theo chunks với transaction/idempotency phù hợp. Không chỉ thêm clear vào giữa một aggregate lớn.

### 12.5. Clear không tự kích hoạt orphanRemoval

Clear detach parent và children, **không có nghĩa xóa tất cả children**. OrphanRemoval liên quan child bị loại khỏi managed relationship theo semantics thích hợp. Ngược lại, nếu merge một detached parent với collection thiếu phần tử, orphan removal có thể gây DELETE ngoài ý muốn. Khi cập nhật riêng child, nạp child managed và sửa trường cần thiết thay vì merge partial graph.

## 13. Sau clear, merge trả về managed object khác

~~~java
Customer source = em.find(Customer.class, 10L);

em.flush();
em.clear();

source.rename("Từ detached"); // Không còn được dirty checking.

Customer managed = em.merge(source);
managed.rename("Giá trị cuối");

em.flush();
~~~

Sau clear:
- source detached;
- merge copy state sang một managed target;
- managed return value phải được dùng để sửa tiếp;
- source không tự trở thành managed.

Sai:

~~~java
em.merge(source);
source.rename("Sửa sau merge"); // Không tự được tracking.
~~~

Khi source detached lâu hoặc chỉ chứa một snapshot chưa đầy đủ, merge có thể ghi đè state mới bằng state cũ. Nếu chỉ cần sửa một field có ID, **find managed entity và cập nhật đúng field** thường an toàn hơn.

### 13.1. Optimistic locking

~~~java
@Version
private Long version;
~~~

Nếu source giữ version cũ, merge/flush có thể gây **OptimisticLockException** khi transaction khác đã sửa cùng row. Không sửa version thủ công để ép merge và không tiếp tục transaction đã thất bại. Version bảo vệ xung đột entity theo semantics JPA, không tự bảo vệ toàn bộ bất biến nhiều hàng.

## 14. Bulk JPQL DML khác xử lý managed entities

Với hàng triệu row cần cùng một cập nhật đơn giản, có thể không cần find từng entity:

~~~java
int updated = em.createQuery(
    """
    update Customer c
    set c.name = :newName
    where c.name = :oldName
    """
)
.setParameter("newName", "Chưa đặt tên")
.setParameter("oldName", "")
.executeUpdate();
~~~

Bulk JPQL DML:
- Có thể ghi nhiều rows bằng một statement thay vì dirty checking từng entity;
- Không gọi callbacks/cascades thông thường như thao tác managed entity trên từng row;
- Không tự đồng bộ managed objects đã load;
- Có quy tắc version khác, thường không tự tăng @Version như dirty checking.

### 14.1. Trật tự khi dùng bulk UPDATE/DELETE cùng EntityManager

~~~java
em.flush(); // Đẩy pending changes trước bulk.

int changed = em.createQuery(
    "update Customer c set c.name = :name where c.id > :minId")
    .setParameter("name", "Chuẩn hóa")
    .setParameter("minId", 100L)
    .executeUpdate();

em.clear(); // Bỏ những managed instances có thể đã stale.
~~~

Nếu trước bulk có pending changes, flush trước giúp tránh thứ tự ghi khó đoán. Sau bulk, clear để các entity đã load trước không giữ state cũ và bị dùng lại. Khi cần đọc tiếp, find/query trong context sau clear.

### 14.2. Bulk DELETE và cascade

~~~java
int deleted = em.createQuery(
    "delete from Customer c where c.name = :name")
    .setParameter("name", "Đã vô hiệu")
    .executeUpdate();
~~~

Bulk delete không thực hiện mọi JPA cascade/orphanRemoval/callback như em.remove cho từng managed entity, và FK có thể từ chối DELETE nếu còn child rows. Chỉ dùng bulk DML khi dữ liệu và domain rules cho phép. Nếu cần callbacks hoặc lifecycle riêng từng entity, dùng batch xử lý managed entities hoặc workflow DB phù hợp.

### 14.3. Refresh để đọc dữ liệu DB-generated

Nếu database trigger/default sinh giá trị mới sau INSERT/UPDATE, flush **không nhất thiết** cập nhật mọi field do DB sinh trên Java instance ngay. Trong trường hợp mapping phù hợp và entity vẫn managed:

~~~java
em.flush();
em.refresh(customer);
String normalized = customer.getNormalizedCode();
em.clear();
~~~

Ví dụ giả định Customer có field/getter normalizedCode. **refresh** có thể phát SELECT và thay thế state đang quản lý; cần sắp đúng thứ tự để không mất pending modifications.

Sau clear, entity đã detached:

~~~java
em.clear();
em.refresh(customer); // Không hợp lệ nếu customer detached.
~~~

Muốn đọc lại sau clear, dùng em.find trong context mới.

## 15. Flush không đồng nghĩa một record đã commit

Trong batch job:

~~~java
processed++;
~~~

chỉ nói input đã được xử lý ở mức code, **không chứng minh đã commit**.

| Chỉ số | Ý nghĩa |
|---|---|
| attempted | Input đã thử xử lý |
| persistedToContext | Entity được gọi persist |
| flushed | Đã qua điểm đồng bộ SQL trong transaction |
| committed | Thay đổi đã được transaction commit thành công |
| failed | Record/chunk có lỗi hoặc rollback |
| skipped | Input được bỏ qua theo policy |

Nếu import chạy **một transaction lớn** với flush/clear 100 lần rồi bị rollback tại commit, không được báo “đã commit 10.000 rows” chỉ vì đã flush 10.000 rows.

### 15.1. Các side effects không thể rollback

~~~text
flush chunk thành công
    → gửi email "đã nhập"
    → chunk sau lỗi
    → rollback DB transaction
    → email vẫn đã gửi
~~~

Nếu cần phát sự kiện/email sau khi dữ liệu đã commit, dùng after-commit flow hoặc **transactional outbox** phù hợp. **Flush không phải commit boundary** cho những side effects bên ngoài DB.

## 16. Chọn phương án xử lý nhiều entity

| Bài toán | Giải pháp cân nhắc | Cảnh báo |
|---|---|---|
| INSERT nhiều entity có associations/callbacks | persist theo chunk + flush/clear | Giữ owning sides và cascade đúng |
| UPDATE từng entity với domain methods | find theo ID/page + mutate + flush/clear | Giữ @Version/validation |
| UPDATE hàng triệu rows cùng điều kiện | Bulk JPQL UPDATE hoặc SQL | Bỏ qua lifecycle thông thường, stale context |
| DELETE nhiều rows có quan hệ | Batch em.remove hoặc DB workflow | Xét FK, cascade, callbacks |
| Import rất lớn, dữ liệu phẳng | JDBC batching, staging table, DB COPY/loader | Có thể bỏ bớt semantics ORM |
| Báo cáo đọc lớn | DTO projection, paging, stream theo provider | Tránh dựng toàn bộ managed graph |
| Muốn checkpoint/resume | Chunk transactions + idempotency | Chấp nhận partial commits |
| Muốn atomicity toàn bộ | Một transaction với flush/clear | Giới hạn locks/log/thời gian |
| Cần thông báo bên ngoài DB | After-commit/outbox | Không dựa vào flush |

Nếu chỉ cần chuyển status của một triệu rows, SQL bulk update có thể tốt hơn việc tải từng entity. Nếu mỗi row có business rule, callback, audit và optimistic locking riêng, quản lý entity theo chunk có thể đúng hơn. **Tính đúng đắn nghiệp vụ phải dẫn dắt quyết định tối ưu**.

## 17. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Mất INSERT/UPDATE | clear trước flush | Luôn flush trước clear khi cần lưu pending changes |
| Chỉ chunk đầu được cập nhật | Clear detach cả entities đã tải nhưng chưa xử lý | Nạp theo chunk/IDs |
| Transaction khác không thấy dữ liệu | Flush chưa commit | Commit thành công |
| RAM vẫn tăng | Caller giữ List entities/DTOs hoặc LOB | Streaming/paging, bỏ external references |
| FK/parent bị detached ở chunk sau | Giữ parent reference qua clear | getReference/find trong context mới |
| Cascade PERSIST gây lỗi | Cascade tới parent đã tồn tại/detached | Chọn cascade theo lifecycle |
| Child bị xóa | Merge partial graph + orphanRemoval | Thay đổi child managed có chủ đích |
| JDBC vẫn INSERT từng row | IDENTITY, batch config/driver/SQL không tương thích | Kiểm tra provider và ID strategy |
| Flush từng entity quá chậm | Quá nhiều đồng bộ | Điều chỉnh flush interval |
| Bị lỗi SQL và tiếp tục transaction | Transaction bị rollback-only/invalid | Rollback, transaction mới |
| Bulk DML xong entity còn state cũ | Bulk bypasses context | Flush trước, clear sau, reload |
| DB-triggered field chưa cập nhật | Chưa refresh/generation mapping | Refresh khi managed hoặc find lại |
| em.refresh báo detached | Gọi sau clear | Refresh trước clear hoặc tìm lại |
| OFFSET bỏ sót bản ghi | Update làm thay đổi query results | Keyset/snapshot phù hợp |
| Job giữ lock lâu | Clear không commit | Xem lại transaction chunking |
| saveAll vẫn giữ context lớn | Không cam kết clear định kỳ | Thiết kế batch service tường minh |
| N+1 | Fetch plan không phù hợp | Projection/join fetch/batch fetch |
| Retry tạo duplicate | Thiếu unique/idempotency | DB constraint và checkpoint logic |
| LAZY không load được sau clear | Entity đã detached | Fetch trước clear hoặc query lại |

## 18. Flush và clear có phạm vi toàn persistence context

Một hiểu nhầm rất nguy hiểm là “flush/clear chỉ thao tác trên 100 entity mà vòng lặp vừa xử lý”. Thực tế, với API chuẩn:

~~~java
em.flush();
em.clear();
~~~

**không có tham số danh sách entity**. Chúng tác động tới **persistence context đang được EntityManager quản lý**, không chỉ một collection do ứng dụng lựa chọn.

Giả sử một service khác đã sửa một entity chung context:

~~~java
Customer priorityCustomer = em.find(Customer.class, priorityId);
priorityCustomer.rename("Đang chỉnh dở");

// Gọi batch importer dùng cùng em:
importChunk(em, inputs);  // bên trong có em.flush(); em.clear();

priorityCustomer.rename("Chỉnh tiếp");
// priorityCustomer đã detached sau em.clear().
~~~

Lần flush của importer có thể ghi cả thay đổi của **priorityCustomer**, dù nó không thuộc input chunk. Lần clear của importer cũng detach **priorityCustomer**, khiến thay đổi về sau trên cùng reference không tự được theo dõi.

### 18.1. Hệ quả đối với service nhiều bước

Nếu một transaction cần:
1. Sửa cấu hình Customer;
2. Import một số Order;
3. Tiếp tục sửa Customer;
4. Commit tất cả;

thì **em.clear() ở bước 2** có thể làm bước 3 dùng detached object.

Cách giải quyết:
- Đặt rõ ràng boundary của batch công việc;
- Sau clear, **find lại** bất kỳ entity cần tiếp tục chỉnh sửa;
- Tách trách nhiệm sang transaction/context riêng nếu domain cho phép;
- Không gọi em.clear trong một helper được tái sử dụng ở service lớn mà không công bố side effect này;
- Dùng DTO/IDs thay vì giữ reference managed xuyên chunk.

### 18.2. Flush cũng không chỉ gửi SQL của batch hiện tại

Nếu trước khi vào importer có 10 Customer dirty khác trong cùng context, một lời gọi **em.flush()** có thể đồng bộ luôn 10 Customer ấy. Điều này có thể làm constraint lỗi sớm hơn mong đợi, hoặc tạo SQL liên quan các đơn vị nghiệp vụ khác.

Đó không phải lỗi của flush: nó làm đúng trách nhiệm đồng bộ **persistence context**. Vấn đề là thiết kế service đã hiểu sai phạm vi thao tác.

### 18.3. Không chia sẻ EntityManager giữa nhiều threads

**EntityManagerFactory** được thiết kế để quản lý việc tạo các EntityManager, còn một **EntityManager** không được dùng chung đồng thời cho nhiều threads.

Nếu parallelize import:
- Mỗi worker/task cần persistence context và transaction phù hợp;
- Không chia sẻ một EntityManager hoặc cùng managed entities giữa threads;
- Thiết kế partition/chunk tránh ghi cùng rows, kết hợp DB constraints và optimistic/pessimistic locking;
- Hạn chế số concurrent transactions theo sức tải database.

Nhiều EntityManager song song không có cùng identity map, nên clear một context không ảnh hưởng managed state của context khác; nhưng **DB concurrency** vẫn là vấn đề chung.

## 19. Kiểm thử sự phối hợp flush/clear

Nên có integration tests chạy trên provider/database gần với production. Ví dụ bên dưới giả định một JUnit test class với EntityManager được cấu hình trong transaction, import JUnit assertions, và Customer từ phần trước có getName().

### 19.1. Clear sau flush làm entity detached nhưng DB đã nhận thay đổi

~~~java
@Test
void flushThenClearDetachesEntityAndPreservesChanges() {
    Customer customer = new Customer("C001", "Lan");

    em.persist(customer);
    em.flush();

    Long id = customer.getId();

    assertTrue(em.contains(customer));

    em.clear();

    assertFalse(em.contains(customer));

    Customer reloaded = em.find(Customer.class, id);

    assertNotSame(customer, reloaded);
    assertEquals("Lan", reloaded.getName());
    assertTrue(em.contains(reloaded));
}
~~~

**Flush + clear** bảo đảm context mới không trả lại chính reference đã detach; query/find nạp lại state từ DB (theo các cơ chế cache và provider phù hợp). Đây là test về persistence identity và trạng thái managed.

### 19.2. Clear trước flush có thể làm mất UPDATE chưa đồng bộ

~~~java
@Test
void clearWithoutFlushDiscardsUnflushedUpdate() {
    Customer customer = new Customer("C002", "Minh");
    em.persist(customer);
    em.flush();
    Long id = customer.getId();

    em.clear();

    Customer managed = em.find(Customer.class, id);
    managed.rename("Tên chưa flush");

    em.clear(); // Không flush các thay đổi chưa được DB đồng bộ.

    Customer reloaded = em.find(Customer.class, id);
    assertEquals("Minh", reloaded.getName());
}
~~~

Mục đích là minh họa clear bỏ pending changes của một managed instance. Trong một cấu hình phức tạp có query hoặc automatic flush xảy ra trước clear, cần thiết kế test transaction/flush mode phù hợp để kiểm chứng chính xác kịch bản không có flush trung gian.

### 19.3. Thay đổi trên detached object không được tự lưu

~~~java
@Test
void entityIsNotTrackedAfterClear() {
    Customer customer = new Customer("C003", "An");

    em.persist(customer);
    em.flush();
    Long id = customer.getId();

    em.clear();

    customer.rename("Sửa trên detached");
    em.flush(); // Không có UPDATE do object này đã detached.

    Customer reloaded = em.find(Customer.class, id);
    assertEquals("An", reloaded.getName());
}
~~~

Trong cùng test, **em.contains(customer)** sẽ false sau clear. Nếu bạn muốn lưu thay đổi, hãy cập nhật một managed instance mới:

~~~java
Customer managedAgain = em.find(Customer.class, id);
managedAgain.rename("Sửa trên managed");
em.flush();
~~~

### 19.4. Chunk import phải xử lý phần dư

~~~java
@Test
void import205CustomersDoesNotMissLastChunk() {
    List<CustomerInput> inputs = new ArrayList<>();

    for (int i = 1; i <= 205; i++) {
        inputs.add(new CustomerInput("C-" + i, "Name-" + i));
    }

    int count = importer.importAll(inputs);

    assertEquals(205, count);

    // Dùng EntityManager mới để query dữ liệu sau commit của importer.
    EntityManager verifyEm = emf.createEntityManager();
    try {
        Long saved = verifyEm.createQuery(
            "select count(c) from Customer c", Long.class
        ).getSingleResult();

        assertEquals(205L, saved);
    } finally {
        verifyEm.close();
    }
}
~~~

Giả định test database sạch hoặc câu COUNT có điều kiện riêng cho batch test, tránh số lượng Customer từ test khác ảnh hưởng. Importer sử dụng transaction riêng; tránh chạy importer resource-local bên trong một test transaction Spring/JTA rồi cho rằng cùng transaction.

### 19.5. Flush rồi rollback vẫn không commit

Quy trình test bằng resource-local transaction:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();
Long id;

try {
    tx.begin();

    Customer customer = new Customer("C-ROLLBACK", "Temporary");
    em.persist(customer);
    em.flush();

    id = customer.getId();
    tx.rollback();
} finally {
    if (tx.isActive()) {
        tx.rollback();
    }
    em.close();
}

// Dùng EntityManager khác sau rollback để tìm theo id:
EntityManager verifyEm = emf.createEntityManager();
try {
    assertNull(verifyEm.find(Customer.class, id));
} finally {
    verifyEm.close();
}
~~~

Ví dụ nhằm chứng minh **flush không đồng nghĩa commit**. Với ID sequence, một ID có thể đã được cấp và sequence tăng dù transaction rollback; việc sequence có khoảng trống **không chứng minh INSERT được commit**.

### 19.6. Một số test hữu ích khác

| Tình huống | Điều cần xác minh |
|---|---|
| Flush/clear mỗi 50 entity | Context chỉ giữ entities của chunk đang xử lý |
| Entity bên ngoài batch nằm cùng context | Clear cũng detach entity ấy |
| Parent reference qua clear | Service lấy managed reference mới |
| Child FK | Owning side và constraint DB ghi đúng |
| Cascade/Orphan | Không xóa dữ liệu ngoài ý muốn khi batch xử lý |
| JDBC batch với sequence | Quan sát statement/batch statistics đúng provider |
| IDENTITY | Đo số lần INSERT/round trips thực tế |
| Query AUTO giữa loop | Hiểu lúc nào provider flush sớm |
| Bulk update | Managed state sau clear được nạp lại chính xác |
| Optimistic locking | Chunks xử lý conflict và rollback đúng |
| Chunk transaction retry | Không tạo duplicate hoặc báo committed sai |
| OFFSET khi filter thay đổi | Không bỏ sót records |
| Keyset pagination | Xử lý các IDs theo thứ tự ổn định |
| Transaction lỗi ở chunk cuối | Trong một transaction, các chunks trước cũng rollback |

## 20. Bài tập thực hành

### Bài 1: Chọn thứ tự đúng

Cho:

~~~java
for (int i = 0; i < 1000; i++) {
    em.persist(new Customer("C-" + i, "Name-" + i));

    if ((i + 1) % 100 == 0) {
        em.clear();
        em.flush();
    }
}
~~~

Hãy giải thích lỗi. Viết lại theo thứ tự đúng và bổ sung xử lý phần dư nếu số lượng không chia hết cho 100.

**Định hướng:** flush phải diễn ra trước clear để các pending changes được đồng bộ trước khi entity bị detach.

### Bài 2: Clear làm thay đổi object nào?

Một EntityManager đã load A, B, C. Vòng lặp chỉ sửa A và gọi em.flush(); em.clear().

Hỏi:
- A, B, C còn managed không?
- Nếu code sửa B sau clear, database có tự nhận UPDATE không?
- Phải làm gì để sửa B tiếp?
- flush có chỉ ghi riêng A không nếu trước đó C đã dirty?

### Bài 3: 250 entity với interval 100

Mô tả các lần flush/clear được thực thi. Nếu transaction rollback ở record 250, DB giữ bao nhiêu records được commit từ job này khi tất cả nằm trong **một transaction**?

**Gợi ý:** rollback toàn transaction, không có “200 records đã commit” chỉ vì hai lần flush trước thành công.

### Bài 4: Chọn transaction boundary

Một job nhập 1.000.000 log rows được phép lưu dần theo từng chunk. Một job khác chuyển tiền giữa tài khoản cần atomicity toàn bộ.

Trong hai trường hợp, việc chia thành transaction theo chunk có phù hợp không? Vì sao flush/clear không tự chia transaction? Những thông tin nào cần lưu để retry job import an toàn?

### Bài 5: Phân biệt JDBC batching và flush interval

Cấu hình Hibernate jdbc.batch_size=50, flush/clear interval=200, sử dụng IDENTITY cho Customer.

Hãy giải thích vì sao không chắc có đúng bốn JDBC batches cho mỗi chunk, và IDENTITY có thể ảnh hưởng insert batching ra sao. Đề xuất cách quan sát JDBC batch statistics thay vì suy luận chỉ từ SQL log.

### Bài 6: Parent reference detached

Một Department managed được nạp trước vòng lặp nhập 500 Employee. Mỗi 100 rows, code flush/clear.

Tại sao Department reference không còn managed ở chunk 2? Viết lại code dùng em.getReference hoặc em.find ở context mới. Cần kiểm tra tồn tại và quyền với Department ở bước nào?

### Bài 7: Xử lý các entities đã load sẵn

Code tải List<Customer> gồm 5.000 managed instances, rồi rename từng item, flush/clear mỗi 100. Tại sao sau clear lần đầu, những phần tử còn lại có thể không được dirty checking?

Hãy đề xuất cách duyệt scalar IDs và find entity trong từng chunk.

### Bài 8: Offset pagination bị sai

Query các Order có status=PENDING với OFFSET 0, 100, 200 và mỗi trang chuyển trạng thái thành DONE. Hãy giải thích trường hợp bỏ sót row khi result set thay đổi, và đề xuất keyset pagination theo ID ổn định.

### Bài 9: Bulk JPQL update

Viết JPQL cập nhật tất cả Customer có name rỗng thành "Chưa đặt tên". Trước đó service đã sửa một managed Customer; sau bulk vẫn muốn đọc lại dữ liệu mới.

Hãy xác định vị trí cần flush, executeUpdate, clear và find. Vì sao bulk update không chạy entity callbacks như update managed thông thường?

### Bài 10: Xác định hiệu quả bộ nhớ

Một batch persist 100.000 Customer rồi clear mỗi 100, nhưng vẫn thêm từng Customer vào List<Customer> allCustomers.

Vì sao heap có thể vẫn tăng? Những loại reference nào khác ngoài persistence context có thể giữ memory? Cách đọc input bằng stream/iterator có thể giúp gì?

### Bài 11: Kiểm tra flush không commit

Trong resource-local transaction: persist 20 Customers, em.flush(), sau đó tx.rollback(). Cần query từ EntityManager khác sau rollback để kỳ vọng điều gì? Vì sao sequence có thể vẫn tăng dù không có row mới?

### Bài 12: Sau clear có thể refresh không?

Code:

~~~java
em.persist(customer);
em.flush();
em.clear();
em.refresh(customer);
~~~

Hãy xác định lỗi. Nếu muốn đọc giá trị DB trigger vừa tạo, đặt refresh ở vị trí nào? Nếu đã clear, làm sao nạp lại managed instance?

### Bài 13: Lỗi optimistic locking sau clear

Một Customer được update, flush, clear, sau đó source detached bị sửa và merge sau khi transaction khác đã cập nhật cùng row.

Vai trò của @Version là gì? Nếu merge/flush báo conflict, có được tiếp tục ghi các record khác trong transaction đó không? Cần xử lý retry với transaction mới thế nào?

### Bài 14: Thiết kế Spring batch service

Viết service @Transactional với EntityManager được inject, duyệt danh sách IDs, find Customer, gọi business method, flush/clear mỗi 100. Giải thích:
- Vì sao không nhất thiết gọi repository.save cho từng managed entity?
- Vì sao @Transactional self-invocation có thể không tạo transaction?
- Khi nào cần tách các chunks thành giao dịch riêng để có checkpoint?

### Bài 15: Lựa chọn ORM hay bulk SQL

Một job cần set status='EXPIRED' cho 3.000.000 token rows, không có lifecycle callbacks và chỉ cần một SQL condition. Một job khác cập nhật từng Invoice với business validation, audit và optimistic locking.

Hãy chọn cách xử lý cho từng job và giải thích vì sao flush/clear không phải lựa chọn duy nhất cho mọi batch task.

### Bài 16: Phân tích một lỗi thực tế

Hệ thống ghi log:

~~~text
Chunk 1: flushed 100
Chunk 2: flushed 100
Chunk 3: flushed 100
Commit: failed due to unique constraint
HTTP response: 300 rows imported successfully
~~~

Chỉ ra vì sao phản hồi này có thể sai nếu cả ba chunks nằm trong một transaction. Đề xuất cách chỉ báo thành công sau commit và cách thiết kế partial commits nếu nghiệp vụ thật sự muốn lưu 100 rows ở từng chunk.

## 21. Checklist áp dụng flush/clear trong dự án

Trước khi dùng flush và clear trong một vòng lặp lớn, xác định:

1. **Đơn vị công việc**: một entity, một aggregate hay một chunk DTO?
2. **Kích thước tập dữ liệu**: có thể load tất cả không, hay phải paging/stream?
3. **Phạm vi persistence context**: có entity khác ngoài batch đang managed trong cùng context không?
4. **Thứ tự**: luôn flush trước clear nếu muốn giữ pending changes.
5. **Xử lý phần dư**: có flush cho chunk cuối ít hơn interval không?
6. **Transaction**: một transaction cho toàn job hay một transaction mỗi chunk?
7. **Tính atomicity**: có chấp nhận các chunks trước đã commit nếu chunk sau thất bại?
8. **Đường đọc**: có đang giữ List managed entities qua clear không?
9. **Tham chiếu parent**: có reference bị detached giữa các chunks không?
10. **Owning side**: FK và collection được cập nhật đúng qua helper chưa?
11. **Cascade/orphanRemoval**: có rủi ro lưu/xóa child ngoài ý muốn không?
12. **ID generation**: IDENTITY/SEQUENCE ảnh hưởng insert timing và batching thế nào?
13. **JDBC batching**: đã cấu hình và đo trên provider/driver thực tế chưa?
14. **Memory**: còn external references/LOB/DTO lists giữ object sau clear không?
15. **Flush mode/query**: AUTO có kích hoạt flush sớm khi query trong loop không?
16. **Bulk DML**: có làm managed objects stale không?
17. **Version/concurrency**: cập nhật đồng thời được phát hiện và xử lý thế nào?
18. **DB constraints**: UNIQUE, NOT NULL, FK và CHECK có thực sự ở database không?
19. **Rollback/retry**: sau exception có rollback transaction và dùng context mới không?
20. **Thông báo kết quả**: chỉ báo số committed sau commit thành công, không nhầm flushed với committed.
21. **Kiểm thử**: có test flush/clear, detached state, partial chunks, rollback và FK không?
22. **Hiệu năng**: đã đo heap, JDBC round trips, locks và throughput chưa?

Ghi nhớ ngắn:

~~~text
persist / mutate managed entities
              |
              v
       flush() → đồng bộ SQL trong transaction
              |
              v
       clear() → detach toàn bộ managed entities
              |
              v
       chunk tiếp theo: nạp managed instances mới
              |
              v
       commit() → hoàn tất transaction nếu thành công

flush != commit
clear != delete
clear != rollback
flush/clear interval != JDBC batch size
clear() tác động toàn persistence context, không chỉ chunk hiện tại
~~~

**Kết luận:** phối hợp **flush trước clear** là một kỹ thuật quan trọng để kiểm soát kích thước persistence context khi xử lý nhiều entity trong JPA. Flush đồng bộ trạng thái pending với database, còn clear detach các managed instances để tránh giữ cả graph lớn trong bộ nhớ. Nhưng kỹ thuật này chỉ đúng khi hiểu **clear tác động toàn context**, những object đã clear trở thành detached, và các quan hệ/foreign keys phải được nạp hoặc tham chiếu lại trong chunk mới. Kết hợp với transaction boundary, JDBC batching, pagination, optimistic locking, constraints và kiểm thử phù hợp sẽ giúp xử lý khối lượng lớn **đúng dữ liệu, kiểm soát bộ nhớ và vận hành ổn định**, thay vì chỉ nhanh hơn trong một vòng lặp đơn giản.



