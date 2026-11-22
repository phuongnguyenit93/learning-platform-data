# Liên kết tham số bằng @Param

## 1. Vì sao cần liên kết tham số trong truy vấn khai báo?

Spring Data R2DBC cho phép khai báo truy vấn ngay trên repository interface bằng annotation @Query. Trong câu SQL, bạn thường cần truyền giá trị từ tham số của phương thức Java vào điều kiện lọc, giá trị cập nhật hoặc biểu thức khác.

Ví dụ, repository cần tìm khách hàng theo email:

~~~java
@Query("SELECT id, full_name, email FROM customers WHERE email = :email")
Mono<Customer> findCustomerByEmail(@Param("email") String email);
~~~

Trong ví dụ này có hai tên thuộc hai ngữ cảnh:

- email trong @Param("email") là tên tham số logic được khai báo ở phương thức Java.
- :email trong câu SQL là placeholder có tên mà Spring Data dùng để liên kết giá trị vào truy vấn.

Khi phương thức được gọi với một địa chỉ email, Spring Data lấy giá trị của tham số Java và bind vào placeholder tương ứng. Giá trị được truyền như một tham số của câu lệnh, không được nối trực tiếp vào chuỗi SQL.

Annotation @Param thuộc package org.springframework.data.repository.query. Nó đặc biệt hữu ích với các phương thức repository có @Query sử dụng named parameters.

## 2. @Param hoạt động như thế nào?

### 2.1. Đặt tên cho tham số phương thức

Ví dụ:

~~~java
import org.springframework.data.repository.query.Param;
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("""
        SELECT id, full_name, email
        FROM customers
        WHERE email = :email
        """)
    Mono<Customer> findByEmailAddress(
        @Param("email") String emailAddress
    );
}
~~~

Tên tham số Java là emailAddress. Placeholder trong SQL lại là :email. Annotation @Param("email") nói với Spring Data rằng giá trị của emailAddress phải được liên kết với placeholder có tên email.

Tên trong @Param không bắt buộc phải giống tên biến Java. Điều cần bảo đảm là chuỗi trong @Param khớp với tên placeholder trong câu SQL.

Luồng liên kết có thể hình dung như sau:

~~~text
Lời gọi repository
findByEmailAddress("a@example.com")
              |
              v
Tham số Java: emailAddress
              |
              v
@Param("email")
              |
              v
Placeholder SQL: :email
              |
              v
Bind giá trị vào câu lệnh
              |
              v
Database thực thi truy vấn
~~~

### 2.2. Tên phải khớp chính xác

Giả sử SQL có placeholder :customerId:

~~~java
@Query("""
    SELECT id, customer_id, status
    FROM orders
    WHERE customer_id = :customerId
    """)
Flux<Order> findByCustomer(
    @Param("customerId") Long id
);
~~~

Cách khai báo trên liên kết đúng dù tên biến Java là id. Nếu viết @Param("customer_id") trong khi SQL dùng :customerId, Spring Data không thể tìm thấy tham số logic tương ứng. Tùy thời điểm phát hiện và phiên bản, lỗi có thể xuất hiện khi tạo query hoặc khi thực thi.

Nên chọn một quy ước đặt tên dễ đọc và dùng nhất quán. Thông thường, tên placeholder nên mô tả ý nghĩa của giá trị, ví dụ :customerId, :status hoặc :createdAfter.

### 2.3. Nhiều tham số trong một truy vấn

Một phương thức có thể nhận nhiều tham số. Mỗi placeholder có tên được liên kết với một tham số bằng @Param tương ứng:

~~~java
@Query("""
    SELECT id, full_name, email
    FROM customers
    WHERE first_name = :firstName
      AND last_name = :lastName
      AND active = :active
    """)
Flux<Customer> searchCustomers(
    @Param("firstName") String firstName,
    @Param("lastName") String lastName,
    @Param("active") Boolean active
);
~~~

Bảng liên kết:

| Tham số Java | @Param | Placeholder SQL |
|---|---|---|
| firstName | firstName | :firstName |
| lastName | lastName | :lastName |
| active | active | :active |

Mỗi placeholder phải có một giá trị tương ứng. Không nên dựa vào thứ tự tham số trong method để đoán tên placeholder khi SQL đã dùng named parameters.

## 3. Khi nào cần dùng @Param?

### 3.1. Dùng với @Query có named parameters

Trường hợp điển hình:

~~~java
@Query("""
    SELECT id, status, created_at
    FROM orders
    WHERE customer_id = :customerId
      AND status = :status
    """)
Flux<Order> findOrders(
    @Param("customerId") Long customerId,
    @Param("status") OrderStatus status
);
~~~

@Param làm rõ quan hệ giữa tên placeholder và tham số Java. Đây là cách khai báo tường minh, dễ đọc và ít phụ thuộc vào metadata biên dịch.

### 3.2. Có thể dựa vào tên tham số Java trong một số cấu hình

Spring Data có thể khám phá tên tham số từ metadata của class file nếu quá trình biên dịch lưu tên tham số, ví dụ sử dụng tùy chọn javac -parameters. Khi đó, trong những trường hợp được hỗ trợ, tên tham số Java có thể được dùng để khớp với named placeholder mà không cần ghi @Param cho từng tham số.

Tuy nhiên, điều này phụ thuộc cấu hình biên dịch, phiên bản Spring và cách parameter name discovery hoạt động. Nếu tên tham số không có trong bytecode, Spring có thể không suy ra được tên cần thiết.

Vì vậy, với repository query dùng named parameters, khai báo @Param tường minh thường dễ bảo trì hơn, nhất là khi:

- Tên biến Java khác tên placeholder SQL.
- Dự án có nhiều module với cấu hình biên dịch khác nhau.
- Code cần hoạt động nhất quán giữa các môi trường build.
- Phương thức có nhiều tham số hoặc tên tham số dễ gây nhầm lẫn.

### 3.3. Không cần @Param cho query method được suy ra từ tên

Với derived query method, Spring Data suy ra điều kiện từ tên phương thức và liên kết các đối số theo thứ tự/property được mô tả trong method.

Ví dụ:

~~~java
Flux<Customer> findByFirstNameAndLastName(
    String firstName,
    String lastName
);
~~~

Ở đây không cần @Param vì không có chuỗi SQL với named placeholder do bạn tự viết. Spring Data phân tích tên method và các tham số để tạo truy vấn.

Tương tự:

~~~java
Mono<Customer> findByEmail(String email);

Flux<Order> findByCustomerIdAndStatus(
    Long customerId,
    OrderStatus status
);
~~~

Không thêm @Param chỉ vì method có tham số. Hãy dùng nó khi cần liên kết tham số với tên placeholder trong query khai báo hoặc trong những API repository có hỗ trợ parameter name annotation.

### 3.4. @Param không phải annotation cho mọi kiểu truy vấn

@Param không thay thế cơ chế bind của DatabaseClient. Nếu viết SQL trực tiếp bằng DatabaseClient, bạn thường gọi bind() trên spec của câu lệnh:

~~~java
return databaseClient.sql("""
        SELECT id, full_name, email
        FROM customers
        WHERE email = :email
        """)
    .bind("email", emailAddress)
    .map((row, metadata) -> mapCustomer(row))
    .one();
~~~

Ở đây tên email được liên kết qua .bind("email", emailAddress), không phải qua @Param. @Param gắn với tham số của repository method; DatabaseClient dùng API bind riêng của nó.

## 4. Named parameters và placeholder trong SQL

### 4.1. Cú pháp :name

Trong query khai báo của Spring Data R2DBC, named parameter thường được viết với dấu hai chấm đứng trước tên:

~~~sql
SELECT id, full_name
FROM customers
WHERE email = :email
~~~

Placeholder :email là vị trí nhận giá trị. Nó không phải tên cột và không làm thay đổi cấu trúc câu SQL.

Ví dụ khác:

~~~sql
SELECT id, status
FROM orders
WHERE customer_id = :customerId
  AND status = :status
  AND created_at >= :createdAfter
~~~

Tương ứng, repository method có thể khai báo:

~~~java
@Query("""
    SELECT id, status
    FROM orders
    WHERE customer_id = :customerId
      AND status = :status
      AND created_at >= :createdAfter
    """)
Flux<Order> searchOrders(
    @Param("customerId") Long customerId,
    @Param("status") String status,
    @Param("createdAfter") Instant createdAfter
);
~~~

### 4.2. Named parameters được chuyển thành bind markers của driver

R2DBC SPI và từng driver có quy tắc bind marker riêng. Ví dụ, một driver có thể dùng marker theo vị trí, driver khác có thể dùng cú pháp marker khác.

