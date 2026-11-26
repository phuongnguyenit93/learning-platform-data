# Chạy bộ kiểm thử Testcontainers và đo tải theo mẫu truy cập

## 1. Mục tiêu bài thực hành

**Spring Data Cassandra** cung cấp entity mapping, repository, `CassandraTemplate` và truy vấn CQL giúp ứng dụng truy cập Apache Cassandra. Tuy nhiên, một kiểm thử `repository.save()` thành công chưa chứng minh rằng thiết kế bảng phù hợp với truy vấn hoặc hệ thống đáp ứng tốt dưới tải. Cassandra được thiết kế theo **mẫu truy cập (access pattern)**, partition key, clustering key, consistency, paging và hành vi của một cụm phân tán.

Bài thực hành này yêu cầu hoàn thành hai nhóm công việc:

1. **Kiểm thử tích hợp:** dùng **Testcontainers** khởi động Cassandra thật, tạo schema, kiểm tra mapping Spring Data, truy vấn bằng khóa và phân trang đúng thứ tự.
2. **Đo tải có kiểm soát:** chuẩn bị dữ liệu đại diện, chạy các profile truy vấn khác nhau, đo throughput, tỷ lệ lỗi và độ trễ P50/P95/P99 rồi giải thích sự khác biệt.

**Kết quả cần bàn giao:** mã kiểm thử chức năng, mã tạo dữ liệu và đo tải, báo cáo có điều kiện thí nghiệm, bảng số liệu thật và nhận xét dựa trên mẫu truy cập. Các ví dụ dùng Java 17+, Spring Boot 3.x, Spring Data Cassandra, Java Driver 4.x và API phổ biến của Testcontainers 1.x. Nếu dự án dùng Testcontainers 2.x, cần điều chỉnh tọa độ dependency/import theo phiên bản đang dùng.

> Testcontainers với **một node Cassandra** là môi trường tốt để kiểm thử tính đúng, cách truy vấn và phương pháp đo. Kết quả về throughput hoặc consistency tại đây **không được coi là năng lực production của cụm nhiều replica**.

## 2. Bài toán: hai bảng phục vụ ba mẫu truy cập

Giả sử dịch vụ quản lý đơn hàng cần hỗ trợ:

| Mã | Mẫu truy cập | Cách lấy dữ liệu | Yêu cầu kỹ thuật |
|---|---|---|---|
| **AP1** | Tra cứu một đơn hàng theo ID | `WHERE order_id = ?` | Tìm đúng một partition theo ID. |
| **AP2** | Liệt kê đơn mới nhất của khách trong một ngày | `WHERE customer_id = ? AND order_day = ?` | Phân vùng theo khách/ngày, sắp theo thời gian giảm dần. |
| **AP3** | Nhiều request tập trung vào một khách/ngày | Cùng CQL với AP2 | Đo tình huống partition nóng, không chỉ đo dữ liệu phân bố đều. |

Tạo schema CQL:

```sql
CREATE KEYSPACE IF NOT EXISTS practice_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

-- AP1: tra cứu bằng order_id.
CREATE TABLE IF NOT EXISTS practice_lab.order_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    status text,
    created_at timestamp,
    amount_cents bigint
);

-- AP2/AP3: lấy đơn mới nhất trong một bucket ngày.
CREATE TABLE IF NOT EXISTS practice_lab.order_by_customer_day (
    customer_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    status text,
    amount_cents bigint,
    PRIMARY KEY ((customer_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
```

Ở bảng `order_by_customer_day`, `(customer_id, order_day)` là **partition key kép**, còn `(created_at, order_id)` là clustering key. Thứ tự giảm dần theo `created_at` cho phép đọc đơn gần nhất trước. `order_id` phân biệt các đơn có cùng thời điểm.

**Đánh đổi thiết kế:** Một khách hàng có hàng trăm nghìn đơn trong một ngày vẫn có thể tạo partition rộng hoặc nóng. Việc chia bucket theo giờ hoặc thêm shard có thể giảm kích thước partition, nhưng ứng dụng sẽ phải đọc nhiều bucket/shard hơn để ghép lịch sử. Bài đo tải sẽ cung cấp dữ liệu để quyết định.

Ghi một đơn mới thường cập nhật **cả hai bảng**. Cassandra không cung cấp một giao dịch nguyên tử tổng quát cho hai bảng trên nhiều partition. Trong ứng dụng thật, cần định danh đơn ổn định, retry an toàn, đối soát ghi thiếu và thứ tự cập nhật. Bài này tập trung vào kiểm tra đường truy vấn và đo tải đọc.

## 3. Chuẩn bị môi trường

Cần có JDK 17 trở lên, Docker Engine/Desktop đang chạy, Gradle/Maven, JUnit Jupiter và Spring Boot Test. Cassandra trong container tốn nhiều bộ nhớ và khởi động khá lâu; môi trường CI cần cấu hình đủ CPU, RAM và startup timeout.

Ví dụ dependency Gradle (Groovy DSL) cho Testcontainers 1.x, với phiên bản do BOM/dependency management của dự án quản lý:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:cassandra'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Với Testcontainers 2.x, artifact/module và package có thể khác. Không cố lắp các bản Java Driver không tương thích vào dependency tree mà Spring Data Cassandra đang sử dụng.

Các file Java minh họa mà người học tạo trong dự án của mình:

```text
src/main/java/.../PracticeApplication.java
src/main/java/.../OrderById.java
src/main/java/.../OrderByIdRepository.java
src/test/java/.../CassandraPracticeIntegrationTest.java
```

