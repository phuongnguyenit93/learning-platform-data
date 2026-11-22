# Thiết kế contract null của domain type trong Java 21

## 1. Vì sao contract null là quyết định thiết kế domain?

Trong Java, một reference có thể nhận giá trị `null`, nhưng **việc Java cho phép null không có nghĩa domain cho phép null**. Một kiểu `Order` có `customerId == null`, `destination == null` hoặc `amount <= 0` có thể là trạng thái vô nghĩa với nghiệp vụ. Ngược lại, một yêu cầu nhập liệu đang dở dang có thể hợp lệ khi `city` chưa được cung cấp.

**Null contract** là cam kết mà một kiểu dữ liệu hoặc API công bố: trường nào bắt buộc có giá trị, trường nào có thể vắng mặt, vắng mặt mang ý nghĩa gì, nếu vi phạm thì chuyện gì xảy ra và tầng nào chịu trách nhiệm xử lý.

Ví dụ một bản ghi:

```java
record Address(String city) {}
record Order(String id, Address address) {}
```

Cú pháp trên **không tự cấm**:

```java
new Order(null, null);
```

Dù các component có kiểu `String` và `Address`, canonical constructor mặc định không bổ sung validation. Hơn nữa, `record` chỉ có **bất biến nông**: final reference không bảo đảm mọi đối tượng mà nó tham chiếu là immutable.

Khi dùng **record patterns** và **pattern matching cho `switch`**, contract null quyết định liệu một nhánh có khớp, liệu guard `when` có được xét và liệu cần nhánh dự phòng hay không. Thiết kế contract sai có thể gây `NullPointerException` bất ngờ, nhánh `case` không chạy, hoặc dữ liệu thiếu bị hiểu nhầm là dữ liệu hợp lệ.

Bài này tập trung vào ba chiến lược: **từ chối null đối với dữ liệu bắt buộc; chấp nhận vắng mặt có chủ đích ở boundary; biểu diễn sự lựa chọn/thiếu vắng bằng kiểu domain tường minh**. Sau đó ta kết nối chúng với cách kiểm tra pattern và exception trong Java.

**Phiên bản:** `record` chính thức từ Java 16; `instanceof` type patterns ổn định từ Java 16; **record patterns (JEP 440)** và **pattern matching cho `switch` (JEP 441)** chính thức từ **Java 21**. Chương trình mẫu dùng JDK 21+ và không cần `--enable-preview`.

## 2. Bốn câu hỏi phải trả lời cho từng component

Trước khi khai báo một domain type, lập bảng:

| Câu hỏi | Ví dụ với đơn hàng | Quyết định cần ghi rõ |
| --- | --- | --- |
| Giá trị có bắt buộc không? | `customerId` | Bắt buộc, không chấp nhận null |
| Vắng mặt có ý nghĩa riêng không? | Địa chỉ giao hàng khi khách đến nhận tại quầy | Không dùng null mơ hồ; có thể dùng biến thể Pickup |
| Nếu có mặt, thế nào là hợp lệ? | Mã khách không rỗng, số tiền dương | Chuẩn hóa và kiểm tra ở constructor |
| Vi phạm contract thì sao? | `new Order(null, ...)` | Ném exception sớm, không tạo domain object nửa hợp lệ |

Một contract tốt phải áp dụng nhất quán ở:
- **Constructor/factory:** đối tượng được tạo có hợp lệ không?
- **Accessor/method:** kết quả có thể null hay không?
- **Boundary API:** input ngoài hệ thống được phép thiếu gì?
- **Pattern matching:** nhánh nào xử lý thiếu dữ liệu, nhánh nào giả định invariant?
- **Test:** trường hợp null được chấp nhận hoặc bị từ chối như thế nào?

Đừng dùng quy ước “ai cũng hiểu field này không bao giờ null” thay cho constructor, kiểu dữ liệu, tài liệu và test.

## 3. Chiến lược 1 — Fail fast: từ chối null ở domain invariant

Với dữ liệu **bắt buộc**, cách rõ nhất thường là từ chối ngay khi tạo value object:

```java
record CustomerId(String value) {
    CustomerId {
        value = java.util.Objects.requireNonNull(
            value, "customerId").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException(
                "customerId must not be blank");
        }
    }
}
```

**Compact canonical constructor** nhận tham số cùng tên component. Việc gán lại tham số `value` để chuẩn hóa được phép; khi constructor kết thúc bình thường, Java gán giá trị đã xử lý cho field cuối cùng tương ứng.

