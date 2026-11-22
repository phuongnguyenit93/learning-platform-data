# Đánh giá ứng dụng JDBC/JPA trước khi chuyển sang R2DBC

## 1. Vì sao phải đánh giá trước khi chuyển đổi?

Chuyển một ứng dụng đang dùng JDBC hoặc JPA sang Spring Data Relational R2DBC là thay đổi kiến trúc truy cập dữ liệu, không chỉ là thay dependency hoặc đổi repository interface. JDBC dùng mô hình I/O blocking; R2DBC cung cấp API truy cập database theo Reactive Streams. JPA còn bổ sung một mô hình ORM với persistence context, dirty checking, lazy loading, cascade và nhiều cơ chế quản lý entity.

Một ứng dụng có thể chạy tốt với JDBC/JPA trong nhiều năm. Nếu workload không bị giới hạn bởi thread chờ database, nếu team không cần reactive end-to-end hoặc nếu ứng dụng phụ thuộc sâu vào tính năng ORM, chuyển sang R2DBC có thể làm tăng độ phức tạp mà không đem lại lợi ích tương xứng.

Đánh giá trước migration giúp trả lời:

- Vấn đề hiện tại có thực sự đến từ mô hình blocking của JDBC không?
- Ứng dụng có đang sử dụng những tính năng JPA mà R2DBC không cung cấp tương đương không?
- Các query, transaction, locking và batch hiện tại có thể biểu diễn bằng R2DBC không?
- Các thư viện ngoài database có hỗ trợ reactive hay vẫn blocking?
- Team có đủ năng lực thiết kế, vận hành và debug reactive pipeline không?
- Phần nào nên chuyển, phần nào nên giữ JDBC/JPA?
- Có thể triển khai theo từng use case mà không làm gián đoạn hệ thống không?

Kết quả assessment không nhất thiết phải là “chuyển toàn bộ”. Có thể chọn chuyển một số luồng có lợi ích rõ, giữ các luồng reporting hoặc batch trên JDBC, hoặc chưa chuyển nếu lợi ích không đủ bù chi phí.

## 2. Phân biệt JDBC, JPA và R2DBC

Ba công nghệ này giải quyết các lớp vấn đề khác nhau:

| Công nghệ | Vai trò chính | Đặc điểm |
|---|---|---|
| JDBC | API truy cập database chuẩn của Java | Blocking; thao tác thường chờ kết quả trên thread gọi |
| JPA | Đặc tả ORM và quản lý persistence | Thường chạy trên JDBC; có persistence context, dirty checking, entity lifecycle và relationship mapping |
| Spring Data JPA | Abstraction repository trên JPA | Cung cấp repository, query derivation và tích hợp với EntityManager |
| R2DBC | SPI truy cập database reactive | Non-blocking API dựa trên Publisher |
| Spring Data R2DBC | Mapping relational và repository reactive | Dùng ConnectionFactory, MappingR2dbcConverter, DatabaseClient và R2dbcEntityTemplate |

JPA không phải driver database. Một ứng dụng Spring Data JPA thường dùng Hibernate hoặc provider khác ở trên JDBC. Khi chuyển sang Spring Data R2DBC, ứng dụng thường bỏ mô hình EntityManager/JPA và làm việc trực tiếp hơn với relational mapping.

Điều đó có nghĩa là không có phép thay thế một-một cho mọi hành vi JPA. R2DBC không tự cung cấp persistence context kiểu JPA, lazy-loading proxy, dirty checking hoặc cascade operation tự động theo object graph.

Nếu ứng dụng chỉ dùng JdbcTemplate hoặc JDBC DAO, assessment tập trung nhiều hơn vào blocking calls, transaction, SQL, row mapping, batch và connection lifecycle. Nếu ứng dụng dùng JPA sâu, cần kiểm kê thêm các semantics ORM và hành vi phụ thuộc provider.

## 3. R2DBC giải quyết vấn đề nào?

JDBC blocking có thể giữ một thread trong thời gian chờ database trả kết quả. Trong ứng dụng có nhiều request đồng thời, số thread và bộ nhớ stack có thể tăng theo lượng công việc đang chờ I/O. Connection pool và thread pool cần được cấu hình để tránh cạn tài nguyên.

R2DBC cho phép ứng dụng gửi thao tác database và tiếp tục xử lý tín hiệu khi kết quả sẵn sàng mà không phải giữ một thread blocking cho mỗi lần chờ I/O. Mô hình này phù hợp với ứng dụng đã sử dụng reactive stack như WebFlux, Reactor và Reactive Streams.

R2DBC có thể hữu ích khi:

- Có nhiều request đồng thời và phần lớn thời gian chờ database/network.
- Ứng dụng cần xử lý stream dữ liệu theo backpressure.
- Stack HTTP, messaging và downstream đã reactive.
- Thread blocking là một nút thắt được đo và chứng minh.
- Driver R2DBC của database hỗ trợ các tính năng cần thiết.
- Team có thể duy trì reactive programming đúng cách.

R2DBC không tự làm câu SQL nhanh hơn. Database vẫn thực thi query, kiểm tra constraint, lấy lock và đọc/ghi storage như trước. Một query chậm vẫn chậm; một transaction giữ connection quá lâu vẫn gây áp lực lên pool. Nếu ứng dụng bị giới hạn bởi CPU, index thiếu, query kém hoặc database saturation, chuyển driver không giải quyết nguyên nhân gốc.

## 4. Bắt đầu bằng mục tiêu và baseline

Trước khi đánh giá code, hãy xác định vấn đề kinh doanh hoặc vận hành mà migration cần giải quyết. Tránh bắt đầu bằng mục tiêu chung chung như “muốn dùng reactive”.

Các câu hỏi nên trả lời:

- Request rate trung bình và peak là bao nhiêu?
- Số request đồng thời và p95/p99 latency hiện tại?
- Bao nhiêu thời gian request nằm trong database call?
- Thread pool có bị cạn hoặc có nhiều thread chờ JDBC không?
- Connection pool có pending acquire hoặc timeout không?
- Database CPU, memory, I/O và active session đang ở mức nào?
- Có nhiều thao tác I/O khác như HTTP, Redis, Kafka hoặc file không?
- Phần nào trong request là CPU-bound và phần nào I/O-bound?
- Mục tiêu sau migration là tăng concurrency, giảm tài nguyên, cải thiện tail latency hay thống nhất reactive stack?

