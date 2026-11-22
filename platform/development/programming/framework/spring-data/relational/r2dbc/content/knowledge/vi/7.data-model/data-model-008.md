# Phân biệt thực thể, đối tượng giá trị, DTO và kết quả tổng hợp

Trong một ứng dụng Spring Data Relational R2DBC, dữ liệu có thể xuất hiện dưới nhiều hình dạng: đối tượng được lưu trong database, thành phần cấu thành một mô hình nghiệp vụ, dữ liệu gửi qua API hoặc kết quả được tính từ nhiều dòng. Những hình dạng này có thể chứa các trường giống nhau nhưng có ý nghĩa và vòng đời khác nhau.

Ví dụ, thông tin khách hàng có thể được biểu diễn thành:

- Một **thực thể (entity)** có mã định danh ổn định, chẳng hạn khách hàng có ID 42.
- Một **đối tượng giá trị (value object)** như địa chỉ, được xác định bởi nội dung của nó.
- Một **DTO** chứa tên và địa chỉ để trả về cho màn hình hoặc API.
- Một **kết quả tổng hợp** cho biết mỗi trạng thái có bao nhiêu khách hàng.

Phân biệt đúng các loại này giúp thiết kế mô hình domain, schema, repository và truy vấn rõ ràng. Đặc biệt, trong Spring Data Relational, cần phân biệt entity với aggregate root của Domain-Driven Design (DDD), đồng thời không nhầm aggregate của DDD với kết quả của câu SQL dùng hàm tổng hợp.

## 1. Thực thể (Entity)

**Entity là đối tượng có danh tính riêng và danh tính đó tồn tại qua những lần thay đổi trạng thái.** Hai đối tượng có cùng tên và địa chỉ vẫn có thể là hai entity khác nhau nếu chúng có ID khác nhau. Ngược lại, một entity vẫn là cùng một entity khi tên, email hoặc địa chỉ được cập nhật.

Ví dụ:

| ID | Tên | Email |
|---:|---|---|
| 42 | An | an@example.com |
| 57 | An | an@example.com |

Hai dòng trên mô tả hai khách hàng riêng biệt dù các thuộc tính đang giống nhau. ID giúp hệ thống nhận diện từng khách hàng.

Trong Spring Data Relational, một entity được ánh xạ với bảng bằng các annotation mapping. Ví dụ:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    private String email;

    private String status;

    protected Customer() {
    }

    public Customer(String name, String email, String status) {
        this.name = name;
        this.email = email;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public String getStatus() {
        return status;
    }
}
~~~

- **@Table** chỉ định bảng được ánh xạ.
- **@Id** đánh dấu thuộc tính định danh.
- Spring Data dùng mapping metadata để chuyển đổi giữa dòng dữ liệu và đối tượng Java.
- Repository thường thao tác với entity hoặc aggregate root theo ID.

Ví dụ repository reactive:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByStatus(String status);
}
~~~

Entity không nhất thiết phải là một class có annotation. Entity là khái niệm mô hình domain; annotation của Spring Data giúp ánh xạ mô hình đó với dữ liệu quan hệ.

### Entity trong Spring Data Relational không đồng nghĩa với entity được quản lý bởi JPA

Đây là điểm dễ gây nhầm lẫn khi chuyển từ Spring Data JPA sang Spring Data JDBC hoặc R2DBC. Spring Data Relational có thể ánh xạ một class có ID thành entity, nhưng không cung cấp persistence context kiểu JPA/Hibernate để theo dõi mọi object đang được quản lý và tự động dirty checking.

Trong cách làm việc thông thường:

- Ứng dụng tải aggregate qua repository.
- Ứng dụng thay đổi trạng thái object.
- Ứng dụng gọi thao tác lưu phù hợp để ghi thay đổi xuống database.
- Spring Data thực hiện các câu SQL theo mapping và quy tắc của module.

Không nên giả định rằng chỉ cần thay đổi một thuộc tính trên object đã tải thì Spring Data R2DBC sẽ tự phát hiện và ghi lại như Hibernate trong một persistence context.

## 2. Aggregate root và ranh giới aggregate

