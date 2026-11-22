# Viết record pattern lồng nhau trong Java 21

## 1. Bài thực hành tổng hợp: yêu cầu đặt hàng nhiều lớp dữ liệu

Trong Java, một record có thể chứa một record khác. Khi xử lý dữ liệu từ API, command handler, message queue hoặc domain model, ta thường gặp cấu trúc như:

```text
Request (sealed interface)
├── CancelOrder(id)
└── PlaceOrder(order)
    └── Order(customer, destination, payment, count)
        ├── Customer(name, contact)
        │   └── Contact(email)
        ├── Destination(city, district)
        └── Payment (sealed interface)
            ├── Card(last4)
            └── Cash()
```

Ta muốn viết một hàm **`classify(Request)`** xử lý:
- Yêu cầu null → `NO_REQUEST`.
- Hủy đơn với ID rỗng → `INVALID_CANCEL`; ID hợp lệ → `CANCEL:<id>`.
- Đặt hàng nhưng `order == null` → `MISSING_ORDER`.
- Đơn thiếu customer, destination, payment hoặc `count <= 0` → `INVALID_ORDER`.
- Thanh toán thẻ, số lượng ít nhất 10 và có email → `BULK_CARD`.
- Thanh toán thẻ thông thường → `CARD`.
- Thanh toán tiền mặt → `CASH`.
- Thiếu record sâu hơn như `Customer.contact == null` → `INCOMPLETE_DETAILS`.

Trước đây, code thường dùng một chuỗi `instanceof`, cast và accessor với nhiều nhánh null check. **Nested record patterns** của Java 21 cho phép viết hình dạng dữ liệu cần kiểm tra ngay trong pattern:

```java
// Một case minh họa; các type đầy đủ được khai báo sau.
case PlaceOrder(Order(
        Customer(String name, Contact(String email)),
        Destination(String city, String district),
        Card(String last4), int count)) ->
    "CARD:" + name + ":" + city + ":" + count;
```

Đọc từ ngoài vào: đây là `PlaceOrder` chứa `Order`; `Order` chứa `Customer` với `Contact`, `Destination`, `Card` và số lượng. Nếu các record patterns khớp, Java ràng buộc các component variables vào đúng kiểu, không phải cast thủ công.

**Bài này hướng dẫn từ pattern đơn giản đến pattern lồng nhiều cấp, sau đó kiểm thử trọn vẹn, xử lý null/guard, lỗi compiler và các giới hạn thực tế.**

Phiên bản:
- `record` chính thức từ Java 16.
- `sealed class`/`sealed interface` chính thức từ Java 17.
- **Record patterns (JEP 440)** và **pattern matching cho `switch` (JEP 441)** chính thức từ **Java 21**, không cần `--enable-preview`.

Ví dụ chính dùng `javac --release 21` và một file Java SE duy nhất.

## 2. Phân biệt type pattern, record pattern và nested record pattern

### Type pattern

```java
Object value = "hello";
if (value instanceof String text) {
    System.out.println(text.length());
}
```

`String text` kiểm tra object có kiểu phù hợp và ràng buộc biến `text`. Với `null` là toán hạng của `instanceof`, kết quả luôn false.

### Record pattern

Cho record:

```java
record Destination(String city, String district) {}
```

Ta có thể match trực tiếp:

```java
if (value instanceof Destination(String city, String district)) {
    System.out.println(city + "/" + district);
}
```

`Destination(String city, String district)` là **record pattern**, không phải lời gọi constructor. Nó kiểm tra record ngoài và các component patterns. Khi thành công, `city`/`district` là biến đã được bind.

### Nested record pattern

```java
record Contact(String email) {}
record Customer(String name, Contact contact) {}
```

Khi dùng:

```java
if (value instanceof Customer(String name, Contact(String email))) {
    System.out.println(name + ":" + email);
}
```

Java phải match `Customer` rồi match record `Contact` trong component `contact`. Nếu component contact là null, nested record `Contact(...)` **không khớp**. Đây là một non-match bình thường, không phải `MatchException`.

Sự khác biệt: **type pattern** xác định kiểu và bind; **record pattern** kiểm tra record và tiếp tục match các component; **nested record pattern** dùng một record pattern làm component pattern của record khác.

## 3. Record declaration quyết định cú pháp deconstruction

Mô hình dùng trong chương trình:

```java
sealed interface Request permits PlaceOrder, CancelOrder {}

record PlaceOrder(Order order) implements Request {}
record CancelOrder(String id) implements Request {}

record Order(Customer customer, Destination destination,
             Payment payment, int count) {}
record Customer(String name, Contact contact) {}
record Contact(String email) {}
record Destination(String city, String district) {}

sealed interface Payment permits Card, Cash {}
record Card(String last4) implements Payment {}
record Cash() implements Payment {}
```

