# Kiểm thử repository và ánh xạ trên cơ sở dữ liệu thực phù hợp

Trong Domain-Driven Design (DDD), Repository tạo ranh giới giữa mô hình domain và cách lưu trữ Aggregate. Domain làm việc với Entity, Value Object và hành vi nghiệp vụ; persistence adapter chịu trách nhiệm chuyển đổi chúng thành hàng, cột, quan hệ và câu lệnh truy vấn. Ranh giới này chỉ đáng tin khi implementation thực sự lưu và nạp lại đúng mô hình.

Unit test với Repository giả (mock hoặc fake) hữu ích để kiểm tra Application Service điều phối use case. Nhưng nó không chứng minh SQL đúng, mapping ORM đúng, khóa ngoại được bảo vệ, transaction rollback như mong đợi hay Aggregate được tái tạo đầy đủ. Những hành vi đó phụ thuộc vào database, dialect SQL, ORM và cấu hình transaction thực tế.

Vì vậy, một hệ thống DDD cần kiểm thử Repository và mapping trên cơ sở dữ liệu thật phù hợp với môi trường triển khai. Cơ sở dữ liệu thật ở đây thường là một instance tạm thời chạy trong container với cùng engine và phiên bản gần production, chẳng hạn PostgreSQL cho production PostgreSQL. Test sẽ chạy migration, ghi Aggregate, flush, xóa persistence context, nạp lại rồi xác minh trạng thái và hành vi domain.

Bài viết giải thích phạm vi cần kiểm thử, cách chọn database test, cách tổ chức Integration Test với Spring Data JPA và Testcontainers, cách kiểm tra mapping Entity/Value Object/Aggregate, transaction, constraint, concurrency, truy vấn và migration. Mục tiêu là xác minh hợp đồng Repository trong điều kiện gần với thực tế mà không biến test thành bản sao của implementation.

## 1. Vì sao cần kiểm thử Repository bằng database thật?

Repository không chỉ là một interface có hai phương thức find và save. Implementation của nó thường phải giải quyết nhiều chi tiết có thể sai khi chạy với database:

- Ánh xạ Aggregate Root và các Entity con.
- Chuyển đổi Value Object thành cột hoặc cấu trúc nhúng.
- Tạo và khôi phục identity.
- Lưu quan hệ một-nhiều, nhiều-một và thứ tự collection.
- Thực hiện cascade và orphan removal đúng phạm vi.
- Áp dụng unique constraint, foreign key, not-null và precision.
- Xử lý transaction, flush, rollback và optimistic locking.
- Dịch truy vấn domain thành SQL đúng với database dialect.
- Tái tạo Aggregate ở trạng thái hợp lệ sau khi đọc.

Mock Repository không thực hiện bất kỳ thao tác database nào. Nếu test chỉ cấu hình mock trả về một Order đã dựng sẵn, test không thể phát hiện mapping thiếu OrderLine, enum lưu sai kiểu, SQL không chạy được hoặc migration thiếu cột.

### 1.1. Phân biệt các loại kiểm thử

| Loại test | Điều cần xác minh | Database |
|---|---|---|
| Unit Test cho Aggregate | Invariant và hành vi domain | Không cần |
| Application Test | Use case điều phối đúng các port | Thường dùng fake/mock |
| Repository Integration Test | Lưu, nạp, truy vấn và mapping đúng | Database thật phù hợp |
| Transaction Integration Test | Commit, rollback, isolation và concurrency | Database thật |
| Migration Test | Schema mới được tạo và nâng cấp đúng | Database thật |
| API Test | Hợp đồng HTTP và DTO | Có thể dùng database hoặc test slice tùy phạm vi |

Không nên dùng Integration Test để thay thế Unit Test. Unit Test vẫn nhanh và tập trung vào quy tắc domain. Integration Test bổ sung bằng chứng rằng persistence adapter giữ đúng mô hình khi làm việc với database.

### 1.2. Kiểm thử hợp đồng Repository

Một Repository contract có thể diễn đạt những điều mà mọi implementation phải tuân thủ:

- Lưu một Aggregate rồi tìm theo ID sẽ trả về Aggregate tương đương về mặt nghiệp vụ.
- ID và identity của Entity con được bảo toàn.
- Các Value Object được tái tạo đúng.
- Truy vấn theo tiêu chí trả về đúng tập kết quả.
- Không tìm thấy Aggregate được biểu diễn bằng Optional rỗng hoặc contract đã định nghĩa.
- Thay đổi trong Aggregate được lưu theo transaction.
- Quy tắc nhất quán và concurrency được bảo vệ.

Nếu ứng dụng có nhiều adapter, ví dụ JPA và document store, cùng một bộ contract test có thể chạy trên từng adapter. Các chi tiết đặc thù của từng database vẫn cần test riêng.

### 1.3. Kiểm thử Repository không phải kiểm thử SQL theo từng dòng

Mục tiêu chính là xác minh hành vi quan sát được qua contract. Thường không cần assert chính xác ORM đã phát bao nhiêu câu SQL hoặc câu lệnh có đúng một alias cụ thể. Những assertion như vậy dễ vỡ khi thay đổi phiên bản ORM mà không làm thay đổi hành vi.

Tuy nhiên, khi một truy vấn có yêu cầu hiệu năng hoặc có nguy cơ N+1, có thể bổ sung kiểm tra số query, query plan hoặc metric phù hợp. Hãy chọn mức kiểm tra dựa trên rủi ro thật.

## 2. Chọn cơ sở dữ liệu test phù hợp với production

Một Integration Test chỉ có giá trị đối với các đặc tính mà môi trường test thực sự mô phỏng. Database khác engine có thể có cách xử lý kiểu dữ liệu, khóa, transaction, collation và SQL khác nhau.

### 2.1. Vì sao H2 không thay thế hoàn toàn PostgreSQL hoặc MySQL?

H2 rất tiện cho test nhanh và một số bài kiểm thử đơn giản. Nhưng nó không phải PostgreSQL hay MySQL. Những khác biệt có thể xuất hiện ở:

