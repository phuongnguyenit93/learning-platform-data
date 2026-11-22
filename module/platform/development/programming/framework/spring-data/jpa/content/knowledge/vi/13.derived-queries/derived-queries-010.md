# Distinct, countDistinct và ý nghĩa thực tế của phép đếm trong Spring Data JPA

## 1. Distinct trong truy vấn dữ liệu nghĩa là gì?

Khi truy vấn dữ liệu, một giá trị hoặc một entity có thể xuất hiện nhiều lần trong kết quả. Điều này thường xảy ra khi nhiều bản ghi có cùng thuộc tính, hoặc khi JOIN một quan hệ một-nhiều làm một entity cha xuất hiện ở nhiều hàng kết quả SQL.

SQL và JPQL cung cấp từ khóa `DISTINCT` để loại bỏ kết quả trùng theo biểu thức được chọn. Spring Data JPA hỗ trợ khai báo distinct qua tên phương thức repository hoặc viết truy vấn rõ ràng bằng `@Query`.

Cần phân biệt ba mục tiêu:

1. **Lấy entity không trùng:** mỗi entity chỉ xuất hiện một lần, kể cả khi JOIN tạo nhiều hàng cho cùng entity.
2. **Lấy giá trị thuộc tính không trùng:** danh sách tên, email, thành phố hoặc thuộc tính khác, mỗi giá trị chỉ xuất hiện một lần.
3. **Đếm số lượng không trùng:** đếm số entity hoặc số giá trị khác nhau thỏa điều kiện.

Ba mục tiêu này không tương đương. Một phương thức có từ Distinct trong tên không tự động có nghĩa là nó đếm các giá trị của một thuộc tính không trùng.

## 2. DISTINCT trong SQL và JPQL

### 2.1. DISTINCT trên biểu thức được chọn

Giả sử bảng `users` có dữ liệu:

| id | name | city |
|---:|---|---|
| 1 | An | Hanoi |
| 2 | Binh | Hanoi |
| 3 | Chi | Da Nang |
| 4 | Dung | Hanoi |
| 5 | Ha | Da Nang |

Truy vấn SQL:

~~~sql
SELECT DISTINCT city
FROM users;
~~~

Kết quả chỉ có hai giá trị:

~~~text
Hanoi
Da Nang
~~~

Database loại bỏ các giá trị city trùng nhau trong tập kết quả.

Nếu truy vấn chọn cả ID và city:

~~~sql
SELECT DISTINCT id, city
FROM users;
~~~

thì cả năm hàng vẫn xuất hiện, vì mỗi cặp ID và city là khác nhau. DISTINCT áp dụng trên toàn bộ tổ hợp biểu thức được chọn, không tự hiểu rằng chỉ muốn loại trùng ở cột city.

JPQL có cách viết tương tự:

~~~java
@Query("select distinct u.city from User u")
List<String> findDistinctCities();
~~~

JPQL truy vấn theo entity và thuộc tính Java. Tên entity User và thuộc tính city phải khớp với mapping.

### 2.2. DISTINCT trên entity

Ví dụ muốn lấy danh sách người dùng đang hoạt động mà không trả về cùng một entity nhiều lần:

~~~java
@Query("select distinct u from User u where u.active = true")
List<User> findDistinctActiveUsers();
~~~

Khi truy vấn JOIN tới collection, một user có nhiều bản ghi liên quan có thể tạo ra nhiều hàng SQL. Biểu thức select distinct u yêu cầu kết quả entity loại bỏ các lần lặp của cùng user theo ngữ nghĩa truy vấn.

Với derived query, có thể khai báo:

~~~java
List<User> findDistinctByActiveTrue();
~~~

Phương thức này trả về các entity User thỏa điều kiện active, với distinct được áp dụng cho kết quả entity. Nó không có nghĩa là lấy một user đại diện cho mỗi tên hoặc mỗi thành phố.

Nếu mục tiêu là lấy các thành phố duy nhất, hãy chọn thuộc tính city bằng JPQL:

~~~java
@Query("select distinct u.city from User u where u.active = true")
List<String> findDistinctActiveCities();
~~~

## 3. Derived query có Distinct

Spring Data JPA phân tích tên phương thức repository để tạo truy vấn. Từ khóa Distinct có thể dùng với các nhóm phương thức như find, read, get hoặc count.

