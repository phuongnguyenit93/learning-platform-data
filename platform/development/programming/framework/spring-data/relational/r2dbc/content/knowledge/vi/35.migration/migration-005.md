# Di chuyển từng chức năng và kiểm chứng hành vi tương đương

## 1. Vì sao nên di chuyển từng chức năng?

Chuyển một ứng dụng truy cập database từ JDBC/JPA sang Spring Data Relational R2DBC không chỉ là thay kiểu repository hoặc đổi câu gọi blocking thành Mono/Flux. Hai mô hình có cách quản lý connection, transaction, mapping, concurrency và vòng đời dữ liệu khác nhau.

Một chức năng đang chạy ổn định có thể phụ thuộc vào những hành vi không được ghi rõ trong tài liệu thiết kế:

- Thứ tự sắp xếp mặc định của một truy vấn.
- Cách xử lý giá trị null.
- Thời điểm ID được sinh.
- Cách optimistic locking hoạt động.
- Transaction bao phủ những repository nào.
- Side effect được thực hiện trước hay sau commit.
- Quy tắc làm tròn decimal và chuyển đổi ngày giờ.
- Exception nào được trả cho client.
- Một lần gọi API có tạo đúng một event hay không.

Nếu chuyển toàn bộ ứng dụng cùng lúc, khi hành vi thay đổi sẽ khó xác định nguyên nhân nằm ở mapping, SQL, transaction, driver hay code nghiệp vụ.

Một cách an toàn hơn là di chuyển theo từng chức năng hoặc vertical slice. Mỗi slice đi qua đầy đủ các lớp cần thiết để hoàn thành một use case, từ API/service đến database và các side effect liên quan. Sau mỗi slice, nhóm phát triển kiểm chứng hành vi mới so với hành vi hiện tại trước khi mở rộng phạm vi.

Ví dụ, có thể di chuyển chức năng xem chi tiết đơn hàng trước, tiếp theo là tìm kiếm đơn hàng, sau đó xác nhận đơn hàng và cuối cùng là quy trình thanh toán. Mỗi bước có tiêu chí hoàn thành và bằng chứng kiểm thử riêng.

Cách làm này giúp:

- Giảm phạm vi thay đổi trong mỗi lần triển khai.
- Phát hiện sớm khác biệt về dữ liệu và transaction.
- Giữ khả năng phát hành từng phần.
- So sánh kết quả giữa implementation cũ và mới.
- Xác định chính xác chức năng nào đã sẵn sàng chuyển traffic.
- Giảm rủi ro phải rollback toàn bộ ứng dụng.

## 2. Hành vi tương đương có nghĩa là gì?

Hành vi tương đương không có nghĩa implementation mới phải có cùng class, method hoặc SQL với implementation cũ. Điều cần giữ là hợp đồng mà người dùng, hệ thống tích hợp và các chức năng khác đang dựa vào.

Với một chức năng truy cập dữ liệu, cần xem xét ít nhất các khía cạnh sau:

| Khía cạnh | Điều cần giữ hoặc chủ động thay đổi |
|---|---|
| API contract | HTTP method, path, status, response schema và error contract |
| Business rules | Điều kiện hợp lệ, trạng thái chuyển đổi và kết quả nghiệp vụ |
| Data mapping | Giá trị được đọc/ghi, nullability, precision và kiểu dữ liệu |
| Query semantics | Filter, sort, pagination, join, count và thứ tự kết quả |
| Transaction | Nhóm thao tác commit/rollback cùng nhau |
| Concurrency | Hành vi khi nhiều request cùng cập nhật dữ liệu |
| Side effects | Event, email, payment, audit và thời điểm phát sinh |
| Security | Tenant scope, authorization và dữ liệu được phép đọc |
| Performance contract | Latency, throughput, pool usage và giới hạn tài nguyên |
| Failure behavior | Timeout, retry, cancellation và lỗi database |

Một số khác biệt nội bộ có thể chấp nhận nếu không làm thay đổi hợp đồng bên ngoài. Ví dụ, implementation cũ dùng một query join còn implementation mới dùng hai query rồi ghép kết quả. Điều cần xác nhận là dữ liệu, quyền truy cập, consistency và hiệu năng vẫn đáp ứng yêu cầu.

Ngược lại, một khác biệt nhỏ về null, thứ tự kết quả hoặc transaction có thể làm thay đổi nghiệp vụ dù API vẫn trả HTTP 200.

### 2.1. Phân biệt tương đương với cải tiến nghiệp vụ

Trong quá trình migration, có thể phát hiện hành vi cũ là lỗi hoặc không còn phù hợp. Không nên âm thầm thay đổi hành vi đó trong cùng một bước migration kỹ thuật.

Hãy phân loại:

- Hành vi cần giữ để tương thích.
- Hành vi cũ sai và cần sửa.
- Hành vi chưa được xác định, cần quyết định từ product/domain owner.
- Hành vi mới được chủ động thiết kế lại.

Nếu vừa chuyển sang R2DBC vừa thay đổi business rule, khi test thất bại sẽ khó biết lỗi đến từ đâu. Nên tách thay đổi nghiệp vụ thành một quyết định có ghi nhận và bộ test riêng.

## 3. Lập danh mục chức năng trước khi thay đổi

Trước khi viết adapter R2DBC, hãy lập inventory các use case đang truy cập database.

Ví dụ:

| Chức năng | Đọc/ghi | Thành phần hiện tại | Rủi ro chính | Thứ tự dự kiến |
|---|---|---|---|---|
| Xem chi tiết order | Đọc | JDBC/JPA repository | Mapping, quan hệ và null | Thấp |
| Tìm kiếm order | Đọc | Criteria/Specification | Filter, sort, pagination | Trung bình |
| Tạo order | Ghi | JPA repository | ID, transaction và outbox | Trung bình |
| Cập nhật trạng thái | Ghi | JPA + service | Optimistic locking | Cao |
| Xác nhận order | Nhiều ghi | Nhiều repository | Transaction boundary | Cao |
| Xuất báo cáo | Đọc lớn | JDBC streaming | Memory, cursor và timeout | Cao |
| Đồng bộ audit | Ghi + event | JDBC + broker | Retry và idempotency | Cao |