**Một record pattern phải có đúng số lượng nested patterns bằng số lượng record components**, theo đúng thứ tự declaration.

Ví dụ `Order` có bốn components:

| Vị trí | Component | Kiểu | Pattern tương ứng |
| --- | --- | --- | --- |
| 1 | `customer` | `Customer` | `Customer(...)` hoặc `var customer` |
| 2 | `destination` | `Destination` | `Destination(...)` hoặc `var destination` |
| 3 | `payment` | `Payment` | `Card(...)`, `Cash()` hoặc `var payment` |
| 4 | `count` | `int` | `int count` hoặc `var count` |

Một mẫu hợp lệ:

```java
Order(var customer, var destination, var payment, int count)
```

Mẫu cụ thể hơn:

```java
Order(Customer(var name, var contact),
      Destination(var city, var district),
      Card(var last4), int count)
```

Mẫu thứ hai **chỉ nhận Order có Payment là Card**, vì `Card(...)` là record pattern cho một subtype của `Payment`.

Không được đổi chỗ component cho “dễ nhớ”: `Order(int count, Customer(...), ...)` sẽ không phù hợp declaration. Không thể viết `Order(Customer customer)` để bỏ qua ba component còn lại. Nếu không cần phân tích sâu, dùng `var` tại mỗi vị trí không cần deconstruct.

**`Cash()` hợp lệ:** Record `Cash` có không component; cặp ngoặc rỗng trong pattern có nghĩa số nested patterns là 0, không phải constructor call.

## 4. Viết nested pattern theo từng bước

Đừng bắt đầu bằng mẫu sáu lớp nếu chỉ cần một field. Mở rộng theo nhu cầu:

### Bước 1 — Kiểm tra type ngoài

```java
if (request instanceof PlaceOrder place) {
    Order order = place.order();
    System.out.println(order);
}
```

`order` có thể null. Lợi ích là code đơn giản, dễ debug; nhược điểm là phải truy cập accessor và kiểm tra cấu trúc bằng code thêm.

### Bước 2 — Bóc tách Order

```java
if (request instanceof PlaceOrder(Order(
        var customer, var destination, var payment, int count))) {
    System.out.println(count);
}
```

Lúc này `PlaceOrder.order()` phải là `Order` khác null. Các biến tham chiếu tạo bởi `var` có thể chứa null.

### Bước 3 — Bóc tách Customer và Destination

```java
if (request instanceof PlaceOrder(Order(
        Customer(String name, var contact),
        Destination(String city, String district),
        var payment, int count))) {
    System.out.println(name + "@" + city + ":" + count);
}
```

Hai nested record patterns mới yêu cầu `customer` và `destination` đều là record tương ứng khác null. Nhưng `contact` chưa phải `Contact(...)` — nó được bind qua `var`.

### Bước 4 — Đi sâu tới Contact và Card

```java
if (request instanceof PlaceOrder(Order(
        Customer(String name, Contact(String email)),
        Destination(String city, String district),
        Card(String last4), int count))) {
    System.out.println(name + ":" + city + ":" + count);
}
```

Giờ matcher cần cả `Customer`, `Contact`, `Destination` và `Card`. `Cash()` không thể khớp `Card(...)`; `customer.contact() == null` cũng làm nested `Contact(...)` không khớp.

**Giữ mức lồng vừa đủ.** Nếu bài toán chỉ dùng `count`, không có lý do thiết kế tốt để bóc tách `Contact.email` và `Card.last4`. Mẫu ngắn hơn giúp code rõ và ít phụ thuộc cấu trúc record.

## 5. Một pattern, nhiều nhánh: guard when

Giả sử đơn thanh toán thẻ với `count >= 10` và email có giá trị là đơn bulk:

```java
// Một case trong switch expression trên Request.
case PlaceOrder(Order(
        Customer(String name, Contact(String email)),
        Destination(String city, String district),
        Card(String last4), int count))
        when count >= 10 && email != null ->
    "BULK_CARD:" + city + ":" + last4 + ":" + count;
```

**Pattern** mô tả cấu trúc, **guard** mô tả điều kiện bổ sung. Guard chỉ được đánh giá sau khi pattern liên quan đã khớp:
- Guard true → case bulk được chọn.
- Guard false → case khác còn được xét.
- Guard ném exception → quá trình chọn case kết thúc bất thường; không coi exception là false.

Sau đó là case Card không guard:

```java
case PlaceOrder(Order(
        Customer(String name, Contact(String email)),
        Destination(String city, String district),
        Card(String last4), int count)) ->
    "CARD:" + name + ":" + city + ":" + count;
```

