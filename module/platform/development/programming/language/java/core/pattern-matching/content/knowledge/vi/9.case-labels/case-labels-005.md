# Qualified enum constant trong case (Java 21+)

## 1. Qualified enum constant là gì?

Trong Java, một `enum` khai báo tập hằng đã được đặt tên, ví dụ `Color.RED`, `Color.GREEN` và `Color.BLUE`. **Qualified enum constant** là cách viết một hằng enum kèm tên kiểu enum sở hữu nó:

```java
enum Color { RED, GREEN, BLUE }

// Một nhãn case dùng hằng enum có tên kiểu:
case Color.RED -> "red";
```

Nhãn trên có hai phần: `Color` là **kiểu enum**; `RED` là **một hằng cụ thể của enum đó**. Trong `switch`, nó chỉ chọn nhánh khi giá trị selector đúng bằng hằng `Color.RED`.

Bài này tập trung vào **qualified enum constant trong case label**, đặc biệt khi kết hợp với **pattern matching for switch** được chuẩn hóa trong **Java 21 (JEP 441)**. Từ Java 21, các nhãn enum có dạng `case Color.RED` có thể xuất hiện trong nhiều tình huống hơn, kể cả khi selector có kiểu tĩnh `Object` hoặc một interface mà enum triển khai.

Đừng nhầm ba dạng sau:

- `case Color.RED -> ...`: nhãn **hằng enum cụ thể**; chỉ khớp hằng `RED` của `Color`.
- `case Color color -> ...`: **type pattern**; khớp các giá trị khác `null` thuộc **bất kỳ hằng nào** của `Color` và khai báo biến `color`.
- `case RED -> ...`: **hằng enum không có qualifier**, thường dùng trong switch truyền thống khi selector đã có kiểu `Color`.

Cần hiểu rõ sự khác nhau giữa **khớp một hằng** và **khớp một kiểu** để tránh lỗi dominance và lựa chọn nhầm nhánh.

## 2. Từ switch enum truyền thống đến switch có pattern

### Cách viết quen thuộc trước Java 21

Khi selector có kiểu tĩnh là chính enum, switch kiểu truyền thống thường dùng các tên hằng **không có tên enum đi trước**:

```java
enum Color { RED, GREEN, BLUE }

static String legacyName(Color color) {
    return switch (color) {
        case RED -> "red";
        case GREEN -> "green";
        case BLUE -> "blue";
    };
}
```

Đoạn này hợp lệ trên Java 17. Vì selector đã có kiểu `Color`, compiler xác định `RED`, `GREEN` và `BLUE` thuộc enum nào. Với Java 17, viết `case Color.RED` ở vị trí đó dẫn đến lỗi biên dịch yêu cầu enum case label phải dùng tên **unqualified**.

### Cách viết qualified từ Java 21

Java 21 chấp nhận cách viết đầy đủ ngay cả khi selector có kiểu `Color`:

```java
static String qualifiedName(Color color) {
    return switch (color) {
        case Color.RED -> "red";
        case Color.GREEN -> "green";
        case Color.BLUE -> "blue";
    };
}
```

Hai phương thức ở trên đều chọn đúng cùng các giá trị `Color`. Với `qualifiedName(Color.RED)`, kết quả là `"red"`.

Điểm mở rộng quan trọng hơn là switch có pattern trên một kiểu **rộng hơn**:

```java
static String describe(Object value) {
    return switch (value) {
        case Color.RED -> "red";
        case Color.GREEN -> "green";
        case Color.BLUE -> "blue";
        default -> "not a Color";
    };
}
```

Selector ở đây có kiểu tĩnh `Object`, vì vậy kiểu enum không thể được suy ra từ selector. Viết `Color.RED` xác định rõ **hằng của kiểu nào** đang được dùng làm nhãn. Với `describe(Color.RED)`, kết quả là `"red"`; với `describe("RED")`, kết quả là `"not a Color"`.

