# Switch với enum constant trong Java

## 1. Vì sao enum đặc biệt phù hợp với switch?

Trong Java, một kiểu `enum` định nghĩa một tập hữu hạn các giá trị có tên. Mỗi giá trị là một **enum constant** thuộc kiểu enum đó:

```java
enum Stage {
    QUEUED, RUNNING, DONE, FAILED
}
```

Ở đây `Stage.QUEUED`, `Stage.RUNNING`, `Stage.DONE`, `Stage.FAILED` là bốn enum constants. Chúng được xác định khi viết chương trình, có tên và kiểu rõ ràng; không phải những chuỗi tự do như `"RUNNING"`.

Một `switch` có thể dùng các hằng enum làm **case labels** để chọn cách xử lý:

```java
static String label(Stage stage) {
    return switch (stage) {
        case QUEUED  -> "Chờ";
        case RUNNING -> "Đang chạy";
        case DONE    -> "Hoàn thành";
        case FAILED  -> "Thất bại";
    };
}
```

**`switch (stage)`** là biểu thức được kiểm tra (selector). Kiểu tĩnh của `stage` là `Stage`, nên Java biết các nhãn `QUEUED`, `RUNNING`, `DONE`, `FAILED` thuộc enum đó. Với `stage == Stage.DONE`, kết quả biểu thức là `"Hoàn thành"`.

**Case enum constant** chọn đúng **một hằng có tên**, không phải một kiểu đối tượng và **không khai báo pattern variable**. Điều này khác với **`case Stage s`** trong pattern switch Java 21, vốn khớp các đối tượng thuộc kiểu `Stage` và tạo biến `s`.

### Phạm vi phiên bản Java

- **Java trước 14:** switch statement dạng `case NAME:` đã hỗ trợ enum từ Java 5.
- **Java 14 trở lên:** switch expression và nhánh mũi tên `case NAME -> ...` đã được chuẩn hóa (JEP 361).
- **Java 21 trở lên:** Pattern Matching for switch (JEP 441) được chuẩn hóa; cho phép các **qualified enum constants** `case Stage.DONE` trong switch có selector kiểu interface/kiểu cha như `Object`, cùng case type patterns và `case null`.

Bài sử dụng **Java 21** để minh họa đầy đủ cả switch enum truyền thống và phần mở rộng hiện đại. Phần cú pháp cổ điển riêng lẻ có thể dùng với Java 17 mà không cần preview.

## 2. Cú pháp nền tảng: `case QUEUED` trong switch có selector enum

Với khai báo:

```java
enum Stage { QUEUED, RUNNING, DONE, FAILED }
```

Có thể viết:

```java
static String shortLabel(Stage value) {
    return switch (value) {
        case QUEUED  -> "Q";
        case RUNNING -> "R";
        case DONE    -> "D";
        case FAILED  -> "F";
    };
}
```

Đây là **switch expression**: toàn bộ `switch` tạo ra một giá trị kiểu `String` và được dùng làm giá trị trả về của phương thức. Nếu `value == Stage.RUNNING`, nhánh `case RUNNING` được chọn và kết quả là `"R"`.

Khi selector có kiểu enum cụ thể, tên hằng ngắn `case RUNNING` được giải quyết theo chính kiểu `Stage`. Không cần viết `case "RUNNING"`: đó là **chuỗi**, không phải hằng enum.

### 2.1. Tại sao các case không cần gọi `name()`?

```java
Stage value = Stage.RUNNING;
System.out.println(value.name()); // RUNNING
```

`value.name()` trả một chuỗi `String` cho mục đích hiển thị hoặc xử lý văn bản. Nhưng bản thân `value` là một đối tượng `Stage`. Khi `switch (value)`, Java đối chiếu giá trị enum với những enum constants trong `case`; không yêu cầu tự chuyển qua chuỗi.

Đây là khác biệt quan trọng về **an toàn kiểu**:

```java
// Đúng: switch trên enum, dùng enum constants.
switch (value) {
    case DONE -> System.out.println("done");
    default   -> System.out.println("other");
}
```

```java
// Một bài toán khác: switch trên String trả từ name().
switch (value.name()) {
    case "DONE" -> System.out.println("done");
    default     -> System.out.println("other");
}
```

Đoạn thứ hai hợp lệ vì selector đã chuyển thành `String`; nhưng nó không còn là **switch trực tiếp trên enum**. Khi đã có giá trị enum, ưu tiên cách thứ nhất để tránh lặp chuỗi và không làm mất lợi thế kiểm tra theo kiểu enum.

### 2.2. Case constant có phải biến mới?

Không:

```java
case DONE -> "Completed";
```

`DONE` là tên hằng đã khai báo trong enum. Nhánh đó **không tạo biến `DONE`**. Nếu cần xử lý chi tiết đối tượng `value`, biến selector `value` đã có sẵn trong phạm vi phương thức.

Đừng nhầm với cú pháp Java 21:

```java
case Stage s -> "State is " + s.name();
```

Đây là **case type pattern**: biến `s` được khai báo và gắn với đối tượng `Stage` đã khớp. Một case enum constant và một type pattern phục vụ hai mức kiểm tra khác nhau: **đúng giá trị cụ thể** so với **thuộc kiểu cụ thể**.

## 3. Switch statement cổ điển: `case NAME:`, `break` và fall-through

Trước khi có switch expression, Java thường viết switch statement:

```java
static void printStage(Stage stage) {
    switch (stage) {
        case QUEUED:
            System.out.println("Queued");
            break;
        case RUNNING:
            System.out.println("Running");
            break;
        case DONE:
            System.out.println("Done");
            break;
        case FAILED:
            System.out.println("Failed");
            break;
    }
}
```

Ở đây dấu **`:`** giới thiệu nhóm lệnh cho một case. Lệnh **`break`** thoát khỏi switch statement sau khi xử lý xong nhóm lệnh tương ứng.

### 3.1. Fall-through: không có break có thể chạy tiếp nhánh sau

```java
static void demonstrateFallThrough(Stage stage) {
    switch (stage) {
        case QUEUED:
            System.out.println("A");
            // Không có break ở đây.
        case RUNNING:
            System.out.println("B");
            break;
        default:
            System.out.println("C");
    }
}
```

Với `Stage.QUEUED`, đoạn trên in:

```text
A
B
```

