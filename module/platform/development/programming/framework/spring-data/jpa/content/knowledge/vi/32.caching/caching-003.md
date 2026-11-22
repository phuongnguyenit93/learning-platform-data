# Chính sách truy cập cache cho Entity có thay đổi trong Spring Data JPA

## Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt **first-level cache (persistence context)**, **second-level cache** của Hibernate, **query cache** và **Spring Cache**.
2. Chọn chính sách đồng thời (cache concurrency strategy) cho **Entity có thể thay đổi**: `READ_WRITE`, `NONSTRICT_READ_WRITE` hoặc `TRANSACTIONAL`, đồng thời hiểu vì sao `READ_ONLY` không thích hợp.
3. Giải thích vòng đời đọc–sửa–`flush`–`commit` và việc cập nhật/vô hiệu hóa vùng cache.
4. Phối hợp `@Version`, ranh giới giao dịch, xóa cache và xử lý cập nhật ngoài Hibernate để giảm nguy cơ dữ liệu cũ (stale data).
5. Kiểm chứng cách hoạt động bằng ứng dụng Java 17+, Spring Data JPA, Hibernate, H2 và một JCache provider.

Trọng tâm là **Spring Data JPA dùng Hibernate làm JPA provider**. JPA định nghĩa một số thao tác cache chung, còn các chiến lược `READ_WRITE`, `NONSTRICT_READ_WRITE`, `READ_ONLY` và `TRANSACTIONAL` là cơ chế **cụ thể của Hibernate**, không phải từ khóa của `JpaRepository`.

## 1. Hiểu đúng các lớp cache trước khi chọn chính sách

| Lớp | Phạm vi | Được sử dụng khi nào? | Điểm cần nhớ |
| --- | --- | --- | --- |
| **L1 / Persistence Context** | Một `EntityManager` (Hibernate `Session`) | Tự động quản lý Entity được tải, `persist`, `merge` và dirty checking | Luôn gắn với ngữ cảnh persistence; không có annotation chính sách L2 nào thay thế L1. |
| **L2 / Second-level cache** | `EntityManagerFactory` / Hibernate `SessionFactory`, có thể được provider chia sẻ trên cluster | Đọc lại một Entity cacheable theo ID ở các session khác nhau | Cần cache provider + cấu hình opt-in + concurrency strategy; có vấn đề đồng thời cần quản lý. |
| **Query cache** | Cache kết quả truy vấn được chỉ định cacheable | Cần bật riêng và bật cho từng query | Không đồng nghĩa với cache toàn bộ Entity; dữ liệu thay đổi có thể làm kết quả query cache hết hiệu lực. |
| **Spring Cache** (`@Cacheable`, `@CacheEvict`) | Kết quả phương thức Spring/service theo key | Khi code sử dụng Spring Cache abstraction | Độc lập với bộ nhớ đệm L1/L2 của Hibernate; cần chính sách invalidation riêng. |

Sơ đồ minh họa khi tìm theo khóa chính:

```text
TX A / EntityManager A
  findById(10)
    ├─ L1 có Entity? → trả đối tượng đang được quản lý
    └─ L1 miss → L2 có dữ liệu hợp lệ? → tái tạo Entity trong L1
                   └─ L2 miss → SELECT database → đưa Entity vào L1
                                                   └─ có thể put vào L2

TX B / EntityManager B
  findById(10)
    ├─ L1 của B (khác L1 của A)
    └─ L2 dùng chung trong cùng SessionFactory → có thể cache hit
```

**Quan trọng:** Khi gọi `findById` hai lần trong **cùng một giao dịch/EntityManager**, việc không xuất hiện SQL lần thứ hai có thể hoàn toàn do **L1**, không chứng minh L2 hoạt động. Muốn đo L2, thử trong **hai giao dịch/persistence context tách biệt** và xem Hibernate statistics hoặc SQL.

Khi gọi các phương thức truy vấn theo điều kiện như `findByStatus(...)`, Hibernate thường vẫn phải thực thi truy vấn để biết ID phù hợp; việc Entity có L2 cache **không tự biến mọi truy vấn thành truy vấn được cache**.

## 2. Vì sao Entity có thay đổi cần chính sách đồng thời?

Giả sử `Product` có ID `10`, `price=100` và nằm trong L2 cache. Hai giao dịch xảy ra:

```text
Thời điểm      TX A: cập nhật Product #10       TX B: đọc Product #10
t0             —                                L2 đang chứa price=100
t1             LOAD / thay price thành 120      —
t2             Chưa commit                      Đọc trong lúc A đang ghi
t3             COMMIT thành công                —
t4             —                                Đọc lại sau khi A commit
```

Nếu L2 vẫn trả dữ liệu cũ sau commit, TX B có thể dùng `price=100` dù database đã là `120`. Vấn đề cũng nảy sinh khi một transaction đọc dữ liệu trong lúc transaction khác cập nhật. Chiến lược cache quyết định **có cho phép đọc cache, chặn ghi cache tạm thời, hoặc invalidation** ở các thời điểm này.

Không một chính sách L2 nào có thể thay thế hoàn toàn **isolation của database**, **khóa dữ liệu**, **`@Version`** hoặc thiết kế giao dịch đúng. Đặc biệt, lần đọc trong một EntityManager đã quản lý `Product#10` có thể vẫn thấy object cũ từ L1, bất kể L2 đã bị evict.

## 3. Bốn chính sách Hibernate: chọn theo tần suất cập nhật và yêu cầu nhất quán

Hibernate sử dụng `org.hibernate.annotations.Cache` với enum `org.hibernate.annotations.CacheConcurrencyStrategy`.

| Chính sách | Có cho phép cập nhật Entity đã cache? | Cơ chế chính | Phù hợp |
| --- | --- | --- | --- |
| `READ_ONLY` | **Không** — dành cho dữ liệu bất biến | Truy cập cache đơn giản, không hỗ trợ cập nhật bản ghi đã cache | Danh mục bất biến / dữ liệu tham chiếu gần như không bao giờ đổi |
| `NONSTRICT_READ_WRITE` | **Có** | Không dùng soft lock; invalidation xung quanh việc cập nhật | Đọc nhiều, cập nhật cực hiếm; chấp nhận một cửa sổ đọc dữ liệu cũ |
| `READ_WRITE` | **Có** | Sử dụng **soft lock** ở cache trong lúc hoàn tất cập nhật, để giao dịch khác tránh đọc/ghi entry chưa an toàn | Entity có thay đổi, ghi không quá dày, cần giảm nguy cơ dữ liệu cũ |
| `TRANSACTIONAL` | **Có**, nếu provider hỗ trợ | Dựa vào **transactional cache provider** tích hợp với JTA/XA | Hệ thống có giao dịch cache–database được phối hợp và provider hỗ trợ thực sự |

### 3.1. READ_ONLY — không dùng cho Entity mutable

```java
@Cache(usage = CacheConcurrencyStrategy.READ_ONLY)
```

Dành cho đối tượng không thay đổi. Nếu cố cập nhật một thực thể đã cache theo `READ_ONLY`, Hibernate có thể ném exception. Không chọn `READ_ONLY` chỉ để có hiệu năng tốt cho Entity đang cho phép sửa giá, trạng thái hoặc số lượng. `@Immutable` (Hibernate) còn có ý nghĩa riêng về dirty checking/khả năng sửa, không nên thêm vào một Entity được thiết kế để ghi.

### 3.2. NONSTRICT_READ_WRITE — đơn giản nhưng cho phép cửa sổ stale

```java
@Cache(usage = CacheConcurrencyStrategy.NONSTRICT_READ_WRITE)
```

Thích hợp khi cập nhật rất hiếm và business **chấp nhận eventual consistency** ở cửa sổ ngắn. Hibernate invalidates entry quanh thời điểm cập nhật; vì không có cơ chế soft lock, giao dịch khác có thể đọc hoặc nạp vào cache một phiên bản chưa phải mới nhất trong lúc cập nhật hoàn tất. **TTL chỉ giới hạn thời gian giữ entry theo chính sách provider**, không tự bảo đảm một lần đọc sẽ thấy dữ liệu mới ngay sau commit.

Ví dụ chấp nhận được: cấu hình hiển thị phụ ít thay đổi, chỉ cần cập nhật tương đối nhanh. Ví dụ nên tránh: tồn kho, số dư, trạng thái thanh toán hoặc hạn mức cần độ chính xác cao.

### 3.3. READ_WRITE — lựa chọn thường cân nhắc đầu tiên cho Entity mutable

```java
@Cache(usage = CacheConcurrencyStrategy.READ_WRITE)
```

