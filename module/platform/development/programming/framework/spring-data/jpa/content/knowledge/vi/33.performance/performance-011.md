# Kiểm thử hiệu năng với cơ sở dữ liệu và dữ liệu gần thực tế

Một truy vấn Spring Data JPA chạy nhanh với vài chục bản ghi trong H2 chưa chứng minh rằng nó sẽ chạy tốt trên cơ sở dữ liệu thật với hàng trăm nghìn hoặc hàng triệu bản ghi. Hiệu năng phụ thuộc vào hệ quản trị cơ sở dữ liệu, schema, index, số lượng và phân bố dữ liệu, quan hệ giữa các bảng, cache, connection pool và mức độ truy cập đồng thời.

Kiểm thử hiệu năng có giá trị khi môi trường và dữ liệu phản ánh đủ gần workload thực tế để kết quả có thể dùng ra quyết định. Bài này trình bày cách dựng database kiểm thử bằng Testcontainers, tạo dữ liệu đại diện, đo query count và độ trễ, đọc execution plan và thiết kế kiểm thử có thể lặp lại.

> Các đoạn Java dưới đây là snippet cho dự án Java 17+ dùng Spring Boot 3+ và `spring-boot-starter-data-jpa`. Chúng minh họa cấu hình và phương thức cần tích hợp vào dự án, không phải chương trình độc lập chạy trực tiếp bằng `javac`/`java`.

## 1. Xác định điều cần đo

Trước khi viết test, xác định câu hỏi hiệu năng mà test cần trả lời. Một số mục tiêu thường gặp:

- Một truy vấn tìm kiếm hoặc phân trang có giữ được độ trễ chấp nhận được khi bảng tăng lên kích thước dự kiến không?
- Một API có phát sinh N+1 query khi tải entity cùng quan hệ không?
- Index mới có làm giảm thời gian truy vấn và số block đọc không?
- Một thao tác ghi hàng loạt có giữ được throughput khi số bản ghi tăng không?
- Connection pool có bị cạn khi nhiều request cùng truy cập database không?
- Khi nhiều transaction chạy đồng thời, lock wait, deadlock hoặc timeout có tăng không?

Chọn chỉ số theo mục tiêu. Các chỉ số hữu ích gồm:

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Độ trễ | p50, p95, p99 | Thời gian phản hồi ở trung vị và các phân vị chậm |
| Thông lượng | requests/second hoặc operations/second | Số thao tác hoàn tất trong một đơn vị thời gian |
| Độ ổn định | error rate, timeout, retry | Tỷ lệ yêu cầu thất bại hoặc phải thử lại |
| SQL | số prepared statement, số query, thời gian SQL | Phát hiện N+1 hoặc truy vấn đắt |
| Database | CPU, I/O, buffer hit/read, lock wait | Xác định nút thắt ở database |
| Connection pool | active, idle, pending, timeout | Phát hiện thiếu kết nối hoặc chờ lấy kết nối |
| JVM | heap, GC pause, CPU | Phân biệt chi phí ORM/JVM với chi phí database |

Không nên chỉ đo thời gian của một lần gọi. Một kết quả đơn lẻ dễ bị ảnh hưởng bởi khởi động JVM, tạo connection, biên dịch query plan, cache và tải nền. Hãy đo nhiều lần sau giai đoạn warm-up và so sánh các phân vị, không chỉ nhìn giá trị trung bình.

## 2. Dùng đúng loại cơ sở dữ liệu

H2 hoặc database in-memory rất tiện cho unit test và kiểm tra mapping cơ bản, nhưng không đại diện đầy đủ cho PostgreSQL, MySQL, Oracle hay SQL Server. Khác biệt về dialect, kiểu dữ liệu, index, collation, execution planner, isolation level và cách xử lý SQL có thể làm kết quả hiệu năng khác đáng kể.

Đối với integration/performance test, hãy dùng cùng loại database và phiên bản gần với môi trường triển khai. Testcontainers có thể khởi chạy database thật trong Docker cho mỗi test suite hoặc application context. Ví dụ dưới đây dùng PostgreSQL:

**Phụ thuộc test cần có** (quản lý version qua Spring Boot dependency management hoặc Testcontainers BOM):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
```

Spring Boot hỗ trợ `@ServiceConnection` để tự cấu hình kết nối từ container. Có thể khai báo container như một Spring bean để vòng đời container gắn với application context:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
class TestDatabaseConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
```

