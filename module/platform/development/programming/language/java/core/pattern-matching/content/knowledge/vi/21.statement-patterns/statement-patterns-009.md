# Khi statement rõ hơn expression trong Java Pattern Matching

## 1. Mô hình tư duy: muốn **thực hiện công việc** hay muốn **tính ra giá trị**?

Trong Java, **statement** (câu lệnh) mô tả một hành động hoặc điều khiển luồng chạy; **expression** (biểu thức) là một cấu trúc có giá trị có thể gán, truyền cho hàm hoặc trả về. Với `switch`, Java hỗ trợ cả hai cách dùng:

```java
// Switch expression: tính ra một giá trị.
String label = switch (status) {
    case NEW -> "new";
    case DONE -> "done";
};

// Switch statement: thực hiện hành động.
switch (status) {
    case NEW -> System.out.println("Start work");
    case DONE -> System.out.println("Archive work");
}
```

Các đoạn này minh họa cú pháp, giả định `status` là kiểu enum chỉ có `NEW` và `DONE`. Cả hai đều có thể dùng nhánh `case` dạng mũi tên `->`; **dấu mũi tên không quyết định** đoạn code là statement hay expression. Vị trí sử dụng mới quyết định: sau dấu `=` là expression; một cấu trúc `switch` đứng riêng để thực thi là statement.

Khi kết hợp với **pattern matching** (mẫu kiểu, mẫu record, `when`), lựa chọn vẫn dựa vào mục đích:

- Nếu mỗi nhánh **tạo một giá trị** cùng ý nghĩa (nhãn, mã trạng thái, kết quả ánh xạ), `switch expression` thường biểu đạt rõ.
- Nếu mỗi nhánh **tiến hành một quy trình** gồm kiểm tra, gọi dịch vụ, ghi log, phát sự kiện hoặc dừng phương thức sớm, `switch statement` hay chuỗi `if` dùng pattern có thể dễ theo dõi hơn.
- Nếu các nhánh khác nhau không nhất thiết có cùng kiểu kết quả hoặc có bước cần bỏ qua, việc ép tất cả thành một biểu thức có thể khiến code phức tạp mà không thêm giá trị.

**Không có quy tắc tuyệt đối** rằng statement luôn tốt hơn khi có side effect. Switch expression vẫn cho phép khối lệnh và `yield`. Tiêu chí là cấu trúc nào làm ý định và các đường đi của chương trình rõ ràng nhất.

Trong Java 21, `switch` hỗ trợ pattern matching chính thức (JEP 441) và record patterns chính thức (JEP 440). Bài này dùng cú pháp Java 21+, không cần bật preview.

## 2. Khi cùng một nhánh phải làm nhiều việc, statement thường tự nhiên hơn

Hãy hình dung một hệ thống xử lý lệnh đặt hàng:

```text
Command
  ├── Register(id, customer)
  │     ├── kiểm tra khách hàng
  │     ├── lưu yêu cầu
  │     └── ghi nhật ký kiểm toán
  ├── Cancel(id, reason)
  │     ├── hủy yêu cầu
  │     └── ghi nhật ký
  └── Ship(id, address)
        ├── kiểm tra địa chỉ
        └── gửi yêu cầu vận chuyển
```

Mục tiêu của phương thức xử lý không phải tạo ra một nhãn chuỗi duy nhất; nó phải **thực thi quy trình** phù hợp với loại lệnh. Một `switch statement` với record patterns biểu diễn thẳng các bước:

```java
switch (command) {
    case Register(var id, var customer) -> {
        validateCustomer(customer);
        saveRegistration(id, customer);
        audit(id, "registered");
    }
    case Cancel(var id, var reason) -> {
        cancelRegistration(id, reason);
        audit(id, "cancelled");
    }
    case Ship(var id, var address) -> {
        validateAddress(address);
        submitShipment(id, address);
    }
}
```

Đây là đoạn minh họa kiến trúc: `validateCustomer`, `saveRegistration`, `audit`, `cancelRegistration`, `validateAddress` và `submitShipment` là các phương thức ứng dụng cần được định nghĩa; các record cũng cần khai báo. Từng nhánh mang ý nghĩa *thực thi lệnh*. Không cần tạo biến `result` hoặc đưa ra một giá trị giả chỉ để hoàn tất biểu thức.

