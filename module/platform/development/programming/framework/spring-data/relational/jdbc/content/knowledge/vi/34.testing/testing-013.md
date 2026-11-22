# Đo truy vấn và phát hiện hồi quy hiệu năng

## 1. Vì sao cần đo truy vấn trong ứng dụng Spring Data JDBC?

Một repository method có thể chỉ gồm một dòng Java:

~~~java
Optional<PurchaseOrder> order = orders.findById(id);
~~~

Nhưng để thực hiện lời gọi đó, Spring Data JDBC có thể cần đọc hàng aggregate root, tải các entity được tham chiếu, chạy thêm SELECT cho collection hoặc property path, chuyển đổi ResultSet thành object và gọi callback/event theo cấu hình.

Vì vậy, thời gian của một repository method không chỉ phụ thuộc vào câu SELECT đầu tiên. Một thay đổi nhỏ trong mapping, query method, index hoặc cấu trúc aggregate có thể làm số câu SQL tăng lên, khiến truy vấn chậm hơn hoặc tiêu thụ nhiều connection hơn.

Hồi quy hiệu năng thường không xuất hiện dưới dạng lỗi chức năng. Ứng dụng vẫn trả kết quả đúng nhưng:

- Một request trước đây chạy 3 SELECT, nay chạy 40 SELECT.
- Một truy vấn chuyển từ index scan sang full table scan.
- Thời gian p95 tăng từ vài chục lên vài trăm mili giây.
- Một màn hình tải danh sách aggregate gây nhiều query lặp theo từng hàng.
- Connection pool thường xuyên hết connection dù số request không tăng nhiều.
- Batch job mất nhiều thời gian hơn sau khi thêm một quan hệ hoặc callback.

Muốn phát hiện sớm, cần đo ở nhiều lớp: số lần gọi JDBC, thời gian từng query, execution plan của database, thời gian toàn use case và trạng thái connection pool.

## 2. Những chỉ số cần theo dõi

Không nên chỉ nhìn vào thời gian của một câu SQL. Một use case có thể chạy nhiều câu SQL nhanh nhưng tổng thời gian vẫn lớn vì số lần gọi quá nhiều.

| Chỉ số | Ý nghĩa | Phát hiện được |
| --- | --- | --- |
| Query count | Số lần thực thi SELECT/INSERT/UPDATE/DELETE | N+1, query thừa, thay đổi số round trip |
| Query duration | Thời gian database thực thi từng câu lệnh | Câu SQL chậm, lock wait hoặc plan xấu |
| Total database time | Tổng thời gian thực thi các câu SQL trong một use case | Tổng chi phí database |
| Rows returned/affected | Số hàng trả về hoặc bị thay đổi | Query đọc quá nhiều dữ liệu hoặc UPDATE không như dự kiến |
| Execution plan | Cách database quét bảng, dùng index và JOIN | Full scan, sort lớn, join tốn kém |
| Buffer/IO metrics | Lượng dữ liệu đọc từ cache hoặc storage | Query gây I/O lớn |
| Connection pool active/idle | Số connection đang dùng và còn trống | Pool contention, transaction giữ connection lâu |
| End-to-end latency | Thời gian toàn service/API | Ảnh hưởng thực tế người dùng nhận được |
| Throughput | Số request hoặc item xử lý mỗi giây | Năng lực xử lý tổng thể |
| p50/p95/p99 | Các percentile của thời gian phản hồi | Độ trễ điển hình và các trường hợp chậm |

Ví dụ một request có tổng thời gian 250 ms:

~~~text
Thời gian service: 250 ms
  Query A: 12 ms
  Query B: 9 ms
  Query C: 11 ms
  Query D: 8 ms
  Query E: 10 ms
  Query F: 9 ms
  ...
  Mapping, callback, xử lý Java, network và các phần khác: phần còn lại
~~~

Mỗi query riêng lẻ có vẻ nhanh, nhưng nếu request chạy hàng chục query, tổng thời gian database và round trip có thể trở thành nút thắt.

## 3. Đo SQL được Spring Data JDBC thực thi

### 3.1. Bật SQL logging tạm thời

