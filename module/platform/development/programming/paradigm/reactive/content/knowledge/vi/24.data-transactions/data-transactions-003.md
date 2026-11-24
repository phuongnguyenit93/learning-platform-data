# Dữ liệu và giao dịch

## Quản lý nhóm kết nối và giới hạn số truy vấn đồng thời

Một ứng dụng reactive có thể tiếp nhận nhiều yêu cầu cùng lúc mà không cần giữ một thread riêng cho mỗi lần chờ cơ sở dữ liệu. Tuy vậy, cơ sở dữ liệu vẫn có giới hạn về số kết nối, số truy vấn đang chạy và tài nguyên dùng để thực thi truy vấn. Nếu ứng dụng mở quá nhiều kết nối hoặc gửi truy vấn đồng thời vượt khả năng của database, độ trễ sẽ tăng, hàng đợi phình to và các request có thể hết thời gian chờ.

Trong Java reactive, nhóm kết nối (connection pool) và giới hạn truy vấn đồng thời giải quyết hai phần liên quan nhưng khác nhau. Pool giới hạn số kết nối database mà ứng dụng mượn cùng lúc, đồng thời quản lý việc tạo, tái sử dụng và trả kết nối. Các toán tử như **flatMap** giới hạn số thao tác truy vấn mà một pipeline khởi chạy đồng thời. Kết hợp hai cơ chế giúp điều tiết tải từ ứng dụng đến database.

### 1. Vì sao ứng dụng reactive vẫn cần giới hạn kết nối?

I/O non-blocking giúp thread không phải đứng chờ trong lúc database xử lý. Nó không làm cho database có khả năng xử lý vô hạn. Mỗi kết nối vẫn tiêu thụ tài nguyên ở database và ở ứng dụng; mỗi truy vấn vẫn dùng CPU, bộ nhớ, khóa, buffer và I/O của database.

Nếu một endpoint nhận hàng nghìn yêu cầu và mỗi yêu cầu mở một kết nối mới, số kết nối có thể vượt giới hạn database. Nếu tất cả request cùng phát nhiều truy vấn, database có thể bị quá tải dù server web vẫn tiếp nhận request bình thường.

Pool cung cấp một giới hạn hữu hình cho số kết nối được cấp phát. Khi tất cả kết nối đang được sử dụng, yêu cầu mượn kết nối mới phải chờ một kết nối được trả lại, hoặc thất bại khi vượt thời gian chờ. Việc chờ được quản lý ở tầng pool; nó vẫn cần giới hạn để tránh tích tụ vô hạn.

~~~text
Nhiều HTTP request
        |
        v
Các pipeline Mono / Flux
        |
        v
Giới hạn truy vấn đồng thời
        |
        v
R2DBC Connection Pool
   |       |       |
   v       v       v
 Conn 1  Conn 2  Conn N
   |       |       |
   +-------+-------+
           |
           v
        Database
~~~

### 2. Pool quản lý vòng đời kết nối như thế nào?

Một R2DBC connection pool thường quản lý các bước:

1. Tạo một số kết nối ban đầu theo cấu hình.
2. Cấp kết nối đang rảnh khi một Publisher cần truy cập database.
3. Tạo kết nối mới nếu chưa đạt giới hạn và có nhu cầu.
4. Đưa yêu cầu mượn kết nối vào hàng đợi khi mọi kết nối đều đang được sử dụng.
5. Thu hồi kết nối không còn phù hợp hoặc đã vượt thời gian sống.
6. Trả kết nối về pool khi thao tác hoặc transaction kết thúc.

Pool tái sử dụng kết nối để tránh chi phí mở và đóng kết nối liên tục. Một kết nối được trả về pool không đồng nghĩa socket vật lý luôn bị đóng; pool có thể giữ nó ở trạng thái idle để request tiếp theo sử dụng.

Với R2DBC, có thể dùng thư viện **r2dbc-pool** để bọc một **ConnectionFactory** do driver cung cấp. **ConnectionPool** đóng vai trò **ConnectionFactory** ở phía ứng dụng:

~~~java
import java.time.Duration;

