# Kiểm tra điều kiện bằng `when` trong record pattern (Java 21)

## 1. Bài toán: record match đúng kiểu nhưng chưa chắc đủ điều kiện

Giả sử một hệ thống xử lý đơn hàng cần phân loại đầu vào thành: **được duyệt**, **chờ thanh toán**, **chưa đủ tuổi**, **cần xem xét thủ công**, **thiếu cấu trúc dữ liệu**, **đầu vào null** hoặc **không hỗ trợ**. Dữ liệu được truyền dưới dạng các `record` lồng nhau: `Purchase` có `Customer` và `Money`.

Kiểm tra kiểu đơn thuần chưa giải quyết hết yêu cầu: một đối tượng `Purchase` vẫn có thể có `Customer` chưa xác minh, số tiền bằng 0, mã tiền tệ sai hoặc chưa thanh toán. Java 21 giải quyết việc phân loại theo **cấu trúc + điều kiện** bằng một nhãn `case` có **record pattern** và **guard `when`**.

Ví dụ thu gọn:

```java
case Purchase(var orderId,
              Customer(var id, var age, var verified),
              Money(var currency, var amount), var paid)
        when eligible(orderId, id, age, verified,
                      currency, amount, paid) ->
        "APPROVED:" + orderId;
```

Trong đó:

- `Purchase(...)` kiểm tra object ngoài và bind các component.
- `Customer(...)` và `Money(...)` là các **record patterns lồng nhau**, bắt buộc component tương ứng là record phù hợp, không phải `null`.
- `var orderId`, `var age`, `var amount`, `var paid`... khai báo các **biến pattern**, có scope hợp lệ trong `when` và thân nhánh đó.
- `eligible(...)` là một hàm kiểm tra quy tắc nghiệp vụ và trả `boolean`. Guard chỉ được gọi **sau khi** cả nested record pattern đã match.
- Nếu pattern match nhưng `eligible(...) == false`, Java thử nhánh kế tiếp, không tự nhảy ngay vào `default`.

**Mục tiêu sau bài:** tự thiết kế guard an toàn với `null`, bảo toàn thứ tự ưu tiên, dùng `BigDecimal` cho số tiền, viết chương trình Java 21 chạy được, test tình huống biên/ngoại lệ và hiểu lỗi dominance ở compile time.

**Yêu cầu phiên bản:** Record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) trở thành tính năng chuẩn từ **Java 21**. Với JDK 21+ có thể dùng `javac --release 21`; không cần `--enable-preview`. Mẫu `instanceof Type variable` đơn giản đã chuẩn từ Java 16, nhưng `when` trong pattern switch là cú pháp Java 21.

## 2. Cơ chế chính xác của nhãn `case Pattern when Expression`

Nhãn guarded pattern có dạng:

```java
case SomeRecord(var x, var y) when predicate(x, y) -> result;
```

Đoạn trên là **cú pháp minh họa** trong một `switch` expression, giả định `SomeRecord` tồn tại và `predicate` trả `boolean`.

Khi `switch` xét một nhãn guarded pattern, trình tự logic là:

1. Kiểm tra selector có thể match pattern của nhãn `case` hay không.
2. Với record pattern, deconstruct record bằng accessor và tiếp tục match các component/nested patterns. Nếu một nested record pattern không match, **guard của case đó không chạy**.
3. Khi pattern match, các biến `x`, `y` đã được bind; Java tính biểu thức sau `when`.
4. Nếu biểu thức trả `true`, case được chọn, thân nhánh thực thi và switch expression có kết quả.
5. Nếu biểu thức trả `false`, switch tiếp tục tìm nhãn phù hợp khác theo thứ tự; nhánh sau có thể là một record pattern giống nhau nhưng không guard.
6. Nếu biểu thức guard **ném exception**, việc chọn nhánh kết thúc bất thường với exception đó; Java **không** xem exception như `false` để rơi vào fallback.

Hãy phân biệt ba trạng thái:

| Trạng thái | Ví dụ | Hậu quả |
| --- | --- | --- |
| Pattern không match | `Purchase.customer == null` nhưng nhãn đòi `Customer(...)` | Bỏ qua guard, thử case sau |
| Pattern match, guard sai | `paid == false` nhưng nhãn cần `eligible(...) == true` | Guard chạy, trả `false`, thử case sau |
| Pattern match, guard ném lỗi | `when text.length() > 0` với `text == null` | Ném `NullPointerException`; không đi vào case sau |

Đây là khác biệt trọng yếu khi test record patterns: **chọn đúng case** chưa đủ, phải biết guard có được đánh giá hay không và có gây side effects/exception không.

### 2.1. `when` gắn với pattern, không phải nhãn hằng thông thường

Cú pháp chuẩn cần nhớ:

```java
case String s when s.length() >= 3 -> "long enough";
case String s -> "short";
```

Không dùng cú pháp preview cũ `case String s && s.length() >= 3` trong dự án Java 21. Với `instanceof`, không viết `instanceof String s when ...`; hãy dùng `instanceof String s && ...`.

## 3. Thiết kế mô hình record cho case study

Bộ ví dụ dùng các record sau:

```java
record Customer(String id, int age, boolean verified) {}
record Money(String currency, BigDecimal amount) {}
record Purchase(String orderId, Customer customer,
                Money total, boolean paid) {}
```

Với các khai báo này, cần import `java.math.BigDecimal`. Trong chương trình hoàn chỉnh ở mục 8, các record được đặt bên trong class `RecordWhenCaseStudy`.

| Record / component | Ý nghĩa trong bài | Cần chú ý |
| --- | --- | --- |
| `Customer.id` | Mã khách hàng | Có thể `null` hoặc blank; phải kiểm tra |
| `Customer.age` | Tuổi | `int` không null; 18 là ngưỡng minh họa |
| `Customer.verified` | Đã xác minh | `boolean`; không phải phép xác minh tài khoản thật |
| `Money.currency` | Đơn vị tiền tệ | Ví dụ chỉ chấp nhận chuỗi `"VND"` chính xác |
| `Money.amount` | Giá trị tiền | `BigDecimal` có thể `null`; yêu cầu dương và không quá giới hạn |
| `Purchase.orderId` | Mã đơn hàng | Bắt buộc nonblank trong điều kiện duyệt |
| `Purchase.paid` | Đã thanh toán | Nếu sai, phân loại chờ thanh toán theo ưu tiên |
| `Purchase.customer/total` | Hai record lồng nhau | Có thể bằng `null`; nested record pattern khi đó thất bại |

