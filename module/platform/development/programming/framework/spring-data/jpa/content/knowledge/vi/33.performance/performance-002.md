# Quan sát số truy vấn, thời gian SQL và số dòng trả về trong Spring Data JPA

## 1. Vì sao cần quan sát truy vấn?

Một chức năng Spring Data JPA có thể chạy đúng về nghiệp vụ nhưng chậm khi dữ liệu tăng. Nguyên nhân thường không nằm ở một dòng Java riêng lẻ mà ở số lần ứng dụng truy cập database, thời gian mỗi câu SQL và lượng dữ liệu phải đọc, truyền qua JDBC rồi chuyển thành object.

Ba tín hiệu cần theo dõi:

- **Query count:** có bao nhiêu câu truy vấn thực sự được thực thi trong một use case hoặc request.
- **SQL execution time:** câu truy vấn mất bao lâu, câu nào chậm nhất và thời gian thay đổi ra sao theo tải.
- **Returned row count:** database/JDBC đã trả về bao nhiêu dòng, ứng dụng giữ lại bao nhiêu entity/DTO và có bao nhiêu dòng bị lặp do JOIN.

Các tín hiệu này giúp phát hiện N+1, fetch quá nhiều dữ liệu, thiếu index, phân trang không hiệu quả và cấu hình cache chưa phù hợp.

Không nên chỉ nhìn thời gian của một request. Hãy kết hợp số truy vấn, thời gian trung bình và phân vị p95/p99, số dòng, cache hit/miss, kích thước dữ liệu và trạng thái connection pool để xác định nguyên nhân.

## 2. Phân biệt các lớp quan sát

Một truy vấn đi qua nhiều lớp:

1. **Spring Data repository:** method như findAll, derived query hoặc @Query được gọi.
2. **Hibernate ORM:** phân tích JPQL/HQL, tạo SQL, quản lý persistence context và ánh xạ kết quả.
3. **JDBC:** gửi statement, bind parameter, thực thi và đọc ResultSet.
4. **Database:** lập kế hoạch, đọc index/table, join, sort, lock và trả dữ liệu.
5. **Ứng dụng:** materialize entity/DTO, xử lý quan hệ, mapping và serialize response.

Mỗi công cụ quan sát một phần khác nhau:

| Công cụ | Đo tốt điều gì | Giới hạn cần nhớ |
|---|---|---|
| Hibernate SQL log | SQL được tạo và thứ tự thực thi | Không tự cung cấp dashboard hoặc phân vị thời gian |
| Hibernate Statistics | Số query, thời gian tổng hợp, cache và entity/collection counters | Phần lớn là số liệu toàn SessionFactory |
| Hibernate QueryStatistics | Số lần, thời gian và số ResultSet rows của một query string | Không tự gắn số liệu với từng HTTP request |
| JDBC/DataSource instrumentation | Thời gian execute, fetch ResultSet, số dòng và số dòng bị tác động | Cần cấu hình proxy/observation và backend metrics/tracing |
| Database monitoring | Execution plan, buffer/cache, lock, I/O và thời gian phía server | Cần đối chiếu với SQL và request ở ứng dụng |

Hãy chọn công cụ theo câu hỏi cần trả lời. Khi debug một query, SQL log thường đủ để bắt đầu. Khi cần so sánh toàn hệ thống, dùng statistics và metrics. Khi cần biết request nào phát sinh nhiều SQL, dùng trace hoặc JDBC instrumentation có correlation với request.

## 3. Bật SQL logging trong Hibernate

Trong Spring Boot, có thể cấu hình logging ở application.properties:

~~~properties
# Hiển thị câu SQL Hibernate gửi qua JDBC
logging.level.org.hibernate.SQL=DEBUG

# Giá trị bind vào PreparedStatement (Hibernate 6)
logging.level.org.hibernate.orm.jdbc.bind=TRACE

# Giá trị đọc từ JDBC ResultSet (Hibernate 6)
logging.level.org.hibernate.orm.jdbc.extract=TRACE

# Format SQL dễ đọc hơn
spring.jpa.properties.hibernate.format_sql=true
~~~

