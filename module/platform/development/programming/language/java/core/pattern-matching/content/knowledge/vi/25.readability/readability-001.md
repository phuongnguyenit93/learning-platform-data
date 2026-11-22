# Đặt tên pattern variable theo domain trong Java Pattern Matching

## 1. Vì sao tên biến trong pattern quan trọng?

Pattern matching giúp Java kiểm tra kiểu đối tượng và lấy các thành phần ngay trong điều kiện. Nhưng cú pháp ngắn **không tự làm cho code dễ đọc**: người đọc vẫn phải biết mỗi biến biểu thị khái niệm nghiệp vụ nào, đến từ đâu, và được dùng vào việc gì.

Xét một đối tượng đại diện cho sự kiện cập nhật vận chuyển:

```java
record Address(String city, String countryCode) {}
record ShippingUpdated(String orderId, Address shippingAddress) {}
```

Cùng một phép phân rã có thể được viết theo hai cách:

```java
// Tên quá chung: người đọc phải tra ngược cấu trúc record.
if (candidate instanceof ShippingUpdated(var x, Address(var a, var b))) {
    System.out.println(x + " -> " + a + "/" + b);
}
```

```java
// Tên phản ánh vai trò nghiệp vụ của từng giá trị.
if (candidate instanceof ShippingUpdated(
        var orderId,
        Address(var shippingCity, var shippingCountryCode))) {
    System.out.println(orderId + " -> "
            + shippingCity + "/" + shippingCountryCode);
}
```

Hai đoạn có **cùng cơ chế so khớp** và có thể tạo đầu ra như nhau. Tuy nhiên, bản thứ hai cho thấy rõ: `orderId` là định danh đơn hàng, `shippingCity` là thành phố giao hàng và `shippingCountryCode` là mã quốc gia của địa chỉ giao hàng.

**Đặt tên pattern variable theo domain** nghĩa là đặt tên biến ràng buộc bởi mẫu theo **vai trò, nguồn gốc và ý nghĩa của dữ liệu trong miền nghiệp vụ**. Không chỉ đặt tên theo kiểu Java (`String`, `Address`) hoặc vị trí (`a`, `b`), và cũng không thêm những tính từ dài không mang thông tin.

Bài học thuộc nhóm **Tính dễ đọc** trong Java Core Pattern Matching. Các ví dụ sử dụng Java 21+ vì record patterns và pattern matching for switch được chuẩn hóa trong Java 21 (JEP 440, JEP 441). Riêng type patterns trong `instanceof` đã chính thức từ Java 16.

## 2. Pattern variable là gì? Tên biến có thay đổi cách so khớp không?

**Type pattern** khai báo một biến có kiểu sau khi phép kiểm tra kiểu thành công:

```java
if (candidate instanceof ShippingUpdated shippingEvent) {
    System.out.println(shippingEvent.orderId());
}
```

Ở đây:
- `ShippingUpdated` là **kiểu cần kiểm tra**.
- `shippingEvent` là **pattern variable**, chỉ sử dụng được ở vùng mà trình biên dịch biết pattern đã khớp.
- Tên `shippingEvent` cho biết đây là **sự kiện**, không phải chính một địa chỉ hay đối tượng đơn hàng.

**Record pattern** có thể phân rã từng thành phần được khai báo trong record:

```java
if (candidate instanceof ShippingUpdated(
        var orderId, var shippingAddress)) {
    // orderId được suy ra là String.
    // shippingAddress được suy ra là Address.
}
```

Trong biểu thức trên, hai biến `orderId` và `shippingAddress` là biến được ràng buộc bởi các mẫu thành phần `var`. Java suy ra kiểu của chúng từ khai báo `record ShippingUpdated(String orderId, Address shippingAddress)`.

**Quy tắc cốt lõi:** record pattern ghép các mẫu con với thành phần record theo **thứ tự khai báo**, chứ không dựa trên tên biến. Đổi `orderId` thành `foo` không khiến compiler lấy thành phần khác; chỉ khiến ý nghĩa khó đọc hơn. Ngược lại, viết nhầm tên có vẻ đúng vai trò **không tự sửa được vị trí** nếu các thành phần cùng kiểu bị đảo.

```java
record Transfer(String senderAccountId, String receiverAccountId) {}

// SAI về ý nghĩa tên: hai biến String vẫn hợp lệ ở mức kiểu.
if (candidate instanceof Transfer(
        var receiverAccountId, var senderAccountId)) {
    // receiverAccountId thực ra lấy từ thành phần senderAccountId!
}
```