Spring JDBC sử dụng JdbcTemplate để thực thi nhiều thao tác persistence. Có thể bật log để quan sát SQL:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core.JdbcTemplate: DEBUG
    org.springframework.jdbc.core.StatementCreatorUtils: TRACE
~~~

JdbcTemplate ở mức DEBUG giúp nhìn thấy câu SQL được thực thi. StatementCreatorUtils ở mức TRACE có thể cho biết cách bind tham số.

Chỉ bật log chi tiết trong môi trường phát triển hoặc một khoảng thời gian chẩn đoán có kiểm soát. Log tham số có thể chứa email, số điện thoại, địa chỉ, token hoặc dữ liệu cá nhân. Không ghi dữ liệu nhạy cảm vào log production nếu chưa có cơ chế che hoặc mã hóa phù hợp.

### 3.2. Log SQL không thay thế query metrics

Log hữu ích để biết câu SQL cụ thể, nhưng khó trả lời tự động các câu hỏi:

- Một service method đã gọi bao nhiêu SELECT?
- Query nào chiếm nhiều tổng thời gian nhất?
- Số query có tăng khi danh sách kết quả lớn hơn không?
- Có câu SQL nào vượt ngưỡng thời gian không?
- Một JDBC batch chứa bao nhiêu statement?

Để đo các chỉ số đó, có thể bọc DataSource bằng công cụ theo dõi JDBC.

## 4. Dùng datasource-proxy để đếm và đo query

**datasource-proxy** bọc một DataSource và cho phép lắng nghe trước/sau khi JDBC thực thi câu lệnh. Thư viện có các listener hỗ trợ:

- Ghi log câu SQL và tham số.
- Phát hiện query vượt ngưỡng thời gian.
- Đếm SELECT, INSERT, UPDATE, DELETE.
- Đo tổng thời gian query.
- Theo dõi batch execution và connection ID.
- Viết QueryExecutionListener riêng để thu thập metric tùy ứng dụng.

### 4.1. Thêm dependency

Với Gradle:

~~~groovy
runtimeOnly("net.ttddyy:datasource-proxy:<version>")
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>net.ttddyy</groupId>
    <artifactId>datasource-proxy</artifactId>
    <version><!-- chọn phiên bản phù hợp với JDK và ứng dụng --></version>
    <scope>runtime</scope>
</dependency>
~~~

Không chép một phiên bản cố định từ ví dụ cũ vào dự án. Chọn phiên bản tương thích với Java và dependency management hiện tại.

### 4.2. Bọc DataSource

Ví dụ tạo proxy:

~~~java
DataSource monitoredDataSource =
        ProxyDataSourceBuilder
                .create(actualDataSource)
                .name("applicationDataSource")
                .countQuery()
                .logSlowQueryBySlf4j(500, TimeUnit.MILLISECONDS)
                .build();
~~~

Đưa DataSource được bọc vào Spring context để JdbcTemplate, Spring Data JDBC và transaction manager cùng sử dụng. Nếu chỉ tạo một proxy cục bộ mà repository vẫn dùng DataSource gốc, các query của repository sẽ không được đo.

### 4.3. Đọc query count

Sau khi gọi use case:

~~~java
QueryCountHolder.clear();

orderService.loadOrderSummary(orderId);

QueryCount count = QueryCountHolder.getGrandTotal();

long selectCount = count.getSelect();
long updateCount = count.getUpdate();
long totalCount = count.getTotal();
long totalQueryTime = count.getTime();

QueryCountHolder.clear();
~~~

Các metric có thể dùng trong integration test hoặc ghi vào log để so sánh giữa các lần chạy. QueryCountHolder mặc định dùng thread-local strategy; vì vậy, số liệu được thu thập trên thread hiện tại. Nếu use case dispatch database work sang thread khác, cần chọn strategy hoặc listener phù hợp để không bỏ sót query.

### 4.4. Đếm query và đếm statement trong batch không giống nhau

Một PreparedStatement có thể được thực thi bằng executeBatch() với nhiều bộ tham số. Công cụ quan sát có thể ghi nhận một lần thực thi batch, đồng thời cung cấp batch size cho biết có bao nhiêu bộ lệnh được gửi.