Sau đó import cấu hình vào integration test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(TestDatabaseConfiguration.class)
class OrderRepositoryPerformanceIT {

    @Test
    void applicationConnectsToPostgres() {
        // Spring context đã kết nối PostgreSQL trong Testcontainers.
    }
}
```

Cấu hình trên cần Docker runtime mà Testcontainers hỗ trợ. Dependency `spring-boot-testcontainers` cung cấp tích hợp `@ServiceConnection`. Nếu dùng cách cấu hình thủ công, có thể đăng ký JDBC URL, username và password qua `@DynamicPropertySource`.

Dùng Spring-managed container giúp vòng đời container phù hợp với vòng đời application context được Spring cache giữa các test. Nếu dùng JUnit `@Testcontainers` với static `@Container`, cần chú ý container có thể dừng sau test class trong khi Spring vẫn giữ application context để tái sử dụng ở test khác. Spring Boot khuyến nghị quản lý container như bean trong trường hợp context có thể được cache và dùng lại.

## 3. Tạo dữ liệu có quy mô và phân bố gần thực tế

Số lượng bản ghi chỉ là một phần của dữ liệu kiểm thử. Một fixture tốt nên mô phỏng:

- Quy mô bảng gần với dự kiến khi vận hành, bao gồm cả bảng chính và bảng quan hệ.
- Phân bố giá trị: trạng thái phổ biến/hiếm, giá trị null, khoảng ngày tháng, nhóm dữ liệu lệch (skew).
- Cardinality và phân bố quan hệ: một khách hàng có bao nhiêu đơn hàng, một đơn hàng có bao nhiêu dòng chi tiết.
- Độ dài chuỗi, kích thước JSON/blob và các cột thường được lọc hoặc sắp xếp.
- Tỷ lệ dữ liệu mới/cũ và tỷ lệ bản ghi thỏa điều kiện truy vấn.
- Index, foreign key, unique constraint và migration giống môi trường thật.

Ví dụ, một bảng có 100.000 đơn hàng nhưng chỉ có 10 trạng thái hiếm được tìm kiếm sẽ tạo ra kế hoạch truy vấn khác với bảng có 100.000 đơn hàng chia đều cho các trạng thái. Một truy vấn lọc theo ngày cũng cần dữ liệu trải dài qua các tháng/năm, thay vì tất cả bản ghi có cùng một timestamp.

Có thể tạo dữ liệu bằng migration test, SQL fixture, `JdbcTemplate` batch insert hoặc một công cụ sinh dữ liệu riêng. Với PostgreSQL, `generate_series` giúp tạo fixture lớn nhanh chóng. Ví dụ SQL minh họa:

```sql
INSERT INTO purchase_order (status, total_amount, created_at)
SELECT
    CASE WHEN n % 20 = 0 THEN 'CANCELLED' ELSE 'PAID' END,
    (100 + (n % 50000))::numeric / 100,
    now() - (n || ' seconds')::interval
