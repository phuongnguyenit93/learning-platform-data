# Ánh xạ kế thừa và giới hạn so với JPA

Trong ứng dụng Spring Data Relational R2DBC, entity Java được ánh xạ vào bảng quan hệ thông qua mapping metadata. Java cho phép một lớp kế thừa thuộc tính và hành vi từ lớp cha, nhưng khả năng kế thừa của ngôn ngữ không đồng nghĩa với việc framework hỗ trợ mọi chiến lược ánh xạ kế thừa như JPA.

JPA là một ORM có mô hình kế thừa entity riêng: một hệ phân cấp entity có thể dùng chung một bảng, nhiều bảng có quan hệ join hoặc bảng riêng cho từng lớp cụ thể. Spring Data Relational tập trung vào ánh xạ các aggregate và entity vào cấu trúc bảng quan hệ; nó không cung cấp đầy đủ các chiến lược inheritance mapping của JPA.

Cần phân biệt hai ý:

- **Kế thừa trong Java:** lớp con nhận thuộc tính và phương thức từ lớp cha để tái sử dụng mô hình và hành vi.
- **Kế thừa trong ORM:** framework tự xác định cách lưu nhiều loại entity trong một hoặc nhiều bảng, nhận diện subtype khi đọc dữ liệu và xây dựng truy vấn đa hình.

Spring Data R2DBC có thể làm việc với mô hình lớp Java có thuộc tính kế thừa, nhưng không nên kỳ vọng `@Inheritance`, discriminator hoặc các annotation JPA sẽ tạo ra chiến lược lưu trữ tương ứng. Bài học này giải thích ranh giới đó và cách mô hình hóa dữ liệu quan hệ khi ứng dụng cần các loại đối tượng có phần dữ liệu chung.

## 1. Kế thừa lớp Java và ánh xạ quan hệ là hai vấn đề khác nhau

Giả sử ứng dụng có nhiều loại tài khoản. Mỗi tài khoản đều có mã định danh, tên chủ tài khoản và thời điểm tạo, nhưng mỗi loại còn có dữ liệu riêng.

Có thể dùng một lớp cha để gom các thuộc tính chung:

~~~java
public abstract class BaseAccount {

    @Column("owner_name")
    private String ownerName;

    @Column("created_at")
    private LocalDateTime createdAt;

    // Constructor, getters
}
~~~

Lớp cụ thể:

~~~java
@Table("savings_account")
public class SavingsAccount extends BaseAccount {

    @Id
    private Long id;

    @Column("interest_rate")
    private BigDecimal interestRate;
}
~~~

~~~java
@Table("checking_account")
public class CheckingAccount extends BaseAccount {

    @Id
    private Long id;

    @Column("overdraft_limit")
    private BigDecimal overdraftLimit;
}
~~~

Trong mô hình này, lớp con kế thừa các thuộc tính Java từ `BaseAccount`. Mỗi lớp cụ thể có `@Table` riêng, vì vậy ý định mô hình dữ liệu là bảng `savings_account` cho tài khoản tiết kiệm và bảng `checking_account` cho tài khoản thanh toán.

Mapping metadata của Spring Data được xây dựng cho từng persistent type và các thuộc tính mà framework nhận diện trên kiểu đó, bao gồm các thuộc tính kế thừa được khám phá trong hệ phân cấp lớp. Những thuộc tính đó được ánh xạ như thuộc tính của entity cụ thể. Điều này không tạo ra một bảng riêng cho lớp cha, không tự tạo join giữa bảng cha và bảng con, và cũng không tự sinh discriminator để lựa chọn subtype.

Khi dùng kế thừa thuộc tính, cần kiểm tra mapping metadata và SQL được sinh trên đúng phiên bản Spring Data Relational của dự án. Đặc biệt, tránh khai báo lại một property cùng tên ở lớp con vì có thể gây mơ hồ trong quá trình ánh xạ.

## 2. Spring Data Relational ánh xạ entity theo bảng như thế nào?

Một persistent entity thường được xác định bởi kiểu Java cụ thể và metadata mapping của nó. Annotation `@Table` chỉ định bảng, `@Id` chỉ định định danh, `@Column` chỉ định cột, còn các annotation khác mô tả những đặc điểm của property hoặc quan hệ.

Ví dụ:

~~~java
@Table("employee")
public class Employee {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    @Column("department_code")
    private String departmentCode;
}
~~~

Entity `Employee` ánh xạ vào bảng `employee`. Khi repository thực hiện insert, select hoặc update, Spring Data dùng metadata của entity để tạo SQL và chuyển đổi hàng kết quả thành đối tượng Java.

Nếu lớp `Employee` kế thừa một lớp Java có thuộc tính persistent, các thuộc tính được nhận diện đó có thể tham gia vào mapping của `Employee` như các property khác. Tuy nhiên, framework vẫn ánh xạ entity cụ thể theo bảng của nó.

Ví dụ, lớp cha không tự trở thành một bảng chỉ vì nó có các property được kế thừa:

~~~java
public abstract class Auditable {

    @Column("created_at")
    private LocalDateTime createdAt;

    @Column("updated_at")
    private LocalDateTime updatedAt;
}

@Table("employee")
public class Employee extends Auditable {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;
}
~~~

Mô hình này thể hiện việc tái sử dụng thuộc tính audit trong Java. Hai cột `created_at` và `updated_at` được xem là thuộc tính của entity `Employee` và nằm trong bảng `employee`, nếu mapping metadata của phiên bản dự án nhận diện các property kế thừa như dự kiến.

Đây là kế thừa thuộc tính trong mô hình đối tượng, không phải chiến lược inheritance mapping có bảng cha và bảng con.

## 3. JPA hỗ trợ các chiến lược kế thừa nào?

JPA định nghĩa ba chiến lược chính thông qua `@Inheritance`:

| Chiến lược JPA | Cách lưu dữ liệu |
|---|---|
| `SINGLE_TABLE` | Toàn bộ hệ phân cấp entity lưu trong một bảng; discriminator giúp nhận diện loại cụ thể |
| `JOINED` | Lớp cha và các lớp con có bảng riêng; truy vấn subtype thường cần join |
| `TABLE_PER_CLASS` | Mỗi lớp cụ thể có bảng chứa cả thuộc tính kế thừa và thuộc tính riêng |

JPA còn có `@MappedSuperclass` để chia sẻ mapping thuộc tính từ lớp cha mà không biến lớp cha thành một entity có bảng riêng.

Những cơ chế này thuộc mô hình ORM của JPA. Không thể chỉ thêm các annotation đó vào entity R2DBC rồi kỳ vọng Spring Data Relational tự tạo cùng cấu trúc hoặc hành vi.

### 3.1. SINGLE_TABLE

Ví dụ JPA:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "account_type")
public abstract class Account {
    @Id
    private Long id;
    private String ownerName;
}

@Entity
@DiscriminatorValue("SAVINGS")
public class SavingsAccount extends Account {
    private BigDecimal interestRate;
}

@Entity
@DiscriminatorValue("CHECKING")
public class CheckingAccount extends Account {
    private BigDecimal overdraftLimit;
}
~~~

JPA có thể lưu cả hai loại tài khoản trong một bảng `account`. Cột `account_type` cho biết mỗi hàng đại diện cho subtype nào. Các cột riêng của từng subtype thường nullable đối với loại còn lại.

Với Spring Data Relational, có thể thiết kế bảng đơn theo cách tường minh: tạo một entity ánh xạ tới bảng đó, khai báo cột discriminator như một property thông thường, rồi tự chuyển đổi thành kiểu domain cụ thể ở tầng ứng dụng. Spring Data R2DBC không tự động áp dụng `@DiscriminatorColumn` và `@DiscriminatorValue` theo cơ chế JPA.

### 3.2. JOINED

Trong JPA, lớp cha có bảng riêng chứa các cột chung. Mỗi lớp con có bảng riêng chứa cột đặc thù và khóa liên kết về hàng của lớp cha. Truy vấn subtype có thể cần join các bảng.

Với Spring Data Relational, có thể mô hình hóa các bảng này bằng entity và repository riêng, sau đó thực hiện truy vấn join tường minh bằng SQL hoặc `DatabaseClient`. Việc đọc dữ liệu và dựng đối tượng domain cần được viết rõ trong ứng dụng. Không có chiến lược `JOINED` tự động tương đương JPA.

### 3.3. TABLE_PER_CLASS

