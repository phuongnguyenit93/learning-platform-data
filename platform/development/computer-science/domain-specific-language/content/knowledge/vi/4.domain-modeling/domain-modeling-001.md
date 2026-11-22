# Thực thể và đối tượng giá trị

Trong mô hình miền (*domain model*), một khái niệm nghiệp vụ có thể được biểu diễn bằng **thực thể** (*entity*) hoặc **đối tượng giá trị** (*value object*). Cả hai đều giúp mô tả dữ liệu và quy tắc của miền, nhưng chúng trả lời hai câu hỏi khác nhau:

- Với thực thể, điều quan trọng là **đối tượng nào** đang được nói đến và nó tồn tại qua thời gian như thế nào.
- Với đối tượng giá trị, điều quan trọng là **giá trị nào** đang được biểu diễn; hai đối tượng có cùng giá trị được xem là tương đương.

Đây là hai khái niệm nền tảng trong thiết kế hướng miền (*Domain-Driven Design – DDD*). Phân biệt đúng chúng giúp mô hình thể hiện quy tắc nghiệp vụ rõ ràng, xác định cách so sánh đối tượng, kiểm soát thay đổi trạng thái và lựa chọn cách lưu trữ phù hợp.

## 1. Thực thể là gì?

**Thực thể** là đối tượng trong miền có danh tính riêng (*identity*) và được theo dõi xuyên suốt vòng đời. Trạng thái của thực thể có thể thay đổi, nhưng những thay đổi đó không làm nó trở thành một thực thể khác.

Ví dụ trong hệ thống bán hàng:

- Một khách hàng được nhận diện bằng mã khách hàng. Tên, địa chỉ hoặc số điện thoại có thể thay đổi, nhưng khách hàng vẫn là người đó.
- Một đơn hàng có mã đơn hàng riêng. Trạng thái có thể chuyển từ `Draft` sang `Confirmed`, rồi `Shipped` hoặc `Cancelled`; đó vẫn là cùng một đơn hàng.
- Một tài khoản ngân hàng giữ danh tính qua nhiều lần nạp, rút và thay đổi số dư.

### 1.1. Danh tính của thực thể

Danh tính là đặc điểm quan trọng nhất của thực thể. Trong phần mềm, danh tính thường được biểu diễn bằng một mã định danh ổn định như `CustomerId`, `OrderId` hoặc UUID.

Ví dụ:

```java
public record CustomerId(UUID value) {
    public CustomerId {
        Objects.requireNonNull(value, "value");
    }
}

public final class Customer {
    private final CustomerId id;
    private String name;
    private Address address;

    public Customer(CustomerId id, String name, Address address) {
        this.id = Objects.requireNonNull(id);
        this.name = Objects.requireNonNull(name);
        this.address = Objects.requireNonNull(address);
    }

    public CustomerId id() {
        return id;
    }

    public void changeName(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Name is required");
        }
        this.name = newName;
    }

    public void changeAddress(Address newAddress) {
        this.address = Objects.requireNonNull(newAddress);
    }
}
```

`CustomerId` biểu diễn danh tính của khách hàng. Khi tên hoặc địa chỉ thay đổi, mã định danh vẫn giữ nguyên. Trong một hệ thống thực tế, việc tạo mã có thể do ứng dụng, domain factory hoặc cơ chế cấp mã của hệ thống đảm nhiệm. Nếu cần so sánh thực thể ngay từ khi tạo, nên có danh tính ổn định từ thời điểm đó; nếu mã chỉ được cấp khi lưu vào cơ sở dữ liệu, cần xử lý riêng trạng thái chưa được lưu.

### 1.2. So sánh thực thể

Hai thực thể được xem là cùng một thực thể khi chúng có cùng danh tính theo quy tắc của miền, dù trạng thái hiện tại có thể khác nhau.

Giả sử hai bản thể `Customer` cùng có `CustomerId = C-100`, nhưng một bản thể chứa tên cũ và bản thể còn lại chứa tên mới. Nếu chúng đại diện cho cùng khách hàng, chúng vẫn là cùng một thực thể.

Do đó, phép so sánh thực thể thường dựa trên định danh, không dựa trên toàn bộ thuộc tính. Trong Java, nếu ghi đè `equals()` và `hashCode()` cho một entity, quy tắc phải nhất quán với danh tính của nó. Cũng cần tránh dùng thuộc tính có thể thay đổi làm khóa trong `HashSet` hoặc `HashMap`, vì thay đổi thuộc tính đó có thể làm đối tượng không còn được tìm thấy đúng cách.

