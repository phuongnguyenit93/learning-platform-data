# Thiết kế model để pattern có ý nghĩa trong Java (Java 21+)

## 1. Vấn đề cần giải quyết

Pattern matching không tự làm một domain model trở nên đúng đắn. Nó giúp **nhận diện dạng dữ liệu**, **kiểm tra cấu trúc** và **lấy các thành phần đã khớp** một cách rõ ràng. Nếu model vẫn chỉ gồm `String status` và `Object payload`, pattern thường chỉ là một lớp cú pháp đẹp hơn phủ lên những trạng thái mơ hồ.

**Thiết kế model để pattern có ý nghĩa** là tổ chức dữ liệu sao cho mỗi nhánh pattern tương ứng với **một khái niệm hoặc trạng thái nghiệp vụ thực sự**, và các giá trị hợp lệ mang đúng thông tin mà nhánh đó cần xử lý.

Ví dụ trong xử lý thanh toán:

- **Approved**: thanh toán được chấp thuận, có mã đơn và biên nhận hợp lệ.
- **Declined**: thanh toán bị từ chối, có mã đơn và lý do.
- **Pending**: thanh toán đang chờ, có mã đơn nhưng chưa có biên nhận được chấp thuận.

Nếu dùng ba biến thể này làm các kiểu Java khác nhau, `case Approved(...)`, `case Declined(...)` và `case Pending(...)` không chỉ là điều kiện kỹ thuật: **chúng diễn đạt chính xác ba nhánh nghiệp vụ**.

Bài dùng **sealed types** (ổn định từ Java 17, JEP 409), **record patterns** (ổn định từ Java 21, JEP 440) và **pattern matching for switch** (ổn định từ Java 21, JEP 441). Ví dụ có thể biên dịch với **JDK 21+**, không cần `--enable-preview`.

## 2. Dấu hiệu một model khiến pattern trở nên vô nghĩa

Xét cách biểu diễn tất cả trạng thái thanh toán bằng một record tổng quát:

```java
record LegacyPayment(
    String status,
    String orderId,
    Receipt receipt,
    String reason
) {}
```

Đoạn này là **minh họa model**, giả sử `Receipt` đã được khai báo. Nó cho phép tạo ra nhiều tổ hợp phi lý:

- `status = "APPROVED"` nhưng `receipt == null`.
- `status = "PENDING"` nhưng đã có `receipt` và `reason`.
- `status = "DECLINED"` nhưng `reason` trống.
- `status = "SOMETHING_ELSE"` mà hệ thống không định nghĩa.

Đến bước xử lý, lập trình viên buộc phải `switch(payment.status())`, tự kiểm tra nullable fields, tự cast hoặc dò ý nghĩa của từng chuỗi. Các điều kiện này lặp lại ở nhiều nơi và không được hệ kiểu giúp kiểm tra đầy đủ.

**Đây không phải lỗi cú pháp `record`.** Đây là dấu hiệu model không biểu diễn rõ những tổ hợp dữ liệu được phép tồn tại. Trước khi viết pattern đẹp, hãy đặt câu hỏi: *mỗi biến thể nghiệp vụ cần trường nào, trường nào không có ý nghĩa với biến thể đó, và điều gì phải luôn đúng khi tạo đối tượng?*

## 3. Bước 1: mô hình hóa các biến thể thật bằng sealed interface

Thay vì một status string dùng chung cho mọi thứ:

```java
sealed interface PaymentOutcome permits Approved, Declined, Pending {}

record Approved(String orderId, Receipt receipt)
        implements PaymentOutcome {}

record Declined(String orderId, String reason)
        implements PaymentOutcome {}

record Pending(String orderId)
        implements PaymentOutcome {}
```

Đây là các khai báo **rút gọn để minh họa cấu trúc**; bản chạy đầy đủ có kiểm tra invariant ở mục 6.

Ý nghĩa thiết kế:

- `PaymentOutcome` là tên trừu tượng mô tả **kết quả/trạng thái thanh toán** mà một hàm cần xử lý.
- `Approved` mang `Receipt` vì biên nhận có ý nghĩa và bắt buộc ở trạng thái được chấp thuận.
- `Declined` mang `reason`; nó không sở hữu một trường `receipt` vô nghĩa.
- `Pending` chỉ có `orderId`, không phải “một `Approved` với receipt null”.
- `sealed ... permits ...` mô tả tập subtype được phép, phù hợp khi tập biến thể này **cố ý đóng**.

Khi một `switch expression` duyệt `PaymentOutcome`, trình biên dịch biết các subtype được phép. Nếu bỏ sót nhánh trong một `switch` cần bao phủ hết, lỗi có thể được phát hiện ngay lúc biên dịch.

**Giới hạn:** sealed hierarchy không tự bảo đảm các trường trong record là hợp lệ. `new Approved("O-1", null)` vẫn có thể tạo được nếu constructor không cấm `null`. Vì vậy, thiết kế variant và **bất biến dữ liệu** (*invariants*) là hai công việc bổ sung cho nhau.

## 4. Bước 2: dùng value objects cho dữ liệu có ý nghĩa

Một biên nhận gồm mã tham chiếu và số tiền. Thay vì truyền nhiều chuỗi/số nguyên rời rạc qua các phương thức, ta có thể dùng record value objects:

```java
record Money(long cents, String currency) {}
record Receipt(String reference, Money amount) {}
```

Trong ví dụ này:

- `Money.cents` biểu diễn số tiền bằng **đơn vị nhỏ nhất** (như cents) để tránh lỗi làm tròn không mong muốn khi xử lý các giá trị đã được quy đổi thành đơn vị nguyên.
- `Money.currency` biểu diễn mã tiền tệ. Chỉ kiểm tra ba chữ cái viết hoa **không đồng nghĩa** với việc xác minh mã ISO 4217 có tồn tại.
- `Receipt.reference` là mã biên nhận, còn `Receipt.amount` là một `Money`. Hai giá trị này đi cùng nhau theo đúng khái niệm nghiệp vụ.

Khi record được thiết kế theo cách này, pattern lồng sẽ có ý nghĩa:

```java
// Trong một switch trên PaymentOutcome.
case Approved(
    var orderId,
    Receipt(var reference, Money(var cents, var currency))
) -> ...
```

Pattern diễn đạt: *“Trạng thái được chấp thuận của đơn này, với biên nhận có mã tham chiếu và số tiền cụ thể.”* Người đọc không cần đoán `payload[0]`, `payload[1]` hoặc cast một `Object`.

**Đừng phân rã mọi dữ liệu chỉ để có thể dùng pattern.** Nếu `Money` có logic về đơn vị, chuyển đổi hoặc tính toán, đôi khi giữ nguyên `Money money` và gọi một phương thức nghiệp vụ rõ tên sẽ tốt hơn là tách các component rồi thao tác số nguyên khắp nơi.

## 5. Bước 3: bảo vệ invariant trong constructor

Một model tốt không chỉ có tên kiểu rõ ràng: nó phải ngăn tạo ra những trường hợp bất hợp lý **theo chính sách miền nghiệp vụ đã chọn**.

Trong ví dụ thanh toán này, quy tắc là:

1. Mã đơn, mã biên nhận và lý do từ chối không được null hoặc chỉ chứa khoảng trắng.
2. `Approved` bắt buộc có `Receipt`; `Receipt` bắt buộc có `Money`.
3. `Money.cents > 0`, vì ví dụ đang mô tả một khoản thanh toán **dương**; hoàn tiền, số tiền bằng không hoặc điều chỉnh có thể cần model/quy tắc khác.
4. `Money.currency` phải có dạng **ba ký tự ASCII viết hoa**; đây là kiểm tra hình dạng dữ liệu, không phải tra cứu danh mục tiền tệ thực.

Record hỗ trợ **compact canonical constructor** để kiểm tra các component khi khởi tạo:

```java
record Money(long cents, String currency) {
    public Money {
        if (cents <= 0) {
            throw new IllegalArgumentException("cents must be positive");
        }
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("currency format invalid");
        }
    }
}
```

Đây là một khai báo độc lập về mặt cú pháp nhưng có thể đặt dưới dạng nested record trong class của chương trình. Kiểm tra chạy trước khi đối tượng được khởi tạo thành công. Các component được Java tự gán sau phần thân compact constructor nếu không có ngoại lệ.

Với các record khác, có thể kiểm tra `receipt != null`, `amount != null` và chuỗi bắt buộc không blank. Từ đây, những đối tượng được xây dựng qua constructor hợp lệ mang invariant mà mã nghiệp vụ có thể dựa vào.

**Lưu ý:** `record` bảo đảm mỗi component là field final, không có nghĩa là *deep immutability* nếu component trỏ tới object mutable. Các record của chương trình hoàn chỉnh bên dưới chỉ chứa primitive, `String` và các record value objects cùng được kiểm soát; đó là lựa chọn có chủ đích để giảm rủi ro thay đổi trạng thái qua tham chiếu.

## 6. Ví dụ Java hoàn chỉnh: domain model và pattern cùng diễn đạt nghiệp vụ

Tạo file **`MeaningfulPatternModelDemo.java`**:

```java
public class MeaningfulPatternModelDemo {
    sealed interface PaymentOutcome permits Approved, Declined, Pending {}

    static void requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " required");
        }
    }

    record Money(long cents, String currency) {
        public Money {
            if (cents <= 0) {
                throw new IllegalArgumentException("cents must be positive");
            }
            if (currency == null || !currency.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException("currency format invalid");
            }
        }
    }

    record Receipt(String reference, Money amount) {
        public Receipt {
            requireText(reference, "reference");
            if (amount == null) throw new IllegalArgumentException("amount required");
        }
    }

    record Approved(String orderId, Receipt receipt) implements PaymentOutcome {
        public Approved {
            requireText(orderId, "orderId");
            if (receipt == null) throw new IllegalArgumentException("receipt required");
        }
    }

    record Declined(String orderId, String reason) implements PaymentOutcome {
        public Declined {
            requireText(orderId, "orderId");
            requireText(reason, "reason");
        }
    }

    record Pending(String orderId) implements PaymentOutcome {
        public Pending {
            requireText(orderId, "orderId");
        }
    }

    static String describe(PaymentOutcome outcome) {
        return switch (outcome) {
            case Approved(var id, Receipt(var ref, Money(var cents, var currency))) ->
                    "approved:" + id + ":" + ref + ":" + cents + ":" + currency;
            case Declined(var id, var reason) ->
                    "declined:" + id + ":" + reason;
            case Pending(var id) -> "pending:" + id;
            case null -> "missing";
        };
    }

    static void mustReject(String testName, Runnable action) {
        try {
            action.run();
            throw new AssertionError(testName + " was accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println(testName + " -> " + expected.getMessage());
        }
    }

    public static void main(String[] args) {
        PaymentOutcome approved = new Approved("O-10",
                new Receipt("R-1", new Money(2500, "USD")));
        PaymentOutcome declined = new Declined("O-11", "insufficient funds");
        PaymentOutcome pending = new Pending("O-12");

        System.out.println(describe(approved));
        System.out.println(describe(declined));
        System.out.println(describe(pending));
        System.out.println(describe(null));

        mustReject("invalid-money", () -> new Money(0, "USD"));
        mustReject("invalid-approved", () -> new Approved("O-13", null));
        mustReject("invalid-reason", () -> new Declined("O-14", ""));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac --release 21 MeaningfulPatternModelDemo.java
java MeaningfulPatternModelDemo
```

**Stdout chính xác:**

```text
approved:O-10:R-1:2500:USD
declined:O-11:insufficient funds
pending:O-12
missing
invalid-money -> cents must be positive
invalid-approved -> receipt required
invalid-reason -> reason required
```

