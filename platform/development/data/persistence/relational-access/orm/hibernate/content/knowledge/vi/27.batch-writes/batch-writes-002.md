# Cấu hình kích thước JDBC batch và xác nhận driver hỗ trợ

## 1. Bài toán: 10.000 lần `persist()` có thành 10.000 lượt gửi SQL không?

Giả sử một chương trình nhập dữ liệu tạo 10.000 sản phẩm:

~~~java
for (ProductInput input : inputs) {
    entityManager.persist(Product.from(input));
}
~~~

Đây là 10.000 thao tác ở tầng ORM. Số lần JDBC driver gửi SQL còn phụ thuộc cấu hình **JDBC statement batching**, hình dạng SQL, mapping khóa chính, transaction, cách Hibernate flush và khả năng JDBC driver.

Khi batching được bật, Hibernate có thể sử dụng cùng một `PreparedStatement` cho nhiều tập giá trị:

~~~text
Java / Hibernate                    JDBC driver                   Database
------------------------------      -------------------------     --------
persist(A) -------------------\
persist(B) --------------------+---> PreparedStatement INSERT
persist(C) -------------------/      addBatch(params A)
                                     addBatch(params B)
                                     addBatch(params C)
                                     executeBatch() ------------> thực thi nhóm
~~~

Lợi ích thường thấy là giảm overhead và số lượt giao tiếp client–server. Nhưng **một `executeBatch()` không bảo đảm chỉ một network round-trip**: driver có thể gửi nhiều commands riêng hoặc rewrite thành một multi-values INSERT; điều này phụ thuộc driver/database/options.

**Mục tiêu bài học:** cấu hình kích thước JDBC batch của Hibernate và **xác nhận driver thật sự hỗ trợ**, không dừng ở việc nhìn thấy một property. Đây là bài thuộc chương **Ghi hàng loạt**, module **Data Persistence Relational Access ORM Hibernate**.

Nội dung sẽ làm rõ:

- JDBC `addBatch()`/`executeBatch()` và Hibernate `hibernate.jdbc.batch_size`.
- Cấu hình theo project và override riêng cho `Session`.
- `DatabaseMetaData.supportsBatchUpdates()` và thử batch thực tế.
- Các điều kiện khiến INSERT/UPDATE không được gom (nhất là IDENTITY).
- Driver rewrite options, update counts, optimistic locking và xử lý lỗi.
- Flush/clear interval, transaction chunk, SQL ordering, logging và benchmark.
- Phân biệt JDBC write batching với batch fetching và bulk HQL DML.

> Ví dụ tập trung Jakarta Persistence và Hibernate ORM 6.6. Những API/config tương tự tồn tại ở các phiên bản khác, nhưng chi tiết `StatelessSession`, metadata, driver behavior và API version phải kiểm tra theo dependency thực tế.

## 2. JDBC batch thực chất là gì?

### 2.1. PreparedStatement với nhiều bộ tham số