Ví dụ này là đoạn minh họa, giả định `candidate` đã khai báo. Vì hai thành phần đều là `String`, trình biên dịch không nhất thiết phát hiện lỗi hoán đổi vai trò. Đọc đúng record declaration và kiểm tra logic nghiệp vụ quan trọng hơn việc chỉ trông chờ kiểm tra kiểu.

## 3. Từ “tên theo type” đến “tên theo vai trò domain”

Một quy tắc thực dụng: **kiểu cho biết dữ liệu là gì về mặt kỹ thuật; tên biến cho biết dữ liệu đóng vai trò gì trong trường hợp đang xét**.

| Kiểu tĩnh / vị trí | Tên ít thông tin | Tên có ngữ cảnh domain | Ý nghĩa |
| --- | --- | --- | --- |
| `String` ở thành phần đơn hàng | `s`, `id` | `orderId` | Phân biệt định danh đơn hàng với định danh khách hàng |
| `String` ở thành phần khách hàng | `x`, `id2` | `customerId` | Không nhầm với `orderId` |
| `Address` trong khách hàng | `address`, `a` | `contactAddress` | Dữ liệu phục vụ liên hệ |
| `Address` trong vận chuyển | `address`, `a2` | `shippingAddress` | Đích giao hàng |
| `String` thành phố liên hệ | `city1` | `contactCity` | Thành phố của địa chỉ liên hệ |
| `String` thành phố giao hàng | `city2` | `shippingCity` | Thành phố của địa chỉ giao hàng |
| `long` tiền tính bằng cent | `amount`, `n` | `amountInCents` | Làm rõ đơn vị, tránh nhầm cent với đơn vị tiền chính |
| `String` mã tiền tệ | `code`, `c` | `currencyCode` | Phân biệt với mã quốc gia hoặc trạng thái |
| `String` lý do hủy | `reason`, `r` | `cancellationReason` | Lý do thuộc sự kiện hủy |
| `String` mã yêu cầu | `id`, `x` | `requestId` | Không nhầm với `orderId` |

**Mức chi tiết phụ thuộc phạm vi.** Nếu một hàm chỉ có một `Address` duy nhất và toàn bộ hàm xử lý địa chỉ giao hàng, `shippingAddress` rất rõ; nếu hàm xử lý đồng thời hai địa chỉ, cần phân biệt `contactAddress` và `shippingAddress`. Tên `shippingAddressCityStringValue` lại thừa vì vừa diễn giải quá mức vừa lặp kiểu kỹ thuật.

Tên nên:
- Dùng danh từ/cụm danh từ đúng khái niệm: `orderId`, `placedEvent`, `customerId`.
- Thể hiện vai trò ở những nhánh cùng kiểu: `contactCity` so với `shippingCity`.
- Ghi đơn vị hoặc thang đo khi lỗi đơn vị gây hậu quả: `amountInCents`, `durationMillis`.
- Không “nói dối” về cấu trúc: một biến `ShippingUpdated` là sự kiện, không đặt là `order` nếu nó không phải một record `Order`.
- Theo quy ước đặt tên Java `lowerCamelCase`, nhất quán với codebase và thuật ngữ domain.
- Giữ đủ ngắn trong phạm vi cục bộ, nhưng đủ khác biệt để không phải dò ngược nhiều tầng pattern.

## 4. Khi có nhiều record cùng kiểu: thêm nguồn gốc vào tên

Một trong những tình huống khó đọc nhất là **record patterns lồng nhau có các thành phần cùng kiểu**.

Giả sử:

```java
record Address(String city, String countryCode) {}
record Customer(String customerId, Address contactAddress) {}
record DeliveryRequest(String requestId, Customer customer, Address shippingAddress) {}
```

Mẫu lồng nhau:

```java
if (candidate instanceof DeliveryRequest(
        var requestId,
        Customer(var customerId,
                Address(var contactCity, var contactCountryCode)),
        Address(var shippingCity, var shippingCountryCode))) {
    System.out.println(requestId
            + ": contact=" + contactCity
            + ", ship=" + shippingCity);
}
```

Các biến được đặt tên theo **đường đi qua mô hình**:

```text
DeliveryRequest
  ├── requestId
  ├── customer: Customer
  │   ├── customerId
  │   └── contactAddress: Address
  │        ├── contactCity
  │        └── contactCountryCode
  └── shippingAddress: Address
       ├── shippingCity
       └── shippingCountryCode
```

Từ một cái nhìn vào thân `if`, người đọc hiểu tại sao `contactCity` và `shippingCity` có thể khác nhau. Hai biến cùng là `String`, nhưng tên cho thấy nguồn và vai trò của từng giá trị. Việc kiểm tra kiểu không thay thế được ngữ nghĩa này.

Một mẫu rút gọn quá mức:

```java
if (candidate instanceof DeliveryRequest(
        var id1, Customer(var id2, Address(var c1, var cc1)),
        Address(var c2, var cc2))) {
    // Đọc tiếp phải nhớ c1 thuộc nhánh nào.
}
```

Code hợp lệ về mặt cú pháp, nhưng gánh nặng nhận thức tăng lên khi thêm xử lý: tính phí vận chuyển theo `c1` thay vì `c2` vẫn biên dịch nếu cả hai là chuỗi. Tên domain không loại bỏ toàn bộ lỗi, nhưng giúp review và kiểm thử tập trung đúng ý nghĩa.

## 5. Tên theo domain và mức phân rã: đừng làm mất object gốc quá sớm

Không phải mọi bài toán đều cần lấy hết thành phần trong một pattern. Khi nghiệp vụ còn dùng API hoặc quy tắc của record con, có thể **giữ record con** thay vì chỉ lấy trường nguyên thủy.

### Phân rã quá sâu

```java
if (candidate instanceof DeliveryRequest(
        var requestId,
        Customer(var customerId, Address(var contactCity, var contactCountryCode)),
        Address(var shippingCity, var shippingCountryCode))) {
    // Có 6 biến rời. Muốn gọi phương thức trên Address cần thêm tham chiếu.
}
```

### Giữ đối tượng theo đúng vai trò

```java
if (candidate instanceof DeliveryRequest(
        var requestId, var customer, var shippingAddress)) {
    // customer: Customer; shippingAddress: Address.
    if (customer != null && shippingAddress != null) {
        System.out.println(requestId + " -> " + shippingAddress.city());
    }
}
```

Đây là các đoạn minh họa, dựa trên record định nghĩa ở phần trước. Đặt tên `shippingAddress` thay cho `address` cho phép phần thân tiếp tục truy xuất `shippingAddress.countryCode()` và truyền record này đến API vận chuyển; `customer` vẫn là một thực thể có thể chứa `contactAddress`.

Trong trường hợp chỉ cần toàn bộ record theo kiểu con, **type pattern** còn gọn hơn:

```java
if (candidate instanceof ShippingUpdated shippingEvent) {
    Address shippingAddress = shippingEvent.shippingAddress();
    // Có cả sự kiện và địa chỉ, đều được đặt tên đúng vai trò.
}
```

Không thể chỉ dựa vào tên biến để “gắn” toàn bộ object cha nếu pattern đã chỉ ràng buộc các thành phần. Java 21 không có cú pháp record pattern tổng quát vừa đặt một tên cho record cha ngay tại nút đó, vừa phân rã tất cả thành phần theo kiểu `as`. Khi cần giữ record cha, dùng mẫu kiểu như `instanceof ShippingUpdated shippingEvent`, hoặc giữ tham chiếu đầu vào có kiểu thích hợp.

**Quy tắc:** chỉ destructure đến mức dữ liệu được dùng thực sự; tên domain cho thành phần **và** tên domain cho record trung gian đều có giá trị.

## 6. Ví dụ đầy đủ Java 21: đặt tên biến theo ngữ nghĩa nghiệp vụ

Chương trình sau minh họa type patterns, record patterns, mẫu lồng nhau, `switch` với `when`, đặt tên theo vai trò, cùng những nhánh dữ liệu thiếu. Lưu vào tệp **`DomainPatternNamesDemo.java`**.

