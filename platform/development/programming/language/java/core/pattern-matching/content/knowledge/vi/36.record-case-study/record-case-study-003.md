# Lấy `customer` và `amount` trong một record pattern (Java 21+)

## 1. Bài toán: lấy hai dữ liệu của một bản ghi trong cùng phép kiểm tra

Giả sử ứng dụng xử lý đơn hàng, mỗi đơn có **khách hàng** (`customer`) và **số tiền** (`amount`). Nếu dữ liệu đến một hàm dưới kiểu rộng `Object`, cách truyền thống thường gồm kiểm tra kiểu, ép kiểu và gọi các accessor:

~~~java
record Customer(String id, String name) {}
record Purchase(Customer customer, java.math.BigDecimal amount) {}

static String manual(Object input) {
    if (input instanceof Purchase) {
        Purchase purchase = (Purchase) input;
        Customer customer = purchase.customer();
        java.math.BigDecimal amount = purchase.amount();
        return customer.name() + ": " + amount.toPlainString();
    }
    return "Không phải Purchase";
}
~~~

Java 21 cung cấp cách gọn hơn: **record pattern** có thể vừa kiểm tra kiểu ngoài, vừa tách **nhiều record components trong một pattern duy nhất**.

~~~java
static String withPattern(Object input) {
    if (input instanceof Purchase(var customer, var amount)) {
        return customer.name() + ": " + amount.toPlainString();
    }
    return "Không phải Purchase";
}
~~~

Ở đây, `Purchase(var customer, var amount)` là **một record pattern**, không phải hai phép `instanceof` riêng và cũng không phải lời gọi constructor. Hai biến `customer` và `amount` được ràng buộc theo **thứ tự** hai components trong khai báo record.

**Mục tiêu của bài:** hiểu cơ chế tách đồng thời `customer` và `amount`, tiến thêm một bước với **nested record pattern** để lấy chi tiết khách hàng, dùng `when` để lọc số tiền, xử lý `null` đúng chỗ, và kiểm chứng bằng ví dụ chạy được.

Record patterns được chuẩn hóa trong **Java 21 (JEP 440)**; pattern matching for `switch` được chuẩn hóa cùng phiên bản (JEP 441). Với JDK 21+, các tính năng trong bài **không cần `--enable-preview`**.

> Các ví dụ ngắn trong từng mục là đoạn trích để minh họa. Chương trình độc lập, có thể biên dịch và chạy, nằm ở mục 8.

## 2. Record components xác định chính xác hai vị trí

Xét:

~~~java
record Customer(String id, String name) {}
record Purchase(Customer customer, BigDecimal amount) {}
~~~

(Trong file thực tế, import `java.math.BigDecimal`.)

Khai báo `Purchase` có **đúng hai components**:

| Vị trí | Tên component | Kiểu tĩnh | Giá trị được lấy ra |
| --- | --- | --- | --- |
| 1 | `customer` | `Customer` | Đối tượng khách hàng |
| 2 | `amount` | `BigDecimal` | Số tiền của giao dịch |

Một pattern hợp lệ:

~~~java
if (input instanceof Purchase(var customer, var amount)) {
    // customer có kiểu Customer
    // amount có kiểu BigDecimal
}
~~~

Không có quy tắc buộc tên biến phải giống tên record component. Ví dụ này cũng hợp lệ:

~~~java
if (input instanceof Purchase(var buyer, var total)) {
    System.out.println(buyer.name() + ": " + total);
}
~~~

Bản chất là compiler ghép **vị trí 1 với `Customer`, vị trí 2 với `BigDecimal`**, rồi suy luận kiểu biến từ khai báo.

**Cảnh báo quan trọng:** nếu hai component cùng kiểu, đặt tên lẫn vị trí có thể vẫn biên dịch nhưng sai ý nghĩa. Với `record Transfer(String from, String to) {}`, pattern `Transfer(var destination, var source)` là hợp lệ về kiểu nhưng gán tên trái ý nghĩa thực tế. Hãy review theo **thứ tự component**, không theo cảm nhận từ tên biến.

## 3. `var` trong record pattern là suy luận kiểu tĩnh

`var` trong `Purchase(var customer, var amount)` **không** là kiểu động. Nó là *variable pattern* mà compiler có thể suy luận kiểu dựa trên component tương ứng:

- `customer`: kiểu tĩnh `Customer`.
- `amount`: kiểu tĩnh `BigDecimal`.

Có thể khai báo type patterns tường minh:

~~~java
if (input instanceof Purchase(Customer customer, BigDecimal amount)) {
    System.out.println(customer.id() + " / " + amount.toPlainString());
}
~~~