Trong giai đoạn hoàn tất giao dịch sửa dữ liệu, Hibernate dùng **soft lock** (một marker trong cache) để ngăn transaction khác đọc entry cũ từ cache hoặc đưa entry có thể đã cũ trở lại cache. Khi gặp soft lock, reader có thể **cache miss và truy vấn database**, chứ không nhất thiết bị block như khóa row trong SQL.

`READ_WRITE` giảm lỗi stale cache với các cập nhật qua Hibernate, nhưng **soft lock không phải khóa database**, không thay thế `@Version`, và không cam kết mức isolation `SERIALIZABLE`. Theo tài liệu Hibernate, `READ_WRITE` và `NONSTRICT_READ_WRITE` không tương thích với mô hình transaction isolation serializable. Nếu business yêu cầu tính nhất quán rất mạnh trên dữ liệu ghi dày, trước hết cân nhắc **không dùng L2 cho Entity đó**.

### 3.4. TRANSACTIONAL — chỉ khi hạ tầng thực sự hỗ trợ

```java
@Cache(usage = CacheConcurrencyStrategy.TRANSACTIONAL)
```

Cần cache provider hỗ trợ **transactional caching** và khả năng phối hợp giữa cache và database qua **JTA/XA** hoặc cơ chế tương đương mà provider tuyên bố. Chỉ đổi enum sang `TRANSACTIONAL` không biến Caffeine/Ehcache thông thường thành bộ nhớ đệm XA. Với ứng dụng Spring Boot + JPA transaction thông dụng (`JpaTransactionManager`) không có cache provider giao dịch tương thích, **không chọn** chiến lược này theo suy đoán.

## 4. Cấu hình Entity mutable dùng READ_WRITE

Ví dụ Entity cập nhật tên hàng hóa, có cột version để bảo vệ khỏi ghi đè đồng thời:

```java
package com.example.cache;

import jakarta.persistence.Cacheable;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@Table(name = "inventory_items")
@Cacheable
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "inventory-items"
)
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Column(nullable = false)
    private String description;

    protected InventoryItem() {
        // JPA cần constructor không đối số.
    }

    public InventoryItem(String description) {
        this.description = description;
    }

    public Long getId() {
        return id;
    }

    public long getVersion() {
        return version;
    }

    public String getDescription() {
        return description;
    }

    public void rename(String newDescription) {
        this.description = newDescription;
    }
}
```

Trong ví dụ:
- `@Cacheable` là annotation **JPA** cho biết đối tượng đủ điều kiện đưa vào shared cache tùy cache mode/provider.
- `@Cache(usage = READ_WRITE)` là annotation **Hibernate** chọn concurrency policy và vùng `inventory-items`.
- `@Version` cho optimistic locking ở **database**, bảo vệ khỏi hai lần cập nhật dựa trên cùng phiên bản dữ liệu. Nó **khác soft lock của L2**.
- `description` là trạng thái mutable; method `rename` thay đổi object managed. Hibernate dirty checking sẽ phát hiện và flush khi commit một transaction ghi.

Đặt annotation Hibernate `@Cache` ở entity root đối với inheritance hierarchy; không tùy tiện đặt cùng loại ở các subclass. Thêm `@Cache` chỉ là khai báo eligibility: muốn L2 chạy cần cấu hình một **cache provider** (JCache, Infinispan hoặc provider tương thích).

## 5. Ví dụ chạy độc lập: Spring Boot + Hibernate L2 + Caffeine JCache + H2

Ví dụ dùng **Java 17**, Maven, **Spring Boot 3.5.16**, Hibernate do Spring Boot quản lý, **Caffeine JCache 3.2.4** và H2 trong bộ nhớ. Mục tiêu là quan sát một entity sau khi đổi tên và đo L2 hit giữa các giao dịch. Đây là **cấu hình học tập một JVM**; cách tạo region tự động bên dưới không đủ giới hạn bộ nhớ/TTL cho production.

Cấu trúc:

```text
mutable-cache-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/cache/
    │   ├── InventoryItem.java
    │   ├── InventoryItemRepository.java
    │   └── CacheDemoApplication.java
    └── resources/application.properties
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mutable-cache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.hibernate.orm</groupId>
            <artifactId>hibernate-jcache</artifactId>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>jcache</artifactId>
            <version>3.2.4</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/com/example/cache/InventoryItem.java`**: dùng nguyên mã entity ở mục 4, cùng package `com.example.cache`.

