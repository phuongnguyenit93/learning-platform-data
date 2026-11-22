# Review khả năng đọc của lời giải Java Pattern Matching

## 1. Mục tiêu của bài thực hành tổng hợp

Sau khi hoàn thành một bài tập `instanceof`, record pattern hoặc `switch` trên `sealed` hierarchy, câu hỏi tiếp theo không chỉ là “mã có biên dịch và cho ra kết quả đúng không?”. Người bảo trì còn cần xác định: **liệu người khác có thể hiểu chính xác các nhánh, điều kiện và hợp đồng null của lời giải mà không phải chạy thử từng dòng?**

Một lời giải dễ đọc thường có những đặc điểm:

1. Người đọc nhận biết nhanh **kiểu dữ liệu/domain** đang được xử lý.
2. Mỗi `case` thể hiện một ý nghĩa nghiệp vụ riêng; không có trường hợp che khuất hoặc trùng lặp khó giải thích.
3. Tên pattern variable cho thấy **vai trò của giá trị**, không chỉ để code ngắn.
4. Record pattern chỉ phân rã sâu tới mức thực sự cần; những dữ liệu quan trọng vẫn có ngữ cảnh.
5. `when` mô tả điều kiện ngắn, thuần, rõ và có nhánh cho trường hợp guard không thỏa.
6. Chính sách với **selector null**, **record component null** và ngoại lệ là nhất quán, được kiểm thử.
7. `switch expression` có kiểu kết quả dễ hiểu; `yield` chỉ xuất hiện khi block cần nhiều câu lệnh.
8. Nếu refactor cho dễ đọc, **hành vi quan sát được phải được giữ nguyên**, trừ khi thay đổi hành vi là một yêu cầu tách biệt và được kiểm thử rõ.

**Nguyên tắc chính:** *Dễ đọc không đồng nghĩa ít dòng*. Một lời giải rút từ mười case thành một case `Object o -> ...` có thể ngắn hơn nhưng đánh mất thông tin về subtype. Ngược lại, phân rã mọi record component vào tên biến dù không dùng sẽ làm code dài và khó đọc hơn.

Bài dùng **Java 21+**, vì record patterns và pattern matching for switch là tính năng chính thức từ Java 21. Với `instanceof` type pattern thuần túy, Java 17 cũng đã hỗ trợ. Phần trọng tâm là **review lời giải đã có và cải thiện tính rõ ràng**, không phải viết một bộ thuật toán hoàn toàn khác.

## 2. Tình huống review: chuyển yêu cầu hỗ trợ thành nhãn hiển thị

Giả sử một hệ thống helpdesk có ba loại yêu cầu:

- `CreateTicket(ticketId, title)`: tạo ticket, cần tiêu đề có nội dung.
- `CloseTicket(ticketId, reason)`: đóng ticket, cần lý do có nội dung.
- `EscalateTicket(ticketId, priority)`: chuyển ticket đến hàng xử lý chuyên biệt; `priority` có `queueName` và `score`.

Một `sealed` hierarchy mô tả tập biến thể:

```text
TicketRequest (sealed interface)
├── CreateTicket   (record)
├── CloseTicket    (record)
└── EscalateTicket (record)
                      │
                      └── PriorityInfo(queueName, score) (record component)
```

Khai báo các kiểu:

```java
sealed interface TicketRequest
        permits CreateTicket, CloseTicket, EscalateTicket {}

record CreateTicket(String ticketId, String title)
        implements TicketRequest {}

record CloseTicket(String ticketId, String reason)
        implements TicketRequest {}

record PriorityInfo(String queueName, int score) {}

record EscalateTicket(String ticketId, PriorityInfo priority)
        implements TicketRequest {}
```

Đây là **đoạn minh họa cấu trúc**; chương trình độc lập ở mục 7 đặt các type này bên trong một lớp có `public static void main`.

Hợp đồng hiển thị của bài tập:

| Đầu vào | Kết quả kỳ vọng | Ý nghĩa |
| --- | --- | --- |
| Selector `null` | `request:missing` | Không có request |
| CreateTicket với title không blank | `create:<id>:<title đã strip>` | Hiển thị ticket tạo mới |
| CreateTicket với title null/blank | `create:invalid:<id>` | Thiếu tiêu đề hữu ích |
| CloseTicket với reason không blank | `close:<id>:<reason đã strip>` | Hiển thị yêu cầu đóng |
| CloseTicket với reason null/blank | `close:invalid:<id>` | Thiếu lý do hữu ích |
| EscalateTicket có score từ 90 | `escalate:critical:<id>:<queueName>` | Ưu tiên rất cao |
| EscalateTicket có score dưới 90 | `escalate:<id>:<queueName>` | Ưu tiên thông thường |
| EscalateTicket có priority null | `escalate:missing:<id>` | Thiếu record ưu tiên |

Các dấu `<...>` trong bảng là chỗ mô tả cấu trúc chuỗi, **không phải cú pháp Java**. Kết quả thực tế trong chương trình sẽ dùng mã như `T-1` hoặc `risk`.

Ở đây chúng ta **giữ chính xác hợp đồng hiện tại**, kể cả trường hợp `queueName == null` sẽ bị nối chuỗi thành chữ `"null"`. Trong ứng dụng production có thể muốn cấm queueName null bằng validation, nhưng đó là **thay đổi hợp đồng**, không được âm thầm trộn vào một lần refactor chỉ nhằm tăng tính dễ đọc.

## 3. Phiên bản ban đầu: đúng nhưng khó review

Xem phương thức sau:

```java
static String before(TicketRequest r) {
    return switch (r) {
        case null -> "request:missing";

        case CreateTicket(var x, var y)
                when y != null && !y.isBlank() ->
                "create:" + x + ":" + y.strip();

        case CreateTicket(var x, var y) ->
                "create:invalid:" + x;

        case CloseTicket(var x, var y)
                when y != null && !y.isBlank() ->
                "close:" + x + ":" + y.strip();

        case CloseTicket(var x, var y) ->
                "close:invalid:" + x;

        case EscalateTicket(var x, PriorityInfo(var z, var n))
                when n >= 90 ->
                "escalate:critical:" + x + ":" + z;

        case EscalateTicket(var x, PriorityInfo(var z, var n)) ->
                "escalate:" + x + ":" + z;

        case EscalateTicket(var x, var p) ->
                "escalate:missing:" + x;
    };
}
```

