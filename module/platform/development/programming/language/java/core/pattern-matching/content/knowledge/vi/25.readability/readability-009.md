# Giữ code tương thích với người đọc Java cũ khi dùng Pattern Matching

Khi một nhóm phát triển chuyển từ phong cách Java 8/11 sang **pattern matching** của Java 16–21, mã nguồn có thể ngắn hơn nhưng chưa chắc **dễ đọc hơn** đối với đồng nghiệp quen `instanceof`, ép kiểu thủ công và chuỗi `if/else`. Mục tiêu của bài này không phải né các tính năng Java mới, mà là **dùng chúng theo cách người đọc có thể đối chiếu nhanh với cú pháp quen thuộc**, nhận ra luồng điều khiển và hiểu đúng trường hợp nào được xử lý.

Bài thuộc **Java Core Pattern Matching → Tính dễ đọc**. Trọng tâm là chuyển đổi có kiểm soát giữa **`instanceof` + cast**, **type pattern**, **record pattern** và **`switch` có pattern**, kèm hướng dẫn chú thích, đặt tên, review code và tránh những cấu trúc quá cô đọng.

**Quan trọng: có hai loại “tương thích” khác nhau.** Code **dễ hiểu với người từng dùng Java cũ** không đồng nghĩa với code **biên dịch/chạy được trên JDK cũ**. Ví dụ Java 21 vẫn có thể được trình bày rất thân thiện với người dùng Java 8, nhưng một dự án bắt buộc chạy trên Java 8 không thể đưa trực tiếp cú pháp `record` hoặc `case Type variable` vào mã nguồn.

## 1. Xác định đúng loại tương thích trước khi sửa code

### Tương thích với người đọc (readability compatibility)

Một đoạn code thân thiện với người quen Java 8/11 thường có các đặc điểm:

- Tên biến nêu rõ vai trò: `customerId`, `delta`, `reason` thay vì `a`, `b`, `v`.
- Mỗi nhánh `case` trả lời câu hỏi rõ ràng: “Nếu đây là `UserRegistered` thì làm gì?”.
- Không đan nhiều loại cú pháp mới trong một biểu thức dài; khi cần, tách guard hoặc bước xử lý ra phương thức nhỏ.
- Có thể đọc từ trên xuống dưới, không buộc người đọc tự suy luận nhiều cấp deconstruction hay phạm vi biến phức tạp.
- Chú thích nhấn mạnh **nghiệp vụ hoặc lý do chọn cấu trúc**, không phải chú thích từng từ khóa của Java.

### Tương thích biên dịch và chạy (source/binary/runtime compatibility)

Đây là yêu cầu kỹ thuật khác: dự án có phiên bản JDK mục tiêu, chuẩn ngôn ngữ, thư viện/API và môi trường chạy cụ thể. Cú pháp pattern matching không thể được trình biên dịch Java 8 hiểu chỉ bằng cách thêm một comment hoặc đổi tên biến.

| Phiên bản Java | Cú pháp liên quan đã ổn định | Điều người đọc cần biết |
| --- | --- | --- |
| Java 8/11 | `instanceof` truyền thống, ép kiểu, `if/else`; `switch` statement cổ điển | Cần cast khi dùng phương thức riêng của subtype |
| Java 14 | `switch expression`, dạng mũi tên `->` và `yield` (JEP 361) | Switch có thể tạo giá trị, không chỉ thực hiện câu lệnh |
| Java 16 | `instanceof Type variable` (JEP 394), `record` (JEP 395) | Bớt cast, record có accessor/component rõ ràng |
| Java 17 | `sealed class` / `sealed interface` (JEP 409) | Có thể kiểm soát tập subtype được phép |
| Java 21 | Record patterns (JEP 440), pattern matching cho `switch` (JEP 441) | `case Type variable`, `case Record(var ...)`, guard `when` ổn định |

Java 11 có thêm một số API như `String.isBlank()` so với Java 8; bản thân API này không phải tính năng pattern matching. Đừng dựa chỉ vào phong cách viết để đoán phiên bản tối thiểu.

**Quy tắc đặt kỳ vọng:** Bài có hai chương trình mẫu độc lập: một ví dụ chỉ dùng những cấu trúc quen thuộc Java 8, và một ví dụ **Java 21+** so sánh cách viết cổ điển với pattern matching mới trong cùng chương trình. “Cách cổ điển” ở ví dụ thứ hai chỉ mô tả phong cách xử lý, **không** có nghĩa toàn bộ tệp đó chạy được trên Java 8 vì các khai báo `sealed`/`record` vẫn yêu cầu phiên bản mới.

## 2. Dạy một quy tắc chuyển đổi đơn giản trước

Đây là cú pháp Java 8 quen thuộc:

```java
// Trích đoạn Java 8: 'value' có kiểu Object.
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.trim());
}
```

Từ Java 16, có thể viết:

```java
// Trích đoạn Java 16+: 'value' có kiểu Object.
if (value instanceof String text) {
    System.out.println(text.trim());
}
```

