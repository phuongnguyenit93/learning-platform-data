# Review readability của pattern matching trong Java 21+

## 1. Mục tiêu của code review: dễ hiểu, đúng hành vi, dễ thay đổi

Pattern matching giúp Java diễn đạt kiểm tra kiểu và cấu trúc dữ liệu ngắn gọn hơn so với chuỗi `instanceof` + cast thủ công. Nhưng **ít dòng code không đồng nghĩa với dễ đọc**. Một `switch` chứa nhiều type patterns, nested record patterns và guard `when` có thể biên dịch đúng mà vẫn khó hiểu: người review phải tự suy luận thứ tự ưu tiên, trường hợp null, hành vi khi kiểu mới xuất hiện và các hiệu ứng phụ bị giấu trong biểu thức.

Bài học này hướng dẫn **review readability của pattern matching**: đánh giá xem người khác có thể đọc, kiểm tra tính đúng và bảo trì mã mà không phải mô phỏng quá nhiều điều kiện trong đầu hay không.

Nguyên tắc mở đầu:

> Review không chỉ hỏi “pattern có hợp lệ theo compiler không?” mà còn hỏi “pattern này có thể hiện rõ một quy tắc nghiệp vụ, giữ đúng hành vi và hỗ trợ thay đổi an toàn không?”.

Ba tiêu chí phải đồng thời đạt:

1. **Correctness:** khớp đúng kiểu/cấu trúc, đúng thứ tự case, đúng null/fallback, exhaustive khi cần.
2. **Clarity:** tên biến thể hiện domain, guard ngắn và có ý nghĩa, nested patterns không quá khó theo dõi, mỗi method có trách nhiệm rõ ràng.
3. **Maintainability:** reviewer xác định được chỗ sửa khi thêm subtype hoặc quy tắc mới, có điểm test cho các giá trị biên, không giấu side effect hay lỗi runtime.

**Phiên bản:** `instanceof` pattern chính thức từ Java 16 (JEP 394); record patterns và pattern matching for `switch` chính thức từ **Java 21** (JEP 440 và JEP 441). Các ví dụ chính dùng **JDK 21+**, không cần `--enable-preview`.

## 2. Những thành phần cần nhìn thấy khi đọc code

Xét ví dụ:

```java
record Point(int x, int y) {}

String position = switch (value) {
    case Point(int x, int y) when x == 0 && y == 0 ->
            "origin";
    case Point(int x, int y) when x > 0 && y > 0 ->
            "quadrant I";
    case Point(int x, int y) ->
            "other point";
    case null -> "missing";
    default -> "not a point";
};
```

Người review nên phân biệt được:

- **Selector `value`:** biểu thức đầu vào của `switch`. Kiểu tĩnh của selector quyết định các nhãn `case` nào có thể áp dụng.
- **Record pattern `Point(int x, int y)`:** kiểm tra một `Point` và trích xuất component `x`, `y`.
- **Pattern variables:** `x`, `y` chỉ được phép sử dụng trong scope compiler chứng minh pattern đã khớp.
- **Guard `when`:** lọc thêm theo giá trị, được xét sau khi pattern phù hợp; `when` khác với điều kiện ngay trong `if`.
- **Arrow rule `->`:** chỉ thân nhánh được chọn được thực thi, không fall-through sang nhánh khác.
- **Nhánh không guard:** là điểm bao phủ các `Point` còn lại; không nên đứng trước các nhánh `Point` có guard.
- **`case null`/`default`:** có vai trò khác nhau. Trong pattern switch, `default` không mặc nhiên thay thế việc xử lý null selector.

Nếu người đọc phải dò ngược nhiều method mới biết guard bảo vệ điều kiện gì, hoặc không thể xác định nhánh nào chịu trách nhiệm cho một subtype, đó là tín hiệu cần làm rõ thiết kế trước khi merge.

## 3. Khung review theo sáu lớp

