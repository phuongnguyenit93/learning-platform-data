# Ràng buộc lớp entity và khả năng dùng đối tượng bất biến theo phiên bản

Trong Java thuần, một đối tượng bất biến (*immutable object*) thường được thiết kế bằng `final class`, các trường `private final`, khởi tạo đầy đủ qua constructor và không cho sửa trạng thái sau khi tạo. Cách thiết kế này có nhiều ưu điểm: dễ suy luận, ít lỗi do thay đổi ngoài ý muốn và thuận tiện khi dùng làm value object.

Nhưng **entity của JPA không phải một Java object tùy ý**. Entity có định danh lâu dài trong cơ sở dữ liệu, phải được provider khởi tạo khi truy vấn, được theo dõi trong persistence context và có thể được đồng bộ lại khi trạng thái thay đổi. Vì vậy, đặc tả JPA đặt ra ràng buộc về **loại lớp, constructor, từ khóa `final`, trường dữ liệu và cách truy cập trạng thái**.

Điểm dễ nhầm là **không cho mã nghiệp vụ thay đổi entity** khác với **entity bất biến tuyệt đối theo cú pháp Java**. Một lớp không có public setter vẫn có thể hợp lệ với JPA; ngược lại, một `record` Java là immutable nhưng không thể được đánh dấu `@Entity` theo Jakarta Persistence 3.2. Khả năng dùng `record` trong mapping cũng khác nhau giữa các phiên bản đặc tả.

Bài học này giải thích các giới hạn đó, cách thiết kế entity có kiểm soát thay đổi, và cách tận dụng immutable value object mà vẫn giữ tính tương thích với JPA.

## 1. Vì sao JPA đặt ra ràng buộc đối với entity?

Một đoạn mã đơn giản:

```java
Book book = em.find(Book.class, 42L);
book.changeTitle("Jakarta Persistence");
// Khi flush/commit, provider có thể phát hiện thay đổi và gửi UPDATE.
```

Ẩn sau `find()` là nhiều công việc của provider:

1. Dùng metadata xác định `Book` ánh xạ đến bảng nào và khóa chính nằm ở đâu.
2. Tạo hoặc tìm lại một instance tương ứng trong persistence context.
3. Đọc dữ liệu từ JDBC và điền vào những thuộc tính được ánh xạ.
4. Có thể chuẩn bị proxy hoặc enhancement để hỗ trợ lazy loading và theo dõi thay đổi.
5. Phát hiện sự thay đổi của entity đang được quản lý rồi đồng bộ xuống cơ sở dữ liệu.

Một đối tượng thiết kế theo kiểu `final class`, chỉ có constructor nhận mọi thuộc tính và mọi trường đều `final` không đáp ứng trực tiếp những cơ chế này theo hợp đồng portable của JPA. Một số provider hỗ trợ thêm các trường hợp riêng; nhưng **chạy được với một provider không đồng nghĩa với tuân thủ đặc tả để chuyển sang provider khác**.

### Entity và value object không có cùng nhiệm vụ

| Đặc tính | Entity | Value object |
|---|---|---|
| Cách xác định cùng một đối tượng nghiệp vụ | Dựa trên định danh ổn định, ví dụ khóa chính | Dựa trên giá trị các thuộc tính |
| Vòng đời | New, managed, detached, removed | Thường tạo ra rồi thay bằng instance khác |
| Quan hệ với JPA | Có persistence identity và persistence context | Thường là basic type, embeddable hoặc DTO |
| Khả năng thay đổi | Có thể được provider theo dõi và cập nhật | Thường ưu tiên immutable |
| Ví dụ | `Book`, `Customer`, `Order` | `Address`, `Money`, `DateRange` |

Trong thiết kế hướng miền (DDD), bất biến hóa value object và giới hạn quyền sửa entity thường bổ trợ nhau: entity giữ identity, còn các giá trị cấu thành có thể được thay nguyên khối.

## 2. Những yêu cầu bắt buộc đối với lớp `@Entity`

Với **Jakarta Persistence 3.2**, quy tắc cốt lõi ở mục *The Entity Class* là:

- Lớp được đánh dấu `@Entity` hoặc khai báo là entity trong XML mapping.
- Entity phải là **lớp top-level** hoặc **lớp lồng tĩnh** (`static nested class`). Không được dùng `enum`, `record` hoặc `interface` làm entity.
- Entity phải có constructor **không tham số, `public` hoặc `protected`** để provider tạo instance. Có thể có thêm constructor khác cho ứng dụng.
- Bản thân lớp entity **không được `final`**.
- Các phương thức của entity và những **instance field được persistence quản lý** **không được `final`**.
- Entity có thể là lớp `abstract` hoặc lớp cụ thể, có thể tham gia quan hệ kế thừa phù hợp.
- Trạng thái persistent phải được biểu diễn thông qua field hoặc JavaBeans property theo quy tắc access type của JPA.
- Mọi entity phải có khóa chính, được khai báo trên entity root hoặc mapped superclass trong hierarchy.

Những quy tắc này là yêu cầu của **đặc tả**. Một provider có thể mở rộng khả năng ánh xạ ngoài đặc tả, nhưng mã dựa vào hành vi mở rộng sẽ mất bớt tính di động.

### 2.1. Entity hợp lệ với field access

