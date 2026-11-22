# Kiểm thử derived query, JPQL và native query trong Spring Data JPA

## Mục tiêu bài học

Trong Spring Data JPA, một repository thường có ba cách định nghĩa truy vấn: **derived query** suy ra từ tên method, **JPQL** viết theo entity/property Java, và **native SQL** viết trực tiếp theo bảng/cột của database. Cả ba có thể trả dữ liệu trông giống nhau trong một bài test đơn giản, nhưng cơ chế xử lý, tính di động giữa database engines, cách phân trang và những lỗi tiềm ẩn lại khác nhau.

Ví dụ, test chỉ gọi `repository.findBySku("BK-001")` rồi kiểm `Optional.isPresent()` chưa đủ để chứng minh truy vấn lọc đúng trạng thái `active`, xử lý tên danh mục không phân biệt hoa/thường, giữ thứ tự khi có nhiều giá bằng nhau hoặc không trả bản ghi thừa. Đối với native query, test chạy xanh trên H2 cũng **không tự chứng minh** câu SQL hoạt động đúng trên PostgreSQL/MySQL production.

Sau bài này, bạn có thể:

- Phân biệt **derived query**, **JPQL** và **native SQL** theo cú pháp và nơi diễn giải.
- Đặt tên method như `findByCategoryIgnoreCaseAndActiveTrueOrderByPriceCentsAscSkuAsc`, `countBy...` và `existsBy...`.
- Dùng `@Query` với JPQL, `@Param`, các toán tử so sánh, truy vấn tổng hợp và **constructor projection**.
- Dùng `@Query(nativeQuery = true)` với **tên bảng/cột**, tham số bind, kết quả entity và **Pageable/countQuery**.
- Thiết kế fixture đủ mạnh để phát hiện lỗi điều kiện lọc, giá trị ở ranh giới, bản ghi inactive, thứ tự khi trùng giá, trường hợp rỗng và lỗi phân trang.
- Viết `@DataJpaTest` với H2 và `TestEntityManager`, dùng `flush`/`clear` đúng nơi để quan sát database thật.
- Hiểu transaction/rollback mặc định của JPA slice và tại sao đọc trong cùng persistence context có thể gây kết luận sai.
- Biết khi nào phải thay H2 bằng **PostgreSQL/MySQL Testcontainers** và không để embedded DataSource thay thế container ngoài ý muốn.
- Chẩn đoán lỗi tên property, JPQL sai entity, native SQL sai column, projection type, pagination count, query injection và hiệu năng N+1.
- Chạy ví dụ đầy đủ bằng **Java 17, Spring Boot 3.3.5, Gradle, JUnit Jupiter và Spring Data JPA**.

**Nguyên tắc trọng tâm:** Query test cần dùng **expected độc lập với chính truy vấn đang test**, chạy trên **database phù hợp với hợp đồng cần bảo vệ**, và kiểm cả nội dung lẫn điều kiện/ordering/pagination; không chỉ “query chạy không ném exception”.

## 1. Ba kiểu truy vấn: cùng interface, khác ngôn ngữ

Giả sử có entity Java:

~~~java
@Entity
@Table(name = "catalog_products")
public class CatalogProduct {
    // Java properties: sku, title, category, priceCents, active
}
~~~

Đây chỉ là snippet giới thiệu. Entity đầy đủ có ở mục 7.

### 1.1. Derived query: từ tên method

~~~java
List<CatalogProduct>
findByCategoryIgnoreCaseAndActiveTrueOrderByPriceCentsAscSkuAsc(
        String category);
~~~

Spring Data phân tích tên method thành predicate/filter và thứ tự sắp xếp. Ví dụ:

- `findBy` yêu cầu trả những entity khớp.
- `CategoryIgnoreCase` lọc `category` không phân biệt hoa/thường.
- `AndActiveTrue` lọc `active = true`.
- `OrderByPriceCentsAscSkuAsc` sắp theo `priceCents` tăng dần; khi bằng giá thì theo `sku` tăng dần.

Cách này **không phải SQL viết trong Java**; Spring Data phân tích property của entity và dựng truy vấn tương ứng. Nếu đổi tên field `priceCents` nhưng quên đổi tên method, repository có thể fail ngay khi Spring khởi tạo bean vì không tìm được property.

### 1.2. JPQL: theo entity và Java property

~~~java
@Query("""
    select p
    from CatalogProduct p
    where p.category = :category
      and p.active = true
      and p.priceCents >= :minimum
    order by p.priceCents asc, p.sku asc
    """)
List<CatalogProduct> findActiveCostingAtLeast(
        @Param("category") String category,
        @Param("minimum") long minimum);
~~~

Trong JPQL:

- `CatalogProduct` là **tên entity** (mặc định từ tên class) chứ không phải tên bảng `catalog_products`.
- `p.priceCents` là **Java property** chứ không phải cột `price_cents`.
- `:category` và `:minimum` là named parameters đã được bind.
- JPA provider (ví dụ Hibernate) chuyển JPQL thành SQL theo mapping/dialect.
- `>=` là inclusive boundary, nên sản phẩm bằng giá tối thiểu vẫn được trả.

Nếu viết `from catalog_products` trong JPQL mà không có entity mang tên đó, không nên kỳ vọng Hibernate tự hiểu là bảng. Ngược lại, nếu viết `price_cents` thay `priceCents` trong JPQL, truy vấn có thể fail vì property không tồn tại.

### 1.3. Native SQL: theo schema database

~~~java
@Query(value = """
    SELECT *
    FROM catalog_products
    WHERE category = :category
      AND active = TRUE
    ORDER BY price_cents DESC, sku ASC
    """, nativeQuery = true)
List<CatalogProduct> findActiveNative(
        @Param("category") String category);
~~~

Native query dùng **tên bảng/cột SQL thực tế**: `catalog_products`, `price_cents`, `active`. Nó có thể tận dụng dialect-specific functions, `CTE`, window functions hoặc database extensions, nhưng khả năng di chuyển giữa H2/PostgreSQL/MySQL thấp hơn JPQL.

Native query trả `CatalogProduct` chỉ khi tập cột/result mapping đủ để Hibernate dựng entity; tránh chọn thiếu cột bắt buộc rồi kỳ vọng ORM tự điền đầy đủ.

### 1.4. Bảng so sánh

| Tiêu chí | Derived query | JPQL | Native SQL |
| --- | --- | --- | --- |
| Nguồn cú pháp | Tên repository method | Chuỗi `@Query` theo entity/property | Chuỗi `@Query(nativeQuery=true)` theo table/column |
| Thích hợp | Lọc đơn giản, đếm, tồn tại, sort cơ bản | Joins, DTO projection, aggregate, biểu thức JPA | SQL vendor-specific, query phức tạp, tối ưu đặc thù |
| Lỗi thường thấy | Sai tên property hoặc keyword | Sai entity/property, type/projection | Sai tên bảng/cột, dialect, alias hoặc count |
| Tính di động | Tương đối tốt trong JPA | Tương đối tốt theo JPQL/Hibernate support | Phụ thuộc DB engine/dialect nhiều hơn |
| Test tối thiểu | Đúng tập record, filter, sorting | Filter/boundary, projection, aggregate | SQL thật, mapping, countQuery, dialect, pagination |
| Rủi ro khi test chỉ dùng H2 | Khác collation/case/null semantics | Provider/dialect chuyển SQL có khác biệt | Native SQL production có thể không chạy được trên H2 |

Không có loại nào “luôn tốt hơn”. Chọn loại query đơn giản nhất thể hiện hợp đồng đủ rõ và phù hợp hiệu năng, đồng thời viết test bảo vệ behavior.

## 2. `@DataJpaTest` kiểm gì?

`@DataJpaTest` trong Spring Boot 3.3 dùng để bootstrap một **JPA slice**. Nó thường:

- Quét JPA entities và Spring Data JPA repository interfaces.
- Cấu hình JPA, Hibernate và `EntityManager`.
- Tạo embedded database nếu driver tương ứng có trên test classpath.
- Mặc định chạy test trong transaction và **rollback sau mỗi test**.
- Cho phép inject `TestEntityManager` để tạo fixture.
- Không tự nạp toàn bộ `@Service`/`@Controller` của ứng dụng như `@SpringBootTest`.

Ví dụ:

~~~java
@DataJpaTest
class CatalogRepositoryTest {
    @Autowired
    CatalogProductRepository repository;

    @Autowired
    TestEntityManager entityManager;
}
~~~

Đây là snippet class test, chưa có test methods. Bộ project chạy được nằm ở mục 7.

### Test slice không phải HTTP integration test

Test gọi `repository.findBySku(...)` trực tiếp thông qua Spring Data JPA bean. Nó kiểm derived/JPQL/native query trên DB trong test context, nhưng **không kiểm** Spring MVC controller, JSON response, HTTP status, authentication filter hoặc một API client thực.

