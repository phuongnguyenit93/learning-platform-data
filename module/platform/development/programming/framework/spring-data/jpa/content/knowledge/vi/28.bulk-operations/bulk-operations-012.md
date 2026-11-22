# Lựa chọn JDBC hoặc công cụ chuyên dụng khi JPA không phù hợp

Spring Data JPA giúp ánh xạ bảng thành entity, quản lý PersistenceContext, dirty checking, quan hệ và transaction theo mô hình object. Tuy nhiên, không phải mọi thao tác dữ liệu đều phù hợp với ORM. Các truy vấn báo cáo nhiều phép tổng hợp, SQL phụ thuộc database, bulk update/delete rất lớn, import/export theo lô hoặc thao tác cần kiểm soát chính xác từng câu SQL có thể phù hợp hơn với JDBC hoặc một công cụ chuyên dụng.

Các lựa chọn phổ biến:

- **JPA/JPQL**: phù hợp khi làm việc với entity, association, lifecycle và domain model.
- **Native SQL qua JPA**: giữ EntityManager/transaction của JPA nhưng cho phép viết SQL trực tiếp.
- **Spring JDBC** (`JdbcTemplate`, `NamedParameterJdbcTemplate`, `JdbcClient`): phù hợp khi muốn kiểm soát SQL, bind parameter và mapping kết quả rõ ràng.
- **jOOQ**: phù hợp khi cần SQL DSL có kiểu, hỗ trợ sâu các tính năng database và code generation.
- **MyBatis**: phù hợp khi muốn quản lý SQL tường minh cùng mapper ánh xạ kết quả.
- **Spring Batch**: phù hợp khi bài toán là xử lý dữ liệu khối lượng lớn theo job, chunk, checkpoint, retry và restart.

Chọn công cụ theo bản chất công việc, không theo thói quen. Một ứng dụng có thể dùng JPA cho CRUD nghiệp vụ và JDBC cho báo cáo/batch trong cùng service layer. Điều quan trọng là kiểm soát transaction, PersistenceContext và ranh giới giữa các cách truy cập dữ liệu.

## 1. Khi nào JPA không còn là lựa chọn tốt nhất?

JPA phù hợp khi ứng dụng thao tác với entity và quan hệ theo mô hình domain. Nhưng ORM có chi phí chuyển đổi giữa object graph và SQL, cũng như các quy tắc về dirty checking, flush, persistence context và fetch plan.

Các dấu hiệu nên cân nhắc JDBC hoặc công cụ khác:

1. Query có nhiều CTE, window function, vendor-specific operator hoặc cú pháp SQL đặc thù.
2. Báo cáo cần GROUP BY, pivot, nhiều aggregate, UNION hoặc projection phức tạp.
3. Cần bulk update/delete rất lớn và không cần lifecycle callback của từng entity.
4. Import hàng trăm nghìn hoặc hàng triệu dòng với throughput cao.
5. Cần batch insert/update với kiểm soát chính xác statement, parameter và generated key.
6. Dữ liệu trả về chỉ là read model phẳng, không cần entity managed.
7. Query cần tối ưu theo execution plan cụ thể và SQL sinh từ ORM khó kiểm soát.
8. Làm việc với stored procedure, view, temporary table, database feature riêng.
9. Cần streaming/cursor đọc dữ liệu với memory ổn định.
10. Mapping entity/association làm phát sinh N+1 hoặc tải object graph dư thừa.

Một query JPQL phức tạp chưa chắc cần bỏ JPA. Có thể dùng native query qua EntityManager hoặc Spring Data repository trước. Chuyển sang JDBC khi lợi ích về SQL control, mapping, batch hoặc streaming đủ rõ và có thể đo được.

## 2. Phân biệt native query của JPA với JDBC

Native SQL không đồng nghĩa với JDBC. JPA cũng cho phép chạy SQL thuần:

```java
List<Object[]> rows = entityManager
    .createNativeQuery("""
        select id, name, price
        from product
        where active = ?
        order by created_at desc
        """)
    .setParameter(1, true)
    .getResultList();
```

Đây vẫn là native query chạy qua EntityManager. JPA provider quản lý query execution trong PersistenceContext/transaction hiện tại và trả kết quả theo mapping JPA.

So sánh:

| Tiêu chí | Native SQL qua JPA | Spring JDBC |
|---|---|---|
| API thực thi | EntityManager / Spring Data @Query | JdbcTemplate, NamedParameterJdbcTemplate, JdbcClient |
| SQL | SQL vật lý của database | SQL vật lý của database |
| Entity mapping | Có thể map entity hoặc result set mapping | Thường map qua RowMapper/ResultSetExtractor |
| PersistenceContext | Có liên quan nếu trả entity hoặc dùng cùng EntityManager | Không tự đồng bộ PersistenceContext |
| Dirty checking/lifecycle | Có khi làm việc với entity managed; bulk DML vẫn bỏ qua lifecycle từng entity | Không có entity lifecycle tự động |
| Batch và JDBC control | Provider quyết định nhiều chi tiết | Kiểm soát trực tiếp JDBC API qua Spring abstraction |
| Phù hợp | SQL đặc thù nhưng vẫn muốn dùng JPA mapping | SQL-centric, batch, báo cáo, mapping tùy chỉnh |

Native query qua JPA vẫn hữu ích nếu cần một câu SQL đặc biệt nhưng kết quả là entity hoặc DTO theo mapping JPA. JDBC phù hợp hơn khi muốn kiểm soát ResultSet, batch, generated keys, streaming hoặc SQL là trung tâm.

## 3. Spring JDBC là gì?

Spring JDBC là abstraction trên JDBC API, giúp giảm boilerplate như mở/đóng Connection, tạo PreparedStatement, bind parameter, lặp ResultSet và chuyển SQLException sang hệ exception của Spring.

Các API chính:

- `JdbcTemplate`: API phổ biến để thực hiện query/update/batch.
- `NamedParameterJdbcTemplate`: bind parameter theo tên thay vì vị trí `?`.
- `JdbcClient`: fluent API được giới thiệu trong Spring Framework 6.1, hỗ trợ named/positional parameter và query/update.
- `SimpleJdbcInsert` / `SimpleJdbcCall`: hỗ trợ insert và stored procedure theo metadata/cấu hình.

Spring JDBC không phải ORM. Nó không tự quản lý entity graph, dirty checking, cascade hay lazy loading. Ứng dụng định nghĩa SQL và cách ánh xạ từng hàng.

## 4. JdbcTemplate: query và RowMapper

Ví dụ record làm read model:

```java
public record ProductRow(
    Long id,
    String name,
    BigDecimal price
) {
}
```

Repository JDBC:

```java
@Repository
public class ProductJdbcRepository {

    private final JdbcTemplate jdbcTemplate;

    private static final RowMapper<ProductRow> ROW_MAPPER =
        (rs, rowNum) -> new ProductRow(
            rs.getLong("id"),
            rs.getString("name"),
            rs.getBigDecimal("price")
        );

    public ProductJdbcRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<ProductRow> findActiveProducts() {
        return jdbcTemplate.query("""
            select id, name, price
            from product
            where active = ?
            order by name, id
            """, ROW_MAPPER, true);
    }

    public int updatePrice(Long id, BigDecimal price) {
        return jdbcTemplate.update("""
            update product
            set price = ?
            where id = ?
            """, price, id);
    }
}
```

Ý nghĩa:

- `query(..., RowMapper, args...)` thực thi SELECT và ánh xạ từng hàng.
- `RowMapper` tạo một object cho mỗi row; không cần giữ toàn bộ ResultSet.
- `update(...)` trả số hàng bị ảnh hưởng.
- Parameter được bind qua PreparedStatement, không nối trực tiếp input vào SQL.

Nếu cột nullable, chú ý JDBC primitive getter như `getLong()` trả 0 khi SQL NULL; gọi `rs.wasNull()` ngay sau getter để phân biệt. Với kiểu nullable, có thể dùng `getObject("column", Long.class)` nếu driver hỗ trợ đúng JDBC mapping.

## 5. NamedParameterJdbcTemplate

Với query nhiều tham số, named parameter giúp tránh nhầm thứ tự:

```java
@Repository
public class ProductSearchJdbcRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public ProductSearchJdbcRepository(
            NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<ProductRow> search(
            String category,
            BigDecimal minimumPrice,
            boolean active) {

        String sql = """
            select id, name, price
            from product
            where category = :category
              and price >= :minimumPrice
              and active = :active
            order by name, id
            """;

        MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("category", category)
            .addValue("minimumPrice", minimumPrice)
            .addValue("active", active);

        return jdbc.query(sql, params, (rs, rowNum) ->
            new ProductRow(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getBigDecimal("price")
            )
        );
    }
}
```

NamedParameterJdbcTemplate chuyển named placeholder thành JDBC positional parameter trước khi thực thi. Giá trị vẫn được bind qua PreparedStatement.

Với danh sách:

