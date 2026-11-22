# Đánh giá API Limit, scrolling và Specification theo phiên bản Spring Data JPA

Spring Data JPA bổ sung API qua nhiều release train. Một số khả năng quen thuộc như Pageable và Specification đã tồn tại lâu; những API mới hơn như ScrollPosition/Window, Limit, PredicateSpecification và các fluent query operations chỉ xuất hiện ở những phiên bản nhất định.

Khi đánh giá một API mới, cần kiểm tra ba việc: phiên bản Spring Data Commons và Spring Data JPA mà ứng dụng thực sự chạy, khả năng của repository/query type đang dùng, và chi phí thực thi ở database. Không nên chỉ dựa vào ví dụ trên tài liệu mới nhất rồi đưa thẳng vào dự án cũ.

Bài học này tập trung vào ba nhóm API:

- Limit: giới hạn số kết quả động theo từng lần gọi.
- Scrolling: đọc tập kết quả lớn theo từng Window bằng offset hoặc keyset.
- Specification: xây dựng và kết hợp predicate động; phân biệt Specification truyền thống với PredicateSpecification và các API mới ở Spring Data JPA 4.x.

## 1. Xác định phiên bản trước khi dùng API

Spring Data JPA phụ thuộc Spring Data Commons. Nhiều kiểu dữ liệu như Limit, ScrollPosition, Window và WindowIterator được định nghĩa trong Spring Data Commons, sau đó module JPA tích hợp chúng với query JPA.

Trong ứng dụng Spring Boot, version thường được quản lý qua dependency management/BOM. Trước khi nâng cấp, kiểm tra:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-jpa --configuration runtimeClasspath
~~~

Cần xác định version thực tế của ít nhất:

- spring-data-jpa.
- spring-data-commons.
- spring-boot-dependencies hoặc BOM tương ứng.
- Hibernate ORM và Jakarta Persistence provider.

Không nâng riêng spring-data-jpa lên một version mới nếu BOM của Spring Boot vẫn quản lý release train cũ. Các module Spring Data cùng release train được kiểm thử và phát hành tương thích với nhau.

Tại thời điểm biên soạn, tài liệu Spring Data JPA công bố dòng 4.1.x là stable mới nhất; ví dụ dưới đây chỉ dùng API có mốc phiên bản được nêu rõ. Hãy kiểm tra patch version và ma trận tương thích trong tài liệu chính thức trước khi thay đổi build.

## 2. Bản đồ API theo phiên bản

Các mốc quan trọng:

| API | Mốc xuất hiện | Ý nghĩa |
|---|---:|---|
| Pageable, Page, Slice | Có từ các dòng Spring Data cũ | Phân trang theo offset |
| ScrollPosition, Window, WindowIterator | Spring Data 3.1 | Cuộn kết quả theo từng cửa sổ |
| Limit | Spring Data 3.2 | Truyền giới hạn động vào query method |
| Specification.unrestricted() | Spring Data JPA 3.5.2 | Specification không đóng góp predicate |
| Specification.where(Specification) nullable | Deprecated từ 3.5, bỏ hỗ trợ null ở 4.0 | Không tiếp tục dùng null để biểu diễn điều kiện rỗng |
| PredicateSpecification | Spring Data JPA 4.0 | Predicate độc lập loại query |
| UpdateSpecification, DeleteSpecification | Spring Data JPA 4.0 | Predicate gắn với CriteriaUpdate/CriteriaDelete |
| SpecificationFluentQuery mở rộng | Spring Data JPA 4.x | Limit, projection, page, slice, scroll, stream trong fluent API |

Một API xuất hiện trong Spring Data Commons chưa chắc mọi Spring Data module đều hỗ trợ giống nhau. Ví dụ Scroll API có ở hạ tầng chung, nhưng Spring Data JPA có giới hạn với một số loại query cụ thể. Luôn đọc phần store-specific trong tài liệu Spring Data JPA.

## 3. Limit giải quyết nhu cầu gì?

Limit biểu diễn số lượng kết quả tối đa mà query được phép trả về. Khác với Pageable, Limit không yêu cầu page number, offset hay tổng số trang.

Ví dụ repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<Customer> findByStatus(
        CustomerStatus status,
        Limit limit
    );
}
~~~

Caller chọn giới hạn tại thời điểm gọi:

~~~java
List<Customer> firstTwenty =
    repository.findByStatus(
        CustomerStatus.ACTIVE,
        Limit.of(20)
    );

List<Customer> allActive =
    repository.findByStatus(
        CustomerStatus.ACTIVE,
        Limit.unlimited()
    );
~~~

Limit thuộc package org.springframework.data.domain. Nó là tham số đặc biệt được Spring Data nhận diện, không phải property của entity và không được bind thành điều kiện WHERE.

Dùng Limit khi API cần giới hạn động theo request, ví dụ lấy tối đa 10 gợi ý autocomplete hoặc tối đa 100 bản ghi cho một tác vụ xử lý.

## 4. Limit khác Top và First thế nào?

Spring Data đã hỗ trợ keyword Top và First trong tên query method từ lâu:

~~~java
List<Customer> findTop10ByStatusOrderByCreatedAtDesc(
    CustomerStatus status
);

Optional<Customer> findFirstByEmailOrderByCreatedAtDesc(
    String email
);
~~~

Top/First biểu diễn giới hạn cố định trong tên method. Limit cho phép truyền giá trị động:

~~~java
List<Customer> findByStatusOrderByCreatedAtDesc(
    CustomerStatus status,
    Limit limit
);
~~~

So sánh:

| Cách | Giới hạn | Phù hợp |
|---|---|---|
| Top10/First10 | Cố định trong method name | Quy tắc luôn giống nhau |
| Limit.of(n) | Động theo lần gọi | Client/service chọn giới hạn |
| Pageable | Động cả page size và offset | Màn hình phân trang |
| Scroll Window | Đọc nhiều chunk và tiếp tục từ vị trí | Batch/export/đọc dữ liệu lớn |

Không kết hợp keyword Top/First với tham số Limit trong cùng query method. Chọn một nơi định nghĩa giới hạn để tránh hai giới hạn cạnh tranh nhau.

## 5. Quy tắc kết hợp Limit với Sort và Pageable

Limit có thể kết hợp với Sort:

~~~java
List<Customer> findByStatus(
    CustomerStatus status,
    Sort sort,
    Limit limit
);
~~~

Ví dụ:

~~~java
List<Customer> newest = repository.findByStatus(
    CustomerStatus.ACTIVE,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    ),
    Limit.of(50)
);
~~~

Không truyền null cho tham số đặc biệt. Nếu không muốn sort hoặc giới hạn, dùng:

- Sort.unsorted().
- Limit.unlimited().
- Pageable.unpaged() khi method nhận Pageable.

Không kết hợp Pageable và Limit trong cùng method vì Pageable đã chứa page size/offset. Tương tự, Pageable đã có Sort nên không truyền thêm Sort riêng. Top/First có thể dùng cùng Pageable; keyword đặt mức trần tổng thể, còn Pageable điều khiển page bên trong mức trần đó.

## 6. Limit không tạo metadata phân trang

Method trả List với Limit chỉ trả danh sách đã bị giới hạn. Nó không cung cấp:

- Tổng số bản ghi phù hợp.
- Tổng số trang.
- Trang hiện tại.
- Có trang tiếp theo hay không.

Nếu giao diện cần totalElements và totalPages, dùng Page. Nếu chỉ cần biết có kết quả tiếp theo, dùng Slice. Nếu cần xử lý liên tục theo vị trí mà không cần count tổng, xem xét Scroll API.

Không gọi count query riêng chỉ để hiển thị metadata nếu nghiệp vụ không cần. Count trên bảng lớn hoặc query nhiều join có thể đắt hơn phần truy vấn dữ liệu.

## 7. Scroll API gồm những thành phần nào?

Scroll API được thiết kế để đọc một tập kết quả lớn thành nhiều Window nhỏ.

Các thành phần chính:

- Window<T>: một cửa sổ kết quả hiện tại.
- ScrollPosition: vị trí để tiếp tục đọc.
- OffsetScrollPosition: vị trí theo offset.
- KeysetScrollPosition: vị trí dựa trên giá trị của các cột sắp xếp.
- WindowIterator<T>: iterator tự quản lý việc gọi các Window tiếp theo.

Một query scrolling cần có:

1. Điều kiện lọc ổn định.
2. Thứ tự sắp xếp xác định.
3. Kích thước mỗi Window.
4. ScrollPosition để bắt đầu hoặc tiếp tục.

Scroll không yêu cầu tính tổng số bản ghi. Vì vậy, nó phù hợp cho export, đồng bộ dữ liệu, batch job hoặc đọc nhiều bản ghi để xử lý nền.

## 8. Khai báo query method trả Window

Ví dụ đọc Customer theo trạng thái, mỗi lần tối đa 100 bản ghi:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Window<Customer> findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        CustomerStatus status,
        ScrollPosition position
    );
}
~~~

Lần đầu:

~~~java
Window<Customer> window =
    repository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        CustomerStatus.ACTIVE,
        ScrollPosition.offset()
    );
~~~

Window chứa tối đa 100 Customer và cung cấp vị trí để lấy cửa sổ tiếp theo.

Có thể dùng WindowIterator để không phải tự viết vòng lặp kiểm tra hasNext và cập nhật ScrollPosition:

~~~java
WindowIterator<Customer> customers = WindowIterator
    .of(position ->
        repository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
            CustomerStatus.ACTIVE,
            position
        )
    )
    .startingAt(ScrollPosition.offset());

while (customers.hasNext()) {
    Customer customer = customers.next();
    process(customer);
}
~~~

Ví dụ giả định process(Customer) là method xử lý của ứng dụng. WindowIterator giữ vị trí cuộn và gọi repository để lấy các Window tiếp theo.

## 9. Offset scrolling

Offset scrolling xác định vị trí bằng số hàng đã bỏ qua.

Ví dụ:

~~~java
Window<Customer> first =
    repository.findFirst100ByStatusOrderByIdAsc(
        CustomerStatus.ACTIVE,
        ScrollPosition.offset()
    );

Window<Customer> next =
    repository.findFirst100ByStatusOrderByIdAsc(
        CustomerStatus.ACTIVE,
        first.positionAt(first.size() - 1)
    );
~~~

ScrollPosition.offset() biểu diễn bắt đầu từ đầu tập kết quả.

Điểm dễ nhầm: ScrollPosition là vị trí exclusive. ScrollPosition.offset(0) chỉ đến phần tử ở offset 0 và lần truy vấn tiếp theo bắt đầu sau phần tử đó, nên có thể bỏ qua phần tử đầu tiên. Khi bắt đầu từ đầu, dùng ScrollPosition.offset() thay vì offset(0).

