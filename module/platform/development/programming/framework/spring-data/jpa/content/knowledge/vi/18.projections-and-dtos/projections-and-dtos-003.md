# Interface projection mở với biểu thức và đánh đổi tối ưu

Spring Data JPA cho phép repository trả về interface projection để ứng dụng chỉ đọc những thuộc tính cần thiết của entity. Với interface projection, Spring tạo một proxy triển khai interface và cung cấp giá trị cho các getter từ dữ liệu truy vấn.

Có hai kiểu interface projection quan trọng:

- **Closed projection**: interface chỉ khai báo các getter tương ứng với thuộc tính của aggregate/entity. Spring biết chính xác những thuộc tính cần thiết và có thể tối ưu truy vấn để chỉ lấy phần dữ liệu đó.
- **Open projection**: interface có biểu thức **@Value** dùng Spring Expression Language (SpEL), thường truy cập object nguồn thông qua biến **target**. Vì biểu thức có thể đọc bất kỳ thuộc tính nào của object nguồn, Spring không thể xác định chắc chắn tập cột tối thiểu cần lấy và không áp dụng được cùng mức tối ưu truy vấn như closed projection.

Open projection linh hoạt để tạo giá trị trình bày, nhưng có đánh đổi về khả năng tối ưu, độ phức tạp và khả năng phát sinh tải association. Bài này giải thích cách dùng **target**, **args**, bean trong SpEL, phương thức mặc định của interface, nested projection và cách chọn giữa projection với DTO.

**Điều kiện của ví dụ:** các đoạn mã dùng Spring Boot 3.x, Java 17 trở lên và Spring Data JPA. Ứng dụng cần **spring-boot-starter-data-jpa**, JDBC driver, DataSource và schema phù hợp. Các đoạn mã là những phần của ứng dụng Spring Boot, không phải chương trình độc lập có thể chạy chỉ bằng **javac**.

## 1. Projection là gì?

Entity thường mô tả trạng thái persistent đầy đủ của một đối tượng. Nhưng một use case đọc có thể chỉ cần một phần dữ liệu. Ví dụ màn hình danh sách người dùng chỉ cần tên hiển thị và email, không cần mọi thuộc tính của entity.

Projection là một kiểu kết quả đại diện cho phần dữ liệu cần đọc:

~~~text
Person entity
+ id
+ firstname
+ lastname
+ email
+ phone
+ address
+ createdAt
+ ...
       |
       | repository query
       v
PersonName projection
+ firstname
+ lastname
~~~

Repository có thể khai báo:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    List<PersonName> findByLastname(String lastname);
}
~~~

Interface projection:

~~~java
public interface PersonName {
    String getFirstname();
    String getLastname();
}
~~~

Khi gọi repository, Spring Data tạo projection proxy cho mỗi kết quả. Code sử dụng interface mà không cần tự viết lớp triển khai.

Projection thường phù hợp cho read model: danh sách, trang chi tiết rút gọn, báo cáo nhỏ hoặc dữ liệu phục vụ một API. Nếu cần cập nhật entity, hãy tải entity phù hợp trong transaction và áp dụng quy tắc nghiệp vụ lên entity đó.

## 2. Closed interface projection

Một projection được xem là closed khi các accessor tương ứng trực tiếp với thuộc tính của aggregate root/entity và không dùng biểu thức mở để tính giá trị từ object nguồn.

Ví dụ entity:

~~~java
@Entity
@Table(name = "people")
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String firstname;

    @Column(nullable = false)
    private String lastname;

    @Column(nullable = false)
    private String email;

    private String phone;

    protected Person() {
    }

    public Person(String firstname, String lastname, String email) {
        this.firstname = firstname;
        this.lastname = lastname;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getFirstname() {
        return firstname;
    }

    public String getLastname() {
        return lastname;
    }

    public String getEmail() {
        return email;
    }

    public String getPhone() {
        return phone;
    }
}
~~~

Projection chỉ cần tên và email:

~~~java
public interface PersonContact {

    String getFirstname();

    String getLastname();

    String getEmail();
}
~~~

