# Tìm chuỗi bằng Like, Containing, StartingWith và EndingWith

## 1. Truy vấn chuỗi trong Spring Data JPA

Ứng dụng thường cần tìm dữ liệu theo một phần của chuỗi: tìm khách hàng theo một phần tên, tìm sản phẩm theo tiền tố mã hoặc lọc email theo domain. Spring Data JPA hỗ trợ các toán tử LIKE thông qua tên phương thức repository, đồng thời cho phép viết JPQL bằng @Query khi cần kiểm soát truy vấn chi tiết hơn.

Bốn từ khóa cần phân biệt:

- Like: dùng pattern LIKE do caller cung cấp, bao gồm ký tự đại diện nếu cần.
- Containing: tìm chuỗi con, tự thêm ký tự đại diện ở cả hai đầu.
- StartingWith: tìm giá trị bắt đầu bằng chuỗi đầu vào, tự thêm ký tự đại diện ở cuối.
- EndingWith: tìm giá trị kết thúc bằng chuỗi đầu vào, tự thêm ký tự đại diện ở đầu.

Các từ khóa này đều được chuyển thành biểu thức LIKE trong truy vấn. Chúng không phải bốn thuật toán tìm kiếm khác nhau; điểm khác biệt chính là cách Spring Data tạo pattern từ tham số đầu vào.

## 2. Hiểu ký tự đại diện của SQL LIKE

Trong SQL, LIKE thường dùng hai ký tự đại diện:

| Ký tự | Ý nghĩa | Ví dụ |
|---|---|---|
| % | Khớp với không hoặc nhiều ký tự bất kỳ | 'An%' khớp An, Anh, An Nguyen |
| _ | Khớp với đúng một ký tự bất kỳ | 'A_n' khớp Ann, A-n |

Ví dụ:

```sql
select *
from customer
where name like 'An%';
```

Truy vấn này tìm tên bắt đầu bằng An. Nếu dùng:

```sql
select *
from customer
where name like '%An%';
```

thì chuỗi An có thể xuất hiện ở bất kỳ vị trí nào. Còn:

```sql
select *
from customer
where name like '%An';
```

tìm tên kết thúc bằng An.

LIKE phân biệt chữ hoa/chữ thường hay không phụ thuộc collation, kiểu dữ liệu và cấu hình database. Không nên suy luận rằng LIKE luôn case-sensitive trên mọi hệ quản trị.

## 3. Dùng các từ khóa trong tên phương thức repository

Giả sử có entity:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Repository:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<Customer> findByNameLike(String pattern);

    List<Customer> findByNameContaining(String fragment);

    List<Customer> findByNameStartingWith(String prefix);

    List<Customer> findByNameEndingWith(String suffix);

    List<Customer> findByNameContainingIgnoreCase(String fragment);
}
```

Spring Data phân tích tên method, xác định property name và toán tử tương ứng, sau đó tạo query. Property name trong method là tên thuộc tính Java của entity, không nhất thiết là tên cột database.

### 3.1. Like: caller cung cấp pattern

Method:

```java
List<Customer> findByNameLike(String pattern);
```

tham số được dùng như pattern LIKE. Caller cần tự cung cấp wildcard:

```java
repository.findByNameLike("An%");
repository.findByNameLike("%An%");
repository.findByNameLike("%An");
```

Ý nghĩa lần lượt là bắt đầu bằng An, chứa An và kết thúc bằng An.

Nếu truyền "An" mà không có wildcard, truy vấn LIKE tương đương so khớp chính xác chuỗi An. Like không tự biến mọi tham số thành tìm kiếm chuỗi con.

Vì caller tự điều khiển pattern, cần phân biệt nhu cầu tìm literal text với nhu cầu cho phép người dùng nhập wildcard. Không nối trực tiếp input vào chuỗi JPQL hoặc SQL; hãy truyền qua parameter binding.

### 3.2. Containing: tìm chuỗi con ở bất kỳ vị trí nào

Method:

```java
List<Customer> findByNameContaining(String fragment);
```

Spring Data tự thêm wildcard ở hai phía của tham số. Về ý nghĩa, truy vấn tương đương:

```sql
where name like '%<fragment>%'
```

Ví dụ:

```java
List<Customer> results =
    repository.findByNameContaining("ng");
