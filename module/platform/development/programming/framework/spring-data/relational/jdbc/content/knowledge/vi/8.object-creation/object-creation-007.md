# Ảnh hưởng của kế thừa, thuộc tính bị che khuất và Lombok đến ánh xạ

Trong **Spring Data Relational JDBC**, Spring ánh xạ một đối tượng Java thành dữ liệu quan hệ dựa trên metadata của kiểu, constructor và các persistent properties. Vì vậy, cấu trúc class ảnh hưởng trực tiếp đến việc framework tìm thấy thuộc tính nào, đọc/ghi giá trị ra sao và tạo SQL với tên cột nào.

Ba chủ đề thường gây nhầm lẫn:

- **Kế thừa (inheritance):** thuộc tính khai báo ở superclass có thể trở thành một phần trạng thái được ánh xạ của kiểu entity cụ thể. Điều đó không đồng nghĩa Spring Data JDBC hỗ trợ đầy đủ các chiến lược kế thừa bảng như JPA.
- **Thuộc tính bị che khuất (field hiding):** subclass khai báo một field cùng tên với field của superclass. Java giữ hai vùng lưu trữ riêng, nhưng metadata ánh xạ không có một cách tự nhiên, ổn định để coi cả hai là hai cột khác nhau.
- **Lombok:** annotation có thể sinh getter/setter, constructor, builder, equals/hashCode và toString. Những thành phần được sinh có thể tác động tới cách Spring Data tạo object và truy cập property, dù Lombok tự nó không định nghĩa schema SQL.

Hiểu các khác biệt này giúp thiết kế entity dễ dự đoán, tránh lỗi khởi tạo và tránh việc dữ liệu bị đọc/ghi qua một property khác với dự định.

## 1. Spring Data JDBC ánh xạ những gì từ một class?

Spring Data JDBC sử dụng mapping metadata của Spring Data Relational. Metadata mô tả:

| Thành phần | Ý nghĩa đối với mapping |
| --- | --- |
| Persistent entity | Kiểu Java được lưu/đọc như một relational entity, thường gắn với một bảng |
| Persistent property | Thuộc tính được xem là dữ liệu cần ánh xạ |
| Constructor dùng để tạo object | Cách framework tạo instance khi đọc một hàng |
| Property accessor | Cách đọc hoặc gán giá trị vào object |
| Mapping annotation | Tên bảng/cột, khóa, quan hệ và các tùy chọn ánh xạ |

Ví dụ đơn giản:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    private String email;

    protected Customer() {
    }

    public Customer(String fullName, String email) {
        this.fullName = fullName;
        this.email = email;
    }
}
```

Trong ví dụ này:

- `@Table("customer")` chỉ định bảng.
- `@Id` đánh dấu khóa định danh.
- `@Column("full_name")` chỉ định tên cột khác với tên property Java `fullName`.
- `email` được ánh xạ theo naming strategy nếu không có annotation đổi tên.
- Constructor không tham số được giữ ở mức `protected` để hỗ trợ các tình huống tạo object cần thiết; constructor được Spring Data lựa chọn còn phụ thuộc quy tắc object creation và các constructor hiện diện.

Spring Data JDBC không đơn giản quét mọi method trong class rồi biến chúng thành cột. Nó xây dựng metadata từ kiểu, field/property, annotation và quy tắc mapping. Các method tính toán, method tiện ích hoặc property được đánh dấu transient không tự động trở thành cột.

## 2. Kế thừa Java và giới hạn của ánh xạ quan hệ

Java cho phép class kế thừa field và method từ superclass:

```java
import java.time.Instant;

public abstract class AuditedRecord {
    private Instant createdAt;
    private Instant updatedAt;

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}

@Table("customer")
public class Customer extends AuditedRecord {
    @Id
    private Long id;