Inventory nên ghi cả những đường truy cập ít phổ biến:

- Scheduled job.
- Batch import/export.
- Consumer message.
- Admin endpoint.
- Repository custom implementation.
- Stored procedure.
- SQL trực tiếp.
- Tác vụ chạy khi khởi động.
- Migration và maintenance script.

Một use case có thể được gọi từ nhiều entry point. Di chuyển service mà quên scheduled job hoặc message consumer có thể khiến hai mô hình persistence cùng ghi vào một bảng theo cách khác nhau.

### 3.1. Ghi lại dependency của mỗi chức năng

Với mỗi use case, ghi rõ:

- Controller hoặc message handler gọi nó.
- Service nào điều phối nghiệp vụ.
- Repository, template hoặc DatabaseClient nào được dùng.
- Bảng và schema liên quan.
- Transaction manager hiện tại.
- Event hoặc side effect được tạo.
- Các chức năng khác phụ thuộc dữ liệu đầu ra.
- Các API contract test hiện có.

Dependency map giúp xác định một slice có thực sự độc lập hay không.

### 3.2. Chọn slice đầu tiên có phạm vi nhỏ

Nên bắt đầu bằng chức năng:

- Có contract rõ.
- Có ít side effect.
- Ít bảng liên quan.
- Dễ tạo fixture.
- Dễ kiểm chứng dữ liệu.
- Có thể chuyển traffic độc lập.
- Có phương án quay lại implementation cũ.

Một query đọc chi tiết không nhất thiết là slice đầu tiên tốt nhất nếu nó phụ thuộc nhiều quan hệ lazy loading hoặc dữ liệu được ghép từ nhiều nguồn. Hãy chọn dựa trên độ phức tạp thực tế, không chỉ dựa vào tên CRUD.

## 4. Characterization test: ghi nhận hành vi hiện tại

Trước khi thay implementation, hãy tạo test mô tả hành vi của hệ thống đang chạy. Đây thường được gọi là characterization test hoặc golden-master style test.

Mục tiêu là ghi nhận kết quả thực tế mà implementation cũ đang cung cấp, kể cả những chi tiết chưa được tài liệu hóa.

Ví dụ với chức năng tìm kiếm order, cần ghi lại:

- Khi status không được truyền thì filter mặc định là gì?
- Keyword được trim hay giữ nguyên khoảng trắng?
- Tìm kiếm phân biệt hoa thường hay không?
- Khi ngày bắt đầu bằng ngày kết thúc thì kết quả ra sao?
- Sort mặc định theo trường nào?
- Hai hàng có cùng timestamp được sắp xếp thế nào?
- Page size bằng 0 hoặc âm được xử lý ra sao?
- Không có kết quả trả danh sách rỗng hay lỗi?
- Total count có tính cùng filter với danh sách không?
- Tenant nào được phép nhìn thấy dữ liệu?

Test không nên chỉ kiểm tra một fixture đơn giản. Cần có dữ liệu biên để phát hiện các quy tắc ẩn.

### 4.1. Ví dụ test hợp đồng hiện tại

~~~java
@Test
void searchShouldUseStableDefaultOrdering() {
    SearchRequest request = new SearchRequest(
        null,
        0,
        20,
        null,
        null
    );

    StepVerifier.create(legacyOrderService.search(request))
        .assertNext(page -> {
            assertThat(page.items())
                .extracting(OrderSummary::id)
                .containsExactly(103L, 102L, 101L);

            assertThat(page.totalElements()).isEqualTo(3);
        })
        .verifyComplete();
}
~~~

Ví dụ giả định service cũ đã được bọc bằng API test phù hợp. Trong dự án thực tế, có thể implementation cũ trả kiểu đồng bộ; khi đó dùng test tương ứng với API hiện tại, không cần chuyển nó sang reactive chỉ để viết characterization test.

### 4.2. Lưu fixture và kết quả có thể tái lập

Fixture cần chứa:
- Dữ liệu thông thường.
- Dữ liệu null.
- Giá trị biên.
- Hai hàng có cùng giá trị sort.
- Dữ liệu thuộc tenant khác.
- Bản ghi đã soft-delete nếu ứng dụng có quy tắc này.
- Dữ liệu có version khác nhau.
- Trạng thái nghiệp vụ không hợp lệ.

Không dùng database production làm nguồn test. Hãy dùng schema và dữ liệu tổng hợp có thể tái tạo.

### 4.3. Không đóng băng lỗi bảo mật

Nếu characterization test phát hiện implementation cũ cho phép đọc dữ liệu tenant khác, không nên coi đó là hành vi phải giữ. Ghi nhận đây là lỗi bảo mật và xử lý bằng thay đổi được phê duyệt riêng. Tương đương không có nghĩa phải sao chép lỗ hổng.

## 5. Thiết kế ranh giới để có thể thay implementation

Một cách hữu ích là giữ hợp đồng ứng dụng ổn định và thay adapter persistence phía dưới.

Ví dụ:

~~~java
public interface OrderReader {
    Mono<OrderDetails> findDetails(long orderId, TenantId tenantId);
}
~~~

Implementation hiện tại:

~~~java
@Repository
public class JdbcOrderReader implements OrderReader {
    // JDBC/JPA implementation hiện tại
}
~~~

Implementation mới:

~~~java
@Repository
public class R2dbcOrderReader implements OrderReader {
    // R2DBC implementation
}
~~~

Service phụ thuộc vào abstraction:

~~~java
@Service
public class OrderQueryService {

    private final OrderReader orderReader;

    public OrderQueryService(OrderReader orderReader) {
        this.orderReader = orderReader;
    }

    public Mono<OrderDetails> details(
            long orderId,
            TenantId tenantId) {
        return orderReader.findDetails(orderId, tenantId);
    }
}
~~~

Đây là một ví dụ về adapter boundary. Không phải mọi ứng dụng đều cần tạo interface mới cho mỗi repository. Hãy tạo ranh giới khi nó giúp chuyển implementation, kiểm thử hoặc quản lý nhiều nguồn persistence rõ ràng hơn.

