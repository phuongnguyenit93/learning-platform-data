# Kiểm thử cập nhật, xóa và rollback theo ranh giới giao dịch

Trong **Spring Framework Cache**, một câu lệnh **@Transactional** có thể thành công hoặc rollback nhưng cache thường nằm **ngoài transaction của database**. Do đó, nếu code chạy **@CachePut** hoặc **@CacheEvict** trước khi database commit, transaction thất bại có thể khiến bản sao trong cache **không còn tương ứng với dữ liệu đã commit**.

Bài này tập trung vào kiểm thử đúng **ranh giới giao dịch**: cập nhật DB và cache khi **commit**, giữ nguyên giá trị khi **rollback**, xác nhận eviction chỉ xuất hiện sau commit và phân biệt thao tác cache ngay lập tức với thao tác được hoãn tới **after-commit**. Ví dụ dùng **Java 17, Spring Framework 6.1.14, Spring JDBC/TX, H2 và JUnit 5**, không cần Spring Boot hoặc server ngoài.

**Kết luận cần nhớ ngay:** **@Transactional không tự biến cache thành một thành phần có rollback**. Muốn cache put/evict được đồng bộ với transaction Spring, cần dùng provider có semantics tương ứng hoặc một wrapper như **TransactionAwareCacheManagerProxy**, đặt cache operation trong transaction thật và kiểm thử hoạt động trên provider thực tế.

## 1. DB và cache là hai trạng thái độc lập

Giả sử lúc đầu cả DB và cache đều có giá trị **product 1 = alpha-v1**. Application muốn đổi thành **alpha-v2**.

~~~text
    API / Command
          |
   @Transactional
          |
   UPDATE product --> DB có giá trị chưa commit
          |
   @CachePut hoặc @CacheEvict
          |
    commit / rollback
          |
   Trả kết quả cho caller
~~~

Một database rollback chỉ phục hồi dữ liệu theo transaction của database. Với ConcurrentMapCache hoặc Redis thao tác bình thường, **put/evict đã xảy ra** không tự được database transaction manager hoàn nguyên.

| Hành động | Sau khi rollback DB | Nếu cache đổi ngay | Nếu mutation được defer after-commit |
| --- | --- | --- | --- |
| UPDATE alpha-v1 → alpha-v2; put alpha-v2 | alpha-v1 | Có thể giữ **alpha-v2 sai** | Giữ **alpha-v1 đúng** |
| UPDATE alpha-v1 → alpha-v2; evict key | alpha-v1 | Entry đã mất, tạo cache miss thừa | Entry alpha-v1 vẫn còn |
| UPDATE alpha-v1 → alpha-v2; commit + put | alpha-v2 | Cache đã mới, nhưng có thể mới quá sớm | Cache cập nhật sau commit |
| UPDATE alpha-v1 → alpha-v2; commit + evict | alpha-v2 | Key có thể đã bị xóa trước commit | Key bị xóa sau commit; lần đọc sau nạp mới |

Cả hai chiến lược **put** và **evict** đều có chỗ dùng: put cập nhật cache bằng value mới, còn evict loại value cũ rồi để lần đọc tiếp theo nạp lại. **Evict không phải refresh**; lúc nó được thực hiện chưa nhất thiết có một lần đọc DB.

## 2. TransactionAwareCacheManagerProxy làm gì?

Spring cung cấp **org.springframework.cache.transaction.TransactionAwareCacheManagerProxy**, bọc một CacheManager bình thường và trả về các Cache đã được trang bị **TransactionAwareCacheDecorator**.

~~~java
@Bean
public CacheManager cacheManager() {
    CacheManager base = new ConcurrentMapCacheManager("products");
    return new TransactionAwareCacheManagerProxy(base);
}
~~~

Đây là snippet cấu hình Spring; phần project đầy đủ bên dưới có toàn bộ imports và dependencies.

Khi một **Spring-managed transaction thực sự đang hoạt động** và cache thao tác qua decorator, các lệnh **Cache.put**, **Cache.evict** và **Cache.clear** phù hợp có thể được xếp vào transaction synchronization, chỉ thực thi trong pha **afterCommit** của một commit thành công. Khi transaction rollback, các cache mutation đã hoãn không được áp dụng. Nếu không có transaction active, các lệnh này thường thực thi ngay.