### 1.3. Vòng đời và trạng thái

Thực thể thường có vòng đời được miền quy định. Ví dụ, một đơn hàng có thể được tạo, xác nhận, thanh toán, giao hàng hoặc hủy. Không phải mọi chuyển đổi đều hợp lệ: đơn đã giao có thể không được quay lại trạng thái bản nháp.

Các hành vi nên được đặt ở nơi có đủ thông tin để bảo vệ quy tắc của thực thể:

```java
public final class Order {
    private final OrderId id;
    private OrderStatus status;

    public Order(OrderId id) {
        this.id = Objects.requireNonNull(id);
        this.status = OrderStatus.DRAFT;
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only a draft order can be confirmed");
        }
        status = OrderStatus.CONFIRMED;
    }
}
```

Ví dụ này cho thấy thực thể không chỉ là một túi thuộc tính. Nó có thể cung cấp hành vi để bảo đảm trạng thái luôn tuân theo quy tắc nghiệp vụ.

## 2. Đối tượng giá trị là gì?

**Đối tượng giá trị** là đối tượng được xác định bằng các giá trị cấu thành nó, không có danh tính riêng cần theo dõi. Hai đối tượng giá trị có cùng các giá trị theo quy tắc so sánh của miền được xem là tương đương.

Ví dụ:

- `Money(100, VND)` biểu diễn một khoản tiền.
- `Address("12 Nguyễn Huệ", "Quận 1", "TP. Hồ Chí Minh")` biểu diễn một địa chỉ.
- `DateRange(2026-01-01, 2026-01-31)` biểu diễn một khoảng thời gian.
- `Temperature(25, Celsius)` biểu diễn một giá trị nhiệt độ có đơn vị.

Nếu hai đơn hàng cùng có địa chỉ giao hàng giống nhau, mô hình thường không cần tạo hai danh tính riêng cho hai địa chỉ đó. Chúng là hai giá trị tương đương được sử dụng trong ngữ cảnh khác nhau.

### 2.1. Bình đẳng theo giá trị

Đối tượng giá trị được so sánh theo toàn bộ thuộc tính có ý nghĩa trong miền. Ví dụ, hai khoản tiền chỉ tương đương nếu cả số tiền và đơn vị tiền tệ tương đương. `100 USD` không bằng `100 VND`.

Trong Java, `record` thường là lựa chọn phù hợp để biểu diễn value object đơn giản vì Java tự tạo các phương thức `equals()`, `hashCode()` và `toString()` dựa trên các thành phần của record.

```java
public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        // Chuẩn hóa để 10.0 và 10.00 có cùng biểu diễn giá trị.
        amount = amount.stripTrailingZeros();
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency must match");
        }
        return new Money(amount.add(other.amount), currency);
    }
}
```

Ở ví dụ này, `Money` không có mã định danh. Hai đối tượng có cùng `amount` và `currency` sẽ bằng nhau theo `equals()`. Phép cộng trả về một đối tượng mới, nhờ đó không làm thay đổi khoản tiền ban đầu.

Trong ứng dụng tài chính thực tế, quy tắc làm tròn và số chữ số thập phân cần dựa vào đơn vị tiền tệ và chính sách nghiệp vụ. Chuẩn hóa số thập phân trong ví dụ chỉ nhằm minh họa cách làm cho phép so sánh phù hợp với ý nghĩa giá trị.

### 2.2. Tính bất biến

Đối tượng giá trị thường được thiết kế bất biến (*immutable*): sau khi được tạo, các giá trị cấu thành không thay đổi. Nếu cần một giá trị mới, chương trình tạo một đối tượng mới.

Ví dụ về địa chỉ:

```java
public record Address(
    String street,
    String district,
    String city,
    String postalCode
) {
    public Address {
        if (street == null || street.isBlank()) {
            throw new IllegalArgumentException("Street is required");
        }
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("City is required");
        }
    }
}
```

Muốn đổi địa chỉ giao hàng, chương trình tạo `Address` mới rồi gán vào đơn hàng. Nó không sửa từng trường của đối tượng địa chỉ cũ.

Tính bất biến mang lại một số lợi ích:

- Dễ suy luận vì giá trị không thay đổi bất ngờ sau khi được truyền sang thành phần khác.
- Có thể chia sẻ cùng một đối tượng giữa nhiều nơi mà ít lo tác dụng phụ.
- Dễ kiểm thử và dùng làm khóa trong cấu trúc dữ liệu dựa trên `equals()` và `hashCode()`.
- Có thể kiểm tra toàn bộ bất biến ngay khi tạo đối tượng.

Không phải mọi value object đều bắt buộc bất biến theo định nghĩa ở mọi ngôn ngữ và mọi hệ thống. Tuy nhiên, bất biến là lựa chọn thiết kế được ưu tiên vì phù hợp với bản chất của giá trị và làm giảm độ phức tạp khi quản lý trạng thái.

## 3. So sánh thực thể và đối tượng giá trị

| Tiêu chí | Thực thể (Entity) | Đối tượng giá trị (Value Object) |
|---|---|---|
| Điều xác định đối tượng | Danh tính ổn định | Các giá trị cấu thành |
| Phép so sánh | So sánh theo danh tính | So sánh theo giá trị |
| Thay đổi trạng thái | Có thể thay đổi trong vòng đời | Thường bất biến; thay đổi bằng cách tạo giá trị mới |
| Vòng đời | Có vòng đời cần theo dõi | Thường không có vòng đời độc lập cần theo dõi |
| Chia sẻ | Hai tham chiếu có thể cùng trỏ đến một thực thể | Các đối tượng tương đương có thể thay thế nhau theo ngữ nghĩa |
| Ví dụ | Khách hàng, đơn hàng, tài khoản | Tiền, địa chỉ, khoảng thời gian, tọa độ |
| Câu hỏi thiết kế | “Đây có phải cùng một đối tượng qua thời gian?” | “Hai giá trị này có tương đương nhau không?” |

Không nên phân loại chỉ dựa vào việc một đối tượng có nhiều trường hay ít trường, có được lưu trong cơ sở dữ liệu hay không, hoặc tên lớp là danh từ gì. Cần dựa vào ý nghĩa nghiệp vụ và cách hệ thống cần nhận diện đối tượng.

## 4. Một khái niệm có thể là entity hoặc value object tùy ngữ cảnh

Không có danh sách cố định nói rằng một khái niệm luôn luôn là thực thể hoặc luôn luôn là đối tượng giá trị trong mọi hệ thống. Vai trò của nó phụ thuộc vào miền và yêu cầu theo dõi.

### 4.1. Địa chỉ

Trong hệ thống bán hàng, địa chỉ giao hàng thường là value object nằm trong đơn hàng. Nếu khách hàng đổi địa chỉ, đơn hàng cũ có thể vẫn giữ địa chỉ tại thời điểm đặt mua.

Trong hệ thống quản lý địa chỉ bưu chính, một địa chỉ có thể cần danh tính và vòng đời riêng vì nó được xác minh, quản lý lịch sử, gắn với nhiều dịch vụ hoặc có trạng thái hiệu lực. Khi đó, mô hình có thể xem địa chỉ như một entity.

### 4.2. Sản phẩm

Một mặt hàng trong danh mục thường là entity: nó có mã sản phẩm, mô tả, trạng thái kinh doanh và có thể thay đổi giá hoặc thông tin theo thời gian.

Một dòng đơn hàng có thể lưu `ProductId`, tên sản phẩm và giá tại thời điểm mua. `UnitPrice` hoặc bản chụp thông tin sản phẩm trong dòng đơn hàng có thể được biểu diễn bằng value object để bảo toàn giá trị giao dịch, dù sản phẩm trong danh mục tiếp tục thay đổi.

### 4.3. Dòng đơn hàng

`OrderLine` có thể là value object nếu nó chỉ là tập hợp sản phẩm, số lượng và giá, không cần nhận diện riêng hoặc theo dõi độc lập. Nó có thể được thay thế bằng một giá trị mới khi số lượng thay đổi.

Trong một miền khác, dòng đơn hàng có thể có danh tính riêng nếu cần theo dõi việc xử lý, hoàn trả, phân bổ hoặc lịch sử thay đổi của từng dòng. Khi đó, nó có thể được mô hình hóa thành entity bên trong phạm vi đơn hàng.

Những ví dụ này nhấn mạnh rằng mô hình phải phản ánh quy tắc thực tế. Không nên quyết định loại đối tượng chỉ từ tên gọi quen thuộc.

## 5. Quan hệ giữa entity, value object và aggregate

