# Vì sao mock repository không xác minh query derivation hoặc mapping?

## 1. Test xanh chỉ chứng minh điều đã thực sự được thực thi

Trong chương **Kiểm thử** của **SPRING_DATA_COMMONS**, cần phân biệt kiểm thử logic dùng repository với kiểm thử chính repository. Spring Data cung cấp các abstraction chung như Repository, CRUD, derived queries, phân trang và projection, nhưng mỗi store có cách tạo truy vấn và mapping riêng.

Một repository mock không chạy toàn bộ cơ chế Spring Data. Nếu test khai báo “khi gọi phương thức này, trả về danh sách kia”, danh sách được trả về từ cấu hình mock, không phải từ truy vấn được suy ra rồi thực thi trên store.

~~~text
Unit test có mock:
Service → Mock repository → Kết quả được test cấu hình sẵn

Kiểm thử repository thật:
Caller → Repository proxy → Tạo truy vấn theo module
       → Thực thi trên store → Mapping kết quả → Domain/projection
~~~

Vì vậy, mock có thể giúp kiểm tra service truyền đúng tham số và xử lý kết quả đúng. Nó không tự chứng minh:

- Tên derived query tham chiếu đúng property của domain.
- Từ khóa truy vấn được module và store hỗ trợ.
- Điều kiện lọc, sắp xếp hoặc phân trang thực sự có hiệu lực.
- Domain được ghi và đọc đúng theo mapping.
- Schema, collection, index hoặc cấu hình converter phù hợp.

Bài học này dùng một ví dụ xuyên suốt để xác định ranh giới bằng chứng của từng loại test.

## 2. Query derivation và mapping nằm ngoài đường đi của mock

### Query derivation

Với một phương thức như:

~~~java
List<Customer> findByActiveTrueAndEmailAddressContaining(String fragment);
~~~

Hạ tầng repository thật cần nhận diện phương thức truy vấn, phân tích cấu trúc tên, phân giải property và tạo truy vấn theo module.

Trong ví dụ JPA ở phần sau, ý định là tìm khách hàng đang hoạt động có địa chỉ email chứa fragment. Tuy nhiên, khả năng hỗ trợ từ khóa, cách xử lý chuỗi và các giới hạn truy vấn phải được đánh giá trong module cụ thể.

Không nên coi tập từ khóa của mọi store là hoàn toàn giống nhau chỉ vì các repository có abstraction chung.

### Mapping

Mapping quyết định cách domain được chuyển sang biểu diễn lưu trữ và ngược lại, chẳng hạn:

- Property emailAddress tương ứng với cột hoặc field nào.
- ID được nhận diện và tạo như thế nào.
- Constructor hoặc cơ chế khởi tạo đối tượng nào được dùng khi đọc.
- Giá trị enum, thời gian hoặc kiểu tùy biến được chuyển đổi ra sao.
- Quan hệ, dữ liệu nhúng và tham chiếu được biểu diễn thế nào.

Mock thường trả lại một đối tượng Java đã được test tạo sẵn. Đối tượng đó không phải đi qua bước ghi, đọc, conversion hoặc materialization thực tế.

### Hai loại metadata khác nhau

Tên derived query thông thường diễn đạt **property domain**, không phải tên cột vật lý. Ví dụ emailAddress có thể được mapping sang email_address trong database.

Tên phương thức đúng không chứng minh mapping cột đúng. Ngược lại, entity ghi đọc được cũng không chứng minh một derived query có nhiều điều kiện đang lọc đúng.

## 3. Mô hình minh họa