import io.r2dbc.pool.ConnectionPool;
import io.r2dbc.pool.ConnectionPoolConfiguration;
import io.r2dbc.spi.ConnectionFactory;

ConnectionPoolConfiguration configuration =
    ConnectionPoolConfiguration.builder(driverConnectionFactory)
        .initialSize(5)
        .maxSize(20)
        .maxIdleTime(Duration.ofMinutes(10))
        .maxLifeTime(Duration.ofMinutes(30))
        .maxAcquireTime(Duration.ofSeconds(5))
        .maxCreateConnectionTime(Duration.ofSeconds(3))
        .build();

ConnectionPool pool = new ConnectionPool(configuration);
~~~

Ví dụ cấu hình tạo ban đầu năm kết nối và cho phép tối đa hai mươi kết nối. Một yêu cầu mượn kết nối chỉ được chờ tối đa năm giây; thời gian tạo kết nối mới cũng có giới hạn. Các giá trị này chỉ là điểm bắt đầu để minh họa. Cần chọn theo driver, phiên bản r2dbc-pool, giới hạn database và tải thực tế.

Trong ứng dụng Spring, nên đăng ký pool như một bean **ConnectionFactory** và để Spring quản lý vòng đời của nó. Khi ứng dụng dừng, pool cần được dispose/đóng đúng cách để giải phóng kết nối và tài nguyên.

### 3. Ý nghĩa các giới hạn của pool

Các thuộc tính cấu hình thường có vai trò khác nhau:

| Thuộc tính | Ý nghĩa | Khi điều chỉnh |
| --- | --- | --- |
| **initialSize** | Số kết nối tạo sẵn khi pool khởi tạo | Tăng nếu cần sẵn sàng phục vụ ngay, nhưng tránh tạo kết nối không cần thiết |
| **maxSize** | Số kết nối tối đa pool có thể cấp phát | Đặt theo ngân sách kết nối của database và số instance ứng dụng |
| **maxIdleTime** | Thời gian một kết nối có thể ở trạng thái idle | Giảm kết nối rảnh khi tải thấp |
| **maxLifeTime** | Thời gian sống tối đa của một kết nối | Làm mới kết nối lâu năm theo chính sách hạ tầng |
| **maxAcquireTime** | Thời gian tối đa chờ mượn kết nối | Ngăn request chờ pool vô hạn |
| **maxCreateConnectionTime** | Thời gian tối đa để tạo kết nối mới | Giới hạn thời gian chờ khi database hoặc mạng gặp vấn đề |

Một số phiên bản và cấu hình pool còn hỗ trợ giới hạn số yêu cầu đang chờ mượn kết nối, kiểm tra tính hợp lệ của kết nối và thu thập metrics. Tên thuộc tính hoặc overload có thể thay đổi theo phiên bản. Hãy kiểm tra API đúng với dependency của dự án thay vì sao chép cấu hình từ một phiên bản khác.

**maxAcquireTime** khác với timeout của truy vấn. Acquire timeout giới hạn thời gian chờ lấy connection từ pool; query timeout giới hạn thời gian thực thi thao tác database sau khi đã có connection. HTTP timeout lại giới hạn thời gian request ở tầng web. Cần phân biệt ba mốc này để xác định đúng nơi gây chậm.

### 4. Tính ngân sách kết nối trên toàn hệ thống

**maxSize** áp dụng cho một pool trong một tiến trình. Nếu ứng dụng chạy nhiều replica, tổng số kết nối tối đa có thể tăng theo số instance:

\[
\text{Tổng kết nối tối đa}
=
\text{maxSize mỗi instance}
\times
\text{số instance}
\]

Ví dụ, nếu có bốn replica và mỗi replica cho phép tối đa hai mươi kết nối, riêng dịch vụ này có thể mở tới tám mươi kết nối. Database còn phải dành chỗ cho các dịch vụ khác, tác vụ nền, migration, quản trị và kết nối dự phòng.

Không đặt **maxSize** bằng toàn bộ giới hạn connection của database. Hãy lập ngân sách cho tất cả client cùng truy cập database, dành một phần cho hoạt động vận hành và tránh để các service tranh hết kết nối của nhau.