Có thể giải thích trong **một câu**: `instanceof String text` thực hiện hai việc trước đây tách riêng — **kiểm tra kiểu `String`** và **khai báo biến `text` có kiểu `String` khi khớp**, nên không phải cast thêm.

Nếu chỉ sửa một đoạn ngắn, kiểu chuyển đổi này thường là điểm bắt đầu tốt: giữ nguyên cấu trúc `if`, giữ nguyên thứ tự điều kiện, chỉ bỏ cast lặp. Nó dễ review hơn việc đồng thời chuyển cả phương thức sang `switch`, đổi tên biến và thay đổi chính sách xử lý lỗi.

### Cách đọc type pattern

```java
if (value instanceof String customerName) {
    // customerName là String tại đây.
}
```

Người đọc hãy tách thành ba phần:

1. `value`: dữ liệu đang xét.
2. `String`: kiểu phải khớp tại runtime.
3. `customerName`: tên biến mới sử dụng **sau khi match**.

Đặt tên `customerName` giúp giải thích ý nghĩa hơn `s` khi dữ liệu là tên khách hàng. Với đoạn chỉ vài dòng, `text` hoặc `number` cũng đủ rõ.

**Không nên nói “compiler ép kiểu ngầm cho mọi nơi trong phương thức”.** Pattern variable chỉ nằm trong phạm vi mà control flow chứng minh pattern đã khớp; bên ngoài phạm vi đó, biến không tồn tại.

## 3. Ví dụ độc lập dùng cú pháp Java 8

Đây là một chương trình hoàn chỉnh không sử dụng `record`, `sealed`, `var`, `switch expression` hay pattern variable. Nó minh họa cách viết có thể đọc được bởi nhóm chưa dùng Java mới.

Lưu tệp **`Java8ReadableDemo.java`**:

```java
public class Java8ReadableDemo {
    static final class Ticket {
        private final String code;

        Ticket(String code) {
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    static String describe(Object input) {
        if (input == null) {
            return "Missing";
        }

        if (input instanceof Ticket) {
            Ticket ticket = (Ticket) input;
            return "Ticket: " + ticket.code();
        }

        if (input instanceof String) {
            String text = (String) input;
            return "Text: " + text.trim();
        }

        return "Other";
    }

    public static void main(String[] args) {
        System.out.println(describe(new Ticket("T-19")));
        System.out.println(describe("  note  "));
        System.out.println(describe(null));
        System.out.println(describe(23));
    }
}
```

Biên dịch bằng JDK hỗ trợ target Java 8 (ví dụ JDK 8 hoặc JDK mới hơn có hỗ trợ `--release 8`). Trên JDK mới phù hợp:

```bash
javac --release 8 Java8ReadableDemo.java
java Java8ReadableDemo
```

Nếu đang dùng **JDK 8**, lệnh biên dịch là `javac Java8ReadableDemo.java` vì JDK 8 chưa có cờ `--release`.

Kết quả:

```text
Ticket: T-19
Text: note
Missing
Other
```

**Vì sao mẫu này dễ theo dõi?** `instanceof` kiểm tra kiểu, dòng cast đặt ngay sau kiểm tra, mỗi nhánh xử lý một loại đầu vào và kết thúc bằng `return`. Đây là mô hình tinh thần mà một độc giả Java 8/11 có thể đem theo khi học pattern matching mới.

**Lưu ý:** đoạn này không có `String.isBlank()`, `List.of()` hoặc API được thêm sau Java 8; nó dùng các cấu trúc cơ bản của Java 8. Khi dự án phải hỗ trợ một JDK cũ, cần kiểm tra **toàn bộ source và dependency**, không chỉ vài dòng chứa pattern.

## 4. Giữ nguyên logic khi đổi sang pattern matching

Một cách học an toàn là **đổi biểu thức nhưng không đổi quy tắc xử lý**:

| Bước | Cách cũ | Cách dùng pattern |
| --- | --- | --- |
| Kiểm tra đối tượng có phải kiểu `T` | `value instanceof T` | `value instanceof T item` |
| Tạo biến đã cast | `T item = (T) value;` | `item` được ràng buộc nếu khớp |
| Gọi phương thức subtype | `item.method()` | `item.method()` như cũ |
| Xử lý không khớp | Nhánh `else`/`return` cũ | Giữ nguyên trong lần refactor đầu |
| Kiểm tra business rule | `if (item.valid())` | Vẫn giữ `if` nếu dễ đọc hơn |

Không cần thay mọi `if` bằng `switch` chỉ vì Java mới cho phép. Nếu phương thức chỉ quan tâm một kiểu, dạng `if (value instanceof T item)` thường rõ ràng nhất.

### Guard clause và phạm vi biến

Một đoạn dễ đọc cho người quen `if`:

```java
// Trích đoạn Java 16+: trong phương thức trả String.
if (!(input instanceof String customerName)) {
    return "Unsupported";
}

return "Customer: " + customerName.trim();
```

