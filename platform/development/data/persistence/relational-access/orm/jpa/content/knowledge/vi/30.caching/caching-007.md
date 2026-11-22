# Xử lý dữ liệu cũ khi nguồn khác cập nhật trực tiếp cơ sở dữ liệu

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** Bộ nhớ đệm

Trong một hệ thống JPA, ứng dụng không phải lúc nào cũng là nơi duy nhất ghi dữ liệu. Một công cụ quản trị có thể chạy SQL trực tiếp, một job ETL cập nhật hàng loạt, một dịch vụ khác ghi qua JDBC, hoặc một stored procedure thay đổi trạng thái bản ghi. Những thay đổi này được cơ sở dữ liệu lưu lại nhưng **không tự đồng bộ các Java entity đang được quản lý trong persistence context**; tùy cache và provider, những giao dịch tiếp theo cũng có nguy cơ đọc state chưa mới.

Ví dụ: ứng dụng tải Product#42 có giá 100.000 đồng. Một job khác chạy:

~~~sql
UPDATE products
SET price = 120000.00
WHERE id = 42;
~~~

Job đã commit. Ứng dụng vẫn giữ object Product đang managed:

~~~java
Product product = em.find(Product.class, 42L);
// product.getPrice() có thể vẫn là 100000.00.
~~~

Gọi em.find một lần nữa **không nhất thiết truy vấn lại database**: first-level cache có thể trả chính instance cũ. Nếu ứng dụng còn bật **second-level cache**, ngay cả EntityManager mới cũng có thể lấy state từ cache chưa được invalidated. Và nếu đang dùng **query cache**, một kết quả truy vấn đã cache cũng có thể lỗi thời khi nguồn bên ngoài không phát tín hiệu thay đổi.

Bài học này tập trung vào cách nhận diện, giải thích và xử lý tình huống **nguồn khác cập nhật trực tiếp cơ sở dữ liệu** mà JPA không tự quan sát được, bao gồm:

- Phân biệt **database state**, **first-level cache**, **second-level cache** và **query cache**;
- Chọn đúng **refresh, clear, detach, evict** hoặc **persistence context mới**;
- Bypass/refresh shared cache bằng các **standard JPA cache hints** khi thích hợp;
- Không nhầm **cache staleness** với **transaction isolation/snapshot visibility**;
- Ngăn **lost update** khi SQL bên ngoài không cập nhật **@Version**;
- Thiết kế invalidation, TTL, CDC/event hoặc hợp đồng versioning cho nhiều dịch vụ;
- Kiểm thử bằng hai database sessions/transactions và nhiều persistence contexts.

**Nguyên tắc dẫn đường:** Cache giúp tiết kiệm truy vấn, nhưng tính đúng đắn phải được thiết kế ở ranh giới đọc/ghi. Không thể giả định một SQL UPDATE từ bên ngoài sẽ khiến mọi entity đang tồn tại trong RAM được tự làm mới.

## 1. Một bản ghi có thể có nhiều bản sao trong hệ thống

Khi dữ liệu đi qua JPA và các tầng cache, có thể tồn tại nhiều bản sao logic của cùng Product#42:

~~~text
                       Nguồn ngoài
                 (SQL / JDBC / ETL / service)
                            |
                            | UPDATE + COMMIT
                            v
                    +---------------+
                    |   DATABASE    |
                    | Product#42    |
                    | price=120000  |
                    +---------------+
                            ^
                            |
                  JDBC SQL / JPA provider
                            |
              +-------------+-------------+
              |                           |
     +-----------------+       +---------------------+
     | Shared/L2 cache |       | Query result cache  |
     | Product#42      |       | IDs/results của     |
     | price=100000?   |       | một truy vấn cũ?    |
     +-----------------+       +---------------------+
              ^
              |
     +---------------------+
     | EntityManager A     |
     | Persistence context |
     | Product#42 managed  |
     | price=100000        |
     +---------------------+
              ^
              |
       Service / Controller
~~~

Không phải mọi dự án đều bật L2 hoặc query cache; **first-level cache/persistence context** là yếu tố cơ bản của JPA khi dùng EntityManager. Chính vì thế tình huống stale data có thể xảy ra **ngay cả khi chưa bật bất kỳ Redis hay Hibernate second-level cache nào**.

### 1.1. Bốn khái niệm cần phân biệt

| Thành phần | Phạm vi | Có thể giữ dữ liệu cũ sau external SQL? | Biện pháp chính |
|---|---|---|---|
| Database row | Nguồn dữ liệu được commit | Có thể đọc snapshot cũ do isolation/replica lag | Transaction mới, kiểm tra isolation/replica |
| Persistence context / L1 | Một EntityManager/context | **Có**, managed entity không tự refresh | em.refresh, em.clear, em.detach, context mới |
| Shared second-level cache / L2 | EntityManagerFactory/provider, đôi khi nhiều nodes qua cache backend | **Có**, external writer không tự kích hoạt invalidation của provider | emf.getCache().evict, cache policy/invalidation |
| Query cache | Tùy provider, thường lưu tập IDs/kết quả query | **Có**, khi thông tin thay đổi bypass cơ chế invalidation | Provider-specific query cache eviction/TTL |

**Không tồn tại một lời gọi portable duy nhất bảo đảm làm mới đồng thời cả bốn tầng cho mọi DB/provider/cache/cluster**. Cần xử lý đúng tầng gây lỗi và đảm bảo transaction nhìn thấy dữ liệu mới.

### 1.2. “Committed” không đồng nghĩa “mọi reader nhìn thấy ngay”

Sau khi job ngoài COMMIT:
- Một giao dịch mới đọc từ primary DB theo isolation phù hợp thường có khả năng thấy state mới;
- Một transaction đang giữ snapshot theo REPEATABLE READ/SNAPSHOT có thể tiếp tục thấy dữ liệu trước đó;
- Một EntityManager giữ managed instance cũ có thể trả giá cũ dù DB đã commit;
- L2/cache trên node khác có thể chưa nhận invalidation;
- Một read replica có thể chậm hơn primary do replication lag.

Vì vậy câu “DB đã update mà JPA vẫn cũ” cần điều tra **đang đọc từ đâu, trong transaction nào và qua cache nào**.

### 1.3. Một số nguồn cập nhật trực tiếp thường gặp

- Script quản trị chạy qua psql, SSMS, SQL Developer;
- Batch migration/repair bằng JDBC;
- Job ETL hoặc data warehouse sync;
- Một microservice khác ghi cùng database;
- Stored procedure, trigger hoặc scheduled DB job;
- Native SQL hoặc JPQL bulk DML do chính ứng dụng gửi;
- External importer, replication/synchronization process;
- Tool vận hành sửa dữ liệu nóng.

**Tất cả đều phải có chính sách nhất quán về cache invalidation và versioning** nếu các đường đọc JPA cần thấy thay đổi ngay hoặc trong một thời hạn được xác định.

## 2. Mô hình ví dụ: Product có version và giá

Ta sử dụng entity Product để thống nhất các ví dụ trong bài.

### 2.1. Entity Product

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(nullable = false)
    private Long version;

    @Column(nullable = false, unique = true, length = 64)
    private String sku;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    protected Product() {}

    public Product(String sku, BigDecimal price) {
        this.sku = Objects.requireNonNull(sku);
        changePrice(price);
        this.active = true;
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public String getSku() { return sku; }
    public BigDecimal getPrice() { return price; }
    public boolean isActive() { return active; }

    public void changePrice(BigDecimal nextPrice) {
        if (nextPrice == null
                || nextPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Giá không được âm"
            );
        }
        this.price = nextPrice;
    }

    public void deactivate() {
        this.active = false;
    }
}
~~~

Mapping dùng Jakarta Persistence (**jakarta.persistence**). Trong các ứng dụng JPA cũ dùng namespace javax.persistence, imports và hint keys cần theo đúng phiên bản provider/framework.

**@Version** là optimistic concurrency token. Nó không tự làm mới Product khi SQL bên ngoài cập nhật database và không tự tăng nếu external SQL chỉ sửa price.

### 2.2. Schema PostgreSQL minh họa

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    sku VARCHAR(64) NOT NULL UNIQUE,
    price NUMERIC(19, 2) NOT NULL
        CHECK (price >= 0),
    active BOOLEAN NOT NULL
);
~~~

Schema chỉ để minh họa. Khi triển khai, DDL/version initialization phải tương thích với JPA provider và migration system; không mặc định mọi provider bắt đầu @Version ở cùng một số.

### 2.3. Dữ liệu ví dụ

Giả sử ban đầu:

| ID | SKU | Price | Active | Version |
|---:|---|---:|---|---:|
| 42 | KB-001 | 100000.00 | true | 7 |
| 43 | MS-002 | 250000.00 | true | 4 |
| 44 | HD-003 | 900000.00 | false | 2 |

EntityManager A đã đọc Product#42 và vẫn giữ nó managed với **price=100000.00, version=7**.

Một SQL writer B thay giá Product#42 thành **120000.00** rồi commit. Câu hỏi không chỉ là “giá nào đúng” — rõ ràng database đã ghi giá mới — mà là **khi nào, ở tầng nào và bằng cách nào A được phép quan sát giá mới**.

## 3. First-level cache: nguồn stale data thường bị bỏ sót

Trong JPA, mỗi persistence context lưu những entity được quản lý và đảm bảo identity map cho chúng.

~~~java
Product first = em.find(Product.class, 42L);
Product second = em.find(Product.class, 42L);

System.out.println(first == second); // true
~~~

Trong cùng persistence context, hai lời gọi find cho cùng entity identity thường trả **cùng Java instance**. Điều này giúp dirty checking và identity consistency, nhưng cũng có hệ quả khi SQL bên ngoài thay đổi row.

### 3.1. Tình huống stale object

~~~java
Product product = em.find(Product.class, 42L);

// Tại thời điểm này:
// product.getPrice() = 100000.00

// Một connection khác:
// UPDATE products SET price=120000.00 WHERE id=42;
// COMMIT;

Product again = em.find(Product.class, 42L);

System.out.println(again == product); // true
System.out.println(again.getPrice());
// Có thể vẫn là 100000.00.
~~~

Lời gọi find thứ hai **không phải lời cam kết đọc lại database**. Persistence context đã giữ instance có ID này nên provider có thể trả state đang có.

### 3.2. Tại sao đây là hành vi hợp lý của JPA?

JPA cần:
- Một instance managed duy nhất ứng với một entity identity trong context;
- Khả năng phát hiện thay đổi từ object;
- Quản lý quan hệ giữa managed entities;
- Tránh tạo nhiều Java objects khác nhau cho cùng identity trong một unit of work.

Nếu mỗi lần find đều âm thầm overwrite managed state, những thay đổi chưa flush của ứng dụng có thể bị mất. Do đó **refresh là một thao tác có chủ đích**, tách khỏi find.

### 3.3. Không cần bật Hibernate L2 để có L1

Nhiều lập trình viên tắt:

~~~properties
spring.jpa.properties.hibernate.cache.use_second_level_cache=false
~~~

rồi nghĩ không còn cache. Điều này chỉ liên quan tính năng Hibernate L2; **persistence context của EntityManager vẫn tồn tại**.

Không thể tắt identity map/managed entity semantics chỉ bằng cách tắt second-level cache. Muốn tránh đọc lại một managed instance cũ, phải quản lý vòng đời context hoặc refresh.

### 3.4. Trong Spring, một transaction thường có persistence context riêng

Trong nhiều cấu hình Spring Data JPA thông dụng, transaction-scoped persistence context hoạt động theo ranh giới transaction. Một request mới, transaction mới thường dùng context riêng nên tránh lưu Java instances managed xuyên quá lâu.

Tuy nhiên vẫn có tình huống kéo dài:
- Một @Transactional method chạy lâu;
- Open EntityManager In View;
- Extended persistence context;
- EntityManager được quản lý thủ công và không đóng đúng lúc;
- Import/job giữ context qua nhiều batches.

Không đồng nhất “HTTP request mới” với “chắc chắn không có L1 stale” nếu cấu hình transaction/context khác thông thường.

### 3.5. Persistence context giữ cả các quan hệ đã load

Nếu Product có Category hoặc PriceRule relationship đã được tải, refresh một Product không có nghĩa mọi entity liên quan trong context tự cập nhật theo thay đổi từ bên ngoài. Cần kiểm tra cascade=REFRESH và phạm vi graph, hoặc refresh những managed entity liên quan một cách có chủ đích.

