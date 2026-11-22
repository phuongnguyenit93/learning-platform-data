# Xử lý dữ liệu lớn theo lô và giữ giao dịch có kích thước phù hợp

## 1. Vì sao phải chia dữ liệu lớn thành các lô?

Một ứng dụng Spring Data JDBC có thể bắt đầu bằng những thao tác nhỏ: lưu một customer, cập nhật một đơn hàng hoặc tải một aggregate theo ID. Khi hệ thống phát triển, ứng dụng có thể phải:

- Import hàng trăm nghìn customer từ file.
- Đồng bộ dữ liệu từ một hệ thống bên ngoài.
- Cập nhật trạng thái cho một lượng lớn đơn hàng.
- Tạo dữ liệu tổng hợp theo ngày hoặc theo kỳ.
- Xử lý lại các bản ghi lỗi sau một lần triển khai.
- Chạy tác vụ bảo trì hoặc backfill dữ liệu lịch sử.

Nếu tải toàn bộ dữ liệu vào một List, xử lý tất cả rồi gọi saveAll một lần, ứng dụng có thể tiêu thụ nhiều heap, giữ transaction lâu và tạo lượng SQL lớn. Nếu commit sau từng bản ghi, overhead mở/commit transaction lại tăng cao.

Giải pháp thường dùng là **batch processing**: đọc một nhóm bản ghi, xử lý nhóm đó, ghi dữ liệu và kết thúc transaction; sau đó tiếp tục nhóm tiếp theo.

Tuy nhiên, trong JDBC có nhiều khái niệm cùng mang tên batch. Cần phân biệt:

1. **Batch SQL:** số lần thực thi cùng một prepared statement được gom lại để giảm round trip.
2. **Application chunk:** số item ứng dụng đọc và xử lý trong một lượt.
3. **Transaction chunk:** số item được ghi trong một transaction trước khi commit.

Ba kích thước này có thể bằng nhau, nhưng không bắt buộc phải bằng nhau. Đặt batch SQL là 500 không có nghĩa transaction tự commit sau mỗi 500 item. Đặt vòng lặp xử lý 500 item cũng không tạo transaction riêng nếu toàn bộ vòng lặp vẫn nằm trong một transaction bên ngoài.

Bài này trình bày cách xử lý dữ liệu lớn trong Spring Data JDBC, cách chọn API phù hợp cho aggregate và SQL lặp lại, cách đọc dữ liệu theo luồng hoặc trang, cách tạo transaction theo từng chunk và cách kiểm soát lỗi, checkpoint cùng hiệu năng.

## 2. Phân biệt ba loại kích thước

Giả sử một job import 100.000 customer.

| Khái niệm | Ví dụ | Tác dụng |
| --- | ---: | --- |
| Application chunk size | 500 customer | Giới hạn số object giữ trong bộ nhớ và số item xử lý trong một lượt. |
| JDBC batch size | 100 câu UPDATE giống nhau | Giảm số lần gửi lệnh qua mạng tới database. |
| Transaction size/commit interval | 500 customer | Giới hạn số thay đổi commit hoặc rollback cùng nhau. |

Một cách triển khai có thể:

- Đọc 500 customer vào một chunk.
- Ghi chúng bằng một hoặc nhiều JDBC batch, mỗi batch 100 câu lệnh.
- Commit transaction sau khi ghi xong toàn bộ 500 customer.

Khi đó, JDBC batch size là 100 nhưng transaction size là 500.

~~~text
Đọc nguồn
   |
   v
Application chunk: 500 item
   |
   +--> JDBC batch 1: 100 statement
   +--> JDBC batch 2: 100 statement
   +--> JDBC batch 3: 100 statement
   +--> JDBC batch 4: 100 statement
   +--> JDBC batch 5: 100 statement
   |
   v
COMMIT transaction của chunk
   |
   v
Đọc chunk tiếp theo
~~~

Nếu một chunk cần nhiều statement cho mỗi aggregate, số statement thực tế có thể lớn hơn số item. Ví dụ một đơn hàng có một root row và 20 dòng hàng. Ghi 500 aggregate có thể phát sinh nhiều nghìn thao tác SQL.

Vì vậy, không nên chọn kích thước chỉ dựa trên số aggregate root. Hãy xem cả số child row, số statement, kích thước payload và thời gian xử lý của mỗi item.

## 3. saveAll trong Spring Data JDBC có ý nghĩa gì?

Repository kế thừa CrudRepository có method:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Có thể gọi:

~~~java
List<Customer> customers = loadCustomers();
customerRepository.saveAll(customers);
~~~

`saveAll(Iterable<S>)` lưu các aggregate được truyền vào và trả về các instance đã lưu. Với Spring Data JDBC, thao tác lưu một aggregate bao gồm cả các thành viên thuộc aggregate đó.

### 3.1. saveAll không có tham số commit interval

API `CrudRepository.saveAll` không nhận một tham số `batchSize` hoặc `commitInterval`. Vì vậy, caller không thể yêu cầu method tự chia một nguồn dữ liệu vô hạn thành từng nhóm 500 item.

