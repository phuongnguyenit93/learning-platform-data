# Match cấu trúc order bằng record pattern trong Java 21

## 1. Bài toán: nhìn vào cấu trúc đơn hàng để quyết định xử lý

Một đơn hàng thương mại điện tử có thể gồm nhiều lớp dữ liệu: thông tin khách hàng, dòng sản phẩm, phương thức nhận hàng, địa chỉ và trạng thái thanh toán. Khi cần phân loại một đơn hàng, chương trình không chỉ hỏi “đây có phải `Order` không?” mà còn phải xét **cấu trúc các thành phần nằm trong `Order`**.

Ví dụ: đơn đã thanh toán, thuộc khách VIP và giao tận nhà tại Việt Nam cần một luồng xử lý khác đơn nhận tại cửa hàng. Đơn đang chờ thanh toán chưa được chuyển sang luồng giao hàng. Nếu thiếu khách hàng, sản phẩm, địa chỉ hoặc có tổng tiền bị tràn kiểu số, đơn phải bị từ chối trước khi phân tuyến.

**Record patterns** trong Java 21 cho phép diễn đạt cấu trúc đó trực tiếp trong nhãn `case`:

```java
// Một nhánh minh họa trong switch trên Order:
case Order(
        var id,
        Customer(var customerId, boolean vip),
        Line(var sku, int quantity, long price),
        Home(Address(var city, var country)),
        var status)
        when status == Status.PAID
                && vip
                && "VN".equalsIgnoreCase(country) ->
        "VIP_HOME_VN";
```

Cách đọc từ ngoài vào trong:

1. Selector phải là một `Order`.
2. Component thứ hai phải là `Customer` để lấy `customerId` và `vip`.
3. Component thứ ba phải là `Line` để lấy `sku`, `quantity`, `price`.
4. Component thứ tư phải là `Home` và chứa một `Address` để lấy `city`, `country`.
5. Component cuối là `status`.
6. **Chỉ sau khi các pattern khớp**, guard `when` kiểm tra đơn đã thanh toán, khách VIP và quốc gia là VN.

Điểm mạnh: loại đơn, cấu trúc lồng và điều kiện phân tuyến xuất hiện **ngay trong một case label**, không cần viết nhiều `instanceof` và cast thủ công. Điểm cần cẩn trọng: **record pattern không thay thế validation, null contract hay quy tắc tính tiền**.

**Mốc phiên bản:** `record` là tính năng chuẩn từ Java 16 (JEP 395); `sealed` chuẩn từ Java 17 (JEP 409). **Record patterns** (JEP 440) và **pattern matching for `switch`** (JEP 441) trở thành chuẩn từ **Java 21**. Bài dùng JDK 21+, **không cần `--enable-preview`**.

## 2. Xác định hợp đồng domain trước khi match

Case study sử dụng các data records sau:

| Kiểu | Record components | Vai trò |
| --- | --- | --- |
| `Customer` | `id: String`, `vip: boolean` | Khách đặt hàng và cờ VIP |
| `Line` | `sku: String`, `quantity: int`, `unitPriceCents: long` | **Một** dòng sản phẩm của đơn |
| `Address` | `city: String`, `country: String` | Địa chỉ giao hàng |
| `Home` | `address: Address` | Giao tận nhà |
| `Pickup` | `storeId: String` | Nhận tại cửa hàng |
| `Delivery` | `sealed interface` | Kiểu chung của `Home` và `Pickup` |
| `Status` | `NEW`, `PAID`, `CANCELLED` | Trạng thái thanh toán/xử lý đơn |
| `Order` | `id`, `customer`, `line`, `delivery`, `status` | Tổng hợp cấu trúc của đơn |

Một `Order` trong bài chỉ có **một `Line`**. Đây là giả định để minh họa record pattern lồng nhau, **không phải định nghĩa của mọi hệ thống bán hàng**. Đơn nhiều dòng sẽ cần `List<Line>` hoặc một aggregate khác; record pattern trên `List` không tự destructure từng phần tử.

Để trình bày rõ các đường lỗi, constructor records của ví dụ **chưa validate toàn bộ invariant**. Chúng có thể được tạo với component null hoặc số lượng không hợp lệ; một hàm `valid(Order)` chịu trách nhiệm kiểm tra trước khi phân tuyến. Trong thiết kế domain nghiêm ngặt hơn, có thể validate ở canonical constructor/factory và dùng một DTO riêng để đại diện input chưa đáng tin cậy.

### Quy tắc nghiệp vụ được chọn

Một đơn được xem là hợp lệ về dữ liệu khi:

- `Order.id`, `Customer.id`, `Line.sku` là chuỗi không null, không blank.
- `Customer` và `Line` đều tồn tại.
- `quantity > 0`; `unitPriceCents >= 0`. Giá bằng 0 là hợp lệ, ví dụ hàng tặng; điều này do hợp đồng demo quy định.
- `quantity * unitPriceCents` **không tràn `long`**.
- `delivery` và `status` khác null.
- Với `Home`, `Address` tồn tại, `city`/`country` không null và không blank.
- Với `Pickup`, `storeId` không null và không blank.

Sau khi dữ liệu hợp lệ, thứ tự phân loại là:

| Ưu tiên | Điều kiện | Kết quả |
| --- | --- | --- |
| 1 | Selector `Order` là null | `MISSING_ORDER` |
| 2 | Có component hoặc số tiền không hợp lệ | `INVALID_ORDER` |
| 3 | `status == CANCELLED` | `CANCELLED` |
| 4 | `status == NEW` | `WAITING_PAYMENT` |
| 5 | `PAID` + `Home` + khách VIP + `country = VN` | `VIP_HOME_VN` |
| 6 | `PAID` + `Home` còn lại | `HOME_DELIVERY` |
| 7 | `PAID` + `Pickup` | `PICKUP` |
| 8 | Trạng thái/biến thể hợp lệ nhưng không được định nghĩa | **Báo lỗi thiết kế**, không tự coi là đã thanh toán |