Đến dòng `return` cuối, compiler biết rằng nếu pattern không khớp thì phương thức đã thoát. Vì vậy biến `customerName` hợp lệ sau `if`.

Đừng tự động dùng mẫu này nếu chỉ in log khi không khớp:

```java
// SAI: 'customerName' không chắc đã được ràng buộc.
if (!(input instanceof String customerName)) {
    System.out.println("Unsupported");
}
return customerName.trim();
```

Người đọc Java cũ có thể thấy “biến được khai báo trong điều kiện” hơi lạ. Một comment ngắn như “không match đã return ở trên; từ đây customerName là String” có ích tại những đoạn đầu tiên áp dụng pattern matching. Không cần rải comment giống nhau cho mọi nhánh sau khi nhóm đã quen.

## 5. Khi nào chuyển từ `if/else` sang `switch` có pattern?

Khi phương thức thực sự phải xử lý **nhiều loại dữ liệu có liên quan**, `switch` có thể làm rõ **tập trường hợp**. Trước tiên hãy viết từng loại ở một nhánh dễ đọc:

```java
// Trích đoạn Java 21+: 'value' là Object.
String label = switch (value) {
    case String text -> "Text: " + text;
    case Integer number -> "Number: " + number;
    case null -> "Missing";
    default -> "Other";
};
```

Đọc tương đương với chuỗi điều kiện:

- Nếu là `String`, ràng buộc `text` rồi lấy kết quả đầu.
- Nếu là `Integer`, ràng buộc `number` rồi lấy kết quả thứ hai.
- Nếu `null`, dùng nhánh riêng.
- Nếu không thuộc các trường hợp trên, dùng `default`.

**Khác biệt so với `switch` cổ điển:**

- `switch expression` **tạo ra một giá trị**, có thể gán hoặc `return switch (...)`.
- Nhánh dạng `case ... ->` **không fall-through** như cách dùng `case ...:` cũ.
- Một nhánh nhiều câu lệnh của `switch expression` cần `yield result;` để cung cấp giá trị, thay vì `break result;`.
- `case null` xử lý selector `null`; không nên nghĩ `default` tự động thay thế điều kiện null.
- `switch expression` cần **exhaustive**: mọi giá trị selector có thể xảy ra cần có nhánh phù hợp hoặc nhánh xử lý tương ứng.

Nếu một người quen Java 8 dễ nhầm `return` và `yield`, hãy ưu tiên **nhánh mũi tên một biểu thức** khi có thể, hoặc tách xử lý phức tạp ra helper method để hạn chế `yield` rải rác.

## 6. Giới thiệu record pattern như cách gọi accessor ngắn hơn

Ví dụ Java 21+:

```java
record UserRegistered(String userId, String displayName) {}
```

Trước khi dùng record pattern, một cách đọc đơn giản (vẫn sử dụng kiểu `record` của Java mới) là:

```java
// Trích đoạn: 'event' có kiểu Object.
if (event instanceof UserRegistered registered) {
    String id = registered.userId();
    String name = registered.displayName();
    System.out.println(id + ": " + name);
}
```

Sau khi người đọc đã hiểu kiểu record và accessor, có thể rút gọn bằng record pattern:

```java
// Java 21+, trích đoạn: 'event' có kiểu Object.
if (event instanceof UserRegistered(var id, var name)) {
    System.out.println(id + ": " + name);
}
```

Mẫu này đọc là: **nếu `event` là `UserRegistered` thì lấy component thứ nhất vào `id`, component thứ hai vào `name`**. Thứ tự được xác định bởi khai báo record, không dựa vào tên `id`/`name`.

### Tránh nén quá nhiều tầng

Với record lồng nhau:

```java
record Address(String city, String street) {}
record Customer(String id, Address address) {}
```

Cách phân rã hai cấp:

```java
// Java 21+, minh họa khi thật sự cần truy cập cả city và street.
if (value instanceof Customer(var customerId,
                              Address(var city, var street))) {
    System.out.println(customerId + ": " + city + "/" + street);
}
```

Nhưng nếu code chỉ dùng thành phố, hoặc nghiệp vụ còn cần kiểm tra `address == null`, cách từng bước đôi khi dễ đọc hơn:

```java
if (value instanceof Customer(var customerId, var address)) {
    if (address != null) {
        System.out.println(customerId + ": " + address.city());
    }
}
```

**Sự khác biệt quan trọng:** record pattern lồng nhau `Address(...)` **không khớp** khi component `address` bằng `null`; còn `var address` có thể nhận `null`. Khi refactor, phải giữ nguyên chính sách null và nhánh lỗi, không chỉ thấy code ngắn hơn là thay ngay.

Trong một bài toán có nhiều điều kiện nghiệp vụ, nên tránh pattern lồng ba bốn tầng trên một dòng. Trích component một hoặc hai tầng rồi dùng helper method có tên rõ nghĩa thường thân thiện hơn với người mới đọc pattern matching.

## 7. Ví dụ Java 21+: so sánh “cổ điển” và “hiện đại” trên cùng dữ liệu

