# Thực thể, đối tượng giá trị và tính bất biến của mô hình nghiệp vụ

Khi xây dựng ứng dụng với **Spring Data JDBC**, thiết kế lớp Java không chỉ là ánh xạ cột trong bảng dữ liệu. Mô hình cần diễn tả được **đối tượng nào có danh tính riêng**, **giá trị nào chỉ quan trọng ở nội dung**, **quy tắc nghiệp vụ nào phải luôn đúng**, và **ai được phép thay đổi trạng thái**. Đây là nền tảng để xác định ranh giới *aggregate*, thiết kế repository và tránh việc dữ liệu trong database rơi vào trạng thái không hợp lệ.

Bài học sử dụng ví dụ đặt hàng để giải thích ba khái niệm liên quan chặt chẽ: **entity (thực thể)**, **value object (đối tượng giá trị)** và **immutability (tính bất biến)**. Các ví dụ đặt trong bối cảnh Spring Data Relational JDBC, nơi aggregate được lưu bằng SQL và không có persistence context/change tracking kiểu JPA.

## 1. Nhìn dữ liệu bằng ngôn ngữ nghiệp vụ

Giả sử một cửa hàng có đơn hàng gồm mã đơn, khách hàng, các dòng hàng, tổng tiền và trạng thái. Một cách tổ chức thuần dữ liệu là tạo lớp chứa getter/setter tương ứng từng cột. Cách đó dễ dẫn đến tình huống bất kỳ thành phần nào trong ứng dụng cũng có thể sửa trạng thái hoặc tổng tiền tùy ý.

Cách tiếp cận theo mô hình miền (*domain model*) đặt những câu hỏi khác:

- Hai đơn hàng có cùng tổng tiền và trạng thái có phải cùng một đơn hàng?
- Hai số tiền `100_000 VND` được tạo từ hai lời gọi khác nhau có thể xem là cùng một giá trị?
- Đơn hàng đã xác nhận có được quay về trạng thái mới tạo không?
- Nếu sửa một dòng hàng, tổng tiền có phải thay đổi theo hay không?
- Những thay đổi nào cần được lưu cùng một transaction để duy trì tính nhất quán?

Các câu trả lời giúp phân biệt **identity**, **value equality**, **invariant** và **aggregate boundary**. Những khái niệm này liên quan đến nhau nhưng không đồng nghĩa với bảng, khóa chính hay annotation.

### Thuật ngữ cốt lõi

| Thuật ngữ | Ý nghĩa trong mô hình nghiệp vụ | Ví dụ |
| --- | --- | --- |
| Entity | Đối tượng có danh tính liên tục qua thời gian, ngay cả khi thuộc tính thay đổi | Đơn hàng số `ORD-2026-0042` |
| Value object | Đối tượng được xác định bằng giá trị thuộc tính, không cần danh tính riêng | Số tiền gồm số lượng đơn vị tiền tệ và mã tiền |
| Invariant | Quy tắc bắt buộc đúng ở các trạng thái hợp lệ của mô hình | Không xác nhận đơn hàng không có dòng hàng |
| Aggregate | Nhóm entity/value object có một ranh giới nhất quán khi thay đổi | Đơn hàng cùng những dòng hàng thuộc nó |
| Aggregate root | Entity đóng vai trò điểm truy cập và kiểm soát thay đổi aggregate | `PurchaseOrder` |
| Immutability | Trạng thái đã tạo của một đối tượng không bị thay đổi trực tiếp | `Money.add(...)` trả đối tượng `Money` mới |

## 2. Entity: danh tính quan trọng hơn thuộc tính

**Entity** là đối tượng cần phân biệt “chính đối tượng đó” theo thời gian. Một đơn hàng vẫn là đơn hàng ban đầu sau khi chuyển từ `DRAFT` sang `CONFIRMED`. Hai đơn hàng có cùng khách hàng, cùng số tiền và cùng trạng thái vẫn có thể là hai entity khác nhau.

~~~text
Đơn hàng A: ID = 101, trạng thái DRAFT, tổng = 250_000 VND
     |
     | xác nhận
     v
Đơn hàng A: ID = 101, trạng thái CONFIRMED, tổng = 250_000 VND

Đơn hàng B: ID = 102, trạng thái CONFIRMED, tổng = 250_000 VND
~~~

A trước và sau khi xác nhận là cùng entity. A và B là hai entity khác nhau dù một số thuộc tính bằng nhau.

### 2.1. Danh tính nghiệp vụ và khóa kỹ thuật

Một entity có thể có:

- **Khóa kỹ thuật**: ví dụ `id BIGINT` do database sinh để định danh hàng dữ liệu.
- **Danh tính nghiệp vụ**: ví dụ `orderNumber` mà khách hàng và nhân viên sử dụng để tra cứu.

Hai giá trị này có thể trùng vai trò trong một mô hình đơn giản, nhưng không nhất thiết giống nhau. Một `id` có thể chỉ xuất hiện sau khi lưu xuống database, trong khi `orderNumber` đã được cấp trước đó.

Không nên mặc định rằng mọi đối tượng có `id` đều là entity theo nghĩa nghiệp vụ. Ngược lại, một entity miền có thể chưa có khóa database khi đang ở trạng thái mới tạo.

### 2.2. Equality của entity

Trong phân tích miền, so sánh entity là so sánh **danh tính ổn định**, không phải mọi field. Tuy nhiên, việc cài đặt Java `equals()`/`hashCode()` cho entity dùng ID do database sinh cần thận trọng:

- Hai entity mới tạo đều có `id == null` không vì vậy mà trở thành cùng entity.
- Một đối tượng được thêm vào `HashSet` rồi mới được cấp ID có thể làm thay đổi hash nếu `hashCode()` phụ thuộc ID.
- So sánh chỉ dựa trên `id` cũng cần xét phạm vi loại entity và tính duy nhất của ID.

Không có một công thức `equals()` áp dụng cho mọi miền. Có thể dùng danh tính nghiệp vụ bất biến nếu nó thực sự duy nhất và được cấp từ đầu; hoặc giữ identity theo tham chiếu Java cho entity và dùng phương thức so sánh ID rõ ràng tại điểm cần thiết. Quyết định phải phù hợp vòng đời entity.

### 2.3. Entity không đồng nghĩa với một bảng

Một entity có thể được lưu trong một bảng, nhưng **entity thuộc về mô hình nghiệp vụ**, còn bảng là cấu trúc lưu trữ. Với Spring Data JDBC:

- Aggregate root thường được ánh xạ vào bảng chính.
- Entity con thuộc aggregate có thể được lưu ở bảng phụ với khóa ngoại hướng về root.
- Một số thuộc tính dạng value object có thể được nhúng thành nhiều cột trong bảng của entity.

Việc chia bảng nhằm tối ưu dữ liệu không tự quyết định aggregate boundary; ranh giới đó xuất phát từ quy tắc nhất quán của nghiệp vụ.

## 3. Value object: nội dung quan trọng hơn danh tính

**Value object** đại diện cho một khái niệm được nhận diện bằng **giá trị**, chẳng hạn `Money`, `EmailAddress`, `DateRange` hoặc `ShippingAddress`. Hai value object cùng kiểu, có nội dung bằng nhau và tuân theo cùng quy tắc nghiệp vụ có thể được coi là tương đương, không cần ID riêng.

~~~text
Money(100_000, "VND") == Money(100_000, "VND")  // bằng nhau theo giá trị
Money(100_000, "VND") != Money(100_000, "USD")  // khác loại tiền
~~~

Value object tốt thường có những đặc điểm:

1. **Không có identity độc lập** cần theo dõi qua thời gian.
2. **Bất biến sau khi tạo**: thao tác “thay đổi” trả một giá trị mới.
3. **Tự bảo vệ tính hợp lệ**: không cho khởi tạo trạng thái trái quy tắc.
4. **Có hành vi nghiệp vụ**: ví dụ cộng tiền, kiểm tra cùng đơn vị tiền, xét khoảng ngày giao nhau.
5. **So sánh theo giá trị** thay vì so sánh địa chỉ đối tượng trong bộ nhớ.

### 3.1. Ví dụ `Money` bằng Java record

~~~java
import java.util.Locale;
import java.util.Objects;

public record Money(long minorUnits, String currency) {

    public Money {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("Số tiền không được âm");
        }

        currency = Objects.requireNonNull(currency, "currency")
                .trim()
                .toUpperCase(Locale.ROOT);

        if (!currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Mã tiền phải gồm ba chữ cái");
        }
    }

    public Money add(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Không thể cộng hai loại tiền");
        }
        return new Money(Math.addExact(minorUnits, other.minorUnits()), currency);
    }
}
~~~

Ví dụ giả định số tiền **không âm** và được biểu diễn bằng `minorUnits`: đơn vị nhỏ nhất theo loại tiền, ví dụ cent đối với USD hoặc đồng đối với VND. Không nên giả định mọi tiền tệ đều có hai chữ số thập phân. Biểu thức kiểm tra ba chữ cái chỉ xác nhận hình dạng mã, chưa xác nhận mã đó thuộc danh sách tiền tệ hợp lệ; nếu miền cần, phải bổ sung chính sách phù hợp.

Sử dụng:

~~~java
Money a = new Money(150_000, "vnd");
Money b = new Money(50_000, "VND");
Money total = a.add(b);

System.out.println(total);                // Money[minorUnits=200000, currency=VND]
System.out.println(a);                    // Money[minorUnits=150000, currency=VND]
System.out.println(
        a.equals(new Money(150_000, "VND"))
);                                       // true
~~~

`a` không đổi sau phép cộng. Java record tự cung cấp các thành phần truy cập, `equals()`, `hashCode()` và `toString()` dựa trên các component. Logic chuẩn hóa ở compact constructor giúp hai đầu vào tương đương có biểu diễn thống nhất.

### 3.2. Khi nào một khái niệm nên là value object?

Một địa chỉ giao hàng được lưu theo từng đơn và thay đổi bằng cách thay toàn bộ địa chỉ thường phù hợp value object. Nhưng “địa chỉ đã đăng ký” có ID, lịch sử kiểm chứng và vòng đời riêng có thể là entity trong một miền khác.

Tiêu chí quan trọng là **nghiệp vụ có cần theo dõi danh tính và lịch sử riêng của nó hay không**, chứ không chỉ vì đối tượng có nhiều trường dữ liệu.

Ví dụ:

| Khái niệm | Thường là | Lý do |
| --- | --- | --- |
| Đơn hàng | Entity | Cần theo dõi cùng một đơn qua nhiều trạng thái. |
| Dòng hàng trong đơn | Entity con hoặc value object, tùy quy tắc | Nếu cần sửa/xóa từng dòng theo ID ổn định, entity con hữu ích; nếu chỉ thay toàn bộ danh sách, có thể thiên về value object. |
| Số tiền | Value object | Quan trọng là lượng tiền và loại tiền. |
| Mã bưu chính | Value object | Giá trị mã và quy tắc hợp lệ là cốt lõi. |
| Khách hàng | Entity | Có vòng đời, danh tính và lịch sử riêng. |
| Địa chỉ giao hàng chụp tại thời điểm đặt đơn | Value object | Lưu lại giá trị của thời điểm giao dịch, không cần tham chiếu một đối tượng địa chỉ đang thay đổi. |