Spring Data R2DBC làm việc với named parameters ở lớp truy vấn và chuyển chúng sang bind markers mà dialect/driver sử dụng. Vì thế, khi viết @Query theo abstraction của Spring Data R2DBC, bạn thường dùng :name thay vì tự viết cú pháp marker riêng của một driver.

Điều này giúp câu query dễ đọc và giảm phụ thuộc vào cách đánh số tham số của driver. Tuy vậy, SQL vẫn phải hợp lệ theo dialect của database. Named parameter không biến cú pháp SQL riêng của PostgreSQL, MySQL hay SQL Server thành cú pháp dùng chung.

### 4.3. Dùng cùng một tham số ở nhiều vị trí

Một giá trị có thể được dùng ở nhiều điều kiện trong cùng câu query:

~~~java
@Query("""
    SELECT id, full_name, email
    FROM customers
    WHERE email = :email
       OR backup_email = :email
    """)
Mono<Customer> findByPrimaryOrBackupEmail(
    @Param("email") String email
);
~~~

Cả hai placeholder cùng tên email nhận một giá trị từ cùng tham số. Nếu cần hai giá trị độc lập, hãy đặt hai tên riêng và khai báo hai @Param.

### 4.4. Đừng nhầm tên tham số với tên cột

Ví dụ:

~~~java
@Query("""
    SELECT id, full_name
    FROM customers
    WHERE customer_code = :code
    """)
Mono<Customer> findByCode(
    @Param("code") String customerCode
);
~~~

customer_code là tên cột trong database. code là tên placeholder. customerCode là tên biến Java. Ba tên có thể khác nhau, miễn là mapping và liên kết tham số được khai báo đúng.

## 5. Ví dụ thực tế với nhiều kiểu tham số

### 5.1. Tìm theo ID và trạng thái

~~~java
@Query("""
    SELECT id, customer_id, status, created_at
    FROM orders
    WHERE customer_id = :customerId
      AND status = :status
    ORDER BY created_at DESC
    """)
Flux<Order> findByCustomerAndStatus(
    @Param("customerId") Long customerId,
    @Param("status") String status
);
~~~

Service có thể gọi:

~~~java
public Flux<Order> getPaidOrders(Long customerId) {
    return orderRepository.findByCustomerAndStatus(
        customerId,
        "PAID"
    );
}
~~~

Nếu status là enum, có thể khai báo tham số OrderStatus và dựa vào conversion đã cấu hình, miễn là kiểu cột và converter tương thích. Với query thủ công, cần kiểm tra cách bind enum trong phiên bản Spring Data/driver đang dùng.

### 5.2. Tìm theo khoảng thời gian

~~~java
@Query("""
    SELECT id, customer_id, status, created_at
    FROM orders
    WHERE created_at >= :fromTime
      AND created_at < :toTime
    ORDER BY created_at
    """)
Flux<Order> findCreatedBetween(
    @Param("fromTime") Instant fromTime,
    @Param("toTime") Instant toTime
);
~~~

Sử dụng khoảng nửa mở [fromTime, toTime) giúp ghép các khoảng thời gian liên tiếp mà không phải xử lý trùng ở ranh giới. Kiểu Instant cần được chuyển đổi tương thích với kiểu timestamp của database và driver.

### 5.3. Tìm kiếm với LIKE

Bạn có thể bind cả mẫu tìm kiếm:

~~~java
@Query("""
    SELECT id, full_name, email
    FROM customers
    WHERE full_name LIKE :pattern
    """)
Flux<Customer> searchByName(
    @Param("pattern") String pattern
);
~~~

Service tạo pattern:

~~~java
public Flux<Customer> search(String keyword) {
    String pattern = "%" + keyword + "%";
    return customerRepository.searchByName(pattern);
}
~~~

Giá trị keyword vẫn được bind như dữ liệu. Dấu phần trăm là thành phần của giá trị pattern, không phải nối keyword vào câu SQL.

Nếu cần tìm kiếm không phân biệt hoa thường, cú pháp phụ thuộc database, ví dụ ILIKE trên PostgreSQL hoặc LOWER(...) ở những hệ quản trị hỗ trợ biểu thức tương ứng. Hãy dùng cú pháp theo dialect thực tế.

## 6. Liên kết collection với điều kiện IN

Một truy vấn có thể cần lọc theo một tập ID hoặc một tập trạng thái. Ví dụ:

~~~java
@Query("""
    SELECT id, customer_id, status
    FROM orders
    WHERE status IN (:statuses)
    """)
