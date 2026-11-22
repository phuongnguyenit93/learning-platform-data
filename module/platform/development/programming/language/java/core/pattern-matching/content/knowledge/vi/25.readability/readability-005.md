# Tránh pattern chỉ để rút ngắn code: ưu tiên tính dễ đọc trong Java

## 1. Mục tiêu bài học

Pattern matching giúp Java loại bỏ nhiều đoạn `instanceof` + ép kiểu thủ công, nhận diện kiểu an toàn và phân rã record. Tuy nhiên, **mã ngắn hơn không tự động là mã dễ đọc hơn**. Một nested record pattern kéo dài qua nhiều tầng, cộng thêm `when` và các điều kiện nghiệp vụ, có thể làm người đọc mất nhiều thời gian hơn một phương thức với tên rõ nghĩa.

Bài này tập trung vào tiêu chí **tính dễ đọc**: khi nào pattern giúp thể hiện ý định, khi nào chỉ thay nhiều dòng cú pháp bằng một biểu thức khó hiểu, cách chọn mức phân rã vừa đủ và cách chứng minh refactor không đổi hành vi.

Sau khi học, bạn có thể:

- Phân biệt **giảm mã thừa** với **giảm độ phức tạp nhận thức**.
- Chọn giữa type pattern nông, nested record pattern và phương thức domain có tên.
- Tổ chức guard, điều kiện `null` và nhánh fallback sao cho nhìn vào là hiểu.
- Review một thay đổi pattern theo **nghĩa** và **hành vi**, không theo số dòng code.
- Biết khi nào pattern là lựa chọn rõ ràng nhất, thay vì tránh pattern một cách cực đoan.

Ví dụ chính sử dụng Java 21, vì **record patterns** (JEP 440) và **pattern matching for switch** (JEP 441) đã là tính năng chính thức từ phiên bản này. Type pattern trong `instanceof` đã được chuẩn hóa từ Java 16 (JEP 394).

## 2. Đừng tối ưu theo số dòng

Hãy xem hai cách diễn đạt cùng một ý tưởng trong ví dụ giả lập về giao hàng:

**Một nhánh có cấu trúc rất sâu:**

```java
case Order(var id,
           Customer(var name, Address(var city, var country)),
           var status)
        when status == PaymentStatus.PAID
             && "VN".equals(country)
             && "HCM".equals(city)
        -> "EXPRESS:" + id;
```

**Một nhánh nông, hỏi thẳng domain:**

```java
case Order order when order.eligibleForExpress()
        -> "EXPRESS:" + order.id();
```

Hai đoạn này là **case labels minh họa**, chưa phải chương trình độc lập; lớp đầy đủ ở mục 5.

Đoạn đầu phơi bày các chi tiết `Order → Customer → Address` và chính sách thanh toán, quốc gia, thành phố. Nó hữu ích khi *chính việc khớp cấu trúc* là điều người đọc cần thấy. Nhưng nếu câu hỏi thực sự là “Đơn hàng có đủ điều kiện giao nhanh không?”, một tên `eligibleForExpress()` làm ý định rõ hơn.

Điểm mấu chốt: **khả năng đọc được phụ thuộc câu hỏi nghiệp vụ**, không phụ thuộc việc cách viết nào ngắn hơn. Nested pattern không sai; nó chỉ không phải lựa chọn tốt nhất trong mọi ngữ cảnh.

### Dấu hiệu đang dùng pattern như một thủ thuật rút ngắn code

- Người đọc phải đếm số tầng ngoặc `(...)` mới biết biến nào thuộc record nào.
- Biến được bind nhưng không dùng, chỉ vì bạn cố phân rã toàn bộ cấu trúc.
- Guard dài, lẫn điều kiện nghiệp vụ với logic nhận diện kiểu.
- Cùng một nested pattern được copy vào nhiều controller hoặc service.
- Việc thêm một field vào record khiến nhiều caller phải sửa, dù ý nghĩa nghiệp vụ không đổi.
- Đường đi của `null` và fallback trở nên khó hình dung.
- Một dòng rất dài thay thế cho vài dòng `if` có tên biến rõ ràng.

Các dấu hiệu đó là **gợi ý để cân nhắc**, không phải quy tắc bắt buộc xóa pattern.

## 3. Phân biệt ba trách nhiệm