Ví dụ:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {
    List<User> findDistinctByLastname(String lastname);

    long countDistinctByLastname(String lastname);
}
~~~

Hai phương thức này có ý nghĩa khác nhau:

- `findDistinctByLastname`: tìm các entity User có lastname khớp và loại bỏ kết quả entity trùng.
- `countDistinctByLastname`: đếm số entity thỏa điều kiện theo phép đếm distinct mà Spring Data suy ra.

Để hiểu chính xác countDistinctBy..., cần xem biểu thức mà Spring Data JPA thực sự đếm.

## 4. Điểm dễ nhầm: countDistinctByLastname không đếm số họ khác nhau

Giả sử có 100 người dùng cùng mang họ Nguyen. Nếu gọi phương thức countDistinctByLastname với tham số Nguyen, nhiều người có thể kỳ vọng kết quả là 1 vì chỉ có một giá trị họ khác nhau trong nhóm đó.

Nhưng derived query countDistinctByLastname của Spring Data JPA thường được chuyển thành truy vấn đếm distinct theo ID entity, có dạng khái niệm:

~~~sql
SELECT COUNT(DISTINCT u.id)
FROM users u
WHERE u.lastname = ?;
~~~

Vì ID mỗi user là duy nhất, kết quả tương đương số user có họ Nguyen, tức có thể là 100, giống với countByLastname("Nguyen").

Đây là điểm quan trọng:

**countDistinctByLastname thường đếm số entity có lastname thỏa điều kiện, không đếm số giá trị lastname khác nhau.**

Tên phương thức có Distinct không đủ để xác định cột nào được đếm. Hãy xem truy vấn được sinh ra và kiểu dữ liệu mà nghiệp vụ thực sự cần.

### Ví dụ dữ liệu

| id | lastname |
|---:|---|
| 1 | Nguyen |
| 2 | Nguyen |
| 3 | Tran |
| 4 | Nguyen |
| 5 | Le |

Với điều kiện lastname là Nguyen:

| Truy vấn | Kết quả | Ý nghĩa |
|---|---:|---|
| countByLastname("Nguyen") | 3 | Đếm entity có họ Nguyen |
| countDistinctByLastname("Nguyen") | 3 | Đếm ID entity distinct có họ Nguyen |
| COUNT(DISTINCT lastname) trên toàn bảng | 3 | Đếm các giá trị họ khác nhau: Nguyen, Tran, Le |

Nếu lọc chính xác lastname = Nguyen, số giá trị lastname khác nhau trong tập kết quả chỉ có thể là 1 khi có bản ghi phù hợp, còn số entity có thể là hàng trăm hoặc hàng triệu.

## 5. Đếm số giá trị thuộc tính khác nhau bằng COUNT(DISTINCT field)

Nếu nghiệp vụ muốn đếm số giá trị khác nhau của một thuộc tính, hãy viết truy vấn đếm rõ thuộc tính đó.

Ví dụ: đếm số thành phố khác nhau có người dùng đang hoạt động:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    @Query("""
        select count(distinct u.city)
        from User u
        where u.active = true
    """)
    long countDistinctActiveCities();
}
~~~

Truy vấn này đếm các giá trị city khác nhau, không đếm ID người dùng.

Muốn lấy danh sách thành phố không trùng:

~~~java
@Query("""
    select distinct u.city
    from User u
    where u.active = true
    order by u.city
""")
List<String> findDistinctActiveCities();
~~~

Muốn đếm số họ khác nhau trong một nhóm điều kiện:

~~~java
@Query("""
    select count(distinct u.lastname)
    from User u
    where u.active = true
""")
long countDistinctLastnamesOfActiveUsers();
~~~

Nếu cần lọc theo một điều kiện khác, thêm điều kiện vào WHERE:

~~~java
@Query("""
    select count(distinct u.city)
    from User u
    where u.active = true
      and u.countryCode = :countryCode
""")
long countDistinctCities(
    @Param("countryCode") String countryCode
);
~~~

COUNT(DISTINCT u.city) đếm số giá trị thành phố không trùng trong tập dữ liệu sau khi áp dụng điều kiện WHERE. Với ngữ nghĩa SQL/JPQL, giá trị NULL không được tính trong COUNT(expression), kể cả khi có DISTINCT.