Chương trình sau dùng **`sealed interface` và `record`**, do đó **chỉ biên dịch với Java 21+ theo cú pháp hiện đại được minh họa**. Hai hàm `describeClassic` và `describeModern` dùng **cùng một mô hình dữ liệu** để so sánh **phong cách xử lý**, không phải để nói toàn bộ hàm cổ điển có thể sao chép sang dự án Java 8.

Tạo tệp **`ReadablePatternsDemo.java`**:

```java
public class ReadablePatternsDemo {
    sealed interface DomainEvent permits UserRegistered, PointsChanged, UserDisabled {}

    record UserRegistered(String userId, String displayName)
            implements DomainEvent {}

    record PointsChanged(String userId, int delta)
            implements DomainEvent {}

    record UserDisabled(String userId, String reason)
            implements DomainEvent {}

    static String describeClassic(DomainEvent event) {
        if (event == null) {
            return "Missing event";
        }

        if (event instanceof UserRegistered) {
            UserRegistered registered = (UserRegistered) event;
            return "Registered " + registered.userId()
                    + ": " + registered.displayName();
        }

        if (event instanceof PointsChanged) {
            PointsChanged points = (PointsChanged) event;
            if (points.delta() > 0) {
                return "Points +" + points.delta()
                        + " for " + points.userId();
            }
            return "Points " + points.delta()
                    + " for " + points.userId();
        }

        if (event instanceof UserDisabled) {
            UserDisabled disabled = (UserDisabled) event;
            return "Disabled " + disabled.userId()
                    + " (" + disabled.reason() + ")";
        }

        throw new IllegalStateException("Unhandled event");
    }

    static String describeModern(DomainEvent event) {
        return switch (event) {
            case UserRegistered(var id, var name) ->
                    "Registered " + id + ": " + name;

            case PointsChanged(var id, var delta) when delta > 0 ->
                    "Points +" + delta + " for " + id;

            case PointsChanged(var id, var delta) ->
                    "Points " + delta + " for " + id;

            case UserDisabled(var id, var reason) ->
                    "Disabled " + id + " (" + reason + ")";

            case null -> "Missing event";
        };
    }

    static String greetClassic(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            if (!text.isBlank()) {
                return "Hi, " + text.trim();
            }
        }
        return "Unknown";
    }

    static String greetModern(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Hi, " + text.trim();
        }
        return "Unknown";
    }

    public static void main(String[] args) {
        DomainEvent[] events = {
                new UserRegistered("u7", "Lan"),
                new PointsChanged("u7", 5),
                new PointsChanged("u7", -2),
                new UserDisabled("u8", "requested"),
                null
        };

        for (DomainEvent event : events) {
            System.out.println(
                    describeClassic(event) + " | " + describeModern(event));
        }

        System.out.println(
                greetClassic("  Mai  ") + " | " + greetModern("  Mai  "));
        System.out.println(greetClassic(42) + " | " + greetModern(42));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac --release 21 -encoding UTF-8 ReadablePatternsDemo.java
java ReadablePatternsDemo
```

Kết quả:

```text
Registered u7: Lan | Registered u7: Lan
Points +5 for u7 | Points +5 for u7
Points -2 for u7 | Points -2 for u7
Disabled u8 (requested) | Disabled u8 (requested)
Missing event | Missing event
Hi, Mai | Hi, Mai
Unknown | Unknown
```

### Đọc từng cặp tương đương

**`describeClassic`** kiểm tra runtime type bằng `instanceof`, thực hiện cast rồi gọi accessor. `describeModern` dùng `case UserRegistered(var id, var name)` để kiểm tra record và lấy component. Kết quả **giống nhau** với các dữ liệu được test.

**`PointsChanged`** có hai nhánh trong bản hiện đại: trường hợp `delta > 0` đứng trước nhánh tổng quát. Guard `when` được hiểu giống điều kiện `if (points.delta() > 0)` của bản cổ điển. Nếu đảo thứ tự hai nhánh `case PointsChanged(...)`, compiler có thể báo **dominated case**: nhánh rộng trước đã bao phủ nhánh hẹp sau.

**`UserDisabled`** minh họa record deconstruction: `var id` lấy component `userId`, `var reason` lấy `reason`. Những tên này là biến cục bộ trong case, không tự động thay tên accessor gốc.

**`case null`** bảo toàn hành vi `if (event == null) return ...` ở bản cổ điển. `switch` còn được compiler kiểm tra độ bao phủ vì `DomainEvent` là sealed hierarchy đã liệt kê các subtype trong ví dụ.

**`greetClassic` và `greetModern`** minh họa chuyển đổi ít rủi ro hơn: chỉ thay cặp `instanceof + cast` bằng type pattern, giữ nguyên kiểm tra `isBlank()` và `trim()`. Đây thường là loại PR đầu tiên nên áp dụng với nhóm mới làm quen pattern matching.

### Những điều ví dụ không chứng minh