    private String email;
}
```

Về mặt Java, `Customer` có thể đọc và sử dụng `createdAt`, `updatedAt` được kế thừa. Spring Data mapping metadata có thể xem các persistent properties kế thừa là một phần trạng thái của kiểu concrete, tùy quy tắc truy cập và metadata của framework. Nếu các property đó được xem là persistent, schema của bảng concrete phải có các cột tương ứng.

Tuy nhiên, cần phân biệt **kế thừa code/property trong Java** với **chiến lược kế thừa entity trong ORM**:

- Kế thừa Java giúp tái sử dụng field và behavior.
- Kế thừa relational/ORM là quy tắc xác định dữ liệu của nhiều subtype được lưu trong một bảng, nhiều bảng nối nhau hay mỗi subtype một bảng.

Spring Data JDBC không cung cấp mô hình kế thừa entity kiểu JPA với các chiến lược `SINGLE_TABLE`, `JOINED`, `TABLE_PER_CLASS` và discriminator tự động. Không nên kỳ vọng chỉ cần tạo abstract superclass và các subclass là framework tự thiết kế schema, tự join bảng hoặc tự khôi phục subtype dựa trên discriminator.

Nếu dùng superclass để chia sẻ thuộc tính kỹ thuật như thời điểm tạo/cập nhật, mỗi aggregate root cụ thể vẫn cần bảng và schema tường minh. Nếu mô hình nghiệp vụ có nhiều biến thể với cấu trúc khác nhau, cân nhắc composition, các aggregate root riêng hoặc mapping/query tùy chỉnh có chủ đích.

### 2.1. Dùng superclass cho thuộc tính dùng chung

Ví dụ, nhiều bảng có thể cùng chứa cột audit:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE supplier (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

Superclass có thể giữ field audit chung:

```java
import java.time.Instant;

public abstract class AuditedRecord {
    private Instant createdAt;
    private Instant updatedAt;

    protected AuditedRecord() {
    }

    protected AuditedRecord(Instant createdAt, Instant updatedAt) {
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
    }
}
```

Các class concrete khai báo bảng riêng và kế thừa:

```java
@Table("customer")
public class Customer extends AuditedRecord {
    @Id
    private Long id;
    private String email;
}

@Table("supplier")
public class Supplier extends AuditedRecord {
    @Id
    private Long id;
    private String companyName;
}
```

Đây là **tái sử dụng cấu trúc Java**. DDL của từng bảng vẫn phải có các cột audit phù hợp; superclass không tự chạy câu `ALTER TABLE` hay tạo schema.

Spring Data JDBC cũng cung cấp auditing qua các annotation như `@CreatedDate` và `@LastModifiedDate` khi bật cấu hình auditing phù hợp. Nếu dùng auditing, hãy cấu hình callback/auditing infrastructure đúng cách thay vì kỳ vọng field có tên `createdAt` sẽ tự được điền chỉ vì nó nằm trong superclass.

### 2.2. Khi cần mô hình nhiều subtype

Giả sử nghiệp vụ có hai loại phương thức thanh toán:

```java
abstract class PaymentMethod {
    private String displayName;
}

class CardPayment extends PaymentMethod {
    private String lastFourDigits;
}

class BankTransfer extends PaymentMethod {
    private String bankCode;
}
```

Đừng mặc định rằng Spring Data JDBC sẽ tự:

1. Tạo bảng duy nhất chứa cả `lastFourDigits` và `bankCode`.
2. Tạo cột discriminator để ghi loại subtype.
3. Đọc discriminator rồi tạo `CardPayment` hoặc `BankTransfer` khi query một `PaymentMethod`.

Đó là các hành vi thường gắn với chiến lược inheritance của ORM. Trong Spring Data JDBC, hãy xác định rõ relational model: ví dụ một aggregate `Payment` với các thuộc tính phù hợp, hoặc các bảng/aggregate riêng cùng quan hệ rõ ràng. Nếu cần polymorphic read model, có thể viết query/projection/converter tùy chỉnh để quyết định loại Java một cách tường minh.

Composition thường thể hiện quan hệ "có một" rõ hơn:

```java
public record PaymentDetails(
        String method,
        String providerReference,
        String maskedAccount
) {}