Ngược lại, clear toàn context cũng làm detached **mọi entity** đang managed, không chỉ Product#42. Đó là tác động phải tính đến trong service lớn.

## 4. Giải pháp cấp L1: EntityManager.refresh

**em.refresh(entity)** yêu cầu đồng bộ state của một **managed entity** từ database.

~~~java
Product product = em.find(Product.class, 42L);

// Nguồn bên ngoài commit update Product#42.

em.refresh(product);

System.out.println(product.getPrice());
// Có thể trở thành 120000.00 khi DB snapshot
// của transaction hiện tại nhìn thấy bản mới.
~~~

### 4.1. Refresh cập nhật chính managed instance

Khác với em.clear rồi find lại, em.refresh thường làm mới state vào **đối tượng managed hiện tại**:

~~~java
Product sameReference = product;
em.refresh(product);

System.out.println(product == sameReference); // true
~~~

Điều này hữu ích nếu các đoạn code khác trong cùng context còn tham chiếu Product instance ấy và muốn nhìn thấy state mới.

### 4.2. Refresh yêu cầu đối tượng managed

~~~java
em.clear();

em.refresh(product); // Sai: product đã detached.
~~~

Với detached entity, JPA không cho phép refresh như một managed target thông thường và có thể ném IllegalArgumentException. Phải find lại entity trong một context phù hợp rồi refresh nếu cần.

### 4.3. Cẩn thận vì refresh có thể làm mất thay đổi chưa flush

Ví dụ:

~~~java
Product product = em.find(Product.class, 42L);

product.changePrice(
    new BigDecimal("110000.00")
);

// Chưa flush: giá mới chỉ ở managed state.
em.refresh(product);

// Thay đổi 110000.00 có thể bị thay bằng
// giá từ database; không tự được giữ lại.
~~~

**em.refresh không phải merge ba chiều**. Nó chủ yếu nạp state từ DB vào object, và có thể overwrite những sửa đổi Java chưa flush. Nếu nghiệp vụ cần giữ dirty changes, phải xác định rõ cách xử lý trước khi refresh.

### 4.4. Refresh và transaction isolation

Giả sử:
1. Transaction A bắt đầu ở mức isolation kiểu snapshot;
2. A đọc Product price=100000;
3. Transaction B cập nhật price=120000 và commit;
4. A gọi em.refresh(product) trong **cùng transaction A**.

Nếu A đang đọc snapshot cố định theo REPEATABLE READ/SNAPSHOT, nó có thể **không nhìn thấy giá 120000** dù đã refresh. Điều này không chứng minh em.refresh bị hỏng; DB không cung cấp phiên bản mới trong snapshot hiện tại.

Khi cần quan sát commit của B, có thể phải:
- Kết thúc transaction A;
- Mở transaction/context đọc mới;
- Bảo đảm đọc primary DB hoặc read source đã bắt kịp replication;
- Áp isolation level phù hợp với yêu cầu.

**Refresh không phá vỡ transaction isolation của database.**

### 4.5. Refresh không giống flush

| Thao tác | Hướng dữ liệu chính | Tác dụng |
|---|---|---|
| em.flush() | Managed state → DB | Ghi pending changes trong transaction, chưa commit |
| em.refresh(entity) | DB → Managed entity | Nạp lại entity, có thể overwrite dirty state |
| em.clear() | Quản lý state → detached | Bỏ quản lý tất cả entities, không xóa DB row |
| em.detach(entity) | Managed → detached | Bỏ quản lý một entity |
| em.find(...) | Lấy entity theo identity | Có thể trả managed instance đã có |

Gọi **em.flush() sau external UPDATE không tự làm Product có giá mới**. Ngược lại, flush một Product đang stale có thể gây lost update hoặc optimistic conflict tùy version và SQL strategy.

### 4.6. Refresh theo graph/cascade

Nếu có quan hệ:

~~~java
@ManyToOne(
    fetch = FetchType.LAZY,
    cascade = CascadeType.REFRESH
)
private Category category;
~~~

thì refresh có thể cascade qua quan hệ theo mapping. **Không thêm CascadeType.REFRESH hoặc CascadeType.ALL bừa bãi**: nó có thể nạp lại những objects có dirty state khác, tăng SQL và làm mất thay đổi chưa lưu.

Với aggregate lớn, refresh cả graph để cập nhật một trường giá có thể rất tốn chi phí. Chọn phạm vi có chủ đích.

### 4.7. Refresh không phải công cụ thay thế invalidation đa node

Refresh Product trong EntityManager A chỉ giải quyết state trong context A (và những thao tác cache provider thực hiện tương ứng). Nó **không tự đảm bảo** xóa mọi L2/query cache trên các JVM khác hoặc các cached REST responses/CDN.

Đối với nhiều dịch vụ, cần chiến lược cache consistency rộng hơn.

## 5. Giải pháp cấp L1: clear, detach và context mới

Khi cần đọc lại một hoặc nhiều entities mà không muốn dùng old managed state, có thể loại bỏ chúng khỏi persistence context.

### 5.1. em.clear(): detach tất cả managed entities

~~~java
Product old = em.find(Product.class, 42L);

// SQL writer ngoài đã commit.

em.clear();

Product current = em.find(Product.class, 42L);

System.out.println(em.contains(old));     // false
System.out.println(em.contains(current)); // true
~~~

**old** vẫn là một Java object có price cũ; nó không tự thay đổi chỉ vì em.clear. **current** là managed instance được tìm sau clear, nhưng nguồn state có thể là L2 cache nếu L2 đang bật và còn stale.

### 5.2. Clear trước flush có thể bỏ mất pending changes

~~~java
Product product = em.find(Product.class, 42L);
product.changePrice(new BigDecimal("115000.00"));

em.clear();

// Thay đổi 115000.00 chưa được flush
// có thể không được đồng bộ vào database.
~~~

Nếu nghiệp vụ muốn giữ pending changes, cân nhắc **em.flush() trước em.clear()**, nhưng chỉ khi chắc chắn không đưa stale data xuống DB. Nếu context đang giữ Product có state cũ do external SQL, flush có thể nguy hiểm.

Vì vậy không áp công thức “cứ flush rồi clear” vô điều kiện trong tình huống stale data. Cần biết **những entities nào đang dirty, những DB rows nào đã bị nguồn ngoài thay đổi, và @Version có được duy trì hay không**.

### 5.3. em.detach(entity): loại một entity khỏi context

~~~java
Product old = em.find(Product.class, 42L);

em.detach(old);

Product current = em.find(Product.class, 42L);
~~~

detach chỉ target entity, trừ những phần có cascade DETACH theo mapping. Các entities khác vẫn managed. Cách này phù hợp khi xác định rõ một Product cần được nạp lại nhưng không muốn clear toàn persistence context.

**Cẩn thận:** Nếu old Product có pending dirty changes, detach có thể làm các thay đổi ấy không được flush. Và một entity association đã managed liên quan vẫn có thể giữ state cũ riêng.

### 5.4. Persistence context mới là ranh giới rõ ràng

~~~java
EntityManager fresh = emf.createEntityManager();

try {
    Product product = fresh.find(Product.class, 42L);
    // Context mới không chứa instance Product#42
    // từ EntityManager cũ.
} finally {
    fresh.close();
}
~~~

Để bảo đảm nhìn thấy external commit, còn phải xét:
- Transaction của context mới có thấy commit mới theo isolation không;
- L2 cache có stale không;
- Có đi qua read replica đang trễ không.

Context mới **giải quyết L1 cũ, không tự xóa L2**.

### 5.5. Không chia sẻ EntityManager giữa threads

Nếu có nhiều job/process cập nhật chung database, không cho nhiều threads cùng dùng một EntityManager để “cùng nhìn thấy state”. EntityManager không được thiết kế để dùng đồng thời như một thread-safe shared cache.

Mỗi unit of work nên có context phù hợp. Khi cần giao tiếp giữa writers, dùng transaction, database concurrency control và invalidation events, không share Java entity references xuyên threads.

## 6. Quyết định khi nào refresh, clear hay detach

| Nhu cầu | Ưu tiên cân nhắc | Lý do |
|---|---|---|
| Làm mới một managed Product, vẫn dùng cùng reference | em.refresh(product) | Nạp state vào object hiện tại |
| Bỏ một stale entity nhưng giữ các managed entities khác | em.detach(product), find lại | Phạm vi hẹp |
| Bỏ toàn bộ managed state cũ | em.clear() | Context sạch nhưng có side effects toàn context |
| Kết thúc workflow dài rồi đọc state mới | Transaction/context mới | Ranh giới dễ hiểu |
| L2 cache stale | emf.getCache().evict(...) | Không phải nhiệm vụ của em.clear |
| Query cache stale | Provider-specific query cache invalidation | Standard Cache.evict không đồng nghĩa clear query cache |
| Transaction snapshot cũ | Transaction mới/isolation phù hợp | Cache operations không phá snapshot |
| Read replica lag | Đọc primary/consistency routing | Không phải lỗi JPA L1 |

### 6.1. Khi nào dùng refresh ngay?

Hợp lý khi:
- Vẫn ở transaction thấy dữ liệu mới;
- Product là managed;
- Không có dirty changes cần giữ trên Product;
- Chỉ cần vài entities;
- Những association cần dùng được xác định rõ.

### 6.2. Khi nào nên chọn transaction mới?

Hợp lý khi:
- Transaction cũ có snapshot được cố định;
- Workflow đã hoàn thành và cần kiểm tra kết quả writer khác;
- Có nhiều managed entities cũ khó phân biệt;
- Service không cần giữ object identity cũ;
- Có thể tái tạo read model từ DB một cách rõ ràng.

### 6.3. Khi nào chưa nên gọi bất kỳ cache operation nào?

Nếu business rule không cần đọc giá mới **ngay**, việc liên tục refresh/evict trên mỗi request có thể làm cache mất tác dụng. Cần định nghĩa consistency requirement trước:
- Strong/transactional consistency;
- Read-your-writes;
- Bounded staleness vài giây;
- Eventual consistency;
- Snapshot báo cáo tại một thời điểm.

Không mọi dữ liệu đều cần “luôn mới nhất” bất chấp hiệu năng; nhưng cũng không được tự nới yêu cầu nhất quán của giá/tồn kho/tài chính khi nghiệp vụ không cho phép.

## 7. Second-level cache: dữ liệu cũ có thể đi qua nhiều EntityManagers

**Second-level cache (L2)** là cache dùng chung ở phạm vi provider/EntityManagerFactory hoặc backend mà provider cấu hình. Nó khác **L1**, vốn chỉ thuộc một persistence context.

Giả sử:
1. EntityManager A đọc Product#42, làm L2 lưu price=100000;
2. A đóng;
3. Job ngoài cập nhật DB price=120000 và commit;
4. EntityManager B mới tìm Product#42;
5. Nếu L2 còn entry price=100000 và provider sử dụng entry ấy, B có thể nhận giá cũ dù L1 của B hoàn toàn mới.

