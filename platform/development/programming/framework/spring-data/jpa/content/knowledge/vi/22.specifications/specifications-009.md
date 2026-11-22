# Phân trang, sắp xếp và Fluent Query với Spring Data JPA Specification

## 1. Mục tiêu: truy vấn linh hoạt mà không tải thừa dữ liệu

Trong ứng dụng thực tế, một màn hình tìm kiếm thường cho phép người dùng kết hợp nhiều điều kiện: trạng thái, tên, khoảng ngày, mức giá, rồi chọn trang và thứ tự sắp xếp. Spring Data JPA `Specification` giúp ghép các điều kiện động thành một predicate có thể tái sử dụng. `Pageable` và `Sort` bổ sung cách phân trang, sắp xếp kết quả. Ở các phiên bản Spring Data JPA hỗ trợ Fluent Query, có thể định nghĩa thêm kiểu kết quả, projection, giới hạn số hàng và cách lấy kết quả ngay tại nơi gọi truy vấn.

Ba khái niệm có vai trò riêng:

- **Specification:** mô tả điều kiện lọc dựa trên Criteria API.
- **Pageable / Sort:** mô tả trang cần lấy và thứ tự kết quả.
- **Fluent Query:** điều khiển cách thực thi Specification và kiểu dữ liệu trả về bằng chuỗi thao tác trung gian và thao tác kết thúc.

Kết hợp đúng các API này giúp một bộ điều kiện tìm kiếm được dùng cho nhiều use case: lấy entity, lấy DTO, lấy một trang, lấy một lát kết quả, đếm hoặc kiểm tra tồn tại.

## 2. Chuẩn bị repository hỗ trợ Specification

Repository cần mở rộng `JpaSpecificationExecutor` ngoài `JpaRepository`:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
~~~

`JpaRepository` cung cấp thao tác CRUD, phân trang và sắp xếp thông dụng. `JpaSpecificationExecutor` cung cấp các phương thức thực thi `Specification`, ví dụ:

- `findAll(spec)` trả về toàn bộ entity phù hợp.
- `findAll(spec, sort)` trả về danh sách entity đã sắp xếp.
- `findAll(spec, pageable)` trả về `Page<T>`.
- `findOne(spec)` trả về `Optional<T>` và báo lỗi nếu có nhiều hơn một kết quả.
- `count(spec)` đếm số entity phù hợp.
- `exists(spec)` kiểm tra có kết quả phù hợp hay không.

Những method `findAll` cơ bản với Specification và Pageable/Sort có sẵn từ các phiên bản Spring Data JPA trước Fluent API. Vì vậy, dự án cũ vẫn có thể phân trang và sắp xếp bằng Specification mà không cần dùng Fluent API.

## 3. Specification biểu diễn điều kiện lọc

`Specification<T>` là một predicate được xây dựng bằng JPA Criteria API. Một Specification nhận `Root<T>`, `CriteriaQuery<?>` và `CriteriaBuilder`, sau đó trả về `Predicate`.

Ví dụ entity đơn giản:

~~~java
@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String fullName;
    private String email;

    @Enumerated(EnumType.STRING)
    private CustomerStatus status;

    private LocalDate createdDate;

    protected Customer() {
    }

    // Constructor, getters and domain methods omitted.
}
~~~

Tạo Specification theo trạng thái:

~~~java
public final class CustomerSpecifications {

    private CustomerSpecifications() {
    }

    public static Specification<Customer> hasStatus(
            CustomerStatus status) {

        return (root, query, cb) ->
            status == null
                ? cb.conjunction()
                : cb.equal(root.get("status"), status);
    }
}
~~~

`cb.conjunction()` tạo điều kiện luôn đúng. Nhờ vậy, khi không truyền trạng thái, điều kiện này không lọc bỏ bản ghi nào.

Tạo Specification tìm tên chứa từ khóa, không phân biệt chữ hoa/thường:

~~~java
public static Specification<Customer> nameContains(String keyword) {
    return (root, query, cb) -> {
        if (keyword == null || keyword.isBlank()) {
            return cb.conjunction();
        }

        String pattern =
            "%" + keyword.trim().toLowerCase(Locale.ROOT) + "%";

        return cb.like(
            cb.lower(root.<String>get("fullName")),
            pattern
        );
    };
}
~~~

Tạo điều kiện theo khoảng ngày:

~~~java
public static Specification<Customer> createdBetween(
        LocalDate from,
        LocalDate to) {

    return (root, query, cb) -> {
        if (from == null && to == null) {
            return cb.conjunction();
        }
        if (from == null) {
            return cb.lessThanOrEqualTo(root.get("createdDate"), to);
        }
        if (to == null) {
            return cb.greaterThanOrEqualTo(root.get("createdDate"), from);
        }
        return cb.between(root.get("createdDate"), from, to);
    };
}
~~~