| Lớp review | Câu hỏi trọng tâm | Dấu hiệu cần kiểm tra |
| --- | --- | --- |
| **Ý định nghiệp vụ** | Đoạn matching đang phân loại gì, vì sao? | Tên pattern, tên case/handler, một method có quá nhiều trách nhiệm |
| **Thứ tự khớp** | Nhánh ưu tiên và fallback có rõ ràng không? | Type cha/con, guard chồng lấn, dominated case |
| **Cấu trúc dữ liệu** | Record pattern có thể đọc liền mạch không? | Độ sâu nesting, quá nhiều component, nullable component |
| **Biểu thức và scope** | Guard và biến pattern có dễ suy luận không? | `when` quá dài, `&&`/`||`, tên biến mơ hồ, type checking |
| **An toàn runtime** | Null, ngoại lệ, side effects có minh bạch không? | Accessor tùy biến, gọi I/O trong guard, thay đổi fallback |
| **Khả năng tiến hóa** | Thêm subtype/quy tắc có bị bỏ sót không? | Exhaustive sealed switch, `default` quá rộng, bộ test giá trị biên |

Không cần chấm “điểm đẹp” từng dòng. Mục tiêu là có nhận xét **cụ thể và kiểm chứng được**: điều kiện nào khó hiểu, đầu vào nào gây nhầm, tên nào không cho thấy domain, hoặc trường hợp nào chưa có test.

## 4. Ví dụ đầy đủ: review và cải thiện một switch dài

### 4.1. Bối cảnh

Giả sử một hệ thống phân loại bốn trường hợp: `Login`, `Purchase`, `Heartbeat` và selector null. `Event` là sealed interface; riêng `Purchase` có record lồng `Money`. Chính sách:

- Login thành công với username không null/không blank → `LOGIN_OK`; các trường hợp còn lại → `LOGIN_REVIEW`.
- Purchase với giá trị từ 10.000 cents và buyer hợp lệ → `PURCHASE_LARGE`.
- Purchase với cents dương còn lại → `PURCHASE`; buyer null sẽ hiển thị `unknown`.
- Purchase có money null hoặc cents không dương → `PURCHASE_REVIEW`.
- Heartbeat → `PING`; selector null → `MISSING`.

Bản `before` dùng nhiều case/guard để vừa xác định loại event vừa thực hiện chính sách nghiệp vụ. Bản `after` dành `switch` cho **điều phối theo loại**, chuyển quy tắc riêng của Login/Purchase sang helper đặt tên rõ ràng.

Lưu file **`PatternReadabilityReviewDemo.java`**:

```java
public class PatternReadabilityReviewDemo {
    sealed interface Event permits Login, Purchase, Heartbeat {}

    record Login(String user, boolean success) implements Event {}
    record Money(int cents) {}
    record Purchase(String buyer, Money money) implements Event {}
    record Heartbeat(long timestamp) implements Event {}

    // Bản đầu: hợp lệ, nhưng nhiều chính sách trộn trong một switch.
    static String before(Event event) {
        return switch (event) {
            case Login(var user, boolean success)
                    when success && user != null && !user.isBlank() ->
                    "LOGIN_OK:" + user;
            case Login(var user, var success) -> "LOGIN_REVIEW";

            case Purchase(var buyer, Money(int cents))
                    when cents >= 10_000
                            && buyer != null && !buyer.isBlank() ->
                    "PURCHASE_LARGE:" + buyer;
            case Purchase(var buyer, Money(int cents)) when cents > 0 ->
                    "PURCHASE:" + (buyer == null ? "unknown" : buyer);
            case Purchase(var buyer, var money) -> "PURCHASE_REVIEW";

            case Heartbeat(var timestamp) -> "PING";
            case null -> "MISSING";
        };
    }

    // Bản sau: mỗi case chỉ quyết định nhóm domain cần xử lý.
    static String after(Event event) {
        return switch (event) {
            case Login login -> describeLogin(login);
            case Purchase purchase -> describePurchase(purchase);
            case Heartbeat heartbeat -> "PING";
            case null -> "MISSING";
        };
    }

    static String describeLogin(Login login) {
        String user = login.user();
        if (login.success() && user != null && !user.isBlank()) {
            return "LOGIN_OK:" + user;
        }
        return "LOGIN_REVIEW";
    }

    static String describePurchase(Purchase purchase) {
        Money money = purchase.money();
        if (money == null) {
            return "PURCHASE_REVIEW";
        }

        int cents = money.cents();
        String buyer = purchase.buyer();

        if (cents >= 10_000 && buyer != null && !buyer.isBlank()) {
            return "PURCHASE_LARGE:" + buyer;
        }
        if (cents > 0) {
            return "PURCHASE:"
                    + (buyer == null ? "unknown" : buyer);
        }
        return "PURCHASE_REVIEW";
    }

    static void check(String name, Event event) {
        String oldValue = before(event);
        String newValue = after(event);

        if (!oldValue.equals(newValue)) {
            throw new AssertionError(
                    name + " mismatch: " + oldValue + " vs " + newValue);
        }
        System.out.println(name + " => " + newValue);
    }

    public static void main(String[] args) {
        check("login-ok", new Login("Ada", true));
        check("login-blank", new Login(" ", true));
        check("login-null-user", new Login(null, true));
        check("login-failed", new Login("Ada", false));
        check("large", new Purchase("Mai", new Money(10_000)));
        check("small", new Purchase("Mai", new Money(500)));
        check("buyer-null", new Purchase(null, new Money(50)));
        check("zero", new Purchase("Mai", new Money(0)));
        check("money-null", new Purchase("Mai", null));
        check("heartbeat", new Heartbeat(123L));
        check("selector-null", null);
    }
}
```