Case có guard phải đứng **trước** case cùng record pattern nhưng không guard. Nếu đảo thứ tự, case tổng quát sẽ **dominate** case có guard phía sau.

Một điểm không trực giác: `new Contact(null)` vẫn là record `Contact` khác null, và `Contact(String email)` có thể ràng buộc `email == null` tại vị trí component có kiểu `String`. Điều này là quy tắc **unconditional type pattern** trong Java 21, không có nghĩa `null instanceof String` sẽ trả true. Vì vậy guard cần kiểm tra null trước khi dùng `email.isBlank()`.

## 6. Null ở bốn mức: tại sao cần phân biệt?

| Trường hợp | Ví dụ | Kết quả |
| --- | --- | --- |
| Selector của `instanceof` là null | `null instanceof Customer(...)` | False |
| Selector của `switch` null và có case null | `case null -> ...` | Case null |
| Component Order null nhưng dùng `var` | `PlaceOrder(var order)` | Bind `order=null`, pattern ngoài có thể match |
| Component Order null nhưng dùng nested `Order(...)` | `PlaceOrder(Order(...))` | Nested record pattern không match |
| Contact record tồn tại, email null | `Contact(String email)` | Type pattern component có thể bind null |
| Customer record tồn tại nhưng contact null | `Customer(String n, Contact(...))` | Nested `Contact(...)` không match |

Đây là lý do demo có ba lớp xử lý:

```java
case null -> "NO_REQUEST";

case PlaceOrder(var order) when order == null ->
    "MISSING_ORDER";

case PlaceOrder(Order(
        var customer, var destination, var payment, int count))
        when customer == null || destination == null ||
             payment == null || count <= 0 ->
    "INVALID_ORDER";
```

Mẫu `PlaceOrder(Order(...))` chỉ chạy khi order thực sự là một record `Order`. Dùng `var` trong các component giúp guard có thể kiểm tra những field null mà không đòi match một nested record cụ thể.

Về cuối switch, một case:

```java
case PlaceOrder(var order) -> "INCOMPLETE_DETAILS";
```

được giữ lại **sau các case chuyên biệt** để nhận những trường hợp nested data còn thiếu, chẳng hạn `Customer.contact == null`. Nếu đặt nó lên trước, các case Card/Cash sau đó sẽ bị dominated.

**Thiết kế domain:** Một sản phẩm thật thường nên chặn dữ liệu không hợp lệ ở constructor hoặc boundary. Trong bài thực hành, các record cố ý không validate ngay để quan sát từng kết quả pattern. Không nên coi “có fallback” đồng nghĩa cho phép lưu object sai invariant.

## 7. Chương trình Java 21 hoàn chỉnh và 13 ca kiểm thử

Tạo file **`NestedRecordPatternsWorkshop.java`** với nội dung sau. Mã chỉ dùng Java SE và đã được chạy với `--release 21`:

```java
import java.util.Objects;

public class NestedRecordPatternsWorkshop {
    sealed interface Request permits PlaceOrder, CancelOrder {}
    record PlaceOrder(Order order) implements Request {}
    record CancelOrder(String id) implements Request {}

    record Order(Customer customer, Destination destination,
                 Payment payment, int count) {}
    record Customer(String name, Contact contact) {}
    record Contact(String email) {}
    record Destination(String city, String district) {}
    sealed interface Payment permits Card, Cash {}
    record Card(String last4) implements Payment {}
    record Cash() implements Payment {}

    static String classify(Request request) {
        return switch (request) {
            case null -> "NO_REQUEST";

            case CancelOrder(String id)
                    when id == null || id.isBlank() ->
                "INVALID_CANCEL";

            case CancelOrder(String id) ->
                "CANCEL:" + id;

            case PlaceOrder(var order) when order == null ->
                "MISSING_ORDER";

            case PlaceOrder(Order(
                    var customer, var destination,
                    var payment, int count))
                    when customer == null || destination == null ||
                         payment == null || count <= 0 ->
                "INVALID_ORDER";

            case PlaceOrder(Order(
                    Customer(String name, Contact(String email)),
                    Destination(String city, String district),
                    Card(String last4), int count))
                    when count >= 10 && email != null ->
                "BULK_CARD:" + city + ":" + last4 + ":" + count;

            case PlaceOrder(Order(
                    Customer(String name, Contact(String email)),
                    Destination(String city, String district),
                    Card(String last4), int count)) ->
                "CARD:" + name + ":" + city + ":" + count;

            case PlaceOrder(Order(
                    Customer(String name, Contact(String email)),
                    Destination(String city, String district),
                    Cash(), int count)) ->
                "CASH:" + name + ":" + district + ":" + count;

            case PlaceOrder(var order) ->
                "INCOMPLETE_DETAILS";
        };
    }

    static void assertCase(
            String label, Request request, String expected) {
        String actual = classify(request);
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError(
                label + ": expected=" + expected +
                ", actual=" + actual);
        }
        System.out.println(label + " -> " + actual);
    }

    record Traced(String value) {
        static int reads;

        @Override
        public String value() {
            reads++;
            return value;
        }
    }

    record Envelope(Traced traced) {}

    record Broken(String value) {
        @Override
        public String value() {
            throw new IllegalStateException("accessor failure");
        }
    }

    record BrokenEnvelope(Broken broken) {}

    public static void main(String[] args) {
        Customer lan =
            new Customer("Lan", new Contact("lan@example.test"));
        Destination danang =
            new Destination("Da Nang", "Hai Chau");
        Customer mai =
            new Customer("Mai", new Contact("mai@example.test"));

        assertCase("S01", null, "NO_REQUEST");
        assertCase("S02", new CancelOrder("A1"), "CANCEL:A1");
        assertCase("S03", new CancelOrder(" "), "INVALID_CANCEL");

        assertCase("S04", new PlaceOrder(new Order(
            lan, danang, new Card("1234"), 2)),
            "CARD:Lan:Da Nang:2");

        assertCase("S05", new PlaceOrder(new Order(
            lan, danang, new Card("1234"), 12)),
            "BULK_CARD:Da Nang:1234:12");

        assertCase("S06", new PlaceOrder(new Order(
            new Customer("Lan", new Contact(null)),
            danang, new Card("1234"), 12)),
            "CARD:Lan:Da Nang:12");

        assertCase("S07", new PlaceOrder(new Order(
            mai, new Destination("Ha Noi", "Ba Dinh"),
            new Cash(), 3)),
            "CASH:Mai:Ba Dinh:3");

        assertCase("S08", new PlaceOrder(null),
            "MISSING_ORDER");

        assertCase("S09", new PlaceOrder(new Order(
            lan, danang, new Card("1234"), 0)),
            "INVALID_ORDER");

        assertCase("S10", new PlaceOrder(new Order(
            lan, danang, null, 2)),
            "INVALID_ORDER");

        assertCase("S11", new PlaceOrder(new Order(
            null, danang, new Cash(), 2)),
            "INVALID_ORDER");

        assertCase("S12", new PlaceOrder(new Order(
            lan, null, new Cash(), 2)),
            "INVALID_ORDER");

        assertCase("S13", new PlaceOrder(new Order(
            new Customer("Lan", null), danang, new Cash(), 2)),
            "INCOMPLETE_DETAILS");

        Object complete = new Envelope(new Traced("OK"));
        if (!(complete instanceof
                Envelope(Traced(String value)) &&
                value.equals("OK"))) {
            throw new AssertionError("nested matching failed");
        }
        System.out.println("ACCESSOR_READS=" + Traced.reads);

        Object missingNested = new Envelope(null);
        boolean nestedMatch =
            missingNested instanceof
                Envelope(Traced(String missingValue));
        System.out.println("NULL_NESTED_MATCH=" + nestedMatch);

        try {
            Object broken =
                new BrokenEnvelope(new Broken("x"));
            boolean ignored = broken instanceof
                BrokenEnvelope(Broken(String brokenValue));
            throw new AssertionError(
                "Expected MatchException, got " + ignored);
        } catch (MatchException ex) {
            System.out.println("ACCESSOR_ERROR=" +
                ex.getClass().getSimpleName() + ":" +
                ex.getCause().getClass().getSimpleName());
        }

        System.out.println("TESTS=13");
    }
}
```

Biên dịch và chạy trên **JDK 21 trở lên**:

```bash
javac --release 21 NestedRecordPatternsWorkshop.java
java NestedRecordPatternsWorkshop
```

**Stdout chính xác:**

```text
S01 -> NO_REQUEST
S02 -> CANCEL:A1
S03 -> INVALID_CANCEL
S04 -> CARD:Lan:Da Nang:2
S05 -> BULK_CARD:Da Nang:1234:12
S06 -> CARD:Lan:Da Nang:12
S07 -> CASH:Mai:Ba Dinh:3
S08 -> MISSING_ORDER
S09 -> INVALID_ORDER
S10 -> INVALID_ORDER
S11 -> INVALID_ORDER
S12 -> INVALID_ORDER
S13 -> INCOMPLETE_DETAILS
ACCESSOR_READS=1
NULL_NESTED_MATCH=false
ACCESSOR_ERROR=MatchException:IllegalStateException
TESTS=13
```

