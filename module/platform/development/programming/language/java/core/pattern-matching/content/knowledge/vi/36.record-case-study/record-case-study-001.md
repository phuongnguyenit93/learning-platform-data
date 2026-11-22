# Thiết kế nested record cho dữ liệu đơn hàng trong Java 21

## 1. Bài toán: đơn hàng có cấu trúc lồng nhau

Một đơn hàng hiếm khi chỉ có `id` và `total`. Nó thường liên quan đến khách hàng, thông tin liên hệ, phương thức nhận hàng, địa chỉ giao hàng và nhiều dòng sản phẩm. Một mô hình phẳng rất nhanh trở nên khó hiểu:

```java
// Phác họa: nhiều field nullable và phụ thuộc lẫn nhau.
record OrderData(
    String orderId,
    String customerId,
    String email,
    String city,
    String street,
    String pickupStore,
    String[] skus,
    int[] quantities,
    long[] unitPrices
) {}
```

Các vấn đề của thiết kế này:
- `city`/`street` có thể null khi pickup, nhưng không được null khi delivery; ai bảo đảm?
- Ba mảng `skus`, `quantities`, `unitPrices` phải luôn cùng độ dài; phần tử cùng vị trí phải ứng với một dòng.
- Mảng mutable làm thay đổi state của record qua tham chiếu, dù record component là final.
- Đơn hàng có thể có `customerId` mà không có `email`; hợp đồng thiếu dữ liệu chưa rõ.
- Đổi một quy tắc nhỏ dễ dẫn đến validation rải khắp ứng dụng.

**Nested records** giúp đưa quan hệ dữ liệu thành **cấu trúc có tên và invariant riêng**. Thay vì ba mảng, dùng `List<OrderLine>`. Thay vì ba field địa chỉ, dùng `Address` bên trong `Delivery`. Thay vì diễn giải null theo kiểu “có địa chỉ thì giao, không có thì nhận”, dùng biến thể `Delivery` hoặc `Pickup`.

Một mô hình có ý định rõ hơn:

```text
Order
├── id: OrderId
├── customer: Customer
│   ├── id: CustomerId
│   └── contact: Contact
│       └── email: String
├── fulfillment: Fulfillment (sealed interface)
│   ├── Delivery
│   │   └── address: Address
│   │       ├── city: String
│   │       └── street: String
│   └── Pickup
│       └── storeCode: String
└── lines: List<OrderLine>
    └── OrderLine
        ├── sku: String
        ├── quantity: int
        └── unitPriceVnd: long
```

Đây là **composition**: record chứa component thuộc kiểu record khác. Không cần đặt tất cả record bên trong cùng một file hoặc khai báo record như nested class theo cú pháp Java; “nested record” trong bài chủ yếu chỉ **cấu trúc dữ liệu lồng nhau** và **record patterns lồng nhau**. Các record có thể là top-level types hoặc static nested record declarations tùy cách đóng gói.

Bài tập trung vào thiết kế domain rõ nghĩa, constructor validation, immutability ở mức cần thiết, `switch` và nested record patterns của **Java 21**, cùng giới hạn khi dùng record cho aggregate có identity hoặc lifecycle phức tạp.

## 2. Phân biệt ba kiểu “nested”

Khi nói “record lồng nhau”, cần tách rõ:

1. **Record component chứa record khác:** `record Customer(CustomerId id, Contact contact)`. Đây là composition của value types.
2. **Khai báo record bên trong class/interface:** `class Demo { record Point(int x, int y) {} }`. Record thành viên là **implicitly static**, không nắm instance của class bao ngoài.
3. **Nested record pattern:** `Customer(CustomerId(var id), Contact(var email))`. Đây là cú pháp dùng trong `instanceof`/`switch` để kiểm tra và deconstruct nhiều tầng.

Ba khái niệm liên quan nhưng không đồng nhất. Một hệ thống có thể dùng các record ở những file riêng, rồi vẫn match nested patterns. Ngược lại, khai báo nhiều record cùng file không tự tạo quan hệ composition nếu component không tham chiếu tới nhau.

**Quy tắc đầu tiên:** bắt đầu từ **quan hệ dữ liệu của nghiệp vụ** rồi mới chọn vị trí khai báo type và cú pháp deconstruction. Đừng tạo một cây record rất sâu chỉ vì Java hỗ trợ nested record patterns.

### Phiên bản Java

- Record classes là tính năng chuẩn từ **Java 16**.
- Type pattern trong `instanceof` cũng chuẩn từ Java 16.
- **Record patterns** và **pattern matching cho `switch`** hoàn chỉnh và chuẩn trong **Java 21** (JEP 440, JEP 441).
- Các ví dụ đầy đủ dưới đây yêu cầu **JDK 21 hoặc mới hơn**, biên dịch bằng `javac --release 21`, **không cần `--enable-preview`**.

## 3. Chọn ranh giới aggregate: Order sở hữu dữ liệu nào?

Trong mô hình đơn hàng, không phải cứ có quan hệ “có liên quan” là nên nhúng nguyên một object vào Order. Hãy phân biệt:

| Thành phần | Ví dụ | Có nên lưu trực tiếp trong Order snapshot? |
| --- | --- | --- |
| Định danh đơn | `OrderId` | Có, là cách nhận diện đơn trong use case |
| Dòng hàng đã chốt | `List<OrderLine>` | Thường có, vì tổng tiền phụ thuộc nội dung đã chốt |
| Giá đơn vị ở thời điểm đặt | `unitPriceVnd` | Thường có trong snapshot, không phụ thuộc giá catalog hiện tại |
| Mã khách hàng | `CustomerId` | Có, liên kết đến khách hàng |
| Email liên hệ của đơn | `Contact` | Có nếu nghiệp vụ cần snapshot tại lúc đặt; chú ý dữ liệu cá nhân |
| Toàn bộ hồ sơ khách hàng sống | `CustomerEntity` trong DB | Không mặc định: có thể chỉ giữ ID hoặc snapshot những trường cần |
| Địa chỉ giao đã xác nhận | `Delivery(Address)` | Có khi giao hàng cần một địa chỉ cụ thể |
| Lịch sử vận chuyển nhiều bước | Tracking events, shipment lifecycle | Thường nên có mô hình/vòng đời riêng |

