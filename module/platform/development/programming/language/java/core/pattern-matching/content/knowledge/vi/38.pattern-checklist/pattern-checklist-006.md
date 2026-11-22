# Checklist record pattern trong Java 21+: kiểm tra cú pháp, kiểu, null và hành vi

## 1. Dùng checklist này khi nào?

**Record pattern** là cú pháp kiểm tra cấu trúc và tách các component của một Java `record`. Khác với việc chỉ xác định “đối tượng có phải `Receipt` không?”, record pattern còn giúp lấy những dữ liệu bên trong ngay tại nơi match:

```java
// Đoạn minh họa đặt trong phương thức có Object input.
if (input instanceof Receipt(var number, Amount(var cents, var currency))) {
    System.out.println(number + ":" + cents + ":" + currency);
}
```

Đoạn trên yêu cầu một `Receipt` thực sự có component `amount` là một `Amount` khác `null`, rồi ràng buộc các component `number`, `cents`, `currency`. **Match thành công chưa chứng minh dữ liệu hợp lệ theo nghiệp vụ:** `number` hoặc `currency` vẫn có thể `null` vì các biến `var` có thể chứa null nếu component tương ứng là kiểu tham chiếu.

Bài thuộc nhóm **Checklist pattern**. Mục tiêu là có một quy trình review có thể sử dụng **trước khi viết, khi biên dịch, khi kiểm thử và trước khi merge** một đoạn `instanceof` hoặc `switch` chứa record patterns. Checklist tập trung vào những lỗi dễ bị bỏ qua: sai thứ tự/arity của component, suy luận kiểu, các tầng null, guard, thứ tự case, exhaustiveness, generic erasure, invariant và kiểm thử.

**Phiên bản:** record declaration chính thức từ Java 16 (JEP 395); record patterns chính thức từ **Java 21** (JEP 440); pattern matching for `switch` cũng chính thức từ Java 21 (JEP 441). Cần **JDK 21 trở lên** để chạy chương trình hoàn chỉnh của bài, không cần `--enable-preview`. `instanceof` type patterns có từ Java 16, nhưng `Receipt(var number, ...)` là **record pattern** và không phải cú pháp final trên Java 16/17.

## 2. Checklist nhanh: 24 câu hỏi trước khi chấp nhận một record pattern

Có thể đánh dấu từng ô sau khi kiểm tra bằng source code, compiler hoặc test.

### A. Kiểu và cấu trúc record

- [ ] **A1.** Biểu thức cần match đúng **record type**, không nhầm một class thường với record có thể deconstruct.
- [ ] **A2.** Mỗi `RecordType(...)` có **đúng số lượng pattern con** bằng số record components.
- [ ] **A3.** Thứ tự pattern con tương ứng **thứ tự khai báo components**, không suy diễn từ tên biến.
- [ ] **A4.** Kiểu của mỗi pattern con tương thích với kiểu component; `var` được compiler suy luận kiểu tĩnh chính xác.
- [ ] **A5.** Chỉ lồng tới tầng thật sự cần dùng; không phụ thuộc sâu vào schema khi chỉ cần một value object hoặc accessor có tên.

### B. Null và kiểm tra giá trị

- [ ] **B1.** Đã xác định chính sách khi **selector gốc `null`**: `instanceof` không match; `switch` có xử lý null phù hợp.
- [ ] **B2.** Đã kiểm tra trường hợp **record con bằng `null`**: nested record pattern tại tầng ấy không match.
- [ ] **B3.** Đã kiểm tra trường hợp **component tham chiếu bằng `null`** nhưng được lấy bằng `var`: record pattern vẫn có thể match.
- [ ] **B4.** Dữ liệu nghiệp vụ (mã, số tiền, đơn vị, khoảng giá trị) có validator/guard rõ ràng, không coi “match” là “valid”.
- [ ] **B5.** Các guard gọi phương thức trên component tham chiếu **sau khi kiểm tra null** và không thay đổi chính sách của nhánh do vô ý.

### C. Flow, switch và generic

- [ ] **C1.** Biến pattern chỉ được dùng ở những vị trí hợp lệ theo **flow scoping**; không dùng sau nhánh có thể không match.
- [ ] **C2.** Trong `instanceof`, điều kiện tiếp theo đặt ở vế phải của `&&` khi cần biến đã match; không tùy tiện dùng `||`.
- [ ] **C3.** Với `switch`, các case **cụ thể/guarded trước case tổng quát**, tránh dominance.
- [ ] **C4.** Nếu selector là sealed hierarchy, `switch expression` xử lý đủ biến thể; không thêm `default` chỉ để che lỗi thiếu case.
- [ ] **C5.** Guard của pattern case Java 21 dùng **`when`**, khác `&&` trong biểu thức Boolean chứa `instanceof`.
- [ ] **C6.** Generic record pattern dùng đúng ngữ cảnh kiểu tĩnh; không dùng `instanceof Packet<Receipt>` trên `Object` như thể generic argument kiểm tra được runtime.

### D. Kiểm thử và khả năng bảo trì