Các method trên là ví dụ mã trong ứng dụng Spring Data JPA; cần có enum, entity mapping, import và dependency tương ứng. Tách mỗi điều kiện thành một Specification nhỏ giúp dễ kiểm thử và kết hợp.

## 4. Ghép Specification bằng AND và OR

Các Specification có thể được kết hợp bằng `and()`, `or()` và `not()`.

Ví dụ tìm khách hàng đang hoạt động, có tên phù hợp và được tạo trong khoảng ngày:

~~~java
Specification<Customer> spec =
    CustomerSpecifications.hasStatus(CustomerStatus.ACTIVE)
        .and(CustomerSpecifications.nameContains("an"))
        .and(CustomerSpecifications.createdBetween(
            LocalDate.of(2025, 1, 1),
            LocalDate.of(2025, 12, 31)
        ));
~~~

Dùng `or()` khi chỉ cần thỏa một trong nhiều điều kiện:

~~~java
Specification<Customer> nameOrEmail =
    CustomerSpecifications.nameContains("an")
        .or((root, query, cb) ->
            cb.like(
                cb.lower(root.<String>get("email")),
                "%an%"
            )
        );
~~~

Có thể dùng `not()` để phủ định một Specification:

~~~java
Specification<Customer> notActive =
    Specification.not(
        CustomerSpecifications.hasStatus(CustomerStatus.ACTIVE)
    );
~~~

Cần thiết kế rõ ý nghĩa của điều kiện khi tham số có thể null hoặc rỗng. Nếu điều kiện bị bỏ qua, trả về predicate luôn đúng là cách thường dùng. Nếu null có nghĩa là tìm các bản ghi có cột NULL, hãy viết `isNull()` thay vì bỏ qua điều kiện.

## 5. Pageable và PageRequest

`Pageable` là abstraction mô tả số trang, kích thước trang và có thể cả thứ tự sắp xếp. `PageRequest` là implementation thường dùng để tạo yêu cầu phân trang.

Ví dụ lấy trang đầu tiên, 20 bản ghi:

~~~java
Pageable pageable = PageRequest.of(0, 20);
~~~

Số trang bắt đầu từ 0:

- `PageRequest.of(0, 20)` là trang đầu tiên.
- `PageRequest.of(1, 20)` là trang thứ hai.
- `PageRequest.of(2, 20)` là trang thứ ba.

Tham số thứ hai là kích thước trang, phải là số dương. Không nên dùng page size quá lớn nếu kết quả chứa entity hoặc quan hệ phức tạp.

Có thể đặt sắp xếp ngay trong `PageRequest`:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdDate"),
    Sort.Order.asc("id")
);

Pageable pageable = PageRequest.of(0, 20, sort);
~~~

Ở đây, kết quả được sắp xếp theo ngày tạo giảm dần, sau đó theo ID tăng dần. ID là khóa duy nhất nên giúp thứ tự ổn định khi nhiều khách hàng có cùng ngày tạo.

## 6. Page, Slice và List khi phân trang

Spring Data JPA có thể trả về `Page<T>`, `Slice<T>` hoặc `List<T>` khi method nhận `Pageable`.

| Kiểu trả về | Metadata | Count query | Khi nên dùng |
|---|---|---|---|
| `Page<T>` | Có tổng số phần tử, tổng số trang, trang hiện tại | Thường cần để xác định tổng số | Giao diện cần tổng số trang/bản ghi |
| `Slice<T>` | Có thông tin còn trang tiếp theo hay không | Không cần đếm tổng | Cuộn hoặc điều hướng từng phần |
| `List<T>` | Chỉ có nội dung trong phạm vi trang | Không cần tạo metadata tổng | Chỉ cần một đoạn kết quả |

Ví dụ repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {

    Page<Customer> findByStatus(
        CustomerStatus status,
        Pageable pageable
    );

    Slice<Customer> findByEmailContaining(
        String keyword,
        Pageable pageable
    );

    List<Customer> findByFullNameContaining(
        String keyword,
        Pageable pageable
    );
}
~~~

Dùng Specification để lấy một Page:

~~~java
Page<Customer> page =
    customerRepository.findAll(spec, PageRequest.of(0, 20));
~~~

Có thể đọc metadata:

~~~java
int currentPage = page.getNumber();
int pageSize = page.getSize();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
boolean hasPrevious = page.hasPrevious();
~~~

`Page<T>` hữu ích cho giao diện hiển thị “trang 2 trên 8” hoặc tổng số kết quả. Để tính tổng, Spring Data thường cần thực hiện count query; với truy vấn phức tạp, phép đếm có thể tốn kém. Framework có thể tối ưu và không cần chạy count query trong một số trường hợp có thể suy ra tổng từ kết quả hiện tại.

`Slice<T>` chỉ cần biết có phần tử tiếp theo hay không. Cơ chế thường lấy thêm một hàng để xác định `hasNext()`, không cần đếm toàn bộ tập kết quả.

