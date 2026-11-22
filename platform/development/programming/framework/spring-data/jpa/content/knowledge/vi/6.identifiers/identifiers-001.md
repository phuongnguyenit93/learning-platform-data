# Khóa tự nhiên, khóa thay thế và tiêu chí lựa chọn

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt khóa tự nhiên (natural key) và khóa thay thế (surrogate key).
- Nhận diện candidate key, primary key và alternate key trong mô hình dữ liệu.
- Ánh xạ khóa trong JPA bằng `@Id`, `@GeneratedValue`, `@Column`, `@UniqueConstraint`, `@EmbeddedId` và `@IdClass`.
- Chọn khóa phù hợp dựa trên tính ổn định, tính duy nhất, phạm vi nghiệp vụ, khả năng tích hợp và chi phí vận hành.
- Thiết kế `equals()` và `hashCode()` cho entity mà không gây lỗi khi entity chuyển từ transient sang persistent.
- Xử lý thay đổi khóa, dữ liệu trùng và migration khi hệ thống đã có dữ liệu.

## 1. Khóa định danh trong mô hình dữ liệu

Một bản ghi cần có cách nhận diện duy nhất để hệ quản trị cơ sở dữ liệu và ứng dụng có thể tham chiếu đến nó. Trong quan hệ dữ liệu, khóa là một thuộc tính hoặc tập hợp thuộc tính dùng để xác định một dòng.

Một số khái niệm cần phân biệt:

- **Candidate key**: tập thuộc tính tối thiểu có thể xác định duy nhất một dòng. Một bảng có thể có nhiều candidate key.
- **Primary key (PK)**: candidate key được chọn làm khóa chính của bảng. Mỗi bảng quan hệ chỉ có một định nghĩa primary key, dù khóa đó có thể gồm nhiều cột.
- **Alternate key**: candidate key khác không được chọn làm primary key. Thường được bảo vệ bằng unique constraint.
- **Foreign key (FK)**: cột hoặc nhóm cột tham chiếu đến khóa được bảo đảm duy nhất của bảng khác.
- **Natural key**: khóa có ý nghĩa trong nghiệp vụ hoặc thế giới bên ngoài, chẳng hạn mã ISBN của sách hoặc mã ISO quốc gia.
- **Surrogate key**: khóa được tạo ra chủ yếu để định danh bản ghi trong hệ thống, không mang ý nghĩa nghiệp vụ, chẳng hạn số tăng tự động hoặc UUID.

Natural key và surrogate key mô tả nguồn gốc/ý nghĩa của khóa. Primary key và alternate key mô tả vai trò của khóa trong cấu trúc bảng. Vì vậy, một natural key có thể được chọn làm primary key hoặc chỉ được đặt làm alternate key; surrogate key thường được chọn làm primary key.

## 2. Khóa tự nhiên (Natural Key)

Natural key được lấy từ dữ liệu nghiệp vụ đã có ý nghĩa độc lập với cơ sở dữ liệu. Ví dụ:

- Mã ISBN xác định một ấn bản sách.
- Mã quốc gia ISO hai ký tự xác định một quốc gia theo chuẩn tương ứng.
- Mã SKU của sản phẩm trong một hệ thống bán hàng, nếu doanh nghiệp bảo đảm mã này duy nhất và không thay đổi.
- Mã đăng ký hoặc mã hợp đồng, nếu quy tắc nghiệp vụ xác định rõ phạm vi và vòng đời của mã.

Một natural key tốt thường có các đặc điểm:

1. **Duy nhất**: hai đối tượng khác nhau không được có cùng khóa trong phạm vi đã xác định.
2. **Ổn định**: giá trị hiếm khi hoặc không bao giờ thay đổi trong vòng đời đối tượng.
3. **Không rỗng**: hệ thống có thể xác định khóa ngay khi tạo đối tượng.
4. **Có quy tắc rõ ràng**: cách chuẩn hóa, phân biệt chữ hoa/chữ thường, khoảng trắng và phạm vi duy nhất được xác định.
5. **Đủ gọn**: không quá dài hoặc chứa quá nhiều cột khiến index và foreign key trở nên nặng nề.

### Natural key có thể thay đổi