Nếu implementation cũ là blocking, không được giả vờ biến nó thành non-blocking chỉ bằng cách đổi kiểu trả về thành Mono. Khi tạm thời gọi JDBC trong WebFlux, phải cô lập blocking work trên scheduler phù hợp và ghi nhận đó là giai đoạn chuyển tiếp.

## 6. Di chuyển theo vertical slice

Một slice nên hoàn thành toàn bộ luồng của một use case, thay vì chuyển từng lớp kỹ thuật trên toàn hệ thống.

Ví dụ slice xem chi tiết order:

~~~text
HTTP GET /orders/{id}
        |
        v
OrderController
        |
        v
OrderQueryService
        |
        v
OrderReader
        |
        v
R2dbcOrderReader
        |
        v
R2dbcEntityTemplate / DatabaseClient
        |
        v
Orders database
~~~

Một slice ghi order có thể cần thêm transaction manager và outbox:

~~~text
HTTP POST /orders
        |
        v
OrderCommandService
        |
        v
Reactive transaction
        |
        +-- OrderRepository.save(...)
        |
        +-- OutboxRepository.save(...)
        |
        v
COMMIT
~~~

Mỗi slice nên có:
1. Hợp đồng và tiêu chí chấp nhận.
2. Mapping và query R2DBC.
3. Transaction boundary nếu có ghi.
4. Kiểm thử tương đương.
5. Đo hiệu năng và tài nguyên.
6. Cách chuyển traffic.
7. Cách rollback implementation.

### 6.1. Chuyển read trước write khi phù hợp

Một số hệ thống có thể bắt đầu bằng read-only use case vì không cần giải quyết dual-write và side effect.

Tuy nhiên, read path vẫn cần kiểm tra:
- Tenant scope.
- Consistency giữa các query.
- Sorting và pagination.
- Locking hoặc snapshot semantics nếu cần.
- Query latency.
- Kích thước kết quả.

Không giả định đọc dữ liệu luôn không có rủi ro.

### 6.2. Không chuyển một nửa transaction

Nếu một use case cập nhật hai bảng phải atomic, không chuyển riêng repository đầu tiên sang R2DBC trong khi repository thứ hai vẫn ghi JDBC mà vẫn kỳ vọng một transaction chung.

R2dbcTransactionManager quản lý ConnectionFactory R2DBC. Transaction manager JDBC quản lý DataSource JDBC. Hai manager riêng không tự tạo một transaction ACID chung.

Hãy chuyển toàn bộ phần ghi thuộc cùng transaction boundary trong một slice, hoặc thiết kế một quy trình phối hợp có outbox/saga nếu hai resource phải tách biệt.

## 7. Khác biệt quan trọng khi chuyển từ JDBC/JPA sang R2DBC

### 7.1. Blocking và non-blocking

JDBC là API blocking. Khi gọi query, thread thường chờ kết quả. R2DBC là API reactive, thao tác được biểu diễn bằng Publisher và kết quả được phát khi subscription thực thi.

Ví dụ JDBC:

~~~java
Order order = jdbcTemplate.queryForObject(
    "SELECT id, status FROM orders WHERE id = ?",
    mapper,
    orderId
);
~~~

Ví dụ R2DBC:

~~~java
Mono<Order> order = orderRepository.findById(orderId);
~~~

Không chỉ thay kiểu trả về. Phải xem lại:
- Threading.
- Subscription lifecycle.
- Error propagation.
- Cancellation.
- Backpressure.
- Transaction context.
- Các API downstream có blocking hay không.

Không gọi block() trong event-loop để giữ cảm giác code tuần tự như JDBC.

### 7.2. JPA persistence context không có bản sao trực tiếp

JPA EntityManager có persistence context, dirty checking, lazy loading và cascade semantics. Spring Data Relational R2DBC không cung cấp một persistence context giống JPA.

Trong R2DBC:
- Thay đổi object trong bộ nhớ không tự động được flush chỉ vì transaction còn mở.
- Phải gọi repository save hoặc thao tác ghi tương ứng.
- Không có lazy loading theo cơ chế proxy JPA.
- Quan hệ giữa entity không tự động được load theo cùng mô hình.
- Cascade persistence không nên được giả định như JPA.
- Cần thiết kế query và aggregate boundary rõ hơn.

Ví dụ với JPA, code có thể thay đổi entity đã managed rồi commit để dirty checking ghi xuống database. Với R2DBC, hãy gọi save tường minh:

~~~java
return orderRepository.findById(orderId)
    .flatMap(order -> {
        order.setStatus("CONFIRMED");
        return orderRepository.save(order);
    });
~~~

### 7.3. Generated ID và giá trị database sinh

JPA có nhiều chiến lược ID generation và lifecycle callback. R2DBC phụ thuộc khả năng generated value của database/driver và mapping strategy.

Hãy kiểm chứng:
- ID có được sinh khi insert không.
- Entity trả về có chứa ID không.
- Version được cập nhật thế nào.
- Default value ở database có được đọc lại không.
- Trigger hoặc generated column có được trả về qua RETURNING/driver support không.

Không giả định entity đầu vào sau save luôn được mutate giống implementation cũ. Hãy sử dụng giá trị entity mà repository phát ra và kiểm tra behavior của database/driver.

### 7.4. Mapping và conversion

Cần kiểm tra từng kiểu dữ liệu:
- Decimal precision và scale.
- LocalDate, LocalDateTime, Instant và timezone.
- Boolean.
- Enum.
- UUID.
- JSON hoặc kiểu database đặc thù.
- Binary data.
- Null và default.
- Tên bảng/cột, quoting và schema.

Một mapping có thể chạy mà không lỗi nhưng vẫn làm tròn decimal hoặc đổi timezone. Kiểm thử nên so sánh giá trị đã đọc lại từ database, không chỉ object trước khi save.

### 7.5. Query và pagination

JPA Specification, Criteria API, native query và Spring Data repository method không phải lúc nào cũng chuyển một-một sang R2DBC.

Hãy kiểm tra:
- SQL được sinh ra.
- Bind marker theo driver.
- Null semantics.
- Case sensitivity.
- Collation.
- LIKE và wildcard escaping.
- ORDER BY và null ordering.
- LIMIT/OFFSET.
- Count query.
- Join và projection.

Nếu phải viết lại query, hãy dùng test với dữ liệu biên để xác nhận semantics, không chỉ so sánh chuỗi SQL.

