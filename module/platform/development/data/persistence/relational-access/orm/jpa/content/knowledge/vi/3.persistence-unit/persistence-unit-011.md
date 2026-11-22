# Quản lý vòng đời và giới hạn chia sẻ EntityManager giữa các luồng

Trong kiến trúc **Jakarta Persistence (JPA)**, `EntityManager` là điểm truy cập chính để làm việc với các thực thể được ánh xạ vào cơ sở dữ liệu quan hệ. Bên trong nó là một **persistence context**, nơi JPA theo dõi các đối tượng đang được quản lý, danh tính của chúng và những thay đổi cần đồng bộ vào database. Vì chứa trạng thái có thể thay đổi, `EntityManager` phải được tạo, sử dụng, đóng và phối hợp với giao dịch đúng cách.

Quy tắc quan trọng nhất:

> **`EntityManagerFactory` được phép chia sẻ giữa nhiều luồng, nhưng một `EntityManager` thực tế không an toàn để nhiều luồng cùng sử dụng.** Với cơ chế ứng dụng tự quản lý, hãy tạo một manager riêng cho mỗi đơn vị công việc rồi đóng nó. Với cơ chế do môi trường quản lý, hãy sử dụng tham chiếu do container/framework cấp theo đúng ranh giới transaction.

Bài học này giải thích quy tắc trên trong bối cảnh **Persistence Unit**, cách quản lý vòng đời trong Java SE, Jakarta EE và Spring, cách xử lý công việc bất đồng bộ, cùng sự khác biệt giữa lỗi chia sẻ `EntityManager` và xung đột khi nhiều giao dịch truy cập một hàng dữ liệu.

## 1. Mối quan hệ giữa Persistence Unit, Factory và EntityManager

Một **persistence unit** xác định tập thực thể và cấu hình truy cập dữ liệu của một ứng dụng: tên unit, provider JPA, nguồn dữ liệu, kiểu transaction và các thuộc tính cần thiết. Tên unit được dùng để lấy `EntityManagerFactory`, là nhà máy cung cấp `EntityManager` cho các đơn vị công việc.

```text
Persistence Unit "shopPU"
      |
      v
EntityManagerFactory ----------------> được tái sử dụng giữa nhiều request
      |
      +-- EntityManager A
      |      |
      |      +-- Persistence context A
      |             +-- Customer#10
      |             +-- Order#101
      |
      +-- EntityManager B
             |
             +-- Persistence context B
                    +-- Customer#10
                    +-- Order#102
                       |
                       v
                Provider / JDBC
                       |
                       v
               Database quan hệ
```

`Customer#10` trong context A và `Customer#10` trong context B thường là hai object Java khác nhau biểu diễn cùng hàng có khóa chính 10. Mỗi context theo dõi trạng thái của các đối tượng đó độc lập. Chúng không tự đồng bộ thay đổi trong bộ nhớ cho nhau.

| Thành phần | Chức năng | Chia sẻ giữa các luồng? |
| --- | --- | --- |
| `EntityManagerFactory` | Tạo các manager với cấu hình của persistence unit; thường tồn tại lâu hơn request. | **Có**: API factory được thiết kế để sử dụng đồng thời. |
| `EntityManager` | `find`, `persist`, `merge`, `remove`, truy vấn và quản lý persistence context. | **Không**: không chia sẻ một instance thực tế cho nhiều luồng. |
| Persistence context | Quản lý identity map, entity state và thay đổi đang chờ đồng bộ. | Không phải vùng trạng thái dùng chung có đồng bộ cho mọi request. |
| Transaction | Xác định ranh giới commit/rollback và tính nhất quán của thao tác database. | Một transaction không tự động chuyển sang luồng khác. |
| Entity | Đối tượng Java thể hiện dữ liệu nghiệp vụ. | Không nên chia sẻ entity đang managed cùng proxy/lazy collection cho thao tác persistence đồng thời. |

