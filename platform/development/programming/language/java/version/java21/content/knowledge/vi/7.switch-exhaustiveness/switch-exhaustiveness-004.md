# Exhaustiveness với enum và qualified enum constant

## 1. Exhaustiveness là gì?

Một `switch` được gọi là **exhaustive** (đầy đủ) khi các case label bao phủ mọi giá trị có thể thuộc kiểu của selector theo quy tắc của Java. Khi switch exhaustive, người đọc có thể xác định rằng mọi trường hợp hợp lệ đều được xử lý hoặc được chuyển đến một nhánh dự phòng đã định nghĩa.

Với `enum`, compiler biết trước tập hằng số được khai báo trong enum. Vì vậy, nếu selector có kiểu enum, Java có thể xác định tính đầy đủ bằng cách kiểm tra các enum constant đã xuất hiện trong các case label.

```java
enum OrderStatus {
    CREATED,
    PAID,
    SHIPPED,
    CANCELLED
}

static String describe(OrderStatus status) {
    return switch (status) {
        case CREATED -> "Order created";
        case PAID -> "Payment received";
        case SHIPPED -> "Order shipped";
        case CANCELLED -> "Order cancelled";
    };
}
```

Đây là một `switch` expression exhaustive vì cả bốn hằng số của `OrderStatus` đều được xử lý. Không cần viết `default` chỉ để làm cho switch expression này đầy đủ.

Exhaustiveness đặc biệt quan trọng với switch expression vì expression phải tạo ra một giá trị hoặc kết thúc bằng exception trên mọi đường thực thi. Java cũng áp dụng quy tắc exhaustiveness cho enhanced switch statement, giúp tránh trường hợp một nhánh không được xử lý mà chương trình vẫn tiếp tục âm thầm.

## 2. Exhaustiveness khi selector có kiểu enum

### 2.1. Liệt kê tất cả enum constant trong switch expression

Nếu selector có kiểu enum `E`, tập case element không có guard phải chứa tên của tất cả enum constant thuộc `E` để switch được xem là exhaustive mà không cần `default`.

```java
enum Priority {
    LOW,
    NORMAL,
    HIGH
}

static int weight(Priority priority) {
    return switch (priority) {
        case LOW -> 1;
        case NORMAL -> 2;
        case HIGH -> 3;
    };
}
```

Nếu bỏ `case HIGH`, compiler báo switch expression không exhaustive. Có thể thay việc liệt kê đầy đủ bằng `default` khi thực sự muốn gom mọi trường hợp còn lại vào cùng một nhánh:

```java
static int weight(Priority priority) {
    return switch (priority) {
        case LOW -> 1;
        case NORMAL -> 2;
        default -> 3;
    };
}
```

Trong ví dụ thứ hai, `default` làm switch exhaustive nhưng compiler không còn yêu cầu source phải liệt kê từng enum constant. Nếu sau này `Priority` được bổ sung `URGENT`, nhánh `default` cũng sẽ xử lý giá trị mới. Đây là lựa chọn phù hợp khi các giá trị mới có cùng chính sách xử lý; nếu mỗi trạng thái cần logic riêng, hãy liệt kê rõ từng constant để compiler hỗ trợ phát hiện thay đổi.

### 2.2. Gộp nhiều enum constant trong một case label

Các constant có cùng hành vi có thể được đặt chung trong một case label, phân tách bằng dấu phẩy:

```java
enum DayType {
    MONDAY,
    TUESDAY,
    WEDNESDAY,
    THURSDAY,
    FRIDAY,
    SATURDAY,
    SUNDAY
}

static String group(DayType day) {
    return switch (day) {
        case MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY -> "Weekday";
        case SATURDAY, SUNDAY -> "Weekend";
    };
}
```

Mỗi enum constant vẫn được tính vào tập giá trị đã bao phủ dù nhiều constant nằm trong cùng một label. Điều quan trọng là không bỏ sót constant và không lặp lại cùng một constant trong các label khác nhau.

Với selector có kiểu enum, cách viết thông dụng là tên constant không kèm tên enum, ví dụ `case MONDAY`. Tên constant được phân giải dựa trên kiểu enum của selector.

### 2.3. `null` không phải enum constant

Một enum variable có thể chứa `null`, nhưng `null` không thuộc tập enum constant. Vì vậy, liệt kê đủ các constant không có nghĩa là switch tự động xử lý `null`.

```java
static String describe(Priority priority) {
    return switch (priority) {
        case null -> "Priority not provided";
        case LOW -> "Low priority";
        case NORMAL -> "Normal priority";
        case HIGH -> "High priority";
    };
}
```

