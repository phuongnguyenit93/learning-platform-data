# Tổng kết Java Pattern Matching bằng mini project: ShopFlow Checkout (Java 21)

## 1. Bối cảnh bài thực hành tổng hợp

Hãy tưởng tượng bạn đang xây dựng một dịch vụ **ShopFlow Checkout** cho cửa hàng nhỏ. Hệ thống nhận một trong hai loại command:

- **Checkout:** Tính số tiền đơn hàng, quyết định phương thức giao hàng/thanh toán được chấp nhận, và áp dụng khuyến mãi trong một trường hợp cụ thể.
- **Cancel:** Chấp nhận yêu cầu hủy có mã đơn hợp lệ (chưa thực hiện thao tác hủy thật lên database).

Trong Checkout, dữ liệu không phẳng: một `Cart` chứa `Customer`, `Shipment`, `Payment`, số lượng và đơn giá. `Customer` lại chứa `Contact`. `Shipment` có hai subtype là `Standard`/`Express`; `Payment` có hai subtype là `Card`/`Cash`.

Đây là một bài **mini project kết thúc phần Java Core Pattern Matching**, tổng hợp những kiến thức đã học về:

- `instanceof` type pattern và flow scoping.
- `record`, record component, nested record pattern.
- `sealed interface` và danh sách `permits`.
- Pattern matching trong `switch expression`.
- Guard `when`, thứ tự case, dominance và exhaustive checking.
- `case null`, component null, nested record null và fallback.
- Kết quả dạng sealed hierarchy, phân tách domain decision khỏi định dạng hiển thị.
- Validation đầu vào, tiền tệ dùng số nguyên, kiểm tra overflow.
- Bộ kiểm thử lặp lại được, phân tích lỗi javac và cách mở rộng subtype.

Bài ưu tiên một **chương trình độc lập chạy được** thay vì chỉ đưa ra một tập các snippet rời rạc. Mã chính sử dụng **Java 21**, nơi record patterns (JEP 440) và pattern matching cho switch (JEP 441) là tính năng chính thức, **không cần `--enable-preview`**.

### Những gì bạn sẽ làm được

Sau khi hoàn thành, bạn có thể đọc một biểu thức `switch` chứa nhiều record patterns lồng nhau, tự bổ sung case vào hierarchy đóng kín, thiết kế guard không gây `NullPointerException`, hiểu vì sao một fallback có thể che thiếu subtype lồng bên trong, và kiểm thử logic trước khi đưa vào một hệ thống thật.

**Phạm vi nghiệp vụ của demo:** Chúng ta chỉ **tính báo giá và ra quyết định**, không tạo đơn hàng trong DB, không thực hiện thanh toán, không hủy giao dịch, không gửi request tới bên vận chuyển. Các chuỗi `APPROVED` hoặc `CANCEL_ACCEPTED` có nghĩa quyết định ở tầng demo đã được chấp nhận, **không phải** thực thi thành công ở hệ thống ngoài.

## 2. Yêu cầu của mini project

### 2.1. Mô hình lệnh

```text
Command (sealed)
├── Checkout(cart)
│   └── Cart(customer, shipment, payment, quantity, unitPriceCents)
│       ├── Customer(customerId, contact)
│       │   └── Contact(email)
│       ├── Shipment (sealed)
│       │   ├── Standard(zone)
│       │   └── Express(zone)
│       └── Payment (sealed)
│           ├── Card(last4)
│           └── Cash()
└── Cancel(orderId)
```

Mỗi command được xử lý theo một hợp đồng rõ ràng:

- `null` command → từ chối với mã `NO_COMMAND`.
- `Cancel` không có `orderId` hoặc chỉ có khoảng trắng → `INVALID_CANCEL_ID`.
- `Cancel` hợp lệ → kết quả `CancellationAccepted`.
- `Checkout` có cart null → `MISSING_CART`.
- Cart thiếu customer/shipment/payment, quantity không dương hoặc đơn giá không dương → `INVALID_CART`.
- Customer có ID null hoặc blank → `INVALID_CUSTOMER`.
- Nếu một **nested record** cần thiết còn thiếu, ví dụ `Customer.contact == null` → `INCOMPLETE_DETAILS`.
- Giao hàng Express chỉ được chấp nhận khi Payment là Card.
- Giao hàng Standard nhận cả Card lẫn Cash.
- Express/Card, quantity từ 10 trở lên, email không null/blank → **giảm 10% tiền hàng**.
- Tiền giao hàng cố định theo loại vận chuyển: **Express 500 cents**, **Standard 100 cents**.
- Mọi phép tính tổng tiền phải kiểm tra overflow; không silently wrap khi số quá lớn.

`Cents` trong ví dụ là đơn vị nguyên nhỏ nhất (1/100 của đơn vị tiền tệ giả định). Cách này tránh dùng `double` để cộng/trừ tiền. Chính sách tính thuế, tỷ giá, làm tròn ngoại tệ và giá của bên vận chuyển không nằm trong mini project.

### 2.2. Domain result

Không trả lại một `String` tùy ý từ mọi branch. Chúng ta định nghĩa **một sealed result hierarchy**:

```text
Result (sealed)
├── Approved(rule, subtotalCents, discountCents, shippingCents, payableCents)
├── Rejected(code)
└── CancellationAccepted(orderId)
```

Các kiểu kết quả tách bạch việc **quyết định nghiệp vụ** khỏi **format chuỗi đưa ra stdout**. Method `decide(Command)` trả `Result`; method `display(Result)` mới chuyển sang chuỗi có cấu trúc như `APPROVED:STANDARD_CARD:500`.

`Result` cũng là một sealed type, nên `display` có thể dùng `switch` exhaustive, compiler hỗ trợ nhắc cập nhật khi thêm một result subtype mới.

## 3. Vì sao chọn Java 21 và những tính năng nào được dùng?

| Tính năng | Vai trò trong mini project | Vị trí minh họa |
| --- | --- | --- |
| `sealed interface` | Giới hạn biến thể lệnh/đầu ra/giao hàng/thanh toán | `Command`, `Shipment`, `Payment`, `Result` |
| `record` | Mô hình dữ liệu ngắn gọn, component có kiểu | `Cart`, `Customer`, `Contact`, `Card` |
| Record pattern | Bind component theo declaration | `Cancel(String id)` |
| Nested record pattern | Đi sâu từ Checkout → Cart → Customer/Shipment/Payment | Các nhánh trong `decide` |
| `var` pattern | Bind giá trị component chưa cần deconstruct sâu | `Checkout(var cart)` |
| Guard `when` | Chọn rule theo số lượng, email, giá trị | Express bulk, invalid input |
| Pattern `switch expression` | Chọn một result bằng rule rõ ràng | `decide`, `display` |
| Type pattern `instanceof` | Kiểm tra/ràng buộc result đã approved | `isBillable` |
| `case null` | Chính sách selector null | `decide` và `display` |
| Exhaustiveness | Nhắc khi một direct sealed subtype chưa có case bao phủ | Hai switch expressions |
| Compact constructor | Bảo vệ invariant của record Card | `Card` |
| `Math.multiplyExact`/`addExact` | Bắt lỗi tràn số tiền | `quote` |

**Phân biệt các mốc Java:** `record` final từ Java 16; `sealed` final từ Java 17; nhưng **record patterns và pattern switch với `when` là final ở Java 21**. Vì vậy hãy biên dịch demo với `--release 21`.

