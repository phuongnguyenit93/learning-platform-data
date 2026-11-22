# Refactor nested pattern thành phương thức domain (Java 21)

## Mục tiêu

Sau bài này, bạn biết cách nhận ra khi một `nested record pattern` đang chứa **quy tắc nghiệp vụ**, chuyển quy tắc đó thành phương thức có tên diễn đạt ý nghĩa trong domain, và giữ nguyên hành vi về kiểu dữ liệu, `null`, thứ tự nhánh `switch` và điều kiện `when`. Bài học sử dụng **Record Patterns (JEP 440)** và **Pattern Matching for switch (JEP 441)**, đã là tính năng chính thức từ Java 21.

**Nguyên tắc chính:** pattern matching rất phù hợp để **nhận diện và phân rã cấu trúc dữ liệu**; phương thức domain phù hợp để **diễn đạt quyết định nghiệp vụ**. Refactor có giá trị khi nhiều nơi phải hiểu chi tiết cấu trúc record mới trả lời được một câu hỏi nghiệp vụ.

## 1. Vấn đề: điều kiện nghiệp vụ bị nhúng trong cấu trúc

Giả sử ứng dụng ví dụ có ba record lồng nhau:

```text
Order
├── id: String
├── payment: PaymentState
└── customer: Customer
    ├── name: String
    └── address: Address
        ├── city: String
        └── country: String
```

Đây là **quy tắc giả định của ví dụ**, không phải quy định giao hàng thực tế: đơn hàng đủ điều kiện giao trong ngày khi đã thanh toán (`PAID`), quốc gia có mã `VN` và thành phố có mã `HCM`. Đối tượng có thể thiếu `customer` hoặc `address`; khi thiếu thì đơn không đủ điều kiện.

Một cách viết trực tiếp tại lớp điều phối:

```java
case Order(
        var id,
        Customer(var name, Address(var city, var country)),
        var payment)
        when payment == PaymentState.PAID
             && "VN".equals(country)
             && "HCM".equals(city) -> "SAME_DAY";
```

**Đây là một nhánh `case` minh họa**, cần nằm trong `switch` thích hợp. Nó hợp lệ trong Java 21, nhưng có những chi phí khi dùng lặp lại ở controller, service hoặc nơi xử lý sự kiện:

- Mỗi nơi phải biết `Order → Customer → Address`, dù mục đích chỉ là hỏi “đơn có đủ điều kiện giao trong ngày không?”.
- Các mã `"VN"` và `"HCM"` cùng quy tắc thanh toán bị phân tán. Thay đổi chính sách dễ khiến các nơi lệch nhau.
- Một thay đổi cấu trúc, chẳng hạn chuyển địa chỉ giao hàng thành component trực tiếp của `Order`, có thể làm phải sửa hàng loạt pattern.
- Các trường hợp `customer == null`, `address == null` hoặc giá trị lá bằng `null` dễ bị xử lý không nhất quán.

Pattern **không sai**; điều cần xem xét là quy tắc nghiệp vụ có đang bị đặt ở quá nhiều nơi hay không.

## 2. Chọn phương thức domain và nơi đặt trách nhiệm

Thay vì để client quyết định từ các component của record, chuyển thành những câu hỏi có tên:

| Kiểu domain | Phương thức | Trách nhiệm |
|---|---|---|
| `Address` | `supportsSameDay()` | Địa chỉ có thuộc vùng giao trong ngày theo chính sách ví dụ không? |
| `Customer` | `hasSameDayAddress()` | Khách hàng có địa chỉ phù hợp không? |
| `Order` | `qualifiesForSameDay()` | Đơn hàng đã thanh toán và có khách hàng với địa chỉ phù hợp không? |

Client sau refactor chỉ cần hỏi:

```java
case Order order when order.qualifiesForSameDay() -> "SAME_DAY";
```

Đây là **phương thức domain**, vì nó diễn đạt một quy tắc về `Order` và sử dụng các thành phần thuộc chính domain. Nó không phụ thuộc HTTP, database, giao diện người dùng hay định dạng phản hồi.

