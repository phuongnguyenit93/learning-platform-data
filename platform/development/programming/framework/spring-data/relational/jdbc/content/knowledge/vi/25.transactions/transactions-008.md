# Isolation, readOnly, timeout và giới hạn phụ thuộc driver

Trong Spring Data JDBC, các thuộc tính giao dịch thường được cấu hình bằng annotation @Transactional. Ngoài propagation, annotation cho phép chọn isolation level, đánh dấu transaction chỉ đọc và đặt timeout. Những thuộc tính này được áp dụng bởi transaction manager, JDBC connection, driver và database. Cùng một khai báo có thể có hiệu quả khác nhau tùy database hoặc khi method tham gia transaction đã tồn tại.

## 1. Vai trò của transaction manager và JDBC connection

Spring dùng PlatformTransactionManager để điều phối transaction. Trong ứng dụng Spring Data JDBC, transaction manager thường được cấu hình dựa trên DataSource, chẳng hạn JdbcTransactionManager hoặc DataSourceTransactionManager.

Khi transaction bắt đầu, transaction manager lấy JDBC Connection, cấu hình isolation/read-only, rồi bắt đầu transaction. Repository Spring Data JDBC và JdbcTemplate có thể cùng tham gia transaction nếu dùng cùng DataSource và transaction manager.

~~~mermaid
flowchart TD
    A[Service method có @Transactional] --> B[Spring transaction interceptor]
    B --> C[PlatformTransactionManager]
    C --> D[JDBC Connection từ DataSource]
    D --> E[Thiết lập isolation / readOnly / timeout]
    E --> F[Thực thi SQL qua Repository hoặc JdbcTemplate]
    F --> G[(Database)]
    G --> H[Commit hoặc rollback]
~~~

Annotation mô tả yêu cầu của ứng dụng. Transaction manager chuyển yêu cầu thành cấu hình connection/transaction; JDBC driver chuyển lời gọi JDBC thành hành vi mà database hỗ trợ. Không thể chỉ nhìn annotation để kết luận database chắc chắn thực hiện đúng một isolation level hay timeout.

## 2. Khai báo @Transactional

~~~java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(
    isolation = Isolation.READ_COMMITTED,
    timeout = 5
)
public void updateCustomer(Long id, String name) {
    // Đọc và cập nhật aggregate trong transaction có timeout 5 giây.
}
~~~

Các thuộc tính thường dùng:

| Thuộc tính | Mục đích |
|---|---|
| propagation | Tham gia transaction hiện có hay tạo transaction mới |
| isolation | Mức cô lập cho transaction mới |
| readOnly | Gợi ý transaction chỉ đọc |
| timeout | Giới hạn thời gian transaction theo khả năng transaction manager |
| rollbackFor / noRollbackFor | Tùy chỉnh loại exception gây rollback |

Các thuộc tính isolation, readOnly và timeout cần được hiểu trong mối quan hệ với propagation. Khi một method tham gia transaction đã tồn tại, transaction vật lý bên ngoài thường quyết định các thiết lập này.

## 3. Isolation level là gì?

Isolation mô tả mức độ một transaction nhìn thấy thay đổi do transaction khác thực hiện đồng thời. Mức cô lập ảnh hưởng đến các anomaly có thể xảy ra khi nhiều transaction đọc/ghi cùng dữ liệu.

Ba anomaly thường dùng để giải thích:

- **Dirty read**: transaction đọc dữ liệu chưa commit của transaction khác. Transaction ghi có thể rollback sau đó, khiến dữ liệu vừa đọc chưa từng trở thành dữ liệu đã commit.
- **Non-repeatable read**: cùng một hàng được đọc hai lần trong một transaction nhưng giá trị khác nhau vì transaction khác đã commit update giữa hai lần đọc.
- **Phantom read**: cùng một điều kiện truy vấn được thực hiện hai lần nhưng tập hàng phù hợp thay đổi vì transaction khác insert/delete hoặc thay đổi dữ liệu để hàng bắt đầu/ngừng thỏa điều kiện.

Bảng tổng quát theo định nghĩa isolation trong SQL:

| Isolation level | Dirty read | Non-repeatable read | Phantom read |
|---|---|---|---|
| READ_UNCOMMITTED | Có thể | Có thể | Có thể |
| READ_COMMITTED | Không | Có thể | Có thể |
| REPEATABLE_READ | Không | Không | Có thể theo mô hình SQL chuẩn |
| SERIALIZABLE | Không | Không | Không theo mô hình SQL chuẩn |