**Order snapshot không nhất thiết là JPA entity.** Record có value equality theo tất cả component. Nếu một thực thể domain có identity và trạng thái thay đổi qua thời gian, việc dùng `record Order(...)` có thể phù hợp cho **ảnh chụp bất biến** hoặc một DTO domain, nhưng không tự giải quyết transaction, versioning, optimistic locking, lazy loading và ORM mapping.

Ví dụ hai Order có cùng `OrderId` nhưng khác `lines` sẽ **không bằng nhau theo `record.equals` mặc định**, vì equality so sánh tất cả component. Nếu nghiệp vụ coi chúng là **cùng một thực thể** bởi ID, hãy thể hiện distinction ấy ở tầng entity/repository; đừng giả định record mặc định có identity equality.

### Snapshot hóa thông tin khách hàng

Trong ví dụ, `Customer(CustomerId, Contact)` đại diện cho thông tin khách hàng **dùng trong đơn**. Nó không tự đồng bộ với tài khoản khách hàng sau này. Nếu khách cập nhật email, lịch sử đơn cần giữ email lúc đặt hay dùng email hiện tại là **quyết định nghiệp vụ**.

Tên như `CustomerSnapshot` hay `OrderContact` có thể rõ hơn `Customer` trong hệ thống thật. Ví dụ chạy độc lập dùng tên ngắn để tập trung vào nested composition, nhưng cần ghi rõ semantics.

## 4. Chọn kiểu cho từng loại thông tin

Một kiểu dữ liệu có tên giúp đẩy invariant về đúng chỗ:

```java
record OrderId(String value) {}
record CustomerId(String value) {}
record Contact(String email) {}
record Address(String city, String street) {}
record OrderLine(String sku, int quantity, long unitPriceVnd) {}
```

Tại sao không dùng mọi ID là `String`? Với hai record `OrderId` và `CustomerId`, compiler giúp tránh vô tình truyền mã khách vào nơi yêu cầu mã đơn, đồng thời mỗi loại ID có thể có validation hoặc normalization riêng.

Tại sao `OrderLine` là một record thay vì ba danh sách song song? Mỗi dòng buộc **SKU, số lượng, đơn giá** thuộc về cùng một đối tượng. Việc thêm một dòng làm thay đổi một danh sách `List<OrderLine>`, không phải phối hợp ba cấu trúc theo index.

Tại sao `Address` có type riêng? Khi địa chỉ có nhiều field, contract về city/street, quốc gia, postal code, normalization và validation có thể được quản lý ở một nơi. Với hệ thống đa quốc gia, quy tắc địa chỉ cần linh hoạt hơn hai field demo; không nên lấy `city/street` làm schema địa chỉ toàn cầu.

### Dùng kiểu tiền nào?

Ví dụ dùng `long unitPriceVnd`, nghĩa là **số đồng Việt Nam nguyên** cho một đơn vị sản phẩm. Mô hình này phù hợp khi chỉ xử lý VND nguyên, không có phần lẻ. Với đa tiền tệ hoặc precision khác nhau, nên dùng value type như `Money(currency, minorUnits)` với chính sách rõ, không chỉ một `long` mơ hồ.

Không dùng `double` cho tiền nếu nghiệp vụ cần số học chính xác theo đơn vị nhỏ nhất. Dùng `Math.multiplyExact` và `Math.addExact` để tránh overflow âm thầm với `long` trong ví dụ.

## 5. Invariant: record không tự cấm null hoặc dữ liệu sai

Khai báo:

```java
record Address(String city, String street) {}
```

**không tự chặn** `new Address(null, "")`. Record tạo final components và các phương thức cấu trúc, nhưng không biết quy tắc nghiệp vụ. Hãy dùng **compact canonical constructor** khi dữ liệu phải luôn hợp lệ:

```java
record Address(String city, String street) {
    Address {
        city = requireText(city, "city");
        street = requireText(street, "street");
    }
}

static String requireText(String value, String name) {
    java.util.Objects.requireNonNull(value, name);
    String normalized = value.strip();
    if (normalized.isEmpty()) {
        throw new IllegalArgumentException(name + " is blank");
    }
    return normalized;
}
```

Ở đây `requireText` là helper minh họa cần đặt trong một lớp bao ngoài cùng phạm vi truy cập phù hợp. Compact constructor cho phép thay tham số `city`, `street` rồi compiler sẽ gán giá trị cuối vào component fields khi kết thúc bình thường; không viết `this.city = city` trong thân compact constructor.

**Invariants có ích:**

- `OrderId.value` và `CustomerId.value`: không-null, không-blank, được strip khoảng trắng hai đầu.
- `Contact.email`: không-null, không-blank ở ví dụ; **chưa phải validator email chuẩn RFC**.
- `Address.city/street`: không-null, không-blank.
- `OrderLine.sku`: không-null, không-blank; `quantity > 0`; `unitPriceVnd >= 0`.
- `Delivery.address`: không-null.
- `Pickup.storeCode`: không-null, không-blank.
- `Order.id/customer/fulfillment/lines`: không-null; `lines` không rỗng, không có phần tử null.

Đừng nhầm **“đủ điều kiện tạo object”** với **“đã được chấp thuận thanh toán”**. Một Order snapshot có cấu trúc đúng vẫn có thể cần kiểm tra kho, hạn mức, khuyến mại, ủy quyền, idempotency và transaction ở tầng nghiệp vụ khác.

### Null contract và exception

`Objects.requireNonNull(value, "field")` thường ném `NullPointerException` khi argument null. `IllegalArgumentException` phù hợp cho giá trị có mặt nhưng sai miền (chuỗi blank, quantity 0). Không có quy tắc duy nhất bắt buộc mọi domain dùng đúng hai exception ấy; hãy công bố và giữ nhất quán contract API của ứng dụng.

## 6. Biểu diễn Delivery và Pickup bằng sealed variants

Một lỗi mô hình phổ biến:

```java
record Order(
    String id,
    Address shippingAddress,
    String pickupStoreCode
) {}
```

Nếu `shippingAddress == null`, nghĩa là pickup hay thiếu địa chỉ? Nếu cả hai khác null, đơn giao hay nhận? Nếu cả hai null, có hợp lệ? Những trạng thái mơ hồ làm tăng guard và lỗi khi xử lý.

Thay bằng:

```java
sealed interface Fulfillment permits Delivery, Pickup {}

record Delivery(Address address) implements Fulfillment {
    Delivery {
        java.util.Objects.requireNonNull(address, "address");
    }
}

record Pickup(String storeCode) implements Fulfillment {
    Pickup {
        storeCode = requireText(storeCode, "storeCode");
    }
}
```

