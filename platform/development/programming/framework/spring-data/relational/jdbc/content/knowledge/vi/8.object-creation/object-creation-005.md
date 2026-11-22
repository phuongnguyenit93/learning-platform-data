# Thiết kế entity bất biến và Java record

Trong **Spring Data Relational JDBC**, entity là mô hình Java đại diện cho trạng thái của một aggregate được lưu trong cơ sở dữ liệu quan hệ. Một cách thiết kế phổ biến là dùng class mutable với setter để framework hoặc code nghiệp vụ thay đổi trực tiếp từng field. Tuy nhiên, cách tiếp cận đó có thể khiến trạng thái bị sửa ở nhiều nơi, làm quy tắc nghiệp vụ khó kiểm soát và khiến việc hiểu một object đang ở trạng thái nào trở nên khó khăn.

**Entity bất biến (immutable entity)** giới hạn việc thay đổi trực tiếp trạng thái sau khi object được tạo. Khi nghiệp vụ cần chuyển sang trạng thái mới, ứng dụng tạo một object mới biểu diễn trạng thái tiếp theo rồi lưu nó bằng repository. **Java record** cung cấp cú pháp ngắn gọn để khai báo những object có thành phần dữ liệu cố định sau khi khởi tạo, rất phù hợp với value object và một số mô hình entity.

Để áp dụng đúng trong Spring Data JDBC, cần hiểu đồng thời ba khía cạnh:

- Ngữ nghĩa của entity: danh tính tồn tại xuyên suốt các lần thay đổi trạng thái.
- Ngữ nghĩa của record: dữ liệu bất biến ở mức tham chiếu và equality mặc định dựa trên các thành phần.
- Cơ chế persistence: Spring Data JDBC tạo object từ dữ liệu đọc được, lưu aggregate khi gọi repository và có thể nhận ID/version do database hoặc framework quản lý.

## 1. Mutable entity và immutable entity

Một entity mutable thường cho phép thay đổi field sau khi khởi tạo:

~~~java
public class MutableProduct {
    private Long id;
    private String name;
    private long price;

    public void setName(String name) {
        this.name = name;
    }

    public void setPrice(long price) {
        this.price = price;
    }
}
~~~

Đoạn mã minh họa này có thể tiện khi binding dữ liệu, nhưng bất kỳ code nào có tham chiếu đến object và truy cập được setter đều có thể thay đổi nó. Nếu một quy tắc yêu cầu giá phải dương, việc kiểm tra trong một setter không đảm bảo mọi đường cập nhật đều giữ đúng invariant nếu còn setter khác hoặc field bị truy cập trực tiếp.

Entity bất biến thường có các đặc điểm:

- Trạng thái được thiết lập khi tạo object.
- Các field được khai báo `final` hoặc record component.
- Không cung cấp setter công khai.
- Giá trị đầu vào được kiểm tra trong constructor/factory.
- Hành vi nghiệp vụ tạo ra một object biểu diễn trạng thái tiếp theo.

~~~java
public record ProductState(String name, long price) {
    public ProductState {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên sản phẩm không được trống");
        }
        if (price < 0) {
            throw new IllegalArgumentException("Giá không được âm");
        }
    }

    public ProductState changePrice(long newPrice) {
        return new ProductState(name, newPrice);
    }
}
~~~

Sau khi tạo `ProductState`, không thể gán lại `name` hoặc `price`. Phương thức `changePrice` trả về object mới. Object cũ vẫn biểu diễn trạng thái trước đó.

### 1.1. Immutability không có nghĩa entity không thể thay đổi theo nghiệp vụ

Một đơn hàng có thể chuyển từ `DRAFT` sang `CONFIRMED`. Nếu entity được triển khai immutable, hai trạng thái có thể được biểu diễn bằng hai object Java:

~~~text
PurchaseOrder(id=42, status=DRAFT)
          |
          | confirm()
          v
PurchaseOrder(id=42, status=CONFIRMED)

Object trước và sau là hai instance khác nhau.
Cả hai cùng biểu diễn entity nghiệp vụ có danh tính id=42.
~~~

Đây là điểm cần phân biệt:

- **Identity** trả lời “đây là entity nào?”.
- **State** trả lời “entity hiện có dữ liệu gì?”.
- **Immutability** quy định object Java đã tạo có được sửa trạng thái trực tiếp hay không.

Entity vẫn có thể có nhiều trạng thái theo thời gian. Tính bất biến chỉ làm cho mỗi object biểu diễn một trạng thái xác định.

