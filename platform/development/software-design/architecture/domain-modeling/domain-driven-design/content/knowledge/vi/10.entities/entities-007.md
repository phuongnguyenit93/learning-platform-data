# Phân biệt hai thực thể có cùng thuộc tính nhưng khác danh tính

Trong Domain-Driven Design (DDD), **entity (thực thể)** là một đối tượng nghiệp vụ được nhận diện và theo dõi xuyên suốt vòng đời bằng danh tính của nó. Các thuộc tính của entity có thể thay đổi, nhưng entity vẫn là đối tượng đó nếu danh tính không đổi và nghiệp vụ không xác định rằng nó đã kết thúc hoặc được thay thế.

Điều này dẫn đến một điểm dễ nhầm: hai entity có thể có cùng toàn bộ giá trị thuộc tính tại một thời điểm nhưng vẫn là hai entity khác nhau. Hai khách hàng có cùng tên và địa chỉ không nhất thiết là một khách hàng. Hai đơn hàng có cùng người mua, mặt hàng, số lượng và tổng tiền vẫn có thể là hai lần đặt hàng riêng. Ngược lại, một khách hàng đổi địa chỉ hoặc số điện thoại vẫn có thể là cùng một khách hàng.

Vì vậy, khi mô hình hóa entity, nhóm cần phân biệt **danh tính (identity)** với **giá trị thuộc tính (attribute values)**. Danh tính trả lời “đây là đối tượng nào?”, còn thuộc tính mô tả “đối tượng này hiện có những đặc điểm gì?”. Bài học này giải thích cách nhận diện danh tính, phân biệt entity với value object, xử lý trường hợp trùng thuộc tính và thể hiện ngữ nghĩa đó trong mã nguồn.

## 1. Danh tính và thuộc tính là hai khái niệm khác nhau

Một entity thường có nhiều thuộc tính như tên, trạng thái, địa chỉ, ngày tạo hoặc số tiền. Những thuộc tính này giúp mô tả entity, nhưng không phải thuộc tính nào cũng xác định entity đó là ai.

Ví dụ, một khách hàng có thể được mô tả bằng:

- Mã khách hàng.
- Tên hiển thị.
- Ngày sinh hoặc ngày thành lập.
- Địa chỉ liên hệ.
- Số điện thoại và email.
- Trạng thái quan hệ với doanh nghiệp.

Trong đó, tên, địa chỉ, số điện thoại và email có thể thay đổi. Mã khách hàng thường được dùng để nhận diện bản ghi khách hàng xuyên suốt vòng đời. Nếu khách hàng chuyển nhà, việc cập nhật địa chỉ không tạo ra một khách hàng hoàn toàn mới.

Hãy phân biệt hai câu hỏi:

- **Danh tính:** Đối tượng này là ai hoặc là đối tượng nào trong mô hình?
- **Thuộc tính:** Đối tượng đó đang có những giá trị và trạng thái nào?

Nếu dùng toàn bộ thuộc tính làm căn cứ xác định entity, bất kỳ thay đổi nào cũng có thể khiến hệ thống xem entity cũ biến mất và entity mới xuất hiện. Điều đó làm mất tính liên tục của lịch sử, quan hệ và các giao dịch đã phát sinh.

## 2. Hai entity cùng thuộc tính vẫn có thể khác nhau

Giả sử một cửa hàng có hai khách hàng cùng tên “Nguyễn An”, cùng ngày sinh và cùng địa chỉ. Hai người có thể là hai cá nhân khác nhau. Nếu hệ thống dùng tổ hợp tên, ngày sinh và địa chỉ làm danh tính, nó có thể gộp nhầm hồ sơ của họ.

Tương tự, một khách hàng có thể đặt cùng một giỏ hàng hai lần. Hai đơn hàng có thể có:

| Thuộc tính | Đơn hàng A | Đơn hàng B |
| --- | --- | --- |
| Khách hàng | CUST-100 | CUST-100 |
| Sản phẩm | SKU-01 | SKU-01 |
| Số lượng | 2 | 2 |
| Đơn giá | 150.000 VND | 150.000 VND |
| Tổng tiền | 300.000 VND | 300.000 VND |
| Danh tính đơn hàng | ORD-501 | ORD-502 |