Trong DDD, entity và value object thường được tổ chức trong một **aggregate** (*cụm tổng hợp*). Aggregate là ranh giới nhất quán nghiệp vụ: nó nhóm các đối tượng cần bảo vệ những bất biến liên quan trong cùng một đơn vị thay đổi.

**Aggregate root** là entity gốc mà các đối tượng bên ngoài sử dụng để truy cập và yêu cầu thay đổi aggregate. Nó kiểm soát những thao tác cần thiết để duy trì quy tắc của cụm.

Ví dụ, `Order` có thể là aggregate root, chứa các `OrderLine` và value object `Money`, `ShippingAddress`. Khi thêm một dòng hàng, đơn hàng kiểm tra trạng thái, số lượng và quy tắc liên quan trước khi chấp nhận thay đổi.

```text
Order (Aggregate Root / Entity)
├── OrderId (Value Object)
├── Status (Value Object hoặc kiểu liệt kê)
├── ShippingAddress (Value Object)
├── Total (Money - Value Object)
└── OrderLine (Entity hoặc Value Object tùy miền)
    ├── ProductId (Value Object)
    ├── Quantity (Value Object)
    └── UnitPrice (Money - Value Object)
```

Sơ đồ chỉ minh họa một cách tổ chức có thể có. Việc `OrderLine` là entity hay value object phải dựa vào yêu cầu nhận diện và vòng đời của dòng hàng. Aggregate root cũng không có nghĩa là mọi đối tượng trong hệ thống đều phải được đặt dưới một entity gốc duy nhất.

## 6. Cách nhận diện một đối tượng trong mô hình miền

Khi phân tích một khái niệm nghiệp vụ, có thể lần lượt đặt các câu hỏi sau:

1. **Miền có cần phân biệt từng cá thể không?** Nếu hai đối tượng có cùng thuộc tính nhưng vẫn có thể là hai cá thể khác nhau, đó là dấu hiệu của entity.
2. **Đối tượng có được theo dõi qua các lần thay đổi không?** Nếu cần biết cùng một đối tượng đã thay đổi trạng thái ra sao, entity thường phù hợp.
3. **Hai đối tượng có cùng giá trị có thể thay thế nhau không?** Nếu có, value object thường là lựa chọn tự nhiên.
4. **Có cần tham chiếu đến đối tượng bằng một mã ổn định không?** Nếu danh tính là một phần quan trọng của quy tắc miền, hãy xem xét entity.
5. **Thay đổi một thành phần có tạo ra một giá trị mới không?** Nếu có, biểu diễn bất biến như value object có thể làm mô hình rõ ràng hơn.
6. **Đối tượng có cần tồn tại độc lập ngoài đối tượng chứa nó không?** Nếu không, nó có thể là value object thuộc về entity hoặc aggregate khác.

Ví dụ, với `Money`, hai khoản tiền có cùng số tiền và loại tiền có thể thay thế nhau trong phép tính, nên thường là value object. Với `Customer`, hai khách hàng có cùng tên và địa chỉ vẫn có thể là hai người khác nhau, nên cần danh tính riêng và thường là entity.

## 7. Cách triển khai trong Java

Java cung cấp nhiều cấu trúc để biểu diễn entity và value object. Việc chọn cấu trúc nên phục vụ ngữ nghĩa của miền.

### 7.1. Dùng record cho value object

`record` phù hợp với các đối tượng chủ yếu mang dữ liệu và có phép so sánh theo giá trị. Các thành phần của record là `final`, và Java tự sinh các phương thức cơ bản dựa trên những thành phần đó.

```java
public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }
}
```

`Quantity` vừa đóng gói kiểu số nguyên, vừa bảo vệ quy tắc số lượng phải lớn hơn 0. Thay vì truyền `int` ở mọi nơi và lặp lại kiểm tra, mô hình sử dụng một kiểu miền có ý nghĩa rõ ràng.

### 7.2. Dùng class cho entity

Entity thường cần kiểm soát trạng thái và cung cấp hành vi. Có thể dùng class thông thường với trường định danh bất biến, các trường trạng thái và phương thức nghiệp vụ.

```java
public final class BankAccount {
    private final AccountId id;
    private Money balance;

    public BankAccount(AccountId id, Money openingBalance) {
        this.id = Objects.requireNonNull(id);
        this.balance = Objects.requireNonNull(openingBalance);
    }

    public void deposit(Money amount) {
        this.balance = this.balance.add(amount);
    }

    public AccountId id() {
        return id;
    }

    public Money balance() {
        return balance;
    }
}
```