| Thông số minh họa | Giá trị |
| --- | ---: |
| Giới hạn kết nối database | 120 |
| Dự phòng cho quản trị, migration và tác vụ khác | 20 |
| Ngân sách cho ứng dụng | 100 |
| Số replica ứng dụng | 5 |
| **maxSize** đề xuất ban đầu mỗi replica | 20 |

Các con số trên chỉ minh họa phép tính ngân sách. Giá trị triển khai cần xét số truy vấn thực tế, thời gian giữ connection, giới hạn database và tải cao điểm.

### 5. Giới hạn truy vấn đồng thời bằng flatMap

Pool giới hạn số connection được mượn, còn **flatMap** giới hạn số Publisher con được đăng ký đồng thời trong một subscription. Khi xử lý một danh sách ID, có thể đặt concurrency tường minh:

~~~java
import reactor.core.publisher.Flux;

Flux<OrderSummary> summaries =
    Flux.fromIterable(orderIds)
        .flatMap(this::findOrderSummary, 8);
~~~

Với concurrency bằng tám, một subscription của pipeline chỉ đăng ký tối đa tám thao tác tra cứu con cùng lúc. Khi một thao tác hoàn tất, toán tử có thể đăng ký thao tác tiếp theo. Điều này tránh phát hàng trăm truy vấn đồng thời từ một lần xử lý batch.

Ví dụ phương thức truy vấn dùng Spring **DatabaseClient**:

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Mono;

record OrderSummary(Long id, String status) {}

Mono<OrderSummary> findOrderSummary(Long id) {
    return databaseClient.sql("""
            SELECT id, status
            FROM orders
            WHERE id = :id
            """)
        .bind("id", id)
        .map((row, metadata) -> new OrderSummary(
            row.get("id", Long.class),
            row.get("status", String.class)
        ))
        .one();
}
~~~

**DatabaseClient** làm việc với **ConnectionFactory** và quản lý việc lấy/trả connection cho thao tác. Trong pipeline batch, **flatMap** giới hạn số lời gọi **findOrderSummary** đang hoạt động từ subscription đó.

### 6. Concurrency của flatMap không phải giới hạn toàn ứng dụng

Một điểm dễ nhầm là concurrency của **flatMap** thường áp dụng cho từng subscription. Nếu một endpoint có ba mươi request đồng thời và mỗi request dùng **flatMap(..., 8)**, tổng số Publisher con có thể được đăng ký trên toàn ứng dụng lớn hơn tám rất nhiều.

Ví dụ, ba mươi request cùng xử lý batch có thể tạo nhu cầu lên đến 240 thao tác tra cứu. Pool **maxSize=20** vẫn chỉ cấp tối đa hai mươi connection tại một thời điểm; những yêu cầu còn lại có thể chờ pool. Vì vậy, hai giới hạn này giải quyết hai phạm vi khác nhau:

| Cơ chế | Phạm vi | Điều được giới hạn |
| --- | --- | --- |
| **flatMap(mapper, concurrency)** | Một subscription | Số Publisher con đang được đăng ký đồng thời trong pipeline đó |
| R2DBC pool **maxSize** | Một pool trong một tiến trình | Số connection được pool cấp phát đồng thời |
| Giới hạn toàn ứng dụng/bulkhead | Phạm vi do ứng dụng thiết kế | Số tác vụ database đang hoạt động qua nhiều request |
| Database connection limit | Toàn database hoặc user/database role | Số kết nối database chấp nhận |

Pool là lớp bảo vệ cuối cùng cho số kết nối, nhưng nó không nhất thiết giới hạn số request đang chờ. Nếu lưu lượng đầu vào quá lớn, hàng đợi acquire có thể tăng và làm độ trễ cao. Khi cần giới hạn tải toàn ứng dụng, hãy bổ sung admission control hoặc bulkhead ở tầng service, đồng thời giới hạn hàng đợi chờ của pool theo khả năng phiên bản thư viện.

### 7. Kết hợp backpressure với giới hạn truy vấn

