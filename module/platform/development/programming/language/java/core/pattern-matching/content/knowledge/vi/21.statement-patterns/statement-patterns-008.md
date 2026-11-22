# Giảm nesting bằng guard clause khi dùng pattern trong statement (Java 21)

## 1. Bài toán cần giải quyết

Trong Java, một phương thức xử lý dữ liệu thường phải qua nhiều điều kiện: đầu vào có đúng kiểu không, record con có tồn tại không, component quan trọng có hợp lệ không, và cuối cùng mới đến nghiệp vụ chính. Nếu đặt mọi điều kiện thành nhiều lớp `if` lồng nhau, phần xử lý thực sự bị đẩy sâu sang phải và các nhánh lỗi xen vào luồng thành công.

**Guard clause** là một điều kiện kiểm tra ở đầu hoặc gần đầu một khối xử lý; khi điều kiện **không đáp ứng yêu cầu**, ta kết thúc sớm đường đi hiện tại bằng `return`, `throw` hoặc `continue` trong vòng lặp. Các điều kiện thất bại được giải quyết lần lượt, để phần xử lý hợp lệ nằm ở mức thụt đầu dòng nông hơn.

Với **pattern matching** của Java, guard clause đặc biệt hữu ích vì `instanceof` và `record pattern` vừa kiểm tra kiểu/cấu trúc vừa khai báo biến chỉ có thể dùng khi pattern đã khớp. Khi điều kiện phủ định một pattern và nhánh lỗi kết thúc bằng `return`, Java biết rằng luồng đi tiếp **đã khớp pattern**, nên những biến được khai báo trong pattern có thể được dùng ở phía sau.

Bài này áp dụng với:
- Type pattern `obj instanceof String text` (chuẩn từ Java 16).
- Record patterns `obj instanceof Order(var customer, var quantity)` và nested record patterns (chuẩn từ Java 21, JEP 440).
- Pattern matching trong `switch` statement và `when` (chuẩn từ Java 21, JEP 441).
- Guard clauses bằng `return`, `throw` và `continue`, cùng cách bảo toàn phạm vi biến pattern (*flow scoping*).

Mọi chương trình hoàn chỉnh trong bài sử dụng **JDK 21 trở lên**, không cần `--enable-preview`.

## 2. Trước và sau: giảm số tầng `if`

Định nghĩa dữ liệu:

```java
record Address(String city) {}
record Customer(String name, Address address) {}
record Order(Customer customer, int quantity) {}
```

Một cách xử lý theo hướng lồng nhiều cấp (đặt trong phương thức nhận `Object value` và trả về `String`):

```java
if (value instanceof Order(Customer(var name, Address(var city)), var quantity)) {
    if (city != null && !city.isBlank()) {
        if (quantity > 0) {
            return "Ship " + quantity + " for " + name + " to " + city;
        }
        return "Invalid quantity";
    }
    return "Missing city";
}
return "Invalid order structure";
```

Đoạn mã đúng nhưng phần nghiệp vụ nằm trong ba tầng `if`. Khi yêu cầu bổ sung như giới hạn số lượng, kiểm tra quyền hoặc số lượng hàng còn lại xuất hiện, mức lồng nhau tiếp tục tăng.

Viết bằng guard clauses:

```java
if (!(value instanceof Order(Customer(var name, Address(var city)), var quantity))) {
    return "Invalid order structure";
}
if (city == null || city.isBlank()) {
    return "Missing city";
}
if (quantity <= 0) {
    return "Invalid quantity";
}
return "Ship " + quantity + " for " + name + " to " + city;
```

Hai phiên bản giữ **cùng thứ tự ưu tiên kết quả**:

1. Đầu vào phải khớp cấu trúc `Order → Customer → Address`; không khớp thì trả `Invalid order structure`.
2. Đã khớp cấu trúc nhưng `city` thiếu hoặc chỉ chứa khoảng trắng thì trả `Missing city`.
3. Thành phố hợp lệ nhưng số lượng không dương thì trả `Invalid quantity`.
4. Tất cả điều kiện thỏa mãn mới thực hiện nghiệp vụ tạo thông báo giao hàng.

