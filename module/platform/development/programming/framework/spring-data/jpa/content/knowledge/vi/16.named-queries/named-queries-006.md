# Áp dụng query hints và giới hạn phụ thuộc nhà cung cấp

## Mục tiêu

Query hint là một chỉ dẫn bổ sung gắn với một truy vấn JPA. Hint có thể yêu cầu provider áp dụng timeout, điều chỉnh cách tải dữ liệu, kiểm soát cache hoặc tối ưu cách đọc kết quả. Spring Data JPA cho phép gắn các hint vào repository method bằng `@QueryHints`; khi dùng trực tiếp EntityManager, có thể gọi `Query.setHint`.

Một số hint được chuẩn hóa bởi Jakarta Persistence, còn một số chỉ được Hibernate hoặc provider khác hỗ trợ. Hint mang tính hướng dẫn cho provider và driver; không phải mọi hint đều được thực hiện giống nhau trên mọi database.

Sau bài này, bạn có thể:

- Hiểu query hint tác động ở lớp nào và khác bind parameter ra sao.
- Khai báo JPA-standard hint và vendor-specific hint.
- Dùng `@QueryHints` trên Spring Data repository.
- Kiểm soát việc áp dụng hint cho count query của Page.
- Cấu hình query timeout, lock timeout, cache, fetch size và read-only.
- Phân biệt query hint với `@Transactional(readOnly = true)`, `@Lock` và `@EntityGraph`.
- Nhận biết giới hạn tương thích giữa JPA provider, JDBC driver và database.
- Kiểm thử để bảo đảm hint có tác dụng đúng và không trở thành điều kiện bắt buộc của nghiệp vụ.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA. Một số ví dụ Hibernate-specific cần được đối chiếu với đúng phiên bản Hibernate mà Spring Boot quản lý.

## 1. Query hint là gì?

JPA query có thể được cấu hình bằng các thuộc tính bổ sung ngoài câu JPQL hoặc SQL. Những thuộc tính đó gọi là query hint.

Ví dụ, cùng một JPQL:

```java
select e
from Employee e
where e.active = true
```

có thể được thực thi với timeout, chế độ cache hoặc gợi ý fetch size khác nhau. Query hint không thay đổi điều kiện nghiệp vụ trong câu query; nó cung cấp metadata cho JPA provider hoặc JDBC driver về cách thực thi.

Các nhóm hint thường gặp:

| Nhóm | Mục đích |
|---|---|
| Timeout | Giới hạn thời gian chờ query hoặc lock |
| Cache | Điều khiển việc đọc/ghi shared cache hoặc query cache |
| Fetch | Gợi ý cách lấy dữ liệu và số hàng đọc mỗi lần |
| Read-only | Giảm theo dõi thay đổi entity trong provider hỗ trợ |
| Lock | Điều chỉnh thời gian chờ khi lấy lock |
| Diagnostic | Thêm thông tin hỗ trợ theo dõi SQL |

Hint có thể được áp dụng cho JPQL, Criteria query hoặc native query, nhưng hiệu lực cụ thể phụ thuộc loại query, provider và database.

### 1.1. Query hint khác bind parameter

Bind parameter truyền giá trị được dùng trong điều kiện query:

```java
@Query("select e from Employee e where e.email = :email")
Optional<Employee> findByEmail(@Param("email") String email);
```

Query hint cấu hình cách query được thực thi:

```java
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.query.timeout",
        value = "1500"
    )
)
@Query("select e from Employee e where e.active = true")
List<Employee> findActiveEmployees();
```

`:email` là dữ liệu tham gia điều kiện WHERE. `jakarta.persistence.query.timeout` là chỉ dẫn về thời gian thực thi. Không dùng hint để truyền điều kiện lọc hoặc thay thế bind parameter.

### 1.2. Hint không phải một cam kết hiệu năng

Một hint có thể:

- Được provider hỗ trợ và áp dụng.
- Được chuyển xuống JDBC driver hoặc database dưới dạng cấu hình phù hợp.
- Bị bỏ qua vì provider không hỗ trợ hoặc query không phù hợp.
- Có hiệu quả khác nhau giữa các phiên bản provider/driver.

Vì vậy, query phải trả về kết quả đúng ngay cả khi một hint tối ưu bị bỏ qua. Với hint ảnh hưởng timeout hoặc locking, hãy xác nhận provider và database thực sự thực hiện hành vi cần thiết.