- [ ] **D1.** Có ca hợp lệ cho mỗi pattern/case cần xử lý.
- [ ] **D2.** Có ca `null` cho selector và từng record con quan trọng, cùng các component nullable.
- [ ] **D3.** Có ca guard thất bại nhưng cấu trúc record vẫn match, để phân biệt **non-match cấu trúc** với **giá trị không hợp lệ**.
- [ ] **D4.** Có ca phủ định cho sai arity, case bị che, switch không exhaustive hoặc generic runtime-check sai.
- [ ] **D5.** Ví dụ có expected output và assertion; không chỉ in giá trị rồi tự đoán là đúng.
- [ ] **D6.** Đã review sự phụ thuộc vào số lượng/thứ tự component khi record schema thay đổi; với component cùng kiểu, lỗi đảo tên có thể vẫn biên dịch.
- [ ] **D7.** Đã xác định nơi giữ invariant: constructor/factory/boundary validation, thay vì lặp guard thiếu nhất quán ở mọi nơi.
- [ ] **D8.** Nếu nested pattern khó debug hoặc nhiều case, đã cân nhắc tách bước/đặt helper có tên và kiểm thử tương đương.

Checklist trên là **tiêu chí review có chủ đích**, không phải danh sách điều kiện do trình biên dịch Java tự kiểm toàn bộ. Compiler giải quyết rất tốt A2–A4 và nhiều lỗi C1/C3/C4; các mục về domain, null policy, test và readability vẫn là trách nhiệm của lập trình viên.

## 3. Model thực hành để dùng checklist

Để thấy rõ sự khác biệt giữa **match cấu trúc** và **validation**, ví dụ chủ động dùng record có thể tạo dữ liệu không hợp lệ:

```java
sealed interface Event permits Paid, Rejected, Pending {}

record Amount(long cents, String currency) {}
record Receipt(String number, Amount amount) {}

record Paid(String orderId, Receipt receipt) implements Event {}
record Rejected(String orderId, String reason) implements Event {}
record Pending(String orderId) implements Event {}

record Packet<T>(T data) {}
```

Đây là **đoạn khai báo minh họa**, không phải file độc lập. Chương trình đầy đủ ở mục 9.

Trong mô hình này:

- `Paid` có mã đơn và `Receipt`.
- `Receipt` có số tham chiếu và `Amount`.
- `Amount` có số tiền đơn vị nhỏ nhất (`cents`) và mã tiền tệ dạng chuỗi.
- `Rejected` có lý do bị từ chối.
- `Pending` chỉ có mã đơn.
- `Packet<T>` giúp kiểm tra record pattern trong ngữ cảnh **generic**.

**Không có compact constructors trong ví dụ học tập**: `new Receipt("R-1", null)`, `new Rejected("O-2", " ")` và `new Amount(0, "USD")` đều được tạo để kiểm thử nhánh guard/fallback. Trong một domain model production, các trạng thái bất hợp lệ nên thường bị ngăn chặn sớm tại constructor/factory hoặc ranh giới chuyển dữ liệu. Không sao chép trực tiếp model cố tình cho phép trạng thái sai này vào hệ thống thanh toán thật.

## 4. A1–A5: kiểm tra đúng cấu trúc, số lượng và kiểu component

### 4.1. Record pattern dựa vào khai báo record, không dựa vào tên biến

`Receipt` khai báo:

```java
record Receipt(String number, Amount amount) {}
```

Pattern hợp lệ:

```java
// Hợp lệ: hai pattern con ứng với number, amount.
if (input instanceof Receipt(var number, var amount)) {
    // number có kiểu String, amount có kiểu Amount.
}
```

Và pattern lồng:

```java
if (input instanceof Receipt(var number,
        Amount(var cents, var currency))) {
    // cents có kiểu long, currency có kiểu String.
}
```

**Checklist A2:** `Receipt` có **hai** component, `Amount` có **hai** component. Vì vậy `Receipt(var number)` hoặc `Amount(var cents)` thiếu một pattern con và bị compiler từ chối.

**Checklist A3:** Java match component theo **vị trí**. Viết `Receipt(var amount, var number)` vẫn có thể biên dịch vì `var` chấp nhận suy luận kiểu tương ứng, nhưng biến tên `amount` khi ấy thực chất nhận `String number` và biến tên `number` nhận `Amount amount`. Đây là lỗi đọc hiểu/đặt tên có thể **không** bị compiler bắt. Đặt tên biến phản ánh chính xác component ở vị trí đó.

**Checklist A4:** với `Amount(var cents, var currency)`, `cents` mang kiểu `long`, `currency` mang kiểu `String`. Không được giả định `var` là biến dynamic có thể gọi mọi phương thức. `cents.toUpperCase()` là lỗi biên dịch vì primitive `long` không có method.

### 4.2. Có thực sự cần lồng sâu?

Nếu chỉ cần `Receipt.number`, cân nhắc:

```java
// Trong ngữ cảnh Paid paid đã có kiểu.
String number = paid.receipt() == null
        ? null : paid.receipt().number();
```

Hoặc một pattern chỉ sâu tới `Receipt`:

```java
if (input instanceof Paid(var id, Receipt(var number, var amount))) {
    System.out.println(number);
}
```

