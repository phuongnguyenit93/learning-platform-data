# Yêu cầu về constructor, lớp Entity và khả năng tạo proxy

## 1. Vì sao Entity có những quy tắc riêng?

Một entity là object Java được JPA quản lý và ánh xạ với dữ liệu trong database. Khi đọc dữ liệu, JPA provider phải tạo instance, nạp trạng thái từ các cột và theo dõi thay đổi trong persistence context. Khi ứng dụng dùng lazy loading, provider còn có thể thay thế hoặc bao bọc entity bằng một đối tượng trung gian để trì hoãn việc đọc dữ liệu liên quan.

Vì vậy, class dùng làm entity có một số yêu cầu khác DTO hoặc class nghiệp vụ thông thường. Constructor không tham số cho phép provider tạo object trước khi nạp dữ liệu. Class và các phương thức cần được thiết kế sao cho provider có thể truy cập trạng thái, ghi đè phương thức hoặc tạo proxy khi cần.

Trong Spring Data JPA, repository không trực tiếp quyết định cách khởi tạo entity. Spring Data JPA gọi JPA API; Hibernate hoặc JPA provider đang sử dụng chịu trách nhiệm tạo instance, quản lý persistence context và thực hiện proxying hoặc bytecode enhancement.

Bài này tập trung vào ba yêu cầu liên quan chặt chẽ:
- Constructor không tham số và cách JPA tạo entity.
- Cấu trúc, modifier và cách truy cập thuộc tính của lớp entity.
- Khả năng tạo proxy để hỗ trợ lazy loading.

## 2. Các yêu cầu cơ bản đối với Entity class

Theo hợp đồng portable của Jakarta Persistence, entity class cần tuân thủ các quy tắc chính:

1. Là top-level class hoặc static nested class. Non-static inner class cần instance của lớp bao ngoài nên không phù hợp để provider tự tạo độc lập.
2. Có constructor không tham số với mức truy cập public hoặc protected.
3. Class không được khai báo final.
4. Các phương thức và persistent instance variables không được khai báo final.
5. Được đánh dấu bằng @Entity và tuân thủ các quy tắc ánh xạ của JPA.
6. Có thể là abstract class nếu mô hình kế thừa cần điều đó; provider sẽ tạo instance của concrete entity phù hợp.

Ví dụ entity hợp lệ:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    protected Customer() {
        // Constructor dành cho JPA.
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void rename(String newName) {
        this.name = newName;
    }
}
```

Constructor protected đáp ứng yêu cầu của JPA. Ứng dụng vẫn có constructor có tham số để tạo entity mới theo nghiệp vụ. Không cần mở constructor JPA thành public chỉ để repository sử dụng.

Các field có thể là private. JPA không yêu cầu mọi thuộc tính phải có public getter/setter. Mức truy cập thực tế phụ thuộc chiến lược field access hoặc property access được chọn.

### 2.1. Top-level class và static nested class

Entity thường được khai báo thành top-level class:

```java
@Entity
public class Order {
    protected Order() {
    }
}
```

Nếu cần khai báo entity lồng bên trong một lớp khác, nested class phải là static:

```java
public class PersistenceModel {

    @Entity
    public static class Customer {
        protected Customer() {
        }
    }
}
```

Một non-static inner class giữ tham chiếu ngầm tới instance của lớp bao ngoài. Constructor của nó về bản chất cần instance đó, trong khi JPA phải có thể tạo entity mà không cần biết một instance bao ngoài cụ thể. Vì vậy không dùng non-static inner class làm entity.

Trong dự án thông thường, top-level class dễ đọc, dễ tìm và ít gây nhầm lẫn hơn.

### 2.2. Entity có thể abstract, nhưng không được final

Một abstract entity có thể làm phần gốc của hierarchy:

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {

    @Id
    @GeneratedValue
    private Long id;

    protected Payment() {
    }
}
```

