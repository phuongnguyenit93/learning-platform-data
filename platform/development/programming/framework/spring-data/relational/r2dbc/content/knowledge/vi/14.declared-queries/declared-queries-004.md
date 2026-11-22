# Biểu thức SpEL trong truy vấn và ranh giới dữ liệu đáng tin cậy

## 1. SpEL trong truy vấn Spring Data R2DBC dùng để làm gì?

Spring Data R2DBC cho phép khai báo SQL trực tiếp trên repository method bằng annotation **@Query**. Thông thường, giá trị đầu vào được truyền qua bind parameter:

~~~java
@Query("""
    SELECT id, name, status
    FROM customers
    WHERE status = :status
    """)
Flux<Customer> findByStatus(@Param("status") String status);
~~~

Cách này phù hợp với phần lớn truy vấn. Tuy nhiên, đôi khi giá trị cần bind phải được lấy từ một thuộc tính lồng nhau, chuẩn hóa hoặc tính từ tham số trước khi gửi xuống database. Spring Data hỗ trợ **Spring Expression Language (SpEL)** trong query string để biểu diễn những phép tính như vậy.

Ví dụ, một phương thức nhận object filter thay vì nhiều tham số riêng:

~~~java
@Query("""
    SELECT id, name, status
    FROM customers
    WHERE status = :#{#filter.status}
    """)
Flux<Customer> findByFilter(@Param("filter") CustomerFilter filter);
~~~

Biểu thức **:#{#filter.status}** đọc thuộc tính status từ tham số filter. Spring Data đánh giá biểu thức rồi bind kết quả làm giá trị của câu SQL.

SpEL trong query hữu ích khi cần tính **giá trị dữ liệu** trước khi bind. Nó không phải cơ chế thay thế tên bảng, tên cột hoặc một đoạn SQL tùy ý. Việc phân biệt rõ giá trị với cấu trúc SQL là ranh giới quan trọng để giữ truy vấn an toàn và dễ kiểm soát.

## 2. Cách viết biểu thức SpEL trong @Query

Trong query string của Spring Data, biểu thức SpEL có thể được đặt bên trong bind marker theo dạng:

~~~text
:#{expression}
~~~

Phần sau dấu hai chấm là biểu thức được đánh giá để tạo giá trị bind. Dấu hai chấm đóng vai trò bind marker; biểu thức không được hiểu như một đoạn SQL do người dùng gửi vào.

### 2.1. Truy cập tham số theo vị trí

Có thể truy cập tham số phương thức theo chỉ số bắt đầu từ 0:

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE email_address = :#{[0]}
    """)
Mono<Customer> findByEmailWithExpression(String email);
~~~

Trong ví dụ, **[0]** là tham số đầu tiên của method. Cách truy cập theo vị trí ngắn gọn, nhưng khi method có nhiều tham số, người đọc khó nhận ra tham số nào đang được sử dụng.

### 2.2. Truy cập tham số theo tên

Có thể đặt tên tham số bằng **@Param** và tham chiếu trong SpEL:

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE status = :#{#status}
    """)
Flux<Customer> findByStatusExpression(
        @Param("status") String status
);
~~~

Biểu thức **#status** tham chiếu đến method parameter tên status. Cách này thường dễ đọc hơn chỉ số vị trí, nhất là với query dài.

Nên dùng **@Param** khi query dựa vào tên tham số để thể hiện rõ mối liên hệ giữa SQL và method signature. Điều đó cũng tránh phụ thuộc không cần thiết vào việc tên tham số Java có được giữ trong bytecode hay không.

### 2.3. Truy cập thuộc tính lồng nhau

SpEL có thể đọc thuộc tính từ một object được truyền vào method:

~~~java
public record CustomerFilter(
        String status,
        String city
) {}
~~~

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE status = :#{#filter.status}
      AND city = :#{#filter.city}
    """)
Flux<Customer> search(
        @Param("filter") CustomerFilter filter
);
~~~

Ở đây, **#filter.status** và **#filter.city** lấy hai giá trị từ object filter. SQL vẫn có cấu trúc cố định; chỉ những giá trị điều kiện được tính từ object.

Nếu tham số hoặc thuộc tính lồng nhau có thể null, cần quyết định rõ ý nghĩa nghiệp vụ. Không nên giả định rằng việc truy cập một thuộc tính null sẽ tự biến điều kiện SQL thành điều kiện bỏ qua.

## 3. SpEL tính giá trị trước khi bind

Biểu thức SpEL có thể thực hiện phép tính đơn giản để tạo giá trị cho bind marker.

Ví dụ chuẩn hóa trạng thái về chữ hoa:

~~~java
@Query("""
    SELECT id, name, status
    FROM customers
    WHERE status = :#{#status.toUpperCase()}
    """)
Flux<Customer> findByNormalizedStatus(
        @Param("status") String status
);
~~~

Nếu tham số là **"active"**, giá trị được tính thành **"ACTIVE"** trước khi bind. Database vẫn nhận một parameter value; nó không nhận một đoạn SQL được nối từ chuỗi status.

Có thể dùng toán tử điều kiện để chọn giá trị mặc định:

~~~java
@Query("""
    SELECT id, name, status
    FROM customers
    WHERE status = :#{#status == null ? 'ACTIVE' : #status}
    """)
Flux<Customer> findByStatusOrDefault(
        @Param("status") String status
);
~~~

Biểu thức trên chọn ACTIVE khi tham số null. Chỉ nên dùng default khi đó thực sự là quy tắc nghiệp vụ. Nếu null có nghĩa là người gọi không muốn lọc theo status, câu query cần được thiết kế để bỏ qua điều kiện thay vì tự chọn một trạng thái mặc định.

SpEL có nhiều khả năng biểu đạt. Tuy nhiên, query nên giữ biểu thức ngắn, dễ đọc và có thể kiểm thử. Nếu logic bắt đầu chứa nhiều nhánh, gọi nhiều method hoặc phụ thuộc vào trạng thái bên ngoài, hãy tính giá trị ở service rồi truyền tham số thông thường vào repository.

## 4. Kết hợp SpEL với bind parameter

### 4.1. Giá trị động vẫn là dữ liệu

Giả sử API tìm khách hàng theo status và city. Người gọi có thể cung cấp những giá trị này từ query string HTTP. Repository method có thể nhận một filter và dùng SpEL lấy từng giá trị:

~~~java
public record CustomerSearch(
        String status,
        String city
) {}
~~~

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE status = :#{#search.status}
      AND city = :#{#search.city}
    ORDER BY id
    """)
Flux<Customer> search(
        @Param("search") CustomerSearch search
);
~~~

Các chuỗi status và city vẫn được truyền như giá trị bind. Người gọi có thể thay đổi dữ liệu đầu vào, nhưng không thể làm thay đổi cấu trúc SQL chỉ bằng cách đưa ký tự SQL vào giá trị.

### 4.2. Không nối dữ liệu người dùng vào query string

Không nên xây dựng query bằng phép nối chuỗi:

~~~java
String sql = "SELECT * FROM customers WHERE status = '"
        + requestStatus + "'";
~~~

Nếu requestStatus chứa ký tự quote và cú pháp SQL, câu query có thể bị thay đổi ngoài ý định. Đây là lỗi SQL injection điển hình.

Dùng bind parameter:

~~~java
databaseClient.sql("""
        SELECT id, name, status
        FROM customers
        WHERE status = :status
        """)
    .bind("status", requestStatus)
    .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("name", String.class),
            null,
            row.get("status", String.class)
    ))
    .all();
~~~

Hoặc dùng repository query với **:#{#status}** nếu cần biểu thức để lấy hoặc tính giá trị. Cả hai cách đều giữ giá trị tách khỏi cấu trúc câu SQL.

### 4.3. Bind parameter không thay thế identifier

Bind marker dùng cho **giá trị dữ liệu**, không dùng để thay tên bảng, tên cột hoặc từ khóa SQL.

Ví dụ sau không chọn động cột theo ý định:

~~~sql
SELECT id, name
FROM customers
ORDER BY :sortColumn
~~~