| Trách nhiệm | Câu hỏi | Công cụ phù hợp |
|---|---|---|
| **Phân loại kiểu** | Dữ liệu có phải `Order` không? | `input instanceof Order order` hoặc `case Order order` |
| **Phân rã cấu trúc** | Đối tượng có nested `Customer`/`Address` để lấy component không? | `Order(..., Customer(..., Address(...)), ...)` khi cần |
| **Quy tắc nghiệp vụ** | Đơn hàng có đủ điều kiện giao nhanh không? | `order.eligibleForExpress()` hoặc một policy/domain service |

Pattern giúp **nhận diện và lấy dữ liệu**. Phương thức domain giúp **đặt tên cho quyết định**. Trộn cả hai vào một nhánh không phải luôn sai, nhưng nếu nó tạo một biểu thức khó đọc, nên giảm số chi tiết bộc lộ ở caller.

Ví dụ, không nên ép domain phải nằm trong một helper có tên chung `Utils.check(...)` chỉ để làm `switch` trông ngắn. Một phương thức tốt phải được đặt ở nơi có trách nhiệm rõ ràng và có tên mô tả điều gì đang được quyết định.

## 4. Bài toán minh họa và hợp đồng hành vi

Giả sử có bốn kiểu:

```java
enum PaymentStatus { PAID, PENDING }

record Address(String city, String country) {}

record Customer(String name, Address address) {}

record Order(String id, Customer customer, PaymentStatus status) {}
```

Đây là **các khai báo minh họa**, không cần lưu thành các tệp riêng; chương trình đầy đủ ở phần 5 định nghĩa chúng bên trong một lớp.

Chính sách **giả định chỉ để học**: một `Order` được gắn `EXPRESS` nếu:

1. Trạng thái thanh toán là `PAID`.
2. Có `Customer` khác `null`.
3. Có `Address` khác `null`.
4. Quốc gia là `VN` và thành phố là `HCM`.

Mọi `Order` khác phải trả `STANDARD:<id>`; input không phải `Order` (bao gồm `null`) trả `NOT_ORDER`. Đây là hợp đồng hành vi cần giữ khi đổi cách viết.

### Cách A — nested pattern rất dày

```java
static String routeDense(Object input) {
    return switch (input) {
        case null -> "NOT_ORDER";
        case Order(var id,
                   Customer(var name, Address(var city, var country)),
                   var status)
                when status == PaymentStatus.PAID
                     && "VN".equals(country)
                     && "HCM".equals(city) -> "EXPRESS:" + id;
        case Order(var id, var customer, var status) -> "STANDARD:" + id;
        default -> "NOT_ORDER";
    };
}
```

**Ưu điểm:** lộ rõ cấu trúc mà nhánh `EXPRESS` yêu cầu; compiler đảm nhận việc khớp nested record. **Nhược điểm:** logic nghiệp vụ và cấu trúc record dồn vào cùng một `case`; biến `name` được bind nhưng không dùng; thay đổi domain cần sửa guard tại caller.

### Cách B — `switch` nông với domain method

```java
static String routeSwitch(Object input) {
    return switch (input) {
        case null -> "NOT_ORDER";
        case Order order when order.eligibleForExpress()
                -> "EXPRESS:" + order.id();
        case Order order -> "STANDARD:" + order.id();
        default -> "NOT_ORDER";
    };
}
```

**Ưu điểm:** cho thấy rõ hai lựa chọn với `Order`. Người đọc không phải biết nội bộ của `Customer` hay `Address`. Cách này phù hợp nếu thực sự có nhiều nhánh phân loại, hoặc biểu thức `switch` được dùng nhất quán trong codebase.

### Cách C — type pattern nông với guard clause

```java
static String routeReadable(Object input) {
    if (!(input instanceof Order order)) {
        return "NOT_ORDER";
    }
    return (order.eligibleForExpress() ? "EXPRESS:" : "STANDARD:")
            + order.id();
}
```

Với đúng hai trạng thái của `Order` trong bài toán, cách C có thể **dễ hiểu nhất**: không cần `switch`, không lặp nhánh `Order` và không cần deconstruct. Pattern variable `order` tồn tại sau `if` vì nếu `instanceof` sai thì phương thức đã `return` (flow scoping). Trường hợp input `null` hoặc sai kiểu đều trả `NOT_ORDER`.