Đây là mô tả khái niệm theo chuẩn, không phải dự đoán tuyệt đối cho mọi engine. Database có thể dùng MVCC, snapshot isolation, khóa predicate hoặc cơ chế riêng. Một số engine thực thi mạnh hơn mức được yêu cầu, một số ánh xạ mức isolation sang hành vi khác. Hãy kiểm tra tài liệu database và chạy thử với hai connection/transaction khi cần xác nhận.

## 4. Isolation enum trong Spring

Spring cung cấp các giá trị trong enum Isolation:

~~~java
import org.springframework.transaction.annotation.Isolation;

Isolation.DEFAULT;
Isolation.READ_UNCOMMITTED;
Isolation.READ_COMMITTED;
Isolation.REPEATABLE_READ;
Isolation.SERIALIZABLE;
~~~

Ý nghĩa:

- **DEFAULT**: dùng isolation mặc định của transaction manager/database. Đây là giá trị mặc định của @Transactional.
- **READ_UNCOMMITTED**: mức đọc lỏng nhất theo mô hình SQL chuẩn; có thể đọc dữ liệu chưa commit nếu database hỗ trợ.
- **READ_COMMITTED**: chỉ đọc dữ liệu đã commit; một lần đọc sau có thể thấy commit mới từ transaction khác.
- **REPEATABLE_READ**: bảo đảm dữ liệu của hàng đã đọc không thay đổi trong lần đọc lại theo định nghĩa chuẩn; phantom vẫn có thể phụ thuộc engine.
- **SERIALIZABLE**: yêu cầu kết quả tương đương thực thi tuần tự các transaction; có thể tăng khóa, retry hoặc serialization failure.

Ví dụ:

~~~java
@Transactional(isolation = Isolation.REPEATABLE_READ)
public OrderSummary calculateSummary(Long customerId) {
    // Các lần đọc trong transaction cần mức cô lập cao hơn.
}
~~~

Không nên chọn SERIALIZABLE mặc định cho mọi method. Mức cô lập cao hơn có thể làm tăng contention, blocking, deadlock hoặc serialization failure. Chọn mức thấp nhất vẫn đáp ứng invariant của use case và database.

## 5. DEFAULT sử dụng isolation của database

Nếu không chỉ định isolation:

~~~java
@Transactional
public void processOrder(Long orderId) {
    // ...
}
~~~

Spring dùng Isolation.DEFAULT. Transaction manager không yêu cầu một mức isolation khác; connection/database áp dụng mặc định của nó.

Mặc định khác nhau giữa hệ quản trị và có thể thay đổi theo cấu hình database. Không nên giả định ứng dụng nào cũng chạy READ_COMMITTED hoặc REPEATABLE_READ.

Có thể kiểm tra metadata JDBC:

~~~java
try (Connection connection = dataSource.getConnection()) {
    int level = connection.getTransactionIsolation();
}
~~~

Trong code ứng dụng thực tế, ví dụ trên chỉ nhằm minh họa API; phải đóng connection đúng cách và tránh lấy connection độc lập để suy luận isolation của transaction đang chạy. JDBC DatabaseMetaData còn có phương thức supportsTransactionIsolationLevel để xem driver khai báo hỗ trợ mức nào.

## 6. Driver và database có thể giới hạn isolation

JDBC định nghĩa các mức isolation, nhưng khả năng thực tế phụ thuộc driver và database:

- Driver có thể không hỗ trợ một mức cụ thể.
- Database có thể ánh xạ một mức yêu cầu sang hành vi mạnh hơn hoặc đặc thù.
- Một số engine không cho phép thay đổi isolation khi transaction đã bắt đầu.
- Một số database dùng MVCC/snapshot thay vì chỉ dựa vào khóa.
- Isolation có thể được cấu hình ở cấp database, connection hoặc transaction.
- Một số lỗi concurrency chỉ xuất hiện dưới tải đồng thời và khó phát hiện bằng test tuần tự.

Có thể kiểm tra hỗ trợ qua DatabaseMetaData:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    boolean supportsRepeatableRead =
            metadata.supportsTransactionIsolationLevel(
                    Connection.TRANSACTION_REPEATABLE_READ);

    int currentIsolation = connection.getTransactionIsolation();
}
~~~