Các entity con concrete kế thừa từ nó và được JPA ánh xạ theo chiến lược inheritance đã chọn. Abstract ngăn tạo trực tiếp instance của lớp gốc; nó không đồng nghĩa với final.

Ngược lại, final class ngăn Hibernate tạo subclass proxy theo cơ chế kế thừa thông thường. Nó cũng vi phạm yêu cầu portable của entity class. Không khai báo entity là final nếu muốn ứng dụng hoạt động theo hợp đồng JPA và hỗ trợ lazy proxy thông thường.

## 3. Constructor không tham số

### 3.1. Tại sao JPA cần constructor này?

Khi truy vấn database, provider cần tạo một object entity. Với field access, quá trình khái quát là:

1. Tạo instance thông qua constructor không tham số.
2. Nạp giá trị các cột vào persistent fields.
3. Thiết lập trạng thái quan hệ và thông tin quản lý nội bộ.
4. Đưa entity vào persistence context để theo dõi.

JPA không yêu cầu provider gọi constructor có tham số của ứng dụng để dựng lại object. Provider cần một cách tạo instance ổn định mà không phải biết constructor nghiệp vụ nào phù hợp với từng hàng dữ liệu.

Constructor không tham số vì vậy là một phần của hợp đồng persistence, không phải constructor chính để ứng dụng sử dụng.

### 3.2. Vì sao nên dùng protected?

Mức truy cập protected vừa đáp ứng JPA, vừa tránh để code bên ngoài tùy ý tạo một entity rỗng:

```java
@Entity
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    protected Product() {
    }

    public Product(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Product name is required");
        }
        this.name = name;
    }
}
```

Ứng dụng tạo entity mới thông qua constructor có tham số. Provider có thể gọi constructor protected khi hydrate entity. Constructor không tham số cũng có thể là public, nhưng thường không có lợi ích nếu ứng dụng không cần tạo entity rỗng.

Không nên khai báo constructor JPA là private nếu muốn tuân thủ hợp đồng portable, vì đặc tả yêu cầu public hoặc protected.

### 3.3. Có constructor có tham số vẫn phải có constructor không tham số

Java chỉ tự sinh default constructor khi class không khai báo constructor nào. Khi đã khai báo constructor có tham số, compiler không tự tạo constructor rỗng nữa.

Ví dụ không hợp lệ:

```java
@Entity
public class Product {

    @Id
    private Long id;

    private String name;

    public Product(String name) {
        this.name = name;
    }
}
```

Class này chỉ có constructor nhận name. Khi Hibernate cần tạo entity, nó không tìm thấy constructor không tham số phù hợp. Có thể dẫn đến lỗi khởi tạo entity hoặc lỗi truy vấn lúc runtime.

Cách sửa:

```java
@Entity
public class Product {

    @Id
    private Long id;

    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }
}
```

### 3.4. Constructor JPA nên làm ít việc

Constructor không tham số nên đơn giản và không thực hiện nghiệp vụ:

- Không gọi repository hoặc service.
- Không mở transaction hoặc kết nối database.
- Không phát sự kiện nghiệp vụ.
- Không gọi phương thức có thể bị override.
- Không giả định các field đã có giá trị từ database.
- Không kiểm tra invariant dựa trên toàn bộ thuộc tính vì provider chưa hydrate chúng.

Không nên đặt logic gửi email, tạo hóa đơn hoặc ghi audit nghiệp vụ trong constructor entity. Provider có thể gọi constructor khi đọc dữ liệu, tạo proxy hoặc trong các tình huống nội bộ khác. Nếu constructor gây side effect, một lần truy vấn có thể vô tình lặp lại hành động nghiệp vụ.

Nghiệp vụ nên được gọi tường minh từ application service hoặc phương thức domain sau khi entity đã được tạo và có trạng thái cần thiết.

### 3.5. Field initializer và constructor JPA

Field initializer của Java vẫn được thực thi khi object được tạo. Ví dụ:

```java
private boolean active = true;
private List<OrderLine> lines = new ArrayList<>();
```

