# Kiểm thử repository với cơ sở dữ liệu và cơ chế lưu trữ thực tế

Repository là ranh giới giúp tầng ứng dụng hoặc domain truy cập dữ liệu mà không cần biết chi tiết SQL, ORM hay hệ quản trị cơ sở dữ liệu. Unit test với repository giả có thể kiểm tra cách ca sử dụng phối hợp các thành phần, nhưng không chứng minh repository thật truy vấn đúng, ánh xạ dữ liệu đúng hoặc tuân thủ hành vi của hệ quản trị đang dùng. Vì vậy, cần có kiểm thử tích hợp repository với cơ sở dữ liệu và cơ chế lưu trữ thực tế của ứng dụng.

Trong module SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED — học tổ chức phần mềm theo kiến trúc phân tầng — bài học này tập trung vào cách kiểm tra adapter lưu trữ ở đúng ranh giới: dùng engine phù hợp, schema và migration thực tế, kiểm tra ánh xạ và truy vấn, transaction, constraint, phân trang và hành vi đồng thời. Mục tiêu là xác minh hợp đồng lưu trữ trong môi trường gần với production, đồng thời giữ cho test có dữ liệu độc lập, kết quả lặp lại được và thời gian chạy hợp lý.

## 1. Vì sao cần kiểm thử repository với storage thực?

Một unit test có thể mock OrderRepository và xác minh PlaceOrderService gọi save(order). Điều đó kiểm tra luồng điều phối của application, nhưng không kiểm tra các vấn đề có thể chỉ xuất hiện khi repository thật làm việc với database:

- Tên bảng, tên cột hoặc kiểu dữ liệu trong mapping không khớp schema.
- Quan hệ JPA, cascade, orphan removal hoặc fetch strategy không hoạt động như mong đợi.
- JPQL, native SQL hoặc derived query sai cú pháp hay cho kết quả khác dự kiến.
- Unique constraint, khóa ngoại, CHECK constraint hoặc NOT NULL không được áp dụng như thiết kế.
- Giá trị enum, thời gian, số thập phân hoặc kiểu định danh bị chuyển đổi sai.
- Transaction, flush, locking và hành vi đồng thời khác với giả định của ứng dụng.
- Phân trang hoặc sắp xếp cho kết quả không ổn định khi có nhiều bản ghi trùng khóa sắp xếp.

Một cơ sở dữ liệu nhúng có thể chạy nhanh và phù hợp cho một số test, nhưng nó không luôn tương đương PostgreSQL, MySQL, SQL Server hoặc hệ quản trị production. Khác biệt về dialect SQL, kiểu dữ liệu, collation, constraint, isolation và locking có thể khiến test xanh trong môi trường nhúng nhưng ứng dụng lỗi khi triển khai.

Do đó, hãy chọn mức test theo điều cần xác minh. Unit test dùng fake/mock để kiểm tra application. Repository integration test dùng engine thật để kiểm tra adapter và mapping. Application integration test có thể khởi động Spring và kiểm tra transaction qua nhiều repository. Không cần biến mọi unit test thành test database; cần đặt test storage tại những ranh giới mà mock không thể xác minh.

## 2. Phạm vi của repository integration test

Một repository integration test thường khởi tạo repository thật, persistence provider thật và database engine thật. Nó nên kiểm tra các hành vi mà hợp đồng repository công bố:

| Hành vi | Điều cần xác minh |
|---|---|
| Lưu và tải | Bản ghi được ghi và đọc lại với giá trị, kiểu dữ liệu và quan hệ đúng. |
| Truy vấn theo điều kiện | Kết quả khớp bộ lọc, trạng thái, thời gian và điều kiện biên. |
| Cập nhật và xóa | Thay đổi được lưu; xóa có hành vi đúng với quan hệ và cascade. |
| Ràng buộc dữ liệu | Unique, foreign key, NOT NULL và CHECK được thực thi. |
| Mapping ORM | Enum, ngày giờ, decimal, embedded/value type và quan hệ được ánh xạ đúng. |
| Phân trang và sắp xếp | Page size, tổng số bản ghi, thứ tự và tie-breaker chính xác. |
| Transaction | Flush, rollback và ranh giới commit có hành vi phù hợp. |
| Đồng thời | Optimistic/pessimistic locking hoặc cập nhật có điều kiện ngăn trạng thái sai. |