Trong ví dụ này, `BankAccount` là entity vì tài khoản có danh tính riêng và số dư thay đổi qua các giao dịch. `Money` là value object vì mỗi khoản tiền được xác định bởi số tiền và đơn vị tiền tệ.

Đây là ví dụ tập trung vào phân biệt loại đối tượng. Hệ thống ngân hàng thực tế cần thêm quy tắc như kiểm tra số tiền nạp, giới hạn tài khoản, tiền tệ, ghi sổ giao dịch và xử lý đồng thời.

### 7.3. Dùng kiểu định danh riêng

Thay vì dùng `String` hoặc `UUID` trực tiếp ở mọi nơi, có thể tạo kiểu định danh riêng như `CustomerId`, `OrderId`, `AccountId`. Cách này giúp tránh truyền nhầm mã giữa các loại entity và làm chữ ký phương thức dễ hiểu hơn.

```java
public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value);
    }
}

public Order findOrder(OrderId id) {
    // Tìm đơn hàng theo đúng loại định danh.
    return repository.findById(id);
}
```

Kiểu định danh riêng cũng có thể chứa quy tắc định dạng hoặc kiểm tra hợp lệ nếu miền yêu cầu.

## 8. Lưu trữ và ánh xạ cơ sở dữ liệu

Entity thường được lưu với định danh ổn định để có thể tải lại và nhận diện qua nhiều phiên làm việc. Value object có thể được lưu dưới dạng các cột trong bảng entity chứa nó, một bảng thành phần, kiểu nhúng hoặc cấu trúc JSON tùy công nghệ và nhu cầu truy vấn.

Ví dụ, bảng `orders` có thể chứa các cột địa chỉ giao hàng (`street`, `district`, `city`) cùng dữ liệu đơn hàng. Khi đọc, ứng dụng tạo một `ShippingAddress` bất biến từ các cột đó.

Một số điểm cần lưu ý:

- **Khóa chính không tự quyết định mô hình miền.** Một bảng có khóa chính không nhất thiết có nghĩa đối tượng nghiệp vụ tương ứng là entity; khóa có thể chỉ phục vụ lưu trữ.
- **Không phải mọi value object đều cần bảng riêng.** Cách lưu phụ thuộc vào cách truy vấn, vòng đời và yêu cầu nhất quán.
- **Không nên để ORM quyết định ngữ nghĩa miền.** Annotation hoặc cấu hình ORM là chi tiết ánh xạ; entity/value object cần được xác định từ quy tắc nghiệp vụ.
- **Giữ quy tắc bình đẳng nhất quán.** Cách ORM tạo proxy, tải lười hoặc khôi phục đối tượng có thể ảnh hưởng đến `equals()` và `hashCode()`, nên cần thiết kế theo framework đang dùng.
- **Lịch sử cần được mô hình hóa có chủ đích.** Nếu đơn hàng phải giữ giá và địa chỉ tại thời điểm mua, hãy lưu các giá trị đó trong đơn hàng thay vì luôn tham chiếu đến dữ liệu hiện tại của khách hàng hoặc sản phẩm.

## 9. Những sai lầm thường gặp

### 9.1. Xem mọi lớp dữ liệu là entity

Nếu mọi lớp đều có ID và được so sánh bằng ID, mô hình có thể tạo ra nhiều danh tính không mang ý nghĩa nghiệp vụ. Những khái niệm như tiền, địa chỉ, khoảng ngày hoặc tọa độ thường dễ hiểu hơn khi là value object.

### 9.2. Xem entity là một túi dữ liệu

Một entity chỉ có getter và setter có thể khiến quy tắc nghiệp vụ bị phân tán ở service hoặc controller. Khi phù hợp, hãy đưa hành vi và điều kiện chuyển trạng thái vào entity hoặc aggregate để bảo vệ bất biến.

### 9.3. Dùng primitive thay cho kiểu miền

Sử dụng `int`, `String` hoặc `BigDecimal` ở mọi nơi có thể khiến chương trình khó phân biệt `CustomerId` với `OrderId`, hoặc số tiền với số lượng. Value object giúp đặt tên và kiểm tra quy tắc tại một nơi.

### 9.4. Cho value object có thể thay đổi tùy tiện

Nếu một `Address` được chia sẻ giữa nhiều entity rồi bị sửa trực tiếp, nhiều đối tượng có thể thay đổi ngoài ý muốn. Dùng value object bất biến và thay thế bằng giá trị mới thường giúp tránh vấn đề này.