~~~text
EntityManager A → L2 { Product#42 price=100000 }
                    |
External SQL → DB { Product#42 price=120000 }
                    |
EntityManager B → L2 hit { price=100000? }
                    |
                 Stale read
~~~

Tính năng L2 có bật hay không, entry nào cache được, chiến lược concurrency của cache và cách provider invalidates dữ liệu là **phụ thuộc cấu hình/provider**.

### 7.1. Không mặc định JPA nào cũng bật L2

JPA chuẩn định nghĩa cơ chế shared cache và API liên quan, nhưng việc có L2 thực sự, các entity tham gia cache và provider hỗ trợ ra sao phụ thuộc implementation và persistence-unit configuration.

Các lựa chọn **SharedCacheMode** có thể gồm:
- ALL;
- NONE;
- ENABLE_SELECTIVE;
- DISABLE_SELECTIVE;
- UNSPECIFIED.

Ví dụ cấu hình bằng annotation:

~~~java
import jakarta.persistence.Cacheable;

@Entity
@Cacheable
public class Product {
    // ...
}
~~~

**@Cacheable** và SharedCacheMode giúp xác định eligibility theo JPA, nhưng không tự tạo một backend L2 đầy đủ nếu provider chưa được cấu hình. Với Hibernate thường cần thêm provider/cache region strategy cụ thể.

### 7.2. Cache API chuẩn qua EntityManagerFactory

JPA cung cấp:

~~~java
Cache cache = emf.getCache();
~~~

trong đó **Cache** là **jakarta.persistence.Cache**.

Một số thao tác thường dùng:

~~~java
cache.contains(Product.class, 42L);
cache.evict(Product.class, 42L);
cache.evict(Product.class);
cache.evictAll();
~~~

Những thao tác này tập trung vào **shared cache dành cho entities** ở EntityManagerFactory tương ứng, không phải toàn bộ object caches khác trong hệ thống.

### 7.3. Xóa entry một Product

~~~java
emf.getCache().evict(Product.class, productId);
~~~

Lời gọi yêu cầu xóa Product cụ thể khỏi shared cache. Với hệ thống có một EntityManagerFactory và provider quản lý L2, nó có thể đủ để lần **load mới** không nhận entry cũ từ cache của factory đó.

Nhưng **evict không cập nhật Java object Product đã managed trong EntityManager khác**.

### 7.4. Xóa cả entity region

~~~java
emf.getCache().evict(Product.class);
~~~

Loại mọi Product entries trong shared cache theo contract tương ứng. Hữu ích khi external job đã cập nhật một tập lớn IDs không thể xác định gọn, nhưng gây nhiều cache misses hơn nên cần cân nhắc hiệu năng.

### 7.5. Xóa tất cả entity cache regions

~~~java
emf.getCache().evictAll();
~~~

Đây là phương án phạm vi rất rộng và có thể tạo **cache stampede**/tăng database load đột ngột. Chỉ dùng khi thực sự cần hoặc trong recovery/operations đã được đánh giá; không dùng sau mọi SQL update nhỏ.

### 7.6. Evict không có nghĩa xóa L1

~~~java
Product product = em.find(Product.class, 42L);

// External SQL commit ...
emf.getCache().evict(Product.class, 42L);

Product same = em.find(Product.class, 42L);
~~~

Trong cùng EntityManager, **same** có thể vẫn là **product** mang price cũ. Lý do: L2 eviction không làm instance managed trong L1 biến mất.

Nếu cần đọc lại state:
- em.refresh(product), hoặc
- em.detach(product) rồi find lại, hoặc
- em.clear rồi find lại, hoặc
- dùng context mới.

Đồng thời phải kiểm tra transaction visibility và L2 strategy như đã phân tích.

### 7.7. Em.clear không có nghĩa xóa L2

Chiều ngược lại cũng quan trọng:

~~~java
em.clear();

Product product = em.find(Product.class, 42L);
~~~

Nếu L2 còn stale, Product đọc sau clear có thể tiếp tục lấy giá cũ từ L2. **Clear giải quyết L1, không mặc định invalidates shared cache**.

### 7.8. Nhiều EntityManagerFactory, nhiều nodes

Giả sử triển khai hai JVM:

~~~text
Application Node A                 Application Node B
EntityManagerFactory A            EntityManagerFactory B
L2 cache A                        L2 cache B
        \                           /
           Shared production DB
                    ^
                    |
              External writer
~~~

Gọi **emfA.getCache().evict(...)** không chứng minh **L2 cache trên node B** đã bị invalidated. Điều đó phụ thuộc:
- Cache backend có phân tán hay không;
- Provider có cơ chế cluster invalidation không;
- Node B có subscription tới event không;
- Cache region/version strategy có nhất quán không;
- Đường ghi ngoài có phát tín hiệu cần thiết không.

Không gọi một thao tác JPA Cache của node A rồi tuyên bố mọi replica/node đã sạch.

### 7.9. Cache contains không phải bằng chứng dữ liệu mới

~~~java
boolean cached =
    emf.getCache().contains(Product.class, 42L);
~~~

contains trả thông tin về sự hiện diện entry (theo contract/provider), **không so sánh phiên bản/cột giá với database**. Giá trị true có thể là entry stale; false không bảo đảm mọi tầng khác (L1/query cache/Redis/read replica) đều không có state cũ.

### 7.10. Tình huống xóa row từ nguồn ngoài

External SQL:

~~~sql
DELETE FROM products WHERE id = 42;
COMMIT;
~~~

Một Product#42 stale trong L1/L2 có thể khiến ứng dụng tiếp tục nhìn thấy entity đã bị xóa cho đến khi refresh/reload/invalidation và transaction visibility cho phép. Nếu đọc lại DB và row không còn, em.find trong context sạch thường trả null, còn em.refresh một entity đã bị xóa có thể ném exception theo JPA/provider.

Đừng coi L2 eviction là một DELETE hoặc một SQL query: nó chỉ liên quan cache.

## 8. CacheRetrieveMode và CacheStoreMode: điều khiển JPA shared cache

JPA có các **cache modes chuẩn** để đưa vào properties/hints của EntityManager operations hoặc query:

- **jakarta.persistence.cache.retrieveMode**
- **jakarta.persistence.cache.storeMode**

Ví dụ:

~~~java
import jakarta.persistence.CacheRetrieveMode;
import jakarta.persistence.CacheStoreMode;
~~~

Các enum giúp yêu cầu provider đọc cache hay không và xử lý việc đưa dữ liệu vào shared cache. Chúng **không phải cơ chế bỏ qua L1 identity map**, cũng không phải lệnh thay đổi transaction isolation.

### 8.1. CacheRetrieveMode

| Mode | Ý nghĩa |
|---|---|
| USE | Cho phép truy xuất dữ liệu từ shared cache |
| BYPASS | Bỏ qua shared cache khi truy xuất entity state |

Ví dụ:

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);
~~~

Nếu truy vấn thực sự cần tải entity từ DB và không bị L1 giữ sẵn, BYPASS giúp giảm nguy cơ lấy một entry cũ từ L2.

### 8.2. CacheStoreMode

| Mode | Ý nghĩa chính |
|---|---|
| USE | Có thể đưa state vừa tải vào shared cache theo quy tắc provider |
| BYPASS | Không đưa state mới vào shared cache theo hint |
| REFRESH | Yêu cầu làm mới shared cache entry bằng state đọc từ DB |

Ví dụ:

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.REFRESH
);
~~~

**REFRESH ở đây là cache store mode**, không phải lời gọi em.refresh(entity) và không trực tiếp có nghĩa “tải lại mọi managed entity trong persistence context”.

### 8.3. Kết hợp BYPASS và REFRESH cho một lần load

Khi muốn đọc state từ DB và làm mới L2 entry tương ứng, có thể yêu cầu:

~~~java
Map<String, Object> properties = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS,
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.REFRESH
);

Product current = em.find(
    Product.class,
    productId,
    properties
);
~~~

**Điều kiện quan trọng:** Nếu Product#42 đã managed trong **cùng EntityManager**, em.find có thể trả instance L1 trước đó. Hai cache hints không buộc object managed đang có tự cập nhật.

Để thí nghiệm hoặc triển khai read cần cache bypass:
- Dùng EntityManager chưa chứa Product#42;
- Hoặc detach/clear cũ theo policy;
- Đảm bảo transaction đang nhìn thấy commit mới;
- Sau đó mới áp hints.

### 8.4. BYPASS và BYPASS: đọc mà không dùng/ghi L2

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS,
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.BYPASS
);
~~~

Phù hợp cho một luồng đọc muốn tránh tương tác shared cache, nhưng có thể làm tăng database traffic. Không coi BYPASS là cách xóa entry stale đã tồn tại; nó chỉ yêu cầu behavior cho thao tác đọc/ghi cache của operation.

### 8.5. USE + REFRESH khác BYPASS + REFRESH

Cơ chế cache modes có semantics riêng theo JPA/provider; khi mục tiêu là **buộc lấy DB state thay cho L2**, đặt **retrieveMode=BYPASS** là một cách diễn đạt rõ hơn. **storeMode=REFRESH** hướng tới cập nhật cache khi state được load.

Đừng tự suy rằng chỉ thêm REFRESH vào bất kỳ em.find nào là bảo đảm bypass mọi cache và DB snapshot. Nếu persistence context đã quản lý entity, vẫn phải giải quyết L1.

### 8.6. Hints cho TypedQuery

~~~java
TypedQuery<Product> query = em.createQuery(
    """
    select p
    from Product p
    where p.id = :id
    """,
    Product.class
);

query.setParameter("id", productId);
query.setHint(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);
query.setHint(
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.REFRESH
);

Product product = query.getSingleResult();
~~~

Nếu Product đã managed trong cùng context, provider có thể trả managed instance theo identity map. Vì vậy một query bypass L2 không phải cam kết tránh stale L1.

### 8.7. Namespace của JPA cũ

Với API sử dụng javax.persistence, tương ứng:

~~~java
"javax.persistence.cache.retrieveMode"
"javax.persistence.cache.storeMode"
~~~

và enum từ **javax.persistence**. Không trộn Jakarta và javax imports/hint names rồi kỳ vọng provider nhận diện đúng.

### 8.8. Phải kiểm tra provider thực tế

Shared cache hints được JPA chuẩn hóa, nhưng mức hỗ trợ và tương tác với query types, multi-table joins, cache regions và transaction context có thể khác. Khi correctness quan trọng:
- Dùng provider/database thật;
- Quan sát SQL và cache hit/miss;
- Đo trên context mới;
- Kiểm tra transaction visibility;
- Không dựa duy nhất vào việc setHint trả về bình thường.

## 9. Query cache: stale results khác stale entity state

Nhiều provider có **query result cache** (thường là tính năng provider-specific), khác với cache entity theo ID.

Ví dụ một query:

~~~java
select p
from Product p
where p.active = true
order by p.id
~~~

có thể được cache ở dạng IDs hoặc kết quả dữ liệu tùy provider. External SQL:

~~~sql
UPDATE products
SET active = false
WHERE id = 42;
COMMIT;
~~~

có thể khiến danh sách "active products" trong query cache vẫn chứa Product#42 dù DB đã bỏ trạng thái active.

### 9.1. Hai lớp stale khác nhau

~~~text
Query cache cũ:
    List active IDs = [42, 43]

L2 entity cache cũ:
    Product#42 {active=true, price=100000}

Database mới:
    Product#42 {active=false, price=120000}
~~~

Nếu chỉ evict Product#42 khỏi L2 nhưng query cache vẫn cho rằng #42 thuộc active list, ứng dụng có thể vẫn xử lý membership lỗi thời (tùy provider/query cache mechanism).

Ngược lại, nếu xóa query cache nhưng L2 entity entry cũ vẫn còn, query execution có thể nhìn danh sách đúng mà entity state vẫn lỗi thời.

### 9.2. JPA Cache.evict không phải API portable xóa mọi query cache

~~~java
emf.getCache().evict(Product.class, 42L);
~~~

là API chuẩn cho **entity shared cache**. Không khẳng định nó bắt buộc dọn mọi query result cache được provider cài đặt.

Với Hibernate, query cache/regions có cơ chế invalidate/evict riêng; với EclipseLink hoặc các providers khác, tên API và behavior khác. Phải kiểm tra phiên bản thực tế trước khi dùng provider-specific eviction.

### 9.3. Native SQL/bulk DML có thể được provider biết hoặc không

Phân biệt:

1. **JPA provider thực thi một JPQL mutation**: provider có thể biết entity/tables bị ảnh hưởng và invalidates một số cache regions theo chiến lược của nó.
2. **JPA provider thực thi native SQL**: provider có thể không suy ra đầy đủ tables/regions ảnh hưởng, hoặc có cơ chế synchronize query spaces theo cấu hình.
3. **Công cụ ngoài JVM thực thi SQL trực tiếp**: provider không tự nhận được sự kiện mutation trừ khi có cơ chế khác.

Không khẳng định Hibernate tự invalidate query/L2 caches cho mọi SQL/native procedure trong mọi cấu hình. **Writer nằm ngoài provider là trường hợp đặc biệt cần giải quyết bằng invalidation coordination**.

### 9.4. Query cache hit không chứng minh kết quả vẫn hợp lệ

Một cache hit chỉ nói kết quả được phục vụ từ cache, không chứng minh source data chưa đổi. Khi external writers tồn tại, phải có một trong những policy:
- Explicit invalidation;
- TTL phù hợp với bounded staleness;
- Version-based cache key;
- CDC/invalidation events;
- Không cache những query nhạy cảm;
- Đọc nhất quán từ DB ở operation quan trọng.

### 9.5. Tách query result freshness và entity freshness khi test

Kiểm thử:
- External INSERT Product#45 active=true để xem query membership cập nhật;
- External UPDATE Product#42 active=false để xem entry được loại khỏi list;
- External UPDATE price để xem entity values mới;
- Lặp lại với L1 context mới và tùy chọn query cache/L2 on/off.

