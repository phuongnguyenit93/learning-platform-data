# JdbcPagingItemReader

Trong Spring Batch, JdbcPagingItemReader<T> đọc dữ liệu từ database theo từng trang (page) bằng các câu SQL được tạo bởi một PagingQueryProvider. Thay vì giữ một JDBC cursor mở xuyên suốt quá trình đọc, reader truy vấn một nhóm bản ghi, giữ page hiện tại để trả item cho chunk, rồi truy vấn trang tiếp theo khi cần.

Reader này phù hợp khi cần đọc một tập dữ liệu lớn từ database, muốn giới hạn lượng dữ liệu nạp vào bộ nhớ mỗi lần truy vấn và cần khả năng restart dựa trên khóa sắp xếp. Nó thường được dùng với JdbcPagingItemReaderBuilder, PagingQueryProvider, RowMapper<T> và một DataSource.

Điểm quan trọng nhất khi dùng paging là thứ tự phải ổn định. Query cần có sort key xác định và tốt nhất là duy nhất, hoặc tổ hợp sort key tạo thành khóa duy nhất. Spring Batch dùng các giá trị sort key để tạo truy vấn cho những trang tiếp theo và lưu vị trí đọc trong ExecutionContext. Nếu thứ tự không ổn định, dữ liệu có thể bị đọc trùng hoặc bỏ sót, đặc biệt khi job restart hoặc nguồn dữ liệu thay đổi trong lúc chạy.

## 1. JdbcPagingItemReader hoạt động như thế nào?

JdbcPagingItemReader thực hiện các truy vấn phân trang thông qua PagingQueryProvider. Provider tạo SQL phù hợp với hệ quản trị database, dựa trên các phần select, from, where, sort key và các cấu hình khác.

Luồng xử lý tổng quát:

~~~mermaid
flowchart TD
    A[Step mở JdbcPagingItemReader] --> B[Đọc page đầu tiên]
    B --> C[PagingQueryProvider tạo SQL]
    C --> D[Database trả page]
    D --> E[RowMapper chuyển ResultSet thành object]
    E --> F[Reader trả từng item cho chunk]
    F --> G{Đã hết item trong page?}
    G -- Chưa --> F
    G -- Rồi --> H[Đọc page tiếp theo theo sort key]
    H --> C
    F --> I[Chunk commit và lưu checkpoint]
    I --> G
~~~

Ví dụ bảng customer có hàng triệu bản ghi. Reader có thể lấy 500 bản ghi mỗi truy vấn, ánh xạ từng hàng thành Customer, rồi trả chúng cho processor/writer theo commit interval của step.

pageSize điều khiển số bản ghi của một page. chunkSize điều khiển số item được xử lý trong một transaction chunk. Hai giá trị này có liên quan về hiệu năng nhưng không phải cùng một khái niệm.

## 2. Khi nào nên dùng JdbcPagingItemReader?

Reader này thường phù hợp khi:

- Dữ liệu nằm trong relational database và có thể truy vấn theo điều kiện.
- Tập dữ liệu lớn, không muốn tải toàn bộ kết quả vào bộ nhớ.
- Có khóa sắp xếp ổn định để đi qua các trang.
- Muốn hỗ trợ restart bằng checkpoint đã lưu trong ExecutionContext.
- Cần giới hạn truy vấn theo khoảng ID, ngày nghiệp vụ, trạng thái hoặc batch key.

Một số trường hợp cần cân nhắc reader khác:

| Nhu cầu | Lựa chọn có thể phù hợp |
|---|---|
| Đọc tuần tự một result set lớn trong một cursor | JdbcCursorItemReader |
| Đọc theo page và cần restart dựa trên sort key | JdbcPagingItemReader |
| Nguồn là file văn bản | FlatFileItemReader |
| Dữ liệu được chia theo partition và mỗi worker có query riêng | JdbcPagingItemReader trong worker step-scoped |
| Query hoặc giao thức đọc đặc thù không phù hợp provider | Custom ItemReader hoặc reader chuyên biệt |

Paging thường tránh việc giữ một cursor JDBC mở trong toàn bộ thời gian xử lý. Đổi lại, reader thực hiện nhiều truy vấn theo page và cần một chiến lược sort/restart chính xác.

## 3. PagingQueryProvider và SQL theo database

PagingQueryProvider định nghĩa cách tạo truy vấn cho trang đầu tiên và các trang tiếp theo. Spring Batch cung cấp các implementation theo database, ví dụ cho PostgreSQL, MySQL, Oracle, SQL Server, DB2 và một số hệ quản trị khác.

