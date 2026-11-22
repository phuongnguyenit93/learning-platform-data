# Phân biệt saveAll với JDBC batch và đánh giá chi phí ghi trong Spring Data JDBC

## 1. Hai cách ghi nhiều bản ghi, hai mục tiêu khác nhau

Khi cần lưu nhiều dữ liệu, Spring Data JDBC cung cấp §saveAll(...)§ trên repository. Spring JDBC cung cấp các API batch như §JdbcTemplate.batchUpdate(...)§. Cả hai đều có thể ghi nhiều hàng, nhưng chúng giải quyết hai bài toán khác nhau.

- **§saveAll(entities)§** lưu nhiều entity/aggregate root theo mô hình mapping và lifecycle của Spring Data JDBC.
- **JDBC batch** gom nhiều lần thực thi cùng một câu SQL có tham số vào một batch JDBC, giúp driver/database có cơ hội giảm chi phí gửi và thực thi nhiều statement.

Một lời gọi §saveAll§ **không phải cam kết JDBC batch**. Repository có thể phải thực hiện nhiều câu lệnh cho mỗi aggregate, ví dụ ghi root, ghi collection con, cập nhật version hoặc xử lý dữ liệu quan hệ. Ngược lại, JDBC batch chỉ thực thi SQL mà ứng dụng cung cấp; nó không tự hiểu aggregate, không tự áp dụng mapping entity và không tự chạy toàn bộ lifecycle của repository.

Cần chọn công cụ theo yêu cầu:

- Cần lưu aggregate theo domain model, mapping, generated ID, version và lifecycle: ưu tiên repository §save§ / §saveAll§.
- Cần ghi hàng loạt dữ liệu dạng bảng với SQL đơn giản, cấu trúc đồng nhất và muốn kiểm soát batch: cân nhắc §JdbcTemplate.batchUpdate§.
- Cần throughput rất lớn: có thể cần cơ chế bulk load/import riêng của database, sau khi đánh giá constraint, transaction và khả năng phục hồi.

## 2. saveAll làm gì?

Với §CrudRepository§, chữ ký phổ biến là:

~~~java
<S extends T> Iterable<S> saveAll(Iterable<S> entities);
~~~

Phương thức nhận một tập entity và trả về tập entity đã lưu. Nếu repository kế thừa §ListCrudRepository§, kiểu trả về tương ứng có thể là §List<S>§.

Ví dụ:

~~~java
List<Book> input = List.of(
        new Book(null, "Book A", new BigDecimal("100000")),
        new Book(null, "Book B", new BigDecimal("120000")),
        new Book(null, "Book C", new BigDecimal("150000"))
);

Iterable<Book> saved = bookRepository.saveAll(input);

for (Book book : saved) {
    log.info("Saved id={}", book.id());
}
~~~

Kết quả trả về quan trọng vì entity có thể nhận ID do database sinh, version mới hoặc một instance mới nếu được thiết kế bất biến. Luôn dùng các entity trong kết quả trả về khi cần tiếp tục xử lý.

### 2.1. saveAll không hứa một statement hay một batch

Tên phương thức chỉ diễn đạt thao tác repository trên nhiều entity. Nó không hứa rằng:

- Tất cả hàng được ghi bằng một câu §INSERT ... VALUES (...), (...), ...§.
- Driver chỉ nhận một lần gọi §executeBatch()§.
- Toàn bộ aggregate được ghi bằng một round trip.
- Mỗi entity chỉ cần một statement.
- Mọi kiểu entity đều có cùng số câu SQL.

Một aggregate có thể gồm root và nhiều thành phần con. Việc lưu aggregate có thể cần nhiều thao tác SQL để giữ đúng quan hệ và vòng đời. Vì vậy, số statement có thể lớn hơn số aggregate đầu vào.

Cách triển khai nội bộ của repository có thể thay đổi theo phiên bản Spring Data. Nếu hiệu năng phụ thuộc vào một chi tiết cụ thể, hãy kiểm tra implementation/version đang dùng và đo SQL thực tế. **Đừng suy ra JDBC batching chỉ từ việc code gọi một lần §saveAll§.**