Ở tầng `JdbcAggregateTemplate`, Spring Data JDBC có các thao tác `saveAll`, `insertAll` và `updateAll` để xử lý nhiều aggregate. Framework xây dựng batch aggregate change cho tập instance được cung cấp. Tuy nhiên, điều đó không đồng nghĩa với việc ứng dụng có thể truyền một nguồn dữ liệu không giới hạn mà không tiêu tốn bộ nhớ, hoặc mỗi nhóm nội bộ tự động commit thành một transaction riêng.

Nếu ứng dụng đã đọc 200.000 aggregate vào một List rồi gọi `saveAll`, chi phí tạo và giữ các object vẫn đã phát sinh trước khi repository thực thi. Nếu cần transaction theo chunk, caller phải tự giới hạn số aggregate đưa vào mỗi lần gọi và đặt transaction boundary phù hợp.

### 3.2. Lưu aggregate có thể tạo nhiều SQL

Spring Data JDBC lưu theo aggregate boundary. Khi aggregate root mới, framework insert root trước rồi insert các entity được tham chiếu. Khi lưu một aggregate đã tồn tại, chiến lược mặc định có thể xóa các entity được tham chiếu, cập nhật root rồi insert lại các entity con theo trạng thái aggregate mới.

Điều này có nghĩa một lời gọi saveAll cho 500 aggregate không nhất thiết chỉ tạo 500 câu SQL. Chi phí còn phụ thuộc số bảng và số child entity trong mỗi aggregate.

Nếu chỉ thay đổi một thuộc tính trong mỗi aggregate nhưng aggregate có collection lớn, hãy đánh giá chi phí xóa và insert lại collection. Với thao tác bulk đơn giản, một câu SQL cập nhật theo điều kiện có thể phù hợp hơn, miễn là nghiệp vụ cho phép bỏ qua aggregate persistence pipeline.

### 3.3. Khi nào dùng saveAll?

`saveAll` phù hợp khi:

- Tập aggregate đã được giới hạn ở một kích thước hợp lý.
- Mỗi item cần đi qua mapping và persistence của Spring Data JDBC.
- Cần lưu cả root và các thành viên của aggregate.
- Muốn giữ lifecycle callback, auditing và optimistic locking của aggregate persistence.

Nếu nguồn dữ liệu lớn, hãy chia nguồn thành các chunk trước khi gọi `saveAll`. Nếu cần chạy một câu UPDATE lặp lại cho nhiều dòng độc lập, cân nhắc `JdbcTemplate.batchUpdate`.

## 4. Chia aggregate thành chunk và commit từng chunk

Giả sử một file chứa customer mới. Ta muốn mỗi transaction lưu tối đa 500 customer. Có thể tách phần điều phối đọc dữ liệu và phần ghi transaction thành hai bean.

### 4.1. Writer xử lý một chunk

~~~java
@Service
public class CustomerChunkWriter {

    private final CustomerRepository customers;

    public CustomerChunkWriter(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public void writeChunk(List<Customer> chunk) {
        customers.saveAll(chunk);
    }
}
~~~

Mỗi lần gọi `writeChunk` qua Spring proxy sẽ bắt đầu một transaction nếu chưa có transaction bên ngoài. Khi method kết thúc thành công, transaction được commit. Nếu exception kích hoạt rollback, toàn bộ thay đổi trong chunk đó bị rollback.

### 4.2. Coordinator không mở transaction bao trùm toàn job

~~~java
@Component
public class CustomerImportCoordinator {

    private static final int CHUNK_SIZE = 500;

    private final CustomerChunkWriter writer;

    public CustomerImportCoordinator(CustomerChunkWriter writer) {
        this.writer = writer;
    }

    public void importCustomers(Iterator<Customer> source) {
        while (source.hasNext()) {
            List<Customer> chunk = new ArrayList<>(CHUNK_SIZE);

            for (int i = 0; i < CHUNK_SIZE && source.hasNext(); i++) {
                chunk.add(source.next());
            }

            writer.writeChunk(chunk);
        }
    }
}
~~~

Coordinator chỉ giữ một chunk trong bộ nhớ tại một thời điểm. Mỗi lần gọi writer là một transaction riêng, vì writer là bean khác và lời gọi đi qua proxy.

### 4.3. Vì sao không đặt @Transactional trên coordinator?

Giả sử coordinator có `@Transactional` và gọi writer có `@Transactional` với propagation mặc định `REQUIRED`. Writer sẽ tham gia transaction đang có. Dù coordinator gọi writer 200 lần, tất cả vẫn có thể nằm trong một transaction duy nhất.

~~~text
Coordinator @Transactional
  |
  +--> writeChunk(1)  REQUIRED: tham gia transaction ngoài
  +--> writeChunk(2)  REQUIRED: tham gia transaction ngoài
  +--> writeChunk(3)  REQUIRED: tham gia transaction ngoài
  |
  +--> COMMIT khi coordinator kết thúc
~~~

Để mỗi chunk có transaction riêng:

- Để coordinator không có transaction bao trùm.
- Gọi một writer bean khác có `@Transactional` cho từng chunk.
- Hoặc dùng `TransactionTemplate` để mở và kết thúc transaction cho từng lần xử lý.

Trong cấu hình proxy mặc định, self-invocation (một method gọi method khác trong cùng object) không đi qua proxy. Đặt phương thức ghi chunk ở bean riêng là cách đơn giản để transaction boundary rõ ràng.

### 4.4. Nếu bắt buộc có transaction bên ngoài

Nếu một transaction ngoài phải tồn tại vì lý do khác, có thể cân nhắc `Propagation.REQUIRES_NEW` cho writer. Spring sẽ tạm treo transaction ngoài và mở transaction độc lập cho chunk.

Không dùng `REQUIRES_NEW` theo thói quen. Transaction ngoài vẫn giữ connection/resource trong khi transaction mới cần một connection khác. Với connection pool nhỏ và nhiều thread, điều này có thể gây cạn pool. Nếu mục tiêu chỉ là commit từng chunk, một coordinator không có transaction ngoài thường đơn giản hơn.

## 5. Dùng TransactionTemplate cho transaction theo chunk

Có thể điều khiển transaction bằng code thay vì annotation:

~~~java
@Component
public class CustomerBatchWriter {

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactionTemplate;

