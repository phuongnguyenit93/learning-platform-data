# Nhận diện truy vấn lặp khi tải danh sách aggregate trong Spring Data JDBC

## 1. Vì sao cần quan sát số truy vấn khi tải aggregate?

Một màn hình danh sách thường tải nhiều aggregate root cùng lúc. Ví dụ, trang đơn hàng hiển thị danh sách đơn và các dòng hàng của từng đơn. Ở tầng Java, lời gọi repository có thể rất đơn giản:

~~~java
List<Order> orders = orderRepository.findAll();
~~~

Tuy nhiên, một lần gọi repository không nhất thiết chỉ tạo một câu SELECT. Spring Data JDBC tải aggregate theo mapping của nó. Nếu aggregate root tham chiếu collection con, framework có thể chạy thêm câu truy vấn để lấy dữ liệu của collection đó.

Với cách tải truyền thống, quá trình có thể là:

1. SELECT danh sách aggregate root.
2. Với từng root, SELECT các entity thuộc collection thứ nhất.
3. Với từng root, SELECT các entity thuộc collection thứ hai, nếu có.
4. Lắp các kết quả thành aggregate hoàn chỉnh.

Khi số aggregate tăng, số SQL statement có thể tăng tuyến tính theo số root. Đây là dạng vấn đề thường được gọi là **N+1 query**.

Điều quan trọng là nhận diện được mẫu truy vấn này từ SQL log, query metrics và thời gian xử lý. Chỉ nhìn vào code findAll() không đủ để kết luận ứng dụng đang chạy bao nhiêu câu SQL.

## 2. Cách tải aggregate truyền thống của Spring Data JDBC

Giả sử có aggregate đơn hàng:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public class Order {

    @Id
    private Long id;

    private String orderNumber;

    private String status;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;

    // constructors, getters...
}
~~~

Entity con:

~~~java
@Table("order_lines")
public class OrderLine {

    @Id
    private Long id;

    private String sku;

    private int quantity;

    // constructors, getters...
}
~~~

Repository:

~~~java
public interface OrderRepository
        extends CrudRepository<Order, Long> {
}
~~~

Khi gọi orderRepository.findAll() theo cách tải truyền thống, SQL có thể có dạng:

~~~sql
SELECT id, order_number, status
FROM orders
ORDER BY id;
~~~

Sau đó, với mỗi đơn hàng, framework lấy các dòng hàng:

~~~sql
SELECT id, order_id, sku, quantity
FROM order_lines
WHERE order_id = ?;
~~~

Nếu có 3 đơn hàng, log có thể cho thấy:

~~~text
SELECT ... FROM orders;

SELECT ... FROM order_lines WHERE order_id = 101;
SELECT ... FROM order_lines WHERE order_id = 102;
SELECT ... FROM order_lines WHERE order_id = 103;
~~~

Đây là mẫu một truy vấn lấy root cộng một truy vấn collection cho mỗi root.

### 2.1. Công thức số truy vấn

Gọi:

- N là số aggregate root được tải.
- K là số collection path trực tiếp cần tải riêng cho mỗi aggregate.
- Qroot là số truy vấn lấy aggregate root, thường là 1 cho một lần tải danh sách.

Trong trường hợp đơn giản, số truy vấn gần đúng là:

\[
Q = Q_{root} + N \times K
\]

Nếu chỉ có một collection:

\[
Q = 1 + N
\]

Nếu có hai collection được tải riêng:

\[
Q = 1 + 2N
\]

Ví dụ:

| Số aggregate root | Một collection | Hai collection |
|---:|---:|---:|
| 1 | 2 | 3 |
| 10 | 11 | 21 |
| 50 | 51 | 101 |
| 100 | 101 | 201 |

Đây là mô hình để nhận diện xu hướng, không phải cam kết số statement cho mọi mapping. Aggregate lồng nhau, truy vấn bổ sung của ứng dụng và các đường tải khác có thể làm số lượng thay đổi. Hãy xác nhận bằng SQL log trên chính aggregate và phiên bản đang chạy.

## 3. N+1 trong Spring Data JDBC khác cách hiểu lazy loading của ORM

Spring Data JDBC quản lý aggregate theo ranh giới aggregate. Khi tải aggregate, framework dựng object graph cần thiết theo mapping. Hiện tượng truy vấn lặp có thể xảy ra trong chính quá trình materialize danh sách aggregate, vì các entity được tham chiếu được tải bằng statement riêng.