**Vì sao đặt validation trước status?** Với hợp đồng này, `Order` bị thiếu `Line` vẫn là `INVALID_ORDER`, ngay cả khi `status=CANCELLED`. Một domain khác có thể cho phép hủy một draft chưa đủ thông tin. Khi đó cần **thay đổi thứ tự chính sách có chủ đích và cập nhật test**, không chỉ hoán đổi case để “đẹp hơn”.

## 3. Mô hình record và sealed interface

Khai báo các kiểu lồng trong một class Java:

```java
record Customer(String id, boolean vip) {}
record Line(String sku, int quantity, long unitPriceCents) {}
record Address(String city, String country) {}

sealed interface Delivery permits Home, Pickup {}

record Home(Address address) implements Delivery {}
record Pickup(String storeId) implements Delivery {}

enum Status {
    NEW, PAID, CANCELLED
}

record Order(
        String id,
        Customer customer,
        Line line,
        Delivery delivery,
        Status status) {}
```

Những thành phần này có vai trò riêng:

- **Record** là một loại data carrier: compiler tạo canonical constructor, component accessors (`order.customer()`, `line.quantity()`...), `equals`, `hashCode` và `toString` theo quy tắc của record.
- **Sealed interface** giới hạn các implementation trực tiếp của `Delivery` trong trường hợp này về `Home` và `Pickup`. Compiler có thêm thông tin để kiểm tra `switch` exhaustive.
- **Enum** xác định tập trạng thái có tên. Tuy nhiên compiler **không tự chứng minh** các guard như `status == PAID` và `status == NEW` đã bao phủ mọi giá trị enum — guard là điều kiện runtime.
- Các fields record là final về mặt **reference/value**, không tự chứng minh mọi dữ liệu tham chiếu bất biến sâu. Các kiểu lồng trong demo chỉ chứa `String`, primitive và record khác nên không có `List`/mảng mutable.

Không nhất thiết phải dùng một `Order` record nếu chỉ muốn truyền từng field tản mát. Nhưng khi những thành phần luôn cùng nhau mô tả một thực thể, record tạo **schema rõ ràng** cho matching và test.

## 4. Hiểu record pattern qua ba mức trích xuất

### 4.1. Type pattern: chỉ lấy đối tượng

```java
// Minh họa một case trong switch (order):
case Order o -> o.line().quantity();
```

Cách này chỉ xác nhận selector có kiểu `Order` và binding đối tượng `o`. Vẫn phải gọi accessor để đi sâu vào cấu trúc. Phù hợp khi logic phức tạp hoặc cần truyền nguyên `Order` cho service.

### 4.2. Record pattern nông: lấy components trực tiếp

```java
case Order(var id, var customer, var line, var delivery, var status) ->
        id;
```

Các component của `Order` được binding theo **thứ tự khai báo**, không theo tên field được viết lại trong pattern. Kiểu của biến `customer`, `line`, `delivery` được compiler suy luận với `var`. `var` ở đây **không phải wildcard bỏ qua dữ liệu**: nó là một pattern khai báo biến có tên.

Đây là dạng dễ đọc khi muốn lấy nhiều component cấp cao nhưng không cần giải cấu trúc sâu.

### 4.3. Nested record pattern: đi sâu vào cây dữ liệu

```java
case Order(
        var id,
        Customer(var customerId, boolean vip),
        Line(var sku, int quantity, long unitPriceCents),
        Home(Address(var city, var country)),
        var status) ->
        sku + ":" + quantity;
```

Mẫu này trực tiếp lấy `Customer` → `vip`, `Line` → `quantity` và `Home` → `Address` → `country`. Nó cần Java 21 nếu dùng như **record pattern**, không phải chỉ vì model được khai báo là `record`.

**Tránh nhầm lẫn về vị trí:** `Order` khai báo `id, customer, line, delivery, status`; vì thế pattern phải có năm component tương ứng. Một pattern thiếu component hoặc có kiểu không tương thích có thể bị compiler từ chối. Nếu đảo `customer` và `line`, người viết phải sửa pattern cho đúng schema, không thể dựa vào tên biến để compiler “tìm field theo tên”.

### 4.4. Khi không nên lồng quá sâu

Một case chứa nhiều tầng record cộng thêm guard dài có thể khó review hơn helper có tên:

```java
// Một dạng tách điều phối khi logic nghiệp vụ tăng lên:
case Order order -> classifyValidatedOrder(order);
```

`classifyValidatedOrder` trong đoạn trên là tên helper **minh họa**, không phải phương thức có sẵn của Java. Nếu các điều kiện domain dài, hãy giữ `switch` điều phối theo loại và đưa phần quyết định phụ vào helper. Nhưng khi cấu trúc ngắn, như Order/Customer/Line/Home/Address trong một case, nested pattern giúp thể hiện **hợp đồng cấu trúc** rất rõ.

## 5. Null ở từng tầng cấu trúc Order

Trong dữ liệu lồng nhau, cần phân biệt ít nhất bốn mức:

1. **`order == null`**: selector null, có thể xử lý bằng `case null`.
2. **`order.customer() == null`**: selector vẫn là `Order` nhưng nested pattern `Customer(...)` không khớp.
3. **`order.delivery() instanceof Home` nhưng `Home.address() == null`**: nested `Address(...)` không khớp, mặc dù `Home` vẫn tồn tại.
4. **`new Address(null, "VN")`**: record `Address` tồn tại, component `city` là null. `Address(var city,var country)` vẫn có thể binding giá trị null vào `city`; validation/guard quyết định có chấp nhận hay không.

Ví dụ:

```java
// Đoạn này minh họa sự khác nhau về shape:
var missingCustomer = new Order(
        "o-1", null, new Line("book", 1, 500),
        new Pickup("store1"), Status.PAID);

var missingAddress = new Order(
        "o-2", new Customer("c1", true),
        new Line("book", 1, 500),
        new Home(null), Status.PAID);
```

