# Projection lồng nhau và nguy cơ tải quan hệ ngoài dự kiến trong Spring Data JPA

Projection cho phép repository trả về hình dạng dữ liệu mà caller cần thay vì trả toàn bộ entity. Với interface projection, Spring Data JPA có thể tạo proxy để cung cấp các thuộc tính được khai báo trong interface. Nested projection mở rộng cách này: một getter có thể trả về một projection interface khác đại diện cho quan hệ của entity gốc.

Nested projection giúp API đọc dữ liệu gọn và dễ tổ chức, nhưng không bảo đảm database chỉ đọc đúng một trường ở cấp quan hệ lồng nhau. Spring Data JPA có thể tối ưu các thuộc tính cấp cao nhất của projection; một thuộc tính lồng nhau cần JOIN có thể khiến toàn bộ thuộc tính quan hệ được materialize. Nếu quan hệ là collection, kết quả còn có thể làm nhân số hàng, tăng dữ liệu truyền về và gây khó khăn khi phân trang.

Bài này phân tích cơ chế, minh họa bằng Customer và Address, so sánh nested projection với flat interface projection và DTO, rồi chỉ cách kiểm tra SQL để phát hiện tải dữ liệu ngoài dự kiến.

## 1. Projection và nested projection là gì?

Giả sử entity Customer có các trường tên và quan hệ đến Address. Một màn hình danh sách chỉ cần ID, tên khách hàng và thành phố.

Nếu repository trả entity:

~~~java
List<Customer> findByLastName(String lastName);
~~~

caller nhận entity Customer. Khi đọc `customer.getAddress().getCity()`, provider có thể phải tải quan hệ Address. Nếu caller serialize entity, các getter khác hoặc quan hệ khác cũng có thể bị truy cập ngoài ý muốn.

Một interface projection chỉ khai báo dữ liệu cần dùng:

~~~java
public interface CustomerNameView {
    Long getId();
    String getFirstName();
    String getLastName();
}
~~~

Nested projection cho phép biểu diễn quan hệ bằng một interface con:

~~~java
public interface CustomerCard {
    Long getId();
    String getFirstName();
    String getLastName();

    AddressView getAddress();

    interface AddressView {
        String getCity();
    }
}
~~~

Repository có thể trả trực tiếp projection:

~~~java
List<CustomerCard> findByLastName(String lastName);
~~~

Caller dùng:

~~~java
for (CustomerCard customer : customers) {
    String name = customer.getFirstName() + " " + customer.getLastName();
    String city = customer.getAddress() == null
            ? null
            : customer.getAddress().getCity();
}
~~~

Projection lồng nhau làm API Java dễ đọc: CustomerCard chứa AddressView. Tuy nhiên, cấu trúc interface không đồng nghĩa với cấu trúc SELECT chỉ lấy address.city.

## 2. Mô hình entity minh họa

Giả sử một khách hàng có thể chưa có địa chỉ hoặc có một địa chỉ chính. Ví dụ dùng quan hệ Many-to-One để tập trung vào cách tải quan hệ; có thể thay bằng One-to-One tùy mô hình nghiệp vụ.

### 2.1. Entity Address

Tạo file `Address.java`:

~~~java
package com.example.projection;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "addresses")
public class Address {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String street;

    @Column(nullable = false, length = 100)
    private String city;

    @Column(length = 20)
    private String postalCode;

    protected Address() {
    }

    public Address(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public Long getId() {
        return id;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
~~~

### 2.2. Entity Customer

Tạo file `Customer.java`:

~~~java
package com.example.projection;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 80)
    private String firstName;

    @Column(nullable = false, length = 80)
    private String lastName;

    @Column(nullable = false, unique = true, length = 150)
    private String email;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "address_id")
    private Address address;

    protected Customer() {
    }

    public Customer(
            String firstName,
            String lastName,
            String email,
            Address address) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.email = email;
        this.address = address;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public String getEmail() {
        return email;
    }

    public Address getAddress() {
        return address;
    }
}
~~~

Customer.address được khai báo LAZY để provider có thể trì hoãn tải quan hệ. Hãy nhớ FetchType.LAZY là hint theo Jakarta Persistence; provider được phép tải sớm hơn nếu cần. Việc projection khai báo getter lồng nhau và việc entity mapping đặt LAZY là hai yếu tố có liên quan nhưng không phải cùng một cơ chế.

