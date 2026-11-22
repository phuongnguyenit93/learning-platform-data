# Xử lý nhiều entity theo khối với flush và clear

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** Hiệu năng

Một tác vụ nhập 500.000 bản ghi, tính lại giá cho 200.000 sản phẩm hoặc chuẩn hóa dữ liệu khách hàng có thể chạy rất chậm dù mỗi lệnh ghi đơn lẻ rất đơn giản. Khi sử dụng JPA, một nguyên nhân thường gặp là **persistence context** giữ quá nhiều entity ở trạng thái managed: provider cần theo dõi danh tính object, dirty checking, cascade và trạng thái liên quan để thực hiện các thao tác ghi đúng. Nếu nạp và lưu hàng trăm nghìn entity liên tục trong cùng một EntityManager mà không quản lý vòng đời của chúng, mức dùng bộ nhớ, thời gian flush và áp lực database có thể tăng đáng kể.

Hai thao tác quan trọng là:

~~~java
entityManager.flush();
entityManager.clear();
~~~

Nhưng đây **không phải một cặp lệnh tăng tốc thần kỳ**. Cần hiểu chính xác:

- **flush()** đồng bộ những thay đổi đang chờ của persistence context xuống database theo transaction hiện tại; **không phải COMMIT**.
- **clear()** tách (detach) **tất cả managed entities** khỏi persistence context; nó **không ghi** những thay đổi chưa flush thay cho bạn.
- **flush trước clear** là thứ tự thường dùng khi xử lý từng khối để không bỏ mất thay đổi đang chờ.
- **flush/clear theo khối** kiểm soát kích thước persistence context, nhưng số lần transaction COMMIT và cấu hình JDBC batching là những vấn đề riêng.
- **flush/clear không xóa dữ liệu trong database, không giải quyết N+1 query, không tự động bật JDBC batching và không bảo đảm lỗi một khối chỉ ảnh hưởng một phần transaction**.

Bài học này đi từ ví dụ nhỏ tới quy trình nhập và cập nhật hàng loạt an toàn, phân tích các lớp bộ nhớ, transaction, JDBC batch, hiệu năng, khóa, lỗi, test và chiến lược thay thế khi khối lượng thực tế rất lớn.

## 1. Vì sao xử lý nhiều entity cần chiến lược riêng?

### 1.1. Một vòng lặp đơn giản có thể tạo persistence context rất lớn

Ví dụ:

~~~java
EntityTransaction tx = em.getTransaction();
tx.begin();

for (ProductInput input : inputs) {
    Product product = new Product(
        input.sku(),
        input.price()
    );
    em.persist(product);
}

tx.commit();
~~~

Với vài chục entity, code trên thường ổn. Với 500.000 entity, nó có thể gặp vấn đề:

1. Mỗi Product vừa persist trở thành **managed**.
2. EntityManager phải giữ thông tin để nhận diện các entity được quản lý.
3. Provider có thể giữ snapshot, dirty-check state, pending actions và cascade information.
4. Tới flush, lượng công việc tích lũy rất lớn.
5. Java heap/GC có thể chịu áp lực cao, hoặc xảy ra OutOfMemoryError.
6. Một transaction quá dài gây áp lực lên locks, transaction log, MVCC/vacuum và tài nguyên connection.
7. Nếu có một lỗi ở cuối transaction, toàn bộ công việc có thể phải rollback.

Dù provider có các tối ưu nội bộ, không nên xây một chương trình dựa trên giả định EntityManager sẽ tự tách mọi object khi số lượng tăng cao.

### 1.2. First-level cache là persistence context

Một EntityManager dùng **persistence context** như identity map. Ví dụ:

~~~java
Product first = em.find(Product.class, 42L);
Product second = em.find(Product.class, 42L);

System.out.println(first == second); // true
~~~

Với cùng entity identity, trong một persistence context, JPA trả cùng managed instance. Điều này hữu ích cho tính nhất quán object graph, nhưng cũng khiến mỗi entity đã nạp có thể tiếp tục được giữ trong context suốt unit of work.

**Tắt second-level cache không loại bỏ persistence context/first-level cache.** Cặp flush/clear trong bài tác động trực tiếp đến managed state của persistence context, không phải một cache backend Redis.

### 1.3. Một luồng xử lý theo khối

~~~text
Danh sách đầu vào: 100.000 ProductInput
                      |
                      v
              Nhận khối 1..500
                      |
                      v
              persist / update
                      |
                      v
                 em.flush()
                      |
                      v
                 em.clear()
                      |
                      v
              Nhận khối 501..1000
                      |
                      v
              persist / update
                      |
                      v
                 em.flush()
                      |
                      v
                 em.clear()
                      |
                     ...
                      |
                      v
                COMMIT theo policy
~~~

Khối **500** chỉ là ví dụ. Kích thước tối ưu tùy entity graph, JDBC driver, database, số cột, SQL strategy, heap, transaction duration, indexes, triggers và độ trễ mạng.

### 1.4. Phân biệt ba đơn vị quan trọng

| Khái niệm | Ví dụ | Điều nó kiểm soát |
|---|---|---|
| Persistence-context chunk | Flush/clear sau 500 entities | Số managed entities tồn tại giữa các lần clear |
| JDBC batch | Gom tối đa 50 INSERT/UPDATE statements vào một driver batch | Số statement/round-trip theo khả năng provider/driver |
| Database transaction | Commit sau 5.000 rows hoặc cả file | Ranh giới atomicity, rollback, lock và transaction log |

Ba con số này **có thể khác nhau**. Không được đồng nhất batchSize của JDBC với chunkSize của flush/clear hoặc transaction size.

## 2. Mô hình ví dụ dùng xuyên suốt bài

Ta dùng Product đơn giản, tránh quan hệ phức tạp cho ví dụ đầu tiên.

### 2.1. Entity Product

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(
    name = "products",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_products_sku",
        columnNames = "sku"
    )
)
public class Product {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "product_seq_gen"
    )
    @SequenceGenerator(
        name = "product_seq_gen",
        sequenceName = "product_seq",
        allocationSize = 50
    )
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, length = 64)
    private String sku;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    protected Product() {}

    public Product(String sku, BigDecimal price) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU bắt buộc");
        }
        this.sku = sku;
        changePrice(price);
        this.active = true;
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public String getSku() { return sku; }
    public BigDecimal getPrice() { return price; }
    public boolean isActive() { return active; }

    public void changePrice(BigDecimal newPrice) {
        Objects.requireNonNull(newPrice, "price");
        if (newPrice.signum() < 0) {
            throw new IllegalArgumentException("Giá không được âm");
        }
        this.price = newPrice;
    }

    public void deactivate() {
        this.active = false;
    }
}
~~~

Ví dụ dùng **Jakarta Persistence**. Với dự án dùng javax.persistence cũ, cần thay namespace nhất quán. Chiến lược SEQUENCE được chọn để minh họa batching có thể hiệu quả, không phải yêu cầu mọi entity phải đổi từ IDENTITY sang SEQUENCE.

### 2.2. DTO đầu vào

~~~java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductInput(
    String sku,
    BigDecimal price
) {}
~~~

Một batch import nên đọc/parse/validate đầu vào theo chính sách trước hoặc trong mỗi chunk, không giữ hàng triệu đối tượng DTO nếu có thể stream file đầu vào.

### 2.3. Schema PostgreSQL minh họa

~~~sql
CREATE SEQUENCE product_seq
    START WITH 1
    INCREMENT BY 50;

CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    sku VARCHAR(64) NOT NULL,
    price NUMERIC(19,2) NOT NULL,
    active BOOLEAN NOT NULL,
    CONSTRAINT uk_products_sku UNIQUE (sku),
    CONSTRAINT ck_products_price_nonnegative
        CHECK (price >= 0)
);
~~~

Schema chỉ là ví dụ: **sequence increment, allocationSize và provider optimizer phải được cấu hình tương thích**. Không mặc định mọi phiên bản Hibernate hoặc mọi strategy của SequenceGenerator có cùng yêu cầu DDL. Migrations cần được kiểm thử với provider thực tế.

**Không chỉ dựa vào validation của entity**: SQL writer ngoài JPA có thể bỏ qua Java methods. Các database constraints bảo vệ dữ liệu ở mọi đường ghi.

## 3. Các trạng thái entity quyết định tác dụng flush/clear

JPA sử dụng các trạng thái quan trọng:

- **New/transient:** object mới, chưa được persistence context quản lý.
- **Managed:** entity hiện được EntityManager theo dõi.
- **Detached:** entity từng managed nhưng đã ra khỏi context; thay đổi của object không được tự dirty-check.
- **Removed:** entity managed đã được yêu cầu xóa, SQL DELETE có thể chưa thực hiện.

### 3.1. persist đưa object vào managed state

~~~java
Product product = new Product(
    "KB-001",
    new BigDecimal("120000.00")
);

System.out.println(em.contains(product)); // false

em.persist(product);

System.out.println(em.contains(product)); // true
~~~

EntityManager theo dõi Product cho đến khi bị detach/clear/close hoặc kết thúc vòng đời context phù hợp.

### 3.2. clear làm entity trở thành detached

~~~java
em.persist(product);
em.flush();
em.clear();

System.out.println(em.contains(product)); // false
~~~

**Java object vẫn tồn tại trong RAM nếu biến product hoặc collection bên ngoài còn tham chiếu nó.** Clear chỉ bỏ entity khỏi persistence context; nó không chạy System.gc(), không xóa Java object và không bảo đảm heap lập tức giảm nếu code còn giữ danh sách các objects.

### 3.3. Thay đổi detached entity không được tự lưu

~~~java
Product p = em.find(Product.class, 42L);
em.clear();

p.changePrice(new BigDecimal("150000.00"));

// p đã detached.
// Không tự sinh UPDATE chỉ vì commit transaction.
~~~

Nếu muốn cập nhật lại cần nạp managed entity mới hoặc dùng merge với hiểu biết đầy đủ về merge semantics. Không gọi persist trên một detached entity hiện hữu như thể đó là object mới.

### 3.4. clear ảnh hưởng tất cả managed entities trong context

~~~java
Customer customer = em.find(Customer.class, customerId);
Product product = em.find(Product.class, productId);

em.clear();

// Cả customer và product đều không còn managed.
~~~

Đây là lý do **không nhét em.clear() vào một helper dùng chung mà caller không biết**. Một service giao dịch lớn có thể đang sửa các managed Customer/Order khác; clear sẽ detach chúng và có thể làm mất những thay đổi chưa flush.

### 3.5. clear khác detach

| Thao tác | Phạm vi | Tình huống |
|---|---|---|
| em.detach(product) | Một entity và cascade DETACH theo mapping | Muốn bỏ một entity cụ thể |
| em.clear() | Toàn bộ persistence context | Muốn giải phóng managed state sau một chunk |
| em.close() | Đóng EntityManager ứng dụng tự quản lý | Kết thúc unit of work |
| Context/transaction mới | Một lifecycle riêng | Bắt đầu đơn vị xử lý kế tiếp |

Với batch import chuyên biệt, em.clear() thường hợp lý vì context chỉ dành cho batch. Trong một transaction service hỗn hợp, detach hoặc context riêng có thể an toàn hơn.

## 4. flush() thực hiện chính xác điều gì?

### 4.1. Đồng bộ thay đổi tới database

~~~java
Product p = em.find(Product.class, 42L);
p.changePrice(new BigDecimal("130000.00"));

em.flush();
~~~

Provider đồng bộ pending changes cần thiết theo JPA semantics, có thể phát SQL UPDATE. Nếu câu UPDATE thành công, thay đổi **vẫn nằm trong transaction chưa commit**.

~~~text
Managed Product.price = 130000
             |
             v
          em.flush()
             |
             v
   SQL UPDATE trong transaction
             |
             +-- COMMIT → có hiệu lực bền vững
             |
             +-- ROLLBACK → DB trả về trạng thái trước tx
~~~

### 4.2. Flush không phải commit

~~~java
tx.begin();
em.persist(new Product("MS-001", BigDecimal.TEN));
em.flush();
tx.rollback();
~~~

Nếu transaction rollback thành công, INSERT vừa flush không trở thành dữ liệu đã commit. **Flush không chia transaction thành những phần đã lưu vĩnh viễn.**

### 4.3. Flush có thể kích hoạt kiểm tra lỗi

Tại flush, JPA/provider có thể:
- Kiểm tra Jakarta Bean Validation callbacks nếu tích hợp;
- Chạy dirty checking;
- Phát INSERT/UPDATE/DELETE;
- Gặp database NOT NULL, UNIQUE, CHECK, FK constraints;
- Phát hiện optimistic locking conflicts;
- Gặp deadlock/lock timeout;
- Gửi JDBC batch và nhận BatchUpdateException.

Vì vậy flush theo chunk còn giúp **phát hiện lỗi sớm hơn** trong tiến trình, nhưng không bảo đảm lỗi nào cũng hiện đúng tại flush: deferred DB constraints hoặc commit failures có thể xuất hiện muộn.

### 4.4. Flush mode và thời điểm auto-flush

Một số flush modes phổ biến trong JPA:

~~~java
em.setFlushMode(FlushModeType.AUTO);
em.setFlushMode(FlushModeType.COMMIT);
~~~

- **AUTO:** provider xử lý flush để query/transaction quan sát dữ liệu theo semantics tương ứng.
- **COMMIT:** provider trì hoãn flush theo policy; tác động của pending changes tới query trước commit không phải điều có thể suy luận như AUTO.

Không coi flush mode COMMIT là một cách loại bỏ nhu cầu explicit flush trước clear. Trong bài này, **em.flush() được gọi chủ động** để tạo ranh giới đồng bộ theo chunk.

### 4.5. Query có thể tự kích hoạt flush

Trong AUTO mode, một JPQL query bên trong vòng import có thể khiến provider flush trước để kết quả query nhất quán. Nếu cứ 100 rows lại gọi existsBySku qua query, có thể vô tình tạo thêm flush/round-trip và phá hiệu quả batching.

Nên tránh query kiểm tra từng row khi có thể chuyển sang:
- Pre-validation theo chunk;
- Fetch theo tập SKU;
- Database UNIQUE constraint để chống race;
- Query/deduplication theo batch;
- Bulk operations phù hợp.

## 5. clear() thực hiện chính xác điều gì?

### 5.1. Clear không gửi SQL thay bạn

~~~java
tx.begin();

Product product = new Product(
    "HD-001", new BigDecimal("400000.00")
);

em.persist(product);
em.clear();

tx.commit();
~~~

Những thay đổi **chưa được flush** có thể không được đồng bộ xuống DB do entity đã detached và pending state đã bị bỏ khỏi context. Không dùng đoạn trên như một mẫu nhập dữ liệu an toàn.

### 5.2. Thứ tự thực hành thường dùng

~~~java
em.persist(product);

// Sau khi đủ số rows trong chunk:
em.flush(); // Đẩy pending SQL xuống database.
em.clear(); // Detach managed objects khỏi context.
~~~

**Flush trước clear** giúp các pending operations được đồng bộ trước khi bỏ managed state. Tuy vậy nếu flush ném exception, **không tiếp tục clear rồi chạy tiếp transaction lỗi** như thể không có gì xảy ra. Phải rollback hoặc để transaction manager xử lý lỗi.

### 5.3. Không phải mọi object mất reference sau clear

~~~java
List<Product> all = new ArrayList<>();

for (ProductInput input : inputs) {
    Product p = new Product(input.sku(), input.price());
    em.persist(p);
    all.add(p);  // Giữ references lâu dài.
    // flush/clear theo chunk ở đây...
}
~~~

Dù clear, list **all** vẫn giữ toàn bộ Product objects. Nếu mục tiêu là tiết kiệm heap, không tích lũy entity references trong một collection không giới hạn. Nên giữ **ID/summary/metrics** tối thiểu hoặc stream input.

### 5.4. Lazy relations trên detached objects

Nếu sau clear, code gọi một lazy association chưa tải:

~~~java
em.clear();

product.getCategory().getName();
~~~

có thể gặp lỗi lazy-loading khi provider không còn context thích hợp. Mặc dù lỗi cụ thể phụ thuộc provider, nguyên tắc là **đừng dùng detached entity graph như thể nó vẫn managed**. Tính toán DTO cần thiết trước clear hoặc nạp lại theo query phù hợp.