Khi đọc metric, hãy phân biệt:

- Số lần gọi JDBC execute.
- Số query logic trong batch.
- Số bộ tham số được bind.
- Số hàng database thực sự bị ảnh hưởng.

Không so sánh trực tiếp query count của batch execution với query count của các câu SQL đơn lẻ mà không hiểu cách công cụ ghi nhận batch.

### 4.5. Viết listener cho slow query

QueryExecutionListener nhận thông tin trước và sau khi query chạy. Sau khi thực thi, ExecutionInfo có thể cung cấp thời gian thực thi, kết quả và exception nếu có.

Ví dụ ý tưởng:

~~~java
long thresholdMillis = 500;

ProxyDataSourceBuilder builder =
        ProxyDataSourceBuilder.create(actualDataSource)
                .afterQuery((execution, queries) -> {
                    if (execution.getElapsedTime() >= thresholdMillis) {
                        // Ghi query fingerprint, datasource, elapsed time
                        // và trạng thái thành công/thất bại.
                    }
                });
~~~

Trong production, nên ghi query fingerprint hoặc câu SQL đã chuẩn hóa cùng thông tin thời gian. Tránh ghi toàn bộ giá trị bind nếu chúng có thể chứa dữ liệu nhạy cảm.

## 5. Phân biệt metric connection pool và metric từng query

Spring Boot Actuator có thể tự instrument các DataSource và công bố metric với prefix jdbc.connections. Những metric này mô tả trạng thái connection pool:

- Số connection đang active.
- Số connection đang idle.
- Số connection tối đa được phép.
- Số connection tối thiểu được giữ.

Nếu dùng HikariCP, còn có các metric riêng với prefix hikaricp.

Các metric pool giúp phát hiện:

- Connection pool thường xuyên gần mức tối đa.
- Request phải chờ connection.
- Transaction giữ connection lâu.
- Pool có cấu hình quá nhỏ hoặc quá lớn.

Nhưng metric pool không tự cho biết câu SELECT nào mất 800 ms hoặc service method nào tạo 30 query. Muốn đo từng query, cần instrumentation JDBC như datasource-proxy, P6Spy hoặc giải pháp quan sát query tương đương.

| Công cụ | Phạm vi đo chính |
| --- | --- |
| Spring Boot Actuator DataSource metrics | Trạng thái pool và connection |
| HikariCP metrics | Active/idle/pending connection, thời gian lấy connection và các chỉ số pool |
| datasource-proxy | Query count, query duration, slow query, batch metadata và listener |
| P6Spy | Ghi log SQL đã thực thi và thời gian theo cấu hình |
| Database statistics | Query fingerprint, execution statistics, buffer/IO, lock và plan tùy engine |

Không dùng một metric pool để kết luận rằng database query đang nhanh. Một pool có nhiều connection active có thể do nhiều request đang chờ query, transaction dài hoặc ứng dụng đang giữ connection quá lâu.

## 6. Phát hiện N+1 và query count tăng bất thường

N+1 là tình huống một truy vấn tải danh sách root, sau đó phát sinh thêm một truy vấn cho mỗi root hoặc cho từng phần tử trong danh sách.

Ví dụ một màn hình tải 50 đơn hàng:

~~~text
SELECT các purchase_order
SELECT các lines của order 1
SELECT các lines của order 2
SELECT các lines của order 3
...
SELECT các lines của order 50
~~~

Nếu query count tăng tuyến tính theo số đơn hàng, cần kiểm tra xem ứng dụng có đang tải quan hệ theo từng aggregate hay không.

Spring Data JDBC không dùng lazy loading như JPA. Khi tải aggregate, framework sử dụng mapping và các truy vấn quan hệ theo aggregate/property path. Số câu SQL thực tế phụ thuộc thao tác, kiểu quan hệ và cách query được khai báo. Vì vậy, hãy đo trên use case thật thay vì mặc định rằng mọi findAll đều tạo N+1 hoặc mọi collection đều được tải bằng một JOIN.

