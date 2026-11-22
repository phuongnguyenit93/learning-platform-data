# Kiểm thử truy vấn với kích thước, phân bố và đặc điểm dữ liệu phù hợp

## 1. Một truy vấn đúng trên 5 bản ghi chưa chắc đúng trên dữ liệu thật

Một lỗi kiểm thử dữ liệu phổ biến là tạo ba đến năm dòng với giá trị khác nhau hoàn toàn, chạy `repository.find...()`, thấy kết quả đúng rồi kết luận truy vấn đã được kiểm chứng. Dataset ấy thường không có các đặc điểm tạo ra bug trong thực tế: hàng triệu bản ghi, tenant chiếm phần lớn dữ liệu, trạng thái không đồng đều, khóa ngoại có nhiều bản ghi con, giá trị `NULL`, dữ liệu trùng, thời gian bằng nhau, giá trị ngoại lệ hoặc dữ liệu thay đổi đồng thời khi đang phân trang.

Ví dụ: một API tìm hóa đơn đã thanh toán trong một tenant, sắp xếp mới nhất và trả 40 bản ghi một trang. Khi có ba hóa đơn với ba thời điểm khác nhau, cách sắp xếp chỉ bằng `createdAt` dường như đúng. Khi có hàng nghìn hóa đơn trùng thời điểm, việc thiếu tiêu chí phụ `id` có thể khiến nội dung giữa hai trang không ổn định. Khi tenant lớn có 70% bản ghi đã thanh toán nhưng tenant nhỏ chỉ có 20%, một index hiệu quả cho tenant này có thể không hiệu quả cho tenant khác. Khi có một hóa đơn rất lớn, cách tính tổng bằng `int` có thể bị tràn.

**Chủ đề của bài:** cách thiết kế, tạo và kiểm chứng **dữ liệu thử nghiệm có kích thước, phân bố và đặc điểm phù hợp với câu truy vấn**, thay vì xem dữ liệu thử nghiệm chỉ là vài dòng phụ trợ cho test.

### Sau bài học, bạn có thể

1. Phân biệt **đúng logic truy vấn** và **hiệu năng truy vấn**: chúng cần bằng chứng khác nhau.
2. Phân tích workload thật để chọn số bản ghi, cardinality, tần suất các giá trị, độ lệch phân bố, quan hệ bảng và trường hợp biên.
3. Dùng dataset **deterministic**, có seed và thống kê kỳ vọng rõ ràng, có thể tạo lại trên máy phát triển/CI.
4. Viết Spring Data JPA tests cho filter theo tenant, trạng thái, khoảng thời gian nửa mở, `NULL`, chuỗi rỗng, giá trị trùng, tổng hợp và phân trang.
5. Hiểu vì sao `Page`, `Slice`, offset paging, keyset/seek paging và `ORDER BY` có tie-breaker khác nhau.
6. Đọc `EXPLAIN`/`EXPLAIN ANALYZE` và nhận biết tác động của index, statistics, skew, correlated columns và database engine.
7. Tránh benchmark thiếu kiểm soát như `assertThat(duration).isLessThan(100)` trên laptop/CI shared runners.
8. Dùng Java 17+, Spring Boot 3.x, Spring Data JPA, H2 và JUnit Jupiter để xây một ví dụ hoàn chỉnh với 1.200 dòng và **11 phép kiểm thử JUnit**.
9. Biết khi nào H2/`@DataJpaTest` đủ để kiểm tra logic và khi nào phải dùng PostgreSQL/MySQL thật, Testcontainers và test tải riêng.

**Phạm vi:** mục tiêu trực tiếp là *dữ liệu kiểm thử cho truy vấn SQL/JPA*. Bài phân tích đặc điểm dữ liệu từ góc độ Spring Boot Testing, không coi 1.200 dòng là kích thước đại diện cho mọi hệ thống production. Ví dụ runnable nhắm Spring Boot **3.x/Jakarta Persistence/Hibernate 6/Java 17+**; phiên bản khác cần kiểm tra lại imports, dependencies và SQL dialect.

## 2. Cần mô tả dataset bằng những chiều nào?

Một dataset hữu ích không chỉ có trường `size = N`. Nó phải mô tả ít nhất các chiều liên quan đến **predicate, join, grouping, ordering và business constraints** của truy vấn.

| Chiều dữ liệu | Câu hỏi thiết kế | Loại bug có thể lộ ra |
|---|---|---|
| **Số hàng** | 0, 1, bằng page size, vượt page size, hàng nghìn/hàng triệu? | Empty result, limit/offset, memory, count query |
| **Phân bố tenant/group** | Tenant lớn chiếm 75%, các tenant nhỏ chia 25% hay đồng đều? | Tenant leakage, độ chọn lọc, index lệch |
| **Tần suất trạng thái** | 70% PAID hay chỉ 1% PAID? Có status hiếm? | Plan selectivity, count, wrong predicate |
| **Giá trị NULL** | Một trường có null 5%, 40% hay không? | `IS NULL`, outer join, sort null order |
| **Giá trị trùng** | Nhiều rows cùng customer/time/code không? | Duplicate handling, pagination ties, aggregation |
| **Chuỗi rỗng và khoảng trắng** | `""`, `" "`, Unicode, mixed case tồn tại? | Trim, collation, equality, normalization |
| **Phân bố thời gian** | Giờ cao điểm, trùng timestamp, các mốc biên, quá khứ? | Inclusive/exclusive ranges, order ties |
| **Giá trị ngoại lệ** | Số tiền lớn bất thường, chuỗi rất dài, số âm hợp lệ? | Overflow, precision, sorting, validation |
| **Tương quan nhiều cột** | Tenant lớn cũng thường có trạng thái PAID hơn? | Planner estimate sai, cross-filter bugs |
| **Cardinality quan hệ** | 1:n có n=0, n=1, n=1000 hay fan-out lớn? | JOIN duplicates, GROUP BY, N+1, pagination |
| **Độ rộng hàng** | TEXT/BLOB/JSON lớn hay chỉ ID/enum? | I/O, memory, serialization, index-only scan |
| **Lịch sử/thay đổi** | Dữ liệu xóa mềm, archived, version cũ? | Filter bị quên, snapshot, concurrent paging |
| **Ngữ nghĩa đặc thù** | Multi-tenant, PII, timezone, tiền tệ, mã hóa? | Security, timezone, precision/collation |

**Tư duy quan trọng:** chọn các chiều **ảnh hưởng truy vấn đang kiểm thử**. Không cần nhét mọi trường hợp vào một fixture khổng lồ. Nếu truy vấn chỉ tìm email duy nhất, cardinality email và case-sensitivity là ưu tiên. Nếu truy vấn báo cáo doanh thu theo tháng, phân bố thời gian, trạng thái, giá trị tiền và số bản ghi quyết định chất lượng dữ liệu thử nghiệm.

### 2.1. Cardinality và selectivity

- **Cardinality** của một cột: số giá trị khác nhau. Ví dụ cột `status` có ba giá trị, cột `id` có 1.200 giá trị.
- **Selectivity** của điều kiện: tỷ lệ rows khớp. Ví dụ `tenant_id='HOT' AND entry_state='PAID'` khớp 630/1.200 = 52,5% toàn bảng; còn `tenant_id='COLD' AND entry_state='PAID'` chỉ khớp 60/1.200 = 5%.
- Một điều kiện rất phổ biến có thể trả lượng dữ liệu lớn; một điều kiện hiếm có thể chỉ trả vài hàng. Cả hai cần test vì truy vấn và query planner có thể xử lý rất khác nhau.

Một công thức định hướng:

\[
\text{selectivity}(P) = \frac{\text{số hàng thỏa predicate }P}{\text{tổng số hàng}}
\]

Không sử dụng cardinality như từ đồng nghĩa với selectivity. Hai cột cùng có 10 giá trị khác nhau nhưng tần suất các giá trị rất lệch vẫn tạo hành vi khác nhau.

### 2.2. Skew: dữ liệu không chia đều

Dataset đồng đều có thể ẩn một failure mode phổ biến:

```text
Một dataset đều:
  Tenant A: 500 rows, 250 PAID
  Tenant B: 500 rows, 250 PAID

Một dataset lệch:
  Tenant HOT : 900 rows, 630 PAID
  Tenant COLD: 300 rows,  60 PAID
```

Tổng cùng 1.000 hoặc 1.200 chưa nói lên selectivity của từng predicate. Query plan có thể thích quét bảng ở nhóm chiếm đa số nhưng tận dụng index khi lọc nhóm hiếm. Kiểm tra một tenant đại diện “trung bình” không đủ cho multi-tenant app có vài tenant rất lớn.

### 2.3. Correlation: điều kiện không độc lập

Nếu trong tenant HOT có 70% PAID, trong COLD có 20% PAID, hai cột `tenant_id` và `entry_state` **có tương quan**. Bộ dữ liệu tạo uniform random status không tái hiện được sự tương quan ấy.

Các query planners có thể cần *extended/multivariate statistics* để ước tính selectivity của nhiều cột kết hợp. Chẳng hạn PostgreSQL có extended statistics (dependencies, n-distinct, most-common-value combinations) được thu thập qua `ANALYZE`; việc chúng có tác dụng phụ thuộc query, phiên bản và configuration. **Đây là đặc điểm phải đo trên database engine thật**, không phải khẳng định H2 sẽ chọn cùng plan.

### 2.4. Duplicate và ties không phải dữ liệu lỗi

Nếu một customer có hàng trăm đơn hàng, dữ liệu đó **hợp lệ**. Nếu nhiều giao dịch có timestamp bằng nhau do ghi batch hoặc precision của DB, dữ liệu đó cũng thường hợp lệ. Test chỉ tạo giá trị unique ở mọi cột sẽ không bao giờ phát hiện các bug:

- Query vô tình dùng `distinct` và làm mất bản ghi hợp lệ.
- `LIMIT/OFFSET` thiếu stable ordering khiến trang 1/trang 2 overlap.
- `GROUP BY` thiếu field làm sai aggregate.
- JOIN một-to-n tạo fan-out và trả trùng entity.
- Mapping query dùng `getSingleResult()` trong khi điều kiện không unique.

