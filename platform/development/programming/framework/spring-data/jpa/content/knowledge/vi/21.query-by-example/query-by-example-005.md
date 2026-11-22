# Xử lý giá trị mặc định của kiểu nguyên thủy trong probe

Trong Spring Data JPA, **Query by Example (QBE)** tạo điều kiện truy vấn từ một object mẫu gọi là *probe*. Những thuộc tính có giá trị trong probe thường được dùng làm tiêu chí tìm kiếm; thuộc tính `null` mặc định được bỏ qua. Điều này tạo ra một vấn đề dễ bỏ sót với kiểu nguyên thủy của Java: `int` mặc định là `0`, `boolean` mặc định là `false`, và các primitive khác cũng có giá trị mặc định cụ thể. Chúng không thể là `null`, nên QBE có thể coi chúng là điều kiện lọc dù người gọi chưa hề cung cấp giá trị.

Ví dụ, một probe Product mới có `stock = 0` và `active = false`. Nếu chỉ muốn tìm theo tên nhưng không bỏ qua hai thuộc tính này, QBE có thể tìm sản phẩm có tồn kho bằng 0 và active=false. Cách xử lý phù hợp thường là dùng wrapper (`Integer`, `Boolean`) cho các tiêu chí tùy chọn, hoặc chủ động thêm property vào `withIgnorePaths` khi filter tương ứng không được cung cấp.

## 1. Probe và Query by Example hoạt động thế nào?

QBE là cách xây dựng truy vấn bằng một object mẫu thay vì viết JPQL/SQL cho từng tổ hợp điều kiện. Probe chứa những giá trị muốn tìm; `ExampleMatcher` quyết định cách so khớp các thuộc tính.

Repository cần mở rộng `QueryByExampleExecutor<T>`:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                QueryByExampleExecutor<Product> {
}
```

Ví dụ tạo probe:

```java
Product probe = new Product();
probe.setName("Tea");

Example<Product> example = Example.of(probe);
List<Product> products = productRepository.findAll(example);
```

Với cấu hình mặc định, các thuộc tính null thường bị bỏ qua, còn các thuộc tính có giá trị được dùng để tạo điều kiện. Với String, mặc định là exact matching; các thuộc tính không phải String cũng được so khớp chính xác theo giá trị.

Ví dụ về ý nghĩa truy vấn:

```text
Probe:
  name = "Tea"
  category = null

Điều kiện QBE:
  name = 'Tea'

category bị bỏ qua vì null.
```

QBE phù hợp với các điều kiện equality đơn giản và tổ hợp AND/OR cơ bản. Nó không phải công cụ tổng quát cho mọi biểu thức tìm kiếm; các điều kiện range, join phức tạp hoặc logic nghiệp vụ đặc biệt thường phù hợp với Specification, Criteria API, QueryDSL hoặc query tường minh hơn.

## 2. Giá trị mặc định của primitive trong Java

Khi tạo object và không gán giá trị cho field primitive, Java khởi tạo field bằng giá trị mặc định:

| Kiểu primitive | Giá trị mặc định |
|---|---|
| `byte` | `0` |
| `short` | `0` |
| `int` | `0` |
| `long` | `0L` |
| `float` | `0.0f` |
| `double` | `0.0d` |
| `char` | `'\u0000'` (ký tự NUL) |
| `boolean` | `false` |

Các field tham chiếu như `Integer`, `Long`, `Boolean`, `String` mặc định là `null` nếu không được gán.

Ví dụ:

```java
public class ProductProbe {
    private int stock;
    private boolean active;
    private Integer minRating;
    private Boolean featured;
}
```

Ngay sau `new ProductProbe()`:

```text
stock     = 0
active    = false
minRating = null
featured  = null
```

Khác biệt quan trọng: primitive luôn có một giá trị; wrapper có thể biểu diễn trạng thái chưa được cung cấp bằng null. Vì QBE mặc định bỏ qua null, wrapper giúp phân biệt “không lọc thuộc tính này” với “lọc theo giá trị 0/false”.

Lưu ý: constructor, field initializer hoặc builder có thể ghi đè giá trị mặc định của Java. QBE sử dụng giá trị thực tế đang có trong probe tại thời điểm tạo Example, không suy luận người dùng có gửi thuộc tính hay không.

## 3. Vì sao primitive gây lọc ngoài ý muốn?

Giả sử entity:

```java
@Entity
@Table(name = "product")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    private int stock;

    private boolean active;

    protected Product() {
    }

    // getters/setters
}
```

Tạo probe mới và chỉ gán tên:

```java
Product probe = new Product();
probe.setName("Tea");