Tên, email, số điện thoại, địa chỉ hoặc tên đăng nhập có thể là duy nhất ở một thời điểm nhưng không nhất thiết ổn định suốt vòng đời đối tượng.

Ví dụ, email có thể thay đổi khi người dùng chuyển công ty hoặc cập nhật thông tin liên hệ. Nếu email là primary key, thay đổi email sẽ kéo theo cập nhật mọi foreign key đang tham chiếu, đồng thời có thể ảnh hưởng đến cache, URL, log, sự kiện tích hợp và dữ liệu lịch sử.

Không nên chọn một thuộc tính làm natural key chỉ vì hiện tại nó có unique constraint. Cần hỏi liệu nghiệp vụ có cam kết giá trị đó bất biến hay không, và nếu thay đổi thì tác động lan đến đâu.

### Phạm vi duy nhất

Một mã có thể duy nhất trong từng tổ chức nhưng không duy nhất trên toàn hệ thống. Ví dụ mã nhân viên `E001` có thể xuất hiện ở nhiều công ty.

Khi đó, khóa nghiệp vụ thực tế là cặp `(tenant_id, employee_code)`, không phải riêng `employee_code`. Quy tắc này phải được thể hiện bằng unique constraint ở database và bằng logic kiểm tra ở ứng dụng.

## 3. Khóa thay thế (Surrogate Key)

Surrogate key được hệ thống tạo ra để định danh bản ghi. Nó không mang ý nghĩa nghiệp vụ và thường được giữ ổn định dù các thuộc tính nghiệp vụ thay đổi.

Các dạng phổ biến:

- Số nguyên tăng tự động: `BIGINT`, identity column hoặc sequence.
- UUID: mã định danh 128 bit, có thể tạo độc lập ở nhiều node.
- Một mã kỹ thuật do hệ thống sinh theo cơ chế riêng, miễn là duy nhất và không phụ thuộc dữ liệu nghiệp vụ có thể thay đổi.

Ví dụ:

| id | sku | name |
|---:|---|---|
| 101 | BK-001 | Java Fundamentals |
| 102 | BK-002 | Spring Data JPA |

Ở đây `id` là surrogate primary key. `sku` là natural key của sản phẩm và được bảo vệ bằng unique constraint. Nếu SKU thay đổi theo một quy trình nghiệp vụ được cho phép, các foreign key vẫn tham chiếu đến `id` nên không cần đổi theo.

### Ưu điểm

- Khóa ngắn, ổn định và thuận tiện cho foreign key.
- Không phụ thuộc vào quy tắc đặt mã nghiệp vụ.
- Dễ tham chiếu giữa các bảng khi dữ liệu nghiệp vụ thay đổi.
- Có thể tạo trước khi dữ liệu nghiệp vụ hoàn tất.
- UUID cho phép tạo ID ở nhiều dịch vụ mà không cần xin số từ một sequence trung tâm.

### Chi phí và giới hạn

- Cần một unique constraint riêng để bảo vệ natural key nếu nghiệp vụ yêu cầu.
- ID số tăng dần có thể để lộ thứ tự tương đối của bản ghi nếu đưa trực tiếp ra API; không được xem ID là cơ chế phân quyền hay bí mật.
- UUID thường lớn hơn khóa số, làm tăng kích thước index và foreign key. UUID ngẫu nhiên có thể gây phân mảnh index tùy database và cách lưu trữ.
- Với hệ thống phân tán, cần chọn định dạng UUID và chiến lược tạo khóa phù hợp với database, API và khả năng sắp xếp.

Surrogate key không loại bỏ yêu cầu kiểm tra trùng lặp nghiệp vụ. Ví dụ, hai sản phẩm vẫn không được có cùng SKU chỉ vì chúng có hai ID khác nhau.

## 4. Ánh xạ surrogate key và natural key trong JPA

Một lựa chọn thường phù hợp cho entity nghiệp vụ là dùng surrogate key làm `@Id`, đồng thời đặt natural key ở cột riêng có unique constraint.

Ví dụ dưới đây sử dụng Java 17+, Jakarta Persistence và Hibernate:

~~~java
package com.example.catalog;