**Không thể** chỉ thêm `case null` để bắt hai tình huống này, vì chính `Order` vẫn khác null. Nếu đặt **chỉ** các nested record patterns mà không có nhánh fallback, một `switch` compiler coi là exhaustive theo kiểu vẫn có thể thất bại ở runtime khi component record lồng null (trong một số cấu trúc có thể ném `MatchException`).

Bài dùng **guard validation trên một `Order` record pattern nông trước** các pattern lồng sâu:

```java
case Order(var id, var customer, var line, var delivery, var status)
        when !valid(order) ->
        "INVALID_ORDER";
```

Do đó dữ liệu sai không bị ép đi qua nested patterns của các nhánh giao hàng. Trong một ứng dụng thực tế, việc reject có cấu trúc ngay ở boundary/constructor cũng là lựa chọn hợp lý.

**Lưu ý:** `case null` ở cấp Order xử lý selector null, còn `valid` chủ động kiểm tra component null. Đây là hai cơ chế khác nhau, không thay thế lẫn nhau.

## 6. Guard `when` và quy tắc ưu tiên

Hai nhánh giao tận nhà:

```java
case Order(
        var id, Customer(var customerId, boolean vip),
        Line(var sku, int quantity, long price),
        Home(Address(var city, var country)), var status)
        when status == Status.PAID
                && vip
                && "VN".equalsIgnoreCase(country) ->
        "VIP_HOME_VN";

case Order(
        var id, Customer(var customerId, boolean vip),
        Line(var sku, int quantity, long price),
        Home(Address(var city, var country)), var status)
        when status == Status.PAID ->
        "HOME_DELIVERY";
```

**Thứ tự có ý nghĩa:** nhánh VIP-VN phải đứng trước nhánh Home tổng quát hơn. Khi cả hai guard cùng đúng, nhánh đầu được chọn. Nếu đảo thứ tự, lệnh có thể đi vào `HOME_DELIVERY` và bỏ qua xử lý ưu tiên VIP.

- `when` chỉ được đánh giá khi record pattern đã khớp.
- `&&` short-circuit; phần `"VN".equalsIgnoreCase(country)` là null-safe ngay cả khi country null vì gọi trên literal.
- Guard nên thuần túy, không gửi notification, ghi database hay thay đổi state. Một guard có thể được thử rồi trả false, khiến case tiếp theo được xét.
- Cả hai nhánh đều kiểm tra `status == PAID`. Nếu chỉ kiểm tra trạng thái ở nhánh VIP, nhánh Home tổng quát có thể nhận một trạng thái mới bổ sung vào enum trong tương lai và **giao hàng nhầm**.
- Nhánh fallback cuối của ví dụ ném lỗi tường minh cho `Order` hợp lệ nhưng **không thuộc bất kỳ chính sách nào đã định**, thay vì tự động xử lý như đơn đã thanh toán.

Không áp dụng “ít guard nhất có thể” một cách máy móc. Mỗi guard phải phản ánh **một ràng buộc nghiệp vụ dễ kiểm tra**.

## 7. Chương trình Java 21 hoàn chỉnh: phân loại và tính tổng tiền đơn hàng

Ví dụ sau chạy độc lập, không cần framework hoặc thư viện ngoài. Nó chứa:

- Kiểu `Order` gồm các records lồng và sealed `Delivery`.
- Validation trước khi phân loại.
- `switch` với **record patterns**, **nested record patterns**, **guard `when`** và `case null`.
- Phân loại đơn chưa thanh toán, đã hủy, VIP giao tận nhà, giao thường và nhận tại cửa hàng.
- Kiểm tra tính toán bằng `Math.multiplyExact` để tránh tràn `long`.
- So sánh record theo giá trị và minh họa tạo bản sao khi cần đổi dữ liệu.
- Test bằng assertions cho **21 trường hợp phân loại**, rồi kiểm tra phép tính, equality, immutability và exception.

Tạo file **`OrderRecordPatternDemo.java`**:

```java
public class OrderRecordPatternDemo {
    record Customer(String id, boolean vip) {}

    record Line(String sku, int quantity, long unitPriceCents) {}

    record Address(String city, String country) {}

    sealed interface Delivery permits Home, Pickup {}

    record Home(Address address) implements Delivery {}

    record Pickup(String storeId) implements Delivery {}

    enum Status { NEW, PAID, CANCELLED }

    record Order(
            String id,
            Customer customer,
            Line line,
            Delivery delivery,
            Status status) {}

    static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    static boolean valid(Order order) {
        if (order == null || !hasText(order.id())) {
            return false;
        }

        Customer customer = order.customer();
        Line line = order.line();
        Delivery delivery = order.delivery();

        if (customer == null || !hasText(customer.id())) {
            return false;
        }

        if (line == null || !hasText(line.sku())
                || line.quantity() <= 0
                || line.unitPriceCents() < 0) {
            return false;
        }

        if (delivery == null || order.status() == null) {
            return false;
        }

        try {
            Math.multiplyExact(
                    (long) line.quantity(),
                    line.unitPriceCents());
        } catch (ArithmeticException ex) {
            return false;
        }

        return switch (delivery) {
            case Home(var address) ->
                    address != null
                            && hasText(address.city())
                            && hasText(address.country());

            case Pickup(var storeId) ->
                    hasText(storeId);
        };
    }

    static String route(Order order) {
        return switch (order) {
            case null ->
                    "MISSING_ORDER";

            case Order(
                    var id, var customer, var line,
                    var delivery, var status)
                    when !valid(order) ->
                    "INVALID_ORDER";

            case Order(
                    var id, var customer, var line,
                    var delivery, var status)
                    when status == Status.CANCELLED ->
                    "CANCELLED";

            case Order(
                    var id, var customer, var line,
                    var delivery, var status)
                    when status == Status.NEW ->
                    "WAITING_PAYMENT";

            case Order(
                    var id,
                    Customer(var customerId, boolean vip),
                    Line(var sku, int quantity, long price),
                    Home(Address(var city, var country)),
                    var status)
                    when status == Status.PAID
                            && vip
                            && "VN".equalsIgnoreCase(country) ->
                    "VIP_HOME_VN";

            case Order(
                    var id,
                    Customer(var customerId, boolean vip),
                    Line(var sku, int quantity, long price),
                    Home(Address(var city, var country)),
                    var status)
                    when status == Status.PAID ->
                    "HOME_DELIVERY";

            case Order(
                    var id,
                    Customer(var customerId, boolean vip),
                    Line(var sku, int quantity, long price),
                    Pickup(var storeId),
                    var status)
                    when status == Status.PAID ->
                    "PICKUP";

            case Order(
                    var id, var customer, var line,
                    var delivery, var status) ->
                    throw new IllegalStateException(
                            "unexpected valid order");
        };
    }

    static long totalCents(Order order) {
        if (!valid(order)) {
            throw new IllegalArgumentException("invalid order");
        }

        return switch (order) {
            case Order(
                    var id,
                    var customer,
                    Line(var sku, int quantity, long price),
                    var delivery,
                    var status) ->
                    Math.multiplyExact((long) quantity, price);
        };
    }

    static void check(
            String label, Order order, String expected) {
        String actual = route(order);

        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + ": expected " + expected
                            + " got " + actual);
        }

        System.out.println(label + " => " + actual);
    }

    public static void main(String[] args) {
        var customer = new Customer("c1", true);
        var standard = new Customer("c2", false);
        var line = new Line("book", 2, 1_250);

        var vn = new Home(new Address("Ha Noi", "VN"));
        var foreign = new Home(new Address("Paris", "FR"));

        Order paid = new Order(
                "o-1", customer, line, vn, Status.PAID);

        check("vip-vn", paid, "VIP_HOME_VN");

        check("standard-vn",
                new Order("o-2", standard, line, vn, Status.PAID),
                "HOME_DELIVERY");

        check("vip-foreign",
                new Order(
                        "o-3", customer, line, foreign, Status.PAID),
                "HOME_DELIVERY");

        check("pickup",
                new Order(
                        "o-4", customer, line,
                        new Pickup("store7"), Status.PAID),
                "PICKUP");

        check("waiting",
                new Order("o-5", customer, line, vn, Status.NEW),
                "WAITING_PAYMENT");

        check("cancelled",
                new Order(
                        "o-6", customer, line, vn, Status.CANCELLED),
                "CANCELLED");

        check("null-order", null, "MISSING_ORDER");

        check("null-customer",
                new Order("o-7", null, line, vn, Status.PAID),
                "INVALID_ORDER");

        check("blank-id",
                new Order(" ", customer, line, vn, Status.PAID),
                "INVALID_ORDER");

        check("null-line",
                new Order("o-8", customer, null, vn, Status.PAID),
                "INVALID_ORDER");

        check("zero-qty",
                new Order(
                        "o-9", customer,
                        new Line("book", 0, 50),
                        vn, Status.PAID),
                "INVALID_ORDER");

        check("negative-price",
                new Order(
                        "o-10", customer,
                        new Line("book", 2, -1),
                        vn, Status.PAID),
                "INVALID_ORDER");

        check("overflow",
                new Order(
                        "o-11", customer,
                        new Line("book", 2, Long.MAX_VALUE),
                        vn, Status.PAID),
                "INVALID_ORDER");

        check("null-address",
                new Order(
                        "o-12", customer, line,
                        new Home(null), Status.PAID),
                "INVALID_ORDER");

        check("null-city",
                new Order(
                        "o-13", customer, line,
                        new Home(new Address(null, "VN")),
                        Status.PAID),
                "INVALID_ORDER");

        check("blank-country",
                new Order(
                        "o-14", customer, line,
                        new Home(new Address("Hue", " ")),
                        Status.PAID),
                "INVALID_ORDER");

        check("blank-store",
                new Order(
                        "o-15", customer, line,
                        new Pickup(" "), Status.PAID),
                "INVALID_ORDER");

        check("null-delivery",
                new Order(
                        "o-16", customer, line, null, Status.PAID),
                "INVALID_ORDER");

        check("null-status",
                new Order(
                        "o-17", customer, line, vn, null),
                "INVALID_ORDER");

        check("blank-sku",
                new Order(
                        "o-18", customer,
                        new Line(" ", 1, 10),
                        vn, Status.PAID),
                "INVALID_ORDER");

        check("country-case",
                new Order(
                        "o-19", customer, line,
                        new Home(new Address("Hanoi", "vn")),
                        Status.PAID),
                "VIP_HOME_VN");

        System.out.println("total=" + totalCents(paid));

        System.out.println("records-equal="
                + paid.equals(
                        new Order(
                                "o-1",
                                new Customer("c1", true),
                                new Line("book", 2, 1_250),
                                new Home(
                                        new Address("Ha Noi", "VN")),
                                Status.PAID)));

        Order changed = new Order(
                paid.id(),
                paid.customer(),
                new Line("book", 3, 1_250),
                paid.delivery(),
                paid.status());

        System.out.println(
                "original-quantity=" + paid.line().quantity()
                        + " new-quantity="
                        + changed.line().quantity());

        try {
            totalCents(
                    new Order(
                            "bad", customer,
                            new Line("x", 0, 10),
                            vn, Status.PAID));
            throw new AssertionError("expected invalid order");
        } catch (IllegalArgumentException expected) {
            System.out.println(
                    "invalid-total=IllegalArgumentException");
        }
    }
}
```

Biên dịch/chạy với **JDK 21 hoặc mới hơn**:

```bash
javac --release 21 OrderRecordPatternDemo.java
java OrderRecordPatternDemo
```

**Stdout chính xác:**

```text
vip-vn => VIP_HOME_VN
standard-vn => HOME_DELIVERY
vip-foreign => HOME_DELIVERY
pickup => PICKUP
waiting => WAITING_PAYMENT
cancelled => CANCELLED
null-order => MISSING_ORDER
null-customer => INVALID_ORDER
blank-id => INVALID_ORDER
null-line => INVALID_ORDER
zero-qty => INVALID_ORDER
negative-price => INVALID_ORDER
overflow => INVALID_ORDER
null-address => INVALID_ORDER
null-city => INVALID_ORDER
blank-country => INVALID_ORDER
blank-store => INVALID_ORDER
null-delivery => INVALID_ORDER
null-status => INVALID_ORDER
blank-sku => INVALID_ORDER
country-case => VIP_HOME_VN
total=2500
records-equal=true
original-quantity=2 new-quantity=3
invalid-total=IllegalArgumentException
```