~~~text
Có transaction Spring đang hoạt động:
   @CachePut / @CacheEvict
             |
             v
   Cache được decorator bọc
             |
       đăng ký afterCommit
          /        \
       COMMIT    ROLLBACK
         |          |
    thực thi      bỏ qua
    put/evict     mutation
~~~

**Không suy rộng:** Cache.get vẫn có thể trả dữ liệu đang có trong cache khi transaction chưa commit. Các API tức thời như **putIfAbsent** hoặc **evictIfPresent** không có cùng khả năng hoãn đơn giản; lối đi **get(key, Callable)** hoặc **sync=true** cũng cần kiểm tra theo provider/phiên bản. Transaction-aware cache không phải một transaction phân tán, không khóa mọi entry và không bảo đảm cache đã được cập nhật nguyên tử cùng database.

### Vị trí của cache operation trong transaction rất quan trọng

Trong ví dụ bên dưới:

- **ProductWriter** là một bean có **@Transactional**, bắt đầu transaction và cập nhật DB.
- **ProductCachePort** là bean riêng có **@CachePut / @CacheEvict** và được ProductWriter gọi **qua Spring proxy** trong transaction đã mở.
- **CacheManager** được bọc bởi TransactionAwareCacheManagerProxy.

Cấu trúc này loại bỏ sự mơ hồ về thứ tự các advice nếu đặt transaction và caching annotation cùng một method rồi chỉ nhìn thứ tự annotation trên source. Đối với code production, có nhiều cách tổ chức khác nhưng đều cần kiểm chứng rằng cache operation được yêu cầu **khi transaction thật sự còn active**.

## 3. Bốn ca kiểm thử bắt buộc

Các bài test không nên bắt đầu từ cache rỗng; cần **warm entry cũ** trước để quan sát việc giữ lại hay xóa entry.

| Ca | Lời gọi trong transaction | Kết thúc | DB sau lời gọi | Cache sau lời gọi | Lần đọc sau |
| --- | --- | --- | --- | --- | --- |
| **Put commit** | UPDATE rồi @CachePut(value mới) | COMMIT | Mới | Mới | **Hit**, không tăng loader |
| **Put rollback** | UPDATE rồi @CachePut(value mới) | ROLLBACK | Cũ | Cũ | **Hit**, không tăng loader |
| **Evict commit** | UPDATE rồi @CacheEvict(key) | COMMIT | Mới | **Không có key** | **Miss**, nạp value mới |
| **Evict rollback** | UPDATE rồi @CacheEvict(key) | ROLLBACK | Cũ | Cũ | **Hit**, không tăng loader |

Ba điều nên xác minh trong mỗi test:

1. **DB state** sau commit/rollback; nếu chỉ nhìn cache thì không chứng minh được DB rollback.
2. **Cache state** bằng CacheManager.getCache(name).get(key), để biết put/evict đã chạy hay chưa.
3. **Loader count** của method @Cacheable, để phân biệt cache hit với đọc lại DB không cần thiết.

Thêm một phép thử về **thời điểm**: trong TransactionTemplate, sau khi update và gọi cache put, đọc DB bằng chính transaction sẽ thấy value mới của mình, nhưng cache được hoãn vẫn trả value cũ. **Sau khi TransactionTemplate kết thúc và commit**, cache mới nhận value mới. Với rollback-only, cache mutation không được thực hiện.

## 4. Project Java 17 + Spring JDBC + H2

Cấu trúc:

~~~text
spring-cache-transaction-tests/
├── settings.gradle
├── build.gradle
├── src/main/java/demo/cache/TxCacheDemo.java
└── src/test/java/demo/cache/TxCacheDemoTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-cache-transaction-tests'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-context-support:6.1.14'
    implementation 'org.springframework:spring-jdbc:6.1.14'
    implementation 'com.h2database:h2:2.2.224'

    testImplementation 'org.springframework:spring-test:6.1.14'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.cache.TxCacheDemo'
}