**Persistence context khác JDBC Connection**: context quản lý trạng thái đối tượng; kết nối database là tài nguyên để thực hiện SQL. Thời điểm giữ/lấy/trả kết nối tùy provider, cấu hình và transaction. Một `EntityManager` cũng không tương đương một transaction: cả hai có thể có vòng đời khác nhau.

## 2. Vòng đời của application-managed EntityManager

Khi **ứng dụng tự quản lý** (*application-managed*), mã gọi `EntityManagerFactory.createEntityManager()` và phải đóng instance đó. Đây là mô hình thường gặp trong ứng dụng Java SE hoặc tác vụ độc lập không được môi trường inject manager.

```text
Khởi động chương trình
      |
      v
Tạo EntityManagerFactory
      |
      +---- createEntityManager() ----> EntityManager OPEN
      |                                  |
      |                                  +-- bắt đầu transaction
      |                                  +-- find / persist / cập nhật
      |                                  +-- flush khi thích hợp
      |                                  +-- commit hoặc rollback
      |                                  +-- close() trong finally
      |                                  v
      |                              EntityManager CLOSED
      |
      +---- createEntityManager() ----> đơn vị công việc khác
      |
Dừng chương trình
      |
Đóng EntityManagerFactory
```

### 2.1. Tạo factory một lần và tái sử dụng

Ứng dụng Java SE có thể khởi tạo factory từ `META-INF/persistence.xml`:

```java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

EntityManagerFactory factory =
        Persistence.createEntityManagerFactory("shopPU");

try {
    // Các dịch vụ trong ứng dụng sử dụng factory.
} finally {
    factory.close();
}
```

Factory thường phải nạp metadata mapping, cấu hình provider và tài nguyên cần thiết, nên việc tạo factory cho mỗi truy vấn gây chi phí không cần thiết. Thông thường, **mỗi persistence unit có một factory sống lâu trong phạm vi ứng dụng/thành phần**; các request gọi chung factory để tạo manager riêng.

Không được đóng factory khi vẫn còn các tác vụ cần sử dụng nó. Quá trình shutdown cần dừng nhận việc mới, hoàn tất/cancel việc đang chạy theo chính sách ứng dụng, rồi mới đóng factory.

### 2.2. Mỗi đơn vị công việc tạo và đóng EntityManager riêng

Ví dụ một service chỉ đọc tên khách hàng. Entity `Customer` được giả định có phương thức `getName()` và khóa chính `Long`:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;

public final class CustomerReader {
    private final EntityManagerFactory factory;

    public CustomerReader(EntityManagerFactory factory) {
        this.factory = factory;
    }

    public String findName(long id) {
        EntityManager em = factory.createEntityManager();
        try {
            Customer customer = em.find(Customer.class, id);
            return customer == null ? null : customer.getName();
        } finally {
            em.close();
        }
    }
}
```

Khi `findName()` kết thúc, manager được đóng ngay cả nếu truy vấn ném ngoại lệ. Service trả về `String`, không bắt tầng gọi phải sử dụng một managed entity hoặc lazy association sau khi context đã đóng.

Đối với nghiệp vụ yêu cầu ảnh chụp dữ liệu nhất quán giữa nhiều lần đọc, cần transaction phù hợp; một lời gọi đọc đơn giản ngoài transaction không có nghĩa mọi yêu cầu consistency đều được đáp ứng.

### 2.3. Ghi dữ liệu với RESOURCE_LOCAL transaction

Với persistence unit dùng `RESOURCE_LOCAL`, ứng dụng điều khiển giao dịch bằng `EntityTransaction`:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public final class CustomerWriter {
    private final EntityManagerFactory factory;

    public CustomerWriter(EntityManagerFactory factory) {
        this.factory = factory;
    }

    public void create(String name) {
        EntityManager em = factory.createEntityManager();
        try {
            EntityTransaction tx = em.getTransaction();
            try {
                tx.begin();
                em.persist(new Customer(name));
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
    }
}
```

Ví dụ này giả định `Customer(String)` tạo entity mới hợp lệ. Với transaction JTA, ứng dụng phải dùng cơ chế điều phối JTA thay cho `getTransaction().begin()`.