### 9.5. So sánh entity bằng toàn bộ thuộc tính

Nếu `equals()` của entity dựa trên tên, địa chỉ hoặc trạng thái, một thay đổi nghiệp vụ có thể làm cùng một entity bị xem là đối tượng khác. So sánh entity cần dựa trên danh tính ổn định theo quy tắc miền.

### 9.6. Đồng nhất DTO với value object

DTO (*Data Transfer Object*) được thiết kế để chuyển dữ liệu giữa các tầng hoặc qua biên hệ thống. Value object là khái niệm trong mô hình miền và mang ý nghĩa nghiệp vụ. Một DTO có thể bất biến và có `equals()` theo giá trị, nhưng điều đó không tự động biến nó thành value object.

## 10. Ví dụ tổng hợp: đơn hàng bán hàng

Một mô hình đơn hàng có thể sử dụng cả entity và value object:

| Khái niệm | Loại thường gặp | Lý do |
|---|---|---|
| `Customer` | Entity | Khách hàng có danh tính riêng; tên và địa chỉ có thể thay đổi |
| `Order` | Entity / Aggregate Root | Đơn hàng có mã riêng và vòng đời trạng thái |
| `OrderId` | Value Object | Giá trị định danh có kiểu rõ ràng, được so sánh theo nội dung |
| `Money` | Value Object | Được xác định bởi số tiền và loại tiền |
| `ShippingAddress` | Value Object | Biểu diễn địa chỉ tại thời điểm giao hàng |
| `Quantity` | Value Object | Đóng gói số lượng và quy tắc hợp lệ |
| `OrderLine` | Tùy miền | Là value object nếu không cần danh tính riêng; là entity nếu cần theo dõi độc lập |

Khi khách hàng đặt hàng, hệ thống có thể tạo `Order` với `OrderId` mới, sao chép địa chỉ giao hàng hiện tại thành `ShippingAddress`, và tạo các dòng hàng chứa `ProductId`, `Quantity`, `UnitPrice`. Sau khi đơn được xác nhận, trạng thái và các giá trị giao dịch cần được bảo toàn theo quy tắc miền. Nếu khách hàng đổi địa chỉ hoặc giá sản phẩm trong danh mục thay đổi, đơn hàng cũ vẫn giữ dữ liệu giao dịch tại thời điểm đặt mua.

Mô hình này làm rõ ranh giới giữa danh tính và giá trị: khách hàng và đơn hàng được theo dõi qua thời gian; tiền, địa chỉ và số lượng được so sánh theo giá trị và có thể thay thế bằng một giá trị mới khi cần.

## 11. Ghi nhớ

- Entity có danh tính riêng và được theo dõi qua vòng đời; trạng thái có thể thay đổi mà danh tính vẫn giữ nguyên.
- Value object được xác định bởi các thuộc tính có ý nghĩa; hai đối tượng có cùng giá trị được xem là tương đương.
- Entity thường dùng định danh ổn định để so sánh; value object thường dùng so sánh theo giá trị và nên được thiết kế bất biến.
- Một khái niệm có thể là entity hoặc value object tùy quy tắc và ngữ cảnh của miền.
- Aggregate root bảo vệ các bất biến trong aggregate; entity và value object có thể cùng tồn tại bên trong aggregate.
- Cách ánh xạ cơ sở dữ liệu không quyết định bản chất entity hay value object. Hãy bắt đầu từ ý nghĩa nghiệp vụ.

## 12. Câu hỏi tự kiểm tra

1. Vì sao tên hoặc địa chỉ của khách hàng thay đổi mà khách hàng vẫn là cùng một entity?
2. Hai đối tượng `Money` có cùng số tiền nhưng khác loại tiền có bằng nhau không? Giải thích.
3. Tại sao value object thường được thiết kế bất biến?
4. Nêu một trường hợp `Address` là value object và một trường hợp địa chỉ có thể được mô hình hóa như entity.
5. `OrderLine` nên là entity hay value object? Những yêu cầu nào quyết định lựa chọn đó?
6. Khóa chính trong bảng cơ sở dữ liệu có đủ để kết luận một khái niệm là entity trong mô hình miền không?
7. Phân biệt DTO và value object.
8. Trong một aggregate `Order`, vì sao các thay đổi đối với dòng hàng nên đi qua aggregate root khi chúng ảnh hưởng đến bất biến của đơn hàng?