**Yêu cầu phiên bản:** ví dụ có `switch (Object)` với enum-qualified `case` phải dùng **Java 21+** theo cú pháp chuẩn, không cần `--enable-preview`. Việc ép Java 17 chấp nhận mẫu cú pháp này sẽ không thành công chỉ bằng cách đổi sang một tên hằng khác.

## 3. Khi nào nên dùng tên qualified?

Tên qualified đặc biệt hữu ích trong các tình huống sau.

**Trường hợp 1: selector có kiểu `Object`.**

```java
Object input = Color.GREEN;

String text = switch (input) {
    case Color.RED -> "stop";
    case Color.GREEN -> "go";
    case Color.BLUE -> "info";
    default -> "unknown";
};
```

Selector có thể chứa nhiều loại đối tượng. Một nhãn `case Color.GREEN` xác định chính xác giá trị enum cần match. Không có chuyển đổi chuỗi nào diễn ra; `"GREEN"` vẫn khác `Color.GREEN`.

**Trường hợp 2: selector có kiểu interface do nhiều enum triển khai.**

```java
sealed interface Status permits Pipeline, Ticket {}

enum Pipeline implements Status {
    READY, PAUSED
}

enum Ticket implements Status {
    READY, DONE
}
```

Vì cả `Pipeline` và `Ticket` đều có hằng tên `READY`, cách viết `Pipeline.READY` và `Ticket.READY` cho phép phân biệt hai ý nghĩa ngay trong case label. Điều này đặc biệt hữu ích với một hệ thống có nhiều tập trạng thái độc lập.

**Trường hợp 3: giữ rõ tên kiểu trong switch có nhiều loại pattern.**

```java
static String label(Object value) {
    return switch (value) {
        case Color.RED -> "special red";
        case Color c -> "other color:" + c;
        case String s -> "text:" + s;
        default -> "other";
    };
}
```

Nhánh hằng `Color.RED` được thử trước, nhánh type pattern `Color c` xử lý các giá trị `Color` còn lại, rồi mới đến `String` và `default`. Tên qualified giúp người đọc thấy ngay nhánh nào dành riêng cho một giá trị enum.

Không nhất thiết mọi switch trên enum đều phải đổi sang qualified form. Với switch chỉ nhận một `Color`, viết `case RED` vẫn đơn giản và đúng. Lựa chọn qualifier dựa vào kiểu selector, sự rõ ràng và phiên bản Java.

## 4. Khớp hằng enum khác khớp type pattern thế nào?

Xét enum:

```java
enum Color { RED, GREEN, BLUE }
```

So sánh:

| Case label | Điều kiện khớp với selector value | Có khai báo pattern variable không? |
| --- | --- | --- |
| `case Color.RED` | Giá trị chính là hằng `Color.RED` | Không |
| `case Color.GREEN` | Giá trị chính là hằng `Color.GREEN` | Không |
| `case Color c` | Giá trị là bất kỳ hằng `Color` khác `null` | Có, biến `c` kiểu `Color` |
| `case Enum<?> e` | Giá trị là một đối tượng enum bất kỳ phù hợp type pattern | Có, biến `e` kiểu `Enum<?>` |
| `case null` | Selector value là `null` | Không |
| `default` | Trường hợp còn lại theo quy tắc `switch` | Không |

Với các hằng enum, Java có một đối tượng singleton ứng với mỗi hằng được khai báo trong enum. Do đó nhãn `case Color.RED` biểu thị **đúng giá trị enum cụ thể**, không khớp chỉ vì đối tượng khác có chuỗi tên `"RED"`.

```java
Object value = Color.RED;

String result = switch (value) {
    case Color.RED -> "exact constant";
    case Color c -> "another Color: " + c;
    default -> "other";
};
```

Kết quả `"exact constant"`. Nếu đổi `value` thành `Color.BLUE`, nhánh `case Color c` khớp và trả `"another Color: BLUE"`.