Khi JPA hydrate entity, provider sẽ nạp trạng thái persistent từ database. Giá trị khởi tạo không nên được xem là giá trị mặc định thay thế cho schema hoặc dữ liệu database.

Khởi tạo collection để tránh null thường hữu ích, nhưng provider có thể thay collection bằng wrapper riêng để quản lý lazy loading và dirty checking. Không nên giữ tham chiếu collection cũ rồi tiếp tục thao tác sau khi provider đã thay thế nó.

Đối với field persistent có default nghiệp vụ, hãy phân biệt:
- Giá trị mặc định khi ứng dụng tạo entity mới.
- Giá trị được lưu trong database.
- Giá trị mà provider nạp lại khi hydrate entity.

Ba điều này có thể khác nhau. Nếu cần default ở database, hãy định nghĩa trong schema hoặc migration; Java initializer không tự tạo default cho những hàng được ghi từ ứng dụng khác.

## 4. Field access và property access

JPA hỗ trợ hai cách truy cập persistent state chính.

### 4.1. Field access

Khi annotation mapping như @Id được đặt trên field, JPA sử dụng field access:

```java
@Entity
public class Account {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String accountName;

    protected Account() {
    }

    public String getAccountName() {
        return accountName;
    }

    public void changeAccountName(String value) {
        this.accountName = value;
    }
}
```

Provider đọc/ghi persistent fields trực tiếp theo cơ chế truy cập được phép của runtime. Field có thể private; không cần public setter cho mọi thuộc tính.

Ưu điểm của field access:
- Giữ encapsulation của API entity.
- Không cần tạo setter công khai chỉ để phục vụ persistence.
- Getter có thể được thiết kế cho domain mà không nhất thiết là điểm truy cập persistence.
- Tránh gọi setter có side effect trong lúc hydrate entity.

Đây là cách phổ biến trong nhiều ứng dụng Hibernate.

### 4.2. Property access

Khi annotation mapping được đặt trên getter, JPA dùng property access:

```java
@Entity
public class Account {

    private Long id;
    private String accountName;

    protected Account() {
    }

    @Id
    @GeneratedValue
    public Long getId() {
        return id;
    }

    public String getAccountName() {
        return accountName;
    }

    public void setAccountName(String accountName) {
        this.accountName = accountName;
    }
}
```

Với property access, provider sử dụng getter để đọc và setter để ghi state. Accessor persistent cần tuân thủ quy tắc truy cập của JPA; setter không nên chứa side effect phức tạp vì provider có thể gọi nó trong quá trình hydrate.

Property access hữu ích khi cần tùy chỉnh cách lấy hoặc gán một giá trị persistent, nhưng cần giữ accessor đơn giản, xác định và không phụ thuộc thứ tự setter.

### 4.3. Không trộn lẫn annotation tùy tiện

Theo mặc định, vị trí annotation @Id xác định access type của hierarchy entity. Nếu @Id nằm trên field, các annotation mapping thường đặt trên field; nếu nằm trên getter, chúng thường đặt trên getter.

Trộn mapping annotations giữa field và getter mà không khai báo rõ ràng có thể khiến provider diễn giải sai hoặc báo lỗi. Khi thật sự cần chọn access type, có thể dùng @Access:

```java
@Entity
@Access(AccessType.FIELD)
public class Account {
    // Persistent mapping đặt trên field.
}
```

Có thể chọn property access ở cấp class hoặc thuộc tính cụ thể theo quy tắc Jakarta Persistence. Chỉ dùng mixed access khi có lý do rõ ràng và đã kiểm thử; một quy ước nhất quán thường dễ bảo trì hơn.

## 5. Vì sao proxy cần entity có thể kế thừa?

### 5.1. Proxy là gì?

Proxy là object trung gian đại diện cho entity hoặc quan hệ entity. Provider có thể trả về proxy thay vì tải toàn bộ trạng thái ngay lập tức. Proxy giữ định danh cần thiết và biết cách yêu cầu provider tải dữ liệu khi ứng dụng truy cập thuộc tính cần thiết.