Tất cả đường dẫn ở đây chỉ là hướng dẫn triển khai bài lab, **không phải yêu cầu tự sửa cấu trúc repository đang chứa tài liệu**.

## 4. Khởi động Cassandra và tạo schema trước Spring context

Khi Spring Data được cấu hình với `keyspace-name=practice_lab` nhưng keyspace chưa tồn tại, tạo `CqlSession` có thể thất bại. Trong ví dụ, container được khởi động và schema được tạo **trước khi Spring context bắt đầu kết nối**. `@DynamicPropertySource` chuyển địa chỉ/cổng ngẫu nhiên của container cho ứng dụng.

Ví dụ phần đầu file `CassandraPracticeIntegrationTest.java`:

```java
import java.time.Duration;

import com.datastax.oss.driver.api.core.CqlSession;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.CassandraContainer;

@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class CassandraPracticeIntegrationTest {

    static final CassandraContainer<?> cassandra =
        new CassandraContainer<>("cassandra:4.1")
            .withStartupTimeout(Duration.ofMinutes(5));

    static {
        cassandra.start();

        try (CqlSession bootstrap = CqlSession.builder()
                .addContactPoint(cassandra.getContactPoint())
                .withLocalDatacenter(cassandra.getLocalDatacenter())
                .build()) {

            bootstrap.execute("""
                CREATE KEYSPACE IF NOT EXISTS practice_lab
                WITH replication = {
                    'class': 'SimpleStrategy', 'replication_factor': 1
                }
                """);

            bootstrap.execute("""
                CREATE TABLE IF NOT EXISTS practice_lab.order_by_id (
                    order_id uuid PRIMARY KEY,
                    customer_id uuid,
                    status text,
                    created_at timestamp,
                    amount_cents bigint
                )
                """);

            bootstrap.execute("""
                CREATE TABLE IF NOT EXISTS
                    practice_lab.order_by_customer_day (
                    customer_id uuid,
                    order_day date,
                    created_at timestamp,
                    order_id uuid,
                    status text,
                    amount_cents bigint,
                    PRIMARY KEY ((customer_id, order_day),
                                 created_at, order_id)
                ) WITH CLUSTERING ORDER BY
                    (created_at DESC, order_id DESC)
                """);
        } catch (Exception e) {
            cassandra.stop();
            throw new ExceptionInInitializerError(e);
        }
    }

    @DynamicPropertySource
    static void cassandraProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.cassandra.contact-points",
            cassandra::getHost);
        registry.add("spring.cassandra.port",
            () -> cassandra.getMappedPort(9042));
        registry.add("spring.cassandra.local-datacenter",
            cassandra::getLocalDatacenter);
        registry.add("spring.cassandra.keyspace-name",
            () -> "practice_lab");
        registry.add("spring.cassandra.schema-action",
            () -> "NONE");
    }

    @Autowired CqlSession session;
    @Autowired CassandraTemplate template;
    @Autowired OrderByIdRepository repository;

    @BeforeEach
    void cleanData() {
        session.execute("TRUNCATE practice_lab.order_by_id");
        session.execute(
            "TRUNCATE practice_lab.order_by_customer_day");
    }

    @AfterAll
    static void stopContainer() {
        cassandra.stop();
    }

    // Các phương thức @Test bên dưới được bổ sung vào class này.
}
```

Ví dụ sử dụng **quản lý container thủ công** để thứ tự khởi động và tạo keyspace rõ ràng. Những dự án khác có thể dùng `@Testcontainers`/`@Container`, `@ServiceConnection` hoặc init script theo phiên bản framework. Dù theo cách nào, schema vẫn phải tồn tại trước khi repository truy cập.

Một số điểm cần lưu ý:

- `SimpleStrategy` với replication factor 1 chỉ dành cho lab một node. Test consistency với nhiều replica cần thiết kế cluster riêng.
- `getHost()` và `getMappedPort(9042)` giúp tương thích Docker port mapping. Không hard-code `localhost:9042`.
- `TRUNCATE` phù hợp để cô lập từng test trong một class **chạy tuần tự**. Không chạy song song nhiều test dùng cùng bảng rồi cùng `TRUNCATE`.
- `@DirtiesContext` giúp Spring không tái sử dụng context của class này sau khi container dừng.
- Nếu ứng dụng đã có cấu hình Cassandra riêng, kiểm tra chúng không ghi đè địa chỉ và keyspace test.

## 5. Kiểm thử entity mapping, repository và CassandraTemplate

Tạo `OrderById.java`:

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_by_id")
public class OrderById {

    @PrimaryKey("order_id")
    private UUID id;

    @Column("customer_id")
    private UUID customerId;

    private String status;

    @Column("created_at")
    private Instant createdAt;

    @Column("amount_cents")
    private Long amountCents;

    protected OrderById() {}

    public OrderById(UUID id, UUID customerId, String status,
                     Instant createdAt, Long amountCents) {
        this.id = id;
        this.customerId = customerId;
        this.status = status;
        this.createdAt = createdAt;
        this.amountCents = amountCents;
    }

    public UUID getId() { return id; }
    public UUID getCustomerId() { return customerId; }
    public String getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public Long getAmountCents() { return amountCents; }
}
```

Tạo `OrderByIdRepository.java`:

```java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderByIdRepository
        extends CassandraRepository<OrderById, UUID> {
}
```

Hai lớp được đặt trong package Spring Boot quét và cùng keyspace do session cấu hình. Với bảng này, truy vấn đúng là `findById(orderId)`. Không tự viết `findByCustomerId(...)` trên `order_by_id` khi không có partition key tương ứng.

Thêm test vào class tích hợp:

```java
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

