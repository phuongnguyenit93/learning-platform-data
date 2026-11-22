# Pattern trong switch statement (Java 21)

## 1. Vì sao cần pattern trong switch statement?

Trong Java, `switch` truyền thống thường so sánh một giá trị với các hằng như `int`, `String` hoặc `enum`. Khi đầu vào là `Object`, một interface hoặc một lớp cha chứa nhiều dạng dữ liệu, chỉ so sánh hằng không đủ. Trước khi có pattern matching cho `switch`, lập trình viên thường dùng chuỗi `if / else if` và `instanceof` để phân loại kiểu, sau đó lại ép kiểu hoặc gọi accessor để lấy thông tin.

**Pattern matching trong `switch statement`** cho phép viết các nhánh `case` theo *kiểu* và *cấu trúc* của đầu vào. Một nhánh có thể dùng type pattern (`String text`), record pattern (`Text(String content)`), record pattern lồng nhau (`Envelope(Text(String content), String destination)`) hoặc guard `when` để lọc điều kiện. Khi nhánh khớp, những biến pattern có thể dùng trực tiếp trong câu lệnh xử lý.

Bài này tập trung vào **`switch statement`**: cấu trúc điều khiển thực thi một hoặc nhiều câu lệnh, ví dụ ghi log, thông báo, cập nhật trạng thái, gọi một service. Cuối bài sẽ phân biệt rõ với **`switch expression`** vốn tạo ra một giá trị.

**Phiên bản:** Pattern matching cho `switch` được chuẩn hóa từ **Java 21** (JEP 441); record patterns được chuẩn hóa cùng phiên bản (JEP 440). Các ví dụ dùng JDK 21 trở lên và không cần `--enable-preview`.

Sau bài học, bạn có thể:
- Viết `switch statement` dùng type pattern, record pattern và guard `when`.
- Lựa chọn cú pháp nhánh mũi tên `->` hoặc dấu hai chấm `:`.
- Hiểu thứ tự pattern, dominance, exhaustive switch, `null` và phạm vi biến.
- Phát hiện những lỗi thường gặp khi chuyển từ `if/else` sang `switch`.

## 2. Cú pháp cơ bản: case khớp kiểu dữ liệu

Xét đầu vào có kiểu khai báo `Object`, có thể chứa `String`, `Integer` hoặc một kiểu khác. Một `switch statement` dùng pattern:

```java
// Minh họa trong một phương thức có biến value kiểu Object:
switch (value) {
    case String text ->
        System.out.println("Text length: " + text.length());

    case Integer number ->
        System.out.println("Integer: " + number);

    case null ->
        System.out.println("Value is null");

    default ->
        System.out.println("Another type");
}
```

Ở đây:

1. `case String text` là **type pattern**: kiểm tra selector có kiểu `String` và ràng buộc giá trị với biến `text`.
2. `case Integer number` kiểm tra selector có kiểu `Integer` và ràng buộc biến `number`.
3. `case null` xử lý riêng selector bằng `null`.
4. `default` nhận các đối tượng còn lại, chẳng hạn `Double`, `Long` hoặc kiểu tự định nghĩa.
5. Vì đây là **statement**, mỗi nhánh chỉ thực hiện lời gọi `System.out.println`. Toàn bộ `switch` không tạo ra giá trị để gán.

Khác với cách viết thủ công `if (value instanceof String)` rồi ép kiểu `(String) value`, biến `text` được trình biên dịch gắn kiểu sẵn, nên không cần cast.

**Lưu ý:** Giá trị selector của `switch` được tính khi vào `switch`, rồi so khớp các nhánh theo luật của Java. Không viết `switch` để thay thế một chuỗi điều kiện không liên quan đến cùng selector.

## 3. Hai kiểu viết case trong switch statement

### 3.1. Dùng arrow: case ... ->

Đây là cú pháp nên ưu tiên với pattern matching khi mỗi nhánh cần một hành động độc lập:

```java
// Minh họa:
switch (value) {
    case String text -> System.out.println(text);
    case Integer number -> System.out.println(number * 2);
    case null -> System.out.println("missing");
    default -> System.out.println("other");
}
```

