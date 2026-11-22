# Sử dụng Java record làm DTO projection trong Spring Data JPA

## 1. DTO projection là gì?

Trong Spring Data JPA, repository thường trả về entity được ánh xạ từ bảng database. Entity phù hợp khi ứng dụng cần làm việc với dữ liệu được persistence context quản lý, cập nhật thuộc tính, theo dõi quan hệ và lưu thay đổi.

Nhiều màn hình hoặc API chỉ cần một phần dữ liệu. Ví dụ, trang danh sách khách hàng chỉ cần ID, tên hiển thị và email; báo cáo doanh thu chỉ cần mã khách hàng và tổng tiền. Nếu tải toàn bộ entity cùng các quan hệ không cần thiết, ứng dụng có thể đọc thừa cột, tạo thêm JOIN, giữ nhiều object trong persistence context và làm tăng chi phí bộ nhớ.

**DTO projection** cho phép repository trả về một kiểu dữ liệu chỉ chứa các trường mà truy vấn cần. DTO là đối tượng truyền dữ liệu, thường dùng cho kết quả đọc hoặc báo cáo. Trong Java 16 trở lên, `record` là lựa chọn phù hợp vì cung cấp constructor, accessor và các phương thức cơ bản theo cấu trúc dữ liệu một cách ngắn gọn.

Ví dụ:

~~~java
package com.example.customer.dto;

public record CustomerSummary(
    Long id,
    String fullName,
    String email
) {}
~~~

Record trên định nghĩa một DTO có ba thành phần. Java tự tạo canonical constructor, accessor `id()`, `fullName()`, `email()`, cùng `equals()`, `hashCode()` và `toString()`.

Record DTO giúp:

- Chỉ mang những trường cần cho use case.
- Có dữ liệu bất biến ở mức tham chiếu thành phần.
- Giảm boilerplate so với một class DTO truyền thống.
- Làm rõ cấu trúc kết quả của repository bằng kiểu Java cụ thể.
- Tách mô hình dữ liệu trả về khỏi entity persistence.

Record phù hợp nhất với kết quả đọc. Nó không thay thế entity và không tham gia dirty checking của JPA.

## 2. Record khác entity như thế nào?

Một JPA entity đại diện cho dữ liệu được persistence provider quản lý. Entity có định danh, vòng đời và trạng thái managed, detached hoặc removed. Một record DTO chỉ là object Java chứa dữ liệu kết quả.

| Tiêu chí | JPA entity | Record DTO |
|---|---|---|
| Mục đích | Mô hình dữ liệu được persistence context quản lý | Mang dữ liệu cho một use case hoặc kết quả truy vấn |
| Định danh JPA | Có `@Id` | Không cần `@Id` |
| Thay đổi dữ liệu | Có thể được dirty checking khi managed | Không được JPA theo dõi |
| Quan hệ entity | Có thể ánh xạ `@OneToMany`, `@ManyToOne`... | Thường chứa scalar hoặc kiểu dữ liệu đã chọn |
| Constructor | Phải đáp ứng yêu cầu entity của JPA | Dùng canonical constructor của record |
| Mutability | Thường có setter hoặc phương thức thay đổi trạng thái | Thành phần record là final |
| `save()` | Có thể persist/merge nếu được mapping đúng | Không phải đối tượng để repository lưu như entity |

Java record là kiểu final và không đáp ứng các yêu cầu thông thường của một entity class JPA. Không đánh dấu record DTO bằng `@Entity`, không đặt `@Id` để mong JPA quản lý nó như một entity. Dùng record làm kiểu kết quả projection.

Tính bất biến của record là bất biến nông: tham chiếu tới mỗi thành phần không thể gán lại sau khi tạo, nhưng nếu thành phần là một object mutable như `List`, object bên trong vẫn có thể thay đổi. Với DTO trả về API, nên cân nhắc kiểu dữ liệu và cách sao chép collection phù hợp.

## 3. Class-based projection với record

Spring Data JPA hỗ trợ class-based projection, còn gọi là DTO projection. Record có thể làm kiểu trả về của repository method nếu constructor của nó khớp với dữ liệu truy vấn.

Ví dụ entity:

~~~java
@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String fullName;
    private String email;
    private CustomerStatus status;

    protected Customer() {}

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public CustomerStatus getStatus() {
        return status;
    }
}
~~~

Record DTO:

~~~java
package com.example.customer.dto;

public record CustomerSummary(
    Long id,
    String fullName,
    String email
) {}
~~~