Một cách viết ép thành expression có thể khiến mỗi nhánh trả về một chuỗi như `"done"`, `"cancelled"` hoặc `"shipped"` chỉ để người viết bỏ qua kết quả:

```java
// Minh họa thiết kế không phù hợp nếu trạng thái không được dùng.
String ignored = switch (command) {
    case Register(var id, var customer) -> "registered";
    case Cancel(var id, var reason) -> "cancelled";
    case Ship(var id, var address) -> "shipped";
};
```

Về mặt Java, đây là biểu thức hợp lệ với kiểu `Command` là sealed hierarchy đầy đủ như ví dụ chạy được bên dưới. Vấn đề là **hành vi nghiệp vụ đã bị thay bằng nhãn**; một giá trị không sử dụng không làm code rõ hơn. Nếu cần trả về trạng thái thực sự cho caller, expression có thể lại là lựa chọn tốt.

## 3. Pattern matching phục vụ cả statement lẫn expression

Giả sử mô hình:

```java
sealed interface Command permits Register, Cancel, Ship {}
record Register(String id, String customer) implements Command {}
record Cancel(String id, String reason) implements Command {}
record Ship(String id, String address) implements Command {}
```

Ta có thể dùng cùng record patterns trong cả hai cấu trúc.

**Statement — mỗi case là một hoạt động:**

```java
switch (command) {
    case Register(var id, var customer) -> System.out.println("save " + id);
    case Cancel(var id, var reason) -> System.out.println("cancel " + id);
    case Ship(var id, var address) -> System.out.println("ship " + id);
}
```

**Expression — mỗi case trả về một giá trị:**

```java
String label = switch (command) {
    case Register(var id, var customer) -> "register:" + id;
    case Cancel(var id, var reason) -> "cancel:" + id;
    case Ship(var id, var address) -> "ship:" + id;
};
```

Cả hai đều là Java 21 hợp lệ khi `command` có kiểu `Command` và các record được khai báo như trên. Cả hai đều áp dụng nguyên tắc so khớp theo **kiểu record** rồi phân rã thành phần theo thứ tự khai báo. Việc chọn statement hay expression **không thay đổi semantics của pattern**.

Với hệ thống có nhiều bước, statement giúp người đọc thấy trình tự và nhánh có thể dừng tại đâu. Với phép ánh xạ từ một giá trị sang một giá trị khác, expression giúp người đọc thấy rõ kết quả được tính từ mọi nhánh.

## 4. Ví dụ Java 21 hoàn chỉnh và kết quả kiểm chứng

Lưu toàn bộ chương trình vào file **`StatementVsExpressionDemo.java`**. Nó cho thấy cùng hierarchy `Command` có thể phục vụ xử lý lệnh bằng statement và tạo nhãn bằng expression; `instanceof` kết hợp `if` phù hợp cho các điều kiện kiểm tra độc lập.