**Giới hạn miền dữ liệu:** Đây là case study để học `when` và pattern matching. Nó **không** thực hiện thanh toán, không cấp quyền truy cập, không truy vấn hệ thống khách hàng và không phải chính sách tài chính. Các ngưỡng/điều kiện được chọn để có test rõ ràng.

### 3.1. Vì sao `BigDecimal` cho tiền?

Nếu dùng `double` cho số tiền, các phép biểu diễn thập phân như `0.1` có thể có sai số nhị phân. Trong ví dụ, `BigDecimal` cho phép so sánh theo giá trị thập phân bằng `compareTo(...)`:

```java
private static final BigDecimal LIMIT = new BigDecimal("5000000");

// Chỉ chấp nhận amount > 0 và amount <= LIMIT:
amount != null && amount.signum() > 0
        && amount.compareTo(LIMIT) <= 0
```

Đây là fragment trong class đã import `BigDecimal`. Khi so **giá trị** BigDecimal, `compareTo` thường phù hợp hơn `equals` vì `BigDecimal("1.0")` và `BigDecimal("1.00")` so bằng 0 qua `compareTo`, nhưng không `equals` do scale khác nhau. Tuy vậy, nếu scale là một phần hợp đồng, việc chọn phép so phải phản ánh yêu cầu đó.

## 4. Tách điều kiện dài thành một predicate rõ nghĩa

### 4.1. Guard inline có thể khó review

Có thể viết:

```java
case Purchase(var orderId,
              Customer(var id, var age, var verified),
              Money(var currency, var amount), var paid)
        when orderId != null && !orderId.isBlank()
                && id != null && !id.isBlank()
                && age >= 18 && verified
                && "VND".equals(currency)
                && amount != null && amount.signum() > 0
                && amount.compareTo(LIMIT) <= 0 && paid ->
        "APPROVED:" + orderId;
```

Cú pháp này hợp lệ khi đặt trong switch có đúng record/helpers. Nhưng nhãn `case` chứa nhiều điều kiện chi tiết khiến ý nghĩa "**đủ điều kiện duyệt**" khó nhìn thấy. Khi các điều kiện còn được unit test riêng, nên trích xuất thành một hàm boolean có tên mang ý nghĩa nghiệp vụ.

### 4.2. Hàm `eligible(...)` an toàn

```java
static boolean eligible(String orderId, String id, int age,
                        boolean verified, String currency,
                        BigDecimal amount, boolean paid) {
    return orderId != null && !orderId.isBlank()
            && id != null && !id.isBlank()
            && age >= 18 && verified
            && "VND".equals(currency)
            && amount != null && amount.signum() > 0
            && amount.compareTo(LIMIT) <= 0
            && paid;
}
```

Đây là helper trong class đã khai báo `LIMIT` và import `BigDecimal`. Từng yếu tố có vai trò:

- Kiểm tra `orderId != null` **trước** khi gọi `isBlank()`.
- Kiểm tra `id != null` trước thao tác tương tự.
- Điều kiện `age >= 18` và `verified` không phụ thuộc tham chiếu nullable.
- Viết `"VND".equals(currency)` để xử lý `currency == null` an toàn.
- Kiểm tra `amount != null` trước `signum()`/`compareTo()`.
- `&&` là toán tử **short-circuit**: khi một vế sai, các vế sau không được đánh giá.
- Hàm chỉ trả `boolean`, không ghi DB hay làm nghiệp vụ ngoài ý định.

Trong đoạn cuối, `paid` là một điều kiện để duyệt, không phải lời gọi thực hiện thanh toán.

### 4.3. Khi nào nên nhận cả record?

Cũng có thể viết:

```java
static boolean eligible(Purchase p) {
    return p.orderId() != null && !p.orderId().isBlank()
            && p.customer() != null
            && p.customer().id() != null
            && p.total() != null;
}
```

Đây là **một helper rút gọn minh họa chữ ký**, không thay thế công thức `eligible(...)` đầy đủ trong chương trình chính. Cách nhận record gọn hơn khi cần nhiều component, nhưng có thể đọc accessor nhiều lần và cần xử lý các record lồng nhau null. Việc chuyển từ nested record deconstruction sang `case Purchase p when eligible(p)` có thể đổi số lần/thứ tự gọi accessor nếu record override getter.

Trong một refactor chỉ nhằm cải thiện readability, hãy giữ cấu trúc pattern hiện có và chuyển **nguyên biểu thức điều kiện** vào helper; đừng đồng thời thay đổi cách deconstruct và logic nghiệp vụ nếu không có test tương đương.

## 5. Đặt thứ tự nhánh đúng với ưu tiên nghiệp vụ

Ta định nghĩa thứ tự ra quyết định như sau:

1. Nếu đủ mọi điều kiện, trả `APPROVED:<orderId>`.
2. Nếu cấu trúc record lồng nhau có đủ nhưng `paid == false`, trả `AWAIT_PAYMENT`.
3. Nếu chưa rơi vào nhánh trước và `age < 18`, trả `UNDERAGE`.
4. Những `Purchase` có đủ record nested nhưng điều kiện khác không đạt, trả `MANUAL_REVIEW`.
5. Những `Purchase` thiếu `Customer` hoặc `Money` record, trả `MISSING_DETAILS`.
6. Selector `null` trả `NULL_INPUT`.
7. Các loại object khác `Purchase` trả `UNSUPPORTED`.

Đây là **thứ tự ưu tiên có chủ đích của ví dụ**, không phải một danh sách kết quả được compiler tự suy ra.

```java
static String decide(Object input) {
    return switch (input) {
        case Purchase(var orderId,
                      Customer(var id, var age, var verified),
                      Money(var currency, var amount), var paid)
                when eligible(orderId, id, age, verified,
                              currency, amount, paid) ->
                "APPROVED:" + orderId;

        case Purchase(var orderId,
                      Customer(var id, var age, var verified),
                      Money(var currency, var amount), var paid)
                when !paid -> "AWAIT_PAYMENT";

        case Purchase(var orderId,
                      Customer(var id, var age, var verified),
                      Money(var currency, var amount), var paid)
                when age < 18 -> "UNDERAGE";

        case Purchase(var orderId,
                      Customer(var id, var age, var verified),
                      Money(var currency, var amount), var paid) ->
                "MANUAL_REVIEW";

        case Purchase p -> "MISSING_DETAILS";
        case null -> "NULL_INPUT";
        default -> "UNSUPPORTED";
    };
}
```

**Giải thích chính xác:** Nếu một khách hàng 17 tuổi **chưa thanh toán**, nhánh đầu trả `false`, nhánh `when !paid` ở vị trí thứ hai được chọn, kết quả là **`AWAIT_PAYMENT`**, không phải `UNDERAGE`. Nếu muốn ưu tiên độ tuổi cao hơn trạng thái thanh toán, phải **đổi thứ tự hai guard** và cập nhật test; đó là thay đổi nghiệp vụ.