Chương trình minh họa được kiểm tra bằng **JDK 24 JShell** với ngôn ngữ Java 21: 21 tình huống phân loại cùng các dòng kiểm tra tổng tiền, equals, tạo bản sao và exception. Phần guard `status == PAID` đã được kiểm tra riêng bằng một phiên bản enum bổ sung `REFUNDED`: trạng thái mới không được phân tuyến như đơn đã thanh toán mà đi vào nhánh lỗi tường minh.

**Phạm vi thực thi:** `route` chỉ trả mã phân loại; nó **không tự gửi hàng, trừ tiền, gọi database hoặc chuyển trạng thái**. Đây là một quyết định có chủ đích để ví dụ tập trung vào match cấu trúc. Trong hệ thống thật, sau khi có mã phân tuyến có thể giao cho các handler/service tương ứng, với transaction và authorization phù hợp.

## 8. Giải thích luồng matching cho từng nhóm case

### 8.1. Null và invalid được kiểm tra trước

Với `null`, nhánh `case null` trả `MISSING_ORDER`; các record patterns không được thử như thể có một Order hợp lệ.

Với `new Order("o-7", null, line, vn, PAID)`, nhánh:

```java
case Order(var id, var customer, var line, var delivery, var status)
        when !valid(order) -> "INVALID_ORDER";
```

khớp **Order bên ngoài**, rồi `valid` thấy `customer == null` và trả false. Không cần thử `Customer(...)` lồng sâu khi dữ liệu đã không hợp lệ. Đây là cách phân tầng dễ debug.

### 8.2. Đơn mới và đã hủy

Sau khi validation pass, hai guard điều hướng:

```java
case Order(var id, var c, var l, var d, var status)
        when status == Status.CANCELLED ->
        "CANCELLED";

case Order(var id, var c, var l, var d, var status)
        when status == Status.NEW ->
        "WAITING_PAYMENT";
```

Đây là **các mảnh case label**, không phải một chương trình độc lập. Đơn mới chưa được coi là đủ điều kiện giao. Với hợp đồng đã nêu, trạng thái hủy nhưng thiếu dữ liệu cũng bị xem là `INVALID_ORDER` vì validation đứng trước.

### 8.3. Home có nested Address, Pickup có storeId

Home:

```java
Home(Address(var city, var country))
```

khác Pickup:

```java
Pickup(var storeId)
```

Khi ở cùng vị trí thứ tư của `Order`, hai record patterns loại trừ nhau theo subtype `Delivery`. Một đơn Pickup hợp lệ sẽ không bao giờ khớp Home; thứ tự của Home và Pickup không quan trọng về kiểu, nhưng thứ tự **hai Home guarded cases** rất quan trọng.

Với `new Home(null)`, Home record tồn tại nhưng nested `Address(...)` không khớp. Vì vậy validation/fallback phải đảm bảo không để case bị bỏ qua bất ngờ.

### 8.4. Kiểm tra country bằng literal

`"VN".equalsIgnoreCase(country)` xử lý `"vn"` như `"VN"`; đó là **hợp đồng chủ đích của demo**. Với hệ thống quốc tế thật, country thường nên lưu **mã quốc gia chuẩn hóa** (ví dụ ISO 3166-1 alpha-2), phân biệt giữa display name và code, và validate theo danh sách chấp nhận; `equalsIgnoreCase` không tự validate độ dài hay tính hợp lệ của mọi mã.

Đồng thời phải xác định chính sách ưu tiên VIP: nếu một khách VIP ở nước khác thì demo trả `HOME_DELIVERY`, không phải `VIP_HOME_VN`.

### 8.5. Tại sao có nhánh throw cuối?

```java
case Order(var id, var customer, var line, var delivery, var status) ->
        throw new IllegalStateException("unexpected valid order");
```

Guard `when` không tự chứng minh hết các giá trị `Status` có thể gặp. Nếu sau này enum thêm `REFUNDED` và đơn vẫn hợp lệ, ba nhánh `PAID`, `NEW`, `CANCELLED` không bao phủ trạng thái mới. Nhánh throw cuối giúp báo **logic domain cần cập nhật**, thay vì âm thầm đưa đơn refunded vào luồng giao hàng.

Một hệ thống production có thể chọn mã kết quả `UNSUPPORTED_STATUS` hoặc sealed outcome thay vì throw, nhưng phải quyết định **theo hợp đồng**, và có test/migration cho trạng thái mới.

## 9. Tổng tiền: tránh lỗi số học khi order có cấu trúc đúng

Dữ liệu “đúng kiểu” chưa đồng nghĩa phép nhân an toàn.

Với một dòng sản phẩm:

\[
\text{totalCents} = \text{quantity}\times\text{unitPriceCents}
\]

Đoạn:

```java
return switch (order) {
    case Order(
            var id,
            var customer,
            Line(var sku, int quantity, long price),
            var delivery,
            var status) ->
            Math.multiplyExact((long) quantity, price);
};
```

được dùng trong method sau khi `valid(order)` pass. `Math.multiplyExact` ném `ArithmeticException` khi phép nhân có dấu vượt miền của `long`. Trong `valid`, exception dự kiến này được catch và biến thành **invalid input** trước khi phân loại; trong `totalCents` cũng dùng `multiplyExact` để giữ bảo vệ.

**Ví dụ:**

- `quantity=2`, `unitPriceCents=1250` → `total=2500`.
- `quantity=0` → không hợp lệ theo quy tắc demo.
- `unitPriceCents=-1` → không hợp lệ.
- `quantity=2` và `unitPriceCents=Long.MAX_VALUE` → phép nhân tràn, không được wrap thành số âm.