Chương trình đã chạy với các trường hợp thử ở trên, nhưng một số bất biến nghiệp vụ không được kiểm tra: `displayName`/`reason` có thể `null`; `delta` có thể âm. Hai hàm trả về kết quả chuỗi giống nhau **trên dữ liệu mẫu**, không đồng nghĩa mọi refactor tương tự đều đúng với mọi dữ liệu đầu vào. Khi áp dụng cho production, cần test thêm trường hợp null, giá trị biên và mọi nhánh theo hợp đồng.

## 8. Giữ tên biến “nói hộ” cho cú pháp mới

Vì pattern có thể vừa kiểm tra kiểu vừa khai báo biến, lựa chọn tên càng quan trọng:

```java
// Khó đọc khi ngữ cảnh phức tạp.
if (value instanceof UserRegistered(var a, var b)) {
    System.out.println(a + b);
}
```

Hãy ưu tiên tên theo ý nghĩa:

```java
if (value instanceof UserRegistered(var userId, var displayName)) {
    System.out.println(userId + ": " + displayName);
}
```

| Thói quen nên áp dụng | Lý do |
| --- | --- |
| Gọi biến theo vai trò (`userId`, `displayName`) | Người đọc khỏi phải nhớ thứ tự component ở chỗ khác |
| Dùng tên ngắn với cấu trúc nhỏ, quen thuộc (`x`, `y` trong `Point`) | Tránh tên quá dài làm loãng biểu thức |
| Đặt guard bên cạnh nhánh cụ thể (`when delta > 0`) | Thấy ngay nguyên nhân nhánh được chọn |
| Tránh `var` khi kiểu suy luận không rõ | Có thể dùng typed component pattern hoặc tách bước |
| Không đổi tên biến, thứ tự case, hành vi null cùng lúc trong một PR | Dễ đối chiếu hành vi trước–sau |
| Giữ một phong cách nhất quán trong module | Độc giả chỉ phải học một quy ước đọc |

Dấu `var` trong record pattern không có nghĩa mọi biến đều có kiểu `Object`. Compiler suy luận kiểu component từ record; ví dụ `PointsChanged(String userId, int delta)` làm `var id` có kiểu `String` và `var delta` có kiểu `int`. Khi đối tượng truyền vào có generic type ít cụ thể, cần xem kỹ kiểu được suy luận để không nhầm.

## 9. Tránh “code golf”: khi nào cú pháp mới làm khó người đọc?

### 9.1. Không lồng nhiều pattern chỉ để ít dòng hơn

Ví dụ dễ gây ngợp:

```java
// Minh họa Java 21+, giả định các record phù hợp đã khai báo.
if (value instanceof Order(var id,
        Customer(var customerId, Address(var city, var street)))) {
    // ...
}
```

Pattern lồng nhau có giá trị khi ta cần **đúng cấu trúc đó**. Nhưng nếu mục tiêu là kiểm tra các trường null với thông điệp lỗi khác nhau, một loạt guard clause sau khi trích `Order` thường dễ hiểu hơn. Có thể chia một điều kiện thành các bước đặt tên:

```java
// Trích đoạn với các kiểu record tương ứng.
if (!(value instanceof Order(var orderId, var customer))) {
    return "Not an order";
}
if (customer == null) {
    return "Missing customer";
}
Address address = customer.address();
if (address == null) {
    return "Missing address";
}
return orderId + " / " + address.city();
```

Hai mẫu **không hoàn toàn tương đương về luồng lỗi**: mẫu lồng nhau chỉ phân biệt “match hay không match”; mẫu có guard trả lý do cụ thể. Chọn cách viết theo nhu cầu diễn đạt chứ không chỉ dựa vào số dòng.

### 9.2. Không ép `switch` vào xử lý chỉ có một loại

Nếu chỉ cần kiểm tra chuỗi rồi trả kết quả, `if (input instanceof String text)` đơn giản hơn `switch` với vài nhánh không có ý nghĩa mới. Dùng `switch` khi nó giúp trình bày một tập biến thể có cùng trọng tâm, đặc biệt với `sealed` hoặc cấu trúc xử lý nhiều kiểu.

### 9.3. Đừng giấu side effect trong guard

`when` phù hợp để kiểm tra điều kiện như `delta > 0` hoặc `name != null && !name.isBlank()`. Không nên thực hiện những thao tác gây side effect khó đoán ngay trong guard (ghi DB, gọi API, cập nhật trạng thái). Độc giả quen Java cũ thường hiểu những thao tác đó dễ hơn khi được viết thành câu lệnh rõ ràng trong nhánh xử lý.

### 9.4. Không nhầm “dễ đọc” với “mỗi nhánh một dòng”

Một `switch` có thể ngắn nhưng khó hiểu nếu có điều kiện dài, biến một chữ, record pattern bốn cấp và fallback không nêu ý nghĩa. Ngược lại, thêm vài dòng `if` để diễn đạt validation rõ ràng có thể là lựa chọn tốt hơn.

## 10. `null`, scope và thứ tự case: nơi độc giả Java cũ dễ nhầm

### `null`: hỏi rõ null ở đâu