Nếu chỉ test thay price nhưng không thay membership, có thể không phát hiện query cache cũ. Nếu chỉ test membership, có thể bỏ sót L2 entity state cũ.

## 10. Ba tình huống stale đọc thường gặp

### 10.1. Tình huống A: chỉ L1 cũ

- EntityManager A đọc Product#42;
- External job update/commit;
- A find lại cùng ID;
- L1 trả Java instance cũ;
- L2 không bật.

Giải pháp: refresh trong transaction thấy dữ liệu mới, detach/clear hoặc context mới.

### 10.2. Tình huống B: L2 cũ, context mới

- A đọc Product#42 làm L2 chứa version cũ;
- External SQL update/commit;
- B dùng EntityManager mới;
- B find nhưng có L2 hit với giá cũ.

Giải pháp: cache eviction/invalidation hoặc L2 bypass+refresh theo mục tiêu; cần kiểm tra cache provider và propagation qua nodes.

### 10.3. Tình huống C: DB snapshot cũ dù cache đã sạch

- Transaction A đọc Product trong REPEATABLE READ/snapshot;
- B update/commit;
- A clear/evict rồi refresh hoặc query lại;
- A vẫn có thể nhìn snapshot cũ theo isolation.

Giải pháp: kết thúc transaction A, mở transaction mới với consistency routing phù hợp. Đây không phải lỗi cache API.

### 10.4. Một tình huống thực tế có thể kết hợp cả ba

Trong production có nhiều nodes và read replica, stale state có thể do:
- L1 instance;
- L2 local cache;
- Query result cache;
- Redis cache-aside;
- MVCC snapshot;
- Replica lag.

Đừng dùng một lệnh **evictAll** để "chữa" ngay tất cả, rồi kết luận rằng vấn đề đã được giải quyết. Cần xác định stale xuất hiện ở tầng nào qua các thí nghiệm có kiểm soát.

## 11. Nguy cơ nghiêm trọng hơn stale read: lost update

Dữ liệu cũ không chỉ khiến màn hình hiển thị sai. Nếu một managed entity được tải trước external SQL update, sau đó ứng dụng sửa và flush, nó có thể **ghi đè một phần hoặc toàn bộ thay đổi bên ngoài**, tùy mapping, dirty checking, SQL UPDATE strategy và versioning.

### 11.1. Timeline xung đột

~~~text
T0  DB Product#42:
    price=100000, active=true, version=7

T1  App A em.find:
    managed Product#42 price=100000, active=true, version=7

T2  External writer B:
    UPDATE products SET price=120000 WHERE id=42;
    COMMIT;
    DB price=120000, active=true, version=7

T3  A gọi product.deactivate():
    managed price=100000, active=false, version=7

T4  A flush/commit:
    Provider UPDATE theo dirty state/version strategy.

Rủi ro:
    - active đổi thành false;
    - price có thể bị ghi lại 100000 nếu SQL UPDATE
      chứa cột price từ managed snapshot cũ;
    - @Version vẫn có thể thấy version=7 khớp,
      do B không tăng version.
~~~

Đây là ví dụ **lost update**: thay đổi price của B có thể bị ghi đè bởi A dù A chỉ định đổi active. Không mặc định lỗi luôn xảy ra; một provider có chiến lược dynamic update có thể chỉ viết dirty columns. Nhưng **không thể dựa vào điều đó để bảo vệ mọi đường ghi**.

### 11.2. SQL ORM khái niệm

Một provider có thể phát:

~~~sql
UPDATE products
SET price = 100000.00,
    active = false,
    version = 8
WHERE id = 42
  AND version = 7;
~~~

Vì external UPDATE không tăng version, điều kiện **version=7** vẫn khớp; update của A có thể thành công và thay price về giá cũ.

Provider khác có thể chỉ phát:

~~~sql
UPDATE products
SET active = false,
    version = 8
WHERE id = 42
  AND version = 7;
~~~

làm price không bị ghi đè trong ví dụ này. Tuy nhiên nếu external writer thay đổi cùng field active hoặc có invariants dựa trên price, race và dữ liệu stale vẫn tồn tại.

### 11.3. @Version chỉ hoạt động đúng khi mọi writer tham gia

Nếu writer B thay đổi cột được bảo vệ thì nên tăng version theo cùng chính sách. Với numeric version:

~~~sql
UPDATE products
SET price = 120000.00,
    version = version + 1
WHERE id = 42;
~~~

Lúc đó:
- A đã tải version=7;
- DB sau B là version=8;
- A cố UPDATE với WHERE version=7;
- Provider nhận thấy không còn phiên bản phù hợp và có thể ném **OptimisticLockException**.

Cách này bảo vệ A khỏi ghi đè âm thầm vào row đã thay đổi. Nhưng nó cần được áp **nhất quán trên mọi đường ghi**; một ETL job bỏ qua version cũng đủ tạo lỗ hổng.

### 11.4. Việc tăng version không tự làm mới cache

External SQL:

~~~sql
UPDATE products
SET price = 120000.00,
    version = version + 1
WHERE id = 42;
~~~

giúp phát hiện stale update, nhưng:
- Managed Product trong L1 vẫn có price/version cũ;
- L2 entry có thể vẫn cũ;
- Query cache có thể vẫn chứa kết quả cũ;
- Transaction snapshot có thể vẫn nhìn phiên bản cũ.

**Versioning là cơ chế bảo vệ write conflict; invalidation/refresh là cơ chế quản lý read freshness.** Cần cả hai khi business yêu cầu.

### 11.5. Conditional update theo expected version

External writer cũng có thể dùng compare-and-set:

~~~sql
UPDATE products
SET price = :new_price,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
~~~

Caller phải kiểm tra **affected row count = 1** cho một ID hợp lệ. Nếu 0:
- Row đã bị xóa;
- Version đã đổi;
- ID sai;
- Hoặc predicate bổ sung không khớp.

Đừng tự động kết luận mỗi kết quả 0 đều là optimistic conflict nếu câu SQL còn tenant/status predicates.

### 11.6. Bảo vệ dữ liệu từ nguồn ngoài không nên bỏ @Version

Một vài người chọn SQL:

~~~sql
UPDATE products
SET version = 0
WHERE id = 42;
~~~

nhằm "đồng bộ" version về mặc định. Điều đó phá cơ chế concurrency token. Không tự hạ version để khiến các detached objects cũ có thể ghi lại. Khi migration dữ liệu cần sửa version, phải có plan nhất quán, không reset tùy tiện trên dữ liệu đang được giao dịch sử dụng.

### 11.7. Trigger quản lý version có phải lời giải?

Database trigger có thể tăng version khi UPDATE bất kỳ cột nào; điều này có lợi nếu nhiều writers không thể sửa câu SQL. Nhưng phải cân nhắc tương thích với ORM:
- ORM cũng có thể tự tăng version, dễ bị tăng hai lần nếu trigger thêm một lần nữa;
- Giá trị version JPA giữ trong managed entity có thể không khớp DB nếu trigger thay ngoài hiểu biết provider;
- Một số mapping có cơ chế database-generated version, cần cấu hình provider tương ứng;
- Trigger semantics khác nhau giữa INSERT, UPDATE, NO-OP updates và tables.

Không bật trigger tăng version mà chưa kiểm thử insert/update/merge/refresh với provider thực tế. Có thể thay bằng chính sách SQL writer rõ hơn hoặc một cơ chế version-generated được ORM hỗ trợ.

### 11.8. Optimistic conflict là lỗi cần giải quyết, không phải lỗi cache đơn thuần

Nếu A flush và gặp OptimisticLockException sau external update có version tăng:
1. Rollback transaction A;
2. Không tiếp tục dùng stale managed context như nguồn sự thật;
3. Tải lại Product trong transaction mới;
4. Kiểm tra lại business invariant;
5. Áp dụng sửa đổi có ý thức hoặc báo conflict.

Không tự bắt exception rồi “refresh + ghi lại ngay” nếu thao tác có thể làm mất giá hoặc vi phạm quy tắc nghiệp vụ.

## 12. Chiến lược read-after-write khi có external writer

Các hệ thống khác nhau cần mức độ nhất quán khác nhau; quyết định điều đó trước khi bật/tắt cache.

### 12.1. Strong read-after-write trên primary

Nếu một API quản trị sửa giá qua external service và ngay sau đó cần trả đúng giá mới:
1. Đợi external writer commit thành công;
2. Tạo read transaction/context mới hoặc refresh khi isolation cho phép;
3. Không dùng stale L1;
4. Bypass/evict L2 nếu external writer chưa invalidates nó;
5. Đọc từ primary hoặc nguồn có consistency guarantee;
6. Trả dữ liệu đã xác minh.

Đừng chỉ thêm **Thread.sleep(1000)** rồi gọi find lại trong cùng context. Ngủ không xóa L1 và cũng không bảo đảm L2/replica được đồng bộ.

### 12.2. Bounded staleness

Một catalog công khai có thể chấp nhận giá hiển thị cũ tối đa vài giây nếu nghiệp vụ cho phép, nhưng checkout vẫn phải tính giá và tồn kho authoritative.

Khi đó:
- TTL cache ngắn;
- Invalidation event khi cập nhật;
- Cache miss khi hết hạn;
- Monitoring staleness window;
- Đường read authoritative cho bước quan trọng.

Phải phân biệt **trải nghiệm hiển thị** với **quyết định tài chính**; không đặt sự an toàn của checkout lên một giá trị eventual cache nếu hợp đồng nghiệp vụ yêu cầu consistency mạnh.

### 12.3. Snapshot reporting

Một báo cáo có thể cố ý đọc snapshot tại thời điểm T dù DB thay đổi sau T. Đây **không phải lỗi stale cache** nếu semantics được mô tả rõ; nó là snapshot consistency.

Không cố refresh giữa chừng một báo cáo đòi snapshot nhất quán, vì có thể dẫn đến số liệu trộn nhiều thời điểm. Điều chỉnh isolation/transaction boundary theo yêu cầu báo cáo.

### 12.4. Eventual consistency của nhiều services

External service B cập nhật DB rồi publish event ProductPriceChanged. Service A nhận event và xóa L2/Redis entries.

~~~text
Service B                Database             Event Bus              Service A
    |                        |                    |                      |
    +-- UPDATE+COMMIT ------>|                    |                      |
    |                        |                    |                      |
    +-- publish event --------------------------->|                      |
    |                        |                    +-- notify ---------->|
    |                        |                    |                  evict cache
    |                        |                    |                      |
    |                        |<-------------------+-- next DB read ------+
~~~

Giữa commit và invalidation event luôn có thể có một cửa sổ stale. Nếu cần “đọc lập tức phải mới”, event-driven invalidation đơn thuần có thể chưa đủ; cần synchronous consistency protocol hoặc read bypass.

### 12.5. Không publish event trước commit

Nếu B publish ProductPriceChanged **trước khi UPDATE commit**, A có thể xóa cache rồi đọc lại DB **vẫn là giá cũ**, sau đó cache lại giá cũ; B mới commit. Đây là một race tạo stale data khó nhìn thấy.

Giải pháp đáng cân nhắc: **transactional outbox**, CDC của transaction log, hoặc publish-after-commit có recovery semantics phù hợp.

### 12.6. Invalidation event có thể đến trễ hoặc mất

Event bus có thể:
- Deliver trễ;
- Deliver trùng;
- Deliver không đúng thứ tự;
- Retry lâu;
- Mất sự kiện do cấu hình/bug;
- Service A offline tạm thời.

Muốn hệ thống chịu lỗi tốt, cân nhắc:
- Idempotent invalidation;
- Version trong event;
- Ordered processing theo entity key;
- Outbox + retry;
- TTL fallback;
- Reconciliation job;
- Metrics cho event lag.

**Không coi event phát đi là bằng chứng mọi node đã xóa cache xong.**

## 13. Invalidation cache đa node: chiến lược và đánh đổi

### 13.1. Invalidate theo ID

Khi biết Product#42 đã đổi:

~~~java
emf.getCache().evict(Product.class, 42L);
~~~

Nhanh và có phạm vi hẹp. Phù hợp với một update event mang chính xác Product ID.

Nhưng một consumer trên node A gọi JPA Cache.evict không nhất thiết evict cache node B. Cần broadcast hoặc cache provider distributed invalidation.

### 13.2. Invalidate cả region

Khi batch job sửa 1.000.000 Products và không có danh sách IDs:
 
