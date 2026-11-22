# Lập bộ kiểm thử hồi quy cho SQL, mapping, giao dịch và hiệu năng

Khi ứng dụng Spring Data R2DBC thay đổi entity, repository, câu SQL, converter hoặc cách kết hợp publisher, một chức năng có thể vẫn trả kết quả đúng trong test đơn giản nhưng lại sai trên dữ liệu thực tế. Một cột thời gian có thể bị đổi timezone, truy vấn join có thể nhân bản hàng, count query có thể đếm sai, transaction có thể commit một phần hoặc một thay đổi nhỏ trong predicate có thể khiến database bỏ qua index.

Bộ kiểm thử hồi quy (*regression test suite*) giúp phát hiện những thay đổi như vậy trước khi phát hành. Với R2DBC, bộ test cần kiểm tra nhiều lớp: SQL thực sự chạy trên database mục tiêu, dữ liệu được ánh xạ vào entity/projection đúng, transaction và concurrency giữ đúng semantics, và hiệu năng vẫn nằm trong ngân sách đã xác định.

Không nên chỉ kiểm tra method trả về một `Mono` hay `Flux` có giá trị. Một bộ test đáng tin cậy cần xác nhận kết quả cuối trong database, các ràng buộc, hành vi khi lỗi, số lượng truy vấn quan trọng và những chỉ số hiệu năng có ý nghĩa với workload. Đồng thời, test phải lặp lại được, dùng dữ liệu xác định và chạy trên database/driver gần production.

## 1. Mục tiêu và phạm vi của regression suite

Regression testing không chỉ xác nhận tính năng mới. Nó xác nhận những hành vi đã được cam kết vẫn đúng sau khi code hoặc schema thay đổi.

Với Spring Data R2DBC, nên bao phủ ít nhất bốn nhóm:

| Nhóm | Câu hỏi cần trả lời | Ví dụ lỗi có thể phát hiện |
|---|---|---|
| SQL và query behavior | Query lọc, join, sort, paging và aggregate có trả đúng tập dữ liệu không? | Thiếu tenant predicate, count sai, join nhân bản hàng |
| Entity/projection mapping | Kiểu Java, tên cột, null, generated value và conversion có đúng không? | Mất precision, sai timezone, enum không map được |
| Transaction và concurrency | Commit, rollback, isolation và optimistic locking có giữ tính toàn vẹn không? | Ghi một phần, lost update, transaction context bị tách |
| Hiệu năng | Query latency, throughput, pool và tài nguyên có nằm trong ngưỡng không? | N+1, full table scan, acquire timeout, memory tăng |

Ngoài bốn nhóm chính, bộ test có thể bao gồm migration compatibility, cancellation, lỗi driver, retry và observability nếu các hành vi đó quan trọng với ứng dụng.

### 1.1. Xác định contract trước khi viết test

Mỗi test nên kiểm tra một hành vi được mô tả rõ:

- Input và trạng thái database ban đầu là gì?
- Query hoặc nghiệp vụ phải thực hiện điều gì?
- Kết quả trả về cần có giá trị nào?
- Database cuối cùng phải ở trạng thái nào?
- Có lỗi nào được mong đợi không?
- Thời gian hoặc tài nguyên có giới hạn nào không?

Ví dụ contract của truy vấn tìm đơn hàng theo tenant và trạng thái:

```text
Given:
  tenant A có 3 đơn PAID, tenant B có 2 đơn PAID
  request của tenant A lọc trạng thái PAID

When:
  gọi searchOrders(tenantA, PAID, page=0, size=20)

Then:
  chỉ nhận 3 đơn của tenant A
  totalElements = 3
  kết quả được sort ổn định
  không có hàng của tenant B
```

Test này kiểm tra cả kết quả content và total, đồng thời xác nhận ranh giới tenant. Chỉ kiểm tra `content.size() == 3` là chưa đủ nếu một query khác có thể trả nhầm dữ liệu cùng số lượng.

### 1.2. Tách test theo tầng

Một chiến lược hữu ích gồm:

1. **Unit test:** kiểm tra logic thuần Java, validation, mapping function và quy tắc nghiệp vụ không cần database.
2. **Repository integration test:** kiểm tra SQL, mapping và driver trên database thật.
3. **Transaction/concurrency integration test:** kiểm tra nhiều statement, nhiều connection và các tình huống tranh chấp.
4. **Performance regression test:** đo query và luồng end-to-end trên dữ liệu đại diện.
5. **Migration compatibility test:** kiểm tra schema sau migration và tương thích với phiên bản code liên quan.

Không dùng mock repository để chứng minh SQL, transaction hoặc query plan đúng. Mock chỉ chứng minh code gọi mock theo cách đã định nghĩa.

## 2. Chọn môi trường kiểm thử gần production

SQL và transaction semantics phụ thuộc database engine. Một test chạy trên H2 không chứng minh cùng query sẽ hoạt động giống PostgreSQL, MySQL, SQL Server hoặc Oracle.

### 2.1. Dùng Testcontainers cho integration test

Testcontainers cho phép khởi chạy database thật trong container và cấu hình Spring R2DBC kết nối tới cổng được ánh xạ động.

Ví dụ cấu hình PostgreSQL với JUnit 5:

```java
@Testcontainers
@DataR2dbcTest
@ActiveProfiles("test")
class OrderRepositoryTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16.4-alpine")
                    .withDatabaseName("store_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void configureR2dbc(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
                "r2dbc:postgresql://" + postgres.getHost() + ":"
                        + postgres.getMappedPort(5432) + "/"
                        + postgres.getDatabaseName());
        registry.add("spring.r2dbc.username", postgres::getUsername);
        registry.add("spring.r2dbc.password", postgres::getPassword);
    }

    @Autowired
    OrderRepository orderRepository;
}
```

