# Tổng kết deconstruction trong domain — Case study record với Java Pattern Matching

Trong một domain model, dữ liệu có cấu trúc thường được biểu diễn bằng nhiều **record** nhỏ: địa chỉ chứa thành phố và quốc gia, khách hàng có địa chỉ giao hàng, đơn hàng chứa khách hàng và tổng tiền. **Record deconstruction** cho phép kiểm tra một đối tượng có đúng hình dạng record cần dùng, đồng thời trích các component ra thành biến có kiểu rõ ràng. Từ **Java 21**, ta có thể viết record patterns như `Customer(var id, Address(var city, var country))` trong `instanceof` hoặc `switch`.

Tuy nhiên, **biết cách viết nested record pattern chưa đủ để có domain model tốt**. Điều cần quyết định là: một dữ liệu có thể còn thiếu trường nào, invariant đặt ở đâu, khi nào dùng pattern để phân loại, khi nào giữ nguyên object và gọi phương thức mang ý nghĩa domain, và khi nào nên tách việc xác thực input khỏi domain đã hợp lệ.

Bài thuộc **Java Core Pattern Matching → Case study record**, với chủ đề **Tổng kết deconstruction trong domain**. Ta dùng một case study xử lý yêu cầu tạo/hủy đơn hàng, gồm dữ liệu nháp `DraftOrder`, record `Customer`, `Address`, `Money` và sealed hierarchy `OrderAction`. Ví dụ cho thấy cách kết hợp record patterns, nested patterns, guards, fallback, exhaustive `switch` và validation **mà không biến pattern matching thành một framework nghiệp vụ tự động**.

**Phiên bản:** Records ổn định từ Java 16 (JEP 395), sealed classes/interfaces từ Java 17 (JEP 409), record patterns và pattern matching for `switch` ổn định từ **Java 21** (JEP 440, JEP 441). Hai chương trình độc lập bên dưới được viết cho **Java 21+**, không cần bật preview.

## 1. Deconstruction là gì trong ngữ cảnh domain?

Với khai báo:

~~~java
// Trích đoạn Java 21+: record trong cùng phạm vi thích hợp.
record Address(String city, String country) {}
record Customer(String id, Address deliveryAddress) {}
~~~

Một **type pattern** chỉ kiểm tra loại và ràng buộc nguyên đối tượng:

~~~java
// Trích đoạn: input có kiểu Object.
if (input instanceof Customer customer) {
    System.out.println(customer.id());
}
~~~

Một **record pattern** vừa kiểm tra record, vừa ràng buộc các component theo đúng thứ tự:

~~~java
if (input instanceof Customer(var customerId, var address)) {
    System.out.println(customerId + ": " + address);
}
~~~

Và một **nested record pattern** đi sâu thêm:

~~~java
if (input instanceof Customer(
        var customerId,
        Address(var city, var country))) {
    System.out.println(customerId + " -> " + city + "/" + country);
}
~~~

Trong cách viết cuối:

1. `input` phải là một `Customer` phù hợp.
2. Record pattern đọc component thứ nhất `id` vào biến `customerId`.
3. Component thứ hai `deliveryAddress` phải khớp một `Address` khác `null`.
4. Nếu khớp, pattern tiếp tục lấy `city` và `country`.
5. Nếu component `deliveryAddress` là `null`, **nested `Address(...)` không match**; nhánh `if` không chạy.

Đây là **pattern matching trên hình dạng dữ liệu và giá trị component**. Nó không tự kiểm tra rằng địa chỉ giao hàng được khách hàng xác nhận, khách hàng có quyền thanh toán, hay mã đơn hàng được lưu trong database.

### Mô hình dễ nhớ: tổng và tích

Một record như `Address(String city, String country)` đại diện cho **product type**: một giá trị chứa đồng thời các thành phần được khai báo. Một sealed hierarchy có các subtype `Submit` hoặc `Cancel` mô tả **sum type** gần với tư duy “một trong các biến thể được phép”.

~~~text
OrderAction
    |
    +-- Submit(DraftOrder)
    |        |
    |        +-- orderId
    |        +-- Customer(id, Address(city, country))
    |        +-- Money(currency, cents)
    |
    +-- Cancel(orderId, reason)
~~~

Pattern `Submit(DraftOrder(...))` kiểm tra **biến thể hành động**, rồi record pattern lồng nhau đọc **các thành phần dữ liệu** của biến thể. Đây là cách phối hợp rất tự nhiên khi domain có tập hành động đóng và payload khác nhau.

Không cần sử dụng thuật ngữ “sum/product type” trong mọi API Java; mô hình tư duy này chỉ giúp tách **chọn biến thể** khỏi **trích cấu trúc**.

## 2. Vì sao mô hình record riêng tốt hơn “một record mọi trường”?

Giả sử dịch vụ nhận hai yêu cầu: tạo đơn và hủy đơn. Một thiết kế yếu có thể là:

~~~java
// MINH HỌA ANTI-PATTERN, không khuyến nghị cho domain nội bộ.
record RequestData(
    String kind,
    String orderId,
    String customerId,
    String city,
    String country,
    Long amountCents,
    String cancelReason
) {}
~~~

Mô hình này cho phép:

- `kind = "CANCEL"` nhưng lại có `amountCents` và `city`.
- `kind = "SUBMIT"` nhưng thiếu `customerId`.
- Chuỗi `kind` sai chính tả hoặc không được hỗ trợ.
- `amountCents` là `null` trong khi logic muốn một giá trị nguyên thủy.
- Nhiều field nullable mà code phải liên tục suy đoán field nào hợp lệ trong từng trạng thái.

Thay vì một payload chứa mọi thứ, ta dùng các record theo đúng ý nghĩa:

~~~java
// Trích đoạn Java 21+, trong cùng phạm vi sealed hierarchy phù hợp.
sealed interface OrderAction permits Submit, Cancel {}
record Submit(DraftOrder draft) implements OrderAction {}
record Cancel(String orderId, String reason) implements OrderAction {}
~~~

Khi xử lý `Submit`, compiler biết payload là `DraftOrder`; với `Cancel`, compiler biết có `orderId` và `reason`. Phân nhánh không phải so sánh `String kind` rồi ép kiểu payload ở runtime.

**Nhưng sealed/record không thay thế validation dữ liệu.** Người gọi vẫn có thể tạo `new Cancel(null, null)` nếu constructor không chặn; và `new Submit(null)` cũng hợp lệ ở mức type khi component tham chiếu không được kiểm tra. Trước khi đưa yêu cầu vào nghiệp vụ thật, cần xác định mức tin cậy và validate giá trị.