Repository:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    List<PersonContact> findByLastname(String lastname);
}
~~~

Spring Data biết projection chỉ cần các thuộc tính **firstname**, **lastname** và **email**. Với closed projection, Spring Data có thể tối ưu query execution bằng cách giới hạn dữ liệu cần lấy thay vì tải toàn bộ entity, tùy loại query, store module và khả năng của provider.

Điều này có thể giảm lượng dữ liệu truyền từ database, chi phí materialize entity và dữ liệu không cần thiết. Tuy nhiên, đây là khả năng tối ưu của framework, không phải bảo đảm rằng mọi truy vấn sẽ luôn phát ra đúng ba cột trong mọi tình huống. Hãy kiểm tra SQL thực tế.

## 3. Open interface projection và @Value

Open projection cho phép tính giá trị bằng SpEL thông qua **@Value**. Biểu thức có thể truy cập object nguồn bằng biến **target**.

Ví dụ tạo tên đầy đủ:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface PersonDisplay {

    @Value("#{target.firstname + ' ' + target.lastname}")
    String getFullName();

    String getEmail();
}
~~~

Trong biểu thức:

- **target** là object nguồn đang được dùng để tạo projection.
- **target.firstname** truy cập thuộc tính firstname của object nguồn.
- **target.lastname** truy cập thuộc tính lastname.
- Kết quả của biểu thức được trả về qua getter **getFullName()**.

Repository:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    List<PersonDisplay> findByLastname(String lastname);
}
~~~

Code sử dụng:

~~~java
List<PersonDisplay> people = repository.findByLastname("Nguyen");

for (PersonDisplay person : people) {
    System.out.println(person.getFullName());
    System.out.println(person.getEmail());
}
~~~

Vì **getFullName()** dùng SpEL trên object nguồn, đây là open projection. Spring không thể biết trước biểu thức có thể truy cập những thuộc tính nào của target. Do đó, framework không thể áp dụng tối ưu chọn cột giống closed projection một cách an toàn.

Open projection hữu ích khi biểu thức trình bày ngắn gọn và thực sự cần đọc object nguồn. Nếu chỉ ghép các getter đã có, phương thức mặc định của interface thường là lựa chọn nhẹ hơn.

## 4. Biến args trong SpEL

SpEL của open projection có thể truy cập các tham số được truyền vào phương thức projection thông qua biến **args**.

Ví dụ:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface PersonGreeting {

    @Value("#{args[0] + ' ' + target.firstname + '!'}")
    String getGreeting(String prefix);
}
~~~

Sử dụng:

~~~java
PersonGreeting person = repository.findGreetingById(id);

String greeting = person.getGreeting("Xin chào");
~~~

Nếu firstname là **An**, kết quả có thể là:

~~~text
Xin chào An!
~~~

**args[0]** là tham số đầu tiên truyền vào getter **getGreeting**. Nếu phương thức có nhiều tham số, có thể truy cập **args[1]**, **args[2]** và các vị trí tương ứng.

Không dùng args như một cách truyền dữ liệu tùy ý vào query database. Đây là tham số của phương thức projection, được dùng trong biểu thức tính giá trị trả về. Nếu cần lọc dữ liệu, hãy truyền tham số vào repository query method.

## 5. Gọi Spring bean từ biểu thức SpEL

Open projection cũng có thể gọi bean Spring bằng tên bean. Cách này hữu ích khi logic định dạng cần tái sử dụng hoặc có nhiều quy tắc hơn một biểu thức ngắn.

Bean định dạng:

~~~java
@Component("personNameFormatter")
public class PersonNameFormatter {

    public String format(Person person) {
        return person.getLastname() + ", " + person.getFirstname();
    }
}
~~~

Projection:

~~~java
public interface PersonLabel {

    @Value("#{@personNameFormatter.format(target)}")
    String getLabel();

    String getEmail();
}
~~~

Biểu thức **@personNameFormatter** tham chiếu bean có tên tương ứng trong Spring ApplicationContext. **target** được truyền vào phương thức format.