## 4. Tính bất biến (immutability) là gì?

Một đối tượng **immutable** không cho phép trạng thái quan sát được của chính nó thay đổi sau khi khởi tạo. Muốn thể hiện một trạng thái mới, ta tạo **đối tượng mới**.

~~~java
Money current = new Money(100_000, "VND");
Money updated = current.add(new Money(20_000, "VND"));

// current vẫn là 100_000 VND; updated là 120_000 VND.
~~~

Đối với entity, cần phân biệt hai ý:

- **Entity vẫn thay đổi theo nghiệp vụ**: một đơn hàng có thể đi từ `DRAFT` sang `CONFIRMED`.
- **Đối tượng Java biểu diễn một phiên bản trạng thái có thể immutable**: phương thức `confirm()` trả về phiên bản mới của cùng entity, mang cùng ID nhưng trạng thái mới.

~~~text
PurchaseOrder(id=42, status=DRAFT)     --confirm()-->
PurchaseOrder(id=42, status=CONFIRMED)

Hai object Java khác nhau; trong miền chúng biểu diễn cùng entity ID 42
ở hai trạng thái khác nhau.
~~~

### 4.1. Các mức độ bảo vệ trạng thái

**Bất biến toàn bộ đối tượng (immutable object):**

~~~java
public final class ShippingAddress {
    private final String city;
    private final String street;

    public ShippingAddress(String city, String street) {
        this.city = Objects.requireNonNull(city);
        this.street = Objects.requireNonNull(street);
    }

    public String city() {
        return city;
    }

    public String street() {
        return street;
    }
}
~~~

Ví dụ sử dụng `Objects` cần thêm `import java.util.Objects;`. Vì `String` bất biến, không có setter và lớp không cho kế thừa, giá trị đã tạo không thể bị sửa thông qua API thông thường. Có thể dùng `record` để giảm boilerplate.

**Đóng gói thay đổi có kiểm soát (encapsulated mutability):**

~~~java
public class Basket {
    private final List<String> productCodes = new ArrayList<>();

    public void addProduct(String code) {
        // Có thể kiểm tra quy tắc trước khi sửa.
        productCodes.add(Objects.requireNonNull(code));
    }

    public List<String> productCodes() {
        return List.copyOf(productCodes);
    }
}
~~~

`Basket` không hoàn toàn immutable, nhưng caller không thể sửa trực tiếp collection nội bộ qua getter. Thay đổi phải đi qua phương thức nghiệp vụ.

Không có yêu cầu mọi entity đều phải dùng `final`. Điều quan trọng là **bảo vệ invariant và hạn chế sửa trạng thái không kiểm soát**. Mutable entity với hành vi nghiệp vụ rõ ràng có thể là thiết kế hợp lệ.

### 4.2. `final` không bảo đảm bất biến sâu

~~~java
public record CustomerSnapshot(List<String> tags) {
}

List<String> source = new ArrayList<>(List.of("VIP"));
CustomerSnapshot snapshot = new CustomerSnapshot(source);
source.add("BLOCKED"); // snapshot.tags() cũng thấy phần tử mới
~~~

Component của record là `final` ở mức tham chiếu, nhưng danh sách được tham chiếu vẫn mutable. Cách sửa:

~~~java
public record CustomerSnapshot(List<String> tags) {
    public CustomerSnapshot {
        tags = List.copyOf(Objects.requireNonNull(tags));
    }
}
~~~

`List.copyOf` ngăn sửa cấu trúc danh sách và sao chép phần tử sang danh sách không chỉnh sửa được, nhưng là **shallow copy**: nếu bản thân phần tử mutable, các phần tử vẫn có thể đổi trạng thái. Tương tự với array, `Date` hoặc đối tượng có trường mutable; cần defensive copy hoặc thiết kế giá trị thành phần immutable.

## 5. Aggregate và invariant: ai có quyền thay đổi điều gì?

Một aggregate gom những đối tượng phải giữ **nhất quán trong cùng ranh giới nghiệp vụ**. Mọi thay đổi từ bên ngoài đi qua **aggregate root**. Root quyết định thao tác nào hợp lệ, khi nào tạo entity con và khi nào từ chối thay đổi.

~~~text
PurchaseOrder  (AGGREGATE ROOT)
    |
    +--- orderId / customerId / status
    |
    +--- total: Money                  (VALUE OBJECT)
    |
    +--- lines: OrderLine[]            (CHILD ENTITY / VALUE)
            |
            +--- productCode
            +--- quantity
            +--- unitPrice: Money      (VALUE OBJECT)

Customer                             (AGGREGATE ROOT KHÁC)
    |
    +--- customerId
~~~

Trong ví dụ này, `PurchaseOrder` giữ `customerId` để tham chiếu một aggregate khách hàng độc lập. Root của đơn hàng không “sở hữu” mọi thay đổi của khách hàng.

Một số invariant có thể là:

- Đơn hàng đã xác nhận không được thêm hoặc xóa dòng hàng.
- Mỗi dòng hàng phải có số lượng dương.
- Mọi dòng hàng cùng loại tiền nếu tổng tiền được tính bằng một đơn vị tiền.
- Tổng tiền phải bằng tổng `quantity × unitPrice` của các dòng hàng đang có hiệu lực.
- Đơn hàng không có dòng hàng không được xác nhận.

