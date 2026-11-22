# Phân biệt truy cập qua trường và qua thuộc tính

Khi dùng **Jakarta Persistence API (JPA)** để ánh xạ đối tượng Java vào cơ sở dữ liệu quan hệ, persistence provider (ví dụ Hibernate) phải biết **đọc và ghi trạng thái persistent của entity qua đâu**. JPA có hai kiểu truy cập chính:

- **Truy cập qua trường (*field access*, `AccessType.FIELD`):** JPA ánh xạ và thao tác trực tiếp với các **field** của đối tượng.
- **Truy cập qua thuộc tính (*property access*, `AccessType.PROPERTY`):** JPA ánh xạ trạng thái qua các **JavaBeans property**, thường được thể hiện bằng cặp phương thức getter/setter.

Hai kiểu đều có thể lưu cùng một cấu trúc bảng và cùng dữ liệu. Điểm khác biệt nằm ở **hợp đồng giữa JPA và lớp Java**: JPA quan sát thành viên nào, annotation ánh xạ đặt ở đâu, cách đối tượng được khôi phục và những tác động khi getter/setter chứa logic nghiệp vụ.

Trong chương **Entity và định danh**, lựa chọn này đặc biệt quan trọng vì vị trí khai báo `@Id` hoặc `@EmbeddedId` thường quyết định kiểu truy cập mặc định cho entity khi không dùng `@Access` tường minh.

## 1. Khái niệm: field của Java khác property của JavaBeans

Xét một lớp Java thông thường:

```java
public class Customer {
    private Long id;
    private String name;

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Trong ví dụ này:

| Thành phần | Bản chất | Ví dụ |
|---|---|---|
| **Field** | Biến thành viên được khai báo trong lớp | `private String name;` |
| **Getter** | Phương thức đọc giá trị | `getName()` |
| **Setter** | Phương thức gán giá trị | `setName(String name)` |
| **JavaBeans property** | Thuộc tính logic được xác định qua quy ước tên và chữ ký các phương thức truy cập | Property `name` tương ứng `getName()` và `setName(...)` |
| **Persistent attribute** | Thuộc tính được JPA ánh xạ để lưu/đọc trạng thái | Có thể là field `name` hoặc property `name`, tùy access type |

Property không nhất thiết là một field riêng biệt. Một getter có thể đọc nhiều field hoặc tính toán kết quả. Điều này giải thích vì sao lựa chọn `FIELD` hay `PROPERTY` có thể ảnh hưởng đến ý nghĩa dữ liệu được ánh xạ.

**Lưu ý:** “Property access” của JPA nói về cách truy cập trạng thái persistence. Nó **không có nghĩa** field phải khai báo `public`, cũng không liên quan trực tiếp đến quyền truy cập HTTP, REST, JSON, SQL hay mối quan hệ `FetchType.LAZY`.

## 2. Truy cập qua trường — `AccessType.FIELD`

### 2.1. Đặc điểm

Ở chế độ `FIELD`, JPA làm việc với những field được coi là persistent. Các annotation như `@Id`, `@Column`, `@Version`, `@ManyToOne`, `@Embedded` và `@Transient` được đặt trên **khai báo field** tương ứng.

JPA có thể dùng reflection, cơ chế tăng cường bytecode hoặc cách triển khai khác để đọc/ghi field, kể cả field `private`, mà không cần gọi các getter/setter do ứng dụng cung cấp.

Ví dụ độc lập:

```java
package com.example.persistence;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;
import jakarta.persistence.Version;

@Entity
@Table(name = "customer")
@Access(AccessType.FIELD)
public class CustomerFieldAccess {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 150)
    private String name;

    @Version
    private Long version;

    @Transient
    private String displayCache;

    protected CustomerFieldAccess() {
        // JPA dùng constructor không tham số.
    }

    public CustomerFieldAccess(String name) {
        rename(name);
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.name = newName;
        this.displayCache = null;
    }

    public String getDisplayLabel() {
        if (displayCache == null) {
            displayCache = "Khách hàng: " + name;
        }
        return displayCache;
    }
}
```

Ở đây:

1. `@Id` được đặt trên field `id`, nên đây là thuộc tính định danh của entity.
2. `@Column` trên field `name` cấu hình cột `full_name` trong bảng `customer`.
3. `@Version` trên field `version` cấu hình thuộc tính phiên bản phục vụ optimistic locking.
4. `@Transient` trên field `displayCache` đánh dấu dữ liệu tạm, không lưu vào bảng.
5. `getDisplayLabel()` là phương thức tính nhãn hiển thị. Với `FIELD`, JPA không tự coi một getter bất kỳ thành thuộc tính cần lưu.

Tên lớp có hậu tố `FieldAccess` chỉ để phân biệt ví dụ. JPA không yêu cầu tên lớp phải có hậu tố này. Khi triển khai ứng dụng thực tế, thông thường chỉ cần một lớp entity `Customer` cho một mô hình tương ứng; hai lớp ví dụ `CustomerFieldAccess` và `CustomerPropertyAccess` ở bài này là **hai phương án thay thế**, không phải hai entity cần đăng ký đồng thời để quản lý cùng một bảng.

### 2.2. Getter/setter có còn cần không?

**Không phải để JPA truy cập trường.** Khi áp dụng field access, JPA có thể nạp `id` và `name` vào các field mà không gọi `setId()` hoặc `setName()`.

Tuy vậy, ứng dụng vẫn có thể cần:

- Getter để code nghiệp vụ đọc dữ liệu.
- Phương thức nghiệp vụ như `rename()`, `changeAddress()` để thay đổi trạng thái hợp lệ.
- Constructor hoặc factory để bảo đảm dữ liệu khởi tạo đúng.
- Phương thức phục vụ serialization, presentation hoặc thư viện khác.

Entity vẫn cần constructor không tham số đáp ứng yêu cầu của JPA (thông thường `public` hoặc `protected`), dù access type là `FIELD` hay `PROPERTY`.

Một lợi ích lớn của `FIELD` là có thể giữ API của entity gọn, tránh công khai setter tự do cho các giá trị nhạy cảm:

```java
// Ứng dụng gọi phương thức mang nghĩa nghiệp vụ:
customer.rename("Nguyễn An");