@Table("payment")
public record Payment(
        @Id Long id,
        Long orderId,
        PaymentDetails details
) {}
```

Đây chỉ là phác thảo mô hình Java. Để lưu `PaymentDetails`, cần chọn mapping phù hợp với schema, chẳng hạn embedded value object hoặc các cột được khai báo tường minh; không giả định mọi object lồng nhau tự động được lưu vào cùng một hàng. Spring Data JDBC có các annotation relational như `@Embedded` cho value object và `@MappedCollection` cho thành phần thuộc aggregate; chọn đúng cấu trúc theo ý nghĩa dữ liệu.

## 3. Field hiding: cùng tên nhưng hai vùng lưu trữ

Trong Java, field không được override như method. Nếu subclass khai báo field trùng tên với superclass, field của subclass **che khuất** field của superclass:

```java
class BaseRecord {
    protected String status = "BASE";

    String baseStatus() {
        return status;
    }
}

class OrderRecord extends BaseRecord {
    private String status = "ORDER";

    String orderStatus() {
        return status;
    }
}
```

Hai field `status` là hai biến độc lập. Khi truy cập field trực tiếp, tên nào được chọn phụ thuộc kiểu khai báo của reference và quyền truy cập; khi gọi method, quy tắc override/dispatch lại khác.

Ví dụ:

```java
OrderRecord order = new OrderRecord();
System.out.println(order.orderStatus()); // Field của OrderRecord: ORDER
System.out.println(order.baseStatus());  // Field của BaseRecord: BASE
```

Hai method chỉ giúp quan sát hai vùng lưu trữ trong ví dụ; chúng không thay đổi quy tắc Java. Điều cốt lõi là Java lưu hai field, chứ không gộp chúng thành một property duy nhất.

### 3.1. Vì sao field hiding nguy hiểm với mapping?

Spring Data cần xây dựng tập persistent properties cho kiểu entity. Nhưng hai field cùng tên trong một hierarchy tạo ra câu hỏi mơ hồ:

- `status` ở superclass là cột nào?
- `status` ở subclass là cột nào?
- Getter `getStatus()` đọc field nào?
- Setter `setStatus(...)` ghi field nào?
- Nếu cả hai được ánh xạ, framework sẽ chọn tên cột và property metadata nào?

Kết quả cụ thể có thể phụ thuộc mapping metadata, access strategy và phiên bản framework. Không nên dựa vào thứ tự reflection hoặc kỳ vọng framework tự phân biệt hai field cùng tên. Một property name bị trùng trong hierarchy không phải một cách thiết kế mapping rõ ràng.

Ví dụ không nên dùng:

```java
abstract class BaseOrder {
    private String status;
}

@Table("customer_order")
class CustomerOrder extends BaseOrder {
    private String status; // Che khuất field cùng tên
}
```

Ngay cả khi gắn `@Column` với hai field, tên property trùng vẫn làm metadata/access khó hiểu và dễ tạo mapping ngoài ý muốn. Annotation không biến hai field Java thành một mô hình kế thừa quan hệ được hỗ trợ.

### 3.2. Đổi tên để thể hiện đúng ý nghĩa

Nếu hai trạng thái thực sự khác nhau, hãy đặt tên khác nhau và cột khác nhau:

```java
abstract class BaseOrder {
    @Column("lifecycle_status")
    private String lifecycleStatus;
}

@Table("customer_order")
class CustomerOrder extends BaseOrder {
    @Column("approval_status")
    private String approvalStatus;
}
```

DDL:

```sql
CREATE TABLE customer_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    lifecycle_status VARCHAR(30) NOT NULL,
    approval_status VARCHAR(30) NOT NULL
);
```

Tên property diễn tả hai khái niệm nghiệp vụ khác nhau; tên cột tường minh giúp schema dễ đọc. Nếu subclass chỉ muốn **thay đổi cách biểu diễn** cùng một trạng thái, hãy override method phù hợp hoặc dùng converter/property access có chủ đích, không tạo field thứ hai cùng tên.

### 3.3. Override getter không giống field hiding

Method có thể được override:

```java
class BaseRecord {
    protected String status;

    public String getStatus() {
        return status;
    }
}

