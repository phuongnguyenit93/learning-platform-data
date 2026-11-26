# Chọn một store thực thi để xác minh các abstraction dùng chung

Các interface như `Repository`, `CrudRepository`, `Pageable`, `Example` hay projection mô tả cách ứng dụng làm việc với dữ liệu. Chúng không tự tạo ra một database, driver hoặc bộ máy thực thi truy vấn. Muốn xác minh hành vi của các abstraction, cần chọn một store module và một hệ lưu trữ cụ thể để chạy các quan sát có thể lặp lại.

Trong chương **Thực hành tổng hợp** của module **SPRING_DATA_COMMONS**, bài học này chọn một cấu hình thực thi cho bài thực hành, thiết kế dữ liệu và xác định bằng chứng cần thu thập. Mục tiêu là nối các kiến thức về Repository, CRUD, derived query, phân trang, sắp xếp, projection, QBE, metadata, auditing và mở rộng repository với một implementation thật, đồng thời giữ rõ giới hạn của từng store.

## 1. Kết quả cần đạt sau bước chọn store

Kết thúc bước này, người thực hành cần giải thích và kiểm chứng được:

1. Module nào tạo repository proxy và thực hiện các thao tác dữ liệu.
2. Hệ lưu trữ, driver và transaction manager nào đang được dùng.
3. Domain type, kiểu ID và mapping nào thuộc cấu hình đã chọn.
4. Những abstraction nào được đưa vào bài thực hành và được store hỗ trợ.
5. Cách quan sát dữ liệu thật thay vì chỉ mock kết quả repository.
6. Những kết luận nào mới đúng với store đã chọn, chưa phải bảo đảm phổ quát.

Một lựa chọn như “dùng Spring Data” chưa đủ cụ thể. Một lựa chọn đầy đủ hơn là:

```text
Store module: Spring Data JPA
Hệ lưu trữ: PostgreSQL
Mô hình thực thi: imperative, truy cập qua JDBC/JPA provider
Domain thực hành: danh mục sản phẩm
ID: Long do database sinh theo mapping
Transaction: manager JPA của cùng datasource
Môi trường xác minh: database hoặc schema kiểm thử riêng
```

Đây là cấu hình được chọn cho các ví dụ trong bài, không phải yêu cầu mọi dự án dùng Spring Data Commons đều phải dùng JPA.

## 2. Vì sao chọn một store trước thay vì nhiều store cùng lúc?

Với một store, lỗi ban đầu dễ phân loại hơn: repository thuộc factory nào, entity thuộc mapping nào và transaction quản lý tài nguyên nào.

