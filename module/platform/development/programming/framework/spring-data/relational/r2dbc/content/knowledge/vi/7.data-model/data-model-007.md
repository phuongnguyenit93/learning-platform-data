# Thực thể khả biến, bất biến và Java record

Spring Data R2DBC có thể ánh xạ nhiều kiểu entity Java khác nhau. Entity có thể là **mutable** (khả biến, có thể thay đổi trạng thái sau khi tạo), **immutable** (bất biến sau khi tạo) hoặc **Java record** (một dạng lớp dữ liệu có các component final và constructor được sinh tự động).

Spring Data không bắt buộc entity phải có constructor không tham số và setter cho mọi thuộc tính. Khi đọc dữ liệu, framework sử dụng metadata để chọn constructor và dựng đối tượng; sau đó, nếu cần, nó điền các thuộc tính còn thiếu. Khi ghi dữ liệu, Spring Data trả về entity tương ứng với trạng thái đã lưu. Điều này đặc biệt quan trọng với entity immutable vì ID hoặc version mới có thể được đặt trên một instance mới thay vì thay đổi instance ban đầu.

## 1. Entity trong Spring Data R2DBC

Entity là kiểu Java đại diện cho dữ liệu được lưu trong cơ sở dữ liệu quan hệ. Mapping của entity thường được mô tả bằng annotation thuộc Spring Data Relational:

- @Table chỉ định bảng.
- @Id đánh dấu thuộc tính định danh.
- @Column chỉ định tên cột.
- @Version đánh dấu thuộc tính version cho optimistic locking.
- @Transient loại thuộc tính khỏi persistent mapping.
- @Embedded và @MappedCollection mô tả một số cấu trúc value object hoặc collection thuộc aggregate.

Ví dụ đơn giản:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {
    @Id
    private Long id;

    @Column("full_name")
    private String fullName;
}
~~~

Annotation chỉ mô tả mapping. Spring Data R2DBC còn cần biết cách tạo một instance Customer khi đọc Row và cách truy cập hoặc cập nhật các property khi lưu.

Một entity thường được thiết kế quanh aggregate root. Những đối tượng thuộc cùng aggregate có thể được lưu theo quy tắc relational mapping của Spring Data. Dù chọn mutable hay immutable, mô hình aggregate và quy tắc bảng/cột vẫn cần rõ ràng.

## 2. Entity mutable: đối tượng có thể thay đổi trạng thái

Entity mutable cho phép thay đổi thuộc tính sau khi khởi tạo, thường thông qua setter hoặc phương thức nghiệp vụ. Đây là kiểu mô hình quen thuộc với JavaBean.

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    @Version
    private Long version;

    protected Customer() {
        // Dành cho cơ chế tạo entity của framework.
    }

    public Customer(String fullName) {
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public Long getVersion() {
        return version;
    }

    public void setVersion(Long version) {
        this.version = version;
    }
}
~~~

Khi đọc một hàng dữ liệu, Spring Data có thể tạo instance rồi điền giá trị vào các property thông qua cơ chế truy cập phù hợp. Nếu entity có constructor không tham số và setter, framework thường có thể sử dụng mô hình này.

### 2.1. Ưu điểm của entity mutable

- Dễ làm quen với lập trình JavaBean.
- Có thể tạo đối tượng trước rồi điền dữ liệu theo từng bước.
- Dễ tích hợp với một số thư viện hoặc framework yêu cầu setter.
- Có thể thay đổi trạng thái của entity trong một quy trình nghiệp vụ nhiều bước.
- Có thể thuận tiện khi cần cập nhật từng thuộc tính trong bộ nhớ.

### 2.2. Hạn chế cần lưu ý

- Đối tượng có thể rơi vào trạng thái chưa hoàn chỉnh giữa các lần gọi setter.
- Nhiều nơi có thể thay đổi cùng một instance, làm khó xác định nơi phát sinh thay đổi.
- Setter công khai có thể cho phép sửa thuộc tính mà nghiệp vụ muốn giữ cố định.
- Việc chia sẻ một entity mutable giữa nhiều luồng hoặc nhiều nhánh reactive có thể tạo ra lỗi do truy cập đồng thời.

R2DBC sử dụng mô hình reactive nhưng điều đó không làm đối tượng Java tự động an toàn khi nhiều luồng cùng sửa. Không nên hiểu non-blocking I/O là bảo đảm thread-safety cho entity.