class OrderRecord extends BaseRecord {
    @Override
    public String getStatus() {
        return status == null ? "NEW" : status;
    }
}
```

Đây là một method override hợp lệ. Tuy nhiên, nếu mapping đang dùng field access thì framework có thể đọc field trực tiếp và không chạy logic của getter. Nếu mapping dùng property access, getter có thể là đường đọc dữ liệu. Vì vậy, đừng viết getter có side effect, giá trị phụ thuộc thời điểm hoặc trả về giá trị khác dữ liệu cần lưu rồi giả định mọi access strategy sẽ quan sát giống nhau.

## 4. Field access và property access

Spring Data mapping hỗ trợ truy cập giá trị thông qua field hoặc JavaBean property. Mặc định, mapping infrastructure của Spring Data thường sử dụng **field access**. Có thể chọn property access bằng `@AccessType(AccessType.Type.PROPERTY)` khi thật sự cần getter/setter làm đường truy cập.

Ví dụ chọn property access:

```java
import org.springframework.data.annotation.AccessType;

@AccessType(AccessType.Type.PROPERTY)
@Table("customer")
public class Customer {
    private Long id;
    private String email;

    @Id
    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email == null ? null : email.trim();
    }
}
```

Khi property access được chọn, getter/setter là một phần hợp đồng mapping. Setter trong ví dụ chuẩn hóa chuỗi; vì thế giá trị sau khi được populate có thể khác dữ liệu thô ban đầu. Hãy chỉ làm việc này nếu đó là quy tắc domain mong muốn.

Với field access, framework có thể đọc/ghi field trực tiếp mà không gọi getter/setter. Điều đó hữu ích khi getter chỉ là logic hiển thị hoặc setter chứa side effect không nên chạy lúc đọc dữ liệu. Tuy nhiên, nếu muốn một property bị bỏ qua khỏi mapping, phải dùng annotation transient phù hợp chứ không chỉ ẩn getter.

`@AccessType` nên được dùng có chủ đích và nhất quán. Khi thay đổi access strategy, hãy kiểm tra lại property nào được ánh xạ, annotation nằm trên field hay getter nào và constructor nào đang tạo object.

## 5. Lombok tác động tới object mapping như thế nào?

Lombok là annotation processor tạo mã Java khi biên dịch. Nó có thể sinh method/constructor mà không xuất hiện trực tiếp trong source code. Spring Data làm việc với class đã biên dịch và mapping metadata, vì vậy cần hiểu Lombok thực sự sinh ra gì.

| Lombok annotation | Mã thường được sinh | Ảnh hưởng có thể có với Spring Data |
| --- | --- | --- |
| `@Getter` | Getter | Có ý nghĩa nếu property access hoặc code ứng dụng cần getter |
| `@Setter` | Setter | Có ý nghĩa nếu property access; với field access, setter không nhất thiết được gọi |
| `@Data` | Getter, setter, `equals/hashCode`, `toString` và required-args constructor | Có thể thay đổi constructor khả dụng và hành vi method; không tự định nghĩa mapping SQL |
| `@NoArgsConstructor` | Constructor không tham số | Thêm một lựa chọn tạo object; cần xem quy tắc chọn persistence constructor |
| `@AllArgsConstructor` | Constructor nhận tất cả field | Có thể tạo thêm constructor và làm lựa chọn constructor trở nên mơ hồ nếu còn constructor khác |
| `@RequiredArgsConstructor` | Constructor cho field final và field `@NonNull` chưa khởi tạo | Có thể là constructor phù hợp cho immutable object, nhưng phải kiểm tra tên/thứ tự tham số |
| `@Builder` | API builder | Không có nghĩa Spring Data JDBC sẽ tự dùng builder để khôi phục entity |
| `@SuperBuilder` | Builder hỗ trợ hierarchy Lombok | Giúp tạo object bằng builder trong code ứng dụng; không tạo relational inheritance strategy |
| `@Value` | Class/field bất biến, getter và constructor | Có thể dùng với constructor-based mapping nếu metadata constructor phù hợp |
| `@With` | Phương thức tạo bản sao với một property thay đổi | Có thể hữu ích cho immutable object; phải kiểm tra cách property accessor dùng wither |

Lombok không thay thế `@Table`, `@Column`, `@Id` hoặc các annotation mapping. Một class có `@Data` vẫn cần metadata relational phù hợp với schema.

### 5.1. Getter/setter do Lombok sinh

Ví dụ:

```java
@Getter
@Setter
@Table("customer")
public class Customer {
    @Id
    private Long id;