Không nên mặc định rằng một truy vấn child chỉ chạy khi code gọi getter của collection như cách một số ORM dùng lazy-loading proxy. Hãy quan sát thời điểm các statement xuất hiện trong request và call stack tương ứng.

Cũng cần phân biệt hai mẫu:

**Mẫu A — Aggregate loading truyền thống**

~~~java
List<Order> orders = orderRepository.findAll();
~~~

Một truy vấn lấy root, sau đó framework tải collection cho từng root.

**Mẫu B — Ứng dụng tự gọi repository trong vòng lặp**

~~~java
List<Long> ids = findOrderIds();

List<Order> orders = new ArrayList<>();

for (Long id : ids) {
    orders.add(orderRepository.findById(id).orElseThrow());
}
~~~

Ở đây ứng dụng chủ động gọi findById nhiều lần. Ngay cả khi aggregate không có collection con, số truy vấn root vẫn tăng theo số ID.

Hai mẫu có thể cùng xuất hiện trong một request. Vì vậy, khi thấy nhiều SELECT giống nhau, hãy xác định chúng được phát ra từ quá trình load relation hay từ vòng lặp ở service/controller.

## 4. Dấu hiệu nhận biết N+1 trong SQL log

Một dấu hiệu mạnh là cùng một SQL template được thực thi nhiều lần, chỉ khác bind parameter là ID của aggregate cha.

Ví dụ log:

~~~text
Executing SQL:
SELECT id, order_number, status FROM orders

Executing SQL:
SELECT id, order_id, sku, quantity
FROM order_lines WHERE order_id = ?
Parameters: [101]

Executing SQL:
SELECT id, order_id, sku, quantity
FROM order_lines WHERE order_id = ?
Parameters: [102]

Executing SQL:
SELECT id, order_id, sku, quantity
FROM order_lines WHERE order_id = ?
Parameters: [103]
~~~

Hãy chú ý ba đặc điểm:

1. Có một câu SELECT lấy danh sách root.
2. Một câu SELECT khác lặp lại với cùng cấu trúc SQL.
3. Giá trị bind parameter thay đổi theo ID của từng root.

Nếu số lần chạy câu child SELECT tăng gần tương ứng với số root, đó là tín hiệu N+1.

### 4.1. So sánh số lượng query theo page size

Một phép thử hữu ích là tải cùng endpoint với các page size khác nhau:

| Page size | Số query quan sát | Nhận xét |
|---:|---:|---|
| 1 | 2 | Một root query và một child query |
| 10 | 11 | Child query lặp theo từng root |
| 50 | 51 | Số statement tăng theo page size |

Nếu số query tăng gần tuyến tính như vậy, hãy kiểm tra cách tải collection.

Không nhất thiết phải dùng đúng các con số trong bảng. Mục đích là so sánh độ tăng query khi tăng N, trong khi filter và cấu trúc aggregate giữ nguyên.

### 4.2. Phân biệt query lặp với query hợp lệ

Không phải mọi SQL giống nhau đều là N+1:

- Một truy vấn root và một truy vấn count để tạo Page có thể là hành vi dự kiến.
- Một truy vấn lấy dữ liệu và một truy vấn kiểm tra quyền có thể là hai phần khác nhau của use case.
- Một batch có thể thực thi cùng SQL template nhiều lần theo thiết kế.
- Một vòng lặp gọi findById là N query do code ứng dụng tạo ra, không phải do collection loading.

Hãy nhóm statement theo SQL fingerprint/template, đếm số lần thực thi, ghi nhận bind values và liên kết với trace/request. Đừng chỉ đếm tổng số dòng log.

## 5. Bật SQL logging để quan sát

Với Spring JDBC, có thể bật log câu SQL ở mức DEBUG:

~~~properties
logging.level.org.springframework.jdbc.core.JdbcTemplate=DEBUG
~~~

Để quan sát bind parameter, có thể bật TRACE:

~~~properties
logging.level.org.springframework.jdbc.core.StatementCreatorUtils=TRACE
~~~

Ví dụ log cấu hình:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core.JdbcTemplate: DEBUG
    org.springframework.jdbc.core.StatementCreatorUtils: TRACE