Lợi ích chính là **đường đi thành công nằm thẳng trong thân phương thức**. Cách viết này dễ bổ sung điều kiện kiểm tra mà không buộc phần chính lùi sâu thêm một cấp.

## 3. Vì sao biến pattern dùng được sau `if (!(...))`?

Đây là điểm then chốt về **flow scoping**, không chỉ là mẹo định dạng code.

Xem phiên bản type pattern đơn giản:

```java
static int lengthOf(Object raw) {
    if (!(raw instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

`raw instanceof String text` thử khớp kiểu và gán biến pattern `text` nếu thành công. Dấu `!` đảo điều kiện. Nếu điều kiện của `if` là true, phương thức trả `-1` ngay. Vì vậy **mọi đường chạy có thể đi đến câu lệnh `text.length()`** đều là đường đã khớp `String text`.

Trình biên dịch áp dụng quy tắc *definitely matched* (pattern đã chắc chắn khớp theo luồng điều khiển), cho phép sử dụng `text` ở câu lệnh tiếp theo. Với **record pattern** lồng nhau, nguyên tắc tương tự áp dụng cho các biến component:

```java
static String cityOf(Object input) {
    if (!(input instanceof Order(
            Customer(var name, Address(var city)), var quantity))) {
        return "No complete address";
    }
    return name + " / " + city + " / " + quantity;
}
```

Ở cuối `if`, Java biết `Order(...)`, `Customer(...)` và `Address(...)` đã khớp. Do đó `name` có kiểu `String`, `city` có kiểu `String` và `quantity` có kiểu `int`; có thể dùng ở phần `return`.

Cần phân biệt với điều kiện dương nhưng không kết thúc mọi đường đi:

```java
// KHÔNG BIÊN DỊCH: text không chắc đã được gán sau if.
static int invalid(Object raw) {
    if (raw instanceof String text) {
        System.out.println(text);
    }
    return text.length();
}
```

Ở ví dụ sai, sau khi kết thúc `if`, đầu vào có thể không phải `String` nên `text` không nằm trong phạm vi được bảo đảm. Có thể khắc phục bằng `return` ngay trong nhánh khớp hoặc dùng guard clause phủ định như `lengthOf`.

**Điều kiện quan trọng:** Nhánh guard thất bại phải **không thể hoàn tất bình thường để rơi xuống các câu lệnh bên dưới**, ví dụ `return` hoặc `throw`. Nếu chỉ ghi log bên trong `if (!(...))` rồi tiếp tục, Java không thể coi các biến pattern là chắc chắn có giá trị.

## 4. Pattern thất bại và kiểm tra dữ liệu là hai loại guard khác nhau

Record pattern lồng nhau kiểm tra cấu trúc, còn guard clauses tiếp theo kiểm tra **quy tắc dữ liệu/nghiệp vụ**.

Với `Order(Customer(var name, Address(var city)), var quantity)`:

- Nếu giá trị ngoài không phải `Order`, pattern không khớp.
- Nếu component `customer` là `null`, `Customer(...)` không khớp.
- Nếu component `address` là `null`, `Address(...)` không khớp.
- Nếu `Address` tồn tại nhưng component `city` là `null`, `var city` vẫn có thể nhận `null`; bản thân record pattern không tự đảm bảo chuỗi khác `null`.
- Nếu `quantity` bằng `0` hoặc âm, pattern vẫn khớp vì component có kiểu `int`; đó là lỗi nghiệp vụ cần kiểm tra riêng.

Bởi vậy, guard clauses nên đi từ **hình dạng/kiểu dữ liệu**, qua **tính hợp lệ của component**, đến **nghiệp vụ**. Ví dụ:

```java
if (!(value instanceof Order(Customer(var name, Address(var city)), var quantity))) {
    return "Invalid order structure";
}
if (city == null || city.isBlank()) {
    return "Missing city";
}
if (quantity <= 0) {
    return "Invalid quantity";
}
return "Ship " + quantity + " for " + name + " to " + city;
```

Điều kiện `city == null || city.isBlank()` có short-circuit: khi `city == null`, toán hạng thứ hai không chạy nên tránh gọi `isBlank()` trên `null`. Trong thực tế, ta có thể thêm `name == null || name.isBlank()` nếu hợp đồng nghiệp vụ yêu cầu tên khách hàng hợp lệ. Không nên coi việc khớp `var name` là đủ để bảo đảm tên khác `null`.

Một guard chứa nested pattern có thể gom nhiều kiểm tra cấu trúc vào một lần. Nhưng nếu ứng dụng cần **phân biệt lỗi thiếu khách hàng và lỗi thiếu địa chỉ**, hãy tách thành nhiều bước, thay vì để mọi lỗi cấu trúc cùng trả một thông báo:

```java
// Ví dụ minh họa trong phương thức nhận Object value.
if (!(value instanceof Order(var customer, var quantity))) {
    return "Not an order";
}
if (customer == null) {
    return "Missing customer";
}
if (!(customer.address() instanceof Address(var city))) {
    return "Missing address";
}
if (city == null || city.isBlank()) {
    return "Missing city";
}
return "Ready";
```

Ở đây `customer` được suy luận kiểu `Customer`, nên có thể gọi `customer.address()` sau guard đầu tiên và kiểm tra `null` riêng. Tách bước có thể dài hơn một pattern lồng, nhưng cho lỗi cụ thể hơn.

## 5. Dùng `throw` khi điều kiện sai là lỗi hợp đồng API

Không phải mọi guard clause đều trả một giá trị mặc định. Trong phương thức xây dựng đối tượng hoặc xử lý API có hợp đồng chặt, đầu vào sai có thể cần ném ngoại lệ:

```java
record PositiveCount(int value) {}