**`src/main/java/com/example/cache/InventoryItemRepository.java`**

```java
package com.example.cache;

import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryItemRepository
        extends JpaRepository<InventoryItem, Long> {
}
```

**`src/main/java/com/example/cache/CacheDemoApplication.java`**

```java
package com.example.cache;

import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class CacheDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(
            InventoryItemRepository repository,
            PlatformTransactionManager transactionManager,
            EntityManagerFactory entityManagerFactory) {

        return args -> {
            TransactionTemplate tx = new TransactionTemplate(transactionManager);

            Long id = tx.execute(status ->
                    repository.saveAndFlush(new InventoryItem("Old")).getId());

            // Chỉ evict L2 sau giao dịch tạo để lượt đọc đầu tiên là cache miss.
            entityManagerFactory.getCache().evict(InventoryItem.class, id);

            Statistics stats = entityManagerFactory
                    .unwrap(SessionFactory.class)
                    .getStatistics();
            stats.clear();

            // Hai transaction khác nhau => hai persistence context khác nhau.
            String first = tx.execute(status ->
                    repository.findById(id).orElseThrow().getDescription());

            String second = tx.execute(status ->
                    repository.findById(id).orElseThrow().getDescription());

            long l2HitsAfterReads = stats.getSecondLevelCacheHitCount();

            long oldVersion = tx.execute(status ->
                    repository.findById(id).orElseThrow().getVersion());

            tx.executeWithoutResult(status -> {
                InventoryItem managed =
                        repository.findById(id).orElseThrow();
                managed.rename("New");
                // Không cần gọi save: dirty checking khi transaction commit.
            });

            String afterUpdate = tx.execute(status ->
                    repository.findById(id).orElseThrow().getDescription());

            long newVersion = tx.execute(status ->
                    repository.findById(id).orElseThrow().getVersion());

            System.out.println("first=" + first);
            System.out.println("second=" + second);
            System.out.println("l2HitAfterTwoReads=" + (l2HitsAfterReads > 0));
            System.out.println("afterUpdate=" + afterUpdate);
            System.out.println("versionIncreased=" + (newVersion > oldVersion));
        };
    }
}
```

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:cachedemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=false

spring.jpa.properties.hibernate.cache.use_second_level_cache=true
spring.jpa.properties.hibernate.cache.region.factory_class=jcache
spring.jpa.properties.hibernate.javax.cache.provider=com.github.benmanes.caffeine.jcache.spi.CaffeineCachingProvider
spring.jpa.properties.hibernate.javax.cache.missing_cache_strategy=create
spring.jpa.properties.hibernate.generate_statistics=true
```

**Chạy:**

```bash
mvn spring-boot:run
```

Sau log khởi động có các dòng chẩn đoán sau khi cấu hình JCache chạy đúng:

```text
first=Old
second=Old
l2HitAfterTwoReads=true
afterUpdate=New
versionIncreased=true
```

Giải thích:

1. Giao dịch tạo mới lưu `Old`; lệnh `evict(InventoryItem.class, id)` xóa bản sao L2 để thí nghiệm bắt đầu từ trạng thái rõ ràng.
2. Giao dịch đọc thứ nhất cache miss rồi lấy `Old` từ DB; khi đủ điều kiện, Hibernate đưa dữ liệu vào L2.
3. Giao dịch đọc thứ hai dùng persistence context mới; nếu provider hoạt động, thống kê `getSecondLevelCacheHitCount()` tăng. Biến `l2HitsAfterReads` đo trước các giao dịch đọc/sửa tiếp theo để không lẫn số hit.
4. Giao dịch ghi tải entity managed, gọi `rename("New")`; khi flush/commit, Hibernate cập nhật DB và vùng cache theo `READ_WRITE`.
5. Giao dịch sau commit thấy `New`; `@Version` được tăng khi có thay đổi thực sự.

Số lượng cache hit/miss/put tuyệt đối, số câu SQL và thứ tự log phụ thuộc provider, phiên bản và cách tối ưu; đoạn in ở trên chỉ chuyển **có ít nhất một hit** thành boolean. Nếu hiện `l2HitAfterTwoReads=false`, cần kiểm tra dependency `hibernate-jcache`, provider, region, trạng thái cache và việc tách persistence context; không kết luận L2 chỉ từ việc thiếu SQL.

**Giới hạn cấu hình demo:** `hibernate.javax.cache.missing_cache_strategy=create` cho phép tự tạo vùng cache chưa khai báo; vùng mặc định có thể thiếu giới hạn số phần tử và TTL. Trong production, khai báo vùng cache, giới hạn kích thước, expiry/eviction và giám sát cho từng provider; cân nhắc `missing_cache_strategy=fail` để phát hiện cấu hình region thiếu.

## 6. Dòng thời gian sửa Entity có READ_WRITE

```text
TX1: READ Product#10
  EntityManager/L1 miss → L2 hit hoặc DB → object managed