## 3. Tách hai mục tiêu: correctness và performance

### 3.1. Query correctness test

Test logic phải có assertions xác định:

- Có đúng rows theo tenant, state, timestamp?
- Có rò rỉ rows của tenant khác?
- `NULL` và `""` có bị nhầm?
- Duplicate keys có bị vô tình loại?
- Kết quả phân trang đủ phần tử, total count, thứ tự ổn định?
- Tổng/số lượng có đúng với outlier, large values?
- Empty result có xử lý đúng?
- Page cuối và page không tồn tại có đúng?
- Query sort có tránh mâu thuẫn khi nhiều rows cùng time?

Bài test kiểu này nên deterministic, có thể chạy nhiều lần và có giá trị thật cho CI. Không cần một triệu rows nếu 1.200 rows **được cấu trúc đúng để lộ bug**.

### 3.2. Query performance test

Test hiệu năng cần các điều kiện khác:

- Tổng row count và index sizes đủ giống production workload.
- Distribution, histogram, most-common values, correlation, fan-out tương ứng.
- DB engine/version/collation/isolation/configuration tương thích production.
- Dataset được `ANALYZE`/statistics cập nhật theo cách môi trường thật hoạt động.
- Có warm-up, cache state (cold/warm), concurrency, connection pool, client network latency.
- Đo p50/p95/p99, throughput, memory, I/O và query plans phù hợp.
- Ngân sách/SLO được xác định độc lập với một lần chạy CI trên shared runner.
- Có baseline và cùng điều kiện thử nghiệm trước khi kết luận performance regression.

**Không dùng một mốc cứng “SQL phải chạy dưới 20 ms” trong unit-test JVM/H2 rồi cho rằng production đã đạt SLO.** Độ trễ đo được chịu ảnh hưởng JIT, GC, CI neighbors, disk/cache, network, database settings và query planner. Có thể dùng performance integration job tách riêng cho regressions có thống kê, hoặc assert plan shape có điều kiện và không quá brittle, thay vì assertions dựa vào vài mili giây trên H2.

### 3.3. Một ma trận cấp độ kiểm thử hợp lý

| Cấp test | Dữ liệu | Mục đích | Nhịp chạy |
|---|---|---|---|
| Unit logic | Vài object cố định | Pure filter/domain logic | Mỗi commit |
| `@DataJpaTest`/H2 | Vài trăm–vài nghìn rows có shape | Repository correctness, paging, aggregation | Mỗi commit hoặc PR |
| Integration + production DB engine | Cỡ vừa và có skew đúng | SQL dialect, index, count/JOIN, constraints | PR/main tùy chi phí |
| Performance job | Tỷ lệ scale và phân bố gần production | Query plans, latency distributions, memory/I/O | Nightly/weekly/pre-release |
| Staging/e2e | Workload ẩn danh/synthetic | End-to-end API, proxy, caching, concurrency | Theo release |
| Production monitoring | Workload thực, có bảo vệ PII | Quan sát slow queries, regression alerts | Liên tục |

Đừng ép tất cả logic tests phải seed triệu hàng. Ngược lại, đừng xem một H2 slice test đã chứng minh PostgreSQL production indexing và query plan.

## 4. Thiết kế dataset có hồ sơ định lượng trước khi viết code

Ta chọn một bảng `invoice_entries` với:

- `id`: primary key duy nhất, được tạo theo thứ tự 1...1.200.
- `tenant_id`: 900 hàng HOT và 300 hàng COLD.
- `entry_state`: HOT có 70% PAID; COLD có 20% PAID; còn lại OPEN.
- `created_at`: chỉ có 24 giá trị giờ khác nhau, nên rất nhiều ties.
- `customer_ref`: có NULL, chuỗi rỗng và nhiều giá trị trùng.
- `gross_cents`: các số tiền nhỏ thường gặp và một giá trị outlier 1.000.000 cents.

### 4.1. Hồ sơ đích

| Nhóm | Tổng | PAID | OPEN | NULL customer_ref |
|---|---:|---:|---:|---:|
| HOT | 900 | 630 | 270 | 45 |
| COLD | 300 | 60 | 240 | 15 |
| **Tổng** | **1.200** | **690** | **510** | **60** |

Tần suất:

- HOT chiếm 75% số hàng; COLD chiếm 25%.
- PAID chiếm 70% của HOT, nhưng chỉ 20% của COLD.
- NULL customer_ref xuất hiện ở mỗi hàng có `id % 20 == 0`, tương ứng 5% tổng dữ liệu.
- Chuỗi rỗng customer_ref có mặt ở các hàng chia hết cho 33 mà không chia hết cho 20; HOT có **26** hàng như vậy.
- Customer ref `CUST-7` xuất hiện **18** lần ở HOT; COLD có **5** lần vì một hàng vốn trùng chuyển sang chuỗi rỗng.
- Các thời điểm được tính bằng `2026-01-01 00:00:00` cộng `id % 24` giờ. Nên ở HOT, thời điểm 12:00 xuất hiện **38** lần, 13:00 xuất hiện **37** lần.
- Hóa đơn `id=900` thuộc HOT/PAID, có `gross_cents=1_000_000`, cao hơn rất nhiều so với mức bình thường `100 + id % 7`.

Những con số này là **oracle kiểm thử**: test phải assert chính xác chúng, thay vì tính “expected count” bằng chính câu SQL đang được kiểm tra.

### 4.2. Tại sao dùng công thức deterministic?

Dùng `Random()` không seed hoặc `Instant.now()` mỗi lần seed khiến test khó tái hiện, đặc biệt lỗi ở page boundary. Một công thức dựa trên ID:

```text
tenant(i) = HOT  nếu 1 <= i <= 900; ngược lại COLD
state(i)  = PAID nếu (HOT && i % 10 < 7)
                    hoặc (COLD && i % 10 < 2)
             OPEN trong những trường hợp còn lại
time(i)   = 2026-01-01T00:00 + (i % 24) giờ
amount(i) = 1_000_000 nếu i = 900; ngược lại 100 + (i % 7)
ref(i)    = NULL nếu i % 20 = 0
            "" nếu i % 33 = 0 và không NULL
            "CUST-" + (i % 50) trong những trường hợp khác
```

Khi build/CI fail ở id=957, developer biết chính xác nó thuộc COLD, thời điểm nào, ref nào, và có thể tái tạo nguyên bộ dữ liệu. Dataset deterministic còn giúp so sánh hai implementation của cùng query trên input giống nhau.

### 4.3. Khi nào dùng random có seed?

Random có seed vẫn hữu ích cho các shape phức tạp: lognormal/Zipfian distributions, xác suất nhiều chiều hoặc Monte Carlo. Nhưng phải:

1. Chọn seed cố định, được ghi trong test report.
2. Pin version của generator/algorithm để kết quả không trôi ngoài ý muốn.
3. Verify histogram/quantiles sau khi generate.
4. Có một số **edge fixtures trực tiếp** ngoài random để bảo đảm trường hợp hiếm luôn xuất hiện.
5. Tránh giả định Random.nextInt(...) đồng nghĩa workload production phân bố đúng.

Bài mẫu dùng công thức không random vì mục tiêu là tests chính xác và dễ giải thích.

## 5. Ví dụ Spring Boot 3.x/Java 17+ chạy được

Ví dụ có 4 file: Spring Boot application, JPA entity, repository và lớp JUnit test. Không cần HTTP server, Docker, Redis hoặc API ngoài. Dùng H2 để kiểm tra semantics JPA/SQL ở mức hợp lý.

**Version đích:** Java 17+, Spring Boot 3.x (ví dụ 3.5), Spring Data JPA, Hibernate 6, H2, JUnit Jupiter. Boot 3 sử dụng imports `jakarta.persistence.*`; đừng sao chép thẳng sang Boot 2 (thường `javax.persistence.*`) hoặc mặc định giữ nguyên test module packages khi lên Boot 4.

### 5.1. Dependencies

**Gradle Groovy DSL**, trong dự án đã có Boot Gradle plugin, dependency management, repositories và Java toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Maven**, trong project đã có Spring Boot parent/BOM và Maven Surefire/JDK 17 phù hợp:

```xml
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
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

**Đây là hai đoạn dependencies, không phải toàn bộ build files**. H2 phải nằm trên test runtime classpath, không được lôi production database connection vào demo.

### 5.2. Cấu trúc project

```text
src/
├── main/java/com/example/queryshape/
│   ├── QueryShapeApplication.java
│   ├── InvoiceEntry.java
│   └── InvoiceEntryRepository.java
└── test/java/com/example/queryshape/
    └── InvoiceQueryShapeTest.java
```

Test không tạo file CSV lớn riêng. `@BeforeEach` tạo dataset bằng `JdbcTemplate.batchUpdate(...)` trong test-managed transaction, giúp nạp 1.200 rows mà không buộc Hibernate tạo 1.200 managed entities.

### 5.3. Spring Boot application class

**File `src/main/java/com/example/queryshape/QueryShapeApplication.java`:**

```java
package com.example.queryshape;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QueryShapeApplication {
    public static void main(String[] args) {
        SpringApplication.run(QueryShapeApplication.class, args);
    }
}
```

Main class cùng package gốc với entity/repository; `@DataJpaTest` có thể tìm Spring Boot configuration và auto-configure JPA slice. Không cần explicit `@EntityScan` hoặc `@EnableJpaRepositories` cho sample package này.

### 5.4. Entity định nghĩa bảng, cột và hai index

**File `src/main/java/com/example/queryshape/InvoiceEntry.java`:**

```java
package com.example.queryshape;

import java.time.LocalDateTime;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