test {
    useJUnitPlatform()
}
~~~

**spring-jdbc** kéo theo hỗ trợ transaction cần dùng. **spring-context-support** cung cấp các cache adapter/decorator liên quan. **H2** là database in-memory dùng cho kiểm thử có commit và rollback thật. Để tránh database biến mất khi connection tạm đóng, URL H2 trong ví dụ dùng **DB_CLOSE_DELAY=-1**.

## 5. Chương trình hoàn chỉnh: DB, cache và transaction

**src/main/java/demo/cache/TxCacheDemo.java**

~~~java
package demo.cache;

import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.transaction.TransactionAwareCacheManagerProxy;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public final class TxCacheDemo {

    @Configuration
    @EnableCaching
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:cache_tx_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public CacheManager cacheManager() {
            CacheManager base = new ConcurrentMapCacheManager("products");
            return new TransactionAwareCacheManagerProxy(base);
        }

        @Bean
        public ProductCachePort productCachePort(JdbcTemplate jdbc) {
            return new ProductCachePort(jdbc);
        }

        @Bean
        public ProductWriter productWriter(
                JdbcTemplate jdbc, ProductCachePort cachePort) {
            return new ProductWriter(jdbc, cachePort);
        }
    }

    public static final class PlannedRollback extends RuntimeException {
        public PlannedRollback() {
            super("Rollback requested for test");
        }
    }

    // Bean chứa cache annotations, được gọi qua Spring proxy.
    public static class ProductCachePort {
        private final JdbcTemplate jdbc;
        private final AtomicInteger dbLoads = new AtomicInteger();

        public ProductCachePort(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Cacheable(cacheNames = "products", key = "#p0")
        public String find(int id) {
            dbLoads.incrementAndGet();
            return dbValue(jdbc, id);
        }

        @CachePut(cacheNames = "products", key = "#p0")
        public String put(int id, String newLabel) {
            return newLabel;
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void evict(int id) {
        }

        public int loads() {
            return dbLoads.get();
        }

        public void resetLoads() {
            dbLoads.set(0);
        }
    }

    // Bean ngoài tạo ranh giới @Transactional trước khi vào CachePort.
    public static class ProductWriter {
        private final JdbcTemplate jdbc;
        private final ProductCachePort cachePort;

        public ProductWriter(
                JdbcTemplate jdbc, ProductCachePort cachePort) {
            this.jdbc = jdbc;
            this.cachePort = cachePort;
        }

        @Transactional
        public void updateThenPut(
                int id, String newLabel, boolean fail) {
            updateRow(id, newLabel);
            cachePort.put(id, newLabel);

            if (fail) {
                throw new PlannedRollback();
            }
        }

        @Transactional
        public void updateThenEvict(
                int id, String newLabel, boolean fail) {
            updateRow(id, newLabel);
            cachePort.evict(id);

            if (fail) {
                throw new PlannedRollback();
            }
        }

        private void updateRow(int id, String newLabel) {
            int affected = jdbc.update(
                "UPDATE product SET label = ? WHERE id = ?",
                newLabel, id);

            if (affected != 1) {
                throw new IllegalArgumentException(
                    "Missing product id " + id);
            }
        }
    }

    public static String dbValue(JdbcTemplate jdbc, int id) {
        return jdbc.queryForObject(
            "SELECT label FROM product WHERE id = ?",
            String.class, id);
    }

    public static void seed(JdbcTemplate jdbc) {
        jdbc.execute("DROP TABLE IF EXISTS product");
        jdbc.execute("CREATE TABLE product "
            + "(id INT PRIMARY KEY, label VARCHAR(80) NOT NULL)");

        jdbc.update(
            "INSERT INTO product(id, label) VALUES (?, ?)",
            1, "alpha-v1");
        jdbc.update(
            "INSERT INTO product(id, label) VALUES (?, ?)",
            2, "beta-v1");
        jdbc.update(
            "INSERT INTO product(id, label) VALUES (?, ?)",
            3, "gamma-v1");
        jdbc.update(
            "INSERT INTO product(id, label) VALUES (?, ?)",
            4, "delta-v1");
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            ProductCachePort cache = ctx.getBean(ProductCachePort.class);
            ProductWriter writer = ctx.getBean(ProductWriter.class);

            seed(jdbc);

            System.out.println("warm=" + cache.find(1) + ","
                + cache.find(2) + ","
                + cache.find(3) + ","
                + cache.find(4));
            System.out.println("warmLoads=" + cache.loads());

            writer.updateThenPut(1, "alpha-v2", false);
            System.out.println("putCommit=" + cache.find(1) + "/"
                + dbValue(jdbc, 1) + "/loads=" + cache.loads());

            try {
                writer.updateThenPut(2, "beta-v2", true);
            } catch (PlannedRollback expected) {
                // DB đã rollback; deferred put không được áp dụng.
            }
            System.out.println("putRollback=" + cache.find(2) + "/"
                + dbValue(jdbc, 2) + "/loads=" + cache.loads());

            writer.updateThenEvict(3, "gamma-v2", false);
            System.out.println("evictCommit=" + cache.find(3) + "/"
                + dbValue(jdbc, 3) + "/loads=" + cache.loads());

            try {
                writer.updateThenEvict(4, "delta-v2", true);
            } catch (PlannedRollback expected) {
                // DB đã rollback; deferred evict bị bỏ qua.
            }
            System.out.println("evictRollback=" + cache.find(4)
                + "/" + dbValue(jdbc, 4)
                + "/loads=" + cache.loads());
        }
    }
}
~~~