Biên dịch/chạy bằng JDK 21 trở lên:

```bash
javac --release 21 PatternReadabilityReviewDemo.java
java PatternReadabilityReviewDemo
```

Stdout:

```text
login-ok => LOGIN_OK:Ada
login-blank => LOGIN_REVIEW
login-null-user => LOGIN_REVIEW
login-failed => LOGIN_REVIEW
large => PURCHASE_LARGE:Mai
small => PURCHASE:Mai
buyer-null => PURCHASE:unknown
zero => PURCHASE_REVIEW
money-null => PURCHASE_REVIEW
heartbeat => PING
selector-null => MISSING
```

### 4.2. Những quyết định review có thể rút ra

1. **Ý định rõ hơn:** `after` trả lời “event thuộc nhóm nào?”, còn `describePurchase` trả lời “purchase hợp lệ theo mức nào?”.
2. **Giảm tải nhận thức:** trước kia người đọc phải theo dõi hai guard Purchase và nhánh Purchase dự phòng ở giữa các loại event khác; giờ chính sách Purchase được đọc liền mạch trong một helper.
3. **Không che quy tắc null:** selector null được xử lý ở `case null`; component `Money money` null được xử lý trong `describePurchase`.
4. **Giữ thứ tự ưu tiên:** mức `>= 10_000` vẫn được xét trước mức `> 0`; test `large` dùng đúng ranh giới 10.000.
5. **Giữ tính exhaustive:** `Event` là sealed interface cho phép đúng ba subtype record. `after` bao phủ ba kiểu và `null`, không thêm `default` để giấu biến thể mới.
6. **Giữ khả năng kiểm thử:** chương trình đối chiếu `before`/`after` trên 11 đầu vào và ném `AssertionError` nếu đầu ra khác nhau.

**Lưu ý quan trọng:** Việc 11 test đều qua **không chứng minh tương đương cho mọi dữ liệu**; trong ứng dụng thật cần bổ sung input biên, exception và side effect theo hợp đồng nghiệp vụ. Nếu các accessor hoặc helper gây side effect, chỉ so sánh chuỗi trả về có thể chưa đủ.

Bản `before` không “sai” về ngôn ngữ. Trong một đoạn code rất ngắn hoặc khi các nhánh phản ánh trực tiếp một bảng phân loại, giữ `switch` tại chỗ có thể tốt hơn. Bản `after` hữu ích ở đây vì các chính sách Login/Purchase có tên, phạm vi và điểm kiểm thử rõ.

## 5. Review thứ tự nhánh và khả năng bao phủ

### 5.1. Pattern cụ thể trước pattern tổng quát

Ví dụ đúng khi phân biệt subtype:

```java
class Document {}
class ConfidentialDocument extends Document {}

// Một phần switch trên selector Object:
case ConfidentialDocument secret -> "restricted";
case Document ordinary -> "regular";
```

Nếu `case Document` đứng trước, nó bao phủ cả `ConfidentialDocument`; compiler có thể báo nhãn sau bị **dominated**. Nhưng reviewer vẫn phải hiểu nghiệp vụ: không thể “sửa” bằng cách xóa nhánh Confidential nếu có quy tắc bảo mật khác biệt.

Với guard:

```java
case Purchase(var buyer, Money(int cents))
        when cents >= 10_000 -> "large";
case Purchase(var buyer, Money(int cents))
        when cents > 0 -> "normal";
case Purchase(var buyer, var money) -> "review";
```

Nhánh không guard nên đặt sau hai nhánh phân loại. Khi guard trước không đúng, Java có thể xét nhánh tiếp theo; guard không có nghĩa là “bắt buộc phải chọn nhánh”.

### 5.2. Exhaustiveness của switch expression

Một `switch` expression cần trả về kết quả hoặc kết thúc bằng ngoại lệ trên mọi giá trị thích hợp. Với sealed hierarchy, compiler có thể dùng thông tin `permits` để kiểm tra tính bao phủ.

**Cảnh báo review:** Thêm `default -> "unknown"` vào mọi switch sealed có thể làm mất tín hiệu hữu ích khi thêm một subtype mới: compiler không còn buộc tác giả xét lại từng nơi phân loại. Nhưng `default` vẫn có chỗ hợp lệ nếu domain thật sự mở, cần nhận subtype không biết trước hoặc chủ ý đưa giá trị không hỗ trợ vào fallback.

Không nên dùng `case Event e -> ...` hoặc `default` quá sớm chỉ để làm compiler hết báo thiếu case mà chưa xác định hợp đồng.

### 5.3. Null selector không đồng nghĩa null component

- `case null` kiểm tra **toàn bộ selector** là null.
- `new Purchase("Mai", null)` là một đối tượng Purchase khác null nhưng component Money null. Pattern `Purchase(var buyer, Money(int cents))` **không khớp** record Money null; nhánh `Purchase(var buyer, var money)` rộng hơn có thể tiếp nhận.
- Trong `after`, case Purchase khớp đối tượng, rồi helper kiểm tra `money == null`.
- `default` của pattern switch không mặc nhiên xử lý selector null. Đừng coi nó giống hoàn toàn `else` của chuỗi `if (value instanceof ...)`.

Reviewer nên yêu cầu test riêng cho null ở từng tầng khi schema cho phép component nullable.

## 6. Review tính dễ đọc của record patterns

Record patterns có lợi vì thấy cấu trúc ngay tại nhánh:

```java
record Point(int x, int y) {}
record Line(Point start, Point end) {}

// Một case trong switch:
case Line(Point(int x1, int y1), Point(int x2, int y2))
        when x2 > x1 && y2 > y1 -> "increasing";
```

Nhưng khi có nhiều tầng record, nhiều tên biến ngắn như `a`, `b`, `c` và điều kiện kết hợp phức tạp, người đọc phải giữ quá nhiều ngữ cảnh.

Các câu hỏi review:

- Cấu trúc lồng có thật sự thể hiện **quy tắc chính**, hay chỉ là cách lấy hai field để gọi helper?
- Component nào có thể null? Pattern lồng tương ứng có thể bỏ qua giá trị không?
- Tên biến có gợi nghĩa không? `startX`/`endX` thường dễ hiểu hơn `x1`/`x2` ở domain có nhiều tọa độ.
- Accessor record có thuần túy, ổn định và không ném lỗi bất ngờ không?
- Nếu trích xuất sang helper, helper có tên nghiệp vụ thay vì `handle1` hay `foo` không?

Một cách khác là dùng pattern nông rồi tách:

```java
case Line(var start, var end) ->
        describeDirection(start, end);
```