Có thể dùng SqlPagingQueryProviderFactoryBean để Spring Batch chọn provider phù hợp dựa trên DataSource:

~~~java
@Bean
PagingQueryProvider customerPagingQueryProvider(
        DataSource dataSource) throws Exception {

    SqlPagingQueryProviderFactoryBean factory =
            new SqlPagingQueryProviderFactoryBean();
    factory.setDataSource(dataSource);
    factory.setSelectClause(
            "select id, first_name, last_name, status");
    factory.setFromClause("from customer");
    factory.setWhereClause("where status = :status");

    Map<String, Order> sortKeys = new LinkedHashMap<>();
    sortKeys.put("id", Order.ASCENDING);
    factory.setSortKeys(sortKeys);

    return factory.getObject();
}
~~~

Các phần chính:

- selectClause: các cột cần đọc; phải bao gồm các cột được dùng làm sort key.
- fromClause: bảng hoặc biểu thức nguồn.
- whereClause: điều kiện lọc; có thể dùng named parameter.
- sortKeys: các cột và chiều sắp xếp dùng để xác định thứ tự paging.
- dataSource: giúp factory xác định database và tạo provider phù hợp.

Provider sẽ tạo SQL paging theo dialect database. Cách viết SQL cho page đầu và page tiếp theo có thể khác nhau giữa các hệ quản trị. Vì vậy, nên dùng provider tương ứng thay vì tự ghép LIMIT, OFFSET, ROWNUM hoặc cú pháp phân trang riêng trong reader.

Không thêm ORDER BY tùy tiện vào whereClause. Thứ tự paging được khai báo qua sort keys để provider có thể tạo truy vấn tiếp theo nhất quán.

## 4. Sort key phải xác định và ổn định

Sort key là nền tảng của paging. Reader cần biết bản ghi cuối cùng đã đọc trong page trước để truy vấn các bản ghi tiếp theo. Nếu sort key không tạo ra thứ tự duy nhất, hai hàng có cùng giá trị sort key có thể nằm ở ranh giới page và làm kết quả không xác định.

Ví dụ không an toàn:

~~~sql
select id, customer_id, status
from orders
where status = :status
order by status
~~~

Nếu nhiều hàng có cùng status, sort key này không phân biệt được thứ tự của chúng. Nên dùng một khóa duy nhất như id.

~~~sql
select id, customer_id, status
from orders
where status = :status
order by id
~~~

Trong PagingQueryProvider, khai báo:

~~~java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("id", Order.ASCENDING);
factory.setSortKeys(sortKeys);
~~~

Sort key nên đáp ứng:

- Tạo ra thứ tự toàn phần, tức mỗi hàng có vị trí xác định.
- Ổn định trong suốt thời gian job đọc.
- Có mặt trong select clause để reader theo dõi giá trị.
- Không chứa giá trị null nếu provider/database không thể so sánh chúng nhất quán.
- Được hỗ trợ bởi index phù hợp nếu tập dữ liệu lớn.

Một primary key tăng dần thường là lựa chọn tốt. Nếu dùng một cột không duy nhất, hãy bổ sung khóa phân biệt vào sort key.

## 5. Composite sort keys

Đôi khi không có một cột duy nhất phù hợp với thứ tự mong muốn. Có thể dùng nhiều sort key để tạo thứ tự xác định, ví dụ created_at và id.

~~~java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("created_at", Order.ASCENDING);
sortKeys.put("id", Order.ASCENDING);
factory.setSortKeys(sortKeys);
~~~

Thứ tự trên có nghĩa sắp xếp theo created_at, sau đó dùng id để phân biệt các bản ghi có cùng thời điểm. Tổ hợp (created_at, id) cần duy nhất trong tập dữ liệu được đọc.

Với composite key, provider xây dựng điều kiện cho trang tiếp theo dựa trên các giá trị sort key theo đúng thứ tự. Ví dụ logic khái quát:

~~~sql
where created_at > :lastCreatedAt
   or (created_at = :lastCreatedAt and id > :lastId)
order by created_at asc, id asc
~~~

Đây là cách diễn đạt logic keyset paging, không phải SQL cố định được dùng cho mọi database. Provider cụ thể sẽ tạo cú pháp phù hợp.

Nếu các cột có chiều sắp xếp khác nhau, chẳng hạn created_at DESC nhưng id ASC, hãy khai báo từng chiều trong map và kiểm tra query do provider sinh ra với database mục tiêu.