## 3. Nested interface projection hoạt động như thế nào?

### 3.1. Khai báo projection lồng nhau

Tạo file `CustomerCard.java`:

~~~java
package com.example.projection;

public interface CustomerCard {

    Long getId();

    String getFirstName();

    String getLastName();

    AddressView getAddress();

    interface AddressView {
        String getCity();
    }
}
~~~

Khai báo repository:

~~~java
package com.example.projection;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<CustomerCard> findByLastName(String lastName);
}
~~~

Spring Data nhận thấy kiểu trả về là interface projection. Getter getAddress() đại diện cho thuộc tính address; kiểu trả về AddressView cho phép truy cập tiếp thuộc tính city.

Nested projection có thể được wrap đệ quy. Điều này giúp chia nhỏ cấu trúc kết quả theo domain, nhưng không đảm bảo mỗi getter lồng nhau tương ứng với một cột SELECT độc lập.

### 3.2. Giới hạn quan trọng: nested property không đồng nghĩa chọn một cột

Spring Data JPA có thể tối ưu closed interface projection để chỉ chọn các thuộc tính cấp cao nhất mà projection yêu cầu. Tuy nhiên, khi một thuộc tính lồng nhau cần JOIN để giải quyết đường dẫn quan hệ, JPA projection có thể chọn/materialize toàn bộ thuộc tính lồng nhau đó.

Trong ví dụ trên, projection chỉ khai báo AddressView.getCity(), nhưng không nên mặc định SQL chỉ đọc addresses.city. Việc truy cập address có thể khiến toàn bộ thuộc tính quan hệ Address được materialize với nhiều cột hơn cần thiết, chẳng hạn ID, street, city và postalCode.

Hãy phân biệt:

- **Hình dạng Java:** caller chỉ nhìn thấy các getter được khai báo trong projection.
- **Hình dạng SQL:** provider quyết định JOIN, cột được chọn và cách materialize theo query/mapping.
- **Hành vi tải:** một quan hệ có thể được tải trong query ban đầu hoặc được khởi tạo sau đó khi getter được gọi.

Không suy luận số cột, số JOIN hoặc số câu SQL chỉ từ số getter trong interface. Hãy xem SQL thực tế.

## 4. Vì sao nested projection có thể tải nhiều dữ liệu hơn mong đợi?

### 4.1. JOIN có thể materialize toàn bộ thuộc tính quan hệ

Khi projection truy cập customer.address.city, Spring Data cần giải quyết đường dẫn qua quan hệ address. Với JPA, nested property resolving to a join có thể khiến toàn bộ thuộc tính nested được materialize. Vì thế, một getter lồng nhau không tương đương với một phép chọn cột đơn giản.

Nếu Address có nhiều cột hoặc quan hệ khác, SQL có thể đọc nhiều dữ liệu hơn màn hình cần.

### 4.2. Lazy loading có thể phát SELECT khi getter được gọi

Nếu association vẫn được biểu diễn bằng proxy hoặc đối tượng lazy, lần gọi getAddress() hoặc getter thuộc tính bên trong có thể kích hoạt tải trạng thái. Khi nhiều customer được duyệt, số lần tải có thể tăng theo số hàng.

Không phải nested projection nào cũng gây N+1. Một query có thể JOIN và lấy quan hệ trong cùng một SQL. N+1 xuất hiện khi provider phải tải từng association riêng, chẳng hạn khi projection dựa trên entity/proxy và caller truy cập quan hệ lazy theo từng hàng. Cần kiểm tra log thay vì mặc định kết luận theo tên projection.

### 4.3. Serialize projection có thể kích hoạt getter ngoài dự kiến

Một serializer JSON có thể gọi getter để tạo response. Nếu response chứa nested projection, serializer có thể truy cập sâu hơn phần code nghiệp vụ đã chủ động đọc.

Ví dụ controller trả thẳng projection:

~~~java
@GetMapping("/customers")
public List<CustomerCard> findCustomers(
        @RequestParam String lastName) {
    return customers.findByLastName(lastName);
}
~~~

