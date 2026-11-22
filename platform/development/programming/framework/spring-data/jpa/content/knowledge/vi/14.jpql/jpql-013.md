# Hàm cơ sở dữ liệu, FUNCTION và giới hạn tính khả chuyển trong Spring Data JPA

## 1. Vì sao truy vấn JPA cần gọi hàm của database?

JPQL cung cấp ngôn ngữ truy vấn dựa trên entity và thuộc tính Java. Ngôn ngữ này có sẵn nhiều hàm thông dụng để xử lý chuỗi, số, ngày giờ, giá trị NULL và phép tổng hợp. Tuy nhiên, ứng dụng thực tế đôi khi cần chức năng riêng của hệ quản trị cơ sở dữ liệu, ví dụ:

- Chuẩn hóa chuỗi theo extension hoặc collation đặc thù.
- Cắt thời gian theo ngày, tháng hoặc múi giờ.
- Đọc một trường trong JSON/JSONB.
- Tính khoảng cách địa lý.
- Dùng hàm nghiệp vụ do nhóm phát triển tạo trong database.
- Tận dụng hàm phân tích hoặc xử lý dữ liệu đặc thù của một hệ quản trị.

Spring Data JPA có thể gọi những hàm này thông qua JPQL `FUNCTION`, Criteria API hoặc native SQL. Lựa chọn cách nào phụ thuộc vào mức độ phức tạp của truy vấn và yêu cầu chạy trên nhiều hệ quản trị.

Cần phân biệt ba lớp:

1. **JPQL/JPA:** quy định cú pháp truy vấn và một tập hàm chuẩn.
2. **JPA provider:** ví dụ Hibernate, phân tích JPQL, xác định kiểu dữ liệu và chuyển truy vấn thành SQL.
3. **Database:** thực thi hàm thực tế. Tên hàm, kiểu tham số, kiểu trả về và hành vi có thể phụ thuộc hệ quản trị hoặc extension đã cài đặt.

Việc JPQL cho phép gọi một hàm không có nghĩa mọi database đều có hàm đó.

## 2. Các hàm chuẩn thường dùng trong JPQL

Trước khi gọi hàm riêng của database, hãy kiểm tra xem JPQL đã có hàm chuẩn phù hợp chưa. Những hàm sau thuộc nhóm chức năng phổ biến của JPQL:

| Nhóm | Hàm | Mục đích |
|---|---|---|
| Chuỗi | `CONCAT(a, b)` | Nối chuỗi |
| Chuỗi | `SUBSTRING(s, start, length)` | Lấy một phần chuỗi |
| Chuỗi | `TRIM(s)` | Loại bỏ khoảng trắng ở đầu/cuối theo quy tắc trim |
| Chuỗi | `LOWER(s)`, `UPPER(s)` | Chuyển chữ thường/chữ hoa |
| Chuỗi | `LENGTH(s)` | Lấy độ dài chuỗi |
| Chuỗi | `LOCATE(search, source)` | Tìm vị trí chuỗi con |
| Số | `ABS(n)` | Giá trị tuyệt đối |
| Số | `SQRT(n)` | Căn bậc hai |
| Số | `MOD(n, divisor)` | Phần dư |
| Ngày giờ | `CURRENT_DATE` | Ngày hiện tại của database |
| Ngày giờ | `CURRENT_TIME` | Giờ hiện tại của database |
| Ngày giờ | `CURRENT_TIMESTAMP` | Thời điểm hiện tại của database |
| NULL | `COALESCE(a, b, ...)` | Lấy biểu thức đầu tiên khác NULL |
| NULL | `NULLIF(a, b)` | Trả về NULL nếu hai biểu thức bằng nhau |
| Collection | `SIZE(collection)` | Số phần tử trong collection |
| Collection | `INDEX(alias)` | Chỉ số của phần tử trong một quan hệ list có thứ tự, khi mapping hỗ trợ |
| Tổng hợp | `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` | Đếm, tính tổng, trung bình, nhỏ nhất, lớn nhất |