Các thuộc tính nghiệp vụ được liệt kê giống nhau, nhưng hai lần đặt hàng là hai giao dịch độc lập. Chúng có thể được thanh toán, hủy, giao hoặc hoàn tiền theo những diễn biến khác nhau. Gộp chúng thành một entity sẽ làm mất thông tin về hai lần mua riêng biệt.

Về mặt khái niệm, ta có:

```text
Customer
  id = CUST-100
  name = "Nguyễn An"
  address = "12 Lê Lợi"

Order A
  id = ORD-501
  customerId = CUST-100
  lines = [(SKU-01, 2)]
  total = 300000 VND

Order B
  id = ORD-502
  customerId = CUST-100
  lines = [(SKU-01, 2)]
  total = 300000 VND
```

Hai đơn hàng có cùng dữ liệu mô tả nhưng có định danh khác nhau. Đây là hai entity khác nhau vì nghiệp vụ theo dõi chúng như hai giao dịch độc lập.

## 3. Một entity thay đổi thuộc tính nhưng vẫn giữ danh tính

Danh tính giúp duy trì sự liên tục của một đối tượng qua các thay đổi. Ví dụ, khách hàng `CUST-100` chuyển từ địa chỉ cũ sang địa chỉ mới:

```text
Trước khi cập nhật
  id = CUST-100
  name = "Nguyễn An"
  address = "12 Lê Lợi"

Sau khi cập nhật
  id = CUST-100
  name = "Nguyễn An"
  address = "45 Nguyễn Huệ"
```

Đây vẫn là cùng một entity vì `CustomerId` không đổi. Hệ thống có thể ghi lịch sử thay đổi địa chỉ, nhưng không cần tạo một khách hàng mới chỉ vì thuộc tính đã thay đổi.

Điều này đặc biệt quan trọng với các khái niệm có lịch sử và quan hệ lâu dài:

- Khách hàng có các đơn hàng, hợp đồng và lịch sử chăm sóc.
- Hợp đồng có các lần điều chỉnh, gia hạn và trạng thái hiệu lực.
- Tài khoản có các giao dịch và số dư thay đổi.
- Nhân viên có thay đổi chức danh, phòng ban hoặc thông tin liên hệ.

Nếu danh tính bị gắn với thuộc tính dễ thay đổi, những quan hệ này sẽ trở nên khó duy trì. Hệ thống có thể mất khả năng truy vết lịch sử hoặc tạo ra nhiều bản ghi tưởng như cùng một đối tượng.

## 4. Phân biệt entity với value object

Entity và value object đều là những thành phần quan trọng của domain model, nhưng cách xác định sự đồng nhất của chúng khác nhau.

**Entity** được nhận diện bằng danh tính. Hai instance có cùng giá trị thuộc tính vẫn có thể là hai entity khác nhau nếu ID khác nhau. Một entity có thể thay đổi thuộc tính mà vẫn là chính nó.

**Value object** được xác định bằng giá trị của các thuộc tính. Hai value object có cùng các giá trị liên quan được xem là tương đương theo giá trị, không cần một ID riêng để phân biệt.

Ví dụ:

| Tiêu chí | Entity | Value object |
| --- | --- | --- |
| Cách xác định | Danh tính ổn định | Giá trị của các thuộc tính |
| Hai instance cùng thuộc tính | Có thể là hai đối tượng khác nhau | Thường được xem là bằng nhau |
| Thay đổi thuộc tính | Có thể vẫn là cùng entity | Thường tạo ra một value object có giá trị mới |
| Vòng đời | Có danh tính và lịch sử riêng | Thường được thay thế khi giá trị thay đổi |
| Ví dụ | Customer, Order, Contract | Money, Address, DateRange |

Ví dụ, hai `Money` có giá trị 100.000 VND thường tương đương nhau theo giá trị. Nhưng hai `Order` có tổng tiền 100.000 VND không vì vậy mà là cùng một đơn hàng.

