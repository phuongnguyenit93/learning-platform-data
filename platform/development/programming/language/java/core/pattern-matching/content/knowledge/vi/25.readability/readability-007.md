# Tách guard dài thành predicate để dễ đọc Pattern Matching (Java 21)

## 1. Vấn đề: guard dài che mất ý nghĩa nghiệp vụ

Trong pattern matching for `switch`, **guard** là điều kiện boolean đứng sau từ khóa `when`. Guard chỉ được đánh giá sau khi pattern đứng trước đã match, giúp tách một kiểu dữ liệu thành các trường hợp cụ thể hơn.

Xét record khách hàng:

```java
record Customer(String name, int age, List<String> tags) {}
```

Một nhánh có thể viết:

```java
case Customer(var name, var age, var tags)
        when name != null && !name.isBlank()
                && age >= 18 && tags != null
                && tags.contains("ACTIVE") ->
        "approved:" + name.trim();
```

Về mặt cú pháp, đoạn này hợp lệ trong một `switch` Java 21 khi `List` đã được import. Tuy nhiên, người đọc phải tự diễn dịch từng phép `null` check, `isBlank`, tuổi và tag để hiểu **điều kiện được duyệt**. Khi bổ sung nhiều điều kiện, phần `case` có thể dài hơn cả hành động cần thực hiện.

Giải pháp là **tách biểu thức guard dài thành một hoặc nhiều predicate có tên mang ý nghĩa nghiệp vụ**:

```java
case Customer(var name, var age, var tags)
        when eligibleCustomer(name, age, tags) ->
        "approved:" + name.trim();
```

Trong bài này, *predicate* trước hết có nghĩa là **một phép kiểm tra trả về `boolean`**. Nó có thể được cài bằng phương thức `static boolean eligibleCustomer(...)`; không bắt buộc phải dùng interface `java.util.function.Predicate<T>`.

### Mục tiêu

Sau bài học, bạn có thể:

1. Tách `when` dài thành hàm boolean có tên rõ ràng, không làm mất ý nghĩa hoặc thay đổi kết quả.
2. Biết khi nào dùng predicate nhận **các component** và khi nào nhận **cả record**.
3. Dùng biến pattern đã bind đúng phạm vi trong `when` và trong biểu thức `instanceof && ...`.
4. Giữ nguyên thứ tự đánh giá, short-circuit, xử lý `null` và exception.
5. Tránh trộn thay đổi business rule vào một refactor chỉ nhằm cải thiện khả năng đọc mã.
6. Chứng minh kết quả trước/sau bằng chương trình Java và ma trận kiểm thử.

**Phiên bản:** `instanceof` patterns chuẩn từ Java 16 (JEP 394). Record patterns và pattern matching cho `switch` trở thành tính năng chuẩn trong **Java 21** (JEP 440, JEP 441). Mã thực hành dùng JDK 21+, không cần `--enable-preview`.

## 2. Cơ chế của `case Pattern when guard`

Ví dụ tổng quát:

```java
return switch (value) {
    case Customer(var name, var age, var tags)
            when eligibleCustomer(name, age, tags) ->
            "approved";
    case Customer c -> "pending";
    case null -> "null";
    default -> "other";
};
```

Diễn tiến:

1. Java kiểm tra `value` có khớp record pattern `Customer(...)` hay không.
2. Nếu match, các biến `name`, `age`, `tags` được bind từ component của record.
3. Java tính `eligibleCustomer(name, age, tags)`; lời gọi phải trả về `boolean`.
4. Nếu trả `true`, nhánh này được chọn. Nếu trả `false`, `switch` tiếp tục xét nhãn `case` phù hợp phía sau; ở đây `case Customer c` xử lý khách hàng chưa đủ điều kiện.
5. Nếu chính selector là `null`, `case null` xử lý. `default` dành cho loại object khác.

Guard **không chạy** khi pattern đứng trước không match. Biến pattern chỉ có phạm vi trong điều kiện `when` và nhánh được chọn; không thể dùng tùy tiện ở các nhánh khác.

Một số chi tiết cần nhớ:

- `when` thuộc **nhãn `case` có pattern** trong `switch`. Không viết `value instanceof Customer c when predicate(c)`; với `instanceof`, dùng toán tử boolean `&&`.
- `when` không tạo một pattern mới. Nó lọc các giá trị **đã match pattern** theo điều kiện bổ sung.
- Guard chỉ chấp nhận kết quả kiểu `boolean`/`Boolean` sử dụng được trong ngữ cảnh boolean; cách thiết kế an toàn và dễ đọc là trả `boolean` nguyên thủy.
- Các nhánh được xét theo thứ tự. Nhánh không guard, rộng hơn thường phải đặt **sau** nhánh có guard cùng kiểu để tránh dominance.

## 3. Quy trình tách guard an toàn từng bước

### Bước 1: Chọn tên theo quy tắc, không theo cú pháp

Một tên tốt nói **vì sao** điều kiện đúng:

- `eligibleCustomer(...)`, `hasAccess(...)`, `canIssueInvoice(...)`, `isWithinLimit(...)`.
- Tránh `check(...)`, `validateStuff(...)`, `condition1(...)` vì không mang thông tin.
- Nếu hàm trả `boolean`, tên thường bắt đầu bằng `is`, `has`, `can` hoặc một mô tả trạng thái như `eligibleCustomer`.

Tên phải tương ứng với logic thật. Ví dụ `eligibleCustomer` không nên chỉ kiểm tra tuổi nếu điều kiện thực tế còn đòi tag đang hoạt động.

### Bước 2: Chuyển **nguyên biểu thức** vào helper

Từ guard gốc:

```java
when name != null && !name.isBlank()
        && age >= 18 && tags != null
        && tags.contains("ACTIVE")
```

Tạo:

```java
static boolean eligibleCustomer(String name, int age, List<String> tags) {
    return name != null && !name.isBlank()
            && age >= 18 && tags != null
            && tags.contains("ACTIVE");
}
```

Tại thời điểm refactor, **giữ nguyên thứ tự các toán hạng và toán tử** để bảo toàn short-circuit. Chỉ tách biểu thức ra ngoài; không "nhân tiện" đổi ngưỡng tuổi, làm `trim()` trước khi so, thêm `equalsIgnoreCase` hoặc thay `contains` bằng quy tắc khác.

### Bước 3: Chia thành các predicate nhỏ khi có hai khái niệm rõ ràng

```java
static boolean validIdentity(String name, int age) {
    return name != null && !name.isBlank() && age >= 18;
}

static boolean hasActiveTag(List<String> tags) {
    return tags != null && tags.contains("ACTIVE");
}

static boolean eligibleCustomer(String name, int age, List<String> tags) {
    return validIdentity(name, age) && hasActiveTag(tags);
}
```

Đây là mức phân tách hợp lý: **danh tính/độ tuổi** và **trạng thái tag** là hai khái niệm có thể giải thích, test và tái sử dụng riêng. Việc ghép vẫn là `&&`, theo thứ tự gốc.

Không cần tạo một hàm cho từng phép `name != null` hoặc `age >= 18` nếu những hàm nhỏ đó khiến người đọc phải nhảy giữa quá nhiều vị trí để hiểu một quy tắc đơn giản.

### Bước 4: Thay guard, không đổi pattern hoặc kết quả nhánh

Trước:

```java
case Customer(var name, var age, var tags)
        when name != null && !name.isBlank()
                && age >= 18 && tags != null
                && tags.contains("ACTIVE") ->
        "approved:" + name.trim();
```

Sau:

```java
case Customer(var name, var age, var tags)
        when eligibleCustomer(name, age, tags) ->
        "approved:" + name.trim();
```

Giữ nguyên record pattern, các biến, chuỗi kết quả và thứ tự nhánh. Việc này giúp diff nhỏ, dễ review và giảm nguy cơ thay đổi số lần gọi accessor. Có thể cân nhắc đổi mẫu record thành type pattern sau đó, nhưng đó là một thay đổi riêng cần đánh giá.

### Bước 5: Chứng minh tương đương

Chạy cùng bộ input qua bản guard inline và bản đã trích xuất; so **giá trị trả về**, các exception quan trọng, và nếu ứng dụng có side effect thì so cả thứ tự/số lần gọi dependency. Đừng chỉ chạy một ca "happy path" rồi kết luận refactor đã thành công.

## 4. Chọn chữ ký predicate: component hay object?

Có hai cách viết đặc biệt hữu ích trong Java 21.

### 4.1. Nhận các component đã bind

```java
case Customer(var name, var age, var tags)
        when eligibleCustomer(name, age, tags) ->
        "approved:" + name.trim();
```

Với cách này, signature phản ánh đúng dữ liệu được kiểm tra:

```java
static boolean eligibleCustomer(String name, int age, List<String> tags)
```

**Ưu điểm:** dễ unit test từng giá trị; không cần tạo `Customer` nếu đang test predicate; không buộc predicate phụ thuộc toàn bộ record. Thích hợp khi logic chính là quy tắc trên một nhóm component và nhiều nơi khác có thể cung cấp các component tương đương.

**Cần lưu ý:** khi có quá nhiều tham số, khó biết mỗi tham số đến từ đâu và dễ truyền sai thứ tự nếu nhiều tham số cùng kiểu. Khi ấy nhận record hoặc một value object có thể đọc tốt hơn.

### 4.2. Nhận chính đối tượng record

Nếu predicate là một quy tắc thuộc về `Customer`, có thể viết:

```java
static boolean eligibleCustomer(Customer c) {
    return c.name() != null && !c.name().isBlank()
            && c.age() >= 18
            && c.tags() != null
            && c.tags().contains("ACTIVE");
}
```

Trong `switch`:

```java
case Customer c when eligibleCustomer(c) -> "approved";
case Customer c -> "pending";
```

**Ưu điểm:** signature ngắn, tên kiểu giúp thể hiện miền nghiệp vụ, dễ mở rộng khi điều kiện sử dụng thêm field. Phù hợp với quy tắc chủ yếu hoạt động trên cả object.