### 6.1. So sánh query count theo kích thước dữ liệu

Một cách phát hiện hồi quy là chạy cùng use case với hai bộ dữ liệu:

| Số aggregate root | Số SELECT đo được |
| ---: | ---: |
| 1 | 2 |
| 10 | 11 |
| 50 | 51 |

Nếu query count tăng gần một câu cho mỗi aggregate, có thể đang tồn tại query lặp theo từng root. Đây là tín hiệu để điều tra, không phải bằng chứng duy nhất: một số use case có chủ đích tải từng aggregate và số query có thể tăng theo dữ liệu.

### 6.2. Kiểm tra query count trong integration test

Ví dụ:

~~~java
@DataJdbcTest
class OrderRepositoryQueryCountTest {

    @Autowired
    OrderRepository orders;

    @Test
    void loadingOrdersShouldStayWithinQueryBudget() {
        // Chuẩn bị dữ liệu gồm nhiều order và order line.

        QueryCountHolder.clear();

        List<PurchaseOrder> result =
                orders.findByStatus(OrderStatus.OPEN);

        QueryCount count = QueryCountHolder.getGrandTotal();

        assertThat(result).hasSize(20);
        assertThat(count.getSelect()).isLessThanOrEqualTo(5);

        QueryCountHolder.clear();
    }
}
~~~

Ví dụ giả định DataSource của test đã được bọc bằng datasource-proxy và ngưỡng 5 được xác định từ hành vi mong muốn của repository. Không copy một con số tùy ý vào test thực tế. Đo baseline trước, sau đó đặt budget có lý do.

Nên kiểm tra cả số lượng kết quả và query count. Một test chỉ assert query count có thể pass nếu query bị thiếu dữ liệu hoặc trả về kết quả không đầy đủ.

## 7. Phân tích execution plan

Khi một query chậm, bước tiếp theo là xem database thực hiện nó như thế nào.

Execution plan cho biết database dự kiến hoặc thực tế:

- Quét toàn bảng hay dùng index.
- Chọn index nào.
- Dùng nested loop, hash join hay merge join.
- Số hàng dự kiến và số hàng thực tế.
- Có sort, aggregate hoặc temporary operation lớn không.
- Có đọc nhiều block từ storage không.

### 7.1. EXPLAIN trên PostgreSQL

Ví dụ:

~~~sql
EXPLAIN
SELECT id, status, created_at
FROM purchase_order
WHERE status = 'OPEN'
ORDER BY created_at DESC
LIMIT 50;
~~~

Plan cho biết node scan, index và chi phí ước lượng. Nếu muốn số liệu thực tế:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, status, created_at
FROM purchase_order
WHERE status = 'OPEN'
ORDER BY created_at DESC
LIMIT 50;
~~~

ANALYZE thực sự thực thi statement và bổ sung thời gian, số hàng thực tế cho từng node. BUFFERS cho biết block được lấy từ cache, đọc, ghi hoặc làm bẩn.

Chú ý: EXPLAIN ANALYZE không chỉ lập kế hoạch. Với SELECT, truy vấn thực sự được chạy; với INSERT/UPDATE/DELETE, các thay đổi cũng được thực thi. Nếu thử nghiệm DML trên PostgreSQL và không muốn giữ thay đổi, có thể chạy trong transaction rồi ROLLBACK:

~~~sql
BEGIN;
EXPLAIN ANALYZE
UPDATE purchase_order
SET status = 'ARCHIVED'
WHERE status = 'COMPLETED';
ROLLBACK;
~~~

Rollback không đảo ngược mọi side effect bên ngoài transaction, chẳng hạn một số hành động do trigger gọi ra hệ thống khác. Chỉ dùng trên môi trường thử nghiệm và hiểu rõ trigger đang chạy.

### 7.2. Đọc các dấu hiệu quan trọng