Các ví dụ dùng Java 17, JUnit Jupiter, Mockito và một biến thể JPA dùng Jakarta Persistence. Phần mapping này chỉ dành cho ví dụ store quan hệ; không mang annotation JPA áp dụng trực tiếp cho mọi module Spring Data.

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_account")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email_address", nullable = false)
    private String emailAddress;

    @Column(name = "active", nullable = false)
    private boolean active;

    protected Customer() {
    }

    public Customer(String emailAddress, boolean active) {
        this.emailAddress = emailAddress;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getEmailAddress() {
        return emailAddress;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Chiến lược IDENTITY ở đây giả định database và schema thử nghiệm hỗ trợ identity tương ứng. Ứng dụng có cơ chế ID khác cần mapping phù hợp, thay vì sao chép nguyên cấu hình này.

~~~java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository extends CrudRepository<Customer, Long> {

    List<Customer> findByActiveTrueAndEmailAddressContaining(String fragment);
}
~~~

Service chuẩn hóa tham số rồi chuyển kết quả sang danh sách email:

~~~java
import java.util.List;

public class CustomerDirectory {

    private final CustomerRepository customers;

    public CustomerDirectory(CustomerRepository customers) {
        this.customers = customers;
    }

    public List<String> activeEmailsContaining(String fragment) {
        if (fragment == null || fragment.isBlank()) {
            throw new IllegalArgumentException("fragment không được rỗng");
        }

        return customers
                .findByActiveTrueAndEmailAddressContaining(fragment.trim())
                .stream()
                .map(Customer::getEmailAddress)
                .toList();
    }
}
~~~

Service không tự lọc active lần nữa. Nó sử dụng hợp đồng truy vấn của repository. Vì vậy, cần có bằng chứng riêng rằng implementation repository thực hiện đúng hợp đồng đó.

## 4. Unit test có mock kiểm chứng được gì?

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import org.junit.jupiter.api.Test;

class CustomerDirectoryTest {

    @Test
    void trimsFragmentAndReturnsEmailsFromRepository() {
        CustomerRepository repository = mock(CustomerRepository.class);
        CustomerDirectory directory = new CustomerDirectory(repository);

        when(repository.findByActiveTrueAndEmailAddressContaining("@sample.test"))
                .thenReturn(List.of(new Customer("an@sample.test", true)));

        List<String> result =
                directory.activeEmailsContaining("  @sample.test  ");

        assertThat(result).containsExactly("an@sample.test");
        verify(repository)
                .findByActiveTrueAndEmailAddressContaining("@sample.test");
    }
}
~~~

Test này có giá trị đối với logic service:

1. Service loại bỏ khoảng trắng ngoài tham số.
2. Service gọi đúng dependency với tham số đã chuẩn hóa.
3. Service chuyển kết quả domain thành email.

Nhưng Mockito đã được yêu cầu trả về một Customer cụ thể. Test chưa có bước nào đọc dữ liệu trong store hoặc phân tích tên truy vấn.

Ngay cả khi stub trả về một Customer có active bằng false, mock vẫn trả đối tượng đó. Phần True trong tên phương thức không phải điều kiện mà Mockito tự thực thi.

Tương tự, verify chứng minh mock đã nhận một lời gọi. Nó không chứng minh database đã nhận truy vấn đúng hoặc đã có bất kỳ thao tác lưu trữ nào.

### Kiểm thử nhánh lỗi của service

Có thể kiểm tra fragment rỗng làm service ném lỗi và không gọi repository. Đây là kiểm thử một quy tắc đầu vào thực sự của service, không cần database.

Có thể cấu hình mock ném exception để kiểm tra service chuyển lỗi hoặc phản ứng đúng theo hợp đồng. Tuy nhiên, test đó không chứng minh store sẽ thực sự phát sinh exception ấy trong điều kiện cụ thể.

## 5. Phản ví dụ: tên truy vấn sai nhưng mock test vẫn xanh

Giả sử repository có lỗi chính tả:

~~~java
import java.util.List;
import org.springframework.data.repository.Repository;

interface BrokenCustomerRepository extends Repository<Customer, Long> {

    List<Customer> findByActveTrue();
}
~~~

Customer có property active, không có property actve. Tuy nhiên, Java vẫn cho phép khai báo phương thức trên vì tên phương thức là một identifier hợp lệ.

Đoạn test độc lập sau vẫn có thể thành công:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.List;
import org.junit.jupiter.api.Test;

class BrokenCustomerRepositoryMockTest {

    @Test
    void mockDoesNotParseTheDerivedQueryName() {
        BrokenCustomerRepository repository =
                mock(BrokenCustomerRepository.class);

        when(repository.findByActveTrue())
                .thenReturn(List.of(new Customer("an@sample.test", true)));

        assertThat(repository.findByActveTrue()).hasSize(1);
    }
}
~~~

Test chỉ kiểm tra kết quả của stub. Nó không tạo Spring Data repository và không yêu cầu hạ tầng query derivation phân giải actve.

Khi repository thật được cấu hình để suy ra truy vấn từ tên phương thức, quá trình tạo hoặc thực thi truy vấn mới có cơ hội phát hiện property không hợp lệ. Thời điểm lỗi có thể phụ thuộc bootstrap mode, query lookup strategy và module; không nên mặc định mọi lỗi đều xuất hiện ngay khi Spring context bắt đầu.

BrokenCustomerRepository là phản ví dụ riêng. Không đưa nó vào vùng repository scan của cấu hình kiểm thử hợp lệ, trừ khi mục đích là kiểm tra lỗi khởi tạo hoặc lỗi phân giải truy vấn.

### Ranh giới của kiểm tra khi biên dịch

Trình biên dịch có thể phát hiện gọi một phương thức chưa được khai báo hoặc truyền sai kiểu tham số. Nó không kiểm chứng ngữ nghĩa Spring Data của tên một phương thức đã khai báo hợp lệ.

Vì thế, các kết luận sau khác nhau:

~~~text
Code gọi đúng chữ ký Java.
Tên query phân giải đúng property.
Truy vấn được tạo đúng cho store.
Kết quả thực thi đúng với dữ liệu.
~~~

Mock chủ yếu hỗ trợ kiểm tra hợp đồng lời gọi Java và hành vi của thành phần sử dụng hợp đồng đó.

## 6. Phân biệt các lớp bằng chứng kiểm thử

| Cách kiểm thử | Bằng chứng chính | Giới hạn |
| --- | --- | --- |
| Service với repository mock | Quy tắc service, tham số, xử lý kết quả và lỗi giả lập | Không chạy query derivation hoặc mapping của store |
| Unit test cho converter thuần Java | Thuật toán chuyển đổi của converter | Không chứng minh converter đã được đăng ký vào mapping thực tế |
| Tạo repository/context thật | Một phần cấu hình và metadata có thể được xác thực | Chưa chắc mọi truy vấn đã được thực thi |
| Repository thật với store | Truy vấn và mapping chạy trên dữ liệu cụ thể | Chỉ bao phủ môi trường, cấu hình và ca dữ liệu được thử |
| Kiểm thử với engine gần production | Tăng bằng chứng về dialect, kiểu dữ liệu và tính năng engine | Vẫn cần kiểm soát schema, cấu hình và các điều kiện vận hành |

Không cần bỏ unit test để chuyển tất cả thành integration test. Cần chọn test phù hợp với phát biểu mà bạn muốn chứng minh.

Ví dụ:

- “Service từ chối fragment rỗng” có thể được chứng minh bằng unit test.
- “Khách hàng inactive không xuất hiện trong kết quả” cần thực thi truy vấn thật trên fixture có khách hàng inactive.
- “emailAddress nằm đúng ở cột email_address” cần kiểm tra mapping với schema hoặc dữ liệu lưu trữ tương ứng.

## 7. Thiết kế fixture làm lộ truy vấn sai

Nếu fixture chỉ có một khách hàng active khớp email, một truy vấn quên điều kiện active cũng có thể trả kết quả giống kỳ vọng.

Fixture tốt cần có dữ liệu gây nhiễu theo từng điều kiện:

| Email | Active | Với fragment @sample.test |
| --- | --- | --- |
| an@sample.test | true | Phải được trả về |
| binh@sample.test | false | Phải bị loại bởi điều kiện active |
| chi@other.test | true | Phải bị loại bởi điều kiện email |
| dung@other.test | false | Không khớp cả hai điều kiện |

Dữ liệu được chọn giúp phân biệt ít nhất ba lỗi:

- Bỏ điều kiện active.
- Bỏ điều kiện email.
- Dùng logic OR thay cho AND.

Nên xác nhận chính xác tập kết quả hoặc các giá trị có ý nghĩa. Chỉ kiểm tra “kết quả không rỗng” sẽ bỏ qua nhiều trường hợp truy vấn sai.

Nếu truy vấn không khai báo sắp xếp, không khẳng định một thứ tự kết quả mặc định. Với nhiều phần tử, dùng assertion không phụ thuộc thứ tự trừ khi chính thứ tự là hợp đồng cần kiểm tra.

## 8. Kiểm thử với repository JPA thật

Một test slice JPA như **@DataJpaTest** có thể cung cấp môi trường tập trung vào persistence. Cần dùng import và cấu hình tương ứng với phiên bản Spring Boot của dự án.

Ví dụ dưới đây giả định repository và entity được scan đúng, database thử nghiệm có schema phù hợp, JUnit và AssertJ đã được cấu hình. Repository được inject là bean thật, không bị thay bằng mock.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManager;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

// Import DataJpaTest từ gói tương ứng với phiên bản Spring Boot của dự án.
@DataJpaTest
class CustomerRepositoryIntegrationTest {

    @Autowired
    CustomerRepository customers;

    @Autowired
    EntityManager entityManager;

    @Test
    void selectsOnlyActiveCustomersWithMatchingEmail() {
        customers.save(new Customer("an@sample.test", true));
        customers.save(new Customer("binh@sample.test", false));
        customers.save(new Customer("chi@other.test", true));
        customers.save(new Customer("dung@other.test", false));

        entityManager.flush();
        entityManager.clear();

        List<Customer> result =
                customers.findByActiveTrueAndEmailAddressContaining("@sample.test");

        assertThat(result)
                .extracting(Customer::getEmailAddress)
                .containsExactly("an@sample.test");

        assertThat(result)
                .allMatch(Customer::isActive);
    }

    @Test
    void returnsEmptyWhenNoEmailMatches() {
        customers.save(new Customer("an@sample.test", true));

        entityManager.flush();
        entityManager.clear();

        List<Customer> result =
                customers.findByActiveTrueAndEmailAddressContaining("@missing.test");

        assertThat(result).isEmpty();
    }
}
~~~

Trong test đầu, query thực sự được gọi trên repository thật và fixture có dữ liệu đối chứng cho cả hai điều kiện.

Assertion active có thể hỗ trợ chẩn đoán, còn assertion email xác định chính xác đối tượng mong muốn. Chỉ kiểm tra active mà không kiểm tra email vẫn có thể bỏ qua lỗi lọc fragment.

### Vì sao flush rồi clear?

Trong ví dụ JPA:

- Flush đồng bộ các thay đổi đang chờ trong persistence context xuống database theo cơ chế provider.
- Clear loại entity đang được quản lý khỏi persistence context để lần đọc sau không chỉ dựa vào đối tượng đang giữ trong bộ nhớ.

Điều này giúp tăng bằng chứng rằng dữ liệu có thể được đọc lại qua mapping. Flush không đồng nghĩa transaction đã commit.

Nếu provider sử dụng cache cấp khác và mục tiêu là kiểm chứng đường đọc vật lý, còn cần kiểm soát cấu hình cache phù hợp. Không coi clear là thao tác vô hiệu hóa mọi loại cache.

Với store khác, phải dùng cơ chế tương ứng; document repository hoặc reactive repository không mặc định có EntityManager, flush và clear.

## 9. Kiểm chứng mapping bằng đường ghi và đọc thực tế

Một kiểm tra round trip đơn giản:

~~~java
@Test
void readsPersistedCustomerFields() {
    Customer saved =
            customers.save(new Customer("mapped@sample.test", true));

    entityManager.flush();
    Long id = saved.getId();
    assertThat(id).isNotNull();

    entityManager.clear();

    Customer reloaded = customers.findById(id).orElseThrow();

    assertThat(reloaded.getEmailAddress()).isEqualTo("mapped@sample.test");
    assertThat(reloaded.isActive()).isTrue();
}
~~~

Đoạn này là phương thức bổ sung trong lớp integration test đã có dependency ở phần trước.

Nên lấy ID từ kết quả save vì API lưu không yêu cầu mọi implementation phải cập nhật đối tượng đầu vào theo cùng cách. Không dự đoán ID tự sinh hoặc giả định nó luôn là 1.

### Round trip chưa đủ cho mọi yêu cầu mapping

Nếu dùng chính annotation sai để tự sinh schema rồi ghi và đọc bằng cùng mapping sai đó, round trip vẫn có thể thành công.

Ví dụ, ứng dụng đáng ra phải dùng cột email_address theo migration, nhưng mapping lại trỏ đến một tên khác. Schema tự sinh theo mapping có thể che mất sự không tương thích với database triển khai.

Để kiểm chứng yêu cầu vật lý, có thể bổ sung:

- Tạo schema từ migration thực tế và kiểm tra mapping với schema đó.
- Ghi dữ liệu rồi đọc biểu diễn vật lý bằng SQL hoặc API native phù hợp.
- Chèn fixture bằng tên cột hoặc field đã thỏa thuận rồi đọc qua repository.
- Kiểm tra converter và kiểu dữ liệu đặc thù với giá trị có ý nghĩa.

Trong ví dụ JPA, sau khi save và flush có thể đọc cột đã được quy định:

~~~java
Object storedEmail = entityManager
        .createNativeQuery(
                "select email_address from customer_account where id = ?1")
        .setParameter(1, id)
        .getSingleResult();

assertThat(storedEmail).isEqualTo("mapped@sample.test");
~~~

Đoạn bổ sung này kiểm tra tên bảng và cột cụ thể của ví dụ. Nó không phải mã truy vấn dùng chung cho mọi store.

Các kiểu dữ liệu như thời gian, số thập phân hoặc enum cần fixture kiểm tra đúng yêu cầu về độ chính xác và biểu diễn. Việc new một đối tượng có giá trị đúng trong mock không kiểm tra được quá trình chuyển đổi đó.

## 10. Chọn môi trường store phù hợp

Một integration test trên database thay thế chứng minh hành vi trong môi trường đã chạy. Nó không tự chứng minh mọi hành vi giống production.

| Thành phần môi trường | Khác biệt có thể ảnh hưởng kết quả |
| --- | --- |
| Database engine và dialect | Hàm, toán tử, cú pháp, kiểu dữ liệu |
| Collation và cấu hình chuỗi | Phân biệt hoa thường, so sánh, sắp xếp |
| Schema và migration | Tên cột, constraint, index, default value |
| Transaction và isolation | Thời điểm thấy dữ liệu, khóa, cạnh tranh |
| Extension hoặc kiểu đặc thù | JSON, array, địa lý hoặc kiểu chuyên biệt |
| Mapping và converter | Đăng ký converter, naming strategy, serialization |

Database nhúng hữu ích cho nhiều test nhanh, nhưng cần đánh giá mức tương đồng với môi trường đích. Khi query hoặc mapping phụ thuộc engine, có thể dùng database thử nghiệm cùng loại, chẳng hạn một instance được quản lý bằng container.

Container chỉ là cách cung cấp môi trường. Nó không tự bảo đảm đúng phiên bản engine, migration, extension hoặc cấu hình production.

Một test slice cũng có thể cấu hình hoặc thay thế datasource theo cơ chế của phiên bản và dự án. Cần kiểm tra datasource thực sự được dùng khi mục tiêu là chạy với database cụ thể.

### Với document và các store khác

Nguyên tắc bằng chứng không thay đổi:

- Repository phải là implementation thật của module cần kiểm tra.
- Truy vấn phải được gọi thật.
- Dữ liệu phải đi qua mapping và conversion thực tế.
- Kết quả phải được đối chiếu với fixture có khả năng phân biệt lỗi.

Có thể dùng test slice phù hợp của module nếu môi trường hỗ trợ. Tuy nhiên, không giả định slice nào cũng tự cung cấp store, transaction rollback hoặc khả năng isolation giống JPA.

Nếu kiểm tra reactive repository, phải subscribe pipeline và chờ kết thúc bằng công cụ kiểm thử phù hợp. Chỉ tạo publisher rồi kết thúc test chưa chứng minh truy vấn đã được thực thi.

## 11. Các tính năng Commons cũng cần bằng chứng thực thi

| Tính năng | Mock có thể che mất điều gì? | Cách kiểm chứng có ý nghĩa |
| --- | --- | --- |
| Derived query | Sai property, toán tử hoặc cách nối điều kiện | Gọi query thật với fixture phân biệt từng điều kiện |
| Sort | Stub đã được sắp sẵn dù store không sắp đúng | Dùng nhiều giá trị khác nhau và khai báo sort tường minh |
| Pageable | Stub tự dựng Page với metadata tùy ý | Kiểm tra nội dung trang và metadata phù hợp trên dữ liệu thật |
| Slice | Stub tự đặt hasNext | Dùng số lượng dữ liệu vượt ranh giới kích thước slice |
| Projection | Đối tượng giả không đi qua tạo projection | Gọi repository thật, đọc các accessor cần dùng |
| Query by Example | Mock bỏ qua matcher và conversion | Thực thi Example với dữ liệu đối chứng theo matcher được hỗ trợ |
| Auditing | Test tự gán người tạo hoặc thời điểm | Kích hoạt cấu hình auditing và kiểm tra giá trị thực sự được ghi |
| Repository fragment | Mock bỏ qua toàn bộ implementation tùy biến | Kiểm tra fragment thật cùng các thành phần nó phụ thuộc |

Với paging, không nên kết luận implementation luôn chạy một count query chỉ vì kiểu trả về là Page. Nếu số truy vấn là yêu cầu hiệu năng, cần phép đo hoặc quan sát riêng.

Với sorting và paging, nên có khóa phân định ổn định khi nhiều bản ghi cùng giá trị sort. Nếu không, kết quả tại ranh giới trang có thể thay đổi mà assertion vốn dựa vào thứ tự ngẫu nhiên không phản ánh đúng hợp đồng.

## 12. Những cách test dễ tạo cảm giác an toàn sai

### Tự tạo dữ liệu trả về giống kỳ vọng

Khi stub trả danh sách đã lọc đúng rồi test chỉ kiểm tra danh sách đó, không có query nào được xác minh. Test vẫn có thể hữu ích cho phần xử lý phía service, nhưng phải đặt tên và kết luận đúng phạm vi.

### Dùng spy nhưng phương thức vẫn bị stub

Nếu phương thức cần kiểm tra bị thay bằng kết quả cấu hình sẵn, đường tạo và thực thi query vẫn có thể bị bỏ qua. Từ khóa spy không tự làm test trở thành integration test.

### Chạy Spring context nhưng thay repository bằng mock

Việc context khởi động không thay đổi bản chất lời gọi đến repository đã bị thay thế. Cần kiểm tra dependency thực tế được inject vào thành phần kiểm thử.

### Dùng fake repository tự lọc trong bộ nhớ

Fake hữu ích để kiểm tra service với một hợp đồng đơn giản. Tuy nhiên, thuật toán của fake không phải parser, query translator hoặc mapping implementation của store.

Nếu fake và code thật hiểu null, chuỗi, quan hệ hoặc sorting khác nhau, test của fake có thể xanh trong khi repository thật sai.

### Chỉ kiểm tra context khởi động

Khởi động thành công có thể phát hiện một số lỗi cấu hình và metadata. Nó không thay thế việc gọi từng truy vấn có ý nghĩa và đối chiếu kết quả. Một số lỗi chỉ xuất hiện khi tạo query muộn, bind tham số hoặc đọc dữ liệu.

### Xóa dữ liệu không phù hợp với môi trường test

Test repository cần isolation. Rollback mặc định của một test JPA không phải hợp đồng chung cho mọi module hoặc mọi luồng async.

Tùy store, có thể cần database riêng, collection riêng, namespace riêng hoặc cơ chế dọn fixture được kiểm soát. Không để test phụ thuộc thứ tự chạy hoặc dữ liệu còn lại từ lần trước.

## 13. Tổ chức bộ test theo câu hỏi cần trả lời

Một cách phân chia thực tế:

| Câu hỏi | Loại kiểm thử ưu tiên |
| --- | --- |
| Service từ chối đầu vào sai? | Unit test không cần store |
| Service truyền đúng fragment và xử lý kết quả? | Unit test với repository mock |
| Derived query lọc đúng? | Repository thật với fixture có đối chứng |
| Domain ghi và đọc đúng? | Mapping round trip trên store |
| Mapping phù hợp schema triển khai? | Migration thực tế và kiểm tra representation cần thiết |
| Truy vấn dùng đặc tính engine hoạt động đúng? | Integration test trên engine tương ứng |
| Use case commit hoặc rollback đúng? | Kiểm thử ranh giới transaction của service |

Phân chia theo câu hỏi giúp test nhanh tập trung vào logic Java và test persistence tập trung vào đường đi không thể được mock chứng minh.

Nếu một test thất bại, nên xác định lỗi thuộc nhóm nào: service, phân giải query, binding, thực thi store, mapping kết quả hay môi trường. Không sửa stub để che một lỗi của implementation thật.

## 14. Bài tập áp dụng

Với CustomerRepository trong bài:

1. Viết unit test kiểm tra fragment rỗng bị từ chối trước khi gọi repository.
2. Giải thích vì sao stub trả Customer inactive không làm Mockito tự loại đối tượng đó.
3. Thực thi derived query thật trên fixture có cả active/inactive và email khớp/không khớp.
4. Thêm trường hợp không có kết quả.
5. Đọc lại dữ liệu sau khi loại ảnh hưởng của persistence context theo cơ chế JPA.
6. Kiểm tra mapping emailAddress với schema và cột email_address đã thỏa thuận.
7. Đổi một property trong tên query thành tên không tồn tại và chỉ ra lớp kiểm thử nào phát hiện lỗi.
8. Nếu đổi sang store khác, xác định phần nào của ý định kiểm thử giữ nguyên và phần hạ tầng nào phải thay đổi.

Kết quả cần nêu rõ mỗi test chứng minh điều gì. Mock repository phù hợp để cô lập logic phía sử dụng repository; query derivation và mapping cần được kiểm chứng trên đường thực thi thật của Spring Data và store tương ứng.
