# Giới hạn callback khi dùng RowMapper hoặc SQL ghi tùy chỉnh

## 1. Vì sao callback không phải lúc nào cũng chạy?

Spring Data JDBC cung cấp lifecycle callback và lifecycle event để ứng dụng can thiệp vào những thời điểm nhất định trong vòng đời aggregate. Ví dụ, trước khi lưu có thể chuẩn hóa dữ liệu hoặc tạo ID; sau khi lưu có thể ghi nhận một hoạt động; sau khi tải có thể bổ sung thông tin cho aggregate.

Điều dễ nhầm là không phải mọi thao tác SQL trong ứng dụng đều đi qua vòng đời persistence của Spring Data JDBC. Khi ứng dụng:

- Dùng `RowMapper` hoặc `ResultSetExtractor` tùy chỉnh cho query method.
- Dùng `@Modifying` với `@Query` để cập nhật hoặc xóa dữ liệu trực tiếp.
- Dùng `JdbcTemplate` hoặc `NamedParameterJdbcTemplate` để chạy SQL.

thì một phần hoặc toàn bộ lifecycle pipeline của Spring Data JDBC có thể không được gọi. Nếu ứng dụng dựa vào callback để cập nhật audit field, chuẩn hóa dữ liệu hoặc phát hiện thao tác lưu, việc chuyển sang mapping hay SQL tùy chỉnh có thể làm hành vi đó biến mất.

Điều quan trọng là phân biệt ba đường thực thi:

1. Repository dùng mapping mặc định của Spring Data JDBC.
2. Repository query dùng `RowMapper`/`ResultSetExtractor` tùy chỉnh.
3. SQL ghi trực tiếp qua `@Modifying` hoặc Spring JDBC.

Ba đường này không có cùng hành vi callback. Bài này giải thích chính xác giới hạn, các callback/events thuộc aggregate lifecycle và cách giữ nghiệp vụ nhất quán khi cần SQL tùy chỉnh.

## 2. Lifecycle callback và lifecycle event là gì?

Spring Data JDBC có hai cơ chế liên quan nhưng mục đích khác nhau:

| Cơ chế | Mục đích | Đặc điểm |
| --- | --- | --- |
| `EntityCallback` | Can thiệp đồng bộ vào một bước của quá trình persistence hoặc mapping | Có thể nhận và trả về aggregate đã được thay đổi; phù hợp với immutable object và auditing. |
| Lifecycle event | Thông báo rằng một giai đoạn trong vòng đời aggregate vừa xảy ra | Listener phản ứng với event; event không phải cơ chế chính để thay đổi aggregate. |

Ví dụ, `BeforeConvertCallback` có thể chuẩn hóa một aggregate trước khi Spring Data JDBC chuyển nó thành các thao tác SQL. `BeforeSaveEvent` thông báo rằng aggregate sắp được lưu. Callback phù hợp hơn nếu cần thay đổi object; event phù hợp hơn nếu cần thông báo cho thành phần khác.

Spring Data khuyến khích dùng callback thay cho event khi cần can thiệp vào object, vì callback hỗ trợ immutable class và thực thi theo thứ tự xác định trong pipeline. Lifecycle event dựa trên `ApplicationEventMulticaster`; nếu cấu hình multicaster dùng `TaskExecutor`, thời điểm listener xử lý event có thể không còn đồng bộ với bước persistence.

## 3. Những callback và event của Spring Data JDBC

Spring Data JDBC phát lifecycle callback/event cho **aggregate root**. Callback không tự chạy riêng cho từng object con trong aggregate. Nếu cần xử lý dữ liệu của child entity, hãy làm việc thông qua aggregate root chứa nó.

### 3.1. Các callback chính

