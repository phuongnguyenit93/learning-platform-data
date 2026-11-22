# Enum constant trong pattern switch của Java

## 1. Enum constant là gì và vì sao xuất hiện trong pattern switch?

`enum` định nghĩa một tập các giá trị có tên, hữu hạn và được biết trước ở thời điểm biên dịch. Ví dụ:

```java
enum Status {
    NEW, RUNNING, DONE
}
```

`Status.NEW`, `Status.RUNNING` và `Status.DONE` là các **enum constant** (hằng enum). Mỗi hằng là một đối tượng duy nhất của kiểu `Status`. Khi dùng `switch`, ta có thể phân nhánh theo hằng enum:

```java
static String describe(Status status) {
    return switch (status) {
        case NEW     -> "Mới";
        case RUNNING -> "Đang chạy";
        case DONE    -> "Hoàn thành";
    };
}
```

Đây là **switch trên enum truyền thống**, không cần pattern matching. Nếu biểu thức `status` có kiểu tĩnh `Status`, trình biên dịch biết `NEW`, `RUNNING`, `DONE` thuộc enum nào. Các nhánh là phép đối chiếu **hằng**, không phải mẫu khai báo biến.

**Pattern matching for switch** (chuẩn hóa trong **Java 21**, JEP 441) mở rộng `switch` để kiểm tra kiểu đối tượng bằng những nhánh như `case String text`, `case Integer number`. Cùng với đó, Java 21 cho phép dùng **tên enum có định danh kiểu** (*qualified enum constant*) như `case Status.NEW`, kể cả khi kiểu tĩnh của biểu thức `switch` **không phải** `Status`, miễn giá trị hằng `Status.NEW` có thể gán cho kiểu selector.

Điểm mới này rất hữu ích khi một interface có nhiều enum triển khai, hoặc khi `switch` nhận một kiểu cha như `Object`.

**Đừng nhầm hai loại `case`:**

- `case Status.NEW` là **case constant**: khớp chính xác một giá trị enum cụ thể, **không khai báo biến pattern**.
- `case Status status` là **case type pattern**: khớp các giá trị khác `null` có kiểu `Status` và giới thiệu biến `status`.
- `case Status status when status == Status.NEW` là **guarded type pattern**: khớp kiểu `Status` rồi kiểm tra điều kiện bổ sung. Trong tình huống so một hằng enum, thường nên dùng `case Status.NEW` ngắn gọn hơn.

Bài học này dùng cú pháp **Java 21 không bật preview**. Java 17 đã có `switch` trên enum theo kiểu cổ điển nhưng chưa có **pattern switch ổn định** hay các cú pháp qualified enum constant được chuẩn hóa cùng JEP 441. Ví dụ hoàn chỉnh dùng `javac --release 21`.

## 2. Từ `case NEW` đến `case Status.NEW`

Giả sử:

```java
enum Status { NEW, RUNNING, DONE }
```

Khi selector là enum cụ thể, hai cách sau đều hợp lệ trong Java 21:

**Cách 1 — tên ngắn (đặc trưng của switch trên enum):**

```java
static String shortName(Status value) {
    return switch (value) {
        case NEW     -> "NEW";
        case RUNNING -> "RUNNING";
        case DONE    -> "DONE";
    };
}
```

**Cách 2 — tên định danh đầy đủ (qualified name):**

```java
static String qualifiedName(Status value) {
    return switch (value) {
        case Status.NEW     -> "NEW";
        case Status.RUNNING -> "RUNNING";
        case Status.DONE    -> "DONE";
    };
}
```

`Status.NEW` là hằng enum đã tồn tại, **không phải** tên biến mới. Hai `switch` trên tương đương về lựa chọn nhánh với các giá trị `Status` khác `null`.

Trong những ví dụ đơn giản với một kiểu enum, tên ngắn thường dễ đọc hơn. Khi selector là interface/kiểu cha và có nhiều enum cùng tham gia, tên đầy đủ trở nên cần thiết để xác định chính xác hằng được so khớp.

### Nhóm nhiều enum constant vào một nhánh

Một nhánh có thể liệt kê nhiều **hằng**:

```java
static boolean notFinished(Status value) {
    return switch (value) {
        case NEW, RUNNING -> true;
        case DONE         -> false;
    };
}
```