```java
package example.domain;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "books")
@Access(AccessType.FIELD)
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Version
    private long version;

    protected Book() {
        // JPA provider dùng constructor này khi khởi tạo entity.
    }

    public Book(String title) {
        changeTitle(title);
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void changeTitle(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Title must not be blank");
        }
        this.title = newTitle;
    }
}
```

Lớp `Book` không phải `final`, có `protected Book()`, các field persistent không phải `final`, và có một `@Id`. Nhờ `@Access(AccessType.FIELD)`, provider có thể đọc/ghi các field được ánh xạ mà ứng dụng không cần tạo public setter cho `id` hoặc `version`.

Ứng dụng vẫn giữ một **giao diện nghiệp vụ có kiểm soát**: muốn đổi tiêu đề phải đi qua `changeTitle()`, nơi kiểm tra quy tắc hợp lệ. Đây là ví dụ của **encapsulation/controlled mutability**, không phải immutable object tuyệt đối.

### 2.2. Constructor không tham số là để provider khởi tạo

**Không đúng nếu muốn portable:**

```java
@Entity
public class Book {
    @Id
    private Long id;
    private String title;

    public Book(String title) {
        this.title = title;
    }
}
```

Khi có constructor nhận tham số do lập trình viên khai báo, Java không tự tạo constructor không tham số. Entity trên thiếu constructor mà JPA yêu cầu.

**Sửa:**

```java
@Entity
public class Book {
    @Id
    private Long id;
    private String title;

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
    }
}
```

Constructor không tham số không cần làm tất cả công việc của constructor nghiệp vụ. Provider có thể khởi tạo một instance tạm thời rồi nạp trạng thái từ cơ sở dữ liệu. Vì thế, đừng viết logic nghiệp vụ quan trọng trong no-arg constructor với giả định mọi trường đã có giá trị đầy đủ tại thời điểm đó.

Constructor `private` hoặc package-private có thể được một số provider chấp nhận trong các điều kiện riêng, nhưng không đáp ứng yêu cầu portable `public`/`protected` của Jakarta Persistence 3.2.

### 2.3. Entity không được `final`

```java
@Entity
public final class Book { // Không hợp lệ theo chuẩn JPA.
    @Id
    private Long id;

    protected Book() {}
}
```

Một lý do thực tiễn là nhiều provider sử dụng cơ chế **proxy kế thừa từ entity** để thực hiện lazy loading. Lớp `final` không thể được subclass; phương thức `final` không thể bị override. Tuy nhiên, ràng buộc `final` là yêu cầu của đặc tả, không chỉ là một mẹo để tránh lỗi lazy loading: ngay cả khi truy vấn hiện tại không dùng proxy, class `final` vẫn không phải thiết kế entity portable.

Các entity `abstract` được chấp nhận và hữu ích cho inheritance mapping. Ví dụ một entity trừu tượng `Payment` có các entity con `CardPayment` và `TransferPayment`. Việc một entity là `abstract` không xóa bỏ các quy tắc về constructor hoặc field persistent.

### 2.4. Field persistent không được `final`

```java
@Entity
public class Book {
    @Id
    private final Long id;      // Không hợp lệ theo JPA chuẩn.

    private final String title; // Persistent field cũng không được final.

    // ...
}
```

Các field Java `final` thường chỉ được gán một lần khi khởi tạo. Trái lại, provider cần đưa dữ liệu truy vấn từ database vào entity theo access strategy và có thể thay đổi trạng thái khi merge, refresh hoặc đồng bộ relationship.

Từ khóa `final` của field còn cần phân biệt với **định danh bất biến về mặt nghiệp vụ**. Không cho người dùng thay khóa chính **không đòi hỏi khai báo Java field `final`**. Ta có thể dùng `private Long id`, không có `setId()`, chỉ cung cấp `getId()`. Provider vẫn có thể nạp/gán id khi cần.

Các hằng số không phải persistent state, chẳng hạn `private static final String TYPE = "BOOK";`, không nằm trong nhóm *persistent instance variable* này. Tránh hiểu nhầm rằng mọi khai báo `final` trên bất kỳ dữ liệu nào trong entity đều bị cấm.

### 2.5. Visibility của field và access type

Theo đặc tả, các instance field của entity dùng để biểu diễn trạng thái phải có visibility `private`, `protected` hoặc package-private. Field persistent không nên được phơi ra dưới dạng `public`.

JPA có hai cách truy cập chủ yếu:

| Cách truy cập | Metadata thường đặt ở đâu? | Cách provider đọc và ghi giá trị |
|---|---|---|
| **Field access** | Field, ví dụ `@Id private Long id` | Provider truy cập trực tiếp field |
| **Property access** | Getter, ví dụ `@Id public Long getId()` | Provider dùng JavaBeans property accessors |

Khi dùng **field access**, có thể ẩn setter và chỉ cung cấp business method. Khi dùng **property access**, getter phải có visibility phù hợp, và phần truy cập property phải cho phép provider thực hiện những thao tác đọc/ghi cần thiết. Đặc tả định nghĩa chi tiết yêu cầu với JavaBeans property; không nên xóa setter một cách tùy tiện trong mô hình property access chỉ để ép class “immutable”.

Ví dụ property access:

```java
@Entity
@Access(AccessType.PROPERTY)
public class Category {
    private Long id;
    private String name;

    protected Category() {}

    @Id
    public Long getId() {
        return id;
    }

    protected void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    protected void setName(String name) {
        this.name = name;
    }
}
```