Với các component tham chiếu đúng kiểu tĩnh của chúng, cách này có ý nghĩa gần với `Purchase(var customer, var amount)`. `var` gọn khi kiểu đã hiển nhiên; kiểu tường minh hữu ích nếu review cần nhìn rõ hợp đồng của dữ liệu.

Khi dùng biến trong thân `if`, compiler đã biết pattern thành công, nên không cần:

~~~java
// Cast thừa sau record pattern:
// Customer customer = (Customer) purchase.customer();
~~~

Ngoài `if`, biến pattern chịu quy tắc **flow scoping**. Bạn không thể dùng `customer` hay `amount` tại mọi dòng chỉ vì đã viết chúng trong điều kiện.

Ví dụ đúng:

~~~java
if (input instanceof Purchase(var customer, var amount)) {
    System.out.println(customer.id()); // Có trong nhánh khớp.
}
// Ở đây không giả định customer/amount còn trong scope.
~~~

Lỗi scope hoặc tên biến trùng trong pattern có thể khiến code không biên dịch. Đặt tên biến rõ ràng và dùng trong miền compiler bảo đảm đã khớp.

## 4. Từ một pattern có hai components đến nested record pattern

Giả sử cần lấy **tên khách hàng** và **amount**, không chỉ lấy đối tượng `Customer`. Có hai cách.

### Cách A — tách `customer` rồi gọi accessor

~~~java
if (input instanceof Purchase(var customer, var amount)) {
    String name = customer.name();
    System.out.println(name + ": " + amount.toPlainString());
}
~~~

Cách này rõ ràng khi khách hàng chắc chắn khác null theo invariant dữ liệu. Nếu `customer == null`, câu `customer.name()` gây NPE.

### Cách B — tách luôn record `Customer` bên trong

~~~java
if (input instanceof Purchase(
        Customer(var customerId, var customerName),
        var amount)) {

    System.out.println(customerName + " (" + customerId
            + "): " + amount.toPlainString());
}
~~~

Toàn bộ `Purchase(Customer(var customerId, var customerName), var amount)` vẫn là **một record pattern ngoài** chứa một **record pattern lồng**:

~~~text
Purchase
├── component 1: customer (Customer)
│   ├── component 1: customerId
│   └── component 2: customerName
└── component 2: amount (BigDecimal)
~~~

Quy trình khớp:

1. Đầu vào phải phù hợp kiểu record `Purchase`.
2. Component thứ nhất phải phù hợp record `Customer`.
3. Compiler/VM tách `id` và `name` của `Customer` và ràng buộc hai pattern variables.
4. Component thứ hai của `Purchase` được ràng buộc cho `amount`.
5. Khi toàn bộ pattern khớp, thân `if` hoặc case mới chạy.

**Lưu ý:** một record pattern lồng không gọi constructor `new Customer(...)`, không tạo object Customer mới và không khẳng định tên/id của khách hàng đã được validate. Nó chỉ deconstruct giá trị hiện tại.

## 5. `null`: khác nhau giữa record ngoài, khách hàng và số tiền

Đây là điểm đáng kiểm tra nhất khi lấy `customer` và `amount` trong một pattern.

### 5.1. Selector là `null`

~~~java
Object value = null;

boolean ok = value instanceof Purchase(var customer, var amount);
System.out.println(ok); // false
~~~

Với `instanceof`, record pattern **không khớp null**; biểu thức trả `false`, không ném NPE do phép kiểm tra kiểu.

Nhưng `switch (value)` có quy tắc khác: khi selector là `null` mà **không có `case null`**, switch trên reference selector ném `NullPointerException` (kể cả có `default`).

### 5.2. `customer == null` trong record ngoài

Giả sử dữ liệu đến từ một record được phép chứa component null:

~~~java
Purchase purchase = new Purchase(null, new BigDecimal("100"));
~~~

Pattern trực tiếp:

~~~java
if (purchase instanceof Purchase(var customer, var amount)) {
    System.out.println(customer == null); // true
}
~~~

`var customer` là component pattern vô điều kiện đối với kiểu `Customer` của component, nên có thể **ràng buộc null**. Vì vậy nhánh được chạy, nhưng không được mù quáng gọi `customer.name()`.

Pattern lồng:

~~~java
if (purchase instanceof Purchase(Customer(var id, var name), var amount)) {
    // Không chạy: nested record Customer(...) không khớp null.
}
~~~

Pattern ngoài `Purchase` hợp lệ nhưng **toàn bộ nested pattern không khớp** vì component khách hàng null. Hai trường hợp phải phân biệt rõ khi review.

### 5.3. `amount == null` trong record ngoài

~~~java
Purchase purchase = new Purchase(
        new Customer("C-7", "An"), null);
~~~

Pattern trực tiếp `Purchase(var customer, var amount)` có thể khớp và ràng buộc `amount == null`. Nested pattern `Purchase(Customer(var id,var name),var amount)` cũng có thể khớp vì Customer tồn tại; bản thân `var amount` không chặn null.