Trong Java 21, có thể ghi phiên bản dùng tên đầy đủ:

```java
static boolean notFinishedQualified(Status value) {
    return switch (value) {
        case Status.NEW, Status.RUNNING -> true;
        case Status.DONE                -> false;
    };
}
```

`case Status.NEW, Status.RUNNING` là danh sách **hai case constant**, không phải hai type pattern. Nó không giới thiệu biến pattern nào cho thân nhánh.

## 3. Trường hợp quan trọng: selector là interface, enum triển khai interface

Giả sử hệ thống có hai nhóm sự kiện:

```java
sealed interface Event permits State, Level {}

enum State implements Event {
    CREATED, PROCESSED, FAILED
}

enum Level implements Event {
    INFO, WARN
}
```

Đây là các khai báo minh họa, có thể đặt cùng nhau trong một file Java 21 với các loại top-level không mang `public`. `Event` là **sealed interface** và chỉ cho phép `State` cùng `Level` triển khai trực tiếp. Các enum triển khai interface được chấp nhận là các kiểu con cuối cùng (*final* theo tính chất enum).

Một phương thức có tham số `Event event` có thể nhận **bất kỳ** hằng nào của `State` hoặc `Level`. Kiểu tĩnh selector là `Event`, không phải enum `State` hay `Level`.

**Cú pháp Java 21:**

```java
static String nameOf(Event event) {
    return switch (event) {
        case State.CREATED   -> "state-created";
        case State.PROCESSED -> "state-processed";
        case State.FAILED    -> "state-failed";
        case Level.INFO      -> "level-info";
        case Level.WARN      -> "level-warn";
        case null            -> "missing";
    };
}
```

Với `event = State.FAILED`, `switch` chọn `case State.FAILED`; với `event = Level.INFO`, nó chọn `case Level.INFO`. **Không cần** ép `Event` thành enum cụ thể và cũng không cần một chuỗi `if (event instanceof ...)`.

**Vì sao phải viết `State.CREATED`, không phải chỉ `CREATED`?** Vì selector có kiểu `Event` — một interface chứ không phải một kiểu enum duy nhất. Java không thể suy ra loại enum cần tìm cho tên không định danh `CREATED`. Trong trường hợp này, case constant enum cần có tên được định danh kiểu và giá trị của nó phải *assignment-compatible* với kiểu selector.

Trong ví dụ trên, cả `State` và `Level` đều triển khai `Event`; vì vậy các hằng của chúng gán được cho `Event`, thỏa điều kiện.

### Nếu hai enum có hằng cùng tên thì sao?

```java
sealed interface Action permits NetworkAction, FileAction {}

enum NetworkAction implements Action {
    OPEN, CLOSE
}

enum FileAction implements Action {
    OPEN, CLOSE
}
```

Từ `Action action`, có thể viết:

```java
static String label(Action action) {
    return switch (action) {
        case NetworkAction.OPEN  -> "network-open";
        case NetworkAction.CLOSE -> "network-close";
        case FileAction.OPEN     -> "file-open";
        case FileAction.CLOSE    -> "file-close";
    };
}
```

`NetworkAction.OPEN` và `FileAction.OPEN` là **hai hằng khác nhau** dù đều có tên `OPEN`. Việc định danh bằng enum class tránh nhập nhằng, và các case constant có thể trực tiếp diễn đạt nghiệp vụ khác nhau của từng enum.

Đây là một lợi ích rõ ràng của qualified enum constants so với cách phải viết nhiều type pattern có `when` chỉ để so một hằng.

## 4. So sánh qualified enum constant và guarded type pattern

Trước khi cú pháp qualified enum constant được chuẩn hóa, việc kiểm tra một hằng bên trong selector kiểu interface trong các phiên bản preview thường được minh họa bằng type pattern kết hợp điều kiện:

```java
static String oldStyle(Event event) {
    return switch (event) {
        case State s when s == State.CREATED -> "created";
        case State s when s == State.FAILED  -> "failed";
        case State s                        -> "other-state";
        case Level l                        -> "level-" + l.name();
    };
}
```