~~~java
emf.getCache().evict(Product.class);
~~~

Có thể đúng hơn từng eviction không đầy đủ, nhưng làm giảm hit rate và tăng database traffic. Với một hệ nhiều nodes, cần gửi event region-invalidate tới tất cả nodes liên quan hoặc dùng cache infrastructure có khả năng đó.

### 13.3. Dùng TTL làm giới hạn stale window

Ví dụ cache entry có TTL 30 giây:
- External writer có thể đổi Product ngay sau lúc entry được cache;
- Nếu không có invalidation event, entry có thể stale gần 30 giây;
- Sau TTL, lần load mới có thể đọc DB.

TTL không phải cam kết chính xác nếu:
- Cache refresh-ahead tự gia hạn;
- Read từ replica chậm;
- L1 giữ entity lâu hơn TTL;
- Query cache có TTL khác;
- Có layers CDN/Redis khác.

Nếu nghiệp vụ yêu cầu freshness tối đa 5 giây, phải tính **tất cả tầng**, không chỉ một TTL L2.

### 13.4. Versioned cache keys

Một mô hình:

~~~text
Product#42:version=8
Product#42:version=9
~~~

giúp tránh ghi đè nhầm bản cũ khi consumer có version mới. Nhưng client phải biết **version hiện hành** để tạo key; nếu current version lại được cache stale, vấn đề vẫn còn.

Versioning event/cache keys giúp phân biệt generations, không tự giải quyết cách phát hiện DB đã đổi. Cần source version hoặc invalidation signal đáng tin.

### 13.5. Không cache những đường đọc cần strict freshness

Với một số operation quan trọng, giải pháp đơn giản nhất có thể là:
- Không bật L2/query cache cho entity nhạy cảm;
- Dùng EntityManager mới;
- CacheRetrieveMode.BYPASS;
- Đọc primary DB trong transaction phù hợp;
- Dựa vào DB constraints/optimistic locking cho writes.

Cache không bắt buộc phải có ở mọi entity. Đo hit rate và mức độ chịu stale trước khi quyết định cache dữ liệu thường xuyên bị external writers sửa.

### 13.6. Invalidation ordering

Ví dụ:
- Event v8 đến chậm;
- Event v9 đến trước;
- Consumer invalidate rồi đọc DB version=9;
- Event v8 sau đó cũng invalidate.

Evict đơn thuần thêm lần nữa thường không làm dữ liệu cũ quay lại, nhưng tạo cache miss. Nếu consumer lại **ghi một payload v8 trực tiếp vào cache sau v9**, có thể làm cache downgrade.

Với event payload chứa state, nên kiểm tra version monotonic hoặc dùng compare-and-set trên cache entry. Invalidation event chỉ mang ID thường đơn giản hơn cache update event chứa toàn bộ object.

### 13.7. Cache stampede

Sau evictAll, hàng nghìn requests có thể đồng thời truy vấn Product catalog. Có thể cần:
- Batching;
- Request coalescing/single-flight;
- TTL jitter;
- Rate limiting;
- Stale-while-revalidate **chỉ khi business cho phép**;
- Warm-up những keys quan trọng.

Không áp stale-while-revalidate cho số dư tài khoản hay kết quả quyết định quyền nếu nghiệp vụ yêu cầu dữ liệu authoritative.

## 14. CDC, outbox và external SQL: bảo đảm event đi cùng commit

### 14.1. Tại sao publish trực tiếp dễ lỗi?

Nếu một batch cập nhật 1.000 rows và publish events cho từng ID, nhưng service crash giữa UPDATE và publish:
- DB có thể đã commit;
- Không phải tất cả cache invalidation events được phát;
- Một số caches ở nodes khác tiếp tục giữ dữ liệu cũ.

Nếu publish trước commit, cache consumer có thể đọc state chưa mới. Cả hai là những khoảng trống consistency cần có thiết kế.

### 14.2. Transactional outbox

Một mẫu phổ biến:

~~~text
BEGIN TRANSACTION
    UPDATE products ...
    INSERT INTO outbox_events (
        event_id,
        aggregate_type,
        aggregate_id,
        event_type,
        version,
        payload
    ) VALUES (...)
COMMIT

Outbox publisher (retry/idempotent)
    → event bus
    → consumers evict Product cache
~~~

Cập nhật Product và ghi outbox event trong **cùng DB transaction** giúp tránh trường hợp DB commit nhưng event hoàn toàn không được ghi nhận. Consumer vẫn cần idempotency, event ordering và replay.

### 14.3. CDC từ database change log

Change Data Capture có thể đọc transaction log/redo/WAL để phát hiện thay đổi từ **bất kỳ writer** (tùy phạm vi cấu hình), gồm SQL scripts và dịch vụ khác.

Lợi ích:
- Không cần mọi SQL caller tự publish event;
- Có thể nhận diện UPDATE/DELETE/INSERT từ nhiều nguồn;
- Có transaction order/LSN hoặc metadata tương ứng;
- Hỗ trợ invalidation/reconciliation pipelines.

Rủi ro:
- CDC lag;
- Restart/replay;
- Snapshot bootstrap;
- Schema evolution;
- Duplicate/out-of-order delivery;
- Quyền đọc database logs và bảo mật;
- Mapping table changes tới JPA entity/cache regions.

Không coi CDC có nghĩa mọi reader luôn synchronous fresh. Đó thường là một pipeline **eventual invalidation**.

### 14.4. Phân biệt event cho dữ liệu và event cho cache

Một event nghiệp vụ:

~~~json
{
  "eventId": "e-123",
  "type": "ProductPriceChanged",
  "productId": 42,
  "version": 8
}
~~~

có thể được nhiều consumers dùng. Một event kỹ thuật:

~~~json
{
  "eventId": "invalidate-456",
  "type": "InvalidateProductCache",
  "productId": 42
}
~~~

chỉ nói “bỏ entry cache”. Cả hai có thể cần, nhưng phải phân định:
- Ai là nguồn sự thật;
- Consumer có nên đọc lại DB;
- Nếu event đến trễ thì làm gì;
- Schema có thay đổi khi thêm cột Product không;
- Cache nào (L2, Redis, REST response) thực sự nhận event.

### 14.5. Không chia sẻ trực tiếp JPA entity qua event

Không serialize một managed Product với lazy relationships vào event rồi dùng làm authoritative cache payload ở service khác. Nên dùng event DTO/schema độc lập, rõ version và fields, tránh vòng quan hệ và phụ thuộc Hibernate proxy.

## 15. Phân biệt stale JPA với dữ liệu trễ do read replica

Một hệ thống có primary và read replicas:

~~~text
External writer → Primary DB
                       |
                  replication
                       |
                 Read replica (lag)
                       |
                JPA read service
~~~

Có thể xảy ra:
- External writer commit trên primary price=120000;
- Service tạo EntityManager mới;
- L2 disabled, cache BYPASS;
- Đọc từ replica vẫn thấy 100000 vì replication chưa áp transaction.

Khi đó em.refresh/clear/evict cũng chưa giải quyết được nếu tất cả đều tiếp tục truy vấn replica đang trễ.

### 15.1. Cách chẩn đoán

- Xác minh datasource/connection URL và read-write routing;
- Query trực tiếp cùng Product#42 trên primary và replica;
- Ghi nhận commit LSN/replication lag theo DB;
- Kiểm tra transaction snapshot/isolation;
- Chạy test đọc trên primary với fresh context và cache bypass;
- Không vô tình dùng connection pool A cho write và pool B cho read.

### 15.2. Read-your-writes routing

Một vài kiến trúc dùng chính sách **đọc primary trong khoảng sau write** hoặc **đợi replica bắt kịp commit token**. Đây là chiến lược datasource/DB replication, không phải EntityManager.refresh tự hỗ trợ.

Nếu API yêu cầu đọc chính xác phiên bản đã commit, cần cơ chế read-after-write nhất quán từ hạ tầng, không chỉ cache invalidation.

### 15.3. L1 stale và replica lag có thể cùng tồn tại

Một Product stale được giữ trong L1; ngay cả khi clear, DB replica vẫn cũ. Khi replica bắt kịp, L2 cũ có thể lại tiếp tục trả giá cũ. Điều này minh họa lý do **phải xác định nguyên nhân ở từng tầng** trước khi chọn giải pháp.

## 16. Spring Data JPA: đóng gói đường đọc cần dữ liệu mới

Một ứng dụng Spring nên có contract rõ về việc đọc qua cache hoặc từ nguồn authoritative, thay vì để controller tùy ý gọi refresh/clear trên những entity đã sử dụng.

### 16.1. DTO tách khỏi entity lifecycle

~~~java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductSnapshot(
    Long id,
    String sku,
    BigDecimal price,
    boolean active,
    Long version
) {
    public static ProductSnapshot from(Product p) {
        return new ProductSnapshot(
            p.getId(),
            p.getSku(),
            p.getPrice(),
            p.isActive(),
            p.getVersion()
        );
    }
}
~~~

Trả DTO giúp response không còn phụ thuộc lazy loading và dirty checking sau transaction. Nhưng **DTO không tự làm dữ liệu mới hơn**: cần quyết định context/cache/database đọc ở đâu.

### 16.2. Service đọc bỏ qua shared cache

~~~java
package com.example.catalog;

import jakarta.persistence.CacheRetrieveMode;
import jakarta.persistence.CacheStoreMode;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductReadService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public ProductSnapshot readCurrentProduct(Long id) {
        Product product = em.find(
            Product.class,
            id,
            Map.of(
                "jakarta.persistence.cache.retrieveMode",
                CacheRetrieveMode.BYPASS,
                "jakarta.persistence.cache.storeMode",
                CacheStoreMode.REFRESH
            )
        );

        if (product == null) {
            throw new IllegalArgumentException(
                "Product không tồn tại"
            );
        }

        return ProductSnapshot.from(product);
    }
}
~~~

**Điều kiện:** Chỉ có thể coi đây là một DB-oriented read nếu context **chưa giữ Product managed**, transaction có thể nhìn thấy external commit, và datasource đi tới primary/replica đủ mới. @Transactional mặc định có thể tham gia transaction của caller, nên không đảm bảo context mới trong mọi trường hợp.

### 16.3. Khi cần transaction mới

~~~java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    readOnly = true
)
public ProductSnapshot readAfterExternalCommit(Long id) {
    // Load trong một unit of work mới,
    // với cache bypass theo ví dụ trước.
}
~~~

Propagation là **org.springframework.transaction.annotation.Propagation**. Đây chỉ là thiết kế boundary, không phải lời khuyên luôn bật REQUIRES_NEW: nó có thể tăng nhu cầu DB connections, tách atomicity, vẫn chịu replica lag và cần Spring proxy thực sự áp transaction. Context cũ của caller vẫn có thể giữ Product stale.

### 16.4. Refresh nếu caller đã có managed entity

~~~java
@Transactional
public ProductSnapshot reloadManaged(Product p) {
    em.refresh(p);
    return ProductSnapshot.from(p);
}
~~~

Đoạn trên yêu cầu **p là managed trong chính persistence context** đang dùng. Nếu p detached, refresh có thể thất bại. Nếu p có dirty changes chưa flush, chúng có thể bị thay bởi DB state. Không dùng refresh như helper ngầm trên mọi đường đọc.

### 16.5. External writer và invalidation consumer

Khi một event phát sau external commit mang Product ID:

~~~java
public void onProductChanged(Long productId) {
    entityManagerFactory.getCache().evict(
        Product.class,
        productId
    );
}
~~~

Chỉ xóa shared entity entry của factory tương ứng; cần event bus/consumer trên mỗi node, xử lý duplicate, query cache/Redis invalidation nếu có, và không thể ép những EntityManagers đang mở tự refresh.

### 16.6. Native scalar query không sửa L1 stale

Nếu service dùng native SELECT price trực tiếp rồi vẫn tiếp tục sửa cùng managed Product cũ, object này không tự nhận giá mới. Không trộn một scalar vừa đọc DB với một managed snapshot cũ mà không xác định business consistency.

## 17. Chẩn đoán stale data theo từng tầng

Nên áp một quy trình có thứ tự thay vì evictAll ngay khi thấy giá cũ.

### 17.1. Xác minh external commit

Dùng một connection độc lập đọc **primary DB**:

~~~sql
SELECT id, price, active, version
FROM products
WHERE id = 42;
~~~