TX2: UPDATE Product#10
  load trong L1 → sửa property → dirty checking tại flush
  → SQL UPDATE (kiểm tra @Version nếu có)
  → commit thành công
  → Hibernate/provider xử lý entry L2 bằng READ_WRITE, soft lock
     và cập nhật/invalidate theo chu kỳ hoàn tất giao dịch

TX3: READ Product#10 sau commit TX2
  L1 mới → L2 hợp lệ thì dùng L2; nếu miss thì SELECT DB
```

Điểm quan trọng về thời gian:
- **Đang sửa nhưng chưa flush:** object trong L1 đã đổi giá trị; database có thể vẫn giữ bản cũ.
- **Flush chưa đồng nghĩa commit:** SQL có thể đã gửi nhưng transaction khác còn bị chi phối bởi transaction isolation. Không lấy `flush()` làm tín hiệu phát sự kiện invalidation ra ngoài khi ghi có thể rollback.
- **Sau commit thành công:** Hibernate mới có cơ sở hoàn tất đồng bộ cache theo chính sách, nhưng không có cam kết tuyệt đối về thứ tự quan sát giữa các hệ thống/instance và các cơ chế cache khác nhau.
- **Rollback:** dữ liệu DB không được coi là cập nhật thành công; không thiết kế manual cache put chứa dữ liệu chưa commit.

## 7. @Version bảo vệ cập nhật đồng thời — không bị thay thế bởi cache

Giả sử hai giao dịch đều đọc `Product#10, version=3`:

```text
TX A                                    TX B
đọc version=3                          đọc version=3
đổi price=120                          đổi price=130
UPDATE ... WHERE id=10 AND version=3   —
DB ghi price=120, version=4             UPDATE ... WHERE id=10 AND version=3
COMMIT                                  0 row updated → optimistic locking failure
```

Khi dùng `@Version`, Hibernate kiểm tra phiên bản lúc update/flush và phát hiện bản ghi bị sửa từ giao dịch khác. Spring có thể dịch lỗi JPA/Hibernate sang exception thuộc nhóm `ObjectOptimisticLockingFailureException`; thời điểm xuất hiện có thể ở `flush` hoặc `commit`. Cách xử lý là rollback và tải lại dữ liệu để người dùng quyết định retry/giải quyết xung đột; **không chỉ retry mù** một giao dịch thanh toán.

**Soft lock của `READ_WRITE`** bảo vệ việc sử dụng entry của L2 trong khoảng cập nhật; **optimistic locking `@Version`** ngăn ghi đè dữ liệu theo phiên bản trong database. Hai cơ chế xử lý hai vấn đề khác nhau.

## 8. Bulk UPDATE/DELETE, native SQL và thay đổi từ hệ thống ngoài

### 8.1. JPQL bulk update không sửa object đang managed

```java
package com.example.cache;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryItemRepository
        extends JpaRepository<InventoryItem, Long> {

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update InventoryItem i
           set i.description = :description
         where i.id = :id
        """)
    int bulkRename(
            @Param("id") Long id,
            @Param("description") String description);
}
```

Đây là **biến thể mở rộng của repository trong demo**, không thêm interface thứ hai cùng tên vào project. Gọi `bulkRename` trong một transaction ghi (ví dụ service gắn `@Transactional`).

Bulk JPQL chạy trực tiếp tại database: **không gọi setter trên các Entity đang nằm trong persistence context và không dirty-check từng object**. `clearAutomatically=true` giúp giải phóng object có thể đã cũ ở L1 sau bulk operation; `flushAutomatically=true` flush các thay đổi đang chờ trước khi chạy bulk query. Hibernate có cơ chế invalidation L2/query cache cho không gian bảng bị tác động bởi bulk HQL/JPQL, nhưng hành vi cụ thể phụ thuộc loại câu lệnh và provider — đừng coi đó là cơ chế đồng bộ mọi cache tùy biến.