**Cẩn trọng:** ví dụ trên đọc accessor `c.name()` và `c.tags()` nhiều lần. Với record thông thường, accessor mặc định chỉ trả component, nhưng Java cho phép khai báo accessor tường minh, có thể có side effect, chi phí hoặc exception. Nếu contract cần **chính xác một lần đọc**, hãy lưu vào biến cục bộ và bảo toàn thứ tự tính toán, hoặc giữ các component đã bind từ record pattern. Việc đổi từ record deconstruction sang type pattern cũng có thể làm thay đổi thời điểm/số lần gọi accessor. Đánh giá thay đổi này độc lập với việc tách guard.

### Chọn cách nào?

| Tiêu chí | Nhận component | Nhận record |
| --- | --- | --- |
| Logic dùng ít trường, dễ tái sử dụng ở nơi khác | Thường phù hợp | Có thể phụ thuộc record nhiều hơn mức cần |
| Logic thực sự mô tả trạng thái của object | Phải truyền nhiều đối số | Dễ đặt tên, giữ ý nghĩa nghiệp vụ |
| Cần kiểm soát accessor | Component đã bind có thể tái sử dụng | Phải kiểm soát số lần gọi accessor trong helper |
| Unit test predicate đơn lẻ | Truyền trực tiếp giá trị | Tạo record |
| Signature có quá nhiều đối số cùng kiểu | Dễ nhầm | Thường gọn hơn |

Không có một lựa chọn đúng cho mọi tình huống. Ưu tiên **cách làm rõ hành vi với ít thay đổi ngoài mục tiêu refactor nhất**.

## 5. Phương thức `boolean` và `Predicate<T>` khác nhau thế nào?

Từ "predicate" có hai cách dùng phổ biến:

1. Một phương thức trả boolean, chẳng hạn `static boolean eligibleCustomer(Customer c)`.
2. Một đối tượng triển khai interface `java.util.function.Predicate<T>` có phương thức `boolean test(T value)`, có thể truyền như một giá trị và ghép bằng `and`, `or`, `negate`.

Trong `when`, **cả hai đều được**, miễn biểu thức sau `when` trả boolean.

Dạng phương thức:

```java
case Customer c when eligibleCustomer(c) -> "approved";
```

Dạng đối tượng `Predicate<Customer>`:

```java
import java.util.function.Predicate;

private static final Predicate<Customer> ELIGIBLE =
        c -> c.name() != null && !c.name().isBlank() && c.age() >= 18;

static String status(Object input) {
    return switch (input) {
        case Customer c when ELIGIBLE.test(c) -> "approved";
        case Customer c -> "pending";
        case null -> "null";
        default -> "other";
    };
}
```

Đoạn này là ví dụ đặt trong class có `record Customer(String name, int age, ...)`, không phải chương trình độc lập. `ELIGIBLE.test(c)` trả về `boolean`, còn bản thân `ELIGIBLE` chỉ là một **đối tượng hàm**, không phải boolean.

Cách viết sau **cố ý không biên dịch**:

```java
case Customer c when ELIGIBLE -> "approved"; // Predicate<Customer> không phải boolean
```

Nếu các quy tắc cần dùng trong `Stream.filter(...)` hoặc được truyền giữa các lớp, `Predicate<T>` hữu ích. Nếu chỉ cần đặt tên cho một guard `switch`, **phương thức `boolean` thường đơn giản và trực tiếp hơn**, giảm thêm một lớp cú pháp `.test(...)`.

### Ghép predicate với `and`/`or`

Ví dụ khi có hai predicate thực sự cần dùng nhiều nơi:

```java
Predicate<Customer> namedAdult =
        c -> c.name() != null && !c.name().isBlank() && c.age() >= 18;
Predicate<Customer> active =
        c -> c.tags() != null && c.tags().contains("ACTIVE");
Predicate<Customer> eligible = namedAdult.and(active);
```

`eligible.test(c)` áp dụng `namedAdult` trước và chỉ đánh giá `active` nếu predicate đầu trả `true`. `or` cũng đánh giá ngắn mạch theo thứ tự; `negate` đảo boolean. Việc tạo và ghép `Predicate` nên có lý do thiết kế rõ ràng, tránh biến một guard đơn giản thành chuỗi lambda khó đọc.

## 6. Short-circuit, null và đánh giá tham số: điều kiện bắt buộc bảo toàn

### 6.1. Giữ nguyên thứ tự kiểm tra null

Trong guard:

```java
when name != null && !name.isBlank()
        && tags != null && tags.contains("ACTIVE")
```

`!name.isBlank()` không chạy nếu `name == null`. Tương tự, `tags.contains(...)` không chạy nếu `tags == null`. Predicate tách ra phải giữ tương quan này:

```java
static boolean valid(String name, List<String> tags) {
    return name != null && !name.isBlank()
            && tags != null && tags.contains("ACTIVE");
}
```