Xác định writer đã commit, bảng/schema/tenant/ID đúng, và trigger/procedure không đưa dữ liệu về giá trị khác. Nếu database chưa có giá mới, không cần sửa cache JPA.

### 17.2. Xem L1/persistence context

Kiểm tra:
- Product#42 đã được find trước external update chưa?
- EntityManager còn giữ object managed không?
- Có long-running @Transactional, Open EntityManager In View hoặc extended context không?
- Có pending changes chưa flush?
- Gọi find lại có trả chính reference cũ không?

Nếu context đang giữ object cũ, **refresh hoặc context mới** là hướng đầu tiên tùy nghiệp vụ.

### 17.3. Thử context mới

~~~java
EntityManager fresh = emf.createEntityManager();

try {
    Product p = fresh.find(Product.class, 42L);
    // Ghi nhận giá trị.
} finally {
    fresh.close();
}
~~~

Nếu context mới thấy giá đúng, có cơ sở nghi L1 ở context cũ. Nếu vẫn cũ, thử bypass L2 trong **một context chưa chứa Product#42**.

### 17.4. Thử bypass L2

~~~java
Product p = fresh.find(
    Product.class,
    42L,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS,
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.BYPASS
    )
);
~~~

Nếu BYPASS L2 cho giá mới, còn normal load cho giá cũ, cần kiểm tra L2 cache hit/eviction. Nhưng đừng gọi normal find trước và lại BYPASS trong cùng context rồi diễn giải hai kết quả như independent loads.

### 17.5. Thử evict entry rồi đọc bằng context mới

~~~java
emf.getCache().evict(Product.class, 42L);
~~~

Nếu vấn đề hết, cần một invalidation policy tự động từ external writers, không yêu cầu operator chạy cache eviction thủ công mãi.

### 17.6. Kiểm tra transaction isolation

Nếu transaction đang ở snapshot isolation hoặc REPEATABLE READ, nó có thể không thấy commit mới ngay cả khi L1/L2 đã sạch. Mở **transaction mới** sau commit rồi kiểm tra lại trên primary.

### 17.7. Kiểm tra query cache, Redis và replica

Nếu Product entity mới đúng nhưng danh sách active products vẫn sai, nghi query result cache. Nếu JPA đọc đúng nhưng HTTP API vẫn cũ, nghi cache ở Redis/gateway/CDN. Nếu primary đúng nhưng replica sai, nghi replication lag.

### 17.8. Kiểm tra @Version trước khi ghi

Sau external update, đọc DB version. Nếu cột giá đổi nhưng version vẫn cũ, external writer chưa tham gia optimistic locking. Invalidate cache **không đủ** để ngăn stale managed entity ở transaction khác ghi đè dữ liệu.

### 17.9. Bảng chẩn đoán

| Quan sát | Khả năng chính | Cần làm |
|---|---|---|
| Find trong cùng context trả object cũ | L1 identity map | refresh/detach/clear/context mới |
| Context mới cũ, BYPASS đúng | L2 stale | shared cache invalidation |
| Evict L2 vẫn cũ trong cùng EM | L1 vẫn managed | refresh hoặc detach |
| Refresh vẫn cũ trong transaction snapshot | Isolation | transaction mới |
| Fresh context + BYPASS vẫn cũ trên replica | Replication lag | read primary/consistency routing |
| Entity đúng nhưng query membership sai | Query result cache | provider query cache invalidation |
| Backend đúng nhưng API response cũ | Redis/CDN/gateway cache | invalidate tầng tương ứng |
| UPDATE JPA ghi đè external price | Writer bỏ @Version/old state | versioning và concurrency policy |
| Node A đúng, Node B cũ | Invalidation không propagate | cluster/event coordination |
| External SQL chưa commit | DB chưa có state mới | sửa writer transaction |
| Cache sau event v9 lại có v8 | Late payload overwrote cache | version-aware cache updates |

## 18. Anti-pattern và cách khắc phục

### 18.1. EvictAll để sửa transaction snapshot

~~~java
emf.getCache().evictAll();
~~~

không làm transaction cũ theo REPEATABLE READ tự nhìn thấy phiên bản mới; nó chỉ tạo cache misses.

### 18.2. Refresh trong mọi getter

~~~java
public BigDecimal getCurrentPrice(Product p) {
    em.refresh(p);
    return p.getPrice();
}
~~~

có thể phát SELECT liên tục, tăng DB load và ghi đè dirty changes. Chỉ refresh ở boundary được thiết kế.

### 18.3. Clear không thông báo caller

Một helper gọi em.clear giữa transaction có thể detach cả Customer/Order không liên quan, làm mất dirty changes chưa flush. Không clear toàn context vô điều kiện chỉ vì một Product stale.

### 18.4. Thread.sleep thay cache invalidation

~~~java
Thread.sleep(1000);
return em.find(Product.class, id);
~~~

Sleep không xóa L1, không đảm bảo L2 hết hạn và không chứng minh replica bắt kịp.

### 18.5. Cache eviction thay versioning

Nếu external writer không tăng @Version, JPA update dựa trên snapshot cũ vẫn có nguy cơ lost update. Cache freshness và write conflict là hai vấn đề độc lập.

### 18.6. Coi query cache eviction là Cache.evict

Standard **emf.getCache().evict(...)** chủ yếu hướng tới shared entity cache; không được bảo đảm xóa mọi provider-specific query cache region.

### 18.7. Coi event phát ra là invalidation hoàn tất

Event có thể bị chậm, mất hoặc đến không theo thứ tự. Cần outbox/CDC, retry/idempotency, TTL fallback và metrics khi cần.

### 18.8. Dùng L2/cache-aside như nguồn sự thật cho tiền/tồn kho

Nếu giá/stock/balance bị writers khác đổi mà cache không có consistency guarantees, nghiệp vụ quan trọng phải dựa trên DB atomic constraints/locking/concurrency strategy thay vì state cũ từ cache.

### 18.9. Cache key bỏ qua tenant/authorization

Nếu query result còn phụ thuộc tenant, locale hoặc pricing tier, cache key phải phản ánh security/variant scope. Cache invalidation không thay được authorization check và không sửa lỗi lộ dữ liệu do key không đầy đủ.

### 18.10. Thay đổi tất cả cache layers cùng lúc

Vừa tắt L2, đổi Redis TTL, tăng isolation và evictAll trong một deploy khiến khó xác định nguyên nhân. Hãy đo từng tầng, sửa phạm vi nhỏ nhất đáp ứng business consistency.

## 19. Kiểm thử tích hợp: external JDBC writer cập nhật DB

Một bài kiểm thử đáng tin phải có **hai đường truy cập dữ liệu độc lập**:
- **Reader A** qua EntityManager/JPA;
- **Writer B** qua JDBC connection hoặc một client SQL không đi qua JPA provider của A.

Nếu B cũng dùng một JPQL bulk query được provider biết, provider có thể tự invalidate một số cache regions; test ấy **không còn mô phỏng đầy đủ nguồn bên ngoài bypass JPA**.

### 19.1. Thiết lập môi trường

- Database thật hoặc Testcontainers cùng loại/version với production;
- Product fixture đã commit và có ID;
- DataSource trỏ cùng primary DB, nhưng B dùng **physical connection độc lập**;
- EntityManager A không được chia sẻ với thread khác;
- Transaction isolation được ghi rõ (ví dụ READ_COMMITTED để test refresh thấy B commit);
- L2/query cache được bật/tắt theo scenario cụ thể;
- Test đóng connections/EM và rollback trong finally;
- Không giả định JPA provider sẽ tự nhận một JDBC UPDATE ngoài EntityManager;
- SQL statements/parameters phải phù hợp dialect target.

### 19.2. Helper JDBC writer bên ngoài JPA

~~~java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class ExternalProductSqlWriter {

    private final DataSource dataSource;

    public ExternalProductSqlWriter(
            DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void updatePriceWithoutVersion(
            long productId,
            BigDecimal newPrice) throws SQLException {

        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);

            try (PreparedStatement ps = c.prepareStatement(
                    """
                    UPDATE products
                    SET price = ?
                    WHERE id = ?
                    """
            )) {
                ps.setBigDecimal(1, newPrice);
                ps.setLong(2, productId);

                int updated = ps.executeUpdate();
                if (updated != 1) {
                    throw new IllegalStateException(
                        "Không tìm thấy đúng Product"
                    );
                }

                c.commit();
            } catch (SQLException | RuntimeException ex) {
                c.rollback();
                throw ex;
            }
        }
    }
}
~~~

**Quan trọng:** JDBC connection này thực sự phải đứng ngoài transaction/persistence context của reader A. Trong Spring, nếu dùng DataSourceUtils hoặc TransactionAwareDataSourceProxy trong cùng thread, việc lấy connection có thể vô tình tham gia transaction đang hoạt động. Với integration test, quản lý writer connection/transaction tách biệt và xác nhận connection IDs khi cần.

### 19.3. Test L1 giữ Product cũ

~~~java
@Test
void externalJdbcCommitDoesNotRefreshManagedProduct()
        throws Exception {

    EntityManager a = emf.createEntityManager();

    try {
        a.getTransaction().begin();

        Product managed =
            a.find(Product.class, productId);

        BigDecimal originalPrice =
            managed.getPrice();

        externalWriter.updatePriceWithoutVersion(
            productId,
            new BigDecimal("120000.00")
        );

        // Object managed không tự đổi vì JDBC writer khác commit.
        assertEquals(
            0,
            originalPrice.compareTo(managed.getPrice())
        );

        Product again =
            a.find(Product.class, productId);

        assertSame(managed, again);

        a.getTransaction().rollback();
    } finally {
        if (a.getTransaction().isActive()) {
            a.getTransaction().rollback();
        }
        a.close();
    }
}
~~~

Fixture phải bảo đảm initialPrice khác 120000.00. Test này khẳng định **state managed không tự đổi**, không phải rằng DB chưa cập nhật.

### 19.4. Test refresh sau external commit

~~~java
@Test
void refreshReloadsExternalValueWhenTransactionCanSeeIt()
        throws Exception {

    EntityManager a = emf.createEntityManager();

    try {
        a.getTransaction().begin();

        Product managed =
            a.find(Product.class, productId);

        externalWriter.updatePriceWithoutVersion(
            productId,
            new BigDecimal("130000.00")
        );

        a.refresh(managed);

        assertEquals(
            0,
            new BigDecimal("130000.00")
                .compareTo(managed.getPrice())
        );

        a.getTransaction().rollback();
    } finally {
        if (a.getTransaction().isActive()) {
            a.getTransaction().rollback();
        }
        a.close();
    }
}
~~~

**Điều kiện:** test chạy trên isolation/path cho phép transaction A nhìn thấy external commit mới, chẳng hạn nhiều cấu hình READ_COMMITTED đọc primary. Với snapshot isolation cố định, kết quả có thể khác. Không dùng test này để tuyên bố refresh luôn xuyên qua MVCC snapshot.

### 19.5. Test em.clear không giữ dirty changes

~~~java
@Test
void clearDetachesManagedProduct() {
    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Product old = em.find(
            Product.class,
            productId
        );

        em.clear();

        assertFalse(em.contains(old));

        Product current =
            em.find(Product.class, productId);

        assertTrue(em.contains(current));

        em.getTransaction().rollback();
    } finally {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        em.close();
    }
}
~~~

Test này chỉ kiểm tra state transition. Để kiểm chứng **mất pending changes**, cần fixture và transaction riêng rồi so sánh DB sau khi clear/commit, tránh ảnh hưởng từ provider flush tự động hoặc các callbacks.

### 19.6. Test shared cache eviction

Một scenario dành cho provider có L2 thực sự bật:
1. Tạo EntityManager A, load Product#42, đóng A.
2. Xác nhận cache entry/metric nếu provider hỗ trợ; không mặc định entry luôn cache.
3. Dùng JDBC B update Product#42 và commit.
4. Tạo EntityManager C, quan sát state với read path bình thường.
5. Gọi emf.getCache().evict(Product.class, 42L).
6. Tạo EntityManager D, đọc lại Product theo transaction visibility phù hợp.
7. Đối chiếu với fresh read có retrieveMode=BYPASS.

Test cần phân biệt **supported caching scenario** và **provider không cache entity này**. Nếu L2 không bật, chuyện C đọc state mới không chứng minh eviction hoạt động; đó chỉ là DB read bình thường.

### 19.7. Test cache modes trên context mới