Trong DDD, **aggregate** là một nhóm đối tượng domain được xem như một đơn vị nhất quán. **Aggregate root** là entity đứng ở ranh giới bên ngoài của nhóm đó; code bên ngoài truy cập và yêu cầu thay đổi các thành phần thuộc aggregate thông qua root.

Ví dụ một đơn hàng có thể bao gồm:

- **PurchaseOrder:** aggregate root, có ID và trạng thái đơn hàng.
- **OrderLine:** dòng hàng thuộc đơn hàng.
- **Money:** value object biểu diễn số tiền và đơn vị tiền tệ.

Một repository thường được thiết kế quanh aggregate root:

~~~java
public interface PurchaseOrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {
}
~~~

Code nghiệp vụ tải đơn hàng, gọi hành vi trên root rồi lưu aggregate theo quy tắc của mô hình. Các dòng hàng được quản lý như thành phần bên trong aggregate, thay vì để các service tùy ý cập nhật từng dòng mà bỏ qua quy tắc của đơn hàng.

Spring Data Relational hỗ trợ ánh xạ aggregate và các thành phần của aggregate bằng mapping metadata. Ví dụ **@MappedCollection** có thể dùng để ánh xạ collection thuộc root vào bảng liên quan. Các aggregate khác thường được tham chiếu bằng ID thay vì nhúng toàn bộ object graph vào cùng một aggregate.

Điều quan trọng: entity là đối tượng có danh tính; aggregate là ranh giới nhất quán của một nhóm đối tượng. Một aggregate root là entity, nhưng không phải mọi entity đều nhất thiết là aggregate root.

## 3. Đối tượng giá trị (Value Object)

**Value object được xác định bởi giá trị của các thuộc tính, không có danh tính độc lập.** Nếu hai value object có cùng giá trị theo quy tắc domain thì chúng được xem là tương đương, dù được tạo thành hai instance khác nhau.

Ví dụ địa chỉ:

~~~java
public record Address(
    String street,
    String city,
    String postalCode
) {
}
~~~

Hai địa chỉ có cùng đường, thành phố và mã bưu chính được xem là cùng một giá trị. Nếu khách hàng đổi địa chỉ, domain thường thay value object cũ bằng value object mới; không nhất thiết phải cập nhật một entity Address độc lập.

Value object thường có những đặc điểm:

- Không có ID nghiệp vụ riêng.
- So sánh dựa trên giá trị của các thuộc tính.
- Nên bất biến (immutable) sau khi tạo để tránh thay đổi ngoài ý muốn.
- Có thể chứa quy tắc nghiệp vụ và kiểm tra tính hợp lệ của chính nó.
- Thường được dùng bên trong entity hoặc aggregate.

Ví dụ Money:

~~~java
public record Money(
    BigDecimal amount,
    Currency currency
) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Amount must not be negative"
            );
        }
    }
}
~~~

Money không chỉ là hai cột dữ liệu. Nó có thể chứa quy tắc như không cho phép số tiền âm trong một ngữ cảnh, kiểm tra loại tiền tệ khi cộng và áp dụng quy tắc làm tròn.

### Ánh xạ value object trong Spring Data Relational

Một value object đơn giản có thể được ánh xạ vào cùng bảng với entity bằng cơ chế embedded mapping:

~~~java
public record Address(
    String street,
    String city,
    String postalCode
) {
}

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    @Embedded(prefix = "address_")
    private Address address;
}
~~~

Các thuộc tính của Address được ánh xạ thành các cột của bảng customer, chẳng hạn:

| Cột | Giá trị |
|---|---|
| id | 42 |
| name | An |
| address_street | 12 Nguyen Trai |
| address_city | Ho Chi Minh City |
| address_postal_code | 700000 |

Prefix giúp tránh trùng tên cột và làm rõ các cột thuộc value object nào. Khả năng và quy tắc xử lý embedded object, bao gồm trường hợp toàn bộ giá trị là null, phụ thuộc annotation và phiên bản Spring Data Relational đang dùng.