Cách này giúp tái sử dụng formatter, nhưng projection vẫn là open projection. Biểu thức có thể truy cập object nguồn nên Spring không thể suy ra chính xác tập thuộc tính cần lấy để tối ưu như closed projection.

Giữ formatter tập trung vào trình bày dữ liệu. Không đặt truy vấn database, gọi dịch vụ bên ngoài hoặc quy tắc nghiệp vụ phức tạp trong SpEL; những logic đó nên nằm ở service hoặc một thành phần chuyên trách.

## 6. Dùng default method thay cho SpEL khi có thể

Nếu giá trị tính toán chỉ dựa trên các getter đã khai báo trong projection, có thể dùng default method của Java interface.

~~~java
public interface PersonName {

    String getFirstname();

    String getLastname();

    default String getFullName() {
        return getFirstname() + " " + getLastname();
    }
}
~~~

Đây vẫn là closed projection vì các thuộc tính cần lấy được xác định rõ bởi hai getter firstname và lastname. Phương thức **getFullName()** chỉ kết hợp kết quả từ các accessor đó; nó không cần truy cập object nguồn tùy ý.

So sánh:

| Cách | Ví dụ | Đặc điểm |
|---|---|---|
| Closed projection | Getter **getFirstname()**, **getLastname()** | Spring biết các thuộc tính cần thiết |
| Default method | Ghép hai getter trong interface | Giữ projection đóng nếu chỉ dùng accessor đã khai báo |
| Open projection | **@Value("#{target.firstname + ...}")** | Có thể truy cập target nên hạn chế tối ưu chọn thuộc tính |
| Bean trong SpEL | **@Value("#{@formatter.format(target)}")** | Tái sử dụng bean nhưng vẫn là open projection |

Nếu chỉ cần ghép chuỗi, tính nhãn đơn giản hoặc tạo giá trị dẫn xuất từ vài getter, ưu tiên default method. Dùng SpEL khi cần truy cập object nguồn hoặc gọi bean một cách có chủ đích.

## 7. Nested interface projection

Projection có thể lồng một projection khác để biểu diễn thuộc tính quan hệ.

Giả sử Person có quan hệ tới Address:

~~~java
@Entity
public class Address {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String city;

    private String country;

    protected Address() {
    }

    public String getCity() {
        return city;
    }

    public String getCountry() {
        return country;
    }
}
~~~

Trong Person:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "address_id")
private Address address;
~~~

Projection lồng:

~~~java
public interface AddressSummary {

    String getCity();

    String getCountry();
}
~~~

~~~java
public interface PersonWithAddress {

    String getFirstname();

    String getLastname();

    AddressSummary getAddress();
}
~~~

Repository:

~~~java
List<PersonWithAddress> findByLastname(String lastname);
~~~

Khi gọi **getAddress()**, Spring Data tạo projection cho thuộc tính Address theo khả năng hỗ trợ của nested projection.

Tuy nhiên, cần hiểu một đánh đổi: thuộc tính lồng được giải quyết thông qua join có thể khiến toàn bộ thuộc tính quan hệ được materialize. Không nên mặc định rằng nested projection luôn tạo SQL chỉ chọn đúng hai cột city và country. Hành vi cụ thể phụ thuộc cách query được tạo, mapping và provider.

Nếu truy vấn cần kiểm soát chính xác cột của cả hai bảng, hãy cân nhắc JPQL DTO constructor expression hoặc một query projection tường minh. Kiểm tra SQL để biết association đang được join/tải như thế nào.

## 8. Open projection ảnh hưởng tối ưu truy vấn ra sao?

Closed projection cho framework biết tập thuộc tính cần thiết. Open projection không cung cấp bảo đảm đó vì SpEL có thể truy cập bất kỳ thuộc tính nào của target.

Ví dụ closed:

~~~java
public interface PersonSummary {
    String getFirstname();
    String getLastname();
}
~~~

Ví dụ open:

~~~java
public interface PersonSummaryOpen {

    @Value("#{target.firstname + ' ' + target.lastname + ' (' + target.email + ')'}")
    String getLabel();
}
~~~

