# Theo dõi case được chọn khi debug Pattern Matching trong Java 21

## 1. Mục tiêu: biết nhánh nào **thật sự** chạy

Khi dùng `switch` với type pattern, record pattern và guard `when`, một giá trị đầu vào có thể nhìn giống nhiều mẫu khác nhau. Trong lúc debug, cần phân biệt ba sự kiện:

1. **Pattern được thử:** trình thực thi xem nhãn `case` theo quy tắc lựa chọn của `switch`.
2. **Pattern khớp nhưng guard sai:** dữ liệu đúng kiểu/cấu trúc, nhưng điều kiện `when` trả `false`, nên phải xét nhánh tiếp theo.
3. **Case được chọn:** pattern khớp (và guard đúng nếu có); phần thân nhánh chạy và sinh kết quả hoặc thực hiện lệnh.

Chỉ sự kiện thứ ba trả lời trực tiếp câu hỏi **“case nào đã được chọn?”**. Ví dụ:

```java
return switch (value) {
    case String text when !text.isBlank() -> "Có nội dung";
    case String text -> "Chuỗi rỗng hoặc trắng";
    default -> "Không phải chuỗi";
};
```

Với `value = "   "`, **pattern `String` đầu tiên khớp về kiểu** nhưng guard `!text.isBlank()` trả false. Kết quả là **case thứ hai**, không phải case thứ nhất. Với `value = 42`, cả hai pattern String đều không khớp và `default` được chọn.

Chỉ nhìn kiểu runtime hoặc đặt log trong phương thức xử lý chung không đủ để biết chính xác đường đi. Ta nên có một cách xác định **case ID**, **đầu vào hoặc điều kiện liên quan** và **kết quả**, mà không vô tình sửa logic hoặc ghi log nhạy cảm.

**Phiên bản:** Pattern matching cho `switch` (JEP 441) và record patterns (JEP 440) là tính năng chính thức từ **Java 21**. Bài dùng JDK 21+, không cần `--enable-preview`. Các phương pháp breakpoint, logging và kiểm thử cũng áp dụng cho `switch` truyền thống.

## 2. Cơ chế chọn nhánh trong switch pattern matching

Một cách đọc đúng là:

```text
Giá trị selector
    |
    v
Xử lý selector null nếu có case null phù hợp
    |
    v
Xét các nhãn case theo thứ tự
    |
    +-- Pattern không khớp --------> thử case tiếp theo
    |
    +-- Pattern khớp
          |
          +-- Có guard when?
                |
                +-- false -------> thử case tiếp theo
                |
                +-- true / không có guard
                         |
                         v
                   CASE ĐƯỢC CHỌN
                         |
                         v
                 Chạy biểu thức / block nhánh
                         |
                         v
               Giá trị yield hoặc side effect
```

**Điểm cần lưu ý:**

- Selector của `switch` được đánh giá một lần, nhưng kết quả khớp từng pattern và guard phụ thuộc vào các case.
- Trong một enhanced `switch`, `null` cần chính sách riêng. Đừng mặc định `default` sẽ bắt selector null; muốn xử lý tường minh có thể dùng `case null`.
- Record pattern kiểm tra các component theo cấu trúc. Nếu một component dùng nested record pattern không có đúng loại (kể cả null), **toàn bộ pattern không khớp** và guard của case đó không chạy.
- `when` chỉ được đánh giá **sau khi** pattern khớp. Guard trả false có nghĩa là tiếp tục tìm nhánh, **không** có nghĩa đã chạy thân case.
- Nếu guard ném exception, đừng hiểu đó là “guard false”: exception có thể thoát khỏi `switch`. Nếu code trong thân nhánh ném exception thì nhánh đã được chọn nhưng có thể không tạo kết quả thành công.
- Với nhánh dạng `->`, **không có fall-through** giữa các case. Với `switch statement` dạng dấu hai chấm `:` truyền thống, cần lưu ý hành vi fall-through khi không có `break` và các hạn chế riêng của pattern labels.
- Với `switch expression`, mỗi nhánh được chọn phải cung cấp giá trị (hoặc kết thúc đột ngột do exception). Trong block `-> { ... }`, dùng `yield` để cung cấp giá trị; với `switch statement`, không dùng `yield` để trả giá trị cho một statement thông thường.

Một điểm phân biệt quan trọng khi ghi nhận trace: **“pattern được xét”** không phải **“case được chọn”**. Ghi log tại nhánh thực thi hoặc trả về **Case ID** là cách quan sát chính xác hơn.

## 3. Cách 1 — Gắn Case ID rõ ràng vào kết quả

Khi việc phân loại có output, có thể trả về một record chứa **mã nhánh** và **kết quả nghiệp vụ**:

```java
enum SelectedCase {
    NORMAL_TEXT,
    EMPTY_TEXT,
    OTHER
}

record Decision(SelectedCase selectedCase, String message) {}

static Decision decide(Object value) {
    return switch (value) {
        case String s when !s.isBlank() ->
            new Decision(SelectedCase.NORMAL_TEXT, s.strip());
        case String s ->
            new Decision(SelectedCase.EMPTY_TEXT, "(rỗng)");
        default ->
            new Decision(SelectedCase.OTHER, "khác");
    };
}
```

Đoạn này là một mẫu trong cùng class, cần imports/tên miền bao quanh tùy ứng dụng; chương trình độc lập hoàn chỉnh nằm ở mục 7. Với input `"  Java  "`, mã case là `NORMAL_TEXT` và message `"Java"`; với `" "`, mã là `EMPTY_TEXT`.

**Ưu điểm:**

- Test có thể khẳng định `selectedCase()` trực tiếp, không phải phân tích text log.
- Mã nhánh là dữ liệu có kiểu `enum`, ít phụ thuộc vào thông báo hiển thị, bản dịch hoặc format output.
- Có thể ghi log **sau** khi `switch` trả kết quả; giữ các guard thuần và tránh lặp câu lệnh log trong mọi case.
- Một request ID hoặc trace ID có thể được ghép ở tầng bên ngoài mà không đưa toàn bộ payload vào log.

**Cân nhắc:** không nhất thiết thêm field `selectedCase` vào DTO public của mọi API. Trong ứng dụng lớn, có thể giữ nó trong kết quả nội bộ, event debug hoặc một adapter logging, tránh làm thay đổi hợp đồng bên ngoài chỉ phục vụ điều tra.

## 4. Cách 2 — Log ngay trong thân case

Khi dùng `switch statement`, mỗi case có thể có một log ở điểm đầu:

```java
// Minh họa: logger, value và các handler đã được khai báo.
switch (value) {
    case String s when !s.isBlank() -> {
        logger.fine("selected=NONBLANK_STRING");
        handleText(s);
    }
    case String s -> {
        logger.fine("selected=BLANK_STRING");
        handleBlank(s);
    }
    default -> {
        logger.fine("selected=OTHER");
        handleOther(value);
    }
}
```

Đây là **mẫu minh họa**, không phải chương trình độc lập. Với `switch statement`, dấu `->` giúp thấy ngay block thuộc nhánh nào, không cần `break` ở cuối mỗi case.

Trong `switch expression`, nếu muốn log trong block, phải tạo giá trị bằng `yield`:

```java
// Minh họa: logger và value có sẵn.
String result = switch (value) {
    case String s when !s.isBlank() -> {
        logger.fine("selected=NONBLANK_STRING");
        yield s.strip();
    }
    case String s -> {
        logger.fine("selected=BLANK_STRING");
        yield "(rỗng)";
    }
    default -> {
        logger.fine("selected=OTHER");
        yield "khác";
    }
};
```

**Ưu điểm:** thấy case được chọn ở điểm thực thi; dễ gắn breakpoint vào câu lệnh log. **Nhược điểm:** log lặp ở nhiều nhánh, có thể rải concerns hạ tầng vào logic nghiệp vụ. Nếu chỉ cần giám sát tên case, một record `Outcome` kèm mã nhánh hoặc wrapper theo dõi bên ngoài thường ít xâm lấn hơn.

Với `java.util.logging.Logger`, dùng mức `FINE` hoặc tương đương để tránh spam production; log có được hiển thị hay không còn tùy cấu hình logger/handler. Chỉ dùng `System.out.println` cho demo nhỏ, không coi nó là hệ thống tracing production.

## 5. Cách 3 — Breakpoint ở điểm bắt đầu từng case

Dùng IDE có debugger (IntelliJ IDEA, Eclipse, VS Code với Java Debugger) hoặc `jdb`:

1. Biên dịch ở debug mode (theo mặc định `javac` thường bao gồm một số thông tin debug; có thể chỉ rõ `-g` khi cần).
2. Đặt breakpoint tại **dòng đầu tiên của thân nhánh** muốn theo dõi, hoặc tại nơi tạo `Decision` chứa Case ID.
3. Chạy với input cụ thể; khi dừng, kiểm tra selector, pattern variable, các component của record và giá trị guard liên quan.
4. Dùng step over/step into để theo dõi hàm xử lý được gọi. Nếu guard nằm trong helper, đặt breakpoint trong helper để thấy vì sao true/false.
5. Dùng conditional breakpoint nếu chỉ muốn dừng khi ID hoặc một thuộc tính đạt điều kiện, nhưng cẩn thận biểu thức điều kiện có side effect.
6. Khi nghi ngờ một nhánh không được chọn, đặt breakpoint ở **nhánh được chọn thực tế** và ở guard/helper; một breakpoint không kích hoạt không tự chứng minh nguyên nhân.