### 7.6. Transaction và propagation

JDBC/JPA thường dùng transaction gắn với thread. Reactive transaction R2DBC được truyền theo Reactor Context.

Cần kiểm tra:
- R2dbcTransactionManager được chọn đúng.
- Publisher được trả về từ service method transactional.
- Không tự subscribe trong service.
- Không gọi block().
- Các repository cùng dùng ConnectionFactory tương ứng.
- Lỗi truyền tới transaction boundary để rollback.
- Side effect ngoài database không bị hiểu nhầm là rollback được.

### 7.7. Locking và optimistic concurrency

Nếu JPA dùng @Version, R2DBC Spring Data Relational cũng có hỗ trợ optimistic locking qua @Version cho entity mapping path tương ứng. Tuy nhiên, các câu SQL trực tiếp hoặc update custom không tự động được bảo vệ bởi @Version.

Hãy kiểm tra:
- Version ban đầu.
- Version sau insert/update.
- Exception khi stale update.
- Hành vi retry.
- Custom SQL có điều kiện version nếu cần.
- Các writer ngoài Spring Data có tuân thủ cùng bất biến hay không.

### 7.8. Callbacks và auditing

Entity callbacks của Spring Data Relational có phạm vi theo mapping lifecycle. Không giả định chúng thay thế mọi JPA entity listener hoặc được chạy cho SQL trực tiếp qua DatabaseClient.

Đối chiếu từng quy tắc:
- createdAt/updatedAt.
- createdBy/modifiedBy.
- Chuẩn hóa field trước mapping.
- Giá trị transient sau khi đọc.
- Audit event.
- Callback thứ tự và side effect.

Nếu một quy tắc phải áp dụng trên mọi đường ghi, đặt nó ở service/domain policy hoặc database constraint/mechanism phù hợp, không chỉ ở callback.

## 8. Kiểm chứng query và kết quả dữ liệu

### 8.1. So sánh trên cùng một snapshot dữ liệu

Để so sánh implementation cũ và mới, cả hai cần đọc cùng một trạng thái dữ liệu hoặc fixture tương đương.

Có thể:
- Seed hai database test giống nhau.
- Reset database giữa hai lượt chạy.
- Chạy hai query trên một database dùng chung nếu chúng chỉ đọc và không tạo side effect.
- Dùng snapshot hoặc transaction isolation phù hợp với mục tiêu kiểm thử.

Nếu dữ liệu thay đổi giữa hai lần chạy, khác biệt kết quả chưa chắc do implementation.

### 8.2. Chuẩn hóa kết quả trước khi so sánh

Không so sánh object bằng cách serialize tùy tiện nếu response chứa field không ổn định như:
- Timestamp hiện tại.
- Random ID.
- Thứ tự collection không được quy định.
- Trace ID.
- Giá trị generated theo môi trường.

Hãy chuẩn hóa những field không thuộc contract, nhưng không loại bỏ khác biệt có ý nghĩa nghiệp vụ như:
- Amount.
- Currency.
- Status.
- Tenant.
- Owner.
- Version khi version là một phần của contract.
- Số lượng bản ghi.
- Thứ tự nếu API cam kết ordering.

### 8.3. So sánh query result có thứ tự

Nếu API có sort contract, hãy so sánh danh sách theo đúng thứ tự. Nếu thứ tự không được cam kết, so sánh tập hợp theo khóa ổn định và ghi rõ contract đó.

Không dùng HashSet để so sánh khi thứ tự là một phần của hành vi.

### 8.4. So sánh cả dữ liệu sau khi ghi

Đối với use case ghi:
1. Chạy command trên database fixture của implementation cũ.
2. Chạy command tương đương trên fixture của R2DBC.
3. Đọc lại các bảng liên quan.
4. Chuẩn hóa field kỹ thuật không thuộc contract.
5. So sánh trạng thái cuối, audit và outbox.
6. Kiểm tra số lần side effect được tạo.

Response giống nhau chưa chứng minh dữ liệu được lưu giống nhau. Một implementation có thể trả response đúng nhưng ghi thiếu bảng phụ hoặc version.

## 9. Contract test dùng chung cho hai implementation

Nếu có abstraction như OrderReader, có thể viết contract test để chạy cùng một bộ test trên JDBC adapter và R2DBC adapter.

Ví dụ cấu trúc:

~~~java
abstract class OrderReaderContractTest {

    protected abstract OrderReader orderReader();

    protected abstract void resetAndSeed();

    @BeforeEach
    void setUp() {
        resetAndSeed();
    }

    @Test
    void shouldReturnOrderWithinTenant() {
        StepVerifier.create(
                orderReader().findDetails(1001L, TenantId.of("tenant-a"))
            )
            .assertNext(details -> {
                assertThat(details.id()).isEqualTo(1001L);
                assertThat(details.tenantId().value())
                    .isEqualTo("tenant-a");
            })
            .verifyComplete();
    }

    @Test
    void shouldNotExposeAnotherTenantOrder() {
        StepVerifier.create(
                orderReader().findDetails(2002L, TenantId.of("tenant-a"))
            )
            .verifyComplete();
    }
}
~~~

Một lớp con có thể cấu hình JDBC adapter, lớp khác cấu hình R2DBC adapter. Với implementation JDBC đồng bộ, có thể dùng một contract interface đồng bộ riêng hoặc adapter test phù hợp; không cần ép cả hai implementation vào một abstraction reactive giả tạo.

Contract test nên tập trung vào kết quả quan sát được. Các test riêng cho transaction, pool và cancellation vẫn cần thiết vì hai công nghệ có lifecycle khác nhau.

## 10. Kiểm thử transaction tương đương

Với use case ghi nhiều bảng, cần chứng minh các thay đổi phải atomic thực sự atomic.

Ví dụ nghiệp vụ tạo order:
- Ghi order.
- Ghi order item.
- Trừ inventory.
- Ghi outbox event.

Test thành công xác nhận tất cả dữ liệu xuất hiện. Test lỗi cố ý làm bước cuối thất bại rồi đọc lại database để xác nhận các bước trước đã rollback.

Với R2DBC:

~~~java
@Test
void shouldRollbackAllWritesWhenOutboxFails() {
    StepVerifier.create(orderService.create(commandThatFailsOutbox))
        .expectError()
        .verify();

    StepVerifier.create(orderRepository.findByBusinessKey(command.key()))
        .verifyComplete();

    StepVerifier.create(inventoryRepository.findById(productId))
        .assertNext(inventory ->
            assertThat(inventory.getAvailable()).isEqualTo(10)
        )
        .verifyComplete();
}
~~~

Ví dụ cần được điều chỉnh theo kiểu kết quả repository và dữ liệu fixture. Test phải quan sát trạng thái sau khi service publisher kết thúc, tránh một transaction test bên ngoài che khuất kết quả commit/rollback của service.

### 10.1. Kiểm tra transaction manager đúng nguồn

Nếu ứng dụng có JDBC và R2DBC cùng tồn tại trong giai đoạn chuyển tiếp, hãy xác nhận mỗi use case dùng đúng transaction manager.

Một @Transactional JDBC không tự quản lý thao tác R2DBC. Một R2dbcTransactionManager không tự quản lý JDBC connection.

Không đánh dấu migration thành công chỉ vì test service chạy qua; cần kiểm tra dữ liệu được ghi bằng đúng resource và transaction boundary.

### 10.2. Side effect ngoài database

Nếu use case gửi event, email hoặc gọi payment:
- Xác định thời điểm side effect xảy ra.
- Xác nhận số lần thực hiện.
- Kiểm tra retry và idempotency.
- Không giả định rollback database hoàn tác hệ thống bên ngoài.
- Dùng outbox nếu cần ghi nhận sự kiện nguyên tử với dữ liệu local.

Hành vi side effect là một phần của contract nghiệp vụ.

## 11. Shadow read và so sánh kết quả

Với một số chức năng đọc, có thể chạy implementation cũ làm nguồn trả response và chạy implementation mới ở chế độ shadow để so sánh.

Luồng khái niệm:

~~~text
                Request đọc
                    |
                    v
              Read service
                    |
          +---------+---------+
          |                   |
          v                   v
      JDBC reader         R2DBC reader
          |                   |
          v                   v
      Kết quả cũ          Kết quả mới
          |                   |
          v                   v
       Response           Compare/log
          |
          v
       Client
~~~

Shadow read chỉ phù hợp khi query mới không tạo side effect. Cần xem xét:
- Tăng gấp đôi tải database.
- Dữ liệu có thay đổi giữa hai lần đọc.
- Cùng transaction snapshot hay không.
- Không để lỗi shadow làm hỏng response chính.
- Không log dữ liệu nhạy cảm khi so sánh.
- Giới hạn tỷ lệ request được shadow.
- Theo dõi chênh lệch theo loại field và query.

Nếu hai query chạy trên cùng database nhưng ở hai thời điểm khác nhau, kết quả có thể khác vì dữ liệu vừa thay đổi. Có thể dùng fixture/snapshot trong test hoặc chỉ shadow những truy vấn có semantics phù hợp.

Không shadow write bằng cách thực thi cả implementation JDBC và R2DBC trên production. Điều đó có thể tạo dữ liệu trùng, phát event hai lần hoặc trừ tồn kho hai lần.

## 12. Tránh dual-write khi chuyển write path

Trong giai đoạn migration, một ý tưởng dễ xuất hiện là ghi đồng thời bằng JDBC và R2DBC để so sánh.

Đây là dual-write và thường nguy hiểm nếu không có một giao thức nhất quán:
- JDBC commit thành công nhưng R2DBC thất bại.
- R2DBC commit thành công nhưng JDBC thất bại.
- Một bên retry và tạo duplicate.
- Hai bên cập nhật version khác nhau.
- Side effect bị phát hai lần.
- Không có transaction chung bao phủ cả hai resource.

Nếu cần kiểm chứng write path mới, ưu tiên:
- Test trên database fixture riêng.
- Chạy replay trên bản sao dữ liệu đã ẩn danh.
- Chạy migration rehearsal ở staging.
- Chuyển một nhóm request sang implementation mới bằng feature flag.
- So sánh trạng thái sau khi chỉ một implementation ghi dữ liệu.

Nếu có lý do bắt buộc phải ghi nhiều nơi, hãy thiết kế outbox, CDC hoặc quy trình reconciliation có idempotency và ownership rõ ràng. Không dùng hai lần save độc lập như một chiến lược migration.

## 13. Chuyển traffic bằng feature flag hoặc routing

Khi slice đã được kiểm chứng, có thể chuyển traffic theo từng bước:

1. Tắt implementation mới mặc định.
2. Bật cho môi trường test/staging.
3. Bật cho một nhóm tenant hoặc tỷ lệ nhỏ nếu hệ thống hỗ trợ.
4. Theo dõi error rate, latency, pool metrics và data discrepancy.
5. Tăng tỷ lệ theo các checkpoint.
6. Chuyển toàn bộ traffic khi đạt tiêu chí.
7. Giữ khả năng quay lại trong khoảng thời gian được xác định.

Ví dụ abstraction chọn implementation:

~~~java
@Service
public class OrderReaderRouter implements OrderReader {

    private final OrderReader jdbcReader;
    private final OrderReader r2dbcReader;
    private final MigrationFlags flags;

    public OrderReaderRouter(
            JdbcOrderReader jdbcReader,
            R2dbcOrderReader r2dbcReader,
            MigrationFlags flags) {
        this.jdbcReader = jdbcReader;
        this.r2dbcReader = r2dbcReader;
        this.flags = flags;
    }

    @Override
    public Mono<OrderDetails> findDetails(
            long orderId,
            TenantId tenantId) {

        if (flags.useR2dbcOrderReader()) {
            return r2dbcReader.findDetails(orderId, tenantId);
        }

        return jdbcReader.findDetails(orderId, tenantId);
    }
}
~~~

Ví dụ giả định cả hai reader được bọc bởi một contract trả Mono. Nếu JDBC implementation blocking, nó phải được cô lập trên scheduler dành cho blocking trong thời gian chuyển tiếp; không thực thi trực tiếp trên WebFlux event-loop.