JPA có thể tạo bảng riêng cho mỗi lớp cụ thể và lặp lại các cột kế thừa trong từng bảng. Một truy vấn trên kiểu cha có thể cần hợp nhất dữ liệu từ nhiều bảng theo chiến lược của provider.

Với Spring Data Relational, có thể tạo entity riêng cho từng bảng cụ thể. Nếu ứng dụng cần tìm kiếm trên nhiều loại, hãy viết truy vấn tổng hợp phù hợp với database hoặc gọi các repository riêng rồi hợp nhất kết quả ở tầng dịch vụ. Framework không tự thực hiện truy vấn đa hình trên toàn bộ các bảng của hệ phân cấp theo chiến lược JPA.

### 3.4. Mapped superclass

JPA dùng `@MappedSuperclass` để khai báo các thuộc tính chung được kế thừa bởi entity con. Lớp cha không có bảng riêng và không thể được truy vấn như một entity độc lập.

Trong Spring Data Relational, việc chia sẻ thuộc tính có thể thực hiện bằng một lớp Java cha thông thường, với các property được mapping framework nhận diện trên entity cụ thể. Không cần coi `jakarta.persistence.MappedSuperclass` là annotation cấu hình cho R2DBC; annotation JPA không thay thế metadata của Spring Data Relational.
## 4. Giới hạn của inheritance mapping trong Spring Data R2DBC

Khi chuyển từ JPA sang R2DBC, cần điều chỉnh kỳ vọng về những gì framework tự động thực hiện.

### 4.1. Không có chiến lược @Inheritance của JPA

Spring Data Relational không cung cấp các chiến lược `SINGLE_TABLE`, `JOINED` và `TABLE_PER_CLASS` thông qua `@Inheritance` như JPA. Các annotation sau không phải cách cấu hình inheritance mapping cho entity R2DBC:

- `jakarta.persistence.Inheritance`
- `jakarta.persistence.InheritanceType`
- `jakarta.persistence.DiscriminatorColumn`
- `jakarta.persistence.DiscriminatorValue`
- `jakarta.persistence.MappedSuperclass`

Nếu classpath có cả JPA và R2DBC, việc import nhầm annotation có thể khiến mã nguồn biên dịch nhưng annotation không tham gia vào mapping metadata mà Spring Data Relational sử dụng.

### 4.2. Không tự nhận diện subtype bằng discriminator theo JPA

Một cột `account_type` trong database chỉ là dữ liệu cột đối với mapping thông thường. Nó không tự làm cho Spring Data R2DBC chọn `SavingsAccount` hoặc `CheckingAccount` khi repository đọc một hàng vào kiểu cha.

Nếu cần polymorphism, ứng dụng phải quyết định cách đọc discriminator, xác định subtype và tạo đối tượng tương ứng. Việc này có thể thực hiện bằng một entity lưu trữ chung, custom mapping/conversion hoặc truy vấn và factory ở tầng ứng dụng.

### 4.3. Không tự sinh join cho hệ phân cấp lớp

Kế thừa Java không làm Spring Data tự join bảng cha và bảng con. Nếu schema lưu thuộc tính chung ở một bảng và thuộc tính subtype ở bảng khác, ứng dụng cần truy vấn join rõ ràng, dùng `DatabaseClient` hoặc SQL tùy chỉnh, rồi ánh xạ kết quả sang projection/DTO.

### 4.4. Không có truy vấn đa hình kiểu JPQL

JPA có JPQL và mô hình truy vấn entity, cho phép truy vấn trên một kiểu cha và có thể bao gồm các subtype theo chiến lược kế thừa của provider. Spring Data R2DBC thường dùng derived query theo property, `@Query` với SQL hoặc `DatabaseClient`.

Do đó, truy vấn đa hình qua nhiều bảng phải được thiết kế theo SQL và schema thực tế. Không thể chuyển nguyên một câu JPQL dùng entity hierarchy sang R2DBC mà không điều chỉnh.

### 4.5. Không có persistence context và lazy proxy như ORM JPA

JPA thường quản lý entity trong persistence context, theo dõi thay đổi và có thể tải association lazy thông qua proxy khi truy cập. Spring Data R2DBC không cung cấp cùng mô hình persistence context, dirty checking và lazy loading của JPA.