### Ranh giới AOP trong code

**ProductWriter** được lấy từ **ApplicationContext** và gọi qua proxy. **@Transactional** được Spring áp dụng cho public methods. Trong method, **cachePort.put/evict** được gọi trên **bean khác** cũng được Spring quản lý. Điều này có nghĩa transaction đã active trước khi cache interceptor nhận lệnh.

Nếu dùng **new ProductWriter(...)** trực tiếp, hoặc gọi **this.updateThenPut(...)** trong chính ProductWriter, Spring transaction advice có thể bị bỏ qua. Nếu code gọi **this.put(...)** trong ProductCachePort, cache advice cũng có thể bị bỏ qua. Những lỗi self-invocation này khiến test tưởng đang kiểm tra transaction nhưng thực chất chưa có Spring-managed transaction.

Không dùng method **private** với @Transactional trong proxy mode và mong nó được intercept. Không suy đoán thứ tự advice từ việc viết @Transactional ở trên hay dưới @CachePut trên cùng một method.

### Chạy chương trình

Chạy từ thư mục project bằng Gradle thích hợp Java 17 hoặc wrapper đã có:

~~~bash
gradle run --quiet
~~~

Những dòng **System.out.println** dự kiến (không bao gồm log thư viện nếu có):

~~~text
warm=alpha-v1,beta-v1,gamma-v1,delta-v1
warmLoads=4
putCommit=alpha-v2/alpha-v2/loads=4
putRollback=beta-v1/beta-v1/loads=4
evictCommit=gamma-v2/gamma-v2/loads=5
evictRollback=delta-v1/delta-v1/loads=5
~~~

Lý do từng dòng:

- Ban đầu cache rỗng. Đọc bốn key khiến **find** chạy bốn lần, **loads=4**.
- **Put commit:** update DB thành alpha-v2, put được hoãn và áp dụng sau commit; lần **find(1)** tiếp theo hit alpha-v2, nên loads vẫn 4.
- **Put rollback:** sau DB UPDATE và put pending, method ném **PlannedRollback** (RuntimeException), Spring rollback DB và bỏ deferred put; **find(2)** vẫn hit beta-v1.
- **Evict commit:** update gamma-v2 commit rồi evict key 3; lần **find(3)** tiếp theo miss và tải gamma-v2, loads tăng lên 5.
- **Evict rollback:** transaction đưa DB về delta-v1, pending eviction không chạy, **find(4)** hit delta-v1 nên loads vẫn 5.