Giờ contract rất rõ:
- Một `Delivery` hợp lệ **phải có Address**.
- Một `Pickup` hợp lệ **phải có storeCode**.
- `Order.fulfillment` phải là một trong các biến thể permitted, không-null.

Dùng `switch` theo sealed hierarchy:

```java
static String fulfillmentLabel(Fulfillment value) {
    java.util.Objects.requireNonNull(value, "value");
    return switch (value) {
        case Delivery delivery ->
            "Giao tới " + delivery.address().street()
                + ", " + delivery.address().city();
        case Pickup pickup ->
            "Nhận tại " + pickup.storeCode();
    };
}
```

Hai case là **exhaustive** với mọi instance non-null của Fulfillment trong hierarchy hiện tại. Không cần `default`. Khi thêm `LockerDelivery` được permitted, nếu chưa có case bao phủ, compiler sẽ yêu cầu cập nhật `switch expression`.

**Không suy ra rằng `default` luôn bắt selector null** ở enhanced switch. Ví dụ trên từ chối null bằng `requireNonNull` trước khi switch. Nếu hợp đồng khác, có thể dùng `case null` với một kết quả typed phù hợp.

## 7. Thiết kế OrderLine: dữ liệu đi cùng nhau và công thức có kiểm soát

Một dòng hàng cần cả định danh sản phẩm, số lượng và đơn giá tại thời điểm đơn được tạo:

```java
record OrderLine(String sku, int quantity, long unitPriceVnd) {
    OrderLine {
        sku = requireText(sku, "sku");
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity must be positive");
        }
        if (unitPriceVnd < 0) {
            throw new IllegalArgumentException(
                "unitPriceVnd must be non-negative");
        }
    }

    long lineTotalVnd() {
        return Math.multiplyExact(unitPriceVnd, quantity);
    }
}
```

**Vì sao cho phép đơn giá bằng 0?** Demo cho phép hàng tặng miễn phí. Nếu domain không có hàng tặng, có thể yêu cầu giá dương. Không nên đổi chính sách mà không xét yêu cầu nghiệp vụ.

**Vì sao không lưu cả `lineTotal` làm component?** Vì `lineTotal = unitPrice × quantity` có thể được suy ra từ những component kia. Nếu lưu cả hai, phải bảo vệ invariant “lineTotal luôn đúng” mỗi khi tạo snapshot. Với công thức ngắn và thuần, method `lineTotalVnd()` trên record là chấp nhận được.

**Overflow:** `Math.multiplyExact(long, int)` dùng promotion `int` sang `long` rồi phép nhân long; nếu vượt phạm vi `long`, ném `ArithmeticException` thay vì wrap. Trong Java, lời gọi `Math.multiplyExact(unitPriceVnd, quantity)` chọn overload `multiplyExact(long, long)` do đối số `int` được widen sang long. Không tự tin rằng mọi phép cộng số tiền đều an toàn chỉ vì dùng `long`.

Đối với nhiều dòng:

```java
long total = 0;
for (OrderLine line : order.lines()) {
    total = Math.addExact(total, line.lineTotalVnd());
}
```

Đây là code minh họa trong phương thức có `order`. Công thức kiểm soát overflow nhưng **không** tự áp dụng thuế, chiết khấu, phí vận chuyển, tỷ giá hay rounding. Những thứ đó phải có contract và bước tính riêng.

## 8. Bảo vệ danh sách dòng hàng bằng defensive copy

Record component là final nhưng `List` mà nó trỏ tới có thể mutable:

```java
record UnsafeOrder(java.util.List<OrderLine> lines) {}
```

Nếu caller truyền `ArrayList` và sau đó `add/remove`, một `UnsafeOrder` đã tạo vẫn “thay đổi” về mặt giá trị quan sát được. Dùng một snapshot bất biến cấu trúc:

```java
record Order(
    OrderId id,
    Customer customer,
    Fulfillment fulfillment,
    java.util.List<OrderLine> lines
) {
    Order {
        java.util.Objects.requireNonNull(id, "id");
        java.util.Objects.requireNonNull(customer, "customer");
        java.util.Objects.requireNonNull(fulfillment, "fulfillment");
        lines = java.util.List.copyOf(
            java.util.Objects.requireNonNull(lines, "lines"));
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("lines is empty");
        }
    }
}
```

`List.copyOf`:
- Trả một danh sách unmodifiable; caller không thể `add`, `remove` hoặc `clear` qua accessor.
- Không cho các phần tử null.
- Tạo snapshot độc lập với thay đổi cấu trúc của input mutable list.
- Có thể tái sử dụng một instance đã unmodifiable phù hợp; không hứa lúc nào cũng cấp phát danh sách mới.

**Bất biến nông vs sâu:** Trong ví dụ, phần tử là `OrderLine` record chỉ có `String` và primitive, các component của nó ổn định; các subrecord như `CustomerId`, `Contact`, `Address` cũng chứa String nên toàn bộ cây demo là một snapshot có giá trị ổn định. Nếu đổi `OrderLine` thành record chứa `Map<String, MutablePrice>`, `List.copyOf` ở Order **không** làm sâu các object ấy bất biến.

### Thứ tự dòng và ý nghĩa equality

`List.equals` so sánh cả phần tử và thứ tự. Hai đơn có cùng SKU và quantity nhưng thứ tự line khác nhau có thể có `record.equals` khác. Nếu thứ tự là một phần contract in hóa đơn, điều này hợp lý. Nếu nghiệp vụ xem thứ tự không quan trọng, cần quyết định normalization/sắp xếp hoặc cấu trúc dữ liệu khác, không chỉ ghi chú “thứ tự không quan trọng” mà không cài đặt.

### Có nên cấm SKU trùng trong một đơn?

Demo **không** tự cấm hai dòng cùng SKU; một hệ thống có thể cho phép chúng vì khuyến mại, lô hàng hoặc tùy biến khác nhau. Nếu nghiệp vụ buộc mỗi SKU chỉ có một dòng, hãy thêm một invariant có kiểm thử ở constructor/factory hoặc dùng bước normalize danh sách trước khi tạo Order.

## 9. Nested record patterns: đọc từ ngoài vào trong

Java 21 cho phép khớp cấu trúc nhiều tầng:

```java
// Các type trong chương trình đầy đủ được khai báo ở mục 11.
if (value instanceof Order(
        OrderId(var orderId),
        Customer(
            CustomerId(var customerId),
            Contact(var email)),
        Delivery(
            Address(var city, var street)),
        var lines)) {

    System.out.println(orderId + ": " + customerId);
}
```

Đây là **đoạn minh họa trong một phương thức nhận biến `value` kiểu Object**. Cây match tương ứng:

```text
Order
├── OrderId(var orderId)              -> String orderId
├── Customer
│   ├── CustomerId(var customerId)    -> String customerId
│   └── Contact(var email)            -> String email
├── Delivery
│   └── Address
│       ├── var city                  -> String city
│       └── var street                -> String street
└── var lines                         -> List<OrderLine> lines
```

**Ngữ nghĩa:**
1. Input phải là một `Order` không-null.
2. `id` phải khớp `OrderId` không-null, và `value` được gán vào `orderId`.
3. `customer` phải khớp `Customer` không-null; các component bên trong phải khớp tiếp `CustomerId` và `Contact`.
4. `fulfillment` phải khớp biến thể `Delivery`. Một `Pickup` không đi vào nhánh này dù vẫn là Fulfillment hợp lệ.
5. `Delivery.address` phải khớp `Address` không-null; các component city/street được ràng buộc.
6. `lines` được bắt bằng `var`, có kiểu `List<OrderLine>` suy luận từ khai báo record.
7. Nếu một nested record pattern thất bại, **toàn bộ pattern không khớp**.

Trong domain demo, constructor bảo vệ các reference bắt buộc nên một Order tạo hợp lệ có cây dữ liệu non-null theo hợp đồng. Nhưng compiler **không tự sử dụng** các quy tắc runtime trong compact constructor để chứng minh mọi nested component luôn có mặt.

### `var` không phải phép kiểm tra non-null

Nếu dùng một record nhập liệu chưa validate:

```java
record RawOrder(String code, String email) {}

if (value instanceof RawOrder(var code, var email)) {
    // email có thể null, mặc dù kiểu tĩnh là String.
}
```

Record pattern ở tầng ngoài yêu cầu RawOrder không-null, nhưng `var email` có thể ràng buộc null. Ngược lại, `Contact(var email)` **không khớp** khi toàn bộ component Contact là null. Đây là khác biệt quan trọng khi thiết kế nested record và guard `when`.

### Khi guard được đánh giá

`case Order(...nested...) when someCondition -> ...` chỉ xét guard **sau khi toàn bộ nested pattern khớp**. Nếu `fulfillment` là Pickup, guard của nhánh Delivery không chạy. Nếu guard sai, `switch` xét nhánh phù hợp khác.

Một giá trị không thỏa pattern **khác** một giá trị thỏa pattern nhưng guard trả false; khi debug cần biết case được chọn thực sự và nhánh fallback.

## 10. Không nên lồng quá sâu trong mọi case

Nested record pattern rất mạnh nhưng dễ gây **quá nhiều thông tin ở điểm điều phối**.

Ví dụ phần xử lý chỉ cần Order ID và total:

```java
// Không cần mở cây Customer -> Contact -> Delivery -> Address
// nếu công việc chỉ là tính tiền.
long total = orderTotalVnd(order);
```

Nếu viết pattern sâu ở mọi nhánh, một thay đổi như thêm `postalCode` vào `Address` có thể buộc sửa hàng loạt record patterns dù phép tính tiền không liên quan tới địa chỉ.

Các cách giảm độ sâu:

**A. Type pattern ở switch boundary**

```java
return switch (fulfillment) {
    case Delivery delivery -> handleDelivery(delivery);
    case Pickup pickup -> handlePickup(pickup);
};
```

Đây là ví dụ trong một phương thức có hai handler cùng kiểu kết quả. Switch chọn đúng biến thể; handler chịu trách nhiệm xử lý chi tiết.

**B. Record pattern chỉ đến cấp cần thiết**

```java
if (value instanceof Order(
        var id, var customer, Delivery(var address), var lines)) {
    // Chỉ cần biết Delivery và lấy Address.
}
```

**C. Helper có tên nghiệp vụ**

```java
if (order.fulfillment() instanceof Delivery delivery
        && isServiceableAddress(delivery.address())) {
    // Quy tắc có tên, test độc lập.
}
```

`isServiceableAddress` là helper minh họa; với policy đòi I/O, nên thực hiện ở application service trước hoặc tách outcome rõ ràng, không giấu remote call bên trong một guard được kiểm tra nhiều lần.

**Nguyên tắc:** độ sâu của pattern phải phản ánh **cấu trúc thực sự liên quan đến quyết định**. Nếu cần toàn bộ thông tin để tạo hóa đơn, nested pattern ở adapter có thể có giá trị. Nếu chỉ cần tổng số tiền, không nên deconstruct địa chỉ.

## 11. Chương trình Java 21 đầy đủ: đơn hàng nested records

Chương trình sau là **một tệp độc lập**, không cần dependency ngoài. Nó xây các value objects với constructor bảo vệ invariant, dùng sealed fulfillment, sao chép danh sách dòng hàng và minh họa cả `switch` type patterns lẫn nested record patterns.