`case null` xử lý riêng selector `null`. Nếu không có label này, switch nhận selector `null` sẽ ném `NullPointerException`, kể cả khi đã liệt kê tất cả enum constant hoặc có `default` thông thường.

## 3. Phân biệt switch expression và switch statement trên enum

Java 21 có một khác biệt quan trọng về yêu cầu exhaustive giữa switch expression và switch statement.

| Cấu trúc | Khi selector là enum và chỉ dùng enum constant labels | Yêu cầu exhaustive |
|---|---|---|
| `switch` expression | Phải xử lý tất cả enum constant hoặc có `default` | Bắt buộc |
| `switch` statement kiểu truyền thống | Có thể bỏ sót enum constant | Không bắt buộc vì lý do tương thích |
| Enhanced `switch` statement có `case null` hoặc pattern | Phải xử lý đầy đủ các trường hợp theo kiểu selector | Bắt buộc |

Ví dụ dưới đây là switch statement chỉ dùng enum constant labels. Dù không có `case SHIPPED` hoặc `default`, đoạn mã vẫn hợp lệ trong Java 21:

```java
enum ShipmentStatus {
    CREATED,
    SHIPPED,
    DELIVERED
}

static void logStatus(ShipmentStatus status) {
    switch (status) {
        case CREATED -> System.out.println("Created");
        case DELIVERED -> System.out.println("Delivered");
    }
}
```

Đây là switch statement kiểu truyền thống vì selector có kiểu enum và switch block không chứa pattern label hoặc `null` label. Nếu `status` là `SHIPPED`, không label nào áp dụng và switch statement hoàn tất bình thường mà không thực hiện nhánh nào.

Nếu thêm `case null`, switch statement trở thành **enhanced switch statement**. Khi đó nó phải exhaustive:

```java
static void logStatus(ShipmentStatus status) {
    switch (status) {
        case null -> System.out.println("Missing status");
        case CREATED -> System.out.println("Created");
        case SHIPPED -> System.out.println("Shipped");
        case DELIVERED -> System.out.println("Delivered");
    }
}
```

Trong ví dụ này, compiler yêu cầu bao phủ cả ba enum constant; `case null` xử lý thêm giá trị null. Nếu bỏ `case SHIPPED`, enhanced switch statement không exhaustive và không biên dịch.

Quy tắc này giúp giữ tương thích với các switch statement enum đã tồn tại trước Java 21, trong khi switch expression và enhanced switch statement được kiểm tra tính đầy đủ ngay khi biên dịch.

## 4. Qualified enum constant là gì?

Khi selector có kiểu chính là enum, có thể dùng tên constant không kèm tên enum, ví dụ:

```java
case CREATED -> ...
```

Nhưng nếu selector có kiểu là một interface chung được nhiều enum triển khai, Java không thể dựa vào kiểu selector để xác định một tên constant không định danh thuộc enum nào. Khi đó, dùng **qualified enum constant** bằng cách ghi đầy đủ tên enum và constant:

```java
case WorkflowStatus.CREATED -> ...
case SyncStatus.RUNNING -> ...
```

Một qualified enum constant là một enum constant được viết kèm tên enum chứa nó. Nó vẫn là một **case constant**, không phải type pattern. Java so sánh giá trị selector với chính enum constant đó.

Điều kiện quan trọng là kiểu của enum constant phải assignment-compatible với kiểu tĩnh của selector. Ví dụ, nếu selector có kiểu `ProcessStatus`, thì các enum `WorkflowStatus` và `SyncStatus` có thể dùng làm case constant nếu chúng triển khai `ProcessStatus`.

## 5. Dùng qualified enum constants với sealed interface

Qualified enum constants hữu ích khi một sealed interface được triển khai bởi nhiều enum. Mỗi enum có thể định nghĩa một tập constant riêng, kể cả khi tên constant giống nhau.

```java
sealed interface CardClassification permits Standard, Tarot {}

enum Standard implements CardClassification {
    SPADE,
    HEART,
    DIAMOND,
    CLUB
}

enum Tarot implements CardClassification {
    SPADE,
    HEART,
    DIAMOND,
    CLUB,
    TRUMP,
    EXCUSE
}

static String describe(CardClassification card) {
    return switch (card) {
        case Standard.SPADE -> "Spades";
        case Standard.HEART -> "Hearts";
        case Standard.DIAMOND -> "Diamonds";
        case Standard.CLUB -> "Clubs";
        case Tarot.SPADE -> "Spades or Piques";
        case Tarot.HEART -> "Hearts or Coeur";
        case Tarot.DIAMOND -> "Diamonds or Carreaux";
        case Tarot.CLUB -> "Clubs or Trefles";
        case Tarot.TRUMP -> "Trumps";
        case Tarot.EXCUSE -> "The Fool";
    };
}
```