### 2.2. saveAll vẫn có giá trị ở tầng domain

Khi dùng repository, Spring Data JDBC đảm nhiệm các công việc theo mapping:

- Xác định entity mới hay đã tồn tại theo ID/version hoặc cơ chế new-state detection.
- Thực hiện INSERT hoặc UPDATE phù hợp.
- Nhận generated key theo hỗ trợ của database/dialect/driver.
- Áp dụng optimistic locking nếu entity dùng §@Version§.
- Chuyển đổi kiểu Java/SQL theo mapping và custom conversions.
- Lưu aggregate root cùng các thành phần con theo quan hệ đã khai báo.
- Thực hiện các lifecycle callback tương ứng.

Đây là lý do §saveAll§ phù hợp khi dữ liệu là aggregate của ứng dụng. Dùng JDBC batch thuần sẽ chuyển trách nhiệm mapping và các quy tắc này về cho code ứng dụng.

## 3. JDBC batch hoạt động thế nào?

JDBC batch là cơ chế gom nhiều lần bind tham số cho cùng một câu SQL, rồi gửi batch xuống JDBC driver để thực thi. Luồng khái quát:

~~~mermaid
flowchart TD
    A["Danh sách dữ liệu đầu vào"] --> B["Chuẩn bị một SQL statement"]
    B --> C["Bind tham số cho phần tử 1"]
    C --> D["addBatch()"]
    D --> E["Bind tham số cho phần tử 2"]
    E --> F["addBatch()"]
    F --> G["... đến kích thước batch"]
    G --> H["executeBatch()"]
    H --> I["JDBC driver"]
    I --> J["Database thực thi batch"]
    J --> K["Update counts / lỗi"]
~~~

Ví dụ JDBC thuần:

~~~java
String sql = """
        INSERT INTO audit_events (event_type, message)
        VALUES (?, ?)
        """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    for (AuditEvent event : events) {
        statement.setString(1, event.type());
        statement.setString(2, event.message());
        statement.addBatch();
    }

    int[] counts = statement.executeBatch();
}
~~~

Ứng dụng bind nhiều bộ tham số cho một §PreparedStatement§. §addBatch()§ thêm bộ tham số vào batch; §executeBatch()§ yêu cầu driver thực thi các phần tử đã tích lũy.

Trong code Spring, có thể dùng §JdbcTemplate.batchUpdate(...)§ để giảm phần quản lý connection/statement:

~~~java
int[] counts = jdbcTemplate.batchUpdate(
        "INSERT INTO audit_events (event_type, message) VALUES (?, ?)",
        events,
        500,
        (ps, event) -> {
            ps.setString(1, event.type());
            ps.setString(2, event.message());
        }
);
~~~

Tham số §500§ là kích thước batch mà API dùng để chia dữ liệu thành các nhóm thực thi. Kích thước phù hợp phụ thuộc driver, database, kích thước payload, thời gian transaction và giới hạn tham số.

### 3.1. Batch không đồng nghĩa với một câu SQL đa hàng

Có ba khái niệm dễ bị nhầm:

| Cơ chế | Ý nghĩa |
|---|---|
| JDBC batch | Nhiều bộ tham số cho statement, thực thi qua batch API |
| Multi-row INSERT | Một câu SQL chứa nhiều nhóm giá trị §VALUES§ |
| Bulk load/import | Cơ chế riêng của database để nạp lượng lớn dữ liệu |

Driver có thể tối ưu batch, gộp câu lệnh hoặc gửi theo cách riêng. Ví dụ một số driver có tùy chọn rewrite batch INSERT thành multi-row INSERT. Điều đó phụ thuộc driver, cấu hình và câu SQL. JDBC API không bảo đảm một cách truyền dữ liệu vật lý duy nhất.

### 3.2. Update counts và lỗi batch

§executeBatch()§ trả về mảng update count. Các giá trị có thể là:

- Số hàng bị tác động.
- §Statement.SUCCESS_NO_INFO§: statement thành công nhưng driver không cung cấp số hàng chính xác.
- §Statement.EXECUTE_FAILED§: phần tử batch thất bại trong một số tình huống báo lỗi.