### 5.1. Tại sao cần một nhánh cùng record nhưng không có guard?

Nhánh:

```java
case Purchase(var orderId,
              Customer(var id, var age, var verified),
              Money(var currency, var amount), var paid) ->
        "MANUAL_REVIEW";
```

đứng **sau** các nhánh có guard. Nó là fallback cho những đơn hàng có đủ record nested nhưng thất bại ở tất cả điều kiện đặc biệt. Nếu đặt nhánh này lên trên, các nhánh có guard cùng cấu trúc phía sau sẽ bị **dominated**, compiler có thể từ chối.

### 5.2. Pattern match không đồng nghĩa dữ liệu hợp lệ

Record cho phép tạo `Customer(null, 20, true)` và `Money(null, null)`. `Customer(var id, ...)` và `Money(var currency, var amount)` vẫn có thể match record object **non-null** rồi bind các component **null**. Vì vậy `eligible(...)` bắt buộc chịu trách nhiệm xác thực các giá trị.

Ngược lại, nếu `Purchase.customer() == null`, nested **record pattern** `Customer(...)` không match và guard không chạy. Khi đó `case Purchase p` phía sau xử lý, trả `MISSING_DETAILS`.

## 6. Bộ ca kiểm thử phải phân biệt pattern thất bại và guard sai

Ma trận dưới là hợp đồng của ví dụ, trước khi nhìn vào chương trình.

| Input đại diện | Pattern nested | Guard / ưu tiên | Kết quả |
| --- | --- | --- | --- |
| Tuổi 20, verified, VND 5.000.000, paid | Match | `eligible=true` | `APPROVED:O1` |
| Tuổi 18, VND 100, paid | Match | Ranh giới tuổi đủ điều kiện | `APPROVED:O2` |
| Tổng 5.000.001 | Match | Vượt hạn mức | `MANUAL_REVIEW` |
| Chưa thanh toán, tuổi 20 | Match | `!paid=true` | `AWAIT_PAYMENT` |
| Chưa thanh toán, tuổi 17 | Match | `!paid` đứng trước guard tuổi | `AWAIT_PAYMENT` |
| Đã thanh toán, tuổi 17 | Match | `age<18` | `UNDERAGE` |
| ID blank/null | Match | Helper chặn null/blank | `MANUAL_REVIEW` |
| `verified=false` | Match | Không đủ điều kiện duyệt | `MANUAL_REVIEW` |
| `orderId=null` hoặc blank | Match | Không đủ điều kiện duyệt | `MANUAL_REVIEW` |
| `currency=null` hoặc `"USD"` | Match | Không phải `"VND"` | `MANUAL_REVIEW` |
| `amount=null`, 0 hoặc âm | Match | Không dương / không có giá trị | `MANUAL_REVIEW` |
| `customer=null` | **Không match** nested `Customer(...)` | Guard không chạy | `MISSING_DETAILS` |
| `total=null` | **Không match** nested `Money(...)` | Guard không chạy | `MISSING_DETAILS` |
| Selector `null` | Không match `Purchase(...)` | `case null` | `NULL_INPUT` |
| Selector `Integer` | Không match `Purchase(...)` | `default` | `UNSUPPORTED` |

Hai trường hợp `amount=null` và `total=null` **không giống nhau**:

- `total=null`: không có đối tượng `Money` để deconstruct, nên record pattern nested không match.
- `new Money("VND",null)`: có record `Money`, `var amount` bind `null`, helper trả `false`.

Tương tự với `customer=null` so với `new Customer(null,20,true)`. Đây là lý do test không nên chỉ gộp mọi loại `null` vào một kết quả chung.

## 7. Guard và `instanceof`: cùng ý tưởng, cú pháp khác

Một kiểm tra cấu trúc + điều kiện có thể viết bằng `instanceof` với toán tử `&&`:

```java
static boolean matchingAndEligible(Object input) {
    return input instanceof Purchase(
            var orderId,
            Customer(var id, var age, var verified),
            Money(var currency, var amount), var paid)
            && eligible(orderId, id, age, verified,
                        currency, amount, paid);
}
```

Trong ví dụ này:

1. Java thử nested record pattern ở vế trái của `&&`.
2. Nếu pattern không match, `eligible(...)` **không được gọi**.
3. Nếu match, pattern variables được bind và có scope hợp lệ ở vế phải, nơi helper được gọi.
4. Biểu thức kết quả là một `boolean`; không cần `switch` khi chỉ hỏi một câu đúng/sai.

**Không viết:**

```java
// CỐ Ý SAI: when không phải cú pháp cho instanceof.
if (input instanceof Purchase p when eligible(p)) {
    // ...
}
```

Đoạn này còn giả định có hàm `eligible(Purchase)` chưa được định nghĩa trong ví dụ runnable; điều quan trọng là **sau `instanceof` sử dụng `&&`, không sử dụng `when`**.

### Khi nào nên chọn cách nào?

- **Chỉ cần xác nhận đúng/sai:** `instanceof ... && predicate(...)` thường gọn hơn.
- **Cần phân loại nhiều trường hợp và ưu tiên nhiều guard:** `switch` với các `case ... when ...` rõ hơn.
- **Chỉ kiểm tra kiểu ngoài:** `instanceof Purchase p` hoặc `case Purchase p` là đủ, không nên deconstruct mọi component nếu không cần.
- **Dữ liệu có custom accessor/side effect:** phải đánh giá chi phí và thứ tự accessor trước khi refactor từ type-only sang nested record pattern.

## 8. Chương trình Java 21 hoàn chỉnh: `RecordWhenCaseStudy.java`

Chương trình sau **chạy độc lập bằng JDK 21**, không cần Maven/JUnit. Nó dùng 20 ca phân loại, hai phép so `instanceof`, bộ đếm chứng minh thời điểm chạy guard, và một ca guard cố ý ném `NullPointerException` để minh họa việc exception không trở thành `false`.

Tạo đúng file **`RecordWhenCaseStudy.java`**:

```java
import java.math.BigDecimal;
import java.util.Objects;

public class RecordWhenCaseStudy {
    record Customer(String id, int age, boolean verified) {}
    record Money(String currency, BigDecimal amount) {}
    record Purchase(String orderId, Customer customer,
                    Money total, boolean paid) {}
    record Probe(String text) {}

    static final BigDecimal LIMIT = new BigDecimal("5000000");
    static int tests;
    static int guardProbes;

    static boolean eligible(String orderId, String id, int age,
                            boolean verified, String currency,
                            BigDecimal amount, boolean paid) {
        return orderId != null && !orderId.isBlank()
                && id != null && !id.isBlank()
                && age >= 18 && verified
                && "VND".equals(currency)
                && amount != null && amount.signum() > 0
                && amount.compareTo(LIMIT) <= 0
                && paid;
    }

    static String decide(Object input) {
        return switch (input) {
            case Purchase(var orderId,
                          Customer(var id, var age, var verified),
                          Money(var currency, var amount), var paid)
                    when eligible(orderId, id, age, verified,
                                  currency, amount, paid) ->
                    "APPROVED:" + orderId;
            case Purchase(var orderId,
                          Customer(var id, var age, var verified),
                          Money(var currency, var amount), var paid)
                    when !paid -> "AWAIT_PAYMENT";
            case Purchase(var orderId,
                          Customer(var id, var age, var verified),
                          Money(var currency, var amount), var paid)
                    when age < 18 -> "UNDERAGE";
            case Purchase(var orderId,
                          Customer(var id, var age, var verified),
                          Money(var currency, var amount), var paid) ->
                    "MANUAL_REVIEW";
            case Purchase p -> "MISSING_DETAILS";
            case null -> "NULL_INPUT";
            default -> "UNSUPPORTED";
        };
    }

    static boolean paidProbe(boolean paid) {
        guardProbes++;
        return paid;
    }

    static String traced(Object input) {
        return switch (input) {
            case Purchase(var orderId,
                          Customer(var id, var age, var verified),
                          Money(var currency, var amount), var paid)
                    when paidProbe(paid) -> "PAID";
            case Purchase p -> "OTHER_PURCHASE";
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    static String inspect(Object input) {
        return switch (input) {
            case Probe(var text) when text.length() > 0 -> "NONEMPTY";
            case Probe p -> "EMPTY";
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    static boolean matchingAndEligible(Object input) {
        return input instanceof Purchase(
                var orderId, Customer(var id, var age, var verified),
                Money(var currency, var amount), var paid)
                && eligible(orderId, id, age, verified,
                            currency, amount, paid);
    }

    static Purchase purchase(String orderId, String id, int age,
                             boolean verified, String currency,
                             String amount, boolean paid) {
        return new Purchase(
                orderId, new Customer(id, age, verified),
                new Money(currency, amount == null
                        ? null : new BigDecimal(amount)), paid);
    }

    static void check(String name, Object value, String expected) {
        String actual = decide(value);
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError(name + ": expected=" + expected
                    + ", got=" + actual);
        }
        tests++;
        System.out.println(name + " => " + actual);
    }

    public static void main(String[] args) {
        check("at-limit",
                purchase("O1","C1",20,true,"VND","5000000",true),
                "APPROVED:O1");
        check("below-limit",
                purchase("O2","C2",18,true,"VND","100",true),
                "APPROVED:O2");
        check("over-limit",
                purchase("O3","C3",20,true,"VND","5000001",true),
                "MANUAL_REVIEW");
        check("unpaid",
                purchase("O4","C4",20,true,"VND","100",false),
                "AWAIT_PAYMENT");
        check("minor-unpaid",
                purchase("O5","C5",17,true,"VND","100",false),
                "AWAIT_PAYMENT");
        check("minor-paid",
                purchase("O6","C6",17,true,"VND","100",true),
                "UNDERAGE");
        check("blank-id",
                purchase("O7"," ",20,true,"VND","100",true),
                "MANUAL_REVIEW");
        check("null-id",
                purchase("O8",null,20,true,"VND","100",true),
                "MANUAL_REVIEW");
        check("unverified",
                purchase("O9","C9",20,false,"VND","100",true),
                "MANUAL_REVIEW");
        check("null-order-id",
                purchase(null,"C10",20,true,"VND","100",true),
                "MANUAL_REVIEW");
        check("blank-order-id",
                purchase(" ","C11",20,true,"VND","100",true),
                "MANUAL_REVIEW");
        check("null-currency",
                purchase("O12","C12",20,true,null,"100",true),
                "MANUAL_REVIEW");
        check("other-currency",
                purchase("O13","C13",20,true,"USD","100",true),
                "MANUAL_REVIEW");
        check("null-amount",
                purchase("O14","C14",20,true,"VND",null,true),
                "MANUAL_REVIEW");
        check("zero-amount",
                purchase("O15","C15",20,true,"VND","0",true),
                "MANUAL_REVIEW");
        check("negative-amount",
                purchase("O16","C16",20,true,"VND","-1",true),
                "MANUAL_REVIEW");
        check("null-customer",
                new Purchase("O17",null,new Money("VND",BigDecimal.ONE),true),
                "MISSING_DETAILS");
        check("null-money",
                new Purchase("O18",new Customer("C18",20,true),null,true),
                "MISSING_DETAILS");
        check("null-selector", null, "NULL_INPUT");
        check("other-type", 42, "UNSUPPORTED");
        System.out.println("DECISION CASES PASS: " + tests);

        Purchase approved = purchase(
                "O19","C19",20,true,"VND","15",true);
        if (!matchingAndEligible(approved)
                || matchingAndEligible(
                    new Purchase("O20",null,approved.total(),true))) {
            throw new AssertionError("instanceof guard parity");
        }
        System.out.println("INSTANCEOF CHECKS PASS: 2");

        String noNested = traced(
                new Purchase("O21",null,approved.total(),true));
        String notPaid = traced(
                purchase("O22","C22",20,true,"VND","100",false));
        String isPaid = traced(approved);
        if (!noNested.equals("OTHER_PURCHASE")
                || !notPaid.equals("OTHER_PURCHASE")
                || !isPaid.equals("PAID")
                || guardProbes != 2) {
            throw new AssertionError("guard timing");
        }
        System.out.println("GUARD PROBES PASS: " + guardProbes);

        try {
            inspect(new Probe(null));
            throw new AssertionError("expected NullPointerException");
        } catch (NullPointerException ex) {
            System.out.println("UNSAFE GUARD => NullPointerException");
        }
        System.out.println("ALL CHECKS PASSED");
    }
}
```

### 8.1. Biên dịch và chạy

Dùng JDK 21+:

```bash
javac --release 21 RecordWhenCaseStudy.java
java RecordWhenCaseStudy
```

**Stdout chính xác đã kiểm thử:**