Không phải mọi use case đều nên dùng một switch lớn. Ví dụ này cố ý tập trung vào khả năng **phân loại dữ liệu** của pattern matching. Nếu quy tắc thanh toán ngày càng phức tạp, có thể chuyển một phần behavior vào domain service riêng.

## 4. Thiết kế pipeline: từ Command tới Result

```text
Command input
    |
    v
decide(Command)
    |
    +-- Check null / missing required data
    |
    +-- Match sealed subtype
    |
    +-- Deconstruct nested Cart records
    |
    +-- Apply guard when and policy rules
    |
    +-- quote(...) using exact integer arithmetic
    |
    v
Result (Approved / Rejected / CancellationAccepted)
    |
    +-- display(Result)      [switch + record pattern]
    |
    +-- isBillable(Result)   [instanceof type pattern]
    |
    v
Deterministic output + tests
```

**Lưu ý tính thuần:** `decide` và `quote` trong demo không truy cập network, database hay filesystem. Chúng tạo Result từ dữ liệu đầu vào. Điều này khiến những case của `switch` dễ test và dễ suy luận hơn khi so sánh với code vừa match pattern vừa cập nhật DB.

Method `quote` là **helper định giá**; không tự làm lại type matching. Mỗi branch truyền một `rule` ổn định, phí ship và tỷ lệ giảm giá cụ thể. Cách tổ chức này tránh nhân bản `Math.multiplyExact` trong nhiều case.

## 5. Các quyết định thiết kế trước khi lập trình

### 5.1. Sealed domain types

Ta dùng:

```java
sealed interface Command permits Checkout, Cancel {}
sealed interface Shipment permits Standard, Express {}
sealed interface Payment permits Card, Cash {}
sealed interface Result permits Approved, Rejected, CancellationAccepted {}
```

Các record triển khai trực tiếp là `final`, nên compiler có thể hiểu tập biến thể được kiểm soát. Nếu sau này thêm subtype, nơi sử dụng pattern switch có thể phải cập nhật.

**Không ngầm cho phép plugin tùy ý** tạo Payment subtype; nếu yêu cầu hệ thống là mở rộng qua bên thứ ba, có thể phải dùng `non-sealed` hoặc extension point khác, và chính sách xử lý sẽ khác.

### 5.2. Một rule rõ ràng cho mỗi nhánh

Các mã `rule` ví dụ:

- `EXPRESS_BULK_CARD`.
- `EXPRESS_CARD`.
- `STANDARD_CARD`.
- `STANDARD_CASH`.

Các mã `Rejected.code` ví dụ `INVALID_CART`, `EXPRESS_CARD_ONLY` và `AMOUNT_OVERFLOW`.

Mã tĩnh dễ test và dễ dùng làm nhãn quan sát hệ thống hơn việc cố gắng in toàn bộ `Cart`, nhất là khi có dữ liệu như email và thông tin thanh toán.

### 5.3. Tiền là long, không phải double

Mỗi `Cart` chứa `int quantity` và `long unitPriceCents`. Tính:

\[
\text{subtotal} = \text{quantity}\times\text{unitPriceCents}
\]

\[
\text{discount} =
\begin{cases}
\left\lfloor \frac{\text{subtotal}}{10}\right\rfloor, & \text{nếu giảm }10\%\\
0, & \text{nếu không giảm}
\end{cases}
\]

\[
\text{payable} = \text{subtotal}-\text{discount}+\text{shipping}.
\]

Trong demo, các phép chia nguyên làm tròn xuống theo số cents cho discount 10%. Đây là **quy tắc làm tròn của ví dụ**, không phải quy tắc tài chính áp dụng cho mọi thị trường. Production cần có chính sách làm tròn, thuế, hoàn tiền và đơn vị tiền tệ thống nhất.

Để chống overflow, sử dụng `Math.multiplyExact`, `Math.subtractExact` và `Math.addExact` thay vì phép toán âm thầm wrap. Khi không biểu diễn được số tiền bằng `long`, trả `Rejected("AMOUNT_OVERFLOW")`.

### 5.4. Invariant cho Card

Record `Card` chỉ lưu bốn chữ số cuối mô phỏng. Nó kiểm tra chính xác **bốn ký tự ASCII từ 0 đến 9**. Đây không phải validation đầy đủ cho thẻ thanh toán và tuyệt đối **không phải nơi lưu PAN/CVV**. Đối với hệ thống thật, dùng tokenized payment instruments và các tiêu chuẩn an toàn phù hợp.

Trong demo, các record khác không có constructor validation toàn diện để người học luyện cách guard và fallback phản hồi dữ liệu sai. Đây là lựa chọn **sư phạm**, không có nghĩa record có `Customer.contact == null` là mô hình domain tốt cho production.

## 6. Chương trình Java 21 hoàn chỉnh

Tạo file **`PatternCheckoutMiniProject.java`** với nội dung sau. Tất cả các type đều là nested types trong một public class để dễ chạy với một lệnh `javac`; không cần Maven, Gradle hoặc framework.