Feature flag cần:
- Có owner.
- Có giá trị mặc định an toàn.
- Có audit thay đổi nếu cần.
- Có cách bật/tắt nhanh.
- Không tạo nhánh migration tồn tại vĩnh viễn.
- Có ngày hoặc tiêu chí xóa flag.

## 14. Tiêu chí chấp nhận cho mỗi slice

Không nên chuyển traffic chỉ vì code compile hoặc unit test pass.

Một slice nên có các tiêu chí định lượng và có thể kiểm tra:

| Nhóm | Ví dụ tiêu chí |
|---|---|
| Correctness | Response và trạng thái database khớp contract |
| Security | Tenant scope và authorization được giữ |
| Query | Filter, sort, null và pagination tương đương |
| Transaction | Rollback/commit đúng ở mọi nhánh lỗi |
| Concurrency | Version/constraint bảo vệ cập nhật cạnh tranh |
| Side effects | Event và outbox không bị tạo trùng |
| Reliability | Timeout/cancel không để connection leak |
| Performance | p95/p99 và throughput đáp ứng SLO |
| Capacity | Pool, database session và memory nằm trong ngân sách |
| Operations | Metrics, logs và alert đủ để chẩn đoán |
| Rollback | Có thể chuyển lại implementation cũ trong điều kiện đã xác định |

Ngưỡng cụ thể phải theo SLO và baseline của hệ thống. Không đặt một con số chung cho mọi chức năng.

### 14.1. Correctness gate

Ví dụ:
- Tất cả contract test pass.
- Test biên về null, sort và pagination pass.
- Không có chênh lệch dữ liệu chưa giải thích.
- Test transaction rollback pass.
- Test optimistic locking và idempotency pass nếu use case cần.

### 14.2. Performance gate

So sánh trên workload tương đương:
- Throughput.
- p50/p95/p99 latency.
- CPU và heap.
- Connection acquired/pending.
- Database query latency.
- Số connection toàn hệ thống.
- Error và timeout rate.

R2DBC không đảm bảo ứng dụng nhanh hơn JDBC trong mọi workload. Nếu phần lớn thời gian nằm ở query hoặc database, thay API truy cập không tự làm query nhanh hơn. Mục tiêu migration có thể là khả năng mở rộng concurrency hoặc mô hình reactive xuyên suốt; hãy đo đúng mục tiêu đó.

### 14.3. Operational gate

Xác nhận:
- Có dashboard cho pool và query.
- Có log lỗi đủ ngữ cảnh nhưng không lộ dữ liệu nhạy cảm.
- Có tracing cho use case quan trọng.
- Có alert cho acquire timeout, query timeout và error rate.
- Có hướng dẫn rollback.
- Có người chịu trách nhiệm theo dõi giai đoạn rollout.

## 15. Kế hoạch rollback

Rollback không đơn giản là đổi feature flag về implementation cũ. Cần xem schema, dữ liệu và side effect có tương thích ngược không.

Trước khi chuyển slice, xác định:
- JDBC implementation cũ còn đọc/ghi được schema mới không?
- Migration schema có additive và tương thích ngược không?
- Có cột mới bắt buộc mà code cũ không biết không?
- Dữ liệu mới có format mà code cũ không hiểu không?
- Event mới có được consumer cũ hiểu không?
- Có thể dừng worker mới mà không mất outbox event không?
- Có cần backfill hoặc reconciliation trước khi quay lại không?

### 15.1. Ưu tiên schema expand-contract

Một quy trình thường dùng:

1. Expand: thêm cột/bảng/index mới theo cách code cũ vẫn hoạt động.
2. Deploy code có thể hiểu schema cũ và mới nếu cần.
3. Chuyển chức năng sang R2DBC.
4. Theo dõi và hoàn tất backfill.
5. Contract: chỉ xóa schema cũ sau khi không còn code cũ phụ thuộc.

Không xóa hoặc đổi tên cột ngay trong cùng release chuyển adapter nếu rollback vẫn cần code cũ.

### 15.2. Khi dữ liệu đã được ghi bởi implementation mới

Nếu implementation mới ghi dữ liệu có semantics khác, quay lại implementation cũ có thể không an toàn. Cần kiểm tra:
- Cột mới có giá trị default hợp lệ không.
- Version có cùng semantics không.
- Event mới có thể được consumer cũ xử lý không.
- Có dữ liệu cần chuyển đổi ngược không.
- Có thao tác ngoài database không thể hoàn tác không.

Rollback phải dựa trên khả năng tương thích dữ liệu, không chỉ dựa trên khả năng khởi động lại binary cũ.

## 16. Theo dõi và so sánh sau khi chuyển

Trong giai đoạn đầu sau cutover, theo dõi riêng slice vừa chuyển:

- Request rate.
- Error rate theo loại exception.
- p95/p99 latency.
- Query duration.
- Acquire wait và pool pending.
- Transaction duration.
- Optimistic locking conflict.
- Rows returned và response bytes.
- Outbox lag và retry count.
- Data discrepancy nếu có đối chiếu.

So sánh với baseline trước migration theo cùng khung giờ và workload tương đương. Một thay đổi traffic hoặc dữ liệu có thể làm so sánh không công bằng.

Khi có sự cố:
1. Xác định ảnh hưởng thuộc slice nào.
2. Kiểm tra metric và trace.
3. Xác định có phải sai dữ liệu, timeout, pool saturation hay transaction.
4. Quyết định tắt flag hay tiếp tục điều tra.
5. Giữ log và dữ liệu cần thiết để tái hiện.
6. Chỉ mở rộng rollout khi nguyên nhân đã được hiểu và khắc phục.

Không dùng một metric tổng toàn ứng dụng để kết luận slice mới hoạt động tốt. Cần tag theo use case/implementation ở mức có cardinality kiểm soát.

## 17. Ví dụ kế hoạch migration một chức năng tìm kiếm order

Giả sử hiện tại có một API tìm kiếm order sử dụng JPA Specification.

### Bước 1: Ghi nhận contract

Request:
- Keyword tùy chọn.
- Status tùy chọn.
- Khoảng ngày.
- Page và size.
- Sort field và direction.

Response:
- Danh sách OrderSummary.
- Total elements.
- Current page.
- Page size.