import java.util.Locale;
import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
    name = "products",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_products_sku",
        columnNames = "sku"
    )
)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, updatable = false, length = 40)
    private String sku;

    @Column(name = "name", nullable = false, length = 160)
    private String name;

    protected Product() {
        // Required by JPA
    }

    public Product(String sku, String name) {
        this.sku = normalizeSku(sku);
        this.name = Objects.requireNonNull(name, "name must not be null");
    }

    private static String normalizeSku(String value) {
        Objects.requireNonNull(value, "sku must not be null");
        String normalized = value.strip().toUpperCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        return normalized;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public void rename(String name) {
        this.name = Objects.requireNonNull(name, "name must not be null");
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Product that)) {
            return false;
        }
        return sku != null && sku.equals(that.getSku());
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(sku);
    }
}
~~~

Trong ví dụ:

- `id` là surrogate primary key, được database sinh khi insert.
- `sku` là natural key, được chuẩn hóa khi tạo và không có setter.
- `updatable = false` ngăn Hibernate đưa cột SKU vào câu UPDATE thông thường.
- `uniqueConstraints` mô tả ràng buộc duy nhất ở cấp bảng.
- `equals()` và `hashCode()` dựa trên SKU vì ví dụ giả định SKU bất biến và đã có ngay khi tạo entity.

`updatable = false` không phải ràng buộc bảo mật hoặc bảo đảm bất biến ở cấp database. Native SQL, migration hoặc một ứng dụng khác vẫn có thể thay đổi cột. Unique constraint và quy tắc bất biến cần được bảo vệ ở database cùng quy trình nghiệp vụ.

Repository có thể tra cứu theo cả ID và natural key:

~~~java
package com.example.catalog;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {

    Optional<Product> findBySku(String sku);
}
~~~

Khi lưu, nếu SKU bị trùng, database sẽ từ chối insert hoặc update theo unique constraint. Có thể kiểm tra trước bằng repository để đưa ra thông báo thân thiện, nhưng kiểm tra trước không thay thế unique constraint vì hai transaction đồng thời vẫn có thể cùng vượt qua bước kiểm tra.

## 5. equals() và hashCode() của entity

Đây là điểm dễ gây lỗi khi chọn natural key hoặc surrogate key.

Entity JPA có vòng đời:

- **Transient**: đối tượng mới, chưa được quản lý bởi persistence context; ID sinh tự động thường vẫn là null.
- **Managed/Persistent**: entity đang được EntityManager quản lý; ID có thể đã được gán.
- **Detached**: entity đã rời persistence context nhưng vẫn còn trong bộ nhớ.
- **Removed**: entity được đánh dấu xóa trong persistence context.

Nếu `hashCode()` phụ thuộc vào ID sinh tự động, giá trị hash có thể thay đổi sau khi persist. Nếu entity đã nằm trong `HashSet` trước khi ID được sinh, việc tìm hoặc xóa phần tử có thể thất bại vì phần tử nằm ở bucket cũ.

### Khi dùng natural key

Chỉ dùng natural key cho `equals()` và `hashCode()` nếu khóa đó:

- Không null ngay từ khi tạo entity.
- Duy nhất trong phạm vi entity.
- Bất biến trong toàn bộ vòng đời.
- Có cùng cách chuẩn hóa ở mọi đường tạo entity.

Ví dụ Product ở trên phù hợp với giả định SKU bất biến. Nếu SKU có thể đổi, cách cài đặt đó không còn an toàn cho collection dựa trên hash.

### Khi dùng generated surrogate ID

Không nên viết `equals()` đơn giản bằng `id == other.id` mà không xét trường hợp hai entity mới cùng có ID null. Hai đối tượng transient không có ID không phải là cùng một entity.

Một chiến lược thường gặp là:

- Hai reference giống nhau thì bằng nhau.
- Chỉ so sánh ID khi cả hai ID đều khác null.
- Dùng hash code ổn định trong suốt vòng đời entity.
- Xử lý proxy của provider nhất quán.

Hibernate proxy có thể làm cho so sánh `getClass()` và `instanceof` cần được cân nhắc. Nếu dùng API như `Hibernate.getClass()`, cần chấp nhận phụ thuộc Hibernate. Không có một mẫu `equals/hashCode` duy nhất phù hợp cho mọi entity; hãy chọn theo identity contract của domain và kiểm thử với proxy, entity transient, managed và detached.