Pin image version để kết quả có thể tái tạo. Không dùng `latest` trong regression suite cần ổn định. Nếu dự án có nhiều database được hỗ trợ, chạy contract suite riêng cho từng database/driver thay vì giả định một engine đại diện cho tất cả.

### 2.2. Dùng schema và fixture xác định

Schema test nên được tạo bằng migration hoặc SQL initialization đã được dự án chọn làm nguồn sự thật. Fixture cần:

- Có natural key dễ tìm như `ORD-TEST-001`.
- Dùng timestamp cố định nếu assertion phụ thuộc thời gian.
- Tạo dữ liệu cha trước dữ liệu con.
- Giữ constraint và index quan trọng như production.
- Không giả định identity luôn bắt đầu từ một số cụ thể.

Ví dụ, test tìm đơn hàng bằng `orderCode` thay vì `id = 1`. Nếu cần kiểm tra generated ID, chỉ cần xác nhận ID được sinh và đọc lại đúng bản ghi.

### 2.3. Dữ liệu cần đại diện cho workload

Một bảng chỉ có ba hàng phù hợp để kiểm tra mapping cơ bản, nhưng không đủ để đánh giá paging hoặc query plan. Performance regression cần dữ liệu có:

- Kích thước gần quy mô sử dụng thực tế.
- Phân bố dữ liệu và độ chọn lọc của predicate tương tự production.
- Tỷ lệ null, trạng thái và khóa ngoại hợp lý.
- Số lượng quan hệ một-nhiều đủ để lộ lỗi join hoặc N+1.
- Một số trường hợp biên như dữ liệu rỗng, rất lớn hoặc giá trị trùng.

Không nhất thiết đưa toàn bộ production data vào test. Dùng dữ liệu tổng hợp có phân bố tương tự và không chứa thông tin cá nhân thật.

## 3. Kiểm thử SQL và hành vi truy vấn

Test SQL cần xác nhận tập dữ liệu, thứ tự và semantics, không chỉ xác nhận query chạy mà không phát exception.

### 3.1. Kiểm tra predicate và điều kiện biên

Với mỗi repository query, chuẩn bị các hàng thỏa và không thỏa từng điều kiện. Ví dụ query lọc theo tenant, trạng thái và thời gian:

```sql
SELECT id, order_code, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND created_at >= :from
  AND created_at < :to
ORDER BY created_at DESC, id DESC
```

Test cần xác nhận:

- Hàng thuộc tenant khác không xuất hiện.
- Hàng có status khác không xuất hiện.
- Mốc `from` được bao gồm.
- Mốc `to` bị loại nếu predicate dùng `<`.
- Timestamp trùng nhau được sắp xếp ổn định bằng `id`.
- Không có dữ liệu thì publisher hoàn tất rỗng hoặc response page có content rỗng theo contract.

Đối với khoảng thời gian, dùng quy ước half-open `[from, to)` thường giúp ghép các khoảng liên tiếp mà không đếm trùng biên. Nếu nghiệp vụ chọn quy ước khác, test phải phản ánh chính xác quy tắc đó.

### 3.2. Kiểm tra filter động

Với filter tùy chọn, tạo test cho từng tổ hợp có ý nghĩa:

- Chỉ có filter bắt buộc.
- Thêm từng filter riêng lẻ.
- Nhiều filter kết hợp.
- Filter chuỗi rỗng hoặc chỉ có whitespace.
- Giá trị null mang nghĩa bỏ qua filter.
- Trường hợp cần tìm giá trị SQL `NULL` một cách tường minh.

Đừng chỉ test trường hợp mọi filter đều có giá trị. Lỗi thường xuất hiện khi query builder nối `AND`/`OR` sai hoặc bind null không đúng kiểu.

### 3.3. Kiểm tra join và cardinality

Khi join một-nhiều, một entity cha có thể xuất hiện nhiều hàng SQL. Test cần phân biệt:

- Query trả entity cha duy nhất.
- Query trả từng dòng con.
- Query trả projection đã aggregate.

Ví dụ một đơn có ba dòng hàng. Nếu màn hình phân trang theo đơn hàng, kết quả phải có một phần tử cho đơn đó, còn `lineCount` bằng 3. Nếu count query dùng `COUNT(*)` trên join, total có thể thành 3 thay vì 1.

Tạo fixture gồm:

- Một đơn không có dòng con nếu quan hệ cho phép.
- Một đơn có một dòng.
- Một đơn có nhiều dòng.
- Hai đơn cùng khách hàng.
- Dữ liệu con thuộc tenant khác nếu schema có tenant scope.

Kiểm tra `LEFT JOIN`, `COUNT(child.id)`, `COUNT(DISTINCT parent.id)` hoặc `EXISTS` theo đúng semantics. Đừng chỉ so sánh số hàng của content mà bỏ qua nội dung từng projection.

### 3.4. Kiểm tra paging và sort

Với offset pagination:

- Trang đầu trả đúng `size` hàng tối đa.
- Trang tiếp theo không lặp hàng trong dataset tĩnh.
- Trang cuối có số hàng còn lại chính xác.
- Trang vượt phạm vi trả content rỗng.
- `totalElements` không bị giới hạn bởi `LIMIT/OFFSET`.
- Sort có tie-breaker duy nhất.

Với keyset pagination:

- Cursor chứa đủ các trường sort.
- Hàng có cùng timestamp không bị bỏ sót hoặc lặp.
- Cursor không được tái sử dụng sau khi đổi filter hoặc sort.
- Điều kiện cursor xử lý đúng chiều tăng/giảm.

Nếu sort động được whitelist, test từng lựa chọn được phép và xác nhận giá trị không hợp lệ bị từ chối trước khi tạo SQL.

### 3.5. Kiểm tra count query độc lập

Count query cần được test như một query riêng về semantics. Những trường hợp quan trọng:

- Count không có limit/offset.
- Count áp dụng cùng filter logic với content.
- Join một-nhiều không đếm trùng entity logic.
- Query aggregate đếm số nhóm thay vì số hàng nguồn.
- `HAVING` được giữ trong count qua subquery nếu cần.
- Empty result trả total bằng 0.

Nếu content và count được tạo từ một builder dùng chung, vẫn cần integration test vì hai SQL cuối cùng có thể khác nhau ở phần join, group hoặc bind.

### 3.6. Kiểm tra SQL injection và bind parameters

Không kiểm thử injection bằng cách chỉ tìm chuỗi SQL trong source. Hãy gọi query với input chứa dấu nháy, ký tự đặc biệt hoặc payload giống cú pháp SQL và xác nhận nó được coi là giá trị dữ liệu, không thay đổi cấu trúc câu lệnh.

Ví dụ email:

```java
String input = "x' OR '1'='1";

StepVerifier.create(customerRepository.findByEmail(input))
        .verifyComplete();
```

Test nên xác nhận query không trả tất cả khách hàng. Tên cột, tên bảng và sort direction phải được chọn từ whitelist, vì identifier không thể bind như value.

### 3.7. Kiểm tra list rỗng và giới hạn parameter

Query `IN (:ids)` có thể có hành vi đặc biệt khi list rỗng hoặc rất lớn. Xác định contract cho list rỗng: trả empty, bỏ predicate hay báo validation. Không để một list rỗng vô tình làm query trả tất cả dữ liệu.

Với list lớn, kiểm tra giới hạn bind parameter của database/driver. Nếu cần, chia batch hoặc dùng kiểu array/native table parameter theo database mục tiêu.

## 4. Kiểm thử entity và projection mapping

Mapping regression thường khó phát hiện nếu test chỉ đọc một vài trường String. Hãy kiểm tra đầy đủ kiểu dữ liệu, nullability, tên cột và giá trị do database sinh.

### 4.1. Round-trip insert và read

Với mỗi entity quan trọng, test:

1. Tạo entity với các giá trị hợp lệ.
2. Lưu qua repository.
3. Dùng ID hoặc natural key đọc lại.
4. So sánh các thuộc tính cần bảo toàn.
5. Kiểm tra giá trị database sinh hoặc auditing nếu có.

```java
@Test
void savesAndReadsCustomer() {
    CustomerEntity draft = new CustomerEntity(
            null, "an@example.test", "An Nguyen");

    StepVerifier.create(customerRepository.save(draft)
            .flatMap(saved -> customerRepository.findById(saved.id())))
            .assertNext(found -> {
                assertThat(found.id()).isNotNull();
                assertThat(found.email()).isEqualTo("an@example.test");
                assertThat(found.displayName()).isEqualTo("An Nguyen");
            })
            .verifyComplete();
}
```

Với record/immutable entity, dùng instance được phát ra từ `save`; không giả định object đầu vào bị sửa tại chỗ.

### 4.2. Kiểm tra kiểu số và precision

Với `BigDecimal`, kiểm tra:

- Giá trị âm, zero và dương.
- Precision/scale ở biên schema.
- Số có nhiều chữ số thập phân.
- Giá trị vượt scale bị database từ chối hay làm tròn theo quy tắc nào.
- Giá trị null nếu cột nullable.

Không chuyển tiền tệ qua `double` trong test hoặc mapper. So sánh `BigDecimal` theo semantics nghiệp vụ: `compareTo` nếu chỉ quan tâm giá trị số, hoặc `equals` nếu scale cũng là một phần contract.

### 4.3. Kiểm tra thời gian và timezone

Với `Instant`, `OffsetDateTime`, `LocalDateTime` hoặc kiểu temporal khác, test timestamp cụ thể có offset khác UTC và xác nhận round-trip giữ đúng instant theo quy ước schema.

Kiểm tra độ chính xác mà database lưu được. Một số database cắt timestamp xuống microsecond hoặc millisecond; test nên so sánh theo precision thực tế, không giả định nanosecond luôn được giữ.

Đặc biệt test các mốc ngày/giờ gần DST nếu ứng dụng dùng local time theo vùng. `LocalDateTime` không tự mang timezone nên cần quy tắc chuyển đổi rõ ràng.

### 4.4. Kiểm tra null và default

Test riêng các trường hợp:

- Cột được bỏ qua để database áp dụng `DEFAULT`.
- Cột được bind explicit `NULL`.
- Cột `NOT NULL` từ chối null.
- Cột generated/read-only được đọc nhưng không bị ghi từ entity.
- `@InsertOnlyProperty` không bị ghi lại khi update.
- `@Transient` không tham gia persistence.

Không giả định Java null tương đương với bỏ cột khỏi câu insert. Kiểm tra SQL thực tế hoặc kết quả database để xác nhận semantics.

### 4.5. Kiểm tra UUID, enum, JSON, array và binary

Nếu ứng dụng dùng kiểu đặc thù, tạo round-trip test cho từng kiểu và trường hợp biên:

- UUID native hoặc dạng text.
- Enum label thay đổi, giá trị không biết và null.
- JSON object lồng nhau, Unicode, array và null property.
- SQL array có phần tử rỗng hoặc null nếu database hỗ trợ.
- Binary payload rỗng và payload lớn.

Custom converter của Spring Data và codec của driver cần được kiểm tra trên database thật. Converter hoạt động trong Repository không có nghĩa mọi bind thủ công qua `DatabaseClient` tự động dùng cùng conversion path.

### 4.6. Kiểm tra projection và alias

Với query trả DTO/projection, xác nhận alias SQL khớp tên property hoặc mapping function:

```sql
SELECT c.display_name AS customer_name,
       COUNT(o.id) AS order_count
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.display_name
```

Test cả giá trị null từ `LEFT JOIN`, kiểu số của `COUNT`, và trường hợp một khách hàng không có đơn. Alias sai có thể khiến mapping trả null hoặc phát lỗi chỉ ở runtime.

## 5. Kiểm thử auditing và optimistic locking