## 6. Cấu hình JdbcPagingItemReader cơ bản

Sau khi tạo query provider, có thể xây dựng reader bằng JdbcPagingItemReaderBuilder:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<Customer> customerReader(
        DataSource dataSource,
        PagingQueryProvider customerPagingQueryProvider,
        @Value("#{jobParameters['status']}") String status) {

    return new JdbcPagingItemReaderBuilder<Customer>()
            .name("customerReader")
            .dataSource(dataSource)
            .queryProvider(customerPagingQueryProvider)
            .parameterValues(Map.of("status", status))
            .pageSize(500)
            .fetchSize(500)
            .rowMapper((rs, rowNum) -> new Customer(
                    rs.getLong("id"),
                    rs.getString("first_name"),
                    rs.getString("last_name"),
                    rs.getString("status")))
            .saveState(true)
            .build();
}
~~~

Trong ví dụ:

- name là tên reader, được dùng trong metadata/checkpoint; cần duy nhất trong phạm vi step/job phù hợp.
- dataSource là nguồn kết nối database.
- queryProvider cung cấp SQL paging.
- parameterValues truyền giá trị cho named parameter trong where clause.
- pageSize đặt số hàng mỗi page.
- fetchSize là gợi ý cho JDBC driver về số hàng nên fetch trong một lần lấy dữ liệu.
- rowMapper ánh xạ mỗi hàng ResultSet thành Customer.
- saveState(true) cho phép lưu state để restart.

Bean reader thường được khai báo @StepScope khi cần late binding từ JobParameters hoặc StepExecutionContext. Không dùng chung một reader đang mở giữa nhiều StepExecution độc lập.

## 7. RowMapper chuyển ResultSet thành object

Sau khi query trả về một page, RowMapper<T> được gọi cho từng hàng để tạo object. Đây là tầng ánh xạ từ JDBC ResultSet sang kiểu Java; nó khác FieldSetMapper, vốn dùng cho dữ liệu file.

Ví dụ:

~~~java
public class CustomerRowMapper implements RowMapper<Customer> {

    @Override
    public Customer mapRow(ResultSet rs, int rowNum)
            throws SQLException {
        return new Customer(
                rs.getLong("id"),
                rs.getString("first_name"),
                rs.getString("last_name"),
                rs.getString("status"));
    }
}
~~~

Có thể dùng BeanPropertyRowMapper nếu tên cột có thể map rõ ràng vào property JavaBean:

~~~java
BeanPropertyRowMapper<Customer> mapper =
        new BeanPropertyRowMapper<>(Customer.class);
~~~

Nếu database dùng first_name nhưng object có property firstName, BeanPropertyRowMapper thường hỗ trợ quy tắc underscore-to-camel-case. Với mapping phức tạp, constructor bất biến hoặc kiểu dữ liệu đặc thù, custom RowMapper thường rõ ràng hơn.

Không đặt logic nghiệp vụ như kiểm tra hạn mức hoặc gọi API trong RowMapper. Mapper nên tập trung chuyển dữ liệu từ ResultSet thành object. Validation nghiệp vụ thuộc processor/service phía sau reader.

## 8. Named parameters và parameterValues

JdbcPagingItemReader hỗ trợ truyền giá trị cho named parameter được khai báo trong query provider. Ví dụ:

~~~java
factory.setWhereClause(
        "where status = :status and created_at < :cutoff");
~~~

Khi xây dựng reader:

~~~java
Map<String, Object> parameters = new HashMap<>();
parameters.put("status", status);
parameters.put("cutoff", cutoffTimestamp);

return new JdbcPagingItemReaderBuilder<Customer>()
        .name("customerReader")
        .dataSource(dataSource)
        .queryProvider(queryProvider)
        .parameterValues(parameters)
        .pageSize(500)
        .rowMapper(customerRowMapper)
        .saveState(true)
        .build();
~~~

Parameter binding giúp database xử lý giá trị đúng kiểu và giảm nguy cơ SQL injection. Không nối trực tiếp giá trị người dùng vào whereClause.

Tên bảng, tên cột và hướng sắp xếp thường là cấu trúc SQL, không phải bind parameter. Nếu cần chọn cấu trúc query theo input, hãy dùng whitelist cấu hình đã biết thay vì ghép chuỗi tùy ý.