**Không có “người thắng” tuyệt đối:** nếu thêm nhiều loại event, `switch` ở cách B có thể hợp hơn. Nếu xử lý một cấu trúc lồng nhau ở một ranh giới duy nhất, nested pattern ở cách A có thể trực quan hơn. Quyết định dựa vào **ý định, độ sâu và số nhánh**, không dựa vào ít ký tự.

## 5. Ví dụ Java 21 hoàn chỉnh: ba cách viết, cùng hành vi

Tạo tệp **`PatternReadabilityDemo.java`** với nội dung sau:

```java
import java.util.Objects;

public class PatternReadabilityDemo {
    enum PaymentStatus { PAID, PENDING }
    record Address(String city, String country) {}
    record Customer(String name, Address address) {}
    record Order(String id, Customer customer, PaymentStatus status) {
        boolean eligibleForExpress() {
            if (status != PaymentStatus.PAID || customer == null) {
                return false;
            }
            Address address = customer.address();
            return address != null
                    && "VN".equals(address.country())
                    && "HCM".equals(address.city());
        }
    }

    static String routeDense(Object input) {
        return switch (input) {
            case null -> "NOT_ORDER";
            case Order(var id,
                       Customer(var name, Address(var city, var country)),
                       var status)
                    when status == PaymentStatus.PAID
                         && "VN".equals(country)
                         && "HCM".equals(city) -> "EXPRESS:" + id;
            case Order(var id, var customer, var status) -> "STANDARD:" + id;
            default -> "NOT_ORDER";
        };
    }

    static String routeSwitch(Object input) {
        return switch (input) {
            case null -> "NOT_ORDER";
            case Order order when order.eligibleForExpress()
                    -> "EXPRESS:" + order.id();
            case Order order -> "STANDARD:" + order.id();
            default -> "NOT_ORDER";
        };
    }

    static String routeReadable(Object input) {
        if (!(input instanceof Order order)) {
            return "NOT_ORDER";
        }
        return (order.eligibleForExpress() ? "EXPRESS:" : "STANDARD:")
                + order.id();
    }

    static void check(String label, Object input, String expected) {
        String dense = routeDense(input);
        String guarded = routeSwitch(input);
        String simple = routeReadable(input);
        if (!Objects.equals(expected, dense)
                || !Objects.equals(dense, guarded)
                || !Objects.equals(guarded, simple)) {
            throw new AssertionError(label + ": " + dense + " / "
                    + guarded + " / " + simple + ", expected=" + expected);
        }
        System.out.println(label + " => " + simple);
    }

    public static void main(String[] args) {
        check("paid HCM", new Order("O1", new Customer("An",
                new Address("HCM", "VN")), PaymentStatus.PAID), "EXPRESS:O1");
        check("pending HCM", new Order("O2", new Customer("An",
                new Address("HCM", "VN")), PaymentStatus.PENDING), "STANDARD:O2");
        check("other city", new Order("O3", new Customer("An",
                new Address("HN", "VN")), PaymentStatus.PAID), "STANDARD:O3");
        check("other country", new Order("O4", new Customer("An",
                new Address("HCM", "US")), PaymentStatus.PAID), "STANDARD:O4");
        check("null customer", new Order("O5", null,
                PaymentStatus.PAID), "STANDARD:O5");
        check("null address", new Order("O6", new Customer("Binh", null),
                PaymentStatus.PAID), "STANDARD:O6");
        check("null city", new Order("O7", new Customer(null,
                new Address(null, "VN")), PaymentStatus.PAID), "STANDARD:O7");
        check("null country", new Order("O8", new Customer("Chi",
                new Address("HCM", null)), PaymentStatus.PAID), "STANDARD:O8");
        check("null status", new Order("O9", new Customer("Dung",
                new Address("HCM", "VN")), null), "STANDARD:O9");
        check("null id", new Order(null, new Customer("Em",
                new Address("HCM", "VN")), PaymentStatus.PAID), "EXPRESS:null");
        check("root null", null, "NOT_ORDER");
        check("wrong type", "text", "NOT_ORDER");
    }
}
```

Biên dịch và chạy với JDK 21 hoặc mới hơn:

```bash
javac --release 21 PatternReadabilityDemo.java
java PatternReadabilityDemo
```

**Stdout đã kiểm chứng:**