Selector có kiểu `CardClassification`, không phải kiểu enum. Vì vậy, mỗi enum constant được viết dưới dạng qualified name như `Standard.SPADE` hoặc `Tarot.TRUMP`.

Switch expression trên exhaustive mà không cần `default` vì:

1. `CardClassification` là sealed interface và chỉ cho phép hai kiểu con trực tiếp là `Standard` và `Tarot`.
2. `Standard` là enum và tất cả constant của nó đều được liệt kê.
3. `Tarot` là enum và tất cả constant của nó đều được liệt kê.
4. Không còn kiểu con được phép nào khác của `CardClassification` cần xử lý.

Compiler dùng tập permitted direct subclasses của sealed interface cùng tập enum constant để xác định type coverage. Do đó, việc liệt kê tất cả constant của từng enum subtype có thể làm cho switch trên sealed supertype exhaustive.

### 5.1. Vì sao cần qualified name?

Hai enum `Standard` và `Tarot` đều khai báo `SPADE`, `HEART`, `DIAMOND` và `CLUB`. Nếu selector là `CardClassification`, viết `case SPADE` không xác định rõ constant thuộc enum nào. Qualified name làm rõ danh tính constant và bảo đảm mỗi case label tham chiếu đúng giá trị.

### 5.2. Khi sealed hierarchy có thêm kiểu con khác

Nếu sealed interface có thêm một record hoặc class được phép, switch phải bao phủ kiểu đó nữa. Ví dụ:

```java
sealed interface Result permits ResultCode, MessageResult {}

enum ResultCode implements Result {
    SUCCESS,
    FAILURE
}

record MessageResult(String message) implements Result {}

static String describe(Result result) {
    return switch (result) {
        case ResultCode.SUCCESS -> "Success";
        case ResultCode.FAILURE -> "Failure";
        case MessageResult message -> message.message();
    };
}
```

Các enum constant bao phủ mọi giá trị của `ResultCode`; type pattern `MessageResult message` bao phủ kiểu record còn lại. Vì `Result` là sealed và mọi permitted subtype đều được bao phủ, switch expression exhaustive.

Nếu một permitted subtype là `non-sealed`, subtype đó có thể có các lớp con chưa biết tại thời điểm biên dịch. Khi đó, cần một type pattern bao phủ subtype mở đó hoặc `default`; chỉ liệt kê một số enum constant của các nhánh khác là chưa đủ.

## 6. Qualified enum constants không tự làm mọi switch exhaustive

Qualified enum constant chỉ bao phủ đúng một giá trị enum. Nó không đại diện cho mọi instance thuộc kiểu selector.

Ví dụ, selector có kiểu `Object` có thể chứa string, number, record hoặc bất kỳ object nào khác. Dù liệt kê tất cả constant của `WorkflowStatus`, switch vẫn không exhaustive với kiểu `Object`:

```java
enum WorkflowStatus {
    CREATED,
    RUNNING,
    FINISHED
}

static String describe(Object value) {
    return switch (value) {
        case WorkflowStatus.CREATED -> "Created";
        case WorkflowStatus.RUNNING -> "Running";
        case WorkflowStatus.FINISHED -> "Finished";
        default -> "Other object";
    };
}
```

`default` cần thiết vì selector là `Object`, một kiểu mở có thể chứa nhiều loại giá trị ngoài `WorkflowStatus`. Tập enum constant chỉ bao phủ các giá trị cụ thể của `WorkflowStatus`, không bao phủ toàn bộ `Object`.

Ngược lại, với selector có kiểu sealed interface mà tất cả permitted subtype đều là các enum đã được liệt kê đầy đủ, compiler có đủ thông tin để chứng minh coverage mà không cần `default`.

## 7. Ảnh hưởng khi enum được mở rộng

Thêm một enum constant vào enum class là thay đổi binary-compatible đối với các binary đã biên dịch. Tuy nhiên, một switch exhaustive được biên dịch trước đó có thể gặp constant mới mà nó chưa biết.

Ví dụ, phiên bản đầu của enum:

```java
enum ConnectionState {
    DISCONNECTED,
    CONNECTED
}
```

Switch expression được biên dịch khi enum chỉ có hai constant:

```java
static String message(ConnectionState state) {
    return switch (state) {
        case DISCONNECTED -> "Offline";
        case CONNECTED -> "Online";
    };
}
```

Sau đó, thư viện enum được cập nhật và bổ sung `CONNECTING`, nhưng class chứa switch chưa được biên dịch lại. Khi nhận `CONNECTING`, không có case label nào trong binary cũ khớp. Với switch expression liệt kê đầy đủ enum constant tại thời điểm biên dịch, compiler tạo một implicit `default` để bảo vệ trường hợp enum được mở rộng; nếu fallback này được thực thi, switch expression kết thúc bằng `MatchException`.