// Không cần setter public cho ID:
Long customerId = customer.getId();
```

### 2.3. Những field nào được ánh xạ?

Với field access, các field đủ điều kiện thường được coi là persistent **kể cả khi không gắn `@Column`**. JPA chỉ cần annotation khi có cấu hình bổ sung hoặc khi muốn loại trừ một field.

Ví dụ:

```java
@Entity
@Access(AccessType.FIELD)
public class Product {
    @Id
    private Long id;

    private String sku;              // Persistent theo mapping mặc định.

    @Transient
    private String cachedLabel;      // Không persistent.

    private transient String secret; // Java transient: không persistent.

    private static int instanceCount; // Static: không persistent.

    protected Product() {
    }
}
```

Các điểm cần chú ý:

- `@Transient` ở đây là `jakarta.persistence.Transient`, một annotation JPA, khác với từ khóa `transient` của Java.
- Field `static` và field `transient` không thuộc trạng thái persistent mặc định.
- `@Transient` đặt trên **getter** của một field-access entity không phải cách chuẩn để loại field tương ứng ra khỏi mapping; hãy đặt nó trên **field**.
- Các field persistent phải tuân theo các ràng buộc của JPA đối với loại trường có thể ánh xạ; không nên giả định mọi field Java (ví dụ field `final`) đều được provider hỗ trợ để hydrate như một thuộc tính persistent thông thường.

## 3. Truy cập qua thuộc tính — `AccessType.PROPERTY`

### 3.1. Đặc điểm

Với `PROPERTY`, JPA ánh xạ qua **JavaBeans property**; annotation đặt trên **getter**. Đối với một thuộc tính persistent thông thường, cần có bộ phương thức truy cập phù hợp, chẳng hạn `getName()` và `setName(String)`. Property boolean có thể dùng dạng `isActive()` theo quy ước JavaBeans.

Ví dụ thay thế cho entity ở phần trước:

```java
package com.example.persistence;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;
import jakarta.persistence.Version;

@Entity
@Table(name = "customer")
@Access(AccessType.PROPERTY)
public class CustomerPropertyAccess {

    private Long id;
    private String name;
    private Long version;
    private String displayCache;

    protected CustomerPropertyAccess() {
        // JPA.
    }

    public CustomerPropertyAccess(String name) {
        setName(name);
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Long getId() {
        return id;
    }

    protected void setId(Long id) {
        this.id = id;
    }

    @Column(name = "full_name", nullable = false, length = 150)
    public String getName() {
        return name;
    }

    public void setName(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.name = name;
        this.displayCache = null;
    }

    @Version
    public Long getVersion() {
        return version;
    }

    protected void setVersion(Long version) {
        this.version = version;
    }

    @Transient
    public String getDisplayLabel() {
        if (displayCache == null) {
            displayCache = "Khách hàng: " + name;
        }
        return displayCache;
    }
}
```

Trong ví dụ này, ánh xạ nằm ở các getter:

- `getId()`: `@Id` và `@GeneratedValue`.
- `getName()`: `@Column(name = "full_name", ...)`.
- `getVersion()`: `@Version`.
- `getDisplayLabel()`: `@Transient` để thể hiện rõ đây không phải thuộc tính persistent.

Ở chế độ này, `private String name;` là **backing field**; bản thân khai báo field không phải nơi đặt annotation ánh xạ mặc định. Provider phải quan sát property tương ứng khi thực hiện truy cập persistence. Cách provider thực thi ở cấp bytecode có thể được tối ưu hóa, nhưng hợp đồng JPA của chế độ property access gắn với các accessor.

### 3.2. Cặp getter/setter là một phần hợp đồng ánh xạ

Thông thường, một property persistent cần:

```java
public String getName() {
    return name;
}

public void setName(String name) {
    this.name = name;
}
```

Các kiểu getter khác thường thấy:

```java
public boolean isActive() {
    return active;
}

public void setActive(boolean active) {
    this.active = active;
}
```

Cần đặc biệt lưu ý:

- Annotation mapping đặt trên **getter**, không đặt trên setter.
- Tên và kiểu của getter/setter phải phù hợp quy ước property, tránh đặt tên khác thường rồi mong JPA tự suy ra.
- Getter nên trả về trạng thái ổn định, hạn chế tác dụng phụ.
- Setter cần chấp nhận trạng thái hợp lệ mà JPA có thể phải khôi phục từ database.
- Không nên đặt logic gọi dịch vụ bên ngoài, gửi sự kiện hay truy vấn database trong getter/setter mà JPA có thể gọi nhiều lần.

Ví dụ getter có tác dụng phụ:

```java
@Column(name = "access_count")
public int getAccessCount() {
    return ++accessCount; // Không nên: chỉ việc đọc có thể làm đổi dữ liệu.
}
```

Nếu JPA lấy giá trị qua getter này trong một chu kỳ đồng bộ, nội dung bị tăng chỉ vì thao tác đọc. Getter phục vụ persistence nên tránh những hành vi như vậy.

### 3.3. Một getter tính toán có thể vô tình trở thành property

Giả sử entity dùng `PROPERTY` và có cặp getter/setter để phục vụ UI:

```java
public String getDisplayName() {
    return name.toUpperCase();
}

public void setDisplayName(String displayName) {
    // Ví dụ API đặt giá trị hiển thị, không phải mapping dự kiến.
    this.name = displayName;
}
```

Nếu không đánh dấu loại trừ thích hợp, JPA có thể xét property `displayName` vào persistent state theo quy tắc ánh xạ mặc định. Hệ quả có thể là provider tìm cột `displayName` hoặc cột theo naming strategy, dù schema không có.

Để thể hiện chủ đích **không lưu** property phụ trợ:

```java
@Transient
public String getDisplayName() {
    return name.toUpperCase();
}
```

Ở đoạn này, `@Transient` phải đặt trên **getter** vì entity dùng property access. Nếu entity dùng field access, một phương thức tính toán không liên kết trực tiếp với field persistent và thường không cần đánh dấu để loại khỏi mapping; field cache tương ứng mới cần `@Transient` nếu không được lưu.

## 4. JPA xác định access type bằng cách nào?

Có **hai cách**: xác định **mặc định** từ vị trí mapping annotation theo quy tắc JPA, hoặc khai báo **tường minh** bằng `@Access`.

### 4.1. Mặc định khi không khai báo `@Access`

Với một hierarchy dùng mapping nhất quán, vị trí đặt `@Id` hay `@EmbeddedId` thường xác định access type mặc định:

**`@Id` đặt trên field:**

```java
@Entity
public class Author {
    @Id
    private Long id; // => FIELD access mặc định.

