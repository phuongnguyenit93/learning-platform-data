# Java 21 và pattern matching đã hoàn thiện

## 1. “Đã hoàn thiện” nghĩa là gì?

**Java 21 là cột mốc lớn của pattern matching trong Java:** hai tính năng được đưa ra khỏi trạng thái *preview* và trở thành tính năng chính thức là **record patterns (JEP 440)** và **pattern matching for `switch` (JEP 441)**. Cùng với **pattern matching for `instanceof`** đã chính thức từ Java 16, **records** chính thức từ Java 16 và **sealed classes/interfaces** chính thức từ Java 17, Java 21 cho phép mô hình hóa dữ liệu và phân loại nhiều dạng đối tượng bằng cú pháp nhất quán.

Ví dụ ý tưởng:

```java
sealed interface Request permits Parcel, Cancellation {}
record Parcel(String code, int weight) implements Request {}
record Cancellation(String reason) implements Request {}
```

Từ Java 21, có thể dùng pattern trong `switch`:

```java
static String label(Request request) {
    return switch (request) {
        case Parcel(String code, int weight) when weight >= 10 ->
                "Hàng nặng: " + code;
        case Parcel(String code, int weight) ->
                "Hàng thường: " + code;
        case Cancellation(String reason) ->
                "Hủy: " + reason;
        case Cancellation ignored ->
                "Hủy thiếu lý do";
        case null -> "Chưa có yêu cầu";
    };
}
```

Các đoạn trên là **minh họa khai báo**, có thể đặt trong cùng một ngữ cảnh kiểu; phần 9 cung cấp chương trình đầy đủ. Chú ý rằng `Cancellation(String reason)` không khớp khi component `reason` là `null`, nên case `Cancellation ignored` phía sau có vai trò dự phòng.

Khi nói **“pattern matching đã hoàn thiện trong Java 21”**, cần hiểu chính xác:

- Những tính năng cụ thể **record patterns** và **pattern matching for `switch`** đã được chuẩn hóa, có thể dùng trong mã production với JDK 21 mà **không cần `--enable-preview`**.
- Điều đó **không có nghĩa mọi ý tưởng pattern matching trong tương lai đều đã có ở Java 21**. Ví dụ, **unnamed patterns and variables** dùng dấu `_` chỉ là *preview* trong Java 21 (JEP 443), không phải một phần của cú pháp chính thức mặc định.
- “Chính thức” cũng không bảo đảm mã luôn đúng nghiệp vụ, luôn không có `null` hay tự động nhanh hơn cách viết cũ. Compiler kiểm tra các quy tắc kiểu và luồng; logic nghiệp vụ vẫn cần thiết kế và test.

## 2. Dòng thời gian tương thích

| Phiên bản Java | Mốc quan trọng | Ý nghĩa đối với người lập trình |
| --- | --- | --- |
| Java 14–15 | Pattern matching for `instanceof` ở trạng thái preview | Có thể thử nghiệm khi bật preview, không nên nhầm với cú pháp chính thức ở các phiên bản ấy. |
| **Java 16** | `instanceof` type patterns chính thức (JEP 394); records chính thức (JEP 395) | Viết `obj instanceof String text` và định nghĩa `record` không cần preview. |
| **Java 17** | Sealed classes/interfaces chính thức (JEP 409); pattern matching for `switch` bắt đầu preview (JEP 406) | Có thể mô hình hóa hệ phân cấp đóng; chưa được coi `switch` pattern matching là tính năng chính thức. |
| Java 19–20 | Record patterns được thử nghiệm qua preview (JEP 405, JEP 432); pattern matching for `switch` tiếp tục preview | Cú pháp và một số quy tắc còn được hoàn thiện trước phiên bản chính thức. |
| **Java 21** | **Record patterns (JEP 440) và pattern matching for `switch` (JEP 441) chính thức** | Dùng type/record patterns trong `switch`, guard `when` và deconstruction lồng nhau theo cú pháp chuẩn, không cần preview. |
| Java 21 | Unnamed patterns and variables vẫn ở dạng preview (JEP 443) | Không viết `_` như unnamed pattern khi yêu cầu chỉ dùng tính năng Java 21 chính thức. |