Phân biệt các thao tác trong vòng đời:

| Thao tác | Ý nghĩa | Có đóng EntityManager không? |
| --- | --- | --- |
| `persist(entity)` | Đưa entity mới vào trạng thái managed và lên lịch lưu theo quy tắc JPA. | Không |
| `find(type, id)` | Lấy thực thể theo khóa chính từ context hoặc database. | Không |
| `flush()` | Đồng bộ thay đổi đang chờ bằng SQL; transaction chưa nhất thiết commit. | Không |
| `commit()` | Cam kết transaction khi thành công. | **Không**, với application-managed manager. |
| `rollback()` | Hoàn tác transaction database; trạng thái object phải được xử lý cẩn thận. | Không |
| `clear()` | Tách toàn bộ entity khỏi context. | Không |
| `detach(entity)` | Tách một entity khỏi context. | Không |
| `close()` | Kết thúc context của application-managed manager và giải phóng tài nguyên liên quan. | **Có** |

Lệnh `INSERT` không nhất thiết chạy ngay khi gọi `persist()`. Thời điểm SQL được thực thi có thể phụ thuộc flush, commit, cách cấp khóa như `IDENTITY` và provider. Sau rollback hoặc lỗi transaction nghiêm trọng, nên kết thúc đơn vị công việc và đóng manager thay vì tái sử dụng một context có trạng thái khó kiểm soát.

### 2.4. EntityManager có thể sống lâu hơn một transaction

```text
EntityManager:       |----------------------------------| close
Transaction 1:         | begin ---- commit |
Transaction 2:                             | begin --- commit |
Persistence context:  | tiếp tục quản lý entity nếu chưa detach/clear/close |
```

Trong application-managed model, commit không mặc nhiên detach mọi entity. Vì thế một manager được giữ quá lâu có thể giữ nhiều đối tượng, tiêu thụ bộ nhớ và trả lại trạng thái đã tải từ trước. Với những công việc độc lập, quy ước **một manager cho một đơn vị công việc hoặc transaction** giúp việc cleanup và kiểm soát dữ liệu rõ ràng hơn.

## 3. Vì sao không được chia sẻ EntityManager giữa các luồng?

`EntityManager` và persistence context có trạng thái nội bộ thay đổi khi tải dữ liệu, tạo proxy, kiểm tra dirty state hoặc flush SQL. Đặc tả JPA **không bảo đảm EntityManager thread-safe**. Lời gọi có vẻ chỉ đọc như `find()` vẫn có thể thay đổi trạng thái context hoặc khởi tạo dữ liệu.

Ví dụ thiết kế nguy hiểm:

```java
import jakarta.persistence.EntityManager;

public final class UnsafeCustomerService {
    private final EntityManager sharedEm;

    public UnsafeCustomerService(EntityManager sharedEm) {
        this.sharedEm = sharedEm;
    }

    public Customer find(long id) {
        return sharedEm.find(Customer.class, id);
    }
}
```

Nếu một `UnsafeCustomerService` singleton giữ `sharedEm` được tạo trước bằng `createEntityManager()`, các request trên nhiều luồng đều dùng chung một instance thực tế. Khi một request đóng hoặc thay đổi trạng thái manager, các request khác có thể gặp lỗi và dữ liệu quản lý có thể bị trộn. Đưa manager vào field `static` cũng mang cùng rủi ro.

Không nên dựa vào việc thêm `synchronized` cho từng hàm để hợp thức hóa cách thiết kế đó. Vòng đời transaction, lazy loading và entity state có thể tiếp tục vượt khỏi vùng khóa. Cách rõ ràng hơn là **mỗi công việc sở hữu manager riêng**.

### 3.1. Mẫu đúng: service dùng chung factory, mỗi lần gọi có manager riêng

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;

public final class CustomerService {
    private final EntityManagerFactory factory;

    public CustomerService(EntityManagerFactory factory) {
        this.factory = factory;
    }