```text
at-limit => APPROVED:O1
below-limit => APPROVED:O2
over-limit => MANUAL_REVIEW
unpaid => AWAIT_PAYMENT
minor-unpaid => AWAIT_PAYMENT
minor-paid => UNDERAGE
blank-id => MANUAL_REVIEW
null-id => MANUAL_REVIEW
unverified => MANUAL_REVIEW
null-order-id => MANUAL_REVIEW
blank-order-id => MANUAL_REVIEW
null-currency => MANUAL_REVIEW
other-currency => MANUAL_REVIEW
null-amount => MANUAL_REVIEW
zero-amount => MANUAL_REVIEW
negative-amount => MANUAL_REVIEW
null-customer => MISSING_DETAILS
null-money => MISSING_DETAILS
null-selector => NULL_INPUT
other-type => UNSUPPORTED
DECISION CASES PASS: 20
INSTANCEOF CHECKS PASS: 2
GUARD PROBES PASS: 2
UNSAFE GUARD => NullPointerException
ALL CHECKS PASSED
```

Chương trình dùng kiểm tra `if (...) throw new AssertionError(...)` để mọi phép đối chiếu chạy ngay cả khi JVM không có cờ `-ea`. Thông báo cuối xuất hiện **chỉ khi** tất cả kiểm tra dự kiến hoàn thành.

### 8.2. Cách đọc các kết quả đặc biệt

- **`at-limit`** và **`below-limit`** chứng minh `amount.compareTo(LIMIT) <= 0` bao gồm chính giới hạn; người 18 tuổi cũng vượt qua điều kiện `age >= 18`.
- **`minor-unpaid`** trả `AWAIT_PAYMENT` vì guard `!paid` đứng trước guard `age < 18`.
- **`null-id`, `null-amount`** được xử lý ở nhánh `MANUAL_REVIEW`, vì record nested vẫn match và helper xử lý component null an toàn.
- **`null-customer` và `null-money`** trả `MISSING_DETAILS` vì nested record pattern không match.
- **`INSTANCEOF CHECKS PASS: 2` chứng minh pattern + `&& eligible(...)` đúng trên một input hợp lệ và một input thiếu nested customer; nó không đánh đồng cú pháp `when` và `instanceof`.
- **`GUARD PROBES PASS: 2` là điểm mấu chốt: ta gọi `traced(...)` ba lần, nhưng `paidProbe(...)` chỉ chạy hai lần. Trường hợp `Customer==null` không đi tới guard, còn hai Purchase có nested records thì có chạy guard, kể cả khi kết quả `false`.
- **`UNSAFE GUARD => NullPointerException` là kiểm chứng có chủ đích cho một `Probe(var text)` với `text==null`. Guard ném exception; Java không tự chuyển exception thành `false`.

Chương trình không đo hiệu năng, không kết nối dịch vụ và không thực hiện bất kỳ thanh toán thật nào.

## 9. Hiểu kỹ `null`, guard và short-circuit

### 9.1. Ba cấp `null` khác nhau

Xét biểu thức:

```java
case Purchase(var orderId,
              Customer(var id, var age, var verified),
              Money(var currency, var amount), var paid)
        when eligible(orderId, id, age, verified,
                      currency, amount, paid) ->
        "APPROVED:" + orderId;
```

Ba nhóm `null` phải phân biệt:

1. **Selector null:** `input == null` → `case null` riêng; `default` không mặc nhiên xử lý `null`.
2. **Record trung gian null:** `customer == null` hoặc `total == null` → nested `Customer(...)` hoặc `Money(...)` không match; bỏ qua guard.
3. **Component reference null:** `id == null` hoặc `amount == null` khi record trung gian vẫn non-null → `var` có thể bind null; guard **chạy** và phải kiểm tra an toàn.

Đừng dùng một test `input==null` làm đại diện cho cả ba nhóm.

### 9.2. Nested type pattern không luôn có nghĩa non-null

Trong Java 21, một **type pattern nested** trong component của record có thể *null-matching* khi nó unconditional đối với kiểu khai báo của component. Ví dụ record `Money(String currency, BigDecimal amount)` có thể match mẫu `Money(String currency, BigDecimal amount)` và bind component null trong những điều kiện unconditional phù hợp. Mẫu dùng `var` trong chương trình chính cũng cho phép bind component reference null.

**Quy tắc cần nhớ:** Record pattern như `Money(...)` không match **object Money null**, nhưng pattern của từng **component** không phải là một cơ chế validate non-null tự động. Nếu nghiệp vụ đòi non-null, phải đặt điều kiện tương ứng trong guard/helper.

### 9.3. Tại sao điều kiện có `&&` cần giữ thứ tự?

```java
return id != null && !id.isBlank()
        && amount != null && amount.signum() > 0;
```

Đây là safe short-circuit. Đảo thành:

```java
// CỐ Ý KHÔNG AN TOÀN:
return !id.isBlank() && id != null;
```

sẽ ném NPE khi `id==null`. Các fragment này nằm trong ngữ cảnh method trả boolean. Ngay cả việc đổi một guard dài sang helper cũng phải giữ thứ tự nếu có null checks hoặc side effects.

### 9.4. Vì sao `when text.length() > 0` có thể ném lỗi?

Chương trình đầy đủ có:

```java
record Probe(String text) {}

static String inspect(Object input) {
    return switch (input) {
        case Probe(var text) when text.length() > 0 -> "NONEMPTY";
        case Probe p -> "EMPTY";
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

Khi `input = new Probe(null)`, record pattern ngoài match, `var text` bind null, và `text.length()` gây `NullPointerException`. **Nhánh `case Probe p -> "EMPTY"` không được thử** khi guard ném exception; nó chỉ được thử khi guard tính xong và trả `false`.

**Sửa nếu muốn false an toàn:**

```java
case Probe(var text)
        when text != null && !text.isEmpty() -> "NONEMPTY";
case Probe p -> "EMPTY";
```

Đây là thay đổi policy từ ném NPE thành fallback EMPTY với `Probe(null)`, nên cần xem đây là một quyết định nghiệp vụ/test riêng, không mặc nhiên là refactor bảo toàn hành vi cũ.

## 10. Đánh giá guard đúng thời điểm, tránh side effect ẩn

Mặc dù Java cho phép gọi hàm có side effect trong guard, predicate lý tưởng nên **thuần**: chỉ nhận input và trả `boolean`, không gửi HTTP request, ghi DB, trừ tiền, ghi log nghiệp vụ hoặc thay đổi state.

Trong chương trình, `eligible(...)` là helper thuần. Hàm `paidProbe(...)` là **bộ đo riêng của test**:

```java
static int guardProbes;

static boolean paidProbe(boolean paid) {
    guardProbes++;
    return paid;
}
```

Bộ đếm cho phép quan sát chính xác số lần guard chạy trong fixture đơn luồng. Không nên đưa state mutable kiểu này vào code production để "đếm mọi guard" mà không có thiết kế instrumentation/thread-safety thích hợp.

### 10.1. Guard chỉ chạy sau khi nested pattern đã match

Ví dụ:

```java
case Purchase(var orderId,
              Customer(var id, var age, var verified),
              Money(var currency, var amount), var paid)
        when paidProbe(paid) -> "PAID";