Thiết lập baseline trước khi thay đổi:

| Nhóm | Chỉ số nên thu thập |
|---|---|
| HTTP/API | Request rate, p50/p95/p99, error rate |
| JVM | Thread count, heap, GC pause, CPU |
| JDBC pool | Active, idle, pending, acquire latency, timeout |
| Database | Active sessions, query latency, CPU, I/O, lock wait |
| Query | Slow query, rows read/returned, execution plan |
| Transaction | Duration, rollback rate, lock duration |
| Batch | Batch size, throughput, thời gian hoàn tất |

Baseline cần được đo với workload đại diện và khoảng thời gian đủ dài. Nếu không có số liệu trước migration, sẽ khó chứng minh R2DBC cải thiện điều gì sau khi triển khai.

## 5. Lập inventory các điểm truy cập database

Tạo danh sách tất cả thành phần truy cập database, không chỉ repository interface.

Nguồn cần tìm trong codebase:

- Spring Data JPA repository.
- EntityManager và Criteria API.
- JdbcTemplate và NamedParameterJdbcTemplate.
- JdbcClient ở các phiên bản Spring hỗ trợ.
- DataSource và DriverManager.
- Hibernate Session, query API hoặc native SQL.
- Stored procedure và function.
- Batch update/insert.
- JDBC trực tiếp trong thư viện nội bộ.
- Database access bên trong scheduler, listener và background worker.
- Transaction manager và annotation transaction.
- Migration tool và schema initializer.

Có thể phân loại theo module/use case:

| Module | Công nghệ hiện tại | Số query/luồng | Mức độ phức tạp | Tầm quan trọng |
|---|---|---:|---|---|
| Customer API | Spring Data JPA | 18 | Trung bình | Cao |
| Reporting | JdbcTemplate/native SQL | 30 | Cao | Trung bình |
| Import worker | JDBC batch | 5 | Cao | Cao |
| Reference data | Spring Data JPA | 6 | Thấp | Thấp |

Bảng chỉ là mẫu inventory. Hãy ghi rõ query quan trọng, tần suất gọi, số hàng, transaction boundary và những feature database đang sử dụng.

Không dựa vào số lượng repository method để đánh giá độ khó. Một method dùng native SQL phức tạp hoặc dựa vào locking có thể khó chuyển hơn hàng chục CRUD method.

## 6. Kiểm kê tính năng JPA đang được sử dụng

Nếu ứng dụng dùng JPA, cần rà soát các tính năng sau:

| Tính năng JPA | Câu hỏi cần đặt ra khi chuyển sang R2DBC |
|---|---|
| Persistence context | Code có dựa vào EntityManager theo dõi entity không? |
| Dirty checking | Có sửa property rồi mong tự động UPDATE khi commit không? |
| Lazy loading | Có truy cập association sau khi query entity không? |
| Eager relationship | Có dựa vào fetch tự động để lấy object graph không? |
| Cascade | Có lưu/xóa object graph bằng một thao tác không? |
| Orphan removal | Có dựa vào việc bỏ phần tử khỏi collection để xóa row không? |
| Entity lifecycle callback | Có dùng @PrePersist, @PostLoad hoặc listener không? |
| Auditing | Có dùng auditing listener/provider của Spring Data JPA không? |
| Entity graph | Có dùng @EntityGraph hoặc fetch plan không? |
| JPQL/HQL | Có query dựa vào entity name và association không? |
| Criteria API/Specification | Có query động dựa trên object model JPA không? |
| Pessimistic/optimistic locking | Có dùng LockModeType hoặc @Version không? |
| First-level cache | Có dựa vào cùng entity instance trong một persistence context không? |
| Second-level/query cache | Có dùng Hibernate cache không? |
| Inheritance mapping | Có dùng JOINED, SINGLE_TABLE hoặc TABLE_PER_CLASS không? |
| Embedded/value mapping | Có dùng @Embedded, @ElementCollection hoặc converter phức tạp không? |

Không phải tính năng nào cũng có bản tương đương trực tiếp trong Spring Data R2DBC. Một số phải chuyển thành SQL tường minh, service orchestration hoặc thiết kế schema/domain khác.

Nếu một use case phụ thuộc nhiều vào persistence context, lazy loading và cascade, chi phí chuyển đổi có thể lớn. Cần prototype use case đó trước khi quyết định migration diện rộng.

## 7. Persistence context và dirty checking

JPA EntityManager duy trì persistence context. Entity được load trong context có thể được theo dõi; khi property thay đổi, provider phát hiện thay đổi và tạo UPDATE khi flush hoặc commit.

Ví dụ JPA:

~~~java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName(newName);
    // Dirty checking có thể phát UPDATE khi flush/commit.
}
~~~

Spring Data R2DBC không có persistence context kiểu JPA để theo dõi mọi object đã đọc. Thay đổi một object trong bộ nhớ không tự động ghi xuống database.

Với R2DBC, thường phải thể hiện thao tác ghi rõ:

~~~java
public Mono<Customer> renameCustomer(Long id, String newName) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)
            ))
            .map(customer -> customer.withName(newName))
            .flatMap(customerRepository::save);
}
~~~

Với immutable entity, phương thức withName tạo instance mới. Service gọi save để phát sinh UPDATE. Đây là thay đổi quan trọng trong cách nghĩ: đọc entity không đăng ký nó vào một context theo dõi thay đổi.

Trong assessment, tìm các service method chỉ sửa property mà không gọi save/merge/update tường minh. Chúng sẽ không giữ nguyên hành vi khi chuyển sang R2DBC.

## 8. Lazy loading và object graph

JPA có thể dùng proxy hoặc collection wrapper để tải association khi code truy cập. Một đoạn code có thể trông đơn giản:

~~~java
@Transactional
public CustomerProfile getProfile(Long id) {
    Customer customer = customerRepository.findById(id).orElseThrow();
    List<Address> addresses = customer.getAddresses();
    return new CustomerProfile(customer, addresses);
}
~~~

Nếu addresses là LAZY, việc gọi getter có thể kích hoạt query bổ sung trong lúc persistence context còn mở. Điều này đôi khi tạo N+1 query mà code không thể hiện rõ.

R2DBC không cung cấp lazy-loading proxy cho association như JPA. Ứng dụng phải quyết định dữ liệu nào cần lấy và kết hợp publisher/query tường minh.

Ví dụ:

~~~java
public Mono<CustomerProfile> getProfile(Long id) {
    return customerRepository.findById(id)
            .flatMap(customer ->
                    addressRepository.findByCustomerId(id)
                            .collectList()
                            .map(addresses ->
                                    new CustomerProfile(customer, addresses)
                            )
            );
}
~~~

Nếu cần tránh hai round-trip, có thể dùng JOIN và projection phù hợp. Với quan hệ một-nhiều, cần xử lý việc một customer xuất hiện trên nhiều row và nhóm dữ liệu đúng cách.

Trong assessment, lập danh sách các association và fetch strategy hiện tại. Ghi lại endpoint nào cần object graph nào, số query phát sinh và dữ liệu thực sự được trả về. Đây là đầu vào để thiết kế query R2DBC, không nên chuyển nguyên entity graph JPA thành một chuỗi publisher mà chưa xem xét N+1 và lượng dữ liệu.

## 9. Cascade, orphan removal và quan hệ entity

JPA có thể tự động cascade persist, merge, remove hoặc xử lý orphan removal theo mapping. R2DBC không tự điều phối object graph theo cascade semantics JPA.

Ví dụ JPA có thể lưu aggregate với cascade:

~~~java
@OneToMany(mappedBy = "order", cascade = CascadeType.ALL,
           orphanRemoval = true)
private List<OrderLine> lines;
~~~

Khi chuyển sang R2DBC, phải xác định rõ:

- Lưu order trước hay order line trước?
- Generated ID của order được dùng thế nào?
- Nếu một order line lỗi, có rollback toàn bộ không?
- Khi xóa line khỏi collection, có cần DELETE row không?
- Khi xóa order, có cần xóa child row theo thứ tự nào?
- Foreign key và ON DELETE CASCADE đang đảm nhiệm phần nào?

Một cách triển khai tường minh:

~~~java
public Mono<Order> saveOrder(Order order) {
    return orderRepository.save(order)
            .flatMap(saved ->
                    orderLineRepository.deleteByOrderId(saved.id())
                            .thenMany(
                                    orderLineRepository.saveAll(
                                            order.lines().stream()
                                                    .map(line -> line.withOrderId(saved.id()))
                                                    .toList()
                                    )
                            )
                            .then(Mono.just(saved))
            );
}
~~~

Đoạn ví dụ cần được đặt trong transaction nếu nghiệp vụ yêu cầu lưu order và lines atomic. Nó minh họa orchestration tường minh, không phải cách duy nhất hoặc tối ưu cho mọi aggregate.

Đánh giá các cascade mapping đang có và xác định hành vi tương ứng ở service, SQL constraint hoặc stored procedure. Đừng giả định bỏ annotation JPA là database sẽ tự thực hiện cùng logic.

## 10. Query inventory: JPQL, Criteria, Specification và native SQL

Phân loại query hiện tại:

1. Derived query method.
2. JPQL/HQL.
3. Criteria API hoặc Specification.
4. Native SQL.
5. Stored procedure/function.
6. Query tạo động theo filter/sort.
7. Query phân trang và tổng hợp.
8. Query dùng locking hoặc hint của provider.

Ví dụ JPQL:

~~~java
@Query("""
       select c
       from Customer c
       where c.status = :status
       order by c.createdAt desc
       """)
List<Customer> findRecentByStatus(String status);
~~~

Khi chuyển sang R2DBC, query thường cần viết theo tên bảng/cột và SQL dialect:

~~~java
@Query("""
       SELECT id, name, status, created_at
       FROM customers
       WHERE status = :status
       ORDER BY created_at DESC
       """)
Flux<Customer> findRecentByStatus(String status);
~~~

Cần xác nhận:

- Tên bảng/cột sau naming strategy của Hibernate.
- Alias và mapping kết quả.
- Bind parameter và kiểu dữ liệu.
- Null semantics.
- Pagination syntax.
- Sort có được whitelist không.
- Query có dùng function riêng của database không.
- Kết quả có thể lớn đến mức cần streaming không.

Không dịch JPQL bằng cách thay entity name thành table name một cách máy móc. JPQL làm việc trên entity model; SQL làm việc trên relational schema. Association path, inheritance, embedded field và function có thể cần viết lại.

### 10.1. Criteria API và Specification

JPA Criteria/Specification có thể xây query động bằng metamodel entity. Spring Data R2DBC không cung cấp cùng cơ chế JPA Specification. R2dbcEntityTemplate có Criteria API riêng để xây điều kiện relational, nhưng không phải bản sao của JPA Criteria.

Hãy kiểm kê số lượng filter, join, sort và điều kiện tùy chọn. Nếu query đơn giản, có thể chuyển sang query method hoặc Criteria của R2DBC. Nếu query phức tạp, cân nhắc DatabaseClient với SQL tường minh và mapping DTO.

Đối với sort động, chỉ cho phép tên cột nằm trong danh sách đã định nghĩa. Không nối trực tiếp input người dùng vào SQL identifier.

## 11. SQL native, stored procedure và tính năng riêng của database

Native SQL thường là phần dễ bị đánh giá thấp khi chuyển đổi. Query có thể dùng:

- Window function.
- CTE và recursive CTE.
- JSON/JSONB operator.
- Array operator.
- Full-text search.
- Partial index.
- Upsert và conflict handling.
- RETURNING hoặc generated key.
- Vendor-specific hint.
- Stored procedure, function và trigger.
- Temporary table hoặc session variable.