    public CustomerBatchWriter(
            JdbcTemplate jdbc,
            TransactionTemplate transactionTemplate
    ) {
        this.jdbc = jdbc;
        this.transactionTemplate = transactionTemplate;
    }

    public void writeChunk(List<CustomerRow> chunk) {
        transactionTemplate.executeWithoutResult(status -> {
            jdbc.batchUpdate(
                    """
                    INSERT INTO customer_import (
                        external_id,
                        email,
                        status
                    )
                    VALUES (?, ?, ?)
                    """,
                    chunk,
                    chunk.size(),
                    (ps, customer) -> {
                        ps.setString(1, customer.externalId());
                        ps.setString(2, customer.email());
                        ps.setString(3, customer.status());
                    }
            );
        });
    }
}
~~~

Mỗi lần gọi `writeChunk` chạy trong một transaction do TransactionTemplate quản lý. Khi method trả về, transaction hoàn tất. Nếu có lỗi, exception thoát khỏi callback thì transaction được rollback theo quy tắc của transaction manager.

TransactionTemplate mặc định dùng transaction manager được cấu hình trong ứng dụng. Bảo đảm transaction manager quản lý cùng DataSource mà JdbcTemplate sử dụng.

TransactionTemplate hữu ích khi:

- Muốn transaction boundary hiển thị rõ trong code.
- Cần chạy nhiều chunk trong cùng một coordinator.
- Không muốn phụ thuộc vào việc tách bean để vượt qua self-invocation.
- Cần kiểm soát propagation, timeout hoặc isolation ở từng đoạn.

## 6. JDBC batchUpdate cho nhiều câu lệnh giống nhau

Khi có nhiều dòng dữ liệu cần chạy cùng một SQL statement, JDBC batching có thể giảm số round trip giữa ứng dụng và database. Thay vì gửi một lệnh UPDATE riêng cho từng row, driver có thể gom nhiều lần bind/execute thành một batch.

Spring cung cấp các API batch của `JdbcTemplate` và `NamedParameterJdbcTemplate`.

### 6.1. BatchPreparedStatementSetter

Ví dụ cập nhật tồn kho:

~~~java
public int[] updateInventory(List<InventoryRow> rows) {
    return jdbcTemplate.batchUpdate(
            """
            UPDATE inventory
            SET available = ?
            WHERE sku = ?
            """,
            new BatchPreparedStatementSetter() {

                @Override
                public void setValues(PreparedStatement ps, int index)
                        throws SQLException {
                    InventoryRow row = rows.get(index);
                    ps.setInt(1, row.available());
                    ps.setString(2, row.sku());
                }

                @Override
                public int getBatchSize() {
                    return rows.size();
                }
            }
    );
}
~~~

`getBatchSize` cho biết số bộ tham số trong batch. `setValues` được gọi để bind giá trị cho từng phần tử. Kết quả là một mảng số hàng bị ảnh hưởng do JDBC driver báo cáo. Driver có thể trả `-2` nếu không cung cấp số lượng chính xác.

### 6.2. NamedParameterJdbcTemplate

Nếu SQL dùng named parameter, có thể tạo batch từ danh sách object:

~~~java
public int[] updateInventory(List<InventoryRow> rows) {
    SqlParameterSource[] batch =
            SqlParameterSourceUtils.createBatch(rows);

    return namedParameterJdbcTemplate.batchUpdate(
            """
            UPDATE inventory
            SET available = :available
            WHERE sku = :sku
            """,
            batch
    );
}
~~~

Các thuộc tính Java cần có tên khớp với named parameter. Cách này ngắn gọn khi object có getter/property phù hợp.

### 6.3. Chia JDBC batch thành nhiều batch nhỏ

Spring còn cung cấp overload nhận Collection, batch size và ParameterizedPreparedStatementSetter:

~~~java
int[][] updateCounts = jdbcTemplate.batchUpdate(
        """
        UPDATE inventory
        SET available = ?
        WHERE sku = ?
        """,
        inventoryRows,
        100,
        (ps, row) -> {
            ps.setInt(1, row.available());
            ps.setString(2, row.sku());
        }
);
~~~

Ở đây, Spring chia các bộ tham số thành các JDBC batch tối đa 100 statement. Giá trị trả về là mảng hai chiều: mỗi phần tử ngoài tương ứng một batch, mỗi phần tử trong chứa số hàng bị ảnh hưởng cho từng statement.

### 6.4. Batch size không phải transaction size

Đoạn code sau có batch size 100:

~~~java
@Transactional
public void updateAll(List<InventoryRow> rows) {
    jdbcTemplate.batchUpdate(SQL, rows, 100, setter);
}
~~~

Nếu `rows` có 10.000 phần tử, Spring có thể thực hiện nhiều JDBC batch trong cùng một lần gọi, nhưng method vẫn chạy trong một transaction duy nhất do `@Transactional` bao trùm.

Muốn commit mỗi 500 row, hãy chia input thành 500 row và gọi method transactional riêng cho từng chunk. Bên trong mỗi chunk, có thể tiếp tục dùng JDBC batch size 100:

~~~text
Transaction chunk: 500 row
  JDBC batch 1: 100 statement
  JDBC batch 2: 100 statement
  JDBC batch 3: 100 statement
  JDBC batch 4: 100 statement
  JDBC batch 5: 100 statement
COMMIT
~~~

## 7. Khi nào nên dùng saveAll và khi nào nên dùng batchUpdate?

Hai API giải quyết những nhu cầu khác nhau:

| Nhu cầu | API phù hợp |
| --- | --- |
| Lưu aggregate root cùng các entity con | Repository `saveAll` hoặc `JdbcAggregateTemplate.saveAll` |
| Insert nhiều aggregate có ID được cung cấp trước | `JdbcAggregateTemplate.insertAll` |
| Update nhiều aggregate đã tồn tại | `JdbcAggregateTemplate.updateAll` hoặc repository `saveAll` theo entity state |
| Chạy cùng một câu UPDATE cho nhiều dòng độc lập | `JdbcTemplate.batchUpdate` |
| Import dữ liệu dạng phẳng, không cần aggregate lifecycle | `JdbcTemplate.batchUpdate` hoặc `NamedParameterJdbcTemplate.batchUpdate` |
| Cập nhật hàng loạt theo một điều kiện chung | Một câu SQL `UPDATE ... WHERE ...` nếu semantics phù hợp |
| Job import cần restart, retry, skip và checkpoint | Spring Batch chunk-oriented processing |

### 7.1. Lưu ý khi dùng SQL bulk

Một câu `@Modifying @Query` hoặc `JdbcTemplate.update` chạy SQL trực tiếp. Nó không tự gọi lifecycle callback/event của aggregate persistence. Các trường auditing như `@LastModifiedDate` hoặc `@LastModifiedBy` cũng không tự được cập nhật nếu câu SQL không ghi các cột đó.

SQL bulk cũng không tự chạy domain method hoặc optimistic locking của aggregate. Nếu dùng cách này, hãy tự bảo vệ invariant, version, audit và các side effect cần thiết. Chỉ dùng bulk SQL khi nghiệp vụ có thể biểu diễn an toàn bằng câu lệnh đó.

## 8. Đọc dữ liệu lớn theo trang hoặc theo luồng

Xử lý ghi theo chunk không đủ nếu bước đọc vẫn tải toàn bộ bảng vào heap.

### 8.1. Page và Slice

Repository có thể khai báo query method nhận Pageable:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    Slice<Customer> findByStatus(
            CustomerStatus status,
            Pageable pageable
    );
}
~~~