Offset scrolling dễ hiểu và phù hợp với tập dữ liệu vừa phải. Nhưng ở offset rất lớn, database vẫn phải xử lý hoặc bỏ qua nhiều hàng trước khi trả Window tiếp theo. Chi phí có thể tăng theo độ sâu.

## 10. Keyset scrolling

Keyset scrolling dùng giá trị của các cột sắp xếp ở phần tử cuối Window hiện tại để tiếp tục.

Ví dụ sort theo createdAt rồi id:

~~~java
Window<Customer> findFirst100ByStatusOrderByCreatedAtAscIdAsc(
    CustomerStatus status,
    ScrollPosition position
);
~~~

Bắt đầu:

~~~java
Window<Customer> window =
    repository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        CustomerStatus.ACTIVE,
        ScrollPosition.keyset()
    );
~~~

Tiếp tục từ phần tử cuối:

~~~java
ScrollPosition nextPosition =
    window.positionAt(window.size() - 1);

Window<Customer> next =
    repository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        CustomerStatus.ACTIVE,
        nextPosition
    );
~~~

Về mặt logic, nếu phần tử cuối có createdAt = T và id = 500, truy vấn tiếp theo tìm các hàng sau khóa sắp xếp đó:

~~~sql
WHERE status = 'ACTIVE'
  AND (
       created_at > :lastCreatedAt
       OR (created_at = :lastCreatedAt AND id > :lastId)
  )
ORDER BY created_at ASC, id ASC
FETCH FIRST 100 ROWS ONLY
~~~

Đây là minh họa logic keyset. SQL thật được Spring Data JPA và Hibernate sinh theo database dialect.

Keyset tránh phải bỏ qua hàng nghìn offset ở các trang sâu. Database có thể dùng index trên các cột sắp xếp để tìm điểm tiếp tục.

## 11. Điều kiện để keyset scrolling hoạt động đúng

Keyset cần một thứ tự ổn định và có thể xác định duy nhất vị trí.

Các nguyên tắc:

- Các property dùng để sort phải được ánh xạ trong entity.
- Giá trị sort nên không null; keyset filtering không hỗ trợ tốt property nullable do semantics so sánh NULL khác nhau giữa database.
- Projection phải chứa các property cần để tái tạo keyset.
- Nên có index phù hợp với điều kiện lọc và thứ tự sort.
- Thứ tự cần có khóa duy nhất. Spring Data có thể bổ sung primary key để bảo đảm tính duy nhất, nhưng cần hiểu query và projection thực tế.
- Nếu giá trị sort thay đổi trong lúc cuộn, bản ghi có thể di chuyển vị trí và gây thiếu hoặc lặp trong quá trình đọc.

Ví dụ index phù hợp cho query theo status và sort theo createdAt, id có thể là composite index trên (status, created_at, id). Cấu trúc index cuối cùng phải dựa trên execution plan và workload.

## 12. Offset và keyset: chọn cách nào?

| Tiêu chí | Offset | Keyset |
|---|---|---|
| Vị trí tiếp tục | Số hàng đã bỏ qua | Giá trị sort key cuối cùng |
| Độ sâu lớn | Có thể chậm | Thường ổn định hơn nếu có index |
| Yêu cầu sort | Cần sort ổn định | Cần sort ổn định và key phù hợp |
| Property nullable | Dễ xử lý hơn | Có giới hạn, nên dùng key không null |
| Dịch chuyển dữ liệu | Offset có thể bỏ sót/lặp khi dữ liệu đổi | Ít nhạy hơn với insert trước vị trí, nhưng update sort key vẫn có thể dịch chuyển |
| Độ phức tạp | Thấp | Cao hơn, cần thiết kế key/index |

Dùng offset khi người dùng cần nhảy đến trang bất kỳ hoặc tập dữ liệu không quá lớn. Dùng keyset khi đọc tuần tự qua tập dữ liệu lớn và database có index phù hợp.

Keyset không phải snapshot transaction tự động. Nếu dữ liệu thay đổi trong khi batch chạy, cần xác định chính sách nhất quán, ví dụ cố định khoảng thời gian, watermark hoặc transaction phù hợp.

## 13. Giới hạn hỗ trợ scrolling trong Spring Data JPA

Scroll API không hoạt động với mọi kiểu query.

Theo tài liệu Spring Data JPA hiện hành:

- Có thể dùng với query method được derive từ tên.
- Có thể dùng với Query by Example.
- Có thể dùng với Querydsl.
- Spring Data JPA 4.x hỗ trợ scrolling qua fluent Specification query.
- Scrolling với string-based query methods khai báo bằng @Query hiện chưa được hỗ trợ.
- Stored @Procedure query methods cũng không hỗ trợ scrolling.

Nếu cần scrolling cho query có JPQL phức tạp, native SQL hoặc procedure, cân nhắc custom repository dùng EntityManager/JdbcTemplate và cơ chế cursor/seek riêng. Không giả định chỉ cần đổi return type từ List sang Window là @Query sẽ cuộn được.

## 14. Window khác Stream thế nào?

Window là abstraction phân đoạn query bằng nhiều lần thực thi. Mỗi lần gọi trả một chunk hữu hạn và vị trí tiếp tục.

Stream<T> có thể giữ tài nguyên JDBC/result set mở trong khi tiêu thụ. Phải đóng Stream bằng try-with-resources:

~~~java
try (Stream<Customer> stream = repository.streamAllByStatus(
        CustomerStatus.ACTIVE)) {
    stream.forEach(this::process);
}
~~~

Không phải mọi query method hoặc provider đều hỗ trợ stream theo cùng cách. Stream không thay thế Scroll API khi cần lưu vị trí tiếp tục, chia chunk qua nhiều request hoặc xử lý lại từ một keyset.

Với batch dài, Window thường dễ kiểm soát memory và transaction boundary hơn vì mỗi chunk có thể được xử lý trong một đơn vị công việc riêng.

## 15. Specification truyền thống

Specification là abstraction của Spring Data JPA để biểu diễn predicate dựa trên Criteria API.

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
~~~

Specification truyền thống:

~~~java
public static Specification<Customer> hasStatus(
        CustomerStatus status) {

    return (root, query, cb) ->
        status == null
            ? null
            : cb.equal(root.get(Customer_.status), status);
}
~~~

Ba tham số:

- Root<T>: entity root đang truy vấn.
- CriteriaQuery<?>: query tổng thể; có thể dùng để tạo subquery hoặc điều chỉnh query-level behavior.
- CriteriaBuilder: tạo predicate như equal, like, greaterThan, and, or, isNull.

Specification phù hợp khi cần predicate gắn với query cụ thể, hoặc cần dùng CriteriaQuery để xây subquery, distinct hay logic query-bound.

## 16. PredicateSpecification trong Spring Data JPA 4.0

Spring Data JPA 4.0 bổ sung PredicateSpecification, một API nhỏ hơn và không gắn với loại query cụ thể.

~~~java
public static PredicateSpecification<Customer> hasStatus(
        CustomerStatus status) {

    return (from, cb) ->
        status == null
            ? null
            : cb.equal(from.get(Customer_.status), status);
}
~~~

Chữ ký:

~~~java
public interface PredicateSpecification<T> {
    Predicate toPredicate(
        From<?, T> from,
        CriteriaBuilder builder
    );
}
~~~

PredicateSpecification chỉ nhận From và CriteriaBuilder. Nó phù hợp cho điều kiện độc lập với query type, có thể tái sử dụng giữa các thao tác truy vấn.

Vì không nhận CriteriaQuery, PredicateSpecification không tự tạo subquery hoặc điều chỉnh query-level selection/order. Nếu logic cần CriteriaQuery, dùng Specification truyền thống.

## 17. So sánh Specification và PredicateSpecification

| Tiêu chí | PredicateSpecification | Specification |
|---|---|---|
| Có từ | Spring Data JPA 4.0 | Các dòng Spring Data JPA cũ hơn |
| Tham số | From, CriteriaBuilder | Root, CriteriaQuery, CriteriaBuilder |
| Phạm vi | Query-type-agnostic | Query-bound |
| Dùng cho | Predicate đơn giản, tái sử dụng | Predicate cần query context |
| Subquery | Không có CriteriaQuery trực tiếp | Có thể dùng CriteriaQuery.subquery |
| Composition | and/or/not | and/or/not |
| Executor | JpaSpecificationExecutor ở 4.x | JpaSpecificationExecutor |

Không cần chuyển mọi Specification sang PredicateSpecification. Nếu implementation đang dùng CriteriaQuery hoặc subquery, giữ Specification là hợp lý. Với các điều kiện đơn giản như status, email, ngày tạo, PredicateSpecification giúp code ít phụ thuộc hơn.

## 18. UpdateSpecification và DeleteSpecification trong 4.0

Spring Data JPA 4.0 bổ sung các kiểu Specification gắn với CriteriaUpdate và CriteriaDelete:

~~~java
public interface UpdateSpecification<T> {
    Predicate toPredicate(
        Root<T> root,
        CriteriaUpdate<T> update,
        CriteriaBuilder builder
    );
}

public interface DeleteSpecification<T> {
    Predicate toPredicate(
        Root<T> root,
        CriteriaDelete<T> delete,
        CriteriaBuilder builder
    );
}
~~~

Các kiểu này phản ánh đúng loại query cần thực hiện:

- Specification: select query.
- UpdateSpecification: bulk update query.
- DeleteSpecification: bulk delete query.

Đây là API hữu ích khi muốn tái sử dụng điều kiện filter cho truy vấn cập nhật hoặc xóa theo Criteria API.

Bulk update/delete có semantics khác việc tải entity rồi gọi setter/remove: chúng không đồng bộ tự động các entity đang nằm trong persistence context. Sau bulk operation, cần cân nhắc flush/clear/refresh để tránh đọc trạng thái cũ.

## 19. Specification.unrestricted() và thay đổi từ 3.5 sang 4.0

Trong các phiên bản cũ, code thường dùng null để biểu diễn Specification không có điều kiện:

~~~java
Specification<Customer> spec = null;
spec = spec == null ? nextSpec : spec.and(nextSpec);
~~~

Spring Data JPA 3.5 deprecate Specification.where(Specification) khi truyền null và cung cấp Specification.unrestricted() từ 3.5.2.

Cách viết mới:

~~~java
Specification<Customer> spec =
    Specification.unrestricted()
        .and(hasStatus(CustomerStatus.ACTIVE))
        .and(createdAfter(startTime));
~~~