Contract của `CustomerId` ở ví dụ:

1. Tham số null → `NullPointerException` với thông báo `customerId`.
2. Chuỗi rỗng/toàn khoảng trắng → `IllegalArgumentException`.
3. Chuỗi có khoảng trắng hai đầu → được chuẩn hóa bằng `strip()`.
4. Sau khi tạo thành công, `value()` là chuỗi không-null, không rỗng.

**Chọn loại exception theo hợp đồng**, không vì một lựa chọn duy nhất bắt buộc cho mọi ứng dụng. `Objects.requireNonNull` thường dùng để khẳng định tham chiếu bắt buộc và ném `NullPointerException`. `IllegalArgumentException` phù hợp cho giá trị có mặt nhưng vi phạm miền cho phép. Với domain cần thông báo lỗi có cấu trúc, có thể dùng một exception/domain-result riêng, nhưng chính sách phải thống nhất và được tài liệu hóa.

Với reference bắt buộc khác:

```java
record Shipment(CustomerId customerId, Address destination) {
    Shipment {
        java.util.Objects.requireNonNull(customerId, "customerId");
        java.util.Objects.requireNonNull(destination, "destination");
    }
}
```

Trong những object được xây đúng constructor này, `shipment.customerId()` và `shipment.destination()` luôn không-null. Các phương thức xử lý không cần lặp lại null-check chỉ để bù cho một invariant đã có.

**Chú ý:** điều này không có nghĩa mọi `Shipment` được nhận từ mọi cơ chế serialization/framework đều bảo đảm contract mà không cần xét. Hãy kiểm tra cách thư viện khôi phục object và đường đi dữ liệu ở boundary.

## 4. Chiến lược 2 — Vắng mặt được cho phép, nhưng phải định nghĩa nghĩa của nó

Một số dữ liệu **thực sự tùy chọn**. Ví dụ số điện thoại liên hệ của người dùng:

```java
record Contact(String email, String phone) {
    Contact {
        email = java.util.Objects.requireNonNull(
            email, "email").strip();
        if (email.isEmpty()) {
            throw new IllegalArgumentException("email is blank");
        }
        // Contract ví dụ: phone có thể null nghĩa là chưa cung cấp.
    }
}
```

Ở đây `phone == null` **không phải bug** nếu contract công khai nói rõ nó có nghĩa là “chưa cung cấp số điện thoại”. Nhưng caller phải nhớ điều kiện trước khi dùng:

```java
String phone = contact.phone();
if (phone != null && !phone.isBlank()) {
    System.out.println("Có số: " + phone);
}
```

Đổi lại, null có thể bị truyền xa và buộc nhiều tầng kiểm tra. Với domain có nhiều tình huống thiếu vắng hoặc các ràng buộc giữa field, một kiểu thể hiện trạng thái rõ ràng thường tốt hơn.

### `Optional` dùng thế nào?

`Optional<T>` giúp diễn đạt **kết quả có thể vắng mặt**, chẳng hạn:

```java
static java.util.Optional<String> findPhone(Contact contact) {
    return java.util.Optional.ofNullable(contact.phone());
}
```

Caller có thể dùng `ifPresent`, `orElse`, `map` hoặc `isPresent`. Tuy nhiên, `Optional` **không tự biến component bên trong record thành non-null**, và cũng không nên được coi là cách dùng bắt buộc cho mọi field. Bản thân tham chiếu `Optional` cũng có thể null nếu thiếu validation; `Optional.empty()` mới là trạng thái vắng mặt rõ.

Đối với domain model, cân nhắc API và framework: `Optional` thường hữu ích ở **return type**, còn component/field cần quyết định dựa trên contract, serialization và ngôn ngữ biểu diễn trạng thái. Nếu “chưa có” là một trạng thái nghiệp vụ riêng, có thể dùng sealed variants như mục kế tiếp.

## 5. Chiến lược 3 — Thay null mơ hồ bằng biến thể domain

Hãy xét đơn hàng: giao tận nhà cần **địa chỉ**, còn khách đến nhận tại quầy cần **mã chi nhánh**. Khai báo:

```java
record Order(String id, Address deliveryAddress,
             String pickupBranch) {}
```

làm phát sinh tổ hợp khó hiểu: cả hai null, cả hai có giá trị, hoặc chỉ một có giá trị. Mỗi nơi xử lý đều phải nhớ “chính xác một trong hai được phép khác null”.

Một mô hình tường minh hơn:

```java
sealed interface Destination permits ShipTo, CollectAt {}

record ShipTo(Address address) implements Destination {
    ShipTo {
        java.util.Objects.requireNonNull(address, "address");
    }
}

record CollectAt(String branchCode) implements Destination {
    CollectAt {
        branchCode = java.util.Objects.requireNonNull(
            branchCode, "branchCode").strip();
        if (branchCode.isEmpty()) {
            throw new IllegalArgumentException("branchCode is blank");
        }
    }
}
```

Bây giờ một `Destination` hợp lệ là **ShipTo** hoặc **CollectAt**. Constructor của từng biến thể giữ invariant riêng, thay vì buộc `Order` suy đoán dựa trên các cặp null.

Lợi ích:
- Ý nghĩa nghiệp vụ hiện trong **tên kiểu**, không ẩn trong null.
- Không tạo trạng thái “giao hàng mà không có địa chỉ” qua canonical constructor của `ShipTo`.
- `switch` theo sealed hierarchy có thể kiểm tra bao phủ các biến thể ở compile-time.
- Khi thêm `LockerPickup` chẳng hạn, code điều phối có thể được compiler nhắc cập nhật.

Tuy nhiên **không ép mọi field tùy chọn thành sealed hierarchy**. Một nullable phone đơn giản có thể đủ nếu contract được hiểu rõ. Chọn kiểu riêng khi sự vắng mặt kéo theo hành vi, invariant hoặc phân nhánh nghiệp vụ riêng.

## 6. Null semantics trong pattern matching

### 6.1. `instanceof` với selector null

```java
Object value = null;
if (value instanceof String text) {
    System.out.println(text.length()); // Không chạy.
}
```

`null` không khớp type pattern `String text`; `instanceof` trả `false`. Biến `text` chỉ nằm trong phạm vi được compiler bảo đảm pattern đã khớp.

### 6.2. `switch` cần chính sách riêng cho selector null

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "Đầu vào null";
        case String s -> "Chuỗi: " + s;
        default -> "Kiểu khác";
    };
}
```

Trong pattern-matching `switch`, **`case null`** xử lý selector null. Đừng giả định `default` luôn bắt null: nếu không có case null thích hợp, selector null có thể gây `NullPointerException` theo quy tắc của enhanced switch. Null handling cần được thiết kế rõ theo hợp đồng API, không nên “để default tính sau”.

### 6.3. `var` trong record pattern có thể nhận component null

```java
record RawAddress(String city) {}

if (value instanceof RawAddress(var city)) {
    // city có kiểu String, nhưng vẫn có thể là null.
    System.out.println(city == null ? "(chưa có)" : city);
}
```

Record pattern `RawAddress(var city)` yêu cầu đối tượng **RawAddress** ở tầng ngoài không-null, nhưng `var city` nhận giá trị của component, kể cả khi đó là null. **Kiểu tĩnh String không bảo đảm non-null**.

So sánh với nested pattern:

```java
record Customer(RawAddress address) {}

// address phải là RawAddress không-null để khớp.
if (value instanceof Customer(RawAddress(var city))) {
    // city vẫn có thể null.
    System.out.println(city);
}
```

Nếu `Customer.address() == null`, nested `RawAddress(...)` không khớp, nên **toàn bộ `Customer(...)` không khớp**. Không có guard nào phía sau được gọi cho nhánh ấy.

### 6.4. Guard `when` được xét sau khi pattern khớp

```java
// Nhãn case minh họa bên trong một switch phù hợp.
case RawAddress(var city) when city != null && !city.isBlank() ->
    "Thành phố: " + city;