Ví dụ repository dùng hàm chuẩn:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<Customer> findByNameContainingIgnoreCase(String keyword);

    @Query("""
        select c
        from Customer c
        where lower(c.email) = lower(:email)
    """)
    Optional<Customer> findByEmailIgnoreCase(
        @Param("email") String email
    );

    @Query("""
        select coalesce(c.displayName, c.legalName)
        from Customer c
        where c.id = :id
    """)
    Optional<String> findPreferredName(@Param("id") Long id);
}
~~~

`LOWER`, `COALESCE` và các hàm chuẩn giúp truy vấn dễ đọc và thường có tính khả chuyển tốt hơn hàm riêng của database. Tuy vậy, kết quả thực tế vẫn có thể chịu ảnh hưởng bởi collation, kiểu dữ liệu, cách database xử lý chuỗi và NULL.

Một số chi tiết cú pháp JPQL có quy tắc riêng. Ví dụ, vị trí trong `SUBSTRING` và `LOCATE` được xác định theo ngữ nghĩa JPQL; không nên tự giả định mọi hàm của JPQL giống hệt hàm cùng tên trong một dialect SQL.

## 3. FUNCTION trong JPQL là gì?

JPA 2.1 bổ sung cú pháp `FUNCTION` để gọi một hàm do database cung cấp:

~~~text
FUNCTION('function_name', argument1, argument2, ...)
~~~

Tên hàm được truyền dưới dạng chuỗi literal; các đối số tiếp theo là biểu thức JPQL, tham số hoặc literal phù hợp với chữ ký của hàm database.

Ví dụ, PostgreSQL có extension `unaccent` để loại dấu khỏi chuỗi. Nếu extension đã được cài đặt và hàm khả dụng trong schema/search path của kết nối:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select c
        from Customer c
        where function('unaccent', lower(c.name))
          like function(
              'unaccent',
              lower(concat('%', :keyword, '%'))
          )
    """)
    List<Customer> searchNameIgnoringAccents(
        @Param("keyword") String keyword
    );
}
~~~

Truy vấn trên:

1. Chuyển tên khách hàng về chữ thường bằng hàm chuẩn `LOWER`.
2. Gọi hàm PostgreSQL `unaccent` để chuẩn hóa dấu.
3. Tạo mẫu tìm kiếm có ký tự `%` bằng `CONCAT`.
4. Dùng `LIKE` để tìm chuỗi con.

Ví dụ, từ khóa `Nguyen` có thể tìm được tên `Nguyễn` tùy cấu hình extension và dữ liệu. Đây là ví dụ phụ thuộc PostgreSQL; database khác có thể không có hàm `unaccent` hoặc có cách triển khai khác.

Với PostgreSQL, extension cần được cài đặt trước khi truy vấn:

~~~sql
CREATE EXTENSION IF NOT EXISTS unaccent;
~~~

Lệnh này cần quyền phù hợp và phải được thực hiện trong đúng database. Nếu extension chưa có hoặc hàm không nằm trong schema search path, truy vấn sẽ lỗi dù cú pháp JPQL hợp lệ.

### FUNCTION không phải cú pháp SQL tùy ý

`FUNCTION` chỉ cho phép gọi hàm trong biểu thức truy vấn theo quy tắc JPA/provider. Nó không biến JPQL thành SQL đầy đủ và không cho phép chèn tùy ý một đoạn SQL vào truy vấn.

Tên hàm phải được viết tường minh trong truy vấn. Không thể coi tên hàm là một giá trị thông thường để bind như `:functionName`. Nếu ứng dụng cần lựa chọn một trong vài hàm, hãy chọn bằng logic Java từ danh sách cho phép và dùng các truy vấn/cấu hình đã xác định trước.

## 4. FUNCTION và kiểu dữ liệu trả về

Khi gọi hàm database, cần bảo đảm kiểu kết quả phù hợp với vị trí sử dụng và kiểu trả về của repository.

Ví dụ:

~~~java
@Query("""
    select function('date_trunc', 'day', o.createdAt)
    from PurchaseOrder o
    where o.id = :id