Driver cũng có thể ném §BatchUpdateException§; exception chứa update counts đã thực hiện trước khi lỗi được báo. Không nên giả định mọi driver sẽ báo kết quả từng phần giống hệt nhau hoặc batch tự động tiếp tục sau lỗi.

Khi xử lý batch failure, cần biết database và driver đang dùng, transaction có rollback hay không, và phần tử nào cần retry. Không được retry toàn bộ batch một cách mù quáng nếu một phần dữ liệu đã commit hoặc thao tác không idempotent.

## 4. So sánh saveAll và JDBC batch

| Tiêu chí | Spring Data JDBC §saveAll§ | JDBC batch / §JdbcTemplate.batchUpdate§ |
|---|---|---|
| Đơn vị thao tác | Entity/aggregate root | Các lần thực thi SQL có tham số |
| Mapping entity | Có metadata và converter | Ứng dụng tự bind và map |
| Quan hệ aggregate | Quản lý theo mapping Spring Data JDBC | Ứng dụng tự ghi root/child |
| Generated ID | Repository xử lý theo dialect/driver | Phải tự xử lý, batch generated keys phụ thuộc driver/API |
| Optimistic locking | Có thể áp dụng với §@Version§ | Tự viết điều kiện version và kiểm tra update count |
| Lifecycle callback | Theo cơ chế Spring Data | Không tự chạy callback repository |
| SQL | Framework sinh từ mapping hoặc query | Ứng dụng viết SQL tường minh |
| Batch execution | Không được API bảo đảm | Là mục tiêu trực tiếp của batch API |
| Transaction | Repository transaction semantics; có thể mở rộng ở service | Cần transaction phù hợp nếu muốn atomic |
| Kết quả | Entity đã lưu | Update counts hoặc kết quả batch |
| Phù hợp | CRUD aggregate, domain persistence | Ghi hàng loạt SQL đơn giản, đồng nhất |

Không có lựa chọn nào luôn nhanh hơn. Với một aggregate có nhiều bảng và callback, §saveAll§ cung cấp đúng semantics domain. Với hàng triệu dòng log đơn giản, §JdbcTemplate.batchUpdate§ hoặc native bulk import có thể giảm overhead đáng kể.

## 5. Chi phí ghi gồm những gì?

Đánh giá hiệu năng không chỉ đếm số lần gọi Java method. Chi phí tổng thể có thể gồm:

1. **Network round trips:** số lần ứng dụng/driver trao đổi với database.
2. **SQL parsing/planning:** database phân tích và lập kế hoạch thực thi.
3. **Statement preparation:** tạo và chuẩn bị statement.
4. **Parameter binding/conversion:** chuyển giá trị Java sang kiểu JDBC/SQL.
5. **Index maintenance:** cập nhật index khi INSERT/UPDATE/DELETE.
6. **Constraint checks:** kiểm tra primary key, unique, foreign key, check constraint.
7. **Transaction log/WAL:** ghi log phục vụ durability và recovery.
8. **Locking/concurrency:** chờ khóa, xung đột và tranh chấp tài nguyên.
9. **Object mapping:** tạo entity, collection, converter và callback.
10. **Memory/GC:** giữ input, kết quả, statement state và object graph.
11. **Commit/flush:** đồng bộ dữ liệu và xác nhận transaction.

Sơ đồ chi phí khái niệm:

~~~mermaid
flowchart TD
    A["Application"] --> B["Object mapping / conversion"]
    B --> C["JDBC statement preparation"]
    C --> D["Network / driver"]
    D --> E["Database execution"]
    E --> F["Index + constraints"]
    E --> G["Locks + transaction log"]
    F --> H["Commit"]
    G --> H
    H --> I["Return result"]
~~~

JDBC batch thường giảm overhead lặp lại ở tầng driver/network/statement execution. Nó không làm biến mất chi phí index, constraint, WAL, lock hay commit. Nếu database phải cập nhật nhiều index hoặc ghi log lớn, batching không thể loại bỏ phần chi phí đó.

## 6. Ước lượng round trips và tác động của batch size