```

Pattern bên ngoài phải khớp trước, sau đó guard kiểm tra component. `city != null` đứng **trước** `!city.isBlank()` để tránh NPE nhờ tính short-circuit của `&&`. Guard false khiến `switch` xem xét nhánh kế tiếp, chứ không tự báo lỗi validation.

Nếu record constructor đã **cấm null và blank**, guard này có thể dư thừa đối với instance được xây đúng contract. Dù vậy guard vẫn hữu ích cho **quy tắc phụ thuộc ngữ cảnh**, ví dụ chỉ cho phép một số thành phố nhận hàng.

## 7. Phân biệt ba tình huống: fail match, fail guard, fail constructor

| Tình huống | Ví dụ | Hệ quả |
| --- | --- | --- |
| **Constructor từ chối** | `new ShipTo(null)` | Ném NPE ngay khi tạo; không có `ShipTo` hợp lệ |
| **Pattern không khớp** | `Customer(RawAddress(...))` khi `address == null` | Nhánh không được chọn, guard không chạy |
| **Pattern khớp nhưng guard sai** | `RawAddress(var city) when city != null` với `city == null` | Nhánh không được chọn; xét nhánh khác |
| **Pattern khớp và guard đúng** | `RawAddress("Huế")` với guard nonblank | Chạy thân nhánh |
| **Selector của `switch` null** | `switch (null)` không có xử lý null phù hợp | Có thể ném NPE; phải thiết kế `case null` hoặc chặn trước |
| **Dùng reference nullable không kiểm tra** | `city.isBlank()` khi `city == null` | NPE khi thực thi lời gọi |

Đây là các cơ chế khác nhau. **Không dùng một pattern/guard như biện pháp thay thế cho invariant của constructor**, và không coi mọi exception là “match thất bại”.

## 8. Ranh giới: dữ liệu thô khác domain object đã xác thực

Một DTO đầu vào (JSON, form, message queue) thường chứa dữ liệu **chưa đầy đủ hoặc chưa đáng tin**. Domain type nên được tạo **sau khi đã kiểm tra và chuẩn hóa**.

```text
Input HTTP / JSON / file
        |
        v
Raw DTO (có thể thiếu field, null, blank)
        |
        v
Parse + Validate + Normalize
        |
        +--> Input error / Result lỗi rõ ràng
        |
        v
Domain value objects (invariant được bảo vệ)
        |
        v
Business rules / pattern matching / persistence
```

Ví dụ:
- `RawOrder` có `customerId == null`: biểu thị input thiếu; nơi tiếp nhận có thể trả lỗi 400 kèm danh sách field (tùy giao thức).
- `CustomerId` đã tạo thành công: không-null, không blank; code domain có thể dựa vào invariant.
- `Destination` là một trong hai biến thể rõ nghĩa: không cần suy đoán “cả địa chỉ và mã chi nhánh đều null thì phải làm gì?”.
- Khi hợp đồng yêu cầu gửi lỗi có cấu trúc, nên convert validation exception sang phản hồi theo chính sách API ở boundary. Không nên trả trực tiếp stack trace hoặc chi tiết nội bộ cho client.

**Tránh vừa chấp nhận null ở domain constructor, vừa âm thầm biến nó thành chuỗi trống hoặc một ID giả.** Việc đó che dữ liệu sai, khiến logic phía sau không phân biệt được “thiếu” và “giá trị thực”.

## 9. Chương trình Java 21 hoàn chỉnh: contract, nested patterns và null

Tạo tệp **`DomainNullContractDemo.java`**:

```java
import java.util.Objects;

public class DomainNullContractDemo {

    // Raw DTO cố ý chưa validate: null là dữ liệu cần kiểm tra.
    record RawOrder(String customerId, String city) {}

    record CustomerId(String value) {
        CustomerId {
            value = Objects.requireNonNull(
                value, "customerId").strip();
            if (value.isEmpty()) {
                throw new IllegalArgumentException(
                    "customerId must not be blank");
            }
        }
    }

    record Address(String city) {
        Address {
            city = Objects.requireNonNull(city, "city").strip();
            if (city.isEmpty()) {
                throw new IllegalArgumentException("city is blank");
            }
        }
    }

    sealed interface Destination permits ShipTo, CollectAt {}

    record ShipTo(Address address) implements Destination {
        ShipTo {
            Objects.requireNonNull(address, "address");
        }
    }

    record CollectAt(String branchCode) implements Destination {
        CollectAt {
            branchCode = Objects.requireNonNull(
                branchCode, "branchCode").strip();
            if (branchCode.isEmpty()) {
                throw new IllegalArgumentException(
                    "branchCode is blank");
            }
        }
    }

    record Order(CustomerId customerId,
                 Destination destination,
                 long amount) {
        Order {
            Objects.requireNonNull(customerId, "customerId");
            Objects.requireNonNull(destination, "destination");
            if (amount <= 0) {
                throw new IllegalArgumentException(
                    "amount must be positive");
            }
        }
    }

    // Ở boundary: pattern var có thể nhận component null.
    static String inspectRaw(Object value) {
        return switch (value) {
            case null -> "Raw: null";

            case RawOrder(var id, var city)
                    when id == null || id.isBlank() ->
                "Raw: thiếu khách";

            case RawOrder(var id, var city)
                    when city == null || city.isBlank() ->
                "Raw: thiếu thành phố";

            case RawOrder(var id, var city) ->
                "Raw: " + id.strip() + "/" + city.strip();

            default -> "Raw: sai kiểu";
        };
    }