Ứng dụng cần gọi các repository hoặc truy vấn cần thiết một cách tường minh và kết hợp kết quả trong reactive pipeline. Việc có một property Java kiểu lớp cha hoặc lớp con không làm cho quan hệ database tự được tải khi gọi getter.

## 5. Tái sử dụng thuộc tính chung bằng lớp cha Java

Nếu mục tiêu chỉ là tránh lặp lại các trường chung như `id`, `createdAt`, `updatedAt` hoặc `tenantId`, một lớp cha Java có thể là lựa chọn phù hợp.

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;

public abstract class AuditableEntity {

    @Id
    private Long id;

    @Column("created_at")
    private LocalDateTime createdAt;

    @Column("updated_at")
    private LocalDateTime updatedAt;

    protected AuditableEntity() {
    }

    protected AuditableEntity(
            Long id,
            LocalDateTime createdAt,
            LocalDateTime updatedAt) {
        this.id = id;
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
    }

    public Long getId() {
        return id;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }
}
~~~

Entity cụ thể:

~~~java
@Table("purchase_order")
public class PurchaseOrder extends AuditableEntity {

    @Column("order_number")
    private String orderNumber;

    @Column("total_amount")
    private BigDecimal totalAmount;

    public PurchaseOrder() {
    }

    // Constructor và các getter cần thiết
}
~~~

Ở đây, `PurchaseOrder` vẫn ánh xạ vào một bảng `purchase_order`. Các thuộc tính audit được tái sử dụng trong mã Java và được mapping như property của entity cụ thể.

Một lớp cha dùng chung nên tập trung vào những property có cùng ý nghĩa và cùng cách lưu trữ ở các entity con. Không nên đưa mọi hành vi persistence vào một base class quá lớn; các entity khác nhau có thể có vòng đời, khóa chính và quy tắc lưu trữ khác nhau.

### 5.1. Chú ý property trùng tên

Tránh khai báo lại một property đã có trong lớp cha:

~~~java
public abstract class BaseEntity {
    private String status;
}

@Table("shipment")
public class Shipment extends BaseEntity {
    private String status;
}
~~~

Hai property cùng tên nhưng khác vị trí trong hệ phân cấp có thể làm mapping, constructor binding hoặc truy cập property trở nên khó dự đoán. Hãy chọn một định nghĩa duy nhất hoặc đổi tên property riêng nếu chúng thực sự có ý nghĩa khác nhau.

### 5.2. Constructor và entity bất biến

Nếu entity dùng constructor thay cho setter, cần bảo đảm Spring Data có thể tạo entity từ các property đã mapping. Có thể dùng constructor phù hợp hoặc `@PersistenceCreator` khi cần chỉ định constructor được sử dụng.

Khi property nằm ở lớp cha, hãy bảo đảm constructor của lớp con khởi tạo đầy đủ trạng thái cần thiết và các tham số constructor khớp với property model. Hãy kiểm tra materialization bằng integration test trên phiên bản framework của dự án.

### 5.3. Property không cần lưu trữ

Nếu lớp cha có dữ liệu chỉ phục vụ logic ứng dụng, hãy đánh dấu property đó là transient theo Spring Data:

~~~java
import org.springframework.data.annotation.Transient;

public abstract class BaseEntity {

    @Transient
    private String displayLabel;
}
~~~

Không dùng `@Column` cho property chỉ được tính toán và không tồn tại trong schema.

## 6. Dùng composition thay cho kế thừa khi chia sẻ dữ liệu

Kế thừa phù hợp khi các loại entity thực sự có quan hệ "là một" và có thể chia sẻ cùng một tập thuộc tính nền tảng. Nếu chỉ muốn gom nhóm dữ liệu liên quan, composition thường rõ ràng hơn.

Ví dụ, nhiều entity có địa chỉ liên hệ:

~~~java
public class Address {

    private String street;
    private String city;
    private String postalCode;
}
~~~

Có thể nhúng object value vào entity bằng `@Embedded` của Spring Data Relational:

~~~java
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    @Embedded.Nullable
    private Address address;
}
~~~

`@Embedded` biểu diễn các thuộc tính của value object như một phần của hàng chứa nó, thay vì tạo một entity độc lập có định danh riêng. Có thể dùng prefix nếu cần tránh trùng tên cột giữa các embedded property, theo API của phiên bản Spring Data Relational đang dùng.

