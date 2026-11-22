# Refactor cast lồng nhau bằng pattern matching trong Java 21

## 1. Mục tiêu và bối cảnh

Một đoạn mã Java legacy thường nhận `Object` hoặc dữ liệu qua nhiều wrapper, nên phải liên tục **kiểm tra kiểu → ép kiểu → truy cập thành phần → kiểm tra kiểu tiếp**. Khi các phép cast lồng nhau, phần nghiệp vụ bị che bởi nhiều lớp `if` và những biểu thức như `((Address) ((Customer) ((Shipment) raw).customer()).address()).city()` khó đọc, dễ sai khi một cấp bị `null` hoặc sai kiểu.

**Refactor cast lồng nhau** là thay chuỗi kiểm tra/cast thủ công bằng **type patterns**, **record patterns lồng nhau** và **guard clauses**, giúp Java vừa kiểm tra kiểu hoặc cấu trúc vừa tạo biến có kiểu chính xác. Quan trọng hơn, refactor cần giữ hành vi có chủ đích: giá trị trả về, ưu tiên lỗi, ngoại lệ và điều kiện null.

Tính năng theo phiên bản:

- **Java 16+ (JEP 394):** `instanceof Type variable` cho phép kiểm tra và ràng buộc biến cùng lúc.
- **Java 21+ (JEP 440):** `record patterns` và nested record patterns cho phép phân rã record nhiều cấp.
- **Java 21+ (JEP 441):** type/record patterns dùng được trong `switch` với guard `when`.
- **Java 22+ (JEP 456):** có unnamed pattern `_` để không cần đặt tên biến component không sử dụng. Các ví dụ chạy của bài giữ tương thích **Java 21**.

Bạn sẽ biết cách chuyển mã cũ từng bước, khi nào dùng type pattern thay vì nested record pattern, cách kiểm tra semantics, và cách kiểm thử bản trước/sau.

## 2. Chuỗi cast cũ: ba tầng record, hai component kiểu Object

Giả sử có các record sau:

```java
record Address(String city, String street) {}
record Customer(String name, Object address) {}
record Shipment(Object customer, int quantity) {}
```

Dùng `Object` ở hai component trung gian để mô phỏng dữ liệu legacy chưa khai báo kiểu tĩnh chặt. Trong hệ thống mới được thiết kế tốt, có thể chuyển hai component đó thành `Customer` và `Address`; ở đây chúng là `Object` để việc kiểm tra và ép kiểu có ý nghĩa.

Muốn lấy thành phố và số lượng vận chuyển, một cách viết cũ là:

```java
if (!(value instanceof Shipment)) return "Invalid structure";
Shipment shipment = (Shipment) value;

if (!(shipment.customer() instanceof Customer)) return "Invalid structure";
Customer customer = (Customer) shipment.customer();

if (!(customer.address() instanceof Address)) return "Invalid structure";
Address address = (Address) customer.address();

String city = address.city();
if (city == null || city.isBlank()) return "Missing city";
if (shipment.quantity() <= 0) return "Invalid quantity";

return "Ship " + shipment.quantity() + " for "
        + customer.name() + " to " + city;
```

Mỗi `instanceof` kiểm tra kiểu rồi một biểu thức `(Type) object` lặp lại thông tin đó để có biến typed. Điều kiện kiểm tra đã bảo vệ cast nhưng vẫn dễ xảy ra lỗi khi bảo trì: quên kiểm tra một cấp, đánh sai thứ tự, ép sai đối tượng hoặc gọi getter trên null.

Đây là **baseline có kiểm tra**, trả chuỗi `Invalid structure` nếu cây dữ liệu không đủ ba record đúng kiểu. Khi refactor, ta so sánh bản mới với baseline này, kể cả khi `Shipment.customer()` chứa một `String` hoặc `Customer.address()` là null.

## 3. Bước 1: chuyển instanceof + cast thành type pattern

Từ Java 16:

```java
// Trước:
if (!(value instanceof Shipment)) return "Invalid structure";
Shipment shipment = (Shipment) value;

// Sau:
if (!(value instanceof Shipment shipment)) return "Invalid structure";
```

Pattern `Shipment shipment` vừa kiểm tra kiểu vừa khai báo biến `shipment` có kiểu tĩnh `Shipment`. Áp dụng tương tự cho các cấp trong:

```java
if (!(value instanceof Shipment shipment)) return "Invalid structure";
if (!(shipment.customer() instanceof Customer customer)) return "Invalid structure";
if (!(customer.address() instanceof Address address)) return "Invalid structure";

String city = address.city();
if (city == null || city.isBlank()) return "Missing city";
if (shipment.quantity() <= 0) return "Invalid quantity";

return "Ship " + shipment.quantity() + " for "
        + customer.name() + " to " + city;
```

Lúc này không còn cast thủ công; chỉ có những biến `shipment`, `customer`, `address` đã được ràng buộc an toàn. Nhờ **flow scoping**, biến vẫn có thể dùng **sau** một guard dạng `if (!(x instanceof Type t)) return ...;`. Đường đi mà pattern thất bại đã kết thúc bằng `return`, nên mọi luồng chạy xuống dưới đều có pattern khớp.

Nếu nhánh thất bại chỉ ghi log mà không thoát, biến pattern không được bảo đảm:

```java
// KHÔNG BIÊN DỊCH vì nhánh thất bại có thể rơi xuống.
if (!(value instanceof Shipment shipment)) {
    System.out.println("Wrong type");
}
System.out.println(shipment.quantity());
```

Hãy kết thúc nhánh guard bằng `return`, `throw` hoặc tái cấu trúc để biến chỉ được dùng khi compiler biết chắc đã khớp.

Ta cũng có thể nối type pattern bằng `&&`:

```java
if (value instanceof Shipment shipment
        && shipment.customer() instanceof Customer customer
        && customer.address() instanceof Address address) {
    System.out.println(address.city());
}
```

`&&` đánh giá từ trái sang phải và ngắn mạch: khi không khớp `Shipment`, không đọc `customer()`; khi không khớp `Customer`, không đọc `address()`. Các biến được dùng trong thân `if` sau khi tất cả điều kiện đúng. Nếu nghiệp vụ có nhiều kiểm tra lỗi riêng, các guard clauses tuần tự thường rõ ràng hơn một biểu thức `&&` rất dài.

## 4. Bước 2: gộp nhiều cast thành nested record pattern

Khi **mọi tầng cần phân rã đều là record**, Java 21 cho phép biểu đạt cây cấu trúc trực tiếp trong một pattern:

```java
if (!(value instanceof Shipment(
        Customer(var name, Address(var city, var street)), var quantity))) {
    return "Invalid structure";
}
if (city == null || city.isBlank()) return "Missing city";
if (quantity <= 0) return "Invalid quantity";
return "Ship " + quantity + " for " + name + " to " + city;
```

Đọc từ ngoài vào trong:

1. `Shipment(...)` yêu cầu đối tượng ngoài là `Shipment`, có component thứ nhất `customer` và thứ hai `quantity`.
2. `Customer(...)` khớp component `customer` (mặc dù được khai báo là `Object`). Nếu là null hoặc sai kiểu, toàn pattern không khớp.
3. `var name` lấy component tên của `Customer`. `Address(...)` tiếp tục kiểm tra/giải cấu trúc component `address`.
4. `var city`, `var street` lấy hai component `String`. `var quantity` lấy component `int`.
5. Phần code sau guard chỉ chạy khi toàn bộ cây record được khớp; sau đó mới kiểm tra các ràng buộc nghiệp vụ.

**Số pattern con phải đúng số component và đúng thứ tự khai báo.** `Shipment(Customer(Address(var city)))` không hợp lệ vì thiếu các vị trí component tương ứng. Với Java 21, muốn biểu đạt “không dùng street”, có thể đặt `var ignoredStreet`. Với Java 22 trở lên, unnamed pattern `_` giúp bỏ qua việc đặt tên nhưng vẫn phải chiếm đúng một vị trí.

Kết hợp record pattern với guard clause làm code nông hơn: một guard kiểm tra cấu trúc, các guard sau kiểm tra nội dung và nghiệp vụ, cuối cùng trả kết quả thành công. Tuy nhiên, không phải record pattern nào càng dài càng tốt. Nếu cần thông báo riêng `Missing customer` và `Missing address`, nên giữ các kiểm tra từng tầng để biết cấp nào hỏng.

## 5. Bảo toàn null, lỗi và ngoại lệ

Refactor đúng cần xác định rõ **đầu vào nào khớp, đầu vào nào bị từ chối và kết quả từ chối là gì**.