Nếu entity không cần so sánh theo giá trị trong collection hoặc domain, có thể giữ identity equality mặc định của Object. Đừng tự động sinh equals/hashCode cho mọi field bằng IDE hoặc Lombok `@Data`: điều đó có thể đưa association lazy, collection hoặc field có thể thay đổi vào phép so sánh, dẫn đến tải dữ liệu ngoài ý muốn, đệ quy hoặc hash không ổn định.

## 6. Natural key làm primary key

Có trường hợp natural key thực sự ổn định, ngắn và được chuẩn hóa bởi một tiêu chuẩn hoặc quy tắc nghiệp vụ đáng tin cậy. Khi đó có thể ánh xạ trực tiếp bằng `@Id`.

Ví dụ bảng quốc gia dùng mã ISO hai ký tự làm khóa:

~~~java
@Entity
@Table(name = "countries")
public class Country {

    @Id
    @Column(name = "country_code", length = 2, nullable = false)
    private String code;

    @Column(name = "name", nullable = false)
    private String name;

    protected Country() {
    }

    public Country(String code, String name) {
        this.code = code.strip().toUpperCase(Locale.ROOT);
        this.name = name;
    }

    public String getCode() {
        return code;
    }
}
~~~

Mã quốc gia có thể là lựa chọn tốt nếu hệ thống dùng đúng chuẩn ISO và có quy tắc xử lý mã đã ngừng sử dụng, thay đổi hoặc dữ liệu lịch sử. Nếu một mã có thể được tái sử dụng hoặc cần lưu nhiều phiên bản theo thời gian, phải mô hình hóa thêm trạng thái/hiệu lực thay vì giả định mã luôn đại diện cho một đối tượng bất biến.

Không nên dùng natural key làm primary key chỉ vì nó dễ đọc. Khóa chính được tham chiếu bởi nhiều bảng và có thể trở thành chi phí lớn nếu quy tắc nghiệp vụ đổi.

## 7. Khóa tự nhiên kết hợp nhiều cột

Một natural key có thể là tổ hợp nhiều thuộc tính. Ví dụ mã nhân viên chỉ duy nhất trong từng tenant:

`(tenant_id, employee_code)`

Nếu bảng vẫn có surrogate ID, có thể giữ khóa chính kỹ thuật và tạo unique constraint cho cặp natural key:

~~~java
@Entity
@Table(
    name = "employees",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_employee_tenant_code",
        columnNames = {"tenant_id", "employee_code"}
    )
)
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false, updatable = false)
    private Long tenantId;

    @Column(name = "employee_code", nullable = false, updatable = false)
    private String employeeCode;

    protected Employee() {
    }
}
~~~

Unique constraint bảo đảm một tenant không có hai nhân viên cùng mã. Hai tenant khác nhau vẫn có thể dùng cùng employee_code.

### Khi nào dùng composite primary key?

Nếu tổ hợp thuộc tính tự nhiên là định danh ổn định và phù hợp với mọi quan hệ tham chiếu, JPA hỗ trợ hai cách chính:

- `@EmbeddedId`: đóng gói các thành phần khóa vào một lớp `@Embeddable`.
- `@IdClass`: khai báo lớp khóa riêng và đánh dấu các field khóa trực tiếp trên entity bằng `@Id`.

Ví dụ với `@EmbeddedId`:

~~~java
@Embeddable
public class EmployeeKey implements java.io.Serializable {

    @Column(name = "tenant_id")
    private Long tenantId;

    @Column(name = "employee_code")
    private String employeeCode;

    protected EmployeeKey() {
    }

    public EmployeeKey(Long tenantId, String employeeCode) {
        this.tenantId = tenantId;
        this.employeeCode = employeeCode;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getEmployeeCode() {
        return employeeCode;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof EmployeeKey that)) return false;
        return java.util.Objects.equals(tenantId, that.tenantId)
                && java.util.Objects.equals(employeeCode, that.employeeCode);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(tenantId, employeeCode);
    }
}

@Entity
@Table(name = "employees")
public class EmployeeWithCompositeId {

    @EmbeddedId
    private EmployeeKey id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    protected EmployeeWithCompositeId() {
    }
}
~~~