Với Hibernate, một dạng proxy phổ biến là subclass được tạo động từ entity class. Proxy override các phương thức có thể override để chặn lời gọi, kiểm tra entity đã được khởi tạo hay chưa, rồi tải trạng thái khi cần.

Ví dụ một quan hệ:

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public Customer getCustomer() {
        return customer;
    }
}
```

Khi tải PurchaseOrder, provider có thể chưa tải đầy đủ Customer. Trường customer có thể giữ một proxy. Khi code truy cập customer.getName(), proxy mới yêu cầu database tải dữ liệu nếu nó chưa được khởi tạo và persistence context còn hoạt động.

### 5.2. Vì sao final class cản trở subclass proxy?

Subclass proxy cần tạo một class con của entity class. Java không cho phép kế thừa một class final. Nếu entity là final, cơ chế proxy dựa trên subclass không thể tạo class con.

Ví dụ không phù hợp:

```java
@Entity
public final class Customer {

    @Id
    private Long id;

    protected Customer() {
    }
}
```

Cách sửa portable là bỏ final:

```java
@Entity
public class Customer {

    @Id
    private Long id;

    protected Customer() {
    }
}
```

Không chỉ class, các phương thức persistent cũng không nên là final. Nếu getter là final, subclass proxy không thể override getter đó để chặn lời gọi và kích hoạt lazy initialization. Tương tự, persistent instance variables không nên khai báo final theo hợp đồng entity portable.

### 5.3. Final method và final field ảnh hưởng ra sao?

Với property access, getter/setter là đường truy cập persistent state. Nếu getter final, proxy không thể override để can thiệp vào quá trình truy cập. Điều này có thể khiến lazy loading không hoạt động như dự kiến hoặc không portable giữa các provider.

Với field access, provider có thể truy cập field trực tiếp theo mapping. Tuy nhiên, đặc tả vẫn yêu cầu persistent instance variables không final. Final field cũng gây khó khăn cho provider khi hydrate và cập nhật state theo cơ chế thông thường.

Quy tắc an toàn:
- Entity class không final.
- Persistent methods không final.
- Persistent instance fields không final.
- Constructor JPA public/protected và không tham số.

Các phương thức helper không liên quan đến persistent state có thể được thiết kế tùy nhu cầu, nhưng không nên biến entity thành final hoặc làm accessor cần proxy không thể override.

## 6. Lazy loading và persistence context

Proxy chỉ là một phần của lazy loading. Để proxy có thể tải dữ liệu, provider cần còn quyền truy cập persistence context và transaction phù hợp.

Một tình huống thường gặp:

1. Service mở transaction.
2. Repository tải một PurchaseOrder.
3. Quan hệ customer được để lazy.
4. Service truy cập order.getCustomer().getName().
5. Hibernate khởi tạo proxy bằng truy vấn bổ sung.
6. Transaction kết thúc; entity và proxy có thể trở thành detached.

Nếu ứng dụng giữ proxy rồi truy cập thuộc tính chưa tải sau khi persistence context đóng, Hibernate có thể ném LazyInitializationException.

Cách thiết kế tốt là xác định dữ liệu cần cho use case và tải nó trong transaction:
- Dùng fetch join khi truy vấn cần quan hệ đó.
- Dùng @EntityGraph khi muốn khai báo fetch plan.
- Dùng DTO projection khi chỉ cần một tập cột cụ thể.
- Chuyển dữ liệu cần thiết thành DTO trước khi trả response ra ngoài transaction.

Không nên bật eager loading cho tất cả quan hệ chỉ để tránh lazy exception. Eager loading có thể kéo theo nhiều dữ liệu không cần thiết và làm tăng số lượng hoặc độ phức tạp truy vấn.

### 6.1. Lazy là yêu cầu gợi ý trong một số quan hệ

Trong JPA, @ManyToOne và @OneToOne mặc định là EAGER; nếu muốn trì hoãn, cần khai báo fetch = FetchType.LAZY. Đặc tả coi LAZY là hint đối với provider, vì vậy cần xác nhận hành vi trên provider và cấu hình đang dùng.

Quan hệ collection như @OneToMany và @ManyToMany mặc định là LAZY. Hibernate thường dùng persistent collection wrapper để theo dõi việc khởi tạo và thay đổi collection.

Ví dụ:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();
```