| Trường hợp | Chuỗi type pattern | Nested record pattern | Kết quả với guard ví dụ |
| --- | --- | --- | --- |
| `value == null` | `instanceof Shipment` false | `Shipment(...)` không khớp | `Invalid structure` |
| `value` không phải `Shipment` | Kiểm tra ngoài false | Record ngoài không khớp | `Invalid structure` |
| `Shipment.customer == null` | `instanceof Customer` false | `Customer(...)` không khớp | `Invalid structure` |
| `Shipment.customer` là `String` | Sai kiểu `Customer` | Nested `Customer(...)` không khớp | `Invalid structure` |
| `Customer.address == null` hoặc sai kiểu | `instanceof Address` false | `Address(...)` không khớp | `Invalid structure` |
| `Address.city == null` | `Address` khớp, component null | `var city` ràng buộc null | `Missing city` |
| `Address.city == " "` | `isBlank()` true | Như type pattern | `Missing city` |
| `Shipment.quantity <= 0`, cấu trúc đúng | Kiểm tra cuối thất bại | Kiểm tra cuối thất bại | `Invalid quantity` |

**Null của record con khác null của component được ràng buộc bằng `var`.** `Address(...)` không khớp với bản thân record địa chỉ là null, nhưng `Address(var city, ...)` có thể khớp khi record tồn tại mà `city` bằng null. Do đó cần kiểm tra `city == null || city.isBlank()`. Toán tử `||` short-circuit, tránh gọi `isBlank()` trên null.

Đừng giả định refactor luôn bảo toàn **ngoại lệ**. Nếu code cũ ép kiểu không kiểm tra:

```java
// Ví dụ legacy không an toàn, có thể ném ngoại lệ.
Shipment shipment = (Shipment) raw;
Customer customer = (Customer) shipment.customer();
Address address = (Address) customer.address();
String city = address.city();
```

thì sai kiểu có thể gây `ClassCastException`, còn dereference một record trung gian null có thể gây `NullPointerException`. Đổi sang `instanceof` và trả `"Invalid structure"` đã **thay đổi hợp đồng lỗi**. Đó có thể là cải tiến mong muốn, nhưng cần cập nhật caller/tests hoặc giữ cách báo lỗi cũ nếu caller phụ thuộc ngoại lệ.

Thứ tự kiểm tra cũng phải được giữ. Trong bài, cấu trúc được kiểm tra trước, tiếp đến thành phố, cuối cùng là số lượng. Nếu city trống và số lượng âm cùng lúc, baseline trả `Missing city`. Đổi thứ tự guard có thể làm kết quả thành `Invalid quantity`, tức đã thay đổi hành vi quan sát được.

## 6. Ví dụ hoàn chỉnh: so sánh bốn cách triển khai trên Java 21

Tạo tệp **`NestedCastRefactorDemo.java`**:

```java
public class NestedCastRefactorDemo {
    record Address(String city, String street) {}
    record Customer(String name, Object address) {}
    record Shipment(Object customer, int quantity) {}

    static String legacy(Object value) {
        if (!(value instanceof Shipment)) return "Invalid structure";
        Shipment shipment = (Shipment) value;
        if (!(shipment.customer() instanceof Customer)) return "Invalid structure";
        Customer customer = (Customer) shipment.customer();
        if (!(customer.address() instanceof Address)) return "Invalid structure";
        Address address = (Address) customer.address();
        String city = address.city();
        if (city == null || city.isBlank()) return "Missing city";
        if (shipment.quantity() <= 0) return "Invalid quantity";
        return "Ship " + shipment.quantity() + " for " + customer.name() + " to " + city;
    }

    static String withTypePatterns(Object value) {
        if (!(value instanceof Shipment shipment)) return "Invalid structure";
        if (!(shipment.customer() instanceof Customer customer)) return "Invalid structure";
        if (!(customer.address() instanceof Address address)) return "Invalid structure";
        String city = address.city();
        if (city == null || city.isBlank()) return "Missing city";
        if (shipment.quantity() <= 0) return "Invalid quantity";
        return "Ship " + shipment.quantity() + " for " + customer.name() + " to " + city;
    }

    static String withRecordPatterns(Object value) {
        if (!(value instanceof Shipment(
                Customer(var name, Address(var city, var street)), var quantity))) {
            return "Invalid structure";
        }
        if (city == null || city.isBlank()) return "Missing city";
        if (quantity <= 0) return "Invalid quantity";
        return "Ship " + quantity + " for " + name + " to " + city;
    }

    static String withSwitch(Object value) {
        return switch (value) {
            case null -> "Invalid structure";
            case Shipment(Customer(var name, Address(var city, var street)), var quantity)
                    when city != null && !city.isBlank() && quantity > 0
                    -> "Ship " + quantity + " for " + name + " to " + city;
            case Shipment(Customer(var name, Address(var city, var street)), var quantity)
                    when city == null || city.isBlank() -> "Missing city";
            case Shipment(Customer(var name, Address(var city, var street)), var quantity)
                    -> "Invalid quantity";
            default -> "Invalid structure";
        };
    }

    public static void main(String[] args) {
        Object ok = new Shipment(new Customer("Lan", new Address("Hue", "Le Loi")), 2);
        Object badCity = new Shipment(new Customer("Mai", new Address(" ", "Street")), 1);
        Object badQuantity = new Shipment(new Customer("Minh", new Address("Hanoi", "Pho")), 0);
        Object wrongType = new Shipment("legacy customer", 4);
        Object missingAddress = new Shipment(new Customer("An", null), 1);
        Object[] cases = {ok, badCity, badQuantity, wrongType, missingAddress, null};

        for (Object input : cases) {
            String baseline = legacy(input);
            String typed = withTypePatterns(input);
            String records = withRecordPatterns(input);
            String switched = withSwitch(input);
            System.out.println(baseline + " | equal=" +
                    (baseline.equals(typed) && baseline.equals(records)
                            && baseline.equals(switched)));
        }
    }
}
```