    @Column("full_name")
    private String fullName;
}
```

Với field access mặc định, Lombok chỉ thêm method để code Java gọi; sự hiện diện của getter/setter không tự động biến cột thành một tên SQL khác. Nếu class chọn property access, getter/setter được sinh trở thành một phần của cách framework truy cập giá trị.

Chú ý các tùy chọn như `@Accessors(fluent = true)`: chúng có thể sinh method dạng `email()`/`email(value)` thay vì JavaBean `getEmail()`/`setEmail(...)`. Với property access, tên method không theo quy ước bean có thể khiến property không được phát hiện như mong đợi. Nếu cần property access, dùng accessor theo quy ước hoặc xác nhận mapping metadata thực tế.

### 5.2. Constructor sinh tự động có thể đổi cách Spring tạo object

Spring Data phải tạo instance trước khi populate các property còn lại. Nó chọn persistence constructor theo quy tắc object mapping của Spring Data:

- Constructor duy nhất có thể được chọn tự động.
- Khi có nhiều constructor, cần chỉ rõ constructor dùng để persistence bằng `@PersistenceCreator` nếu framework không thể lựa chọn rõ ràng.
- Với constructor được chọn, tên tham số phải khớp persistent property để framework truyền đúng giá trị.
- Immutable object cần constructor nhận các giá trị cần thiết; mutable object có thể được populate qua accessor sau khi khởi tạo.

Ví dụ class bất biến với constructor tường minh:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {
    @Id
    private final Long id;
    private final String email;

    @PersistenceCreator
    public Customer(Long id, String email) {
        this.id = id;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

Nếu Lombok thêm constructor khác, hãy kiểm tra constructor được Spring Data lựa chọn. Ví dụ `@NoArgsConstructor` cộng `@AllArgsConstructor` tạo hai constructor; không nên dựa vào thứ tự annotation để đoán constructor nào được dùng. Có thể giữ constructor persistence tường minh và đánh dấu `@PersistenceCreator`.

### 5.3. `@Data` không phải annotation mapping

`@Data` là shortcut của Lombok cho một nhóm tính năng:

- Getter cho các field.
- Setter cho các field không final.
- `equals` và `hashCode` dựa trên field.
- `toString`.
- Required-args constructor.

Nó **không** tự động:

- Tạo bảng hoặc cột.
- Quyết định tên SQL theo schema.
- Chọn khóa chính nếu thiếu `@Id`.
- Tạo quan hệ aggregate hoặc foreign key.
- Làm Spring Data JDBC sử dụng builder.

Đặc biệt, `equals/hashCode/toString` được sinh trên mọi field phù hợp có thể kéo theo quan hệ/collection lớn, đệ quy qua object graph hoặc in dữ liệu nhạy cảm. Đây không phải quy tắc SQL mapping, nhưng có thể gây vấn đề khi log entity, so sánh object hoặc dùng entity trong collection. Với aggregate phức tạp, cân nhắc viết các method này có chủ đích thay vì dùng `@Data` mặc định.

### 5.4. `@Builder` và `@SuperBuilder` không điều khiển Spring Data

Ví dụ:

```java
@Getter
@Builder
@Table("customer")
public class Customer {
    @Id
    private Long id;
    private String email;
}
```

Code ứng dụng có thể tạo instance:

```java
Customer customer = Customer.builder()
        .email("an@example.test")
        .build();