Ngược lại, `case Color c` **không phải** một nhãn hằng, mà là type pattern cho toàn bộ kiểu. Trong thân nhánh đó có thể sử dụng `c.name()`, `c.ordinal()` hoặc phương thức khác của `Color`, bởi compiler đã biết kiểu tĩnh của biến `c`.

## 5. Chương trình Java 21 đầy đủ: hai enum cùng có hằng READY

Lưu toàn bộ mã dưới đây vào tệp **QualifiedEnumCaseDemo.java**.

```java
public class QualifiedEnumCaseDemo {
    enum Color { RED, GREEN, BLUE }

    sealed interface Status permits Pipeline, Ticket {}

    enum Pipeline implements Status { READY, PAUSED }

    enum Ticket implements Status { READY, DONE }

    static String describe(Object value) {
        return switch (value) {
            case null -> "null";

            case Color.RED -> "color:red";
            case Color c -> "color:" + c.name().toLowerCase();

            case Pipeline.READY -> "pipeline:ready";
            case Ticket.READY -> "ticket:ready";

            case Pipeline p ->
                    "pipeline:" + p.name().toLowerCase();
            case Ticket t ->
                    "ticket:" + t.name().toLowerCase();

            default -> "other";
        };
    }

    static String fromEnum(Color color) {
        return switch (color) {
            case Color.RED -> "red";
            case Color.GREEN, Color.BLUE -> "green-or-blue";
        };
    }

    static String fromStatus(Status status) {
        return switch (status) {
            case null -> "no-status";
            case Pipeline.READY -> "pipeline-ready";
            case Ticket.READY -> "ticket-ready";
            case Pipeline p -> "pipeline-other:" + p;
            case Ticket t -> "ticket-other:" + t;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(Color.RED));
        System.out.println(describe(Color.GREEN));
        System.out.println(describe(Pipeline.READY));
        System.out.println(describe(Ticket.READY));
        System.out.println(describe(Pipeline.PAUSED));
        System.out.println(describe(Ticket.DONE));
        System.out.println(describe("READY"));
        System.out.println(describe(null));
        System.out.println(fromEnum(Color.BLUE));
        System.out.println(fromStatus(Ticket.READY));
        System.out.println(fromStatus(Pipeline.PAUSED));
        System.out.println(fromStatus(null));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac QualifiedEnumCaseDemo.java
java QualifiedEnumCaseDemo
```

**Đầu ra chính xác:**

```text
color:red
color:green
pipeline:ready
ticket:ready
pipeline:paused
ticket:done
other
null
green-or-blue
ticket-ready
pipeline-other:PAUSED
no-status
```

Các điểm cần chú ý:

1. **Hai enum cùng tên hằng `READY`:** `Pipeline.READY` chọn nhánh `case Pipeline.READY`; `Ticket.READY` chọn nhánh `case Ticket.READY`. Hai hằng này hoàn toàn khác nhau.
2. **Selector kiểu rộng `Object`:** `describe(Object value)` nhận cả `Color`, `Pipeline`, `Ticket`, `String` và `null`. Những enum-qualified case label vẫn chọn đúng từng hằng.
3. **Pattern cụ thể trước type pattern:** nhánh `case Color.RED` đứng trước `case Color c`; hai nhánh `Pipeline.READY` và `Ticket.READY` đứng trước các type pattern cho toàn enum tương ứng.
4. **Nhánh dự phòng cho giá trị còn lại:** `case Pipeline p` nhận `Pipeline.PAUSED` và `case Ticket t` nhận `Ticket.DONE`; đây là những type patterns, không phải constant labels.
5. **Nhiều constant cùng một nhánh:** `case Color.GREEN, Color.BLUE -> ...` cho phép hai hằng enum dùng cùng một kết quả khi selector có kiểu `Color`.
6. **Sealed hierarchy:** selector kiểu `Status` chỉ có hai loại implementation được permits, là `Pipeline` và `Ticket`. `fromStatus` đã bao phủ cả hai kiểu với các type patterns, vì vậy không phải viết `default`.
7. **Khác biệt giữa chuỗi và enum:** `describe("READY")` trả `"other"`; chuỗi `"READY"` không tự được parse thành `Pipeline.READY` hay `Ticket.READY`.
8. **Null:** có nhánh `case null` trong `describe` và `fromStatus` để xử lý selector bằng `null` một cách tường minh.

