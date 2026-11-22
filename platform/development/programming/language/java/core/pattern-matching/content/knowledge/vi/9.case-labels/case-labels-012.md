# Chọn cấu trúc `case` dễ kiểm thử trong Java Pattern Matching

**Chủ đề:** Java Core Pattern Matching → Case label  
**Phiên bản:** Java 21 trở lên. Pattern matching cho `switch` chính thức từ Java 21 (JEP 441); các ví dụ trong bài không cần `--enable-preview`.

## 1. Mục tiêu: viết `case` để dễ kiểm tra từng hành vi

Một `switch` có type pattern giải quyết bài toán phân loại nhiều dạng dữ liệu: `case String s`, `case Number n`, `case SomeRecord r`, v.v. Nhưng **đúng cú pháp không đồng nghĩa với dễ kiểm thử**. Một `switch` sẽ khó test khi nhiều nhánh chồng lấn, guard chứa tác dụng phụ, dữ liệu `null` bị xử lý ngầm, hoặc nhánh vừa quyết định vừa gọi database/network.

Một cấu trúc tốt tạo được **ánh xạ rõ ràng từ đầu vào tới kết quả**. Với cùng một giá trị đầu vào, hàm phân loại trả một kết quả quan sát được, ổn định; test có thể gọi riêng hàm đó mà không cần khởi tạo web server, mock database hay chờ console output.

Sau bài học, bạn có thể:

- Chọn giữa `switch` expression dùng `->` và `switch` statement dùng `case ...:`.
- Thiết kế `case` theo nhóm kiểu, điều kiện `when`, nhánh tổng quát và biên `null`.
- Tránh nhánh bị **dominance**, kiểm soát **exhaustiveness** với sealed hierarchy.
- Biến bảng các nhánh thành test có expected result cụ thể, kể cả những trường hợp sát ranh giới.
- Tách phân loại khỏi I/O và các tác dụng phụ để test độc lập.

## 2. Ưu tiên `switch` expression trả một kết quả rõ ràng

Khi mục tiêu là **biến một input thành một output**, `switch` expression thường dễ kiểm thử hơn một `switch` statement dài làm thay đổi biến cục bộ rồi gọi nhiều dịch vụ.

Ví dụ với đầu vào kiểu `Object`:

```java
static String describe(Object input) {
    return switch (input) {
        case null -> "MISSING";
        case String text when text.isBlank() -> "BLANK";
        case String text -> "TEXT:" + text.length();
        case Integer number -> "INT:" + number;
        default -> "OTHER";
    };
}
```

Mỗi nhãn `case` biểu diễn một điều kiện chọn nhánh và **một giá trị trả về**. Chỉ cần gọi `describe(input)` và so sánh chuỗi thực tế với chuỗi kỳ vọng là đã có một test hữu ích.

Đặc điểm giúp test đơn giản:

1. `input` là tham số duy nhất, không phụ thuộc trạng thái toàn cục.
2. `switch` được đánh giá để tạo một giá trị; không có biến `result` bị cập nhật từ nhiều vị trí.
3. Mỗi nhánh có kết quả phân biệt được, tránh việc nhiều ca thử “đều trả cùng một giá trị” khiến test khó phát hiện lỗi thứ tự nhánh.
4. Nhánh `case null` chỉ ra chính sách xử lý `null` tường minh.
5. `default` bao phủ những kiểu đầu vào không được liệt kê.

Nếu một nhánh cần nhiều câu lệnh để xây dựng kết quả, dùng block với `yield`:

```java
case String text -> {
    int length = text.length();
    yield "TEXT:" + length;
}
```

Đoạn trên là **một nhánh minh họa**, không phải chương trình chạy độc lập. Trong `switch` expression, `yield` cấp giá trị cho chính expression; không dùng `break` kèm một giá trị để thay `yield`.

### Khi nào dùng `switch` statement?

`switch` statement thích hợp khi thao tác thực sự là điều khiển luồng hoặc thực hiện các hành động, nhưng nó thường phải được test bằng việc quan sát tác dụng phụ. Với những bài toán phân loại, nên cân nhắc tách làm hai bước:

```java
Decision decision = classify(event); // Hàm thuần, dễ unit test.
applyDecision(decision);             // I/O hoặc hành động nghiệp vụ riêng.
```