**Tình huống cần phân biệt:**

- Breakpoint trong **case body** không dừng nếu pattern không khớp hoặc guard false.
- Breakpoint trong **guard helper** có thể dừng khi type pattern khớp, kể cả sau đó helper trả false.
- Breakpoint trong **handler** xác nhận handler được gọi, nhưng không chắc phân biệt được hai case nếu nhiều case cùng gọi handler ấy.
- Nếu guard/helper ném exception, dùng exception breakpoint để biết vị trí và nguyên nhân; không nhầm với một nhánh fallback.

Đừng phụ thuộc tuyệt đối vào số dòng mapping một-một giữa source và bytecode: compiler có thể tạo cấu trúc điều khiển khác với cách viết pattern. Khi nghi ngờ, xác thực bằng input test, breakpoint ở statement rõ ràng và trace result, thay vì suy đoán từ các bước nhảy của debugger.

## 6. Đặt tên case, không suy ra bằng output text

Cách thiếu ổn định:

```java
// Không nên coi text hiển thị là định danh kỹ thuật của case.
if (result.startsWith("Ưu tiên")) {
    // Suy ra đã chọn case nào?
}
```

Khi thay đổi bản dịch, template hoặc format, logic kiểm thử/debug sẽ vỡ. Bên cạnh đó, **hai nhánh có thể trả cùng chuỗi** nhưng được chọn vì điều kiện khác nhau.

Cách rõ hơn:

```java
record Outcome(Branch branch, String text) {}
enum Branch { PRIORITY, ORDINARY, MISSING_DATA }
```

Rồi kiểm tra `outcome.branch()`. Nếu chỉ dùng diagnostic logging, có thể ghi `selected=PRIORITY` ở một nơi ổn định. Mục tiêu là tách **“vì sao đi vào nhánh này”** khỏi **“nội dung hiển thị cho người dùng”**.

Không ghi đầy đủ dữ liệu nhạy cảm vào log chỉ để xác định case: thường **case ID, loại selector, một correlation ID và một số cờ điều kiện** đã đủ. ID hoặc payload thuộc dữ liệu cá nhân/đơn hàng phải tuân thủ chính sách bảo mật, masking và retention của ứng dụng.

## 7. Ví dụ hoàn chỉnh Java 21: chọn case, xác minh kết quả và trace

Chương trình này cố ý có những nhánh dễ nhầm:

- `Shipment` ưu tiên: cần `Location` có mặt, city không-null/blank và priority đủ cao.
- `Shipment` có `Location` nhưng **không đủ điều kiện ưu tiên**.
- `Shipment` thiếu `Location`, nên hai record patterns lồng không khớp.
- `Message` có text không rỗng, và `Message` còn lại.
- `Measurement` dương, và `Measurement` không dương.
- Selector `null`.

Thay vì log trong guard, mỗi nhánh trả một `Outcome` với `CaseId`. Hàm `verify` kiểm tra case được chọn và chỉ in sau khi `switch` hoàn tất.

Tạo file **`CaseSelectionTraceDemo.java`**:

```java
public class CaseSelectionTraceDemo {

    sealed interface Input permits Shipment, Message, Measurement {}

    record Location(String city) {}

    record Shipment(String code, Location location, int priority)
            implements Input {}

    record Message(String text) implements Input {}

    record Measurement(int value) implements Input {}

    enum CaseId {
        NULL_INPUT,
        PRIORITY_SHIPMENT,
        SHIPMENT_WITH_LOCATION,
        SHIPMENT_NO_LOCATION,
        NONBLANK_MESSAGE,
        OTHER_MESSAGE,
        POSITIVE_MEASUREMENT,
        OTHER_MEASUREMENT
    }

    record Outcome(CaseId selected, String description) {}

    static Outcome classify(Input input) {
        return switch (input) {
            case null ->
                new Outcome(CaseId.NULL_INPUT, "Đầu vào null");

            // Chỉ khớp khi Location không-null và guard true.
            case Shipment(var code, Location(var city), var priority)
                    when priority >= 5
                        && city != null
                        && !city.isBlank() ->
                new Outcome(
                    CaseId.PRIORITY_SHIPMENT,
                    "Ưu tiên " + code + " đến " + city);

            // Cùng record pattern nhưng không có guard.
            case Shipment(var code, Location(var city), var priority) ->
                new Outcome(
                    CaseId.SHIPMENT_WITH_LOCATION,
                    "Có vị trí " + code
                        + " tại " + String.valueOf(city));

            // Location null: cả hai record patterns phía trên fail.
            case Shipment shipment ->
                new Outcome(
                    CaseId.SHIPMENT_NO_LOCATION,
                    "Thiếu Location " + shipment.code());

            case Message(var text)
                    when text != null && !text.isBlank() ->
                new Outcome(
                    CaseId.NONBLANK_MESSAGE,
                    "Nội dung " + text.strip());

            case Message message ->
                new Outcome(
                    CaseId.OTHER_MESSAGE,
                    "Nội dung rỗng hoặc null");

            case Measurement(var value) when value > 0 ->
                new Outcome(
                    CaseId.POSITIVE_MEASUREMENT,
                    "Giá trị dương " + value);

            case Measurement measurement ->
                new Outcome(
                    CaseId.OTHER_MEASUREMENT,
                    "Giá trị không dương " + measurement.value());
        };
    }

    static void verify(Input input, CaseId expected) {
        Outcome outcome = classify(input);

        if (outcome.selected() != expected) {
            throw new AssertionError(
                "Expected " + expected + ", got " + outcome.selected());
        }

        // Trace chỉ sau khi classify hoàn tất:
        // một input, một CaseId, không log trong guard.
        System.out.println(
            "case=" + outcome.selected()
                + " | " + outcome.description());
    }

    public static void main(String[] args) {
        verify(
            new Shipment("S-1", new Location("Hà Nội"), 8),
            CaseId.PRIORITY_SHIPMENT);

        verify(
            new Shipment("S-2", new Location("Huế"), 2),
            CaseId.SHIPMENT_WITH_LOCATION);

        // Guard ưu tiên sai vì city == null, nhưng nested
        // Location(...) vẫn khớp; case thứ hai nhận.
        verify(
            new Shipment("S-3", new Location(null), 9),
            CaseId.SHIPMENT_WITH_LOCATION);

        // location == null làm nested Location(...) không khớp.
        verify(
            new Shipment("S-4", null, 9),
            CaseId.SHIPMENT_NO_LOCATION);

        verify(new Message("  Java  "), CaseId.NONBLANK_MESSAGE);
        verify(new Message("  "), CaseId.OTHER_MESSAGE);
        verify(new Message(null), CaseId.OTHER_MESSAGE);
        verify(new Measurement(4), CaseId.POSITIVE_MEASUREMENT);
        verify(new Measurement(0), CaseId.OTHER_MEASUREMENT);
        verify(null, CaseId.NULL_INPUT);
    }
}
```

Biên dịch và chạy trong thư mục chứa file bằng **JDK 21+**:

```bash
javac --release 21 -encoding UTF-8 -g CaseSelectionTraceDemo.java
java CaseSelectionTraceDemo
```

Đầu ra dự kiến chính xác:

```text
case=PRIORITY_SHIPMENT | Ưu tiên S-1 đến Hà Nội
case=SHIPMENT_WITH_LOCATION | Có vị trí S-2 tại Huế
case=SHIPMENT_WITH_LOCATION | Có vị trí S-3 tại null
case=SHIPMENT_NO_LOCATION | Thiếu Location S-4
case=NONBLANK_MESSAGE | Nội dung Java
case=OTHER_MESSAGE | Nội dung rỗng hoặc null
case=OTHER_MESSAGE | Nội dung rỗng hoặc null
case=POSITIVE_MEASUREMENT | Giá trị dương 4
case=OTHER_MEASUREMENT | Giá trị không dương 0
case=NULL_INPUT | Đầu vào null
```

### 7.1. Tại sao không có `default` trong chương trình chính?

`Input` là một `sealed interface` chỉ cho phép `Shipment`, `Message` và `Measurement` trong ví dụ này. Các case không guard cho từng kiểu bao phủ mọi instance non-null của các subtype; thêm `case null` xử lý null. Vì vậy `switch expression` là **exhaustive**, không cần `default`.

Nếu mở rộng hệ sealed bằng một subtype mới, khi các case hiện tại không bao phủ subtype đó, compiler buộc cập nhật `switch`. Đây là cơ hội bổ sung một case ID đúng nghiệp vụ, thay vì để default che lỗi thiếu nhánh.

### 7.2. S-2: pattern khớp nhưng guard false

S-2 có `Location("Huế")` hợp lệ về cấu trúc, nhưng `priority == 2` không đạt `priority >= 5`. Guard của case đầu trả false. Trình thực thi xét nhánh kế tiếp có cùng record pattern nhưng không guard và chọn `SHIPMENT_WITH_LOCATION`.

**Trace đúng phải là case thứ hai**, dù type và record shape của case đầu đều khớp.

### 7.3. S-3: guard false do thành phố null

S-3 có một `Location` **không-null** với component `city == null`. `Location(var city)` khớp và ràng buộc biến `city` có kiểu `String`, nhưng giá trị có thể null. Guard `priority >= 5 && city != null && !city.isBlank()` trả false ở kiểm tra null, nên không gọi `city.isBlank()`; không ném NPE.