### 5.5. Clear không làm mất transaction

~~~java
tx.begin();
em.persist(...);
em.flush();
em.clear();

em.persist(...);
em.flush();
em.clear();

tx.commit();
~~~

Hai lần flush/clear vẫn nằm trong **một transaction** nếu code không commit/begin thêm lần nào. Clear chỉ thay đổi persistence context, không tự commit và không tự rollback.

## 6. Mẫu cơ bản: persist theo khối trong một transaction

Bài toán: import danh sách ProductInput đã được đọc từ file/service. Cần giới hạn số Product objects managed cùng lúc, nhưng nghiệp vụ yêu cầu **toàn bộ import hoặc thành công hoặc rollback**.

### 6.1. Triển khai bằng JPA resource-local transaction

~~~java
package com.example.catalog.imports;

import com.example.catalog.Product;
import com.example.catalog.ProductInput;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public final class ProductImporter {

    private final EntityManagerFactory emf;

    public ProductImporter(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public long importAll(
            Iterable<ProductInput> inputs,
            int chunkSize) {

        if (chunkSize <= 0) {
            throw new IllegalArgumentException(
                "chunkSize phải lớn hơn 0"
            );
        }

        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();
        long processed = 0;

        try {
            tx.begin();

            for (ProductInput input : inputs) {
                Product product = new Product(
                    input.sku(),
                    input.price()
                );

                em.persist(product);
                processed++;

                if (processed % chunkSize == 0) {
                    em.flush();
                    em.clear();
                }
            }

            // Đồng bộ chunk cuối nếu số lượng không chia hết.
            em.flush();
            em.clear();

            tx.commit();
            return processed;
        } catch (RuntimeException failure) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
            }
            throw failure;
        } finally {
            em.close();
        }
    }
}
~~~

**Giới hạn và điều kiện của ví dụ:**

- Sử dụng **resource-local EntityTransaction**. Không dùng em.getTransaction() trong một context do JTA hoặc Spring transaction manager điều khiển.
- Đầu vào là **Iterable**; để thực sự tiết kiệm heap, caller phải cung cấp iterator/streaming source phù hợp, không tự tạo sẵn một List chứa 1 triệu DTO/entity.
- Một transaction duy nhất được giữ từ tx.begin tới tx.commit.
- Gọi flush/clear sau mỗi chunk, nhưng **không commit từng chunk**.
- Nếu chunk cuối rỗng hoặc đã flush ở đúng bội số chunkSize, lời gọi flush cuối có thể không còn pending inserts; ví dụ ưu tiên đơn giản dễ hiểu.
- Nếu một lần flush thất bại, **rollback toàn transaction**; không tiếp tục sang row tiếp theo.
- Input stream/iterator có tài nguyên file/socket cần được caller đóng theo lifecycle riêng.

### 6.2. Vì sao kiểm tra chunkSize trước khi modulo?

~~~java
if (processed % chunkSize == 0) {
    em.flush();
    em.clear();
}
~~~

Nếu chunkSize=0, phép chia modulo phát lỗi. Ngoài ra các số âm không có ý nghĩa trong policy batching. Validation tham số trước khi mở transaction giúp tránh lỗi cấu hình bị hiểu là lỗi DB.

### 6.3. Vì sao không giữ tất cả Products vào một List?

Mục tiêu của clear là làm giảm kích thước first-level cache. Nếu code:

~~~java
List<Product> saved = new ArrayList<>();

for (ProductInput input : inputs) {
    Product entity = new Product(input.sku(), input.price());
    em.persist(entity);
    saved.add(entity);
    // flush/clear...
}
~~~

thì List vẫn giữ references; Object vẫn chiếm heap, chỉ không còn managed. Với hàng triệu rows, nên trả **count**, **importId** hoặc các summary số lượng thay vì collection chứa toàn bộ entities.

### 6.4. Vì sao không clear trước flush?

Sai:

~~~java
if (processed % chunkSize == 0) {
    em.clear();
    em.flush();
}
~~~

Các entities bị detached trước khi đồng bộ, nên những thay đổi đang chờ có thể không được ghi. **Không xem thứ tự hai lệnh là chi tiết tùy ý.**

### 6.5. Vì sao một transaction lớn vẫn có rủi ro?

Flush/clear giảm số managed entities nhưng transaction vẫn rất dài, dẫn tới:
- Transaction log/WAL/undo tăng;
- Locks được giữ qua các chunk;
- MVCC snapshots cũ, vacuum pressure (tùy DB);
- Connection bị giữ lâu;
- Một lỗi cuối cùng có thể khiến rollback toàn bộ;
- Commit latency và recovery cost cao.

Nếu không bắt buộc all-or-nothing cho cả file, cân nhắc **transaction-per-chunk**.

## 7. Mẫu transaction-per-chunk: commit từng khối

Nếu nghiệp vụ chấp nhận import tiến dần theo từng khối, mỗi chunk có transaction riêng. Khi chunk 5 fail, các chunks 1–4 đã commit **không bị rollback tự động**.

### 7.1. Cấu trúc một transaction cho một chunk

~~~text
Input stream
    |
    +-- Chunk#1 (IDs 1..500)
    |      BEGIN
    |      persist
    |      flush
    |      COMMIT
    |      close EntityManager
    |
    +-- Chunk#2 (IDs 501..1000)
    |      BEGIN
    |      persist
    |      flush
    |      COMMIT
    |      close EntityManager
    |
    +-- Chunk#3 ...
           BEGIN
           ...
           FAILURE → ROLLBACK riêng Chunk#3
~~~

Sự khác biệt với một transaction lớn là **atomicity theo chunk**, không phải theo toàn bộ import.

### 7.2. Hàm lưu một chunk

~~~java
public int persistChunk(
        List<ProductInput> chunk) {

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        for (ProductInput input : chunk) {
            em.persist(
                new Product(input.sku(), input.price())
            );
        }

        em.flush();

        // Vì EntityManager sẽ được đóng, clear không
        // bắt buộc về memory trong ví dụ này.
        tx.commit();
        return chunk.size();

    } catch (RuntimeException failure) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw failure;

    } finally {
        em.close();
    }
}
~~~

Hàm giả định **chunk đã được giới hạn kích thước** ở caller. Sau mỗi lần gọi, EntityManager được đóng nên không cần cố gọi clear chỉ để làm sạch context sắp bị đóng.

### 7.3. Điều phối danh sách đầu vào theo chunk

~~~java
public long importPerChunk(
        Iterator<ProductInput> source,
        int chunkSize) {

    if (chunkSize <= 0) {
        throw new IllegalArgumentException("chunkSize");
    }

    long committed = 0;

    while (source.hasNext()) {
        List<ProductInput> chunk =
            new ArrayList<>(chunkSize);

        while (source.hasNext()
                && chunk.size() < chunkSize) {
            chunk.add(source.next());
        }

        committed += persistChunk(chunk);
    }

    return committed;
}
~~~

Để triển khai cần imports Iterator, List, ArrayList và hàm persistChunk ở trên. Mỗi chunk list chỉ tồn tại trong phạm vi vòng lặp; không nên lưu toàn bộ chunks đã xử lý vào một collection lớn.

**Quan trọng:** Nếu một chunk commit thành công nhưng response bị mất, caller không thể tự suy rằng chunk chưa commit. Với import có thể retry, phải thiết kế **idempotency**, import run ID, offset/checkpoint hoặc unique keys.

### 7.4. Ranh giới lỗi của hai chiến lược

| Tình huống | Một transaction cho toàn file | Transaction-per-chunk |
|---|---|---|
| Lỗi tại row 1.000 | Rollback toàn file | Chunks trước có thể đã commit |
| Atomicity | Toàn file | Mỗi chunk |
| DB transaction duration | Rất dài | Ngắn hơn |
| Rollback cost | Có thể cao | Nhỏ hơn |
| Resume/retry | Chạy lại toàn file sau rollback | Chạy lại chunk lỗi nếu idempotent |
| Hiệu năng | Có thể ít commits nhưng log/locks lớn | Nhiều commits nhưng giữ tài nguyên ngắn |
| Business consistency | Hợp với all-or-nothing | Hợp với imports tiến dần |

### 7.5. Chọn theo nghiệp vụ, không chỉ theo thời gian chạy

Nếu batch là một lệnh chuyển sổ kế toán không thể để nửa file thành công, transaction-per-chunk có thể sai về nghiệp vụ. Nếu batch là đồng bộ catalog có thể resume, transaction-per-chunk thường hợp lý hơn.

Không tự chọn commit-per-chunk chỉ vì nhanh hơn trong benchmark nếu partial success phá bất biến hệ thống.

## 8. Spring @Transactional: một transaction, nhiều lần flush/clear

Trong Spring, một method @Transactional thường có một persistence context được bind vào transaction. Có thể inject EntityManager rồi flush/clear theo chunk.

~~~java
package com.example.catalog.imports;

import com.example.catalog.Product;
import com.example.catalog.ProductInput;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SpringProductImporter {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public long importAll(
            Iterable<ProductInput> inputs,
            int chunkSize) {

        if (chunkSize <= 0) {
            throw new IllegalArgumentException("chunkSize");
        }

        long count = 0;

        for (ProductInput input : inputs) {
            em.persist(
                new Product(input.sku(), input.price())
            );
            count++;

            if (count % chunkSize == 0) {
                em.flush();
                em.clear();
            }
        }

        em.flush();
        em.clear();
        return count;
    }
}
~~~

**Điều quan trọng:** @Transactional không commit sau mỗi em.flush(). Transaction được quản lý bởi Spring ở boundary bên ngoài method. Nếu một row fail trong toàn method, toàn transaction có thể rollback theo rollback rules.

### 8.1. @PersistenceContext dùng proxy/context do container quản lý

Không dùng:

~~~java
em.close();
~~~

trên EntityManager do Spring/container quản lý qua @PersistenceContext một cách tùy tiện. Framework chịu trách nhiệm lifecycle, và close có thể không hợp lệ với proxy/shared EntityManager.

### 8.2. Self-invocation và @Transactional

Sai về mặt kỳ vọng proxy:

~~~java
@Service
class ImportService {
    public void start() {
        importChunk(...); // Gọi cùng object.
    }

    @Transactional
    public void importChunk(...) {
        // ...
    }
}
~~~

Khi Spring dùng proxy-based transaction management, self-invocation có thể không đi qua proxy nên annotation @Transactional của importChunk **không có hiệu lực như kỳ vọng**. Đặt chunk handler trong bean khác được gọi qua proxy hoặc dùng TransactionTemplate.

### 8.3. Đừng vô tình tham gia transaction caller

Một method @Transactional với propagation REQUIRED có thể tham gia transaction đã mở của caller. Nếu caller đang giữ managed Customer/Order entities, **em.clear() trong importer có thể detach những entities đó**.

Vì vậy một batch importer cần:
- Boundary transaction rõ;
- Không chia sẻ context với unrelated business work;
- API quy định caller không mở transaction bọc ngoài khi importer tự quản lý chunk;
- Hoặc dùng transaction propagation/EntityManager policy phù hợp.

### 8.4. Không bắt và nuốt PersistenceException

~~~java
@Transactional
public void importAll(...) {
    try {
        // persist/flush/clear
    } catch (PersistenceException ex) {
        // Sai nếu log rồi tiếp tục.
    }
}
~~~

Khi flush thất bại, transaction có thể rollback-only hoặc DB transaction đã aborted. Trả kết quả success sẽ gây sai trạng thái nghiệp vụ. Hãy propagate lỗi hoặc thiết kế retry từ transaction mới.

## 9. Spring transaction-per-chunk với bean tách riêng

Một chiến lược dễ đọc: coordinator không có @Transactional, còn chunk writer có @Transactional. Mỗi lần gọi qua Spring proxy là một transaction riêng.

### 9.1. ChunkWriter

~~~java
@Service
public class ProductChunkWriter {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public int write(List<ProductInput> inputs) {
        for (ProductInput input : inputs) {
            em.persist(
                new Product(input.sku(), input.price())
            );
        }

        em.flush();

        // Không cần clear nếu context đóng tại
        // cuối transaction theo lifecycle thông thường.
        // Có thể clear nếu context kéo dài đặc biệt.
        return inputs.size();
    }
}
~~~

Ở Spring transaction-scoped context thông dụng, khi transaction kết thúc, context không tiếp tục giữ entities như một import transaction dài. Không mặc định điều này nếu sử dụng extended persistence context hoặc cấu hình custom.

### 9.2. Coordinator

~~~java
@Service
public class ProductImportCoordinator {

    private final ProductChunkWriter writer;

    public ProductImportCoordinator(ProductChunkWriter writer) {
        this.writer = writer;
    }

    public long importChunks(
            Iterator<ProductInput> source,
            int chunkSize) {

        if (chunkSize <= 0) {
            throw new IllegalArgumentException("chunkSize");
        }

        long committed = 0;

        while (source.hasNext()) {
            List<ProductInput> chunk = new ArrayList<>();

            while (source.hasNext()
                    && chunk.size() < chunkSize) {
                chunk.add(source.next());
            }

            // Gọi qua bean khác/proxy.
            committed += writer.write(chunk);
        }

        return committed;
    }
}
~~~

Nếu writer.write ném exception, **những chunks trước đó có thể đã commit**. Coordinator cần lưu checkpoint hoặc trả kết quả lỗi chứa phần đã thành công theo business contract; không giả định transaction tự rollback mọi chunks trước.

### 9.3. TransactionTemplate là lựa chọn khác

~~~java
public void persistChunkWithTemplate(
        List<ProductInput> chunk) {

    transactionTemplate.executeWithoutResult(status -> {
        for (ProductInput input : chunk) {
            em.persist(
                new Product(input.sku(), input.price())
            );
        }
        em.flush();
    });
}
~~~

Trong Spring, transactionTemplate cần được cấu hình với transaction manager đúng; em là EntityManager được quản lý theo transaction. Ví dụ này giúp thấy commit xảy ra **sau callback**, do TransactionTemplate điều khiển. Nếu dùng TransactionTemplate từ coordinator, đảm bảo không có transaction ngoài đang khiến template tham gia transaction lớn ngoài ý muốn.

### 9.4. @Transactional(propagation=REQUIRES_NEW) không phải phép màu

REQUIRES_NEW có thể dùng khi có outer transaction phải tạm đình chỉ để mở chunk transaction độc lập, nhưng thường cần thêm connection, tăng áp lực pool và có thể phá atomicity. Không tự áp nó cho mọi chunk nếu có thể tổ chức coordinator ngoài transaction và writer với REQUIRED.

### 9.5. Chunk writer phải xác định khi nào báo thành công

Một method writer.write trả trước khi Spring proxy commit xong, nhưng **caller qua proxy** sẽ nhận kết quả chỉ sau khi invocation interceptor xử lý transaction commit (nếu commit thành công). Nếu gọi trực tiếp qua self-invocation, semantics khác. Đặt thống kê “committed rows” tại coordinator **sau khi proxy call trả thành công** và xác minh thực tế theo transaction manager.

## 10. Cập nhật nhiều entities hiện hữu theo khối

Insert entities mới khá thẳng. Update khó hơn vì phải **nạp entities**, sửa state, dirty checking và tránh giữ cả kết quả query trong memory.

### 10.1. Cách làm dễ gây nổ heap

~~~java
List<Product> all = em.createQuery(
    "select p from Product p",
    Product.class
).getResultList();

for (Product p : all) {
    p.changePrice(calculatePrice(p));
}

em.flush();
~~~

Nếu bảng có hàng triệu Products, List giữ toàn bộ Java objects và persistence context cũng có thể giữ các managed instances. Dù có clear ở cuối, heap đã chịu áp lực trước đó.

### 10.2. Đọc ID theo trang, load từng tập

Một chiến lược:
1. Đọc trang **IDs hoặc projections** chứ không nạp toàn entity graph;
2. Nạp đúng các Products của trang;
3. Áp business transformation;
4. flush và clear;
5. Sang trang tiếp theo.

Ví dụ:

~~~java
public int updateIds(
        EntityManager em,
        List<Long> productIds,
        UnaryOperator<BigDecimal> priceRule) {

    int count = 0;

    for (Long id : productIds) {
        Product p = em.find(Product.class, id);
        if (p == null) {
            continue; // Hoặc xử lý theo contract.
        }

        p.changePrice(
            priceRule.apply(p.getPrice())
        );

        count++;
    }

    em.flush();
    em.clear();
    return count;
}
~~~