    public String getName(long id) {
        EntityManager em = factory.createEntityManager();
        try {
            Customer customer = em.find(Customer.class, id);
            return customer == null ? null : customer.getName();
        } finally {
            em.close();
        }
    }
}
```

Một `CustomerService` không có shared mutable state khác có thể được nhiều luồng gọi vì nó chỉ giữ **factory** và mỗi lời gọi tạo **manager riêng**.

```text
Thread A                             Thread B
--------                             --------
service.getName(10)                  service.getName(10)
    |                                    |
factory.createEntityManager()       factory.createEntityManager()
    |                                    |
 emA + context A                      emB + context B
    |                                    |
 emA.close()                          emB.close()

             Shared EntityManagerFactory
                        |
                     Database
```

Hai context có thể cùng đọc hàng `customers.id = 10` nhưng không chia sẻ identity map hoặc dirty state trong bộ nhớ.

### 3.2. Thread pool và tác vụ bất đồng bộ

Khi xử lý song song, hãy truyền **ID hoặc DTO**, sau đó thực hiện truy cập JPA bên trong task với manager của riêng task:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

CustomerService service = new CustomerService(factory);
ExecutorService executor = Executors.newFixedThreadPool(4);

try {
    List<Future<String>> futures = new ArrayList<>();

    for (long id : List.of(10L, 11L, 12L, 13L)) {
        futures.add(executor.submit(() -> service.getName(id)));
    }

    for (Future<String> future : futures) {
        System.out.println(future.get());
    }
} finally {
    executor.shutdown();
}
```

Ví dụ giả định `factory` còn mở suốt khi tasks sử dụng nó và ứng dụng sở hữu factory chỉ đóng sau khi các task đã hoàn thành. `Future.get()` có thể ném ngoại lệ nên chương trình gọi cần xử lý. Mỗi tác vụ gọi `getName` sẽ tạo/đóng manager trong `finally`.

Không nên viết:

```java
EntityManager em = factory.createEntityManager();

// Sai: các task truy cập đồng thời cùng một manager thực tế.
executor.submit(() -> em.find(Customer.class, 10L));
executor.submit(() -> em.find(Customer.class, 11L));
```

Nếu đơn vị công việc cần transaction, hãy bắt đầu và kết thúc transaction **bên trong task**, hoặc dùng framework transaction manager theo scope của task. Transaction/context của luồng gửi task không tự động chuyển sang executor thread.

**Virtual threads cũng không phải ngoại lệ**: mỗi virtual thread cần scope persistence phù hợp. Việc có thể tạo nhiều luồng không đồng nghĩa JDBC connection pool và database có thể xử lý vô hạn transaction song song.

## 4. Vòng đời Entity khi manager kết thúc

Một entity Java tồn tại độc lập với việc nó có đang được JPA quản lý hay không. Các trạng thái thường gặp:

```text
new / transient
      |
      | persist()
      v
   managed -------------------> removed
      |                          ^
      | close/clear/detach        | remove()
      v                          |
   detached -- merge() --> managed
               (trả về object managed)
```

Sơ đồ là mô tả giản lược những chuyển đổi phổ biến. Ví dụ:

```java
Customer detached;

EntityManager first = factory.createEntityManager();
try {
    detached = first.find(Customer.class, 10L);
} finally {
    first.close();
}

// detached vẫn là object Java thông thường.
// Thuộc tính đã tải vẫn có thể được đọc:
String name = detached.getName();
```

Sau `first.close()`, thay đổi thuộc tính trên `detached` **không tự động được JPA lưu xuống database**. Muốn cập nhật, mã phải làm việc với một context mới trong transaction phù hợp. `merge(detached)` sao chép trạng thái của đối tượng detached sang một phiên bản managed và **trả về phiên bản managed**; đối tượng gốc không tự trở thành managed.

### 4.1. Rủi ro lazy loading

```java
EntityManager em = factory.createEntityManager();
PurchaseOrder order;

try {
    order = em.find(PurchaseOrder.class, 101L);
} finally {
    em.close();
}

// Nếu quan hệ chưa được khởi tạo, thao tác có thể thất bại:
String customerName = order.getCustomer().getName();
```