Example<Product> example = Example.of(probe);
List<Product> result = repository.findAll(example);
```

Probe có các giá trị:

```text
id     = null
name   = "Tea"
stock  = 0
active = false
```

Hai field primitive có giá trị khác null theo bản chất Java. QBE có thể tạo điều kiện tương đương:

```sql
where name = 'Tea'
  and stock = 0
  and active = false
```

SQL trên chỉ minh họa ý nghĩa predicate. SQL thực tế do provider và database tạo ra.

Kết quả có thể rỗng hoặc chỉ chứa các sản phẩm vừa có tên Tea, vừa tồn kho bằng 0, vừa active=false. Người viết code có thể tưởng chỉ lọc theo tên, nhưng probe đã mang theo các giá trị primitive mặc định.

## 4. Cách ưu tiên: dùng wrapper cho tiêu chí tùy chọn

Nếu một thuộc tính có thể không được dùng làm filter, wrapper thường là lựa chọn tự nhiên:

```java
@Entity
@Table(name = "product")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    private Integer stock;

    private Boolean active;

    protected Product() {
    }

    // getters/setters
}
```

Tạo probe:

```java
Product probe = new Product();
probe.setName("Tea");
// stock và active vẫn null nên mặc định được bỏ qua.

ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnoreNullValues();

Example<Product> example = Example.of(probe, matcher);
List<Product> result = repository.findAll(example);
```

Khi muốn lọc rõ ràng theo stock=0 hoặc active=false:

```java
probe.setStock(0);
probe.setActive(false);

Example<Product> example = Example.of(
    probe,
    ExampleMatcher.matching().withIgnoreNullValues()
);
```

Lúc này 0 và false là giá trị wrapper không null, nên chúng là tiêu chí hợp lệ. Wrapper cho phép biểu diễn ba trạng thái nghiệp vụ thường gặp:

- `null`: không lọc thuộc tính.
- `0`: lọc đúng giá trị số 0.
- Số dương/âm hợp lệ: lọc theo giá trị cụ thể.

Với Boolean:

- `null`: không lọc theo active.
- `true`: chỉ lấy active=true.
- `false`: chỉ lấy active=false.

Đừng viết điều kiện kiểu `if (filter.getActive())` để quyết định có áp dụng filter hay không; cách đó bỏ mất trường hợp false có chủ đích. Hãy kiểm tra `filter.getActive() != null`.

## 5. Ví dụ đầy đủ với filter DTO và QBE

Trong ứng dụng thực tế, nên tách input tìm kiếm khỏi entity. DTO dùng wrapper để thể hiện filter có thể vắng mặt:

```java
public record ProductFilter(
    String name,
    Integer stock,
    Boolean active
) {
}
```

Repository:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                QueryByExampleExecutor<Product> {
}
```

Service:

```java
@Service
public class ProductSearchService {

    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    public List<Product> search(ProductFilter filter) {
        Product probe = new Product();
        probe.setName(filter.name());
        probe.setStock(filter.stock());
        probe.setActive(filter.active());

        ExampleMatcher matcher = ExampleMatcher.matching()
            .withIgnoreNullValues()
            .withMatcher("name", spec ->
                spec.contains().ignoreCase()
            );

        return repository.findAll(Example.of(probe, matcher));
    }
}
```

Ví dụ input:

```json
{
  "name": "tea",
  "stock": 0,
  "active": false
}
```

Cả ba tiêu chí đều có giá trị và được áp dụng. Nếu request chỉ gửi name, stock và active là null nên hai thuộc tính đó được bỏ qua.

Nếu DTO nhận `active` bằng primitive boolean, request không truyền active vẫn trở thành false sau khi deserialize. Khi đó service không thể phân biệt “không gửi active” với “gửi active=false”. Dùng `Boolean` ở request DTO để giữ được khác biệt này.

Nếu API cần phân biệt cả “không gửi field” và “gửi field với JSON null”, wrapper đơn thuần có thể chưa đủ vì cả hai thường cùng thành null sau binding. Khi semantics đó quan trọng, dùng cơ chế theo dõi field presence phù hợp với framework/API contract.

## 6. Khi entity bắt buộc dùng primitive: withIgnorePaths