Lý do: sau khi thực hiện nhóm `QUEUED`, chương trình **rơi tiếp** vào nhóm lệnh của `RUNNING` vì không có `break`. Đây là đặc tính của switch statement kiểu dấu `:`, không phải vì `Stage.QUEUED` bằng `Stage.RUNNING`.

Với `Stage.RUNNING`, chỉ in `B`; với `Stage.FAILED`, in `C`.

**Tránh fall-through ngoài ý muốn** bằng `break`, `return`, `throw`, hoặc dùng switch rule với `->` như phần kế tiếp. Nếu cố ý fall-through, nên ghi chú rõ.

### 3.2. Nhóm nhiều hằng bằng nhiều nhãn `case`

Dạng cổ điển thường thấy:

```java
static String phase(Stage stage) {
    switch (stage) {
        case QUEUED:
        case RUNNING:
            return "IN_PROGRESS";
        case DONE:
            return "SUCCESS";
        case FAILED:
            return "ERROR";
        default:
            return "UNKNOWN";
    }
}
```

Các nhãn `QUEUED` và `RUNNING` cùng dẫn tới một nhóm lệnh trả `IN_PROGRESS`. Đây là **nhóm hằng**, không khai báo biến pattern nào.

Nhánh `default` trong ví dụ giúp mọi đường đi có giá trị trả về. Nó cũng là lựa chọn khi một giá trị enum mới được bổ sung mà phương thức chưa được cập nhật; tuy nhiên việc dùng `default` luôn cần cân nhắc vì có thể che khuất yêu cầu xử lý một hằng mới.

## 4. Switch rule với dấu `->`: không có fall-through

Từ Java 14, cách viết mũi tên thường gọn hơn:

```java
static String stageText(Stage stage) {
    return switch (stage) {
        case QUEUED  -> "Waiting";
        case RUNNING -> "Working";
        case DONE    -> "Complete";
        case FAILED  -> "Failure";
    };
}
```

Mỗi **rule** chỉ chạy phần xử lý sau dấu `->` của chính nó. Không có hành vi chạy tiếp sang rule kế bên như cú pháp `:`.

Đối với switch statement, có thể dùng:

```java
static void printArrow(Stage stage) {
    switch (stage) {
        case QUEUED  -> System.out.println("Waiting");
        case RUNNING -> System.out.println("Working");
        case DONE    -> System.out.println("Complete");
        case FAILED  -> System.out.println("Failure");
    }
}
```

Một câu lệnh `System.out.println` là **statement expression** hợp lệ sau `->` trong switch statement.

### 4.1. Khi một nhánh cần nhiều câu lệnh

Với switch expression, dùng block và `yield`:

```java
static String loggable(Stage stage) {
    return switch (stage) {
        case QUEUED, RUNNING -> {
            String info = "PENDING:" + stage.name();
            yield info;
        }
        case DONE   -> "OK";
        case FAILED -> "ERROR";
    };
}
```

`yield info;` trả giá trị của **switch expression**, không kết thúc cả phương thức như `return` bên trong một phương thức thông thường.

Với switch statement, block có thể chứa các lệnh hiệu ứng phụ:

```java
static void logStage(Stage stage) {
    switch (stage) {
        case QUEUED, RUNNING -> {
            System.out.println("Current: " + stage);
            System.out.println("Not final yet");
        }
        case DONE   -> System.out.println("Success");
        case FAILED -> System.out.println("Failure");
    }
}
```

### 4.2. Có dùng `break` với dấu mũi tên không?

Không cần `break` để chống fall-through khi dùng `->`. Dấu mũi tên đã đảm bảo rule không tự chạy sang rule khác. `break` hữu ích chủ yếu với nhóm câu lệnh dấu `:`; viết `break` vô nghĩa theo thói quen trong một switch expression có thể tạo lỗi cú pháp hoặc lỗi điều khiển.

## 5. Một case nhận nhiều enum constants

Khi nhiều hằng cần chung kết quả, có thể viết danh sách phân tách bằng dấu phẩy:

```java
static boolean terminal(Stage stage) {
    return switch (stage) {
        case DONE, FAILED    -> true;
        case QUEUED, RUNNING -> false;
    };
}
```

Các giá trị `Stage.DONE` và `Stage.FAILED` cùng trả `true`, còn hai giá trị còn lại trả `false`.

**Mỗi hằng trong danh sách được khớp độc lập.** `case DONE, FAILED` không khai báo một biến mới, không cần viết biểu thức `DONE || FAILED`, và không yêu cầu thêm câu lệnh `break`.

Đây là lựa chọn tốt khi các trạng thái có cùng hành vi nghiệp vụ. Khi mỗi hằng có hành vi đặc biệt, giữ riêng từng case để mã dễ đọc và mở rộng.

### 5.1. Nhóm không đồng nghĩa bỏ qua những enum constants khác

```java
// KHÔNG BIÊN DỊCH: thiếu hai hằng cho switch expression.
// static boolean terminal(Stage stage) {
//     return switch (stage) {
//         case DONE, FAILED -> true;
//     };
// }
```

Nhóm `DONE, FAILED` chỉ bao phủ **hai** giá trị trong bốn hằng của `Stage`. Để switch expression exhaustive, phải thêm cách xử lý `QUEUED`, `RUNNING` hoặc một nhánh tổng quát hợp lệ.

## 6. Exhaustiveness: liệt kê đủ enum constants

**Exhaustive switch** là một switch mà trình biên dịch chứng minh được các nhánh bao phủ những trường hợp cần thiết của kiểu selector.

Đối với enum, điều này thường dễ kiểm tra vì compiler biết đầy đủ danh sách enum constants tại thời điểm biên dịch:

```java
enum Color { RED, YELLOW, GREEN }

static String signal(Color color) {
    return switch (color) {
        case RED    -> "STOP";
        case YELLOW -> "WAIT";
        case GREEN  -> "GO";
    };
}
```

Mã hợp lệ dù không có `default`, vì ba hằng enum đã được xử lý.

### 6.1. Switch expression luôn yêu cầu exhaustive

```java
// KHÔNG BIÊN DỊCH: switch expression thiếu GREEN.
// static String signal(Color color) {
//     return switch (color) {
//         case RED    -> "STOP";
//         case YELLOW -> "WAIT";
//     };
// }
```

Đây là **lỗi biên dịch**, không phải một trường hợp runtime mặc định trả `null`. Java yêu cầu switch expression có khả năng tạo giá trị cho toàn bộ các giá trị enum thuộc kiểu selector.