Không cần lồng tiếp `Amount(var cents, var currency)` nếu không sử dụng dữ liệu tiền tệ. Mỗi record pattern thêm vào vừa cung cấp dữ liệu, vừa yêu cầu record con tại vị trí đó **khác null**, và tăng phụ thuộc vào số component của schema. Độ sâu cần được quyết định bởi **mục tiêu của nhánh**, không phải vì muốn dùng tối đa cú pháp.

## 5. B1–B5: bảng kiểm null theo từng tầng

So sánh bốn input:

```java
Paid full = new Paid("O-1",
        new Receipt("R-1", new Amount(450, "USD")));

Paid emptyAmount = new Paid("O-4",
        new Receipt("R-4", null));

Paid emptyReceipt = new Paid("O-5", null);

Paid nullableCurrency = new Paid("O-6",
        new Receipt("R-6", new Amount(450, null)));
```

Và pattern:

```java
Paid(var id, Receipt(var no, Amount(var cents, var currency)))
```

| Input | Pattern sâu có match? | Giải thích |
| --- | --- | --- |
| `full` | Có | `Paid`, `Receipt`, `Amount` đều khác null và đúng kiểu |
| `emptyAmount` | Không | Record con `Amount(...)` cần một đối tượng `Amount`, không thể match null |
| `emptyReceipt` | Không | Record con `Receipt(...)` cần một đối tượng `Receipt`, không thể match null |
| `nullableCurrency` | **Có** | `Amount` tồn tại; `var currency` có thể nhận null |
| Selector `null` trong `instanceof` | Không | `null instanceof Pattern` trả `false` |
| Selector `null` trong `switch` có `case null` | Đi vào `case null` | Chính sách xử lý null được khai báo rõ |

**Điểm thường sai nhất:** `Record(var component)` không tự từ chối component null; chỉ record pattern con `NestedRecord(...)` mới cần một record con khác null để match. Hãy test riêng hai trường hợp để tránh lỗi xử lý thiếu dữ liệu.

Với **guard**:

```java
case Paid(var id, Receipt(var no, Amount(var cents, var currency)))
        when cents > 0 && currency != null
                && currency.matches("[A-Z]{3}") -> ...
```

Đây là đoạn **một case trong switch Java 21**, không phải file Java độc lập. Kiểm tra `currency != null` đứng trước `currency.matches(...)` để tránh gọi method trên null. `cents > 0` là quy tắc của ví dụ; không áp dụng cho mọi khoản tiền trong mọi miền nghiệp vụ (ví dụ hoàn tiền và điều chỉnh có thể dùng model khác).

Regex `[A-Z]{3}` chỉ kiểm tra định dạng ba chữ cái in hoa, **không xác minh đó là một mã ISO 4217 tồn tại**. Nếu domain yêu cầu mã tiền tệ thực, cần xác thực danh mục riêng.

## 6. C1–C5: phân biệt `instanceof`, `switch`, `when` và thứ tự case

### 6.1. Flow scoping với instanceof

```java
if (value instanceof Paid(var id,
        Receipt(var no, Amount(var cents, var currency)))
        && id != null && !id.isBlank() && cents > 0) {
    System.out.println(id + ":" + cents);
}
```

Các biến `id`, `no`, `cents`, `currency` chỉ hợp lệ ở các vị trí mà compiler biết record pattern đã match. `&&` short-circuit bảo đảm guard được đánh giá **sau khi** pattern khớp. Không dùng biến `id` sau khối `if` trong trường hợp compiler không thể chứng minh pattern đã thành công trên mọi đường đi.

Đừng nhầm cú pháp:

- Trong `instanceof`: `value instanceof Paid(...) && validCondition` — `&&` là **toán tử Boolean nằm ngoài pattern**.
- Trong case của `switch` Java 21: `case Paid(...) when validCondition -> ...` — `when` là **guard của case label**.

Cú pháp cũ kiểu `case String s && ... ->` từng xuất hiện trong preview ở các JDK cũ; **không phải cú pháp Java 21 final**.

### 6.2. Thứ tự case từ cụ thể đến tổng quát

Xét một `switch` trên `Event`:

```java
return switch (event) {
    case Paid(var id, Receipt(var no, Amount(var cents, var currency)))
            when cents > 0 && currency != null
                    && currency.matches("[A-Z]{3}") ->
            "paid:" + id + ":" + no + ":" + cents + ":" + currency;

    case Paid(var id, Receipt(var no, var amount)) ->
            "paid:invalid-amount";

    case Paid(var id, var receipt) ->
            "paid:missing-receipt";

    case Rejected(var id, var reason)
            when reason != null && !reason.isBlank() ->
            "rejected:" + id + ":" + reason;

    case Rejected(var id, var reason) ->
            "rejected:invalid-reason";

    case Pending(var id) -> "pending:" + id;
    case null -> "missing";
};
```

Đoạn trên nằm trong phương thức `String summarize(Event event)` của chương trình mục 9.

Ba case cho `Paid` phân loại có chủ đích:

1. `Paid` có cả `Receipt` và `Amount`, **đủ điều kiện guard**: trả thông tin thanh toán.
2. `Paid` có `Receipt` nhưng **không đạt case trước**: trả `paid:invalid-amount`. Trong demo, trường hợp này gồm `Amount` null hoặc số tiền/mã tiền tệ không đạt guard.
3. `Paid` còn lại: vì `Receipt(...)` ở hai case trên đều không khớp, trường hợp còn lại theo model là `receipt == null`, trả `paid:missing-receipt`.