| Dấu hiệu trong plan | Điều cần kiểm tra |
| --- | --- |
| Seq Scan trên bảng lớn | Predicate có chọn lọc không, index có phù hợp không, planner có đủ statistics không |
| Index Scan/Index Only Scan | Index có đúng thứ tự cột và bao phủ query không |
| Actual Rows khác xa Plan Rows | Statistics cũ, phân bố dữ liệu lệch hoặc điều kiện có selectivity khó ước lượng |
| Nested Loop với số loops lớn | Inner side có bị chạy lặp quá nhiều không |
| Sort/Hash dùng nhiều memory hoặc temp | Có cần index, giới hạn tập dữ liệu hoặc thay đổi query không |
| Buffers read cao | Query đọc nhiều page từ storage |
| Rows Removed by Filter cao | Predicate đang lọc sau khi đọc quá nhiều hàng |

Không kết luận rằng Seq Scan luôn xấu. Với bảng nhỏ hoặc query trả về phần lớn hàng, sequential scan có thể là plan tốt nhất. Mục tiêu là kiểm tra plan có phù hợp dữ liệu và workload hay không.

### 7.3. Cú pháp theo database

EXPLAIN không phải một câu lệnh SQL chuẩn có cú pháp giống nhau ở mọi engine. PostgreSQL, MySQL, SQL Server và Oracle có công cụ xem plan riêng. Hãy dùng tài liệu của database production.

## 8. Đo hiệu năng của Spring Data JDBC thay vì chỉ đo SQL

Một repository method còn có chi phí ngoài database:

- Chờ lấy connection từ pool.
- Chuẩn bị statement và bind tham số.
- Chờ network round trip.
- Chuyển đổi kiểu dữ liệu.
- Tạo aggregate root và entity con.
- Chạy callback hoặc event listener.
- Xử lý dữ liệu trong Java.

Vì vậy, hãy đo cả hai lớp:

1. **Database time:** tổng thời gian các câu SQL.
2. **Application time:** thời gian từ lúc gọi service/repository đến khi nhận kết quả.

Nếu database time thấp nhưng application time cao, hãy kiểm tra mapping, callback, xử lý Java, connection acquisition và network. Nếu query time cao, xem execution plan, lock wait, I/O và index.

### 8.1. Đo percentile

Giả sử kết quả benchmark:

| Chỉ số | Trước thay đổi | Sau thay đổi |
| --- | ---: | ---: |
| p50 | 35 ms | 32 ms |
| p95 | 90 ms | 160 ms |
| p99 | 180 ms | 420 ms |
| Query count/request | 4 | 18 |

Thời gian trung bình có thể vẫn trông ổn, nhưng p95/p99 và query count đã xấu đi. Hãy xem phân phối thời gian thay vì chỉ nhìn average.

### 8.2. Warm-up và chạy lặp

Một phép đo duy nhất dễ bị ảnh hưởng bởi:

- JVM chưa JIT compile.
- Connection pool vừa khởi tạo.
- Database cache chưa nóng.
- OS page cache.
- Background job hoặc hoạt động khác trên database.
- Test data quá nhỏ.

Nên chạy warm-up, thực hiện nhiều lần đo, dùng cùng môi trường và báo percentile. Nếu muốn đo cold-start, hãy thiết kế một kịch bản riêng thay vì trộn cold và warm run vào cùng một con số.

## 9. Kiểm thử trên database gần production

**@DataJdbcTest** hữu ích cho repository test. Spring Boot tự cấu hình DataSource, JdbcTemplate và Spring Data JDBC repositories. Theo mặc định, test slice này dùng embedded database nếu có và mỗi test chạy trong transaction được rollback khi kết thúc.

Embedded database phù hợp để kiểm tra mapping cơ bản, nhưng không đảm bảo execution plan, index behavior, collation, lock hoặc kiểu dữ liệu giống database production.

Nếu production dùng PostgreSQL, MySQL hoặc SQL Server, hãy chạy integration/performance test trên cùng engine và phiên bản gần tương ứng. Testcontainers có thể khởi chạy database thật trong container để kiểm tra:

- SQL được sinh bởi Spring Data JDBC.
- Index và execution plan.
- Kiểu dữ liệu, JSON, timestamp và collation.
- Lock, isolation và transaction.
- Query count với mapping aggregate thực tế.

### 9.1. @DataJdbcTest và transaction test