Đây là **phương thức hợp lệ** khi đặt trong lớp có các type tương ứng. Phương thức này không có lỗi cú pháp và trong ví dụ thử nghiệm nó tuân theo hợp đồng đã nêu. Không nên tuyên bố “đoạn code sai” chỉ vì cách đặt tên khiến reviewer khó hiểu.

### Những chi phí đọc hiểu cụ thể

**Tên quá chung:** `r`, `x`, `y`, `z`, `n`, `p` khiến reviewer phải tra lại từng khai báo record. Trong `CreateTicket`, `x` là `ticketId` còn `y` là `title`; sang `CloseTicket`, `y` lại là `reason`. Cùng một ký hiệu một chữ nhưng mang vai trò khác nhau.

**Lặp điều kiện kiểm tra văn bản:** hai cặp `CreateTicket`/`CloseTicket` đều kiểm tra `y != null && !y.isBlank()` rồi gọi `strip()`. Nếu chính sách hiển thị của hai loại thực sự giống nhau, duplication làm reviewer phải xác nhận hai cặp không vô tình khác nhau.

**Guard và fallback trộn cùng một tầng:** reviewer nhìn thấy nhiều case liên tiếp và phải suy ra rằng case sau của Create/Close dành cho title/reason thiếu dữ liệu, còn case cuối của Escalate dành cho record `priority == null`.

**Record pattern lồng thiếu ngữ nghĩa:** `PriorityInfo(var z, var n)` cho biết kiểu nhưng không nói được `z` là tên queue và `n` là điểm. Ngưỡng `90` do vậy khó đọc vì không nhìn thấy `riskScore` hay `priorityScore`.

**Phạm vi business rule bị che:** người đọc phải hiểu “đủ điều kiện hiển thị” nghĩa là chuỗi khác null và không blank; không có tên nào mô tả chính sách ấy.

**Điều đúng cần giữ:** case hẹp có guard đứng trước case rộng, `case null` hiện diện và case tổng quát `EscalateTicket` xử lý component priority null. Reviewer không được xóa các nhánh đó chỉ vì muốn mã gọn.

## 4. Rubric review: đo mức rõ ràng, không chấm theo số dòng

Có thể dùng một rubric ngắn cho code review. Với mỗi tiêu chí, chấm **0–2**: 0 = khó xác định hoặc rủi ro rõ; 1 = hiểu được nhưng cần tra cứu; 2 = đọc tự nhiên và có test bảo vệ. Đây là công cụ trao đổi, **không phải quy chuẩn Java bắt buộc**.

| Tiêu chí | Điều reviewer cần tìm | Dấu hiệu đáng chỉnh |
| --- | --- | --- |
| **Tên domain** | Biến bộc lộ role như `ticketId`, `queueName` | `x`, `a`, `n` xuất hiện hàng loạt |
| **Intent từng case** | Nhìn case thấy ngay biến thể và rule | Hai case trông giống nhau nhưng thiếu giải thích |
| **Độ sâu phân rã** | Chỉ lấy component thực sự dùng | Record pattern lồng 3–4 tầng, nhiều biến bỏ trống |
| **Thứ tự case** | Hẹp/guard trước rộng; không dominated | Mẫu cha đứng trước mẫu con |
| **Null/exception contract** | Selector null và component null khác nhau | `default` bị hiểu nhầm là bắt null |
| **Kết quả và side effects** | Switch expression tạo một giá trị rõ ràng | Helper ẩn I/O hoặc có thay đổi trạng thái trong guard |
| **Duplication/abstraction** | Trích quy tắc lặp có cùng semantics | Lặp nhiều logic hoặc helper quá tổng quát |
| **Khả năng kiểm thử** | Có ca biên và expected rõ | Chỉ test happy path, không assert giá trị |

**Cách dùng:** Không nhất thiết cộng điểm thành KPI. Reviewer nên ghi nhận **vấn đề thực tế và đề xuất cụ thể**: “Đổi `var n` thành `var score` để ngưỡng `>= 90` có ý nghĩa”, thay vì chỉ bình luận “code chưa clean”.

Rubric cũng giúp phân biệt hai loại nhận xét:
- **Blocker về correctness:** thiếu subtype, xử lý null sai hợp đồng, guard làm ném exception, thay thứ tự case khiến khác hành vi.
- **Gợi ý readability:** tên biến, tách helper, xuống dòng, bình luận giải thích domain.

Trong review, ưu tiên correctness trước, sau đó cải thiện cấu trúc mà không làm hỏng các cam kết hiện có.

## 5. Phiên bản cải thiện: tên rõ và một helper có mục đích

Mục tiêu là giữ nguyên kết quả từ `before(...)`, nhưng giảm mức độ reviewer phải “dịch ngược” tên biến và các rule lặp.

Trích riêng chính sách format text dùng chung:

```java
static String formatNonBlankDetail(
        String action, String ticketId, String detail) {
    if (detail == null || detail.isBlank()) {
        return action + ":invalid:" + ticketId;
    }
    return action + ":" + ticketId + ":" + detail.strip();
}
```

Đây là helper **thuần** theo nghĩa không tự thay đổi trạng thái ứng dụng, không truy vấn dịch vụ hay database. Nó trả về đúng định dạng chuỗi đã có trong cả hai cặp case `CreateTicket` và `CloseTicket`.

Đổi lời giải thành:

```java
static String after(TicketRequest request) {
    return switch (request) {
        case null -> "request:missing";

        case CreateTicket(var ticketId, var title) ->
                formatNonBlankDetail("create", ticketId, title);

        case CloseTicket(var ticketId, var reason) ->
                formatNonBlankDetail("close", ticketId, reason);

        case EscalateTicket(
                var ticketId,
                PriorityInfo(var queueName, var score))
                when score >= 90 ->
                "escalate:critical:" + ticketId + ":" + queueName;

        case EscalateTicket(
                var ticketId,
                PriorityInfo(var queueName, var score)) ->
                "escalate:" + ticketId + ":" + queueName;

        case EscalateTicket(var ticketId, var priority) ->
                "escalate:missing:" + ticketId;
    };
}
```

### Vì sao phiên bản này dễ đọc hơn?

