# Ranh giới context trong xử lý theo lô và nhiều giao dịch

## 1. Bài toán: xử lý 100.000 bản ghi không giống xử lý một entity

Trong ứng dụng Java sử dụng Jakarta Persistence (JPA) và Hibernate ORM, một thao tác CRUD đơn lẻ thường khá đơn giản:

~~~java
@Transactional
public void renameProduct(Long id, String newName) {
    Product product = entityManager.find(Product.class, id);
    product.rename(newName);
}
~~~

Trong transaction hợp lệ, `Product` được quản lý bởi **persistence context**; Hibernate theo dõi thay đổi và đồng bộ xuống database khi flush. Nhưng khi chuyển từ một bản ghi sang hàng trăm nghìn bản ghi, hai câu hỏi trở nên quan trọng hơn:

1. **Persistence context nên tồn tại trong bao lâu và chứa bao nhiêu entity?**
2. **Transaction nên bao phủ toàn bộ dữ liệu hay chỉ một phần nhỏ (chunk)?**

Giả sử cần import 100.000 sản phẩm từ tệp CSV. Cách viết trực giác:

~~~java
@Transactional
public void importAll(List<ProductInput> inputs) {
    for (ProductInput input : inputs) {
        entityManager.persist(new Product(
            input.sku(),
            input.name(),
            input.price()
        ));
    }
}
~~~

có thể gặp các vấn đề:

- Persistence context tích lũy rất nhiều managed entities, snapshots, collections và pending actions, làm tăng sử dụng bộ nhớ.
- Transaction kéo dài dẫn tới giữ khóa lâu hơn, tăng lượng log/undo dữ liệu, chiếm kết nối và khiến rollback tốn kém.
- Một bản ghi lỗi ở cuối có thể khiến toàn bộ 100.000 bản ghi phải rollback.
- Flush có thể đưa một lượng SQL rất lớn qua JDBC trong thời gian ngắn.
- Nếu import chạy nhiều thread hoặc nhiều node, tranh chấp và xử lý trùng dữ liệu trở nên phức tạp.
- Thao tác đọc cùng bảng đang ghi có thể gặp dữ liệu thay đổi, entity stale hoặc pagination bỏ sót bản ghi.

Để giải quyết, phải phân biệt rạch ròi **persistence context**, **transaction**, **flush**, **clear**, **commit** và **ranh giới công việc nghiệp vụ**.

Bài học trình bày các mô hình sử dụng trong Java SE và Spring, từ một transaction duy nhất có flush/clear định kỳ đến nhiều transaction nhỏ với context riêng, rồi mở rộng sang phân trang, bulk DML, retry, idempotency và xử lý đồng thời.

> **Phạm vi API:** Ví dụ sử dụng `jakarta.persistence.*`, Hibernate ORM hiện đại và, ở những đoạn có `@Transactional`/`TransactionTemplate`, Spring Framework. Một số cơ chế batching, streaming, `StatelessSession`, flush mode và các extension riêng phụ thuộc phiên bản Hibernate, dialect và JDBC driver. Phần SQL chỉ minh họa; luôn căn cứ schema thực tế khi triển khai.

## 2. Persistence context và transaction là hai khái niệm khác nhau

### 2.1. Persistence context quản lý đối tượng

**Persistence context** là tập các entity instances được JPA provider quản lý theo một định danh persistence. Hibernate `Session` là API native gắn với cơ chế này; `EntityManager` là API Jakarta Persistence.

Trong một context, nếu cùng entity type và ID được nạp nhiều lần, provider duy trì cùng một managed entity instance tương ứng:

~~~java
Product a = entityManager.find(Product.class, 42L);
Product b = entityManager.find(Product.class, 42L);

System.out.println(a == b); // true trong cùng persistence context
~~~

Persistence context hỗ trợ:

- Identity map: một managed instance cho mỗi entity identity trong context.
- Dirty checking: nhận biết persistent state thay đổi.
- Quản lý pending insert/update/delete và đồng bộ khi flush.
- Lazy loading theo điều kiện session/context còn hợp lệ.
- Cascade, lifecycle callbacks và các semantics JPA khác.

**First-level cache** chính là phần quản lý thực thể trong persistence context. Nó không phải second-level cache dùng chung giữa các session.

Một context chứa hàng chục nghìn managed entities có thể cần đáng kể bộ nhớ, nhất là khi entity có collections, snapshots hoặc graph liên quan. Kể cả sau khi SQL đã được gửi bằng `flush()`, những entity đó **không tự động được gỡ khỏi context**.

### 2.2. Transaction quản lý tính nguyên tử của thay đổi

**Transaction** là ranh giới những thao tác database cùng thành công hoặc cùng rollback theo chính sách nhất quán/isolation của database.

~~~text
Transaction A:
    INSERT product 1
    INSERT product 2
    INSERT product 3
    COMMIT   -> cả 3 được xác nhận

Transaction B:
    INSERT product 4
    INSERT product 5
    ROLLBACK -> thay đổi của B không được commit
~~~

Transaction xử lý commit, rollback, isolation và các loại khóa database; nó không tự định nghĩa bao nhiêu entity được giữ trong first-level cache.

Một `EntityManager` application-managed có thể được giữ mở qua nhiều transaction trong Java SE. Ngược lại, trong nhiều cấu hình Spring/Jakarta EE, persistence context có phạm vi theo transaction. Vì vậy, **không được suy luận rằng context và transaction luôn có cùng vòng đời**.

### 2.3. Sơ đồ hai ranh giới

~~~text
MÔ HÌNH 1: Một context + một transaction dài

EntityManager / Persistence Context
+-------------------------------------------------------+
| Transaction ----------------------------------------  |
|   record 1 ... record 100000                          |
|   flush/clear nhiều lần nếu có                        |
|   commit một lần                                      |
+-------------------------------------------------------+


MÔ HÌNH 2: Nhiều transaction, mỗi transaction một context

Chunk 1    [EntityManager A] [Transaction A] COMMIT
Chunk 2    [EntityManager B] [Transaction B] COMMIT
Chunk 3    [EntityManager C] [Transaction C] ROLLBACK
Chunk 4    [EntityManager D] [Transaction D] ... tùy chính sách
~~~

Trong mô hình 2, commit của chunk 1 và 2 **không bị rollback** khi chunk 3 thất bại. Đây là sự thay đổi ngữ nghĩa nghiệp vụ quan trọng, không chỉ là tối ưu hiệu năng.

### 2.4. Flush khác commit, clear khác rollback

| Thao tác | Tác động chính | Không đồng nghĩa |
|---|---|---|
| `persist(entity)` | Đưa entity mới vào managed state, yêu cầu lưu theo lifecycle | INSERT đã commit |
| `flush()` | Đồng bộ những SQL pending của context xuống database theo transaction | Commit |
| `clear()` | Gỡ mọi managed instances khỏi context; các thay đổi chưa flush có thể bị bỏ | Rollback |
| `detach(entity)` | Gỡ một instance khỏi context | Xóa row DB |
| `commit()` | Xác nhận transaction thành công | Tự giải phóng mọi entity khỏi một context còn mở |
| `rollback()` | Hủy các thay đổi của transaction chưa commit | Hoàn tác mọi lệnh setter trong Java |
| `close()` | Đóng EntityManager application-managed, giải phóng context | Commit transaction |
| `merge(detached)` | Sao chép trạng thái vào managed instance và trả về instance đó | Biến đối tượng đầu vào thành managed |

Dùng `flush(); clear();` định kỳ chỉ kiểm soát lượng entity giữ trong bộ nhớ và thời điểm gửi SQL; nó **không chia một transaction lớn thành nhiều transaction nhỏ**.

## 3. Ví dụ domain và dữ liệu đầu vào cho batch

Giả sử hệ thống cần nhập danh mục sản phẩm. Một entity tối giản:

~~~java
package example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "product_seq")
    @jakarta.persistence.SequenceGenerator(
        name = "product_seq",
        sequenceName = "product_id_seq",
        allocationSize = 50
    )
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 64)
    private String sku;

    @Column(name = "display_name", nullable = false, length = 160)
    private String displayName;

    @Column(name = "price", nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Version
    private long version;

    protected Product() {}

    public Product(String sku, String displayName, BigDecimal price) {
        this.sku = sku;
        this.displayName = displayName;
        this.price = price;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getDisplayName() { return displayName; }
    public BigDecimal getPrice() { return price; }

    public void changePrice(BigDecimal newPrice) {
        this.price = newPrice;
    }
}
~~~

Một bảng PostgreSQL minh họa:

~~~sql
CREATE SEQUENCE product_id_seq START WITH 1 INCREMENT BY 50;

CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    display_name VARCHAR(160) NOT NULL,
    price NUMERIC(14, 2) NOT NULL,
    version BIGINT NOT NULL
);
~~~

Tùy cấu hình Hibernate, sequence allocation và generator, DDL cụ thể có thể khác; ví dụ này chỉ thể hiện ý định. Khi schema được quản lý bằng Flyway/Liquibase, DDL/migration phải khớp mapping và generator thực tế.

Dữ liệu nhập được diễn đạt bằng DTO không phải entity:

~~~java
public record ProductInput(
    String sku,
    String name,
    BigDecimal price
) {}
~~~

