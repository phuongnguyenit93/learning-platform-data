# Kết hợp constant case và pattern case trong một switch

Trong Java 21, một câu lệnh hoặc biểu thức `switch` có thể kết hợp **constant case label** với **pattern case label**. Constant case xử lý những giá trị cụ thể đã biết, chẳng hạn chuỗi trạng thái hoặc hằng enum. Pattern case xử lý theo kiểu và cấu trúc của giá trị, đồng thời có thể bind dữ liệu vào biến để dùng ngay trong nhánh tương ứng.

Kết hợp hai loại case giúp một `switch` xử lý cả trường hợp đặc biệt lẫn nhóm dữ liệu tổng quát. Khi viết, cần chú ý thứ tự các nhãn để tránh nhãn phía sau bị nhãn trước bao phủ (dominance), đồng thời xử lý `null` rõ ràng. Pattern matching for `switch` và cú pháp guard `when` là tính năng chính thức trong Java 21, không cần bật preview.

## 1. Hai loại case label trong cùng một switch

**Constant case label** khớp với một giá trị cụ thể. Các ví dụ phổ biến là hằng chuỗi, hằng số nguyên và hằng enum:

```java
case "READY" -> "Đã sẵn sàng";
case "FAILED" -> "Thất bại";
```

**Pattern case label** khớp theo kiểu hoặc cấu trúc của giá trị. Pattern có thể tạo biến để nhánh xử lý sử dụng:

```java
case String text -> "Văn bản: " + text;
case Integer number -> "Số nguyên: " + number;
```

Constant case trả lời câu hỏi “giá trị có đúng bằng hằng này không?”. Pattern case trả lời câu hỏi “giá trị có khớp kiểu hoặc cấu trúc này không?”. Vì một pattern rộng có thể bao phủ nhiều giá trị cụ thể, thứ tự nhãn có ý nghĩa trực tiếp đến khả năng biên dịch.

## 2. Ví dụ kết hợp constant case và pattern case

Constant expression labels như chuỗi literal chỉ hợp lệ với những kiểu selector được Java quy định, trong đó có `String`. Vì vậy, hãy dùng selector `String` khi cần kết hợp chuỗi literal với pattern cho các chuỗi còn lại:

```java
public class PatternSwitchDemo {
    static String describeText(String value) {
        return switch (value) {
            case null -> "Không có giá trị";

            // Constant case: chỉ khớp đúng các chuỗi này.
            case "PING", "HEALTH" -> "Yêu cầu kiểm tra trạng thái";
            case "STOP" -> "Yêu cầu dừng";

            // Guarded pattern: chỉ khớp chuỗi rỗng hoặc toàn khoảng trắng.
            case String text when text.isBlank() -> "Chuỗi trống";

            // Type pattern: xử lý mọi chuỗi còn lại.
            case String text -> "Văn bản: " + text;
        };
    }

    public static void main(String[] args) {
        System.out.println(describeText("PING"));
        System.out.println(describeText("   "));
        System.out.println(describeText("Java 21"));
        System.out.println(describeText(null));
    }
}
```

Biên dịch và chạy với JDK 21:

```shell
javac --release 21 PatternSwitchDemo.java
java PatternSwitchDemo
```

Kết quả:

```text
Yêu cầu kiểm tra trạng thái
Chuỗi trống
Văn bản: Java 21
Không có giá trị
```

Trong ví dụ, `"PING"`, `"HEALTH"` và `"STOP"` là constant case. Pattern `String text` xử lý các chuỗi khác; `String text when text.isBlank()` lọc riêng chuỗi trống. Pattern không guard cuối cùng là pattern tổng quát cho kiểu selector `String`, nên biểu thức switch đã bao phủ mọi giá trị chuỗi không null; `case null` xử lý trường hợp còn lại.

Không chuyển nguyên các literal này sang `switch (value)` nếu `value` có kiểu `Object`: constant expression label kiểu `String` không tương thích với selector `Object`. Khi selector là `Object`, có thể dùng type pattern và record pattern; ví dụ:

```java
record Command(String name, int priority) {}

static String describeObject(Object value) {
    return switch (value) {
        case null -> "Không có giá trị";
        case Command(String name, int priority) ->
                "Lệnh " + name + ", độ ưu tiên " + priority;
        case String text when text.isBlank() -> "Chuỗi trống";
        case String text -> "Văn bản: " + text;
        case Integer number -> "Số nguyên: " + number;
        case Number number -> "Số khác: " + number;
        default -> "Kiểu khác: " + value.getClass().getSimpleName();
    };
}
```

Đoạn thứ hai dùng `Object` và chỉ có pattern labels cùng `null`/`default`. Nó cho phép nhận diện nhiều kiểu runtime, nhưng không phân biệt `String` literal như `"PING"` bằng constant case.

## 3. Thứ tự case và quy tắc dominance

Một case label bị *dominated* khi một nhãn đứng trước đã bao phủ mọi giá trị mà nhãn đó có thể khớp. Nhãn bị dominated không thể được thực thi và trình biên dịch báo lỗi.

### Đặt constant trước pattern bao phủ nó

Đúng:

```java
static String describe(String value) {
    return switch (value) {
        case "READY" -> "Đã sẵn sàng";
        case String text -> "Chuỗi khác: " + text;
        case null -> "Không có giá trị";
    };
}
```

Sai:

```java
static String describe(String value) {
    return switch (value) {
        case String text -> "Chuỗi: " + text;
        // LỖI: nhãn String phía trên đã bao phủ mọi chuỗi, gồm cả READY.
        case "READY" -> "Đã sẵn sàng";
        case null -> "Không có giá trị";
    };
}
```

`case String text` khớp mọi giá trị không null có kiểu `String`. Vì vậy, nếu đặt trước, nó làm cho constant case `"READY"` không còn cơ hội khớp. Hãy đặt các constant cụ thể trước pattern rộng tương ứng.

### Đặt pattern cụ thể trước pattern tổng quát

Đúng:

```java
static String describe(Object value) {
    return switch (value) {
        case Integer number -> "Số nguyên: " + number;
        case Number number -> "Số: " + number;
        default -> "Kiểu khác";
    };
}
```

Sai:

```java
static String describe(Object value) {
    return switch (value) {
        case Number number -> "Số: " + number;
        // LỖI: Number đã bao gồm Integer.
        case Integer number -> "Số nguyên: " + number;
        default -> "Kiểu khác";
    };
}
```

`Integer` là lớp con của `Number`, nên pattern `Number` đứng trước sẽ bao phủ các giá trị `Integer`. Nguyên tắc này cũng áp dụng cho các quan hệ kế thừa khác: đặt pattern hẹp trước pattern rộng khi cả hai cùng có thể khớp selector.

### Guarded pattern và pattern không có guard

Guarded pattern dùng từ khóa `when` để thêm điều kiện boolean. Đặt trường hợp có guard trước pattern không có guard cùng kiểu:

```java
static String describe(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "Chuỗi trống";
        case String text -> "Chuỗi có nội dung: " + text;
        default -> "Kiểu khác";
    };
}
```

Guard có thể khiến một pattern chỉ khớp một phần giá trị thuộc kiểu đó. Nếu pattern không có guard đứng trước, nó đã nhận mọi giá trị của kiểu và làm nhánh có guard phía sau trở nên unreachable.

Trong guard, pattern variable đã được bind và có thể sử dụng trực tiếp, ví dụ `text.isBlank()`. Nếu guard trả về `false`, việc xét case tiếp tục với các nhãn sau theo thứ tự. Guard không thay thế kiểm tra kiểu của pattern; nó bổ sung điều kiện sau khi pattern khớp.

## 4. Kết hợp nhiều constant case cho cùng một hành động

Khi nhiều hằng có cùng cách xử lý, có thể đặt chúng trong một nhãn, phân tách bằng dấu phẩy:

```java
static String statusMessage(String status) {
    return switch (status) {
        case "NEW", "QUEUED" -> "Đang chờ xử lý";
        case "DONE", "SUCCESS" -> "Đã hoàn tất";
        case "ERROR", "FAILED" -> "Đã xảy ra lỗi";
        default -> "Trạng thái chưa xác định";
    };
}
```

Các hằng trong cùng một nhãn phải có kiểu phù hợp với selector và không được lặp lại theo cách gây nhãn trùng. Cú pháp này cũng áp dụng cho hằng enum:

```java
enum Priority {
    LOW, NORMAL, HIGH
}

static String describe(Priority priority) {
    return switch (priority) {
        case LOW -> "Có thể xử lý sau";
        case NORMAL -> "Xử lý theo lịch";
        case HIGH -> "Ưu tiên xử lý";
    };
}
```

Với selector có kiểu enum, các hằng enum được kiểm tra theo giá trị enum. Khi tất cả hằng enum đã được liệt kê, biểu thức `switch` có thể exhaustive mà không cần `default`; nếu enum được mở rộng thêm hằng trong phiên bản biên dịch mới, cần biên dịch và xem xét lại các nhánh.

## 5. Xử lý `null`, `default` và tính exhaustive

`null` có quy tắc riêng trong pattern switch:

- `case null` khớp khi selector có giá trị `null`.
- `default` xử lý các giá trị không null còn lại chưa khớp nhãn nào.
- `default` không tự động khớp `null`.
- Nếu selector là `null` và switch không có `case null`, quá trình đánh giá switch ném `NullPointerException`.

Ví dụ, `default` không bảo vệ chương trình khỏi null:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> text;
        default -> "Kiểu khác";
    };
}
```

Gọi `describe(null)` sẽ ném `NullPointerException`. Nếu muốn xử lý null, thêm nhánh rõ ràng:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Không có giá trị";
        case String text -> text;
        default -> "Kiểu khác";
    };
}
```

Nếu null và các giá trị còn lại có cùng hành động, Java 21 cho phép viết `case null, default -> ...`. Chỉ dùng dạng gộp khi thật sự muốn xử lý null giống mọi trường hợp không khớp.

Với **switch expression**, các nhánh phải bao phủ các trường hợp mà compiler yêu cầu để biểu thức có kết quả trên mọi đường đi. `default` thường dùng để bao phủ những giá trị không được liệt kê. Với selector có thể null, việc biểu thức exhaustive đối với các giá trị thông thường không đồng nghĩa null tự động được xử lý; hãy quyết định rõ có cần `case null` hay chấp nhận `NullPointerException` theo hợp đồng đầu vào.

Với **switch statement** thông thường chỉ dùng selector và constant labels kiểu truyền thống, Java vẫn giữ quy tắc tương thích cũ về tính exhaustive. Nhưng trong Java 21, switch statement có pattern label hoặc `case null` là *enhanced switch statement* và cũng phải exhaustive. Có thể dùng `default`, hoặc bao phủ đầy đủ kiểu selector bằng các pattern phù hợp. Quy tắc khớp nhãn và xử lý null vẫn cần được xem xét ở cả hai dạng.

## 6. Dùng switch expression và switch statement

Switch expression tạo ra một giá trị, phù hợp khi mỗi nhánh tính toán một kết quả. Với selector kiểu `String`, có thể kết hợp hằng chuỗi và pattern cho các chuỗi còn lại:

```java
static String category(String value) {
    return switch (value) {
        case "ADMIN" -> "Quản trị";
        case String text when text.isBlank() -> "Chưa nhập";
        case String text -> "Người dùng: " + text;
        case null -> "Không có người dùng";
    };
}
```

Switch statement thực hiện hành động theo nhánh. Ví dụ sau dùng tham số kiểu `String`; các phương thức xử lý là phần của ứng dụng:

```java
static void dispatch(String commandText) {
    switch (commandText) {
        case "START" -> startService();
        case String command when command.startsWith("LOG-") ->
                writeLog(command);
        case String command -> handleText(command);
        case null -> handleMissingValue();
    }
}
```

Ví dụ dùng arrow labels (`->`), nên không có fall-through giữa các nhánh. Nếu một nhánh switch expression cần nhiều câu lệnh trước khi tạo giá trị, dùng block và `yield` để trả kết quả:

```java
static String normalize(Object value) {
    return switch (value) {
        case String text -> {
            String normalized = text.trim();
            yield normalized.isEmpty() ? "EMPTY" : normalized;
        }
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

## 7. Kết hợp pattern case với record pattern

Pattern case không chỉ kiểm tra kiểu tổng quát. Với record, có thể kiểm tra cấu trúc và lấy component ngay trong nhãn `case`:

```java
record HttpResult(int status, String body) {}