Backpressure cho phép downstream yêu cầu số phần tử mà nó có thể xử lý. Với một nguồn hữu hạn, **flatMap** dùng demand và concurrency để điều phối việc tạo các Publisher con. Khi đạt giới hạn concurrency, các phần tử nguồn tiếp theo sẽ được giữ lại theo cơ chế prefetch của toán tử cho đến khi có chỗ trống.

~~~java
import reactor.core.publisher.Flux;

Flux<ImportResult> importOrders =
    Flux.fromIterable(orderIds)
        .flatMap(
            id -> orderService.importOne(id),
            6,
            1
        );
~~~

Trong ví dụ:

- **6** giới hạn số thao tác import đang hoạt động trong subscription.
- **1** là prefetch của **flatMap**, tức lượng phần tử được yêu cầu trước từ mỗi Publisher con theo cấu hình của toán tử.

Concurrency quyết định số nhánh con hoạt động; prefetch ảnh hưởng lượng phần tử được yêu cầu trước và có thể đang chờ. Tăng concurrency có thể cải thiện thông lượng khi database còn dư tài nguyên, nhưng cũng tăng số connection được yêu cầu và áp lực lên database.

Backpressure không tự tạo giới hạn toàn cục nếu có nhiều subscription độc lập. Nó cũng không thể làm một database xử lý nhanh hơn. Hãy kết hợp demand, concurrency của pipeline và giới hạn connection để điều tiết tải ở nhiều lớp.

### 8. Tránh giữ connection lâu hơn cần thiết

Connection nên được giữ trong khoảng thời gian thực hiện truy vấn hoặc transaction cần nó. Nếu ứng dụng lấy connection rồi thực hiện thêm công việc không liên quan như gọi HTTP bên ngoài, chờ người dùng hoặc tính toán dài, connection sẽ bị chiếm dụng trong khi database không được sử dụng.

Các API cấp cao như **DatabaseClient** và Spring Data R2DBC tự quản lý vòng đời connection cho từng thao tác. Khi cần thao tác trực tiếp với connection, hãy gắn cleanup với vòng đời Publisher, kể cả khi hoàn tất, lỗi hoặc cancellation:

~~~java
import io.r2dbc.spi.Connection;
import io.r2dbc.spi.ConnectionFactory;
import reactor.core.publisher.Mono;

Mono<ResultSummary> executeWithConnection(
    ConnectionFactory connectionFactory
) {
    return Mono.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> executeQuery(connection),
        connection -> Mono.from(connection.close())
    );
}
~~~

**usingWhen** lấy tài nguyên khi có subscription và chạy cleanup khi Publisher kết thúc. Trong ví dụ, **executeQuery** đại diện cho hàm thực thi truy vấn và ánh xạ kết quả thành **Mono<ResultSummary>**. Nếu cần cleanup khác nhau cho hoàn tất, lỗi và cancellation, dùng overload **usingWhen** có các hàm cleanup tương ứng.

Không lưu connection vào field dùng chung hoặc tự chia sẻ một connection cho nhiều request độc lập. Connection có trạng thái transaction và giao thức thực thi riêng; hãy để pool cấp connection theo từng phạm vi sử dụng phù hợp.

### 9. Transaction giữ connection trong suốt phạm vi giao dịch

Một reactive transaction thường gắn connection với Reactor Context trong phạm vi transaction. Các thao tác database tham gia cùng transaction có thể dùng connection đã được ràng buộc cho transaction đó. Connection chỉ được trả lại pool khi transaction kết thúc và cleanup hoàn tất.

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

TransactionalOperator tx =
    TransactionalOperator.create(transactionManager);

Mono<Void> createOrder =
    orderRepository.insert(order)
        .then(inventoryRepository.reserve(order.items()))
        .then(paymentRepository.recordPending(order.id()))
        .as(tx::transactional);
~~~

Ví dụ minh họa ba thao tác tham gia cùng một transaction. Trong thực tế, cần khai báo **transactionManager** phù hợp với **ConnectionFactory** và kiểm tra các repository cùng tham gia transaction đó.