Khi dùng JobParameters làm điều kiện lọc, hãy cân nhắc chúng có phải identifying parameters hay không. Tham số xác định tập dữ liệu nghiệp vụ thường nên tham gia định danh JobInstance để restart không vô tình đọc một tập dữ liệu khác.

## 9. Page size, chunk size và fetch size

Ba thông số này có vai trò khác nhau:

| Thông số | Điều khiển | Tác động chính |
|---|---|---|
| pageSize | Số hàng được query trong một page | Số lần truy vấn và lượng dữ liệu reader giữ cho page hiện tại |
| chunkSize | Số item được xử lý trong một transaction chunk | Tần suất commit và phạm vi rollback |
| fetchSize | Gợi ý cho JDBC driver về số hàng fetch từ database mỗi lượt | Cách driver lấy dữ liệu qua JDBC |

Ví dụ cấu hình:

~~~java
new JdbcPagingItemReaderBuilder<Customer>()
        .pageSize(500)
        .fetchSize(500)
        // Step dùng chunk(100, transactionManager)
        .build();
~~~

pageSize và chunkSize thường được đặt gần nhau hoặc bằng nhau để tránh nạp quá nhiều hàng chưa cần dùng và giảm số lần query. Tuy nhiên, đây là quyết định hiệu năng, không phải yêu cầu bắt buộc. Nếu page size lớn hơn chunk size, reader có thể giữ phần còn lại của page qua nhiều chunk. Nếu page size nhỏ hơn chunk size, một chunk có thể cần dữ liệu từ nhiều page.

fetchSize là hint cho JDBC driver; driver và database có thể diễn giải khác nhau. Không giả định fetchSize luôn bằng số hàng trả về trong page. Hãy đo thời gian query, memory, network round trip và số lần page được nạp.

## 10. Checkpoint và restart

Khi saveState(true), reader lưu thông tin cần thiết vào ExecutionContext để có thể tiếp tục sau khi job thất bại hoặc dừng. Với paging reader, trạng thái đọc gắn với sort key của item đã được xử lý đến checkpoint.

Ở lần chạy đầu:

1. Reader truy vấn page đầu tiên.
2. Reader trả item cho chunk.
3. Chunk commit.
4. Spring Batch cập nhật checkpoint trong execution context.
5. Khi cần page mới, reader tiếp tục từ giá trị sort key cuối cùng đã đọc.

Khi restart:

1. Spring Batch mở reader với execution context đã lưu.
2. Reader khôi phục vị trí dựa trên sort key/checkpoint.
3. Query tiếp theo lấy các bản ghi sau vị trí đã commit.
4. Những chunk đã commit không cần xử lý lại theo cơ chế restart thông thường.

Để restart hoạt động đúng:

- Đặt saveState(true) nếu cần checkpoint.
- Đặt name ổn định và duy nhất cho reader.
- Dùng sort key ổn định, tốt nhất là duy nhất.
- Giữ điều kiện lọc và ý nghĩa JobParameters giống lần chạy ban đầu.
- Không thay đổi tùy tiện thứ tự sort hoặc cấu trúc query giữa lần chạy và restart.
- Đảm bảo nguồn dữ liệu không bị thay đổi theo cách làm mất tính nhất quán của checkpoint.

Nếu saveState(false), reader không lưu state để restart. Điều này có thể phù hợp với một số trường hợp multi-threaded client hoặc job chấp nhận chạy lại từ đầu, nhưng phải hiểu rõ nguy cơ đọc lại và side effect trùng.

## 11. Vì sao sort key ảnh hưởng tới restart?

Giả sử reader đã xử lý đến id=5000 và checkpoint được commit. Khi restart, truy vấn tiếp theo cần lấy những bản ghi sau khóa đó. Nếu sort key là id duy nhất, điều kiện tiếp tục có thể được xác định rõ.

Nếu sort key chỉ là status, nhiều hàng có cùng giá trị. Checkpoint không thể phân biệt chính xác hàng nào trong nhóm cùng status đã được xử lý đến đâu. Điều này có thể làm một số hàng bị lặp hoặc bỏ qua.

Với composite key (created_at, id), checkpoint giữ đủ giá trị để xác định vị trí trong thứ tự. Cần bảo đảm tổ hợp này duy nhất và không thay đổi trong khi job chạy.

Không nên dùng một cột mutable như priority hoặc status làm sort key nếu các bản ghi có thể thay đổi giá trị đó trong lúc paging. Một hàng đã đọc có thể di chuyển sang vị trí trước/sau checkpoint, làm thay đổi tập dữ liệu của trang tiếp theo.