Repository có thể khai báo derived query:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<CustomerSummary> findByStatus(CustomerStatus status);
}
~~~

Spring Data JPA nhận biết kiểu trả về `CustomerSummary` là DTO projection. Với derived query, framework có thể chọn các thuộc tính cần thiết dựa trên constructor/component của DTO và mapping entity. Tên các thành phần record cần khớp với tên thuộc tính entity mà projection yêu cầu; kiểu và thứ tự tham số của constructor cũng phải phù hợp với kết quả.

Ví dụ này là mã thuộc tầng Spring Data JPA, cần entity, enum, repository, dependency và datasource của ứng dụng. Đây không phải chương trình Java độc lập có thể chạy chỉ bằng `javac`.

## 4. Dùng JPQL constructor expression

Khi muốn kiểm soát rõ các trường được chọn, có thể dùng JPQL constructor expression với `SELECT NEW`.

Ví dụ:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select new com.example.customer.dto.CustomerSummary(
            c.id,
            c.fullName,
            c.email
        )
        from Customer c
        where c.status = :status
        order by c.fullName
    """)
    List<CustomerSummary> findSummariesByStatus(
        @Param("status") CustomerStatus status
    );
}
~~~

JPQL sẽ gọi constructor tương ứng của record với các giá trị theo đúng thứ tự:

1. `c.id` ánh xạ vào thành phần `id`.
2. `c.fullName` ánh xạ vào thành phần `fullName`.
3. `c.email` ánh xạ vào thành phần `email`.

Các quy tắc cần nhớ:

- Dùng **tên đầy đủ của class DTO** trong `new`, gồm cả package.
- Thứ tự biểu thức trong constructor expression phải khớp thứ tự tham số canonical constructor.
- Kiểu kết quả của mỗi biểu thức phải tương thích với kiểu tham số record.
- Không thêm alias `AS` cho từng đối số bên trong constructor expression.
- JPQL dùng tên entity và thuộc tính Java, không dùng tên bảng/cột SQL trực tiếp.

Ví dụ sai nếu tên class hoặc thứ tự kiểu không khớp:

~~~java
select new CustomerSummary(c.fullName, c.id, c.email)
from Customer c
~~~

Biểu thức trên không khớp constructor `(Long id, String fullName, String email)`. Hãy sắp xếp đúng thứ tự hoặc định nghĩa record phù hợp với truy vấn.

## 5. Canonical constructor và tên thành phần record

Mỗi record có canonical constructor tương ứng với danh sách thành phần được khai báo:

~~~java
public record CustomerSummary(
    Long id,
    String fullName,
    String email
) {}
~~~

Tương đương về ý nghĩa với constructor nhận `Long`, `String`, `String` theo thứ tự trên. Constructor này được Java tạo tự động nếu không tự khai báo.

Spring Data JPA dùng thông tin constructor để xác định các thuộc tính cần lấy cho class-based projection. Với record thông thường chỉ có canonical constructor, cấu trúc này rất rõ ràng.

Nếu dùng một class DTO thông thường có nhiều constructor, Spring Data có thể không biết constructor nào cần dùng. Khi đó, có thể đánh dấu constructor mong muốn bằng `@PersistenceCreator`. Với record, canonical constructor thường là lựa chọn tự nhiên; chỉ cần chú ý nếu tự thêm constructor khác hoặc thay đổi cấu trúc record.

Không đặt tên thành phần record tùy tiện nếu muốn Spring Data suy ra projection từ derived query. Ví dụ entity có thuộc tính `fullName`, nhưng record khai báo `name`, thì tên thuộc tính không còn khớp để framework suy ra trường cần lấy. Trong trường hợp đó, dùng JPQL constructor expression tường minh hoặc ánh xạ phù hợp.

## 6. Projection từ truy vấn tổng hợp

Record đặc biệt hữu ích khi truy vấn trả về giá trị tính toán như `COUNT`, `SUM`, `AVG` hoặc dữ liệu nhóm.

Ví dụ record cho doanh thu theo khách hàng:

~~~java
package com.example.order.dto;

import java.math.BigDecimal;

public record CustomerRevenue(
    Long customerId,
    BigDecimal totalRevenue
) {}
~~~

Repository:

~~~java
@Query("""
    select new com.example.order.dto.CustomerRevenue(
        o.customer.id,
        sum(o.totalAmount)
    )
    from PurchaseOrder o
    where o.status = :status
    group by o.customer.id
    order by o.customer.id