Mã nghiệp vụ không nhận public setter ở đây; provider vẫn có setter cần thiết. Trong thực hành, field access thường đơn giản hơn khi thiết kế entity với các hành vi nghiệp vụ thay cho setter hàng loạt.

### 2.6. Entity identity và trạng thái persistent

Entity cần khóa chính `@Id` hoặc `@EmbeddedId` để định danh trong persistence context và cơ sở dữ liệu. Tính bất biến của **khóa chính sau khi entity đã persistent** là một nguyên tắc quan trọng:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;

public Long getId() {
    return id;
}

// Không cung cấp public setId(Long).
```

Khi entity đang managed, ứng dụng không nên tự sửa khóa chính. Việc thay đổi khóa chính của một entity đã persistent không được JPA bảo đảm có ngữ nghĩa portable. Nếu cần một mã nghiệp vụ có thể thay đổi, hãy cân nhắc mô hình hóa nó như một thuộc tính riêng, không phải identifier.

Một entity khác biệt với immutable value object ở chỗ nó có **identity và lifecycle**. Trong cùng persistence context, JPA duy trì một managed instance nhất quán cho một entity identity; nếu muốn sửa đối tượng đó, thường thay đổi state trên instance managed, không tạo một instance mới mỗi lần giống như thay `record`.

## 3. Java immutable object và “entity chỉ đọc” khác nhau thế nào?

Khái niệm “bất biến” có ít nhất bốn cấp độ dễ bị trộn lẫn:

| Mục tiêu | Cách thực hiện thường gặp | Có biến entity thành Java immutable object không? |
|---|---|---|
| **Không công khai khả năng sửa** | Private field, không public setter, chỉ có business method | Không; field vẫn thay đổi nội bộ/provider |
| **Không cho sửa một số thuộc tính sau INSERT** | Mapping như `@Column(updatable = false)` | Không; chỉ ảnh hưởng SQL cập nhật thuộc tính đó |
| **Provider xem một entity là read-only** | Cơ chế provider-specific như Hibernate `@Immutable` | Không; Java object vẫn có thể bị sửa trong RAM |
| **Bất biến thực sự ở cấp ngôn ngữ** | `final class`, `private final` field, constructor đầy đủ/`record` | Không portable dưới dạng `@Entity` theo JPA 3.2 |

Ví dụ:

```java
@Column(name = "created_by", updatable = false)
private String createdBy;
```

`updatable = false` khiến cột này bị loại khỏi các câu lệnh `UPDATE` sinh từ mapping tương ứng. Nó **không ngăn** code gọi một setter hay thay field trong bộ nhớ, không bảo vệ bản ghi trước thao tác SQL trực tiếp, và cũng không tự động áp dụng cơ chế read-only cho toàn bộ entity.

Tương tự, `@Version` hỗ trợ **optimistic locking** để phát hiện xung đột cập nhật. Nó không làm entity immutable.

### “Không có setter” chưa phải immutable

```java
@Entity
public class UserAccount {
    @Id
    private Long id;

    private String displayName;

    protected UserAccount() {}

    public String getDisplayName() {
        return displayName;
    }

    public void rename(String newName) {
        this.displayName = newName;
    }
}
```

Về API, mã ngoài không được gán tùy ý qua `setDisplayName(...)`. Nhưng `rename()` vẫn thay đổi state. Khi entity managed, provider có thể dirty-check rồi cập nhật CSDL.

Đó thường là thiết kế **phù hợp hơn cho entity JPA**: giới hạn điểm thay đổi, giữ invariant, nhưng vẫn cho provider thực hiện vòng đời ORM.

## 4. Quy tắc thay đổi qua các phiên bản JPA/Jakarta Persistence

Ràng buộc entity có lịch sử lâu dài và nhìn chung không thay đổi đột ngột. Những thay đổi đáng chú ý liên quan tới immutable data object chủ yếu nằm ở **embeddable và composite-key classes**, không phải việc biến `@Entity` thành Java `record`.

| Đặc tả | Namespace / đặc điểm | Entity class | Khả năng dùng immutable record |
|---|---|---|---|
| **JPA 2.2** | `javax.persistence` | Top-level class; có no-arg `public`/`protected`; class/method/persistent field không `final` | Java `record` không phải mô hình portable của JPA 2.2 |
| **Jakarta Persistence 3.0** | Chuyển sang `jakarta.persistence` | Vẫn giữ yêu cầu top-level, non-final, no-arg | Chưa chuẩn hóa record embeddable |
| **Jakarta Persistence 3.1** | Bổ sung nhiều API, giữ ràng buộc class cốt lõi | Vẫn yêu cầu top-level, non-final, no-arg | Record chưa là embeddable portable theo chuẩn 3.1 |
| **Jakarta Persistence 3.2** | Mở rộng mô hình class và khóa | Entity có thể top-level **hoặc static nested**; vẫn không nhận `record`/`final` | **Cho phép record làm `@Embeddable` và lớp composite primary key** |
| **Jakarta Persistence 4.0 (bản nháp đang phát triển)** | API đang được thiết kế và thay đổi | Tài liệu nháp vẫn giữ entity non-final, no-arg, không dùng record làm entity | Chỉ dựa vào tính năng của bản chính thức được provider hỗ trợ khi triển khai |

**Lưu ý về phiên bản:** bảng trên nói về mức đảm bảo của **đặc tả**, không khẳng định từng bản Hibernate/EclipseLink đều đã triển khai đầy đủ các tính năng tương ứng. Trước khi chọn code dùng record, hãy kiểm tra *phiên bản Jakarta Persistence API*, *provider*, *phiên bản Java* và kết quả kiểm chứng trên CSDL mục tiêu.

### 4.1. Đổi `javax.persistence` sang `jakarta.persistence` không xóa ràng buộc entity

Ví dụ hai import thuộc hai thế hệ API:

```java
// JPA 2.2
import javax.persistence.Entity;