```java
public class DomainPatternNamesDemo {
    record Address(String city, String countryCode) {}
    record Customer(String customerId, Address contactAddress) {}
    record Money(long amountInCents, String currencyCode) {}
    record DeliveryRequest(String requestId, Customer customer, Address shippingAddress) {}

    sealed interface OrderEvent permits OrderPlaced, ShippingUpdated, OrderCancelled {}
    record OrderPlaced(String orderId, Customer customer, Money total) implements OrderEvent {}
    record ShippingUpdated(String orderId, Address shippingAddress) implements OrderEvent {}
    record OrderCancelled(String orderId, String cancellationReason) implements OrderEvent {}

    static String describe(Object candidate) {
        return switch (candidate) {
            case null -> "unknown:null";

            // Cac bien noi len don hang, khach hang va don vi tien.
            case OrderPlaced(
                    var orderId,
                    Customer(var customerId, var contactAddress),
                    Money(var amountInCents, var currencyCode))
                    when amountInCents >= 0 ->
                    "order=" + orderId + " customer=" + customerId
                    + " totalCents=" + amountInCents + " " + currencyCode;

            // Giu customer va total neu mau sau khong du dieu kien.
            case OrderPlaced(var orderId, var customer, var total) ->
                    "placed:incomplete:" + orderId;

            // Dia chi giao hang: khong nham voi dia chi lien he.
            case ShippingUpdated(
                    var orderId, Address(var shippingCity, var shippingCountryCode)) ->
                    "shipping:" + orderId + " to "
                    + shippingCity + "/" + shippingCountryCode;

            case ShippingUpdated(var orderId, var shippingAddress) ->
                    "shipping:missing:" + orderId;

            case OrderCancelled(var orderId, var cancellationReason) ->
                    "cancelled:" + orderId + " reason=" + cancellationReason;

            default -> "unknown:type";
        };
    }

    static String addresses(Object candidate) {
        if (candidate instanceof DeliveryRequest(
                var requestId,
                Customer(var customerId,
                        Address(var contactCity, var contactCountryCode)),
                Address(var shippingCity, var shippingCountryCode))) {
            return requestId + " customer=" + customerId
                    + " contact=" + contactCity + "/" + contactCountryCode
                    + " ship=" + shippingCity + "/" + shippingCountryCode;
        }
        return "missing route";
    }

    static String shippingLabel(Object candidate) {
        if (candidate instanceof ShippingUpdated(
                var orderId,
                Address(var shippingCity, var shippingCountryCode))) {
            return orderId + " -> " + shippingCity + " (" + shippingCountryCode + ")";
        }
        return "not-shippable";
    }

    public static void main(String[] args) {
        Customer customer = new Customer("C-11", new Address("Ha Noi", "VN"));

        System.out.println(describe(new OrderPlaced(
                "O-501", customer, new Money(125000, "USD"))));
        System.out.println(describe(new ShippingUpdated(
                "O-501", new Address("Da Nang", "VN"))));
        System.out.println(describe(new ShippingUpdated("O-502", null)));
        System.out.println(describe(new OrderPlaced(
                "O-503", null, new Money(20, "USD"))));
        System.out.println(describe(new OrderPlaced(
                "O-504", new Customer("C-12", null), new Money(-100, "USD"))));
        System.out.println(describe(new OrderCancelled("O-501", "user-request")));

        System.out.println(addresses(new DeliveryRequest(
                "D-1", customer, new Address("Da Nang", "VN"))));
        System.out.println(addresses(new DeliveryRequest(
                "D-2", new Customer("C-12", null), new Address("Hue", "VN"))));

        System.out.println(shippingLabel(new ShippingUpdated(
                "O-511", new Address("Hue", "VN"))));
        System.out.println(shippingLabel(new ShippingUpdated("O-512", null)));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac --release 21 -encoding UTF-8 DomainPatternNamesDemo.java
java DomainPatternNamesDemo
```

**Đầu ra chính xác:**

```text
order=O-501 customer=C-11 totalCents=125000 USD
shipping:O-501 to Da Nang/VN
shipping:missing:O-502
placed:incomplete:O-503
placed:incomplete:O-504
cancelled:O-501 reason=user-request
D-1 customer=C-11 contact=Ha Noi/VN ship=Da Nang/VN
missing route
O-511 -> Hue (VN)
not-shippable
```

### Phân tích ngữ nghĩa và tên biến

**Sự kiện đặt hàng:** `OrderPlaced` chứa `orderId`, `customer` và `total`. Mẫu đầu tiên phân rã sâu các thành phần cần dùng: `customerId`, `contactAddress`, `amountInCents` và `currencyCode`. `contactAddress` vẫn được ràng buộc như một `Address` nhưng chưa cần phân rã thành phố/quốc gia vì phương thức `describe` không sử dụng chúng; đây là lựa chọn cố ý để tránh tạo biến vô ích.

**Tiền và đơn vị:** `amountInCents` là số nguyên được khai báo trong `Money`, chẳng hạn `125000` là 125000 cent của `USD`, không phải 125000 đô la. Tên chỉ đơn vị giúp người đọc không nhầm khi tính toán/hiển thị. Ví dụ không tự động chuyển đổi cent sang đô la; nó chỉ in giá trị đã lưu.

**Thứ tự nhánh:** mẫu `OrderPlaced` có guard `amountInCents >= 0` đứng trước mẫu `OrderPlaced(var orderId, var customer, var total)` rộng hơn. Trường hợp `customer == null`, `total == null` hoặc số tiền âm không khớp nhánh sâu có điều kiện và đi vào nhánh dự phòng. Tên `customer` và `total` trong nhánh dự phòng giúp người đọc thấy record nào chưa được phân rã sâu, dù ví dụ chỉ trả thông báo ngắn.

**Vận chuyển:** `shippingCity` và `shippingCountryCode` phân biệt rõ địa chỉ giao hàng. Nếu `shippingAddress == null`, mẫu record `Address(...)` không khớp; nhánh `ShippingUpdated(var orderId, var shippingAddress)` phía sau xử lý trường hợp còn lại. `shippingAddress` có thể là `null` ở nhánh đó, nhưng pattern variable vẫn được ràng buộc.