Tùy cấu trúc projection và serializer, việc dựng JSON có thể truy cập address, rồi city, và khởi tạo quan hệ lazy trong lúc serialize. Khi đó SQL phát sinh ngoài điểm mà người đọc code repository dễ nhận ra.

Nếu cần API ổn định, hãy chọn rõ hình dạng DTO, truy vấn và dữ liệu được tải trước khi trả response.

## 5. Nested projection với quan hệ ToMany còn có thêm rủi ro

Nested projection không chỉ áp dụng cho ToOne. Một projection có thể khai báo collection lồng nhau:

~~~java
public interface CustomerWithOrders {
    Long getId();
    String getFirstName();
    List<OrderView> getOrders();

    interface OrderView {
        Long getId();
        String getOrderNumber();
    }
}
~~~

Nếu một customer có nhiều order, JOIN có thể tạo nhiều hàng SQL cho cùng customer. Ví dụ một customer có 5 order có thể xuất hiện trong 5 hàng kết quả join trước khi provider/projection xử lý kết quả.

Các hệ quả có thể gặp:

- Tăng số hàng trung gian và lượng dữ liệu truyền từ database.
- Lặp dữ liệu của entity gốc trên các hàng join.
- Khó phân trang chính xác ở cấp customer.
- Tải collection lớn dù màn hình chỉ cần một vài order.
- Phát thêm query khi collection lazy được khởi tạo theo từng customer.

Không nên giả định Page<CustomerWithOrders> luôn phân trang đúng và hiệu quả nếu query phải materialize collection. Phân trang SQL diễn ra trên hàng join có thể không tương ứng với số customer duy nhất.

Với ToMany, cân nhắc lấy trang customer trước, sau đó tải dữ liệu con cho tập ID của trang bằng một query riêng hoặc dùng DTO query được thiết kế rõ ràng. Nếu method nhận Pageable, hãy kiểm tra cả query lấy nội dung và cách đếm tổng số customer.

## 6. Giải pháp 1: Flat interface projection với JOIN tường minh

Nếu màn hình chỉ cần tên thành phố, có thể tạo projection phẳng:

~~~java
package com.example.projection;

public interface CustomerCardFlat {
    Long getId();
    String getFirstName();
    String getLastName();
    String getCity();
}
~~~

Đây là flat interface projection: các trường của customer và address nằm cùng một cấp trong kết quả. Repository viết query chỉ chọn đúng các trường cần thiết:

~~~java
@Query("""
       select c.id as id,
              c.firstName as firstName,
              c.lastName as lastName,
              a.city as city
       from Customer c
       left join c.address a
       where c.lastName = :lastName
       order by c.id
       """)
List<CustomerCardFlat> findFlatCardsByLastName(
        @Param("lastName") String lastName);
~~~

Ở đây:

- LEFT JOIN giữ lại customer chưa có address.
- Chỉ các biểu thức c.id, c.firstName, c.lastName và a.city xuất hiện trong SELECT.
- Alias khớp tên getter của interface projection.
- Kết quả là projection phẳng, không cần truy cập nested association.
- ORDER BY c.id giúp thứ tự ổn định.

Đây là lựa chọn tốt khi muốn kiểm soát rõ cột được chọn mà vẫn dùng interface projection. Cần kiểm tra alias và kiểu kết quả với provider đang chạy.

## 7. Giải pháp 2: DTO constructor expression

Nếu muốn kiểu kết quả bất biến và constructor rõ ràng, dùng DTO:

~~~java
package com.example.projection;

public record CustomerCardDto(
        Long id,
        String firstName,
        String lastName,
        String city) {
}
~~~

JPQL constructor expression:

~~~java
@Query("""
       select new com.example.projection.CustomerCardDto(
           c.id,
           c.firstName,
           c.lastName,
           a.city
       )
       from Customer c
       left join c.address a
       where c.lastName = :lastName
       order by c.id
       """)
List<CustomerCardDto> findDtoCardsByLastName(
        @Param("lastName") String lastName);
~~~

Query chỉ chọn các biểu thức được truyền vào constructor. CustomerCardDto là DTO, không phải entity managed; thay đổi record hoặc object DTO không làm database tự cập nhật.

Ưu điểm:

- SELECT nêu rõ các trường cần đọc.
- Không trả proxy nested để serializer truy cập sau này.
- Constructor và kiểu dữ liệu được kiểm tra khi query được thực thi.
- Dễ dùng cho API response, báo cáo và use case chỉ đọc.

Lưu ý: tên lớp trong SELECT NEW phải là fully qualified class name. Thứ tự và kiểu đối số phải khớp constructor. a.city có thể null vì dùng LEFT JOIN, nên trường city phải chấp nhận null.

## 8. Giải pháp 3: Closed projection và default method

Closed projection chỉ khai báo các thuộc tính có thể đối chiếu trực tiếp với thuộc tính của target entity:

~~~java
public interface CustomerNameView {
    String getFirstName();
    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
~~~

Spring Data biết các thuộc tính mà projection cần. Default method chỉ kết hợp các getter đã khai báo, vì vậy vẫn giữ được khả năng tối ưu của closed projection trong các trường hợp được hỗ trợ.

Nếu dùng open projection với SpEL:

~~~java
public interface CustomerOpenView {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
~~~

Đây là open projection vì biểu thức có thể truy cập target entity. Spring Data không thể suy luận chắc chắn chỉ cần những thuộc tính nào để tính kết quả; vì vậy không thể tối ưu truy vấn theo cùng cách closed projection.

Quy tắc thực hành:

- Ưu tiên closed projection nếu chỉ cần thuộc tính entity.
- Dùng default method để ghép giá trị từ các getter đã khai báo.
- Chỉ dùng @Value/SpEL khi thật sự cần logic biểu thức.
- Nếu kết quả cần JOIN và chọn một vài trường lồng nhau, flat projection hoặc DTO thường dễ kiểm soát hơn nested projection.

## 9. Giải pháp 4: EntityGraph khi thực sự cần entity graph

Nếu use case cần entity Customer cùng Address để thực hiện logic trong transaction, có thể dùng EntityGraph:

~~~java
@EntityGraph(attributePaths = "address")
List<Customer> findWithAddressByLastName(String lastName);
~~~

EntityGraph yêu cầu provider tải quan hệ address theo fetch plan. Nó hữu ích khi caller thực sự cần entity và association.

Tuy nhiên, EntityGraph không phải công cụ chọn riêng một vài cột của nested entity. Khi tải Address như một phần entity graph, provider thường cần materialize entity Address theo mapping của nó. Nếu mục tiêu là chỉ đọc city, flat projection hoặc DTO phù hợp hơn.

Không chuyển mọi quan hệ thành EAGER để tránh nested lazy loading. Hãy quyết định fetch plan theo từng use case.

## 10. Optional và quan hệ có thể null

Nếu customer chưa có address, getAddress() có thể trả null. Caller cần xử lý:

~~~java
CustomerCard.AddressView address = card.getAddress();

String city = address == null
        ? "Chưa cập nhật"
        : address.getCity();
~~~

Spring Data projection cũng hỗ trợ một số wrapper như Optional cho thuộc tính có thể null:

~~~java
public interface CustomerOptionalView {
    Long getId();
    Optional<AddressView> getAddress();

    interface AddressView {
        String getCity();
    }
}
~~~

Kiểu wrapper giúp biểu đạt rõ dữ liệu có thể vắng mặt. Tuy nhiên, wrapper không thay đổi bản chất fetch plan: khi cần truy cập nested property, provider vẫn phải cung cấp dữ liệu theo mapping/query.

Nếu dùng DTO constructor expression với LEFT JOIN, kiểu tham chiếu như String hoặc Long có thể nhận null. Không dùng primitive cho đối số có thể null.

## 11. Kiểm thử để phát hiện tải ngoài dự kiến

Một test projection nên kiểm tra cả nội dung trả về lẫn SQL được thực thi. Chỉ xác nhận city đúng chưa đủ để biết query có tải thêm street, postalCode hoặc phát N+1 hay không.

### 11.1. Kiểm thử kết quả flat projection

Ví dụ với @DataJpaTest:

~~~java
@DataJpaTest
class CustomerProjectionTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private CustomerRepository customers;