```java
String sql = """
    select id, name, price
    from product
    where id in (:ids)
    """;

List<ProductRow> rows = jdbc.query(
    sql,
    Map.of("ids", ids),
    ROW_MAPPER
);
```

Spring có thể mở rộng collection thành nhiều placeholder. Hãy xử lý danh sách rỗng ở application layer trước khi gọi query; SQL `IN ()` không portable và cách xử lý có thể phụ thuộc database/framework. Với danh sách rất lớn, chia chunk hoặc dùng cơ chế database-specific như temporary table/array parameter.

## 6. JdbcClient trong Spring Framework 6.1+

`JdbcClient` cung cấp API fluent trên JDBC với named và positional parameter. Nó phù hợp khi muốn code ngắn gọn mà vẫn giữ SQL và mapping tường minh.

Ví dụ:

```java
@Repository
public class ProductJdbcClientRepository {

    private final JdbcClient jdbcClient;

    public ProductJdbcClientRepository(JdbcClient jdbcClient) {
        this.jdbcClient = jdbcClient;
    }

    public Optional<ProductRow> findById(Long id) {
        return jdbcClient.sql("""
            select id, name, price
            from product
            where id = :id
            """)
            .param("id", id)
            .query((rs, rowNum) -> new ProductRow(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getBigDecimal("price")
            ))
            .optional();
    }
}
```

Trong Spring Boot, việc auto-configure JdbcClient phụ thuộc phiên bản Spring Boot/Spring Framework và classpath. Nếu không có bean tự động, có thể tạo bằng `JdbcClient.create(dataSource)`.

`JdbcClient` không thay thế JDBC semantics; nó vẫn chạy SQL và ánh xạ ResultSet. Nếu dự án dùng Spring Framework trước 6.1, dùng JdbcTemplate hoặc NamedParameterJdbcTemplate.

## 7. Batch update và batch insert bằng JDBC

JDBC batch phù hợp khi cần thực hiện nhiều statement cùng cấu trúc với bộ tham số khác nhau. `JdbcTemplate.batchUpdate` giúp gửi nhiều bộ giá trị trong một batch.

Ví dụ:

```java
public int[] updatePrices(List<PriceChange> changes) {
    return jdbcTemplate.batchUpdate(
        """
        update product
        set price = ?
        where id = ?
        """,
        new BatchPreparedStatementSetter() {
            @Override
            public void setValues(
                    PreparedStatement ps,
                    int index) throws SQLException {
                PriceChange change = changes.get(index);
                ps.setBigDecimal(1, change.price());
                ps.setLong(2, change.productId());
            }

            @Override
            public int getBatchSize() {
                return changes.size();
            }
        }
    );
}
```

Record:

```java
public record PriceChange(
    Long productId,
    BigDecimal price
) {
}
```

Kết quả là mảng số hàng cập nhật theo từng batch command. JDBC driver có thể trả `Statement.SUCCESS_NO_INFO` hoặc `Statement.EXECUTE_FAILED` trong một số tình huống batch; cần xử lý theo contract của driver và transaction.

Với dữ liệu lớn:

- Chia danh sách thành chunk có kích thước phù hợp.
- Dùng transaction boundary rõ ràng cho mỗi chunk hoặc toàn bộ job theo yêu cầu atomicity.
- Đo batch size, round trip, lock duration và memory.
- Dùng PreparedStatement parameter binding.
- Xử lý retry/idempotency nếu job có thể chạy lại.
- Kiểm tra driver/database có hỗ trợ batch rewrite hoặc tối ưu tương ứng không.

Batch JDBC không tự gọi JPA lifecycle callback, cascade hay dirty checking. Nếu thao tác trên bảng cũng đang được JPA quản lý trong cùng PersistenceContext, phải đồng bộ trạng thái như phần transaction bên dưới.

## 8. Batch insert và generated keys

Nếu insert cần lấy generated key, JDBC hỗ trợ `GeneratedKeyHolder` với `JdbcTemplate`:

```java
KeyHolder keyHolder = new GeneratedKeyHolder();

jdbcTemplate.update(connection -> {
    PreparedStatement ps = connection.prepareStatement(
        """
        insert into product(name, price, active)
        values (?, ?, ?)
        """,
        Statement.RETURN_GENERATED_KEYS
    );

    ps.setString(1, "Tea");
    ps.setBigDecimal(2, new BigDecimal("12.50"));
    ps.setBoolean(3, true);
    return ps;
}, keyHolder);

Number generatedId = keyHolder.getKey();
```

Đoạn code là phần thân method trong repository JDBC; cần import `KeyHolder`, `GeneratedKeyHolder`, `PreparedStatement`, `Statement` và cấu hình database hỗ trợ generated keys qua JDBC driver.

