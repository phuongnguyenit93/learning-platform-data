# Đưa pattern guideline vào code review: checklist thực hành cho Java 21+

## 1. Tại sao nhóm cần guideline riêng cho pattern matching?

Từ Java 21, **pattern matching for switch** (JEP 441) và **record patterns** (JEP 440) đã trở thành tính năng chuẩn, không cần `--enable-preview`. Các tính năng này giúp Java giảm cast lặp, biểu diễn cấu trúc record rõ hơn và cho compiler kiểm tra nhiều trường hợp thiếu nhánh. Nhưng mã ngắn hơn **không tự bảo đảm** đúng, dễ bảo trì hoặc an toàn với `null`.

Trong code review, một đoạn `switch` có vẻ đẹp về cú pháp vẫn có thể mắc lỗi:

- Nhánh `case` tổng quát đặt trước khiến nhánh có `when` bị che (*dominance*).
- `switch` có `default` nhưng đầu vào `null` vẫn gây `NullPointerException`.
- Pattern khớp record ngoài nhưng **component lồng** bằng `null` nên nhánh chuyên biệt không được chọn.
- Reviewer chỉ thấy một test chạy vào case mà chưa test **guard false** và nhánh fallback.
- Dùng type pattern để phân loại một hierarchy có hành vi đa hình, gây coupling không cần thiết.
- Viết generic pattern không kiểm tra an toàn được do type erasure.
- Dồn quá nhiều validation/I/O vào guard, khiến thứ tự chọn case khó dự đoán hoặc khó test.

**Mục tiêu của pattern guideline trong code review** là thống nhất cách đánh giá **tính đúng, sự rõ ràng, khả năng mở rộng, tính kiểm thử và tương thích Java version**. Guideline không phải luật bắt buộc “mọi `instanceof` phải đổi thành pattern” hay “mọi phép dispatch phải đổi thành `switch`”.

### Ba mức đánh giá được đề xuất

| Mức trong review | Khi áp dụng | Hành động |
| --- | --- | --- |
| **Block / Request changes** | Sai kiểu/scope, không compile, lỗi `null` có thể xảy ra theo hợp đồng, thiếu test quan trọng, làm sai nghiệp vụ hoặc gây lỗi bảo mật | Sửa và kiểm chứng trước khi merge |
| **Should improve** | Có duplication, không tận dụng exhaustiveness, guard khó đọc, thiếu test biên nhưng chưa có lỗi đã chứng minh | Cải thiện trong PR hoặc thống nhất việc theo dõi |
| **Suggestion / Nit** | Cách đặt tên, tách dòng, chọn `var` hay kiểu tường minh khi cả hai đều đúng | Góp ý không chặn nếu không vi phạm chuẩn đã thống nhất |

Đừng dùng nhãn *Block* chỉ vì sở thích cá nhân về kiểu viết. Mỗi nhận xét nên gắn với **quy tắc Java, ví dụ input, ảnh hưởng thực tế hoặc tiêu chí chất lượng của nhóm**.

## 2. Chuẩn bị bối cảnh trước khi đọc code

Một reviewer cần nắm các thông tin sau trước khi kết luận về pattern:

1. **Baseline JDK/source level:** project build với Java 17, 21 hay mới hơn? Ví dụ record patterns và `when` chuẩn từ Java 21, nhưng `instanceof String s` đã chuẩn từ Java 16.
2. **Kiểu tĩnh của selector:** `Object`, sealed interface, enum, record hay generic type? Nó quyết định tính exhaustive và các pattern hợp lệ.
3. **Chính sách `null`:** đầu vào có thể null không, và null mang nghĩa gì? Trả giá trị, từ chối hay bảo đảm non-null tại API boundary?
4. **Domain contract:** phép phân loại nhằm format dữ liệu, parse command, thay đổi state hay xử lý nghiệp vụ? Có yêu cầu bảo vệ quyền, transaction hoặc giữ invariant không?
5. **Test matrix:** những subtype, guard, component null và exception nào được phép xảy ra?
6. **Chiến lược mở rộng:** hierarchy đóng bằng `sealed` hay có plugin/subtype do bên thứ ba cung cấp?

Không nên review `switch` pattern một cách tách rời khỏi hợp đồng dữ liệu. Cùng một `case null` có thể là xử lý hợp lệ ở tầng hiển thị, nhưng lại đang che lỗi đầu vào trong một API bắt buộc non-null.

## 3. Quy tắc chọn pattern hay polymorphism

### 3.1. Pattern thường hợp khi xử lý dữ liệu theo cấu trúc

~~~java
record Point(int x, int y) {}

static String format(Object value) {
    return switch (value) {
        case Point(var x, var y) -> "(" + x + "," + y + ")";
        case null -> "null";
        default -> "khác";
    };
}
~~~

Đây là phép **biến đổi dữ liệu sang chuỗi** dựa trên kiểu/shape. Record pattern giúp thấy rõ component cần dùng mà không phải ép kiểu hoặc gọi accessor từng bước.

### 3.2. Đa hình thường hợp khi hành vi thuộc subtype

~~~java
interface PriceRule {
    int apply(int price);
}