Không phải test nào cũng cần kiểm tra tất cả các mục. Hãy tập trung vào hợp đồng thực tế của repository và các rủi ro do engine, ORM hoặc schema tạo ra. Các quy tắc nghiệp vụ phức tạp vẫn nên được kiểm tra trong domain/application test; repository test chỉ xác minh phần lưu trữ và truy vấn liên quan.

## 3. Chọn đúng database engine cho test

Nếu production dùng PostgreSQL, test quan trọng về SQL, mapping, constraint hoặc locking nên chạy trên PostgreSQL. Nếu production dùng MySQL, hãy kiểm tra trên MySQL. Với MongoDB, Redis hoặc một cơ chế lưu trữ khác, hãy dùng đúng loại server và phiên bản tương thích với production khi hành vi của nó là điều cần xác minh.

Có thể dùng Testcontainers để tạo database tạm thời trong container cho mỗi test suite hoặc test class. Ví dụ dưới đây dùng PostgreSQL và Spring Boot 3.1 trở lên, nơi có annotation ServiceConnection để Spring Boot lấy thông tin kết nối từ container:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
@Testcontainers
class OrderRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    OrderJpaRepository orders;

    @Autowired
    EntityManager entityManager;

    @Test
    void savesAndLoadsOrder() {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();

        OrderJpaEntity order = OrderJpaEntity.pending(
            orderId, customerId, new BigDecimal("125.50"));

        orders.save(order);
        entityManager.flush();
        entityManager.clear();

        OrderJpaEntity loaded = orders.findById(orderId)
            .orElseThrow();

        assertEquals(customerId, loaded.getCustomerId());
        assertEquals(new BigDecimal("125.50"), loaded.getTotal());
        assertEquals(OrderStatus.PENDING, loaded.getStatus());
    }
}
~~~

Các annotation có vai trò khác nhau:

- @DataJpaTest tạo test slice cho JPA, cấu hình repository và EntityManager cần thiết.
- @Testcontainers quản lý vòng đời container trong JUnit.
- @Container khai báo container mà test sử dụng.
- @ServiceConnection cung cấp cấu hình kết nối cho Spring Boot từ container.
- @AutoConfigureTestDatabase với Replace.NONE ngăn test slice tự thay datasource bằng database nhúng.

Đoạn mã giả định dự án đã khai báo dependency test cho Spring Boot, JUnit, Testcontainers PostgreSQL và có các lớp OrderJpaEntity, OrderJpaRepository phù hợp. Nếu dùng Spring Boot trước phiên bản 3.1, có thể cấu hình URL, username và password bằng DynamicPropertySource thay cho ServiceConnection.

Một cấu hình Maven minh họa cho dependency test (phiên bản nên được quản lý bởi Spring Boot BOM hoặc version catalog của dự án):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
~~~

Testcontainers cần môi trường có thể chạy container, thường là Docker Engine hoặc môi trường tương thích. Nếu môi trường CI không cung cấp runtime container, có thể dùng database test được quản lý riêng, nhưng phải bảo đảm mỗi lần chạy có schema và dữ liệu độc lập.

## 4. Kiểm tra lưu, tải và mapping thật

Một test lưu/tải không nên chỉ xác minh object trả về từ phương thức save có cùng giá trị với object đầu vào. Với ORM, object có thể vẫn nằm trong persistence context và được trả lại từ bộ nhớ mà chưa được ghi hoặc đọc từ database.

Trong test JPA, gọi flush để buộc Hibernate gửi thay đổi xuống database, sau đó clear persistence context để lần đọc tiếp theo phải lấy dữ liệu từ storage:

~~~java
@Test
void persistsOrderLinesAndReloadsThem() {
    OrderJpaEntity order = OrderJpaEntity.withLines(
        UUID.randomUUID(),
        UUID.randomUUID(),
        List.of(
            OrderLineJpaEntity.of(UUID.randomUUID(), 2),
            OrderLineJpaEntity.of(UUID.randomUUID(), 1)
        )
    );

    orders.save(order);
    entityManager.flush();
    entityManager.clear();

    OrderJpaEntity loaded = orders.findById(order.getId())
        .orElseThrow();

    assertEquals(2, loaded.getLines().size());
    assertEquals(2, loaded.getLines().get(0).getQuantity());
}
~~~