Một lỗi khó thấy: bulk JPQL update như trên **không tự tăng `@Version`** theo cách cập nhật entity managed thông thường. Nếu business cần optimistic locking với bulk update, phải viết điều kiện version và tăng version phù hợp, hoặc tránh bulk update cho luồng đó. Ví dụ ý tưởng kiểm tra phiên bản:

```java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
    update InventoryItem i
       set i.description = :description,
           i.version = i.version + 1
     where i.id = :id
       and i.version = :expectedVersion
    """)
int bulkRenameIfVersionMatches(
        @Param("id") Long id,
        @Param("expectedVersion") long expectedVersion,
        @Param("description") String description);
```

Kiểm tra kết quả `int updated`: nếu `0` thì có thể không tồn tại ID hoặc version đã đổi; ứng dụng phải xác định và xử lý xung đột. **Đừng dùng bulk statement kiểu này đồng thời với manual update trên cùng row khi chưa có chiến lược transaction rõ ràng.**

### 8.2. Native SQL và cập nhật ngoài Hibernate

Câu SQL do JDBC khác, trigger, job, ETL hoặc service khác thực thi có thể sửa dữ liệu **mà L2 cache hiện tại không biết**. Hibernate không tự phát hiện mọi thay đổi ngoài tiến trình. Native query do Hibernate quản lý có các cơ chế đồng bộ/invalidation riêng, nhưng không áp dụng giả định đó cho SQL chạy từ bên ngoài Hibernate.

Khi biết chắc Entity cụ thể đã đổi **sau commit**, có thể chủ động evict L2:

```java
entityManagerFactory.getCache().evict(InventoryItem.class, itemId);
```

Hoặc xóa toàn bộ dữ liệu thuộc class/region qua API tương thích nếu tác động nhiều ID. **Evict L2 không xóa L1 đang quản lý object**. Khi cùng EntityManager đã đọc object cũ, cần cân nhắc:

```java
entityManager.refresh(managedItem); // tải lại trạng thái từ database
// hoặc entityManager.clear();      // detach toàn bộ entity đang managed
```

`refresh` có thể ghi đè trạng thái chưa flush của entity đó; `clear` detach toàn bộ entity và các thay đổi chưa flush có thể bị mất. Chỉ dùng khi bạn hiểu ranh giới transaction và đối tượng đang được quản lý.

API `EntityManagerFactory.getCache().evict(...)` có tác dụng loại entry **ngay lập tức**, không phải bản thân nó là cơ chế phối hợp commit/rollback. Nếu yêu cầu “chỉ evict khi cập nhật thành công”, hãy phát event xử lý **after commit** hoặc dùng cơ chế đồng bộ transaction tương thích. Ở hệ thống nhiều node, sự kiện phải đến đúng các instance/provider cần invalidation; cache local trên từng JVM không tự đồng bộ chỉ nhờ `@Cache(READ_WRITE)`.

## 9. Query cache và Spring Cache có cần cập nhật riêng không?

**Query cache của Hibernate** được bật bằng:

```properties
spring.jpa.properties.hibernate.cache.use_query_cache=true
```

Nhưng cờ này **chưa làm mọi query được cache**; truy vấn phải được đánh dấu cacheable (qua API Hibernate/JPQL hints tương thích). Hibernate dùng vùng kết quả truy vấn cùng cơ chế theo dõi logical timestamp cập nhật bảng, ví dụ các region nội bộ `default-query-results-region` và `default-update-timestamps-region`, để quyết định kết quả nào đã cũ. Không cấu hình expiry cho timestamp region theo cách khiến bản ghi theo dõi timestamp biến mất sớm hơn kết quả query; Hibernate cảnh báo vùng update timestamps không nên expire/evict theo chính sách thông thường. Truy vấn đổi tham số liên tục hoặc bảng ghi thường xuyên có thể có hit rate thấp, tốn thêm bộ nhớ và chi phí invalidation.