Composition giúp mô hình domain thể hiện rõ một nhóm giá trị có cùng vòng đời với entity chứa nó. Nếu địa chỉ có định danh riêng, được nhiều aggregate tham chiếu hoặc có vòng đời độc lập, hãy cân nhắc mô hình hóa nó thành bảng và quan hệ phù hợp thay vì nhúng.

## 7. Mô hình hóa một bảng đơn có discriminator bằng SQL tường minh

Nếu nghiệp vụ cần nhiều subtype trong cùng một bảng, có thể lưu một cột phân loại như dữ liệu thông thường.

Ví dụ schema:

~~~sql
CREATE TABLE payment_method (
    id BIGINT PRIMARY KEY,
    method_type VARCHAR(30) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    card_last_four VARCHAR(4),
    bank_account_number VARCHAR(100)
);
~~~

Entity lưu trữ chung:

~~~java
@Table("payment_method")
public class PaymentMethodRecord {

    @Id
    private Long id;

    @Column("method_type")
    private String methodType;

    @Column("display_name")
    private String displayName;

    @Column("card_last_four")
    private String cardLastFour;

    @Column("bank_account_number")
    private String bankAccountNumber;
}
~~~

Tầng ứng dụng có thể chuyển bản ghi sang mô hình domain cụ thể:

~~~java
public sealed interface PaymentMethod
        permits CardPayment, BankTransfer {
}

public record CardPayment(
        Long id,
        String displayName,
        String lastFourDigits) implements PaymentMethod {
}

public record BankTransfer(
        Long id,
        String displayName,
        String accountNumber) implements PaymentMethod {
}
~~~

Factory đọc `methodType` và tạo subtype:

~~~java
PaymentMethod toDomain(PaymentMethodRecord record) {
    return switch (record.getMethodType()) {
        case "CARD" -> new CardPayment(
                record.getId(),
                record.getDisplayName(),
                record.getCardLastFour());
        case "BANK_TRANSFER" -> new BankTransfer(
                record.getId(),
                record.getDisplayName(),
                record.getBankAccountNumber());
        default -> throw new IllegalArgumentException(
                "Unsupported payment method type");
    };
}
~~~

Cách làm này có các điểm cần quản lý:

- Giá trị discriminator phải được kiểm soát bằng enum, constraint hoặc quy tắc domain.
- Cột không áp dụng cho subtype hiện tại có thể để null, nhưng cần xác định rõ điều kiện hợp lệ.
- Khi thêm subtype mới, cần cập nhật schema nếu cần cột mới, factory và kiểm thử.
- Không được mặc định mọi giá trị discriminator trong database đều hợp lệ.
- Nếu cần đọc danh sách nhiều subtype, có thể đọc record rồi map từng record trong reactive pipeline.

Ví dụ chỉ minh họa thiết kế; cần bổ sung constructor/getter, repository và validation phù hợp với ứng dụng.

## 8. Mô hình hóa kiểu JOINED bằng entity và truy vấn riêng

Nếu muốn tách dữ liệu chung và dữ liệu riêng thành nhiều bảng, có thể biểu diễn cấu trúc đó tường minh.

Ví dụ:

~~~sql
CREATE TABLE vehicle (
    id BIGINT PRIMARY KEY,
    manufacturer VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    vehicle_type VARCHAR(30) NOT NULL
);

CREATE TABLE car_detail (
    vehicle_id BIGINT PRIMARY KEY REFERENCES vehicle(id),
    door_count INTEGER NOT NULL
);

CREATE TABLE motorcycle_detail (
    vehicle_id BIGINT PRIMARY KEY REFERENCES vehicle(id),
    engine_capacity INTEGER NOT NULL
);
~~~

Có thể tạo entity riêng cho bảng gốc và từng bảng chi tiết:

~~~java
@Table("vehicle")
public class VehicleRecord {

    @Id
    private Long id;

    private String manufacturer;
    private String model;

    @Column("vehicle_type")
    private String vehicleType;
}
~~~

~~~java
@Table("car_detail")
public class CarDetail {

    @Id
    @Column("vehicle_id")
    private Long vehicleId;

    @Column("door_count")
    private Integer doorCount;
}
~~~

