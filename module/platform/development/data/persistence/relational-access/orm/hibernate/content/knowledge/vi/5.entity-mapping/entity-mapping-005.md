# Thuộc tính không lưu bằng @Transient và từ khóa transient của Java

Trong Hibernate/JPA, một entity có thể chứa các trường phục vụ giao diện, tính toán tạm thời, bộ đệm hoặc xử lý nghiệp vụ nhưng **không cần lưu vào bảng**. Hai cách viết trông gần giống nhau là annotation `@Transient` và từ khóa `transient` của Java:

~~~java
@Transient
private String displayLabel;

private transient String workingNote;
~~~

Ở những entity ánh xạ theo field, cả hai trường trên thường đều không được ORM ghi xuống database. Tuy nhiên, **ý nghĩa gốc của hai cách khác nhau**: `@Transient` điều khiển ánh xạ JPA, còn `transient` là từ khóa của ngôn ngữ Java điều khiển cơ chế Java object serialization. Sự khác biệt trở nên quan trọng khi entity sử dụng property access, khi truyền đối tượng qua serialization hoặc khi kết hợp Hibernate với JSON API.

Bài học giải thích cách chọn đúng, các tình huống dễ nhầm và cách quan sát hành vi qua ví dụ.

## 1. Trước hết: “không lưu” vào đâu?

Một đối tượng Java có thể đi qua nhiều cơ chế độc lập:

1. **ORM persistence:** Hibernate/JPA ánh xạ thuộc tính entity thành các cột hoặc quan hệ của cơ sở dữ liệu.
2. **Java object serialization:** `ObjectOutputStream` ghi trạng thái đối tượng thành luồng byte nếu lớp hỗ trợ `Serializable`.
3. **JSON serialization:** Jackson hoặc thư viện khác chuyển đối tượng thành JSON cho API.
4. **Bộ nhớ Java:** một đối tượng tồn tại trên heap, gồm cả các trường chỉ phục vụ tính toán trong quá trình chạy.

`@Transient` và `transient` ảnh hưởng đến các cơ chế này theo cách khác nhau. Một trường không được Hibernate lưu xuống bảng vẫn có thể nằm trong bộ nhớ, xuất hiện trong JSON hoặc được Java serialization ghi vào byte stream.

### 1.1. `@Transient` thuộc Jakarta Persistence

Với Jakarta Persistence hiện đại:

~~~java
import jakarta.persistence.Transient;
~~~

Ở dự án JPA đời cũ dùng namespace Java EE:

~~~java
import javax.persistence.Transient;
~~~

Hai import phục vụ các thế hệ API khác nhau; cần sử dụng namespace phù hợp với phiên bản framework đang chạy. Không đưa cả hai loại annotation vào cùng một mô hình entity.

Annotation này nói với JPA rằng **thuộc tính được đánh dấu không phải thuộc tính persistent**. Trong chế độ access tương ứng, Hibernate sẽ bỏ thuộc tính đó khỏi mô hình ánh xạ entity:

- Không tạo ánh xạ cột cho thuộc tính ấy.
- Không đọc/ghi giá trị ấy khi load/insert/update entity.
- Không dirty-check thay đổi của riêng thuộc tính ấy để sinh SQL cập nhật.
- Không coi thuộc tính ấy là một đường dẫn persistent dùng trong JPQL/Criteria.

`@Transient` không có chức năng xóa một cột đã tồn tại trong database và không tự xóa giá trị đang nằm trong Java object.

### 1.2. `transient` là từ khóa của Java

`transient` được viết ngay trong khai báo field, giống `private` hoặc `final`:

~~~java
private transient String temporaryToken;
~~~

Nó hướng dẫn cơ chế **Java serialization mặc định** không ghi field vào stream khi đối tượng được serialize bằng `ObjectOutputStream`. Đây không phải annotation JPA và không cần `import`.

Trong entity dùng **field access**, JPA cũng mặc định bỏ qua field có modifier Java `transient`. Nhưng nếu entity dùng **property access**, annotation ở getter mới quyết định ánh xạ thuộc tính; một backing field Java `transient` không nhất thiết khiến getter tương ứng bị bỏ qua.

Vì thế, quy tắc “`transient` luôn tương đương `@Transient` trong JPA” là không chính xác cho mọi kiểu access.

## 2. Ví dụ cơ bản với một entity Hibernate

Giả sử bảng `employees` lưu `id`, `first_name`, `last_name` và `department`:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;