- Kiểu UUID, JSON/JSONB, array, enum hoặc timestamp.
- Cú pháp DDL và hành vi migration.
- Unique constraint với giá trị NULL.
- Collation, so sánh chuỗi và chữ hoa/chữ thường.
- Locking, isolation level và deadlock.
- Generated column, sequence và identity.
- Hàm SQL, toán tử và truy vấn native.
- Quy tắc precision, rounding và timezone.

Một test chạy qua H2 có thể xanh trong khi migration hoặc truy vấn thất bại trên PostgreSQL production. H2 vẫn có thể hữu ích cho test rất nhanh nếu hệ thống dùng các tính năng SQL phổ thông, nhưng không nên là bằng chứng duy nhất cho persistence adapter.

### 2.2. Dùng cùng engine và phiên bản gần production

Nếu production chạy PostgreSQL 16, test nên dùng PostgreSQL cùng major version hoặc phiên bản được tổ chức hỗ trợ. Nếu production dùng MySQL, SQL Server hoặc Oracle, hãy dùng đúng engine tương ứng khi kiểm thử hành vi đặc thù.

Testcontainers giúp khởi chạy database tạm thời bằng container:

- Mỗi test suite hoặc test class có database cô lập.
- Test dùng schema và dialect thật.
- Có thể chạy migration như môi trường triển khai.
- Không cần một database dùng chung được cài sẵn trên máy lập trình viên.
- CI có thể tái tạo môi trường nếu runner hỗ trợ container.

Ví dụ trong bài dùng PostgreSQL. Hãy thay image và cấu hình theo database thật của dự án.

### 2.3. Khi nào database container là chưa đủ?

Container giúp mô phỏng engine, nhưng không tự mô phỏng mọi đặc điểm production như cấu hình replication, network latency, connection pool, quyền IAM hoặc dữ liệu có quy mô rất lớn.

Có thể chia kiểm thử thành nhiều lớp:

- Integration Test thường xuyên với database container.
- Performance Test trên dữ liệu và cấu hình gần production.
- Smoke Test trên môi trường staging sau khi triển khai.
- Kiểm tra vận hành cho backup, replication và failover nếu các đặc tính đó quan trọng.

Không cần dựng toàn bộ production topology cho mọi test Repository. Chọn mức môi trường phù hợp với câu hỏi cần trả lời.

## 3. Thiết kế test cho đúng ranh giới Repository

Repository nên được kiểm thử qua hợp đồng mà Application Layer sử dụng. Test cần gọi Repository thật, để ORM và database thực hiện việc lưu/nạp.

Giả sử Order Aggregate có:

- OrderId là identity của Root.
- CustomerId tham chiếu khách hàng.
- Một hoặc nhiều OrderLine.
- ShippingAddress là Value Object.
- Money là Value Object gồm số tiền và tiền tệ.
- OrderStatus là trạng thái nghiệp vụ.
- Mỗi OrderLine có identity riêng trong phạm vi Order.

Repository contract có thể như sau:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);

    void save(Order order);

    Optional<Order> findByOrderNumber(OrderNumber number);
}
~~~

Test không cần biết implementation dùng JpaRepository, EntityManager, JDBC hay MyBatis. Nó chỉ biết hợp đồng và xác minh dữ liệu sau khi thao tác.

### 3.1. Test lưu rồi nạp lại Aggregate

Đây là test nền tảng của Repository:

1. Tạo Aggregate hợp lệ bằng factory hoặc test fixture của domain.
2. Gọi Repository thật để lưu.
3. Flush thay đổi xuống database.
4. Xóa persistence context để không đọc lại cùng object đang được ORM quản lý.
5. Nạp Aggregate bằng ID.
6. So sánh identity, Value Object, Entity con và trạng thái nghiệp vụ.

Điểm quan trọng là bước flush và clear. Nếu test chỉ đọc lại object đang nằm trong persistence context, nó có thể nhận chính instance đã lưu mà không đi qua SQL SELECT. Khi đó test không chứng minh mapping đọc hoạt động.

~~~java
@Test
void savesAndRehydratesAnOrderAggregate() {
    Order order = TestOrders.draftWithTwoLines();

    orders.save(order);
    entityManager.flush();

    OrderId id = order.id();

    entityManager.clear();

    Order reloaded = orders.findById(id).orElseThrow();

    assertEquals(id, reloaded.id());
    assertEquals(order.orderNumber(), reloaded.orderNumber());
    assertEquals(order.status(), reloaded.status());
    assertEquals(order.shippingAddress(), reloaded.shippingAddress());
    assertEquals(order.total(), reloaded.total());
    assertEquals(2, reloaded.lines().size());
}
~~~

Test này chỉ có ý nghĩa khi Order được tạo từ fixture hợp lệ và Repository thực sự dùng database test. Nếu dùng JPA, EntityManager clear giúp buộc lần đọc sau đi qua database thay vì persistence context hiện tại.

### 3.2. So sánh theo ngữ nghĩa, không phụ thuộc implementation

Không nên assert rằng EntityManager phải trả cùng object reference hoặc collection phải có cùng class cụ thể. Sau khi nạp lại, Aggregate có thể là object instance mới và collection có thể là implementation khác.

Hãy so sánh các thuộc tính nghiệp vụ:

- Hai Order có cùng identity không?
- Hai Money có cùng amount và currency không?
- Địa chỉ có giữ đúng các thành phần không?
- Các OrderLine có đúng identity, ProductId, Quantity và unit price không?
- Trạng thái có giữ đúng không?
- Hành vi tiếp theo có hoạt động theo invariant không?

Có thể dùng domain equality hoặc assertion theo từng Value Object. Tránh so sánh chuỗi JSON của toàn bộ object vì nó kéo test sang chi tiết serialization.

### 3.3. Kiểm tra hành vi sau khi rehydrate

Một Aggregate đọc lại không chỉ cần có field đúng. Nó cần hoạt động như một Aggregate hợp lệ.