Mỗi nhánh `->` chỉ thực hiện hành động của chính nó; **không fall-through** sang nhánh sau. Không cần thêm `break` để ngăn chạy tiếp.

Nếu một case gồm nhiều câu lệnh, dùng khối:

```java
case String text -> {
    String normalized = text.trim();
    System.out.println("Length: " + normalized.length());
    System.out.println("Text: " + normalized);
}
```

Đây là phần thân một case đặt bên trong `switch statement`, không phải chương trình độc lập.

### 3.2. Dùng colon: case ...:

Java 21 cũng cho phép **switch statement** kiểu truyền thống với nhãn pattern:

```java
switch (value) {
    case String text:
        System.out.println("Text: " + text);
        break;

    case Integer number:
        System.out.println("Integer: " + number);
        break;

    case null:
        System.out.println("missing");
        break;

    default:
        System.out.println("other");
}
```

Ở dạng `:`, `break` thoát khỏi `switch statement`. Với các case pattern ràng buộc biến, **không được dựa vào fall-through** giữa các nhánh: Java có các giới hạn biên dịch nhằm tránh rơi vào nhánh có biến pattern chưa được ràng buộc đúng cách. Khi chuyển mã cũ sang pattern switch, nên thêm `break` thích hợp hoặc chuyển cả `switch` sang dạng `->`.

Một switch block phải dùng nhất quán dạng **`case ... ->`** hoặc **`case ...:`**, không trộn hai dạng trong cùng một block.

### 3.3. Switch statement khác switch expression

| Tiêu chí | `switch statement` | `switch expression` |
| --- | --- | --- |
| Mục đích | Thực hiện hành động, điều khiển luồng chương trình | Tính và trả về một giá trị |
| Ví dụ | `switch (value) { case String s -> log(s); ... }` | `String result = switch (value) { case String s -> s; ... };` |
| Nhánh `->` | Có thể dùng statement expression, khối lệnh hoặc `throw` | Dùng biểu thức giá trị, khối có `yield` hoặc `throw` |
| `break` | Dùng để thoát switch, thường ở dạng `case ...:` | Không dùng `break` để trả về giá trị |
| `yield` | Không dùng để tạo kết quả của switch statement | Dùng trong block của switch expression để tạo kết quả |
| Exhaustiveness với case pattern | Enhanced switch statement phải bao phủ hết khả năng của selector | Switch expression cũng phải exhaustive |

Ví dụ dùng **expression** để đối chiếu, không phải cách triển khai của bài này:

```java
// value có kiểu Object:
String description = switch (value) {
    case String text -> "Text: " + text;
    case Integer number -> "Integer: " + number;
    case null -> "Missing";
    default -> "Other";
};
```

Trong `switch statement` dạng `->`, viết `case String text -> "Text: " + text;` chỉ để tạo chuỗi không phải một statement expression hợp lệ. Nếu muốn trả về chuỗi, chuyển sang `switch expression` hoặc gọi một phương thức thực hiện hành động, chẳng hạn `System.out.println`.

## 4. Ví dụ hoàn chỉnh: type pattern, record pattern, when và null

Giả sử ứng dụng nhận ba dạng thông điệp: văn bản, phép cộng và gói gửi văn bản đến một đích. Ta khai báo `sealed interface Message` với ba record con. Lợi ích của cấu trúc này là trình biên dịch có thể kiểm tra các nhánh `switch` có bao phủ mọi subtype hay chưa.

Tạo file **`SwitchStatementPatternDemo.java`**:

```java
public class SwitchStatementPatternDemo {

    sealed interface Message permits Text, Sum, Envelope {}

    record Text(String content) implements Message {}

    record Sum(int left, int right) implements Message {}

    record Envelope(Text text, String destination) implements Message {}

    static void handle(Message message) {
        switch (message) {
            case Text(String content) when content == null ->
                System.out.println("TEXT_NULL");

            case Text(String content) when content.isBlank() ->
                System.out.println("TEXT_EMPTY");

            case Text(String content) ->
                System.out.println("TEXT "
                    + content.toUpperCase(java.util.Locale.ROOT));

            case Sum(int left, int right)
                    when left < 0 || right < 0 ->
                System.out.println("SUM_INVALID");

            case Sum(int left, int right) ->
                System.out.println("SUM " + (left + right));

            case Envelope(Text(String content), String destination) ->
                System.out.println("SEND " + content
                    + " -> " + destination);

            case Envelope(var text, var destination) ->
                System.out.println("ENVELOPE_INCOMPLETE");

            case null ->
                System.out.println("NULL");
        }
    }

    static void inspect(Object value) {
        switch (value) {
            case String text:
                System.out.println("STRING " + text.length());
                break;

            case Integer number:
                System.out.println("INTEGER " + number);
                break;

            case null:
                System.out.println("OBJECT_NULL");
                break;

            default:
                System.out.println("OTHER");
        }
    }

    public static void main(String[] args) {
        handle(new Text("hello"));
        handle(new Text(""));
        handle(new Text(null));
        handle(new Sum(2, 5));
        handle(new Sum(-1, 8));
        handle(new Envelope(new Text("ping"), "ops"));
        handle(new Envelope(null, "ops"));
        handle(null);

        inspect("java");
        inspect(42);
        inspect(3.14);
        inspect(null);
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**:

```bash
javac --release 21 SwitchStatementPatternDemo.java
java SwitchStatementPatternDemo
```

**Stdout chính xác:**

```text
TEXT HELLO
TEXT_EMPTY
TEXT_NULL
SUM 7
SUM_INVALID
SEND ping -> ops
ENVELOPE_INCOMPLETE
NULL
STRING 4
INTEGER 42
OTHER
OBJECT_NULL
```

Chương trình được chia thành hai tình huống:

- **`handle(Message message)`** dùng `case ... ->` và phối hợp record patterns với guard `when`. Đây là `switch statement` thực hiện hành động in thông điệp; nó không cần gán hay trả về kết quả.
- **`inspect(Object value)`** dùng `case ...:`, type patterns và `break` để minh họa cách viết statement truyền thống. Có `default` do `Object` có thể là nhiều loại ngoài `String` và `Integer`.

### Giải thích nhóm case Text

`Text` là record có component `String content`. Trong record pattern `Text(String content)`, type pattern `String content` là **unconditional** đối với component khai báo `String`, vì vậy cũng có thể ràng buộc giá trị component bằng `null`. Điều này khác với việc dùng `null instanceof String` ở ngoài cùng, vốn luôn sai.

Do vậy case đầu tiên xử lý component null:

```java
case Text(String content) when content == null ->
    System.out.println("TEXT_NULL");
```

Case thứ hai xử lý chuỗi rỗng/trắng:

```java
case Text(String content) when content.isBlank() ->
    System.out.println("TEXT_EMPTY");
```

Vì nhánh `content == null` được xét trước, `content.isBlank()` chỉ được gọi đối với `Text` còn lại có content khác null; tránh `NullPointerException`. Cuối cùng, case `Text(String content)` không guard xử lý những trường hợp `Text` khác.

Nếu thay đổi thứ tự, chẳng hạn đưa case `Text(String content)` không guard lên đầu, nó sẽ bao phủ cả những case `Text` cụ thể phía sau và gây lỗi dominance.

### Giải thích nhóm case Sum

`Sum(int left, int right)` bóc tách hai component nguyên từ record. Guard:

```java
case Sum(int left, int right) when left < 0 || right < 0 ->
    System.out.println("SUM_INVALID");