Imports: java.util.List, java.util.function.UnaryOperator, java.math.BigDecimal và entity Product. Hàm giả định **productIds là một chunk giới hạn** và em đang nằm trong transaction thích hợp.

### 10.3. Đọc IDs theo keyset pagination

~~~java
List<Long> nextIds = em.createQuery(
    """
    select p.id
    from Product p
    where p.id > :lastId
    order by p.id
    """,
    Long.class
)
.setParameter("lastId", lastId)
.setMaxResults(chunkSize)
.getResultList();
~~~

Sau mỗi batch, cập nhật lastId bằng **ID lớn nhất đã duyệt**, không phải ID lớn nhất đã update thành công, nếu mục tiêu là quét tập một lần. Nếu bảng được ghi đồng thời, cần xác định snapshot/window/upperBound để tránh bỏ hoặc thêm rows ngoài phạm vi mong muốn.

### 10.4. Vì sao OFFSET pagination có thể sai khi predicate thay đổi?

Giả sử query chọn active=true:

~~~sql
SELECT id
FROM products
WHERE active = true
ORDER BY id
OFFSET 1000
LIMIT 500;
~~~

Nếu chunk trước đã **deactivate 500 Products**, tập rows phù hợp điều kiện active=true đã thu hẹp. OFFSET kế tiếp có thể bỏ qua rows chưa xử lý, dù database không bị lỗi.

**Keyset pagination bằng khóa ổn định** thường tránh vấn đề này tốt hơn khi quét và sửa chính tập dữ liệu đang query.

### 10.5. Keyset cần thứ tự ổn định và policy với concurrent writers

Điều kiện **id > lastId** chỉ quét theo ID; nó không tự tạo snapshot nhất quán. Concurrent INSERT với ID mới hoặc DELETE/UPDATE của process khác có thể làm tập dữ liệu thay đổi.

Nếu nghiệp vụ cần xử lý chính xác tập tại thời điểm bắt đầu, có thể:
- Chốt upperBound ID;
- Chốt danh sách IDs vào staging table;
- Dùng snapshot transaction phù hợp (cân nhắc chi phí);
- Gắn batch_run_id/claim state;
- Thiết kế idempotent processing.

### 10.6. Tránh vòng lặp query toàn bộ entity và clear giữa ResultList

Nếu resultList đã chứa 10.000 managed entities, clear giữa vòng lặp detach tất cả những objects còn trong List. Tiếp tục sửa chúng sau clear sẽ không được dirty-check.

Đây là lỗi logic thường gặp:

~~~java
List<Product> products = query.getResultList();

for (int i = 0; i < products.size(); i++) {
    Product p = products.get(i);
    p.changePrice(...);

    if ((i + 1) % 500 == 0) {
        em.flush();
        em.clear();
        // Các Product chưa tới lượt trong List
        // cũng đã detached!
    }
}
~~~

Phải load **mỗi trang riêng** hoặc quản lý flush/clear sao cho không làm detached các entities sẽ còn cần cập nhật.

## 11. JDBC batching và flush/clear không phải cùng một chức năng

Một nhầm lẫn quan trọng: **Cứ gọi em.flush() mỗi 100 entities nghĩa là database nhận đúng một JDBC batch 100 statements.** Điều này **không được bảo đảm**.

### 11.1. Hai cơ chế khác nhau

**JPA flush/clear** quản lý vòng đời state và thời điểm provider đồng bộ DML:

~~~text
500 managed Product instances
             |
          em.flush()
             |
   Provider tạo SQL actions
             |
   JDBC statements / batches
             |
          Database
             |
          em.clear()
             |
   Context bỏ managed state
~~~

**JDBC batching** là cơ chế driver/provider gom nhiều statements tương thích để giảm overhead. Việc gom còn phụ thuộc:
- Hibernate/JPA provider và cấu hình;
- JDBC driver và dialect;
- Identity generation;
- Thứ tự statement;
- Entity types/column SQL shapes;
- Giới hạn bind parameters;
- Batch insert/update strategy;
- Driver/server protocol.

Dù flush theo 500, provider có thể gửi nhiều batches 50 statements, vài statements riêng, hoặc không batch được.

### 11.2. Cấu hình Hibernate JDBC batch size

Một cấu hình Hibernate thường gặp:

~~~properties
hibernate.jdbc.batch_size=50
~~~

Với Spring Boot:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
~~~

Đây là **Hibernate provider property**, không phải API Jakarta Persistence portable. Nó thường cho phép Hibernate sử dụng JDBC batching phù hợp khi gửi DML.

**Không suy ra** chỉ set property là chắc chắn JDBC driver thực hiện batching. Hãy quan sát Hibernate statistics, JDBC proxy/batch metrics hoặc logs tương ứng trong môi trường test.

### 11.3. So sánh ba con số

Giả sử:
- **chunkSize=500** để flush/clear;
- **hibernate.jdbc.batch_size=50**;
- **transactionSize=5.000** entities.

Một flow có thể:

~~~text
Transaction A: 5.000 entities
    |
    +-- Chunk 1: 500 entities → flush → clear
    |        JDBC batches tối đa ~50 statements
    |
    +-- Chunk 2: 500 entities → flush → clear
    |        JDBC batches tương tự
    |
    ...
    |
    +-- Chunk 10: 500 entities → flush → clear
    |
    +-- COMMIT transaction A
~~~

Nếu chuyển sang transaction-per-chunk 500, mỗi 500 entities lại COMMIT riêng. Cùng chunkSize và JDBC batchSize nhưng atomicity/rollback khác hẳn.

### 11.4. order_inserts và order_updates

Hibernate có các cấu hình thường gặp:

~~~properties
hibernate.order_inserts=true
hibernate.order_updates=true
~~~

Khi provider sắp xếp INSERT/UPDATE cùng loại entity/SQL shape gần nhau, cơ hội gom thành JDBC batch có thể tăng. Nhưng có đánh đổi:
- Thêm công việc sắp xếp actions;
- Thứ tự DML không nên được business code dựa vào;
- Foreign keys/cascades có thể ràng buộc thứ tự thực thi;
- Sắp thứ tự khóa có thể ảnh hưởng deadlock patterns;
- Cần benchmark trên dataset thực.

Không mặc định bật cả hai sẽ luôn nhanh hơn.

### 11.5. Số lượng entity không bằng số lượng statements

Một Product đơn giản có thể tạo một INSERT. Nhưng nếu Product có:
- One-to-many children với cascade;
- Join-table rows;
- ElementCollection;
- Audit triggers;
- Versioning;
- Secondary tables;

thì một thao tác persist logical Product có thể tạo **nhiều SQL statements**. JDBC batch size tính theo statements tương thích, không phải “50 aggregate roots”.

### 11.6. Hạn chế của SQL shapes

Hibernate có thể không batch được hai UPDATE với SQL shape khác nhau, ví dụ:
- UPDATE products SET price=? WHERE id=? AND version=?;
- UPDATE products SET active=? WHERE id=? AND version=?.

Một provider/dynamic-update strategy có thể phát các SQL shapes khác nhau tùy dirty fields, làm giảm khả năng batching. Chọn tối ưu **@DynamicUpdate** (provider-specific) hay batching cần đo trên thực tế.

### 11.7. Driver có thể rewrite batch

Một số JDBC drivers có tùy chọn rewrite batched INSERTs thành dạng multi-values hoặc tối ưu truyền statements. Cách hoạt động phụ thuộc DB/driver và SQL statement. Không dùng cùng một JDBC URL flag cho mọi database rồi kỳ vọng kết quả.

**Tổng quát:** em.flush() là lệnh ORM, còn addBatch/executeBatch là khái niệm JDBC. Provider quyết định có dùng JDBC batching hay không và dùng như thế nào.

## 12. Chiến lược sinh ID quyết định khả năng batch INSERT

### 12.1. IDENTITY thường làm batching khó hơn

Entity:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Với nhiều cấu hình Hibernate, provider cần thực hiện INSERT sớm để biết generated key từ database; điều này **có thể hạn chế hoặc vô hiệu hóa JDBC INSERT batching cho entity dùng IDENTITY**.

Không khẳng định mọi provider, DB và mọi Hibernate version đều không thể batch bất kỳ thao tác nào khi có IDENTITY, nhưng cần nhận biết đây là một hạn chế phổ biến và kiểm tra thực tế.

### 12.2. SEQUENCE và pooled allocation

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "product_seq_gen"
)
@SequenceGenerator(
    name = "product_seq_gen",
    sequenceName = "product_seq",
    allocationSize = 50
)
private Long id;
~~~

Sequence strategy có thể cho phép provider biết IDs trước khi INSERT và thuận lợi hơn cho JDBC batching. **allocationSize** có thể giảm số lần round-trip cấp IDs nếu provider dùng cơ chế pooled/optimizer phù hợp.

Lưu ý:
- Database phải hỗ trợ sequences;
- Sequence increment và optimizer có yêu cầu tương thích;
- Migration DDL phải đúng;
- Có thể xuất hiện khoảng trống IDs, và đó không nhất thiết là lỗi;
- Không chuyển primary key strategy chỉ để tối ưu batch nếu làm hỏng dữ liệu hoặc compatibility.

### 12.3. TABLE generator và AUTO

**TABLE generator** dùng một bảng phụ để cấp IDs, có thể gây contention nếu nhiều writers cùng dùng. **AUTO** để provider chọn strategy phụ thuộc provider/dialect.

Không suy rằng AUTO luôn là SEQUENCE hoặc IDENTITY trên mọi hệ. Nếu hiệu năng import là yêu cầu, xác minh **effective generator** qua metadata, SQL logs và measurements.

### 12.4. UUID và client-generated IDs

Một entity có ID được tạo phía client có thể tránh việc phải INSERT để lấy generated ID, nhưng:
- UUID index locality có thể ảnh hưởng INSERT/index cost;
- DB storage/PK size tăng;
- Không phải mọi kiểu UUID có cùng tính chất;
- Provider vẫn có thể không batch do SQL shape/cascade;
- Business ID format không nên đổi chỉ vì một benchmark.

Sinh ID phía client là một lựa chọn kiến trúc, không tự bảo đảm throughput.

### 12.5. Đo các câu SELECT sequence

Nếu cứ mỗi entity lại gọi:

~~~sql
SELECT nextval('product_seq');
~~~

thì batch insert vẫn có thể chịu overhead cấp IDs. Sequence pooling có thể giảm số lần gọi, nhưng phải kiểm tra tương thích optimizer/DDL và kiến trúc nhiều writers.

### 12.6. Bảng tóm tắt về ID và batching

| ID strategy | Đặc điểm | Tác động cần kiểm tra |
|---|---|---|
| IDENTITY | DB trả key khi INSERT | Có thể cản batch INSERT |
| SEQUENCE | Có thể cấp ID trước INSERT | Thường thuận lợi hơn cho batching |
| SEQUENCE pooled | Cấp một dải IDs | Giảm sequence calls, yêu cầu cấu hình đúng |
| TABLE | Bảng lưu generator state | Có thể tạo contention |
| AUTO | Provider chọn strategy | Phải xác minh trên dialect thực |
| Assigned/UUID | ID có sẵn trước INSERT | Không tự tối ưu các DML khác |

## 13. saveAll, saveAndFlush và repository abstractions

### 13.1. saveAll không nhất thiết là một SQL bulk INSERT

Spring Data JPA có:

~~~java
productRepository.saveAll(products);
~~~

Tên **saveAll** không có nghĩa provider lập tức sinh một SQL INSERT đa giá trị hoặc một JDBC batch duy nhất. Implementation có thể gọi save từng entity, dùng persist hoặc merge tùy trạng thái entity.

Hiệu năng vẫn phụ thuộc transaction boundary, ID strategy, Hibernate batching, flush mode và số managed entities.

### 13.2. saveAll với List rất lớn vẫn tốn heap

~~~java
List<Product> products = parseAllMillionRows();
productRepository.saveAll(products);
~~~

Dù cấu hình batching tốt, **List đầu vào đã giữ một triệu Product objects**. Nếu repository trả Iterable/List of saved entities, code còn có thể giữ thêm references.

Nên chia đầu vào từ file/stream thành những chunks nhỏ rồi gọi một writer có transaction policy rõ. Với một transaction lớn và EntityManager được truy cập trực tiếp, cần flush/clear theo nhu cầu.

### 13.3. saveAndFlush không thay clear

~~~java
productRepository.saveAndFlush(product);
~~~

gọi save rồi flush theo semantics repository, **không có nghĩa nó clear persistence context**. Gọi saveAndFlush trên mỗi row có thể làm tăng số lần flush và giảm cơ hội batching.

### 13.4. Không gọi flush sau từng entity nếu không cần

~~~java
for (Product p : products) {
    em.persist(p);
    em.flush();
}
~~~

Mẫu này có thể làm mất lợi thế gom DML, tăng round-trips và overhead dirty checking. Thay vào đó flush/clear sau một chunk đủ hợp lý.

### 13.5. saveAll với detached entities có thể dùng merge

Spring Data JPA thường phân biệt entity mới hay đã tồn tại. Với entity đã có ID, save có thể dùng **merge**. Merge có semantics khác persist:
- Managed instance trả về có thể khác object nguồn;
- Provider cần load state để hợp nhất;
- Detached source không tự trở thành managed instance;
- Có rủi ro ghi đè nếu source stale;
- @Version giúp phát hiện conflicts khi áp đúng.

Với batch update, không dùng saveAll detached objects như một công cụ “cứ ghi đè database” nếu domain cần tránh lost updates. Khi nạp managed entities theo ID rồi sửa, dirty checking thường rõ ràng hơn.

### 13.6. Khi nào dùng repository abstraction?

- Business CRUD thông thường: Spring Data Repository rất thuận tiện.
- Import lớn: một dedicated JPA adapter với EntityManager và batching policy có thể giúp kiểm soát memory/flush.
- Update hàng triệu rows theo một predicate: cân nhắc JPQL bulk DML/native SQL nếu không cần entity callbacks.
- High-throughput insert riêng: JDBC batch/COPY/staging có thể phù hợp hơn JPA entity lifecycle.

Không “bỏ Spring Data JPA” chỉ vì benchmark nhỏ; hãy xác định bottleneck trước.

## 14. Bulk JPQL UPDATE/DELETE là chiến lược khác hẳn entity batching

Nếu cần đổi một field giống nhau cho hàng trăm nghìn rows:

~~~java
int updated = em.createQuery(
    """
    update Product p
    set p.active = false
    where p.active = true
    """
).executeUpdate();
~~~

đây là **JPQL bulk update** chứ không phải vòng lặp load-managed-change-flush-clear.

### 14.1. Ưu điểm của bulk DML

- Ít phải nạp entity objects vào Java heap;
- Có thể tránh dirty checking từng entity;
- Một SQL statement (hoặc tập statements phụ thuộc provider/dialect) có thể xử lý nhiều rows;
- Thường tốt hơn vòng lặp EntityManager.find khi cùng một rule đơn giản áp cho cả tập.

### 14.2. Bulk DML bỏ qua một số semantics của managed entities

JPQL bulk UPDATE/DELETE thường **không** xử lý entities như khi sửa từng managed object:
- Không chạy lifecycle callbacks cho từng entity theo cách ORM normal;
- Không áp cascade/entity graph như một vòng lặp em.remove;
- Không tự đồng bộ state của các managed entities đang có;
- Không tự tăng @Version cho từng entity theo optimistic locking lifecycle thông thường, trừ khi query/provider xử lý đặc biệt;
- Query cache/L2 invalidation cần kiểm tra provider.

Vì vậy bulk DML chỉ hợp lý khi bài toán cho phép semantics đó.

### 14.3. Persistence context có thể stale sau bulk DML

~~~java
Product p = em.find(Product.class, 42L);

// Bulk SQL/JPQL thay đổi giá trị row trong DB.
em.createQuery(
    "update Product p set p.active = false"
).executeUpdate();

// p vẫn có thể giữ active=true trong context!
~~~

Nếu cần tiếp tục đọc entity current state, clear/refresh/reload trong transaction có visibility phù hợp.

### 14.4. Flush trước bulk DML nếu có pending changes liên quan