Nếu entity có `@CreatedBy`, `@LastModifiedBy`, `@CreatedDate`, `@LastModifiedDate` hoặc `@Version`, cần regression test cho vòng đời insert/update.

### 5.1. Auditing

Với `@EnableR2dbcAuditing` và `ReactiveAuditorAware`, xác nhận:

- Insert gán creator và created date.
- Update giữ nguyên creator/created date.
- Update thay last modifier và modified date.
- Anonymous hoặc background job được xử lý theo chính sách.
- Entity bất biến trả về từ `save` chứa metadata mới.

Có thể inject `Clock` cố định để timestamp test không phụ thuộc thời điểm chạy.

### 5.2. Optimistic locking

Với `@Version`, kiểm tra:

- Insert khởi tạo version.
- Update thành công tăng version.
- Hai instance cùng đọc một version: chỉ lần ghi đầu thành công; lần sau phát optimistic locking exception.
- Custom SQL/bulk update có version predicate riêng nếu cần.

Test concurrency phải thực hiện trên database thật và bảo đảm hai entity được đọc trước khi lần ghi đầu xảy ra. Mock exception không chứng minh câu SQL có điều kiện version.

## 6. Kiểm thử transaction và tính toàn vẹn

Một transaction regression test cần kiểm tra trạng thái cuối trong database, không chỉ kiểm tra method phát lỗi.

### 6.1. Kiểm tra commit

Tạo nghiệp vụ gồm nhiều thao tác ghi trong cùng transaction, sau khi publisher hoàn tất thành công, đọc lại từ một transaction/connection khác để xác nhận dữ liệu đã commit.

Ví dụ nghiệp vụ đặt hàng có thể:

1. Trừ hoặc giữ tồn kho.
2. Tạo order.
3. Tạo order lines.
4. Ghi payment intent hoặc trạng thái liên quan.

Test cần xác nhận mọi thay đổi được lưu và liên kết foreign key chính xác.

### 6.2. Kiểm tra rollback khi một bước lỗi

Giả sử bước đầu giữ tồn kho thành công nhưng bước tạo order vi phạm constraint. Nếu các bước nằm trong cùng transaction, trạng thái tồn kho phải được rollback.

```java
@Transactional
public Mono<OrderEntity> placeOrder(OrderCommand command) {
    return inventoryRepository.reserve(command.items())
            .then(orderRepository.save(toOrder(command)))
            .flatMap(order -> orderLineRepository.saveAll(
                    toLines(order, command.items())).then(Mono.just(order)));
}
```

Integration test nên cố ý làm một bước sau thất bại, rồi đọc lại inventory/order từ một transaction độc lập để xác nhận không có ghi một phần.

Không nuốt lỗi bằng `onErrorResume` bên trong transaction nếu nghiệp vụ yêu cầu rollback. Khi lỗi được biến thành completion bình thường trước transaction boundary, transaction manager có thể không nhận được error signal để rollback như mong muốn.

### 6.3. Kiểm tra isolation và concurrency

Với nghiệp vụ phụ thuộc isolation, tạo hai transaction riêng và điều phối thứ tự đọc/ghi. Kiểm tra hiện tượng mà hệ thống cần ngăn:

- Lost update.
- Double booking hoặc oversell.
- Duplicate insert.
- Đọc dữ liệu chưa commit nếu database/isolation cho phép.
- Serialization failure hoặc deadlock được xử lý đúng.

Không chạy hai query song song trên cùng transaction connection nếu driver không hỗ trợ concurrent statement. Dùng hai transaction/connection riêng để mô phỏng hai request độc lập.

### 6.4. Kiểm tra transaction context trong Reactor

Các thao tác R2DBC cần nằm trong cùng reactive pipeline để transaction manager truyền context. Không gọi `subscribe()` hoặc `block()` nội bộ để tách thao tác ra khỏi transaction.

Test nên xác nhận thao tác ghi lồng nhau rollback cùng nhau khi lỗi, và thao tác được tạo từ subscription độc lập không vô tình tham gia transaction hiện tại.

### 6.5. Kiểm tra cancellation

Nếu request bị hủy hoặc client disconnect, xác định query/transaction được xử lý thế nào. Kiểm tra connection có được trả lại pool, transaction có rollback khi chưa commit và không có tác vụ ghi nền tiếp tục ngoài ý muốn.

Cancellation behavior phụ thuộc driver và database; không giả định hủy subscription luôn dừng ngay statement phía server. Với nghiệp vụ ghi quan trọng, thiết kế idempotency và trạng thái thao tác rõ ràng.

## 7. Kiểm thử SQL sinh ra và query plan

Không phải lúc nào cũng nên assert toàn bộ chuỗi SQL chính xác vì alias, thứ tự cột hoặc cách quote có thể thay đổi giữa phiên bản framework. Thay vào đó, kiểm tra behavior và các đặc tính quan trọng của query.

### 7.1. Khi nào cần kiểm tra SQL text?

SQL text assertion hữu ích khi:

- Query là SQL tùy chỉnh quan trọng.
- Cần bảo đảm có predicate tenant hoặc optimistic version.
- Cần xác nhận `LIMIT/OFFSET`, `ORDER BY` hoặc điều kiện cursor.
- Một thay đổi framework có thể làm biến đổi cú pháp quan trọng.

Giữ assertion ở mức cấu trúc cần thiết, tránh khóa test vào whitespace hoặc alias không có ý nghĩa. Tốt hơn nữa, chạy query trên database và xác nhận kết quả để chứng minh semantics.

### 7.2. Thu thập SQL trong test

Có thể bật logging phù hợp cho driver/framework hoặc dùng proxy/observability instrumentation để quan sát query. Tránh log bind values nhạy cảm trong CI hoặc production. Với test cần xác nhận số query, dùng instrumentation/spy ở tầng phù hợp và phân biệt query chính với query do fixture/health check tạo ra.