## 12. Dữ liệu nguồn thay đổi trong khi job đang paging

Paging query được thực hiện nhiều lần. Nếu các transaction/chunk nhìn thấy dữ liệu ở những thời điểm khác nhau, tập dữ liệu có thể thay đổi giữa hai page:

- Một hàng mới được insert với sort key nhỏ hơn checkpoint có thể không được đọc.
- Một hàng mới có sort key lớn hơn checkpoint có thể xuất hiện ở page sau dù không tồn tại khi job bắt đầu.
- Một hàng đã đọc bị xóa hoặc cập nhật điều kiện lọc có thể làm kết quả không còn phản ánh snapshot ban đầu.
- Thay đổi sort key có thể khiến hàng di chuyển qua ranh giới checkpoint.

Nếu nghiệp vụ yêu cầu xử lý một snapshot ổn định, cần định nghĩa rõ phạm vi dữ liệu. Một số cách:

- Chụp high-water mark trước khi đọc, ví dụ id <= maxIdAtStart.
- Lọc theo batch ID hoặc business date bất biến.
- Đọc từ bảng staging/snapshot đã đóng băng cho lần chạy.
- Dùng isolation level hoặc snapshot semantics phù hợp với database và thời gian xử lý.
- Không cập nhật các cột dùng làm sort key trong lúc job đang đọc.

Không giả định transaction chunk của Spring Batch tạo ra một snapshot xuyên suốt toàn job. Mỗi chunk có thể commit riêng, vì vậy snapshot consistency cần được thiết kế theo database và nghiệp vụ.

## 13. Index và hiệu năng truy vấn

Paging reader thực hiện nhiều query theo điều kiện lọc và sort key. Nếu query không có index phù hợp, mỗi page có thể tốn thời gian scan/sort lớn.

Ví dụ query:

~~~sql
select id, customer_id, status, created_at
from orders
where status = :status
  and id > :lastId
order by id
~~~

Index có thể cần xem xét theo điều kiện lọc và thứ tự sort. Với database cụ thể, index (status, id) có thể hữu ích hơn index riêng trên status hoặc id, nhưng quyết định cần dựa trên query plan và phân bố dữ liệu thực tế.

Các điểm cần đo:

- Thời gian của query trang đầu và query trang tiếp theo.
- Số hàng database phải scan để trả một page.
- Sort operation có dùng disk hay không.
- Index hit và buffer/cache behavior.
- Connection acquisition time.
- Network round trips và kích thước row.
- Thời gian mapping mỗi page.

Tránh chọn page size quá lớn chỉ để giảm số lần query. Page lớn có thể tăng memory, thời gian query, thời gian giữ transaction và độ trễ trước khi item đầu tiên được xử lý.

## 14. Reader và transaction boundary

JdbcPagingItemReader dùng DataSource để thực hiện query. Khi datasource tham gia transaction do step quản lý, các thao tác database khác trong cùng thread có thể tham gia transaction theo cấu hình transaction manager.

Tuy nhiên, reader paging không có nghĩa toàn bộ job nằm trong một transaction. Chunk vẫn có transaction riêng theo commit interval. Reader có thể query nhiều page qua nhiều chunk; checkpoint được lưu tại ranh giới commit theo cơ chế Spring Batch.

Các lưu ý:

- Dùng đúng DataSource với transaction manager của step nếu cần cùng transaction.
- Không chia sẻ JDBC Connection hoặc ResultSet ra ngoài reader.
- Không giữ transaction mở xuyên suốt toàn job chỉ để cố định snapshot nếu điều đó gây lock hoặc giữ connection quá lâu.
- Kiểm tra isolation level và hành vi database khi có concurrent updates.
- Nếu reader query một datasource còn writer ghi datasource khác, xác định rõ tính nhất quán và cơ chế phục hồi.

Nếu reader và writer cùng truy cập một bảng, cần xem xét liệu việc writer cập nhật cột lọc hoặc sort key có ảnh hưởng đến các page tiếp theo hay không.

## 15. Đọc dữ liệu theo JobParameters