Case `Shipment(..., Location(var city), ...)` thứ hai không có guard, nên được chọn và kết quả hiển thị chuỗi `"null"` qua `String.valueOf(city)`. Đây là **chủ ý minh họa sự khác nhau giữa null component và null record**, không phải mẫu format nghiệp vụ được khuyến nghị. Trong hệ thống thật nên quyết định city null là lỗi, vắng mặt hợp lệ hay trạng thái riêng.

### 7.4. S-4: nested record pattern không khớp

S-4 có `location == null`. Nested `Location(var city)` ở cả hai case đầu **không khớp**, do đó **không chạy guard của case ưu tiên**. `case Shipment shipment` còn lại nhận S-4 và trả `SHIPMENT_NO_LOCATION`.

Nếu chỉ nhìn `priority == 9` rồi kết luận “phải ưu tiên”, ta đã bỏ sót **điều kiện cấu trúc**. Trên debugger cần xem cả `location` và điều kiện `when`.

### 7.5. Message: tách pattern khớp và guard sai

`Message("  Java  ")` khớp record, text không null và không blank → `NONBLANK_MESSAGE`. `Message("  ")` khớp record nhưng guard `!text.isBlank()` false → `OTHER_MESSAGE`. `Message(null)` vẫn **khớp `Message(var text)`** vì `var` nhận component null; guard `text != null` false → `OTHER_MESSAGE`.

### 7.6. Measurement: điều kiện giá trị tách khỏi kiểu

Hai giá trị `Measurement(4)` và `Measurement(0)` đều cùng kiểu. Guard `value > 0` xác định `POSITIVE_MEASUREMENT`; giá trị không dương vào `OTHER_MEASUREMENT`. Việc đặt nhánh có guard trước nhánh tổng quát là cần thiết để không bị dominance.

## 8. Debug cùng một input bằng bảng quyết định

Khi một trường hợp không rơi vào case mong đợi, đừng chỉ nhìn cuối output. Lập một bảng trạng thái theo thứ tự các nhánh:

| Input | Case có guard đầu tiên | Lý do tiếp tục hoặc chọn | Case được chọn |
| --- | --- | --- | --- |
| `Shipment("S-1", Location("Hà Nội"), 8)` | Pattern khớp, guard true | Có Location, priority cao, city hợp lệ | `PRIORITY_SHIPMENT` |
| `Shipment("S-2", Location("Huế"), 2)` | Pattern khớp, guard false | Priority nhỏ hơn 5 | `SHIPMENT_WITH_LOCATION` |
| `Shipment("S-3", Location(null), 9)` | Pattern khớp, guard false | City null, short-circuit bảo vệ NPE | `SHIPMENT_WITH_LOCATION` |
| `Shipment("S-4", null, 9)` | Pattern không khớp | Nested Location không-null là bắt buộc | `SHIPMENT_NO_LOCATION` |
| `Message("  ")` | Pattern khớp, guard false | Chuỗi blank | `OTHER_MESSAGE` |
| `Message(null)` | Pattern khớp, guard false | `var text` có thể nhận null | `OTHER_MESSAGE` |
| `Measurement(0)` | Pattern khớp, guard false | Số không dương | `OTHER_MEASUREMENT` |
| `null` | Chọn case null | Selector null có chính sách tường minh | `NULL_INPUT` |

Bảng này giải thích **vì sao** một case được chọn, còn `Outcome.selected()` cho phép test **case nào** được chọn. Kết hợp hai cách giúp debug đáng tin cậy hơn việc suy luận từ một thông báo chung.

## 9. Log ở đâu để không làm thay đổi luồng chọn case?

Có ba vị trí quan sát có mục đích khác nhau:

| Vị trí đặt log/breakpoint | Biết được điều gì? | Không tự chứng minh điều gì? |
| --- | --- | --- |
| Trước `switch` | Selector đầu vào, context, correlation ID | Case cuối cùng |
| Bên trong helper được gọi bởi `when` | Helper được gọi và điều kiện đang được xét | Guard tổng thể true hoặc case được chọn |
| Dòng đầu của thân `case` | Nhánh này thực sự được chọn | Vì sao mọi nhánh trước nó không được chọn |
| Sau `switch` nhận `Outcome` có Case ID | Case được chọn và kết quả trả về | Mọi phép kiểm tra trung gian, nếu không có trace chi tiết |
| Trong `catch` bao quanh `switch` | Exception thoát ra | Case nào từng match nếu exception xảy ra trước thân case |

**Khuyến nghị:** trước tiên hãy dùng **mã định danh case + test có dữ liệu biên**. Khi một case ID không đúng kỳ vọng, mới thêm breakpoint tại guard/helper và theo dõi các thành phần cụ thể. Đó thường là cách ít thay đổi mã nhất.

### Không đưa logging có side effect vào guard chỉ để theo dõi

Một đoạn như:

```java
// KHÔNG KHUYẾN NGHỊ cho code nghiệp vụ:
case Message(var text) when debugAndReturnTrue(text)
        && text != null && !text.isBlank() ->
    handleText(text);
```

có thể khiến guard vừa thay đổi hệ thống, vừa trả Boolean. Nếu việc log thất bại hoặc helper không thuần, quá trình phân loại có thể bị ảnh hưởng. Nếu `debugAndReturnTrue` luôn true thì logic trông tương đương nhưng vẫn có side effect ở nơi quyết định nhánh.

Cách tốt hơn: dùng breakpoint ở helper kiểm tra **thuần** hoặc log **sau khi** nhận outcome. Không tự sửa thứ tự guard, thêm lời gọi accessor tốn kém hay đánh giá một biểu thức hai lần chỉ để in giá trị.

### Cẩn trọng với guard có chi phí cao

Nếu `when isEligible(input)` gọi dịch vụ ngoài hoặc có side effect, debugging trở nên khó dự đoán và có thể không giữ tính quyết định. Cân nhắc tách quyết định nghiệp vụ thành một bước có kiểu kết quả rõ ràng và thử trên dữ liệu snapshot. `when` nên ưu tiên điều kiện ngắn hoặc helper thuần, dễ kiểm thử.

## 10. Phân biệt lỗi compiler với vấn đề runtime

Có những nhánh **không thể được chọn ngay từ source**, compiler Java 21 có thể báo lỗi vì dominance.

Ví dụ **cố ý sai, không biên dịch**:

```java
return switch (input) {
    case Shipment shipment ->
        "Mọi Shipment";
    case Shipment(var code, Location(var city), var priority)
            when priority >= 5 ->
        "Ưu tiên"; // Bị nhánh Shipment tổng quát che.
    default -> "Khác";
};
```

`case Shipment shipment` đã nhận mọi đối tượng `Shipment` non-null. Nhánh lồng phía sau không thể đến; đừng tìm vấn đề này bằng log runtime, hãy **đọc lỗi compiler và đặt nhánh cụ thể trước nhánh rộng**.

Với cùng type, thứ tự hợp lý:

```java
// Nhãn case minh họa, cần đặt trong switch phù hợp.
case Shipment(var code, Location(var city), var priority)
        when priority >= 5 ->
    "Ưu tiên";
case Shipment shipment ->
    "Shipment còn lại";
```

Lưu ý nhánh đầu vẫn cần `Location` không-null; nếu location null, nhánh tổng quát xử lý. Guard chỉ được xét khi pattern đầu khớp.

**Phạm vi pattern variable** cũng do compiler kiểm soát: `city` của case đầu chỉ ở trong `when` và thân case ấy, không đi sang case khác. Nếu đặt câu lệnh log tham chiếu `city` sau `switch`, nó không hợp lệ; muốn quan sát, đưa thông tin thích hợp vào `Outcome` hoặc log ngay trong phạm vi hợp lệ.

## 11. Switch expression so với switch statement khi debug

| Tiêu chí | `switch expression` | `switch statement` |
| --- | --- | --- |
| Mục tiêu | Tính ra giá trị | Thực hiện câu lệnh/side effect |
| Nhánh `case T t -> expr` | Trả giá trị của biểu thức | Dùng làm expression statement hợp lệ khi biểu thức là statement expression |
| Nhánh `-> { ... }` | Dùng `yield value` khi cần trả giá trị từ block | Chạy các statement; không cần `yield` |
| Theo dõi case | Case ID trong result là lựa chọn thuận tiện | Log/breakpoint đầu block hoặc callback chung |
| Fall-through | Không xảy ra | Dạng `->` không; dạng `:` truyền thống có thể có |
| Exhaustiveness | Bắt buộc phải bao phủ các trường hợp phù hợp | Các quy tắc exhaustiveness của enhanced switch statement cũng cần chú ý |

Trong bài này, `classify` là `switch expression`. Nó làm một việc: **phân loại input thành outcome**. Hàm `verify` làm việc còn lại: đối chiếu expected branch và phát log. Việc tách này giảm nguy cơ log phụ tác động lên logic phân nhánh.

## 12. Checklist debug một case không được chọn

1. **Ghi lại input thực tế** và kiểu runtime, không chỉ giá trị dự kiến.
2. **Xem selector null không** và có `case null` hay guard đầu vào phù hợp chưa.
3. **Xem thứ tự case**: nhánh tổng quát có che nhánh cụ thể không?
4. **Kiểm tra cây record từ ngoài vào trong**, đặc biệt các nested components null.
5. **Phân biệt `var component` với `Type(...)`**: `var` có thể giữ null; nested record pattern không match null.
6. **Tính guard trên đúng dữ liệu**: biến pattern có kiểu/value nào, điều kiện short-circuit nào dừng trước?
7. **Xem guard có ném exception không**: exception khác false.
8. **Đặt breakpoint trong body nhánh thực tế và guard helper**, không suy luận chỉ từ breakpoint không dừng.
9. **Dùng Case ID để assert** nhánh được chọn; không so sánh text log làm định danh duy nhất.
10. **Kiểm tra fallback/default** và các trường hợp input không thuộc hệ sealed hoặc enum (nếu API nhận kiểu rộng).
11. **Đối chiếu output và side effect**: case được chọn không luôn có nghĩa thao tác hoàn tất thành công.
12. **Thử lại bằng bộ test nhỏ, xác định** để tránh phụ thuộc vào lịch sử thao tác hoặc dữ liệu thay đổi giữa các lần chạy.