### 6.2. Switch statement cổ điển không bắt buộc exhaustive

```java
static void incomplete(Color color) {
    switch (color) {
        case RED -> System.out.println("STOP");
    }
}
```

Đoạn này **biên dịch**: một switch statement kiểu cổ điển (selector enum, không có case pattern hoặc `case null`) không bắt buộc exhaustive. Với `YELLOW` hoặc `GREEN`, không case nào áp dụng nên statement có thể kết thúc mà không in gì.

Cần phân biệt: từ Java 21, **enhanced switch statement** (ví dụ selector interface hoặc có case pattern/null label) **phải exhaustive**; không thể áp dụng quy tắc của classic switch statement cho mọi dạng switch mới.

### 6.3. Bổ sung hằng mới và vai trò của default

Giả sử một ngày `Stage` được mở rộng thêm `CANCELLED`:

```java
// Phiên bản enum giả định sau khi thay đổi:
// enum Stage { QUEUED, RUNNING, DONE, FAILED, CANCELLED }
```

Với switch expression liệt kê đủ bốn hằng cũ nhưng **không có default**, khi biên dịch lại với enum mới, compiler có thể báo thiếu `CANCELLED`. Đây là cơ chế nhắc cập nhật logic nghiệp vụ.

Nếu trước đó đã viết `default -> "OTHER"`, compiler có thể coi switch vẫn exhaustive và không buộc thêm case dành cho `CANCELLED`. Cả hai cách đều có tình huống sử dụng:

- **Domain đóng, yêu cầu xử lý rõ từng trạng thái:** ưu tiên liệt kê đủ hằng và bỏ default nếu compiler có thể chứng minh exhaustive.
- **Đầu vào rộng hoặc có hành vi dự phòng hợp lý:** dùng default để nhận giá trị khác.

Việc **biên dịch lại** là điều kiện quan trọng. Với mã đã được biên dịch trước đó nhưng runtime nạp enum đã thay đổi từ thư viện khác, bảo đảm compile-time không tự động kiểm tra lại mọi thay đổi. Ở Java 21, một exhaustive switch bị mất tính đầy đủ tại runtime có thể ném `MatchException`; quản lý tương thích nhị phân và thử nghiệm tích hợp vẫn cần thiết.

## 7. `null` trong switch với enum constant

Enum là **kiểu tham chiếu**, nên một biến `Stage` vẫn có thể bằng `null`:

```java
Stage stage = null;
```

Các enum constants như `QUEUED`, `DONE` đều là đối tượng khác null. Vì vậy, nếu dùng switch không có xử lý null:

```java
static String label(Stage stage) {
    return switch (stage) {
        case QUEUED  -> "Q";
        case RUNNING -> "R";
        case DONE    -> "D";
        case FAILED  -> "F";
    };
}
```

`label(null)` **ném `NullPointerException`**. Dù đã liệt kê mọi hằng enum, không hằng nào là `null`. Tính exhaustive của enum không có nghĩa biểu thức tự xử lý null.

### 7.1. Java 21: `case null` là nhãn riêng

```java
static String safeLabel(Stage stage) {
    return switch (stage) {
        case null    -> "MISSING";
        case QUEUED  -> "Q";
        case RUNNING -> "R";
        case DONE    -> "D";
        case FAILED  -> "F";
    };
}
```

Với `null`, trả `"MISSING"`; với mọi giá trị `Stage` không null, trả chuỗi tương ứng. `case null` được chuẩn hóa cùng Pattern Matching for switch trong Java 21.

Đối với mã Java 17, có thể xử lý null **trước khi vào switch**:

```java
static String safeLabelJava17(Stage stage) {
    if (stage == null) {
        return "MISSING";
    }

    return switch (stage) {
        case QUEUED  -> "Q";
        case RUNNING -> "R";
        case DONE    -> "D";
        case FAILED  -> "F";
    };
}
```

### 7.2. `default` riêng lẻ không phải nhãn bắt null

```java
static String withDefault(Stage stage) {
    return switch (stage) {
        case DONE -> "SUCCESS";
        default   -> "NOT_DONE";
    };
}
```

Với `Stage.QUEUED`, trả `"NOT_DONE"`; với `Stage.DONE`, trả `"SUCCESS"`. Nhưng **`withDefault(null)` vẫn ném `NullPointerException`**, dù có `default`.

Trong Java 21, khi muốn xử lý giống nhau với null và các giá trị không khớp, dùng `case null, default`:

```java
static String doneOrOther(Stage stage) {
    return switch (stage) {
        case DONE          -> "SUCCESS";
        case null, default -> "OTHER_OR_NULL";
    };
}
```

Nhãn kết hợp `case null, default` phải là nhãn cuối trong switch block. Nó không khai báo pattern variable.

## 8. Java 21: qualified enum constants `case Stage.DONE`

Khi selector có kiểu tĩnh `Stage`, ta thường viết `case DONE`. Từ Java 21, có thể viết hằng với **tên có định danh enum**:

```java
static String qualified(Stage value) {
    return switch (value) {
        case Stage.QUEUED  -> "Q";
        case Stage.RUNNING -> "R";
        case Stage.DONE    -> "D";
        case Stage.FAILED  -> "F";
    };
}
```

Cách này vẫn so khớp đúng từng hằng. Điểm đáng giá hơn của qualified enum constants là: **selector không còn bắt buộc có kiểu tĩnh chính là enum đó**. Nó có thể là một interface mà enum triển khai, hoặc `Object`, miễn **kiểu của hằng enum có thể gán cho kiểu selector**.

### 8.1. Selector là interface, hai enum cùng triển khai

```java
sealed interface WorkflowEvent permits Stage, Priority {}

enum Stage implements WorkflowEvent {
    QUEUED, RUNNING, DONE, FAILED
}

enum Priority implements WorkflowEvent {
    LOW, HIGH
}
```

Đây là các khai báo top-level minh họa tương thích Java 21: `WorkflowEvent` chỉ cho phép hai enum trên triển khai trực tiếp. Một biến `WorkflowEvent` có thể chứa hằng của `Stage` hoặc `Priority`.