Do đó:

~~~java
// KHÔNG AN TOÀN nếu amount có thể null:
// amount.signum() > 0

// AN TOÀN:
amount != null && amount.signum() > 0
~~~

**Kết luận:** record pattern cho bạn **kiểu tĩnh** và **cấu trúc**, chứ không phải bảo đảm tất cả reference components không null. Những điều kiện null cần có hợp đồng rõ tại constructor, boundary hoặc nhánh xử lý.

## 6. Lấy `customer` và `amount` bằng `switch`, kết hợp `when`

Đối với nhiều điều kiện của `amount`, `switch` expression Java 21 giúp thể hiện quy tắc phân loại:

~~~java
static String inspect(Object value) {
    return switch (value) {
        case null -> "Không có đơn";

        case Purchase(Customer(var id, var name), var amount)
                when amount != null && amount.signum() > 0 ->
            name + " thanh toán " + amount.toPlainString();

        case Purchase(Customer(var id, var name), var amount)
                when amount != null && amount.signum() == 0 ->
            name + " có số tiền bằng 0";

        case Purchase(Customer(var id, var name), var amount) ->
            name + " có số tiền null hoặc âm";

        case Purchase(var customer, var amount) ->
            "Thiếu khách hàng";

        default -> "Không phải Purchase";
    };
}
~~~

Hãy đọc theo **thứ tự**:

1. `case null` giải quyết selector null (nếu null là đầu vào được cho phép).
2. Nhánh `Purchase(Customer(...), var amount)` với guard đầu chỉ chọn khi Customer hiện diện **và** amount khác null, dương.
3. Nhánh với guard thứ hai chỉ chọn khi Customer hiện diện **và** amount khác null, bằng 0.
4. Nhánh nested không guard bắt các Purchase còn lại có Customer hiện diện; đây là amount **âm hoặc null**.
5. Nhánh `Purchase(var customer, var amount)` tổng quát đứng sau cùng của nhóm Purchase để xử lý Customer null.
6. `default` là kiểu không thuộc Purchase; **không** thay thế `case null`.

Tại sao đặt nhánh cụ thể trước nhánh chung? Nếu đặt `case Purchase(var customer, var amount)` lên đầu, nó đã khớp mọi Purchase (không null) trước các pattern chuyên biệt, khiến những nhánh sau có thể bị compiler báo **dominated case label**.

### Guard chỉ chạy sau khi pattern khớp

`amount != null && amount.signum() > 0` có **short-circuit**: `signum()` chỉ chạy sau khi kiểm tra amount khác null. Nếu Customer component null, nested Customer pattern không khớp, nên guard tương ứng không được đánh giá.

Không đặt I/O, ghi database hoặc mutation vào guard chỉ để chọn case. Guard đơn giản, không side effect thường dễ review và test hơn.

## 7. `BigDecimal`: đọc số tiền đúng nghĩa, không dựa vào `==`

Dữ liệu tiền thường sử dụng `BigDecimal` thay vì `double` để tránh sai lệch biểu diễn nhị phân cho các phép tính thập phân. Trong Java:

~~~java
BigDecimal amount = new BigDecimal("125000.00");
int sign = amount.signum();
~~~

`signum()` trả:

- `1` nếu số dương.
- `0` nếu bằng 0.
- `-1` nếu âm.

Để so sánh giá trị số học:

~~~java
BigDecimal left = new BigDecimal("10.0");
BigDecimal right = new BigDecimal("10.00");

System.out.println(left.compareTo(right) == 0); // true
System.out.println(left.equals(right));          // false
~~~

`compareTo` so sánh **giá trị số** (không yêu cầu cùng scale), trong khi `equals` của BigDecimal còn xét **scale**. `==` trên hai đối tượng BigDecimal là so sánh tham chiếu, không phải số tiền.

**Đừng tạo BigDecimal từ literal `double` khi cần giá trị thập phân chính xác:**

~~~java
// Nên:
new BigDecimal("0.10");

// Cẩn thận với:
new BigDecimal(0.10); // Có thể mang sai lệch biểu diễn nhị phân.
~~~

Trong ứng dụng thật, amount còn cần chính sách về **currency, scale, rounding, range và dấu**. Bài demo coi amount là số tiền danh nghĩa, không xử lý nhiều loại tiền hoặc phép tính thuế. Khi phải tính tổng/giá trị theo tiền tệ, cân nhắc value object như `Money(BigDecimal amount, Currency currency)` và quy tắc làm tròn rõ ràng.

Đáng chú ý: record chứa `BigDecimal` có `equals()` dựa vào `BigDecimal.equals()` của component. Hai record giống nhau về mặt số học nhưng khác scale có thể không bằng nhau theo `record.equals()`. Không dùng value equality như bằng chứng hai giao dịch là cùng một yêu cầu nghiệp vụ.