**Dominance:** nếu đặt `case Paid(var id, var receipt)` lên đầu, nó bao phủ mọi `Paid`, các case cụ thể phía dưới có thể bị compiler từ chối do đã bị che khuất. Vì vậy checklist C3 cần xem **thứ tự của tất cả pattern labels**, không chỉ một case riêng lẻ.

**Không đồng nhất fallback với validation đầy đủ:** case `paid:invalid-amount` đang gộp nhiều nguyên nhân. Nếu API cần trả lỗi chi tiết (zero, currency format, amount null), cần thêm validation cụ thể hoặc kiểu kết quả khác. Mặt khác, không nhất thiết phải tạo một case cho từng điều kiện nếu business logic chỉ cần biết “không dùng được”.

### 6.3. Exhaustiveness của sealed hierarchy

`Event` là sealed interface với ba record subtype cuối cùng: `Paid`, `Rejected`, `Pending`. Các case của `summarize` xử lý đủ ba biến thể cùng `case null`; đây là một **switch expression** không cần `default`.

Nếu thêm subtype mới `Canceled` vào `permits`, trình biên dịch có thể yêu cầu cập nhật các `switch expression` chưa bao phủ subtype ấy. Đó là lợi ích của một hierarchy cố ý đóng.

Một `default -> "other"` được thêm chỉ để dễ biên dịch có thể che yêu cầu cập nhật logic khi model thay đổi. Tuy nhiên, với API cố tình mở rộng hoặc cần fallback thực, `default` có thể phù hợp; hãy review rõ chính sách.

`case null` xử lý **selector null**, không làm hợp lệ mọi component null bên trong các record.

## 7. C6: checklist cho generic record patterns

Generic record:

```java
record Packet<T>(T data) {}
```

Khi tham số phương thức là `Packet<Receipt> packet`, compiler có thông tin kiểu tĩnh để suy luận một record pattern:

```java
// Trong phương thức nhận Packet<Receipt> packet.
return switch (packet) {
    case Packet(Receipt(var no, Amount(var cents, var currency))) ->
            "packet:" + no + ":" + cents;
    case Packet(var receipt) -> "packet:unavailable";
    case null -> "packet:missing";
};
```

Ví dụ này sẽ có mặt trong chương trình chạy ở mục 9. Case sâu cần `Packet`, `Receipt` và `Amount` tồn tại, còn case `Packet(var receipt)` có thể match kể cả khi component `data == null`. Hai case cần đúng thứ tự.

**Điều compiler suy luận không có nghĩa JVM kiểm chứng mọi generic type arguments lúc runtime.** Từ một biến `Object input`, không thể hợp thức hóa kiểu `Packet<Receipt>` bằng phép thử `input instanceof Packet<Receipt> p` như thể generic argument `Receipt` còn được giữ đầy đủ ở runtime.

Nếu nhận dữ liệu không tin cậy qua `Object`, có thể dùng:

```java
// Đoạn minh họa trong phương thức có Object input.
if (input instanceof Packet<?> packet) {
    Object data = packet.data();
    if (data instanceof Receipt(var no, var amount)) {
        System.out.println(no);
    }
}
```

`Packet<?>` kiểm tra được kiểu record gốc với tham số chưa biết; `Receipt(...)` kiểm tra riêng thành phần. Nếu có tập phần tử sâu hơn như `List<Receipt>`, còn phải cân nhắc **erasure và validate từng phần tử**, không suy luận an toàn từ một type tag ngoài mạng.

## 8. Thiết kế test matrix từ checklist

Trước khi viết source hoàn chỉnh, xác định đầu vào và đầu ra mong đợi:

| Ca | Đầu vào | Kết quả mong đợi | Checklist |
| --- | --- | --- | --- |
| Thanh toán hợp lệ | `Paid("O-1", Receipt("R-1", Amount(450,"USD")))` | `paid:O-1:R-1:450:USD` | A/B/C/D |
| Số tiền bằng 0 | `Paid(...Amount(0,"USD"))` | `paid:invalid-amount` | B4, D3 |
| Thiếu Amount | `Paid(...Receipt("R-4", null))` | `paid:invalid-amount` | B2, D2 |
| Thiếu Receipt | `Paid("O-5", null)` | `paid:missing-receipt` | B2, D2 |
| Rejected hợp lệ | `Rejected("O-2","out-of-stock")` | `rejected:O-2:out-of-stock` | C3, D1 |
| Reason blank | `Rejected("O-2"," ")` | `rejected:invalid-reason` | B4, D3 |
| Pending | `Pending("O-3")` | `pending:O-3` | C4, D1 |
| Event gốc null | `summarize(null)` | `missing` | B1 |
| Instanceof hợp lệ | Paid hợp lệ | `inspected:O-1:450` | C1/C2 |
| Instanceof Amount null | Paid có Amount null | `no-match` | B2 |
| Instanceof Receipt null | Paid có Receipt null | `no-match` | B2 |
| Instanceof sai kiểu | `"unexpected"` | `no-match` | A1 |
| Packet hợp lệ | `Packet<Receipt>` có Amount | `packet:R-1:450` | C6 |
| Packet có Amount null | `Packet<Receipt>` chứa Receipt nhưng amount null | `packet:unavailable` | B2/C6 |
| Packet gốc null | `packetInfo(null)` | `packet:missing` | B1/C6 |