~~~

Logger JdbcTemplate giúp nhìn thấy SQL được thực thi qua Spring JDBC. Logger parameter giúp kiểm tra giá trị bind trong quá trình chẩn đoán.

Không nên bật log bind parameter rộng rãi trong production nếu giá trị có thể chứa thông tin nhạy cảm. Dùng thời gian ngắn trong môi trường kiểm thử hoặc cấu hình log có kiểm soát, và tắt sau khi hoàn tất điều tra.

Nếu log mặc định chưa đủ chi tiết, có thể dùng công cụ quan sát JDBC như P6Spy hoặc datasource-proxy để ghi nhận:

- SQL statement và parameter.
- Thời gian thực thi.
- Số lần statement được gọi.
- Connection/request context.
- Tổng query count trong một use case.

Công cụ proxy DataSource đặc biệt hữu ích khi cần đếm query theo request hoặc viết assertion trong integration test.

## 6. Đo query count theo một use case

Đừng đo toàn bộ ứng dụng rồi suy ra một endpoint. Hãy chọn một use case cụ thể, chẳng hạn API liệt kê đơn hàng.

Quy trình đo:

1. Tạo dữ liệu kiểm thử với số lượng aggregate đã biết.
2. Gọi đúng service/controller method cần quan sát.
3. Đếm SELECT theo SQL fingerprint.
4. Phân biệt root query, child query, count query và các truy vấn khác.
5. Lặp lại với số lượng root khác nhau.
6. So sánh query count, tổng thời gian SQL và thời gian toàn request.

Ví dụ dữ liệu:

~~~text
orders:
  id 101
  id 102
  id 103

order_lines:
  order_id 101 -> 2 rows
  order_id 102 -> 3 rows
  order_id 103 -> 1 row
~~~

Với cách tải truyền thống, số dòng child không quyết định trực tiếp số lần query child. Một câu SELECT lấy collection của một root có thể trả về 0, 1 hoặc nhiều dòng, nhưng statement vẫn được thực thi cho root đó.

Đây là lý do query count và row count cần được theo dõi riêng. Một query có thể trả nhiều dòng; nhiều query có thể mỗi query chỉ trả một dòng.

## 7. Xác định nguồn tạo truy vấn lặp

Khi đã thấy SQL lặp, hãy lần ngược về nguồn tạo statement.

### 7.1. Truy vấn collection trong quá trình dựng aggregate

Dấu hiệu:

- Có một SELECT lấy aggregate root.
- SELECT collection lặp lại với parent ID khác nhau.
- Không có vòng lặp repository rõ ràng trong service.
- Số query tăng khi danh sách root tăng.

Đây là mẫu tải aggregate truyền thống.

### 7.2. Repository method được gọi trong vòng lặp

Ví dụ:

~~~java
for (Long customerId : customerIds) {
    Customer customer = customerRepository.findById(customerId)
            .orElseThrow();
    // Xử lý customer.
}
~~~

Nếu chỉ cần tải các customer theo danh sách ID, dùng API tải theo tập:

~~~java
Iterable<Customer> customers =
        customerRepository.findAllById(customerIds);
~~~

findAllById cho phép gửi một tập ID trong một thao tác repository. Số SQL thực tế vẫn phụ thuộc store strategy, giới hạn bind parameter và cách aggregate có collection được tải, nhưng nó tránh pattern gọi một repository method cho từng ID ở tầng ứng dụng.

### 7.3. Service gọi repository trong mapper hoặc serializer

Một mapper DTO hoặc getter có thể gọi service/repository để bổ sung dữ liệu cho từng item. Khi chuyển danh sách thành response, query count có thể tăng theo số item.

Ví dụ không nên:

~~~java
List<OrderResponse> responses = orders.stream()
        .map(order -> new OrderResponse(
                order.getId(),
                customerRepository.findById(order.getCustomerId())
                        .orElseThrow()
                        .getName()
        ))
        .toList();
~~~

Hãy nhận diện các truy vấn được phát ra trong giai đoạn mapping response. Có thể batch-load các customer ID trước, tạo map theo ID, rồi dựng DTO từ map đó.

### 7.4. Listener hoặc callback truy vấn thêm dữ liệu