record FixedDiscount(int amount) implements PriceRule {
    public int apply(int price) {
        return Math.max(0, price - amount);
    }
}

record PercentDiscount(int percent) implements PriceRule {
    public int apply(int price) {
        return price * (100 - percent) / 100;
    }
}

static int finalPrice(PriceRule rule, int price) {
    return rule.apply(price);
}
~~~

Nếu hành vi là trách nhiệm cốt lõi của mỗi loại `PriceRule`, việc ép tất cả caller tự phân biệt `FixedDiscount`/`PercentDiscount` có thể làm tăng coupling và khiến plugin khó mở rộng. Ngược lại, muốn thêm nhiều operation ngoài miền dữ liệu đóng (format, mapping, biểu diễn UI), pattern switch có thể phù hợp hơn.

**Guideline:** review nên hỏi “logic này thuộc đối tượng hay thuộc một phép biến đổi bên ngoài?” trước khi tranh luận cú pháp nào nhanh hơn. Hiệu năng của virtual dispatch và pattern switch phụ thuộc JIT/workload; **không chặn PR bằng khẳng định tốc độ chưa có benchmark**.

## 4. Checklist type pattern và flow scoping

Một type pattern có thể gộp kiểm tra kiểu và khai báo biến:

~~~java
static int lengthIfText(Object input) {
    if (input instanceof String text && !text.isBlank()) {
        return text.length();
    }
    return 0;
}
~~~

Các điểm review:

- Biến `text` có kiểu `String` do compiler xác định.
- Toán tử `&&` short-circuit: `text.isBlank()` chỉ chạy khi `input` thật sự khớp `String`, nên truy cập biến hợp lệ.
- Với `input == null`, `instanceof String text` trả `false`, nên method trả 0, không có NPE do chính phép `instanceof`.
- Tên biến pattern cần nói rõ ý nghĩa; tránh đặt `x`, `s`, `o` ở những switch dài nhiều case.

**Sai về scope, compiler từ chối:**

~~~java
// KHÔNG BIÊN DỊCH: text không ở phạm vi hợp lệ ở vế phải ||.
// if (input instanceof String text || text.isBlank()) {
//     System.out.println(text);
// }
~~~

Khi vế trái của `||` sai, `text` chưa được ràng buộc; Java không cho phép sử dụng theo cách này. Đổi `||` thành `&&` **chỉ khi đúng ý nghĩa nghiệp vụ**. Không chỉnh operator chỉ để code compile rồi vô tình thay điều kiện.

Trường hợp sử dụng early return cũng được:

~~~java
static String requireNonBlankString(Object value) {
    if (!(value instanceof String text)) {
        return "không phải String";
    }
    return text.isBlank() ? "rỗng" : text.strip();
}
~~~

Nếu code dùng biến pattern sau một nhánh thoát sớm, reviewer cần kiểm tra **flow scoping**: compiler bảo đảm đã khớp ở đường thực thi đó hay chưa? Không tạo cast thừa khi pattern đã cho kiểu chính xác.

## 5. Checklist `switch` pattern: thứ tự, guard và dominance

Trong Java 21:

~~~java
static String label(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.isBlank() -> "BLANK";
        case String s -> "TEXT:" + s;
        default -> "OTHER";
    };
}
~~~

Review cần xác minh:

1. **Case cụ thể trước case tổng quát:** `String s when s.isBlank()` phải đứng trước `String s`.
2. **Guard dùng biến đã khớp:** `s` chỉ có giá trị trong nhánh/guard phù hợp, không được tham chiếu ở case khác.
3. **Thứ tự có chủ đích:** nếu hai pattern chồng lấp, nhánh đứng trước có thể quyết định kết quả; cần mô tả rõ quy tắc ưu tiên.
4. **Guard true/false đều được test:** `"  "` và `"Java"` khác nhau dù cùng kiểu `String`.
5. **Null có chính sách riêng:** có `case null` hoặc tiền điều kiện rõ; `default` không mặc định bắt null.
6. **Default có cần không:** selector `Object` thường cần `default`; selector sealed đầy đủ có thể không cần.

**Sai do dominance:**

~~~java
// CỐ Ý SAI: case String tổng quát che case String có guard.
// return switch (value) {
//     case String s -> s;
//     case String s when s.isBlank() -> "BLANK";
//     default -> "OTHER";
// };
~~~

Đây là lỗi **compile time**, không phải chỉ thiếu test. Một review comment tốt:

> **Block:** Nhánh `case String s` phía trước dominate case có `when`, khiến compiler từ chối. Chuyển nhánh có guard lên trước nhánh String tổng quát và thêm test cho chuỗi trắng lẫn chuỗi thường.

Không yêu cầu thêm `default` như cách che lỗi dominance; phải sửa **thứ tự và ý nghĩa pattern**.

## 6. Checklist `null`: selector null khác component null

### 6.1. Selector của switch là null

~~~java
static String unsafe(Object value) {
    return switch (value) {
        case String s -> s;
        default -> "OTHER";
    };
}
~~~

`unsafe(null)` ném **`NullPointerException`**, không trả `"OTHER"`. Nếu hợp đồng cho phép null, bổ sung `case null`. Nếu hợp đồng cấm null, kiểm tra bằng `Objects.requireNonNull(value, "...")` hoặc ném exception rõ ràng ở boundary.