Ví dụ trên giả định phương thức withLines tạo entity và gắn quan hệ hai chiều đúng theo mapping. Nếu quan hệ JPA dùng mappedBy, helper phải gán cả phía sở hữu quan hệ để ORM ghi khóa ngoại đúng.

Kiểm tra reload giúp phát hiện lỗi mapping mà test chỉ nhìn object trong bộ nhớ có thể bỏ qua. Với quan hệ lazy, hãy truy cập quan hệ trong phạm vi persistence context hợp lệ hoặc chủ động dùng fetch query phù hợp. Đừng vô tình biến test thành kiểm tra lazy loading sau khi EntityManager đã đóng, trừ khi đó chính là hành vi cần xác minh.

Các kiểu dữ liệu cần kiểm tra cẩn thận gồm:

- BigDecimal: precision, scale và cách lưu số tiền; tránh so sánh tiền bằng double.
- Instant, LocalDateTime, OffsetDateTime: múi giờ, độ chính xác và quy ước lưu trữ.
- Enum: cách lưu tên hoặc ordinal; dùng STRING thường tránh việc đổi thứ tự enum làm thay đổi ý nghĩa dữ liệu cũ.
- UUID: kiểu cột và cách driver chuyển đổi.
- Value object/embedded type: các cột thành phần được ghi và đọc đúng.
- Quan hệ: khóa ngoại, cascade, orphan removal và thứ tự nạp dữ liệu.

## 5. Kiểm tra truy vấn, lọc, sắp xếp và phân trang

Một repository không chỉ lưu và tải theo ID. Các truy vấn tìm kiếm thường là phần quan trọng của hợp đồng dữ liệu. Ví dụ:

~~~java
public interface OrderJpaRepository
        extends JpaRepository<OrderJpaEntity, UUID> {

    Page<OrderJpaEntity> findByCustomerIdAndStatusOrderByCreatedAtDesc(
        UUID customerId,
        OrderStatus status,
        Pageable pageable
    );
}
~~~

Test nên tạo nhiều bản ghi với customer, status và thời điểm khác nhau, sau đó xác minh cả điều kiện lọc lẫn thứ tự:

~~~java
@Test
void filtersAndPagesOrdersInExpectedOrder() {
    UUID customerId = UUID.randomUUID();
    seedOrder(customerId, OrderStatus.PENDING, instant("2026-01-01T10:00:00Z"));
    seedOrder(customerId, OrderStatus.PENDING, instant("2026-01-02T10:00:00Z"));
    seedOrder(customerId, OrderStatus.CANCELLED, instant("2026-01-03T10:00:00Z"));
    entityManager.flush();
    entityManager.clear();

    Page<OrderJpaEntity> page = orders
        .findByCustomerIdAndStatusOrderByCreatedAtDesc(
            customerId,
            OrderStatus.PENDING,
            PageRequest.of(0, 1)
        );

    assertEquals(1, page.getContent().size());
    assertEquals(2, page.getTotalElements());
    assertEquals(instant("2026-01-02T10:00:00Z"),
        page.getContent().get(0).getCreatedAt());
}
~~~

Các hàm seedOrder và instant chỉ là helper minh họa. Khi nhiều bản ghi có cùng createdAt, nên thêm một tiêu chí sắp xếp ổn định như id để phân trang không thay đổi ngẫu nhiên giữa các lần truy vấn. Hãy kiểm tra trang đầu, trang cuối, trang rỗng, page size và tổng số phần tử khi hợp đồng repository yêu cầu.

Đừng chỉ dùng một bản ghi trong test truy vấn. Một điều kiện WHERE sai hoặc thiếu bộ lọc có thể vẫn trả kết quả đúng khi dataset quá đơn giản. Dữ liệu test nên có cả bản ghi khớp và không khớp, các giá trị biên và những trường hợp có thể gây nhầm lẫn.

## 6. Kiểm tra constraint và lỗi lưu trữ

Database là lớp bảo vệ quan trọng cho tính toàn vẹn dữ liệu, đặc biệt khi có nhiều tiến trình hoặc đường ghi. Test cần xác minh schema thực sự từ chối dữ liệu vi phạm các ràng buộc đã thiết kế.