| Giai đoạn | Callback | Thời điểm |
| --- | --- | --- |
| Trước khi xóa | `BeforeDeleteCallback` | Trước khi các hàng thuộc aggregate bị xóa. |
| Sau khi xóa | `AfterDeleteCallback` | Sau khi aggregate được xóa. |
| Trước khi chuyển đổi để lưu | `BeforeConvertCallback` | Sau khi Spring đã quyết định insert hay update, trước khi tạo kế hoạch SQL. |
| Trước khi thực thi lệnh lưu | `BeforeSaveCallback` | Sau khi kế hoạch thay đổi aggregate đã được tạo, trước khi SQL chạy. |
| Sau khi lưu | `AfterSaveCallback` | Sau khi các câu SQL lưu aggregate đã chạy. |
| Sau khi chuyển đổi khi tải | `AfterConvertCallback` | Sau khi aggregate root được tạo từ ResultSet và các thuộc tính đã được gán. |

Một số điểm quan trọng trong thứ tự lưu:

1. Spring Data JDBC quyết định aggregate là mới hay đã tồn tại.
2. Gọi `BeforeConvertCallback`.
3. Tạo `AggregateChange`, gồm các `DbAction` cần thực hiện và quyết định ID nào được gửi xuống database.
4. Gọi `BeforeSaveCallback`.
5. Thực thi các câu SQL.
6. Gọi `AfterSaveCallback`.

Vì vậy, nếu muốn tự tạo ID cho aggregate mới, dùng `BeforeConvertCallback`. Đến `BeforeSaveCallback`, quyết định insert/update và kế hoạch ID đã được tạo; đây không phải vị trí thích hợp để tạo ID mới.

Khi tải aggregate, `AfterConvertCallback` chạy sau khi aggregate root được chuyển đổi từ dữ liệu database.

### 3.2. Các lifecycle event

| Event | Thời điểm phát |
| --- | --- |
| `BeforeDeleteEvent` | Trước khi aggregate root bị xóa. |
| `AfterDeleteEvent` | Sau khi aggregate root bị xóa. |
| `BeforeConvertEvent` | Trước khi aggregate root được chuyển thành kế hoạch SQL. |
| `BeforeSaveEvent` | Trước khi aggregate root được lưu, sau khi quyết định insert/update. |
| `AfterSaveEvent` | Sau khi aggregate root được lưu. |
| `AfterConvertEvent` | Sau khi aggregate root được tạo từ ResultSet và gán thuộc tính. |

Các event trên không phải event cho từng bảng hoặc từng child object. Nếu một aggregate có nhiều dòng con, event vẫn đại diện cho vòng đời aggregate root.

## 4. Callback hoạt động trong đường repository mặc định

Khi dùng repository CRUD hoặc aggregate persistence thông thường, Spring Data JDBC thực hiện quy trình mapping và persistence của aggregate. Đây là đường thực thi mà callback/event được thiết kế để tham gia.

Ví dụ callback chuẩn hóa tên customer trước khi lưu:

~~~java
import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class CustomerBeforeConvertCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(Customer customer) {
        return customer.withName(customer.name().trim());
    }
}
~~~

`Customer` ở ví dụ là immutable record/class có phương thức `withName`. Callback trả về instance được chỉnh sửa để Spring Data JDBC tiếp tục chuyển đổi và lưu.

Nếu dùng aggregate root mutable, callback có thể trả lại chính instance sau khi sửa thuộc tính. Với immutable object, hãy trả về một instance mới.

### 4.1. Callback không thay thế hành vi domain

Callback thích hợp cho logic kỹ thuật gắn với persistence, ví dụ:

- Chuẩn hóa một giá trị trước khi lưu.
- Gán ID ở bước `BeforeConvertCallback`.
- Cập nhật metadata auditing.
- Bổ sung dữ liệu kỹ thuật nhất quán trong mọi lần aggregate được lưu.

Các quy tắc như “đơn hàng chỉ được hủy khi đang ở trạng thái nháp” hoặc “không được thêm dòng hàng sau khi đơn đã gửi” nên nằm trong aggregate/domain model hoặc application service. Không nên giấu toàn bộ nghiệp vụ vào callback, vì callback không thay thế contract và hành vi tường minh của domain.

## 5. @Query với mapping mặc định và mapping tùy chỉnh

