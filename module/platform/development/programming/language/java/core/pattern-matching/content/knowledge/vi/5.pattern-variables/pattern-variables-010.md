# Đặt tên pattern variable để giữ ngữ nghĩa domain trong Java 21

## 1. Vì sao tên biến quan trọng khi dùng pattern matching?

Pattern matching trong Java cho phép kiểm tra kiểu hoặc cấu trúc dữ liệu và **khai báo biến ngay tại vị trí khớp**. Ví dụ:

```java
if (event instanceof PaymentReceived payment) {
    process(payment);
}
```

Phần `PaymentReceived payment` là **type pattern**; `payment` là **pattern variable**. Tên `payment` giúp người đọc nhận ra giá trị có vai trò gì trong luồng nghiệp vụ. Nếu chỉ đặt là `p` hay `x`, trình biên dịch vẫn có thể chấp nhận, nhưng người đọc phải tự suy luận ý nghĩa của nó.

**Domain** là miền nghiệp vụ mà chương trình đang mô hình hóa, chẳng hạn đơn hàng, thanh toán, giao hàng, đặt chỗ hoặc hóa đơn. **Giữ ngữ nghĩa domain** nghĩa là tên biến diễn đạt đúng vai trò của dữ liệu ở chỗ nó được sử dụng: ai là người mua, số tiền nào đã thu, mã nào thuộc giao dịch nào, địa điểm nào là điểm đi và điểm đến.

So sánh hai cách viết cùng một điều kiện:

```java
// Vai trò không rõ:
if (value instanceof PaymentReceived p) {
    audit(p);
}

// Vai trò rõ hơn:
if (value instanceof PaymentReceived receivedPayment) {
    audit(receivedPayment);
}
```

Hai đoạn trên là **mảnh mã minh họa**; các kiểu và phương thức nghiệp vụ phải được định nghĩa trong ứng dụng. Với Java 21, cơ chế pattern matching của hai đoạn là như nhau. Giá trị của tên tốt nằm ở khả năng giải thích **tại sao** một giá trị được dùng trong luồng nghiệp vụ và giảm việc hiểu nhầm khi sửa code.

Điều này đặc biệt quan trọng đối với **record pattern**, vì một dòng có thể khai báo đồng thời nhiều pattern variable:

```java
record Transfer(String fromAccountId, String toAccountId, long amountVnd) {}

// Pattern đọc dữ liệu chuyển khoản:
if (value instanceof Transfer(
        String sourceAccountId,
        String destinationAccountId,
        long transferAmountVnd)) {
    // Có thể đọc ngay vai trò từng giá trị mà không dò lại record declaration
}
```

`sourceAccountId` và `destinationAccountId` đều có kiểu `String`; kiểu Java không thể phân biệt **vai trò nghiệp vụ** của chúng. Tên biến phải làm được việc đó.

## 2. Phân biệt bốn loại tên khi đọc một pattern

Xét:

```java
record Order(String orderId, String buyerId) {}

if (input instanceof Order(String matchedOrderId, String purchasingCustomerId)) {
    // ...
}
```

Có bốn thành phần khác nhau:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tên **kiểu domain** | `Order` | Định nghĩa khái niệm nghiệp vụ |
| Tên **record component** | `orderId`, `buyerId` | Dữ liệu thành phần theo định nghĩa của record |
| Tên **pattern variable** | `matchedOrderId`, `purchasingCustomerId` | Biến cục bộ được khai báo khi pattern khớp |
| Tên **giá trị đang kiểm tra** | `input` | Biến ban đầu chứa đối tượng cần phân loại |

Trong record pattern, Java đối chiếu component **theo vị trí và kiểu**, không theo sự giống nhau giữa tên pattern variable và tên record component. `purchasingCustomerId` vẫn nhận **component thứ hai** (`buyerId`) vì nó đứng ở vị trí thứ hai.

Không bắt buộc đặt tên pattern variable trùng với tên component. Nhưng khi đổi tên, cần giữ đúng nghĩa: nếu `buyerId` là mã người mua thì `supplierId` là tên **gây hiểu nhầm**, dù đoạn mã có thể biên dịch.

**Quy tắc cốt lõi:** tên pattern variable phải diễn đạt *giá trị này là gì trong ngữ cảnh xử lý*, còn kiểu và vị trí record component quyết định *giá trị nào được liên kết*.