Với `Customer(var name, var age, var tags)`, các component reference **có thể bằng `null`**. Record pattern dùng `var` có thể bind `null`; không được tưởng rằng việc match record đã bảo đảm mọi component non-null.

Cần phân biệt:

- `value == null`: selector không match `Customer(...)`; xử lý bằng `case null` nếu muốn.
- `new Customer(null, 20, ...)`: record ngoài vẫn match; component `name` bind `null` với `var`, và predicate phải chủ động xử lý.
- `new Customer("", 20, ...)`: `name` non-null nhưng blank; hàm quyết định đây có đủ điều kiện hay không.

### 6.2. Java đánh giá đối số trước khi gọi phương thức

Một cách refactor nguy hiểm là chuyển biểu thức có side effect sang **đối số hàm**, làm nó chạy sớm hơn. So sánh:

```java
// Trước: chỉ gọi expensiveCheck() nếu name không null.
boolean before = name != null && expensiveCheck();

// Sau: KHÔNG tương đương nếu expensiveCheck() có side effect,
// vì Java đánh giá đối số trước khi gọi isValid(...).
boolean after = isValid(name, expensiveCheck());
```

Giả định `expensiveCheck()` là phương thức trả `boolean` và `isValid(String, boolean)` cũng trả boolean; đoạn này dùng để minh họa **thứ tự đánh giá**, không phải mã tự chạy độc lập. Java sẽ gọi `expensiveCheck()` để lấy đối số thứ hai kể cả khi `name == null`.

**Cách an toàn** là truyền những biến đã bind/đã tính sẵn vào helper, và đặt logic short-circuit bên trong:

```java
static boolean isValid(String name) {
    return name != null && expensiveCheck();
}
```

Trong ví dụ minh họa thứ hai, `expensiveCheck()` là một dependency giả định. Khi refactor code thực, cần giữ đúng ngữ cảnh/hàm gốc thay vì copy đoạn này như chương trình độc lập.

### 6.3. Không đổi thứ tự các điều kiện "cho đẹp" khi chưa chứng minh tương đương

Trong biểu thức chỉ gồm các giá trị primitive và pure function, việc đổi thứ tự `&&` có thể giữ kết quả boolean. Nhưng với getter có side effect, `List` mutable, `Clock`, I/O, log hoặc phương thức ném exception, **thứ tự đánh giá là một phần hành vi**.

Ví dụ:

```java
tags != null && tags.contains("ACTIVE") && auditAllowed()
```

không tự động tương đương với:

```java
auditAllowed() && tags != null && tags.contains("ACTIVE")
```

Nếu `auditAllowed()` ghi log, tính lại cache hoặc có thể ném lỗi, hai bản có thể khác nhau. Ngay cả khi cùng kết quả boolean, sự khác biệt về side effect vẫn quan trọng.

## 7. Predicate nên thuần (pure) và không gây bất ngờ

Một **pure predicate** lý tưởng chỉ đọc dữ liệu đầu vào và trả `boolean`, không sửa trạng thái, không gọi hệ thống ngoài, không sinh log nghiệp vụ hoặc thay đổi thời gian. Với guard `switch`, tính thuần giúp:

- Kết quả dễ dự đoán và dễ kiểm thử.
- Việc đánh giá nhiều lần ít nguy hiểm hơn.
- Tên hàm thực sự mô tả một câu hỏi về dữ liệu, không giấu hành động.
- Không phát sinh exception/latency bất ngờ khi giá trị match một pattern.

Ví dụ tốt:

```java
static boolean canIssueInvoice(
        String currency, BigDecimal total, boolean paid) {
    return currency != null && !currency.isBlank()
            && total != null && total.signum() > 0 && paid;
}
```

Hàm kiểm tra một thuộc tính của hóa đơn; nó không thực sự phát hành hóa đơn, không trừ tiền và không ghi dữ liệu. **Tên có tiền tố `can`**, không phải `issueInvoice`, phản ánh rằng kết quả chỉ là điều kiện để thực hiện một thao tác khác.

**Tránh:**

```java
// Không nên dùng trực tiếp làm guard nếu hàm làm các thao tác bên ngoài.
case Invoice invoice when chargeCardAndUpdateDatabase(invoice) -> "ready";
```

Đoạn trên là minh họa syntax trong một `switch`, với helper giả định. Nếu guard có tác dụng phụ, thất bại hoặc ném exception có thể làm thay đổi tiến trình chọn nhánh và tạo hành vi khó truy vết. Khi cần gọi external service, thường nên thực hiện ở bước điều phối rõ ràng và truyền kết quả đã được kiểm soát cho logic phân loại.

**Lưu ý quan trọng:** `when` được gọi khi pattern match đến nhãn đó; nếu guard trả `false`, `switch` có thể xét nhánh sau. Không nên dựa vào việc compiler "tự cache" kết quả giữa các guard có vẻ giống nhau. Khi cùng predicate xuất hiện ở nhiều nhánh, hãy cân nhắc chi phí và các side effect; nếu cần đánh giá đúng một lần, tổ chức luồng điều khiển để lưu kết quả ở vị trí phù hợp.