Không phải cứ viết `@Query` là callback bị tắt. Spring Data JDBC dùng cùng `RowMapper` mặc định cho kết quả `@Query` như với các query do framework tự tạo. Nếu query dùng mapping mặc định và trả về aggregate theo cách Spring Data JDBC quản lý, lifecycle mapping có thể tiếp tục tham gia.

Ví dụ query dùng mapping mặc định:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    @Query("""
        SELECT id, name, email
        FROM customers
        WHERE email = :email
        """)
    Optional<Customer> findByEmail(@Param("email") String email);
}
~~~

Câu SQL phải trả đủ các cột cần thiết cho constructor của entity. Những thuộc tính được gán bằng setter, wither hoặc field access có thể không bắt buộc nếu không có cột tương ứng; khi thiếu cột, thuộc tính đó không được gán. Với aggregate có quan hệ one-to-one, tên cột cần theo quy ước prefix quan hệ của Spring Data JDBC. Các collection/map/list của entity có thể cần những query riêng do framework tạo.

Nếu chỉ cần SQL tùy chỉnh nhưng vẫn muốn giữ mapping mặc định của Spring Data JDBC, hãy cân nhắc để query trả về aggregate theo đúng định dạng mà mapper mặc định mong đợi.

## 6. Custom RowMapper hoặc ResultSetExtractor tắt callback và event

Đây là giới hạn quan trọng nhất của bài học.

Spring Data JDBC cho phép chỉ định mapper riêng trong `@Query`, chẳng hạn:

- `rowMapperClass`
- `rowMapperRef`
- `resultSetExtractorClass`
- `resultSetExtractorRef`

Ngoài ra, có thể đăng ký `QueryMappingConfiguration` để chọn `RowMapper` theo kiểu trả về của query method.

**Khi dùng custom `RowMapper` thông qua `QueryMappingConfiguration`, `@Query(rowMapperClass = ...)` hoặc custom `ResultSetExtractor`, Spring Data JDBC tắt Entity Callbacks và Lifecycle Events cho quá trình mapping kết quả.** Mapper tùy chỉnh có thể tự phát event hoặc gọi logic riêng nếu ứng dụng cần.

Ví dụ:

~~~java
public final class CustomerSummaryRowMapper
        implements RowMapper<CustomerSummary> {

    @Override
    public CustomerSummary mapRow(ResultSet rs, int rowNum)
            throws SQLException {
        return new CustomerSummary(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getString("email")
        );
    }
}
~~~

Dùng mapper cho một query:

~~~java
public interface CustomerReportRepository
        extends Repository<Customer, Long> {

    @Query(
        value = """
            SELECT id, display_name, email
            FROM customers
            WHERE active = true
            """,
        rowMapperClass = CustomerSummaryRowMapper.class
    )
    List<CustomerSummary> findActiveSummaries();
}
~~~

Trong trường hợp này, `CustomerSummaryRowMapper` tự tạo DTO từ ResultSet. Spring Data JDBC không chạy `AfterConvertCallback` hoặc lifecycle event cho kết quả được map bằng mapper tùy chỉnh.

### 6.1. Đăng ký RowMapper theo kiểu trả về

Nếu nhiều query trả cùng một kiểu cần dùng chung mapper, có thể đăng ký `QueryMappingConfiguration`:

~~~java
@Configuration
public class QueryMappingConfig {

    @Bean
    QueryMappingConfiguration queryMappingConfiguration() {
        return new DefaultQueryMappingConfiguration()
                .register(CustomerSummary.class,
                        new CustomerSummaryRowMapper());
    }
}
~~~

Spring Data JDBC tìm mapper theo kiểu trả về của method. Với `Optional<CustomerSummary>` hoặc collection chứa `CustomerSummary`, framework unwrap wrapper để xác định kiểu cần mapping. Thứ tự đăng ký có ý nghĩa: kiểu cụ thể nên được đăng ký trước kiểu tổng quát hơn.

Khi cấu hình một custom mapper theo cách này, các query method trả kiểu tương ứng dùng mapper đó sẽ không chạy entity callback và lifecycle event cho mapping kết quả.