    @Test
    void flatProjectionReturnsOnlyTheRequiredView() {
        Address address = new Address(
                "12 Nguyen Trai",
                "Ho Chi Minh City",
                "700000"
        );
        entityManager.persist(address);

        Customer customer = new Customer(
                "An",
                "Nguyen",
                "an@example.com",
                address
        );
        entityManager.persist(customer);

        entityManager.flush();
        entityManager.clear();

        List<CustomerCardFlat> result =
                customers.findFlatCardsByLastName("Nguyen");

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getFirstName()).isEqualTo("An");
        assertThat(result.get(0).getCity())
                .isEqualTo("Ho Chi Minh City");
    }
}
~~~

Ví dụ giả định repository có phương thức findFlatCardsByLastName và entity constructors đúng như phần trên. flush() ghi dữ liệu setup xuống database; clear() xóa persistence context để query được thực thi và không dựa vào entity instance đang managed.

### 11.2. So sánh nested và flat projection bằng SQL log

Trong profile test, có thể bật:

~~~properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Với Hibernate 6, logger org.hibernate.orm.jdbc.bind giúp quan sát giá trị bind. Chỉ bật bind logging trong môi trường phát triển/kiểm thử vì log có thể chứa dữ liệu nhạy cảm.

Thực hiện hai lần gọi riêng:

1. Gọi nested projection và truy cập getAddress().getCity().
2. Gọi flat projection và đọc getCity().
3. So sánh số câu SELECT, cột SELECT, JOIN và số hàng trả về.
4. Tăng số customer trong fixture để xem số query có tăng theo từng customer hay không.
5. Lặp lại với customer không có address và address có nhiều cột.

Không yêu cầu SQL phải giống nhau giữa Hibernate và EclipseLink. Hãy kiểm tra hành vi theo provider/version mà ứng dụng hỗ trợ. Nếu cần giới hạn số query, dùng Hibernate Statistics hoặc công cụ thu thập SQL trong integration test; assertion về số query nên gắn với provider và cấu hình cụ thể, không coi là hợp đồng JPA portable.

### 11.3. Kiểm thử ToMany và phân trang

Với nested collection projection, tạo fixture có:

- Một customer không có order.
- Một customer có một order.
- Một customer có nhiều order.
- Nhiều customer cùng thỏa điều kiện tìm kiếm.

Kiểm tra:

- Số customer duy nhất được trả về.
- Số order của từng customer.
- Trang đầu và trang tiếp theo có customer nào.
- Không có customer bị lặp hoặc bị bỏ sót do JOIN.
- Số query không tăng tuyến tính bất ngờ theo số customer.

Nếu phân trang collection projection không cho kết quả ổn định, chuyển sang phân trang customer trước rồi lấy orders cho danh sách ID của trang.

## 12. Cách nhận diện và xử lý N+1

N+1 là tình huống một query lấy danh sách entity gốc, sau đó phát thêm một query cho mỗi association được truy cập.

Ví dụ về mặt ý tưởng:

~~~text
SELECT customers ...
SELECT addresses WHERE id = ?   -- customer 1
SELECT addresses WHERE id = ?   -- customer 2
SELECT addresses WHERE id = ?   -- customer 3
...
~~~

Các cách xử lý:

1. **Flat projection:** chọn trực tiếp address.city bằng JOIN và alias.
2. **DTO constructor expression:** chọn đúng các cột cần thiết trong JPQL.
3. **EntityGraph:** dùng khi cần entity graph đầy đủ trong transaction.
4. **Batch fetching:** nếu cần khởi tạo nhiều proxy/collection, cân nhắc batch fetching theo provider.
5. **Tách query cho ToMany:** phân trang entity gốc trước, sau đó lấy dữ liệu con cho nhóm ID.
6. **DTO response:** tránh để serializer tự khởi tạo association lazy.

Không đổi tất cả mapping sang EAGER để chữa N+1. EAGER có thể làm query khác tải thừa dữ liệu và vẫn phát nhiều SELECT phụ.

## 13. Chọn loại projection theo use case