    @Column(name = "pen_name")
    private String penName;

    protected Author() {
    }

    public Long getId() { return id; }
    public String getPenName() { return penName; }
}
```

**`@Id` đặt trên getter:**

```java
@Entity
public class Publisher {
    private Long id;
    private String name;

    protected Publisher() {
    }

    @Id
    public Long getId() { return id; } // => PROPERTY access mặc định.
    protected void setId(Long id) { this.id = id; }

    @Column(name = "publisher_name")
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
```

Cách xác định mặc định còn cần xét **hệ phân cấp entity và mapped superclass**, không chỉ nhìn một lớp con. Chẳng hạn, nếu lớp `@MappedSuperclass` chứa `@Id` trên field và lớp entity con kế thừa định danh đó, không nên tự giả định rằng chuyển vài annotation trong lớp con sang getter sẽ làm cả hierarchy chuyển sang property access.

### 4.2. Khai báo tường minh với `@Access`

Cách làm rõ ý định nhất là:

```java
@Entity
@Access(AccessType.FIELD)
public class Invoice {
    @Id
    private Long id;

    private String description;

    protected Invoice() {
    }
}
```

Hoặc:

```java
@Entity
@Access(AccessType.PROPERTY)
public class Payment {
    private Long id;

    protected Payment() {
    }

    @Id
    public Long getId() { return id; }
    protected void setId(Long id) { this.id = id; }
}
```

`@Access` thuộc package `jakarta.persistence`. Hai hằng số là `AccessType.FIELD` và `AccessType.PROPERTY`.

**Bảng quyết định nhanh:**

| Cấu hình | JPA coi gì là thành viên persistent chính? | Annotation ánh xạ đặt ở đâu? |
|---|---|---|
| `@Id` trên field, không có `@Access` | Field (theo quy tắc mặc định, khi hierarchy nhất quán) | Field |
| `@Id` trên getter, không có `@Access` | Property | Getter |
| `@Access(FIELD)` trên entity | Field, trừ thuộc tính override hợp lệ | Field |
| `@Access(PROPERTY)` trên entity | Property, trừ thuộc tính override hợp lệ | Getter |
| `@Access` ở một thành viên cụ thể | Có thể đổi kiểu truy cập riêng thành viên đó | Đặt annotation đúng nơi kiểu truy cập mới yêu cầu |

**Thứ tự ưu tiên về mặt thiết kế:** Nếu muốn tất cả thành viên dùng một cơ chế, đặt `@Access` ở lớp và nhất quán toàn bộ annotation. Chỉ override ở từng thành viên khi có nhu cầu thực tế.

### 4.3. Vì sao không nên trộn annotation vô ý?

Ví dụ có vấn đề:

```java
@Entity
public class WrongCustomer {

    @Id
    private Long id; // FIELD access mặc định.

    private String name;

    @Column(name = "full_name") // Annotation nằm trên getter!
    public String getName() {
        return name;
    }