**@DataJdbcTest** mặc định bao test trong transaction và rollback khi test kết thúc. Điều này thuận tiện cho test repository và query count.

Nếu mục tiêu là đo commit latency hoặc hành vi transaction thật, transaction ngoài do test framework tạo có thể làm kết quả khác với production. Có thể tắt transaction test bằng propagation phù hợp hoặc viết test service transaction riêng.

### 9.2. Dùng dữ liệu đại diện

Một bảng chỉ có 20 hàng không thể chứng minh index sẽ hiệu quả với 20 triệu hàng. Test dataset nên phản ánh:

- Số hàng và số child row thực tế.
- Phân bố status, timestamp và khóa tìm kiếm.
- Tỷ lệ NULL và duplicate.
- Số lượng aggregate có collection lớn.
- Tỷ lệ đọc/ghi.
- Các giá trị tham số thường gặp và các giá trị hiếm.

Không chỉ tạo nhiều hàng ngẫu nhiên. Phân bố dữ liệu và selectivity có thể thay đổi execution plan.

## 10. Phát hiện hồi quy bằng test và baseline

Hồi quy hiệu năng có thể xuất hiện khi:

- Thêm một property collection vào aggregate.
- Thay derived query bằng custom query.
- Đổi mapping hoặc converter.
- Thêm callback chạy thêm một query.
- Xóa hoặc đổi index.
- Thay điều kiện WHERE hoặc ORDER BY.
- Thay đổi số lượng dữ liệu trung bình mỗi aggregate.
- Nâng cấp Spring Data JDBC hoặc JDBC driver.

Một quy trình phát hiện hồi quy nên có nhiều lớp.

### 10.1. Test query count

Đặt budget cho những use case quan trọng:

- Tải chi tiết một aggregate.
- Tải danh sách có phân trang.
- Tạo aggregate có collection.
- Cập nhật aggregate đã tồn tại.
- Chạy một thao tác bulk.

Query count thường ổn định hơn thời gian tuyệt đối trong CI. Nếu số query tăng đột ngột, test có thể cảnh báo ngay cả khi máy CI đủ nhanh để che giấu vấn đề.

### 10.2. Test giới hạn dữ liệu trả về

Kiểm tra:

- Page size có được áp dụng không.
- Query có trả thừa cột hoặc hàng không.
- Collection có bị tải khi use case không cần không.
- Projection có thực sự chỉ lấy các trường cần thiết không.

Một query có thể chạy nhanh trên dataset nhỏ nhưng trả về hàng trăm nghìn row không cần thiết.

### 10.3. Test execution plan có mục tiêu

Không nên snapshot toàn bộ execution plan thành một chuỗi cứng cho mọi CI run. Plan có thể thay đổi theo version database, statistics và dữ liệu. Thay vào đó:

- Kiểm tra query có dùng index cần thiết khi điều kiện và dữ liệu phù hợp.
- Theo dõi actual rows, loops, buffers và execution time.
- So sánh plan trên database và dataset được cố định.
- Điều tra thay đổi lớn thay vì bắt mọi thay đổi nhỏ đều làm test fail.

### 10.4. Performance test có ngưỡng

Với luồng quan trọng, có thể đặt budget:

- p95 latency không vượt ngưỡng đã thống nhất.
- Query count không vượt mức dự kiến.
- Throughput không giảm quá tỷ lệ cho phép.
- Connection pool không liên tục chạm mức tối đa.

Ngưỡng cần được xác lập từ baseline thực tế. Tránh đặt giới hạn quá chặt khiến test thất bại ngẫu nhiên do tải máy CI.

## 11. Theo dõi production và slow query

Test giúp phát hiện vấn đề trước khi deploy, còn production metrics cho biết workload thực tế.

Nên theo dõi:

- Query fingerprint và số lần thực thi.
- Tổng thời gian và percentile theo query fingerprint.
- Số lần lỗi, timeout và deadlock.
- Rows returned/affected nếu instrumentation hỗ trợ.
- Connection pool active, idle và pending.
- Database CPU, I/O, buffer cache, lock wait.
- Request latency và throughput của endpoint.