## 3. Đặt tên theo vai trò nghiệp vụ, không chỉ theo kiểu

Một `String` có thể là mã đơn hàng, mã khách hàng, địa chỉ email hoặc thông báo lỗi. Một `long` có thể là số tiền, thời gian hoặc số lượng. Tên chỉ phản ánh kiểu không đủ để truyền tải ý nghĩa:

| Tên khó hiểu | Tên diễn đạt domain | Lý do |
| --- | --- | --- |
| `s`, `str` | `orderId`, `customerEmail` | Nêu đúng loại chuỗi |
| `n`, `num` | `quantity`, `paymentAmountVnd` | Nêu đúng đại lượng, có thể kèm đơn vị |
| `p`, `obj` | `receivedPayment`, `targetProduct` | Gắn đối tượng với vai trò |
| `item1`, `item2` | `sourceItem`, `replacementItem` | Phân biệt hai đối tượng cùng kiểu |
| `a`, `b` | `originCity`, `destinationCity` | Tránh đảo chiều trong xử lý tuyến đường |
| `r`, `res` | `approvalResult`, `declineReason` | Giúp hiểu nhánh nào đang được xét |
| `data`, `value` | `matchedOrder`, `selectedShipment` | Bớt mơ hồ khi nhiều nguồn dữ liệu cùng tồn tại |

Không phải tên nào càng dài cũng càng tốt. `orderId` thường tốt hơn `theUniqueIdentifierOfTheOrderBeingProcessed`. Hãy chọn **tên ngắn nhất vẫn đủ phân biệt vai trò trong phạm vi đang đọc**.

Ví dụ khi cả hai đầu của một tuyến đường đều là `Location`:

```java
record Location(String city) {}
record ShipmentRoute(Location origin, Location destination) {}

if (candidate instanceof ShipmentRoute(
        Location(String originCity),
        Location(String destinationCity))) {
    System.out.println(originCity + " -> " + destinationCity);
}
```

`originCity` và `destinationCity` làm rõ chiều vận chuyển. Các tên `city1` và `city2` che mất thông tin quan trọng; người bảo trì có thể dễ dàng đảo hai giá trị mà trình biên dịch không phát hiện.

## 4. Đặt tên type pattern cho đúng đối tượng đã khớp

Type pattern có cú pháp cơ bản `Type variableName`, chẳng hạn:

```java
if (message instanceof PaymentCommand paymentCommand) {
    dispatch(paymentCommand);
}
```

`paymentCommand` là giá trị đã khớp kiểu `PaymentCommand`. Khi đặt tên, hãy chọn giữa:

- **Danh từ nghiệp vụ:** `order`, `invoice`, `customer`, `payment`.
- **Danh từ có vai trò trong thao tác:** `originalOrder`, `replacementOrder`, `selectedInvoice`, `sourceAccount`.
- **Tên có trạng thái khi trạng thái được kiểu hoặc logic đảm bảo:** `approvedOrder` cho một kiểu thực sự mô hình hóa `ApprovedOrder`, hoặc biến dùng trong nhánh đã kiểm tra trạng thái đó.

Ví dụ với các lớp domain giả định:

```java
// MẢNH MÃ: các kiểu OrderEvent, OrderCancelled được định nghĩa trong ứng dụng.
if (event instanceof OrderCancelled cancelledOrderEvent) {
    notifyCustomer(cancelledOrderEvent);
}
```

`cancelledOrderEvent` chính xác hơn `cancelledOrder` nếu dữ liệu được match thực sự là **sự kiện**, không phải chính đơn hàng.

### Tránh tên hứa hẹn điều chưa được chứng minh

Một phép match kiểu không tự xác nhận mọi quy tắc nghiệp vụ:

```java
// Tên gây hiểu nhầm nếu chỉ kiểm tra String:
if (input instanceof String verifiedEmail) {
    sendNotice(verifiedEmail);
}
```

`String` không bảo đảm chuỗi là email hợp lệ hay đã được xác thực. Tên `verifiedEmail` tạo ấn tượng sai.

Cách rõ ràng hơn:

```java
if (input instanceof String emailCandidate
        && isValidEmail(emailCandidate)) {
    sendNotice(emailCandidate);
}
```