Nếu persistence context có pending entity changes, việc chạy bulk update mà không cân nhắc flush/ordering có thể tạo conflict không mong muốn. Có thể cần:

~~~java
em.flush();

int count = em.createQuery(
    """
    update Product p
    set p.active = false
    where p.id in :ids
    """
)
.setParameter("ids", selectedIds)
.executeUpdate();

em.clear();
~~~

**selectedIds** phải không rỗng và số parameters phải phù hợp dialect. Ví dụ trên là một pattern, không bảo đảm mọi provider tự xử lý empty IN lists hay invalidation đầy đủ.

### 14.5. Bulk UPDATE và @Version

Nếu ứng dụng dựa vào @Version để phát hiện conflicts, bulk UPDATE thông thường không tự áp optimistic version increments. Một lệnh:

~~~java
int count = em.createQuery(
    """
    update Product p
    set p.active = false,
        p.version = p.version + 1
    where p.id in :ids
    """
)
.setParameter("ids", selectedIds)
.executeUpdate();
~~~

chỉ là ví dụ với **numeric version** và DB/provider hỗ trợ; còn cần đánh giá concurrency, filters/tenants, version policy và đúng semantics của JPA bulk update. Không coi đây là thay thế hoàn toàn cho optimistic locking per entity.

### 14.6. Bulk DELETE khác em.remove từng entity

~~~java
em.createQuery(
    "delete from Product p where p.active = false"
).executeUpdate();
~~~

không bảo đảm gọi @PreRemove hoặc cascades theo đường entity remove thông thường. Với foreign keys, soft delete, audit và business events, cần thiết kế rõ.

### 14.7. Quyết định dùng cách nào

| Nhu cầu | Entity batching với flush/clear | Bulk JPQL/native SQL |
|---|---|---|
| Mỗi row có business logic khác nhau | Phù hợp | Khó biểu diễn |
| Cần lifecycle callbacks | Phù hợp hơn | Thường bỏ qua per-entity callbacks |
| Cần cascades/graph consistency | Có thể phù hợp | Phải xử lý riêng |
| Cùng một field được cập nhật đồng loạt | Có overhead | Thường hiệu quả |
| Kiểm soát @Version từng row | Có ở managed lifecycle | Phải thiết kế |
| Muốn hạn chế Java heap | Chunking giải quyết | Thường ít entity objects hơn |
| Cần SQL tối ưu DB-specific | Không phải luôn tốt nhất | Native/JDBC có thể phù hợp |

## 15. Hibernate StatelessSession: lựa chọn riêng, không phải JPA chuẩn

Hibernate có **StatelessSession** trong API riêng, được thiết kế cho những use cases không cần full persistence-context semantics. Nó có các khác biệt quan trọng so với Session/EntityManager:
- Không có first-level persistence context theo nghĩa managed identity map thông thường;
- Không dựa trên dirty checking tự động giống managed entities;
- Các semantics cascade/interceptor/event/collection có thể khác;
- Cách thao tác insert/update/delete cần theo API phiên bản Hibernate.

**StatelessSession không thuộc Jakarta Persistence API.** Không đề xuất nó như drop-in replacement cho EntityManager khi application dựa trên cascades, lifecycle listeners, optimistic locking, entity relationships hoặc business invariants.

Nếu chọn, đặt trong infrastructure adapter Hibernate-specific và kiểm thử behavior đúng phiên bản. So sánh với **EntityManager + flush/clear**, JDBC batch hoặc native bulk SQL trên dữ liệu thực.

## 16. Khi JPA không phải lựa chọn phù hợp cho toàn bộ pipeline

Đối với hàng triệu rows, có những tác vụ:
- COPY/bulk load vào staging table;
- INSERT SELECT hoặc MERGE/UPSERT theo dialect;
- JDBC PreparedStatement batching;
- DB stored procedure;
- Partition/CTAS migration;
- Streaming ETL với bulk writer.

Các cách này có thể nhanh hơn vòng lặp managed entities vì bỏ overhead object mapping/dirty checking. Nhưng cần tự chịu trách nhiệm:
- Data validation;
- Transaction/rollback;
- Constraints;
- Idempotency;
- Audit;
- Version columns;
- Cache invalidation;
- Event publishing/outbox;
- Security/tenant isolation.

**Tối ưu hiệu năng không được đánh đổi các invariants bắt buộc.**

## 17. Memory growth: flush/clear giải quyết gì và không giải quyết gì?

### 17.1. Những nguồn tiêu thụ bộ nhớ

~~~text
JVM heap
  |
  +-- Input buffers / parsed DTOs
  +-- Managed entity instances
  +-- Persistence context identity map
  +-- Entity snapshots / dirty-check state
  +-- Pending actions / cascading graphs
  +-- Query result lists
  +-- Application output/metrics buffers
  +-- Other caches / thread state
~~~

em.clear() chủ yếu giải quyết một phần liên quan **managed entities/persistence context**. Nó không:
- Xóa DTOs khỏi một List đầu vào lớn;
- Xóa application collection còn giữ references;
- Đóng ResultSet/stream;
- Đóng network input;
- Giải phóng toàn bộ JVM heap ngay lập tức;
- Thay đổi database transaction log;
- Xóa second-level cache.

### 17.2. Heap có thể vẫn tăng dù clear đúng

Một ứng dụng:

~~~java
List<ProductInput> allInputs = parseEntireFile();
importAll(allInputs, 500);
~~~

vẫn giữ mọi ProductInput trong memory. Với file cực lớn, cần đọc theo từng record/stream:
- BufferedReader hoặc streaming CSV parser;
- JsonParser dạng stream;
- Page/chunk từ queue;
- Resource lifecycle đóng đúng;
- Backpressure để không đẩy nhiều chunks đồng thời vào memory.

### 17.3. GC heap không bằng resident memory

Một heap dump/GC log có thể cho thấy objects đã không còn reachable, nhưng hệ điều hành vẫn thấy process RSS cao do JVM memory management, direct buffers, caches hoặc GC heuristics. Đừng chỉ nhìn Windows Task Manager/RSS để kết luận em.clear không có tác dụng.

Cần đo:
- Live heap sau GC trong benchmark;
- Allocations/GC pauses;
- Persistence context entity count nếu provider expose metrics;
- Input buffers;
- JDBC/pool memory;
- Application collections.

### 17.4. Context lớn ảnh hưởng thời gian flush

Dirty checking thường duyệt state liên quan đến managed entities theo provider strategy; nhiều managed entities có thể tăng flush cost. Hibernate có thể hỗ trợ bytecode enhancement/dirty tracking, nhưng số lượng objects và cascades vẫn quan trọng.

Với batch nghiệp vụ dài, kiểm soát context size là **một thành phần hiệu năng**. Không hứa một mức tăng tốc cố định khi không có benchmark.

### 17.5. em.clear không xóa L2 cache

L2 và query cache (nếu được bật) có lifespan/region/invalidation riêng. Clear L1 không tương đương:

~~~java
emf.getCache().evictAll();
~~~

Và không cần evictAll sau mỗi chunk chỉ để tiết kiệm memory L1; làm vậy có thể tạo cache miss và tăng database load không cần thiết.

## 18. Chọn chunkSize và transaction size như thế nào?

Không có một giá trị đúng cho mọi project. Một entity hai cột khác rất nhiều một aggregate gồm 20 children và nhiều collections.

### 18.1. Thử từ một giá trị hợp lý rồi đo

Những giá trị như **50, 100, 250, 500, 1.000** có thể được dùng làm **điểm thí nghiệm**, không phải khuyến nghị mặc định cho sản xuất. Với một số workloads, chunk rất nhỏ làm tăng flush overhead; chunk quá lớn làm tăng memory, latency và thời gian rollback.

Dùng:
- Cùng dataset/fixtures;
- Cùng DB/driver/provider versions;
- Cùng connection pool size;
- Cùng indexes/triggers;
- Cùng transaction policy;
- Cùng warmup;
- Đo nhiều lần với percentile, không chọn kết quả đẹp nhất.

### 18.2. Những chỉ số nên đo

| Metric | Vì sao cần |
|---|---|
| Rows/second | Throughput thực tế |
| P50/P95/P99 chunk latency | Không chỉ xem tổng throughput |
| Heap live set / allocation | Memory pressure |
| GC pause / GC frequency | Ảnh hưởng latency |
| Hibernate flush count/time | Overhead đồng bộ ORM |
| Entity insert/update/delete count | Workload thực sự |
| JDBC batch execution count/size | Có batching thật không? |
| SQL statement count | N+1/query per row? |
| Database CPU/I/O/WAL | DB có phải bottleneck? |
| Lock wait/deadlock | Transaction giữ locks bao lâu |
| Connection acquisition time | Pool saturation |
| Transaction duration | Khả năng rollback/timeout |
| Error rate/retry rate | Có giữ correctness không? |

### 18.3. Ví dụ ma trận benchmarking

| Thử nghiệm | Flush/clear chunk | JDBC batch config | Transaction policy | Điều cần đánh giá |
|---|---:|---:|---|---|
| A | Không chủ động | 0 hoặc disabled | Toàn file | Baseline về heap/GC |
| B | 100 | 0 hoặc disabled | Toàn file | Hiệu quả chỉ từ quản lý L1 |
| C | 100 | 50 | Toàn file | Lợi ích thêm của JDBC batching |
| D | 500 | 50 | Toàn file | Chunk lớn hơn có lợi không |
| E | 500 | 50 | Mỗi chunk commit | Transaction overhead/partial success |
| F | 1.000 | 100 | Theo business window | DB saturation, lock time |

Bảng không khẳng định C/D/E/F luôn nhanh nhất; nó giúp thiết kế một phép đo tách biệt các yếu tố.

### 18.4. Flush quá thường xuyên

Với chunkSize=1:

~~~java
for (ProductInput input : inputs) {
    em.persist(new Product(input.sku(), input.price()));
    em.flush();
    em.clear();
}
~~~

Có thể làm tăng:
- Flush calls;
- JDBC round-trips;
- SQL execution overhead;
- Thời gian chạy;
- Network latency sensitivity.

Tuy nhiên cũng có trường hợp một row phải xác nhận DB constraint ngay; đó là yêu cầu nghiệp vụ khác với bulk throughput.

### 18.5. Chunk quá lớn

Với chunkSize=100.000:
- Context giữ nhiều objects;
- GC có thể tăng;
- Flush lớn có thể tốn thời gian;
- Một lỗi ở cuối khối khiến diagnostic khó xác định row;
- Database transaction giữ resources lâu hơn tùy commit policy;
- Các SQL batches vẫn có thể nhỏ hơn rất nhiều chunkSize.

Chọn chunk size qua benchmark, không lấy khả năng heap tối đa làm target.

### 18.6. Transaction size độc lập chunk size

Một lựa chọn:
- Mỗi 200 entities flush/clear;
- Sau 2.000 entities commit rồi mở transaction mới.

Nhưng nếu dùng EntityManager do Spring container quản lý, không được gọi tx.commit trực tiếp trong một @Transactional method. Phải tổ chức transaction boundary thông qua service/TransactionTemplate.

### 18.7. Adaptive chunk sizing có cần thiết?

Một pipeline có thể giảm chunk khi heap/DB latency tăng. Tuy nhiên chiến lược động phức tạp:
- Metrics có độ trễ;
- Thay đổi chunk làm khó dự đoán checkpoint;
- Error recovery phải giữ semantics;
- Không được thay transaction atomicity ngoài business contract;
- Rất dễ tạo dao động.

Chỉ áp adaptive sizing sau khi đã có baseline và hiểu bottleneck; một fixed chunk size được test tốt thường dễ vận hành hơn.

## 19. Transaction, locks và database pressure

Flush/clear giúp ORM quản lý object state, nhưng **database transaction vẫn quyết định lock/rollback scope**.

### 19.1. Flush không giải phóng database locks đã được giữ

~~~text
BEGIN
  UPDATE 500 rows
  FLUSH
  CLEAR
  UPDATE 500 rows
  FLUSH
  CLEAR
COMMIT
~~~

Ở nhiều database/isolation configurations, locks của các UPDATE vẫn có thể được giữ đến transaction end. **Clear không gửi UNLOCK**. Vì vậy, một transaction chứa 100 lần flush vẫn có thể làm transactions khác chờ lâu.

### 19.2. Dài transaction làm tăng blast radius

Nếu một transaction chứa toàn bộ 2 triệu updates:
- Một lỗi ở cuối có thể rollback rất nhiều công việc;
- DB transaction log/undo có thể tăng;
- Deadlock hoặc timeout có thể xảy ra;
- Replication lag có thể tăng trong một số hạ tầng;
- Khả năng quan sát tiến độ và resume khó hơn.

Commit theo chunks giảm phạm vi rollback nhưng chấp nhận partial success. Đây là **quyết định nhất quán dữ liệu**, không chỉ tối ưu memory.

### 19.3. Thứ tự khóa và deadlock

Hai workers cùng cập nhật Products theo thứ tự khác nhau:

~~~text
Worker A: lock Product#10 → chờ Product#20
Worker B: lock Product#20 → chờ Product#10
~~~

có thể tạo deadlock. Để giảm nguy cơ:
- Sort IDs theo thứ tự ổn định trước update;
- Giữ transaction ngắn;
- Tránh đọc/sửa unrelated rows;
- Phân vùng workload để tránh trùng;
- Dùng retry bounded trên transaction mới khi DB báo deadlock.

**order_updates=true** của Hibernate có thể ảnh hưởng SQL ordering, nhưng không thay thế một concurrency plan dựa trên business aggregates.

### 19.4. Isolation và snapshot

Một batch đọc Products trong transaction REPEATABLE READ/SNAPSHOT có thể thấy snapshot cố định, trong khi workers khác cập nhật. Khi commit theo chunk, mỗi transaction mới có thể thấy state khác.

Cần xác định yêu cầu:
- Quét nhất quán một tập dữ liệu tại thời điểm T;
- Chấp nhận trạng thái mới cập nhật trong từng chunk;
- Chặn concurrent writers;
- Dùng version checks và retry.

Không thể áp một isolation level duy nhất cho mọi import/repair job mà không xem business semantics.

### 19.5. Transaction timeouts

Spring hoặc JPA provider có thể đặt transaction/query timeouts, database có lock/statement timeouts, pool có acquisition timeout. Mỗi loại khác nhau.

Nếu job bị timeout ở chunk thứ 50, giảm chunkSize có thể giúp nhưng không chắc:
- Query plan có thể là vấn đề;
- Transaction vẫn quá dài;
- Pool đang cạn;
- Lock contention ở một row;
- Database bị I/O saturation;
- Trigger/index maintenance nặng.

Theo dõi nguyên nhân cụ thể trước khi tối ưu.

### 19.6. Không giải quyết fail bằng cách chỉ tăng timeout

Tăng timeout mà không giảm lock footprint hoặc sửa SQL có thể làm hệ thống tắc lâu hơn. Cần phân tích DB wait events, deadlocks, execution plan và transaction duration.

## 20. Cascades, associations và entity graphs khi xử lý theo khối

Một Product có Category, Tags, PriceHistory hoặc stock records. Batch không còn là “một entity tương ứng một INSERT”.

### 20.1. Cascade persist

~~~java
@Entity
public class Order {

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST
    )
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

em.persist(order) có thể schedule INSERT cho cả Order và OrderLine. Nếu một chunk gồm 500 Order, tổng số managed entities có thể là hàng nghìn.

**Chunk theo root count** không cho biết chính xác heap/SQL count. Nếu mỗi Order có 1.000 lines, chunk 500 roots có thể quá lớn.

### 20.2. Không clear giữa parent và children khi graph chưa hoàn chỉnh

~~~java
Order order = new Order(...);
em.persist(order);

em.flush();
em.clear();

// Sau clear, order đã detached.
// Thêm line vào order ở Java rồi hy vọng
// cascade persist tự chạy ở commit là sai.
order.addLine(new OrderLine(...));
~~~

Phải hoàn tất aggregate/cascade trước flush/clear, hoặc dùng một chiến lược nạp/attach managed references phù hợp.

### 20.3. Hai chunks cần tham chiếu cùng Category

Nếu Category đã tồn tại, không persist một Category mới cho mỗi Product.

Có thể dùng:

~~~java
Category categoryRef = em.getReference(
    Category.class,
    categoryId
);

Product product = new Product(...);
product.setCategory(categoryRef);
em.persist(product);
~~~

Ví dụ giả định Product có method setCategory và mapping @ManyToOne phù hợp. getReference trả một managed reference/proxy theo provider, và việc reference ID không tồn tại có thể chỉ được phát hiện sau. FK constraint ở DB vẫn cần thiết.

Sau **em.clear()**, categoryRef cũ có thể đã detached; với chunk tiếp theo nên lấy reference mới trong context hiện tại, thay vì giữ nguyên Java proxy/reference managed cũ qua các chunks.

### 20.4. getReference không phải cách bypass mọi validation

Nếu database category_id không tồn tại, getReference có thể không query DB ngay; lỗi có thể xảy ra khi access field hoặc flush FK. Không xem API này là bằng chứng reference hợp lệ, và không dùng để bỏ qua authorization/tenant isolation.

### 20.5. orphanRemoval và clear

Một aggregate:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
~~~

Khi sửa collection, JPA có thể schedule INSERT/DELETE/UPDATE. Nếu em.clear() trước khi flush, pending changes đối với orphan removal có thể bị bỏ. Nếu graph bị detached giữa thao tác, subsequent changes có thể không được dirty-check.

### 20.6. N+1 query vẫn tồn tại

Một batch update:

~~~java
for (Product product : products) {
    String name = product.getCategory().getName();
    // ...
}
~~~

có thể gây thêm SELECT cho mỗi Category nếu lazy associations được truy cập theo cách không tối ưu. flush/clear không sửa N+1; thậm chí clear thường xuyên có thể làm provider phải tải lại dữ liệu lặp.

Giải pháp riêng:
- Projection query;
- JOIN FETCH có kiểm soát;
- EntityGraph;
- Batch fetching phù hợp provider;
- Cache read-only reference data khi đáp ứng freshness policy;
- Preload dictionary/tables nhỏ thành map riêng nếu phù hợp.

### 20.7. Fetch join collections và pagination

Phân trang qua JPQL với collection fetch joins có thể tạo duplicate rows hoặc khiến provider phải paginate trong memory. Không dùng một query collection JOIN FETCH khổng lồ rồi trông mong em.clear cứu heap.

Một chiến lược:
1. Trang IDs của root entities;
2. Tải graph cho đúng IDs trong chunk;
3. Transform;
4. Flush/clear;
5. Tiếp tục keyset.

### 20.8. Audit callbacks và listeners

Với @PrePersist/@PreUpdate, các callbacks vẫn có thể chạy trong normal entity lifecycle. Một callback nạp quan hệ hoặc gọi dịch vụ ngoài có thể làm giảm throughput hoặc phát side effects không mong muốn trong batch.

Nếu cần audit/outbox, phải thiết kế:
- Thao tác DB thuộc cùng transaction;
- Không publish event trước commit;
- Callback không trở thành một query/service call mỗi row;
- Provider-specific event handling có behavior được kiểm thử.

### 20.9. Chu trình parent-child khi khóa chính chưa có

Với IDENTITY generator, parent ID có thể chỉ xuất hiện sau INSERT; với SEQUENCE có thể được cấp sớm. Khi tạo children, đừng giả định mọi generated ID strategy hoạt động như nhau. Dùng mapping associations đúng và để provider quản lý FK theo mapping, không tự lấy ID ở thời điểm chưa được gán.

## 21. @Version và cập nhật từng khối

### 21.1. Optimistic lock bảo vệ stale updates

~~~java
@Version
private Long version;
~~~

Khi một Product được load version=5 rồi người khác commit version=6, lần flush của batch có thể ném **OptimisticLockException** nếu provider update dựa trên version cũ.

Điều này bảo vệ chống ghi đè âm thầm, nhưng cần policy phục hồi rõ.

### 21.2. Lỗi một row có thể làm rollback cả chunk

Nếu 500 rows được update trong một transaction, một optimistic conflict ở row 379 có thể làm transaction rollback. Không cố tiếp tục từ row 380 trên cùng persistence context/transaction bị lỗi.

Có thể:
- Retry cả chunk trong transaction mới;
- Chia chunk nhỏ hơn khi conflict rate cao;
- Tách row lỗi thành quarantine/review với policy rõ;
- Re-fetch current state và reapply business intent;
- Dùng conditional SQL nếu hợp với nghiệp vụ.

### 21.3. Retry detached snapshot y nguyên nguy hiểm

Sai về semantics:

~~~java
catch (OptimisticLockException ex) {
    repository.saveAll(oldDetachedProducts);
}
~~~

Nếu detached Products chứa state cũ, retry y nguyên có thể tiếp tục fail hoặc ghi đè khi code đổi version sai. Cần reload **current managed entities** và kiểm tra lại intent.

### 21.4. Cập nhật hàng loạt có writer khác

Một batch price recalculation và một API cập nhật giá thủ công có thể cùng viết Product. Nếu batch dựa trên giá snapshot cũ, cần quyết định:
- Manual override có ưu tiên không;
- Batch có được tính lại theo price mới không;
- Khi conflict có retry hay skip;
- Có cần version/updated_at predicate;
- Có cần lock theo SKU/id.

flush/clear không trả lời các câu hỏi này; nó chỉ giúp quản lý ORM state.

### 21.5. External SQL writers và version

Nếu ETL sửa price bằng SQL trực tiếp nhưng **không tăng version**, optimistic locking của JPA có thể không phát hiện xung đột. Khi nhiều writers tồn tại, cần versioning/concurrency contract nhất quán trên mọi đường ghi, không chỉ entity annotation.

## 22. Đọc dữ liệu theo trang hay stream?

### 22.1. getResultList trên toàn bảng là rủi ro

~~~java
List<Product> all = em.createQuery(
    "select p from Product p",
    Product.class
).getResultList();
~~~

Với hàng triệu rows, List và persistence context có thể rất lớn. em.clear() **sau khi nạp toàn bộ** không giải quyết peak memory đã xảy ra.

### 22.2. Keyset pagination theo ID

~~~java
List<Long> ids = em.createQuery(
    """
    select p.id
    from Product p
    where p.id > :lastId
      and p.id <= :upperBound
    order by p.id
    """,
    Long.class
)
.setParameter("lastId", lastId)
.setParameter("upperBound", upperBound)
.setMaxResults(chunkSize)
.getResultList();
~~~

Chốt upperBound ở đầu job có thể giới hạn phạm vi IDs sẽ quét. Nhưng nó không tự đảm bảo tất cả rows dưới upperBound tồn tại/trạng thái không đổi trong quá trình chạy.

### 22.3. Đừng dùng OFFSET khi predicate bị thay đổi bởi job

Nếu job chọn active=true rồi chuyển từng record thành active=false, OFFSET page tiếp theo có thể bỏ sót rows. Keyset trên một khóa ổn định thường phù hợp hơn.

### 22.4. getResultStream và cursor không luôn tiết kiệm memory

JPA có getResultStream; provider có thể thực thi bằng JDBC cursor/streaming hoặc materialize data tùy implementation. Bên dưới còn phụ thuộc fetch size/transaction/driver.

Do đó:

~~~java
try (Stream<Product> stream = query.getResultStream()) {
    stream.forEach(...);
}
~~~

không phải cam kết mọi provider chỉ nạp một vài rows tại một thời điểm. Nếu provider materializes một List hoặc giữ các managed entities, heap vẫn có thể tăng.

### 22.5. Clear trong lúc đang duyệt stream cần kiểm tra kỹ

Nếu một stream giữ ResultSet/cursor đang mở, flush/clear trong quá trình xử lý có thể tương tác với provider session state, lazy loading, DB cursor, auto-flush hoặc transaction handling. **Không tuyên bố một pattern stream+clear portable an toàn với mọi provider.**

Với nhu cầu predictable behavior, keyset ID paging + load/update one chunk thường dễ kiểm soát hơn.

### 22.6. Không chia sẻ cùng EntityManager giữa threads

EntityManager không thread-safe. Nếu parallel import:
- Mỗi worker có transaction/context riêng;
- Không chia sẻ managed entities giữa workers;
- Phân vùng IDs/SKUs không trùng;
- Giới hạn concurrency theo connection pool và DB;
- Chặn duplicate processing bằng claim/idempotency;
- Tránh lock order khác nhau gây deadlock.

Không cho 8 threads cùng gọi em.persist và em.clear trên một EntityManager.

## 23. Backpressure và parallelism

### 23.1. Nhiều workers không luôn tăng tốc

Nếu một worker xử lý 10.000 rows/s và database đã gần giới hạn I/O, tăng lên 10 workers có thể:
- Làm giảm throughput;
- Tăng lock contention;
- Cạn connection pool;
- Tăng deadlocks;
- Tăng WAL/redo pressure;
- Tăng GC/CPU;
- Làm latency của workload online xấu đi.

Cần đo tại bottleneck DB và so với SLA của hệ thống đang phục vụ người dùng.

### 23.2. Bound queue chứa chunks

Producer parse file nhanh hơn consumer ghi DB có thể khiến hàng nghìn chunks chờ trong heap. Dùng bounded queues, backpressure và worker limit để giữ memory có giới hạn.

~~~text
Streaming parser
      |
      v
Bounded queue (ví dụ tối đa 8 chunks)
      |
      v
1..N workers
mỗi worker có EntityManager/transaction riêng
      |
      v
Database connection pool
      |
      v
Database
~~~

### 23.3. Concurrency không phá ordering/idempotency

Nếu Product#42 có hai updates trong file theo thứ tự:
- price=100;
- price=200;

đưa chúng vào hai parallel workers có thể làm UPDATE price=100 chạy sau price=200, trái với semantics đầu vào.

Cần:
- Partition theo entity key;
- Đảm bảo order trong một partition;
- Dedupe/last-write-wins có version/timestamp policy;
- Hoặc loại các updates trùng trước khi ghi.

### 23.4. Không scale worker vượt pool capacity

Ví dụ có 16 workers mà pool tối đa 8 connections, các workers có thể chờ connection. Nếu transactions cũng mở secondary connections (REQUIRES_NEW), áp lực có thể nặng hơn.

Điều chỉnh worker count, pool size và DB capacity cùng nhau; không coi mỗi thread thêm vào là hiệu năng tự tăng.

## 24. Read-only transactions và batch ghi

### 24.1. @Transactional(readOnly=true) không dành cho batch write

~~~java
@Transactional(readOnly = true)
public void importProducts(...) {
    em.persist(...);
}
~~~

Một số transaction managers/providers dùng read-only như optimization hint/flush-mode adjustment; database có thể từ chối write nếu transaction thật là read-only. Không dùng readOnly=true cho method cần INSERT/UPDATE/DELETE.

### 24.2. Read-only phase và write phase

Một job có thể:
1. Transaction read-only đọc IDs/projections;
2. Transaction write cho mỗi chunk;
3. Commit rồi ghi checkpoint.

Nhưng khi tách transactions, rows có thể thay đổi giữa lúc đọc và lúc ghi. Dùng version/business predicates để bảo vệ expected state.

### 24.3. Không dùng flush mode MANUAL provider-specific như phép tối ưu vô điều kiện

Hibernate có những flush modes ngoài các giá trị JPA chuẩn. Tắt auto-flush quá mạnh có thể làm entity writes không được đồng bộ khi developer quên explicit flush. Nếu dùng provider-specific flush mode, đặt trong infrastructure adapter và kiểm thử semantics.

## 25. Xử lý lỗi trong một khối

Một khối có thể thất bại vì duplicate SKU, NOT NULL/CHECK/FK, optimistic conflict, deadlock, lock timeout, connection failure, mapping error hoặc JDBC batch exception. Hành vi phục hồi phụ thuộc **tính chất lỗi** và **transaction scope**.

### 25.1. Không catch flush exception rồi đi tiếp

Sai:

~~~java
for (ProductInput input : inputs) {
    em.persist(new Product(input.sku(), input.price()));

    if (++count % chunkSize == 0) {
        try {
            em.flush();
        } catch (PersistenceException ex) {
            log.warn("Bỏ qua chunk hỏng", ex);
        }
        em.clear();
    }
}
~~~

Sau flush failure, transaction có thể rollback-only hoặc DB transaction đã aborted. **em.clear không làm transaction sạch lại**. Phải rollback hoặc để transaction manager xử lý lỗi, rồi mở transaction/context mới khi có chính sách retry.

### 25.2. Một lỗi không nhất thiết chỉ ảnh hưởng một row

Nếu JDBC batch gồm 50 INSERT statements và statement thứ 37 vi phạm UNIQUE, driver có thể báo BatchUpdateException. Những statements trước có thể đã thực thi nhưng **chưa commit**. Với transaction-per-chunk, rollback loại những thay đổi chưa commit của chunk.

Không từ update counts của BatchUpdateException suy ra 36 entities đã được lưu bền vững.

### 25.3. Phân loại permanent và transient

| Lỗi | Bản chất thường gặp | Hướng xử lý |
|---|---|---|
| Duplicate SKU | Vi phạm uniqueness | Dedupe, skip/reject theo business |
| NOT NULL/CHECK | Dữ liệu sai | Validate/quarantine/fix input |
| FK invalid | Tham chiếu thiếu/race | Sửa thứ tự load/relationship |
| Optimistic conflict | Snapshot đã cũ | Reload/recompute/retry có policy |
| Deadlock | Transaction concurrency | Rollback, bounded retry transaction mới |
| Serialization failure | Snapshot concurrency | Retry toàn unit of work nếu an toàn |
| Lock timeout | Contention | Điều tra lock, retry bounded khi phù hợp |
| Query timeout | Query/DB load | Không retry mù quáng |
| Connection failure | Hạ tầng, có thể unknown outcome | Idempotency/reconciliation |
| Mapping/schema mismatch | Code/migration lỗi | Sửa deployment |

Một lỗi permanent không tự hết bằng cách giảm chunkSize. Một lỗi transient không nên retry vô hạn.

### 25.4. Bisect chunk để xác định row lỗi khi business cho phép

Khi chấp nhận lưu những rows hợp lệ và cách ly rows lỗi:
1. Ghi chunk 500 rows trong transaction A.
2. Nếu fail, rollback transaction A.
3. Chia chunk làm hai phần.
4. Thử từng phần trong **transaction mới**.
5. Tiếp tục phân nhỏ khi cần.
6. Quarantine row lỗi với source offset và category.
7. Chỉ commit các phần hợp lệ theo contract.

**Cảnh báo:** Không phải mọi lỗi đều do một row riêng lẻ. Hai rows trùng SKU có thể từng row riêng biệt hợp lệ nhưng cùng nhau vi phạm UNIQUE. Thứ tự input/dependencies có thể quan trọng. Deadlock không phải bad row. Nếu commit outcome chưa rõ, retry phần đã commit có thể tạo duplicate.

Bisect là kỹ thuật **có điều kiện**, không phải cách xử lý mặc định.

### 25.5. Quarantine lưu những gì?

Một bảng/file lỗi có thể chứa:
- Import run ID;
- Row number/source offset;
- Business key được bảo vệ;
- Stable error category;
- Validation fields;
- Retry status/attempt count;
- Correlation ID;
- Schema/parser version.

Không log raw SQL exception hoặc toàn bộ dữ liệu nhạy cảm. Khi reprocess, kiểm tra idempotency và input version.

### 25.6. Validate trước persistence để giảm lỗi

~~~java
for (ProductInput input : chunk) {
    validateInput(input);
}

for (ProductInput input : chunk) {
    em.persist(new Product(input.sku(), input.price()));
}

em.flush();
~~~

Validation Java giảm lỗi đầu vào, nhưng **không thay database constraints**. UNIQUE vẫn có thể race với transaction khác.

### 25.7. Rollback không đảo ngược mọi side effect

Nếu service gửi email/publish message trước commit, DB rollback không thu hồi được email/event. Với batch quan trọng, dùng transactional outbox hoặc publish-after-commit strategy với idempotent processing.

### 25.8. Commit outcome unknown

Một connection có thể đứt khi COMMIT. Database có thể đã commit nhưng caller chưa nhận acknowledgment. Không tự đánh dấu chunk failed rồi INSERT lại nếu không có idempotency key, importRunId/chunkId, reconciliation và cơ chế kiểm tra trạng thái đã commit.