    protected WrongCustomer() {
    }
}
```

Trong cách viết này, vị trí `@Id` gợi ý `FIELD` nhưng `@Column` lại gắn với getter. Việc **pha trộn nơi đặt annotation ánh xạ mà không khai báo `@Access` phù hợp** dẫn đến hành vi không được xác định rõ theo quy tắc truy cập của JPA. Tùy provider, ứng dụng có thể gặp lỗi mapping hoặc mapping cột khác dự kiến.

Nên sửa bằng **một** trong hai cách:

- Giữ field access, chuyển `@Column` lên field `name`.
- Dùng property access, chuyển `@Id` lên getter `getId()` và tổ chức getter/setter đầy đủ; hoặc áp dụng explicit access hợp lệ khi thực sự cần phối hợp.

Không cần sửa tên field Java để khớp tên cột SQL. `@Column(name = "...")` đã là nơi khai báo mapping.

## 5. Sơ đồ: JPA đọc/ghi cùng dữ liệu theo hai đường

```text
                         Bảng customer
                       +------------------+
                       | id | full_name   |
                       +------------------+
                       | 12 | "Nguyễn An" |
                       +------------------+
                               |
                  JPA đọc dữ liệu / ghi thay đổi
                               |
              +----------------+----------------+
              |                                 |
              v                                 v
       FIELD access                       PROPERTY access
     +-------------------+               +-----------------------+
     | @Id private id    |               | @Id getId()           |
     | @Column private   |               | @Column getName()     |
     | name              |               | setName(String)       |
     +-------------------+               +-----------------------+
              |                                 |
      Đọc/ghi field                        Truy cập property
      (getter có thể                       (getter/setter là
       chỉ phục vụ API)                      hợp đồng ánh xạ)
              |                                 |
              +----------------+----------------+
                               |
                    Cùng giá trị nghiệp vụ
```

Chọn `FIELD` hay `PROPERTY` tự nó **không đổi lược đồ database**. Hai entity có thể được ánh xạ về cùng các cột khi khai báo tương đương; sự khác nhau nằm ở cách ORM lấy giá trị từ object và đặt lại giá trị vào object.

## 6. Hệ quả đối với định danh `@Id` và `@EmbeddedId`

### 6.1. Một entity vẫn có identity như nhau ở cả hai cách

Field access:

```java
@Id
@GeneratedValue
private Long id;
```

Property access:

```java
@Id
@GeneratedValue
public Long getId() {
    return id;
}
```

Trong cả hai trường hợp, `id` đều là định danh JPA của entity. Access type không thay đổi ý nghĩa của identity, cơ chế persistence context hay sự phân biệt giữa entity managed/detached.

Trong cùng một persistence context, JPA nhận diện entity theo loại entity và giá trị định danh. Entity thay đổi `name` nhưng vẫn đại diện cùng một thực thể.

### 6.2. Định danh ghép và `@EmbeddedId`

Với `@EmbeddedId`, hãy giữ annotation ở đúng thành viên được truy cập:

```java
@Embeddable
public class OrderLineId implements java.io.Serializable {
    private Long orderId;
    private Integer lineNo;

    protected OrderLineId() {
    }

    public OrderLineId(Long orderId, Integer lineNo) {
        this.orderId = orderId;
        this.lineNo = lineNo;
    }

    public Long getOrderId() { return orderId; }
    public Integer getLineNo() { return lineNo; }

    // Cần equals/hashCode phù hợp với giá trị khóa ghép.
}
```

Entity dùng field access:

```java
@Entity
@Access(AccessType.FIELD)
public class OrderLine {

    @EmbeddedId
    private OrderLineId id;

    private String sku;

    protected OrderLine() {
    }
}
```

Nếu entity dùng property access, `@EmbeddedId` phải đặt trên getter `getId()` thích hợp. Với khóa ghép, lớp ID phải đáp ứng các yêu cầu của JPA như serializable, constructor không tham số và quy tắc equality nhất quán với các thành phần khóa; đoạn code trên minh họa cấu trúc, chưa phải triển khai đầy đủ của một khóa ghép sản xuất.

### 6.3. Không lẫn access type với cách tạo khóa

`@GeneratedValue` chọn chiến lược sinh định danh như `IDENTITY`, `SEQUENCE`, `TABLE` hoặc `AUTO` tùy nhu cầu và hệ quản trị; `FIELD`/`PROPERTY` chỉ quyết định **annotation đặt ở đâu và JPA tiếp cận attribute như thế nào**.

Ví dụ `@GeneratedValue(strategy = GenerationType.IDENTITY)` vẫn mang cùng ý nghĩa khi đặt trên field `id` ở field access hoặc getter `getId()` ở property access. Việc ID xuất hiện trước hay sau flush còn phụ thuộc chiến lược sinh ID, provider và transaction, không chỉ access type.

## 7. Kết hợp hai kiểu với `@Access` ở cấp thuộc tính

JPA cho phép **override kiểu truy cập của một thuộc tính cụ thể** bằng `@Access`. Cơ chế này hữu ích nếu phần lớn entity dùng field access nhưng một thuộc tính cần ánh xạ qua getter.

Ví dụ minh họa:

```java
@Entity
@Access(AccessType.FIELD)
public class Article {

    @Id
    private Long id;

    private String title;

    @Transient
    private String searchCode;

    protected Article() {
    }

    @Access(AccessType.PROPERTY)
    @Column(name = "search_code")
    public String getSearchCode() {
        return searchCode;
    }