Trong đó `Decision` là kết quả dữ liệu; `applyDecision` chỉ là **minh họa kiến trúc**, cần được định nghĩa bởi ứng dụng thực tế, không có trong chương trình chạy mẫu bên dưới. Cách tách này không cấm `switch` statement, mà giúp bạn chọn hình thức khớp với mục đích cần kiểm thử.

## 3. Thiết kế nhánh theo kiểu: cụ thể trước, tổng quát sau

Type pattern `case Type variable` kiểm tra kiểu và cung cấp biến đã gắn kiểu cho nhánh đó. Quy tắc **dominance** ngăn những nhánh bị che hoàn toàn bởi các nhánh trước.

Ví dụ **không biên dịch**:

```java
// Một phần của switch(Object input), KHÔNG hợp lệ vì dominance:
case Number n -> "NUMBER";
case Integer i -> "INTEGER";
```

Vì `Integer` là một `Number`, nhánh `Integer` sau không bao giờ có cơ hội được chọn. Cách sửa:

```java
case Integer i -> "INTEGER";
case Number n -> "NUMBER";
```

Trong test, nên có ít nhất một `Integer` và một `Double` để chứng minh hai nhánh có thể được chọn, chứ không chỉ kiểm tra một `Number` bất kỳ.

Cấu trúc dễ đọc là:

- **Nhánh đặc biệt:** `case Type x when condition` cho dữ liệu lỗi hoặc biên.
- **Nhánh type tổng quát:** `case Type x` để bao phủ phần còn lại của kiểu đó.
- **Nhánh kiểu cha:** ví dụ `case Number n` sau các kiểu số chuyên biệt.
- **Chính sách còn lại:** `default` hoặc các type pattern của một sealed hierarchy.

Các bullet trên là thứ tự thiết kế, không phải yêu cầu mọi `switch` đều cần tất cả các dạng nhãn.

## 4. Guard `when`: chia miền dữ liệu thành các nhóm có thể test

Guard `when` chỉ được đánh giá **sau khi type pattern khớp**. Nên dùng guard ngắn, không có tác dụng phụ và dễ tạo dữ liệu kiểm tra.

Ví dụ:

```java
case Integer n when n < 0 -> "NEGATIVE";
case Integer n when n == 0 -> "ZERO";
case Integer n -> "POSITIVE";
```

Ba nhánh này chia các giá trị `Integer` thành ba miền rõ ràng. Bộ test tự nhiên là **-1, 0, 1**; có thể bổ sung `Integer.MIN_VALUE` và `Integer.MAX_VALUE` nếu nghiệp vụ xử lý số ở biên.

Lưu ý: `case Integer n` cuối phải đứng **sau** hai nhánh có guard để không che chúng. Dù ba miền số nguyên không giao nhau, đặt nhánh có `when` theo trình tự dễ đọc giúp người kiểm thử nhìn thấy logic phân chia.

Tránh guard vừa kiểm tra vừa thực hiện I/O:

```java
// Ví dụ cần tránh trong logic phân loại:
// case Order o when repository.save(o) -> ...
```

Nếu guard gây thay đổi dữ liệu, test phải kiểm soát trạng thái ngoài, và việc đổi thứ tự nhánh có thể làm thay đổi các tác dụng phụ. Thay bằng điều kiện thuần như `o.total() > 0` và chuyển thao tác lưu dữ liệu sang tầng xử lý sau khi `switch` trả quyết định.

Với guard phức tạp, có thể dùng một helper thuần `isEligible(order)`. Helper vẫn phải có kết quả ổn định và được test riêng. **Không viết `when` như một ngôn ngữ truy vấn phức tạp**: điều kiện càng ngắn, mỗi case càng dễ cô lập.

## 5. `null` phải là một ca kiểm thử riêng

Type pattern `case String s` không khớp khi selector là `null`. Trong pattern `switch` Java 21, nếu không có nhãn xử lý `null` thích hợp, selector `null` thường làm `switch` ném `NullPointerException` trước khi vào các nhánh thông thường. **`default` đứng riêng không tự bắt `null`**.

Hai chính sách đều có thể đúng nếu được thiết kế có chủ ý:

```java
case null -> new Decision("MISSING", "null input");
```

Hoặc kiểm tra `null` trước khi gọi `switch` và từ chối đầu vào theo hợp đồng API. Lựa chọn phụ thuộc yêu cầu, nhưng test phải nói rõ `null` là hợp lệ hay là lỗi.