**Lưu ý quan trọng:** `record`, `sealed` và type pattern trong `instanceof` không đồng nghĩa với “record pattern” trong `switch`. Chúng là các bước phát triển khác nhau; khi kiểm tra tương thích, phải xét **từng cấu trúc cú pháp thực sự dùng**, không chỉ xem dự án có record hay không.

Ví dụ:

```java
// Java 16+:
if (obj instanceof String text) {
    System.out.println(text.length());
}

// Java 21+ (chính thức):
if (obj instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
```

Đoạn thứ hai yêu cầu `Point` là record có hai component `int`. Java 17 không hiểu record pattern `Point(int x, int y)` theo phiên bản ngôn ngữ chính thức của nó, dù Java 17 đã hỗ trợ khai báo record.

## 3. Type pattern trong instanceof: nền tảng đã ổn định

Trước khi pattern matching for `instanceof` trở thành tính năng chính thức:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.toUpperCase());
}
```

Sau khi dùng type pattern:

```java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Cách viết mới kết hợp phép thử kiểu và ràng buộc biến có kiểu `String`. Khi `value` không phải `String` hoặc bằng `null`, pattern không khớp và thân `if` không chạy.

**Compiler quản lý phạm vi theo luồng (flow scoping):**

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.length());
}
```

Vế phải `&&` chỉ được đánh giá khi vế trái đúng, nên `text` chắc chắn đã được ràng buộc. Trái lại:

```java
// KHÔNG BIÊN DỊCH: vế phải của || chạy khi pattern bên trái sai.
// if (value instanceof String text || text.isBlank()) {
//     System.out.println(text);
// }
```

Trong một **guard clause** có nhánh không khớp thoát sớm, biến pattern có thể dùng ở phần tiếp theo:

```java
static String requireString(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Cần String");
    }
    return text;
}
```

Không được dùng biến pattern ở nhánh `else` của phép thử dương, ở các đường đi mà pattern có thể sai, hoặc ngoài phạm vi compiler đã chứng minh là khớp. Đây là cơ chế quan trọng vẫn giữ nguyên khi đưa pattern vào `switch` và record patterns.

## 4. Record patterns: phân rã dữ liệu có kiểm tra kiểu

Một record khai báo cấu trúc component:

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}
```

Trong Java 21, có thể dùng record pattern trực tiếp:

```java
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
```

Và dùng **nested record pattern**:

```java
if (value instanceof Segment(
        Point(int x1, int y1),
        Point(int x2, int y2))) {
    System.out.println(x2 - x1);
}
```

Về nguyên tắc, compiler đối chiếu pattern với cấu trúc record: số component và kiểu pattern ở từng vị trí phải phù hợp. Các biến `x1`, `y1`, `x2`, `y2` chỉ được dùng ở nơi mẫu lồng nhau đã khớp.

Có thể dùng `var` để **suy luận kiểu component**:

```java
if (value instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

Ở đây `x` và `y` có kiểu `int` theo khai báo record, không phải `Object` không xác định.

### Record pattern và null

Cần tách ba trường hợp:

1. **Selector là `null`:** không khớp một record pattern như `Point(int x, int y)`.
2. **Record lồng là `null`:** `Segment(Point(...), Point(...))` không khớp khi `start` hoặc `end` bằng `null`.
3. **Component được ràng buộc bằng `var` là null:** với component tham chiếu, `var` có thể nhận `null`; phải tự kiểm tra trước khi gọi phương thức trên biến.

Ví dụ:

```java
record Note(String message) {}