Với batch insert, việc lấy generated keys cho từng hàng phụ thuộc driver/database và API. Đừng giả định mọi driver trả key theo cùng cách hoặc cùng thứ tự. Nếu cần mapping chính xác, hãy kiểm tra tài liệu driver và integration test trên database mục tiêu.

## 9. JDBC và JPA trong cùng transaction

Một ứng dụng Spring Boot thường dùng cùng DataSource cho JPA và JdbcTemplate. Khi được cấu hình đúng, `JpaTransactionManager` có thể phối hợp truy cập JDBC trên cùng DataSource trong transaction JPA; `JdbcTemplate` dùng cơ chế Spring để tham gia connection đang được transaction quản lý.

Ví dụ:

```java
@Service
public class ProductMaintenanceService {

    private final ProductRepository jpaRepository;
    private final ProductJdbcRepository jdbcRepository;
    private final EntityManager entityManager;

    public ProductMaintenanceService(
            ProductRepository jpaRepository,
            ProductJdbcRepository jdbcRepository,
            EntityManager entityManager) {
        this.jpaRepository = jpaRepository;
        this.jdbcRepository = jdbcRepository;
        this.entityManager = entityManager;
    }

    @Transactional
    public void changePrice(Long id, BigDecimal price) {
        Product product = jpaRepository.findById(id)
            .orElseThrow();

        entityManager.flush();

        jdbcRepository.updatePrice(id, price);

        entityManager.refresh(product);
    }
}
```

Trình tự:

1. Load entity qua JPA.
2. Flush các thay đổi JPA pending trước khi JDBC đọc/ghi cùng dữ liệu.
3. Thực hiện UPDATE qua JDBC.
4. Refresh entity cụ thể để cập nhật trạng thái từ database.

Nếu JDBC thay đổi nhiều entity đang managed, có thể cân nhắc `entityManager.clear()` để detach toàn bộ persistence context rồi load lại khi cần. Clear ảnh hưởng mọi entity managed trong context, nên không dùng tùy tiện.

Nếu không refresh/clear, entity trong first-level cache có thể giữ giá trị cũ. Một lần flush sau đó có thể ghi state cũ trở lại database nếu entity đã bị thay đổi trong memory. Đây là nguồn lỗi mất cập nhật khó phát hiện.

Các điều kiện quan trọng:

- JPA và JDBC phải dùng cùng DataSource/transaction resource nếu muốn cùng local transaction.
- Truy cập JDBC bằng JdbcTemplate/NamedParameterJdbcTemplate hoặc Spring-managed connection để tham gia transaction.
- Nếu ứng dụng có nhiều DataSource/transaction manager, chỉ rõ manager phù hợp bằng `@Transactional(transactionManager = "...")`.
- Hai transaction manager độc lập không tự tạo atomic transaction chung. Nếu cần atomicity qua nhiều resource, phải thiết kế distributed transaction/JTA hoặc quy trình bù trừ phù hợp.
- Không lấy connection trực tiếp qua `DriverManager` trong service Spring được quản lý transaction.

## 10. Flush, clear và thứ tự đọc/ghi khi trộn ORM với JDBC

JPA và JDBC không chia sẻ cùng một object state:

- JPA PersistenceContext giữ entity instance và snapshot dirty checking.
- JDBC thao tác trực tiếp trên database row.
- JDBC không thông báo cho EntityManager rằng một entity đã được UPDATE/DELETE.
- EntityManager không tự đọc lại mọi row sau khi JDBC chạy.

Quy trình thường dùng khi cần đồng bộ:

| Thao tác | Mục đích |
|---|---|
| `entityManager.flush()` trước JDBC | Ghi thay đổi JPA pending để JDBC nhìn thấy |
| JDBC update/delete | Thay đổi database trực tiếp |
| `entityManager.refresh(entity)` | Nạp lại một entity managed cụ thể |
| `entityManager.clear()` | Detach tất cả entity managed, tránh dùng state cũ |
| Load lại entity | Lấy trạng thái database vào context mới/sạch |

Không phải mọi JDBC SELECT đều cần flush; chỉ cần flush khi query phải nhìn thấy thay đổi JPA pending theo thứ tự nghiệp vụ. AUTO flush có thể xảy ra tùy query/provider, nhưng khi trộn API hãy chủ động xác định thứ tự.

Sau JDBC UPDATE, nếu entity liên quan đang managed, refresh hoặc clear trước khi tiếp tục làm việc với state đó. Nếu JDBC DELETE một entity đang managed, không tiếp tục dùng instance như thể nó vẫn còn tồn tại trong database.