FROM generate_series(1, 100000) AS n;
```

Câu lệnh trên tạo 100.000 đơn hàng với phân bố trạng thái lệch 95/5 và thời điểm tạo trải dài. Đây là dữ liệu tổng hợp đơn giản; workload thực tế có thể cần thêm khách hàng, dòng hàng, địa chỉ, lịch sử và các phân bố phức tạp hơn.

Nạp fixture trước vùng đo. Không tính thời gian tạo dữ liệu vào thời gian truy vấn cần benchmark. Nếu cần mô phỏng khối lượng rất lớn, nạp theo batch và tránh giữ toàn bộ entity trong persistence context hoặc heap. Có thể dùng JDBC batch để tạo fixture nhanh, sau đó dùng repository/JPA để kiểm tra đường truy cập cần đo.

Dữ liệu từ production cần được ẩn danh hoặc tổng hợp trước khi đưa vào môi trường kiểm thử. Giữ lại phân bố và quan hệ cần thiết cho phép đánh giá hiệu năng mà không mang thông tin cá nhân vào fixture.

## 4. Dùng schema và cấu hình gần production

Database kiểm thử nên được dựng bằng cùng migration mà ứng dụng dùng khi triển khai, chẳng hạn Flyway hoặc Liquibase. Không chỉ tạo bảng bằng `hibernate.ddl-auto=create` nếu production dùng migration, vì schema sinh tự động có thể thiếu index, constraint, kiểu dữ liệu hoặc cấu trúc tối ưu thực tế.

Kiểm tra các yếu tố sau trước khi đo:

- Cùng phiên bản major của database và các extension quan trọng.
- Cùng migration, index, constraint và kiểu dữ liệu.
- Cấu hình connection pool và giới hạn kết nối có ý nghĩa tương đương.
- Isolation level và cấu hình transaction phù hợp.
- Cấu hình Hibernate/JPA, fetch strategy và batch size gần với ứng dụng thật.
- Cache cấp một, cache cấp hai và query cache được bật/tắt theo đúng kịch bản muốn đo.

Một container database vẫn có thể khác production về CPU, RAM, ổ đĩa, network và cấu hình server. Vì vậy, Testcontainers rất tốt cho kiểm tra tích hợp và so sánh có kiểm soát, nhưng benchmark trên máy developer không tự động đại diện cho latency production. Với quyết định capacity hoặc SLA, cần một môi trường benchmark có tài nguyên được kiểm soát và gần với hạ tầng triển khai.

## 5. Viết integration test cho repository

Ví dụ repository dùng projection để lấy đúng các trường cần thiết, tránh tải toàn bộ entity khi màn hình chỉ cần một phần dữ liệu:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Page<OrderSummary> findByStatus(
            OrderStatus status,
            Pageable pageable);
}
```

Projection:

```java
import java.math.BigDecimal;
import java.time.Instant;

public interface OrderSummary {
    Long getId();
    BigDecimal getTotalAmount();
    Instant getCreatedAt();
}
```

Một integration test có thể xác nhận truy vấn hoạt động trên PostgreSQL và trả đúng số lượng trang:

```java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManagerFactory;

import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@SpringBootTest
@Import(TestDatabaseConfiguration.class)
class OrderRepositoryPerformanceIT {

    @Autowired
    private PurchaseOrderRepository repository;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Test
    void loadsPageWithBoundedStatementCount() {
        // Fixture đại diện đã được nạp trước khi đo.
        SessionFactory sessionFactory =
                entityManagerFactory.unwrap(SessionFactory.class);
        Statistics statistics = sessionFactory.getStatistics();

        statistics.setStatisticsEnabled(true);
        statistics.clear();

        Page<OrderSummary> page = repository.findByStatus(
                OrderStatus.PAID,
                PageRequest.of(
                        0,
                        50,
                        Sort.by(Sort.Direction.DESC, "createdAt")));

        long statements = statistics.getPrepareStatementCount();

        assertThat(page.getContent()).hasSize(50);
        assertThat(statements).isLessThanOrEqualTo(2);
    }
}
```

`Statistics` là API riêng của Hibernate. `getPrepareStatementCount()` giúp kiểm tra số prepared statement được lấy trong khoảng đo. Với một truy vấn phân trang projection, có thể có một câu truy vấn lấy trang và một câu count; giới hạn cụ thể phải dựa trên query thực tế của ứng dụng.

Ví dụ trên giả định fixture đã có đủ dữ liệu PAID và test được chạy cô lập. Hibernate statistics là số liệu toàn cục ở cấp `SessionFactory`, vì vậy không dùng cách reset rồi đo này đồng thời với test khác đang chạy song song trên cùng context. Statistics cũng tạo thêm overhead; chỉ bật khi cần chẩn đoán, không dùng số đo đó làm benchmark latency cuối cùng.

Đếm query giúp phát hiện N+1 nhưng không chứng minh truy vấn nhanh. Một câu SQL duy nhất vẫn có thể quét toàn bảng, join quá nhiều hàng hoặc trả payload lớn. Cần kết hợp số lượng statement với execution plan và độ trễ.

## 6. Đo hiệu năng một cách lặp lại

Một quy trình đo nên tách rõ các giai đoạn:

1. **Chuẩn bị:** khởi động ứng dụng và database, chạy migration, nạp fixture và xác nhận dữ liệu.
2. **Warm-up:** gửi các request thử để JVM JIT, connection pool, ORM metadata và query plan cache ổn định.
3. **Đo:** chạy cùng workload trong một khoảng thời gian hoặc số lần lặp đã định trước.
4. **Lặp lại:** thực hiện nhiều vòng đo với điều kiện tương đương, tránh kết luận từ một lần chạy.
5. **Phân tích:** so sánh p50/p95/p99, throughput, error rate, query count và tài nguyên database.
6. **Lưu kết quả:** ghi lại commit, cấu hình, phiên bản database, kích thước fixture, concurrency và cache state để có thể tái lập.