Flux<Order> findByStatuses(
    @Param("statuses") Collection<String> statuses
);
~~~

Khi dùng named parameter với collection trong ngữ cảnh IN, cơ chế mở rộng tham số của Spring Data R2DBC có thể tạo các bind marker tương ứng cho các phần tử trong collection. Điều này giúp tránh phải tự nối danh sách giá trị vào chuỗi SQL.

Ví dụ gọi:

~~~java
List<String> statuses = List.of("PAID", "SHIPPED");

Flux<Order> orders = orderRepository.findByStatuses(statuses);
~~~

### 6.1. Collection rỗng

Collection rỗng là trường hợp cần xử lý rõ. Cú pháp IN với danh sách không có phần tử không có cùng ý nghĩa hoặc không được hỗ trợ đồng nhất ở mọi dialect/driver.

Nếu collection rỗng có nghĩa là không tìm kết quả, có thể xử lý trước khi gọi repository:

~~~java
public Flux<Order> findByStatuses(Collection<String> statuses) {
    if (statuses == null || statuses.isEmpty()) {
        return Flux.empty();
    }

    return orderRepository.findByStatuses(statuses);
}
~~~

Nếu collection rỗng có nghĩa là không áp dụng bộ lọc, hãy thiết kế method/query riêng hoặc xây dựng query theo nhánh rõ ràng. Không nên dựa vào cách database diễn giải IN ().

### 6.2. Collection không đồng nghĩa với một tham số SQL duy nhất

Khi mở rộng collection, mỗi phần tử được bind như một giá trị riêng. Không nối các phần tử thành chuỗi SQL như:

~~~java
String sql = "SELECT * FROM orders WHERE id IN (" + ids + ")";
~~~

Cách nối chuỗi vừa dễ sai cú pháp, vừa có nguy cơ SQL injection nếu dữ liệu đến từ đầu vào bên ngoài. Hãy dùng named collection binding hoặc API query builder được hỗ trợ.

## 7. Giá trị null và điều kiện SQL

Một tham số Java có thể nhận null nếu kiểu tham số cho phép. Tuy nhiên, SQL dùng logic ba giá trị: TRUE, FALSE và UNKNOWN. Biểu thức:

~~~sql
email = :email
~~~

không trở thành phép kiểm tra IS NULL khi email được bind bằng null. So sánh với NULL cho kết quả UNKNOWN, nên hàng không được chọn theo điều kiện WHERE đó.

Nếu cần tìm hàng có email NULL, hãy dùng điều kiện SQL riêng:

~~~sql
WHERE email IS NULL
~~~

Ví dụ repository:

~~~java
@Query("""
    SELECT id, full_name, email
    FROM customers
    WHERE email IS NULL
    """)
Flux<Customer> findWithoutEmail();
~~~

Nếu nghiệp vụ có hai trường hợp: lọc theo email khi có giá trị và lấy tất cả khi null, hãy thiết kế logic có chủ đích. Một biểu thức kiểu:

~~~sql
WHERE (:email IS NULL OR email = :email)
~~~

có thể cần chú ý về kiểu của tham số null và cách database suy luận kiểu bind. Tùy driver, có thể phải khai báo kiểu rõ ràng hoặc tách thành các query riêng. Không nên dùng biểu thức này một cách máy móc mà chưa thử với database thực tế.

Cũng cần phân biệt null với chuỗi rỗng. Một tham số email là "" sẽ tìm chuỗi rỗng nếu điều kiện dùng phép so sánh bằng; nó không tìm các hàng có email NULL.

## 8. @Param và kiểu dữ liệu của tham số

Tên tham số chỉ giải quyết việc liên kết. Giá trị vẫn phải có kiểu mà Spring Data conversion, R2DBC driver và database có thể xử lý.

Ví dụ:

| Kiểu Java | Cột thường gặp | Lưu ý |
|---|---|---|
| Long | BIGINT | ID hoặc số nguyên lớn |
| Integer | INTEGER | Số nguyên |
| BigDecimal | DECIMAL / NUMERIC | Số thập phân cần độ chính xác |
| String | VARCHAR / TEXT | Chuỗi |
| Boolean | BOOLEAN | Tùy hệ quản trị |
| LocalDate | DATE | Ngày |
| LocalDateTime | TIMESTAMP | Ngày giờ không kèm múi giờ |
| Instant | Timestamp phù hợp với driver | Thống nhất quy ước UTC |
| Enum | Chuỗi hoặc kiểu đã cấu hình | Cần conversion tương ứng |