Khi bind sortColumn = **'created_at'**, database hiểu đó là một giá trị parameter, không phải identifier cột. Kết quả có thể không sắp xếp theo cột mong muốn.

Tương tự, không dùng SpEL như một cách để lấy tên bảng từ request rồi ghép trực tiếp vào SQL. Nếu thật sự cần lựa chọn identifier động, phải ánh xạ lựa chọn của người dùng sang một tập identifier cố định do ứng dụng kiểm soát.

## 5. Phân biệt dữ liệu, identifier và SQL structure

Để giữ ranh giới tin cậy rõ ràng, cần phân biệt ba loại đầu vào:

| Loại | Ví dụ | Cách xử lý |
|---|---|---|
| Giá trị dữ liệu | email, status, customer ID, ngày tạo | Dùng bind parameter; SpEL có thể tính giá trị trước khi bind |
| Identifier | tên bảng, tên cột, schema, cột sắp xếp | Dùng mapping metadata hoặc lựa chọn từ allowlist cố định |
| SQL structure | JOIN, WHERE, ORDER BY, toán tử, câu lệnh | Khai báo tĩnh trong query hoặc xây dựng bằng API query có kiểm soát |

Ví dụ:

~~~sql
SELECT id, email_address
FROM customers
WHERE status = :status
ORDER BY created_at DESC
~~~

- **customers**, **email_address**, **status** và **created_at** là identifier do ứng dụng xác định.
- **:status** là vị trí bind cho giá trị dữ liệu.
- SELECT, FROM, WHERE và ORDER BY là cấu trúc SQL cố định.

SpEL giúp tính giá trị ở vị trí bind. Nó không biến một chuỗi bất kỳ thành identifier an toàn.

## 6. Dynamic sorting và lựa chọn cột an toàn

Một yêu cầu phổ biến là cho phép client chọn cột sắp xếp. Không nên đưa trực tiếp chuỗi từ request vào SQL:

~~~java
String sql = "SELECT id, name FROM customers ORDER BY "
        + request.getSort();
~~~

Người dùng có thể gửi một biểu thức không mong muốn thay cho tên cột. Vì identifier không thể bind như một giá trị, cách an toàn là dùng allowlist.

Ví dụ:

~~~java
enum CustomerSort {
    NAME,
    CREATED_AT
}
~~~

~~~java
String orderBy = switch (sort) {
    case NAME -> "name";
    case CREATED_AT -> "created_at";
};

String sql = "SELECT id, name FROM customers ORDER BY " + orderBy;
~~~

Ở đây, phần được nối vào SQL chỉ có thể là một trong hai identifier cố định do code quyết định. Nếu đầu vào bên ngoài là chuỗi, hãy parse nó thành enum hoặc tra cứu trong map allowlist; giá trị không hợp lệ phải bị từ chối hoặc chuyển về mặc định đã quy định.

Với API Criteria/Query của Spring Data Relational, có thể xây dựng Sort từ những lựa chọn được kiểm soát. Dù chọn API nào, không để raw identifier từ request đi thẳng vào câu SQL.

## 7. SpEL và dữ liệu theo tenant hoặc người dùng hiện tại

Trong ứng dụng multi-tenant, nhiều truy vấn phải giới hạn dữ liệu theo tenant hiện tại. Điều quan trọng là **nguồn tenant ID phải đáng tin cậy** và điều kiện tenant phải được áp dụng ở mọi đường truy cập dữ liệu phù hợp.

Ví dụ repository nhận tenant ID như một tham số rõ ràng:

~~~java
@Query("""
    SELECT id, name, status
    FROM customers
    WHERE tenant_id = :#{#tenantId}
      AND id = :#{#customerId}
    """)
Mono<Customer> findForTenant(
        @Param("tenantId") UUID tenantId,
        @Param("customerId") Long customerId
);
~~~

Cách này thể hiện rõ điều kiện tenant trong query. Nhưng việc bind tenantId không tự xác minh người gọi có quyền sử dụng tenant đó hay không. Service hoặc security layer phải lấy tenant từ danh tính đã xác thực và kiểm tra quyền, rồi truyền giá trị đã được xác minh vào repository.