Lifecycle event listener có thể chạy khi aggregate được tải và listener có thể gọi thêm repository. Nếu log cho thấy query xuất hiện sau khi aggregate được dựng, kiểm tra listener, callback và các bean quan sát entity.

Một listener chỉ ghi log không nhất thiết tạo thêm SQL. Nhưng listener thực hiện truy vấn để lấy thông tin bổ sung có thể tạo ra một chuỗi truy vấn khác.

## 8. Single Query Loading trong Spring Data JDBC

Từ Spring Data JDBC 3.2, framework cung cấp **Single Query Loading** để tải nhiều aggregate cùng collection bằng một SQL statement trong những trường hợp được hỗ trợ.

Thay vì:

~~~text
SELECT orders
SELECT order_lines WHERE order_id = 101
SELECT order_lines WHERE order_id = 102
SELECT order_lines WHERE order_id = 103
~~~

Single Query Loading có thể dựng kết quả aggregate bằng một truy vấn SQL duy nhất. Cách triển khai dùng các window function như row_number() và count(*) để biểu diễn các collection con trong một result set mà không tạo cross product không cần thiết giữa các collection.

Tham khảo: https://spring.io/blog/2023/08/31/this-is-the-beginning-of-the-end-of-the-n-1-problem-introducing-single-query/

### 8.1. Bật Single Query Loading

Thuộc tính được cấu hình trên JdbcMappingContext/RelationalMappingContext:

~~~java
mappingContext.setSingleQueryLoadingEnabled(true);
~~~

Nếu ứng dụng dùng cấu hình JDBC tường minh dựa trên AbstractJdbcConfiguration, có thể tùy chỉnh bean mapping context hiện có:

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.core.convert.JdbcCustomConversions;
import org.springframework.data.jdbc.core.mapping.JdbcMappingContext;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;
import org.springframework.data.relational.core.mapping.NamingStrategy;
import org.springframework.data.relational.core.mapping.RelationalManagedTypes;

@Configuration
@EnableJdbcRepositories
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    @Bean
    public JdbcMappingContext jdbcMappingContext(
            Optional<NamingStrategy> namingStrategy,
            JdbcCustomConversions customConversions,
            RelationalManagedTypes jdbcManagedTypes
    ) {
        JdbcMappingContext context = super.jdbcMappingContext(
                namingStrategy,
                customConversions,
                jdbcManagedTypes
        );

        context.setSingleQueryLoadingEnabled(true);

        return context;
    }
}
~~~

Đây là ví dụ khi ứng dụng sở hữu cấu hình JDBC theo kiểu Java configuration. Nếu Spring Boot đã tạo mapping context tự động hoặc project đã có lớp cấu hình kế thừa AbstractJdbcConfiguration, hãy tùy chỉnh bean hiện có theo cấu trúc của ứng dụng. Không tạo một JdbcMappingContext thứ hai chỉ để bật flag, vì converter và aggregate operations phải dùng cùng mapping context.

### 8.2. Điều kiện hỗ trợ

Single Query Loading có các giới hạn cần kiểm tra trước khi kỳ vọng query count giảm:

| Điều kiện | Giới hạn |
|---|---|
| Version | Có từ Spring Data JDBC 3.2 |
| Collection | Aggregate không có nested collections; giới hạn này bao gồm Map |
| Embedded/reference | Aggregate không dùng AggregateReference hoặc embedded entities |
| Database dialect | Dialect phải hỗ trợ analytic/window functions; các dialect Spring Data JDBC cung cấp ngoại trừ H2 và HSQL hỗ trợ |
| Repository method | Chỉ áp dụng cho các find methods của CrudRepository; derived query và annotated query không nằm trong phạm vi hiện tại |
| Cấu hình | Phải bật setSingleQueryLoadingEnabled(true) |

Nếu một điều kiện không đáp ứng, Spring Data JDBC quay về cách tải aggregate mặc định. Vì vậy, bật flag chưa đủ để chứng minh endpoint đã dùng Single Query Loading.

Tài liệu Spring Data Relational hiện vẫn mô tả tính năng này là experimental. Hãy kiểm thử trên database/dialect thực tế và kiểm tra SQL log sau khi bật.

Tài liệu: https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html

### 8.3. H2 và HSQL trong kiểm thử