- **Selector** bằng `null`: `instanceof` type pattern và record pattern không khớp; `switch` trên tham chiếu null thường ném `NullPointerException` nếu không có xử lý null phù hợp. Dùng `case null` khi null là dữ liệu đầu vào hợp lệ.
- **Component bên trong record** bằng `null`: `record Box(String text) {}` cho phép `text` bằng `null` nếu constructor không chặn; `Box(var text)` có thể khớp và ràng buộc `text == null`.
- **Nested record pattern** như `Outer(Inner(var x))` không khớp khi component `Inner` bằng `null`. Đừng refactor một câu `if (outer.inner() == null)` thành nested pattern rồi quên mất trường hợp null cần báo riêng.

### Scope: dùng biến ở đâu?

```java
// Java 16+, hợp lệ: nếu không khớp, return sớm.
if (!(value instanceof String text)) {
    return "Not string";
}
return text.trim();
```

Bên dưới guard clause, biến `text` được phép dùng vì đường đi không khớp đã kết thúc. Nhưng đừng tham chiếu nó sau một `if` mà nhánh không match vẫn có thể đi tiếp. Dùng `if (value instanceof String text && !text.isBlank())` khi guard cần xem biến được ràng buộc.

### Thứ tự case: hẹp trước rộng

```java
// Java 21+, selector có kiểu Object.
String kind = switch (input) {
    case String text when text.isBlank() -> "Blank";
    case String text -> "Text";
    case CharSequence sequence -> "Other text-like";
    case null -> "Missing";
    default -> "Other";
};
```

- Nhánh `String` có guard đứng trước nhánh `String` tổng quát.
- Nhánh `CharSequence` đứng sau `String` vì `String` implement `CharSequence`.
- Nếu đảo ngược các nhánh rộng/hẹp, Java có thể báo dominance error vì nhánh sau bị nhánh trước che.
- Ngay cả khi code biên dịch, thứ tự guard nghiệp vụ phức tạp vẫn phải được kiểm tra bằng test; compiler không suy luận được mọi quan hệ logic tùy ý.

Cách giải thích thân thiện: “Đi từ trường hợp cụ thể tới trường hợp còn lại, giống `if / else if / else`”, rồi bổ sung rằng compiler còn kiểm tra một số nhánh không thể đạt tới.

## 11. Lộ trình cải tiến theo từng PR, tránh thay đổi lớn

Đội có nhiều người quen Java 8/11 có thể đưa pattern matching vào dự án theo tiến trình:

1. **Thống nhất runtime/build target trước.** Xác định dự án chạy Java nào; không dùng cú pháp mới trong nhánh code yêu cầu Java 8/11.
2. **Bắt đầu bằng type pattern đơn giản.** Thay `instanceof + cast` trong `if`, không đổi business logic. Bổ sung test bảo toàn hành vi.
3. **Đặt tên biến và format nhất quán.** Không ép mọi chỗ phải ngắn nhất; tiêu chí là người mới mở file hiểu được nhánh xử lý.
4. **Giới thiệu `record` và accessor trước record deconstruction.** Khi người đọc đã biết `record` chứa component theo thứ tự, chuyển một số đoạn sang `Record(var a, var b)` ở nơi thật sự giúp ích.
5. **Dùng `switch` khi có nhiều biến thể.** Nếu miền nghiệp vụ có tập subtype đóng, `sealed` + exhaustive `switch` có lợi cho compiler và code review.
6. **Giữ chú thích “why”, hạn chế chú thích “what”.** Giải thích lý do guard hoặc fallback, không lặp lại ý nghĩa của `instanceof` trên từng dòng.
7. **Đo chất lượng bằng review và test.** Reviewer quen Java cũ nên có thể trả lời: dữ liệu nào vào nhánh này, null đi đâu, thiếu loại mới thì thế nào, có còn cùng kết quả không?
8. **Sửa nhỏ và có mục đích.** Không kết hợp refactor pattern matching với thay đổi contract API hoặc schema trong cùng PR nếu có thể tách, vì sẽ khó xác định lỗi đến từ đâu.

Trong tài liệu nội bộ, đôi khi một cặp code “trước / sau” ngắn ngay cạnh nhau hữu ích hơn một chương giải thích toàn lý thuyết. Tuy nhiên, không nhất thiết giữ cả hai cách viết trong production; phần lớn trường hợp chỉ cần giữ cách đã chọn và test rõ ràng.

## 12. Kiểm tra tính tương thích kỹ thuật khi thật sự phải hỗ trợ JDK cũ

Nếu yêu cầu sản phẩm là **chạy trên Java 8**, việc viết code “trông như Java 8” chưa đủ. Cần biên dịch/test theo đích tương ứng:

```bash
# Ví dụ với JDK hiện đại có hỗ trợ biên dịch cho Java 8.
javac --release 8 Java8ReadableDemo.java
```

Với tệp dùng sealed types, records hoặc `case ... when ...`:

```bash
# Ví dụ với JDK 21+ và mã nguồn Java 21.
javac --release 21 -encoding UTF-8 ReadablePatternsDemo.java
```