### 7.3. EXPLAIN và EXPLAIN ANALYZE

Với PostgreSQL, `EXPLAIN` cho biết kế hoạch dự kiến; `EXPLAIN ANALYZE` thực thi query và báo số liệu thực tế. Các database khác có cú pháp và công cụ tương đương.

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_code, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

Khi xem plan, chú ý:

- Sequential scan hay index scan có phù hợp với độ chọn lọc không?
- Số hàng ước lượng có lệch lớn so với số hàng thực tế không?
- Join strategy có tạo nhiều hàng trung gian không?
- Có sort tốn kém hoặc spill ra disk không?
- Buffer reads và thời gian thực thi thay đổi thế nào?
- Index được dùng có đúng thứ tự cột với predicate và sort không?

Không yêu cầu mọi query phải dùng index. Với bảng nhỏ hoặc predicate trả phần lớn hàng, sequential scan có thể là lựa chọn tối ưu. Regression test cần theo dõi kế hoạch và chi phí trong bối cảnh dữ liệu thực, không assert máy móc tên một node.

### 7.4. Query plan thay đổi theo thống kê và dữ liệu

Query plan phụ thuộc statistics, parameter distribution, database version, cache và tải hệ thống. Một plan khác không luôn có nghĩa regression. Hãy so sánh actual rows, buffer, execution time và workload. Sau khi nạp fixture lớn, cập nhật statistics theo cách database yêu cầu trước khi đo.

## 8. Thiết kế performance regression test

Performance test cần trả lời một câu hỏi cụ thể: thay đổi này có làm query hoặc luồng nghiệp vụ chậm hơn vượt ngưỡng chấp nhận không?

### 8.1. Chọn chỉ số phù hợp

| Chỉ số | Ý nghĩa | Khi hữu ích |
|---|---|---|
| Throughput | Số request/query hoàn tất mỗi giây | So sánh năng lực xử lý tổng thể |
| p50 latency | Thời gian của request ở trung vị | Đánh giá trải nghiệm điển hình |
| p95/p99 latency | Độ trễ ở phần đuôi | Phát hiện query chậm hoặc pool contention |
| Error rate | Tỷ lệ lỗi/timeout | Phát hiện quá tải hoặc lỗi driver |
| Connection acquire latency | Thời gian chờ lấy connection | Phân biệt nghẽn pool với query chậm |
| Active/pending connections | Mức sử dụng và hàng đợi pool | Đánh giá concurrency và pool sizing |
| Rows scanned/returned | Công việc database thực hiện | Phát hiện query đọc quá nhiều hàng |
| CPU, I/O, buffer reads | Chi phí database | Phát hiện plan hoặc workload nặng |
| Allocation/heap | Chi phí ứng dụng | Phát hiện materialize quá nhiều dữ liệu |

Không chỉ đo average latency. Một query có average tốt nhưng p99 tăng mạnh vẫn có thể làm API timeout khi tải cao.

### 8.2. Tạo baseline

Trước khi thay đổi query hoặc mapping, chạy workload chuẩn trên cùng database version, dataset, cấu hình pool và tài nguyên tương đương. Lưu:

- Commit/build version.
- Database và driver version.
- Số hàng và phân bố dữ liệu.
- Query parameters và tỷ lệ từng loại request.
- Pool size và concurrency.
- Warm-up duration và measurement duration.
- Throughput, latency percentiles, error rate và database metrics.

Baseline chỉ có ý nghĩa nếu điều kiện so sánh tương đương. So sánh một lần chạy local trên laptop với một lần CI trên máy khác thường không đủ để kết luận regression.

### 8.3. Warm-up và nhiều lần chạy

JIT compilation, connection pool warm-up, prepared statement cache và database buffer cache có thể làm những request đầu chậm hơn. Tách giai đoạn warm-up khỏi measurement. Chạy nhiều iteration và xem median hoặc phân phối thay vì dựa vào một con số duy nhất.

Không xóa cache giữa mỗi request nếu production giữ cache nóng; ngược lại, nếu workload production thường xuyên chạy cold start, hãy có kịch bản cold-start riêng.

### 8.4. Kiểm soát concurrency và tải

Performance test nên mô phỏng mức tải thực tế:

- Số request đồng thời.
- Tỷ lệ đọc/ghi.
- Kích thước page/batch.
- Tỷ lệ cache hit nếu có.
- Query có join/aggregate.
- Các transaction giữ connection lâu.

Không dùng `flatMap` không giới hạn trong test rồi kết luận database chậm do driver. Cần phân biệt concurrency của test harness, concurrency trong reactive pipeline và giới hạn pool.

### 8.5. Đặt ngưỡng regression có ý nghĩa

Ví dụ tiêu chí:

- p95 không tăng quá 15% so với baseline trong cùng môi trường.
- Error rate không vượt ngưỡng được xác định.
- Query không đọc số hàng lớn hơn nhiều so với kết quả cần thiết.
- Pending connection không tăng liên tục ở tải mục tiêu.
- Throughput không giảm quá mức chấp nhận.

Các con số phải được xác định từ SLO và độ nhiễu của môi trường, không sao chép mặc định. Với benchmark nhiễu, có thể dùng nhiều lần chạy, khoảng tin cậy hoặc so sánh phân phối.

## 9. Phát hiện N+1 và số query bất thường

Một thay đổi nhỏ trong service có thể vô tình biến một query join thành nhiều query theo từng hàng.

Ví dụ:

```java
return orderRepository.findAllByStatus("PAID")
        .flatMap(order -> customerRepository.findById(order.customerId())
                .map(customer -> OrderView.from(order, customer)));
```

Nếu có 100 đơn, code có thể thực hiện một query lấy orders và khoảng 100 query lấy customer. Đây là N+1 pattern.

Regression test có thể kiểm tra số query cho một kịch bản fixture cố định:

- Với một query join/projection, số query cần thiết vẫn ở mức dự kiến.
- Khi số order tăng từ 10 lên 100, số query không tăng tuyến tính ngoài chủ đích.
- Nếu dùng batch lookup, số query tăng theo số batch chứ không theo từng entity.

Đếm query cần loại trừ query setup, transaction metadata hoặc health check. Có thể dùng datasource/driver instrumentation hoặc query log trong test để thu thập. Không khóa test vào một số query tuyệt đối nếu framework có thể thay đổi một query phụ hợp lệ; hãy định nghĩa ngân sách query theo use case.

## 10. Kiểm tra connection pool và resource usage

Một query có thể nhanh trong điều kiện đơn lẻ nhưng timeout khi nhiều request cùng chạy vì pool bị bão hòa.

Regression suite hoặc performance test nên quan sát:

- Active/allocated connection.
- Idle connection.
- Pending acquire.
- Acquire latency và timeout count.
- Connection creation time.
- Thời gian transaction giữ connection.
- Số connection tối đa so với ngân sách database.

Kịch bản tải cần xác nhận:

1. Pool không cấp quá `max-size`.
2. Query hoàn tất hoặc bị hủy thì connection được trả lại.
3. Tải vượt pool được xử lý theo timeout/backpressure đã thiết kế.
4. Không có pending acquire tăng vô hạn.
5. Transaction dài không chiếm hết connection của traffic thông thường.

Không tăng `max-size` chỉ để làm test pass. Nếu database CPU, I/O hoặc lock đã bão hòa, pool lớn hơn có thể làm p99 tệ hơn.

## 11. Kiểm thử bằng StepVerifier

`StepVerifier` thuộc `reactor-test`, giúp subscribe publisher và xác nhận signal theo thứ tự.

### 11.1. Kiểm tra Mono thành công

```java
StepVerifier.create(customerRepository.findByEmail("an@example.test"))
        .assertNext(customer -> {
            assertThat(customer.email()).isEqualTo("an@example.test");
        })
        .verifyComplete();
```

### 11.2. Kiểm tra Flux và số phần tử

```java
StepVerifier.create(orderRepository.findByStatus("PAID"))
        .expectNextCount(2)
        .verifyComplete();
```

Nếu thứ tự là một phần contract, hãy kiểm tra từng phần tử theo đúng thứ tự thay vì chỉ `expectNextCount`.

### 11.3. Kiểm tra lỗi

```java
StepVerifier.create(orderService.updateWithStaleVersion(command))
        .expectError(OptimisticLockingFailureException.class)
        .verify();
```

Kiểm tra cả loại lỗi và trạng thái database sau lỗi. Với exception được map sang domain exception, xác nhận cause được giữ nếu đó là contract chẩn đoán.

### 11.4. Kiểm tra timeout và cancellation

`StepVerifier` có thể đặt timeout cho verification để test không treo vô hạn. Với cancellation, dùng `thenCancel()` và sau đó kiểm tra tài nguyên/transaction đã được giải phóng qua instrumentation hoặc truy vấn độc lập.

Timeout trong test là hàng rào bảo vệ suite; nó không tự chứng minh query timeout ở production đã cấu hình đúng.

### 11.5. Không gọi subscribe trong test để bỏ qua assertion

Nếu gọi `.subscribe()` rồi kết thúc test ngay, test có thể hoàn tất trước publisher và bỏ lỡ lỗi bất đồng bộ. Dùng `StepVerifier` hoặc kết hợp publisher thành một scenario duy nhất mà test có thể đợi và kiểm tra.

## 12. Tổ chức test suite và tên test

Nên đặt test theo hành vi và tầng:

```text
src/test/java/
  .../repository/
    CustomerRepositorySqlTest.java
    OrderRepositoryPagingTest.java
    OrderProjectionMappingTest.java
  .../transaction/
    OrderTransactionIntegrationTest.java
    OptimisticLockingIntegrationTest.java
  .../performance/
    OrderSearchPerformanceTest.java
  .../migration/
    SchemaMigrationCompatibilityTest.java
```

Không nhất thiết phải chia đúng cấu trúc này. Điều quan trọng là test có tên mô tả hành vi, fixture và môi trường rõ ràng. Performance test có thể được đặt trong source set hoặc pipeline riêng để không làm chậm mọi lần chạy unit test.

### 12.1. Chia tầng chạy trong CI

Một pipeline có thể chia:

| Stage | Nội dung | Khi chạy |
|---|---|---|
| Fast tests | Unit test, validation, mapping function thuần Java | Mỗi commit |
| Database integration | Repository SQL, mapping, constraints | Mỗi PR hoặc commit chính |
| Transaction suite | Rollback, isolation, optimistic locking | Mỗi PR quan trọng hoặc nightly tùy chi phí |
| Migration suite | Database rỗng và upgrade từ schema cũ | Mỗi PR thay schema |
| Performance suite | Baseline, query plan, load profile | Nightly, trước release hoặc khi query trọng yếu đổi |

Không trì hoãn test SQL quan trọng tới sau merge nếu thay đổi query có rủi ro cao. Tần suất phụ thuộc thời gian chạy và mức độ critical của chức năng.

### 12.2. Cô lập test song song

Nếu nhiều test cùng dùng một database, tránh `TRUNCATE` toàn bảng trong khi test khác đang chạy. Dùng container/database/schema riêng, fixture key riêng hoặc tắt parallel cho nhóm test có cleanup toàn cục.

Mỗi test cần biết ai sở hữu dữ liệu và cách dọn dữ liệu. Không dùng chung natural key nếu test chạy song song trên cùng schema.

## 13. Kiểm thử migration và schema compatibility

Thay đổi entity hoặc query thường đi cùng migration. Regression suite nên kiểm tra:

- Toàn bộ migration chạy được từ database rỗng.
- Migration mới nâng cấp được schema phiên bản trước.
- Dữ liệu cũ được backfill chính xác.
- Code cũ vẫn chạy trên schema mở rộng trong rolling deployment nếu cần.
- Code mới hoạt động trên schema sau expand.
- Contract migration chỉ chạy sau khi không còn consumer dùng cấu trúc cũ.

Với migration phá vỡ, dùng expand-and-contract và test các giai đoạn thay vì chỉ test trạng thái cuối. Một test chỉ chạy code mới trên schema mới không phát hiện được việc instance cũ bị hỏng giữa rolling deployment.

## 14. SQL query plan và performance baseline trong CI

Performance test trong CI cần cân bằng giữa tính ổn định và khả năng phát hiện regression.

### 14.1. Không dùng threshold quá sát

Thời gian query phụ thuộc CPU chia sẻ, disk, cache, container runtime và tải CI. Nếu threshold quá sát, suite sẽ flaky. Chọn ngưỡng đủ rộng để bỏ qua nhiễu nhỏ nhưng vẫn phát hiện regression đáng kể.

### 14.2. Tách benchmark khỏi correctness test

Correctness test nên ổn định, có assertion chính xác và chạy thường xuyên. Benchmark có thể chạy ít thường xuyên hơn, trên môi trường kiểm soát tốt hơn và lưu kết quả để so sánh qua nhiều build.

Không biến một test latency 20 ms thành gate bắt buộc trên runner chia sẻ nếu độ biến động môi trường lớn hơn chênh lệch cần phát hiện.

### 14.3. Lưu kết quả có metadata

Mỗi benchmark report nên lưu:

- Git commit/build ID.
- Database/driver/framework version.
- Dataset size và seed.
- Hardware/container limits.
- Pool size và concurrency.
- Warm-up và measurement duration.
- Throughput, p50/p95/p99, error rate.
- Query plan hoặc plan summary nếu phù hợp.

Nếu thiếu metadata, so sánh hai con số latency có thể dẫn tới kết luận sai.

### 14.4. Dùng query plan như bằng chứng bổ sung

Lưu plan cho query trọng yếu có thể giúp phát hiện index bị bỏ qua hoặc join order thay đổi. Nhưng plan phụ thuộc statistics và server version; không nên so sánh raw text một cách máy móc. Hãy tập trung vào actual rows, buffers, sort spill và các thay đổi chi phí đáng kể.

## 15. Ví dụ: regression suite cho truy vấn tìm kiếm đơn hàng

Giả sử use case tìm kiếm đơn hàng có:

- Tenant bắt buộc.
- Status và khoảng thời gian tùy chọn.
- Tên khách hàng từ join.
- Số dòng hàng và tổng tiền.
- Sort theo thời điểm tạo mới nhất.
- Offset pagination và count tổng.

Một bộ test có thể gồm:

| Test | Dữ liệu/điều kiện | Assertion chính |
|---|---|---|
| Tenant isolation | Hai tenant có đơn cùng status | Không trả đơn tenant khác |
| Optional filters | Status/time có hoặc không | Tập kết quả đúng từng tổ hợp |
| Join cardinality | Đơn có 0, 1 và nhiều dòng | Mỗi đơn chỉ xuất hiện một lần |
| Aggregate mapping | quantity × unit_price | `totalAmount` đúng kiểu và giá trị |
| Paging | Nhiều đơn cùng timestamp | Không lặp/thiếu trong dataset tĩnh; sort có ID tie-breaker |
| Count | Join một-nhiều | Total đếm đơn logic, không đếm dòng hàng |
| Empty result | Không có đơn thỏa filter | Content rỗng, total bằng 0 |
| SQL injection | Input chứa ký tự SQL | Không thay đổi cấu trúc query |
| Query budget | Dataset lớn hơn | Không phát sinh N+1 |
| Performance | Tải mục tiêu | p95/p99 và acquire latency trong ngưỡng |

Test nên xác nhận cả response DTO lẫn database state khi nghiệp vụ có ghi. Với query chỉ đọc, xác nhận đúng tập dữ liệu và query budget có thể đủ.

## 16. Ví dụ: regression suite cho transaction đặt hàng

Một use case đặt hàng có thể giữ tồn kho, tạo order và order lines trong một transaction. Các test quan trọng:

1. **Happy path:** tất cả thao tác commit và dữ liệu liên kết đúng.
2. **Constraint failure:** order line không hợp lệ làm toàn bộ transaction rollback.
3. **Insufficient inventory:** không tạo order nếu không giữ được tồn kho.
4. **Concurrent requests:** hai request không thể cùng bán vượt tồn kho.
5. **Optimistic conflict:** cập nhật dựa trên version cũ thất bại có kiểm soát.
6. **Cancellation:** request bị hủy trước commit không để lại dữ liệu một phần theo contract.
7. **Retry:** chỉ retry lỗi tạm thời và không tạo đơn trùng.

Đặc biệt với double booking/oversell, test cần điều phối hai transaction cạnh tranh trên database thật. Test tuần tự không phát hiện được race condition.

## 17. Đánh giá kết quả regression

Khi một test thất bại, cần phân loại nguyên nhân thay vì chỉ sửa assertion để suite xanh trở lại.

| Dấu hiệu | Vùng cần kiểm tra |
|---|---|
| Sai tập dữ liệu | Predicate, tenant scope, join, null semantics |
| Sai thứ tự | `ORDER BY`, tie-breaker, collation, cursor |
| Sai total | Count query, distinct, group by, having |
| Mapping null hoặc sai kiểu | Alias, converter, driver codec, schema type |
| Timestamp lệch | Timezone, precision, session settings |
| Rollback không đầy đủ | Transaction boundary, nested subscription, error recovery |
| Lost update | `@Version`, predicate update, isolation |
| Test timeout khi tải | Pool acquire, query latency, lock wait, concurrency |
| Query plan xấu đi | Index, statistics, predicate, cardinality estimate |
| N+1 | Fan-out trong `flatMap`, lazy follow-up query, projection |