Nếu đồng thời thêm nhiều module, một repository dùng interface chung có thể cần thêm thông tin để xác định nó thuộc công nghệ nào. Spring Data mô tả cơ chế phân biệt repository khi có nhiều factory trong [định nghĩa repository interface](https://docs.spring.io/spring-data/commons/reference/repositories/definition.html).

Trong bài thực hành cơ sở, chọn một store giúp tập trung vào hợp đồng trước. Việc thêm store thứ hai là một phép thử mở rộng có chủ đích về mức độ dùng chung, không phải điều kiện để hoàn thành bước xác minh đầu tiên.

### 2.1. Cân nhắc theo mục tiêu học

| Lựa chọn | Thích hợp để quan sát | Phần phải học thêm tại store |
| --- | --- | --- |
| JPA với database quan hệ | Repository imperative, mapping entity, query, transaction và nhiều dạng đọc dữ liệu | Persistence context, provider, SQL và mapping JPA |
| MongoDB | Repository theo document, query và projection trên document | BSON, query MongoDB, index và điều kiện transaction |
| JDBC với database quan hệ | Mô hình aggregate và đường truy cập SQL imperative | Mapping aggregate và khả năng truy vấn cụ thể của module |
| R2DBC với database quan hệ | Repository reactive, tín hiệu publisher và context giao dịch | Driver reactive, subscription và khả năng của module |

Không dùng bảng này để suy rằng tất cả lựa chọn đều hỗ trợ nguyên xi cùng một executor, query operator hoặc cấu hình auditing. Cần đối chiếu tài liệu module trước khi đưa tính năng vào hợp đồng bài thực hành.

### 2.2. Lý do chọn JPA và PostgreSQL trong bài

Danh mục sản phẩm là mô hình nhỏ, có dữ liệu scalar rõ ràng, thuận tiện cho việc đối chiếu CRUD, điều kiện truy vấn, sort, page, projection và QBE. PostgreSQL cho phép quan sát trạng thái quan hệ và SQL thực tế, còn JPA làm rõ ranh giới giữa abstraction repository và cơ chế persistence.

Lựa chọn này có chi phí học thêm: cần hiểu entity manager, persistence context và flush. Những khái niệm đó được ghi nhận là phần của JPA; không mang chúng thành yêu cầu chung cho MongoDB hoặc mọi store khác.

## 3. Tách hợp đồng Commons khỏi implementation đã chọn

```text
Mã gọi repository và các kiểu Commons
    Repository, CRUD, Pageable, Sort, Example, projection
                           |
                           v
Spring Data JPA
    repository factory, query integration, entity mapping
                           |
                           v
JPA provider và JDBC driver
                           |
                           v
PostgreSQL
    bảng, ràng buộc, index, transaction và kế hoạch thực thi
```

| Thành phần | Vai trò trong bài thực hành |
| --- | --- |
| Spring Data Commons | Cung cấp các hợp đồng và hạ tầng dùng chung |
| Spring Data JPA | Kết nối các hợp đồng đó với persistence JPA |
| JPA provider | Quản lý entity, persistence context và thực thi mapping/query tương ứng |
| PostgreSQL JDBC driver | Giao tiếp với server PostgreSQL |
| PostgreSQL | Lưu dữ liệu và thực thi các bảo đảm thuộc database |
| Spring transaction manager phù hợp | Phối hợp ranh giới giao dịch của tài nguyên JPA |

Chỉ có dependency `spring-data-commons` chưa đủ tạo một repository lưu dữ liệu. Ngược lại, có driver database nhưng không có cấu hình repository factory cũng chưa chứng minh các interface repository được thực thi.

## 4. Chuẩn bị môi trường với các giả định rõ ràng

Bộ runtime cần có:

- Spring Data JPA và bộ phiên bản tương thích với Spring Framework cùng JPA provider.
- JDBC driver PostgreSQL phù hợp môi trường.
- Datasource, persistence unit, entity scanning và repository discovery.
- Transaction manager quản lý đúng cùng tài nguyên.
- Hạ tầng kiểm thử, chẳng hạn JUnit Jupiter và Spring TestContext.
- Các thành phần auditing cần thiết nếu đưa auditing vào phạm vi xác minh.

Nếu dùng một nền tảng quản lý dependency, hãy chọn bộ phiên bản do nền tảng đó hỗ trợ. Không tự nâng riêng Commons lên một version khác chỉ để có thêm API trong khi module JPA vẫn thuộc bộ không tương thích.

### 4.1. Ghi lại môi trường đã chạy

Người thực hành nên biết các giá trị thực tế:

```text
Java runtime
Spring Framework
Spring Data Commons
Spring Data JPA
JPA provider
PostgreSQL driver
PostgreSQL server
Cách khởi tạo schema và datasource của test
```

Không nhất thiết dùng phiên bản mới nhất cho mọi thành phần. Điều cần thiết là bộ tương thích, có thể chạy lại và đủ hỗ trợ các tính năng được chọn.

### 4.2. Chọn nơi lưu dữ liệu kiểm thử

Có thể dùng database hoặc schema riêng theo vòng đời bài thực hành, trên một PostgreSQL cục bộ hay môi trường kiểm thử được quản lý phù hợp.

Nếu thay PostgreSQL bằng một database nhúng ở một số ca nhanh, hãy ghi rõ phần bằng chứng đó thuộc database thay thế. Nó không tự xác minh collation, kiểu dữ liệu, transaction hoặc cú pháp riêng của PostgreSQL.

Môi trường riêng cũng giúp cleanup có phạm vi rõ ràng và tránh việc test này xóa dữ liệu của test khác.

## 5. Mô hình miền nhỏ nhưng đủ tạo đối chứng

Chọn aggregate `Product`:

| Thuộc tính | Kiểu Java trong ví dụ | Vai trò |
| --- | --- | --- |
| id | Long | ID persistence, không đoán trước giá trị sinh ra |
| sku | String | Mã nghiệp vụ duy nhất |
| name | String | Thuộc tính hiển thị và tìm kiếm |
| category | String | Điều kiện lọc đơn giản |
| price | BigDecimal | Giá để kiểm tra sort và khoảng giá |
| active | Boolean | Trạng thái có thể đưa vào probe, null trong probe nghĩa chưa lọc |
| version | Long | Metadata optimistic locking theo mapping JPA |
| createdAt | Instant | Thời điểm tạo bởi auditing |
| lastModifiedAt | Instant | Thời điểm sửa bởi auditing |

Lựa chọn Boolean thay primitive trong ví dụ giúp probe QBE biểu diễn “không cung cấp active” bằng null. Đối với entity được lưu, ứng dụng vẫn cần ràng buộc trạng thái hợp lệ theo nghiệp vụ.

### 5.1. Phần mapping thể hiện quyết định JPA

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "catalog_product")
@EntityListeners(AuditingEntityListener.class)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private String category;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private Boolean active;

    @Version
    private Long version;

    @CreatedDate
    @Column(updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    private Instant lastModifiedAt;

    protected Product() {
    }

    // Factory, getter và các phương thức thay đổi nghiệp vụ
    // được triển khai theo hợp đồng của bài thực hành.
}
```

Đây là phần khung mapping, chưa phải entity hoàn chỉnh có thể dùng mọi thao tác minh họa ngay. Cần bổ sung factory hợp lệ, getter và phương thức thay đổi như `changePrice` theo thiết kế domain.

`@Id`, `@GeneratedValue` và `@Version` ở đây là các annotation JPA. Những annotation thời gian auditing thuộc hạ tầng Spring Data, còn listener là tích hợp của JPA. Không đánh đồng các import có cùng tên ở mọi module.

Schema thực phải khớp mapping và các ràng buộc đã chọn. Annotation Java không tự chứng minh migration đã được áp dụng trên database đang chạy.

## 6. Định nghĩa repository để nhìn rõ các abstraction chung

Một cách biểu đạt các khả năng cần thực hành:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.PagingAndSortingRepository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

import java.util.Optional;

public interface ProductRepository
        extends CrudRepository<Product, Long>,
                PagingAndSortingRepository<Product, Long>,
                QueryByExampleExecutor<Product> {

    Optional<Product> findBySku(String sku);

    Page<ProductCard> findCardsByActiveTrueAndCategory(
            String category, Pageable pageable);
}
```