Một số phiên bản Hibernate còn hỗ trợ cấu hình hibernate.show_sql=true để in SQL trực tiếp ra console. Trong ứng dụng Spring Boot, thường nên dùng logger org.hibernate.SQL để output đi qua logging framework, có thể lọc theo level, appender và môi trường.

Ví dụ log SQL có thể cho thấy:

~~~sql
select
    o1_0.id,
    o1_0.customer_id,
    o1_0.created_at,
    o1_0.status
from purchase_order o1_0
where o1_0.customer_id=?
~~~

Dòng bind parameter cho biết giá trị thực tế được gắn vào dấu ?. Khi kiểm tra một query không trả dữ liệu như mong đợi, hãy đối chiếu SQL, kiểu dữ liệu và parameter đã bind.

### Chỉ bật log chi tiết trong thời gian cần thiết

Bind parameter và ResultSet extraction log có thể rất nhiều. Giá trị bind có thể chứa email, số điện thoại, token, thông tin thanh toán hoặc dữ liệu cá nhân. Không bật TRACE rộng trong production nếu chưa có chính sách bảo vệ log, masking, quyền truy cập và thời hạn lưu trữ phù hợp.

SQL log cũng không cho biết đầy đủ số dòng đã được ứng dụng tiêu thụ nếu query dùng streaming hoặc đọc ResultSet từng phần. Dùng công cụ đo JDBC hoặc thống kê query khi cần con số đó.

## 4. Gắn comment để tìm nguồn JPQL

Khi nhiều repository method sinh ra SQL giống nhau, khó biết câu SQL đến từ đâu. Hibernate hỗ trợ hibernate.use_sql_comments để thêm comment HQL/JPQL vào SQL được tạo.

~~~properties
spring.jpa.properties.hibernate.use_sql_comments=true
~~~

Comment giúp nối SQL về query ở tầng ứng dụng. Với Hibernate Query API, có thể đặt comment cho query bằng setComment(...) hoặc query hint tương ứng.

Không đưa thông tin nhạy cảm, ID người dùng hoặc nội dung request vào comment. Hãy dùng tên use case ổn định, ví dụ OrderRepository.findRecentByCustomer.

## 5. Theo dõi slow query bằng Hibernate

Hibernate hỗ trợ hibernate.log_slow_query: đặt ngưỡng thời gian tối thiểu, tính bằng millisecond, để ghi log những SQL vượt ngưỡng.

~~~properties
# Ví dụ: ghi log query có thời gian thực thi lớn hơn 250 ms
spring.jpa.properties.hibernate.log_slow_query=250
~~~

Đây là ngưỡng minh họa. Hãy đặt ngưỡng theo mục tiêu latency của ứng dụng và đặc điểm database. Một truy vấn 150 ms có thể quá chậm với endpoint cần phản hồi 50 ms, nhưng có thể chấp nhận với báo cáo chạy nền.

Có thể bật thêm:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Khi bật, Hibernate thu thập số liệu thống kê để đọc qua Statistics. Hibernate cũng có thể ghi slow query vào statistics map khi cấu hình slow-query logging được bật và phiên bản hỗ trợ.

Slow-query logging giúp tìm những câu vượt ngưỡng. Nó không thay thế histogram hoặc percentile: một query có trung bình 30 ms nhưng p99 là 2 giây vẫn có thể gây trải nghiệm kém.

## 6. Đọc Hibernate Statistics

Hibernate cung cấp Statistics gắn với SessionFactory. Với Spring Boot và Hibernate, có thể unwrap từ EntityManagerFactory:

~~~java
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.springframework.stereotype.Component;

@Component
public class HibernateStatisticsReader {

    private final Statistics statistics;

    public HibernateStatisticsReader(EntityManagerFactory entityManagerFactory) {
        SessionFactory sessionFactory =
            entityManagerFactory.unwrap(SessionFactory.class);
        this.statistics = sessionFactory.getStatistics();
    }