Trong ví dụ này không có request đồng thời, TTL hoặc cache backend lỗi, vì thế các dòng kết quả tính được theo trình tự. Đây là kết quả mong đợi từ code; chưa phải bằng chứng rằng nó đã được chạy trên máy của bạn.

## 6. Kiểm thử JUnit 5: đủ bốn trường hợp

Cấu hình test dùng Spring TestContext thực, **không đặt @Transactional lên test class**. Mỗi test reset bảng H2 và cache trước khi bắt đầu, không giữ state của test trước.

**src/test/java/demo/cache/TxCacheDemoTest.java**

~~~java
package demo.cache;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(TxCacheDemo.Config.class)
class TxCacheDemoTest {

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    TxCacheDemo.ProductCachePort cache;

    @Autowired
    TxCacheDemo.ProductWriter writer;

    @Autowired
    CacheManager cacheManager;

    @Autowired
    PlatformTransactionManager txManager;

    @BeforeEach
    void resetState() {
        TxCacheDemo.seed(jdbc);
        cacheManager.getCache("products").clear();
        cache.resetLoads();
    }

    private String db(int id) {
        return TxCacheDemo.dbValue(jdbc, id);
    }

    private Cache products() {
        Cache result = cacheManager.getCache("products");
        assertNotNull(result);
        return result;
    }

    @Test
    void putCommit() {
        assertEquals("alpha-v1", cache.find(1));
        assertEquals(1, cache.loads());

        writer.updateThenPut(1, "alpha-v2", false);

        assertEquals("alpha-v2", db(1));
        assertEquals("alpha-v2", products().get(1).get());
        assertEquals("alpha-v2", cache.find(1));
        assertEquals(1, cache.loads());
    }

    @Test
    void putRollback() {
        assertEquals("beta-v1", cache.find(2));
        assertEquals(1, cache.loads());

        assertThrows(TxCacheDemo.PlannedRollback.class,
            () -> writer.updateThenPut(2, "beta-v2", true));

        assertEquals("beta-v1", db(2));
        assertEquals("beta-v1", products().get(2).get());
        assertEquals("beta-v1", cache.find(2));
        assertEquals(1, cache.loads());
    }

    @Test
    void evictCommit() {
        assertEquals("gamma-v1", cache.find(3));
        assertEquals(1, cache.loads());

        writer.updateThenEvict(3, "gamma-v2", false);

        assertEquals("gamma-v2", db(3));
        assertNull(products().get(3));
        assertEquals("gamma-v2", cache.find(3));
        assertEquals(2, cache.loads());
    }

    @Test
    void evictRollback() {
        assertEquals("delta-v1", cache.find(4));
        assertEquals(1, cache.loads());

        assertThrows(TxCacheDemo.PlannedRollback.class,
            () -> writer.updateThenEvict(4, "delta-v2", true));

        assertEquals("delta-v1", db(4));
        assertEquals("delta-v1", products().get(4).get());
        assertEquals("delta-v1", cache.find(4));
        assertEquals(1, cache.loads());
    }

    @Test
    void putNotVisibleUntilAfterCommit() {
        assertEquals("alpha-v1", cache.find(1));
        TransactionTemplate tx = new TransactionTemplate(txManager);

        tx.executeWithoutResult(status -> {
            jdbc.update(
                "UPDATE product SET label = ? WHERE id = ?",
                "alpha-v2", 1);
            cache.put(1, "alpha-v2");

            // Trong transaction, JDBC thấy thay đổi của chính mình.
            assertEquals("alpha-v2", db(1));
            // Deferred cache put CHƯA chạy.
            assertEquals("alpha-v1", products().get(1).get());
        });

        // TransactionTemplate đã commit và chạy afterCommit.
        assertEquals("alpha-v2", db(1));
        assertEquals("alpha-v2", products().get(1).get());
        assertEquals(1, cache.loads());
    }