Đặt phương thức ở lớp có đủ ngữ cảnh để trả lời câu hỏi và có quyền sở hữu quy tắc. Với quy tắc đơn hàng, `Order` là đầu mối phù hợp; `Address` và `Customer` chỉ giữ các kiểm tra có ý nghĩa riêng. Nếu chính sách phụ thuộc giá, hạn mức, múi giờ hay cấu hình thay đổi liên tục từ dịch vụ ngoài, nên cân nhắc **domain service/policy object được truyền vào**, không giấu truy cập dịch vụ ngoài trong getter hay record.

## 3. Ví dụ hoàn chỉnh: trước và sau refactor

Tạo một tệp **`NestedPatternRefactorDemo.java`** với toàn bộ nội dung sau. Các phương thức `routeBefore` và `routeAfter` đều trả về ba giá trị: `SAME_DAY`, `STANDARD`, `NOT_ORDER`.

```java
public class NestedPatternRefactorDemo {
    enum PaymentState { PAID, PENDING }

    record Address(String city, String country) {
        boolean supportsSameDay() {
            return "VN".equals(country) && "HCM".equals(city);
        }
    }

    record Customer(String name, Address address) {
        boolean hasSameDayAddress() {
            return address != null && address.supportsSameDay();
        }
    }

    record Order(String id, Customer customer, PaymentState payment) {
        boolean qualifiesForSameDay() {
            return payment == PaymentState.PAID
                    && customer != null
                    && customer.hasSameDayAddress();
        }
    }

    // BEFORE: client biết toàn bộ cấu trúc Order -> Customer -> Address.
    static String routeBefore(Object input) {
        return switch (input) {
            case null -> "NOT_ORDER";
            case Order(var id,
                       Customer(var name, Address(var city, var country)),
                       var payment)
                    when payment == PaymentState.PAID
                         && "VN".equals(country)
                         && "HCM".equals(city) -> "SAME_DAY";
            case Order(var id, var customer, var payment) -> "STANDARD";
            default -> "NOT_ORDER";
        };
    }

    // AFTER: client chỉ cần kiểu Order và câu hỏi có nghĩa nghiệp vụ.
    static String routeAfter(Object input) {
        return switch (input) {
            case null -> "NOT_ORDER";
            case Order order when order.qualifiesForSameDay() -> "SAME_DAY";
            case Order order -> "STANDARD";
            default -> "NOT_ORDER";
        };
    }

    // Kiểm tra hồi quy: mọi trường hợp phải cho cùng kết quả.
    static void show(String label, Object input) {
        String before = routeBefore(input);
        String after = routeAfter(input);
        if (!before.equals(after)) {
            throw new AssertionError(label + ": before=" + before + ", after=" + after);
        }
        System.out.println(label + ": " + after);
    }

    public static void main(String[] args) {
        show("null root", null);
        show("other type", "text");
        show("paid HCM", new Order("O1", new Customer("An",
                new Address("HCM", "VN")), PaymentState.PAID));
        show("pending HCM", new Order("O2", new Customer("An",
                new Address("HCM", "VN")), PaymentState.PENDING));
        show("no customer", new Order("O3", null, PaymentState.PAID));
        show("no address", new Order("O4", new Customer("An", null),
                PaymentState.PAID));
        show("null city", new Order("O5", new Customer("An",
                new Address(null, "VN")), PaymentState.PAID));
        show("different city", new Order("O6", new Customer("An",
                new Address("HN", "VN")), PaymentState.PAID));
        show("null payment", new Order("O7", new Customer("An",
                new Address("HCM", "VN")), null));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac --release 21 NestedPatternRefactorDemo.java
java NestedPatternRefactorDemo
```

Kết quả:

```text
null root: NOT_ORDER
other type: NOT_ORDER
paid HCM: SAME_DAY
pending HCM: STANDARD
no customer: STANDARD
no address: STANDARD
null city: STANDARD
different city: STANDARD
null payment: STANDARD
```