```

lọc phép cộng có số âm theo quy tắc minh họa. Với dữ liệu còn lại, case `Sum(int left, int right)` không guard in kết quả. Đây chỉ là quy tắc nghiệp vụ giả định: số âm hoàn toàn hợp lệ trong phép cộng toán học; hệ thống thật cần định nghĩa rõ dữ liệu nào bị coi là không hợp lệ.

### Giải thích record pattern lồng nhau

`Envelope(Text(String content), String destination)` chỉ khớp khi component `text` chứa một **record `Text` khác null**, từ đó lấy trực tiếp `content`. Nếu `text == null` thì nested `Text(...)` không khớp.

Nhánh `Envelope(var text, var destination)` đứng sau sẽ nhận `Envelope` chưa khớp nhánh cụ thể, ví dụ `new Envelope(null, "ops")`. Tại đây `var text` có thể ràng buộc component null: record pattern không tự yêu cầu mọi component tham chiếu khác null.

### Giải thích case null

`case null` của `handle` nhận selector `message == null` và in `NULL`; `case null` của `inspect` nhận `value == null` và in `OBJECT_NULL`. Không có nhánh này, một `switch` tham chiếu null thường ném `NullPointerException`, ngay cả khi có `default`.

## 5. Guard when và cách xét thứ tự case

Guard dùng để thêm điều kiện sau khi Java đã khớp pattern. Ví dụ:

```java
case String text when text.length() > 10 ->
    System.out.println("Long text");

case String text ->
    System.out.println("Short or medium text");
```

Đây là hai nhánh minh họa trong cùng một `switch`. Với selector kiểu `String` dài hơn 10 ký tự, case đầu chạy; các chuỗi khác được case thứ hai tiếp nhận. Nếu giá trị selector không phải `String`, cả hai case không khớp.

**Thứ tự quan trọng:**
1. Pattern của case được kiểm tra.
2. Nếu pattern khớp, guard `when` (nếu có) được đánh giá.
3. Nếu guard đúng, thực hiện nhánh được chọn; nếu guard sai, tiếp tục tìm case phù hợp.
4. Một case tổng quát không guard có thể làm những case cụ thể phía sau bị dominated.

**Ví dụ sai (cố ý không biên dịch):**

```java
case String text ->
    System.out.println("Any string");

case String text when text.isBlank() ->
    System.out.println("Blank string");