import static org.junit.jupiter.api.Assertions.*;

@Test
void repositoryAndTemplateShouldReadTheSameOrder() {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    Instant when = Instant.parse("2026-11-25T08:15:00Z");

    repository.save(new OrderById(
        orderId, customerId, "NEW", when, 12900L));

    OrderById fromRepository =
        repository.findById(orderId).orElseThrow();

    assertEquals("NEW", fromRepository.getStatus());
    assertEquals(customerId, fromRepository.getCustomerId());
    assertEquals(12900L, fromRepository.getAmountCents());

    Query byPrimaryKey =
        Query.query(Criteria.where("order_id").is(orderId));

    OrderById fromTemplate =
        template.selectOne(byPrimaryKey, OrderById.class);

    assertNotNull(fromTemplate);
    assertEquals(orderId, fromTemplate.getId());
    assertEquals(when, fromTemplate.getCreatedAt());
}
```

Test này đi qua **Cassandra thật**, kiểm tra lưu rồi đọc lại bằng hai API Spring Data. Nó có thể phát hiện lỗi keyspace, annotation mapping hoặc tương tác thực tế với driver; mock repository sẽ không kiểm tra được các yếu tố này.

## 6. Kiểm thử AP2: truy vấn đúng partition và phân trang

CQL phục vụ mẫu AP2:

```sql
SELECT order_id, created_at, status
FROM practice_lab.order_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
LIMIT 50;
```

Query chọn đúng partition key `(customer_id, order_day)` và trả theo clustering key. `LIMIT 50` giới hạn tổng hàng sống mà query trả về; `setPageSize(5)` của driver chỉ đề nghị mỗi lần fetch một page 5 hàng. Hai khái niệm không giống nhau.

Thêm một test gồm 13 hàng để buộc driver đọc hơn một page:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

@Test
void readAllPagesWithoutMissingOrDuplicateKeys()
        throws Exception {

    UUID customer = UUID.randomUUID();
    LocalDate day = LocalDate.of(2026, 11, 25);
    Instant base = day.atStartOfDay(ZoneOffset.UTC).toInstant();

    for (int i = 0; i < 13; i++) {
        session.execute(SimpleStatement.newInstance("""
            INSERT INTO practice_lab.order_by_customer_day
                (customer_id, order_day, created_at,
                 order_id, status, amount_cents)
            VALUES (?, ?, ?, ?, ?, ?)
            """, customer, day, base.plusSeconds(i),
                UUID.randomUUID(), "NEW", 100L));
    }

    SimpleStatement read = SimpleStatement.builder("""
            SELECT order_id, created_at
            FROM practice_lab.order_by_customer_day
            WHERE customer_id = ? AND order_day = ?
            """)
        .addPositionalValues(customer, day)
        .setPageSize(5)
        .build();

    AsyncResultSet page = session.executeAsync(read)
        .toCompletableFuture().get(30, TimeUnit.SECONDS);

    List<UUID> ids = new ArrayList<>();
    List<Instant> timestamps = new ArrayList<>();

    while (true) {
        for (Row row : page.currentPage()) {
            ids.add(row.getUuid("order_id"));
            timestamps.add(row.getInstant("created_at"));
        }
        if (!page.hasMorePages()) {
            break;
        }
        page = page.fetchNextPage()
            .toCompletableFuture().get(30, TimeUnit.SECONDS);
    }

    assertEquals(13, ids.size());
    assertEquals(13, new HashSet<>(ids).size());

    for (int i = 1; i < timestamps.size(); i++) {
        assertFalse(timestamps.get(i)
            .isAfter(timestamps.get(i - 1)));
    }
}
```

`AsyncResultSet.currentPage()` và `fetchNextPage()` làm rõ ranh giới giữa các page. Với `ResultSet` đồng bộ, driver có thể tự động fetch page tiếp trong lúc lặp. Không lấy kết quả một page rồi giả định toàn bộ truy vấn đã hoàn tất.

Nếu lịch sử nằm ở nhiều `order_day`, ứng dụng phải chủ động chuyển bucket và giữ trạng thái truy vấn/paging tương ứng. Một paging state của một câu CQL không phải con trỏ để quét tùy ý sang partition khác.

### 6.1. Anti-pattern cần tránh

```sql
-- Sai hướng thiết kế cho AP2 trên bảng order_by_id:
SELECT order_id, status
FROM practice_lab.order_by_id
WHERE customer_id = ?
ALLOW FILTERING;
```

Câu lệnh trên không có partition key `order_id`; Cassandra có thể phải lọc dữ liệu ngoài phạm vi được chọn trực tiếp. Khi một query thiếu khóa phù hợp, đừng thêm `ALLOW FILTERING` như biện pháp chữa mặc định. Bảng `order_by_customer_day` được tạo chính là để phục vụ truy vấn đó.

## 7. Chuẩn bị dữ liệu cho đo tải

Một test có vài hàng chứng minh chức năng, nhưng chưa phản ánh tải. Dataset cần có phân bố rõ:

- **1.000 đơn hàng** với ID riêng cho AP1.
- Nhiều cặp `(customer_id, order_day)` cho AP2 phân tán.
- Một khách hàng “nóng” có nhiều đơn trong cùng ngày cho AP3.
- Cùng độ dài payload, consistency và cách tiêu thụ kết quả khi so profile.

Dùng ID ổn định trong dữ liệu test để các lần chạy có cùng khóa logic:

```java
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

UUID orderId = UUID.nameUUIDFromBytes(
    "order-42".getBytes(StandardCharsets.UTF_8));

UUID customer = UUID.nameUUIDFromBytes(
    "customer-7".getBytes(StandardCharsets.UTF_8));

LocalDate day = LocalDate.of(2026, 11, 25);
Instant createdAt = day.atStartOfDay(ZoneOffset.UTC)
    .toInstant().plusSeconds(42);
```

Phần seed sẽ nằm **ngoài** cửa sổ đo. Chạy warm-up có kiểm soát trước benchmark để JVM, connection pool và cache đạt trạng thái tương đối ổn định. Nếu cần so cold và warm cache, phải ghi rõ cách tạo hai trạng thái, không gọi cùng một bộ test warm-up là cold benchmark.

## 8. Thiết kế profile đo theo mẫu truy cập

| Profile | CQL | Cách chọn khóa | Điều được đo |
|---|---|---|---|
| `by-id-uniform` | AP1 | Ngẫu nhiên trên nhiều `order_id` | Tra cứu trực tiếp phân tán trên partition. |
| `by-day-uniform` | AP2 | Ngẫu nhiên nhiều cặp khách/ngày | Truy vấn theo bucket, trả tối đa 20 đơn. |
| `by-day-hot` | AP3 | Luôn chọn cùng khách/ngày | Tập trung request vào một partition. |
| `mixed-70-30` | 70% AP1, 30% AP2 | Chọn mẫu theo tỷ lệ xác suất | Gần hơn tỷ lệ workload ứng dụng. |

Mỗi profile cần đo:

- **attempts**, **success**, **errors** và **error rate**;
- **throughput** (lượt gọi mỗi giây, ghi rõ gồm cả lỗi hay chỉ thành công);
- **P50/P95/P99 latency** từ trước khi gọi query đến khi tiêu thụ đủ kết quả cần thiết;
- concurrency, số hàng/partition, số hàng trả về, page size, consistency level và phân bố khóa;
- khi cần giải thích nguyên nhân: CPU, I/O, heap/GC, số SSTable, tombstone scanned, in-flight requests và retry của driver.

P99 có nghĩa xấp xỉ 99% mẫu đo không vượt quá giá trị đó. Với mẫu ít hoặc môi trường nhiều nhiễu, P99 có thể dao động mạnh; chạy nhiều vòng và báo sự biến thiên.

## 9. Helper đo tải với giới hạn concurrency

Dùng nhiều thread gọi một `CqlSession` chung: driver thiết kế session để sử dụng lại và phục vụ các yêu cầu đồng thời. Mỗi worker gửi nhiều yêu cầu, ghi thời gian bằng `System.nanoTime()` và cùng bắt đầu từ một barrier.

Thêm helper sau vào class test hoặc class tiện ích riêng:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

record LoadResult(
    String profile,
    int attempts,
    int errors,
    double seconds,
    double attemptsPerSecond,
    double p50Ms,
    double p95Ms,
    double p99Ms
) {}