### 11.1. Chuẩn hóa query fingerprint

Hai câu SQL khác nhau chỉ vì giá trị tham số thường là cùng một loại query:

~~~sql
SELECT id, status FROM purchase_order WHERE customer_id = 101;
SELECT id, status FROM purchase_order WHERE customer_id = 202;
~~~

Nên nhóm theo dạng chuẩn hóa:

~~~sql
SELECT id, status
FROM purchase_order
WHERE customer_id = ?;
~~~

Điều này giúp tìm query có tần suất cao hoặc tổng thời gian lớn mà không tạo metric riêng cho từng giá trị tham số.

### 11.2. Không đưa tham số tùy ý vào metric label

Nếu dùng email, customer ID hoặc SQL đầy đủ chứa literal làm metric label, số lượng time series có thể tăng không giới hạn. Điều đó gây high cardinality và làm hệ thống metrics tốn tài nguyên.

Dùng query fingerprint, datasource, operation name hoặc endpoint làm dimension ổn định. Giữ tham số nhạy cảm ngoài metric label và ngoài log thông thường.

### 11.3. Slow query threshold

Ngưỡng slow query cần dựa trên SLA và phân bố thực tế. Một câu SELECT 200 ms có thể chấp nhận được trong báo cáo chạy nền nhưng quá chậm trong endpoint cần phản hồi dưới 100 ms.

Không chỉ log query vượt một ngưỡng toàn cục. Nên phân loại theo use case, endpoint hoặc query fingerprint.

## 12. Các nguyên nhân hồi quy thường gặp trong Spring Data JDBC

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| Query count tăng theo số aggregate | Truy vấn quan hệ lặp theo từng root hoặc xử lý từng item | Đếm query với nhiều kích thước input; kiểm tra SQL fingerprint lặp lại. |
| Một SELECT chậm hơn sau khi bảng tăng dữ liệu | Index thiếu, statistics cũ hoặc plan thay đổi | Chạy EXPLAIN/EXPLAIN ANALYZE trên database mục tiêu. |
| Repository trả object graph lớn | Aggregate có nhiều child hoặc query tải nhiều trường không cần | Đo số hàng/cột, dùng projection khi chỉ đọc báo cáo. |
| p95 tăng nhưng p50 gần như không đổi | Một số tham số có selectivity thấp hoặc lock contention | Phân nhóm theo query fingerprint và tham số đã chuẩn hóa; xem plan và lock. |
| Connection pool thường xuyên hết connection | Query chậm, transaction dài hoặc stream chưa đóng | Theo dõi pool active/pending, transaction duration và vòng đời Stream. |
| Save aggregate chậm sau khi thêm collection | Update có thêm thao tác xóa/insert child row | Đếm INSERT/DELETE/UPDATE và xem kích thước collection. |
| Query chạy nhanh trong test nhưng chậm production | Dataset, index, statistics hoặc database engine khác | Dùng database thật và dữ liệu đại diện trong integration/performance test. |
| Log SQL quá lớn | Bật logging toàn bộ query/parameter trong production | Chỉ bật có thời hạn, lọc query và che giá trị nhạy cảm. |
| Metric query tăng đột biến sau deploy | Một code path mới gọi repository nhiều lần hoặc retry lặp | So sánh fingerprint, request trace, query count và deployment timeline. |

## 13. Quy trình điều tra một hồi quy hiệu năng

Khi endpoint hoặc batch job chậm hơn sau một lần thay đổi, hãy làm theo thứ tự:

1. **Xác định use case:** endpoint/service nào chậm và bắt đầu từ thời điểm nào?
2. **So sánh latency:** p50, p95, p99, throughput và error rate trước/sau.
3. **Đo query count:** số SELECT/INSERT/UPDATE/DELETE trong một lần gọi có tăng không?
4. **Tìm query fingerprint:** câu SQL nào có tần suất hoặc tổng thời gian cao nhất?
5. **Kiểm tra connection pool:** request có phải chờ connection không?
6. **Lấy execution plan:** database scan, join, sort và buffer thế nào?
7. **So sánh dữ liệu:** số hàng, phân bố giá trị, index và statistics có thay đổi không?
8. **Kiểm tra mapping:** aggregate có thêm collection, callback hoặc converter mới không?
9. **Tạo test hồi quy:** khóa query count hoặc một budget hiệu năng phù hợp.
10. **Đo lại sau thay đổi:** dùng cùng dataset, engine và kịch bản tải để so sánh.

