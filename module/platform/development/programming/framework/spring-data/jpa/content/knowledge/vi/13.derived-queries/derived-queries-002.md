# Query lookup strategy: CREATE, USE_DECLARED_QUERY và CREATE_IF_NOT_FOUND

## 1. Query lookup strategy là gì?

Spring Data JPA cung cấp nhiều cách xác định câu truy vấn cho một repository method. Khi tạo repository, framework phải quyết định lấy truy vấn từ tên phương thức, từ khai báo `@Query`, hay từ một JPA named query. Quy tắc lựa chọn này được gọi là **query lookup strategy**.

Ba chiến lược có trong `QueryLookupStrategy.Key`:

| Strategy | Cách tìm truy vấn | Khi không có declared query |
| --- | --- | --- |
| `CREATE` | Phân tích tên method để tạo query | Tiếp tục tạo query từ tên method; nếu tên không hợp lệ thì lỗi |
| `USE_DECLARED_QUERY` | Tìm truy vấn đã khai báo, như `@Query` hoặc named query | Báo lỗi vì không tìm thấy truy vấn khai báo |
| `CREATE_IF_NOT_FOUND` | Tìm declared query trước, nếu không có thì phân tích tên method | Fallback sang query derivation |

`CREATE_IF_NOT_FOUND` là chiến lược mặc định của Spring Data JPA. Tên `CREATE` ở đây nói về việc tạo truy vấn từ tên method, không phải lệnh SQL `CREATE TABLE` hay thao tác tạo schema.

## 2. CREATE: tạo query từ tên phương thức

Với `CREATE`, Spring Data phân tích tên repository method và ánh xạ các phần của tên thành điều kiện dựa trên thuộc tính Entity. Ví dụ:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Optional<Customer> findByEmail(String email);

    List<Customer> findByStatusAndCreatedAtAfterOrderByCreatedAtDesc(
        CustomerStatus status,
        Instant createdAt
    );

    boolean existsByEmail(String email);

    long countByStatus(CustomerStatus status);
}
```

Framework phân tích các thành phần như:

- `findBy`: truy vấn và trả về kết quả phù hợp.
- `Email`: điều kiện trên thuộc tính `email`.
- `And`: kết hợp hai điều kiện.
- `CreatedAtAfter`: so sánh thời gian lớn hơn tham số.
- `OrderByCreatedAtDesc`: sắp xếp giảm dần theo `createdAt`.
- `existsBy`: kiểm tra có bản ghi phù hợp hay không.
- `countBy`: đếm số bản ghi phù hợp.

Các từ khóa phổ biến khác gồm `Or`, `Between`, `LessThan`, `GreaterThan`, `Like`, `Containing`, `StartingWith`, `EndingWith`, `In`, `NotIn`, `IsNull`, `IsNotNull`, `True`, `False`, `IgnoreCase`, `Distinct`, `First` và `Top`. Cú pháp chính xác phụ thuộc loại thuộc tính và khả năng của phiên bản Spring Data.

Query derivation tham chiếu tên thuộc tính Java trong Entity, không phải tên cột vật lý. Nếu Entity có `createdAt` được ánh xạ xuống cột `created_at`, method phải dùng `findByCreatedAt...`, không dùng `findByCreated_at...`.

Với thuộc tính lồng nhau, Spring Data có thể phân tích property path. Nếu tên thuộc tính gây nhập nhằng, dấu gạch dưới có thể dùng làm dấu phân cách rõ ràng, ví dụ `findByAddress_ZipCode(...)` để chỉ `address.zipCode`.

Ưu điểm của CREATE là method ngắn, dễ đọc và phù hợp các truy vấn CRUD đơn giản. Nhược điểm là method có thể dài hoặc khó hiểu khi điều kiện phức tạp, có nhiều join, projection, aggregate hoặc logic database riêng.

## 3. USE_DECLARED_QUERY: bắt buộc khai báo query

Với `USE_DECLARED_QUERY`, Spring Data yêu cầu mỗi query method phải có truy vấn khai báo sẵn. Nguồn declared query thường gặp:

- `@Query` trên repository method.
- JPA `@NamedQuery` hoặc `@NamedQueries` khai báo trên Entity.
- Named query được khai báo trong `orm.xml`.

Nếu không tìm thấy declared query cho method, repository sẽ báo lỗi khi query được khởi tạo. Đây là cách fail-fast để phát hiện thiếu truy vấn ngay trong quá trình khởi động/khởi tạo repository, thay vì âm thầm suy diễn từ tên method.

Ví dụ dùng `@Query` với JPQL:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    @Query("select c from Customer c where lower(c.email) = lower(:email)")
    Optional<Customer> findByEmail(@Param("email") String email);
}
```