static String noteText(Object input) {
    if (input instanceof Note(var message)
            && message != null
            && !message.isBlank()) {
        return message;
    }
    return "Thiếu thông điệp";
}
```

Dùng `var message` giúp case khi component null được xử lý bằng một điều kiện tường minh. Nếu dùng `Note(String message)`, type pattern con `String message` không khớp với component null; không nên nhầm hai hành vi.

### Record pattern không tự tạo dữ liệu

Record pattern **đọc component thông qua accessor của record** để khớp mẫu, không tạo record mới và không thực hiện constructor validation thay cho ứng dụng. Accessor tùy chỉnh có thể tốn chi phí hoặc ném exception; nếu accessor ném exception trong quá trình khớp record pattern, cần hiểu cơ chế `MatchException` của Java 21. Đừng dựa vào cú pháp ngắn hơn để suy ra rằng pattern không có chi phí hoặc không thể phát sinh lỗi.

## 5. Pattern matching for switch: case, when và kết quả

Java 21 cho phép dùng **type pattern** và **record pattern** trong `case`:

```java
static String classify(Object input) {
    return switch (input) {
        case Integer number when number > 0 ->
                "Số dương: " + number;
        case Integer number ->
                "Số nguyên không dương: " + number;
        case String text when !text.isBlank() ->
                "Chuỗi: " + text;
        case String ignored ->
                "Chuỗi trống";
        case null ->
                "Không có dữ liệu";
        default ->
                "Loại khác";
    };
}
```

Đây là phương thức Java 21 hoàn chỉnh nếu đặt trong lớp. Điểm cần nhớ:

- `switch` kiểm tra các nhánh theo **thứ tự**; nhánh đầu tiên phù hợp cả pattern và guard được chọn.
- Guard `when` được đánh giá **sau khi pattern khớp**; vì vậy `number` hoặc `text` đã có kiểu rõ ràng trong guard.
- Nếu guard trả `false`, Java tiếp tục xét các nhánh sau.
- Nhánh không guard như `case Integer number` phải **đặt sau** nhánh cùng kiểu có guard, nếu không có thể làm nhánh sau bị **dominated**.
- `->` là cú pháp switch rule, không có cơ chế fall-through như dạng nhóm nhãn colon cũ.
- `return switch (...) { ... };` là **switch expression** và phải cho ra một giá trị hoặc kết thúc bằng `throw` cho mỗi đường đi.

### Dùng block và yield khi cần nhiều lệnh

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> {
            String normalized = text.strip();
            yield normalized.isEmpty()
                    ? "Chuỗi rỗng"
                    : "Nội dung: " + normalized;
        }
        case null -> "Không có chuỗi";
        default -> "Không phải chuỗi";
    };
}
```

Trong `switch expression`, block case cần `yield` để cấp giá trị cho biểu thức. Đừng nhầm `yield` với `break` hoặc `return`; mỗi từ khóa có quy tắc điều khiển riêng.

### Guard khi pattern không khớp

Nếu selector là `Double` và case đang thử `case Integer number when number > 0`, pattern `Integer` không khớp nên guard `number > 0` không được đánh giá. Nếu selector là `Integer(-2)`, pattern khớp nhưng guard sai, nên case `Integer` không guard phía sau được chọn.

Sự khác nhau giữa **pattern không khớp** và **guard sai** rất quan trọng trong unit test, vì cả hai đều làm một case bị bỏ qua nhưng có thể dẫn đến các nhánh khác nhau.

## 6. Sealed interface và exhaustiveness: lợi ích của kiểu đóng

`sealed interface` giúp compiler biết những subtype **trực tiếp được phép**:

```java
sealed interface Outcome permits Accepted, Refused, Waiting {}
record Accepted(String id) implements Outcome {}
record Refused(String reason) implements Outcome {}
record Waiting(int seconds) implements Outcome {}
```

Trong Java 21:

```java
static String status(Outcome outcome) {
    return switch (outcome) {
        case Accepted(String id) -> "Đã nhận: " + id;
        case Refused(String reason) -> "Từ chối: " + reason;
        case Refused refused -> "Từ chối không có lý do";
        case Waiting(int seconds) -> "Chờ: " + seconds;
        case null -> "Chưa có trạng thái";
    };
}
```

`switch expression` có thể được compiler xác nhận **exhaustive**: mọi đối tượng `Outcome` không null phải thuộc một subtype được phép là `Accepted`, `Refused` hoặc `Waiting` (các record đều là final), và `case null` xử lý riêng selector null. **Không cần `default`**.

Nếu thêm một subtype mới, ví dụ `TimedOut`, vào danh sách `permits`, những `switch` dựa vào tập kiểu cũ có thể cần bổ sung case khi biên dịch lại. Đây là ưu thế để phát hiện những chính sách xử lý chưa cập nhật.

**Tuy nhiên, cần chú ý một chi tiết:** `Accepted(String id)` không khớp nếu `id == null`, còn code phía trên **không có case `Accepted accepted` dự phòng**. Như vậy, đoạn `status` minh họa chưa đầy đủ đối với `Accepted` có component `null`. Để chính xác và exhaustive, nên sử dụng một trong hai cách:

```java
// Cách 1: var cho component có thể null.
case Accepted(var id) -> "Đã nhận: " + id;

// Cách 2: thêm case bao quát subtype sau pattern cụ thể.
case Accepted(String id) -> "Đã nhận: " + id;
case Accepted accepted -> "Đã nhận nhưng thiếu id";
```

Các đoạn trên là những **nhánh minh họa để sửa**, không phải chương trình đặt nguyên cả hai lựa chọn vào cùng một `switch`. Trường hợp `Refused` đã có nhánh `Refused refused` dự phòng. Khi viết `switch` trên sealed hierarchy, tính đầy đủ là vấn đề dựa trên kiểu và những quy tắc của Java; nếu component type pattern có thể không khớp do null, hãy bảo đảm xử lý được dữ liệu đó theo hợp đồng nghiệp vụ.

**Lưu ý kỹ thuật:** Đối với Java 21, việc compiler công nhận một record pattern là bao phủ type record có các quy tắc riêng về tính *unconditional* của pattern; không nên coi việc có record pattern chứa type pattern tham chiếu là phép chứng minh tự động rằng các component không bao giờ null. Khi cần biểu thị rõ chính sách null trong domain, dùng `var`, nhánh type pattern rộng hơn hoặc validation ở constructor.

### Đừng che dấu thiếu case bằng default

Với một domain đóng, đoạn:

```java
// Kém an toàn về việc phát hiện subtype mới:
return switch (outcome) {
    case Accepted accepted -> "OK";
    default -> "OTHER";
};
```

dễ che mất việc `Refused` và `Waiting` cần quy tắc riêng. `default` có thể hợp lý với đầu vào mở như `Object` hoặc một interface cho plugin, nhưng trong domain đóng nó làm yếu đi một lợi ích của exhaustiveness.

**Không đồng nhất null với default:** với pattern matching for `switch`, `null` có quy tắc riêng; nếu muốn xử lý selector null, hãy dùng `case null` hoặc kiểm tra trước. Không nên trông đợi `default` tự biến null thành một kết quả thông thường.

## 7. Khác biệt giữa Java 17 và Java 21 trong một dự án

Nếu dự án đang chạy trên JDK 17 và chỉ dùng tính năng chính thức, những cấu trúc sau có thể được sử dụng:

```java
record Request(String id) {}
sealed interface Response permits Success, Failure {}
record Success(String value) implements Response {}
record Failure(String error) implements Response {}

static String requestId(Object value) {
    if (value instanceof Request request) {
        return request.id();
    }
    return "Không phải Request";
}
```

Đây là ví dụ mã nguồn minh họa dùng **records + sealed types + type pattern `instanceof`**. Không cần `switch` pattern matching.

Nếu chuyển dự án sang Java 21, có thể đưa những thao tác phân loại type rõ ràng sang `switch`, giảm chuỗi `if/else if` và tận dụng kiểm tra tính đầy đủ khi subtype đóng:

```java
static String responseText(Response response) {
    return switch (response) {
        case Success(String value) ->
                "Thành công: " + value;
        case Success success ->
                "Thành công thiếu giá trị";
        case Failure(String error) ->
                "Thất bại: " + error;
        case Failure failure ->
                "Thất bại thiếu lý do";
        case null ->
                "Không có kết quả";
    };
}
```

Khi dùng trong JDK 17, ví dụ `responseText` Java 21 ở trên sẽ **không biên dịch theo ngôn ngữ Java 17 chính thức**. Không thể chỉ đổi runtime lên 21 mà vẫn cấu hình compiler ở `--release 17` rồi mong record patterns và `when` được chấp nhận.

**Chỉ nâng lên Java 21 khi phù hợp hệ thống:** kiểm tra toolchain, CI, môi trường production, framework, thư viện, build plugins, IDE, phân phối JVM và chính sách nâng cấp. Những tính năng pattern đã chính thức không bắt buộc mọi ứng dụng Java 17 phải viết lại ngay; refactor cần chứng minh code rõ hơn và test hành vi được bảo toàn.

## 8. Cú pháp sai thường gặp khi di chuyển từ preview sang Java 21