Nếu chọn mutable entity, nên giới hạn setter ở phạm vi cần thiết, giữ các thay đổi trong service/aggregate có kiểm soát và tránh chia sẻ instance đang bị sửa giữa nhiều thao tác đồng thời.

## 3. Entity immutable: trạng thái được xác định khi tạo

Entity immutable không cho phép thay đổi trạng thái sau khi được tạo. Các thuộc tính thường là final, không có setter công khai; thay đổi nghiệp vụ được biểu diễn bằng cách tạo một instance mới.

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public final class Customer {

    @Id
    private final Long id;

    private final String fullName;

    @Version
    private final Long version;

    @PersistenceCreator
    public Customer(Long id, String fullName, Long version) {
        this.id = id;
        this.fullName = fullName;
        this.version = version;
    }

    public static Customer newCustomer(String fullName) {
        return new Customer(null, fullName, null);
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public Long getVersion() {
        return version;
    }

    public Customer withId(Long id) {
        return new Customer(id, this.fullName, this.version);
    }

    public Customer withVersion(Long version) {
        return new Customer(this.id, this.fullName, version);
    }

    public Customer rename(String newFullName) {
        return new Customer(this.id, newFullName, this.version);
    }
}
~~~

Trong ví dụ, các thuộc tính là final và không có setter. Phương thức rename tạo một Customer mới với tên mới. Các phương thức withId và withVersion cũng tạo instance mới khi framework cần áp dụng giá trị định danh hoặc version.

Spring Data có thể sử dụng constructor được chọn để tạo entity. Nếu có nhiều constructor, @PersistenceCreator giúp chỉ rõ constructor dùng cho persistence. Với một constructor duy nhất phù hợp, framework thường có thể tự chọn constructor đó.

### 3.1. Ưu điểm của entity immutable

- Trạng thái không bị thay đổi âm thầm sau khi đối tượng được tạo.
- Dễ suy luận khi đọc code vì một instance có dữ liệu cố định.
- Giảm nguy cơ một nơi thay đổi thuộc tính trong khi nơi khác đang sử dụng cùng instance.
- Phù hợp với value object và mô hình domain ưu tiên bất biến.
- Thuận tiện cho kiểm thử vì dữ liệu đầu vào và đầu ra có thể được so sánh rõ ràng.

### 3.2. Đổi lại, việc cập nhật tạo ra instance mới

Với mutable entity, một setter có thể thay đổi trực tiếp đối tượng. Với immutable entity, phương thức cập nhật phải tạo đối tượng mới:

~~~java
Customer renamed = customer.rename("Tran An");
~~~

Cách làm này có thể tạo thêm instance, nhưng thường giúp luồng thay đổi trạng thái minh bạch hơn. Trong hầu hết ứng dụng nghiệp vụ, chi phí tạo một object nhỏ không phải lý do đủ mạnh để bỏ qua lợi ích của tính bất biến; tuy nhiên, cần đo đạc nếu có khối lượng object rất lớn hoặc cấu trúc dữ liệu nặng.

## 4. Java record: dạng entity bất biến gọn hơn

Java record là dạng khai báo lớp dữ liệu. Compiler tự sinh canonical constructor, accessor cho từng component, equals, hashCode và toString. Các component được khai báo là final và record không cung cấp setter.

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    @Column("full_name") String fullName,
    @Version Long version
) {}
~~~

Record này có thể được Spring Data R2DBC sử dụng như một entity. Spring Data dùng constructor của record để tạo đối tượng khi đọc dữ liệu. Không cần viết getter, setter hoặc constructor chỉ để gán ba component.

Khi tạo mới:

~~~java
Customer customer = new Customer(null, "Nguyen An", null);
~~~

Các giá trị null ở đây biểu thị ID và version chưa được gán trong ví dụ. Quy tắc khởi tạo version và cách phát sinh ID còn phụ thuộc cấu hình, kiểu ID và database.

### 4.1. Record không đồng nghĩa với mọi dữ liệu đều bất biến sâu

Record ngăn thay đổi tham chiếu component sau khi tạo, nhưng không tự làm bất biến các object được tham chiếu.

Ví dụ:

~~~java
import java.util.List;

public record OrderDraft(List<String> items) {}
~~~