### Một mẫu lỗi dễ bỏ qua: null ở record con

```java
record Address(String city) {}
record Delivery(Address address) {}

// Nhãn case minh họa:
case Delivery(Address(var city)) when city != null ->
    "Có thành phố";
case Delivery delivery ->
    "Delivery khác";
```

Với `new Delivery(null)`, case đầu không match vì `Address(...)` không match null; guard `city != null` **không được chạy**. Case thứ hai được chọn. Nếu muốn log riêng trạng thái thiếu địa chỉ, có thể dùng `case Delivery(var address) when address == null -> ...`, đặt trước case tổng quát.

## 13. Kiểm thử regression thay vì chỉ đọc log

Một test tốt kiểm tra **nhánh được chọn**, **kết quả**, và khi cần **side effect/exception**.

Trong ví dụ ở mục 7, `verify` kiểm tra `Outcome.selected()`; nếu sai, ném `AssertionError` thay vì chỉ in ra. Để mạnh hơn, có thể thêm expected description:

```java
// Mẫu minh họa, cùng class với Outcome và classify.
static void assertOutcome(Input input,
                          CaseId expectedCase,
                          String expectedDescription) {
    Outcome actual = classify(input);
    if (actual.selected() != expectedCase
            || !actual.description().equals(expectedDescription)) {
        throw new AssertionError("Unexpected outcome: " + actual);
    }
}
```

Với JUnit 5, có thể viết test theo bảng dữ liệu để xác nhận các trường hợp cụ thể, nhưng cú pháp project phụ thuộc dependency và cấu hình JUnit hiện tại. Mã Java độc lập ở mục 7 không cần JUnit và vẫn tạo xác minh tự động đơn giản.

**Nên có test cho:**
- pattern + guard true;
- pattern match nhưng guard false;
- nested record null làm pattern không match;
- component `var` null nhưng record vẫn match;
- case tổng quát của cùng type;
- selector null;
- số ở ranh giới ngưỡng (ví dụ priority 4/5, value 0/1);
- ngoại lệ trong guard/handler nếu ứng dụng cho phép;
- thêm subtype mới vào sealed hierarchy và sửa switch exhaustive.

Không nên khẳng định một Case ID khớp là đã kiểm thử mọi nghiệp vụ: output và tương tác với hệ thống phụ thuộc vẫn cần kiểm tra tương ứng.

## 14. Quan sát production: log có cấu trúc và bảo vệ dữ liệu

Một log trace có ích thường chứa:

```text
traceId=...  operation=classify  selectedCase=PRIORITY_SHIPMENT
```

Đây là **mẫu format minh họa**, không phải một ID cụ thể. Nếu hệ thống xử lý nhiều request đồng thời, correlation/trace ID giúp ghép log. Ghi log **sau khi có kết quả phân loại** có thể giảm sai lệch giữa “case nào được chọn” và “giá trị đã phát ra”.

Các thực hành tốt:

- Dùng logger đúng mức, điều chỉnh sampling/verbosity ở môi trường production để tránh quá nhiều sự kiện.
- Tên Case ID ổn định để dashboard/metric không phụ thuộc ngôn ngữ giao diện.
- Không ghi raw payload, email, địa chỉ cụ thể, token hay dữ liệu bí mật khi chỉ cần tên nhánh.
- Phân biệt `selectedCase` với `operationStatus`; nhánh được chọn không chứng minh việc ghi DB/HTTP thành công.
- Nếu muốn đếm số lần chọn case, cập nhật metric ở tầng ghi nhận kết quả; không chèn phép tăng counter có side effect vào guard.
- Khi thay đổi thứ tự nhánh, cập nhật test Case ID và theo dõi thay đổi tỷ lệ case trong những lần triển khai có quan sát thực tế.

## 15. Lỗi thường gặp