Nếu `customer` được cấu hình tải trì hoãn và chưa tải, việc truy cập sau khi context đóng có thể thất bại; Hibernate thường biểu hiện bằng `LazyInitializationException`. Nên tải dữ liệu cần thiết trong đơn vị công việc bằng join fetch, entity graph hoặc projection rồi trả về **DTO**:

```java
public record OrderSummary(Long id, String customerName) {}
```

DTO được tạo từ giá trị đã lấy có thể truyền giữa các tầng hoặc task mà không đòi hỏi context đang mở. Tránh kéo dài scope của manager đến tận tầng giao diện chỉ để cho phép mọi truy cập lazy hoạt động.

## 5. Container-managed EntityManager trong Jakarta EE

Trong môi trường **Jakarta EE** có hỗ trợ JPA, container có thể cung cấp `EntityManager` cho bean qua `@PersistenceContext`:

```java
import jakarta.ejb.Stateless;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

@Stateless
public class CustomerApplicationService {
    @PersistenceContext(unitName = "shopPU")
    private EntityManager em;

    public String getName(long id) {
        Customer customer = em.find(Customer.class, id);
        return customer == null ? null : customer.getName();
    }
}
```

Với EJB stateless, giao dịch do container quản lý thường có thuộc tính mặc định `REQUIRED` khi gọi qua container. Container gắn persistence context với transaction JTA tương ứng và quản lý vòng đời của nó. **Không gọi `em.close()`** đối với manager do container inject; code ứng dụng không sở hữu vòng đời của tham chiếu này.

Container-managed `EntityManager` thường là một tham chiếu do container điều phối theo context hiện hành. Sự an toàn của việc nhiều request gọi bean phải dựa trên **hợp đồng container**, không phải suy luận rằng instance `EntityManager` do `createEntityManager()` đã trở thành thread-safe.

### 5.1. Transaction-scoped context

Đây là phạm vi mặc định:

```java
@PersistenceContext(
    unitName = "shopPU",
    type = jakarta.persistence.PersistenceContextType.TRANSACTION
)
private EntityManager em;
```

Context thường liên kết với transaction JTA. Sau khi transaction kết thúc, những entity do context này quản lý trở thành detached nếu không thuộc context khác.

```text
Transaction A                    Transaction B
     |                                |
Context A                        Context B
     |                                |
Customer#10                      Customer#10
     |                                |
   commit                           commit
     |                                |
Context A kết thúc               Context B kết thúc
```

Dù mỗi transaction có context riêng, hai transaction vẫn có thể cùng ghi vào một hàng của database. Vấn đề đó cần xử lý bằng concurrency control ở tầng persistence/database.

### 5.2. Extended context

Trong Jakarta EE, một số thành phần có vòng đời dài hơn, điển hình stateful session bean, có thể sử dụng `EXTENDED` persistence context:

```java
import jakarta.ejb.Stateful;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.PersistenceContextType;

@Stateful
public class CheckoutWorkflow {
    @PersistenceContext(
        unitName = "shopPU",
        type = PersistenceContextType.EXTENDED
    )
    private EntityManager em;

    // Context có thể tồn tại qua nhiều transaction của workflow.
}
```

Extended context có thể giữ entity managed qua nhiều lần gọi/giao dịch, hỗ trợ quy trình nhiều bước. Nó không kéo dài một transaction xuyên suốt mọi bước và không phải context toàn cục để nhiều user/luồng dùng chung. Scope càng dài càng cần chú ý bộ nhớ, thay đổi dữ liệu từ transaction khác và xung đột cập nhật.

## 6. Tại sao Spring singleton service có thể inject EntityManager?