```

có thể tìm Nguyen, Hoang, Dang hoặc các tên khác có chứa chuỗi ng, tùy dữ liệu và collation.

Containing có các biến thể alias như Contains và IsContaining trong query derivation. Trong code mới, nên chọn một cách viết nhất quán trong repository.

### 3.3. StartingWith: tìm theo tiền tố

Method:

```java
List<Customer> findByNameStartingWith(String prefix);
```

Spring Data thêm wildcard ở cuối tham số. Về ý nghĩa:

```sql
where name like '<prefix>%'
```

Ví dụ tìm các tên bắt đầu bằng An:

```java
List<Customer> results =
    repository.findByNameStartingWith("An");
```

Kết quả có thể gồm An, Anh, An Nguyen và các tên bắt đầu bằng An. Đây là lựa chọn phù hợp cho chức năng gợi ý theo tiền tố, tìm mã bắt đầu bằng một chuỗi hoặc lọc tên theo phần đầu.

### 3.4. EndingWith: tìm theo hậu tố

Method:

```java
List<Customer> findByNameEndingWith(String suffix);
```

Spring Data thêm wildcard ở đầu tham số. Về ý nghĩa:

```sql
where name like '%<suffix>'
```

Ví dụ tìm email kết thúc bằng một domain:

```java
List<Customer> findByEmailEndingWith("@example.com");
```

Trong ví dụ thực tế, repository cần có thuộc tính email tương ứng. EndingWith cũng hữu ích với mã có hậu tố hoặc định danh theo quy ước, nhưng thường khó tận dụng B-tree index thông thường hơn tìm theo tiền tố.

## 4. So sánh bốn từ khóa

| Method keyword | Pattern tương đương | Vị trí khớp |
|---|---|---|
| Like | Pattern do caller truyền | Caller quyết định |
| Containing | %value% | Bất kỳ vị trí |
| StartingWith | value% | Đầu chuỗi |
| EndingWith | %value | Cuối chuỗi |

Ví dụ cùng truyền chuỗi An:

| Method | Pattern về ý nghĩa | Ví dụ khớp |
|---|---|---|
| findByNameLike("An") | An | An |
| findByNameLike("An%") | An% | Anh, An Nguyen |
| findByNameContaining("An") | %An% | Lan, An Nguyen |
| findByNameStartingWith("An") | An% | Anh, An Nguyen |
| findByNameEndingWith("An") | %An | Hoang An |

Các pattern trên mô tả ngữ nghĩa LIKE. SQL thực tế và cách bind parameter do Spring Data JPA/provider thực hiện; không cần tự ghép wildcard vào tên method.

## 5. Tìm kiếm không phân biệt hoa thường

### 5.1. Dùng IgnoreCase

Spring Data JPA hỗ trợ IgnoreCase trong derived query:

```java
List<Customer> findByNameContainingIgnoreCase(String fragment);

List<Customer> findByNameStartingWithIgnoreCase(String prefix);