**Hủy đơn:** `cancellationReason` thể hiện lý do của hành động hủy, tránh nhầm với `reason` từ một loại sự kiện khác nếu sau này mô hình mở rộng.

**Hai địa chỉ:** phương thức `addresses` dùng `contactCity`/`contactCountryCode` và `shippingCity`/`shippingCountryCode` vì có hai `Address` cùng kiểu. Khi địa chỉ liên hệ của khách hàng bằng `null`, mẫu lồng nhau thất bại và trả `"missing route"`.

**Kiểu và cú pháp:** mẫu `var amountInCents` trong record `Money(long amountInCents, ...)` được Java suy ra là `long`. Tên biến không ảnh hưởng tới cơ chế suy luận; chỉ giúp truyền đạt ý nghĩa của `long` đó cho người đọc.

## 7. Đặt tên trong `switch`: rõ vai trò, không cần đặt độc nhất toàn phương thức

Pattern variable trong `case` có phạm vi theo nhánh của switch. Vì vậy, có thể dùng lại tên `orderId` ở nhiều case khi **cùng mang một ý nghĩa nghiệp vụ**:

```java
return switch (event) {
    case OrderPlaced(var orderId, var customer, var total) ->
            "placed:" + orderId;
    case ShippingUpdated(var orderId, var shippingAddress) ->
            "shipping:" + orderId;
    case OrderCancelled(var orderId, var cancellationReason) ->
            "cancelled:" + orderId;
};
```

Đây là **đoạn minh họa** dùng `OrderEvent event` và các record trong chương trình ở mục 6. Mỗi `orderId` là một biến pattern cục bộ của nhánh đó, nhưng cùng ý nghĩa định danh đơn hàng. Không cần dùng `placedOrderId`, `shippedOrderId`, `cancelledOrderId` chỉ để làm chúng độc nhất nếu chúng cùng chỉ một khái niệm.

Ngược lại, nếu có cả `customerId` và `orderId` trong **cùng một nhánh**, không được đặt cả hai đều là `id`. Nếu ở hai nhánh các giá trị có ý nghĩa khác nhau, việc dùng chung tên `id` tuy có thể hợp lệ nhưng có thể khiến người đọc hiểu nhầm.

Khi sử dụng `when`, đặt tên đủ rõ để điều kiện đọc được mà không cần dịch ngược:

```java
case OrderPlaced(
        var orderId, var customer, Money(var amountInCents, var currencyCode))
        when amountInCents >= 0 -> "non-negative amount";
```

Đây là nhãn `case` minh họa, không phải câu lệnh độc lập. Biến `amountInCents` nằm trong phạm vi `when` nên có thể được dùng trực tiếp. Một điều kiện như `n >= 0` khiến ý nghĩa về tiền ít rõ hơn.

**Chú ý:** tên `amountInCents` không làm Java tự kiểm tra rằng dữ liệu là cent hoặc currency code hợp lệ; đó vẫn là trách nhiệm thiết kế `Money` và validation nghiệp vụ.

## 8. Flow scoping: đặt tên đúng vẫn phải dùng đúng phạm vi

Với `instanceof`, pattern variable chỉ khả dụng ở nơi điều khiển luồng chứng minh phép kiểm tra đã khớp.

```java
if (candidate instanceof ShippingUpdated shippingEvent) {
    System.out.println(shippingEvent.orderId());
}
// shippingEvent không tự động dùng được sau if.
```

Kết hợp kiểm tra bổ sung bằng `&&`:

```java
if (candidate instanceof ShippingUpdated(
        var orderId, var shippingAddress)
        && shippingAddress != null) {
    System.out.println(orderId + " -> " + shippingAddress.city());
}
```

Vế phải của `&&` chỉ được xét khi mẫu record đã khớp, nên có thể dùng `shippingAddress`. Việc kiểm tra `null` là cần thiết: một mẫu thành phần `var shippingAddress` có thể ràng buộc giá trị `null` dù `ShippingUpdated` bên ngoài hợp lệ.

Không dùng một pattern variable ở nơi nó có thể chưa được ràng buộc:

```java
// CỐ Ý SAI: vế phải || không được bảo đảm shippingEvent tồn tại.
if (candidate instanceof ShippingUpdated shippingEvent
        || shippingEvent.shippingAddress() != null) {
    System.out.println("check");
}
```

Compiler sẽ từ chối vì `shippingEvent` không nằm trong phạm vi an toàn của vế phải `||`. Đây là quy tắc phạm vi và kiểm soát luồng, **không phải** hậu quả của tên biến. Với logic “đúng kiểu *và* có địa chỉ”, viết `&&` thay vì `||`.