Ví dụ đã được kiểm tra biên dịch với `javac --release 21` và chạy. Trong mỗi trường hợp, `show` so sánh kết quả **trước/sau** và sẽ ném `AssertionError` nếu khác nhau. Đây là phép kiểm tra hành vi cho các dữ liệu mẫu; trong dự án thực tế vẫn cần unit test cho các trường hợp biên theo hợp đồng nghiệp vụ.

## 4. Vì sao refactor giữ được hành vi?

### 4.1. Root null và giá trị không phải Order

Trong `routeBefore` và `routeAfter`, `case null` trả về `NOT_ORDER`. Nếu selector là một `String`, `default` cũng trả về `NOT_ORDER`. Phương thức domain chỉ được gọi sau khi `case Order order` đã khớp; nó không nhận selector tùy ý hoặc tự xử lý việc ép kiểu.

Lưu ý: trong `switch` pattern của Java 21, chỉ viết `default` không đồng nghĩa với tự động bắt selector `null`. Để giữ nghĩa của bài toán, hai phiên bản đều khai báo `case null`.

### 4.2. Nested record bằng null

Ở phiên bản trước, phần `Customer(..., Address(...))` chỉ khớp khi cả `Customer` và `Address` đều là đối tượng record **khác `null`**. Nếu một trong hai bằng `null`, nhánh giao trong ngày không khớp; nhánh `case Order(var id, var customer, var payment)` nhận `Order` còn lại và trả về `STANDARD`.

Ở phiên bản sau, `Order.qualifiesForSameDay()` kiểm tra `customer != null`; `Customer.hasSameDayAddress()` kiểm tra `address != null` trước khi truy cập phương thức tiếp theo. Toán tử `&&` trong Java đánh giá từ trái sang phải và dừng ngay khi gặp `false`. Hai đường đi vì thế cùng trả về `STANDARD`, không dereference đối tượng thiếu.

### 4.3. Component lá bằng null

`Address(var city, var country)` là record pattern cần một `Address` khác `null`. Tuy nhiên, các pattern `var city` và `var country` **có thể bind `null`** từ component kiểu tham chiếu. Điều kiện `"HCM".equals(city)` hoặc `"VN".equals(country)` sẽ cho `false` khi đối số là `null`.

Phiên bản domain tiếp tục dùng `constant.equals(component)`. Cả hai vẫn coi `city == null` hoặc `country == null` là không đủ điều kiện. Phép so sánh `payment == PaymentState.PAID` cũng an toàn nếu `payment == null`.

**Không tự ý thay `"HCM".equals(city)` bằng `city.equals("HCM")`** khi refactor: nếu `city` có thể null, cách viết thứ hai ném `NullPointerException` và đổi hợp đồng hành vi.

### 4.4. Thứ tự switch và dominance

Trong phiên bản sau:

```java
case Order order when order.qualifiesForSameDay() -> "SAME_DAY";
case Order order -> "STANDARD";
```

Nhánh có `when` phải đứng trước nhánh `Order order` tổng quát. Nếu đảo thứ tự, nhánh tổng quát bao phủ nhánh hẹp hơn và trình biên dịch báo lỗi **dominated case label**. Một guard `when` chỉ chạy sau khi pattern tương ứng đã khớp.

Trước khi refactor, nhánh nested cụ thể cũng phải nằm trước nhánh `Order(...)` rộng hơn. Refactor không cho phép thay đổi tùy ý thứ tự các `case`.

## 5. Các bước refactor an toàn trong codebase