**Mức review:** thường **Block** nếu input null thực sự có thể đến và code hiện tại gây NPE ngoài dự kiến. Nếu hợp đồng đã bảo đảm non-null bằng điều kiện đủ mạnh, reviewer nên đề nghị thể hiện hợp đồng/tests thay vì tự giả định bug.

### 6.2. Component trong record là null

~~~java
record Point(int x, int y) {}
record Moved(Point target) {}

static String move(Object value) {
    return switch (value) {
        case Moved(Point(var x, var y)) -> "Đến " + x + "," + y;
        case Moved(var target) -> "Chưa có đích";
        case null -> "Thiếu dữ liệu";
        default -> "Khác";
    };
}
~~~

Với `new Moved(null)`, selector **không null**, nhưng nested record pattern `Point(...)` không khớp vì component target null; nhánh `Moved(var target)` tiếp nhận dữ liệu đó. Đây là case fallback khác hoàn toàn `case null` của switch.

Một **unconditional component pattern** như `var target` có thể ràng buộc reference component bằng null. Vì vậy nếu nhánh sau gọi `target.toString()` hoặc `target.x()` mà không kiểm tra, có thể NPE **bên trong branch**.

**Guideline:** khi thấy `RecordA(RecordB(...))`, xem hợp đồng null của component tương ứng. Test ít nhất một trường hợp component null nếu dữ liệu cho phép và cần fallback.

## 7. Checklist record pattern: đúng cấu trúc và không lạm dụng

Record pattern ghép component **theo thứ tự khai báo**, không theo tên của pattern variable:

~~~java
record User(String name, int age) {}

static String summarize(Object obj) {
    return switch (obj) {
        case User(var name, var age) -> name + " (" + age + ")";
        case null -> "null";
        default -> "khác";
    };
}
~~~

Các câu reviewer nên hỏi:

- Kiểu ngoài có thực sự là **record**? Java 21 không có constructor pattern tổng quát cho mọi class thường.
- Số component pattern có đúng với số component trong record?
- Các kiểu có tương thích với từng component? `User(String name, int age)` đúng; `User(int age, String name)` sai.
- Tên biến đã rõ vai trò và có tránh tráo vị trí khi hai component cùng kiểu `String`?
- Chỉ cần một accessor thì liệu `case User user -> user.name()` dễ đọc hơn `User(var name, var ignoredAge)`?
- Pattern lồng sâu trên ba cấp có còn giúp đọc code, hay nên tách thành hàm phụ/đặt tên cho cấu trúc?
- Record có component là collection mutable hay tham chiếu nullable, và code có bảo vệ chúng đúng hợp đồng?

`var` trong record pattern là **suy luận kiểu tĩnh**, không phải dynamic typing; nó cũng không làm mọi component non-null. Record có field `final` nhưng chứa `List` mutable vẫn cần defensive copy nếu muốn bất biến theo giá trị.

## 8. Checklist guard `when`: sự thuần túy và thứ tự điều kiện

Guard là công cụ hữu ích nhưng không nên biến thành nơi thực thi workflow:

~~~java
case LabelChanged(var sku, var label)
        when label == null || label.isBlank() ->
    "Nhãn trống: " + sku;
~~~

Ưu điểm của guard này:

- Đọc được như một **điều kiện chọn nhánh**.
- Dùng short-circuit để tránh gọi `isBlank()` khi label null.
- Không thay đổi state; cùng một giá trị đầu vào cho cùng kết quả.
- Có thể test điều kiện theo từng trạng thái: null, chỉ khoảng trắng, có nội dung.

Những dạng guard nên xem lại:

~~~java
// Gợi ý tránh trong guard:
// case Command c when repository.save(c) -> ...
// case Request r when auditService.send(r) -> ...
~~~

Các lời gọi lưu database, gửi mạng hoặc ghi audit có side effect và có thể ném exception. Đặt chúng trong guard làm quá trình **chọn case** phụ thuộc vào I/O, thứ tự thử nhánh và trạng thái bên ngoài; code khó giải thích, khó test, khó đảm bảo transaction. Đưa hành vi đó vào handler/service sau khi case phù hợp được chọn.

**Không phải mọi lời gọi phương thức trong `when` đều sai.** Một predicate thuần như `s.isBlank()` hoặc một hàm validation đơn giản có hợp đồng rõ ràng là hợp lý. Reviewer nên đánh giá **side effect, chi phí và khả năng ném lỗi**, không cấm guard một cách máy móc.

## 9. Checklist sealed hierarchy và exhaustive switch

Ví dụ:

~~~java
sealed interface Event permits Created, Deleted {}
record Created(int id) implements Event {}
record Deleted(int id) implements Event {}

static String eventName(Event event) {
    return switch (event) {
        case null -> "NONE";
        case Created(var id) -> "CREATED:" + id;
        case Deleted(var id) -> "DELETED:" + id;
    };
}
~~~

Vì Java biết tập subtype hợp lệ của `Event`, switch expression có thể exhaustive **không cần `default`**. Đây là tín hiệu tốt khi review API có hierarchy đóng: lúc thêm subtype mới, compiler có thể buộc cập nhật các switch liên quan.