    public void setSearchCode(String searchCode) {
        this.searchCode = searchCode;
    }
}
```

Ý nghĩa:

- `id` và `title` được ánh xạ theo field access của lớp.
- Field nền `searchCode` được loại khỏi field mapping bằng `@Transient`, tránh ánh xạ một giá trị hai lần.
- Property `getSearchCode()/setSearchCode()` được ánh xạ tường minh theo `PROPERTY` và dùng cột `search_code`.

Trường hợp ngược lại, một lớp mặc định `PROPERTY` cũng có thể dùng `@Access(FIELD)` trên field được chọn, kèm cách loại trừ property cùng tên phù hợp để tránh trùng mapping.

**Nguyên tắc:** một thuộc tính lưu trữ chỉ có **một mapping có chủ đích**. Nếu dùng mixed access, hãy làm rõ quyền sở hữu mapping cho cả backing field và JavaBeans property. Khi không có lý do đặc biệt, lựa chọn một access type nhất quán trong entity dễ đọc và dễ bảo trì hơn.

## 8. Tác động đến lifecycle, dirty checking và encapsulation

### 8.1. Dirty checking tồn tại ở cả hai chế độ

Giả sử entity `Customer` được JPA quản lý trong transaction:

```java
Customer customer = entityManager.find(Customer.class, 12L);
customer.rename("Nguyễn An");

// Đến flush/commit, JPA có thể phát hiện state đã thay đổi
// và sinh UPDATE tương ứng nếu cần.
```

Nếu `rename()` thay đổi field persistent thì:

- Với **field access**, JPA theo dõi và đồng bộ trạng thái field đó.
- Với **property access**, JPA theo dõi và đồng bộ trạng thái persistent property tương ứng theo cơ chế provider.

Không thể kết luận “chỉ thay đổi qua setter mới được dirty checking”. ORM có nhiều chiến lược nhận biết thay đổi, chẳng hạn so sánh snapshot hoặc bytecode enhancement; chi tiết kỹ thuật tùy provider. Điều quan trọng là **entity đang managed, thuộc tính được ánh xạ và transaction được điều khiển đúng**.

Ngược lại, sửa một entity **detached** không tự động đồng bộ vào database dù dùng `FIELD` hay `PROPERTY`.

### 8.2. Setter nghiệp vụ có được gọi khi nạp entity?

Với `FIELD`, ORM có thể đi thẳng vào field và **không chạy setter**. Do đó không nên đặt một bất biến nghiệp vụ quan trọng **chỉ** trong setter rồi giả định JPA sẽ kiểm tra nó khi hydrate entity.

Với `PROPERTY`, getter/setter là bề mặt truy cập persistence. Điều này tạo rủi ro nếu setter:

- Phát sự kiện, gửi email hoặc gọi API khác.
- Dùng dữ liệu của nhiều property chưa được hydrate xong để xác thực toàn cục.
- Có logic phụ thuộc thứ tự gọi setter.
- Tự thêm đối tượng liên kết và vô tình làm sai quan hệ.
- Chuyển đổi giá trị không thuận nghịch, làm lần đọc sau khác dữ liệu gốc.

Ví dụ setter có logic khó phù hợp với hydration:

```java
public void setBalance(java.math.BigDecimal balance) {
    if (balance.signum() < 0) {
        throw new IllegalArgumentException("Balance cannot be negative");
    }
    // Nếu gọi dịch vụ hoặc phát sự kiện ở đây,
    // quá trình JPA khôi phục state cũng có thể kích hoạt tác dụng phụ.
    this.balance = balance;
}
```

Một quy tắc kiểm tra âm có thể hợp lý với nghiệp vụ cụ thể, nhưng phải xét cách xử lý bản ghi tồn tại, dữ liệu legacy và thứ tự nạp các thuộc tính. Hãy tách thao tác nghiệp vụ có tác dụng phụ vào phương thức chuyên biệt, áp dụng validation ở ranh giới nhập dữ liệu và dùng constraint database thích hợp.

### 8.3. Field access hỗ trợ đóng gói trạng thái

Một entity có thể từ chối setter `public` cho ID và cho phép cập nhật theo phương thức:

```java
public void activate() {
    if (this.deleted) {
        throw new IllegalStateException("Đã xóa thì không kích hoạt");
    }
    this.active = true;
}
```

JPA vẫn ánh xạ `private boolean active;` nếu lớp dùng field access. Đây là lý do field access thường phù hợp với entity tập trung vào hành vi nghiệp vụ.

Property access vẫn có thể đóng gói logic, nhưng phải thiết kế các accessor được JPA sử dụng sao cho ổn định, dễ hiểu và không gây tác dụng phụ.

### 8.4. `@PostLoad` không thay thế access type

Callback `@PostLoad` được gọi sau khi entity được tải theo lifecycle JPA. Có thể dùng callback cho logic khởi tạo cache hoặc trạng thái dẫn xuất không persistent, nhưng không nên dùng nó để che giấu một mapping sai hay phụ thuộc vào setter có tác dụng phụ.

Dù chọn access type nào, bất biến quan trọng vẫn nên được bảo vệ bằng thiết kế miền nghiệp vụ, transaction và constraint database theo nhu cầu.

## 9. Trường hợp kế thừa và `@MappedSuperclass`

Entity có thể kế thừa một lớp chứa ID và các thuộc tính dùng chung:

```java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;

@MappedSuperclass
@Access(AccessType.FIELD)
public abstract class BaseEntity {

    @Id
    @GeneratedValue
    private Long id;

    public Long getId() {
        return id;
    }
}

@Entity
@Access(AccessType.FIELD)
public class BlogPost extends BaseEntity {

    private String title;

    protected BlogPost() {
    }