Ở đây `isValidEmail` là hàm kiểm tra nghiệp vụ **minh họa**, cần có triển khai thực tế. Biến `emailCandidate` vẫn mô tả đúng dữ liệu đầu vào; việc hợp lệ đã được thể hiện bằng điều kiện. Nếu hệ thống có kiểu `VerifiedEmail` thực sự bảo đảm bất biến này, dùng type pattern `VerifiedEmail verifiedEmail` mới có cơ sở mạnh hơn.

## 5. Record pattern: đặt tên theo vị trí và nghĩa của component

Trong Java 21, record pattern cho phép lấy nhiều giá trị ngay từ các component:

```java
record Invoice(String invoiceId, String customerId, long totalVnd) {}

if (candidate instanceof Invoice(
        String matchedInvoiceId,
        String billedCustomerId,
        long invoiceTotalVnd)) {
    // ...
}
```

Các component của `Invoice` có thứ tự cố định: `invoiceId`, `customerId`, `totalVnd`. Pattern nhận dữ liệu theo thứ tự đó, bất kể biến được đặt tên gì. Vì thế, khi refactor record pattern, **kiểm tra vị trí trước rồi chọn tên**.

Một ví dụ tên sai nhưng vẫn có thể hợp lệ về cú pháp:

```java
// LỖI NGỮ NGHĨA: hai tên làm người đọc tưởng vai trò bị đảo
if (candidate instanceof Invoice(
        String customerId,
        String invoiceId,
        long totalVnd)) {
    // customerId thực tế nhận invoiceId component;
    // invoiceId thực tế nhận customerId component!
}
```

Đây là lỗi nguy hiểm vì cả hai component đều là `String`. Trình biên dịch không thể xác định bạn có đặt sai tên vai trò hay không. Cách sửa là đổi tên theo **vị trí thực**:

```java
if (candidate instanceof Invoice(
        String invoiceId,
        String customerId,
        long invoiceTotalVnd)) {
    // ...
}
```

### Khi nào dùng `var` trong record pattern?

```java
if (candidate instanceof Invoice(
        var invoiceId,
        var customerId,
        var invoiceTotalVnd)) {
    // ...
}
```

`var` để Java suy luận kiểu của các component: hai biến đầu là `String`, biến cuối là `long`. Nó **không** suy luận ý nghĩa domain. Vì vậy, dùng `var` thì tên biến càng cần thể hiện rõ vai trò và đơn vị.

Bạn có thể giữ kiểu cụ thể khi nó giúp người đọc:

```java
if (candidate instanceof Invoice(
        String invoiceId,
        String customerId,
        long invoiceTotalVnd)) {
    // ...
}
```

Hai dạng đều là record pattern hợp lệ trong Java 21. Chọn cách thống nhất với coding convention và độ rõ ràng của đoạn code.

## 6. Nested record pattern: tên biến phải thể hiện đường đi dữ liệu

Record lồng nhau khiến người đọc phải theo dõi nhiều lớp:

```java
record Customer(String id, String displayName) {}
record Address(String city, String district) {}
record Delivery(Customer recipient, Address destination) {}

if (candidate instanceof Delivery(
        Customer(String recipientId, String recipientName),
        Address(String destinationCity, String destinationDistrict))) {
    // ...
}
```

Đọc theo đường dữ liệu:

```text
Delivery
├── recipient: Customer
│   ├── id          -> recipientId
│   └── displayName -> recipientName
└── destination: Address
    ├── city        -> destinationCity
    └── district    -> destinationDistrict
```

Ở đây `recipientName` tốt hơn `name`, vì mã nghiệp vụ có thể còn tên người gửi, người nhận, đại lý. Tương tự, `destinationCity` tốt hơn `city` nếu có cả điểm xuất phát.

**Không cần sao chép toàn bộ đường đi vào tên.** `deliveryDestinationAddressCityName` thường quá dài. Trong khối ngắn chỉ xử lý một đích đến, `destinationCity` đủ rõ.

### Khi dữ liệu có các vai trò đối xứng

```java
record Account(String accountId) {}
record Transfer(Account source, Account destination, long amountVnd) {}

if (candidate instanceof Transfer(
        Account(String sourceAccountId),
        Account(String destinationAccountId),
        long transferAmountVnd)) {
    // sourceAccountId và destinationAccountId có thể cùng kiểu,
    // nhưng phải giữ đúng chiều chuyển tiền.
}
```