## 3. Phân biệt dữ liệu nháp và domain đã hợp lệ

Trong case study, ta cố ý dùng tên `DraftOrder` cho dữ liệu **có thể chưa hoàn chỉnh**:

~~~java
record DraftOrder(String orderId, Customer customer, Money total) {}
~~~

Chữ “Draft” nói rõ đây là dữ liệu đang được thu thập hoặc chuẩn hóa; nó có thể thiếu `customer`, `total` hoặc một component khác. Tại ranh giới của hệ thống, ta thường gặp DTO từ HTTP/JSON, message broker hay import dữ liệu cũ với mức tin cậy khác nhau.

Ngược lại, một **domain object đã xác nhận hợp lệ** nên có contract rõ ràng hơn:

~~~java
// Trích đoạn trong class có các kiểu và helper cùng phạm vi.
record ConfirmedOrder(
        String orderId, Customer customer, Money total) {
    ConfirmedOrder {
        requireText(orderId, "orderId");
        java.util.Objects.requireNonNull(customer, "customer");
        java.util.Objects.requireNonNull(
                customer.deliveryAddress(), "deliveryAddress");
        java.util.Objects.requireNonNull(total, "total");
    }
}
~~~

Tại đây, compact constructor ngăn phần lớn trạng thái thiếu dữ liệu ở thời điểm tạo đối tượng. Nếu mọi instance `ConfirmedOrder` chỉ được tạo qua contract này, code xử lý có thể dựa vào invariant để đơn giản hóa luồng kiểm tra.

**Giới hạn quan trọng:** Record và pattern không tự chứng minh rằng dữ liệu qua mạng đã được xác thực đầy đủ. Việc decode JSON thành record, kiểm tra quyền truy cập, trạng thái đơn, đơn vị tiền tệ, inventory và transaction vẫn là trách nhiệm riêng của boundary/service.

### Quy tắc thực dụng

- **Boundary/draft:** có thể còn thiếu component; dùng deconstruction + fallback hoặc validation result để chỉ rõ trường hợp không hoàn chỉnh.
- **Validated domain:** constructor/factory đã bảo đảm invariant; không cần lặp lại các null checks ở mọi phép toán nếu contract thật sự được duy trì.
- **Service nghiệp vụ:** điều phối quyền truy cập, persistence, transaction, I/O và side effect; không nhét hành động này vào `when` hoặc custom accessor.

Tên kiểu nên giúp người đọc biết mức độ tin cậy. Đừng gọi một payload còn thiếu nhiều trường là `ConfirmedOrder` chỉ vì record tự động sinh constructor.

## 4. Ví dụ ngắn: nested pattern và component `null`

Trước khi đi vào case study lớn, hãy xác nhận một quy tắc thường gây nhầm lẫn. Tạo tệp **`RecordDeconstructionQuickDemo.java`**:

~~~java
public class RecordDeconstructionQuickDemo {
    record Location(String city) {}
    record Delivery(Location location) {}

    static String route(Object input) {
        return switch (input) {
            case Delivery(Location(var city)) -> "Send to " + city;
            case Delivery(var location) -> "No location";
            case null -> "Missing input";
            default -> "Not a delivery";
        };
    }

    public static void main(String[] args) {
        System.out.println(route(new Delivery(new Location("Hue"))));
        System.out.println(route(new Delivery(null)));
        System.out.println(route(null));
        System.out.println(route("Other"));
    }
}
~~~

Chạy bằng JDK 21+:

~~~bash
javac --release 21 -encoding UTF-8 RecordDeconstructionQuickDemo.java
java RecordDeconstructionQuickDemo
~~~

Đầu ra:

~~~text
Send to Hue
No location
Missing input
Not a delivery
~~~

Phân tích chính xác bốn trường hợp:

1. `new Delivery(new Location("Hue"))` khớp cả `Delivery(...)` và nested `Location(...)`; `city = "Hue"`.
2. `new Delivery(null)` **không khớp nested record pattern** `Location(var city)`, nhưng **khớp `Delivery(var location)`**; biến `location` nhận `null`. Kết quả `"No location"`.
3. Selector bằng `null` được `case null` xử lý; nó **không** biến thành `Delivery(null)`.
4. Giá trị kiểu `String` không phải `Delivery` nên tới `default`.

**Ba loại “null” cần phân biệt:** selector null; một record object khác null nhưng component null; và một component rỗng như `new Location("")`. Record pattern phân biệt hình dạng/kiểu chứ không tự biến chuỗi rỗng thành null. Muốn cấm city rỗng, phải validate hoặc dùng guard phù hợp.

## 5. Thiết kế case study đơn hàng trước khi deconstruct

Ta sử dụng những record có vai trò rõ ràng:

| Kiểu | Vai trò | Contract trong ví dụ |
| --- | --- | --- |
| `Address(city, country)` | Địa chỉ giao hàng | `city`/`country` không được null hoặc trắng |
| `Customer(id, deliveryAddress)` | Khách hàng và địa chỉ dự kiến | `id` phải có nội dung; `deliveryAddress` có thể null khi bản nháp chưa chọn nơi giao |
| `Money(currency, cents)` | Số tiền bằng đơn vị nhỏ nhất | `currency` có nội dung; `cents` không âm |
| `DraftOrder(orderId, customer, total)` | Dữ liệu đơn hàng chưa xác thực đầy đủ | Component có thể thiếu để minh họa fallback |
| `Submit(draft)` | Yêu cầu gửi đơn | Một biến thể của `OrderAction` |
| `Cancel(orderId, reason)` | Yêu cầu hủy | Biến thể còn lại |
| `OrderAction` | Tập hành động đóng | `sealed interface` chỉ cho phép hai biến thể trong ví dụ |

**Vì sao dùng `Money(currency, cents)` thay vì `double amount`?** Số nguyên đơn vị nhỏ nhất giúp tránh một nhóm vấn đề làm tròn của floating point trong tiền tệ. Tuy nhiên, bản mẫu chưa kiểm tra currency code ISO, số chữ số thập phân của từng đơn vị tiền hay overflow ở phép cộng; hệ thống thanh toán thật cần thiết kế những invariant này.