```java
Money first = new Money(new BigDecimal("100000"), Currency.getInstance("VND"));
Money second = new Money(new BigDecimal("100000"), Currency.getInstance("VND"));

// Hai giá trị tiền tương đương theo value semantics.

Order orderA = new Order(new OrderId("ORD-501"));
Order orderB = new Order(new OrderId("ORD-502"));

// Hai đơn hàng khác nhau dù các thuộc tính khác có thể giống nhau.
```

Một khái niệm ngoài đời không tự động là entity hay value object. Cách mô hình hóa phụ thuộc vào mục tiêu của bounded context. Ví dụ, địa chỉ có thể là value object trong một context giao hàng, nhưng một hồ sơ địa điểm có danh tính và lịch sử riêng trong context quản lý cơ sở vật chất.

## 5. Danh tính trong phạm vi bounded context

Trong DDD, danh tính của entity được hiểu trong phạm vi mô hình mà entity thuộc về. Cùng một người ngoài đời có thể được đại diện bởi các entity khác nhau trong các bounded context khác nhau.

Ví dụ:

- Context bán hàng có `Buyer` với ID dùng để quản lý quan hệ mua bán.
- Context thanh toán có `PayerAccount` với ID dùng để quản lý nghĩa vụ thanh toán.
- Context giao hàng có `Recipient` với thông tin và định danh phục vụ giao nhận.

Các entity có thể liên kết thông qua mã tham chiếu hoặc một cơ chế định danh chung, nhưng không nhất thiết là cùng một entity. Một `Buyer` có thể đặt đơn cho người khác nhận; một pháp nhân có thể thanh toán thay cho nhiều người mua.

Vì vậy, không nên giả định rằng một ID trong context này có thể được dùng như danh tính trong context khác mà không có hợp đồng và quy tắc ánh xạ rõ ràng. Cần xác định:

- ID thuộc loại entity nào và bounded context nào sở hữu nó.
- Phạm vi duy nhất của ID: toàn hệ thống, một tenant, một context hay một loại đối tượng.
- Context khác được phép tham chiếu ID đó theo cách nào.
- Điều gì xảy ra khi hai hệ thống dùng mã khác nhau cho cùng một đối tượng ngoài đời.
- Cách xử lý khi danh tính được hợp nhất, tách hoặc đánh dấu trùng.

## 6. Các loại định danh thường gặp

Danh tính có thể được biểu diễn bằng nhiều cách. Không có một lựa chọn duy nhất phù hợp mọi miền.

### 6.1. Định danh kỹ thuật

Định danh kỹ thuật thường được hệ thống tạo ra để phân biệt entity, chẳng hạn UUID, số tăng tự động hoặc một chuỗi ngẫu nhiên. Nó có thể không mang ý nghĩa nghiệp vụ.

Ưu điểm là ít phụ thuộc vào thuộc tính nghiệp vụ và có thể giữ ổn định khi tên, địa chỉ hoặc trạng thái thay đổi. Tuy nhiên, cần xác định phạm vi duy nhất và cách tạo ID để tránh va chạm hoặc phụ thuộc không cần thiết vào database.

### 6.2. Định danh nghiệp vụ

Một số miền có mã định danh do nghiệp vụ quản lý, chẳng hạn số hợp đồng, mã hồ sơ hoặc số đăng ký. Mã này có thể được dùng làm identity nếu nó thực sự ổn định và có quy tắc duy nhất phù hợp với bounded context.

Không phải mọi mã nghiệp vụ đều là identity tốt. Một mã có thể được tái sử dụng, thay đổi khi chuyển hệ thống hoặc chỉ duy nhất trong một năm tài chính. Nhóm cần kiểm tra quy tắc cấp mã và vòng đời trước khi dùng nó làm danh tính.

### 6.3. Định danh tổng hợp

Trong một số mô hình, danh tính được xác định bởi nhiều thành phần, ví dụ `(tenantId, accountNumber)` hoặc `(warehouseId, binCode)`. Khi đó, tổ hợp này phải có quy tắc ổn định và duy nhất trong phạm vi đã xác định.

Nếu một thành phần của khóa có thể thay đổi, cần cân nhắc dùng ID ổn định riêng và lưu khóa nghiệp vụ như thuộc tính hoặc alternate key.

### 6.4. Không đồng nhất ID với thuộc tính duy nhất