Nếu có **nhiều dòng** hàng, phải tính tổng qua các dòng với `Math.addExact` và xử lý quy tắc thuế, chiết khấu, currency, rounding, refund và quantity phù hợp. Không dùng `double` cho tiền thật nếu cần giá trị chính xác theo đơn vị nhỏ nhất. Demo dùng `long cents` với một loại đơn vị giả định; bản thân nó **không phải một hệ thống thanh toán an toàn**.

### Ranh giới giữa validation và tính tiền

Hàm `valid` kiểm tra `Math.multiplyExact` để từ chối các đơn có tổng tràn. `totalCents` tính lại trên một `Order` đã hợp lệ. Đây là ví dụ nhỏ, thuần dữ liệu nên chi phí không đáng kể; với đơn nhiều dòng và dữ liệu lớn, có thể chuyển sang một kiểu `ValidatedOrder`/`PricingResult` để **chỉ kiểm tra một lần** và truyền các giá trị đã tính được. Tránh lưu trữ tổng tiền bị trùng với dữ liệu nguồn mà không có cơ chế giữ nhất quán.

## 10. Record equality và tạo bản sao khi sửa đơn

Hai `Order` có toàn bộ record components tương ứng giống nhau sẽ `equals` theo **value semantics**:

```java
var first = new Order(
        "o-1", new Customer("c1", true),
        new Line("book", 2, 1250),
        new Home(new Address("Ha Noi", "VN")),
        Status.PAID);

var second = new Order(
        "o-1", new Customer("c1", true),
        new Line("book", 2, 1250),
        new Home(new Address("Ha Noi", "VN")),
        Status.PAID);

System.out.println(first.equals(second)); // true
```

`record` sinh canonical constructor và accessor, nhưng **không sinh wither** hoặc setter như `withLine(...)`. Khi cần thay số lượng, tạo một Order mới với Line mới:

```java
Order changed = new Order(
        first.id(),
        first.customer(),
        new Line("book", 3, 1250),
        first.delivery(),
        first.status());
```

Order `first` không bị đột biến. Điều này dễ test và phù hợp một số hệ thống xử lý dữ liệu bất biến.

**Tuy nhiên:** record chỉ đảm bảo các component fields là final, **không bảo đảm bất biến sâu** khi component là mảng/list hoặc object mutable. Trong mô hình hiện tại, các kiểu lồng là records và chuỗi/enum/primitive nên an toàn hơn, nhưng nếu sau này thay `Line` bằng `List<Line>`, cần `List.copyOf`/defensive-copy và thiết kế constructor/accessor phù hợp.

**Value equality khác identity của đơn hàng:** Domain có thể xem hai phiên bản Order có cùng `id` là cùng một entity dù khác trạng thái hoặc tổng tiền. `record.equals` lại so sánh **tất cả components**. Nếu cần entity identity và lifecycle phức tạp, nên tách `OrderSnapshot` record (giá trị) khỏi `OrderEntity` (identity, persistence, version), thay vì ép `record.equals` đại diện mọi quan hệ đồng nhất nghiệp vụ.

## 11. Khi thêm nhiều line items, nested record pattern sẽ thay đổi thế nào?

Order thực tế có thể dùng:

```java
// Schema minh họa cho phiên bản khác:
record MultiLineOrder(
        String id,
        Customer customer,
        java.util.List<Line> lines,
        Delivery delivery,
        Status status) {}
```

`record pattern` có thể lấy `lines` như một component:

```java
case MultiLineOrder(var id, var customer, var lines, var delivery, var status)
        -> ...;
```

Nhưng cú pháp Java 21 **không tự động destructure `List`** như cú pháp sequence patterns trong một số ngôn ngữ khác. Không viết `case MultiLineOrder(..., List(Line(...), Line(...)),...)` như thể Java 21 có list patterns.

Hướng giải quyết:

1. Dùng record pattern để lấy `List<Line> lines`.
2. Validate nonnull, size, từng Line, quantity và price.
3. Duyệt danh sách bằng `for`/streams có xử lý `Math.multiplyExact` và `Math.addExact`.
4. Nếu cần pattern match từng phần tử, dùng `switch(line)` hoặc `instanceof` trong loop.
5. Không tự thay thế biến mutable list vào một record mà tin là đã thành immutable.

**Type erasure:** Pattern `List<String>` từ một `Object` không thể chứng minh tất cả element là String chỉ bằng runtime generic pattern. Với List<Line>, phải dựa trên type boundary/validation hoặc kiểm tra từng phần tử khi dữ liệu chưa đáng tin cậy.

## 12. Bốn cách dùng pattern trong ứng dụng Order

### 12.1. `instanceof` pattern cho một nhánh đơn giản

```java
if (order.delivery() instanceof Pickup pickup) {
    System.out.println(pickup.storeId());
}
```

Đây là lựa chọn tốt khi chỉ cần một nhánh. Pattern matching for `instanceof` đã final từ Java 16. Nếu `order` có thể null, phải bảo vệ `order` trước khi gọi accessor.

### 12.2. Type pattern trong switch

```java
return switch (delivery) {
    case Home home -> "HOME";
    case Pickup pickup -> "PICKUP";
};
```

Đoạn minh họa giả định `delivery` là một `Delivery` khác null. Với sealed hierarchy có hai subtype, compiler kiểm tra exhaustive. Null selector cần chính sách riêng nếu dữ liệu có thể null.

### 12.3. Record pattern trong switch

```java
return switch (delivery) {
    case Home(Address(var city, var country)) ->
            "HOME:" + country;
    case Pickup(var storeId) ->
            "STORE:" + storeId;
    case Home(var address) ->
            "HOME_WITHOUT_ADDRESS";
    case null ->
            "MISSING_DELIVERY";
};
```

Đây là một **đoạn biểu thức minh họa** trong method có biến `delivery` kiểu `Delivery`. Nhánh `Home(var address)` xử lý Home chứa Address null, đặt sau Home record pattern cụ thể. Trong code thực tế, có thể validate city/country thay vì trả string thô.

### 12.4. Guard `when` để diễn đạt chính sách phân tuyến