| Hiểu nhầm | Thực tế | Cách sửa |
| --- | --- | --- |
| “Kiểu khớp nên chắc case đầu chạy” | Guard có thể false | Theo dõi guard và assert Case ID |
| “Guard false nghĩa là đã vào case rồi” | Chỉ thân case được chọn mới chạy | Log tại thân/Outcome sau switch |
| “Nested record null cũng sẽ tới `when`” | Pattern lồng không khớp trước guard | Kiểm tra component và bắt bằng `var` khi muốn xử lý null |
| “`var text` luôn khác null” | Component có thể null | Kiểm tra null trước khi gọi method |
| “`default` xử lý mọi null” | Enhanced switch có quy tắc riêng cho selector null | `case null` tường minh hoặc chặn trước switch |
| “Cần log trong tất cả guard” | Log tạo side effect ở logic chọn nhánh | Đưa Case ID vào result, đặt breakpoint/helper thuần |
| “Hai case có cùng output là cùng case” | Cùng String không xác định đường đi | Dùng enum Case ID hoặc branch tags |
| “Case luôn không chạy dù test đúng” | Có thể bị dominance ở compile-time | Đọc lỗi compiler và sắp xếp cụ thể trước tổng quát |
| “Case chạy nghĩa là xử lý thành công” | Handler/IO có thể lỗi sau khi vào case | Tách selectedCase khỏi operation status |
| “Càng log nhiều data càng dễ debug” | Có rủi ro lộ thông tin và tạo nhiễu | Log tối thiểu thông tin liên quan, masking |
| “`switch` expression có fall-through” | Nhánh arrow không fall-through | Xem cách nhánh trả giá trị/`yield` |
| “Debugger dừng ở helper đồng nghĩa chọn nhánh” | Helper `when` có thể trả false | Đặt breakpoint tại thân case hoặc assert Outcome |

## 16. Bài tập

**Bài 1 — Dự đoán case.** Với `Shipment("S-5", new Location("Đà Nẵng"), 5)`, Case ID nào được chọn? Đáp án: `PRIORITY_SHIPMENT` vì priority đúng bằng ngưỡng 5, city có nội dung.

**Bài 2 — Pattern fail hay guard false?** So sánh `Shipment("S-6", null, 8)` với `Shipment("S-7", new Location(null), 8)`. Trường hợp đầu không khớp nested Location và chọn `SHIPMENT_NO_LOCATION`; trường hợp sau khớp Location nhưng guard sai nên chọn `SHIPMENT_WITH_LOCATION`.

**Bài 3 — Chuỗi trắng.** Vì sao `Message("   ")` không được chọn `NONBLANK_MESSAGE`, mặc dù đúng kiểu `Message`? Giải thích thứ tự đánh giá `text != null && !text.isBlank()`.

**Bài 4 — Thêm case riêng cho city null.** Thêm một case `Shipment(..., Location(var city), ...) when city == null` trước case Shipment có Location không guard. Tạo mã `SHIPMENT_NULL_CITY` mới và test S-3. Lưu ý xem xét vị trí so với case ưu tiên.

**Bài 5 — Thêm subtype sealed.** Khai báo `record Flag(boolean enabled) implements Input {}` và cập nhật `permits`. Quan sát compiler yêu cầu xử lý thêm nhánh khi `switch` không có `default`. Tạo Case ID và test cho hai giá trị true/false nếu cần.

**Bài 6 — Dùng debugger.** Đặt breakpoint tại kết quả `PRIORITY_SHIPMENT`, ở case `SHIPMENT_WITH_LOCATION` và ở guard/helper (nếu bạn trích helper riêng). Với S-2, xác định vì sao breakpoint ở nhánh ưu tiên không dừng.

**Bài 7 — Log và hành vi.** Nếu thêm logging vào guard bằng một helper không thuần, liệt kê hai rủi ro. Đề xuất cách ghi lại `selectedCase` sau khi phân loại mà không gọi lại `classify` lần nữa.

**Bài 8 — Tách nhánh và kết quả xử lý.** Viết thêm record `ProcessingReport(CaseId branch, boolean succeeded, String reason)` và giải thích vì sao branch ID và trạng thái thành công là hai thuộc tính riêng.

## 17. Tổng kết

Để **theo dõi case được chọn**, đừng chỉ suy luận từ kiểu input hoặc output text. Trong Java 21:

- **Pattern match** và **guard true** đều cần để nhánh có guard được chọn.
- Với nested record pattern, component record con null có thể làm pattern không khớp, khiến guard không được đánh giá.
- `var` trong record pattern có thể giữ component null.
- Case có guard nên đứng trước case cùng kiểu tổng quát, tránh dominance.
- `case null` diễn đạt chính sách selector null rõ ràng; arrow switch không fall-through.
- **Case ID trong Outcome** và breakpoint tại thân case giúp quan sát case thực sự chạy; test có thể assert trực tiếp Case ID.
- Logging nên ở điểm kết quả hoặc thân nhánh, tránh làm guard có side effect; tách case được chọn khỏi trạng thái xử lý thành công.

### Tài liệu tham khảo

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Java Language Specification 21 — Switch statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification 21 — Switch expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