Một thuộc tính có thể được yêu cầu duy nhất tại một thời điểm, chẳng hạn email đăng nhập hoặc số đăng ký doanh nghiệp. Nhưng điều đó không tự động biến nó thành danh tính lâu dài. Email có thể đổi chủ, được cập nhật hoặc không còn sử dụng. Một quy tắc duy nhất giúp ngăn dữ liệu trùng trong một phạm vi, còn identity giúp theo dõi cùng entity qua thời gian.

Nhóm cần phân biệt **unique constraint** với **entity identity**. Unique constraint là quy tắc về dữ liệu; identity là cách mô hình nhận diện và theo dõi đối tượng.

## 7. Cách thể hiện identity trong mã Java

Trong mã nguồn, nên biểu diễn ID bằng một kiểu riêng để tránh nhầm lẫn giữa các loại định danh có cùng kiểu nền như `String` hoặc `UUID`.

### 7.1. Tạo kiểu ID riêng

```java
public record CustomerId(UUID value) {
    public CustomerId {
        Objects.requireNonNull(value, "value");
    }

    public static CustomerId generate() {
        return new CustomerId(UUID.randomUUID());
    }
}
```

`CustomerId` là value object biểu diễn định danh của entity Customer. Nó có thể được so sánh theo giá trị ID, trong khi Customer được so sánh theo danh tính đó.

### 7.2. Entity so sánh theo identity

```java
public final class Customer {
    private final CustomerId id;
    private String name;
    private String address;

    public Customer(CustomerId id, String name, String address) {
        this.id = Objects.requireNonNull(id);
        this.name = Objects.requireNonNull(name);
        this.address = Objects.requireNonNull(address);
    }

    public CustomerId id() {
        return id;
    }

    public void changeAddress(String newAddress) {
        this.address = Objects.requireNonNull(newAddress);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (other == null || getClass() != other.getClass()) return false;
        Customer customer = (Customer) other;
        return id.equals(customer.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
```

Hai object `Customer` có cùng `CustomerId` được xem là cùng entity trong mô hình này, dù chúng là hai instance Java khác nhau. Nếu ID khác nhau, chúng là hai entity khác nhau dù tên và địa chỉ giống hệt nhau.

```java
CustomerId idA = CustomerId.generate();
CustomerId idB = CustomerId.generate();

Customer customerA = new Customer(idA, "Nguyễn An", "12 Lê Lợi");
Customer customerB = new Customer(idB, "Nguyễn An", "12 Lê Lợi");

boolean sameEntity = customerA.equals(customerB); // false

Customer reloadedCustomer = new Customer(
        idA,
        "Nguyễn An",
        "12 Lê Lợi"
);

boolean sameIdentity = customerA.equals(reloadedCustomer); // true
```

Ví dụ trên giả định ID được cấp ổn định ngay khi tạo entity. Cách triển khai `equals` và `hashCode` cần được điều chỉnh nếu dự án dùng ORM tạo ID sau khi persist, proxy hoặc kế thừa entity. Không nên dùng một implementation máy móc mà chưa kiểm tra vòng đời ID và cách framework quản lý instance.

### 7.3. Không dùng mọi thuộc tính trong equals/hashCode của entity

Một lỗi phổ biến là dùng tất cả trường của entity để tạo `equals` và `hashCode`:

```java
// Không phù hợp cho entity có danh tính riêng
return Objects.equals(name, other.name)
        && Objects.equals(address, other.address);
```

Nếu khách hàng đổi địa chỉ, kết quả so sánh có thể thay đổi dù danh tính không đổi. Nếu hai khách hàng khác nhau có cùng tên và địa chỉ, chúng có thể bị xem là một. Với entity, equality cần phản ánh identity theo quy tắc của mô hình.

## 8. Danh tính trong persistence và ORM

Khi entity được lưu trong database, primary key thường được dùng để nhận diện bản ghi. Tuy nhiên, primary key ở tầng persistence và identity trong domain model là hai khái niệm có liên quan nhưng không nên đồng nhất một cách máy móc.

Một hệ thống có thể dùng UUID làm domain identity và ánh xạ nó vào cột primary key. Hệ thống khác có thể dùng mã nghiệp vụ ổn định làm khóa chính. Điều quan trọng là identity của entity không thay đổi bất ngờ trong vòng đời.