Với record object, cần phân biệt **record cấp ngoài bằng `null`** với **component bên trong bằng `null`**. Chẳng hạn `new TextEvent(null)` vẫn là một object `TextEvent` và khớp `case TextEvent t`; nhưng `t.text()` trả `null`. Đặt nhánh bảo vệ component trước guard gọi `isBlank()`:

```java
case TextEvent t when t.text() == null -> "MISSING_TEXT";
case TextEvent t when t.text().isBlank() -> "BLANK_TEXT";
case TextEvent t -> "TEXT";
```

Đây là các **nhánh minh họa của một `switch`**; định nghĩa `TextEvent` sẽ xuất hiện trong ví dụ hoàn chỉnh. Nếu đảo nhánh có `isBlank()` lên trước, input `new TextEvent(null)` có thể ném `NullPointerException`. Test cho input này sẽ phát hiện lỗi ưu tiên nhánh.

## 6. Exhaustiveness: dùng kiểu sealed khi tập biến thể là đóng

Đối với API có một tập sự kiện cố định, `sealed interface` giúp compiler biết những subtype được phép và kiểm tra `switch` expression có bao phủ đủ hay chưa.

```java
sealed interface Event permits TextEvent, PaymentEvent, PingEvent {}

record TextEvent(String text) implements Event {}
record PaymentEvent(int cents) implements Event {}
record PingEvent() implements Event {}
```

Một `switch` trên `Event` có nhánh không guard cho **từng subtype được phép** sẽ exhaustiveness mà không bắt buộc có `default`. Các nhánh `when` chia nhỏ một subtype theo điều kiện; vì guard có thể là `false`, chúng **không thay thế** nhánh bắt trọn subtype còn lại.

Lợi ích cho bảo trì và kiểm thử: nếu sau này thêm một subtype vào `permits` và biên dịch lại, compiler có thể yêu cầu cập nhật `switch` đang thiếu nhánh. Nếu bạn để `default -> "UNKNOWN"` vô điều kiện, một subtype mới có thể bị hấp thụ âm thầm và test cũ không nhận ra chưa có hành vi nghiệp vụ riêng.

Vì vậy:

- Với **tập kiểu mở** như `Object`, `default` thường là cách cần thiết để biểu thức đầy đủ.
- Với **sealed hierarchy đóng**, hãy cân nhắc liệt kê đủ subtype và để compiler giúp bắt trường hợp mới, đồng thời xử lý `null` tường minh theo hợp đồng.
- Đừng loại `default` một cách máy móc khi yêu cầu thực sự cần chính sách fallback, hoặc khi compiler không thể chứng minh đầy đủ.

Lưu ý: exhaustiveness của type pattern và chính sách đối với selector `null` là hai vấn đề khác nhau. Một `switch` exhaustive theo các subtype vẫn có thể ném `NullPointerException` nếu không thiết kế nhánh cho `null`.

## 7. Chương trình Java 21 hoàn chỉnh: một hàm, tám test minh bạch

Bài toán: phân loại ba dạng sự kiện `TextEvent`, `PaymentEvent`, `PingEvent`, và cả input `null`. Ta trả về `Decision` là record bất biến có hai trường `code` và `detail`, để test so sánh chính xác cả hai.

**Tạo tệp `TestableCaseDesignDemo.java`:**