Hãy gom query theo database engine và đánh dấu phần phụ thuộc dialect. R2DBC driver phải hỗ trợ database và kiểu dữ liệu cần thiết; Spring Data không thể làm một tính năng SQL không được engine hỗ trợ trở thành portable.

Nếu stored procedure hiện tại là phần cốt lõi của nghiệp vụ, cần prototype gọi procedure bằng R2DBC API/DatabaseClient và kiểm tra kết quả, parameter mode, transaction và driver behavior. Không giả định mọi JDBC CallableStatement pattern có bản thay thế trực tiếp trong R2DBC.

## 12. Transaction boundary và propagation

Ứng dụng JPA thường dùng @Transactional với PlatformTransactionManager/JpaTransactionManager. Khi chuyển sang R2DBC, transaction manager là reactive và transaction context được truyền qua Reactor Context.

Các câu hỏi cần kiểm kê:

- Transaction bắt đầu ở controller, service hay repository?
- Một use case có gọi nhiều repository không?
- Có nhiều DataSource hoặc database không?
- Có gọi HTTP/message broker trong transaction không?
- Có propagation REQUIRES_NEW, NESTED hoặc read-only không?
- Có transaction timeout hoặc isolation level cụ thể không?
- Có code imperative gọi transaction method reactive không?
- Có self-invocation khiến Spring proxy không được áp dụng không?

Ví dụ reactive transaction:

~~~java
@Transactional
public Mono<Order> placeOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    orderLineRepository.saveAll(toLines(order.id(), command))
                            .thenReturn(order)
            );
}
~~~

Hoặc dùng TransactionalOperator để thể hiện boundary bằng publisher.

Không được trộn imperative transaction và reactive transaction rồi giả định chúng chia sẻ cùng context. JpaTransactionManager không tự quản lý R2DBC ConnectionFactory. Nếu cần cùng một transaction atomic giữa JDBC/JPA và R2DBC, không nên giả định có thể đạt được chỉ bằng cách đặt cả hai lời gọi trong một method @Transactional. Thường phải tách transaction, dùng outbox/saga hoặc giữ cùng một công nghệ truy cập dữ liệu trong boundary cần atomic.

## 13. Locking và concurrency control

JPA hỗ trợ optimistic locking qua @Version và các lock mode của EntityManager. Spring Data R2DBC có thể hỗ trợ optimistic locking thông qua version property trong mapping, nhưng semantics và query phải được xác nhận theo phiên bản và driver. Không có sự thay thế tự động cho toàn bộ lock mode JPA.

Ví dụ JPA:

~~~java
@Version
private Long version;
~~~

Khi chuyển đổi, kiểm tra:

- Cột version có tồn tại và đúng kiểu không?
- UPDATE có điều kiện theo version cũ không?
- Khi không có row được cập nhật, lỗi optimistic locking được biểu diễn thế nào?
- Service có retry conflict không?
- Có dùng PESSIMISTIC_WRITE hoặc SELECT FOR UPDATE không?
- Query lock có được R2DBC dialect/driver hỗ trợ không?
- Các transaction đồng thời có giữ cùng semantics không?

Hãy xây integration test trên đúng database production cho các luồng concurrency quan trọng. Một test tuần tự trên H2 không chứng minh deadlock, lock wait hoặc isolation giống production.

Nếu code hiện tại dựa vào pessimistic locking để bảo vệ inventory, balance hoặc quota, đây là một rủi ro migration cao. Prototype trước khi cam kết chuyển toàn bộ.

## 14. Batch processing và bulk operations

JDBC/JPA có nhiều cơ chế batch, nhưng hiệu quả phụ thuộc provider, JDBC driver, flush/clear strategy và database. Một ứng dụng có thể dùng:

- Hibernate JDBC batch.
- saveAll trên repository.
- JdbcTemplate batchUpdate.
- Batch insert/update.
- Bulk JPQL UPDATE/DELETE.
- Import/export lớn.
- Scheduled job xử lý nhiều hàng.

R2DBC hỗ trợ batch/statement qua SPI và driver, nhưng không phải mọi cách saveAll đều tạo một bulk statement duy nhất. Có thể có nhiều statement được gửi qua một publisher.

Cần đo:

- Kích thước batch.
- Số round-trip.
- Generated key behavior.
- Bộ nhớ giữ entity.
- Transaction duration.
- Lock contention.
- Throughput và error recovery.
- Khả năng resume sau lỗi giữa batch.

Với dữ liệu lớn, cần chia batch, checkpoint và idempotency. Không chuyển một job JDBC batch thành Flux.flatMap concurrency rất cao mà không kiểm tra database capacity.

Nếu batch hiện tại tận dụng tối ưu đặc thù Hibernate/JDBC và không phải bottleneck thread, có thể giữ batch đó trên JDBC trong khi chuyển API tương tác sang R2DBC.

## 15. Generated ID, sequence và entity mapping

JPA provider có nhiều chiến lược sinh ID: IDENTITY, SEQUENCE, TABLE hoặc custom generator. Spring Data R2DBC có mapping metadata và dialect riêng để làm việc với generated values, nhưng không có cùng hệ thống generator phong phú của Hibernate.

Hãy kiểm kê:

- @GeneratedValue strategy.
- Sequence name và allocation size.
- Trigger tạo ID.
- Composite key.
- UUID generator.
- ID được cấp từ application.
- ID được trả về sau INSERT.
- Entity có dùng constructor mapping hoặc property access không.

Prototype từng chiến lược trên database thật. Kiểm tra cả trường hợp insert một row, batch insert và generated value được dùng ngay để lưu bảng con.

Ngoài ID, kiểm tra @Embedded, @ElementCollection, inheritance mapping, enum, converter, JSON type và naming strategy. Spring Data R2DBC mapping đơn giản hơn JPA nhưng cần schema/row mapping rõ ràng.

## 16. Auditing, lifecycle callback và event

JPA có thể dùng @PrePersist, @PreUpdate, @PostLoad, EntityListener hoặc Spring Data auditing. Khi chuyển sang R2DBC, cần xác định callback nào thuộc lifecycle entity, callback nào là nghiệp vụ và callback nào tạo side effect.