    public void printSummary() {
        if (!statistics.isStatisticsEnabled()) {
            return;
        }

        System.out.println(
            "queryCount=" + statistics.getQueryExecutionCount()
        );
        System.out.println(
            "slowestQueryMs=" + statistics.getQueryExecutionMaxTime()
        );
        System.out.println(
            "slowestQuery=" + statistics.getQueryExecutionMaxTimeQueryString()
        );
        System.out.println(
            "entityFetchCount=" + statistics.getEntityFetchCount()
        );
        System.out.println(
            "collectionFetchCount=" + statistics.getCollectionFetchCount()
        );
        System.out.println(
            "secondLevelCacheHits=" + statistics.getSecondLevelCacheHitCount()
        );
        System.out.println(
            "secondLevelCacheMisses=" + statistics.getSecondLevelCacheMissCount()
        );
        System.out.println(
            "queryCacheHits=" + statistics.getQueryCacheHitCount()
        );
        System.out.println(
            "queryCacheMisses=" + statistics.getQueryCacheMissCount()
        );
    }
}
~~~

Đây là một component đọc số liệu Hibernate. Các con số là bộ đếm tích lũy của SessionFactory, không phải số liệu riêng của request đang chạy.

Một số method hữu ích:

| Method | Ý nghĩa |
|---|---|
| getQueryExecutionCount() | Tổng số query đã thực thi |
| getQueryExecutionMaxTime() | Thời gian lớn nhất của query |
| getQueryExecutionMaxTimeQueryString() | Query string tương ứng với thời gian lớn nhất |
| getEntityLoadCount() | Số entity được load |
| getEntityFetchCount() | Số entity được fetch |
| getCollectionLoadCount() | Số collection được load |
| getCollectionFetchCount() | Số collection được fetch |
| getPrepareStatementCount() | Số PreparedStatement được acquire |
| getSecondLevelCacheHitCount() | Số lần hit second-level cache |
| getSecondLevelCacheMissCount() | Số lần miss second-level cache |
| getQueryCacheHitCount() | Số lần hit query cache |
| getQueryCacheMissCount() | Số lần miss query cache |

Các bộ đếm entity/collection giúp nhận diện hành vi tải dữ liệu. Ví dụ, một endpoint trả về 20 đơn hàng nhưng phát sinh nhiều collection fetch có thể đang tải từng collection riêng lẻ.

### Statistics là số liệu toàn SessionFactory

Statistics tổng hợp hoạt động từ tất cả Session thuộc một SessionFactory. Nếu nhiều request chạy đồng thời, bộ đếm tăng từ tất cả request đó. Vì vậy:

- Không dùng getQueryExecutionCount() như query count của một request cụ thể.
- Không gọi statistics.clear() trong mỗi request để lấy số chênh lệch; thao tác đó reset số liệu dùng chung và làm sai kết quả của request khác.
- Có thể dùng snapshot/delta trong integration test đơn luồng hoặc môi trường kiểm thử cô lập.
- Với production, dùng trace hoặc instrumentation ở tầng JDBC để gắn query vào request/trace cụ thể.

## 7. Đo số lần và thời gian của một query cụ thể

Statistics.getQueryStatistics(queryString) trả về thống kê cho một query string HQL hoặc SQL. Đối tượng QueryStatistics cung cấp số lần thực thi, thời gian trung bình, tối đa, tối thiểu, tổng thời gian và số dòng ResultSet đã xử lý.

Ví dụ:

~~~java
import org.hibernate.SessionFactory;
import org.hibernate.stat.QueryStatistics;
import org.hibernate.stat.Statistics;

String hql =
    "select o from PurchaseOrder o where o.status = :status";

Statistics statistics = sessionFactory.getStatistics();

if (statistics.isStatisticsEnabled()) {
    QueryStatistics queryStats =
        statistics.getQueryStatistics(hql);

    long executions = queryStats.getExecutionCount();
    long averageMs = queryStats.getExecutionAvgTime();
    long maximumMs = queryStats.getExecutionMaxTime();
    long totalMs = queryStats.getExecutionTotalTime();
    long resultSetRows = queryStats.getExecutionRowCount();
}
~~~

Query string dùng để tra cứu phải khớp với chuỗi mà Hibernate thống kê. Các giá trị bind khác nhau thường vẫn thuộc cùng một query string.