Với closed projection, Spring có thể giới hạn dữ liệu cần lấy cho firstname và lastname. Với open projection, biểu thức còn đọc email và về nguyên tắc có thể đọc bất kỳ thuộc tính nào khác. Vì vậy, Spring không thể áp dụng cùng tối ưu chọn cột.

Các hệ quả có thể gặp:

- Nhiều cột được lấy hơn nhu cầu hiển thị thực tế.
- Entity hoặc object nguồn có thể được materialize.
- SpEL truy cập association LAZY có thể kích hoạt truy vấn bổ sung.
- Một biểu thức đơn giản có thể che giấu chi phí truy cập dữ liệu.
- Việc thay đổi biểu thức có thể làm thay đổi dữ liệu cần tải mà không thể hiện rõ trong chữ ký getter.

Open projection không mặc nhiên chậm trong mọi trường hợp. Nếu số dòng nhỏ, biểu thức đơn giản và SQL phù hợp, chi phí có thể chấp nhận được. Nhưng với truy vấn danh sách lớn hoặc API có yêu cầu hiệu năng chặt, hãy đo đạc và ưu tiên projection đóng hoặc DTO có select rõ ràng.

## 9. Tránh N+1 khi biểu thức truy cập association

Một biểu thức SpEL có thể truy cập quan hệ:

~~~java
public interface PersonLocation {

    @Value("#{target.firstname + ' - ' + target.address.city}")
    String getLocationLabel();
}
~~~

Nếu **address** là LAZY và danh sách có nhiều Person với các Address khác nhau, việc đánh giá biểu thức có thể kích hoạt truy vấn bổ sung khi từng getter được gọi. Đây là một đường dẫn có thể dẫn đến N+1.

Cách xử lý phụ thuộc use case:

- Dùng closed projection nếu chỉ cần các thuộc tính đơn giản đã biết.
- Dùng JPQL query với join và DTO projection để chọn rõ các cột cần thiết.
- Dùng **@EntityGraph** khi cần entity cùng một association cụ thể.
- Nếu dùng open projection, kiểm tra SQL và số truy vấn với tập dữ liệu có kích thước thực tế.

Ví dụ DTO projection với JPQL:

~~~java
public record PersonLocationView(
    String firstname,
    String city
) {
}
~~~

~~~java
@Query("""
    select new com.example.people.PersonLocationView(
        p.firstname,
        a.city
    )
    from Person p
    left join p.address a
    where p.lastname = :lastname
    """)
List<PersonLocationView> findLocations(
    @Param("lastname") String lastname
);
~~~

DTO constructor expression làm rõ dữ liệu cần lấy và phép join. Nó thường là lựa chọn dễ kiểm soát khi cần kết quả từ nhiều entity.

## 10. Interface projection với @Query và alias

Với JPQL tùy chỉnh, có thể trả về interface projection. Các alias trong SELECT nên khớp với tên thuộc tính mà projection getter yêu cầu.

Projection:

~~~java
public interface PersonContact {

    String getFirstname();

    String getEmail();
}
~~~

Repository:

~~~java
@Query("""
    select p.firstname as firstname,
           p.email as email
    from Person p
    where p.lastname = :lastname
    """)
List<PersonContact> findContactsByLastname(
    @Param("lastname") String lastname
);
~~~

Alias **firstname** được ánh xạ tới **getFirstname()**, còn alias **email** tới **getEmail()**. Nếu alias sai hoặc không khớp, giá trị projection có thể không được ánh xạ như mong muốn.

Với JPQL constructor expression cho DTO, thứ tự và kiểu tham số constructor phải khớp biểu thức SELECT. Với interface projection, hãy đặt alias tường minh để tránh phụ thuộc vào tên suy luận khó đọc.

## 11. Dynamic projections

Spring Data JPA hỗ trợ dynamic projection: cùng một repository method có thể trả về projection type khác nhau tùy class được truyền vào lúc gọi.

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    <T> List<T> findByLastname(String lastname, Class<T> type);
}
~~~

Có thể gọi:

~~~java
List<PersonName> names =
    repository.findByLastname("Nguyen", PersonName.class);

List<PersonContact> contacts =
    repository.findByLastname("Nguyen", PersonContact.class);

List<Person> entities =
    repository.findByLastname("Nguyen", Person.class);
~~~

Dynamic projection giúp tái sử dụng điều kiện truy vấn trong khi chọn hình dạng kết quả theo use case.

Lưu ý chữ ký **Class<T>** phải phù hợp với kiểu trả về generic để Spring nhận diện đây là tham số projection. Nếu tham số là **Class<?>** hoặc không khớp kiểu generic, nó có thể được xem như một tham số query thông thường tùy chữ ký method.

Dynamic projection không loại bỏ đánh đổi giữa open và closed. Nếu truyền một open projection, các giới hạn tối ưu của open projection vẫn áp dụng.

## 12. So sánh interface projection với DTO projection

| Tiêu chí | Interface projection | DTO/class-based projection |
|---|---|---|
| Khai báo | Interface getter | Class hoặc record |
| Cơ chế | Projection proxy | Khởi tạo object DTO |
| Giá trị tính toán | Default method hoặc SpEL | Constructor, factory hoặc mapping ở service |
| Open projection | Có thể dùng SpEL và target | Không có open interface projection theo cơ chế này |
| Tối ưu truy vấn | Closed projection có thể giới hạn thuộc tính | Query/constructor expression thể hiện rõ field cần lấy |
| Nested data | Có nested interface projection | DTO lồng hoặc constructor mapping |
| Phù hợp | Read view nhỏ, linh hoạt, ít boilerplate | API/report cần cấu trúc rõ, immutable hoặc join nhiều nguồn |

Ví dụ DTO record:

~~~java
public record PersonContactDto(
    String firstname,
    String email
) {
}
~~~

Repository:

~~~java
@Query("""
    select new com.example.people.PersonContactDto(
        p.firstname,
        p.email
    )
    from Person p
    where p.lastname = :lastname
    """)
List<PersonContactDto> findContactDtos(
    @Param("lastname") String lastname
);
~~~

DTO thường phù hợp khi cần hợp đồng kết quả ổn định, constructor rõ ràng và kiểm soát dữ liệu lấy ra. Interface projection phù hợp khi muốn định nghĩa read view nhanh bằng các getter.

## 13. Những giới hạn và lưu ý khi dùng open projection

Trước khi chọn open projection, hãy xem xét các điểm sau:

1. **Không tối ưu cột như closed projection:** SpEL có thể truy cập mọi thuộc tính target.
2. **Có thể phát sinh tải LAZY:** truy cập association trong biểu thức có thể kích hoạt truy vấn bổ sung.
3. **Logic khó nhìn từ chữ ký:** getter có thể thực hiện phép tính hoặc gọi bean, nên người đọc phải xem biểu thức để hiểu dữ liệu phụ thuộc.
4. **Khó kiểm thử hiệu năng nếu chỉ kiểm tra kết quả:** cần đo số SQL và số hàng được tải.
5. **Không phù hợp cho logic nghiệp vụ lớn:** biểu thức dài, nhiều nhánh hoặc gọi dịch vụ bên ngoài nên chuyển sang service/formatter chuyên trách.
6. **Không dùng làm entity cập nhật:** projection là read view; hãy tải entity managed nếu cần thay đổi và lưu dữ liệu.

Open projection là công cụ trình bày dữ liệu. Giữ biểu thức ngắn và dễ đọc; nếu nó bắt đầu điều phối nhiều quy tắc hoặc truy cập nhiều association, hãy chuyển sang DTO/service.

## 14. Kiểm thử projection và SQL

Một bài test có thể xác nhận projection trả đúng dữ liệu:

~~~java
@DataJpaTest
class PersonProjectionTest {

    @Autowired
    private PersonRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void returnsClosedProjection() {
        entityManager.persist(
            new Person("An", "Nguyen", "an@example.test")
        );
        entityManager.flush();
        entityManager.clear();

        List<PersonContact> result =
            repository.findByLastname("Nguyen");

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getFirstname()).isEqualTo("An");
        assertThat(result.get(0).getEmail()).isEqualTo("an@example.test");
    }
}
~~~