List<Customer> findByNameEndingWithIgnoreCase(String suffix);
```

Với IgnoreCase, Spring Data tạo biểu thức so sánh không phân biệt hoa thường, thường dựa trên việc áp dụng UPPER cho biểu thức thuộc tính và tham số. Ví dụ về ý nghĩa SQL:

```sql
where upper(name) like upper(?)
```

Nếu gọi:

```java
repository.findByNameContainingIgnoreCase("AN");
```

thì An, AN, an hoặc Nguyen An có thể được khớp theo cách xử lý case của database.

### 5.2. IgnoreCase không đồng nghĩa với không phân biệt dấu

IgnoreCase xử lý khác biệt chữ hoa/chữ thường. Nó không tự bảo đảm các ký tự có dấu và không dấu được coi là tương đương. Ví dụ, việc "a" có khớp "á" hay không phụ thuộc collation, kiểu dữ liệu, chuẩn hóa Unicode và chức năng database.

Nếu sản phẩm cần tìm kiếm không phân biệt dấu tiếng Việt, cần thiết kế rõ:
- Collation phù hợp của database.
- Hàm normalize/loại dấu ở thời điểm ghi và tìm kiếm.
- Cột tìm kiếm đã chuẩn hóa.
- Extension hoặc full-text search phù hợp nếu cần.

Không tự loại dấu trong Java cho một phía mà không chuẩn hóa dữ liệu lưu trữ tương ứng; hai phía phải dùng cùng quy tắc.

### 5.3. Tác động của UPPER/LOWER tới index

Khi query áp dụng UPPER(name), B-tree index thông thường trên name có thể không được dùng như mong đợi. Tùy database, có thể cần functional index trên UPPER(name), collation case-insensitive hoặc một cột normalized riêng.

Hãy xem execution plan trên database thật. IgnoreCase thuận tiện về cú pháp, nhưng không tự bảo đảm hiệu năng.

## 6. Wildcard trong dữ liệu đầu vào và escaping

### 6.1. Vì sao % và _ có thể làm thay đổi kết quả?

Giả sử người dùng muốn tìm đúng chuỗi "50%". Nếu pattern được tạo thành %50%%, ký tự % trong dữ liệu đầu vào lại bị hiểu là wildcard. Kết quả có thể khớp nhiều chuỗi không chứa ký tự phần trăm thực tế.

Tương tự, dấu gạch dưới _ đại diện cho đúng một ký tự. Nếu không escape, input "A_B" có thể khớp cả "A1B".

Cần phân biệt:
- Wildcard do ứng dụng chủ động cung cấp.
- Wildcard do người dùng nhập như một phần literal text.

### 6.2. Derived Containing/StartingWith/EndingWith có escaping

Spring Data có cơ chế escape các ký tự wildcard đặc biệt trong tham số của derived query dùng Containing, StartingWith và EndingWith, để wildcard người dùng nhập được hiểu như ký tự literal thay vì mở rộng pattern. Escape character mặc định và cách cấu hình phụ thuộc Spring Data JPA; có thể cấu hình qua escapeCharacter trên @EnableJpaRepositories.

Vì vậy, khi dùng derived keyword, không cần tự thêm wildcard vào input. Ví dụ:

```java
repository.findByNameContaining("50%");
```

được hiểu là tìm chuỗi chứa literal 50%, thay vì để dấu % do người dùng nhập mở rộng thành wildcard.

### 6.3. Like là pattern tường minh

Với Like, caller đang cung cấp pattern, vì vậy phải chủ động quyết định wildcard nào được phép. Nếu muốn tìm literal text do người dùng nhập, cần escape % và _ theo escape character và thêm ESCAPE clause phù hợp.

Ví dụ JPQL dùng dấu ! làm escape character:

```java
@Query("""
    select c
    from Customer c
    where c.name like :pattern escape '!'
    """)
List<Customer> searchByPattern(
    @Param("pattern") String pattern
);
```

Với ví dụ này, caller phải chuẩn bị pattern theo quy ước escape !. Để tìm literal 50%, pattern cần biểu diễn dấu % bằng !% và vẫn thêm wildcard bao ngoài nếu muốn tìm chuỗi con. Cú pháp escape của database và provider cần được kiểm thử.

### 6.4. Dùng SpEL escape trong @Query của Spring Data

Spring Data JPA cung cấp helper escape() và escapeCharacter() cho query có wildcard do framework thêm:

```java
@Query("""
    select c
    from Customer c
    where c.name like %?#{escape([0])}%
          escape ?#{escapeCharacter()}
    """)