Khai báo LAZY không có nghĩa dữ liệu chắc chắn không bao giờ được tải; nó trì hoãn cho tới khi use case cần và provider thực thi được việc tải đó.

### 6.2. Proxy và identifier

Provider thường có thể biết identifier của proxy mà không cần tải toàn bộ entity. Vì vậy, gọi getter ID đôi khi không kích hoạt truy vấn; hành vi chi tiết phụ thuộc mapping và provider.

Không nên viết logic nghiệp vụ dựa trên giả định rằng mọi getter đều không kích hoạt SQL. Hãy quan sát SQL thực tế, đặc biệt khi serialize entity hoặc gọi toString(), equals() và hashCode().

## 7. Bytecode enhancement và giới hạn của proxy subclass

Hibernate có thể sử dụng bytecode enhancement để bổ sung hành vi vào class entity, chẳng hạn lazy attribute loading, dirty tracking hoặc khả năng quản lý state mà không chỉ dựa vào subclass proxy.

Điều này có thể mở rộng cách Hibernate xử lý lazy loading và giảm một số hạn chế của proxy truyền thống. Tuy nhiên:
- Bytecode enhancement là cơ chế provider-specific, không thay đổi yêu cầu portable của Jakarta Persistence.
- Cấu hình build/plugin phải thực sự chạy enhancement trên class cần thiết.
- Hành vi phải được kiểm thử với đúng phiên bản Hibernate và cấu hình production.
- Không nên mặc định enhancement làm cho mọi entity final trở thành entity portable hoặc mọi final accessor đều an toàn.

Khi thiết kế entity dùng trong ứng dụng Spring Data JPA thông thường, hãy giữ entity có thể kế thừa và accessor persistent có thể override. Chỉ dựa vào enhancement khi dự án đã cấu hình, kiểm chứng và chủ động chấp nhận phụ thuộc Hibernate.

## 8. Các lỗi thiết kế phổ biến

### 8.1. Chỉ khai báo constructor có tham số

```java
@Entity
public class Customer {

    @Id
    private Long id;

    private String name;

    public Customer(String name) {
        this.name = name;
    }
}
```

Lỗi: không có constructor không tham số. Provider không thể tạo entity theo hợp đồng JPA.

Sửa bằng cách bổ sung constructor protected:

```java
protected Customer() {
}

public Customer(String name) {
    this.name = name;
}
```

### 8.2. Khai báo entity final

```java
@Entity
public final class Customer {
    protected Customer() {
    }
}
```

Lỗi: không đáp ứng yêu cầu portable và cản trở subclass proxy của Hibernate. Sửa bằng cách bỏ final trên entity class.

### 8.3. Đánh dấu getter persistent là final

Nếu getter được dùng cho property access mà khai báo final, proxy subclass không thể override nó. Hãy để persistent accessors không final.

### 8.4. Dùng record làm Entity

Java record là final, có constructor canonical theo các component và không có constructor không tham số theo mô hình entity truyền thống. Record phù hợp làm DTO, request/response object hoặc projection, nhưng không phải lựa chọn phù hợp cho entity JPA thông thường.

Ví dụ DTO record:

```java
public record CustomerSummary(Long id, String name) {
}
```

Có thể dùng record trong constructor projection hoặc mapping DTO, trong khi entity vẫn là class mutable do JPA quản lý.

### 8.5. Dùng Lombok @Data cho entity