```java
import java.util.Objects;

public class PatternCheckoutMiniProject {
    sealed interface Command permits Checkout, Cancel {}
    record Checkout(Cart cart) implements Command {}
    record Cancel(String orderId) implements Command {}

    record Cart(Customer customer, Shipment shipment, Payment payment,
                int quantity, long unitPriceCents) {}
    record Customer(String customerId, Contact contact) {}
    record Contact(String email) {}

    sealed interface Shipment permits Standard, Express {}
    record Standard(String zone) implements Shipment {}
    record Express(String zone) implements Shipment {}

    sealed interface Payment permits Card, Cash {}
    record Card(String last4) implements Payment {
        Card {
            if (last4 == null || !last4.matches("[0-9]{4}")) {
                throw new IllegalArgumentException(
                    "last4 must be four digits");
            }
        }
    }
    record Cash() implements Payment {}

    sealed interface Result
            permits Approved, Rejected, CancellationAccepted {}

    record Approved(
            String rule, long subtotalCents, long discountCents,
            long shippingCents, long payableCents) implements Result {}

    record Rejected(String code) implements Result {}
    record CancellationAccepted(String orderId) implements Result {}

    static Result quote(
            String rule, int quantity, long unitPriceCents,
            long shippingCents, int discountPercent) {
        try {
            long subtotal =
                Math.multiplyExact((long) quantity, unitPriceCents);

            long discount =
                discountPercent == 10 ? subtotal / 10 : 0;

            long payable = Math.addExact(
                Math.subtractExact(subtotal, discount),
                shippingCents);

            return new Approved(
                rule, subtotal, discount, shippingCents, payable);

        } catch (ArithmeticException overflow) {
            return new Rejected("AMOUNT_OVERFLOW");
        }
    }

    static Result decide(Command command) {
        return switch (command) {
            case null ->
                new Rejected("NO_COMMAND");

            case Cancel(String id) when id == null || id.isBlank() ->
                new Rejected("INVALID_CANCEL_ID");
            case Cancel(String id) ->
                new CancellationAccepted(id);

            case Checkout(var cart) when cart == null ->
                new Rejected("MISSING_CART");

            case Checkout(Cart(
                    var customer, var shipment, var payment,
                    int quantity, long unitPrice))
                    when customer == null || shipment == null ||
                         payment == null || quantity <= 0 ||
                         unitPrice <= 0 ->
                new Rejected("INVALID_CART");

            case Checkout(Cart(
                    Customer(String id, var contact),
                    var shipment, var payment,
                    int quantity, long unitPrice))
                    when id == null || id.isBlank() ->
                new Rejected("INVALID_CUSTOMER");

            case Checkout(Cart(
                    Customer(String id, Contact(String email)),
                    Express(String zone), Card(String last4),
                    int quantity, long unitPrice))
                    when quantity >= 10 && email != null &&
                         !email.isBlank() ->
                quote(
                    "EXPRESS_BULK_CARD",
                    quantity, unitPrice, 500, 10);

            case Checkout(Cart(
                    Customer(String id, Contact(String email)),
                    Express(String zone), Card(String last4),
                    int quantity, long unitPrice)) ->
                quote(
                    "EXPRESS_CARD",
                    quantity, unitPrice, 500, 0);

            case Checkout(Cart(
                    Customer(String id, Contact(String email)),
                    Express(String zone), Cash(),
                    int quantity, long unitPrice)) ->
                new Rejected("EXPRESS_CARD_ONLY");

            case Checkout(Cart(
                    Customer(String id, Contact(String email)),
                    Standard(String zone), Card(String last4),
                    int quantity, long unitPrice)) ->
                quote(
                    "STANDARD_CARD",
                    quantity, unitPrice, 100, 0);

            case Checkout(Cart(
                    Customer(String id, Contact(String email)),
                    Standard(String zone), Cash(),
                    int quantity, long unitPrice)) ->
                quote(
                    "STANDARD_CASH",
                    quantity, unitPrice, 100, 0);

            case Checkout(var cart) ->
                new Rejected("INCOMPLETE_DETAILS");
        };
    }

    static String display(Result result) {
        return switch (result) {
            case Approved(
                    String rule, long base, long discount,
                    long shipping, long payable)
                    when discount > 0 ->
                "APPROVED_PROMO:" + rule + ":" + payable;

            case Approved(
                    String rule, long base, long discount,
                    long shipping, long payable) ->
                "APPROVED:" + rule + ":" + payable;

            case Rejected(String code) ->
                "REJECTED:" + code;

            case CancellationAccepted(String id) ->
                "CANCEL_ACCEPTED:" + id;

            case null ->
                "NO_RESULT";
        };
    }

    static boolean isBillable(Result result) {
        return result instanceof Approved approved &&
               approved.payableCents() > 0;
    }

    static int passed;

    static void check(
            String testId, Command command,
            String expected, boolean expectedBillable) {
        Result result = decide(command);
        String actual = display(result);
        boolean billable = isBillable(result);

        if (!Objects.equals(actual, expected) ||
                billable != expectedBillable) {
            throw new AssertionError(
                testId + " expected " + expected + "/" +
                expectedBillable + " but got " +
                actual + "/" + billable);
        }

        passed++;
        System.out.println(
            testId + " " + actual + " | billable=" + billable);
    }

    static void expectBadCard() {
        try {
            new Card("ABC");
            throw new AssertionError("Expected invalid Card");
        } catch (IllegalArgumentException expected) {
            passed++;
            System.out.println("C20 CARD_INVALID");
        }
    }

    public static void main(String[] args) {
        Customer lan =
            new Customer("U1", new Contact("lan@example.test"));
        Customer noEmail =
            new Customer("U2", new Contact(null));

        Shipment express = new Express("NORTH");
        Shipment standard = new Standard("SOUTH");
        Payment card = new Card("1234");
        Payment cash = new Cash();

        check("C01", null,
            "REJECTED:NO_COMMAND", false);
        check("C02", new Cancel(null),
            "REJECTED:INVALID_CANCEL_ID", false);
        check("C03", new Cancel("ORD-7"),
            "CANCEL_ACCEPTED:ORD-7", false);
        check("C04", new Checkout(null),
            "REJECTED:MISSING_CART", false);

        check("C05", new Checkout(new Cart(
            null, express, card, 1, 200)),
            "REJECTED:INVALID_CART", false);

        check("C06", new Checkout(new Cart(
            lan, express, card, 0, 200)),
            "REJECTED:INVALID_CART", false);

        check("C07", new Checkout(new Cart(
            lan, express, card, 2, -1)),
            "REJECTED:INVALID_CART", false);

        check("C08", new Checkout(new Cart(
            new Customer(" ", new Contact("x@example.test")),
            express, card, 2, 200)),
            "REJECTED:INVALID_CUSTOMER", false);

        check("C09", new Checkout(new Cart(
            lan, express, card, 2, 200)),
            "APPROVED:EXPRESS_CARD:900", true);

        check("C10", new Checkout(new Cart(
            lan, express, card, 10, 200)),
            "APPROVED_PROMO:EXPRESS_BULK_CARD:2300", true);

        check("C11", new Checkout(new Cart(
            noEmail, express, card, 10, 200)),
            "APPROVED:EXPRESS_CARD:2500", true);

        check("C12", new Checkout(new Cart(
            lan, express, cash, 2, 200)),
            "REJECTED:EXPRESS_CARD_ONLY", false);

        check("C13", new Checkout(new Cart(
            lan, standard, card, 2, 200)),
            "APPROVED:STANDARD_CARD:500", true);

        check("C14", new Checkout(new Cart(
            lan, standard, cash, 3, 200)),
            "APPROVED:STANDARD_CASH:700", true);

        check("C15", new Checkout(new Cart(
            new Customer("U3", null),
            express, card, 2, 200)),
            "REJECTED:INCOMPLETE_DETAILS", false);

        check("C16", new Checkout(new Cart(
            lan, null, card, 2, 200)),
            "REJECTED:INVALID_CART", false);

        check("C17", new Checkout(new Cart(
            lan, standard, card, 2, Long.MAX_VALUE)),
            "REJECTED:AMOUNT_OVERFLOW", false);

        check("C18", new Checkout(new Cart(
            lan, standard, null, 2, 200)),
            "REJECTED:INVALID_CART", false);

        check("C19", new Checkout(new Cart(
            lan, standard, card, 1, Long.MAX_VALUE)),
            "REJECTED:AMOUNT_OVERFLOW", false);

        expectBadCard();

        System.out.println("RESULT_NULL=" + display(null));
        System.out.println("TESTS=" + passed);
    }
}
```

### Biên dịch và chạy

Cần **JDK 21 trở lên**. Đứng trong thư mục chứa file và chạy:

```bash
javac --release 21 PatternCheckoutMiniProject.java
java PatternCheckoutMiniProject
```

Chương trình không cần dependency bên ngoài. Bộ kiểm thử dùng `AssertionError` tường minh khi sai, nên không cần bật `java -ea`.

### Stdout chính xác