Không nên coi tenant ID do client gửi trong request body hoặc query string là đáng tin cậy chỉ vì nó được bind an toàn. Bind parameter bảo vệ cấu trúc SQL; nó không phải kiểm tra authorization.

Một quy trình phù hợp:

1. Xác thực request và danh tính người dùng.
2. Xác định tenant từ security context hoặc nguồn dữ liệu được tin cậy.
3. Kiểm tra người dùng được phép truy cập tenant đó.
4. Truyền tenant ID đã xác minh vào service/repository.
5. Áp dụng điều kiện tenant trong mọi query cần giới hạn dữ liệu.
6. Kiểm thử để chắc chắn không thể đọc hoặc sửa dữ liệu của tenant khác.

Nếu ứng dụng dùng cơ chế context hoặc evaluation-context extension để cung cấp principal/tenant cho SpEL, cần cấu hình rõ nguồn dữ liệu, phạm vi và quyền truy cập. Chỉ expose những giá trị cần thiết, chỉ đọc và đã được xác thực. Không mở rộng evaluation context thành nơi có thể gọi tùy ý các bean nghiệp vụ hoặc truy cập secret.

## 8. Không dùng SpEL như cơ chế phân quyền

SpEL có thể giúp lấy tenant ID, user ID hoặc một thuộc tính từ context đã cấu hình. Nhưng biểu thức không thay thế việc kiểm tra quyền.

Ví dụ:

~~~text
WHERE tenant_id = :#{#tenantId}
~~~

chỉ giới hạn kết quả theo giá trị tenantId được cung cấp. Nó không chứng minh giá trị đó thuộc về người dùng hiện tại.

Nếu một service nhận tenantId từ request mà không xác minh, người dùng có thể đổi tenantId và truy cập dữ liệu ngoài phạm vi. Dù query dùng bind parameter và không có SQL injection, lỗi phân quyền vẫn tồn tại.

Cần tách ba trách nhiệm:

- **Authentication:** xác định người gọi là ai.
- **Authorization:** xác định người gọi được phép làm gì và truy cập dữ liệu nào.
- **Parameter binding:** truyền giá trị vào SQL an toàn, tách khỏi cấu trúc câu lệnh.

Một hệ thống an toàn cần cả ba. Không dùng một trong ba để thay thế hai phần còn lại.

## 9. Cẩn trọng với biểu thức phức tạp và evaluation context

SpEL là ngôn ngữ biểu thức có khả năng truy cập thuộc tính, gọi method và đánh giá điều kiện. Trong query, biểu thức nên được viết bởi developer và chỉ thực hiện phép tính cần thiết cho tham số.

Những nguyên tắc nên tuân theo:

- Viết expression tĩnh trong source code hoặc cấu hình do đội phát triển kiểm soát.
- Không nhận nguyên văn chuỗi SpEL từ HTTP request, message hoặc dữ liệu người dùng rồi đánh giá.
- Không cho phép người dùng quyết định bean, method hoặc class được tham chiếu trong expression.
- Hạn chế những object được đưa vào evaluation context.
- Ưu tiên tham số method rõ ràng thay vì phụ thuộc ngầm vào context toàn cục.
- Chuyển logic nghiệp vụ phức tạp sang service hoặc domain layer.
- Kiểm tra hành vi expression trên phiên bản Spring Data đang sử dụng.

Nếu ứng dụng cấu hình thêm evaluation context extension hoặc bean được tham chiếu trong SpEL, hãy xem đó là một bề mặt thực thi cần quản lý. Chỉ cung cấp dữ liệu và hàm cần thiết; tránh expose bean có thể thực hiện thao tác ghi, gọi mạng hoặc truy cập tài nguyên nhạy cảm.

## 10. Xử lý null và điều kiện tùy chọn

Một trường lọc có thể không được cung cấp. Cần phân biệt các ý nghĩa:

- Không lọc theo trường đó.
- Chỉ tìm các hàng có giá trị SQL NULL.
- Dùng một giá trị mặc định.
- Từ chối request vì thiếu dữ liệu bắt buộc.