Có thể viết test tương tự cho open projection:

~~~java
@Test
void computesOpenProjectionValue() {
    PersonDisplay result =
        repository.findDisplayById(personId).orElseThrow();

    assertThat(result.getFullName()).isEqualTo("An Nguyen");
}
~~~

Để xác nhận tối ưu, bật SQL logging trong môi trường test:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
~~~

So sánh SQL của closed và open projection trên cùng dữ liệu. Kiểm tra số cột được chọn, số truy vấn khi gọi getter, association có được tải thêm không và hành vi khi dữ liệu tăng. Kết quả phụ thuộc query shape, Spring Data version, Hibernate và database; không chỉ dựa vào tên projection để kết luận hiệu năng.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Projection getter trả null | Tên getter không khớp property hoặc alias | Kiểm tra tên property và alias SELECT |
| Open projection tải nhiều cột | SpEL truy cập target nên framework không biết tập field tối thiểu | Dùng closed projection hoặc DTO |
| Gọi getter làm phát sinh nhiều SQL | SpEL truy cập association LAZY | Dùng join/DTO hoặc fetch plan phù hợp |
| Default method không được tính đúng | Phụ thuộc getter sai hoặc tên property không khớp | Kiểm tra accessor và test projection |
| Bean SpEL không tìm thấy | Tên bean hoặc cấu hình component sai | Kiểm tra bean name và ApplicationContext |
| Nested projection tải dữ liệu lớn | Nested property được materialize qua join | Kiểm tra SQL và dùng DTO khi cần chọn cột tường minh |
| Dynamic projection không được nhận diện | Chữ ký Class generic không khớp kiểu trả về | Dùng **<T> List<T> ... Class<T>** |
| Dùng projection để cập nhật entity | Nhầm read view với entity managed | Tải entity trong transaction và cập nhật entity |
| Query interface projection không ánh xạ đúng | Alias không khớp getter | Đặt alias trùng tên property projection |

## 16. Checklist lựa chọn projection

- [ ] Xác định use case chỉ đọc hay cần cập nhật entity.
- [ ] Dùng closed projection khi các getter ánh xạ trực tiếp tới thuộc tính cần thiết.
- [ ] Dùng default method khi chỉ cần kết hợp các getter đã khai báo.
- [ ] Dùng open projection khi thật sự cần SpEL truy cập target, args hoặc bean.
- [ ] Giữ biểu thức SpEL ngắn và không chứa logic nghiệp vụ phức tạp.
- [ ] Tránh truy cập association LAZY trong open projection nếu chưa kiểm tra số SQL.
- [ ] Dùng nested projection có chủ đích và kiểm tra hành vi join.
- [ ] Đặt alias tường minh khi dùng interface projection với **@Query**.
- [ ] Dùng dynamic projection khi nhiều use case cần hình dạng kết quả khác nhau.
- [ ] Dùng DTO/record khi cần kiểm soát cột, join và cấu trúc kết quả rõ ràng.
- [ ] Kiểm thử kết quả và SQL trên database/provider thực tế.

## 17. Kết luận

Closed interface projection chỉ khai báo các thuộc tính cần đọc, giúp Spring Data biết tập dữ liệu cần thiết và có thể tối ưu query. Open interface projection dùng **@Value** với SpEL, cho phép truy cập **target**, tham số **args** hoặc bean Spring để tính giá trị, nhưng vì biểu thức có thể đọc bất kỳ thuộc tính nào nên không có cùng khả năng tối ưu chọn cột.

Nếu chỉ cần ghép getter, dùng default method để giữ projection đóng. Nếu cần biểu thức linh hoạt, dùng open projection nhưng giữ logic ngắn và đo SQL. Khi cần kết quả từ nhiều association hoặc muốn kiểm soát chính xác dữ liệu trả về, DTO/record projection thường rõ ràng và dễ tối ưu hơn.