Đây là **đoạn minh họa cú pháp type pattern + guard trong Java 21**; nó không phải chương trình độc lập. `case State s` kiểm tra đối tượng thuộc enum `State`, gắn biến `s`; phần `when` tiếp tục so `s` với hằng cụ thể.

Nếu mục tiêu chỉ là nhận diện một enum constant, Java 21 cho cách ngắn hơn:

```java
static String newStyle(Event event) {
    return switch (event) {
        case State.CREATED -> "created";
        case State.FAILED  -> "failed";
        case State s       -> "other-state";
        case Level l       -> "level-" + l.name();
    };
}
```

Những điểm khác biệt:

| Cú pháp | Ý nghĩa | Biến mới? | Khi phù hợp |
| --- | --- | --- | --- |
| `case State.CREATED` | Khớp đúng hằng `State.CREATED` | Không | Một giá trị enum cụ thể |
| `case State.CREATED, State.FAILED` | Khớp một trong hai hằng | Không | Gộp nhiều hằng dùng chung xử lý |
| `case State s` | Khớp mọi hằng của enum `State` | Có: `s` | Xử lý chung cả một enum |
| `case State s when s == State.CREATED` | Khớp enum `State` và so thêm điều kiện | Có: `s` | Khi thực sự cần cấu trúc guard |
| `case Level l when l.name().startsWith("W")` | Kiểm tra kiểu rồi kiểm tra thuộc tính | Có: `l` | Điều kiện động/phức tạp hơn so hằng |

`case State.CREATED` **không phải là một type pattern** và không tạo ra biến `CREATED`. Các quy tắc của biến pattern chỉ áp dụng cho những nhánh khai báo pattern variable như `case State s`.

### Quy tắc `when` không áp dụng trực tiếp cho case constant

Đoạn sau **không hợp lệ**:

```java
// KHÔNG BIÊN DỊCH:
// return switch (event) {
//     case State.CREATED when someCondition -> "created";
//     default -> "other";
// };
```

Trong Java 21, `when` gắn với **case pattern**, chẳng hạn `case State s when ...`, không gắn trực tiếp với `case` chứa một hằng enum. Khi muốn xử lý có điều kiện sau khi đã khớp `State.CREATED`, bạn có thể kiểm tra bằng `if` trong thân nhánh, hoặc dùng một guarded type pattern thích hợp.

## 5. Thứ tự nhánh và quy tắc dominance

Với pattern switch, thứ tự các case không chỉ ảnh hưởng cách người đọc hiểu mã. **Dominance** là quy tắc biên dịch ngăn một case nằm sau bị một pattern phía trước bao phủ hoàn toàn.

Ví dụ sau **hợp lệ**:

```java
static String inspect(Event event) {
    return switch (event) {
        case State.FAILED -> "failed-special";
        case State s      -> "state:" + s.name();
        case Level l      -> "level:" + l.name();
    };
}
```

Khi `event == State.FAILED`, hằng cụ thể được xử lý ở nhánh đầu; các hằng `State` còn lại đi vào `case State s`. Những hằng `Level` đi vào `case Level l`.

**Nếu đảo thứ tự hai nhánh đầu thì không hợp lệ:**

```java
// KHÔNG BIÊN DỊCH: case State.FAILED bị che khuất.
// return switch (event) {
//     case State s      -> "state:" + s.name();
//     case State.FAILED -> "failed-special";
//     case Level l      -> "level:" + l.name();
// };
```

Vì `case State s` khớp **mọi hằng của `State`**, nên `case State.FAILED` phía sau không thể là nhánh được chọn. Java 21 báo lỗi *dominated case label*.

**Nguyên tắc sắp xếp:** đặt các enum constant cụ thể **trước** type pattern bao quát enum đó; đặt nhánh tổng quát sau các ngoại lệ cần ưu tiên.

### Không thể trộn hằng và type pattern vào cùng một danh sách case

```java
// KHÔNG BIÊN DỊCH:
// case State.FAILED, State s -> "value";
```

Một case label dạng danh sách có thể gồm các **case constant**, còn nhánh có một **case pattern** là dạng khác. Khi cần phân biệt `State.FAILED` với các hằng `State` còn lại, hãy viết hai case riêng như ví dụ hợp lệ ở trên.