Tạo file **`NestedOrderRecordDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class NestedOrderRecordDemo {

    static String required(String text, String field) {
        Objects.requireNonNull(text, field);
        String normalized = text.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(field + " is blank");
        }
        return normalized;
    }

    record OrderId(String value) {
        OrderId {
            value = required(value, "orderId");
        }
    }

    record CustomerId(String value) {
        CustomerId {
            value = required(value, "customerId");
        }
    }

    // Demo chỉ kiểm tra email có nội dung;
    // không khẳng định đã validate địa chỉ email theo RFC.
    record Contact(String email) {
        Contact {
            email = required(email, "email");
        }
    }

    // Customer ở đây là snapshot liên hệ dùng trong đơn.
    record Customer(CustomerId id, Contact contact) {
        Customer {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(contact, "contact");
        }
    }

    record Address(String city, String street) {
        Address {
            city = required(city, "city");
            street = required(street, "street");
        }
    }

    sealed interface Fulfillment permits Delivery, Pickup {}

    record Delivery(Address address) implements Fulfillment {
        Delivery {
            Objects.requireNonNull(address, "address");
        }
    }

    record Pickup(String storeCode) implements Fulfillment {
        Pickup {
            storeCode = required(storeCode, "storeCode");
        }
    }

    record OrderLine(String sku, int quantity, long unitPriceVnd) {
        OrderLine {
            sku = required(sku, "sku");
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                    "quantity must be positive");
            }
            if (unitPriceVnd < 0) {
                throw new IllegalArgumentException(
                    "unitPriceVnd must be non-negative");
            }
        }

        long lineTotalVnd() {
            return Math.multiplyExact(unitPriceVnd, quantity);
        }
    }

    // Order là một snapshot bất biến, không phải JPA entity.
    record Order(OrderId id, Customer customer,
                 Fulfillment fulfillment, List<OrderLine> lines) {
        Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(customer, "customer");
            Objects.requireNonNull(fulfillment, "fulfillment");
            lines = List.copyOf(
                Objects.requireNonNull(lines, "lines"));
            if (lines.isEmpty()) {
                throw new IllegalArgumentException("lines is empty");
            }
        }
    }

    static long totalVnd(Order order) {
        Objects.requireNonNull(order, "order");
        long total = 0L;
        for (OrderLine line : order.lines()) {
            total = Math.addExact(total, line.lineTotalVnd());
        }
        return total;
    }

    // Switch exhaustive nhờ sealed Fulfillment.
    static String fulfillmentLabel(Fulfillment fulfillment) {
        Objects.requireNonNull(fulfillment, "fulfillment");
        return switch (fulfillment) {
            case Delivery delivery ->
                "Giao tới " + delivery.address().street()
                    + ", " + delivery.address().city();
            case Pickup pickup ->
                "Nhận tại " + pickup.storeCode();
        };
    }

    // Deconstruction nhiều tầng khi adapter cần toàn bộ cấu trúc.
    static String inspect(Object value) {
        if (value instanceof Order(
                OrderId(var orderId),
                Customer(
                    CustomerId(var customerId),
                    Contact(var email)),
                Delivery(
                    Address(var city, var street)),
                var lines)) {

            return "Đơn " + orderId
                + " | khách " + customerId
                + " | " + email
                + " | giao " + street + ", " + city
                + " | " + lines.size() + " dòng";
        }

        if (value instanceof Order(
                OrderId(var orderId),
                var customer,
                Pickup(var storeCode),
                var lines)) {

            return "Đơn " + orderId
                + " | nhận " + storeCode
                + " | " + lines.size() + " dòng";
        }

        return switch (value) {
            case null -> "Không có dữ liệu";
            case Order order ->
                "Đơn chưa khớp cấu trúc: " + order.id().value();
            default -> "Không phải đơn hàng";
        };
    }

    public static void main(String[] args) {
        Customer customer = new Customer(
            new CustomerId(" C-7 "),
            new Contact(" buyer@example.com "));

        List<OrderLine> sourceLines = new ArrayList<>();
        sourceLines.add(
            new OrderLine(" BOOK-1 ", 2, 120_000));
        sourceLines.add(
            new OrderLine("PEN-1", 3, 10_000));

        Order deliveryOrder = new Order(
            new OrderId(" OD-42 "),
            customer,
            new Delivery(new Address(" Hà Nội ", " Nguyễn Trãi ")),
            sourceLines);

        // Mutate list nguồn sau khi tạo:
        // snapshot trong Order không thay đổi.
        sourceLines.add(
            new OrderLine("EXTRA", 1, 999));

        System.out.println(
            "Mã đơn: " + deliveryOrder.id().value());
        System.out.println(
            "Khách: " + deliveryOrder.customer().id().value());
        System.out.println(
            "Số dòng đã chốt: " + deliveryOrder.lines().size());
        System.out.println(
            "Tổng VND: " + totalVnd(deliveryOrder));
        System.out.println(
            "Fulfillment: "
                + fulfillmentLabel(deliveryOrder.fulfillment()));
        System.out.println(inspect(deliveryOrder));

        Order pickupOrder = new Order(
            new OrderId("OD-43"),
            customer,
            new Pickup(" Q1 "),
            List.of(new OrderLine("PEN-1", 1, 10_000)));

        System.out.println(
            "Pickup: " + fulfillmentLabel(pickupOrder.fulfillment()));
        System.out.println(inspect(pickupOrder));

        try {
            deliveryOrder.lines().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("Danh sách bất biến");
        }

        try {
            new Delivery(null);
        } catch (NullPointerException ex) {
            System.out.println("Thiếu địa chỉ bị từ chối");
        }

        try {
            new OrderLine(" ", 1, 1_000);
        } catch (IllegalArgumentException ex) {
            System.out.println("SKU rỗng bị từ chối");
        }

        System.out.println(inspect(null));
    }
}
```

Biên dịch và chạy từ thư mục chứa file, bằng **JDK 21+**:

```bash
javac --release 21 -encoding UTF-8 NestedOrderRecordDemo.java
java NestedOrderRecordDemo
```

**Đầu ra dự kiến:**

```text
Mã đơn: OD-42
Khách: C-7
Số dòng đã chốt: 2
Tổng VND: 270000
Fulfillment: Giao tới Nguyễn Trãi, Hà Nội
Đơn OD-42 | khách C-7 | buyer@example.com | giao Nguyễn Trãi, Hà Nội | 2 dòng
Pickup: Nhận tại Q1
Đơn OD-43 | nhận Q1 | 1 dòng
Danh sách bất biến
Thiếu địa chỉ bị từ chối
SKU rỗng bị từ chối
Không có dữ liệu
```

### 11.1. Kiểm tra từng kết quả

- `OrderId(" OD-42 ")` được strip thành `"OD-42"`; `CustomerId(" C-7 ")` thành `"C-7"`.
- Dòng BOOK-1: `2 × 120000 = 240000` VND. Dòng PEN-1: `3 × 10000 = 30000` VND. Tổng là `270000` VND.
- Thêm `EXTRA` vào `sourceLines` **sau khi** tạo Order không làm tăng `deliveryOrder.lines().size()`; snapshot có 2 dòng.
- `Delivery(Address)` trả mô tả giao tới địa chỉ đã strip thành `Nguyễn Trãi, Hà Nội`.
- Nested record pattern của `inspect` match `Order -> Customer -> CustomerId/Contact -> Delivery -> Address` và ràng buộc những biến dùng trong dòng mô tả.
- Đơn pickup có `Fulfillment` là `Pickup` nên **không** match pattern chứa `Delivery(...)`; pattern thứ hai chọn biến thể Pickup.
- `List.copyOf` làm `deliveryOrder.lines().clear()` ném `UnsupportedOperationException`.
- `new Delivery(null)` ném `NullPointerException`; `new OrderLine(" ", ...)` ném `IllegalArgumentException` do SKU blank.
- `inspect(null)` không match các nested patterns; nhánh `case null` của switch dự phòng trả `Không có dữ liệu`.