### 1.2. Lợi ích của entity bất biến

**Dễ suy luận:** sau khi nhận một object, code có thể tin rằng trạng thái của nó không tự đổi do một thành phần khác giữ cùng tham chiếu.

**Kiểm soát invariant:** constructor/factory và phương thức nghiệp vụ là các điểm rõ ràng để xác nhận dữ liệu hợp lệ.

**An toàn khi chia sẻ tham chiếu:** giảm nguy cơ một luồng xử lý thay đổi dữ liệu mà luồng khác đang đọc.

**Dễ kiểm thử:** có thể kiểm tra đầu vào và object kết quả mà không phải chuẩn bị rồi kiểm tra nhiều lần mutation trên cùng instance.

**Thể hiện lịch sử trạng thái:** object cũ có thể được giữ lại như snapshot trong một luồng xử lý, log hoặc phép so sánh trước/sau nếu nghiệp vụ cần.

### 1.3. Đánh đổi

Immutability không miễn phí. Khi thay đổi trạng thái, ứng dụng cần tạo object mới; nếu object chứa nhiều collection, việc sao chép có thể tốn bộ nhớ và thời gian. Với entity được database sinh ID/version, persistence framework cũng cần một cách tạo instance mới mang giá trị do hệ thống lưu trữ trả về.

Vì vậy, mục tiêu không phải làm mọi object đều immutable bằng mọi giá. Hãy chọn kiểu mô hình giúp giữ invariant rõ ràng, mapping dễ hiểu và chi phí phù hợp.

## 2. Java record là gì?

Java record được giới thiệu từ Java 14 dưới dạng preview và trở thành tính năng chính thức từ **Java 16**. Record là một dạng class dành cho dữ liệu có các thành phần được khai báo rõ ràng. Compiler tự sinh:

- Các field private final tương ứng với record component.
- Constructor chính (canonical constructor).
- Accessor cùng tên component, ví dụ `name()` thay vì `getName()`.
- `equals()`, `hashCode()` và `toString()` dựa trên các component, trừ khi được ghi đè.

Ví dụ:

~~~java
public record Money(long minorUnits, String currency) {
}
~~~

Tương đương về ý tưởng với một class có field private final, constructor, accessor và các phương thức equality/hash cơ bản. Record giúp giảm code lặp, đồng thời làm rõ rằng danh tính của kiểu dữ liệu này gắn với tập giá trị của nó.

### 2.1. Record component và accessor

Với khai báo:

~~~java
public record CustomerName(String firstName, String lastName) {
}
~~~

Java sinh accessor:

~~~java
CustomerName customer = new CustomerName("An", "Nguyen");

String first = customer.firstName();
String last = customer.lastName();
~~~

Không phải `getFirstName()` và `getLastName()` như JavaBean truyền thống. Các framework hiện đại, trong đó có Spring Data, hỗ trợ constructor/property discovery cho record, nhưng khi viết code Java trực tiếp phải dùng accessor đúng cú pháp.

### 2.2. Compact constructor để kiểm tra invariant

Record có thể khai báo compact constructor:

~~~java
public record Money(long minorUnits, String currency) {
    public Money {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("Số tiền không được âm");
        }
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Mã tiền không hợp lệ");
        }
    }
}
~~~

Compact constructor không khai báo lại danh sách tham số. Các tham số component có thể được kiểm tra hoặc chuẩn hóa; sau khi constructor kết thúc, Java gán chúng vào field tương ứng. Đây là vị trí thích hợp để bảo vệ invariant của value object.

Lưu ý ví dụ kiểm tra ba chữ cái chỉ kiểm tra hình dạng mã, không xác nhận mã đó là đơn vị tiền tệ được hệ thống hỗ trợ. Quy tắc miền thực tế có thể cần danh sách tiền tệ hoặc kiểu enum.

### 2.3. Record không cho phép kế thừa

Record là final một cách ngầm định. Nó không thể được mở rộng bởi class khác, nhưng vẫn có thể implement interface:

~~~java
public interface Identified<ID> {
    ID id();
}

public record ProductId(Long value) {
}
~~~

Không thể viết `class SpecialProduct extends ProductRecord` nếu `ProductRecord` là record. Hãy dùng composition hoặc interface khi cần mở rộng hành vi.

## 3. Bất biến nông và bất biến sâu

Record bảo vệ việc gán lại component, nhưng điều đó không tự làm object được tham chiếu trở nên immutable.

Ví dụ:

~~~java
public record OrderSnapshot(List<String> productCodes) {
}