**`--release`** giúp kiểm tra ngôn ngữ, bytecode và API Java Platform tương ứng mục tiêu theo hỗ trợ của `javac`. Nó không tự làm thư viện phụ thuộc tương thích, không biến cú pháp Java 21 thành Java 8, và không thay thế việc chạy integration test trên JVM thực tế.

Với Gradle/Maven, hãy đặt toolchain hoặc compiler release thống nhất theo dự án, chạy CI cho phiên bản mục tiêu, và để IDE báo lỗi ngay khi vô tình sử dụng API hoặc cú pháp mới. Nếu nhóm cần phát hành thư viện dùng cho Java 8 và Java 21, có thể tách module/API tương thích hoặc có những adapter phù hợp thay vì ép một codebase duy nhất dùng cú pháp mới trên target cũ.

### Phân biệt ba tuyên bố

| Tuyên bố | Có đúng không? |
| --- | --- |
| “Người từng dùng Java 8 có thể hiểu code Java 21 nếu viết rõ ràng.” | Có thể, khi có ví dụ đối chiếu, tên tốt và độ phức tạp hợp lý |
| “Dùng `instanceof String s` vẫn chạy trên Java 8.” | **Không**; type pattern ổn định từ Java 16, Java 8 không hiểu cú pháp |
| “Không dùng pattern matching là code Java 8.” | **Không đủ**; có thể vẫn dùng `record`, `sealed`, switch expression hoặc API mới |
| “Dùng `--release 8` là bảo đảm mọi dependency và runtime đều an toàn.” | **Không**; cần kiểm tra dependency và chạy/test trên môi trường mục tiêu |
| “Code hiện đại ngắn hơn chắc chắn dễ đọc hơn.” | **Không**; tên, scope, số tầng pattern và độ rõ ràng nghiệp vụ quan trọng hơn độ ngắn |

## 13. Checklist review giúp nhóm quen Java cũ

Khi xem một PR có pattern matching, reviewer có thể kiểm tra:

- **Phiên bản:** tính năng có hợp với JDK/build target không?
- **So sánh trước–sau:** việc chuyển từ `instanceof + cast` sang pattern có giữ cùng luồng match/fallback không?
- **Tên biến:** người chưa quen thứ tự component có đoán được biến chứa gì không?
- **Phạm vi:** pattern variable có được sử dụng chỉ ở chỗ chắc chắn đã khớp không?
- **Null:** selector và nested component null có được xử lý đúng theo hợp đồng cũ không?
- **Thứ tự case:** nhánh có guard/kiểu hẹp đã đứng trước nhánh rộng chưa?
- **Exhaustiveness:** với sealed hierarchy, thiếu biến thể có được compiler chỉ ra không hay `default` che đi?
- **Nghiệp vụ:** có validation bị bỏ mất khi rút ngắn biểu thức không?
- **Độ phức tạp:** pattern lồng nhiều cấp có đáng giá hơn các bước truy cập rõ tên không?
- **Kiểm thử:** các trường hợp thành công, thất bại, null, giá trị biên và biến thể mới có được cover không?

Điểm mấu chốt không phải “đã dùng hết tính năng Java 21 chưa”, mà là **người bảo trì tiếp theo có thể sửa đúng mà không phải giải mã một biểu thức khó hiểu hay không**.

## 14. Lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Khẳng định code “hỗ trợ Java 8” chỉ vì vẫn dùng `if` | Các khai báo hoặc API khác có thể yêu cầu JDK mới | Kiểm tra `--release 8` và test runtime; dùng cấu trúc Java 8 thật sự |
| Chuyển mọi chuỗi `if` thành `switch` | Thay cú pháp nhưng không tăng độ rõ ràng | Dùng `if` cho trường hợp đơn giản; `switch` cho tập biến thể |
| Dùng `var a, var b, var c` trong record lớn | Người đọc không biết biến lấy từ component nào | Đặt tên rõ nghĩa hoặc tách bước lấy component |
| Refactor nested record pattern rồi bỏ mất xử lý `null` | Pattern lồng không khớp record component null | Giữ guard/fallback null tương đương |
| Cho rằng `default` xử lý null | Selector null có ngữ nghĩa riêng | Dùng `case null` hoặc từ chối null tường minh |
| Đặt case tổng quát trước case có guard | Nhánh hẹp bị che, dominance error | Sắp case cụ thể trước |
| Dùng pattern variable ngoài phạm vi match | Compiler không thể chứng minh biến đã được ràng buộc | Dùng trong nhánh khớp hoặc guard clause có `return` |
| Trộn migration syntax với thay đổi nghiệp vụ trong cùng PR | Khó kiểm tra kết quả có tương đương không | Tách thay đổi, viết test đặc tả hành vi |
| Giải thích code mới bằng quá nhiều thuật ngữ mà không có ví dụ | Tăng gánh nặng nhận thức | Cho cặp code cổ điển/hiện đại, giải thích từng bước |
| Tin rằng refactor ngắn hơn là hiệu quả hơn | Số dòng không đo được độ rõ ràng | Tối ưu khả năng hiểu, kiểm thử và bảo trì |