H2 và HSQL không hỗ trợ các analytic/window function cần cho cơ chế này theo các dialect được Spring Data JDBC cung cấp. Do đó, test chạy trên hai database này có thể rơi về cách tải mặc định.

Nếu mục tiêu là xác nhận Single Query Loading hoạt động, hãy chạy integration test với database có dialect hỗ trợ, ví dụ PostgreSQL, MySQL hoặc một hệ quản trị khác được phiên bản Spring Data JDBC của project hỗ trợ.

Không kết luận tính năng không hoạt động chỉ từ kết quả test trên H2/HSQL. Cũng không kết luận đã hoạt động chỉ vì cấu hình flag không báo lỗi.

## 9. Giảm chi phí khi Single Query Loading không áp dụng được

Không phải aggregate nào cũng đáp ứng điều kiện Single Query Loading. Một số hướng xử lý khác:

### 9.1. Giới hạn số aggregate mỗi lần tải

Dùng pagination để chỉ tải một số root cho mỗi request:

~~~java
public interface OrderRepository
        extends CrudRepository<Order, Long>,
                PagingAndSortingRepository<Order, Long> {
}

Page<Order> page = orderRepository.findAll(
        PageRequest.of(0, 20, Sort.by("id").descending())
);
~~~

Pagination không tự loại bỏ N+1 trong cách tải truyền thống. Tuy nhiên, nó giới hạn số root N trong một request và làm chi phí truy vấn collection dễ kiểm soát hơn.

Đừng tải toàn bộ bảng để phục vụ một màn hình danh sách nếu người dùng chỉ xem một trang dữ liệu.

### 9.2. Chỉ tải dữ liệu mà màn hình cần

Một màn hình danh sách có thể chỉ cần ID đơn hàng, mã đơn, trạng thái, ngày tạo và tổng tiền. Nếu không cần toàn bộ OrderLine, không nhất thiết phải tải đầy đủ aggregate cho list view. Có thể tạo custom repository query trả DTO/read model chứa đúng các cột cần thiết.

Ví dụ projection:

~~~java
public record OrderListItem(
        Long id,
        String orderNumber,
        String status,
        BigDecimal totalAmount
) {}
~~~

Custom query có thể tính tổng tiền ở database và trả trực tiếp OrderListItem. Cách này tránh dựng toàn bộ object graph chỉ để hiển thị một bảng.

Hãy giữ ranh giới rõ: custom query phục vụ read model/list view; thao tác nghiệp vụ cần aggregate đầy đủ vẫn có thể dùng repository aggregate.

### 9.3. Batch-load child data theo danh sách parent ID

Khi cần hiển thị dữ liệu con nhưng Single Query Loading không phù hợp, có thể tải root trước rồi lấy tất cả child rows trong một truy vấn theo danh sách parent IDs.

SQL minh họa:

~~~sql
SELECT id, order_id, sku, quantity
FROM order_lines
WHERE order_id IN (:orderIds)
ORDER BY order_id, id;
~~~

Sau đó nhóm kết quả theo order_id trong Java:

~~~java
Map<Long, List<OrderLineView>> linesByOrderId =
        lineViews.stream().collect(
                Collectors.groupingBy(OrderLineView::orderId)
        );
~~~

Cách này biến N truy vấn child thành một truy vấn batch cho cả trang. Nó phù hợp với read model hoặc custom repository fragment. Nếu tự dựng aggregate đầy đủ, cần xử lý đúng mapping, thứ tự collection, transaction consistency và các property path; không nên bỏ qua aggregate semantics của Spring Data JDBC.

Với danh sách ID rất lớn, kiểm tra giới hạn bind parameter của database/driver và chia batch theo kích thước phù hợp.

### 9.4. Tránh truy vấn từng aggregate trong vòng lặp

Nếu đã có danh sách ID, ưu tiên một thao tác findAllById thay vì gọi findById nhiều lần.

Nếu dữ liệu liên quan thuộc aggregate khác, có thể batch-load các aggregate đó theo tập ID rồi lập map tra cứu. Chỉ dùng cách này khi chúng thực sự là aggregate độc lập; không chuyển entity con thuộc cùng aggregate thành aggregate riêng chỉ để né query count.

### 9.5. Cẩn thận với JOIN nhiều collection

Một truy vấn JOIN root với một collection có thể giảm số round-trip. Nhưng khi JOIN nhiều collection một-nhiều, kết quả có thể tạo cross product.