Thay vì cho gọi `setTotal(...)` và `setStatus(...)` độc lập, hãy cung cấp hành vi miền như `addLine(...)`, `removeLine(...)`, `confirm()`. Mỗi thao tác kiểm tra điều kiện trước/sau và tạo một trạng thái hợp lệ.

### Ranh giới nhất quán và transaction

Aggregate được thiết kế để các invariant nội bộ có thể được duy trì trong một transaction khi lưu. Những quy tắc bắc cầu qua nhiều aggregate có thể cần cơ chế phối hợp riêng, chẳng hạn transaction ở application service khi database cho phép, sự kiện miền, outbox hoặc eventual consistency tùy nhu cầu. Không nên vì hai đối tượng có quan hệ mà gộp chúng thành một aggregate rất lớn.

Aggregate càng lớn, việc tải và lưu toàn bộ graph thường càng tốn kém, mức tranh chấp cập nhật càng cao. Với Spring Data JDBC, đây là cân nhắc đặc biệt quan trọng vì thao tác `save` trên root có thể dẫn tới nhiều câu SQL với entity con.

## 6. Ví dụ ánh xạ value object vào Spring Data JDBC

Value object `Money` đã có hai thành phần `minorUnits` và `currency`. Nếu nó là thuộc tính của đơn hàng, một lựa chọn là lưu thẳng vào các cột của bảng `purchase_order`:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    total_minor_units BIGINT NOT NULL,
    total_currency VARCHAR(3) NOT NULL,
    status VARCHAR(24) NOT NULL
);
~~~

Cú pháp trên dùng kiểu identity tương thích với nhiều hệ quản trị hiện đại nhưng chi tiết DDL có thể cần điều chỉnh cho database cụ thể. Trong Spring Data JDBC, `@Embedded` có thể trải các thuộc tính của object ra nhiều cột:

~~~java
import org.springframework.data.relational.core.mapping.Embedded;

@Embedded(onEmpty = Embedded.OnEmpty.USE_NULL, prefix = "total_")
private final Money total;
~~~

Theo chiến lược đặt tên cột kiểu snake_case thông dụng, `Money.minorUnits` ánh xạ tới `total_minor_units` và `Money.currency` tới `total_currency`. `prefix` giúp phân biệt khi một entity chứa nhiều value object cùng kiểu, ví dụ `subTotal` và `shippingFee`.

`onEmpty = USE_NULL` nghĩa là khi **tất cả cột của object nhúng đều null**, framework có thể xem toàn bộ object là null. Nếu miền yêu cầu `total` luôn tồn tại, ngoài kiểm tra trong constructor cần dùng ràng buộc `NOT NULL` ở database như ví dụ.

`@Embedded` phù hợp cho đối tượng thành phần lưu vào cùng hàng. Nó không phải cách tạo quan hệ một-nhiều tới bảng entity con; trường hợp đó cần cơ chế ánh xạ collection tương ứng.

## 7. Entity root immutable với `@Id`, `@Version` và hành vi nghiệp vụ

Đoạn mã dưới đây minh họa một aggregate root đơn giản, chưa có collection dòng hàng để tập trung vào entity, value object và trạng thái bất biến:

~~~java
import java.util.Objects;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public final class PurchaseOrder {

    public enum Status {
        DRAFT, CONFIRMED
    }

    @Id
    private final Long id;

    @Version
    private final Long version;

    private final Long customerId;

    @Embedded(onEmpty = Embedded.OnEmpty.USE_NULL, prefix = "total_")
    private final Money total;

    private final Status status;

    @PersistenceCreator
    public PurchaseOrder(
            Long id,
            Long version,
            Long customerId,
            Money total,
            Status status
    ) {
        if (customerId == null || customerId <= 0) {
            throw new IllegalArgumentException("Khách hàng không hợp lệ");
        }

        this.id = id;
        this.version = version;
        this.customerId = customerId;
        this.total = Objects.requireNonNull(total, "total");
        this.status = Objects.requireNonNull(status, "status");
    }

    public static PurchaseOrder draft(Long customerId, Money total) {
        return new PurchaseOrder(null, null, customerId, total, Status.DRAFT);
    }

    public PurchaseOrder confirm() {
        if (status != Status.DRAFT) {
            throw new IllegalStateException("Chỉ có thể xác nhận đơn đang nháp");
        }
        return new PurchaseOrder(id, version, customerId, total, Status.CONFIRMED);
    }

    public PurchaseOrder withId(Long generatedId) {
        return new PurchaseOrder(generatedId, version, customerId, total, status);
    }

    public PurchaseOrder withVersion(Long persistedVersion) {
        return new PurchaseOrder(id, persistedVersion, customerId, total, status);
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public Long getCustomerId() {
        return customerId;
    }

    public Money getTotal() {
        return total;
    }

    public Status getStatus() {
        return status;
    }
}
~~~

Đây là ví dụ **có chủ đích thu gọn**: đơn hàng chỉ có tổng tiền được cung cấp lúc tạo, chưa tự tính từ các dòng hàng. Trong mô hình có `OrderLine`, tổng tiền phải được tính/kiểm tra bằng logic aggregate, thay vì tin một giá trị tổng do caller gửi lên.

### Giải thích các quyết định

| Chi tiết | Ý nghĩa |
| --- | --- |
| `@Table("purchase_order")` | Đặt tên bảng cho aggregate root trong Spring Data Relational. |
| `@Id` | Đánh dấu khóa định danh dùng cho lưu trữ. `null` thể hiện đối tượng chưa có ID được sinh. |
| `@Version` | Đánh dấu version phục vụ optimistic locking và xác định tình trạng mới của aggregate. |
| `@Embedded` | Ánh xạ `Money` thành các cột cùng hàng với entity root. |
| `@PersistenceCreator` | Chỉ rõ constructor dùng để materialize object từ dữ liệu đọc được. |
| Các trường `final` | Không có cách thay trường trực tiếp sau khi khởi tạo. |
| `draft(...)` | Factory tạo trạng thái hợp lệ ban đầu. |
| `confirm()` | Phương thức nghiệp vụ kiểm tra chuyển trạng thái trước khi tạo object mới. |
| `withId(...)` / `withVersion(...)` | Tạo bản sao với thuộc tính lưu trữ đã được điền/cập nhật; hỗ trợ cơ chế materialization và lưu đối tượng immutable. |

Spring Data có thể chọn constructor phù hợp theo quy tắc của framework; dùng `@PersistenceCreator` giúp làm rõ ý định khi kiểu có nhiều khả năng khởi tạo. Để constructor binding hoạt động ổn định, tên tham số cần được framework xác định, ví dụ thông qua tùy chọn biên dịch Java `-parameters` hoặc metadata phù hợp.

**Một vấn đề thực tế:** ID và version có thể được cập nhật sau thao tác lưu. Với object immutable, repository có thể **trả về một object mới** có ID/version mới. Vì vậy luôn dùng giá trị do `save(...)` trả về khi còn cần tiếp tục thao tác:

~~~java
PurchaseOrder draft = PurchaseOrder.draft(
        7L, new Money(125_000, "VND")
);

PurchaseOrder saved = repository.save(draft);

// saved là trạng thái đã được lưu; sử dụng saved.getId() thay cho
// giả định draft sẽ bị mutate để nhận ID mới.
~~~

Giá trị version cụ thể được framework gán theo quy tắc của Spring Data JDBC; không tự dự đoán con số mà sử dụng bản đã trả về.

## 8. Repository, transaction và optimistic locking

Một repository của aggregate root:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Application service có thể điều phối việc đọc, gọi hành vi miền rồi lưu:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {
    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder confirm(Long orderId) {
        PurchaseOrder current = repository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Không tìm thấy đơn hàng: " + orderId
                ));

        PurchaseOrder confirmed = current.confirm();
        return repository.save(confirmed);
    }
}
~~~