Ví dụ, nếu email phải duy nhất, có thể kiểm tra unique constraint bằng cách flush sau lần lưu thứ hai:

~~~java
@Test
void rejectsDuplicateEmail() {
    users.save(UserJpaEntity.active("a@example.test"));
    entityManager.flush();

    users.save(UserJpaEntity.active("a@example.test"));

    assertThrows(DataIntegrityViolationException.class,
        entityManager::flush);
}
~~~

Trong một số cấu hình, ngoại lệ có thể xuất hiện ngay ở repository.save; trong cấu hình khác, nó chỉ xuất hiện lúc flush hoặc commit. Test nên chủ động flush để quan sát lỗi database tại thời điểm có thể dự đoán. Sau lỗi constraint, transaction hiện tại thường đã bị đánh dấu rollback-only; không nên tiếp tục dùng transaction đó để kiểm tra nhiều hành vi khác.

Các ràng buộc cần cân nhắc kiểm tra:

- UNIQUE: không cho phép trùng khóa nghiệp vụ.
- NOT NULL: trường bắt buộc không thể bị bỏ trống.
- FOREIGN KEY: không tạo dữ liệu con tham chiếu tới bản ghi không tồn tại.
- CHECK: giá trị phải nằm trong miền lưu trữ cho phép.
- Optimistic version: không ghi đè cập nhật mới hơn.
- Cascade/orphan removal: thêm hoặc xóa bản ghi con theo đúng vòng đời đã định nghĩa.

Không nên dựa duy nhất vào annotation JPA để suy ra schema production. Nếu ứng dụng dùng Flyway hoặc Liquibase, hãy chạy migration thật trong test và kiểm tra repository trên schema được tạo từ migration. Cấu hình tạo schema tự động từ entity có thể che giấu việc migration bị thiếu hoặc sai.

## 7. Transaction và rollback trong test

@DataJpaTest thường chạy mỗi test trong một transaction và rollback khi test kết thúc. Điều này giúp dữ liệu test không rò sang test khác, nhưng có thể che giấu một số vấn đề nếu test không hiểu transaction được quản lý như thế nào.

Một số điểm cần lưu ý:

- Thay đổi có thể chỉ nằm trong persistence context cho đến khi gọi flush.
- Flush kiểm tra câu SQL và nhiều constraint tức thời, nhưng constraint trì hoãn có thể chỉ được kiểm tra lúc commit.
- Test chạy trong transaction có thể không phản ánh chính xác hành vi của một request mới dùng transaction khác.
- Gọi phương thức @Transactional từ cùng một đối tượng có thể không đi qua proxy Spring, giống như khi chạy ứng dụng thật.
- Async task hoặc thread khác không tự tham gia transaction của test hiện tại.
- Test rollback cuối phương thức không chứng minh hành vi commit thành công.

Khi cần xác minh commit hoặc ranh giới transaction thực tế, có thể dùng một test không chạy trong transaction bao ngoài, hoặc chủ động điều khiển transaction test. Ví dụ với Spring Test:

~~~java
@Test
void committedDataIsVisibleToANewTransaction() {
    TestTransaction.flagForCommit();
    TestTransaction.end();

    // Bắt đầu transaction mới hoặc truy vấn qua một context mới
    // để xác minh dữ liệu đã được commit.
}
~~~

Ví dụ này chỉ minh họa cách điều khiển transaction của test; cần cấu hình test phù hợp và bảo đảm dữ liệu được tạo trong transaction đang kiểm tra. Với kiểm thử rollback, hãy xác minh dữ liệu không tồn tại sau khi transaction bị rollback bằng một transaction hoặc EntityManager mới.

Không nên mặc định mọi test repository phải kiểm tra commit. Hãy dùng rollback mặc định để cô lập dữ liệu cho test thông thường; chỉ tạo test commit/rollback chuyên biệt khi đó là một phần của hợp đồng cần bảo vệ.

## 8. Kiểm tra locking và truy cập đồng thời

Một test repository chạy tuần tự không phát hiện được mọi lỗi cạnh tranh dữ liệu. Nếu ứng dụng dùng optimistic locking, pessimistic locking hoặc cập nhật có điều kiện, cần có test kiểm tra hành vi tương ứng.