    // Ở domain: constructor đã bảo vệ các nested component.
    static String route(Object value) {
        return switch (value) {
            case null -> "Order: null";

            case Order(
                    CustomerId(var id),
                    ShipTo(Address(var city)),
                    var amount)
                    when amount >= 1_000 ->
                "Ưu tiên: " + id + " -> " + city;

            case Order(
                    CustomerId(var id),
                    ShipTo(Address(var city)),
                    var amount) ->
                "Giao: " + id + " -> " + city;

            case Order(
                    CustomerId(var id),
                    CollectAt(var branchCode),
                    var amount) ->
                "Nhận: " + id + " @ " + branchCode;

            default -> "Order: sai kiểu";
        };
    }

    public static void main(String[] args) {
        System.out.println(
            inspectRaw(new RawOrder(null, "Huế")));
        System.out.println(
            inspectRaw(new RawOrder(" C-9 ", null)));
        System.out.println(
            inspectRaw(new RawOrder(" C-9 ", " Huế ")));
        System.out.println(inspectRaw(null));

        CustomerId customerId = new CustomerId(" C-9 ");
        Address address = new Address(" Huế ");

        System.out.println(route(new Order(
            customerId, new ShipTo(address), 1_500)));

        System.out.println(route(new Order(
            customerId, new ShipTo(address), 500)));

        System.out.println(route(new Order(
            customerId, new CollectAt(" Q1 "), 200)));

        System.out.println(route(null));
        System.out.println(route(new RawOrder("X", "Huế")));

        try {
            new Order(customerId, null, 100);
        } catch (NullPointerException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }

        try {
            new CustomerId("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Từ chối mã khách rỗng");
        }
    }
}
```

Biên dịch và chạy với **JDK 21+**, ở thư mục chứa tệp:

```bash
javac --release 21 -encoding UTF-8 DomainNullContractDemo.java
java DomainNullContractDemo
```

Kết quả dự kiến:

```text
Raw: thiếu khách
Raw: thiếu thành phố
Raw: C-9/Huế
Raw: null
Ưu tiên: C-9 -> Huế
Giao: C-9 -> Huế
Nhận: C-9 @ Q1
Order: null
Order: sai kiểu
Từ chối: destination
Từ chối mã khách rỗng
```

### 9.1. Vì sao dữ liệu thô không ném exception ngay?

`RawOrder` là DTO ở boundary. Trong ví dụ này constructor mặc định cho phép `null`; `inspectRaw` diễn giải nó thành lỗi thiếu field. Nhánh `case RawOrder(var id, var city)` vẫn khớp với raw record có component null, nhờ `var`. Vì hai guard đầu đã xử lý null/blank, nhánh RawOrder tổng quát chỉ nhận các dữ liệu còn lại.

Nhánh guard đầu được ưu tiên nếu **cả id và city đều thiếu**. Đây là **chính sách phân loại lỗi đầu tiên**, không phải kết luận rằng hệ thống chỉ có một lỗi. Một API muốn trả danh sách mọi lỗi nên dùng validation tổng hợp thay vì chỉ một `switch` trả chuỗi.

### 9.2. Vì sao domain không cần lặp mọi guard null?

`CustomerId`, `Address`, `ShipTo`, `CollectAt` và `Order` được thiết kế với invariant rõ ràng. Khi gọi constructor thành công, code dùng `route` có thể dựa vào các giá trị bắt buộc đã có mặt.

Nhánh `Order(CustomerId(var id), ShipTo(Address(var city)), var amount)` chỉ có thể match khi các tầng `Order → CustomerId` và `Order → ShipTo → Address` đều khớp record tương ứng. Với các instance tạo qua constructor có invariant, những tầng này không-null. Guard `amount >= 1000` là **quy tắc nghiệp vụ theo ngữ cảnh**, khác với invariant `amount > 0` được constructor bảo vệ.

**Lưu ý:** `case null` của `route` vẫn có ý nghĩa khi **chính biến đầu vào cho route là null**, ngay cả khi constructor Order không cho phép component null.

### 9.3. Vì sao `CollectAt` tốt hơn một địa chỉ null?

Nếu khách nhận tại quầy, thông tin cần thiết là `branchCode`. Với sealed variant `CollectAt`, không phải để `ShipTo(null)` rồi giải thích “null là nhận tại quầy”. Cấu trúc domain thể hiện trực tiếp hành vi:

- `ShipTo(Address)`: có địa chỉ giao.
- `CollectAt(String branchCode)`: có chi nhánh nhận.
- `Order.destination`: bắt buộc là một trong các biến thể đó.

Điều này giảm số tổ hợp trạng thái không hợp lệ và làm `switch` dễ bao phủ.

### 9.4. Phân biệt exception và kết quả phân loại

`new Order(customerId, null, 100)` ném `NullPointerException("destination")` **trước khi một Order hợp lệ xuất hiện**. Không có nhánh `route` nào xử lý nó vì record chưa tạo thành công. Đây là fail-fast theo contract constructor.

`route(new RawOrder(...))` không ném exception; nó trả `"Order: sai kiểu"` theo `default` vì selector kiểu `Object` có thể là loại khác. Đây là xử lý đầu vào tại boundary, không phải lỗi constructor.

## 10. Chọn exception, result hay null: một contract cho mỗi API

| Trường hợp | Thiết kế thường phù hợp | Lý do |
| --- | --- | --- |
| Constructor của value object có field bắt buộc null | `Objects.requireNonNull` hoặc lỗi validation đã định nghĩa | Fail fast, giữ invariant |
| Giá trị không-null nhưng sai định dạng/miền | `IllegalArgumentException` hoặc domain validation error | Phân biệt “thiếu” với “có nhưng sai” |
| Tìm kiếm có thể không có kết quả, đây là tình huống bình thường | `Optional<T>`, kết quả typed hoặc kiểu trạng thái riêng | Tránh coi vắng mặt bình thường là exception |
| Nghiệp vụ có các biến thể hợp lệ loại trừ nhau | `sealed interface` với các record/class variants | Biểu diễn trạng thái trong type system |
| Input chưa validate từ HTTP/JSON | Raw DTO nullable + bước validate/parse | Thu thập lỗi thân thiện tại boundary |
| Hàm gặp vi phạm invariant không thể tự hồi phục | Exception theo contract hoặc result lỗi có cấu trúc | Tránh tiếp tục với trạng thái sai |
| Một field có thể vắng mặt nhưng không có hành vi riêng | Nullable field được tài liệu hóa, hoặc optional return | Giữ mô hình đơn giản nếu đủ rõ |

**Phân biệt lỗi lập trình và tình huống nghiệp vụ bình thường.** Vi phạm `Order.destination` bắt buộc là dấu hiệu caller đã truyền dữ liệu không hợp lệ. “Không tìm thấy địa chỉ giao gần đây” có thể là tình huống bình thường cần một kiểu kết quả vắng mặt, không nhất thiết ném NPE.

Không khuyến khích **catch `NullPointerException` trên diện rộng** để biến mọi null thành kết quả “dữ liệu thiếu”. Làm vậy có thể che lỗi khác như dereference null ngoài dự kiến. Hãy kiểm tra ở boundary hoặc tại constructor, và bắt exception ở tầng biết cách chuyển sang thông điệp hợp lệ.

## 11. Null contract ảnh hưởng thứ tự case và tính exhaustive

Đối với `switch` có nhiều pattern, thứ tự case vẫn quan trọng. Ví dụ:

```java
// Minh họa trong switch nhận Object:
case RawOrder(var id, var city) when id == null ->
    "Thiếu id";