Ví dụ đã được thực thi với JDK 24 bằng JShell, dùng các cấu trúc ngôn ngữ đã chính thức trong Java 21. Phần kiểm thử constructor cố tình tạo giá trị không hợp lệ; nếu constructor chấp nhận, `mustReject` sẽ ném `AssertionError` khiến test thất bại, thay vì báo thành công giả.

### Đọc kết quả theo từng nhóm

| Dữ liệu | Biểu thức pattern được chọn | Ý nghĩa |
| --- | --- | --- |
| `Approved("O-10", Receipt("R-1", Money(2500, "USD")))` | `Approved(..., Receipt(..., Money(...)))` | Tách dữ liệu đến tận đơn vị tiền và trả biểu diễn được chấp thuận |
| `Declined("O-11", "insufficient funds")` | `Declined(var id, var reason)` | Kết quả từ chối có lý do riêng |
| `Pending("O-12")` | `Pending(var id)` | Trạng thái chờ không cần biên nhận |
| `null` | `case null` | Xử lý không có đối tượng, theo hợp đồng minh họa |
| `Money(0, "USD")` | Không có đối tượng hợp lệ để match | Constructor từ chối vì khoản tiền không dương |
| `Approved("O-13", null)` | Không có `Approved` hợp lệ để match | Constructor từ chối vì thiếu biên nhận |
| `Declined("O-14", "")` | Không có `Declined` hợp lệ để match | Constructor từ chối vì lý do rỗng |

Trong trường hợp thành công, các record patterns cung cấp cấu trúc, còn phép nối chuỗi là **logic trình bày** của ví dụ. Pattern matching không tự sinh DTO, tự định dạng tiền tệ hay tự triển khai quy tắc thanh toán.

## 7. Vì sao các pattern này “có ý nghĩa”?

### 7.1. Mỗi case phản ánh một trạng thái có nghĩa

`case Approved(...)` nghĩa là đơn đã được chấp thuận; `case Declined(...)` nghĩa là bị từ chối; `case Pending(...)` nghĩa là đang chờ. Ta không cần viết `if ("APPROVED".equals(status))` rồi tiếp tục suy luận trường nào có thể null.

**Tên subtype** không nên là phân loại kỹ thuật mơ hồ kiểu `Type1`, `Kind2`. Hãy chọn thuật ngữ mà domain expert có thể xác nhận.

### 7.2. Dữ liệu của biến thể được đặt đúng chỗ

`Approved` có `Receipt`; `Declined` có `reason`; `Pending` không mang dữ liệu không áp dụng. Nhờ đó, khi pattern thành công, phần thân case không phải kiểm tra một loạt field “có thể có hoặc không” chỉ vì model chung.

Tất nhiên, nếu một trường thực sự là **tùy chọn trong domain**, hãy biểu diễn và kiểm tra tính tùy chọn một cách có chủ đích; không cố ép mọi giá trị đều non-null vì muốn pattern trông đẹp.

### 7.3. Bất biến được giữ ở nơi tạo dữ liệu

Compiler có thể kiểm tra **kiểu** của component, nhưng không thể tự chứng minh một chuỗi mã đơn khác blank hay giá trị tiền dương. Canonical constructors làm rõ các quy tắc đó. Việc tách cấu trúc bằng pattern chỉ an toàn theo **những invariant mà model thực sự áp đặt**, không dựa vào lời hứa ở tài liệu.

### 7.4. Compiler giúp phát hiện thiếu nhánh

Vì `PaymentOutcome` là sealed interface và các record của nó là những subtype final, `switch expression` trong `describe` có các case bao phủ toàn bộ các subtype được phép, cộng `case null` để xử lý selector null theo chủ đích.

Nếu xóa hẳn `case Pending(var id)` mà không thêm case khác có thể bao phủ Pending, trình biên dịch từ chối `switch expression` vì **không exhaustive**. Kiểm tra này đã được thử bằng JDK 24. Khi thêm subtype mới vào `permits` mà quên cập nhật các vị trí xử lý, lỗi biên dịch thường giúp tìm các `switch expression` cần sửa.