""")
Optional<LocalDateTime> findCreatedDay(@Param("id") Long id);
~~~

Ví dụ này minh họa hàm PostgreSQL `date_trunc`, trả về giá trị timestamp đã được cắt tới đầu ngày. Kiểu Java thực tế phải phù hợp với mapping thời gian, driver và provider đang dùng; có thể cần điều chỉnh thành `Timestamp`, `LocalDateTime` hoặc kiểu projection tương ứng theo phiên bản.

Một hàm trả về số, chuỗi, ngày giờ, JSON hoặc kiểu database đặc biệt có thể cần chuyển đổi trước khi ánh xạ sang Java. Nếu provider không suy luận được kiểu trả về, truy vấn có thể thất bại khi phân tích hoặc khi đọc kết quả.

Khi thiết kế repository, hãy xác định:

- Hàm database trả về kiểu SQL nào?
- JDBC driver biểu diễn kiểu đó ra sao?
- JPA provider có hỗ trợ ánh xạ kiểu đó không?
- Phương thức repository đang khai báo kiểu Java nào?
- Kết quả có thể là NULL hay không?

Không nên khai báo `List<String>` chỉ vì muốn kết quả là chuỗi. Hãy kiểm tra kiểu trả về thật của hàm và mapping phù hợp.

## 5. Gọi hàm qua Criteria API

Nếu truy vấn được xây dựng động bằng Criteria API, có thể gọi hàm bằng `CriteriaBuilder.function()`.

Chữ ký thường dùng:

~~~java
<T> Expression<T> function(
    String name,
    Class<T> type,
    Expression<?>... args
)
~~~

Ví dụ gọi hàm PostgreSQL `unaccent` trong một truy vấn Criteria:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<Customer> query = cb.createQuery(Customer.class);
Root<Customer> customer = query.from(Customer.class);
ParameterExpression<String> keyword =
    cb.parameter(String.class, "keyword");

Expression<String> normalizedName = cb.function(
    "unaccent",
    String.class,
    cb.lower(customer.get("name"))
);

Expression<String> normalizedKeyword = cb.function(
    "unaccent",
    String.class,
    cb.lower(keyword)
);

Expression<String> pattern = cb.concat(
    cb.concat(cb.literal("%"), normalizedKeyword),
    cb.literal("%")
);

query.select(customer).where(cb.like(normalizedName, pattern));

List<Customer> result = entityManager.createQuery(query)
    .setParameter("keyword", keywordValue)
    .getResultList();
~~~

`String.class` mô tả kiểu Java mong đợi của biểu thức trả về. Provider vẫn phải biết cách tạo SQL và database phải có hàm tương ứng. Ví dụ này là phần thân minh họa của một custom repository method; ứng dụng cần khai báo các biến, import và dependency tương ứng.

Trong Criteria API:

- Dùng `cb.function()` khi cần gọi hàm database không có phương thức Criteria chuẩn tương ứng.
- Dùng `cb.lower()`, `cb.upper()`, `cb.concat()`, `cb.length()` và các phương thức chuẩn khi có thể.
- Dùng `cb.parameter()` nếu muốn khai báo parameter rõ ràng.
- Không nối dữ liệu người dùng vào tên hàm hoặc cấu trúc SQL.

Với dữ liệu đầu vào có ký tự `%` hoặc `_`, hãy xác định chúng là wildcard hay ký tự cần tìm theo nghĩa đen và xử lý escape tương ứng.

## 6. Khi nào nên dùng native SQL?

Có những truy vấn phụ thuộc sâu vào database hoặc khó biểu đạt rõ ràng bằng JPQL. Khi đó, Spring Data JPA cho phép dùng native SQL qua `@Query(nativeQuery = true)`.

Ví dụ với PostgreSQL:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query(
        value = """
            select distinct lower(unaccent(name))
            from customer
            where active = true
            order by lower(unaccent(name))
        """,
        nativeQuery = true
    )
    List<String> findNormalizedActiveNames();
}
~~~

Truy vấn native dùng tên bảng và cột trong database, không dùng tên entity và thuộc tính Java. Nó có thể sử dụng hàm, toán tử, kiểu dữ liệu và cú pháp riêng của PostgreSQL.

Chọn native SQL khi:

- Truy vấn cần tính năng chỉ database đó hỗ trợ.
- Cần dùng CTE, window function hoặc cú pháp SQL phức tạp mà JPQL/provider không hỗ trợ thuận tiện.
- Cần kiểm soát chính xác SQL được gửi xuống database.
- Truy vấn tận dụng kiểu dữ liệu hoặc toán tử riêng như JSONB, full-text search hoặc toán tử địa lý.

Đổi lại, native SQL làm tăng phụ thuộc vào schema và dialect. Đổi database có thể yêu cầu viết lại truy vấn, projection, kiểu tham số hoặc cách phân trang.

### Native query với phân trang

Khi dùng `Page<T>` và truy vấn native phức tạp, nên khai báo `countQuery` rõ ràng:

~~~java
@Query(
    value = """
        select c.*
        from customer c
        where lower(unaccent(c.name)) like lower(unaccent(:pattern))
        order by c.id
    """,
    countQuery = """
        select count(*)
        from customer c
        where lower(unaccent(c.name)) like lower(unaccent(:pattern))
    """,
    nativeQuery = true
)
Page<Customer> searchByName(
    @Param("pattern") String pattern,
    Pageable pageable
);
~~~

Truy vấn đếm phải đếm đúng tập bản ghi mà truy vấn nội dung trả về. Nếu truy vấn chính có `DISTINCT`, JOIN hoặc GROUP BY, `countQuery` phải phản ánh cùng định nghĩa phần tử và loại bỏ trùng thích hợp.

## 7. Giới hạn tính khả chuyển của truy vấn

Tính khả chuyển (portability) là khả năng chạy cùng một ứng dụng hoặc truy vấn trên các JPA provider hay hệ quản trị cơ sở dữ liệu khác nhau mà không phải sửa mã.

Có thể xem tính khả chuyển ở ba mức:

| Mức | Ví dụ | Khả năng di chuyển |
|---|---|---|
| Hàm và cú pháp JPQL chuẩn | `LOWER`, `CONCAT`, `COALESCE`, `COUNT` | Thường cao giữa các provider/database tương thích JPA |
| Cú pháp gọi hàm `FUNCTION` | `FUNCTION('unaccent', ...)` | Cú pháp gọi được JPA chuẩn hóa; tên và hành vi hàm vẫn phụ thuộc database |
| Native SQL hoặc hàm riêng | `unaccent`, `date_trunc`, JSONB operator | Phụ thuộc mạnh vào database, dialect và extension |

`FUNCTION` là cú pháp chuẩn của JPA, nhưng tên hàm bên trong thường không portable. Ví dụ:

- PostgreSQL có `date_trunc`.
- MySQL có các hàm ngày giờ và định dạng như `DATE_FORMAT`.
- SQL Server có `DATEADD` và `DATEDIFF`.
- PostgreSQL có kiểu JSONB và các hàm/toán tử JSON riêng.
- Các hệ quản trị khác có thể dùng tên hàm, thứ tự tham số hoặc kiểu kết quả khác.

Một truy vấn dùng `FUNCTION('date_trunc', ...)` có thể chạy trên PostgreSQL nhưng thất bại trên MySQL vì MySQL không có hàm cùng tên và chữ ký tương ứng.

### Tính khả chuyển còn phụ thuộc vào ngữ nghĩa

Ngay cả khi hai database có hàm cùng tên, kết quả vẫn có thể khác vì:

- Collation và quy tắc so sánh chuỗi.
- Múi giờ của session và kiểu timestamp có/không có timezone.
- Cách làm tròn số và độ chính xác decimal.
- Cách chuyển đổi kiểu dữ liệu ngầm định.
- Cách xử lý NULL, chuỗi rỗng và giá trị không hợp lệ.
- Quy tắc so sánh chữ hoa/thường, dấu và ký tự Unicode.

Do đó, chỉ kiểm tra truy vấn có chạy không là chưa đủ. Cần kiểm tra kết quả trên dữ liệu đại diện của từng hệ quản trị mục tiêu.

## 8. Đăng ký hàm tùy chỉnh trong JPA provider

Khi dùng Hibernate, một số hàm có thể được nhận diện sẵn theo dialect. Với hàm tự định nghĩa hoặc hàm cần thông tin kiểu dữ liệu rõ ràng, có thể phải đăng ký hàm với provider.

Trong Hibernate 6, cơ chế mở rộng có thể dùng `FunctionContributor` hoặc cấu hình dialect phù hợp phiên bản. Cơ chế đăng ký cho phép provider biết:

- Tên hàm và cách render thành SQL.
- Số lượng và kiểu đối số.
- Kiểu dữ liệu trả về.
- Quy tắc xử lý cú pháp hoặc chuyển đổi đối số.

Đây là API riêng của Hibernate, không phải JPA chuẩn. Nếu ứng dụng thay Hibernate bằng EclipseLink hoặc provider khác, phần đăng ký này có thể phải viết lại.

Không nên tạo custom dialect chỉ để gọi một hàm đơn giản nếu `FUNCTION` đã đủ. Đăng ký hàm hữu ích khi truy vấn cần type checking tốt hơn, hàm được dùng nhiều nơi, cú pháp SQL cần chuyển đổi theo dialect hoặc muốn cung cấp tên hàm nhất quán cho ứng dụng.

Khi nâng cấp Hibernate, hãy kiểm tra API đăng ký hàm theo đúng phiên bản. API extension của provider có thể thay đổi giữa các major version.

## 9. Tham số truy vấn và an toàn đầu vào

Các giá trị do người dùng cung cấp phải được bind bằng named parameter hoặc positional parameter:

~~~java
@Query("""
    select c
    from Customer c
    where function('unaccent', lower(c.name))
      like function('unaccent', lower(:pattern))