## 8. Đặt predicate vào đúng vị trí trong thứ tự case

Xét một bản phân loại có ba nhánh khách hàng:

```java
return switch (value) {
    case Customer(var name, var age, var tags)
            when eligibleCustomer(name, age, tags) -> "approved";
    case Customer(var name, var age, var tags)
            when age < 18 -> "underage";
    case Customer c -> "pending";
    case null -> "null";
    default -> "other";
};
```

Thứ tự ở đây có nghĩa:

1. Nếu là `Customer` và đủ điều kiện, chọn `approved`.
2. Nếu guard đầu sai và người đó dưới 18 tuổi, chọn `underage`.
3. Các `Customer` còn lại chọn `pending`.
4. `null` và các kiểu khác có fallback riêng.

Không đặt nhánh `case Customer c -> "pending"` lên trước. Pattern tổng quát **không có guard** bao phủ các nhánh khách hàng sau, khiến compiler báo lỗi dominance.

Tách một guard dài thành helper boolean **không phải lý do để tự thay đổi thứ tự các case**. Nếu cần phân loại lại ưu tiên, đó là thay đổi hành vi nghiệp vụ riêng, phải có test và review.

### Không nhầm guard `false` với nhánh `else` của `if`

Trong `switch`, khi `case Customer(...) when predicate(...)` khớp pattern nhưng predicate trả `false`, runtime tiếp tục xem xét nhãn khác. Nếu bạn chuyển logic predicate **vào thân của một case tổng quát** rồi trả luôn `pending`, bạn có thể làm bỏ qua các case sau vốn dùng guard khác, ví dụ `underage`. Hai cấu trúc chỉ tương đương nếu đã chứng minh tất cả nhánh còn lại có cùng kết quả.

### Guard bình thường và dominance

Nhánh có `when somePredicate(...)` trước một nhánh cùng kiểu không guard là cấu trúc hợp lệ. Compiler **không suy luận mọi ý nghĩa của predicate helper** để chứng minh nó luôn đúng. Tuy nhiên, một guard là constant `true` trong mã nguồn có xử lý dominance đặc biệt, gần như nhánh không guard. Đừng thay `when predicate(...)` bằng `when true` để "giảm complexity" khi vẫn cần nhánh phân loại phía sau.

## 9. Ví dụ Java 21 hoàn chỉnh: refactor và kiểm thử parity

Tạo tệp **`GuardPredicateDemo.java`**. Ví dụ này giữ riêng hai phương thức:

- `before(...)`: guard dài viết trực tiếp trong `when`.
- `after(...)`: guard được thay bằng các predicate có tên, giữ nguyên thứ tự nhánh và kết quả.

Chương trình cũng có `compact(...)` để minh họa cách chuyển sang `case Customer c when ...` khi muốn truyền dữ liệu của cả record qua accessor.

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Locale;

public class GuardPredicateDemo {
    record Customer(String name, int age, List<String> tags) {}
    record Invoice(String currency, BigDecimal total, boolean paid) {}

    static String before(Object value) {
        return switch (value) {
            case Customer(var name, var age, var tags)
                    when name != null && !name.isBlank()
                            && age >= 18 && tags != null
                            && tags.contains("ACTIVE") ->
                    "approved:" + name.trim();
            case Customer(var name, var age, var tags) when age < 18 ->
                    "underage";
            case Customer c -> "pending";
            case Invoice(var currency, var total, var paid)
                    when currency != null && !currency.isBlank()
                            && total != null && total.signum() > 0 && paid ->
                    "invoice:" + currency.toUpperCase(Locale.ROOT);
            case Invoice i -> "invoice-held";
            case null -> "null";
            default -> "other";
        };
    }

    static boolean validIdentity(String name, int age) {
        return name != null && !name.isBlank() && age >= 18;
    }

    static boolean hasActiveTag(List<String> tags) {
        return tags != null && tags.contains("ACTIVE");
    }

    static boolean eligibleCustomer(String name, int age, List<String> tags) {
        return validIdentity(name, age) && hasActiveTag(tags);
    }

    static boolean canIssueInvoice(
            String currency, BigDecimal total, boolean paid) {
        return currency != null && !currency.isBlank()
                && total != null && total.signum() > 0 && paid;
    }

    static String after(Object value) {
        return switch (value) {
            case Customer(var name, var age, var tags)
                    when eligibleCustomer(name, age, tags) ->
                    "approved:" + name.trim();
            case Customer(var name, var age, var tags) when age < 18 ->
                    "underage";
            case Customer c -> "pending";
            case Invoice(var currency, var total, var paid)
                    when canIssueInvoice(currency, total, paid) ->
                    "invoice:" + currency.toUpperCase(Locale.ROOT);
            case Invoice i -> "invoice-held";
            case null -> "null";
            default -> "other";
        };
    }