`List<T>` kết hợp với `Pageable` chỉ lấy phạm vi dữ liệu được yêu cầu mà không tạo metadata của Page. Dùng cách này khi caller chỉ cần danh sách trong một trang và không cần biết tổng số bản ghi.

## 7. Sử dụng Specification cùng Pageable

Ví dụ service nhận các bộ lọc từ request:

~~~java
@Service
public class CustomerSearchService {

    private final CustomerRepository repository;

    public CustomerSearchService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Page<Customer> search(
            CustomerStatus status,
            String keyword,
            LocalDate from,
            LocalDate to,
            int page,
            int size) {

        Specification<Customer> spec =
            CustomerSpecifications.hasStatus(status)
                .and(CustomerSpecifications.nameContains(keyword))
                .and(CustomerSpecifications.createdBetween(from, to));

        Pageable pageable = PageRequest.of(
            page,
            size,
            Sort.by(
                Sort.Order.desc("createdDate"),
                Sort.Order.asc("id")
            )
        );

        return repository.findAll(spec, pageable);
    }
}
~~~

Service tạo Specification từ các bộ lọc rồi tạo Pageable. Repository thực thi truy vấn và trả về Page.

Trong API thực tế, cần xác thực `page` không âm và `size` nằm trong giới hạn cho phép. Không nên để client yêu cầu hàng trăm nghìn bản ghi trong một trang. Có thể đặt page size mặc định và tối đa tại tầng API/service.

`Pageable.unpaged()` biểu thị không phân trang. Nếu method nhận Sort, dùng `Sort.unsorted()` khi không cần sắp xếp. Các API nhận Pageable/Sort thường yêu cầu giá trị không null; không truyền null để biểu thị “không phân trang” hoặc “không sắp xếp”.

## 8. Sắp xếp bằng Sort

`Sort` mô tả một hoặc nhiều thứ tự. Mỗi `Sort.Order` chứa thuộc tính, chiều tăng/giảm và một số tùy chọn.

Ví dụ:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("status"),
    Sort.Order.desc("createdDate"),
    Sort.Order.asc("id")
);
~~~

Có thể viết ngắn:

~~~java
Sort sort = Sort.by("createdDate").descending()
    .and(Sort.by("id").ascending());
~~~

Một số thao tác thường dùng:

- `Sort.by("name")`: sắp xếp tăng dần theo name.
- `Sort.by("name").descending()`: giảm dần.
- `Sort.Order.asc("name")`: một order tăng dần.
- `Sort.Order.desc("createdDate")`: một order giảm dần.
- `Sort.unsorted()`: không áp dụng sắp xếp.
- `Sort.Order.asc("name").ignoreCase()`: yêu cầu sắp xếp không phân biệt hoa/thường khi được hỗ trợ.
- `Sort.Order.asc("name").nullsLast()`: chỉ định mong muốn xử lý giá trị null; cách database thực hiện có thể khác nhau.

Thuộc tính trong Sort phải phân giải được thành thuộc tính của entity hoặc alias được query khai báo. Ví dụ, nếu entity có `createdDate`, dùng `Sort.by("createdDate")`; không dùng tên cột SQL như `created_date` trừ khi đó là alias hợp lệ trong query.

## 9. Sắp xếp tĩnh bằng tên method

Nếu thứ tự luôn cố định, có thể khai báo `OrderBy` ngay trong tên repository method:

~~~java
List<Customer> findByStatusOrderByCreatedDateDescIdAsc(
    CustomerStatus status
);
~~~

Method trên lọc theo status, sau đó sắp xếp ngày tạo giảm dần và ID tăng dần.

Sắp xếp tĩnh phù hợp khi nghiệp vụ có một thứ tự cố định. Nếu người dùng có thể chọn cột sắp xếp hoặc chiều tăng/giảm, hãy nhận `Sort` hoặc `Pageable` để điều khiển động.

Không cần vừa mã hóa một thứ tự cố định trong tên method vừa truyền một thứ tự khác nếu không có lý do rõ ràng. Hãy xác định một nguồn quyết định sort để tránh hành vi khó đoán.

## 10. Sắp xếp động với @Query

Method dùng `@Query` cũng có thể nhận `Sort` hoặc `Pageable`:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select c
        from Customer c
        where c.status = :status
    """)
    List<Customer> findByStatus(
        @Param("status") CustomerStatus status,
        Sort sort
    );
}
~~~

Gọi:

~~~java
List<Customer> customers = repository.findByStatus(
    CustomerStatus.ACTIVE,
    Sort.by("fullName").ascending()
);
~~~

Spring Data bổ sung `ORDER BY` phù hợp vào truy vấn. Sort expression phải là property path hợp lệ hoặc alias có thể tham chiếu trong query.

Ví dụ query chọn biểu thức có alias:

~~~java
@Query("""
    select c.id as id, length(c.fullName) as nameLength
    from Customer c
    where c.status = :status