## 6. Phân biệt COUNT(*), COUNT(field) và COUNT(DISTINCT field)

Ba biểu thức đếm phổ biến có ý nghĩa khác nhau:

| Biểu thức | Ý nghĩa |
|---|---|
| COUNT(*) | Đếm số hàng trong tập kết quả |
| COUNT(u.city) | Đếm số hàng có city khác NULL |
| COUNT(DISTINCT u.city) | Đếm số giá trị city khác nhau và khác NULL |

Ví dụ dữ liệu:

| id | city |
|---:|---|
| 1 | Hanoi |
| 2 | Hanoi |
| 3 | Da Nang |
| 4 | NULL |
| 5 | Hanoi |
| 6 | NULL |

Kết quả:

- COUNT(*) = 6 hàng.
- COUNT(city) = 4 hàng có city khác NULL.
- COUNT(DISTINCT city) = 2 giá trị khác nhau: Hanoi và Da Nang.

Nếu nghiệp vụ cần tính cả trường hợp chưa có thành phố như một nhóm riêng, phải biểu đạt quy tắc đó tường minh, ví dụ dùng COALESCE để thay NULL bằng một giá trị đại diện phù hợp. Hãy chọn giá trị thay thế không thể nhầm với dữ liệu hợp lệ.

## 7. DISTINCT khi JOIN quan hệ một-nhiều

Một tình huống thường gặp là truy vấn entity cha cùng quan hệ collection.

Giả sử một đơn hàng có nhiều dòng chi tiết. Khi JOIN PurchaseOrder với OrderItem, một đơn hàng có ba dòng chi tiết có thể tạo ra ba hàng kết quả SQL cho cùng một đơn hàng.

Ví dụ:

~~~java
@Query("""
    select distinct o
    from PurchaseOrder o
    join o.items i
    where i.productName = :productName
""")
List<PurchaseOrder> findOrdersContainingProduct(
    @Param("productName") String productName
);
~~~

Nếu cùng một đơn hàng có nhiều dòng phù hợp, distinct giúp trả về mỗi entity đơn hàng một lần trong kết quả.

Nếu bỏ distinct, truy vấn join có thể tạo kết quả lặp tùy truy vấn và provider. Khi chỉ cần kiểm tra có tồn tại dòng chi tiết phù hợp, có thể cân nhắc truy vấn EXISTS trong subquery thay vì JOIN rồi khử trùng lặp.

~~~java
@Query("""
    select o
    from PurchaseOrder o
    where exists (
        select i.id
        from OrderItem i
        where i.order = o
          and i.productName = :productName
    )
""")
List<PurchaseOrder> findOrdersWithProduct(
    @Param("productName") String productName
);
~~~

Cách viết này biểu đạt trực tiếp mục tiêu: lấy các đơn hàng có ít nhất một dòng chi tiết phù hợp. Database có thể tối ưu EXISTS tốt trong nhiều trường hợp, nhưng hiệu năng thực tế vẫn cần xem execution plan và index.

## 8. DISTINCT với projection và kết quả scalar

Khi repository trả về entity, distinct được áp dụng cho entity result. Khi repository trả về một thuộc tính đơn như String, distinct được áp dụng cho giá trị scalar đã chọn.

Ví dụ:

~~~java
@Query("select distinct u.department from User u")
List<String> findDistinctDepartments();
~~~

Kết quả là danh sách tên phòng ban không trùng.

Nếu chọn nhiều thuộc tính:

~~~java
@Query("""
    select distinct u.department, u.countryCode
    from User u
""")
List<Object[]> findDistinctDepartmentCountryPairs();
~~~

thì distinct áp dụng trên cả cặp department và countryCode. Hai hàng có cùng department nhưng khác countryCode vẫn là hai kết quả khác nhau.

Trong ứng dụng thực tế, nên dùng DTO projection thay cho Object[] nếu cần trả về nhiều trường:

~~~java
public record DepartmentCountry(
    String department,
    String countryCode
) {}
~~~

~~~java
@Query("""
    select distinct new com.example.shop.DepartmentCountry(
        u.department,
        u.countryCode
    )
    from User u
""")
List<DepartmentCountry> findDistinctDepartmentCountryPairs();
~~~