static LoadResult measure(
        String profile, int workers, int requests,
        Runnable operation) throws Exception {

    if (workers <= 0 || requests <= 0) {
        throw new IllegalArgumentException("Invalid load size");
    }

    ExecutorService pool = Executors.newFixedThreadPool(workers);
    CountDownLatch ready = new CountDownLatch(workers);
    CountDownLatch start = new CountDownLatch(1);
    ConcurrentLinkedQueue<Long> durations =
        new ConcurrentLinkedQueue<>();
    AtomicInteger errors = new AtomicInteger();
    List<Future<?>> tasks = new ArrayList<>();

    try {
        for (int worker = 0; worker < workers; worker++) {
            final int workerIndex = worker;
            tasks.add(pool.submit((Callable<Void>) () -> {
                ready.countDown();
                if (!start.await(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Start timed out");
                }
                for (int i = workerIndex; i < requests; i += workers) {
                    long began = System.nanoTime();
                    try {
                        operation.run();
                    } catch (RuntimeException failure) {
                        errors.incrementAndGet();
                    } finally {
                        durations.add(System.nanoTime() - began);
                    }
                }
                return null;
            }));
        }

        if (!ready.await(30, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Workers not ready");
        }

        long startedAt = System.nanoTime();
        start.countDown();
        for (Future<?> task : tasks) {
            task.get(120, TimeUnit.SECONDS);
        }

        double elapsed =
            (System.nanoTime() - startedAt) / 1_000_000_000.0;

        List<Long> sorted = new ArrayList<>(durations);
        Collections.sort(sorted);

        if (sorted.size() != requests) {
            throw new IllegalStateException("Incomplete samples");
        }

        return new LoadResult(
            profile, requests, errors.get(), elapsed,
            requests / elapsed,
            percentileMs(sorted, 0.50),
            percentileMs(sorted, 0.95),
            percentileMs(sorted, 0.99)
        );
    } finally {
        start.countDown();
        pool.shutdownNow();
    }
}

static double percentileMs(List<Long> sortedNanos, double p) {
    int index = Math.max(0, Math.min(sortedNanos.size() - 1,
        (int) Math.ceil(p * sortedNanos.size()) - 1));
    return sortedNanos.get(index) / 1_000_000.0;
}
```

Helper đo **attempted throughput** và latency của cả attempt lỗi. Mã ghi số lỗi nhưng chưa phân loại exception để giữ đoạn thực hành ngắn; trong benchmark thật, ghi thêm loại lỗi và một số mẫu exception đã che dữ liệu nhạy cảm.

**Giới hạn phương pháp:** đây là **closed-loop generator**: mỗi worker chỉ phát yêu cầu tiếp khi yêu cầu trước kết thúc. Khi Cassandra chậm, tốc độ phát yêu cầu tự giảm, có thể che queueing so với traffic đến có tốc độ cố định. Để đánh giá SLO dưới arrival rate thực, cần công cụ phát tải **open-loop/constant-arrival-rate** và báo cáo phương pháp tương ứng.


## 10. Tạo dữ liệu và thực thi bốn profile

Kích hoạt profile đo tải một cách **chủ động** bằng biến môi trường `RUN_CASSANDRA_LOAD_TEST=true`. Điều này giữ cho bộ test chức năng thường ngày nhanh và ít nhiễu hơn.

Các import cần dùng:

```java
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import static org.junit.jupiter.api.Assertions.assertEquals;
```

Đặt record hỗ trợ và test bên trong `CassandraPracticeIntegrationTest`:

```java
record CustomerDay(UUID customerId, LocalDate day) {}

@Test
@Tag("load")
@EnabledIfEnvironmentVariable(
    named = "RUN_CASSANDRA_LOAD_TEST", matches = "true")
void measureByAccessPattern() throws Exception {

    LocalDate day = LocalDate.of(2026, 11, 25);
    Instant base = day.atStartOfDay(ZoneOffset.UTC).toInstant();

    UUID hotCustomer = UUID.nameUUIDFromBytes(
        "hot-customer".getBytes(StandardCharsets.UTF_8));

    PreparedStatement insertById = session.prepare("""
        INSERT INTO practice_lab.order_by_id
            (order_id, customer_id, status,
             created_at, amount_cents)
        VALUES (?, ?, ?, ?, ?)
        """);

    PreparedStatement insertByDay = session.prepare("""
        INSERT INTO practice_lab.order_by_customer_day
            (customer_id, order_day, created_at,
             order_id, status, amount_cents)
        VALUES (?, ?, ?, ?, ?, ?)
        """);

    List<UUID> ids = new ArrayList<>();
    LinkedHashSet<CustomerDay> daySet = new LinkedHashSet<>();

    // 1.000 hàng, trong đó 200 hàng ở cùng một partition hot.
    for (int i = 0; i < 1000; i++) {
        UUID orderId = UUID.nameUUIDFromBytes(
            ("order-" + i).getBytes(StandardCharsets.UTF_8));

        UUID customer = i < 200
            ? hotCustomer
            : UUID.nameUUIDFromBytes(
                ("customer-" + i / 10)
                    .getBytes(StandardCharsets.UTF_8));

        Instant createdAt = base.plusSeconds(i);

        session.execute(insertById.bind(
            orderId, customer, "NEW", createdAt, 1000L));

        session.execute(insertByDay.bind(
            customer, day, createdAt,
            orderId, "NEW", 1000L));

        ids.add(orderId);
        daySet.add(new CustomerDay(customer, day));
    }

    List<CustomerDay> customerDays = new ArrayList<>(daySet);

    PreparedStatement readById = session.prepare("""
        SELECT order_id, status
        FROM practice_lab.order_by_id
        WHERE order_id = ?
        """);

    PreparedStatement readByDay = session.prepare("""
        SELECT order_id, created_at, status
        FROM practice_lab.order_by_customer_day
        WHERE customer_id = ? AND order_day = ?
        LIMIT 20
        """);

    Runnable byId = () -> {
        UUID order = ids.get(
            ThreadLocalRandom.current().nextInt(ids.size()));
        Row found = session.execute(readById.bind(order)).one();

        if (found == null) {
            throw new IllegalStateException("Missing order");
        }
    };

    Runnable byDayUniform = () -> {
        CustomerDay key = customerDays.get(
            ThreadLocalRandom.current()
                .nextInt(customerDays.size()));

        int count = 0;
        for (Row ignored : session.execute(readByDay.bind(
                key.customerId(), key.day()))) {
            count++;
        }

        if (count == 0) {
            throw new IllegalStateException("Missing customer day");
        }
    };

    Runnable byDayHot = () -> {
        int count = 0;
        for (Row ignored : session.execute(
                readByDay.bind(hotCustomer, day))) {
            count++;
        }

        if (count != 20) {
            throw new IllegalStateException("Hot bucket incomplete");
        }
    };

    Runnable mixed = () -> {
        if (ThreadLocalRandom.current().nextInt(100) < 70) {
            byId.run();
        } else {
            byDayUniform.run();
        }
    };

    // Warm-up trước khi thu thập latency.
    for (int i = 0; i < 200; i++) {
        byId.run();
        byDayUniform.run();
        byDayHot.run();
    }

    // Cùng số worker và attempts cho mỗi profile.
    List<LoadResult> results = List.of(
        measure("by-id-uniform", 8, 2000, byId),
        measure("by-day-uniform", 8, 2000, byDayUniform),
        measure("by-day-hot", 8, 2000, byDayHot),
        measure("mixed-70-30", 8, 2000, mixed)
    );

    for (LoadResult r : results) {
        System.out.printf(
            "%s attempts=%d errors=%d throughput=%.1f/s "
                + "p50=%.2fms p95=%.2fms p99=%.2fms%n",
            r.profile(), r.attempts(), r.errors(),
            r.attemptsPerSecond(), r.p50Ms(),
            r.p95Ms(), r.p99Ms());
    }

    assertEquals(0, results.stream()
        .mapToInt(LoadResult::errors).sum());
}
```

**Những điều phép thử thực sự thực hiện:**

- AP1 chọn ngẫu nhiên trên 1.000 `order_id`, nghĩa là phân tán trên nhiều partition cho dù một số ID thuộc cùng khách hàng.
- AP2 chọn ngẫu nhiên trong **tập cặp customer/day duy nhất**. Không dùng danh sách lặp lại 200 lần của khách hàng nóng để vô tình khiến profile “uniform” bị lệch.
- AP3 truy vấn một partition có 200 đơn nhưng chỉ trả 20 đơn mới nhất, mô phỏng nhiều request cùng một khóa.
- Profile mixed thực hiện lựa chọn **theo xác suất**, vì vậy mỗi lần chạy có thể không có đúng 70,00% AP1. Nếu cần tỷ lệ chính xác, tạo trước một schedule có seed và trộn thứ tự.
- Kết quả đo ghi nhận cả lần lỗi; nếu có lỗi, assertion cuối giúp test fail. Khi phân tích tải chịu lỗi, có thể thay assertion bằng ngưỡng lỗi rõ ràng cùng báo cáo nguyên nhân.

Các profile chạy tuần tự nên kết quả chịu tác động của **cache warming và thứ tự chạy**. Nên thực hiện nhiều lượt, thay đổi thứ tự profile hoặc khởi tạo lại môi trường giữa các nhóm so sánh quan trọng. Đừng kết luận AP3 luôn chậm hơn AP2: trên một node, partition nóng có thể nằm trong cache và trả lời nhanh, trong khi trên cụm nhiều replica tải tập trung có thể gây nghẽn.

## 11. Chạy test bằng Gradle và ghi báo cáo

Lệnh chạy test chức năng trên Linux/macOS:

```bash
./gradlew test --tests '*CassandraPracticeIntegrationTest'
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*CassandraPracticeIntegrationTest'
```

Phần tải có `@EnabledIfEnvironmentVariable` nên mặc định không được chạy. Khi muốn chạy các profile:

```powershell
$env:RUN_CASSANDRA_LOAD_TEST = "true"
.\gradlew.bat test --tests '*CassandraPracticeIntegrationTest'
```

Người học cần chạy lệnh trên **trong dự án thực hành đã bổ sung các file Java** và có Docker đang hoạt động. Bài Markdown này cung cấp hướng dẫn, chưa tự thực thi Gradle.

Lập báo cáo gồm tối thiểu:

```text
Run ID: cassandra-practice-local-001
Cassandra image: 4.1 / 1 node / replication factor 1
JDK / Spring Boot / Spring Data / Java Driver / Testcontainers: ...
OS, Docker CPU/RAM, ổ đĩa và tài nguyên khác: ...
Dataset: 1.000 orders; 200 rows trên hot customer/day
Consistency: ... (ghi giá trị driver thực sự áp dụng)
Concurrency: 8
Attempts/profile: 2.000
Warm-up: 200 lời gọi/profile trước khi đo
Query/page size, số hàng đã tiêu thụ: ...
Kết quả: throughput, P50/P95/P99, errors/error rate
```

Bảng dưới đây là **dữ liệu giả lập để minh họa cách báo cáo, không phải kết quả đã đo**:

| Profile | Throughput (req/s) | P50 (ms) | P95 (ms) | P99 (ms) | Error rate |
|---|---:|---:|---:|---:|---:|
| by-id-uniform | 420 | 8 | 16 | 24 | 0% |
| by-day-uniform | 365 | 10 | 21 | 31 | 0% |
| by-day-hot | 450 | 7 | 15 | 22 | 0% |
| mixed-70-30 | 402 | 9 | 18 | 28 | 0% |

Chỉ viết kết luận từ **số liệu thực sự thu thập được**. Cùng một query có thể cho latency khác nhau giữa máy cá nhân và CI vì Docker CPU throttling, disk I/O, JIT, cache, Garbage Collection, network và số request đang chạy đồng thời.

### 11.1. Vì sao không assert cứng P99 trong unit test?

Một assertion như “P99 phải dưới 20 ms” trên Testcontainers thường dễ bị **flaky**: kết quả phụ thuộc máy chạy hơn là chất lượng code. Test chức năng nên assert kết quả, số hàng, thứ tự, khóa duy nhất và không có lỗi. Với kiểm thử hiệu năng, so sánh baseline trên hạ tầng ổn định hoặc kiểm tra ngân sách SLO theo quy trình benchmark có nhiều lần lặp, trạng thái warm-up và dữ liệu đại diện.

## 12. Mở rộng thí nghiệm có kiểm soát

Sau baseline, chỉ thay đổi một biến mỗi lần để tìm nguyên nhân.

### 12.1. Số hàng và kích thước partition

Tạo AP2 với ba mức: khoảng 20–100 hàng/partition, 1.000 hàng/partition và hàng chục nghìn hàng/partition trong môi trường đủ tài nguyên. Giữ nguyên `LIMIT 20` rồi đo P95/P99, bytes trả về, số page thực tế và metric SSTable/cell. Một truy vấn trả 20 hàng vẫn có thể phải xử lý nhiều dữ liệu hơn nếu partition có nhiều tombstone, ghi đè hoặc các hàng đã hết TTL.

### 12.2. Concurrency và điểm bão hòa

Giữ dataset/query không đổi và chạy các mức ví dụ 1, 4, 8, 16, 32 worker. Với mỗi mức, ghi throughput, error rate và P99. Khi throughput không tăng nữa nhưng P99/timeout tăng, có thể hệ thống vượt qua điểm bão hòa. Cần nhìn thêm CPU/GC, số request đang chờ, compaction và network trước khi quy kết cho partition.

Một ví dụ minh họa kỳ vọng chung (không phải kết quả chạy):

```text
workers:     1 -> 4 -> 8 -> 16 -> 32
throughput:  tăng, rồi có thể bão hòa
P99:         có thể tăng mạnh khi hàng đợi đầy
errors:      có thể tăng nếu timeout/overload xảy ra
```

### 12.3. Page size và tổng dữ liệu đã tiêu thụ

So `setPageSize(10)`, `50` và `100` trên cùng truy vấn và cùng số hàng cần trả cho API. Đo đến khi **tiêu thụ đủ kết quả yêu cầu**, không chỉ đến page đầu. Dùng cả số page fetch và số hàng sống thực tế để đánh giá; page size là gợi ý fetch, không bảo đảm mọi page luôn đầy vì tombstone/giới hạn server.

### 12.4. Consistency level trong cụm nhiều node

Với RF=1 trong container một node, thay đổi `LOCAL_ONE` và `LOCAL_QUORUM` không mô phỏng được chi phí phối hợp nhiều replica. Muốn đánh giá độ trễ, availability và tính nhất quán, phải dùng cụm nhiều node có replication phù hợp, điều kiện kết nối cụ thể và mô hình node failure. Mức consistency **không thay thế** thiết kế partition key đúng.

### 12.5. Phân biệt cold cache và warm cache

Thực hiện hai phép đo riêng với trạng thái cache được kiểm soát và ghi rõ thao tác trước mỗi lần đo. Không mặc định lần đầu ngay sau seed là cold cache: dữ liệu vừa ghi có thể vẫn ở memtable/cache. Với thử nghiệm cache thật sự cần hiểu read path của Cassandra và cách hệ điều hành/container dùng bộ nhớ.

## 13. Giới hạn của Testcontainers và benchmark production

Một node Testcontainers kiểm tra tốt **syntax, mapping, CQL, paging, dữ liệu thật và logic test**. Nó không mô phỏng đầy đủ:

| Lab một node | Cần bổ sung để đánh giá gần production |
|---|---|
| RF=1, không phối hợp nhiều replica | Cụm nhiều node và consistency đúng kiến trúc. |
| Dataset ít, có thể nằm trong cache | Phân bố dữ liệu thực: cardinality, hot partition, tombstone, TTL, partition lớn. |
| Client và server dùng chung máy chạy Docker | Load generator tách CPU/network hoặc quan sát rõ tranh chấp tài nguyên. |
| Test vài nghìn request, thời gian ngắn | Warm-up, steady state, soak test, arrival rate được kiểm soát. |
| Không có lỗi mạng/replica | Fault injection, mất node, packet loss, timeout, retry và reconnect. |
| Chỉ một số API đọc | Tỷ lệ đọc/ghi, kích thước payload, paging và các workflow thực tế. |

Không dựa vào benchmark local để cam kết throughput của cụm production. Nếu cần thí nghiệm gần thực tế, dùng staging cô lập, dữ liệu tổng hợp hoặc dữ liệu được phép, bảo đảm không làm ảnh hưởng người dùng và có kế hoạch quản lý tải.

### 13.1. Metric nên kết hợp từ driver, Cassandra và JVM

- **Java Driver:** request latency, in-flight requests, pool usage, timeout/retry, speculative execution nếu có.
- **Cassandra:** read latency, SSTable count, tombstone scanned, compaction backlog, dropped messages, CPU/I/O.
- **Spring Boot/Micrometer:** endpoint latency, error rate, executor usage, heap/GC.
- **Container/OS:** CPU quota, throttling, RAM, disk IOPS, network.

Kết hợp metric mới phân biệt được query bị ảnh hưởng bởi **hot partition**, dữ liệu hết hạn/tombstone, cache, compaction hay quá tải từ client.

## 14. Các lỗi dễ gặp khi chạy bài thực hành

| Triệu chứng | Nguyên nhân khả dĩ | Cách sửa |
|---|---|---|
| Docker không hoạt động | Testcontainers không khởi tạo được Cassandra | Bật Docker, xác nhận quyền truy cập daemon và tài nguyên. |
| Cassandra chưa ready trước timeout | Image khởi động chậm, thiếu CPU/RAM | Kiểm tra log container, chỉnh startup timeout/tài nguyên. |
| `Invalid keyspace` khi dựng context | Spring kết nối trước khi tạo keyspace | Khởi động bootstrap và tạo schema trước context. |
| Driver không tìm được node | Sai mapped port hoặc local datacenter | Dùng `getHost()`, `getMappedPort(9042)` và `getLocalDatacenter()`. |
| Repository lỗi unknown column | Annotation mapping không khớp CQL | Kiểm tra `@PrimaryKey`, `@Column` và schema. |
| AP2 trả 0 hàng | Sai customer/day hoặc ngày tính lệch timezone | Seed và query với cùng UTC bucket. |
| Test paging chỉ đọc 5 thay vì 13 hàng | Quên gọi `fetchNextPage()` | Lặp tới `hasMorePages() == false`. |
| Test tải có P99 thất thường | JVM/Docker/cache/concurrency thay đổi | Warm-up, chạy nhiều vòng, ghi điều kiện môi trường. |
| Tỷ lệ lỗi cao nhưng throughput vẫn đẹp | Chỉ tính số request đã cố gửi, lỗi bị bỏ qua | Báo error rate và phân loại exception; chỉ so throughput thành công khi phù hợp. |
| Hai test làm mất dữ liệu nhau | `TRUNCATE` cùng bảng khi chạy song song | Cô lập keyspace hoặc chạy tuần tự. |
| Query AP2 bắt buộc `ALLOW FILTERING` | Primary key không phục vụ truy vấn | Đổi bảng/mẫu truy cập thay vì dựa vào lọc toàn bảng. |

**Không retry vô hạn khi gặp timeout.** Một `session.execute()` có thể được Java Driver retry theo policy; tổng số attempt phía Cassandra có thể lớn hơn số lần gọi trong bộ phát tải. Ghi rõ retry policy và consistency level khi so kết quả.

## 15. Tiêu chí nghiệm thu

Một bài làm hoàn chỉnh cần chứng minh:

1. Cassandra thật chạy qua Testcontainers; Spring context kết nối đúng host, mapped port và keyspace.
2. Repository và `CassandraTemplate` ghi/đọc entity chính xác bằng `order_id`.
3. Truy vấn theo `(customer_id, order_day)` trả dữ liệu đúng thứ tự, có test nhiều page không thiếu hoặc trùng khóa.
4. Bộ seed có cardinality, số hàng, kích thước partition nóng và quy tắc timestamp/UTC rõ ràng.
5. Chạy được ít nhất hai profile AP1 và AP2; nên có AP3 và profile mixed.
6. Thu thập throughput, P50/P95/P99, error rate, concurrency, số request, số hàng trả về và điều kiện môi trường.
7. Có nhận xét dựa trên **chính số liệu đo được**, giải thích điều kiện có thể gây sai khác và chỉ rõ hạn chế một node.
8. Test tải chỉ bật có chủ đích; test chức năng có thể chạy thường xuyên mà không phụ thuộc benchmark nặng.

Mẫu báo cáo sau khi thực hành:

```text
Environment:
  JDK: ...
  Spring Boot / Spring Data / Driver: ...
  Cassandra image / Testcontainers: ...
  CPU / RAM / Disk / Docker limits: ...

Data:
  total orders: ...
  distinct customers: ...
  partition sizes: ...
  hot customer/day: ...

Profiles:
  AP1 uniform: ... req/s, P50/P95/P99 ..., errors ...
  AP2 uniform: ... req/s, P50/P95/P99 ..., errors ...
  AP3 hot: ... req/s, P50/P95/P99 ..., errors ...
  mixed: ... req/s, P50/P95/P99 ..., errors ...

Findings:
  - Mẫu truy cập nào có P99 lớn nhất?
  - Có bằng chứng nào về hot partition/cache/compaction?
  - Có cần đổi bucket, page size hoặc concurrency không?

Next experiment:
  - Chỉ thay một biến rồi chạy lại cùng dataset.
```

## 16. Bài tập mở rộng

### Bài A — Thay bucket ngày bằng bucket giờ

Một khách hàng sinh 80.000 đơn/ngày. Thiết kế bảng theo `(customer_id, order_hour)`, bổ sung logic đọc nhiều bucket liên tiếp và so sánh số partition cần truy vấn, kích thước partition, P99 với bucket ngày. Chỉ rõ trade-off khi bucket nhỏ hơn.

### Bài B — Thêm profile ghi và tính lũy đẳng

Dùng ID ổn định rồi đo `INSERT/UPDATE` gán giá trị cố định ở bảng `order_by_id`. Phân biệt số lần ghi thành công và số hàng duy nhất. Giải thích tại sao đổi thao tác thành `counter = counter + 1` khiến retry sau timeout nguy hiểm.

### Bài C — TTL, tombstone và đọc dải thời gian

Trên bảng test riêng, ghi các hàng có TTL ngắn, đợi hết hạn và đo truy vấn đọc phải duyệt nhiều dữ liệu hết hiệu lực. So sánh số hàng trả về, latency và tombstone scanned nếu tracing/metric hỗ trợ. Không giả định TTL hết thì dung lượng đĩa giảm ngay.

### Bài D — Tiêu thụ đúng số hàng API cần

Một API chỉ trả 50 item nhưng code duyệt toàn bộ `ResultSet` không có `LIMIT`. Hãy điều chỉnh statement và logic tiêu thụ để không fetch thêm dữ liệu không cần. Đo số page, latency và memory trước/sau.

### Bài E — Thử nghiệm nhiều node

Tạo môi trường Cassandra nhiều replica và so `LOCAL_ONE` với `LOCAL_QUORUM` khi một replica bị ngắt. Đo độ trễ, error rate, availability và cơ chế retry. Giải thích tại sao test một node không thể cho cùng kết luận.

## 17. Ghi nhớ

- **Testcontainers** xác minh mapping, schema, CQL và paging với Cassandra thật mà không phụ thuộc một cluster chia sẻ.
- **Mẫu truy cập quyết định thiết kế bảng**: AP1 và AP2 cần partition key phục vụ trực tiếp cho từng truy vấn.
- **Đo riêng từng profile**: phân tán theo ID, theo bucket và hot partition cung cấp những tín hiệu khác nhau; đừng chỉ báo một con số throughput.
- **Độ trễ và lỗi phải đi cùng nhau**: P50/P95/P99, error rate, concurrency, consistency, dataset và page size là một bộ ngữ cảnh không thể tách rời.
- **Test chức năng khác benchmark**: kiểm thử logic nên ổn định; đo tải bật có chủ đích và so trên môi trường được kiểm soát.
- **Một node không đại diện cho cụm phân tán**: replication, node failure, consistency và SLO production cần thử nghiệm riêng với nhiều replica.

Hoàn thành bài này có nghĩa bạn không chỉ chứng minh **Spring Data Cassandra kết nối và truy vấn thành công**, mà còn có phương pháp đo để trả lời: **mẫu truy cập nào đang hiệu quả, nơi nào hình thành partition nóng và bằng chứng nào cho thấy cần thay đổi schema hoặc giới hạn tải?**