Ví dụ, sau khi nạp Order ở trạng thái Draft, gọi hành vi đặt đơn phải thực hiện đúng quy tắc:

~~~java
@Test
void rehydratedOrderCanExecuteDomainBehavior() {
    Order order = TestOrders.draftWithOneLine();

    orders.save(order);
    entityManager.flush();
    OrderId id = order.id();
    entityManager.clear();

    Order reloaded = orders.findById(id).orElseThrow();

    reloaded.place();

    assertEquals(OrderStatus.PLACED, reloaded.status());
}
~~~

Test này giúp phát hiện lỗi rehydration như thiếu collection, sai enum hoặc Value Object bị dựng thiếu dữ liệu khiến hành vi domain không còn đúng.

### 3.4. Kiểm tra không tìm thấy và truy vấn theo business key

Ngoài ID, Repository thường có truy vấn theo mã đơn hoặc tiêu chí nghiệp vụ. Hãy kiểm tra:

- ID không tồn tại trả về Optional rỗng.
- Business key tìm đúng Aggregate.
- Business key có unique constraint nếu domain yêu cầu duy nhất.
- Kết quả không phụ thuộc thứ tự mặc định không được quy định.
- Truy vấn có phân trang và sắp xếp ổn định.

Nếu một query có thể trả nhiều kết quả, hãy kiểm tra tập dữ liệu và thứ tự theo contract, không chỉ kiểm tra số lượng bản ghi.

## 4. Kiểm thử ánh xạ Aggregate và Entity con

Mapping là nơi cấu trúc object được chuyển thành cấu trúc lưu trữ. Một mapping sai có thể khiến dữ liệu bị mất, nhân đôi hoặc tái tạo sai quan hệ.

### 4.1. Identity của Aggregate Root

Aggregate Root thường có ID ổn định. Test cần xác minh:

- ID do domain tạo có được lưu đúng không.
- ID do database sinh có được trả lại cho Aggregate theo contract không.
- Lần lưu tiếp theo cập nhật đúng bản ghi hiện tại.
- Repository không vô tình tạo bản ghi mới khi cập nhật Aggregate đã tồn tại.

Nếu dùng UUID do ứng dụng tạo, test cần xác minh giá trị không bị đổi sau khi round-trip. Nếu dùng sequence database, test cần xác minh ID được gán sau khi persist và được dùng đúng trong các quan hệ.

### 4.2. Identity của Entity con

OrderLine có thể có identity riêng trong Aggregate. Sau khi lưu và nạp lại, identity đó cần được bảo toàn. Nếu mapping chỉ dùng vị trí trong List làm identity, việc sắp xếp hoặc xóa phần tử có thể tạo lỗi khó phát hiện.

Test nên:

- Lưu Aggregate có nhiều dòng hàng.
- Ghi lại ID từng dòng.
- Nạp lại Aggregate.
- Xác minh mỗi dòng có đúng ID và dữ liệu.
- Xóa một dòng qua hành vi của Root rồi lưu lại.
- Nạp lại và xác minh chỉ dòng được yêu cầu bị xóa.

### 4.3. Quan hệ hai chiều và owning side

JPA có thể ánh xạ quan hệ hai chiều giữa Order và OrderLine. Một phía là owning side quyết định foreign key được ghi. Nếu domain chỉ cập nhật collection phía Order mà không đồng bộ owning side, database có thể không lưu quan hệ như mong muốn.

Test cần tạo Aggregate qua hành vi domain, lưu rồi nạp lại và kiểm tra quan hệ từ Root. Nếu implementation có helper nội bộ để đồng bộ hai phía, test Repository sẽ phát hiện khi helper bị bỏ sót.

Không nên để test tự gọi setter của JPA Entity nhằm sửa quan hệ trước khi lưu, vì như vậy test bỏ qua đường đi thật của domain và mapper.

### 4.4. Cascade và orphan removal

Cascade quyết định thao tác trên Root có lan tới Entity con hay không. Orphan removal có thể xóa bản ghi con khi nó bị loại khỏi quan hệ.

Test cần xác minh đúng semantics mong muốn:

- Lưu Order mới có lưu các OrderLine không?
- Xóa một dòng qua hành vi Root có xóa đúng bản ghi con không?
- Xóa Order có được phép xóa các dòng con không?
- Entity con có bị chia sẻ giữa hai Aggregate không?
- Thay collection có vô tình xóa và tạo lại mọi dòng hàng không?

Không nên bật cascade remove chỉ vì nó tiện. Ranh giới Aggregate và quyền sở hữu vòng đời của Entity con phải quyết định hành vi xóa.

### 4.5. Thứ tự collection

Nếu thứ tự dòng hàng có ý nghĩa nghiệp vụ hoặc hiển thị, database cần lưu thông tin thứ tự hoặc query cần ORDER BY rõ ràng. Quan hệ một-nhiều không tự bảo đảm thứ tự.

Test nên tạo dữ liệu theo thứ tự khác nhau, nạp lại và xác minh thứ tự theo contract. Không dựa vào thứ tự ngẫu nhiên mà database tình cờ trả về.

## 5. Kiểm thử ánh xạ Value Object

Value Object thường không có identity riêng và được so sánh theo giá trị. Mapping của nó cần bảo toàn toàn bộ ý nghĩa.

### 5.1. Money và precision

Money thường gồm amount và currency. Nếu chỉ lưu amount mà bỏ currency, cùng một con số có thể bị diễn giải sai.

Test cần kiểm tra:

- Amount round-trip không mất precision ngoài quy tắc đã chọn.
- Currency được lưu và nạp đúng.
- Scale của DECIMAL phù hợp với nghiệp vụ.
- Rounding được thực hiện ở đúng lớp.
- So sánh Money không vô tình bỏ qua currency.

Ví dụ, 125.50 USD và 125.50 VND không phải cùng một giá trị nghiệp vụ. Test mapping nên xác minh cả hai thành phần.