Không nên viết `default -> "other"` chỉ để tránh việc xử lý từng subtype: với hierarchy đóng, nhánh `default` có thể che mất cảnh báo khi domain xuất hiện một trạng thái mới. Tuy nhiên, nếu domain cố tình cho phép mở rộng bởi plugin bên ngoài, một kiểu sealed đóng có thể không phù hợp; lúc đó cần chiến lược fallback rõ ràng.

### 7.5. Pattern cho biết cấu trúc, không thay business rule

`case Approved(var id, Receipt(var ref, Money(var cents, var currency)))` đọc được dữ liệu theo **thứ tự khai báo** của từng record. Nó không giải quyết chính sách miễn phí vận chuyển, hoàn tiền, tỷ giá hay độ hợp lệ của giao dịch. Những quy tắc đó vẫn thuộc service/domain logic, value objects hoặc các phương thức có tên rõ ràng.

## 8. Độ sâu pattern: đọc rõ ràng quan trọng hơn tách mọi thứ

Nested record pattern mạnh nhưng có thể trở nên khó đọc nếu lồng quá nhiều tầng:

```java
case Approved(var id, Receipt(var reference, Money(var cents, var currency))) ->
        "approved:" + id + ":" + cents + currency;
```

Trong trường hợp chỉ cần một phương thức trên `Money`, có thể giữ giá trị có ý nghĩa lại:

```java
// Minh họa một case trong switch trên PaymentOutcome.
case Approved(var id, Receipt(var reference, var amount)) ->
        "approved:" + id + ":" + amount;
```

Ở phiên bản thứ hai, `amount` có kiểu `Money` và có thể được chuyển đến một formatter riêng. Với code nghiệp vụ thật, việc giữ nguyên value object có thể tránh lan truyền chi tiết `cents`/`currency` và tập trung quy tắc liên quan đến tiền vào một chỗ.

**Quy tắc thực hành:** tách đến tầng cần dùng trong case, không tách đến tầng sâu nhất chỉ để chứng minh khả năng của record patterns.

## 9. Phân biệt kiểu hợp lệ với giá trị hợp lệ

Có hai cấp độ cần kiểm tra:

1. **Khớp kiểu/cấu trúc:** `Approved` hay `Declined`? Record có bao nhiêu component? Pattern con có kiểu tương thích? Compiler và pattern matching hỗ trợ mạnh.
2. **Hợp lệ nghiệp vụ:** `orderId` có blank không? `Money.cents` có dương không? `currency` có nằm trong danh sách chấp nhận không? Đây là việc của constructors, validation và business rules.

Một ví dụ về guard trên dữ liệu đã khớp:

```java
// Đặt trong phương thức có biến PaymentOutcome outcome.
if (outcome instanceof Approved(
        var id, Receipt(var ref, Money(var cents, var currency)))
        && cents >= 10_000) {
    System.out.println("large-approved:" + id);
}
```

`&&` đánh giá ngắn mạch: điều kiện `cents >= 10_000` chỉ được xét khi toàn bộ record pattern đã khớp. Biến `cents` khả dụng ở vế phải và trong nhánh `if` đúng nhờ **flow scoping**. Mốc `10_000` chỉ là quy tắc minh họa cho “khoản lớn”, không phải một chuẩn thanh toán phổ quát.

**`null`:** `case null` trong `switch` xử lý **chính selector `outcome` bằng null**. Với record pattern con `Receipt(...)`, một `receipt == null` sẽ không khớp. Trong model ở mục 6, constructor của `Approved` chủ động từ chối receipt null, nên các đối tượng được khởi tạo đúng không có tình huống đó. Tuy vậy, nếu dùng `var receipt` để lấy một component nullable ở model khác thì `var` vẫn có thể nhận null; pattern matching không biến mọi component thành non-null.

## 10. Sai lầm khi thiết kế model để phục vụ pattern