**Spring Cache** là hệ riêng. Ví dụ service dùng `@Cacheable("item-view")` để cache DTO vẫn có thể trả DTO cũ nếu Hibernate đã cập nhật L2 nhưng Spring Cache chưa bị xóa. Cần `@CacheEvict` / update value đúng key và thời điểm commit; tránh cache trực tiếp entity managed qua Spring Cache khi các đối tượng có thể bị mutate/detach và quan hệ lazy-loading. Spring Cache thường phù hợp hơn với DTO bất biến, có chiến lược key/TTL/invalidation rõ ràng.

## 10. Quy trình chọn chính sách an toàn

1. **Xác định Entity có phải bất biến không.** Nếu bất biến thật và không có đường update, `READ_ONLY` có thể phù hợp; nếu có nghiệp vụ sửa, không dùng.
2. **Đo tỷ lệ đọc/ghi và chi phí SELECT theo ID.** L2 hữu ích nhất khi đọc lặp lại theo ID qua nhiều EntityManager và ghi hiếm. Nếu ghi nhiều hoặc query dữ liệu đa điều kiện, lợi ích L2 có thể thấp.
3. **Xác định mức stale data mà business chấp nhận.** Không chấp nhận dữ liệu cũ cho số dư/tồn kho/hạn mức quan trọng → xem xét DB transaction, `@Version`, khóa thích hợp và có thể **không cache entity đó**.
4. **Nếu mutable, ghi không quá thường xuyên và cần kiểm soát cache khi cập nhật qua Hibernate**, bắt đầu đánh giá `READ_WRITE` cùng provider có support.
5. **Nếu ghi cực hiếm và có thể chấp nhận một khoảng dữ liệu cũ**, cân nhắc `NONSTRICT_READ_WRITE` sau khi thử concurrency.
6. **Chỉ chọn `TRANSACTIONAL`** khi đã kiểm tra provider/transaction manager hỗ trợ JTA/XA hoặc mô hình giao dịch cache–DB tương thích end-to-end.
7. **Liệt kê mọi đường ghi:** `save` trên managed entity, JPQL bulk, native SQL, batch job, các service khác và thao tác trực tiếp database. Với đường ghi ngoài Hibernate, thiết kế after-commit invalidation hoặc cache TTL/ràng buộc nhất quán phù hợp.
8. **Định nghĩa vùng cache:** memory cap, eviction policy, TTL, serializer, monitoring, behavior khi node mất liên lạc, cách tương thích dữ liệu sau deploy và tác động khi nhiều node.
9. **Kiểm thử bằng giao dịch riêng và cập nhật đồng thời.** Kiểm tra result, version conflict, hit/miss/put, SQL count, rollback và external write; đừng chỉ chạy một lần đọc.

## 11. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Gắn `READ_ONLY` cho hàng hóa có thể sửa | Chiến lược coi dữ liệu cached là bất biến | Đổi sang chiến lược hỗ trợ ghi hoặc bỏ L2 |
| Có `@Cache` nhưng không có provider | Hibernate thiếu backend L2 | Thêm `hibernate-jcache` và JCache provider, xác minh runtime |
| Gọi `findById` hai lần cùng transaction để “chứng minh L2 hit” | Cả hai có thể dùng L1 | Đọc bằng hai persistence context khác nhau, bật statistics |
| Dùng `NONSTRICT_READ_WRITE` khi cần đọc mới ngay | Có cửa sổ stale vì không có soft lock | Dùng mức nhất quán phù hợp, thường cân nhắc `READ_WRITE` hoặc không cache |
| Tưởng soft lock chặn double update ở DB | Soft lock bảo vệ cache entry | Thêm `@Version` / khóa DB phù hợp |
| Tưởng `flush()` là commit | Flush chưa kết thúc transaction | Gắn event/invalidation ngoài tiến trình vào **commit thành công** |
| Dùng JPQL bulk rồi tiếp tục đọc Entity cũ trong cùng persistence context | Bulk không đồng bộ object managed | Flush/clear/refresh theo phạm vi an toàn |
| Bỏ qua writer ngoài Hibernate | L2 không được báo dữ liệu đã đổi | Event after-commit + evict/refresh/TTL, cân nhắc cache phân tán |
| Tưởng Hibernate L2 đồng bộ Spring `@Cacheable` | Hai cache độc lập | Invalidates đúng key Spring Cache riêng |
| Tự tạo region không giới hạn | Có thể tăng bộ nhớ vô hạn hoặc TTL khó kiểm soát | Khai báo cấu hình vùng cache production và giám sát |
| Dùng cache local trên nhiều instance rồi giả định nhất quán cluster | Mỗi JVM có thể giữ bản copy khác nhau | Dùng provider cluster/invalidation được kiểm thử hoặc bỏ L2 |
| Bật query cache đại trà | Update thường xuyên và query biến động dễ làm cache kém hiệu quả | Chỉ bật query ổn định, đo hit rate và giữ timestamp region phù hợp |