```text
paid HCM => EXPRESS:O1
pending HCM => STANDARD:O2
other city => STANDARD:O3
other country => STANDARD:O4
null customer => STANDARD:O5
null address => STANDARD:O6
null city => STANDARD:O7
null country => STANDARD:O8
null status => STANDARD:O9
null id => EXPRESS:null
root null => NOT_ORDER
wrong type => NOT_ORDER
```

Phương thức `check(...)` không chỉ so sánh ba implementation với nhau mà còn so với `expected` độc lập. Nếu một cách viết trả sai, chương trình ném `AssertionError`. Ví dụ đã được biên dịch bằng `javac --release 21` và chạy thành công cho **12 tình huống**, bao gồm các tầng `null` và ngữ cảnh không phải `Order`. Trong codebase thật, vẫn cần test thêm những invariant và dependency thuộc domain của dự án.

## 6. Vì sao các cách viết giữ được hành vi với null?

Đây là nơi pattern ngắn hơn có thể vô tình đổi logic.

### 6.1. Record ở tầng nested khác null

Với cách A:

```java
Order(var id,
      Customer(var name, Address(var city, var country)),
      var status)
```

Nhánh này chỉ khớp nếu các đối tượng `Order`, `Customer` và `Address` tồn tại. `Customer(...)` hoặc `Address(...)` **không khớp khi chính record đó bằng `null`**. Khi không khớp, `case Order(var id, var customer, var status)` xử lý tiếp và trả `STANDARD` cho `Order` có component thiếu.

Với cách B/C, `eligibleForExpress()` làm tương đương bằng kiểm tra:

```java
if (status != PaymentStatus.PAID || customer == null) {
    return false;
}
Address address = customer.address();
return address != null
        && "VN".equals(address.country())
        && "HCM".equals(address.city());
```

Nội dung trên **là thân phương thức đã có trong chương trình mục 5**, không phải một lớp độc lập. Nếu bỏ `customer == null` hoặc `address != null` khi chuyển logic ra phương thức, bản mới có thể ném `NullPointerException`, không còn tương đương.

### 6.2. Component lá có thể null

Component `city` và `country` là `String`. Pattern `var city` và `var country` trực tiếp trong `Address(...)` có thể **bind `null`**. Guard `"HCM".equals(city)`, `"VN".equals(country)` vẫn an toàn, trả `false` khi đối số null.

Phiên bản domain sử dụng `"VN".equals(address.country())` và `"HCM".equals(address.city())` để giữ null-safe. Nếu refactor thành `address.city().equals("HCM")` thì dữ liệu city null sẽ gây lỗi. Việc “viết gọn” không biện minh cho đổi kết quả.

### 6.3. Root null và kiểu khác

`routeDense` và `routeSwitch` có `case null -> "NOT_ORDER"` và `default -> "NOT_ORDER"`. Không nên giả định `default` trong pattern `switch` tự bắt selector null.

`routeReadable` dùng `input instanceof Order order`: biểu thức trả `false` nếu root null hoặc sai kiểu, nên guard clause trả `NOT_ORDER` mà không cần nhánh `case null`.

### 6.4. Biến không dùng và nullable ID

Trong nested pattern, `var name` được bind nhưng không dùng để quyết định express. Một người review có thể hỏi: “Tại sao lớp điều phối phải biết cả tên khách hàng?” Điều đó gợi ý chuyển sang type pattern nông.

Cả ba phiên bản đều có thể xử lý `id == null` bằng phép nối chuỗi, tạo `EXPRESS:null` khi đủ điều kiện. **Đây là hành vi của ví dụ, không phải khuyến nghị domain cho phép thiếu ID.** Nếu cần ID không null, hãy thay đổi invariant riêng, không trộn vào refactor.

## 7. Một số lỗi khi cố dùng pattern cho mọi thứ

### 7.1. Dùng switch cho câu hỏi chỉ có true/false

Khi input đã có kiểu `Order` và chỉ cần câu trả lời boolean, đoạn sau thường không thêm nhiều giá trị:

```java
boolean eligible = switch (order) {
    case Order(var id, Customer(var name, Address(var city, var country)),
               var status)
            when status == PaymentStatus.PAID
                 && "VN".equals(country)
                 && "HCM".equals(city) -> true;
    default -> false;
};
```