Tên theo *source/destination* giúp tránh sai sót nghiệp vụ: chuyển nhầm hướng hoặc ghi log sai tài khoản. Khi phân tích dữ liệu cùng kiểu theo vị trí, đây là thông tin thiết yếu.

## 7. Pattern variable trong `switch`: gắn tên với từng nhánh domain

Pattern matching for `switch` là tính năng chính thức của Java 21. Mỗi nhánh có thể gắn một pattern vào trạng thái hay biến thể domain:

```java
sealed interface PaymentOutcome permits Paid, Rejected {}
record Paid(String paymentId, long amountVnd) implements PaymentOutcome {}
record Rejected(String reason) implements PaymentOutcome {}

static String describe(PaymentOutcome outcome) {
    return switch (outcome) {
        case Paid(String paymentId, long paidAmountVnd)
                when paidAmountVnd >= 1_000_000L ->
            "Large payment " + paymentId;
        case Paid(String paymentId, long paidAmountVnd) ->
            "Payment " + paymentId + ": " + paidAmountVnd;
        case Rejected(String rejectionReason) ->
            "Rejected: " + rejectionReason;
    };
}
```

Các biến mang nghĩa:

- `paymentId`: mã của giao dịch thanh toán đã thành công, không nhầm với mã đơn hàng.
- `paidAmountVnd`: số tiền **đã thanh toán**, đơn vị **VND**.
- `rejectionReason`: nguyên nhân **từ chối thanh toán**, không phải lỗi bất kỳ.
- `when paidAmountVnd >= 1_000_000L`: điều kiện cho nhánh giá trị lớn. `when` là **guard**, không phải một pattern variable.

Các nhánh `Paid(...)` dùng lại tên biến là hợp lệ vì đó là các khai báo pattern riêng theo nhánh. Tên giống nhau có nghĩa giống nhau ở cả hai nhánh, nên việc dùng nhất quán có ích. Ngược lại, không nên gọi số tiền trong một `Rejected` là `paidAmountVnd` nếu bản ghi chỉ lưu khoản **dự định thanh toán**.

### Đừng dùng tên mang nghĩa domain khác với type đang match

Ví dụ đáng tránh:

```java
// MẢNH MÃ MINH HỌA TÊN KHÔNG TỐT
case Rejected(String approvedReason) -> ...
```

Biến thực tế là lý do từ chối, nên tên `approvedReason` làm sai thông điệp nghiệp vụ. Java chỉ kiểm tra cú pháp và kiểu, không hiểu ý nghĩa tên để báo lỗi.

**Gợi ý đặt tên theo trạng thái:** `approvalReason`, `rejectionReason`, `refundReason` chỉ nên dùng khi dữ liệu tương ứng đúng với trạng thái đã được mô hình hóa.

## 8. Đặt tên khi ghép pattern với `when`

Guard có thể làm rõ điều kiện chọn nhánh:

```java
static String classify(Object candidate) {
    return switch (candidate) {
        case null -> "missing";
        case String couponCode when couponCode.isBlank() -> "blank coupon";
        case String couponCode -> "coupon: " + couponCode;
        default -> "unsupported";
    };
}
```

Trong ví dụ này:

- `couponCode` xuất phát từ **ngữ cảnh xử lý**, nên phù hợp hơn `s`.
- Cả hai nhánh `String couponCode` đều là **type pattern**, và mỗi biến chỉ tồn tại trong phạm vi nhánh riêng.
- `couponCode.isBlank()` là guard. Nó **không đổi kiểu** của biến.
- Nhánh nhận chuỗi không blank vẫn cần phân biệt “đã được kiểm tra không blank” với “mã coupon hợp lệ trong hệ thống”. Hai điều này không đồng nghĩa.

Đặt tên `validatedCouponCode` ngay tại `String` chỉ vì có `when !couponCode.isBlank()` sẽ nói quá: kiểm tra không blank chưa xác minh mã có tồn tại, hết hạn hay được áp dụng cho đơn hàng hiện tại.

## 9. Giữ nhất quán thuật ngữ domain, đơn vị và mốc thời gian

Có ba nhóm thông tin rất dễ mất khi dùng tên chung chung:

| Nhóm thông tin | Dễ gây nhầm | Tên nên cân nhắc |
| --- | --- | --- |
| **Vai trò** | Hai người/tài khoản/địa chỉ có cùng kiểu | `payerId`, `payeeId`; `originCity`, `destinationCity` |
| **Đơn vị** | `long amount` có thể tính bằng VND, USD cent, millisecond | `amountVnd`, `amountCents`, `timeoutMillis` |
| **Mốc thời gian** | Các ngày cùng kiểu `LocalDate` | `orderedAt`, `paidAt`, `deliveredAt` (kiểu thời điểm phù hợp) |
| **Trạng thái** | `total` khác `paid`, `pending`, `refunded` | `invoiceTotalVnd`, `paidAmountVnd`, `refundAmountVnd` |
| **Định danh** | Cùng là `String`, nhưng định danh thuộc các thực thể khác nhau | `orderId`, `paymentId`, `customerId` |

Tên có đơn vị không thay thế cho mô hình kiểu mạnh (ví dụ `Money`, `Currency`, `OrderId`), nhưng giúp giảm nhầm lẫn khi domain tạm dùng kiểu nguyên thủy.

Ví dụ:

```java
record Payment(String paymentId, long amountCents) {}

if (obj instanceof Payment(String paymentId, long chargedAmountCents)) {
    System.out.println(paymentId + ": " + chargedAmountCents + " cents");
}
```

Nếu muốn hiển thị USD, cần quy đổi cent sang đơn vị tiền tệ đúng quy tắc nghiệp vụ. Không nên chỉ đổi tên `chargedAmountCents` thành `chargedAmountUsd` khi giá trị vẫn tính bằng cent.

### Từ vựng thống nhất trong một codebase

Một nhóm nên thống nhất danh từ miền nghiệp vụ: `customer` hay `buyer` khi nào, `accountId` có phải định danh tài khoản hay mã người dùng, `settledAmount` khác `authorizedAmount` thế nào. Khi record component dùng `customerId` nhưng pattern variable lại dùng `clientCode` không có lý do, người đọc sẽ phải đoán đó có phải hai khái niệm khác nhau hay không.

Trong phạm vi một phương thức, tên có thể ngắn hơn khi ngữ cảnh rõ. Chỉ thêm tiền tố như `invoice`, `payment`, `shipping` khi thật sự giúp phân biệt với đối tượng khác.

## 10. Scope và xung đột tên khi đổi tên pattern variable

Tên tốt vẫn phải tuân theo **flow scoping**. Pattern variable chỉ được dùng khi Java biết pattern đã khớp.

```java
if (candidate instanceof Invoice invoice) {
    System.out.println(invoice); // Hợp lệ trong nhánh match
}
// System.out.println(invoice); // Lỗi: ngoài flow scope
```

Trong đoạn trên, `Invoice` là kiểu domain **giả định**. Sau `if`, `candidate` có thể không phải `Invoice`, nên tên `invoice` không ở scope.

Một cách giữ tên có nghĩa khi cần dùng các bước phía sau là guard clause:

```java
static String requireCustomerId(Object value) {
    if (!(value instanceof String customerId)) {
        throw new IllegalArgumentException("customerId must be a String");
    }
    return customerId;
}
```

Nhưng phương thức trên chỉ kiểm tra **kiểu**, không kiểm tra `customerId` đúng định dạng hay tồn tại trong cơ sở dữ liệu. Tên đã rõ nghĩa, còn kiểm tra domain phải được thực hiện ở nơi thích hợp.

### Tránh trùng tên biến đang ở scope

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH:
String orderId = "ORD-OLD";
if (candidate instanceof String orderId) {
    System.out.println(orderId); // Trùng khai báo tên
}
```

Sửa bằng tên có vai trò khác rõ ràng:

```java
String existingOrderId = "ORD-OLD";
if (candidate instanceof String incomingOrderId) {
    System.out.println(incomingOrderId);
}
```

Nếu cả hai là mã đơn hàng nhưng đến từ hai nguồn khác nhau, `existingOrderId` và `incomingOrderId` làm rõ mục đích so sánh. Không nên đặt `orderId2` vì không giải thích khác biệt.

Với `switch`, mỗi nhánh pattern có scope của mình. Đừng dùng biến `paidAmountVnd` của `case Paid(...)` trong nhánh `case Rejected(...)`. Nếu cần giá trị dùng sau `switch`, trả về kết quả và gán vào một biến có tên domain, chẳng hạn `paymentSummary`.

## 11. Chương trình hoàn chỉnh: nhận diện tên domain qua nhiều pattern

Tệp **`DomainPatternVariableNamesDemo.java`** dưới đây dùng các tính năng **chính thức của Java 21**, không yêu cầu preview.

```java
public class DomainPatternVariableNamesDemo {
    sealed interface PaymentOutcome permits Paid, Rejected {}