### 5.2. Address và các Value Object phức hợp

ShippingAddress có thể được ánh xạ bằng JPA Embeddable, JSON column hoặc các cột riêng. Dù chọn cách nào, Repository cần tái tạo cùng ngữ nghĩa:

~~~java
@Embeddable
public class ShippingAddressEmbeddable {
    private String recipientName;
    private String street;
    private String district;
    private String city;
    private String postalCode;
}
~~~

Nếu domain Value Object là immutable record nhưng persistence model cần class mutable cho ORM, mapper có thể chuyển đổi giữa hai loại. Test cần xác minh constructor domain nhận đủ dữ liệu và kiểm tra invariant khi rehydrate.

### 5.3. Attribute Converter

Các kiểu như EmailAddress, OrderStatus hoặc Currency có thể dùng AttributeConverter để ánh xạ sang kiểu database. Test cần xác minh cả hai chiều:

- Domain value chuyển thành giá trị lưu trữ đúng.
- Giá trị lưu trữ được chuyển ngược thành domain value đúng.
- Giá trị không hợp lệ trong database được xử lý rõ.
- Thay đổi enum không làm đọc dữ liệu cũ sai.

Đừng chỉ test converter bằng cách gọi hàm Java nếu điều quan trọng là ORM có thực sự áp dụng converter trong SQL hay không. Hãy có ít nhất một Integration Test lưu và nạp Aggregate dùng converter.

### 5.4. Enum và schema evolution

Lưu enum theo ordinal có rủi ro: đổi thứ tự các phần tử enum có thể làm dữ liệu cũ mang ý nghĩa khác. Lưu theo string thường dễ đọc và an toàn hơn khi thêm giá trị, nhưng vẫn cần chính sách khi đổi tên hoặc loại bỏ enum.

Test migration và round-trip nên xác minh giá trị được lưu theo contract. Khi enum được đổi tên, cần migration hoặc converter tương thích với dữ liệu cũ.

### 5.5. Thời gian và timezone

Instant, LocalDate, LocalDateTime và OffsetDateTime có semantics khác nhau. Test cần dùng giá trị có timezone/offset rõ và xác minh round-trip phù hợp với kiểu database.

Nếu nghiệp vụ lưu một thời điểm tuyệt đối, Instant thường thích hợp. Nếu lưu ngày địa phương như ngày nghỉ hoặc ngày giao dự kiến, LocalDate có thể đúng hơn. Không nên chuyển mọi thời gian thành String rồi hy vọng parser giữ nguyên ý nghĩa.

## 6. Kiểm tra schema và constraint trên database thật

ORM có thể giúp tạo schema trong test, nhưng migration là một phần của ứng dụng. Integration Test nên xác minh schema được tạo từ cùng migration mà môi trường triển khai sử dụng.

### 6.1. Chạy migration thật

Nếu dự án dùng Flyway hoặc Liquibase, hãy để test khởi động database rỗng và chạy migration. Không chỉ dùng Hibernate auto-create schema nếu production dùng migration, vì hai cơ chế có thể tạo schema khác nhau.

Một test khởi động sạch giúp phát hiện:

- Migration thiếu cột hoặc sai kiểu.
- Thứ tự migration không hợp lệ.
- Constraint chưa được tạo.
- Index bị thiếu.
- Default value khác với kỳ vọng.
- Schema không tương thích với mapping ORM.

### 6.2. Unique constraint

Nếu OrderNumber phải duy nhất, test nên thử lưu hai Aggregate có cùng OrderNumber và xác minh database từ chối bản ghi thứ hai.

Không chỉ kiểm tra một validator Java. Constraint database bảo vệ invariant trước các request đồng thời hoặc các đường ghi khác nhau.

### 6.3. Foreign key và not-null

Test nên xác minh database từ chối dữ liệu vi phạm quan hệ hoặc field bắt buộc khi các ràng buộc đó thuộc schema. Repository bình thường không nên tạo được một OrderLine tham chiếu tới Order không tồn tại.

Không nên cố tình dùng SQL tùy tiện để phá mọi constraint trong từng test. Chỉ kiểm tra những constraint là một phần của contract lưu trữ và giúp bảo vệ dữ liệu.

### 6.4. Precision, length và default

Các kiểu DECIMAL, VARCHAR, timestamp và default value có thể khác giữa database engine. Test với engine thật giúp phát hiện:

- Giá bị làm tròn hoặc tràn precision.
- Chuỗi vượt độ dài.
- Giá trị NULL ở cột NOT NULL.
- Default không được áp dụng như dự kiến.
- Timestamp bị mất độ chính xác.

Nếu domain có quy tắc giới hạn độ dài hoặc precision, hãy xác thực ở domain và giữ constraint tương ứng ở database để bảo vệ dữ liệu.

## 7. Kiểm thử transaction, flush và rollback

Một Repository có thể hoạt động đúng khi gọi đơn lẻ nhưng sai khi kết hợp với transaction. Test cần xác minh ranh giới commit thực tế.

### 7.1. Phân biệt save, flush và commit

Với ORM:

- save có thể đăng ký hoặc đồng bộ trạng thái object vào persistence context.
- flush yêu cầu ORM gửi thay đổi xuống database.
- commit kết thúc transaction và xác nhận thay đổi theo transaction semantics.

Constraint hoặc lỗi SQL có thể chỉ xuất hiện ở flush hoặc commit. Vì vậy, test chỉ gọi save rồi kết thúc có thể chưa kiểm tra được thao tác ghi.

### 7.2. Flush để phát hiện lỗi persistence sớm

Trong Repository Integration Test, gọi flush sau khi lưu giúp buộc ORM thực thi SQL. Điều này hữu ích cho unique constraint, foreign key và mapping.

~~~java
@Test
void rejectsDuplicateOrderNumber() {
    orders.save(TestOrders.withNumber("ORD-100"));
    entityManager.flush();

    orders.save(TestOrders.withNumber("ORD-100"));

    assertThrows(
        DataIntegrityViolationException.class,
        () -> entityManager.flush()
    );
}
~~~