1. **Khoanh đúng hành vi hiện tại.** Ghi nhận loại input, các nhánh `null`, giá trị mặc định, guard, thứ tự `case` và những kết quả đầu ra phải giữ. Không gộp refactor với thay đổi yêu cầu nghiệp vụ.
2. **Đặt tên cho câu hỏi nghiệp vụ.** Nếu biểu thức là “đơn có đủ điều kiện giao trong ngày không?”, tên `qualifiesForSameDay()` rõ nghĩa hơn `check()`, `isValid()` hay `isMatch()`.
3. **Chọn nơi sở hữu quy tắc.** `Order` chịu trách nhiệm kiểm tra thanh toán và khách hàng; `Customer` kiểm tra sự tồn tại của địa chỉ; `Address` kiểm tra vùng giao trong ngày. Không chuyển code chỉ để tăng số phương thức.
4. **Chuyển logic mà vẫn giữ null contract.** Mỗi bước phải giữ short-circuit và điều kiện phân nhánh. Nếu cần từ chối `null` bằng constructor, đó là một thay đổi domain riêng cần đánh giá, không phải refactor thuần túy.
5. **Thay nested pattern tại caller bằng pattern nông.** Từ `Order(Customer(Address(...)), ...)` sang `Order order when order.qualifiesForSameDay()`; hoặc nếu đầu vào đã có kiểu `Order`, gọi thẳng `order.qualifiesForSameDay()`.
6. **Chạy kiểm tra hồi quy theo bảng trạng thái.** Bao phủ trường hợp đủ điều kiện, không đủ điều kiện, sai kiểu, root null và null ở từng tầng. So sánh kết quả trước/sau trước khi xóa cách cũ trong code thực tế.

Chỉ xóa biểu thức cũ khỏi production khi tất cả caller đã dùng cùng quy tắc mới và các tình huống biên đều được xác minh.

## 6. Khi nào vẫn nên dùng nested pattern?

Không phải nested record pattern nào cũng cần tách thành phương thức domain.

**Giữ pattern tại nơi sử dụng** khi nhiệm vụ là ánh xạ một lần từ cấu trúc dữ liệu sang kết quả, chẳng hạn bóc một event, log dữ liệu hoặc chọn định dạng hiển thị. Ví dụ sau chỉ lấy tên thành phố từ một `Order` nếu cấu trúc tồn tại:

```java
static String cityForDisplay(Object input) {
    return switch (input) {
        case Order(var id, Customer(var name, Address(var city, var country)),
                   var payment) -> city == null ? "(unknown)" : city;
        case null, default -> "(no address)";
    };
}
```

Đây là **phương thức minh họa** để thêm vào lớp `NestedPatternRefactorDemo` ở mục 3. Việc phân rã chỉ để hiển thị một giá trị, chưa nhất thiết biểu đạt quy tắc domain dùng lặp lại.

**Ưu tiên phương thức domain** khi biểu thức đại diện cho quyết định nghiệp vụ có tên riêng, xuất hiện ở nhiều nơi hoặc cần giữ ổn định khi cấu trúc dữ liệu bên trong thay đổi. Caller khi đó nên hỏi domain về hành vi, thay vì biết mọi component.

**Cân nhắc domain service/policy** khi quy tắc cần dữ liệu từ ngoài aggregate: cấu hình theo thời điểm, vùng giao hàng được cập nhật từ hệ thống khác, lịch hoạt động, giá hoặc quyền truy cập. Không nên thêm network call âm thầm vào `supportsSameDay()` chỉ để giữ cú pháp dễ đọc.

## 7. Lưu ý về record, API và hiệu năng

- **Record không mặc định cấm null.** Các component tham chiếu có thể nhận `null` trừ khi constructor hoặc hợp đồng của hệ thống quy định khác. Chính sách null thuộc domain và phải được giữ khi refactor.
- **Record là shallowly immutable.** Mỗi component không thể được gán lại sau khởi tạo, nhưng đối tượng tham chiếu chứa bên trong vẫn có thể mutable. Các phương thức kiểm tra nên tránh thay đổi trạng thái.
- **Phương thức domain nên có kết quả rõ ràng, nhất quán.** Một predicate như `qualifiesForSameDay()` phù hợp khi kết quả không phụ thuộc side effect; nếu quyết định cần thời điểm, truyền `Clock` hoặc một `Instant` đầu vào thay vì đọc ngầm thời gian hệ thống.
- **Không lộ `Object` nếu API domain đã biết kiểu.** `qualifiesForSameDay()` nằm trên `Order`, vì vậy nó không cần tham số `Object`, không cần tự dùng `instanceof`. `instanceof` hoặc `switch` chỉ còn nằm tại ranh giới phải phân loại đối tượng.
- **Không giả định phương thức mới luôn nhanh hơn.** Lợi ích chính của refactor là tính nhất quán và giảm phụ thuộc cấu trúc. Hiệu năng phụ thuộc JVM/JIT và workload; chỉ tối ưu sau khi đo.
- **Tên phương thức phải phản ánh chính sách.** `supportsSameDay()` trong ví dụ giả lập một tập mã tĩnh; nếu chính sách giao trong ngày thay đổi theo ngày, hãy dùng tên và API phản ánh dữ liệu cần thiết.