getExecutionRowCount() là số dòng ResultSet tích lũy đã được xử lý cho query đó. Với query dùng stream() hoặc scroll(), Hibernate không nhất thiết biết tổng số dòng tại thời điểm thực thi nên thống kê này có thể không được cập nhật đầy đủ. Nếu cần đo số dòng thực tế được fetch qua JDBC, hãy instrument ResultSet.

Các số liệu trong QueryStatistics cũng tích lũy theo vòng đời SessionFactory. Chúng hữu ích để xếp hạng query thường chạy, query chậm hoặc query đọc nhiều dòng; chúng không phải latency p95/p99 của một endpoint.

## 8. Phân biệt query count với statement count

Một method repository không nhất thiết tương ứng với một SQL statement.

Ví dụ một method findAll(pageable) có thể thực thi:

1. Query lấy nội dung trang.
2. Count query để tính tổng số phần tử.

Một lần tải entity có quan hệ LAZY rồi truy cập từng quan hệ có thể tạo thêm nhiều SELECT. Một query có thể được lấy từ query cache hoặc entity cache và không phát sinh cùng số SQL như khi cache miss.

Cũng cần phân biệt:

- **Repository method count:** số lần gọi method repository.
- **Hibernate query execution count:** số query Hibernate ghi nhận đã thực thi.
- **JDBC statement/query count:** số lần thao tác SQL thực sự đi qua DataSource.
- **Database query count:** số câu lệnh database ghi nhận trong cửa sổ quan sát.

Các con số có thể khác nhau do cache, lazy loading, flush, batch, native JDBC và query nội bộ. Khi chẩn đoán số round-trip tới database, JDBC instrumentation là điểm đo trực tiếp hơn ORM-level query counter.

## 9. Đo thời gian SQL và thời gian fetch riêng biệt

Thời gian người dùng cảm nhận không chỉ là thời gian database chạy câu lệnh. Tổng latency có thể bao gồm:

- Chờ lấy connection từ pool.
- Gửi SQL và bind parameter.
- Database parse/plan/execute.
- Truyền dữ liệu qua mạng.
- JDBC fetch ResultSet theo từng đợt.
- Hibernate chuyển dòng SQL thành entity/DTO.
- Xử lý quan hệ, mapping và serialize response.

Một query có thời gian execute ngắn vẫn có thể chậm nếu trả hàng trăm nghìn dòng và mất nhiều thời gian fetch/materialize.

Datasource Micrometer phân tách các quan sát JDBC như CONNECTION, QUERY, FETCH và KEYS. Vì vậy, có thể nhìn thấy thời gian thực thi query và thời gian đọc ResultSet riêng. Khi QUERY nhanh nhưng FETCH dài, hãy kiểm tra số dòng, kích thước cột, fetch size, network và mapping entity.

## 10. Đo số dòng ResultSet bằng JDBC instrumentation

Hibernate Statistics phù hợp để quan sát ORM. Nếu cần số dòng thực sự được đọc qua JDBC và gắn với request/trace, có thể dùng Datasource Micrometer.

Dự án cung cấp module:

- datasource-micrometer: instrumentation JDBC nền tảng.
- datasource-micrometer-spring-boot: tự cấu hình cho Spring Boot.
- datasource-micrometer-opentelemetry: ánh xạ observation sang OpenTelemetry conventions.

Ví dụ dependency Maven cho Spring Boot theo tài liệu hiện hành:

~~~xml
<dependency>
    <groupId>net.ttddyy.observation</groupId>
    <artifactId>datasource-micrometer-spring-boot</artifactId>
    <version>2.3.0</version>
</dependency>
~~~

Hãy kiểm tra ma trận tương thích với phiên bản Spring Boot, Micrometer và Java của dự án; dùng BOM của thư viện nếu cần quản lý nhiều module cùng phiên bản.

Module Spring Boot tự instrument DataSource và đăng ký observation vào Micrometer infrastructure. Khi thêm registry/exporter phù hợp, các observation có thể đi tới metrics backend hoặc tracing backend.

Datasource Micrometer phân biệt:

| Observation | Ý nghĩa |
|---|---|
| CONNECTION | Lấy và đóng JDBC connection |
| QUERY | Thực thi câu lệnh |
| FETCH | Đọc dữ liệu từ ResultSet |
| KEYS | Đọc generated keys |