```text
C01 REJECTED:NO_COMMAND | billable=false
C02 REJECTED:INVALID_CANCEL_ID | billable=false
C03 CANCEL_ACCEPTED:ORD-7 | billable=false
C04 REJECTED:MISSING_CART | billable=false
C05 REJECTED:INVALID_CART | billable=false
C06 REJECTED:INVALID_CART | billable=false
C07 REJECTED:INVALID_CART | billable=false
C08 REJECTED:INVALID_CUSTOMER | billable=false
C09 APPROVED:EXPRESS_CARD:900 | billable=true
C10 APPROVED_PROMO:EXPRESS_BULK_CARD:2300 | billable=true
C11 APPROVED:EXPRESS_CARD:2500 | billable=true
C12 REJECTED:EXPRESS_CARD_ONLY | billable=false
C13 APPROVED:STANDARD_CARD:500 | billable=true
C14 APPROVED:STANDARD_CASH:700 | billable=true
C15 REJECTED:INCOMPLETE_DETAILS | billable=false
C16 REJECTED:INVALID_CART | billable=false
C17 REJECTED:AMOUNT_OVERFLOW | billable=false
C18 REJECTED:INVALID_CART | billable=false
C19 REJECTED:AMOUNT_OVERFLOW | billable=false
C20 CARD_INVALID
RESULT_NULL=NO_RESULT
TESTS=20
```

`TESTS=20` là tổng **19 ca `check`** cộng một ca validation trong `expectBadCard`. Dòng `RESULT_NULL` minh họa chính sách định dạng null và không làm tăng bộ đếm test.

## 7. Lần theo `decide`: vì sao các case được chọn?

### 7.1. Null selector trước mọi loại command

```java
case null -> new Rejected("NO_COMMAND");
```

Một selector null trong pattern `switch` cần được xử lý theo policy. `case null` rõ ràng hơn việc giả định `default` là catch-all cho null. Nếu contract yêu cầu null phải là lỗi lập trình thay vì kết quả bị từ chối, có thể validate ở boundary và chủ động ném `NullPointerException`/exception phù hợp.

### 7.2. Type cụ thể, guard, rồi case không guard

Với `Cancel`:

```java
case Cancel(String id) when id == null || id.isBlank() ->
    new Rejected("INVALID_CANCEL_ID");

case Cancel(String id) ->
    new CancellationAccepted(id);
```

Hai case cùng nhận subtype `Cancel`. Guard đầu nhận ID null/blank; case không guard sau nhận mọi Cancel còn lại. Nếu đảo thứ tự, case có guard sẽ **dominated** bởi case đầu và compiler từ chối.

`id == null || id.isBlank()` dùng short-circuit; khi id null, Java không gọi `isBlank()`.

### 7.3. Dùng `var` để kiểm tra component null

```java
case Checkout(var cart) when cart == null ->
    new Rejected("MISSING_CART");
```

`Checkout` là record khác null; component `cart` có thể null. `var cart` bind cả null để guard kiểm tra. Trái lại, nếu dùng `Checkout(Cart(...))`, một `cart == null` không khớp **nested record pattern** `Cart(...)`.

Tiếp đó:

```java
case Checkout(Cart(
        var customer, var shipment, var payment,
        int quantity, long unitPrice))
        when customer == null || shipment == null ||
             payment == null || quantity <= 0 || unitPrice <= 0 ->
    new Rejected("INVALID_CART");
```

Đây là ví dụ **record pattern lồng nhau + var patterns + guard**. `Cart(...)` chỉ khớp khi Cart tồn tại; các component bên trong được bind, kể cả null đối với reference. Guard kiểm tra những điều kiện nghiệp vụ khác nhau trong một nơi.

### 7.4. Validate Customer ID nhưng không ép Contact tồn tại

```java
case Checkout(Cart(
        Customer(String id, var contact),
        var shipment, var payment,
        int quantity, long unitPrice))
        when id == null || id.isBlank() ->
    new Rejected("INVALID_CUSTOMER");
```

Bằng cách dùng `var contact`, rule này vẫn nhận được `Customer` có contact null để kiểm tra ID. Một pattern sâu `Customer(String id, Contact(String email))` sẽ không khớp nếu contact null, và ta có thể bỏ qua lỗi ID.

Đây là minh họa quan trọng: **độ sâu của pattern quyết định những trường hợp có thể đi tới guard**. Không nên lồng mọi record sâu nhất chỉ vì cú pháp cho phép; lồng vừa đủ phục vụ quy tắc đang kiểm tra.

### 7.5. Express/Card: guard bulk trước nhánh thường

```java
case Checkout(Cart(
        Customer(String id, Contact(String email)),
        Express(String zone), Card(String last4),
        int quantity, long unitPrice))
        when quantity >= 10 && email != null &&
             !email.isBlank() ->
    quote("EXPRESS_BULK_CARD", quantity, unitPrice, 500, 10);
```

Pattern yêu cầu:
- Command là `Checkout`.
- `Cart` khác null.
- `Customer` khác null và có `Contact` khác null.
- Shipment là `Express`.
- Payment là `Card`.
- Quantity và đơn giá là giá trị `int`/`long` của Cart.

Guard yêu cầu thêm quantity lớn và email không rỗng. Nếu true, áp dụng giảm giá 10%.

Case Express/Card **không guard** ở ngay sau trả giá thường:

```java
case Checkout(Cart(
        Customer(String id, Contact(String email)),
        Express(String zone), Card(String last4),
        int quantity, long unitPrice)) ->
    quote("EXPRESS_CARD", quantity, unitPrice, 500, 0);
```

Sắp thứ tự này có ý nghĩa nghiệp vụ: trường hợp bulk đi trước, trường hợp card còn lại đi sau. Nếu đặt case tổng quát trước, compiler báo **dominated case**.

### 7.6. Express/Cash bị từ chối

```java
case Checkout(Cart(
        Customer(String id, Contact(String email)),
        Express(String zone), Cash(),
        int quantity, long unitPrice)) ->
    new Rejected("EXPRESS_CARD_ONLY");
```

`Cash()` là record pattern của record không có components. Không viết `Cash` như một type pattern có biến nếu mục tiêu ở đây là deconstruct đúng subtype cụ thể. Với policy demo, Express không nhận Cash nên không gọi `quote`.

Điều này giúp phân biệt **pattern có thể khớp cấu trúc** với **nghiệp vụ có chấp nhận hay không**. Mẫu Express/Cash được match thành công, nhưng Result là Rejected.

### 7.7. Standard có cả hai loại thanh toán

Hai case Standard/Card và Standard/Cash có cùng phí ship 100 cents, không giảm giá. Chúng vẫn tách riêng trong `switch` để người học thấy rõ phân loại theo hai sealed subtypes của Payment.

Nếu production có nhiều Payment type, việc liệt kê mọi cặp shipment/payment có thể không còn tối ưu về tổ chức. Khi đó, cân nhắc tách bảng phí và policy tương ứng sang domain services, vẫn giữ pattern matching cho điểm phân loại thực sự có giá trị.

### 7.8. Fallback cho nested data không đầy đủ

```java
case Checkout(var cart) ->
    new Rejected("INCOMPLETE_DETAILS");
```

Case này bắt tất cả Checkout còn lại, trong đó có:

```java
new Checkout(new Cart(
    new Customer("U3", null),
    new Express("NORTH"), new Card("1234"), 2, 200))
```

`Customer` tồn tại, nhưng `Customer.contact == null` nên nested `Contact(String email)` ở những case cụ thể **không khớp**. Case fallback nhận command và trả `INCOMPLETE_DETAILS`.