Exception cụ thể phụ thuộc Spring, ORM và database. Test nên bắt loại exception ở abstraction mà dự án cam kết, tránh phụ thuộc sâu vào một exception vendor nếu không cần.

### 7.3. Rollback khi use case thất bại

Một test transaction nên xác minh nếu use case thay đổi Aggregate rồi thất bại trước commit, database không giữ lại một phần thay đổi.

Cần lưu ý rằng nhiều test slice như @DataJpaTest tự bọc mỗi test trong transaction và rollback khi kết thúc. Điều này tiện cho cô lập dữ liệu, nhưng có thể che giấu một số lỗi ở ranh giới commit.

Để kiểm tra commit/rollback thực tế, có thể dùng test với transaction do service quản lý, TransactionTemplate hoặc test không có transaction bao ngoài. Mỗi tình huống cần tạo transaction mới và đọc lại từ transaction khác sau khi kết thúc.

### 7.4. Không dùng cùng persistence context để xác minh rollback

Nếu object vẫn còn trong persistence context, nó có thể giữ trạng thái đã thay đổi trong bộ nhớ dù database đã rollback. Sau rollback, clear hoặc mở EntityManager mới rồi nạp lại từ database để kiểm tra trạng thái bền vững.

### 7.5. Kiểm tra transaction boundary của Application Service

Repository test tập trung vào adapter. Một Integration Test ở Application boundary có thể gọi use case thật với transaction manager thật, sau đó xác minh:

- Aggregate và các Entity con được commit cùng nhau.
- Lỗi trong quá trình lưu làm rollback toàn bộ thay đổi thuộc transaction.
- Domain Event hoặc Outbox được ghi cùng transaction nếu kiến trúc sử dụng.
- Kết quả chỉ được công bố thành công sau commit.

Không nên đưa mọi tác dụng phụ bên ngoài vào transaction database. Gửi email hoặc gọi payment gateway không tự rollback khi database rollback.

## 8. Kiểm thử optimistic locking và cập nhật đồng thời

Aggregate thường được nhiều request hoặc worker đọc và cập nhật cùng lúc. Optimistic locking giúp phát hiện một transaction đang ghi dựa trên phiên bản cũ.

### 8.1. Test hai transaction cùng đọc một version

Một test concurrency cần hai persistence context hoặc hai transaction độc lập:

1. Transaction A nạp Order version 4.
2. Transaction B cũng nạp Order version 4.
3. A thay đổi và commit, tạo version 5.
4. B thay đổi trên object version 4 và cố commit.
5. B phải nhận conflict thay vì âm thầm ghi đè A.

Nếu test dùng chung một EntityManager, nó không mô phỏng được hai transaction độc lập.

### 8.2. Mapping version

Với JPA, trường version có thể được ánh xạ bằng @Version:

~~~java
@Entity
public class OrderJpaEntity {
    @Id
    private UUID id;

    @Version
    private long version;

    private String status;
}
~~~

Test cần xác minh version tăng sau cập nhật và lần ghi dựa trên version cũ bị từ chối. Domain không nhất thiết phụ thuộc annotation JPA; đây là chi tiết của persistence adapter.

### 8.3. Không retry mù quáng trong Repository

Khi optimistic lock conflict xảy ra, cần rollback transaction hiện tại, mở transaction mới, nạp Aggregate mới nhất và đánh giá lại hành vi nghiệp vụ. Repository không nên tự động merge trạng thái cũ hoặc ghi đè version.

Test nên xác minh adapter báo conflict theo contract. Logic retry, nếu có, thuộc Application Layer hoặc cơ chế điều phối phù hợp.

### 8.4. Tránh test concurrency không xác định

Dùng Thread.sleep để hy vọng hai transaction đụng nhau thường tạo test chập chờn. Hãy dùng CountDownLatch, CyclicBarrier hoặc cơ chế điều phối rõ để kiểm soát thời điểm cả hai transaction đã đọc dữ liệu.

Không cần chạy hàng trăm thread trong mỗi test. Một kịch bản có kiểm soát đủ để chứng minh optimistic locking hoạt động.

## 9. Kiểm thử truy vấn Repository

Repository không chỉ lưu và nạp theo ID. Các truy vấn domain cần được kiểm tra với dữ liệu đủ đa dạng để phát hiện điều kiện lọc và sắp xếp sai.

### 9.1. Chuẩn bị dữ liệu phân biệt rõ

Ví dụ, tạo các Order có:

- Hai Customer khác nhau.
- Nhiều trạng thái.
- Thời điểm tạo khác nhau.
- Tổng tiền khác nhau.
- Một số đơn không có dữ liệu tùy chọn.
- Các OrderNumber gần giống nhau.

Sau đó kiểm tra từng tiêu chí lọc. Nếu tất cả fixture có cùng trạng thái hoặc cùng customer, test có thể pass dù điều kiện WHERE bị bỏ sót.

### 9.2. Kiểm tra kết quả và thứ tự

Nếu contract yêu cầu đơn mới nhất trước, query cần ORDER BY rõ ràng. Test nên tạo các bản ghi có timestamp khác nhau và xác minh thứ tự.

Nếu nhiều bản ghi có cùng createdAt, hãy dùng tie-breaker ổn định như ID. Nếu không, phân trang có thể lặp hoặc bỏ sót kết quả giữa các lần gọi.

### 9.3. Kiểm tra pagination

Test cần xác minh:

- Page đầu có đúng phần tử.
- Page tiếp theo không lặp phần tử.
- Total count chính xác.
- Sort ổn định.
- Kết quả rỗng có metadata phù hợp.
- Filter được áp dụng trước khi phân trang.

Không chỉ kiểm tra page size. Một query có thể trả đúng số phần tử nhưng sai tập dữ liệu.

### 9.4. Kiểm tra query cần join hoặc projection