## 6. Tương thích kiểu của hằng enum với selector

Trong switch có pattern, compiler kiểm tra xem một case label có thể được áp dụng cho kiểu selector không.

Ví dụ hợp lệ với selector kiểu `Object`:

```java
Object value = Color.RED;

String text = switch (value) {
    case Color.RED -> "red";
    default -> "other";
};
```

Tương tự, selector kiểu `Status` trong chương trình trên có thể match `Pipeline.READY` và `Ticket.READY`, vì hai enum thực thi `Status`.

**Ví dụ không hợp lệ:** nếu selector chắc chắn có kiểu `String`, đặt hằng enum `Color.RED` vào `case` không tương thích:

```java
// Lỗi biên dịch: Color không thể được chuyển thành String.
// static String wrong(String value) {
//     return switch (value) {
//         case Color.RED -> "red";
//         default -> "other";
//     };
// }
```

Đây là lỗi về **kiểu**, không phải đơn giản là “nhánh này chưa có dữ liệu để chạy”. Java phát hiện ngay khi biên dịch. Không nên ép selector thành `Object` chỉ để che lỗi thiết kế; hãy chọn kiểu đầu vào và case label đúng với ý nghĩa nghiệp vụ.

**Cảnh giác với `enum.name()` và chuỗi:** nếu đầu vào là `String`, `case "RED"` chỉ match chuỗi. Để chuyển chuỗi thành hằng enum có chủ đích, có thể dùng `Color.valueOf(text)` với xử lý `IllegalArgumentException` cho tên không hợp lệ. Sau đó switch trên giá trị `Color`. `valueOf` phân biệt chữ hoa/thường và không phải một phần ngầm định của case matching.

## 7. Thứ tự case và lỗi dominance

Các case label được compiler kiểm tra dominance, tức một nhánh tổng quát đặt trước có thể làm nhánh sau **không thể được chọn**.

Ví dụ **sai**:

```java
// Sai: case Color.RED bị pattern Color c ở trên bao phủ.
// static String wrongOrder(Object value) {
//     return switch (value) {
//         case Color c -> "any Color";
//         case Color.RED -> "red";
//         default -> "other";
//     };
// }
```

Dù `Color.RED` rất cụ thể, nó xuất hiện **sau** một type pattern khớp mọi hằng `Color`, nên compiler báo nhánh `Color.RED` bị dominated.

Cách đúng:

```java
static String correctOrder(Object value) {
    return switch (value) {
        case Color.RED -> "red";
        case Color c -> "another color";
        default -> "other";
    };
}
```

Với `Color.RED`, trả `"red"`; với `Color.BLUE`, trả `"another color"`. Đặt những **hằng cần xử lý riêng** trước type pattern bao phủ toàn enum.

Trình tự này cũng áp dụng khi dùng nhãn `case Object obj`: nếu đặt type pattern bao phủ mọi giá trị selector khác `null` lên trước các enum constants, các nhãn enum phía sau có thể bị che khuất. Mọi nhánh có nên tồn tại hay không cần được quyết định từ phạm vi giá trị của selector và thứ tự match mong muốn.

## 8. Gộp nhiều enum constant trong một case

Khi nhiều hằng của **cùng kiểu selector** cần cùng hành động, có thể viết nhãn gồm nhiều constant phân tách bằng dấu phẩy:

```java
static String bucket(Color color) {
    return switch (color) {
        case Color.RED -> "warm";
        case Color.GREEN, Color.BLUE -> "other";
    };
}
```