~~~java
@Test
void bypassSharedCacheOnFreshContext() {
    EntityManager em = emf.createEntityManager();

    try {
        Product product = em.find(
            Product.class,
            productId,
            Map.of(
                "jakarta.persistence.cache.retrieveMode",
                CacheRetrieveMode.BYPASS,
                "jakarta.persistence.cache.storeMode",
                CacheStoreMode.BYPASS
            )
        );

        assertNotNull(product);
    } finally {
        em.close();
    }
}
~~~

Kết quả correctness cần được so sánh với một external JDBC UPDATE đã commit và một SELECT trực tiếp trên primary DB. Test chỉ assertNotNull là **khung minh họa API**, chưa đủ chứng minh freshness.

### 19.8. Test optimistic conflict khi external writer tăng version

~~~java
@Test
void externalVersionIncrementRejectsStaleJpaUpdate()
        throws Exception {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Product stale =
            em.find(Product.class, productId);

        // Một JDBC connection độc lập:
        // UPDATE products
        // SET price=?, version=version+1
        // WHERE id=?;
        // COMMIT;
        externalWriter.updatePriceAndIncrementVersion(
            productId,
            new BigDecimal("140000.00")
        );

        stale.deactivate();

        assertThrows(
            PersistenceException.class,
            () -> {
                em.flush();
                em.getTransaction().commit();
            }
        );
    } finally {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        em.close();
    }
}
~~~

**updatePriceAndIncrementVersion** là helper cần triển khai tương tự JDBC writer ở phần trước, với SQL tăng numeric version trong cùng statement/transaction. Kiểu exception cần điều chỉnh theo provider/framework và điểm xung đột được ném; JPA có thể báo OptimisticLockException ở flush hoặc RollbackException ở commit.

Nếu B không tăng version, @Version của A có thể không phát hiện external price change; test này có thể được bổ sung để chứng minh tác động của version policy, không để chứng minh lost update xảy ra ở mọi provider.

### 19.9. Test query membership bị stale

Dữ liệu ban đầu:
- Product#42 active=true;
- Product#43 active=true.

B dùng JDBC:

~~~sql
UPDATE products
SET active = false,
    version = version + 1
WHERE id = 42;
COMMIT;
~~~

Với query cache được provider bật, thử query "all active products" trước và sau external update. Xác minh:
- Query cache có được sử dụng không;
- Những cache regions nào bị invalidated;
- Product#42 có còn trong IDs cache cũ không;
- Sau query-cache eviction hoặc TTL, membership có cập nhật không;
- L2 entity state có được làm mới riêng không.

Không dựa vào một test chỉ sửa price để đánh giá query cache membership.

### 19.10. Test transaction snapshot tách biệt cache

Trên DB hỗ trợ snapshot/repeatable-read behavior:
1. A bắt đầu transaction theo isolation yêu cầu và đọc Product;
2. B update/commit;
3. A clear/refresh/bypass L2 theo luồng phù hợp;
4. Quan sát A vẫn có thể đọc snapshot cũ;
5. A kết thúc transaction;
6. C mở transaction mới đọc primary;
7. C thấy version mới.

Test phải dùng cấu hình isolation thật; không giả định H2 và PostgreSQL/MySQL có behavior đồng nhất.

### 19.11. Test multi-node invalidation

Trong môi trường staging:
1. Node A và B đều đọc Product#42, có L2/local cache entries.
2. External job update Product#42 và commit.
3. Publish invalidation event.
4. Đợi consumer acknowledgments hoặc quan sát lag theo thiết kế.
5. Tạo read contexts mới trên cả hai nodes.
6. Kiểm tra version/price mới.
7. Thử khi Node B offline, event duplicate, event out-of-order.
8. Xác định bounded staleness khi không nhận event.

Một test chỉ chạy trong một JVM không chứng minh invalidation qua cluster.

## 20. Bài tập thực hành

Các bài tập dùng bảng products và entity Product đã trình bày. Với câu hỏi về cache, luôn chỉ ra **đang xét L1, L2, query cache hay snapshot database**, vì các tầng không có hành vi giống nhau.

### Bài 1. L1 và em.find

A gọi:

~~~java
Product p1 = em.find(Product.class, 42L);
~~~

Một JDBC writer khác UPDATE price và commit. A gọi lại:

~~~java
Product p2 = em.find(Product.class, 42L);
~~~

Tại sao **p1 == p2** có thể true và cả hai vẫn trả giá cũ? Cần làm gì nếu A muốn giữ chính reference p1?

### Bài 2. Refresh hay flush?

A giữ managed Product giá 100000; B bên ngoài commit giá 120000. A gọi em.flush(). Giá trong object A có tự trở thành 120000 không? So sánh chiều dữ liệu của flush và refresh.

### Bài 3. Refresh và dirty changes

A đã gọi product.changePrice(115000) nhưng chưa flush. Sau đó A gọi em.refresh(product). Điều gì có thể xảy ra với thay đổi 115000? Đề xuất cách tổ chức service để không âm thầm mất dữ liệu.

### Bài 4. Clear không giải quyết L2

A bật second-level cache và có Product#42 cached giá 100000. External SQL update/commit giá 120000. A gọi em.clear rồi em.find lại. Vì sao vẫn có thể nhận 100000? Hãy sửa luồng gồm cache invalidation hoặc BYPASS trên context thích hợp.

### Bài 5. Evict không giải quyết L1

A đang quản lý Product#42. Một event làm:

~~~java
emf.getCache().evict(Product.class, 42L);
~~~

Sau đó trong cùng EntityManager, A gọi em.find cùng ID. Có chắc A được object giá mới không? Vì sao?

### Bài 6. So sánh detach và clear

Một transaction đang quản lý Product#42, Customer#7 và Order#10. Chỉ Product#42 bị writer ngoài cập nhật. Khi nào nên dùng em.detach(product) thay vì em.clear()? Phân tích cascading detach và pending changes.

### Bài 7. Context mới

Đóng EntityManager A, tạo EntityManager B, đọc Product#42 sau external commit. B có chắc lấy DB row mới không nếu L2 đang stale? Hãy dùng cache retrieve mode và giải thích điều kiện L1.

### Bài 8. CacheRetrieveMode.BYPASS

Viết em.find(Product.class, id, properties) với:

~~~java
CacheRetrieveMode.BYPASS
~~~

Giải thích API này xử lý tầng cache nào và vì sao nó không tự refresh Product đã managed trong context.

### Bài 9. CacheStoreMode.REFRESH

Viết một lần load Product trong context sạch với retrieveMode=BYPASS và storeMode=REFRESH. Mục tiêu của REFRESH là gì? Nó có đồng nghĩa em.refresh(product) không?

### Bài 10. BYPASS/BYPASS

So sánh properties:
- retrieveMode=BYPASS, storeMode=REFRESH;
- retrieveMode=BYPASS, storeMode=BYPASS.

Trường hợp nào muốn cập nhật shared cache sau DB read, trường hợp nào không muốn tương tác L2? Những điều kiện nào vẫn gây stale?

### Bài 11. Cache.evict overloads

Giải thích khác biệt giữa:

~~~java
cache.evict(Product.class, 42L);
cache.evict(Product.class);
cache.evictAll();
~~~

Trong một batch sửa 10 Products biết IDs, lựa chọn nào có phạm vi nhỏ nhất? Nếu sửa 1.000.000 Products không biết IDs, tradeoff của region eviction là gì?

### Bài 12. Cache.contains

Nếu cache.contains(Product.class, 42L) trả true, có thể suy ra dữ liệu trong cache bằng database row hiện tại không? Cần cách nào kiểm tra freshness?

### Bài 13. Query cache stale membership

Query cache lưu danh sách active Product IDs [42,43]. Một JDBC writer đặt Product#42 active=false rồi commit. Chỉ evict Product#42 L2 có nhất thiết sửa danh sách IDs ở query cache không? Đề xuất test.

### Bài 14. Bulk SQL trong cùng ứng dụng

So sánh:
- JPQL bulk UPDATE qua EntityManager;
- Native SQL qua cùng provider;
- SQL chạy từ external psql/ETL.

Vì sao không được giả định cả ba loại mutation đều kích hoạt invalidation giống nhau?

### Bài 15. Lost update khi B không tăng version

Product#42 version=7, price=100000, active=true. A tải entity. B chạy:

~~~sql
UPDATE products SET price=120000 WHERE id=42;
~~~

rồi commit. A deactivate và flush. Viết hai dạng SQL UPDATE giả định mà provider A có thể sinh (update mọi columns vs dirty columns) và giải thích rủi ro khi version DB vẫn 7.

### Bài 16. External writer tăng version

Sửa SQL B để tăng numeric @Version cùng transaction. A vẫn giữ version=7. Khi A flush, điều gì thường xảy ra? Vì sao tăng version không tự làm mới L1/L2?

### Bài 17. Conditional update CAS

Viết SQL ngoài JPA có:

~~~sql
WHERE id = :id AND version = :expected_version
~~~

và tăng version nếu cập nhật. Nếu row count=0, hãy liệt kê nguyên nhân có thể ngoài concurrent edit khi query còn điều kiện tenant/status.

### Bài 18. @Version và trigger

DB trigger tăng version tự động trong khi Hibernate cũng tự tăng version. Các vấn đề gì có thể xảy ra nếu không cấu hình provider về DB-generated version? Thiết kế integration test INSERT, managed UPDATE, external SQL UPDATE và stale merge.

### Bài 19. Transaction REPEATABLE READ

A mở transaction snapshot, đọc giá 100000. B commit 120000. A gọi em.refresh nhưng vẫn thấy 100000. Vì sao đây không nhất thiết là cache bug? Hãy đề xuất cách đọc từ transaction mới.

### Bài 20. Replica lag

Một service đã tạo EntityManager mới, BYPASS L2, nhưng giá vẫn cũ. Primary DB trả 120000, replica trả 100000. Cache operations có giúp không? Cần thay đổi datasource routing/consistency requirement thế nào?

### Bài 21. Spring service đọc dữ liệu mới

Viết service method trả ProductSnapshot, dùng context phù hợp và cache retrieveMode=BYPASS. Phân tích những điều kiện mà tên method **readCurrentProduct** có thể gây hiểu nhầm nếu được caller gọi giữa transaction dài.

### Bài 22. Multi-node invalidation

Node A và Node B dùng L2 caches riêng. External job update Product#42 rồi chỉ Node A nhận event. User gọi Node B thấy giá cũ. Hãy thiết kế protocol giúp cả hai nodes invalidate cache và xử lý khi Node B tạm thời offline.

### Bài 23. Event đến không đúng thứ tự

Các events v8 và v9 bị reorder. Nếu consumer dùng payload để đặt cache state, v8 đến sau v9 có thể gây điều gì? So sánh cache invalidation event chỉ chứa ID với payload update và đề xuất version monotonic check.

### Bài 24. Publish trước commit

External service B publish ProductChanged rồi mới COMMIT SQL. Consumer A nhận event, evict và đọc giá cũ trước khi B commit, sau đó cache giá cũ. Hãy mô tả race và giải thích transactional outbox.

### Bài 25. CDC và ETL

Một batch ETL không biết cách publish event sau mỗi SQL row update. CDC từ transaction log có thể giúp gì? Những giới hạn nào vẫn tồn tại về lag, duplicate, schema changes và replay?

### Bài 26. TTL và bounded staleness

Một cache Product có TTL 30 giây. Business yêu cầu giá không cũ quá 5 giây. Có đủ không? Nếu thêm event invalidation, có thể cam kết 5 giây tuyệt đối không? Hãy xác định các điều kiện cần đo.

### Bài 27. Cache stampede

Sau một external migration, hệ thống gọi cache.evictAll rồi 50.000 requests cùng truy vấn Product. Có thể xảy ra vấn đề gì? Nêu các giải pháp request coalescing, TTL jitter, warm-up và rate limiting.

### Bài 28. Hiển thị giá khác checkout

Catalog UI được phép stale vài giây, nhưng checkout phải dùng giá authoritative hiện tại. Đề xuất hai đường đọc dữ liệu khác nhau và giải thích tại sao không dùng L2 stale để quyết định thanh toán.

### Bài 29. API caching và tenant

Một API trả Product có giá khác nhau cho Tenant A và Tenant B. Cache key chỉ là productId. Nguy cơ gì có thể xảy ra, và có liên quan trực tiếp đến JPA Cache.evict không? Hãy thiết kế key/authorization policy đúng.

### Bài 30. Thực hành two-writer integration test