Trong `switch`, phạm vi pattern variable bao gồm guard `when` và biểu thức/khối xử lý tương ứng với case. Không dùng tên biến trong case khác hoặc ở ngoài switch nếu chưa khai báo lại hợp lệ.

## 9. Tên miền nghiệp vụ phải nhất quán với record component và API

Tên biến pattern có thể khác tên thành phần record để diễn đạt rõ **ngữ cảnh sử dụng**, nhưng không nên tạo ra ý nghĩa sai.

Ví dụ record dùng tên chung:

```java
record Contact(String name, String phone) {}
record Parcel(String id, Contact contact) {}

if (candidate instanceof Parcel(
        var parcelId, Contact(var recipientName, var recipientPhone))) {
    System.out.println(parcelId + " -> " + recipientName);
}
```

Ở đây, `id` được đặt tên thành `parcelId`; `Contact.name` được đặt tên thành `recipientName` vì trong bối cảnh này contact là người nhận. Nếu contact thực tế đại diện cho người gửi, thì `recipientName` **sai về domain** dù cú pháp hợp lệ.

Khi domain có các từ gần nghĩa, cần chọn từ chuẩn:
- `buyer` so với `recipient`: người mua có thể khác người nhận.
- `billingAddress` so với `shippingAddress`: thanh toán có thể khác giao hàng.
- `createdAt` so với `paidAt`: đều là thời điểm nhưng là hai sự kiện khác.
- `totalAmount` so với `paidAmount`: số tiền đơn hàng khác số đã thanh toán.
- `customerId` so với `userId`: chỉ gộp khi mô hình thật sự đồng nhất hai khái niệm.
- `amountInCents` so với `amountInDollars`: cùng kiểu số nhưng khác đơn vị, phải rõ trước khi chuyển đổi.

Nếu domain có đối tượng giá trị (như `Money`, `Address`, `OrderId`) thì cân nhắc giữ chính đối tượng ấy trong phạm vi phù hợp. Kiểu domain truyền đạt ràng buộc tốt hơn một nhóm biến cùng kiểu chỉ có tên khác nhau.

## 10. Lỗi thường gặp khi đặt tên pattern variable

### 10.1. Tên quá chung khiến mất nguồn gốc

`if (candidate instanceof ShippingUpdated(var id, var a))` rất ngắn nhưng làm mất dấu hiệu `id` thuộc đơn hàng và `a` là địa chỉ giao. Đổi thành `orderId` và `shippingAddress` khi thân nhánh xử lý chúng theo vai trò đó.

### 10.2. Dùng tên theo kiểu thay vì ý nghĩa

`Address address` không sai, nhưng khi có nhiều địa chỉ, `contactAddress` hoặc `shippingAddress` tốt hơn. Ngược lại, `String stringValue` chẳng cho biết chuỗi là mã đơn hàng, quốc gia hay tên khách.

### 10.3. “Đặt tên hay” nhưng đặt sai vị trí thành phần

`record Transfer(String senderAccountId, String receiverAccountId)` được phân rã theo vị trí. `Transfer(var receiverAccountId, var senderAccountId)` vẫn có thể biên dịch vì cả hai cùng là chuỗi, nhưng giá trị đã bị đặt tên sai. Đọc component declaration và viết kiểm thử cho các nhánh nhiều trường cùng kiểu.

### 10.4. Dùng thuật ngữ domain khác nhau cho cùng một khái niệm

Một file dùng `orderId`, file khác dùng `purchaseKey` hoặc `saleRef` cho cùng định danh mà không có khác biệt thực tế sẽ làm tốn thời gian đoán. Ưu tiên thuật ngữ được định nghĩa trong domain model, API và các tài liệu nghiệp vụ.

### 10.5. Đặt tên bằng giả định chưa kiểm chứng

`approvedPayment` không phù hợp nếu pattern chỉ chứng minh đối tượng là `Payment`, chưa kiểm tra trạng thái phê duyệt. Chỉ dùng tên `approvedPayment` khi có bảo đảm rõ ràng qua loại dữ liệu hoặc điều kiện đã kiểm tra. Pattern matching **không tự áp dụng** mọi quy tắc nghiệp vụ.

### 10.6. Thêm tên quá dài vào từng nút lồng nhau

`customerContactAddressCityNameString` dư thừa, khó nhìn trong một case dài. Chọn `contactCity` nếu phạm vi chỉ chứa một contact và một shipping address; `customerContactCity` nếu có nhiều contact khác nhau.

### 10.7. Quên đơn vị, múi giờ và loại mã