Biên dịch/chạy với JDK 21 trở lên, không cần preview:

```bash
javac --release 21 NestedCastRefactorDemo.java
java NestedCastRefactorDemo
```

**Kết quả:**

```text
Ship 2 for Lan to Hue | equal=true
Missing city | equal=true
Invalid quantity | equal=true
Invalid structure | equal=true
Invalid structure | equal=true
Invalid structure | equal=true
```

Đây là sáu ca: dữ liệu hợp lệ, thành phố chỉ có khoảng trắng, số lượng bằng 0, sai kiểu khách hàng, thiếu địa chỉ và đầu vào null. Ở mỗi dòng, `equal=true` nghĩa là phương thức dùng type patterns, nested record patterns và switch đều trả đúng chuỗi bằng baseline.

Điểm quan trọng trong `withSwitch`: nhánh `Shipment(...) when ...` chấp nhận dữ liệu đầy đủ; nhánh `when city == null || city.isBlank()` bắt thành phố không hợp lệ; nhánh `Shipment(...)` không guard xử lý lượng không hợp lệ. Guard hẹp phải đặt trước nhánh bao quát để không bị **dominated case label**. `case null` xử lý null selector, còn `default` xử lý cấu trúc sai hoặc kiểu khác.

Bốn phiên bản cho kết quả giống nhau trên **sáu ca đã thử**, không có nghĩa chúng đương nhiên giống nhau trên mọi dữ liệu. Với sản phẩm thực tế, bổ sung dữ liệu sai kiểu ở địa chỉ, customer null, city null, lượng âm, nhiều lỗi cùng lúc, và kiểm tra ngoại lệ/tác dụng phụ.

## 7. Quy trình refactor từng bước trong dự án

1. **Chụp hành vi hiện tại:** xác định đầu vào hợp lệ, kiểu lỗi, ngoại lệ và thứ tự xử lý. Tạo test cho các ca chính trước khi đổi cấu trúc.
2. **Thay cast thừa:** biến `if (obj instanceof Type) { Type t = (Type) obj; ... }` thành `if (obj instanceof Type t) { ... }`, giữ các nhánh lỗi cũ.
3. **Giảm nesting bằng guard clauses:** `if (!(obj instanceof Type t)) return failure;`, với điều kiện nhánh thất bại phải thoát và biến được dùng trên đường chắc chắn khớp.
4. **Nhận diện record và mức cần phân rã:** nếu tầng trong là record và chỉ cần một vài component, thử nested record pattern. Nếu cần biết chính xác tầng nào sai, giữ các guard từng cấp.
5. **Chọn `switch` khi có nhiều loại dữ liệu:** với nhiều kiểu subtype hoặc nhiều trường hợp record, một `switch expression` hoặc statement có các `case` riêng có thể rõ hơn loạt `if`.
6. **Đối chiếu ngữ nghĩa:** so sánh result, exception, kiểm tra null, thứ tự lỗi, các lần gọi accessor, và các side effect có thể có.
7. **Hoàn tất khi đã xác minh:** chạy test phù hợp, xóa cast hoặc nhánh cũ không còn cần thiết; tránh để song song hai cách xử lý trong mã sản phẩm.

Không cần chuyển toàn bộ cây cast cùng lúc. Có thể chỉ đổi cast tầng ngoài, chạy test rồi đổi tầng tiếp. Điều này đặc biệt hữu ích trong repository lớn hoặc code đang được nhiều nơi gọi.

