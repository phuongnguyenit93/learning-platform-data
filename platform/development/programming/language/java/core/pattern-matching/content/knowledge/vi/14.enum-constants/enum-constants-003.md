# Pattern type và enum type trong cùng switch — Java 21

## 1. Khi nào cần kết hợp enum constant và type pattern?

`enum` mô tả một tập giá trị hằng được đặt tên, ví dụ trạng thái `NEW`, `RUNNING`, `DONE`. Pattern matching trong `switch` lại giúp phân loại giá trị theo **kiểu runtime** hoặc **cấu trúc**. Từ Java 21, hai cách này có thể xuất hiện trong **cùng một switch block**:

~~~java
return switch (value) {
    case Status.NEW -> "NEW_CONSTANT";
    case Status s -> "OTHER_STATUS:" + s.name();
    case String text -> "TEXT:" + text;
    case null -> "NULL";
    default -> "OTHER";
};
~~~

Đây là **đoạn trích** thuộc phương thức nhận `Object value`, cần có khai báo `enum Status` phù hợp. Nó thể hiện hai ý khác nhau:

- **`case Status.NEW`**: so khớp **chính xác hằng enum `Status.NEW`**, không khai báo pattern variable.
- **`case Status s`**: một **type pattern**, nhận **mọi hằng của enum `Status` còn lại** sau các case trước; khai báo biến `s` kiểu tĩnh `Status` để gọi `s.name()`.
- **`case String text`**: phân loại các giá trị kiểu khác trong cùng switch.
- **`case null`** và `default`: quyết định cách xử lý null và các giá trị còn lại.

Như vậy, “pattern type và enum type trong cùng switch” không có nghĩa enum trở thành một kiểu pattern đặc biệt. Đó là **hai loại nhãn hợp lệ khác nhau**: *enum constant case label* và *case pattern*. Cùng một kiểu enum có thể xuất hiện dưới dạng hằng chính xác hoặc type pattern nhận tất cả giá trị thuộc kiểu đó.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Viết switch trên selector kiểu `enum`, `Object` hoặc interface có các enum implementation.
2. Phân biệt `case NEW`, `case Status.NEW`, `case Status s` và `case Status s when ...`.
3. Biết khi nào **qualified enum constant** như `Status.NEW` là cần thiết, đặc biệt khi selector **không có kiểu tĩnh là enum đó**.
4. Sắp xếp các case constant trước type pattern tổng quát để tránh **dominance**, đồng thời nhận diện các guard có thể làm thay đổi thứ tự chọn nhánh.
5. Hiểu tính **switch compatibility**, phạm vi pattern variable, `null`, `default` và exhaustiveness.
6. Kết hợp nhiều enum thực thi một interface/sealed interface và các pattern kiểu record.
7. Nhận diện lỗi compiler: hằng không tương thích selector, thiếu tên enum, trùng case, pattern che khuất constant, gộp constant với pattern không hợp lệ và thiếu nhánh.

**Phiên bản:** code minh họa dùng **Java 21+**, thời điểm pattern matching for `switch` và cú pháp enum constant có tên đầy đủ chính thức, không cần `--enable-preview`. Dùng JDK 21 trở lên và biên dịch bằng `javac --release 21`.

## 2. Trước hết: enum constant khác type pattern như thế nào?

Giả sử:

~~~java
enum Status {
    NEW, RUNNING, DONE, FAILED
}
~~~

Có bốn cách viết dễ bị nhầm:

| Nhãn case | Loại nhãn | Điều kiện khớp | Biến được khai báo? |
| --- | --- | --- | --- |
| `case NEW` | Hằng enum không có tên kiểu | Giá trị chính là `Status.NEW`, khi selector có ngữ cảnh enum thích hợp | Không |
| `case Status.NEW` | Hằng enum **qualified** | Giá trị chính là `Status.NEW`, kể cả khi selector là `Object` nếu compatible | Không |
| `case Status s` | **Type pattern** | Giá trị không null có runtime type `Status` | Có: `s` kiểu `Status` |
| `case Status s when s == Status.NEW` | Type pattern **có guard** | Khớp `Status` và điều kiện Boolean đúng | Có: `s` |

**Enum constant không phải pattern variable.** Viết `case Status.NEW` không tạo ra biến `NEW` để sử dụng trong rule body; đây là hằng enum duy nhất. Ngược lại, `case Status s` tạo biến `s` để đọc trạng thái đang được xử lý:

~~~java
case Status s -> "STATUS:" + s.name();
~~~

Pattern variable có phạm vi trong guard của nhãn (nếu có) và rule/statement group tương ứng, **không** xuyên sang case khác.

**Kiểu enum là class đặc biệt:** mỗi enum class có một tập hằng đã biết, và các hằng của cùng enum đều là đối tượng thuộc kiểu enum đó. `case Status s` không chọn một hằng riêng; nó kiểm tra kiểu của giá trị.

Nếu selector có kiểu `Status`, bạn có thể dùng `case NEW` theo cách viết enum switch truyền thống. Nhưng nếu selector là `Object`, không thể mặc nhiên viết `case NEW` rồi mong compiler tự suy ra đó là `Status.NEW`. Java 21 cho phép dùng tên đầy đủ `case Status.NEW`.

## 3. Vì sao kiểu tĩnh của selector là điểm xuất phát?