Khi cần một đối tượng xe hoàn chỉnh, service có thể đọc `VehicleRecord`, dựa vào `vehicleType` để truy vấn bảng chi tiết phù hợp rồi tạo đối tượng domain. Nếu cần hiệu năng hoặc tính nhất quán tốt hơn, viết một câu SQL join tường minh và map kết quả sang projection/DTO.

Việc ghi nhiều bảng cần transaction nếu các thay đổi phải cùng thành công hoặc cùng rollback. Transaction reactive có thể bao bọc các publisher repository hoặc `DatabaseClient` tương ứng, miễn là chúng dùng cùng connection factory và transaction context.

Đây là mô hình hóa quan hệ tường minh. Spring Data R2DBC không tự sinh join theo hệ phân cấp Java như JPA `JOINED`.
## 9. Mô hình hóa TABLE_PER_CLASS bằng entity riêng

Nếu mỗi subtype có bảng riêng và phần dữ liệu chung được lặp lại ở từng bảng, có thể tạo mỗi bảng thành một entity độc lập.

Ví dụ:

~~~java
@Table("physical_product")
public class PhysicalProduct {

    @Id
    private Long id;

    private String name;

    @Column("shipping_weight")
    private BigDecimal shippingWeight;
}
~~~

~~~java
@Table("digital_product")
public class DigitalProduct {

    @Id
    private Long id;

    private String name;

    @Column("download_url")
    private String downloadUrl;
}
~~~

Có thể chia sẻ interface hoặc class Java cho các hành vi domain ở tầng ứng dụng, nhưng mỗi entity vẫn có repository và mapping table riêng.

Nếu cần một danh sách sản phẩm tổng hợp, có thể dùng SQL `UNION ALL` với các cột chuẩn hóa và discriminator, hoặc truy vấn từng repository rồi hợp nhất các publisher. Hãy cân nhắc phân trang, sắp xếp và tổng số bản ghi vì việc hợp nhất kết quả từ nhiều bảng ở ứng dụng có thể khác với một truy vấn database duy nhất.

## 10. Quan hệ aggregate và @MappedCollection

Spring Data Relational ưu tiên mô hình aggregate: aggregate root kiểm soát vòng đời của các đối tượng thuộc aggregate. Với collection các đối tượng con được lưu trong bảng riêng, `@MappedCollection` có thể mô tả cách ánh xạ quan hệ thuộc aggregate.

Ví dụ:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(
        idColumn = "order_id",
        keyColumn = "line_number")
    private List<OrderLine> lines;
}
~~~

`OrderLine` là phần dữ liệu thuộc aggregate `PurchaseOrder`, không nhất thiết là một subtype của `PurchaseOrder`. Khi lưu aggregate, Spring Data Relational quản lý các phần tử collection theo mapping đã khai báo.

Không dùng `@MappedCollection` để mô phỏng JPA inheritance. Nó mô tả quan hệ giữa aggregate root và phần tử được quản lý trong collection. Nếu đối tượng con có vòng đời và quyền sở hữu độc lập, hãy xem xét mô hình quan hệ và repository phù hợp với ranh giới aggregate.

## 11. So sánh Spring Data R2DBC và JPA

| Khả năng | JPA | Spring Data Relational R2DBC |
|---|---|---|
| Kế thừa property Java | Có | Có thể tái sử dụng property được mapping trên kiểu cụ thể |
| `@MappedSuperclass` | Có | Không dùng annotation JPA này làm metadata mapping |
| `@Inheritance` | Có | Không có chiến lược inheritance tương đương |
| `SINGLE_TABLE` với discriminator tự động | Có | Cần mô hình hóa và xử lý discriminator tường minh |
| `JOINED` tự động | Có | Cần entity/query join tường minh |
| `TABLE_PER_CLASS` | Có | Dùng entity/bảng riêng và tự tổng hợp truy vấn khi cần |
| Persistence context | Có | Không có persistence context kiểu JPA |
| Dirty checking | Có | Thường gọi save/update tường minh |
| Lazy loading qua proxy | Có thể có | Không có lazy proxy kiểu JPA |
| JPQL | Có | Dùng SQL, derived query hoặc `DatabaseClient` |
| Aggregate mapping | Không phải trọng tâm duy nhất | Là trọng tâm thiết kế của Spring Data Relational |