Giả sử cần ghi §N§ bản ghi bằng cùng một câu SQL. Nếu ứng dụng gửi từng bản ghi riêng lẻ, số lần gửi statement có thể gần với §N§. Nếu dùng batch size §B§, số nhóm batch xấp xỉ:

\[
\text{batchCount} = \left\lceil \frac{N}{B} \right\rceil
\]

Ví dụ §N = 10.000§, §B = 500§ thì có 20 nhóm batch. Đây là số nhóm gọi batch ở tầng ứng dụng, **không phải cam kết database chỉ nhận đúng 20 network round trips**. Driver có thể chia nhỏ, gộp hoặc thực hiện theo giao thức riêng.

### 6.1. Minh họa số nhóm batch

| Số bản ghi N | Batch size B | Số nhóm lý thuyết |
|---:|---:|---:|
| 1.000 | 100 | 10 |
| 1.000 | 250 | 4 |
| 10.000 | 500 | 20 |
| 10.000 | 1.000 | 10 |
| 100.000 | 1.000 | 100 |

Tăng batch size làm giảm số nhóm, nhưng không đồng nghĩa throughput luôn tăng. Batch quá lớn có thể:

- Tăng bộ nhớ phía ứng dụng và driver.
- Tăng thời gian giữ lock.
- Kéo dài transaction và thời gian rollback.
- Làm batch failure khó xác định/khôi phục hơn.
- Chạm giới hạn tham số, packet hoặc buffer của driver/database.
- Làm tăng độ trễ của một nhóm dữ liệu và ảnh hưởng các request khác.

### 6.2. Không có batch size tối ưu cho mọi hệ thống

Một quy trình thực tế là thử một số kích thước nhỏ, vừa và lớn (ví dụ 100, 500, 1.000), đo trên database và dữ liệu thật, rồi chọn mức cân bằng giữa throughput, latency, bộ nhớ và khả năng phục hồi.

Các con số chỉ là điểm bắt đầu cho benchmark, không phải cấu hình mặc định khuyến nghị cho mọi database. Cần xem xét kích thước từng row, số cột, index, constraint, payload và concurrency.

## 7. Vì sao saveAll có thể tốn nhiều SQL hơn JDBC batch?

Giả sử mỗi §Book§ chỉ là một hàng đơn giản, việc lưu có thể tương đối gọn. Nhưng một §PurchaseOrder§ có nhiều §OrderLine§ thì một aggregate cần ghi vào nhiều bảng.

Ví dụ:

~~~text
purchase_orders
    id
    ordered_on

order_lines
    order_id
    line_number
    product_code
    quantity
~~~

Khi lưu nhiều aggregate, Spring Data JDBC cần duy trì quan hệ root-child và các quy tắc aggregate. Tùy loại thao tác và phiên bản, việc ghi có thể phát sinh statement cho root và child. Một lần gọi §saveAll(orders)§ vì vậy không thể được đánh giá như một batch INSERT đơn giản vào một bảng.

JDBC batch thuần có thể ghi bảng §order_lines§ rất nhanh, nhưng ứng dụng phải tự:

- Lấy hoặc tạo ID của root.
- Gắn đúng §order_id§ cho từng child.
- Bảo đảm collection key không trùng.
- Giữ thứ tự ghi phù hợp với foreign key.
- Xử lý transaction khi ghi root và child.
- Xử lý lỗi giữa các nhóm và khôi phục dữ liệu.
- Duy trì optimistic locking/lifecycle nếu domain cần.

Nếu tự viết batch để tăng hiệu năng nhưng bỏ sót invariant của aggregate, dữ liệu có thể nhanh hơn nhưng sai về nghiệp vụ.

## 8. Khi nào nên dùng saveAll?

Dùng §saveAll§ khi:

- Input là một tập aggregate root của Spring Data JDBC.
- Cần mapping annotation như §@Id§, §@Column§, §@MappedCollection§.
- Cần generated ID hoặc version từ repository.
- Cần Spring Data conversion và lifecycle callbacks.
- Cần giữ quy tắc lưu/xóa child theo aggregate.
- Khối lượng dữ liệu vừa phải và throughput hiện tại đáp ứng yêu cầu.
- Cần code dễ bảo trì, gắn với domain model và repository.