Transaction giữ connection lâu hơn một truy vấn đơn lẻ. Nếu bên trong transaction có gọi dịch vụ HTTP hoặc chờ một tác vụ không liên quan đến database, connection có thể bị giữ trong suốt thời gian chờ đó. Hãy giữ transaction ngắn, chỉ bao quanh các thao tác cần tính nguyên tử ở database.

Không nên mặc định chạy nhiều truy vấn đồng thời trên cùng một transaction/connection bằng **flatMap**. Driver hoặc database có thể không hỗ trợ nhiều statement đồng thời trên một connection; thứ tự thực thi và tính nhất quán cũng có thể bị ảnh hưởng. Với các thao tác phụ thuộc trong cùng transaction, ưu tiên nối tuần tự bằng **then**, **concatMap** hoặc pipeline tuần tự tương đương.

### 10. Chọn concurrency theo thời gian giữ connection

Số kết nối cần thiết phụ thuộc vào số thao tác đồng thời và thời gian trung bình mỗi thao tác giữ connection. Một truy vấn rất nhanh có thể dùng chung pool nhỏ với nhiều request; một truy vấn chậm hoặc transaction kéo dài sẽ chiếm connection lâu hơn.

Một ước lượng trực giác dựa trên thông lượng:

\[
\text{Số truy vấn đang hoạt động trung bình}
\approx
\text{Tốc độ truy vấn mỗi giây}
\times
\text{Thời gian giữ connection tính bằng giây}
\]

Ví dụ, nếu hệ thống thực hiện trung bình 100 truy vấn mỗi giây và mỗi truy vấn giữ connection khoảng 0,1 giây, số truy vấn đang hoạt động trung bình vào khoảng 10. Đây là ước lượng theo tải trung bình; giờ cao điểm, phân bố độ trễ và transaction dài có thể cần thêm dung lượng dự phòng.

Không nên tăng pool size để chữa mọi vấn đề hiệu năng. Nếu truy vấn chậm do thiếu index, khóa tranh chấp hoặc kế hoạch thực thi kém, thêm connection có thể làm database chịu tải lớn hơn và khiến độ trễ xấu đi. Hãy tối ưu truy vấn và transaction trước khi tăng giới hạn.

### 11. Timeout và hàng đợi chờ connection

Khi pool hết connection, các yêu cầu mới chờ một connection được trả lại. Một hàng đợi chờ quá dài có thể khiến request tích tụ, tiêu thụ bộ nhớ và cuối cùng hết timeout ở tầng HTTP.

Nên thiết lập các giới hạn có chủ đích:

- **Acquire timeout:** thời gian tối đa chờ lấy connection từ pool.
- **Connection creation timeout:** thời gian tối đa để tạo connection mới.
- **Query timeout:** thời gian tối đa chờ truy vấn hoàn tất nếu driver/API hỗ trợ.
- **Request timeout:** thời gian tối đa dành cho toàn bộ request ở tầng web.
- **Pending acquire limit:** giới hạn số yêu cầu đang chờ mượn connection nếu phiên bản pool hỗ trợ.

Các timeout nên phối hợp theo thứ tự hợp lý. Ví dụ, acquire timeout cần ngắn hơn request timeout để ứng dụng có thể trả lỗi quá tải có kiểm soát trước khi request hết hạn. Query timeout cần phản ánh SLA và đặc tính truy vấn; đặt quá thấp có thể hủy các truy vấn hợp lệ.

Khi acquire timeout xảy ra, cần phân biệt đó là pool cạn connection, database không phản hồi hay kết nối không thể tạo mới. Metrics và log có ngữ cảnh giúp xác định nguyên nhân thay vì chỉ ghi nhận một lỗi chung.

### 12. Giám sát sức khỏe của pool

Một pool được cấu hình tốt cần được quan sát trong điều kiện tải thật. Những chỉ số hữu ích gồm:

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| Số connection đang được sử dụng (acquired/active) | Pool có thường xuyên chạm **maxSize** không? |
| Số connection idle | Có quá nhiều connection rảnh hoặc pool không đủ connection sẵn sàng? |
| Số connection đã tạo/allocated | Pool có liên tục mở và loại bỏ connection không? |
| Số yêu cầu đang chờ acquire | Có hiện tượng pool saturation không? |
| Thời gian acquire trung bình và phân vị cao | Request mất bao lâu để lấy được connection? |
| Số acquire timeout | Có request bị từ chối do không lấy được connection không? |
| Thời gian truy vấn và transaction | Connection bị giữ lâu ở thao tác nào? |
| Lỗi tạo hoặc xác thực connection | Database, mạng hoặc credential có vấn đề không? |