Ở đây, service quản lý transaction và lựa chọn thao tác; chính `PurchaseOrder.confirm()` quản lý quy tắc chuyển trạng thái. Một controller không cần gọi `setStatus(...)`, vì phương thức đó không tồn tại.

### Hai request cùng sửa một entity thì sao?

Immutability chỉ ngăn sửa trực tiếp trạng thái của **một object Java**. Nó không tự giải quyết việc hai tiến trình đọc cùng một hàng database rồi ghi đè nhau.

~~~text
Database: Order #42, version = 3, status = DRAFT

Request A đọc version 3         Request B đọc version 3
        |                               |
        v                               v
 A tạo bản CONFIRMED             B tạo bản CONFIRMED
        |                               |
        v                               v
 A save với version cũ 3         B save với version cũ 3
        |                               |
        v                               v
 A thành công, tăng version      B không còn khớp version
                                        |
                                        v
                              Optimistic locking failure
~~~

`@Version` giúp Spring Data JDBC phát hiện cập nhật dựa trên version đã cũ và báo lỗi optimistic locking thay vì âm thầm ghi đè. Tuy nhiên:

- Ứng dụng phải quyết định trả lỗi xung đột hay thử lại có kiểm soát.
- Retry phải đọc lại trạng thái mới và kiểm tra lại invariant; không nên lặp lại bản cập nhật cũ vô điều kiện.
- Với side effect ngoài database (gửi email, gọi thanh toán), cần cơ chế điều phối phù hợp để tránh lặp tác vụ khi retry.
- Cập nhật bằng SQL thủ công hoặc công cụ bên ngoài có thể bỏ qua cơ chế version của repository nếu không tự duy trì điều kiện/version tương ứng.

Transaction bảo đảm các thao tác trong ranh giới của nó có thể commit/rollback theo khả năng database; optimistic locking bổ sung khả năng phát hiện xung đột. Hai cơ chế phục vụ mục đích khác nhau và có thể dùng cùng nhau.

## 9. Entity con trong aggregate: danh tính cục bộ và vòng đời

Một aggregate đơn hàng thực tế thường chứa các dòng hàng:

~~~text
PurchaseOrder (root)
  ├── OrderLine(lineId=1, productCode="BOOK-A", quantity=2)
  └── OrderLine(lineId=2, productCode="PEN-B",  quantity=4)
~~~

`OrderLine` có thể là **entity con** nếu nghiệp vụ cần phân biệt từng dòng theo ID riêng, chẳng hạn khi điều chỉnh số lượng của một dòng cụ thể. Tuy vậy, nó không nhất thiết có repository riêng. Người dùng sửa dòng hàng **qua phương thức của `PurchaseOrder`**, vì root phải kiểm soát tổng tiền và trạng thái của đơn.

~~~java
// Phác họa hành vi trong aggregate (chưa phải lớp ánh xạ hoàn chỉnh).
public PurchaseOrder changeLineQuantity(long lineId, int newQuantity) {
    requireDraft();
    if (newQuantity <= 0) {
        throw new IllegalArgumentException("Số lượng phải dương");
    }

    List<OrderLine> changedLines = replaceQuantity(lines, lineId, newQuantity);
    Money updatedTotal = calculateTotal(changedLines);

    return copyWith(changedLines, updatedTotal);
}
~~~