```java
static String eventName(WorkflowEvent event) {
    return switch (event) {
        case Stage.QUEUED   -> "stage-queued";
        case Stage.RUNNING  -> "stage-running";
        case Stage.DONE     -> "stage-done";
        case Stage.FAILED   -> "stage-failed";
        case Priority.LOW   -> "priority-low";
        case Priority.HIGH  -> "priority-high";
        case null           -> "missing";
    };
}
```

Đây là Java 21: **qualified enum case constants** của các enum triển khai interface có thể xuất hiện cùng nhau trong một switch. Những nhánh liệt kê toàn bộ các giá trị của hai enum, nên có thể đáp ứng exhaustiveness trên phân cấp sealed này. Với một interface **mở** (không sealed), chỉ liệt kê vài enum constants thường chưa đủ để làm một switch expression exhaustive; cần nhánh bao quát thích hợp.

### 8.2. Khi selector không là enum, cần tên hằng có định danh

```java
// KHÔNG BIÊN DỊCH trong switch trên WorkflowEvent:
// return switch (event) {
//     case DONE -> "done"; // Không xác định enum chứa hằng.
//     default   -> "other";
// };
```

Với selector `WorkflowEvent` hoặc `Object`, phải viết `case Stage.DONE` để chỉ rõ enum nào chứa `DONE`. Trong trường hợp có nhiều enum đều định nghĩa một hằng cùng tên, tên đầy đủ còn giúp tránh nhập nhằng.

**Quy tắc tương thích kiểu:** hằng `Stage.DONE` có kiểu `Stage`, gán được cho `WorkflowEvent` và `Object`, nên phù hợp. Nhưng nếu selector có kiểu tĩnh `Priority`, `case Stage.DONE` không tương thích và gây lỗi biên dịch.

### 8.3. Với `Object`, cần nhánh cho kiểu khác enum

```java
static String any(Object value) {
    return switch (value) {
        case null        -> "null";
        case Stage.DONE  -> "done";
        case Priority.HIGH -> "high-priority";
        default          -> "other";
    };
}
```

Phép switch trên `Object` có thể gặp một `Integer`, `String`, record, danh sách... Hơn hai hằng enum được liệt kê vẫn **không đủ** bao phủ mọi đối tượng. `default` nhận các giá trị không null chưa khớp; `case null` nhận null.

### 8.4. Java 17 so với Java 21

| Khả năng | Java 17 (không preview) | Java 21 |
| --- | --- | --- |
| `switch (Stage s)` và `case DONE` | Có | Có |
| Switch expression với enum constants | Có | Có |
| `case DONE, FAILED -> ...` | Có | Có |
| `case null` trong switch | Không | Có |
| `case Stage.DONE` trên selector `WorkflowEvent` | Không | Có |
| `case Stage state` type pattern trong switch | Không ổn định/không dùng không preview | Có |
| `case Stage s when ...` | Không | Có |

Các ví dụ runnable phía sau được gắn cụ thể với **Java 21**. Không dùng `--release 17` cho một file có `case null`, pattern switch hoặc qualified enum case constants trên interface.

## 9. Case enum constant so với type pattern

Đây là điểm rất dễ nhầm trong cùng một pattern switch:

```java
static String classifyEvent(WorkflowEvent event) {
    return switch (event) {
        case Stage.FAILED  -> "ALERT";
        case Stage stage   -> "STAGE:" + stage.name();
        case Priority.HIGH -> "URGENT";
        case Priority p    -> "PRIORITY:" + p.name();
        case null          -> "MISSING";
    };
}
```

**Hai loại nhánh đang cùng xuất hiện:**

- `case Stage.FAILED`: **case constant** chỉ khớp **chính hằng** `FAILED` của enum `Stage`; không tạo biến.
- `case Stage stage`: **type pattern** khớp **bất kỳ giá trị `Stage` nào khác null** chưa được nhánh trước xử lý; khai báo biến `stage` có kiểu `Stage`.
- `case Priority.HIGH`: nhận riêng hằng mức ưu tiên cao.
- `case Priority p`: nhận các giá trị `Priority` còn lại; khai báo biến `p`.
- `case null`: nhận null, không tạo biến.

**Tại sao phải đặt hằng trước type pattern?** Vì `case Stage stage` khớp mọi hằng `Stage`. Nếu đặt nó trước `case Stage.FAILED`, hằng `Stage.FAILED` sẽ bị che khuất (**dominated case**) và compiler báo lỗi.

```java
// KHÔNG BIÊN DỊCH: case enum constant bị type pattern bao phủ.
// return switch (event) {
//     case Stage stage  -> "ALL_STAGES";
//     case Stage.FAILED -> "ALERT";
//     case Priority p   -> "PRIORITY";
// };
```

Một case constant **chọn giá trị cụ thể**; type pattern **chọn cả kiểu**. Đó là lý do chúng có thứ tự ưu tiên khi xuất hiện cùng switch.

### 9.1. Guard `when` chỉ áp dụng cho case pattern

Cú pháp sau **không hợp lệ**:

```java
// KHÔNG BIÊN DỊCH:
// case Stage.DONE when authorized -> "DONE";
```

`when` đi sau một **case pattern**, không gắn trực tiếp với **case constant**. Nếu cần điều kiện phụ, có hai lựa chọn:

**Cách A — kiểm tra sau khi khớp hằng:**

```java
case Stage.DONE -> {
    if (authorized) {
        yield "DONE";
    }
    yield "DENIED";
}
```

Đây là mảnh **switch expression rule** bên trong một phương thức có biến boolean `authorized`; dùng `yield` khi cần trả giá trị từ block.

**Cách B — dùng guarded type pattern:**

```java
case Stage s when s == Stage.DONE && authorized -> "DONE";
case Stage s -> "OTHER_STAGE";
```

Hai dòng trên là các rule minh họa; cần đặt trong switch tương thích, có các nhánh khác phù hợp. Guard được đánh giá chỉ sau khi `Stage s` đã khớp.

### 9.2. Khi nào không nên dùng type pattern?

Nếu chỉ muốn phân biệt `Stage.DONE` với `Stage.FAILED`, viết `case DONE` (selector là `Stage`) hoặc `case Stage.DONE` (selector interface/cha) ngắn và rõ hơn `case Stage s when s == Stage.DONE`. Pattern hữu ích khi bạn cần biến kiểu `Stage` cho một **nhóm giá trị**.

## 10. Các vấn đề compile-time thường gặp

### 10.1. Trùng một hằng trong hai case