Nếu caller giữ tham chiếu tới List và sửa nó, nội dung mà OrderDraft nhìn thấy cũng thay đổi. Muốn bảo vệ dữ liệu collection, cần sao chép hoặc dùng collection bất biến:

~~~java
import java.util.List;

public record OrderDraft(List<String> items) {

    public OrderDraft {
        items = List.copyOf(items);
    }
}
~~~

Đây là tính bất biến sâu ở mức collection được sao chép; các phần tử bên trong vẫn cần được xem xét riêng nếu bản thân chúng mutable.

### 4.2. Khi record phù hợp

Record phù hợp khi:

- Entity có cấu trúc dữ liệu tương đối ổn định.
- Các thuộc tính được xác định đầy đủ tại thời điểm tạo.
- Không cần setter để thay đổi trạng thái.
- Constructor binding phản ánh tự nhiên mô hình dữ liệu.
- Dự án dùng phiên bản Java hỗ trợ record (Java 16 trở lên cho record được chuẩn hóa).

Record không phù hợp khi domain object cần một quy trình xây dựng nhiều bước phức tạp, cần kế thừa từ một lớp cơ sở, hoặc phải tương thích với một thư viện chỉ làm việc qua constructor không tham số và setter. Khi đó, immutable class hoặc mutable JavaBean có thể phù hợp hơn.

## 5. Spring Data tạo entity như thế nào?

Khi truy vấn trả về một Row, Spring Data R2DBC phải chuyển dữ liệu thành một instance entity. Quá trình này gồm hai phần chính:

1. **Object creation**: chọn constructor và tạo instance từ các giá trị tương ứng với constructor parameters.
2. **Property population**: điền những property persistent chưa được cung cấp trong constructor, thông qua cơ chế truy cập property mà Spring Data hỗ trợ.

~~~mermaid
flowchart TB
    A["Row và metadata"]
    B["RelationalMappingContext"]
    C["Chọn persistence constructor"]
    D["Đọc và chuyển đổi tham số"]
    E["Tạo entity instance"]
    F["Điền property còn thiếu"]
    G["Entity hoàn chỉnh"]

    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
~~~

### 5.1. Chọn constructor

Các quy tắc thường gặp:

- Nếu entity có một constructor phù hợp, Spring Data có thể dùng constructor đó.
- Nếu có nhiều constructor, constructor được đánh dấu @PersistenceCreator được ưu tiên theo quy tắc mapping.
- Với record, canonical constructor là constructor tự nhiên để dựng record.
- Constructor parameters cần tương ứng với property persistent và có thể được xác định tên/kiểu để ánh xạ dữ liệu.

Ví dụ immutable class có nhiều constructor:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.relational.core.mapping.Table;

@Table("product")
public class Product {

    @Id
    private final Long id;

    private final String name;

    private final String sku;

    public Product(String name, String sku) {
        this(null, name, sku);
    }