## 8. Chương trình Java 21+ hoàn chỉnh, chạy được

Mã sau cố ý **cho phép Customer hoặc amount bằng null trong `Order`** để minh họa cách record pattern khớp và nhánh fallback xử lý input thiếu dữ liệu. Đây là mô hình **đầu vào/dữ liệu thử nghiệm**, **không** phải recommendation để lưu các Order nghiệp vụ sai invariant. `Customer` có compact constructor kiểm tra id/name; `Order` chỉ kiểm tra orderId. Mục 10 trình bày cách siết invariant trong domain model.

Lưu thành **`CustomerAmountPatternDemo.java`**:

~~~java
import java.math.BigDecimal;

public class CustomerAmountPatternDemo {
    record Customer(String id, String name) {
        public Customer {
            id = required(id, "id");
            name = required(name, "name");
        }
    }

    record Order(String orderId, Customer customer,
                 BigDecimal amount) {
        public Order {
            orderId = required(orderId, "orderId");
        }
    }

    static String required(String text, String field) {
        if (text == null || text.isBlank())
            throw new IllegalArgumentException(
                    field + " không được trống");
        return text.strip();
    }

    static String direct(Object input) {
        if (input instanceof Order(var id, var customer, var amount)) {
            return "Direct " + id + ": customer=" +
                    (customer == null ? "null" : customer.id()) +
                    ", amount=" +
                    (amount == null ? "null" : amount.toPlainString());
        }
        return "Direct: không phải Order";
    }

    static String nested(Object input) {
        if (input instanceof Order(
                var id,
                Customer(var customerId, var name),
                var amount)) {

            return "Nested " + id + ": "
                    + name + " (" + customerId + "), amount="
                    + (amount == null ? "null" : amount.toPlainString());
        }
        return "Nested: không khớp";
    }

    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL_SELECTOR";

            case Order(var id, Customer(var cid, var name), var amount)
                    when amount != null && amount.signum() > 0 ->
                "POSITIVE " + id + ": " + name + " / "
                        + amount.toPlainString();

            case Order(var id, Customer(var cid, var name), var amount)
                    when amount != null && amount.signum() == 0 ->
                "ZERO " + id + ": " + name;

            case Order(var id, Customer(var cid, var name), var amount) ->
                "BAD_AMOUNT " + id + ": "
                        + (amount == null
                                ? "null" : amount.toPlainString());

            case Order(var id, var customer, var amount) ->
                "MISSING_CUSTOMER " + id;