Có **13 ca phân loại** S01–S13, thêm các quan sát về accessor/nested null/MatchException. Hàm `assertCase` ném `AssertionError` khi sai, nên không cần bật cờ `-ea`.

**Lưu ý:** Các chuỗi, email và bốn số cuối thẻ trong demo đều là dữ liệu giả. Trong code production, không tự động ghi log toàn bộ record; thông tin thanh toán, token và dữ liệu cá nhân phải được kiểm soát theo chính sách bảo mật.

## 8. Giải thích kết quả chi tiết

| Test | Input quan trọng | Output | Ý nghĩa |
| --- | --- | --- | --- |
| S01 | Request null | `NO_REQUEST` | `case null` |
| S02 | CancelOrder ID `A1` | `CANCEL:A1` | Guard invalid false, case Cancel thường |
| S03 | CancelOrder ID trống | `INVALID_CANCEL` | `isBlank()` true |
| S04 | Card, count2, email có giá trị | `CARD` | Guard bulk false |
| S05 | Card, count12, email có giá trị | `BULK_CARD` | Guard bulk true |
| S06 | Card, count12, Contact.email null | `CARD` | Record Contact vẫn khớp, guard bulk false |
| S07 | Cash, count3 | `CASH` | Nested `Cash()` khớp |
| S08 | PlaceOrder.order null | `MISSING_ORDER` | `var order` bind null |
| S09 | Order.count 0 | `INVALID_ORDER` | Guard count <=0 |
| S10 | Order.payment null | `INVALID_ORDER` | Guard nhận null Payment |
| S11 | Order.customer null | `INVALID_ORDER` | Guard nhận null Customer |
| S12 | Order.destination null | `INVALID_ORDER` | Guard nhận null Destination |
| S13 | Customer.contact null | `INCOMPLETE_DETAILS` | Nested Contact không khớp, fallback |

### Phân tích S06

`new Customer("Lan", new Contact(null))` có record Contact khác null. `Contact(String email)` match record; component `email` có thể được bind với null vì type pattern unconditional tại component kiểu String. `count>=10` đúng nhưng `email!=null` false. Vì vậy case BULK_CARD bị bỏ qua, case CARD không guard được chọn.

Nếu logic doanh nghiệp yêu cầu email không được null, hãy thêm validation hoặc case `INVALID_EMAIL`. Đây là một quyết định về **domain contract**, không phải tự động được bảo đảm bởi nested record pattern.

### Phân tích S13

`new Customer("Lan", null)` làm nested `Contact(String email)` không khớp. Vì cả pattern Card và Cash đều cần `Customer(..., Contact(...))`, chúng không áp dụng. Case `PlaceOrder(var order)` cuối cùng nhận yêu cầu này và trả `INCOMPLETE_DETAILS`.

**Không nhầm:** Nested pattern không match là kết quả bình thường. Nó không ném `MatchException` chỉ vì record component null.

### Tại sao có hai sealed hierarchy?

`Request` bao gồm `PlaceOrder` và `CancelOrder`, còn `Payment` bao gồm `Card` và `Cash`. Compiler có thể xác nhận root `switch` exhaustive khi case CancelOrder tổng quát và PlaceOrder fallback đã bao phủ mọi subtype Request. Tuy nhiên, compiler **không chứng minh mọi loại Payment được xử lý nghiệp vụ đúng** nếu có một fallback PlaceOrder rộng.

Nếu thêm `Voucher` vào `Payment` mà quên case riêng, fallback vẫn có thể khiến root switch biên dịch, nhưng trả `INCOMPLETE_DETAILS` cho voucher. Vì vậy cần test riêng cho từng nested subtype, không chỉ dựa vào tính exhaustive của root.

## 9. Phạm vi biến và flow scoping

Các pattern variables được ràng buộc ở một nhánh có thể dùng trong body của nhánh đó và trong guard thích hợp. Ví dụ:

```java
case PlaceOrder(Order(
        Customer(String name, Contact(String email)),
        Destination(String city, String district),
        Card(String last4), int count))
        when count >= 10 && email != null ->
    "BULK_CARD:" + city + ":" + last4 + ":" + count;
```

`name`, `email`, `city`, `district`, `last4` và `count` đều có kiểu xác định, nhưng **không tự trở thành biến ở ngoài `switch`**.

Trong `instanceof`:

```java
if (obj instanceof Customer(String name, Contact(String email))
        && email != null) {
    System.out.println(name + ":" + email.toLowerCase());
}
```

Nhánh phải của `&&` dùng được `email` vì Java chỉ đánh giá nó khi pattern bên trái đã khớp. Nhưng khi dùng biến bên ngoài vùng đã được bảo đảm match, compiler sẽ từ chối.