`amount` có thể là cent hay đô la; `timestamp` có thể là UTC hay local; `code` có thể là currency, status, country. Khi rủi ro nhầm cao, thêm `amountInCents`, `createdAtUtc`, `currencyCode` hoặc `countryCode` theo hợp đồng thật.

### 10.8. Gây xung đột tên hoặc bỏ qua flow scoping

Tên biến pattern không được trùng với một biến khác trong vùng mà Java cấm khai báo trùng. Biến pattern cũng không tự khả dụng ở mọi nhánh. Sửa tên và cấu trúc điều khiển luồng hợp lệ, đừng thêm cast dư thừa để né compiler.

### 10.9. Coi tên tốt là thay thế validation

`shippingCity` vẫn có thể là `null` hoặc chuỗi rỗng; `amountInCents` vẫn có thể âm; `currencyCode` vẫn có thể không hợp lệ. Tên đúng hỗ trợ đọc code, **không ràng buộc runtime value**.

### 10.10. Biến việc đổi tên thành refactor thay đổi behavior

Đổi tên `id` thành `orderId` đơn thuần không thay dữ liệu khi mọi tham chiếu được cập nhật đúng. Nhưng đồng thời đổi thứ tự các mẫu record, thay guard, chuyển `if` sang `switch` hoặc thay gọi accessor có thể đổi behavior. Nên tách sửa tên khỏi thay đổi cấu trúc logic nếu mục tiêu là cải thiện readability có thể review dễ dàng.

## 11. Checklist khi review code dùng record/type pattern

| Câu hỏi khi đọc diff | Dấu hiệu tốt | Dấu hiệu cần sửa |
| --- | --- | --- |
| Biến đang đại diện cho điều gì? | `orderId`, `customerId`, `shippingAddress` | `id1`, `id2`, `x` |
| Có hai giá trị cùng kiểu không? | `contactCity` và `shippingCity` | `city1` và `city2` |
| Domain có đơn vị đo không? | `amountInCents`, `durationMillis` | `amount`, `time` trong phép tính nhạy cảm |
| Biến đại diện object hay sự kiện? | `shippingEvent` cho `ShippingUpdated` | `order` khi thực chất là event |
| Tên có đúng vị trí thành phần record không? | Thứ tự khớp khai báo record | Tên tốt nhưng bị hoán đổi |
| Có giữ record trung gian khi cần không? | `customer`, `shippingAddress` | Phân rã sâu mọi thứ thành chuỗi rời |
| Có biến không được sử dụng không? | Chỉ bind dữ liệu cần xử lý | Tạo nhiều `var` vô ích rồi bỏ qua |
| Guard có dễ hiểu không? | `amountInCents >= 0` | `n >= 0` khi không rõ n |
| Có phụ thuộc vào `null` hay giới hạn phạm vi không? | Kiểm tra đúng trước khi dùng | Accessor trên biến có thể `null` |
| Có dùng đúng thuật ngữ nghiệp vụ không? | Đồng nhất tên với mô hình và API | Đặt tên theo suy đoán của người sửa |

Việc review có thể tập trung vào **đường đi của dữ liệu**: “giá trị này xuất phát từ component nào, đại diện vai trò gì, dùng ở đâu?”. Với các mẫu có nhiều tầng, trả lời nhanh các câu hỏi ấy là chỉ báo tốt cho tên biến.

## 12. Thực hành đổi tên trước/sau

### Trước: code hợp lệ nhưng khó đoán

```java
if (candidate instanceof DeliveryRequest(
        var a, Customer(var b, Address(var c, var d)),
        Address(var e, var f))) {
    System.out.println(a + ":" + c + ":" + e);
}
```

### Sau: cùng cấu trúc, ý nghĩa nhìn thấy ngay

```java
if (candidate instanceof DeliveryRequest(
        var requestId,
        Customer(var customerId,
                Address(var contactCity, var contactCountryCode)),
        Address(var shippingCity, var shippingCountryCode))) {
    System.out.println(requestId + ":" + contactCity + ":" + shippingCity);
}
```

Các đoạn này là ví dụ minh họa trong ngữ cảnh đã khai báo record và `candidate`. Khi cùng record được dùng và các biến được thay thế nhất quán theo đúng vị trí, phép so khớp không thay đổi; phần thân vẫn in cùng ba thành phần theo thứ tự. Điểm khác nhau là người đọc biết được hai thành phố đến từ đâu.

Nếu thân code chỉ cần thành phố giao hàng, còn cách viết ngắn và rõ hơn có thể là **ít phân rã hơn**:

```java
if (candidate instanceof DeliveryRequest(
        var requestId, var customer, var shippingAddress)
        && shippingAddress != null) {
    System.out.println(requestId + ":" + shippingAddress.city());
}
```