### Cùng một hằng xuất hiện hai lần

```java
// KHÔNG BIÊN DỊCH: duplicate case constant.
// switch (event) {
//     case State.FAILED -> System.out.println("A");
//     case State.FAILED -> System.out.println("B");
//     default -> System.out.println("Other");
// }
```

Hai nhánh có cùng một enum constant tạo lỗi biên dịch do trùng nhãn case. Thay vì lập lại hằng ở hai nơi, hãy gộp xử lý hoặc đặt điều kiện phụ trong thân nhánh phù hợp.

## 6. Bao phủ toàn bộ trường hợp (exhaustiveness) với enum constants

Một **switch expression** phải có khả năng trả về kết quả cho mọi giá trị hợp lệ được yêu cầu bao phủ. Với enum, Java có thể kiểm tra đủ các hằng ở thời điểm biên dịch:

```java
enum Traffic { RED, YELLOW, GREEN }

static String action(Traffic traffic) {
    return switch (traffic) {
        case RED    -> "Stop";
        case YELLOW -> "Wait";
        case GREEN  -> "Go";
    };
}
```

Không cần `default` vì cả ba hằng `Traffic` đã được liệt kê. Nếu bỏ `case GREEN` mà không có nhánh tổng quát khác, `switch` expression không còn exhaustive và sẽ bị từ chối khi biên dịch.

### Selector là sealed interface với nhiều enum

Trong ví dụ `Event permits State, Level`, **tập case constant của cả hai enum** cũng có thể tạo thành một switch expression exhaustive:

```java
static int code(Event event) {
    return switch (event) {
        case State.CREATED   -> 1;
        case State.PROCESSED -> 2;
        case State.FAILED    -> 3;
        case Level.INFO      -> 4;
        case Level.WARN      -> 5;
    };
}
```

Điều này hợp lệ trên Java 21: các nhánh bao phủ mọi hằng của `State` và `Level`, mà đó là hai kiểu được `Event` cho phép. Trình biên dịch có thể xác định tính exhaustive theo **enum coverage** kết hợp với **sealed hierarchy coverage**.

Một lựa chọn khác là dùng type pattern để bao phủ các loại enum:

```java
static String generic(Event event) {
    return switch (event) {
        case State s -> "State: " + s;
        case Level l -> "Level: " + l;
    };
}
```

Cách này cũng exhaustive vì `Event` chỉ cho phép hai enum đó. Nhưng nó **không phân biệt từng hằng**. Hãy dùng từng enum constant khi hành vi của các giá trị khác nhau; dùng type pattern khi các giá trị của cùng một enum có thể xử lý chung.

### Exhaustive không đồng nghĩa tự xử lý `null`

Đây là một điểm rất quan trọng:

```java
static String statusName(State state) {
    return switch (state) {
        case CREATED   -> "created";
        case PROCESSED -> "processed";
        case FAILED    -> "failed";
    };
}
```

Mã **biên dịch được**, vì đã liệt kê đủ hằng `State`. Nhưng gọi `statusName(null)` không vào nhánh hằng nào và **ném `NullPointerException`**. Tính exhaustive đối với các hằng enum không tự biến `null` thành một enum constant.

Trong Java 21, có thể chủ động xử lý `null`:

```java
static String statusNameOrMissing(State state) {
    return switch (state) {
        case null      -> "missing";
        case CREATED   -> "created";
        case PROCESSED -> "processed";
        case FAILED    -> "failed";
    };
}
```

`case null` là nhãn riêng xử lý giá trị `null`, không phải một hằng `State`.

**`default` không tự bắt `null`** trong pattern switch Java 21. Ví dụ `case State s` và `default` cũng không làm `null` được xử lý theo ý muốn nếu không có nhánh `case null`. Có thể dùng cú pháp gộp `case null, default -> ...` khi muốn cùng một cách xử lý cho `null` và các giá trị còn lại.

## 7. Selector không phải enum: dùng với `Object` và phân loại rộng hơn

Nhờ Java 21, `switch` có thể dùng kiểu tham chiếu tổng quát. Ví dụ phương thức nhận `Object`:

```java
static String classifyAny(Object value) {
    return switch (value) {
        case null         -> "null";
        case State.FAILED -> "failed";
        case State s      -> "state:" + s.name();
        case Level.WARN   -> "warning";
        case Level l      -> "level:" + l.name();
        default           -> "other";
    };
}
```

Các nhánh được xét theo khả năng khớp:

- `State.FAILED` khớp đúng giá trị đó.
- `State s` xử lý các hằng `State` khác `FAILED`.
- `Level.WARN` khớp đúng mức cảnh báo.
- `Level l` xử lý các hằng `Level` khác `WARN`.
- `case null` xử lý `null`.
- `default` xử lý các kiểu khác không thuộc những nhánh đã liệt kê.

Vì `Object` có thể chứa rất nhiều kiểu, liệt kê mọi giá trị của chỉ hai enum **không làm** switch trên `Object` exhaustive. Dùng `default` hoặc một pattern bao quát phù hợp để xử lý các khả năng còn lại.

### Vì sao `case State.FAILED` hợp lệ trên `Object`?

Hằng `State.FAILED` là một đối tượng; bất kỳ đối tượng `State` nào cũng có thể được gán cho biến `Object`. Theo quy tắc switch compatibility của Java 21, enum case constant phải có kiểu *assignment-compatible* với selector. `State` tương thích với `Object`, nên nhánh hằng hợp lệ.

Ngược lại, nếu selector có kiểu `Level`, bạn không được dùng `case State.FAILED` vì hằng `State` không thể gán cho biến `Level`. **Đó là lỗi biên dịch về tương thích kiểu**, không phải một nhánh hợp lệ chỉ trả `false`.

## 8. Chương trình Java 21 hoàn chỉnh, có thể biên dịch và chạy

Tạo file **`EnumConstantPatternSwitchDemo.java`** đúng tên class công khai:

```java
import java.util.Locale;

public class EnumConstantPatternSwitchDemo {

    sealed interface Event permits State, Level {}

    enum State implements Event {
        CREATED, PROCESSED, FAILED
    }

    enum Level implements Event {
        INFO, WARN
    }

    // Selector là interface Event, nhưng case có thể là
    // hằng của các enum triển khai interface đó.
    static String describe(Event event) {
        return switch (event) {
            case State.CREATED   -> "state-created";
            case State.PROCESSED -> "state-processed";
            case State.FAILED    -> "state-failed";
            case Level.INFO      -> "level-info";
            case Level.WARN      -> "level-warn";
            case null            -> "missing";
        };
    }

    // Switch trên một enum cụ thể, dùng tên hằng ngắn.
    static String grouped(State state) {
        return switch (state) {
            case CREATED, PROCESSED -> "IN_PROGRESS";
            case FAILED             -> "STOPPED";
        };
    }

    // Enum constant cụ thể phải đứng trước type pattern
    // bao quát enum đó để tránh dominated case.
    static String mixed(Event event) {
        return switch (event) {
            case null        -> "UNKNOWN";
            case State.FAILED -> "STOP";
            case State s      -> "STATE:" +
                    s.name().toLowerCase(Locale.ROOT);
            case Level.WARN   -> "ALERT";
            case Level l      -> "LEVEL:" +
                    l.name().toLowerCase(Locale.ROOT);
        };
    }

    // Selector kiểu Object: có cả qualified enum
    // constants, type patterns và nhánh mặc định.
    static String fromObject(Object value) {
        return switch (value) {
            case null         -> "EMPTY";
            case State.CREATED -> "new state";
            case State s       -> "state:" + s.name();
            case Level.WARN    -> "warning";
            case Level l       -> "level:" + l.name();
            default            -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(State.CREATED));
        System.out.println(describe(Level.WARN));
        System.out.println(describe(null));

        System.out.println(grouped(State.PROCESSED));
        System.out.println(grouped(State.FAILED));

        System.out.println(mixed(State.FAILED));
        System.out.println(mixed(State.PROCESSED));
        System.out.println(mixed(Level.INFO));
        System.out.println(mixed(Level.WARN));

        System.out.println(fromObject(State.CREATED));
        System.out.println(fromObject(Level.INFO));
        System.out.println(fromObject(17));
        System.out.println(fromObject(null));
    }
}
```

Dùng **JDK 21 hoặc cao hơn**:

```bash
javac --release 21 EnumConstantPatternSwitchDemo.java
java EnumConstantPatternSwitchDemo
```

Kết quả mong đợi:

```text
state-created
level-warn
missing
IN_PROGRESS
STOPPED
STOP
STATE:processed
LEVEL:info
ALERT
new state
level:INFO
other
EMPTY
```

**Giải thích các nhánh chính:**

1. `describe` nhận `Event`, nhưng so trực tiếp từng enum constant của `State` và `Level`. Vì cả hai enum được bao phủ đủ, `switch` expression exhaustive; `case null` xử lý riêng đầu vào rỗng.
2. `grouped` biểu diễn switch enum truyền thống: nhiều hằng có thể chia sẻ một nhánh, không cần khai báo pattern variable.
3. `mixed` đặt `State.FAILED` trước `State s`, `Level.WARN` trước `Level l`. `State.PROCESSED` đi tới type pattern `State s` và in `STATE:processed`; `Level.WARN` được nhánh hằng cụ thể xử lý thành `ALERT`.
4. `fromObject` còn nhận được số `17` (đóng hộp thành `Integer`). Không nhánh enum nào khớp nên chọn `default` và in `other`.
5. `null` được kiểm tra trước bằng `case null` ở các switch nhận kiểu tham chiếu, tránh việc mặc định ném `NullPointerException`.

Chương trình sử dụng **Java 21 finalized features**; không có `--enable-preview` trong lệnh biên dịch. Nếu IDE hoặc công cụ build đang đặt language level 17, nó có thể báo lỗi với chính cú pháp `case State.CREATED` trên selector `Event` và các type pattern trong switch — cần chọn JDK/language level 21 cho ví dụ này.

## 9. Các lỗi biên dịch phổ biến và cách sửa

### Lỗi 1: dùng hằng enum không định danh khi selector là interface

```java
// KHÔNG HỢP LỆ nếu event có kiểu Event:
// switch (event) {
//     case CREATED -> System.out.println("created");
//     default -> System.out.println("other");
// }
```

`Event` không phải là kiểu enum cụ thể để Java gắn tên ngắn `CREATED` với một enum class.

**Sửa:**

```java
switch (event) {
    case State.CREATED -> System.out.println("created");
    default            -> System.out.println("other");
}
```

Đoạn sửa minh họa một câu lệnh bên trong phương thức có biến `Event event` đã khai báo; nếu `event == null`, phải thêm `case null` nếu không muốn ném `NullPointerException`.

### Lỗi 2: dùng hằng enum không thể gán cho kiểu selector

```java
// KHÔNG BIÊN DỊCH nếu level có kiểu Level:
// switch (level) {
//     case State.CREATED -> System.out.println("bad");
//     default -> System.out.println("other");
// }
```

`State.CREATED` có kiểu `State`, không thể gán cho biến `Level`. Chỉ dùng hằng của kiểu enum tương thích với selector, hoặc mở rộng selector thành interface chung nếu nghiệp vụ thực sự nhận cả hai enum.

### Lỗi 3: đặt type pattern tổng quát trước hằng cụ thể

```java
// KHÔNG BIÊN DỊCH do dominated case:
// switch (event) {
//     case State s       -> System.out.println("any-state");
//     case State.CREATED -> System.out.println("created");
//     case Level l       -> System.out.println("level");
// }
```

**Sửa:** đưa `case State.CREATED` lên trước `case State s` để xử lý ngoại lệ cụ thể trước, phần còn lại bằng nhánh chung.

### Lỗi 4: tưởng case enum constant có biến pattern

```java
// KHÔNG HỢP LỆ:
// switch (event) {
//     case State.CREATED -> System.out.println(CREATED.name());
//     default -> System.out.println("other");
// }
```

`case State.CREATED` không khai báo biến tên `CREATED`. Nếu cần dùng giá trị hằng, gọi trực tiếp `State.CREATED.name()`; nếu cần đối tượng thực tế đã khớp với kiểu `State`, dùng `case State s` rồi truy cập `s`.

### Lỗi 5: gắn `when` trực tiếp sau enum constant

```java
// KHÔNG BIÊN DỊCH:
// case State.CREATED when flag -> "created";
```