**Checklist:**

- Nếu chủ đích là xử lý đầy đủ một sealed hierarchy, nên cân nhắc **không có `default`** để giữ tín hiệu exhaustiveness.
- Nếu cần fallback vì API cho phép subtype ngoài dự kiến, phải viết lý do rõ ràng; tránh `default -> null` chỉ để im lặng.
- `case null` là **chính sách runtime**, không thay thế exhaustive checking của subtype.
- Các case có guard phải được bố trí để những giá trị **guard false** vẫn có nhánh xử lý đúng.
- Thêm subtype hoặc đổi record components là thay đổi API, cần cập nhật test/contract/documentation.

**Lưu ý:** sealed hierarchy không nhất thiết là lựa chọn đúng cho plugin API mở. Nếu bên thứ ba phải tự implement interface, `sealed` có thể ngăn mở rộng không mong muốn. Đừng đổi interface mở thành sealed chỉ để viết switch không `default`.

## 10. Checklist generic pattern và type erasure

Một vấn đề thường bị bỏ qua khi review code Java generics:

~~~java
record Box<T>(T value) {}
~~~

Đầu vào chỉ có kiểu `Object` **không** thể được kiểm tra như `Box<String>` tùy ý ở runtime, vì generic type arguments không được lưu đầy đủ trong instance sau **type erasure**:

~~~java
// KHÔNG BIÊN DỊCH với Object input:
// if (input instanceof Box<String>(var text)) {
//     System.out.println(text);
// }
~~~

Cách làm an toàn hơn:

~~~java
static String boxLabel(Object input) {
    if (input instanceof Box<?>(var value)
            && value instanceof String text) {
        return text.toUpperCase();
    }
    return "Không có String";
}
~~~

`Box<?>` không hứa hẹn generic argument cụ thể, còn `value instanceof String text` xác minh kiểu component thật. Hãy review mọi pattern trên generic record để tránh unchecked cast, raw types và lời hứa sai về type safety.

**Block** nếu một thay đổi đưa cast không an toàn có khả năng gây `ClassCastException` hoặc phá vỡ hợp đồng kiểu. **Suggestion** nếu cùng hành vi đã type-safe nhưng cách đặt wildcard/biến làm code khó hiểu.

## 11. Checklist exception, dữ liệu đầu vào và bảo mật

Pattern matching **không thay thế validation**. Một `case` match đúng subtype không chứng minh dữ liệu bên trong hợp lệ:

~~~java
record Transfer(String account, long amount) {}
~~~

`case Transfer(var account, var amount)` có thể khớp dù `account == null` hoặc `amount <= 0`, trừ khi constructor đã từ chối các giá trị đó. Với domain quan trọng:

- Điều kiện độc lập của dữ liệu nên được bảo vệ trong constructor/value object hoặc validation layer.
- Quy tắc cần trạng thái, quyền hoặc nguồn dữ liệu bên ngoài phải xử lý ở application/domain service.
- `case null` cần quyết định có chấp nhận input rỗng hay ném lỗi; không biến dữ liệu không hợp lệ thành thành công giả.
- Guard không nên gọi API không đáng tin hoặc ghi side effect rồi quyết định có “match” hay không.
- Pattern variable lấy từ input **không tự trở thành dữ liệu đáng tin**: cần kiểm tra phân quyền, giới hạn độ dài, định dạng, số lượng và escape/output đúng ngữ cảnh.
- Việc đặt mọi thứ dưới `default -> "OK"` có thể che trường hợp không hỗ trợ; nên trả lỗi có ý nghĩa khi cần.

Đừng tự động yêu cầu bắt mọi `NullPointerException`. Ưu tiên **điều kiện đầu vào rõ ràng**, kiểm tra tại nơi hợp lý và test tình huống bất thường. Nếu record accessor được tự triển khai và ném exception, quá trình deconstruction không nên được xem là hoàn toàn không có hành vi; reviewer cần hiểu contract của accessor.

## 12. Checklist test: coverage theo đường đi, không chỉ số lượng case

Với pattern switch:

~~~java
return switch (value) {
    case null -> "NULL";
    case String s when s.isBlank() -> "BLANK";
    case String s -> "TEXT";
    default -> "OTHER";
};
~~~

Ít nhất nên test bốn nhóm: selector null, String blank, String non-blank, và kiểu khác. Nếu guard chứa `||` hoặc `&&`, kiểm tra các **đường short-circuit** có ý nghĩa nghiệp vụ.

Một ma trận tối thiểu cho code review:

| Nhóm đầu vào | Kiểm tra kỳ vọng |
| --- | --- |
| `null` selector | Kết quả/exception theo chính sách |
| Pattern khớp và guard đúng | Nhánh chuyên biệt trả kết quả đúng |
| Pattern khớp và guard sai | Chuyển sang case chung/fallback đúng |
| Type pattern không khớp | Nhánh khác hoặc default đúng |
| Record component bằng null | Nested pattern/fallback và xử lý field null |
| Thêm subtype sealed | Compiler/test phát hiện switch không đầy đủ |
| Dữ liệu không hợp lệ | Validation/exception, không trả thành công |
| Input biên | Zero, âm, chuỗi trắng, rỗng, giá trị cực đại theo domain |