## 26. Checkpoint, resume và idempotency

### 26.1. Checkpoint phải bám transaction outcome

~~~text
BEGIN transaction chunk#15
  INSERT/UPDATE Products
  FLUSH
  Ghi trạng thái chunk#15 đã xử lý trong DB (nếu cùng resource)
COMMIT
       |
       v
  Chunk#15 bền vững
       |
       v
  Có thể bắt đầu chunk#16
~~~

Nếu checkpoint ở một hệ thống khác, crash có thể xảy ra giữa DB COMMIT và checkpoint write. Cần reconciliation hoặc một protocol nhất quán.

### 26.2. Một bảng theo dõi chunk

~~~sql
CREATE TABLE import_chunks (
    run_id VARCHAR(100) NOT NULL,
    chunk_id BIGINT NOT NULL,
    start_offset BIGINT NOT NULL,
    end_offset BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (run_id, chunk_id)
);
~~~

Ghi tiến độ **cùng transaction với domain rows** khi có thể. UNIQUE run_id/chunk_id giúp nhận diện chunk bị xử lý lại, nhưng vẫn cần business idempotency nếu xử lý từng row có side effects khác.

### 26.3. Source phải có phiên bản ổn định

Checkpoint offset=10.000 chỉ có ý nghĩa nếu source không thay đổi hoặc có hash/immutable version. Nếu file thay đổi và một hàng được chèn trước offset, resume có thể bỏ sót hoặc xử lý trùng.

Nên ghi source ID/hash, parser version, run parameters, last committed chunk và upperBound/keyset cursor khi đọc DB.

### 26.4. UPSERT không tự giải quyết business conflicts

Nếu file có hai updates khác nhau cho cùng SKU, một câu UPSERT có thể làm row sau thắng theo SQL order, nhưng **không tự chứng minh đó là quy tắc nghiệp vụ đúng**. Cần version/order/deduplication policy.

### 26.5. Partial progress phải được báo rõ

Nếu 20 chunks đã commit, chunk 21 fail và các chunks sau chưa chạy, job status phải phản ánh **partial success**, không trả all-success. Khi retry, cần phân biệt số rows đã commit với số rows chỉ được parse hoặc flush.

### 26.6. Exactly-once không xuất hiện từ flush/clear

Những hệ có retries, duplicate message delivery và commit outcome unknown thường dùng **at-least-once processing + idempotent side effects**. Không hứa exactly-once chỉ vì mỗi chunk được em.flush và tx.commit.

## 27. Spring Batch và chunk-oriented processing

**Spring Batch** là framework hỗ trợ reader, processor, writer, step execution, job repository, restart, skip/retry và partitioning. Nó **không phải chức năng tự động xuất hiện** khi gọi em.flush/em.clear.

~~~text
ItemReader → ItemProcessor → ItemWriter
     |            |             |
     +---------- Chunk N --------+
                    |
                    v
             Transaction commit
                    |
                    v
               Job progress
~~~

Chunk size trong Spring Batch thường liên quan transaction commit boundary của step theo configuration, nhưng cách buffering/retry/writer lifecycle phụ thuộc Spring Batch version.

### 27.1. JpaItemWriter và các phiên bản

Spring Batch có JPA item-writer support trong các versions phù hợp. Cách flush/clear/persist/merge có thể khác theo version/configuration. **Không khẳng định một writer đang dùng luôn clear theo cùng cách từ một bài hướng dẫn viết cho version khác**; kiểm tra API và test lifecycle.

### 27.2. Restartability không thay idempotency

Job repository/checkpoint giúp resume nhưng không giải quyết mọi tình huống:
- DB commit rồi crash trước external checkpoint;
- Source thay đổi;
- External side effects không cùng transaction;
- Duplicate business key;
- Row được retry nhiều lần.

### 27.3. Khi nào chọn framework?

Chọn Spring Batch khi job có nhiều steps, restart/resume, retry/skip, partitioning, monitoring và pipelines phức tạp. Với import vài nghìn rows đơn giản, một service transaction-per-chunk có thể đủ.

## 28. Đo hiệu năng theo mục tiêu end-to-end

### 28.1. Phải đo flush và commit

Nếu chỉ đo vòng for gọi em.persist, ta có thể bỏ qua phần SQL đắt nhất đang chờ flush/commit.

~~~java
long start = System.nanoTime();

for (ProductInput input : chunk) {
    em.persist(new Product(input.sku(), input.price()));
}

em.flush();

long elapsedNanos = System.nanoTime() - start;
double elapsedMillis = elapsedNanos / 1_000_000.0;
~~~

Đoạn trên đo persist + flush, **không đo commit** nếu chưa gọi tx.commit. Khi mục tiêu là throughput end-to-end, cần đo commit và checkpoint tại transaction boundary.

### 28.2. Không log một message cho mỗi row

~~~java
log.info("Persisted {}", product.getSku());
~~~

trong vòng lặp hàng triệu rows có thể gây I/O overhead, tăng log volume và lộ dữ liệu. Thay bằng summary theo chunk:
- Rows processed/committed;
- Duration;
- Error category;
- Import run/chunk IDs.

### 28.3. Benchmark cần dữ liệu đại diện

- JVM/JIT warmup;
- Connection pool;
- DB cache nóng/lạnh;
- Index sizes;
- Uniqueness distribution;
- Entity graph/cascades;
- Concurrent requests;
- Realistic transaction durations.

Không so benchmark empty DB với production nhiều indexes/triggers rồi kết luận throughput giống nhau.

### 28.4. Throughput chưa đủ

Một cấu hình rows/sec cao hơn nhưng P99 chunk latency, lock wait hoặc connection pool pressure rất lớn có thể không phù hợp hệ thống online. Dùng nhiều metrics và SLA để quyết định.

## 29. Observability và Hibernate statistics

### 29.1. Quan sát entity count và flush behavior

Khi dùng Hibernate, có thể bật thống kê theo cấu hình/provider version, ví dụ property thường gặp:

~~~properties
hibernate.generate_statistics=true
~~~

Trong Spring Boot:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Số metric được expose và overhead phụ thuộc Hibernate version. Nên dùng trong development/benchmark hoặc bật có kiểm soát ở production.

### 29.2. Những tín hiệu hữu ích

- Entity inserts/updates/deletes;
- Flush count;
- JDBC prepared statement count;
- JDBC batching execution/size nếu instrumentation có;
- Second-level cache hit/miss khi liên quan;
- Query execution statistics;
- Persistence context managed entity count qua API provider nếu có;
- Transaction commits/rollbacks;
- GC heap và allocation;
- DB CPU/I/O/WAL/lock wait.

**Statement count không tự bằng network round-trip count**: JDBC batching và driver có thể gộp statements.

### 29.3. Flush count không bằng commit count

Một transaction gồm 10 chunks có thể gọi em.flush 10 lần nhưng **chỉ commit một lần**. Đừng suy số commits từ flush metrics.

### 29.4. N+1 query là bottleneck riêng

Nếu batch cần category name, SQL SELECT count có thể tăng tỉ lệ với số Product. Flush/clear không tự sửa N+1; thậm chí clear thường xuyên có thể khiến cùng Category được load lại nhiều lần. Tối ưu query shape/preload/batch fetching khi phù hợp.

### 29.5. Metrics label cần cardinality hữu hạn

Không đưa raw SKU, Product ID hoặc SQL statement chứa parameters vào metric labels. Dùng operation, error category, chunk status và transaction policy.

## 30. Phục hồi transaction-per-chunk

### 30.1. Chunk thứ N thất bại

Giả sử:
- Chunks 1–10 đã commit;
- Chunk 11 lỗi;
- Chunk 12 chưa chạy.

Quy trình:
1. Giữ trạng thái 1–10 là committed;
2. Rollback chunk 11 và đóng/bỏ context lỗi;
3. Ghi error category và source offset;
4. Quyết định quarantine, sửa input hoặc retry;
5. Với retry, mở transaction/context mới;
6. Xác minh idempotency nếu commit outcome có thể unknown;
7. Tiếp tục từ checkpoint hợp lệ.

Không dùng em.clear để “rollback” những chunks đã commit. Để sửa dữ liệu đã commit cần nghiệp vụ **compensation/reversal** riêng.

### 30.2. Skip row invalid không giống retry DB transient

- Invalid CSV row → quarantine theo policy;
- Duplicate SKU → skip, update hay reject tùy contract;
- Missing FK → có thể cần import parent trước;
- Optimistic conflict → reload/resolve;
- Deadlock → retry transaction mới có giới hạn;
- Connection fail → cần phân biệt commit outcome.

Catch mọi Exception rồi tiếp tục có thể biến sự cố DB thành báo cáo “đã hoàn tất” sai.

### 30.3. Retry phải bao toàn transaction

~~~text
Attempt #1:
    BEGIN transaction A
    writeChunk(chunk)
    FLUSH
    DEADLOCK
    ROLLBACK

Backoff outside transaction

Attempt #2:
    BEGIN transaction B (mới)
    read current state nếu update
    writeChunk(chunk) idempotently
    FLUSH
    COMMIT
~~~

Không tái sử dụng persistence context cũ sau flush failure.

### 30.4. Cancellation/shutdown

Khi job bị cancel:
- Ngừng nhận chunks mới;
- Hoàn tất hoặc rollback transaction hiện tại theo policy;
- Đóng input/output streams;
- Giải phóng EntityManager/connection;
- Ghi checkpoint durable;
- Không đánh dấu running chunk là committed trước commit;
- Cho phép resume bằng idempotency.

## 31. Xóa entities theo khối

Xóa từng Product khi cần JPA cascade và lifecycle callbacks:

~~~java
long processed = 0;

for (Long id : productIds) {
    Product product = em.find(Product.class, id);

    if (product != null) {
        em.remove(product);
    }

    processed++;

    if (processed % chunkSize == 0) {
        em.flush();
        em.clear();
    }
}

em.flush();
em.clear();
~~~

Điều kiện:
- EntityManager nằm trong transaction write;
- em.remove yêu cầu managed entity;
- FK constraints có thể chặn DELETE;
- CascadeType.REMOVE/orphanRemoval có thể tạo nhiều SQL;
- @PreRemove có thể chạy;
- Clear có thể detach unrelated managed objects;
- Một transaction dài vẫn giữ locks/rollback scope.

Nếu chỉ xóa hàng loạt theo predicate và không cần callbacks/cascades, bulk JPQL DELETE có thể nhanh hơn, nhưng semantics khác em.remove từng entity.

## 32. Streaming một file lớn vào chunk writer

Một skeleton application đọc file thành từng chunk, không giữ toàn bộ input trong memory:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public long importCsv(
        Path file,
        int chunkSize,
        ProductChunkWriter writer) throws IOException {

    if (chunkSize <= 0) {
        throw new IllegalArgumentException("chunkSize");
    }

    long committed = 0;

    try (BufferedReader reader =
             Files.newBufferedReader(file)) {

        List<ProductInput> chunk = new ArrayList<>(chunkSize);
        String line;

        while ((line = reader.readLine()) != null) {
            ProductInput input = parseCsvLine(line);
            // validateInput(input) nếu cần.

            chunk.add(input);

            if (chunk.size() == chunkSize) {
                committed += writer.write(chunk);
                chunk.clear();
            }
        }

        if (!chunk.isEmpty()) {
            committed += writer.write(chunk);
        }
    }

    return committed;
}
~~~

**Giới hạn:**
- Đây là skeleton. Cần implementation parseCsvLine thật với quotes/escapes/headers/encoding. Không dùng line.split(",") như CSV parser tổng quát.
- writer.write cần là chunk writer có **transaction boundary rõ**, ví dụ Spring bean @Transactional được gọi qua proxy.
- writer phải xử lý chunk **đồng bộ** và không giữ reference đến List sau method return. Nếu writer bất đồng bộ, chunk.clear() sẽ thay đổi buffer khi worker vẫn cần đọc; phải chuyển ownership/copy immutable.
- Nếu writer fail, committed chỉ chứa các chunks đã trả thành công; muốn resume sau crash cần checkpoint/idempotency durable.
- File import phải có source version/checksum nếu offset được dùng cho restart.

## 33. Integration tests: kiểm chứng flush/clear và transaction

Một bài kiểm thử trên database thật giúp xác minh semantics của provider, không chỉ đọc code.

### 33.1. Cấu hình cơ sở

- PostgreSQL/Testcontainers hoặc DB giống production;
- Jakarta Persistence provider/driver tương thích;
- Migration products + sequence phù hợp;
- Product entity có UNIQUE SKU và @Version;
- Resource-local EntityManagerFactory hoặc Spring transaction environment rõ;
- Fixture được tạo và cleanup;
- Test dùng transaction mới để kiểm tra commit;
- Không chạy trên database production.

### 33.2. Test clear làm entity detached

~~~java
@Test
void clearDetachesManagedProducts() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Product p = new Product(
            "SKU-" + UUID.randomUUID(),
            new BigDecimal("100.00")
        );

        em.persist(p);
        assertTrue(em.contains(p));

        em.flush();
        em.clear();

        assertFalse(em.contains(p));
        tx.rollback();

    } finally {
        if (tx.isActive()) {
            tx.rollback();
        }
        em.close();
    }
}
~~~

Test xác nhận **managed → detached**. Không suy từ assertFalse rằng Java object đã được GC hoặc L2 cache bị xóa.

### 33.3. Test flush không phải commit

~~~java
@Test
void flushThenRollbackDoesNotCommitProduct() {
    String sku = "SKU-" + UUID.randomUUID();

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        em.persist(
            new Product(sku, new BigDecimal("100.00"))
        );
        em.flush();

        tx.rollback();
    } finally {
        if (tx.isActive()) {
            tx.rollback();
        }
        em.close();
    }

    EntityManager check = emf.createEntityManager();
    try {
        Long count = check.createQuery(
            """
            select count(p)
            from Product p
            where p.sku = :sku
            """,
            Long.class
        )
        .setParameter("sku", sku)
        .getSingleResult();

        assertEquals(0L, count);
    } finally {
        check.close();
    }
}
~~~

Đây là bài test phân biệt flush vs commit. Query kiểm tra dùng EntityManager mới sau rollback.

### 33.4. Test chunk cuối không chia hết

Ví dụ 1.050 rows, chunkSize=200:
- 5 chunks đủ 200;
- Chunk cuối 50;
- Kết quả phải có đủ 1.050 rows sau commit.

Nếu code quên final em.flush/commit hoặc bỏ chunk cuối trong caller, test sẽ phát hiện. Không chỉ test input có số lượng chia hết chunkSize.

### 33.5. Test all-or-nothing khi một transaction

Một batch 100 Products có SKU trùng ở row 75. Với **một transaction cho toàn file**:
1. Bắt exception từ flush/commit;
2. Rollback;
3. Dùng context mới kiểm tra không có bất kỳ imported Product của batch;
4. Kiểm tra các rows trước khi import vẫn còn.

### 33.6. Test partial success transaction-per-chunk

Tạo:
- Chunk#1: 100 Product hợp lệ;
- Chunk#2: chứa một SKU trùng;
- Chunk#3: chưa chạy.

Kỳ vọng:
- Chunk#1 vẫn có thể đã commit;
- Chunk#2 rollback;
- Chunk#3 chưa có rows;
- Job status phản ánh partial success.

### 33.7. Test clear không cứu pending changes

Một test có entity đang managed và đã sửa nhưng **chưa flush**, gọi em.clear rồi commit. Xác minh database **không nhận thay đổi đã bị detached** trong một context/flush mode được kiểm soát.

Đừng dùng test với IDENTITY INSERT đã chạy ngay rồi kết luận clear “không ảnh hưởng pending persist” nói chung: IDENTITY có thể tạo INSERT trước clear. Nên dùng một entity managed hiện hữu, sửa field rồi clear không flush.

### 33.8. Test dirty checking qua nhiều chunks

- Tạo 1.100 Products;
- Đọc IDs theo keyset 200;
- Load từng Product, changePrice;
- flush/clear sau mỗi page;
- Commit;
- Query database một lần nữa để xác minh tất cả IDs được thay đổi đúng.

Test cần dùng input ổn định và upperBound rõ để tránh concurrent rows.

### 33.9. Test không sửa detached entities sau clear