```

Builder là API khởi tạo tiện lợi cho người viết code. Spring Data JDBC không mặc định gọi `Customer.builder()` rồi gán từng property chỉ vì class có `@Builder`. Khi đọc hàng từ database, Spring vẫn sử dụng constructor/property accessor theo mapping infrastructure.

`@SuperBuilder` cho phép Lombok tạo builder hỗ trợ class hierarchy khi các superclass liên quan cũng được cấu hình phù hợp. Điều đó chỉ giải quyết trải nghiệm khởi tạo object trong Java; nó không tạo discriminator, join hoặc bảng cho từng subclass trong database.

### 5.5. Immutable class và `@Value`

Immutable entity có thể phù hợp nếu mọi dữ liệu cần thiết được truyền qua constructor:

```java
import lombok.Value;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Value
@Table("customer")
public class Customer {
    @Id
    Long id;
    String email;
}
```

`@Value` tạo class immutable theo quy ước Lombok, gồm field final, getter và constructor. Spring Data có thể dùng constructor-based materialization khi tên tham số constructor ánh xạ được với persistent properties. Hãy kiểm tra cấu hình biên dịch và metadata tham số constructor trong dự án; nếu có nhiều constructor hoặc constructor do Lombok sinh không được chọn rõ ràng, dùng constructor tường minh và `@PersistenceCreator`.

Khi database tạo ID mới, một immutable object có thể cần được tạo lại với ID được sinh. Spring Data có hỗ trợ các cơ chế cập nhật immutable object trong mapping infrastructure, nhưng thiết kế cụ thể phải phù hợp phiên bản framework và kiểu constructor/wither. Không nên tự giả định rằng một builder bất kỳ sẽ được gọi để gán ID.

## 6. Kế thừa kết hợp Lombok: các bẫy phổ biến

Khi dùng Lombok trên cả superclass và subclass, nhiều constructor và accessor có thể được sinh mà source code không thể hiện đầy đủ:

```java
@Getter
@NoArgsConstructor
abstract class BaseRecord {
    private String status;
}

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Table("customer_order")
class CustomerOrder extends BaseRecord {
    @Id
    private Long id;
    private String orderNumber;
}
```

Các điểm cần xem xét:

1. Constructor của subclass phải có khả năng gọi constructor hợp lệ của superclass. Nếu superclass chỉ có constructor nhận tham số, constructor không tham số do Lombok sinh ở subclass có thể không biên dịch được nếu không có lời gọi phù hợp.
2. Nếu superclass và subclass cùng khai báo field tên `status`, field hiding vẫn xảy ra dù Lombok sinh getter/setter.
3. `@AllArgsConstructor` trên subclass không tự động có nghĩa nó nhận mọi field kế thừa theo cách bạn mong muốn; constructor được sinh dựa trên field của class được annotate. Với hierarchy, hãy xem mã thực tế sau annotation processing.
4. `@SuperBuilder` có thể hỗ trợ builder qua hierarchy, nhưng không giải quyết việc Spring Data ánh xạ các field bị che khuất.
5. Nhiều constructor có thể làm persistence constructor không rõ ràng; đánh dấu constructor phù hợp.

Nếu cần kiểm tra Lombok thực sự sinh mã gì, có thể dùng tính năng *delombok* của Lombok hoặc xem mã bytecode/decompiled class trong IDE. Hãy xác nhận constructor, getter/setter, visibility và tên tham số thay vì chỉ suy đoán từ annotation.

## 7. Thiết kế entity dễ ánh xạ

Một số quy tắc thực hành:

### 7.1. Dùng inheritance có giới hạn

Kế thừa phù hợp khi superclass đại diện các thuộc tính thực sự chung, ổn định và các bảng concrete có thể chứa những cột đó. Ví dụ audit metadata có thể dùng chung. Không dùng hierarchy chỉ để mô phỏng các chiến lược ORM mà Spring Data JDBC không tự cung cấp.

Nếu superclass có nhiều trạng thái chỉ một vài subtype sử dụng, composition hoặc các entity riêng có thể rõ ràng hơn.

### 7.2. Không che khuất persistent field

Tránh:

```java
class Parent {
    private String code;
}