// Jakarta Persistence 3.x
import jakarta.persistence.Entity;
```

Việc đổi namespace là một thay đổi quan trọng cho dependency và môi trường chạy. Nó **không tự động cho phép** dùng `final entity`, `record @Entity` hoặc bỏ no-arg constructor trong chương trình portable.

### 4.2. Bước ngoặt ở 3.2: record làm embeddable, không phải entity

Java `record` thường phù hợp để chứa **giá trị**. Trong Jakarta Persistence 3.2, một `record` có thể được đánh dấu `@Embeddable`:

```java
package example.domain;

import jakarta.persistence.Embeddable;

@Embeddable
public record Address(
        String street,
        String city,
        String countryCode
) {}
```

Một record có các thành phần `final` và constructor nhận giá trị, không có constructor không tham số. Ở phiên bản 3.2, đây vẫn là **embeddable hợp lệ theo đặc tả** vì record được hỗ trợ bằng cách khởi tạo qua constructor phù hợp với thành phần của record.

Record vẫn **không được** khai báo:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity // Sai theo chuẩn Jakarta Persistence 3.2.
public record Book(Long id, String title) {}
```

Nguyên nhân không phải annotation sai cú pháp Java, mà là `record` không thỏa yêu cầu của một entity class JPA: bản thân record là `final`, thành phần của nó là `final`, không có mô hình setter/mutation như entity và không đáp ứng quy tắc entity.

## 5. Thiết kế entity mutable có kiểm soát + embeddable immutable

Một mô hình mạnh là để entity giữ khóa chính và lifecycle, trong khi các phần mô tả bằng giá trị được tạo dưới dạng immutable record.

### 5.1. Entity sở hữu một `Address` bất biến

```java
package example.domain;

import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @Embedded
    private Address address;

    protected Customer() {}

    public Customer(String name, Address address) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        if (address == null) {
            throw new IllegalArgumentException("address must not be null");
        }
        this.name = name;
        this.address = address;
    }

    public Long getId() {
        return id;
    }

    public Address getAddress() {
        return address;
    }

    public void moveTo(Address newAddress) {
        if (newAddress == null) {
            throw new IllegalArgumentException("address must not be null");
        }
        this.address = newAddress;
    }
}
```

Khi thay địa chỉ:

```java
Customer customer = em.find(Customer.class, 10L);
customer.moveTo(new Address(
    "12 Nguyen Hue",
    "Ho Chi Minh City",
    "VN"
));
```

Không có thao tác `customer.getAddress().setCity(...)` vì `Address` là record bất biến. Thay vì sửa từng thuộc tính của value object, ứng dụng **tạo một giá trị mới và gán vào field của entity đang managed**. Provider nhận biết entity state đã thay đổi rồi đồng bộ các cột của địa chỉ theo mapping.

Điểm phân biệt quan trọng:

- `Customer` vẫn là entity mutable: field `address` không phải `final`.
- `Address` là embeddable không có identity riêng: giá trị sống như một phần state của `Customer`.
- Không dùng `em.persist(address)` để lưu riêng `Address` như entity.
- Không được xem cùng một embedded object chia sẻ giữa nhiều entity là một đối tượng có vòng đời độc lập; với record bất biến, có thể tái sử dụng giá trị tại tầng Java nhưng mỗi mapping embeddable vẫn là state của entity sở hữu.

### 5.2. Ví dụ trước phiên bản 3.2: embeddable class thông thường

Trong JPA 2.2 hoặc Jakarta Persistence 3.0/3.1, để giữ mã portable, có thể biểu diễn `Address` bằng lớp `@Embeddable` thông thường:

```java
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {
    private String street;
    private String city;
    private String countryCode;

    protected Address() {}

    public Address(String street, String city, String countryCode) {
        this.street = street;
        this.city = city;
        this.countryCode = countryCode;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getCountryCode() {
        return countryCode;
    }
}
```

Mã ví dụ dùng namespace Jakarta 3.0/3.1; nếu phải biên dịch với JPA 2.2, hãy thay import thành `javax.persistence.Embeddable`.

Class này không có public setter, nên ứng dụng khó sửa nó từ bên ngoài. Tuy vậy các field **không `final`**, và lớp vẫn được thiết kế để provider có thể khởi tạo/nạp dữ liệu. Đây là **giao diện gần bất biến**, chưa phải immutable theo quy tắc của ngôn ngữ Java.

Nếu một provider cũ hỗ trợ record embeddable thông qua tiện ích riêng trước Jakarta Persistence 3.2, đó là khả năng **provider-specific**, không nên gọi là bảo đảm của Jakarta Persistence 3.1.

### 5.3. Khi cần immutable composite key

Trong Jakarta Persistence 3.2, lớp khóa chính tổng hợp có thể là Java record. Ví dụ dùng `@EmbeddedId`:

```java
package example.domain;

import jakarta.persistence.Embeddable;

@Embeddable
public record OrderLineId(
    Long orderId,
    Integer lineNo
) {}
```

```java
package example.domain;

import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
public class OrderLine {
    @EmbeddedId
    private OrderLineId id;

    private String productName;

    protected OrderLine() {}

    public OrderLine(OrderLineId id, String productName) {
        this.id = id;
        this.productName = productName;
    }

    public OrderLineId getId() {
        return id;
    }
}
```

Khóa `OrderLineId` có semantics theo **giá trị** và được Java sinh `equals()`, `hashCode()`. Đây là lợi thế của record cho composite key, nhưng cần lưu ý:

- Các thành phần của khóa phải có type phù hợp với các cột CSDL.
- Equality của khóa phải nhất quán với equality của các kiểu dữ liệu trong CSDL.
- Sau khi entity được lưu, không nên thay `id` sang một giá trị khóa chính khác.
- Khả năng dùng record làm `@EmbeddedId` hoặc `@IdClass` cần provider thực sự hỗ trợ Jakarta Persistence 3.2 hoặc tính năng tương đương.

Khóa tổng hợp với `@IdClass` cũng có thể dùng record từ 3.2, miễn ánh xạ tên và kiểu thuộc tính giữa id class với entity tuân thủ quy tắc của JPA. Không được suy ra rằng **mọi record** đều là entity; record ở đây chỉ đóng vai trò **lớp biểu diễn khóa**.

## 6. Hibernate có thể chấp nhận thiết kế ngoài chuẩn ra sao?

Hibernate ORM cung cấp một số khả năng linh hoạt hơn yêu cầu portable của JPA. Chẳng hạn, tùy phiên bản và cách cấu hình bytecode enhancement:

- Có thể chấp nhận entity `final` hoặc phương thức `final` ở một số trường hợp; nhưng proxy-based lazy loading có thể bị giới hạn.
- Có thể chấp nhận no-arg constructor package-private, hoặc bổ sung constructor trong quá trình enhancement.
- Có thể xử lý một số persistent field `final`; tuy nhiên cách nạp giá trị, reflection và tương thích với phiên bản Java có thể gây rủi ro.
- Có thể hỗ trợ record value type trước khi tính năng đó được tiêu chuẩn hóa.

Vì vậy, câu hỏi không nên chỉ là **“Hibernate chạy được không?”**, mà còn là:

1. Phiên bản Hibernate đang dùng có hỗ trợ trường hợp này không?
2. Cấu hình enhancement và cách tạo proxy có ảnh hưởng gì không?
3. Khi đổi provider hoặc nâng Java/JPA, mã có còn hoạt động không?
4. Có thực sự cần phá ràng buộc chuẩn, hay chỉ cần ẩn setter và dùng immutable embeddable?

Nếu mục tiêu là giáo trình JPA và mã có thể di chuyển giữa provider, nên **tuân thủ ràng buộc non-final + no-arg + persistent fields non-final** cho entity. Chỉ sử dụng ngoại lệ provider-specific khi đã chấp nhận ràng buộc kỹ thuật và kiểm chứng tác động của nó.

### 6.1. `@Immutable` của Hibernate không biến entity thành Java record

Hibernate cung cấp `org.hibernate.annotations.Immutable`:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import org.hibernate.annotations.Immutable;

@Entity
@Immutable
public class AuditSnapshot {
    @Id
    private Long id;

    private String message;

    protected AuditSnapshot() {}

    public Long getId() {
        return id;
    }

    public String getMessage() {
        return message;
    }
}
```

Với một entity được Hibernate đánh dấu `@Immutable`, thay đổi state của entity trong bộ nhớ **không được Hibernate đồng bộ xuống database** như cập nhật thông thường; Hibernate cũng có thể giảm chi phí dirty checking/snapshot cho entity này. Đó là **chính sách ORM ở runtime** của Hibernate.

Điều này **không đồng nghĩa**:

- Class trở thành Java `final` hoặc field trở thành `final`.
- Trạng thái được bảo vệ trước mọi câu lệnh SQL trực tiếp, hệ thống khác hay thao tác ngoài ORM.
- Có thể dùng `@Immutable` theo chuẩn JPA trên mọi provider; annotation này thuộc Hibernate.
- Mọi thao tác thay đổi state đều phát sinh exception. Theo tài liệu Hibernate, các thay đổi bộ nhớ với immutable entity thường bị bỏ qua khi đồng bộ.

Trong ứng dụng cần tính bất biến bắt buộc ở **mức database**, có thể phải bổ sung quyền truy cập phù hợp, constraint, trigger hoặc kiến trúc chỉ cho insert dữ liệu mới theo yêu cầu nghiệp vụ. Annotation ORM một mình không phải cơ chế bảo mật hay bảo vệ tính toàn vẹn tuyệt đối.

### 6.2. `@Column(updatable = false)` và `@Immutable` khác nhau

| Thiết lập | Phạm vi | Giới hạn cần hiểu |
|---|---|---|
| `@Column(updatable = false)` | Từng cột trong SQL `UPDATE` do JPA sinh ra | Không chặn thay đổi giá trị trong RAM; cột vẫn có thể được đưa vào `INSERT` |
| `@Immutable` của Hibernate | Entity/collection/attribute theo phạm vi annotation Hibernate | Không portable; không thay đổi luật Java về `final` |
| Không public setter | API của lớp Java | Provider vẫn có quyền nạp hoặc thay đổi persistent field |
| Ràng buộc CSDL | CSDL thực thi theo định nghĩa schema/permissions | Không quyết định entity có hợp lệ theo JPA hay không |

## 7. Lựa chọn thiết kế bất biến phù hợp với từng lớp

Không phải đối tượng nào có dữ liệu từ cơ sở dữ liệu cũng cần trở thành entity. Phân loại đúng thường giải quyết nhu cầu immutable hiệu quả hơn việc ép một entity thành `final`.

### 7.1. Entity có identity: quản lý thay đổi qua nghiệp vụ

Ví dụ một tài khoản:

```java
@Entity
public class Account {
    @Id
    @GeneratedValue
    private Long id;