Ghi lại behavior của implementation hiện tại cho:
- Keyword null/blank.
- Ngày bắt đầu/kết thúc.
- Sort mặc định.
- Page size quá lớn.
- Tenant khác.
- Không có kết quả.

### Bước 2: Tạo R2DBC query

Dùng DTO và allowlist cho filter/sort. Dùng DatabaseClient hoặc R2dbcEntityTemplate tùy độ phức tạp. Bind tất cả giá trị và đặt LIMIT/OFFSET ở database.

~~~java
public Flux<OrderSummary> search(
        SearchCriteria criteria,
        TenantId tenantId,
        int page,
        int size) {

    int limit = validateSize(size);
    long offset = Math.multiplyExact((long) page, limit);

    return databaseClient.sql("""
            SELECT id, status, created_at
            FROM orders
            WHERE tenant_id = :tenantId
              AND (:status IS NULL OR status = :status)
            ORDER BY created_at DESC, id DESC
            LIMIT :limit OFFSET :offset
            """)
        .bind("tenantId", tenantId.value())
        .bind("status", criteria.status())
        .bind("limit", limit)
        .bind("offset", offset)
        .map((row, metadata) -> new OrderSummary(
            row.get("id", Long.class),
            row.get("status", String.class),
            row.get("created_at", LocalDateTime.class)
        ))
        .all();
}
~~~

Đoạn SQL trên minh họa ý tưởng. Cách bind giá trị null và cú pháp nullable parameter cần được xác nhận với driver/database cụ thể. Một số trường hợp nên xây predicate có điều kiện thay vì dùng biểu thức nullable trong SQL để tận dụng index tốt hơn.

### Bước 3: Kiểm tra count query

Nếu response cần total elements, count query phải áp dụng cùng tenant và filter:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status;
~~~

Không được bỏ tenant predicate ở count query. Nếu không, total count có thể tiết lộ số lượng dữ liệu của tenant khác dù danh sách đã được lọc đúng.

### Bước 4: Chạy contract test trên cả hai adapter

Dùng cùng fixture và xác nhận:
- Cùng tập order.
- Cùng thứ tự.
- Cùng total count.
- Cùng cách xử lý ngày và null.
- Không đọc chéo tenant.
- Page size và offset đúng.

### Bước 5: Đo hiệu năng

Chạy workload có page size mặc định và tối đa. So sánh:
- p95/p99.
- Query plan.
- Rows scanned/returned.
- Connection acquire wait.
- Database CPU.

### Bước 6: Chuyển traffic

Bật R2DBC cho staging, sau đó một nhóm tenant hoặc tỷ lệ request nhỏ. Theo dõi discrepancy và error rate. Nếu đạt gate, tăng tỷ lệ đến 100%.

### Bước 7: Xóa code cũ sau thời gian ổn định

Chỉ xóa JPA adapter và dependency liên quan khi:
- Không còn entry point nào dùng nó.
- Job và consumer đã được chuyển.
- Rollback window đã kết thúc.
- Schema không còn cần tương thích với implementation cũ.
- Dashboard xác nhận không còn traffic cũ.

## 18. Các lỗi thường gặp khi migration

| Lỗi hoặc nhầm lẫn | Hệ quả | Cách xử lý |
|---|---|---|
| Đổi toàn bộ ứng dụng trong một lần | Khó xác định nguyên nhân khi có regression | Di chuyển theo vertical slice |
| Chỉ kiểm tra code compile | Hành vi runtime có thể khác | Characterization và contract test |
| Cho rằng Mono chỉ là kiểu trả về mới của JDBC | Blocking vẫn chiếm thread | Chuyển sang R2DBC thực sự hoặc cô lập blocking trong giai đoạn chuyển tiếp |
| Mong đợi JPA dirty checking trong R2DBC | Thay đổi object không được lưu | Gọi save hoặc thao tác ghi tường minh |
| Giả định lazy loading/cascade giống JPA | Thiếu dữ liệu hoặc thiếu thao tác ghi | Thiết kế query và aggregate boundary rõ |
| Bỏ qua generated ID/default value | Response hoặc dữ liệu liên quan sai | Kiểm tra giá trị trả về sau insert |
| Chỉ so sánh response | Bảng phụ/outbox có thể ghi thiếu | Đọc lại toàn bộ trạng thái database liên quan |
| Dùng một transaction manager cho JDBC và R2DBC | Một phần thao tác nằm ngoài transaction dự kiến | Dùng manager đúng resource; không giả định cross-resource atomic |
| Chạy cả hai write implementation để so sánh | Duplicate write/event hoặc dữ liệu lệch | Dùng fixture/replay và chuyển một writer duy nhất |
| Shadow read không giới hạn | Tăng gấp đôi tải database | Sample và giới hạn shadow traffic |
| So sánh hai query trên dữ liệu đã thay đổi | Báo discrepancy giả | Dùng snapshot/fixture hoặc ghi nhận thời điểm |
| Chuyển query nhưng bỏ tenant filter | Lộ dữ liệu ngoài phạm vi | Contract test authorization cho mọi query |
| Giữ code cũ quá lâu sau cutover | Hai đường persistence khó bảo trì | Có tiêu chí và thời hạn xóa adapter cũ |
| Rollback code nhưng schema đã phá tương thích | Phiên bản cũ không chạy được | Dùng expand-contract và kế hoạch rollback dữ liệu |
| Chỉ đo throughput | Có thể bỏ sót tail latency, pool và error | Đo p95/p99, resource và correctness cùng nhau |

## 19. Checklist triển khai một vertical slice

Trước khi bắt đầu:
- Xác định use case và entry point.
- Lập danh sách repository, bảng, transaction và side effect.
- Ghi lại API contract.
- Viết characterization test.
- Xác định tiêu chí chấp nhận và rollback.

Trong lúc triển khai:
- Tạo R2DBC adapter.
- Xác nhận mapping, query và null semantics.
- Xác nhận transaction manager và ConnectionFactory.
- Không đưa blocking vào event-loop.
- Giữ tenant authorization.
- Giới hạn query, rows và timeout.
- Ghi nhận side effect và idempotency.