Tên class DTO trong JPQL constructor expression phải là tên đầy đủ của lớp. Các kiểu dữ liệu và thứ tự tham số phải khớp với constructor.

## 9. Đếm distinct theo nhóm với GROUP BY

Đôi khi cần đếm số entity hoặc số giá trị duy nhất cho từng nhóm, ví dụ số thành phố khác nhau theo quốc gia.

~~~java
@Query("""
    select u.countryCode, count(distinct u.city)
    from User u
    where u.active = true
    group by u.countryCode
    order by u.countryCode
""")
List<Object[]> countDistinctCitiesByCountry();
~~~

Mỗi hàng kết quả chứa mã quốc gia và số thành phố khác nhau của quốc gia đó. Trong ứng dụng thực tế, có thể thay Object[] bằng DTO projection để dễ đọc và kiểm tra kiểu.

Cần phân biệt:

- COUNT(DISTINCT u.city) đếm thành phố khác nhau trong từng nhóm.
- COUNT(u) đếm entity trong từng nhóm.
- COUNT(DISTINCT u.id) đếm ID entity khác nhau trong từng nhóm.

Nếu có JOIN tới collection, lựa chọn biểu thức đếm càng quan trọng vì JOIN có thể nhân số hàng trước khi aggregate.

## 10. DISTINCT và phân trang

Khi dùng Page<T>, Spring Data JPA thường cần hai truy vấn:

1. Truy vấn lấy dữ liệu của trang hiện tại.
2. Truy vấn đếm tổng số phần tử để tạo metadata của Page.

Với truy vấn có DISTINCT, JOIN hoặc GROUP BY, truy vấn đếm tự suy ra có thể không phản ánh đúng số entity hoặc giá trị duy nhất mà trang đang trả về.

Ví dụ:

~~~java
@Query(
    value = """
        select distinct u
        from User u
        join u.roles r
        where r.name = :roleName
    """,
    countQuery = """
        select count(distinct u.id)
        from User u
        join u.roles r
        where r.name = :roleName
    """
)
Page<User> findDistinctUsersByRole(
    @Param("roleName") String roleName,
    Pageable pageable
);
~~~

Ở đây:

- Truy vấn nội dung trả về các entity User distinct.
- countQuery đếm distinct ID user, đúng với mục tiêu tổng số entity.
- Nếu mục tiêu là đếm số giá trị scalar khác nhau, count query phải dùng COUNT(DISTINCT thuộc_tính) tương ứng.

Khi truy vấn phân trang có JOIN phức tạp, hãy kiểm tra cả truy vấn nội dung và count query. Có thể khai báo countQuery riêng để bảo đảm tổng số phần tử của trang đúng với định nghĩa nghiệp vụ.

Nếu chỉ cần dữ liệu trang và thông tin còn trang tiếp theo mà không cần tổng số bản ghi, có thể dùng Slice<T> để tránh truy vấn đếm tổng trong các trường hợp phù hợp.

## 11. Tên phương thức và @Query: chọn cách nào?

| Nhu cầu | Cách viết phù hợp |
|---|---|
| Lấy entity thỏa điều kiện, loại bỏ entity lặp | findDistinctBy... |
| Đếm entity thỏa điều kiện | countBy... |
| Đếm distinct entity ID theo điều kiện | countDistinctBy... |
| Đếm số giá trị khác nhau của một thuộc tính | @Query với COUNT(DISTINCT e.field) |
| Lấy danh sách giá trị scalar không trùng | @Query với SELECT DISTINCT e.field |
| Đếm distinct sau JOIN hoặc theo nhóm phức tạp | JPQL @Query, khai báo count query nếu phân trang |
| Dùng cú pháp riêng của database | Native SQL, cân nhắc khả năng phụ thuộc hệ quản trị |

Derived query phù hợp với điều kiện đơn giản, dễ đọc. Khi nghiệp vụ cần nói rõ đang đếm ID, một thuộc tính hay một tổ hợp, @Query thường giúp người đọc hiểu chính xác hơn.

## 12. Hiệu năng và các lưu ý thực tế

DISTINCT có thể làm database phải sắp xếp hoặc dùng hash aggregate để loại trùng. Với tập dữ liệu lớn, thao tác này có chi phí về CPU, bộ nhớ hoặc I/O tùy execution plan.

Một số điểm nên kiểm tra:

- **JOIN:** nếu JOIN làm nhân số hàng, hãy xác định có thật sự cần lấy entity distinct hay có thể dùng EXISTS.
- **Index:** index trên cột lọc và cột join có thể giúp truy vấn; index phù hợp cho DISTINCT phụ thuộc database, thứ tự cột và execution plan.
- **Projection:** chỉ chọn trường cần thiết; không tải toàn bộ entity nếu chỉ cần một danh sách scalar.
- **COUNT:** truy vấn đếm distinct trên tập dữ liệu lớn có thể tốn kém. Hãy đo bằng dữ liệu gần với production.
- **NULL:** COUNT(expression) bỏ qua NULL; nếu nghiệp vụ cần tính nhóm NULL, hãy biểu đạt riêng.
- **Case và collation:** hai chuỗi khác chữ hoa/thường có được xem là cùng một giá trị hay không phụ thuộc biểu thức, collation và cách chuẩn hóa dữ liệu.
- **Composite distinct:** JPQL chuẩn không cung cấp một cách portable thống nhất để đếm distinct trên nhiều cột như một tuple. Nếu cần đếm cặp hoặc bộ nhiều thuộc tính, hãy dùng truy vấn nhóm/subquery phù hợp hoặc native SQL theo database.
- **Generated SQL:** tên method chỉ là đầu vào cho query derivation. Khi kết quả bất ngờ, hãy bật log SQL và bind parameter trong môi trường phát triển để kiểm tra truy vấn thực tế.

Không thêm DISTINCT theo thói quen để che kết quả JOIN sai. Hãy xác định nguồn tạo hàng lặp và chọn đúng projection, JOIN, EXISTS hoặc phép đếm.

## 13. Quy trình xác định phép đếm đúng

Trước khi viết method repository, hãy diễn đạt yêu cầu bằng một câu cụ thể:

1. Muốn đếm **số entity** hay **số giá trị thuộc tính**?
2. Nếu đếm giá trị thuộc tính, thuộc tính nào là biểu thức distinct?
3. Có cần bỏ qua NULL hay xem NULL như một nhóm riêng?
4. Có JOIN quan hệ một-nhiều khiến một entity xuất hiện nhiều lần không?
5. Có phân trang và cần tổng số phần tử hay chỉ cần biết còn trang tiếp theo?
6. Truy vấn sinh ra có khớp với ý nghĩa nghiệp vụ không?

Ví dụ:

- “Có bao nhiêu user có họ Nguyen?” → countByLastname("Nguyen").
- “Có bao nhiêu ID user khác nhau có họ Nguyen?” → countDistinctByLastname("Nguyen"); trong trường hợp ID duy nhất, kết quả thường giống phép đếm entity thông thường.
- “Có bao nhiêu họ khác nhau trong toàn bộ user đang hoạt động?” → COUNT(DISTINCT u.lastname).
- “Có bao nhiêu thành phố khác nhau trong mỗi quốc gia?” → GROUP BY countryCode kết hợp COUNT(DISTINCT city).

## 14. Ghi nhớ

- DISTINCT áp dụng trên biểu thức hoặc tập cột được chọn trong truy vấn.
- findDistinctBy... thường trả về entity distinct, không có nghĩa là distinct một thuộc tính bất kỳ.
- countDistinctBy... của Spring Data JPA thường đếm distinct ID entity thỏa điều kiện; nó có thể cho kết quả giống countBy....
- Muốn đếm số giá trị thuộc tính khác nhau, hãy viết COUNT(DISTINCT e.field) bằng JPQL hoặc SQL.
- COUNT(*), COUNT(field) và COUNT(DISTINCT field) có ý nghĩa khác nhau; COUNT expression bỏ qua NULL.
- JOIN collection có thể nhân hàng; select distinct entity hoặc EXISTS có thể diễn đạt đúng mục tiêu lấy entity.
- Với phân trang, count query phải đếm đúng loại phần tử mà nội dung trang trả về.
- Kiểm tra generated SQL khi ý nghĩa của method name chưa rõ hoặc kết quả không như mong đợi.

Điều quyết định một phép đếm đúng là **đối tượng đang được đếm**: hàng, entity, ID, hay giá trị thuộc tính duy nhất. Hãy viết truy vấn sao cho biểu thức được đếm thể hiện chính xác khái niệm đó.