Một value object cũng có thể được lưu trong bảng riêng như một thành phần thuộc aggregate, tùy mô hình và cách mapping. Việc nó nằm ở bảng riêng không tự động biến nó thành entity độc lập. Cần xét identity và quy tắc vòng đời trong domain, không chỉ nhìn số lượng bảng.

## 4. DTO (Data Transfer Object)

**DTO là đối tượng dùng để chuyển dữ liệu qua một ranh giới**, chẳng hạn giữa controller và service, giữa service và client khác, hoặc giữa tầng truy vấn và màn hình. DTO định hình dữ liệu cần truyền mà không nhất thiết phản ánh đầy đủ mô hình domain hay cấu trúc bảng.

Ví dụ API chỉ cần trả ID, tên và thành phố của khách hàng:

~~~java
public record CustomerResponse(
    Long id,
    String name,
    String city
) {
}
~~~

Entity Customer có thể chứa email, trạng thái, địa chỉ đầy đủ và các thuộc tính nội bộ khác. DTO CustomerResponse chỉ chứa trường mà API cần công bố.

Việc dùng DTO mang lại một số lợi ích:

- Không để schema database quyết định trực tiếp cấu trúc API.
- Không vô tình trả các trường nội bộ hoặc dữ liệu nhạy cảm.
- Cho phép một API ghép dữ liệu từ nhiều entity hoặc nguồn khác nhau.
- Có thể đặt tên trường theo ngôn ngữ của API thay vì tên cột.
- Có thể thay đổi cấu trúc response mà không phải thay đổi entity domain.

DTO thường không có identity hoặc lifecycle persistence riêng. Hai DTO có cùng nội dung có thể được xem là hai thông điệp dữ liệu tương đương; điều đó không tạo ra hai khách hàng khác nhau.

### DTO đầu vào và DTO đầu ra

Không nhất thiết phải dùng một DTO cho cả request và response.

Ví dụ request tạo khách hàng:

~~~java
public record CreateCustomerRequest(
    String name,
    String email,
    String street,
    String city,
    String postalCode
) {
}
~~~

Service kiểm tra dữ liệu, tạo value object và entity:

~~~java
public Mono<CustomerResponse> create(
        CreateCustomerRequest request) {

    Address address = new Address(
        request.street(),
        request.city(),
        request.postalCode()
    );

    Customer customer = new Customer(
        request.name(),
        request.email(),
        address
    );

    return customerRepository.save(customer)
        .map(saved -> new CustomerResponse(
            saved.getId(),
            saved.getName(),
            saved.getAddress().city()
        ));
}
~~~

Ví dụ trên thể hiện ranh giới chuyển đổi: request DTO đi vào, domain object được tạo và kiểm tra, repository lưu entity, rồi response DTO được tạo để trả ra ngoài.

Không nên để controller nhận trực tiếp entity rồi bind mọi trường từ request vào object persistence. Cách đó có thể cho phép client thay đổi những thuộc tính mà nghiệp vụ không muốn công khai, ví dụ ID, trạng thái phê duyệt hoặc thông tin quản trị.

## 5. Projection và DTO dùng cho truy vấn

Ở chiều đọc, ứng dụng thường không cần tải toàn bộ entity. Một màn hình có thể chỉ cần tên khách hàng và số đơn hàng. **Projection** là cách biểu diễn một phần dữ liệu cần đọc; DTO là một dạng class/record có thể dùng làm kiểu projection.

Ví dụ read model:

~~~java
public record CustomerOrderCount(
    Long customerId,
    String customerName,
    Long orderCount
) {
}
~~~

Kết quả này không nhất thiết là entity Customer. Nó là dữ liệu được tạo từ phép join và phép đếm. Không nên lưu nó qua CustomerRepository như thể đó là một khách hàng hoàn chỉnh.

Trong Spring Data, projection có thể được biểu diễn bằng interface hoặc DTO tùy kiểu truy vấn và khả năng của module. Với truy vấn SQL tùy chỉnh trong R2DBC, DatabaseClient cho phép ánh xạ tường minh từng cột sang DTO:

~~~java
Flux<CustomerOrderCount> results =
    databaseClient.sql(
        "SELECT c.id AS customer_id, " +
        "c.name AS customer_name, " +
        "COUNT(o.id) AS order_count " +
        "FROM customer c " +
        "LEFT JOIN purchase_order o ON o.customer_id = c.id " +
        "GROUP BY c.id, c.name"
    )
    .map((row, metadata) -> new CustomerOrderCount(
        row.get("customer_id", Long.class),
        row.get("customer_name", String.class),
        row.get("order_count", Long.class)
    ))
    .all();
~~~

Mapping tường minh giúp nhìn thấy rõ:

1. SQL chọn những cột nào.
2. Alias nào được dùng cho kết quả.
3. Kiểu Java nào được yêu cầu khi đọc từng cột.
4. DTO nào được tạo từ một dòng kết quả.

Kiểu Java phù hợp cho một cột tổng hợp có thể phụ thuộc database và R2DBC driver. Ví dụ COUNT thường được ánh xạ thành kiểu số nguyên rộng, nhưng nên xác nhận bằng driver thực tế và kiểm thử tích hợp.

## 6. Kết quả tổng hợp từ SQL (Aggregate Query Result)

Trong SQL, từ aggregate thường chỉ các phép tính tổng hợp dữ liệu trên một nhóm dòng. Các hàm phổ biến gồm:

| Hàm | Ý nghĩa | Ví dụ |
|---|---|---|
| COUNT | Đếm số dòng hoặc giá trị không null | Số khách hàng |
| SUM | Tính tổng | Tổng doanh thu |
| AVG | Tính trung bình | Giá trị đơn hàng trung bình |
| MIN | Tìm giá trị nhỏ nhất | Ngày tạo sớm nhất |
| MAX | Tìm giá trị lớn nhất | Ngày tạo gần nhất |

Ví dụ đếm số khách hàng theo trạng thái:

~~~sql
SELECT status, COUNT(*) AS customer_count
FROM customer
GROUP BY status;
~~~

Kết quả có thể như sau:

| status | customer_count |
|---|---:|
| ACTIVE | 120 |
| BLOCKED | 8 |
| PENDING | 15 |

Mỗi dòng trong kết quả đại diện cho một nhóm trạng thái. Nó không phải entity Customer vì không có một khách hàng cụ thể nào tương ứng với dòng đó. Nó cũng không nhất thiết phải được lưu trong một bảng.

Ta có thể định nghĩa DTO cho kết quả:

~~~java
public record CustomerStatusCount(
    String status,
    Long customerCount
) {
}
~~~

Và ánh xạ kết quả bằng DatabaseClient:

~~~java
Flux<CustomerStatusCount> counts =
    databaseClient.sql(
        "SELECT status, COUNT(*) AS customer_count " +
        "FROM customer GROUP BY status"
    )
    .map((row, metadata) -> new CustomerStatusCount(
        row.get("status", String.class),
        row.get("customer_count", Long.class)
    ))
    .all();
~~~

Nếu truy vấn chỉ trả về một giá trị, có thể dùng Mono:

~~~java
Mono<Long> totalCustomers =
    databaseClient.sql("SELECT COUNT(*) AS total FROM customer")
        .map((row, metadata) -> row.get("total", Long.class))
        .one();
~~~

Kết quả tổng hợp thường phù hợp với báo cáo, dashboard, thống kê và màn hình đọc. Vì dữ liệu đã được tính trong database, ứng dụng không cần tải tất cả entity về bộ nhớ rồi tự đếm.

### Một số lưu ý khi dùng hàm tổng hợp

- COUNT(*) đếm số dòng; COUNT(column) bỏ qua dòng có giá trị null ở cột đó.
- SUM và AVG thường bỏ qua giá trị null; kiểu trả về phụ thuộc kiểu cột và database.
- GROUP BY tạo một dòng kết quả cho mỗi nhóm theo các biểu thức nhóm.
- HAVING lọc nhóm sau khi tổng hợp; WHERE lọc dòng trước khi nhóm.
- Join một-nhiều có thể nhân số dòng trước khi tính COUNT hoặc SUM. Cần chọn đúng cột và cấu trúc truy vấn để không đếm trùng.
- Khi kết quả có thể không có dòng, dùng API trả về kiểu tùy chọn hoặc Mono đúng với semantics của truy vấn.