**Vì sao `Customer.deliveryAddress` có thể null?** Domain mẫu có bước nháp và một khách hàng có thể chưa chọn địa chỉ giao hàng. Nếu hệ thống của bạn yêu cầu một `Customer` luôn có địa chỉ, hãy đổi contract: bắt buộc non-null trong constructor hoặc tách `CustomerProfile` khỏi `DeliveryDetails`. Thiết kế null ở đây là **lựa chọn có chủ đích để dạy deconstruction**, không phải quy tắc chung cho mọi khách hàng.

**Vì sao gọi là `Submit` và `Cancel` thay vì `OrderSubmitted` và `OrderCancelled`?** Hai kiểu này là **command/yêu cầu** cần kiểm tra, không phải domain event xác nhận một việc đã xảy ra. Khi đã có kết quả, tầng ứng dụng mới có thể phát event thích hợp theo quy tắc hệ thống.

## 6. Chương trình hoàn chỉnh Java 21+: domain deconstruction có fallback

Tạo tệp **`DomainDeconstructionDemo.java`**:

~~~java
public class DomainDeconstructionDemo {
    sealed interface OrderAction permits Submit, Cancel {}

    record Address(String city, String country) {
        Address {
            requireText(city, "city");
            requireText(country, "country");
        }
    }

    record Customer(String id, Address deliveryAddress) {
        Customer {
            requireText(id, "customerId");
        }
    }

    record Money(String currency, long cents) {
        Money {
            requireText(currency, "currency");
            if (cents < 0) {
                throw new IllegalArgumentException("cents must be non-negative");
            }
        }
    }

    record DraftOrder(String orderId, Customer customer, Money total) {}

    record Submit(DraftOrder draft) implements OrderAction {}
    record Cancel(String orderId, String reason) implements OrderAction {}