Chương trình sau có **15 lời gọi `check`**. Mỗi `check` tự so sánh expected và actual; nếu khác, nó ném `AssertionError`. Vì vậy chỉ in `15/15 checks passed` khi toàn bộ test phía trước thành công.

## 9. Chương trình độc lập: kiểm thử toàn bộ checklist trên Java 21+

Tạo file **`RecordPatternChecklistDemo.java`**:

```java
public class RecordPatternChecklistDemo {
    sealed interface Event permits Paid, Rejected, Pending {}

    record Amount(long cents, String currency) {}
    record Receipt(String number, Amount amount) {}
    record Paid(String orderId, Receipt receipt) implements Event {}
    record Rejected(String orderId, String reason) implements Event {}
    record Pending(String orderId) implements Event {}
    record Packet<T>(T data) {}

    static String summarize(Event event) {
        return switch (event) {
            case Paid(var id, Receipt(var no, Amount(var cents, var currency)))
                    when cents > 0 && currency != null
                            && currency.matches("[A-Z]{3}") ->
                    "paid:" + id + ":" + no + ":" + cents + ":" + currency;

            case Paid(var id, Receipt(var no, var amount)) ->
                    "paid:invalid-amount";

            case Paid(var id, var receipt) ->
                    "paid:missing-receipt";

            case Rejected(var id, var reason)
                    when reason != null && !reason.isBlank() ->
                    "rejected:" + id + ":" + reason;

            case Rejected(var id, var reason) ->
                    "rejected:invalid-reason";

            case Pending(var id) -> "pending:" + id;
            case null -> "missing";
        };
    }

    static String inspect(Object value) {
        if (value instanceof Paid(var id,
                Receipt(var no, Amount(var cents, var currency)))
                && id != null && !id.isBlank() && cents > 0) {
            return "inspected:" + id + ":" + cents;
        }
        return "no-match";
    }

    static String packetInfo(Packet<Receipt> packet) {
        return switch (packet) {
            case Packet(Receipt(var no, Amount(var cents, var currency))) ->
                    "packet:" + no + ":" + cents;
            case Packet(var receipt) -> "packet:unavailable";
            case null -> "packet:missing";
        };
    }

    static void check(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        System.out.println(label + " -> " + actual);
    }

    public static void main(String[] args) {
        Paid paid = new Paid("O-1",
                new Receipt("R-1", new Amount(450, "USD")));
        Paid zero = new Paid("O-0",
                new Receipt("R-0", new Amount(0, "USD")));
        Paid nullAmount = new Paid("O-4",
                new Receipt("R-4", null));
        Paid nullReceipt = new Paid("O-5", null);

        check("paid", "paid:O-1:R-1:450:USD", summarize(paid));
        check("zero", "paid:invalid-amount", summarize(zero));
        check("null-amount", "paid:invalid-amount",
                summarize(nullAmount));
        check("null-receipt", "paid:missing-receipt",
                summarize(nullReceipt));
        check("rejected", "rejected:O-2:out-of-stock",
                summarize(new Rejected("O-2", "out-of-stock")));
        check("bad-reason", "rejected:invalid-reason",
                summarize(new Rejected("O-2", " ")));
        check("pending", "pending:O-3",
                summarize(new Pending("O-3")));
        check("root-null", "missing", summarize(null));

        check("inspect-paid", "inspected:O-1:450", inspect(paid));
        check("inspect-no-amount", "no-match",
                inspect(nullAmount));
        check("inspect-no-receipt", "no-match",
                inspect(nullReceipt));
        check("inspect-not-paid", "no-match",
                inspect("unexpected"));

        check("packet-paid", "packet:R-1:450",
                packetInfo(new Packet<>(paid.receipt())));
        check("packet-null-amount", "packet:unavailable",
                packetInfo(new Packet<>(nullAmount.receipt())));
        check("packet-null", "packet:missing", packetInfo(null));

        System.out.println("15/15 checks passed");
    }
}
```

**Biên dịch/chạy bằng JDK 21+:**

```bash
javac --release 21 RecordPatternChecklistDemo.java
java RecordPatternChecklistDemo
```

**Stdout chính xác, đã đối chiếu trên JDK 24:**

```text
paid -> paid:O-1:R-1:450:USD
zero -> paid:invalid-amount
null-amount -> paid:invalid-amount
null-receipt -> paid:missing-receipt
rejected -> rejected:O-2:out-of-stock
bad-reason -> rejected:invalid-reason
pending -> pending:O-3
root-null -> missing
inspect-paid -> inspected:O-1:450
inspect-no-amount -> no-match
inspect-no-receipt -> no-match
inspect-not-paid -> no-match
packet-paid -> packet:R-1:450
packet-null-amount -> packet:unavailable
packet-null -> packet:missing
15/15 checks passed
```