## 2. Hai loại query hint

### 2.1. JPA-standard hint

Jakarta Persistence định nghĩa một số tên hint chuẩn. Các tên thường gặp:

| Hint | Giá trị thường dùng | Ý nghĩa |
|---|---|---|
| `jakarta.persistence.query.timeout` | Số mili giây | Thời gian chờ query |
| `jakarta.persistence.lock.timeout` | Số mili giây | Thời gian chờ lấy lock |
| `jakarta.persistence.cache.retrieveMode` | `USE` / `BYPASS` | Có đọc shared cache hay không |
| `jakarta.persistence.cache.storeMode` | `USE` / `BYPASS` / `REFRESH` | Cách ghi shared cache |
| `jakarta.persistence.fetchgraph` | EntityGraph | Dùng graph như fetch plan |
| `jakarta.persistence.loadgraph` | EntityGraph | Bổ sung fetch plan theo graph |

Tên chuẩn dùng tiền tố `jakarta.persistence` trong Jakarta Persistence. Dự án cũ dùng Java Persistence API có thể dùng tên thuộc namespace `javax.persistence`; không trộn tên hint và import giữa hai thế hệ API.

Hint chuẩn giúp tăng tính di động, nhưng hiệu lực cuối cùng vẫn phụ thuộc khả năng của provider, JDBC driver và database. Ví dụ timeout có thể được chuyển thành JDBC statement timeout, nhưng mức độ chính xác và thời điểm dừng còn tùy hệ thống.

### 2.2. Vendor-specific hint

Provider có thể cung cấp hint riêng. Với Hibernate, một số tên thường gặp trong các phiên bản Hibernate 6 gồm:

| Hint Hibernate | Mục đích |
|---|---|
| `org.hibernate.readOnly` | Đánh dấu entity result là read-only đối với cơ chế theo dõi thay đổi của Hibernate |
| `org.hibernate.fetchSize` | Gợi ý JDBC fetch size |
| `org.hibernate.cacheable` | Cho phép query cache |
| `org.hibernate.cacheRegion` | Chỉ định vùng query cache |
| `org.hibernate.comment` | Thêm SQL comment để chẩn đoán |
| `org.hibernate.timeout` | Timeout theo đơn vị giây trong API hint Hibernate tương ứng |

Danh sách, tên hằng và cách áp dụng có thể thay đổi theo phiên bản Hibernate. Hãy ưu tiên hằng số được provider cung cấp nếu phiên bản đang dùng có API tương ứng; tránh sao chép tên hint từ ví dụ thuộc version khác mà không kiểm tra tài liệu.

Không đưa vendor-specific hint vào một repository dùng chung nhiều provider nếu ứng dụng cần khả năng chuyển đổi provider. Khi phải dùng, ghi rõ sự phụ thuộc và kiểm thử trên provider triển khai thực tế.

## 3. Dùng @QueryHints trong Spring Data JPA

Spring Data JPA cung cấp annotation `@QueryHints` trong package `org.springframework.data.jpa.repository`. Mỗi phần tử bên trong là annotation chuẩn `@QueryHint` của Jakarta Persistence.

Ví dụ:

```java
import jakarta.persistence.QueryHint;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @QueryHints({
        @QueryHint(
            name = "jakarta.persistence.query.timeout",
            value = "1500"
        )
    })
    @Query("""
           select e
           from Employee e
           where e.active = true
           """)
    List<Employee> findActiveEmployees();
}
```

Ở đây:

- `@QueryHints` là annotation của Spring Data JPA, nhận một mảng hint.
- `@QueryHint` là annotation của Jakarta Persistence, mô tả tên và giá trị một hint.
- `value = "1500"` là chuỗi theo cấu trúc annotation; với query timeout chuẩn, giá trị biểu thị mili giây.
- Hint được gắn với query mà repository method thực thi.

Có thể khai báo nhiều hint:

```java
@QueryHints({
    @QueryHint(
        name = "jakarta.persistence.query.timeout",
        value = "1500"
    ),
    @QueryHint(
        name = "org.hibernate.readOnly",
        value = "true"
    ),
    @QueryHint(
        name = "org.hibernate.fetchSize",
        value = "100"
    )
})
@Query("""
       select e
       from Employee e
       where e.active = true
       """)
List<Employee> findActiveEmployeesForReport();
```