Với biểu thức:

~~~java
switch (expression) {
    // case labels
}
~~~

compiler kiểm tra nhãn dựa trên **kiểu tĩnh** của `expression`. Đây là bước kiểm tra **switch compatibility** trong JLS `14.11.1:

- Một **enum constant case** phải thuộc enum có kiểu tương thích để gán cho kiểu tĩnh của selector.
- Một **type pattern** phải *applicable* với kiểu tĩnh của selector.
- Hằng kiểu số nguyên/chuỗi có quy tắc compatibility riêng; không phải cứ selector là `Object` thì mọi literal constant đều được chấp nhận.
- `null` chỉ dùng khi selector có kiểu tham chiếu.

Ba selector thường gặp:

**Selector là chính enum:**

~~~java
static String classify(Status status) {
    return switch (status) {
        case NEW -> "NEW";
        case RUNNING -> "RUNNING";
        case DONE -> "DONE";
        case FAILED -> "FAILED";
    };
}
~~~

Đây là phương thức minh họa (chưa bao gồm enum), `Status` có đầy đủ bốn hằng như đã khai báo. Switch expression bao phủ toàn bộ các enum constant nên không cần `default`. Tuy nhiên, truyền `null` mà không có `case null` sẽ ném `NullPointerException` tại runtime.

**Selector là `Object`:**

~~~java
static String classify(Object value) {
    return switch (value) {
        case Status.NEW -> "NEW";
        case Status s -> "OTHER_STATUS:" + s;
        case String s -> "TEXT:" + s;
        case null -> "NULL";
        default -> "OTHER";
    };
}
~~~

Các case này là **hằng enum có tên đầy đủ** hoặc **type pattern**. Dùng `case NEW` trần ở đây sẽ không có ngữ cảnh enum `Status` cần thiết.

**Selector là interface mà enum triển khai:** Java 21 có thể dùng trực tiếp `case SomeEnum.VALUE` nếu giá trị enum đó có kiểu tương thích với interface selector. Đây là một ứng dụng quan trọng của qualified enum constants, thay vì buộc viết `case SomeEnum e when e == SomeEnum.VALUE`.

## 4. Chương trình 1: enum constant + enum type pattern + String trong switch(Object)

Lưu chương trình đầy đủ thành `MixedEnumObjectDemo.java`:

~~~java
public class MixedEnumObjectDemo {
    enum Status { NEW, RUNNING, DONE, FAILED }

    static String describe(Object value) {
        return switch (value) {
            case Status.NEW -> "NEW_CONSTANT";
            case Status.DONE -> "DONE_CONSTANT";
            case Status s when s.name().startsWith("FAIL") ->
                "FAIL_PATTERN:" + s;
            case Status s -> "OTHER_STATUS:" + s.name();
            case String text -> "TEXT:" + text;
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(Status.NEW));
        System.out.println(describe(Status.DONE));
        System.out.println(describe(Status.FAILED));
        System.out.println(describe(Status.RUNNING));
        System.out.println(describe("hello"));
        System.out.println(describe(null));
        System.out.println(describe(42));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file:

~~~bash
javac --release 21 MixedEnumObjectDemo.java
java MixedEnumObjectDemo
~~~

Kết quả chính xác:

~~~text
NEW_CONSTANT
DONE_CONSTANT
FAIL_PATTERN:FAILED
OTHER_STATUS:RUNNING
TEXT:hello
NULL
OTHER
~~~

Đọc từng đường đi:

- `Status.NEW` và `Status.DONE` khớp các **constant label** tương ứng trước tiên.
- `Status.FAILED` không khớp hai hằng trên; type pattern `Status s` khớp, guard `s.name().startsWith("FAIL")` trả `true`, kết quả `FAIL_PATTERN:FAILED`.
- `Status.RUNNING` khớp type pattern `Status` nhưng guard không đạt; case `Status s` **không guard** kế tiếp xử lý.
- Chuỗi `"hello"` không phải enum `Status` nên khớp `String text`.
- `null` được xử lý tường minh bằng `case null`.
- `42` được boxing thành `Integer`, không thuộc các kiểu trước nên đi tới `default`.

**Điểm then chốt:** Đây là **một switch duy nhất** thực hiện cả phép so khớp hằng enum, kiểm tra kiểu enum bằng pattern và kiểm tra các kiểu khác. Không cần lồng một switch riêng cho enum vào trong một chuỗi `if/else` dài.

### Guard và thứ tự

Nhãn có guard:

~~~java
case Status s when s.name().startsWith("FAIL") -> "FAIL";
~~~

chỉ chạy guard **sau khi** giá trị khớp kiểu `Status`. Đặt các constant cần ưu tiên và guarded case cụ thể **trước** `case Status s` không guard. Nếu đảo `case Status s` chung lên trước, các constant cùng enum phía sau sẽ bị dominated.

## 5. Chương trình 2: selector enum vẫn kết hợp được case constant và type pattern

Một hiểu nhầm khác: “Nếu selector đã là `enum` thì không thể dùng type pattern nữa”. Điều này sai với Java 21.

Lưu `EnumSelectorPatternDemo.java`:

~~~java
public class EnumSelectorPatternDemo {
    enum Level { LOW, MEDIUM, HIGH }

    static String decide(Level level) {
        return switch (level) {
            case LOW -> "LOW_CONSTANT";
            case Level value when value.ordinal() == 2 -> "HIGH_PATTERN";
            case Level value -> "REST:" + value;
            case null -> "NULL";
        };
    }

    public static void main(String[] args) {
        System.out.println(decide(Level.LOW));
        System.out.println(decide(Level.MEDIUM));
        System.out.println(decide(Level.HIGH));
        System.out.println(decide(null));
    }
}
~~~

~~~bash
javac --release 21 EnumSelectorPatternDemo.java
java EnumSelectorPatternDemo
~~~

Output:

~~~text
LOW_CONSTANT
REST:MEDIUM
HIGH_PATTERN
NULL
~~~

Trong chương trình này:

1. Kiểu tĩnh selector là `Level`, nên `case LOW` viết theo cú pháp enum truyền thống là hợp lệ.
2. `case Level value when ...` là một type pattern với guard; nếu enum có giá trị `HIGH` thì `ordinal() == 2` đúng.
3. `case Level value` không guard nhận mọi giá trị `Level` còn lại. Vì thế với `MEDIUM`, kết quả là `REST:MEDIUM`.
4. `case null` xử lý null riêng. Type pattern `Level value` không khớp null.

**Không lạm dụng `ordinal()` cho nghiệp vụ thực tế.** `ordinal` phụ thuộc thứ tự khai báo enum; thêm, xóa hoặc sắp xếp lại hằng có thể đổi ý nghĩa. Ví dụ trên dùng `ordinal()` để minh họa cách guard đọc pattern variable. Trong ứng dụng, nếu cần trạng thái `HIGH`, hãy ưu tiên `case HIGH`, hoặc dùng thuộc tính nghiệp vụ ổn định khai báo trong enum.

### Trường hợp nào type pattern hữu ích hơn enum constant?

- Bạn muốn nhóm **nhiều hằng còn lại** trong một rule mà không liệt kê hết từng constant.
- Bạn cần gọi phương thức, đọc field hoặc kiểm tra điều kiện phức tạp trên enum thông qua biến pattern.
- Selector là `Object` hoặc interface, và bạn muốn xử lý cả nhóm enum theo kiểu runtime.
- Bạn có một nhánh đặc biệt theo constant, sau đó một nhánh dùng type pattern để xử lý phần còn lại.

Ngược lại, khi chỉ phân biệt một hằng xác định, `case Level.HIGH` hoặc `case HIGH` thường rõ hơn `case Level x when x == Level.HIGH`.

## 6. Qualified enum constants: vì sao Java 21 hỗ trợ?

Trước cú pháp mới của Java 21, các nhãn enum constant trong switch thường gắn chặt với selector có kiểu tĩnh là chính enum đó. Với selector là interface có **nhiều enum triển khai**, cách viết này không đủ linh hoạt.

Java 21 cho phép viết tên enum constant đầy đủ như:

~~~java
case StandardEvent.OPEN -> "STANDARD_OPEN";
case SpecialEvent.ALERT -> "SPECIAL_ALERT";
~~~

trong switch có selector kiểu interface được hai enum này triển khai. Hai enum có thể cùng chứa hằng tên `OPEN` nhưng `StandardEvent.OPEN` và `SpecialEvent.OPEN` là **hai đối tượng khác nhau thuộc hai enum type khác nhau**.

**Vì sao phải qualified?** Selector kiểu interface hoặc `Object` không chỉ ra một enum class duy nhất làm ngữ cảnh cho `OPEN`. Viết `StandardEvent.OPEN` loại bỏ nhập nhằng và giúp compiler kiểm tra kiểu enum đó có compatible với selector hay không.

Ngược lại, với selector trực tiếp có kiểu `StandardEvent`, hai cách viết:

~~~java
case OPEN -> "OPEN";
case StandardEvent.CLOSE -> "CLOSE";
~~~

đều có thể hợp lệ trong các nhãn riêng của một switch phù hợp. Không được khai báo **cùng một hằng** ở cả hai cách viết trong cùng switch (ví dụ `case OPEN` và `case StandardEvent.OPEN`); đó vẫn là **duplicate case label**.

## 7. Chương trình 3: nhiều enum + record trong một sealed-interface switch

Lưu `SealedEnumMixedDemo.java`:

~~~java
sealed interface Event permits StandardEvent, SpecialEvent, TextEvent {}

enum StandardEvent implements Event { OPEN, CLOSE }
enum SpecialEvent implements Event { OPEN, ALERT }
record TextEvent(String message) implements Event {}

public class SealedEnumMixedDemo {
    static String render(Event value) {
        return switch (value) {
            case StandardEvent.OPEN -> "STANDARD_OPEN";
            case SpecialEvent.ALERT -> "SPECIAL_ALERT";
            case StandardEvent e -> "STANDARD:" + e.name();
            case SpecialEvent e -> "SPECIAL:" + e.name();
            case TextEvent(var message) -> "TEXT:" + message;
            case null -> "NULL";
        };
    }

    public static void main(String[] args) {
        System.out.println(render(StandardEvent.OPEN));
        System.out.println(render(StandardEvent.CLOSE));
        System.out.println(render(SpecialEvent.ALERT));
        System.out.println(render(SpecialEvent.OPEN));
        System.out.println(render(new TextEvent("hi")));
        System.out.println(render(null));
    }
}
~~~

~~~bash
javac --release 21 SealedEnumMixedDemo.java
java SealedEnumMixedDemo
~~~

Kết quả:

~~~text
STANDARD_OPEN
STANDARD:CLOSE
SPECIAL_ALERT
SPECIAL:OPEN
TEXT:hi
NULL
~~~

Phân tích:

- `Event` là một **sealed interface** chỉ cho phép ba implementation trực tiếp trong ví dụ: hai enum và một record.
- `StandardEvent.OPEN` và `SpecialEvent.ALERT` là **case constants**, nhắm đúng từng hằng.
- `case StandardEvent e` và `case SpecialEvent e` là **type patterns** cho các hằng enum cùng loại chưa được nhận ở các nhãn trước.
- `case TextEvent(var message)` là **record pattern**, lấy component `message` của đối tượng record.
- `case null` xử lý `null` rõ ràng.

Switch expression này **không cần `default`** vì compiler có thể chứng minh nhánh cho mỗi subtype được phép của sealed interface: `StandardEvent`, `SpecialEvent` và `TextEvent` đều có case pattern tổng quát. Nhãn `null` bổ sung đường xử lý null theo hợp đồng.

**Tại sao hai hằng cùng tên OPEN không bị coi là duplicate?** Chúng thuộc hai enum class khác nhau: `StandardEvent.OPEN` và `SpecialEvent.OPEN` không bằng nhau và không có cùng type. Viết tên đầy đủ đảm bảo rõ cả kiểu và giá trị được khớp.

### Khi nào sealed interface có lợi?

Nếu một domain có nhiều biến thể sự kiện cố định, sealed interface giúp compiler xác định tập lớp con được phép. Switch có thể kết hợp:

- **Enum constants** cho các biến thể trạng thái riêng cần ưu tiên.
- **Enum type patterns** cho tất cả trạng thái còn lại của mỗi enum.
- **Record patterns** cho dữ liệu có cấu trúc khác.
- **Case null** nếu muốn xử lý null một cách tường minh.

Nếu bạn thay đổi tập subtype được phép, cần biên dịch lại và kiểm tra các switch liên quan. Không nên tự thêm `default` chỉ để che đi thiếu sót trong thiết kế phân loại khi mục tiêu là kiểm tra exhaustive bằng compiler.

## 8. Chương trình 4: cùng selector enum, có thể trộn nhãn qualified và unqualified

Lưu `QualifiedEnumConstantsDemo.java`:

~~~java
public class QualifiedEnumConstantsDemo {
    enum Basic { RED, GREEN, BLUE }

    static String classify(Basic color) {
        return switch (color) {
            case Basic.RED -> "R";
            case GREEN -> "G";
            case BLUE -> "B";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(Basic.RED));
        System.out.println(classify(Basic.GREEN));
        System.out.println(classify(Basic.BLUE));
    }
}
~~~

~~~bash
javac --release 21 QualifiedEnumConstantsDemo.java
java QualifiedEnumConstantsDemo
~~~

Kết quả:

~~~text
R
G
B
~~~

Điều này cho thấy trong Java 21, việc chọn qualified hay unqualified form thường phụ thuộc ngữ cảnh kiểu selector và sự rõ ràng mong muốn. `case Basic.RED` và `case RED` cùng chỉ hằng `RED` khi selector là `Basic`; chúng **không phải hai giá trị khác nhau**.

Tất cả ba hằng enum đều được liệt kê nên switch expression exhaustive mà không cần `default`. Tuy nhiên, **không có `case null`**, nên `classify(null)` sẽ gây `NullPointerException` tại runtime.

### Phân biệt null và exhaustiveness

- **Exhaustiveness theo enum constant**: liệt kê toàn bộ giá trị hằng của một enum đủ để compiler chấp nhận switch expression không default.
- **Null**: không phải một hằng enum; Java có quy tắc riêng. Một switch exhaustive theo constant vẫn có thể ném lỗi với null.
- **Default**: nếu bỏ sót hằng enum trong switch expression, `default` có thể giúp bao phủ, nhưng nó không tự nhiên xử lý null theo cách bạn mong muốn.

Không coi `case null` là bắt buộc về cú pháp trong mọi switch; chỉ thêm khi cần xử lý null bằng một nhánh có kết quả riêng.

## 9. Chương trình 5: nhóm nhiều enum constants trong cùng một case

Nếu muốn các hằng enum có cùng ý nghĩa nghiệp vụ, bạn có thể đặt nhiều **case constants** trong một nhãn.

Lưu `EnumGroupedLabelsDemo.java`:

~~~java
public class EnumGroupedLabelsDemo {
    enum Status { NEW, IN_PROGRESS, DONE, BLOCKED }

    static String stage(Object value) {
        return switch (value) {
            case Status.NEW, Status.IN_PROGRESS -> "ACTIVE";
            case Status.DONE, Status.BLOCKED -> "INACTIVE";
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(stage(Status.NEW));
        System.out.println(stage(Status.IN_PROGRESS));
        System.out.println(stage(Status.DONE));
        System.out.println(stage(Status.BLOCKED));
        System.out.println(stage(null));
        System.out.println(stage("x"));
    }
}
~~~

~~~bash
javac --release 21 EnumGroupedLabelsDemo.java
java EnumGroupedLabelsDemo
~~~

Kết quả:

~~~text
ACTIVE
ACTIVE
INACTIVE
INACTIVE
NULL
OTHER
~~~

Cách nhóm này phù hợp vì `Status.NEW`, `Status.IN_PROGRESS`, `Status.DONE` và `Status.BLOCKED` đều là **case constants**. Không có pattern variable nào cần được khởi tạo khác nhau cho các đường đi.

**Nhưng không được trộn enum constant và type pattern trong cùng một nhãn:** đoạn sau cố ý không biên dịch:

~~~java
case Status.NEW, Status s -> "VALUE"; // COMPILE ERROR
~~~

Java 21 báo `invalid case label combination`. Thay vào đó, đặt hai nhãn **riêng**:

~~~java
case Status.NEW -> "NEW";
case Status s -> "OTHER_STATUS:" + s;
~~~

Các đoạn trên giả định switch có selector thích hợp và enum `Status` đã được khai báo; đây là code minh họa, không phải chương trình độc lập. Nếu muốn nhiều hằng chung một nhánh, hãy nhóm **hằng với hằng** thay vì thêm một pattern khai báo biến vào cùng nhãn.

## 10. Thứ tự và dominance: constant trước, pattern tổng quát sau

Một lỗi phổ biến là đặt type pattern rộng trước enum constant cùng kiểu:

~~~java
case Color c -> "COLOR";
case Color.RED -> "RED"; // COMPILE ERROR: dominated
~~~

Nếu selector phù hợp, `case Color c` đã khớp **mọi hằng của Color**, bao gồm `Color.RED`. Compiler từ chối nhãn `Color.RED` ở sau vì nó không bao giờ được chọn.

Cách đúng:

~~~java
case Color.RED -> "RED";
case Color c -> "OTHER_COLOR:" + c.name();
~~~

Điều này là nguyên tắc “**giá trị cụ thể trước, kiểu tổng quát sau**”. Nó áp dụng tương tự cho selector `Object`, interface hay chính kiểu enum nếu type pattern hợp lệ.

### Guard động không nhất thiết dominate constant đứng sau

Thứ tự được cho phép nhưng có thể đáng ngạc nhiên:

~~~java
case Status s when s == Status.NEW -> "GUARDED_NEW";
case Status.NEW -> "CONSTANT_NEW";
case Status s -> "OTHER";
~~~

Đây là **trích đoạn** với `Status` phù hợp. Guard `s == Status.NEW` là điều kiện động, nên Java không nhất thiết xem nó như pattern không guard cho dominance. Với `Status.NEW`, guard đầu đúng và case constant ở sau sẽ **không được chạy**. Code vẫn có thể biên dịch, nhưng dễ gây lỗi logic nếu developer nghĩ constant luôn có ưu tiên cao hơn.

Chương trình hoàn chỉnh `GuardedEnumConstantDemo.java`:

~~~java
public class GuardedEnumConstantDemo {
    enum Status { NEW, ACTIVE, DONE }

    static String select(Status s) {
        return switch (s) {
            case Status value when value == Status.NEW -> "GUARDED_NEW";
            case NEW -> "CONSTANT_NEW";
            case ACTIVE -> "ACTIVE";
            case Status value -> "REST:" + value;
            case null -> "NULL";
        };
    }

    public static void main(String[] args) {
        System.out.println(select(Status.NEW));
        System.out.println(select(Status.ACTIVE));
        System.out.println(select(Status.DONE));
    }
}
~~~

~~~bash
javac --release 21 GuardedEnumConstantDemo.java
java GuardedEnumConstantDemo
~~~

Kết quả:

~~~text
GUARDED_NEW
ACTIVE
REST:DONE
~~~

Với `Status.NEW`, guard phía trước đã chọn nhánh `GUARDED_NEW` nên case `NEW` sau không được chọn, dù cú pháp hợp lệ. Nếu ý định là luôn ưu tiên hằng `NEW`, đặt `case NEW` ở trước guarded pattern.

Nếu một guard là **constant expression `true`**, Java xem nhãn đó như không có guard khi xét dominance. `case Status s when true` đứng trước `case Status.NEW` sẽ gây lỗi dominated tương tự type pattern không guard. Ngược lại, guard là constant expression `false` tự nó không được phép trong nhãn case.

### Mẹo tổ chức code

Thứ tự thực dụng khi kết hợp enum và pattern:

1. Enum constants riêng biệt cần ưu tiên, ví dụ `case Status.NEW`.
2. Type pattern kèm guard cho trạng thái có điều kiện bổ sung, ví dụ `case Status s when s.name().startsWith("FAIL")`.
3. Type pattern không guard cho những hằng còn lại, ví dụ `case Status s`.
4. Các pattern của kiểu khác và fallback thích hợp.

Đây là **chiến lược đọc và bảo trì**, không phải quy tắc tự động xếp ưu tiên: thứ tự thực tế luôn là thứ tự các nhãn trong mã.

## 11. Tương thích kiểu: enum constant không thuộc selector sẽ bị từ chối

Mỗi qualified enum constant vẫn phải **assignment-compatible** với kiểu tĩnh của selector.

Đoạn sau **cố ý không biên dịch**:

~~~java
enum Color { RED }
enum Size { SMALL }

static String test(Size value) {
    return switch (value) {
        case Color.RED -> "RED"; // LỖI: Color không phải Size
        default -> "OTHER";
    };
}
~~~

Nếu đây là code trong một class, compiler báo lỗi dạng:

~~~text
error: incompatible types: Color cannot be converted to Size
~~~

Dùng qualified tên kiểu **không vượt qua** kiểm tra kiểu của Java. Với selector `Size`, một hằng `Color.RED` không compatible nên không thể là case label.

Ngược lại, với selector `Object`, `Color.RED` thuộc một kiểu tham chiếu có thể gán cho `Object`; vì vậy có thể dùng như ví dụ `MixedEnumObjectDemo`. Với selector interface, enum phải thực thi interface đó (hoặc thuộc quan hệ assignment-compatible thích hợp).

### Unqualified constant trong selector Object có phải đủ không?

Ví dụ **cố ý không biên dịch**:

~~~java
enum Color { RED, BLUE }

static String test(Object value) {
    return switch (value) {
        case RED -> "RED"; // Không có enum context Color
        default -> "OTHER";
    };
}
~~~

Compiler báo `cannot find symbol: variable RED` trong ví dụ này. Hãy đổi `case RED` thành `case Color.RED`.

Đừng dùng `import static` để tìm cách lách ngữ cảnh enum khi chưa hiểu loại nhãn: cách rõ ràng, đơn nghĩa cho switch trên `Object` hoặc interface là qualified enum constant.

## 12. Duplicate case constants: cùng hằng enum chỉ được xuất hiện một lần

Trong một switch trên `Color`, hai nhãn:

~~~java
case RED -> "A";
case Color.RED -> "B";
~~~

là **trùng nhau**, dù một nhãn không viết tên enum còn nhãn kia có. `javac --release 21` báo:

~~~text
error: duplicate case label
~~~

Tương tự, `case RED, RED` cũng trùng hằng. Compiler phân biệt hằng theo **giá trị enum**, không dựa vào độ dài cách viết.

Khác với trùng hằng, hai enum class khác nhau có thể cùng khai báo `OPEN`; chúng là **hai giá trị riêng** và có thể cùng xuất hiện trong switch trên một interface hoặc `Object`, miễn mỗi enum constant compatible với selector.

Một nhãn enum constant cũng không khai báo biến pattern; muốn đọc các thuộc tính trên hằng được chọn mà không hardcode thêm thao tác, có thể dùng case pattern tổng quát cùng kiểu trong một nhánh khác.

## 13. Exhaustiveness: enum selector, Object selector và sealed selector

### 13.1. Enum selector

Với:

~~~java
enum Status { NEW, RUNNING, DONE }
~~~

switch expression bao phủ **tất cả** enum constants:

~~~java
return switch (status) {
    case NEW -> "N";
    case RUNNING -> "R";
    case DONE -> "D";
};
~~~

là exhaustive nếu `status` có kiểu `Status`. Không cần `default`. Nhưng nếu chỉ liệt kê `NEW` và `RUNNING`, compiler báo:

~~~text
error: the switch expression does not cover all possible input values
~~~

Một pattern `case Status s` không guard có thể nhận các enum constants chưa liệt kê và giúp bảo đảm coverage, miễn các nhãn không bị dominated.

### 13.2. Object selector

Với `switch (Object value)`, chỉ có các hằng `Status.NEW`, `Status.DONE` thì **không exhaustive** vì `value` còn có thể là bất kỳ lớp nào khác. Phải có `default`, một type pattern tổng quát thích hợp, hoặc cách bao phủ khác được Java chấp nhận.

Ví dụ `MixedEnumObjectDemo` dùng `default` vì selector là `Object` và có nhiều loại không được liệt kê.

### 13.3. Sealed interface selector

Nếu selector có kiểu sealed interface và switch chứa case patterns bao phủ tất cả implementation được phép, compiler có thể chứng minh exhaustive **không cần `default`**. Ví dụ `SealedEnumMixedDemo` dùng các case `StandardEvent e`, `SpecialEvent e`, `TextEvent(...)` để bao phủ ba subtype, còn enum constant cases để xử lý hằng đặc biệt.

**Lưu ý:** liệt kê một vài enum constants từ mỗi subtype chưa chắc đã bao phủ toàn bộ subtype. Nếu muốn exhaustive bằng enum constants, phải bao phủ các trường hợp theo đúng quy tắc JLS; dùng type pattern không guard cho từng enum subtype thường đơn giản hơn.

### 13.4. Null

Dù một switch expression được coi là exhaustive ở compile time, truyền `null` vẫn có thể làm nó ném `NullPointerException` nếu không có nhãn xử lý null thích hợp. `default` không mặc nhiên xử lý null như giá trị bình thường của pattern switch.

Vì vậy, quyết định `case null` theo hợp đồng API; không nhầm nó với hằng enum nào.

## 14. Switch statement và switch expression đều phối hợp được

Dùng switch expression khi cần **một giá trị**:

~~~java
String result = switch (value) {
    case Status.NEW -> "NEW";
    case Status s -> "STATUS:" + s;
    case null -> "NULL";
    default -> "OTHER";
};
~~~

Dùng switch statement khi cần thực hiện **hành động**:

~~~java
switch (value) {
    case Status.NEW -> System.out.println("NEW");
    case Status s -> System.out.println("STATUS:" + s);
    case null -> System.out.println("NULL");
    default -> System.out.println("OTHER");
}
~~~

Hai đoạn là trích đoạn cần khai báo `enum Status` và biến `Object value` trong một phương thức.

Với rule mũi tên `->`, không có fall-through. Nếu dùng dạng dấu hai chấm `case ...:`, cần kiểm soát `break` hoặc `return`; Java còn hạn chế việc fall-through **vào** nhãn pattern khai báo biến, vì biến đó có thể chưa được khởi tạo.

**Một lưu ý Java 21:** switch statement thuộc loại *enhanced switch statement* khi có pattern, nhãn null hoặc selector thuộc một số loại tham chiếu rộng (như `Object`); khi đó phải exhaustive theo quy tắc của Java 21. Đừng nhầm với switch statement enum truyền thống không dùng pattern, vốn được duy trì một số quy tắc tương thích ngược về exhaustiveness.

## 15. Các lỗi thường gặp và cách sửa

Các đoạn sau minh họa tình huống cố ý sai. Những kết luận về lỗi đã được đối chiếu với `javac --release 21`.

| Tình huống | Dấu hiệu/lỗi | Cách sửa |
| --- | --- | --- |
| `case RED` trong `switch(Object)` mà không có enum context | `cannot find symbol: variable RED` | Dùng `case Color.RED` |
| `case Color.RED` trong `switch(Size)`, hai enum không liên quan | `Color cannot be converted to Size` | Chỉ dùng enum constant assignment-compatible với selector |
| `case Color c` trước `case Color.RED` | `dominated by a preceding case label` | Constant trước type pattern chung |
| `case RED` và `case Color.RED` trong cùng switch | `duplicate case label` | Chỉ dùng một nhãn cho hằng đó |
| `case RED when true` | Sai cú pháp/guard không gắn trực tiếp lên constant | Dùng `case RED` hoặc `case Color c when ...` |
| `case Color.RED, Color c` | `invalid case label combination` | Tách thành hai case labels riêng |
| Switch expression enum bỏ sót hằng mà không có fallback | `switch expression does not cover all possible input values` | Liệt kê đủ hằng hoặc thêm nhánh bao phủ hợp lệ |
| Type pattern chung đặt trước hằng của cùng enum | Hằng bị dominated | Đưa hằng đặc biệt lên trước |
| Đoán `default` sẽ bắt null | Có thể ném `NullPointerException` | Viết `case null` nếu muốn xử lý |
| Dùng `ordinal()` để định danh trạng thái lâu dài | Dễ vỡ khi đổi thứ tự khai báo enum | Dùng tên hằng hoặc thuộc tính ổn định |

### Ví dụ 1 — Constant sau pattern chung bị dominated

~~~java
static String invalid(Object value) {
    return switch (value) {
        case Color c -> "COLOR";
        case Color.RED -> "RED"; // COMPILE ERROR
        default -> "OTHER";
    };
}
~~~

Đoạn trích nằm trong class có `enum Color { RED, BLUE }`. Case `Color c` đã bao phủ `Color.RED`.

### Ví dụ 2 — Nhãn có guard chỉ gắn với pattern

~~~java
static String invalid(Color value) {
    return switch (value) {
        case RED when true -> "RED"; // COMPILE ERROR
        default -> "OTHER";
    };
}
~~~

Thay bằng:

~~~java
case RED -> "RED";
~~~

Nếu cần điều kiện phụ, dùng:

~~~java
case Color c when customCondition(c) -> "MATCH";
~~~

Ở đây `customCondition(Color)` là phương thức Boolean minh họa do ứng dụng tự định nghĩa, không phải API Java Core sẵn có.

### Ví dụ 3 — Constant và type pattern không cùng một nhãn

~~~java
case Color.RED, Color c -> "COLOR"; // COMPILE ERROR
~~~

Thay bằng:

~~~java
case Color.RED -> "RED";
case Color c -> "OTHER_COLOR";
~~~

Java chỉ cho gộp nhiều **case constants** trong một nhãn theo cú pháp tương ứng. Một pattern giới thiệu biến không thể trộn với constant trong cùng nhãn.

## 16. Bài tập tự kiểm tra và đáp án

### Bài 1 — Đọc output của switch(Object)

Với `enum State { NEW, DONE }`:

~~~java
static String inspect(Object x) {
    return switch (x) {
        case State.NEW -> "NEW";
        case State s -> "STATE:" + s;
        case String s -> "TEXT";
        case null -> "NULL";
        default -> "OTHER";
    };
}
~~~

Hãy dự đoán kết quả của `inspect(State.NEW)`, `inspect(State.DONE)`, `inspect("x")`, `inspect(null)` và `inspect(3)`.

**Đáp án:** `NEW`, `STATE:DONE`, `TEXT`, `NULL`, `OTHER`. Case constant bắt riêng `NEW`, type pattern `State s` bắt hằng còn lại, pattern `String` bắt chuỗi và default bắt số nguyên.

### Bài 2 — Sửa tên hằng trong selector Object

Trong `switch(Object value)`, tại sao:

~~~java
case OPEN -> "OPEN";
~~~

có thể sai khi `OPEN` là hằng enum của `EventType`?

**Đáp án:** Selector `Object` không cung cấp enum context tự suy ra `EventType.OPEN`. Viết `case EventType.OPEN -> "OPEN";` nếu enum constant compatible với selector.

### Bài 3 — Sắp xếp case đúng

Sắp xếp hai case sau sao cho vẫn có thể xử lý riêng hằng `Color.RED`:

~~~java
case Color c -> "COLOR";
case Color.RED -> "RED";
~~~

**Đáp án:**

~~~java
case Color.RED -> "RED";
case Color c -> "COLOR";
~~~

### Bài 4 — Hai enum có hằng cùng tên

Giả sử `enum A implements Event { OPEN }` và `enum B implements Event { OPEN }`, với `Event` là interface hợp lệ. Hai nhãn `case A.OPEN` và `case B.OPEN` có là duplicate không?

**Đáp án:** Không. Hai hằng thuộc hai enum type khác nhau, đều có thể hợp lệ trong switch selector `Event` nếu assignment-compatible. Viết qualified name để phân biệt rõ.

### Bài 5 — Exhaustiveness với enum selector

Với `enum Mode { START, STOP, PAUSE }`, switch expression chỉ có `case START` và `case STOP` có hợp lệ nếu không có `default` không?

**Đáp án:** Không exhaustive vì bỏ sót `PAUSE`. Có thể thêm `case PAUSE`, `default` hoặc một pattern thích hợp nhận các hằng còn lại.

### Bài 6 — Guard trên enum type pattern

Đoạn sau có thể biên dịch nhưng trả kết quả bất ngờ như thế nào?

~~~java
case Status s when s == Status.NEW -> "GUARD";
case Status.NEW -> "CONST";
case Status s -> "OTHER";
~~~

**Đáp án:** Với `Status.NEW`, guard đầu đúng nên kết quả là `GUARD`; case constant phía sau không chạy. Nếu muốn constant được ưu tiên, chuyển `case Status.NEW` lên trước.

### Bài 7 — Null và default

Nếu một switch expression liệt kê đủ enum constants nhưng không có `case null`, điều gì có thể xảy ra khi truyền `null`? Liệu thêm `default` có tự biến null thành hằng enum không?

**Đáp án:** Runtime có thể ném `NullPointerException`; `null` không phải enum constant. `default` không tự xử lý null theo cách mong muốn trong pattern switch. Viết `case null` nếu API cần trả kết quả thay vì ném lỗi.

### Bài 8 — Gộp hằng và pattern

Có được viết:

~~~java
case State.NEW, State s -> "STATE";
~~~

không?

**Đáp án:** Không, Java 21 báo `invalid case label combination`. Có thể gộp nhiều hằng như `case State.NEW, State.DONE`, hoặc tách constant và pattern ra hai nhánh độc lập.

## 17. Checklist khi review switch kết hợp enum và pattern

Trước khi hoàn tất, kiểm tra:

1. Kiểu tĩnh selector là **enum cụ thể**, `Object` hay interface nào?
2. Với enum constant, nhãn cần qualified (`Status.NEW`) hay có thể dùng unqualified (`NEW`)?
3. Mọi enum constant có **assignment-compatible** với selector không?
4. Bạn đang cần khớp **một hằng** hay **mọi hằng của enum type**? Dùng constant hoặc type pattern đúng mục đích.
5. Các hằng đặc biệt đã đứng **trước** type pattern không guard cùng kiểu chưa?
6. Guard có trả Boolean và có dùng pattern variable đúng phạm vi không?
7. Hai case có trùng cùng một hằng, kể cả một dạng qualified và một dạng unqualified, không?
8. Có đang gộp constant với pattern trong cùng một nhãn không hợp lệ không?
9. Nếu selector là sealed interface, các case có bao phủ tất cả subtype được phép chưa?
10. Nếu selector là enum, switch expression đã bao phủ đủ hằng hoặc có fallback thích hợp chưa?
11. `null` được xử lý theo đúng hợp đồng API chưa?
12. Có test thực tế cho các giá trị enum mà nhiều case có thể cùng khớp (constant + guarded pattern + type pattern) không?
13. Đang biên dịch với Java 21+ và không vô tình dùng các quy tắc preview cũ của Java 17–20 chứ?

**Ghi nhớ:** `case EnumType.VALUE` kiểm tra **một enum constant**; `case EnumType variable` kiểm tra **kiểu enum** và giới thiệu pattern variable. Java 21 cho phép phối hợp chúng trong cùng switch trên enum, `Object` hoặc interface tương thích. **Thứ tự nhãn và khả năng bao phủ quyết định cả tính hợp lệ khi biên dịch lẫn hành vi runtime.**

### Tài liệu tham khảo

- Oracle Java 21 — Pattern Matching for switch, mục *Qualified enum Constants as case Constants*: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- JLS Java SE 21 `14.11.1 — Switch Blocks, compatibility, dominance, enum case labels: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1
- JLS Java SE 21 `14.11.1.1 — Exhaustive Switch Blocks: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1
- JLS Java SE 21 `15.28 — Switch Expressions: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28
- OpenJDK JEP 441 — Pattern Matching for switch (Java 21): https://openjdk.org/jeps/441