**Không có payment/transaction thật** trong demo. Các phép tính là ví dụ dữ liệu đơn hàng, chưa có thuế, phí vận chuyển, chiết khấu, trạng thái thanh toán hay quản lý tồn kho.

### 11.2. Vì sao code runnable nhưng model vẫn cố ý tối giản?

Cách đặt `Customer` và `Address` là lựa chọn domain demo, không phải schema chuẩn cho mọi hệ thống thương mại. Mô hình thật còn có quốc gia/postal code, giá tại thời điểm đặt, nguồn khuyến mại, currency, VAT, trạng thái đơn và lifecycle. Bài này tập trung **nested composition và pattern matching**, tránh trộn nhiều quy tắc ngoài đề.

### 11.3. Vì sao nested pattern nằm ở `inspect`, không nằm trong `totalVnd`?

`inspect` cần đọc cả ID, customer và destination để tạo một bản tóm tắt có cấu trúc. Khi đó nested deconstruction trực tiếp có ích. Ngược lại `totalVnd` chỉ cần `lines` và giá, nên dùng loop đơn giản. Đây là tiêu chí để **không lạm dụng nested patterns**.

## 12. Kỹ thuật viết `switch` an toàn với nested records

Một `switch` trên Fulfillment sẽ dễ chứng minh exhaustive hơn:

```java
return switch (fulfillment) {
    case Delivery delivery -> describeDelivery(delivery);
    case Pickup pickup -> describePickup(pickup);
};
```

Các handler là minh họa và phải trả kiểu kết quả tương thích. Khi `Delivery` có thông tin `Address` không-null theo constructor, handler có thể tự chọn mức deconstruction cần thiết.

Nếu `switch` trực tiếp trên `Object` với nhiều nested record patterns, cần xét trường hợp pattern **không khớp** do biến thể hoặc nullable component; nên có nhánh xử lý domain rộng hơn và `default` cho kiểu hoàn toàn khác, tùy hợp đồng.

Ví dụ:

```java
// Minh họa: label được gán từ switch expression nhận Object.
String label = switch (value) {
    case null -> "null";
    case Delivery(Address(var city, var street)) ->
        "Giao: " + street + ", " + city;
    case Delivery delivery ->
        "Delivery có cấu trúc địa chỉ không khớp";
    case Pickup(var storeCode) ->
        "Pickup: " + storeCode;
    default -> "Khác";
};
```

Trong hệ demo, constructor `Delivery` chặn null nên nhánh `case Delivery delivery` hiếm khi xảy ra với instance được tạo đúng contract. Nhưng về **ngữ nghĩa pattern**, `Delivery(Address(...))` là trường hợp có nested component phù hợp; compiler không dùng validation constructor để bỏ mọi nhánh fallback.

### Thứ tự cụ thể trước tổng quát

Viết:

```java
case Delivery(Address(var city, var street)) -> "Giao";
case Delivery delivery -> "Delivery khác";
```

là một cách có chủ đích: nhánh cấu trúc cụ thể đứng trước nhánh nhận mọi Delivery. Đảo thứ tự sẽ khiến nhánh nested bị **dominated** bởi `Delivery delivery`, thường bị compiler báo lỗi vì không thể tới.

### Guard và policy null

```java
case Delivery(Address(var city, var street))
        when city != null && !city.isBlank() ->
    "Có thành phố";
```

Guard chỉ được đánh giá khi `Delivery` và `Address` đều khớp record không-null. `var city` có thể nhận null nếu Address được tạo qua một đường không có validation; guard dùng short-circuit an toàn. `case null` cho **selector** là vấn đề khác với component null ở trong cây.

### Record patterns không gọi phép tính tùy ý thay cho bạn

`OrderLine(var sku, var quantity, var price)` chỉ đọc component; nó **không tự gọi** `lineTotalVnd()`. Khi phân loại theo tổng dòng, phải chủ động tính toán ở helper/guard hoặc đưa kết quả vào một object đã đánh giá. Không coi việc deconstruct là tự động thực thi validation hay calculation.

## 13. Điều gì xảy ra khi mô hình đơn hàng thay đổi?

Record component header là một phần của **public API**. Thay đổi:

```java
record Address(String city, String street) {}
```

thành:

```java
record Address(String city, String street, String postalCode) {}
```

ảnh hưởng tới:
- Canonical constructor;
- Accessors, reflection và một số serialization tools;
- Record patterns như `Address(var city, var street)` vì số component phải khớp;
- `equals`/`hashCode` mặc định;
- Các DTO/schema/API contracts nếu được public.

Nếu `Order` lồng toàn bộ Address rồi nhiều use case cũng deconstruct sâu, một thay đổi nhỏ của Address sẽ lan rộng nhiều file. Đó là lý do **không dùng nested pattern ở mọi nơi**.

Các chiến lược:
1. Giữ domain model rõ và có version khi cần thay schema public.
2. Dùng handler/helper theo type pattern khi use case không cần mọi component.
3. Tách mapping boundary từ dữ liệu ngoài sang domain value objects.
4. Không sửa cấu trúc và quy tắc business cùng lúc nếu có thể kiểm chứng riêng.
5. Giữ test hợp đồng cho snapshot cũ/mới và mọi đường deserialize quan trọng.

Không có cơ chế tự động bảo đảm source compatibility cho mọi consumer chỉ vì record là immutable. Record thường thuận tiện cho nội bộ nhưng cần thận trọng khi public API đã có người dùng bên ngoài.

## 14. Serialization và ranh giới dữ liệu thô

Một input JSON từ hệ thống ngoài có thể chứa null, sai kiểu, thiếu lines hoặc số âm. Đừng tin rằng việc deserialize thành record luôn gọi đúng đường validation theo mọi thư viện/cấu hình mà không kiểm tra.

Một pipeline rõ ràng:

```text
HTTP / JSON / Message
         |
         v
RawOrderRequest (nullable DTO)
         |
         v
Parser + validator
         |
         v
OrderId, CustomerSnapshot, Fulfillment, OrderLine
         |
         v
Order snapshot (các invariant đã được bảo vệ)
         |
         v
Business use case / pattern matching / persistence
```