ResultSet observation có thể cung cấp số dòng đã đọc. Trong OpenTelemetry mapping, jdbc.row-count là số SQL rows của ResultSet span; jdbc.row-affected là số dòng bị tác động bởi executeUpdate, executeLargeUpdate hoặc batch DML.

Nếu tự tạo proxy bằng datasource-proxy, cần bật proxy ResultSet để instrument việc đọc từng dòng. Với Spring Boot module, kiểm tra cấu hình jdbc.includes để chọn loại observation cần thu thập; mặc định tài liệu hiện hành bao gồm CONNECTION, QUERY, KEYS và FETCH.

## 11. Phân biệt SQL rows, entity count và Page metadata

Ba giá trị sau không đồng nghĩa:

1. **SQL rows:** số dòng database/JDBC trả về.
2. **Java result size:** số object trong List, Set hoặc projection được Hibernate trả về.
3. **Page totalElements:** tổng số phần tử phù hợp với điều kiện lọc, có thể được tính bằng count query.

Ví dụ JOIN FETCH:

~~~sql
select
    o.id,
    i.id,
    i.product_name
from purchase_order o
left join order_item i on i.order_id = o.id
where o.id in (10, 11)
~~~

Giả sử hai đơn hàng có tổng cộng năm dòng hàng. Database có thể trả năm SQL rows, trong khi Hibernate ánh xạ thành hai root PurchaseOrder entity với các collection items tương ứng.

Vì vậy, SQL row count lớn hơn số root entity không nhất thiết là lỗi. Nhưng nếu JOIN nhiều collection, số dòng có thể tăng theo tích số lượng phần tử của các quan hệ, gây dữ liệu lặp và tăng chi phí truyền tải.

Với Page, getNumberOfElements() là số phần tử trong trang hiện tại; getTotalElements() là tổng số phần tử khớp điều kiện. Không dùng totalElements làm số dòng SQL của query nội dung vì Spring Data có thể chạy một count query riêng.

## 12. Phát hiện N+1 bằng query count

N+1 xảy ra khi ứng dụng tải một danh sách entity bằng một query, rồi truy cập một quan hệ LAZY và phát sinh thêm một query cho từng entity.

Ví dụ:

~~~java
List<PurchaseOrder> orders = repository.findAll();

for (PurchaseOrder order : orders) {
    System.out.println(order.getItems().size());
}
~~~

Nếu có 40 đơn hàng, có thể thấy:

- 1 SELECT lấy danh sách đơn hàng.
- 40 SELECT lấy collection items cho từng đơn hàng.

Tổng cộng khoảng 41 query, tùy mapping và cache.

Dấu hiệu nhận biết:

- Query count tăng gần tuyến tính theo số entity trong danh sách.
- Cùng một SQL được thực thi nhiều lần với parameter khác nhau.
- collectionFetchCount hoặc entityFetchCount tăng nhanh.
- Endpoint chạy nhanh với vài bản ghi nhưng chậm khi danh sách lớn.

Cách xử lý có thể gồm:

- Dùng JOIN FETCH cho quan hệ cần đọc ngay.
- Dùng @EntityGraph để khai báo fetch plan theo use case.
- Dùng batch fetching để gom nhiều lazy loads thành ít query hơn.
- Dùng DTO projection khi chỉ cần một số trường.
- Tránh truy cập quan hệ LAZY ngoài transaction hoặc trong vòng lặp mà không có kế hoạch fetch.

Không bật EAGER cho mọi quan hệ để chữa N+1. EAGER có thể làm query khác tải quá nhiều dữ liệu và tạo N+1 ở một đường truy cập khác.

## 13. Quan sát cache cùng với query count

Spring Data JPA thường chạy trên Hibernate, nơi có nhiều lớp cache:

- **First-level cache:** persistence context của một EntityManager/Session. Entity đã managed có thể được tái sử dụng trong cùng persistence context.
- **Second-level cache:** cache dùng chung giữa các Session, nếu được cấu hình và entity/collection được phép cache.
- **Query cache:** cache kết quả của query có bật cache; thường cần phối hợp với second-level cache để tái sử dụng entity state.