@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "first_name", nullable = false)
    private String firstName;

    @Column(name = "last_name", nullable = false)
    private String lastName;

    private String department;

    @Transient
    private String displayLabel;

    private transient String importBatchMarker;

    protected Employee() {
        // Constructor để JPA khởi tạo entity.
    }

    public Employee(String firstName, String lastName, String department) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.department = department;
    }

    public String getFullName() {
        return firstName + " " + lastName;
    }

    public void setDisplayLabel(String displayLabel) {
        this.displayLabel = displayLabel;
    }

    public String getDisplayLabel() {
        return displayLabel;
    }

    public void setImportBatchMarker(String marker) {
        this.importBatchMarker = marker;
    }

    public String getImportBatchMarker() {
        return importBatchMarker;
    }
}
~~~

Trong ví dụ, `@Id` đặt trên **field**, nên mặc định JPA sử dụng **field access** cho entity (sẽ bàn kỹ ở phần sau).

Khi Hibernate ánh xạ entity:

| Thuộc tính | Được ORM lưu? | Lý do |
| --- | --- | --- |
| `id` | Có | Khóa chính persistent |
| `firstName` | Có | Field persistent, ánh xạ cột `first_name` |
| `lastName` | Có | Field persistent, ánh xạ cột `last_name` |
| `department` | Có | Field persistent thông thường |
| `displayLabel` | Không | Có `@Transient` trên field |
| `importBatchMarker` | Không | Field có modifier Java `transient` trong chế độ field access |
| `getFullName()` | Không tạo thêm một cột | Với field access, getter tính toán này không tự trở thành một persistent property |

`displayLabel` thích hợp cho nhãn giao diện mà ứng dụng gán tạm. `importBatchMarker` có thể mang dữ liệu phục vụ một lần nhập dữ liệu. Hai giá trị vẫn dùng được trong đối tượng Java hiện tại nhưng **không được khôi phục từ bảng khi truy vấn lại entity**.

Ví dụ thao tác:

~~~java
Employee employee = new Employee("Lan", "Nguyen", "Sales");
employee.setDisplayLabel("Nhân viên mới");
employee.setImportBatchMarker("batch-2026-11");

// Giả sử em đang tham gia một transaction hợp lệ:
em.persist(employee);
em.flush();

Long id = employee.getId();
em.clear(); // Bỏ entity managed để lần đọc sau phải nạp lại từ DB.

Employee reloaded = em.find(Employee.class, id);

System.out.println(reloaded.getFullName());          // Lan Nguyen
System.out.println(reloaded.getDisplayLabel());      // null
System.out.println(reloaded.getImportBatchMarker()); // null
~~~

Đoạn ví dụ giả định các trường tạm **không có giá trị khởi tạo mặc định** và không được thiết lập bằng callback khác. Nếu đặt initializer hoặc `@PostLoad` cho những field này, object mới có thể nhận giá trị không phải `null`, nhưng đó vẫn không phải dữ liệu Hibernate đọc từ cột tương ứng.

## 3. Bảng so sánh @Transient và transient

Bảng dưới đây giả định entity dùng **field access** và đối tượng được Java serialization bằng cơ chế mặc định, nếu có triển khai `Serializable`.

| Khía cạnh | JPA `@Transient` | Java `transient` |
| --- | --- | --- |
| Cú pháp | Annotation đặt trên field/getter | Modifier đặt trên field |
| Nguồn gốc | Jakarta Persistence/JPA | Ngôn ngữ Java |
| Mục đích chính | Loại thuộc tính khỏi ORM persistence | Loại field khỏi Java serialization mặc định |
| Dùng trên getter? | Có, khi getter là nơi đặt ánh xạ phù hợp | Không; `transient` chỉ áp dụng cho field |
| Dùng trên field? | Có | Có |
| Trong JPA field access | Không được ánh xạ | Không được ánh xạ theo quy tắc persistent field |
| Trong JPA property access | Có thể loại getter khỏi ánh xạ nếu đặt đúng getter | Modifier trên backing field **không tự loại** property getter |
| Trong Java serialization mặc định | Không làm Java tự bỏ field | Java bỏ qua field đó |
| Ảnh hưởng tới JSON | Không phải quy tắc JSON chung | Tùy thư viện/cấu hình và cách khám phá property |
| Giá trị tồn tại trong RAM? | Có | Có |

Từ bảng này có thể rút ra cách chọn:

- Nếu mục tiêu là **không lưu thuộc tính bằng JPA/Hibernate**, hãy dùng `@Transient` ở vị trí phù hợp với access strategy.
- Nếu mục tiêu là **không serialize field bằng Java Object Serialization**, hãy dùng từ khóa `transient`.
- Nếu cần cả hai hành vi theo cách tường minh, có thể dùng cả hai cho cùng một field khi cần, nhưng trước hết phải hiểu access strategy của entity.

Ví dụ:

~~~java
@Transient
private transient String inMemoryOnly;
~~~

Cách viết này nêu rõ cả hai ý định ở entity field access: không persist bằng JPA và không serialize field bằng Java serialization mặc định. Nó không tự quyết định việc field có được đưa vào JSON hay không.

## 4. Field access và property access quyết định vị trí đặt @Transient

Đây là phần quan trọng nhất khi áp dụng `@Transient`. JPA hỗ trợ hai cách truy cập trạng thái entity:

- **Field access:** provider đọc/ghi trực tiếp field; các annotation ánh xạ chủ yếu đặt trên field.
- **Property access:** provider đọc/ghi thông qua getter/setter JavaBeans; các annotation ánh xạ chủ yếu đặt trên getter.

Theo quy tắc mặc định, vị trí `@Id` hoặc `@EmbeddedId` thường xác định access strategy của entity, trừ khi có cấu hình `@Access` rõ ràng. Nên giữ một chiến lược nhất quán trong entity hoặc chỉ trộn khi đã khai báo `@Access` đúng cách.

### 4.1. Field access: @Id trên field

~~~java
@Entity
public class Product {

    @Id
    private Long id;

    private String name;

    @Transient
    private String uiHint;

    private transient String importNote;

    // Getter/setter có thể có cho Java code,
    // nhưng ORM ánh xạ theo field.
}
~~~

Hibernate đọc `name` từ field và bỏ qua `uiHint`, `importNote`. Annotation `@Transient` đặt trên getter khác trong cùng entity **không tự điều khiển một field mapping** khi entity đang dùng field access.

Ví dụ nếu chỉ viết:

~~~java
public class ProductViewExample {
    @Id
    private Long id;

    private String note;

    @Transient
    public String getNote() {
        return note;
    }
}
~~~

Đoạn này chỉ minh họa một cách đặt annotation **không nên dựa vào**: nếu entity dùng field access do `@Id` trên field thì `@Transient` trên getter `getNote()` không phải cách đúng để loại persistent field `note`. Hãy đặt `@Transient` trên chính field trong trường hợp đó.

### 4.2. Property access: @Id trên getter

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Transient;

@Entity
public class Product {

    private Long id;
    private String name;
    private transient String uiHint;

    @Id
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    @Transient
    public String getUiHint() {
        return uiHint;
    }

    public void setUiHint(String uiHint) {
        this.uiHint = uiHint;
    }
}
~~~

Ở đây JPA dùng **property access** vì `@Id` nằm trên `getId()`. Getter `getUiHint()` là một JavaBeans property và cần được **loại khỏi JPA bằng `@Transient` trên getter**. Modifier `transient` trên field `uiHint` tự nó chỉ đảm bảo hành vi của Java serialization, không phải cách đáng tin để loại getter này khỏi ánh xạ JPA.

Khi dùng property access, một getter tính toán như:

~~~java
public String getDisplayName() {
    return getName() + " (đang bán)";
}
~~~

cũng nên được đánh dấu `@Transient` nếu không phải property persistent. Việc chỉ có getter tính toán hoặc thiếu setter có thể khiến provider xem property là không hợp lệ hoặc cố ánh xạ theo quy tắc JavaBeans; đánh dấu rõ ý định giúp tránh nhầm lẫn.

### 4.3. Trộn access strategy bằng @Access

Có những trường hợp đặc biệt muốn đa số thuộc tính ánh xạ theo field nhưng một thuộc tính ánh xạ qua getter. JPA hỗ trợ `@Access(AccessType.FIELD)` và `@Access(AccessType.PROPERTY)` ở cấp lớp hoặc thuộc tính.

~~~java
@Entity
@Access(AccessType.FIELD)
public class Article {

    @Id
    private Long id;

    private String title;

    @Transient
    private String displayTitle;

    @Access(AccessType.PROPERTY)
    @Column(name = "normalized_title")
    public String getNormalizedTitle() {
        return title == null ? null : title.trim().toLowerCase();
    }

    public void setNormalizedTitle(String value) {
        // Cần thiết kế setter/field phù hợp hợp đồng persistence.
    }
}
~~~