```

Nếu `Purchase.customer() == null`, record pattern `Customer(...)` thất bại; `paidProbe` **không được gọi**. Nếu customer và money hợp lệ, guard được gọi để trả true/false.

### 10.2. Thứ tự truyền đối số vẫn quan trọng

Java đánh giá đối số lời gọi phương thức **trước** khi gọi helper. Một refactor nguy hiểm là chuyển biểu thức đắt hoặc có side effect từ vế phải của `&&` thành đối số tính sớm.

```java
// Trước: slowCheck() chỉ chạy nếu id khác null.
boolean before = id != null && slowCheck();

// Sau: slowCheck() luôn được đánh giá trước isValid(...).
boolean after = isValid(id, slowCheck());
```

Đoạn này minh họa ngữ nghĩa đánh giá tham số; `slowCheck` và `isValid` là các helper giả định, **không phải đoạn mã độc lập chạy được**. Nếu `slowCheck` có ngoại lệ/side effect, hai phiên bản có thể khác nhau.

Ưu tiên truyền các component đã bind vào helper rồi thực hiện toàn bộ `&&` theo thứ tự đã xác nhận trong helper.

## 11. Dominance và `when true` / `when false`

Compiler Java 21 kiểm tra xem case nào **bị bao phủ bởi case trước** (dominance). Quy tắc cơ bản:

- Một pattern không guard đứng trước pattern hẹp hơn có thể khiến nhánh sau không bao giờ được chọn.
- Case có `when` thông thường **không tự bị coi là bao phủ** tất cả giá trị của cùng pattern, vì compiler không giải quyết mọi biểu thức boolean tùy ý.
- `when true` là trường hợp đặc biệt: constant guard true được đối xử như **nhãn không guard** đối với dominance.
- `when false` nếu là **biểu thức hằng** có giá trị false bị Java 21 từ chối tại compile time.
- Guard phải có kiểu `boolean` hoặc `Boolean` trong ngữ cảnh hợp lệ; `String` không thể tự dùng làm điều kiện.

Các ví dụ **cố ý không biên dịch** dưới đây dùng record:

```java
record Order(String id, int quantity) {}
```

### 11.1. Nhánh rộng trước guard cụ thể — dominance

```java
// CỐ Ý SAI:
return switch (value) {
    case Order order -> "all";
    case Order(var id, var quantity) when quantity > 0 -> "positive";
    default -> "other";
};
```

Compiler báo `this case label is dominated by a preceding case label`. Sửa bằng cách đưa nhánh có guard lên trước, nhánh không guard xuống sau.

### 11.2. Guard hằng `true` vẫn có thể dominate

```java
// CỐ Ý SAI:
return switch (value) {
    case Order order when true -> "all";
    case Order other -> "duplicate";
    default -> "other";
};
```

Dù có chữ `when`, guard `true` khiến nhánh đầu được xem như không guard, che nhánh sau. Đây là **hành vi của Java 21 đã được compiler xác nhận**.

### 11.3. Guard hằng `false` bị từ chối

```java
// CỐ Ý SAI:
return switch (value) {
    case Order order when false -> "never";
    case Order other -> "other";
    default -> "not order";
};
```

Compiler báo tương đương `this case label has a guard that is a constant expression with value 'false'`. Nếu cần tắt một nhánh theo cấu hình, không viết `when false` trực tiếp; hãy bỏ nhánh, hoặc dùng logic cấu hình hợp lệ có chủ đích và test.

### 11.4. Guard không phải boolean

```java
// CỐ Ý SAI nếu Order.id() trả String:
return switch (value) {
    case Order order when order.id() -> "bad";
    default -> "other";
};
```

Compiler báo `String cannot be converted to boolean`. Muốn kiểm tra mã ID không rỗng, dùng điều kiện boolean rõ ràng:

```java
case Order order
        when order.id() != null && !order.id().isBlank() -> "valid";
```

### 11.5. Trường hợp hai guards cùng có thể đúng

Giả sử một giao dịch `age==17` và `paid==false`. Hai biểu thức `when !paid` và `when age < 18` đều true. Compiler không mặc định báo dominance cho hai guards này; **nhánh đứng trước thắng**. Đừng viết test chỉ cho trường hợp mỗi guard đúng độc lập rồi bỏ qua trường hợp **đồng thời đúng**.

## 12. Scope và cách dùng biến pattern

Trong:

```java
case Purchase(var orderId,
              Customer(var id, var age, var verified),
              Money(var currency, var amount), var paid)
        when eligible(orderId, id, age, verified,
                      currency, amount, paid) ->
        "APPROVED:" + orderId;
```

các biến pattern `orderId`, `id`, `age`, `verified`, `currency`, `amount`, `paid` có scope trong biểu thức `when` và trong phần thân của case được chọn, theo quy tắc flow scoping.

**Không dùng một biến pattern từ case trước trong case khác.** Ví dụ:

```java
// CỐ Ý SAI: id ở case thứ nhất không tồn tại trong default.
return switch (input) {
    case Customer(var id, var age, var verified) -> id;
    default -> id;
};
```

Với các case khác nhau, có thể khai báo **tên biến giống nhau** trong các pattern độc lập theo quy tắc scope; ví dụ ở chương trình chính, `orderId` và `id` được bind lặp lại ở nhiều case, vẫn biên dịch hợp lệ.

Trong `instanceof` với `&&`, vế phải được phép dùng các biến pattern đã bind nếu vế trái match thành công:

```java
if (input instanceof Customer(var id, var age, var verified)
        && id != null && age >= 18) {
    System.out.println(id);
}
```

Còn việc dùng biến từ match thất bại qua `||` hoặc ra ngoài scope mà compiler không thể chứng minh definitely matched sẽ gây lỗi. Khi IDE báo variable cannot be resolved, kiểm tra flow path trước khi tìm cách cast thủ công.

## 13. Bộ kiểm thử hồi quy cho record guards

Với case study, test cần tách rõ ba tầng:

1. **Structure testing:** `Purchase`, nested `Customer`/`Money` có match không? Component null khác record null ra sao?
2. **Predicate testing:** `eligible(...)` chấp nhận/từ chối giá trị gì? Có NPE do thiếu short-circuit không?
3. **Branch/priority testing:** Hai guards cùng true thì case nào chọn? Guard false có rơi xuống fallback đúng không?

Chương trình ở mục 8 đã bao phủ các trường hợp sau:

- 20 ca quyết định có expected string rõ ràng.
- Hai ca `instanceof + &&` xác minh đường match success/failure.
- Ba lần gọi `traced`, với chính xác hai lần guard được đánh giá.
- Một ca guard cố ý ném `NullPointerException` để kiểm chứng không dùng exception làm fallback.
- Các tình huống biên: tuổi **17/18**, amount **0**, amount **5.000.000/5.000.001**, ID blank/null, record nested null, paid false.

### 13.1. JUnit 5: chuyển bảng thành parameterized tests

Trong dự án có JUnit Jupiter và dependency `junit-jupiter-params`, có thể tổ chức test dạng bảng. Đoạn sau là **mảnh code JUnit**, không chạy độc lập chỉ với JDK và không thay thế file Java chính ở mục 8:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import java.util.stream.Stream;

class RecordWhenCaseStudyTest {
    static Stream<Arguments> scenarios() {
        return Stream.of(
            Arguments.of("eligible",
                RecordWhenCaseStudy.purchase(
                    "O1","C1",18,true,"VND","5000000",true),
                "APPROVED:O1"),
            Arguments.of("unpaid minor",
                RecordWhenCaseStudy.purchase(
                    "O2","C2",17,true,"VND","100",false),
                "AWAIT_PAYMENT"),
            Arguments.of("missing amount",
                RecordWhenCaseStudy.purchase(
                    "O3","C3",20,true,"VND",null,true),
                "MANUAL_REVIEW"),
            Arguments.of("null selector", null, "NULL_INPUT")
        );
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("scenarios")
    void decidesAsSpecified(String description, Object input,
                            String expected) {
        assertEquals(expected, RecordWhenCaseStudy.decide(input));
    }
}
```