    static void requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must be nonblank");
        }
    }

    static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    static String describe(OrderAction action) {
        return switch (action) {
            case Submit(DraftOrder(var orderId,
                    Customer(var customerId, Address(var city, var country)),
                    Money(var currency, var cents)))
                    when hasText(orderId) && cents >= 10_000 ->
                    "Review " + orderId + " for " + customerId
                            + " to " + city + "/" + country
                            + ": " + cents + " " + currency;

            case Submit(DraftOrder(var orderId,
                    Customer(var customerId, Address(var city, var country)),
                    Money(var currency, var cents)))
                    when hasText(orderId) ->
                    "Ready " + orderId + " for " + customerId
                            + " to " + city + "/" + country
                            + ": " + cents + " " + currency;

            case Submit(var draft) -> "Incomplete submit";

            case Cancel(var id, var reason)
                    when hasText(id) && hasText(reason) ->
                    "Cancel " + id + ": " + reason;

            case Cancel(var id, var reason) -> "Invalid cancellation";

            case null -> "Missing action";
        };
    }

    static String describeExplicit(DraftOrder draft) {
        if (draft == null || !hasText(draft.orderId())) {
            return "Incomplete submit";
        }

        Customer customer = draft.customer();
        Money total = draft.total();
        if (customer == null || customer.deliveryAddress() == null
                || total == null) {
            return "Incomplete submit";
        }

        Address address = customer.deliveryAddress();
        String prefix = total.cents() >= 10_000 ? "Review " : "Ready ";
        return prefix + draft.orderId() + " for " + customer.id()
                + " to " + address.city() + "/" + address.country()
                + ": " + total.cents() + " " + total.currency();
    }

    public static void main(String[] args) {
        Submit[] samples = {
            new Submit(new DraftOrder("O-100",
                    new Customer("C-7", new Address("Hue", "VN")),
                    new Money("VND", 12_500))),
            new Submit(new DraftOrder("O-101",
                    new Customer("C-8", new Address("Hanoi", "VN")),
                    new Money("VND", 500))),
            new Submit(new DraftOrder("O-102",
                    new Customer("C-9", null), new Money("VND", 800))),
            new Submit(new DraftOrder("O-103", null, new Money("VND", 800))),
            new Submit(new DraftOrder("  ",
                    new Customer("C-4", new Address("Da Nang", "VN")),
                    new Money("VND", 800))),
            new Submit(null)
        };

        for (Submit submit : samples) {
            String viaPattern = describe(submit);
            String viaAccessors = describeExplicit(submit.draft());
            System.out.println(viaPattern + " | equal="
                    + viaPattern.equals(viaAccessors));
        }

        System.out.println(describe(
                new Cancel("O-100", "Customer requested")));
        System.out.println(describe(new Cancel("O-100", "  ")));
        System.out.println(describe(null));

        try {
            new Money("VND", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid money: " + ex.getMessage());
        }

        try {
            new Address("", "VN");
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid address: " + ex.getMessage());
        }
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac --release 21 -encoding UTF-8 DomainDeconstructionDemo.java
java DomainDeconstructionDemo
~~~

Đầu ra chính xác:

~~~text
Review O-100 for C-7 to Hue/VN: 12500 VND | equal=true
Ready O-101 for C-8 to Hanoi/VN: 500 VND | equal=true
Incomplete submit | equal=true
Incomplete submit | equal=true
Incomplete submit | equal=true
Incomplete submit | equal=true
Cancel O-100: Customer requested
Invalid cancellation
Missing action
Invalid money: cents must be non-negative
Invalid address: city must be nonblank
~~~

### Những gì chương trình minh họa

**6.1. Trường hợp dữ liệu đầy đủ, cần kiểm tra thêm ngưỡng tiền**

`Submit(DraftOrder(... Customer(... Address(...)), Money(...)))` vừa chọn biến thể `Submit` vừa kiểm tra các tầng dữ liệu. Khi hình dạng phù hợp và `orderId` có nội dung, `when cents >= 10_000` phân loại đơn vào nhóm cần review. Nhánh thường tiếp theo áp dụng cho trường hợp cùng hình dạng và orderId hợp lệ nhưng số tiền nhỏ hơn.

**6.2. Nested pattern có thể thất bại vì component null**

`DraftOrder("O-102", Customer("C-9", null), Money(...))` không khớp `Address(var city, var country)`. `DraftOrder("O-103", null, Money(...))` còn không khớp nested `Customer(...)`. Cả hai được nhánh `case Submit(var draft)` xử lý.

**6.3. Fallback cũng xử lý dữ liệu nháp chưa hợp lệ**

`DraftOrder("  ", Customer(...), Money(...))` khớp cấu trúc nhưng không qua guard `hasText(orderId)`, vì vậy không vào hai nhánh đầu. `Submit(null)` không khớp nested `DraftOrder(...)`, nhưng vẫn khớp `Submit(var draft)`. Kết quả đều là `"Incomplete submit"`.

**6.4. Type pattern và record pattern không tự xác nhận nghiệp vụ**

`Cancel("O-100", "Customer requested")` đi vào nhánh guard đúng; `Cancel("O-100", "  ")` có reason toàn khoảng trắng, guard sai và đi tới nhánh `"Invalid cancellation"`. Những phép kiểm tra này **không kiểm chứng rằng đơn O-100 thực sự tồn tại hay được phép hủy**.

**6.5. Constructor validation khác với việc match**

`new Money("VND", -1)` và `new Address("", "VN")` bị compact constructor từ chối **trước khi** có bất kỳ deconstruction nào. Record pattern không có nhiệm vụ chặn việc tạo domain data sai — invariant nên nằm ở contract của việc xây dựng object hoặc bước chuyển đổi từ DTO.

**6.6. So sánh `describe` với `describeExplicit`**

Sáu đầu vào `Submit` đều có hậu tố `equal=true`: kết quả của nested pattern trùng với kết quả các bước truy cập accessor trong những trường hợp được kiểm thử. Đây là **kiểm thử tương đương hành vi trên tập mẫu**, không chứng minh hai cách luôn tương đương khi custom accessor có side effect hoặc khi logic thay đổi.

**6.7. `null` của selector không phải component null**

`describe(null)` chọn `case null` và trả `"Missing action"`. Nó khác `describe(new Submit(null))`, vốn được xem là một `Submit` chứa dữ liệu nháp thiếu.

**6.8. Tính exhaustive được giữ**

`OrderAction` là sealed interface chỉ có `Submit` và `Cancel` trong ví dụ; switch có các nhánh không guard cho từng biến thể cùng `case null`. Vì thế `switch expression` không cần `default`. Nếu sau này bổ sung `UpdateAddress` vào hierarchy, khi biên dịch lại cần xem xét case mới.

### Đây là mô hình minh họa, không phải service nhận đơn production

Phương thức `describe` chỉ **phân loại và tạo chuỗi mô tả**. Nó không lưu đơn, thu tiền, trừ hàng, kiểm tra người sở hữu, kiểm tra trạng thái hay phát event. Ngưỡng `10_000` được chọn để dễ đọc, **không phải quy tắc tiền tệ chuẩn**. Tại hệ thống thực tế, quyết định và side effect cần được đặt trong application service có contract rõ ràng.

## 7. Cách đọc nested pattern mà không nhầm thứ tự component

Record pattern dùng **thứ tự khai báo trong record**, không dùng tên biến để dò component:

~~~java
record Address(String city, String country) {}
~~~

Với một `Address("Hue", "VN")`:

~~~java
// Trích đoạn Java 21+, input có kiểu Object.
if (input instanceof Address(var city, var country)) {
    System.out.println(city + "/" + country);
}
~~~

`city` nhận `"Hue"`, `country` nhận `"VN"`. Nhưng:

~~~java
if (input instanceof Address(var country, var city)) {
    // HỢP LỆ VỀ CÚ PHÁP nhưng tên biến gây hiểu nhầm:
    // country thực tế nhận "Hue"; city thực tế nhận "VN".
}
~~~

Lỗi này **không nhất thiết bị compiler phát hiện** vì cả hai component đều cùng kiểu `String`. Vì vậy:

- Đọc chữ ký record trước khi viết pattern.
- Dùng tên local variable theo đúng ý nghĩa component.
- Tránh deconstruct quá nhiều component cùng kiểu khi chúng khó phân biệt bằng mắt.
- Nếu việc đặt nhầm tên có rủi ro lớn, **gọi accessor tường minh** như `address.city()` và `address.country()` có thể an toàn hơn cho người bảo trì.

**Không dùng record pattern như lời gọi constructor.** Cú pháp `Address(var city, var country)` ở `case` là pattern để match một giá trị đã tồn tại, không tạo `new Address(...)`.

## 8. Khi nào deconstruction quá sâu trở thành vấn đề?

Nhánh đầu trong `describe` vừa phải đọc subtype, order draft, customer, address, money và guard:

~~~java
// Trích đoạn từ ví dụ chính, rút bớt phần thân.
case Submit(DraftOrder(var orderId,
        Customer(var customerId, Address(var city, var country)),
        Money(var currency, var cents)))
        when hasText(orderId) && cents >= 10_000 ->
        /* mô tả đơn cần review */;
~~~

Nó hữu ích khi mục tiêu là **xác nhận toàn bộ cấu trúc phải đủ để đi tiếp**. Nhưng khi logic trở nên phức tạp hơn, nested pattern nhiều tầng có thể:

- Khiến tên component khó đối chiếu với record declaration.
- Gộp nhiều lý do không hợp lệ thành “không khớp”.
- Làm thay đổi chính sách lỗi khi chỉ đổi thứ tự các case.
- Khiến cùng cấu trúc pattern bị lặp ở nhiều nhánh có guard khác nhau.
- Làm code phụ thuộc mạnh hơn vào thứ tự và số lượng component của record.
- Khó bảo trì khi thêm field mới hoặc thay cấu trúc domain.
- Gây khó khăn nếu custom accessor không thuần túy hoặc đắt.

### Tách thành bước có tên khi cần lý do lỗi cụ thể

Ví dụ `describeExplicit` dùng:

~~~java
// Trích đoạn trong phương thức trả String, DraftOrder draft đã có.
if (draft == null || !hasText(draft.orderId())) {
    return "Incomplete submit";
}
Customer customer = draft.customer();
Money total = draft.total();
if (customer == null || total == null) {
    return "Incomplete submit";
}
Address address = customer.deliveryAddress();
if (address == null) {
    return "Incomplete submit";
}
~~~

Khi nghiệp vụ cần nhiều mã lỗi, có thể biến từng đường kiểm tra thành `ValidationResult` hoặc enum như `MISSING_CUSTOMER`, `MISSING_ADDRESS`, `INVALID_ORDER_ID` thay vì mọi nhánh đều trả `"Incomplete"`.

**Không bắt buộc chuyển hết sang `if`.** Có thể kết hợp: dùng `switch` ở tầng `OrderAction` để chọn loại command, sau đó gọi `validateDraft(draft)` cho nghiệp vụ có nhiều bước. Chọn pattern ở nơi nó biểu diễn một cấu trúc rõ ràng, không cố đặt toàn bộ quy trình trong một case.

## 9. Guard `when`: phân loại, không điều phối side effect

Trong ví dụ, các guard:

~~~java
when hasText(orderId) && cents >= 10_000
when hasText(orderId)
when hasText(id) && hasText(reason)
~~~

đều chỉ đọc giá trị và trả `boolean`. Đây là công việc phù hợp với guard. Các phương thức `hasText` cũng thuần túy, không ghi dữ liệu và không gọi dịch vụ ngoài.

Một anti-pattern có thể trông như:

~~~java
// CỐ Ý MINH HỌA THIẾT KẾ XẤU, không phải source độc lập.
case Submit(var draft) when paymentGateway.charge(draft) ->
        "Accepted";
~~~

Nếu `charge` thực hiện giao dịch, side effect có thể xảy ra ngay **trong lúc chọn case**, kể cả khi trả `false` và Java tiếp tục xét nhánh sau. `switch` không tự rollback giao dịch đã chạy.

**Hướng tốt hơn:** deconstruct để lấy dữ liệu, validate, tạo một decision/value object thuần túy; rồi trong application service thực hiện lưu/thu tiền/audit với transaction, idempotency và xử lý lỗi phù hợp.

### Một guard dài không phải lúc nào cũng dễ đọc hơn helper

Khi có nhiều điều kiện như trạng thái đơn, quyền truy cập, hạn mức, tồn kho hoặc phiên bản dữ liệu, một chuỗi `when a && b && c && d` có thể che lý do từ chối. Hãy cân nhắc một hàm `validate(...)` trả kết quả có cấu trúc và test riêng. Không nên biến mọi điều kiện nghiệp vụ thành một case Boolean.

## 10. Dominance và thứ tự case trong domain

Phân loại từ **trường hợp chuyên biệt tới tổng quát**:

~~~java
// Java 21+, trích đoạn trong switch trên OrderAction.
case Submit(DraftOrder(var id, var customer, var total))
        when hasText(id) -> "Ready";
case Submit(var draft) -> "Incomplete";
~~~

Nếu đặt `case Submit(var draft)` lên trước, nó bao phủ mọi `Submit` nên nhánh cụ thể phía sau bị **dominated** theo những quy tắc Java áp dụng. Compiler giúp phát hiện một số dạng nhánh bị che.

Tương tự, trong chương trình chính:

1. `Submit(... nested ...) when cents >= 10_000` trước.
2. `Submit(... nested ...) when hasText(orderId)` sau.
3. `Submit(var draft)` không guard ở cuối của nhóm `Submit`.

Điều kiện ở nhánh đầu cũng cần `hasText(orderId)` để tránh phân loại draft có mã đơn rỗng là đơn cần review. **Compiler không tự chứng minh mọi quan hệ Boolean phức tạp giữa guard**; thứ tự phân loại và các giá trị biên vẫn phải được kiểm thử.

### Nhánh không guard đóng vai trò gì?

Nhánh `case Submit(var draft)` nhận những `Submit` không thỏa nhánh trước: thiếu draft, thiếu customer, thiếu address, thiếu money hoặc orderId không hợp lệ. Nó làm việc phân loại trở nên toàn diện về kiểu, nhưng không giải thích chi tiết **vì sao** không hợp lệ.

Chọn fallback tổng quát chỉ khi hợp đồng không yêu cầu phân biệt từng lý do; nếu không, nên dùng validation result hoặc những nhánh rõ ý nghĩa hơn.

## 11. Exhaustiveness giúp domain model tiến hóa có kiểm soát

Sealed hierarchy đóng cho phép compiler biết danh sách subtype trực tiếp được phép. Với:

~~~java
sealed interface OrderAction permits Submit, Cancel {}
record Submit(DraftOrder draft) implements OrderAction {}
record Cancel(String orderId, String reason) implements OrderAction {}
~~~

một `switch expression` có các nhánh xử lý `Submit` và `Cancel` đầy đủ có thể không cần `default`. Khi thêm `RescheduleDelivery`, code đang phân loại theo `OrderAction` phải được xem xét lại.

~~~java
// MINH HỌA thay đổi, không phải tệp chạy độc lập.
sealed interface OrderAction
        permits Submit, Cancel, RescheduleDelivery {}

record RescheduleDelivery(String orderId, Address address)
        implements OrderAction {}
~~~

**Điểm mạnh:** các `switch expression` exhaustive chưa có nhánh mới có thể báo lỗi compile-time khi biên dịch lại, nhắc tác giả code quyết định cách xử lý hành động mới. Một `default -> "Other"` quá rộng sẽ che tín hiệu đó.

**Giới hạn:** nếu module có branch `non-sealed`, tập subtype có thể mở và khả năng exhaustive thay đổi theo thiết kế. Không nên cho rằng mọi interface được gắn `sealed` đều tự động đảm bảo mọi branch cụ thể không cần fallback trong mọi cấu trúc mở rộng.

### `null` không phải permitted subtype

`null` không đại diện cho một biến thể trong danh sách `permits`. Trong demo, `case null` là chính sách nhận `null` và trả `"Missing action"`. Một lựa chọn khác là `Objects.requireNonNull(action)` để từ chối đầu vào này trước `switch`. Điều quan trọng là **chọn chính sách rõ ràng**.

## 12. Deconstruction và khả năng tiến hóa API

Các record patterns phụ thuộc vào **hình dạng record tại compile time**. Xét:

~~~java
record Address(String city, String country) {}
~~~

và pattern:

~~~java
case Address(var city, var country) -> ...
~~~

Nếu sau này `Address` đổi thành:

~~~java
// MINH HỌA phiên bản schema mới, không khai báo cùng lúc với bản cũ.
record Address(String city, String region, String country) {}
~~~

record pattern hai component không còn đúng số lượng; nơi sử dụng pattern cần được sửa và biên dịch lại. Đây là **coupling có chủ đích với hình dạng dữ liệu**.

So sánh:

- **Deconstruction:** biểu diễn cấu trúc rõ ràng, rất gọn khi nhiều component cùng cần dùng, nhưng bị ảnh hưởng khi thay số lượng/thứ tự component.
- **Accessor có tên:** `address.city()` có thể tiếp tục hợp lệ khi record thêm một component khác nếu accessor cũ vẫn giữ nguyên.
- **Phương thức domain:** `order.isDeliverable()` diễn đạt một chính sách; implementation có thể thay đổi mà người gọi không phải biết toàn bộ dữ liệu bên trong.

**Thay đổi record components còn ảnh hưởng constructor, serialization và tương thích API**, không chỉ pattern. Đừng “đổi chỗ” hai component cùng kiểu mà không xem xét hậu quả, bởi compiler có thể không phát hiện việc tráo ý nghĩa.

### Đặc biệt cẩn thận tại biên module/public API

Trong module nội bộ, thay record shape và sửa mọi pattern có thể là một bước refactor được kiểm soát. Với public API hoặc message schema lưu trữ, việc đổi shape có thể ảnh hưởng client đã biên dịch, serializer, deserializer và dữ liệu cũ.

Một thiết kế bền vững thường là:
- DTO/schema bên ngoài có versioning rõ.
- Tầng chuyển đổi từ DTO sang domain record đã validate.
- Domain operation dùng những phương thức có ý nghĩa thay vì phụ thuộc mọi component khi không cần.
- Deconstruction được dùng ở những chỗ thực sự cần so khớp hình dạng và có quyền sửa cùng domain model.

## 13. Record patterns có phải một dạng gọi getter không?

Một record component có accessor tương ứng, và **record pattern dùng các accessor** để lấy dữ liệu trích ra. Với record thường có accessor đơn giản, điều này dễ hiểu và JVM có thể tối ưu. Nhưng Java cho phép **custom accessor**:

~~~java
// Trích đoạn Java: minh họa khả năng tự định nghĩa accessor.
record Counter(int value) {
    public int value() {
        System.out.println("accessor invoked");
        return value;
    }
}
~~~

Đây là code hợp lệ, nhưng **không nên** đặt side effect nghiệp vụ trong accessor của domain value object. Nested matching có thể truy cập component để thử pattern rồi tiếp tục thử case dự phòng; không nên viết logic nghiệp vụ phụ thuộc vào việc accessor “chắc chắn chỉ chạy một lần”.

Tương tự, custom accessor có thể ném ngoại lệ; việc ném lỗi không đồng nghĩa pattern không match để tự chuyển sang case sau. Nếu cần truy cập dữ liệu từ mạng, database hoặc tính toán có trạng thái, hãy gọi một service/phương thức rõ ràng **bên ngoài pattern** và xử lý lỗi cụ thể.

### Record bất biến đến mức nào?

Record components là field không thể gán lại sau khi xây dựng (trừ cơ chế bên ngoài ngôn ngữ bình thường), nhưng **không tự làm bất biến sâu** những đối tượng mà nó giữ tham chiếu.

~~~java
// Trích đoạn có ý nghĩa khi danh sách phải được bảo vệ.
record LineItems(java.util.List<String> skuIds) {
    LineItems {
        skuIds = java.util.List.copyOf(skuIds);
    }
}
~~~

`List.copyOf` tạo một danh sách không sửa được qua interface và từ chối `null` theo contract của API; nhưng nếu phần tử là đối tượng mutable, cần thêm chiến lược để có deep immutability khi thật sự cần. Trong demo chính, `Address` và `Money` chỉ dùng `String` và kiểu nguyên thủy, giúp mô hình đơn giản hơn.

## 14. Chọn record pattern hay accessor theo ý nghĩa nghiệp vụ

### Nên dùng record pattern khi

- Cần phân nhánh rõ các biến thể của sealed domain hierarchy.
- Cấu trúc nhỏ hoặc vừa phải, dữ liệu thực sự là value-like record.
- Muốn kiểm tra hình dạng lồng nhau “phải có đủ `Customer → Address`”.
- Cần nhiều component của cùng record để tạo một kết quả ngắn.
- Muốn compiler giúp phát hiện thiếu biến thể trong exhaustive `switch`.
- Code có quyền bảo trì cả record declaration và nơi deconstruct nó.

### Nên dùng accessor hoặc domain method khi

- Chỉ cần một field: `order.id()` thường rõ hơn deconstruct cả `Order`.
- Dữ liệu ở dạng draft, cần **lý do lỗi cụ thể** cho từng component thiếu.
- Nested pattern lặp nhiều tầng, có quá nhiều `var` cùng kiểu.
- Domain model có thể thêm field/reorder components thường xuyên.
- Muốn che cấu trúc nội bộ và giữ public API ổn định.
- Có hành vi giàu ý nghĩa như `order.canBeCancelledBy(user)` mà không nên tái hiện logic ở từng `when`.
- Có accessor tùy biến/side effect, muốn kiểm soát rõ thời điểm đọc.

### Một lựa chọn kết hợp thường tốt

~~~java
// MINH HỌA kiến trúc, không phải source chạy độc lập.
return switch (action) {
    case Submit(var draft) -> submitService.validateAndProcess(draft);
    case Cancel(var id, var reason) -> cancelService.process(id, reason);
    case null -> handleMissingAction();
};
~~~

Ở đây `switch` chọn **biến thể hành động** nhưng không phải gánh toàn bộ validation hoặc workflow. Nếu cần deconstruct `Address` trong hàm format thuần túy, vẫn có thể dùng record pattern ở đó. **Không có quy tắc rằng đã chọn pattern matching thì phải phân rã mọi object tới component nhỏ nhất.**

## 15. Hiệu năng: đừng chọn thiết kế chỉ theo số dòng

Một nested pattern không tự tạo bản sao record mới cho mỗi tầng. Nó thực hiện matching và truy xuất component; JIT có thể inline những accessor đơn giản và tối ưu phần code quan sát được.

Tuy nhiên:
- Một nhánh có nested match thất bại có thể dẫn đến **thử lại pattern khác**.
- Guard chạy **sau khi** phần record pattern của case đã khớp.
- Custom accessor có thể tốn chi phí, bị đọc lại hoặc có side effect.
- Thời gian nối chuỗi, validation, I/O hoặc tính toán nghiệp vụ thường có thể lớn hơn thời gian deconstruction.
- Code ngắn không đồng nghĩa bytecode/chạy máy nhanh hơn.

**Ví dụ `describe` và `describeExplicit` chỉ kiểm chứng kết quả, không đo tốc độ**. Muốn kết luận hiệu năng, nên dùng **JMH**, input dựng ngoài đoạn đo, warmup/forks/measurements, kiểm tra tương đương và nhiều hình dạng dữ liệu; xem profiler để xác định đường hot thật sự.

**Khuyến nghị:** chọn theo rõ ràng và đúng contract trước. Chỉ thay nested pattern bằng accessor thủ công vì mục tiêu hiệu năng nếu đã đo và thấy khác biệt có ý nghĩa trong workload thực.

## 16. Những lỗi thường gặp khi deconstruct domain records

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đặt tên biến trái thứ tự component cùng kiểu | Compiler có thể không phát hiện, dữ liệu bị hiểu sai | So khai báo record; chọn tên đúng hoặc gọi accessor có tên |
| Nghĩ `Customer(var id, Address(...))` khớp address null | Nhánh lồng không match và chuyển fallback | Phân biệt nested type pattern với `var address` |
| Nghĩ record tự validate mọi invariant | `DraftOrder(null, null, null)` vẫn có thể tạo | Constructor/factory/validation theo contract |
| Deconstruct sâu cho mọi xử lý | Coupling vào record shape, khó biết nơi thiếu dữ liệu | Tách validation và dùng domain method khi hợp lý |
| Không có fallback cho dữ liệu draft | Giá trị thiếu cấu trúc không được xử lý như mong muốn | Nhánh tổng quát hoặc validation result |
| Đặt case tổng quát trước case guard | Guard case bị che hoặc compiler báo dominance | Đặt case cụ thể trước |
| Thêm `default` cho sealed `switch` | Che việc thiếu case khi thêm biến thể | Giữ exhaustive cases khi tập biến thể đóng |
| Gọi service có side effect trong `when` | Có thể gây hành động trước khi nhánh được chọn | Guard thuần túy; workflow trong service |
| Dùng deconstruction như đối chiếu hai record bằng `equals` | Hiểu sai mục tiêu của pattern | Dùng `equals` cho value equality; pattern cho kiểm tra kiểu/hình dạng |
| Tạo domain event trước khi nghiệp vụ thực sự xảy ra | Lẫn command với event | Đặt tên yêu cầu và sự kiện rõ ràng |
| Đổi thứ tự record components mà không cập nhật client | Pattern có thể lấy nhầm ý nghĩa, code public API bị ảnh hưởng | Contract/schema review, tests và versioning |
| Coi số lần accessor trong demo là benchmark | Không đo runtime/JIT thực tế | JMH/profiler và input đại diện |
| Dùng generic record pattern khi chưa hiểu kiểu suy luận | Có thể hiểu sai type inference và type erasure | Kiểm tra kiểu tĩnh, giới hạn pattern phù hợp và compile tests |

## 17. Bộ kiểm thử cần có cho case study record

| Đầu vào/điều kiện | Kết quả mong đợi | Quy tắc cần kiểm chứng |
| --- | --- | --- |
| `Submit(DraftOrder("O-100", Customer(...Address...), Money("VND",12500)))` | `Review ...` | Nested pattern khớp, guard ngưỡng đúng |
| Đơn đầy đủ tổng 500 cents | `Ready ...` | Nhánh review không chọn, nhánh thường chọn |
| `Customer.deliveryAddress == null` | `Incomplete submit` | Nested `Address(...)` không match |
| `DraftOrder.customer == null` | `Incomplete submit` | Nested `Customer(...)` không match |
| `DraftOrder.orderId` toàn khoảng trắng | `Incomplete submit` | Guard từ chối dữ liệu |
| `Submit(null)` | `Incomplete submit` | `Submit(var draft)` vẫn match |
| `Cancel` với lý do có nội dung | `Cancel ...` | Nhánh guard đúng |
| `Cancel` với lý do trắng | `Invalid cancellation` | Nhánh fallback cùng subtype |
| Selector `null` | `Missing action` | `case null` rõ ràng |
| `new Money("VND",-1)` | `IllegalArgumentException` | Constructor invariant |
| `new Address("", "VN")` | `IllegalArgumentException` | Constructor invariant |
| Thêm subtype mới không bổ sung case | Compile error về exhaustiveness | Compiler hỗ trợ khi domain mở rộng |
| Đổi số lượng component của `DraftOrder` | Pattern cũ cần sửa/biên dịch lại | Record shape là contract |

Trong chương trình mẫu, hậu tố `equal=true` của sáu dòng đầu kiểm chứng việc **hai cách triển khai cùng trả kết quả** với những input đã chọn. Trong dự án thật, cần thêm property-based tests hoặc unit tests cho nhiều tổ hợp hợp lệ/không hợp lệ, đặc biệt khi dữ liệu import có nhiều ngoại lệ.

### Test compile-time và test runtime có nhiệm vụ khác nhau

- **Compile-time:** phát hiện pattern sai số lượng component, dominance, dùng biến ngoài scope hoặc `switch expression` không exhaustive.
- **Runtime:** phát hiện dữ liệu thiếu, business validation sai, currency không hợp lệ, logic ưu tiên nhánh và tác động giao dịch.
- **Integration:** kiểm tra DTO/schema, deserialization, persistence, idempotency, authorization và tương thích phiên bản.

Không thể thay thế tất cả kiểm thử nghiệp vụ bằng compiler; cũng không nên viết một test runtime để “chứng minh” lỗi compiler bằng cách bỏ qua bước compile.

## 18. Bài tập thực hành

### Bài 1 — Đọc nested record pattern

Cho:

~~~java
record Contact(String email) {}
record Member(String id, Contact contact) {}
~~~

Với `Object input`, dự đoán hành vi:

~~~java
String result = switch (input) {
    case Member(var id, Contact(var email)) ->
            id + ":" + email;
    case Member(var id, var contact) -> "Missing contact";
    case null -> "No member";
    default -> "Other";
};
~~~

**Đáp án:** `new Member("M1", new Contact("m@example.com"))` chọn nhánh đầu; `new Member("M2", null)` chọn nhánh `"Missing contact"`; selector null chọn `"No member"`. Nested `Contact(...)` không match component null; `var contact` có thể ràng buộc null.

### Bài 2 — Tìm lỗi đặt tên component

Với `record Money(String currency, long cents) {}`:

~~~java
// CỐ Ý SAI VỀ Ý NGHĨA BIẾN, dù Java có thể biên dịch.
if (input instanceof Money(var cents, var currency)) {
    System.out.println(cents + " " + currency);
}
~~~

**Đáp án:** Component thứ nhất là `currency`, thứ hai là `cents`. Tên trong pattern bị đảo nên biến `cents` thực tế có kiểu `String` và biến `currency` có kiểu `long`. Sửa thành `Money(var currency, var cents)`. Đây là minh họa lý do phải so pattern với record declaration, không suy luận theo tên tự chọn.

### Bài 3 — Chọn nơi đặt invariant

Một hệ thống chỉ cho phép `ConfirmedOrder` có `orderId` không rỗng và `total` khác null. Nên viết `when orderId != null && !orderId.isBlank() && total != null` trong mọi `switch` hay validate trong constructor/factory?

**Gợi ý đáp án:** Nên đặt invariant cốt lõi ở **constructor/factory**, để object không thể được tạo qua đường hợp lệ với dữ liệu vi phạm. Deconstruction trong phép toán có thể dựa vào invariant đó. Tại boundary vẫn phải bắt lỗi và trả kết quả phù hợp cho dữ liệu đầu vào không hợp lệ.

### Bài 4 — Lựa chọn deep pattern hay helper

Một hàm cần báo riêng `MISSING_CUSTOMER`, `MISSING_ADDRESS` và `MISSING_TOTAL`. Có nên chỉ dùng một case `Submit(DraftOrder(... Customer(... Address(...)), Money(...)))` rồi fallback `"Incomplete"` không?

**Gợi ý đáp án:** Không đủ nếu yêu cầu là thông điệp lỗi riêng. Dùng helper `validateDraft` trả validation code hoặc kiểm tra accessor từng bước rõ ràng. Có thể giữ `switch` để chọn `Submit`/`Cancel`, nhưng để phần kiểm tra nhiều lý do trong helper có tên.

### Bài 5 — Thêm hành động mới

Thêm `record UpdateAddress(String orderId, Address address) implements OrderAction {}` vào sealed hierarchy. Điều gì cần làm?

**Đáp án:** Cập nhật `permits` và thêm case thích hợp cho `UpdateAddress` trong các exhaustive `switch expression` xử lý `OrderAction`. Compiler có thể giúp phát hiện nơi thiếu nhánh. Cũng cần test xử lý null/validation và cập nhật API/schema nếu hành động có thể đến từ hệ thống ngoài.

### Bài 6 — Deconstruction có thay đổi object gốc không?

Với `Customer(var id, var address)`, có phải `address` là bản sao deep copy của `Address` không?

**Đáp án:** Không. Pattern ràng buộc các giá trị component. Nó không tự tạo bản sao record hay copy sâu đồ thị object. Record nói chung có các field final ở mức component nhưng nếu component tham chiếu đến đối tượng mutable, cần biện pháp bất biến riêng.

### Bài 7 — Guard bị che

~~~java
// CỐ Ý SAI: giả sử input có kiểu Object và DraftOrder hợp lệ.
String value = switch (input) {
    case DraftOrder(var id, var customer, var total) -> "draft";
    case DraftOrder(var id, var customer, var total)
            when hasText(id) -> "valid id";
    case null -> "null";
    default -> "other";
};
~~~

**Đáp án:** Case không guard đầu đã bao phủ các `DraftOrder`, nên case `when hasText(id)` phía sau bị dominated. Đặt guard case lên trước và case tổng quát sau.

## 19. Checklist ra quyết định cho domain

Trước khi đưa record deconstruction vào production, kiểm tra:

1. **Domain type có ý nghĩa rõ không?** `DraftOrder` khác `ConfirmedOrder`; `Submit` là command chứ không phải event.
2. **Record shape có ổn định không?** Pattern phụ thuộc thứ tự, số lượng và kiểu component.
3. **Tất cả component cần dùng chứ?** Nếu chỉ cần một field, accessor có tên có thể dễ hiểu hơn.
4. **Nested null semantics có đúng không?** Selector null, component null và chuỗi rỗng là các trường hợp khác nhau.
5. **Invariant đã được kiểm tra ở ranh giới phù hợp chưa?** Constructor/factory cho domain, validation cho DTO.
6. **Guard có thuần túy không?** Không gọi payment gateway, repository ghi hay audit quan trọng để chọn nhánh.
7. **Case có thứ tự từ đặc biệt tới tổng quát không?** Tránh dominance và sai ưu tiên phân loại.
8. **Sealed `switch` có exhaustive không?** Tránh `default` không cần thiết che việc thêm subtype.
9. **Lý do lỗi có cần chi tiết không?** Nếu có, validation result thường phù hợp hơn một nested pattern rồi fallback chung.
10. **Code public API có chịu nổi khi record shape thay đổi không?** Cân nhắc accessor/domain method và compatibility.
11. **Đã chạy trên JDK target chưa?** Record patterns và pattern `switch` final từ Java 21.
12. **Đã kiểm tra cả compile time và runtime chưa?** Chạy input đầy đủ, thiếu, guard đúng/sai, null, invariant sai.
13. **Có side effect bị giấu trong accessor không?** Pattern matching không phải nơi kiểm soát I/O hoặc transaction.
14. **Có benchmark nếu quyết định dựa trên hiệu năng không?** Không suy luận chi phí từ số dấu ngoặc nested pattern.

## 20. Tổng kết

**Deconstruction là công cụ để nhìn vào cấu trúc dữ liệu, không phải lý do để phơi bày mọi chi tiết domain.**

- `record` giúp biểu diễn các giá trị có component rõ ràng.
- **Record pattern** kiểm tra record và ràng buộc component; **nested record pattern** kiểm tra thêm cấu trúc lồng nhau.
- `sealed` kết hợp `switch expression` giúp xử lý tập biến thể có kiểm soát và nhận tín hiệu compiler khi thêm subtype.
- **`when`** dùng để phân loại bằng điều kiện thuần túy, không nên thực hiện transaction hoặc side effect.
- **Dữ liệu nháp** cần fallback/validation vì component có thể thiếu; **domain đã xác nhận** nên được bảo vệ bằng invariant ở constructor/factory.
- Giữ lại **accessor có tên** và **domain method** ở nơi chúng diễn đạt ý nghĩa tốt hơn nested deconstruction, nhất là khi muốn API ổn định.
- Kiểm thử cả những trường hợp không match, component null, guard false, thêm subtype và thay record shape.
- Đừng chọn nested pattern chỉ vì viết được một biểu thức rất ngắn. Hãy chọn cách người đọc dễ xác định **dữ liệu nào được chấp nhận, trường hợp nào bị từ chối và ai chịu trách nhiệm về invariant nghiệp vụ**.

**Nguồn chính thức:** [JEP 395 — Records](https://openjdk.org/jeps/395); [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409); [JEP 440 — Record Patterns](https://openjdk.org/jeps/440); [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441); [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html); [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