Kết quả metadata là thông tin do driver cung cấp; vẫn nên xác nhận bằng tài liệu DBMS và integration test. Nếu driver không hỗ trợ mức isolation được yêu cầu, transaction manager có thể báo lỗi khi cấu hình connection hoặc database có thể áp dụng hành vi riêng.

## 7. Vì sao isolation của method tham gia transaction có thể bị bỏ qua?

Giả sử service A mở transaction READ_COMMITTED và gọi service B:

~~~java
@Service
public class CheckoutService {
    private final InventoryService inventory;

    public CheckoutService(InventoryService inventory) {
        this.inventory = inventory;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void checkout() {
        inventory.reserveStock();
    }
}

@Service
public class InventoryService {
    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void reserveStock() {
        // ...
    }
}
~~~

Mặc định propagation của @Transactional là REQUIRED. Khi reserveStock được gọi trong lúc checkout đang có transaction, nó tham gia transaction hiện có. Không có transaction vật lý mới chỉ vì method bên trong yêu cầu SERIALIZABLE. Isolation của transaction bên ngoài vẫn có hiệu lực.

Tương tự, timeout hoặc readOnly được khai báo trên method tham gia transaction hiện có thường không thay đổi timeout/read-only của transaction đã bắt đầu.

Nếu muốn cấu hình method bên trong thành transaction vật lý riêng, REQUIRES_NEW có thể tạo transaction mới; tuy nhiên, nó có hệ quả về connection, commit/rollback và tính nhất quán. Chỉ dùng khi thật sự cần độc lập.

Có thể bật chế độ kiểm tra transaction hiện có nghiêm ngặt bằng validateExistingTransaction trên transaction manager để phát hiện isolation/read-only không tương thích thay vì âm thầm tham gia transaction với cấu hình bên ngoài. API cấu hình cụ thể phụ thuộc transaction manager.

## 14. Chọn isolation theo invariant nghiệp vụ

Không nên chọn isolation chỉ vì tên mức cao hơn nghe an toàn hơn. Hãy bắt đầu từ anomaly mà nghiệp vụ không chấp nhận.

| Nhu cầu | Điều cần bảo vệ | Hướng cân nhắc |
|---|---|---|
| Đọc dữ liệu đã commit là đủ | Không đọc dirty data | READ_COMMITTED thường là điểm bắt đầu phổ biến |
| Đọc cùng hàng nhiều lần phải ổn định | Tránh non-repeatable read | REPEATABLE_READ hoặc cơ chế snapshot phù hợp |
| Kiểm tra điều kiện trên tập hàng và cần tránh phantom | Tập kết quả phải nhất quán theo yêu cầu | SERIALIZABLE hoặc khóa/constraint/query strategy chuyên biệt |
| Chỉ đọc báo cáo và không ghi | Ý định đọc, tối ưu có thể có | readOnly=true |
| Tác vụ phải hoàn tất trong thời hạn | Giới hạn thời gian transaction/statement | timeout cùng statement/query timeout và network timeout phù hợp |

Ví dụ kiểm tra số lượng chỗ còn trống: nếu hai transaction cùng đọc available = 1, cả hai cùng quyết định đặt chỗ rồi ghi, chỉ tăng isolation có thể chưa phải giải pháp duy nhất hoặc tối ưu nhất. Có thể dùng conditional update nguyên tử:

~~~sql
UPDATE event_slots
SET available = available - 1
WHERE id = :id
  AND available > 0;
~~~

Sau đó kiểm tra update count. Database constraint, khóa hoặc optimistic locking có thể bảo vệ invariant rõ ràng hơn tùy mô hình. Isolation là một phần của thiết kế concurrency, không thay thế mọi ràng buộc dữ liệu.

## 15. Locking, deadlock và serialization failure

Isolation cao hơn có thể làm database phải giữ khóa lâu hơn hoặc kiểm tra xung đột chặt hơn. Một số kết quả có thể xảy ra:

- Transaction chờ lock và vượt timeout.
- Deadlock khiến database chọn một transaction làm nạn nhân.
- Serializable transaction bị từ chối commit do không thể sắp xếp tương đương tuần tự.
- Ứng dụng nhận exception truy cập dữ liệu và cần rollback/retry.

Retry phải có chủ đích. Chỉ retry những lỗi được xác định là transient, giới hạn số lần, có backoff và bảo đảm use case có thể chạy lại an toàn. Không retry mọi exception; thao tác gửi email, charge payment hoặc gọi dịch vụ ngoài không tự rollback cùng database transaction.

## 16. Giới hạn theo transaction manager

Spring transaction abstraction cho phép cấu hình isolation, readOnly và timeout, nhưng hiệu lực phụ thuộc transaction manager:

- **JdbcTransactionManager/DataSourceTransactionManager** quản lý transaction JDBC cho một DataSource.
- **JtaTransactionManager** điều phối transaction JTA và có semantics/capability khác.
- **Transaction manager tùy chỉnh** có thể hỗ trợ một số thuộc tính nhưng bỏ qua hoặc xử lý khác các thuộc tính khác.

Với Spring Data JDBC, cần bảo đảm transaction manager quản lý đúng DataSource mà repository sử dụng. Nếu có nhiều transaction manager, có thể chỉ rõ bean bằng thuộc tính transactionManager của @Transactional khi cần.

Không nên đặt isolation/timeout trên một transaction manager rồi thực thi JDBC bằng một DataSource không được manager đó quản lý. Khi đó câu lệnh có thể không nằm trong transaction mà ứng dụng nghĩ đang có.

## 17. Giới hạn do driver/database và cách kiểm tra

Một quy trình kiểm tra thực tế:

1. Xác định database engine và phiên bản.
2. Xác định JDBC driver và phiên bản.
3. Xác định transaction manager đang được cấu hình.
4. Kiểm tra isolation mặc định và các mức driver báo hỗ trợ.
5. Chạy integration test với hai connection độc lập để quan sát anomaly cần kiểm soát.
6. Bật SQL/transaction logging ở môi trường phát triển để xác nhận transaction boundary.
7. Thử timeout bằng một query có thời gian chạy kiểm soát trong database test.
8. Kiểm tra trạng thái dữ liệu sau commit/rollback.

Có thể đọc metadata:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println(metadata.getDatabaseProductName());
    System.out.println(metadata.getDatabaseProductVersion());
    System.out.println(metadata.getDriverName());
    System.out.println(metadata.getDriverVersion());