    record Paid(String paymentId, long amountVnd)
            implements PaymentOutcome {}

    record Rejected(String reason)
            implements PaymentOutcome {}

    record Customer(String customerId, String displayName) {}

    record Order(
            String orderId,
            Customer buyer,
            PaymentOutcome paymentOutcome) {}

    record City(String name) {}
    record Route(City origin, City destination) {}

    static String paymentSummary(PaymentOutcome outcome) {
        return switch (outcome) {
            case null -> "no payment outcome";
            case Paid(String paymentId, long paidAmountVnd)
                    when paidAmountVnd >= 1_000_000L ->
                "large payment " + paymentId + ": "
                        + paidAmountVnd + " VND";
            case Paid(String paymentId, long paidAmountVnd) ->
                "payment " + paymentId + ": "
                        + paidAmountVnd + " VND";
            case Rejected(String rejectionReason) ->
                "rejected: " + rejectionReason;
        };
    }

    static String orderSummary(Object candidate) {
        if (candidate instanceof Order(
                String orderId,
                Customer(String customerId, String customerName),
                Paid(String paymentId, long paidAmountVnd))) {
            return "order " + orderId + " for " + customerName
                    + " (" + customerId + "), payment " + paymentId
                    + ": " + paidAmountVnd + " VND";
        }
        return "order not paid";
    }

    static String routeSummary(Object candidate) {
        if (candidate instanceof Route(
                City(String originCity),
                City(String destinationCity))) {
            return originCity + " -> " + destinationCity;
        }
        return "unknown route";
    }

    public static void main(String[] args) {
        PaymentOutcome paid = new Paid("PAY-9", 1_500_000L);

        System.out.println(paymentSummary(paid));
        System.out.println(
                paymentSummary(new Paid("PAY-10", 250_000L)));
        System.out.println(
                paymentSummary(new Rejected("card declined")));
        System.out.println(paymentSummary(null));

        System.out.println(orderSummary(new Order(
                "ORD-1", new Customer("CUS-7", "Lan"), paid)));
        System.out.println(orderSummary(new Order(
                "ORD-2", new Customer("CUS-8", "Minh"),
                new Rejected("insufficient balance"))));

        System.out.println(routeSummary(new Route(
                new City("Hanoi"), new City("Danang"))));
    }
}
```

Biên dịch và chạy bằng **JDK 21**:

```bash
javac --release 21 DomainPatternVariableNamesDemo.java
java DomainPatternVariableNamesDemo
```

Stdout:

```text
large payment PAY-9: 1500000 VND
payment PAY-10: 250000 VND
rejected: card declined
no payment outcome
order ORD-1 for Lan (CUS-7), payment PAY-9: 1500000 VND
order not paid
Hanoi -> Danang
```

### Vì sao những tên này có ích?

- `paidAmountVnd` là giá trị thuộc trạng thái thanh toán thành công, **không** phải tổng tiền của đơn hàng.
- `paymentId` khác `orderId`; hai mã không nên đổi chỗ khi ghi log hoặc trả về kết quả.
- `customerId` khác `customerName`; tuy cả hai cùng là `String`, mỗi tên gắn đúng component của `Customer`.
- `rejectionReason` chỉ thuộc biến thể `Rejected`, tránh hiểu nhầm với ghi chú thanh toán.
- `originCity` và `destinationCity` thể hiện hướng của `Route`, thay vì `city1`, `city2`.
- `paymentSummary` là kết quả của `switch`, được đặt tên theo nghiệp vụ; biến ở từng pattern không bị đưa ra ngoài flow scope.

**Giới hạn cần nhớ:** `Paid` là một record đại diện trạng thái trong ví dụ, không phải bằng chứng một hệ thống thanh toán ngoài đời đã thực sự quyết toán. Trong ứng dụng thật, tên và mô hình `Paid`, `Settled`, `Authorized` phải phản ánh chính xác quy ước nghiệp vụ.

## 12. Những cách đặt tên dễ gây lỗi khi bảo trì

### 12.1. Đặt tên theo số thứ tự khi các giá trị có vai trò

```java
// Khó đọc:
case Route(City(var city1), City(var city2)) ->
    city1 + " -> " + city2;