### 6.2. Dùng ResultSetExtractor cũng có giới hạn tương tự

`ResultSetExtractor` cho phép xử lý toàn bộ ResultSet, chẳng hạn tạo một cấu trúc lồng nhau hoặc tổng hợp nhiều hàng thành một object. Khi chỉ định custom extractor cho query method, Spring Data JDBC cũng tắt entity callback và lifecycle event cho mapping đó.

Đây là chủ đích: framework không thể giả định custom mapper/extractor đã tạo aggregate theo đúng lifecycle mà mapping mặc định thực hiện. Nếu mapper tự quản lý việc tạo object, mapper cũng phải chịu trách nhiệm cho các bước bổ sung mà ứng dụng cần.

## 7. RowMapper của JdbcTemplate không chạy Spring Data callbacks

Một trường hợp khác là dùng trực tiếp `JdbcTemplate`:

~~~java
List<Customer> customers = jdbcTemplate.query(
        "SELECT id, name, email FROM customers WHERE active = ?",
        (rs, rowNum) -> new Customer(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getString("email")
        ),
        true
);
~~~

Dù `RowMapper` tạo ra object có cùng class `Customer` với aggregate root, thao tác này không đi qua repository/aggregate mapping pipeline của Spring Data JDBC. Vì vậy, Spring Data JDBC không tự gọi:

- `AfterConvertCallback`.
- Lifecycle event `AfterConvertEvent`.
- Các callback/event lưu hoặc xóa aggregate.
- Cơ chế auditing gắn với aggregate persistence.

`JdbcTemplate` chỉ thực thi SQL và gọi mapper mà caller cung cấp. Nó không tự suy luận rằng object vừa tạo là một aggregate root cần chạy lifecycle callback.

Nếu chỉ cần đọc dữ liệu cho báo cáo hoặc màn hình, hãy map sang DTO/projection thay vì tạo một aggregate giả chỉ để tái sử dụng class domain. Nếu cần aggregate với lifecycle behavior, dùng repository hoặc `JdbcAggregateTemplate` với mapping mặc định.

## 8. SQL ghi tùy chỉnh không gọi callback hoặc event

Query sửa dữ liệu được đánh dấu `@Modifying` chạy trực tiếp trên database:

~~~java
@Modifying
@Query("""
    UPDATE customers
    SET display_name = :name
    WHERE id = :id
    """)
int updateDisplayName(
        @Param("id") Long id,
        @Param("name") String name
);
~~~

Với modifying query, Spring Data JDBC không gọi lifecycle event hoặc entity callback. Điều đó có nghĩa:

- `BeforeSaveCallback` không chạy.
- `AfterSaveCallback` không chạy.
- `BeforeSaveEvent` và `AfterSaveEvent` không được phát.
- Callback auditing không tự cập nhật các trường `@LastModifiedDate` hoặc `@LastModifiedBy`.

Nếu câu SQL không cập nhật cột audit, cột đó giữ giá trị cũ. Việc method trả về `int` hoặc `boolean` chỉ cung cấp thông tin về số hàng được cập nhật; nó không làm callback tự chạy.

Điều tương tự xảy ra khi dùng `JdbcTemplate.update(...)` hoặc `NamedParameterJdbcTemplate.update(...)`. SQL được thực thi trực tiếp và không đi qua aggregate save pipeline.

### 8.1. Direct DELETE cũng không có aggregate lifecycle như repository delete

Nếu dùng SQL tùy chỉnh để xóa hàng, không nên kỳ vọng `BeforeDeleteCallback`, `AfterDeleteCallback`, `BeforeDeleteEvent` hoặc `AfterDeleteEvent` tự được gọi. Spring Data JDBC không có cách hiệu quả để suy ra chính xác những aggregate nào bị ảnh hưởng bởi một câu SQL tùy chỉnh có thể tác động nhiều hàng.

Nếu nghiệp vụ cần xử lý trước/sau khi xóa aggregate, hãy dùng đường aggregate delete hoặc gọi logic cần thiết ở application service. Với bulk delete, thiết kế rõ cách xử lý audit, outbox và các quan hệ liên quan.