1. `request` giúp nhận ra selector là một yêu cầu hỗ trợ.
2. `ticketId`, `title` và `reason` mang đúng ngữ nghĩa component.
3. `queueName` và `score` giúp reviewer biết câu `score >= 90` đang xét điểm ưu tiên.
4. Chính sách chuỗi null/blank/strip tập trung ở `formatNonBlankDetail`, giảm lặp điều kiện.
5. Các case `EscalateTicket` vẫn đứng theo thứ tự **critical → standard → missing priority**, bộc lộ chính sách rõ.
6. `case null` vẫn xử lý selector null.
7. Không thêm `default` để che subtype mới; compiler vẫn kiểm tra exhaustiveness của sealed hierarchy.

**Trade-off phải nói rõ:** helper `formatNonBlankDetail` nhận `action` dạng chuỗi, vì ví dụ hiện có chung quy tắc giữa tạo và đóng ticket. Nếu sau này CreateTicket cần validate title khác CloseTicket.reason, tiếp tục ép cả hai qua helper có thể khiến nghiệp vụ bị trộn. Khi đó, hai helper theo domain hoặc hai case rõ ràng riêng biệt có thể dễ đọc hơn. **Không trích helper chỉ để giảm số dòng.**

## 6. So sánh trước–sau theo hành vi, không chỉ theo cảm giác

Đây là ma trận tối thiểu để kiểm chứng rằng refactor không làm thay đổi output:

| Input | Kết quả của cả `before` và `after` | Điểm cần bảo toàn |
| --- | --- | --- |
| `null` | `request:missing` | Chính sách selector null |
| CreateTicket với `"  Login fails  "` | `create:T-1:Login fails` | `strip()` khoảng trắng |
| CreateTicket với `" \t "` | `create:invalid:T-2` | `isBlank()` |
| CreateTicket với `null` title | `create:invalid:T-3` | Không gọi method trên null |
| CloseTicket với `" solved "` | `close:T-4:solved` | Nội dung hợp lệ |
| CloseTicket với `null` reason | `close:invalid:T-6` | Nhánh missing reason |
| EscalateTicket có score 90 | `escalate:critical:T-7:risk` | Ranh giới `>= 90` |
| EscalateTicket có score 89 | `escalate:T-9:risk` | Guard false có fallback |
| EscalateTicket với priority null | `escalate:missing:T-10` | Record lồng không khớp null |
| EscalateTicket có queueName null | `escalate:T-11:null` | Hợp đồng nối chuỗi hiện tại |

Bảng này không chỉ chứng minh “hai hàm in giống nhau”. Nó buộc reviewer xác định **đâu là hành vi đúng từ yêu cầu**. Nếu hai phiên bản cùng chứa bug, phép so sánh before/after sẽ cùng pass; vì thế bộ test cần so **cả expected theo đặc tả**, không chỉ `before(input).equals(after(input))`.

Trong chương trình đầy đủ, mỗi test đồng thời xác minh:

```java
Objects.equals(expected, before(input))
        && Objects.equals(expected, after(input))
```

Nếu một trong hai khác expected, test ném `AssertionError`. Sau refactor, khi hàm `before` được loại bỏ khỏi code sản xuất, regression tests dựa trên **expected theo hợp đồng** vẫn cần được giữ.

## 7. Ví dụ chạy độc lập Java 21: refactor và 14 phép so sánh

Lưu toàn bộ ví dụ sau thành **`PatternReadabilityReviewDemo.java`**. Đây là chương trình độc lập, có `main`, chỉ dùng JDK. Các record cố ý không validate sâu để kiểm thử những giá trị null/blank mà caller có thể tạo ra. Đó là đặc điểm của fixture học tập, không phải khuyến nghị luôn cho phép dữ liệu thiếu hợp lệ trong sản phẩm.

```java
import java.util.Objects;

public class PatternReadabilityReviewDemo {
    sealed interface TicketRequest
            permits CreateTicket, CloseTicket, EscalateTicket {}

    record CreateTicket(String ticketId, String title)
            implements TicketRequest {}

    record CloseTicket(String ticketId, String reason)
            implements TicketRequest {}

    record PriorityInfo(String queueName, int score) {}

    record EscalateTicket(String ticketId, PriorityInfo priority)
            implements TicketRequest {}

    // BEFORE: cùng hành vi nhưng dùng tên biến khó theo dõi và lặp guard.
    static String before(TicketRequest r) {
        return switch (r) {
            case null -> "request:missing";

            case CreateTicket(var x, var y)
                    when y != null && !y.isBlank() ->
                    "create:" + x + ":" + y.strip();
            case CreateTicket(var x, var y) ->
                    "create:invalid:" + x;

            case CloseTicket(var x, var y)
                    when y != null && !y.isBlank() ->
                    "close:" + x + ":" + y.strip();
            case CloseTicket(var x, var y) ->
                    "close:invalid:" + x;

            case EscalateTicket(var x, PriorityInfo(var z, var n))
                    when n >= 90 ->
                    "escalate:critical:" + x + ":" + z;
            case EscalateTicket(var x, PriorityInfo(var z, var n)) ->
                    "escalate:" + x + ":" + z;
            case EscalateTicket(var x, var p) ->
                    "escalate:missing:" + x;
        };
    }

    // AFTER: một helper có hợp đồng rõ cho hai hành động cùng chính sách.
    static String formatNonBlankDetail(
            String action, String ticketId, String detail) {
        if (detail == null || detail.isBlank()) {
            return action + ":invalid:" + ticketId;
        }
        return action + ":" + ticketId + ":" + detail.strip();
    }

    static String after(TicketRequest request) {
        return switch (request) {
            case null -> "request:missing";

            case CreateTicket(var ticketId, var title) ->
                    formatNonBlankDetail("create", ticketId, title);

            case CloseTicket(var ticketId, var reason) ->
                    formatNonBlankDetail("close", ticketId, reason);

            case EscalateTicket(
                    var ticketId, PriorityInfo(var queueName, var score))
                    when score >= 90 ->
                    "escalate:critical:" + ticketId + ":" + queueName;

            case EscalateTicket(
                    var ticketId, PriorityInfo(var queueName, var score)) ->
                    "escalate:" + ticketId + ":" + queueName;

            case EscalateTicket(var ticketId, var priority) ->
                    "escalate:missing:" + ticketId;
        };
    }

    static int passed = 0;

    static void check(
            String name, TicketRequest input, String expected) {
        String original = before(input);
        String refactored = after(input);

        if (!Objects.equals(expected, original)
                || !Objects.equals(expected, refactored)) {
            throw new AssertionError(name
                    + " expected=" + expected
                    + ", original=" + original
                    + ", refactored=" + refactored);
        }

        passed++;
        System.out.println("PASS " + name + "=" + refactored);
    }

    public static void main(String[] args) {
        check("null-selector", null, "request:missing");

        check("create-valid",
                new CreateTicket("T-1", "  Login fails  "),
                "create:T-1:Login fails");

        check("create-blank",
                new CreateTicket("T-2", " \t "),
                "create:invalid:T-2");

        check("create-null",
                new CreateTicket("T-3", null),
                "create:invalid:T-3");

        check("close-valid",
                new CloseTicket("T-4", " solved "),
                "close:T-4:solved");

        check("close-blank",
                new CloseTicket("T-5", "   "),
                "close:invalid:T-5");

        check("close-null",
                new CloseTicket("T-6", null),
                "close:invalid:T-6");

        check("critical-boundary",
                new EscalateTicket(
                        "T-7", new PriorityInfo("risk", 90)),
                "escalate:critical:T-7:risk");

        check("critical-above",
                new EscalateTicket(
                        "T-8", new PriorityInfo("risk", 99)),
                "escalate:critical:T-8:risk");

        check("standard-below",
                new EscalateTicket(
                        "T-9", new PriorityInfo("risk", 89)),
                "escalate:T-9:risk");

        check("priority-null",
                new EscalateTicket("T-10", null),
                "escalate:missing:T-10");

        check("queue-null",
                new EscalateTicket(
                        "T-11", new PriorityInfo(null, 10)),
                "escalate:T-11:null");

        check("queue-blank",
                new EscalateTicket(
                        "T-12", new PriorityInfo(" ", 10)),
                "escalate:T-12: ");

        check("unicode-spaces",
                new CreateTicket(
                        "T-13", "\u2003Need help\u2003"),
                "create:T-13:Need help");

        System.out.println("TOTAL_PASS=" + passed);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 -encoding UTF-8 PatternReadabilityReviewDemo.java
java PatternReadabilityReviewDemo
```