static String describe(Object value) {
    return switch (value) {
        case HttpResult(int status, String body) when status >= 200 && status < 300 ->
                "Thành công: " + body;
        case HttpResult(int status, String body) ->
                "HTTP " + status + ": " + body;
        case String text -> "Văn bản: " + text;
        case null -> "Không có kết quả";
        default -> "Kiểu kết quả không hỗ trợ";
    };
}
```

Hai record pattern xử lý `HttpResult`: nhánh đầu tiên có guard cho status thành công, nhánh tiếp theo xử lý các status còn lại. Vì pattern record thứ hai bao phủ mọi `HttpResult`, nó phải đứng sau pattern có guard. Pattern `String text` xử lý các giá trị chuỗi; `default` xử lý các kiểu còn lại.

Nếu component của record có thể null, cần chọn pattern component và guard phù hợp. Record pattern lồng hoặc type pattern trên component có thể không khớp khi component null; có thể dùng `var` để nhận giá trị component rồi kiểm tra null trong guard hoặc thân nhánh.

## 8. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Constant case không biên dịch hoặc unreachable | Pattern rộng đứng trước đã bao phủ giá trị hằng | Đặt constant case trước pattern bao phủ nó |
| Pattern hẹp bị dominated | Pattern tổng quát đứng trước, ví dụ `Number` trước `Integer` | Đặt pattern cụ thể trước pattern tổng quát |
| Guarded case không bao giờ chạy | Pattern không guard cùng kiểu đã đứng trước và bắt mọi giá trị | Đưa guarded pattern lên trước pattern không guard |
| `switch` ném `NullPointerException` | Selector là null nhưng không có `case null` | Thêm `case null` hoặc xác định rõ hợp đồng không chấp nhận null |
| Switch expression không exhaustive | Chưa có nhánh bao phủ một số giá trị có thể xảy ra | Thêm `default` hoặc hoàn thiện các nhánh theo kiểu selector |
| Không dùng được biến pattern trong nhánh | Biến được khai báo trong pattern chỉ có phạm vi ở nhánh tương ứng | Dùng biến trong guard hoặc thân nhánh đã bind nó |
| Dùng cú pháp guard cũ hoặc không đúng phiên bản | Cú pháp guard chính thức hiện tại dùng `when` | Viết `case Type value when condition -> ...` và biên dịch theo Java 21 |

Khi trình biên dịch báo một nhãn bị dominated, hãy kiểm tra toàn bộ các nhãn đứng trước. Câu hỏi quan trọng là liệu có giá trị nào có thể đi đến nhãn đó sau khi các nhãn trước đã được xét hay không.

## 9. Checklist trước khi hoàn thiện pattern switch

- Đã phân biệt constant case (giá trị cụ thể) và pattern case (kiểu hoặc cấu trúc).
- Đặt constant cụ thể trước pattern rộng có thể bao phủ constant đó.
- Đặt pattern hẹp trước pattern tổng quát trong cùng hệ phân cấp kiểu.
- Đặt guarded pattern trước pattern không guard cùng kiểu.
- Dùng `when` để bổ sung điều kiện cho pattern và chỉ tham chiếu pattern variable sau khi đã bind.
- Xác định rõ selector có thể null hay không và xử lý bằng `case null` khi cần.
- Đảm bảo switch expression có đủ nhánh để exhaustive.
- Với switch statement có pattern label hoặc `case null`, bảo đảm enhanced switch statement cũng exhaustive theo Java 21.
- Dùng arrow labels để mỗi nhánh có phạm vi thực thi rõ ràng.
- Biên dịch với Java 21 mà không bật preview cho pattern switch và guard `when`.

Kết hợp constant case và pattern case giúp `switch` xử lý hiệu quả cả giá trị đặc biệt lẫn nhóm đối tượng theo kiểu. Khi sắp xếp nhãn theo mức độ cụ thể, thêm guard đúng chỗ và xử lý null tường minh, mã Java 21 dễ đọc, tránh nhánh unreachable và thể hiện rõ từng trường hợp nghiệp vụ.