Đôi khi entity dùng primitive là hợp lý vì domain/database yêu cầu giá trị luôn có mặt. Không nhất thiết phải đổi entity field chỉ để phục vụ QBE. Có thể dùng `ExampleMatcher.withIgnorePaths(...)` để loại những primitive không phải filter trong truy vấn hiện tại.

Ví dụ entity giữ primitive:

```java
@Entity
public class Product {
    @Id
    @GeneratedValue
    private Long id;

    private String name;

    private int stock;

    private boolean active;

    protected Product() {
    }

    // getters/setters
}
```

Nếu lần tìm kiếm chỉ lọc name, bỏ qua stock và active:

```java
Product probe = new Product();
probe.setName("Tea");

ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("stock", "active", "id")
    .withMatcher("name", spec ->
        spec.contains().ignoreCase()
    );

List<Product> result = repository.findAll(
    Example.of(probe, matcher)
);
```

Tên path trong `withIgnorePaths` là property Java của domain type, không phải tên cột database. Chỉ đưa vào danh sách những property cần bỏ qua trong query đó.

Không dùng `withIgnorePaths("stock", "active")` cố định nếu có những request cần lọc theo stock hoặc active. Một path đã bị ignore trong matcher thì không thể đồng thời dùng làm điều kiện của Example đó. Cần tạo matcher khác nhau tùy filter.

## 7. Tạo ignorePaths động khi filter tùy chọn

Nếu entity có primitive nhưng API cần cho phép lọc theo 0 và false khi người dùng gửi rõ ràng, dùng wrapper trong DTO để biết field có được cung cấp hay không; sau đó xây dựng ignore path động.

```java
public record ProductFilter(
    String name,
    Integer stock,
    Boolean active
) {
}
```

Service:

```java
public List<Product> search(ProductFilter filter) {
    Product probe = new Product();
    probe.setName(filter.name());

    List<String> ignoredPaths = new ArrayList<>();

    if (filter.stock() == null) {
        ignoredPaths.add("stock");
    } else {
        probe.setStock(filter.stock());
    }

    if (filter.active() == null) {
        ignoredPaths.add("active");
    } else {
        probe.setActive(filter.active());
    }

    ExampleMatcher matcher = ExampleMatcher.matching()
        .withIgnoreNullValues()
        .withIgnorePaths(ignoredPaths.toArray(String[]::new))
        .withMatcher("name", spec ->
            spec.contains().ignoreCase()
        );

    return repository.findAll(Example.of(probe, matcher));
}
```

Cách này xử lý được cả hai trường hợp:

| Filter input | Probe primitive | Matcher | Kết quả |
|---|---:|---|---|
| stock không gửi | 0 mặc định | ignore stock | Không lọc stock |
| stock = 0 | 0 | không ignore stock | Lọc stock=0 |
| active không gửi | false mặc định | ignore active | Không lọc active |
| active = false | false | không ignore active | Lọc active=false |
| active = true | true | không ignore active | Lọc active=true |

Điều quan trọng là quyết định ignore dựa trên sự hiện diện của filter DTO (wrapper), không dựa trên việc giá trị primitive có khác 0/false hay không.

## 8. withIgnoreNullValues và withIncludeNullValues

Mặc định, QBE bỏ qua các property null. Có thể thể hiện rõ bằng:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnoreNullValues();
```

Nếu muốn null trở thành tiêu chí tìm kiếm, dùng:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIncludeNullValues();
```

Với include null values, thuộc tính null được dùng để tìm các hàng có giá trị NULL tương ứng theo khả năng mapping/provider. Điều này thường không phải điều mong muốn cho form filter tùy chọn.

Phân biệt:

- **Ignore null:** không tạo điều kiện cho property null.
- **Include null:** tạo điều kiện tìm giá trị null.
- **Primitive:** không thể null, nên ignoreNullValues không bỏ qua giá trị mặc định 0/false.
- **Ignore path:** bỏ qua property bất kể giá trị của nó là gì.

Vì vậy, `withIgnoreNullValues()` không giải quyết được vấn đề primitive default. Muốn bỏ qua primitive phải dùng wrapper hoặc ignore path.

## 9. Constructor và field initializer cũng ảnh hưởng probe

Không phải mọi probe đều bắt đầu bằng giá trị default thuần của Java. Constructor hoặc field initializer có thể gán giá trị khác:

```java
public class Product {
    private int stock = 10;
    private boolean active = true;
}
```

Sau `new Product()`, probe có stock=10 và active=true. QBE có thể coi hai giá trị này là tiêu chí nếu path không bị ignore.

Builder cũng có thể thiết lập default:

```java
Product probe = Product.builder()
    .active(true)
    .build();
```

Hãy kiểm tra toàn bộ giá trị của probe trước khi tạo Example. Không chỉ tìm các field primitive không có initializer; mọi property khác null đều có thể ảnh hưởng điều kiện QBE.

## 10. Primitive trong request JSON và phân biệt field không gửi

Vấn đề tương tự xuất hiện trước khi probe được tạo. Giả sử REST request:

```java
public class ProductSearchRequest {
    private boolean active;
    private int stock;
}
```

Nếu client gửi:

```json
{
  "name": "Tea"
}
```

Sau deserialize, active thường là false và stock là 0 vì đó là default của object Java. Service có thể vô tình coi chúng là filter đã được gửi.

Dùng wrapper:

```java
public class ProductSearchRequest {
    private Boolean active;
    private Integer stock;
}
```

Khi field không xuất hiện trong JSON, chúng thường vẫn null; khi gửi false hoặc 0, giá trị được giữ nguyên. Sau đó chuyển request sang ProductFilter hoặc trực tiếp xây probe.

Không dùng giá trị false/0 như một sentinel có nghĩa “không lọc” nếu false/0 cũng là dữ liệu hợp lệ. Thiết kế API cần phân biệt rõ sự vắng mặt của filter với giá trị filter.

## 11. Không nhầm Java default, database DEFAULT và NULL

Ba khái niệm này khác nhau:

| Khái niệm | Xảy ra khi nào | Ví dụ |
|---|---|---|
| Java primitive default | Khi tạo object và không gán field | `int stock = 0` |
| SQL DEFAULT | Khi INSERT không cung cấp cột hoặc dùng từ khóa DEFAULT theo cú pháp database | `stock integer default 0` |
| SQL NULL | Giá trị không có/không xác định trong cột nullable | `stock is null` |

QBE đọc giá trị của object probe để xây dựng điều kiện WHERE. Nó không yêu cầu database áp dụng DEFAULT và cũng không tự biến primitive 0 thành NULL.

Ví dụ cột database có `DEFAULT 10` không làm một probe primitive `stock=0` trở thành 10. DEFAULT là quy tắc INSERT; probe là dữ liệu đầu vào cho truy vấn SELECT.

Tương tự, `@Column(nullable = false)` hoặc database NOT NULL chỉ mô tả constraint lưu trữ. Nó không khiến QBE bỏ qua primitive field trong probe.

## 12. QBE và giới hạn của phép so khớp

QBE hữu ích cho tìm kiếm theo thuộc tính nhưng có giới hạn:

- Các property được so khớp theo equality mặc định, ngoại trừ cấu hình string matcher.
- Không trực tiếp biểu diễn `stock >= 10`, khoảng ngày hoặc phép tính phức tạp.
- Không hỗ trợ mọi kiểu nested/grouped predicate hoặc collection matching.
- `matchingAll()` là AND giữa các điều kiện; `matchingAny()` là OR.
- Property null mặc định bị bỏ qua, trừ khi bật include null.
- Property primitive không thể biểu diễn trạng thái chưa cung cấp bằng null.

Ví dụ nếu nghiệp vụ cần tồn kho từ 10 trở lên, QBE không phải lựa chọn tự nhiên. Dùng JPQL:

```java
@Query("""
    select p
    from Product p
    where (:minimumStock is null or p.stock >= :minimumStock)
    """)
List<Product> findByMinimumStock(
    @Param("minimumStock") Integer minimumStock
);
```

Hoặc dùng Specification/Criteria API để xây dựng điều kiện động.

## 13. Khi nào dùng QBE, Specification hay @Query?

| Nhu cầu | Công cụ phù hợp |
|---|---|
| Tìm theo nhiều thuộc tính equality đơn giản | Query by Example |
| String contains/startsWith/ignoreCase | ExampleMatcher |
| Filter tùy chọn với wrapper null | QBE hoặc Specification |
| Filter theo primitive nhưng cần phân biệt 0/false với không gửi | Wrapper trong request + wrapper probe hoặc ignorePaths động |
| So sánh lớn hơn/nhỏ hơn, BETWEEN | Specification, Criteria API hoặc JPQL |
| OR/AND lồng nhau phức tạp | Specification, Criteria API, QueryDSL hoặc @Query |
| Join/report nhiều bảng | JPQL/native SQL hoặc QueryDSL |
| Query cố định, có hiệu năng cần kiểm soát | @Query JPQL/native SQL |