""")
List<CustomerRevenue> summarizeRevenue(
    @Param("status") OrderStatus status
);
~~~

Truy vấn nhóm theo khách hàng và tạo một record cho mỗi nhóm. `SUM` trên thuộc tính `BigDecimal` thường cho kết quả kiểu tương ứng theo quy tắc JPQL/provider; hãy xác nhận kiểu trả về của biểu thức aggregate với mapping thực tế.

Một số lưu ý:

- `COUNT(...)` trong JPQL có kiểu kết quả `Long`; record nên khai báo `Long` cho thành phần nhận giá trị này.
- `AVG(...)` có quy tắc kiểu trả về riêng; không tự giả định nó luôn có kiểu giống cột nguồn.
- `SUM(...)` có kiểu phụ thuộc kiểu số của biểu thức theo đặc tả JPQL.
- Nhóm không có bản ghi sẽ không tạo một record với tổng bằng 0; nó không xuất hiện trong kết quả `GROUP BY`.
- `SUM` có thể trả `NULL` trong các ngữ cảnh không có giá trị phù hợp; cần chọn kiểu tham chiếu hoặc xử lý `COALESCE` theo nghiệp vụ.

Ví dụ dùng `COALESCE` nếu muốn thay kết quả NULL bằng 0 và kiểu dữ liệu tương thích:

~~~java
@Query("""
    select new com.example.order.dto.CustomerRevenue(
        o.customer.id,
        coalesce(sum(o.totalAmount), 0)
    )
    from PurchaseOrder o
    group by o.customer.id