### 8.1. Guard `&&` trong nhãn case kiểu cũ

Một số tài liệu preview cũ từng sử dụng kiểu viết guarded pattern khác với cú pháp hoàn thiện. Trong Java 21, viết guard bằng **`when`**:

```java
// Java 21:
case String text when !text.isBlank() -> "Có chữ";

// Cú pháp preview cũ, không dùng như case Java 21 chính thức:
// case String text && !text.isBlank() -> "Có chữ";
```

Mã trong fence là minh họa các nhãn case; không phải một phương thức Java độc lập. Với `instanceof`, `&&` **vẫn hoàn toàn hợp lệ** để nối điều kiện:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text);
}
```

Vì vậy, đừng sửa nhầm tất cả `&&` thành `when`: `when` là cú pháp guard trong `case` của `switch`, còn `&&` là toán tử boolean.

### 8.2. Trộn record pattern với constructor

`case Parcel(String code, Address(String city), int weight)` **không tạo một `Parcel` mới**. Đó là pattern kiểm tra một đối tượng `Parcel` đã có và lấy dữ liệu component qua accessor. Constructor `new Parcel(...)` là việc tạo dữ liệu; record pattern là việc so khớp/phân rã dữ liệu.

### 8.3. Đặt case tổng quát trước case cụ thể

```java
// KHÔNG BIÊN DỊCH: case String bị case Object phía trước bao phủ.
// return switch (value) {
//     case Object anything -> "Một object";
//     case String text -> "Chuỗi: " + text;
//     case null -> "null";
// };
```

`case Object anything` là pattern tổng quát cho các đối tượng không null, nên `case String text` phía sau bị dominated. Hãy đặt nhánh cụ thể/guard trước nhánh rộng hơn.

### 8.4. Không tính đến component null

`record Note(String content)` vẫn có thể được tạo với `content == null` nếu constructor không cấm. `Note(String text)` có type pattern con `String`, không khớp khi content null. `Note(var text)` có thể ràng buộc content null. Khi cần dùng `text.length()`, kiểm tra `text != null` trước.

### 8.5. Tưởng `_` luôn dùng được như unnamed pattern

Trong Java 21, khả năng dùng `_` làm unnamed variable/pattern thuộc **preview JEP 443**. Nếu code production yêu cầu chỉ dùng tính năng chính thức, sử dụng tên biến có nghĩa (ví dụ `ignored`) hoặc cách tổ chức khác thay vì cho rằng `case Parcel(_, _, _)` là cú pháp Java 21 mặc định.

### 8.6. Bỏ test vì compiler đã kiểm tra exhaustive

Compiler kiểm tra kiểu, dominance và exhaustiveness theo ngôn ngữ; nó không biết các ràng buộc như “khối lượng phải dương”, “mã không được trống” hay “thành phố phải được hỗ trợ”. Phải test các guard đúng/sai, nhánh fallback, null, dữ liệu biên và kiểu mới nếu domain thay đổi.

## 9. Chương trình Java 21 chạy hoàn chỉnh

Tạo tệp **`Java21PatternMatchingFinalDemo.java`**:

```java
import java.util.Locale;

public class Java21PatternMatchingFinalDemo {
    sealed interface Request permits Parcel, Cancellation, Delay {}

    record Address(String city) {}

    record Parcel(String code, Address destination, int weight)
            implements Request {}

    record Cancellation(String reason) implements Request {}

    record Delay(int minutes) implements Request {}