**Đầu ra của cả 14 ca khi thành công:**

```text
PASS null-selector=request:missing
PASS create-valid=create:T-1:Login fails
PASS create-blank=create:invalid:T-2
PASS create-null=create:invalid:T-3
PASS close-valid=close:T-4:solved
PASS close-blank=close:invalid:T-5
PASS close-null=close:invalid:T-6
PASS critical-boundary=escalate:critical:T-7:risk
PASS critical-above=escalate:critical:T-8:risk
PASS standard-below=escalate:T-9:risk
PASS priority-null=escalate:missing:T-10
PASS queue-null=escalate:T-11:null
PASS queue-blank=escalate:T-12: 
PASS unicode-spaces=create:T-13:Need help
TOTAL_PASS=14
```

Chú ý: dòng `queue-blank` kết thúc bằng **một dấu cách** sau dấu hai chấm cuối. Điều đó được giữ nguyên có chủ đích để kiểm tra rằng refactor không tự thêm chính sách validate/normalize `queueName`. Nếu copy output qua môi trường tự loại khoảng trắng cuối dòng, việc so sánh hiển thị có thể không phản ánh chính xác byte/ký tự; bản thân chương trình đã dùng các assertion để kiểm tra chuỗi.

Ví dụ được chạy bằng Java compiler ở chế độ `--release=21`, và các trường hợp cụ thể ở trên đã cho kết quả như expected. Số 14 là số lời gọi `check` trong `main` thành công, không phải số case của `switch`.

## 8. Từ ví dụ rút ra điều gì về khả năng đọc?

### 8.1. Tên biến tạo ra mối liên hệ với domain

So sánh:

```java
case EscalateTicket(var x, PriorityInfo(var z, var n))
        when n >= 90 -> ...
```

và:

```java
case EscalateTicket(
        var ticketId, PriorityInfo(var queueName, var score))
        when score >= 90 -> ...
```

Cả hai là **đoạn minh họa trong một switch**, không thể biên dịch riêng với `...`. Nhưng câu thứ hai cho thấy thứ gì đang được so sánh với 90, và tại sao `queueName` được đưa vào nhãn.

**Quy tắc đề xuất:** đặt tên theo **vai trò của component tại vị trí đang dùng**, không chỉ theo kiểu Java. Hai thành phần đều có thể là `String` nhưng `ticketId` không được đặt tên như `title` hay `reason`.

Không nhất thiết dùng tên dài: `score` đủ rõ trong một case `PriorityInfo`, còn `ticketId` cần khác `requestId` nếu domain phân biệt hai ID. Tên phải cân bằng giữa khả năng định vị ý nghĩa và độ gọn khi đọc.

### 8.2. Giữ nguyên object khi không cần deconstruction

Nếu chỉ cần chuyển tiếp toàn bộ request đến một handler khác:

```java
case CloseTicket closeTicket -> closeHandler.handle(closeTicket);
```

Đây là nhãn minh họa, giả định có `closeHandler`. Việc dùng **type pattern** giữ ngữ cảnh `CloseTicket` và tránh tạo các biến component không dùng.

Chỉ dùng:

```java
case CloseTicket(var ticketId, var reason) -> ...
```

khi thực sự cần `ticketId` hoặc `reason` tại nhánh. Không phân rã record chỉ vì cú pháp cho phép.

### 8.3. Dừng phân rã đúng cấp

Trong `EscalateTicket`:
- Cần score/queueName để phân loại → `PriorityInfo(var queueName, var score)` là hợp lý.
- Chỉ cần biết request thuộc loại EscalateTicket → `case EscalateTicket escalation` là rõ hơn.
- Cần xét priority null → một mẫu tổng quát `EscalateTicket(var ticketId, var priority)` rõ nghĩa.

Nếu record lồng sâu qua bốn tầng mà case chỉ dùng một giá trị, có thể tách một helper thuần có tên nghiệp vụ hoặc dùng accessor trực tiếp sau một type pattern. Tuy nhiên, không tạo helper tùy tiện nếu nó chỉ đổi cú pháp mà làm người đọc phải nhảy đến nhiều file.

## 9. Guard, dominance và thứ tự case

Một review pattern matching tốt phải phân biệt **điều kiện business** và **thứ tự matching**.

### 9.1. Hẹp trước rộng

Đúng:

```java
case EscalateTicket(var id, PriorityInfo(var queue, var score))
        when score >= 90 -> "critical";

case EscalateTicket(var id, PriorityInfo(var queue, var score)) ->
        "standard";

case EscalateTicket(var id, var priority) ->
        "missing";
```