List<Customer> findContainingLiteral(String fragment);
```

escape() escape các ký tự SQL LIKE chuẩn là % và _. escapeCharacter() trả về ký tự escape được cấu hình cho repository. Helper này hữu ích khi tự viết @Query nhưng vẫn muốn tìm chuỗi con literal.

Helper escape chỉ xử lý các ký tự wildcard LIKE chuẩn được Spring Data hỗ trợ; nó không thay thế việc kiểm tra các quy tắc wildcard đặc thù của database.

## 7. Null, chuỗi rỗng và input người dùng

### 7.1. Null không có nghĩa là bỏ điều kiện

Nếu truyền null cho một điều kiện LIKE, phép so sánh SQL thường tạo ra UNKNOWN và không trả về hàng nào. Không nên kỳ vọng:

```java
repository.findByNameContaining(null);
```

sẽ trả toàn bộ customer.

Nếu filter là tùy chọn, hãy chỉ thêm predicate khi người dùng thực sự nhập giá trị. Có thể dùng Specification, Querydsl hoặc xây dựng query có điều kiện ở service.

### 7.2. Chuỗi rỗng có thể trở thành pattern khớp rộng

Với Containing, chuỗi rỗng có thể tạo pattern tương đương %% và khớp mọi giá trị name khác null. Với StartingWith hoặc EndingWith, pattern tương đương % cũng có thể khớp mọi chuỗi khác null.

Điều này dễ gây truy vấn rất rộng nếu form tìm kiếm gửi chuỗi rỗng. Hãy chuẩn hóa input:
- trim khoảng trắng đầu/cuối nếu nghiệp vụ cho phép.
- Từ chối hoặc bỏ qua filter rỗng theo quy tắc API.
- Giới hạn độ dài tìm kiếm.
- Kết hợp Pageable hoặc giới hạn kết quả.
- Không chạy tìm kiếm contains toàn bảng khi chưa có điều kiện đủ chọn lọc.

### 7.3. Khoảng trắng và Unicode

Containing tìm chuỗi con theo quy tắc so sánh của database. Khoảng trắng, dấu tiếng Việt, Unicode normalization và collation có thể ảnh hưởng kết quả.

Hai chuỗi hiển thị giống nhau có thể có cách mã hóa Unicode khác nhau. Nếu yêu cầu tìm kiếm đa ngôn ngữ nghiêm ngặt, cần thống nhất chuẩn hóa dữ liệu ở cả lúc ghi và lúc tìm kiếm, đồng thời kiểm tra collation trên database thực tế.

## 8. Dùng @Query khi cần kiểm soát điều kiện

Derived query dễ đọc với một số predicate đơn giản. Khi điều kiện phức tạp hơn, @Query giúp biểu đạt JPQL tường minh:

```java
@Query("""
    select c
    from Customer c
    where c.name like concat('%', :term, '%')
    order by c.name
    """)
List<Customer> searchByName(
    @Param("term") String term
);
```

Cách này truyền parameter an toàn, nhưng nếu term chứa % hoặc _, các ký tự đó vẫn có thể mang ý nghĩa wildcard. Nếu muốn literal substring, dùng escaping như phần trước hoặc derived Containing.

Nếu cần kết hợp nhiều điều kiện tùy chọn, có thể dùng Specification:

```java
public static Specification<Customer> nameContains(String term) {
    return (root, query, cb) -> {
        if (term == null || term.isBlank()) {
            return cb.conjunction();
        }

        return cb.like(
            cb.lower(root.get("name")),
            "%" + term.toLowerCase(Locale.ROOT) + "%"
        );
    };
}
```

Đây là ví dụ minh họa: nó xử lý filter null/rỗng nhưng chưa escape % và _. Nếu term là input literal từ người dùng, cần escape ký tự wildcard và chỉ định escape character cho Criteria predicate. Locale.ROOT giúp chuẩn hóa chữ thường phía Java nhất quán hơn với locale mặc định, nhưng vẫn cần đối chiếu quy tắc collation/Unicode của database.

Không nối input vào chuỗi JPQL hoặc SQL. Dùng parameter binding hoặc Criteria API để tránh lỗi cú pháp và SQL injection.

## 9. Hiệu năng của từng kiểu LIKE

### 9.1. StartingWith thường thân thiện hơn với B-tree index

Pattern dạng value% có tiền tố cố định. Nhiều database có thể sử dụng B-tree index cho truy vấn prefix, tùy collation, operator class và execution plan.

```sql
select id, name
from customer
where name like 'Ng%';
```

Nếu đây là truy vấn thường xuyên, có thể tạo index trên name và kiểm tra execution plan.

### 9.2. Containing thường khó dùng B-tree index

Pattern %value% không có tiền tố cố định. B-tree index thông thường thường không thể tìm một range liên tục hiệu quả, dẫn tới scan nhiều hàng.

```sql
select id, name
from customer
where name like '%ng%';
```

Với PostgreSQL, extension pg_trgm và GIN/GiST index có thể hỗ trợ một số truy vấn substring/LIKE. Các database khác có full-text, n-gram hoặc giải pháp search riêng. Hãy chọn công nghệ theo database và yêu cầu tìm kiếm, không mặc định một B-tree index sẽ giải quyết được contains search.

### 9.3. EndingWith cũng thường khó dùng B-tree index thông thường

Pattern %value không có prefix cố định nên cũng thường phải scan. Nếu truy vấn suffix là yêu cầu quan trọng, có thể lưu thêm cột đảo chuỗi và index cột đó, hoặc dùng giải pháp search chuyên biệt. Cách này tăng chi phí ghi và cần duy trì dữ liệu normalized/reversed nhất quán.

### 9.4. IgnoreCase và function index

Nếu query áp dụng UPPER(name), index thường trên name có thể không được sử dụng. Một functional index phù hợp có thể giúp, ví dụ trên database hỗ trợ:

```sql
create index idx_customer_name_upper
on customer (upper(name));
```

Cú pháp và hiệu quả phụ thuộc database. Nếu dùng collation case-insensitive, có thể có chiến lược khác. Luôn kiểm tra execution plan với dữ liệu có kích thước gần production.

## 10. Phân trang và giới hạn kết quả

Không nên trả hàng chục nghìn kết quả contains search vào một List. Dùng Pageable:

```java
Page<Customer> searchByNameContainingIgnoreCase(
    String fragment,
    Pageable pageable
);
```

Có thể gọi:

```java
Pageable page = PageRequest.of(
    0,
    20,
    Sort.by("name").ascending()
);