## 15. Bài tập tự luyện

### Bài 1 — Chuyển từng bước, không đổi hành vi

Cho đoạn code Java cũ:

```java
// Trích đoạn trong phương thức trả String.
if (input instanceof String) {
    String text = (String) input;
    return text.trim();
}
return "Other";
```

Viết lại cho Java 16+ mà vẫn dùng `if`.

**Đáp án:**

```java
if (input instanceof String text) {
    return text.trim();
}
return "Other";
```

Giữ nguyên kiểu đầu ra và hành vi null: khi `input == null`, `instanceof` không khớp, nên kết quả vẫn là `"Other"`.

### Bài 2 — Chọn tên biến cho record pattern

Với `record Refund(String paymentId, long amountCents) {}`, cách nào dễ đọc hơn trong đoạn xử lý hoàn tiền?

```java
// A
if (value instanceof Refund(var x, var y)) {
    System.out.println(x + " " + y);
}

// B
if (value instanceof Refund(var paymentId, var amountCents)) {
    System.out.println(paymentId + ": " + amountCents);
}
```

**Đáp án:** B dễ đọc hơn đối với đa số ngữ cảnh nghiệp vụ vì người đọc không phải quay lại record declaration để nhớ `x` và `y`. Cả hai đều hợp lệ về cú pháp Java 21+.

### Bài 3 — Sửa dominance

Với `Object input`, sắp xếp lại các nhánh:

```java
// CỐ Ý SAI vì nhánh String tổng quát đứng trước guard.
String label = switch (input) {
    case String text -> "Text";
    case String text when text.isBlank() -> "Blank";
    case null -> "Missing";
    default -> "Other";
};
```

**Đáp án:**

```java
String label = switch (input) {
    case String text when text.isBlank() -> "Blank";
    case String text -> "Text";
    case null -> "Missing";
    default -> "Other";
};
```

Nhánh đặc biệt phải đứng trước nhánh tổng quát. Cách đọc tương tự `if (isString && blank) ... else if (isString) ...`.

### Bài 4 — Đọc tương đương giữa accessor và deconstruction

Giả sử `record Ticket(String code, int priority) {}`. Hai đoạn sau có luôn cùng hành vi không?

```java
// Mẫu thứ nhất
if (input instanceof Ticket ticket) {
    System.out.println(ticket.code());
}

// Mẫu thứ hai
if (input instanceof Ticket(var code, var priority)) {
    System.out.println(code);
}
```

**Đáp án:** Với một đối tượng `Ticket` hợp lệ theo mô hình trên, cả hai đều lấy component `code` và in ra; cả hai không chạy khi selector `input` là null. Tuy nhiên, mẫu thứ hai yêu cầu record pattern từ **Java 21**, trong khi `instanceof Ticket ticket` là type pattern ổn định từ **Java 16**. Nếu target Java quá cũ, cả hai vẫn không biên dịch như viết ở đây; cần `instanceof Ticket` + cast và một kiểu `Ticket` hợp lệ cho target đó.

### Bài 5 — Kế hoạch migration

Nhóm đang chạy Java 11, muốn code dễ đọc và dự kiến lên Java 21. Có nên merge các record patterns Java 21 vào nhánh Java 11 trước khi nâng target không?

**Đáp án:** Không. Trước khi nâng JDK/build target, chỉ refactor trong giới hạn cú pháp/API Java 11, bổ sung test và chuẩn bị ví dụ đối chiếu. Khi target đã chuyển sang Java 21, mới cân nhắc chuyển dần sang type patterns, record patterns hoặc `switch` theo từng PR có phạm vi rõ ràng.

## 16. Ghi nhớ và tài liệu

- **“Người Java cũ đọc được” không đồng nghĩa “JDK cũ biên dịch được”.** Phân biệt readability compatibility với source/runtime compatibility.
- Giới thiệu pattern matching bằng phép đối chiếu **`instanceof + cast` → `instanceof Type variable`**, rồi mới mở rộng sang record patterns và `switch`.
- Giữ code dễ đọc bằng **tên rõ nghĩa, nhánh ngắn, guard có mục đích, xử lý null tường minh** và số tầng deconstruction hợp lý.
- Không đổi hành vi nghiệp vụ chỉ vì cú pháp mới ngắn hơn; dùng test để kiểm tra các trường hợp match, không match và dữ liệu biên.
- Chọn `if` cho kiểm tra đơn giản và `switch` cho nhiều biến thể có liên quan. Với sealed hierarchy, exhaustive switch không `default` có thể giúp compiler nhắc khi thêm subtype.
- Chuyển đổi có kiểm soát theo từng bước là cách giúp người từng dùng Java 8/11 hiểu Java 21 nhanh nhất mà vẫn giữ khả năng bảo trì.

**Tài liệu chính thức:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 395 — Records](https://openjdk.org/jeps/395), [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361), [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