@Data sinh getter, setter, equals, hashCode và toString dựa trên các field. Với entity, điều này dễ tạo ra vấn đề:
- toString() có thể truy cập quan hệ lazy và phát sinh truy vấn.
- equals()/hashCode() có thể đi qua association, gây vòng lặp hoặc tải dữ liệu ngoài ý muốn.
- Quan hệ hai chiều có thể gây đệ quy vô hạn.
- Field mutable có thể khiến hashCode thay đổi khi entity đã nằm trong HashSet/HashMap.

Nên dùng annotation Lombok có chọn lọc, ví dụ @Getter, @Setter khi phù hợp, và tự thiết kế equals/hashCode theo quy tắc domain. Constructor không tham số vẫn phải được khai báo hoặc sinh với mức truy cập phù hợp:

```java
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@Getter
@Entity
public class Customer {
    // ...
}
```

Lombok chỉ sinh mã lúc compile; cần kiểm tra kết quả sinh ra, nhất là khi dùng @Builder, @AllArgsConstructor hoặc @Value. @Value thường làm class và field final, vì vậy không phù hợp với entity JPA thông thường.

### 8.6. Constructor JPA có side effect

Nếu constructor không tham số gửi event, ghi log nghiệp vụ, tạo dữ liệu phụ hoặc gọi service, các hành động đó có thể xảy ra mỗi khi provider tạo instance để hydrate hoặc proxy. Hãy để constructor này tối thiểu và chuyển side effect sang service hoặc lifecycle callback phù hợp.

### 8.7. Dùng equals/hashCode dựa trên mọi field

Entity thường có quan hệ hai chiều và field lazy. Nếu equals() hoặc hashCode() duyệt toàn bộ field, chỉ so sánh hai entity cũng có thể:
- Kích hoạt lazy loading.
- Tạo vòng lặp qua quan hệ hai chiều.
- Đọc nhiều dữ liệu hơn cần thiết.
- Thay đổi hashCode sau khi field mutable thay đổi.

Nếu có natural key bất biến và duy nhất, có thể dùng nó làm cơ sở so sánh. Nếu dùng generated ID, cần thiết kế cẩn thận cho trạng thái trước và sau persist; ID có thể null trước khi entity được lưu. Không có một implementation duy nhất phù hợp cho mọi domain.

## 9. Lưu ý với Kotlin và các ngôn ngữ có class final mặc định

Kotlin class và method mặc định là final. Nếu dùng Kotlin với JPA, cần cấu hình compiler plugin để mở class/method phù hợp và tạo constructor không tham số cho entity.

Hai plugin thường gặp:
- kotlin-jpa (no-arg plugin) hỗ trợ sinh constructor không tham số cho các annotation JPA.
- all-open có thể mở class được đánh dấu bằng annotation được cấu hình, ví dụ @Entity, để proxying hoạt động.

Cấu hình cụ thể phụ thuộc phiên bản Kotlin và Gradle plugin. Cần xác nhận plugin áp dụng đúng module và annotation JPA mà dự án sử dụng. Đừng chỉ thêm dependency runtime rồi giả định compiler đã sinh mã phù hợp.

Nếu dùng Java, vấn đề này đơn giản hơn vì class không final theo mặc định; chỉ cần tránh khai báo final và cung cấp constructor không tham số đúng mức truy cập.

## 10. Kiểm tra entity có thể khởi tạo và proxy

### 10.1. Kiểm tra bằng integration test

Một bài test có thể kiểm tra entity được persist, tải lại và quan hệ lazy được khởi tạo trong transaction. Ví dụ khái quát:

```java
@DataJpaTest
class PurchaseOrderRepositoryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private PurchaseOrderRepository repository;

    @Test
    void loadsLazyCustomerInsideTransaction() {
        Customer customer = new Customer("Lan");
        entityManager.persist(customer);

        PurchaseOrder order = new PurchaseOrder(customer);
        entityManager.persist(order);
        entityManager.flush();
        entityManager.clear();

        PurchaseOrder loaded = repository.findById(order.getId())
            .orElseThrow();

        assertThat(loaded.getCustomer().getName()).isEqualTo("Lan");
    }
}
```