    private boolean active;

    protected Account() {}

    public void deactivate() {
        if (!active) {
            return;
        }
        this.active = false;
    }

    public boolean isActive() {
        return active;
    }
}
```

Mã ngoài không có `setActive(boolean)` để gán trạng thái tùy ý; hành vi `deactivate()` diễn đạt một chuyển trạng thái nghiệp vụ. Provider vẫn có thể quản lý và đồng bộ thay đổi này.

### 7.2. Value object không có identity riêng: ưu tiên record nếu phiên bản cho phép

Ví dụ số tiền:

```java
import java.math.BigDecimal;
import jakarta.persistence.Embeddable;

@Embeddable
public record Money(BigDecimal amount, String currencyCode) {
    public Money {
        if (amount == null || currencyCode == null || currencyCode.isBlank()) {
            throw new IllegalArgumentException("Invalid money value");
        }
    }
}
```

Trong Jakarta Persistence 3.2, `Money` có thể là một value object embeddable. Cần bổ sung xử lý chuẩn hóa tiền tệ/làm tròn theo miền nghiệp vụ thực tế; ví dụ chỉ minh họa cách lưu giá trị trong một record.

Entity có thể chứa:

```java
@Embedded
private Money unitPrice;

public void reprice(Money newPrice) {
    if (newPrice == null) {
        throw new IllegalArgumentException("Price required");
    }
    this.unitPrice = newPrice;
}
```

Tùy mapping và ngữ cảnh, `@AttributeOverride` có thể cần để đặt tên cột hoặc tránh trùng cột khi cùng entity có nhiều embedded object cùng loại.

### 7.3. DTO trả dữ liệu: record là lựa chọn độc lập với entity mapping

Record cũng phù hợp với **DTO/projection**, kể cả khi entity phải được biểu diễn bằng lớp mutable:

```java
package example.api;

public record BookView(Long id, String title) {}
```

```java
List<BookView> views = em.createQuery(
        "select new example.api.BookView(b.id, b.title) from Book b",
        BookView.class)
    .getResultList();
```

`BookView` không có `@Entity`, không được persistence context theo dõi, và không cần constructor không tham số. Nó chỉ là kiểu dữ liệu chứa kết quả truy vấn.

Đây là cách rất hữu ích khi muốn API trả một cấu trúc bất biến, tránh vô tình đưa entity managed và các quan hệ lazy trực tiếp ra ngoài ranh giới transaction.

### 7.4. Đưa collection ra ngoài bằng giao diện chỉ đọc

Một entity có quan hệ `@OneToMany` thường phải cho provider quản lý collection. Có thể hạn chế mã gọi sửa trực tiếp:

```java
@OneToMany(mappedBy = "order", cascade = CascadeType.ALL, orphanRemoval = true)
private List<OrderLine> lines = new ArrayList<>();

public List<OrderLine> getLines() {
    return Collections.unmodifiableList(lines);
}

public void addLine(OrderLine line) {
    // Kiểm tra quy tắc nghiệp vụ, đồng bộ cả hai phía của quan hệ.
    lines.add(line);
    line.attachTo(this);
}
```

Đoạn code chỉ minh họa API, giả định `OrderLine.attachTo(...)` được định nghĩa phù hợp. Collection persistent bên trong vẫn mutable để provider và các business method quản lý; danh sách trả về không cho caller chỉnh sửa trực tiếp. Nếu `lines` được tải lazy, việc truy cập nó vẫn tuân theo vòng đời persistence context.

## 8. Những mẫu code cần tránh khi muốn tối ưu immutability

### 8.1. Gắn `@Entity` lên record

```java
@Entity
public record Customer(@Id Long id, String name) {}
```

**Vấn đề:** `record` không hợp lệ làm entity trong Jakarta Persistence 3.2; việc Java hỗ trợ record không đồng nghĩa ORM coi nó là entity. Chuyển record thành `@Embeddable` nếu nó là value object, hoặc giữ entity dưới dạng non-final class và dùng record làm DTO.

### 8.2. Dùng Lombok `@Value` cho entity portable

```java
@Entity
@lombok.Value
public class Customer {
    @Id
    Long id;

    String name;
}
```

Lombok `@Value` hướng tới immutable value class, thông thường sinh class và field `final` cùng constructor nhận giá trị; điều này xung đột với các yêu cầu entity portable. Nếu dùng Lombok với JPA, cần hiểu code sau biên dịch, bảo đảm có constructor không tham số và không tạo `final` trên class/persistent field.

### 8.3. Đánh dấu toàn bộ getter `final`

```java
@Entity
public class Customer {
    @Id
    private Long id;