    static String inspect(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return text.strip().toUpperCase(Locale.ROOT);
        }
        return "Không phải chuỗi có nội dung";
    }

    static String describe(Request request) {
        return switch (request) {
            case Parcel(String code, Address(String city), int weight)
                    when weight >= 10 && "Hà Nội".equals(city) ->
                    "Hàng nặng " + code + " đến " + city;

            case Parcel(String code, Address(String city), int weight) ->
                    "Gửi " + code + " đến " + city;

            case Parcel ignored ->
                    "Thiếu cấu trúc địa chỉ";

            case Cancellation(String reason)
                    when !reason.isBlank() ->
                    "Đã hủy: " + reason;

            case Cancellation ignored ->
                    "Hủy thiếu lý do";

            case Delay(int minutes) when minutes > 0 ->
                    "Hoãn " + minutes + " phút";

            case Delay ignored ->
                    "Thời gian hoãn không hợp lệ";

            case null ->
                    "Không có yêu cầu";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspect("  java  "));
        System.out.println(inspect(42));

        System.out.println(describe(
                new Parcel("P1", new Address("Hà Nội"), 12)));
        System.out.println(describe(
                new Parcel("P2", new Address("Đà Nẵng"), 5)));
        System.out.println(describe(
                new Parcel("P3", null, 2)));
        System.out.println(describe(
                new Parcel("P4", new Address(null), 2)));

        System.out.println(describe(new Cancellation("Hết hàng")));
        System.out.println(describe(new Cancellation(null)));
        System.out.println(describe(new Delay(3)));
        System.out.println(describe(new Delay(0)));
        System.out.println(describe(null));
    }
}
```

Biên dịch bằng **JDK 21 hoặc mới hơn** và chạy:

```bash
javac -encoding UTF-8 Java21PatternMatchingFinalDemo.java
java Java21PatternMatchingFinalDemo
```

Đầu ra mong đợi:

```text
JAVA
Không phải chuỗi có nội dung
Hàng nặng P1 đến Hà Nội
Gửi P2 đến Đà Nẵng
Thiếu cấu trúc địa chỉ
Thiếu cấu trúc địa chỉ
Đã hủy: Hết hàng
Hủy thiếu lý do
Hoãn 3 phút
Thời gian hoãn không hợp lệ
Không có yêu cầu
```

### Giải thích kết quả

1. `inspect("  java  ")` khớp type pattern `String text`, vượt qua `!text.isBlank()`, rồi loại khoảng trắng bằng `strip()` và chuyển thành `JAVA`.
2. `inspect(42)` nhận `Integer`, không khớp `String` nên trả về kết quả dự phòng.
3. `Parcel("P1", Address("Hà Nội"), 12)` khớp nested record pattern, guard `weight >= 10` và thành phố `Hà Nội` đều đúng nên chọn nhánh hàng nặng.
4. `Parcel("P2", Address("Đà Nẵng"), 5)` khớp record pattern nhưng guard đầu sai; nhánh `Parcel(...)` kế tiếp trả `Gửi P2 đến Đà Nẵng`.
5. `Parcel("P3", null, 2)` không khớp nested `Address(String city)` vì `destination == null`, nên chọn `case Parcel ignored`.
6. `Parcel("P4", Address(null), 2)` có `Address` nhưng component `city == null` khiến type pattern `String city` không khớp; cũng chọn `case Parcel ignored`.
7. `Cancellation("Hết hàng")` khớp pattern và `!reason.isBlank()`; `Cancellation(null)` không khớp type pattern `String reason`, nên đi đến case `Cancellation ignored`.
8. `Delay(3)` thỏa guard `minutes > 0`; `Delay(0)` trượt guard và đi đến case `Delay ignored`.
9. `null` được xử lý riêng bởi `case null`.

Trong ví dụ, các subtype `Parcel`, `Cancellation` và `Delay` là record final được permitted trực tiếp, nên các case không guard tương ứng làm `switch expression` có thể xử lý mọi giá trị `Request` không-null. Không cần `default`.

### Kiểm tra phiên bản thực tế

Trong terminal, có thể xem JDK đang dùng:

```bash
java -version
javac -version
```

Nếu `javac` ở phiên bản 17, chương trình dùng record patterns và switch patterns Java 21 này không thể biên dịch bằng cú pháp chính thức của Java 17. Với JDK 21, có thể kiểm tra mức ngôn ngữ mục tiêu:

```bash
javac --release 21 -encoding UTF-8 Java21PatternMatchingFinalDemo.java
```

Tham số `--release 21` yêu cầu công cụ biên dịch hỗ trợ release 21; nó **không** biến một `javac` phiên bản cũ thành compiler Java 21. Ngoài ra, artifact được biên dịch cho Java 21 không thể mặc nhiên chạy trên runtime Java 17.

## 10. Type inference, generics và những giới hạn cần biết

Record patterns không chỉ dành cho record không generic. Java 21 có khả năng **suy luận type arguments của generic record pattern** từ ngữ cảnh kiểu tĩnh khi đủ thông tin:

```java
record Box<T>(T item) {}