Nếu method nhận Long nhưng cột database là UUID, việc đặt đúng @Param không thể sửa sự không tương thích kiểu. Hãy đồng bộ kiểu Java, kiểu cột và converter.

Ví dụ tham số enum:

~~~java
@Query("""
    SELECT id, status
    FROM orders
    WHERE status = :status
    """)
Flux<Order> findByStatus(
    @Param("status") OrderStatus status
);
~~~

Nếu OrderStatus được lưu theo tên mặc định, Spring Data có thể chuyển enum theo cơ chế conversion mặc định. Nếu enum dùng mã nghiệp vụ riêng, cần converter đọc/ghi đã đăng ký và xác nhận converter áp dụng cho query parameter trong phiên bản đang dùng.

## 9. @Param không thể thay thế tên bảng, tên cột hoặc cú pháp SQL động

Bind parameter chỉ dùng cho giá trị. Không thể dùng placeholder để thay thế tên bảng hoặc tên cột theo cách thông thường.

Ví dụ không hợp lệ về ý nghĩa:

~~~sql
SELECT * FROM :tableName
~~~

Hoặc:

~~~sql
SELECT id, full_name
FROM customers
ORDER BY :columnName
~~~

Các placeholder được bind như literal value. Database không diễn giải giá trị bind thành identifier hoặc từ khóa SQL. Trong trường hợp ORDER BY :columnName, database có thể hiểu đó là một biểu thức giá trị cố định cho mỗi hàng, chứ không phải tên cột để sắp xếp.

Nếu cần chọn cột sắp xếp động, hãy dùng Sort được Spring Data hỗ trợ hoặc ánh xạ đầu vào sang một danh sách identifier đã được cho phép. Ví dụ:

~~~java
Sort sort = switch (requestedSort) {
    case "name" -> Sort.by("fullName");
    case "created" -> Sort.by("createdAt");
    default -> Sort.by("id");
};
~~~

Không ghép trực tiếp tên cột do client gửi vào SQL. Hãy whitelist các lựa chọn hợp lệ trước khi tạo query.

Tương tự, không dùng @Param để thay thế từ khóa như ASC/DESC, toán tử hoặc đoạn SQL. Những thành phần cấu trúc của câu query cần được quyết định từ code tin cậy.

## 10. Parameter binding giúp giảm nguy cơ SQL injection

Không an toàn:

~~~java
String sql = "SELECT * FROM customers WHERE email = '" + email + "'";
return databaseClient.sql(sql);
~~~

Nếu email chứa dấu nháy hoặc nội dung có chủ đích thao túng SQL, câu truy vấn có thể bị thay đổi ngoài ý muốn.

An toàn hơn:

~~~java
@Query("""
    SELECT id, full_name, email
    FROM customers
    WHERE email = :email
    """)
Mono<Customer> findByEmail(@Param("email") String email);
~~~

Spring Data bind giá trị như tham số của câu lệnh. Database xử lý giá trị tách biệt với cấu trúc SQL, nhờ đó giảm nguy cơ dữ liệu đầu vào bị diễn giải thành cú pháp SQL.

Parameter binding không thay thế mọi biện pháp bảo mật. Vẫn cần kiểm tra quyền truy cập, validation nghiệp vụ, giới hạn dữ liệu trả về và whitelist identifier động. Không đưa dữ liệu nhạy cảm vào log SQL hoặc thông báo lỗi gửi cho client.

## 11. Kết hợp @Param với @Modifying

Ngoài SELECT, repository query có thể dùng @Query cho câu lệnh cập nhật hoặc xóa tùy API và phiên bản. Với modifying query, Spring Data R2DBC hỗ trợ annotation @Modifying trong các trường hợp tương ứng.

Ví dụ:

~~~java
@Modifying
@Query("""
    UPDATE orders
    SET status = :status
    WHERE id = :orderId
    """)
Mono<Integer> updateStatus(
    @Param("orderId") Long orderId,
    @Param("status") String status
);
~~~

Trong ví dụ, hai tham số được bind theo tên. Kiểu trả về thường được dùng để nhận số hàng bị ảnh hưởng theo API của phiên bản Spring Data R2DBC.

Một thao tác cập nhật nhiều bản ghi cũng có thể dùng named parameters:

~~~java
@Modifying
@Query("""
    UPDATE orders
    SET status = :newStatus
    WHERE customer_id = :customerId
      AND status = :oldStatus
    """)
Mono<Integer> moveOrdersToNewStatus(
    @Param("customerId") Long customerId,
    @Param("oldStatus") String oldStatus,
    @Param("newStatus") String newStatus
);
~~~

Hãy kiểm tra method signature và yêu cầu annotation trong phiên bản Spring Data đang sử dụng. Nếu nghiệp vụ gồm nhiều câu lệnh phải thành công hoặc thất bại cùng nhau, hãy bao bọc chúng trong reactive transaction.

## 12. @Param trong query có JOIN hoặc subquery

Named parameter hoạt động như nhau khi câu SQL có nhiều bảng. Ví dụ:

~~~java
@Query("""
    SELECT o.id, o.customer_id, o.status, o.created_at
    FROM orders o
    JOIN customers c ON c.id = o.customer_id
    WHERE c.email = :email
      AND o.created_at >= :createdAfter
    """)
Flux<Order> findOrdersForCustomer(
    @Param("email") String email,
    @Param("createdAfter") Instant createdAfter
);
~~~

Tên placeholder không cần trùng alias hoặc tên bảng. email là tham số logic, còn c.email là cột được so sánh.

Subquery cũng dùng được named parameter:

~~~java
@Query("""
    SELECT id, customer_id, status
    FROM orders
    WHERE customer_id IN (
        SELECT id
        FROM customers
        WHERE active = :active
    )
    """)
Flux<Order> findOrdersForActiveCustomers(
    @Param("active") Boolean active
);
~~~

Một placeholder có thể xuất hiện ở vị trí phù hợp trong query. Hãy giữ tên rõ ràng, tránh dùng cùng một tên cho những giá trị nghiệp vụ khác nhau chỉ vì chúng có cùng kiểu Java.

## 13. Những lỗi thường gặp khi dùng @Param

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy named parameter | Tên @Param không khớp placeholder | Đối chiếu chính xác tên trong annotation và SQL |
| Placeholder không có giá trị | SQL có :name nhưng method không có tham số tương ứng | Bổ sung tham số hoặc sửa query |
| Tham số Java có tên khác nhưng bỏ @Param | Spring không có metadata tên tham số cần thiết | Dùng @Param tường minh hoặc bảo đảm build lưu parameter names |
| Dùng @Param cho derived query không cần thiết | Nhầm cơ chế query derivation với @Query | Để Spring suy ra từ tên method và thứ tự tham số |
| Dùng @Param với DatabaseClient.bind() | Nhầm annotation repository với API bind trực tiếp | Dùng .bind("name", value) của DatabaseClient |
| Bind null rồi so sánh bằng = | SQL không xem NULL như giá trị bằng thông thường | Dùng IS NULL hoặc thiết kế nhánh query |
| Bind tên cột hoặc tên bảng | Placeholder chỉ nhận giá trị | Dùng whitelist hoặc Sort cho identifier động |
| IN với collection rỗng | Không có phần tử để mở rộng bind marker | Xử lý collection rỗng trước khi gọi repository |
| Kiểu tham số không tương thích cột | Tên binding đúng nhưng kiểu không phù hợp | Đồng bộ kiểu Java, converter, driver và schema |
| Nối chuỗi đầu vào vào SQL | Dữ liệu bị trộn với cấu trúc câu query | Dùng parameter binding |

## 14. Quy trình khai báo query method có @Param

Khi viết một repository method dùng @Query, hãy thực hiện theo thứ tự:

1. Viết câu SQL với tên bảng và cột đúng theo schema.
2. Đặt named placeholder có ý nghĩa rõ ràng cho mỗi giá trị cần truyền.
3. Khai báo tham số Java với kiểu phù hợp với cột và conversion.
4. Gắn @Param lên từng tham số để liên kết đúng tên placeholder.
5. Chọn kiểu trả về Mono hoặc Flux theo số lượng kết quả.
6. Với UPDATE/DELETE, kiểm tra yêu cầu @Modifying và kiểu kết quả theo phiên bản Spring Data.
7. Không nối dữ liệu đầu vào vào chuỗi SQL.
8. Xử lý rõ null, collection rỗng và các trường hợp dữ liệu biên.
9. Kiểm tra SQL theo dialect và driver thực tế.
10. Viết integration test cho trường hợp tham số hợp lệ, không có kết quả, null nếu được phép, collection rỗng và giá trị có ký tự đặc biệt.