""")
List<CustomerRevenue> summarizeAllRevenue();
~~~

Cần kiểm tra kiểu literal `0` và kiểu `totalAmount` trên provider đang dùng. Với dữ liệu tiền tệ, ưu tiên `BigDecimal` và kiểm thử precision/scale.

## 7. Record projection và interface projection

Spring Data JPA có hai dạng projection thường dùng:

- **Interface-based projection:** khai báo interface với getter; Spring Data thường tạo proxy để cung cấp giá trị.
- **Class-based projection:** dùng class hoặc record với constructor; kết quả là instance DTO.

Ví dụ interface:

~~~java
public interface CustomerNameView {
    String getFullName();
    String getEmail();
}
~~~

Repository:

~~~java
List<CustomerNameView> findByStatus(CustomerStatus status);
~~~

Ví dụ record:

~~~java
public record CustomerNameDto(
    String fullName,
    String email
) {}
~~~

Repository:

~~~java
List<CustomerNameDto> findByStatus(CustomerStatus status);
~~~

So sánh:

| Tiêu chí | Interface projection | Record DTO projection |
|---|---|---|
| Khai báo | Interface và getter | Record component |
| Instance | Thường là proxy | Instance record cụ thể |
| Constructor | Không cần constructor DTO | Cần constructor khớp |
| Tính bất biến | Phụ thuộc cách triển khai accessor/proxy | Thành phần record final |
| Biểu thức JPQL | Có thể dùng projection theo thuộc tính | Có thể dùng `SELECT NEW` |
| Phù hợp | View đơn giản, có thể dùng nested projection | DTO rõ kiểu, dữ liệu đọc, kết quả tổng hợp |

Chọn interface khi cần một view đơn giản hoặc nested projection được hỗ trợ. Chọn record khi muốn một kiểu DTO cụ thể, bất biến ở mức thành phần và dễ truyền giữa các tầng.

Class-based projection không hỗ trợ nested projection theo cùng cách interface projection. Nếu cần cấu trúc lồng nhau, hãy cân nhắc nhiều truy vấn, constructor expression phù hợp hoặc tạo DTO ở service từ dữ liệu đã truy vấn.

## 8. Dynamic projection với record

Một repository method có thể nhận `Class<T>` để caller chọn kiểu projection tại thời điểm gọi:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    <T> List<T> findByStatus(
        CustomerStatus status,
        Class<T> projectionType
    );
}
~~~

Gọi với record:

~~~java
List<CustomerSummary> summaries =
    repository.findByStatus(
        CustomerStatus.ACTIVE,
        CustomerSummary.class
    );
~~~

Cùng một điều kiện truy vấn có thể trả về entity, interface projection hoặc record DTO tùy kiểu được truyền vào, miễn kiểu projection tương thích với thuộc tính entity và cơ chế projection của Spring Data.

Dynamic projection hữu ích khi nhiều use case dùng chung điều kiện lọc nhưng cần các tập trường khác nhau. Tuy nhiên, không nên lạm dụng khiến repository khó đọc. Nếu mỗi use case có logic hoặc JOIN khác nhau, các method riêng với tên rõ ràng có thể dễ bảo trì hơn.

Spring Data nhận diện tham số `Class<T>` phù hợp làm dynamic projection parameter. Nếu muốn dùng một tham số Class như giá trị truy vấn thông thường, cần khai báo kiểu tham số khác hoặc thiết kế method phù hợp để Spring Data không nhận nó là projection selector.

## 9. Native SQL và record DTO

Native query có thể trả về DTO class/record trong một số trường hợp, nhưng cần chú ý thứ tự cột và kiểu dữ liệu.

Ví dụ native SQL chọn các cột theo đúng thứ tự canonical constructor:

~~~java
@Query(
    value = """
        select c.id, c.full_name, c.email
        from customer c
        where c.status = :status
        order by c.full_name
    """,
    nativeQuery = true
)
List<CustomerSummary> findNativeSummaries(
    @Param("status") String status
);
~~~

Với class-based native projection, thứ tự cột và kiểu JDBC cần khớp với thứ tự và kiểu tham số constructor. Alias cột có thể giúp truy vấn dễ đọc, nhưng không nên giả định alias tự động giải quyết mọi khác biệt giữa tên cột và tên record component.

Nếu native query trả về biểu thức phức tạp, nhiều kiểu vendor-specific hoặc thứ tự không khớp constructor, có thể dùng `@SqlResultSetMapping` kết hợp `@ConstructorResult`, hoặc custom repository dùng `EntityManager.createNativeQuery(sql, mappingName)`.

Ví dụ mapping chuẩn JPA:

~~~java
@SqlResultSetMapping(
    name = "CustomerSummaryMapping",
    classes = @ConstructorResult(
        targetClass = CustomerSummary.class,
        columns = {
            @ColumnResult(name = "id", type = Long.class),
            @ColumnResult(name = "full_name", type = String.class),
            @ColumnResult(name = "email", type = String.class)
        }
    )
)
@Entity
@Table(name = "customer")
public class Customer {
    @Id
    private Long id;
}
~~~

Custom repository có thể gọi mapping:

~~~java
@SuppressWarnings("unchecked")
public List<CustomerSummary> findSummariesNative(String status) {
    return entityManager
        .createNativeQuery(
            "select id, full_name, email from customer where status = :status",
            "CustomerSummaryMapping"
        )
        .setParameter("status", status)
        .getResultList();
}
~~~

Ví dụ mapping phải được đặt ở vị trí mà JPA provider quét metadata; các entity field và package cần khớp với ứng dụng. Với native SQL, kiểu enum, UUID, timestamp, numeric và alias cột có thể khác theo JDBC driver và database, vì vậy cần integration test trên hệ quản trị thực tế.

## 10. Phân trang với record DTO

Có thể trả về `Page<RecordDto>` khi muốn phân trang dữ liệu đã projection.

~~~java
@Query(
    value = """
        select new com.example.customer.dto.CustomerSummary(
            c.id,
            c.fullName,
            c.email
        )
        from Customer c
        where c.status = :status
        order by c.fullName
    """,
    countQuery = """
        select count(c)
        from Customer c
        where c.status = :status
    """
)
Page<CustomerSummary> findSummaryPage(
    @Param("status") CustomerStatus status,
    Pageable pageable
);
~~~

Truy vấn nội dung tạo record cho mỗi khách hàng. `countQuery` đếm tổng số entity phù hợp để Spring Data tạo metadata trang.

Nếu truy vấn chính có JOIN một-nhiều và `DISTINCT`, count query phải đếm đúng loại phần tử mà trang trả về, thường là `count(distinct c.id)` khi mục tiêu là số khách hàng duy nhất. Với `GROUP BY`, cần xem lại semantics phân trang và có thể cần truy vấn đếm riêng phức tạp hơn.

Nếu chỉ cần dữ liệu trang và biết còn trang tiếp theo, `Slice<CustomerSummary>` có thể tránh việc lấy tổng số phần tử. Chọn `Page` khi thực sự cần tổng số trang hoặc tổng số bản ghi.

## 11. Record DTO có thể cập nhật entity không?

Record projection thường được dùng cho luồng đọc. Kết quả record không được persistence context quản lý, nên:

- Thay đổi dữ liệu nguồn trong database không tự cập nhật record đã trả về.
- Không thể dùng dirty checking trên record.
- Repository `save()` không lưu record như một entity nếu record không phải entity hợp lệ.
- Muốn cập nhật dữ liệu, hãy tải entity managed trong transaction, thay đổi entity rồi để JPA flush.

Ví dụ cập nhật đúng cách:

~~~java
@Transactional
public void updateCustomerEmail(Long id, String newEmail) {
    Customer customer = customerRepository.findById(id)
        .orElseThrow(() -> new EntityNotFoundException("Customer not found"));

    customer.changeEmail(newEmail);
}
~~~

Sau đó, nếu cần trả DTO, có thể map entity sang record:

~~~java
@Transactional
public CustomerSummary updateAndReturn(
        Long id,
        String newEmail) {

    Customer customer = customerRepository.findById(id)
        .orElseThrow(() -> new EntityNotFoundException("Customer not found"));

    customer.changeEmail(newEmail);

    return new CustomerSummary(
        customer.getId(),
        customer.getFullName(),
        customer.getEmail()
    );
}
~~~

Đoạn service trên minh họa mô hình: entity được quản lý trong transaction, còn record chỉ là dữ liệu trả về. Phương thức `changeEmail` là logic domain của entity ví dụ và cần được định nghĩa trong lớp `Customer`.

## 12. Lợi ích hiệu năng và giới hạn

DTO projection có thể giảm lượng dữ liệu đọc và số object entity được tạo. Khi chỉ chọn các scalar cần thiết, provider có thể tránh tải nhiều cột hoặc quan hệ không cần dùng.

Lợi ích thường thấy:

- Ít dữ liệu truyền từ database về ứng dụng.
- Ít entity được materialize và quản lý trong persistence context.
- Giảm nguy cơ vô tình truy cập lazy relationship trong tầng trình bày.
- Kiểu trả về thể hiện chính xác dữ liệu use case cần.

Tuy nhiên, DTO projection không tự động bảo đảm truy vấn nhanh hơn. Hiệu năng còn phụ thuộc:

- JOIN và điều kiện lọc.
- Index và execution plan.
- Số lượng hàng trả về.
- Aggregate, sort và pagination.
- Cách provider tạo SQL.
- Việc DTO cần nhiều quan hệ hoặc biểu thức tính toán.

Nếu record projection dùng quan hệ như `c.address.city`, provider có thể tạo JOIN để lấy trường đó. Hãy xem SQL sinh ra thay vì chỉ nhìn số component trong record.

Một DTO query cũng không tự ngăn N+1 trong mọi trường hợp. Nếu service gọi thêm repository cho từng record hoặc thực hiện truy vấn khác trong vòng lặp, N+1 vẫn có thể xuất hiện.

## 13. Lỗi thường gặp khi dùng record projection

### 13.1. Sai package trong SELECT NEW

JPQL constructor expression cần tên đầy đủ của class DTO:

~~~java
select new com.example.customer.dto.CustomerSummary(
    c.id, c.fullName, c.email
)
~~~

Nếu chỉ viết `new CustomerSummary(...)` mà provider không thể phân giải tên class, query sẽ thất bại. Kiểm tra package và class name chính xác.

### 13.2. Sai thứ tự constructor argument

Nếu record là `(Long id, String fullName, String email)`, truy vấn phải chọn các biểu thức theo thứ tự và kiểu tương ứng. Đổi chỗ `id` và `fullName` sẽ làm constructor không khớp.

### 13.3. Kiểu dữ liệu không khớp

Các biểu thức aggregate, enum, timestamp, UUID hoặc numeric có thể trả về kiểu khác với kiểu record khai báo. Kiểm tra đặc tả JPQL, JDBC driver và provider. Dùng wrapper như `Long` khi giá trị có thể NULL; không dùng primitive nếu truy vấn có thể trả NULL.

### 13.4. Tên component không khớp với entity property

Với derived class-based projection, tên thành phần record giúp Spring Data xác định property cần lấy. Nếu tên khác entity property, dùng JPQL constructor expression hoặc thay tên component cho phù hợp.

### 13.5. Coi record DTO là entity

Không gắn `@Entity` cho record để dùng với `save()`. Hãy giữ entity cho persistence và record cho dữ liệu projection.

### 13.6. Native query trả cột sai thứ tự

Khi ánh xạ native query trực tiếp vào record, thứ tự cột và kiểu kết quả phải tương thích với constructor. Nếu mapping phức tạp, dùng `@SqlResultSetMapping` hoặc tự map trong custom repository.

### 13.7. Quên count query đúng khi phân trang

Một DTO page có thể hiển thị đúng nội dung nhưng tổng số phần tử sai nếu `countQuery` không tương ứng với truy vấn chính. Kiểm tra JOIN, DISTINCT và GROUP BY trong cả hai truy vấn.

## 14. Kiểm thử record projection

Nên dùng `@DataJpaTest` hoặc integration test với database phù hợp để xác nhận query và constructor mapping.

Ví dụ:

~~~java
@DataJpaTest
class CustomerProjectionRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void returnsCustomerSummary() {
        Customer customer = new Customer(
            "An Nguyen",
            "an@example.com",
            CustomerStatus.ACTIVE
        );
        repository.saveAndFlush(customer);

        List<CustomerSummary> result =
            repository.findByStatus(CustomerStatus.ACTIVE);

        assertThat(result).hasSize(1);
        assertThat(result.get(0).fullName()).isEqualTo("An Nguyen");
        assertThat(result.get(0).email()).isEqualTo("an@example.com");
    }
}
~~~

Đây là ví dụ kiểm thử ở tầng Spring Data JPA; constructor của entity, repository method, enum, imports và test dependencies cần khớp với dự án. Không có stdout Java độc lập vì test được chạy trong Spring test context.

Nên kiểm tra thêm:

1. Record có đúng thứ tự và kiểu constructor không?
2. Query có chọn đúng các trường cần thiết không?
3. Khi không có bản ghi, repository trả list rỗng hay Optional rỗng như mong đợi?
4. Các trường nullable có được ánh xạ an toàn không?
5. Aggregate có trả đúng kiểu và giá trị không?
6. Page content và total count có khớp không?
7. Native query có chạy trên đúng database production không?
8. SQL có tải thừa quan hệ hoặc tạo JOIN không cần thiết không?

Với native projection hoặc truy vấn phụ thuộc dialect, ưu tiên Testcontainers hoặc database test tương đương môi trường production thay vì chỉ dựa vào H2.

## 15. Quy trình chọn và triển khai record DTO projection

Khi xây dựng một use case đọc dữ liệu:

1. Xác định chính xác các trường màn hình/API/báo cáo cần.
2. Tạo record DTO với component, kiểu dữ liệu và thứ tự rõ ràng.
3. Chọn derived query nếu property projection đơn giản và tên component khớp entity property.
4. Chọn JPQL `SELECT NEW` nếu cần kiểm soát rõ trường, điều kiện, JOIN hoặc phép tính.
5. Chọn native SQL khi cần tính năng database-specific; kiểm tra thứ tự cột, kiểu JDBC và result mapping.
6. Nếu dùng `Page`, khai báo hoặc xác minh count query tương ứng.
7. Dùng record như dữ liệu đọc; cập nhật thông qua entity managed trong transaction.
8. Kiểm tra SQL sinh ra và viết integration test cho constructor mapping, NULL, aggregate và phân trang.

## 16. Ghi nhớ

- Java record (Java 16+) phù hợp làm class-based DTO projection trong Spring Data JPA.
- Record DTO không phải JPA entity và không được persistence context quản lý.
- Derived DTO projection cần constructor/component tương thích với thuộc tính entity.
- JPQL `SELECT NEW` phải dùng tên class đầy đủ và truyền đối số đúng thứ tự canonical constructor.
- Record giúp khai báo DTO ngắn gọn, nhưng thành phần chỉ bất biến nông.
- DTO projection có thể chọn ít cột hơn entity query; hiệu năng vẫn phụ thuộc SQL, JOIN, index và execution plan.
- Có thể dùng record cho kết quả aggregate, `Page<T>` và dynamic projection nếu kiểu truy vấn tương thích.
- Native query cần chú ý thứ tự cột và kiểu JDBC; mapping phức tạp có thể cần `@SqlResultSetMapping`.
- Muốn cập nhật dữ liệu, tải và thay đổi entity managed; không dùng record DTO làm đối tượng `save()`.
- Kiểm thử truy vấn trên database mục tiêu, đặc biệt với native SQL và kiểu dữ liệu đặc thù.

Dùng Java record làm DTO projection giúp repository trả đúng dữ liệu mà use case cần với cấu trúc kiểu rõ ràng và ít mã phụ trợ. Hãy giữ record ở vai trò dữ liệu đọc, để entity đảm nhiệm vòng đời persistence, và xác nhận constructor, kiểu kết quả cùng SQL thực tế bằng integration test.