    @PersistenceCreator
    public Product(Long id, String name, String sku) {
        this.id = id;
        this.name = name;
        this.sku = sku;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getSku() {
        return sku;
    }
}
~~~

Constructor có @PersistenceCreator cho Spring Data biết cách tạo entity từ dữ liệu persistence. Constructor đơn giản hơn vẫn có thể được dùng trong mã nghiệp vụ để tạo sản phẩm mới.

Với class thông thường, cần bảo đảm metadata tên tham số constructor có thể được khám phá và khớp với property. Cấu hình biên dịch giữ lại tên tham số (chẳng hạn Java compiler option -parameters trong các môi trường cần nó) giúp mapping xác định đúng tham số. Không nên đổi tên tham số constructor một cách tùy tiện nếu chúng đang được dùng để ánh xạ property.

### 5.2. Property population sau constructor

Sau khi constructor chạy, Spring Data có thể cần điền các property chưa được constructor thiết lập. Với mutable entity, framework có thể dùng setter hoặc property access phù hợp.

Với immutable entity, có hai cơ chế đáng chú ý:

- **Wither**: phương thức tạo một instance mới với một property được thay đổi, thường theo quy ước tên withProperty.
- **Persistence constructor**: nếu không có wither phù hợp, Spring Data có thể tạo lại instance qua constructor với giá trị property mới.

Ví dụ wither:

~~~java
public Customer withId(Long newId) {
    return new Customer(newId, this.fullName, this.version);
}
~~~

Wither không sửa đối tượng hiện tại. Nó trả về một Customer khác. Điều này cho phép framework bổ sung giá trị sinh ra từ database mà vẫn giữ entity bất biến.

Nếu constructor đã nhận đủ mọi property persistent cần thiết, framework có thể không cần bước property population bổ sung.

### 5.3. Tên property và tên cột là hai khái niệm khác nhau

Tên tham số constructor thường gắn với property Java, còn SQL column có thể được đổi tên bằng @Column hoặc NamingStrategy.

Ví dụ:

~~~java
@Table("customer")
public record Customer(
    @Id Long id,
    @Column("full_name") String fullName
) {}
~~~

Property Java là fullName; tên cột trong database là full_name. Constructor component vẫn là fullName. Không đổi tên component thành full_name chỉ vì database dùng tên cột snake_case.

## 6. ID được sinh ra và entity immutable

Một trường hợp quan trọng là database tự sinh ID khi insert.

Với entity mới, ứng dụng thường tạo đối tượng chưa có ID:

~~~java
Customer customer = new Customer(null, "Nguyen An", null);
~~~

Sau khi insert, database có thể trả về ID. Spring Data cần tạo hoặc cập nhật trạng thái entity được trả về để chứa ID đó.

Với immutable class hoặc record, instance ban đầu không thể bị thay đổi. Vì vậy, cần sử dụng **entity được phát ra từ kết quả save**:

~~~java
Mono<Customer> savedCustomer =
    customerRepository.save(
        new Customer(null, "Nguyen An", null)
    );

return savedCustomer.flatMap(saved ->
    customerRepository.findById(saved.id())
);
~~~

Đừng bỏ qua giá trị trả về của save rồi tiếp tục dùng instance ban đầu với giả định rằng ID đã được ghi vào object. Đối với entity immutable, instance ban đầu vẫn giữ trạng thái ban đầu; instance trả về mới phản ánh dữ liệu sau khi lưu.

Đây cũng là lý do nên trả publisher từ repository qua service/controller thay vì gọi subscribe tùy tiện ở tầng nghiệp vụ.

### 6.1. Mutable entity cũng nên dùng giá trị trả về

Một số cơ chế mapping có thể điền ID vào entity mutable, nhưng cách an toàn và rõ ràng nhất vẫn là dùng entity được phát ra từ save. API repository trả về entity đã lưu để caller có thể tiếp tục xử lý với trạng thái mà Spring Data trả lại.

### 6.2. ID do ứng dụng cấp

Nếu ID được tạo trước bởi ứng dụng, entity có thể mang ID ngay khi tạo:

~~~java
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record CustomerWithUuid(
    @Id UUID id,
    String fullName,
    @Version Long version
) {}

CustomerWithUuid customer =
    new CustomerWithUuid(UUID.randomUUID(), "Nguyen An", null);
~~~

Kiểu ID và cách xác định entity mới cần nhất quán với mapping và cấu hình của Spring Data. Với ID không null, repository thường cần xác định thao tác là update hay entity đã tồn tại theo quy tắc new-state detection. Nếu dự án dùng ID do ứng dụng cấp, cần hiểu cơ chế xác định entity mới, có thể cần Persistable hoặc chiến lược phù hợp thay vì giả định rằng mọi ID đã có nghĩa là bản ghi chắc chắn đã tồn tại.

## 7. Version và optimistic locking với entity immutable

Spring Data Relational hỗ trợ optimistic locking thông qua @Version. Version cho phép phát hiện một bản ghi đã bị thay đổi bởi transaction khác kể từ khi entity được đọc.

Ví dụ:

~~~java
@Table("customer")
public record Customer(
    @Id Long id,
    String fullName,
    @Version Long version
) {}
~~~

Khi cập nhật, Spring Data sử dụng version hiện tại trong điều kiện update và cập nhật version mới theo cơ chế của framework. Nếu không có hàng nào được cập nhật vì version không còn khớp, thao tác có thể phát sinh OptimisticLockingFailureException.

Với record, version mới cũng là một phần của instance kết quả. Vì vậy, sau save/update, hãy tiếp tục sử dụng entity được trả về:

~~~java
Mono<Customer> updated =
    customerRepository.findById(customerId)
        .map(customer ->
            new Customer(
                customer.id(),
                "Tran An",
                customer.version()
            )
        )
        .flatMap(customerRepository::save);
~~~

Ví dụ trên minh họa việc tạo một record mới trước khi lưu. Trong ứng dụng thực tế, nên đặt thao tác thay đổi domain trong một phương thức rõ nghĩa, và xử lý trường hợp bản ghi không tồn tại hoặc optimistic locking thất bại.

Không tự tăng version trong service nếu Spring Data đang quản lý @Version. Hãy để cơ chế persistence kiểm soát việc so sánh và cập nhật version.

## 8. So sánh mutable class, immutable class và record

| Tiêu chí | Mutable class | Immutable class | Java record |
|---|---|---|---|
| Trạng thái sau khi tạo | Có thể thay đổi | Không thay đổi; tạo instance mới | Component không thể gán lại |
| Thuộc tính | Thường có field và setter | Thường là final, không setter | Component final |
| Constructor | Có thể dùng no-arg hoặc constructor nghiệp vụ | Constructor nhận dữ liệu cần thiết | Canonical constructor do compiler sinh |
| Spring Data object creation | Tạo instance rồi điền property hoặc dùng constructor | Constructor binding; có thể dùng wither/copy qua constructor | Canonical constructor |
| Cập nhật thuộc tính | Setter hoặc phương thức nghiệp vụ | Tạo instance mới | Tạo record mới |
| ID/version sinh sau insert | Có thể được phản ánh vào instance mutable hoặc instance trả về | Instance trả về chứa giá trị mới | Record trả về chứa giá trị mới |
| Boilerplate | Nhiều getter/setter | Có thể nhiều constructor và wither | Ít |
| Phù hợp khi | Cần thay đổi trạng thái theo từng bước | Domain ưu tiên bất biến, cần kiểm soát tạo object | Kiểu dữ liệu gọn, constructor binding tự nhiên |

Không có lựa chọn nào luôn đúng cho mọi domain. Hãy chọn theo cách ứng dụng quản lý trạng thái, yêu cầu tích hợp và độ phức tạp của entity.

## 9. Kết hợp entity với Repository và service

Repository reactive có thể làm việc với cả mutable class, immutable class và record nếu mapping được cấu hình đúng.

Ví dụ repository:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByFullName(String fullName);
}
~~~