Ví dụ tổng hợp:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    @Query("""
        SELECT id, customer_id, status, created_at
        FROM orders
        WHERE customer_id = :customerId
          AND status = :status
          AND created_at >= :createdAfter
        ORDER BY created_at DESC
        """)
    Flux<Order> searchOrders(
        @Param("customerId") Long customerId,
        @Param("status") String status,
        @Param("createdAfter") Instant createdAfter
    );
}
~~~

Method này có ba tham số, mỗi tham số được liên kết tường minh với một named placeholder. Kết quả là Flux<Order> vì một khách hàng có thể có nhiều đơn hàng thỏa điều kiện.

## 15. Bài tập tự kiểm tra

### Bài 1: Liên kết tên khác nhau

SQL dùng :emailAddress nhưng tham số Java tên email. Hãy khai báo method với @Param.

Gợi ý:

~~~java
@Query("SELECT id, email FROM customers WHERE email = :emailAddress")
Mono<Customer> findByEmail(
    @Param("emailAddress") String email
);
~~~

### Bài 2: Nhiều điều kiện

Viết repository method tìm đơn hàng theo customerId, status và createdAfter.

Gợi ý:

~~~java
@Query("""
    SELECT id, customer_id, status, created_at
    FROM orders
    WHERE customer_id = :customerId
      AND status = :status
      AND created_at >= :createdAfter
    """)
Flux<Order> search(
    @Param("customerId") Long customerId,
    @Param("status") String status,
    @Param("createdAfter") Instant createdAfter
);
~~~

### Bài 3: Derived query có cần @Param không?

Method findByFirstNameAndLastName(String firstName, String lastName) có cần @Param không?

Gợi ý: Không cần trong query method được suy ra từ tên. Spring Data phân tích tên method và liên kết các đối số theo cấu trúc đó.

### Bài 4: Điều kiện null

Bạn muốn tìm khách hàng có email NULL. Có thể bind null vào email = :email để làm việc này không?

Gợi ý: Không. Dùng email IS NULL vì so sánh bằng NULL không trả về TRUE.

### Bài 5: Collection trong IN

Viết method tìm đơn hàng theo một tập trạng thái.

Gợi ý:

~~~java
@Query("""
    SELECT id, status
    FROM orders
    WHERE status IN (:statuses)
    """)
Flux<Order> findByStatuses(
    @Param("statuses") Collection<String> statuses
);
~~~

Xử lý collection rỗng ở service trước khi gọi query.

### Bài 6: SQL injection

Vì sao không nên nối keyword tìm kiếm trực tiếp vào câu SQL?

Gợi ý: Dữ liệu có thể bị diễn giải thành cú pháp SQL. Dùng placeholder và bind giá trị như tham số.

## 16. Ghi nhớ

- @Param thuộc org.springframework.data.repository.query và liên kết tham số Java với named placeholder trong repository query.
- Với @Query, placeholder thường có dạng :name và giá trị được bind theo tên.
- Tên trong @Param phải khớp tên placeholder; tên biến Java có thể khác.
- Có thể dùng nhiều @Param trong một method và dùng lại một named parameter ở nhiều vị trí.
- Derived query method thường không cần @Param vì Spring suy ra điều kiện từ tên method.
- DatabaseClient dùng API .bind(), không dùng @Param.
- Bind parameter dùng cho giá trị, không dùng để thay tên bảng, tên cột hoặc từ khóa SQL.
- Không so sánh NULL bằng dấu bằng; dùng IS NULL khi cần tìm giá trị null.
- Xử lý collection rỗng trước khi dùng IN và kiểm tra kiểu tham số với schema/driver.
- Dùng parameter binding thay cho nối chuỗi để giảm nguy cơ SQL injection.
- Với modifying query, kiểm tra @Modifying và chữ ký trả về theo phiên bản Spring Data R2DBC.
- Kiểm tra query trên database và driver thực tế, nhất là với kiểu đặc thù và null.

Khi viết query khai báo, hãy đặt tên placeholder rõ nghĩa rồi liên kết từng tham số bằng @Param. Cách làm này giữ SQL tách biệt với dữ liệu đầu vào, giúp repository dễ đọc và giảm lỗi khi đổi tên biến hoặc mở rộng điều kiện truy vấn.