`describeDirection` là phương thức minh họa phải được tự định nghĩa trong ứng dụng. Cách này dễ review hơn nếu logic xét hai điểm dài, nhưng không cần thiết với một nhánh đơn giản.

**Không đặt ngưỡng cứng “chỉ cho phép hai tầng nested pattern” như quy tắc của Java.** Có thể dùng guideline nội bộ và yêu cầu giải thích khi quá sâu, nhưng quyết định vẫn dựa vào sự rõ ràng của domain.

## 7. Review guard `when` và tính thuần túy

Guard nên diễn đạt **một điều kiện có ý nghĩa rõ ràng**:

```java
case Purchase(var buyer, Money(int cents))
        when cents >= 10_000 -> "large purchase";
```

Nếu guard dài, có thể đặt tên predicate:

```java
static boolean highValue(int cents) {
    return cents >= 10_000;
}

// Một nhánh minh họa:
case Purchase(var buyer, Money(int cents))
        when highValue(cents) -> "large purchase";
```

Nhưng một helper chỉ đổi tên vô nghĩa như `check(int x)` không giúp reviewer hiểu được quy tắc.

**Tránh side effects trong guard:** Một guard có thể chạy rồi trả `false`, sau đó Java tiếp tục tìm case khác. Tác động của guard như ghi database, gửi thông báo hoặc tăng bộ đếm **không được hoàn tác** chỉ vì nhánh đó không được chọn.

Ví dụ cần xem xét lại:

```java
// Minh họa: auditAndCheck là phương thức giả định có side effect.
// case Purchase p when auditAndCheck(p) -> processPurchase(p);
```

Nên tách **kiểm tra thuần túy** và **hành động xảy ra sau khi chọn nhánh**, hoặc tổ chức giao dịch nghiệp vụ minh bạch. Guard ném ngoại lệ sẽ truyền ngoại lệ ra ngoài, không được coi như `false`.

**Boolean short-circuit:** dùng `&&` để bảo vệ phép truy cập nullable:

```java
case Login(var user, boolean success)
        when success && user != null && !user.isBlank() ->
        "valid login";
```

Khi `user == null`, `isBlank()` không được gọi. Nếu dùng `||` hoặc đổi thứ tự điều kiện mà chưa hiểu, có thể gây `NullPointerException` hoặc thay đổi ý nghĩa.

## 8. Review flow scoping, tên biến và format

### 8.1. Flow scoping

Trong `if`:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text);
}
```

`text` dùng được ở vế phải `&&` và trong thân `if` vì compiler biết pattern đã khớp.

Sai:

```java
// KHÔNG BIÊN DỊCH:
// if (value instanceof String text || !text.isBlank()) {
//     System.out.println(text);
// }
```

Nếu vế trái `||` sai, vế phải có thể chạy mà `text` chưa được ràng buộc. Reviewer đừng đề nghị “gom điều kiện vào một dòng” nếu việc đó vô tình làm sai flow scoping.

Trong `switch`, biến pattern thuộc scope guard và thân nhánh tương ứng; không dùng tên ấy như thể có giá trị ở mọi nhánh.

### 8.2. Tên biến và thiết kế hiển thị

Ưu tiên tên phản ánh domain:

```java
// Khó đọc:
case Purchase(var x, Money(int n)) when n > 0 -> ...;