Một batch job thường đọc dữ liệu theo tham số như ngày nghiệp vụ, trạng thái hoặc batch ID. Có thể bind tham số ở reader step-scoped:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<Order> orderReader(
        DataSource dataSource,
        PagingQueryProvider orderQueryProvider,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    LocalDate date = LocalDate.parse(businessDate);
    Timestamp start = Timestamp.valueOf(date.atStartOfDay());
    Timestamp end = Timestamp.valueOf(date.plusDays(1).atStartOfDay());

    Map<String, Object> parameters = Map.of(
            "startTime", start,
            "endTime", end);

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("orderReader")
            .dataSource(dataSource)
            .queryProvider(orderQueryProvider)
            .parameterValues(parameters)
            .pageSize(300)
            .rowMapper(orderRowMapper())
            .saveState(true)
            .build();
}
~~~

Query provider tương ứng:

~~~java
factory.setWhereClause(
        "where created_at >= :startTime and created_at < :endTime");
~~~

Dùng khoảng thời gian nửa mở [start, end) giúp tránh lỗi ở phần mili giây/nanosecond tại ranh giới ngày và tránh một bản ghi thuộc hai ngày liên tiếp. Hãy dùng timezone nghiệp vụ nhất quán khi chuyển LocalDate sang timestamp.

Nếu businessDate xác định tập dữ liệu của JobInstance, nên là identifying JobParameter. Khi restart, dùng lại cùng giá trị để query không đổi phạm vi.

## 16. Partitioning với JdbcPagingItemReader

Với tập dữ liệu rất lớn, có thể chia thành partition theo range ID. Mỗi worker có StepExecution và ExecutionContext riêng, do đó có thể dùng một JdbcPagingItemReader step-scoped cho từng partition.

Ví dụ worker reader:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<Order> partitionOrderReader(
        DataSource dataSource,
        PagingQueryProvider partitionQueryProvider,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxIdExclusive) {

    Map<String, Object> parameters = Map.of(
            "minId", minId,
            "maxIdExclusive", maxIdExclusive);

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("partitionOrderReader")
            .dataSource(dataSource)
            .queryProvider(partitionQueryProvider)
            .parameterValues(parameters)
            .pageSize(500)
            .rowMapper(orderRowMapper())
            .saveState(true)
            .build();
}
~~~

Query provider:

~~~java
factory.setWhereClause(
        "where id >= :minId and id < :maxIdExclusive");
~~~

Partitioner phải tạo các khoảng không giao nhau và bao phủ đúng tập dữ liệu cần đọc. Ví dụ [1, 1001), [1001, 2001) và [2001, 3001) không chồng lấn. Mỗi worker có reader và checkpoint riêng, giúp restart một partition dễ kiểm soát hơn.

Khi chạy partitioning, cần cân bằng kích thước partition, giới hạn số worker và connection pool. Nhiều partition cùng query database có thể tăng tải; index theo range/sort key rất quan trọng.

## 17. Multi-threaded client và thread safety

JdbcPagingItemReader có đặc tính thread-safety cần lưu ý: reader được mô tả là thread-safe giữa các lần gọi open(ExecutionContext). Tuy nhiên, khi dùng trong một multi-threaded client, cần đặt saveState=false; khi đó không có checkpoint reader để restart theo state đã lưu.

Điều này không có nghĩa mọi cách chia sẻ reader giữa thread đều cho cùng thứ tự item hoặc restart semantics. Trong multi-threaded step, nhiều worker có thể lấy item theo thứ tự không xác định; nếu ứng dụng cần checkpoint độc lập, partitioning thường dễ kiểm soát hơn vì mỗi worker có reader và StepExecution riêng.

Không dùng một reader đang mở cho nhiều JobExecution độc lập. Nếu reader nhận JobParameters khác nhau, tạo target bean theo StepScope để mỗi execution có cấu hình và lifecycle riêng.

Khi cần parallelism:

- Ưu tiên partitioning với range/key rõ ràng nếu cần restart từng worker.
- Dùng saveState=false chỉ khi chấp nhận không có restart state của reader trong mô hình multi-thread client.
- Kiểm tra writer và processor có thread-safe không; reader an toàn không làm toàn pipeline tự động an toàn.
- Giới hạn số worker theo năng lực database và connection pool.

## 18. saveState, name và giới hạn restart

Khi saveState bật, reader ghi trạng thái vào ExecutionContext. Tên reader được dùng để tạo key metadata ổn định. Nếu có nhiều reader cùng step, mỗi reader cần tên riêng.

Ví dụ:

~~~java
new JdbcPagingItemReaderBuilder<Order>()
        .name("orderPagingReader")
        .saveState(true)
        // các cấu hình khác
        .build();
~~~