@Entity
@Table(
        name = "invoice_entries",
        indexes = {
            @Index(
                name = "idx_inv_tenant_state_time_id",
                columnList = "tenant_id,entry_state,created_at,id"
            ),
            @Index(
                name = "idx_inv_tenant_time_id",
                columnList = "tenant_id,created_at,id"
            )
        }
)
public class InvoiceEntry {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false, length = 20)
    private String tenantId;

    @Column(name = "entry_state", nullable = false, length = 20)
    private String entryState;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "gross_cents", nullable = false)
    private long grossCents;

    @Column(name = "customer_ref")
    private String customerRef;

    protected InvoiceEntry() {
        // Constructor required by JPA.
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getEntryState() {
        return entryState;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public long getGrossCents() {
        return grossCents;
    }

    public String getCustomerRef() {
        return customerRef;
    }
}
```

**Vì sao gán ID tường minh?** Test seed với ID từ 1 đến 1.200 nên mỗi run tái lập được cùng ordering. Nếu dùng `@GeneratedValue(IDENTITY)`, sequence/identity values có thể tăng giữa test contexts hoặc DB reset, làm khó tạo fixture tương ứng một ID cố định. Trong một ứng dụng thật, bạn có thể vẫn dùng auto-generated ID; test lúc đó cần một business key ổn định hoặc map ID sau insert.

**Vì sao dùng LocalDateTime?** Bài đang đo điều kiện thứ tự và khoảng thời gian theo *local timestamp* cố định. `LocalDateTime` **không có timezone**; sample không muốn làm phát sinh lỗi do UTC offsets trong phần test data shape. Với events thực sự là thời điểm toàn cầu, thường nên dùng `Instant`/`OffsetDateTime` và kiểm tra timezone/DB JDBC mapping riêng.

Hai index trong entity chỉ là ví dụ minh họa đường truy vấn khác nhau:

- `(tenant_id, entry_state, created_at, id)` phù hợp để nghiên cứu filter tenant/status + sort time/id.
- `(tenant_id, created_at, id)` phù hợp để nghiên cứu filter tenant + sort time/id (không có status).

Không khẳng định H2 và PostgreSQL sẽ chọn cùng index hoặc cùng plan. **Tạo index không tự chứng minh query nhanh.** Cần kế hoạch thực thi/latency trên workload tương ứng.

### 5.5. Repository với count, Page, Slice, seek và aggregate

**File `src/main/java/com/example/queryshape/InvoiceEntryRepository.java`:**

```java
package com.example.queryshape;

import java.time.LocalDateTime;
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InvoiceEntryRepository
        extends JpaRepository<InvoiceEntry, Long> {

    long countByTenantId(String tenantId);

    long countByTenantIdAndEntryState(
            String tenantId, String entryState);

    long countByTenantIdAndCustomerRefIsNull(String tenantId);

    long countByTenantIdAndCustomerRef(
            String tenantId, String customerRef);

    long countByTenantIdAndCreatedAtGreaterThanEqualAndCreatedAtLessThan(
            String tenantId,
            LocalDateTime fromInclusive,
            LocalDateTime toExclusive);

    Page<InvoiceEntry> findByTenantId(
            String tenantId, Pageable pageable);

    Page<InvoiceEntry> findByTenantIdAndEntryState(
            String tenantId, String entryState, Pageable pageable);

    Slice<InvoiceEntry> findSliceByTenantIdAndEntryState(
            String tenantId, String entryState, Pageable pageable);

    List<InvoiceEntry>
    findTop10ByTenantIdAndEntryStateOrderByCreatedAtDescIdDesc(
            String tenantId, String entryState);

    @Query("""
            select sum(e.grossCents)
            from InvoiceEntry e
            where e.tenantId = :tenant
              and e.entryState = :state
            """)
    Long sumGrossCents(
            @Param("tenant") String tenantId,
            @Param("state") String entryState);

    @Query("""
            select e
            from InvoiceEntry e
            where e.tenantId = :tenant
              and (
                    e.createdAt > :cursorTime
                    or (e.createdAt = :cursorTime and e.id > :cursorId)
              )
            order by e.createdAt asc, e.id asc
            """)
    List<InvoiceEntry> seekAfter(
            @Param("tenant") String tenantId,
            @Param("cursorTime") LocalDateTime cursorTime,
            @Param("cursorId") Long cursorId,
            Pageable pageable);
}
```

Lưu ý:

1. `countBy...` trả `long` vì số hàng có thể vượt `int`.
2. Method thời gian dùng `GreaterThanEqual` và `LessThan`, thể hiện rõ **[from, to)** (bao gồm đầu, loại trừ cuối).
3. `Page<T>` mang thông tin `totalElements`/`totalPages`; tùy tình huống Spring Data JPA cần thêm count query.
4. `Slice<T>` chỉ cần biết có trang tiếp theo không, tránh nhu cầu biết tổng số rows cho một số use cases.
5. `findTop10...OrderByCreatedAtDescIdDesc` dùng id tie-breaker cho timestamp trùng.
6. JPQL `sum` trả `Long` theo mapping trường số nguyên dài; khi **không có row** thỏa, aggregate SQL/JPA `SUM` thường trả `null`, không mặc định 0.
7. `seekAfter` là một **query keyset thủ công**: truyền cặp key cuối `(createdAt,id)` và yêu cầu 40 records tiếp theo. Nó **không phải** toàn bộ Spring Data Scroll API và không tự cung cấp consistency snapshot qua các transaction khác nhau.
8. `Pageable` cho `seekAfter` được dùng để giới hạn số rows; trong test gọi `PageRequest.of(0,40)` không thêm sort động, vì JPQL đã có `ORDER BY`.

## 6. Lớp JUnit tạo dataset và kiểm thử nhiều tình huống

**File `src/test/java/com/example/queryshape/InvoiceQueryShapeTest.java`:**

```java
package com.example.queryshape;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.sql.Types;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.LongStream;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(
        showSql = false,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
class InvoiceQueryShapeTest {

    private static final int TOTAL = 1_200;
    private static final LocalDateTime BASE =
            LocalDateTime.of(2026, 1, 1, 0, 0);

    private static final Comparator<InvoiceEntry> STABLE_ASC =
            Comparator.comparing(InvoiceEntry::getCreatedAt)
                    .thenComparing(InvoiceEntry::getId);

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    EntityManager entityManager;

    @Autowired
    InvoiceEntryRepository repository;

    private static String tenant(int id) {
        return id <= 900 ? "HOT" : "COLD";
    }

    private static String state(int id) {
        boolean paid = id <= 900
                ? (id % 10 < 7)
                : (id % 10 < 2);
        return paid ? "PAID" : "OPEN";
    }

    private static LocalDateTime createdAt(int id) {
        return BASE.plusHours(id % 24);
    }

    private static long grossCents(int id) {
        return id == 900 ? 1_000_000L : 100L + (id % 7);
    }

    private static String customerRef(int id) {
        if (id % 20 == 0) {
            return null;
        }
        if (id % 33 == 0) {
            return "";
        }
        return "CUST-" + (id % 50);
    }

    private static Sort stableSort() {
        return Sort.by(
                Sort.Order.asc("createdAt"),
                Sort.Order.asc("id"));
    }

    @BeforeEach
    void seedDeterministicFixtureInTestTransaction() {
        jdbc.batchUpdate(
                """
                insert into invoice_entries (
                    id, tenant_id, entry_state,
                    created_at, gross_cents, customer_ref
                ) values (?, ?, ?, ?, ?, ?)
                """,
                new BatchPreparedStatementSetter() {

                    @Override
                    public void setValues(
                            PreparedStatement ps, int row)
                            throws SQLException {

                        int id = row + 1;

                        ps.setLong(1, id);
                        ps.setString(2, tenant(id));
                        ps.setString(3, state(id));
                        ps.setTimestamp(4,
                                Timestamp.valueOf(createdAt(id)));
                        ps.setLong(5, grossCents(id));

                        String ref = customerRef(id);
                        if (ref == null) {
                            ps.setNull(6, Types.VARCHAR);
                        }
                        else {
                            ps.setString(6, ref);
                        }
                    }

                    @Override
                    public int getBatchSize() {
                        return TOTAL;
                    }
                });

        // Seed qua JDBC; không giữ managed entities từ fixture.
        entityManager.clear();
    }

    @Test
    void profileHasExpectedVolumeAndStatusSkew() {
        assertThat(repository.count()).isEqualTo(1_200L);

        assertThat(repository.countByTenantId("HOT"))
                .isEqualTo(900L);
        assertThat(repository.countByTenantId("COLD"))
                .isEqualTo(300L);

        assertThat(repository.countByTenantIdAndEntryState(
                "HOT", "PAID")).isEqualTo(630L);
        assertThat(repository.countByTenantIdAndEntryState(
                "HOT", "OPEN")).isEqualTo(270L);

        assertThat(repository.countByTenantIdAndEntryState(
                "COLD", "PAID")).isEqualTo(60L);
        assertThat(repository.countByTenantIdAndEntryState(
                "COLD", "OPEN")).isEqualTo(240L);
    }

    @Test
    void filterSelectivityDiffersByTenant() {
        long hotPaid = repository.countByTenantIdAndEntryState(
                "HOT", "PAID");
        long coldPaid = repository.countByTenantIdAndEntryState(
                "COLD", "PAID");

        assertThat(hotPaid).isEqualTo(630L);
        assertThat(coldPaid).isEqualTo(60L);

        // 70% của tenant HOT, 20% của tenant COLD.
        assertThat(hotPaid * 100 / 900).isEqualTo(70L);
        assertThat(coldPaid * 100 / 300).isEqualTo(20L);
    }

    @Test
    void nullEmptyAndRepeatedRefsAreDifferent() {
        assertThat(repository.countByTenantIdAndCustomerRefIsNull(
                "HOT")).isEqualTo(45L);

        assertThat(repository.countByTenantIdAndCustomerRefIsNull(
                "COLD")).isEqualTo(15L);

        // Mỗi 33rd id có ref rỗng, trừ các id có ref NULL.
        assertThat(repository.countByTenantIdAndCustomerRef(
                "HOT", "")).isEqualTo(26L);

        // Một customer có nhiều hóa đơn; không được giả định unique.
        assertThat(repository.countByTenantIdAndCustomerRef(
                "HOT", "CUST-7")).isEqualTo(18L);
        assertThat(repository.countByTenantIdAndCustomerRef(
                "COLD", "CUST-7")).isEqualTo(5L);
    }

    @Test
    void halfOpenTimeRangeIncludesStartAndExcludesEnd() {
        LocalDateTime noon = BASE.plusHours(12);
        LocalDateTime onePm = BASE.plusHours(13);
        LocalDateTime twoPm = BASE.plusHours(14);

        // Id=12,36,...,900 -> 38 HOT rows tại 12:00.
        assertThat(
                repository
                        .countByTenantIdAndCreatedAtGreaterThanEqualAndCreatedAtLessThan(
                                "HOT", noon, onePm))
                .isEqualTo(38L);

        // 13:00 thuộc khoảng kế tiếp, không thuộc khoảng trước.
        assertThat(
                repository
                        .countByTenantIdAndCreatedAtGreaterThanEqualAndCreatedAtLessThan(
                                "HOT", onePm, twoPm))
                .isEqualTo(37L);
    }

    @Test
    void stablePagingWithTiesDoesNotDuplicateRows() {
        Page<InvoiceEntry> first =
                repository.findByTenantIdAndEntryState(
                        "HOT", "PAID",
                        PageRequest.of(0, 40, stableSort()));

        Page<InvoiceEntry> second =
                repository.findByTenantIdAndEntryState(
                        "HOT", "PAID",
                        PageRequest.of(1, 40, stableSort()));

        assertThat(first.getTotalElements()).isEqualTo(630L);
        assertThat(first.getTotalPages()).isEqualTo(16);
        assertThat(first.getContent()).hasSize(40);
        assertThat(second.getContent()).hasSize(40);

        List<InvoiceEntry> combined = new ArrayList<>(
                first.getContent());
        combined.addAll(second.getContent());

        for (int i = 1; i < combined.size(); i++) {
            assertThat(STABLE_ASC.compare(
                    combined.get(i - 1), combined.get(i)))
                    .isLessThan(0);
        }

        Set<Long> ids = new HashSet<>();
        for (InvoiceEntry row : combined) {
            assertThat(row.getTenantId()).isEqualTo("HOT");
            assertThat(row.getEntryState()).isEqualTo("PAID");
            assertThat(ids.add(row.getId())).isTrue();
        }
        assertThat(ids).hasSize(80);
    }

    @Test
    void lastPageHasOnlyRemainingRows() {
        Page<InvoiceEntry> last =
                repository.findByTenantIdAndEntryState(
                        "HOT", "PAID",
                        PageRequest.of(15, 40, stableSort()));

        assertThat(last.getTotalElements()).isEqualTo(630L);
        assertThat(last.getContent()).hasSize(30);
        assertThat(last.isLast()).isTrue();
        assertThat(last.hasNext()).isFalse();
    }

    @Test
    void sliceHasNextWithoutRequiringTotalCount() {
        Slice<InvoiceEntry> first =
                repository.findSliceByTenantIdAndEntryState(
                        "HOT", "PAID",
                        PageRequest.of(0, 40, stableSort()));

        Slice<InvoiceEntry> last =
                repository.findSliceByTenantIdAndEntryState(
                        "HOT", "PAID",
                        PageRequest.of(15, 40, stableSort()));

        assertThat(first.getContent()).hasSize(40);
        assertThat(first.hasNext()).isTrue();
        assertThat(last.getContent()).hasSize(30);
        assertThat(last.hasNext()).isFalse();
    }

    @Test
    void seekPaginationMatchesOffsetOnUnchangedFixture() {
        Page<InvoiceEntry> first =
                repository.findByTenantId(
                        "HOT", PageRequest.of(
                                0, 40, stableSort()));

        InvoiceEntry cursor = first.getContent().get(39);

        List<InvoiceEntry> after =
                repository.seekAfter(
                        "HOT", cursor.getCreatedAt(),
                        cursor.getId(), PageRequest.of(0, 40));

        Page<InvoiceEntry> offsetSecond =
                repository.findByTenantId(
                        "HOT", PageRequest.of(
                                1, 40, stableSort()));

        assertThat(after).hasSize(40);
        assertThat(after.stream()
                .map(InvoiceEntry::getId).toList())
                .isEqualTo(offsetSecond.getContent().stream()
                        .map(InvoiceEntry::getId).toList());
    }

    @Test
    void aggregateIncludesLargeOutlierWithoutIntOverflow() {
        long expected = LongStream.rangeClosed(1, 900)
                .filter(i -> i % 10 < 7)
                .map(i -> grossCents((int) i))
                .sum();

        assertThat(repository.sumGrossCents("HOT", "PAID"))
                .isEqualTo(expected);
        assertThat(expected).isGreaterThan(1_000_000L);

        // SUM không có hàng khớp thường trả NULL, không phải 0.
        assertThat(repository.sumGrossCents("MISSING", "PAID"))
                .isNull();
    }

    @Test
    void topTenHasDeterministicTieBreaker() {
        List<InvoiceEntry> top =
                repository
                        .findTop10ByTenantIdAndEntryStateOrderByCreatedAtDescIdDesc(
                                "HOT", "PAID");

        assertThat(top).hasSize(10);
        assertThat(top.get(0).getCreatedAt())
                .isEqualTo(BASE.plusHours(23));

        for (int i = 1; i < top.size(); i++) {
            assertThat(STABLE_ASC.compare(
                    top.get(i - 1), top.get(i)))
                    .isGreaterThan(0);
        }
    }

    @Test
    void emptyTenantProducesEmptyPageAndZeroCount() {
        Page<InvoiceEntry> page =
                repository.findByTenantId(
                        "NOT-PRESENT", PageRequest.of(
                                0, 40, stableSort()));

        assertThat(repository.countByTenantId("NOT-PRESENT"))
                .isZero();
        assertThat(page.getContent()).isEmpty();
        assertThat(page.getTotalElements()).isZero();
        assertThat(page.getTotalPages()).isZero();
    }
}
```

### 6.1. Kỳ vọng của mã mẫu

Lớp có **11 phương thức `@Test`**, nhằm kiểm tra:

| Test | Dataset feature được sử dụng | Assertion quan trọng |
|---|---|---|
| `profileHasExpectedVolumeAndStatusSkew` | 1.200 rows; 900/300; status imbalance | Chính xác sáu counts |
| `filterSelectivityDiffersByTenant` | Tương quan tenant/status | 70% và 20% |
| `nullEmptyAndRepeatedRefsAreDifferent` | NULL/empty/duplicates | 45, 15, 26, 18, 5 |
| `halfOpenTimeRangeIncludesStartAndExcludesEnd` | 24 giờ, rất nhiều ties | 12:00 có 38, 13:00 có 37 |
| `stablePagingWithTiesDoesNotDuplicateRows` | 630 PAID HOT, timestamp ties | 80 rows, không overlap, sort (time,id) |
| `lastPageHasOnlyRemainingRows` | 630 chia page size 40 | Page cuối có 30 |
| `sliceHasNextWithoutRequiringTotalCount` | Same filter + page size | First hasNext, last không |
| `seekPaginationMatchesOffsetOnUnchangedFixture` | Keyset với cursor (time,id) | 40 IDs bằng offset page thứ hai |
| `aggregateIncludesLargeOutlierWithoutIntOverflow` | Giá trị 1.000.000 cents | Tổng đúng theo fixture oracle |
| `topTenHasDeterministicTieBreaker` | Timestamp trùng, sort DESC | 10 rows theo time/id |
| `emptyTenantProducesEmptyPageAndZeroCount` | Không có hàng khớp | Empty page, total=0 |

**Điều kiện áp dụng:** đúng Spring Boot 3.x + H2 + Hibernate và không có custom converters/entities, schema migrations hay test auto-configuration khác can thiệp. Nội dung này là mã mẫu được rà soát tĩnh; để xác nhận môi trường cụ thể, hãy thực sự chạy lệnh build/test ở phần sau. Không tuyên bố đã đo p95 hoặc chạy benchmark production từ ví dụ H2 này.

### 6.2. Chạy test bằng Gradle hoặc Maven

Linux/macOS, chọn đúng build tool của project:

```bash
# Gradle Wrapper
./gradlew test --tests "com.example.queryshape.InvoiceQueryShapeTest"

# Hoặc Maven Wrapper
./mvnw -Dtest=InvoiceQueryShapeTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.queryshape.InvoiceQueryShapeTest"

# Hoặc nếu dự án dùng Maven:
.\mvnw.cmd "-Dtest=InvoiceQueryShapeTest" test
```

Với module nhiều source sets, chọn đúng module chứa lớp test. Nếu không có Wrapper, tạo wrapper theo quy trình build của dự án hoặc dùng Maven/Gradle đã được version-pin trong CI. Đọc JUnit report để xác nhận **11 tests đã thực thi**, không chỉ nhìn màu xanh của build có thể bị task up-to-date/skipped.

### 6.3. Vì sao dùng JDBC để seed JPA test?

Dùng `repository.saveAll(...)` rồi truy vấn ngay có thể để lại nhiều entity **managed** trong persistence context; kết quả `findById(...)` hoặc query có thể bị ảnh hưởng bởi first-level cache, JPA dirty checking và flush timing.

Ví dụ dùng `JdbcTemplate.batchUpdate` để:

1. Tạo 1.200 rows có kiểm soát qua SQL.
2. Không giữ 1.200 managed entity trong `EntityManager`.
3. Seed nhanh hơn vòng lặp `saveAndFlush` từng entity.
4. Chủ động kiểm chứng SQL database row bằng JPA repository sau đó.
5. Tận dụng `@DataJpaTest` mặc định transaction + rollback sau mỗi test, tránh dữ liệu rò giữa methods.

**Lưu ý:** JDBC seed chạy trong test transaction khi dùng cùng DataSource/transaction manager ở Spring Boot JPA slice thông thường. `entityManager.clear()` chỉ làm sạch persistence context, không commit JDBC transaction. Nếu project cấu hình nhiều DataSources/managers, cần xác nhận JDBC seed và JPA queries dùng cùng database.

### 6.4. Vì sao seed trước từng test, không seed một lần duy nhất?

Mỗi test phải độc lập và chạy được khi chọn riêng bằng IDE:

- `@BeforeEach` tạo fixture trong **test-managed transaction**.
- Mỗi test assert một hợp đồng.
- Spring TestContext rollback sau method, xóa toàn bộ INSERT của method đó.
- Test sau seed lại từ cùng công thức, không phụ thuộc ID/số hàng từ test trước.

Với vài trăm nghìn rows, seed lại toàn bộ cho mỗi test có thể quá chậm. Lúc đó nên:

- Tách các mức test (nhỏ/hình dạng vs cỡ production).
- Dùng isolated schema/database, snapshot/restore hoặc Testcontainers template có kiểm soát.
- Seed một lần cho **read-only performance suite** mà từng test không mutate, nhưng phải quản lý lifecycle/cleanup và parallel isolation.
- Không dùng @TestMethodOrder để “tối ưu” bằng cách test A tạo data, test B hưởng data và test C xóa.

### 6.5. SQL aggregate dùng long, không dùng int một cách tùy tiện

Một báo cáo doanh thu tính `sum(gross_cents)` có thể vượt giới hạn của Java `int` nếu rows nhiều hoặc có outliers. Trong code, entity field `grossCents` là `long`, repository trả `Long`, và oracle dùng `LongStream.sum()`.

Dù vậy, **long không đủ cho mọi dạng tiền**. Nếu domain cần số lẻ thập phân, nhiều currency hoặc giá trị cực lớn, dùng `BigDecimal` và xác định rounding/scale/currency rõ. Test tổng trên 1.200 rows giúp bắt một số bugs, nhưng overflow có thể chỉ xuất hiện khi lớn hơn vài tỷ; cần edge case riêng gần numeric limits nếu yêu cầu.

### 6.6. Không so sánh timestamp theo kiểu đoán timezone

Fixture dùng `LocalDateTime`. Nếu ứng dụng lưu timestamps với UTC/offset, hãy xác định:

- DB column type `TIMESTAMP [WITH TIME ZONE]` hoặc tương đương.
- Java type `Instant`, `OffsetDateTime`, `LocalDateTime`.
- JDBC driver/session timezone, DST và precision.
- Query interval lấy theo timezone nào; quy tắc [from,to) sau chuyển đổi.
- Client input có offset hay local time.

Chẳng hạn tháng có DST không luôn dài 30×24 giờ ở timezone đang xét. Test thời gian business nên được xây từ **Instant boundaries theo zone policy** rồi áp vào query, không cộng số giờ tùy tiện cho một monthly report.

## 7. Những dữ liệu biên cần thêm tùy loại truy vấn

Ví dụ 1.200 rows minh họa nhiều chiều nhưng **không thay thế toàn bộ edge cases** của hệ thống thật.

### 7.1. Số lượng: 0, 1, N = page size, N = page size + 1

Với page size 40, nên có thêm query scenario:

| Số kết quả | Cần assert |
|---|---|
| 0 | Empty body/content, total count 0, không có phantom next page |
| 1 | Một row, không có next |
| 39 | Một trang chưa đầy |
| 40 | Một trang vừa đủ, không có trang tiếp theo |
| 41 | Hai trang, trang sau 1 row |
| 80 | Hai trang vừa đủ, trang ba rỗng |
| 630 | Page cuối 30 rows, totalPages = 16 |

Một query có thể đúng ở 39 nhưng sai ở 40/41 do off-by-one trong limit/offset. Nếu API trả `Slice`, cần kiểm tra `hasNext`; nếu trả `Page`, cần thêm total count semantics. Không phải mọi query phải có mọi case; chọn những trường hợp boundary liên quan hợp đồng.

### 7.2. String semantics: null, empty, whitespace, case và Unicode

Trong SQL:

- `customer_ref IS NULL` không giống `customer_ref = ''`.
- `NULL = NULL` không hoạt động như equality bình thường; cần `IS NULL`.
- `"CUST-7"` với `"cust-7"` có thể khác nhau theo collation/case rules.
- `"A"` với `"A "` có thể khác nhau theo column type/collation/database.
- Unicode composed/decomposed characters có thể cần normalization policy.
- Long VARCHAR/TEXT fields có thể ảnh hưởng row width và index storage.

Dataset mẫu có null/empty/duplicate refs; nếu query cần normalize customer names hoặc tìm kiếm quốc tế, tạo fixture tiếng Việt có dấu, kết hợp ký tự và mixed case, rồi kiểm tra trên **collation của RDBMS thực**. H2 không đại diện mọi Unicode collation behavior của PostgreSQL/MySQL.

### 7.3. JSON, XML và trường dữ liệu lớn

Một bảng có JSONB/TEXT vài KB đến MB trên mỗi row tạo I/O/memory pressure khác bảng chỉ chứa số nguyên và mã ngắn. Performance suite nên phân bố:

- Small payload phổ biến.
- p95/p99 payload sizes.
- Một số outliers rất dài.
- Những trường chứa null hoặc thiếu key.
- JSON shapes khác nhau nếu query lọc JSON paths.
- Tỷ lệ compressed/uncompressed, index/TOAST/page storage của DB thực.

Không chỉ tăng 1.200 rows thành một triệu rows có cấu trúc rất hẹp rồi cho rằng đã mô phỏng production có nhiều TEXT/BLOB.

### 7.4. Join fan-out và N+1

Truy vấn có JOIN giữa `orders` và `order_lines` cần dataset với:

- Một order không có line.
- Một order có đúng một line.
- Một order có vài lines.
- Một “whale” order có hàng trăm hoặc hàng nghìn lines.
- Các line trùng product/variant nhưng khác sequence.
- Orphan/cascade/soft-delete scenarios khi domain cho phép.

Nếu mọi order đều có đúng một line, JOIN có thể trông giống quan hệ một-một; test không phát hiện nhân bản rows hoặc pagination count sai khi fetch collection.

N+1 xảy ra khi code truy vấn N parents rồi lazy load children từng parent, tạo nhiều SQL selects. Một test chỉ fetch 2 parents khó phản ánh chi phí; với 100 parents và fan-out có skew, statistics/logs có thể lộ rõ. Nhưng **đừng đếm số câu SQL bằng một assertion cứng** nếu test không kiểm soát caches, fetch strategy, batch size và lazy initialization.

### 7.5. Soft delete, active/inactive và dữ liệu lịch sử

Nếu entity có `deletedAt`, `archived`, `validFrom`/`validTo` hoặc status workflow, dataset phải có trạng thái chuyển tiếp:

- active vs soft-deleted;
- expired nhưng chưa xóa;
- validFrom == query boundary;
- validTo == query boundary;
- record có status không còn được dùng nhưng vẫn nằm trong DB;
- mỗi tenant có chính sách archival khác nhau.

Một sample chỉ gồm bản ghi active sẽ không phát hiện filter quên loại soft-deleted data.

### 7.6. Dữ liệu mang ý nghĩa bảo mật

Với multi-tenant queries, **tenant isolation là correctness và security contract**. Chỉ assert COUNT có thể chưa đủ nếu query trộn rows của tenant khác nhưng tổng số trùng tình cờ. Với các test cần cao hơn, assert **mọi kết quả đều có tenantId đúng**, và kết hợp tests ở Spring Security/row-level security/database layer tương ứng.

Tránh sao chép dữ liệu khách hàng production vào test. Dùng synthetic data dựa trên aggregate distributions, hoặc dữ liệu đã được quản lý/anonymize theo chính sách bảo mật, không hardcode email/địa chỉ/token thật.

## 8. Page, Slice, offset và keyset: dữ liệu hình dạng nào làm lộ bug?

### 8.1. Page có count semantics

Với:

```java
Page<InvoiceEntry> page =
        repository.findByTenantIdAndEntryState(
                "HOT", "PAID",
                PageRequest.of(15, 40, stableSort()));
```

Đây là snippet trong test class ở phần 6. Vì HOT/PAID có 630 rows, page size 40, page 15 (zero-based) phải có 30. Spring Data JPA `Page` cung cấp `totalElements=630` và `totalPages=16` trong trường hợp query như sample.

Một custom query có JOIN/GROUP BY/native SQL phức tạp có thể cần `countQuery` riêng, để total đúng theo business result cardinality chứ không chỉ số hàng join thô. Không mặc định count query được suy diễn đúng cho mọi native SQL phức tạp.

### 8.2. Slice phù hợp khi không cần total count

`Slice<T>` tập trung vào có trang sau hay không. Nó thường chỉ cần dữ liệu đủ để xác định `hasNext`, tránh chi phí total count trong những use cases chỉ bấm “Next”.

Nhưng đổi Page sang Slice không sửa mọi performance issue. Query dữ liệu vẫn có thể scan/order nhiều rows; offset lớn vẫn tốn chi phí, đặc biệt khi có sort không được index hỗ trợ.

### 8.3. Stable sort bắt buộc khi có ties

Nếu query chỉ:

```sql
ORDER BY created_at ASC
```

và hàng trăm rows có created_at bằng nhau, thứ tự nội bộ của những rows đó **không được bảo đảm**. Kết hợp:

```sql
ORDER BY created_at ASC, id ASC
```

tạo một **total ordering** khi id unique. Điều này giúp các page requests trả kết quả lặp lại trên **dataset không đổi**.

Trong repository sample, `stableSort()` dùng `createdAt` và `id`. Với query top10 DESC, method name bao gồm `OrderByCreatedAtDescIdDesc`.

**Không đánh đồng total order với snapshot isolation.** Nếu có INSERT/DELETE giữa hai page requests, offset pagination vẫn có thể bỏ sót/lặp rows do rows dịch vị trí. Stable tie-breaker giải quyết nondeterminism của các rows bằng nhau, không khóa dataset qua nhiều requests.

### 8.4. Offset pagination và deep pages

`PageRequest.of(100_000, 40)` không phải lúc nào cũng là cách truy vấn hiệu quả. Database có thể cần duyệt/sắp xếp nhiều rows trước khi bỏ qua offset, dù chỉ trả 40 rows.

Đối với các API cuộn rất sâu, keyset/seek pagination thường là một lựa chọn. Hình thức logic:

```sql
SELECT id, created_at
FROM invoice_entries
WHERE tenant_id = ?
  AND (
       created_at > ?
       OR (created_at = ? AND id > ?)
  )
ORDER BY created_at ASC, id ASC
LIMIT 40;
```

Đây là SQL khái niệm có placeholders cho query cursor, không phải method JDBC runnable độc lập. Với index hỗ trợ filter/order, database có thể tận dụng seek hiệu quả hơn offset lớn. Nhưng biểu thức OR, collation, nullable key và DB engine ảnh hưởng optimizer; cần xem plan trên production DB.

Keyset cursor phải chứa **đủ khóa sort duy nhất**. Cursor chỉ chứa `createdAt` sẽ bỏ qua những rows còn lại có cùng timestamp ở page boundary. Test mẫu phần 6 dùng cặp `(createdAt,id)`.

### 8.5. Dataset tĩnh không chứng minh concurrency behavior

Test `seekPaginationMatchesOffsetOnUnchangedFixture` chứng minh hai phương pháp trả cùng IDs khi không có writes chen vào. Nó **không chứng minh** cách API xử lý INSERT/DELETE giữa hai HTTP requests.

Nếu cursor feed là chức năng sản phẩm quan trọng, thiết kế thêm integration test với:

- Hai transaction/connection khác nhau.
- INSERT/DELETE ở điểm xác định giữa page 1 và page 2.
- Isolation level và snapshot semantics cụ thể.
- Quy tắc business: “đọc snapshot cố định”, “feed mới nhất”, hay “không được lặp”?
- Predicate cursor nhất quán với ordering và index.
- Kiểm tra records có sort key NULL.

Không dùng sleep ngẫu nhiên để tái hiện race; điều phối bằng latch/barrier và controlled transactions.

## 9. Query plans và statistics: tại sao cùng SQL chọn kế hoạch khác nhau?

### 9.1. EXPLAIN không phải câu trả lời “index luôn tốt”

Các database chọn execution plan dựa trên:

- cardinality estimates, histograms, most-common values;
- số pages/index pages và độ rộng hàng;
- tình trạng index và thứ tự cột của composite index;
- selectivity kết hợp nhiều predicates;
- index scan vs sequential/table scan;
- sort/aggregate cost;
- join ordering, join algorithms, fan-out;
- LIMIT/OFFSET và row count estimates;
- table statistics có mới hay không.

Một index tốt cho `tenant_id='COLD' AND entry_state='PAID'` (60/1.200 rows) có thể không hiệu quả bằng table scan đối với một filter rất phổ biến trên bảng nhỏ, và điều này **không nhất thiết là bug**.

### 9.2. EXPLAIN trong H2

H2 hỗ trợ `EXPLAIN` và `EXPLAIN ANALYZE`. Có thể khám phá:

```sql
EXPLAIN
SELECT id, created_at
FROM invoice_entries
WHERE tenant_id = 'HOT'
  AND entry_state = 'PAID'
ORDER BY created_at ASC, id ASC;
```

Đây là query chẩn đoán chạy được trong H2 nếu schema/table có mặt. `EXPLAIN` trình bày kế hoạch thực thi; **`EXPLAIN ANALYZE` thực thi query thật** và báo thông tin scan thực tế theo khả năng của H2. Không chạy EXPLAIN ANALYZE với UPDATE/DELETE trên production mà thiếu kiểm soát transaction vì chúng có side effects.

Đoạn code chẩn đoán nếu cần trong @DataJpaTest:

```java
String plan = jdbc.queryForObject(
        """
        EXPLAIN SELECT id
        FROM invoice_entries
        WHERE tenant_id = ? AND entry_state = ?
        ORDER BY created_at, id
        """,
        String.class,
        "HOT", "PAID");

assertThat(plan).isNotBlank();
```

Đây là **snippet trong test context** đã có `jdbc` và AssertJ, không phải file độc lập. Ta cố ý chỉ assert có plan, **không hardcode** chuỗi tên index/H2 planner output, bởi planner và cost estimates có thể thay đổi theo version mà query logic vẫn đúng.

### 9.3. PostgreSQL EXPLAIN ANALYZE và row estimates

Trên PostgreSQL, các lệnh như sau có thể giúp phân tích:

```sql
ANALYZE invoice_entries;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at
FROM invoice_entries
WHERE tenant_id = 'COLD'
  AND entry_state = 'PAID'
ORDER BY created_at, id
LIMIT 40;
```

**Dùng trong môi trường kiểm thử**, không mặc định chạy trên production không có kiểm soát. Trong PostgreSQL, `EXPLAIN (ANALYZE)` thực thi câu query; với SELECT như ví dụ là đọc, nhưng có thể tiêu tốn tài nguyên/khóa và ảnh hưởng hệ thống dưới tải.

Xem:

- **Estimated rows vs actual rows:** planner đánh giá selectivity có đúng không.
- **Loops:** nested-loop join có lặp quá nhiều không.
- **Sort:** có sort ngoài index hoặc spill disk không.
- **Buffers:** dữ liệu đọc từ shared buffers/disk ở mức nào.
- **Planning time vs execution time:** đang chậm ở lập kế hoạch hay thực thi.
- **Index Cond vs Filter:** điều kiện nào được đẩy xuống index, điều kiện nào lọc sau.
- **Temp files/work_mem:** có sorting/hash spilling không.

Khi dataset quá nhỏ hoặc phân bố không giống production, output EXPLAIN có thể **không đại diện** cho production plan. Query “dùng index” trên 1.200 rows cũng không chứng minh nó có latency tốt ở 100 triệu rows.

### 9.4. Multivariate statistics cho dữ liệu tương quan

PostgreSQL hỗ trợ extended statistics, ví dụ:

```sql
CREATE STATISTICS invoice_tenant_state_stats
    (dependencies, mcv)
    ON tenant_id, entry_state
    FROM invoice_entries;

ANALYZE invoice_entries;
```

Đây là ví dụ DDL **chỉ nên áp dụng ở môi trường phù hợp**, và cần kiểm tra quyền, DB version, nhu cầu thật. Extended statistics có thể cải thiện estimates cho các điều kiện tương quan. Nhưng chúng không bảo đảm mọi query bỗng nhanh; có chi phí thu thập stats và planner vẫn chịu nhiều yếu tố khác.

Trong tests correctness của bài, không cần tạo PostgreSQL statistics vì chúng chạy trên H2. Trong performance job, chọn DB engine thật và phân bố dữ liệu đúng rồi mới kiểm tra có cần stats nâng cao hay không.

### 9.5. Kiểm tra index phải dựa vào query shape

Index `(tenant_id,entry_state,created_at,id)` phù hợp cho query filter equality theo tenant/status và sắp xếp time/id. Nhưng một query chỉ có `tenant_id` và sắp `created_at,id` có thể cần index khác. Query đếm theo `customer_ref` có thể cần index tenant/ref nếu là use case thường xuyên và lớn.

**Không tạo index cho mọi cột** chỉ để test xanh: index tăng chi phí ghi, lưu trữ và bảo trì. Dùng workload, query plans và domain yêu cầu để chọn; sau đó test query correctness và performance riêng.

## 10. Tạo dataset production-like mà không sao chép dữ liệu nhạy cảm

### 10.1. Ba chiến lược

**Fixture được viết tay:** tốt cho edge cases và logic, nhưng dễ quá nhỏ/đều.

**Generator deterministic:** tốt cho medium dataset có histogram/relationships, dễ tái lập; phải định nghĩa phân bố và xác minh thống kê.

**Synthetic data dựa trên profile production:** tốt cho performance job. Chỉ sử dụng số liệu aggregate/anonymized được phép, không sao chép PII/secrets. Những quan hệ đặc biệt cần bảo tồn dạng thống kê, không giữ định danh thật.

### 10.2. Phân bố cần mô hình hóa cẩn thận

Với dữ liệu skew cao, có thể dùng:

- Log-normal cho transaction amount/sizes.
- Zipf/Pareto cho tenant popularity, hot products.
- Mixture distributions cho nhiều nhóm người dùng.
- Piecewise distributions cho status theo tenant/region.
- Burst timestamps cho peak-hours.
- Correlated variables cho status và account age hoặc category.

Chỉ chọn công thức xác suất vì nó tiện **không bảo đảm** tính thực tế. Hãy so histogram, percentiles, distinct counts, null rate, rows per tenant, fan-out per parent và các conditional distributions với số liệu đã được phép sử dụng.

### 10.3. Lập “data profile contract”

Một ví dụ mô tả cho performance job:

```yaml
dataset:
  version: query-shape-v3
  generator_seed: 20261108
  total_rows: 1000000
  partitions:
    tenants: 400
    largest_tenant_share: 0.35
  status:
    paid_share_given_hot_tenant: 0.70
    paid_share_given_cold_tenant: 0.20
  customer_ref:
    null_share: 0.05
    duplicates_allowed: true
  timestamps:
    distribution: bursty
    duplicate_sort_keys: true
  amounts:
    heavy_tail: true
  workload:
    page_size: 40
    query_mix:
      hot_tenant_paid: 0.50
      cold_tenant_paid: 0.15
      tenant_time_seek: 0.35
```

Đây là **ví dụ thiết kế metadata**, không phải file YAML được application ở phần 5 thực thi. Các tỷ lệ mang tính minh họa; cần thay bằng hồ sơ thực tế và yêu cầu sản phẩm. “Một triệu rows” chỉ là một mức thử, không phải chuẩn cho mọi app.

## 11. Query test, SQL logging và chi phí thu thập bằng chứng

### 11.1. Ghi nhận SQL khi kiểm thử logic

Với Spring Boot 3/Hibernate 6, có thể dùng test properties:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Các category này phụ thuộc phiên bản Hibernate/Boot; `@DataJpaTest(showSql=false)` trong sample cố ý tắt show-sql để tránh hàng nghìn câu log INSERT. Bật logging chỉ trong một test chẩn đoán hay profile có kiểm soát.

**Không bật TRACE bind parameters trên production data** vì log có thể chứa PII, token, tài khoản và dữ liệu nhạy cảm.

### 11.2. Đếm SQL statements để tìm N+1

Hibernate có thống kê (statistics) và logs có thể hỗ trợ đo query count. Nhưng một assertion kiểu:

```java
assertThat(hibernateStatistics.getPrepareStatementCount())
        .isLessThanOrEqualTo(3L);
```

là **snippet minh họa không độc lập**; nó chỉ có ý nghĩa nếu bạn đã bật statistics, xóa bộ đếm đúng lúc, kiểm soát setup queries, lazy associations, cache và session boundaries.

Tốt hơn:

- Seed data *trước khi reset SQL counters*.
- Thực thi đúng một query path + load associations mà endpoint thật sử dụng.
- Assert số SQL hoặc upper bound theo kiến trúc được chấp nhận, không theo số log lines tùy tiện.
- Lặp trên datasets 1/10/100 parents để thấy query count có tăng tuyến tính kiểu N+1 không.
- Đo trong application context phù hợp, không chỉ gọi repository mà bỏ qua phần DTO mapping khiến lazy loads phát sinh.

### 11.3. Performance không chỉ là latency

Một query trả 10.000 entities có thể nhanh ở SQL nhưng gây nhiều heap allocations, JSON serialization cost hoặc response payload lớn. Với HTTP API, cần theo dõi:

- DB query latency.
- Query count và total DB time per request.
- Result rows/bytes.
- Hibernate entity hydration + first-level cache memory.
- Pagination/count-query overhead.
- Network bytes và HTTP serialization.
- GC/heap, peak RSS, client timeout.
- Connection pool saturation khi chạy đồng thời.

Một repository correctness test không thay cho end-to-end performance tests; vẫn cần profile endpoint theo workload thực tế.

## 12. Các anti-pattern khi thiết kế dữ liệu kiểm thử truy vấn

### 12.1. “Dùng H2 5 rows rồi áp SLO production”

**Sai:** kết quả truy vấn dưới 5 ms trên H2 in-memory được coi như bằng chứng PostgreSQL qua mạng sẽ dưới 100 ms với 100 triệu rows.

**Đúng:** test H2 xác minh query semantics, sau đó dùng DB engine/version thật + representative dataset + controlled workload cho performance, thống kê nhiều lần/percentiles. So sánh plan và row estimates trước khi tối ưu.

### 12.2. Random không seed

**Sai:** tạo 1.000 customers bằng `new Random()`, để test thi thoảng fail khi không có rare status hoặc khi page boundary thay đổi.

**Đúng:** seed cố định, verify histogram, thêm deterministic edge cases để bảo đảm trạng thái hiếm.

### 12.3. Uniform data cho một domain rất skew

**Sai:** mỗi tenant có đúng 50 rows và 50% PAID, trong khi production có tenant lớn và tenant nhỏ khác nhau hàng nghìn lần.

**Đúng:** giữ top tenants, long-tail và conditional state distribution. Test filters với both popular và rare predicates.

### 12.4. Mọi timestamp đều unique

**Sai:** generated timestamps dùng `BASE.plusNanos(id)` khiến không bao giờ có tied sort keys.

**Đúng:** tạo nhiều rows cùng timestamp và luôn sắp xếp thêm unique tie-breaker cho stable pagination.

### 12.5. Không test NULL, empty hoặc duplicates

**Sai:** fixture luôn có customer_ref và unique, dù schema cho phép null/duplicate.

**Đúng:** tách `NULL`, `""`, whitespace, repeated refs; assert correct query predicate và business semantics.

### 12.6. Query expected được tính bằng cùng một query

**Sai:**

```java
long expected = repository.countByTenantId("HOT");
assertThat(repository.countByTenantId("HOT"))
        .isEqualTo(expected);
```

Đây là **phản mẫu**: gọi một method hai lần rồi so bằng nhau là kiểm tra giả. Kỳ vọng phải độc lập, ví dụ HOT=900 theo generator contract hoặc một oracle khác được xác định trước.

### 12.7. So thời gian bằng “mili giây” trên CI không kiểm soát

**Sai:**

```java
long start = System.currentTimeMillis();
repository.findByTenantId("HOT", pageable);
assertThat(System.currentTimeMillis() - start)
        .isLessThan(20);
```

Đây là **phản mẫu**, không phải performance test đáng tin. Nó phụ thuộc scheduler, CPU contention, JVM/JIT, DB cache và timer resolution.

**Đúng:** test correctness ở unit/slice; đo performance bằng suite được thiết kế với warm-up, workload, số lần chạy, p95/p99, query plans, resource metrics và machine/DB settings được kiểm soát.

### 12.8. Dữ liệu commit rò sang test sau

**Sai:** seed vào shared database rồi không cleanup; kết quả phụ thuộc test order.

**Đúng:** với `@DataJpaTest`, seed trong transactional test và rollback mặc định; với `@SpringBootTest(RANDOM_PORT)`, test-managed transaction ở JUnit thread **không tự rollback** operations server thread. Cần cleanup/schema riêng ở đúng transaction boundary.

### 12.9. Chỉ kiểm tra totalElements, không kiểm tra content

**Sai:** Page totalElements đúng, nhưng content có tenant khác hoặc duplicates.

**Đúng:** assert cả total count, mọi row thuộc scope, size, order, no overlap và boundary values. Tổng đúng có thể chỉ là trùng hợp khi filters sai.

### 12.10. Đánh giá plan bằng tên index cố định

**Sai:** test cứng rằng EXPLAIN output phải chứa `idx_inv_tenant_state_time_id` trên mọi H2/PostgreSQL version.

**Đúng:** dùng EXPLAIN cho chẩn đoán, đo actual rows/plan trong môi trường phù hợp; khi cần regression guard, pin DB version/dataset/stats và theo dõi behavior/plan class có ngưỡng rõ.

## 13. Khi cần kiểm thử với database giống production

### 13.1. H2 hữu ích nhưng không thay database engine thật

H2 cho phản hồi nhanh về entity mappings, JPQL, basic sort/pagination/aggregates. Nhưng khác PostgreSQL/MySQL ở:

- Optimizer/planner and statistics.
- Index support, index-only scans, partial indexes.
- SQL dialect, functions, collations, NULL ordering.
- JSONB/array/full-text/partitioning.
- Isolation/locks/deadlock behavior.
- Timezone, timestamp precision.
- Query plan stability under skew and large volume.
- DDL constraints/unique/deferrable behaviors.

Nếu production query dựa vào PostgreSQL-specific JSONB, trigram search, partial index hoặc recursive CTE, viết **integration tests trên PostgreSQL engine thật**, không ép H2 mô phỏng mọi syntax.

### 13.2. Testcontainers ở tầng integration

Có thể chạy PostgreSQL trong Testcontainers để test database engine đúng version. Phác thảo cấu hình Spring Boot 3.1+:

```java
@Testcontainers
@SpringBootTest
class PostgresQueryIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Inject real repository, seed representative dataset,
    // run queries, assert correctness/plan/performance contract.
}
```

**Đây chỉ là snippet kiến trúc**, không phải test class hoàn chỉnh. Cần dependencies `org.testcontainers:postgresql`, `junit-jupiter`/Boot `spring-boot-testcontainers` tương ứng, Docker runtime và migrations/schema riêng. Không đưa snippet này vào project H2 runnable ở phần 5 mà không bổ sung build/config.

Khi dùng Testcontainers, chọn production-compatible PostgreSQL major version; kiểm soát image updates, reused containers, migrations, database isolation, cleanup và CI resources. Không lấy runtime một lần khởi động container làm DB query latency benchmark.

### 13.3. Staging dataset và snapshot

Để đo performance ở quy mô hàng triệu rows:

1. Tạo schema, indexes và constraints giống production.
2. Seed bằng bulk loading/batch inserts có đo thời gian riêng, không tính seed vào query timing.
3. Chạy `ANALYZE`/statistics theo chiến lược DB.
4. Warm up query paths và kiểm tra cache state.
5. Thực thi nhiều loại query theo workload mix (popular/rare predicates).
6. Chạy concurrency có kiểm soát, không chỉ một client.
7. Đo actual plan/latency/resource metrics.
8. Bắt regression theo baseline/SLO với tolerance hợp lý, giữ artifact để debug.
9. Cleanup test data hoặc drop isolated schema/container.
10. Không dùng thông tin định danh hoặc dữ liệu cá nhân thật nếu không có quyền/biện pháp xử lý tương ứng.

## 14. Những câu hỏi cần ghi vào test plan

| Câu hỏi | Ví dụ trả lời từ dataset của bài |
|---|---|
| Query nào là đường chính? | HOT/PAID, COLD/PAID, tenant timeline |
| Group nào phổ biến nhất? | HOT 900/1.200 |
| Có correlated predicates? | HOT 70% PAID, COLD 20% PAID |
| Có duplicate sort keys? | 24 distinct timestamps cho 1.200 rows |
| Có null/blank? | 60 NULL refs; HOT có 26 blank refs |
| Có many-to-one duplicates? | CUST-7 có 18 HOT và 5 COLD rows |
| Có outliers? | Một hàng 1.000.000 cents |
| Page size là bao nhiêu? | 40 |
| Có page cuối không đầy? | HOT/PAID 630 → last page 30 |
| Có empty result? | Tenant NOT-PRESENT |
| Oracle của query ở đâu? | Generator contract, expected counts, half-open boundaries |
| Scope transaction? | @DataJpaTest transactional, rollback sau từng method |
| DB engine test logic? | H2 |
| DB engine test performance? | Phải dùng engine như production |
| Đo plan ở đâu? | EXPLAIN/EXPLAIN ANALYZE trong workload integration |
| Cần test concurrency? | Nếu API paging/feed cập nhật đồng thời |

**Một bộ dữ liệu test tốt có hồ sơ như trên**, được version hóa cùng test code và review khi query/business domain thay đổi.

## 15. Bài tập thực hành và lời giải

### Bài A. Phát hiện lỗi phân trang

Một query dùng `ORDER BY created_at DESC`, `LIMIT 40 OFFSET 40`. Trong bảng có 500 rows cùng `created_at`. Hai lần chạy trang thứ hai trả IDs khác nhau. Query có nhất thiết sai SQL syntax không?

**Đáp án:** không; SQL chỉ yêu cầu sort theo created_at. Trong nhóm có cùng timestamp, thứ tự không được xác định. Thêm unique tie-breaker như `ORDER BY created_at DESC, id DESC` và test nhiều tied timestamps. Khi có concurrent writes, còn phải xác định snapshot/cursor policy.

### Bài B. Data uniform che bug gì?

Tenant HOT có 70% PAID và COLD có 20% PAID nhưng fixtures đều dùng 50%. Tại sao performance regression có thể không xuất hiện?

**Đáp án:** cardinality/selectivity estimates và query plan khác khi phân bố/correlation khác. Planner có thể chọn index/table scan/join khác; test uniform không mô phỏng popular/rare predicates. Cần workload có skew/correlation và DB statistics tương ứng.

### Bài C. NULL và blank

Repository có query `findByCustomerRefIsNull()`. Một row `customerRef=""` có được tính không?

**Đáp án:** không; empty string là một giá trị khác `NULL` theo semantics SQL thông thường (có ngoại lệ theo DB, ví dụ một số DB xử lý empty strings đặc biệt). Test riêng NULL, blank và trên database engine thật khi compatibility là yêu cầu.

### Bài D. Tổng tiền quá lớn

Một `SUM(gross_cents)` bị ép vào Java `int`. Test với 5 rows mỗi hàng 100 cents pass. Rủi ro?

**Đáp án:** khi tổng vượt 2.147.483.647 có thể overflow/convert error. Dùng `long/Long` hoặc `BigDecimal` theo domain, seed outliers/số lượng lớn hoặc boundary fixtures để chứng minh không tràn.

### Bài E. Page và Slice

Một API chỉ hiển thị nút “Xem tiếp”, không hiển thị tổng số records. Có bắt buộc dùng `Page` không?

**Đáp án:** không. `Slice` thường đủ cho “has next” và có thể tránh count query. Cần test hasNext/page boundary, đồng thời đảm bảo sorting/pagination theo dataset phù hợp.

### Bài F. Keyset cursor thiếu id

Một query có điều kiện `createdAt > cursorTime` và 100 rows cùng timestamp ở cuối page. Hậu quả?

**Đáp án:** bỏ qua những rows còn lại cùng timestamp. Cursor cần toàn bộ keyset định nghĩa total order, ví dụ `(createdAt,id)`; predicate dùng `createdAt > t OR (createdAt=t AND id>cursorId)` khi sort ASC.

### Bài G. EXPLAIN trên H2 có chứng minh PostgreSQL nhanh không?

**Không.** H2 và PostgreSQL có optimizer, statistics/index behavior khác nhau. EXPLAIN H2 hữu ích cho chẩn đoán bài sample; performance contract cần DB engine/version, schema/indexes, row counts và workload gần production.

### Bài H. Dữ liệu JPA test tự biến mất

Bạn seed 1.200 rows trong `@BeforeEach` của `@DataJpaTest`, test method query thấy đủ, nhưng test sau không có rows cho tới khi @BeforeEach seed lại. Có phải dữ liệu bị mất do H2 lỗi?

**Không.** `@DataJpaTest` mặc định mở test-managed transaction và rollback sau method. Fixture trong transaction được hoàn tác. Đây là cơ chế isolation hợp lý cho test correctness.

### Bài I. Date range tháng

Một báo cáo lấy điều kiện `createdAt BETWEEN start AND end`, trong khi hai kỳ liên tiếp dùng cùng end/start boundary. Rủi ro?

**Đáp án:** `BETWEEN` bao gồm cả hai đầu, có thể đếm trùng rows đúng mốc nối. Thường dùng interval nửa mở `[from,to)`: `>= from AND < to`. Nhưng phải xác định timezone và precision theo business domain.

### Bài J. Tối ưu test seed tốn 30 giây

Một lớp có 100 tests, mỗi test seed 1 triệu rows. Có nên bỏ hết test về dữ liệu lớn?

**Không.** Tách logic-shape tests nhanh khỏi performance/integration suite chạy theo lịch. Dùng reproducible isolated snapshot/bulk loader cho lớp lớn, vẫn giữ vài tests correctness có edge cases. Không bỏ volume validation nếu nghiệp vụ cần nó; thay cách tổ chức.

### Bài K. Query COUNT đúng nhưng dữ liệu sai tenant

Một repository method trả total 40, nhưng một số rows thuộc tenant khác. Tại sao count assertion không đủ?

**Vì** total 40 có thể đúng tình cờ. Phải assert tenant id của từng returned row; khi truy vấn phức tạp, có test API/security scope và database row-level security phù hợp.

### Bài L. Timestamp của test thay đổi theo hôm nay

Fixture dùng `LocalDateTime.now()` rồi filter theo UTC midnight, chạy sáng xanh, chiều đỏ. Sửa thế nào?

**Đáp án:** dùng thời điểm cố định, clock được inject/fake, timezone policy rõ ràng và interval boundaries tường minh. Không phụ thuộc local timezone của CI runner cho expected query result.

## 16. Checklist trước khi gọi query test là đáng tin

- [ ] Tài liệu query có mô tả bảng, predicates, joins, sorting, pagination, aggregates.
- [ ] Dataset có **số rows** đáp ứng mục tiêu test logic hoặc performance.
- [ ] Có xác định **histogram/conditional distributions**, không chỉ tổng N.
- [ ] Có popular và rare values, tenant lớn và tenant nhỏ.
- [ ] Có correlation giữa các columns nếu workload thật có.
- [ ] Có NULL, blank, duplicates và outliers theo schema/business constraints.
- [ ] Có tied timestamps/sort keys nếu dữ liệu thật có thể trùng.
- [ ] Có edge cases 0, 1, page size, page size+1, last page.
- [ ] Có temporal [from,to) boundary và timezone/precision policy.
- [ ] Có explicit unique tie-breaker để pagination ổn định trên dataset tĩnh.
- [ ] Nếu dùng keyset pagination, cursor chứa đủ sort keys.
- [ ] Nếu có writes giữa pages, có concurrency/snapshot test riêng.
- [ ] Oracle độc lập với chính query đang kiểm thử.
- [ ] Mọi rows trả về đều thuộc expected tenant/scope; không chỉ đúng count.
- [ ] Kiểm tra count query/Page.totalElements khi query có joins/grouping.
- [ ] Kiểm tra aggregate với outliers và null/empty result.
- [ ] Fixture deterministic, seed/version ghi rõ và tái tạo được.
- [ ] Test có thể chạy độc lập, không phụ thuộc test order.
- [ ] Setup/cleanup đúng transaction boundaries; @DataJpaTest rollback hoặc cleanup explicit.
- [ ] Không dùng production PII/secrets trong fixtures hoặc logs.
- [ ] Tách correctness assertions khỏi latency benchmark dễ flaky.
- [ ] Performance jobs dùng DB engine/version/schema/indexes tương tự production.
- [ ] Statistics/ANALYZE được cập nhật trước khi đọc plan.
- [ ] Có representative popular/rare predicates trong workload mix.
- [ ] Theo dõi DB latency, rows, count queries, N+1, memory/GC, network nếu liên quan.
- [ ] Không so sánh chỉ một lần chạy hoặc hardcode plan index names tùy optimizer.
- [ ] Có Testcontainers/real engine tests khi dùng SQL dialect, index, collation, JSONB.
- [ ] Có cleanup schema/container/bulk fixture rõ ràng sau performance suite.
- [ ] Build wrapper/JUnit reports chứng minh tests đã chạy, không skipped/up-to-date bất ngờ.

## 17. Kết luận

**Chất lượng của bài kiểm thử truy vấn phụ thuộc không chỉ vào số lượng dữ liệu mà còn vào cách dữ liệu được phân bố và những đặc điểm có khả năng làm thay đổi kết quả hoặc kế hoạch thực thi.** Một fixture 1.200 hàng được thiết kế có chủ đích — 900/300 giữa tenants, trạng thái 70%/20%, NULL/blank/duplicate refs, timestamp ties, outlier amounts — có thể phát hiện nhiều lỗi correctness hơn hàng nghìn rows đồng đều.

Trong Spring Boot, hãy dùng **`@DataJpaTest` với fixture deterministic** cho các hợp đồng về filter, count, aggregate, pagination và query semantics; dùng **real database integration/performance suite** khi mục tiêu là optimizer, scale, index, concurrency hoặc độ trễ production. Bảo đảm expected results độc lập với câu query, stable ordering có tie-breaker, dataset profile có thể tái lập và cleanup đúng transaction.

Một test truy vấn đáng tin trả lời được ba câu: **dữ liệu nào đã được chọn để mô phỏng workload, query đã chứng minh điều gì, và giới hạn của bằng chứng ấy là gì?**

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — @DataJpaTest](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html): JPA slice, embedded database, rollback mặc định.
- [Spring Data JPA — Defining Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html): query method names, Page/Slice, Pageable, sorting, pagination, keyset.
- [Spring Data JPA — JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): @Query, named parameters, native SQL count queries, query rewriting, scrolling.
- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): Page, Slice, Sort, Pageable, Window, ScrollPosition.
- [Hibernate ORM — User Guide](https://docs.hibernate.org/stable/orm/userguide/html_single/): JDBC batching, fetching, N+1, query pagination, JPA persistence context.
- [H2 — SQL Commands](https://h2database.github.io/html/commands.html): EXPLAIN, EXPLAIN ANALYZE, DDL và SQL dialect của H2.
- [PostgreSQL 17 — Planner Statistics](https://www.postgresql.org/docs/17/planner-stats.html): histograms, most-common values, extended statistics, ANALYZE.
- [PostgreSQL 17 — Using EXPLAIN](https://www.postgresql.org/docs/17/using-explain.html): estimated/actual rows, buffers, plan evaluation.
- [Spring Boot — Testcontainers Service Connections](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): @ServiceConnection, Docker-based integration tests.
- [Spring Framework — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transaction rollback, fixture lifecycle và thread boundaries.