Các helper `requireDraft`, `replaceQuantity`, `calculateTotal`, `copyWith` trong đoạn trên đại diện cho logic miền cần hiện thực khi thiết kế aggregate đầy đủ. Mục đích là thể hiện quy trình: **kiểm tra → tạo collection mới → tính lại giá trị phụ thuộc → tạo root mới**, không phải cho phép caller sửa collection rồi đặt tổng tiền tùy ý.

### Cách Spring Data JDBC nhìn quan hệ trong aggregate

Spring Data JDBC hỗ trợ ánh xạ quan hệ thuộc aggregate qua các cơ chế như `@MappedCollection`, chẳng hạn:

~~~java
@MappedCollection(idColumn = "purchase_order_id", keyColumn = "line_position")
private final List<OrderLine> lines;
~~~

Với một collection được ánh xạ như vậy, `idColumn` mô tả cột khóa ngoại về root, còn `keyColumn` có thể lưu chỉ số của phần tử khi mapping một `List`. Phần ánh xạ còn cần một lớp `OrderLine` tương thích và schema bảng con phù hợp; đây chỉ là phần khai báo minh họa.

Nên hiểu sự khác nhau:

| Quan hệ nghiệp vụ | Cách nghĩ trong thiết kế | Gợi ý ánh xạ |
| --- | --- | --- |
| Đơn hàng có nhiều dòng hàng thuộc vòng đời của đơn | Cùng aggregate, root kiểm soát thêm/xóa/sửa | Collection entity con như `@MappedCollection` |
| Đơn hàng có tổng tiền | Value object thuộc trạng thái root | `@Embedded` vào các cột của root |
| Đơn hàng tham chiếu khách hàng tồn tại độc lập | Hai aggregate khác nhau | Giữ `customerId` hoặc một dạng tham chiếu theo ID |

Trong Spring Data JDBC, đối tượng được tham chiếu trực tiếp trong cấu trúc aggregate thường được framework hiểu là thuộc cùng aggregate. Nếu trỏ thẳng từ `PurchaseOrder` sang entity root `Customer` như một graph sở hữu, hệ thống có thể hiểu sai vòng đời và cách lưu. Đối với aggregate độc lập, nên dùng ID/reference phù hợp thay cho quan hệ object sở hữu.

### Chi phí khi lưu aggregate có collection

Đối với nhiều kiểu mapping Spring Data JDBC, khi lưu một aggregate đã tồn tại, framework có thể xóa rồi chèn lại những entity con được tham chiếu, ngay cả khi một số phần tử không đổi; root được cập nhật riêng. Vì vậy:

- `save(root)` không có nghĩa chỉ phát ra một lệnh `UPDATE`.
- Bất biến ở cấp Java không có nghĩa chỉ những field thay đổi mới được ghi xuống database.
- Aggregate quá lớn có thể gây nhiều SQL, ghi log, khóa và xung đột phiên bản hơn cần thiết.
- Nếu hai nhóm dữ liệu có vòng đời và transaction độc lập, cân nhắc tách aggregate trước khi giải quyết bằng cấu hình pool.

Cần quan sát SQL thực tế của phiên bản Spring Data JDBC và kiểu mapping đang dùng để đánh giá chi phí cụ thể.

## 10. Thiết kế API bảo vệ invariant

Một lỗi phổ biến là dựng mô hình với toàn bộ setter công khai:

~~~java
// Ví dụ thiết kế dễ vi phạm invariant.
order.setStatus(Status.CONFIRMED);
order.setTotal(new Money(0, "VND"));
order.getLines().clear();
~~~

Nếu nghiệp vụ yêu cầu đơn đã xác nhận phải có ít nhất một dòng hàng và tổng tiền phải khớp các dòng, ba lời gọi trên có thể tạo trạng thái sai mà không thành phần nào chịu trách nhiệm kiểm soát.

API theo hành vi nghiệp vụ làm trách nhiệm rõ ràng:

~~~java
PurchaseOrder updated = order
        .addLine("BOOK-A", 2, new Money(85_000, "VND"))
        .addLine("PEN-B", 1, new Money(15_000, "VND"))
        .confirm();
~~~

Ví dụ này minh họa API mục tiêu; lớp `PurchaseOrder` giản lược ở mục 7 chưa cài đặt `addLine`. Trong thiết kế đầy đủ, `addLine` phải:

1. Kiểm tra đơn còn cho phép sửa.
2. Kiểm tra mã hàng, số lượng và loại tiền hợp lệ.
3. Tạo tập dòng hàng mới hoặc thay đổi có kiểm soát.
4. Tính lại tổng tiền từ các dòng, tránh đồng bộ thủ công hai nguồn dữ liệu.
5. Trả trạng thái aggregate hợp lệ tiếp theo.

Với object immutable, mỗi bước trả bản sao mới. Nếu sử dụng entity mutable có đóng gói, cùng logic có thể được thực thi trong một phương thức và sửa collection private. Cả hai hướng đều có thể giữ invariant; lựa chọn tùy độ phức tạp, kích thước aggregate và nhu cầu ánh xạ.

### Invariant ở các lớp khác nhau

| Lớp | Ví dụ quy tắc | Vì sao cần |
| --- | --- | --- |
| Constructor/factory của value object | `Money` không âm, mã tiền đúng hình dạng | Không tồn tại giá trị miền sai ngay từ lúc tạo. |
| Phương thức của aggregate root | Không xác nhận đơn khi thiếu dòng hàng | Bảo vệ quy tắc chuyển trạng thái nghiệp vụ. |
| Application service | Kiểm tra quyền thao tác, điều phối nhiều root | Quyết định ai làm gì và trong ngữ cảnh nào. |
| Database constraint | `NOT NULL`, `UNIQUE`, `CHECK`, foreign key phù hợp | Bảo vệ dữ liệu trước truy cập ngoài ứng dụng, lỗi đồng thời hoặc mã bỏ qua domain model. |
| Optimistic locking / transaction | Chặn cập nhật dựa trên phiên bản cũ, commit/rollback | Duy trì nhất quán khi có nhiều tác vụ đồng thời. |