unrestricted() trả về một Specification không đóng góp predicate. Nó không giống predicate TRUE được tạo bằng cb.conjunction() về mặt ý nghĩa composition; nó được loại khỏi phép kết hợp.

Ở Spring Data JPA 4.0, không tiếp tục truyền null vào Specification.where(Specification). Dùng unrestricted() để biểu diễn trường hợp không có filter.

Nếu đang nâng từ 3.4 hoặc thấp hơn, kiểm tra version vì unrestricted() chưa có ở các bản trước 3.5.2.

## 20. Kết hợp PredicateSpecification với Specification

Trong Spring Data JPA 4.0, hai loại có thể kết hợp với nhau.

Ví dụ:

~~~java
PredicateSpecification<Customer> isActive =
    (from, cb) -> cb.isTrue(from.get(Customer_.active));

Specification<Customer> createdAfter =
    (root, query, cb) ->
        cb.greaterThanOrEqualTo(
            root.get(Customer_.createdAt),
            startTime
        );

Specification<Customer> combined =
    createdAfter.and(isActive);
~~~

Điều này cho phép viết điều kiện đơn giản theo PredicateSpecification và giữ Specification cho phần cần query context.

Đừng chuyển đổi qua lại một cách máy móc. Chọn abstraction nhỏ nhất đáp ứng nhu cầu của predicate; chỉ dùng query-bound Specification khi cần query context.

## 21. SpecificationFluentQuery trong 4.x

JpaSpecificationExecutor cung cấp fluent API qua method findBy:

~~~java
Page<CustomerSummary> page = repository.findBy(
    combined,
    query -> query
        .as(CustomerSummary.class)
        .page(PageRequest.of(
            0,
            20,
            Sort.by("createdAt").descending()
        ))
);
~~~

Fluent API cho phép cấu hình kết quả ngay tại nơi gọi:

- sortBy: thêm thứ tự.
- limit: giới hạn số kết quả.
- as: chọn projection/result type.
- project: giới hạn property được đọc khi phù hợp.
- first/firstValue: lấy phần tử đầu.
- one/oneValue: yêu cầu tối đa một kết quả.
- all: lấy toàn bộ kết quả.
- page: trả Page.
- slice: trả Slice.
- scroll: trả Window tiếp theo theo ScrollPosition.
- stream: trả Stream.
- count/exists: đếm hoặc kiểm tra tồn tại.

Ví dụ chỉ lấy 10 kết quả đầu:

~~~java
Optional<Customer> newest = repository.findBy(
    combined,
    query -> query
        .sortBy(Sort.by("createdAt").descending())
        .limit(10)
        .first()
);
~~~

Ví dụ cuộn theo keyset:

~~~java
Window<Customer> window = repository.findBy(
    combined,
    query -> query
        .sortBy(Sort.by("createdAt").ascending())
        .limit(100)
        .scroll(ScrollPosition.keyset())
);
~~~

Các intermediate và terminal operation phải được gọi bên trong query function. Không trả query object ra ngoài callback để dùng sau.

## 22. Chọn Page, Slice, Limit hay Window

| Nhu cầu | API | Count query |
|---|---|---|
| Trang 1, 2, 3 và cần tổng trang | Page + Pageable | Có thể cần |
| Chỉ cần biết còn trang sau | Slice + Pageable | Không cần total count |
| Lấy tối đa N kết quả | Limit | Không |
| Đọc tuần tự nhiều chunk, có vị trí tiếp tục | Window + ScrollPosition | Không |
| Đọc theo thứ tự khóa để xử lý batch lớn | Keyset Window | Không |
| Chỉ lấy một bản ghi tốt nhất | First/Top hoặc fluent first | Không cần total count |

Page tiện cho giao diện nhưng count query có thể tốn kém. Slice và Window phù hợp cho điều hướng/đọc tiếp. Limit phù hợp cho giới hạn động đơn giản.

Không dùng Page chỉ vì method đang trả về danh sách; hãy xác định giao diện có thật sự cần tổng số trang hay không.

## 23. Ví dụ kết hợp Specification với Limit

Trong Spring Data JPA 4.x, có thể dùng fluent API:

~~~java
List<Customer> topCustomers = repository.findBy(
    hasStatus(CustomerStatus.ACTIVE),
    query -> query
        .sortBy(Sort.by("createdAt").descending())
        .limit(25)
        .all()
);
~~~

Với derived query method, dùng Limit trực tiếp:

~~~java
List<Customer> findByStatus(
    CustomerStatus status,
    Sort sort,
    Limit limit
);
~~~

Cả hai cách đều tránh phải khai báo nhiều method chỉ khác nhau ở con số giới hạn.

Nếu cần một page có total, dùng page(Pageable) thay vì limit().all().

## 24. Kết hợp Specification với scrolling

Fluent Specification query trong Spring Data JPA 4.x có thể dùng scroll:

~~~java
Window<Customer> firstWindow = repository.findBy(
    hasStatus(CustomerStatus.ACTIVE),
    query -> query
        .sortBy(Sort.by("id").ascending())
        .limit(500)
        .scroll(ScrollPosition.keyset())
);
~~~

Nếu cần duyệt toàn bộ dữ liệu, dùng WindowIterator hoặc vòng lặp quản lý ScrollPosition. Với query method derive, dùng method trả Window như các ví dụ trước.

String-based @Query methods hiện chưa hỗ trợ Scroll API trong Spring Data JPA. Nếu query phức tạp không thể biểu diễn bằng derived method, Specification hoặc Querydsl, cân nhắc custom repository.

