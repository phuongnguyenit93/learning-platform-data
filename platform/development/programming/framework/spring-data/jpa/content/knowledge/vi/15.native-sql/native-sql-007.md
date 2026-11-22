# Sắp xếp động, bộ phân tích truy vấn và giới hạn theo phiên bản

Spring Data JPA cho phép quyết định thứ tự kết quả tại thời điểm gọi repository bằng Sort hoặc Pageable. Cách này hữu ích khi màn hình cho phép người dùng chọn sắp xếp theo ngày tạo, số tiền, trạng thái hoặc nhiều cột cùng lúc. Tuy nhiên, Sort không nhận mọi chuỗi tùy ý: thuộc tính sắp xếp phải hợp lệ với entity hoặc alias của truy vấn. Với biểu thức hàm và native SQL, Spring Data còn phải phân tích hoặc viết lại câu query để chèn ORDER BY và tạo count query. Khả năng đó phụ thuộc cấu trúc truy vấn, parser có trên classpath và phiên bản Spring Data JPA.

Bài học dùng ví dụ PurchaseOrder để trình bày Sort, Sort.Order, Pageable, alias, JpaSort.unsafe, bảo vệ đầu vào từ API, khác biệt giữa parser của derived query và query enhancer, lựa chọn regex/JSqlParser cho native query, countQuery, QueryRewriter và các giới hạn cần kiểm tra khi nâng cấp phiên bản.

## 1. Sắp xếp tĩnh và sắp xếp động

Sắp xếp tĩnh được định nghĩa ngay trong tên phương thức:

~~~java
List<PurchaseOrder> findByStatusOrderByCreatedAtDesc(
    OrderStatus status
);
~~~

Method này luôn sắp xếp createdAt giảm dần. Người gọi không thể chọn cột hoặc chiều sắp xếp khác.

Sắp xếp động nhận Sort làm tham số:

~~~java
List<PurchaseOrder> findByStatus(
    OrderStatus status,
    Sort sort
);
~~~

Người gọi có thể chọn thứ tự khi chạy:

~~~java
repository.findByStatus(
    OrderStatus.PAID,
    Sort.by(Sort.Direction.DESC, "createdAt")
);
~~~

Sắp xếp động phù hợp với bảng dữ liệu có nhiều lựa chọn sắp xếp. Câu query và điều kiện lọc vẫn được xác định bởi repository; Sort bổ sung phần ORDER BY cho lần gọi cụ thể.

Hai khái niệm cần phân biệt:

- **OrderBy trong tên method**: thứ tự cố định, được khai báo trong method name.
- **Sort**: thứ tự được truyền vào lúc gọi repository.

Nếu thứ tự luôn cố định và đơn giản, OrderBy dễ đọc. Nếu thứ tự phụ thuộc yêu cầu người dùng hoặc từng use case, dùng Sort.

## 2. Tạo Sort với một hoặc nhiều tiêu chí

Spring Data cung cấp Sort và Sort.Order:

~~~java
Sort newestFirst = Sort.by(
    Sort.Order.desc("createdAt")
);

Sort byAmountThenDate = Sort.by(
    Sort.Order.desc("total"),
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("id")
);

Sort ascending = Sort.by(
    Sort.Direction.ASC,
    "customerName"
);

Sort noSorting = Sort.unsorted();
~~~

Mỗi Order mô tả một thuộc tính và hướng sắp xếp:

- **asc(property)**: tăng dần.
- **desc(property)**: giảm dần.
- **ignoreCase()**: yêu cầu so sánh không phân biệt hoa thường cho thuộc tính chuỗi.
- **nullsFirst()**: gợi ý đưa giá trị null lên trước.
- **nullsLast()**: gợi ý đưa giá trị null xuống sau.
- **nullsNative()**: để database/provider xử lý theo mặc định.

Thứ tự khai báo Order có ý nghĩa. Trong ví dụ byAmountThenDate, database sắp xếp total trước; nếu total bằng nhau thì so sánh createdAt; nếu vẫn bằng nhau thì so sánh id.

Nên thêm khóa duy nhất làm tiêu chí cuối để tạo thứ tự ổn định. Nếu chỉ sắp xếp theo createdAt, nhiều bản ghi có thể cùng timestamp và thứ tự tương đối giữa chúng không được bảo đảm. Thứ tự ổn định đặc biệt quan trọng khi phân trang.