```java
public class StatementVsExpressionDemo {
    sealed interface Command permits Register, Cancel, Ship {}

    record Register(String id, String customer) implements Command {}
    record Cancel(String id, String reason) implements Command {}
    record Ship(String id, String address) implements Command {}

    // Xử lý quy trình: mỗi nhánh có thể thực hiện nhiều bước hoặc kết thúc sớm.
    static void process(Command command) {
        switch (command) {
            case Register(var id, var customer) -> {
                System.out.println("validate register:" + id);

                if (customer == null || customer.isBlank()) {
                    System.out.println("reject:missing customer");
                    return;
                }

                System.out.println("store:" + id);
                System.out.println("audit:registered");
            }
            case Cancel(var id, var reason) -> {
                System.out.println("cancel:" + id);
                System.out.println("audit:cancelled");
            }
            case Ship(var id, var address) -> {
                if (address == null || address.isBlank()) {
                    System.out.println("reject:missing address");
                    return;
                }

                System.out.println("ship:" + id + "->" + address);
            }
        }
    }

    // Ánh xạ một command thành một chuỗi: expression có mục đích rõ.
    static String preview(Command command) {
        return switch (command) {
            case Register(var id, var customer) -> "register:" + id;
            case Cancel(var id, var reason) -> "cancel:" + id;
            case Ship(var id, var address) -> "ship:" + id;
        };
    }

    // Kiểm tra theo thứ tự: if + instanceof pattern có thể dễ đọc hơn.
    static String classify(Object input) {
        if (input instanceof String message) {
            if (message.isBlank()) {
                return "empty text";
            }
            return "text:" + message;
        }

        if (input instanceof Number number) {
            return "number:" + number;
        }

        return "other";
    }

    // Statement truyền thống: không bắt buộc bao phủ mọi số nguyên.
    static void traditional(int priority) {
        switch (priority) {
            case 1 -> System.out.println("urgent");
            case 2 -> System.out.println("normal");
        }
    }

    public static void main(String[] args) {
        process(new Register("O-1", "Lan"));
        process(new Register("O-2", ""));
        process(new Ship("O-3", "Hue"));
        process(new Cancel("O-4", "duplicate"));

        System.out.println(preview(new Ship("O-5", "Hanoi")));
        System.out.println(classify("hello"));
        System.out.println(classify("  "));

        traditional(3); // Không có case tương ứng nên không in thêm.
    }
}
```

Biên dịch và chạy với JDK 21 trở lên:

```bash
javac --release 21 -encoding UTF-8 StatementVsExpressionDemo.java
java StatementVsExpressionDemo
```

Đầu ra chính xác:

```text
validate register:O-1
store:O-1
audit:registered
validate register:O-2
reject:missing customer
ship:O-3->Hue
cancel:O-4
audit:cancelled
ship:O-5
text:hello
empty text
```

Chương trình dùng chuỗi ASCII trong phần output để tránh phụ thuộc cấu hình bảng mã của terminal. Các chú thích tiếng Việt được biên dịch với `-encoding UTF-8`.

### Đọc kết quả theo luồng thực thi

- `process(Register("O-1", "Lan"))` thực hiện ba thao tác: thông báo kiểm tra, lưu đơn, ghi audit. Các lời gọi `System.out.println` chỉ mô phỏng side effect; ứng dụng thực có thể thay bằng repository/service.
- `process(Register("O-2", ""))` in hai dòng rồi **`return` khỏi phương thức `process`**. Nhờ đó không có dòng `store` hay `audit` cho đơn bị từ chối. `return` ở trong khối case của statement có thể thoát trực tiếp khỏi phương thức.
- `process(Ship(...))` kiểm tra địa chỉ trước bước vận chuyển; các bước này không phải một phép tính giá trị cần `yield`.
- `preview` dùng switch expression vì hợp đồng của phương thức là **trả về một chuỗi mô tả**. Không có thao tác cần hủy bỏ giữa nhánh.
- `classify` dùng hai lần `instanceof` với mẫu kiểu `String` và `Number` vì mỗi trường hợp có quy tắc riêng và một chuỗi kiểm tra theo thứ tự. `null` không khớp với hai phép `instanceof` nên đi tới `"other"`.
- `traditional(3)` không in gì: đây là switch statement truyền thống trên `int`, không cần nhánh cho tất cả số nguyên.

## 5. Khi statement đặc biệt rõ: kiểm tra dữ liệu rồi thoát sớm

Hãy xem một nhánh xử lý lệnh có thể cần từ chối sớm:

```java
case Register(var id, var customer) -> {
    if (customer == null || customer.isBlank()) {
        reportValidationError(id);
        return;
    }

    saveRegistration(id, customer);
    notifySuccess(id);
}
```

Đây là **phần của một switch statement**, giả định phương thức bao quanh trả về `void` và `reportValidationError`, `saveRegistration`, `notifySuccess` được triển khai trong ứng dụng.

Cấu trúc này có lợi khi:

1. Điều kiện sai dẫn đến thông báo và **kết thúc phương thức** ngay, không cần gom mọi con đường vào một kết quả chung.
2. Điều kiện đúng tiếp tục với các side effects theo thứ tự, mỗi bước có tên thể hiện mục đích.
3. Mỗi thao tác có thể thất bại theo hợp đồng riêng; người đọc nhìn thấy nơi lỗi được xử lý hoặc ngoại lệ được chuyển ra.
4. Quy trình có các nhánh có số lượng bước không đồng đều; biểu thức trả về một nhãn chung không phản ánh đầy đủ hoạt động.

Nếu phương thức **phải tạo kết quả** sau khi kiểm tra, switch expression vẫn hoàn toàn phù hợp. Câu hỏi là “đầu ra cần dùng ở đâu?” và “đường điều khiển có nhiều lối thoát hay không?”. Không nên dựa vào độ dài của biểu thức để quyết định.

## 6. Khi `if` + pattern statement sáng sủa hơn một switch lớn

Pattern matching không bắt buộc dùng `switch`. Với `instanceof`, ta có thể đi theo một chuỗi điều kiện độc lập:

```java
static String classify(Object input) {
    if (input instanceof String text) {
        if (text.isBlank()) {
            return "empty text";
        }
        return "text:" + text;
    }

    if (input instanceof Number number) {
        return "number:" + number;
    }

    return "other";
}
```

Điểm đáng chú ý:

- Mỗi nhánh chứa một mẫu kiểu và có thể kiểm tra thêm **điều kiện riêng**.
- Biến `text` chỉ được dùng trong nhánh có thể chứng minh `input` khớp `String`; tương tự biến `number` cho `Number`.
- `return` kết thúc phương thức ở nhánh đã xử lý, nên phần cuối là trường hợp dự phòng.
- Không bắt buộc chứng minh một tập mẫu đóng ở thời điểm biên dịch; bạn đang chủ động viết chuỗi câu lệnh có lối ra dự phòng.

Mẫu `if` hữu ích khi việc xử lý là một chuỗi **guard clauses** (điều kiện gác) hoặc khi các nhánh được sắp theo mức ưu tiên nghiệp vụ. Nhưng nếu có một `sealed` hierarchy gồm nhiều trường hợp đóng và bạn muốn compiler kiểm tra xem có quên kiểu con hay không, `switch` với pattern thường thể hiện tốt hơn.

## 7. Không nhầm: switch expression cũng có khối lệnh và side effect