    System.out.println(
            metadata.supportsTransactionIsolationLevel(
                    Connection.TRANSACTION_SERIALIZABLE)
    );
}
~~~

Metadata là tín hiệu ban đầu. Để xác nhận hành vi, cần integration test trên đúng database/driver production hoặc Testcontainers dùng cùng engine và phiên bản gần tương đương. H2 có thể hữu ích cho test nhanh nhưng không chứng minh mọi semantics của PostgreSQL, MySQL, SQL Server, Oracle hay database khác.

## 18. Lỗi thường gặp khi cấu hình @Transactional

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Isolation khai báo SERIALIZABLE nhưng hành vi không như mong đợi | Method tham gia transaction ngoài theo REQUIRED | Kiểm tra transaction nào thực sự bắt đầu physical transaction |
| Timeout ở method trong không có tác dụng | Method tham gia transaction ngoài đã có timeout khác | Đặt timeout ở ranh giới bắt đầu transaction hoặc dùng propagation phù hợp |
| DML vẫn chạy trong readOnly transaction | Driver/database coi readOnly là hint | Dùng DB permissions nếu cần chặn ghi |
| DML bị từ chối khi readOnly=true | Database thực thi chế độ read-only | Bỏ readOnly cho use case ghi |
| Timeout không dừng HTTP call | Transaction timeout không phải HTTP client timeout | Cấu hình timeout riêng cho HTTP client |
| Query không bị dừng đúng lúc | Driver/statement không áp dụng query timeout mong đợi | Dùng JdbcTemplate, statement timeout hoặc DB timeout phù hợp |
| Isolation không được hỗ trợ | Driver/database giới hạn mức isolation | Kiểm tra DatabaseMetaData và tài liệu DBMS |
| Transaction không bao trùm repository và JdbcTemplate | Khác DataSource/transaction manager hoặc tự mở connection | Dùng chung DataSource và Spring transaction-aware access |
| @Transactional không chạy khi gọi method nội bộ | Self-invocation không đi qua proxy | Gọi qua Spring bean/proxy hoặc tổ chức lại service |
| SERIALIZABLE gây deadlock/serialization failure | Contention hoặc transaction kéo dài | Giảm phạm vi transaction, thêm retry có kiểm soát, đánh giá isolation |
| Đọc lặp vẫn thấy dữ liệu khác | Database semantics khác giả định hoặc transaction thực tế đã kết thúc | Kiểm tra engine, isolation và transaction boundary |