Ví dụ một đơn có 4 dòng hàng và 3 lịch sử trạng thái. JOIN cả hai collection có thể trả 12 dòng cho cùng một đơn. Khi dữ liệu con tăng, số hàng trung gian và dữ liệu lặp có thể rất lớn.

Single Query Loading sử dụng chiến lược result set với window functions để tránh cách nhân chéo đơn giản này. Nếu tự viết JOIN, hãy đo số dòng trả về và dung lượng dữ liệu truyền qua mạng, không chỉ đếm số statement.

## 10. Query count không phải chỉ số hiệu năng duy nhất

Giảm số câu SQL thường giúp giảm round-trip và overhead, nhưng một truy vấn duy nhất vẫn có thể rất chậm.

Theo dõi ít nhất các chỉ số:

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| Query count | Một request phát bao nhiêu statement? |
| SQL fingerprint frequency | Câu nào bị gọi lặp nhiều lần? |
| Total database time | Tổng thời gian chờ database là bao lâu? |
| Slowest statement | Statement nào có latency cao nhất? |
| Rows returned | Mỗi query trả về bao nhiêu dòng? |
| Rows scanned | Database phải đọc bao nhiêu dòng để tìm kết quả? |
| Payload size | Có truyền quá nhiều dữ liệu lặp qua network không? |
| Request latency | Người dùng thực sự chờ bao lâu? |
| Connection usage | Request giữ connection trong bao lâu? |

Ví dụ:

- 100 query rất nhanh nhưng mỗi query đều có round-trip sẽ gây overhead.
- 1 query JOIN trả 100.000 dòng cũng có thể chậm và tốn bộ nhớ.
- 1 query có predicate không dùng index có thể quét toàn bảng.
- Query count thấp nhưng entity callback/listener làm nhiều công việc Java vẫn có thể khiến request chậm.

Dùng query plan như EXPLAIN hoặc công cụ tương ứng của database để đánh giá statement chậm. Kiểm tra index trên foreign key của collection, chẳng hạn order_lines(order_id), nếu truy vấn thường lọc theo parent ID.

## 11. Lifecycle events cũng có thể ảnh hưởng thời gian tải

Spring Data JDBC phát lifecycle events cho aggregate. Tài liệu chính thức lưu ý lifecycle events có thể tốn chi phí và làm thay đổi hiệu năng khi tải result set lớn.

Nếu query count đã ổn nhưng thời gian materialize aggregate vẫn cao, hãy kiểm tra:

- Listener có thực hiện xử lý nặng không?
- Listener có gọi repository để lấy thêm dữ liệu không?
- Có listener logging toàn bộ entity hoặc serialize object lớn không?
- Callback có thực hiện phép tính hoặc truy cập tài nguyên bên ngoài không?

JdbcAggregateTemplate cung cấp setEntityLifecycleEventsEnabled(false) để tắt việc phát lifecycle events khi phù hợp. Đây là lựa chọn ảnh hưởng tới semantics event của ứng dụng, vì vậy chỉ dùng khi đã xác định listener không cần chạy trên đường tải đó.

Không nhầm lifecycle events với entity callbacks. Spring Data JDBC dùng callback cho các chức năng như auditing; tắt event publication không đồng nghĩa tắt mọi entity callback.

Tài liệu: https://docs.spring.io/spring-data/relational/reference/jdbc/events.html

## 12. Thiết kế kiểm thử để phát hiện N+1

Một integration test có thể kiểm tra xu hướng query count khi tăng số aggregate. Dùng DataSource proxy hoặc công cụ đếm statement để lấy số query trong phạm vi lời gọi repository.

Ví dụ test case cần có:

1. Tạo 1 aggregate root có collection con.
2. Đếm query khi gọi findAll.
3. Tạo 10 aggregate root có cùng cấu trúc.
4. Đếm query khi gọi lại findAll.
5. So sánh số query và xác định statement nào lặp.

Kết quả minh họa với cách tải truyền thống và một collection:

| Dữ liệu | Root SELECT | Child SELECT | Tổng |
|---|---:|---:|---:|
| 1 root | 1 | 1 | 2 |
| 10 roots | 1 | 10 | 11 |
| 50 roots | 1 | 50 | 51 |