Đừng cố dồn mọi điều kiện vào annotation validation của request, vì một entity có thể được tạo từ batch job, message handler hoặc code nội bộ mà không đi qua HTTP validation. Quy tắc cốt lõi phải được bảo vệ tại nơi mọi đường đi đều gặp: value object, aggregate và database khi thích hợp.

## 11. Những khác biệt cần nhớ khi dùng Spring Data JDBC

Thiết kế entity/value object có thể áp dụng rộng rãi, nhưng hạ tầng persistence ảnh hưởng đến cách hiện thực.

### 11.1. Spring Data JDBC không phải JPA

| Đặc điểm | Spring Data JDBC | JPA/Hibernate (để đối chiếu) |
| --- | --- | --- |
| Mô hình sở hữu | Tập trung vào aggregate root và thành phần thuộc aggregate | Entity graph và quan hệ có thể được quản lý với nhiều kiểu mapping. |
| Persistence context theo dõi dirty field | Không có cơ chế đó như JPA | Thường có dirty checking cho managed entity. |
| Lưu object đã thay đổi | Thường gọi repository `save(...)` rõ ràng | Managed entity có thể được flush tự động trong transaction. |
| Quan hệ giữa aggregate độc lập | Thường lưu ID/tham chiếu theo ID | Có thể dùng association entity như `@ManyToOne` theo cách JPA. |
| Lazy loading kiểu entity proxy của JPA | Không dựa trên persistence context/lazy-loading model đó | Có thể có lazy association tùy mapping. |

Không lấy ví dụ JPA dùng `@Entity`, `@OneToMany`, `@ManyToOne` rồi mặc định áp dụng nguyên xi cho Spring Data JDBC. Spring Data JDBC dùng annotation của Spring Data Relational như `@Table`, `@MappedCollection`, `@Embedded` cùng annotation Spring Data Commons như `@Id` và `@Version`.

### 11.2. Bất biến và materialization

Framework cần dựng entity từ dữ liệu trong database. Với class immutable, một số cách phù hợp gồm:

- Constructor khai báo rõ các thuộc tính cần khôi phục; dùng `@PersistenceCreator` khi cần chỉ định.
- Record cho value object đơn giản hoặc trường hợp entity thật sự phù hợp.
- Với thuộc tính do hệ thống lưu trữ cập nhật (ID/version), cung cấp cách tạo bản sao bằng `withId(...)`/`withVersion(...)` hoặc kiểu copy creator được framework hỗ trợ.
- Bảo đảm property mapping và tên tham số constructor được xác định đúng; tránh overload nhiều constructor mơ hồ.

Một constructor persistence không nên bí mật truy cập mạng hoặc sinh lại định danh nghiệp vụ: nó phải tái dựng được trạng thái đã lưu. Nếu cần invariant phức tạp, nên thiết kế riêng cách tạo mới qua factory và cách khôi phục từ dữ liệu hợp lệ, đồng thời giữ ràng buộc dữ liệu ở database.

### 11.3. Phân biệt immutable object với immutable business fact

Ví dụ hóa đơn đã phát hành có thể là **chứng từ nghiệp vụ không được sửa nội dung** theo quy tắc miền. Đó là tính bất biến ở cấp nghiệp vụ. Ngược lại, `PurchaseOrder` có thể được biểu diễn bằng class Java immutable nhưng vẫn chuyển trạng thái qua các phiên bản mới. Một hệ thống có thể cần cả hai:

- **Immutable implementation:** ngăn mutation trực tiếp để code dễ suy luận.
- **Immutable business fact:** ngăn thao tác miền thay đổi dữ liệu đã chốt dù implementation có cho phép copy.

Không suy ra tính bất biến nghiệp vụ chỉ từ từ khóa Java `final`.

## 12. Cân nhắc khi chọn entity immutable

### Lợi ích

- Dễ suy luận vì một object không đổi khi được truyền giữa các hàm.
- Tránh caller vô tình sửa collection hoặc field nội bộ.
- Tạo đường đi thay đổi trạng thái rõ ràng qua phương thức nghiệp vụ.
- Hữu ích khi cần so sánh snapshot trước và sau, log sự kiện hoặc kiểm tra invariant.
- Hạn chế nhiều loại lỗi do chia sẻ tham chiếu mutable trong một luồng xử lý.

### Đánh đổi

- Cần tạo bản sao khi thay đổi; aggregate chứa nhiều phần tử có thể tốn bộ nhớ/copy.
- Mapping ID/version do database sinh đòi hỏi constructor hoặc wither hợp lệ.
- Nhiều phép copy có thể làm API rườm rà nếu mô hình chưa được tổ chức tốt.
- Immutability không loại bỏ transaction, race condition, lost update hay những yêu cầu đồng bộ giữa nhiều instance.
- Với Spring Data JDBC, hiệu năng truy cập dữ liệu vẫn phụ thuộc SQL do repository tạo; immutable object không làm thao tác lưu tự động trở thành cập nhật tối thiểu.

Có thể chọn **value object immutable gần như mặc định**, còn entity có thể immutable hoàn toàn hoặc mutable được đóng gói chặt. Tính đúng của invariant, khả năng hiểu code và chi phí lưu thực tế quan trọng hơn việc cố áp dụng một kiểu cho mọi aggregate.