    public final Long getId() {
        return id;
    }
}
```

Các method `final` không thỏa yêu cầu entity portable. Với proxy-based lazy loading, method `final` còn có thể hạn chế khả năng provider override hành vi đọc dữ liệu.

### 8.4. Thay entity managed bằng object mới như thay record

```java
Book existing = em.find(Book.class, 7L);
Book replacement = new Book("New title");
// 'replacement' không tự thay thế 'existing' trong persistence context.
```

Tạo instance mới không có cùng ngữ nghĩa với sửa entity managed. Nếu `persist(replacement)`, ứng dụng thường yêu cầu tạo một entity mới; không phải cập nhật row của `existing`. Muốn thay dữ liệu của entity cũ, hãy gọi business method trên managed entity hoặc dùng `merge()` đúng ngữ nghĩa với một entity detached có identity phù hợp.

### 8.5. Hiểu nhầm `@Version` là “phiên bản class hỗ trợ immutable”

```java
@Version
private long version;
```

`@Version` trong JPA nói đến **phiên bản của một bản ghi entity để optimistic locking**, không phải phiên bản của Jakarta Persistence, và cũng không làm object immutable. Bài học đang phân biệt *phiên bản JPA* khi quy tắc mapping thay đổi; không nên trộn khái niệm ấy với thuộc tính `@Version`.

## 9. Bài toán minh họa: địa chỉ nhận hàng không được sửa từng phần

Giả sử hệ thống đặt hàng yêu cầu địa chỉ giao hàng phải là một tập dữ liệu nhất quán: đường, thành phố và mã quốc gia luôn đi cùng nhau. Cho phép từng setter có thể làm đối tượng ở trạng thái nửa cập nhật trong một khoảng thời gian.

Một thiết kế theo Jakarta Persistence 3.2:

```java
@Embeddable
public record ShippingAddress(
    String street,
    String city,
    String countryCode
) {
    public ShippingAddress {
        if (street == null || street.isBlank()
                || city == null || city.isBlank()
                || countryCode == null || countryCode.length() != 2) {
            throw new IllegalArgumentException("Invalid shipping address");
        }
    }
}
```

```java
@Entity
@Table(name = "orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    private ShippingAddress shippingAddress;

    protected PurchaseOrder() {}

    public PurchaseOrder(ShippingAddress shippingAddress) {
        changeShippingAddress(shippingAddress);
    }

    public void changeShippingAddress(ShippingAddress newAddress) {
        if (newAddress == null) {
            throw new IllegalArgumentException("Address required");
        }
        this.shippingAddress = newAddress;
    }

    public ShippingAddress getShippingAddress() {
        return shippingAddress;
    }
}
```

Khi xử lý nghiệp vụ:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
order.changeShippingAddress(
    new ShippingAddress("45 Le Loi", "Ho Chi Minh City", "VN")
);
```

Thiết kế này đạt ba mục tiêu:

1. **Entity còn tương thích với JPA:** `PurchaseOrder` là class non-final, có `protected` no-arg constructor và field persistent không `final`.
2. **Giá trị địa chỉ là immutable:** `ShippingAddress` chỉ tồn tại dưới dạng record đầy đủ, không thể sửa từng thành phần.
3. **Provider vẫn hoạt động bình thường:** nó theo dõi entity managed và đồng bộ việc thay giá trị embeddable.

Nếu chạy trên hệ thống chỉ hỗ trợ Jakarta Persistence 3.1, có thể dùng `@Embeddable class` thông thường với constructor không tham số, field không final và không public setter. Cách đó cung cấp phần lớn lợi ích **đóng gói** nhưng không đạt tính immutable đầy đủ của record ở cấp ngôn ngữ.

## 10. Khả năng di chuyển giữa provider và nâng cấp phiên bản

Khi một ứng dụng muốn chuyển từ JPA 2.2/`javax.persistence` sang Jakarta Persistence 3.x/`jakarta.persistence` hoặc nâng provider, cần xem xét:

| Điều cần xác định | Hướng kiểm tra |
|---|---|
| Dependency API thuộc phiên bản nào? | Kiểm tra `javax.persistence`/`jakarta.persistence` và phiên bản artifact |
| Provider hỗ trợ đặc tả nào? | Xem release notes và ma trận tương thích chính thức |
| Java runtime hỗ trợ record không? | Record là tính năng Java hiện đại; Jakarta Persistence 3.2 yêu cầu Java SE 17 trở lên |
| Class entity có tuân thủ đặc tả không? | No-arg, non-final, loại class phù hợp, identifier và access strategy |
| Có dùng record embeddable/composite key không? | Chỉ xem là portable khi đặc tả và provider cùng hỗ trợ |
| Có annotation riêng của provider không? | Phân biệt `org.hibernate.annotations.Immutable` với annotation chuẩn |
| Lazy loading và proxy có bị ảnh hưởng không? | Xem cấu hình enhancement, final modifiers và các truy vấn thực tế |
| Dữ liệu có được đọc và cập nhật đúng không? | Kiểm chứng mapping, vòng đời entity, transaction và SQL của các trường hợp nghiệp vụ |

Đừng chỉ kiểm tra rằng ứng dụng khởi động thành công. Một mapping có thể load được metadata nhưng gặp vấn đề ở lazy association, merge, refresh, detach, dirty checking hoặc cơ chế tạo khóa trong những luồng chạy khác.