```java
public class TestableCaseDesignDemo {
    sealed interface Event permits TextEvent, PaymentEvent, PingEvent {}

    record TextEvent(String text) implements Event {}
    record PaymentEvent(int cents) implements Event {}
    record PingEvent() implements Event {}

    record Decision(String code, String detail) {}

    static Decision classify(Event event) {
        return switch (event) {
            case null -> new Decision("MISSING_EVENT", "null");

            case TextEvent t when t.text() == null ->
                    new Decision("MISSING_TEXT", "null");
            case TextEvent t when t.text().isBlank() ->
                    new Decision("BLANK_TEXT", "blank");
            case TextEvent t ->
                    new Decision("TEXT_LENGTH",
                            String.valueOf(t.text().length()));

            case PaymentEvent p when p.cents() < 0 ->
                    new Decision("NEGATIVE_PAYMENT",
                            String.valueOf(p.cents()));
            case PaymentEvent p when p.cents() == 0 ->
                    new Decision("ZERO_PAYMENT", "0");
            case PaymentEvent p ->
                    new Decision("POSITIVE_PAYMENT",
                            String.valueOf(p.cents()));

            case PingEvent p -> new Decision("PING", "pong");
        };
    }

    static void check(String label, Event input, Decision expected) {
        Decision actual = classify(input);
        if (!expected.equals(actual)) {
            throw new AssertionError(label
                    + ": expected " + expected + ", got " + actual);
        }
        System.out.println(label + " => "
                + actual.code() + ":" + actual.detail());
    }

    public static void main(String[] args) {
        check("null event", null,
                new Decision("MISSING_EVENT", "null"));
        check("null text", new TextEvent(null),
                new Decision("MISSING_TEXT", "null"));
        check("blank text", new TextEvent("   "),
                new Decision("BLANK_TEXT", "blank"));
        check("text", new TextEvent("Java"),
                new Decision("TEXT_LENGTH", "4"));
        check("negative", new PaymentEvent(-5),
                new Decision("NEGATIVE_PAYMENT", "-5"));
        check("zero", new PaymentEvent(0),
                new Decision("ZERO_PAYMENT", "0"));
        check("positive", new PaymentEvent(150),
                new Decision("POSITIVE_PAYMENT", "150"));
        check("ping", new PingEvent(),
                new Decision("PING", "pong"));

        System.out.println("ALL TESTS PASSED");
    }
}
```

Chạy với JDK 21+:

```bash
javac --release 21 TestableCaseDesignDemo.java
java TestableCaseDesignDemo
```

**Standard output chính xác:**

```text
null event => MISSING_EVENT:null
null text => MISSING_TEXT:null
blank text => BLANK_TEXT:blank
text => TEXT_LENGTH:4
negative => NEGATIVE_PAYMENT:-5
zero => ZERO_PAYMENT:0
positive => POSITIVE_PAYMENT:150
ping => PING:pong
ALL TESTS PASSED
```

Phương thức `check` sử dụng `Decision.equals` do record tự sinh để so sánh **nội dung hai component**, không chỉ kiểm tra output hiển thị. Nếu một nhánh trả sai `code` hoặc `detail`, chương trình ném `AssertionError`, nên **không in** `ALL TESTS PASSED`. Đây là bộ self-test chạy được chỉ với JDK; không cần thư viện JUnit bên ngoài.

### Vì sao cấu trúc này dễ kiểm thử?

1. **Mỗi case có một ý định:** trường hợp thiếu event, thiếu text, text blank, text hợp lệ, payment âm, payment bằng 0, payment dương, ping.
2. **Guard có tính xác định:** gọi accessor của record và so sánh, không ghi log, gửi HTTP hay sửa biến bên ngoài.
3. **Có nhánh không guard** cho từng subtype: `TextEvent`, `PaymentEvent`, `PingEvent`; compiler có thể chứng minh `switch` đủ cho sealed `Event`.
4. **Không dùng `default` vô cớ:** thêm subtype mới và biên dịch lại buộc người phát triển xem xét hành vi tương ứng.
5. **`null` được phân biệt ở hai cấp:** selector null qua `case null`; text component null qua guard riêng.
6. **Kết quả tường minh và bất biến:** `Decision` giúp test so sánh một giá trị, không phải bắt console output hay mock phụ thuộc.
7. **Test vừa kiểm tra logic vừa kiểm tra thứ tự:** nếu nhánh TextEvent chung bị đặt sớm hơn guard, chương trình bị lỗi dominance; nếu đảo hai guard text, case null text sẽ có thể bị NPE.

## 8. Ma trận kiểm thử: bao phủ nhánh và biên

Bảng dưới đây biến các case thành điều kiện quan sát được. Nó giúp review nhanh xem bộ test còn thiếu gì.

| Đầu vào | Nhánh mong đợi | `Decision.code` | `Decision.detail` |
| --- | --- | --- | --- |
| `null` | `case null` | `MISSING_EVENT` | `null` |
| `new TextEvent(null)` | TextEvent có text null | `MISSING_TEXT` | `null` |
| `new TextEvent("   ")` | TextEvent có text blank | `BLANK_TEXT` | `blank` |
| `new TextEvent("Java")` | TextEvent còn lại | `TEXT_LENGTH` | `4` |
| `new PaymentEvent(-5)` | Payment âm | `NEGATIVE_PAYMENT` | `-5` |
| `new PaymentEvent(0)` | Payment bằng 0 | `ZERO_PAYMENT` | `0` |
| `new PaymentEvent(150)` | Payment dương | `POSITIVE_PAYMENT` | `150` |
| `new PingEvent()` | PingEvent | `PING` | `pong` |