## 11. So sánh hiệu năng với JPA batching

Trước khi chuyển hàng loạt thao tác sang JDBC, hãy kiểm tra JPA đã được cấu hình đúng chưa. Hibernate hỗ trợ JDBC batching cho insert/update:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

Với entity nhiều, flush và clear theo chunk giúp tránh PersistenceContext phình quá lớn:

```java
for (int i = 0; i < entities.size(); i++) {
    entityManager.persist(entities.get(i));

    if ((i + 1) % 50 == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}
```

Đây là skeleton minh họa; nếu ID generation dùng identity strategy, khả năng batching insert có thể bị giới hạn tùy Hibernate/database. Sau clear, các entity trước đó detached; không giữ và tiếp tục sửa chúng như managed.

So sánh công bằng:

- JPA batching giữ entity lifecycle, cascade và mapping semantics nhưng có overhead quản lý entity.
- JDBC batch kiểm soát SQL trực tiếp và tránh dựng entity graph, nhưng ứng dụng tự quản lý mapping, audit, optimistic locking và consistency.
- Native bulk DML qua JPA cũng bỏ qua lifecycle từng entity, dù vẫn chạy qua EntityManager.

Đo trên dữ liệu và schema gần production trước khi chọn. Đừng chuyển JDBC chỉ vì số lượng row lớn nếu JPA batch đã đáp ứng throughput và semantics cần thiết.

## 12. jOOQ: SQL DSL có kiểu

jOOQ cung cấp DSL để xây SQL bằng Java, có thể dùng code generation từ schema để tạo table/field reference có kiểu.

Ví dụ minh họa phong cách jOOQ:

```java
var records = dsl
    .select(PRODUCT.ID, PRODUCT.NAME, PRODUCT.PRICE)
    .from(PRODUCT)
    .where(PRODUCT.ACTIVE.eq(true))
    .orderBy(PRODUCT.CREATED_AT.desc(), PRODUCT.ID.desc())
    .limit(50)
    .fetch();
```

Tên `PRODUCT` và field constants trong ví dụ thường được sinh từ schema bằng jOOQ code generator. API thực tế phụ thuộc cấu hình generated code và edition/version.

jOOQ phù hợp khi:

- Query có CTE, window function, lateral join, JSON/array hoặc vendor-specific SQL.
- Cần SQL expression được biểu diễn bằng DSL có kiểu.
- Muốn compile-time hỗ trợ tên bảng/cột và kiểu dữ liệu khi schema/code generation đồng bộ.
- SQL là một phần quan trọng của domain/data access layer.

Đánh đổi:

- Cần quản lý code generation theo schema migration.
- Generated source phải được cập nhật khi schema thay đổi.
- Một số tính năng hoặc database support có thể phụ thuộc edition/version.
- jOOQ không tự thay thế JPA entity lifecycle; có thể dùng cạnh JPA cho query-centric workload.

## 13. MyBatis: SQL mapper

MyBatis cho phép viết SQL tường minh trong mapper XML hoặc annotation và ánh xạ kết quả vào Java object.

Mapper interface:

```java
@Mapper
public interface ProductMapper {

    @Select("""
        select id, name, price
        from product
        where active = #{active}
        order by name, id
        """)
    List<ProductRow> findActive(
        @Param("active") boolean active
    );
}
```

MyBatis phù hợp khi:

- Muốn kiểm soát SQL theo từng mapper method.
- Query có cấu trúc phức tạp hoặc nhiều dynamic SQL branch.
- Team quen quản lý mapper XML/annotation.
- Cần mapping kết quả vào DTO/association theo resultMap.

MyBatis không cung cấp PersistenceContext/dirty checking giống JPA. Ứng dụng kiểm soát SQL và mapping; transaction có thể được tích hợp qua Spring transaction manager theo cấu hình.

Không dùng string substitution `${...}` cho dữ liệu người dùng trong MyBatis vì nó chèn trực tiếp vào SQL. Dùng `#{...}` để bind value. Nếu phải thay identifier động, whitelist giá trị trước khi đưa vào SQL.

## 14. Spring Batch cho job dữ liệu lớn

Nếu yêu cầu là xử lý file hoặc hàng triệu database rows theo job, vấn đề không chỉ là chọn JDBC hay JPA. Cần quản lý:

- Chunk size và transaction boundary.
- Checkpoint/restart sau lỗi.
- Retry/skip cho record lỗi.
- Idempotency khi chạy lại.
- Job parameters và trạng thái execution.
- Reader/writer throughput.
- Monitoring và vận hành job.