Spring Data R2DBC có EntityCallback như BeforeConvertCallback, BeforeSaveCallback, AfterSaveCallback và AfterConvertCallback. Auditing cũng có thể được cấu hình cho R2DBC. Tuy nhiên, không nên giả định JPA listener sẽ được gọi hoặc có cùng thứ tự sau migration.

Hãy phân loại:

- Gán createdAt/updatedAt.
- Gán createdBy/lastModifiedBy.
- Chuẩn hóa field.
- Validate entity.
- Phát application event.
- Gửi email hoặc HTTP.
- Publish message.
- Ghi audit trail trong database.

Các thay đổi dữ liệu cần nằm trong persistence lifecycle có thể phù hợp với EntityCallback. Quy tắc nghiệp vụ nên nằm ở service/domain. Side effect cần nhất quán với commit nên cân nhắc transactional outbox thay vì gửi trực tiếp trong callback.

## 17. Transactional event và side effect ngoài database

Nhiều ứng dụng JPA dùng event listener sau commit để phát message hoặc gọi hệ thống ngoài. Khi chuyển sang reactive, cần xem lại transaction event model và Reactor Context.

Một callback sau khi lưu entity không đồng nghĩa database transaction đã commit. Nếu gửi message trước commit rồi transaction rollback, consumer có thể nhận một sự kiện cho dữ liệu chưa tồn tại.

Với yêu cầu phát message đáng tin cậy:

1. Ghi thay đổi nghiệp vụ.
2. Ghi outbox event trong cùng database transaction.
3. Commit cả hai.
4. Worker/publisher đọc outbox và gửi message.
5. Đánh dấu đã gửi hoặc xử lý retry.
6. Consumer hỗ trợ deduplication/idempotency.

Nếu hiện tại ứng dụng dựa vào JPA @TransactionalEventListener(AFTER_COMMIT), cần thiết kế tương ứng cho reactive transaction, kiểm tra context và failure handling. Không chuyển annotation một cách cơ học.

## 18. Blocking dependency ngoài database

Một migration chỉ thay JDBC bằng R2DBC nhưng vẫn gọi nhiều API blocking sẽ không tạo reactive end-to-end.

Kiểm kê các dependency trong cùng request path:

- RestTemplate hoặc HTTP client blocking.
- JDBC DAO còn sót.
- Redis client blocking.
- File I/O.
- SDK cloud blocking.
- LDAP hoặc legacy service.
- Synchronous message producer.
- CPU-heavy transformation.
- ThreadLocal context/security/audit.

Nếu service dùng WebFlux nhưng gọi JDBC hoặc JPA trên event-loop, request vẫn có thể block. Có thể cô lập blocking work trên scheduler phù hợp trong giai đoạn chuyển tiếp, nhưng đây là giải pháp vận hành tạm thời và cần đo. Không chuyển một đoạn blocking call sang boundedElastic rồi gọi đó là non-blocking.

Để có lợi ích reactive, toàn bộ đường đi cần được xem xét. Một endpoint có thể bắt đầu reactive nhưng chờ một SDK blocking trong flatMap, làm mất lợi ích concurrency và gây áp lực lên scheduler.

## 19. API contract: List/Optional so với Flux/Mono

JPA repository thường trả về kiểu đồng bộ như Entity, Optional, List hoặc Page. R2DBC repository thường trả Mono và Flux.

| Kiểu imperative phổ biến | Kiểu reactive thường dùng |
|---|---|
| Entity | Mono<Entity> |
| Optional<Entity> | Mono<Entity> empty khi không có |
| List<Entity> | Flux<Entity> |
| Page<Entity> | Cần thiết kế kết hợp dữ liệu và count |
| void | Mono<Void> |
| int/long rows affected | Mono<Integer/Long> tùy API |
| Stream<Entity> | Flux<Entity>, cần quản lý lifecycle/cancel |

Thay đổi này lan ra service, controller, scheduler, message handler và test. Không nên gọi block() ngay trong service để giữ chữ ký đồng bộ nếu mục tiêu là reactive end-to-end.

### 19.1. Pagination không tự chuyển một-một

Spring Data JPA Page thường chứa content, total elements, total pages và paging metadata. Với R2DBC, có thể cần query content và query count riêng, ghép kết quả bằng Mono.zip hoặc một publisher phù hợp.

Với dữ liệu lớn, cân nhắc keyset pagination thay vì offset pagination nếu database và nghiệp vụ hỗ trợ. Hãy kiểm tra sort ổn định và điều kiện trang cuối.

### 19.2. Flux có thể phát dữ liệu theo stream

Một Flux không phải List được trả ngay. Caller cần subscribe và tiêu thụ các phần tử. Nếu collectList(), ứng dụng lại giữ toàn bộ kết quả trong bộ nhớ.

Đánh giá API consumer: có thể stream ra HTTP response, xử lý theo batch hoặc cần tổng hợp toàn bộ dữ liệu? Chọn kiểu trả về dựa trên nhu cầu thật, không đổi List thành Flux rồi lập tức collectList ở mọi nơi.

## 20. Context, security và transaction propagation

Reactive pipeline có thể chuyển execution giữa thread. Những thông tin trước đây được lưu trong ThreadLocal có thể không tự đi theo pipeline.

Cần kiểm kê:

- SecurityContext.
- Tenant ID.
- MDC/log correlation.
- Locale.
- User/auditor identity.
- Transaction context.
- Request-scoped data.
- Custom ThreadLocal.

Spring Security reactive dùng Reactor Context cho security context. Reactive transaction cũng dựa trên Reactor Context. Nếu code hiện tại tự đọc ThreadLocal trong callback hoặc repository listener, cần chuyển sang cơ chế context-aware phù hợp.

Không dùng ThreadLocal để truyền transaction hoặc security identity qua các operator một cách tùy tiện. Kiểm tra các đoạn dùng SecurityContextHolder, RequestContextHolder và MDC khi chuyển sang WebFlux/reactive.

## 21. Connection pool và vận hành