Đây là các nhãn minh họa. Mẫu tổng quát không guard được đặt sau những trường hợp chi tiết.

### 9.2. Ví dụ sai thứ tự bị compiler từ chối

Ví dụ Java 21 **cố ý không biên dịch**:

```java
public class ReadabilityDominanceCheck {
    sealed interface TicketRequest
            permits CreateTicket, CloseTicket {}

    record CreateTicket(String ticketId, String title)
            implements TicketRequest {}
    record CloseTicket(String ticketId, String reason)
            implements TicketRequest {}

    static String bad(TicketRequest request) {
        return switch (request) {
            case CreateTicket(var id, var title) -> "create:" + id;
            case CreateTicket(var id, var title)
                    when title != null -> "has-title";
            case CloseTicket(var id, var reason) -> "close:" + id;
        };
    }
}
```

Compiler báo dạng:

```text
this case label is dominated by a preceding case label
```

Lý do là case `CreateTicket` không guard ở trước đã bao phủ mọi CreateTicket, làm case có guard phía sau không bao giờ được chọn. Đây là **lỗi biên dịch**, không phải lỗi runtime mà reviewer có thể “bỏ qua vì không ai gọi tới”.

Đổi thứ tự thành guard trước, fallback sau, hoặc gộp một case rồi viết `if` trong body. Không nên thêm `default` để né lỗi dominance vì nó không thay đổi quan hệ bao phủ giữa hai case.

### 9.3. Khi guard quá dài

`when` nên mô tả điều kiện dễ đọc và không có side effect. Với điều kiện:

```java
when score >= 90
```

ý định tương đối dễ hiểu; nhưng nếu guard có nhiều lời gọi như đọc database, tính quyền, lấy thời gian hiện tại, logging rồi thay đổi state, reviewer khó biết khi nào matching thực sự “đúng”.

Ưu tiên:
- Kiểm tra dữ liệu cục bộ, thuần, ngắn ngay trong guard.
- Logic nghiệp vụ nhiều bước ở case body hoặc helper có tên rõ.
- Tránh phụ thuộc vào số lần gọi helper có side effect trong quá trình đánh giá pattern/guard.
- Với điều kiện `&&`, kiểm tra null **trước** khi dereference.

Điều này vừa tăng khả năng đọc vừa giúp debug các đường ngoại lệ.

## 10. Exhaustiveness là công cụ review, không phải thay thế nghiệp vụ

Hierarchy của bài có ba record trực tiếp, tất cả là `final`. Phương thức `after` có case cho đủ ba loại (một số loại có nhiều case hẹp/guard/fallback). Vì vậy compiler có thể chứng minh switch expression exhaustive mà không cần `default`.

**Lợi ích cho reviewer:** Nếu một người khác thêm:

```java
record ReopenTicket(String ticketId) implements TicketRequest {}
```

thì phải sửa `permits` của `TicketRequest` để subtype hợp lệ. Sau khi tập subtype thay đổi, một switch expression cũ thiếu đường xử lý `ReopenTicket` có thể bị compiler từ chối khi recompile. Đây là cơ hội review yêu cầu mới thay vì tự động trả `unknown`.

**Không diễn giải quá mức:** Compiler không chứng minh `"escalate:critical"` có đúng chính sách hay không. Ngưỡng 90 là quy tắc nghiệp vụ; phải có test ranh giới, kiểm thử spec và code review.

Nếu API cố ý có nhánh `non-sealed` để plugin bên ngoài thêm subtype, cần một case bao phủ nhánh mở và chính sách xử lý fallback rõ ràng. Không thể chỉ liệt kê concrete implementations hiện tại rồi khẳng định sẽ exhaustive mãi.

## 11. Null và exception: điều reviewer phải tách bạch

### 11.1. Selector null

`after(null)` chọn `case null` và trả `request:missing`. Nếu bỏ `case null`, `default` không tự xử lý null theo quy tắc Java 21. Switch trên tham chiếu null thường ném `NullPointerException` nếu không có nhãn xử lý phù hợp.

Đây là một **hợp đồng public**: refactor có thể phải giữ việc trả chuỗi này, chứ không được thay bằng NPE chỉ vì muốn ít case.

### 11.2. Component PriorityInfo null

`new EscalateTicket("T-10", null)` là một EscalateTicket khác null. Mẫu lồng `PriorityInfo(...)` không khớp component null; case `EscalateTicket(var ticketId, var priority)` vẫn khớp và trả `escalate:missing:T-10`.

Nhánh fallback này là cần thiết cho hợp đồng đang có. Xóa nó và giả định “priority luôn non-null” chỉ vì domain thông thường muốn vậy có thể khiến switch không còn exhaustive hoặc đổi hành vi đối với dữ liệu hiện có.

### 11.3. Queue name null và blank

Với `PriorityInfo(null, 10)`, cả phiên bản trước/sau đều nối chuỗi thành `escalate:T-11:null`. Với `PriorityInfo(" ", 10)`, kết quả có dấu cách cuối.

Đây không phải cách format tốt cho UI thật; **nhưng đã là behavior của lời giải gốc**, nên một refactor readability không được âm thầm đổi nó thành `escalate:missing`. Nếu muốn validate queueName, nên viết yêu cầu mới, quyết định thời điểm ngoại lệ hoặc fallback, rồi đổi test theo hợp đồng mới.

### 11.4. Accessor ném ngoại lệ

Record pattern cần truy xuất component bằng accessor. Nếu một record tự khai báo accessor và accessor ném lỗi trong lúc matching, Java 21 có thể ném `MatchException` với exception gốc trong `getCause()`. Đó là đường lỗi khác với “mẫu con không khớp vì null”.

Trong ví dụ, accessor mặc định của records không tự làm I/O hoặc ném lỗi theo logic tùy chỉnh. Nếu refactor một hệ thống có accessor side effect, cần kiểm thử cả thứ tự/số lần gọi và exception contract, không chỉ chuỗi trả về.

### 11.5. Thay đổi về đánh giá biểu thức

Nếu trước đây code gọi cùng một hàm nhiều lần trong `instanceof + cast`, chuyển sang pattern variable thường chỉ gọi nguồn một lần. Điều này có thể là sửa bug, nhưng vẫn là **thay đổi behavior** nếu hàm có side effect.