Nếu đổi tên reader giữa lần chạy và restart, framework có thể không tìm thấy checkpoint cũ theo key dự kiến. Nếu đổi query, sort keys hoặc điều kiện lọc trong khi restart, checkpoint cũ có thể không còn đại diện cho cùng một vị trí trong tập dữ liệu.

saveState(false) phù hợp với reader được dùng trong môi trường không hỗ trợ restart state hoặc khi ứng dụng chủ động chấp nhận đọc lại. Đừng tắt saveState chỉ để tránh một lỗi checkpoint mà chưa hiểu nguyên nhân; việc đó có thể khiến job restart từ đầu và tạo side effect trùng.

## 19. Xử lý dữ liệu trùng và thay đổi trong tập đọc

Sort key duy nhất bảo đảm thứ tự, nhưng không tự giải quyết mọi vấn đề về dữ liệu trùng. Nếu bảng nguồn có duplicate nghiệp vụ, reader vẫn đọc cả hai hàng nếu query không lọc hoặc group chúng.

Nếu nguồn có thể được cập nhật trong lúc job chạy:

- Tránh dùng sort key mutable.
- Xác định high-water mark tại thời điểm bắt đầu.
- Dùng điều kiện lọc ổn định theo batch/version.
- Nếu cần snapshot chính xác, tạo snapshot hoặc staging set.
- Dùng unique business key ở writer để chống duplicate khi restart/replay.

Nếu reader lấy theo id tăng dần và một hàng mới được insert với ID lớn hơn checkpoint, nó có thể xuất hiện ở page sau. Nếu nghiệp vụ không muốn nhận dữ liệu phát sinh sau lúc job bắt đầu, cần chặn bằng maxIdAtStart hoặc batch cutoff.

## 20. So sánh với JdbcCursorItemReader

| Tiêu chí | JdbcPagingItemReader | JdbcCursorItemReader |
|---|---|---|
| Cách đọc | Query theo page | Duyệt ResultSet/cursor |
| Kết nối/cursor | Không cần giữ một cursor xuyên suốt toàn bộ lượt đọc | Thường giữ cursor/kết nối trong thời gian đọc |
| Phân trang | Cần PagingQueryProvider và sort keys | Không cần paging query provider |
| Restart | Dựa vào state/checkpoint và sort key | Dựa vào vị trí/state của cursor reader |
| SQL | Provider tạo query theo database dialect | Query thường là một câu SQL cố định |
| Hiệu năng | Nhiều query; có thể phù hợp với page và index tốt | Có thể hiệu quả cho đọc tuần tự nếu driver/database hỗ trợ cursor tốt |
| Dữ liệu thay đổi | Các page có thể nhìn thấy thay đổi theo transaction/isolation | Kết quả phụ thuộc cursor và transaction/driver |

Không có reader nào luôn nhanh hơn. Hãy benchmark trên database, driver, kích thước row, số lượng record và workload thực tế. Nếu query page tiếp theo tốn nhiều chi phí do thiếu index, paging có thể chậm hơn cursor. Nếu không muốn giữ cursor lâu hoặc cần restart theo sort key, paging có thể phù hợp hơn.

## 21. Kiểm thử JdbcPagingItemReader

Kiểm thử nên bao gồm query paging, mapping, checkpoint và restart:

1. First page: xác nhận page đầu có đúng dữ liệu và số lượng.
2. Next page: xác nhận các trang tiếp theo không lặp và không bỏ sót hàng.
3. Sort key uniqueness: tạo nhiều hàng trùng giá trị sort key chính và xác nhận composite key vẫn cho thứ tự xác định.
4. Parameter binding: xác nhận named parameter lọc đúng tập dữ liệu.
5. RowMapper: xác nhận kiểu số, ngày, null và alias cột được map đúng.
6. Page/chunk sizing: kiểm tra với page size nhỏ hơn, bằng và lớn hơn chunk size.
7. Restart: dừng job sau một số chunk đã commit rồi restart cùng JobParameters; xác nhận item không bị đọc trùng/bỏ sót.
8. Source mutation: thêm/xóa/cập nhật record giữa các page để xác nhận chính sách snapshot/cutoff.
9. Partitioning: xác nhận các range không giao nhau và tổng hợp kết quả bằng tập input dự kiến.
10. Performance: đo query plan, index usage, page latency, memory và connection usage.

Ví dụ test reader trực tiếp:

~~~java
ExecutionContext context = new ExecutionContext();
reader.open(context);