Ví dụ phân biệt WHERE và HAVING:

~~~sql
SELECT status, COUNT(*) AS customer_count
FROM customer
WHERE created_at >= :from_date
GROUP BY status
HAVING COUNT(*) >= 10;
~~~

WHERE giới hạn các khách hàng được đưa vào phép tổng hợp. HAVING chỉ giữ các nhóm có ít nhất 10 khách hàng.

## 7. Không nhầm kết quả SQL aggregate với DDD aggregate

Hai khái niệm dùng chung từ aggregate nhưng khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| DDD aggregate | Nhóm đối tượng domain có ranh giới nhất quán và một aggregate root | Đơn hàng cùng các dòng hàng |
| SQL aggregate | Phép tính trên nhiều dòng dữ liệu | COUNT đơn hàng theo trạng thái |
| Aggregate query result | Các giá trị được trả về sau phép tính hoặc GROUP BY | Trạng thái và số lượng đơn hàng |

DDD aggregate là cách tổ chức mô hình nghiệp vụ và kiểm soát thay đổi. SQL aggregate là phép tính trong truy vấn. Một aggregate root có thể được lưu qua nhiều bảng; một aggregate query result có thể được tính từ một hoặc nhiều bảng mà không tạo ra entity domain mới.

Ví dụ, PurchaseOrder là aggregate root. Truy vấn tổng doanh thu theo tháng có thể đọc nhiều PurchaseOrder và OrderLine rồi trả về MonthlyRevenue. MonthlyRevenue là read model/DTO cho báo cáo, không phải một aggregate root chỉ vì tên có từ aggregate.

## 8. So sánh bốn loại dữ liệu

| Tiêu chí | Entity | Value Object | DTO | Kết quả tổng hợp |
|---|---|---|---|---|
| Danh tính riêng | Có | Không | Thường không | Không nhất thiết |
| So sánh | Theo identity | Theo giá trị | Theo mục đích truyền dữ liệu | Theo các giá trị được tính |
| Vòng đời domain | Có | Phụ thuộc entity/aggregate chứa nó | Theo lần truyền dữ liệu | Theo lần thực thi truy vấn |
| Có cần lưu database? | Thường có | Có thể lưu cùng entity hoặc thành phần aggregate | Không bắt buộc | Thường được tính khi truy vấn |
| Mục đích chính | Đại diện một đối tượng có identity | Mô tả một giá trị nghiệp vụ | Truyền dữ liệu qua ranh giới | Thống kê, báo cáo, phân tích |
| Ví dụ | Customer | Address, Money | CustomerResponse | CustomerStatusCount |

Không nên phân loại chỉ dựa trên tên class hoặc số lượng thuộc tính. Một class có ba trường có thể là DTO, value object hoặc projection tùy vai trò và semantics của nó.

## 9. Tổ chức mô hình dữ liệu trong ứng dụng R2DBC

Một cách tổ chức phổ biến là giữ domain model ở tầng nghiệp vụ, dùng Spring Data Relational để ánh xạ aggregate cần persistence, và dùng DTO/projection riêng cho biên đọc/ghi.

Ví dụ cấu trúc:

~~~text
API
 |
 +-- CreateCustomerRequest
 |
 v
Application Service
 |
 +-- Kiểm tra dữ liệu đầu vào
 +-- Tạo Address (Value Object)
 +-- Tạo Customer (Entity / Aggregate Root)
 |
 v
CustomerRepository
 |
 v
Spring Data R2DBC
 |
 v
Database

DatabaseClient / Query Repository
 |
 +-- SQL JOIN / GROUP BY / COUNT
 |
 v
CustomerStatusCount (DTO / Read Model)
 |
 v
API hoặc Dashboard
~~~

Một số nguyên tắc thiết kế:

1. Dùng entity cho đối tượng cần identity và có vòng đời nghiệp vụ.
2. Dùng value object cho các khái niệm được xác định bằng giá trị và có thể đóng gói quy tắc.
3. Giữ aggregate đủ nhỏ để ranh giới nhất quán và thao tác lưu có thể kiểm soát.
4. Dùng DTO riêng cho request/response để không phơi bày toàn bộ persistence model.
5. Dùng projection hoặc DTO cho truy vấn chỉ cần một phần dữ liệu.
6. Dùng kết quả tổng hợp cho thống kê thay vì tải toàn bộ entity về ứng dụng để tính lại.