Trong Spring/Spring Boot, service thường là singleton nhưng vẫn có thể khai báo:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerQueryService {
    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public String findName(long id) {
        Customer customer = em.find(Customer.class, id);
        return customer == null ? null : customer.getName();
    }
}
```

Cấu hình Spring thông thường inject một **proxy/tham chiếu EntityManager được framework quản lý**. Khi lời gọi diễn ra trong transaction, proxy định tuyến đến `EntityManager` thực tế phù hợp với transaction đó, thường gắn với ngữ cảnh hiện hành của luồng. Nhiều request có thể cùng giữ tham chiếu proxy trong singleton, trong khi các manager thực tế của từng transaction được quản lý riêng.

```text
Spring singleton CustomerQueryService
             |
      @PersistenceContext
       EntityManager proxy
             |
             +-- Transaction A --> actual EntityManager A
             |
             +-- Transaction B --> actual EntityManager B
```

Đây là lý do cần phân biệt:

| Thiết kế | Kết luận |
| --- | --- |
| Singleton giữ `EntityManager` thực tế do `factory.createEntityManager()` tạo | **Sai** khi dùng chung giữa nhiều luồng. |
| Singleton giữ proxy `@PersistenceContext` do Spring quản lý đúng cấu hình | **Phù hợp** với cơ chế framework. |
| Jakarta EE bean dùng `@PersistenceContext` do container cung cấp | **Phù hợp** theo hợp đồng quản lý của môi trường. |

Spring `@Transactional` xác định ranh giới giao dịch thông qua cơ chế framework, thường bằng proxy/interceptor. Trong ứng dụng một database, Spring có thể dùng `JpaTransactionManager` mà không dùng JTA. Cũng cần nhớ self-invocation, tức phương thức trong cùng object tự gọi một phương thức khác có `@Transactional`, có thể bỏ qua transaction interceptor trong mô hình proxy mặc định.

### 6.1. Công việc @Async không tự nhận transaction của request

Transaction và `EntityManager` của luồng gọi không tự được truyền vào luồng chạy `@Async`. Mẫu an toàn thường là truyền ID rồi bắt đầu transaction tại service xử lý async:

```java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerAsyncService {
    private final CustomerUpdater updater;

    public CustomerAsyncService(CustomerUpdater updater) {
        this.updater = updater;
    }

    @Async
    public void renameInBackground(Long id, String name) {
        updater.rename(id, name);
    }
}

@Service
class CustomerUpdater {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void rename(Long id, String name) {
        Customer customer = em.find(Customer.class, id);
        if (customer == null) {
            throw new IllegalArgumentException("Customer not found: " + id);
        }
        customer.rename(name);
    }
}
```

Ví dụ giả định entity có phương thức `rename`, Spring đã bật async và các thành phần được tạo như Spring beans. Việc gọi qua bean `CustomerUpdater` cho phép transaction interception của Spring áp dụng theo cơ chế mặc định. Ứng dụng thực tế phải xử lý ngoại lệ async và giới hạn concurrency phù hợp. Không gửi `EntityManager` hoặc entity đang managed của request gốc sang task khác.

## 7. Không chia sẻ EntityManager vẫn có thể gặp xung đột cập nhật

Một `EntityManager` riêng cho mỗi transaction bảo vệ trạng thái **trong bộ nhớ của JPA**. Nhưng nếu các transaction cùng đọc một hàng, chúng vẫn có thể gây **lost update**:

```text
Thời điểm    Transaction A                 Transaction B
---------    ---------------------------   ----------------------------
t1           Đọc Customer#10 = "Lan"
t2                                         Đọc Customer#10 = "Lan"
t3           Sửa thành "Lan A"
t4                                         Sửa thành "Lan B"
t5           Commit
t6                                         Commit, có thể ghi đè A
```

JPA hỗ trợ **optimistic locking** bằng `@Version`:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Customer {
    @Id
    private Long id;

    private String name;

    @Version
    private Long version;

    protected Customer() {}

    public void rename(String newName) {
        this.name = newName;
    }
}
```

Đây là lớp minh họa độc lập với các ví dụ trước, tập trung vào trường `version`; trong dự án thật cần cấu hình id và schema thích hợp. Khi một transaction cập nhật version, một transaction khác cố commit trên phiên bản cũ có thể gặp optimistic locking exception. Ứng dụng quyết định báo xung đột, tải lại dữ liệu hoặc retry **toàn bộ đơn vị công việc** khi nghiệp vụ cho phép.