Trong ví dụ này, query timeout là JPA-standard; read-only và fetch size là Hibernate-specific. Nếu ứng dụng dùng provider khác, hai hint Hibernate có thể không có tác dụng.

Không phải cứ khai báo annotation là provider sẽ thực hiện mọi hint. Hãy xem log SQL, cấu hình provider và kiểm thử hành vi trên database đích.

## 4. forCounting: hint có áp dụng cho count query không?

Một phương thức trả về `Page<T>` thường cần hai query:

1. Query lấy nội dung trang.
2. Count query để xác định tổng số phần tử/trang.

Spring Data JPA có thuộc tính `forCounting` trong `@QueryHints`. Mặc định là `true`; đặt `false` để không áp dụng các hint đó cho count query.

Ví dụ:

```java
@QueryHints(
    value = {
        @QueryHint(
            name = "org.hibernate.fetchSize",
            value = "100"
        ),
        @QueryHint(
            name = "org.hibernate.readOnly",
            value = "true"
        )
    },
    forCounting = false
)
@Query("""
       select e
       from Employee e
       where e.active = true
       """)
Page<Employee> findActiveEmployees(Pageable pageable);
```

Ở đây hint chỉ áp dụng cho query lấy nội dung trang, không áp dụng cho count query. Điều này hữu ích khi hint chỉ có ý nghĩa với query trả entity hoặc đọc nhiều hàng, trong khi count query chỉ trả một giá trị.

Với query có count query riêng:

```java
@Query(
    value = """
            select e
            from Employee e
            where e.department.id = :departmentId
            """,
    countQuery = """
            select count(e)
            from Employee e
            where e.department.id = :departmentId
            """
)
@QueryHints(
    value = @QueryHint(
        name = "jakarta.persistence.query.timeout",
        value = "2000"
    ),
    forCounting = false
)
Page<Employee> findByDepartment(
        @Param("departmentId") Long departmentId,
        Pageable pageable
);
```

Nếu muốn timeout áp dụng cho cả query nội dung và count query, giữ `forCounting = true` hoặc bỏ thuộc tính này. Chọn theo yêu cầu thực tế: count query cũng có thể tốn thời gian, đặc biệt với JOIN, DISTINCT hoặc bảng lớn.

`forCounting = false` chỉ điều khiển việc Spring Data áp dụng hint vào count query; nó không bỏ count query và không biến `Page` thành `Slice`.

## 5. Query timeout

Timeout giúp giới hạn thời gian chờ một truy vấn. JPA-standard hint:

`jakarta.persistence.query.timeout`

Ví dụ:

```java
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.query.timeout",
        value = "2000"
    )
)
@Query("select e from Employee e where e.active = true")
List<Employee> findActiveWithinTwoSeconds();
```

Giá trị chuẩn được biểu diễn bằng mili giây. Tuy nhiên, đây là query hint; provider có thể chuyển nó thành timeout của JDBC statement hoặc cơ chế phù hợp. Driver/database có thể có độ phân giải, giới hạn hoặc cách hủy câu lệnh khác nhau.

Khi timeout xảy ra, ứng dụng có thể nhận exception như `QueryTimeoutException` hoặc một exception persistence/SQL được Spring dịch. Hãy xử lý ở ranh giới transaction và kiểm tra trạng thái transaction sau lỗi. Không tiếp tục ghi dữ liệu trong transaction đã bị đánh dấu rollback-only.

### 5.1. Timeout Hibernate-specific

Hibernate cũng có hint timeout riêng:

```java
@QueryHints(
    @QueryHint(
        name = "org.hibernate.timeout",
        value = "2"
    )
)
@Query("select e from Employee e where e.active = true")
List<Employee> findActiveWithHibernateTimeout();
```

Hint Hibernate này dùng đơn vị giây trong API tương ứng, khác đơn vị mili giây của JPA-standard query timeout. Không khai báo cả hai chỉ để “chắc chắn”; chọn một cơ chế, xác nhận version Hibernate và kiểm thử timeout thực tế.

### 5.2. Timeout không thay thế tối ưu query

Nếu query chậm, cần kiểm tra:

- Execution plan và index.
- Số lượng hàng đọc, JOIN và điều kiện lọc.
- N+1 query hoặc fetch plan quá rộng.
- Phân trang và giới hạn kết quả.
- Lock contention và transaction kéo dài.