Một phiên bản ngắn hơn ở ranh giới khi chỉ cần boolean:

```java
static boolean eligible(Object input) {
    return input instanceof Order order && order.qualifiesForSameDay();
}
```

Đoạn trên dùng type pattern để xác nhận input là `Order`; nội dung nghiệp vụ vẫn do domain quyết định. Với `input == null`, `instanceof` là `false` và không gọi phương thức.

## 8. Các lỗi refactor thường gặp

| Lỗi | Tác động | Cách phòng tránh |
|---|---|---|
| Chuyển nested pattern thành chuỗi accessor mà thiếu null check | `NullPointerException` với `customer`/`address` thiếu | Giữ short-circuit trên từng component |
| Đổi thứ tự `case` rộng/hẹp | Lỗi dominated case, hoặc đổi nhánh được chọn | Giữ thứ tự từ cụ thể tới tổng quát |
| Bỏ `case null` | Selector null có thể ném `NullPointerException` | Ghi rõ hợp đồng của `null` ở ranh giới |
| Đổi `constant.equals(value)` thành `value.equals(constant)` | Thay đổi hành vi với nullable leaf | Giữ so sánh null-safe |
| Dời rule vào controller/helper chung tên `Utils` | Rule tiếp tục phân tán, thiếu sở hữu | Đặt tên có ý nghĩa tại domain hoặc domain policy |
| Cho `requireNonNull` vào constructor cùng đợt refactor | Làm thay đổi dữ liệu được phép tạo | Tách việc siết invariant thành thay đổi riêng |
| Đưa I/O, database hoặc thời gian thực vào predicate | Hành vi khó kiểm thử, khó dự đoán | Truyền context/policy cần thiết hoặc dùng domain service |
| Tách quá nhiều phương thức cho một biểu thức chỉ dùng một lần | Làm code khó theo dõi hơn | Đánh giá ý nghĩa nghiệp vụ và mức độ tái sử dụng |

## 9. Tự kiểm tra

Giả sử input là `new Order("O8", new Customer("Binh", null), PaymentState.PAID)`:

1. Nhánh `Order(Customer(Address(...)), ...)` có khớp không? **Không**: `Address(...)` không khớp `null`, dù `Order` và `Customer` vẫn tồn tại.
2. `case Order order when order.qualifiesForSameDay()` có đi vào `SAME_DAY` không? **Không**: `hasSameDayAddress()` trả về `false`.
3. Nhánh nào xử lý tiếp? **`case Order order -> "STANDARD"`**, vì `Order` tồn tại và không thỏa guard.
4. Nếu `country` đổi thành `null` nhưng `city` vẫn là `"HCM"`, kết quả có đổi không? **Không**: `"VN".equals(null)` là `false` ở cả hai phiên bản.
5. Nếu thêm điều kiện `order.id() != null` vào `qualifiesForSameDay()` mà không có trong logic cũ, có còn là refactor giữ nguyên hành vi không? **Không**: đó là thay đổi quy tắc nghiệp vụ cần được duyệt và kiểm thử độc lập.

## Ghi nhớ

- **Nested record pattern** diễn đạt *cấu trúc nào đang hiện diện*.
- **Domain method** diễn đạt *quy tắc nghiệp vụ nào được thỏa mãn*.
- Khi chuyển từ `case Order(Customer(Address(...))) when ...` sang `case Order order when order.qualifiesForSameDay()`, cần giữ nguyên hành vi với `null`, thứ tự nhánh, guard và kết quả mặc định.
- Refactor tốt làm caller ít biết cấu trúc nội bộ hơn và giữ quy tắc tại một nơi có trách nhiệm rõ ràng, đồng thời không làm thay đổi input/output quan sát được.

## Tài liệu chính thức

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JLS Java SE 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