Nếu yêu cầu là “GET /api/products/{sku} trả HTTP 200 và JSON đúng”, phải thêm MVC/HTTP test ở tầng thích hợp. Nếu yêu cầu là “JPQL trả đúng sản phẩm active có giá >= minimum”, `@DataJpaTest` là lựa chọn tập trung và thường nhanh hơn full context.

### Rollback có giới hạn

Theo mặc định `@DataJpaTest` mở test transaction và rollback. Nhưng rollback ấy chỉ xử lý dữ liệu thuộc transaction test-managed; không tự xóa Redis cache, file, message hoặc những transaction được tạo độc lập. Đối với `@SpringBootTest(RANDOM_PORT)` có request HTTP thật, server transaction có thể commit ngoài test transaction — phải cleanup riêng.

Trong bài này, các tests gọi repository trực tiếp, không gửi HTTP, nên fixture tạo qua `TestEntityManager` nằm trong cùng transaction test và được rollback cuối mỗi method.

## 3. Dữ liệu fixture phải được thiết kế để bắt được lỗi

Một fixture yếu:

~~~text
Chỉ một sản phẩm:
BK-001 | Java Essentials | books | 2500 | active=true
~~~

Với một dòng duy nhất, rất nhiều query sai vẫn trả đúng:

- Query quên `active=true`.
- Query sắp xếp sai.
- Query dùng `>=` thay vì `>`.
- Query dùng sai `category` nhưng dữ liệu không có category khác.
- Native pagination `countQuery` sai nhưng trang đầu vẫn có một record.

Fixture mạnh hơn, dùng cho project runnable:

| SKU | Title | Category | Price cents | Active |
| --- | --- | --- | ---: | --- |
| BK-001 | Java Essentials | books | 2500 | true |
| BK-002 | Spring Boot | books | 3900 | true |
| BK-003 | Legacy Java | books | 1800 | false |
| BK-004 | Java Practice | books | 3900 | true |
| GE-001 | USB Cable | gear | 1500 | true |
| GE-002 | Laptop Stand | gear | 5200 | true |

Fixture cố ý có:

- **Ba** book active và **một** book inactive.
- Hai book cùng giá **3900**, buộc test kiểm secondary sort `sku`.
- Category khác `gear` để bắt filter sai.
- Giá **2500 và 3900** để kiểm boundary inclusive.
- Title chứa “Java” ở các vị trí khác nhau, kể cả record inactive, để kiểm `ContainingIgnoreCase`.
- Một số SKU chắc chắn tồn tại/không tồn tại.
- Tổng giá active books `2500 + 3900 + 3900 = 10300`.

**Expected phải lấy từ đặc tả fixture**, không gọi lại method đang test để tính “expected”. Chẳng hạn `assertEquals(repository.countByCategory(...), repository.findByCategory(...).size())` có thể để hai query cùng sai mà test vẫn xanh.

## 4. Derived query: những điều phải kiểm

### 4.1. `findBy...`: có và không có dữ liệu

~~~java
Optional<CatalogProduct> findBySku(String sku);
~~~

Hai ca cần thiết:

- `"BK-001"` → present và đúng SKU/title/price.
- `"NO-SUCH-SKU"` → `Optional.empty()`, không ném lỗi tùy tiện và không trả một entity khác.

Đừng chỉ kiểm `isPresent()`; nếu query vô tình trả sản phẩm khác, test vẫn pass. Khi entity có các trường trọng yếu, kiểm các giá trị hợp đồng.

### 4.2. `IgnoreCase` và điều kiện logic

~~~java
List<CatalogProduct>
findByCategoryIgnoreCaseAndActiveTrueOrderByPriceCentsAscSkuAsc(
        String category);
~~~

Test với `"BOOKS"` mặc dù fixture lưu `"books"`. Expected: `BK-001`, `BK-002`, `BK-004` theo thứ tự đó. `BK-003` inactive **không được xuất hiện**. Cặp `BK-002` và `BK-004` cùng giá giúp xác minh tie-breaker.

Việc kiểm cả tập giá trị và thứ tự bắt được lỗi mà chỉ assert `size() == 3` không bắt được. Ví dụ query sai trả `BK-001, BK-003, BK-004` vẫn có size 3.

### 4.3. `ContainingIgnoreCase`

~~~java
List<CatalogProduct>
findByTitleContainingIgnoreCaseOrderBySkuAsc(String fragment);
~~~

Với fragment `"JAVA"`, expected `BK-001`, `BK-003`, `BK-004` vì cả ba title có “Java” ở vị trí khác nhau. Record `BK-003` inactive **vẫn được trả** vì tên method **không chứa điều kiện `ActiveTrue`**. Đây là một assertion quan trọng để tránh thêm filter mà contract không yêu cầu.

Với fragment không xuất hiện, expected list rỗng chứ không phải null. `Containing` thường được chuyển thành biểu thức `LIKE` tương ứng với substring; chi tiết xử lý ký tự đặc biệt và collation cần đối chiếu bản Spring Data JPA và engine.

### 4.4. `countBy`, `existsBy`

~~~java
long countByCategoryAndActiveTrue(String category);
boolean existsBySku(String sku);
~~~

- `countByCategoryAndActiveTrue("books")` → 3.
- `countByCategoryAndActiveTrue("gear")` → 2.
- `existsBySku("BK-001")` → true.
- `existsBySku("unknown")` → false.

Đừng test `existsBySku` bằng cách gọi `findBySku` rồi chỉ so kết quả hai method: nếu cả hai map sai property, chúng có thể đồng thuận nhưng vẫn sai theo fixture.

### 4.5. Logic `And`/`Or` và tên property dài

Spring Data phân tích tên method thành biểu thức. Với tổ hợp `And` và `Or`, hãy đặt test cho **từng nhánh và phần giao** để phát hiện lỗi logic. Khi truy vấn trở nên quá dài/khó đọc, JPQL hoặc Specification có thể diễn đạt predicate rõ hơn.

Ví dụ tên:

~~~java
List<CatalogProduct>
findByCategoryAndActiveTrueOrSku(String category, String sku);
~~~

Đây là **snippet không thuộc runnable repository** và chỉ dùng giải thích: người đọc rất dễ hiểu sai nhóm điều kiện. Không viết test chỉ có một record; thêm các record nằm riêng ở mỗi nhánh để xác nhận chính xác precedence. Khi ý định nghiệp vụ là `category AND (active OR sku = X)`, biểu diễn bằng `@Query`/Specification có dấu ngoặc tường minh sẽ dễ review hơn.

### 4.6. Nested property và đổi tên field

Nếu entity có `Customer customer` và `Customer.address.city`, Spring Data có thể xử lý property traversal trong tên method. Dấu gạch dưới `_` đôi khi được dùng để giải tỏa mơ hồ đường dẫn property theo tài liệu Spring Data. Tuy nhiên, tên quá dài dễ gãy khi refactor model; test cần tạo fixture với customer ở nhiều thành phố và cả trường hợp không có liên kết.

**Không giả định tên cột SQL được dùng trong tên derived method.** `findByPriceCents` trỏ tới Java property `priceCents`, không phải `price_cents`.

## 5. JPQL: viết trên model thay vì schema SQL

### 5.1. Named parameter

~~~java
@Query("""
    select p from CatalogProduct p
    where p.category = :category
      and p.active = true
      and p.priceCents >= :minimum
    order by p.priceCents asc, p.sku asc
    """)
List<CatalogProduct> findActiveCostingAtLeast(
        @Param("category") String category,
        @Param("minimum") long minimum);
~~~

Với `category="books"`, `minimum=2500`, expected `BK-001`, `BK-002`, `BK-004`. Với `minimum=3900`, expected `BK-002`, `BK-004` và **không có `BK-001`**. Các ca này phát hiện:

- Quên điều kiện active.
- Sai dấu `>=` thành `>`.
- Lọc `category` sai.
- Sắp xếp theo giá sai chiều.
- Không có tie-breaker khi hai giá bằng nhau.

**Named parameters** làm query dễ đọc hơn khi có nhiều giá trị. `@Param("category")` khớp với `:category` trong JPQL, không phải tên column.

### 5.2. `select new ...`: DTO constructor projection

Khi chỉ cần SKU và price, không nhất thiết lấy toàn bộ entity:

~~~java
@Query("""
    select new com.example.jpaquery.SkuPrice(
        p.sku, p.priceCents)
    from CatalogProduct p
    where p.category = :category
      and p.active = true
    order by p.sku asc
    """)
List<SkuPrice> findActivePrices(
        @Param("category") String category);
~~~

`SkuPrice` là Java record với constructor `(String,long)`. JPQL **constructor expression** dùng tên class đầy đủ và thứ tự/type arguments khớp constructor. Test phải kiểm cả SKU, price và thứ tự. Nó không nên chỉ kiểm `list.size()`.

Một số projection có constructor/alias behavior khác tùy Spring Data/Hibernate version; nếu constructor không khớp, context có thể fail lúc validation hoặc query fail lúc thực thi. Dùng record DTO public với constructor rõ ràng giảm mơ hồ.