Một List có 1.000 Products được getResultList; sau khi clear ở item thứ 200, các objects còn lại detached. Test có thể chứng minh sửa chúng sau clear **không tự tạo UPDATE**. Đây là regression test cho lỗi kết hợp whole-result-list với chunk clear.

### 33.10. Test @Version conflict

- EM A load Product#42;
- EM B load và commit thay đổi version;
- A changePrice;
- A flush → optimistic conflict;
- Rollback A;
- EM C đọc DB và thấy update của B còn nguyên.

Test sử dụng hai transactions/connections độc lập, không chia sẻ một EntityManager giữa threads.

### 33.11. Test SQL batching thực tế

Bật Hibernate JDBC batch config và statistics/JDBC instrumentation phù hợp:
- Đếm INSERT statements;
- Đếm batch executions/size nếu instrumentation hỗ trợ;
- So với batch disabled;
- Kiểm tra IDENTITY vs SEQUENCE;
- Đo throughput/latency và heap.

Không assert “một flush = một JDBC batch” vì không phải JPA contract.

### 33.12. Test Spring @Transactional per chunk

Gọi coordinator → ProductChunkWriter bean:
1. Chunk 1 commit;
2. Chunk 2 fail;
3. Query DB bằng transaction khác;
4. Xác nhận chunk 1 đã commit nhưng chunk 2 không;
5. Kiểm tra @Transactional thật sự đi qua proxy (không self-invocation).

## 34. Bảng xử lý sự cố thực tế

| Triệu chứng | Nguyên nhân có thể | Hành động trước tiên |
|---|---|---|
| Heap tăng đều khi import | L1 context lớn | Flush/clear theo chunk |
| Heap vẫn tăng dù clear | List DTO/entity giữ references | Streaming input, bounded buffer |
| OutOfMemory sau getResultList | Query nạp toàn bảng | ID/keyset paging, projection |
| SQL quá nhiều so với rows | N+1 / cascade / no batching | JDBC/Hibernate statistics |
| Flush chậm ở cuối file | Context/action queue lớn | Giảm chunk; đo dirty check |
| SaveAll chậm | Merge, identity generator, no batching | Kiểm tra effective SQL/ID |
| INSERT mỗi row dù jdbc.batch_size=50 | IDENTITY/statement shape/config | Đo JDBC batch activity |
| Update 500 entities nhưng chỉ vài SQL | Dirty checking không thấy field thay đổi hoặc batch | Kiểm tra thực tế DB/SQL |
| Transaction lock dài | Một transaction cho toàn file | Xem commit-per-chunk nếu business cho phép |
| Chunk đầu đã commit dù job fail | Transaction-per-chunk | Báo partial success/checkpoint |
| Một lỗi row rollback toàn file | Single transaction | Chọn atomicity policy |
| Clear xong không thấy UPDATE | Clear trước flush hoặc sửa detached | Flush trước clear / reload managed |
| Lazy loading fail sau clear | Entity detached | Đọc dữ liệu cần thiết trước clear |
| Row bị bỏ sót | OFFSET với predicate thay đổi | Keyset/cursor/ID staging |
| Query result stream tốn heap | Provider materializes hoặc L1 giữ entities | Test provider, ID paging |
| Batch update báo optimistic conflict | @Version stale | Rollback/reload/resolution |
| Database báo FK violation | Parent/child order hoặc mapping sai | Kiểm tra graph/FK constraints |
| Retry vẫn fail cùng SKU | Permanent UNIQUE violation | Dedupe hoặc business conflict |
| Deadlock tăng khi thêm workers | Lock ordering, contention | Partition, fixed lock order |
| Hết connections | Worker count > pool capacity | Bounded concurrency |
| Import xong thiếu chunk cuối | Quên final flush/write | Test remainder chunk |
| Event phát dù transaction rollback | Side effect trước commit | Outbox/after-commit |
| Trùng dữ liệu sau restart | Thiếu checkpoint/idempotency | Unique keys/run ID |
| SQL từ ORM chưa commit nhưng UI thấy khác | Transaction visibility/cache | Phân biệt flush và commit |
| Hibernate metrics nhiều flush | Queries auto-flush hoặc flush per row | Query pattern, chunk strategy |
| 500 Product tạo 4.000 statements | Cascades/secondary/join tables | Đo SQL per aggregate |
| Test H2 tốt nhưng PostgreSQL chậm | DB dialect/driver/indexes khác | Benchmark trên target DB |
| Import pause dài mỗi vài giây | GC hoặc DB flush/checkpoint | Correlate GC/DB metrics |
| Thay chunkSize không giúp | Bottleneck DB index/N+1/network | Profiling end-to-end |

## 35. Bài tập thực hành

Các bài tập sử dụng Product/ProductInput, EntityManager và những mẫu transaction đã học. Khi trả lời, phải chỉ rõ **managed state, SQL flush, transaction commit và phạm vi rollback**. Không đánh đồng các khái niệm này.

### Bài 1. Giải thích flush

Trong một transaction:

~~~java
em.persist(product);
em.flush();
tx.rollback();
~~~

Product có được lưu vĩnh viễn không? Vì sao flush không phải commit?

### Bài 2. Giải thích clear

~~~java
Product p = em.find(Product.class, id);
em.clear();
System.out.println(em.contains(p));
~~~

Kết quả expected là gì? Object p có bị xóa khỏi JVM heap ngay không?

### Bài 3. Thứ tự flush/clear

So sánh:

~~~java
em.persist(p);
em.flush();
em.clear();
~~~

với:

~~~java
em.persist(p);
em.clear();
em.flush();
~~~

Khác biệt nào liên quan pending changes? Có trường hợp SQL INSERT đã chạy sớm vì IDENTITY không?

### Bài 4. L1 cache và memory

Một job persist 200.000 Product không clear. Những structures nào provider có thể giữ? Tại sao tắt L2 cache không giải quyết hết memory growth?

### Bài 5. Chunk size bằng 0

Trong code:

~~~java
if (count % chunkSize == 0) {
    em.flush();
    em.clear();
}
~~~

Điều gì xảy ra nếu chunkSize=0? Đề xuất API validation trước transaction.

### Bài 6. Chunk cuối

Import 1.050 rows, chunkSize=200. Sau bao nhiêu full chunks sẽ có remainder? Nếu quên flush/commit phần cuối, chuyện gì có thể xảy ra?

### Bài 7. Một transaction cho toàn file

Mô tả import 1.000 Product với flush/clear mỗi 100 nhưng chỉ một commit cuối. Nếu row 999 bị database CHECK từ chối, 900 rows trước có còn committed không?

### Bài 8. Transaction-per-chunk

Import 1.000 rows với transaction mỗi 100. Chunk thứ 7 lỗi. Hãy xác định những chunks nào có thể đã commit và cách báo partial progress.

### Bài 9. Managed state sau clear

~~~java
Product p = em.find(Product.class, id);
em.clear();
p.changePrice(new BigDecimal("200"));
tx.commit();
~~~

Có chắc SQL UPDATE được sinh không? Cần làm gì để cập nhật entity đúng cách?

### Bài 10. List giữ memory

Code persist theo chunk và gọi clear nhưng vẫn thêm mọi Product vào một List allProducts. Vì sao heap vẫn có thể tăng? Sửa output contract của importer như thế nào?

### Bài 11. Flush theo từng row

Một developer gọi em.flush sau mỗi persist. Tại sao có thể làm tăng SQL/network overhead? Trong tình huống nào xác nhận mỗi row sớm là yêu cầu nghiệp vụ cần cân nhắc?

### Bài 12. Flush mode AUTO

Trong vòng persist, developer gọi query existsBySku với mỗi input. Tại sao query có thể kích hoạt auto-flush và ảnh hưởng throughput? Có thể thay bằng pre-validation theo chunk và DB UNIQUE thế nào?

### Bài 13. JDBC batch vs ORM chunk

Giả sử:
- chunkSize=500;
- hibernate.jdbc.batch_size=50;
- transactionSize=5.000.

Hãy mô tả số lần flush/clear và commit về mặt cấu trúc. Có thể kết luận chính xác số JDBC round-trips không?

### Bài 14. IDENTITY và SEQUENCE

So sánh khả năng JDBC INSERT batching khi entity dùng IDENTITY và khi dùng SEQUENCE pooled. Vì sao không nên đổi primary key strategy trên production chỉ để chạy nhanh hơn mà không kiểm tra migration?

### Bài 15. allocationSize

Entity có @SequenceGenerator(allocationSize=50), DB sequence lại có increment không phù hợp với provider optimizer. Những lỗi/hiện tượng nào có thể xảy ra? Cần xác nhận cấu hình như thế nào?

### Bài 16. saveAll

~~~java
repository.saveAll(products);
~~~

Có chắc đây là một SQL multi-values INSERT không? Nếu products chứa một triệu entity objects, memory pressure có giảm do API name saveAll không?

### Bài 17. saveAndFlush

Một loop gọi repository.saveAndFlush sau mỗi row. So sánh với em.persist và flush/clear theo chunk. saveAndFlush có tự clear không?

### Bài 18. Spring self-invocation

Một class có method start() gọi this.writeChunk(), trong khi writeChunk có @Transactional. Tại sao proxy-based transaction có thể không kích hoạt đúng? Đề xuất tách bean hoặc TransactionTemplate.

### Bài 19. @Transactional propagation

Coordinator mở outer transaction rồi gọi chunk writer @Transactional(REQUIRED). Chunk writer có commit riêng không? Làm thế nào bảo đảm mỗi chunk là một transaction thực sự?

### Bài 20. REQUIRES_NEW và connection pool

Một service có outer transaction, gọi nhiều REQUIRES_NEW chunks. Tại sao có thể cần thêm DB connections và gây pool starvation? Có phương án tổ chức coordinator ngoài transaction không?

### Bài 21. Transaction readOnly

Nếu importProducts được annotate @Transactional(readOnly=true), những vấn đề nào có thể xảy ra? Có nên dựa vào em.flush để vượt qua DB read-only transaction không?

### Bài 22. Nạp toàn bảng

~~~java
List<Product> products =
    em.createQuery("select p from Product p", Product.class)
      .getResultList();
~~~

Với 2 triệu rows, em.clear trong vòng xử lý có giải quyết peak memory đã tiêu tốn khi getResultList không? Đề xuất ID paging.

### Bài 23. Clear giữa một ResultList

Code nạp List<Product> 2.000 rows, sửa 200 rows rồi em.clear. Sau đó tiếp tục sửa 1.800 Products còn trong List. Vì sao những thay đổi sau đó có thể không được lưu?

### Bài 24. OFFSET và predicate thay đổi

Job chọn WHERE active=true rồi deactivate rows đã xử lý. Nếu dùng OFFSET 0, 500, 1.000, có thể bỏ sót rows thế nào? Viết query keyset dùng id > :lastId.

### Bài 25. Keyset và concurrent writes

Khi dùng id > lastId, một transaction khác INSERT Product với ID lớn hơn upperBound hoặc DELETE một row ở giữa. Tác động lên tập dữ liệu job sẽ xử lý là gì? Có cần snapshot/upperBound/staging không?

### Bài 26. Query streams

getResultStream có luôn giữ heap O(1) không? Những yếu tố nào quyết định driver fetch size, materialization và persistence context growth? Vì sao stream+clear trong cùng cursor cần test theo provider?

### Bài 27. ManyToOne reference qua chunks

Một Category đã tồn tại được dùng cho hàng nghìn Products. Nếu giữ Category managed reference từ chunk trước rồi em.clear, trạng thái của reference thay đổi thế nào? Có thể dùng getReference lại trong chunk mới không?

### Bài 28. Cascade graph lớn

Mỗi Order có 1.000 OrderLine; chunkSize=500 Orders. Có bao nhiêu entity instances có thể được persist trong một chunk nếu tất cả lines được cascade? Điều đó gợi ý gì về sizing theo aggregate complexity?

### Bài 29. Lazy loading sau clear

Một Product có Category lazy. Sau clear, gọi product.getCategory().getName() có thể gây vấn đề gì? Đề xuất DTO/projection hoặc truy cập trước clear khi cần.

### Bài 30. @Version conflict

Batch A load Product version=5. API B commit version=6. Batch A flush gặp OptimisticLockException. Có nên bắt và retry cùng oldDetachedProduct trong transaction hiện tại không? Đề xuất workflow reload/resolution.

### Bài 31. External SQL không tăng version

Một ETL cập nhật Product.price qua SQL nhưng không tăng version. Optimistic locking của JPA có phát hiện mọi xung đột không? Cần consistency contract gì?

### Bài 32. Bulk UPDATE so với entity batching

Yêu cầu deactivate tất cả Products active=true. So sánh:
- Load từng Product, gọi deactivate(), flush/clear;
- JPQL bulk UPDATE.

Phương án nào cần @PreUpdate/cascade/versioning semantics? Phương án nào thường giảm Java heap hơn?

### Bài 33. Bulk DML và L1 stale

Trong context đã managed Product active=true, chạy JPQL bulk UPDATE active=false. Java object Product có tự chuyển active=false không? Cần refresh/clear gì?

### Bài 34. Bulk DELETE

em.remove từng entity khác JPQL DELETE FROM Product thế nào về callbacks, cascades, FK và state của managed entities?

### Bài 35. JDBC batch thực tế

Hệ thống đặt hibernate.jdbc.batch_size=50 nhưng logs cho thấy INSERT từng row. Nêu các nguyên nhân: IDENTITY, SQL shapes, config/dialect/driver, cascades. Cần đo bằng metrics nào?

### Bài 36. N+1

Batch cập nhật Products và lấy category name qua lazy getter cho từng Product. Số SELECT tăng theo số rows. Flush/clear có sửa N+1 không? Đề xuất projection/entity graph/batch fetching.

### Bài 37. Multiple workers

Dùng 16 worker threads nhưng pool chỉ có 8 connections. Hệ thống có thể gặp hiện tượng gì? Có nên chia sẻ một EntityManager giữa 16 threads không?

### Bài 38. Deadlock và lock ordering

Worker A cập nhật Product#1 rồi #2; Worker B cập nhật #2 rồi #1. Hãy vẽ wait-for cycle và đề xuất thứ tự ID ổn định để giảm deadlock.

### Bài 39. Bisect chunk hỏng

Một chunk chứa 100 Products fail do trùng SKU trong chính chunk. Nếu chia đôi, có thể xảy ra trường hợp hai nửa riêng lẻ đều pass nhưng kết hợp fail không? Vì sao bisect không luôn chỉ ra một bad row độc lập?

### Bài 40. Quarantine và retry

Phân loại:
- Invalid price=-10;
- Duplicate SKU;
- Deadlock;
- Connection loss trong commit;
- Missing foreign key.

Trường hợp nào quarantine, trường hợp nào retry bounded, trường hợp nào cần reconciliation?

### Bài 41. Partial commit và checkpoint

Chunk 1 commit, process crash trước khi ghi checkpoint ở hệ khác. Lần resume có thể xử lý lại chunk 1. Hãy thiết kế runId/chunkId UNIQUE và DB transaction checkpoint để giảm duplicate.

### Bài 42. Source file thay đổi

Checkpoint lưu offset 10.000 nhưng file import được chỉnh sửa và thêm 5 rows ở đầu. Khi resume từ offset cũ, vấn đề gì xảy ra? Cần checksum/source version thế nào?

### Bài 43. Outbox

Batch persist 500 Products và publish ProductImported events trước COMMIT. Nếu COMMIT fail, external consumers sẽ quan sát điều gì? Đề xuất outbox/after-commit.

### Bài 44. Memory benchmark

Thiết kế benchmark so:
- No flush/clear;
- Chunk=100;
- Chunk=500;
- Chunk=1.000.

Đo heap live set, GC, throughput, flush count, SQL count và DB lock wait. Vì sao không chỉ đo thời gian vòng for persist?

### Bài 45. Test flush rollback

Viết test resource-local:
1. BEGIN;
2. em.persist Product;
3. em.flush();
4. ROLLBACK;
5. EM mới query count by SKU;
6. Assert count=0.

Nêu ý nghĩa của test.

### Bài 46. Test clear detached

Persist Product trong transaction, em.flush(), em.clear(). Assert em.contains(product)==false. Tại sao test này không chứng minh JVM đã giải phóng memory?

### Bài 47. Test remainder chunk