Các ý nghĩa này dẫn đến SQL khác nhau.

### 10.1. Không dùng = NULL để tìm giá trị null

Trong SQL, so sánh **column = NULL** không trả về true. Muốn tìm giá trị null phải dùng **IS NULL**.

Ví dụ query cố định cho trường hợp null:

~~~sql
SELECT id, name
FROM customers
WHERE city IS NULL
~~~

Nếu muốn một điều kiện tùy chọn, có thể viết query với logic tường minh:

~~~java
@Query("""
    SELECT id, name, status
    FROM customers
    WHERE (:#{#status} IS NULL OR status = :#{#status})
    """)
Flux<Customer> findByOptionalStatus(
        @Param("status") String status
);
~~~

Khi status null, vế đầu đúng và điều kiện status được bỏ qua. Khi status có giá trị, query lọc theo status. Cần kiểm tra cách bind null và kiểu dữ liệu của driver/dialect trong phiên bản đang dùng; với truy vấn phức tạp, có thể xây dựng query động bằng Criteria để biểu đạt điều kiện rõ ràng.

### 10.2. Null không đồng nghĩa với chuỗi rỗng

**NULL**, **''** và chuỗi chỉ chứa khoảng trắng là những giá trị khác nhau. Không tự động dùng SpEL để biến mọi trường hợp thành cùng một giá trị nếu nghiệp vụ cần phân biệt.

Có thể chuẩn hóa ở service trước khi gọi repository:

~~~java
String normalizedStatus =
        status == null || status.isBlank()
                ? null
                : status.trim().toUpperCase(Locale.ROOT);
~~~

Sau đó truyền giá trị đã chuẩn hóa làm bind parameter. Cách này giúp logic dễ unit test và tránh làm expression trong query quá phức tạp.

## 11. LIKE, wildcard và ý nghĩa của dữ liệu đầu vào

Bind parameter ngăn chuỗi đầu vào trở thành cú pháp SQL, nhưng không loại bỏ ý nghĩa wildcard của LIKE.