### 5.3. Aggregate `SUM` và empty result

~~~java
@Query("""
    select sum(p.priceCents) from CatalogProduct p
    where p.category = :category and p.active = true
    """)
Long totalPriceOfActiveProducts(
        @Param("category") String category);
~~~

Với books active, tổng là **10300**; với gear active, tổng **6700**. Nhưng khi **không có dòng nào**, SQL/JPA `SUM` thường trả **null**, không phải 0. Vì vậy method khai báo `Long` (boxed) và test có assertion `assertNull` cho category không tồn tại.

Nếu hợp đồng ứng dụng yêu cầu 0, dùng `coalesce(sum(...), 0)` trong JPQL hoặc chuyển ở service **có chủ đích**; đừng viết test kỳ vọng 0 trong khi query thực trả null.

### 5.4. JPQL join, `distinct` và N+1

Khi entity có quan hệ `@OneToMany`, join có thể tạo nhiều row SQL cho một parent. Một query:

~~~java
@Query("""
    select p from ParentOrder p
    join p.items i
    where i.active = true
    """)
List<ParentOrder> findOrdersWithActiveItems();
~~~

Đây là **snippet lý thuyết**, không thuộc project runnable: cần entity `ParentOrder` và `OrderItem`. Nếu một order có ba active items, join sinh nhiều SQL rows; tùy cách ORM deduplicate kết quả và phiên bản, test cần xác định contract và cân nhắc `select distinct p`. Không chỉ tạo mỗi order một item.

Đừng kết luận “JPQL tự tránh N+1”. Khi truy cập lazy associations sau query, có thể xảy ra **N+1 selects**. Nếu hiệu năng là hợp đồng, thêm test/quan sát SQL statement count bằng Hibernate statistics, `EntityGraph`/`join fetch` hoặc integration profiling phù hợp; `@DataJpaTest` với một entity không liên kết chưa kiểm vấn đề này.

## 6. Native SQL: đúng schema, đúng engine và đúng count

### 6.1. Entity mapping

~~~java
@Query(value = """
    SELECT *
    FROM catalog_products
    WHERE category = :category
      AND active = TRUE
    ORDER BY price_cents DESC, sku ASC
    """, nativeQuery = true)
List<CatalogProduct> findActiveNative(
        @Param("category") String category);
~~~

Câu này dùng cột `price_cents` và bảng `catalog_products`, không dùng `CatalogProduct.priceCents` như JPQL. Trong demo, H2 chấp nhận `TRUE` trong boolean comparison; PostgreSQL cũng hỗ trợ BOOLEAN. Nếu production MySQL mapping boolean thành `TINYINT`, câu SQL và test cần được xác minh trên MySQL thực, không chỉ dựa vào tương thích giả định.

Expected cho books active theo price giảm dần, SKU tăng dần khi trùng giá: `BK-002`, `BK-004`, `BK-001`.

### 6.2. Named parameters tránh SQL injection

~~~java
@Query(
    value = "SELECT * FROM catalog_products WHERE sku = :sku",
    nativeQuery = true)
CatalogProduct findOneNativeBySku(@Param("sku") String sku);
~~~

Đây là snippet minh họa không thuộc runnable repository. `:sku` là bind parameter; người dùng không thể biến giá trị `sku` thành các toán tử SQL mới chỉ bằng cách gửi dấu quote. Ngược lại, mẫu nối chuỗi trực tiếp:

~~~java
// KHÔNG NÊN: nội dung user đi thẳng vào cú pháp SQL.
String sql = "SELECT * FROM catalog_products WHERE sku = '"
        + userInput + "'";
~~~

có nguy cơ SQL injection và lỗi escape. **Bind parameters cho giá trị**; với sort column/table name động (vốn không phải value parameters), dùng **allowlist** những identifier được phép chứ không nối input raw.

### 6.3. Native pagination cần `countQuery`

~~~java
@Query(
    value = """
        SELECT * FROM catalog_products
        WHERE category = :category
          AND active = TRUE
        ORDER BY price_cents ASC, sku ASC
        """,
    countQuery = """
        SELECT COUNT(*) FROM catalog_products
        WHERE category = :category
          AND active = TRUE
        """,
    nativeQuery = true)
Page<CatalogProduct> findNativePage(
        @Param("category") String category,
        Pageable pageable);
~~~

Phần `value` lấy nội dung trang theo sort; `countQuery` đếm **tổng số record phù hợp**. Trong demo có ba books active:

- `PageRequest.of(0, 2)` → trang 0: `BK-001`, `BK-002`; `totalElements=3`, `totalPages=2`.
- `PageRequest.of(1, 2)` → trang 1: `BK-004`, cùng totalElements.
- `PageRequest.of(0, 2)` với category không tồn tại → content rỗng, totalElements=0.

`PageRequest.of` dùng **page index bắt đầu từ 0**, không phải 1. `Page` có thể cần query count để biết tổng số records; `Slice` thường chỉ quan tâm có trang tiếp không. Nếu native SQL có join/group by/distinct, countQuery phải **đếm đúng tập kết quả logic** (thường cần `COUNT(DISTINCT ...)` hoặc subquery), không chỉ copy `COUNT(*)` bừa.

**Vì sao phải có ORDER BY ổn định?** Không có sort, DB có thể trả row theo thứ tự bất kỳ; các trang khác nhau có thể bị chồng chéo/bỏ sót khi execution plan đổi. Khi price trùng nhau, secondary sort theo SKU tạo thứ tự xác định trong fixture; production cũng cần uniqueness/tie-breaker phù hợp với dữ liệu thực.

### 6.4. Native dynamic sort không phải miễn phí

Spring Data JPA hỗ trợ native query pagination/sort ở các mức khác nhau tùy version và query parser. Đối với **SQL phức tạp**, framework không phải lúc nào cũng tự viết lại `ORDER BY`, thêm count hoặc xử lý vendor syntax đúng. Trong ví dụ, ta **đặt ORDER BY cố định trong SQL** và dùng `PageRequest.of(page,size)` không kèm sort để tránh phụ thuộc rewrite.

Nếu API cho phép user sort, dùng repository/query builder có allowlist sort fields, hoặc các phương án được hỗ trợ chắc chắn bởi version hiện tại. Đừng gửi một `Sort.by(userInput)` tùy ý vào native query rồi giả định nó hợp lệ và an toàn trên mọi dialect.

### 6.5. Native projection và aliases

Khi native SQL trả DTO/projection interface, kết quả thường phụ thuộc **aliases**, type conversion và naming:

~~~java
public interface PriceView {
    String getSku();
    Long getPriceCents();
}
~~~

Ví dụ định hướng về SQL:

~~~sql
SELECT
    sku AS sku,
    price_cents AS priceCents
FROM catalog_products
WHERE category = :category
~~~

Đây là **snippet mở rộng**, không phải method đang dùng trong project runnable. Việc alias `priceCents` có được driver/dialect giữ nguyên hoa-thường hay bị fold case, và Spring Data có mapping camelCase/snake_case tương ứng hay không, cần test trên đúng DB/driver. Với projection phức tạp hoặc native SQL trả tuple không tự ánh xạ được, cân nhắc `@SqlResultSetMapping`/custom repository mapping theo API JPA tương ứng.

## 7. Project chạy được: Java 17 + Spring Boot 3.3.5 + H2

Ví dụ này có **entity, repository, DTO, Gradle build, boot configuration và một class JUnit với nhiều test độc lập**. Không cần khởi động HTTP server, Docker hoặc external database. Các query production mapping/tables đều đặt tường minh để người học nhìn ra sự khác biệt JPQL và SQL.

### 7.1. Cây thư mục

~~~text
jpa-query-test-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/jpaquery/
    │   ├── CatalogApplication.java
    │   ├── CatalogProduct.java
    │   ├── SkuPrice.java
    │   └── CatalogProductRepository.java
    └── test/java/com/example/jpaquery/
        └── CatalogProductRepositoryTest.java
~~~

Các file Gradle Wrapper cần được sinh từ Gradle phù hợp hoặc lấy từ repository; **không tự chép text vào `gradle-wrapper.jar`** vì đây là file binary.

**`settings.gradle`**

~~~groovy
rootProject.name = 'jpa-query-test-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**Giải thích dependency:**

- `spring-boot-starter-data-jpa` chứa Spring Data JPA, Hibernate, Spring JDBC, transaction manager và các API mapping JPA.
- H2 là `testRuntimeOnly`, vì ví dụ không muốn đưa embedded test database driver vào runtime production.
- `spring-boot-starter-test` có JUnit Jupiter, Spring TestContext, assertions và công cụ test Spring.
- `junit-platform-launcher` giúp Gradle chạy JUnit Platform theo cấu hình tương ứng.
- `useJUnitPlatform()` là thiết lập rõ cho Gradle `test` task.
- Spring Boot BOM quản lý versions JPA/Hibernate/H2/JUnit thích hợp; tránh ép một Hibernate khác version chỉ để chạy tutorial.