// Tự mô tả hơn:
case Purchase(var buyer, Money(int cents)) when cents > 0 -> ...;
```

Dấu `...` ở đây chỉ là chỗ lược bỏ thân nhánh để minh họa, **không phải mã độc lập có thể biên dịch**.

Giữ một quy ước format nhất quán: nhãn `case` dài được xuống dòng ở chỗ ngắt giữa pattern và guard; biểu thức phức tạp nên đặt trong block hoặc helper. Với review, ưu tiên diff cho thấy **quy tắc thay đổi** thay vì các dòng bị format lại không liên quan.

## 9. Review switch expression và switch statement

Dùng **switch expression** khi mục tiêu là trả về kết quả:

```java
String label = switch (value) {
    case String text -> "TEXT:" + text;
    case Integer n -> "INT:" + n;
    case null -> "NULL";
    default -> "OTHER";
};
```

Với nhánh nhiều câu lệnh, dùng `yield` để cung cấp giá trị:

```java
String label = switch (value) {
    case String text -> {
        String normalized = text.strip();
        yield normalized.isEmpty() ? "EMPTY" : normalized;
    }
    case null -> "NULL";
    default -> "OTHER";
};
```

Dùng **switch statement** khi mục tiêu là hành động, chẳng hạn gọi handler hoặc ghi log:

```java
switch (value) {
    case String text -> processText(text);
    case Integer n -> processNumber(n);
    case null -> handleNull();
    default -> handleUnknown(value);
}
```

Đoạn statement này là **minh họa**: `processText`, `processNumber`, `handleNull`, `handleUnknown` phải được định nghĩa khi dùng trong chương trình thật.

Reviewer nên hỏi: liệu expression đang che giấu nhiều side effect chỉ để trả về một giá trị giả tạo, hoặc statement đang bỏ qua một giá trị cần thiết? Hai dạng `->` đều không tự fall-through sang nhánh sau, nhưng chỉ switch expression bắt buộc tạo kết quả thích hợp trên các đường đi bình thường.

## 10. Review runtime safety và hành vi ngoại lệ

### 10.1. Record accessor và side effect

Record pattern trích xuất các component bằng accessor. Nếu một record định nghĩa accessor tùy biến có side effect, việc thử khớp pattern có thể tạo tác động **trước khi** guard hoặc thân case chạy.

```java
record Token(String text) {
    @Override
    public String text() {
        System.out.println("accessed");
        return text;
    }
}
```

Khi dùng `case Token(var body) -> ...`, accessor có thể được gọi để tạo binding `body`. Với nhiều pattern, đừng dựa vào số lần accessor được gọi. Reviewer nên ưu tiên accessor đơn giản, deterministic, và đặc biệt lưu ý nếu refactor thay đổi vị trí deconstruct.

### 10.2. Kiểu tĩnh selector và generic type erasure

Java 21 có thể dùng reference type làm selector của `switch`, nhưng không phải mọi pattern tùy ý đều áp dụng được:

```java
Number number = 5;