**Ngữ cảnh sử dụng:** đặt test trong cùng package với class `RecordWhenCaseStudy` (vì các record/helpers ví dụ có mức truy cập package-private) hoặc thiết kế lại public API phù hợp; cấu hình JUnit Jupiter/test runner trong Maven/Gradle. Nếu dùng JUnit riêng, không nên dựa vào `System.out.println` để xác nhận pass — hãy dùng assertions của test framework.

### 13.2. Test theo tính chất thay vì chỉ một input

Những quy tắc có thể kiểm tra với nhiều giá trị:

- Với đủ record nested và `paid=false`, mọi Purchase không được duyệt; trong thứ tự bài này, `AWAIT_PAYMENT` được ưu tiên trước `UNDERAGE`.
- Với `amount <= 0` và `paid=true`, một khách hàng đủ tuổi, đủ thông tin sẽ rơi vào `MANUAL_REVIEW`.
- Thay một `Customer` non-null bằng `null` khiến nested pattern không match, kết quả chuyển từ nhánh record cụ thể sang `MISSING_DETAILS`.
- Với mã ID khác nhau nhưng cùng các điều kiện hợp lệ, output `APPROVED:<orderId>` phải phản ánh đúng orderId đã bind.
- Với `amount == LIMIT`, kết quả vẫn có thể `APPROVED`; `amount > LIMIT` không thể được duyệt.

Khi dùng property-based testing, hãy sinh dữ liệu **đúng miền kiểm thử**, giữ seed tái hiện và bổ sung case tối giản khi phát hiện bug. Không viết một property "mọi đối tượng đều không ném exception" nếu hợp đồng cho phép exception với guard không an toàn hoặc dữ liệu không hợp lệ.

## 14. Hiệu năng, dễ đọc và chất lượng thiết kế guard

`when` là cơ chế điều phối điều kiện, không phải một optimization miễn phí. Nếu guard gọi regex, truy vấn DB hoặc hàm ngoài, chi phí có thể lớn hơn nhiều so với việc kiểm tra kiểu record. Giữ guard **ngắn, xác định, có tên miền nghiệp vụ rõ ràng và thuần** giúp:

- Giảm khó hiểu khi review nhiều case.
- Kiểm thử predicate độc lập.
- Tránh lặp điều kiện ở nhiều nơi.
- Dễ audit việc xử lý `null` và thứ tự `&&`.
- Hạn chế side effect bất ngờ khi Java thử một case rồi tiếp tục case sau.

**Nhưng không nên tách quá mức.** Guard ngắn như `when age < 18` đã rõ; tạo một helper `isAgeLessThan18(age)` chỉ để giấu một phép so có thể làm code khó theo dõi hơn.

### 14.1. Khi nào tránh nested deconstruction sâu?

Nếu bạn chỉ cần biết `input instanceof Purchase` để ghi audit theo loại, `case Purchase p` thường đủ. Pattern `Purchase(...Customer(...),Money(...))` còn làm công việc lấy component qua accessor; trong record có accessor tùy biến có thể gây side effects/exception. Chọn độ sâu pattern theo dữ liệu **thực sự cần**.

### 14.2. Không tự chuyển `if/else` thành `switch` mà bỏ qua `null`

`if (value instanceof Purchase p)` trả `false` khi value null. `switch` trên một selector null mà không có `case null` thường có hành vi ném NPE. Nếu refactor, xác định trước contract `null` và viết test; không mặc nhiên cho rằng `default` tương đương nhánh `else` của `if`.

## 15. Các lỗi thường gặp và cách sửa

### Lỗi 1 — Dùng cú pháp preview cũ

`case String s && condition(s)` là cú pháp từ các bản preview trước Java 21. Với Java 21 chuẩn, dùng `case String s when condition(s)`.

### Lỗi 2 — Tưởng guard xử lý thay cho record pattern

`when condition(...)` **không chạy** khi nested `Customer(...)` hoặc `Money(...)` không match. Muốn phân loại thiếu record, phải có fallback `case Purchase p` hoặc cấu trúc phù hợp.

### Lỗi 3 — Tưởng record có field không null theo mặc định

Records không tự kiểm tra dữ liệu component. Nếu có `Money("VND",null)`, `var amount` vẫn bind null và helper phải tránh dereference khi chưa kiểm tra.

### Lỗi 4 — Đặt nhánh không guard lên đầu

Một `case Purchase p` trước các case `Purchase(...) when ...` có thể dominate chúng. Nhánh cụ thể/guarded trước; nhánh tổng quát sau.

### Lỗi 5 — Giả định compiler hiểu mọi guard

Compiler không quyết định tùy ý hai predicate phức tạp có chồng lấn hay không. Nếu hai guards cùng true, **nhánh xuất hiện trước** được chọn. Viết test cho trường hợp chồng lấn.

### Lỗi 6 — Guard hằng false

`when false` với biểu thức hằng false bị Java 21 từ chối. Đừng dùng nó để "comment out" một case.