Reviewer nên hỏi: “Đầu vào pattern là một biến ổn định hay một lời gọi có thể thay đổi state?” Nếu chưa chắc, tách riêng phần thay đổi số lần đánh giá và có test tương ứng.

## 12. Khi nào trích helper, khi nào giữ case tại chỗ?

Một helper tốt mang một **ý nghĩa ổn định** hoặc gom một **quy tắc thật sự giống nhau**.

Trong ví dụ:
- `CreateTicket` và `CloseTicket` đều có chính sách “detail khác null và không blank; nếu hợp lệ thì strip, nếu không thì invalid”.
- `formatNonBlankDetail` gom đúng logic đó.
- Các case vẫn thể hiện tên domain `CreateTicket`, `CloseTicket` ngay trong switch, nên người đọc không mất bối cảnh.

Nhưng nếu tương lai CloseTicket.reason phải giữ nguyên khoảng trắng để audit, còn CreateTicket.title vẫn cần `strip()`, helper chung trở thành abstraction sai. Hãy tách thành `formatTicketTitle` và `formatClosingReason` hoặc giữ logic tại nơi có trách nhiệm.

**Dấu hiệu helper gây hại:**
1. Tên `process`, `doIt`, `handleValue` chung chung.
2. Nhận nhiều cờ Boolean như `isCreate`, `isClose`, `isUrgent`.
3. Dùng `Object` + cast để nhận nhiều kiểu vốn đã có subtype riêng.
4. Làm I/O hoặc cập nhật trạng thái dù có tên giống formatter.
5. Buộc reviewer mở 3–4 file chỉ để biết một case trả giá trị gì.
6. Được trích chỉ vì “method trên 10 dòng”, không có concept chung.

**Quy tắc review:** giảm duplication khi duplication phản ánh cùng một quy tắc; không cố hợp nhất hai policy chỉ vì chúng hiện viết giống nhau.

## 13. Chọn cấu trúc phù hợp: switch expression, statement, instanceof hay visitor?

Không có cấu trúc duy nhất tối ưu cho mọi bài toán.

| Nhu cầu | Cấu trúc thường dễ đọc | Vì sao |
| --- | --- | --- |
| Biến một giá trị sealed thành một giá trị khác | `switch expression` exhaustive | Nhìn thấy đầy đủ các kiểu được xử lý |
| Phân loại vài kiểu trong một hàm ngắn | `instanceof` type patterns / `if` | Tránh switch phức tạp khi ít nhánh |
| Thực hiện nhiều side effects theo từng case | `switch statement` hoặc dispatch tới handler | Không ép mỗi nhánh phải trả giá trị |
| Chỉ lấy 1–2 component của record | Record pattern nông hoặc accessor | Không tạo quá nhiều biến trung gian |
| Truyền toàn bộ object sang dịch vụ | Type pattern giữ object | Giữ ngữ cảnh và hợp đồng type |
| Hệ thống có subtype mở rộng bởi plugin | Registry/handler/interface mở | Không giả định tập biến thể đã đóng |
| Rule nghiệp vụ nhiều bước | Service/helper có tên rõ | Giữ `when` ngắn và hạn chế side effects |

Chẳng hạn, một application service có bốn command handlers riêng có thể dễ review hơn một switch chứa hàng trăm dòng business logic. Lúc ấy vẫn có thể dùng switch expression ngắn:

```java
return switch (request) {
    case CreateTicket create -> createHandler.handle(create);
    case CloseTicket close -> closeHandler.handle(close);
    case EscalateTicket escalation -> escalationHandler.handle(escalation);
};
```

Đây là đoạn minh họa, giả định các handler tồn tại và trả kiểu tương thích. Nó cố tình **không** phân rã mọi component, vì trách nhiệm xử lý đã được ủy quyền.

Nếu `request` được phép null, cần bổ sung chính sách null theo hợp đồng; nếu null bị cấm, có thể kiểm tra trước switch. Khả năng dễ đọc chỉ thực sự tăng khi ranh giới trách nhiệm được nêu rõ.

## 14. Cách tổ chức một review hiệu quả

Có thể review lời giải pattern matching theo thứ tự sau để giảm việc nhận xét lặp:

### Vòng 1 — Kiểm tra hợp đồng và tính đúng

Đọc type hierarchy, danh sách `permits`, kỳ vọng của các nhánh và policy null. Xác định liệu switch expression đã exhaustive, guard nào có fallback, dữ liệu biên nào bị bỏ quên. Đây là nhóm vấn đề cần xử lý trước khi đổi tên/format.

### Vòng 2 — Đọc case như một bảng quyết định

Chuyển các case thành bảng:

| Case | Kiểu/điều kiện | Hành vi |
| --- | --- | --- |
| `null` | Selector null | Hiển thị missing |
| `CreateTicket` | Title đủ nội dung | Hiển thị create |
| `CreateTicket` | Còn lại | Invalid |
| `CloseTicket` | Reason đủ nội dung | Hiển thị close |
| `CloseTicket` | Còn lại | Invalid |
| `EscalateTicket` | Priority tồn tại, score từ 90 | Critical |
| `EscalateTicket` | Priority tồn tại, score dưới 90 | Standard |
| `EscalateTicket` | Priority không có | Missing priority |

Nếu một case không thể được tóm tắt bằng một dòng dễ hiểu, reviewer có thể đề xuất đặt tên helper hoặc tách business rule. Nếu hai dòng trùng ý nghĩa nhưng code khác, xem xét thống nhất.

### Vòng 3 — Đọc biến và phạm vi

Tra tên component trong record rồi đọc pattern variables. Xem có cùng tên dùng cho nhiều ý nghĩa, có biến được bind nhưng không dùng, có biến đặt tên mơ hồ, hoặc có flow scoping phức tạp hay không. Với `instanceof`, kiểm tra `&&` và `||` để biết biến có chắc chắn đã được ràng buộc ở chỗ sử dụng.

### Vòng 4 — Đọc chi phí đánh giá và ngoại lệ

Pattern matching có thể gọi accessor của record, guard có thể gọi helper. Kiểm tra có side effects, I/O, null dereference, thay đổi số lần gọi hay không. Nếu có, chỉ đổi cấu trúc sau khi đã có test bảo vệ.

### Vòng 5 — Đối chiếu before/after với expected

Viết fixtures cho mỗi case, dữ liệu biên, null selector, null component và exception contract. Sau đó mới làm refactor. **Một diff đẹp nhưng không có regression tests chưa chứng minh là một lời giải tốt hơn.**