Chương trình đã được **thực thi bằng JShell JDK 24**, sử dụng cú pháp đã final từ Java 21, và đạt đúng 15/15 kết quả mong đợi. Cặp phương thức `summarize`/`inspect` có **tiêu chí khác nhau**: `summarize` yêu cầu mã currency có dạng hợp lệ, trong khi `inspect` chỉ kiểm tra ID và số tiền dương. Đây là **sự khác nhau về hợp đồng**, được đặt có chủ ý để nhắc rằng **cùng một record pattern không có nghĩa cùng một policy validation**.

**Checklist review của chương trình:**

- `Paid(var id, Receipt(...Amount(...)))` minh họa nested record pattern qua ba tầng.
- `Receipt(..., var amount)` cho phép component amount null, nên có thể phân loại riêng trường hợp Receipt tồn tại nhưng Amount không match.
- `case Paid(var id, var receipt)` nhận những `Paid` không khớp pattern sâu.
- `when` bảo đảm dữ liệu được kiểm tra trước khi branch hiển thị.
- `case Rejected` có nhánh guarded và nhánh dự phòng.
- `Packet<Receipt>` chứng minh generic record pattern có thể dùng thông tin kiểu tĩnh để suy luận.
- `case null` là chính sách riêng cho selector null.
- `switch` trên sealed `Event` không cần `default`; compiler kiểm tra tính bao phủ của các variant.
- Assertions giúp phát hiện regression ngay khi đổi schema/guard/case order.

## 10. Negative compile tests: các lỗi checklist cần bắt trước runtime

Bốn đoạn sau **cố tình sai**, không được đặt vào file runnable ở mục 9. Chúng đã được thử ở môi trường JShell **JDK 24** với các kiểu tương đương được khai báo trong `RecordPatternChecklistDemo`.

### 10.1. Sai số component (A2)

`Paid` có đúng **hai** component: `orderId` và `receipt`. Không thể viết:

```java
// CỐ TÌNH SAI trong class có Paid.
static boolean wrongArity(Object input) {
    return input instanceof Paid(var id);
}
```

Compiler báo **`incorrect number of nested patterns`**. Cần đủ hai component, chẳng hạn `Paid(var id, var receipt)`.

### 10.2. Case tổng quát che case sâu hơn (C3)

```java
// CỐ TÌNH SAI trong switch trên Event.
case Paid(var id, var receipt) -> "broad";
case Paid(var id, Receipt(var no, var amount)) -> "specific";
```

Case đầu bao phủ mọi `Paid`, nên case sau là **dominated**. Compiler JDK 24 từ chối với thông báo case label bị case phía trước che khuất. Sửa bằng cách đặt `Paid(...Receipt(...))` **trước** case tổng quát.

### 10.3. Switch expression chưa exhaustive (C4)

```java
// CỐ TÌNH SAI: bỏ sót Pending.
static String incomplete(Event event) {
    return switch (event) {
        case Paid p -> "paid";
        case Rejected r -> "rejected";
        case null -> "missing";
    };
}
```

Vì `Event` là sealed và còn `Pending`, compiler bác `switch expression` do **không bao phủ hết input**. `case null` không thay thế một case cho `Pending`. Thêm case `Pending p -> "pending";` để duy trì hợp đồng rõ ràng.

### 10.4. Không kiểm tra generic type argument trực tiếp từ Object (C6)

```java
// CỐ TÌNH SAI: Packet<Receipt> không kiểm tra được từ Object.
static boolean unsafe(Object input) {
    return input instanceof Packet<Receipt> p;
}
```

Compiler từ chối vì không thể kiểm tra/cast an toàn `Object` sang một generic type không reifiable như `Packet<Receipt>` trong tình huống này. Dùng `Packet<?>` để kiểm tra container, rồi kiểm tra component thích hợp.

**Không khái quát sai:** kiểu `Packet<?>` là reifiable để kiểm tra record gốc; Java còn có những `instanceof` hợp lệ với ngữ cảnh kiểu hẹp hơn. Ví dụ âm ở đây cụ thể là **`Object` sang `Packet<Receipt>`**.

## 11. Checklist xử lý schema change và maintainability

Khi thêm/sửa component của một record, pattern có thể bị ảnh hưởng dù phần logic nghiệp vụ không đổi.

Ví dụ đổi:

```java
record Receipt(String number, Amount amount) {}
```

thành:

```java
record Receipt(String number, Amount amount, String issuedBy) {}
```

Các pattern `Receipt(var number, var amount)` cũ thiếu component thứ ba, nên **không còn hợp lệ**. Với codebase lớn có nhiều pattern lồng, đây là coupling với schema. Compiler giúp phát hiện các trường hợp sai số component, nhưng không bảo đảm sửa theo cách nào là đúng nghiệp vụ.

**Checklist khi đổi record declaration:**