Spring Batch cung cấp abstraction như ItemReader, ItemProcessor, ItemWriter và chunk-oriented processing. Có thể dùng JDBC cursor/paging reader, repository reader hoặc reader tùy chỉnh tùy workload.

Luồng khái niệm:

```text
ItemReader
    -> ItemProcessor
        -> ItemWriter
            -> Commit chunk
                -> Checkpoint
```

Ví dụ một chunk 500 record được đọc, xử lý, ghi rồi commit. Nếu job thất bại, restart có thể tiếp tục từ checkpoint theo cấu hình và semantics của reader/writer.

Spring Batch phù hợp cho ETL, import/export, reconciliation và batch maintenance. Không cần đưa Spring Batch vào chỉ để chạy một câu JdbcTemplate.batchUpdate ngắn; dùng framework khi cần job lifecycle, restartability, skip/retry và vận hành.

## 15. Stored procedure, view và database-specific feature

Có thể chọn JDBC hoặc JPA native query khi phải gọi stored procedure hoặc đọc view.

JPA hỗ trợ stored procedure qua `StoredProcedureQuery` hoặc `@NamedStoredProcedureQuery`; Spring JDBC có `SimpleJdbcCall`. Chọn theo cách mapping và transaction hiện tại.

Database view hữu ích cho read model phức tạp. Có thể đọc view bằng JDBC DTO mapper hoặc map thành entity read-only theo provider-specific configuration. Không map một view thành entity có thể update nếu view không hỗ trợ update hoặc mapping không có semantics rõ.

Với database-specific feature như JSON operator, array, full-text search, recursive CTE hoặc window function, native SQL/JDBC/jOOQ thường diễn đạt rõ hơn JPQL. Hãy cô lập SQL phụ thuộc database trong repository/adapter để không lan cú pháp vendor vào service/domain.

## 16. Streaming và đọc dữ liệu lớn

Nếu SELECT trả hàng triệu dòng, không dùng `queryForList` hoặc materialize toàn bộ thành List nếu memory không đủ.

Các lựa chọn:

- JDBC `ResultSet` forward-only với fetch size phù hợp.
- `JdbcTemplate.query(..., RowCallbackHandler)` để xử lý từng hàng.
- Spring Batch reader để đọc theo chunk.
- JPA Stream/scrolling nếu provider và transaction hỗ trợ đúng; phải đóng stream và giữ transaction/connection trong thời gian cần thiết.

Ví dụ RowCallbackHandler:

```java
jdbcTemplate.query(
    "select id, name from product order by id",
    rs -> {
        long id = rs.getLong("id");
        String name = rs.getString("name");
        processRow(id, name);
    }
);
```

RowCallbackHandler xử lý từng row trong callback, tránh tạo một List lớn. Tuy vậy, driver có thể buffer dữ liệu tùy fetch size, cursor mode và database. Cần cấu hình/kiểm tra driver để thực sự streaming; chỉ dùng callback không tự bảo đảm memory constant trong mọi driver.

Nếu xử lý lâu, transaction và connection có thể bị giữ lâu. Chia thành chunk/page hoặc dùng batch framework nếu phù hợp.

## 17. Bảo mật SQL và dynamic query

Dù dùng JPA native query, JdbcTemplate, jOOQ hay MyBatis, quy tắc chung là:

- Bind mọi giá trị dữ liệu bằng parameter.
- Không nối input vào WHERE, LIKE, LIMIT hoặc literal SQL.
- Parameter không thể thay tên bảng/cột, keyword hoặc hướng ASC/DESC.
- Identifier động phải lấy từ whitelist do ứng dụng định nghĩa.
- Kiểm tra quyền truy cập ở service/domain layer; SQL parameterization không thay thế authorization.
- Không log bind values nhạy cảm ở production.

Ví dụ an toàn:

```java
jdbcTemplate.query(
    "select id, name from product where category = ?",
    ROW_MAPPER,
    category
);
```

Ví dụ identifier whitelist:

```java
String orderBy = switch (sortKey) {
    case "name" -> "name";
    case "price" -> "price";
    case "createdAt" -> "created_at";
    default -> "id";
};

String sql = "select id, name from product order by " + orderBy;
```

Chỉ nối biến `orderBy` vì nó được chọn từ các literal do ứng dụng kiểm soát. Không thay bằng giá trị request tùy ý.

## 18. Transaction và nhiều DataSource