Nếu test mới phát hiện lỗi đã tồn tại trước thay đổi, ghi nhận như defect riêng và xác định phạm vi sửa. Không xóa test chỉ vì nó làm lộ hành vi cũ không đúng mong đợi.

## 18. Các lỗi thường gặp khi lập regression suite

### Chỉ test repository bằng mock

Mock không chạy SQL và không kiểm tra mapping, constraint, dialect hoặc driver. Dùng mock cho unit test, nhưng cần integration test trên database thật.

### Dùng database khác production

Hành vi SQL, data type và transaction có thể khác. Dùng Testcontainers hoặc database integration đúng hệ quản trị.

### Fixture quá nhỏ và không đại diện

Dataset vài hàng không làm lộ full scan, N+1 hoặc paging trên dữ liệu lớn. Tạo dataset performance riêng có phân bố gần workload.

### Chỉ kiểm tra giá trị trả về

Một method có thể trả đúng response nhưng ghi sai dữ liệu hoặc commit một phần. Đọc lại database để xác nhận trạng thái cuối cho use case ghi.

### Chỉ kiểm tra average latency

Average che khuất tail latency. Theo dõi p95/p99, error rate và acquire latency.

### Assertion query plan quá cứng

Plan có thể thay đổi hợp lệ theo statistics hoặc server version. Kiểm tra chi phí và đặc tính quan trọng thay vì assert toàn bộ chuỗi plan.

### Dùng transaction test rollback cho mọi kịch bản

Một số test cần quan sát commit, nhiều connection hoặc concurrency. Transaction test bọc toàn bộ scenario có thể làm sai hành vi cần kiểm tra.

### Chạy cleanup toàn bảng song song

Test khác có thể mất fixture hoặc nhận dữ liệu thay đổi giữa chừng. Cô lập database/schema hoặc dùng fixture key riêng.

### Gọi subscribe để test kết thúc nhanh

Test có thể kết thúc trước publisher và bỏ lỡ lỗi. Dùng `StepVerifier` hoặc kết hợp publisher.

### Không kiểm tra generated values và null semantics

ID, default, computed column, timestamp và explicit null thường phụ thuộc database/driver. Thêm integration test riêng.

### Không lưu baseline và môi trường benchmark

Con số latency không có metadata không thể so sánh đáng tin cậy. Ghi lại phiên bản, dataset, pool, concurrency và cấu hình runner.

## 19. Quy trình xây dựng regression suite

1. Liệt kê các query và use case persistence quan trọng nhất.
2. Ghi contract cho predicate, join, sort, paging, aggregate và count.
3. Xác định entity/projection cùng các kiểu dữ liệu cần kiểm tra.
4. Xác định transaction boundary, rollback, isolation và concurrency invariant.
5. Chọn database/driver version gần production và pin môi trường test.
6. Tạo schema bằng migration/SQL initialization và fixture xác định.
7. Viết repository integration test bằng `StepVerifier`.
8. Viết mapping round-trip test cho kiểu dữ liệu, null, default và generated values.
9. Viết transaction/concurrency test trên nhiều connection khi cần.
10. Kiểm tra query count để phát hiện N+1 và query budget bất thường.
11. Thu thập query plan cho SQL trọng yếu với dataset đại diện.
12. Tạo performance baseline và chọn ngưỡng theo SLO/độ nhiễu môi trường.
13. Tách fast test, integration, migration và performance stage trong CI.
14. Cô lập fixture khi chạy song song và bảo đảm cleanup sau cả success lẫn failure.
15. Lưu kết quả, metadata môi trường và phân loại regression khi test thất bại.

## 20. Checklist regression trước khi phát hành

- [ ] SQL filter, join, sort, paging và aggregate có test trên database mục tiêu.
- [ ] Tenant predicate và authorization scope được kiểm tra bằng fixture nhiều tenant.
- [ ] Count query đếm đúng entity hoặc nhóm logic.
- [ ] Null, empty collection, explicit null và database default có test riêng.
- [ ] Generated ID, generated column và trigger values được xác nhận.
- [ ] Decimal precision, temporal timezone và custom types được round-trip test.
- [ ] Projection alias và nullable join result được kiểm tra.
- [ ] Không có N+1 ngoài query budget đã xác định.
- [ ] Transaction commit và rollback được kiểm tra bằng cách đọc trạng thái database cuối.
- [ ] Concurrency test bao phủ lost update, oversell hoặc invariant quan trọng.
- [ ] Reactive pipeline không tạo nested subscription làm tách transaction/context.
- [ ] Cancellation và connection cleanup được kiểm tra nếu use case cần.
- [ ] Query plan và index của query trọng yếu đã được xem xét.
- [ ] Performance baseline có dataset, version, pool và concurrency metadata.
- [ ] p95/p99, throughput, error rate và acquire latency nằm trong ngưỡng.
- [ ] Testcontainers/database image và dependency version được pin.
- [ ] Fixture deterministic và test có thể chạy lại độc lập.
- [ ] Test song song không chia sẻ cleanup hoặc fixture key nguy hiểm.
- [ ] Migration từ schema rỗng và schema phiên bản trước được kiểm tra.
- [ ] CI lưu kết quả test/benchmark đủ thông tin để so sánh và điều tra.

Một regression suite R2DBC tốt phải chứng minh cả correctness lẫn khả năng vận hành. Test SQL và mapping trên database thật phát hiện sai lệch giữa entity, driver và schema; test transaction/concurrency xác nhận tính toàn vẹn khi có lỗi hoặc nhiều request đồng thời; performance baseline và query plan phát hiện thay đổi làm tăng chi phí truy vấn. Khi fixture xác định, môi trường được pin và kết quả có metadata, bộ test có thể trở thành hàng rào đáng tin cậy cho mỗi thay đổi persistence trước khi phát hành.