    public String getTitle() {
        return title;
    }
}
```

Ý nghĩa:

- `BaseEntity` là mapped superclass, không phải entity query độc lập.
- `@Id` đặt trên field của lớp cha và được kế thừa vào mapping entity con.
- Thống nhất field access giữa lớp cha và lớp con giúp tránh hiểu nhầm vị trí annotation mapping.
- Nếu lớp con dùng property access hoặc các thành viên đặc biệt dùng access khác, phải cấu hình `@Access` đúng phạm vi và tuân theo quy tắc override của JPA.

Không nên di chuyển `@Id` giữa field và getter một cách tùy tiện trong hierarchy. Việc đặt annotation thiếu nhất quán có thể khiến mapping không được xác định như tác giả mong muốn.

**Thiết kế tốt:** quy định một access type mặc định cho hệ phân cấp, ghi rõ ngoại lệ bằng `@Access` và tập trung annotation ánh xạ ở đúng lớp sở hữu persistent member.

## 10. `@Embeddable` và kiểu truy cập

Một entity có thể dùng đối tượng nhúng để nhóm các giá trị:

```java
@Embeddable
public class Address {
    private String street;
    private String city;

    protected Address() {
    }

    public Address(String street, String city) {
        this.street = street;
        this.city = city;
    }

    public String getStreet() { return street; }
    public String getCity() { return city; }
}
```

```java
@Entity
@Access(AccessType.FIELD)
public class Warehouse {

    @Id
    private Long id;

    @Embedded
    private Address address;

    protected Warehouse() {
    }
}
```

Khi một embeddable không khai báo `@Access` tường minh, kiểu truy cập mặc định của nó chịu ảnh hưởng bởi nơi sử dụng trong entity sở hữu theo quy tắc JPA. Vì vậy, nếu cùng một lớp `Address` được nhúng ở nhiều entity có access type khác nhau, việc thêm `@Access(AccessType.FIELD)` hoặc `@Access(AccessType.PROPERTY)` trực tiếp vào embeddable có thể giúp xác định ý định rõ ràng.

Ví dụ:

```java
@Embeddable
@Access(AccessType.FIELD)
public class Address {
    private String street;
    private String city;

    protected Address() {
    }