### 7.2. Boot application configuration

**`src/main/java/com/example/jpaquery/CatalogApplication.java`**

~~~java
package com.example.jpaquery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Mục tiêu của `CatalogApplication` là cung cấp `@SpringBootConfiguration`/auto-configuration root cho test slice. Demo không khai báo production datasource URL hay driver; hãy chạy bài bằng **Gradle test** như mục 8 thay vì kỳ vọng `bootRun` có production DB hoàn chỉnh.

### 7.3. Entity và tên cột tường minh

**`src/main/java/com/example/jpaquery/CatalogProduct.java`**

~~~java
package com.example.jpaquery;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "catalog_products")
public class CatalogProduct {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true,
            length = 32)
    private String sku;

    @Column(name = "title", nullable = false, length = 120)
    private String title;

    @Column(name = "category", nullable = false, length = 40)
    private String category;

    @Column(name = "price_cents", nullable = false)
    private long priceCents;

    @Column(name = "active", nullable = false)
    private boolean active;

    protected CatalogProduct() {
        // Required by JPA
    }

    public CatalogProduct(
            String sku, String title, String category,
            long priceCents, boolean active) {
        this.sku = sku;
        this.title = title;
        this.category = category;
        this.priceCents = priceCents;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getTitle() {
        return title;
    }

    public String getCategory() {
        return category;
    }

    public long getPriceCents() {
        return priceCents;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Các chi tiết cần để ý:

- `@Table(name = "catalog_products")` đặt **tên bảng SQL** cho native query.
- Java property `priceCents` ánh xạ cột `price_cents`. Derived/JPQL dùng `priceCents`; native dùng `price_cents`.
- `GenerationType.IDENTITY` để database cấp ID; test **không hardcode ID** vì IDENTITY có thể thay đổi giữa test runs.
- `sku` có unique constraint để không có hai sản phẩm trùng SKU trong demo.
- `active` là boolean cột SQL; trong schema H2 demo, native `active = TRUE` hoạt động.
- Không dùng `double` cho price cents trong ví dụ để tránh sai số floating-point; sản phẩm thật cần mô hình tiền tệ, precision, rounding và validation riêng.

Entity demo không có `@OneToMany`, nên nó chưa kiểm joins/lazy loading/N+1. Các trường hợp đó được thảo luận ở mục 11.

### 7.4. Record DTO projection

**`src/main/java/com/example/jpaquery/SkuPrice.java`**

~~~java
package com.example.jpaquery;

public record SkuPrice(String sku, long priceCents) {
}
~~~

Record có constructor công khai tương ứng với JPQL `new com.example.jpaquery.SkuPrice(p.sku,p.priceCents)`. Record equality theo component giúp JUnit `assertEquals` kiểm toàn bộ một `SkuPrice` chứ không phải object identity.

### 7.5. Repository chứa đủ ba kiểu query

**`src/main/java/com/example/jpaquery/CatalogProductRepository.java`**

~~~java
package com.example.jpaquery;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CatalogProductRepository
        extends JpaRepository<CatalogProduct, Long> {

    // 1. Derived query: exact SKU.
    Optional<CatalogProduct> findBySku(String sku);

    // 2. Derived query: case-insensitive category,
    // active-only and deterministic ordering.
    List<CatalogProduct>
    findByCategoryIgnoreCaseAndActiveTrueOrderByPriceCentsAscSkuAsc(
            String category);

    // 3. Derived query: substring search in title.
    List<CatalogProduct>
    findByTitleContainingIgnoreCaseOrderBySkuAsc(String fragment);

    // 4. Derived query: count and existence.
    long countByCategoryAndActiveTrue(String category);

    boolean existsBySku(String sku);

    // 5. JPQL: entity name and Java property names.
    @Query("""
        select p from CatalogProduct p
        where p.category = :category
          and p.active = true
          and p.priceCents >= :minimum
        order by p.priceCents asc, p.sku asc
        """)
    List<CatalogProduct> findActiveCostingAtLeast(
            @Param("category") String category,
            @Param("minimum") long minimum);

    // 6. JPQL constructor projection (DTO record).
    @Query("""
        select new com.example.jpaquery.SkuPrice(
            p.sku, p.priceCents)
        from CatalogProduct p
        where p.category = :category
          and p.active = true
        order by p.sku asc
        """)
    List<SkuPrice> findActivePrices(
            @Param("category") String category);

    // 7. JPQL aggregate. SUM may return null.
    @Query("""
        select sum(p.priceCents)
        from CatalogProduct p
        where p.category = :category
          and p.active = true
        """)
    Long totalPriceOfActiveProducts(
            @Param("category") String category);

    // 8. Native SQL: physical table/column names.
    @Query(value = """
        SELECT * FROM catalog_products
        WHERE category = :category
          AND active = TRUE
        ORDER BY price_cents DESC, sku ASC
        """, nativeQuery = true)
    List<CatalogProduct> findActiveNative(
            @Param("category") String category);

    // 9. Native SQL: scalar COUNT.
    @Query(value = """
        SELECT COUNT(*) FROM catalog_products
        WHERE category = :category AND active = TRUE
        """, nativeQuery = true)
    long countActiveNative(
            @Param("category") String category);

    // 10. Native Page: stable ORDER BY and exact countQuery.
    @Query(
        value = """
            SELECT * FROM catalog_products
            WHERE category = :category
              AND active = TRUE
            ORDER BY price_cents ASC, sku ASC
            """,
        countQuery = """
            SELECT COUNT(*) FROM catalog_products
            WHERE category = :category
              AND active = TRUE
            """,
        nativeQuery = true)
    Page<CatalogProduct> findNativePage(
            @Param("category") String category,
            Pageable pageable);
}
~~~

**Tính runnable của query code:**

- Dùng Java text blocks `"""`, hỗ trợ từ Java 15; Java 17 biên dịch được.
- `Optional`, `List`, `Page`, `Pageable` là return types phù hợp.
- JPQL `CatalogProduct` khớp entity name; native `catalog_products` khớp `@Table`.
- `priceCents` trong JPQL/derived khớp entity property; `price_cents` trong native khớp `@Column`.
- Named parameters có `@Param` đúng tên để tránh phụ thuộc Java parameter name metadata.
- Native query có fixed `ORDER BY` và `countQuery`, nên tests không cần dynamic Sort rewrite.
- Các method `count`/`exists` là derived queries, không cần `@Query` chỉ để gọi `COUNT(*)`.

### 7.6. `@DataJpaTest`: fixture, flush/clear và các assertions

**`src/test/java/com/example/jpaquery/CatalogProductRepositoryTest.java`**

~~~java
package com.example.jpaquery;

import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(
        properties = "spring.jpa.hibernate.ddl-auto=create-drop",
        showSql = false)
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY,
        connection = EmbeddedDatabaseConnection.H2)
class CatalogProductRepositoryTest {

    @Autowired
    private CatalogProductRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @BeforeEach
    void prepareFixture() {
        entityManager.persist(new CatalogProduct(
                "BK-001", "Java Essentials", "books",
                2500L, true));
        entityManager.persist(new CatalogProduct(
                "BK-002", "Spring Boot", "books",
                3900L, true));
        entityManager.persist(new CatalogProduct(
                "BK-003", "Legacy Java", "books",
                1800L, false));
        entityManager.persist(new CatalogProduct(
                "BK-004", "Java Practice", "books",
                3900L, true));
        entityManager.persist(new CatalogProduct(
                "GE-001", "USB Cable", "gear",
                1500L, true));
        entityManager.persist(new CatalogProduct(
                "GE-002", "Laptop Stand", "gear",
                5200L, true));

        // Buộc SQL INSERT chạy và bỏ entity cache cấp một.
        entityManager.flush();
        entityManager.clear();
    }

    private static List<String> skus(List<CatalogProduct> products) {
        return products.stream()
                .map(CatalogProduct::getSku)
                .toList();
    }

    @Test
    void derivedFindBySkuReturnsExactProduct() {
        CatalogProduct product =
                repository.findBySku("BK-001").orElseThrow();

        assertEquals("BK-001", product.getSku());
        assertEquals("Java Essentials", product.getTitle());
        assertEquals(2500L, product.getPriceCents());
        assertTrue(product.isActive());
    }

    @Test
    void derivedFindBySkuReturnsEmptyWhenMissing() {
        assertTrue(
                repository.findBySku("NO-SUCH-SKU").isEmpty());
    }

    @Test
    void derivedCategoryIgnoresCaseAndExcludesInactive() {
        var result = repository
                .findByCategoryIgnoreCaseAndActiveTrueOrderByPriceCentsAscSkuAsc(
                        "BOOKS");

        assertEquals(
                List.of("BK-001", "BK-002", "BK-004"),
                skus(result));
    }

    @Test
    void derivedContainingIgnoreCaseFindsSubstring() {
        var result = repository
                .findByTitleContainingIgnoreCaseOrderBySkuAsc("JAVA");

        // Có cả inactive BK-003 vì method không lọc active.
        assertEquals(
                List.of("BK-001", "BK-003", "BK-004"),
                skus(result));
    }

    @Test
    void derivedSearchWithoutMatchesReturnsEmptyList() {
        var result = repository
                .findByTitleContainingIgnoreCaseOrderBySkuAsc(
                        "never-appears");

        assertTrue(result.isEmpty());
    }

    @Test
    void derivedCountAndExistsUseIndependentFixtureFacts() {
        assertEquals(3L,
                repository.countByCategoryAndActiveTrue("books"));
        assertEquals(2L,
                repository.countByCategoryAndActiveTrue("gear"));

        assertTrue(repository.existsBySku("BK-001"));
        assertFalse(repository.existsBySku("NO-SUCH-SKU"));
    }

    @Test
    void jpqlFiltersInclusiveMinimumAndSorts() {
        var result = repository.findActiveCostingAtLeast(
                "books", 2500L);

        assertEquals(
                List.of("BK-001", "BK-002", "BK-004"),
                skus(result));
    }

    @Test
    void jpqlIncludesProductsExactlyOnBoundary() {
        var result = repository.findActiveCostingAtLeast(
                "books", 3900L);

        assertEquals(
                List.of("BK-002", "BK-004"),
                skus(result));
    }

    @Test
    void jpqlConstructorProjectionReturnsExactDtoValues() {
        var result = repository.findActivePrices("books");

        assertEquals(
                List.of(
                        new SkuPrice("BK-001", 2500L),
                        new SkuPrice("BK-002", 3900L),
                        new SkuPrice("BK-004", 3900L)),
                result);
    }

    @Test
    void jpqlSumCalculatesActivePrices() {
        Long booksTotal =
                repository.totalPriceOfActiveProducts("books");
        Long gearTotal =
                repository.totalPriceOfActiveProducts("gear");

        assertEquals(10300L, booksTotal);
        assertEquals(6700L, gearTotal);
    }

    @Test
    void jpqlSumWithNoMatchesReturnsNull() {
        assertNull(
                repository.totalPriceOfActiveProducts(
                        "no-such-category"));
    }

    @Test
    void nativeSqlMapsColumnsAndOrdersDescending() {
        var result = repository.findActiveNative("books");

        assertEquals(
                List.of("BK-002", "BK-004", "BK-001"),
                skus(result));
    }

    @Test
    void nativeCountMatchesExactActiveFilter() {
        assertEquals(3L,
                repository.countActiveNative("books"));
        assertEquals(2L,
                repository.countActiveNative("gear"));
        assertEquals(0L,
                repository.countActiveNative("missing"));
    }

    @Test
    void nativePageHasStableContentAndCorrectTotals() {
        Page<CatalogProduct> page0 =
                repository.findNativePage(
                        "books", PageRequest.of(0, 2));

        assertEquals(
                List.of("BK-001", "BK-002"),
                skus(page0.getContent()));
        assertEquals(3L, page0.getTotalElements());
        assertEquals(2, page0.getTotalPages());
        assertTrue(page0.hasNext());

        Page<CatalogProduct> page1 =
                repository.findNativePage(
                        "books", PageRequest.of(1, 2));

        assertEquals(
                List.of("BK-004"),
                skus(page1.getContent()));
        assertEquals(3L, page1.getTotalElements());
        assertFalse(page1.hasNext());
    }

    @Test
    void nativePageForMissingCategoryIsEmpty() {
        Page<CatalogProduct> page =
                repository.findNativePage(
                        "missing", PageRequest.of(0, 2));

        assertTrue(page.getContent().isEmpty());
        assertEquals(0L, page.getTotalElements());
        assertEquals(0, page.getTotalPages());
    }

    @Test
    void jpqlAndNativeReturnSameSetWhenPredicatesAgree() {
        Set<String> jpqlSkus = Set.copyOf(skus(
                repository.findActiveCostingAtLeast(
                        "books", 0L)));

        Set<String> nativeSkus = Set.copyOf(skus(
                repository.findActiveNative("books")));

        // Đối chiếu cross-query, và cả expected độc lập.
        assertEquals(
                Set.of("BK-001", "BK-002", "BK-004"),
                jpqlSkus);
        assertEquals(jpqlSkus, nativeSkus);
    }

    @Test
    void queryParameterIsDataNotSqlSyntax() {
        String suspicious = "' OR 1=1 --";

        var result = repository
                .findByTitleContainingIgnoreCaseOrderBySkuAsc(
                        suspicious);

        assertTrue(result.isEmpty());
    }

    @Test
    void allQueryResultsArePersistedEntities() {
        CatalogProduct result =
                repository.findBySku("GE-001").orElseThrow();

        assertNotNull(result.getId());
        assertEquals("gear", result.getCategory());
        assertEquals(1500L, result.getPriceCents());
    }
}
~~~

### 7.7. Mỗi test bảo vệ hợp đồng gì?

Class trên có **18 method `@Test`**, không có `@ParameterizedTest` hoặc repeated invocation. Mỗi method chạy trên transaction test riêng với fixture sáu products và rollback cuối test.

| Nhóm | Test | Sai sót có thể bắt |
| --- | --- | --- |
| Derived exact lookup | `derivedFindBySkuReturnsExactProduct` | Sai SKU, title, price, active |
| Derived missing | `derivedFindBySkuReturnsEmptyWhenMissing` | Query trả nhầm record khi không tìm thấy |
| Derived compound filter | `derivedCategoryIgnoresCaseAndExcludesInactive` | Không IgnoreCase, quên active, sai sort/tie-break |
| Derived substring | `derivedContainingIgnoreCaseFindsSubstring` | Sai LIKE/IgnoreCase, lọc inactive ngoài contract |
| Derived empty | `derivedSearchWithoutMatchesReturnsEmptyList` | Sai match predicate |
| Count/exists | `derivedCountAndExistsUseIndependentFixtureFacts` | Đếm sai active/category, trả exists sai |
| JPQL inclusive | `jpqlFiltersInclusiveMinimumAndSorts` | Sai min/active/category/order |
| JPQL boundary | `jpqlIncludesProductsExactlyOnBoundary` | Dùng `>` thay `>=` |
| JPQL DTO | `jpqlConstructorProjectionReturnsExactDtoValues` | Sai property/constructor/value |
| JPQL sum | `jpqlSumCalculatesActivePrices` | Quên inactive hoặc category |
| JPQL no rows | `jpqlSumWithNoMatchesReturnsNull` | Nhầm `SUM` rỗng với 0 |
| Native mapping/order | `nativeSqlMapsColumnsAndOrdersDescending` | Sai column names/sort |
| Native count | `nativeCountMatchesExactActiveFilter` | Count predicate sai |
| Native Page | `nativePageHasStableContentAndCorrectTotals` | Sai countQuery, offset/page, sort |
| Native empty Page | `nativePageForMissingCategoryIsEmpty` | Count/content sai khi không match |
| Cross-query | `jpqlAndNativeReturnSameSetWhenPredicatesAgree` | JPQL/native khác filter (đồng thời kiểm expected độc lập) |
| Parameter binding | `queryParameterIsDataNotSqlSyntax` | Input làm thay đổi predicate bất ngờ |
| Persistence | `allQueryResultsArePersistedEntities` | Entity/ID/mapping chưa lưu đúng |

**Lưu ý:** Trong Spring Data, `Page` có thể bỏ qua thực thi count SQL ở một số trường hợp khi framework suy ra total từ nội dung trang. Vì vậy các test `Page` bảo vệ **kết quả total/count behavior**, không khẳng định countQuery chắc chắn luôn được gửi xuống database ở mỗi request. Nếu cần xác minh **chính xác SQL count** hoặc hiệu năng, phải quan sát SQL/metrics trên database và các tình huống pagination đủ dữ liệu.

## 8. Chạy project và xem kết quả

Trong thư mục gốc có Gradle Wrapper, JDK 17 và khả năng tải Maven dependencies:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy riêng JUnit class:

~~~bash
./gradlew test --tests 'com.example.jpaquery.CatalogProductRepositoryTest'
~~~

Dự kiến **18 lượt test pass** với project/hạ tầng như mô tả. Đây là **kết quả suy ra từ source code**, không phải bằng chứng đã chạy trên máy người học. Test không in `System.out.println`, nên không có stdout nghiệp vụ cố định; Gradle có thể báo `BUILD SUCCESSFUL` nếu build/test thành công.

Thông thường báo cáo ở:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    └── TEST-com.example.jpaquery.CatalogProductRepositoryTest.xml
~~~

Với multi-module, `build` thuộc module chứa test. Nếu `test` bị báo `UP-TO-DATE` hoặc `FROM-CACHE`, kết quả có thể là cached; khi chẩn đoán có thể dùng:

~~~bash
./gradlew test --rerun-tasks
~~~

Nếu project mới chưa có Wrapper, một Gradle đã cài và tương thích có thể bootstrap, ví dụ:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Sau đó giữ `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties` và `gradle-wrapper.jar` trong repository theo quy định. Dự án thật nên ưu tiên Wrapper đang dùng, không nâng version chỉ để chạy bài học.

### SQL logs và câu query thực thi

Trong `@DataJpaTest`, thuộc tính `showSql = false` của demo tắt hiển thị SQL trên stdout để tập trung vào test results. Khi debug, có thể bật logging của Hibernate SQL và bind parameters bằng **cấu hình test riêng**. Các logger cụ thể thay đổi giữa Hibernate 5 và 6; với Boot 3.3/Hibernate 6, thường dùng:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Đây là snippet cấu hình dành cho **test/debug environment**, không phải yêu cầu đưa vào production logs: bind parameters có thể chứa dữ liệu nhạy cảm. Trong ví dụ, log giúp thấy JPQL/derived được Hibernate dịch sang SQL, và native SQL dùng bảng/cột trực tiếp.

## 9. `flush` và `clear`: tại sao có thể tạo kết quả “xanh giả”?

JPA dùng **first-level cache / persistence context**. Khi `entityManager.persist(product)` được gọi, entity có thể đã nằm trong persistence context nhưng SQL INSERT chưa được flush đầy đủ theo timing/ID strategy. Hibernate cũng có thể trả entity managed từ cache khi gọi `findById` mà không round-trip database.

Nếu test chỉ:

~~~java
CatalogProduct saved = repository.save(product);
CatalogProduct loaded =
        repository.findById(saved.getId()).orElseThrow();
assertEquals(saved.getSku(), loaded.getSku());
~~~

đôi khi phép thử chỉ chứng minh persistence context đang giữ **cùng Java entity**, không kiểm được đầy đủ schema, SQL hoặc database mapping.

Trong demo:

~~~java
entityManager.flush();
entityManager.clear();
~~~

sau fixture giúp:

1. `flush` buộc JPA đồng bộ những INSERT pending xuống database **trong transaction test hiện tại**.
2. `clear` detach các managed entities khỏi persistence context.
3. Query tiếp theo cần ORM đọc/mapping từ database cho những entity không còn managed.
4. Các test vẫn được rollback cuối method; **flush không phải commit**.

Với `GenerationType.IDENTITY`, một INSERT có thể đã chạy sớm để lấy ID; vẫn giữ `flush/clear` như quy tắc test rõ nghĩa và áp dụng được với các mapping khác.

### Khi nào `flush` làm lộ lỗi?

- Unique/foreign-key constraint thực sự bị vi phạm.
- `nullable=false`/database NOT NULL khác expected.
- Column quá ngắn hoặc type conversion sai.
- SQL INSERT/UPDATE không hợp schema.
- Một query cần data được ghi xuống DB trước khi đối chiếu.

Đừng chỉ viết `repository.save(...)` rồi test một property của object đó; test repository muốn bảo vệ **persistence behavior** nên có ít nhất một trường hợp truy vấn lại từ database.

### Vì sao dùng `@DataJpaTest` rollback thay vì `deleteAll()`?

Fixture của từng test được tạo trong test-managed transaction và rollback; không cần xóa toàn bảng. `deleteAll()` trong `@AfterEach` có thể che lỗi hoặc làm test chậm; nếu datasource trỏ sai production DB, nó còn nguy hiểm. **Không coi rollback là lớp bảo vệ đủ** khi credentials/URL sai: phải bảo đảm database test được cô lập về quyền và mạng.

## 10. Bổ sung kiểm thử PostgreSQL với Testcontainers

Ví dụ H2 chứng minh JPA query contracts trên H2. Nếu production là PostgreSQL, nên có một lớp integration test chạy trên **PostgreSQL thực trong Testcontainers**, nhất là khi có:

- Native SQL dùng `jsonb`, `ILIKE`, `ON CONFLICT`, `RETURNING`, CTE hoặc window functions.
- Custom PostgreSQL enums, arrays, UUID, timestamp/time zone behavior.
- PostgreSQL-specific casts, collations, indexes hoặc query plans.
- Migration Flyway/Liquibase chạy theo dialect.
- Query có transaction/locking behavior phụ thuộc engine.
- Phân trang và count trên native query phức tạp, joins/distinct/group by.

### 10.1. Mẫu Testcontainers trên Spring Boot 3.3

Với project đã có JPA + Spring Boot Test, thêm test dependencies tương thích:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
~~~

Đây là **đoạn bổ sung**, không phải file `build.gradle` độc lập. Testcontainers cần Docker hoặc container runtime tương thích và image PostgreSQL sẵn có hoặc được tải.

Snippet cấu trúc class test:

~~~java
@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgresProductRepositoryTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    CatalogProductRepository repository;

    // @BeforeEach tạo fixture, @Test assert native SQL behavior...
}
~~~