- Liệt kê các nơi dùng `Receipt(...)` trong `instanceof` và `switch`.
- Đối chiếu **số lượng, thứ tự và kiểu** components trong mỗi pattern.
- Chạy compile với JDK/source level mục tiêu.
- Chạy các test null theo từng tầng, test guard và kết quả business.
- Đặc biệt kiểm tra các component cùng kiểu nếu thay thứ tự: `record Person(String first, String last)` với `Person(var last, var first)` có thể vẫn **biên dịch** nhưng dữ liệu bị hiểu ngược.
- Nếu nhiều nơi chỉ cần số tham chiếu, cân nhắc giữ `Receipt` là value object và gọi `receipt.number()`, hoặc một helper domain thay vì deconstruct toàn bộ components.

**Không có “độ sâu tối đa chuẩn”** do Java quy định cho chất lượng code. Một pattern sâu vừa phải nhưng chứa nhiều biến, guard và nhánh fallback có thể khó đọc hơn một pattern dài hơn nhưng rất rõ nghĩa. Dùng review thực tế: người khác có giải thích được đường match/non-match và tên component không?

### 11.1. Trường hợp nên tách bước

Nếu cần thông báo chính xác “thiếu Receipt”, “thiếu Amount”, “currency không hợp lệ” và “cents không dương”, một `instanceof` có Boolean kết quả không đủ thông tin nguyên nhân. Có thể truy cập từng tầng:

```java
// Minh họa trong class có Paid và Receipt.
static String diagnosePaid(Object value) {
    if (!(value instanceof Paid paid)) return "not-paid";

    Receipt receipt = paid.receipt();
    if (receipt == null) return "receipt-null";

    Amount amount = receipt.amount();
    if (amount == null) return "amount-null";

    if (amount.cents() <= 0) return "nonpositive-cents";
    if (amount.currency() == null) return "currency-null";
    if (!amount.currency().matches("[A-Z]{3}"))
        return "invalid-currency-format";

    return "ok";
}
```

Đây là **phương thức minh họa**, không được gọi trong file demo chính. Nó cố tình trả **lý do đầu tiên theo thứ tự kiểm tra**, không tổng hợp tất cả lỗi. Phương thức gọn hơn cho validation/debug có thể có giá trị hơn một nested pattern rất dài với nhiều guard và fallback.

### 11.2. Constructor invariants quan trọng hơn việc lặp guard

Trong hệ thống thực tế, nếu chính sách luôn yêu cầu `Amount.cents > 0` và currency có dạng phù hợp, có thể áp invariant:

```java
// Đoạn minh họa thay thế record Amount của demo.
record Amount(long cents, String currency) {
    public Amount {
        if (cents <= 0
                || currency == null
                || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("invalid amount");
        }
    }
}
```

Khi đó các đối tượng được tạo qua constructor hợp lệ không thể có `Amount` sai theo quy tắc này, và test cần chuyển sang kiểm tra constructor từ chối dữ liệu không hợp lệ. Cần phân biệt rõ model “cố tình nới lỏng để học pattern” với domain model “phải chặn lỗi từ boundary”.

**Lưu ý:** `record` không tự làm mọi component trở nên non-null hay deeply immutable. Một record có component là object mutable vẫn có nguy cơ thay đổi qua tham chiếu; hãy xem xét defensive copy và giới hạn tương ứng.

## 12. Review rủi ro đặc biệt

### 12.1. Accessor không nên có side effects bất ngờ

Record pattern deconstruct thông qua record accessors. Nếu một record tự định nghĩa accessor và accessor ném lỗi khi match, kết quả có thể là **`MatchException`**, không phải một non-match Boolean bình thường. Đối với record dùng làm model dữ liệu, ưu tiên accessor rõ ràng, ít side effects; khi thấy lỗi trong quá trình match, đọc stack trace và cause.

### 12.2. Thứ tự case là contract hành vi, không chỉ cú pháp

Trong `switch`, một case cụ thể có guard có thể không match vì điều kiện nghiệp vụ, rồi case rộng tiếp theo nhận dữ liệu. Điều đó là chính sách xử lý. Nếu thay đổi thứ tự case hoặc biến một nhánh rộng thành `default`, cần xem lại expected outputs, không chỉ kiểm tra code có biên dịch.

### 12.3. Exhaustiveness không chứng minh đúng business rule

Compiler có thể bảo đảm đủ loại biến thể sealed trong `switch expression`, nhưng không chứng minh một khoản tiền hợp lệ, một mã đơn tồn tại trong database hay một regex được chọn đúng nghiệp vụ. Những điều đó cần validation và tests.

### 12.4. Không suy đoán hiệu năng từ số record patterns

Record pattern sâu **không mặc định chậm hơn hoặc nhanh hơn** nhiều accessor thủ công trong mọi workload. JIT, kiểu dữ liệu, tình huống null và các phương thức accessor đều ảnh hưởng. Nếu hiệu năng là yêu cầu, dùng benchmark có kiểm soát như JMH với warmup và dữ liệu đại diện; đừng dùng vài lần `System.nanoTime()` để kết luận tổng quát.

### 12.5. Boundary và generic data

API nhận JSON, event từ queue hoặc `Object` nên parse/validate trước khi tạo model typed. Tránh một `String type` cộng `Object payload` lan sâu vào business logic; khi dùng generic records, kiểm tra phần tử trong container phù hợp với hạn chế type erasure. Pattern matching không tự đảm bảo schema của dữ liệu không tin cậy.

## 13. Checklist kiểm thử trước khi merge