## 19. Lưu ý về proxy và vị trí đặt @Transactional

Trong cấu hình proxy mặc định của Spring, @Transactional được áp dụng khi lời gọi đi qua proxy của Spring bean. Gọi một method transactional khác bằng this.method() trong cùng object thường không đi qua proxy, vì vậy annotation trên method được gọi có thể không được áp dụng như kỳ vọng.

Ví dụ không nên dựa vào self-invocation:

~~~java
@Service
public class ReportService {
    public void generate() {
        loadSnapshot(); // Gọi nội bộ, không qua proxy.
    }

    @Transactional(
        isolation = Isolation.REPEATABLE_READ,
        readOnly = true
    )
    public void loadSnapshot() {
        // ...
    }
}
~~~

Có thể chuyển method transactional sang một service bean riêng rồi inject vào ReportService. Khi đó lời gọi qua bean proxy kích hoạt transaction interceptor đúng cách.

Ngoài ra, quy tắc rollback mặc định của Spring thường rollback với RuntimeException và Error, không mặc định rollback với mọi checked exception. Nếu use case cần rollback cho checked exception, cấu hình rollbackFor phù hợp. Timeout/isolation không thay đổi quy tắc rollback này.

## 20. Ví dụ service đọc báo cáo có isolation và timeout

~~~java
import java.time.LocalDate;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderReportService {
    private final OrderRepository orders;

    public OrderReportService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(
        isolation = Isolation.REPEATABLE_READ,
        readOnly = true,
        timeout = 10
    )
    public List<OrderSummary> loadReport(LocalDate from, LocalDate to) {
        return orders.findSummariesCreatedBetween(
                from.atStartOfDay(),
                to.plusDays(1).atStartOfDay(),
                Sort.by(Sort.Order.asc("createdAt"))
        );
    }
}
~~~

Ví dụ biểu đạt ý định: báo cáo chỉ đọc, muốn các lần đọc trong transaction có mức ổn định phù hợp và giới hạn thời gian. Cần xác nhận database/driver hỗ trợ REPEATABLE_READ theo semantics mong muốn và repository query thực sự chạy trong transaction này. Nếu method được gọi trong transaction ngoài, cấu hình bên ngoài có thể quyết định isolation và timeout thực tế.

## 21. Bài thực hành: quan sát isolation, readOnly và timeout

Dùng database thử nghiệm và hai connection độc lập. Tạo bảng:

~~~sql
CREATE TABLE account_balance (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
);

INSERT INTO account_balance(id, balance) VALUES (1, 100.00);
~~~

Thực hành theo từng mức isolation:

1. Transaction A đọc balance.
2. Transaction B cập nhật balance thành 150 và commit.
3. Transaction A đọc lại cùng hàng.
4. Quan sát sự khác biệt giữa READ_COMMITTED và REPEATABLE_READ theo database đang dùng.
5. Thử một transaction B cập nhật nhưng chưa commit; kiểm tra transaction A có thể đọc dữ liệu chưa commit hay không ở mức driver/database hỗ trợ.
6. Với readOnly=true, thử một câu UPDATE trong database test để xem hệ thống chỉ coi đây là hint hay từ chối DML.
7. Với timeout ngắn, chạy query có thời gian chờ kiểm soát và quan sát exception/rollback.
8. Gọi một method REQUIRED bên trong transaction có isolation khác để xác nhận cấu hình nào được giữ.
9. Kiểm tra metadata JDBC và ghi lại database/driver version cùng kết quả.

Không dùng H2 làm bằng chứng duy nhất nếu production chạy DBMS khác. Hành vi isolation và timeout phải được xác nhận trên engine mục tiêu.

## 22. Nguyên tắc ghi nhớ