Một service có thể tạo entity mới, lưu và sử dụng kết quả trả về:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> register(String fullName) {
        Customer customer = new Customer(null, fullName, null);
        return repository.save(customer);
    }
}
~~~

Trong ví dụ trên, kiểu Customer có thể là record đã khai báo ở phần trước. Service không cần thay đổi cách gọi repository chỉ vì entity là record. Điểm khác biệt nằm ở cách framework tạo và cập nhật instance trong quá trình mapping.

Nếu cần dùng ID vừa sinh, hãy lấy ID từ entity được phát ra:

~~~java
public Mono<Long> registerAndGetId(String fullName) {
    return repository.save(new Customer(null, fullName, null))
        .map(Customer::id);
}
~~~

Không gọi block() trong service reactive chỉ để lấy kết quả đồng bộ. Hãy để publisher được kết hợp với luồng xử lý phía trên.

## 10. Chọn kiểu entity cho từng tình huống

### Dùng mutable entity khi

- Domain hoặc framework tích hợp yêu cầu setter.
- Entity có quy trình khởi tạo từng bước thực sự cần thiết.
- Ứng dụng đang dùng mô hình JavaBean và muốn giữ tính tương thích.
- Có quy tắc kiểm soát rõ nơi được phép sửa trạng thái.

### Dùng immutable class khi

- Muốn kiểm soát constructor và quy tắc khởi tạo.
- Entity có nhiều logic nghiệp vụ hơn một data carrier.
- Cần wither hoặc factory method có tên rõ nghĩa.
- Muốn bất biến nhưng vẫn cần kế thừa hoặc các cấu trúc class thông thường.

### Dùng record khi

- Entity có cấu trúc dữ liệu rõ ràng và tương đối ổn định.
- Constructor binding phù hợp với cách tạo entity.
- Không cần setter hoặc kế thừa lớp.
- Muốn giảm boilerplate cho getter, equals, hashCode và toString.
- Dự án sử dụng Java có hỗ trợ record.