class Child extends Parent {
    private String code;
}
```

Nếu là hai khái niệm, đổi thành `parentCode` và `childCode` rồi ánh xạ tới hai cột riêng. Nếu chỉ muốn thay đổi behavior, override method hoặc dùng property access có chủ đích; không tạo field trùng tên.

### 7.3. Khai báo mapping quan trọng tường minh

Với schema có quy ước đặc biệt, dùng `@Table`, `@Column` và `@Id` để thể hiện tên bảng/cột/khóa. Không dựa vào Lombok hoặc tên getter để suy ra tên SQL. Nếu có quan hệ aggregate, khai báo mapping collection/back-reference rõ ràng.

### 7.4. Giữ constructor persistence ổn định

Với class mutable, giữ constructor đơn giản và các accessor phù hợp. Với immutable class, xác định một constructor persistence rõ ràng, dùng `@PersistenceCreator` khi cần và bảo đảm tên tham số ánh xạ được tới property. Khi thêm Lombok constructor annotation, kiểm tra lại constructor selection.

### 7.5. Dùng Lombok vừa đủ

`@Getter`/`@Setter` có thể giảm boilerplate. Với entity có invariant, tránh setter công khai cho mọi field chỉ vì tiện. Với `@Data`, cân nhắc hệ quả của equals/hashCode/toString. Với builder, nhớ rằng builder phục vụ code ứng dụng, không phải mapping contract.

## 8. Ví dụ tổng hợp: entity có audit superclass

Một thiết kế đơn giản có thể dùng superclass cho audit fields, field names riêng biệt và constructor rõ ràng:

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

public abstract class AuditedRecord {
    @Column("created_at")
    private final Instant createdAt;

    @Column("updated_at")
    private final Instant updatedAt;

    protected AuditedRecord(Instant createdAt, Instant updatedAt) {
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}

@Table("customer")
public class Customer extends AuditedRecord {
    @Id
    private final Long id;

    @Column("email_address")
    private final String email;

    @PersistenceCreator
    public Customer(Long id, String email,
                    Instant createdAt, Instant updatedAt) {
        super(createdAt, updatedAt);
        this.id = id;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

Schema PostgreSQL tương ứng:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email_address VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

Ví dụ minh họa việc gom audit fields vào superclass và khai báo constructor của concrete class nhận đủ property. Khi áp dụng trong dự án, cần xác nhận mapping metadata của phiên bản Spring Data JDBC đang dùng nhận diện các inherited properties và constructor parameter như mong muốn. Nếu dùng auditing tự động, bổ sung cấu hình auditing/callback phù hợp; ví dụ này không tự tạo giá trị timestamp.

Nếu Lombok được thêm, có thể dùng `@Getter` để giảm getter, nhưng vẫn nên giữ constructor persistence tường minh khi hierarchy và immutable fields làm việc lựa chọn constructor trở nên quan trọng. Không cần thêm `@Data` chỉ để sinh getter.

## 9. Điều tra lỗi mapping liên quan inheritance/Lombok

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Thiếu cột audit khi đọc entity | Superclass property được mapping nhưng DDL không có cột tương ứng | Kiểm tra inherited persistent properties và schema |
| Giá trị property không như mong đợi | Field hiding hoặc getter/setter truy cập field khác | Kiểm tra cả superclass/subclass và access strategy |
| Mapping có một giá trị `status` dù code có hai field | Trùng property name trong hierarchy | Loại bỏ field hiding; đặt tên property/cột riêng |
| Không tạo được entity khi query | Constructor không phù hợp, constructor private/protected không đúng hoặc nhiều constructor không rõ ràng | Kiểm tra constructor và `@PersistenceCreator` |
| Giá trị constructor bị đảo hoặc null | Tên/thứ tự tham số không khớp property hoặc parameter metadata không khả dụng | Kiểm tra tên tham số được biên dịch và persistence constructor |
| Thêm `@NoArgsConstructor` làm behavior thay đổi | Framework chọn đường tạo object khác hoặc final field bị khởi tạo mặc định | Kiểm tra constructor selection và trạng thái sau populate |
| `@Builder` hoạt động trong service nhưng đọc DB lỗi | Builder không được Spring Data dùng tự động | Xác định constructor/accessor mapping thực tế |
| Getter Lombok không được gọi | Mapping dùng field access thay vì property access | Kiểm tra `@AccessType` và mapping metadata |
| Property biến mất sau `@Accessors(fluent = true)` | Accessor không theo JavaBean convention trong property access | Dùng accessor chuẩn hoặc field access |
| `toString()` gây log quá dài/đệ quy | `@Data` sinh toString trên nhiều field/quan hệ | Viết toString có kiểm soát hoặc dùng `@ToString.Exclude` |

Khi điều tra, hãy kiểm tra theo thứ tự:

1. **Class thực tế sau Lombok:** field, constructor, getter/setter và tham số được sinh.
2. **Mapping metadata:** persistent properties, tên cột, access type và constructor được chọn.
3. **Schema:** bảng/cột thật, nullability, kiểu dữ liệu, khóa.
4. **SQL thực thi:** tên cột nào được query/insert/update và exception gốc từ JDBC.
5. **Phiên bản framework:** xác nhận behavior với đúng phiên bản Spring Data Relational trong dependency tree.

Đừng chỉ nhìn source code có annotation rồi kết luận framework sẽ sử dụng một constructor hoặc getter cụ thể.

## 10. Bài tập thực hành

**Bài 1 — Kế thừa audit fields.** Tạo abstract class có `createdAt` và `updatedAt`, cho `Customer` kế thừa, tạo bảng có các cột tương ứng và kiểm tra đọc/ghi bằng repository. Thử bỏ một cột khỏi schema để quan sát lỗi.

**Bài 2 — Field hiding.** Tạo superclass và subclass cùng có field `status`. Quan sát giá trị qua reference của từng kiểu và getter. Sau đó đổi tên thành `lifecycleStatus` và `approvalStatus`, ánh xạ thành hai cột riêng.

**Bài 3 — Constructor do Lombok sinh.** Thử `@NoArgsConstructor`, `@AllArgsConstructor` và `@RequiredArgsConstructor` trên một entity. Dùng delombok hoặc IDE để xem constructor thực tế; đánh dấu persistence constructor tường minh khi cần.

**Bài 4 — Builder.** Tạo entity có `@Builder` và dùng builder trong test/service. Sau đó đọc cùng entity qua repository để phân biệt builder API với cơ chế object creation của Spring Data.

**Bài 5 — Field access và property access.** So sánh getter/setter bình thường với `@AccessType(AccessType.Type.PROPERTY)`; thêm setter chuẩn hóa chuỗi và quan sát giá trị sau khi đọc từ database. Đảm bảo behavior mong muốn không phụ thuộc ngầm vào access strategy.

## 11. Điều cần ghi nhớ

Java inheritance có thể giúp chia sẻ thuộc tính và behavior, nhưng không tự tạo relational inheritance strategy. Field hiding tạo ra hai vùng lưu trữ cùng tên và khiến mapping mơ hồ; hãy đặt tên property riêng. Lombok chỉ sinh mã Java: getter/setter, constructor và builder có thể ảnh hưởng đường truy cập hoặc object creation, nhưng không thay thế metadata SQL. Khi entity có hierarchy hoặc immutable fields, constructor persistence và access strategy phải được xác định rõ, đồng thời schema phải khớp các persistent properties thực tế.

### Tài liệu tham khảo

- [Spring Data Relational — Object Mapping Fundamentals](https://docs.spring.io/spring-data/relational/reference/object-mapping.html): object creation, property population, constructor và accessor.
- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): mapping entity, bảng/cột và quan hệ trong Spring Data JDBC.
- [Project Lombok — @Data](https://projectlombok.org/features/Data): các method và constructor được sinh bởi `@Data`.
- [Project Lombok — Constructors](https://projectlombok.org/features/constructor): quy tắc các annotation constructor.
- [Project Lombok — @Builder](https://projectlombok.org/features/Builder): builder generation.
- [Project Lombok — @SuperBuilder](https://projectlombok.org/features/experimental/SuperBuilder): builder cho hierarchy.