Nếu Repository dùng join fetch, entity graph hoặc projection, test cần xác minh kết quả đúng và không nhân đôi Root do join một-nhiều.

Một Order có ba OrderLine có thể tạo ba hàng SQL. Nếu query trả về ba Order thay vì một Aggregate duy nhất, cần xử lý distinct hoặc query strategy phù hợp.

### 9.5. Kiểm tra N+1 ở nơi có rủi ro

Nếu một truy vấn danh sách trả về nhiều Order và mapper truy cập quan hệ lazy, số query có thể tăng theo số bản ghi. Có thể bật Hibernate statistics hoặc datasource query counter để đo trong Integration Test.

Đừng assert một con số SQL quá cụ thể nếu nó không phải yêu cầu. Hãy kiểm tra giới hạn có ý nghĩa, ví dụ truy vấn 20 Order không tạo 21 lần tải Customer riêng lẻ.

## 10. Dựng Integration Test với Spring Boot, JPA và Testcontainers

Ví dụ sau dùng PostgreSQL container, Spring Data JPA và JUnit 5. Tên class, package và dependency cần điều chỉnh theo dự án.

### 10.1. Dependency test

Với Maven, dự án thường cần các dependency test tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
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

Quản lý version Testcontainers bằng BOM hoặc dependency management thống nhất của dự án. CI cần môi trường có thể chạy container.

### 10.2. Khởi động database container

~~~java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class JpaOrderRepositoryIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("orders")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void configureDatabase(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl
        );
        registry.add(
            "spring.datasource.username",
            postgres::getUsername
        );
        registry.add(
            "spring.datasource.password",
            postgres::getPassword
        );
    }

    @Autowired
    OrderRepository orders;

    @Autowired
    EntityManager entityManager;
}
~~~

Annotation AutoConfigureTestDatabase với Replace.NONE yêu cầu Spring dùng datasource container thay vì tự thay bằng embedded database. DynamicPropertySource truyền thông tin kết nối của container vào Spring context.

### 10.3. Chạy migration thay vì chỉ tạo schema từ Entity

Nếu production dùng Flyway, test nên để Flyway chạy migration trên database container. Cấu hình Hibernate schema generation cần phù hợp với chiến lược dự án; thường có thể đặt ddl-auto là validate để ORM kiểm tra mapping so với schema đã được migration tạo ra.

Ví dụ cấu hình test:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
~~~

Không dùng đồng thời nhiều cơ chế tạo schema không kiểm soát. Nếu Hibernate tự tạo bảng trong test nhưng production dùng Flyway, test có thể không phát hiện migration bị lỗi.

### 10.4. Test lưu và nạp lại

~~~java
@Test
void persistsOrderAndRehydratesItsValueObjects() {
    Order order = TestOrders.draftWithTwoLines();

    orders.save(order);
    entityManager.flush();

    OrderId id = order.id();
    entityManager.clear();

    Order loaded = orders.findById(id).orElseThrow();

    assertEquals(order.id(), loaded.id());
    assertEquals(order.orderNumber(), loaded.orderNumber());
    assertEquals(order.status(), loaded.status());
    assertEquals(order.shippingAddress(), loaded.shippingAddress());
    assertEquals(order.total(), loaded.total());
    assertEquals(order.lines().size(), loaded.lines().size());
}
~~~

Trong test thực tế, có thể so sánh từng OrderLine theo ID và xác minh Quantity, ProductId, unit price. Test nên bao gồm các giá trị biên quan trọng như số tiền có scale, địa chỉ có thành phần tùy chọn và trạng thái enum.

### 10.5. Cô lập dữ liệu giữa các test

@DataJpaTest thường mở transaction cho từng test và rollback sau khi test kết thúc. Điều này giúp dữ liệu không rò sang test tiếp theo. Tuy nhiên, nếu test dùng nhiều transaction hoặc thread, rollback của transaction test không tự động dọn dữ liệu được commit từ transaction khác.

Các lựa chọn gồm:

- Database/container riêng cho suite hoặc class.
- Schema riêng cho từng test worker.
- Xóa dữ liệu bằng SQL có thứ tự phù hợp.
- Dùng transaction rollback khi toàn bộ thao tác nằm trong cùng transaction test.

Chọn một chiến lược rõ ràng, đặc biệt khi test chạy song song.

## 11. Tổ chức fixture và test data

Fixture tốt giúp test tập trung vào hành vi cần xác minh thay vì lặp lại hàng chục dòng dựng object.

### 11.1. Tạo Aggregate hợp lệ qua factory hoặc builder

Ưu tiên factory domain hoặc Test Data Builder tạo trạng thái hợp lệ:

~~~java
Order order = TestOrders.draft()
    .withCustomer(customerId)
    .withLine(productId, Quantity.of(2), Money.usd("19.95"))
    .withShippingAddress(address)
    .build();
~~~

Builder là công cụ của test, không nên làm lộ setter công khai trên Aggregate. Nó có thể gọi factory và hành vi domain để tạo trạng thái.

### 11.2. Không phụ thuộc ID hoặc timestamp ngẫu nhiên khi assertion cần ổn định

Có thể dùng UUID cố định trong test khi cần so sánh chính xác. Dùng Clock giả hoặc timestamp cố định cho dữ liệu thời gian. Nếu dùng ID tự sinh, hãy lấy ID từ Aggregate sau khi tạo và dùng lại trong assertion.

Không dùng thời điểm hiện tại trực tiếp trong mọi fixture nếu test lọc theo khoảng thời gian. Ranh giới ngày và timezone có thể làm test khác nhau giữa máy.

### 11.3. Dùng dữ liệu có ý nghĩa phân biệt

Một fixture có một Order duy nhất không thể kiểm tra truy vấn lọc theo Customer hoặc phân trang. Tạo dữ liệu có khác biệt có chủ ý, chẳng hạn hai khách hàng, ba trạng thái và nhiều ngày tạo.

Tránh dùng quá nhiều dữ liệu không liên quan khiến test khó đọc. Mỗi fixture nên giúp làm rõ điều kiện mà test đang kiểm tra.