List<String> codes = new ArrayList<>();
codes.add("BOOK-A");

OrderSnapshot snapshot = new OrderSnapshot(codes);
codes.add("PEN-B");

System.out.println(snapshot.productCodes()); // [BOOK-A, PEN-B]
~~~

Field tham chiếu trong record là final, nhưng danh sách ban đầu vẫn có thể thay đổi. Object record vì vậy chưa bất biến sâu.

Để bảo vệ collection, tạo bản sao không cho chỉnh sửa:

~~~java
public record OrderSnapshot(List<String> productCodes) {
    public OrderSnapshot {
        productCodes = List.copyOf(productCodes);
    }
}
~~~

`List.copyOf` tạo danh sách không sửa được và không cho phép phần tử null. Đây là bản sao nông: nếu phần tử là một object mutable, trạng thái nội bộ của phần tử vẫn có thể thay đổi. Để có immutability sâu, các phần tử cũng cần immutable hoặc phải được sao chép theo quy tắc phù hợp.

Tương tự, cần cẩn thận với array, `Date` mutable, collection lồng nhau và object do thư viện bên ngoài cung cấp. `final` trên tham chiếu không đồng nghĩa với bất biến của toàn bộ object graph.

## 4. Khi nào Java record phù hợp?

Record đặc biệt phù hợp với **value object**:

- `Money`: số tiền và mã tiền.
- `EmailAddress`: địa chỉ email đã chuẩn hóa.
- `DateRange`: ngày bắt đầu và ngày kết thúc.
- `AddressSnapshot`: địa chỉ giao hàng tại thời điểm đặt hàng.
- `SearchCriteria`: tiêu chí tìm kiếm của một request.
- `ProductSummary`: dữ liệu tóm tắt phục vụ một truy vấn.

Record cũng có thể được dùng làm entity trong một số mô hình, vì Spring Data JDBC hỗ trợ ánh xạ object immutable và Java record. Tuy nhiên, cần cân nhắc ngữ nghĩa equality mặc định.

| Tiêu chí | Value object | Entity |
| --- | --- | --- |
| Điều tạo nên sự đồng nhất | Giá trị các thuộc tính | Danh tính ổn định |
| Hai instance có mọi giá trị bằng nhau | Thường được xem là tương đương | Vẫn có thể là hai entity khác nhau |
| Thay đổi | Tạo giá trị mới | Cùng identity nhưng có trạng thái mới |
| Record mặc định | Rất phù hợp | Có thể dùng, nhưng equality theo tất cả component có thể không phù hợp |

### 4.1. Equality mặc định của record có thể không phù hợp với entity

Giả sử:

~~~java
public record Product(Long id, String name, long price) {
}

Product a = new Product(10L, "Book", 100_000);
Product b = new Product(10L, "Book", 120_000);
~~~

`a.equals(b)` trả `false` vì giá khác nhau. Nhưng theo ngữ nghĩa entity, hai object có cùng danh tính `id=10` có thể là hai phiên bản trạng thái của cùng một sản phẩm.

Trường hợp khác:

~~~java
Product a = new Product(10L, "Book", 100_000);
Product b = new Product(11L, "Book", 100_000);
~~~

Hai sản phẩm có các thuộc tính mô tả giống nhau nhưng ID khác nhau; đây là hai entity khác nhau.

Vì vậy:

- Với value object, equality theo mọi component thường là điều mong muốn.
- Với entity, equality thường dựa trên identity ổn định theo quy tắc miền.
- Record tự sinh equality theo mọi component; nếu dùng record làm entity, cần xác nhận semantics đó có đúng với domain hay không.

Có thể ghi đè `equals()` và `hashCode()` trong record, nhưng phải tuân thủ hợp đồng equality/hash và xử lý cẩn thận entity mới chưa có ID. Một class thông thường với chiến lược identity rõ ràng có thể dễ hiểu hơn cho entity phức tạp.

### 4.2. Record không phải DTO trong mọi trường hợp

Record thường rất phù hợp cho DTO, nhưng không có nghĩa mọi record đều chỉ là DTO. Một record có thể chứa hành vi miền, kiểm tra invariant và phương thức tạo giá trị mới. Ngược lại, một class có getter/setter cũng có thể là DTO. Vai trò phụ thuộc vào trách nhiệm và ngữ nghĩa của kiểu, không phụ thuộc riêng vào từ khóa khai báo.

## 5. Spring Data JDBC hỗ trợ object immutable như thế nào?