### 8.1. Tải lại entity không tạo ra danh tính mới

Khi repository tải một khách hàng từ database, nó có thể tạo một instance Java mới. Instance này khác về tham chiếu bộ nhớ so với object đã tải trước đó, nhưng nếu có cùng `CustomerId`, chúng đại diện cho cùng một entity trong domain.

```java
Customer firstLoad = repository.findById(customerId).orElseThrow();
Customer secondLoad = repository.findById(customerId).orElseThrow();

// firstLoad == secondLoad có thể là false.
// Nhưng chúng đại diện cùng entity nếu identity bằng nhau.
// firstLoad.equals(secondLoad) nên phản ánh quy tắc identity của domain.
```

Trong một persistence context của ORM, identity map có thể bảo đảm cùng một bản ghi chỉ được đại diện bởi một instance được quản lý trong phạm vi context đó. Nhưng không nên dựa vào tham chiếu object để định nghĩa danh tính nghiệp vụ xuyên request, transaction hoặc process.

### 8.2. ID sinh trước hay sau khi lưu?

Nếu ID được database tạo sau khi insert, entity có thể tồn tại một khoảng thời gian với ID chưa được gán. Khi đó, cách viết `equals` và `hashCode` dựa trên ID cần được thiết kế cẩn thận, đặc biệt nếu entity được đưa vào `HashSet` hoặc dùng làm key trong `HashMap` trước khi persist.

Một lựa chọn là tạo ID ổn định ở thời điểm khởi tạo entity, ví dụ UUID. Lựa chọn khác là dùng cơ chế equality phù hợp với ORM và quy tắc của dự án. Không nên để `hashCode` thay đổi sau khi object đã được đưa vào collection dựa trên hash.

### 8.3. Không để khóa database quyết định ý nghĩa nghiệp vụ

ID tự tăng có thể là lựa chọn kỹ thuật hợp lý, nhưng không nên được coi là mã có ý nghĩa cho người dùng hoặc hệ thống khác nếu không có hợp đồng. Khi cần công bố định danh, hãy xác định rõ đó là domain ID, business key hay database key.

## 9. Trùng dữ liệu không đồng nghĩa trùng entity

Hai entity có cùng thuộc tính có thể là hai đối tượng riêng biệt. Nhưng đôi khi dữ liệu trùng lại là dấu hiệu một đối tượng ngoài đời đã được tạo thành nhiều entity do lỗi nhập liệu hoặc đồng bộ. Hai trường hợp này cần được phân biệt.

Ví dụ, hệ thống CRM có hai hồ sơ cùng tên, số điện thoại và email. Có thể đó là:

- Hai người khác nhau dùng chung số điện thoại hoặc email gia đình.
- Một người có hai hồ sơ do nhân viên tạo trùng.
- Dữ liệu được nhập từ hai nguồn với mã định danh khác nhau.
- Một khách hàng cá nhân và một hồ sơ đại diện doanh nghiệp bị gộp nhầm.

Chỉ nhìn vào các thuộc tính giống nhau không đủ để quyết định hợp nhất. Nhóm cần xem nguồn dữ liệu, lịch sử giao dịch, bằng chứng định danh và chính sách nghiệp vụ.

### 9.1. Equality khác với duplicate detection

**Entity equality** trả lời liệu hai instance có đại diện cho cùng một entity theo identity hay không. **Duplicate detection** tìm các bản ghi có khả năng mô tả cùng một đối tượng ngoài đời. Đây là hai bài toán khác nhau.

Duplicate detection có thể dùng các thuộc tính như tên, email, số điện thoại, địa chỉ, mã số thuế hoặc thuật toán matching. Kết quả thường là một ứng viên trùng cần được xác minh, không phải bằng chứng chắc chắn rằng hai entity có cùng identity.

### 9.2. Hợp nhất entity là một quyết định nghiệp vụ

Nếu tổ chức xác nhận hai hồ sơ là cùng một khách hàng, việc hợp nhất cần xử lý các quan hệ và lịch sử liên quan. Nhóm cần quyết định:

- Entity nào được giữ làm danh tính chính?
- ID cũ có được giữ như alias hoặc redirect không?
- Đơn hàng, hợp đồng, hóa đơn và yêu cầu hỗ trợ được liên kết lại thế nào?
- Dữ liệu mâu thuẫn được giải quyết theo nguồn nào?
- Có cần lưu audit trail về quyết định hợp nhất không?
- Các hệ thống tích hợp được thông báo và cập nhật tham chiếu ra sao?

Không nên chỉ xóa một bản ghi rồi ghi đè thuộc tính của bản còn lại. Hợp nhất có thể ảnh hưởng đến lịch sử, pháp lý, kế toán và khả năng truy vết.

### 9.3. Một entity có thể có nhiều mã bên ngoài

Khi tích hợp nhiều hệ thống, cùng một entity nội bộ có thể được tham chiếu bằng nhiều external ID. Nên lưu ánh xạ rõ ràng thay vì giả định mọi hệ thống dùng chung một mã.

```text
Internal Customer: CUST-100
  CRM reference: CRM-8831
  ERP reference: AR-2207
  Support reference: CS-1940
```

Các mã bên ngoài là định danh trong phạm vi hệ thống tương ứng. Chúng giúp liên kết và đối soát, nhưng không nhất thiết thay thế `CustomerId` của context nội bộ.

## 10. Quy trình xác định danh tính khi mô hình hóa

Khi phân tích một khái niệm nghiệp vụ, nhóm có thể dùng các bước sau để quyết định nó có phải entity và identity nên được xác định thế nào.

### Bước 1: Xác định đối tượng được theo dõi

Hỏi nghiệp vụ có cần theo dõi đối tượng này qua nhiều thời điểm hay không. Nó có lịch sử, trạng thái, quan hệ hoặc giao dịch riêng không? Nếu chỉ cần biểu diễn một giá trị tại thời điểm sử dụng, nó có thể phù hợp với value object hơn.

### Bước 2: Tìm tiêu chí nhận diện

Hỏi điều gì khiến đối tượng này vẫn là chính nó sau khi thuộc tính thay đổi. Có mã hồ sơ, số hợp đồng, ID nội bộ hoặc một quy tắc định danh ổn định nào không?

### Bước 3: Kiểm tra trường hợp cùng thuộc tính

Đưa ra hai đối tượng có cùng tên, ngày tạo, số tiền hoặc nội dung. Nghiệp vụ có xem chúng là cùng một đối tượng không? Nếu không, cần một identity riêng để phân biệt.

### Bước 4: Kiểm tra trường hợp thuộc tính thay đổi

Hỏi nếu địa chỉ, tên, trạng thái hoặc giá trị khác thay đổi thì entity có trở thành đối tượng mới không. Nếu không, những thuộc tính đó không nên là identity.

### Bước 5: Xác định phạm vi và vòng đời của ID

Làm rõ ID duy nhất trong phạm vi nào, ai tạo, có thể thay đổi hay tái sử dụng không, và điều gì xảy ra khi entity bị hủy, lưu trữ hoặc hợp nhất.

### Bước 6: Phân biệt danh tính với khóa nghiệp vụ

Xác định mã nào dùng để nhận diện entity và mã nào chỉ là thuộc tính hoặc alternate key. Một mã có thể vừa là business identifier vừa là identity nếu nó ổn định và có quy tắc phù hợp.

### Bước 7: Kiểm chứng trong bounded context

Xác nhận danh tính với chuyên gia nghiệp vụ và kiểm tra cách context khác tham chiếu entity. Không giả định identity toàn cục nếu tổ chức chưa có quy tắc định danh chung.