Ở boundary, có thể thu thập lỗi nhiều field cùng lúc thay vì chỉ ném exception đầu tiên. Với domain constructor, fail-fast bảo vệ invariant khi tạo từng value object. Hai tầng có mục tiêu khác nhau và có thể phối hợp.

### Optional field và các biến thể

Không phải mọi component của đơn đều bắt buộc. Ví dụ ghi chú của khách có thể vắng mặt. Có vài thiết kế:
- `String note` nullable, với Javadoc rõ “null nghĩa là không có ghi chú”;
- `Optional<String>` ở return type của API tìm ghi chú khi phù hợp với toolchain;
- Sealed variants nếu “chưa xác nhận”, “khách không cung cấp”, “ẩn bởi chính sách” là **những trạng thái nghiệp vụ khác nhau**.

Đừng nhúng cả chuỗi record mới chỉ vì một field đơn giản có thể null. Chiều sâu của model phải tương xứng với ý nghĩa domain.

### Record và JPA ORM

Nhiều ORM quản lý entity cần identity, lazy loading, mutable lifecycle hoặc proxy. Record không tự phù hợp để thay thế mọi JPA entity theo cách mapping entity truyền thống. Một lựa chọn thực tế là:
- Persistence entity theo yêu cầu ORM;
- Domain immutable snapshot/DTO bằng record;
- Mapping rõ giữa hai dạng.

Đừng gọi một nested Order record là “aggregate root đã đảm bảo transaction” chỉ vì nó chứa toàn bộ state; transaction và concurrency thuộc những tầng có trách nhiệm riêng.

## 15. Tính bất biến và concurrency

Record component fields là final nhưng các component có thể tham chiếu object mutable. Mô hình demo có:
- `String`: immutable;
- `long`/`int`: primitive;
- Các nested records chỉ chứa các giá trị đó hoặc reference đến nested records;
- `List.copyOf`: bảo vệ cấu trúc collection của Order.

Vì vậy cây demo **không có mutable component được lộ ra** và tương đối an toàn để chia sẻ như snapshot. Tuy nhiên không suy diễn rằng **mọi record** có tính bất biến sâu hoặc mọi hệ thống dùng record đều thread-safe.

Nếu lưu:
```java
record Attachment(byte[] data) {}
```

thì mảng có thể bị sửa sau khi tạo và qua accessor. `record.equals` mặc định với array cũng dùng equality của tham chiếu mảng, không so nội dung byte. Muốn value semantics theo nội dung cần clone khi nhận/trả, thiết kế equality/hash tương ứng, hoặc chọn kiểu immutable khác.

Nếu có `List<MutableProduct>`, list unmodifiable vẫn có thể chứa những MutableProduct bị sửa qua tham chiếu khác. **Snapshot toàn vẹn cần xem cả đồ thị object**, không chỉ record gốc.

### Thay đổi đơn hàng bằng cách tạo snapshot mới

Một Order record không có setter. Muốn thêm line sau khi tạo, có thể:
1. Tạo một `ArrayList` mới từ `order.lines()`;
2. Thêm OrderLine mới;
3. Tạo `new Order(order.id(), order.customer(), order.fulfillment(), newLines)`.

Đó là một **snapshot mới**, có thể có cùng OrderId nhưng giá trị record equality khác. Nếu hệ thống có nhiều người chỉnh cùng Order, phải dùng version/optimistic locking hoặc cơ chế đồng bộ ở tầng lưu trữ; immutable snapshot không tự ngăn lost update.

## 16. Unit test cho nested order records

**Kiểm thử constructor invariants:**

| Trường hợp | Kỳ vọng |
| --- | --- |
| `new OrderId(null)` | Ném NPE |
| `new CustomerId("   ")` | Ném IllegalArgumentException |
| `new Delivery(null)` | Ném NPE |
| `new Pickup(" ")` | Ném IllegalArgumentException |
| `new OrderLine("SKU", 0, 100)` | Ném IllegalArgumentException |
| `new OrderLine("SKU", 1, -1)` | Ném IllegalArgumentException |
| `new Order(..., List.of())` | Ném IllegalArgumentException |
| `new Order(..., null)` | Ném NPE |
| `new Order(..., listMutable)`, rồi sửa list nguồn | Snapshot không đổi |

**Kiểm thử pattern matching:**

- Delivery với Address hợp lệ match nested branch đúng, lấy city/street theo đúng thứ tự component.
- Pickup không match nested Delivery branch; match branch Pickup.
- `inspect(null)` trả `Không có dữ liệu`.
- Một `Object` không phải Order trả `Không phải đơn hàng`.
- Nếu một Raw DTO cho phép Contact null, nested `Contact(...)` không match, guard của nhánh đó không chạy.

**Kiểm thử tính toán:**

- Hai dòng `2×120000` và `3×10000` phải cho `270000`.
- Một dòng giá 0 được chấp nhận theo contract demo.
- `unitPriceVnd` rất lớn nhân quantity lớn có thể gây `ArithmeticException`; không được silently overflow.
- Nhiều line có tổng vượt phạm vi long cũng gây `ArithmeticException` qua `Math.addExact`.

**Kiểm thử API evolution:** thêm component `postalCode` của Address cần cập nhật constructor, record patterns, serialization mapping và docs/test. Trường hợp này giúp thấy coupling của nested deconstruction.

### Test equality không đồng nghĩa test identity

Có thể tạo hai `Order` với cùng cấu trúc component để kiểm tra `equals` trả true. Nhưng khi thay một line hoặc Contact, equality mặc định đổi. Nếu repository xem Order bằng nhau khi cùng ID, **đó là quy tắc entity identity riêng**, không nên dùng `record.equals` làm mặc định một cách không suy nghĩ.

## 17. Lỗi thường gặp