- @Transactional mô tả yêu cầu; transaction manager, JDBC driver và database quyết định cách áp dụng thực tế.
- Isolation.DEFAULT dùng mặc định của database/transaction manager.
- READ_UNCOMMITTED, READ_COMMITTED, REPEATABLE_READ và SERIALIZABLE có mức bảo vệ anomaly tăng dần theo mô hình SQL chuẩn; DBMS có thể triển khai khác.
- Isolation chỉ được thiết lập khi bắt đầu transaction vật lý; method REQUIRED tham gia transaction hiện có thường dùng isolation của transaction ngoài.
- readOnly là hint/thuộc tính transaction, không phải cơ chế authorization hoặc bảo đảm mọi DML bị chặn.
- timeout thường tính bằng giây và phụ thuộc transaction manager/driver; không phải deadline cứng cho mọi đoạn code hoặc HTTP call.
- Khi tham gia transaction hiện có, isolation, readOnly và timeout khai báo ở method bên trong thường không thay đổi transaction bên ngoài.
- JdbcTemplate có thể tích hợp transaction timeout qua Spring JDBC; JDBC code tự quản lý Statement cần kiểm tra query timeout tường minh.
- Isolation cao có thể tăng blocking, deadlock và serialization failure; retry cần có giới hạn và an toàn.
- Dùng cùng DataSource/transaction manager để repository và JDBC template tham gia cùng transaction.
- Xác minh behavior trên đúng database và JDBC driver bằng integration test, không chỉ dựa vào annotation hoặc H2.

Trong Spring Data JDBC, isolation, readOnly và timeout là các yêu cầu ở ranh giới transaction. Hãy chọn chúng theo invariant và nhu cầu của use case, đặt tại method thực sự bắt đầu transaction, rồi xác minh trên transaction manager, driver và database đang chạy. Cách đó giúp tránh kỳ vọng sai rằng một annotation có thể ép mọi database thực hiện cùng một semantics hoặc dừng mọi loại công việc sau một số giây cố định.


## 8. readOnly: gợi ý cho transaction chỉ đọc

Khai báo:

~~~java
@Transactional(readOnly = true)
public List<CustomerSummary> searchCustomers(String city) {
    return customerRepository.findSummariesByCity(city);
}
~~~

readOnly biểu thị use case dự định đọc dữ liệu. Transaction manager có thể chuyển gợi ý này xuống JDBC Connection thông qua setReadOnly(true), hoặc áp dụng tối ưu riêng nếu công nghệ persistence hỗ trợ.

Trong Spring Data JDBC, nó hữu ích để thể hiện ý định và cho phép driver/database tối ưu đường đọc khi có hỗ trợ.

### readOnly không phải cơ chế phân quyền

Không nên hiểu readOnly=true là hàng rào bảo mật bảo đảm không thể ghi:

- Một số driver coi read-only là hint và không chặn DML.
- Một số database có thể thực thi chế độ transaction read-only và từ chối lệnh ghi.
- Transaction manager có thể bỏ qua hint nếu không hỗ trợ.
- SQL thủ công vẫn chịu quy tắc mà database và connection áp dụng.

Nếu cần bảo đảm người dùng chỉ có quyền đọc, hãy dùng database user/permission phù hợp và authorization ở ứng dụng. Không dựa vào thuộc tính readOnly của annotation làm cơ chế bảo mật.

### Không nên đánh dấu readOnly cho use case có ghi

Ví dụ sau có ý nghĩa mâu thuẫn:

~~~java
@Transactional(readOnly = true)
public void renameCustomer(Long id, String name) {
    Customer current = customers.findById(id).orElseThrow();
    customers.save(current.rename(name));
}
~~~

Kết quả phụ thuộc transaction manager và database. Một số hệ thống có thể từ chối ghi; nơi khác có thể vẫn thực thi. Hãy khai báo readOnly=true cho transaction chỉ đọc, và dùng transaction ghi mặc định cho use case cập nhật.

## 9. readOnly có thể tác động tới connection như thế nào?

Với JDBC transaction manager, Spring có thể gọi Connection.setReadOnly(true) trước khi bắt đầu transaction. Driver có thể chuyển gợi ý tới database để tối ưu thực thi hoặc áp dụng giới hạn.

Không phải mọi driver đều có cùng hành vi:

- Có driver chấp nhận nhưng không tối ưu đáng kể.
- Có driver dùng read-only như tín hiệu cho đường truy cập phù hợp trong một số cấu hình.
- Có database từ chối câu lệnh ghi trong transaction read-only.
- Có hệ thống chỉ coi đây là thông tin gợi ý.

Không nên suy ra rằng readOnly tự động định tuyến query sang read replica. Việc routing datasource là cấu hình riêng; cần bảo đảm transaction manager, connection routing và consistency requirements được thiết kế đồng bộ.

## 10. timeout: giới hạn thời gian transaction