Projection đóng:

```java
import java.math.BigDecimal;

public interface ProductCard {

    Long getId();

    String getSku();

    String getName();

    BigDecimal getPrice();
}
```

Các accessor phải tương ứng đúng thuộc tính entity. Kiểu `ProductCard` là kiểu đọc dữ liệu, không phải domain root mới của repository.

Tài liệu [core concepts của Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/repositories/core-concepts.html) liên hệ các interface CRUD và phân trang với repository store thực. Có thể chọn `JpaRepository<Product, Long>` để dùng interface tiện ích của module; ví dụ trên tách các interface nhằm nhìn rõ những hợp đồng đang được xác minh.

### 6.1. Không dựa vào quan hệ kế thừa đã thay đổi theo release

Trong các dòng Spring Data hiện hành, interface sorting không mặc định cung cấp lại toàn bộ CRUD như một số phiên bản cũ. Nếu bài cần cả CRUD lẫn phân trang, khai báo rõ những khả năng cần dùng hoặc chọn interface module phù hợp.

### 6.2. Repository chung vẫn được một store cụ thể thực thi

Với một module JPA và domain đã mapping đúng, repository trên được hạ tầng JPA xử lý. Chữ ký dùng Commons không biến các entity JPA thành model có thể đưa sang store khác mà không sửa mapping hoặc kiểm tra khả năng.

## 7. Nạp fixture có thể dự đoán kết quả

Dùng sáu sản phẩm trong phạm vi kiểm thử riêng:

| Nhãn | sku | name | category | price | active |
| --- | --- | --- | --- | ---: | --- |
| A | CAP-A | Java Basics | BOOK | 100.00 | true |
| B | CAP-B | Spring Notes | BOOK | 150.00 | true |
| C | CAP-C | Old Java | BOOK | 80.00 | false |
| D | CAP-D | SQL Guide | BOOK | 150.00 | true |
| E | CAP-E | Desk Pad | OFFICE | 50.00 | true |
| F | CAP-F | Notebook | OFFICE | 30.00 | false |