Tách input DTO khỏi entity giúp parser/reader không vô tình tạo một số lượng lớn entity được quản lý. DTO vẫn dùng bộ nhớ nếu cả tệp được nạp vào `List`; với tệp rất lớn, nên đọc theo luồng hoặc page/chunk thay vì giữ toàn bộ tệp.

## 4. Chiến lược A: một transaction, flush và clear theo đợt

Một cách tăng hiệu quả so với loop persist đơn giản là giới hạn số entity managed bằng flush/clear sau mỗi số bản ghi nhất định:

~~~java
public void importAtomically(
        EntityManagerFactory emf,
        Iterable<ProductInput> inputs) {

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();
    int processed = 0;
    int contextBatchSize = 100;

    try {
        tx.begin();

        for (ProductInput input : inputs) {
            Product entity = new Product(
                input.sku(), input.name(), input.price()
            );
            em.persist(entity);

            processed++;
            if (processed % contextBatchSize == 0) {
                em.flush();
                em.clear();
            }
        }

        em.flush();  // Đồng bộ phần batch còn lại.
        tx.commit(); // Một commit cho toàn bộ import.
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
~~~

Các import ở ví dụ sử dụng `jakarta.persistence.EntityManager`, `EntityManagerFactory` và `EntityTransaction`.

### 4.1. Điều gì được cải thiện?

Sau mỗi nhóm 100 entity, `flush()` gửi những thao tác pending và `clear()` gỡ các managed instances, giúp persistence context không giữ toàn bộ 100.000 entities. Điều này giảm áp lực bộ nhớ trong các vòng lặp import đơn giản.

Tuy nhiên, một transaction vẫn bao phủ từ đầu đến cuối. Nếu bản ghi thứ 99.999 gây lỗi unique constraint và transaction rollback, **các INSERT đã flush trước đó cũng bị rollback**, miễn là chúng nằm trong cùng database transaction.

### 4.2. Điều gì chưa được cải thiện?

- Transaction vẫn có thể rất dài.
- Khóa và tài nguyên DB có thể được giữ lâu.
- Rollback toàn bộ vẫn tốn chi phí.
- Không có checkpoint commit để resume từng chunk.
- Kết quả chưa phải **partial success**.
- Các SQL INSERT có thể cần tối ưu batching riêng, không tự tăng throughput chỉ vì `flush` định kỳ.

Chọn cách này khi nghiệp vụ thực sự yêu cầu **atomicity toàn bộ import**, số lượng bản ghi và thời gian transaction còn chấp nhận được, và không cần checkpoint commit giữa các nhóm.

### 4.3. Vì sao phải flush trước clear?

~~~java
em.persist(product);
em.clear(); // Không phải một cách thay thế flush.
~~~

`clear` loại các entity khỏi context và có thể bỏ các thay đổi chưa đồng bộ, vì vậy không nên dựa vào việc `commit` sau đó vẫn lưu đầy đủ. Muốn giảm context nhưng giữ công việc của transaction, thực hiện `flush` đúng lúc **trước** `clear`, rồi tiếp tục các thao tác mới.

**Flush vẫn không commit.** Nếu sau flush có exception và rollback, dữ liệu đã được gửi tới DB nhưng chưa commit phải được rollback theo transaction.

### 4.4. Chi tiết về lifecycle callback và tham chiếu

Sau `em.clear()`, mọi entity trước đó trở thành **detached**. Nếu mã còn giữ reference rồi sửa:

~~~java
Product p = new Product("SKU-1", "A", new BigDecimal("10.00"));
em.persist(p);
em.flush();
em.clear();

p.changePrice(new BigDecimal("12.00"));
// p đã detached, thay đổi này không tự được ghi tiếp.
~~~

Nếu tiếp tục cần sửa p, phải lấy managed instance mới bằng `find`/query hoặc cân nhắc `merge`. Với `merge`, instance trả về là managed copy; object đầu vào không tự managed.

Nếu trong vòng lặp có quan hệ cha–con, không nên vô tình clear context khi mới persist parent rồi sau đó tiếp tục thao tác như parent vẫn managed. Cần chọn chunk boundary gắn với **một đơn vị aggregate có thể hoàn thành độc lập**, không cắt ngang một graph chưa đồng bộ.

## 5. JDBC batching không phải transaction batching

Thuật ngữ “batch” có thể chỉ ít nhất ba thứ:

1. **Context chunk size:** sau bao nhiêu entity thì `flush/clear`.
2. **JDBC batch size:** Hibernate/driver nhóm bao nhiêu lệnh SQL tương thích trong một đợt gửi.
3. **Transaction chunk size:** bao nhiêu record cùng một commit/rollback.

Chúng **không phải một tham số duy nhất**.

Ví dụ cấu hình Hibernate phổ biến:

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
~~~

Tác dụng cần hiểu:

- `hibernate.jdbc.batch_size` cho phép Hibernate batching JDBC khi câu lệnh và mapping thích hợp.
- `order_inserts` và `order_updates` có thể gom lệnh SQL cùng dạng để tăng cơ hội batch, nhưng cũng có chi phí sắp xếp và cần xem ngữ nghĩa ứng dụng.
- Cơ hội batch còn phụ thuộc driver, ID generator, dialect, sự phân bố entity types và SQL statement shape.
- Những strategy sinh ID như `GenerationType.IDENTITY` thường hạn chế batching INSERT trong Hibernate vì ID có thể cần được DB cấp ngay.

Ví dụ `@GeneratedValue(strategy = GenerationType.SEQUENCE)` kết hợp sequence allocation phù hợp thường tạo điều kiện tốt hơn cho batch insert trên database hỗ trợ sequence, nhưng không bảo đảm mọi insert luôn được gom đúng 50 câu.

### 5.1. Ba kích thước có thể khác nhau

~~~text
Tệp 10.000 dòng
  |
  +-- transaction chunk: 1.000 dòng / commit
        |
        +-- context flush/clear: 100 dòng
              |
              +-- JDBC batch: 50 statements
~~~

Trong một transaction 1.000 dòng, có thể có 10 lần flush/clear và nhiều JDBC batches bên trong. **Một transaction vẫn có một commit cho 1.000 dòng**.

Giá trị 50/100/1000 chỉ là số minh họa. Chọn kích thước dựa trên memory, kích thước entity graph, timeout, DB latency, mức khóa, constraint, throughput, error/retry model và nhu cầu nghiệp vụ. Không có một “batch size tốt nhất” áp dụng cho mọi hệ thống.

### 5.2. Vì sao tăng batch size vô hạn có thể phản tác dụng?

Batch lớn có thể:

- Giảm số round-trip nhưng tăng thời gian giữ tài nguyên.
- Làm lượng SQL pending và memory tăng.
- Tăng số record phải retry sau lỗi.
- Gây áp lực lên transaction log, index và constraint checking.
- Làm xử lý lỗi theo từng record khó hơn.

Hãy phân biệt đo hiệu quả **context size**, **JDBC batch size** và **transaction size** khi vận hành. Một cải tiến ở số round-trip có thể không bù được chi phí transaction dài và retry lớn.
## 6. Chiến lược B: mỗi chunk có transaction và persistence context riêng

Khi nghiệp vụ cho phép **một phần dữ liệu đã được commit dù phần sau thất bại**, ta có thể xử lý từng chunk bằng transaction độc lập. Context mới cho mỗi chunk giúp giới hạn số managed entity, giảm thời gian giữ database connection/lock và dễ xác định checkpoint/retry.

~~~text
File input / Work queue
         |
         v
    Chia thành chunk
         |
         +--> Chunk 1: context A, transaction A --> COMMIT
         +--> Chunk 2: context B, transaction B --> COMMIT
         +--> Chunk 3: context C, transaction C --> ROLLBACK
         +--> Chunk 4: chưa chạy hoặc chạy tiếp theo chính sách

Chunk 3 rollback KHÔNG hoàn tác kết quả đã commit của chunk 1, 2.
~~~

Đây là một thay đổi về **ngữ nghĩa nghiệp vụ**, không chỉ tối ưu hiệu năng. Nếu toàn bộ import phải all-or-nothing, không thể dùng các transaction độc lập rồi kỳ vọng rollback của transaction cuối cùng xóa kết quả các chunk trước.

### 6.1. Java SE: một EntityManager cho mỗi chunk

Đoạn code dùng `RESOURCE_LOCAL` nên mở transaction, commit/rollback và đóng EntityManager tường minh:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import java.util.List;

public final class ProductChunkWriter {
    private final EntityManagerFactory emf;

    public ProductChunkWriter(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public void writeChunk(List<ProductInput> rows) {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            for (ProductInput row : rows) {
                em.persist(new Product(
                    row.sku(),
                    row.name(),
                    row.price()
                ));
            }

            em.flush();  // SQL của chunk; có thể phát hiện lỗi trước commit.
            tx.commit(); // Chỉ commit chunk này.
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
~~~

Trong production, cần xử lý riêng trường hợp rollback/close cũng gặp lỗi, log lỗi và trạng thái job. Điểm chính của ví dụ: **mỗi chunk có persistence context mới và transaction mới**. Khi chunk lỗi do `PersistenceException`, không tiếp tục dùng context/transaction hỏng để thử ghi dòng sau.

### 6.2. Điều phối dữ liệu theo Iterator

~~~java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public final class ProductImportRunner {
    private final ProductChunkWriter writer;

    public ProductImportRunner(ProductChunkWriter writer) {
        this.writer = writer;
    }

    public void run(Iterator<ProductInput> source, int chunkSize) {
        if (chunkSize <= 0) {
            throw new IllegalArgumentException("chunkSize must be positive");
        }

        List<ProductInput> chunk = new ArrayList<>(chunkSize);

        while (source.hasNext()) {
            chunk.add(source.next());

            if (chunk.size() == chunkSize) {
                writer.writeChunk(List.copyOf(chunk));
                chunk.clear();
            }
        }

        if (!chunk.isEmpty()) {
            writer.writeChunk(List.copyOf(chunk));
        }
    }
}
~~~

Với `Iterator` được cấp bởi reader đọc tệp, có thể import mà không giữ toàn bộ 100.000 dòng trong RAM; vẫn phải đóng resource reader ở nơi sở hữu nó. Nếu chunk 3 thất bại, vòng lặp trên dừng nhưng các chunk đã commit trước đó không bị rollback. Có thể chọn retry, skip hoặc fail-fast; phải định nghĩa rõ trong thiết kế job.

### 6.3. Transaction chunk size khác context flush size

Giả sử 10.000 dòng, mỗi chunk có 500 dòng:

~~~text
Chunk 1: records 1..500      -> COMMIT
Chunk 2: records 501..1000   -> COMMIT
...
Chunk 20: records 9501..10000 -> COMMIT
~~~

Mỗi transaction quản lý tối đa 500 entity mới theo ví dụ đơn giản. Nếu chunk 7 lỗi, 6 chunk trước vẫn đã commit. Trong mỗi chunk 500 dòng, có thể tùy chọn `flush(); clear();` sau 100 dòng, nhưng điều đó **không chia chunk thành 5 transaction**.

Nếu chunk đã tương đối nhỏ và EntityManager được đóng ngay sau commit, thường không cần `clear()` trong mỗi chunk. `flush()` tường minh trước commit hữu ích để phát hiện lỗi trong method, nhưng không bắt buộc trong mọi giao dịch do commit thường đồng bộ pending changes.

### 6.4. Vì sao không nên giữ một EntityManager quá lâu qua nhiều transaction?

Application-managed EntityManager có thể tồn tại qua nhiều transaction, nhưng trong batch dài việc tái sử dụng một context làm tăng nguy cơ:

- Managed entities ở chunk cũ chưa được gỡ, tích lũy bộ nhớ.
- First-level cache có dữ liệu cũ sau khi hệ thống khác cập nhật DB.
- Một entity bị sửa ngoài dự định ở transaction trước được flush trong transaction sau.
- Khó xác định một object thuộc context/transaction nào khi debug.
- Rollback và ngoại lệ khiến context không còn phù hợp để tiếp tục công việc.

Vì vậy, **EntityManager riêng cho mỗi chunk transaction** thường là lựa chọn đơn giản và dễ quan sát nhất.

## 7. Spring: transaction-scoped context, REQUIRES_NEW và self-invocation

Trong Spring dùng Hibernate/JPA, một bean có thể được quản lý transaction bằng `@Transactional`.

### 7.1. Tách writer thành bean riêng

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
public class ProductChunkService {
    @PersistenceContext
    private EntityManager em;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeChunk(List<ProductInput> rows) {
        for (ProductInput row : rows) {
            em.persist(new Product(
                row.sku(),
                row.name(),
                row.price()
            ));
        }

        em.flush();
        // Commit thực tế do Spring transaction manager quản lý.
    }
}
~~~

Orchestrator gọi qua bean proxy:

~~~java
import org.springframework.stereotype.Service;
import java.util.List;

@Service
public class ProductImportService {
    private final ProductChunkService writer;

    public ProductImportService(ProductChunkService writer) {
        this.writer = writer;
    }

    public void importChunks(List<List<ProductInput>> chunks) {
        // Không @Transactional ở toàn bộ method điều phối.
        for (List<ProductInput> chunk : chunks) {
            writer.writeChunk(chunk);
        }
    }
}
~~~

`List<List<ProductInput>>` chỉ minh họa điều phối; khi dữ liệu lớn, nên đọc theo chunk từ nguồn. `@PersistenceContext` thường cung cấp EntityManager proxy gắn với transaction scope. `REQUIRES_NEW` tạo transaction mới khi đi qua interceptor/proxy Spring phù hợp. `em.flush()` không tự commit.

Nếu chunk thất bại và ném RuntimeException, Spring thông thường rollback transaction của method theo quy tắc mặc định; checked exception cần xem cấu hình `rollbackFor`. Không nên nuốt exception rồi báo thành công.

### 7.2. Bẫy self-invocation

~~~java
@Service
public class BrokenImporter {
    public void importAll(List<ProductInput> rows) {
        this.writeChunk(rows); // Gọi trực tiếp trên cùng instance.
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeChunk(List<ProductInput> rows) {
        // ...
    }
}
~~~

Trong mô hình Spring proxy-based transaction management phổ biến, `this.writeChunk(...)` **không đi qua proxy**, vì vậy annotation `@Transactional` có thể không tạo transaction như developer mong đợi. Đặt writer ở bean khác và gọi qua Spring-managed bean, hoặc dùng `TransactionTemplate` để mô tả transaction bằng callback rõ ràng.

### 7.3. REQUIRES_NEW không cắt một outer transaction thành phần nhỏ

Nếu caller đang có transaction A:

~~~text
Transaction A (caller)  ---- suspend ------------> resume
                                 |
                                 v
                          Transaction B (chunk)
                               COMMIT
~~~

Transaction B có thể commit dù A rollback sau đó. Việc suspend A cũng có thể giữ connection/lock trong khi B cần connection riêng, làm tăng áp lực lên connection pool. Nếu mục tiêu chỉ là mỗi chunk một transaction, thường **không mở outer transaction** trong orchestrator.

### 7.4. TransactionTemplate

`TransactionTemplate` giúp điều khiển ranh giới mà không phụ thuộc self-invocation:

~~~java
import org.springframework.transaction.support.TransactionTemplate;
import java.util.List;

public class TemplateChunkWriter {
    private final TransactionTemplate txTemplate;
    private final EntityManager em; // Injected transaction-scoped proxy.

    public TemplateChunkWriter(
            TransactionTemplate txTemplate,
            EntityManager em) {
        this.txTemplate = txTemplate;
        this.em = em;
    }

    public void writeChunk(List<ProductInput> rows) {
        txTemplate.executeWithoutResult(status -> {
            for (ProductInput row : rows) {
                em.persist(new Product(
                    row.sku(), row.name(), row.price()
                ));
            }
            em.flush();
        });
    }
}
~~~

Mẫu giả định template đã được cấu hình với transaction manager của ứng dụng. Nếu có transaction ngoài, propagation mặc định có thể tham gia transaction đó; muốn bắt buộc transaction mới, phải cấu hình propagation phù hợp trên template. Khi dùng Spring Data JPA, có thể dùng repository trong callback transaction, nhưng cần hiểu repository save/flush không phải commit.

### 7.5. Entity từ chunk A không tự managed trong chunk B

Một `Product` được tạo ở transaction A rồi giữ reference trong Java thường trở thành detached đối với persistence context của transaction B. Nếu cần sửa nó trong B, dùng `find` hoặc query theo ID để lấy managed entity hiện tại; hoặc `merge` có chủ đích và tiếp tục dùng **managed instance do merge trả về**. Không suy luận object còn ID nghĩa là vẫn managed.

## 8. Đơn vị transaction phải khớp bất biến nghiệp vụ

Nếu một phiếu nhập có header và ba dòng:

~~~text
InventoryReceipt R-100
  |
  +-- Line 1: +10 SKU A
  +-- Line 2: +12 SKU B
  +-- Line 3: +5  SKU C
~~~

cắt transaction giữa line 1 và line 2 có thể tạo một phiếu nhập nửa vời dù mỗi transaction đều commit thành công. Lúc đó kích thước chunk kỹ thuật xung đột với **đơn vị nhất quán của domain**.

Các lựa chọn thiết kế:

- Một receipt là một đơn vị transaction, dù số dòng thay đổi.
- Dùng trạng thái `DRAFT`/`IN_PROGRESS`, nhập thành nhiều transaction, rồi publish khi đầy đủ.
- Nhập vào staging tables, sau đó kiểm tra và kích hoạt dữ liệu theo transaction có kiểm soát.
- Nếu qua nhiều dịch vụ/DB, cần mô hình outbox, saga hoặc một quy trình phối hợp, không thể chỉ trông chờ transaction JPA.

**Chunk size là một lựa chọn kỹ thuật; transaction boundary là quyết định nhất quán dữ liệu.** Chúng chỉ trùng nhau khi mỗi chunk thực sự có thể commit độc lập.

Các câu hỏi phải trả lời nếu dùng nhiều commit:

- Chunk đã commit thì có được nhìn thấy ngay bởi người dùng không?
- Job thất bại một nửa, có tiếp tục dùng phần dữ liệu đã nhập được không?
- Có cần checkpoint/resume và báo cáo partial success không?
- Một bản ghi lỗi có làm cả chunk thất bại hay được phép skip?
- Nhiều worker có được xử lý cùng một record không?
- Nếu thứ tự xử lý có ý nghĩa, làm sao bảo đảm commit đúng thứ tự?

Không thể giải quyết các câu hỏi trên chỉ bằng `flush` hoặc `clear`.
## 9. Checkpoint, retry và idempotency qua nhiều giao dịch

Một batch job có nhiều transaction cần nhận biết chunk nào đã commit, chunk nào chưa xử lý và chunk nào đang ở trạng thái không rõ ràng.

Giả sử tiến trình:

~~~text
09:00:01  Chunk 17 COMMIT thành công.
09:00:02  Process chết trước khi ghi "chunk 17 done".
09:00:10  Worker mới tiếp tục từ checkpoint chunk 16.
09:00:11  Chunk 17 bị xử lý lại.
~~~

Nếu mỗi lần import tự sinh ID mới và không có ràng buộc nghiệp vụ, retry có thể tạo dữ liệu trùng. Vì thế **idempotency** là yếu tố cốt lõi: chạy lại cùng một tác vụ không được tạo thêm hiệu ứng ngoài dự kiến.

### 9.1. Business key và UNIQUE constraint

`Product.sku` có thể là business key. Database nên có một unique constraint thực:

~~~sql
ALTER TABLE products
ADD CONSTRAINT uk_products_sku UNIQUE (sku);
~~~

Constraint này ngăn hai row cùng SKU. Nhưng không có nghĩa retry gặp duplicate sẽ tự được coi là thành công. Ứng dụng phải quyết định:

- Nếu row cũ giống hệt nội dung dự định: bỏ qua và ghi nhận đã xử lý?
- Nếu row cũ khác nội dung: ghi đè, từ chối hay tạo một revision?
- Nếu SKU thuộc một tenant: uniqueness phải theo `(tenant_id, sku)` thay vì riêng SKU?
- Nếu dữ liệu có trạng thái xóa mềm: unique index cần phù hợp quy tắc còn hiệu lực?

Một `SELECT` kiểm tra “chưa có SKU” trước `INSERT` không bảo vệ race condition khi hai worker cùng kiểm tra. Cần constraint tại DB và handling khi vi phạm. Upsert database-specific như PostgreSQL `ON CONFLICT` có thể hữu ích, nhưng phải hiểu rằng native SQL/bulk DML có semantics khác với entity lifecycle của JPA.

### 9.2. Lưu checkpoint và dữ liệu trong cùng transaction

Ví dụ bảng quản lý chunk:

~~~sql
CREATE TABLE import_chunks (
    job_id VARCHAR(64) NOT NULL,
    chunk_number BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    processed_count INTEGER NOT NULL,
    PRIMARY KEY (job_id, chunk_number)
);
~~~

Nếu cùng database và transaction, khi xử lý chunk có thể ghi sản phẩm và cập nhật trạng thái `COMPLETED` của chunk **trước cùng một commit**. Như vậy tiến độ và dữ liệu cùng thành công hoặc cùng rollback.

Không nên ghi dữ liệu trong transaction A rồi ghi checkpoint bằng một transaction B tách biệt mà bỏ qua khoảng trống crash giữa hai commit. Nếu kiến trúc buộc dùng hai hệ thống khác nhau, cần cơ chế hòa giải (reconciliation), outbox hoặc giao thức phù hợp.

Checkpoint chỉ có ý nghĩa nếu nguồn dữ liệu xác định được chính xác. Khi đọc tệp, có thể cần ID/hash của tệp và vị trí; khi đọc DB, có thể cần cutoff ID, version query và job configuration. Nếu dữ liệu nguồn thay đổi giữa hai lần chạy, “resume tại dòng 5000” chưa chắc quay lại cùng công việc.

### 9.3. Lỗi commit có thể mơ hồ

Trường hợp mất kết nối đúng lúc COMMIT: ứng dụng có thể không biết database đã commit hay chưa. Ngoại lệ mạng không đủ để kết luận “chắc chắn chưa lưu”. Retry mù quáng trong tình huống đó có thể lặp hiệu ứng.

Một mô hình job có thể phân biệt:

- `COMPLETED`: dữ liệu và checkpoint được xác nhận.
- `FAILED`: đã xác nhận rollback/lỗi không thể thực hiện.
- `UNKNOWN`: kết quả commit chưa rõ, cần truy vấn đối chiếu trước khi retry.
- `RETRYING`: thực hiện lại có kiểm soát nhờ idempotency key.

Tên trạng thái trên là thiết kế của ứng dụng, không phải enum bắt buộc của Hibernate.

### 9.4. Retry phải ở transaction và context mới

Mẫu xử lý nguy hiểm:

~~~java
try {
    em.persist(productA);
    em.flush();
} catch (PersistenceException ex) {
    // Không nên nuốt lỗi rồi tiếp tục dùng transaction bị lỗi.
    em.persist(productB);
}
~~~

Sau constraint violation hoặc lỗi SQL, transaction có thể đã bị đánh dấu rollback-only hoặc database coi transaction là aborted. Hibernate persistence context sau lỗi cũng không nên được giả định còn đồng bộ với database.

Cách triển khai đáng tin cậy:

1. Rollback transaction thất bại, nếu nó còn active và có thể rollback.
2. Đóng/discard EntityManager của chunk.
3. Phân loại lỗi: transient, conflict nghiệp vụ, dữ liệu sai, lỗi hạ tầng.
4. Nếu được retry, tạo **transaction và persistence context mới**, không dùng lại context lỗi.
5. Áp dụng retry có giới hạn và backoff phù hợp, giữ idempotency.
6. Ghi tiến độ/lỗi của job ở ranh giới transaction phù hợp.

Một deadlock có thể là tình huống retry sau rollback; một ISBN/SKU sai định dạng sẽ không được sửa bằng retry nguyên payload.

### 9.5. Isolate bản ghi lỗi trong một chunk

Một chunk có 500 row nhưng chỉ một row vi phạm `UNIQUE`. Nếu DB đã từ chối thao tác trong transaction, không thể đơn giản bỏ qua row lỗi và tiếp tục trên cùng transaction một cách portable.

Những lựa chọn có thể gồm:

- Rollback cả chunk và yêu cầu xử lý dữ liệu đầu vào.
- Rollback rồi chia chunk nhỏ hơn để tìm row lỗi.
- Validate trước để giảm lỗi dự đoán được, nhưng vẫn giữ DB constraints chống concurrency.
- Khi cho phép partial success ở mức row, dùng transaction nhỏ hơn cho những row đặc biệt, với giới hạn tài nguyên.
- Dùng cơ chế skip/retry của Spring Batch khi phù hợp, hiểu rõ reader/writer transaction semantics.

Việc dùng JDBC savepoint trực tiếp có thể tồn tại ở một số database, nhưng không nên mặc định việc giữ lại Hibernate persistence context và state sau lỗi rồi rollback một phần bằng savepoint là an toàn ở mọi phiên bản/provider.

## 10. Đọc dữ liệu theo lô mà không làm context phình to

Xử lý theo lô không chỉ có INSERT. Một tác vụ thường **đọc các entity cũ, sửa chúng và ghi lại**. Nếu đọc 200.000 managed entities vào một persistence context duy nhất, memory có thể tăng ngay cả khi chỉ chỉnh một trường đơn giản.

### 10.1. Tránh findAll toàn bộ

Mẫu tiềm ẩn rủi ro:

~~~java
List<Product> products = em.createQuery(
    "select p from Product p",
    Product.class
).getResultList();

for (Product p : products) {
    p.changePrice(calculatePrice(p));
}
~~~

Tùy kích thước bảng, câu truy vấn có thể tải hàng trăm nghìn entity và giữ chúng ở first-level cache. Kể cả đã thiết lập `hibernate.jdbc.batch_size`, nó chỉ tác động phần JDBC statement phù hợp, **không làm danh sách Java nhỏ đi**.

### 10.2. Phân trang bằng OFFSET: dễ hiểu nhưng có rủi ro

~~~java
List<Product> page = em.createQuery(
        "select p from Product p order by p.id",
        Product.class)
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();
~~~

Nếu nguồn không đổi trong suốt job, OFFSET pagination có thể phù hợp cho dữ liệu vừa phải. Nhưng:

- OFFSET lớn có thể kém hiệu quả tùy database và execution plan.
- Khi job đồng thời sửa/xóa dữ liệu thuộc tập đang duyệt, các trang có thể dịch chuyển.
- Nếu điều kiện đọc dựa vào trạng thái đang cập nhật, row có thể bị bỏ qua hoặc xử lý lặp.
- Một transaction dài đọc nhiều trang có thể giữ snapshot/locks lâu.
- Thứ tự phải ổn định; query không `order by` không bảo đảm trang nào chứa record nào.

### 10.3. Keyset pagination theo khóa tăng dần

Một chiến lược phổ biến khi đọc theo ID ổn định:

~~~java
List<Long> ids = em.createQuery(
        "select p.id from Product p " +
        "where p.id > :lastId and p.id <= :cutoff " +
        "order by p.id",
        Long.class)
    .setParameter("lastId", lastId)
    .setParameter("cutoff", cutoffId)
    .setMaxResults(pageSize)
    .getResultList();
~~~

Sau mỗi page, cập nhật `lastId` bằng ID cuối cùng đã chọn, rồi ghi checkpoint tương ứng nếu cần.

Giả sử cutoff được xác định khi bắt đầu job:

~~~java
Long cutoffId = em.createQuery(
    "select max(p.id) from Product p", Long.class
).getSingleResult();

if (cutoffId == null) {
    return; // Bảng đang trống.
}
~~~

`cutoffId` giới hạn những ID lớn hơn được thêm sau khi job bắt đầu. Nó **không phải** snapshot transaction toàn diện: những row có ID thấp hơn cutoff vẫn có thể được thêm muộn, sửa, xóa hoặc thay đổi điều kiện lọc tùy generator/concurrency. Muốn cam kết bộ dữ liệu nguồn cố định phải có thêm chiến lược consistency, snapshot/staging hoặc khóa/claim tương ứng.

### 10.4. Đọc ID/DTO trước, ghi bằng context riêng

Một mẫu dễ quản lý:

~~~text
Reader (read-only context / short transaction)
        |
        +-- SELECT id order by id, limit 500
        |
        v
List<Long> IDs (không phải managed entities)
        |
        v
Writer (transaction & persistence context riêng)
        |
        +-- find/getReference/update phù hợp cho từng ID
        +-- flush
        +-- commit
        |
        v
Checkpoint last successfully processed ID
~~~

Nếu reader dùng DTO projection như `select new ...`, nó không tạo managed instances cho chính DTO. Điều này giảm áp lực first-level cache so với việc đọc toàn bộ entity rồi giữ chúng qua nhiều transaction.

Một caveat: **giữ transaction đọc và transaction ghi tách biệt tạo khoảng thời gian dữ liệu có thể thay đổi**. Writer cần kiểm tra lại điều kiện nghiệp vụ hoặc dùng optimistic locking/claim để không xử lý bản ghi đã đổi trạng thái ngoài ý định.

### 10.5. Tránh dùng entity detached làm dữ liệu giữa các chunk

Ví dụ nguy hiểm:

~~~java
// Reader ở transaction A:
List<Product> list = emA.createQuery(
    "select p from Product p", Product.class
).getResultList();
emA.close();

// Writer ở transaction B:
for (Product p : list) {
    p.changePrice(...); // p hiện detached.
}
~~~

Việc sửa `p` sau khi context đọc đóng không tự UPDATE. Có thể `merge`, nhưng merge một graph detached lớn có thể sao chép dữ liệu cũ, kéo theo cascade và làm mất những thay đổi mới ở DB nếu không kiểm soát.

Thường dễ hiểu hơn là truyền **ID + dữ liệu cần xử lý** cho writer, rồi lấy managed entity trong transaction ghi và thay đúng những field cho phép.

### 10.6. Khi nhiều worker cùng đọc dữ liệu

Nếu hai job instance cùng chọn `status = 'PENDING'` bằng query bình thường, cả hai có thể xử lý cùng row. Cần cơ chế claim công việc:

- Cột trạng thái `PENDING -> PROCESSING -> DONE` với update có điều kiện.
- Optimistic locking qua `@Version`.
- Database locking như `SELECT ... FOR UPDATE SKIP LOCKED` khi DB hỗ trợ, sử dụng đúng isolation và transaction.
- Work queue/message broker với semantics phù hợp và idempotent consumer.
- Partition key để chia tập công việc theo phạm vi không giao nhau.

`SKIP LOCKED` là tính năng database-specific và không phải JPQL portable cho mọi DB. Phải kiểm tra đúng khả năng driver, dialect và thiết kế row-level locking; không dùng nó như lời hứa “exactly once” cho toàn job.

## 11. Streaming, scroll và thời gian sống của context

Hibernate và JPA có những cách đọc kết quả theo luồng hoặc cuộn cursor, nhưng **stream không đồng nghĩa mọi dữ liệu đã được giải phóng tự động**.

Ví dụ:

~~~java
try (Stream<Product> stream = em.createQuery(
        "select p from Product p order by p.id",
        Product.class).getResultStream()) {

    stream.forEach(product -> process(product));
}
~~~

Đoạn code cần `java.util.stream.Stream`. Behavior streaming/cursor phụ thuộc Hibernate version và JDBC driver. Những điều phải lưu ý:

- Query trả **entity** có thể làm mỗi hàng được nạp trở thành managed, khiến context phình to dù `ResultSet` được đọc lần lượt.
- Cursor/stream có thể giữ JDBC connection, transaction hoặc ResultSet mở; đóng stream và context theo đúng phạm vi.
- Không giả định có thể commit transaction đang giữ cursor rồi tiếp tục duyệt hợp lệ trên mọi database.
- Nếu gọi `clear()` khi đang xử lý stream, những entity trước đó detach; quan hệ lazy và reference giữa entities có thể thay đổi hành vi.
- Mô hình cursor dài không nhất thiết phù hợp với job nhiều transaction ngắn; keyset pagination/reader partition thường rõ ràng hơn.

Hibernate có API `scroll()` và `ScrollableResults` ở những phiên bản cụ thể. Khi dùng, phải xem đúng Javadoc về vòng đời resource, forward-only scrolling, flush/clear và tác động đến persistence context. Không sao chép các method scroll cũ của Hibernate 5 cho Hibernate 6/7 mà chưa đối chiếu.

## 12. Bulk JPQL/SQL và trạng thái stale của context

Khi cần tăng giá 10% cho nhiều sản phẩm, có thể chọn:

**Cách entity-by-entity:**

~~~java
List<Product> products = em.createQuery(
    "select p from Product p where p.active = true",
    Product.class
).getResultList();

for (Product p : products) {
    p.changePrice(p.getPrice().multiply(new BigDecimal("1.10")));
}
~~~

Phần minh họa giả định entity thực tế có trường `active` và các method tương ứng. Cách này phát huy dirty checking, entity callback và optimistic locking theo mapping thông thường, nhưng nạp nhiều entity và có thể phát sinh nhiều SQL UPDATE.

**Cách bulk JPQL DML:**

~~~java
int updated = em.createQuery(
        "update Product p " +
        "set p.price = p.price * :factor " +
        "where p.id <= :cutoff")
    .setParameter("factor", new BigDecimal("1.10"))
    .setParameter("cutoff", cutoffId)
    .executeUpdate();
~~~

Bulk DML thao tác trực tiếp trên nhiều row mà không quản lý từng entity theo cùng cơ chế dirty checking. Nó có thể hiệu quả hơn cho cập nhật đơn giản, nhưng cần đặc biệt lưu ý:

- Các `Product` đã managed trong context **có thể tiếp tục giữ giá cũ** trong RAM.
- Entity lifecycle callbacks như `@PreUpdate` không chạy cho từng entity theo cách cập nhật managed entity thông thường.
- Cascade và association lifecycle không được áp dụng giống vòng lặp xử lý entity.
- Optimistic versioning trong bulk update cần được giải quyết riêng; bulk JPQL DML không tự có đầy đủ cơ chế version check của từng managed entity.
- Câu lệnh `executeUpdate` thường yêu cầu transaction hợp lệ.
- Lượng row bị ảnh hưởng và constraint DB cần được giám sát/đánh giá theo nghiệp vụ.

### 12.1. Bulk update rồi find cùng ID trong context cũ

~~~java
Product p = em.find(Product.class, productId);
// p.price = 100

em.createQuery(
    "update Product p set p.price = 120 where p.id = :id"
).setParameter("id", productId).executeUpdate();

// p trong context có thể vẫn giữ price = 100.
~~~

Nếu ngay sau đó gọi `em.find(Product.class, productId)` trong cùng context, Hibernate có thể trả lại managed instance cũ từ identity map chứ không tự refresh theo bulk DML. Cần chủ động xử lý context stale:

- Dùng transaction/context mới sau bulk operation.
- `em.clear()` nếu không còn thay đổi managed chưa flush cần giữ.
- `em.refresh(p)` khi cần cập nhật một instance cụ thể và hiểu rằng thay đổi local có thể bị ghi đè.

**Không gọi `clear()` vô điều kiện** nếu context còn pending changes của những entity khác. Có thể cần flush trước bulk operation và đóng/clear context sau đó theo một ranh giới có chủ đích.

### 12.2. Native SQL không thông báo tự động mọi thay đổi cho context

Nếu một đoạn JDBC hoặc hệ thống khác sửa database ngoài Hibernate, first-level cache của EntityManager đang mở không tự cập nhật. Điều này càng lý giải vì sao giữ một context sống qua nhiều transaction là rủi ro với job có dữ liệu thay đổi thường xuyên.

Với bảng lớn, việc chọn bulk DML có thể đúng vì nhu cầu chỉ là cập nhật đồng loạt theo một biểu thức SQL. Nhưng nếu logic update phụ thuộc domain methods, validation, cascade hoặc entity callbacks, phải cân nhắc kỹ việc bỏ qua entity-level processing.
## 13. Hibernate StatelessSession: khi nào giảm chi phí persistence context?

Hibernate cung cấp API riêng `StatelessSession` dành cho một số công việc đọc/ghi lượng lớn dữ liệu khi không cần cơ chế quản lý entity đầy đủ của `Session` thông thường.

### 13.1. Khác biệt khái niệm

| Khả năng | `EntityManager` / stateful `Session` | `StatelessSession` của Hibernate |
|---|---|---|
| First-level persistence context/identity map | Có | Không có theo mô hình stateful thông thường |
| Dirty checking tự động | Có | Không vận hành theo mô hình managed entity + dirty checking |
| Flush/clear managed entity | Có ý nghĩa | Không có cùng ngữ nghĩa vì không giữ managed graph |
| Cascade từ mapping entity | Được áp dụng theo thao tác và mapping | Không tự động tương đương cơ chế cascade của stateful Session |
| Collections và proxy lazy | Hỗ trợ theo mapping/context | Cần hiểu giới hạn, không dựa vào lazy graph như stateful Session |
| Tác động của thay đổi setter | Có thể được flush nếu entity managed | Cần thao tác ghi tường minh theo contract API |
| Hỗ trợ entity callbacks/interceptors | Theo cơ chế JPA/Hibernate | Không nên mặc định lifecycle events giống stateful Session |
| Phù hợp | CRUD nghiệp vụ, aggregate, dirty checking, relations | Một số ETL/import/export thuần dữ liệu, ít cần entity graph |

`StatelessSession` không phải một cơ chế “bật nhanh Hibernate và mọi logic vẫn giữ nguyên”. Nó thay đổi cách ứng dụng chịu trách nhiệm về SQL và state. Nếu business logic dựa vào cascading, dirty checking, lazy collections hoặc entity listeners, việc thay bằng StatelessSession có thể làm sai hành vi.

### 13.2. Khi nào cân nhắc?

Một công việc bulk chuyển đổi dữ liệu có các đặc điểm:

- Mỗi record tương đối độc lập.
- Dữ liệu đã được validate và chuẩn hóa ở tầng input.
- Không cần duyệt object graph sâu.
- Không cần JPA lifecycle callbacks cho từng entity.
- Code có thể chủ động thực hiện insert/update/delete.
- Schema và transaction boundary được quản lý rõ.

Trong tình huống đó, `StatelessSession` có thể giảm chi phí giữ entity states. Nhưng lựa chọn vẫn phụ thuộc Hibernate version và cơ chế JDBC batching của `StatelessSession` ở version đó; không giả định batch insert sẽ tự hoạt động như stateful Session với cùng cấu hình.

### 13.3. Mẫu ý tưởng, không phải code drop-in

~~~text
Mỗi chunk:
    mở StatelessSession
    bắt đầu transaction
    với mỗi record trong chunk:
        chuyển Input -> entity/value phù hợp
        gọi thao tác ghi tường minh (insert/update)
    commit chunk
    đóng StatelessSession

Khi exception:
    rollback
    đóng session
    retry bằng context/session mới theo idempotency
~~~

Khi viết mã thật, dùng API của đúng phiên bản Hibernate để mở session, begin transaction, ghi và xử lý exception. Một số API của Hibernate 6.x/7.x, đặc biệt liên quan native session, mutation và batching, có chữ ký/hành vi khác nhau. Đọc Javadoc của phiên bản đang dùng thay vì chuyển một đoạn mẫu `Session` sang `StatelessSession` bằng cách đổi tên type.

### 13.4. Còn dùng JDBC thuần được không?

Có. Với thao tác SQL đơn giản, database-specific upsert, COPY/bulk-loader hoặc thao tác set-based quy mô lớn, `JdbcTemplate` hoặc JDBC thuần có thể phù hợp hơn một entity loop. Đổi lại, ứng dụng chịu trách nhiệm mapping SQL, transaction, kiểm soát driver, ràng buộc và lỗi.

Quy tắc lựa chọn:

- Cần dirty checking/cascade/logic entity: bắt đầu từ stateful EntityManager.
- Cần import độc lập theo record nhưng vẫn thích Hibernate mapping: cân nhắc StatelessSession có hiểu biết về giới hạn.
- Cần bulk SQL, upsert hoặc chức năng đặc thù DB: cân nhắc JDBC hoặc native SQL.
- Cần job có checkpoint, retry, skip và restart: cân nhắc framework xử lý lô ở tầng orchestration, không chỉ đổi API persistence.

## 14. Spring Batch và ranh giới chunk transaction

Nếu ứng dụng có job chạy định kỳ, chịu lỗi, cần restart, skip và retry có cấu hình, Spring Batch là một lựa chọn chuyên biệt hơn việc viết mọi cơ chế điều phối thủ công.

Về mặt khái niệm:

~~~text
Job
  |
  +-- Step
       |
       +-- ItemReader  (đọc)
       +-- ItemProcessor (chuyển đổi/kiểm tra)
       +-- ItemWriter  (ghi)
       |
       +-- Chunk boundary
             đọc N items
             xử lý N items
             ghi N items
             COMMIT
             cập nhật job/step execution metadata phù hợp
~~~

Framework hỗ trợ khai báo chunk-oriented processing, transaction manager, restartability và các cơ chế fault tolerance tùy version/configuration. **Không thể chỉ đưa một `EntityManager` dùng chung vào mọi step rồi kết luận ranh giới context đã tối ưu**. Cần hiểu:

- Item reader trả DTO, entity hay managed objects?
- Nếu reader là JPA paging reader, sau mỗi page entity có còn managed trong writer không?
- Writer dùng JpaItemWriter hoặc writer JDBC, và method ghi nằm trong transaction nào?
- Context được clear/detach ở đâu?
- Chunk retry có idempotent không?
- Checkpoint của reader dựa vào cursor, index, business key hay trạng thái nguồn?
- Chạy nhiều partitions/threads có chia sẻ EntityManager không? (Không chia sẻ EntityManager giữa threads.)
- Framework ghi JobRepository metadata và business rows ở cùng transaction manager/database hay không?

Các API cấu hình Job/Step/Reader/Writer thay đổi giữa các phiên bản Spring Batch. Hãy dùng tài liệu version đang phụ thuộc thay vì sao chép các builder API cũ.

### 14.1. Một step chunk không bảo đảm exactly-once toàn hệ thống

Ngay cả khi Spring Batch lưu progress, nếu writer gọi một REST API hoặc gửi message tới dịch vụ khác, transaction database của step thường **không tự rollback được side effect ở hệ thống ngoài**. Một message đã gửi không được “unsend” chỉ vì DB rollback.

Trong trường hợp này, cần outbox, idempotent external APIs, duplicate detection hoặc quy trình phối hợp/compensation phù hợp. Không nên tuyên bố job exactly once chỉ vì có chunk commit.

### 14.2. Đặt giới hạn concurrency

Nhiều threads có thể tăng throughput nhưng cũng tạo:

- Cạnh tranh connection pool.
- Deadlock hoặc lock contention trong database.
- Tranh chấp unique keys.
- Thứ tự xử lý không còn tất định.
- Retry trùng khi workers claim cùng job item.
- Mức sử dụng memory tăng theo số chunk chạy đồng thời.

Cần thiết kế partition/claim, concurrency limit và chính sách khóa cụ thể. `EntityManagerFactory` thường dùng chung qua threads theo hợp đồng provider; **EntityManager** thì không thread-safe và phải theo scope thích hợp.

## 15. Isolation, version và context stale qua nhiều transaction

### 15.1. First-level cache không biết mọi thay đổi từ transaction khác

Ví dụ:

~~~text
Context A / Tx A:
    SELECT Product #42, price=100
    COMMIT A
    vẫn giữ context A mở

Context B / Tx B:
    UPDATE Product #42, price=120
    COMMIT B

Context A:
    find(Product.class, 42)
    có thể trả managed instance price=100 từ identity map
~~~

Việc commit B không tự invalidated first-level cache của một EntityManager khác. Nếu A giữ context quá lâu, nó có thể đọc stale entity state, hoặc thực hiện ghi ngoài ý định dựa trên dữ liệu cũ.

Với transaction-scoped context mới mỗi chunk, nguy cơ giữ managed instances cũ xuyên các transaction giảm rõ rệt. Nhưng concurrency vẫn tồn tại vì dữ liệu có thể thay đổi giữa lúc reader lấy ID và writer xử lý.

### 15.2. Optimistic locking bằng @Version

Một entity:

~~~java
@Version
private long version;
~~~

cho phép Hibernate phát hiện một số cập nhật đồng thời trên cùng row trong luồng managed-entity update. Ví dụ:

~~~text
Transaction A đọc Product #42, version=3
Transaction B đọc Product #42, version=3

B cập nhật và commit -> version=4
A cố cập nhật từ version=3 -> OptimisticLockException hoặc lỗi liên quan
~~~

Thời điểm exception có thể là flush/commit. Khi gặp optimistic-lock conflict, thường phải rollback chunk hiện tại và retry trong transaction/context mới với dữ liệu được nạp lại hoặc xử lý conflict theo nghiệp vụ.

Không nên mặc định mọi native SQL/bulk JPQL update tự tăng version giống Hibernate entity update. Khi dùng set-based SQL, phải thiết kế version predicate/increment nếu mục tiêu cần optimistic locking.

### 15.3. Isolation level không thay thế checkpoint

Các mức isolation như READ COMMITTED, REPEATABLE READ hoặc SERIALIZABLE ảnh hưởng cách transaction nhìn dữ liệu đồng thời và xử lý anomaly; chi tiết phụ thuộc database. Nhưng dù ở SERIALIZABLE, **nhiều transaction khác nhau vẫn có nhiều điểm commit**, không trở thành một transaction atomic cho cả import.

Một job dùng nhiều transaction có thể quan sát dữ liệu nguồn thay đổi giữa chunks. Muốn một snapshot nguồn cố định, cần:

- Chuẩn bị tập ID/record đầu vào vào staging/snapshot.
- Xác định cutoff và điều kiện đọc ổn định.
- Dùng cơ chế snapshot DB phù hợp khi thực sự cần (có chi phí riêng).
- Hoặc chấp nhận semantics “xử lý những row thỏa điều kiện tại thời điểm từng chunk”.

### 15.4. Pessimistic locking và SKIP LOCKED

Một queue database có thể dùng row lock để nhiều workers claim task mà không lấy cùng một row. Tùy DB, `FOR UPDATE SKIP LOCKED` có thể giúp workers bỏ qua hàng đang bị worker khác khóa.

Điều quan trọng:

- Lock tồn tại trong transaction, không phải một property của entity sau khi detach.
- Commit/rollback giải phóng lock theo quy tắc DB.
- `SKIP LOCKED` không đảm bảo thứ tự tuyệt đối hoặc fairness.
- Một row được claim cần có trạng thái/lease hoặc cơ chế recovery nếu worker chết.
- Chờ khóa lâu/đụng độ nhiều làm throughput giảm thay vì tăng.

Đối với nhiều worker, phân chia workload/claim idempotent thường quan trọng hơn việc tăng riêng `hibernate.jdbc.batch_size`.

## 16. Vấn đề OSIV và context sống theo request

**Open Session in View (OSIV)** giữ session/persistence context sẵn sàng trong một phạm vi xử lý web để cho phép truy cập lazy associations sau khi service đã hoàn tất transaction. Đây là một lựa chọn kiến trúc ở tầng web, không phải cơ chế tối ưu batch job.

Tương tự, một EntityManager được giữ mở quá lâu để tránh `LazyInitializationException` có thể khiến:

- Connection/query phát sinh ngoài transaction nghiệp vụ dự kiến.
- Object graph bị nạp không kiểm soát từ serializer/view.
- First-level cache giữ state cũ.
- Khó xác định transaction boundary khi xử lý lỗi.
- Rủi ro sử dụng memory lâu dài.

Trong batch/background worker, nên có **ranh giới context rõ ràng**: mỗi chunk hoặc mỗi đơn vị công việc mở/nối context theo transaction, xử lý xong thì đóng/rời context. Đối với API, DTO hoặc fetch plan rõ ràng giúp không phải giữ context sống chỉ để JSON serializer duyệt association.

## 17. Các mẫu cần tránh và cách thay thế

| Mẫu dễ gây lỗi | Vấn đề | Hướng tiếp cận |
|---|---|---|
| Một EntityManager xử lý hàng triệu entities mà không clear | First-level cache và snapshots phình to | Chia chunk, flush/clear hoặc context mới |
| Coi `flush()` là commit chunk | Không có checkpoint transaction; rollback vẫn ảnh hưởng toàn bộ | Commit/rollback theo chunk độc lập |
| Gọi `clear()` trước khi pending changes được flush | Có thể bỏ thao tác chưa đồng bộ | Flush có chủ đích trước clear |
| Giữ một context qua nhiều transaction để tiết kiệm khởi tạo | State stale, memory và transaction interaction phức tạp | Context mới theo transaction/chunk |
| Bật JDBC batch size nhưng không giới hạn entity graph | Batch SQL không giải phóng managed instances | Kiểm soát context size và data reader |
| `@Transactional` method cùng class được gọi bằng `this` | Spring proxy có thể không áp dụng transaction | Bean writer riêng hoặc TransactionTemplate |
| Outer transaction bao mọi chunk trong khi mong commit từng chunk | Atomicity khác mong đợi | Điều phối không có outer transaction |
| Retry trên cùng EntityManager sau PersistenceException | Context/transaction có thể hỏng hoặc DB aborted | Rollback, close và context mới |
| Chỉ checkpoint sau commit ở transaction khác | Crash tạo trạng thái tiến độ lệch dữ liệu | Cùng transaction khi khả thi, idempotency |
| OFFSET pagination trên tập đang thay đổi | Bỏ sót/lặp row hoặc tốn chi phí lớn | Keyset theo khóa ổn định và policy snapshot |
| Đưa entity detached từ reader sang writer rồi sửa | Dirty checking không chạy trên detached | Truyền ID/DTO, find managed trong writer |
| Bulk JPQL DML nhưng đọc lại managed entity cũ | First-level cache stale | Context mới, refresh/clear có kiểm soát |
| Cascade REMOVE trên entity dùng chung | Xóa nhầm dữ liệu | Thiết kế lifecycle/cascade theo aggregate |
| Duyệt stream entity rất dài rồi nghĩ memory cố định | Entity vẫn có thể được giữ managed | DTO projection hoặc clear/reader strategy |
| Dùng Stateful Session API trong nhiều threads | EntityManager/Session không thread-safe | Context riêng cho mỗi worker/thread |
| Bật StatelessSession mà mong callbacks/cascade/dirty checking như cũ | Semantics của API khác | Chọn API theo nhu cầu, ghi tường minh |

### 17.1. Khi kết nối bị đóng hoặc timeout giữa chunk

Nếu job xử lý tốn CPU rất lâu giữa các thao tác DB, một transaction mở suốt thời gian tính toán có thể giữ connection không cần thiết. Có thể tách:

1. Đọc dữ liệu đầu vào (DTO) và xử lý CPU ngoài transaction ghi.
2. Mở transaction khi chuẩn bị ghi một chunk.
3. Revalidate các điều kiện có thể đã thay đổi.
4. Ghi kết quả và checkpoint trong transaction ngắn.
5. Commit và đóng context.

Tuy nhiên, tính đúng đắn của bước revalidate vẫn phải dựa vào unique constraint/version/locking nếu có concurrent modification. Không chỉ kiểm tra trước transaction rồi mặc định dữ liệu vẫn giữ nguyên.

### 17.2. Đừng dùng EntityManagerFactory như EntityManager

`EntityManagerFactory` là đối tượng cấp cao, thường được tạo một lần theo persistence unit và chia sẻ trong ứng dụng. `EntityManager` được tạo/được inject với scope phù hợp cho từng unit of work.

Không tạo mới `EntityManagerFactory` mỗi chunk vì bootstrap metadata/pool quá tốn kém. Nhưng cũng không đưa cùng một EntityManager instance vào tất cả chunks/threads để tránh chi phí tạo context. Hai đối tượng có lifecycle khác nhau.

### 17.3. Khi nào nên chuyển sang SQL set-based?

Nếu chỉ cần tăng giá theo điều kiện, SQL `UPDATE ... WHERE ...` có thể nhanh hơn tải entity vào Java, dirty-check và gọi UPDATE từng row. Nhưng SQL set-based không tự thực hiện:

- Entity lifecycle callbacks như cập nhật audit fields bằng `@PreUpdate`.
- Domain methods kiểm tra quy tắc thay đổi.
- Cascade của entity graph.
- Optimistic version checks cho từng entity, nếu không viết riêng.
- Đồng bộ các managed entities đã có trong context.

Nếu quy tắc nghiệp vụ đòi hỏi các hành vi đó, hãy cân nhắc stateful entity processing theo chunk, hoặc bổ sung các bảo vệ/tính toán tương đương khi dùng bulk SQL.

## 18. Chọn chiến lược: ma trận quyết định

| Nhu cầu nổi bật | Hướng tiếp cận thường phù hợp |
|---|---|
| Toàn bộ import phải all-or-nothing | Một transaction, `flush/clear` theo đợt nếu cần |
| Có thể commit từng nhóm độc lập | Chunk transactions với context riêng |
| Job rất lớn, cần resume/retry | Checkpoint + idempotency + transaction theo chunk |
| Data graph phức tạp, cần cascade và dirty checking | Stateful `EntityManager`/`Session` |
| Record độc lập, không cần stateful lifecycle | Cân nhắc `StatelessSession` hoặc JDBC |
| Cập nhật hàng triệu row theo điều kiện đơn giản | Bulk JPQL/SQL set-based có kiểm soát stale context |
| Reader từ bảng lớn đang thay đổi | Keyset/claim/snapshot strategy tùy semantics |
| Cần reader/writer orchestration và restart | Spring Batch hoặc framework batch phù hợp |
| Nhiều node/worker chạy song song | Partition/claim/locking/idempotency |
| Ràng buộc dữ liệu liên bảng phải cùng commit | Transaction theo aggregate, staging hoặc workflow phối hợp |
| Một bean Spring tự gọi method `@Transactional` | Tách bean/proxy đúng hoặc TransactionTemplate |
| Tính nhất quán sau bulk SQL | Context mới hoặc refresh/clear đúng lúc |

Bảng trên giúp đặt câu hỏi, không thay thế thiết kế theo workload thật. Chẳng hạn, mỗi chunk 100 bản ghi là quá nhỏ hay quá lớn tùy độ phức tạp của entity graph và database. Cần chọn kích thước theo giới hạn tài nguyên, mục tiêu latency/throughput và nghiệp vụ partial success.
## 19. Bài tập tình huống

### Bài 1 — Flush không phải commit

Một job mở một transaction, cứ 100 row gọi `em.flush(); em.clear();`. Đến row thứ 5.000 gặp lỗi `UNIQUE` và rollback transaction.

**Câu hỏi:** 4.900 row đã flush trước đó có được giữ trong DB không?

**Định hướng:** Nếu chúng thuộc cùng database transaction và chưa commit, rollback sẽ hủy cả những SQL đã flush. Flush có thể giảm context/pending work nhưng **không** tạo mốc commit.

### Bài 2 — Nhận diện nơi dùng bộ nhớ

Một vòng lặp lấy 100.000 managed `Product` bằng `getResultList()`, gọi setter, rồi chỉ `flush()` một lần ở cuối.

**Câu hỏi:** bật `hibernate.jdbc.batch_size=50` có loại bỏ nguy cơ memory tăng vì 100.000 managed entities không?

**Định hướng:** Không. JDBC batching giảm số round-trip cho SQL phù hợp, không tự giới hạn list Java hoặc first-level cache. Cần reader theo page/stream có quản lý context và flush/clear hoặc transaction chunks.

### Bài 3 — Commit theo chunk

Job có 20 chunk, mỗi chunk 500 row, mỗi chunk một transaction. Chunk 7 lỗi và rollback.

**Câu hỏi:** trạng thái của các chunk 1–6 ra sao? Có thể công bố toàn job thành công không?

**Định hướng:** Các chunk đã commit trước đó không bị rollback bởi chunk 7. Job có kết quả một phần; cần checkpoint, báo cáo lỗi và quy tắc resume/retry. Không thể báo thành công toàn bộ nếu yêu cầu là xử lý đủ 20 chunk.

### Bài 4 — Spring self-invocation

~~~java
public void importAll(...) {
    this.writeChunk(...);
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeChunk(...) { ... }
~~~

**Câu hỏi:** vì sao có thể không mở transaction mới như mong đợi?

**Định hướng:** Trong Spring proxy-based transaction management, lời gọi trực tiếp trên `this` không đi qua proxy. Dùng writer bean khác hoặc `TransactionTemplate`.

### Bài 5 — Reader và writer dùng context khác

Reader query entity `Product` trong transaction A rồi đóng context. Writer nhận lại objects, gọi `changePrice` nhưng không gọi `merge`/`find` và commit transaction B.

**Câu hỏi:** vì sao DB không tự cập nhật?

**Định hướng:** Những objects từ A đã detached. Dirty checking của context B không theo dõi chúng. Truyền ID/DTO cho writer, lấy managed instances trong B và sửa, hoặc dùng merge có chủ đích.

### Bài 6 — Pagination trên tập đang thay đổi

Job lấy `WHERE status = 'PENDING' ORDER BY id OFFSET :offset LIMIT 100`, xử lý page và đổi status thành `DONE`, rồi tăng offset lên 100.

**Câu hỏi:** có thể bỏ sót row không?

**Định hướng:** Có. Những row đã xử lý không còn thỏa điều kiện, tập kết quả co lại; tăng OFFSET có thể nhảy qua 100 row tiếp theo. Keyset theo ID ổn định hoặc cơ chế claim công việc thường dễ thiết kế hơn, nhưng vẫn phải xác định concurrency/snapshot semantics.

### Bài 7 — Bulk JPQL update và managed state

Trong cùng context, ứng dụng đã nạp `Product #42` với price 100. Một bulk JPQL update đổi giá DB thành 120. Sau đó gọi `em.find(Product.class, 42L)`.

**Câu hỏi:** có chắc nhận được giá 120 không?

**Định hướng:** Không. `find` có thể trả managed instance đang nằm trong identity map với dữ liệu cũ. Cần context mới hoặc refresh/clear có chủ đích, chú ý các thay đổi chưa flush.

### Bài 8 — Retry khi không rõ kết quả commit

Worker gửi commit rồi mất kết nối; ứng dụng không nhận được xác nhận. Lần chạy tiếp theo quyết định insert lại cùng dữ liệu.

**Câu hỏi:** vì sao cách này không an toàn?

**Định hướng:** DB có thể đã commit. Cần idempotency key/business key, checkpoint và reconciliation. Mất phản hồi commit không phải bằng chứng transaction chưa thành công.

### Bài 9 — Chọn StatelessSession

Một job cần nạp 300.000 record độc lập, không có cascade, nhưng có lifecycle callback cập nhật audit log cho từng entity.

**Câu hỏi:** có nên chuyển ngay sang `StatelessSession` mà không đổi code?

**Định hướng:** Không. StatelessSession không có cùng lifecycle/callback semantics với stateful Session. Phải đánh giá audit requirement và có cơ chế ghi audit rõ ràng nếu chọn API thấp hơn.

### Bài 10 — Transaction theo nghiệp vụ

Một phiếu nhập hàng có header và 40 lines. Chunk size là 25 row.

**Câu hỏi:** có nên để 25 dòng đầu commit trước, rồi 15 dòng sau cùng header commit ở transaction khác?

**Định hướng:** Chỉ khi business model hỗ trợ trạng thái trung gian và xử lý partial success. Nếu receipt phải nguyên vẹn, transaction boundary nên bao phủ toàn receipt hoặc cần staging/publish protocol.

### Bài 11 — Nhiều workers và SELECT PENDING

Hai workers đồng thời SELECT cùng một hàng `PENDING` và cùng xử lý.

**Câu hỏi:** thêm `em.clear()` mỗi 100 row có ngăn duplicate execution không?

**Định hướng:** Không. Clear chỉ quản lý first-level cache. Cần claim, locking, optimistic versioning, partitioning hoặc idempotent consumer theo thiết kế concurrency.

### Bài 12 — EntityManagerFactory và EntityManager

Job tạo mới EntityManagerFactory mỗi chunk vì muốn “mỗi chunk có context mới”.

**Câu hỏi:** có phải cách đúng?

**Định hướng:** Không. Factory là đối tượng bootstrap đắt và thường dùng chung cho application/persistence unit. Tạo EntityManager mới cho từng context/chunk, không tái tạo factory liên tục.

## 20. Ghi nhớ

Khi thiết kế xử lý theo lô với Hibernate, hãy trả lời riêng ba câu hỏi:

1. **Persistence context giữ bao nhiêu managed entities và tồn tại đến khi nào?**
2. **Database transaction bao phủ đơn vị công việc nào và commit ở đâu?**
3. **Sau lỗi, crash hoặc chạy lại, hệ thống xác định và bảo vệ kết quả đã commit thế nào?**

Các kết luận then chốt:

- `flush()` gửi SQL pending nhưng **không commit**; `clear()` detach entities nhưng **không rollback**.
- Một transaction duy nhất với flush/clear có thể giảm memory trong khi vẫn giữ atomicity toàn batch, đồng nghĩa vẫn phải rollback toàn bộ nếu cuối batch lỗi.
- Nhiều transaction theo chunk cho phép partial success và thường giới hạn context tốt hơn, nhưng bắt buộc có chiến lược checkpoint, retry và idempotency.
- `hibernate.jdbc.batch_size` là tối ưu JDBC SQL batching, **không phải transaction chunk size** và không tự giới hạn persistence context.
- Trong Spring, transaction proxy và propagation phải được áp dụng đúng. Self-invocation có thể khiến `@Transactional` không được kích hoạt; outer transaction và `REQUIRES_NEW` có ngữ nghĩa commit khác nhau.
- Với đọc dữ liệu lớn, tránh giữ toàn bộ managed entities. Keyset pagination, DTO projections, reader có kiểm soát và context riêng theo chunk thường phù hợp hơn `findAll` toàn bảng.
- Bulk JPQL/SQL không đồng bộ tự động những managed entities cũ trong first-level cache; phải quản lý stale state rõ ràng.
- `StatelessSession` có thể giảm chi phí stateful persistence, nhưng không thay thế các hành vi dirty checking/cascade/callback của EntityManager.
- Khi lỗi SQL/transaction xảy ra, rollback và bỏ context lỗi thay vì cố tiếp tục ghi vào nó.
- **Transaction boundary phải phù hợp bất biến nghiệp vụ**; không vì con số chunk size thuận tiện mà làm một aggregate bị commit dở dang.

Đối với công việc thực tế, ranh giới tốt thường là: **đọc một phần dữ liệu đầu vào có thể xác định lại, xử lý ngoài transaction nếu an toàn, mở transaction/context ngắn để ghi một đơn vị nhất quán, commit cùng checkpoint, rồi đóng context và chuyển sang phần tiếp theo**. Mức tối ưu còn phải phụ thuộc database, driver, Hibernate version, kích thước dữ liệu và yêu cầu phục hồi khi lỗi.

### Tài liệu chính thức

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — persistence context, EntityManager, flush, transaction và lifecycle.
- [Hibernate ORM Documentation](https://docs.hibernate.org/orm/) — user guide theo phiên bản: batching, flushing, persistence context, StatelessSession.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — phần batch processing, fetching và bulk mutation.
- [Spring Framework Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html) — `@Transactional`, propagation, proxy và `TransactionTemplate`.
- [Spring Batch Reference](https://docs.spring.io/spring-batch/reference/) — chunk-oriented processing, checkpoint, restart và fault tolerance.
- [PostgreSQL Documentation](https://www.postgresql.org/docs/current/) — transaction isolation, constraints, locking và SQL phù hợp database mục tiêu.

> Các ví dụ trong bài diễn tả nguyên tắc thiết kế và API phổ biến. Khi triển khai, dùng tài liệu khớp với version Jakarta Persistence, Hibernate, Spring, JDBC driver và dialect thực tế; lựa chọn chunk/concurrency/timeout phải dựa trên ranh giới nhất quán dữ liệu và khả năng vận hành của hệ thống.