Page<Customer> result =
    repository.searchByNameContainingIgnoreCase("an", page);
```

Page thường cần thêm truy vấn COUNT để tính tổng số phần tử; với contains search trên bảng lớn, COUNT cũng có thể tốn kém. Nếu chỉ cần tải thêm dữ liệu tới khi hết, cân nhắc Slice để tránh yêu cầu tổng số hàng. Có thể dùng limit như Top/First khi chỉ cần một số lượng nhỏ.

Pageable giúp giới hạn dữ liệu trả về, nhưng không làm một truy vấn LIKE không có index trở nên rẻ. Cần tối ưu pattern, index hoặc công nghệ tìm kiếm trước khi tăng page size.

## 11. Ví dụ repository hoàn chỉnh

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<Customer> findByNameLike(String pattern);

    List<Customer> findByNameContaining(String fragment);

    List<Customer> findByNameStartingWith(String prefix);

    List<Customer> findByNameEndingWith(String suffix);

    List<Customer> findByNameContainingIgnoreCase(String fragment);

    Page<Customer> searchByNameContainingIgnoreCase(
        String fragment,
        Pageable pageable
    );

    List<Customer> findTop20ByNameStartingWithIgnoreCaseOrderByNameAsc(
        String prefix
    );
}
```

Ví dụ cách gọi:

```java
repository.findByNameLike("Ng%");
repository.findByNameContaining("ng");
repository.findByNameStartingWith("Ng");
repository.findByNameEndingWith("son");
repository.findByNameContainingIgnoreCase("NG");
```

Mỗi method thể hiện một ý định tìm kiếm cụ thể. Không nên đặt method name quá dài nếu Specification hoặc @Query sẽ làm điều kiện dễ đọc và dễ kiểm thử hơn.

## 12. Kiểm thử hành vi LIKE

Một test repository nên bao phủ:
- Chuỗi khớp ở đầu, giữa và cuối.
- Chuỗi không khớp.
- Phân biệt hoa thường và IgnoreCase.
- Ký tự % và _ do người dùng nhập.
- Input null và rỗng.
- Dữ liệu có dấu tiếng Việt.
- Pagination, sorting và giới hạn kết quả.