case RawOrder(var id, var city) ->
    "RawOrder còn lại";
```

Nhánh có guard phải đứng trước nhánh tổng quát. Viết ngược:

```java
// CỐ Ý KHÔNG BIÊN DỊCH: case có guard bị dominated.
case RawOrder(var id, var city) -> "Mọi RawOrder";
case RawOrder(var id, var city) when id == null -> "Thiếu id";
```

Nhánh `RawOrder(...)` đầu tiên bao phủ mọi giá trị RawOrder không-null, nên nhánh sau không còn cơ hội được chọn.

Nếu `switch` nhận một **sealed type**, các type pattern bao phủ đủ permitted subclasses có thể làm `switch expression` exhaustive mà không cần `default`. Tuy nhiên:
- Các guard tùy ý không thay được nhánh tổng quát khi vẫn có giá trị cùng kiểu không thỏa guard.
- Xử lý null của selector là chính sách riêng.
- Một `default` quá rộng có thể che việc thiếu xử lý một subtype mới khi sealed hierarchy thay đổi.

Đặc biệt, đừng cố xử lý component null bằng `when` nếu **nested record pattern đã thất bại ở tầng đó**. Để bắt component null, deconstruct ở tầng nông hơn bằng `var` rồi kiểm tra.

## 12. Trường hợp null trong collection và generic domain types

### 12.1. `List.copyOf` không chấp nhận phần tử null

```java
record OrderLines(java.util.List<String> lines) {
    OrderLines {
        lines = java.util.List.copyOf(
            java.util.Objects.requireNonNull(lines, "lines"));
    }
}
```

`List.copyOf` tạo danh sách không cho sửa và từ chối phần tử null. Nó bảo vệ **cấu trúc danh sách**, không biến các phần tử mutable thành immutable. Vì vậy khi thiết kế null contract cho collection, cần quyết định: collection có được null không, phần tử có được null không, rỗng có hợp lệ không, phần tử mutable có được chia sẻ không?

### 12.2. `Map.get` không phân biệt thiếu key với mapped null

```java
String value = map.get(key);
if (value == null) {
    // Có thể không có key, hoặc key tồn tại với mapped value null.
}
```

Với loại `Map` cho phép null values, dùng `containsKey` nếu cần phân biệt hai trường hợp. Với loại map không cho null (như một số unmodifiable maps), contract thay đổi. Đừng cho rằng null trả về từ API luôn mang một nghĩa duy nhất.

### 12.3. Không nhầm non-null type với kiểm tra runtime

Java không áp dụng một hệ non-null type checking thống nhất cho mọi reference chỉ vì field ghi kiểu `String`. Annotation như `@NonNull` hoặc `@Nullable` có thể giúp tooling/IDE/static analyzer, nhưng tên annotation, độ bao phủ và việc runtime có kiểm tra hay không phụ thuộc thư viện/công cụ đang dùng. Với invariant quan trọng, xác thực ở constructor/factory và test hành vi thực tế.

## 13. Quy trình review một null contract

Khi review một domain type và các pattern sử dụng nó:

1. **Liệt kê component** và đánh dấu: bắt buộc, có thể thiếu, hoặc nên là biến thể type riêng.
2. **Định nghĩa vắng mặt:** null nghĩa là chưa biết, không áp dụng, chưa nhập, hay lỗi? Nếu nhiều ý nghĩa, null có thể quá mơ hồ.
3. **Kiểm tra constructor/factory:** null có bị từ chối ở đúng thời điểm không; giá trị non-null có hợp lệ không; có chuẩn hóa tùy tiện không?
4. **Xem boundary:** DTO thô có thể nhận null, nhưng có bước chuyển/validate trước khi tạo domain object không?
5. **Xem pattern:** record pattern ở mỗi tầng có thể fail vì null ở component nào; `var` nào giữ được null?
6. **Xem guard:** null-safe, short-circuit, không gọi phương thức trên biến nullable trước khi kiểm tra?
7. **Xem selector switch:** null có được xử lý tường minh, và default/exhaustiveness có đúng hợp đồng?
8. **Xem kết quả lỗi:** throw exception, return `Optional` hoặc domain `Result`; caller có thể phân biệt các tình huống quan trọng không?
9. **Kiểm thử** các trường hợp null, blank, dữ liệu đúng, giá trị biên, thiếu biến thể, và failure của nested patterns.
10. **Đọc lại API:** người sử dụng có thể suy luận được contract chỉ bằng kiểu, tên và tài liệu mà không phải lần tới mọi chỗ gọi không?

Với hệ thống thật, nên kiểm tra thêm serialization, ORM, collection copy, thread-safety và cách công cụ static analysis xử lý annotation. Đây là những vấn đề tích hợp, không được giải quyết chỉ bằng cách thêm `case null`.

## 14. Lỗi thường gặp và hướng sửa

| Sai lầm | Rủi ro | Cách sửa |
| --- | --- | --- |
| Tưởng `record` tự cấm component null | Tạo được domain state vô nghĩa | Compact constructor với validation |
| Cho phép null ở mọi component “để linh hoạt” | Tăng nhánh kiểm tra và tổ hợp trạng thái sai | Phân biệt required vs optional vs variant |
| Dùng null để đại diện nhiều trạng thái khác nhau | Caller không biết ý nghĩa | Dùng enum/sealed variants hoặc result có tên |
| Tưởng `var city` luôn non-null trong record pattern | Gọi `isBlank()` gây NPE | Kiểm tra null trước |
| Tưởng guard null check bắt được nested record null | Pattern con fail trước guard | Dừng deconstruction ở tầng nông hơn |
| Cho rằng `default` tự bắt selector null | Runtime có thể ném NPE | `case null` hoặc từ chối null trước switch |
| Bắt mọi NPE rồi coi là input thiếu | Che bug dereference ngoài ý muốn | Validate ở boundary và constructor |
| Đưa `Optional` vào mọi field không cân nhắc | API/framework khó xử lý; Optional reference vẫn có thể null | Chọn return type/variant theo contract |
| Tưởng final field bảo đảm deep immutability | Collection/object con có thể mutate | Defensive copy và immutable components |
| Dùng type pattern để thay validation | Pattern chỉ kiểm tra cấu trúc/kiểu | Đặt invariant và chính sách nghiệp vụ đúng tầng |
| Nhánh tổng quát đứng trước guard case | Dominance, case cụ thể không thể tới | Đặt guard case trước |
| Exception message chứa dữ liệu nhạy cảm | Lộ dữ liệu khi trả lỗi cho caller | Lọc thông tin lỗi ở API boundary |

## 15. Bài tập thực hành

**Bài 1 — Thiết kế required field.** Viết `record ProductCode(String value)` từ chối null, chuỗi blank và chuẩn hóa khoảng trắng. Dự đoán exception cho `new ProductCode(null)` và `new ProductCode("  ")`.

**Bài 2 — Null ở các tầng.** Với `Customer(RawAddress(var city))`, hãy giải thích sự khác biệt giữa `Customer(null)` và `Customer(new RawAddress(null))`. Đáp án: trường hợp đầu **không khớp nested pattern**; trường hợp sau **khớp và `city == null`**.

**Bài 3 — Raw DTO.** Chạy `DomainNullContractDemo.java`, bổ sung `new RawOrder(null, null)`. Dự đoán nhánh được chọn. Đáp án: **`Raw: thiếu khách`** vì guard id đứng trước. Nếu cần báo cả hai lỗi, thay cơ chế trả chuỗi bằng tập validation errors.

**Bài 4 — Sealed variant.** Thêm `record Locker(String lockerCode) implements Destination`, validate code không-null/blank, cập nhật `permits` và thêm case tương ứng trong `route`. Giải thích vì sao loại mới tốt hơn quy ước `destination == null` nghĩa là nhận tại tủ.

**Bài 5 — Constructor fail fast.** Viết test cho `new ShipTo(null)`, `new CollectAt(" ")`, `new Order(customerId, null, 100)` và `new Order(customerId, destination, 0)`. Phân biệt NPE và IllegalArgumentException theo hợp đồng demo.

**Bài 6 — Guard và null-safety.** So sánh `city != null && !city.isBlank()` với `city == null || city.isBlank()`. Vì sao cả hai an toàn nhờ short-circuit, nhưng diễn đạt ý nghĩa đối lập?

**Bài 7 — Thay đổi contract có kiểm chứng.** Giả sử địa chỉ giao hàng có thể tạm thiếu ở trạng thái Draft. Bạn sẽ sửa `ShipTo` để nhận null, tạo biến thể `PendingAddress`, hay tách `DraftOrder` và `ConfirmedOrder`? Giải thích ảnh hưởng tới invariant, flow xử lý và pattern matching.

## 16. Tổng kết

**Thiết kế null contract của domain type phải đi trước việc viết pattern matching.** Một component không-null được bảo vệ ở constructor làm giảm nhu cầu guard lặp lại. Một sự vắng mặt có ý nghĩa nghiệp vụ nên được biểu diễn rõ, bằng nullable contract được tài liệu hóa, `Optional` tại API phù hợp, hoặc biến thể sealed type khi trạng thái có hành vi riêng.

Ghi nhớ:
- `record` giúp biểu diễn dữ liệu nhưng **không tự cấm null** và không tự tạo deep immutability.
- `Objects.requireNonNull` thường phù hợp cho required references; validation khác bảo vệ miền của giá trị non-null.
- `var` trong record pattern có thể giữ component null; **record pattern lồng yêu cầu record con không-null**.
- `case null` diễn đạt chính sách của selector `switch`; `when` chỉ được xét sau khi pattern đã khớp.
- Phân biệt **constructor từ chối**, **pattern không khớp**, **guard false** và **runtime NPE**.
- Tách rõ **raw input → validation → domain object**; không để null mơ hồ lan khắp domain.

### Tài liệu tham khảo

- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String))
- [Java SE 21 — Optional](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Optional.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