static int readCount(Object raw) {
    if (!(raw instanceof PositiveCount(var count))) {
        throw new IllegalArgumentException("Expected PositiveCount");
    }
    if (count <= 0) {
        throw new IllegalArgumentException("Count must be positive");
    }
    return count;
}
```

Cả `return` và `throw` đều kết thúc đường chạy lỗi, nên `count` có thể dùng sau guard phủ định. Chọn `return` cho những kết quả không hợp lệ nhưng **được thiết kế là một phần của luồng bình thường**, và `throw` cho vi phạm hợp đồng mà caller phải xử lý.

Không tự động ném ngoại lệ trong các vòng lặp lọc dữ liệu: nếu mục tiêu là bỏ qua bản ghi không phù hợp và tiếp tục, `continue` thường thể hiện đúng ý định hơn.

## 6. Guard clause trong vòng lặp: `continue` để bỏ qua dữ liệu không khớp

Khi tìm bản ghi đầu tiên thỏa điều kiện trong mảng hoặc collection, có thể dùng `continue` sau guard thay cho nhiều lớp `if`:

```java
static String firstShippable(Object[] values) {
    for (Object value : values) {
        if (!(value instanceof Order(Customer(var name, Address(var city)), var quantity))) {
            continue;
        }
        if (city == null || city.isBlank() || quantity <= 0) {
            continue;
        }
        return "Found " + name + ":" + quantity + "@" + city;
    }
    return "No shippable order";
}
```

Cơ chế:

- Đầu vào hiện tại không khớp nested record pattern: `continue` chuyển sang phần tử tiếp theo.
- Giá trị khớp nhưng thành phố trống hoặc số lượng không hợp lệ: bỏ qua.
- Dòng `return "Found ..."` chỉ được chạy khi toàn bộ guard đã được vượt qua. Java biết các biến pattern đã được gán ở đường chạy đó.
- Nếu duyệt hết mà chưa có phần tử phù hợp, phương thức trả `No shippable order`.

Khác với guard dùng `return`, ở đây **một phần tử không hợp lệ không làm dừng toàn bộ việc tìm kiếm**. Điều này đặc biệt hữu ích khi xử lý sự kiện hoặc collection chứa nhiều kiểu đối tượng.

Hãy cân nhắc đặt logic kiểm tra phức tạp vào một phương thức riêng nếu một vòng lặp có quá nhiều guard, tránh làm phương thức duyệt phải hiểu toàn bộ cấu trúc nghiệp vụ.

## 7. Guard clause với `switch` statement và `when`

Trong Java 21, `switch` statement có thể chứa các nhánh pattern matching. Điều kiện `when` được đánh giá **sau khi pattern khớp**, đóng vai trò lọc thêm một nhánh `case`. Dù tên gọi giống nhau, **`when` guard không đồng nghĩa với guard clause**:

- `when` là **guard của nhánh switch**: quyết định nhánh đó có được chọn hay không; nếu false, tiếp tục xét nhánh phù hợp khác.
- **Guard clause** là kiểu tổ chức luồng điều khiển: kiểm tra một điều kiện bất hợp lệ rồi thoát sớm khỏi phần đang xử lý bằng `return`/`throw`/`continue`.

Một `switch` statement dùng nhánh `case` trả sớm:

```java
// Ví dụ đặt trong phương thức trả về String, với Order/Customer/Address đã khai báo.
switch (value) {
    case null -> {
        return "No input";
    }
    case Order(Customer(var name, Address(var city)), var quantity)
            when city != null && !city.isBlank() && quantity > 0 -> {
        return "Accepted " + name + "@" + city;
    }
    case Order(var customer, var quantity) -> {
        return "Invalid order";
    }
    default -> {
        return "Not an order";
    }
}
```

Ở đây mỗi nhánh là một **statement block** chứa `return` của phương thức; không dùng `yield`. Nếu đổi sang `return switch (value) { ... };` thì `switch` trở thành **expression**, và các block nhiều câu lệnh sẽ dùng `yield` để tạo giá trị, không dùng `return` để “trả giá trị về switch”.

Thứ tự nhánh cần chính xác: nhánh `Order(...) when ...` có điều kiện cụ thể nên đặt trước nhánh `Order(...)` tổng quát. Nếu đảo thứ tự, nhánh cụ thể có thể bị bao phủ (dominated) và gây lỗi biên dịch. `case null` xử lý selector bằng `null`; `default` không tự động thay thế cho việc xử lý null. Các nhánh mũi tên `->` không fall-through.

Khi nhiều điều kiện tuần tự cùng áp dụng cho **một** kiểu record, guard clauses `if` liên tiếp thường rõ hơn switch. Khi cần xử lý **nhiều kiểu dữ liệu khác nhau**, `switch` với các type/record patterns có thể dễ đọc hơn.

## 8. Ví dụ Java 21 đầy đủ: so sánh nesting và guard clauses

Tạo tệp **`GuardClausePatternDemo.java`**:

```java
public class GuardClausePatternDemo {
    record Address(String city) {}
    record Customer(String name, Address address) {}
    record Order(Customer customer, int quantity) {}
    record Failure(String reason) {}