JDBC pool như HikariCP và R2DBC pool quản lý hai loại connection theo API khác nhau. Không thể sao chép nguyên max pool size từ JDBC sang R2DBC rồi mặc định hiệu năng tương đương.

Hãy đánh giá:

- Số replica tối đa.
- Tổng connection từ tất cả pool và service.
- Database max connections.
- Acquire latency và pending queue.
- Connection hold duration.
- Transaction duration.
- Query latency p95/p99.
- Retry và timeout.
- Database CPU, memory, lock và I/O.

R2DBC không làm database xử lý nhiều query hơn vô hạn. Pool quá lớn có thể làm database bão hòa. Pool quá nhỏ có thể tạo queue. Cần load test và ngân sách connection toàn hệ thống.

Các thao tác startup như migration có thể vẫn dùng JDBC. Điều này có nghĩa một ứng dụng R2DBC vẫn có thể cần JDBC driver và DataSource cho Flyway/Liquibase, nhưng runtime repository dùng R2DBC ConnectionFactory. Hai đường kết nối cần trỏ đúng database/schema.

## 22. Database và driver compatibility

Không phải mọi database hoặc tính năng đều có driver R2DBC với cùng độ trưởng thành và khả năng. Trước migration, kiểm tra:

- Database engine và version đang dùng.
- R2DBC driver chính thức/được hỗ trợ.
- R2DBC SPI compatibility.
- Kiểu dữ liệu native.
- Generated keys và sequences.
- Stored procedure/function.
- Large object/BLOB/CLOB.
- Array, JSON, enum, UUID.
- Transaction isolation và locking.
- Cancellation behavior.
- SSL, authentication và failover.
- Connection validation và pool integration.

Nếu ứng dụng dùng tính năng đặc thù của Oracle, SQL Server hoặc một extension PostgreSQL, hãy làm prototype trên chính driver và version production. Không suy luận từ một demo chạy H2.

Kiểm tra roadmap/support policy của driver và khả năng xử lý sự cố trong tổ chức. Một driver có thể đáp ứng CRUD nhưng chưa đáp ứng đầy đủ feature set của ứng dụng.

## 23. Schema migration và lịch sử dữ liệu

JPA có thể đang dùng Hibernate DDL auto hoặc migration tool. Trước khi chuyển, xác định ai sở hữu schema:

- Hibernate tự tạo/cập nhật schema.
- Flyway.
- Liquibase.
- Script SQL thủ công.
- Database team quản lý riêng.
- Nhiều công cụ cùng tồn tại.

Với production, cần migration có versioning rõ ràng. Không để Hibernate DDL auto và R2DBC mapping cùng tự suy luận schema trong môi trường production.

Migration cần bảo đảm tương thích với phiên bản ứng dụng cũ và mới trong rolling deployment. Nếu thay đổi cột hoặc quan hệ, dùng expand-and-contract khi cần:

1. Thêm cấu trúc mới mà code cũ vẫn dùng được.
2. Deploy code có thể đọc/ghi tương thích.
3. Backfill dữ liệu.
4. Chuyển toàn bộ instance sang code mới.
5. Xóa cấu trúc cũ ở release sau.

Không sửa migration đã chạy trên môi trường chia sẻ; tạo migration mới. Kiểm thử cả schema rỗng và upgrade từ schema hiện tại.

## 24. Kiểm thử trước migration

Nên có ba nhóm kiểm thử riêng:

### 24.1. Unit test

Dùng mock/fake để kiểm tra:

- Business rules.
- Validation.
- Error mapping.
- Điều phối publisher.
- Xử lý empty/error.
- Retry policy.
- API response mapping.

Unit test không chứng minh SQL hoặc mapping.

### 24.2. Data-access integration test

Dùng repository/template/DatabaseClient thật với R2DBC driver và database để kiểm tra:

- Entity mapping.
- Derived query và custom SQL.
- Converter.
- Generated ID/version.
- Constraint.
- Transaction rollback.
- Pagination và sorting.
- EntityCallback và auditing.

### 24.3. Production database integration test

Dùng Testcontainers hoặc database test cùng engine/version production để kiểm tra:

- SQL dialect.
- Native type.
- Stored procedure.
- Migration.
- Locking/concurrency.
- Transaction isolation.
- Driver-specific behavior.
- Error code/SQLState.

H2 có thể hỗ trợ test relational phổ thông, nhưng không thay thế database production. Không dùng mock repository để tuyên bố repository đã được kiểm thử.

## 25. Prototype một vertical slice trước khi cam kết

Chọn một use case có giá trị đại diện, không quá đơn giản cũng không quá phức tạp. Ví dụ: tìm customer, cập nhật profile và ghi audit.

Prototype cần đi qua đầy đủ đường đi:

~~~text
HTTP endpoint
     |
     v
Reactive controller
     |
     v
Service / use case
     |
     v
R2DBC repository / template
     |
     v
Production R2DBC driver
     |
     v
Database
~~~

Đánh giá prototype theo các tiêu chí:

- Có giữ được API behavior không?
- Query và mapping có chính xác không?
- Transaction có giữ đúng atomicity không?
- Có xử lý empty/error/cancel không?
- Có blocking call còn sót không?
- Có cải thiện thread usage và latency dưới tải không?
- Pool và database có ổn định không?
- Code có dễ đọc, debug và test không?
- Team có vận hành được metrics/tracing mới không?

Đo cùng workload và dữ liệu trước/sau. Nếu prototype không cho thấy lợi ích hoặc làm tăng đáng kể độ phức tạp, dừng và xem lại mục tiêu trước khi mở rộng.

## 26. Ma trận đánh giá mức độ sẵn sàng

Có thể chấm từng use case theo ma trận:

| Tiêu chí | Thấp rủi ro | Trung bình | Cao rủi ro |
|---|---|---|---|
| ORM feature | CRUD đơn giản | Converter/callback | Lazy loading, cascade sâu, inheritance phức tạp |
| Query | Derived query đơn giản | Criteria/query động | Native SQL/procedure đặc thù |
| Transaction | Một repository call | Nhiều thao tác cùng DB | Nhiều resource hoặc lock phức tạp |
| Data type | Scalar phổ thông | UUID/JSON cần xác minh | Vendor type/LOB/array đặc thù |
| Batch | Khối lượng nhỏ | Batch có giới hạn | Batch lớn, generator/provider-specific |
| Dependency | Reactive end-to-end | Một vài blocking adapter | Nhiều SDK blocking trong critical path |
| Driver | Feature được hỗ trợ rõ | Cần prototype | Thiếu feature/khó vận hành |
| Test | Có integration test | Test coverage một phần | Không có test trên database thật |