""")
List<Customer> search(@Param("pattern") String pattern);
~~~

Binding bảo vệ giá trị tham số khỏi việc bị diễn giải thành một phần cấu trúc truy vấn và giúp provider truyền kiểu dữ liệu phù hợp.

Tên hàm, tên bảng, tên cột và toán tử là thành phần cấu trúc; chúng không thể được bind như một giá trị thông thường. Không nối trực tiếp đầu vào người dùng vào chuỗi JPQL/native SQL để tạo tên hàm hoặc đoạn SQL.

Nếu cần sắp xếp theo một trong nhiều trường, hãy ánh xạ lựa chọn người dùng sang danh sách thuộc tính hợp lệ đã định nghĩa trong ứng dụng. Không đưa một chuỗi tùy ý từ request vào SQL.

Với `LIKE`, cần xác định ý nghĩa của `%` và `_`. Nếu người dùng nhập hai ký tự này, database thường hiểu chúng là wildcard. Khi muốn tìm đúng ký tự, cần escape theo cú pháp `LIKE` và chỉ rõ ký tự escape.

## 10. Hiệu năng: hàm trên cột có thể ảnh hưởng index

Một truy vấn như:

~~~sql
SELECT *
FROM customer
WHERE LOWER(name) = LOWER(?);
~~~

có thể không sử dụng index B-tree thông thường trên cột `name` theo cách mong đợi, vì database phải đánh giá biểu thức `LOWER(name)` trên giá trị cột. Khả năng tối ưu phụ thuộc optimizer và database.

Một số cách xử lý:

- Tạo expression/function-based index phù hợp với biểu thức truy vấn, nếu database hỗ trợ.
- Dùng cột chuẩn hóa được cập nhật có kiểm soát hoặc generated column.
- Chuẩn hóa dữ liệu khi ghi nếu quy tắc nghiệp vụ cho phép.
- Kiểm tra execution plan với dữ liệu có quy mô gần production.
- Chỉ gọi hàm trên cột khi cần thiết; nếu có thể chuyển đổi giá trị tham số trước khi bind mà vẫn giữ đúng ngữ nghĩa, hãy cân nhắc cách đó.

Ví dụ PostgreSQL cho expression index trên `lower(name)`:

~~~sql
CREATE INDEX idx_customer_lower_name
ON customer (lower(name));
~~~

Index này có thể hỗ trợ truy vấn có cùng biểu thức `lower(name)`. Nó không tự động hỗ trợ mọi biểu thức khác như `unaccent(lower(name))`. Với hàm riêng hoặc hàm không được đánh dấu immutable, database có thể có giới hạn khi tạo expression index; cần kiểm tra tài liệu của hệ quản trị.

Đừng thêm index chỉ dựa trên hình thức truy vấn. Hãy dùng `EXPLAIN` hoặc công cụ execution plan tương ứng để xác nhận database thực sự dùng index và chi phí có giảm.

## 11. Ngày giờ, NULL và kiểu dữ liệu cần kiểm tra

Các hàm database có thể cho kết quả khác nhau giữa môi trường vì phụ thuộc session hoặc kiểu dữ liệu.

### Ngày giờ và timezone

`CURRENT_DATE`, `CURRENT_TIME` và `CURRENT_TIMESTAMP` được đánh giá theo database/session. Kết quả có thể khác với thời gian của JVM nếu server và database dùng timezone khác nhau.

Khi gọi hàm cắt ngày hoặc chuyển timezone, hãy xác định rõ:

- Cột đang lưu `DATE`, `TIMESTAMP` hay timestamp có timezone.
- Database session đang dùng timezone nào.
- Ứng dụng ánh xạ sang `LocalDate`, `LocalDateTime`, `OffsetDateTime` hay `Instant`.
- Điều kiện lọc có nên dùng khoảng thời gian `[start, end)` để tránh sai lệch ở biên ngày hay không.

Không nên mặc định một timestamp luôn mang timezone chỉ vì Java dùng một kiểu thời gian cụ thể.

### NULL và biểu thức điều kiện

SQL dùng logic ba giá trị: TRUE, FALSE và UNKNOWN. Nếu một đối số của hàm là NULL, hàm có thể trả NULL theo quy tắc của hàm đó; điều kiện so sánh với NULL thường không cho kết quả TRUE.

Dùng `COALESCE` khi nghiệp vụ cần giá trị thay thế:

~~~java
@Query("""
    select coalesce(c.nickname, c.fullName)
    from Customer c