Thiết kế:
1. Persist Product fixture, commit;
2. JPA EntityManager A load Product;
3. JDBC Connection B riêng UPDATE price và commit;
4. Assert managed Product A vẫn có state cũ;
5. em.refresh(A) trong READ_COMMITTED để quan sát giá mới;
6. Rollback/cleanup;
7. Test lần nữa với B tăng version, A dirty update và optimistic conflict.

Không dùng cùng EntityManager cho A và B; không để test fixture chưa commit.

### Bài 31. Test L2 cache

Bật L2 thực sự cho Product trong provider mục tiêu. Sau external JDBC commit:
- Đọc bằng context mới bình thường;
- Đọc với BYPASS L2;
- Evict entity cache;
- Đọc bằng context mới lần nữa.

Quan sát hit/miss, SQL và state. Vì sao test không có L2 bật không chứng minh cache eviction hiệu quả?

### Bài 32. Test query cache

Bật query cache provider-specific; query active Products. B thực hiện:
- UPDATE active=false cho một Product;
- INSERT Product active=true;
- DELETE Product khác.

Kiểm tra membership và entity states sau khi invalidation. Phân biệt query cache và L2.

### Bài 33. Test snapshot isolation

Tạo transaction A theo isolation snapshot, external writer B commit, rồi A refresh/clear/BYPASS. So sánh với transaction C mới. Giải thích vì sao kết quả phụ thuộc DB isolation và không phải lỗi JPA caching.

### Bài 34. Phân tích production incident

Một giờ sau batch update giá, 10% requests vẫn trả giá cũ. Có 5 application nodes, L2 local cache, Redis cache-aside và 2 read replicas. Hãy lập trình tự điều tra từng tầng:
- Writer commit;
- Primary/replica;
- Context lifetime;
- L2/Redis hits;
- Query cache;
- Invalidation event delivery;
- @Version;
- Metrics và logging.

### Bài 35. Chọn giải pháp đúng

Chọn giữa **refresh, detach/clear, L2 eviction, cache retrieve BYPASS, transaction mới, replica routing, event/CDC và versioning** cho từng tình huống:
1. Một managed Product stale trong transaction READ_COMMITTED;
2. EntityManager mới vẫn lấy giá cũ từ L2;
3. Query active Product chứa row bị archive;
4. REPEATABLE READ snapshot vẫn cũ;
5. Node B không nhận invalidation;
6. External SQL không tăng @Version;
7. API đọc từ replica chậm;
8. Client cần immediate read-after-write.

Không thể dùng cùng một thao tác cho tất cả.

## 21. Bảng tra cứu nhanh

| Mục tiêu | Cơ chế | Phạm vi và giới hạn |
|---|---|---|
| Làm mới managed entity | em.refresh(entity) | L1 entity; không phá DB transaction snapshot |
| Bỏ toàn context managed state | em.clear() | Detach toàn bộ entities; có thể mất dirty changes |
| Bỏ một managed entity | em.detach(entity) | Phạm vi hẹp; cascade theo mapping |
| Đọc bằng context mới | New EntityManager/transaction | Không tự bypass L2/replica |
| Xóa L2 entry theo ID | emf.getCache().evict(Entity.class, id) | L2 của factory/backend; không sửa L1 |
| Xóa L2 entity region | emf.getCache().evict(Entity.class) | Nhiều misses |
| Xóa L2 nhiều entity types | emf.getCache().evictAll() | Phạm vi rộng; không xóa mọi query cache |
| Kiểm tra L2 entry presence | emf.getCache().contains(Entity.class, id) | Không chứng minh freshness |
| Không đọc shared cache | CacheRetrieveMode.BYPASS | Không tự refresh L1 |
| Không ghi shared cache | CacheStoreMode.BYPASS | Không xóa entry cũ đã có |
| Làm mới shared cache khi load | CacheStoreMode.REFRESH | Không đồng nghĩa em.refresh |
| Kiểm soát query cache | Provider-specific invalidation/TTL | Không có API portable tương đương mọi provider |
| Bảo vệ stale writes | @Version + all writers honor version | Không tự invalidate caches |
| External SQL với version | SET version=version+1 / CAS WHERE version | Numeric version, test ORM compatibility |
| Đọc mới sau commit | Fresh context/transaction + primary read | Phụ thuộc isolation và routing |
| Propagate invalidation | Outbox/event bus/CDC | Có lag, retry, duplicate |
| Giới hạn stale window | TTL + monitoring | Không tự bảo đảm strict freshness |
| Đọc nhiều replicas | Consistency-aware routing/commit token | Ngoài phạm vi JPA |
| Xác định cache cause | Context mới + BYPASS + SQL stats | Cần DB/provider test thực |

## 22. Checklist trước khi xử lý dữ liệu cũ

### 22.1. Xác định nguồn và nhu cầu consistency

1. **External writer là ai?** JDBC, ETL, SQL script, stored procedure hay service khác?
2. **Writer đã COMMIT thật chưa?** Đã xác minh bằng connection mới trên primary?
3. **Đúng database/schema/tenant/row chưa?**
4. **Bản cập nhật ảnh hưởng field nào?** Có đổi status/soft delete/relationship không?
5. **Use case cần strict fresh, read-your-writes, bounded staleness hay snapshot?**
6. **Có đường đọc từ read replica không?** Replication lag đã được tính?
7. **Có business process dùng stale state để quyết định tiền/tồn kho/quyền không?**
8. **Có thể hạn chế cache chỉ ở những read paths cho phép stale không?**

### 22.2. First-level cache

9. **Entity đã managed trước writer ngoài chưa?**
10. **Có context dài hoặc Open EntityManager In View không?**
11. **em.find lần hai có trả cùng Java reference không?**
12. **Muốn giữ reference cũ hay có thể đọc instance mới?**
13. **Refresh có overwrite pending changes không?**
14. **Nếu detach/clear, có mất dirty changes của entities khác không?**
15. **Có cascade REFRESH/DETACH ảnh hưởng cả graph không?**
16. **Có cần transaction/context mới vì snapshot isolation không?**

### 22.3. Shared cache và query cache

17. **L2 thực sự bật và Product có được cache không?**
18. **SharedCacheMode/@Cacheable/provider cache regions đã hiểu chưa?**
19. **Có dùng Cache.evict đúng Entity type và key không?**
20. **Có nhầm em.clear với L2 eviction không?**
21. **Có nhầm L2 eviction với refresh managed entity không?**
22. **Có dùng cache.retrieveMode=BYPASS trên context sạch khi cần không?**
23. **Có dùng cache.storeMode=REFRESH/BYPASS đúng mục tiêu không?**
24. **Query cache có stale membership sau INSERT/DELETE/UPDATE không?**
25. **Provider hỗ trợ provider-specific query cache invalidation thế nào?**
26. **Các app nodes có nhận event invalidation như nhau không?**
27. **Ngoài JPA còn Redis/CDN/HTTP cache nào không?**

### 22.4. Versioning và transaction correctness

28. **Entity có @Version không?** Tất cả write paths có tham gia policy?
29. **External SQL có tăng numeric version đúng không?**
30. **Có tránh trigger tăng version hai lần với ORM không?**
31. **JPA update từ snapshot cũ có thể overwrite columns khác không?**
32. **Có DB constraints/optimistic checks cho business invariant không?**
33. **OptimisticLockException có rollback toàn unit of work không?**
34. **Có tránh retry y nguyên stale entity không?**
35. **Có mở transaction mới và tải state mới để reapply intent không?**
36. **Có phân biệt transaction snapshot stale với cache stale không?**

### 22.5. Invalidation và vận hành

37. **External writer có publish event sau commit không?**
38. **Nếu writer crash, outbox/CDC có đảm bảo eventual invalidation không?**
39. **Event consumer có idempotent và xử lý out-of-order không?**
40. **Có TTL fallback và stale-window metrics không?**
41. **EvictAll có gây cache stampede không?**
42. **Có thể invalidate theo ID thay vì cả region không?**
43. **Có monitoring cache hit/miss, replica lag và event lag không?**
44. **Có test trên DB/provider/cache backend giống production không?**
45. **Có tích hợp external JDBC writer không đi qua ORM trong test không?**
46. **Có test một managed entity stale và một context mới riêng biệt không?**
47. **Có test L2 và query cache riêng biệt không?**
48. **Có test optimistic conflict sau external writer tăng version không?**
49. **Có giới hạn log PII/SQL secrets trong observability không?**
50. **Có mô tả rõ sự khác biệt giữa “yêu cầu đọc mới” và “bảo đảm mới” không?**

### 22.6. Cây quyết định

~~~text
Ứng dụng thấy dữ liệu cũ sau external SQL COMMIT
                           |
                           v
             Đã xác minh primary DB mới?
                    |
            +-------+--------+
            |                |
           Chưa             Rồi
            |                |
      Kiểm tra writer        v
      commit/schema      Reader giữ managed entity?
                             |
                      +------+------+
                      |             |
                     Có            Không
                      |             |
               refresh/detach       v
               /clear hoặc     Context mới vẫn cũ?
               context mới          |
                            +-------+-------+
                            |               |
                           Có              Không
                            |               |
                    Bypass/evict L2    L1 là nguyên nhân
                    và query cache          chính
                            |
                            v
                  Bypass rồi vẫn cũ?
                            |
                   +--------+--------+
                   |                 |
                  Có                Không
                   |                 |
            Transaction snapshot    L2/query cache
            /replica lag / routing  invalidation
                   |
                   v
               Ghi tiếp?
                   |
                  Có
                   |
          Kiểm tra external writer
          có tăng @Version?
                   |
          +--------+---------+
          |                  |
         Không              Có
          |                  |
   Sửa version policy     Xử lý optimistic conflict
   + bảo vệ stale writes  và transaction rollback
~~~

## 23. Tổng kết

Khi **nguồn khác cập nhật trực tiếp cơ sở dữ liệu**, JPA không có lý do để tự động thay đổi mọi object đang sống trong các persistence contexts. Dữ liệu cũ có thể tồn tại ở nhiều tầng độc lập: **L1**, **L2**, **query cache**, cache của hệ thống phân tán, DB transaction snapshot và read replica.

Quy tắc quan trọng:

1. **Nếu cũ ở L1:** em.refresh cho managed entity cần cập nhật, hoặc em.detach/em.clear/context mới khi phù hợp. Không dùng em.find lại trong cùng context như một cam kết đọc DB; không dùng refresh/clear khi chưa hiểu dirty changes.
2. **Nếu cũ ở L2:** dùng Cache.evict theo key/region, hoặc CacheRetrieveMode.BYPASS/CacheStoreMode.REFRESH khi đọc trong context sạch. Không nhầm L2 eviction với L1 refresh và không mặc định Cache.evict dọn cả query cache.
3. **Nếu cũ vì transaction isolation hoặc replica lag:** thay đổi cache không đủ. Cần transaction mới, primary/read consistency routing hoặc chờ replica theo commit token thích hợp.
4. **Nếu có nguy cơ stale write:** external SQL phải tuân thủ @Version/CAS/version increment hoặc concurrency protocol tương đương. Cache invalidation không thay thế optimistic locking.
5. **Nếu có nhiều services/nodes:** thiết kế invalidation sau commit bằng event/outbox/CDC, xử lý lag/duplicate/out-of-order, TTL và monitoring theo consistency SLA.
6. **Nếu cần chứng minh correctness:** dùng integration test với external JDBC writer/connection độc lập, JPA EntityManager và DB/provider/cache backend phù hợp.

~~~text
External SQL UPDATE + COMMIT
            |
            +-- Database row mới
            |
            +-- L1 Product cũ?      → refresh / detach / clear
            |
            +-- L2 Product cũ?      → cache eviction / BYPASS
            |
            +-- Query result cũ?    → provider cache invalidation
            |
            +-- Replica/snapshot cũ?→ transaction/routing policy
            |
            +-- @Version chưa tăng? → sửa writer contract / CAS
            |
            +-- Nodes khác chưa biết? → outbox / CDC / event invalidation
~~~

**Bài học thực hành quan trọng nhất:** Không nên giải quyết tất cả dữ liệu cũ bằng cách “xóa sạch cache”. Hãy xác định tầng đang giữ state cũ, bảo vệ transaction và versioning khi ghi, rồi chọn một cơ chế làm mới/invalidation có phạm vi rõ và được kiểm chứng trên môi trường thực tế. Khi thiết kế đúng, ứng dụng vẫn tận dụng được lợi ích của cache mà không đánh đổi sự chính xác của dữ liệu quan trọng.