Nếu pool thường xuyên đạt **maxSize** và acquire latency tăng, hãy xem xét truy vấn chậm, transaction dài, concurrency quá cao hoặc pool quá nhỏ. Nếu số connection idle luôn cao, có thể pool đang cấp phát nhiều hơn nhu cầu. Đừng chỉ nhìn số connection active; hãy đối chiếu với query latency, database CPU, lock wait và tỷ lệ timeout.

Các phiên bản r2dbc-pool và tích hợp Spring có thể cung cấp metrics khác nhau. Bật metrics theo API thực tế của phiên bản đang dùng và đưa chúng vào hệ thống quan sát như Micrometer khi dự án đã tích hợp.

### 13. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tạo một connection mới cho mỗi request mà không dùng pool | Tăng chi phí bắt tay, xác thực và áp lực database | Dùng R2DBC connection pool |
| Đặt **maxSize** bằng toàn bộ giới hạn database | Các service khác không còn ngân sách kết nối | Tính tổng trên tất cả replica và client |
| Dùng **flatMap** không giới hạn rõ trong batch lớn | Một subscription có thể tạo nhiều truy vấn cùng lúc | Đặt concurrency phù hợp |
| Nghĩ concurrency của **flatMap** là giới hạn toàn ứng dụng | Nhiều request nhân số nhánh đồng thời | Dùng pool và bulkhead/admission control |
| Chỉ tăng pool khi query chậm | Có thể làm database quá tải hơn | Kiểm tra query plan, index, lock và transaction |
| Giữ connection khi gọi HTTP bên ngoài | Pool nhanh cạn dù database ít hoạt động | Tách công việc ngoài transaction/connection scope |
| Dùng một connection cho nhiều request | Tranh chấp trạng thái và transaction | Để pool cấp connection theo phạm vi sử dụng |
| Không đặt acquire timeout | Request có thể chờ pool quá lâu | Đặt timeout và theo dõi hàng đợi |
| Chạy nhiều statement đồng thời trong cùng transaction mà không kiểm tra driver | Lỗi giao thức hoặc thứ tự khó dự đoán | Tuần tự hóa thao tác trên connection nếu cần |

### 14. Quy trình chọn pool size và query concurrency

Khi cấu hình một dịch vụ reactive truy cập database, hãy đi theo các bước:

1. Xác định giới hạn connection của database và phần ngân sách dành cho các ứng dụng khác.
2. Nhân số replica với **maxSize** dự kiến để tính tổng kết nối có thể mở.
3. Đo thời gian giữ connection, thời gian truy vấn và thời gian transaction.
4. Chọn concurrency cho từng pipeline batch dựa trên tải database và kích thước batch.
5. Đặt acquire timeout, query timeout và giới hạn hàng đợi chờ phù hợp.
6. Giữ transaction ngắn và không thực hiện I/O ngoài database khi đang giữ connection nếu không cần thiết.
7. Theo dõi active, idle, pending acquire, acquire latency, query latency và timeout dưới tải đại diện.
8. Điều chỉnh từng giới hạn dựa trên số liệu, sau đó kiểm tra lại khi thay đổi số replica hoặc workload.

Trong module REACTIVE_PROGRAMMING, quản lý pool và truy vấn đồng thời là cách nối backpressure của pipeline với giới hạn tài nguyên thật của database. Pool giới hạn số connection được mượn; concurrency giới hạn số Publisher con trong một subscription; admission control bảo vệ toàn ứng dụng khi có nhiều request. Kết hợp các giới hạn cùng timeout, transaction ngắn và metrics giúp hệ thống giữ thông lượng ổn định mà không đẩy áp lực quá mức xuống database.