Timeout giúp bảo vệ tài nguyên khi query vượt ngưỡng; nó không làm query nhanh hơn và không giải quyết nguyên nhân hiệu năng.

## 6. Lock timeout và @Lock

Query hint `jakarta.persistence.lock.timeout` điều chỉnh thời gian chờ khi lấy lock trong các tình huống provider/database hỗ trợ. Ví dụ:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.lock.timeout",
        value = "2000"
    )
)
@Query("select e from Employee e where e.id = :id")
Optional<Employee> findForUpdate(@Param("id") Long id);
```

Hai annotation có vai trò riêng:

- `@Lock`: yêu cầu lock mode cho query, ví dụ `PESSIMISTIC_WRITE`.
- `@QueryHints`: cung cấp hint bổ sung, trong ví dụ là thời gian chờ lock.

Lock pessimistic thường cần transaction đang hoạt động. Nếu database không hỗ trợ timeout hoặc provider không chuyển hint đúng cách, hành vi có thể khác dự kiến. Một số database có thể dùng câu lệnh hoặc cú pháp riêng để đặt lock timeout.

Không nhầm lock timeout với query timeout:

| Loại | Điều khiển |
|---|---|
| Query timeout | Thời gian query được phép chạy/chờ |
| Lock timeout | Thời gian chờ lấy lock |
| Transaction timeout | Giới hạn thời gian của transaction theo cơ chế transaction manager/provider |

Ba giới hạn này có thể tương tác nhưng không thay thế nhau. Khi thiết kế nghiệp vụ đồng thời, cần kiểm tra deadlock, thứ tự lấy lock, thời gian giữ lock và chính sách retry.

## 7. Cache hints

JPA có shared cache ở cấp persistence unit/provider. Một số hint chuẩn điều khiển việc đọc và ghi cache.

### 7.1. Cache retrieve mode

`jakarta.persistence.cache.retrieveMode` nhận các giá trị như:

- `USE`: cho phép lấy dữ liệu từ shared cache nếu có.
- `BYPASS`: bỏ qua shared cache khi đọc.

Ví dụ:

```java
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.cache.retrieveMode",
        value = "BYPASS"
    )
)
@Query("select e from Employee e where e.id = :id")
Optional<Employee> findByIdBypassingSharedCache(@Param("id") Long id);
```

Trong annotation, value là chuỗi; provider diễn giải theo kiểu hint chuẩn. Với API programmatic, có thể truyền enum `CacheRetrieveMode.BYPASS`.

### 7.2. Cache store mode

`jakarta.persistence.cache.storeMode` điều khiển việc đưa kết quả vào shared cache:

- `USE`: cho phép lưu theo chính sách cache.
- `BYPASS`: không lưu kết quả vào shared cache.
- `REFRESH`: cập nhật cache từ dữ liệu đọc được khi provider hỗ trợ.

Ví dụ:

```java
@QueryHints({
    @QueryHint(
        name = "jakarta.persistence.cache.retrieveMode",
        value = "BYPASS"
    ),
    @QueryHint(
        name = "jakarta.persistence.cache.storeMode",
        value = "BYPASS"
    )
})
@Query("select e from Employee e where e.id = :id")
Optional<Employee> findWithoutSharedCache(@Param("id") Long id);
```

Shared cache của JPA khác query cache của Hibernate. Shared cache lưu trạng thái entity theo identity; Hibernate query cache lưu kết quả truy vấn theo cơ chế riêng và thường phối hợp với second-level cache để lấy entity state.

### 7.3. Hibernate query cache

Hibernate có thể bật query cache bằng hint vendor-specific:

```java
@QueryHints({
    @QueryHint(name = "org.hibernate.cacheable", value = "true"),
    @QueryHint(name = "org.hibernate.cacheRegion", value = "employee-active")
})
@Query("select e from Employee e where e.active = true")
List<Employee> findActiveCached();
```

Việc đặt `org.hibernate.cacheable = true` chưa đủ để bảo đảm cache hoạt động. Cần cấu hình query cache, second-level cache/cache region và cơ chế invalidation phù hợp. Query cache có thể không có lợi với dữ liệu thay đổi liên tục hoặc query trả về nhiều kết quả ít được tái sử dụng.

Không bật query cache cho mọi repository method. Đo hit rate, memory usage, invalidation và độ mới dữ liệu trước khi dùng rộng rãi.

## 8. Read-only hint và @Transactional(readOnly = true)

Hibernate hỗ trợ hint:

`org.hibernate.readOnly`

Ví dụ:

```java
@QueryHints(
    @QueryHint(
        name = "org.hibernate.readOnly",
        value = "true"
    )
)
@Query("select e from Employee e where e.active = true")
List<Employee> findActiveReadOnly();
```

Với Hibernate, hint này có thể đánh dấu entity được load từ query là read-only đối với dirty checking, giảm chi phí theo dõi thay đổi trong một số trường hợp.

Cần phân biệt với:

```java
@Transactional(readOnly = true)
public List<Employee> getActiveEmployees() {
    return repository.findActiveEmployees();
}
```

`@Transactional(readOnly = true)` là thuộc tính transaction ở tầng Spring. Nó có thể được transaction manager/provider dùng như một gợi ý tối ưu hoặc cấu hình kết nối. Nó không đồng nghĩa với hint `org.hibernate.readOnly` trên từng query.

Cả hai đều không phải cơ chế phân quyền database. Không dựa vào read-only hint để ngăn một câu UPDATE trái phép. Nếu nghiệp vụ cần cấm ghi, phải kiểm soát quyền, transaction và database constraint phù hợp.

Nếu entity được load read-only rồi thay đổi trong bộ nhớ, đừng kỳ vọng Hibernate tự dirty-check và ghi thay đổi đó như entity managed bình thường. Chỉ dùng khi use case thực sự chỉ đọc.

## 9. Fetch size và giới hạn phụ thuộc JDBC driver

Hibernate hỗ trợ hint:

`org.hibernate.fetchSize`

Ví dụ:

```java
@QueryHints(
    @QueryHint(
        name = "org.hibernate.fetchSize",
        value = "200"
    )
)
@Query("select e from Employee e order by e.id")
List<Employee> streamableEmployees();
```

Fetch size là gợi ý về số hàng JDBC driver lấy mỗi lần khi đọc ResultSet. Nó có thể giảm round trip hoặc bộ nhớ trong một số cách đọc dữ liệu lớn, nhưng hành vi tùy driver và database.

Fetch size không giống page size:

- `Pageable` giới hạn số bản ghi thuộc một trang và có thể tạo LIMIT/OFFSET hoặc cú pháp tương ứng.
- Fetch size ảnh hưởng cách driver đọc hàng từ ResultSet; nó không nhất thiết giới hạn tổng số kết quả query.

Với PostgreSQL JDBC, việc cursor-based fetching còn phụ thuộc cấu hình autocommit/transaction và cách ResultSet được sử dụng. Một số driver có thể bỏ qua fetch size hoặc tải toàn bộ kết quả nếu điều kiện không phù hợp.

Nếu cần xử lý dữ liệu rất lớn, cân nhắc Spring Data `Stream<T>`, scrolling/batch API phù hợp với version, phân trang theo khóa hoặc xử lý theo từng batch. Đóng stream và giữ transaction mở trong thời gian đọc theo đúng yêu cầu provider.

## 10. EntityGraph và fetch hint

JPA có các hint chuẩn `jakarta.persistence.fetchgraph` và `jakarta.persistence.loadgraph` để truyền EntityGraph vào query. Trong Spring Data JPA, thường có thể dùng annotation `@EntityGraph` dễ đọc hơn.

Ví dụ:

```java
@EntityGraph(attributePaths = {"department"})
@Query("select e from Employee e where e.active = true")
List<Employee> findActiveWithDepartment();
```

EntityGraph mô tả association cần tải cho use case. Nó giải quyết fetch plan; không phải cơ chế bind điều kiện query.

Hai hint chuẩn:

- `fetchgraph`: các thuộc tính trong graph được xem là eager cho query; thuộc tính không có trong graph được xử lý theo quy tắc fetch graph.
- `loadgraph`: các thuộc tính trong graph được bổ sung vào fetch plan mặc định.

Chi tiết cách provider tạo JOIN hay SELECT bổ sung có thể khác nhau. EntityGraph không bảo đảm chỉ có một câu SQL. Hãy kiểm tra SQL và tránh tạo fetch plan quá rộng, đặc biệt khi có nhiều collection.

## 11. Dùng query hint trực tiếp với EntityManager

Khi không dùng repository annotation, có thể đặt hint trực tiếp lên query:

```java
@Repository
public class EmployeeSearchDao {