Nếu JPA và JDBC cùng dùng một DataSource và cùng transaction manager phù hợp, chúng có thể tham gia một local transaction. Nếu có hai DataSource độc lập, một `@Transactional` đơn thông thường không tự bảo đảm commit/rollback nguyên tử trên cả hai.

Khi nhiều resource:

- Xác định transaction manager mà mỗi repository/service sử dụng.
- Dùng `@Transactional(transactionManager = "jpaTransactionManager")` hoặc tên manager tương ứng khi cần rõ ràng.
- Nếu cần atomic commit qua nhiều resource, đánh giá JTA/XA và chi phí vận hành.
- Nếu distributed transaction không phù hợp, thiết kế outbox, saga hoặc retry/compensation theo nghiệp vụ.
- Không giả định JDBC update và JPA update trên hai datasource sẽ rollback cùng nhau.

Cũng cần chú ý transaction propagation. Method `REQUIRES_NEW` có thể chạy transaction riêng và commit độc lập với transaction bên ngoài. Không dùng nó nếu nghiệp vụ cần tất cả thao tác cùng rollback.

## 19. So sánh công cụ theo nhu cầu

| Nhu cầu | Lựa chọn nên cân nhắc | Lý do |
|---|---|---|
| CRUD theo entity, association, lifecycle | Spring Data JPA | Mapping và persistence context |
| Query object-centric vừa phải | JPQL/Criteria/Specification | Gắn với entity model |
| Một SQL đặc thù nhưng vẫn cần EntityManager | JPA native query | Giữ JPA transaction/mapping |
| SQL tùy chỉnh, row mapping rõ | JdbcTemplate | API đơn giản, kiểm soát SQL |
| Nhiều tham số và collection parameter | NamedParameterJdbcTemplate | Query dễ đọc |
| Fluent JDBC API trên Spring 6.1+ | JdbcClient | Cú pháp fluent, mapping rõ |
| SQL DSL và compile-time schema types | jOOQ | Query phức tạp, database-centric |
| SQL mapper/XML và dynamic SQL | MyBatis | SQL tường minh, resultMap |
| Import/export job lớn, restart/retry | Spring Batch | Job lifecycle và chunk processing |
| Một số batch update đơn giản | JdbcTemplate.batchUpdate | Ít abstraction, hiệu quả trực tiếp |

Không có công cụ nào luôn nhanh nhất. Hiệu năng phụ thuộc SQL, index, cardinality, driver, network round trip, transaction size và cách mapping.

## 20. Quy trình quyết định trước khi rời JPA

1. Xác định bottleneck bằng SQL log, metrics và execution plan.
2. Kiểm tra N+1, fetch plan, index, pagination và query count.
3. Xem có thể tối ưu JPQL/Criteria/EntityGraph hoặc DTO projection không.
4. Kiểm tra Hibernate JDBC batching nếu thao tác insert/update hàng loạt.
5. Thử native query qua JPA nếu chỉ cần cú pháp SQL đặc thù.
6. Chọn JdbcTemplate/JdbcClient khi cần SQL và ResultSet control trực tiếp.
7. Chọn jOOQ khi query DSL/code generation đem lại giá trị rõ.
8. Chọn MyBatis khi SQL mapper là phong cách phù hợp của team.
9. Chọn Spring Batch khi cần job/chunk/checkpoint/restart.
10. Thiết kế transaction, flush/clear, optimistic locking, audit và retry trước khi triển khai.
11. Benchmark bằng cùng dataset, database và transaction semantics.
12. Viết integration test trên database engine mục tiêu.

Đừng so sánh JPA entity load với JDBC DTO projection rồi kết luận JDBC luôn nhanh hơn. Hai cách có thể đang trả dữ liệu và thực hiện semantics khác nhau. Benchmark phải so sánh cùng yêu cầu nghiệp vụ.

## 21. Kiểm thử và quan sát

Với JDBC/JPA hybrid, kiểm thử nên bao gồm:

- SQL và parameter binding đúng.
- RowMapper xử lý NULL và kiểu JDBC đúng.
- Batch update báo số hàng phù hợp.
- Generated keys đúng với driver/database.
- JDBC và JPA tham gia cùng transaction khi được thiết kế như vậy.
- Rollback một thao tác làm rollback thao tác còn lại trong cùng local transaction.
- Flush trước JDBC giúp nhìn thấy thay đổi pending.
- Refresh/clear ngăn dùng entity stale sau JDBC DML.
- Retry job không tạo duplicate hoặc bỏ sót dữ liệu.
- Streaming không materialize toàn bộ result set ngoài dự kiến.
- Count/page hoặc cursor behavior đúng theo hợp đồng API.