**Đặt fallback cuối:** Nếu case Checkout tổng quát đứng trước Card/Cash, các case cụ thể phía sau bị dominated. Fallback giúp switch bao phủ mọi Checkout, nhưng có đánh đổi: khi thêm subtype Shipment/Payment mà không thêm case phù hợp, fallback vẫn có thể trả `INCOMPLETE_DETAILS` dù dữ liệu mới hoàn toàn hợp lệ. Vì vậy **compiler exhaustiveness ở Command không thay thế test cho nested hierarchy Payment/Shipment**.

## 8. Method `quote`: tách xử lý nghiệp vụ khỏi type matching

`quote` nhận rule đã chọn cùng số lượng, đơn giá, phí ship và tỷ lệ discount:

```java
static Result quote(String rule, int quantity, long unitPriceCents,
                    long shippingCents, int discountPercent) {
    try {
        long subtotal = Math.multiplyExact(
            (long) quantity, unitPriceCents);
        long discount = discountPercent == 10
            ? subtotal / 10 : 0;
        long payable = Math.addExact(
            Math.subtractExact(subtotal, discount),
            shippingCents);

        return new Approved(
            rule, subtotal, discount, shippingCents, payable);
    } catch (ArithmeticException ex) {
        return new Rejected("AMOUNT_OVERFLOW");
    }
}
```

**Vì sao không trực tiếp làm mọi phép tính trong từng case?** Cách đó khiến logic overflow và cấu trúc tính tiền bị lặp. Nếu sửa quy tắc arithmetic, ta phải sửa nhiều nhánh và dễ tạo chênh lệch.

**Vì sao dùng các phép toán exact?** Với số nguyên, phép nhân/cộng có thể overflow và wrap, tạo một khoản thanh toán sai. `Math.multiplyExact`/`Math.addExact`/`Math.subtractExact` ném `ArithmeticException` thay vì trả kết quả wrap. Helper chuyển lỗi số học này thành `Rejected("AMOUNT_OVERFLOW")`.

**Giới hạn:** Helper chỉ chấp nhận policy discountPercent là 0 hoặc 10 theo các call sites trong demo. Đây chưa phải API giá thành tổng quát; nếu đưa ra production, cần validate trực tiếp discountPercent, shippingCents và các invariant khác. Khi nghiệp vụ cần giá tiền vượt phạm vi `long`, có thể cân nhắc `BigInteger`/`BigDecimal` hoặc domain Money type phù hợp.

### Hai thử nghiệm overflow

- **C17:** quantity = 2, unitPriceCents = `Long.MAX_VALUE` → `Math.multiplyExact` overflow.
- **C19:** quantity = 1, unitPriceCents = `Long.MAX_VALUE` → subtotal chưa overflow, nhưng thêm 100 cents phí ship khiến `Math.addExact` overflow.

Cả hai trả `REJECTED:AMOUNT_OVERFLOW`, cho thấy không chỉ phép nhân mà cả phép cộng cuối cùng cũng cần kiểm soát.

## 9. Sealed Result + pattern switch thứ hai

`decide` trả một trong ba subtype của `Result`:

```java
sealed interface Result
    permits Approved, Rejected, CancellationAccepted {}

record Approved(String rule, long subtotalCents, long discountCents,
                long shippingCents, long payableCents) implements Result {}

record Rejected(String code) implements Result {}
record CancellationAccepted(String orderId) implements Result {}
```

`display` là một **operation khác** trên cùng mô hình result. Nó có guard để phân biệt Approved có discount:

```java
case Approved(String rule, long base, long discount,
              long shipping, long payable)
        when discount > 0 ->
    "APPROVED_PROMO:" + rule + ":" + payable;

case Approved(String rule, long base, long discount,
              long shipping, long payable) ->
    "APPROVED:" + rule + ":" + payable;
```

Ở đây:
- Record pattern deconstruct trực tiếp `Approved`.
- Guard `discount > 0` phải đứng trước Approved case không guard.
- `Rejected` và `CancellationAccepted` được xử lý riêng.
- `case null` định nghĩa cách hiển thị null result.
- Không cần `default` khi mỗi direct permitted subtype đã có case bao phủ.

**Exhaustiveness ở hai nơi:** Khi thêm một subtype mới của `Result`, `display` có thể báo non-exhaustive. Khi thêm một subtype của `Command`, `decide` có thể báo non-exhaustive. Đây là hai phép bảo vệ khác nhau tương ứng **đầu vào** và **đầu ra**.

Compiler không kiểm tra xem chuỗi `APPROVED_PROMO` có đúng ý nghĩa marketing không; đây là việc của test và contract.

## 10. Type pattern với `instanceof` và flow scoping

Không phải mọi phép xử lý cần `switch`. Nếu chỉ hỏi một câu boolean, `instanceof` type pattern rất phù hợp:

```java
static boolean isBillable(Result result) {
    return result instanceof Approved approved &&
           approved.payableCents() > 0;
}
```

`approved` chỉ có thể được dùng ở vế phải của `&&` sau khi phép `instanceof` thành công. Đây là **flow scoping**: Java cho phép đọc biến pattern ở nơi điều kiện đã chứng minh nó được bind.

- Nếu `result` là `Approved` và payable > 0, trả true.
- Nếu `result` là `Rejected` hoặc `CancellationAccepted`, trả false.
- Nếu `result` null, `instanceof` false, nên không dereference `approved`.

Một cách viết cũ cần `instanceof Approved` rồi cast, nhưng pattern loại bỏ cast thủ công khỏi source. Không cần so sánh hiệu năng bằng suy luận “ít dòng hơn” — lợi ích chính ở đây là rõ ràng và type safety.

### Phạm vi biến không tùy tiện kéo dài

Đoạn minh họa cố ý sai:

```java
// Không thuộc chương trình chạy được.
if (result instanceof Approved approved) {
    System.out.println(approved.rule());
}
System.out.println(approved.rule()); // biến không có scope tại đây
```

Pattern variable không phải biến local được khai báo cho toàn method. Nếu cần một giá trị ở bên ngoài nhánh, thiết kế biến/result cho đúng hoặc dùng `switch expression` trả về một giá trị.

## 11. Ma trận kiểm thử 20 tình huống

Cả 20 ca trong chương trình đều được so sánh với expected output, đồng thời các ca `check` so `isBillable` theo contract.

| Test | Trường hợp | Kỳ vọng chính |
| --- | --- | --- |
| C01 | Command null | `REJECTED:NO_COMMAND` |
| C02 | Cancel ID null | `REJECTED:INVALID_CANCEL_ID` |
| C03 | Cancel ID hợp lệ | `CANCEL_ACCEPTED:ORD-7` |
| C04 | Checkout cart null | `REJECTED:MISSING_CART` |
| C05 | Cart customer null | `REJECTED:INVALID_CART` |
| C06 | Quantity bằng 0 | `REJECTED:INVALID_CART` |
| C07 | UnitPrice âm | `REJECTED:INVALID_CART` |
| C08 | Customer ID blank | `REJECTED:INVALID_CUSTOMER` |
| C09 | Express/Card, quantity2 | `APPROVED:EXPRESS_CARD:900` |
| C10 | Express/Card, quantity10, có email | `APPROVED_PROMO:EXPRESS_BULK_CARD:2300` |
| C11 | Express/Card, quantity10, email null | `APPROVED:EXPRESS_CARD:2500` |
| C12 | Express/Cash | `REJECTED:EXPRESS_CARD_ONLY` |
| C13 | Standard/Card, quantity2 | `APPROVED:STANDARD_CARD:500` |
| C14 | Standard/Cash, quantity3 | `APPROVED:STANDARD_CASH:700` |
| C15 | Contact record null | `REJECTED:INCOMPLETE_DETAILS` |
| C16 | Shipment null | `REJECTED:INVALID_CART` |
| C17 | Overflow khi nhân | `REJECTED:AMOUNT_OVERFLOW` |
| C18 | Payment null | `REJECTED:INVALID_CART` |
| C19 | Overflow khi cộng phí ship | `REJECTED:AMOUNT_OVERFLOW` |
| C20 | Card có `last4="ABC"` | `IllegalArgumentException` được test bắt |