Lớp khóa phải đáp ứng yêu cầu của Jakarta Persistence cho primary key class, gồm tính serializable và triển khai equals/hashCode theo giá trị khóa. Các field khóa cần được gán đầy đủ trước khi persist và không thay đổi sau đó.

Composite primary key làm foreign key tham chiếu phức tạp hơn vì bảng con phải lưu đủ các thành phần khóa. Khi tổ hợp dài, có nhiều quan hệ hoặc có khả năng thay đổi, surrogate primary key cộng unique constraint thường dễ vận hành hơn.

## 8. Chọn kiểu surrogate key: Long, sequence hay UUID

JPA cung cấp các chiến lược sinh ID phổ biến:

| Chiến lược | Cách hoạt động | Cân nhắc |
|---|---|---|
| IDENTITY | Database sinh ID khi insert bằng identity/auto-increment | Đơn giản; có thể hạn chế JDBC insert batching vì ID chỉ có sau insert |
| SEQUENCE | Lấy ID từ database sequence trước khi insert | Hữu ích với PostgreSQL và database hỗ trợ sequence; có thể cấp theo allocation size |
| TABLE | Dùng một bảng để cấp ID | Có chi phí điều phối và thường ít được ưu tiên nếu DB có identity/sequence |
| UUID | Sinh UUID theo cơ chế provider/JPA | Phù hợp khi cần tạo ID ở nhiều node; cần đánh giá kích thước và đặc tính index |
| AUTO | Để provider chọn chiến lược | Thuận tiện nhưng hành vi cụ thể phụ thuộc provider và database |

Ví dụ dùng identity:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Ví dụ dùng sequence:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "product_seq")
@SequenceGenerator(
    name = "product_seq",
    sequenceName = "product_id_seq",
    allocationSize = 50
)
private Long id;
~~~

`allocationSize` phải được thiết kế tương thích với cách provider cấp số và cấu hình sequence trong database. Hibernate có thể cấp trước một nhóm ID để giảm round trip; không tự đặt giá trị khác biệt mà không kiểm tra cấu hình sequence và chiến lược generator của phiên bản provider.

Ví dụ dùng UUID với Jakarta Persistence 3.1 trở lên:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.UUID)
private java.util.UUID id;
~~~

UUID có thể tạo ID mà không cần sequence trung tâm. Tuy nhiên, UUID không phải token bảo mật và không thay thế authorization. Nếu cần index hiệu quả, cân nhắc kiểu lưu trữ UUID native hoặc dạng sắp xếp phù hợp với database.

## 9. Hibernate @NaturalId

Hibernate có annotation riêng `org.hibernate.annotations.NaturalId` để đánh dấu thuộc tính hoặc nhóm thuộc tính đóng vai trò natural identifier của entity.

Ví dụ:

~~~java
import org.hibernate.annotations.NaturalId;

@Entity
@Table(
    name = "products",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_products_sku",
        columnNames = "sku"
    )
)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NaturalId
    @Column(nullable = false, updatable = false, length = 40)
    private String sku;

    protected Product() {
    }
}
~~~

`@NaturalId` là tính năng riêng của Hibernate, không thuộc Jakarta Persistence. Nó giúp Hibernate hiểu thuộc tính nào là natural identifier và có thể hỗ trợ truy vấn hoặc natural-id cache khi được cấu hình.

Annotation này không tự thay thế unique constraint trong database. Database vẫn cần bảo vệ tính duy nhất để chống dữ liệu trùng, kể cả khi có nhiều ứng dụng hoặc transaction ghi đồng thời.

Nếu natural ID có thể thay đổi, Hibernate có tùy chọn biểu diễn mutable natural ID. Tuy nhiên, chỉ đánh dấu mutable không giải quyết mọi hệ quả nghiệp vụ: cần kiểm tra cache, collection, tham chiếu, lịch sử và transaction. Ưu tiên khóa tự nhiên bất biến khi có thể.

## 10. Tiêu chí lựa chọn natural key hay surrogate key

Không có lựa chọn duy nhất cho mọi bảng. Hãy đánh giá theo các tiêu chí:

| Tiêu chí | Natural key phù hợp khi | Surrogate key phù hợp khi |
|---|---|---|
| Tính ổn định | Quy tắc nghiệp vụ cam kết không đổi | Thuộc tính nghiệp vụ có thể đổi |
| Tính duy nhất | Có chuẩn hoặc quy tắc duy nhất rõ ràng | Dữ liệu nguồn chưa có khóa ổn định |
| Thời điểm có khóa | Khóa đã tồn tại khi tạo đối tượng | Khóa nghiệp vụ được bổ sung sau |
| Độ dài | Khóa ngắn, đơn giản | Khóa dài hoặc gồm nhiều cột |
| Quan hệ | Ít tham chiếu hoặc khóa tự nhiên rất ổn định | Nhiều foreign key cần tham chiếu bền vững |
| Tích hợp | Mã ngoài hệ thống có tính ổn định cao | Có nhiều hệ thống nguồn hoặc mã nguồn có thể thay đổi |
| Phân tán | Mã được cấp duy nhất trên toàn hệ thống | UUID hoặc ID kỹ thuật có thể sinh độc lập |
| Lịch sử | Mã không tái sử dụng và có quy tắc vòng đời rõ | Cần lưu lịch sử khi mã nghiệp vụ thay đổi/tái sử dụng |

### Quy tắc thực hành

- Dùng natural key làm primary key khi giá trị ngắn, bất biến, duy nhất theo một quy tắc đáng tin cậy và mọi quan hệ tham chiếu đều chấp nhận việc phụ thuộc vào nó.
- Dùng surrogate primary key khi entity có nhiều quan hệ, dữ liệu nghiệp vụ có thể thay đổi hoặc khóa tự nhiên dài/phức tạp.
- Giữ natural key dưới dạng alternate key với unique constraint khi cần tra cứu hoặc chống trùng theo nghiệp vụ.
- Dùng composite key khi tổ hợp cột thực sự là định danh ổn định và các bảng tham chiếu có thể quản lý đầy đủ tổ hợp đó.
- Với dữ liệu nhập từ hệ thống ngoài, thường dùng surrogate ID nội bộ và unique constraint trên cặp `(source_system, external_id)`.

## 11. Migration khi thay đổi chiến lược khóa

Đổi primary key trên một hệ thống đã có dữ liệu là một migration có rủi ro cao. Cần xem xét toàn bộ foreign key, index, sequence, API contract, batch import, cache và dữ liệu tích hợp.

Ví dụ chuyển từ natural primary key `employee_code` sang surrogate `id`:

1. Thêm cột `id` vào bảng và tạo cơ chế sinh giá trị cho các dòng hiện có.
2. Backfill ID cho toàn bộ bản ghi, kiểm tra không null và không trùng.
3. Thêm unique constraint cho ID và tạo index cần thiết.
4. Thêm cột ID tương ứng vào các bảng con, backfill bằng cách join qua employee_code.
5. Thêm foreign key mới, xác minh mọi dòng con có bản ghi cha.
6. Triển khai ứng dụng có thể đọc/ghi theo mô hình chuyển tiếp phù hợp.
7. Chuyển foreign key và truy vấn sang ID; theo dõi các consumer và báo cáo.
8. Sau khi không còn consumer phụ thuộc khóa cũ, mới xem xét bỏ primary key/foreign key cũ.
9. Giữ unique constraint cho natural key nếu nghiệp vụ vẫn yêu cầu mã không trùng.

Không thực hiện một lần ALTER PRIMARY KEY đơn giản khi các bảng con, consumer và dữ liệu lịch sử chưa được chuyển đổi. Với hệ thống lớn, cần chiến lược expand-and-contract và khả năng rollback.

## 12. Kiểm tra và kiểm thử

### Kiểm tra database

- Primary key phải không null và duy nhất.
- Natural key có unique constraint ở đúng phạm vi.
- Các foreign key tham chiếu đến cột hoặc tổ hợp cột có tính duy nhất.
- Index hỗ trợ các truy vấn tra cứu theo natural key.
- Các giá trị đã được chuẩn hóa nhất quán.

Ví dụ kiểm tra SKU trùng trước khi thêm constraint:

~~~sql
SELECT sku, COUNT(*) AS total
FROM products
GROUP BY sku
HAVING COUNT(*) > 1;
~~~

Với khóa theo tenant:

~~~sql
SELECT tenant_id, employee_code, COUNT(*) AS total
FROM employees
GROUP BY tenant_id, employee_code
HAVING COUNT(*) > 1;
~~~