Khai báo timeout theo giây:

~~~java
@Transactional(timeout = 5)
public void processPayment(Long paymentId) {
    // Thao tác JDBC trong transaction.
}
~~~

timeout=5 yêu cầu transaction có thời hạn 5 giây theo khả năng của transaction manager. Giá trị thường tính bằng giây, không phải millisecond.

Nếu không khai báo timeout, transaction dùng timeout mặc định của transaction manager (thường không đặt timeout cụ thể nếu manager không được cấu hình khác).

Timeout không nên được hiểu là bộ ngắt cứng cho mọi đoạn code Java:

- Nó không nhất thiết dừng một phép tính CPU dài không tương tác với transaction.
- Nó không tự đặt timeout cho mọi HTTP call hoặc RPC bên ngoài.
- Nó không bảo đảm một database statement bị dừng ngay tức thì nếu driver không hỗ trợ/không áp dụng query timeout.
- Nó không thay thế timeout riêng của connection pool, socket hoặc HTTP client.

## 11. Timeout được áp dụng cho JDBC statement ra sao?

Spring JDBC có thể áp dụng transaction timeout lên Statement thông qua cơ chế hỗ trợ của DataSourceUtils và JdbcTemplate. Vì vậy, các câu lệnh chạy qua JdbcTemplate trong transaction có thể nhận query timeout phù hợp.

~~~java
@Transactional(timeout = 3)
public int updateStatus(Long id) {
    return jdbcTemplate.update(
            "UPDATE orders SET status = ? WHERE id = ?",
            "PROCESSING",
            id
    );
}
~~~

Với JDBC code tự quản lý Statement/Connection, không nên giả định timeout của Spring được áp dụng tự động nếu code bỏ qua các helper/transaction-aware API của Spring. Cần kiểm tra timeout trên Statement hoặc dùng JdbcTemplate để tận dụng cơ chế tích hợp.

Ngoài ra, timeout của transaction và timeout truy vấn ở database là hai khái niệm liên quan nhưng không hoàn toàn giống nhau. Database có thể có statement timeout riêng; connection pool có connection acquisition timeout; socket/driver có network timeout. Cần cấu hình theo từng lớp.

## 12. timeout và transaction đã tồn tại

Giả sử method ngoài mở transaction với timeout 30 giây, sau đó gọi method trong có timeout 2 giây và propagation REQUIRED. Method trong tham gia transaction đã tồn tại; timeout 2 giây thường không thay đổi deadline của transaction vật lý bên ngoài.

~~~java
@Service
public class ImportService {
    private final CustomerImportWriter writer;

    public ImportService(CustomerImportWriter writer) {
        this.writer = writer;
    }

    @Transactional(timeout = 30)
    public void importBatch() {
        writer.writeRows();
    }
}

@Service
public class CustomerImportWriter {
    @Transactional(timeout = 2)
    public void writeRows() {
        // Tham gia transaction đang tồn tại theo REQUIRED.
    }
}
~~~

Nếu method trong cần transaction độc lập với timeout riêng, có thể cân nhắc REQUIRES_NEW. Khi đó transaction ngoài bị suspend, transaction mới có timeout riêng; nhưng nó cũng có thể commit độc lập và cần thêm connection. Không chọn REQUIRES_NEW chỉ để ép một timeout ngắn nếu nghiệp vụ yêu cầu toàn bộ batch phải rollback cùng nhau.

## 13. Kết hợp isolation, readOnly và timeout

Có thể cấu hình nhiều thuộc tính trên cùng một method:

~~~java
@Transactional(
    isolation = Isolation.REPEATABLE_READ,
    readOnly = true,
    timeout = 10
)
public Report loadConsistentReport(LocalDate from, LocalDate to) {
    // Đọc dữ liệu trong một transaction read-only.
}
~~~

Ý nghĩa:

- Yêu cầu isolation REPEATABLE_READ cho transaction mới.
- Đánh dấu transaction chỉ đọc.
- Yêu cầu timeout 10 giây.
- Các thao tác đọc qua repository/JDBC cùng tham gia transaction nếu dùng cùng DataSource và transaction manager.

Nhưng nếu method được gọi trong một transaction đã tồn tại với REQUIRED, các thuộc tính isolation, readOnly và timeout khai báo tại method này thường không thay thế cấu hình của transaction ngoài. Luôn xác định method nào thực sự bắt đầu transaction vật lý.