**Đây là snippet minh họa** sử dụng các record ở mục 5. Nếu chỉ cần “eligible hay không”, mã `order.eligibleForExpress()` nói đúng điều cần hỏi, không cần tự deconstruct. Nếu `order` có thể null, phải quy định rõ hợp đồng của phương thức hoặc xử lý null ở ranh giới gọi.

### 7.2. Làm dày pattern để tránh vài dòng accessor

Ví dụ khi chỉ cần tên đơn hàng, một pattern:

```java
case Order(var id, Customer(var name, Address(var city, var country)),
           var status) -> id;
```

tình cờ áp đặt rằng customer và address phải khác null, dù logic chỉ muốn `id`. Nó **thay đổi tập giá trị được chấp nhận** và tạo một điều kiện ẩn không liên quan.

Nếu selector đã được phân loại là Order, dùng:

```java
case Order order -> order.id();
```

sẽ rõ và bao phủ mọi `Order`, kể cả các component null. Đây là hai **case labels minh họa**, phải đặt trong `switch` phù hợp.

### 7.3. Lạm dụng nhiều pattern variables

Viết `Order(var id, var customer, var status)` không có nghĩa bạn phải sử dụng cả ba biến. Nhưng nếu logic chỉ cần hỏi một điều về Order, đôi khi `case Order order` đơn giản hơn. Ngược lại, nếu bạn thật sự cần nhiều component để tạo output, deconstruction là có lý do rõ ràng.

### 7.4. Giấu nghiệp vụ trong một guard dài

Một `when` dài qua nhiều phép `&&` và `||` khiến người đọc phải tự suy ra tên quy tắc. Khi điều kiện có ý nghĩa riêng và được tái sử dụng, hãy cân nhắc helper hoặc phương thức domain. Việc tách phải **giữ nhóm ngoặc, thứ tự đánh giá và short-circuit**: `a && (b || c)` khác `a && b || c`.

### 7.5. Đổi thứ tự case vì tưởng bản mới sạch hơn

Trong `switch` pattern:

```java
case Order order when order.eligibleForExpress() -> "EXPRESS";
case Order order -> "STANDARD";
```

nhánh có guard phải đứng **trước** nhánh tổng quát. Đảo lại khiến nhánh hẹp bị che (*dominated case label*) và lỗi compile time. Tập trung rút ngắn code mà quên thứ tự nhánh có thể làm refactor không hợp lệ.

## 8. Khi nào pattern thực sự làm code dễ đọc hơn?

Không nên rút ra kết luận “ít pattern hơn luôn tốt hơn”. Pattern hữu ích khi nó **mang thông tin cấu trúc quan trọng**:

- **Phân loại biến có kiểu rộng:** `if (input instanceof Order order)` vừa kiểm tra kiểu vừa bind biến an toàn, thay thế cast thủ công.
- **Xử lý nhiều biến thể dữ liệu:** một `switch` trên sealed hierarchy có thể thể hiện các trường hợp được compiler kiểm tra đầy đủ; nếu không cần trường hợp khác, exhaustiveness là lợi ích đáng kể.
- **Phân rã record ở ranh giới dữ liệu:** khi thực sự cần một vài component của record để tạo một kết quả, pattern có thể tránh chuỗi accessor và ép kiểu.
- **Khớp cấu trúc lồng nhau là yêu cầu:** nếu logic chỉ áp dụng khi một record con thực sự tồn tại, nested record pattern thể hiện điều kiện đó rõ ràng.

Ví dụ một type pattern ngắn, rõ mục đích:

```java
static String label(Object input) {
    if (input instanceof String text) {
        return "Text length=" + text.length();
    }
    return "Not text";
}
```

Đây là phương thức minh họa độc lập, có thể đặt trong lớp Java. Không cần ép kiểu `String text = (String) input`, và việc dùng pattern **giảm code lặp mà không tăng độ khó đọc**.

Một pattern chỉ đáng dùng khi nó giúp người đọc hiểu câu trả lời: **“Đầu vào phải có hình dạng nào để nhánh này hợp lệ?”** Nếu câu hỏi thực là “Quy tắc nghiệp vụ nào đúng?”, phương thức domain có tên thường biểu đạt tốt hơn.

## 9. Tiêu chí đánh giá tính dễ đọc