    static String compact(Object value) {
        return switch (value) {
            case Customer c when eligibleCustomer(c.name(), c.age(), c.tags()) ->
                    "approved";
            case Customer c -> "pending";
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object[] samples = {
            new Customer(" Linh ", 20, List.of("ACTIVE")),
            new Customer("Mai", 17, List.of("ACTIVE")),
            new Customer("", 22, List.of("ACTIVE")),
            new Customer("Ha", 22, List.of("GUEST")),
            new Customer(null, 22, List.of("ACTIVE")),
            new Customer("Long", 22, null),
            new Invoice("usd", new BigDecimal("120.00"), true),
            new Invoice("eur", BigDecimal.ZERO, true),
            new Invoice(null, BigDecimal.ONE, true),
            new Invoice("vnd", new BigDecimal("30"), false),
            null,
            123
        };
        for (Object value : samples) {
            String expected = before(value);
            String actual = after(value);
            if (!expected.equals(actual)) {
                throw new AssertionError("mismatch: " + value);
            }
            System.out.println(actual);
        }
        System.out.println("PARITY PASS: " + samples.length);
        System.out.println("compact: " +
                compact(new Customer(" Hoa ", 30, List.of("ACTIVE"))));
    }
}
```

Dùng JDK 21 trở lên:

```bash
javac --release 21 GuardPredicateDemo.java
java GuardPredicateDemo
```

**Đầu ra chính xác:**

```text
approved:Linh
underage
pending
pending
pending
pending
invoice:USD
invoice-held
invoice-held
invoice-held
null
other
PARITY PASS: 12
compact: approved
```

### Phân tích kết quả

- `approved:Linh`: tên có khoảng trắng đầu/cuối nhưng không blank, khách hàng đủ tuổi, có tag `ACTIVE`; cả bản inline lẫn bản predicate đồng ý.
- `underage`: nhánh đủ điều kiện trả `false` vì tuổi dưới 18; `switch` thử nhánh `when age < 18` tiếp theo.
- Bốn trường hợp `pending` cho thấy tên blank, không có tag `ACTIVE`, tên `null` và danh sách tag `null` đều được xử lý mà không gây `NullPointerException`.
- `invoice:USD`: hóa đơn có tiền tệ, số tiền dương và đã thanh toán; predicate invoice không có side effect. `toUpperCase(Locale.ROOT)` chỉ chạy trong nhánh đã match và guard trả `true`.
- Ba trường hợp `invoice-held`: tổng bằng 0, tiền tệ `null` hoặc `paid == false`.
- `null` và `other`: selector `null` được xử lý riêng, còn kiểu không phải `Customer` hoặc `Invoice` đi vào `default`.
- Dòng `PARITY PASS: 12` xuất hiện sau khi so sánh kết quả của **12 input** ở hai cách cài; nếu khác biệt, chương trình ném `AssertionError` thay vì báo đạt.
- `compact: approved` minh họa khả năng dùng type pattern `Customer c` rồi gọi helper với các component lấy qua accessor.

**Giới hạn của ví dụ:** 12 mẫu chứng minh kết quả của đúng các trường hợp đã thử, không bảo đảm mọi trạng thái production đều tương đương. Nếu record có custom accessor, đối tượng mutable hoặc logic liên quan I/O, cần thêm test theo rủi ro.

## 10. Tách guard trong `instanceof` và các biểu thức khác

Ngoài pattern `switch`, cách đặt tên predicate cũng hữu ích với `instanceof`:

```java
if (value instanceof Customer(var name, var age, var tags)
        && eligibleCustomer(name, age, tags)) {
    System.out.println("approved");
}
```

Đây là mã minh họa bên trong phương thức đã có `value` và khai báo `Customer`. Vế phải của `&&` chỉ được đánh giá khi pattern match và các biến `name`, `age`, `tags` đã bind.

Không viết:

```java
// CỐ Ý SAI: when không phải cú pháp bổ sung cho instanceof.
if (value instanceof Customer c when eligibleCustomer(c)) {
    // ...
}
```

Trong toán tử ba ngôi cũng có thể tái sử dụng predicate:

```java
return value instanceof Customer(var name, var age, var tags)
        && eligibleCustomer(name, age, tags)
        ? "approved" : "pending";
```

Ví dụ `return` trên thuộc ngữ cảnh phương thức trả `String`. Nếu có nhiều nhánh theo các kiểu khác nhau, `switch` expression với `when` thường rõ hơn nhiều toán tử ba ngôi lồng nhau.

**Khác biệt ngữ nghĩa:** `instanceof` trả `false` với input `null`; trong pattern `switch`, selector `null` thường cần `case null` để trả kết quả thay vì ném `NullPointerException`. Khi chuyển qua lại giữa `if` và `switch` để cải thiện readability, phải kiểm tra lại hành vi `null`.

## 11. Unit test predicate và kiểm tra hành vi trước/sau

Predicate nhỏ có lợi thế là test riêng được, nhưng test đơn lẻ **không thay thế** test trên `switch` đầy đủ. Nên kiểm tra cả:

| Nhóm | Input đại diện | Kỳ vọng |
| --- | --- | --- |
| Match khách hàng hợp lệ | Tên nonblank, tuổi 18+, tag `ACTIVE` | Predicate `true`; nhánh `approved` |
| Tên `null` hoặc blank | `null`, `""`, `"  "` | Predicate `false`; không ném NPE |
| Tuổi biên | 17, 18, 19 | 17 thất bại; 18 trở lên còn tùy tiêu chí khác |
| Tags thiếu | `null`, list rỗng, list không `ACTIVE` | Predicate `false` |
| Hóa đơn thiếu dữ liệu | `currency == null` hoặc `total == null` | `false`, không gọi method trên `null` |
| Hóa đơn số tiền | âm, 0, dương | Chỉ dương có thể qua guard |
| Hóa đơn chưa trả | `paid == false` | `false` |
| Đầu vào kiểu khác | `Integer`, `String` | Không gọi Customer/Invoice predicate; nhánh `default` |
| Selector `null` | `null` | Nhánh `case null` theo hợp đồng |
| Guard chồng lấn | Khách hàng thiếu điều kiện và dưới 18 | Nhánh `underage` phải được chọn sau khi guard trước trả `false` |
| Custom accessor/side effect | Record có accessor đếm lần gọi | Không thay đổi số lần/thứ tự đọc nếu hợp đồng yêu cầu |

### Kiểm thử parity

Một cách thực tế là giữ bản logic inline làm baseline tạm thời trong test, chạy cùng danh sách input qua hai phiên bản và so:

1. **Giá trị trả về** và nhánh được chọn.
2. **Loại và điều kiện phát sinh exception** với đầu vào sai/thiếu.
3. **Thứ tự/số lần gọi** đến dependency hoặc accessor có side effect.
4. **Dữ liệu mutable** có bị thay đổi khác đi hay không.

Khi kết quả khác nhau, đừng sửa expected output chỉ để test xanh. Xác định nguyên nhân: có đổi thứ tự điều kiện, cách truyền tham số, hàm kiểm tra `null`, hoặc độ ưu tiên nhánh không?

Các test nên có một vài ca **guard trả `true`**, **guard trả `false`**, **pattern không match**, **selector `null`**, và các giá trị biên. Nếu ứng dụng dùng Maven/Gradle, đưa bộ test vào CI cùng cấu hình Java thực tế của dự án.

## 12. Hướng dẫn review và tiêu chí hoàn tất refactor

Một pull request tách guard dài nên dễ đánh giá qua các câu hỏi:

- [ ] Tên predicate mô tả **quy tắc nghiệp vụ**, không phải chi tiết mơ hồ như `condition1`.
- [ ] Phần điều kiện được chuyển vào helper **giữ nguyên ý nghĩa**, không đổi ngưỡng/định dạng hoặc mở rộng quyền.
- [ ] Pattern, thứ tự case, kết quả nhánh và cách xử lý `null` được giữ nguyên.
- [ ] Có bảo toàn short-circuit và thứ tự đánh giá không? Có chuyển biểu thức có side effect thành **đối số được tính sớm** không?
- [ ] Biến pattern ở `when`/`&&` luôn nằm trong phạm vi hợp lệ.
- [ ] Null check xuất hiện trước mọi thao tác dereference có thể gây NPE.
- [ ] Predicate không giấu hành vi ghi dữ liệu, I/O hoặc exception ngoài dự kiến.
- [ ] Chữ ký helper hợp lý (component hoặc record), tránh quá nhiều tham số cùng kiểu và tránh đọc accessor dư thừa.
- [ ] Không có nhánh dominated; trường hợp guard sai vẫn được xử lý bởi case tiếp theo như trước.
- [ ] Predicate được test riêng ở ranh giới quan trọng và toàn bộ switch có regression/differential tests.
- [ ] Build theo Java version mục tiêu; formatter, static checks và CI liên quan đạt.
- [ ] Diff gọn, không trộn logic mới ngoài phạm vi "tăng tính dễ đọc".

**Tiêu chí DONE:** Người review nhìn vào `case ... when eligibleCustomer(...)` là hiểu ý định, mở helper sẽ thấy quy tắc được đặt tên/tách hợp lý, và có bằng chứng rằng mã sau refactor vẫn trả cùng kết quả cho các trường hợp trong hợp đồng.

### Khi nào *không cần* tách guard?

Một guard ngắn và dễ hiểu như `when x == y` trong `case Point(var x, var y)` thường đã rõ nghĩa. Tạo `isSameCoordinate(x, y)` chỉ để che một phép so đơn giản có thể làm code **kém đọc hơn**. Nên trích xuất khi logic đủ dài, lặp nhiều nơi, có tên miền nghiệp vụ tự nhiên, hoặc cần unit test độc lập.

Đừng dùng số dòng cố định như một quy tắc máy móc. Tiêu chí quan trọng hơn là mức độ **dễ hiểu, nhất quán và có thể kiểm thử**.

## 13. Sai lầm thường gặp

### Sai lầm 1: Tách ra nhưng chỉ đổi tên hình thức

`checkAllConditions(name, age, tags)` không cung cấp thêm nhiều thông tin. Nếu domain gọi trạng thái này là "khách hàng đủ điều kiện", `eligibleCustomer(...)` giúp người đọc nhìn ngay kết quả mong muốn.

### Sai lầm 2: Helper trả `void` hoặc đối tượng thay vì boolean

`when` cần biểu thức boolean; không thể gọi một helper trả `void` hay đặt nguyên `Predicate<Customer>` sau `when`. Khi dùng `Predicate<T>`, phải gọi `.test(value)`.

### Sai lầm 3: Làm đổi thời điểm tính toán khi truyền đối số

Chuyển `name != null && expensiveCheck()` thành `isValid(name, expensiveCheck())` làm `expensiveCheck()` chạy trước khi helper thực hiện null check. Đây không phải refactor bảo toàn hành vi.

### Sai lầm 4: Di chuyển helper có side effect ra khỏi guard

Nếu chuyển từ `when expensivePredicate(value)` sang tính sẵn `boolean ok = expensivePredicate(value)` trước `switch`, helper có thể được gọi **ngay cả khi pattern không match**. Điều này đổi chi phí, exception hoặc log. Cần đánh giá chứ không tự xem là tương đương.

### Sai lầm 5: Dùng record type pattern và deconstruction lẫn lộn không kiểm tra

`case Customer c` và `case Customer(var name, var age, var tags)` khác cách lấy component. Nếu accessor được override, việc chuyển giữa hai dạng có thể tác động đến lần gọi và exception. Đối với một refactor guard đơn thuần, giữ nguyên pattern ban đầu là lựa chọn an toàn.

### Sai lầm 6: Đặt nhánh tổng quát lên trước nhánh có guard

`case Customer c -> ...` trước `case Customer c when eligibleCustomer(c) -> ...` khiến nhánh thứ hai bị che và compiler báo dominance. Nhánh đặc biệt phải đứng trước nhánh tổng quát.

### Sai lầm 7: Hàm predicate xử lý luôn nghiệp vụ

Một hàm tên `canIssueInvoice` nên trả boolean, không tự thực hiện thanh toán, ghi cơ sở dữ liệu hoặc gửi email. Guard thích hợp cho **phân loại/quyết định**, không phải nơi giấu các hành động khó hoàn tác.

### Sai lầm 8: Chỉ test predicate, bỏ qua hành vi cả switch

Một predicate có thể đúng đơn lẻ, nhưng kết quả của switch còn phụ thuộc **pattern match, thứ tự case, guard khác, null/default**. Cần test cả phương thức chứa switch.

## 14. Câu hỏi tự kiểm tra

**1. Vì sao `when eligibleCustomer(name, age, tags)` thường dễ đọc hơn một chuỗi `&&` dài?**  
Vì tên phương thức bộc lộ ý nghĩa nghiệp vụ; người đọc có thể kiểm tra chi tiết trong helper khi cần.

**2. Có bắt buộc phải khai báo `Predicate<Customer>` khi muốn tách guard không?**  
Không. Một phương thức `static boolean eligibleCustomer(...)` là đủ và thường đơn giản hơn.

**3. Với `case Customer(var name, var age, var tags) when ...`, khi nào guard được gọi?**  
Chỉ khi record pattern đã match và các biến đã được bind.

**4. Vì sao `case Customer c when ELIGIBLE` không biên dịch nếu `ELIGIBLE` thuộc kiểu `Predicate<Customer>`?**  
Vì đối tượng `Predicate` không phải boolean; phải dùng `ELIGIBLE.test(c)`.

**5. Khi `name == null`, có an toàn nếu predicate viết `name != null && !name.isBlank()` không?**  
Có; `&&` bỏ qua vế sau khi vế trước sai.

**6. Vì sao truyền `expensiveCheck()` vào đối số helper có thể đổi hành vi?**  
Java đánh giá đối số trước lời gọi phương thức; lệnh tốn kém có thể chạy dù null check trong helper sẽ trả `false`.

**7. Nếu guard đầu trả `false`, `switch` có thể vào case cùng record nhưng không guard ở phía dưới không?**  
Có. Đây là cách xây dựng nhánh phân loại cụ thể rồi fallback tổng quát.

**8. Với một guard chỉ là `when x == y`, luôn cần tách thành method `same(x,y)` không?**  
Không. Guard ngắn và rõ có thể để nguyên; chỉ tách khi cải thiện khả năng đọc hoặc kiểm thử.

**9. Bản refactor trả giống nhau trên 12 ca thử đã chứng minh tương đương hoàn toàn chưa?**  
Chưa. Còn các đường đi, dữ liệu biên, exception và side effect chưa được thử.

**10. Vì sao predicate nên thuần và không làm thay đổi trạng thái?**  
Giúp guard dễ dự đoán, dễ tái sử dụng và kiểm thử; tránh các tác dụng phụ phụ thuộc thứ tự các case.

## Tham khảo

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java SE 21 API — java.util.function.Predicate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/function/Predicate.html)
- [JLS SE 21 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