## 8. Khi nào giữ type pattern thay vì nested record pattern?

Nested record pattern chỉ deconstruct được **record**. Với class thông thường, không thể viết `LegacyCustomer(Address(...))` như thể class đó là record.

Ví dụ minh họa trong codebase đã định nghĩa một class `LegacyCustomer` có getter `getAddress()`:

```java
if (!(raw instanceof LegacyCustomer customer)) {
    return "Invalid customer";
}
if (!(customer.getAddress() instanceof Address address)) {
    return "Invalid address";
}
String city = address.city();
```

Đoạn này chỉ minh họa việc dùng type patterns cùng getter cho class thường; nó không độc lập vì phụ thuộc khai báo `LegacyCustomer` của ứng dụng. Ngay cả khi một tầng là class thường và tầng kế tiếp là record, vẫn có thể kết hợp type pattern ở tầng class với record pattern ở component record.

Đôi khi bạn đã có một biến kiểu `Shipment` và chỉ cần `shipment.quantity()`. Khi đó accessor trực tiếp thường đơn giản hơn tạo một record pattern để lấy đúng một field. Pattern matching có ích nhất ở **ranh giới kiểu chưa rõ**, khi ta cần kiểm tra runtime và lấy dữ liệu ngay sau đó.

**Giới hạn generic:** phép kiểm tra `raw instanceof java.util.List<String>` không hợp lệ khi `raw` là `Object` vì type argument `String` không được xác thực qua runtime erasure. Thay bằng `List<?>` rồi kiểm tra từng phần tử:

```java
if (raw instanceof java.util.List<?> values) {
    for (Object item : values) {
        if (item instanceof String name) {
            System.out.println(name);
        }
    }
}
```

Pattern matching không làm mất đi các quy tắc an toàn kiểu của generic. Nếu mã cũ chứa unchecked casts, cần xác định hợp đồng dữ liệu trước khi thay.

## 9. Thận trọng với thứ tự đánh giá và side effects

Một record có thể tự định nghĩa accessor, còn class thường có thể triển khai getter với logic, ngoại lệ hoặc tác dụng phụ. Khi đổi nhiều lệnh đọc accessor thành nested record pattern, số lần đọc và thứ tự đánh giá có thể khác. Với các DTO/record bất biến và accessor đơn giản, sự khác biệt thường không quan trọng; với code có cache, logging, mutable state hoặc custom accessor, cần kiểm thử.

Đừng tự gom mọi điều kiện vào một pattern nếu hệ thống cần thông báo khác nhau: `Missing customer`, `Missing address`, `Missing city`. Trong trường hợp ấy, một chuỗi type patterns và guard clauses có thể dài hơn nhưng rõ chính xác lỗi ở tầng nào.

Nếu record có nhiều component nhưng chỉ cần một vài giá trị, vẫn phải ghi đủ số vị trí trong pattern. Java 21 cho phép đặt tên như `var ignoredStreet` cho component không dùng. Chỉ từ Java 22 mới có unnamed pattern `_`; không sử dụng cú pháp này khi biên dịch với `javac --release 21`.

## 10. Bảng lỗi thường gặp

| Vấn đề | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Dùng `shipment` sau `if (!(raw instanceof Shipment shipment))` nhưng nhánh lỗi không thoát | Pattern variable chưa chắc được ràng buộc. | `return` hoặc `throw` khi sai; hoặc dùng biến trong nhánh đúng. |
| Bỏ kiểm tra kiểu ở tầng giữa | Cast trực tiếp có thể ném `ClassCastException`. | Giữ type pattern hoặc nested record pattern đúng tầng. |
| Chỉ kiểm tra record ngoài và gọi getter trên record con null | Dereference null có thể ném `NullPointerException`. | Kiểm tra record con hoặc deconstruct bằng nested pattern. |
| Cho rằng `var city` luôn khác null | Record `Address` có thể hợp lệ nhưng component `city` null. | Giữ `city == null || city.isBlank()`. |
| Dùng `Shipment(Customer(Address(var city)))` | Thiếu vị trí component so với khai báo. | Viết đủ pattern con và đúng thứ tự. |
| Dùng record pattern trên class thường | Java 21 không hỗ trợ deconstruction tự do cho class. | Dùng type pattern và accessor. |
| Đặt nhánh tổng quát của `switch` trước nhánh `when` | Nhánh hẹp bị che khuất. | Đặt nhánh guard cụ thể trước. |
| Bỏ `case null` khi cần xử lý null selector | `default` không tự xử lý null theo cách mong muốn. | Viết `case null` hoặc kiểm tra null trước switch. |
| Thay exception cũ bằng giá trị mặc định mà không đánh giá API | Thay đổi hợp đồng lỗi của caller. | Ghi rõ hành vi mong muốn, cập nhật tests/caller khi cần. |
| Bỏ qua thứ tự kiểm tra điều kiện | Có thể trả thông báo lỗi khác khi nhiều điều kiện cùng sai. | Giữ thứ tự guard hoặc thay đổi có chủ đích. |
| Giả định generic type arguments kiểm tra được tại runtime | Type erasure không bảo đảm `List<String>`. | Dùng `List<?>` và kiểm tra phần tử. |
| Chỉ test happy path | Null, sai kiểu, lượng âm, city trống không được kiểm tra. | So sánh cả dữ liệu hợp lệ lẫn trường hợp lỗi. |