Import 1.051 rows với chunkSize=200. Viết expected count sau commit; tại sao phải test một số không chia hết chunkSize?

### Bài 48. Test all-or-nothing

Tạo 100 rows, row thứ 75 trùng SKU. Trong single transaction, verify không có imported rows sau rollback. Trong transaction-per-chunk, verify các chunks trước có thể còn. Vì sao hai tests phải có expectations khác?

### Bài 49. Test optimistic conflict

Dùng hai EntityManagers và @Version, commit B trước khi A flush. Bảo đảm rollback A và verify DB giữ state của B. Vì sao không dùng cùng EntityManager cho hai threads?

### Bài 50. Thiết kế pipeline hoàn chỉnh

Xây kiến trúc import Product 1 triệu rows:
1. Streaming parser, validation và bounded queue;
2. Configurable chunkSize;
3. JPA EntityManager/transaction per chunk;
4. JDBC batch config và ID strategy tương thích;
5. Đảm bảo flush trước clear nếu giữ context qua nhiều chunks;
6. Commit/checkpoint và idempotency;
7. Quarantine input invalid;
8. Retry bounded cho deadlock/serialization;
9. Metrics heap/GC/SQL/throughput/DB lock;
10. Integration tests trên database thực;
11. Đảm bảo quyền tenant và concurrency;
12. Recovery sau crash và commit outcome unknown.

Giải thích các tradeoffs chính thay vì chỉ viết một vòng for với em.flush/em.clear.

## 36. Checklist triển khai xử lý nhiều entity theo khối

### 36.1. Tính đúng đắn của flush/clear

1. **Có hiểu em.flush() gửi pending SQL nhưng không COMMIT không?**
2. **Có hiểu em.clear() detach toàn bộ managed entities không?**
3. **Có luôn flush trước clear khi muốn giữ pending changes không?**
4. **Nếu flush thất bại, có rollback thay vì clear rồi tiếp tục không?**
5. **Có tránh sửa detached entities sau clear và chờ dirty checking không?**
6. **Có biết @Version/optimistic locks có thể fail tại flush/commit không?**
7. **Có tránh gọi clear trong một service chứa unrelated managed entities không?**
8. **Có hiểu EntityManager L1 khác L2/Redis cache không?**
9. **Có xử lý lazy association trước khi entity bị detach không?**
10. **Có tránh dùng em.persist cho detached entity đã tồn tại không?**

### 36.2. Ranh giới giao dịch

11. **Batch có cần all-or-nothing toàn file hay partial success theo chunk không?**
12. **Có phân biệt chunkSize, JDBC batch size và transaction size không?**
13. **Có biết 10 lần flush vẫn có thể là 1 transaction không?**
14. **Nếu commit-per-chunk, job có báo partial progress chính xác không?**
15. **Có tránh dùng em.getTransaction() trong JTA/Spring-managed context không?**
16. **Có đảm bảo @Transactional thật sự kích hoạt qua Spring proxy không?**
17. **Có tránh self-invocation làm sai transaction boundaries không?**
18. **Có cân nhắc REQUIRES_NEW/pool connections trước khi áp dụng không?**
19. **Có tránh @Transactional(readOnly=true) cho write job không?**
20. **Có xác nhận transaction timeout và lock duration phù hợp không?**
21. **Có biết em.clear không giải phóng DB locks khi transaction còn mở không?**
22. **Có rollback và đóng/loại context sau persistence failure không?**
23. **Có kiểm tra commit outcome unknown khi mất connection lúc COMMIT không?**

### 36.3. Persistence context và bộ nhớ

24. **Có giới hạn managed entities trước mỗi clear không?**
25. **Có tránh getResultList toàn bảng rồi mới clear không?**
26. **Có dùng stream/chunked input thay vì parse toàn file vào List không?**
27. **Có tránh giữ allProducts/allResults trong một collection lớn không?**
28. **Có tính cả cascade children khi chọn chunk size không?**
29. **Có xác minh references từ chunk cũ đã detached chưa?**
30. **Có kiểm soát Input DTO buffers và bounded queues không?**
31. **Có đo live heap, GC và allocation thay vì chỉ RSS không?**
32. **Có đóng các ResultSet/Streams/readers/resources đúng lifecycle không?**
33. **Có tránh cho nhiều threads dùng chung EntityManager không?**

### 36.4. JDBC/ORM performance

34. **Hibernate JDBC batching đã được bật và đo thực sự chưa?**
35. **Có phân biệt flush count với JDBC batch executions không?**
36. **Có kiểm tra IDENTITY đang cản batching không?**
37. **Nếu dùng SEQUENCE pooled, optimizer/DDL increment tương thích chưa?**
38. **Có kiểm tra số SQL statements trên mỗi aggregate không?**
39. **Có quan sát order_inserts/order_updates trên dataset thực không?**
40. **Có xem SQL shapes khác nhau làm giảm batching không?**
41. **Có tránh saveAndFlush mỗi row khi không cần không?**
42. **Có hiểu saveAll không tự là một SQL multi-values INSERT không?**
43. **Có đo N+1 queries và repeated lazy loads không?**
44. **Có cân nhắc bulk JPQL/native SQL nếu mọi rows nhận cùng update không?**
45. **Nếu bulk DML, có xử lý L1 stale, @Version/callbacks/cascades không?**
46. **Có đo throughput, P99 chunk latency, DB CPU/I/O/WAL và locks không?**
47. **Có benchmark nhiều chunk sizes trên database giống production không?**

### 36.5. Đọc/quét dữ liệu

48. **Có dùng keyset pagination khi predicate thay đổi trong lúc update không?**
49. **Có dùng order by khóa ổn định và cập nhật lastId đúng không?**
50. **Có upperBound/snapshot/staging khi cần cố định tập rows không?**
51. **Có tránh OFFSET trên tập kết quả đang co lại không?**
52. **Có tránh clear giữa whole-result-list rồi sửa các detached objects còn lại không?**
53. **Nếu dùng getResultStream, có kiểm chứng provider/driver fetch behavior không?**
54. **Có tránh fetch join collections với pagination thiếu kiểm soát không?**
55. **Có quản lý concurrent INSERT/UPDATE/DELETE làm thay đổi phạm vi job không?**

### 36.6. Associations, concurrency và correctness

56. **Có hoàn tất aggregate graph trước flush/clear không?**
57. **Có dùng managed references mới ở chunk kế tiếp nếu association cần không?**
58. **Có kiểm tra CascadeType.PERSIST/REMOVE và orphanRemoval effects không?**
59. **Có xử lý FK constraints và thứ tự parent/child imports không?**
60. **Có tránh external side effects trước DB commit không?**
61. **Có @Version/locking policy cho concurrent writers không?**
62. **Có giữ thứ tự xử lý per entity key khi parallel hóa không?**
63. **Có partition workload tránh trùng keys giữa workers không?**
64. **Có giới hạn worker count theo pool/DB capacity không?**
65. **Có policy lock ordering và bounded deadlock retry không?**

### 36.7. Resume, lỗi và vận hành

66. **Có validation trước persistence cho input malformed không?**
67. **Có phân loại permanent vs transient failures không?**
68. **Có quarantine và reprocess policy cho bad rows không?**
69. **Có rollback chunk đúng nếu JDBC BatchUpdateException xuất hiện không?**
70. **Có tránh suy committed count từ update counts khi chưa COMMIT không?**
71. **Có importRunId/chunkId idempotency keys không?**
72. **Có checkpoint durable gắn với transaction khi có thể không?**
73. **Có source file version/checksum để resume đúng offset không?**
74. **Có reconciliation nếu commit outcome chưa biết không?**
75. **Có outbox hoặc after-commit cho events/notifications không?**
76. **Có metrics/error budget/correlation ID cho mỗi import run không?**
77. **Có log summary mỗi chunk thay vì log từng entity không?**
78. **Có chuẩn bị graceful cancellation/shutdown và resume không?**

### 36.8. Kiểm thử bắt buộc theo mục tiêu

79. **Có test em.flush rồi rollback không tạo committed row không?**
80. **Có test em.clear khiến em.contains(entity)==false không?**
81. **Có test sửa detached entity sau clear không tạo dirty update không?**
82. **Có test input count không chia hết chunkSize không?**
83. **Có test all-or-nothing một transaction khi row cuối fail không?**
84. **Có test partial success transaction-per-chunk không?**
85. **Có test database UNIQUE/FK/CHECK failure thực tế không?**
86. **Có test keyset paging không bỏ sót khi sửa predicate không?**
87. **Có test @Version conflict bằng hai EntityManagers không?**
88. **Có test query/cascade/association graphs thay vì chỉ Product đơn giản không?**
89. **Có test SQL batching thực bằng JDBC/provider instrumentation không?**
90. **Có test Spring proxy transaction boundary, không self-invocation không?**
91. **Có test retry/idempotency sau crash/re-delivery không?**
92. **Có test performance trên DB/driver/provider gần production không?**

## 37. Bảng tra cứu thao tác nhanh

| Nhiệm vụ | Lựa chọn thường phù hợp | Cảnh báo |
|---|---|---|
| Persist nhiều entities mới, cần JPA lifecycle | Chunked em.persist + flush/clear | Theo dõi context, transaction |
| Update từng entity với business logic riêng | Page IDs → load managed → change → flush/clear | @Version và concurrency |
| Delete từng entity cần callbacks/cascade | em.remove managed theo chunk | FK, orphanRemoval, lock duration |
| Cùng một update trên nhiều rows | JPQL bulk DML hoặc SQL | Bỏ qua per-entity callbacks/version auto handling |
| Import hàng triệu rows chỉ cần raw data | JDBC batch/COPY/staging | Tự quản validation/audit/version |
| Cần all-or-nothing toàn file | Một transaction, flush/clear nhiều chunks | Log/lock/rollback pressure |
| Cho phép partial success và resume | Transaction-per-chunk | Checkpoint + idempotency |
| Java heap tăng do managed entities | em.flush rồi em.clear | Đừng giữ references ở List |
| Java heap tăng do input list | Streaming parser + bounded chunks | Clear không giải phóng List |
| SQL INSERT không batch | Kiểm tra Hibernate property/ID generator | IDENTITY thường hạn chế |
| saveAll chậm | Đo persist/merge/SQL/transaction | Không phải tự động bulk SQL |
| Query per row/N+1 | Projection/fetch strategy | Flush/clear không sửa |
| Offset pagination skip rows | Keyset paging/staging IDs | Concurrent changes cần policy |
| Spring annotation không commit mỗi chunk | Separate bean/TransactionTemplate | Tránh self-invocation/outer tx |
| Flush exception | Rollback/context mới | Clear không phục hồi tx lỗi |
| Optimistic conflict | Reload/resolve/retry policy | Không retry stale snapshot y nguyên |
| Deadlock/serialization | Bounded retry whole transaction | Không retry trong tx cũ |
| Commit outcome unknown | Reconcile via idempotency key | Không blind retry |
| Nhiều workers tranh DB | Bounded concurrency/partitioning | EM không thread-safe |

## 38. Cây quyết định lựa chọn chiến lược

~~~text
Cần xử lý rất nhiều bản ghi
             |
             v
  Mỗi entity cần domain/cascade/callback?
           /                    \
         Không                  Có
          |                      |
          v                      v
  Bulk JPQL/SQL/JDBC?      JPA EntityManager
          |                      |
          |                      v
          |             Dữ liệu đầu vào đủ nhỏ?
          |                   /       \
          |                 Có        Không
          |                  |          |
          |              Có thể       Streaming,
          |              CRUD thường  paging,
          |                            chunking
          |                               |
          +-------------------------------+
                                          |
                                          v
                           Cần atomic toàn file?
                              /          \
                            Có           Không
                             |             |
                        Một transaction    Commit per chunk
                        nhiều flush/clear  + checkpoint
                             |             |
                             +------+------+
                                    |
                                    v
                             Chọn chunkSize
                       đo heap/GC/DB latency
                                    |
                                    v
                      Bật JDBC batching nếu có
                      + kiểm tra ID generator
                                    |
                                    v
                       Persist/update một chunk
                                    |
                                    v
                             em.flush()
                                    |
                             Thành công?
                            /         \
                          Có          Không
                           |            |
                        em.clear()    Rollback
                           |         phân loại lỗi
                           v           |
                    Next chunk         +-- Permanent → repair/quarantine
                           |           +-- Transient → new tx bounded retry
                           v           +-- Unknown → reconcile
                    Commit theo policy
                           |
                           v
                      Ghi checkpoint
                           |
                           v
                  Verify / metrics / resume
~~~

## 39. Tổng kết

Xử lý nhiều entity theo khối với **flush và clear** là một kỹ thuật quan trọng để **giới hạn persistence context** và giúp các công việc bulk theo JPA không tích lũy vô hạn managed entities.

### 39.1. Hai lệnh cần nhớ

~~~java
em.flush(); // Đồng bộ pending changes tới DB trong transaction.
em.clear(); // Detach toàn bộ managed entities khỏi context.
~~~

**Thứ tự flush → clear** thường là đúng khi cần lưu những thay đổi đang chờ trước khi bỏ managed state.

Tuy nhiên:

- **flush không commit**; một transaction có thể chứa nhiều lần flush/clear.
- **clear không rollback, không xóa DB rows và không làm JVM giải phóng mọi objects** nếu code còn giữ references.
- **clear ảnh hưởng toàn persistence context**, gồm entities không liên quan nếu share context.
- **flush/clear không tự bật JDBC batching**; cấu hình provider, driver, ID generator và SQL shape quyết định việc gom statements.
- **chunk size, JDBC batch size và transaction size** là ba tham số độc lập.
- **Spring saveAll không mặc định là bulk SQL**; @Transactional ở proxy boundary quyết định commit.
- **update/delete theo entity** giữ lifecycle/cascade/dirty checking semantics khác **JPQL bulk DML**.
- **keyset pagination** giúp tránh lỗi OFFSET bỏ sót rows khi chính job đang thay đổi predicate, nhưng vẫn cần concurrent-data policy.
- **transaction-per-chunk** giúp job resume và giảm rollback scope, nhưng tạo partial success cần idempotency/checkpoint.
- **mọi flush failure** phải được xử lý theo transaction state; không clear rồi tiếp tục như không có lỗi.
- **đo hiệu năng** bằng throughput, heap/GC, SQL/batch executions, DB locks và commit latency; không dựa vào một con số chunkSize cố định.

### 39.2. Công thức thực hành

Với một transaction có nhiều chunks:

~~~java
for (ProductInput input : inputs) {
    em.persist(new Product(input.sku(), input.price()));
    processed++;

    if (processed % chunkSize == 0) {
        em.flush();
        em.clear();
    }
}

em.flush();
em.clear();

// Commit ở transaction boundary phù hợp.
~~~

Nếu cần mỗi chunk commit, **không chỉ thêm tx.commit bên trong một Spring @Transactional method**. Thay vào đó dùng một coordinator/transaction-per-chunk writer hoặc TransactionTemplate với propagation đúng, quản lý idempotency và checkpoint.

### 39.3. Chọn giải pháp theo nhu cầu

~~~text
Chỉ 100 Products:
  CRUD JPA đơn giản có thể đủ.

Import 100.000 Products cần @PrePersist/cascade:
  Chunked JPA persist + flush/clear, JDBC batching nếu hiệu quả.

Cập nhật 1 triệu Products bằng một điều kiện giống nhau:
  Cân nhắc JPQL bulk UPDATE/native SQL.

Import 10 triệu rows từ file:
  Cân nhắc streaming, JDBC batching, COPY/staging và job orchestration.

Cần rollback tất cả rows nếu một row sai:
  Một transaction (cân nhắc tài nguyên), không tự commit chunks.

Có thể commit từng chunk và resume sau lỗi:
  Transaction-per-chunk + checkpoint + idempotency.
~~~

**Nguyên tắc cuối cùng:** Dùng **flush/clear** để quản lý trạng thái của EntityManager, dùng **JDBC batching** để tối ưu cách gửi SQL, và dùng **transaction boundaries** để định nghĩa tính đúng đắn của dữ liệu. Khi cả ba được thiết kế riêng nhưng phối hợp nhất quán, ứng dụng JPA có thể xử lý số lượng lớn entity ổn định hơn, tiết kiệm bộ nhớ và phục hồi rõ ràng khi có sự cố.