Với cả ba kiểu, cần kiểm tra mapping cho property đặc biệt, constructor parameter, ID/version và collection. Record không tự sửa được schema không khớp, và mutable class cũng không giúp giải quyết vấn đề driver hoặc conversion.

## 11. Những lỗi thường gặp

### 11.1. Không tìm được constructor phù hợp

Nguyên nhân có thể là nhiều constructor nhưng không có constructor được đánh dấu, tên tham số không khớp property hoặc constructor không thể truy cập theo cơ chế mapping.

Cách xử lý:

- Đánh dấu constructor persistence bằng @PersistenceCreator khi có nhiều constructor.
- Bảo đảm tham số constructor khớp property persistent.
- Kiểm tra việc giữ lại tên tham số trong quá trình biên dịch.
- Với record, dùng component rõ nghĩa và không đổi tên tùy tiện.

### 11.2. Record hoặc immutable entity không nhận ID sau insert

Nguyên nhân thường là code tiếp tục dùng instance ban đầu thay vì entity được phát ra từ save.

Cách xử lý: giữ và sử dụng publisher kết quả từ repository/template. Lấy ID từ instance đã lưu.

### 11.3. Dùng setter cho field final

Field final không thể được cập nhật như property mutable thông thường. Nếu entity immutable cần nhận giá trị được tạo trong quá trình persistence, hãy cung cấp constructor phù hợp hoặc wither theo quy ước.

### 11.4. Constructor có tham số nhưng tên không khớp

Ví dụ property là fullName nhưng tham số constructor lại là name, Spring Data có thể không xác định được dữ liệu cần truyền nếu không có cơ chế mapping tương ứng.

Cách xử lý: giữ tên tham số phù hợp property hoặc cấu trúc constructor rõ ràng, đồng thời kiểm tra metadata constructor.

### 11.5. Dùng record với collection mutable

Record không làm cho List, Map hoặc object lồng bên trong trở nên immutable. Nếu cần bảo vệ trạng thái, hãy sao chép collection ở constructor và dùng phần tử bất biến khi phù hợp.

### 11.6. Mong đợi entity tự động an toàn khi chạy reactive

Reactive chỉ mô tả cách xử lý tín hiệu và I/O. Nó không ngăn hai nhánh xử lý cùng sửa một object mutable. Hãy tránh chia sẻ entity mutable đang thay đổi giữa các subscriber hoặc request đồng thời.

## 12. Nguyên tắc thiết kế thực tế

- Chọn một mô hình tạo entity rõ ràng: JavaBean mutable, immutable constructor binding hoặc record.
- Dùng @PersistenceCreator khi entity có nhiều constructor và cần chỉ định constructor persistence.
- Bảo đảm constructor parameter có thể ánh xạ chính xác với property.
- Dùng @Table, @Column, @Id và @Version để mô tả mapping; đừng nhầm tên property Java với tên cột SQL.
- Với immutable entity, dùng wither hoặc persistence constructor để tạo instance mới khi cần cập nhật property.
- Với record, nhớ rằng component bất biến nông; tự bảo vệ collection và object mutable bên trong.
- Luôn sử dụng entity được phát ra từ save, nhất là khi database sinh ID hoặc Spring Data cập nhật version.
- Không tự tăng @Version nếu Spring Data đang quản lý optimistic locking.
- Tránh chia sẻ mutable entity giữa các luồng xử lý đồng thời.
- Giữ luồng reactive xuyên suốt service và controller, không block tùy tiện để lấy entity.

## 13. Ghi nhớ luồng mapping

Khi đọc dữ liệu, Spring Data R2DBC dùng metadata entity để chọn constructor, chuyển đổi các giá trị từ Row và tạo instance. Với mutable entity, framework có thể điền các property còn thiếu bằng setter hoặc property access. Với immutable class, framework có thể dùng wither hoặc tạo instance mới qua persistence constructor. Với record, canonical constructor là cơ chế tạo object tự nhiên.

Khi ghi dữ liệu, repository hoặc template thực hiện thao tác và phát ra entity kết quả. Nếu ID hoặc version được sinh/cập nhật trong quá trình persistence, instance kết quả mới là nguồn trạng thái cần dùng tiếp. Hiểu rõ khác biệt này giúp lựa chọn kiểu entity phù hợp và tránh lỗi khi làm việc với Spring Data R2DBC.