## 12. Bài tập kiểm tra hiểu biết

**Tình huống A.** Entity `ExchangeRate` cập nhật mỗi vài phút, API đọc rất nhiều, đôi khi chấp nhận rate lệch một khoảng ngắn. Bạn chọn `NONSTRICT_READ_WRITE` hay `READ_WRITE`? Cần thêm điều kiện gì?

**Gợi ý:** Nếu cho phép stale theo hợp đồng nghiệp vụ và xác nhận tần suất cập nhật/xung đột rất thấp, `NONSTRICT_READ_WRITE` có thể được cân nhắc; nếu yêu cầu hạn chế stale giữa các transaction, ưu tiên đánh giá `READ_WRITE`. Cả hai vẫn cần provider, TTL/region policy và kiểm thử. Với giao dịch tài chính áp dụng tỷ giá chính xác, có thể phải dùng snapshot/version được xác định và không phụ thuộc entry cache “mới nhất”.

**Tình huống B.** `Product` có `@Cache(READ_WRITE)` và `@Version`, một cron job dùng JDBC riêng cập nhật giá. API vẫn trả giá cũ dù mỗi request mở transaction mới. Vì sao?

**Đáp án:** Job không thông báo L2 đang nằm trong Hibernate; `READ_WRITE` không quan sát được mọi external writer. Cần invalidation sau commit hoặc cơ chế đồng bộ khác; nếu đang dùng Spring Cache/Redis độc lập phải xóa đúng cache đó nữa.

**Tình huống C.** Sau `@Modifying @Query("update ...")`, bạn đọc lại entity trong cùng EntityManager nhưng thấy giá trị cũ. Gốc vấn đề nằm ở đâu?

**Đáp án:** L1/persistence context chứa object managed cũ; bulk JPQL không tự cập nhật các Java object này. Cần `refresh`/`clear` thích hợp, bên cạnh đánh giá L2/query cache và version.

**Tình huống D.** Cấu hình `READ_WRITE` + cache provider local có đảm bảo đúng khi ba instance ứng dụng ghi cùng bảng không?

**Đáp án:** Không thể mặc định vậy. Soft locks/cache regions trong các JVM local không đồng bộ tự động; cần provider/kiến trúc cluster phù hợp, hoặc đọc DB trong các luồng yêu cầu nhất quán mạnh. `@Version` vẫn giúp bảo vệ khỏi lost update ở DB.

## 13. Ghi nhớ cốt lõi

- **L1** thuộc EntityManager; **L2** thuộc SessionFactory/provider; **Query cache** và **Spring Cache** là các cơ chế khác.
- **Entity có thay đổi:** `READ_WRITE` là lựa chọn Hibernate thường cần đánh giá; `NONSTRICT_READ_WRITE` chỉ khi chấp nhận stale; `READ_ONLY` dành cho dữ liệu bất biến; `TRANSACTIONAL` đòi hỏi hạ tầng hỗ trợ thực sự.
- Cache soft lock **không thay** transaction isolation hoặc `@Version`.
- Cập nhật qua Hibernate, bulk JPQL, native SQL và external writer có đường invalidation khác nhau.
- Thử L2 bằng **hai persistence context**, đồng thời đo hit/miss/put và kiểm tra dữ liệu **sau commit**.

### Tài liệu chính thức

- Hibernate ORM 6.6 – second-level cache, concurrency strategies, provider và query cache: https://docs.hibernate.org/orm/6.6/introduction/html_single/#caching
- Hibernate ORM 6.6 – User Guide, phần Caching: https://docs.hibernate.org/orm/6.6/userguide/html_single/
- Hibernate ORM – `CacheConcurrencyStrategy` JavaDoc: https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/CacheConcurrencyStrategy.html
- Hibernate JCache – `ConfigSettings` JavaDoc: https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/cache/jcache/ConfigSettings.html
- Spring Boot – Caching reference: https://docs.spring.io/spring-boot/3.5/reference/io/caching.html