Với `Color.RED` trả `"warm"`; với `Color.GREEN` hoặc `Color.BLUE` trả `"other"`. Cách gộp này diễn đạt rõ rằng các hằng cùng đi vào một nhánh.

Trong switch với selector kiểu `Object`, các constant thuộc nhiều enum có thể được xử lý trong các case phù hợp theo cơ chế case labels Java 21, nhưng thường nên giữ riêng các hằng có ý nghĩa nghiệp vụ khác nhau. Đừng dùng cách nhóm quá nhiều giá trị khiến việc kiểm tra quyền hoặc chuyển trạng thái trở nên khó đọc.

Sự khác nhau giữa **nhiều constant cùng một nhánh** và **nhiều pattern khác kiểu** đáng lưu ý: trong ví dụ trên, mọi nhãn đều là các enum constants, không khai báo biến pattern; nếu cần giữ biến đã match để gọi phương thức, hãy dùng nhánh type pattern riêng, ví dụ `case Color c -> ...`.

## 9. Null và default không thay thế nhau

Một hằng enum khác `null`, nên `case Color.RED` và `case Color c` đều không xử lý trường hợp selector value bằng `null` trong cách dùng thông thường.

```java
static String maybeColor(Object value) {
    return switch (value) {
        case null -> "missing";
        case Color.RED -> "red";
        case Color c -> "another color";
        default -> "not a Color";
    };
}
```

- `maybeColor(null)` trả `"missing"`.
- `maybeColor(Color.RED)` trả `"red"`.
- `maybeColor(Color.GREEN)` trả `"another color"`.
- `maybeColor("RED")` trả `"not a Color"`.

Nếu bỏ `case null`, `default` **không tự bắt null** theo quy tắc switch trên kiểu tham chiếu trong Java 21: switch có thể ném `NullPointerException` trước khi đi vào `default`.

Với selector có kiểu enum, viết đầy đủ tất cả constant labels như `case Color.RED`, `case Color.GREEN`, `case Color.BLUE` có thể làm switch expression exhaustive cho các giá trị khác `null`; nó không biến `null` thành một hằng enum. Nếu `null` là một trạng thái hợp lệ của ứng dụng, xử lý nó một cách chủ đích.

## 10. Qualified constant và guard `when`

Một nhãn enum constant là **constant case label**, không phải pattern tự khai báo biến. Trong Java 21, không viết trực tiếp một `when` sau hằng đơn lẻ:

```java
// Sai cú pháp: when không gắn trực tiếp vào constant label.
// case Color.RED when enabled -> "red and enabled";
```

Guard `when` dành cho **pattern case label**. Khi cần kết hợp giá trị enum với điều kiện bên ngoài, có thể dùng type pattern và guard:

```java
static String classify(Object value, boolean enabled) {
    return switch (value) {
        case Color c when c == Color.RED && enabled ->
                "red enabled";
        case Color.RED -> "red disabled";
        case Color c -> "other color";
        default -> "other";
    };
}
```

Với `classify(Color.RED, true)` trả `"red enabled"`; với `classify(Color.RED, false)` trả `"red disabled"`.

Ở đây `c` có kiểu tĩnh `Color` và có hiệu lực trong biểu thức `when`. Guard được xét sau khi type pattern `Color c` khớp. Khi guard sai, Java tiếp tục xét nhánh sau. Đây là cách diễn đạt điều kiện động kết hợp enum constant rõ ràng mà không cần giả định constant label tự có pattern variable.

Nếu điều kiện được dùng để phân biệt hai giá trị cụ thể, có thể kiểm tra nó trong thân case thay vì dùng `when`. Chọn cách viết dễ đọc và giữ thứ tự nhánh nhất quán.

## 11. Exhaustiveness khi enum và sealed interface là selector

**Exhaustiveness** là yêu cầu compiler xác định rằng switch expression sẽ xử lý đầy đủ các giá trị selector có thể xuất hiện theo kiểu tĩnh của nó. Qualified enum constants có thể góp phần vào tính bao phủ.