Vì vậy, khi nâng cấp thư viện có enum:

- Biên dịch lại các module có switch expression exhaustive trên enum để compiler phát hiện constant mới.
- Quyết định rõ constant mới cần hành vi riêng hay có thể dùng chung nhánh `default`.
- Với switch statement enum kiểu truyền thống không exhaustive, kiểm tra xem constant mới có thể khiến luồng xử lý không chạy nhánh nào hay không.
- Nếu switch dùng qualified enum constants trên sealed interface, cập nhật và biên dịch lại switch khi một enum subtype được bổ sung constant mới.

Không nên xem việc compiler chấp nhận switch là bằng chứng rằng binary cũ tự hiểu được mọi enum constant được thêm trong tương lai. Exhaustiveness được kiểm tra dựa trên thông tin kiểu và enum constant có tại thời điểm biên dịch.

## 8. Quy trình kiểm tra exhaustiveness

Khi thiết kế một switch có enum hoặc qualified enum constant, hãy thực hiện lần lượt:

1. **Xác định kiểu tĩnh của selector**: selector có kiểu enum trực tiếp, sealed interface, interface thông thường hay `Object`?
2. **Nếu selector là enum**: liệt kê toàn bộ enum constant, gộp constant có cùng hành vi nếu cần.
3. **Nếu selector không phải enum**: chỉ dùng qualified enum constant khi kiểu constant assignment-compatible với selector.
4. **Nếu selector là sealed type**: xem toàn bộ permitted direct subtype; với subtype là enum, liệt kê tất cả constant; với subtype class/record, dùng pattern bao phủ kiểu đó.
5. **Kiểm tra kiểu mở**: nếu có subtype `non-sealed` hoặc selector là kiểu mở như `Object`, thêm pattern tổng quát phù hợp hoặc `default`.
6. **Xử lý `null` riêng**: nếu đầu vào có thể null và cần hành vi rõ ràng, thêm `case null`.
7. **Chọn switch expression hoặc statement**: switch expression luôn cần exhaustive; switch statement enum chỉ dùng constant labels có thể vẫn là legacy switch không bắt buộc exhaustive.
8. **Biên dịch lại khi mô hình enum thay đổi**: kiểm tra mọi switch liên quan sau khi enum thêm hoặc xóa constant.

## 9. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Switch expression thiếu một enum constant | Tập case constant chưa bao phủ enum | Thêm constant còn thiếu hoặc dùng `default` có chủ đích |
| Nghĩ `default` xử lý được `null` | `default` không khớp null selector | Thêm `case null` nếu cần xử lý null |
| Dùng tên enum constant không định danh khi selector là interface | Không xác định enum chứa constant | Dùng `EnumType.CONSTANT` |
| Switch trên `Object` chỉ liệt kê enum constant nhưng không có `default` | Enum constants không bao phủ toàn bộ Object | Thêm `default` hoặc pattern bao phủ các loại còn lại |
| Bỏ sót constant trong enum subtype của sealed interface | Sealed coverage chưa bao phủ enum subtype đó | Liệt kê tất cả constant hoặc dùng pattern phù hợp bao phủ enum subtype |
| Cho rằng mọi enum switch statement đều phải exhaustive | Nhầm legacy switch statement với enhanced switch statement | Kiểm tra selector type và việc switch có pattern hoặc `null` label không |

## 10. Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 21 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): quy tắc coverage cho enum và sealed hierarchy.
- [Java Language Specification, Java SE 21 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): tính tương thích kiểu selector, enum constant labels và enhanced switch statement.
- [Java Language Specification, Java SE 21 — Run-Time Evaluation of switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28.2): hành vi khi không có switch label áp dụng.
- [Java Language Specification, Java SE 21 — Evolution of Enum Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.26): ảnh hưởng khi thêm hoặc thay đổi enum constant đối với binary đã biên dịch.
- [Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): qualified enum constants và ví dụ enum triển khai sealed interface.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): thiết kế và trạng thái chính thức của pattern switch trong Java 21.

Khi kiểm tra exhaustiveness, hãy bắt đầu từ kiểu tĩnh của selector. Với enum selector, mọi enum constant phải được bao phủ trong switch expression. Với sealed supertype, có thể dùng qualified enum constants để bao phủ từng enum subtype nếu liệt kê đủ constant của chúng. Luôn tách riêng chính sách `null` và lưu ý sự khác nhau giữa switch expression, enhanced switch statement và legacy enum switch statement.