~~~java
String sql = """
    INSERT INTO products(id, sku, name)
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (ProductInput p : products) {
        ps.setLong(1, p.id());
        ps.setString(2, p.sku());
        ps.setString(3, p.name());
        ps.addBatch();
    }

    int[] updateCounts = ps.executeBatch();
}
~~~

Mỗi `addBatch()` lưu một bộ parameter cho cùng SQL template. `executeBatch()` yêu cầu driver thực thi các phần tử đã chờ.

Ví dụ 12 INSERT tương thích, kích thước batch 5:

~~~text
BATCH 1: 5 executions -> executeBatch()
BATCH 2: 5 executions -> executeBatch()
BATCH 3: 2 executions -> executeBatch() ở flush/transaction boundary
~~~

**Batch size là giới hạn trên**, không phải lời hứa mọi batch đều đầy. Sự thay đổi SQL template, flush giữa chừng, dependency FK hoặc identifier generation đều có thể làm batch nhỏ hơn.

### 2.2. Không nhầm JDBC batching với công nghệ khác

| Khái niệm | Mục đích | Có phải JDBC write batching? |
|---|---|---|
| Nhiều `persist()` rồi Hibernate gom DML | Nhiều entity actions cùng SQL | Có thể |
| `PreparedStatement.addBatch/executeBatch` | Nhiều parameter sets qua JDBC | Có |
| HQL bulk `update Product p set ...` | Một set-based UPDATE tại DB | Không |
| SQL `INSERT ... SELECT ...` | Một statement chèn từ query | Không nhất thiết |
| SQL multi-values INSERT | Một câu INSERT chứa nhiều row | Không nhất thiết là JDBC addBatch |
| `@BatchSize` | Nạp entity/association theo nhóm | Không |
| `hibernate.default_batch_fetch_size` | Batch fetching trong SELECT | Không |
| `hibernate.jdbc.fetch_size` | Hint số hàng fetch từ ResultSet | Không |

Khi nói “batch size 30” phải rõ đây là `hibernate.jdbc.batch_size` để gom **ghi**, chứ không phải `@BatchSize(30)` để tối ưu **đọc**.

### 2.3. Tại sao SQL phải tương thích?

Một batch JDBC dựa trên nhiều executions có thể dùng cùng một statement structure. Nếu luồng ghi xen kẽ:

~~~text
INSERT INTO products(...)
INSERT INTO audit_logs(...)
INSERT INTO products(...)
INSERT INTO prices(...)
INSERT INTO products(...)
~~~

các INSERT của products có thể không nằm liền nhau để gom hiệu quả. Hibernate có `hibernate.order_inserts` hỗ trợ tổ chức lại INSERT actions khi có thể.

Tương tự, nếu `@DynamicUpdate` làm SQL UPDATE của mỗi entity gồm các cột khác nhau, SQL template có thể khác và làm batch kém hiệu quả. Không có cách cấu hình số 50 để bắt driver gom các SQL khác cấu trúc vào một PreparedStatement giống hệt nhau.

## 3. Cấu hình kích thước Hibernate JDBC batch

### 3.1. Setting chính

~~~properties
hibernate.jdbc.batch_size=30
~~~

Theo Hibernate ORM 6.6, giá trị mặc định là **0**, tức **không bật JDBC statement batching**; một giá trị dương kích hoạt khả năng gom lệnh tương thích. Hướng dẫn Hibernate trước đây gợi ý bắt đầu thử trong khoảng **10–50**, sau đó đo trên workload thật.

Các lựa chọn liên quan:

~~~properties
hibernate.jdbc.batch_size=30
hibernate.order_inserts=true
hibernate.order_updates=true
~~~

- `hibernate.jdbc.batch_size`: số executions tối đa Hibernate gom vào batch.
- `hibernate.order_inserts=true`: sắp xếp INSERT theo loại entity/statement để tăng cơ hội batching.
- `hibernate.order_updates=true`: sắp xếp UPDATE theo entity và identifier, có thể tăng batching và giảm một số deadlocks.
- Cả hai `order_*` gây thêm CPU/sort overhead, nên benchmark thay vì mặc định bật cho mọi workload.

### 3.2. Cấu hình Spring Boot

`application.properties`:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=30
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Tương đương `application.yml`:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 30
        order_inserts: true
        order_updates: true
        generate_statistics: true
~~~

Các property dưới `spring.jpa.properties` được chuyển cho Hibernate. `hibernate.generate_statistics` chỉ nên bật có chủ đích khi kiểm tra hoặc đo, vì thống kê/log có chi phí.

Hãy kiểm tra **effective configuration**: environment variables, Spring profiles hoặc config server có thể override file mặc định. Nếu provider không phải Hibernate, property Hibernate không tự có tác dụng.

### 3.3. Cấu hình Hibernate thuần

Trong `hibernate.cfg.xml`:

~~~xml
<hibernate-configuration>
  <session-factory>
    <property name="hibernate.jdbc.batch_size">30</property>
    <property name="hibernate.order_inserts">true</property>
    <property name="hibernate.order_updates">true</property>
  </session-factory>
</hibernate-configuration>
~~~

Đây là fragment; ứng dụng thực tế còn khai báo DataSource/connection, entity mappings, dialect và bootstrap.

### 3.4. Các setting liên quan và giới hạn

| Property | Vai trò | Lưu ý |
|---|---|---|
| `hibernate.jdbc.batch_size` | Giới hạn số DML executions trong batch | Mặc định 0 |
| `hibernate.order_inserts` | Gom INSERT tương thích sát nhau | Có thể thay đổi thứ tự thực thi |
| `hibernate.order_updates` | Sắp thứ tự UPDATE theo entity/PK | Thêm chi phí sort |
| `hibernate.jdbc.batch_versioned_data` | Batching UPDATE của versioned entities | Phụ thuộc độ chính xác driver update counts/dialect |
| `hibernate.jdbc.batch.builder` | Chọn BatchBuilder implementation | Thường giữ mặc định |
| `hibernate.generate_statistics` | Bật thống kê Hibernate | Không trực tiếp đếm network trips |
| `hibernate.default_batch_fetch_size` | Batch loading khi đọc | Hoàn toàn khác write batch |

`hibernate.jdbc.batch_versioned_data` cần được hiểu cùng `@Version`: Hibernate dựa vào số row được UPDATE để phát hiện optimistic locking failures. Nếu driver không trả counts chính xác trong batch, cần xem workaround hoặc tắt batching versioned data theo version/dialect. Không mặc định copy một giá trị từ tutorial Hibernate 5 cho mọi Hibernate 6/7.

### 3.5. Cấu hình chỉ *cho phép*, không đảm bảo hiệu quả

Nếu application chỉ INSERT một entity, Hibernate không có lệnh tương thích để gom. Nếu ID generator yêu cầu insert ngay hoặc mapping sinh nhiều SQL templates, batching có thể bị vô hiệu trên những INSERT đó. Bài toán này phải được kiểm tra ở tầng mapping và driver.

## 4. Override batch size theo Session

Hibernate `Session` có API riêng:

~~~java
import org.hibernate.Session;

Session session = entityManager.unwrap(Session.class);
session.setJdbcBatchSize(50);
~~~

`setJdbcBatchSize` là API Hibernate-specific; `EntityManager` JPA chuẩn không khai báo method này.

Ví dụ job import:

~~~java
@Transactional
public void importProducts(List<ProductInput> inputs) {
    Session session = entityManager.unwrap(Session.class);
    session.setJdbcBatchSize(50);

    for (ProductInput input : inputs) {
        entityManager.persist(Product.from(input));
    }

    entityManager.flush();
}
~~~

Trong Spring, cần transaction boundary đúng và không đóng thủ công Session được unwrap từ EntityManager do framework quản lý. Với `SessionFactory.openSession()` được ứng dụng tự mở, lifecycle/transaction lại do ứng dụng chịu trách nhiệm.

Khi override tạm trong Session dùng chung một transaction, phải hiểu override còn hiệu lực cho những operations sau đó. Trong API/version có `getJdbcBatchSize()` và `setJdbcBatchSize(Integer)`, có thể lưu giá trị cũ và khôi phục sau khi flush những thay đổi dự kiến:

~~~java
Session session = entityManager.unwrap(Session.class);
Integer previous = session.getJdbcBatchSize();

try {
    session.setJdbcBatchSize(50);
    // persist/update ...
    entityManager.flush();
} finally {
    session.setJdbcBatchSize(previous);
}
~~~

Các overload/nullable semantics có thể thay đổi theo Hibernate version; cần đối chiếu Javadoc. Chỉ dùng override khi đo thấy một nhóm công việc cần size khác với mặc định.

## 5. Ba giới hạn khác nhau: JDBC batch, flush/clear và transaction

Trong job nhập 50.000 rows, cần phân biệt:

| Loại giới hạn | Ví dụ | Điều kiểm soát |
|---|---:|---|
| **JDBC batch size** | 30 | Số DML executions tương thích gom cho mỗi batch |
| **Flush/clear interval** | 300 entities | Số managed objects giữ trước khi flush/detach |
| **Transaction chunk size** | 3.000 rows/commit | Phạm vi atomicity, locks, undo/WAL, rollback |

Chúng **không cần bằng nhau**. Một transaction có thể flush 10 lần; mỗi flush có thể tạo nhiều JDBC batches. Một batch size lớn không giải quyết memory retention của persistence context.

Ngược lại, cứ flush/clear sau từng entity sẽ phá cơ hội gom thành batch lớn. Cần chọn interval đủ lớn để batch có thể hình thành nhưng không giữ quá nhiều managed entities trong memory.

## 6. Xác nhận driver công bố khả năng hỗ trợ batching

### 6.1. JDBC API chuẩn

~~~java
boolean supported =
    connection.getMetaData().supportsBatchUpdates();
~~~

`DatabaseMetaData.supportsBatchUpdates()` là phép kiểm tra chuẩn để hỏi driver/database có công bố hỗ trợ batch updates hay không.

Nếu trả `true`, mới chứng minh được **driver báo có hỗ trợ JDBC batch API**. Nó không đảm bảo:
- Driver có rewrite INSERT thành multi-values hay không.
- Generated keys và update counts chính xác trong mọi tình huống.
- Hibernate thực sự gom được SQL do mapping/ID generator.
- Hiệu năng tốt hơn khi size tăng.
- Một `executeBatch()` chỉ cần một network round-trip.

### 6.2. Đọc metadata qua Hibernate Session

~~~java
import java.sql.DatabaseMetaData;
import org.hibernate.Session;

Session session = entityManager.unwrap(Session.class);

BatchDriverInfo info = session.doReturningWork(connection -> {
    DatabaseMetaData md = connection.getMetaData();
    return new BatchDriverInfo(
        md.getDriverName(),
        md.getDriverVersion(),
        md.getDatabaseProductName(),
        md.getDatabaseProductVersion(),
        md.supportsBatchUpdates()
    );
});

System.out.println(info);
~~~

Record:

~~~java
public record BatchDriverInfo(
    String driverName,
    String driverVersion,
    String databaseName,
    String databaseVersion,
    boolean supportsBatchUpdates
) {}
~~~

`Session.doReturningWork` lấy connection của Session trong phạm vi callback. **Không đóng, commit hoặc rollback connection mà Hibernate/transaction manager đang quản lý**.

### 6.3. Kiểm tra DataSource trực tiếp

~~~java
public BatchDriverInfo inspect(DataSource dataSource)
        throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        DatabaseMetaData md = connection.getMetaData();

        return new BatchDriverInfo(
            md.getDriverName(),
            md.getDriverVersion(),
            md.getDatabaseProductName(),
            md.getDatabaseProductVersion(),
            md.supportsBatchUpdates()
        );
    }
}
~~~

Connection này được mở riêng, nên try-with-resources là đúng. Nhưng nếu ứng dụng có nhiều DataSources, tenant routing, primary/replica hoặc connection pool khác nhau, hãy kiểm tra **đúng driver/connection được dùng cho ghi**.

### 6.4. Báo cáo môi trường khi benchmark

~~~text
Hibernate ORM:          6.6.x (hoặc version triển khai)
JDBC driver:            tên + exact version
Database:               engine + server version
supportsBatchUpdates:   true/false
hibernate.jdbc.batch_size: 30
hibernate.order_inserts:    true/false
hibernate.order_updates:    true/false
Identifier strategy:    SEQUENCE / IDENTITY / ASSIGNED
Driver rewrite option:  enabled/disabled
Rows/transaction:       ...
Observed executeBatch:  ...
Throughput / p95:       ...
~~~

Tính chính xác của thông tin thực nghiệm quan trọng hơn việc chỉ chụp màn hình property `batch_size=30`.
+
## 7. Kiểm tra `executeBatch()` thật sự chạy: metadata là chưa đủ

Một driver báo `supportsBatchUpdates() == true` vẫn có thể cho hiệu năng không như kỳ vọng, hoặc chỉ hỗ trợ một số kiểu statement/bind parameters. Phép kiểm tra tốt hơn là **thử nghiệm một batch có kiểm soát trên đúng database**.

### 7.1. Chuẩn bị bảng thử nghiệm riêng

Dùng một bảng chỉ dành cho integration test:

~~~sql
CREATE TABLE jdbc_batch_probe (
    id BIGINT PRIMARY KEY,
    payload VARCHAR(100) NOT NULL
);
~~~

Không kiểm thử bằng cách INSERT/DELETE trực tiếp trong bảng nghiệp vụ production. Nếu test chạy rollback trong một transaction, cần đảm bảo DB/driver thực sự tham gia cùng transaction và không dùng DDL tự commit ngoài ý muốn.

### 7.2. Thử addBatch/executeBatch và đọc update counts

~~~java
import java.sql.*;
import java.util.Arrays;

public void probeJdbcBatch(DataSource dataSource) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        boolean originalAutoCommit = connection.getAutoCommit();

        try {
            connection.setAutoCommit(false);

            boolean supports = connection
                .getMetaData()
                .supportsBatchUpdates();

            System.out.println("supportsBatchUpdates=" + supports);

            if (!supports) {
                throw new UnsupportedOperationException(
                    "JDBC driver does not advertise batch update support"
                );
            }

            try (PreparedStatement ps = connection.prepareStatement(
                    """
                    INSERT INTO jdbc_batch_probe(id, payload)
                    VALUES (?, ?)
                    """
                )) {

                for (long id = 101L; id <= 105L; id++) {
                    ps.setLong(1, id);
                    ps.setString(2, "probe-" + id);
                    ps.addBatch();
                }

                int[] counts = ps.executeBatch();
                System.out.println(Arrays.toString(counts));
            }

            // Đây là probe không làm thay đổi DB lâu dài.
            connection.rollback();
        } catch (SQLException | RuntimeException ex) {
            connection.rollback();
            throw ex;
        } finally {
            connection.setAutoCommit(originalAutoCommit);
        }
    }
}
~~~

Đoạn trên dành cho **connection được mở riêng từ DataSource**, không phải connection do Hibernate `Session.doWork` cấp rồi do Hibernate quản lý. Nếu môi trường có connection pooling/transaction manager, không tự đổi autocommit trên một connection đang được framework enlist trong transaction ngoài. Với integration test có `@Transactional`, có thể để transaction manager đảm nhiệm rollback.

Nếu fixture có thể đã chứa ID 101–105, dùng các ID test được đảm bảo riêng hoặc cleanup phù hợp. Việc tái chạy không nên làm test thất bại do xung đột khóa ngoài ý muốn.

### 7.3. Ý nghĩa mảng update counts

`executeBatch()` thành công trả `int[]` theo thứ tự các lệnh đã `addBatch()`. Phần tử có thể là:

- Một số không âm: số hàng bị ảnh hưởng mà driver báo.
- `Statement.SUCCESS_NO_INFO` (giá trị -2): lệnh thành công nhưng driver không cung cấp số hàng chính xác.
- Trong tình huống driver **tiếp tục xử lý sau lỗi** và ném `BatchUpdateException`, mảng counts của exception có thể chứa `Statement.EXECUTE_FAILED` (giá trị -3).

Không được diễn giải `SUCCESS_NO_INFO` là thất bại; nó nghĩa là không có update count chính xác. Không được coi giá trị 0 tự động thành công với lệnh phải ảnh hưởng đúng một hàng; nó có thể cho thấy WHERE predicate không khớp.

Với optimistic locking Hibernate có thể cần **row count chính xác** để phát hiện lỗi cập nhật version. Vì thế dù driver hỗ trợ batch, nếu counts không chính xác thì batching versioned DML có thể cần điều chỉnh theo setting/provider.

### 7.4. Test này vẫn chưa chứng minh Hibernate đang batching

Một JDBC test chứng minh driver chấp nhận `addBatch/executeBatch`. Để chứng minh **Hibernate** đang batch:
1. Kích hoạt `hibernate.jdbc.batch_size`.
2. Chạy một workload ORM có mapping đủ điều kiện.
3. Dùng JDBC-proxy/driver trace/ORM metrics quan sát những lệnh `addBatch` và `executeBatch`.
4. Kiểm tra số SQL templates, kích thước batch và thời gian thực tế.
5. So sánh với `batch_size=0` và giữ những yếu tố khác giống nhau.

Hãy phân biệt kiểm tra **capability** với kiểm tra **actual use**.

## 8. Điều kiện quan trọng nhất với INSERT: cơ chế sinh khóa chính

### 8.1. Vì sao `GenerationType.IDENTITY` có thể làm batching INSERT bị tắt?

Với IDENTITY, database thường quyết định ID sau khi INSERT. Hibernate cần biết identifier để quản lý entity identity và các references/associations. Điều này có thể buộc INSERT diễn ra sớm, làm mất khả năng gom nhiều INSERT.

Hibernate User Guide 6.6 nêu rõ Hibernate **không batch JDBC INSERT cho entity dùng IDENTITY generator** trong đường xử lý được mô tả.

~~~java
@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Product() {}
}
~~~

Dù cấu hình:

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
~~~

các INSERT cho entity dùng IDENTITY như trên vẫn có thể không được gom theo kỳ vọng. **Đừng chỉ tăng batch size khi thấy từng INSERT riêng; kiểm tra ID generator trước.**

### 8.2. `GenerationType.SEQUENCE` thường thuận lợi hơn

Với DB hỗ trợ sequence, Hibernate có thể có identifier trước khi phát INSERT, tạo điều kiện gom nhiều entity inserts:

~~~java
@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "product_seq"
    )
    @SequenceGenerator(
        name = "product_seq",
        sequenceName = "product_id_seq",
        allocationSize = 50
    )
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Product() {}

    public Product(String name) {
        this.name = name;
    }
}
~~~

`allocationSize = 50` là ví dụ về identifier allocation/optimizer strategy, **không phải** JDBC batch size. Nó có thể giảm lượt gọi sequence cần thiết, tùy generator/provider config.

Đối chiếu sequence DB thật và migration/schema; không tự đổi `allocationSize` trên hệ thống đang chạy nếu chưa đánh giá ảnh hưởng tới ID allocation, sequence increments và nhiều application instances.

### 8.3. Assigned ID cũng có thể batch nhưng phải quản lý uniqueness

~~~java
@Entity
public class Product {
    @Id
    private Long id;

    private String name;

    // Constructor/getters ...
}
~~~

Nếu application gán ID hợp lệ trước persist và các INSERT dùng cùng SQL template, Hibernate có thể gom. Nhưng application phải tự bảo đảm ID unique và xử lý concurrency. Chọn assigned IDs chỉ vì benchmark chưa chắc là quyết định thiết kế hợp lý.

### 8.4. `GenerationType.AUTO` không nói rõ đường batching

AUTO phụ thuộc Hibernate version, dialect và database capabilities. Nó có thể chọn sequence, table hoặc cơ chế khác. Không thể kết luận entity chắc chắn batch được chỉ vì annotation là AUTO.

Hãy kiểm tra SQL thực tế, generator đang được Hibernate dùng và Javadoc/dialect.

### 8.5. Bảng tổng hợp

| Chiến lược ID | Hành vi thường gặp | Tác động tới batching INSERT |
|---|---|---|
| `IDENTITY` | ID phải lấy từ kết quả INSERT | Hibernate ORM thường không batch inserts tương ứng |
| `SEQUENCE` | Có thể cấp ID trước INSERT | Thường thuận lợi cho batching |
| Assigned ID | ID do code cung cấp | Có thể batch nếu SQL tương thích |
| `AUTO` | Provider/dialect lựa chọn | Phải xác định generator thực tế |
| UUID/application-generated | Có ID từ Java trước INSERT | Có thể thuận lợi, còn tùy mapping/SQL |

Không chuyển IDENTITY sang SEQUENCE chỉ để tăng throughput khi DB không hỗ trợ sequence hoặc migration không an toàn. Benchmark và ràng buộc kiến trúc quyết định.

## 9. Mô hình INSERT Hibernate: cấu hình + EntityManager + flush/clear

### 9.1. Ví dụ Entity cho batch demo

~~~java
@Entity
@Table(name = "imported_products")
public class ImportedProduct {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE,
                    generator = "import_product_seq")
    @SequenceGenerator(
        name = "import_product_seq",
        sequenceName = "import_product_id_seq",
        allocationSize = 50
    )
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    protected ImportedProduct() {}

    public ImportedProduct(String sku, String name) {
        this.sku = sku;
        this.name = name;
    }
}
~~~

### 9.2. Một transaction, flush và clear theo chunk

~~~java
@Transactional
public void importProducts(List<ProductInput> inputs) {
    final int flushInterval = 250;

    for (int i = 0; i < inputs.size(); i++) {
        ProductInput input = inputs.get(i);

        entityManager.persist(
            new ImportedProduct(input.sku(), input.name())
        );

        if ((i + 1) % flushInterval == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
~~~

Giả định project đã cấu hình batch size 25 hoặc 50. Trong ví dụ:
- **JDBC batch size** có thể là 25.
- **Flush/clear interval** là 250.
- **Transaction size** là toàn bộ `inputs` (vì method `@Transactional` bao trọn).

Hibernate có thể gửi nhiều batches trong mỗi flush. `clear()` giúp giảm số managed objects giữ trong persistence context, không commit transaction. Nếu `inputs` rất lớn, transaction vẫn có thể giữ locks/undo/WAL và connection lâu; cân nhắc chia thành nhiều transaction chunks theo yêu cầu atomicity.

### 9.3. Vì sao không flush/clear sau từng entity?

~~~java
for (ProductInput input : inputs) {
    entityManager.persist(
        new ImportedProduct(input.sku(), input.name())
    );

    entityManager.flush();
    entityManager.clear();
}
~~~

Cách này giữ context nhỏ, nhưng mỗi flush thường chỉ có một entity INSERT để thực thi, làm mất cơ hội gom 25 INSERT vào một JDBC batch. Flush/clear interval phải được chọn đủ lớn để batching có cơ hội hình thành, nhưng không lớn đến mức làm context vượt memory budget.

### 9.4. Vì sao không persist 500.000 entity rồi mới flush?

Persistence context phải giữ các managed objects, identity map, snapshots/actions và có thể collections. Khi quá lớn:
- JVM memory/GC tăng.
- Flush/dirty checking tốn thời gian.
- Connection/transaction giữ quá lâu.
- Nếu lỗi, rollback phải xử lý một lượng công việc lớn.
- Một batch size 50 không tự giải phóng các Java objects đã persist.

Cần cả **batch size** và **flush/clear policy**, không thay thế nhau.

### 9.5. Cẩn trọng khi clear trong unit of work lớn

`entityManager.clear()` detach **tất cả** managed entities trong context, không chỉ ImportedProduct vừa được thêm. Nếu transaction còn entity ở domain khác đang được sửa mà chưa flush, clear có thể làm mất pending changes. Do đó job import nên dùng transaction/context riêng khi thích hợp, hoặc quản lý việc flush/detach có chủ đích.

Khi xây graph parent/child, clear có thể detach parent mà code sau vẫn cần reference managed. Cần lên kế hoạch vòng đời entity và cascades; không áp dụng một đoạn copy-paste cho mọi quan hệ.

## 10. UPDATE và DELETE: batching phụ thuộc SQL template, version và thứ tự

### 10.1. Entity-level UPDATE có thể batch

~~~java
@Transactional
public void increasePrices(List<Long> productIds) {
    List<ImportedProduct> products = entityManager.createQuery(
        "select p from ImportedProduct p where p.id in :ids",
        ImportedProduct.class
    ).setParameter("ids", productIds)
     .getResultList();

    for (ImportedProduct p : products) {
        p.raisePrice(...); // Giả sử entity có domain method tương ứng.
    }

    entityManager.flush();
}
~~~

Đây là minh họa có placeholder cho domain method; khi entity SQL UPDATE có cùng shape và thuộc cùng transaction, Hibernate có thể batch. Với code thật, phải khai báo field price và triển khai domain method phù hợp. Đừng dùng ví dụ này như một class compile độc lập.

### 10.2. ORDER_UPDATES

~~~properties
hibernate.order_updates=true
~~~

Hibernate có thể sắp xếp entity UPDATE actions theo loại entity/identifier. Điều này có thể:
- Tăng số lệnh có cùng SQL nằm cạnh nhau.
- Giảm vài tình huống deadlock khi nhiều transactions cùng cập nhật các khóa nhưng theo thứ tự khác.
- Thêm CPU/memory cost để sắp xếp.

Không bật chỉ vì “có thể giảm deadlock”; benchmark với contention và throughput thực tế.

### 10.3. Versioned entities và update counts

Entity:

~~~java
@Version
private long version;
~~~

Entity-level optimistic update thường có dạng:

~~~sql
UPDATE imported_products
SET name = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Nếu câu SQL cập nhật 0 row do version đã thay đổi, Hibernate cần phát hiện conflict. Khi driver xử lý batch và trả `SUCCESS_NO_INFO` hoặc counts không chính xác, Hibernate có thể khó xác định câu lệnh nào thất bại.

Setting `hibernate.jdbc.batch_versioned_data` trong các phiên bản hỗ trợ quyết định có batch DML của versioned entities hay không. Hibernate ORM 6.6 `BatchSettings` mô tả default thường là true nhưng có thể thay đổi theo dialect. Khi driver counts không đáng tin, cân nhắc cấu hình/version phù hợp và test optimistic-lock conflict trên DB đích; không bỏ kiểm tra optimistic locking để lấy throughput.

### 10.4. @DynamicUpdate có thể làm SQL ít đồng nhất

Nếu entity có `@DynamicUpdate`, Hibernate tạo UPDATE tùy các cột thực sự đổi. Hai Product:
- A chỉ đổi `name`.
- B chỉ đổi `price`.

SQL shapes khác nhau:

~~~sql
UPDATE products SET name = ? WHERE id = ?;
UPDATE products SET price = ? WHERE id = ?;
~~~

Chúng có thể không nằm chung một PreparedStatement batch. `@DynamicUpdate` có lợi trong một số workload để tránh update các cột không đổi, nhưng có thể giảm cơ hội batching. Đánh giá trade-off thay vì mặc định bỏ annotation.

### 10.5. DELETE và cascade

Xóa nhiều entity có cùng SQL DELETE shape có thể batch. Nhưng:
- Quan hệ FK quy định thứ tự parent/child.
- Cascades có thể tạo nhiều SQL templates và batches nhỏ.
- Callbacks, orphanRemoval và version checks ảnh hưởng entity lifecycle.
- Không có setting `order_deletes` tương đương chung để đảm bảo gom mọi cascade deletes như mong muốn.
- DB cascade và entity-level cascade khác semantics.

Nếu mục tiêu chỉ là xóa hàng loạt theo điều kiện, HQL bulk DELETE hoặc SQL set-based có thể phù hợp hơn nhưng **bỏ qua entity lifecycle/cascade semantics**; đây là quyết định riêng, không phải “batch size lớn hơn”.
+
## 11. JDBC driver có thể tối ưu batch theo cách riêng

Hibernate quyết định **khi nào gọi JDBC batching**; driver quyết định **gửi gì xuống database**. Một driver có thể gửi nhiều executions trong một protocol request, rewrite SQL thành multi-values INSERT hoặc giữ nguyên nhiều commands.

Vì thế có hai câu hỏi khác nhau:

1. Hibernate có thực sự gọi `PreparedStatement.addBatch()/executeBatch()` không?
2. Driver/database có biến những lời gọi đó thành thao tác ít round-trip và hiệu quả hơn không?

### 11.1. PostgreSQL JDBC: `reWriteBatchedInserts`

pgJDBC có connection option tên chính xác:

~~~properties
reWriteBatchedInserts=true
~~~

Ví dụ JDBC URL minh họa:

~~~text
jdbc:postgresql://db-host:5432/catalog?reWriteBatchedInserts=true
~~~

Theo tài liệu pgJDBC, option này cho phép rewrite những batched INSERT phù hợp thành multi-values SQL khi driver có thể. Ý tưởng:

~~~sql
-- Các executions dùng cùng SQL shape:
INSERT INTO products(sku, name) VALUES (?, ?);
INSERT INTO products(sku, name) VALUES (?, ?);
INSERT INTO products(sku, name) VALUES (?, ?);

-- Có thể được driver rewrite tương đương:
INSERT INTO products(sku, name)
VALUES (?, ?), (?, ?), (?, ?);
~~~

Đó là **ví dụ logic**, không có nghĩa Hibernate trực tiếp sinh câu multi-values trên mọi phiên bản. Đặc điểm SQL, generated keys, RETURNING clauses, kiểu statement và driver version có thể hạn chế rewrite.

Tài liệu pgJDBC cũng có option `reWriteBatchedInsertsSize` để giới hạn số rows được gộp; đây là **driver-level rewrite cap**, khác hoàn toàn với `hibernate.jdbc.batch_size`. Driver cần tuân thủ giới hạn bind parameters của PostgreSQL/protocol.

**Lưu ý cách viết property:** `reWriteBatchedInserts` có chữ `W` viết hoa giữa tên. Không tự đổi tên thành `rewriteBatchInserts` rồi giả định driver hiểu.

### 11.2. MySQL Connector/J: `rewriteBatchedStatements`

MySQL Connector/J có option:

~~~properties
rewriteBatchedStatements=true
~~~

JDBC URL minh họa:

~~~text
jdbc:mysql://db-host:3306/catalog?rewriteBatchedStatements=true
~~~

Khi phù hợp, Connector/J có thể rewrite các prepared batched INSERT/REPLACE thành multi-values queries. Driver docs lưu ý rewrite có thể ảnh hưởng generated keys/update counts trong những trường hợp đặc biệt, nhất là `INSERT ... ON DUPLICATE KEY UPDATE`.

Không hiểu option này là một “nút bật Hibernate batching”. Cần cả:

1. Hibernate thật sự tạo JDBC batches cho workload.
2. JDBC driver hỗ trợ và option có hiệu lực trên đúng DataSource.
3. SQL statement shape thỏa điều kiện rewrite.
4. Database có năng lực xử lý số rows/packet/parameter phù hợp.

Một prepared statement batch viết bằng JDBC đúng API vẫn có thể chạy khi option rewrite tắt; chỉ có cách driver gửi request/hiệu năng là khác.

### 11.3. SQL Server, Oracle, H2 và driver khác

Không có một property rewrite thống nhất cho mọi JDBC driver. Từng vendor/version có hành vi riêng về batch update, statement caching, array binding, generated keys, server protocol và update counts.

Đối với DB không phải PostgreSQL/MySQL:

- Đọc tài liệu JDBC driver chính thức.
- Chạy `DatabaseMetaData.supportsBatchUpdates()` trên đúng connection.
- Chạy probe `addBatch/executeBatch` với kiểu SQL workload thực tế.
- So sánh driver versions và options.
- Kiểm tra DB query/protocol metrics và execution plan nếu có.
- Chú ý generated keys, optimistic locking và batch partial-failure semantics.

Đừng sao chép `rewriteBatchedStatements=true` cho PostgreSQL hoặc `reWriteBatchedInserts=true` cho Oracle rồi kỳ vọng tác dụng.

### 11.4. Tùy chọn driver không giải quyết được IDENTITY trong Hibernate

Nếu Hibernate phải INSERT ngay để lấy IDENTITY value, driver không có nhiều insert executions đang chờ để rewrite. Bật driver option không thể tự biến những INSERT không được Hibernate batch thành một batch hiệu quả.

Chuỗi kiểm chứng nên là:

~~~text
Hibernate mapping / ID generator đủ điều kiện?
              |
             yes
              v
hibernate.jdbc.batch_size > 0 ?
              |
             yes
              v
Có nhiều SQL executions cùng shape?
              |
             yes
              v
Driver supportsBatchUpdates()?
              |
             yes
              v
Hibernate có gọi executeBatch() thật?
              |
             yes
              v
Driver rewrite/protocol options & DB performance
~~~

## 12. Giới hạn kích thước batch và kích thước payload

### 12.1. Vì sao size càng lớn không nhất thiết càng nhanh?

Giả sử 100.000 INSERT và batch size lần lượt 1, 10, 25, 50, 200, 1.000. Ban đầu tăng batch size có thể giảm overhead; nhưng tới một ngưỡng:
- Driver phải giữ nhiều parameter sets trong memory.
- DB xử lý một batch lớn lâu hơn, làm tăng latency/chờ lock.
- Packet/bind parameter limit có thể bị chạm.
- Generated keys/update count mapping có thể phức tạp.
- Khi một execution thất bại, việc xác định row lỗi khó hơn.
- Một batch quá lớn có thể làm retry/rollback nặng và giảm fairness giữa requests.

**Chọn batch size bằng benchmark**, không có giá trị 1.000 hay 10.000 “tốt nhất” chung cho mọi database.

### 12.2. Batch size và số parameter

Giả sử một INSERT có 12 bind parameters và driver rewrite 400 rows thành một multi-values SQL, phép tính sơ bộ là:

~~~text
12 parameters / row × 400 rows = 4.800 bind parameters
~~~

Một số database/protocol giới hạn số bind parameters mỗi statement. Driver có thể tự chia nhỏ batch, nhưng không nên dựa vào điều đó mà bỏ qua các giới hạn.

Nếu mỗi row chứa CLOB/BLOB hoặc JSON lớn, batch size 50 có thể tạo payload nặng hơn nhiều so với batch size 50 cho ba cột số.

### 12.3. Batch size khác với bulk commit size

Ví dụ:
- Batch size = 50.
- Flush interval = 500.
- Transaction chunk = 5.000.

Một transaction có 10 flush intervals, mỗi flush có thể chứa khoảng 10 batches khi SQL đồng nhất. Dĩ nhiên số thực tế còn phụ thuộc mapping và driver.

Chọn transaction chunk dựa trên:
- Atomicity nghiệp vụ: một import phải all-or-nothing hay có thể commit từng phần?
- Lock duration, WAL/undo size và statement timeout.
- Connection pool availability.
- Retry semantics.
- Kích thước checkpoint và idempotency khi crash.
- Khả năng đối soát số bản ghi đã commit.

Không “giảm batch size” để giải quyết mọi vấn đề transaction dài; đôi khi cần giảm **transaction chunk**, không giảm JDBC batch.

### 12.4. Lập bảng benchmark tối thiểu

| Batch size | Driver rewrite | Flush interval | Transaction chunk | Rows/s | p95 latency | JVM heap/GC | DB CPU |
|---:|---|---:|---:|---:|---:|---|---|
| 0 | off | 250 | 2.500 | đo | đo | đo | đo |
| 10 | off | 250 | 2.500 | đo | đo | đo | đo |
| 25 | off | 250 | 2.500 | đo | đo | đo | đo |
| 50 | off | 250 | 2.500 | đo | đo | đo | đo |
| 25 | on | 250 | 2.500 | đo | đo | đo | đo |
| 50 | on | 250 | 2.500 | đo | đo | đo | đo |

Đây là mẫu thu thập, **không phải số liệu thử nghiệm đã thực hiện**. Nếu một driver không hỗ trợ rewrite, ghi “không áp dụng” thay vì on/off.

### 12.5. Đừng giả định batching cải thiện single-row latency

Batching thường phù hợp throughput của job nhiều hàng. Với một REST endpoint chỉ tạo một entity, batching có thể không giúp và việc chờ gom quá lâu là phản tác dụng. Tối ưu latency endpoint và throughput batch-import có thể cần cấu hình hoặc đường xử lý riêng.

## 13. Làm sao biết Hibernate có thật sự gọi executeBatch?

### 13.1. SQL logging có giới hạn

Bật Hibernate SQL log có thể cho thấy nhiều dòng INSERT cùng mẫu:

~~~sql
insert into products (name, sku, id) values (?, ?, ?)
insert into products (name, sku, id) values (?, ?, ?)
insert into products (name, sku, id) values (?, ?, ?)
~~~

**Nhìn thấy nhiều dòng INSERT trong log không đủ kết luận batching đã tắt.** Hibernate vẫn thực thi nhiều logical SQL statements, còn driver có thể nhận chúng qua `addBatch` thay vì `executeUpdate` từng lần.

Tương tự, nhìn thấy một dòng SQL template không chứng minh có đúng một network request. Các mức quan sát khác nhau cần công cụ tương ứng.

### 13.2. Hibernate statistics và session metrics

Có thể bật:

~~~properties
hibernate.generate_statistics=true
~~~

Hibernate cung cấp Statistics API và các log theo session/events tùy version. Có thể quan sát số entity inserts/updates/deletes, prepared statements, flushes và trong một số session metrics có thông tin số JDBC batches/tổng thời gian batching.

Tuy nhiên:
- `Statistics.getEntityInsertCount()` đếm entity inserts, không phải số network round-trips.
- `getPrepareStatementCount()` không nhất thiết tương đương số batch executions.
- Tên/đơn vị các metrics và log category thay đổi giữa Hibernate versions.
- Logging/statistics có overhead, nên dùng có mục tiêu trong test/benchmark.

Ví dụ code đọc một vài counters của Hibernate:

~~~java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory factory = entityManagerFactory.unwrap(
    SessionFactory.class
);

Statistics stats = factory.getStatistics();

System.out.println("Entity inserts = " + stats.getEntityInsertCount());
System.out.println("Prepared statements = " +
                   stats.getPrepareStatementCount());
~~~

Cần đọc counters sau đúng khoảng benchmark, tránh bị traffic khác hoặc những transactions trước đó làm sai thống kê. Một bộ đếm thấp không tự xác nhận số `executeBatch` đã được gửi.

### 13.3. JDBC proxy hoặc driver-level tracing

Để xác nhận trực tiếp phương thức JDBC:
- Dùng một `DataSource` proxy/instrumentation phù hợp, có thể log/đếm `PreparedStatement.addBatch()`, `executeBatch()` và size.
- Hoặc dùng JDBC driver trace chính thức nếu driver hỗ trợ.
- Hoặc dùng profiler/apm instrument JDBC ở tầng phương thức.
- Kết hợp DB monitoring để xem số requests và thời gian thực thi.

Ví dụ output quan sát **minh họa**:

~~~text
PreparedStatement:
  INSERT INTO imported_products (name, sku, id) VALUES (?, ?, ?)

addBatch calls:     25
executeBatch calls: 1
batch size observed:25
~~~

Nếu thực tế chỉ có 1 `addBatch()` cho mỗi `executeBatch()`, hãy tìm nguyên nhân ở ID generation, SQL shape, flush interval hoặc action ordering.

Đừng bật full SQL/bind-value trace trong production nếu có dữ liệu bí mật/PII; log có thể chứa SKU, email, token hoặc dữ liệu nghiệp vụ.

### 13.4. Query metrics phía database

Khi bật driver rewrite, một DB monitor có thể nhìn thấy statement multi-values hoặc một cách đóng gói khác với Hibernate SQL logger. Kết hợp:
1. Hibernate action counts.
2. JDBC `executeBatch` counts.
3. Driver rewrite/protocol info.
4. DB CPU/IO/locks/statement duration.
5. Thời gian end-to-end của job.

Mỗi tầng trả lời một câu hỏi khác nhau.

### 13.5. Kiểm thử qua proxy không thay thế DB integration test

Một proxy ghi nhận `executeBatch()` chứng minh ORM đã dùng JDBC batching, nhưng không chứng minh database commit đúng số rows, row counts phù hợp `@Version` hoặc driver rewrite không phá generated keys. Phải xác nhận kết quả và transaction behavior trên DB thật.

## 14. Kế hoạch benchmark có kiểm soát

Để quyết định cấu hình production, tạo thử nghiệm trên cùng DB schema và dataset đại diện:

### 14.1. Biến độc lập

Thử thay **một thông số mỗi lần**:
- `hibernate.jdbc.batch_size`: 0, 10, 25, 50...
- `hibernate.order_inserts`: false/true.
- `hibernate.order_updates`: false/true.
- Driver rewrite option: off/on nếu có.
- Identifier strategy: SEQUENCE/IDENTITY chỉ khi có ý nghĩa thiết kế và schema thực tế hỗ trợ.
- Flush interval và transaction chunk, nhưng giữ cố định khi đang khảo sát riêng batch size.

### 14.2. Những gì phải giữ tương đương

- Số bản ghi và số cột.
- Kích thước payload.
- Loại SQL (INSERT hay UPDATE; có/không `@Version`).
- Indexes, triggers, FK constraints.
- Cache, Hibernate statistics/logging settings.
- Connection pool size và mức concurrent jobs.
- Warm-up/JVM/driver connection conditions.
- Database server load/latency.
- Transaction isolation và commit frequency.

Nếu một bài test bật thêm driver rewrite và đồng thời tăng transaction size, không thể quy lợi ích chỉ cho batch_size.

### 14.3. Metrics nên thu

| Metric | Ý nghĩa |
|---|---|
| Rows committed / second | Throughput thật của job |
| End-to-end total duration | Thời gian toàn bộ import |
| `executeBatch()` calls | Số batch driver nhận |
| Average/percentile observed batch size | Có gom đủ nhiều SQL không |
| SQL errors/retries | Độ tin cậy |
| DB CPU, IO, locks/WAL | Tác động phía DB |
| Heap/GC và entity count | Tác động ở Java |
| Connection hold time | Ảnh hưởng connection pool |
| p95/p99 nếu phục vụ request online | Tail latency |
| Optimistic-lock conflicts | Tính đúng đắn của versioned UPDATE |

### 14.4. Kiểm tra cả kết quả nghiệp vụ

Sau benchmark, không chỉ đo thời gian: phải kiểm tra số rows đã commit, unique constraints, generated IDs, version increments, quan hệ FK và dữ liệu đúng. Một cấu hình rất nhanh nhưng bỏ sót rows, trả counts sai hoặc làm mất optimistic-lock conflict không phải cấu hình tốt.

### 14.5. Kết luận benchmark phải có ngữ cảnh

Ví dụ báo cáo đúng cách:

> Với Hibernate X, driver Y, PostgreSQL Z và bài test INSERT 100.000 sản phẩm không có LOB, cấu hình batch size 25 đạt throughput cao hơn baseline trong điều kiện đo A/B.

Không chuyển kết luận này thành “batch size 25 luôn tối ưu với mọi database và mọi workload”.
+
## 15. Lỗi trong JDBC batch và ý nghĩa của BatchUpdateException

Một batch có thể chứa nhiều parameter sets. Nếu một row vi phạm unique constraint, foreign key, NOT NULL hoặc dữ liệu không hợp lệ, vấn đề không chỉ là “SQL thất bại”: ứng dụng còn phải hiểu **transaction state, update counts và retry policy**.

### 15.1. Khi một execution thất bại

JDBC có `java.sql.BatchUpdateException`, subclass của `SQLException`. Trong exception có thể có:
- SQLState và vendor error code.
- Thông báo lỗi DB.
- `getUpdateCounts()` hoặc `getLargeUpdateCounts()`.
- Nested SQL exceptions qua `getNextException()`.

Driver có thể dừng ở phần tử thất bại hoặc tiếp tục xử lý các phần tử còn lại trong batch, theo contract/driver behavior. Vì vậy update-count array khi có exception **không luôn có cùng độ dài hoặc cùng hình dạng** giữa mọi drivers.

### 15.2. Xử lý exception trong JDBC thuần

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "insert into jdbc_batch_probe(id, payload) values (?, ?)"
    )) {

    for (ProbeRow row : rows) {
        ps.setLong(1, row.id());
        ps.setString(2, row.payload());
        ps.addBatch();
    }

    ps.executeBatch();

} catch (BatchUpdateException ex) {
    int[] counts = ex.getUpdateCounts();
    System.err.println("Batch failed, counts length=" + counts.length);
    System.err.println("SQLState=" + ex.getSQLState());

    SQLException nested = ex.getNextException();
    while (nested != null) {
        System.err.println("DB error: " + nested.getMessage());
        nested = nested.getNextException();
    }

    throw ex; // Transaction owner sẽ rollback.
}
~~~

Trong ứng dụng thật không nên đưa toàn bộ SQL bind values có dữ liệu nhạy cảm vào log. Giữ SQLState/vendor code và correlation ID để chẩn đoán. Đừng catch exception rồi tiếp tục commit như thể batch thành công.

### 15.3. Tại sao phải rollback cả transaction sau lỗi?

Một số DB như PostgreSQL có thể đánh dấu transaction hiện tại là aborted sau SQL error; các lệnh tiếp theo sẽ lỗi cho đến khi rollback. Những DB/driver khác có chi tiết khác, nhưng nguyên tắc an toàn là:

- Đặt transaction boundary rõ.
- Khi batch flush/executeUpdate thất bại, **rollback** transaction đó.
- Không tiếp tục dùng Hibernate `Session` đã lỗi như thể state nhất quán.
- Ghi nhận chunk nào thành công/đã commit.
- Retry trên **transaction/session mới** khi lỗi được phân loại là có thể retry.

Nếu batch có 50 elements và phần tử thứ 23 lỗi, không tự suy luận 22 elements trước đó đã **commit**. Có thể chúng chỉ đã được thực thi nhưng transaction còn chờ commit; rollback có thể hủy toàn bộ.

### 15.4. Retry cần idempotency

Nếu job nhận dữ liệu từ queue/file:
- Có business key/unique key rõ, ví dụ `external_id` hoặc `sku`.
- Ghi checkpoint sau transaction commit, không sau `flush()`.
- Tránh retry vô hạn với lỗi ràng buộc dữ liệu không thể tự sửa.
- Deadlock/serialization failure có thể retry với giới hạn/backoff.
- Nếu dùng upsert, kiểm tra semantics và update counts của driver/DB.
- Nếu commit result không chắc chắn do timeout/đứt connection, phải đối soát bằng idempotency key thay vì chèn trùng.

Một batch lớn có thể làm phạm vi retry nặng hơn; đây là yếu tố cần cân nhắc cùng throughput.

### 15.5. Xác định row lỗi trong batch

`BatchUpdateException.getUpdateCounts()` có thể giúp xác định các executions đã thành công/thất bại nhưng không phải mọi driver đều trả index chính xác khi rewrite thành multi-values. Thậm chí driver có thể báo `SUCCESS_NO_INFO` cho nhiều phần tử.

Nếu cần chẩn đoán từng record:
- Gắn input index/business ID vào logs ở tầng application, không log dữ liệu bí mật.
- Khi một chunk lỗi, rollback và thử chia đôi chunk/nhóm nhỏ trong môi trường phù hợp nếu chi phí cho phép.
- Có thể dùng staging table với validation SQL để cô lập lỗi.
- Không cố commit “những row có vẻ thành công” nếu transaction đã ở trạng thái không hợp lệ.

### 15.6. Lỗi optimistic locking trong batch

Khi UPDATE các managed entities có `@Version`, nếu một row không còn phiên bản mong đợi, Hibernate có thể ném exception trong flush/executeBatch/commit phase tùy timing.

Đừng tắt optimistic locking hoặc chấp nhận unknown counts để đạt hiệu năng mà không đánh giá rủi ro lost update. Thử một integration test với update tranh chấp trên chính JDBC driver/version được triển khai.

## 16. Một job thực tế: chọn batch size, flush interval và transaction chunk độc lập

Giả sử cần nạp 100.000 products. Mục tiêu:
- Một lỗi trên nhóm 2.000 bản ghi không hủy tất cả những nhóm đã commit.
- Persistence context không giữ quá 200 entities một lần.
- JDBC batch size thử nghiệm là 25.
- Job có checkpoint và idempotency key để retry được.

### 16.1. Cấu hình

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=25
spring.jpa.properties.hibernate.order_inserts=true
~~~

### 16.2. Chia transaction theo chunk bằng service riêng

Ví dụ định hướng:

~~~java
@Service
public class ProductImportJob {

    private final ProductImportChunkService chunkService;

    public ProductImportJob(ProductImportChunkService chunkService) {
        this.chunkService = chunkService;
    }

    public void importAll(List<ProductInput> all) {
        final int transactionChunkSize = 2_000;

        for (int start = 0; start < all.size();
             start += transactionChunkSize) {

            int end = Math.min(
                start + transactionChunkSize, all.size()
            );

            List<ProductInput> chunk = all.subList(start, end);

            chunkService.persistChunk(chunk);

            // Cập nhật checkpoint chỉ sau khi transaction
            // persistChunk đã commit thành công.
        }
    }
}
~~~

Service chunk:

~~~java
@Service
public class ProductImportChunkService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void persistChunk(List<ProductInput> chunk) {
        final int flushInterval = 200;

        for (int i = 0; i < chunk.size(); i++) {
            ProductInput input = chunk.get(i);

            em.persist(new ImportedProduct(
                input.sku(), input.name()
            ));

            if ((i + 1) % flushInterval == 0) {
                em.flush();
                em.clear();
            }
        }

        em.flush();
        em.clear();
    }
}
~~~

Điểm mấu chốt:

- `ProductImportJob` và `ProductImportChunkService` là hai Spring beans khác nhau nên lời gọi qua proxy có thể kích hoạt transaction interceptor.
- Trong ví dụ này, job outer **không** có `@Transactional` bao trùm mọi chunk; nếu có, `REQUIRED` ở inner method sẽ tham gia transaction ngoài và không còn commit mỗi chunk.
- Nếu chương trình chạy trong một transaction outer có sẵn, dùng propagation/thiết kế khác phù hợp (ví dụ `REQUIRES_NEW` có đánh giá kỹ) để đảm bảo transaction chunks độc lập.
- Dữ liệu `inputs` đang giữ trong memory vẫn chiếm heap riêng; flush/clear chỉ giải phóng managed ORM state, không giải phóng toàn bộ list đầu vào.
- Checkpoint phải được ghi theo cách an toàn nếu crash xảy ra giữa DB commit và lưu checkpoint. Dùng idempotency key để tránh nhập trùng khi chạy lại.
- Với entity graph có cascades, clear mỗi 200 có thể detach objects mà code còn cần; thiết kế theo aggregate boundaries.

Đây là kiến trúc minh họa chứ không phải lời khuyên bắt buộc chia mọi import thành 2.000 rows/transaction. Nếu yêu cầu toàn bộ file atomic, cần transaction toàn bộ hoặc thiết kế staging/activation.

### 16.3. Bảng cấu hình mẫu

| Setting | Giá trị ban đầu | Cần đo/đánh giá |
|---|---:|---|
| JDBC batch size | 25 | Gom được bao nhiêu executions, throughput |
| Flush/clear interval | 200 | JVM memory, dirty checking, batch fullness |
| Transaction chunk | 2.000 | Locks, WAL/undo, retry, atomicity |
| `order_inserts` | true | Chi phí sort vs batches thực |
| `order_updates` | Theo workload | Deadlock/throughput khi UPDATE |
| Driver rewrite | Theo driver, bật thử | Generated keys và DB protocol |
| Connection pool | Theo concurrency | Connection wait và DB capacity |
| Entity generator | SEQUENCE khi thiết kế phù hợp | Khả năng gom INSERT, sequence allocation |

## 17. Các tình huống không đạt hiệu quả dù batch size đã bật

### 17.1. Hibernate không phát đủ executions cùng loại

Ví dụ chỉ lưu 8 sản phẩm trong một transaction, batch size 50. Có thể chỉ có một batch 8 elements; không phải lỗi vì “không đủ 50”.

Nếu mỗi request chỉ lưu một entity, lợi ích batching sẽ nhỏ hơn job import lớn.

### 17.2. IDENTITY generator

Dù driver supportsBatchUpdates=true, Hibernate ORM không gom INSERT của entity IDENTITY theo đường xử lý thông thường, vì cần identifier sau INSERT. Kiểm tra annotation/SQL thực tế.

### 17.3. Có quá nhiều SQL templates

Entity inheritance mappings, audit rows, secondary tables, cascade association tables, dynamic INSERT/UPDATE hoặc các entity types xen kẽ làm batches bị chia nhỏ.

`hibernate.order_inserts`/`order_updates` giúp trong một số trường hợp nhưng không biến mọi SQL thành cùng template.

### 17.4. Flush quá thường xuyên

Nếu cứ `persist → flush → clear` mỗi row, Hibernate phải thực thi SQL khi batch mới có 1 entry. Chọn flush interval đủ lớn so với batch size.

### 17.5. Driver metadata đúng nhưng driver không rewrite

`supportsBatchUpdates()` chỉ khẳng định JDBC batch capability. Để đạt multi-values INSERT trên PostgreSQL/MySQL, cần đúng driver option/version/SQL shape; không có rewrite vẫn có thể batch ở protocol level. So sánh execution metrics thay vì dựa vào tên option.

### 17.6. LOB, generated keys, triggers, upsert và vendor-specific SQL

Một số loại SQL cần generated keys/RETURNING, BLOB streaming, ON CONFLICT/ON DUPLICATE KEY hoặc stored procedures có thể làm driver giới hạn batching/rewrite hay thay đổi update-count semantics. Đọc docs vendor và chạy probe trên query thật.

### 17.7. Batch lớn nhưng database đã bão hòa

Khi DB bị CPU/IO/locks bottleneck, tăng batch size có thể không cải thiện, thậm chí tăng tail latency. Dùng metrics phía server; không “đổ lỗi Hibernate” nếu database capacity là giới hạn chính.

### 17.8. Transaction quá dài

Dù batch hiệu quả, một transaction giữ connection/locks/undo lâu vẫn có thể làm hệ thống chậm. Điều chỉnh transaction chunk riêng với JDBC batch size.

### 17.9. SQL logs bị diễn giải sai

Nhiều dòng INSERT trong Hibernate SQL log **không chứng minh** driver không batch. Cần JDBC-level instrumentation hoặc metrics phù hợp để xác nhận số `executeBatch`.

## 18. Troubleshooting table

| Triệu chứng | Nguyên nhân thường gặp | Bước kiểm tra |
|---|---|---|
| Đã set `batch_size=50` nhưng vẫn từng INSERT | IDENTITY generator | Kiểm tra `@GeneratedValue`, dialect |
| Chỉ có batch size 1 | Flush mỗi entity, SQL shape đổi | Xem flush interval và JDBC instrumentation |
| `supportsBatchUpdates() = false` | Driver/DB không công bố hỗ trợ | Kiểm tra driver version, tính năng DB |
| `supportsBatchUpdates() = true` nhưng chậm | Driver rewrite off hoặc DB bottleneck | Benchmark và EXPLAIN/DB metrics |
| PgJDBC không rewrite INSERT | Sai option, statement không đủ điều kiện | `reWriteBatchedInserts`, generated keys, driver version |
| MySQL không rewrite INSERT | Sai option hoặc statement shape | `rewriteBatchedStatements`, driver docs |
| Batch log nhiều SQL giống nhau | SQL log ghi logical executions | Dùng proxy đo `executeBatch` |
| INSERT không batch dù dùng SEQUENCE | Cascade/SQL khác nhau, thiếu config | Entity SQL shape/order/statistics |
| Batching UPDATE ít hiệu quả | `@DynamicUpdate`, versioned DML, ordering | So sánh SQL templates và counts |
| Optimistic-locking lỗi xuất hiện tại flush | Batched UPDATE version mismatch | Kiểm tra concurrent writers, transaction |
| Batching versioned UPDATE có counts không chính xác | Driver trả `SUCCESS_NO_INFO`/sai counts | Test driver/version, cấu hình phù hợp |
| Import bị OutOfMemory | L1 context giữ quá nhiều entities | Flush/clear theo chunk |
| Import giữ connection quá lâu | Transaction quá lớn | Giảm transaction chunk |
| Mất pending modifications sau clear | Clear trước flush | Flush trước clear khi cần giữ |
| Batch quá lớn báo packet/parameter error | DB/driver limits | Giảm size, xem số bind params/LOB |
| Duplicate key lỗi ở giữa batch | Input có duplicate, không idempotent | Unique validation, rollback chunk, replay-safe |
| Partial counts gây khó xác định row lỗi | Driver continue/stop/rewrite behavior | `BatchUpdateException`, isolate chunk |
| Upsert counts không khớp số rows | Vendor-specific DML/rewrite semantics | Đọc driver docs, kiểm tra DB |
| JDBC probe thành công nhưng Hibernate không batch | ORM mapping không đủ điều kiện | Xem ID generator, flush, SQL shape |
| Hibernate stats cho INSERT count lớn | Entity action count không phải batch count | Đếm JDBC executeBatch riêng |
| Tăng size 25 lên 500 mà throughput giảm | DB/driver/heap/retry overhead | Benchmark theo throughput/latency |
| Cache/trigger làm kết quả không đúng | External write, post-insert generated data | Thiết kế refresh/invalidation phù hợp |
| SQL batch lỗi mà code vẫn commit | Exception handling sai | Rollback transaction, không reuse session lỗi |

## 19. Bài tập tự luyện

### Bài 1 — Batch size đang tắt

~~~properties
hibernate.jdbc.batch_size=0
~~~

**Câu hỏi:** cơ chế JDBC statement batching mặc định của Hibernate có được bật không?

**Đáp án:** Không. Giá trị 0 tắt cơ chế này.

### Bài 2 — Có hỗ trợ hay không?

~~~java
boolean supported =
    connection.getMetaData().supportsBatchUpdates();
~~~

**Câu hỏi:** trả `true` có chứng minh Hibernate đã gọi `executeBatch` chưa?

**Đáp án:** Chưa. Chỉ mới là driver công bố hỗ trợ. Cần test Hibernate workload và instrumentation.

### Bài 3 — 12 lệnh, batch size 5

**Câu hỏi:** với 12 executions tương thích, có thể có bao nhiêu batches khi mọi thứ được flush?

**Đáp án:** Theo mô hình đơn giản: 5 + 5 + 2 thành ba batches; thực tế ORM/driver có thể chia khác.

### Bài 4 — 100.000 INSERT nhưng không batch

Entity dùng `@GeneratedValue(strategy = GenerationType.IDENTITY)`.

**Câu hỏi:** tăng `batch_size` từ 20 lên 200 có chắc giải quyết không?

**Đáp án:** Không. IDENTITY có thể buộc INSERT thực thi ngay để lấy key, khiến Hibernate không gom INSERT theo đường thông thường.

### Bài 5 — SEQUENCE và allocationSize

Entity dùng `@SequenceGenerator(allocationSize = 50)`; Hibernate batch size = 25.

**Câu hỏi:** hai giá trị 50 và 25 có cùng ý nghĩa không?

**Đáp án:** Không. 50 liên quan vùng phân bổ sequence identifiers; 25 là JDBC statement batch size.

### Bài 6 — Flush/clear mỗi entity

Một job persist từng row rồi gọi `flush(); clear();` ngay.

**Câu hỏi:** vì sao batch thực tế nhỏ?

**Đáp án:** Có ít executions chờ tại mỗi flush. Cần interval lớn hơn khi memory/transaction cho phép.

### Bài 7 — Ba giới hạn khác nhau

Batch size 25, flush interval 250, transaction chunk 2.500.

**Câu hỏi:** một transaction tương đương một JDBC batch không?

**Đáp án:** Không. Một transaction có thể bao gồm nhiều flushes và nhiều JDBC batches.

### Bài 8 — Sai property driver

Cấu hình PostgreSQL URL với `rewriteBatchedStatements=true`.

**Câu hỏi:** có chắc pgJDBC hiểu option này không?

**Đáp án:** Không. pgJDBC dùng `reWriteBatchedInserts` cho khả năng rewrite được mô tả; `rewriteBatchedStatements` là option của MySQL Connector/J.

### Bài 9 — Logs nhiều INSERT

Hibernate SQL log hiển thị 30 dòng INSERT cùng mẫu.

**Câu hỏi:** có chắc mỗi dòng là một network round-trip riêng không?

**Đáp án:** Không. Cần JDBC driver instrumentation/metrics.

### Bài 10 — Driver counts

`executeBatch()` trả `[-2, -2, -2]`.

**Câu hỏi:** đây có phải ba lỗi không?

**Đáp án:** Không. `-2` biểu diễn `Statement.SUCCESS_NO_INFO`; driver báo thành công nhưng không biết row count chính xác.

### Bài 11 — Optimistic locking

Driver trả update counts không chính xác khi batching UPDATE có `@Version`.

**Câu hỏi:** việc này có thể ảnh hưởng điều gì?

**Định hướng:** Hibernate có thể không kiểm tra đúng row-level version conflicts. Kiểm thử và điều chỉnh batching versioned DML theo Hibernate/dialect.

### Bài 12 — Concurrent requests

Bật `hibernate.order_updates=true`.

**Câu hỏi:** có bảo đảm hết deadlock không?

**Đáp án:** Không. Ordering có thể giảm một số deadlock patterns nhưng không thay transaction/locking design.

### Bài 13 — Một batch lỗi giữa chừng

Driver ném `BatchUpdateException` sau câu lệnh thứ 23.

**Câu hỏi:** có được tiếp tục commit cả chunk không?

**Đáp án:** Không nên. Rollback transaction, xác định lỗi và retry theo idempotent policy.

### Bài 14 — Batch lớn

Một INSERT chứa 50 trường và driver rewrite 1.500 rows thành một SQL.

**Câu hỏi:** cần quan sát gì?

**Gợi ý:** 75.000 bind parameters nếu rewrite thành một statement; có thể vượt giới hạn driver/DB. Kiểm tra split/cap và giảm batch size.

### Bài 15 — Benchmark fair

So sánh batch size 0 với 50, nhưng ở lần 50 bật thêm rewrite option và tăng transaction chunk.

**Câu hỏi:** có thể kết luận lợi ích chỉ nhờ batch size không?

**Đáp án:** Không. Phải cố định các biến khác hoặc chạy nhiều phép so sánh tách biệt.

### Bài 16 — Batching với REST API

Một endpoint chỉ tạo một row.

**Câu hỏi:** bật batch size 500 có chắc làm endpoint nhanh hơn không?

**Đáp án:** Không. Không có đủ operations tương thích để gom.

### Bài 17 — Batch và bulk HQL

Cần cập nhật 2 triệu rows cùng điều kiện mà không cần gọi entity lifecycle.

**Câu hỏi:** nhất thiết phải load 2 triệu entity để batch UPDATE không?

**Đáp án:** Không. Xem xét HQL/SQL bulk set-based DML, chấp nhận semantics khác về persistence context/cascade/version.

### Bài 18 — Driver metadata từ replica

Ứng dụng kiểm tra `supportsBatchUpdates` trên read replica nhưng import ghi vào primary dùng driver/config khác.

**Câu hỏi:** kết luận có đáng tin không?

**Đáp án:** Không đầy đủ. Kiểm tra đúng DataSource/driver/DB endpoint thực thi job.

## 20. Tổng kết: cấu hình đúng và xác nhận bằng bằng chứng

Một quy trình thực tế:

1. Xác định JDBC driver và database version thật, kiểm tra `supportsBatchUpdates()`.
2. Bật `hibernate.jdbc.batch_size` với giá trị vừa phải, ví dụ 25.
3. Kiểm tra entity generator: đặc biệt tránh giả định IDENTITY INSERT được Hibernate batch.
4. Cân nhắc `hibernate.order_inserts`/`hibernate.order_updates` khi workload có SQL xen kẽ.
5. Chọn flush/clear interval và transaction chunk **riêng** batch size.
6. Nếu có driver-specific rewrite option, bật có mục đích và kiểm tra generated keys/update counts.
7. Quan sát trực tiếp `addBatch/executeBatch` bằng JDBC instrumentation; đừng chỉ đếm dòng Hibernate SQL log.
8. Chạy integration test dữ liệu thực và kiểm tra constraint, optimistic locking, commit/rollback.
9. Đo throughput, tail latency, memory và DB capacity ở nhiều batch sizes.
10. Giữ cấu hình tối ưu cho **workload cụ thể**, không suy ra một con số tốt nhất cho mọi dự án.

Có thể nhớ ba lớp quyết định:

~~~text
Hibernate ORM
  - batch_size + SQL shape + identifier strategy + ordering + flush
            |
            v
JDBC driver
  - supportsBatchUpdates + addBatch/executeBatch
  - rewrite options + generated keys + update counts
            |
            v
Database
  - bind/packet limits + locks + indexes + constraints + WAL/undo
  - throughput + transaction isolation + execution plan
~~~

**Thông điệp chính:** Cấu hình `hibernate.jdbc.batch_size=30` mới chỉ **cho phép** Hibernate gom những DML tương thích. Muốn khẳng định batching hoạt động và đáng dùng, phải **xác nhận driver hỗ trợ, chứng kiến `executeBatch()` thực tế và benchmark trên đúng database**.

### Tài liệu chính thức

- [Hibernate ORM 6.6 User Guide — Batching](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#batch) — JDBC batching, session batching, identifier strategies, flush/clear.
- [Hibernate ORM 6.6 BatchSettings Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/cfg/BatchSettings.html) — setting names và defaults.
- [Hibernate ORM 6.6 Introduction — Statement Batching](https://docs.hibernate.org/orm/6.6/introduction/html_single/) — cấu hình statement batching.
- [Hibernate ORM 6.6 Session Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/Session.html) — `setJdbcBatchSize` và vòng đời Session.
- [Oracle Java SE 21 DatabaseMetaData](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/DatabaseMetaData.html) — `supportsBatchUpdates()`.
- [Oracle Java SE 21 Statement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html) — `addBatch()`, `executeBatch()`, update counts.
- [Oracle Java SE 21 BatchUpdateException](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/BatchUpdateException.html) — partial failures, update counts.
- [pgJDBC Configuration](https://jdbc.postgresql.org/documentation/use/) — `reWriteBatchedInserts` và `reWriteBatchedInsertsSize`.
- [MySQL Connector/J Performance Extensions](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-performance-extensions.html) — `rewriteBatchedStatements`.
- [Spring Data JPA Documentation](https://docs.spring.io/spring-data/jpa/reference/) — repositories và transaction integration.

> Các ví dụ về kích thước 25/50/200/2.000 là điểm khởi đầu minh họa, không phải kết quả benchmark. Khả năng batching và hiệu quả đo được phụ thuộc Hibernate version, JDBC driver/version, database dialect, SQL shape, identifier generator, indexes, payload và transaction/concurrency của ứng dụng.