Không nên ép QBE xử lý mọi loại tìm kiếm. Chọn abstraction theo biểu thức nghiệp vụ thực sự cần.

## 14. Kiểm thử trường hợp primitive default

Một integration test nên xác nhận rằng probe mới không vô tình lọc theo 0/false khi các filter đó không được cung cấp.

Ví dụ với entity có wrapper fields:

```java
@DataJpaTest
class ProductExampleTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void ignoresOptionalFiltersWhenTheyAreNull() {
        repository.save(new Product("Tea", 0, false));
        repository.save(new Product("Tea", 8, true));
        repository.flush();

        Product probe = new Product();
        probe.setName("Tea");
        // stock và active không được gán nên null.

        Example<Product> example = Example.of(
            probe,
            ExampleMatcher.matching().withIgnoreNullValues()
        );

        List<Product> results = repository.findAll(example);

        assertThat(results).hasSize(2);
    }

    @Test
    void canSearchExplicitZeroAndFalse() {
        Product probe = new Product();
        probe.setName("Tea");
        probe.setStock(0);
        probe.setActive(false);

        Example<Product> example = Example.of(
            probe,
            ExampleMatcher.matching().withIgnoreNullValues()
        );

        List<Product> results = repository.findAll(example);

        assertThat(results).hasSize(1);
    }
}
```

Ví dụ giả định entity có constructor `Product(String, Integer, Boolean)`, repository mở rộng QueryByExampleExecutor và dữ liệu test được làm sạch giữa các test. Test chạy trong `@DataJpaTest`; không thể chạy độc lập chỉ bằng `javac`.

Với entity primitive, viết test riêng cho matcher động:

- Filter không gửi stock: stock nằm trong ignorePaths.
- Filter gửi stock=0: stock không nằm trong ignorePaths và query lọc đúng 0.
- Filter không gửi active: active bị ignore.
- Filter gửi active=false: active được đưa vào predicate.
- Constructor/field initializer không vô tình thêm property khác vào probe.

## 15. Checklist trước khi tạo Example

- [ ] Probe có field primitive nào không?
- [ ] Primitive nào có thể trở thành filter ngoài ý muốn do 0/false?
- [ ] Filter DTO có dùng wrapper để phân biệt không gửi với giá trị 0/false?
- [ ] Probe wrapper null có được bỏ qua theo đúng yêu cầu?
- [ ] Nếu entity giữ primitive, matcher có ignorePaths động cho property không được gửi?
- [ ] Có field initializer hoặc constructor đặt giá trị khác default không?
- [ ] Có vô tình dùng includeNullValues khiến null trở thành điều kiện IS NULL?
- [ ] String matcher có đúng exact/contains/startsWith và ignoreCase?
- [ ] Nhu cầu range/join phức tạp có vượt khả năng QBE?
- [ ] Integration test đã kiểm tra 0, false, null và filter không gửi?
- [ ] Không nhầm Java default với SQL DEFAULT hoặc SQL NULL?

## 16. Kết luận

QBE xây dựng điều kiện từ giá trị hiện tại trong probe. Null thường bị bỏ qua, nhưng primitive không thể null: `int` bắt đầu bằng 0, `boolean` bắt đầu bằng false, nên các giá trị đó có thể trở thành predicate ngoài ý muốn.

Với tiêu chí tìm kiếm tùy chọn, ưu tiên wrapper như `Integer` và `Boolean` trong probe/request DTO để null biểu diễn “không lọc”, còn 0/false vẫn là giá trị hợp lệ. Nếu entity phải giữ primitive, dùng `ExampleMatcher.withIgnorePaths` được xây dựng động dựa trên việc filter có được gửi hay không. `withIgnoreNullValues()` không loại bỏ primitive default.

Cuối cùng, kiểm tra giá trị probe trước khi tạo Example và viết integration test cho các trường hợp không gửi, 0, false và null. Nếu truy vấn cần range hoặc logic phức tạp, chuyển sang Specification/Criteria API hoặc JPQL thay vì cố mở rộng QBE quá khả năng của nó.