Với optimistic locking, hai transaction đọc cùng version, transaction thứ nhất cập nhật và commit, transaction thứ hai cố ghi từ version cũ. Test cần xác minh transaction thứ hai nhận lỗi xung đột thay vì ghi đè dữ liệu mới.

Với pessimistic locking, cần xác minh câu truy vấn lấy khóa và hành vi khi transaction khác muốn cập nhật cùng bản ghi. Những test này thường cần hai transaction độc lập, hai EntityManager hoặc hai thread, và đồng bộ hóa bằng latch/barrier thay vì dùng sleep để đoán thời điểm.

Một test concurrency nên:

1. Tạo dữ liệu ban đầu đã commit.
2. Khởi chạy hai transaction độc lập cùng đọc hoặc cập nhật tài nguyên.
3. Đồng bộ thời điểm để tạo ra tình huống tranh chấp có chủ đích.
4. Xác minh chỉ kết quả hợp lệ được commit hoặc một transaction nhận conflict.
5. Đọc lại trạng thái cuối cùng từ database và kiểm tra bất biến.

Không nên kiểm thử cạnh tranh bằng cách dùng chung một EntityManager hoặc cùng một transaction cho hai thread. Persistence context của JPA không được thiết kế để chia sẻ an toàn giữa các thread. Test concurrency cũng nên chạy riêng khi cần, vì có thể tốn thời gian và nhạy với tài nguyên CI.

## 9. Quản lý dữ liệu test để kết quả lặp lại được

Một repository test tốt phải độc lập với thứ tự chạy và dữ liệu của test khác. Một số thực hành hữu ích:

- Tạo ID và dữ liệu riêng cho mỗi test; không phụ thuộc một bản ghi có sẵn trong database dùng chung.
- Dùng transaction rollback cho test thông thường nếu phù hợp với cách test được cấu hình.
- Nếu test cần commit, dọn dữ liệu rõ ràng hoặc dùng schema/database riêng theo test suite.
- Không phụ thuộc thứ tự thực thi test và không dùng chung dữ liệu có thể bị nhiều test sửa đồng thời.
- Dùng clock cố định hoặc thời gian rõ ràng khi kiểm tra trường timestamp.
- Đặt tên dữ liệu có tính duy nhất để tránh va chạm constraint.
- Tránh cleanup bằng cách xóa toàn bộ bảng nếu test đang chạy song song trên cùng database.
- Chỉ dùng dữ liệu mẫu tĩnh khi nó được tạo và quản lý rõ ràng trong phạm vi test.

Nếu test chạy song song, mỗi worker hoặc suite cần schema/database riêng, hoặc dữ liệu có khóa riêng và cơ chế cleanup an toàn. Một container dùng chung có thể tiết kiệm thời gian khởi động nhưng cần tránh test xóa hoặc thay đổi dữ liệu của nhau.

## 10. Migration và cấu hình gần production

Repository test chỉ đáng tin khi schema mà nó sử dụng phản ánh cách ứng dụng được triển khai. Nếu production tạo schema bằng Flyway hoặc Liquibase, test tích hợp nên chạy chính các migration đó thay vì chỉ để Hibernate tự tạo bảng từ entity.

Một cấu hình thường gặp là bật migration trong profile test và đặt Hibernate ở chế độ validate hoặc không tự tạo schema. Cách cụ thể phụ thuộc Spring Boot, database và quy ước dự án. Hãy bảo đảm:

- Phiên bản database/container phù hợp với phiên bản production cần hỗ trợ.
- Migration được chạy từ trạng thái schema ban đầu sạch.
- Test phát hiện migration lỗi hoặc thiếu index/constraint.
- Kiểu dữ liệu, collation, timezone và extension cần thiết được cấu hình giống môi trường mục tiêu.
- Test không vô tình dùng H2 trong khi production dùng PostgreSQL nếu đang kiểm tra hành vi đặc thù PostgreSQL.

Không nhất thiết phải sao chép toàn bộ cấu hình production hoặc dữ liệu production vào test. Chỉ mô phỏng các đặc điểm kỹ thuật có ảnh hưởng tới hợp đồng repository. Không dùng dữ liệu cá nhân hoặc dữ liệu production nhạy cảm làm fixture test.