Ví dụ:

~~~java
@Transactional
public List<Book> registerBooks(List<Book> input) {
    Iterable<Book> saved = bookRepository.saveAll(input);

    List<Book> result = new ArrayList<>();
    saved.forEach(result::add);
    return result;
}
~~~

Dùng kết quả trả về để lấy ID/version. Transaction ở service giúp diễn đạt rõ phạm vi nghiệp vụ, đặc biệt khi use case có thêm thao tác khác ngoài một repository method.

## 9. Khi nào nên dùng JDBC batch?

JDBC batch phù hợp khi:

- Ghi nhiều hàng có cùng cấu trúc SQL.
- Dữ liệu dạng bảng đơn giản, không cần aggregate mapping phức tạp.
- Ứng dụng kiểm soát rõ SQL và cách bind tham số.
- Cần throughput cao cho import, audit log, event hoặc dữ liệu staging.
- Có thể tự quản lý ID, foreign key, constraint và transaction.
- Có benchmark chứng minh batch giải quyết được bottleneck.

Ví dụ batch INSERT:

~~~java
@Repository
public class AuditEventBatchDao {

    private final JdbcTemplate jdbc;

    public AuditEventBatchDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int[] insertBatch(List<AuditEvent> events) {
        String sql = """
                INSERT INTO audit_events (event_type, message, created_at)
                VALUES (?, ?, ?)
                """;

        return jdbc.batchUpdate(
                sql,
                events,
                500,
                (ps, event) -> {
                    ps.setString(1, event.type());
                    ps.setString(2, event.message());
                    ps.setTimestamp(3, Timestamp.from(event.createdAt()));
                }
        );
    }
}
~~~

Code tự kiểm soát cột và kiểu bind. §AuditEvent§ không được tự động ánh xạ qua entity metadata Spring Data JDBC; đây là chủ đích của DAO SQL thuần.

### 9.1. Ghi nhiều loại SQL

Batch thường hiệu quả nhất khi nhiều phần tử dùng cùng statement shape. Nếu mỗi phần tử yêu cầu một câu SQL khác nhau, lợi ích batching giảm hoặc không áp dụng được theo cách đơn giản.

Nếu phải ghi nhiều bảng có phụ thuộc, có thể chia thành các batch theo bảng/thứ tự:

1. Batch INSERT bảng cha và nhận/chuẩn bị khóa.
2. Batch INSERT bảng con với khóa ngoại.
3. Commit trong transaction phù hợp.

Tuy nhiên, cách lấy generated keys từ batch phụ thuộc driver và API. Với ID cần liên kết, có thể tạo ID ở application trước (UUID), hoặc dùng chiến lược lấy key đã được xác nhận trên driver/database. Không nên giả định §batchUpdate§ luôn trả về một generated key cho mỗi phần tử.

## 10. Transaction và atomicity khi batch

Batch execution và transaction là hai cơ chế khác nhau:

- **Batch** điều khiển cách gửi/thực thi nhiều statement.
- **Transaction** xác định phạm vi commit/rollback.

Có thể dùng JDBC batch trong transaction:

~~~java
@Service
public class AuditImportService {

    private final AuditEventBatchDao dao;

    public AuditImportService(AuditEventBatchDao dao) {
        this.dao = dao;
    }

    @Transactional
    public void importEvents(List<AuditEvent> events) {
        dao.insertBatch(events);
        // Có thể thực hiện thêm thao tác cùng transaction.
    }
}
~~~

Nếu transaction manager quản lý cùng §DataSource§, các câu lệnh JDBC được thực hiện qua §JdbcTemplate§ có thể tham gia transaction hiện tại.

Không nên suy luận batch luôn atomic. Kết quả khi có lỗi phụ thuộc database, driver, transaction manager và cách lỗi được xử lý. Nếu transaction được rollback đúng cách trên database hỗ trợ transaction, các thay đổi trong transaction có thể được rollback. Nếu không có transaction chung, một phần batch có thể đã được commit hoặc có trạng thái thực thi cần đối soát.