""")
List<Object[]> findNameLengths(
    @Param("status") CustomerStatus status,
    Sort sort
);
~~~

Có thể sắp xếp theo alias `nameLength` nếu alias đó được query cung cấp và có thể tham chiếu.

## 11. JpaSort.unsafe và biểu thức sắp xếp

Mặc định, Spring Data JPA kiểm tra Sort expression để tránh các hàm hoặc biểu thức không phải property path hợp lệ. Trong một số trường hợp, cần sắp xếp theo biểu thức JPQL như độ dài tên hoặc một phép tính.

Có thể dùng `JpaSort.unsafe()`:

~~~java
List<Customer> customers = repository.findByStatus(
    CustomerStatus.ACTIVE,
    JpaSort.unsafe("LENGTH(fullName)")
);
~~~

`JpaSort.unsafe()` cho phép đưa biểu thức vào phần ORDER BY mà không kiểm tra như property path thông thường. Đây là lựa chọn có rủi ro nếu biểu thức được tạo từ đầu vào người dùng.

Quy tắc an toàn:

- Chỉ dùng biểu thức cố định do lập trình viên kiểm soát.
- Không nối chuỗi sort tùy ý từ request vào `JpaSort.unsafe()`.
- Ánh xạ tên sort client gửi lên thành danh sách property/biểu thức được cho phép.
- Kiểm tra cú pháp JPQL và khả năng hỗ trợ của provider/database.
- Ưu tiên alias query hoặc property path chuẩn nếu đáp ứng yêu cầu.

Ví dụ whitelist:

~~~java
public Sort resolveSort(String requestedSort) {
    return switch (requestedSort) {
        case "name" -> Sort.by("fullName").ascending();
        case "newest" -> Sort.by(
            Sort.Order.desc("createdDate"),
            Sort.Order.asc("id")
        );
        case "oldest" -> Sort.by(
            Sort.Order.asc("createdDate"),
            Sort.Order.asc("id")
        );
        default -> Sort.by("id").ascending();
    };
}
~~~

Client chỉ chọn một khóa hợp lệ; client không được gửi trực tiếp một biểu thức JPQL/SQL.

## 12. Tính ổn định của thứ tự khi phân trang

Phân trang dựa trên một tập kết quả có thứ tự. Nếu không khai báo sort, database không bảo đảm thứ tự bản ghi ổn định giữa các lần truy vấn.

Giả sử nhiều khách hàng có cùng `createdDate` và query chỉ sắp xếp theo ngày. Các hàng có cùng giá trị có thể xuất hiện theo thứ tự khác nhau ở hai lần truy vấn. Khi chuyển từ trang này sang trang khác, điều đó có thể làm bản ghi lặp hoặc bị bỏ qua.

Hãy thêm khóa duy nhất làm tie-breaker:

~~~java
Sort stableSort = Sort.by(
    Sort.Order.desc("createdDate"),
    Sort.Order.asc("id")
);
~~~

Thứ tự này tạo ra một thứ tự toàn phần nếu ID là duy nhất và có giá trị.

Tuy nhiên, sort ổn định không bảo đảm snapshot nhất quán khi dữ liệu thay đổi giữa các request. Nếu một bản ghi được thêm/xóa hoặc thay đổi giá trị sort trong lúc người dùng đang duyệt trang, vị trí offset có thể dịch chuyển.

Với dữ liệu rất lớn hoặc tác vụ nền cần duyệt tuần tự, cân nhắc Scroll API với `Window<T>` và keyset position khi điều kiện phù hợp. Keyset dùng giá trị sort của bản ghi cuối thay vì bỏ qua một số lượng lớn hàng. Cần có sort key không null, thứ tự ổn định và index phù hợp.

## 13. Count query và hiệu năng của Page

Một Page cần tổng số phần tử để tính `totalElements` và `totalPages`. Spring Data có thể suy ra count query từ truy vấn nội dung hoặc từ Specification. Với truy vấn phức tạp, việc đếm có thể cần JOIN hoặc DISTINCT và gây chi phí lớn.

Ví dụ dùng Specification:

~~~java
Page<Customer> page = repository.findAll(spec, pageable);
~~~

Nếu Specification tạo JOIN tới collection, cần kiểm tra số lượng entity được đếm. JOIN một-nhiều có thể nhân số hàng SQL. Khi đó, count query phải phản ánh đúng số entity gốc, thường cần đếm distinct ID hoặc cấu trúc truy vấn phù hợp.

### Count specification riêng

Từ Spring Data JPA 3.5, `JpaSpecificationExecutor` cung cấp overload nhận một Specification riêng cho phần đếm:

~~~java
Page<Customer> page = repository.findAll(
    contentSpec,
    countSpec,
    pageable
);
~~~

`contentSpec` có thể chứa JOIN/fetch hoặc điều kiện cần cho dữ liệu trang. `countSpec` mô tả đúng tập entity cần đếm, nhưng có thể bỏ các fetch join không cần thiết để truy vấn count nhẹ hơn.

Hai Specification phải biểu đạt cùng tập kết quả về mặt nghiệp vụ. Nếu `countSpec` bỏ mất điều kiện lọc, `totalElements` sẽ sai dù nội dung trang đúng.

Khi dùng `@Query`, có thể khai báo `countQuery` riêng nếu truy vấn chính phức tạp hoặc Spring Data không suy ra được phép đếm phù hợp.

## 14. Fluent Query là gì?

Fluent Query cho phép xác định cách thực thi truy vấn ngay trong một hàm callback. Với Specification, `JpaSpecificationExecutor` cung cấp method `findBy(spec, queryFunction)`.

Ý tưởng là:

1. Truyền Specification để xác định bản ghi phù hợp.
2. Nhận đối tượng fluent query trong callback.
3. Gọi các thao tác trung gian như `sortBy`, `limit`, `as` hoặc `project`.
4. Gọi thao tác kết thúc như `all`, `page`, `slice`, `first`, `count` hoặc `exists`.
5. Trả về kết quả đã thực thi từ callback.

Ví dụ tổng quát:

~~~java
List<Customer> customers = repository.findBy(
    spec,
    query -> query
        .sortBy(Sort.by("fullName").ascending())
        .limit(100)
        .all()
);
~~~

Method trên áp dụng Specification, sắp xếp theo tên, giới hạn tối đa 100 kết quả và trả về List.

Fluent Query không bắt buộc cho mọi truy vấn. Với truy vấn đơn giản, `findAll(spec, pageable)` hoặc `findAll(spec, sort)` thường ngắn và dễ đọc hơn. Fluent Query hữu ích khi cần kết hợp projection, sort, limit và kiểu kết quả trong một lời gọi.

## 15. Phân trang với Fluent Query

Ví dụ lấy Page theo Specification và projection:

~~~java
Page<CustomerSummary> page = repository.findBy(
    spec,
    query -> query
        .as(CustomerSummary.class)
        .page(PageRequest.of(
            0,
            20,
            Sort.by("fullName").ascending()
        ))
);
~~~

`as(CustomerSummary.class)` xác định kiểu dữ liệu trả về. `page(Pageable)` thực thi truy vấn theo trang và trả về `Page<CustomerSummary>`.

Có thể dùng `slice(Pageable)` nếu không cần tổng số:

~~~java
Slice<CustomerSummary> slice = repository.findBy(
    spec,
    query -> query
        .as(CustomerSummary.class)
        .slice(PageRequest.of(
            0,
            50,
            Sort.by("id").ascending()
        ))
);
~~~

`Pageable` có chứa Sort. Nếu Pageable truyền vào đã được sắp xếp, sort của nó sẽ ghi đè sort đã đặt trước đó bằng `sortBy()`. Vì vậy, tránh thiết lập hai thứ tự mâu thuẫn; nên chọn một nơi duy nhất để quyết định thứ tự cuối cùng.

## 16. Projection với Fluent Query

Fluent Query cho phép chuyển kết quả entity sang một projection phù hợp với use case.

Ví dụ record DTO:

~~~java
public record CustomerSummary(
    Long id,
    String fullName,
    String email
) {}
~~~

Repository có thể lấy DTO trực tiếp:

~~~java
List<CustomerSummary> summaries = repository.findBy(
    spec,
    query -> query
        .as(CustomerSummary.class)
        .sortBy(Sort.by("fullName").ascending())
        .all()
);
~~~

Projection giúp chỉ trả về dữ liệu cần thiết, giảm việc truyền entity đầy đủ qua tầng service/API. Tuy nhiên, constructor và các thuộc tính projection phải phù hợp với entity và khả năng projection của Spring Data JPA.

`as(Class<R>)` thay đổi kiểu kết quả mong muốn. `project("fieldA", "fieldB")` giới hạn các thuộc tính được đọc trong những trường hợp projection hỗ trợ. Hai thao tác có mục đích gần nhau nhưng không hoàn toàn thay thế cho nhau: `as` chọn kiểu projection, còn `project` giới hạn danh sách property.

Với DTO class/record, hãy bảo đảm constructor tương thích. Với interface projection, các getter cần khớp thuộc tính được expose. Kiểm thử projection bằng integration test thay vì chỉ kiểm tra compile-time.

## 17. Các thao tác Fluent Query thường dùng

Fluent Query có hai nhóm thao tác:

### Thao tác trung gian

| Method | Ý nghĩa |
|---|---|
| `sortBy(Sort)` | Thêm thứ tự sắp xếp |
| `limit(int)` | Giới hạn số kết quả |
| `as(Class<R>)` | Chọn kiểu projection/kết quả |
| `project(String...)` | Chỉ lấy các thuộc tính được chỉ định |

### Thao tác kết thúc

| Method | Kiểu kết quả | Ý nghĩa |
|---|---|---|
| `all()` | `List<T>` | Lấy tất cả kết quả phù hợp trong phạm vi query |
| `first()` | `Optional<T>` | Lấy phần tử đầu tiên hoặc empty |
| `firstValue()` | `T` hoặc null | Biến thể nullable của first |
| `one()` | `Optional<T>` | Yêu cầu tối đa một kết quả; nhiều hơn một sẽ lỗi |
| `oneValue()` | `T` hoặc null | Biến thể nullable của one |
| `page(Pageable)` | `Page<T>` | Lấy trang kèm tổng số |
| `slice(Pageable)` | `Slice<T>` | Lấy lát kết quả, không cần tổng số |
| `scroll(ScrollPosition)` | `Window<T>` | Duyệt theo vị trí offset/keyset |
| `stream()` | `Stream<T>` | Tiêu thụ kết quả qua stream; phải đóng |
| `count()` | `long` | Đếm số entity phù hợp |
| `exists()` | `boolean` | Kiểm tra có kết quả hay không |

`first()` phù hợp khi chỉ cần một phần tử bất kỳ theo thứ tự đã xác định. Nếu không có Sort, “phần tử đầu” không có thứ tự nghiệp vụ bảo đảm. `one()` phù hợp khi nghiệp vụ yêu cầu tối đa một kết quả; nếu query trả về nhiều hơn một, Spring Data ném `IncorrectResultSizeDataAccessException`.

Các thao tác trung gian và kết thúc phải được gọi bên trong callback của `findBy`. Không lưu đối tượng query trung gian để dùng sau callback.

## 18. Fluent Query: first, count và exists

Lấy khách hàng mới nhất:

~~~java
Optional<Customer> newest = repository.findBy(
    spec,
    query -> query
        .sortBy(Sort.by(
            Sort.Order.desc("createdDate"),
            Sort.Order.asc("id")
        ))
        .first()
);
~~~

Đếm kết quả:

~~~java
long total = repository.findBy(
    spec,
    query -> query.count()
);
~~~

Kiểm tra tồn tại:

~~~java
boolean hasMatch = repository.findBy(
    spec,
    query -> query.exists()
);
~~~

Nếu chỉ cần biết có dữ liệu hay không, dùng `exists()` rõ nghĩa hơn việc tải toàn bộ danh sách rồi kiểm tra `isEmpty()`.

## 19. Fluent Query với custom count specification

Từ Spring Data JPA 3.5, `SpecificationFluentQuery` hỗ trợ `page(Pageable, countSpec)`. Có thể dùng một Specification cho truy vấn nội dung và một Specification khác cho phép đếm:

~~~java
Page<CustomerSummary> page = repository.findBy(
    contentSpec,
    query -> query
        .as(CustomerSummary.class)
        .page(pageable, countSpec)
);
~~~

Cách này hữu ích khi truy vấn nội dung có JOIN hoặc fetch cần thiết, nhưng count query không cần những JOIN đó. `countSpec` phải giữ nguyên logic lọc của tập kết quả; chỉ bỏ phần join/fetch không cần cho việc đếm.

Nếu dự án dùng Spring Data JPA trước 3.5, overload custom count specification này chưa có. Có thể dùng `findAll(spec, pageable)` hoặc khai báo count query phù hợp ở nơi hỗ trợ. Không sao chép ví dụ API mới vào dự án cũ mà chưa kiểm tra dependency version.

## 20. Fluent Query kết hợp scrolling

Ở các phiên bản hỗ trợ, Fluent Query có thể kết thúc bằng `scroll(ScrollPosition)` để nhận `Window<T>`:

~~~java
Window<Customer> window = repository.findBy(
    spec,
    query -> query
        .sortBy(Sort.by("id").ascending())
        .scroll(ScrollPosition.offset())
);
~~~

Có thể dùng keyset khi sort key phù hợp:

~~~java
Window<Customer> window = repository.findBy(
    spec,
    query -> query
        .sortBy(Sort.by(
            Sort.Order.asc("createdDate"),
            Sort.Order.asc("id")
        ))
        .scroll(ScrollPosition.keyset())
);
~~~

Scrolling hữu ích khi xử lý tập dữ liệu lớn theo từng window mà không cần tổng số bản ghi. Keyset yêu cầu thứ tự ổn định, sort key không null và projection chứa các trường sort cần thiết.

Scroll API hỗ trợ query methods, Query by Example và Querydsl theo tài liệu hiện hành; string-based query methods như các truy vấn khai báo bằng `@Query` và stored `@Procedure` không hỗ trợ scrolling. Fluent Query trên Specification là một cách để dùng scrolling với predicate động.

## 21. Fluent Query object chỉ có hiệu lực trong callback

Một lỗi thiết kế thường gặp là cố lưu đối tượng query trung gian:

~~~java
// Không làm theo cách này.
var fluentQuery = repository.findBy(spec, query -> query);
~~~

`findBy` yêu cầu callback trả về một kết quả đã được thực thi, ví dụ List, Page, Optional, count hoặc boolean. Đối tượng fluent query chỉ hợp lệ trong thời gian gọi `findBy`; không trả chính đối tượng query ra ngoài để dùng sau đó.

Cách đúng:

~~~java
List<Customer> customers = repository.findBy(
    spec,
    query -> query
        .sortBy(Sort.by("id").ascending())
        .all()
);
~~~

Callback phải gọi một terminal operation và trả kết quả tương ứng. Điều này bảo đảm query được thực thi trong phạm vi mà Spring Data quản lý.

## 22. Giới hạn phiên bản và cách chọn API

Fluent Query và các kiểu Specification được bổ sung theo từng phiên bản Spring Data JPA. Không nên giả định mọi dự án đều có cùng API.

| API | Mốc phiên bản | Ghi chú |
|---|---|---|
| `findAll(spec, pageable)` và `findAll(spec, sort)` | Có trong các dòng Spring Data JPA trước Fluent API | Lựa chọn tương thích rộng |
| `findBy(spec, queryFunction)` | Spring Data JPA 3.0 | Cung cấp fluent query cơ bản cho Specification |
| `SpecificationFluentQuery` và custom count specification | Spring Data JPA 3.5 | Bổ sung page với count Specification riêng |
| `PredicateSpecification` | Spring Data JPA 4.0 | Predicate API độc lập kiểu query, bên cạnh Specification truyền thống |
| `findBy(PredicateSpecification, queryFunction)` | Spring Data JPA 4.0 | Entry point fluent mới cho PredicateSpecification |

Khi dự án chưa hỗ trợ `findBy` fluent query, hãy dùng:

~~~java
Page<Customer> page = repository.findAll(spec, pageable);

List<Customer> sorted = repository.findAll(
    spec,
    Sort.by("fullName").ascending()
);
~~~

Trước khi dùng ví dụ Fluent API, kiểm tra phiên bản Spring Data JPA được Spring Boot BOM quản lý và API Javadoc tương ứng. Không nâng riêng một module Spring Data lên phiên bản khác BOM chỉ để lấy một method nếu chưa đánh giá tương thích giữa các module.

## 23. Các lỗi thường gặp và cách xử lý

### 23.1. Dùng tên cột database trong Sort

Sai nếu entity property là `createdDate` nhưng tên cột là `created_date`:

~~~java
Sort.by("created_date")
~~~

Đúng:

~~~java
Sort.by("createdDate")
~~~

`Sort` thường tham chiếu property path của domain model hoặc alias query, không phải tên cột SQL tùy ý.

### 23.2. Page có totalElements sai

Nguyên nhân thường là count query không cùng điều kiện nghiệp vụ với truy vấn nội dung, hoặc JOIN collection làm nhân số hàng. Kiểm tra `countSpec`/`countQuery` và bảo đảm đếm đúng entity gốc.

### 23.3. Kết quả trang bị lặp hoặc thiếu

Sort không ổn định, không có tie-breaker duy nhất hoặc dữ liệu thay đổi giữa các request có thể làm bản ghi dịch chuyển. Thêm khóa duy nhất vào sort; với tập lớn cần duyệt ổn định, cân nhắc keyset hoặc snapshot phù hợp.

### 23.4. Dùng Page khi không cần tổng số

Page có thể gây thêm chi phí count. Nếu chỉ cần biết còn trang sau, dùng Slice. Nếu chỉ cần nội dung của một phạm vi, dùng List với Pageable. Nếu cần xử lý dữ liệu lớn tuần tự, cân nhắc Window/Scroll API.

### 23.5. Sort động từ request không được kiểm soát

Không truyền chuỗi tùy ý của client vào biểu thức sort hoặc `JpaSort.unsafe()`. Hãy ánh xạ sang danh sách property được cho phép.

### 23.6. Gọi fluent terminal method sai chỗ

Đừng trả đối tượng fluent query từ callback hoặc lưu lại để sử dụng sau. Gọi `all()`, `page()`, `first()`, `count()` hoặc terminal method thích hợp ngay bên trong callback.

### 23.7. Gọi API không có trong dependency hiện tại

Lỗi compile khi không tìm thấy `findBy`, `SpecificationFluentQuery` hoặc `PredicateSpecification` thường là dấu hiệu phiên bản Spring Data JPA không hỗ trợ API đó. Kiểm tra dependency tree và BOM trước khi thay đổi code.

## 24. Kiểm thử phân trang, sort và Fluent Query

Nên kiểm tra cả nội dung và metadata của kết quả.

Ví dụ test repository:

~~~java
@DataJpaTest
class CustomerSpecificationPagingTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void returnsSecondPageInStableOrder() {
        repository.save(new Customer("An", CustomerStatus.ACTIVE));
        repository.save(new Customer("Binh", CustomerStatus.ACTIVE));
        repository.save(new Customer("Chi", CustomerStatus.ACTIVE));
        repository.flush();

        Specification<Customer> spec =
            CustomerSpecifications.hasStatus(CustomerStatus.ACTIVE);

        Page<Customer> page = repository.findAll(
            spec,
            PageRequest.of(
                1,
                2,
                Sort.by("fullName").ascending()
                    .and(Sort.by("id").ascending())
            )
        );

        assertThat(page.getContent()).hasSize(1);
        assertThat(page.getContent().get(0).getFullName())
            .isEqualTo("Chi");
        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }
}
~~~

Ví dụ minh họa cấu trúc test; constructor, getter, enum, imports và entity mapping cần khớp với dự án. Nếu test dùng database thật, bảo đảm dữ liệu seed và thứ tự sắp xếp rõ ràng.

Các trường hợp nên kiểm tra:

1. Trang đầu, trang giữa và trang cuối.
2. Trang vượt quá số trang hiện có.
3. Page content và totalElements.
4. Slice.hasNext() đúng khi còn hoặc hết dữ liệu.
5. Sort nhiều thuộc tính, chiều tăng/giảm và tie-breaker.
6. Tham số lọc null/rỗng.
7. Specification AND/OR cho ra đúng tập bản ghi.
8. Count specification giữ đúng điều kiện lọc.
9. Projection trả đúng kiểu và trường.
10. Fluent first, one, count, exists xử lý đúng trường hợp 0, 1 và nhiều kết quả.
11. Sort request không hợp lệ bị từ chối hoặc chuyển về mặc định.
12. Kiểm tra SQL và execution plan nếu truy vấn có JOIN hoặc count chậm.

## 25. Quy trình chọn cách truy vấn

Khi xây dựng chức năng tìm kiếm, có thể chọn theo nhu cầu:

1. Dùng `Specification` để ghép các bộ lọc động.
2. Dùng `Sort` nếu chỉ cần sắp xếp; dùng `Pageable` nếu cần thêm phạm vi trang.
3. Dùng `Page<T>` khi giao diện cần tổng số; dùng `Slice<T>` khi chỉ cần biết còn trang; dùng `List<T>` với Pageable khi chỉ cần nội dung trang.
4. Dùng `findAll(spec, pageable)` nếu cách truy vấn thông thường đã đủ.
5. Dùng `findBy(spec, query -> ...)` khi cần projection, limit, sort và terminal operation kết hợp tại một điểm.
6. Từ Spring Data JPA 3.5, cân nhắc custom count specification khi count query cần logic riêng.
7. Từ Spring Data JPA 4.0, cân nhắc `PredicateSpecification` cho predicate độc lập query type nếu dự án đã dùng phiên bản đó.
8. Dùng thứ tự ổn định với khóa duy nhất làm tie-breaker.
9. Kiểm thử nội dung, metadata, count và hiệu năng trên database mục tiêu.

## 26. Ghi nhớ

- `Pageable` mô tả trang, kích thước và có thể chứa Sort; chỉ số trang bắt đầu từ 0.
- `Page<T>` cung cấp tổng số phần tử/trang và thường cần count query.
- `Slice<T>` chỉ cần biết có trang tiếp theo; `List<T>` với Pageable không tạo metadata tổng.
- `Sort` dùng property path của entity hoặc alias query, không dùng tùy tiện tên cột SQL.
- Thêm khóa duy nhất vào cuối sort để tạo thứ tự ổn định khi phân trang.
- `JpaSort.unsafe()` chỉ dùng với biểu thức cố định, đáng tin cậy; không đưa trực tiếp input client vào.
- `JpaSpecificationExecutor` hỗ trợ `findAll(spec, pageable)` và `findAll(spec, sort)` ngay cả khi dự án chưa có Fluent Query.
- Fluent `findBy(spec, queryFunction)` có từ Spring Data JPA 3.0; `SpecificationFluentQuery` với custom count specification có từ 3.5; `PredicateSpecification` có từ 4.0.
- Fluent Query có các thao tác trung gian `sortBy`, `limit`, `as`, `project` và thao tác kết thúc như `all`, `first`, `one`, `page`, `slice`, `scroll`, `stream`, `count`, `exists`.
- Query object chỉ có hiệu lực trong callback; callback phải trả về kết quả đã thực thi.
- Count specification phải giữ cùng ngữ nghĩa lọc với truy vấn nội dung.
- Với tập lớn, xem xét scrolling/keyset thay vì phân trang offset sâu.

Kết hợp Specification, Pageable và Sort giúp xây dựng tìm kiếm động có phân trang rõ ràng. Khi phiên bản hỗ trợ Fluent Query, có thể điều khiển projection, sort, limit và kiểu kết quả trong cùng callback. Hãy chọn API theo phiên bản Spring Data JPA của dự án, giữ thứ tự ổn định và kiểm tra cả nội dung lẫn count query.

## Tài liệu tham khảo

- [Spring Data JPA — Specifications and Fluent API](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Spring Data JPA — Query Methods, Sorting and Pagination](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [JpaSpecificationExecutor API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaSpecificationExecutor.html)
- [SpecificationFluentQuery API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaSpecificationExecutor.SpecificationFluentQuery.html)