Đây chỉ là hình minh họa khả năng lựa chọn access; ánh xạ một giá trị tính toán có getter nhưng setter không mang trạng thái cần được thiết kế cẩn thận để tránh lỗi khi load. Trong code nghiệp vụ, cách đơn giản hơn thường là **chọn nhất quán một access strategy**, giữ thuộc tính tính toán ở `@Transient`, hoặc lưu một field riêng có getter/setter rõ ràng nếu thực sự muốn persist.

## 5. Java serialization: @Transient không có nghĩa là Java transient

Đối tượng Java chỉ được serialize bằng cơ chế truyền thống nếu đáp ứng hợp đồng `java.io.Serializable` (hoặc cơ chế serialization khác phù hợp). Khi dùng Java serialization mặc định:

~~~java
import jakarta.persistence.Transient;
import java.io.Serializable;

public class ReportState implements Serializable {

    private static final long serialVersionUID = 1L;

    private String savedValue = "A";

    @Transient
    private String jpaIgnored = "B";

    private transient String javaIgnored = "C";

    public String getSavedValue() {
        return savedValue;
    }

    public String getJpaIgnored() {
        return jpaIgnored;
    }

    public String getJavaIgnored() {
        return javaIgnored;
    }
}
~~~

Giả sử đối tượng được ghi bằng `ObjectOutputStream` rồi đọc lại bằng `ObjectInputStream` với cơ chế mặc định:

- `savedValue` được ghi vào stream, nên thông thường được khôi phục thành `"A"`.
- `jpaIgnored` **vẫn được ghi**, vì `@Transient` không điều khiển Java serialization, nên thông thường được khôi phục thành `"B"`.
- `javaIgnored` bị loại khỏi stream vì modifier `transient`; sau khi deserialize theo cơ chế mặc định, field nhận giá trị mặc định `null`, trừ khi có logic tùy biến làm khác đi.

Đây là ví dụ về Java object serialization, không phải câu SQL của Hibernate. Lớp này thậm chí không cần là JPA entity để thể hiện khác biệt.

**Lưu ý bảo mật:** Không nên xem `@Transient` là biện pháp bảo vệ dữ liệu bí mật khỏi mọi hình thức truyền tải. Nó chỉ quyết định ORM mapping. Ngay cả Java `transient` cũng chỉ tác động lên một cơ chế serialization cụ thể; hệ thống vẫn cần thiết kế rõ các ranh giới lưu trữ, logging và truyền dữ liệu.

## 6. Một thuộc tính @Transient có vòng đời ra sao?

Khi bạn gán giá trị cho một field `@Transient`, đó vẫn là phép gán Java bình thường. Hibernate không giữ bản sao persistent của field này trong database.

Ví dụ:

~~~java
Order order = em.find(Order.class, orderId);

// Giả định Order có field @Transient tên screenMessage.
order.setScreenMessage("Ưu đãi hôm nay");

em.flush(); // Không làm giá trị screenMessage xuất hiện trong DB.

System.out.println(order.getScreenMessage()); // Giá trị vẫn tồn tại trong object.
~~~

Cần phân biệt ba hành động:

1. **Flush:** đồng bộ thay đổi persistent sang database; giá trị transient không được đưa vào SQL.
2. **Clear/detach:** entity không còn managed, nhưng object Java đang được tham chiếu vẫn có field transient của nó. `clear()` không tự xóa field trên object cũ.
3. **Tải lại thành object mới:** Hibernate chỉ đọc thuộc tính persistent; giá trị transient được khởi tạo theo constructor/initializer/callback nếu có, không lấy từ cột database tương ứng.

Đổi một field `@Transient` đơn thuần không tạo ra dirty state của ORM cho field đó. Nếu entity cũng có thay đổi persistent, các cột persistent vẫn được cập nhật bình thường theo cơ chế flush; giá trị transient không được đính kèm vào SQL chỉ vì có một UPDATE khác.

### 6.1. Giá trị dẫn xuất: ưu tiên getter tính toán khi đơn giản

Nếu thuộc tính chỉ là tổng hợp của các trường đã lưu, không nhất thiết cần một cached field:

~~~java
@Entity
public class Person {

    @Id
    private Long id;

    private String firstName;
    private String lastName;

    @Transient
    public String getFullName() {
        return firstName + " " + lastName;
    }
}
~~~

Đoạn trên giả định **field access** bởi `@Id` trên field. Với field access, getter đã không tự được ánh xạ; `@Transient` trên getter ở ví dụ này mang ý nghĩa thể hiện ý định cho người đọc, chứ không phải annotation quyết định ánh xạ. Nếu muốn nhất quán với field access, cách đơn giản hơn là để getter không có annotation:

~~~java
public String getFullName() {
    return firstName + " " + lastName;
}
~~~

Đặt `@Transient` trên getter là **cần thiết trong property access** khi getter đó không được persist. Giá trị tính toán tại thời điểm gọi giúp tránh dữ liệu tạm bị cũ khi `firstName` hoặc `lastName` thay đổi.

### 6.2. Khi dùng @Transient để giữ cache trong entity

Nếu phép tính tốn kém và bạn muốn cache, có thể khai báo field:

~~~java
@Transient
private BigDecimal cachedTotal;
~~~

Một vấn đề cần xử lý: khi các field nguồn như `quantity` hoặc `unitPrice` thay đổi, `cachedTotal` **không tự được Hibernate cập nhật hoặc invalidated**. Bạn phải tự xóa/tính lại cache hoặc dùng một phương thức tính toán thuần để loại bỏ nhu cầu giữ trạng thái.

Nếu chỉ cần khởi tạo giá trị sau khi JPA load entity, có thể sử dụng lifecycle callback `@PostLoad`:

~~~java
@Transient
private String displayText;

@PostLoad
private void afterLoad() {
    displayText = code + " - " + name;
}
~~~

`@PostLoad` chạy sau khi entity được load theo vòng đời JPA, giúp tính lại thông tin hiển thị. Tuy nhiên callback này **không tự chạy mỗi khi thuộc tính nguồn bị thay đổi bằng setter**, nên cần chủ động cập nhật giá trị hoặc tính trực tiếp khi đọc.

## 7. @Transient và những công cụ dễ nhầm

### 7.1. @Transient khác @Column(insertable = false, updatable = false)

Ví dụ:

~~~java
@Column(name = "created_at", insertable = false, updatable = false)
private LocalDateTime createdAt;
~~~

Thuộc tính `createdAt` **vẫn được ánh xạ và đọc từ database**. Hai cờ `insertable = false` và `updatable = false` chỉ loại cột khỏi SQL INSERT/UPDATE mà Hibernate sinh cho thuộc tính đó; chúng không làm thuộc tính biến mất khỏi mô hình persistence. Cách viết này có thể phù hợp với cột do database default hoặc trigger quản lý, tùy cấu hình schema.

Ngược lại:

~~~java
@Transient
private LocalDateTime lastDisplayedAt;
~~~

`lastDisplayedAt` không có ánh xạ persistent; Hibernate không tự đọc nó từ cột nào.

### 7.2. @Transient khác @Formula của Hibernate

`@Formula` là extension riêng của Hibernate, dùng biểu thức SQL để ánh xạ một thuộc tính tính toán khi đọc dữ liệu:

~~~java
@Formula("unit_price * quantity")
private BigDecimal lineTotal;
~~~

Nếu các cột/kiểu dữ liệu tương ứng tồn tại và biểu thức hợp lệ với database, Hibernate có thể lấy `lineTotal` như kết quả của SQL mà không cần cột vật lý tên `line_total`. Đây vẫn là **giá trị có ánh xạ đọc từ database**, khác với `@Transient` chỉ sống trong bộ nhớ Java.

`@Formula` phụ thuộc Hibernate và cú pháp SQL phù hợp; không phải annotation chuẩn JPA. Cần cân nhắc tính di động và truy vấn phát sinh.

### 7.3. @Transient khác @JsonIgnore và @JsonProperty

Ví dụ với Jackson:

~~~java
@Entity
public class Account {

    @Id
    private Long id;

    private String email;

    @Transient
    private String oneTimeDisplayMessage;

    @JsonIgnore
    private String internalComment;
}
~~~

`@Transient` loại `oneTimeDisplayMessage` khỏi JPA persistence; nó **không phải quy tắc JSON chung**. `@JsonIgnore` yêu cầu Jackson bỏ qua `internalComment` trong quá trình ánh xạ JSON theo cấu hình thông thường; điều này **không khiến JPA tự bỏ field đó khỏi database**.

Một thuộc tính có thể cùng lúc:

- Không lưu trong database nhưng vẫn được đưa vào response JSON nếu serializer cho phép.
- Được lưu trong database nhưng không xuất hiện trong JSON API.
- Bị loại khỏi cả database lẫn JSON khi cấu hình hai cơ chế độc lập.

Với API thực tế, dùng DTO để tách hợp đồng JSON khỏi entity thường giúp chủ động hơn trong chọn dữ liệu trả về. Đặc biệt, không dựa vào `@Transient` để che dữ liệu bí mật khỏi API.