Ví dụ một kịch bản workload có thể gồm:

- 70% request tìm kiếm đơn hàng theo trạng thái và khoảng ngày.
- 20% request mở chi tiết đơn hàng cùng khách hàng và các dòng hàng.
- 10% request cập nhật trạng thái hoặc ghi dữ liệu.

Tỷ lệ trên chỉ là ví dụ. Hãy lấy phân bố từ log/metrics đã ẩn danh hoặc yêu cầu nghiệp vụ để chọn workload sát ứng dụng. Ngoài tỷ lệ request, cần mô phỏng số người dùng đồng thời, think time, burst và thời gian chạy liên tục.

Ghi nhận tối thiểu:

- p50, p95 và p99 latency.
- Throughput trong cùng khoảng đo.
- Error rate, timeout và retry.
- Số SQL statement trên một request hoặc use case.
- CPU, memory, disk I/O, buffer hit/read và lock wait của database.
- Connection pool active/idle/pending và thời gian chờ lấy connection.
- Heap, GC pause và CPU của JVM.

Không nên đặt assertion kiểu “truy vấn phải chạy dưới 50 ms” trong mọi CI runner nếu tài nguyên chạy test không được kiểm soát. Máy CI bận, cold cache hoặc tốc độ ổ đĩa khác có thể làm test chập chờn. Hãy dùng CI để giữ các kiểm tra ổn định như query count, số bản ghi, không phát sinh N+1 và tính đúng của pagination. Đo latency/throughput để so sánh baseline trên runner hoặc môi trường benchmark có cấu hình cố định; dùng ngưỡng regression có biên độ phù hợp với độ dao động đã quan sát.

## 7. Đọc execution plan để tìm nút thắt