Spring Data R2DBC là giải pháp truy cập dữ liệu quan hệ theo kiểu reactive, không phải bản sao reactive của toàn bộ ORM JPA. Việc chọn R2DBC cần dựa trên mô hình truy cập dữ liệu và yêu cầu non-blocking của ứng dụng, đồng thời chấp nhận rằng một số tiện ích ORM phải được biểu diễn tường minh hơn.

## 12. Những lỗi thường gặp khi chuyển từ JPA sang R2DBC

| Lỗi | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| Giữ `@Inheritance` và mong subtype tự được lưu | Annotation thuộc JPA ORM | Thiết kế bảng và discriminator tường minh |
| Dùng `@MappedSuperclass` của JPA cho entity R2DBC | Spring Data Relational không dùng annotation đó làm mapping metadata | Dùng lớp Java cha thông thường để tái sử dụng property, rồi kiểm tra mapping |
| Mong repository kiểu cha tự đọc mọi subtype | Không có polymorphic mapping tự động như JPA | Đọc record/discriminator và tự map subtype |
| Mong framework tự join bảng cha/con | Kế thừa Java không tạo quan hệ SQL | Dùng SQL join và map projection rõ ràng |
| Chuyển JPQL nguyên trạng sang `@Query` | `@Query` của R2DBC làm việc với SQL | Viết SQL phù hợp schema và dialect |
| Mong getter tự tải association lazy | R2DBC không dùng lazy proxy JPA | Tạo publisher truy vấn quan hệ và kết hợp kết quả |
| Dùng chung một base repository cho các subtype có schema khác nhau | Các bảng có thể có định danh và thuộc tính riêng | Dùng repository theo entity/table cụ thể |
| Cho rằng lớp cha luôn là một bảng | Java inheritance và table inheritance là hai khái niệm | Khai báo rõ `@Table` và thiết kế schema |

## 13. Quy trình chọn mô hình

Khi thiết kế một hệ thống có nhiều loại entity chia sẻ thuộc tính, hãy bắt đầu từ cấu trúc dữ liệu và vòng đời nghiệp vụ:

1. Xác định các loại đối tượng có thật sự là các subtype của cùng một khái niệm domain hay chỉ tình cờ chia sẻ vài trường.
2. Nếu chỉ cần tái sử dụng property như audit fields, cân nhắc một lớp Java cha thông thường.
3. Nếu nhóm dữ liệu là value object có cùng vòng đời với entity, cân nhắc composition và `@Embedded`.
4. Nếu subtype cần nằm trong một bảng, thiết kế cột discriminator và mapping record tường minh.
5. Nếu subtype có bảng chi tiết riêng, dùng entity/repository riêng và truy vấn join rõ ràng.
6. Nếu mỗi loại có bảng và vòng đời riêng, dùng entity độc lập; chia sẻ interface hoặc hành vi ở tầng domain/service.
7. Kiểm tra mapping metadata, SQL được sinh và constructor materialization bằng integration test.
8. Bao bọc các thao tác ghi nhiều bảng trong reactive transaction khi cần tính nguyên tử.
9. Không dùng annotation JPA làm cấu hình cho Spring Data R2DBC.

## 14. Ghi nhớ

- Kế thừa lớp Java giúp tái sử dụng thuộc tính và hành vi; nó không tự tạo chiến lược kế thừa bảng.
- Spring Data Relational ánh xạ entity cụ thể vào bảng và dùng mapping metadata của entity cùng các property được nhận diện.
- Có thể dùng lớp Java cha thông thường để chia sẻ property, nhưng không nên hiểu đó là `@MappedSuperclass` hay `@Inheritance` của JPA.
- Spring Data R2DBC không cung cấp tự động các chiến lược `SINGLE_TABLE`, `JOINED` và `TABLE_PER_CLASS` của JPA.
- Discriminator, join và truy vấn đa hình cần được thiết kế và xử lý tường minh.
- Composition và `@Embedded` phù hợp để gom value object; `@MappedCollection` mô tả phần tử thuộc aggregate, không phải inheritance.
- Mỗi entity cần dùng đúng annotation của Spring Data Relational, không dựa vào `jakarta.persistence.*`.
- Khi chuyển từ JPA, cần thay đổi cách nghĩ về persistence context, lazy loading, dirty checking và JPQL.
- Hãy chọn mô hình dựa trên schema, ranh giới aggregate và truy vấn thực tế; xác nhận bằng integration test trên database mục tiêu.