Ví dụ test:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsByDifferentStringPatterns() {
        repository.saveAll(List.of(
            new Customer("Nguyen An"),
            new Customer("Tran Binh"),
            new Customer("An Nguyen"),
            new Customer("Lan")
        ));

        assertThat(repository.findByNameStartingWith("Ng"))
            .extracting(Customer::getName)
            .containsExactly("Nguyen An");

        assertThat(repository.findByNameEndingWith("Nguyen"))
            .extracting(Customer::getName)
            .containsExactly("An Nguyen");

        assertThat(repository.findByNameContainingIgnoreCase("AN"))
            .extracting(Customer::getName)
            .contains("Nguyen An", "An Nguyen", "Tran Binh");
    }
}
```

Test này giả định database test và entity/repository tương ứng đã được cấu hình. Thứ tự kết quả của query không có ORDER BY là không được bảo đảm; nếu cần assert thứ tự, khai báo sort trong query hoặc Pageable. Với IgnoreCase, kết quả phụ thuộc dữ liệu test và cách database so sánh chuỗi.

Để kiểm tra escaping và collation sát production, chạy integration test trên cùng loại database. H2 có thể có hành vi khác database production về LIKE, collation, Unicode và index.

## 13. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng Like nhưng không thêm wildcard | Like dùng pattern caller truyền | Truyền % ở vị trí mong muốn hoặc dùng Containing/StartingWith/EndingWith |
| Dùng Containing cho tìm kiếm prefix | Pattern có wildcard ở cả hai đầu | Dùng StartingWith nếu chỉ cần tiền tố |
| Input chứa % hoặc _ tạo kết quả quá rộng | Ký tự được hiểu là wildcard | Dùng derived keyword có escaping hoặc escape thủ công trong @Query |
| Null trả về rỗng | LIKE với NULL không tạo kết quả TRUE | Chỉ thêm predicate khi có input |
| Chuỗi rỗng trả về quá nhiều hàng | Pattern trở thành %% hoặc % | Validate, trim và bỏ qua/từ chối input rỗng |
| IgnoreCase chậm | UPPER/LOWER làm index thường không phù hợp | Functional index, collation hoặc cột chuẩn hóa |
| Contains chậm trên bảng lớn | %term% thường không dùng B-tree hiệu quả | Trigram, full-text hoặc search index phù hợp |
| Tìm không dấu không hoạt động | IgnoreCase không đồng nghĩa accent-insensitive | Thiết kế collation/normalization riêng |
| Kết quả phân trang tốn kém | COUNT query và scan LIKE lớn | Slice, giới hạn kết quả, index hoặc search engine |

## 14. Checklist chọn phương thức

- [ ] Tìm chính xác hay tìm chuỗi con?
- [ ] Cần prefix, suffix hay bất kỳ vị trí?
- [ ] Caller có được phép cung cấp wildcard không?
- [ ] Input % và _ cần được hiểu literal hay wildcard?
- [ ] Có cần IgnoreCase không?
- [ ] Có yêu cầu không phân biệt dấu tiếng Việt không?
- [ ] Input null/rỗng được xử lý theo quy tắc API chưa?
- [ ] Truy vấn có giới hạn kết quả hoặc phân trang chưa?
- [ ] B-tree index có phù hợp pattern không?
- [ ] Đã kiểm tra execution plan trên database thật chưa?
- [ ] Đã test escaping, Unicode và collation chưa?

## 15. Kết luận

Like dành cho pattern do caller kiểm soát. Containing tìm chuỗi con ở mọi vị trí, StartingWith tìm prefix và EndingWith tìm suffix; ba từ khóa sau tự tạo wildcard tương ứng và Spring Data xử lý escaping cho wildcard đặc biệt trong đối số derived query.

IgnoreCase giúp so sánh không phân biệt hoa thường, nhưng không tự xử lý dấu tiếng Việt hoặc bảo đảm hiệu năng. Pattern %term% thường khó tận dụng B-tree index; prefix term% thường có cơ hội dùng index tốt hơn. Với truy vấn lớn, hãy kiểm tra collation, index và execution plan, giới hạn kết quả và cân nhắc công nghệ search phù hợp.

Chọn keyword theo đúng ý định nghiệp vụ, xử lý null/rỗng và wildcard rõ ràng, dùng parameter binding an toàn, rồi kiểm thử trên database thực tế.