Fixture có các đối chứng cần thiết:

- BOOK và OFFICE để phát hiện mất điều kiện category.
- active false để phát hiện bỏ quên trạng thái.
- Giá 100 và 150 để kiểm tra hai cận của khoảng.
- B và D cùng giá để kiểm tra khóa sort phụ.
- SKU duy nhất để tìm lại đúng entity mà không đoán ID.

Nếu chạy song song trên một database chung, không dùng nguyên SKU cố định cho mọi test. Có thể cấp schema riêng hoặc thêm phạm vi mã theo ca; khi đó các nhãn A–F là tên gọi logic, không nhất thiết là toàn bộ SKU thực tế.

### 7.1. Chuẩn bị dữ liệu cũng phải đi qua ranh giới rõ ràng

Khi mục tiêu là quan sát trạng thái lưu trữ, cần bảo đảm fixture đã được đồng bộ thích hợp. Với JPA, flush và clear có thể giúp tránh việc lần đọc chỉ quay lại object còn nằm trong persistence context.

Nếu ca cần kiểm tra sau commit, phải thực hiện commit rồi đọc trong transaction mới. Một test rollback thông thường không tự cung cấp bằng chứng đó.

## 8. Bộ phép thử xác minh tối thiểu trên store đã chọn

### 8.1. CRUD và ID

Thực hiện một vòng đời riêng cho một sản phẩm có SKU chưa dùng:

1. Tạo Product hợp lệ và gọi save.
2. Lấy entity cùng ID từ giá trị trả về.
3. Đọc lại theo ID sau ranh giới persistence phù hợp.
4. Thay đổi giá, lưu lại và xác nhận ID không đổi.
5. Xóa rồi kiểm tra vắng mặt theo ID.

Đừng assertion ID đầu tiên phải bằng 1 hoặc entity trả về phải cùng reference với đầu vào. Điều cần chứng minh là định danh và dữ liệu đúng theo hợp đồng đã chọn.

### 8.2. Derived query

`findBySku("CAP-B")` phải trả B; một SKU không có trong phạm vi fixture phải trả Optional rỗng.

Sự thành công này xác minh query method trên mapping và database của bài thực hành. Nó chưa chứng minh mọi toán tử derived query của mọi store đều được hỗ trợ.

### 8.3. Sort, page và projection

Dùng sort theo price tăng dần, rồi sku tăng dần:

```java
Sort sort = Sort.by("price").ascending()
        .and(Sort.by("sku").ascending());

Page<ProductCard> first = repository.findCardsByActiveTrueAndCategory(
        "BOOK", PageRequest.of(0, 2, sort));

Page<ProductCard> second = repository.findCardsByActiveTrueAndCategory(
        "BOOK", PageRequest.of(1, 2, sort));
```

`Sort` và `PageRequest` thuộc `org.springframework.data.domain`. Với fixture đã chọn, kỳ vọng:

```text
Trang đầu: A, B
Trang tiếp: D
Tổng phần tử khớp: 3
Tổng trang với kích thước 2: 2
C không xuất hiện vì inactive
E và F không xuất hiện vì khác category
```

Ngoài nội dung, kiểm tra đúng kiểu trường và giá trong projection. Nếu mục tiêu bao gồm hiệu năng, quan sát SQL thực tế, số query và dữ liệu được chọn; chỉ có interface nhỏ chưa đủ chứng minh tối ưu.

### 8.4. Query by Example

Tạo một probe chỉ mang category và active. Ví dụ helper domain cho mục đích tìm kiếm có thể tạo object không đặt ID, SKU, giá hoặc metadata; probe này dùng để tạo Example, không được lưu như một sản phẩm hợp lệ.

```java
Product probe = Product.categoryProbe("BOOK", false);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withIgnorePaths(
                "id", "sku", "name", "price", "version",
                "createdAt", "lastModifiedAt");

Example<Product> example = Example.of(probe, matcher);

List<Product> matches = new ArrayList<>();
repository.findAll(example).forEach(matches::add);
```