## 11. Chọn công cụ và mức kiểm thử phù hợp

Spring có một số test slice và công cụ khác nhau:

| Công cụ | Phạm vi phù hợp | Khi nên dùng |
|---|---|---|
| @DataJpaTest | Entity, repository JPA, EntityManager và cấu hình persistence liên quan. | Kiểm tra mapping, query, constraint và hành vi JPA. |
| @JdbcTest | JDBC components và JdbcTemplate. | Kiểm tra SQL, row mapper và repository dùng JDBC. |
| @SpringBootTest | Toàn bộ Spring application context. | Kiểm tra tích hợp repository với transaction manager, service, event hoặc cấu hình rộng hơn. |
| Testcontainers | Chạy database/broker/storage thật trong container. | Cần engine gần production và test có thể quản lý vòng đời môi trường. |
| Embedded database | Database nhúng như H2. | Test nhanh cho logic SQL/JPA đơn giản không phụ thuộc đặc tính riêng của production engine. |

Với MongoDB hoặc Redis, có thể dùng Testcontainers module tương ứng hoặc một instance test được quản lý riêng. Hãy kiểm tra đúng cơ chế lưu trữ mà repository đang sử dụng; một test với PostgreSQL không xác minh được hành vi của MongoDB, và ngược lại.

Đừng dùng @SpringBootTest cho mọi repository test nếu @DataJpaTest đã đủ. Test slice thường khởi động nhanh hơn và cho biết lỗi nằm ở mapping hoặc repository. Dùng full application context khi cần xác minh cấu hình transaction, security, event hoặc wiring giữa nhiều tầng.

## 12. Những sai lầm thường gặp

- **Mock repository trong test được gọi là repository integration test:** mock không chạy SQL, ORM hoặc database engine.
- **Dùng database nhúng nhưng kết luận production database hoạt động đúng:** dialect và hành vi có thể khác nhau.
- **Không flush hoặc clear persistence context:** test có thể chỉ kiểm tra object trong bộ nhớ thay vì dữ liệu đã lưu.
- **Dùng schema tự sinh thay cho migration production:** test không phát hiện migration thiếu hoặc sai.
- **Chỉ tạo một bản ghi để kiểm tra truy vấn:** điều kiện lọc và sắp xếp sai có thể không bị phát hiện.
- **Không kiểm tra constraint:** ứng dụng có thể dựa vào quy tắc mà database không bảo vệ.
- **Giả định rollback test bao phủ mọi tình huống:** commit, async và transaction độc lập cần test riêng.
- **Dùng sleep trong test concurrency:** kết quả phụ thuộc tốc độ máy và dễ chập chờn.
- **Dùng chung database test có dữ liệu không được cô lập:** test phụ thuộc thứ tự và có thể làm hỏng nhau.

## 13. Quy trình xây dựng repository test

Khi thêm hoặc thay đổi một repository, hãy thực hiện:

1. Xác định hợp đồng repository: phương thức lưu, tải, lọc, sắp xếp, phân trang và các ràng buộc mà nó phải giữ.
2. Chọn đúng storage engine và phiên bản cần xác minh; ưu tiên container hoặc môi trường test được quản lý có thể tái tạo.
3. Khởi tạo schema bằng migration giống production và cấu hình ORM phù hợp.
4. Viết test cho lưu/tải, mapping, truy vấn, constraint và các trường hợp biên.
5. Flush và clear persistence context khi cần chứng minh dữ liệu đã đi qua database.
6. Kiểm tra transaction, locking và đồng thời cho những hành vi có rủi ro.
7. Bảo đảm dữ liệu test được cô lập, cleanup an toàn và test có thể chạy độc lập.
8. Chạy test trong môi trường CI có storage phù hợp và ghi nhận phiên bản engine khi cần chẩn đoán.

Repository integration test là một phần của chiến lược kiểm thử phân tầng. Unit test xác minh quy tắc domain và điều phối application; repository test xác minh adapter lưu trữ với engine, schema và transaction thật; application integration test xác minh các tầng phối hợp qua cấu hình runtime. Khi test tập trung vào đúng hợp đồng và dùng storage phù hợp với production, nhóm có thể phát hiện sớm lỗi mapping, truy vấn và tính nhất quán mà mock không thể bộc lộ.