Nếu bật Single Query Loading và aggregate đáp ứng điều kiện, kiểm tra lại số statement. Đừng chỉ assert tổng số query tuyệt đối nếu test framework còn phát các câu SQL khởi tạo, cleanup hoặc count. Hãy lọc theo SQL fingerprint của use case.

### 12.1. Test trên database mục tiêu

Các yếu tố có thể khác giữa H2 và database production:

- Hỗ trợ window function.
- SQL dialect và cách tạo query.
- Query planner và index.
- Driver behavior.
- Kiểu dữ liệu và collation.

Dùng Testcontainers hoặc database integration environment cùng hệ quản trị với production khi cần kiểm tra hiệu năng và cơ chế Single Query Loading.

### 12.2. Không để test phụ thuộc thời gian tuyệt đối

Không nên viết test kiểu “request phải chạy dưới 50 ms” trên mọi máy. Thời gian phụ thuộc CPU, database, container và môi trường CI.

Để phát hiện N+1, kiểm tra số statement theo một SQL fingerprint và xu hướng tăng theo N thường ổn định hơn kiểm tra một ngưỡng latency cứng. Performance benchmark có thể đo latency riêng trong môi trường được kiểm soát.

## 13. Quy trình điều tra một endpoint chậm

Khi endpoint tải danh sách aggregate chậm, có thể thực hiện theo thứ tự:

1. Xác định repository/service method tạo danh sách.
2. Ghi SQL log hoặc bật DataSource query tracing trong môi trường kiểm thử.
3. Nhóm SQL theo fingerprint và đếm số lần chạy.
4. Kiểm tra câu SELECT nào lặp theo từng parent ID.
5. Thử tăng page size trong khi giữ nguyên filter.
6. Phân biệt relation loading với repository call trong vòng lặp.
7. Đo tổng database time, latency từng statement và số dòng trả về.
8. Kiểm tra JdbcMappingContext và điều kiện Single Query Loading.
9. Nếu tính năng không áp dụng được, cân nhắc pagination, projection hoặc batch-load child rows.
10. Đo lại bằng cùng dữ liệu và cùng kịch bản để xác nhận thay đổi thực sự giảm query count/latency.

Không tối ưu dựa trên số query duy nhất. Hãy xem cả số hàng trả về, index, query plan và chi phí dựng object graph.

## 14. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| findAll chỉ có một dòng code nhưng phát nhiều SELECT | Aggregate có collection được tải riêng cho từng root | Nhóm SQL theo fingerprint và kiểm tra N+1 |
| Cùng SELECT child lặp với parent ID khác nhau | Cơ chế tải collection truyền thống | Đánh giá Single Query Loading hoặc batch loading |
| Query count tăng theo page size | Có statement được thực thi cho mỗi aggregate | Xác định relation path và giới hạn số root |
| Gọi findById nhiều lần | Service hoặc mapper có repository call trong vòng lặp | Dùng findAllById hoặc batch query |
| Bật Single Query Loading nhưng query vẫn lặp | Aggregate/method/dialect không đáp ứng điều kiện | Kiểm tra giới hạn và xác nhận SQL log |
| Test H2 vẫn cho N+1 | H2 không hỗ trợ analytic functions cần cho Single Query Loading | Kiểm thử trên database dialect được hỗ trợ |
| Query count thấp nhưng request vẫn chậm | Query nặng, trả quá nhiều hàng hoặc Java mapping/listener tốn thời gian | Đo DB time, rows, payload và lifecycle listener |
| JOIN giảm query nhưng trả rất nhiều dòng | Cross product giữa nhiều collection | Đo số hàng trung gian; cân nhắc Single Query Loading hoặc batch fetch |
| Dùng pagination nhưng vẫn thấy N+1 | Pagination chỉ giới hạn N, không tự đổi chiến lược load | Kết hợp pagination với chiến lược tải phù hợp |
| DTO mapping phát thêm SELECT | Mapper gọi repository cho từng item | Batch-load dữ liệu tham chiếu trước khi dựng DTO |
| SQL log không hiện đầy đủ parameter | Chưa bật logger phù hợp hoặc dùng proxy khác | Dùng JDBC logging/DataSource proxy |
| Test query count không ổn định | Đếm cả SQL setup/cleanup hoặc query phụ của test | Giới hạn phạm vi đếm và lọc SQL fingerprint |
| Tắt lifecycle events nhưng callback vẫn chạy | Nhầm event publication với entity callbacks | Phân biệt hai cơ chế và giữ callback cần thiết |