Nếu có một điều kiện ngắn theo nghiệp vụ, guarded record pattern có thể dễ đọc:

```java
case Order(var id, var c, var l, Home(var address), var status)
        when status == Status.PAID ->
        "PAID_HOME";
```

Nếu điều kiện dài và có nhiều rule liên quan, hãy tạo helper như `eligibleForVipShipping(order)`, không nhét phép gọi service có side effect vào guard. Cân nhắc trade-off giữa độ sâu nesting và số lần phải điều hướng sang method khác.

## 13. Phân biệt tính đúng của record pattern với business validation

Record pattern **không tự** kiểm tra rằng:

- `id` là mã đơn tồn tại trên database.
- `Customer` thực sự được xác thực hoặc có quyền thao tác.
- `unitPriceCents` phù hợp bảng giá hiện tại.
- `status == PAID` được xác nhận bởi cổng thanh toán.
- Địa chỉ có thật hoặc nằm trong vùng dịch vụ.
- `Home` và `Pickup` có các điều kiện riêng về phí/vận chuyển.
- Các field được tạo từ JSON/DTO đã vượt qua schema versioning.

Những điều đó cần tầng validation, authorization, inventory và payment thích hợp. `route` trong demo chỉ **đọc dữ liệu** và trả nhóm xử lý; không được coi là giấy phép giao hàng thực sự.

Một lỗi nguy hiểm là đưa thao tác cập nhật database vào `when`:

```java
// Anti-pattern minh họa, KHÔNG dùng:
// case Order o when chargeCard(o) -> "PAID";
```

Nếu `chargeCard(o)` gây side effect rồi trả `false`, switch có thể xét nhánh sau trong khi tiền đã bị trừ. Guard nên là **predicate thuần túy** trên dữ liệu đã xác minh. Side effect phải nằm trong handler đã chọn, được bảo vệ bởi transaction/idempotency/authorization khi cần.

## 14. Test cho record patterns: bao phủ cấu trúc, guard và null

Từ chương trình mẫu có thể xây ma trận:

| Nhóm | Input cần test | Kết quả |
| --- | --- | --- |
| Selector | `null` | `MISSING_ORDER` |
| Cấu trúc khách | `Customer=null`, `Customer.id` blank | `INVALID_ORDER` |
| Cấu trúc sản phẩm | `Line=null`, `sku` blank, `quantity=0` | `INVALID_ORDER` |
| Giá trị số | `price < 0`, nhân tràn `long` | `INVALID_ORDER` |
| Giao tại nhà | `Home(null)`, `Address.city=null`, `country` blank | `INVALID_ORDER` |
| Nhận tại cửa hàng | `Pickup(" ")` | `INVALID_ORDER` |
| Trạng thái | `status=null` | `INVALID_ORDER` |
| Chưa thanh toán | `Status.NEW` trên Order hợp lệ | `WAITING_PAYMENT` |
| Đã hủy | `Status.CANCELLED` trên Order hợp lệ | `CANCELLED` |
| Giao VIP | `Customer.vip=true`, `country=VN`, `status=PAID` | `VIP_HOME_VN` |
| Giao thường | Khách thường VN hoặc VIP nước khác | `HOME_DELIVERY` |
| Nhận hàng | `Pickup("store7")` + `PAID` | `PICKUP` |
| Case-insensitive | `country="vn"` | `VIP_HOME_VN` |
| Equality | Hai Order có components tương đương | `equals == true` |
| Sao chép | Order thay Line bằng record mới | Order cũ không đổi |

Một **property-based test** có thể sinh các kết hợp của `Status` × `Delivery` × `Customer.vip` × `country` × `quantity`, chú trọng giá trị biên. Các property hữu ích:

- **Totality trên miền đã định nghĩa:** với `Order` hợp lệ của ba trạng thái hiện có, `route` trả đúng một mã hợp lệ.
- **Không phân tuyến giao hàng trước thanh toán:** `NEW` hoặc `CANCELLED` không được trả `HOME_DELIVERY`, `VIP_HOME_VN` hay `PICKUP`.
- **Không bỏ qua validation:** Order thiếu bất kỳ component bắt buộc nào không được đi vào handler giao.
- **Metamorphic:** thay `id` từ một chuỗi hợp lệ sang chuỗi hợp lệ khác không đổi nhóm phân tuyến khi mọi điều kiện khác giữ nguyên.
- **Số học:** tổng tiền phải là phép nhân an toàn, không có overflow/wrap-around.

Nếu có refactor từ `if instanceof/cast` sang `switch`, so sánh kết quả với một oracle độc lập viết theo bảng nghiệp vụ, nhưng đừng chỉ so sánh output nếu có thêm side effect, exception hoặc database writes.

### Vì sao kiểm thử phải đi sâu hơn hai nhánh Home và Pickup?

Compiler biết `Delivery` được sealed, nhưng không biết nội dung `Address` là hợp lệ hoặc null. Compiler cũng không xác thực rằng tất cả các giá trị trạng thái đều đã đi qua đúng guard. Vì vậy **compile success khác với business completeness**. Test phải đi qua các giá trị null ở **mọi tầng** và các điều kiện Boolean quanh ranh giới.

## 15. Những lỗi thường gặp