Để đưa bài học vào quy trình code review, có thể dùng mẫu ngắn sau:

| Câu hỏi kiểm tra | Bằng chứng tối thiểu |
| --- | --- |
| Source level hỗ trợ record patterns? | JDK/toolchain, `javac --release 21` hoặc cấu hình tương đương |
| Record declaration có đúng components? | Đối chiếu khai báo và pattern; compile thành công |
| Kiểu biến `var` và thứ tự có đúng? | Lời gọi method/biến, code review; negative compile khi hữu ích |
| Có root null không? | Test `instanceof null` và nhánh `case null` nếu switch cho phép |
| Có nested record null không? | Test thiếu Receipt và thiếu Amount riêng biệt |
| Có nullable component không? | Test `Amount(450, null)`/`Rejected(...,null)` theo policy |
| Guard an toàn với null không? | Dùng `&&`/`when` đúng thứ tự; test blank/null |
| Có case bị che hay thiếu subtype? | Compile negative về dominance/exhaustiveness |
| Generic argument có kiểm chứng runtime được không? | Dùng wildcard và runtime type check thay cho `Packet<Receipt>` từ Object |
| Invariant nằm đúng tầng? | Constructor/factory/validator và negative tests |
| Kết quả test được khẳng định bằng assertion? | Expected/actual rõ, một ca sai phải làm test fail |
| Schema change có ảnh hưởng không? | Review các pattern deconstruction, chạy regression tests |

**Quy trình gợi ý:** kiểm tra A (cấu trúc) trước → B (null/validation) → C (guard/switch/generic) → D (test/schema/maintainability). Khi phát hiện một lỗi, chỉ sửa đúng tầng rồi chạy lại toàn bộ tests; đừng thêm `default` hoặc cast rộng để che lỗi.

## 14. Bài tập tự luyện

### Bài 1 — tìm lỗi record pattern không khớp số component

Cho:

```java
record Coordinate(double latitude, double longitude) {}
record Destination(String name, Coordinate point) {}
```

Xác định lỗi trong:

```java
// CỐ TÌNH SAI.
if (value instanceof Destination(var name, Coordinate(var latitude))) {
    System.out.println(name);
}
```

**Gợi ý:** `Coordinate` có hai component, nhưng `Coordinate(var latitude)` chỉ có một. Sửa thành `Coordinate(var latitude, var longitude)` rồi test `point == null`.

### Bài 2 — phân biệt nested null và component null

Với `Destination` và `Coordinate`, thử:

- `new Destination("A", null)`: nested `Coordinate(...)` có match không?
- `new Destination(null, new Coordinate(10, 20))`: `var name` có nhận null không?
- `value == null`: `instanceof` và `switch` xử lý thế nào?

**Yêu cầu:** giải thích từng kết quả trước khi chạy thử.

### Bài 3 — thêm guard hợp lệ

Viết `instanceof` pattern lấy `latitude` và `longitude`, chỉ nhận giá trị nếu cả hai hữu hạn và trong khoảng lần lượt `[-90,90]`, `[-180,180]`. Dùng `Double.isFinite` để loại `NaN`/vô cực; nhớ rằng primitive `double` không thể là null.

### Bài 4 — mở rộng sealed hierarchy

Thêm `Canceled(String orderId) implements Event` vào model demo và `permits`. Trước khi sửa `summarize`, chạy compiler; giải thích vì sao một `switch expression` exhaustive cần case mới. Sau đó thêm ca test cho Canceled.

### Bài 5 — review một pattern quá sâu

Tạo nested record bốn tầng. Nếu method chỉ cần một mã tham chiếu ở tầng hai, thử hai giải pháp: (1) pattern sâu bốn tầng, (2) pattern hai tầng rồi dùng accessor có tên. Đo số biến ràng buộc, số record con phải khác null, khả năng nêu lý do lỗi và mức phụ thuộc schema. Chọn phương án đáp ứng domain rõ nhất; không chỉ dùng số dòng làm tiêu chuẩn.

## 15. Tổng kết

Một record pattern tốt cần đi qua **bốn lớp kiểm tra**:

1. **Cấu trúc đúng:** record type, số lượng và thứ tự components, kiểu `var`/pattern con.
2. **Ngữ nghĩa đúng:** null từng tầng, guard, biến pattern trong flow scope, generic inference và chính sách dữ liệu.
3. **Phân nhánh đúng:** case cụ thể trước case rộng, exhaustive switch với sealed types, xử lý selector null rõ ràng.
4. **Khả năng bảo trì đúng:** test có assertion, negative compile tests, invariant ở boundary/constructor, review khi schema đổi và quyết định độ sâu hợp lý.

Với mô hình `Paid → Receipt → Amount`, chương trình đã xác nhận **15/15 ca runtime**, bao gồm null ở nhiều tầng, guard, sealed variants và generic Packet. Bốn tình huống cố tình sai — arity, dominance, exhaustiveness và generic type erasure — được compiler JDK 24 từ chối. Đây là những tiêu chí có thể tái sử dụng trong code review, nhưng **không thay thế domain validation hoặc đánh giá yêu cầu sản phẩm**.

### Tài liệu Java chính thức

- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JLS 21 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7)