| Nhu cầu | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Chỉ đọc vài trường của entity gốc | Closed interface projection | Khai báo gọn và có thể tối ưu cột cấp cao nhất |
| Cần một thuộc tính tính từ getter khác | Closed projection với default method | Tránh SpEL không cần thiết |
| Cần một số trường ở quan hệ lồng nhau | Flat interface projection | SELECT và alias rõ ràng |
| Cần DTO bất biến cho API/report | JPQL constructor expression | Kiểm soát trường và kiểu constructor |
| Cần entity cùng quan hệ để xử lý nghiệp vụ | Entity result kết hợp EntityGraph/fetch join | Entity được quản lý trong persistence context |
| Cần dữ liệu con dạng collection lớn | Query riêng theo trang ID hoặc DTO query | Tránh nhân hàng và phân trang sai |
| Cần biểu thức tùy biến phức tạp | Open projection khi hợp lý hoặc DTO/service mapping | Chấp nhận giới hạn tối ưu truy vấn |

Không có một loại projection tốt nhất cho mọi tình huống. Hãy chọn dựa trên số trường cần trả, cấu trúc quan hệ, kích thước collection, yêu cầu phân trang Pageable và cách response được serialize.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Projection chỉ có getCity() nhưng SQL lấy nhiều cột Address | Nested property resolving to join có thể materialize toàn bộ thuộc tính lồng nhau | Dùng flat projection hoặc DTO query |
| Nested getter làm phát SQL | Association được tải lazy khi truy cập | Đọc SQL, tải dữ liệu trong query hoặc dùng DTO |
| Số SELECT tăng theo số customer | N+1 do khởi tạo association riêng | JOIN tường minh, projection phẳng hoặc batch fetching |
| Trang có customer trùng hoặc thiếu | JOIN collection nhân số hàng trước khi phân trang | Phân trang ID gốc rồi tải collection riêng |
| JSON response phát SQL ngoài service | Serializer truy cập nested getter | Trả DTO đã materialize |
| Closed projection mất khả năng tối ưu | Dùng SpEL truy cập target tùy ý | Dùng getter và default method |
| NullPointerException ở address | Quan hệ tùy chọn nhưng code không kiểm tra null | Dùng null check hoặc Optional wrapper |
| EntityGraph vẫn tải nhiều cột | EntityGraph điều khiển fetch association, không phải projection cột | Dùng DTO/flat projection nếu chỉ cần một vài trường |
| Kết quả khác giữa provider | Cơ chế proxy, query và mapping phụ thuộc provider | Test trên đúng provider/version hỗ trợ |

## 15. Checklist trước khi dùng nested projection

- [ ] Xác định rõ caller cần trường nào ở entity gốc và quan hệ lồng nhau.
- [ ] Kiểm tra quan hệ là ToOne hay ToMany.
- [ ] Không giả định nested interface chỉ chọn đúng các getter được khai báo.
- [ ] Kiểm tra SQL để biết nested join materialize những cột nào.
- [ ] Kiểm tra getter có khởi tạo lazy association hay không.
- [ ] Đo số SELECT khi số entity gốc tăng lên.
- [ ] Dùng flat projection hoặc DTO khi cần chọn chính xác cột quan hệ.
- [ ] Không dùng EntityGraph với kỳ vọng chỉ lấy một trường của nested entity.
- [ ] Kiểm tra null association và collection rỗng.
- [ ] Kiểm thử phân trang Pageable với collection projection.
- [ ] Tránh trả entity/proxy hoặc nested projection phức tạp trực tiếp nếu serializer có thể kích hoạt lazy loading.
- [ ] Chạy integration test trên provider và database thực tế.

## 16. Tài liệu tham khảo

- [Spring Data JPA — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html) — closed/open projections, nested projections, interface và class-based projection.
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html) — khai báo query và projection trong repository.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — entity relationship, fetch type và query semantics.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/6.2/userguide/html_single/) — lazy loading, proxy, fetching và batch fetching.

Nested projection hữu ích để tổ chức kết quả theo cấu trúc domain, nhưng interface gọn không bảo đảm SQL gọn. Với JPA, nested property cần JOIN có thể materialize toàn bộ thuộc tính quan hệ; collection còn có thể nhân hàng và làm phân trang khó chính xác. Khi chỉ cần vài trường ở quan hệ lồng nhau, flat projection hoặc DTO query thường cho phép kiểm soát SELECT rõ hơn. Luôn xác nhận bằng SQL log và integration test trên provider thực tế.