Coordinator đọc từng trang:

~~~java
int pageNumber = 0;
int pageSize = 500;
Slice<Customer> slice;

do {
    Pageable pageable = PageRequest.of(
            pageNumber,
            pageSize,
            Sort.by("id").ascending()
    );

    slice = customerRepository.findByStatus(
            CustomerStatus.ACTIVE,
            pageable
    );

    processChunk(slice.getContent());
    pageNumber++;
} while (slice.hasNext());
~~~

`Page` thường cần thêm count query để biết tổng số kết quả. `Slice` chỉ cần biết còn trang tiếp theo hay không; Spring Data JDBC lấy thêm một hàng để xác định có dữ liệu tiếp tục.

Với dữ liệu lớn, nếu không cần tổng số trang, `Slice` có thể tránh chi phí count query.

### 8.2. Hạn chế của offset pagination

`PageRequest.of(pageNumber, pageSize)` thường tạo truy vấn theo offset. Khi pageNumber tăng rất lớn, database có thể phải bỏ qua nhiều hàng trước khi trả về trang tiếp theo. Nếu dữ liệu thay đổi trong lúc job chạy, offset cũng có thể khiến hàng bị lặp hoặc bị bỏ qua.

### 8.3. Keyset pagination

Keyset pagination dùng khóa của hàng cuối cùng đã đọc làm điểm bắt đầu cho lần tiếp theo:

~~~sql
SELECT id, email, status
FROM customers
WHERE id > :lastId
ORDER BY id
LIMIT :limit;
~~~

Ví dụ repository với câu SQL tùy chỉnh:

~~~java
@Query("""
    SELECT id, email, status
    FROM customers
    WHERE id > :lastId
    ORDER BY id
    LIMIT :limit
    """)
List<Customer> findNextChunk(
        @Param("lastId") long lastId,
        @Param("limit") int limit
);
~~~

Coordinator cập nhật checkpoint sau khi chunk đã xử lý thành công:

~~~java
long lastId = checkpoint.load("customer-import");

while (true) {
    List<Customer> chunk =
            repository.findNextChunk(lastId, 500);

    if (chunk.isEmpty()) {
        break;
    }

    writer.writeChunk(chunk);

    lastId = chunk.get(chunk.size() - 1).id();
    checkpoint.save("customer-import", lastId);
}
~~~