### Selector có kiểu enum

```java
static String allColors(Color color) {
    return switch (color) {
        case Color.RED -> "R";
        case Color.GREEN -> "G";
        case Color.BLUE -> "B";
    };
}
```

Vì `Color` trong ví dụ có đúng ba hằng và cả ba được liệt kê, switch expression exhaustive, không cần `default`. Nếu về sau enum có thêm hằng mới và code được biên dịch lại, compiler có thể yêu cầu xử lý thêm nhánh, tạo cơ hội phát hiện thiếu sót.

### Selector có kiểu interface

Với `Status` là sealed interface do `Pipeline` và `Ticket` triển khai, chỉ liệt kê một vài constants như `Pipeline.READY` hoặc `Ticket.READY` **chưa** bao phủ mọi giá trị. Còn `Pipeline.PAUSED` và `Ticket.DONE`.

Cách đầy đủ, đã dùng trong chương trình chính:

```java
static String handle(Status status) {
    return switch (status) {
        case Pipeline.READY -> "pipeline-ready";
        case Ticket.READY -> "ticket-ready";
        case Pipeline p -> "pipeline:" + p.name();
        case Ticket t -> "ticket:" + t.name();
    };
}
```

Hai type patterns cuối bao phủ các hằng còn lại của từng enum, nên switch expression exhaustive đối với các giá trị `Status` khác `null`. Với selector `null`, switch ở ví dụ này vẫn có thể ném `NullPointerException`, vì không khai báo `case null`.

Nếu selector có kiểu rộng như `Object`, việc liệt kê hằng enum chỉ bao phủ một phần rất nhỏ các kiểu đối tượng có thể có. Thường cần `default` hoặc một pattern tổng quát phù hợp để bao phủ những trường hợp còn lại.

## 12. Những lỗi thường gặp

| Lỗi / hiểu nhầm | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Dùng `case Color.RED` rồi biên dịch `--release 17`. | Java 17 chưa có cú pháp qualified enum case theo tính năng Java 21 này. | Dùng JDK 21+ hoặc switch enum cổ điển với `case RED` khi selector có kiểu `Color`. |
| Dùng `case READY` trong switch trên `Object` mà không rõ enum nào. | Selector không cung cấp một kiểu enum đơn nhất để xác định hằng. | Dùng `case Pipeline.READY`, `case Ticket.READY` với kiểu selector tương thích. |
| Nghĩ `Pipeline.READY` và `Ticket.READY` là một hằng vì cùng tên `READY`. | Nhầm tên hằng với danh tính hằng. | Dùng qualifier để chỉ đúng enum sở hữu hằng; hai hằng khác nhau. |
| Đặt `case Color c` trước `case Color.RED`. | Type pattern tổng quát bao phủ hằng cụ thể phía sau. | Đặt `case Color.RED` trước `case Color c`. |
| Dùng `case Color.RED` trong switch trên selector kiểu `String`. | Kiểu enum không tương thích với kiểu selector. | Sửa mô hình kiểu hoặc switch trên giá trị enum đã được parse hợp lệ. |
| Cho rằng `case Color.RED` tự khai báo biến `RED`. | Constant label không khai báo biến pattern. | Dùng `case Color c` nếu cần biến `c`. |
| Viết `case Color.RED when enabled`. | `when` không gắn trực tiếp vào constant label kiểu này. | Dùng `case Color c when c == Color.RED && enabled`. |
| Nghĩ `default` xử lý selector `null`. | Trong switch Java 21 với kiểu tham chiếu, `null` cần cách xử lý riêng. | Thêm `case null` khi muốn chấp nhận null. |
| Chỉ liệt kê một số hằng enum trong switch expression mà không có nhánh bổ sung. | Thiếu exhaustiveness. | Liệt kê mọi hằng hoặc thêm nhánh bao phủ phần còn lại. |
| So sánh chuỗi `"RED"` với enum qua case label. | `String` và enum là hai loại dữ liệu khác nhau. | Chuyển đổi chuỗi sang enum có kiểm tra lỗi nếu thực sự cần. |