""")
List<String> findDisplayNames();
~~~

Hãy xác định giá trị thay thế có ý nghĩa nghiệp vụ và có cùng kiểu tương thích với các biểu thức còn lại.

### Kiểu số và độ chính xác

Các hàm toán học hoặc aggregate có thể trả về kiểu khác với kiểu đầu vào. Chẳng hạn phép tính trên số nguyên có thể được nâng kiểu, còn `AVG` có quy tắc kiểu trả về theo đặc tả/provider. Với `BigDecimal`, tiền tệ và dữ liệu cần độ chính xác, hãy khai báo kiểu Java, precision/scale và kiểm thử kết quả làm tròn.

## 12. Cách kiểm tra truy vấn gọi hàm

Khi một truy vấn dùng `FUNCTION` hoặc native SQL hoạt động khác mong đợi, hãy kiểm tra theo trình tự:

1. Xác nhận database thực sự có hàm và extension cần thiết.
2. Kiểm tra đúng schema/search path và quyền thực thi.
3. Kiểm tra tên hàm, số lượng, thứ tự và kiểu đối số.
4. Xác nhận kiểu kết quả của hàm khớp với kiểu projection/repository.
5. Bật log SQL và bind parameter trong môi trường phát triển để xem SQL do provider sinh ra.
6. Chạy câu SQL tương ứng trực tiếp trên database với các giá trị đại diện.
7. Kiểm tra NULL, chuỗi rỗng, Unicode, timezone và các giá trị biên.
8. Xem execution plan nếu truy vấn chậm.
9. Chạy integration test trên đúng hệ quản trị mục tiêu, tốt nhất dùng Testcontainers hoặc môi trường database tương đương.

Unit test chỉ mock repository không thể xác nhận hàm database có tồn tại hoặc trả kết quả đúng. Với truy vấn phụ thuộc hàm, cần integration test thực sự đi qua JPA provider và database.

## 13. Chọn JPQL chuẩn, FUNCTION, Criteria hay native SQL?

| Nhu cầu | Lựa chọn |
|---|---|
| Xử lý chuỗi, số, NULL, ngày giờ thông dụng | Hàm JPQL chuẩn |
| Gọi một hàm database cụ thể trong truy vấn tĩnh | `FUNCTION('name', ...)` |
| Xây dựng điều kiện động bằng Criteria/Specification | `CriteriaBuilder.function()` |
| Dùng cú pháp SQL phức tạp hoặc tính năng riêng của database | Native SQL |
| Hàm riêng được dùng rộng và cần kiểu trả về/type checking rõ | Đăng ký hàm ở JPA provider, nếu provider hỗ trợ |
| Cần chạy trên nhiều database | Ưu tiên JPQL chuẩn; cô lập và kiểm thử phần phụ thuộc database |

Nếu phải hỗ trợ nhiều hệ quản trị, có thể định nghĩa một repository interface chung và tách phần truy vấn riêng theo từng database/dialect. Cũng có thể dùng các implementation repository khác nhau được chọn theo cấu hình. Cách tổ chức này giữ phần nghiệp vụ ổn định trong khi phần truy vấn đặc thù được kiểm soát tại một nơi.

## 14. Ghi nhớ

- JPQL có nhiều hàm chuẩn như `LOWER`, `CONCAT`, `SUBSTRING`, `COALESCE`, `COUNT` và các hàm số/ngày giờ.
- `FUNCTION('function_name', ...)` là cú pháp JPA để gọi hàm database; tên hàm và hành vi vẫn phụ thuộc hệ quản trị.
- `CriteriaBuilder.function()` là cách gọi hàm trong Criteria API.
- Native SQL phù hợp khi cần cú pháp hoặc tính năng riêng, nhưng làm giảm tính khả chuyển.
- Kiểu trả về của hàm phải tương thích với JDBC, JPA provider và kiểu Java của repository.
- Tên hàm và cấu trúc SQL không phải giá trị bind parameter; chỉ bind dữ liệu đầu vào.
- Hàm trên cột có thể làm index thường khó được sử dụng; xem xét expression index hoặc generated column và kiểm tra execution plan.
- Khác biệt về collation, NULL, timezone, kiểu số và extension có thể làm kết quả khác giữa database.
- Truy vấn phụ thuộc hàm cần integration test trên database mục tiêu.

Hãy ưu tiên hàm JPQL chuẩn cho logic phổ biến. Khi cần hàm riêng, dùng `FUNCTION` hoặc Criteria API cho truy vấn phù hợp, và chuyển sang native SQL khi cú pháp database là phần thiết yếu của giải pháp. Ghi rõ database/provider được hỗ trợ và kiểm thử kết quả, kiểu dữ liệu cùng hiệu năng trên môi trường mục tiêu.