Hibernate Statistics cung cấp các bộ đếm hit, miss và put cho query cache, second-level cache và các vùng cache. Dùng chúng để kiểm tra cache có thực sự giảm tải database hay không.

Một số nguyên tắc:

- Query cache hit không đồng nghĩa toàn bộ entity state đều được lấy từ query cache.
- Entity second-level cache hit có thể giảm SELECT lấy entity state.
- First-level cache chỉ sống trong persistence context hiện tại; không dùng nó như cache dùng chung giữa request.
- Cache miss có thể là hành vi bình thường khi dữ liệu mới hoặc cache vừa bị invalidate.
- Hit rate cao không tự động chứng minh endpoint nhanh; query plan, row count và thời gian fetch vẫn cần được quan sát.

Khi thay đổi cache strategy, so sánh cùng một workload trước và sau thay đổi: query count, query time, cache hit/miss, số dòng đọc và tỷ lệ dữ liệu được tái sử dụng.

## 14. Tìm nguyên nhân query chậm bằng execution plan

Sau khi tìm được SQL chậm, lấy SQL thực tế và parameter mẫu từ log/trace. Sau đó dùng công cụ của database để xem execution plan.

Tùy hệ quản trị, có thể dùng:

- PostgreSQL: EXPLAIN hoặc EXPLAIN (ANALYZE, BUFFERS).
- MySQL: EXPLAIN hoặc EXPLAIN ANALYZE.
- SQL Server: Actual Execution Plan và Query Store.
- Oracle: EXPLAIN PLAN và SQL Monitor.

EXPLAIN ANALYZE thường thực thi query thật trên database. Hãy cân nhắc tác động khi chạy với query ghi, query tốn tài nguyên hoặc dữ liệu production. Ưu tiên môi trường staging/replica phù hợp hoặc kế hoạch được DBA phê duyệt.

Quan sát:

- Sequential/table scan trên bảng lớn.
- Index scan có chọn lọc kém.
- JOIN tạo nhiều dòng trung gian.
- Sort hoặc hash operation dùng nhiều bộ nhớ/temp space.
- Ước lượng row count lệch xa số dòng thực tế.
- Lock wait hoặc I/O cao.
- Index không khớp điều kiện lọc/sắp xếp.

Không thêm index chỉ dựa trên tên cột xuất hiện trong WHERE. Hãy kiểm tra execution plan, cardinality, tần suất query và chi phí ghi do index mới tạo ra.

## 15. Tạo metrics và trace có thể dùng trong production

Khi đưa số liệu vào Micrometer/Prometheus hoặc tracing backend:

- Dùng tên query ổn định hoặc dạng normalized SQL để nhóm metric.
- Giữ tag có cardinality thấp, ví dụ datasource, operation, query name hoặc repository method.
- Không dùng raw SQL có literal, bind parameter, email, user ID hoặc order ID làm metric label.
- Nếu cần parameter để debug, lưu trong trace/log đã masking và giới hạn quyền truy cập.
- Thu thập histogram để tính p50/p95/p99 thay vì chỉ theo dõi average.
- Theo dõi error count, timeout, connection acquisition và query/fetch latency cùng nhau.
- Đặt sampling cho trace và retention cho log phù hợp với tải.

Metric phải giúp so sánh xu hướng mà không tạo hàng triệu time series. Chi tiết theo request phù hợp hơn với trace/span; metric nên dùng dimension có cardinality thấp.

## 16. Một quy trình điều tra thực tế

Khi endpoint tìm kiếm đơn hàng chậm:

1. Ghi lại request, thời gian tổng và trace ID.
2. Đếm JDBC QUERY spans trong trace để biết số lần round-trip.
3. Xem QUERY duration và FETCH duration riêng.
4. Xem jdbc.row-count để biết số dòng ResultSet được đọc.
5. Đối chiếu Hibernate Statistics để xem entity/collection fetch và cache hit/miss.
6. Tìm SQL lặp lại nhiều lần hoặc query vượt slow threshold.
7. Kiểm tra Page có phát sinh count query hay không.
8. Lấy execution plan của SQL chậm và kiểm tra index/join/sort.
9. Thử fetch plan, projection, batch size hoặc index trên môi trường kiểm thử.
10. Chạy lại cùng workload và so sánh query count, p95/p99, row count, cache metrics và kết quả nghiệp vụ.