## 9. Vì sao Spring Data JDBC không thể tự gọi callback cho bulk SQL?

Giả sử một query cập nhật hàng nghìn customer:

~~~sql
UPDATE customers
SET active = false
WHERE last_seen < :cutoff;
~~~

Để chạy callback kiểu `BeforeSaveCallback<Customer>` cho từng customer, framework phải:

1. Tìm toàn bộ aggregate bị ảnh hưởng.
2. Tải từng aggregate cùng dữ liệu con cần thiết.
3. Gọi callback cho từng aggregate.
4. Tính lại các thay đổi và câu SQL.
5. Đảm bảo kết quả không thay đổi giữa lúc đọc và lúc cập nhật.

Điều này có thể rất tốn kém và không phù hợp với mục tiêu của bulk SQL. Một câu lệnh sửa hàng loạt thường cố ý bỏ qua bước materialize từng aggregate. Do đó Spring Data JDBC không gọi callback/event cho modifying query.

Nếu thao tác phải tuân thủ hành vi domain của từng aggregate, hãy tải và xử lý từng aggregate bằng repository. Nếu đây là một maintenance/bulk operation được định nghĩa rõ, hãy đưa quy tắc cần thiết vào SQL, constraint hoặc quy trình service.

## 10. Auditing khi dùng SQL ghi tùy chỉnh

Spring Data JDBC auditing thường dựa trên entity callback. Khi dùng đường aggregate persistence, các annotation như `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` và `@LastModifiedBy` có thể được cập nhật theo cấu hình auditing.

Với `@Modifying` hoặc JDBC trực tiếp, các giá trị này không tự cập nhật. Có ba cách xử lý phổ biến.

### 10.1. Cập nhật audit field ngay trong SQL

~~~java
@Modifying
@Query("""
    UPDATE customers
    SET display_name = :name,
        last_modified_at = CURRENT_TIMESTAMP,
        last_modified_by = :actor
    WHERE id = :id
    """)
int updateDisplayName(
        @Param("id") Long id,
        @Param("name") String name,
        @Param("actor") String actor
);
~~~

SQL ghi rõ các cột audit cần cập nhật. Cách này minh bạch và phù hợp với một số thao tác bulk. Cần bảo đảm giá trị actor được lấy từ security/application context đã xác thực, không tin trực tiếp dữ liệu do client tùy ý gửi.

### 10.2. Dùng database default hoặc trigger

Nếu quy tắc audit áp dụng ở mọi đường ghi, database default hoặc trigger có thể bảo vệ dữ liệu kể cả khi câu SQL đến từ ứng dụng khác. Tuy nhiên, cần thiết kế trigger nhất quán với auditing ở application layer để tránh hai nơi cùng ghi đè timestamp hoặc actor.

### 10.3. Dùng aggregate persistence khi cần callback auditing

Nếu thao tác là cập nhật một aggregate theo đúng domain behavior và cần auditing callback, tải aggregate, gọi hành vi domain rồi lưu qua repository hoặc `JdbcAggregateTemplate`. Đừng dùng modifying query chỉ để tiết kiệm vài dòng code nếu nó làm mất các quy tắc quan trọng của aggregate.

## 11. Giữ domain behavior khi custom mapper hoặc SQL

Callback không phải nơi duy nhất chứa logic có thể bị bỏ qua. Khi rời khỏi aggregate persistence, ứng dụng cũng cần xem xét:

- Domain invariant có được kiểm tra không?
- Giá trị có được chuẩn hóa như trước không?
- `@Version`/optimistic locking có được áp dụng không?
- Audit metadata có được ghi không?
- Child entity có được đồng bộ đúng không?
- Có cần ghi outbox event hoặc audit row không?
- Có cần xử lý side effect sau khi transaction commit không?

Ví dụ một câu SQL đổi trạng thái đơn hàng:

~~~sql
UPDATE purchase_orders
SET status = 'CANCELLED'
WHERE id = :id;
~~~