**Với Java record dùng làm embeddable:** khi nâng lên Jakarta Persistence 3.2, có thể cân nhắc chuyển các value object từ class thường sang record. Đó là thay đổi biểu diễn và cách khởi tạo giá trị; vẫn phải kiểm tra mapping tên cột, nullability, validation, equality và dữ liệu cũ.

## 11. Một số câu hỏi thường gặp

**1. Entity không có setter có hợp lệ không?**

Có thể. Với field access, provider có thể thao tác trực tiếp với persistent field, nên entity có thể chỉ công khai getter và business method. Không có public setter không đồng nghĩa mọi trạng thái bất biến.

**2. Có thể khai báo entity là `final` nếu dùng Hibernate không?**

Một số phiên bản/cấu hình Hibernate có thể xử lý, nhưng đó không phải thiết kế portable theo JPA. Final entity có thể hạn chế cơ chế proxy lazy loading hoặc phụ thuộc enhancement. Nên ưu tiên entity non-final nếu muốn tuân chuẩn.

**3. Nếu không muốn khóa chính thay đổi, có nên viết `private final Long id`?**

Không. Persistent field `final` xung đột ràng buộc chuẩn. Hãy để `id` non-final, không cung cấp public setter và không tự thay id sau khi entity có identity.

**4. Jakarta Persistence 3.2 cho phép `record` làm entity chưa?**

Chưa. Bản 3.2 cho phép record dùng làm embeddable và composite primary key class, nhưng `@Entity` vẫn yêu cầu một class non-final phù hợp.

**5. Có thể dùng record cho kết quả JPQL ở phiên bản JPA cũ không?**

Record là một Java class có constructor theo thành phần, nên có thể dùng làm DTO qua constructor projection nếu Java/runtime và provider hỗ trợ việc tạo kết quả đó. Đây **không phải** mapping `@Entity` hoặc `@Embeddable`, nên cần phân biệt với tính năng record embeddable chuẩn hóa ở 3.2.

**6. Entity được đánh dấu `@Immutable` có bất biến ở mọi tầng không?**

Không. `@Immutable` của Hibernate ảnh hưởng đến cách ORM đồng bộ state; mã Java và các client khác vẫn có thể thay dữ liệu theo các đường khác. Nếu cần đảm bảo ở mức CSDL phải có cơ chế riêng.

**7. Có nên dùng `record` cho `@EmbeddedId`?**

Có thể là lựa chọn phù hợp trong Jakarta Persistence 3.2 vì khóa tổng hợp thường có semantics theo giá trị. Vẫn cần bảo đảm mapping, equality phù hợp với CSDL và không thay identity của entity sau khi lưu.

**8. Lớp `static nested` là entity được từ phiên bản nào?**

Jakarta Persistence 3.2 cho phép entity là lớp top-level hoặc static nested. Trong các phiên bản cũ hơn, thiết kế portable là top-level class.

**9. `@Version` có liên quan tới Java immutable object không?**

Không trực tiếp. `@Version` quản lý optimistic locking đối với cập nhật đồng thời; nó không cấm việc thay đổi thuộc tính entity và không quyết định class có thể `final` hay không.

## 12. Ghi nhớ khi thiết kế

Khi cần một mô hình dữ liệu vừa rõ ràng vừa phù hợp JPA, hãy phân chia trách nhiệm:

- **Entity:** có identity, non-final, public/protected no-arg constructor, persistent fields non-final, không cần public setter cho mọi thuộc tính. Dùng business method để bảo vệ invariant.
- **Embeddable/value object:** mô tả giá trị không có identity riêng; với Jakarta Persistence 3.2 có thể dùng Java record để đạt tính immutable mạnh hơn.
- **Composite key:** ưu tiên tính ổn định và equality theo giá trị; record key là một khả năng chuẩn từ Jakarta Persistence 3.2.
- **DTO:** có thể dùng record để truyền dữ liệu bất biến ra API, độc lập với persistence lifecycle của entity.
- **Provider-specific read-only:** chỉ dùng khi hiểu chính xác tác động, dependency và giới hạn của nó.

Đối với các hệ thống hỗ trợ nhiều phiên bản JPA, **đừng đồng nhất tính bất biến của miền nghiệp vụ với từ khóa `final` trong entity**. Entity nên được **đóng gói thay đổi**, còn những thành phần có semantics theo giá trị mới là nơi thích hợp để áp dụng thiết kế immutable.

## Tài liệu tham khảo

- [Jakarta Persistence 3.2 Specification — 2.1 The Entity Class](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html#the-entity-class)
- [Jakarta Persistence 3.2 Specification — 2.4.1 Composite primary keys](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html#composite-primary-keys)
- [Jakarta Persistence 3.2 Specification — 2.7 Embeddable Classes](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html#embeddable-classes)
- [Jakarta Persistence 3.2 — Changes and additions](https://jakarta.ee/specifications/persistence/3.2/)
- [Jakarta Persistence 3.1 Specification — entity class requirements](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.html)
- [Jakarta Persistence 4.0 — under development](https://jakarta.ee/specifications/persistence/4.0/)
- [Hibernate ORM User Guide — Entity classes and attribute access](https://docs.hibernate.org/orm/8.0/userguide/html_single/)
- [Hibernate `@Immutable` Javadoc](https://docs.hibernate.org/orm/7.0/javadocs/org/hibernate/annotations/Immutable.html)