Ví dụ cố ý sai:

```java
record Point(int x, int y) {}

static void check(Object obj) {
    if (obj instanceof Point(int x, int y)) {
        System.out.println(x);
    }
    System.out.println(x); // cannot find symbol
}
```

Javac đã được thử với trường hợp này và báo thiếu biến `x` tại dòng ngoài `if`. Với những biểu thức có điều kiện phức tạp, đừng nhầm phạm vi pattern variable với phạm vi của biến local thông thường; compiler áp dụng quy tắc **flow scoping**.

### Tránh trùng tên biến

Trong một method có nhiều `instanceof`, pattern variables có thể có scope kéo dài ở một số đường điều khiển. Dùng đi dùng lại tên `value` có thể khiến compiler báo biến đã được khai báo. Trong demo, các tên `missingValue` và `brokenValue` khác với `value` để tránh xung đột.

## 10. Kiểm thử record accessor và MatchException

Khi deconstruct record, Java dùng accessor để lấy component. Nếu accessor tùy chỉnh có side effect, nested record pattern có hành vi quan sát được.

### Accessor được gọi khi nested pattern cần đọc dữ liệu

```java
record Traced(String value) {
    static int reads;

    @Override
    public String value() {
        reads++;
        return value;
    }
}
record Envelope(Traced traced) {}
```

Với:

```java
Object complete = new Envelope(new Traced("OK"));
boolean match = complete instanceof Envelope(Traced(String text));
```

`Traced.value()` được gọi để match `Traced(String text)`. Trong chương trình đầy đủ, output là:

```text
ACCESSOR_READS=1
```

**Không lấy số lần gọi để suy ra thời gian nanosecond:** JIT có thể inline accessor; những pattern khác nhau có thể yêu cầu các bước khác nhau. Hạn chế accessor có side effect, đặc biệt khi các case lồng nhau nhiều cấp.

### Nested record null không match

```java
Object missingNested = new Envelope(null);
boolean result =
    missingNested instanceof Envelope(Traced(String text));
```

Kết quả false. `Envelope` ngoài tồn tại, nhưng component `traced` bằng null nên nested record `Traced(...)` không thể match.

### Accessor ném lỗi

```java
record Broken(String value) {
    @Override
    public String value() {
        throw new IllegalStateException("accessor failure");
    }
}
record BrokenEnvelope(Broken broken) {}
```

Khi match:

```java
Object broken = new BrokenEnvelope(new Broken("x"));
boolean ignored =
    broken instanceof BrokenEnvelope(Broken(String text));
```

Lỗi `IllegalStateException` trong accessor được Java 21 bọc thành `MatchException`, với `getCause()` là exception gốc. Demo bắt lỗi và in:

```text
ACCESSOR_ERROR=MatchException:IllegalStateException
```

**Bốn kết quả phải phân biệt:**
- Pattern không khớp vì sai subtype → false hoặc case tiếp theo.
- Nested record không khớp vì null → false hoặc case tiếp theo.
- Accessor ném lỗi trong quá trình deconstruction → `MatchException` với cause gốc.
- Guard hoặc body ném lỗi → exception theo đường đánh giá tương ứng, không tự biến thành non-match.

Vì vậy đừng catch mọi `MatchException` rồi trả `INCOMPLETE_DETAILS` như thể đây chỉ là dữ liệu thiếu. Nó có thể che một lỗi accessor thật sự.

## 11. Generic record patterns và suy luận kiểu

Java 21 cho phép kết hợp nested patterns với generic records:

```java
record Box<T>(T value) {}
record Parcel(Box<String> tracking, int pieces) {}

static String inspect(Object obj) {
    if (obj instanceof Parcel(Box(var code), int pieces)) {
        return "PARCEL:" + code + ":" + pieces;
    }
    return "NO_MATCH";
}
```

`var code` được suy luận theo component của `Box<String>`; ở ngữ cảnh này nó có kiểu `String`. Không cần cast thủ công trong body.

Ba ca đã kiểm thử:

```java
System.out.println(inspect(new Parcel(new Box<>("ZX"), 2)));
System.out.println(inspect(new Parcel(new Box<>(null), 0)));
System.out.println(inspect(new Parcel(null, 3)));
```

```text
PARCEL:ZX:2
PARCEL:null:0
NO_MATCH
```

Kết quả thứ hai cho thấy `Box` tồn tại nhưng component `value` bằng null vẫn có thể bind qua `var`. Kết quả thứ ba cho thấy nested `Box(...)` không match vì chính object Box bị null.