## 10. Chọn repository hay DatabaseClient?

Không phải mọi truy vấn đều cần một entity hoàn chỉnh.

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Tìm, lưu hoặc xóa aggregate root theo ID | Spring Data R2DBC repository |
| Truy vấn theo thuộc tính đơn giản, có thể diễn đạt bằng tên method | Derived query method |
| Trả về một tập trường tùy chỉnh | Projection hoặc DTO |
| Join phức tạp, GROUP BY, COUNT, SUM hoặc báo cáo | DatabaseClient hoặc custom repository |
| Thực thi SQL đặc thù của database | DatabaseClient với SQL được kiểm soát |
| Chuyển dữ liệu ra API | Request/response DTO |

Repository giúp code persistence thông thường dễ đọc. DatabaseClient phù hợp khi cần kiểm soát SQL và ánh xạ một read model cụ thể. Hai cách tiếp cận có thể cùng tồn tại trong một ứng dụng.

Với truy vấn báo cáo, không nên cố ánh xạ kết quả GROUP BY vào entity chỉ để tận dụng repository CRUD. Hãy tạo kiểu kết quả phù hợp với chính dữ liệu mà truy vấn trả về.

## 11. Những nhầm lẫn thường gặp

**“Mỗi class có @Table đều là aggregate root.”** Không đúng. @Table mô tả mapping tới bảng. Aggregate root là vai trò trong mô hình domain và ranh giới nhất quán.

**“Value object phải nằm trong cùng một bảng với entity.”** Không bắt buộc. Nó có thể được embedded vào bảng hoặc được lưu thành phần trong bảng liên quan. Cách lưu không tự quyết định identity của nó.

**“DTO chỉ là entity đổi tên.”** Không đúng. DTO được thiết kế cho mục đích truyền dữ liệu và có thể chỉ chứa một phần trường, kết hợp nhiều nguồn hoặc dùng tên trường khác.

**“Kết quả COUNT/GROUP BY là entity.”** Không đúng nếu mỗi dòng chỉ đại diện cho một nhóm và không có identity nghiệp vụ. Nên ánh xạ thành projection hoặc DTO.

**“Có thể trả entity trực tiếp từ REST API trong mọi trường hợp.”** Cách đó làm API phụ thuộc mạnh vào persistence model và có thể lộ trường nội bộ. DTO giúp kiểm soát hợp đồng API.

**“Spring Data R2DBC tự theo dõi thay đổi của entity giống Hibernate.”** Không đúng. Spring Data Relational không có persistence context và dirty checking kiểu JPA/Hibernate.

**“Aggregate trong DDD và aggregate trong SQL là một.”** Không đúng. Một khái niệm nói về ranh giới domain, khái niệm kia nói về phép tính trên tập dòng.

## 12. Ghi nhớ

- **Entity:** có identity ổn định; trạng thái có thể thay đổi nhưng vẫn là cùng một đối tượng domain.
- **Aggregate root:** entity làm điểm truy cập và ranh giới nhất quán cho một aggregate trong DDD.
- **Value Object:** không có identity độc lập; được xác định bởi giá trị, thường nên bất biến.
- **DTO:** định hình dữ liệu để truyền qua ranh giới; không nhất thiết là mô hình persistence hoặc domain.
- **Projection:** chỉ lấy phần dữ liệu cần đọc; có thể được biểu diễn bằng interface hoặc DTO.
- **Kết quả tổng hợp SQL:** dữ liệu trả về từ COUNT, SUM, AVG, MIN, MAX hoặc GROUP BY; thường là read model/DTO chứ không phải entity.
- Trong Spring Data R2DBC, repository phù hợp với persistence của aggregate; DatabaseClient phù hợp với SQL tùy chỉnh và read model.
- Không nhầm entity với aggregate root, value object với bảng riêng, hoặc SQL aggregate result với DDD aggregate.