## 13. Các lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Hướng khắc phục |
| --- | --- | --- |
| Xem mọi DTO/table row là entity miền | Mô hình bị kéo theo cấu trúc database, thiếu hành vi nghiệp vụ | Xác định identity và vòng đời từ quy tắc miền. |
| Value object có setter | Các phần của hệ thống có thể thấy giá trị thay đổi ngoài dự kiến | Dùng record/immutable class, trả value mới khi thao tác. |
| Record chứa `List` mutable | Caller thay đổi gián tiếp trạng thái đã cho là bất biến | Sao chép collection và cân nhắc bất biến sâu. |
| So sánh entity bằng toàn bộ field | Cùng entity sau khi đổi trạng thái bị xem như hai entity | Xác định chiến lược identity phù hợp. |
| Dùng ID do DB sinh trong `hashCode()` trước và sau lưu | Hash thay đổi khi object đã nằm trong hash collection | Dùng chiến lược equality ổn định hoặc không phụ thuộc ID thay đổi. |
| Setter công khai cho status, total, lines | Caller bỏ qua invariant | Cung cấp method thể hiện ý định nghiệp vụ và kiểm tra trạng thái. |
| Expose danh sách con có thể sửa | Caller chèn/xóa child ngoài root | Trả view không sửa được hoặc bản sao; mutation đi qua root. |
| Root trực tiếp sở hữu một root khác | Aggregate phình lớn và sai vòng đời | Tham chiếu aggregate độc lập qua ID. |
| Cho rằng mọi `save` chỉ ghi field thay đổi | Bỏ sót chi phí cập nhật/deletion/reinsertion child | Quan sát SQL, cân nhắc kích thước aggregate. |
| Cho rằng immutable tự giải quyết concurrency | Vẫn có lost update tại database | Dùng `@Version`, transaction và giải pháp xử lý xung đột. |

## 14. Tình huống tự vận dụng

### Tình huống A — Chọn entity hay value object?

Một khách hàng có thể lưu nhiều địa chỉ. Địa chỉ giao hàng được chụp vào mỗi đơn hàng và phải giữ nguyên nội dung kể cả khi khách hàng sửa địa chỉ trong hồ sơ.

**Hướng thiết kế:** `Customer` là aggregate root có identity riêng. Địa chỉ đã gắn vào đơn phù hợp làm value object dạng snapshot immutable. Đơn hàng giữ giá trị địa chỉ lúc đặt hàng, không tham chiếu để tự thay đổi theo profile.

### Tình huống B — Invariant của giỏ hàng

Quy tắc yêu cầu số lượng mỗi dòng lớn hơn 0 và tổng tiền luôn bằng tổng các dòng. Một controller gọi `setQuantity(0)` rồi `setTotal(100_000)`.

**Vấn đề:** invariant có thể bị phá vỡ vì logic nằm rời rạc. **Hướng thiết kế:** controller gọi `cart.changeQuantity(lineId, requestedQuantity)`, aggregate root tự kiểm tra và tính lại total; không cung cấp setter độc lập cho giá trị dẫn xuất.

### Tình huống C — Hai nhân viên cùng xác nhận đơn

Cả hai đều đọc order version 5. Người thứ nhất lưu thành công; người thứ hai tiếp tục save object immutable đã tạo từ version 5.

**Hướng xử lý:** trường `@Version` giúp phát hiện bản lưu cũ. Ứng dụng đọc lại trạng thái, áp dụng lại quy tắc miền và trả về thông báo xung đột hoặc retry có điều kiện. Không tự động retry mọi side effect ngoài database.

### Tình huống D — Aggregate quá rộng

Một đơn hàng được lưu kèm toàn bộ lịch sử thanh toán, địa chỉ tài khoản khách hàng và bảng lịch sử vận chuyển; một thay đổi nhỏ buộc lưu graph lớn.

**Hướng thiết kế:** hỏi thành phần nào thật sự cần được nhất quán trong cùng một transaction. Tách các thực thể có vòng đời độc lập thành aggregate riêng, lưu khóa tham chiếu và xây cơ chế phối hợp nếu cần. Nhờ vậy giảm chi phí ghi và tránh việc một root sở hữu dữ liệu không thuộc trách nhiệm của mình.

## 15. Nguyên tắc ghi nhớ

Để thiết kế aggregate tốt trong Spring Data JDBC:

1. **Chọn entity khi cần identity; chọn value object khi cần equality theo nội dung.**
2. **Đưa invariant vào nơi sở hữu dữ liệu:** value object tự kiểm tra giá trị, aggregate root kiểm soát thay đổi của thành viên.
3. **Thiết kế API theo hành vi nghiệp vụ:** `confirm()`, `changeQuantity()` hoặc `replaceAddress()` diễn đạt ý định tốt hơn chuỗi setter.
4. **Bảo vệ tính bất biến đúng mức:** immutable value object, defensive copy cho collection và chiến lược thay đổi entity rõ ràng.
5. **Hiểu đặc trưng Spring Data JDBC:** root là đơn vị lưu aggregate, mapping quan hệ con khác JPA và `save` có thể tạo nhiều SQL.
6. **Xử lý đồng thời ở tầng persistence:** ID xác định entity, `@Version` phát hiện bản ghi cũ, transaction/constraint giúp giữ nhất quán.

Mục tiêu của mô hình không phải làm mọi lớp Java đều bất biến bằng mọi giá. Mục tiêu là bảo đảm **mọi trạng thái được chấp nhận đều hợp lệ**, **mọi thay đổi có chủ đích nghiệp vụ**, và **ranh giới aggregate đủ nhỏ, đủ rõ để Spring Data JDBC lưu trữ một cách đáng tin cậy**.