Đừng buộc pattern lấy cả `contactAddress` khi nghiệp vụ không cần; một mẫu quá sâu có thể không khớp vì `contactAddress == null` dù địa chỉ giao hàng vẫn hợp lệ.

## 13. Bài tập và đáp án

**Bài 1 — Hai ID.** Với `record Order(String orderId, String customerId)`, tại sao `Order(var id1, var id2)` kém rõ? Viết lại tên biến.

**Đáp án:** `Order(var orderId, var customerId)`. Kiểu `String` không phân biệt hai định danh, còn tên biến giúp kiểm tra đúng vai trò từng thành phần.

**Bài 2 — Hai địa chỉ.** Với `Customer(contactAddress)` và `Order(shippingAddress)` cùng dùng `Address`, chọn `city1/city2` hay `contactCity/shippingCity`?

**Đáp án:** `contactCity` và `shippingCity` khi cả hai xuất hiện trong cùng đoạn code; nhãn thể hiện nguồn và mục đích hơn vị trí.

**Bài 3 — Đơn vị tiền.** Tại sao `Money(var amount, var currency)` đôi khi chưa đủ rõ nếu API lưu số cent?

**Đáp án:** `amountInCents` và `currencyCode` giúp phân biệt số nguyên đơn vị cent với số tiền theo đơn vị chính. Nhưng tên không xác thực giá trị; hợp đồng `Money` và phép tính vẫn phải đúng.

**Bài 4 — Vị trí record.** Với `record Transfer(String senderAccountId, String receiverAccountId)`, đoạn `Transfer(var receiverAccountId, var senderAccountId)` có thể biên dịch không? Có đúng nghiệp vụ không?

**Đáp án:** có thể biên dịch vì cả hai thành phần cùng kiểu `String`, nhưng tên đã bị đảo vai trò. Cần đặt tên theo thứ tự khai báo record.

**Bài 5 — Mẫu chỉ cần một tầng.** Một chức năng chỉ in thành phố giao hàng, không dùng địa chỉ liên hệ. Có nên phân rã sâu toàn bộ `Customer.contactAddress` không?

**Đáp án:** không cần. Giữ `shippingAddress`, kiểm tra `null` rồi gọi `shippingAddress.city()`. Việc ép mẫu phải khớp địa chỉ liên hệ có thể làm loại dữ liệu vẫn dùng được.

**Bài 6 — `when` và tên biến.** Tên `amountInCents` trong `when amountInCents >= 0` mang lại lợi ích gì? Nó có đảm bảo tiền không âm không?

**Đáp án:** giúp hiểu ngay điều kiện kiểm tra số cent; ràng buộc không âm chỉ được thực hiện vì phép so sánh trong guard, không phải do tên biến.

**Bài 7 — Scope.** Có được dùng `shippingEvent` ở vế phải của `if (candidate instanceof ShippingUpdated shippingEvent || shippingEvent.shippingAddress() != null)` không?

**Đáp án:** không; khi vế trái `false`, biến chưa được ràng buộc. Nếu muốn “đúng kiểu và có địa chỉ”, dùng `&&`.

**Bài 8 — Chọn một tên theo domain.** Trong mẫu `OrderCancelled(var orderId, var x)`, thành phần thứ hai là lý do hủy dạng chuỗi. Chọn tên nào?

**Đáp án:** `cancellationReason` (hoặc `cancelReason` nếu dự án dùng thuật ngữ đó nhất quán), không phải `x` hoặc `message` không rõ mục đích.

## 14. Ghi nhớ

- **Tên pattern variable nên diễn tả ý nghĩa nghiệp vụ**, không chỉ kiểu Java hoặc vị trí trong danh sách thành phần.
- Với nhiều thành phần cùng kiểu, thêm **vai trò/nguồn gốc**: `customerId` so với `orderId`, `contactCity` so với `shippingCity`.
- Với số liệu và mã, thêm **đơn vị hoặc loại mã** khi quan trọng: `amountInCents`, `currencyCode`, `countryCode`.
- **Record pattern khớp theo thứ tự component**, không theo tên biến; đặt tên sai vẫn có thể biên dịch nếu kiểu trùng.
- Giữ record hoặc đối tượng trung gian khi cần bảo toàn bối cảnh; không phân rã sâu chỉ vì cú pháp cho phép.
- Kiểm tra `null`, guard và flow scoping theo quy tắc Java: tên tốt **không** thay cho kiểm tra dữ liệu hoặc bảo đảm compiler.
- Ưu tiên cách gọi nhất quán với domain model và API trong dự án; ngắn vừa đủ nhưng đủ rõ để tránh nhầm vai trò.

**Tài liệu tham khảo chính thức:** [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