## 11. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| So sánh entity bằng toàn bộ thuộc tính | Hai entity riêng có thể bị gộp; thay đổi thuộc tính làm thay đổi equality | So sánh theo identity ổn định |
| Dùng tên hoặc email làm identity mà không kiểm tra vòng đời | Thay đổi hoặc tái sử dụng giá trị làm mất liên tục | Chọn ID ổn định; giữ email như thuộc tính hoặc alternate key khi phù hợp |
| Cho rằng hai bản ghi giống nhau chắc chắn là trùng | Có thể gộp nhầm hai đối tượng thật sự khác nhau | Dùng duplicate detection và xác minh nghiệp vụ riêng |
| Cho rằng ID khác nhau luôn chứng minh hai đối tượng ngoài đời khác nhau | Không phát hiện hồ sơ bị tạo trùng | Có quy trình matching và hợp nhất có kiểm soát |
| Dùng database primary key làm mã nghiệp vụ công khai | Tạo phụ thuộc không cần thiết vào persistence | Phân biệt database key, domain ID và business key |
| Tạo ID sau persist nhưng hashCode đã dùng trong collection | Object có thể không được tìm thấy trong hash collection | Chọn chiến lược ID/equality ổn định trước khi đưa vào collection |
| Dùng cùng một ID cho các loại entity khác nhau | Có thể nhầm CustomerId với OrderId hoặc ID thuộc context khác | Tạo kiểu ID riêng và xác định phạm vi |
| Hợp nhất entity bằng cách xóa bản ghi | Mất lịch sử và quan hệ tham chiếu | Lập chính sách merge, giữ alias và audit trail khi cần |

## 12. Nguyên tắc thực hành

Khi thiết kế entity, nhóm nên ghi nhớ:

- **Danh tính không phải toàn bộ thuộc tính.** Thuộc tính mô tả entity; identity giúp theo dõi entity qua thời gian.
- **Cùng thuộc tính không đồng nghĩa cùng entity.** Hai đối tượng có dữ liệu giống nhau vẫn có thể có danh tính khác nhau.
- **Thuộc tính thay đổi không nhất thiết tạo entity mới.** Nếu identity và vòng đời không đổi, entity vẫn là chính nó.
- **Entity equality dựa trên identity.** Không dùng tất cả trường mutable để so sánh entity.
- **Value object được so sánh theo giá trị.** Không gán identity riêng nếu khái niệm chỉ cần ngữ nghĩa giá trị.
- **Identity có phạm vi.** Xác định bounded context, loại entity và phạm vi duy nhất của ID.
- **Phân biệt duplicate detection với equality.** Matching dữ liệu là một bài toán riêng và cần xác minh trước khi hợp nhất.
- **Quản lý ID ổn định.** Cân nhắc thời điểm tạo ID, ORM, `equals`, `hashCode` và việc sử dụng trong collection.
- **Giữ lịch sử khi hợp nhất.** Hợp nhất entity cần bảo vệ quan hệ, giao dịch và khả năng truy vết.
- **Dùng kiểu ID riêng.** Tránh nhầm các định danh khác loại chỉ vì cùng biểu diễn bằng `String` hoặc `UUID`.

Một entity không được xác định bởi việc các thuộc tính của nó trông giống đối tượng khác đến mức nào. Nó được xác định bởi danh tính mà mô hình dùng để theo dõi và các quy tắc nghiệp vụ gắn với vòng đời đó. Khi phân biệt rõ identity với attribute values, nhóm có thể giữ lịch sử chính xác, tránh gộp nhầm đối tượng, thiết kế equality phù hợp và duy trì ngữ nghĩa của domain model.

## 13. Câu hỏi tự kiểm tra

1. Vì sao hai entity có cùng toàn bộ thuộc tính vẫn có thể là hai đối tượng khác nhau?
2. Một khách hàng đổi địa chỉ nhưng giữ nguyên CustomerId có phải entity mới không? Giải thích.
3. Phân biệt entity equality với value equality bằng ví dụ Order và Money.
4. Vì sao cùng một người ngoài đời có thể được biểu diễn bởi các entity khác nhau trong hai bounded context?
5. Phân biệt domain identity, business key và database primary key.
6. Một email duy nhất có nên luôn được dùng làm identity của Customer không? Những rủi ro nào cần xem xét?
7. Vì sao duplicate detection không thể chỉ dựa vào `equals` của entity?
8. Khi hợp nhất hai hồ sơ khách hàng, những quan hệ và lịch sử nào cần được bảo vệ?
9. Vì sao ID sinh sau khi persist có thể gây vấn đề với `hashCode` và hash-based collection?
10. Hãy thiết kế một entity có hai instance cùng thuộc tính nhưng khác identity, sau đó mô tả cách hệ thống phân biệt chúng qua repository và kiểm thử.