Spring Data JDBC cần chuyển dữ liệu giữa database và object Java. Với class mutable, framework có thể tạo instance rồi gán các thuộc tính theo cơ chế mapping. Với object immutable, framework phải tạo object thông qua constructor phù hợp.

Luồng đọc có thể hình dung:

~~~text
SELECT ... FROM product
          |
          v
     ResultSet / Row
          |
          v
 Spring Data JDBC mapping
          |
          v
 constructor / canonical constructor
          |
          v
     Product instance
~~~

Đối với Java record, canonical constructor cung cấp một điểm tạo object tự nhiên. Spring Data có thể sử dụng record component và tên tham số constructor để ánh xạ giá trị đọc được.

Luồng lưu một aggregate mới có thể như sau:

~~~text
Product(id=null, name="Book", ...)
          |
          v
 repository.save(product)
          |
          v
       INSERT SQL
          |
          v
 database sinh ID
          |
          v
 Spring Data tạo trạng thái instance đã có ID
          |
          v
      returned Product
~~~

Với entity immutable, giá trị do persistence layer sinh ra như ID hoặc version không thể được gán vào field final của instance ban đầu. Framework cần tạo một instance mang giá trị mới, dựa trên cơ chế tạo/copy object được hỗ trợ. Vì thế code ứng dụng phải sử dụng **object được trả về từ repository** khi cần ID hoặc version sau khi lưu.

## 6. Ánh xạ một Java record làm aggregate root

Giả sử bảng `product`:

~~~sql
CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price_minor_units BIGINT NOT NULL,
    price_currency VARCHAR(3) NOT NULL
);
~~~

Ta có thể mô hình hóa giá tiền thành record value object:

~~~java
public record Money(long minorUnits, String currency) {
    public Money {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("Số tiền không được âm");
        }
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Mã tiền không hợp lệ");
        }
    }
}
~~~

Record root:

~~~java
import java.util.Objects;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("product")
public record Product(
        @Id Long id,
        @Version Long version,
        String sku,
        String name,
        @Embedded(prefix = "price_") Money price
) {
    public Product {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU không được để trống");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên sản phẩm không được để trống");
        }
        Objects.requireNonNull(price, "price");
    }

    public static Product create(String sku, String name, Money price) {
        return new Product(null, null, sku, name, price);
    }

    public Product rename(String newName) {
        return new Product(id, version, sku, newName, price);
    }

    public Product changePrice(Money newPrice) {
        return new Product(id, version, sku, name, newPrice);
    }
}
~~~

Ví dụ dùng `@Embedded(prefix = "price_")` để ánh xạ hai component của `Money` vào cột `price_minor_units` và `price_currency` theo quy tắc đặt tên snake_case của Spring Data Relational. Nếu ứng dụng dùng naming strategy khác, tên cột cần được cấu hình tương ứng.

Một số điểm cần chú ý:

- `@Table("product")` xác định bảng.
- `@Id` xác định thuộc tính khóa.
- `@Version` đánh dấu version dùng cho optimistic locking.
- `@Embedded` ánh xạ value object vào cùng hàng.
- `id` và `version` dùng kiểu wrapper để biểu diễn trạng thái chưa được persistence layer cấp giá trị bằng `null`.
- Compact constructor xác nhận invariant ngay khi tạo instance.
- `rename` và `changePrice` trả về instance mới, giữ nguyên ID/version của snapshot hiện tại.

Đây là ví dụ mô hình hóa record aggregate root; schema identity và chi tiết mapping cần khớp với database/phiên bản Spring Data JDBC của dự án. Với các component có tên trùng từ khóa SQL hoặc kiểu đặc biệt, có thể cần annotation tên cột tường minh.

### 6.1. Repository

~~~java
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository extends CrudRepository<Product, Long> {
}
~~~

Spring Data JDBC cung cấp implementation repository tại runtime dựa trên mapping metadata. Ứng dụng không cần tự viết implementation cho các thao tác CRUD cơ bản.

### 6.2. Tạo và lưu record

~~~java
Product draft = Product.create(
        "BOOK-021",
        "Spring Data JDBC",
        new Money(185_000, "VND")
);

Product saved = productRepository.save(draft);

System.out.println(draft.id()); // null: instance ban đầu không bị mutate
System.out.println(saved.id()); // ID do persistence layer trả về
~~~

Điểm quan trọng là giữ kết quả `save`:

~~~java
Product saved = productRepository.save(draft);
Long productId = saved.id();
~~~

Không tiếp tục dùng `draft.id()` với giả định nó sẽ được cập nhật. Với entity immutable, instance gốc vẫn đại diện cho trạng thái trước khi lưu.