Ví dụ dấu hiệu và hướng điều tra:

| Dấu hiệu | Khả năng cần kiểm tra |
|---|---|
| Nhiều query giống nhau với ID khác nhau | N+1 hoặc truy cập LAZY trong vòng lặp |
| Ít query nhưng nhiều ResultSet rows | JOIN tạo dòng lặp hoặc query trả quá nhiều dữ liệu |
| Query execute nhanh nhưng FETCH lâu | Kết quả lớn, fetch size, mạng hoặc mapping |
| Query count thấp nhưng một query rất chậm | Execution plan, index, lock, sort hoặc I/O |
| Query count tăng mạnh khi cache cold | Cache miss, cache chưa warm hoặc cache key không ổn định |
| Page endpoint luôn chạy thêm query | Count query để tính totalElements |
| SQL log cho thấy nhiều SELECT theo association | Fetch plan chưa phù hợp hoặc N+1 |

## 17. Lỗi thường gặp khi đo lường

### 17.1. Dùng Statistics global như số liệu một request

Các bộ đếm Hibernate gắn với SessionFactory và cộng dồn từ nhiều session. Lấy chênh lệch trước/sau một request trong production có thể lẫn hoạt động của request khác.

Dùng JDBC spans/observations có trace context nếu cần số liệu per-request.

### 17.2. Chỉ đo query execute time

Một query trả hàng trăm nghìn dòng có thể mất ít thời gian để bắt đầu thực thi nhưng mất lâu để fetch và map. Đo QUERY và FETCH riêng, đồng thời theo dõi số dòng.

### 17.3. Nhầm row count với số entity

JOIN có thể trả nhiều SQL rows cho một root entity. Page totalElements cũng là tổng kết quả logic, không phải số dòng của query nội dung. Hãy ghi rõ metric đang đo lớp nào.

### 17.4. Bật bind logging trong production mà không masking

Bind log có thể chứa dữ liệu nhạy cảm. Chỉ bật khi cần, giới hạn phạm vi và thời gian, bảo vệ log và tắt sau khi điều tra.

### 17.5. Chỉ nhìn average

Average có thể che khuất các request rất chậm. Theo dõi histogram/percentile và query max cùng với throughput.

### 17.6. Reset Statistics trong ứng dụng đang chạy

statistics.clear() reset bộ đếm toàn SessionFactory. Gọi nó từ request có thể làm số liệu của các request khác mất tính liên tục. Chỉ reset trong test cô lập hoặc quy trình vận hành được kiểm soát.

### 17.7. Cho rằng cache hit luôn tốt

Cache hit có thể giảm SQL nhưng cache có chi phí bộ nhớ, invalidation và dữ liệu cũ nếu cấu hình sai. Đánh giá hit/miss cùng độ mới dữ liệu, thời gian và tính đúng đắn.

### 17.8. Tối ưu query mà không xem execution plan

Thêm index hoặc đổi fetch strategy khi chưa xem SQL/plan có thể làm workload khác chậm hơn. Xác nhận bằng dữ liệu và workload gần production.

## 18. Kiểm thử query count và số dòng trong integration test

Có thể dùng Hibernate Statistics trong test để xác nhận một use case không phát sinh query ngoài dự kiến. Chỉ dùng snapshot trong test cô lập để tránh các thao tác setup/teardown làm sai bộ đếm.

Ví dụ:

~~~java
@DataJpaTest
class OrderQueryCountTest {

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Autowired
    private PurchaseOrderRepository repository;

    @Test
    void loadsOrdersWithoutUnexpectedCollectionQueries() {
        SessionFactory sessionFactory =
            entityManagerFactory.unwrap(SessionFactory.class);

        Statistics statistics = sessionFactory.getStatistics();
        statistics.setStatisticsEnabled(true);
        statistics.clear();

        repository.findRecentOrders();

        long queryCount = statistics.getQueryExecutionCount();
        long collectionFetches = statistics.getCollectionFetchCount();

        assertThat(queryCount).isLessThanOrEqualTo(2);
        assertThat(collectionFetches).isZero();
    }
}
~~~