    @PersistenceContext
    private EntityManager entityManager;

    public List<Employee> findActive() {
        TypedQuery<Employee> query = entityManager.createQuery(
                """
                select e
                from Employee e
                where e.active = true
                order by e.fullName
                """,
                Employee.class
        );

        query.setHint("jakarta.persistence.query.timeout", 1500);
        query.setHint("org.hibernate.readOnly", true);
        query.setHint("org.hibernate.fetchSize", 100);

        return query.getResultList();
    }
}
```

Với programmatic API, giá trị hint là Object. Hãy truyền kiểu dữ liệu mà JPA/provider yêu cầu; ví dụ timeout chuẩn có thể được truyền dưới dạng số mili giây, trong khi annotation `@QueryHint` biểu diễn value bằng String.

Có thể kiểm tra các hint hỗ trợ bằng tài liệu của provider và thử nghiệm hành vi. Không có một API portable bảo đảm liệt kê đầy đủ mọi vendor-specific hint mà provider hiểu.

## 12. Giới hạn phụ thuộc nhà cung cấp

Query hint là một trong những nơi dễ tạo phụ thuộc vào Hibernate hoặc database. Trước khi dùng, hãy phân loại:

| Câu hỏi | Cách đánh giá |
|---|---|
| Hint có trong Jakarta Persistence không? | Ưu tiên tên chuẩn nếu đáp ứng nhu cầu |
| Hint chỉ thuộc Hibernate? | Ghi rõ dependency và version |
| Hint có được driver hỗ trợ? | Kiểm tra JDBC driver/database |
| Hint có thể bị bỏ qua? | Thiết kế query vẫn đúng khi không có hint tối ưu |
| Hint ảnh hưởng kết quả hay chỉ hiệu năng? | Test semantics và hành vi lỗi |
| Hint có áp dụng cho count/native query không? | Kiểm tra Spring Data và provider thực tế |
| Hint có làm thay đổi trạng thái transaction? | Kiểm tra exception, rollback và lock |

Một số giới hạn cụ thể:

- Tên hint Hibernate và hằng số API có thể thay đổi giữa các version.
- Timeout không bảo đảm hủy query đúng một thời điểm tuyệt đối.
- Fetch size không bảo đảm driver dùng cursor hoặc streaming.
- Cache hint không bảo đảm cache được cấu hình, có hit hoặc luôn mới.
- Read-only hint không thay thế quyền ghi ở database.
- Lock timeout phụ thuộc khả năng của provider/database và có thể không được hỗ trợ.
- Một hint hợp lệ trên JPQL có thể không có ý nghĩa tương tự trên native query.
- Count query có thể cần tập hint khác với query lấy nội dung trang.

### 12.1. Hint không được hỗ trợ

Provider có thể bỏ qua vendor-specific hint mà nó không nhận diện. Một số trường hợp khác có thể phát sinh cảnh báo hoặc exception do kiểu giá trị không hợp lệ hay provider không chấp nhận hint đó.

Không coi việc ứng dụng khởi động thành công là bằng chứng hint được áp dụng. Cần kiểm tra SQL/log/driver metrics và đo hành vi thật.

## 13. Kiểm thử query hint

Test nên kiểm tra cả kết quả query và tác động mà hint cần tạo ra.

Ví dụ repository method:

```java
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.query.timeout",
        value = "2000"
    )
)
@Query("select e from Employee e where e.email = :email")
Optional<Employee> findByEmailWithTimeout(@Param("email") String email);
```

Test chức năng:

```java
@DataJpaTest
class EmployeeQueryHintTest {