JPQL dùng entity name `Customer` và thuộc tính Java `email`, không dùng tên bảng/cột SQL. `@Param("email")` liên kết tham số method với `:email` trong query. Có thể dùng tham số vị trí `?1`, `?2` thay cho named parameter.

Declared query cũng có thể là native SQL khi thật sự cần cú pháp hoặc tính năng riêng của database:

```java
@Query(
    value = "select * from customer where email = :email",
    nativeQuery = true
)
Optional<Customer> findNativeByEmail(@Param("email") String email);
```

Native query dùng tên bảng và cột vật lý trong schema. Cần kiểm tra tính tương thích với database, cách phân trang/sort và mapping kết quả; không viết native SQL bằng tên thuộc tính Java.

## 4. Named query và quy ước tên

JPA cho phép khai báo query có tên bằng `@NamedQuery`. Spring Data JPA tìm named query theo quy ước `<EntitySimpleName>.<repositoryMethodName>`.

Ví dụ Entity:

```java
@Entity
@NamedQuery(
    name = "Customer.findByEmail",
    query = "select c from Customer c where c.email = ?1"
)
public class Customer {
    @Id
    private Long id;

    private String email;
}
```

Repository:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Optional<Customer> findByEmail(String email);
}
```

Với tên method `findByEmail`, framework có thể tìm named query `Customer.findByEmail`. Query được khai báo bằng `@NamedQuery` là JPQL, nên tham chiếu Entity và thuộc tính Java.

Named query có thể đặt trong `orm.xml` nếu dự án muốn tách query khỏi mã Entity. Khi dùng XML, tên query vẫn cần khớp quy ước mà repository method tra cứu.

Nếu cùng method có `@Query` và named query trùng tên, khai báo `@Query` trên method được ưu tiên trong cơ chế declared query lookup. Nên tránh khai báo nhiều nguồn query mâu thuẫn cho cùng một method để người bảo trì biết đâu là nguồn chuẩn.

## 5. CREATE_IF_NOT_FOUND: declared query trước, derived query sau

Đây là lựa chọn cân bằng và là mặc định của Spring Data JPA:

1. Nếu method có `@Query`, dùng truy vấn được khai báo tại method.
2. Nếu không, tìm named query phù hợp theo tên.
3. Nếu vẫn không có, phân tích tên method để tạo query.

Ví dụ một repository có cả hai kiểu:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    // Không có @Query hoặc named query: query được suy ra từ tên method.
    Optional<Customer> findByEmail(String email);

    // Có @Query: dùng JPQL khai báo bên dưới.
    @Query("select c from Customer c where c.status = :status")
    List<Customer> searchByStatus(@Param("status") CustomerStatus status);
}
```

CREATE_IF_NOT_FOUND giúp các truy vấn đơn giản vẫn ngắn gọn, trong khi truy vấn phức tạp có thể khai báo rõ bằng JPQL hoặc native SQL. Tuy nhiên, một method có thể vô tình chuyển từ derived query sang named query nếu ai đó thêm một named query trùng tên. Vì vậy cần quản lý tên và kiểm thử query như một phần hợp đồng của repository.

## 6. Cấu hình chiến lược cho repository

Spring Data JPA cho phép chọn strategy qua thuộc tính `queryLookupStrategy` của `@EnableJpaRepositories`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.repository.query.QueryLookupStrategy;