Trước khi chuyển traffic:
- Contract test pass.
- Integration test với database/driver mục tiêu pass.
- Transaction rollback test pass.
- Concurrency test pass nếu có cập nhật cạnh tranh.
- Performance test đáp ứng SLO.
- Metrics và alert đã có.
- Schema tương thích với phương án rollback.
- Feature flag/routing đã được kiểm thử.

Sau khi chuyển:
- Theo dõi error, latency và data discrepancy.
- Xác nhận không có traffic bất ngờ vào adapter cũ.
- Theo dõi pool và database capacity.
- Giữ rollback window theo kế hoạch.
- Xóa code cũ và flag khi đủ điều kiện.

## 20. Bài tập tự kiểm tra

### Bài 1: Chọn slice đầu tiên

Một hệ thống có chức năng xem chi tiết, tìm kiếm, tạo và xác nhận đơn hàng. Nên chọn chức năng nào trước?

Gợi ý: Chọn use case có contract rõ, ít side effect và dễ kiểm chứng. Không có một đáp án cố định; xem dependency và khả năng chuyển traffic độc lập.

### Bài 2: Characterization test

Vì sao cần test implementation cũ trước khi thay nó?

Gợi ý: Để ghi nhận hành vi thực tế chưa được tài liệu hóa, tạo baseline cho implementation mới và tránh vô tình thay đổi contract.

### Bài 3: JPA dirty checking

Code JPA thay đổi field của entity rồi commit mà không gọi save. Khi chuyển sang R2DBC, có thể giữ nguyên cách viết không?

Gợi ý: Không nên giả định như vậy. R2DBC không có persistence context/dirty checking giống JPA; cần gọi thao tác save tường minh.

### Bài 4: Blocking API

Một service JDBC được đổi chữ ký thành Mono nhưng bên trong vẫn gọi jdbcTemplate trực tiếp. Nó đã trở thành non-blocking chưa?

Gợi ý: Chưa. JDBC vẫn blocking. Nếu cần chuyển tiếp, cô lập trên scheduler phù hợp và ghi nhận debt; mục tiêu cuối là R2DBC hoặc kiến trúc phù hợp.

### Bài 5: Transaction boundary

Một use case cập nhật order và inventory trong cùng transaction. Có thể chuyển riêng order repository sang R2DBC và giữ inventory repository JDBC mà vẫn dùng một @Transactional để atomic không?

Gợi ý: Không. Hai transaction manager quản lý resource khác nhau; cần chuyển toàn bộ boundary hoặc thiết kế phối hợp khác.

### Bài 6: Shadow write

Có nên chạy cả JDBC và R2DBC write trên production để so sánh kết quả không?

Gợi ý: Không nên thực hiện dual-write tùy tiện. Dùng fixture/replay hoặc chuyển một writer duy nhất theo feature flag.

### Bài 7: Shadow read

Hai implementation đọc cùng một bảng nhưng kết quả khác vì dữ liệu thay đổi giữa hai lần query. Làm sao kiểm chứng công bằng?

Gợi ý: Dùng fixture/snapshot hoặc một cách đọc có consistency phù hợp; ghi nhận thời điểm và không xem mọi discrepancy là lỗi mapping.

### Bài 8: Generated ID

Sau insert, service cần ID để tạo outbox event. Nên dùng ID từ đâu?

Gợi ý: Dùng entity được phát ra từ publisher save và kiểm chứng driver/database trả generated value như mong đợi.

### Bài 9: Rollback

Sau cutover, code R2DBC ghi thêm một cột mới. Vì sao bật lại JDBC code cũ có thể không an toàn?

Gợi ý: Schema hoặc dữ liệu có thể không tương thích ngược. Cần expand-contract và kiểm tra behavior của code cũ với dữ liệu mới.

### Bài 10: Tiêu chí hoàn tất

Unit test pass và ứng dụng compile. Đã đủ điều kiện chuyển 100% traffic chưa?

Gợi ý: Chưa. Cần contract/integration test, transaction/concurrency, performance, security, metrics và rollback readiness.

## 21. Ghi nhớ

- Di chuyển từng chức năng theo vertical slice giúp giới hạn phạm vi và dễ kiểm chứng.
- Hành vi tương đương bao gồm API, business rules, mapping, query, transaction, concurrency, side effect, security và performance.
- Ghi inventory và dependency của mọi entry point, bao gồm job, consumer và SQL trực tiếp.
- Tạo characterization test trước khi thay implementation.
- Giữ application contract ổn định và thay adapter persistence ở phía dưới khi phù hợp.
- JDBC blocking không trở thành non-blocking chỉ vì bọc trong Mono.
- R2DBC không có JPA persistence context, dirty checking, lazy loading và cascade semantics giống JPA.
- Kiểm tra generated ID, default value, version, null, decimal, timezone và query semantics.
- Transaction R2DBC dùng Reactor Context và R2dbcTransactionManager; không giả định transaction JDBC bao phủ nó.
- Chuyển toàn bộ thao tác thuộc cùng transaction boundary trong một slice hoặc thiết kế outbox/saga.
- So sánh cả response lẫn trạng thái database và side effect.
- Contract test có thể dùng chung cho nhiều adapter nếu abstraction phản ánh đúng hợp đồng.
- Shadow read có thể giúp so sánh read path nhưng phải giới hạn tải và kiểm soát snapshot.
- Tránh dual-write production không có giao thức nhất quán.
- Dùng feature flag/canary và tiêu chí chấp nhận định lượng để chuyển traffic.
- Schema expand-contract và rollback plan phải được chuẩn bị trước cutover.
- Đo correctness, p95/p99, pool, database và error rate cùng nhau.
- Chỉ xóa implementation cũ sau khi xác nhận không còn traffic và rollback window đã kết thúc.

Migration sang Spring Data Relational R2DBC là một chuỗi thay đổi có thể kiểm chứng, không phải một lần thay thư viện. Mỗi chức năng cần có contract rõ, test ghi nhận hành vi cũ, implementation mới và bằng chứng rằng dữ liệu, transaction, bảo mật cùng hiệu năng vẫn đáp ứng yêu cầu. Di chuyển từng vertical slice, chuyển traffic theo từng bước và giữ khả năng rollback tương thích sẽ giúp quá trình chuyển đổi có thể kiểm soát được.