## 25. Ví dụ Specification cho filter động

DTO:

~~~java
public record CustomerFilter(
    CustomerStatus status,
    Boolean active,
    Instant createdFrom,
    Instant createdTo
) {
}
~~~

PredicateSpecification cho điều kiện đơn giản:

~~~java
public final class CustomerPredicates {

    private CustomerPredicates() {
    }

    public static PredicateSpecification<Customer> hasStatus(
            CustomerStatus status) {
        return (from, cb) -> status == null
            ? null
            : cb.equal(from.get(Customer_.status), status);
    }

    public static PredicateSpecification<Customer> isActive(
            Boolean active) {
        return (from, cb) -> active == null
            ? null
            : cb.equal(from.get(Customer_.active), active);
    }
}
~~~

Specification cho khoảng ngày:

~~~java
public static Specification<Customer> createdBetween(
        Instant from,
        Instant to) {

    return (root, query, cb) -> {
        List<Predicate> predicates = new ArrayList<>();

        if (from != null) {
            predicates.add(
                cb.greaterThanOrEqualTo(
                    root.get(Customer_.createdAt),
                    from
                )
            );
        }

        if (to != null) {
            predicates.add(
                cb.lessThan(root.get(Customer_.createdAt), to)
            );
        }

        return predicates.isEmpty()
            ? null
            : cb.and(predicates.toArray(Predicate[]::new));
    };
}
~~~

Kết hợp:

~~~java
Specification<Customer> specification =
    Specification.unrestricted()
        .and(CustomerPredicates.hasStatus(filter.status()))
        .and(CustomerPredicates.isActive(filter.active()))
        .and(createdBetween(
            filter.createdFrom(),
            filter.createdTo()
        ));
~~~

Ví dụ dùng metamodel Customer_ để tránh viết tên property dạng chuỗi. Cần sinh static metamodel trong build hoặc thay bằng root.get("property") nếu dự án chưa cấu hình metamodel processor.

## 26. Kiểm tra semantics của Specification rỗng

Một Specification có thể trả null từ toPredicate để không đóng góp điều kiện. Specification.unrestricted() biểu diễn trạng thái đó rõ ràng.

Cần phân biệt:

- Không có filter: trả unrestricted hoặc bỏ qua điều kiện.
- Muốn trả tất cả bản ghi trong phạm vi query: unrestricted có thể phù hợp.
- Muốn trả không có bản ghi: tạo predicate FALSE bằng cb.disjunction().
- Danh sách filter OR rỗng: không tự suy ra ý nghĩa nghiệp vụ.

Trong Spring Data JPA, Specification.anyOf(emptyList) có thể trả unrestricted theo hợp đồng API. Điều này có nghĩa “không có Specification tham gia”, không có nghĩa “OR của tập rỗng phải trả false”. Nếu nghiệp vụ yêu cầu không có kết quả, tạo predicate false tường minh.

Đây là lỗi logic dễ xảy ra khi chuyển từ Specification cũ sang API composition mới.

## 27. Nâng cấp từ Spring Data JPA 3.x lên 4.x

Trước khi nâng cấp, kiểm tra:

1. Spring Boot/BOM có quản lý Spring Data JPA 4.x không.
2. Java và Spring Framework có đáp ứng yêu cầu release train mới không.
3. Hibernate ORM và Jakarta Persistence có tương thích không.
4. Code có dùng Specification.where(null) không.
5. Có thể thay các predicate đơn giản bằng PredicateSpecification không.
6. Có custom repository implementation phụ thuộc API nội bộ không.
7. Query method có dùng Limit, ScrollPosition hoặc Window chưa được hỗ trợ ở version cũ không.
8. Có string-based @Query nào đang được kỳ vọng dùng scrolling không.
9. Integration test có chạy trên database thật và provider tương ứng không.

Không nâng riêng một module Spring Data ngoài release train. Sau khi nâng, chạy compile và test toàn bộ repository để phát hiện thay đổi chữ ký, nullability, generic type và query behavior.

## 28. Những khác biệt cần chú ý giữa 3.1, 3.2, 3.5 và 4.0

| Phiên bản | Thay đổi đáng chú ý | Việc cần làm |
|---|---|---|
| 3.1 | ScrollPosition, Window, WindowIterator | Có thể thiết kế batch scroll thay vì offset page sâu |
| 3.2 | Limit | Dùng giới hạn động thay vì nhiều method TopN cố định |
| 3.5.0 | Specification.where(nullable) bị deprecate | Bắt đầu loại bỏ null Specification khỏi code |
| 3.5.2 | Specification.unrestricted() | Dùng API rõ ràng cho filter không áp dụng |
| 4.0 | PredicateSpecification, UpdateSpecification, DeleteSpecification | Tách predicate đơn giản khỏi query-bound Specification |
| 4.0 | Không chấp nhận null cho Specification.where(Specification) | Chuyển sang unrestricted() |
| 4.x | SpecificationFluentQuery hỗ trợ limit, projection, page, slice, scroll và stream | Tập trung cấu hình kết quả trong findBy callback |

Mốc phiên bản là mốc của Spring Data API, không phải phiên bản Spring Boot. Dùng BOM để biết Spring Boot đang kéo release train nào.

## 29. Hiệu năng và giới hạn thực thi

**Page và count query**