Đây là **snippet mở rộng**, chưa có đủ imports/methods để compile độc lập; cần các thư viện Testcontainers, schema/fixtures và cấu hình JPA tương ứng.

**Quan trọng với Spring Boot 3.3:** `@DataJpaTest` thường có database replacement policy mặc định `ANY`, nên một DataSource do Testcontainers cấu hình có thể bị **thay bằng H2** nếu không đặt `@AutoConfigureTestDatabase(replace = NONE)`. Khi Boot 3.4+ ra đời, `Replace.NON_TEST` được thêm làm default và có cơ chế nhận diện một số test DB/connection details; nhưng **`NON_TEST` không tồn tại ở 3.3**. Dùng `NONE` tường minh khi cần giữ datasource container trên nhiều phiên bản.

### 10.2. Không chỉ kiểm “container đã start”

Có một `PostgreSQLContainer` trong JVM **không chứng minh repository đang dùng PostgreSQL**. Có thể thêm một diagnostic test:

~~~java
@Autowired
DataSource dataSource;

@Test
void repositoryReallyUsesPostgres() throws Exception {
    try (Connection connection = dataSource.getConnection()) {
        assertEquals(
                "PostgreSQL",
                connection.getMetaData().getDatabaseProductName());
    }
}
~~~

Đây là snippet cần imports JUnit, `javax.sql.DataSource` và `java.sql.Connection`. Kiểm DB product name và một SQL feature đặc thù giúp tránh kết luận sai khi embedded replacement âm thầm diễn ra. Không in username/password hoặc full connection URL chứa secrets trong CI logs.