Câu SQL này không tự gọi `order.cancel()` và không kiểm tra đơn hàng có đang ở trạng thái cho phép hủy hay không. Nếu quy tắc chỉ cho phép hủy đơn nháp, điều kiện cần được thể hiện trong domain/application logic hoặc trong SQL:

~~~sql
UPDATE purchase_orders
SET status = 'CANCELLED'
WHERE id = :id
  AND status = 'DRAFT';
~~~

Sau đó kiểm tra số hàng bị ảnh hưởng. Với nghiệp vụ phong phú, tải aggregate, gọi hành vi domain và lưu lại thường diễn đạt rõ hơn.

## 12. Khi cần phát event sau SQL trực tiếp

Nếu một câu `@Modifying` hoặc `JdbcTemplate.update` thay đổi dữ liệu và ứng dụng cần thông báo cho hệ thống khác, đừng kỳ vọng Spring Data JDBC tự phát `AfterSaveEvent`.

Có thể điều phối rõ ràng ở application service:

~~~java
@Service
public class CustomerStatusService {

    private final CustomerRepository customers;
    private final OutboxRepository outbox;

    public CustomerStatusService(
            CustomerRepository customers,
            OutboxRepository outbox
    ) {
        this.customers = customers;
        this.outbox = outbox;
    }

    @Transactional
    public void deactivate(Long id) {
        int changed = customers.deactivateById(id);

        if (changed != 1) {
            throw new IllegalStateException("Customer was not deactivated");
        }

        outbox.save(OutboxMessage.customerDeactivated(id));
    }
}
~~~

Trong ví dụ, `deactivateById` là modifying query và `outbox.save` ghi thông điệp cần phát trong cùng transaction. Sau commit, một publisher riêng đọc outbox và gửi message. Nếu transaction rollback, cả thay đổi customer và outbox row đều rollback.

Nếu chỉ cần thông báo nội bộ trong cùng process, application service có thể publish application event tường minh. Với thông điệp cần bảo đảm không mất khi process dừng sau commit, transactional outbox thường đáng tin cậy hơn việc chỉ phát event trong bộ nhớ.

## 13. Khi nào nên dùng callback, RowMapper hay SQL trực tiếp?

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Chuẩn hóa aggregate trước khi lưu | `BeforeConvertCallback` |
| Tạo ID cho aggregate mới | `BeforeConvertCallback` |
| Thay đổi aggregate trước khi SQL chạy | `BeforeSaveCallback`, hiểu rõ `AggregateChange` đã được tạo |
| Phản ứng sau khi aggregate được lưu | `AfterSaveCallback` hoặc lifecycle event phù hợp |
| Thay đổi aggregate sau khi được tải bằng mapping mặc định | `AfterConvertCallback` |
| Thông báo cho listener về giai đoạn lifecycle | Lifecycle event |
| Trả DTO/projection cho báo cáo | Custom `RowMapper` hoặc `ResultSetExtractor` |
| Tối ưu mapping query đặc thù | Custom `RowMapper`/`QueryMappingConfiguration`, tự xử lý logic cần thiết |
| Cập nhật hàng loạt theo điều kiện | `@Modifying` hoặc `JdbcTemplate`, cập nhật audit/invariant tường minh |
| Thực hiện nghiệp vụ trên một aggregate | Repository hoặc `JdbcAggregateTemplate` |

Không chọn custom RowMapper chỉ vì muốn đổi vài tên cột nếu mapping mặc định đã đáp ứng. Custom mapping có thể làm mất callback/event, nên cân nhắc tác động đó trước khi dùng.

## 14. Kiểm thử giới hạn callback

Nên kiểm thử cả đường aggregate persistence và các đường tùy chỉnh để tránh phụ thuộc vào giả định sai.

### 14.1. Kiểm thử callback trên repository save

Tạo một callback có thể quan sát được:

~~~java
@Component
public class CustomerSaveCallback
        implements BeforeConvertCallback<Customer> {

    private final CustomerCallbackProbe probe;

    public CustomerSaveCallback(CustomerCallbackProbe probe) {
        this.probe = probe;
    }

    @Override
    public Customer onBeforeConvert(Customer customer) {
        probe.record(customer.id());
        return customer;
    }
}
~~~