Dùng Testcontainers hoặc database test cùng engine với production khi có SQL đặc thù. H2 có thể không tái hiện đầy đủ kiểu dữ liệu, locking, generated key, SQL dialect và execution plan của database thật.

Metrics cần theo dõi gồm query count, latency, rows read/updated, batch size, transaction duration, connection pool utilization, lock wait, memory và retry/failure count.

## 22. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| JDBC không thấy dữ liệu JPA vừa persist | Thay đổi JPA chưa flush | Flush trước khi JDBC đọc |
| JPA trả giá trị cũ sau JDBC UPDATE | PersistenceContext còn entity stale | Refresh entity hoặc clear phù hợp |
| JPA ghi đè kết quả JDBC | Entity stale bị dirty checking/flush sau JDBC | Đồng bộ context trước lần flush tiếp theo |
| JDBC không rollback cùng JPA | Khác DataSource hoặc transaction manager | Cấu hình chung resource/manager hoặc thiết kế distributed consistency |
| SQL injection qua sort column | Nối identifier từ request | Whitelist identifier |
| IN query lỗi với list rỗng | SQL sinh IN () không hợp lệ/không portable | Xử lý empty list trước query |
| Batch chậm hoặc lỗi driver | Batch size/driver rewrite/parameter limit không phù hợp | Đo và điều chỉnh chunk/batch size |
| Generated key thiếu trong batch | Driver không hỗ trợ trả key theo giả định | Kiểm tra driver và integration test |
| Memory tăng khi đọc nhiều dòng | Materialize toàn bộ List hoặc driver buffer | RowCallbackHandler/cursor/chunk với fetch size đúng |
| N+1 vẫn xuất hiện trong JPA | Fetch plan chưa giải quyết association | EntityGraph/fetch join/batch fetching/DTO |
| Chuyển JDBC nhưng mất audit/cascade | JDBC bỏ qua JPA lifecycle | Triển khai audit/domain behavior rõ ràng |
| Spring Batch restart xử lý trùng | Writer không idempotent hoặc checkpoint sai | Thiết kế idempotency và transaction/checkpoint |

## 23. Checklist lựa chọn công cụ

- [ ] Đã đo bottleneck thay vì chỉ phỏng đoán JPA chậm?
- [ ] JPA query/fetch plan/index/batching đã được tối ưu?
- [ ] Kết quả cần entity managed hay DTO/read model?
- [ ] Native query qua JPA đã đủ chưa?
- [ ] Cần JdbcTemplate, NamedParameterJdbcTemplate hay JdbcClient?
- [ ] Query có phù hợp với jOOQ hoặc MyBatis hơn không?
- [ ] Bài toán có cần Spring Batch job lifecycle?
- [ ] JDBC và JPA dùng chung DataSource/transaction manager đúng cách?
- [ ] Đã xác định flush/refresh/clear?
- [ ] Có cần cascade, callbacks, auditing hoặc optimistic locking không?
- [ ] Batch/chunk/fetch size có được đo?
- [ ] Dynamic identifier đã whitelist?
- [ ] Integration test chạy trên database production-compatible?
- [ ] Có metrics cho latency, query count, memory, locks và connection pool?

## 24. Kết luận

JPA là lựa chọn tốt cho CRUD và domain workflow cần entity mapping, association, lifecycle và PersistenceContext. Khi SQL phức tạp, báo cáo, bulk processing hoặc streaming khiến ORM không còn thuận tiện, có thể dùng native query, Spring JDBC, jOOQ hoặc MyBatis cho đúng phần việc. Với job lớn cần restart, checkpoint, retry và chunk, Spring Batch cung cấp lớp vận hành cao hơn một câu batch JDBC.

Khi trộn JDBC với JPA, phải chủ động đồng bộ hai thế giới: flush thay đổi JPA trước khi JDBC cần đọc chúng; refresh hoặc clear entity đang managed sau JDBC DML; bảo đảm cùng DataSource và transaction manager nếu cần atomicity. JDBC không tự gọi lifecycle callback, cascade, dirty checking hay optimistic locking của JPA, nên những semantics nghiệp vụ cần thiết phải được thiết kế riêng.

Hãy chọn công cụ dựa trên SQL thực tế, dữ liệu cần trả, transaction semantics, throughput và khả năng vận hành. Đo bằng cùng workload, kiểm thử trên đúng database/driver và giữ ranh giới truy cập dữ liệu rõ ràng để ứng dụng có thể dùng nhiều công cụ mà vẫn dễ bảo trì.