### 10.3. Kiểm schema production thực

Trong project demo H2, `spring.jpa.hibernate.ddl-auto=create-drop` tạo schema theo entity mapping. Trong hệ thống production dùng Flyway/Liquibase, các repository tests cần có một lớp kiểm **migration thực sự** trên đúng DB engine. Nếu mọi test dùng Hibernate tạo schema, bug trong migration SQL có thể không bị phát hiện.

Với PostgreSQL Testcontainers, thường:

1. Khởi tạo container test riêng.
2. Chạy migrations đúng phiên bản.
3. Tạo fixture qua repository/SQL.
4. Gọi derived/JPQL/native queries.
5. Assert database product, dữ liệu, count và constraint.
6. Cleanup bằng rollback/test schema/container lifecycle phù hợp.

Đừng chạy migration destructive hoặc `TRUNCATE` trên DB production; test infrastructure nên dùng credentials/namespace riêng.

## 11. Join, null, distinct và pagination: mở rộng bộ test

Project runnable tập trung một entity để dễ chạy, nhưng repository production thường có quan hệ. Các lỗi sau nên được đưa vào checklist khi phát triển query thật.

### 11.1. Join tạo duplicate rows

Giả sử một order có ba items. Query join `Order o join o.items i` có thể tạo ba rows ở SQL. Nếu bạn muốn **danh sách các orders không lặp**, JPQL có thể dùng:

~~~java
@Query("""
    select distinct o from CustomerOrder o
    join o.items i
    where i.active = true
    """)
List<CustomerOrder> findOrdersWithActiveItems();
~~~

Đây là snippet minh họa, cần entity mappings riêng. Test phải tạo ít nhất một order có **hai active items**, rồi kiểm order chỉ xuất hiện một lần theo hợp đồng. Nếu fixture mỗi order một item, query thiếu `distinct` có thể vẫn pass.

Với pagination join, `countQuery` phải đếm đúng số parent distinct, không nhất thiết bằng `COUNT(*)` của join. `Page` total sai có thể khiến UI hiển thị số trang sai dù content trang đầu đúng.

### 11.2. `null` và optional filtering

Trong SQL, `= NULL` không giống `IS NULL`. JPQL/derived query có cách xử lý tham số null và nullability riêng tùy cú pháp/version. Không suy luận “truyền null nghĩa bỏ qua filter” nếu repository contract không định nghĩa như vậy.

Nếu mong:

- `category=null` → trả mọi category;
- hoặc `category=null` → chỉ bản ghi có category null;
- hoặc `category=null` → ném validation error;

thì phải **chọn một** và viết test tường minh. Với optional filters phức tạp, có thể dùng Specification/Criteria API hoặc JPQL:

~~~java
@Query("""
    select p from CatalogProduct p
    where (:category is null or p.category = :category)
    """)
List<CatalogProduct> findWithOptionalCategory(
        @Param("category") String category);
~~~

Đây là snippet mở rộng, không thuộc runnable repository. Trong hệ thống có dữ liệu lớn, optional OR condition có thể ảnh hưởng việc dùng index và query plan; test correctness không thay profiling trên DB thật.

### 11.3. Các boundary cho thời gian

Khi lọc bằng `Instant createdAt` hoặc ngày, thường chọn khoảng nửa mở:

~~~text
[startInclusive, endExclusive)
~~~

và kiểm đúng ba điểm: trước start, bằng start, bằng end (phải bị loại). Tránh dùng `23:59:59.999` tùy precision database vì có thể bỏ sót microseconds/nanoseconds. Với PostgreSQL/MySQL, time zone và kiểu `timestamp with/without time zone` cũng cần test trên đúng engine.

### 11.4. Case sensitivity và collation

`IgnoreCase` thường sinh biểu thức SQL xử lý `UPPER`/`LOWER` hoặc cơ chế tương ứng, nhưng **kết quả so sánh Unicode, dấu tiếng Việt và collation** không hoàn toàn giống nhau giữa H2, PostgreSQL và MySQL. Nếu product yêu cầu tìm kiếm tên tiếng Việt không phân biệt dấu/hoa-thường, cần một hợp đồng và search strategy riêng; `IgnoreCase` không tự có nghĩa “bỏ dấu tiếng Việt”.

Tạo fixture có các biến thể chữ hoa/thường/dấu và chạy trên database production engine tương ứng khi behavior đó quan trọng.

### 11.5. Ordering khi cùng giá trị

Trong project có hai books cùng `priceCents=3900`. Secondary sort `sku` buộc thứ tự xác định. Nếu SKU cũng trùng (không thể trong demo vì unique), nên dùng ID hoặc một khóa ổn định khác làm tie-breaker. Pagination mà chỉ `ORDER BY price` có thể mất/nhân đôi record giữa các trang khi execution plan đổi hoặc dữ liệu thay đổi.

Ngay cả khi ORDER BY ổn định, offset-based pagination dưới **concurrent writes** có thể dịch record; với feed lớn hoặc thay đổi liên tục, cân nhắc keyset/cursor pagination và test trên database thật.

## 12. Update/delete query và persistence context

Dù trọng tâm là SELECT, nhiều repository còn có `@Modifying @Query`:

~~~java
@Modifying
@Query("""
    update CatalogProduct p
    set p.active = false
    where p.category = :category
    """)
int deactivateCategory(@Param("category") String category);
~~~

Đây là snippet minh họa chưa thêm vào demo. Bulk update/delete **không đi qua tất cả entity lifecycle callbacks và không tự đồng bộ mọi entity đã managed trong persistence context** như cập nhật từng entity. Sau bulk query, các entity mà test đang giữ có thể còn **giá trị cũ**.

Một test đúng nên:

1. Persist fixture và `flush`.
2. Chạy bulk update/delete trong transaction phù hợp.
3. `clear` persistence context (hoặc dùng `@Modifying(clearAutomatically=true, flushAutomatically=true)` khi hiểu side effects).
4. Query lại từ DB.
5. Assert cả số row bị ảnh hưởng và dữ liệu sau cập nhật.

Không viết:

~~~java
CatalogProduct product = repository.findBySku("BK-001").orElseThrow();
// Chạy bulk update...
assertFalse(product.isActive());
~~~

và mong Java object `product` tự đổi state. Nó có thể vẫn là entity managed cũ. Phải đọc lại đúng context/time. Ngoài ra, test `@DataJpaTest` rollback DML cuối method nhưng không đồng nghĩa server-side transactions/messaging/cache ngoài test sẽ bị rollback.

## 13. Test query performance: correctness chưa đủ

Derived, JPQL và native SQL có thể trả cùng tập record nhưng khác cost:

- Index có được sử dụng không?
- Query có quét toàn bảng hay truy xuất theo khóa?
- `LIKE %fragment%` có làm mất lợi thế index thông thường?
- Join fetch có tạo Cartesian product hay N+1?
- Page countQuery có chậm hơn main query?
- Entity loading có lấy quá nhiều columns khi chỉ cần DTO?
- Sorting có cần memory sort vì thiếu composite index?
- Native query có dùng function/CTE không tương thích giữa engine?

**Unit/slice tests** chủ yếu chứng minh correctness. Để bảo vệ performance, dùng **query plan (`EXPLAIN`/`EXPLAIN ANALYZE`), integration benchmarks, Hibernate SQL statistics và dataset có kích thước đại diện** trên database đúng engine. Tránh assert thời gian mili-giây tuyệt đối bằng H2 với sáu records; kết quả rất dễ nhiễu và không đại diện production.

### Từ assertion tới metric có ích

| Mục tiêu | Phương pháp |
| --- | --- |
| Số bản ghi đúng | Assert list/page content và count |
| Tránh N+1 | Quan sát Hibernate SQL statement count hoặc profiling |
| Index được dùng | `EXPLAIN` trên engine thật, schema/migration thật |
| Pagination đúng với join | Test countQuery với parent có nhiều children |
| Query ổn định dưới dữ liệu lớn | Performance integration benchmark có dataset đáng kể |
| Native SQL portable | Test trên từng DB engine được hỗ trợ |
| Không rò dữ liệu tenant | Fixture nhiều tenants và assert query chỉ trả tenant hợp lệ |
| Query không gây injection | Bind parameters, allowlist dynamic identifiers, adversarial input |

## 14. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `PropertyReferenceException` | Derived method dùng sai tên Java property | Đối chiếu entity getter/field và keyword của Spring Data |
| JPQL báo unknown entity | Dùng tên bảng thay entity name | Dùng `CatalogProduct` hoặc entity name đã khai báo |
| JPQL báo unresolved property | Dùng `price_cents` thay `priceCents` | Dùng Java property trong JPQL |
| Native SQL báo table not found | Tên bảng/schema/dialect khác | Kiểm `@Table`, schema migration và DB hiện tại |
| Native SQL báo column not found | Dùng Java property thay SQL column | Kiểm `@Column` và thực tế DDL |
| Projection báo constructor mismatch | DTO class name/type/order không khớp | Kiểm `new fqcn(...)` và constructor public |
| `SUM` no matches trả null | SQL aggregate semantics | Dùng boxed type hoặc `coalesce` khi contract yêu cầu 0 |
| List đúng số lượng nhưng sai record | Chỉ assert `size()` | Assert SKU/field của từng record |
| Test sort fail ngẫu nhiên | Thiếu ORDER BY/tie-breaker | Sort bằng khóa ổn định và test giá trị trùng |
| `Page.totalElements` sai | CountQuery không giống predicate chính | Count đúng distinct/group/filter logic |
| Trang 2 trùng hoặc thiếu | ORDER BY không ổn định hoặc dữ liệu đổi | Stable ordering/cursor strategy và fixture phù hợp |
| Query pass H2, fail PostgreSQL | Dialect/native SQL/collation/type khác | Testcontainers đúng DB engine |
| Test nhìn thấy dữ liệu chưa commit | Persistence context/transaction test | Flush/clear; test commit boundary theo mục tiêu |
| Test query chỉ kiểm Java object đã save | Cache cấp một trả managed entity | Clear context, đọc lại |
| Constraint không fail như mong đợi | Chưa flush hoặc DB khác schema | `flush()` và assert root cause đúng |
| Test suite phụ thuộc thứ tự | Fixture/shared DB chưa reset | @DataJpaTest rollback, per-test namespace, cleanup |
| Native count scalar type mismatch | Driver/JPA đổi kiểu số | Dùng kiểu return thích hợp, kiểm mapping trên engine |
| Query `IgnoreCase` sai kỳ vọng tiếng Việt | Collation/Unicode semantics khác | Xác định search contract, test trên engine thật |
| Spring bean không khởi tạo | @Query lỗi syntax hoặc derived parsing | Đọc root cause trong `Failed to load ApplicationContext` |
| SQL injection có thể xảy ra | Nối raw input vào native SQL | Bind parameters và allowlist identifiers |
| `@DataJpaTest` vô tình dùng H2 thay container | Test datasource replacement policy | Với Boot 3.3, đặt `Replace.NONE` cho container |
| “Test pass” dù SQL migration hỏng | Test dùng Hibernate create-drop thay migration | Thêm migration integration test |
| N+1 hoặc query chậm | Joins/lazy loading/index không hợp lý | Profiling/query plan trên DB thật |

### Quy trình chẩn đoán một repository test fail