    static String nested(Object value) {
        if (value instanceof Order(Customer(var name, Address(var city)), var quantity)) {
            if (city != null && !city.isBlank()) {
                if (quantity > 0) {
                    return "Ship " + quantity + " for " + name + " to " + city;
                }
                return "Invalid quantity";
            }
            return "Missing city";
        }
        return "Invalid order structure";
    }

    static String guarded(Object value) {
        if (!(value instanceof Order(Customer(var name, Address(var city)), var quantity))) {
            return "Invalid order structure";
        }
        if (city == null || city.isBlank()) return "Missing city";
        if (quantity <= 0) return "Invalid quantity";
        return "Ship " + quantity + " for " + name + " to " + city;
    }

    static String firstShippable(Object[] values) {
        for (Object value : values) {
            if (!(value instanceof Order(Customer(var name, Address(var city)), var quantity))) {
                continue;
            }
            if (city == null || city.isBlank() || quantity <= 0) continue;
            return "Found " + name + ":" + quantity + "@" + city;
        }
        return "No shippable order";
    }

    static String message(Object value) {
        if (value == null) return "No input";
        if (value instanceof Failure(var reason)) return "Failure: " + reason;
        if (!(value instanceof Order(var customer, var quantity))) return "Unsupported";
        if (customer == null) return "Missing customer";
        return "Order quantity " + quantity;
    }