### 6.3. Đọc và thay đổi trạng thái

~~~java
Product current = productRepository.findById(productId)
        .orElseThrow();

Product renamed = current.rename("Spring Data Relational JDBC");
Product savedAgain = productRepository.save(renamed);
~~~

`rename` tạo một record mới với cùng ID và version đã đọc. Repository thực hiện lưu; kết quả trả về là instance cần dùng cho những thao tác tiếp theo, nhất là khi version được cập nhật.

Spring Data JDBC không dùng persistence context/dirty checking như JPA. Việc tạo object mới không tự phát ra SQL. Ứng dụng cần gọi `save` trong repository hoặc thực hiện SQL qua API JDBC thích hợp để thay đổi được lưu.

## 7. Version và optimistic locking với entity immutable

Khi nhiều request cùng đọc và cập nhật một entity, chỉ dựa vào việc object Java immutable là chưa đủ để tránh ghi đè dữ liệu. Hai request có thể cùng đọc version 4 rồi tạo hai object mới từ cùng snapshot.

`@Version` hỗ trợ phát hiện cập nhật dựa trên version cũ:

~~~text
Database: Product #10, version=4, price=100

Request A đọc version 4       Request B đọc version 4
        |                             |
        v                             v
 A tạo object price=120        B tạo object price=130
        |                             |
        v                             v
 A save với version 4          B save với version 4
        |
        v
 A thành công, version tăng
        |
        +-----------------------------+
                                      v
                         B không còn khớp version hiện tại
                                      |
                                      v
                           Optimistic locking failure
~~~

Nếu một thao tác lưu dùng version cũ, Spring Data JDBC có thể báo lỗi optimistic locking thay vì âm thầm ghi đè thay đổi của request khác.

Khi dùng record:

- Version là một component của record.
- Khi tạo object mới để thay đổi nghiệp vụ, giữ version đang có.
- Sau khi save thành công, dùng object được trả về để nhận version mới.
- Khi gặp xung đột, đọc lại trạng thái mới và đánh giá lại nghiệp vụ trước khi thử lại.

Không tự tăng version trong phương thức `rename` hoặc `changePrice`. Version là metadata đồng bộ của persistence layer; tự tăng có thể làm sai điều kiện cập nhật.

## 8. Thiết kế immutable entity bằng class thông thường

Java record rất ngắn gọn, nhưng entity có identity phức tạp, equality tùy chỉnh hoặc nhiều cách khởi tạo có thể phù hợp với class thông thường hơn.

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public final class PurchaseOrder {

    @Id
    private final Long id;

    @Version
    private final Long version;

    private final String orderNumber;
    private final String status;

    @PersistenceCreator
    public PurchaseOrder(
            Long id,
            Long version,
            String orderNumber,
            String status
    ) {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException("Mã đơn không hợp lệ");
        }
        if (status == null || status.isBlank()) {
            throw new IllegalArgumentException("Trạng thái không hợp lệ");
        }
        this.id = id;
        this.version = version;
        this.orderNumber = orderNumber;
        this.status = status;
    }

    public static PurchaseOrder draft(String orderNumber) {
        return new PurchaseOrder(null, null, orderNumber, "DRAFT");
    }

    public PurchaseOrder confirm() {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException("Chỉ xác nhận đơn đang nháp");
        }
        return new PurchaseOrder(id, version, orderNumber, "CONFIRMED");
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public String getStatus() {
        return status;
    }
}
~~~

`@PersistenceCreator` đánh dấu constructor mà Spring Data sử dụng để khôi phục object khi cần chọn giữa nhiều constructor/factory. Constructor nhận các thuộc tính persistence; không yêu cầu caller cung cấp giá trị tạm không được ánh xạ.

### 8.1. Wither/copy method

Một class immutable có thể cung cấp phương thức tạo bản sao với một thuộc tính thay đổi:

~~~java
public PurchaseOrder withId(Long generatedId) {
    return new PurchaseOrder(
            generatedId, version, orderNumber, status
    );
}

public PurchaseOrder withVersion(Long newVersion) {
    return new PurchaseOrder(
            id, newVersion, orderNumber, status
    );
}
~~~

Đây là ví dụ về *wither*: trả về instance mới có một giá trị khác, không mutate instance hiện tại. Cơ chế object mapping của Spring Data có thể sử dụng các cách tạo/copy object phù hợp để đưa giá trị do persistence layer cung cấp vào immutable entity. Với record, canonical constructor và metadata component là cách tạo object tự nhiên; với class, constructor hoặc wither có thể được sử dụng tùy cấu trúc.