@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.customer.repository",
    queryLookupStrategy = QueryLookupStrategy.Key.USE_DECLARED_QUERY
)
public class JpaRepositoryConfiguration {
}
```

Thay giá trị enum bằng `CREATE` hoặc `CREATE_IF_NOT_FOUND` theo chính sách của dự án. Nếu ứng dụng dùng Spring Boot auto-configuration, chỉ thêm `@EnableJpaRepositories` khi thực sự cần cấu hình repository scanning/strategy tường minh; hãy chỉ rõ base package và tránh cấu hình trùng lặp với các repository registrar khác.

Không nhầm `queryLookupStrategy` với cấu hình Hibernate dialect, naming strategy hoặc DDL. Nó quyết định cách Spring Data tìm định nghĩa query cho repository method, không thay đổi schema database.

## 7. Chọn strategy nào?

| Nhu cầu | Strategy phù hợp | Lý do |
| --- | --- | --- |
| Repository CRUD đơn giản, method name rõ | `CREATE` | Tập trung query derivation, ít phải viết JPQL |
| Muốn bắt buộc query method có khai báo tường minh | `USE_DECLARED_QUERY` | Thiếu query sẽ bị phát hiện khi repository khởi tạo |
| Muốn kết hợp query đơn giản và query khai báo | `CREATE_IF_NOT_FOUND` | Dùng declared query trước, fallback sang method name |

`USE_DECLARED_QUERY` hữu ích khi dự án muốn kiểm soát mọi câu query, review JPQL/native SQL và tránh method name dài. Đổi lại, mỗi query method cần có khai báo rõ ràng và việc bảo trì query tập trung hơn.

`CREATE` phù hợp với convention-driven repository, nhưng cần đặt tên method dễ hiểu và kiểm tra property path. `CREATE_IF_NOT_FOUND` phù hợp phần lớn ứng dụng vì cho phép chọn cách diễn đạt theo độ phức tạp của từng truy vấn.

## 8. Lỗi thường gặp khi lookup query

**Không tìm thấy property khi tạo repository.** Derived method có thể tham chiếu sai tên field hoặc property path. Đối chiếu với Entity, chú ý camelCase và quan hệ lồng nhau.

**Ứng dụng khởi động lỗi vì thiếu declared query.** Nếu đang dùng `USE_DECLARED_QUERY`, thêm `@Query`, named query hoặc cấu hình lại strategy nếu muốn fallback sang derivation.

**Named query không được nhận diện.** Kiểm tra tên theo dạng `EntitySimpleName.methodName`, tên Entity thực tế, method repository và file `orm.xml` đã được nạp.

**Kết quả khác mong đợi dù method name hợp lệ.** Kiểm tra parser keywords, And/Or, thứ tự property, IgnoreCase, null handling và generated SQL. Method dài có thể khó thể hiện logic; chuyển sang `@Query` khi cần kiểm soát rõ hơn.

**JPQL báo không tìm thấy bảng/cột.** JPQL dùng Entity và thuộc tính Java; native SQL dùng tên vật lý. Xác định loại query trước khi sửa tên.

**Có `@Query` nhưng query được hiểu theo tên method.** Kiểm tra strategy đang sử dụng. `CREATE` tập trung vào query derivation; muốn sử dụng declared query cần strategy có declared-query lookup như `USE_DECLARED_QUERY` hoặc `CREATE_IF_NOT_FOUND`.

**Query chạy được khi khởi động nhưng lỗi khi thực thi.** Kiểm thử query với database/dialect thật, dữ liệu đại diện và các kiểu tham số. Một số lỗi phụ thuộc SQL sinh ra, schema hoặc dữ liệu chỉ xuất hiện lúc chạy.

## 9. Query lookup strategy có ảnh hưởng hiệu năng không?

Bản thân strategy chủ yếu quyết định cách định nghĩa query được tìm và tạo khi repository được khởi tạo. Nó không phải công tắc bật/tắt cache, JDBC batching hay tối ưu query plan. Một derived query và một declared JPQL query tương đương có thể sinh SQL tương tự.

Hiệu năng thực tế phụ thuộc SQL được sinh ra, index, cardinality, execution plan, fetch strategy, số round-trip, kích thước kết quả và database. Khi query chậm, kiểm tra SQL và execution plan thay vì đổi CREATE sang USE_DECLARED_QUERY với kỳ vọng tự tăng tốc.

## 10. Quy trình kiểm thử repository

1. Với derived query, kiểm tra method name khớp thuộc tính Entity và chạy được với dữ liệu biên.
2. Với `@Query`, kiểm tra JPQL tham chiếu đúng Entity/field; với native query, kiểm tra đúng table/column của schema.
3. Với named query, kiểm tra quy ước tên và query thực tế được nạp.
4. Nếu dùng `USE_DECLARED_QUERY`, kiểm tra mọi query method đã có declared query để phát hiện thiếu khai báo.
5. Chạy integration test với database tương thích môi trường triển khai, không chỉ dựa vào mock repository.
6. Kiểm tra kết quả, null, empty collection, phân trang, sort và trường hợp không có bản ghi.
7. Với query quan trọng về hiệu năng, xem SQL, đo số truy vấn và kiểm tra execution plan.

## 11. Tổng kết quy tắc lựa chọn

- `CREATE`: tạo query từ tên method.
- `USE_DECLARED_QUERY`: bắt buộc tìm thấy `@Query`, named query hoặc declared query khác; không fallback.
- `CREATE_IF_NOT_FOUND`: tìm declared query trước, nếu không có thì tạo query từ method name; đây là mặc định.
- `@Query` phù hợp khi cần JPQL/native SQL tường minh; named query phù hợp khi muốn khai báo query có tên gắn với Entity hoặc XML.
- Query lookup strategy quyết định nguồn query, còn hiệu năng phụ thuộc SQL và database.

Chọn strategy theo mức độ kiểm soát mà dự án cần. Dù query được suy ra hay khai báo, hãy giữ method name dễ hiểu, quản lý nguồn query rõ ràng và kiểm thử trên database thực tế để tránh lỗi chỉ xuất hiện khi chạy.