**JaCoCo branch coverage (C1)** tính các nhánh control-flow từ bytecode, **không đồng nhất một-một với số nhãn `case`**. Coverage cao không chứng minh assertion đủ mạnh, guard được test mọi tổ hợp quan trọng hoặc các đường exception đã được kiểm tra. Dùng **ma trận input + assertion + coverage report**, không chỉ một con số %.

Ở cấp PR, reviewer nên yêu cầu test có nội dung: “Với `Moved(null)` phải vào nhánh `NO_TARGET`” tốt hơn “thêm test cho switch”.

## 13. Ví dụ Java 21+ hoàn chỉnh theo guideline

Mã sau thể hiện một hierarchy đóng với các record command dữ liệu, guard chuyên biệt, xử lý null selector và null component, nested record patterns, đồng thời không có `default` che subtype mới.

Tạo file **`PatternReviewGuideDemo.java`**:

~~~java
public class PatternReviewGuideDemo {
    sealed interface Change
            permits QuantityChanged, LabelChanged, Moved, Closed {}

    record QuantityChanged(String sku, int quantity)
            implements Change {}

    record LabelChanged(String sku, String label)
            implements Change {}

    record Point(int x, int y) {}
    record Moved(Point target) implements Change {}
    record Closed(String reason) implements Change {}

    static String describe(Change change) {
        return switch (change) {
            case null -> "Không có thay đổi";

            case QuantityChanged(var sku, var quantity)
                    when quantity <= 0 ->
                "Số lượng không hợp lệ: " + sku;

            case QuantityChanged(var sku, var quantity) ->
                "Đặt " + quantity + " cho " + sku;

            case LabelChanged(var sku, var label)
                    when label == null || label.isBlank() ->
                "Nhãn trống: " + sku;

            case LabelChanged(var sku, var label) ->
                "Đổi nhãn " + sku + ": " + label.strip();

            case Moved(Point(var x, var y))
                    when x == y ->
                "Di chuyển đường chéo: " + x;

            case Moved(Point(var x, var y)) ->
                "Di chuyển đến (" + x + "," + y + ")";

            case Moved(var target) ->
                "Thiếu điểm đến";

            case Closed(var reason) ->
                "Đóng: " + (reason == null
                        ? "không rõ" : reason.strip());
        };
    }

    static void verify(String name, Change change, String expected) {
        String actual = describe(change);
        if (!actual.equals(expected)) {
            throw new AssertionError(name + ": "
                    + actual + " != " + expected);
        }
        System.out.println(name + " -> " + actual);
    }

    public static void main(String[] args) {
        verify("null", null, "Không có thay đổi");

        verify("qty-invalid",
                new QuantityChanged("SKU-1", 0),
                "Số lượng không hợp lệ: SKU-1");
        verify("qty-valid",
                new QuantityChanged("SKU-1", 3),
                "Đặt 3 cho SKU-1");

        verify("label-null",
                new LabelChanged("SKU-2", null),
                "Nhãn trống: SKU-2");
        verify("label-blank",
                new LabelChanged("SKU-2", "  "),
                "Nhãn trống: SKU-2");
        verify("label-valid",
                new LabelChanged("SKU-2", "  Mới  "),
                "Đổi nhãn SKU-2: Mới");

        verify("move-diagonal",
                new Moved(new Point(2, 2)),
                "Di chuyển đường chéo: 2");
        verify("move-other",
                new Moved(new Point(2, 5)),
                "Di chuyển đến (2,5)");
        verify("move-null", new Moved(null),
                "Thiếu điểm đến");

        verify("close-null", new Closed(null),
                "Đóng: không rõ");
        verify("close-valid",
                new Closed("  hoàn tất  "),
                "Đóng: hoàn tất");
    }
}
~~~

Biên dịch và chạy với JDK 21+:

~~~bash
javac --release 21 -encoding UTF-8 PatternReviewGuideDemo.java
java PatternReviewGuideDemo
~~~

Đầu ra:

~~~text
null -> Không có thay đổi
qty-invalid -> Số lượng không hợp lệ: SKU-1
qty-valid -> Đặt 3 cho SKU-1
label-null -> Nhãn trống: SKU-2
label-blank -> Nhãn trống: SKU-2
label-valid -> Đổi nhãn SKU-2: Mới
move-diagonal -> Di chuyển đường chéo: 2
move-other -> Di chuyển đến (2,5)
move-null -> Thiếu điểm đến
close-null -> Đóng: không rõ
close-valid -> Đóng: hoàn tất
~~~

### Nhìn bài demo dưới con mắt reviewer

**Điểm tốt:**

- Hierarchy `Change` đóng; `switch` xử lý đủ bốn subtype và `case null`, không cần `default`.
- Guard chuyên biệt đứng trước case tổng quát của `QuantityChanged`/`LabelChanged`/`Moved`.
- Guard cho label dùng `||` đúng: nếu `label == null` thì không gọi `label.isBlank()`.
- Nested `Point(...)` chỉ khớp khi `Moved.target` có một đối tượng Point; `Moved(null)` đi vào case tổng quát, không đánh đồng với null selector.
- `verify` có assertion; nếu một kết quả sai, chương trình ném `AssertionError` thay vì chỉ in lời khẳng định.