1. **Nhầm record pattern với record declaration:** có `record Order(...)` từ Java 16 không có nghĩa `case Order(...)` final ở Java 16; record patterns final từ Java 21.
2. **Sai thứ tự components trong pattern:** compiler dùng thứ tự canonical components, không tìm theo tên biến.
3. **Cho rằng `var x` bỏ qua mọi giá trị:** đây là binding pattern có kiểu suy luận; người viết có thể dùng nó ở guard/thân nhánh.
4. **Cho rằng nested `Address(...)` khớp `Address=null`:** không; cần validation hoặc fallback ở đúng tầng.
5. **Quên `case null` cho selector Order:** có thể nhận `NullPointerException`, không được hiểu `default` là null fallback.
6. **Đặt nhánh Home tổng quát trước nhánh VIP Home:** che chính sách ưu tiên hoặc khiến case sau bị dominated.
7. **Không kiểm tra `Status.PAID` ở tất cả nhánh giao hàng:** trạng thái mới có thể vô tình được phân tuyến như đã thanh toán.
8. **Coi sealed hierarchy tự kiểm tra hết các guard:** exhaustiveness về **type** không chứng minh hết các trường hợp nghiệp vụ.
9. **Chỉ kiểm tra kiểu Line, không kiểm tra quantity/price:** record pattern không tự thực thi validation nghiệp vụ.
10. **Nhân quantity × price bằng `*` và bỏ qua overflow:** có thể thu được một số âm sai.
11. **Trộn cents với các đơn vị tiền khác nhau:** cần mô hình currency/precision rõ ràng.
12. **Dùng record có `List` mutable mà coi là bất biến sâu:** có nguy cơ dữ liệu thay đổi sau khi được validate.
13. **Nhét database I/O vào `when`:** guard có thể chạy mà nhánh không được chọn, gây side effect ngoài ý muốn.
14. **Cho phép `Order` bị hủy thiếu dữ liệu nhưng không thay chính sách:** với bài này, validation được ưu tiên trước CANCELLED; yêu cầu khác phải được thể hiện bằng thiết kế/test.
15. **Thêm `default -> "OK"` vào exhaustive switch để hết báo lỗi:** có thể che subtype hoặc status mới chưa được xử lý.
16. **Dùng `equals` để thay thế định danh entity:** record value equality có thể khác với “cùng order id” ở domain.
17. **Tưởng rằng `record` tự giải quyết JSON deserialization/schema:** mapping và backward compatibility thuộc tầng khác.
18. **Giấu quy tắc quá nhiều trong một case label:** cấu trúc lồng sâu + guard dài có thể kém đọc hơn helper có tên rõ.
19. **Bắt mọi `RuntimeException` và coi là invalid order:** có thể che bug lập trình, lỗi hạ tầng hoặc MatchException bất thường.
20. **Trộn phân loại đơn với thực thi giao dịch:** `route` không phải bằng chứng đủ để giao hàng/thanh toán.

## 16. Bài tập mở rộng

**Bài 1 — Đơn nhiều dòng:** đổi `Line line` thành `List<Line> lines`; viết validation từng dòng và `Math.addExact` cho tổng tiền. Thêm test cho danh sách rỗng/null và dòng giá trị sai.

**Bài 2 — Thêm trạng thái `REFUNDED`:** cập nhật enum và chạy lại logic phân loại. Định nghĩa một nhánh riêng trả `REFUNDED` hoặc một mã nghiệp vụ rõ ràng, không để rơi vào Home/Pickup. Chứng minh bằng test input đã thanh toán trước đó nhưng nay refunded.

**Bài 3 — Nhận hàng tại cửa hàng:** bổ sung thông tin giờ nhận hàng và validate ngày/giờ. Cân nhắc record mới `Pickup(String storeId, LocalDateTime slot)` và tác động lên các pattern đang destructure Pickup.

**Bài 4 — Địa chỉ không thuộc vùng giao:** thêm rule `isServiceable(Address)` dạng pure predicate; phân biệt lỗi dữ liệu không hợp lệ với địa chỉ hợp lệ nhưng ngoài vùng hỗ trợ.

**Bài 5 — Đổi thành DTO/domain tách biệt:** tạo `OrderRequest` cho raw input chưa validate và `ValidatedOrder` cho dữ liệu đã qua validation. So sánh độ rõ ràng của switch khi domain type bảo đảm component không null.

## 17. Checklist code review

- [ ] `Order` record có đúng component, thứ tự và kiểu theo schema đã định?
- [ ] Các record con (`Customer`, `Line`, `Home`/`Pickup`, `Address`) có bất biến/validation rõ ràng?
- [ ] Nested record patterns có thật sự giúp thể hiện cấu trúc nghiệp vụ thay vì làm case label quá sâu?
- [ ] `when` kiểm tra đúng `PAID`, VIP và địa chỉ/quốc gia, không gọi phương thức side effect?
- [ ] Thứ tự VIP Home trước Home tổng quát có được giữ?
- [ ] Selector null và component null ở từng tầng đã được xử lý đúng?
- [ ] Sealed `Delivery` và enum `Status` có kế hoạch bổ sung nhánh khi domain mở rộng?
- [ ] `Math.multiplyExact`/`Math.addExact` được dùng khi cần chống tràn?
- [ ] Record value equality có phù hợp kỳ vọng hay cần entity identity theo `orderId`?
- [ ] Có test cho invalid structure, null, boundary, trạng thái mới, order tổng tiền lớn và không side effect?
- [ ] Nếu thêm nhiều Line, đã xử lý mutable collections và tổng nhiều dòng?
- [ ] Nếu triển khai API thật, đã đặt transaction, auth, pricing, logistics và error model ở tầng phù hợp?

**Kết luận:** Record pattern Java 21 giúp “đọc” cấu trúc **Order → Customer/Line/Delivery → Address** ngay trong case label, nhờ đó nhiều nhánh phân loại trở nên trực quan và không cần cast. Thiết kế đúng cần phối hợp **schema record rõ ràng, validation trước nested matching, guard `when` thuần túy, thứ tự case có chủ đích, kiểm tra số học và test cho từng tầng null**. Pattern matching là công cụ diễn đạt quyết định; hợp đồng đơn hàng và an toàn nghiệp vụ vẫn phải do chương trình định nghĩa.

### Tài liệu tham khảo

- OpenJDK JEP 440 — Record Patterns (Java 21): https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch (Java 21): https://openjdk.org/jeps/441
- OpenJDK JEP 395 — Records (Java 16): https://openjdk.org/jeps/395
- OpenJDK JEP 409 — Sealed Classes (Java 17): https://openjdk.org/jeps/409
- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java Language Specification SE 21 — `14.30 Patterns` và `14.11 Switch Statements`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html
- Oracle Java 21 API — Math.multiplyExact: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#multiplyExact(long,long)