    public Address(String street, String city) {
        this.street = street;
        this.city = city;
    }
}
```

Annotation như `@AttributeOverride` được dùng để đổi tên cột khi nhúng và không tự thay thế việc quyết định kiểu truy cập. Đối tượng nhúng cũng cần cấu trúc phù hợp với các yêu cầu của JPA đối với embeddable.

## 11. Những nhầm lẫn thường gặp

### 11.1. “Có getter là đang dùng property access”

**Sai.** Gần như mọi entity dùng field access vẫn có getter để ứng dụng đọc trạng thái. Access type được xác định bởi mapping annotation và `@Access`, không bởi sự tồn tại của getter.

```java
@Id
private Long id; // FIELD.

public Long getId() {
    return id; // Không khiến JPA chuyển sang PROPERTY.
}
```

### 11.2. “`private` field thì JPA không thể lưu”

**Sai.** Field access cho phép ánh xạ field `private` theo cơ chế của provider. Không cần đổi thành `public` chỉ để ORM truy cập.

### 11.3. “Đặt `@Column` cả trên field lẫn getter để chắc chắn”

**Không nên.** Mapping trùng hoặc đặt annotation ở nhiều vị trí ngoài quy tắc `@Access` rõ ràng có thể gây mapping sai hoặc không xác định. Mỗi persistent attribute nên có một nguồn cấu hình minh bạch.

### 11.4. “Property access tương đương với JSON property”

**Sai.** JPA và thư viện JSON (ví dụ Jackson) có quy tắc riêng. Một getter có thể mang annotation `@JsonProperty` nhưng JPA vẫn ánh xạ qua field nếu entity dùng field access. Đổi tên JSON không đồng nghĩa đổi tên cột SQL.

### 11.5. “Property access làm Hibernate luôn gọi getter mỗi khi có câu SQL”

Không nên giả định chi tiết nội bộ như vậy. JPA định nghĩa cách ánh xạ và truy cập persistent state; provider có thể dùng reflection, proxy, interception và bytecode enhancement. Số lần getter/setter được gọi trong thực tế có thể khác nhau giữa phiên bản, cấu hình và trạng thái entity. Thiết kế getter/setter an toàn, ít tác dụng phụ vẫn là lựa chọn cần thiết.

### 11.6. “Dùng FIELD thì không có lazy loading”

**Sai.** Field/property access và `FetchType.LAZY` là các trục khác nhau. Lazy loading phụ thuộc loại quan hệ, mapping, khả năng của provider, proxy/enhancement và trạng thái persistence context. Chọn field access không tự làm mọi thuộc tính thành eager hoặc lazy.

### 11.7. “`@Transient` đặt ở đâu cũng được”

**Sai.** Cần đặt `@Transient` tại **thành viên** tương ứng với access type đang có hiệu lực. Dùng Java `transient` có nghĩa riêng ở mức ngôn ngữ; nó không phải phương án thay thế hoàn toàn cho mọi cấu hình property access.

### 11.8. “Dùng FIELD sẽ tránh hết mọi bất biến sai”

**Sai.** Field access có thể bỏ qua setter khi hydrate, nên dữ liệu trong database vẫn cần hợp lệ. Nếu bảng chứa dữ liệu lỗi hoặc thao tác cạnh tranh làm vi phạm invariant, field access không thể tự sửa. Cần kết hợp validation phù hợp, transaction, constraint và logic domain.

### 11.9. “Đổi access type chỉ là di chuyển annotation”

Không hẳn. Khi chuyển từ `FIELD` sang `PROPERTY`, cần xem tất cả persistent property có getter/setter hợp lệ hay không; có property dẫn xuất vô tình được ánh xạ không; getter/setter có logic làm biến đổi dữ liệu không; hierarchy và embeddable có phụ thuộc access mặc định không.

### 11.10. “Java `record` là lựa chọn thay thế tự nhiên cho JPA entity ở mọi chế độ”

Java `record` thường phù hợp DTO và nhiều value object, nhưng entity JPA chuẩn có yêu cầu về constructor, khả năng quản lý và cấu trúc class không giống một Java record bất biến. Chọn `FIELD` không tự biến một Java `record` thành entity JPA hợp lệ. Việc dùng record làm embeddable hoặc projection phải dựa vào phiên bản đặc tả và provider cụ thể.

## 12. So sánh trực tiếp

| Tiêu chí | FIELD access | PROPERTY access |
|---|---|---|
| **Thành viên làm cơ sở ánh xạ** | Field | JavaBeans property |
| **Nơi đặt `@Id`/`@Column`** | Trên field | Trên getter |
| **Mặc định khi `@Id` ở vị trí tương ứng** | `@Id` ở field | `@Id` ở getter |
| **Setter cần cho JPA?** | Không cần cho persistent field | Cần accessor phù hợp cho property persistent thông thường |
| **Field `private`** | Được ánh xạ | Là backing field nội bộ, JPA làm việc với property |
| **Logic trong getter/setter** | Không nhất thiết được gọi khi ORM truy cập field | Cần đặc biệt chú ý vì accessor tham gia hợp đồng persistence |
| **Loại field/property phụ trợ** | `@Transient` trên field, hoặc Java `transient` với field mặc định | `@Transient` trên getter |
| **Hỗ trợ đóng gói hành vi** | Dễ giữ setter nghiệp vụ ở phạm vi hẹp | Có thể nhưng phải thiết kế accessor phù hợp với JPA |
| **Hỗ trợ quan hệ, version, ID ghép** | Có | Có |
| **Dirty checking** | Có với managed entity | Có với managed entity |
| **Tự quyết định tên bảng/cột?** | Không | Không |
| **Nên chọn khi** | Muốn trạng thái nội bộ được ánh xạ trực tiếp, getter/setter phục vụ domain | Muốn getter/setter là bề mặt ánh xạ có chủ đích và hành vi ổn định |

Không có một access type luôn “nhanh hơn” hoặc “đúng hơn” cho mọi dự án. Hiệu năng thực tế chịu ảnh hưởng nhiều bởi truy vấn, fetch plan, index, batching, cache và cơ chế provider. Trước hết hãy chọn theo yêu cầu đóng gói và cách thiết kế entity.

## 13. Ví dụ xuyên suốt: một giao dịch cập nhật

Giả sử bảng:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    version BIGINT NOT NULL
);
```

Có row:

| id | full_name | version |
|---:|---|---:|
| 12 | Nguyễn An | 0 |

Ứng dụng tìm khách hàng và đổi tên:

```java
CustomerFieldAccess customer =
    entityManager.find(CustomerFieldAccess.class, 12L);

customer.rename("Trần An");

// Trong transaction, JPA phát hiện trạng thái managed thay đổi.
// Khi flush/commit thích hợp, database có thể nhận UPDATE.
```

Một lệnh SQL minh họa có thể là:

```sql
UPDATE customer
SET full_name = 'Trần An',
    version = 1
WHERE id = 12 AND version = 0;
```

SQL chính xác còn phụ thuộc provider, database và cấu hình phiên bản. Mục đích của ví dụ là chỉ ra:

- Trong **field access**, `rename()` sửa field `name`; ORM theo dõi thuộc tính persistent được ánh xạ ở field.
- Trong **property access**, thao tác đổi tên có thể đi qua `setName()`; ORM ánh xạ thuộc tính theo property tương ứng.
- Ở cả hai chế độ, `@Version` giúp JPA kiểm soát optimistic locking khi được ánh xạ đúng.
- `flush()` đồng bộ SQL trong transaction, còn `commit` mới xác nhận transaction. Access type không thay đổi nguyên tắc đó.

Nếu chỉ chuyển annotation `@Version` từ field sang getter mà không đồng bộ access type, bạn có thể làm mapping version khác dự kiến. Quy tắc tương tự áp dụng cho `@Embedded`, `@ManyToOne` và `@OneToMany`.

## 14. Lựa chọn trong dự án thực tế

Khi thiết kế một entity mới, có thể suy nghĩ theo các bước:

1. **Xác định định danh.** Entity dùng `@Id` hay `@EmbeddedId`? Thuộc tính ID được khai báo ở lớp hiện tại hay `@MappedSuperclass`?
2. **Chọn bề mặt persistent state.** Muốn ORM làm việc trực tiếp với field hay qua getter/setter?
3. **Khai báo nhất quán.** Đặt `@Access` tường minh khi điều đó giúp loại bỏ mơ hồ; đặt `@Id`, `@Column`, quan hệ, `@Version`, `@Transient` đúng vị trí.
4. **Tách nghiệp vụ khỏi truy cập lưu trữ.** Getter/setter dùng cho persistence cần an toàn; những thay đổi phức tạp nên có phương thức nghiệp vụ rõ ý nghĩa.
5. **Giữ các đối tượng phụ trợ ra khỏi mapping.** Cache, nhãn hiển thị, kết quả tính toán cần được loại trừ đúng cách theo access type.
6. **Nhất quán trong kế thừa và embedded type.** Đọc ý định ánh xạ tại mapped superclass và embeddable, dùng `@Access` để giải quyết ngoại lệ có chủ đích.

Một số tình huống lựa chọn:

| Tình huống | Lựa chọn thường thuận tiện | Vì sao |
|---|---|---|
| Entity có nhiều invariant và muốn giới hạn setter công khai | `FIELD` | JPA ánh xạ state trực tiếp, ứng dụng dùng phương thức nghiệp vụ |
| Entity legacy đã có JavaBeans getter/setter rõ ràng, ổn định | `PROPERTY` | Có thể giữ mapping gắn với contract accessor |
| ID khai báo trong mapped superclass bằng field | Giữ `FIELD` nhất quán trong hierarchy | Giảm rủi ro mixing annotation |
| Một attribute riêng cần getter làm bề mặt ánh xạ | `@Access(PROPERTY)` ở attribute có chủ đích | Override rõ ràng, tránh mapping hai lần |
| Muốn đổi tên cột nhưng giữ tên field Java | Cả hai đều dùng `@Column(name = "...")` | Access type không quyết định tên cột |
| Muốn trả JSON khác cấu trúc entity | DTO riêng | JSON contract và JPA mapping là những vấn đề khác nhau |

## 15. Bài tập nhận diện

### Tình huống A: Dự đoán access type

```java
@Entity
public class Movie {
    @Id
    private Long id;

    private String title;

    public Long getId() { return id; }
    public String getTitle() { return title; }

    protected Movie() {}
}
```

**Câu hỏi:** JPA mặc định dùng field hay property access? Nên đặt `@Column(name = "movie_title")` ở đâu?

**Gợi ý:** `@Id` nằm trên field nên mặc định là **field access** khi hierarchy nhất quán. Đặt `@Column` trên field `title`.

### Tình huống B: Đọc code có annotation đặt sai

```java
@Entity
public class Device {
    private Long id;
    private String serialNumber;

    @Id
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    @Column(name = "serial_no")
    private String getSerialNumberInternal() {
        return serialNumber;
    }

    protected Device() {}
}
```

**Câu hỏi:** Đoạn mapping `serialNumber` có hợp lệ theo ý định không?

**Gợi ý:** Không. Mặc định property access do `@Id` trên getter, nhưng mapping lại gắn lên một phương thức private không phải JavaBeans getter tương ứng. Cần có `getSerialNumber()`/`setSerialNumber()` hợp lệ và đặt `@Column` trên getter thực sự, hoặc chuyển entity sang field access nhất quán.

### Tình huống C: Mô hình chứa cache

```java
@Entity
@Access(AccessType.FIELD)
public class Report {
    @Id
    private Long id;

    private String content;
    private String cachedPreview;

    protected Report() {}
}
```

**Câu hỏi:** `cachedPreview` có được coi là persistent không nếu không có annotation?

**Gợi ý:** Có thể **có**, vì field thường được ánh xạ theo mặc định khi dùng `FIELD`. Nếu đó là cache không được lưu, đánh dấu field `@Transient` hoặc dùng cơ chế loại trừ phù hợp.

### Tình huống D: Thêm getter làm thay đổi dữ liệu

```java
@Entity
@Access(AccessType.PROPERTY)
public class Item {
    private Long id;
    private String code;

    @Id
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getCode() {
        return code == null ? null : code.trim().toUpperCase();
    }

    public void setCode(String code) {
        this.code = code;
    }

    protected Item() {}
}
```

**Câu hỏi:** Nguy cơ là gì?

**Gợi ý:** Getter biến đổi giá trị, nên giá trị JPA đọc qua property có thể khác backing field ban đầu. Có thể xảy ra khác biệt trong round-trip lưu/đọc và logic dirty checking. Nếu chuẩn hóa là quy tắc nghiệp vụ, hãy cân nhắc chuẩn hóa tại thời điểm nhận input và lưu một giá trị nhất quán, không biến đổi bất ngờ ở getter persistence.

### Tình huống E: Chuyển access type

Một entity đang dùng `@Id` ở field và các getter đã có sẵn. Bạn chuyển `@Id` lên getter, các `@Column` vẫn ở field.

**Câu hỏi:** Có thể chỉ đổi một dòng rồi coi là xong?

**Gợi ý:** Không. Khi access type mặc định chuyển sang property, cần chuyển toàn bộ mapping liên quan sang đúng getter hoặc cấu hình override rõ ràng, đồng thời xem xét các property có thể vô tình được mapping và yêu cầu setter.

## 16. Kết luận

**Field access** và **property access** là hai cách JPA xác định **persistent state của entity nằm ở đâu và được đọc/ghi như thế nào**:

- **`FIELD`:** annotation đặt trên field; JPA tiếp cận field; getter/setter có thể được thiết kế chủ yếu cho nghiệp vụ.
- **`PROPERTY`:** annotation đặt trên getter; JavaBeans property là bề mặt persistence; phải quan tâm đến hành vi của getter/setter.
- **`@Id`/`@EmbeddedId`** thường cho biết access type mặc định khi mapping nhất quán, còn **`@Access`** giúp khai báo rõ và override có chủ đích.
- Quy tắc này cũng tác động đến các annotation như `@Column`, `@Version`, `@Transient`, `@Embedded` và các quan hệ, nhất là trong hierarchy và embeddable.
- Dù dùng cách nào, entity vẫn có identity, lifecycle và dirty checking theo JPA; tên bảng/cột, chiến lược sinh ID và transaction là những khía cạnh độc lập.

Khi đọc một entity lạ, hãy **tìm vị trí `@Id` trước, kiểm tra `@Access`, rồi xem các annotation khác có được đặt nhất quán không**. Thói quen này giúp nhận biết và tránh nhiều lỗi mapping khó phát hiện trong dự án ORM/JPA.