`when` chỉ dùng sau case pattern. Với hằng cụ thể, dùng `case State.CREATED -> { ... }` để kiểm tra điều kiện trong thân nhánh hoặc chuyển sang `case State s when s == State.CREATED && flag` nếu muốn diễn đạt guard.

### Lỗi 6: cho rằng `default` xử lý mọi `null`

```java
// Vẫn ném NullPointerException nếu event là null:
static String wrongNullHandling(Event event) {
    return switch (event) {
        case State s -> "state";
        case Level l -> "level";
        default      -> "other";
    };
}
```

**Sửa:** thêm `case null -> "missing"` hoặc nhãn gộp `case null, default -> "other"` tùy ý nghĩa nghiệp vụ. `null` không phải một enum constant.

### Lỗi 7: switch expression thiếu nhánh bao phủ

```java
// KHÔNG BIÊN DỊCH nếu status có kiểu State:
// return switch (status) {
//     case CREATED   -> "created";
//     case PROCESSED -> "processed";
// };
```

Thiếu `FAILED`. Thêm `case FAILED`, hoặc có một nhánh bao quát phù hợp. Một ưu điểm của enum exhaustive switch là trình biên dịch giúp phát hiện trường hợp bị bỏ sót khi nguồn được biên dịch lại.

## 10. Khi nào chọn enum constant, type pattern, hoặc `when`?

| Bài toán | Cách ưu tiên | Lý do |
| --- | --- | --- |
| Selector là enum cụ thể, mỗi hằng có một hành vi | `case CREATED`, `case FAILED` | Gọn, dễ xem đủ các hằng |
| Selector là interface có nhiều enum triển khai | `case State.CREATED`, `case Level.WARN` | Chỉ rõ nguồn gốc của mỗi hằng |
| Nhiều hằng enum dùng cùng hành vi | `case State.CREATED, State.PROCESSED` | Gộp nhánh hằng có chủ đích |
| Cần xử lý chung mọi giá trị thuộc một enum | `case State s` | Có biến kiểu `State` để dùng |
| Cần ngoại lệ cho một hằng trước xử lý chung | Hằng cụ thể trước, type pattern sau | Tránh domination, dễ đọc |
| Điều kiện kiểm tra phụ thuộc thuộc tính hoặc trạng thái động | `case State s when ...` | Guard bổ sung cho pattern |
| Selector có thể là `null` | `case null` | Xử lý tường minh null |
| Đầu vào có nhiều kiểu ngoài các enum đã biết | `default` hoặc pattern bao quát | Đảm bảo có nhánh xử lý các giá trị còn lại |

**Lưu ý thiết kế:** Một chuỗi rất dài các nhánh cho từng enum constant có thể hợp lý nếu các hằng tương ứng với những trạng thái nghiệp vụ cố định. Nhưng nếu mọi hằng có cùng hành vi, dùng `case State s` hoặc một phương thức đa hình trên interface sẽ giảm trùng lặp. Không cần ép mọi switch thành pattern switch.

## 11. Bài tập thực hành và đáp án

### Bài 1 — nhận diện case constant hay case pattern

Cho ba nhánh:

```java
case State.CREATED -> "a";
case State s -> "b";
case State s when s == State.FAILED -> "c";
```

**Câu hỏi:** Nhánh nào khai báo biến pattern?

**Đáp án:** Hai nhánh có `State s` khai báo biến `s`; `State.CREATED` chỉ là một case constant. Lưu ý ba dòng trên là các **mảnh cú pháp** để nhận diện; nếu đặt cả ba theo đúng thứ tự đó trong cùng một switch, nhánh thứ ba sẽ bị `case State s` trước nó thống trị và gây lỗi biên dịch. Khi cần `case` đặc biệt, đặt guard hoặc hằng cụ thể trước nhánh chung.

### Bài 2 — vì sao ví dụ sau bị từ chối?

```java
// KHÔNG BIÊN DỊCH:
// static String task(Event event) {
//     return switch (event) {
//         case State s      -> "any state";
//         case State.FAILED -> "failed";
//         case Level l      -> "level";
//     };
// }
```

**Đáp án:** `case State s` đã khớp tất cả các giá trị `State`, bao gồm `State.FAILED`, nên `case State.FAILED` phía sau là nhánh không thể được chọn (*dominated*). Đưa nhánh `State.FAILED` lên trước.