static void printBox(Box<String> box) {
    if (box instanceof Box(var item)) {
        System.out.println(item.toUpperCase());
    }
}
```

Đây là đoạn minh họa đặt trong lớp có record `Box`. Compiler suy luận kiểu của `item` theo component của `Box<String>`. Không nên hiểu `var` là mất kiểm tra kiểu.

Tuy nhiên, **type erasure vẫn tồn tại**: kiểm tra một đối tượng runtime không chứng minh một đối số generic tùy ý như `T == String` chỉ bằng phép thử kiểu bị xóa. Khi đầu vào có kiểu `Object`, có thể kiểm tra component thực tế bằng pattern con:

```java
static String readStringBox(Object input) {
    if (input instanceof Box(var item)
            && item instanceof String text) {
        return text;
    }
    return "Không phải Box chứa String";
}
```

Mẫu này kiểm tra giá trị component thật là `String` trước khi sử dụng. Khi làm việc với generic, cần xem xét cả compile-time type, runtime type, unchecked casts, `null` và cấu trúc record. Pattern matching không loại bỏ các giới hạn của generics trong JVM.

## 11. Khi nâng cấp từ Java 17 hoặc các phiên bản preview

Một kế hoạch nâng cấp có kiểm soát:

1. **Xác nhận JDK/`javac` và mức `--release`/`sourceCompatibility`:** chạy runtime Java 21 không đồng nghĩa tất cả module đang biên dịch với source 21.
2. **Xác định cú pháp preview cũ:** chuyển những case guard dạng cũ sang `when` theo Java 21, rà lại các quy tắc dominance, null và exhaustiveness; không copy nguyên preview code mà không biên dịch lại.
3. **Giữ các hợp đồng dữ liệu đã có:** thêm record pattern không tự hợp thức hóa giá trị null hoặc negative; tiếp tục validation ở constructor/boundary.
4. **Tập trung vào những nơi phân loại subtype lặp lại:** dùng `switch` trên sealed hierarchy khi giúp code rõ nhánh, nhưng không thay mọi polymorphic method bằng `switch`.
5. **Kiểm tra hành vi exception:** refactor từ accessor thủ công sang record pattern có thể tác động việc bọc exception; test những accessor tùy chỉnh nếu có.
6. **Kiểm thử giá trị biên và case fallback:** `when` true/false, selector null, nested component null, subtype mới và thứ tự case.
7. **Biên dịch và chạy trong CI trên toolchain được chốt:** kiểm tra IDE, formatter, linter, test runner, plugin, container image và môi trường triển khai.
8. **Không bật preview vô tình:** bài học này dùng các tính năng chính thức Java 21; `--enable-preview` chỉ nên bật khi dự án cố ý dùng một JEP preview và chấp nhận chính sách tương thích của nó.

Không nhất thiết phải đổi ngay mọi đoạn `if (x instanceof T) { ... }` sang `switch`. Với chỉ một hoặc hai nhánh đơn giản, `if` có thể dễ hiểu hơn. Lợi ích rõ của `switch` thể hiện ở **tập subtype đóng**, **nhiều nhánh xử lý** hoặc **nhu cầu compiler kiểm tra tính đầy đủ**.

## 12. Các lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai hoặc dễ gây hiểu nhầm | Hướng sửa |
| --- | --- | --- |
| Dùng record patterns trong code target Java 17 | Tính năng này chính thức ở Java 21. | Nâng source/target/toolchain phù hợp hoặc dùng type patterns Java 17. |
| Dùng `case Type t && condition` từ tài liệu preview cũ | Cú pháp guard Java 21 dùng `when`. | Chuyển sang `case Type t when condition -> ...`. |
| Dùng biến pattern ở ngoài flow scope | Compiler không chứng minh mẫu đã khớp. | Dùng trong nhánh đúng, sau `&&` phù hợp hoặc guard clause thoát sớm. |
| Dùng `case Object obj` trước `case String s` | Nhánh sau bị dominated. | Đặt case cụ thể trước. |
| Tưởng `default` luôn xử lý selector null | Pattern switch có xử lý null riêng. | Dùng `case null`/kiểm tra null rõ ràng. |
| Giả định nested record pattern chấp nhận mọi component null | Type patterns con có thể không khớp null. | Dùng `var` và validation hoặc case subtype dự phòng. |
| Dùng `when` chỉ cho giá trị dương mà không có case còn lại | Guard sai làm loại đó chưa được xử lý. | Thêm case cùng subtype không guard hoặc nhánh bao quát. |
| Thêm `default -> "OK"` cho sealed hierarchy | Có thể che thiếu nhánh khi domain có loại mới. | Liệt kê biến thể và để compiler kiểm tra exhaustiveness. |
| Dùng `_` như cú pháp Java 21 chính thức | Unnamed patterns/variables chỉ preview ở Java 21. | Dùng biến có tên trong code không bật preview. |
| Nghĩ pattern matching tự động nhanh hơn mọi cách gọi | Còn type check, accessor, guard và tối ưu JVM. | Đo hiệu năng thực tế, tối ưu khi có bottleneck. |

## 13. Tự kiểm tra

Cho:

```java
sealed interface Message permits Text, NumberMessage {}
record Text(String value) implements Message {}
record NumberMessage(int value) implements Message {}
```

**Câu 1:** Tại sao cách viết sau cần Java 21 mới là cú pháp chính thức?

```java
return switch (message) {
    case Text(String value) -> "Text: " + value;
    case Text text -> "Text thiếu dữ liệu";
    case NumberMessage(int value) -> "Number: " + value;
    case null -> "Không có message";
};
```

**Đáp án:** Vì nó sử dụng **record patterns trong `case` của pattern-matching `switch`**, hai tính năng trở thành chính thức ở Java 21. Các `record`, `sealed` đơn thuần có thể khai báo từ phiên bản Java cũ hơn.

**Câu 2:** Nếu `new Text(null)` được đưa vào `switch`, nhánh nào phù hợp?

**Đáp án:** `case Text(String value)` không khớp vì pattern con `String` không khớp null; nhánh `case Text text` phía sau xử lý. Bỏ nhánh này mà không có chính sách null khác dễ khiến dữ liệu thiếu component không được xử lý theo ý định.

**Câu 3:** Nếu thêm một subtype `Image` vào `permits Message` mà không cập nhật `switch`, chuyện gì cần kiểm tra?

**Đáp án:** Khi biên dịch lại, `switch expression` không có `default` có thể bị báo không exhaustive nếu thiếu case cho subtype mới. Cần bổ sung xử lý có ý nghĩa, thay vì thêm `default` vô điều kiện để làm mất tín hiệu.

**Câu 4:** Có nên dùng `--enable-preview` để chạy ví dụ chính Java 21 trong bài không?

**Đáp án:** Không cần. Type patterns cho `instanceof`, record patterns và pattern matching for `switch` đã là tính năng chính thức trong Java 21. Preview chỉ liên quan những JEP khác chưa hoàn thiện trong phiên bản đó.

## 14. Tài liệu nền

- **JEP 394 – Pattern Matching for `instanceof`:** https://openjdk.org/jeps/394
- **JEP 395 – Records:** https://openjdk.org/jeps/395
- **JEP 409 – Sealed Classes:** https://openjdk.org/jeps/409
- **JEP 440 – Record Patterns:** https://openjdk.org/jeps/440
- **JEP 441 – Pattern Matching for `switch`:** https://openjdk.org/jeps/441
- **JEP 443 – Unnamed Patterns and Variables (Preview in Java 21):** https://openjdk.org/jeps/443
- **Java Language Specification 21, Patterns (`14.30):** https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30
- **Java 21 Language Guide – Pattern Matching for `switch`:** https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html

**Kết luận:** Java 21 đánh dấu giai đoạn **record patterns** và **pattern matching for `switch`** trở thành tính năng chính thức. Kết hợp với type patterns của Java 16, records của Java 16 và sealed types của Java 17, chúng tạo một bộ công cụ mạnh để biểu diễn và phân loại cấu trúc dữ liệu. Để dùng đúng, cần hiểu **phiên bản ngôn ngữ, type/record pattern, flow scope, `when`, null, dominance và exhaustiveness**; khi nâng cấp dự án, đừng nhầm tính năng chính thức với preview và luôn kiểm chứng logic bằng compiler cùng test thực tế.