```java
// KHÔNG BIÊN DỊCH:
// return switch (stage) {
//     case DONE -> "DONE_A";
//     case DONE -> "DONE_B"; // Duplicate case constant.
//     default   -> "OTHER";
// };
```

Một hằng enum không thể xuất hiện hai lần như các case constants trùng nhau trong cùng switch block. Thêm `default` không khắc phục lỗi này.

### 10.2. Case constant không thuộc enum selector

```java
// Giả sử Stage stage đã được khai báo.
// KHÔNG BIÊN DỊCH:
// return switch (stage) {
//     case Priority.HIGH -> "HIGH";
//     default            -> "OTHER";
// };
```

`Priority.HIGH` không gán được cho kiểu `Stage`; kiểu case label không tương thích với selector. Hãy dùng hằng `Stage`, hoặc đổi selector thành kiểu chung nếu thực sự cần xử lý nhiều enum.

### 10.3. Dùng chuỗi thay vì enum constant

```java
// KHÔNG BIÊN DỊCH nếu stage có kiểu Stage:
// return switch (stage) {
//     case "DONE" -> "DONE";
//     default     -> "OTHER";
// };
```

`"DONE"` là một `String`, không phải `Stage.DONE`. Có thể switch trên `stage.name()` nếu cần phân loại chuỗi, nhưng khi đầu vào đã là enum, nên giữ biểu thức switch theo kiểu enum.

### 10.4. Dùng giá trị ordinal như một enum constant

```java
// KHÔNG PHẢI case hợp lệ của switch enum:
// switch (stage) {
//     case 2 -> System.out.println("DONE");
// }
```

`ordinal()` là chỉ số vị trí trong danh sách enum constants, không phải danh tính hằng. Không dùng vị trí `2` thay cho `DONE`; đổi thứ tự khai báo enum có thể đổi ordinal. Với switch enum, dùng tên hằng thực tế.

### 10.5. Dùng biến alias trong case label

```java
static final Stage FINAL_ALIAS = Stage.DONE;

// KHÔNG BIÊN DỊCH trong switch enum nếu dùng alias như hằng case:
// switch (stage) {
//     case FINAL_ALIAS -> System.out.println("Done");
//     default -> {}
// }
```

Một alias `static final Stage` không phải **tên enum constant được khai báo trực tiếp**. Java cho phép enum constants trong case labels, nhưng không biến tùy ý kiểu enum thành một *constant expression* hợp lệ. Dùng `case DONE` hoặc `case Stage.DONE` thay vì alias.

### 10.6. Quên `break` trong dạng dấu hai chấm

```java
switch (stage) {
    case QUEUED:
        System.out.println("Queued");
        // Nếu không break, vẫn chạy vào RUNNING.
    case RUNNING:
        System.out.println("Running");
        break;
    default:
        System.out.println("Other");
}
```

Đây **không phải lỗi biên dịch**, nhưng có thể gây lỗi logic vì fall-through. Nếu không có chủ đích nhóm nhánh, hãy thêm `break` hoặc dùng `->`.

### 10.7. Switch expression thiếu enum constant

```java
// KHÔNG BIÊN DỊCH: thiếu FAILED.
// return switch (stage) {
//     case QUEUED, RUNNING -> "IN_PROGRESS";
//     case DONE            -> "DONE";
// };
```

Đây là lỗi **non-exhaustive switch expression**, không phải dominated case. Bổ sung `case FAILED` hoặc một nhánh bao quát phù hợp.

### 10.8. Đặt type pattern tổng quát trước hằng

```java
// KHÔNG BIÊN DỊCH:
// return switch (event) {
//     case Stage s       -> "ANY_STAGE";
//     case Stage.RUNNING -> "RUNNING";
//     case Priority p    -> "PRIORITY";
// };
```

`Stage.RUNNING` nằm sau pattern `Stage s` bao quát enum `Stage`, nên bị dominated. Hãy đảo thứ tự hai nhánh đầu.

### 10.9. Gắn `when` trực tiếp cho enum constant

```java
// KHÔNG HỢP LỆ:
// case DONE when enabled -> "DONE";
```

Để thêm kiểm tra boolean ở một nhánh, dùng `if` trong thân rule; nếu muốn guard ở case label, khai báo một type pattern có biến trước `when`.

### 10.10. Tưởng default tự nhận null

```java
static String statusOrFallback(Stage stage) {
    return switch (stage) {
        case DONE -> "DONE";
        default   -> "OTHER";
    };
}
```

Với `stage == null`, phương thức **ném `NullPointerException`**. Nếu cần `"OTHER"` cho cả null, dùng Java 21 `case null, default -> "OTHER";` hoặc kiểm tra null trước switch.

## 11. Chương trình Java 21 hoàn chỉnh: enum constants, grouping, pattern switch

Tạo tệp **`EnumSwitchConstantDemo.java`** với nội dung dưới đây. Toàn bộ các kiểu được khai báo bên trong class công khai nên chỉ cần **một file Java**:

```java
public class EnumSwitchConstantDemo {

    sealed interface WorkflowEvent permits Stage, Priority {}

    enum Stage implements WorkflowEvent {
        QUEUED, RUNNING, DONE, FAILED
    }

    enum Priority implements WorkflowEvent {
        LOW, HIGH
    }

    // Switch expression trực tiếp trên enum:
    // các case là tên hằng, không có pattern variable.
    static String label(Stage stage) {
        return switch (stage) {
            case QUEUED  -> "Q";
            case RUNNING -> "R";
            case DONE    -> "D";
            case FAILED  -> "F";
        };
    }

    // Switch statement cổ điển dùng ':', break và nhóm case.
    static String legacy(Stage stage) {
        switch (stage) {
            case QUEUED:
            case RUNNING:
                return "IN_PROGRESS";
            case DONE:
                return "COMPLETE";
            default:
                return "FAILED";
        }
    }

    // Nhiều hằng thuộc cùng một nhánh.
    static boolean isTerminal(Stage stage) {
        return switch (stage) {
            case DONE, FAILED    -> true;
            case QUEUED, RUNNING -> false;
        };
    }

    // Java 21: case null trong switch enum.
    static String nullableStage(Stage stage) {
        return switch (stage) {
            case null            -> "MISSING";
            case QUEUED, RUNNING -> "PENDING";
            case DONE            -> "SUCCESS";
            case FAILED          -> "FAILURE";
        };
    }

    // Java 21: selector là sealed interface; hằng cần
    // định danh kiểu như Stage.FAILED, Priority.HIGH.
    // Hằng cụ thể đứng trước type pattern rộng.
    static String fromEvent(WorkflowEvent value) {
        return switch (value) {
            case Stage.FAILED  -> "ALERT";
            case Stage stage   -> "STAGE:" + stage.name();
            case Priority.HIGH -> "URGENT";
            case Priority p    -> "PRIORITY:" + p.name();
            case null          -> "MISSING";
        };
    }

    // Java 21: selector là Object, dùng qualified constants.
    // default nhận các kiểu khác, case null nhận null.
    static String fromAny(Object value) {
        return switch (value) {
            case null          -> "NULL";
            case Stage.DONE    -> "DONE";
            case Stage stage   -> "STAGE:" + stage.name();
            case Priority.HIGH -> "URGENT";
            case Priority p    -> "PRIORITY:" + p.name();
            default            -> "OTHER";
        };
    }

    // Java 21: nhãn cuối gộp null với default.
    static String runningOrElse(Object value) {
        return switch (value) {
            case Stage.RUNNING -> "ACTIVE";
            case null, default -> "NOT_RUNNING";
        };
    }

    public static void main(String[] args) {
        System.out.println(label(Stage.QUEUED));
        System.out.println(label(Stage.RUNNING));
        System.out.println(label(Stage.DONE));
        System.out.println(label(Stage.FAILED));

        System.out.println(legacy(Stage.RUNNING));
        System.out.println(legacy(Stage.FAILED));

        System.out.println(isTerminal(Stage.DONE));
        System.out.println(isTerminal(Stage.QUEUED));

        System.out.println(nullableStage(null));
        System.out.println(nullableStage(Stage.RUNNING));

        System.out.println(fromEvent(Stage.FAILED));
        System.out.println(fromEvent(Stage.QUEUED));
        System.out.println(fromEvent(Priority.HIGH));
        System.out.println(fromEvent(Priority.LOW));
        System.out.println(fromEvent(null));

        System.out.println(fromAny(Stage.DONE));
        System.out.println(fromAny(Stage.RUNNING));
        System.out.println(fromAny(Priority.HIGH));
        System.out.println(fromAny(5));
        System.out.println(fromAny(null));

        System.out.println(runningOrElse(Stage.RUNNING));
        System.out.println(runningOrElse(Stage.DONE));
        System.out.println(runningOrElse(null));
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**:

```bash
javac --release 21 EnumSwitchConstantDemo.java
java EnumSwitchConstantDemo
```

Không cần cờ `--enable-preview` vì toàn bộ cú pháp sử dụng ở đây đã ổn định từ Java 21.

**Kết quả stdout chính xác:**

```text
Q
R
D
F
IN_PROGRESS
FAILED
true
false
MISSING
PENDING
ALERT
STAGE:QUEUED
URGENT
PRIORITY:LOW
MISSING
DONE
STAGE:RUNNING
URGENT
OTHER
NULL
ACTIVE
NOT_RUNNING
NOT_RUNNING
```

### 11.1. Giải thích từng nhóm đầu ra

**Bốn dòng đầu — switch expression trên enum:**

- `Stage.QUEUED` chọn `case QUEUED`, in `Q`.
- `Stage.RUNNING` chọn `case RUNNING`, in `R`.
- `Stage.DONE` chọn `case DONE`, in `D`.
- `Stage.FAILED` chọn `case FAILED`, in `F`.

**Hai dòng tiếp — statement dấu `:`:** `legacy(Stage.RUNNING)` đi qua các nhãn gộp `QUEUED`/`RUNNING` và `return "IN_PROGRESS"`. `legacy(Stage.FAILED)` không khớp `QUEUED`, `RUNNING`, `DONE`, nên chọn `default` và trả `FAILED`.

**Hai dòng boolean:** `Stage.DONE` thuộc nhóm hằng terminal nên `isTerminal` trả `true`; `Stage.QUEUED` thuộc nhóm chưa kết thúc nên trả `false`.

**Hai dòng xử lý null/nhóm:** `nullableStage(null)` khớp `case null` và in `MISSING`; `nullableStage(Stage.RUNNING)` khớp nhãn gộp `QUEUED, RUNNING` và in `PENDING`.

**Năm dòng về interface:** `fromEvent(Stage.FAILED)` khớp enum constant cụ thể trước type pattern, nên in `ALERT`; `Stage.QUEUED` đi vào `case Stage stage` và in `STAGE:QUEUED`. Tương tự, `Priority.HIGH` được nhánh hằng xử lý, còn `Priority.LOW` được type pattern `Priority p` xử lý. `null` được nhãn riêng nhận.

**Năm dòng về Object:** `Stage.DONE` in `DONE`, `Stage.RUNNING` in `STAGE:RUNNING`, `Priority.HIGH` in `URGENT`. Giá trị `5` được autobox thành `Integer` khi truyền vào `Object`, không khớp hai enum nên đi vào `default`. Null đi vào `case null`.

**Ba dòng cuối — nhãn kết hợp:** `Stage.RUNNING` trả `ACTIVE`; `Stage.DONE` và `null` đều trả `NOT_RUNNING` nhờ `case null, default`.

### 11.2. Tại sao ví dụ không cần default ở fromEvent?

`WorkflowEvent` là **sealed interface**, chỉ cho phép `Stage` và `Priority` triển khai trực tiếp. Nhánh `case Stage stage` khớp mọi hằng `Stage` khác null mà `Stage.FAILED` chưa nhận; nhánh `case Priority p` khớp toàn bộ hằng `Priority` khác null còn lại. Vì vậy bộ case đủ **exhaustive** đối với `WorkflowEvent`, không cần default. `case null` chỉ giúp đưa ra kết quả cho giá trị null.

### 11.3. Vì sao fromAny phải có default?

Kiểu selector của `fromAny` là `Object`; có thể nhận `Integer`, `String`, `Boolean`, v.v. `case Stage stage` và `case Priority p` không thể bao phủ các kiểu đối tượng này. `default` là một cách tạo đường xử lý cho chúng.

## 12. Quy trình chọn switch enum trong code thực tế

### 12.1. Đầu vào đã là enum cụ thể?

Nếu có `Stage stage` và hành vi dựa trên giá trị hằng, dùng **switch trực tiếp trên enum**:

```java
static int progress(Stage stage) {
    return switch (stage) {
        case QUEUED  -> 0;
        case RUNNING -> 50;
        case DONE    -> 100;
        case FAILED  -> -1;
    };
}
```

Cách này đơn giản, type-safe và compiler có thể kiểm tra đủ hằng. Không cần Pattern Matching for switch nếu chỉ phân biệt các trạng thái của một enum.

### 12.2. Một số hằng có cùng xử lý?

Gộp:

```java
case DONE, FAILED -> true;
```

Khi dùng statement dấu `:`, có thể nhóm nhiều nhãn rồi chạy chung lệnh. Với `->`, dùng danh sách hằng phân tách bằng dấu phẩy. Nhớ đặt đầy đủ các enum constants nếu dùng switch expression không có default.

### 12.3. Đầu vào có thể thuộc nhiều enum khác nhau?

Thiết kế một interface chung, rồi dùng **qualified enum constants Java 21**:

```java
case Stage.FAILED -> "stage failed";
case Priority.HIGH -> "priority high";
```

Điều kiện: các hằng đó phải có kiểu gán được cho kiểu selector. Nếu muốn xử lý toàn bộ giá trị của một enum, dùng `case Stage s` ở sau các hằng đặc biệt.

### 12.4. Có thể có null không?

- **Không chấp nhận null:** kiểm tra sớm bằng `Objects.requireNonNull(stage)` hoặc để hợp đồng API rõ ràng, tùy ứng dụng.
- **Chấp nhận null với giá trị riêng:** Java 21 có `case null`.
- **Chấp nhận null giống fallback:** Java 21 có `case null, default`.
- **Java 17:** dùng `if (stage == null)` trước switch.

Đừng dựa vào `default` đơn lẻ để nhận null.

### 12.5. Khi nào nên bỏ default?

Khi enum là **domain đóng** và cần compiler nhắc cập nhật tất cả vị trí switch sau khi thêm hằng mới, switch expression liệt kê đủ hằng **không có default** thường có lợi. Với đầu vào mở hoặc có một chính sách fallback thực sự, default có thể là lựa chọn phù hợp.

## 13. Bảng so sánh và những ranh giới dễ nhầm

| Khái niệm | `case DONE` (selector Stage) | `case Stage.DONE` (Java 21) | `case Stage s` (Java 21) |
| --- | --- | --- | --- |
| Là enum constant? | Có | Có | Không |
| Là type pattern? | Không | Không | Có |
| Khớp giá trị nào? | Đúng `Stage.DONE` | Đúng `Stage.DONE` | Mọi giá trị `Stage` khác null |
| Có pattern variable? | Không | Không | Có: `s` |
| Có dùng được với selector interface không? | Không dưới dạng tên ngắn này | Có nếu kiểu hằng gán được cho interface | Có nếu pattern áp dụng được cho selector |
| Có `when` trực tiếp? | Không | Không | Có, nếu guard hợp lệ |
| Thứ tự khi trộn | Hằng cụ thể trước pattern tổng quát | Hằng cụ thể trước pattern tổng quát | Sau hằng cụ thể cùng enum |

Một số kết luận thực hành:

- `enum Stage` định nghĩa **giá trị** chứ không phải chỉ chuỗi; `case DONE` là cách kiểm tra chính giá trị enum.
- Cú pháp mũi tên `->` ngăn fall-through; cú pháp `:` yêu cầu kiểm soát luồng rõ ràng.
- Nhóm hằng bằng dấu phẩy là cách hợp lệ để nhiều giá trị chia sẻ một hành vi.
- Switch expression trên enum không default phải liệt kê đủ hằng để exhaustive.
- `null` và enum constant là hai trường hợp khác nhau; không bao giờ giả định một enum constant có thể là null.
- Qualified enum constants của Java 21 mở rộng khả năng viết switch khi selector là một interface hoặc kiểu cha.

## 14. Bài tập luyện tập có đáp án

### Bài 1 — dự đoán switch expression

Cho:

```java
enum Status { NEW, SENT, RECEIVED, FAILED }