### Lỗi 7 — Guard không trả boolean

Nếu helper trả `String`, `List` hoặc một đối tượng `Predicate<T>` mà không gọi `.test(...)`, `when` không có giá trị boolean hợp lệ.

### Lỗi 8 — Đổi thứ tự short-circuit

Đưa `amount.signum() > 0` lên trước `amount != null` làm tăng nguy cơ NPE. Giữ null check trước và áp dụng test với component null.

### Lỗi 9 — Cho rằng guard ném exception sẽ sang case sau

Runtime không coi exception là guard false; nó lan truyền exception. Nếu muốn fallback an toàn, predicate phải xử lý điều kiện lỗi theo hợp đồng.

### Lỗi 10 — Dùng `BigDecimal.equals` khi muốn so giá trị

Với amount, `compareTo` phản ánh so sánh giá trị thập phân dù scale khác; `equals` có thể cho kết quả khác khi scale khác nhau. Lựa chọn theo hợp đồng dữ liệu.

### Lỗi 11 — Test một mình predicate

Predicate có thể đúng nhưng switch chọn nhánh sai do thứ tự case hoặc nested record null. Test cả `eligible(...)`, `decide(...)` và các ca chồng lấn guard.

### Lỗi 12 — Đặt quá nhiều hành động trong `when`

Một guard vừa gọi service vừa sửa state rồi mới trả boolean khiến việc rơi qua các nhánh trở nên khó dự đoán. Tách quyết định boolean khỏi hành động có side effect để dễ kiểm thử và rollback.

## 16. Checklist code review và Definition of Done

- [ ] Dự án build bằng **Java 21** với pattern `switch`/record patterns chuẩn.
- [ ] Record ngoài và các nested records được mô hình hóa đúng theo dữ liệu thật.
- [ ] Tên predicate diễn đạt **quy tắc** (ví dụ `eligible`), không giấu hành động.
- [ ] Biến pattern được dùng trong `when` đúng flow scope.
- [ ] Mọi component reference nullable được kiểm tra trước khi dereference.
- [ ] Phân biệt selector `null`, record nested `null` và component `null`.
- [ ] Khi nested pattern thất bại, có fallback phù hợp và guard không bị gọi.
- [ ] Guard true/false có đường đi và expected output rõ ràng.
- [ ] Thứ tự guard thể hiện đúng ưu tiên khi nhiều điều kiện cùng true.
- [ ] Nhánh không guard đứng sau các nhánh cụ thể; không có dominance error.
- [ ] Không viết `when false` hằng; không dùng guard sai kiểu.
- [ ] Không dùng preview syntax `case Pattern && condition` trong mã Java 21.
- [ ] Guard xử lý null an toàn và hạn chế side effect/exception không mong muốn.
- [ ] Với `BigDecimal`, so giá trị và ngưỡng bằng API phù hợp.
- [ ] Có test đúng ngưỡng tuổi và hạn mức, paid/unpaid, verified, null/blank.
- [ ] Có test pattern + `instanceof &&` nếu phần đó được dùng ở ứng dụng.
- [ ] Có test kết quả của guard ném lỗi nếu hợp đồng cần exception.
- [ ] Compiler gate phát hiện dominance, guard hằng sai và lỗi type.
- [ ] Unit tests và CI chạy trên JDK/source level mục tiêu.

**Tiêu chí hoàn tất:** Một người đọc có thể giải thích vì sao từng đơn hàng đi vào nhánh nào; guard chỉ chạy khi pattern match; dữ liệu null không gây NPE bất ngờ trong đường xử lý chính; và các test biên/ưu tiên có kỳ vọng chính xác. Nếu có thay đổi thứ tự case hoặc điều kiện nghiệp vụ, phải công bố đó là một thay đổi hành vi và cập nhật regression tests.

## 17. Câu hỏi tự kiểm tra

**1. `when` được đánh giá trước hay sau nested record pattern?**  
Sau. Java chỉ gọi guard khi pattern trong nhãn case đã match.

**2. Một `Purchase` chứa `Customer=null` có chạy `eligible(...)` ở nhánh nested không?**  
Không, vì `Customer(...)` không match object null.

**3. `Customer(null,20,true)` có thể match `Customer(var id,var age,var verified)` không?**  
Có; `var id` có thể bind null. Guard/helper cần kiểm tra.

**4. Nếu guard đầu trả false, Java đi đâu?**  
Java tiếp tục xét nhãn case phù hợp tiếp theo. Nếu guard ném exception thì không có fallback tự động.

**5. Một đơn hàng 17 tuổi, chưa thanh toán trả gì trong ví dụ?**  
`AWAIT_PAYMENT`, vì nhánh `when !paid` được xét trước `when age < 18`.

**6. Vì sao nên viết `"VND".equals(currency)`?**  
Vì xử lý currency null an toàn, tránh gọi method trên tham chiếu null.

**7. BigDecimal so hạn mức bằng `compareTo` hay `==`?**  
`compareTo` khi cần so sánh giá trị số; `==` chỉ so identity hai object.

**8. `when true` và `when false` có gì đặc biệt?**  
Constant true được đối xử như unguarded pattern cho dominance; constant false bị từ chối compile time.

**9. Có thể dùng `when` sau `instanceof Purchase p` không?**  
Không. Dùng toán tử `&&` để kết hợp boolean condition.

**10. Vì sao `case Purchase p` phải đứng sau các nhánh `Purchase(...) when ...`?**  
Vì nhánh không guard rộng có thể dominate các nhánh cụ thể cùng kiểu.

**11. Hai guards cùng true được chọn thế nào?**  
Nhánh xuất hiện trước trong thứ tự switch.

**12. Dòng `GUARD PROBES PASS: 2` chứng minh điều gì?**  
Trong ba lần gọi `traced`, guard chỉ được đánh giá ở hai input có đủ cấu trúc record nested.

**13. `when amount.signum() > 0` có an toàn nếu amount có thể null không?**  
Không. Cần `amount != null && amount.signum() > 0`.

**14. `ALL CHECKS PASSED` chứng minh mọi đơn hàng trên production hợp lệ chưa?**  
Chưa. Nó chỉ chứng minh các ca được kiểm tra với hợp đồng của ví dụ. Production còn cần quy tắc, dữ liệu, concurrency và integration tests riêng.

## Tài liệu tham khảo

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java SE 21 — Pattern Matching for switch: When Clauses](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JLS SE 21 §14.11 — switch statements, guards and dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS SE 21 §14.30 — Patterns and pattern matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [JLS SE 21 §6.3 — Scope of declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
- [Java SE 21 API — BigDecimal.compareTo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html#compareTo(java.math.BigDecimal))