// KHÔNG BIÊN DỊCH: Number không thể khớp String.
// switch (number) {
//     case String s -> System.out.println(s);
//     default -> {}
// }
```

Với generics, đừng dùng pattern như `List<String>` để “chứng minh” element type từ `Object`. Thông tin type argument thường bị xóa ở runtime; một pattern `List<?>` chỉ xác nhận đối tượng là một `List`, không chứng minh các phần tử đều là `String`.

### 10.3. Không đổi exception và fallback tùy tiện

Đổi cast không điều kiện thành `instanceof` có fallback có thể thay `ClassCastException`/`NullPointerException` bằng chuỗi `"unknown"`. Đó là **thay đổi hành vi**, không phải refactor readability đơn thuần. Hãy xác định hợp đồng của caller, lỗi mong đợi và behavior của dữ liệu legacy trước khi khuyến nghị.

Nếu logic xử lý nhiều subtype qua interface mở, một `default` có thể là cần thiết. Nếu domain được sealed, đừng dùng `default` chỉ để che một case chưa được hiểu.

## 11. Cách viết nhận xét code review có ích

Thay vì nhận xét “nhiều pattern quá, tách ra” hoặc “pattern khó đọc”, hãy nêu **bối cảnh, rủi ro và đề xuất kiểm chứng**.

**Ví dụ 1 — Thứ tự nhánh:**

> Nhánh `case Text` bao phủ cả `UrgentText`, nhưng `UrgentText` có quy tắc ưu tiên riêng. Có thể đặt nhánh cụ thể trước và thêm test đầu vào `UrgentText` để ngăn regression không?

**Ví dụ 2 — Guard chứa side effect:**

> `auditAndCheck` có ghi dữ liệu ngay cả khi trả `false`. Nếu case này không được chọn, audit vẫn tồn tại. Có thể tách predicate kiểm tra ra khỏi hành động được thực hiện trong nhánh đã chọn không?

**Ví dụ 3 — Null ở record con:**

> `Purchase(var buyer, Money(int cents))` không khớp khi `money == null`. Domain có cho phép trường hợp này không? Nhánh fallback nào sẽ nhận nó và có test chưa?

**Ví dụ 4 — Sealed exhaustive switch:**

> `Event` là sealed và ta đã liệt kê đủ các biến thể hiện tại. `default` có cần cho contract không, hay nên bỏ để compiler nhắc cập nhật khi thêm một subtype?

**Ví dụ 5 — Mục đích method:**

> `switch` này vừa phân loại sự kiện vừa xử lý thanh toán. Có thể giữ switch điều phối theo event, chuyển quy tắc thanh toán sang `describePurchase`/`processPurchase` được đặt tên và test riêng không?

Một comment tốt giúp tác giả hiểu *vì sao* cần điều chỉnh, chứ không buộc mọi người tuân theo khẩu vị format cá nhân.

## 12. Checklist trước khi approve pattern matching

### A. Tính rõ ràng của ý định
- [ ] Method có một mục tiêu rõ ràng và tên phù hợp không?
- [ ] Nhìn từng `case` có hiểu được loại dữ liệu và hành động đang chọn không?
- [ ] Tên pattern variables có ý nghĩa domain, tránh `x`/`v`/`tmp` ở các nhánh phức tạp không?

### B. Thứ tự và tính đầy đủ
- [ ] Type subtype đã đứng trước kiểu cha khi có chính sách khác nhau chưa?
- [ ] Guard chồng lấn có ưu tiên rõ và test ranh giới chưa?
- [ ] Nhánh không guard/fallback có xử lý các giá trị còn lại mà không che mất lỗi không?
- [ ] Sealed switch có giữ kiểm tra exhaustive và không `default` vô cớ không?

### C. Cấu trúc và scope
- [ ] Nested record patterns có giúp đọc rõ hơn việc trích xuất vào helper không?
- [ ] Nullable component có được xử lý đúng tầng không?
- [ ] Biến pattern chỉ được dùng khi compiler đã ràng buộc chắc chắn; `&&`/`||` đúng ý định chưa?

### D. Runtime và kiểm thử
- [ ] Guard và accessor có side effect, I/O hoặc ngoại lệ bất ngờ không?
- [ ] `case null` đã khớp hợp đồng cũ chưa?
- [ ] Có test cho subtype, giá trị biên, null, unknown, exception và side effect quan trọng không?
- [ ] Refactor chỉ đổi cấu trúc hay còn đổi semantics? Nếu đổi behavior, đã được xác nhận chưa?
- [ ] Diff có dễ review, tránh trộn format với thay đổi domain quá lớn không?

### E. Quyết định cuối cùng

- **Giữ nguyên** khi một `switch` nhiều nhánh vẫn mô tả một bảng phân loại minh bạch và có test tốt.
- **Tách helper/predicate** khi mỗi nhóm có chính sách riêng, guard dài hoặc nested patterns làm reviewer phải giữ nhiều ngữ cảnh.
- **Cân nhắc đa hình** khi hành vi thực sự là trách nhiệm của các kiểu và các kiểu thuộc quyền sở hữu của module; tránh nhét nhiều logic không liên quan vào domain models.
- **Dừng refactor lớn** nếu chưa hiểu hierarchy, null contract, side effect hoặc hành vi fallback. Làm characterization tests trước khi thay đổi.

**Kết luận:** Review readability của pattern matching là review **cách trình bày quyết định**. Một đoạn `case` đẹp phải cho thấy **dữ liệu gì khớp, điều kiện nào quan trọng, nhánh nào ưu tiên và điều gì xảy ra khi không khớp**. Đừng lấy số dòng hoặc số pattern làm thước đo duy nhất; ưu tiên biểu đạt domain, logic có thể theo dõi và bộ test bảo vệ hành vi.

### Tài liệu tham khảo

- OpenJDK JEP 394 — Pattern Matching for instanceof: https://openjdk.org/jeps/394
- OpenJDK JEP 440 — Record Patterns (Java 21): https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch (Java 21): https://openjdk.org/jeps/441
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