**Điểm cần cân nhắc trong ứng dụng thực:**

- Demo dùng record không có constructor validation để minh họa đường input không hợp lệ. Với hệ thống nghiệp vụ, nên quyết định rõ invariant nào phải bị từ chối ngay khi tạo command.
- `Closed(null)` được biến thành “không rõ” trong formatter; nếu lý do đóng là bắt buộc, **không** nên âm thầm chấp nhận null.
- Các nhãn hiển thị trực tiếp từ `sku`/`label` phù hợp demo, nhưng dữ liệu bên ngoài ứng dụng có thể cần escaping/encoding trong UI hay log tùy ngữ cảnh.
- Pattern switch dài có thể nên chia thành hàm `describeQuantity`, `describeMove` nếu logic tăng; mục tiêu là code dễ review chứ không phải tối đa số pattern trên một màn hình.

## 14. Ma trận review cho chương trình ví dụ

| ID | Input | Nhánh hoặc điều kiện được chứng minh |
| --- | --- | --- |
| T1 | `null` | Selector null, không khớp bất kỳ record nào |
| T2 | `QuantityChanged("SKU-1", 0)` | Quantity guard true |
| T3 | `QuantityChanged("SKU-1", 3)` | Quantity guard false, case chung |
| T4 | `LabelChanged("SKU-2", null)` | Guard: vế trái `label == null` true, short-circuit |
| T5 | `LabelChanged("SKU-2", "  ")` | Guard: vế trái false, `isBlank()` true |
| T6 | `LabelChanged("SKU-2", "  Mới  ")` | Guard false, case thường và `strip()` |
| T7 | `Moved(Point(2,2))` | Nested Point khớp, guard `x == y` true |
| T8 | `Moved(Point(2,5))` | Nested Point khớp, guard false |
| T9 | `Moved(null)` | Nested Point không khớp, case `Moved(var target)` |
| T10 | `Closed(null)` | Unconditional component pattern nhận null, branch xử lý |
| T11 | `Closed("  hoàn tất  ")` | Closed thông thường và chuẩn hóa text |

Ma trận trên chứng minh những **đường đi hành vi đã chạy** trong demo. Đây **không** phải số liệu C1 JaCoCo; muốn có tỷ lệ coverage thật cần chạy build/test được instrument bởi công cụ coverage.

## 15. Mẫu comment code review: ngắn, có bằng chứng, có cách sửa

Một comment hữu ích nên có: **vị trí → vấn đề → trường hợp xảy ra → ảnh hưởng → cách sửa/test**. Dưới đây là những cách viết có thể áp dụng:

### Comment A — `default` không xử lý null

> **Request changes — null handling:** `switch (input)` đang nhận dữ liệu từ API có thể null. Nhánh `default` không nhận null, vì vậy request có `input == null` sẽ ném NPE. Đề nghị thêm `case null` theo hợp đồng hoặc kiểm tra non-null ở boundary; bổ sung test `input == null`.

### Comment B — guard bị case trước che

> **Block — dominance:** `case String s` đã bắt mọi String trước `case String s when s.isBlank()`. Java sẽ báo nhánh sau bị dominate. Vui lòng đưa guard lên trước case chung; test cả chuỗi blank và non-blank.

### Comment C — component lồng có thể null

> **Request changes — nested record:** `case Moved(Point(var x,var y))` không khớp khi `target == null`. Nếu dữ liệu cũ có thể thiếu target, cần case `Moved(var target)` fallback hoặc validation sớm; thêm test đối tượng `Moved(null)`.

### Comment D — dùng pattern nhưng tăng coupling

> **Suggestion — responsibility:** Handler đang switch trên nhiều implementation chỉ để gọi một hành vi vốn thuộc từng implementation. Cân nhắc method trên interface nếu hierarchy cần mở rộng hoặc hành vi cần bảo vệ invariant riêng; giữ pattern switch nếu đây thực sự là phép biến đổi dữ liệu ở boundary.

### Comment E — chưa test guard false

> **Request changes — tests:** Hiện chỉ có test `LabelChanged(null)`. Đề nghị thêm label trắng và label hợp lệ để xác minh cả nhánh `isBlank() == true` sau khi null-check false, và nhánh `LabelChanged` không guard.

### Comment F — hiệu năng chưa có bằng chứng

> **Suggestion — performance:** Mô tả “pattern switch luôn nhanh hơn gọi method” chưa có số liệu. Đề nghị bỏ khẳng định tuyệt đối; nếu latency quan trọng, so sánh bằng JMH với cùng workload và xác minh ảnh hưởng end-to-end.

**Không cần sao chép nguyên comment mẫu** cho mọi PR. Dùng giọng điệu hợp tác, chỉ nêu yêu cầu blocker khi có căn cứ và đưa cách kiểm chứng có thể thực hiện.

## 16. Checklist có thể chép vào Pull Request template

Một nhóm có thể đưa phần sau vào mẫu PR của repository. Đây là **mẫu checklist**, không cần mọi mục đều áp dụng với mọi PR:

~~~markdown
### Pattern matching review (nếu PR có instanceof/switch/record patterns)

- [ ] Source/release của project phù hợp cú pháp được dùng (Java 21 cho record/switch patterns).
- [ ] Pattern matching có lý do rõ so với cast hoặc polymorphic dispatch.
- [ ] Các type/record patterns tương thích kiểu tĩnh và đúng số component.
- [ ] Pattern variables chỉ dùng trong phạm vi flow scoping hợp lệ.
- [ ] Case có when/guard đứng trước pattern tổng quát khi cần.
- [ ] Guard không gây side effect ngoài dự kiến; điều kiện &&/|| null-safe.
- [ ] Null selector có chính sách rõ (case null, requireNonNull hoặc hợp đồng).
- [ ] Null component của nested record đã được xét nếu dữ liệu có thể thiếu.
- [ ] Sealed switch exhaustive không bị default che thiếu subtype mới khi cần.
- [ ] Generic pattern không dựa vào unchecked cast hoặc giả định type erasure sai.
- [ ] Unit tests có guard true/false, subtype khác, null và lỗi đầu vào liên quan.
- [ ] Nếu PR nói về hiệu năng, có profiling/benchmark đại diện thay vì suy đoán.
- [ ] API contract, thay đổi subtype/record components và docs được cập nhật.
~~~

Tại nơi code review, mỗi ô checklist nên gắn với **đoạn code hoặc test thật**. Không phải PR nào cũng cần check “null component” nếu mọi component liên quan đều primitive hoặc invariant constructor bảo đảm non-null.

## 17. Tích hợp guideline vào quy trình của nhóm

Để guideline không chỉ tồn tại trên giấy:

1. **Chốt version contract** trong build (ví dụ Maven compiler release 21) và đưa nó vào phần đầu checklist.
2. **Lưu tài liệu review ngắn** ở repository, kèm liên kết tới JEP/JLS và một ví dụ runnable.
3. **Thêm PR template** như mục 16; tách mục *Block* và *Suggestion* để thống nhất mức độ phản hồi.
4. **Yêu cầu compile/test trong CI**: compiler bắt lỗi dominance, type/scope/exhaustiveness; test kiểm tra semantic cases không thể bắt chỉ bằng compile.
5. **Tạo bảng test matrix** cho các switch nhiều guard hoặc nested record patterns. Đưa các nhóm input cụ thể vào test names.
6. **Review PR mẫu theo cặp** để thống nhất cách dùng `when`, `case null`, `sealed` và mức độ chấp nhận pattern lồng.
7. **Quan sát các bug lặp lại**: nếu một loại lỗi nhiều lần xuất hiện, thêm guideline hoặc static analysis phù hợp; không viết luật cấm tuyệt đối nếu chưa có căn cứ.
8. **Đánh giá lại sau khi nâng JDK/Jacoco/compiler** vì bytecode, tính năng ngôn ngữ và cơ hội JIT tối ưu có thể thay đổi.

### CI gate nên kiểm tra gì?

**Compile:** chạy build ở Java release đã chốt, ví dụ:

~~~bash
javac --release 21 -encoding UTF-8 PatternReviewGuideDemo.java
java PatternReviewGuideDemo
~~~

Với Maven/Gradle, dùng `mvn test` hoặc `./gradlew test` tùy project đã cấu hình đúng. Có thể đặt test coverage gate theo chính sách nhóm, nhưng **không** dùng một con số coverage duy nhất để thay thế review test matrix và các assertion.

**Static analysis:** Checkstyle, SpotBugs, Error Prone hoặc rule riêng có thể hỗ trợ một số vấn đề, tùy công cụ và phiên bản Java; không được cho rằng công cụ mặc định nhận diện mọi lỗi pattern matching. Những quy tắc về domain contract, độ rõ của guard, chính sách null và lợi ích polymorphism vẫn cần reviewer đánh giá.

**Không tự động sửa code:** một lint rule có thể đề xuất chuyển `instanceof` sang pattern hoặc thêm `default`, nhưng reviewer phải xác nhận thay đổi không làm mất exhaustiveness, đổi logic hoặc che null path.

## 18. Những lỗi guideline dễ mắc