### Bài 3 — điền đủ switch expression

Giả sử:

```java
enum Result { OK, RETRY, ERROR }
```

Viết phương thức chuyển mọi giá trị `Result` khác `null` thành ba chuỗi tương ứng `"success"`, `"again"`, `"failure"`. Không dùng `default`, để compiler kiểm tra đủ enum constants.

**Gợi ý đáp án:**

```java
static String message(Result result) {
    return switch (result) {
        case OK    -> "success";
        case RETRY -> "again";
        case ERROR -> "failure";
    };
}
```

Với đầu vào `null`, phương thức này ném `NullPointerException`; nếu muốn trả `"missing"`, thêm `case null -> "missing"` khi biên dịch bằng Java 21.

### Bài 4 — phân loại hai enum có cùng tên hằng

Giả sử interface `Action` được triển khai bởi `NetworkAction` và `FileAction` ở phần 3. Viết `switch (Action action)` để trả `"net-open"` cho `NetworkAction.OPEN`, `"file-open"` cho `FileAction.OPEN`, và `"close"` cho cả hai hằng `CLOSE`.

**Đáp án:**

```java
static String classify(Action action) {
    return switch (action) {
        case NetworkAction.OPEN  -> "net-open";
        case FileAction.OPEN     -> "file-open";
        case NetworkAction.CLOSE, FileAction.CLOSE -> "close";
    };
}
```

Cần dùng **tên enum được định danh** vì selector là interface `Action`. Nhánh thứ ba chứa **hai enum constant** có cùng kết quả. Toàn bộ các hằng của hai enum đã được bao phủ nên switch expression exhaustive trên Java 21.

### Bài 5 — dự đoán đầu ra

Với chương trình hoàn chỉnh ở phần 8:

- `describe(State.FAILED)` → `"state-failed"`.
- `mixed(State.FAILED)` → `"STOP"`, vì hằng cụ thể đứng trước type pattern `State s`.
- `mixed(State.CREATED)` → `"STATE:created"`, vì không trùng `State.FAILED` nhưng khớp `State s`.
- `fromObject(42)` → `"other"`, vì `Integer` không thuộc hai enum.
- `fromObject(null)` → `"EMPTY"`, vì có `case null`.

Giải thích vì sao từng nhánh được chọn quan trọng hơn việc học thuộc đầu ra.

## 12. Tóm tắt kiến thức cần nhớ

1. **Enum constant** như `State.CREATED` là một giá trị enum cụ thể. `case State.CREATED` là **case constant**, không khai báo pattern variable.
2. **Java 21** cho phép qualified enum constants trong switch ngay cả khi selector là một interface hoặc kiểu tham chiếu rộng hơn, nếu hằng đó có thể gán cho kiểu selector.
3. Với selector kiểu enum cụ thể, `case CREATED` vẫn là cách viết ngắn hợp lệ. Với selector kiểu interface có nhiều enum triển khai, viết `case State.CREATED`, `case Level.WARN` để nêu rõ hằng cần khớp.
4. Có thể trộn enum constants với type patterns trong cùng switch, nhưng đặt **hằng cụ thể trước pattern rộng hơn** để tránh lỗi dominance.
5. **`when` chỉ đi cùng case pattern**, không đi trực tiếp sau enum case constant.
6. Switch expression phải exhaustive; với enum hoặc sealed hierarchy phù hợp, liệt kê đủ các hằng có thể đáp ứng yêu cầu này mà không cần `default`.
7. **`null` không phải enum constant**. Tính exhaustive theo hằng không tự xử lý `null`; nếu muốn xử lý `null`, dùng `case null` trong Java 21.

**Mấu chốt:** Trong pattern switch, enum constant là công cụ nhận diện **chính xác một giá trị**, còn type pattern nhận diện **cả một loại đối tượng**. Hiểu sự khác nhau giúp viết switch ngắn hơn, kiểm tra tính bao phủ tốt hơn và tránh lỗi tương thích kiểu hoặc nhánh bị che khuất.

## Tài liệu tham khảo chính thức

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [Java SE 21 Language Specification, §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification, §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