| Lỗi | Hệ quả | Giải pháp |
| --- | --- | --- |
| Nhét toàn bộ đơn vào một record phẳng nhiều field nullable | Tạo tổ hợp trạng thái vô nghĩa | Tách thành ID, Contact, Address, Fulfillment, OrderLine |
| Mọi thứ đều lồng record dù không có ý nghĩa domain | Model sâu và API khó đổi | Chỉ tạo value type có invariant hoặc vai trò rõ |
| Tưởng record tự validate null/blank | Có thể tạo object sai domain | Compact constructor/factory có validation |
| Dùng `shippingAddress == null` để suy ra pickup | Không phân biệt missing/khác phương thức | Sealed Fulfillment variants |
| Dùng ba danh sách SKU/qty/price song song | Index lệch, sai giá dòng | `List<OrderLine>` |
| Dùng `List` mutable đưa thẳng vào record | Thay đổi snapshot sau khi tạo | `List.copyOf` trong constructor |
| Nghĩ `List.copyOf` bảo đảm deep immutable | Phần tử mutable vẫn có thể đổi | Immutable elements/deep copy |
| Dùng `double` cho tiền phải chính xác | Lỗi rounding | Long minor units/Money có contract |
| Quên overflow của số tiền | Tổng hoặc tích wrap | `Math.addExact`/`multiplyExact` |
| Nested pattern kiểm tra cả các tầng không cần thiết | Phụ thuộc vào null/cấu trúc thừa | Dùng type pattern hoặc deconstruct vừa đủ |
| Tưởng `var component` luôn khác null | NPE khi gọi method | Xác định null contract, dùng guard an toàn |
| Đặt case rộng trước case nested cụ thể | Nested case bị dominated | Đặt case cụ thể trước |
| Nghĩ guard chạy khi nested pattern fail | Xử lý null sai nhánh | Tách structural match và guard |
| Dùng `default -> 0` để xử lý fulfillment mới | Che thiếu nghiệp vụ | Sealed exhaustive switch, review subtype mới |
| Đồng nhất Order record với JPA aggregate mutable | Sai identity/lifecycle/transaction | Tách snapshot và entity/use case |
| Không tài liệu hóa thứ tự record component | Deconstruction nhầm field cùng kiểu | Đặt tên rõ, viết Javadoc, test |
| Log full `Order.toString()` trong production | Lộ email, địa chỉ, đơn giá | Logging tối thiểu, masking theo chính sách |

## 18. Bài tập thực hành

**Bài 1 — Thiết kế từ mô hình phẳng.** Chuyển `OrderData` ở mục 1 thành các record `OrderId`, `CustomerId`, `Address`, `OrderLine` và `Order`. Nêu invariant thuộc từng record, không chỉ liệt kê field.

**Bài 2 — Thêm ghi chú tùy chọn.** Thêm `note` vào Order snapshot. Quy định null có hợp lệ không, blank có ý nghĩa không, có chuẩn hóa strip không. Viết Javadoc/constructor tương ứng.

**Bài 3 — Fulfillment mới.** Thêm `record LockerPickup(String lockerCode) implements Fulfillment`, cập nhật `permits` và `fulfillmentLabel`. Quan sát compiler báo `switch expression` thiếu case nếu chưa bổ sung. Đặt validation cho lockerCode.

**Bài 4 — Nested pattern.** Với `Order(OrderId(var id), Customer(CustomerId(var cid), Contact(var email)), Delivery(Address(var city, var street)), var lines)`, cho biết biến nào được ràng buộc, kiểu tĩnh là gì và điều gì xảy ra với Pickup.

**Bài 5 — Chỉ deconstruct khi cần.** Viết `totalVnd(Order)` không dùng nested pattern sâu. Giải thích vì sao calculation không nên phụ thuộc Contact hay Address nếu chỉ cần OrderLine.

**Bài 6 — Snapshot.** Chạy chương trình mục 11, thêm phần tử vào `sourceLines` trước/sau khi tạo Order. Quan sát khi nào số dòng đã chốt là 2, khi nào là 3, và lý do cần `List.copyOf`.

**Bài 7 — Overflow.** Tạo `OrderLine("X", 3, Long.MAX_VALUE)`; khi gọi `lineTotalVnd()`, chuyện gì xảy ra? Vì sao không dùng `long total = price * quantity` rồi coi mọi kết quả hợp lệ?

**Bài 8 — Order identity.** Tạo hai Order có cùng `OrderId` nhưng khác Contact email. `equals` mặc định cho kết quả gì? Điều đó có nghĩa hai snapshot là hai đơn hàng khác nhau về identity trong repository không?

**Bài 9 — API evolution.** Thêm `postalCode` vào Address. Đếm các constructor, nested pattern, test và mapper phải cập nhật; đề xuất cách giảm số nơi phụ thuộc component order.

**Bài 10 — Thiết kế giá đa tiền tệ.** Thay `unitPriceVnd` bằng một `Money` record gồm currency và minorUnits. Khi cộng tiền của nhiều OrderLine, cần kiểm tra điều kiện gì để không cộng khác currency?

**Bài 11 — Trạng thái đơn.** Thêm trạng thái `Draft`, `Confirmed`, `Cancelled`. Phân tích nên dùng enum, sealed variants hay entity workflow thay vì nhét status vào một record mà không bảo vệ transition.

**Bài 12 — Dữ liệu cá nhân.** Nếu `Order.toString()` có thể chứa email/địa chỉ, hãy thiết kế chiến lược logging không làm rò rỉ dữ liệu trong production mà vẫn theo dõi được ID giao dịch hợp lệ.

## 19. Tổng kết

**Thiết kế nested record cho đơn hàng** là đưa cấu trúc domain thành **những value object có tên và invariant rõ ràng**, không phải chỉ gộp nhiều field thành một cây record.

Những điểm cốt lõi:

1. Tách `OrderId`, `CustomerId`, `Contact`, `Address`, `OrderLine` và biến thể `Fulfillment` khi từng kiểu có nghĩa riêng.
2. Giữ constructor bảo vệ **non-null, non-blank, quantity, giá, cấu trúc danh sách**; record không tự validate.
3. Dùng `List.copyOf` để snapshot dòng hàng và hiểu giới hạn **shallow immutability**.
4. Dùng sealed `Delivery`/`Pickup` thay vì phụ thuộc vào các cặp nullable field mơ hồ.
5. Dùng nested record patterns khi cần **thật sự đọc nhiều tầng**; type pattern hoặc helper phù hợp hơn cho xử lý hẹp.
6. Phân biệt **pattern fail** với **guard false**; `var` có thể nhận null; case cụ thể đứng trước case rộng.
7. Với tiền, kiểm soát đơn vị, overflow và thời điểm chốt giá.
8. Phân biệt **Order snapshot có record equality** với **aggregate/entity identity và lifecycle** trong hệ thống lưu trữ.
9. Xem thay đổi record header như thay đổi API có thể tác động constructor, record patterns, equality và mapping.

### Tài liệu tham khảo

- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java SE 21 — `List.copyOf`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
- [Java SE 21 — `Math.multiplyExact`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#multiplyExact(long,long))