## 3. Sort.Order và xử lý chuỗi, NULL

Ví dụ:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("customerName").ignoreCase().nullsLast(),
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("id")
);
~~~

**ignoreCase()** hữu ích với tên hoặc mã dạng chuỗi. Không áp dụng nó tùy tiện cho số, ngày hoặc kiểu không phải String.

Các phương thức nullsFirst(), nullsLast() và nullsNative() biểu diễn mong muốn về vị trí của NULL. Đây là hướng dẫn cho tầng truy vấn; cách dịch thành SQL và khả năng hỗ trợ còn tùy JPA provider, database và dialect. Hãy kiểm tra kết quả trên hệ quản trị đang dùng, đặc biệt nếu ứng dụng phải chạy trên nhiều database.

Nếu yêu cầu nghiệp vụ bắt buộc thứ tự NULL giống nhau ở mọi môi trường, có thể viết biểu thức CASE trong JPQL hoặc native SQL để quy định rõ. Khi đó cần kiểm tra việc parser chèn Sort động và dùng biểu thức đã được kiểm soát.

## 4. Nhận Sort trực tiếp trong repository

Ví dụ entity đơn giản:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal total;

    protected PurchaseOrder() {
    }

    // Constructor và getter được lược bỏ trong ví dụ repository.
}
~~~

Repository:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(
        OrderStatus status,
        Sort sort
    );

    List<PurchaseOrder> findByCustomer_Id(
        Long customerId,
        Sort sort
    );
}
~~~

Cách gọi:

~~~java
List<PurchaseOrder> orders = repository.findByStatus(
    OrderStatus.PAID,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

Sort property dùng tên thuộc tính Java của entity, không phải tên cột SQL. Nếu field createdAt được ánh xạ bằng @Column(name = "created_at"), Sort vẫn dùng createdAt.

Với đường dẫn lồng nhau, có thể dùng property path như customer.name nếu đó là đường dẫn hợp lệ theo mapping. Việc sắp xếp qua quan hệ có thể khiến query cần JOIN. Hãy xem SQL được sinh và tránh sắp xếp theo collection-valued path khi ý nghĩa thứ tự không rõ ràng.

## 5. Kết hợp Sort với Pageable

Khi cần vừa sắp xếp vừa phân trang, truyền Pageable:

~~~java
Page<PurchaseOrder> findByStatus(
    OrderStatus status,
    Pageable pageable
);
~~~

Tạo Pageable:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Pageable pageable = PageRequest.of(
    0,
    20,
    sort
);

Page<PurchaseOrder> page =
    repository.findByStatus(OrderStatus.PAID, pageable);
~~~

PageRequest.of(page, size, sort) dùng chỉ số trang bắt đầu từ 0. Trong ví dụ, page 0 và size 20 nghĩa là yêu cầu trang đầu với tối đa 20 kết quả.

Page cung cấp:

- getContent(): danh sách phần tử của trang hiện tại.
- getNumber(): số trang hiện tại.
- getSize(): kích thước trang yêu cầu.
- getTotalElements(): tổng số phần tử theo count query.
- getTotalPages(): tổng số trang.
- hasNext() và hasPrevious(): kiểm tra trang kế tiếp/trước đó.

Nếu không cần tổng số phần tử và tổng số trang, dùng Slice<T> có thể tránh count query. Slice vẫn hỗ trợ Pageable và Sort, nhưng chỉ tập trung vào việc có trang tiếp theo hay không.

Không nhận page size không giới hạn từ client. Hãy kiểm tra page index, giới hạn kích thước trang tối đa và các thuộc tính sắp xếp được phép.

## 6. Sort với @Query JPQL

Sort cũng có thể truyền vào method dùng @Query:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o
        from PurchaseOrder o
        where o.status = :status
        """)
    List<PurchaseOrder> searchByStatus(
        @Param("status") OrderStatus status,
        Sort sort
    );
}
~~~

Spring Data bổ sung phần ORDER BY tương ứng với Sort vào truy vấn khai báo.

Thuộc tính được dùng trong Sort phải tham chiếu được trong truy vấn: thông thường là property path của entity hoặc alias được khai báo trong SELECT. Một biểu thức không thể tham chiếu hợp lệ sẽ dẫn đến lỗi.

Ví dụ hợp lệ:

~~~java
repository.searchByStatus(
    OrderStatus.PAID,
    Sort.by(Sort.Order.desc("createdAt"))
);
~~~

JPQL sử dụng tên entity và thuộc tính Java. Không viết tên bảng purchase_orders hoặc cột created_at trong JPQL Sort nếu entity property tương ứng là createdAt.

Nếu truy vấn dùng alias trong projection, có thể sắp xếp theo alias đó như phần tiếp theo.

## 7. Sắp xếp theo alias của projection

Giả sử truy vấn trả về ID và độ dài mã đơn hàng:

~~~java
@Query("""
    select o.id as orderId,
           length(o.reference) as referenceLength
    from PurchaseOrder o
    where o.status = :status
    """)
List<Object[]> findOrderMetrics(
    @Param("status") OrderStatus status,
    Sort sort
);
~~~

Có thể sắp xếp theo alias referenceLength:

~~~java
List<Object[]> rows = repository.findOrderMetrics(
    OrderStatus.PAID,
    Sort.by(Sort.Order.desc("referenceLength"))
);
~~~

Alias là một tên có thể tham chiếu trong phần ORDER BY theo truy vấn phù hợp. Nếu dùng DTO projection, hãy xác định alias hoặc constructor expression tương thích với kiểu kết quả.

DISTINCT, GROUP BY và projection nhiều cột có thể làm ngữ nghĩa sắp xếp phức tạp hơn. Ví dụ, khi query chọn giá trị tổng hợp, chỉ sắp xếp theo alias có trong SELECT hoặc biểu thức được JPQL cho phép. Kiểm thử query trên provider thật thay vì giả định mọi alias đều được parser xử lý giống nhau.

## 8. Biểu thức hàm và JpaSort.unsafe

Sort thông thường được kiểm tra để bảo đảm thuộc tính sắp xếp có thể tham chiếu hợp lệ. Biểu thức hàm như LENGTH(o.reference) không phải property path đơn giản:

~~~java
// Không dùng Sort.by với biểu thức hàm tùy ý:
Sort.by("LENGTH(reference)");
~~~

Với string-based query phù hợp, Spring Data JPA cung cấp JpaSort.unsafe:

~~~java
List<PurchaseOrder> orders = repository.searchByStatus(
    OrderStatus.PAID,
    JpaSort.unsafe("LENGTH(o.reference)")
);
~~~

JpaSort.unsafe cho phép đưa biểu thức vào phần ORDER BY mà không qua kiểm tra property path thông thường. Đây là API có chủ đích và cần được dùng cẩn trọng.

Không bao giờ truyền trực tiếp chuỗi sort do người dùng gửi lên vào JpaSort.unsafe. Tên cột, hàm, toán tử và hướng sắp xếp là cấu trúc query, không phải giá trị bind parameter. Hãy chỉ chọn từ danh sách biểu thức cố định đã được lập trình viên kiểm tra.

Nếu có thể, ưu tiên alias đã khai báo trong SELECT:

~~~java
Sort.by("referenceLength");
~~~

Cách dùng alias dễ đọc và an toàn hơn so với ghép biểu thức tùy ý vào query.

JpaSort.unsafe không phải công cụ để biến mọi SQL/JPQL thành hợp lệ. Biểu thức vẫn phải được JPA provider hoặc query context hỗ trợ. Một số đường xử lý dựa trên Criteria API có giới hạn đối với biểu thức như subquery, TREAT hoặc CAST; hãy kiểm tra tài liệu của phiên bản đang sử dụng.

## 9. Bảo vệ Sort nhận từ API

Một lỗi bảo mật thường gặp là lấy trực tiếp tham số sort của HTTP request rồi tạo Sort hoặc JpaSort.unsafe từ chuỗi đó.

Ví dụ request:

~~~text
GET /orders?sort=createdAt,desc
~~~

Không nên coi tên property bất kỳ do client gửi là đáng tin. Hãy ánh xạ tên công khai sang property được cho phép:

~~~java
private static final Map<String, String> ALLOWED_SORTS = Map.of(
    "newest", "createdAt",
    "amount", "total",
    "status", "status"
);

public Sort resolveSort(String requestedField, String requestedDirection) {
    String property = ALLOWED_SORTS.get(requestedField);

    if (property == null) {
        throw new IllegalArgumentException("Unsupported sort field");
    }

    Sort.Direction direction =
        "asc".equalsIgnoreCase(requestedDirection)
            ? Sort.Direction.ASC
            : Sort.Direction.DESC;

    return Sort.by(new Sort.Order(direction, property));
}
~~~

Đoạn code minh họa cách whitelist field; trong ứng dụng thật cần quyết định rõ xử lý direction không hợp lệ, trường hợp null, nhiều sort criteria và phản hồi HTTP tương ứng.

Nguyên tắc:

- Whitelist các trường được phép sắp xếp.
- Không ghép raw input vào JPQL hoặc SQL.
- Không dùng JpaSort.unsafe với đầu vào chưa kiểm soát.
- Giới hạn số lượng tiêu chí sort.
- Xác định rõ tên sort công khai và tên property nội bộ.
- Không cho phép sắp xếp theo field bí mật hoặc dữ liệu không được phép tiết lộ.

## 10. Bộ phân tích tên method và bộ phân tích query là hai việc khác nhau

Khi nói về parser trong Spring Data JPA, cần phân biệt hai cơ chế.

**Parser của derived query** đọc tên method repository, phân tách subject, predicate và property path. Ví dụ findByStatusOrderByCreatedAtDesc được phân tích thành điều kiện status và thứ tự createdAt giảm dần. Parser kiểm tra property có tồn tại trong mô hình domain hay không.

**Query enhancer/parser** xử lý chuỗi query được khai báo bằng @Query hoặc native SQL. Nó có thể cần xác định cấu trúc query để bổ sung Sort, tạo count query hoặc viết lại projection.

Hai cơ chế giải quyết vấn đề khác nhau:

| Cơ chế | Đầu vào | Nhiệm vụ |
|---|---|---|
| Derived query parser | Tên method | Tạo query từ property và keyword |
| JPQL query enhancer | Chuỗi JPQL/HQL | Phân tích và bổ sung query, sort hoặc count |
| Native query enhancer | Chuỗi SQL | Phân tích SQL để viết lại sort/count khi được hỗ trợ |
| QueryRewriter | Chuỗi query đã chuẩn bị | Cho phép ứng dụng sửa query trước khi gửi tới EntityManager |

Một method derived query có thể hoạt động tốt nhưng một native @Query phức tạp vẫn có thể không được parser viết lại đúng. Không suy luận khả năng parser native từ việc derived query parser hỗ trợ property path.

## 11. Native query và việc bổ sung ORDER BY

Với native SQL, tên bảng và cột là tên trong database:

~~~java
@Query(
    value = """
        select o.*
        from purchase_orders o
        where o.status = :status
        """,
    countQuery = """
        select count(*)
        from purchase_orders o
        where o.status = :status
        """,
    nativeQuery = true
)
Page<PurchaseOrder> findNativeByStatus(
    @Param("status") String status,
    Pageable pageable
);
~~~

Có thể truyền Pageable có Sort để yêu cầu sắp xếp động. Tuy nhiên, Spring Data phải viết lại chuỗi SQL để thêm ORDER BY. Kết quả phụ thuộc độ phức tạp câu SQL và parser được chọn.

Với native query, cần chú ý:

- Sort phải dùng cột hoặc alias SQL có thể tham chiếu trong query.
- Tên property Java và tên cột SQL có thể khác nhau.
- Alias cần rõ ràng, duy nhất và không xung đột.
- SQL vendor-specific có thể không được parser nhận diện.
- Query có CTE, UNION, subquery lồng nhau hoặc window function cần kiểm tra kỹ.
- Luôn chạy integration test với đúng database production.

Nếu truy vấn có ORDER BY cố định và không cần dynamic sort, khai báo trực tiếp ORDER BY trong SQL có thể đơn giản hơn.

## 12. Regex parser và JSqlParser

Spring Data JPA có thể dùng cơ chế phân tích khác nhau cho native SQL.

**Regex-based query enhancer** dùng các quy tắc nhận diện đơn giản hơn. Nó phù hợp với nhiều câu SQL đơn giản, nhưng không phải parser SQL đầy đủ. Câu query có cấu trúc lồng nhau, CTE, UNION hoặc cú pháp đặc thù có thể khiến việc thêm sort/count không chính xác hoặc không được hỗ trợ.

**JSqlParser** là thư viện parser SQL độc lập. Khi có trên classpath và được chọn, Spring Data JPA có thể dùng nó để phân tích native query phức tạp hơn. Tuy nhiên, JSqlParser cũng có giới hạn theo cú pháp và phiên bản; không bảo đảm hiểu mọi extension riêng của mọi database.

Trong các tài liệu Spring Data JPA 3.5.x, lựa chọn native parser được mô tả qua thuộc tính:

~~~properties
spring.data.jpa.query.native.parser=auto
~~~

Các giá trị được tài liệu 3.5.13 liệt kê:

| Giá trị | Hành vi |
|---|---|
| auto | Tự chọn parser phù hợp; đây là mặc định |
| regex | Dùng query enhancer dựa trên regex tích hợp |
| jsqlparser | Dùng JSqlParser |

Có thể đặt thuộc tính trong file spring.properties hoặc system property theo tài liệu của phiên bản tương ứng. Đừng nhầm cấu hình này với một tùy chọn chung của mọi phiên bản Spring Data JPA.

Khi chọn jsqlparser, cần thêm dependency JSqlParser tương thích với Spring Data JPA đang dùng. Không tự pin một phiên bản bất kỳ nếu dependency management của dự án đã quản lý phiên bản. Kiểm tra dependency tree và release notes khi nâng cấp.

## 13. Count query và giới hạn khi phân trang

Khi repository trả Page<T>, Spring Data cần tổng số phần tử để tính totalElements và totalPages. Nó có thể cố gắng suy ra count query từ query chính.

Ví dụ native query đơn giản có thể khai báo countQuery tường minh:

~~~java
@Query(
    value = """
        select o.*
        from purchase_orders o
        where o.status = :status
        """,
    countQuery = """
        select count(*)
        from purchase_orders o
        where o.status = :status
        """,
    nativeQuery = true
)
Page<PurchaseOrder> findPageByStatus(
    @Param("status") String status,
    Pageable pageable
);
~~~

Với query phức tạp, hãy khai báo countQuery thay vì phụ thuộc hoàn toàn vào việc tự suy ra. Count query cần giữ cùng điều kiện lọc với query dữ liệu nhưng trả về số lượng phù hợp; thường không cần ORDER BY.

Nếu query có JOIN làm nhân số hàng, countQuery phải đếm đúng đơn vị nghiệp vụ. Ví dụ cần đếm entity duy nhất thì có thể phải dùng COUNT(DISTINCT o.id), không phải COUNT(*).

Một điểm quan trọng: **countQuery và dynamic sorting là hai vấn đề riêng**. Việc khai báo countQuery giúp Spring tính tổng số phần tử; nó không tự bảo đảm parser có thể chèn ORDER BY vào một native query phức tạp. Nếu query enhancer không thể viết lại SQL, hãy dùng query đơn giản hơn, parser phù hợp hoặc custom repository.

## 14. QueryRewriter và custom repository

Nếu cần can thiệp query trước khi gửi tới EntityManager, Spring Data JPA cung cấp QueryRewriter ở các phiên bản có hỗ trợ API này.

Ví dụ minh họa:

~~~java
public class OrderQueryRewriter implements QueryRewriter {

    @Override
    public String rewrite(String query, Sort sort) {
        // Chỉ thực hiện các thay đổi đã được kiểm soát.
        return query;
    }
}
~~~

Repository có thể khai báo queryRewriter trên @Query ở phiên bản hỗ trợ:

~~~java
@Query(
    value = "select o from PurchaseOrder o",
    queryRewriter = OrderQueryRewriter.class
)
List<PurchaseOrder> findWithCustomRewrite(Sort sort);
~~~

QueryRewriter là điểm mở rộng cuối để thay đổi chuỗi query. Nó không phải parser SQL tổng quát và không tự bảo đảm query sau khi rewrite hợp lệ. Nếu tự ghép ORDER BY, phải dùng whitelist, xử lý alias và bảo đảm cú pháp đúng với loại query.

Khi truy vấn quá phức tạp, custom repository có thể phù hợp hơn:

- Dùng EntityManager và Criteria API cho truy vấn JPA động.
- Dùng JdbcTemplate cho SQL động cần kiểm soát trực tiếp.
- Dùng Querydsl hoặc thư viện truy vấn chuyên biệt nếu dự án đã chọn.
- Đưa truy vấn vào database view hoặc stored procedure khi phù hợp với kiến trúc.

Custom repository giúp kiểm soát rõ parser, query, tham số và thứ tự sắp xếp thay vì phụ thuộc vào khả năng tự viết lại một chuỗi SQL phức tạp.

## 15. Giới hạn theo phiên bản Spring Data JPA

Không nên giả định một ví dụ Sort/native parser chạy giống nhau ở mọi release train. Khi đọc tài liệu, hãy chọn đúng phiên bản đang được dự án sử dụng.

| Khu vực | Điều cần kiểm tra theo phiên bản |
|---|---|
| Sort và Pageable | Chữ ký repository, hỗ trợ property path, projection và kiểu trả về |
| JpaSort.unsafe | API có sẵn, quy tắc kiểm tra expression và query type |
| Native query enhancer | Khả năng tự thêm ORDER BY và tạo count query |
| Native parser selection | Thuộc tính cấu hình và giá trị auto/regex/jsqlparser |
| JSqlParser | Phiên bản thư viện tương thích và cú pháp SQL được hỗ trợ |
| @NativeQuery | Annotation có trong release đang dùng hay cần @Query(nativeQuery = true) |
| QueryRewriter | API, thuộc tính annotation và cơ chế đăng ký bean trong release đó |
| Scroll API | Loại query method được phép scroll và giới hạn keyset/offset |

Một số mốc thực tế:

- **Sort và Pageable** là API nền tảng của Spring Data, được dùng rộng rãi trong nhiều release.
- Tài liệu chính thức của **Spring Data JPA 3.5.13** mô tả thuộc tính spring.data.jpa.query.native.parser với các lựa chọn auto, regex và jsqlparser.
- Tài liệu hiện hành của Spring Data JPA **4.1.0** tiếp tục có phần hướng dẫn về Sort, JpaSort và native query enhancement. Khi dùng phiên bản mới, vẫn phải kiểm tra compatibility của Spring Framework, JPA provider và parser.
- Annotation chuyên biệt như **@NativeQuery** có thể không có trong release cũ. Dạng **@Query(nativeQuery = true)** là lựa chọn quen thuộc hơn khi cần tương thích với nhiều phiên bản.
- Tài liệu Spring Data JPA **3.5.13** ghi rõ scrolling với string-based query methods chưa được hỗ trợ. Nếu cần cuộn kết quả lớn, hãy xác nhận trạng thái hỗ trợ của đúng phiên bản trước khi thiết kế API.
- Tên thuộc tính cấu hình, parser mặc định và dependency JSqlParser có thể thay đổi theo release. Không sao chép cấu hình của phiên bản mới vào dự án cũ mà không kiểm tra.

Khi dự án dùng Spring Boot, nên để Spring Boot dependency management quản lý Spring Data release train tương thích. Không nâng riêng spring-data-jpa hoặc JSqlParser vượt khỏi bộ phiên bản được quản lý nếu chưa kiểm tra compatibility matrix và release notes.

## 16. Keyset scrolling và thứ tự ổn định

Với dữ liệu rất lớn, offset pagination có thể trở nên tốn kém vì database phải bỏ qua nhiều hàng trước vị trí trang cần lấy. Keyset scrolling dùng giá trị của các trường sắp xếp ở phần tử cuối trang trước để tiếp tục truy vấn.

Để keyset hoạt động đáng tin cậy:

- Sort phải có thứ tự ổn định và nên có khóa duy nhất làm tie-breaker.
- Các thuộc tính keyset dùng để so sánh cần không null theo yêu cầu của API/provider.
- Các thuộc tính sắp xếp phải có trong kết quả để framework lấy được keyset.
- Index database nên phù hợp với điều kiện lọc và thứ tự sort.
- Nếu dùng projection, phải đưa các trường sort vào projection.
- Kiểm tra giới hạn của phiên bản đối với query method dạng @Query.

Theo tài liệu 3.5.13, Scroll API hỗ trợ query methods, Query by Example và Querydsl; scrolling với string-based query methods chưa được hỗ trợ ở tài liệu release này. Vì vậy, không mặc định có thể kết hợp mọi @Query string với keyset scrolling.

## 17. Kiểm thử Sort và parser

Một bộ integration test nên kiểm tra nhiều lớp hành vi:

**Sort cơ bản**

- Truyền ASC và DESC.
- Truyền nhiều Order.
- Xác minh thứ tự tie-breaker theo id.
- Sắp xếp theo property lồng nhau.
- Kiểm tra ignoreCase và null handling trên database mục tiêu.

**JPQL**

- Sắp xếp theo entity property.
- Sắp xếp theo alias của projection.
- Xác minh Sort.by với biểu thức hàm bị từ chối khi không hợp lệ.
- Kiểm tra JpaSort.unsafe với biểu thức tĩnh đã được kiểm soát.

**Native SQL**

- Sắp xếp native query đơn giản.
- Sắp xếp theo tên cột hoặc alias SQL.
- Kiểm tra regex và JSqlParser nếu dự án hỗ trợ cả hai cấu hình.
- Kiểm tra CTE, UNION, subquery hoặc cú pháp database riêng nếu query thực tế sử dụng.
- Xác minh countQuery và totalElements của Page.

**API và bảo mật**

- Từ chối field không nằm trong whitelist.
- Từ chối hoặc chuẩn hóa direction không hợp lệ.
- Giới hạn page size và số lượng sort criteria.
- Không cho raw input đi vào JpaSort.unsafe.

Không chỉ kiểm thử trên H2 nếu production dùng PostgreSQL, MySQL hoặc SQL Server. Parser có thể viết query giống nhau, nhưng dialect, collation, NULL ordering và SQL syntax của database thật vẫn có thể khác.

## 18. Lỗi thường gặp và cách xử lý

**1. Sort báo không tìm thấy property**

Kiểm tra tên property Java trong entity, không dùng tên cột SQL. Nếu query có alias, kiểm tra alias đó được khai báo và tham chiếu hợp lệ.

**2. Sort.by không chấp nhận LENGTH(...)**

Sort thông thường chỉ nhận property path hoặc alias hợp lệ. Dùng alias trong SELECT hoặc JpaSort.unsafe với biểu thức cố định đã kiểm soát.

**3. Native query không nhận dynamic Sort**

Kiểm tra parser, cấu trúc SQL, tên cột/alias và phiên bản Spring Data JPA. Với SQL phức tạp, thử JSqlParser nếu tương thích hoặc dùng custom repository.

**4. Page trả totalElements sai**

Kiểm tra count query. Nếu JOIN làm nhân số hàng, count query có thể phải dùng COUNT(DISTINCT primaryKey). Đảm bảo điều kiện lọc của count query khớp query chính.

**5. Query chạy được nhưng thứ tự không ổn định**

Thêm khóa duy nhất làm tiêu chí cuối, ví dụ createdAt DESC, id DESC. Nếu không có tie-breaker, bản ghi cùng giá trị sort có thể đổi vị trí giữa các lần chạy.

**6. NULL sắp xếp khác nhau giữa môi trường**

Null handling có thể phụ thuộc database/provider. Dùng CASE hoặc biểu thức rõ ràng khi nghiệp vụ cần cùng kết quả trên nhiều hệ quản trị và kiểm thử trên database thật.

**7. Parser lỗi với CTE hoặc UNION**

Không giả định regex enhancer hỗ trợ đầy đủ SQL. Kiểm tra JSqlParser và cú pháp tương ứng; nếu vẫn không phù hợp, khai báo query/count tường minh hoặc chuyển sang custom repository.

**8. Người dùng có thể sắp xếp theo field bất kỳ**

Whitelist các sort key công khai. Không ghép trực tiếp tham số request vào query và không đưa raw input vào JpaSort.unsafe.

**9. Nâng phiên bản làm parser thay đổi hành vi**

Đọc release notes, dependency tree và tài liệu đúng phiên bản. Chạy integration test cho tất cả native query có dynamic sort/count trước khi phát hành.

## 19. Quy trình triển khai sắp xếp động

Khi thêm dynamic sorting cho một màn hình:

1. Xác định những trường nào thực sự cần cho người dùng sắp xếp.
2. Ánh xạ tên sort công khai sang property Java hoặc alias query hợp lệ.
3. Xác định thứ tự mặc định và thêm unique tie-breaker.
4. Chọn Sort nếu chỉ cần sắp xếp; chọn Pageable nếu cần phân trang.
5. Với @Query JPQL, kiểm tra property path và alias.
6. Với biểu thức hàm, ưu tiên alias; chỉ dùng JpaSort.unsafe cho expression tĩnh.
7. Với native SQL, kiểm tra parser, cột/alias và độ phức tạp query.
8. Với Page native, khai báo countQuery rõ ràng khi query không đơn giản.
9. Kiểm tra cấu hình parser và JSqlParser theo release train.
10. Viết integration test trên database mục tiêu.
11. Kiểm tra index và execution plan khi dữ liệu lớn.
12. Đọc lại tài liệu và release notes mỗi khi nâng Spring Data JPA.

## 20. Checklist tự đánh giá

- [ ] Tôi phân biệt được OrderBy tĩnh và Sort động.
- [ ] Tôi biết tạo Sort với một hoặc nhiều Order.
- [ ] Tôi biết kết hợp Sort với Pageable và PageRequest.
- [ ] Tôi dùng property Java thay vì tên cột SQL trong JPQL Sort.
- [ ] Tôi biết sắp xếp theo alias của projection.
- [ ] Tôi hiểu giới hạn của Sort.by với biểu thức hàm.
- [ ] Tôi biết khi nào dùng JpaSort.unsafe và cách bảo vệ đầu vào.
- [ ] Tôi phân biệt derived query parser với query enhancer.
- [ ] Tôi hiểu native SQL có thể cần regex hoặc JSqlParser.
- [ ] Tôi biết cấu hình native parser theo đúng release hỗ trợ.
- [ ] Tôi phân biệt countQuery với dynamic ORDER BY.
- [ ] Tôi biết khi nào cần QueryRewriter hoặc custom repository.
- [ ] Tôi hiểu tie-breaker và thứ tự ổn định khi phân trang.
- [ ] Tôi kiểm tra được khác biệt theo Spring Data JPA version và database.
- [ ] Tôi có integration test cho Sort, native query, parser và count query.

## 21. Câu hỏi ôn tập

**1. Sort khác OrderBy trong tên method thế nào?**

OrderBy tạo thứ tự cố định trong method name. Sort là đối tượng truyền vào lúc gọi repository để chọn thứ tự động.

**2. Vì sao Sort.by("created_at") có thể sai với entity có field createdAt?**

JPQL Sort thường dùng property Java. Tên cột SQL created_at chỉ phù hợp trong ngữ cảnh native SQL có cột hoặc alias tương ứng.

**3. Khi nào dùng JpaSort.unsafe?**

Khi cần expression sắp xếp như LENGTH(property) mà property path thông thường không biểu diễn được. Chỉ dùng expression cố định đã được kiểm soát; không đưa raw input từ client vào.

**4. Query enhancer khác derived query parser thế nào?**

Derived query parser chuyển tên method thành điều kiện query. Query enhancer phân tích chuỗi @Query/native SQL để hỗ trợ sort, count hoặc rewrite.

**5. Vì sao native SQL phức tạp có thể không được thêm Sort tự động?**

Vì Spring Data không phải parser SQL tổng quát. Regex enhancer chỉ xử lý tốt các cấu trúc đơn giản; cú pháp phức tạp cần parser phù hợp hoặc custom query implementation.

**6. JSqlParser có bảo đảm mọi SQL của database đều được hỗ trợ không?**

Không. Nó hỗ trợ nhiều cấu trúc SQL nhưng vẫn phụ thuộc phiên bản và cú pháp. Các extension riêng của database cần được kiểm thử.

**7. countQuery có giải quyết được lỗi dynamic sorting không?**

Không. countQuery giải quyết việc đếm tổng số kết quả cho Page. Việc chèn ORDER BY vào query dữ liệu là một bước riêng và vẫn phụ thuộc query enhancer/parser.

**8. Vì sao cần thêm id làm tiêu chí sort cuối?**

Nếu nhiều hàng có cùng giá trị sort chính, database không bảo đảm thứ tự tương đối giữa chúng. Khóa duy nhất tạo thứ tự ổn định hơn, đặc biệt khi phân trang.

**9. Khi nào nên chuyển sang custom repository?**

Khi query quá phức tạp, parser không thể viết lại an toàn, cần kiểm soát SQL hoặc cần tối ưu đặc thù database. Có thể dùng EntityManager, Criteria API hoặc JdbcTemplate.

Khi hiểu Sort, Pageable và giới hạn của query parser, bạn có thể xây dựng thứ tự kết quả linh hoạt mà vẫn kiểm soát được property, tính ổn định, hiệu năng, bảo mật và khả năng tương thích giữa các phiên bản Spring Data JPA.

## Tài liệu tham khảo

- [Spring Data JPA 3.5 — JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/3.5/jpa/query-methods.html)
- [Spring Data JPA — JPA Query Methods (current reference)](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [JSqlParser project](https://github.com/JSQLParser/JSqlParser)
- [Spring Data JPA project and release information](https://github.com/spring-projects/spring-data-jpa)