| Sai lầm | Vì sao chưa tốt và cách cải thiện |
| --- | --- |
| Có một `record Event(String type, Object payload)` cho tất cả loại sự kiện | Vẫn cần tag, cast và validation thủ công. Cân nhắc subtype chuyên biệt hoặc adapter chuyển từ envelope bên ngoài sang kiểu nội bộ. |
| Dùng một record lớn với 10 field nullable cho 4 trạng thái | Cho phép nhiều tổ hợp vô nghĩa. Chia subtype theo trạng thái khi các trạng thái thực sự có tập dữ liệu khác nhau. |
| Chỉ thêm `sealed` mà không kiểm tra invariant | `new Approved(id, null)` vẫn có thể tạo nếu constructor cho phép. Thêm kiểm tra và test phủ định. |
| Dùng nhiều `case` theo tên class kỹ thuật | Người đọc không hiểu nghiệp vụ. Đặt tên kiểu, trạng thái và value object theo ngôn ngữ domain. |
| Lồng record patterns qua quá nhiều lớp chỉ để ít gọi accessor | Dễ khó đọc và phụ thuộc mạnh vào cấu trúc record. Giữ value object khi nó có hành vi hữu ích. |
| Viết `default` ở mọi `switch` sealed | Có thể che trường hợp domain thêm subtype mới; cân nhắc exhaustive switch không default. |
| Giả sử `record` luôn bất biến sâu | Các component là final nhưng có thể tham chiếu object mutable. Dùng immutable value objects, defensive copy khi cần. |
| Cho rằng `var x` tự loại bỏ null | Pattern `var` trên component có thể ràng buộc null. Dùng constructor/validation/guard thích hợp. |
| Đặt mọi logic nghiệp vụ trong một `switch` rất dài | Pattern có thể chọn biến thể, nhưng logic lớn nên ở service hoặc phương thức domain/polymorphism, tùy trách nhiệm. |
| Dùng sealed type cho domain cần mở rộng tự do bởi bên thứ ba | Tập subtype đóng có thể cản kiến trúc plugin. Chọn interface mở, registry hay polymorphism khi thật sự cần mở rộng. |

## 11. Đưa model vào hệ thống thực tế

Một hệ thống thường nhận JSON, message từ queue hoặc dữ liệu database trước khi tạo `PaymentOutcome`. Không được giả định rằng một chuỗi `"APPROVED"` từ mạng đã là một `Approved` hợp lệ.

Quy trình khuyến nghị:

1. **Đọc dữ liệu ngoài** bằng cơ chế parse/deserialization phù hợp.
2. **Kiểm tra cấu trúc nguồn**: tag, field bắt buộc, kiểu dữ liệu, format và null.
3. **Chuyển thành domain type** bằng constructor/factory, bảo đảm invariant; trả lỗi parse/validation rõ ràng khi thất bại.
4. **Chạy nghiệp vụ** trên `PaymentOutcome` có kiểu, dùng pattern trong `switch` hoặc `instanceof` để chọn hành vi.
5. **Chuyển sang output** (API response/DTO/event) với mapping và serialization riêng.

Nếu API công khai vẫn yêu cầu type tag, giữ tag trong **DTO ở boundary** và chuyển sang hierarchy có kiểu phía trong. Không cần làm thay đổi wire format chỉ để có pattern matching đẹp.

**Lưu ý về lỗi:** Dùng ngoại lệ trong constructor là cách minh họa phù hợp cho dữ liệu vi phạm invariant. Với dữ liệu không tin cậy đến từ bên ngoài, có thể ưu tiên kết quả parse có mã lỗi để hệ thống xử lý, log và trả thông báo rõ ràng; đừng nuốt mọi lỗi thành `null` nếu cần phân biệt nguyên nhân.

## 12. Checklist kiểm thử model và các nhánh pattern