Page có thể cần count query để tính totalElements. Với query có join, distinct hoặc subquery, count query có thể tốn kém. Slice tránh count tổng.

**Offset scrolling**

Offset sâu có thể buộc database xử lý nhiều hàng bị bỏ qua. Không nên dùng offset page rất sâu cho batch hàng triệu bản ghi.

**Keyset scrolling**

Keyset cần sort ổn định, key không null và index phù hợp. Nếu sort theo nhiều cột, index nên phản ánh điều kiện lọc và thứ tự đó.

**Limit**

Limit giảm số hàng trả về nhưng không tự bảo đảm query nhanh. Nếu điều kiện lọc không có index, database vẫn có thể phải quét nhiều hàng trước khi tìm đủ N kết quả.

**Specification**

Specification tạo query động, nhưng không tự bảo đảm query plan tốt. Join collection, subquery, distinct và OR có thể làm query phức tạp. Kiểm tra SQL và EXPLAIN.

**Fluent projection**

Dùng as/project khi chỉ cần một phần dữ liệu. Projection có thể giảm dữ liệu đọc và tránh hydrate entity không cần thiết.

## 30. Kiểm thử Limit, scrolling và Specification

Nên có integration test trên database cùng loại với production cho các tính năng phụ thuộc sort, keyset, query translation hoặc count query.

Các trường hợp nên kiểm tra:

- Limit.of(10) trả tối đa 10 kết quả.
- Limit.unlimited() không giới hạn.
- Limit không nhận null.
- Sort ổn định khi nhiều bản ghi cùng giá trị sort.
- Top/First và Limit không bị khai báo cùng method.
- Pageable và Limit không bị kết hợp.
- Page totalElements chính xác.
- Slice.hasNext() chính xác.
- Window đầu tiên dùng ScrollPosition.offset() hoặc ScrollPosition.keyset().
- Vị trí tiếp theo không lặp phần tử cuối của Window trước.
- Offset(0) không vô tình bỏ qua phần tử đầu.
- Keyset hoạt động với property không null và index phù hợp.
- Projection chứa các trường sort cần cho keyset.
- String-based @Query không được kỳ vọng hỗ trợ scrolling.
- Specification.unrestricted() không thêm predicate.
- PredicateSpecification kết hợp đúng AND/OR.
- Specification có subquery vẫn dùng query context.
- UpdateSpecification/DeleteSpecification chỉ tác động đúng hàng.
- Empty anyOf/allOf tuân theo semantics API và nghiệp vụ.

## 31. Lỗi thường gặp và cách khắc phục

**1. Không tìm thấy class Limit**

Dự án có thể đang dùng Spring Data Commons thấp hơn 3.2. Kiểm tra dependency tree và release train.

**2. Không tìm thấy ScrollPosition hoặc Window**

Scroll API yêu cầu Spring Data Commons 3.1 trở lên và module store phải hỗ trợ. Kiểm tra version thực tế.

**3. Truyền null vào Limit hoặc Sort**

Dùng Limit.unlimited() và Sort.unsorted(). Các special parameter yêu cầu giá trị không null.

**4. Kết hợp Pageable với Limit**

Không hợp lệ vì Pageable đã chứa page size/limit. Chọn một abstraction.

**5. Dùng Top10 cùng Limit**

Không kết hợp hai cơ chế giới hạn trong cùng query method. Dùng Top10 cố định hoặc Limit động.

**6. Scrolling với @Query không hoạt động**

Spring Data JPA hiện chưa hỗ trợ scrolling cho string-based query methods. Chuyển sang derived method, Querydsl, Specification fluent API hoặc custom repository.

**7. Keyset bị thiếu hoặc lặp dữ liệu**

Kiểm tra sort có ổn định không, key có null không, projection có chứa sort properties không và dữ liệu sort có bị thay đổi trong lúc cuộn không.

**8. Offset scroll bỏ qua phần tử đầu**

Dùng ScrollPosition.offset() để bắt đầu. ScrollPosition.offset(0) là vị trí exclusive và có thể bỏ qua hàng đầu.

**9. Specification.where(null) lỗi sau khi nâng lên 4.0**

Thay bằng Specification.unrestricted() hoặc chỉ tạo Specification khi filter thực sự có giá trị.

**10. PredicateSpecification không compile trên 3.x**

PredicateSpecification được giới thiệu ở Spring Data JPA 4.0. Với 3.x, dùng Specification truyền thống.

**11. Specification không tạo query như mong muốn**

Kiểm tra toPredicate có trả null hay predicate thực tế, logic AND/OR và các join/subquery.

**12. Page rất chậm dù content query nhanh**

Xem count query riêng. Nếu không cần tổng số trang, chuyển sang Slice hoặc Window.

## 32. Quy trình đánh giá API mới

Khi cân nhắc dùng Limit, scrolling hoặc Specification:

1. Xác định version Spring Data JPA và Commons qua dependency tree.
2. Kiểm tra API có từ version nào và module JPA có hỗ trợ query type đang dùng không.
3. Xác định giao diện cần Page, Slice, Limit hay Window.
4. Nếu đọc batch lớn, đánh giá offset và keyset.
5. Chọn sort ổn định và index phù hợp cho keyset.
6. Nếu cần filter động, đánh giá Specification và PredicateSpecification.
7. Giữ Specification khi cần CriteriaQuery/subquery.
8. Dùng UpdateSpecification/DeleteSpecification nếu đang ở 4.0+ và cần bulk Criteria mutation.
9. Dùng Specification.unrestricted() thay cho null Specification.
10. Dùng fluent API để giới hạn, sort, projection và scroll theo use case.
11. Kiểm tra giới hạn của @Query string-based và @Procedure.
12. Viết integration test trên database mục tiêu.
13. Đo count query, offset sâu, keyset và projection.
14. Nâng cấp theo BOM/release train, không nâng riêng lẻ một module.