| Anti-pattern trong review | Tại sao không tốt | Cách cải thiện |
| --- | --- | --- |
| “Mọi `instanceof` phải đổi thành `switch`” | Không phù hợp code chỉ có một type check, có thể làm phức tạp | Chọn cấu trúc nhỏ nhất diễn đạt đúng nghiệp vụ |
| “Luôn thêm `default` để khỏi lỗi compile” | Có thể che subtype mới trong sealed hierarchy | Ưu tiên exhaustive case list khi cần |
| “`case Object obj` sẽ bắt cả null” | Null selector có quy tắc riêng | `case null` hoặc tiền điều kiện |
| “Record pattern luôn làm component non-null” | Component reference có thể là null | Xét nested pattern và unconditional component |
| “`var` nghĩa là kiểu động” | Compiler suy luận kiểu tĩnh của component | Xem khai báo record, đặt tên rõ |
| “Guard có thể gọi mọi service” | Dễ có side effect, I/O và exception khó kiểm soát | Giữ guard thuần, xử lý hành vi ở handler |
| “Chỉ cần một test cho mỗi nhãn case” | Bỏ sót guard false/short-circuit và null nested component | Dùng ma trận đường đi |
| “100% branch coverage nghĩa không còn bug” | Coverage đo thực thi, không chứng minh correctness | Có assertion, boundary/exception tests |
| “Pattern nhanh hơn virtual dispatch” | Tùy JIT, profiling và workload | Đo benchmark nếu hiệu năng là bottleneck |
| “Thấy code dài là bắt phải dùng pattern lồng sâu” | Pattern lồng quá sâu có thể khó bảo trì | Tách hàm và cân nhắc accessor/type pattern |
| “Comment 'sai style' mà không giải thích” | Reviewer thiếu cơ sở, dễ tranh luận vô ích | Gắn với hợp đồng, ví dụ, lỗi/test và đề xuất |
| “Block mọi gợi ý nhỏ” | PR ùn tắc, giảm tin cậy review | Phân mức Block / Should improve / Suggestion |

## 19. Bài tập review

**Bài 1 — Nhận diện blocker.** Một PR thêm:

~~~java
static String status(Object input) {
    return switch (input) {
        case String s -> s;
        case String s when s.isEmpty() -> "EMPTY";
        default -> "OTHER";
    };
}
~~~

Điểm nào chắc chắn gây lỗi compile time? Nếu input có thể null, còn vấn đề nào xảy ra ở runtime? Viết một comment review có đề xuất cụ thể.

**Bài 2 — Phân biệt hai loại null.** Với `record Moved(Point target) {}`, đầu vào `null` và `new Moved(null)` có như nhau không khi dùng `switch`? Test nào cần bổ sung?

**Bài 3 — Test guard.** Với `label == null || label.isBlank()`, ba input `null`, `"  "` và `"ok"` kiểm tra những đường đi nào? Vì sao chỉ test `null` không đủ?

**Bài 4 — Sealed API.** Một reviewer đề nghị thêm `default -> "UNKNOWN"` vào mọi switch trên sealed interface có đủ các subtype. Khi nào nên từ chối đề nghị này, và khi nào fallback thực sự có lý do?

**Bài 5 — Review priority.** Đánh dấu *Block* hay *Suggestion* cho ba trường hợp: (a) `when` gọi `repository.save()` gây side effect; (b) pattern variable tên `s` trong method hai dòng; (c) PR ghi “tối ưu 40%” nhưng không có benchmark và thay logic nghiệp vụ. Giải thích mức độ dựa trên tác động thực tế.

**Bài 6 — Generic pattern.** Vì sao `Object input instanceof Box<String>(var s)` không được kiểm tra an toàn? Nêu một mẫu thay thế dùng wildcard và kiểm tra giá trị component.

**Gợi ý đáp án:**

- Bài 1: `case String s` đứng trước khiến case guard bị **dominated**. Đưa nhánh guard lên trước; nếu null có thể xuất hiện, cần xử lý `case null` hoặc chặn tại boundary, vì `default` không bắt null.
- Bài 2: selector null cần `case null` riêng; `new Moved(null)` là record không null có component null, có thể vào nhánh `Moved(var target)`.
- Bài 3: lần lượt kiểm tra vế trái true, vế trái false/vế phải true và hai vế false. Thêm cả input subtype khác nếu switch nhận kiểu rộng và logic yêu cầu.
- Bài 4: không dùng `default` chỉ vì thói quen nếu muốn compiler buộc cập nhật xử lý subtype mới. Fallback hợp lý khi API/domain thực sự định nghĩa hành vi cho giá trị không hỗ trợ.
- Bài 5: (a) thường Request changes vì hành vi và chọn nhánh bị trộn; (b) thường Nit/Suggestion; (c) Request changes vì claim và logic sai không được chứng minh.
- Bài 6: type erasure; dùng `Box<?>(var item)` rồi kiểm tra `item instanceof String text`.

## 20. Kết luận

Một guideline hiệu quả cho pattern matching trong code review không phải tập luật yêu thích cú pháp. Nó là **thỏa thuận kỹ thuật có thể kiểm chứng**:

- Chọn pattern khi nó làm rõ data shape và phép biến đổi; chọn polymorphism khi hành vi thuộc subtype.
- Giữ **case order, guard, type compatibility và flow scoping** hợp lệ; để compiler giúp phát hiện dominance và thiếu exhaustive case.
- Xử lý **selector null**, **record component null** và generic erasure theo hợp đồng thực tế.
- Review bằng **input/test matrix**, không chỉ bằng số dòng/nhãn `case` hoặc tỷ lệ coverage.
- Đưa nhận xét có **mức độ, ví dụ tái hiện và đề xuất sửa**, thay vì chặn vì style tùy ý.
- Duy trì checklist trong PR template và CI, cập nhật theo baseline Java của dự án.

### Tài liệu tham khảo

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): switch patterns, guards `when`, exhaustiveness, dominance và null (Java 21).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): deconstruction, nested record patterns và component matching (Java 21).
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): các subtype được phép và mô hình đóng.
- [JLS 21 `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): ngữ nghĩa và kiểm tra pattern.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