List<Customer> actual = new ArrayList<>();
Customer item;
while ((item = reader.read()) != null) {
    actual.add(item);
}

reader.close();

assertEquals(expectedCustomerIds, actual.stream()
        .map(Customer::id)
        .toList());
~~~

Để test restart, cần giữ lại ExecutionContext đã được cập nhật ở ranh giới commit, đóng reader, tạo reader mới với cùng cấu hình và gọi open(context) trên state đã lưu. Test step/job integration thực tế có giá trị hơn test reader riêng khi cần xác nhận transaction và checkpoint được phối hợp đúng.

## 22. Những lỗi thường gặp

**Không khai báo sort key.** Provider không có thứ tự paging ổn định. Khai báo sort key rõ ràng.

**Dùng sort key không duy nhất.** Nhiều hàng cùng giá trị có thể gây lặp hoặc thiếu ở ranh giới page. Dùng primary key hoặc composite key duy nhất.

**Sort key thay đổi trong lúc job chạy.** Hàng có thể di chuyển qua checkpoint. Dùng khóa ổn định hoặc snapshot/cutoff.

**Nhầm pageSize với chunkSize.** Page size là số hàng mỗi truy vấn; chunk size là số item mỗi transaction. Chọn và đo riêng.

**Cho rằng fetchSize điều khiển số hàng của page.** Fetch size là JDBC hint; page size mới là cấu hình số hàng của truy vấn paging.

**Nối parameter trực tiếp vào SQL.** Dễ gây SQL injection và lỗi quoting. Dùng named parameter cùng parameterValues.

**Không đưa sort key vào select clause.** Reader/provider cần giá trị khóa để xác định vị trí tiếp theo. Chọn đủ cột.

**Đổi query hoặc reader name khi restart.** Checkpoint cũ có thể không còn tương thích. Giữ cấu hình và tên ổn định.

**Tắt saveState mà vẫn kỳ vọng restart.** Không có checkpoint reader để tiếp tục đúng vị trí. Chỉ tắt khi chấp nhận giới hạn này.

**Chia sẻ reader giữa nhiều execution.** Reader đang mở có state riêng. Dùng StepScope và worker reader riêng.

**Không tạo index theo filter/sort.** Mỗi page có thể scan/sort nhiều dữ liệu. Kiểm tra query plan và index.

**Giả định paging tạo snapshot toàn job.** Các page có thể chạy ở các transaction/thời điểm khác nhau. Dùng cutoff hoặc snapshot khi cần tính nhất quán.

## 23. Quy trình triển khai

Khi xây dựng một JdbcPagingItemReader, có thể làm theo thứ tự:

1. Xác định tập dữ liệu và điều kiện lọc của job.
2. Chọn các cột cần đọc và RowMapper tạo object.
3. Chọn sort key ổn định, duy nhất; dùng composite key nếu cần.
4. Cấu hình PagingQueryProvider theo DataSource và SQL dialect.
5. Bind named parameter qua parameterValues.
6. Chọn pageSize, fetchSize và chunkSize dựa trên benchmark.
7. Đặt tên reader ổn định và bật saveState nếu cần restart.
8. Dùng StepScope khi reader phụ thuộc JobParameters hoặc partition context.
9. Xác định dữ liệu nguồn có thể thay đổi trong lúc đọc không; thêm cutoff/snapshot nếu cần.
10. Kiểm thử paging, composite sort, restart, partition và hiệu năng trên database mục tiêu.

## Kết luận

JdbcPagingItemReader đọc dữ liệu database theo từng page thông qua PagingQueryProvider. Provider tạo SQL phù hợp với database, RowMapper chuyển từng hàng thành object và reader trả item cho chunk step. pageSize quyết định số hàng mỗi page; chunkSize quyết định transaction commit interval; fetchSize là gợi ý cho JDBC driver.

Để paging và restart đáng tin cậy, hãy dùng sort key ổn định và duy nhất, hoặc composite key tạo thành thứ tự toàn phần; giữ reader name, query và identifying parameters ổn định qua restart; bật saveState khi cần checkpoint. Nếu nguồn có thể thay đổi trong lúc đọc, xác định cutoff hoặc snapshot nghiệp vụ. Với parallel processing cần restart độc lập, partitioning cùng một reader step-scoped cho mỗi worker thường dễ kiểm soát hơn chia sẻ reader trong multi-threaded client. Kiểm thử bằng database thực tế và đo query plan, page latency, memory cùng connection usage trước khi chọn cấu hình production.