    static String switchStatement(Object value) {
        switch (value) {
            case null -> { return "No input"; }
            case Order(Customer(var name, Address(var city)), var quantity)
                    when city != null && !city.isBlank() && quantity > 0 -> {
                return "Accepted " + name + "@" + city;
            }
            case Order(var customer, var quantity) -> { return "Invalid order"; }
            default -> { return "Not an order"; }
        }
    }

    public static void main(String[] args) {
        Object ok = new Order(new Customer("Lan", new Address("Da Nang")), 2);
        Object badCity = new Order(new Customer("Lan", new Address(" ")), 2);
        Object badQty = new Order(new Customer("Minh", new Address("Hue")), 0);
        Object absent = new Order(new Customer("An", null), 3);

        System.out.println(nested(ok));
        System.out.println(guarded(ok));
        System.out.println(guarded(badCity));
        System.out.println(guarded(badQty));
        System.out.println(guarded(absent));
        System.out.println(guarded(null));
        System.out.println(firstShippable(new Object[]{null, badQty, ok}));
        System.out.println(firstShippable(new Object[]{badCity, absent}));
        System.out.println(message(new Failure("timeout")));
        System.out.println(message(new Order(null, 4)));
        System.out.println(switchStatement(ok));
        System.out.println(switchStatement(badCity));
        System.out.println(switchStatement(null));
    }
}
```

Biên dịch và chạy bằng JDK 21+:

```bash
javac --release 21 GuardClausePatternDemo.java
java GuardClausePatternDemo
```

**Kết quả:**

```text
Ship 2 for Lan to Da Nang
Ship 2 for Lan to Da Nang
Missing city
Invalid quantity
Invalid order structure
Invalid order structure
Found Lan:2@Da Nang
No shippable order
Failure: timeout
Missing customer
Accepted Lan@Da Nang
Invalid order
No input
```

Những kết quả quan trọng:

1. `nested(ok)` và `guarded(ok)` có cùng kết quả, chứng minh việc tái tổ chức luồng giữ nguyên kết quả ở đường thành công.
2. `badCity` khớp record nhưng `city.isBlank()` là true; guard trả `Missing city`.
3. `badQty` có `quantity == 0`; guard thứ ba trả `Invalid quantity`.
4. `absent` có `Customer.address() == null`; nested `Address(...)` không khớp, vì vậy trả `Invalid order structure`.
5. `guarded(null)` trả `Invalid order structure` mà không ném lỗi, do `null instanceof Order(...)` là false.
6. `firstShippable` bỏ qua phần tử null và đơn hàng số lượng không hợp lệ để tìm phần tử hợp lệ `ok`.
7. `message(new Failure("timeout"))` xử lý `Failure` trước, rồi thoát sớm; `message(new Order(null, 4))` lấy cấu trúc `Order` nhưng phát hiện khách hàng null ở guard tiếp theo.
8. `switchStatement(ok)` dùng `case Order(...) when ...` tạo kết quả chấp nhận, còn `switchStatement(badCity)` đi vào nhánh `Order(...)` tổng quát. `switchStatement(null)` vào `case null`.

Ví dụ minh họa cả ba cách kết thúc nhánh sớm: `return` trong phương thức, `continue` trong vòng lặp, và `return` trong nhánh của `switch statement`. Trong code sản phẩm, không cần giữ cả `nested` và `guarded`; chúng chỉ được đặt cạnh nhau để so sánh.

## 9. Những lỗi thường gặp

| Lỗi / ngộ nhận | Vì sao có vấn đề | Cách sửa |
| --- | --- | --- |
| Viết `if (!(raw instanceof String text)) { log(); }` rồi dùng `text` | Nhánh lỗi có thể chạy xong và rơi xuống; compiler không bảo đảm pattern đã khớp. | Thêm `return`/`throw` trong guard, hoặc dùng nhánh khớp trực tiếp. |
| Quên `!` trong guard | `if (raw instanceof Type t) return...` có thể thoát ngay khi dữ liệu đúng kiểu, làm đảo mục đích. | Diễn đạt điều kiện theo trạng thái **không hợp lệ** và kiểm tra kết quả từng nhánh. |
| Dùng `&&` thay `||` trong kiểm tra `city == null || city.isBlank()` | Khi viết `city == null && city.isBlank()`, nhánh thứ hai có thể dereference null. | Dùng `||` để short-circuit theo đúng logic. |
| Tưởng nested record pattern đồng nghĩa mọi component không null | `var city` có thể nhận null dù `Address(...)` khớp. | Kiểm tra `city == null` trước khi gọi phương thức. |
| Pattern quá sâu làm mất khả năng phân biệt lỗi | Một guard lớn không cho biết cụ thể cấp nào bị thiếu. | Tách các guard theo từng cấp nếu cần lỗi chính xác. |
| Dùng `continue` ngoài vòng lặp | `continue` chỉ có ý nghĩa trong vòng lặp. | Dùng `return` để thoát phương thức hoặc tái cấu trúc vòng lặp. |
| Gọi `return` trong mọi guard mà chưa xét quy trình | Trong xử lý danh sách, một bản ghi lỗi có thể làm bỏ qua toàn bộ phần còn lại. | Dùng `continue` khi cần bỏ qua phần tử và tiếp tục tìm. |
| Nhầm `when` với guard clause | `when` chỉ lọc một nhánh `case`; nó không tự kết thúc phương thức. | Dùng `return`/`throw`/`continue` để diễn đạt thoát sớm. |
| Đặt nhánh `case Order(...)` rộng trước nhánh có `when` | Nhánh hẹp có thể bị che khuất và không biên dịch. | Đặt nhánh hẹp trước, nhánh rộng sau. |
| Dùng mã `record pattern` trên JDK 17 như tính năng chuẩn | Record patterns hoàn thiện trong Java 21. | Dùng JDK 21+ cho các ví dụ. |
| Thêm guard quá nhiều, lặp lại kiểm tra hoặc đổi thứ tự lỗi | Đường đi có thể khó đọc và kết quả khi nhiều điều kiện đồng thời sai có thể thay đổi. | Nhóm theo loại kiểm tra, chọn thứ tự lỗi có chủ đích, tách phương thức khi cần. |

Đừng cố gắng dùng guard clause cho mọi `if`. Với một điều kiện nhỏ mà cả nhánh đúng và sai đều có ý nghĩa tương đương, `if/else` có thể rõ ràng hơn. Mục tiêu là để luồng bình thường dễ nhận ra và dễ kiểm tra, không phải làm giảm số dấu ngoặc bằng mọi giá.

## 10. Bài tập thực hành

Cho hai record:

```java
record Profile(String username, String email) {}
record Registration(Profile profile, int age) {}
```

**Yêu cầu:** Viết phương thức `static String validate(Object input)` theo thứ tự:
1. Chỉ chấp nhận `Registration` có `Profile` khác null, nếu không trả `Invalid structure`.
2. Nếu `username` null hoặc trống sau khi loại khoảng trắng, trả `Missing username`.
3. Nếu `age < 18`, trả `Underage`.
4. Nếu `email` null hoặc không chứa ký tự `@`, trả `Invalid email`.
5. Nếu hợp lệ, trả `Registered: <username>`.

**Lời giải với guard clauses (Java 21):**

```java
static String validate(Object input) {
    if (!(input instanceof Registration(
            Profile(var username, var email), var age))) {
        return "Invalid structure";
    }
    if (username == null || username.isBlank()) {
        return "Missing username";
    }
    if (age < 18) {
        return "Underage";
    }
    if (email == null || !email.contains("@")) {
        return "Invalid email";
    }
    return "Registered: " + username;
}
```

Tất cả các biến `username`, `email`, `age` có hiệu lực sau guard đầu vì đầu vào không khớp đã thoát khỏi phương thức. Các điều kiện sau đó kiểm tra từng ràng buộc và kết thúc sớm khi sai. Mọi nhánh thành công đều đi đến dòng `return "Registered: " + username;` ở cuối.

Hãy tự thử:

- `validate(new Registration(new Profile("Mai", "mai@example.com"), 20))` → `Registered: Mai`.
- `validate(new Registration(null, 20))` → `Invalid structure`.
- `validate(new Registration(new Profile(" ", "mai@example.com"), 20))` → `Missing username`.
- `validate(new Registration(new Profile("Mai", "mai@example.com"), 16))` → `Underage`.
- `validate(new Registration(new Profile("Mai", "invalid"), 20))` → `Invalid email`.

Đoạn lời giải là phương thức minh họa sử dụng hai record được khai báo ngay bên trên; tệp hoàn chỉnh runnable có `main` nằm ở mục 8.

Một phần mở rộng: nếu muốn thông báo riêng khi `Registration.profile == null`, hãy bắt `Registration(var profile, var age)` trước, rồi kiểm tra `profile == null` bằng một guard khác. Chỉ nên phân rã `Profile(...)` sau khi xác nhận nó tồn tại.

## 11. Checklist refactor an toàn

Khi chuyển code lồng nhiều tầng sang guard clauses:

1. Liệt kê **điều kiện tiên quyết** và thứ tự ưu tiên lỗi trước khi đổi cấu trúc. Dùng cùng kết quả/ngoại lệ cho từng loại đầu vào.
2. Đặt điều kiện sai vào các `if` ngắn và thoát sớm. Với pattern, thường là `if (!(obj instanceof Type(var x))) return ...;`.
3. Xác nhận biến pattern còn trong phạm vi sau guard dựa trên đường đi đã khớp, nhất là khi thêm toán tử `!`, `&&`, `||`.
4. Phân biệt null của record con (khi deconstruct thì pattern không khớp) và null của component được lấy bằng `var` (có thể cần kiểm tra riêng).
5. Chọn đúng cơ chế thoát: `return` cho phương thức, `throw` cho vi phạm hợp đồng, `continue` cho phần tử không phù hợp trong vòng lặp.
6. Với nhiều kiểu khác nhau, cân nhắc `switch statement` cùng pattern cases; phân biệt `when` với guard clause.
7. Kiểm thử các đường đi thành công, null, sai kiểu, thiếu record con, dữ liệu biên (0/âm/chuỗi trắng) và nhiều điều kiện sai đồng thời.

**Ghi nhớ:** kết hợp **pattern matching** với **guard clause** giúp chuyển các kiểm tra kiểu/cấu trúc lên đầu, rồi viết nghiệp vụ chính trên một đường đi rõ ràng. Trong Java 21, sau `if (!(obj instanceof Pattern(...))) return ...;`, compiler cho phép dùng các biến pattern ở phía sau vì chúng đã chắc chắn được khớp trên mọi đường chạy tiếp tục.

**Tài liệu tham khảo:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [Oracle Java 21 — Pattern Matching with instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html), [Java Language Specification — Scope for Pattern Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.2).