### 7.4. @Transient của JPA và annotation cùng tên trong framework khác

Một số thư viện cung cấp annotation `Transient` riêng cho mô hình dữ liệu của chúng, chẳng hạn `org.springframework.data.annotation.Transient` trong Spring Data. Với entity quản lý bằng JPA/Hibernate, hãy chú ý import và đặt đúng `jakarta.persistence.Transient` (hoặc `javax.persistence.Transient` với dự án JPA cũ).

Tương tự, các annotation xử lý JSON, validation hoặc schema migration không tự thay đổi quyết định ORM persistence trừ khi framework tích hợp có quy định cụ thể.

## 8. Khi nào nên dùng @Transient trong ứng dụng?

### 8.1. Giá trị chỉ phục vụ giao diện

Ví dụ entity `Product` có các cột `price`, `discountPercent`, còn giao diện cần một nhãn:

~~~java
@Transient
private String priceBadge;
~~~

Ứng dụng có thể gán `"Giảm 20%"` tùy ngữ cảnh người dùng hoặc chiến dịch. Nếu giá trị chỉ dùng cho response API, DTO có thể còn phù hợp hơn đặt vào entity.

### 8.2. Kết quả tính toán dẫn xuất từ các field đã lưu

Ví dụ:

~~~java
public BigDecimal getEstimatedTotal() {
    return unitPrice.multiply(BigDecimal.valueOf(quantity));
}
~~~

Nếu tính trực tiếp từ `unitPrice` và `quantity`, không cần thêm cột. Khi entity dùng property access, đánh dấu getter `@Transient` để không ánh xạ nó.

Nếu kết quả cần được truy vấn, sắp xếp hoặc lọc ở phía database bằng JPQL, một Java-only transient property không đủ. Có thể cần biểu thức JPQL, projection, cột generated hoặc một ánh xạ phù hợp khác.

### 8.3. Dữ liệu trung gian phục vụ import/export

Một entity có thể giữ thông báo tạm về hàng đang xử lý, trạng thái tính toán trong RAM hoặc dấu đánh dấu batch. Nếu không cần giữ chúng sau khi transaction hoàn tất, đặt `@Transient` phù hợp với JPA; nếu cùng lúc không muốn Java serialization đưa dữ liệu đó vào stream, cân nhắc modifier `transient`.

Không dùng entity như một kho lưu trạng thái công việc dài hạn chỉ vì có field `@Transient`: trạng thái đó sẽ mất khi ứng dụng restart, thay instance hoặc entity được load lại.

### 8.4. Dependency hoặc tài nguyên runtime

Không nên ánh xạ trực tiếp một đối tượng như `ExecutorService`, network client hoặc cache service vào cột SQL. Nhưng cũng cần cân nhắc **không giữ tài nguyên hạ tầng trực tiếp trong entity**; service là nơi phù hợp hơn cho dependency phức tạp. Nếu một field runtime bắt buộc nằm trong object, phải loại khỏi persistence và kiểm soát vòng đời, serialization, thread safety.

## 9. Những tình huống không nên lạm dụng @Transient

### 9.1. Khi cần lọc/sắp xếp bằng JPQL

JPQL làm việc với **các thuộc tính persistent** của entity. Nếu `fullName` chỉ là một `@Transient` Java property, truy vấn:

~~~java
em.createQuery(
    "SELECT p FROM Person p ORDER BY p.fullName",
    Person.class);
~~~

không hợp lệ chỉ vì object có getter `getFullName()`. Muốn sắp xếp theo tên đầy đủ, có thể dùng biểu thức dựa trên các trường đã ánh xạ, cột được lưu hoặc native SQL phù hợp database.

### 9.2. Khi thuộc tính phải tồn tại sau khi reload

Nếu nghiệp vụ yêu cầu “ghi chú phê duyệt” phải còn nguyên sau khi ứng dụng restart, nó cần được lưu trong database hoặc kho lưu trữ phù hợp. `@Transient` không phù hợp vì bản thân nó loại giá trị khỏi việc lưu bằng ORM.

### 9.3. Khi muốn field chỉ đọc nhưng vẫn lấy được từ database

`@Transient` sẽ khiến Hibernate không đọc trường đó từ database. Nếu mục tiêu là “có cột trong DB nhưng ứng dụng không ghi”, hãy cân nhắc ánh xạ read-only thích hợp như `@Column(insertable = false, updatable = false)` hoặc cách ánh xạ khác tùy tình huống.

### 9.4. Khi muốn bảo mật hoặc kiểm soát JSON