Các test được viết bằng Java SE thuần; trong một project thật có thể chuyển sang JUnit 5 parameterized tests. Nhưng dù dùng framework nào, **expected values phải phản ánh yêu cầu nghiệp vụ**, không chỉ lặp lại kết quả của hàm đang kiểm.

### Kiểm chứng một ví dụ tính tiền

Với **C10**: quantity10, unitPrice200 cents, Express fee500 cents:
- Subtotal = 10 × 200 = 2.000 cents.
- Discount 10% = 200 cents.
- Shipping = 500 cents.
- Payable = 2.000 − 200 + 500 = **2.300 cents**.

Vì vậy output `APPROVED_PROMO:EXPRESS_BULK_CARD:2300` là nhất quán. C09 quantity2 không hưởng discount, có subtotal400 và phí Express500 → payable900.

### Giá trị biên quan trọng

Guard bulk dùng `quantity >= 10`. Hai giá trị **9 và 10** nên có test thêm khi mở rộng bài để bắt lỗi viết nhầm `> 10` thành `>= 10` hoặc ngược lại. Demo hiện có quantity2 và quantity10; test 10 đã bảo vệ phía tại ngưỡng, nhưng thêm 9 giúp tăng độ tin cậy ngay trước ngưỡng.

Đối với `unitPriceCents` và `quantity`, điều kiện `<= 0` cần test cả 0 và số âm trong suite đầy đủ. Với `Card.last4`, test thêm null, chuỗi 3/5 chữ số và ký tự ngoài ASCII nếu API thật nhận dữ liệu từ bên ngoài.

### Kết quả true/false của `isBillable`

`isBillable` không dùng string matching `display`. Nó nhìn vào kiểu thực của `Result` và giá trị `payableCents`. Điều đó có ích khi thay đổi message hiển thị mà không làm thay đổi logic nghiệp vụ.

Trong suite, các ca C09, C10, C11, C13 và C14 trả true. Những ca Rejected/CancellationAccepted trả false. `isBillable(null)` cũng sẽ false vì `instanceof` trên null không khớp.

## 12. Null policy và nested records: những chỗ dễ hiểu sai

Trong mini project có nhiều mức null:

| Vị trí | Ví dụ | Kết quả |
| --- | --- | --- |
| Selector của `decide` | `decide(null)` | `NO_COMMAND` |
| Component Checkout.cart | `new Checkout(null)` | `MISSING_CART` |
| Component Cart.customer | `new Cart(null, ...)` | `INVALID_CART` |
| Component Cart.shipment | Shipment null | `INVALID_CART` |
| Component Cart.payment | Payment null | `INVALID_CART` |
| Component Customer.contact | `new Customer("U3", null)` | `INCOMPLETE_DETAILS` |
| Component Contact.email | `new Contact(null)` | Pattern Contact vẫn có thể khớp; không được promo |
| Selector của `display` | `display(null)` | `NO_RESULT` |

### Selector null khác component null

`case null` trong `switch (command)` xử lý **command null**, không phải tất cả component null nằm sâu. Một nested record pattern `Contact(String email)` yêu cầu **record Contact tồn tại**, nhưng component email có thể null. Một `var contact` có thể bind null vì nó không yêu cầu match một nested record cụ thể.

Đây là lý do code xử lý invalid ở các mức hợp lý **trước khi** dùng pattern sâu. Nếu đặt quá nhiều nested constraints trong case validation, một object sai có thể không khớp case cần trả lỗi.

### Fallback không phải “bắt exception”

`case Checkout(var cart) -> new Rejected("INCOMPLETE_DETAILS")` được chọn nếu các pattern trước không match hoặc guard false. Nó **không** tự bắt lỗi ném từ accessor, body hoặc guard.

Nếu một record accessor tùy chỉnh ném exception trong deconstruction, Java 21 có quy tắc liên quan `MatchException` với nguyên nhân ban đầu. Nếu một guard ném `NullPointerException`, exception không tự biến thành guard false. Cần xử lý lỗi ở boundary phù hợp, không giả định case fallback luôn chạy.

### Validation sớm so với pattern validation

Demo cố ý cho `Cart.quantity<=0` được tạo rồi trả `Rejected`. Với domain mạnh hơn, có thể validate trong compact constructor:

```java
// Định nghĩa thay thế minh họa; không đặt chung với Cart trong code chính.
record Cart(Customer customer, Shipment shipment, Payment payment,
            int quantity, long unitPriceCents) {
    Cart {
        Objects.requireNonNull(customer);
        Objects.requireNonNull(shipment);
        Objects.requireNonNull(payment);
        if (quantity <= 0 || unitPriceCents <= 0) {
            throw new IllegalArgumentException("invalid cart");
        }
    }
}
```

Khi đó một số case invalid trong switch không còn nhận được object sai vì constructor đã từ chối. Hai chính sách đều có thể hợp lý tùy tầng dữ liệu: một **input DTO** chấp nhận dữ liệu xấu để trả validation errors; một **domain value object** nên giữ invariant. Không trộn hai trách nhiệm một cách vô tình.

## 13. Compiler feedback: khi mở rộng hệ thống

### 13.1. Thêm một Command mới

Giả sử bổ sung:

```java
// Minh họa mở rộng, không ghép vào file chạy được nếu chưa sửa permits/cases.
record Track(String orderId) implements Command {}
```

Cần cập nhật `permits` của `Command` để bao gồm `Track`. Khi compiler build lại method `decide`, không có case nào đang nhận Track; vì thế có thể nhận diagnostic:

```text
the switch expression does not cover all possible input values
```

**Hành động đúng:** Quyết định contract của Track, thêm case cho `Track` và test, thay vì thêm `default -> new Rejected("OTHER")` để né cập nhật.

### 13.2. Dominance khi đặt case tổng quát lên trước

Nếu viết:

```java
// CỐ Ý SAI trong cùng switch:
case Cart(int quantity) -> "STANDARD";
case Cart(int quantity) when quantity >= 10 -> "BULK";
```

Đoạn này chỉ mô tả ý tưởng. `Cart` thật trong chương trình có **năm** components nên mẫu một component sẽ có lỗi arity trước khi nói đến dominance. Để tái tạo dominance chính xác, dùng một record đơn giản khác:

```java
// Đoạn minh họa riêng:
record Line(int quantity) {}

static String classifyLine(Object line) {
    return switch (line) {
        case Line(int quantity) -> "STANDARD";
        case Line(int quantity) when quantity >= 10 -> "BULK";
        default -> "OTHER";
    };
}
```

Đây là code **cố ý sai**: case không guard đứng trước đã nhận mọi Line, khiến case BULK phía sau bị dominated. Javac có thể báo:

```text
this case label is dominated by a preceding case label
```

**Sửa:** Đặt case có `when quantity>=10` trước. Hai trường hợp compiler feedback — non-exhaustive và dominated — là hai loại lỗi khác nhau: một lỗi thiếu coverage, một lỗi case bị che bởi case trước.

Cả hai loại diagnostic đã được kiểm chứng với JavaCompiler ở mức `--release 21`.

### 13.3. Thêm một Payment mới có thể không làm compiler báo

Giả sử:

```java
// Minh họa mở rộng hierarchy:
record Voucher(String code) implements Payment {}
```

Bạn cập nhật `permits` của `Payment` nhưng `decide` vẫn có case tổng quát `Checkout(var cart)` ở cuối. Compiler có thể xem switch trên **Command** vẫn exhaustive, vì mọi Checkout đều có fallback. Nhưng một Cart có Payment Voucher có thể bị trả `INCOMPLETE_DETAILS` dù voucher hợp lệ.

**Đây là giới hạn quan trọng của exhaustive checking:** Compiler chỉ chứng minh một selector được một case bao phủ; nó không chứng minh mọi subtype sâu bên trong được xử lý đúng nghiệp vụ. Khi thêm Payment/Shipment subtype mới, cần cập nhật **test matrix của nested hierarchy**, không chỉ dựa vào build xanh.

### 13.4. Thêm Result mới

Nếu mở rộng `Result` bằng một subtype `Pending`, phương thức `display` phải được xét lại. Vì `display` không có `default`, compiler có thể yêu cầu thêm case để giữ exhaustive.

Với hệ thống multi-module, phải **biên dịch lại consumer** để compiler thấy hierarchy mới. Nếu chỉ build module chứa model, không thể khẳng định tất cả switch bên ngoài đã được cập nhật.

## 14. Lỗi thường gặp và cách khắc phục

| Lỗi | Vì sao không ổn | Cách khắc phục |
| --- | --- | --- |
| Dùng `double` cho tiền mà không có policy | Lỗi làm tròn, khó kiểm soát | Dùng đơn vị cents hoặc Money type rõ |
| Dùng `quantity*unitPrice` và để overflow | Có thể ra giá âm/sai | `Math.multiplyExact` và `addExact` |
| Cho `Approved` đồng nghĩa đã charge tiền | Nhầm decision và execution | Tách quote/approval khỏi payment commit |
| Chỉ dùng `command.getClass()` | Không phân biệt guard bulk/normal | Rule ID gắn với branch thật |
| Đặt case Express/Card không guard trước promo | Promo case bị dominated | Case có guard trước |
| Dùng `case null` để bắt mọi component null | Selector null khác nested null | Dùng `var`, guard và invariant phù hợp |
| Luôn lồng pattern sâu nhất | Dễ khó đọc và bỏ sót validation sớm | Lồng vừa đủ cho rule |
| Dùng `default` rộng để tránh lỗi build | Bỏ qua subtype mới | Giữ exhaustive cases khi có thể |
| Tưởng exhaustive Command là đủ cho Payment | Fallback có thể che biến thể Payment mới | Test nested subtype matrix |
| In toàn bộ Cart/Card vào log | Có thể lộ PII/thông tin thanh toán | Log allowlisted metadata, không dùng raw record |
| Catch mọi `Exception` rồi trả AMOUNT_OVERFLOW | Che bug khác với overflow số học | Chỉ catch ArithmeticException nơi tính tiền |
| Bỏ qua test JDK runtime thật | Compile không bảo đảm deploy tương thích | Test với runtime mục tiêu |
| Dùng Java21 syntax trong `--release 17` | Compiler từ chối | Nâng target hoặc dùng `instanceof` type patterns |
| Đổi cấu trúc record mà quên consumer | Pattern arity/types bị sai | Build/review mọi module phụ thuộc |
| Dùng pattern variable ngoài scope | `cannot find symbol` | Tuân thủ flow scoping |
| Thử C10 nhưng không test ngay trước ngưỡng | Có thể lọt lỗi ranh giới | Thêm quantity9/10 |

## 15. Cấu trúc repo khi phát triển thành dự án thật

Chương trình single-file rất tốt để học, nhưng trong hệ thống lớn cần tách trách nhiệm:

```text
shopflow/
  domain/
    Command.java
    Cart.java
    Customer.java
    Shipment.java
    Payment.java
    Result.java
  application/
    CheckoutDecisionService.java
    QuoteCalculator.java
  adapter/
    HttpCheckoutController.java
    CheckoutResultMapper.java
  tests/
    CheckoutDecisionServiceTest.java
    QuoteCalculatorTest.java
    CheckoutApiIntegrationTest.java
```

Đây là **cấu trúc đề xuất**, không phải các file cần tạo để chạy `PatternCheckoutMiniProject.java`. Những nguyên tắc:
- Domain model chứa invariant và các value types cần thiết.
- Application service sở hữu luồng chọn rule, không trộn logging/network với pattern matching.
- Calculator tính toán số tiền một lần, được test riêng.
- Adapter chuyển HTTP/JSON thành command và Result thành response; các field nhạy cảm không nên được log mặc định.
- Khi thêm Payment subtype, phải cập nhật mapper, tests và policy tương ứng.

Có thể dùng JUnit 5 cho test param, nhưng đây là dependency **ngoài JDK**. Demo không giả vờ rằng source dùng JUnit chạy được chỉ với `javac`. Nếu chuyển sang JUnit, giữ nguyên expected outputs, overflow cases và null matrix trong `@ParameterizedTest`/`@MethodSource`.

### Hướng mở rộng kiểm thử thực tế

Một bộ kiểm thử production nên thêm:
- Test constructor với Card null, ba chữ số, năm chữ số hoặc ký tự không phải ASCII digit.
- Test quantity9/10, quantity âm, unitPrice0, email blank.
- Kiểm bản thân các field `Approved`: subtotal, discount, shipping, payable, không chỉ string summary.
- Test với số tiền rất lớn, overflow cộng và overflow nhân.
- Test DTO parsing: phân biệt JSON missing field, JSON null và kiểu sai.
- Test không lộ email/thông tin Card ra logs hoặc metrics.
- Integration test idempotency/cancel thật nếu project bổ sung database/payment gateway.
- Kiểm API contract và permissions; việc một pattern khớp không xác thực được quyền thực hiện command.

## 16. Có nhất thiết dùng pattern switch cho mọi behavior?

Không. Chọn kỹ thuật theo mục tiêu:

- Dùng **`instanceof` type pattern** cho một điều kiện đơn giản hoặc một pipeline `if` ngắn.
- Dùng **record pattern** khi cần deconstruct cấu trúc dữ liệu mà không gọi accessor thủ công ở nhiều tầng.
- Dùng **switch expression** khi phân loại một sealed hierarchy và cần một Result, nhất là khi muốn compiler nhắc cập nhật subtype.
- Dùng **polymorphism** hoặc domain service khi behavior thuộc sở hữu tự nhiên của domain type và được tái sử dụng ở nhiều consumer.
- Dùng **guard `when`** cho điều kiện gọn, an toàn null; nếu rule rất phức tạp, trích xuất helper thuần và test riêng.
- Không biến tất cả logic thành một switch có hàng trăm case nếu một decision table/rule engine chuyên dụng phù hợp hơn.