### 11.4. Không dùng SQL fixture để né đường đi của Repository

SQL trực tiếp có thể cần cho một số tình huống như tạo dữ liệu legacy hoặc kiểm tra constraint. Nhưng test round-trip chính nên lưu qua Repository thật. Nếu mọi dữ liệu đều được insert bằng SQL, test không xác minh mapping ghi của Repository.

Có thể kết hợp: tạo Aggregate qua domain và Repository, sau đó dùng SQL để xác minh constraint hoặc kiểm tra dữ liệu thô khi cần.

## 12. Kiểm thử mapping khi Domain Model và Persistence Model tách biệt

Một số kiến trúc không dùng trực tiếp JPA Entity làm domain Entity. Persistence Adapter có class riêng và mapper chuyển đổi giữa hai mô hình.

Ví dụ:

~~~java
public class OrderJpaEntity {
    private UUID id;
    private String status;
    private List<OrderLineJpaEntity> lines;
}

public final class OrderMapper {
    public Order toDomain(OrderJpaEntity entity) {
        // Tái tạo Aggregate từ dữ liệu persistence.
    }

    public OrderJpaEntity toPersistence(Order order) {
        // Chuyển Aggregate thành persistence model.
    }
}
~~~

Trong trường hợp này, cần kiểm tra cả mapper và Repository:

- Mapper chuyển Domain sang Persistence Model đúng.
- Mapper tái tạo Domain từ Persistence Model đúng.
- Repository gọi mapper đúng thời điểm.
- Quan hệ Entity con được nạp đủ trước khi tạo Aggregate.
- Mapper không bỏ qua invariant hoặc tạo trạng thái domain không hợp lệ.

Unit Test riêng cho mapper có thể kiểm tra các trường hợp thuần Java. Nhưng vẫn cần Repository Integration Test để xác minh dữ liệu thực trong database được ánh xạ qua mapper như dự kiến.

### 12.1. Reconstitution khác với tạo Aggregate mới

Factory tạo Aggregate mới thường áp dụng quy tắc khởi tạo và có thể tạo ID hoặc Domain Event. Reconstitution tạo lại Aggregate đã tồn tại từ dữ liệu lưu trữ; nó cần bảo toàn identity, trạng thái và lịch sử phù hợp mà không phát sinh sự kiện nghiệp vụ giả như vừa tạo mới.

Thiết kế cụ thể tùy mô hình. Test cần phát hiện việc nạp lại Order vô tình tạo ID mới, đặt lại status về Draft hoặc phát OrderCreated lần nữa.

### 12.2. Không bỏ qua invariant khi rehydrate

Dữ liệu database có thể cũ hoặc được ghi từ phiên bản ứng dụng trước. Reconstitution cần có chiến lược đối với dữ liệu không còn hợp lệ:

- Migration sửa dữ liệu trước khi code mới đọc.
- Mapper chuyển đổi representation cũ sang Value Object mới.
- Dữ liệu không thể chuyển đổi được báo lỗi rõ và đưa vào quy trình sửa chữa.
- Invariant mới cần có giai đoạn tương thích nếu dữ liệu lịch sử chưa đáp ứng.

Không nên âm thầm tạo Aggregate sai hoặc thay giá trị lỗi bằng mặc định tùy tiện.

## 13. Kiểm thử migration và tương thích schema

Migration thay đổi cấu trúc database theo thời gian. Repository có thể chạy tốt với schema do Hibernate tạo nhưng thất bại trên schema production sau nhiều lần nâng cấp.

### 13.1. Kiểm tra database mới từ đầu

Tạo database rỗng, chạy toàn bộ migration và khởi động ứng dụng. Điều này xác minh chuỗi migration có thể tạo schema mới hợp lệ.

### 13.2. Kiểm tra nâng cấp từ schema cũ

Nếu ứng dụng đã có dữ liệu production, cần test đường nâng cấp từ phiên bản schema trước. Một migration có thể chạy được trên database rỗng nhưng thất bại khi cột đã có dữ liệu hoặc constraint mới không tương thích với bản ghi cũ.

Có thể dùng fixture schema ở phiên bản trước, nạp dữ liệu đại diện, chạy migration mới rồi xác minh:

- Dữ liệu cũ được giữ hoặc chuyển đổi đúng.
- Default value có ý nghĩa.
- Constraint mới không làm mất dữ liệu hợp lệ.
- Repository phiên bản mới đọc được dữ liệu sau migration.
- Các giá trị enum hoặc Value Object cũ được chuyển đổi đúng.

### 13.3. Kiểm tra chiến lược expand-and-contract

Với hệ thống triển khai không thể dừng lâu, thay đổi schema có thể cần nhiều bước:

1. Thêm cột hoặc bảng mới theo cách tương thích.
2. Deploy code có thể đọc/ghi cả representation cũ và mới nếu cần.
3. Backfill dữ liệu.
4. Chuyển truy vấn sang representation mới.
5. Sau khi các phiên bản cũ không còn chạy, loại bỏ cột cũ.

Test migration nên phản ánh thứ tự này nếu hệ thống triển khai rolling hoặc có nhiều phiên bản ứng dụng chạy đồng thời.

## 14. Các lỗi phổ biến khi kiểm thử Repository

**Chỉ mock Repository.** Test Application không xác minh SQL, mapping hoặc constraint. Bổ sung Integration Test cho adapter thật.

**Dùng H2 làm bằng chứng duy nhất cho PostgreSQL.** Khác biệt engine có thể che giấu lỗi. Dùng đúng database engine trong test quan trọng.

**Không flush trước assertion.** ORM có thể chưa gửi SQL xuống database. Gọi flush khi cần xác minh câu lệnh ghi hoặc constraint.

**Không clear persistence context.** Test có thể đọc lại cùng object trong bộ nhớ. Clear hoặc dùng EntityManager mới để kiểm tra rehydration.