Ma trận này là công cụ thảo luận, không phải điểm số tuyệt đối. Một use case có một tiêu chí rủi ro cao như pessimistic locking hoặc stored procedure cốt lõi cũng có thể quyết định chưa chuyển.

Ghi thêm owner, estimate, dependency, rollback plan và mức độ ảnh hưởng nếu migration thất bại.

## 27. Quyết định giữ JDBC/JPA, chuyển R2DBC hay dùng hybrid

| Lựa chọn | Khi phù hợp | Điểm cần cân nhắc |
|---|---|---|
| Giữ JDBC/JPA | ORM feature quan trọng, workload ổn định, blocking không phải bottleneck | Giữ mô hình đơn giản, tiếp tục tối ưu query/pool |
| Chuyển R2DBC | I/O concurrency là vấn đề đo được, stack reactive, driver đủ feature | Chi phí viết lại transaction/query và thay đổi API |
| Hybrid theo module/use case | Một số luồng cần reactive, phần khác phụ thuộc JPA/batch | Hai transaction model và connection pool cần quản lý riêng |
| Chỉ chuyển API boundary | Cần reactive HTTP nhưng database path vẫn blocking trong ngắn hạn | Phải cô lập blocking call, không coi là reactive end-to-end |
| Chưa chuyển, tối ưu JDBC | Nút thắt là query/index/DB chứ không phải blocking thread | Có thể đạt lợi ích với chi phí thấp hơn |

Hybrid có thể là lựa chọn thực tế. Ví dụ API tương tác dùng R2DBC, còn reporting hoặc batch hiện tại giữ JDBC. Tuy nhiên, không được giả định một transaction atomic có thể bao trùm cả JpaTransactionManager và R2dbcTransactionManager chỉ bằng một annotation.

Nếu một use case phải ghi vào cả hai đường truy cập dữ liệu, hãy thiết kế boundary rõ ràng. Có thể dùng outbox/saga hoặc tách use case để tránh phụ thuộc vào distributed transaction không được hỗ trợ.

## 28. Lộ trình migration theo từng giai đoạn

Một lộ trình có kiểm soát:

### Giai đoạn 1: Discovery

- Thu thập baseline.
- Lập inventory repository/query.
- Kiểm kê JPA feature.
- Xác định driver và database capability.
- Đánh dấu blocking dependency.
- Phân loại use case theo rủi ro.

### Giai đoạn 2: Prototype

- Chọn một vertical slice.
- Thiết kế entity mapping R2DBC.
- Viết lại query và transaction.
- Thêm integration test trên database production.
- Đo tải và vận hành pool.
- Đánh giá readability và supportability.

### Giai đoạn 3: Foundation

- Chuẩn hóa ConnectionFactory và pool.
- Thiết lập reactive transaction manager.
- Thiết lập metrics, tracing và logging.
- Chuẩn hóa error handling và timeout.
- Chuẩn hóa migration và test infrastructure.

### Giai đoạn 4: Incremental migration

- Chuyển từng use case/module độc lập.
- Duy trì API contract.
- Kiểm thử song song ở môi trường staging.
- Theo dõi metrics và error.
- Giữ khả năng quay lại phiên bản cũ trong thời gian chuyển tiếp.

### Giai đoạn 5: Stabilization

- Xóa code JDBC/JPA chỉ khi không còn caller.
- Xác nhận connection pool và resource budget.
- Kiểm thử concurrency/load.
- Cập nhật runbook và tài liệu vận hành.
- Đào tạo team và chuyển giao ownership.

Không chuyển tất cả repository trong một release lớn nếu có thể chia nhỏ theo boundary nghiệp vụ.

## 29. Chiến lược coexistence và tránh dual-write nguy hiểm

Trong giai đoạn chuyển đổi, một số module có thể dùng JPA, module khác dùng R2DBC trên cùng database. Điều này có thể hoạt động nếu schema và transaction boundary được quản lý rõ.

Các rủi ro:

- Hai connection pool tiêu thụ chung ngân sách database.
- JPA transaction và R2DBC transaction độc lập.
- Cùng một row được cập nhật từ hai đường mà không có concurrency policy.
- Cache/persistence context JPA giữ dữ liệu cũ sau khi R2DBC thay đổi row.
- Entity mapping và naming convention không đồng nhất.
- Một use case vô tình cần atomic write qua cả hai transaction manager.

Nếu JPA persistence context còn mở và R2DBC thay đổi cùng row, JPA entity đang managed có thể không tự biết dữ liệu đã đổi. Cần refresh/clear hoặc thiết kế không để hai đường cùng quản lý state trong một use case.

Tránh dual-write hai database hoặc hai transaction resource rồi giả định cả hai cùng commit. Nếu cần phát sự kiện hoặc đồng bộ, dùng outbox/saga và idempotency.

## 30. Kế hoạch rollback và tiêu chí dừng

Trước khi chuyển một use case production, xác định:

- Phiên bản code cũ còn chạy được trên schema mới không?
- Có migration destructive không?
- Có thể rollback application mà không rollback schema không?
- Dữ liệu ghi bởi phiên bản mới có đọc được bởi phiên bản cũ không?
- Có feature flag để chuyển traffic không?
- Có thể tắt R2DBC path và quay lại JDBC path không?
- Có cần backfill ngược hoặc forward-fix không?
- Ai quyết định dừng rollout và theo metric nào?

Tiêu chí dừng có thể gồm:

- Error rate tăng vượt ngưỡng.
- p95/p99 latency xấu hơn baseline.
- Acquire timeout hoặc pool pending tăng kéo dài.
- Database CPU/connection vượt ngân sách.
- Transaction rollback/deadlock tăng.
- Data mismatch hoặc lỗi mapping.
- Khó khôi phục do schema incompatibility.