Đừng đưa ra quy tắc sai rằng “expression chỉ được viết một dòng” hoặc “không thể ghi log trong expression”. Java cho phép khối `case` với `yield`:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> {
            System.out.println("trace:string");
            yield text.isBlank() ? "empty" : text.toUpperCase();
        }
        case null -> "missing";
        default -> "other";
    };
}
```

Ví dụ:

```java
System.out.println(describe("hello"));
System.out.println(describe(null));
```

Kết quả:

```text
trace:string
HELLO
missing
```

Cú pháp trên là Java 21 hợp lệ (giả sử phương thức đã được đặt vào một lớp và có lời gọi `main` phù hợp). `yield` **trả giá trị từ nhánh của switch expression**, còn `return` của `return switch (...)` ở bên ngoài trả kết quả từ phương thức.

Với expression, mỗi nhánh phải dẫn đến một giá trị hoặc kết thúc bất thường (ví dụ ném ngoại lệ). Không nên cố “chế ra” một giá trị giả chỉ để biểu thức hợp lệ khi mục tiêu duy nhất là thực thi lệnh. Nếu một nhánh chủ yếu là chuỗi hành động và `yield` chỉ để đưa ra một hằng ít ý nghĩa, statement thường diễn đạt đúng ý đồ hơn.

## 8. Những quy tắc kiểm soát luồng cần phân biệt

| Cấu trúc | Mục đích | Điểm cần nhớ |
| --- | --- | --- |
| `switch statement` | Thực thi thao tác | Nhánh `case ... -> { ... }` chứa nhiều statement và có thể `return` khỏi phương thức |
| `switch expression` | Tính một giá trị | Nhánh block dùng `yield value;` khi cần chuyển giá trị ra ngoài |
| `if (...)` và pattern `instanceof` | Điều kiện kiểm tra tuần tự | Có thể thoát sớm bằng `return`, `throw` hoặc tiếp tục xử lý |
| `break;` trong statement | Thoát khỏi switch/vòng lặp bao quanh phù hợp | Không phải cách xuất một giá trị từ switch expression |
| `throw` | Kết thúc bất thường | Có thể được dùng khi bất kỳ dạng rẽ nhánh nào gặp lỗi không thể tiếp tục |

Với `case ... ->` (cả statement và expression), **không có fall-through** từ nhánh này sang nhánh sau. Khác với `case:` truyền thống có thể chạy xuyên nếu thiếu `break`, dạng mũi tên giúp các nhánh có hành vi riêng rõ hơn.

Trong switch statement dùng `case ... -> { ... }`, người viết có thể đặt nhiều câu lệnh trong block, gọi phương thức, thay đổi trạng thái hoặc `return` sớm. Với switch expression dùng `case ... -> { ... }`, khối cần kết thúc bằng `yield` trên con đường hoàn tất bình thường (hoặc ném ngoại lệ trên đường đó).

**Không đổi `yield` thành `return` tùy tiện:** `yield` xuất giá trị của switch expression; `return` xuất khỏi phương thức đang bao quanh trong những ngữ cảnh cho phép. Phương thức `void` có thể `return;` để dừng, còn `return switch (...)` dành cho phương thức có kiểu kết quả tương thích.

## 9. Quy tắc exhaustiveness: statement truyền thống và statement có pattern khác nhau

Một hiểu lầm nguy hiểm là “switch statement không cần đủ case”. Điều này chỉ đúng với **switch statement truyền thống** trong phạm vi được Java giữ lại để tương thích ngược.

### 9.1. Switch statement truyền thống có thể thiếu case

```java
static void printPriority(int priority) {
    switch (priority) {
        case 1 -> System.out.println("urgent");
        case 2 -> System.out.println("normal");
        // priority == 3: không có nhánh; phương thức vẫn chạy tiếp.
    }
}
```

Đây là switch statement trên `int` dùng các nhãn hằng; Java cho phép thiếu `default`. Nếu giá trị bằng `3`, không có câu lệnh nào được thực thi trong switch. Hãy thêm `default` nếu một giá trị chưa biết cần được ghi nhận hoặc từ chối.

### 9.2. Enhanced switch statement với pattern phải exhaustive

Đoạn sau **cố ý không biên dịch** trên Java 21:

```java
static void inspect(Object input) {
    switch (input) {
        case String text -> System.out.println(text);
        case Number number -> System.out.println(number);
        // Không có default hoặc mẫu bao phủ các loại còn lại.
    }
}
```

Lỗi tiêu biểu:

```text
the switch statement does not cover all possible input values
```

Vì `Object` còn bao gồm nhiều kiểu khác, statement có pattern ở trên không exhaustive. Một bản sửa:

```java
static void inspect(Object input) {
    switch (input) {
        case String text -> System.out.println(text);
        case Number number -> System.out.println(number);
        case null -> System.out.println("null");
        default -> System.out.println("other");
    }
}
```

Trong Java 21, enhanced switch statement có quy tắc exhaustiveness tương tự switch expression. Bằng chứng từ kiểu selector cũng áp dụng với `enum` và `sealed`, ví dụ các record `Register`, `Cancel`, `Ship` thuộc `Command` trong chương trình đầy đủ.

### 9.3. Một nhánh có `when` chưa chắc bao phủ cả kiểu

```java
switch (command) {
    case Ship(var id, var address)
            when address != null && !address.isBlank() -> {
        submitShipment(id, address);
    }
    case Ship(var id, var address) -> {
        reportInvalidAddress(id);
    }
    case Register(var id, var customer) -> {
        saveRegistration(id, customer);
    }
    case Cancel(var id, var reason) -> {
        cancelRegistration(id, reason);
    }
}
```

Đây là **đoạn minh họa**, giả định các phương thức ứng dụng đã được khai báo. Nhánh `Ship` có guard xử lý địa chỉ hợp lệ; vẫn cần nhánh `Ship` khác cho địa chỉ thiếu hoặc rỗng. Nếu chỉ viết `case Ship(...) when ...` rồi quên đường guard thất bại, switch có thể không exhaustive.

Thứ tự nhánh cũng quan trọng: đặt mẫu `Ship(...)` không guard **trước** mẫu `Ship(...) when ...` có thể làm nhánh hẹp bị che phủ (*dominated case*) và gây lỗi biên dịch. Với sealed hierarchy, liệt kê hết các kiểu con có thể giúp compiler nhắc cập nhật code khi thêm loại lệnh mới.

## 10. Xử lý `null`, lỗi nghiệp vụ và ngoại lệ

Cả statement lẫn expression đều cần hợp đồng dữ liệu rõ ràng.

- Với `if (obj instanceof Type t)`, đầu vào `obj == null` làm phép `instanceof` trả `false`, không ném NPE vì riêng phép kiểm tra ấy.
- Với `switch (reference)` trên kiểu tham chiếu, nếu selector là `null` và không có `case null` phù hợp, switch thông thường ném `NullPointerException`, **kể cả khi các nhánh kiểu còn lại đã exhaustive**.
- Khi record pattern lồng nhau gặp một thành phần record con bằng `null`, mẫu con không khớp; riêng `var child` có thể ràng buộc một thành phần tham chiếu bằng `null`. Pattern khớp không chứng minh dữ liệu hợp lệ.

Có thể chọn xử lý `null` ngay bằng statement:

```java
switch (command) {
    case null -> System.out.println("reject:null command");
    case Register(var id, var customer) -> System.out.println("register " + id);
    case Cancel(var id, var reason) -> System.out.println("cancel " + id);
    case Ship(var id, var address) -> System.out.println("ship " + id);
}
```

Hoặc từ chối ở đầu phương thức:

```java
java.util.Objects.requireNonNull(command, "command");
// Sau đó dùng switch với các mẫu phù hợp.
```

Đây là **các đoạn minh họa** dùng kiểu `Command` như mục 4. Hãy chọn một hành vi nhất quán: từ chối `null` bằng exception hoặc xử lý bằng một nhánh có nghĩa, tùy hợp đồng API.

**Ngoại lệ không làm statement mặc nhiên tốt hơn.** Một switch expression có thể dùng `throw new IllegalArgumentException(...)` ở nhánh bất hợp lệ. Statement thường rõ hơn khi phải thực hiện nhiều bước khôi phục, ghi log, điều hướng và kết thúc sớm; expression thường rõ hơn khi muốn quy mọi đường đi thành một **kết quả hoặc một lỗi**.

## 11. Lỗi thiết kế phổ biến và hướng sửa

### 11.1. Tạo giá trị giả chỉ để dùng switch expression

Dạng khó đọc:

```java
// Minh họa ý tưởng, không phải chương trình độc lập.
String unused = switch (command) {
    case Register(var id, var customer) -> {
        saveRegistration(id, customer);
        yield "ok";
    }
    case Cancel(var id, var reason) -> {
        cancelRegistration(id, reason);
        yield "ok";
    }
    case Ship(var id, var address) -> {
        submitShipment(id, address);
        yield "ok";
    }
};
```

Nếu `unused` không bao giờ được đọc, có thể chuyển sang switch statement và bỏ `yield "ok"`. Ngược lại, nếu cần đối tượng `OperationResult` thể hiện kết quả từng nhánh (thành công/thất bại, mã lỗi, dữ liệu phản hồi), hãy giữ expression và trả một **giá trị có ý nghĩa**.

### 11.2. Nhiều bước có thứ tự bị giấu trong một biểu thức

Lồng nhiều lời gọi có side effect trong toán tử `?:` hoặc nối chuỗi có thể làm thứ tự xử lý khó theo dõi. Một block statement giúp xác định rõ khi nào kiểm tra hợp lệ, khi nào ghi dữ liệu, khi nào phát thông báo và khi nào dừng.

### 11.3. Nhầm dấu `->` với switch expression

`switch (x) { case A -> doWork(); }` là statement khi đứng riêng. `return switch (x) { case A -> "a"; ... };` là expression được dùng trong `return`. Đừng quyết định loại cấu trúc chỉ dựa vào dấu mũi tên.

### 11.4. Bỏ qua tính exhaustiveness của enhanced statement

Statement có type/record patterns phải có các nhánh bao phủ toàn bộ selector. Nếu gặp lỗi thiếu case, xem xét `sealed` hierarchy, các guard `when` và kiểu selector mở. Đừng bỏ mặc lỗi với suy nghĩ “statement thì thiếu case cũng được”.

### 11.5. Dùng `default` làm mất cảnh báo hữu ích

Với hierarchy `sealed` có tập kiểu con đã biết, việc liệt kê đầy đủ `Register`, `Cancel`, `Ship` giúp compiler báo khi thêm kiểu mới cần xử lý. Thêm `default` một cách máy móc có thể làm mất cơ hội phát hiện thay đổi nghiệp vụ. Với selector kiểu mở như `Object`, `default` thường hợp lý.

### 11.6. Viết nhánh quá dài và trộn nhiều trách nhiệm

Statement phù hợp với quy trình nhiều bước nhưng **không phải giấy phép cho method dài hàng trăm dòng**. Khi một nhánh xử lý đăng ký cần xác thực, truy vấn, ghi CSDL, gọi dịch vụ và gửi thông báo, nên tách thành phương thức/service có tên rõ: `handleRegister`, `handleCancel`, `handleShip`. Switch statement chỉ nên điều phối đúng hướng.

### 11.7. Dùng statement với biến kết quả thay vì expression đơn giản

Nếu mục đích duy nhất là tạo nhãn, cách sau dễ phát sinh lỗi khởi tạo biến:

```java
String label;
switch (stage) {
    case NEW -> label = "new";
    case DONE -> label = "done";
}
```

Biến `label` có thể chưa được gán nếu `stage` có trạng thái khác. Với enum đúng hai trạng thái `NEW` và `DONE`, compiler vẫn không mặc nhiên coi một statement truyền thống thiếu `default` như phép gán chắc chắn trên mọi đường đi. Khi mục tiêu là ánh xạ giá trị, switch expression thường tránh phải quản lý một biến kết quả có thể chưa được gán.

## 12. Bảng chọn cách viết theo mục tiêu

| Mục tiêu chính | Cách thường dễ đọc hơn | Vì sao |
| --- | --- | --- |
| Biến `Stage` thành chuỗi giao diện | `switch expression` | Mỗi nhánh sinh một giá trị, phù hợp `return` hoặc phép gán |
| Nhận `Command` và chạy quy trình thao tác | `switch statement` với record pattern | Mỗi nhánh là một chuỗi hành động rõ thứ tự |
| Kiểm tra hợp lệ và `return` sớm khi lỗi | `if` hoặc `switch statement` | Thể hiện rõ đường thoát khỏi phương thức |
| Trả về đối tượng kết quả cho từng loại command | `switch expression` | Giá trị kết quả có ý nghĩa và được caller sử dụng |
| Phân biệt tất cả kiểu con của sealed hierarchy | Switch có đủ type/record patterns | Trình biên dịch giúp phát hiện thiếu nhánh |
| Kiểm tra một vài điều kiện độc lập, có dự phòng | `if` + `instanceof` patterns | Dễ trình bày thứ tự ưu tiên và các guard riêng |
| Ghi log rồi trả một giá trị đơn giản | Tùy mức phức tạp; expression với `yield` vẫn hợp lệ | Không cần đổi sang statement chỉ vì có một dòng log |
| Điều phối nhiều hàm/service, có thao tác khôi phục | Statement hoặc phương thức chuyên trách | Quy trình là đối tượng chính cần hiểu |
| Xử lý giá trị `null` chủ động | `case null` hoặc kiểm tra đầu vào | Exhaustiveness về kiểu không tự định nghĩa hành vi với null |

Một câu hỏi thực dụng trước khi viết: **“Tôi đang xây một phép ánh xạ từ giá trị sang giá trị, hay đang mô tả cách chương trình làm việc?”** Nếu là phép ánh xạ, nghĩ đến expression; nếu là quy trình, bắt đầu từ statement. Sau đó xét exhaustiveness, xử lý null, khả năng mở rộng và cách kiểm thử.

## 13. Bài tập và đáp án

**Bài 1 — Chọn dạng switch.** Một phương thức nhận `Command`, phải kiểm tra thông tin, cập nhật đơn hàng rồi gửi sự kiện; phương thức trả về `void`. Dạng nào dễ hiểu hơn?

Đáp án: `switch statement` với pattern theo từng kiểu lệnh. Có thể tách mỗi case ra handler nếu quy trình dài; không cần tạo một giá trị chỉ để đạt cú pháp expression.

**Bài 2 — Mục tiêu khác.** Một phương thức nhận `Command` và trả tên hiển thị của lệnh. Dạng nào dễ hiểu hơn?

Đáp án: `switch expression` trả về `String`. Các nhánh cùng tạo một giá trị, trình biên dịch kiểm tra thiếu case trong sealed hierarchy.

**Bài 3 — Truy cập null.** Nếu gọi `process(null)` ở ví dụ mục 4, điều gì xảy ra?

Đáp án: switch statement dùng pattern trên `Command` không có `case null`, nên ném `NullPointerException`. Muốn xử lý `null`, bổ sung `case null` hoặc kiểm tra trước khi vào switch.

**Bài 4 — Statement dùng pattern có thiếu case được không?** Cho `Object input` và switch chỉ có `case String s`, `case Number n`. Kết quả biên dịch?

Đáp án: lỗi thiếu bao phủ (`the switch statement does not cover all possible input values`) vì đây là enhanced switch statement với pattern trên kiểu `Object`. Có thể thêm `default` hoặc mẫu tổng quát phù hợp.

**Bài 5 — Khi `when` thất bại.** Một case `Ship(var id, var address) when address != null` có xử lý mọi `Ship` không?

Đáp án: không. Với `address == null`, guard sai nên case không khớp. Nếu cần exhaustive trên sealed `Command`, bổ sung nhánh `Ship` không guard, và đặt nó sau nhánh có guard.

**Bài 6 — `yield` hay `return`?** Trong switch expression có khối `case String s -> { ... }`, muốn cho biểu thức trả chuỗi `s.toUpperCase()` thì dùng gì?

Đáp án: `yield s.toUpperCase();`. Trong `return switch (...)`, `return` ở ngoài biểu thức đưa giá trị ấy ra khỏi phương thức. Với switch statement trong phương thức `void`, `return;` trong case block có thể dừng cả phương thức.

**Bài 7 — Kiểm tra output.** Trong ví dụ hoàn chỉnh, tại sao không có dòng `store:O-2`?

Đáp án: `customer` là chuỗi rỗng, nên case `Register` in `reject:missing customer` và `return` khỏi `process` trước bước lưu. Nếu một thiết kế cần ghi audit cả trường hợp từ chối, phải chủ động đưa thao tác audit vào đường từ chối trước `return` hoặc có cơ chế xử lý chung phù hợp.

## 14. Ghi nhớ

- **Statement** mô tả việc phải làm, thường rõ khi có nhiều bước, side effects và kết thúc sớm.
- **Expression** biểu diễn giá trị cần tính, thường rõ khi các case là những phép ánh xạ cùng mục đích.
- Pattern matching (`instanceof`, type patterns, record patterns, `when`) có thể xuất hiện trong cả statement và expression; ngữ nghĩa kiểm tra kiểu không đổi vì cách chọn dạng switch.
- Dấu `->` xuất hiện ở cả hai dạng. Trong expression, khối nhiều câu lệnh dùng `yield` để xuất giá trị; statement có thể dùng `return` để dừng phương thức.
- **Enhanced switch statement** dùng pattern phải exhaustive; chỉ statement truyền thống mới có ngoại lệ tương thích ngược cho việc không bao phủ hết các giá trị.
- `null`, dữ liệu thiếu và những trường hợp guard không khớp cần được xử lý theo hợp đồng API, không nên đánh đồng với việc compiler đã chứng minh exhaustive.
- Chọn cấu trúc giúp đọc hiểu trách nhiệm của phương thức; các nhánh quá dài nên tách thành handler thay vì tranh luận statement hay expression.

**Tham khảo chính thức:** [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Java Language Specification 21 — switch statements (`14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11), [Java Language Specification 21 — switch expressions (`15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