    @Autowired
    private EmployeeRepository repository;

    @Test
    void queryWithHintReturnsExpectedEmployee() {
        repository.save(new Employee(
                "An Nguyen",
                "an@example.com",
                true
        ));

        Optional<Employee> result =
                repository.findByEmailWithTimeout("an@example.com");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getFullName())
                .isEqualTo("An Nguyen");
    }
}
```

Test này xác nhận query vẫn trả dữ liệu đúng. Nó không chứng minh timeout đã được driver thực thi. Để kiểm tra timeout, cần integration test với query có thời gian chạy kiểm soát được và đúng database/driver triển khai; tránh dùng thời gian ngủ ngẫu nhiên làm bằng chứng.

Nên kiểm thử:

- Query vẫn đúng khi hint tối ưu không được hỗ trợ.
- Timeout thực tế và exception được ném.
- Lock timeout khi có transaction cạnh tranh giữ lock.
- Count query có nhận hint theo `forCounting` hay không.
- Cache hit/miss và invalidation nếu bật cache.
- Fetch size/streaming trên driver thực tế.
- Read-only hint có hành vi như mong muốn trên Hibernate version đang dùng.
- EntityGraph và query hint không làm phát sinh N+1 hoặc tải dữ liệu quá rộng.

Với test liên quan đến lock, cache, timeout và driver behavior, dùng Testcontainers hoặc môi trường database tương ứng. Embedded database không thể đại diện đầy đủ cho hành vi PostgreSQL/MySQL/Oracle production.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Hint không có tác dụng | Provider/driver không hỗ trợ hoặc query không áp dụng hint | Kiểm tra tài liệu, SQL/log và thử đúng version |
| Query timeout không đúng thời gian mong muốn | Khác đơn vị, driver hoặc database có độ phân giải riêng | Phân biệt JPA timeout mili giây với Hibernate timeout giây |
| Count query chậm dù query chính có hint | Hint không được áp dụng cho count hoặc count query khác | Kiểm tra forCounting và khai báo hint phù hợp |
| Entity read-only vẫn bị thay đổi trong Java | Read-only không khóa object Java hoặc không phải cơ chế phân quyền | Không sửa entity trong use case read-only; bảo vệ ghi ở tầng khác |
| Fetch size không giảm bộ nhớ | Driver tải toàn bộ ResultSet hoặc điều kiện cursor không thỏa | Kiểm tra driver, transaction, stream và paging |
| Cache trả dữ liệu cũ | Cache region/invalidation/chính sách cập nhật chưa đúng | Kiểm tra cache provider, consistency và expiration |
| Lock timeout bị bỏ qua | Database/provider không hỗ trợ hint tương ứng | Xác minh lock mode và cú pháp database |
| Hint Hibernate lỗi sau nâng cấp | Tên hoặc API hint thay đổi | Dùng hằng số/documentation đúng version và integration test |
| Annotation không biên dịch | Import nhầm QueryHints/QueryHint | Dùng Spring Data QueryHints và Jakarta Persistence QueryHint |
| Native query không nhận hint như dự kiến | Hint phụ thuộc loại query/provider | Kiểm thử riêng native query trên database đích |

## 15. Checklist áp dụng query hints

- [ ] Xác định mục tiêu: timeout, cache, fetch, read-only, lock hay chẩn đoán.
- [ ] Ưu tiên JPA-standard hint khi có.
- [ ] Ghi rõ provider/version nếu dùng vendor-specific hint.
- [ ] Phân biệt đơn vị timeout chuẩn và timeout riêng của Hibernate.
- [ ] Dùng `forCounting` phù hợp với Page/count query.
- [ ] Không dùng read-only hint như cơ chế bảo mật.
- [ ] Không nhầm fetch size với Pageable/page size.
- [ ] Dùng EntityGraph khi mục tiêu là mô tả fetch plan.
- [ ] Kiểm tra transaction khi dùng lock hoặc timeout.
- [ ] Đo hiệu năng trước và sau khi thêm hint.
- [ ] Kiểm thử với đúng provider, JDBC driver và database.
- [ ] Đảm bảo kết quả nghiệp vụ vẫn đúng nếu hint tối ưu bị bỏ qua.

## Kết luận

Query hint bổ sung chỉ dẫn cho JPA provider về timeout, cache, fetch, read-only và lock. Spring Data JPA gắn hint vào repository method bằng `@QueryHints`; EntityManager hỗ trợ đặt hint trực tiếp qua `setHint`.

Ưu tiên hint chuẩn của Jakarta Persistence khi có thể. Với hint riêng của Hibernate hoặc database, cần kiểm tra version và driver, đo tác động thực tế và giữ cho tính đúng đắn của query không phụ thuộc vào một tối ưu có thể bị bỏ qua. `forCounting` giúp kiểm soát riêng hint của count query, còn `@Lock`, `@EntityGraph` và `@Transactional(readOnly = true)` giải quyết các khía cạnh khác nhau của việc thực thi query.