            default -> "OTHER_TYPE";
        };
    }

    public static void main(String[] args) {
        Customer an = new Customer(" C-7 ", " An ");
        Order paid = new Order(
                " O-1 ", an, new BigDecimal("125000.00"));

        System.out.println(direct(paid));
        System.out.println(nested(paid));
        System.out.println(classify(paid));

        System.out.println(classify(
                new Order("O-2", an, BigDecimal.ZERO)));
        System.out.println(classify(
                new Order("O-3", an, new BigDecimal("-100"))));
        System.out.println(classify(
                new Order("O-4", an, null)));
        System.out.println(classify(
                new Order("O-5", null, BigDecimal.TEN)));
        System.out.println(nested(
                new Order("O-5", null, BigDecimal.TEN)));

        System.out.println(classify(null));
        System.out.println(classify("unknown"));

        System.out.println(
                new BigDecimal("10.0")
                        .compareTo(new BigDecimal("10.00")) == 0);
        System.out.println(
                new BigDecimal("10.0")
                        .equals(new BigDecimal("10.00")));

        try {
            new Customer("  ", "An");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "VALIDATION " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 21 -encoding UTF-8 CustomerAmountPatternDemo.java
java CustomerAmountPatternDemo
~~~

**Đầu ra chính xác:**

~~~text
Direct O-1: customer=C-7, amount=125000.00
Nested O-1: An (C-7), amount=125000.00
POSITIVE O-1: An / 125000.00
ZERO O-2: An
BAD_AMOUNT O-3: -100
BAD_AMOUNT O-4: null
MISSING_CUSTOMER O-5
Nested: không khớp
NULL_SELECTOR
OTHER_TYPE
true
false
VALIDATION id không được trống
~~~

### Đọc kết quả theo các đường đi

- **`Direct O-1`**: một record pattern `Order(var id, var customer, var amount)` ràng buộc cả customer và amount. `Order` có ba components nên cần đủ ba vị trí.
- **`Nested O-1`**: nested `Customer(var customerId, var name)` lấy thêm id/name trong chính pattern, còn `var amount` lấy BigDecimal của Order.
- **`POSITIVE`**: Customer present, amount dương, guard đúng.
- **`ZERO`**: Customer present, amount bằng 0, guard thứ nhất sai và thứ hai đúng.
- **`BAD_AMOUNT O-3/O-4`**: amount âm hoặc null; nested Customer vẫn khớp và guard không chọn nhánh dương/zero.
- **`MISSING_CUSTOMER`**: Customer component null, nested Customer không khớp; nhánh Order tổng quát vẫn khớp.
- **`Nested: không khớp`**: cùng đối tượng có Customer null sẽ làm `instanceof` với nested record pattern trả `false`.
- **`NULL_SELECTOR`**: nhờ `case null`, không ném NPE khi selector null.
- **`OTHER_TYPE`**: đầu vào là String, không phải Order.
- **`true/false`**: BigDecimal `compareTo` và `equals` cho kết quả khác nhau khi scale khác.
- **`VALIDATION`**: compact constructor của Customer từ chối id trống.

Không có tác vụ I/O ngoài `System.out.println`; chương trình không dùng database, HTTP hoặc framework để người học có thể tập trung vào cấu trúc pattern và điều kiện.

## 9. Khi nào chọn `if instanceof`, khi nào chọn `switch`?

### Chọn `if instanceof` khi chỉ cần trích một lần

~~~java
if (input instanceof Order(var id, var customer, var amount)) {
    // Cả customer và amount đã sẵn sàng trong nhánh.
}
~~~

Cách này ngắn, rõ cho một đường xử lý. Có thể thêm điều kiện sau phép match:

~~~java
if (input instanceof Order(var id, var customer, var amount)
        && customer != null && amount != null
        && amount.signum() > 0) {
    System.out.println(customer.name() + " / "
            + amount.toPlainString());
}
~~~

Toán tử `&&` short-circuit giúp chỉ gọi `customer.name()` và `amount.signum()` sau khi kiểm tra giá trị phù hợp. Lưu ý rằng null selector khiến `instanceof` false, không ném NPE từ phép kiểm tra này.

### Chọn `switch` khi cần phân loại nhiều tình huống

~~~java
return switch (value) {
    case null -> "NULL";
    case Order(var id, Customer(var cid, var name), var amount)
            when amount != null && amount.signum() > 0 ->
        "Khách " + name + " đã có amount dương";
    case Order(var id, var customer, var amount) ->
        "Đơn không đủ điều kiện";
    default -> "Kiểu khác";
};
~~~

`switch` giúp thấy rõ **thứ tự và phạm vi** các nhánh; đặc biệt hữu ích với record patterns lồng hoặc sealed hierarchy có nhiều subtype. Nhưng không cần ép một điều kiện `instanceof` đơn giản thành switch dài chỉ vì muốn dùng tính năng Java 21.

**Giới hạn của ví dụ:** không suy luận hiệu năng từ hình thức cú pháp. HotSpot có thể tối ưu cả hai, và việc chọn kiểu điều phối nên ưu tiên tính đúng/khả năng bảo trì; benchmark chỉ cần khi có yêu cầu hiệu năng cụ thể.

## 10. Nếu domain cấm thiếu `customer`/`amount`, validate tại constructor

Ở ví dụ mục 8, `Order` cố ý cho phép hai component tham chiếu null để kiểm tra các nhánh. Nếu một **domain Order hợp lệ** phải có khách hàng và amount dương, thiết kế kiểu nên bảo vệ invariant ngay khi tạo:

~~~java
record StrictOrder(String orderId,
                   Customer customer,
                   BigDecimal amount) {
    public StrictOrder {
        orderId = required(orderId, "orderId");
        java.util.Objects.requireNonNull(customer, "customer");
        java.util.Objects.requireNonNull(amount, "amount");
        if (amount.signum() <= 0)
            throw new IllegalArgumentException(
                    "amount phải dương");
    }
}
~~~

Nếu amount bằng 0 hợp lệ trong domain, đổi điều kiện thành `amount.signum() < 0`. Mục đích không phải cấm mọi giá trị null bằng mọi giá, mà là **đặt quy tắc ở đúng lớp dữ liệu**.

Hai cách tổ chức thông dụng:

1. **Input DTO có thể thiếu dữ liệu** (ví dụ JSON thô): chấp nhận nullable fields có chủ đích, validate/convert tại boundary và trả lỗi có cấu trúc.
2. **Domain record/value object đã được xác thực**: constructor bảo đảm invariant như non-null và positive amount; phần xử lý sau có thể dựa trên contract này.

Nếu `amount` xuất phát từ hệ thống bên ngoài, nên kiểm tra thêm currency, giới hạn số chữ số, scale, cách làm tròn và nguy cơ vượt giới hạn nghiệp vụ. Một `BigDecimal` đúng kiểu Java **không** tự bảo đảm nó là số tiền được phép.

**Không làm việc này:** âm thầm đổi null thành `BigDecimal.ZERO` nếu domain coi “thiếu amount” khác “số tiền 0”. Việc gán default làm mất thông tin về dữ liệu thiếu.

## 11. Lỗi compile-time dễ gặp khi lấy hai components

### 11.1. Sai số lượng component pattern

~~~java
record Purchase(Customer customer, BigDecimal amount) {}

// CỐ Ý SAI: Purchase có hai components nhưng chỉ có một pattern.
// if (value instanceof Purchase(var customer)) { ... }
~~~

Thông báo thường thuộc nhóm `incorrect number of nested patterns`. Phải cung cấp **hai vị trí**:

~~~java
if (value instanceof Purchase(var customer, var amount)) {
    // ...
}
~~~

Trong ví dụ hoàn chỉnh, `Order` có **ba** components (`orderId`, `customer`, `amount`), vì vậy phải có ba component patterns: `Order(var id, var customer, var amount)`. Không được lấy trực tiếp hai vị trí cuối bằng cách bỏ qua component đầu:

~~~java
// CỐ Ý SAI nếu Order có 3 components:
// Order(var customer, var amount)
~~~

Nếu không cần orderId, vẫn phải đặt pattern cho vị trí đó, ví dụ `Order(var ignoredId, var customer, var amount)`.

### 11.2. Nhầm kiểu của hai components

~~~java
// CỐ Ý SAI: customer được khai báo kiểu Customer, không phải String.
// if (value instanceof Purchase(String customer, BigDecimal amount)) { ... }
~~~

Record pattern phải tương thích với **kiểu tĩnh của từng component**; không thể kỳ vọng compiler tự chuyển `Customer` thành `String` chỉ vì đối tượng có thuộc tính name.

Sửa bằng `Purchase(Customer customer, BigDecimal amount)`, `Purchase(var customer, var amount)`, hoặc pattern lồng `Purchase(Customer(var id, var name), var amount)`.

### 11.3. Dùng record pattern với class thường

~~~java
class PlainPurchase {
    PlainPurchase(Customer customer, BigDecimal amount) {}
}

// CỐ Ý SAI: PlainPurchase không phải record.
// if (value instanceof PlainPurchase(var customer, var amount)) { ... }
~~~

Trong Java 21, **record pattern không phải constructor pattern tổng quát**. Class có constructor nhận hai tham số chưa đủ để `PlainPurchase(...)` là record pattern hợp lệ. Hãy dùng type pattern `PlainPurchase p` và accessor, hoặc chọn record khi đúng mô hình dữ liệu.

### 11.4. Nhầm `when` với cú pháp của `instanceof`

`when` là guard trong **case của pattern switch**. Trong `if`, nối điều kiện bằng `&&`:

~~~java
// ĐÚNG với instanceof:
if (input instanceof Purchase(var customer, var amount)
        && amount != null && amount.signum() > 0) {
    // ...
}
~~~

Không viết `input instanceof Purchase(...) when amount.signum() > 0` như trong nhãn case.

### 11.5. Case tổng quát che case chuyên biệt

~~~java
// CỐ Ý SAI VỀ THỨ TỰ, có thể bị báo dominated case:
// case Order(var id, var customer, var amount) -> "OTHER_ORDER";
// case Order(var id, Customer(var cid, var name), var amount)
//         when amount != null -> "HAS_CUSTOMER";
~~~

`case Order(...)` tổng quát đã khớp mọi Order hợp lệ không null, nên cần đưa case nested/guard chuyên biệt **lên trước**, case fallback sau cùng.

### 11.6. Chỉ có `default` không xử lý null selector

~~~java
// Runtime NPE nếu selector là null, dù có default:
// return switch (value) {
//     case Purchase(var customer, var amount) -> "Purchase";
//     default -> "Other";
// };
~~~

Thêm `case null` nếu null hợp lệ, hoặc từ chối null rõ ràng từ boundary. Không đánh đồng “switch exhaustive ở compile time” với “null-safe ở runtime”.

## 12. Ma trận test cho bài toán customer + amount

Để xác nhận một pattern lấy **đúng hai dữ liệu** và xử lý đủ trường hợp quan trọng:

| Input | Kỳ vọng | Điều chứng minh |
| --- | --- | --- |
| Purchase(Customer hợp lệ, amount dương) | Khớp, lấy customer và amount | Đúng hai vị trí component |
| Purchase(Customer hợp lệ, amount 0) | Khớp, chuyển nhánh zero | Guard dương false, zero true |
| Purchase(Customer hợp lệ, amount âm) | Khớp, xử lý số tiền không hợp lệ | Không bỏ sót guard false |
| Purchase(Customer hợp lệ, amount null) | `var amount` nhận null, không gọi `signum()` sai | Null component khác null selector |
| Purchase(null, amount dương) | Pattern trực tiếp khớp; nested Customer không khớp | Khác biệt giữa `var` và nested record pattern |
| Đầu vào `null` | `instanceof` false hoặc `case null` | Null selector được xử lý rõ |
| Đầu vào kiểu String | Không khớp Purchase | Type checking đúng |
| Customer id/name rỗng | Constructor chặn nếu domain yêu cầu | Invariant dữ liệu |
| BigDecimal `10.0` và `10.00` | `compareTo == 0`, `equals == false` | Không nhầm so sánh số và scale |

Khi code dùng guard như `amount != null && amount.signum() > 0`, test cần các ca amount null, dương, zero và âm. Không chỉ test **case đã chạy ít nhất một lần** mà bỏ qua các đường điều kiện khác.

Với đơn hàng tiền thật, bổ sung test về currency, precision/scale, rounding, số lớn, giới hạn amount và dữ liệu từ serializer. Cấu trúc record pattern có thể đúng trong khi business rule về tiền vẫn sai.

## 13. Ví dụ JUnit 5: kiểm tra phép tách thay vì chỉ in console

Nếu đưa chương trình mục 8 vào một project có JUnit 5, có thể kiểm tra kết quả bằng assertion. Đây là **đoạn test dùng các kiểu lồng trong `CustomerAmountPatternDemo`**, không phải một file có thể chạy độc lập nếu thiếu dependency JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class CustomerAmountPatternDemoTest {
    @Test
    void extractsCustomerAndAmountTogether() {
        var customer =
                new CustomerAmountPatternDemo.Customer("C-7", "An");
        var order = new CustomerAmountPatternDemo.Order(
                "O-1", customer, new BigDecimal("125000.00"));

        assertEquals(
                "Direct O-1: customer=C-7, amount=125000.00",
                CustomerAmountPatternDemo.direct(order));
        assertEquals(
                "Nested O-1: An (C-7), amount=125000.00",
                CustomerAmountPatternDemo.nested(order));
    }

    @Test
    void differentiatesMissingCustomerFromNullAmount() {
        var customer =
                new CustomerAmountPatternDemo.Customer("C-7", "An");

        assertEquals("BAD_AMOUNT O-4: null",
                CustomerAmountPatternDemo.classify(
                    new CustomerAmountPatternDemo.Order(
                        "O-4", customer, null)));

        assertEquals("MISSING_CUSTOMER O-5",
                CustomerAmountPatternDemo.classify(
                    new CustomerAmountPatternDemo.Order(
                        "O-5", null, BigDecimal.TEN)));
    }

    @Test
    void rejectsInvalidCustomer() {
        assertThrows(IllegalArgumentException.class,
                () -> new CustomerAmountPatternDemo.Customer(
                        " ", "An"));
    }
}
~~~

Với kiểu `Customer` và `Order` lồng được khai báo không có modifier `private` trong ví dụ, test cùng package có thể tham chiếu như trên. Project thực tế nên có package rõ ràng và cấu hình Maven/Gradle/JUnit đúng phiên bản.

**Điểm kiểm thử:** kết quả trích `customer` và `amount` là dữ liệu cụ thể được assert, không chỉ kiểm tra một nhánh `case` được gọi. Test cũng tách hai lý do khác nhau dẫn đến fallback: **customer null** và **amount null**.

## 14. Code review checklist cho một record pattern có nhiều component

- [ ] Record khai báo đúng component **và đúng thứ tự**.
- [ ] Một pattern chứa **đủ số vị trí**: `Purchase(var customer, var amount)` có hai; `Order(var id, var customer, var amount)` có ba.
- [ ] `var` được hiểu là kiểu tĩnh suy luận, không coi dữ liệu tự động non-null.
- [ ] Với nested `Customer(...)`, đã xét trường hợp component Customer null chưa?
- [ ] Nếu amount null được phép, mọi lệnh `amount.signum()`, `compareTo()`, `toPlainString()` đều được bảo vệ ở đường tương ứng.
- [ ] Khi dùng `switch`, case có guard cụ thể đứng trước case chung, tránh dominance.
- [ ] Selector null có chính sách `case null` hoặc contract từ chối null rõ ràng.
- [ ] `BigDecimal` được khởi tạo/so sánh đúng mục đích; không dùng `==` để so sánh giá trị số.
- [ ] Domain order có invariant nào phải kiểm tra ngay khi tạo? Có đang lẫn DTO nullable với domain record hợp lệ?
- [ ] Test đã kiểm tra giá trị thực tế của **customer và amount**, guard true/false và các trường hợp null?
- [ ] Nếu schema record đổi, những record patterns khác có phải cập nhật component arity không?

Đây là checklist review theo **tính đúng của chương trình và hợp đồng dữ liệu**, không phải tiêu chuẩn ép tất cả code thành nested pattern nhiều cấp.

## 15. Bài tập tự luyện

**Bài 1 — Trích hai component.** Tạo `record Invoice(Customer customer, BigDecimal amount) {}`. Viết một `if instanceof` duy nhất lấy cả `customer` và `amount`, in `customer.id()` và amount khi cả hai khác null.

**Bài 2 — Nested customer.** Với `record Customer(String id, String name) {}`, thay `Invoice(var customer, var amount)` thành một pattern trích trực tiếp `name` và `amount`. Nếu Customer null thì pattern có khớp không?

**Bài 3 — Thứ tự.** Vì sao `record Invoice(Customer customer, BigDecimal amount)` không cho dùng `Invoice(var amount, var customer)` để đổi thứ tự giá trị, dù tên biến hợp lệ?

**Bài 4 — Guard.** Viết `switch` có các nhánh: null selector, amount dương, amount không dương/thiếu và kiểu khác. Guard cần kiểm tra điều gì trước khi gọi `signum()`?

**Bài 5 — BigDecimal.** Hai đối tượng `new BigDecimal("5.0")` và `new BigDecimal("5.00")` khác nhau về `equals` nhưng bằng nhau về `compareTo`. Tại sao đó là một tình huống cần cân nhắc nếu record `Invoice` dùng `equals()` cho logic nghiệp vụ?

**Bài 6 — Siết invariant.** Thiết kế compact constructor của một record domain `Invoice` để từ chối null customer, null amount và amount âm. Giữ amount = 0 hợp lệ. Tại sao DTO nhận JSON từ ngoài vẫn cần xử lý lỗi schema trước hoặc khi tạo record domain?

### Gợi ý đáp án

~~~java
// Bài 1:
if (value instanceof Invoice(var customer, var amount)
        && customer != null && amount != null) {
    System.out.println(customer.id() + " / "
            + amount.toPlainString());
}

// Bài 2:
if (value instanceof Invoice(
        Customer(var id, var name), var amount)) {
    System.out.println(name + " / " + amount);
}

// Bài 6, phác thảo constructor cho record Invoice:
record Invoice(Customer customer, BigDecimal amount) {
    public Invoice {
        java.util.Objects.requireNonNull(customer, "customer");
        java.util.Objects.requireNonNull(amount, "amount");
        if (amount.signum() < 0)
            throw new IllegalArgumentException("amount phải >= 0");
    }
}
~~~

- Bài 2: nested `Customer(...)` **không khớp** khi component Customer null; dùng case fallback hoặc validation nếu cần.
- Bài 3: pattern ghép **vị trí**, không phải hoán đổi dựa trên tên biến. Đổi tên chỉ đổi nhãn của giá trị nhận được; với những kiểu khác nhau, việc dùng tiếp có thể gây lỗi compile time.
- Bài 4: `amount != null && amount.signum() > 0`; nếu thiếu kiểm tra null, guard có thể ném NPE.
- Bài 5: `record.equals` dựa trên `BigDecimal.equals` của component, nên không được dùng `equals` như một chính sách so sánh tiền theo giá trị số nếu không chuẩn hóa scale/hợp đồng.
- Bài 6: DTO có thể chứa dữ liệu thiếu/sai định dạng; việc chuyển sang domain record cần validation có chủ đích và phản hồi lỗi rõ ràng.

## 16. Tổng kết

Để **lấy `customer` và `amount` trong một pattern** ở Java 21:

1. Khai báo record theo cấu trúc dữ liệu: `record Purchase(Customer customer, BigDecimal amount) {}`.
2. Dùng một record pattern: `input instanceof Purchase(var customer, var amount)`.
3. Nếu cần thông tin bên trong Customer, dùng nested: `Purchase(Customer(var id, var name), var amount)`.
4. Khi có nhiều quy tắc theo amount, kết hợp `case` và `when` nhưng luôn kiểm tra null trước khi gọi phương thức trên `amount`.
5. Phân biệt `null` selector, `null` customer component và `null` amount component: chúng có cách match khác nhau.
6. Dùng `BigDecimal.compareTo`/`signum` để so sánh giá trị số; không nhầm với `equals` xét scale.
7. Đặt invariant thích hợp vào constructor/domain boundary, còn record pattern chỉ có trách nhiệm **kiểm tra cấu trúc và trích giá trị**, không thay thế validation nghiệp vụ.

### Tài liệu tham khảo

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record deconstruction, nested component patterns và suy luận kiểu (Java 21).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): `switch`, guard `when`, case order và null semantics.
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): ví dụ và cú pháp áp dụng.
- [JLS Java SE 21 `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): quy tắc về type/record patterns và matching.
- [Java SE 21 API — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): `compareTo`, `equals`, `signum` và scale.