**Không nhầm với generic reification:** Java vẫn sử dụng type erasure cho generic type arguments. Việc compiler suy luận kiểu của một component qua pattern không có nghĩa mọi type argument được kiểm tra đầy đủ tại runtime như một kiểu reified. Cần tuân thủ quy tắc type checking của Java và không dùng unchecked cast để “ép” pattern hợp lệ.

## 12. Ba lỗi compiler đã tái tạo

### 12.1. Sai số lượng nested patterns

Record:

```java
record Point(int x, int y) {}
```

Pattern sai:

```java
// CỐ Ý SAI:
boolean matches = obj instanceof Point(int x);
```

Javac Java 21 báo:

```text
incorrect number of nested patterns
required: int,int
found: int
```

**Sửa:** Dùng `Point(int x, int y)` hoặc `Point(var x, var y)`. Record pattern phải có hai component patterns như declaration.

### 12.2. Case bị dominated

Giả sử `record Pair(int a, int b) {}`:

```java
// CỐ Ý SAI thứ tự:
case Pair(int a, int b) -> "any";
case Pair(int a, int b) when a > 0 -> "positive";
```

Compiler báo tương đương:

```text
this case label is dominated by a preceding case label
```

Case không guard đứng trước đã bao phủ toàn bộ Pair. **Sửa:** Đặt case có guard `a > 0` trước case không guard.

### 12.3. Pattern variable ngoài scope

Code:

```java
if (obj instanceof Point(int x, int y)) {
    System.out.println(x);
}
System.out.println(x); // CỐ Ý SAI
```

Compiler báo:

```text
cannot find symbol
symbol: variable x
```

**Sửa:** Dùng `x` trong vùng Java đã chứng minh pattern match thành công, hoặc chuyển giá trị sang một biến được khai báo đúng scope.

### Hai lỗi cần tránh khác

**Sai kiểu component:** `Order` khai báo component thứ ba là `Payment`, nên không thể thay bằng nested record pattern cho một kiểu không liên quan như `Destination(...)` rồi mong runtime tự cast. Compiler áp dụng type checking tại mỗi cấp.

**Sai Java release:** File dùng record patterns và case `when` phải biên dịch với release hỗ trợ, ví dụ:

```bash
javac --release 21 NestedRecordPatternsWorkshop.java
```

`javac --release 17` không chấp nhận các tính năng Java21-only này. Bật `--enable-preview` ở Java17 không phải cách biến feature đã final ở Java21 thành mã chạy được trên Java17.

## 13. Khi nào nên dùng pattern lồng sâu?

**Phù hợp khi:**
- Dữ liệu được mô hình hóa bằng immutable records nhiều cấp.
- Consumer thực sự cần đọc cùng lúc nhiều component sâu.
- Cần phân loại DTO, message, command hoặc sealed algebraic data type.
- Muốn dùng compiler để bảo đảm kiểu, scope, dominance và exhaustiveness ở mức thích hợp.
- Có test cụ thể cho các dạng dữ liệu đầu vào và null.

**Không nên quá lạm dụng khi:**
- Chỉ dùng một component đơn giản nhưng deconstruct cả cây record.
- Nested hierarchy thay đổi thường xuyên, làm hàng chục consumer phải sửa.
- Accessors có side effect, I/O hoặc exception khó đoán.
- Guard chứa business rule lớn lặp lại ở nhiều adapter.
- Domain behavior cần được đặt trên type hoặc domain service để tránh nhân bản logic.

Một phương án ít lồng hơn khi chỉ cần count:

```java
if (request instanceof PlaceOrder(Order(
        var customer, var destination, var payment, int count))) {
    System.out.println(count);
}
```

Mẫu này rõ hơn việc bóc tách mọi chi tiết của Customer, Contact, Destination và Payment chỉ để đọc `count`.

### Nếu record phải luôn hợp lệ

Có thể đặt invariant ngay trong compact constructor:

```java
// Định nghĩa Order THAY THẾ cho thiết kế production;
// không khai báo trùng với Order của chương trình hoàn chỉnh.
record Order(Customer customer, Destination destination,
             Payment payment, int count) {
    Order {
        Objects.requireNonNull(customer, "customer");
        Objects.requireNonNull(destination, "destination");
        Objects.requireNonNull(payment, "payment");
        if (count <= 0) {
            throw new IllegalArgumentException("invalid count");
        }
    }
}
```

Lúc này không còn cần những case nhận `new Order(null,...)` nếu object không thể được tạo hợp lệ. Nhưng các nested components sâu hơn, như `Customer.contact`, cũng cần invariant nếu muốn bảo đảm non-null. Việc pattern thành công không tự chứng minh toàn bộ domain invariant.

## 14. Checklist test và refactor

Khi viết nested record pattern, hãy tự kiểm tra:

1. Mỗi record pattern có đúng **số component, thứ tự và kiểu** theo declaration?
2. Record nào có thể null ở selector hoặc component?
3. Vị trí nào chỉ cần `var`, vị trí nào phải match nested record cụ thể?
4. Guard `when` có kiểm tra null trước khi dereference?
5. Có case không guard/tổng quát nào đang dominate case chuyên biệt?
6. Pattern variables có nằm trong flow scope của Java?
7. Các subtype của sealed root có được cover bởi switch không?
8. Các subtype **lồng bên trong** như Payment có test riêng không?
9. Có fallback nào đang âm thầm che việc thêm subtype mới?
10. Accessor có thể ném exception hoặc side effect? Có cần thiết không?
11. Nếu cấu trúc record đổi, đã build lại và test mọi consumer liên quan?
12. Đã thử input sai kiểu, record ngoài null, component null, nested record null, guard false/true?
13. Đã kiểm chứng stdout thay vì chỉ dựa vào việc mã biên dịch?
14. Các output/log có chứa dữ liệu nhạy cảm không?
15. Có thể viết pattern ngắn hơn mà vẫn rõ nghĩa?

Một bộ test tốt cần bao phủ cả **match**, **non-match**, **guard** và **abrupt completion**; không chỉ kiểm tra happy path với dữ liệu hoàn chỉnh.

## 15. Bài tập tự làm

**Bài tập 1 — Thêm payment:** Bổ sung `record Voucher(String code) implements Payment` và cập nhật `permits`. Thêm nhánh `VOUCHER` vào `classify`, test với code hợp lệ và code null. Quan sát rằng fallback PlaceOrder khiến root switch có thể vẫn compile trước khi có case Voucher.

**Bài tập 2 — Email rỗng:** Thêm case trả `INVALID_EMAIL` nếu `Contact.email` null hoặc blank. Test null, `""`, `"   "` và email bình thường. Đừng gọi `email.isBlank()` trước null check.

**Bài tập 3 — Rút ngắn pattern:** Viết method `int count(Request request)` chỉ dùng `count` từ Order, không deconstruct Contact hay Payment. Cân nhắc cách xử lý `PlaceOrder(null)` và `CancelOrder`.

**Bài tập 4 — Sai scope:** Đưa một pattern variable ra ngoài `if`, quan sát lỗi javac, sửa bằng cách giữ code trong scope hoặc gán giá trị vào một result type.

**Bài tập 5 — Accessor ném lỗi:** Đổi `Broken.value()` thành ném `IllegalArgumentException`. Kiểm tra `MatchException.getCause()` và phân biệt lỗi đó với nested null non-match.

**Bài tập 6 — Generic:** Tạo `record Box<T>(T value)` và `record ParcelInt(Box<Integer> value)`. Dùng nested `Box(var number)`, test Box null và value null.

**Bài tập 7 — Ma trận null:** Lập bảng expected cho selector null, PlaceOrder.order null, Order.customer null, Customer.contact null, Contact.email null, Destination null, Payment null và count0. Cập nhật classifying method/test theo contract riêng.

**Bài tập 8 — Refactor domain:** Nếu tính chiết khấu bulk được nhiều consumer dùng, thiết kế domain method/service giữ rule duy nhất; sử dụng nested patterns ở adapter/mapping khi cần. Nêu lý do không nên copy cùng công thức vào nhiều `switch`.

## 16. Kết luận

**Record pattern lồng nhau** giúp Java 21 mô tả và bóc tách dữ liệu record theo đúng hình dạng khi matching. Kết hợp `sealed`, `switch`, `when` và `var` cho phép viết những nhánh cụ thể mà compiler có thể kiểm tra kiểu, phạm vi và dominance.

Những điểm quan trọng nhất:
- **Đúng cấu trúc:** số lượng/thứ tự component phải khớp declaration.
- **Đúng null:** selector null, nested record null và component null được xử lý khác nhau.
- **Đúng thứ tự:** case có guard/cụ thể đứng trước fallback rộng.
- **Đúng phạm vi:** pattern variables chỉ dùng ở nơi compiler chứng minh đã bind.
- **Đúng nghiệp vụ:** exhaustive switch không thay test cho từng nested subtype và mỗi giá trị biên.

Hãy bắt đầu bằng pattern nông, tăng độ sâu theo nhu cầu, giữ accessor/guard dễ dự đoán và luôn kiểm thử cả trường hợp khớp, không khớp lẫn ném exception.

## Tài liệu tham khảo

- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java Language Specification SE 21 — `14.30 Patterns`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30
- Java Language Specification SE 21 — `15.20.2 instanceof`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2
- Java SE 21 API — MatchException: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