Các chiến lược khác như `LockModeType.PESSIMISTIC_WRITE`, database constraints và mức cô lập transaction giải quyết những dạng cạnh tranh khác nhau. Không cơ chế nào biến một `EntityManager` dùng chung thành thread-safe.

## 8. Vòng đời quá dài: bộ nhớ và dữ liệu cũ

Persistence context thường đóng vai trò **first-level cache** theo phạm vi `EntityManager`. Nếu một tác vụ import nhiều đối tượng trong cùng manager, context có thể giữ quá nhiều managed entity và tăng chi phí theo dõi thay đổi.

Với batch import trong persistence unit `RESOURCE_LOCAL`, có thể flush/clear theo nhóm:

```java
EntityManager em = factory.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    for (int i = 0; i < customersToImport.size(); i++) {
        em.persist(customersToImport.get(i));

        if ((i + 1) % 100 == 0) {
            em.flush();
            em.clear();
        }
    }

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Ví dụ này chỉ minh họa giảm số entity đang managed, không mặc nhiên bật JDBC batching. Một số chiến lược khóa như `IDENTITY` có thể hạn chế khả năng batch insert. Sau `clear()`, các entity cũ trở thành detached, không còn được theo dõi tự động.

Context sống qua nhiều giao dịch cũng có thể giữ object mang dữ liệu đã tải từ trước. Gọi lại `find()` cùng id có thể trả về managed instance đang có thay vì tự động đọc toàn bộ cột mới nhất. Khi cần dữ liệu mới, phải xem xét transaction boundary, mức cô lập, `refresh()` hoặc `clear()`; không nên giữ manager qua nhiều request chỉ để giảm số lần khởi tạo.

## 9. Những lỗi thường gặp và cách khắc phục

| Tình huống | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Singleton giữ một `EntityManager` tự tạo. | Nhiều request dùng cùng stateful manager không thread-safe. | Giữ `EntityManagerFactory`; tạo manager theo công việc, hoặc dùng proxy do framework cấp. |
| Quên `close()` khi gặp exception. | Không có `finally` hoặc thiếu phân định sở hữu. | Bọc vòng đời manager bằng `try/finally`. |
| Tự đóng manager được `@PersistenceContext` inject. | Đóng tài nguyên do môi trường sở hữu. | Để container/Spring đóng theo scope. |
| Truy cập lazy association sau khi return entity ra khỏi service. | Context đã kết thúc, dữ liệu chưa tải. | Tải dữ liệu cần thiết trong giao dịch, trả DTO/projection. |
| `TransactionRequiredException` khi ghi dữ liệu. | Không có transaction phù hợp hoặc manager chưa tham gia transaction. | Thiết kế transaction boundary và kiểu quản lý giao dịch nhất quán. |
| `@Async` không thấy transaction của request. | Context không tự truyền sang thread mới. | Truyền ID/DTO, mở transaction và context của task. |
| Lost update dù mỗi request có manager riêng. | Hai transaction hợp lệ tranh chấp cùng một hàng. | Dùng `@Version`, locking hoặc mức cô lập phù hợp. |
| Bộ nhớ tăng khi import nhiều bản ghi. | Context giữ nhiều managed entity. | Chia batch, flush/clear khi cần hoặc dùng bulk operation. |
| `find()` trả lại giá trị cũ. | Identity map trong context hoặc tính chất transaction/isolation. | Điều chỉnh scope, `refresh()` và yêu cầu nhất quán dữ liệu. |

### Có nên dùng ThreadLocal để giữ EntityManager?

Có thể tự xây dựng holder `ThreadLocal<EntityManager>`, nhưng cách này khiến ứng dụng phải tự giải quyết cấp phát, transaction, rollback, đóng manager và `ThreadLocal.remove()` khi thread pool tái sử dụng luồng. Nếu thiếu cleanup, một request có thể ảnh hưởng request sau. Trong Spring, sử dụng `@Transactional` và `@PersistenceContext` thường giúp tránh việc phải tự quản lý ranh giới phức tạp đó.

### Repository có thể giữ EntityManager không?

Repository application-managed có thể giữ **factory** và tạo/đóng manager cho đơn vị công việc rõ ràng. Repository do Spring/container quản lý có thể inject một **proxy/managed reference** của manager. Không nên để repository singleton giữ một manager thực tế được tạo thủ công rồi chia sẻ cho nhiều request.

Khi nhiều repository cùng tham gia một nghiệp vụ, transaction boundary nên được xác định ở tầng service. Nếu mỗi repository tự mở một transaction riêng mà không chủ định, những thay đổi cần nguyên tử có thể bị chia tách.

### Thao tác chỉ đọc có cần quan tâm lifecycle không?

Có. `SELECT` vẫn có thể tạo managed entity, dùng first-level cache, khởi tạo proxy hoặc tiêu thụ kết nối. `EntityManager` application-managed phải được đóng sau khi đọc, và một manager thực tế vẫn không được dùng đồng thời chỉ vì code không gọi `persist()` hoặc `remove()`.

## 10. Thiết kế ranh giới EntityManager trong hệ thống

Khi chọn kiến trúc, cần trả lời bốn câu hỏi:

1. **Ai tạo và đóng factory?** Mã bootstrap hoặc framework quản lý `EntityManagerFactory` sống lâu theo persistence unit.
2. **Ai tạo và đóng manager?** Ứng dụng sở hữu instance `createEntityManager()`; container/framework sở hữu tham chiếu được inject và context tương ứng.
3. **Ai bắt đầu và kết thúc giao dịch?** `RESOURCE_LOCAL` dùng `EntityTransaction`; JTA hoặc Spring dùng transaction manager thích hợp.
4. **Dữ liệu nào rời khỏi context?** Nên đưa ID/DTO ra web, queue hoặc async task; mọi thao tác cần managed entity phải nằm trong scope persistence phù hợp.

```text
                Nhiều HTTP requests / tasks
                            |
                        Service layer
                    Transaction boundary
                            |
             +--------------+--------------+
             |                             |
       Request / Task A              Request / Task B
       EntityManager A               EntityManager B
       Context A                     Context B
             |                             |
             +--------------+--------------+
                            |
                  EntityManagerFactory
                            |
                    Persistence Unit
                            |
                         Database