## 11. Bài tập áp dụng

Cho các record:

```java
record Position(int row, int column) {}
record Location(Object position) {}
record Device(Object location) {}
```

Yêu cầu từ `Object raw`:

- Nếu không khớp chuỗi `Device → Location → Position`, trả `"invalid structure"`.
- Nếu khớp nhưng `row < 0`, trả `"invalid row"`.
- Nếu khớp và row không âm, trả `"row="` cộng giá trị row.

**Phiên bản dùng cast có kiểm tra:**

```java
static String oldDescribe(Object raw) {
    if (!(raw instanceof Device)) return "invalid structure";
    Device device = (Device) raw;
    if (!(device.location() instanceof Location)) return "invalid structure";
    Location location = (Location) device.location();
    if (!(location.position() instanceof Position)) return "invalid structure";
    Position position = (Position) location.position();
    if (position.row() < 0) return "invalid row";
    return "row=" + position.row();
}
```

**Phiên bản record pattern (Java 21):**

```java
static String describe(Object raw) {
    if (!(raw instanceof Device(Location(Position(var row, var column))))) {
        return "invalid structure";
    }
    if (row < 0) return "invalid row";
    return "row=" + row;
}
```

Khi viết `Device(Location(Position(var row, var column)))`, pattern khớp từ record ngoài tới component sâu nhất. `column` được ràng buộc nhưng không sử dụng, vì Java 21 yêu cầu đủ vị trí component. Phiên bản này giữ đúng thông báo lỗi của baseline có kiểm tra trong những ca đầu vào sau:

- `new Device(new Location(new Position(3, 7)))` → `row=3`.
- `new Device(new Location(new Position(-1, 7)))` → `invalid row`.
- `new Device(new Location(null))` → `invalid structure`.
- `new Device("not a location")` → `invalid structure`.
- `null` → `invalid structure`.

Các phương thức trong bài tập là snippet để đặt vào một lớp cùng ba record vừa khai báo. Chương trình chạy độc lập với `main`, lệnh `javac` và stdout đã được trình bày đầy đủ trong mục 6.

**Bài tập nâng cao:** Nếu cần phân biệt lỗi thiếu `Location` với lỗi thiếu `Position`, hãy viết ba guard clauses dùng type pattern theo từng tầng và giữ riêng hai thông báo lỗi.

## 12. Nguyên tắc ghi nhớ

- Với legacy cast, bắt đầu bằng thay `instanceof Type` + `(Type)` thành **type pattern** và biến có kiểu an toàn.
- Khi dữ liệu nhiều tầng đều là record, có thể dùng **nested record pattern** để kiểm tra và lấy component trong một bước; cần đủ vị trí và đúng thứ tự component.
- **Guard clause** giúp xử lý đường thất bại trước rồi giữ logic thành công ở mức thụt đầu dòng nông; lưu ý phạm vi biến pattern.
- **Null record con** khiến pattern phân rã tầng đó không khớp, nhưng component `var` bên trong một record đã khớp vẫn có thể null.
- Luôn xác nhận **hành vi lỗi, ngoại lệ, thứ tự kiểm tra và side effects**, không chỉ giảm số dòng code.
- Dùng `switch` khi có nhiều kiểu/nhánh có ý nghĩa; dùng chuỗi guard tuyến tính khi chỉ có một cấu trúc cần kiểm tra.

**Tài liệu tham khảo:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 456 — Unnamed Variables & Patterns](https://openjdk.org/jeps/456), [Java 21 JLS — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