Nếu truy vấn trả về dữ liệu, phải xử lý trùng và quyết định bản ghi chuẩn trước khi thêm unique constraint.

### Kiểm thử JPA

Integration test nên kiểm tra:

- Hai entity có cùng natural key không thể cùng được lưu thành công.
- Tra cứu bằng repository method `findBySku` trả về đúng entity.
- Entity được lưu rồi nạp lại có cùng identity theo quy tắc đã chọn.
- `equals()` và `hashCode()` ổn định khi entity ở trạng thái transient, managed và detached.
- Nếu dùng proxy lazy, phép so sánh không tạo kết quả bất đối xứng hoặc lỗi class cast.
- Composite key có equals/hashCode đúng và repository ID type khớp.
- Foreign key vẫn tham chiếu đúng sau migration.

Unique constraint là hàng rào cuối cùng trước ghi đồng thời. Kiểm tra bằng `existsBySku()` chỉ giúp thông báo sớm, không loại bỏ race condition giữa hai transaction.

## 13. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Dùng email làm primary key dù email có thể đổi | Phải cập nhật foreign key và tham chiếu ở nhiều nơi | Dùng surrogate ID; giữ email là unique key nếu nghiệp vụ cần |
| Chỉ kiểm tra trùng ở service | Hai transaction đồng thời vẫn có thể ghi trùng | Tạo unique constraint ở database |
| Dùng mã hiển thị có thể tái sử dụng làm khóa | Bản ghi lịch sử có thể bị tham chiếu nhầm | Định nghĩa vòng đời mã hoặc dùng ID nội bộ |
| Dùng nhiều cột làm PK dù quan hệ tham chiếu rất rộng | Foreign key và join phức tạp | Cân nhắc surrogate PK cộng composite unique constraint |
| Dựa vào ID null để so sánh entity | Hai entity transient khác nhau có thể bị xem là bằng nhau | Thiết kế equals/hashCode theo identity contract |
| hashCode đổi sau khi persist | HashSet/HashMap không tìm thấy entity ở bucket cũ | Dùng khóa bất biến hoặc hash code ổn định |
| Dùng Lombok @Data trên entity | Association lazy và collection tham gia equals/hashCode/toString | Viết rõ getter, equals/hashCode và toString phù hợp |
| Cho rằng UUID là cơ chế bảo mật | ID đoán khó vẫn không chứng minh quyền truy cập | Luôn kiểm tra authorization ở tầng nghiệp vụ |
| Cho rằng unique annotation đã tạo constraint production | Schema migration có thể không áp dụng annotation | Quản lý constraint bằng migration và kiểm tra database |

## Checklist trước khi merge

- [ ] Đã xác định natural key và surrogate key của entity.
- [ ] Quy tắc duy nhất và phạm vi duy nhất được mô tả rõ.
- [ ] Natural key được chọn làm PK thật sự bất biến và ổn định.
- [ ] Nếu dùng surrogate PK, natural key nghiệp vụ có unique constraint khi cần.
- [ ] Foreign key tham chiếu đến khóa ổn định và có index phù hợp.
- [ ] equals/hashCode phù hợp với vòng đời entity và proxy.
- [ ] Chiến lược IDENTITY, SEQUENCE, UUID hoặc AUTO được chọn có chủ đích.
- [ ] Migration xử lý dữ liệu cũ, foreign key và consumer.
- [ ] Integration test kiểm tra trùng lặp, tra cứu, identity và quan hệ.

## Kết luận

Natural key mô tả định danh có ý nghĩa nghiệp vụ; surrogate key là định danh kỹ thuật do hệ thống tạo ra. Natural key chỉ nên làm primary key khi nó ngắn, duy nhất và ổn định trong toàn bộ vòng đời dữ liệu. Với nhiều entity nghiệp vụ, surrogate primary key kết hợp unique constraint trên natural key thường giúp foreign key và migration dễ quản lý hơn. Trong JPA, quyết định khóa còn ảnh hưởng đến `equals()`, `hashCode()`, cách sinh ID và repository. Hãy bảo vệ tính duy nhất ở database, kiểm thử vòng đời entity và chọn khóa dựa trên quy tắc nghiệp vụ thực tế.