Thay vì đếm dòng, hãy tự trả lời:

| Tiêu chí | Câu hỏi review |
|---|---|
| **Ý định** | Có hiểu nhánh trả gì mà không giải mã từng component không? |
| **Độ sâu** | Có bắt buộc biết 3–4 tầng record tại caller không? |
| **Scope** | Các biến pattern có tên rõ ràng, có được dùng đúng chỗ không? |
| **Null contract** | Nested null và leaf null có dễ dự đoán không? |
| **Fallback** | Nhánh không khớp đi đâu, có dễ nhìn thấy không? |
| **Cô lập chính sách** | Khi thay rule, cần sửa một nơi hay nhiều caller? |
| **Khả năng test** | Có thể kiểm tra rule riêng không, hay phải dựng cả switch phức tạp? |
| **Độ ổn định** | Khi cấu trúc record thay đổi, có buộc sửa nơi chỉ quan tâm nghiệp vụ không? |
| **Khối lượng khái niệm** | Để hiểu 1 nhánh, người đọc phải giữ bao nhiêu điều kiện trong đầu? |

Điều khó đo nhất là mức *phù hợp với mục đích* (local clarity): một pattern dài có thể hợp lý trong một mapper duy nhất, nhưng gây coupling trong business service. Ngữ cảnh của đoạn code quan trọng hơn style preference cố định.

## 10. Refactor từng bước thay vì viết lại một lần

1. **Khoanh hành vi cũ:** liệt kê input/null/boundary và kết quả mong đợi. Nếu code cũ có bug, đừng âm thầm thay đổi bug trong lần refactor cú pháp; cần tách quyết định sửa hành vi.
2. **Xác định đâu là cấu trúc, đâu là nghiệp vụ:** `input instanceof Order` là kiểm tra kiểu; `eligibleForExpress()` là quyết định.
3. **Chọn mức pattern nông nhất đủ dùng:** chỉ deconstruct những component được logic tại caller sử dụng.
4. **Đặt phương thức domain ở đúng nơi:** nếu thuộc hành vi của Order, cân nhắc `Order.eligibleForExpress()`; nếu phụ thuộc chính sách vùng giao hàng từ hệ thống ngoài, cân nhắc policy/service có dependency rõ ràng.
5. **Giữ thứ tự và null contract:** khi chuyển từ nested record pattern sang type pattern nông, helper phải tự xử lý component còn có thể null.
6. **Viết test trước/sau với expected độc lập:** bao gồm input không phải kiểu, root null, nested null, leaf null, các điều kiện đúng/sai.
7. **Đọc diff như reviewer:** đoạn nào chỉ thay cú pháp, đoạn nào có thể đổi đường đi của input? Có nhánh fallback bị mất không?
8. **Đánh giá bản mới bằng người đọc:** nếu không thể nói mục đích của phương thức bằng một câu, pattern đã quá dày hoặc trách nhiệm chưa được tách tốt.

Không cần đưa mọi helper vào một lớp `Utils` lớn, cũng không nên tách thành hàng chục phương thức nhỏ chỉ để làm từng `when` có một từ. Mức trừu tượng hóa nên **giảm số điều phải hiểu**, không chỉ làm caller ngắn.

## 11. Lỗi review thường gặp

| Lỗi | Hệ quả | Cách tránh |
|---|---|---|
| Chỉ đo số dòng code trước/sau | Đánh giá nhầm một biểu thức ngắn nhưng khó hiểu là tốt hơn | So sánh ý định, scope, fallback, null |
| Dùng nested record pattern khi chỉ cần ID | Làm phát sinh điều kiện non-null ẩn | Dùng `case Order order` hoặc `order.id()` |
| Rút gọn bằng cách bỏ nhánh fallback | Đổi hành vi với component thiếu | Lập bảng đường đi input trước/sau |
| Chuyển sang domain method nhưng quên null check | Có thể xuất hiện `NullPointerException` | So sánh với semantics của nested record pattern |
| Đưa nhiều điều kiện vào `when` | Rule khó đặt tên, dễ copy-paste và sửa lệch | Tách predicate/domain method khi có ý nghĩa |
| Refactor đổi `constant.equals(value)` thành `value.equals(constant)` | Lỗi với giá trị null | Giữ so sánh null-safe |
| Đảo vị trí nhánh có guard và nhánh tổng quát | Dominated case hoặc thay nhánh được chọn | Giữ nhánh cụ thể trước nhánh rộng |
| Tạo helper một dòng cho mọi phép toán nhỏ | Người đọc phải nhảy qua nhiều lớp/phương thức | Chỉ tách theo trách nhiệm có tên |
| Trộn tối ưu performance với refactor readability | Khó xác định nguyên nhân thay đổi | Đo performance và tách thay đổi có mục tiêu |