Không nên tự viết code ứng dụng để giả định framework luôn gọi một phương thức tên `withId` cụ thể. Hãy tuân theo quy tắc object mapping của phiên bản Spring Data đang dùng và luôn dùng kết quả repository trả về.

## 9. Java record cho value object trong aggregate

Một trường hợp rất phù hợp là dùng record cho giá trị nhúng:

~~~java
public record ShippingAddress(
        String recipient,
        String street,
        String city,
        String postalCode
) {
    public ShippingAddress {
        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException("Thiếu người nhận");
        }
        if (street == null || street.isBlank()) {
            throw new IllegalArgumentException("Thiếu địa chỉ đường");
        }
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("Thiếu thành phố");
        }
    }
}
~~~

Hai địa chỉ có cùng nội dung có thể được coi là tương đương theo value equality. Khi địa chỉ giao hàng của đơn thay đổi trước lúc xác nhận, aggregate root có thể được tạo lại với một `ShippingAddress` mới.

Trong Spring Data JDBC, có thể dùng `@Embedded` để ánh xạ các component của value object vào cột cùng hàng:

~~~java
@Embedded(prefix = "shipping_")
ShippingAddress shippingAddress
~~~

Tên cột cụ thể được tạo theo prefix và naming strategy, ví dụ `shipping_recipient`, `shipping_street` và `shipping_city`. Nếu có nhiều object cùng kiểu trong một row, prefix giúp tránh trùng tên cột.

### 9.1. Record lồng trong record

Có thể kết hợp:

~~~java
public record OrderHeader(
        String orderNumber,
        ShippingAddress shippingAddress
) {
}
~~~

Điều cần quan tâm là mapping metadata của Spring Data JDBC, không phải chỉ cú pháp Java. Với value object nhúng, xác định cột bằng `@Embedded` và schema tương ứng. Với collection entity con, dùng cơ chế mapping collection trong aggregate như `@MappedCollection`; đừng nhầm object nhúng với một bảng con độc lập.

## 10. Record chứa collection trong aggregate

Aggregate root đôi khi chứa danh sách thành phần. Record vẫn có thể khai báo component kiểu collection, nhưng phải bảo vệ collection để caller không sửa nội dung sau khi tạo:

~~~java
public record OrderDraft(
        String orderNumber,
        List<String> productCodes
) {
    public OrderDraft {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException("Mã đơn không hợp lệ");
        }
        productCodes = List.copyOf(productCodes);
    }

    public OrderDraft addProduct(String productCode) {
        List<String> updated = new ArrayList<>(productCodes);
        updated.add(Objects.requireNonNull(productCode));
        return new OrderDraft(orderNumber, updated);
    }
}
~~~

Phương thức `addProduct` tạo danh sách mới và trả về record mới. Đối tượng cũ không thay đổi.

Nếu đây là collection cần lưu trong Spring Data JDBC, cần ánh xạ nó đúng vào aggregate schema. Ví dụ collection entity con có thể dùng `@MappedCollection` với khóa ngoại trỏ về root và key column khi cần giữ thứ tự. Record component có thể được dùng cho child object nếu mapping constructor và schema tương thích.

Không dùng `List.copyOf` để thay thế annotation mapping: sao chép collection là quyết định immutability ở Java; `@MappedCollection` là metadata mô tả quan hệ lưu trữ. Hai việc giải quyết hai vấn đề khác nhau.

Với aggregate lớn, tạo bản sao toàn bộ collection mỗi lần thay đổi có thể tốn kém. Cân nhắc kích thước aggregate, số lần cập nhật và yêu cầu nhất quán. Nếu collection có vòng đời độc lập, đó có thể là dấu hiệu cần xem lại aggregate boundary.

## 11. Constructor binding và tên thuộc tính

Spring Data JDBC khôi phục object immutable bằng constructor. Để mapping đúng:

- Constructor phải nhận được các giá trị cần thiết để dựng object hợp lệ.
- Tên tham số cần được xác định để liên hệ với property tương ứng.
- Các annotation mapping phải được đặt đúng component/property.
- Constructor phải duy trì invariant mà không yêu cầu dữ liệu không được lưu.

Record có canonical constructor tương ứng với record component, giúp quan hệ giữa tên component và tham số rõ ràng. Với class thông thường, khi có nhiều constructor, dùng `@PersistenceCreator` để chỉ rõ constructor persistence thích hợp.