Mặc định Spring rollback với §RuntimeException§ và §Error§; checked exception thường cần cấu hình §rollbackFor§ nếu muốn rollback. Hãy để exception persistence thoát ra khỏi ranh giới transaction khi cần rollback; bắt rồi nuốt lỗi có thể làm transaction commit hoặc bị đánh dấu rollback-only tùy tình huống.

## 11. Chia chunk và transaction boundary

Khi import lớn, không nhất thiết xử lý toàn bộ input trong một transaction khổng lồ. Có thể chia chunk để kiểm soát bộ nhớ và thời gian xử lý:

~~~java
public void importInChunks(List<AuditEvent> events) {
    int chunkSize = 500;

    for (int start = 0; start < events.size(); start += chunkSize) {
        int end = Math.min(start + chunkSize, events.size());
        List<AuditEvent> chunk = events.subList(start, end);

        auditEventBatchDao.insertBatch(chunk);
    }
}
~~~

Đoạn code trên không tự tạo transaction riêng cho từng chunk. Transaction boundary phụ thuộc nơi đặt §@Transactional§ và cách gọi qua Spring proxy.

Có hai lựa chọn phổ biến:

| Chiến lược | Đặc điểm |
|---|---|
| Một transaction cho toàn bộ import | Atomic toàn bộ nghiệp vụ nếu database/transaction hỗ trợ; lock và rollback có thể lớn |
| Một transaction cho mỗi chunk | Giảm thời gian và phạm vi rollback; chunk trước có thể đã commit khi chunk sau thất bại |

Nếu mỗi chunk cần commit độc lập, đặt logic transaction ở method được gọi qua proxy hoặc dùng cơ chế transaction propagation phù hợp. Điều đó thay đổi semantics: chunk trước có thể đã commit dù chunk sau thất bại.

Với import nhiều triệu hàng, cần thêm khả năng resume, idempotency, checkpoint và đối soát số lượng đã ghi. Chunking chỉ giải quyết một phần chi phí vận hành.

## 12. Đánh giá chi phí ghi bằng benchmark

Không chọn §saveAll§ hay JDBC batch chỉ bằng cảm giác. Hãy benchmark trong điều kiện gần với production.

### 12.1. Các chỉ số cần đo

| Chỉ số | Ý nghĩa |
|---|---|
| Rows/second | Throughput ghi |
| Total duration | Thời gian hoàn thành toàn bộ workload |
| p50/p95/p99 latency | Độ trễ của một chunk hoặc một lần gọi |
| SQL statement count | Số statement thực tế |
| Batch count / batch size | Số batch và kích thước mỗi batch |
| DB CPU / IO | Chi phí xử lý tại database |
| Lock wait / deadlock | Tranh chấp khi ghi đồng thời |
| WAL/transaction log volume | Khối lượng log phát sinh |
| Heap / allocation / GC | Chi phí bộ nhớ và object mapping |
| Error rate / rollback rate | Độ ổn định khi dữ liệu lỗi hoặc tải cao |

### 12.2. Thiết kế phép đo công bằng

Khi so sánh, giữ các yếu tố giống nhau:

- Cùng database, schema, index và constraint.
- Cùng tập dữ liệu và kiểu dữ liệu.
- Cùng số lượng bản ghi và concurrency.
- Cùng transaction boundary và durability settings.
- Cùng môi trường mạng và connection pool.
- Warm-up JVM/connection pool trước khi lấy số liệu.
- Chạy nhiều lượt, báo median và percentile thay vì chỉ lấy lần chạy nhanh nhất.

Đặc biệt, so sánh phải cùng semantics. Nếu §saveAll§ ghi aggregate gồm root và child nhưng JDBC batch chỉ INSERT một bảng, kết quả throughput không tương đương về công việc hoàn thành.

### 12.3. Ví dụ tính throughput

Giả sử benchmark ghi 50.000 hàng trong 25 giây:

\[
\text{throughput} = \frac{50.000}{25} = 2.000 \text{ rows/second}
\]

Nếu phương án khác ghi cùng dữ liệu trong 10 giây:

\[
\text{throughput} = \frac{50.000}{10} = 5.000 \text{ rows/second}
\]

Tăng throughput:

\[
\frac{5.000 - 2.000}{2.000} \times 100\% = 150\%
\]

Con số chỉ có ý nghĩa nếu hai lần đo thực hiện cùng công việc, cùng độ bền dữ liệu và cùng yêu cầu nhất quán. Không thể kết luận JDBC batch tốt hơn 150% nếu một phương án bỏ qua constraint, callback hoặc bảng con mà phương án kia phải xử lý.

## 13. Những tối ưu khác ngoài batching

Batching không phải cách duy nhất giảm chi phí ghi. Một số yếu tố khác có thể tác động mạnh:

### 13.1. Giảm số index không cần thiết

Mỗi INSERT/UPDATE có thể phải cập nhật nhiều index. Index hỗ trợ truy vấn nhưng làm tăng chi phí ghi và dung lượng. Chỉ giữ index phục vụ truy vấn/constraint thực tế.

### 13.2. Kiểm tra constraint và foreign key

Constraint bảo vệ dữ liệu và thường cần thiết. Tuy nhiên, import lớn cần đảm bảo thứ tự ghi và dữ liệu tham chiếu hợp lệ. Không nên tắt constraint trong production chỉ để tăng tốc nếu không có quy trình xác minh và phục hồi an toàn.

### 13.3. Chọn connection pool hợp lý

Quá nhiều connection đồng thời có thể làm database quá tải. Batch lớn với concurrency cao có thể tăng lock contention thay vì tăng throughput. Kích thước pool cần dựa vào năng lực database và workload.

### 13.4. Giảm payload và mapping không cần thiết

Chỉ ghi các cột cần thiết. Với repository aggregate, thiết kế aggregate hợp lý để tránh tải/lưu object graph quá lớn. Với JDBC batch, bind đúng kiểu và tránh tạo object trung gian không cần thiết.

### 13.5. Dùng native bulk load khi phù hợp

Một số database có công cụ nạp dữ liệu chuyên biệt (ví dụ cơ chế COPY hoặc bulk insert). Chúng có thể nhanh hơn JDBC batch cho import rất lớn, nhưng có semantics và giới hạn riêng về constraint, trigger, transaction, format và error handling. Chỉ dùng khi có benchmark và kế hoạch vận hành rõ ràng.

## 14. Quy trình lựa chọn công cụ

~~~mermaid
flowchart TD
    A["Cần ghi nhiều dữ liệu"] --> B{"Dữ liệu là aggregate Spring Data JDBC?"}
    B -->|Có| C{"Cần mapping, lifecycle, version, generated ID?"}
    C -->|Có| D["Dùng saveAll / repository"]
    C -->|Không hoặc ghi SQL chuyên biệt| E{"SQL có cùng cấu trúc và dữ liệu dạng bảng?"}
    B -->|Không| E
    E -->|Có| F["Đo thử JdbcTemplate.batchUpdate"]
    E -->|Không| G["Thiết kế SQL/import strategy riêng"]
    D --> H["Benchmark cùng semantics"]
    F --> H
    G --> H
    H --> I["Chọn theo throughput, latency, consistency và khả năng phục hồi"]
~~~

Có thể áp dụng các quy tắc thực tế:

1. **CRUD domain thông thường:** dùng repository và §save§/§saveAll§.
2. **Import nhiều hàng đơn giản:** benchmark JDBC batch.
3. **Ghi aggregate nhiều bảng:** ưu tiên repository nếu cần giữ mapping/lifecycle; chỉ viết batch thủ công khi đã chủ động triển khai invariant.
4. **Import cực lớn:** cân nhắc staging table/native bulk load, sau đó validate và chuyển dữ liệu vào bảng chính.
5. **Nghiệp vụ cần atomic:** thiết kế transaction boundary rõ ràng bất kể dùng repository hay batch.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ §saveAll§ chắc chắn là JDBC batch | Kỳ vọng hiệu năng sai | Đo SQL thực tế và kiểm tra implementation phiên bản |
| Chọn JDBC batch chỉ vì nhanh hơn trong benchmark không tương đương | Có thể bỏ qua aggregate/lifecycle/constraint | So sánh cùng semantics và dữ liệu |
| Batch size quá lớn | Bộ nhớ, lock và rollback tăng | Thử nhiều kích thước và đo |
| Không có transaction chung khi ghi nhiều bảng | Có thể để lại dữ liệu dở dang | Đặt transaction boundary và xử lý lỗi |
| Giả định batch luôn trả generated key | Không lấy được ID để liên kết bảng con | Kiểm tra driver/API hoặc tạo ID ở application |
| Bỏ qua update counts | Không biết phần tử nào thành công/thất bại | Kiểm tra count và §BatchUpdateException§ |
| Retry toàn bộ batch sau lỗi | Có thể ghi trùng hoặc lặp side effect | Thiết kế idempotency và đối soát |
| Ghi child trước root | Vi phạm foreign key | Sắp xếp thứ tự ghi hoặc dùng chiến lược key phù hợp |
| Chunk nhưng vẫn giữ một transaction khổng lồ | Không giảm lock/rollback scope | Tách transaction theo chunk nếu semantics cho phép |
| Tắt constraint để import nhanh | Dữ liệu không hợp lệ lọt vào | Dùng staging, validate và constraint có kiểm soát |

## 16. Bài tập thực hành

### Bài 1 — Quan sát saveAll

Tạo danh sách 100 §Book§, gọi §saveAll§, bật SQL logging và đếm statement thực tế. Ghi nhận số lần INSERT/UPDATE và cách generated ID được trả về.

### Bài 2 — Viết JDBC batch

Tạo bảng §audit_events§ có ba cột đơn giản. Viết DAO dùng §JdbcTemplate.batchUpdate§ với batch size 100, 500 và 1.000. So sánh thời gian, throughput và bộ nhớ.

### Bài 3 — So sánh công bằng

Chạy hai phương án ghi cùng 10.000 hàng, cùng schema/index/constraint và cùng transaction policy. So sánh total duration, rows/second, p95 latency và SQL statement count.

### Bài 4 — Batch có lỗi

Đưa một phần tử vi phạm unique constraint vào giữa batch. Quan sát §BatchUpdateException§, update counts và trạng thái dữ liệu sau rollback/commit. Lặp lại trên database production mục tiêu nếu semantics phụ thuộc driver.

### Bài 5 — Aggregate root và child

Tạo §PurchaseOrder§ có nhiều §OrderLine§. Lưu bằng §saveAll§. Sau đó thử ghi root và child bằng JDBC batch thuần. Liệt kê những invariant và lifecycle mà code batch phải tự đảm bảo.

### Bài 6 — Chunk và transaction

Import 50.000 hàng theo chunk 500. So sánh một transaction toàn bộ với transaction riêng cho từng chunk. Quan sát lock duration, rollback scope và khả năng tiếp tục sau lỗi.

### Bài 7 — Đọc execution metrics

Dùng log SQL, metrics connection pool và công cụ quan sát database để xác định bottleneck là network, statement execution, index, constraint, lock hay transaction log. Chọn tối ưu dựa trên bottleneck đã đo.

## 17. Ghi nhớ

- §saveAll§ là API lưu nhiều entity/aggregate theo semantics Spring Data JDBC; nó **không bảo đảm** dùng JDBC batch hay một câu SQL.
- JDBC batch là cơ chế thực thi nhiều bộ tham số cho statement; ứng dụng tự quản lý SQL, mapping, generated ID, quan hệ và invariant.
- §saveAll§ phù hợp với aggregate, mapping, conversion, lifecycle và optimistic locking; JDBC batch phù hợp với ghi SQL đồng nhất, số lượng lớn.
- Batch giảm một phần overhead gửi/thực thi lặp lại, nhưng không loại bỏ chi phí index, constraint, WAL, lock, commit và mapping.
- Batch size cần benchmark; quá lớn có thể tăng memory, lock duration và rollback cost.
- Batch và transaction là hai cơ chế khác nhau. Cần transaction boundary rõ nếu nhiều lần ghi phải atomic.
- Đánh giá hiệu năng phải so sánh **cùng công việc và cùng semantics**, bằng throughput, latency, statement count, database resource và khả năng phục hồi.