## 12. Thực hành: chọn biểu thức dễ đọc hơn

**Tình huống A.** Input là `Object`; bạn chỉ cần in độ dài khi nó là `String`.

- Dùng `instanceof String text` là tự nhiên: type pattern loại bỏ cast mà không gây cấu trúc phức tạp.
- Không cần `switch` nhiều nhánh nếu chỉ có một loại đầu vào và một fallback.

**Tình huống B.** Input là `Order`; nghiệp vụ hỏi “có được giao nhanh không?”.

- Ưu tiên `order.eligibleForExpress()` hoặc policy có tên nếu rule thuộc domain.
- Không cần deconstruct mọi component tại mọi caller chỉ để đánh giá lại cùng quy tắc.

**Tình huống C.** Input là kiểu sự kiện có nhiều biến thể và mỗi biến thể cần cấu trúc khác nhau.

- `switch` với type/record patterns có thể phản ánh tốt tập trường hợp.
- Nếu sử dụng sealed hierarchy, hãy xem xét exhaustiveness và thứ tự các nhánh.
- Nested record pattern chỉ nên sâu đến mức cần cho hành vi của nhánh đó.

**Tình huống D.** Bạn đã có `Customer` và muốn lấy `address.city()`.

- Accessor trực tiếp thường rõ hơn một `instanceof` record pattern dài.
- Nếu `address` có thể null, hãy xử lý theo hợp đồng rõ ràng, không dùng pattern như cách che giấu null check.

### Câu hỏi tự kiểm tra

1. Tại sao `case Order order` có thể rõ hơn `case Order(var id, Customer(var name, Address(...)), var status)`? **Vì caller chỉ cần một Order có tên, không phải hiểu toàn bộ cấu trúc và chính sách.**
2. Nested record pattern `Customer(...)` có khớp khi customer null không? **Không.** Nếu chuyển sang `Order order` thì domain method phải xử lý tình huống đó.
3. Vì sao `String city`/`var city` trực tiếp ở component vẫn có thể bind null? **Vì component tham chiếu của record có thể null; sự tồn tại của record không đảm bảo component lá non-null.**
4. Có nên tránh hoàn toàn `instanceof String text` chỉ vì pattern? **Không.** Đây là type pattern thường làm ý định rõ hơn cast thủ công.
5. Nếu hai phiên bản có cùng output trong 12 case, có chứng minh mọi input tương đương chưa? **Chưa.** Nó là regression evidence cho dữ liệu đã thử; cần xét domain contract và test bổ sung.
6. Khi nào `switch` tốt hơn một guard clause đơn giản? **Khi có nhiều lựa chọn độc lập/biến thể dữ liệu, hoặc exhaustiveness làm rõ các trường hợp phải xử lý.**
7. Có nên ưu tiên một nested pattern dài chỉ vì nó ngắn hơn 4 dòng `if`? **Không.** Tiêu chí là tính dễ đọc, phạm vi trách nhiệm và semantics của nhánh.

## Kết luận

**Đừng dùng pattern chỉ để rút ngắn code.** Hãy dùng nó khi việc phân loại kiểu hoặc deconstruct cấu trúc giúp thể hiện ý định. Với các quy tắc nghiệp vụ, một phương thức có tên rõ nghĩa thường giúp caller ít phụ thuộc vào cấu trúc hơn. Cách viết đáng chọn là cách làm nổi bật **điều kiện có ý nghĩa**, giữ dễ hiểu trường hợp `null` và fallback, đồng thời bảo toàn hành vi.

Trong Java 21, nested record patterns, `switch` guards và type patterns là công cụ hữu ích; chất lượng thiết kế nằm ở việc chọn **đúng mức trừu tượng**, không phải tận dụng tối đa mọi cú pháp trên một dòng.

## Tài liệu tham khảo chính thức

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java Language Specification SE 21 — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