Với Java class thông thường, tên tham số constructor có thể phụ thuộc metadata biên dịch. Cấu hình `-parameters` thường được dùng để giữ tên tham số trong bytecode. Hãy kiểm tra cấu hình build của dự án khi Spring Data không xác định được tham số.

### 11.1. Đừng đưa dữ liệu không lưu vào constructor persistence

Giả sử entity có một giá trị hiển thị chỉ tính trong request:

~~~java
@Transient
private final String displayLabel;
~~~

Nếu constructor persistence yêu cầu `displayLabel` như một tham số bắt buộc, Spring Data JDBC không có cột tương ứng để lấy giá trị. Nên:

- Tính giá trị bằng method từ các property đã lưu.
- Gắn giá trị sau khi materialize nếu class cho phép trạng thái tạm có kiểm soát.
- Tách view model/DTO nếu dữ liệu chỉ phục vụ trình bày.

Record có canonical constructor gắn với toàn bộ component, nên thêm component transient vào record persistence cần được cân nhắc kỹ. Thông thường, nên giữ record persistence tập trung vào dữ liệu thực sự được ánh xạ và xây view DTO riêng.

## 12. Transaction và lưu entity immutable

Một phương thức service có thể đọc aggregate, tạo trạng thái mới rồi lưu trong transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Product rename(Long id, String newName) {
        Product current = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Không tìm thấy sản phẩm"
                ));

        Product renamed = current.rename(newName);
        return repository.save(renamed);
    }
}
~~~

Đây là cách phối hợp rõ ràng:

1. Repository đọc trạng thái hiện tại.
2. Domain method xác nhận yêu cầu và tạo object tiếp theo.
3. Repository lưu object mới.
4. Service trả về object đã lưu.

Với Spring Data JDBC, gọi `save` là thao tác persistence tường minh. Không có dirty checking tự động kiểu JPA chỉ vì một object đã được đọc trong transaction và một field được thay đổi.

Transaction giúp các thao tác database trong phạm vi được quản lý cùng commit/rollback. Tuy nhiên, không nên giữ transaction mở trong lúc gọi API ngoài, chờ người dùng hoặc thực hiện công việc chậm không liên quan đến database, vì connection và khóa có thể bị giữ lâu.

## 13. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| “Record luôn là entity.” | Record chỉ là dạng class dữ liệu; vai trò entity/value object phụ thuộc domain. |
| “Record immutable sâu.” | Component không thể gán lại, nhưng object được tham chiếu có thể mutable. |
| “Entity immutable không thể đổi trạng thái.” | Có thể tạo instance mới cùng identity với trạng thái tiếp theo. |
| “Record equality luôn đúng cho entity.” | Equality mặc định so sánh mọi component; entity thường cần identity semantics. |
| “Gọi setter hoặc tạo record mới sẽ tự lưu.” | Spring Data JDBC cần gọi repository hoặc SQL tương ứng. |
| “Object ban đầu nhận ID sau save.” | Với immutable object, hãy dùng instance repository trả về. |
| “Có thể tự tăng version trong domain method.” | Version là metadata persistence; không tự sửa nếu không có quy tắc rõ ràng. |
| “`@Version` thay thế transaction.” | Optimistic locking phát hiện xung đột; transaction quản lý ranh giới commit/rollback. |
| “Dùng record sẽ giảm số câu SQL.” | Kiểu Java không quyết định số SQL do aggregate mapping sinh ra. |
| “Một record lồng luôn được lưu thành bảng riêng.” | Value object có thể được embed vào cùng row; collection/child mapping cần khai báo quan hệ riêng. |
| “`final` đảm bảo không có dữ liệu sai.” | Invariant phải được kiểm tra ở constructor, factory, domain behavior và database constraint phù hợp. |

## 14. Chọn record hay class cho mô hình Spring Data JDBC?

| Tình huống | Gợi ý | Lý do |
| --- | --- | --- |
| Value object nhỏ, xác định hoàn toàn bằng component | Java record | Equality theo giá trị và constructor rõ ràng. |
| Request/response DTO hoặc projection | Java record | Ít boilerplate, phù hợp dữ liệu mang đi. |
| Entity có identity và equality tùy chỉnh | Class immutable hoặc class đóng gói mutation | Dễ kiểm soát equality/hashCode theo identity. |
| Entity có state transition đơn giản, equality theo toàn bộ component chấp nhận được | Có thể dùng record | Cần xác nhận semantics và mapping ID/version. |
| Aggregate có nhiều collection và quy tắc thay đổi phức tạp | Cân nhắc class root với collection đóng gói hoặc record có copy method | Chọn theo khả năng giữ invariant và chi phí sao chép. |
| Dữ liệu dẫn xuất chỉ dùng hiển thị | Getter tính toán hoặc DTO record | Không cần lưu trạng thái dư thừa trong entity. |