Các ca bổ sung có giá trị:

- `new TextEvent("")`: xác nhận chuỗi rỗng cũng là blank.
- `new TextEvent("\t")`: xác nhận ký tự tab cũng có thể được `isBlank()` nhận diện.
- `new TextEvent("A")`: độ dài 1.
- `new PaymentEvent(-1)`, `new PaymentEvent(1)`: ranh giới sát 0.
- `new PaymentEvent(Integer.MIN_VALUE)` và `new PaymentEvent(Integer.MAX_VALUE)`: nếu phần xử lý số có chuyển đổi/tính toán nhạy cảm.
- Test riêng việc truyền subtype mới khi thay đổi hierarchy, để kiểm soát tính đầy đủ của `switch` qua biên dịch.

**Bao phủ nhánh** là điểm khởi đầu, không phải bằng chứng toàn bộ logic đều đúng. Một guard như `n >= 0` có thể chạy với nhiều giá trị nhưng vẫn cần thử `-1`, `0` và `1` để phát hiện lỗi dấu so sánh. Tương tự, test cho chuỗi blank và nonblank giúp phát hiện sai sót trong thứ tự nhánh `when`.

## 9. Chọn between `case ->` và `case :` theo tính kiểm thử

Java 21 vẫn hỗ trợ `switch` statement với các nhãn colon:

```java
static String legacyStyle(Object input) {
    String result;
    switch (input) {
        case null:
            result = "MISSING";
            break;
        case String text:
            result = "TEXT:" + text;
            break;
        default:
            result = "OTHER";
            break;
    }
    return result;
}
```

Đây là **phương thức minh họa** hợp lệ nếu đặt trong một class Java 21. Nó cũng có thể kiểm thử bằng expected return value. Tuy nhiên, khi có nhiều nhánh, việc quản lý `result`, `break`, fall-through và phạm vi pattern variable thường làm code dài hơn. Với bài toán tính toán một kết quả, `switch` expression và arrow rules thường rõ ý định hơn.

Nếu phải dùng colon để tương thích code cũ, vẫn áp dụng những tiêu chí tương tự: mỗi nhánh có kết quả/hiệu ứng rõ, `null` xử lý minh bạch, không fall-through ngoài ý muốn, và test bao phủ các lối ra của từng nhánh. Không cần chuyển toàn bộ code sang expression chỉ để thỏa mãn một phong cách nhất định.

## 10. Tổ chức code thực tế để giữ test độc lập

Một cách tách trách nhiệm đơn giản:

```text
Dữ liệu đầu vào
    |
    v
classify(input)     <-- unit test bằng input và expected Decision
    |
    v
Decision            <-- dữ liệu bất biến, không I/O
    |
    v
execute(decision)   <-- tích hợp với DB, HTTP, logger; integration test riêng
```

Ở đây `execute` biểu thị tầng thực thi do ứng dụng tự xây dựng, không phải API Java có sẵn. Việc tách tầng giúp unit test không phụ thuộc tài nguyên ngoài, và các test tích hợp tập trung vào hành động thật.

Một số nguyên tắc:

- **Input rõ ràng:** ưu tiên interface/record đại diện cho miền nghiệp vụ thay vì một `Object` chứa đủ thứ không có hợp đồng.
- **Output giàu ngữ nghĩa:** trả enum, record, sealed result hoặc giá trị rõ ràng thay vì magic number khó kiểm tra.
- **Ít nhánh chồng lấn:** guard đặc biệt trước nhánh type bao quát; thứ tự phản ánh ưu tiên nghiệp vụ.
- **Bất biến và hàm thuần:** không thay đổi trạng thái trong guard hoặc nhánh phân loại; gọi tác dụng phụ sau khi quyết định.
- **Không nuốt lỗi bất ngờ:** nếu đầu vào lạ phải báo lỗi, hãy thiết kế nhánh trả kết quả lỗi hoặc ném ngoại lệ có chủ đích, rồi test hành vi đó.
- **Refactor khi cần:** nhiều guard dùng chung logic phức tạp có thể tách helper thuần và test riêng, nhưng tránh tách mỗi `case` một hàm chỉ làm code phân tán hơn.