Đây là test minh họa. Cần seed dữ liệu, flush/clear persistence context trước đoạn đo nếu test setup đã chạy query; cần chọn assertion theo fetch plan thực tế của repository. Không copy ngưỡng 2 sang mọi use case. Với query có paging, count query có thể là một lần thực thi hợp lệ.

Nếu kiểm tra số dòng ResultSet, dùng QueryStatistics.getExecutionRowCount() cho query được Hibernate thống kê hoặc ResultSet observation từ JDBC instrumentation. Không suy ra số SQL rows chỉ từ List.size().

## 19. Checklist quan sát trước khi tối ưu

- SQL log cho thấy câu lệnh thật Hibernate gửi đi.
- Bind parameter đã được xác nhận trong môi trường an toàn.
- Query count được đo đúng lớp và đúng phạm vi request/test.
- Thời gian QUERY và FETCH được phân biệt.
- Có số SQL rows và số entity/DTO trả về để so sánh.
- N+1 được kiểm tra bằng query lặp và collection/entity fetch count.
- Cache hit/miss được đọc cùng với query count và dữ liệu.
- Slow query có SQL comment hoặc trace để truy về use case.
- Execution plan đã được xem trước khi thay index hoặc rewrite query.
- Metrics có p95/p99, error/timeout và cardinality được kiểm soát.
- Test xác nhận query count và kết quả nghiệp vụ sau tối ưu.

## 20. Ghi nhớ

- Hibernate SQL logging giúp xem SQL và bind parameter; dùng TRACE có kiểm soát vì log có thể chứa dữ liệu nhạy cảm.
- hibernate.generate_statistics=true bật Hibernate Statistics; các bộ đếm gắn với SessionFactory và cộng dồn từ nhiều session.
- Statistics cung cấp query count, max query time, entity/collection fetch và cache hit/miss.
- QueryStatistics cung cấp execution count, average/max/min/total time và số ResultSet rows đã xử lý cho một query string.
- Stream/scroll có thể không cập nhật đầy đủ row count trong Hibernate QueryStatistics.
- Hibernate Statistics không thay thế metric per-request; dùng JDBC instrumentation và trace để gắn SQL với request.
- Datasource Micrometer phân biệt CONNECTION, QUERY, FETCH và KEYS; ResultSet observation có thể cung cấp jdbc.row-count.
- jdbc.row-affected phản ánh số dòng bị tác động bởi DML, khác số dòng SELECT trả về.
- SQL rows, Java entity count, Page.getNumberOfElements() và Page.getTotalElements() là các đại lượng khác nhau.
- QUERY execute nhanh không có nghĩa endpoint nhanh nếu FETCH, mapping hoặc serialization tốn thời gian.
- Query count tăng theo số entity là dấu hiệu cần kiểm tra N+1.
- Đánh giá cache bằng hit/miss cùng số query, thời gian, row count và tính đúng đắn.
- Dùng execution plan và workload đại diện trước khi thêm index hoặc đổi fetch strategy.

Quan sát query count, SQL time và returned rows giúp chuyển việc tối ưu Spring Data JPA từ phỏng đoán sang đo lường. Hãy xác định rõ đang đo ở tầng ORM, JDBC hay database, liên kết số liệu với request và kiểm chứng mọi thay đổi trên workload thực tế.

## Tài liệu tham khảo

- [Hibernate ORM 6.6 — Logging the Generated SQL, Statistics and Slow Queries](https://docs.hibernate.org/orm/6.6/introduction/html_single/)
- [Hibernate 7.4 Javadoc — Statistics](https://docs.hibernate.org/orm/7.4/javadocs/org/hibernate/stat/Statistics.html)
- [Hibernate 7.4 Javadoc — QueryStatistics](https://docs.hibernate.org/orm/7.4/javadocs/org/hibernate/stat/QueryStatistics.html)
- [Datasource Micrometer — Reference Documentation](https://jdbc-observations.github.io/datasource-micrometer/docs/current/docs/html/)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)