static String category(Status status) {
    return switch (status) {
        case NEW, SENT -> "PENDING";
        case RECEIVED  -> "SUCCESS";
        case FAILED    -> "ERROR";
    };
}
```

**Câu hỏi:** Kết quả của `category(Status.SENT)`, `category(Status.RECEIVED)`, `category(Status.FAILED)` là gì?

**Đáp án:** lần lượt `"PENDING"`, `"SUCCESS"`, `"ERROR"`. Nhánh đầu gộp hai enum constants; mỗi giá trị chỉ chọn một rule.

### Bài 2 — tìm lỗi compile-time

```java
// KHÔNG BIÊN DỊCH:
// static String category(Status status) {
//     return switch (status) {
//         case NEW      -> "NEW";
//         case SENT     -> "SENT";
//         case RECEIVED -> "RECEIVED";
//     };
// }
```

**Đáp án:** Switch expression không exhaustive vì thiếu hằng `Status.FAILED`. Thêm `case FAILED -> "FAILED";` hoặc một nhánh `default` hợp lệ.

### Bài 3 — fall-through xảy ra như thế nào?

```java
static void show(Status status) {
    switch (status) {
        case NEW:
            System.out.println("A");
        case SENT:
            System.out.println("B");
            break;
        default:
            System.out.println("C");
    }
}
```

**Đáp án:** `show(Status.NEW)` in `A` rồi `B`, vì không có `break` ở nhóm `NEW`. `show(Status.SENT)` chỉ in `B`. `show(Status.FAILED)` in `C`. Nếu không muốn in `B` khi đầu vào là `NEW`, thêm `break` hoặc chuyển sang `->`.

### Bài 4 — sửa nhánh bị dominance

Giả sử selector là `Object event`, và `Stage` đã được khai báo:

```java
// KHÔNG BIÊN DỊCH:
// return switch (event) {
//     case Stage s       -> "ANY_STAGE";
//     case Stage.DONE    -> "DONE";
//     default            -> "OTHER";
// };
```

**Đáp án:** Đưa `case Stage.DONE` lên trước `case Stage s`. `case Stage s` là type pattern bao quát mọi hằng của `Stage`; nếu nó đứng trước thì nhánh hằng `DONE` không còn cơ hội được chọn.

### Bài 5 — viết phương thức trả mã xử lý

Yêu cầu: nhận `Status status` có các hằng `NEW`, `SENT`, `RECEIVED`, `FAILED`. Trả 0 cho `NEW`, 1 cho `SENT`, 2 cho `RECEIVED`, -1 cho `FAILED`. Không dùng `default` để compiler bắt thiếu hằng.

**Một lời giải:**

```java
static int code(Status status) {
    return switch (status) {
        case NEW      -> 0;
        case SENT     -> 1;
        case RECEIVED -> 2;
        case FAILED   -> -1;
    };
}
```

Đây là switch expression exhaustive nhờ đủ enum constants.

### Bài 6 — xử lý null trong Java 21

Viết lại `code(Status status)` sao cho `null` trả -99 mà các enum constants vẫn giữ kết quả ban đầu.

**Đáp án:**

```java
static int codeNullable(Status status) {
    return switch (status) {
        case null     -> -99;
        case NEW      -> 0;
        case SENT     -> 1;
        case RECEIVED -> 2;
        case FAILED   -> -1;
    };
}
```

`case null` không làm mất các nhánh enum, chỉ bổ sung xử lý giá trị tham chiếu rỗng.

### Bài 7 — vì sao alias không hợp lệ?

```java
static final Status COMPLETE_ALIAS = Status.RECEIVED;