Khi một query chậm, hãy lấy SQL thực tế cùng tham số đại diện và xem execution plan của database. Với PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, total_amount, created_at
FROM purchase_order
WHERE status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
```

`EXPLAIN` cho biết database dự định thực thi câu lệnh như thế nào. `EXPLAIN ANALYZE` thực thi câu lệnh thật và báo số hàng thực tế, thời gian theo node và các thông tin buffer. Hãy chú ý:

- Sequential scan hay index scan có hợp lý với số hàng cần đọc không.
- Số hàng ước lượng có gần với số hàng thực tế không.
- Có sort lớn hoặc temporary spill không.
- Join strategy và thứ tự join có phù hợp không.
- Buffer hit/read cho thấy mức truy cập bộ nhớ và I/O như thế nào.
- Index có hỗ trợ đồng thời điều kiện lọc và thứ tự sắp xếp không.

`EXPLAIN ANALYZE` thực thi câu lệnh, kể cả câu lệnh ghi. Chỉ chạy trên database kiểm thử/staging có thể khôi phục; với DML có thể dùng transaction rồi `ROLLBACK` khi phù hợp. Không chạy thử một câu update/delete có tác động trên production chỉ để lấy thời gian. Kết quả cũng không bao gồm đầy đủ thời gian truyền dữ liệu qua mạng tới ứng dụng và có overhead đo đạc, nên không đồng nhất với latency của request end-to-end.

Sau khi thay đổi index hoặc query, hãy chạy lại cùng workload và cùng dataset. Không thêm index chỉ dựa trên phỏng đoán: index làm tăng chi phí ghi và dung lượng lưu trữ, vì vậy cần chứng minh lợi ích trên cả đường đọc lẫn đường ghi liên quan.

## 8. Các nguồn gây sai lệch khi benchmark

### Dữ liệu quá nhỏ hoặc quá đồng đều

Bảng nhỏ có thể khiến database chọn sequential scan dù production sẽ dùng index. Dữ liệu chỉ có một vài giá trị lặp lại cũng không mô phỏng đúng phân bố và thống kê của planner. Tạo fixture đủ lớn, đủ đa dạng và cập nhật statistics database khi cần.

### Cache không được kiểm soát

Lần chạy đầu có thể đọc từ disk, lần sau dữ liệu đã nằm trong database buffer cache hoặc OS page cache. Hibernate second-level cache và query cache cũng có thể thay đổi số truy vấn thực sự gửi tới database. Hãy ghi rõ đang đo cold-cache hay warm-cache, giữ trạng thái tương đương giữa các phiên so sánh và không trộn hai loại kết quả.

### Log SQL trong vùng đo

Bật log toàn bộ SQL hoặc bind parameter ở mức TRACE có thể làm chậm đáng kể ứng dụng và tạo lượng log lớn. Dùng logging để chẩn đoán một kịch bản ngắn; tắt hoặc giảm log khi đo hiệu năng chính thức. Tránh log giá trị chứa dữ liệu nhạy cảm.

### Đo cả thời gian chuẩn bị

Không tính thời gian khởi động container, migration, tạo fixture, khởi tạo context hoặc warm-up vào latency của truy vấn nếu mục tiêu là đo query. Ngược lại, nếu mục tiêu là cold-start của ứng dụng, phải đo riêng như một kịch bản khác.

### Transaction test không giống request thật

Spring TestContext thường chạy test `@Transactional` trong test-managed transaction và rollback khi test kết thúc. Nếu service được gọi bên trong test đó, transaction service có thể tham gia transaction test do propagation `REQUIRED`. Điều này khác với mỗi HTTP request có transaction riêng và commit riêng. Khi đo transaction lifecycle thực tế, hãy thiết kế test sao cho transaction được mở và kết thúc ở đúng ranh giới cần đo.

## 9. Phân biệt integration test, load test và microbenchmark

- **Integration test:** xác nhận mapping, query, transaction, migration và tương tác với database thật. Testcontainers phù hợp để dựng dependency nhất quán.
- **Performance regression test:** chạy một số workload lặp lại và theo dõi query count hoặc các chỉ số ổn định để phát hiện thay đổi xấu.
- **Load/stress test:** tạo nhiều request đồng thời qua ứng dụng, đo p95/p99, throughput, error rate và giới hạn tài nguyên. Có thể dùng Gatling, k6 hoặc JMeter.
- **Microbenchmark:** đo một đoạn tính toán nhỏ trong JVM. JMH phù hợp với mục tiêu này; không nên dùng một vòng lặp `System.nanoTime()` đơn giản để kết luận hiệu năng toàn bộ Spring Data JPA + database.

Đo từ HTTP endpoint sẽ bao gồm controller, serialization, service, ORM, JDBC, network và database. Đo trực tiếp repository bỏ qua một phần chi phí đó. Chọn cấp đo theo câu hỏi và ghi rõ phạm vi của con số.

## 10. Checklist trước khi chấp nhận kết quả

- Database test cùng loại và phiên bản gần production.
- Schema, migration, index và constraint tương đương môi trường triển khai.
- Fixture có quy mô, phân bố, quan hệ và giá trị biên gần thực tế.
- Dữ liệu được nạp trước vùng đo và có thể tái tạo.
- Đã xác định warm-up, cache state, concurrency và thời gian đo.
- Ghi nhận p50/p95/p99, throughput, error rate và tài nguyên.
- Kiểm tra query count để phát hiện N+1, nhưng không dùng query count thay cho latency.
- Phân tích execution plan với tham số và dữ liệu đại diện.
- Không để SQL logging hoặc fixture setup làm sai lệch thời gian đo.
- So sánh trên môi trường có cấu hình ổn định và lưu lại thông tin để tái lập.
- Tách integration test, regression test, load test và microbenchmark theo mục tiêu.

Kiểm thử hiệu năng với database và dữ liệu gần thực tế giúp phát hiện vấn đề trước khi triển khai: query plan không phù hợp, index thiếu, N+1, connection pool nghẽn hoặc chi phí ORM quá lớn. Kết quả đáng tin cậy cần một dataset đại diện, môi trường có thể lặp lại và nhiều chỉ số bổ sung cho nhau thay vì chỉ một con số thời gian.

## Tài liệu tham khảo

- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Testcontainers for Java — PostgreSQL module](https://github.com/testcontainers/testcontainers-java/blob/main/docs/modules/databases/postgres.md)
- [Hibernate ORM — Statistics API](https://docs.hibernate.org/orm/7.4/javadocs/org/hibernate/stat/Statistics.html)
- [PostgreSQL — Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html)