Một lưu ý về khả năng mở rộng: nếu chương trình thêm một enum mới thực thi interface `Status`, chính khai báo `sealed interface` và các nhánh switch cũng cần được xem lại. Qualified constants giúp code rõ ràng, nhưng vẫn phải giữ nhất quán mô hình các trạng thái được cho phép.

## 13. Bài tập tự kiểm tra

### Bài 1: Hằng nào khớp?

Cho khai báo:

```java
enum A { READY, WAITING }
enum B { READY, DONE }
Object input = B.READY;
```

Với:

```java
String result = switch (input) {
    case A.READY -> "A";
    case B.READY -> "B";
    default -> "other";
};
```

**Đáp án:** `"B"`. `A.READY` và `B.READY` là hai hằng khác nhau dù cùng tên `READY`.

### Bài 2: Vì sao không biên dịch?

```java
// Giả sử Color đã được khai báo.
static String check(Object input) {
    return switch (input) {
        case Color c -> "color";
        case Color.RED -> "red";
        default -> "other";
    };
}
```

**Đáp án:** `case Color.RED` bị dominated bởi `case Color c` ở trước. Muốn nhánh `RED` chạy riêng, phải đặt hằng cụ thể trước type pattern.

### Bài 3: Bổ sung nhánh còn thiếu

Cho:

```java
enum Mode { AUTO, MANUAL, OFF }

static String description(Mode mode) {
    return switch (mode) {
        case Mode.AUTO -> "automatic";
        case Mode.MANUAL -> "manual";
    };
}
```

**Đáp án:** switch expression còn thiếu `Mode.OFF`. Thêm `case Mode.OFF -> "off";` hoặc một nhánh bao phủ đúng các trường hợp còn lại. Nếu `mode == null`, việc bao phủ đủ ba hằng không ngăn `NullPointerException` khi thiếu xử lý `null`.

### Bài 4: Dự đoán kết quả chương trình chính

Từ chương trình `QualifiedEnumCaseDemo`:

- `describe(Pipeline.PAUSED)` trả gì? **`"pipeline:paused"`**.
- `describe("READY")` trả gì? **`"other"`**.
- `fromEnum(Color.BLUE)` trả gì? **`"green-or-blue"`**.
- `fromStatus(null)` trả gì? **`"no-status"`**.

Giải thích: từng kết quả phụ thuộc vào kiểu và giá trị của selector, thứ tự case và sự tồn tại của `case null`; việc chuỗi trông giống tên hằng enum không tạo ra một phép match.

## 14. Ghi nhớ

**Qualified enum constant** có dạng **`EnumType.CONSTANT`**. Từ Java 21, nó có thể được dùng trong `case` của pattern switch với selector kiểu rộng như `Object` hoặc interface tương thích. Cách viết này đặc biệt hữu ích khi nhiều enum cùng có hằng tên giống nhau hoặc khi một switch xử lý kết hợp nhiều kiểu dữ liệu.

Hãy nhớ bốn nguyên tắc khi thiết kế case labels:

1. **Khớp giá trị cụ thể:** `case Color.RED` dành cho đúng hằng `Color.RED`; `case Color c` là type pattern khớp mọi hằng `Color` khác `null`.
2. **Kiểu phải tương thích:** compiler so sánh kiểu enum của hằng với kiểu tĩnh selector, vì vậy không phải hằng enum bất kỳ đều đặt được ở mọi switch.
3. **Thứ tự có ý nghĩa:** đặt constant labels chuyên biệt trước type patterns bao phủ chúng để tránh dominance.
4. **Bao phủ và null rõ ràng:** switch expression cần exhaustive; `default` không tự thay `case null`.

Tài liệu chính thức:
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JLS Java SE 21 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS Java SE 21 — The switch Expression](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