Ví dụ:

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE name LIKE :pattern
    """)
Flux<Customer> searchByNamePattern(
        @Param("pattern") String pattern
);
~~~

Nếu pattern là **%an%**, database sẽ tìm chuỗi chứa an. Ký tự **%** và **_** là wildcard của LIKE. Đây không phải SQL injection, nhưng có thể khiến kết quả rộng hơn điều người dùng dự định.

Nếu nghiệp vụ muốn tìm chuỗi literal, cần escape wildcard theo quy tắc của database và khai báo mệnh đề ESCAPE phù hợp. Có thể tạo pattern đã escape ở service rồi bind. Hãy kiểm thử các ký tự %, _ và ký tự escape trong input.

## 12. SpEL trong query so với tính toán ở service

Không phải phép tính tham số nào cũng nên đặt trong SpEL. Chọn vị trí theo độ phức tạp và trách nhiệm:

| Nhu cầu | Cách thường phù hợp |
|---|---|
| Lấy trực tiếp method parameter | Bind parameter thông thường |
| Lấy thuộc tính từ filter object | SpEL ngắn trong bind marker hoặc tách tham số |
| Chuẩn hóa chuỗi đơn giản | Service hoặc SpEL ngắn, tùy quy ước |
| Logic nhiều nhánh, cần kiểm thử riêng | Service/domain layer |
| Lấy tenant/user đã xác thực | Security/service layer, truyền tham số rõ ràng |
| Chọn tên bảng/cột | Mapping metadata hoặc allowlist identifier |
| Tạo JOIN/WHERE phức tạp theo nhiều điều kiện | Criteria/Query hoặc query builder có kiểm soát |
| Chạy SQL khác nhau theo database | Repository/query riêng theo dialect |

SpEL phù hợp để giảm boilerplate trong query, không nên trở thành ngôn ngữ nghiệp vụ chính. Khi biểu thức dài hơn câu SQL hoặc khó giải thích, hãy tính giá trị trước và truyền vào repository bằng tham số có tên rõ ràng.

## 13. Ví dụ hoàn chỉnh: truy vấn theo filter có tenant

Giả sử ứng dụng có bảng customers với các cột tenant_id, id, name, city và status. Filter được khai báo:

~~~java
public record CustomerFilter(
        UUID tenantId,
        String status,
        String city
) {}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("""
        SELECT id, tenant_id, name, city, status
        FROM customers
        WHERE tenant_id = :#{#filter.tenantId}
          AND (:#{#filter.status} IS NULL
               OR status = :#{#filter.status})
          AND (:#{#filter.city} IS NULL
               OR city = :#{#filter.city})
        ORDER BY id
        """)
    Flux<Customer> search(
            @Param("filter") CustomerFilter filter
    );
}
~~~

Service chịu trách nhiệm lấy tenant từ danh tính đã được xác thực và tạo filter:

~~~java
public Flux<Customer> search(
        AuthenticatedUser user,
        CustomerSearchRequest request) {

    UUID authorizedTenantId = tenantAccess.requireTenant(user);

    CustomerFilter filter = new CustomerFilter(
            authorizedTenantId,
            normalizeStatus(request.status()),
            normalizeCity(request.city())
    );

    return customerRepository.search(filter);
}
~~~

**tenantAccess.requireTenant(user)** đại diện cho logic kiểm tra quyền của ứng dụng. Đây không phải API Spring có sẵn; nó minh họa trách nhiệm cần thực hiện trước khi gọi repository.

Trong ví dụ:

- SQL structure được viết tĩnh.
- tenantId, status và city được bind như giá trị.
- SpEL chỉ lấy property từ filter object.
- Tenant ID đến từ security/service layer sau khi xác minh.
- Client không được tự quyết định tenant chỉ bằng cách gửi tenantId trong request.
- Query trả **Flux<Customer>** vì có thể có nhiều kết quả.

Với filter phức tạp hơn, có thể dùng Criteria API để chỉ thêm điều kiện khi giá trị tồn tại. Điều này thường dễ đọc hơn một query có nhiều nhánh null.

## 14. Kiểm thử SpEL và ranh giới dữ liệu

Kiểm thử cần xác nhận cả việc expression lấy đúng giá trị lẫn việc dữ liệu không thể thay đổi cấu trúc SQL.

### 14.1. Kiểm tra tham số được đọc đúng

Dùng integration test với database tương thích để gọi repository với nhiều filter khác nhau:

- Status có giá trị.
- Status null theo ý nghĩa bỏ qua điều kiện.
- Filter có thuộc tính lồng nhau.
- Chuỗi có dấu tiếng Việt hoặc ký tự đặc biệt.
- Không tìm thấy hàng.

Điều này xác nhận Spring Data đánh giá SpEL và bind giá trị theo đúng kiểu mà driver hỗ trợ.

### 14.2. Kiểm tra chuỗi giống SQL injection được coi là dữ liệu

Ví dụ input:

~~~text
' OR 1=1 --
~~~

Khi truyền qua bind parameter, chuỗi đó phải được xử lý như một giá trị tìm kiếm bình thường, không làm thay đổi mệnh đề WHERE. Có thể tạo integration test với dữ liệu kiểm soát để xác nhận truy vấn không trả toàn bộ bảng chỉ vì chuỗi chứa cú pháp SQL.

### 14.3. Kiểm tra authorization độc lập

Kiểm thử các trường hợp:

- Người dùng tenant A chỉ đọc được dữ liệu tenant A.
- Thay đổi tenant ID trong request không giúp truy cập tenant B.
- Query update/delete cũng áp dụng tenant predicate.
- Một repository method khác không vô tình bỏ qua điều kiện tenant.
- Người dùng không có quyền bị từ chối trước khi truy vấn được thực hiện hoặc không nhận được dữ liệu ngoài phạm vi.

Không chỉ kiểm thử một query tìm kiếm. Ranh giới tenant phải được áp dụng nhất quán cho mọi thao tác có thể đọc hoặc thay đổi dữ liệu.

### 14.4. Kiểm thử null, wildcard và identifier

Ngoài giá trị thông thường, cần kiểm thử:

- NULL so với chuỗi rỗng.
- Ký tự **%** và **_** trong LIKE.
- Giá trị Unicode và dấu nháy.
- Sort key không nằm trong allowlist.
- Tên cột/bảng không hợp lệ bị từ chối trước khi tạo SQL.

## 15. Những lỗi thường gặp khi dùng SpEL trong truy vấn

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không phân giải được tên tham số | Tên trong expression không khớp method parameter | Dùng **@Param** và tham chiếu **#parameterName** |
| Lỗi truy cập thuộc tính | Object hoặc nested property null/không tồn tại | Kiểm tra input; dùng null-safe logic hoặc chuẩn hóa ở service |
| Không chuyển được kiểu bind | Expression trả kiểu không tương thích cột/driver | Kiểm tra target type và chuyển đổi trước khi bind |
| Query không tìm đúng khi input null | Dùng **column = NULL** theo semantics SQL | Dùng **IS NULL** hoặc điều kiện tùy chọn tường minh |
| ORDER BY không đổi theo tham số | Cố bind tên cột như một giá trị | Dùng allowlist identifier hoặc Criteria Sort |
| SQL injection dù có SpEL | Ghép expression result vào SQL structure hoặc nối chuỗi input | Dùng expression chỉ trong bind marker; không tạo raw SQL từ input |
| Người dùng đọc được tenant khác | Tenant ID do client kiểm soát hoặc thiếu predicate | Lấy tenant từ identity đã xác thực và áp dụng authorization |
| Query quá khó bảo trì | Expression chứa nhiều logic nghiệp vụ | Chuyển phép tính sang service/domain layer |
| Query hoạt động khác giữa môi trường | Driver/dialect hoặc phiên bản Spring Data khác nhau | Integration test với database/driver thực tế |

## 16. Checklist trước khi đưa query SpEL vào ứng dụng

1. Xác định expression có thực sự cần thiết hay bind parameter thông thường đã đủ.
2. Giữ expression ngắn và do developer kiểm soát.
3. Dùng **@Param** để đặt tên tham số rõ ràng.
4. Đặt SpEL trong bind marker để kết quả được dùng làm giá trị dữ liệu.
5. Không dùng bind marker hoặc SpEL như cách thay tên bảng/cột.
6. Không nối raw input vào SQL hoặc expression text.
7. Dùng allowlist khi cần lựa chọn identifier hoặc sort key.
8. Lấy user/tenant identity từ nguồn đã xác thực và kiểm tra quyền riêng.
9. Xác định rõ semantics của null, chuỗi rỗng và wildcard.
10. Chuyển logic phức tạp sang service hoặc Criteria API.
11. Kiểm thử với database và R2DBC driver thực tế.
12. Kiểm thử cả SQL injection boundary và authorization boundary.

## 17. Kết luận

SpEL trong truy vấn Spring Data R2DBC giúp lấy hoặc tính giá trị từ method parameter và object filter ngay trong query string. Khi dùng biểu thức dạng **:#{...}**, Spring Data đánh giá expression và sử dụng kết quả làm bind value. Cách này hữu ích cho tham số lồng nhau hoặc phép tính nhỏ, trong khi SQL structure vẫn được khai báo tĩnh.

Ranh giới dữ liệu đáng tin cậy nằm ở việc tách giá trị khỏi cấu trúc SQL. Bind parameter bảo vệ giá trị khỏi bị diễn giải thành cú pháp SQL, nhưng không thể thay tên bảng/cột và cũng không thực hiện authorization. Identifier động cần allowlist; tenant/user identity cần được lấy từ nguồn đã xác thực và kiểm tra quyền trước khi truy vấn.

Giữ SpEL ngắn, không đánh giá expression do người dùng cung cấp, không expose evaluation context quá rộng và kiểm thử null, wildcard, tenant isolation cùng database thực tế. Những nguyên tắc này giúp query khai báo linh hoạt mà vẫn duy trì ranh giới bảo mật rõ ràng.