| Nhóm test | Kịch bản | Kết quả cần xác nhận |
| --- | --- | --- |
| Biến thể hợp lệ | `Approved` + `Receipt` + `Money` hợp lệ | Nhánh Approved được chọn, lấy đúng các component |
| Biến thể hợp lệ | `Declined` có reason | Nhánh Declined được chọn, không yêu cầu Receipt |
| Biến thể hợp lệ | `Pending` có orderId | Nhánh Pending được chọn |
| Selector null | `describe(null)` | Nhánh `case null` chạy theo hợp đồng |
| Invariant số tiền | `Money(0, "USD")` | Constructor từ chối vì tiền không dương |
| Invariant reference | `Approved(id, null)` | Constructor từ chối thiếu biên nhận |
| Invariant chuỗi | `Declined(id, "")` | Constructor từ chối lý do rỗng |
| Biên format | Currency không đúng ba chữ cái viết hoa | Constructor từ chối theo quy tắc mẫu |
| Exhaustiveness | Bỏ case Pending trong `switch expression` | Compiler báo switch không bao phủ đủ |
| Thay đổi model | Thêm một subtype được phép mới | Các switch exhaustive cần được cập nhật |
| Dữ liệu ngoài | JSON với tag đúng nhưng field thiếu/sai kiểu | Lỗi parse/validation trước khi gọi nghiệp vụ |

**Hai loại QA khác nhau:** Test runtime chứng minh behavior với dữ liệu; còn negative compile test chứng minh trình biên dịch chặn một cấu trúc không bao phủ đủ subtype. Không nhét một đoạn cố tình sai cú pháp vào file ví dụ đang chạy.

## 13. Bài tập: thiết kế model để pattern phản ánh domain

Bài toán: một yêu cầu giao hàng có thể `Delivered` (có mã xác nhận), `Lost` (có lý do) hoặc `InTransit` (có mã chuyến). Hãy:

1. Định nghĩa `sealed interface DeliveryState` với ba record triển khai, giữ chỉ những component có ý nghĩa cho từng trạng thái.
2. Viết compact constructors để mã lô hàng và dữ liệu bắt buộc không blank.
3. Viết `describe(DeliveryState state)` bằng `switch expression` trên ba subtype; quyết định xử lý `null`.
4. Viết ca âm cho một `Delivered` thiếu mã xác nhận, và ca kiểm tra thiếu nhánh khi thêm subtype mới.

**Gợi ý mô hình** (rút gọn, chưa có constructors kiểm tra):

```java
sealed interface DeliveryState permits Delivered, Lost, InTransit {}
record Delivered(String shipmentId, String confirmation)
        implements DeliveryState {}
record Lost(String shipmentId, String reason)
        implements DeliveryState {}
record InTransit(String shipmentId, String routeId)
        implements DeliveryState {}
```

**Gợi ý pattern xử lý** (đặt trong phương thức có biến `DeliveryState state`):

```java
String message = switch (state) {
    case Delivered(var id, var confirmation) ->
            "delivered:" + id + ":" + confirmation;
    case Lost(var id, var reason) -> "lost:" + id + ":" + reason;
    case InTransit(var id, var route) -> "transit:" + id + ":" + route;
    case null -> "missing";
};
```

Lời giải hoàn chỉnh còn cần constructors kiểm tra các giá trị bắt buộc. Hãy thử nghiệm ca `new Delivered("S-1", null)` để chắc chắn model không cho tạo “đã giao hàng nhưng thiếu xác nhận” theo chính sách đã chọn.

## 14. Tổng kết

Pattern có ý nghĩa khi **cấu trúc kiểu dữ liệu phản ánh đúng các lựa chọn của domain**. Sealed hierarchy diễn đạt các biến thể được phép; record value objects giữ dữ liệu có nghĩa; constructors bảo vệ invariant; type/record patterns chọn và tách biến thể; `switch expression` exhaustive giúp phát hiện nhánh bỏ sót. Tuy nhiên, các quy tắc nghiệp vụ, validation của dữ liệu ngoài, mapping và yêu cầu mở rộng vẫn phải được thiết kế riêng. **Thiết kế model trước, rồi để pattern diễn đạt model — không thiết kế model chỉ nhằm trình diễn cú pháp pattern.**

Tài liệu chính thức:

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