Nếu mục tiêu là không gửi email, số điện thoại, token hay thông tin nội bộ qua API, cần quyết định rõ hợp đồng API/DTO, phân quyền và quy tắc JSON serialization. `@Transient` chỉ xử lý lưu trữ JPA; không phải biện pháp bảo vệ chung cho thông tin nhạy cảm.

### 9.5. Khi có quan hệ thật sự cần persist

Nếu entity có quan hệ `@ManyToOne`, `@OneToMany` hoặc thuộc tính `@ElementCollection` cần được lưu, gắn `@Transient` lên thành phần đó sẽ loại nó khỏi mô hình ORM theo access strategy. Không nên làm vậy chỉ để tránh truy vấn chậm; hãy giải quyết fetch strategy, projection hoặc thiết kế quan hệ đúng cách.

## 10. Ví dụ end-to-end: thuộc tính không lưu qua transaction

Giả sử có entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Transient;

@Entity
public class Customer {

    @Id
    private Long id;

    private String name;

    @Transient
    private String displayMessage;

    private transient String processingTag;

    protected Customer() {}

    public Customer(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setDisplayMessage(String value) {
        displayMessage = value;
    }

    public String getDisplayMessage() {
        return displayMessage;
    }

    public void setProcessingTag(String value) {
        processingTag = value;
    }

    public String getProcessingTag() {
        return processingTag;
    }
}
~~~

Hệ thống sử dụng kiểu access FIELD vì `@Id` đặt trên field. Giả định bảng `customer` có schema tương ứng và transaction đã được mở:

~~~java
Customer customer = new Customer(101L, "Minh");
customer.setDisplayMessage("Khách hàng thân thiết");
customer.setProcessingTag("import-001");

em.persist(customer);
em.flush();

System.out.println(customer.getDisplayMessage());
// Khách hàng thân thiết: object Java còn sống trong RAM.

em.clear();

Customer fromDatabase = em.find(Customer.class, 101L);
System.out.println(fromDatabase.getName());           // Minh
System.out.println(fromDatabase.getDisplayMessage()); // null
System.out.println(fromDatabase.getProcessingTag());  // null
~~~

Vì hai field không persistent, Hibernate chỉ lưu những giá trị tương ứng với `id` và `name`. Chúng không thể được truy vấn lại từ database chỉ bằng `em.find()`.

Trong ví dụ thực tế, transaction cần commit hoặc rollback đúng cách và ID phải không trùng. Để minh họa hiệu ứng rõ hơn, cách dùng `em.clear()` tránh việc `em.find()` chỉ trả về object đã managed và vẫn còn các field tạm trong RAM.

### 10.1. Cách quan sát qua integration test

Một bài kiểm thử tích hợp với database thực tế hoặc database test tương thích có thể thực hiện:

1. Tạo entity mới và gán giá trị cho field persistent cùng hai field transient.
2. Gọi `persist()` và `flush()` trong transaction.
3. Gọi `clear()` để bỏ persistence context.
4. Dùng `find()` để tải object mới từ database.
5. Xác nhận giá trị persistent còn tồn tại, còn giá trị transient không được khôi phục từ cột.
6. Nếu entity có initializer hoặc callback, phân biệt giá trị do Java tự thiết lập với giá trị lấy từ database.

Ngoài kiểm thử entity field access, nên có một trường hợp property access với `@Id` trên getter và `@Transient` trên getter cần loại, vì đây là nơi dễ nhầm giữa annotation và Java modifier.

## 11. Các nhầm lẫn thường gặp

| Nhận định | Điều đúng cần nhớ |
| --- | --- |
| “`@Transient` và `transient` có thể thay thế trong mọi entity.” | Chúng có ý nghĩa khác nhau; property access có thể làm cách xử lý JPA khác biệt. |
| “Có `@Transient` nghĩa là Java không serialize field.” | Java serialization mặc định không bỏ field chỉ vì JPA `@Transient`. |
| “Có `transient` là đủ để bỏ thuộc tính dù JPA dùng getter.” | Với property access, phải xử lý mapping ở getter, thường dùng `@Transient` trên getter. |
| “Flush sẽ xóa giá trị `@Transient` khỏi object.” | Flush chỉ đồng bộ thuộc tính persistent; object hiện tại vẫn giữ giá trị trong RAM. |
| “Clear sẽ đặt mọi field transient thành null.” | Clear detach object; chỉ khi load object mới mới thấy quá trình khởi tạo độc lập. |
| “`@Transient` làm field không xuất hiện trong JSON.” | JSON serialization do thư viện JSON và hợp đồng API quyết định. |
| “`@Transient` giống cột read-only.” | Read-only column vẫn được ánh xạ/đọc; `@Transient` không ánh xạ cột. |
| “Có getter thì JPQL luôn truy vấn được thuộc tính.” | Chỉ persistent property trong mapping mới có thể được tham chiếu như đường dẫn JPQL. |
| “Đổi một field transient sẽ tạo câu UPDATE.” | Hibernate không dirty-check nó như persistent state. |
| “Gắn `@Transient` lên bất kỳ vị trí nào cũng có hiệu lực.” | Annotation phải phù hợp FIELD hoặc PROPERTY access. |

## 12. Quy tắc quyết định nhanh

Đặt câu hỏi theo thứ tự:

1. **Thuộc tính có cần được ghi và đọc lại từ database không?** Nếu có, nó phải được ánh xạ persistent theo cách phù hợp. Không dùng `@Transient`.
2. **Đây là giá trị chỉ dùng trong RAM, chỉ để hiển thị hoặc tính toán?** Có thể dùng `@Transient`, hoặc chuyển sang DTO/service nếu không nên nằm trong entity.
3. **Entity đang dùng field access hay property access?** Xác định qua `@Id`/`@EmbeddedId` và các khai báo `@Access`. Đặt annotation ở field hoặc getter tương ứng.
4. **Có dùng Java `ObjectOutputStream` serialization không?** Nếu cần loại field khỏi byte stream, dùng `transient` của Java và xem xét các quy tắc serialization.
5. **Có trả entity qua JSON không?** Thiết kế DTO hoặc annotation JSON phù hợp riêng; không mặc định kỳ vọng `@Transient` điều khiển JSON.
6. **Có cần lọc, sắp xếp hoặc cập nhật dữ liệu bằng SQL/JPQL không?** Khi đó cần thiết kế persistence mapping hoặc projection thay vì chỉ có Java-only transient field.

## 13. Bài tập thực hành

### Bài 1: Xác định trường được lưu

Cho entity dùng field access:

~~~java
@Entity
class Task {