Trong integration test, gọi `repository.save(customer)` và xác nhận probe đã được gọi.

### 14.2. Kiểm thử custom RowMapper

Khai báo query method dùng `rowMapperClass` hoặc `QueryMappingConfiguration`. Gọi method và xác nhận kết quả DTO đúng, đồng thời callback probe không được gọi cho mapping đó.

### 14.3. Kiểm thử modifying query

Gọi method có `@Modifying @Query`, sau đó xác nhận:

- Hàng database được cập nhật.
- Callback/event save không được gọi.
- Các audit field chỉ thay đổi nếu câu SQL có cập nhật chúng hoặc database trigger xử lý.
- Row count phản ánh số hàng bị tác động.

### 14.4. Kiểm thử transaction và outbox

Nếu SQL ghi tùy chỉnh cần phát event, kiểm thử:

1. Cập nhật dữ liệu và ghi outbox trong cùng transaction.
2. Cố tình làm bước ghi outbox thất bại.
3. Xác nhận thay đổi dữ liệu nghiệp vụ cũng rollback.
4. Chạy thành công và xác nhận publisher chỉ xử lý message đã commit.

Dùng database integration phù hợp với production khi kiểm thử SQL đặc thù, trigger hoặc semantics transaction.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `AfterConvertCallback` không chạy sau query | Query dùng custom `RowMapper` hoặc `ResultSetExtractor` | Dùng mapping mặc định nếu cần callback, hoặc gọi logic cần thiết tường minh trong mapper/service. |
| Callback chạy khi `findById` nhưng không chạy khi query tùy chỉnh | Hai đường mapping khác nhau | Kiểm tra `rowMapperClass`, `rowMapperRef`, `QueryMappingConfiguration` và `ResultSetExtractor`. |
| `@LastModifiedDate` không thay đổi sau bulk update | `@Modifying` chạy SQL trực tiếp, không gọi auditing callback | Cập nhật audit field trong SQL, dùng trigger hoặc chuyển về aggregate save. |
| `AfterSaveEvent` không phát sau `@Modifying` | Modifying query không gọi lifecycle event/callback | Phát application event/outbox tường minh nếu use case cần. |
| RowMapper tạo aggregate nhưng callback vẫn không chạy | Tạo object bằng JDBC mapper không đi qua aggregate mapping pipeline | Dùng repository/`JdbcAggregateTemplate` hoặc tự thực hiện logic cần thiết. |
| Child entity không nhận callback riêng | Lifecycle callback/event chỉ được phát cho aggregate root | Xử lý child qua callback/listener của aggregate root chứa nó. |
| Listener xử lý event không đúng thời điểm | Event multicaster có thể chạy bất đồng bộ | Dùng EntityCallback cho thay đổi đồng bộ; dùng transaction-aware event/outbox cho side effect cần thời điểm rõ ràng. |
| SQL trực tiếp làm sai invariant | Đường SQL bỏ qua hành vi domain | Đưa điều kiện vào domain/service/SQL constraint hoặc dùng aggregate persistence. |
| Bulk update bỏ qua version | SQL tùy chỉnh không tự chạy optimistic locking | Đưa expected version vào điều kiện và tăng version trong cùng statement nếu cần. |

## 16. Quy trình chọn đường thực thi

Trước khi thay mapping mặc định hoặc dùng SQL ghi tùy chỉnh, hãy trả lời:

1. **Kết quả là aggregate hay DTO?** Nếu chỉ cần projection, custom RowMapper thường phù hợp.
2. **Có cần lifecycle callback khi tải không?** Nếu có, tránh custom RowMapper/ResultSetExtractor hoặc tự thực hiện logic tương ứng.
3. **Có cần callback khi lưu/xóa không?** SQL ghi tùy chỉnh không gọi callback/event save/delete.
4. **Có auditing không?** Xác định ai cập nhật created_at, last_modified_at, actor và các trường tương ứng.
5. **Có invariant hoặc version không?** SQL trực tiếp phải bảo vệ chúng một cách tường minh.
6. **Có side effect sau commit không?** Cân nhắc application event hoặc transactional outbox.
7. **Có thao tác trên child entity không?** Nhớ rằng callback/event được phát cho aggregate root.
8. **Đã kiểm thử đúng đường thực thi chưa?** Kiểm tra riêng repository mặc định, custom mapping và direct DML.