```

Với Spring, service có thể nắm giữ một proxy dùng chung trong khi manager thực tế được điều phối theo transaction. Với Java SE application-managed, từng đơn vị công việc chủ động tạo và đóng manager. Ở cả hai cách, **không để hai luồng đồng thời thao tác trên cùng một EntityManager thực tế**.

## 11. Ghi nhớ trọng tâm

- **`EntityManagerFactory` được thiết kế để chia sẻ giữa các luồng** và thường sống cùng ứng dụng; **`EntityManager` thực tế không thread-safe**, phải có scope phù hợp.
- **Manager và transaction không đồng nhất**: `commit()` không tự đóng manager do ứng dụng tạo; `flush()` cũng không đồng nghĩa commit.
- **Application-managed** yêu cầu ứng dụng dùng `createEntityManager()` và `close()`; **container-managed** chuyển trách nhiệm cấp manager/context cho môi trường.
- **Proxy `@PersistenceContext` trong Spring hoặc managed reference trong Jakarta EE** khác với việc lưu một manager thực tế trong singleton.
- **Task bất đồng bộ không thừa hưởng transaction/context** một cách tự động; nên truyền ID/DTO và thực hiện persistence trong scope riêng.
- **Context độc lập không ngăn lost update** ở database; cần thiết kế transaction, `@Version` hoặc locking phù hợp.
- **Context kéo dài làm tăng rủi ro bộ nhớ và dữ liệu cũ**. Cần giới hạn vòng đời, quản lý lazy loading và dùng flush/clear đúng nhu cầu.

Khi xác định rõ ai tạo, ai đóng, ai commit và luồng nào sở hữu context, tầng JPA sẽ dễ bảo trì hơn, tránh chia sẻ tài nguyên sai cách và xử lý các request đồng thời một cách có kiểm soát.