```

Case đầu đã bao phủ mọi `String` khác null nên case sau không thể chọn. Sửa bằng cách đặt case có guard trước, hoặc tách logic bằng `if` trong một case nếu điều đó dễ đọc hơn.

Tương tự, đặt `case Message msg` trước `case Sum(int a, int b)` là sai nếu selector thuộc cùng cây kiểu: case cha bao phủ `Sum` và khiến case lá không thể tới được.

**Quy tắc:** Ưu tiên pattern cụ thể, pattern có guard cần thiết, rồi mới tới case tổng quát hoặc fallback.

## 6. Exhaustiveness: một số switch statement phải bao phủ hết kiểu

Điểm dễ nhầm là **switch statement có pattern trong Java 21 không hoàn toàn giống switch statement truyền thống**. Một **enhanced switch statement** (ví dụ có `case` pattern hoặc `case null`) phải có nhánh bao phủ tất cả giá trị selector phù hợp, tương tự switch expression.

Với `handle(Message message)`, trình biên dịch biết `Message` là `sealed` và chỉ có ba subtype: `Text`, `Sum`, `Envelope`. Ba nhánh record pattern không guard ở cuối mỗi nhóm bao phủ các subtype này, và `case null` xử lý đầu vào null. Vì vậy `switch` này biên dịch **không cần `default`**.

Ngược lại, `inspect(Object value)` cần `default`: đầu vào có thể là `Double`, `Boolean` hay bất kỳ đối tượng nào khác ngoài `String`/`Integer`. Chỉ có hai case type pattern là không exhaustive.

### Khi thêm một subtype mới

Nếu thêm `record Alert(String title) implements Message {}`, phải bổ sung `Alert` vào `permits` của `Message`. Khi biên dịch lại, `handle` không còn exhaustive nếu chưa có nhánh xử lý `Alert`. Trình biên dịch giúp phát hiện nơi còn thiếu logic khi cây kiểu đóng kín được mở rộng.

Nếu hierarchy có một nhánh `non-sealed`, trình biên dịch không thể chỉ dựa vào danh sách các lớp con hiện biết để kết luận nhánh đó đã được bao phủ. Bạn thường cần một type pattern nhận toàn bộ nhánh mở hoặc `default` thích hợp.

Không thêm `default` chỉ để che đi yêu cầu cập nhật handler khi codebase muốn kiểm tra đủ mọi subtype được cho phép; việc lựa chọn phụ thuộc chủ đích thiết kế API.

## 7. Phạm vi biến và các quy tắc khi dùng case pattern

### 7.1. Biến pattern chỉ có giá trị ở nhánh khớp

Trong `case String text -> ...`, biến `text` đã được ràng buộc và có thể truy cập trong phần thân case; trong `case ... when ...`, biến cũng được dùng trong guard. Nó không tự có phạm vi trong các case khác hoặc sau `switch`.

Các case riêng biệt có thể đặt tên biến pattern giống nhau, như `case Text(String content)` lặp lại trong ví dụ, bởi chúng thuộc các nhánh khác nhau.

### 7.2. Không nhầm selector null với component null

- Với `switch (value)`, `case null` xử lý **chính selector** null.
- Với `case Envelope(Text(String content), ...)`, nếu component `text` null thì record pattern lồng không khớp.
- Với `case Text(String content)`, component `content` có kiểu khai báo `String` và pattern unconditional, nên `content` vẫn có thể null.
- Pattern của record ngoài cùng không khớp selector null; đừng trông chờ `case Text(var content)` xử lý `message == null`.

Nếu thuộc tính bắt buộc khác null, nên kiểm soát khi tạo record (ví dụ dùng `Objects.requireNonNull` trong compact constructor) hoặc kiểm tra ở nơi phù hợp; pattern matching không thay mọi bất biến dữ liệu.

### 7.3. Không trộn arrow và colon trong cùng switch block

Một `switch` dùng toàn bộ `->` hoặc toàn bộ `:`. Ví dụ `handle` dùng arrow; `inspect` dùng colon. Bạn có thể có nhiều switch theo hai phong cách khác nhau trong cùng class, nhưng không trộn hai dạng nhãn trong **một** switch block.

### 7.4. Cẩn trọng với fall-through trong switch statement dạng colon

Với nhãn `case ...:`, nếu bỏ `break`, điều khiển luồng có thể tiếp tục chạy vào phần tiếp theo như switch truyền thống. Tuy nhiên, Java giới hạn fall-through khi một nhánh mới dùng pattern variable; không thể giả định có thể đi qua nhãn `case String text:` mà không thiết lập biến `text`.

Một lỗi thường gặp khi chuyển từ switch hằng sang switch pattern là giữ nguyên fall-through mà không xét lại phạm vi biến. Dạng `->` tránh vấn đề này và thường làm logic rõ hơn.

### 7.5. Side effects và thứ tự xét case

Guard `when` được dùng để **quyết định nhánh xử lý**, nên giữ các phép kiểm tra dễ hiểu, không có side effect không cần thiết. Không nên giả định Java sẽ gọi guard của tất cả case; chỉ case có pattern khớp mới cần đánh giá guard. Khi ghi log hay thay đổi trạng thái, đặt hành động trong phần thân case phù hợp.

Không lặp việc gọi accessor đắt đỏ hay có side effect trong nhiều guard nếu có thể tách thành phương thức phân loại nhỏ hoặc dữ liệu đã chuẩn hóa.

## 8. Lỗi phổ biến và cách sửa

| Lỗi | Kết quả | Cách sửa |
| --- | --- | --- |
| Dùng `case String s -> "text";` như statement | Biểu thức chuỗi không phải hành động hợp lệ của switch statement | Dùng phương thức có side effect hoặc chuyển sang switch expression |
| Đặt pattern tổng quát trước pattern cụ thể | Case phía sau bị dominated | Đặt case có guard/cấu trúc cụ thể lên trước |
| Chỉ có `case String` và `case Integer` trên `Object` | Enhanced switch statement không exhaustive | Thêm `default` hoặc case bao phủ còn lại |
| Nghĩ `default` sẽ tự xử lý null | Selector null có thể ném `NullPointerException` | Dùng `case null` khi muốn xử lý riêng |
| Gọi `content.isBlank()` trước khi xử lý component null | Có thể ném `NullPointerException` | Xử lý null trước hoặc dùng guard an toàn null |
| Lạm dụng fall-through với colon labels | Dễ rơi vào luồng có biến pattern chưa ràng buộc; có thể lỗi biên dịch | Dùng `break` hoặc arrow syntax |
| Trộn `->` với `:` trong một switch block | Lỗi cú pháp/kiểm tra trình biên dịch | Chọn một kiểu nhãn cho toàn block |
| Dùng `yield` để trả kết quả từ switch statement | Nhầm cơ chế switch expression | Dùng switch expression khi cần giá trị |
| Dùng record pattern cho class thường | Record deconstruction chỉ áp dụng cho record | Dùng type pattern và phương thức của class |
| Không xử lý subtype mới của sealed hierarchy | Switch thiếu bao phủ sau cập nhật type | Thêm case và biên dịch lại |

## 9. Khi nào nên dùng pattern switch statement?

**Phù hợp** khi ứng dụng nhận các thông điệp nhiều kiểu và cần thực hiện tác vụ theo từng biến thể: xử lý event, dispatch command, ghi log, cập nhật thống kê, kiểm tra hoặc chuyển tiếp thông tin. Các `case` giúp đọc nhanh từng điều kiện kiểu và dữ liệu.

**Nên cân nhắc phương án khác** khi:
- Chỉ có một kiểm tra `instanceof` đơn giản: `if` có thể ngắn và rõ hơn.
- Mục tiêu là tính một giá trị: `switch expression` hoặc một phương thức trả về kết quả có thể tự nhiên hơn.
- Hành vi là trách nhiệm nội tại của từng subtype và có thể biểu đạt bằng phương thức đa hình chung của interface: virtual dispatch có thể phù hợp hơn.
- Một case quá dài hoặc chứa nhiều guard phức tạp: tách xử lý thành phương thức nhỏ, giữ switch làm nơi phân luồng.

Pattern matching chủ yếu cải thiện **cách biểu đạt lựa chọn kiểu và cấu trúc**, không bảo đảm nhanh hơn mọi chuỗi `if/else`. Với yêu cầu hiệu năng, hãy đo trên dữ liệu thật thay vì suy ra từ cú pháp.

## 10. Bài tập tự kiểm tra

**Bài tập 1 — Thêm pattern và guard.** Bổ sung `record Product(String sku, int quantity) implements Message {}` vào sealed hierarchy và thêm `Product` vào `permits` của `Message`. Viết case in `LOW_STOCK` khi `quantity < 5` và case tổng quát in `STOCK_OK` cho số lượng còn lại. Đặt case có guard trước case tổng quát; biên dịch để kiểm chứng switch exhaustive.

**Bài tập 2 — Thêm null handling.** Thử truyền `new Envelope(new Text(null), "ops")`. Nhánh nested pattern trong ví dụ vẫn khớp vì component `Text.content` có thể null, nên nội dung in ra chứa chuỗi `null` khi nối chuỗi. Nếu nghiệp vụ không cho phép nội dung null, hãy thêm một nhánh có guard trước case gửi thông thường hoặc kiểm tra tại lúc tạo `Text`.

**Bài tập 3 — Chuyển colon sang arrow.** Viết lại `inspect` bằng toàn bộ nhánh `case ... ->`. Giữ nguyên đủ 4 trường hợp `String`, `Integer`, `null`, `default` và xác nhận stdout không đổi. Khi dùng arrow, bỏ những `break` không cần thiết.

**Bài tập 4 — Lỗi cố ý.** Đặt một case tổng quát `case Message msg -> System.out.println("MESSAGE");` lên đầu `handle`, rồi biên dịch. Xem lỗi dominance đối với các case chuyên biệt phía sau; sửa bằng cách đặt nhánh chung cuối hoặc bỏ nó khi các subtype đã được bao phủ.

**Ghi nhớ:** Pattern trong **`switch statement`** cho phép phân nhánh theo kiểu và cấu trúc dữ liệu trong khi thực hiện hành động. Java 21 hỗ trợ type pattern, record pattern và guard `when`; ưu tiên case cụ thể trước case tổng quát, kiểm tra exhaustiveness, xử lý selector và component null riêng biệt, và dùng `->` khi không có nhu cầu fall-through.

## Tài liệu tham khảo

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java Language Specification SE 21, `14.11 — The switch Statement: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