**Trade-off:** Một sealed type giúp đóng tập biến thể để compiler kiểm tra exhaustive. Nhưng nếu hệ thống thật cần plugin tùy ý thêm Payment hoặc Shipment, thiết kế đóng kín có thể không phù hợp. Hãy chọn abstraction theo khả năng mở rộng cần thiết, không chỉ theo cú pháp bạn muốn dùng.

### Dữ liệu không đáng tin

Pattern matching là **công cụ chọn nhánh theo type và cấu trúc**, không phải cơ chế xác thực/phân quyền. Một record pattern match thành công không đồng nghĩa:
- Người dùng có quyền hủy đơn hàng đó.
- Token thanh toán còn hiệu lực.
- Email là địa chỉ hợp lệ.
- Số lượng có tồn kho.
- Giá từ client là giá đáng tin để charge tiền.

Những điều đó cần domain validation, application authorization và tích hợp hệ thống chuyên biệt. Mini project cố ý giới hạn trong phân loại/định giá để không trộn các trách nhiệm.

## 17. Bài tập mở rộng cho người học

**Bài tập 1 — Guard 9/10:** Thêm test Checkout Express/Card có email hợp lệ và quantity9, quantity10. Kỳ vọng 9 là `EXPRESS_CARD`, 10 là `EXPRESS_BULK_CARD`. Xác định test nào bắt lỗi `> 10`.

**Bài tập 2 — Email blank:** Thêm `new Contact("   ")` cùng Express/Card quantity10. Kỳ vọng không áp dụng promo. Giải thích vì sao guard phải kiểm `email != null` trước `!email.isBlank()`.

**Bài tập 3 — Voucher:** Thêm `Voucher(String code) implements Payment`, cập nhật permits và viết policy: chỉ chấp nhận Standard, áp dụng giảm giá cố định 50 cents nhưng không vượt subtotal. Dự đoán liệu compiler có yêu cầu thêm case Voucher ngay không nếu vẫn có `Checkout(var cart)` cuối. Bổ sung test.

**Bài tập 4 — Same model, new operation:** Viết `String receipt(Result)` để xuất chứng từ demo. Dùng `switch` exhaustive trên `Result`, không in email hay chi tiết Card. Thêm subtype `Pending` và xem compiler phản hồi.

**Bài tập 5 — Chính sách giá:** Chuyển `discountPercent` sang một enum hoặc value type; validate chỉ cho phép 0–100. Thêm phép làm tròn theo contract và test với giá không chia hết cho 10.

**Bài tập 6 — Dự án Java17:** Viết lại `decide` với `instanceof` type patterns và gọi record accessor thủ công, giữ cùng expected outputs. Không dùng record patterns/switch patterns Java21 trong module `--release 17`.

**Bài tập 7 — Thêm phí theo zone:** Cho Express zone NORTH có phí 500 cents, SOUTH 700 cents. Thiết kế guard hoặc helper policy không nhân bản arithmetic. Test kết quả với từng zone, null zone và zone không được hỗ trợ.

**Bài tập 8 — Test chống overflow:** Tạo một ca mà subtotal hợp lệ nhưng payable overflow sau khi cộng phí, và một ca mà `multiplyExact` overflow. So sánh với C17/C19 và giải thích khác nhau ở bước nào.

**Bài tập 9 — Domain invariant:** Di chuyển validation của quantity và unitPrice vào compact constructor `Cart`. Điều chỉnh test: thay vì `Rejected` từ `decide` cho dữ liệu sai, constructor có thể ném `IllegalArgumentException`. Giải thích khi nào chọn policy ở boundary và khi nào chọn invariant trong domain.

**Bài tập 10 — Tách source files:** Đưa records vào domain package, decision engine vào application package, test vào test source set. Viết pipeline chạy Java21 và bảo đảm thêm subtype mới buộc review mọi consumer liên quan.

## 18. Checklist hoàn thành mini project

Một checklist tự đánh giá sau khi thực hành:

1. Mọi record pattern có đúng số component và thứ tự của declaration?
2. `Command`/`Shipment`/`Payment`/`Result` có đúng tập permitted subtypes?
3. Các case `when` đứng trước case không guard tương ứng?
4. `null` selector khác component null đã được xử lý theo contract?
5. `var` chỉ được dùng khi muốn bind component mà không yêu cầu deconstruct sâu?
6. Pattern variables có được dùng đúng scope?
7. `decide` trả `Result`, không tự thực hiện payment/DB side effects?
8. `display` exhaustive đối với các Result subtypes?
9. `isBillable` dùng type pattern/flow scoping đúng?
10. Phép tính tiền không dùng `double` và đã xử lý overflow?
11. Mã Card chỉ nhận bốn chữ số giả định, không thu thập thông tin thẻ thật?
12. Kiểm thử có đủ null, invalid, promo, bình thường, overflow và cancel?
13. Thêm nested Payment subtype có test riêng, không bị fallback che bug?
14. Output xác định, tên file/class và lệnh Java đã khớp?
15. Có thể giải thích lúc nào dùng polymorphism/domain service thay vì pattern switch?

Nếu không trả lời chắc chắn một mục, thử viết thêm test cho chính mục đó. **Build xanh chưa chứng minh nghiệp vụ đúng; test chỉ có happy path cũng chưa đủ**.

## 19. Tổng kết kiến thức

Mini project ShopFlow cho thấy pattern matching có thể làm rõ một luồng xử lý nhiều biến thể mà không phải dùng cast rời rạc:

1. **Sealed hierarchies** mô tả tập Command, Shipment, Payment và Result.
2. **Records** tạo domain data ngắn gọn và giữ component có kiểu.
3. **Nested record patterns** đọc đúng cấu trúc Cart → Customer/Contact → Shipment/Payment.
4. **Guards `when`** chọn rule theo quantity, email và điều kiện hợp lệ.
5. **`switch expressions`** tạo `Result` mà compiler có thể kiểm tra exhaustiveness.
6. **`case null`** quy định xử lý selector null; nested null cần guard/fallback riêng.
7. **`instanceof` type pattern** cho phép hỏi một điều đơn giản về Approved với flow scoping.
8. **Test và exact arithmetic** bảo vệ giá tiền và các quyết định nghiệp vụ.
9. **Compiler feedback** giúp phát hiện subtype chưa được xử lý hoặc case bị dominated, nhưng không thay thế kiểm thử nested variants và domain rules.

Đối với ứng dụng thực, hãy giữ ranh giới rõ giữa **model, decision, calculation, execution và adapter**. Pattern matching là công cụ diễn đạt logic theo kiểu/cấu trúc; giá trị lớn nhất đến từ việc dùng nó đúng chỗ, có invariant và test đáng tin, chứ không chỉ từ cú pháp ngắn hơn.

## Tài liệu tham khảo

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — Sealed Classes and Interfaces: https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html
- Java Language Specification SE 21 — `14.30 Patterns`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30
- Java Language Specification SE 21 — `15.28 switch Expressions`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28
- OpenJDK JEP 394 — Pattern Matching for instanceof: https://openjdk.org/jeps/394
- OpenJDK JEP 395 — Records: https://openjdk.org/jeps/395
- OpenJDK JEP 409 — Sealed Classes: https://openjdk.org/jeps/409
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