1. **Xác định query type:** derived, JPQL hay native? Đừng sửa tên column SQL nếu method đang parse Java property.
2. **Kiểm đúng database:** H2 test slice hay PostgreSQL/MySQL Testcontainers? Có embedded replacement không?
3. **Kiểm schema:** entity mapping, `@Column/@Table`, migration và data types có đúng?
4. **Kiểm fixture:** có đủ record active/inactive/category/price boundary/tie-order không?
5. **Kiểm transaction:** fixture đã flush chưa? Test đọc từ persistence context hay DB?
6. **Kiểm query predicate:** AND/OR, >= vs >, null, case/LIKE, joins/distinct.
7. **Kiểm result mapping:** entity/DTO/projection/scalar có đúng types và aliases?
8. **Kiểm pagination:** page index từ 0, ORDER BY, countQuery và tổng records.
9. **Đọc root cause và SQL debug** có kiểm soát, không log secrets.
10. **Sửa query hoặc fixture theo đặc tả**, không nới assertions chỉ để được màu xanh.

## 15. Chiến lược test theo tầng trong dự án thực

Một repository có thể được bảo vệ bởi nhiều loại test:

### Lớp 1 — derived/JPQL correctness trên embedded DB

Nhanh, phù hợp cho:

- Parse tên method.
- Kiểm DTO projection/basic aggregate.
- Filter/ordering/boundaries với fixture nhỏ.
- Hành vi repository contract không phụ thuộc dialect.

Dùng `@DataJpaTest` như project mẫu. Đánh giá bất cứ assertion nào chỉ kiểm existence/size mà không kiểm tập dữ liệu.

### Lớp 2 — query native trên DB engine production

Dùng Testcontainers hoặc database test tương đương cho:

- Native SQL, functions/CTEs/casts/JSON types.
- Schema migrations, constraints, collation và locking.
- Query plan/index behavior nếu performance quan trọng.
- CountQuery/pagination cho SQL phức tạp.

Cấu hình datasource test rõ ràng. Không cho CI credentials tới production DB. Nếu dùng multiple DataSources, phải xác minh repository được nối đúng datasource/transaction manager.

### Lớp 3 — service/API contract

Nếu repository được service gọi để tính nghiệp vụ, viết unit test cho logic thuần và integration test để kiểm wiring. Nếu kết quả query được exposed qua HTTP/GraphQL, có thể thêm WebMvcTest/HTTP integration để kiểm authorization, serialization, status, pagination API và error mapping. Không dùng HTTP test thay mọi query test: khi API fail, test cần chỉ ra lỗi nằm ở repository hay web layer.

### Lớp 4 — security và data isolation

Với multi-tenant application, điều kiện `tenant_id` không được bỏ sót dù query còn trả đúng một SKU. Fixture cần **cùng SKU ở tenants khác nhau** nếu schema cho phép, và test phải assert **không rò dữ liệu tenant khác**. Dùng security-aware repository/service filters và database policies phù hợp; một test chỉ có tenant duy nhất không phát hiện lỗi thiếu predicate.

## 16. Các bài tập luyện tập

**Bài A — đổi dấu boundary:** Sửa JPQL `p.priceCents >= :minimum` thành `> :minimum`. Chạy `jpqlIncludesProductsExactlyOnBoundary`. Test phải fail vì hai book giá đúng 3900 bị loại. Hoàn nguyên.

**Bài B — bỏ điều kiện active:** Tạm bỏ `p.active = true` trong `findActiveCostingAtLeast`. Với minimum 0, query sẽ thêm `BK-003`. Kiểm test cross-query/expected đỏ; giải thích vì sao test chỉ dùng min=3900 có thể không bắt lỗi này.

**Bài C — secondary sort:** Bỏ `sku ASC` trong JPQL/native/derived method tương ứng. Với hai books giá 3900, thứ tự có thể phụ thuộc query plan; giải thích vì sao đây là một bug tính ổn định ngay cả khi test đôi lúc còn xanh.

**Bài D — native countQuery:** Đổi countQuery thành `COUNT(*)` không có điều kiện active rồi chạy pagination với category books. Expected 3 active, nhưng count có thể báo 4. Quan sát việc thực thi count được tối ưu ở những trang khác nhau trước khi kết luận test nào chắc chắn bắt lỗi.

**Bài E — H2 vs PostgreSQL:** Thêm một native query dùng `ILIKE`/`jsonb` của PostgreSQL; test H2 có thể không hỗ trợ. Thử Testcontainers PostgreSQL và kiểm native SQL trên engine thật. Không thay production query chỉ vì H2 không hiểu dialect đặc thù.

**Bài F — projection:** Sửa thứ tự argument trong `new SkuPrice(...)` hoặc đổi type constructor; quan sát lỗi validation/mapping. Viết test kiểm cả SKU/price, không chỉ số record.

**Bài G — không có record:** Thử `totalPriceOfActiveProducts("missing")`. Giải thích tại sao `SUM` có thể null, `COUNT` là 0. Nếu business muốn total=0, cập nhật query bằng `coalesce` và thay assertion theo contract.

**Bài H — đổi persistence context:** Bỏ `entityManager.clear()` trong fixture. So sánh kết quả test entity lookup và SQL logs; giải thích tình huống nào có thể đọc từ cache cấp một. Sau đó thử đổi mapping và dùng `flush/clear` để bắt lỗi.

**Bài I — nhiều category/tenant:** Bổ sung tenantId vào entity và query. Thêm records ở hai tenants cùng category, kiểm isolation. Query thiếu tenant predicate phải fail với fixture này.

**Bài J — phân trang không ổn định:** Thêm nhiều products có cùng price; test PageRequest.of(0,2), PageRequest.of(1,2). Tạo stable sort theo `priceCents, sku`, kiểm không thiếu hoặc trùng SKU.

**Bài K — chống SQL injection:** Tạo một repository native query dùng bind parameter `:sku` rồi thử input có dấu quote/SQL operators. Assert đây chỉ là dữ liệu, không làm thay đổi SQL structure. Không chạy câu DELETE/DROP trên database không cô lập.

**Bài L — sai schema migration:** Dùng PostgreSQL Testcontainers với schema Flyway/Liquibase. Đổi tên một column trong migration test branch mà không đổi query native; query phải fail đúng nguyên nhân column missing. Hoàn nguyên.

## 17. Checklist trước khi merge repository queries

- [ ] Tôi biết query là **derived**, **JPQL** hay **native SQL**?
- [ ] Tên derived method dựa trên **Java property**, không phải SQL column?
- [ ] JPQL dùng đúng entity name, field/property và `@Param`?
- [ ] Native SQL dùng đúng table/column, schema, dialect của DB?
- [ ] Fixture có record active/inactive, nhiều category, boundary, empty case và tie-order?
- [ ] Assertion kiểm **đúng SKU/giá/tập record**, không chỉ count hoặc non-null?
- [ ] Các query có ORDER BY/tie-breaker khi contract đòi ổn định?
- [ ] Projection constructor/aliases/type chính xác và được test?
- [ ] Aggregate `SUM` xử lý null, `COUNT` xử lý zero đúng yêu cầu?
- [ ] `Pageable` dùng zero-based index, `countQuery` khớp predicate chính?
- [ ] Fixture đã `flush/clear` khi cần kiểm round-trip database thay vì persistence context cache?
- [ ] `@DataJpaTest` có đúng datasource test, rollback và không đụng production?
- [ ] Native/dialect-specific SQL được test trên đúng engine production bằng container/test DB?
- [ ] Dynamic value được bind bằng parameters, dynamic identifier được allowlist?
- [ ] Dữ liệu/transaction/migration của test được cô lập, không delete toàn DB chia sẻ?
- [ ] Các truy vấn join có test duplicate/distinct và N+1 nếu ảnh hưởng business/performance?
- [ ] Nếu có multi-tenancy, query không rò records của tenant khác?
- [ ] SQL logs không làm lộ dữ liệu nhạy cảm?
- [ ] Gradle report xác nhận test đã thực sự chạy; tôi không nhầm `UP-TO-DATE` với execution mới?

## 18. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@DataJpaTest`, embedded database, TestEntityManager và transactional rollback.
- [Spring Data JPA — Defining Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): derived queries, `@Query`, native queries, named parameters, pagination/projection.
- [Spring Data Commons — Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): cách parse property expressions/keywords của derived query.
- [Spring Data JPA — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html): interface và class/DTO-based projections.
- [Spring Data JPA — Transactions](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): transaction behavior của repository và method-level operations.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection`, database/container test setup.
- [Hibernate ORM — HQL/JPQL](https://docs.jboss.org/hibernate/orm/6.5/querylanguage/html_single/): entity queries, projections và semantics của Hibernate query language.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/3.1/): JPQL, entity mapping, `EntityManager`, persistence context và transaction.

**Ghi nhớ:** Derived queries dùng **tên Java property** trong method; JPQL dùng **entity/property** trong `@Query`; native SQL dùng **table/column/database dialect**. Test hiệu quả phải tạo fixture có điều kiện phản ví dụ, assert đầy đủ nội dung/thứ tự/boundary, flush/clear khi cần, và xác minh native query trên **đúng database engine**. Một bài test “repository trả được một dòng” chưa phải bằng chứng query đúng trong mọi nhánh.