## 17. Bài tập tự thực hành

**Bài tập 1 — Callback mặc định.** Tạo `BeforeConvertCallback<Customer>` để chuẩn hóa tên. Lưu customer qua repository và xác nhận giá trị được chuẩn hóa trước khi ghi.

**Bài tập 2 — Mapping mặc định của @Query.** Viết một `@Query` trả về `Customer` với mapping mặc định. Bảo đảm câu SELECT có đủ cột constructor cần thiết và quan sát callback sau convert.

**Bài tập 3 — Custom RowMapper.** Tạo `CustomerSummaryRowMapper`, gắn qua `rowMapperClass`, gọi query và xác nhận callback/lifecycle event của Spring Data JDBC không được gọi cho mapping tùy chỉnh.

**Bài tập 4 — QueryMappingConfiguration.** Đăng ký mapper cho một kiểu trả về. Kiểm tra query method dùng kiểu đó và quan sát khác biệt với mapping mặc định.

**Bài tập 5 — Modifying query.** Viết `@Modifying @Query` cập nhật customer. Xác nhận `AfterSaveCallback` không chạy và tự cập nhật audit columns trong SQL.

**Bài tập 6 — JdbcTemplate.** Dùng `JdbcTemplate` tạo object qua RowMapper. So sánh với `repository.findById` và giải thích vì sao cùng một class Java không có nghĩa cùng lifecycle.

**Bài tập 7 — Outbox.** Thực hiện bulk update và ghi outbox row trong cùng transaction. Làm outbox insert thất bại và xác nhận bulk update rollback.

**Bài tập 8 — Aggregate root và child.** Tạo aggregate có collection child. Quan sát callback nhận aggregate root và thiết kế cách xử lý child mà không mong đợi callback riêng cho từng phần tử.

## 18. Ghi nhớ

Spring Data JDBC gọi lifecycle callback/event trong đường aggregate persistence và mapping mặc định. Callback/event được phát cho aggregate root, không phải từng child object. `BeforeConvertCallback` phù hợp để chuẩn bị aggregate và tạo ID; `BeforeSaveCallback` chạy sau khi kế hoạch `AggregateChange` đã được tạo; `AfterSaveCallback` và `AfterConvertCallback` tương ứng với các bước sau lưu và sau tải.

`@Query` dùng mapping mặc định không đồng nghĩa callback tự động bị tắt. Nhưng custom `RowMapper` qua `QueryMappingConfiguration` hoặc `rowMapperClass`, cũng như custom `ResultSetExtractor`, sẽ tắt Entity Callbacks và Lifecycle Events cho mapping kết quả. `@Modifying` query chạy SQL trực tiếp nên không gọi callback/event; `JdbcTemplate` cũng nằm ngoài aggregate lifecycle pipeline.

Khi dùng mapping hoặc SQL tùy chỉnh, hãy chủ động xử lý auditing, invariant, version, audit log và outbox nếu use case cần chúng. Dùng callback cho logic kỹ thuật đồng bộ trong aggregate lifecycle, dùng event để thông báo, và dùng application service để điều phối nghiệp vụ. Kiểm thử riêng từng đường thực thi để bảo đảm hành vi không biến mất khi thay đổi cách truy cập dữ liệu.

### Tài liệu tham khảo

- [Spring Data Relational – Lifecycle Events and Entity Callbacks](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html)
- [Spring Data Relational – Query Methods, Custom RowMapper and Modifying Queries](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Data Relational – BeforeConvertCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeConvertCallback.html)
- [Spring Data Relational – BeforeSaveCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeSaveCallback.html)
- [Spring Data Relational – AfterConvertCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/AfterConvertCallback.html)