Rollback code không phải lúc nào cũng có nghĩa rollback database. Ưu tiên migration tương thích ngược và forward-fix an toàn, nhất là khi dữ liệu đã được ghi bởi phiên bản mới.

## 31. Chi phí kỹ năng và vận hành

Reactive programming thay đổi cách đọc stack trace, debug, test và quan sát hệ thống. Team cần hiểu:

- Mono/Flux và lazy subscription.
- Error signal, empty và cancellation.
- Backpressure.
- Reactor Context.
- Reactive transaction.
- Không block hoặc subscribe thủ công.
- Connection pool và acquire timeout.
- Scheduler và blocking boundary.
- Testing bằng StepVerifier.
- Tracing/metrics cho publisher.

Nếu phần lớn hệ thống vẫn dùng MVC, JDBC, synchronous SDK và batch blocking, chỉ chuyển một module database sang R2DBC có thể làm kiến trúc khó hiểu hơn. Đánh giá chi phí onboarding, on-call và khả năng debug trước khi quyết định.

Không coi số dòng code ít hơn hoặc API reactive trông hiện đại hơn là bằng chứng migration thành công. Tiêu chí cần là behavior đúng, tài nguyên ổn định, latency/throughput cải thiện khi cần và team vận hành được.

## 32. Các dấu hiệu nên hoãn migration

Có thể nên hoãn hoặc giới hạn migration khi:

- Chưa đo được blocking JDBC là nút thắt.
- Database đang bão hòa vì query/CPU/lock.
- Ứng dụng phụ thuộc sâu vào JPA persistence context.
- Nhiều use case dựa vào lazy loading và cascade phức tạp.
- Có nhiều stored procedure hoặc native SQL chưa được driver hỗ trợ.
- Transaction cần phối hợp nhiều resource imperative.
- Driver R2DBC thiếu feature hoặc support phù hợp.
- Nhiều dependency blocking nằm trong critical path.
- Không có integration test trên database production.
- Team chưa có kinh nghiệm reactive và không có thời gian đào tạo.
- Lợi ích vận hành dự kiến thấp hơn chi phí viết lại và duy trì hai stack.

Hoãn migration không có nghĩa không cải tiến. Có thể tối ưu index/query, giảm N+1, điều chỉnh JDBC pool, cache đúng chỗ, dùng pagination hoặc cô lập blocking workload để đạt mục tiêu trước mắt.

## 33. Checklist assessment trước khi phê duyệt

### Mục tiêu và baseline

- [ ] Có vấn đề cụ thể mà migration cần giải quyết.
- [ ] Đã đo request latency, throughput và concurrency.
- [ ] Đã đo thread usage và JDBC pool.
- [ ] Đã kiểm tra database CPU, I/O, lock và query plan.
- [ ] Có tiêu chí thành công đo được sau migration.

### Code và ORM

- [ ] Đã inventory toàn bộ JDBC/JPA access path.
- [ ] Đã kiểm kê persistence context và dirty checking.
- [ ] Đã kiểm kê lazy/eager relationship và N+1.
- [ ] Đã kiểm kê cascade/orphan removal.
- [ ] Đã kiểm kê callback, auditing và event listener.
- [ ] Đã kiểm kê JPQL, Criteria, Specification và native SQL.
- [ ] Đã kiểm kê ID generation, converter và inheritance mapping.

### Database behavior

- [ ] Đã kiểm tra transaction boundary/propagation.
- [ ] Đã kiểm tra optimistic/pessimistic locking.
- [ ] Đã kiểm tra batch và bulk operation.
- [ ] Đã xác nhận driver R2DBC hỗ trợ kiểu dữ liệu cần thiết.
- [ ] Đã prototype stored procedure/native feature quan trọng.
- [ ] Đã xác nhận migration strategy và rolling compatibility.

### Reactive readiness

- [ ] Critical path không còn blocking dependency chưa được xử lý.
- [ ] API contract đã thiết kế Mono/Flux phù hợp.
- [ ] Security, tenant và logging context đã được xem xét.
- [ ] Team hiểu cancellation, backpressure và reactive transaction.
- [ ] Connection pool được tính theo số replica tối đa.

### Kiểm thử và rollout

- [ ] Có unit test cho business logic.
- [ ] Có data-access integration test với R2DBC thật.
- [ ] Có test trên đúng database production.
- [ ] Có migration test từ schema rỗng và schema hiện tại.
- [ ] Có load test so sánh với baseline.
- [ ] Có rollout từng phần và rollback plan.
- [ ] Có dashboard, alert và runbook vận hành.

## 34. Kết luận

Đánh giá ứng dụng JDBC/JPA trước khi chuyển sang R2DBC cần bắt đầu từ mục tiêu và số liệu, sau đó kiểm kê toàn bộ query, transaction, ORM feature, kiểu dữ liệu, batch, dependency blocking và yêu cầu vận hành. JDBC và JPA không chỉ là cách gửi SQL: JPA còn cung cấp persistence context, dirty checking, lazy loading, cascade, locking và entity lifecycle. Spring Data R2DBC có mô hình mapping relational và reactive repository riêng, không tái tạo tự động toàn bộ những semantics đó.

R2DBC phù hợp khi ứng dụng có nhu cầu I/O concurrency được đo rõ, driver hỗ trợ feature cần thiết và phần lớn đường đi có thể reactive. Nếu nút thắt nằm ở query, index, database saturation hoặc blocking dependency ngoài database, cần giải quyết nguyên nhân đó trước. Với ứng dụng JPA phức tạp, hãy prototype một vertical slice, kiểm thử trên database production, đo cùng workload và đánh giá chi phí vận hành.

Kết quả assessment có thể là chuyển toàn bộ, chuyển từng module, giữ hybrid JDBC/R2DBC hoặc chưa chuyển. Quyết định tốt là quyết định dựa trên behavior cần bảo toàn, lợi ích đo được, rủi ro database và khả năng đội ngũ duy trì hệ thống sau migration.