// Rõ vai trò:
case Route(City(var originCity), City(var destinationCity)) ->
    originCity + " -> " + destinationCity;
```

Hai dòng là **mảnh nhãn trong switch**, cần kiểu record tương ứng và ngữ cảnh switch hợp lệ. Cách thứ hai cho biết chính xác chiều đi.

### 12.2. Tên bị đảo với thứ tự component

```java
record Refund(String originalPaymentId, String refundId, long amountVnd) {}

// Tên bên dưới SAI NGỮ NGHĨA nhưng có thể biên dịch:
if (obj instanceof Refund(
        String refundId,
        String originalPaymentId,
        long refundAmountVnd)) {
    // ...
}
```

Lúc này `refundId` thực chất nhận **mã thanh toán gốc**. Cách sửa là so lại thứ tự khai báo record, viết `String originalPaymentId, String refundId`. Hãy đặc biệt cảnh giác với record chứa nhiều component cùng kiểu.

### 12.3. Tên thể hiện trạng thái chưa được đảm bảo

```java
if (obj instanceof String approvedOrderId) {
    // Chỉ biết obj là String, chưa biết đơn hàng đã được duyệt
}
```

Thay bằng `orderIdCandidate` hoặc một tên phù hợp dữ liệu đầu vào; nếu muốn có `approvedOrderId`, hãy đặt trong một nhánh có **bằng chứng nghiệp vụ** tương ứng hoặc dùng kiểu đại diện cho trạng thái được duyệt.

### 12.4. Dùng tên chung chung cho nhiều pattern liên tiếp

```java
// MẢNH MÃ: các lớp giả định tồn tại
switch (domainEvent) {
    case PaymentReceived event -> handlePayment(event);
    case OrderCancelled event -> handleCancellation(event);
    default -> handleUnknown(domainEvent);
}
```

Tên `event` không sai: kiểu và nhánh đã rõ. Tuy nhiên, trong nhánh dài hoặc có nhiều đối tượng cùng xuất hiện, `paymentReceivedEvent` và `orderCancelledEvent` có thể rõ hơn. Đừng ép mọi nhánh dùng tên dài khi phần thân chỉ có một dòng; độ rõ phải xét **ngữ cảnh**.

### 12.5. Đổi tên một mình nhưng quên đổi tất cả chỗ sử dụng

Khi refactor `case Paid(String id, long amount)` thành `case Paid(String paymentId, long paidAmountVnd)`, cần sửa **mọi tham chiếu tương ứng trong guard và thân nhánh**. Dùng chức năng *Rename Symbol* của IDE để tránh sót hoặc vô tình sửa các tên trùng chuỗi thuộc scope khác.

## 13. Quy trình đặt tên khi đọc hoặc viết pattern mới

Bạn có thể thực hiện theo thứ tự sau:

1. **Xác định đối tượng domain:** giá trị đang kiểm tra là sự kiện thanh toán, đơn hàng hay địa chỉ? Nếu không biết domain, đọc kiểu, field hoặc record declaration.
2. **Xác định vai trò của từng giá trị:** điểm đi hay điểm đến, mã đơn hay mã thanh toán, tổng tiền hay số tiền đã thu?
3. **Đọc thứ tự component chính xác:** đặc biệt khi nhiều component là `String`, `long` hoặc cùng một record type.
4. **Chọn danh từ và bổ nghĩa cần thiết:** `paymentId`, `sourceAccountId`, `refundAmountVnd`.
5. **Kiểm tra ranh giới đảm bảo:** chỉ dùng tên mang nghĩa “đã xác thực/đã thanh toán/đã phê duyệt” nếu type hoặc logic thật sự bảo đảm.
6. **Giữ scope gọn:** dùng tên trong nhánh khớp; khi cần kết quả chung, gán ra một biến kết quả có nghĩa nghiệp vụ.
7. **Review khả năng phân biệt:** nếu đổi chỗ hai biến cùng kiểu mà compiler vẫn không báo lỗi, tên có giúp người đọc phát hiện việc đảo sai không?
8. **Kiểm tra nhất quán với từ điển nhóm:** ưu tiên tên đã xuất hiện trong mô hình domain hoặc API công khai.

Không cần kéo dài tên để chèn mọi thông tin một cách máy móc. Nếu chỉ có một `Order` trong phương thức ngắn, `order` có thể là tên tốt. Nếu có *original order* và *replacement order*, phải làm rõ hai vai trò.

## 14. Bài tập: chọn tên phản ánh đúng domain

**Bài 1.** `record Shipment(Location pickup, Location dropoff) {}`. Cách nào hợp lý hơn khi lồng pattern?

```java
Shipment(Location(var first), Location(var second))
Shipment(Location(var pickupCity), Location(var dropoffCity))
```

**Đáp án:** Dòng thứ hai. `pickupCity` và `dropoffCity` thể hiện ý nghĩa hai component theo thứ tự. Kiểm tra thêm khai báo của `Location`: ví dụ này giả định `Location` có một component thể hiện tên thành phố.

**Bài 2.** Với `record Charge(String paymentId, long amountCents) {}`, cách đặt tên nào không gây hiểu lầm?

```java
Charge(var id, var amountUsd)
Charge(var paymentId, var chargedAmountCents)
```

**Đáp án:** Dòng thứ hai. Record lưu **cent**, nên `amountUsd` sẽ gợi ý sai đơn vị. `paymentId` cho biết đối tượng sở hữu mã.

**Bài 3.** `input instanceof String verifiedEmail` có bảo đảm email đã xác thực không?

**Đáp án:** Không. Nó chỉ bảo đảm `input` là `String`. Tên nên phản ánh trạng thái thực sự, chẳng hạn `emailCandidate`, cho tới khi logic xác thực hoàn tất.

**Bài 4.** Trong `record Transfer(String sourceId, String targetId) {}`, pattern `Transfer(String targetId, String sourceId)` có tự đảo thứ tự truy xuất component không?

**Đáp án:** Không. Java ghép **theo vị trí**, nên biến đặt tên `targetId` ở đầu lại nhận component `sourceId`. Đây là lỗi đặt tên có thể dẫn đến bug nghiệp vụ mà compiler không phát hiện.

**Bài 5.** Khi nào dùng `var` cho component pattern là hợp lý?

**Đáp án:** Khi kiểu đã dễ suy luận từ record và tên biến đã nói rõ vai trò: `Transfer(var sourceAccountId, var destinationAccountId, var amountVnd)`. Nếu kiểu cung cấp thông tin quan trọng khi đọc, ghi rõ kiểu cũng tốt. `var` chỉ suy luận kiểu, không thể thay người lập trình quyết định nghĩa domain.

## 15. Checklist trước khi review hoặc merge

- [ ] Pattern variable dùng tên `lowerCamelCase` rõ nghĩa và phù hợp kiểu/domain.
- [ ] Hai giá trị cùng kiểu nhưng khác vai trò có tên phân biệt được.
- [ ] Các tên trong record pattern khớp **thứ tự component**, đặc biệt với ID, số tiền và địa chỉ.
- [ ] Tên không khẳng định trạng thái `validated`, `paid`, `approved` khi chương trình chưa chứng minh.
- [ ] Đơn vị tiền tệ, thời gian, số lượng rõ ở tên biến hoặc kiểu dữ liệu.
- [ ] Guard `when` và phạm vi pattern variable được dùng đúng, không tham chiếu ngoài flow scope.
- [ ] Tên dùng nhất quán giữa các nhánh `switch` cùng ý nghĩa nghiệp vụ.
- [ ] Các thao tác refactor đổi cả khai báo và tham chiếu, không tạo trùng tên đang trong scope.
- [ ] Ví dụ, log và thông điệp lỗi sử dụng đúng định danh domain (`orderId` khác `paymentId`).

## 16. Tài liệu tham khảo

- [Java Language Specification 21, §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): cú pháp type pattern, record pattern và pattern variable.
- [Java Language Specification 21, §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): phạm vi của pattern variable theo flow.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): giải cấu trúc record và lấy giá trị từ các component trong Java 21.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): pattern trong `switch`, `when` và phạm vi biến.
- [Oracle Java Code Conventions (lịch sử)](https://www.oracle.com/java/technologies/javase/codeconventions-namingconventions.html): tham khảo hình thức đặt tên `lowerCamelCase`; từ vựng domain cụ thể do nhóm phát triển quyết định.