    @Test
    void rollbackOnlyCancelsEviction() {
        assertEquals("gamma-v1", cache.find(3));
        TransactionTemplate tx = new TransactionTemplate(txManager);

        tx.executeWithoutResult(status -> {
            jdbc.update(
                "UPDATE product SET label = ? WHERE id = ?",
                "gamma-v2", 3);
            cache.evict(3);

            // Chưa commit; entry cũ còn nguyên.
            assertEquals("gamma-v1", products().get(3).get());
            status.setRollbackOnly();
        });

        assertEquals("gamma-v1", db(3));
        assertEquals("gamma-v1", products().get(3).get());
        assertEquals(1, cache.loads());
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Kỳ vọng **sáu test thành công** với phụ thuộc đúng phiên bản và môi trường chạy phù hợp.

**Điểm khác biệt giữa hai loại rollback test:** các test putRollback/evictRollback ném **unchecked exception**, nên Spring dùng quy tắc rollback mặc định. Test rollbackOnlyCancelsEviction không ném lỗi; nó đánh dấu rollback-only một cách chủ động. Cả hai đều phải ngăn callback afterCommit.

**Hai trường hợp boundary:** putNotVisibleUntilAfterCommit chứng minh DB trong transaction có thể thấy value vừa UPDATE, còn cache vẫn giữ bản cũ, rồi sau khi TransactionTemplate trả về thành công cache đổi sang bản mới. rollbackOnlyCancelsEviction xác minh entry được giữ qua rollback-only, không chỉ qua exception.

**Quan trọng khi viết test:** Spring Test có thể tự bao bọc các method test có @Transactional trong test-managed transaction và rollback lúc kết thúc. Nếu vô tình annotate cả test class, lời gọi ProductWriter có thể chỉ tham gia transaction ngoài và **không commit tại thời điểm assert**. Vì vậy các ca muốn chứng minh commit ở trên chủ động để test method **không có @Transactional**, và dùng TransactionTemplate cho ranh giới cần kiểm soát.

## 7. Một đối chứng có ích: bỏ transaction awareness

Nếu thay CacheManager bằng cache local thô:

~~~java
@Bean
public CacheManager cacheManager() {
    return new ConcurrentMapCacheManager("products");
}
~~~

Đây là mã **đối chứng**, không nên thay trong cùng Context rồi coi như đã cấu hình lại Bean. Hãy tạo một cấu hình test riêng. Với cache thô, khi transaction vẫn chưa commit, **@CachePut** có thể ghi ngay và **@CacheEvict** có thể xóa ngay.

Sau **put + rollback**, DB trở về beta-v1 nhưng cache có thể vẫn giữ beta-v2 sai. Sau **evict + rollback**, cache entry delta-v1 mất dù database vẫn là delta-v1; lần đọc sau tạo miss và tốn một lượt DB query.

Khi chuyển sang transaction-aware wrapper, hai rủi ro cụ thể này được giảm bằng cách **chỉ thực hiện mutation sau commit**. Tuy vậy, không nên khẳng định wrapper này bảo vệ tất cả provider, API đặc thù và đường cập nhật native khác. Nếu gọi trực tiếp underlying native cache ngoài decorator, transaction awareness có thể bị bypass.

## 8. Điều transaction-aware cache KHÔNG bảo đảm

### 8.1. After-commit không phải atomicity xuyên DB và cache

~~~text
T1: Database COMMIT đã hoàn tất
T2: Spring gọi afterCommit callback cập nhật/xóa cache
T3: Cache operation hoàn thành hoặc lỗi
~~~

Giữa T1 và T2 có một khoảng thời gian mà DB đã mới nhưng cache chưa được cập nhật. Nếu process chết hoặc cache backend lỗi ngay sau DB commit, DB **không rollback trở lại** chỉ vì cache mutation thất bại. Wrapper đồng bộ thời điểm trong cùng process, không cung cấp giao dịch phân tán/XA.

Đối với dữ liệu quan trọng, cần cơ chế khôi phục như **transactional outbox**, retry idempotent, event-driven invalidation, versioned key/value, TTL phòng vệ và reconciliation. Ghi metrics để phát hiện callback/cache lỗi và xây dựng chiến lược chấp nhận stale rõ ràng.

### 8.2. Race với request khác

~~~text
T0: Cache sản phẩm có value v1
T1: Transaction A update DB sang v2
T2: Transaction A commit DB
T3: Request B tới, thấy cache v1 trước callback eviction
T4: Callback afterCommit evict key
T5: Request C miss và nạp v2
~~~

Một request có thể thấy v1 giữa commit DB và evict. Nguy hiểm hơn, một loader bắt đầu trước commit có thể trả dữ liệu cũ và put lại sau eviction; nếu nghiệp vụ không chấp nhận, phải thiết kế versioning/ordering hoặc điều phối riêng. **@Cacheable(sync = true)** có thể giảm tính lặp theo key khi provider hỗ trợ, nhưng không tự sửa mọi race giữa read, write và invalidation.

### 8.3. Local cache ở nhiều replica

**ConcurrentMapCacheManager** là cache nội bộ một JVM. Nếu ba instance A/B/C đều đã warm P01, transaction-aware eviction ở A **không xóa** entry ở B và C. Dùng shared/distributed cache hoặc cơ chế invalidation phát tán khi SLA đòi hỏi. Đừng hiểu Spring transaction awareness như một distributed lock hay một transaction giữa các node.

### 8.4. Transaction propagation và rollback rules

- **PROPAGATION_REQUIRED:** join transaction hiện tại; callback sau commit thuộc ranh giới transaction ngoài thực sự.
- **REQUIRES_NEW:** transaction con độc lập có thể commit cache mutation ngay cả khi transaction cha sau đó rollback.
- **NESTED/savepoint:** đừng tự khẳng định cache callback luôn xử lý rollback tới savepoint đúng kỳ vọng; test cụ thể version/provider và cấu trúc transaction.
- **Không có transaction active:** mutation thường được áp dụng ngay.
- **RuntimeException/Error:** mặc định khiến Spring rollback đối với @Transactional.
- **Checked exception:** mặc định Spring không nhất thiết rollback; dùng **rollbackFor** hoặc quy tắc phù hợp.
- **Exception bị bắt và nuốt:** phương thức có thể commit nếu không đánh dấu rollback-only.

Một lỗi hay gặp là test chỉ xác minh rằng exception đã được ném; **phải đọc lại DB** để chứng minh transaction thực sự rollback.

### 8.5. @CacheEvict(beforeInvocation = true)

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    beforeInvocation = true
)
public void invalidateBeforeCall(int id) {
    // ...
}
~~~

Tùy chọn **beforeInvocation** thay đổi thời điểm cache interceptor yêu cầu eviction so với thân method, không biến evict thành thao tác database-atomic. Với manager không transaction-aware, xóa sớm có thể xảy ra dù method sau đó thất bại. Với transaction-aware decorator và transaction đang active tại lúc yêu cầu evict, thao tác thông thường vẫn có thể bị hoãn đến commit. Cần test cả thứ tự advice, đặc biệt khi kết hợp nhiều annotation cùng một method.

## 9. Ma trận mở rộng cho integration test thực tế

| Kịch bản | Setup cần có | Assertion quan trọng |
| --- | --- | --- |
| Put commit | Cache đã có old value | DB/cache cùng new; loader count không tăng |
| Put rollback | UPDATE rồi exception | DB/cache cùng old, không cache giá trị chưa commit |
| Evict commit | Warm entry, UPDATE rồi evict | Entry absent sau commit; read tiếp nạp new |
| Evict rollback | Warm entry, UPDATE rồi exception | DB/cache old; không miss thừa |
| Before/after commit | TransactionTemplate | Trong tx cache old, sau commit cache new |
| Rollback-only | TransactionTemplate, setRollbackOnly | Không thực hiện pending eviction |
| Checked exception | Ném exception được khai báo | DB có rollback đúng theo rollbackFor không? |
| Advisor ordering | Cache và tx annotation cùng method | Transaction active ở lúc cache mutation không? |
| Self-invocation | Gọi this.update... so với bean proxy | Test nhận ra khi advice bị bypass |
| Concurrent load/update | CountDownLatch điều phối | Không stale overwrite ngoài chính sách |
| After-commit cache failure | Mock backend cache lỗi | DB đã commit; ghi nhận recovery |
| Nhiều process | Warm local cache nhiều replica | Kiểm tra invalidation propagation |
| Key khác nhau | @CachePut key sai so với @Cacheable | Test tìm được hit/miss lệch hoặc stale |
| Provider thực | Caffeine, Redis, JCache provider | Semantics lỗi, network và timing đúng |

Không cần đưa toàn bộ ma trận vào một unit test. Test tại nhiều tầng: unit test mô phỏng logic với mock, integration test H2 như demo, integration test cache provider production và stress test concurrency để kiểm chứng consistency thực.

**Tránh Thread.sleep tùy ý** khi muốn ép thứ tự hai luồng. Dùng latch/barrier và controlled transaction boundaries để tái hiện race một cách đáng tin cậy.

## 10. Các lỗi phổ biến

1. **Tin rằng @Transactional rollback mọi cache mutation**: cache thường không tham gia JDBC transaction.
2. **Gọi @CachePut khi DB vẫn chưa commit mà dùng cache không transaction-aware**: có thể lộ value chưa commit.
3. **Xóa cache ngay rồi rollback DB**: tạo miss thừa và có thể dẫn đến race.
4. **Chỉ assert giá trị @Cacheable trả về**: không phân biệt hit, miss hay stale; nên đọc cache và loader count.
5. **Chỉ assert cache mà bỏ qua DB sau rollback**: không chứng minh rollback thành công.
6. **Đặt @Transactional lên toàn bộ test class**: test-managed transaction có thể rollback cuối test, khiến kiểm tra commit sai ngữ cảnh.
7. **Gọi this.updateThenPut(...)**: Spring proxy không intercept self-invocation ở proxy mode.
8. **Gọi native cache trực tiếp**: có thể bypass transaction-aware decorator.
9. **Hiểu afterCommit như distributed atomic transaction**: callback có thể thất bại sau khi DB đã commit.
10. **Quên REQUIRES_NEW và checked exception**: transaction thực tế có thể commit/rollback khác dự đoán.
11. **Cho rằng @Cacheable(sync=true) xử lý giống deferred put**: API get-or-load có đường thực thi khác, cần kiểm tra.
12. **Không reset cache giữa test**: test phụ thuộc nhau có thể vẫn pass sai.
13. **Bỏ qua concurrency và multi-replica**: local success không chứng minh cluster correctness.

## 11. Câu hỏi tự kiểm tra

1. Vì sao put cache trước DB commit có thể làm cache trả value chưa từng được commit?
2. TransactionAwareCacheManagerProxy bọc CacheManager và hoãn những thao tác phổ biến nào?
3. Vì sao phải warm cache trước khi kiểm thử rollback eviction?
4. Sau **put + commit**, tại sao loader count không cần tăng?
5. Sau **evict + commit**, vì sao lần đọc đầu tiên thường là cache miss?
6. Vì sao cache có thể vẫn giữ old value bên trong transaction sau lời gọi @CachePut?
7. Khi test method có @Transactional, tại sao assert ngay sau gọi service chưa chắc chứng minh commit?
8. REQUIRES_NEW ảnh hưởng thế nào nếu transaction ngoài rollback?
9. Tại sao after-commit cache error không thể đơn giản rollback DB đã commit?
10. Nếu một instance evict cache local nhưng instance khác không evict, cần thêm cơ chế gì?

**Tổng kết:** Để kiểm thử cập nhật, xóa và rollback theo ranh giới giao dịch, phải đo **DB state + cache state + loader count** ở cả **trước và sau commit/rollback**. Với Spring, **TransactionAwareCacheManagerProxy** giúp defer các cache put/evict được hỗ trợ cho đến sau commit, tránh cập nhật cache do transaction thất bại. Nhưng đây là một cơ chế điều phối thời điểm, **không thay thế transaction xuyên hệ thống, versioning hay kiểm thử concurrency**.

### Tài liệu chính thức

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — TransactionAwareCacheManagerProxy Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html
- Spring Framework — TransactionAwareCacheDecorator Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html
- Spring Framework — Programmatic Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — Rollback rules: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Declarative Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — TestContext transaction management: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