    @Id
    private Long id;

    private String title;

    @Transient
    private String uiColor;

    private transient String localTrace;
}
~~~

Hãy nêu các field được JPA ánh xạ, field nào sẽ không tồn tại trong dữ liệu đọc lại từ database, và tại sao hai field không lưu có cơ chế khác nhau ngoài JPA.

### Bài 2: Tìm lỗi với property access

~~~java
@Entity
class Book {

    private Long id;
    private transient String previewText;

    @Id
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getPreviewText() {
        return previewText;
    }

    public void setPreviewText(String text) {
        previewText = text;
    }
}
~~~

Nếu `previewText` chỉ dùng để hiển thị và tuyệt đối không được ánh xạ, hãy sửa mapping bằng cách đặt `@Transient` tại vị trí phù hợp.

### Bài 3: So sánh với Java serialization

Một lớp implements `Serializable` có `@Transient String note` và `transient String cache`. Với Java serialization mặc định, field nào bị bỏ khỏi byte stream và vì sao? Điều gì thay đổi nếu đối tượng được persist bằng JPA field access?

### Bài 4: Chọn cách thiết kế

Màn hình cần hiển thị “tên đầy đủ” dựa trên họ và tên. Hãy so sánh một getter tính toán, field `@Transient` dạng cache và cột database. Trong trường hợp nào cần có cột hoặc biểu thức truy vấn ở database để hỗ trợ tìm kiếm/sắp xếp?

**Định hướng trả lời:** Bài 1 — `id` và `title` được persist, còn `uiColor` và `localTrace` không; bài 2 — đặt `@Transient` lên `getPreviewText()`; bài 3 — Java `transient` loại `cache` khỏi serialization mặc định, còn JPA `@Transient` tự nó không loại `note` khỏi luồng Java; bài 4 — getter tính toán thường đủ cho hiển thị, cache cần cơ chế vô hiệu hóa, còn lọc/sắp xếp phía DB cần biểu thức/ánh xạ DB phù hợp.

---

**Ghi nhớ:** `@Transient` là quyết định về **ánh xạ ORM**, còn `transient` là quyết định về **Java serialization**. Trong entity JPA, hãy xác định FIELD hay PROPERTY access trước khi chọn vị trí đặt annotation. Sau đó tách riêng các yêu cầu về database, object serialization và JSON API; mỗi cơ chế có quy tắc và vòng đời riêng.