## 14. Bài tập tự thực hành

**Bài tập 1 — Bật SQL logging.** Bật DEBUG cho JdbcTemplate, chạy một repository method và ghi lại toàn bộ câu SQL. Xác định root query và query tải quan hệ.

**Bài tập 2 — Đếm query.** Bọc DataSource bằng datasource-proxy, gọi một service method và đọc QueryCountHolder. So sánh số SELECT khi tải một và hai mươi aggregate.

**Bài tập 3 — Phát hiện N+1.** Tạo một danh sách aggregate có collection child. Đo query count khi danh sách tăng từ 1 lên 10 và 50 phần tử.

**Bài tập 4 — Slow query listener.** Đặt ngưỡng 200 ms cho datasource-proxy và ghi lại query vượt ngưỡng. Xác nhận log có datasource, query fingerprint, thời gian và trạng thái.

**Bài tập 5 — Execution plan.** Chạy EXPLAIN và EXPLAIN ANALYZE cho một query tìm kiếm customer. So sánh estimated rows, actual rows, scan type và buffer usage.

**Bài tập 6 — Index regression.** Chạy cùng query trước và sau khi tạo index phù hợp. Đo plan và thời gian với dataset đủ lớn.

**Bài tập 7 — @DataJdbcTest với database thật.** Chạy repository integration test trên Testcontainers cùng engine production. Xác nhận query, mapping và index behavior.

**Bài tập 8 — Query count budget.** Thêm test giới hạn số SELECT cho một use case quan trọng. Thay đổi mapping để tạo thêm query và xác nhận test phát hiện hồi quy.

**Bài tập 9 — Connection pool.** Quan sát active/idle/pending connection khi tăng số request đồng thời. So sánh với query duration và transaction duration.

**Bài tập 10 — So sánh end-to-end.** Đo service latency và tổng database time. Tạo một callback hoặc xử lý Java chậm để thấy vì sao query time thấp không bảo đảm service nhanh.

## 15. Ghi nhớ

Đo hiệu năng Spring Data JDBC cần nhìn cả số query, thời gian thực thi, execution plan, dữ liệu trả về, connection pool và latency toàn use case. Một câu SQL riêng lẻ có thể nhanh nhưng nhiều query lặp lại vẫn làm request chậm.

Bật SQL logging để quan sát câu lệnh, dùng datasource-proxy hoặc công cụ tương đương để đếm query và phát hiện slow query, dùng Spring Boot Actuator để theo dõi connection pool, rồi dùng EXPLAIN của database để hiểu cách truy vấn được thực thi.

Trong test, hãy khóa query count cho các use case quan trọng để phát hiện N+1 hoặc query thừa. Đo performance trên đúng database engine và dữ liệu đại diện. So sánh p50/p95/p99, throughput và tổng database time thay vì chỉ nhìn average hoặc một lần chạy.

EXPLAIN ANALYZE thực sự chạy câu lệnh; đặc biệt với INSERT/UPDATE/DELETE, cần hiểu side effect và transaction trước khi thử. Log SQL và tham số có thể chứa dữ liệu nhạy cảm, nên chỉ bật có kiểm soát và dùng query fingerprint ổn định cho metric.

### Tài liệu tham khảo

- [Spring Data Relational – Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Boot – Actuator Metrics and DataSource Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [datasource-proxy – User Guide](https://jdbc-observations.github.io/datasource-proxy/docs/current/user-guide/)
- [datasource-proxy – QueryCount API](https://javadoc.io/static/net.ttddyy/datasource-proxy/1.11.0/net/ttddyy/dsproxy/QueryCount.html)
- [PostgreSQL – EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html)
- [Spring Boot – Testing Spring Data JDBC Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