## 33. Checklist tự đánh giá

- [ ] Tôi biết kiểm tra version Spring Data JPA/Commons thực tế.
- [ ] Tôi biết Limit xuất hiện từ Spring Data 3.2.
- [ ] Tôi phân biệt Limit với Top/First và Pageable.
- [ ] Tôi biết Limit.unlimited() và không truyền null.
- [ ] Tôi biết không kết hợp Pageable với Limit.
- [ ] Tôi hiểu Page cần count, Slice không cần total count.
- [ ] Tôi biết ScrollPosition, Window và WindowIterator từ 3.1.
- [ ] Tôi phân biệt offset scrolling và keyset scrolling.
- [ ] Tôi biết dùng ScrollPosition.offset() để bắt đầu.
- [ ] Tôi hiểu ScrollPosition là exclusive.
- [ ] Tôi biết điều kiện sort/index/nullability cho keyset.
- [ ] Tôi biết string-based @Query và @Procedure có giới hạn scrolling.
- [ ] Tôi phân biệt Specification với PredicateSpecification.
- [ ] Tôi biết PredicateSpecification có từ Spring Data JPA 4.0.
- [ ] Tôi biết UpdateSpecification và DeleteSpecification.
- [ ] Tôi biết Specification.unrestricted() từ 3.5.2.
- [ ] Tôi không truyền null vào Specification.where trong 4.0.
- [ ] Tôi biết fluent Specification query có limit, projection, page, slice và scroll.
- [ ] Tôi kiểm thử semantics của anyOf/allOf khi danh sách rỗng.
- [ ] Tôi kiểm tra SQL, count query và execution plan.

## 34. Câu hỏi ôn tập

**1. Limit có từ phiên bản nào?**

Limit thuộc Spring Data Commons từ 3.2 và được các module hỗ trợ tích hợp vào query method.

**2. Limit khác Pageable thế nào?**

Limit chỉ đặt mức kết quả tối đa; Pageable có page size, offset và Sort, đồng thời có thể dùng để tạo Page metadata.

**3. Có thể kết hợp Pageable và Limit không?**

Không. Pageable đã chứa giới hạn và vị trí phân trang.

**4. Scroll API có từ khi nào?**

ScrollPosition, Window và WindowIterator được giới thiệu trong Spring Data 3.1; khả năng sử dụng cụ thể phụ thuộc store module.

**5. Offset và keyset khác nhau ra sao?**

Offset tiếp tục bằng số hàng đã bỏ qua; keyset tiếp tục từ giá trị các cột sort của hàng cuối cùng trong Window trước.

**6. Vì sao keyset cần sort key không null?**

So sánh với NULL có semantics khác nhau giữa database và làm khó tái tạo vị trí tiếp tục ổn định.

**7. Spring Data JPA có scroll được với mọi @Query không?**

Không. Scrolling với string-based @Query và stored @Procedure hiện chưa được hỗ trợ.

**8. PredicateSpecification có từ phiên bản nào?**

Spring Data JPA 4.0. Nó chỉ nhận From và CriteriaBuilder nên phù hợp với predicate không phụ thuộc query type.

**9. Khi nào vẫn cần Specification truyền thống?**

Khi cần CriteriaQuery, subquery hoặc logic phụ thuộc loại query. Specification truyền thống vẫn phù hợp cho các truy vấn phức tạp.

**10. Vì sao Specification.where(null) cần được thay thế?**

API nullable này bị deprecated từ 3.5 và không còn chấp nhận null ở 4.0. Dùng Specification.unrestricted() để biểu diễn không có điều kiện.

**11. Fluent Specification query giúp gì?**

Nó cho phép cấu hình sort, limit, projection và chọn kết quả dạng first/all/page/slice/scroll/stream ngay tại nơi gọi.

**12. Khi nào chọn Window thay vì Page?**

Khi xử lý dữ liệu theo từng chunk và không cần tổng số trang, đặc biệt khi dùng keyset để đọc tuần tự tập dữ liệu lớn.

Việc chọn API mới phải bắt đầu từ version thực tế và hình dạng truy vấn cần thực hiện. Limit phù hợp với mức trần động, Window phù hợp với việc đọc theo vị trí, còn Specification giúp tái sử dụng filter động. Khi phân biệt rõ các mốc 3.1, 3.2, 3.5 và 4.0, nhóm phát triển có thể nâng cấp có kiểm soát, tránh gọi API chưa tồn tại và chọn chiến lược truy vấn phù hợp với database.

## Tài liệu tham khảo

- [Spring Data JPA 4.1 — Query Methods and Scrolling](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Spring Data Commons — Defining Query Methods, Paging and Limiting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [Spring Data Commons — ScrollPosition API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/ScrollPosition.html)
- [Spring Data Commons — Limit API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/Limit.html)
- [Spring Data JPA 3.5 — Specification API and deprecations](https://docs.spring.io/spring-data/jpa/reference/3.5/api/java/org/springframework/data/jpa/domain/Specification.html)