### Vòng 6 — Diễn đạt feedback có thể hành động

Thay vì: “Mã này hơi khó đọc”, hãy viết:

> “Trong hai nhánh CreateTicket và CloseTicket, biến `y` có hai vai trò khác nhau và guard kiểm tra non-blank bị lặp. Đề xuất đặt tên `title`/`reason` theo record component và trích quy tắc hiển thị chung thành một helper thuần. Giữ lại ca kiểm thử null, blank và khoảng trắng trước khi đổi.”

Đây là một ví dụ nhận xét code review, nhấn vào vấn đề, rủi ro và hành động cụ thể.

## 15. JUnit 5: chuyển phép so sánh thành regression test trong dự án

Chương trình ở mục 7 tự chạy không cần JUnit. Nếu dự án dùng JUnit 5, có thể viết test độc lập theo expected behavior, sau đó bỏ mã `before` khỏi production khi refactor đã được chấp nhận.

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class PatternReadabilityReviewTest {
    @Test
    void titleMustBeNonBlankAndTrimmed() {
        var valid = new PatternReadabilityReviewDemo.CreateTicket(
                "T-1", "  Login fails  ");
        var blank = new PatternReadabilityReviewDemo.CreateTicket(
                "T-2", " \t ");

        assertAll(
                () -> assertEquals("create:T-1:Login fails",
                        PatternReadabilityReviewDemo.after(valid)),
                () -> assertEquals("create:invalid:T-2",
                        PatternReadabilityReviewDemo.after(blank))
        );
    }

    @Test
    void priorityBoundaryIsInclusive() {
        var at = new PatternReadabilityReviewDemo.EscalateTicket(
                "T-7", new PatternReadabilityReviewDemo.PriorityInfo(
                        "risk", 90));
        var below = new PatternReadabilityReviewDemo.EscalateTicket(
                "T-9", new PatternReadabilityReviewDemo.PriorityInfo(
                        "risk", 89));

        assertEquals("escalate:critical:T-7:risk",
                PatternReadabilityReviewDemo.after(at));
        assertEquals("escalate:T-9:risk",
                PatternReadabilityReviewDemo.after(below));
    }

    @Test
    void componentNullDiffersFromSelectorNull() {
        var missing = new PatternReadabilityReviewDemo.EscalateTicket(
                "T-10", null);

        assertAll(
                () -> assertEquals("request:missing",
                        PatternReadabilityReviewDemo.after(null)),
                () -> assertEquals("escalate:missing:T-10",
                        PatternReadabilityReviewDemo.after(missing))
        );
    }

    @Test
    void allKnownVariantsRemainCovered() {
        assertEquals("close:T-4:solved",
                PatternReadabilityReviewDemo.after(
                        new PatternReadabilityReviewDemo.CloseTicket(
                                "T-4", " solved ")));
    }
}
```

Đây là **lớp test minh họa, không phải chương trình standalone**: cần JUnit 5 và cùng package với `PatternReadabilityReviewDemo`, hoặc điều chỉnh visibility. Khi dự án có Java 21, code ở mục 7 có thể được giữ trong một file riêng làm fixture chạy bằng JDK trước khi tích hợp JUnit.

**Mở rộng test đáng giá:** thêm kiểm tra exception contract nếu có accessor tùy chỉnh, test negative branch khi score bằng 89, test case score 90 và 91, test cả title/reason Unicode whitespace, và test parity trên các fixture có ảnh hưởng đến UI.

## 16. Những lỗi review thường gặp và cách sửa

### 16.1. “Càng ít case càng tốt”

Ít case có thể giấu những biến thể quan trọng của domain. Với sealed root, case tường minh thường hữu ích. Chỉ gộp case khi thật sự chung một nghiệp vụ.

### 16.2. “Record pattern sâu bao nhiêu cũng tốt”

Mẫu nhiều tầng có thể làm người đọc mất ngữ cảnh và tạo nhiều biến bỏ không. Dùng type pattern hoặc deconstruction nông khi handler chỉ cần object con.

### 16.3. “Đổi tên biến là đủ”

Tên tốt giúp đọc code nhưng không giải quyết guard thiếu fallback, ngoại lệ hoặc side effects. Review phải xem cả cấu trúc matching và hành vi.

### 16.4. “Thêm `default` để khỏi đau đầu exhaustive”

Với sealed hierarchy đóng, default có thể che việc thêm subtype mới. Compiler báo thiếu case thường là **tín hiệu yêu cầu review** hữu ích, không phải phiền toái cần bỏ.

### 16.5. “`case null` giải quyết mọi null”

`case null` xử lý selector null, không tự xử lý component null. Trường hợp EscalateTicket.priority null cần case khác.

### 16.6. “Đổi guard trước/sau không ảnh hưởng gì”

Guard và thứ tự case quyết định đường khớp. Mẫu rộng đứng trước mẫu hẹp có thể gây lỗi dominance; một thay đổi điều kiện `>=` sang `>` còn làm khác boundary behavior.

### 16.7. “Tách helper thì luôn dễ đọc”

Helper quá chung có thể che policy domain hoặc side effects. Nếu hai rule khác nhau, nên tách; nếu cùng rule, helper có tên cụ thể là hợp lý.

### 16.8. “Chỉ test trước–sau giống nhau là đủ”

Nếu cả hai đều trả sai theo yêu cầu, parity test vẫn pass. Cần expected độc lập. Bộ ví dụ kiểm tra cả original và refactored bằng một giá trị expected.

### 16.9. “Không cần test null vì code bình thường luôn có giá trị”

API nhận tham chiếu có thể nhận null nếu không có constraint; record components cũng có thể null. Hợp đồng cần được xác định và kiểm thử rõ.

### 16.10. “Đọc một hàm đồng nghĩa không có side effect”

Pattern có thể gọi accessor và guard có thể gọi method. Nếu accessor custom ném exception hoặc thực hiện I/O, refactor deconstruction có thể thay đổi thời điểm/loại lỗi.

### 16.11. “Code Java 17 cũng dùng được mọi cú pháp pattern Java 21”

`instanceof String text` có từ Java 16; record class có từ Java 16; nhưng record pattern và pattern matching for switch chính thức từ Java 21. Review phải ghi đúng `--release` và JVM đích.

### 16.12. “Reviewer phải thích phong cách viết của tôi”

Phong cách cá nhân không phải căn cứ đủ để yêu cầu thay đổi. Feedback tốt gắn với khả năng hiểu domain, tính đúng, test, hiệu ứng refactor và convention nhất quán của nhóm.

## 17. Bài tập tự luyện có đáp án

**Bài 1 — Tên biến.** Trong `case EscalateTicket(var x, PriorityInfo(var z, var n)) when n >= 90`, nên đổi ba tên thế nào?

**Đáp án:** `ticketId`, `queueName`, `score`. Các tên ấy cho thấy dữ liệu nào tạo nhãn và ngưỡng 90 đánh giá thứ gì.

**Bài 2 — Null.** Vì sao `after(null)` khác `after(new EscalateTicket("T-10", null))`?

**Đáp án:** trường hợp đầu là selector null và khớp `case null`; trường hợp sau là instance EscalateTicket, chỉ component priority null. Mẫu PriorityInfo lồng không khớp, case EscalateTicket tổng quát xử lý.

**Bài 3 — Guard ranh giới.** Score 90 thuộc nhánh critical hay standard?

**Đáp án:** critical vì guard dùng `>= 90`. Nên có test score 89 và 90 để không vô tình đổi thành `> 90`.

**Bài 4 — Dữ liệu blank.** Tại sao title `"  "` bị phân loại invalid thay vì được trả về là chuỗi rỗng sau `strip()`?

**Đáp án:** hợp đồng kiểm tra `isBlank()` trước khi strip. `isBlank()` với chuỗi toàn khoảng trắng trả true, nên helper trả nhãn invalid.

**Bài 5 — Helper chung.** Khi nào `formatNonBlankDetail` không còn phù hợp?

**Đáp án:** khi title và closing reason có chính sách khác nhau, ví dụ reason phải giữ nguyên khoảng trắng, title được chuẩn hóa. Lúc đó cần tách policy thay vì ép hai rule vào cùng helper.

**Bài 6 — Dominance.** Nếu đặt case `CreateTicket(var id, var title)` không guard trước case có `when title != null` thì compiler phản ứng thế nào?

**Đáp án:** case có guard phía sau bị dominated bởi case rộng phía trước; compiler Java 21 từ chối.

**Bài 7 — Độ sâu record.** Handler chỉ cần log “có request EscalateTicket” và truyền nguyên request xuống service. Nên viết type pattern hay record pattern lồng?

**Đáp án:** type pattern `case EscalateTicket escalation` rõ hơn, vì giữ object và không phân rã các trường không dùng.

**Bài 8 — Parity vs correctness.** Hai hàm `before` và `after` cùng trả `create:T-1:` cho title toàn khoảng trắng. Đã chứng minh code đúng chưa?

**Đáp án:** chưa. Chúng có thể cùng sai. Cần expected dựa trên hợp đồng, ở đây là `create:invalid:T-1`.

**Bài 9 — API evolution.** Nếu thêm một subtype `ReopenTicket` vào sealed hierarchy, vì sao nên không có `default` mù?

**Đáp án:** compiler có thể nhắc các switch exhaustive chưa xử lý subtype mới khi recompile. Default chung có thể che nhu cầu quyết định policy cho kiểu mới.

**Bài 10 — Queue name null.** Tại sao bản refactor của bài vẫn cho phép kết quả `escalate:T-11:null` dù không đẹp?

**Đáp án:** mục tiêu là cải thiện readability và bảo toàn behavior hiện tại. Validation queueName là thay đổi nghiệp vụ cần được yêu cầu/test riêng.

**Bài 11 — Phương thức thuần.** Vì sao không nên để `formatNonBlankDetail` tự ghi database hoặc gọi mạng?

**Đáp án:** một helper format trong switch nên dễ dự đoán, không side effects. I/O làm khó hiểu số lần gọi, vị trí lỗi và khả năng test; nên tách trách nhiệm.

**Bài 12 — Nhận xét review.** Câu nào hữu ích hơn: “code xấu” hay “`x` và `y` che vai trò của component, nên đặt `ticketId`, `reason` và giữ test null/blank trước refactor”?

**Đáp án:** câu thứ hai vì chỉ rõ vấn đề, rủi ro và cách sửa có thể thực hiện.

## 18. Checklist review cuối cùng

Trước khi chấp nhận một lời giải Java Pattern Matching, reviewer có thể tự hỏi:

- [ ] Tên sealed root, subtype và pattern variables có truyền đạt domain không?
- [ ] Có thể tóm tắt mỗi case thành một hành vi bằng một câu ngắn không?
- [ ] Mọi subtype của sealed hierarchy đã được xét đúng mức chi tiết chưa?
- [ ] Có case bị dominated hoặc thứ tự hẹp/rộng bị đảo không?
- [ ] Guard có ngắn, thuần, dễ hiểu và có đường xử lý khi false không?
- [ ] Những record patterns lồng sâu có thật sự cần thiết không?
- [ ] Có giữ object nguyên vẹn khi chỉ cần chuyển tiếp cho handler không?
- [ ] Selector null, nested component null và exception có chính sách riêng không?
- [ ] Có vô tình đổi thời điểm gọi accessor, helper, side effects hoặc exception type không?
- [ ] Helper trích ra mang một quy tắc chung thật, không phải abstraction chung chung?
- [ ] Kiểu kết quả của switch expression và `yield` có rõ ràng không?
- [ ] Có test expected độc lập để tránh hai phiên bản cùng sai không?
- [ ] Có ca boundary, null, blank, subtype gián tiếp và đường fallback phù hợp không?
- [ ] Có dùng đúng Java release (record patterns/pattern switch: Java 21+) không?
- [ ] Nếu thêm subtype mới, compiler và regression tests còn giúp phát hiện thiếu xử lý không?
- [ ] Feedback review có cụ thể và kiểm chứng được không?

**Kết luận:** Review khả năng đọc của lời giải không phải một cuộc thi rút gọn code. Đó là quá trình làm rõ **ý nghĩa của từng subtype, dữ liệu được deconstruct, điều kiện guard, hành vi khi null và tính đầy đủ của switch**. Một refactor tốt giúp người đọc dự đoán được hành vi bằng cách nhìn vào tên và cấu trúc, đồng thời có bộ test chứng minh hành vi quan trọng không bị thay đổi.

**Tài liệu tham khảo chính thức:**
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — Switch Statements và Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html)
- [Java Language Specification 21 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