`Product.categoryProbe` là helper cần bổ sung cho model của bài thực hành: nó chỉ gán category và active trên một probe mới. Các import Example và ExampleMatcher thuộc `org.springframework.data.domain`, các collection thuộc `java.util`.

Kết quả với active false là C. Nếu active null theo chính sách bỏ qua null, tập BOOK gồm A, B, C, D.

Đây là QBE với phép khớp đơn giản. Không mở rộng kết luận thành QBE có thể diễn đạt mọi khoảng giá hoặc nhóm `AND (x OR y)`. Các giới hạn và sự phụ thuộc store được mô tả trong [QBE của Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/repositories/query-by-example.html).

### 8.5. Metadata domain và ID

Có thể kiểm tra khai báo repository trước khi quy lỗi cho database:

```java
RepositoryMetadata metadata = AbstractRepositoryMetadata.getMetadata(
        ProductRepository.class);

assertEquals(Product.class, metadata.getDomainType());
assertEquals(Long.class, metadata.getIdType());
```

Đoạn này dùng `RepositoryMetadata` từ `org.springframework.data.repository.core`, `AbstractRepositoryMetadata` từ package support và assertion JUnit Jupiter. Nó kiểm chứng cấu trúc metadata; việc store thật quản lý Product vẫn cần integration test.

## 9. Bật auditing như một tích hợp cần kiểm chứng

Annotation trên field chưa đủ cho mọi cấu hình. Với ví dụ JPA, cần bật hạ tầng auditing và đăng ký listener thích hợp. Tài liệu [auditing của Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/auditing.html) mô tả các thành phần và yêu cầu classpath, bao gồm phần tích hợp auditing cần thiết của JPA.

Một cấu hình thời gian minh họa:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

@Configuration
@EnableJpaAuditing(dateTimeProviderRef = "capstoneDateTimeProvider")
public class CapstoneAuditingConfiguration {

    @Bean
    Clock capstoneClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider capstoneDateTimeProvider(Clock clock) {
        return () -> Optional.of(Instant.now(clock));
    }
}
```

Ví dụ giả định không có nhiều Clock bean gây mơ hồ. Nếu ứng dụng đã có nguồn thời gian, hãy dùng một cấu hình rõ thay vì tạo thêm bean ngoài ý định.

Ở phạm vi cơ sở, chỉ ghi thời điểm tạo và sửa; chưa cần thêm cơ chế xác định người dùng chỉ để dùng timestamp auditing. Nếu bổ sung CreatedBy hoặc LastModifiedBy, phải thiết kế nguồn auditor phù hợp.

### 9.1. Những điều cần quan sát

- Sau khi tạo và đồng bộ hoặc commit đúng phạm vi, createdAt có giá trị theo nguồn thời gian đã chọn.
- Sau khi thay đổi dữ liệu thực sự ở một mốc thời gian khác, lastModifiedAt được cập nhật theo cấu hình.
- createdAt không bị thay thành mốc sửa sau đó.
- Dữ liệu đọc lại từ store có metadata tương ứng.

Test nên điều khiển nguồn thời gian để so sánh hai mốc rõ ràng. Không dựa vào việc ngủ một khoảng rất ngắn rồi yêu cầu timestamp luôn tăng trên mọi môi trường và độ chính xác lưu trữ.

## 10. Xác minh mở rộng repository trên cùng store

Sau khi các phép thử cơ bản ổn định, có thể thêm một fragment nhỏ để đọc sản phẩm active theo khoảng giá bao gồm hai cận.

```java
public interface ProductPriceLookup {