## 11. Những lỗi khiến `case` khó kiểm thử

| Thiết kế có vấn đề | Vì sao khó kiểm thử | Cách cải thiện |
| --- | --- | --- |
| Mỗi case tự gọi database hoặc gửi HTTP | Test phụ thuộc tài nguyên và thứ tự tác dụng phụ | Trả quyết định; đưa I/O ra lớp khác |
| Guard vừa kiểm tra vừa thay đổi dữ liệu | Cùng input có thể cho kết quả khác theo trạng thái ngoài | Dùng helper thuần, không side effect |
| `case` bao quát đặt trước `case` cụ thể | Nhánh cụ thể bị dominance, có thể không biên dịch | Đặt nhánh cụ thể/guard trước |
| Nhiều guard nối nhau nhưng không có nhánh type cuối | Dễ thiếu kết quả khi mọi guard đều false | Có nhánh type không guard hoặc fallback hợp lệ |
| `default` trả một giá trị thành công cho mọi lỗi | Dễ che dữ liệu sai hoặc subtype mới | Định nghĩa lỗi/fallback có chủ ý; tận dụng sealed khi phù hợp |
| Không test `null` | `switch` có thể ném NPE hoặc component null bị bỏ sót | Test cả selector null và component null |
| Chỉ test “happy path” | Không kiểm tra hành vi biên `< 0`, `== 0`, `> 0` | Ma trận case + boundary values |
| Dùng `case String s && guard` | Không phải cú pháp Java 21 ổn định | Dùng `case String s when guard` |
| Chỉ kiểm tra console output bằng mắt | Khó tự động hóa, dễ bỏ qua sai khác | So sánh `Decision` hoặc return value bằng assertion |
| `switch` quá dài với nhiều tầng xử lý | Khó xác định nhánh quyết định hành vi gì | Phân loại trước, xử lý sau; dùng helper có tên mô tả |

## 12. Bài tập luyện thiết kế và kiểm thử

1. Đổi `TextEvent` thành `record TextEvent(String text, boolean urgent)`. Bổ sung nhánh riêng cho `urgent` khi text hợp lệ; viết test cho cả urgent và non-urgent. Bảo đảm guard `text == null` được kiểm tra trước khi gọi phương thức trên text.
2. Thêm `record CancelEvent(String reason) implements Event {}` vào danh sách `permits`, biên dịch lại và quan sát yêu cầu exhaustiveness; bổ sung nhánh `case CancelEvent c` và test input mới.
3. Thay kết quả chuỗi `Decision.code` bằng một `enum`. Chứng minh test vẫn so sánh được đầu ra một cách ổn định.
4. Viết test cho `-1`, `0`, `1`, `Integer.MIN_VALUE`, `Integer.MAX_VALUE` để kiểm tra phân loại `PaymentEvent`. Giải thích vì sao ba nhánh `when` phải có một nhánh Payment không guard ở cuối.
5. Refactor hàm phân loại để một phần xử lý sử dụng block `-> { ... yield ...; }` mà không có I/O; giữ nguyên toàn bộ expected result.
6. Viết phiên bản `switch` statement dùng colon, `break` và biến `result`; so sánh số điểm phải quản lý luồng thực thi với phiên bản `switch` expression.
7. Cố ý đặt nhánh `case TextEvent t` trước nhánh có `when` rồi biên dịch. Đọc lỗi dominance và sửa lại; giải thích tại sao đây là lỗi compiler bắt được, khác với logic phân loại sai nhưng vẫn có thể biên dịch.
8. Tạo một phiên bản dùng `Object` và `default`; kiểm tra trường hợp subtype lạ. So sánh với sealed hierarchy không có `default` về khả năng compiler nhắc cập nhật nhánh.

**Tiêu chí hoàn thành:** thiết kế được `switch` Java 21 có các `case` phân chia rõ, guard an toàn, chính sách `null` tường minh, exhaustiveness hợp lý, mỗi nhánh có test quan sát được, và logic phân loại không bị trộn với tác dụng phụ bên ngoài.

**Nguồn chính thức:**

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — Switch Statements (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21 — Switch Expressions (§15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