**Chỉ kiểm tra Root, bỏ qua Entity con.** Aggregate có thể được nạp thiếu collection hoặc mất identity của child. Kiểm tra quan hệ và hành vi trên toàn Aggregate.

**Dựng Entity bằng setter trong test.** Test bỏ qua factory và hành vi domain. Tạo Aggregate hợp lệ qua domain API.

**Dựa vào thứ tự database ngẫu nhiên.** Query không có ORDER BY không bảo đảm thứ tự. Định nghĩa và kiểm tra sort rõ ràng.

**Dùng transaction test để kết luận commit/rollback.** Transaction bao ngoài có thể che giấu lỗi ở commit. Bổ sung test với transaction boundary thực tế.

**Không kiểm tra migration.** Schema tự tạo từ Entity không chứng minh migration production chạy được. Chạy migration thật trên database rỗng và dữ liệu cũ đại diện.

**Kiểm thử concurrency bằng một EntityManager.** Không mô phỏng được hai transaction độc lập. Dùng persistence context riêng và điều phối đồng thời rõ ràng.

**Assert quá sâu vào SQL nội bộ.** Test dễ vỡ khi ORM thay đổi cách sinh câu lệnh. Ưu tiên contract và kết quả; chỉ kiểm tra SQL khi có yêu cầu kỹ thuật cụ thể.

**Dùng dữ liệu test phụ thuộc thời gian hoặc môi trường.** Test có thể chập chờn theo timezone và thứ tự chạy. Cố định Clock, ID và dữ liệu cần thiết.

## 15. Quy trình xây dựng Repository Integration Test

Có thể áp dụng quy trình sau cho mỗi Aggregate quan trọng:

1. **Đọc Repository contract.** Liệt kê các thao tác nạp, lưu và truy vấn cần được bảo đảm.
2. **Xác định persistence mapping.** Ghi lại Root, Entity con, Value Object, converter, quan hệ và constraint.
3. **Chọn database phù hợp.** Dùng cùng engine và major version gần production.
4. **Khởi tạo database cô lập.** Dùng Testcontainers hoặc môi trường test tương đương.
5. **Chạy migration thật.** Không thay thế migration production bằng schema tự tạo khác biệt.
6. **Tạo Aggregate qua domain factory.** Dùng fixture hợp lệ và dữ liệu có chủ đích.
7. **Lưu, flush và clear.** Buộc ORM ghi và sau đó đọc lại từ database.
8. **Xác minh rehydration.** Kiểm tra identity, Value Object, Entity con và hành vi domain.
9. **Kiểm tra query contract.** Filter, sort, pagination, empty result và business key.
10. **Kiểm tra constraint và transaction.** Unique, foreign key, rollback, flush và commit.
11. **Kiểm tra concurrency khi cần.** Optimistic locking và cập nhật đồng thời.
12. **Kiểm tra migration và phục hồi.** Schema mới, nâng cấp dữ liệu cũ và khả năng chạy lại test.
13. **Đưa test vào CI.** Đảm bảo runner có thể chạy container và test được thực thi thường xuyên.

Không phải mọi Repository đều cần mọi loại test. Hãy ưu tiên theo mức độ quan trọng của Aggregate, độ phức tạp mapping và rủi ro dữ liệu.

## 16. Checklist đánh giá Repository và mapping

**Database và môi trường**

- Test dùng đúng engine với production chưa?
- Phiên bản database có phù hợp không?
- Database test có được cô lập giữa các suite hoặc worker không?
- Migration thật có chạy không?
- Test có tránh phụ thuộc database cài sẵn trên máy cá nhân không?

**Repository contract**

- Lưu rồi nạp lại Aggregate có giữ identity không?
- Không tìm thấy được biểu diễn đúng không?
- Truy vấn theo business key có đúng không?
- Filter, sort và pagination có được kiểm tra không?
- Test có gọi Repository thật thay vì mock không?

**Mapping**

- Entity con và identity của chúng có được bảo toàn không?
- Value Object có round-trip đúng không?
- Money, currency, enum và timestamp có giữ semantics không?
- Quan hệ hai chiều, cascade và orphan removal có đúng không?
- Aggregate rehydrate có thực hiện được hành vi domain không?
- Mapper có xử lý dữ liệu legacy hoặc không hợp lệ rõ ràng không?

**Transaction và dữ liệu**

- Flush có phát hiện lỗi persistence không?
- Commit và rollback có được kiểm tra ở đúng ranh giới không?
- Clear persistence context trước khi xác minh rehydration chưa?
- Unique, foreign key, not-null và precision có được kiểm tra không?
- Optimistic locking có hoạt động với hai transaction độc lập không?

**Độ ổn định của test**

- Fixture có tạo Aggregate hợp lệ qua domain API không?
- ID và thời gian có ổn định không?
- Test có độc lập với thứ tự chạy không?
- Có tránh assertion quá chặt vào SQL nội bộ không?
- CI có chạy được database container không?

## 17. Kết luận

Repository là ranh giới quan trọng giữa Aggregate và database. Unit Test có thể chứng minh hành vi domain, nhưng chỉ Integration Test trên database phù hợp mới xác minh được SQL, mapping, constraint, transaction và cách tái tạo Aggregate trong điều kiện thực tế.

Một bài kiểm thử nền tảng nên lưu Aggregate bằng Repository thật, flush thay đổi, clear persistence context, nạp lại và xác minh identity, Value Object, Entity con cùng hành vi nghiệp vụ. Các test bổ sung cần kiểm tra query, pagination, constraint, migration, rollback và optimistic locking theo rủi ro của hệ thống.

Hãy dùng cùng database engine với production khi kiểm tra các đặc tính phụ thuộc engine, chạy migration thật và tạo dữ liệu test qua domain API. Khi test được thiết kế quanh contract Repository và ngữ nghĩa Aggregate, chúng giúp phát hiện lỗi persistence mà mock không thể thấy, đồng thời giữ được sự tự do thay đổi implementation khi kiến trúc phát triển.