Keyset pagination phù hợp khi có khóa sắp xếp ổn định và duy nhất. Nếu sắp xếp theo nhiều cột, cursor cần chứa toàn bộ khóa sắp xếp, chẳng hạn (created_at, id). SQL cần xử lý đúng trường hợp nhiều hàng có cùng timestamp.

Ví dụ trên dùng cú pháp LIMIT thường gặp ở PostgreSQL/MySQL. Với database khác, hãy điều chỉnh cú pháp phân trang.

## 9. Dùng Stream để đọc kết quả lớn

Spring Data JDBC hỗ trợ query method trả về Stream:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    Stream<Customer> streamByStatus(CustomerStatus status);
}
~~~

Sử dụng:

~~~java
try (Stream<Customer> customers =
        customerRepository.streamByStatus(CustomerStatus.ACTIVE)) {

    customers.forEach(this::process);
}
~~~

Spring Data JDBC trả các phần tử khi chúng sẵn sàng từ database, giúp giảm nhu cầu tạo một List chứa toàn bộ kết quả. Tuy nhiên, Stream giữ một kết nối database mở cho tới khi được đóng. Luôn đóng stream bằng try-with-resources để tránh rò rỉ connection.

### 9.1. Stream không đồng nghĩa với transaction ngắn

Nếu xử lý 2 triệu hàng trong một stream và method bao ngoài có `@Transactional`, transaction có thể tồn tại trong toàn bộ thời gian duyệt stream. Điều này giữ connection và có thể giữ snapshot/lock lâu tùy isolation level.

Tránh thực hiện HTTP call, gửi email hoặc công việc chậm trong khi đang giữ cursor. Nếu cần đọc và ghi theo từng chunk rồi commit, keyset pagination thường dễ kiểm soát transaction hơn vì mỗi lượt đọc có thể kết thúc trước khi bắt đầu transaction ghi.

### 9.2. Khi nào dùng Stream?

Stream phù hợp khi:

- Muốn xử lý kết quả tuần tự và tránh materialize toàn bộ List.
- Có thể đóng stream đúng cách.
- Chấp nhận giữ connection trong thời gian đọc.
- Logic xử lý từng item tương đối ngắn.

Nếu cần checkpoint, resume, retry hoặc commit theo từng chunk, hãy cân nhắc keyset pagination hoặc Spring Batch.

## 10. Chọn transaction size

Không có một transaction size phù hợp với mọi database và mọi loại dữ liệu.

### 10.1. Transaction quá nhỏ

Nếu commit sau từng row:

- Tốn thời gian bắt đầu và kết thúc transaction.
- Tăng round trip và chi phí đồng bộ.
- Giảm lợi ích của JDBC batching.
- Tổng thời gian job có thể tăng đáng kể.

### 10.2. Transaction quá lớn

Nếu một transaction ghi hàng trăm nghìn row:

- Giữ connection và lock trong thời gian dài.
- Tăng lượng undo/redo log hoặc WAL.
- Tăng replication lag và áp lực I/O.
- Tăng nguy cơ timeout.
- Khi lỗi xảy ra, rollback có thể tốn thời gian.
- Một lỗi cuối transaction có thể làm mất toàn bộ công sức của chunk rất lớn.
- Ứng dụng có thể giữ nhiều object và aggregate change trong heap.

### 10.3. Chọn kích thước bằng phép đo

Hãy bắt đầu với một kích thước thử nghiệm có giới hạn, ví dụ 100, 250 hoặc 500 item, rồi đo trên database và dữ liệu gần production.

Các yếu tố ảnh hưởng:

- Số statement cho mỗi aggregate.
- Số child row trong aggregate.
- Kích thước dữ liệu mỗi row.
- Index, trigger và foreign key.
- JDBC driver và khả năng batch của driver.
- Thời gian xử lý nghiệp vụ cho mỗi item.
- Số transaction chạy đồng thời.
- Connection pool và giới hạn của database.
- Mức độ chấp nhận rollback một chunk.

Không tăng batch size chỉ vì một lần thử nhỏ chạy nhanh hơn. Hãy đo throughput trong một khoảng đủ dài, p95/p99 transaction duration, lock wait, memory, log volume và replication lag.

## 11. Spring Batch và chunk-oriented processing

Nếu job có yêu cầu vận hành như restart, checkpoint, retry, skip, job repository và theo dõi tiến độ, Spring Batch cung cấp mô hình chunk-oriented processing.

Luồng xử lý:

~~~text
ItemReader
    |
    v
ItemProcessor (tùy chọn)
    |
    v
Tích lũy commit interval item
    |
    v
ItemWriter ghi chunk
    |
    v
COMMIT transaction
    |
    v
Đọc chunk tiếp theo
~~~

Ví dụ cấu hình step theo API Spring Batch hiện đại:

~~~java
@Bean
Step importCustomers(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer
) {
    return new StepBuilder("importCustomers", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Trong ví dụ, commit interval là 500 item. Spring Batch đọc và xử lý một chunk, gọi ItemWriter, rồi commit transaction. Nếu chunk thất bại, transaction của chunk được rollback theo cấu hình step.

### 11.1. Commit interval khác JDBC batch size

Nếu ItemWriter dùng JdbcTemplate.batchUpdate với batch size 100 trong step có chunk size 500, một transaction chunk có thể chứa nhiều JDBC batch. Commit interval quyết định transaction boundary; JDBC batch size quyết định số statement được gom trong mỗi batch call.

### 11.2. Restart và idempotence

Khi job dừng giữa chừng, Spring Batch có thể dùng ExecutionContext/JobRepository để khôi phục trạng thái đọc theo cấu hình ItemReader. ItemWriter vẫn phải được thiết kế phù hợp với semantics retry và restart.

Nếu job ghi vào database khác với database lưu JobRepository, hai database không tự động nằm trong cùng transaction. Một sự cố đúng thời điểm có thể khiến dữ liệu nghiệp vụ đã commit nhưng checkpoint chưa được ghi, dẫn tới chunk được chạy lại. Idempotent writer hoặc khóa nghiệp vụ duy nhất giúp tránh dữ liệu trùng.

## 12. Checkpoint và khả năng chạy lại

Với job tự viết, checkpoint cần được lưu cùng tiến độ đã hoàn thành.

Ví dụ bảng:

~~~sql
CREATE TABLE batch_checkpoint (
    job_name VARCHAR(100) PRIMARY KEY,
    last_processed_id BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

Nếu dữ liệu nghiệp vụ và checkpoint nằm trong cùng database, có thể cập nhật checkpoint trong cùng transaction chunk:

~~~java
@Transactional
public void writeChunk(List<Customer> chunk, long lastId) {
    customerRepository.saveAll(chunk);
    checkpointRepository.updateLastId("customer-import", lastId);
}
~~~

Nếu transaction commit, cả dữ liệu và checkpoint cùng commit. Nếu rollback, cả hai cùng rollback.

Nếu checkpoint nằm ở hệ thống khác, không có transaction phân tán, phải chấp nhận khả năng job chạy lại một chunk. Khi đó, writer cần idempotent.

### 12.1. Thiết kế idempotent

Một thao tác idempotent có thể chạy lại mà không tạo kết quả sai hoặc trùng. Ví dụ:

- Dùng external ID có unique constraint.
- Dùng upsert theo khóa nghiệp vụ nếu database/dialect hỗ trợ.
- Dùng điều kiện UPDATE để chỉ chuyển trạng thái từ một trạng thái xác định.
- Lưu import batch ID hoặc idempotency key.
- Không gửi email hoặc thanh toán trực tiếp trong đoạn có thể retry nếu chưa có cơ chế chống trùng.

Không dựa vào checkpoint đơn độc để bảo đảm không có bản ghi trùng. Checkpoint có thể bị ghi trễ hoặc job có thể chạy lại sau khi chunk đã commit.

## 13. Xử lý lỗi trong một chunk

Giả sử chunk có 500 customer và bản ghi thứ 420 vi phạm unique constraint. Nếu toàn bộ chunk nằm trong một transaction và lỗi làm transaction rollback, 419 bản ghi trước đó trong chunk cũng bị rollback.

Đây là hành vi nhất quán nhưng cần chính sách xử lý:

- Sửa dữ liệu nguồn rồi chạy lại chunk.
- Ghi bản ghi lỗi vào bảng quarantine trong một transaction phù hợp.
- Dùng Spring Batch retry cho lỗi transient như deadlock hoặc timeout.
- Dùng skip cho lỗi dữ liệu được xác định rõ và có giới hạn.
- Chia nhỏ chunk khi cần khoanh vùng lỗi.

Không bắt mọi exception rồi bỏ qua. Nếu database transaction đã bị đánh dấu rollback-only, bắt exception trong code không làm transaction trở lại trạng thái commit được.

### 13.1. Retry phải giới hạn và có backoff

Retry hữu ích với lỗi tạm thời như deadlock hoặc lock timeout. Nên:

- Chỉ retry các exception được xác định là transient.
- Giới hạn số lần thử.
- Có backoff giữa các lần thử.
- Bảo đảm thao tác có thể chạy lại an toàn.
- Ghi log batch ID, checkpoint và nguyên nhân cuối cùng.

Không retry vô hạn một lỗi dữ liệu như giá trị vượt độ dài cột hoặc vi phạm constraint do dữ liệu nguồn sai.

## 14. Optimistic locking và xử lý đồng thời

Nếu aggregate có thuộc tính `@Version`, Spring Data JDBC kiểm tra version khi cập nhật. Khi một transaction khác đã cập nhật aggregate, thao tác lưu có thể ném `OptimisticLockingFailureException`.

Trong batch, một conflict có thể làm rollback toàn bộ chunk nếu mọi thao tác tham gia cùng transaction. Cần quyết định:

- Retry toàn bộ chunk sau khi tải lại dữ liệu.
- Tách item lỗi để xử lý riêng.
- Ghi nhận conflict và đưa vào hàng chờ xử lý.

Không bỏ qua optimistic locking chỉ để job chạy hết. Nếu ghi đè dữ liệu mới của người dùng, job có thể tạo lỗi nghiệp vụ nghiêm trọng.

Với nhiều worker, chia dữ liệu theo khoảng ID hoặc partition không chồng lấn giúp giảm tranh chấp. Tuy nhiên, phải bảo đảm các worker không cùng cập nhật một aggregate hoặc cùng một khóa nghiệp vụ.

## 15. Cập nhật bulk và lifecycle của aggregate

Một số tác vụ chỉ cần thay đổi một cột trên nhiều row:

~~~sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE created_at < :cutoff
  AND status = 'COMPLETED';
~~~

Nếu thao tác này là một chuyển đổi dữ liệu đơn giản được nghiệp vụ cho phép, một câu SQL bulk có thể hiệu quả hơn tải từng aggregate rồi save.

Nhưng bulk SQL không tự gọi domain method, lifecycle callback hoặc auditing callback của Spring Data JDBC. Nếu dùng `@Modifying` hoặc `JdbcTemplate`:

- Cập nhật audit columns ngay trong SQL nếu cần.
- Thêm điều kiện version nếu cần optimistic concurrency.
- Bảo vệ domain invariant bằng predicate/constraint.
- Phát application event hoặc ghi outbox nếu cần thông báo sau commit.
- Kiểm tra số row bị ảnh hưởng.

Nếu mỗi aggregate có quy tắc chuyển trạng thái phức tạp, hãy tải và xử lý qua domain/application service thay vì thay đổi hàng loạt bằng SQL.

## 16. Tối ưu đọc và ghi cùng một job

Một job import hoặc đồng bộ thường có cả bước đọc nguồn và bước ghi database.

### 16.1. Không giữ transaction ghi trong lúc đọc file

Đọc file lớn, parse dữ liệu hoặc gọi API ngoài nên diễn ra trước hoặc ngoài transaction ghi chunk. Transaction chỉ nên bao trùm phần cần commit/rollback cùng nhau.

Ví dụ:

~~~text
Đọc file và parse 500 dòng
        |
        v
Kiểm tra/chuẩn hóa dữ liệu
        |
        v
Mở transaction
        |
        v
Ghi chunk vào database
        |
        v
Commit
        |
        v
Đọc 500 dòng tiếp theo
~~~

Không giữ database transaction trong khi chờ file, HTTP response hoặc thao tác người dùng.

### 16.2. Giới hạn số thread và connection

Nếu chạy nhiều chunk song song, mỗi worker có thể giữ một connection. Số worker lớn hơn khả năng connection pool hoặc năng lực database có thể làm throughput giảm vì lock contention, context switching và queue chờ connection.

Hãy bắt đầu tuần tự để xác lập baseline. Sau đó tăng concurrency từng bước, đo throughput và latency. Chia partition theo khóa ổn định để giảm khả năng hai worker đụng cùng dữ liệu.

### 16.3. Dùng projection khi không cần toàn bộ aggregate

Nếu job chỉ cần ID và trạng thái để thống kê, không tải toàn bộ aggregate cùng collection child. Dùng query projection/DTO phù hợp để giảm số cột, số object và số query.

Khi cần thay đổi aggregate, hãy tải aggregate theo đúng use case. Không tải object graph lớn chỉ để lấy một vài giá trị đơn giản.

## 17. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Heap tăng nhanh khi import | Tải toàn bộ nguồn vào List trước khi ghi | Đọc và xử lý theo chunk có giới hạn. |
| saveAll mất nhiều thời gian với aggregate lớn | Mỗi aggregate có nhiều child row hoặc update phải xóa/insert lại collection | Đo số statement; cân nhắc mô hình aggregate và đường ghi phù hợp. |
| Đã chia List thành chunk nhưng chỉ commit một lần | Vòng lặp vẫn nằm trong một transaction ngoài | Đặt transaction ở writer bean riêng hoặc dùng TransactionTemplate cho từng chunk. |
| Batch size là 100 nhưng transaction vẫn rất dài | JDBC batch size chỉ chia statement batch, không tự commit | Chia application chunk và transaction boundary riêng. |
| Stream giữ connection lâu | Stream chưa được đóng hoặc xử lý bên trong một transaction dài | Dùng try-with-resources; cân nhắc keyset pagination. |
| Trang cuối bị lặp hoặc thiếu hàng | Dùng offset trong khi dữ liệu đang thay đổi hoặc sort không ổn định | Dùng keyset với khóa duy nhất và checkpoint. |
| Một lỗi làm mất cả job | Toàn bộ job nằm trong một transaction hoặc không có checkpoint | Commit theo chunk, ghi checkpoint và thiết kế retry/resume. |
| Job chạy lại tạo dữ liệu trùng | Writer không idempotent hoặc checkpoint cập nhật trễ | Dùng unique key, idempotency key và checkpoint nhất quán. |
| Deadlock tăng khi tăng worker | Nhiều worker khóa các hàng theo thứ tự khác nhau | Partition không chồng lấn, khóa theo thứ tự ổn định và retry có giới hạn. |
| Audit field không đổi sau bulk update | SQL trực tiếp không chạy lifecycle callback | Cập nhật audit columns trong SQL hoặc dùng aggregate persistence. |
| Transaction timeout | Chunk quá lớn hoặc xử lý ngoài database bên trong transaction | Giảm transaction size và đưa I/O ngoài transaction. |

## 18. Quy trình thiết kế một batch job

Khi xử lý dữ liệu lớn, hãy làm theo thứ tự:

1. **Xác định đơn vị nghiệp vụ:** một item là một row, một aggregate hay một nhóm row có quan hệ?
2. **Chọn đường đọc:** Page, Slice, Stream, keyset query hoặc Spring Batch ItemReader.
3. **Chọn đường ghi:** repository saveAll cho aggregate; JdbcTemplate.batchUpdate cho SQL lặp lại; một bulk UPDATE cho phép biến đổi chung.
4. **Đặt application chunk size:** giới hạn số object được giữ và xử lý trong một lượt.
5. **Đặt JDBC batch size:** nếu có statement lặp lại, đo số lệnh phù hợp cho mỗi batch.
6. **Đặt transaction boundary:** xác định số item được commit cùng nhau.
7. **Thiết kế lỗi:** retry lỗi transient, skip lỗi dữ liệu theo chính sách và ghi lại item lỗi.
8. **Thiết kế checkpoint:** có thể tiếp tục sau khi process dừng.
9. **Bảo đảm idempotence:** chạy lại một chunk không tạo dữ liệu sai hoặc trùng.
10. **Đo và điều chỉnh:** throughput, heap, transaction duration, lock wait, log volume và replication lag.

## 19. Bài tập tự thực hành

**Bài tập 1 — saveAll có giới hạn.** Tạo nguồn 10.000 customer và chia thành chunk 500. Gọi repository.saveAll cho từng chunk, quan sát số object trong heap và thời gian từng transaction.

**Bài tập 2 — Transaction theo chunk.** Tạo coordinator và writer bean riêng. Làm một chunk thất bại và xác nhận các chunk trước đó đã commit, chunk lỗi rollback.

**Bài tập 3 — Self-invocation.** Chuyển writer method về cùng coordinator class, gọi trực tiếp method có @Transactional và quan sát transaction boundary. Sau đó tách bean để so sánh.

**Bài tập 4 — JDBC batchUpdate.** Cập nhật 5.000 inventory row bằng BatchPreparedStatementSetter. So sánh với vòng lặp gọi update từng row.

**Bài tập 5 — Tách batch size và transaction size.** Dùng chunk 500 và JDBC batch size 100. Quan sát số batch call và thời điểm commit.

**Bài tập 6 — Page và Slice.** Viết query method trả Page và Slice. Bật SQL log, so sánh count query và cách xác định trang tiếp theo.

**Bài tập 7 — Keyset pagination.** Đọc customer theo id tăng dần, lưu checkpoint sau mỗi chunk và chạy lại job sau khi dừng giữa chừng.

**Bài tập 8 — Stream.** Tạo query method trả Stream, xử lý bằng try-with-resources và xác nhận connection được giải phóng sau khi stream đóng.

**Bài tập 9 — Spring Batch.** Tạo chunk-oriented step với commit interval 500. Làm ItemWriter lỗi ở một chunk và quan sát rollback/restart.

**Bài tập 10 — Idempotence.** Cho job chạy lại cùng một chunk hai lần. Dùng unique constraint hoặc idempotency key để bảo đảm kết quả không tạo bản ghi trùng.

**Bài tập 11 — Optimistic locking.** Chạy hai worker cùng cập nhật một aggregate có @Version. Quan sát conflict và thiết kế retry hoặc xử lý riêng.

**Bài tập 12 — Bulk update.** So sánh cập nhật từng aggregate qua repository với một câu UPDATE bulk. Kiểm tra audit, version và invariant trong cả hai cách.

## 20. Ghi nhớ

Xử lý dữ liệu lớn cần phân biệt application chunk size, JDBC batch size và transaction size. Chunk giới hạn số object xử lý trong một lượt; JDBC batch giảm round trip cho các statement giống nhau; transaction size quyết định số thay đổi commit hoặc rollback cùng nhau.

Spring Data JDBC cung cấp saveAll để lưu nhiều aggregate, nhưng API này không nhận commit interval và không thay thế việc chia nguồn thành các chunk có giới hạn. Dùng saveAll khi cần aggregate persistence; dùng JdbcTemplate.batchUpdate khi có nhiều lần thực thi cùng một SQL; dùng bulk UPDATE khi quy tắc nghiệp vụ có thể biểu diễn an toàn bằng một câu lệnh.

Đọc dữ liệu lớn bằng Page, Slice, keyset pagination hoặc Stream. Stream giúp tránh tạo toàn bộ List nhưng giữ connection mở cho tới khi được đóng. Với job cần commit và resume theo chunk, keyset pagination hoặc Spring Batch thường dễ kiểm soát hơn.

Đặt transaction ở writer cho từng chunk. Nếu coordinator cũng có transaction ngoài, propagation REQUIRED có thể khiến các chunk tham gia cùng một transaction. Giữ transaction ngắn, không gọi dịch vụ ngoài trong transaction, ghi checkpoint nhất quán và thiết kế writer idempotent để có thể chạy lại an toàn.

Không có một batch size tối ưu chung. Hãy đo trên dữ liệu gần production và điều chỉnh theo số child row, số statement, lock wait, transaction duration, heap, log volume và năng lực database.

### Tài liệu tham khảo

- [Spring Data Relational – Persisting Entities and JdbcAggregateTemplate](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data Relational – JdbcAggregateOperations API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateOperations.html)
- [Spring Data Relational – Query Methods and Streaming Results](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Framework – JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html)
- [Spring Framework – Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Batch – Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch – Commit Interval](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/commit-interval.html)