Đây là ví dụ minh họa; constructor và mapping của Customer, PurchaseOrder cần có trong mô hình test tương ứng. clear() tách entity đã lưu khỏi persistence context, buộc lần tải sau đọc lại từ database. Truy cập getName() kiểm tra đường lazy loading bên trong transaction test.

### 10.2. Kiểm tra trạng thái loaded bằng PersistenceUnitUtil

JPA cung cấp PersistenceUnitUtil để kiểm tra trạng thái tải:

```java
PersistenceUnitUtil util =
    entityManagerFactory.getPersistenceUnitUtil();

boolean loaded = util.isLoaded(order, "customer");
```

Đây là API chuẩn JPA, hữu ích hơn việc kiểm tra tên class proxy cụ thể của Hibernate. Không nên viết test phụ thuộc vào tên class được sinh động vì tên và cơ chế proxy có thể thay đổi giữa các phiên bản provider.

Hibernate cũng cung cấp API riêng như Hibernate.isInitialized(...), nhưng đó là phụ thuộc provider-specific. Dùng nó khi test chủ đích kiểm tra hành vi Hibernate, còn test portability nên ưu tiên API JPA.

### 10.3. Những gì cần quan sát

Khi test proxy và lazy loading, kiểm tra:
- Entity được persist và load lại bình thường.
- Quan hệ lazy chưa bị truy cập thì chưa bị tải nếu provider và mapping thực sự hỗ trợ.
- Truy cập thuộc tính lazy trong transaction hoạt động.
- Không truy cập proxy chưa khởi tạo sau khi persistence context đã đóng.
- Số lượng SQL phát sinh hợp lý, không có N+1 ngoài dự kiến.
- Entity vẫn hoạt động khi dùng đúng constructor, field/property access và modifier.

Không nên chỉ kiểm tra getClass() có phải class proxy hay không. Provider có thể dùng subclass proxy, bytecode enhancement hoặc một cơ chế khác.

## 11. Checklist thiết kế Entity class

Trước khi hoàn thành một entity, kiểm tra:

- [ ] Class được đánh dấu @Entity.
- [ ] Class là top-level hoặc static nested class.
- [ ] Class không khai báo final.
- [ ] Có constructor không tham số public hoặc protected.
- [ ] Constructor JPA không tham số không chứa nghiệp vụ hoặc side effect.
- [ ] Có thể bổ sung constructor có tham số/factory method cho ứng dụng.
- [ ] Persistent instance fields không final.
- [ ] Persistent methods/accessors không final.
- [ ] Access type field/property nhất quán và rõ ràng.
- [ ] Mapping annotations được đặt đúng vị trí theo access type.
- [ ] Quan hệ lazy được tải trong transaction và fetch plan phù hợp.
- [ ] equals, hashCode, toString không vô tình duyệt association lazy.
- [ ] Lombok không sinh class/field final hoặc constructor không phù hợp.
- [ ] Kotlin plugin no-arg/all-open được cấu hình nếu dùng Kotlin.
- [ ] Integration test xác nhận persist, load và lazy access.

## 12. Kết luận

JPA cần constructor không tham số để provider tạo entity trước khi nạp trạng thái từ database. Constructor đó phải public hoặc protected và nên giữ tối thiểu. Entity class phải có khả năng được kế thừa theo hợp đồng portable; class, persistent method và persistent field không nên final.

Các quy tắc này đặc biệt quan trọng với Hibernate subclass proxy, cơ chế thường được dùng để trì hoãn việc tải entity liên quan. Lazy loading còn phụ thuộc persistence context và transaction, vì vậy cần tải dữ liệu đúng ranh giới use case và kiểm tra bằng integration test.

Thiết kế entity tốt là thiết kế tách biệt rõ constructor dành cho persistence với cách ứng dụng tạo object mới, giữ access strategy nhất quán, không làm side effect trong constructor và không để proxy bị cản trở bởi modifier hoặc code sinh tự động.