## 15. Bài tập thực hành

### Bài 1 — Quan sát tải aggregate

Tạo Order có List<OrderLine>. Gọi findAll() với 1, 10 và 50 root. Bật SQL logging và ghi lại số lần câu SELECT của order_lines được thực thi.

### Bài 2 — Tính query growth

Tạo aggregate có hai collection độc lập. So sánh query count khi có 1, 10 và 20 aggregate. Đối chiếu số liệu với công thức gần đúng 1 + N × K.

### Bài 3 — Phân biệt hai nguồn N+1

Viết một service gọi findById trong vòng lặp. Sau đó thay bằng findAllById. So sánh log với trường hợp một lần findAll tải aggregate có collection con.

### Bài 4 — Bật Single Query Loading

Dùng Spring Data JDBC 3.2 trở lên và database hỗ trợ window functions. Bật setSingleQueryLoadingEnabled(true), gọi CrudRepository.findAll() và quan sát SQL. Xác nhận aggregate của bài tập đáp ứng các giới hạn.

### Bài 5 — Kiểm tra fallback

Thêm nested collection hoặc dùng derived query. Quan sát cách tải mặc định khi Single Query Loading không áp dụng được. Ghi lại điều kiện nào khiến framework fallback.

### Bài 6 — Batch-load cho list view

Tạo DTO chỉ chứa thông tin order và các dòng hàng cần hiển thị. Thực hiện một truy vấn lấy child rows theo danh sách order IDs, nhóm kết quả theo parent ID và so sánh với aggregate loading truyền thống.

### Bài 7 — Đánh giá JOIN nhiều collection

Viết một truy vấn JOIN orders, order_lines và order_events. Tạo dữ liệu có nhiều dòng hàng và nhiều event cho một order. Đo số hàng result set để nhận diện cross product.

### Bài 8 — Đo lifecycle listener

Thêm listener AfterConvertEvent có xử lý nhẹ và sau đó mô phỏng listener thực hiện truy vấn phụ. Đo query count và latency. Xác định tác động của listener đối với đường tải aggregate.

## 16. Ghi nhớ

- Tải danh sách aggregate có collection con có thể tạo N+1 query trong cách tải truyền thống của Spring Data JDBC.
- Mẫu thường gặp là một SELECT lấy root, sau đó cùng một SELECT collection được chạy lại với parent ID khác nhau.
- Với một collection, query count gần đúng là 1 + N; với K collection path được tải riêng, có thể gần 1 + N × K.
- Spring Data JDBC dựng aggregate trong quá trình load; không mặc định quy vấn đề này cho lazy-loading proxy như một số ORM.
- Bật SQL logging hoặc DataSource query tracing để nhóm statement theo fingerprint và đo số lần thực thi.
- Phân biệt relation loading với vòng lặp gọi findById, DTO mapper hoặc listener tự truy vấn.
- Single Query Loading có từ Spring Data JDBC 3.2, cần bật trên mapping context và chỉ áp dụng khi aggregate, repository method và database đáp ứng giới hạn.
- Single Query Loading hiện được tài liệu mô tả là experimental; nếu không đủ điều kiện, framework fallback về cách tải mặc định.
- Pagination giới hạn số aggregate nhưng không tự loại bỏ N+1; projection và batch-load có thể phù hợp cho list view.
- Query count không thay thế latency, query plan, rows returned, payload size và chi phí materialize object graph.
- Lifecycle events có thể tăng chi phí khi tải result set lớn; phân biệt event publication với entity callbacks trước khi thay đổi cấu hình.

## Tài liệu tham khảo

- [Spring Data Relational — Persisting Entities and Loading Aggregates](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Blog — Introducing Single Query Loading](https://spring.io/blog/2023/08/31/this-is-the-beginning-of-the-end-of-the-n-1-problem-introducing-single-query/)
- [RelationalMappingContext API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/RelationalMappingContext.html)
- [JdbcMappingContext API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/mapping/JdbcMappingContext.html)
- [Spring Data Relational — Lifecycle Events](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html)
- [JdbcAggregateTemplate API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateTemplate.html)