    List<ProductPriceRow> findWithinPriceRange(
            BigDecimal minInclusive, BigDecimal maxInclusive);
}
```

DTO đầu ra có thể là:

```java
public record ProductPriceRow(
        Long id, String sku, String name, BigDecimal price) {
}
```

Repository kết hợp thêm `ProductPriceLookup`, còn `ProductPriceLookupImpl` dùng EntityManager hoặc cơ chế JPA phù hợp để thực hiện query. Phải triển khai và đăng ký implementation thật; chỉ thêm interface chưa hoàn thành khả năng custom.

Với fixture, khoảng 100.00 tới 150.00 và điều kiện active phải trả A, B, D. Gọi qua repository proxy để kiểm chứng fragment thực sự được ghép, không chỉ gọi trực tiếp một object implementation.

Điều dùng chung ở đây là mô hình fragment và hợp đồng phương thức. JPQL, EntityManager và cách mapping kết quả thuộc implementation JPA. Nếu chuyển sang MongoDB, phần thực thi cần được thay bằng cơ chế document tương ứng và kiểm tra lại kết quả.

## 11. Ghi bằng chứng theo khả năng đã quan sát

Một ma trận thực hành có thể gồm:

| Khả năng | Bằng chứng cần thu thập | Giới hạn kết luận |
| --- | --- | --- |
| CRUD và ID | Vòng lưu, đọc, sửa, xóa qua repository thật | Đúng mapping Long và store đã chọn |
| Derived query | SKU tồn tại, vắng mặt và dữ liệu đối chứng | Chưa đại diện mọi operator |
| Page và Sort | Nội dung hai trang, total và khóa sort phụ | Fixture tĩnh và chính sách phân trang đã chọn |
| Projection | Giá trị accessor đúng; query quan sát được nếu đo tối ưu | Không suy ra mọi projection đều tải cùng cách |
| QBE | Category, false và null được xử lý theo chính sách | Không có nhóm điều kiện tùy ý hoặc range chung |
| Metadata | Product và Long được resolve đúng | Chưa chứng minh mapping persistence đầy đủ |
| Auditing | Metadata tồn tại sau ranh giới lưu trữ phù hợp | Phụ thuộc hạ tầng listener và nguồn thời gian |
| Fragment | Lời gọi qua proxy cho đúng kết quả custom | Query bên trong thuộc store implementation |
| Transaction | Dữ liệu sau commit hoặc rollback đúng theo ca riêng | Không tự bao hệ thống ngoài hoặc store khác |

Mỗi khả năng nên được đánh dấu theo việc đã thực sự chạy: đã xác minh, chưa xác minh hoặc ngoài phạm vi. Không đánh dấu thành công chỉ vì interface biên dịch, bean được inject hay mock đã trả kết quả mong muốn.

Các kết quả A–F trong bài là kỳ vọng để người thực hành đối chiếu, không phải số liệu được thu thập từ một lần chạy benchmark hoặc kiểm thử tại đây.

### 11.1. Phân loại sai lệch trước khi sửa

```text
Không tạo được bean
    -> Repository discovery, generic, mapping hoặc cấu hình store.

Method bị phân tích thành query ngoài ý định
    -> Fragment và cơ chế implementation.

Query chạy nhưng sai tập kết quả
    -> Điều kiện, null, case, fixture hoặc mapping.

Đọc cùng transaction đúng nhưng sau commit khác
    -> Ranh giới transaction và cách quan sát.

Chức năng đúng nhưng chậm
    -> SQL thật, số lượt truy cập, projection, count và index.
```

Không giải quyết mọi sai lệch bằng việc đổi store giữa chừng. Trước tiên cần xác định kết quả nào thuộc hợp đồng Commons và kết quả nào đến từ cách triển khai đã chọn.

## 12. Hoàn tất bước chọn store và chuẩn bị phép thử mở rộng

Bước này đạt mục tiêu khi người thực hành có một đường thực thi có thể giải thích:

```text
ProductRepository
    -> các hợp đồng dùng chung đã khai báo
    -> factory và implementation JPA
    -> provider cùng JDBC driver
    -> PostgreSQL của môi trường kiểm thử
```

Đồng thời có dữ liệu đối chứng, các kỳ vọng cụ thể và cách phân biệt một khả năng đã chạy với một khả năng mới chỉ được thiết kế.

Nếu muốn thử store thứ hai sau đó, hãy giữ lại các yêu cầu nghiệp vụ và bộ kỳ vọng có thể dùng chung, rồi ghi rõ những phần phải đổi: mapping, cấu hình, implementation fragment, query operator, transaction, auditing và công cụ quan sát. Việc cần thay đổi những phần đó là bằng chứng về ranh giới abstraction, không phải lý do ép mọi store mô phỏng JPA.

Chọn một store thực thi là tạo nền quan sát cho các abstraction dùng chung. Giá trị của bài thực hành nằm ở việc nối được hợp đồng Java với hành vi lưu trữ thật, xác định điều đã kiểm chứng và hiểu giới hạn của kết luận trước khi mở rộng sang công nghệ khác.