Không có một quy tắc rằng mọi entity phải mutable hoặc mọi entity phải record. Một mô hình thực tế có thể kết hợp:

- Aggregate root là class immutable vì có identity semantics riêng.
- Value object là record.
- Projection/DTO là record.
- Một số entity con được đóng gói và chỉ thay đổi qua root.

## 15. Ví dụ luồng nghiệp vụ: đổi giá sản phẩm

Giả sử yêu cầu là đổi giá sản phẩm và lưu thay đổi. Mô hình dùng record:

~~~java
public record Product(
        @Id Long id,
        @Version Long version,
        String sku,
        Money price
) {
    public Product {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        Objects.requireNonNull(price);
    }

    public Product changePrice(Money newPrice) {
        return new Product(id, version, sku, newPrice);
    }
}
~~~

Service:

~~~java
@Transactional
public Product changePrice(Long id, Money requestedPrice) {
    Product current = repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy"));

    Product updated = current.changePrice(requestedPrice);
    return repository.save(updated);
}
~~~

Luồng trạng thái:

~~~text
Database row (id=25, version=7, price=100_000)
                    |
                    | findById(25)
                    v
Product #25 v7 price=100_000
                    |
                    | changePrice(120_000)
                    v
Product #25 v7 price=120_000
                    |
                    | repository.save(...)
                    v
Database row (id=25, version=8, price=120_000)
                    |
                    | returned value
                    v
Product #25 v8 price=120_000
~~~

Object trước khi thay đổi vẫn giữ `price=100_000` và `version=7`. Object mới trước khi lưu có cùng version đọc từ database. Sau khi lưu thành công, dùng kết quả trả về có version mới. Nếu một request khác đã cập nhật version 7 trước đó, thao tác lưu có thể thất bại do optimistic locking; service hoặc tầng xử lý lỗi cần quyết định phản hồi phù hợp.

## 16. Checklist thiết kế trước khi đưa entity immutable vào repository

Khi thiết kế một aggregate hoặc entity immutable, hãy tự trả lời:

1. **Identity:** thuộc tính nào xác định entity xuyên suốt các lần đổi trạng thái? Equality mặc định của record có phù hợp không?
2. **Constructor:** Spring Data JDBC có thể tạo object từ những cột được ánh xạ không? Có tham số nào không được lưu nhưng lại bắt buộc không?
3. **Invariant:** constructor/factory và domain method đã từ chối trạng thái sai chưa?
4. **Nested object:** value object và collection có thực sự bất biến sâu hoặc được bảo vệ bằng defensive copy không?
5. **Generated values:** ID/version được nhận từ persistence layer bằng cách nào? Code có giữ instance trả về từ `save` không?
6. **Concurrency:** aggregate có dùng `@Version` khi cần phát hiện cập nhật đồng thời không?
7. **Aggregate mapping:** object nhúng và collection child được ánh xạ đúng với schema Spring Data JDBC không?
8. **Persistence lifecycle:** ứng dụng có gọi `save` tường minh sau khi tạo trạng thái mới không?
9. **Performance:** việc sao chép collection và lưu aggregate có kích thước phù hợp với tần suất cập nhật không?
10. **API boundary:** entity có bị dùng trực tiếp làm request/response khiến trạng thái persistence lộ ra ngoài không? Nếu có, DTO riêng có rõ ràng hơn không?

## Ghi nhớ

Entity bất biến giúp mỗi object biểu diễn một trạng thái rõ ràng; Java record cung cấp cách khai báo ngắn gọn và equality theo giá trị, nên đặc biệt phù hợp với value object. Với entity có identity, phải xem xét equality mặc định của record và vòng đời ID/version do persistence quản lý.

Trong Spring Data JDBC, object immutable được khôi phục qua constructor và thay đổi chỉ được lưu khi ứng dụng gọi repository hoặc SQL tương ứng. Khi lưu entity mới hoặc entity có version, hãy sử dụng object mà repository trả về. Bảo vệ collection bằng defensive copy, giữ invariant trong mô hình miền, và dùng transaction cùng optimistic locking khi nghiệp vụ cần kiểm soát cập nhật đồng thời.