// KHÔNG BIÊN DỊCH khi dùng làm enum case:
// return switch (status) {
//     case COMPLETE_ALIAS -> "RECEIVED";
//     default -> "OTHER";
// };
```

**Đáp án:** `COMPLETE_ALIAS` là biến `static final` tham chiếu đến enum constant, nhưng nó không phải chính **tên một enum constant** theo cú pháp case constant. Dùng `case RECEIVED` (selector `Status`) hoặc `case Status.RECEIVED` (Java 21, khi phù hợp kiểu selector).

### Bài 8 — chọn giải pháp cho hệ thống có nhiều enum

Một hệ thống có `sealed interface Event` do `NetworkEvent` và `FileEvent` (đều là enum) triển khai. Cả hai enum có hằng `OPEN`. Làm sao phân biệt chúng trong switch Java 21?

**Đáp án:** Đặt selector có kiểu `Event` và dùng **qualified enum constants**:

```java
// Các enum cần được khai báo là những kiểu được Event cho phép.
// Đây là mảnh switch expression minh họa:
return switch (event) {
    case NetworkEvent.OPEN -> "NETWORK_OPEN";
    case FileEvent.OPEN    -> "FILE_OPEN";
    default                -> "OTHER";
};
```

`NetworkEvent.OPEN` và `FileEvent.OPEN` là hai hằng **khác kiểu**, nên không bị nhập nhằng dù cùng tên `OPEN`.

## 15. Checklist sử dụng switch với enum constant

Khi review mã Java, hãy kiểm tra:

1. **Selector có kiểu gì?** Với enum cụ thể, tên `case DONE` thường đủ. Với interface/Object ở Java 21, dùng tên đầy đủ `case Stage.DONE`.
2. **Case có thực sự là hằng enum?** Không dùng chuỗi `"DONE"`, số `ordinal()` hoặc alias làm nhãn enum khi selector là enum.
3. **Statement hay expression?** Switch expression luôn cần exhaustive; classic switch statement trên enum có thể thiếu case nhưng dễ gây bỏ sót hành vi.
4. **Cách viết `:` hay `->`?** Với `:`, xem có fall-through ngoài ý muốn không. Với `->`, mỗi rule độc lập.
5. **Có nhóm hằng cùng xử lý không?** Dùng `case DONE, FAILED` hoặc nhiều nhãn dấu `:` khi phù hợp.
6. **Exhaustiveness đã đủ chưa?** Nếu bỏ default trong switch expression, cần đủ enum constants; khi enum mở rộng, biên dịch lại để nhận cảnh báo lỗi thiếu case.
7. **Null được quyết định rõ chưa?** Java 21 dùng `case null` hoặc `case null, default`; Java 17 kiểm tra trước switch. Không dựa vào default riêng lẻ.
8. **Có trộn với type patterns không?** Đặt enum constant cụ thể **trước** type pattern bao quát enum; nếu không, bị dominated case.
9. **Có dùng `when` không?** Guard chỉ gắn với case pattern chứ không đi trực tiếp sau case enum constant.
10. **Có hai enum dùng cùng tên hằng không?** Dùng tên định danh kiểu khi selector không phải một enum cụ thể.
11. **Có phụ thuộc vào thứ tự enum hoặc tên chuỗi để biểu diễn nghiệp vụ không?** Tránh gắn logic quan trọng vào `ordinal()`; nếu lưu ra ngoài, thiết kế mã định danh bền vững và chiến lược nâng cấp.
12. **Dự án dùng Java nào?** Switch expression với enum từ Java 14; case null và qualified enum labels trên selector kiểu cha theo ví dụ ở đây yêu cầu Java 21.

## 16. Tổng kết

**Switch với enum constant** dùng các hằng có tên để chọn hành vi theo giá trị enum, giúp mã phân loại trạng thái có kiểu rõ ràng hơn so với xử lý chuỗi tự do.

- **`case DONE`** khớp hằng enum `DONE` khi selector có kiểu enum cụ thể.
- **`case Stage.DONE`** (Java 21) khớp hằng có định danh đầy đủ và hỗ trợ selector kiểu interface/cha tương thích.
- **`case Stage s`** không phải case constant mà là **type pattern**, khớp toàn bộ kiểu `Stage` và khai báo biến `s`.
- **Dấu `->`** giúp tránh fall-through; **dấu `:`** yêu cầu kiểm soát luồng bằng break/return/throw.
- **Switch expression** cần exhaustive; enum cho phép compiler kiểm tra đủ hằng mà không cần default.
- **`null`** không phải một enum constant; khi muốn xử lý null, dùng nhãn riêng trong Java 21 hoặc kiểm tra sớm.
- Khi trộn hằng enum với type pattern, **case hằng cụ thể đặt trước pattern rộng hơn** để tránh dominance.

Nắm được các quy tắc trên giúp viết switch enum dễ đọc, dễ kiểm thử và dễ mở rộng khi mô hình trạng thái của ứng dụng thay đổi.

## Tài liệu tham khảo chính thức

- [Java SE 21 Language Specification §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification §14.11.1 — Switch Blocks, Labels, Constants, Dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1)
- [Java SE 21 Language Specification §14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1)
- [Java SE 21 Language Specification §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361)
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
