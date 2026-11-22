# Xử lý exception trong case body

**Chủ đề:** Java Core Pattern Matching — Exception và null. Bài dùng **Java 21 trở lên**, phiên bản mà **record patterns (JEP 440)** và **pattern matching for switch (JEP 441)** đã là tính năng chính thức. Cách dùng **switch expression** và **yield** đã ổn định từ Java 14; các ví dụ kết hợp record pattern với switch trong bài cần Java 21+.

## 1. Exception có thể xảy ra ở đâu trong một switch?

**Case body** là phần lệnh hoặc biểu thức được thực thi **sau khi một case được chọn**. Khi dùng pattern matching, việc xử lý một giá trị qua switch thường có các giai đoạn:

1. Đánh giá biểu thức **selector** bên trong dấu ngoặc của switch.
2. Thử các nhãn **case** theo quy tắc matching, gồm type/record pattern và điều kiện guard **when** nếu có.
3. Chọn case phù hợp và thực thi **case body**.
4. Nếu là **switch expression**, cung cấp kết quả bằng biểu thức sau mũi tên hoặc bằng **yield** từ block; nếu có ngoại lệ thì việc đánh giá kết thúc bất thường.

Ví dụ:

~~~java
return switch (request) {
    case Register(String username, int age) -> {
        if (age < 18) {
            throw new IllegalArgumentException("underage");
        }
        yield "accepted: " + username;
    }
    case Cancel(var ticket) -> "cancelled: " + ticket;
    case Ping() -> "pong";
    case null -> throw new IllegalArgumentException("request");
};
~~~

Đây là **đoạn minh họa** dựa trên các record và interface được khai báo đầy đủ ở mục 5, không phải một chương trình độc lập.

Cách đọc: nếu request khớp Register, chương trình đi vào block của case. Khi age nhỏ hơn 18, **throw** làm switch kết thúc bằng ngoại lệ. Ngược lại, **yield** đưa một String ra làm kết quả của switch expression. Không có yêu cầu mọi nhánh phải trả về giá trị trên mọi đường đi: **một nhánh có thể luôn ném ngoại lệ**.

**Phân biệt quan trọng:** ngoại lệ được tạo ra trong **selector**, trong quá trình đánh giá **pattern/guard**, và trong **case body** không xảy ra tại cùng thời điểm. Một khối try/catch đặt *bên trong* case body chỉ bắt ngoại lệ được ném khi khối try ấy thực sự chạy.

## 2. Ba dạng case body và quan hệ với exception

Một nhánh mũi tên (**case ... ->**) trong switch expression có thể dùng một biểu thức, một block hoặc một câu lệnh **throw**. Cả ba hình thức đều hữu ích.

### 2.1. Nhánh trả kết quả trực tiếp

~~~java
case Ping() -> "PONG";
~~~

Nhánh này trả String bằng chính biểu thức sau mũi tên. Nếu biểu thức có lời gọi phương thức và lời gọi đó ném ngoại lệ, ngoại lệ lan ra ngoài switch nếu không được bắt ở phạm vi phù hợp:

~~~java
// Minh họa: format(request) là phương thức do ứng dụng định nghĩa.
case Ping() -> format(request);
~~~

**Switch expression không tự nuốt exception.** Nó chỉ tạo ra giá trị khi nhánh kết thúc bình thường.

### 2.2. Nhánh block có nhiều lệnh và yield

~~~java
case Register(String username, int age) -> {
    if (age < 18) {
        yield "REJECTED: underage";
    }
    yield "REGISTERED: " + username;
}
~~~

Block có thể chứa if, vòng lặp, try/catch và các lệnh nghiệp vụ hợp lệ khác. **yield** truyền một giá trị cho toàn bộ switch expression; nó khác với **return** của phương thức chứa switch.

**Không dùng break để trả giá trị của switch expression.** Với dạng block trong switch expression, sử dụng **yield** hoặc cho phép đường đi kết thúc bất thường bằng **throw**. Một block có đường đi bình thường kết thúc mà không cung cấp giá trị sẽ không biên dịch như một nhánh hợp lệ của switch expression.

### 2.3. Nhánh cố ý ném ngoại lệ

~~~java
case null -> throw new IllegalArgumentException("request");
~~~

Nhánh này xác định rõ hợp đồng: request null là dữ liệu không được chấp nhận. Không có giá trị String được tạo ra. Một câu lệnh throw như vậy **được phép** trong nhánh mũi tên của switch expression mà không cần yield.

Với một block chứa cả kiểm tra và kết quả:

~~~java
case Cancel(String ticket) -> {
    if (ticket == null || ticket.isBlank()) {
        throw new IllegalArgumentException("ticket");
    }
    yield "CANCELLED: " + ticket;
}
~~~

Đường đi lỗi ném exception; đường đi hợp lệ yield kết quả. Hai hành vi này không xung đột.

## 3. Dùng try/catch bên trong một case body

Nhiều tác vụ trong một nhánh có khả năng thất bại có thể **phục hồi được**: phân tích dữ liệu, xác thực một thuộc tính hoặc gọi một dịch vụ. Trong những trường hợp này, bắt một loại ngoại lệ cụ thể ngay tại nhánh có thể giúp tạo kết quả nghiệp vụ rõ ràng.

Ví dụ:

~~~java
case Register(String username, int age) -> {
    try {
        String name = normalizedUser(username);
        if (age < 18) {
            yield "REJECTED: underage";
        }
        yield "REGISTERED: " + name;
    } catch (ValidationException ex) {
        yield "REJECTED: " + ex.getMessage();
    }
}
~~~

Ở đây:

- **normalizedUser** có thể ném **ValidationException**, một checked exception do ứng dụng định nghĩa.
- **try** chứa lời gọi có khả năng thất bại.
- **catch (ValidationException ex)** xử lý **chính xác nhóm lỗi có thể phục hồi** của nhánh này.
- Cả đường đi hợp lệ lẫn đường đi đã bắt lỗi đều **yield một String** cho switch expression.
- Những ngoại lệ khác không bị catch này bắt, nên vẫn có thể truyền lên caller.

**Không cần bắt mọi RuntimeException hoặc Exception** chỉ để case có vẻ “an toàn”. Làm vậy có thể che lỗi lập trình như NullPointerException ngoài ý muốn, lỗi tài nguyên hoặc bug trong phụ thuộc. Chỉ chuyển ngoại lệ thành kết quả thông thường khi đó là một quy tắc được xác định rõ.

### Khi nào nên catch tại case?

Catch trong case thường hợp lý nếu lỗi **thuộc riêng subtype này** và consumer có cách xử lý cụ thể. Ví dụ lỗi định dạng tên của Register có thể trở thành **REJECTED: username**, nhưng lỗi lưu dữ liệu của toàn bộ hệ thống có thể cần đi qua một tầng xử lý lỗi cao hơn.

Nếu có nhiều case cùng dùng một chính sách lỗi, việc copy cùng một try/catch vào từng case sẽ gây lặp. Có thể chuyển sang một phương thức riêng hoặc một **try/catch bao quanh toàn bộ switch** tùy ranh giới trách nhiệm.

## 4. Checked exception: catch hoặc khai báo throws

Java kiểm tra **checked exceptions** ở compile time. Khi case body gọi một phương thức khai báo **throws ValidationException** (kế thừa Exception, không phải RuntimeException), mã chứa lời gọi phải:

- Bắt ValidationException bằng catch phù hợp; **hoặc**
- Khai báo throws ValidationException (hoặc kiểu cha thích hợp) ở phương thức chứa switch.

Ví dụ phần 3 dùng cách bắt ngay trong case. Một phương thức khác có thể chọn để lỗi lan lên caller:

~~~java
// Đoạn trích minh họa: dùng Request, Register, Cancel, Ping và
// normalizedUser, ValidationException của chương trình mục 5.
static String handleStrict(Request request) throws ValidationException {
    return switch (request) {
        case Register(var username, var age) -> normalizedUser(username);
        case Cancel(var ticket) -> "CANCEL:" + ticket;
        case Ping() -> "PONG";
        case null -> throw new IllegalArgumentException("request");
    };
}
~~~

Điểm khác biệt: handleStrict **không catch** ValidationException trong case Register. Phương thức khai báo **throws ValidationException** để caller quyết định xử lý. Switch expression vẫn exhaustive theo ba subtype Request; việc có một checked exception **không thay đổi yêu cầu exhaustiveness**.

Với **unchecked exception** như IllegalArgumentException hoặc NullPointerException, Java không bắt buộc khai báo throws. Tuy nhiên, việc có được phép để lỗi lan lên caller hay không vẫn là quyết định về hợp đồng của API.

Bảng lựa chọn:

| Loại tình huống | Xử lý thường hợp lý | Điều cần giữ rõ |
| --- | --- | --- |
| Dữ liệu Register không đạt validation đã định nghĩa | Catch lỗi xác thực cụ thể và yield kết quả từ chối | Không biến lỗi hệ thống thành lỗi người dùng |
| Lệnh Cancel thiếu mã bắt buộc | Throw IllegalArgumentException hoặc tạo domain error theo hợp đồng | Không trả “success” giả |
| Lỗi I/O hoặc timeout cần retry | Để tầng orchestrator xử lý, hoặc chuyển thành kết quả có kiểu riêng | Không nuốt mất nguyên nhân |
| Lỗi bất ngờ do bug | Để lan ra cơ chế báo lỗi/quan sát phù hợp | Không catch rộng và bỏ qua |
| Caller cần quản lý transaction | Để ngoại lệ hoặc kết quả lỗi đi qua ranh giới transaction | Không vô tình commit khi tác vụ thất bại |

## 5. Chương trình Java 21 hoàn chỉnh

Chương trình sau minh họa **sealed hierarchy**, **record pattern**, **try/catch trong case body**, **yield**, **throw**, null và cách caller bắt unchecked exception. Lưu toàn bộ vào tệp **CaseBodyExceptionDemo.java**.

~~~java
public class CaseBodyExceptionDemo {
    sealed interface Request permits Register, Cancel, Ping {}

    record Register(String username, int age) implements Request {}
    record Cancel(String ticket) implements Request {}
    record Ping() implements Request {}

    static final class ValidationException extends Exception {
        ValidationException(String message) {
            super(message);
        }
    }

    static String normalizedUser(String username) throws ValidationException {
        if (username == null || username.isBlank()) {
            throw new ValidationException("username");
        }
        return username.trim();
    }

    static String handle(Request request) {
        return switch (request) {
            case Register(String username, int age) -> {
                try {
                    String name = normalizedUser(username);
                    if (age < 18) {
                        yield "REJECTED: underage";
                    }
                    yield "REGISTERED: " + name;
                } catch (ValidationException ex) {
                    yield "REJECTED: " + ex.getMessage();
                }
            }
            case Cancel(String ticket) -> {
                if (ticket == null || ticket.isBlank()) {
                    throw new IllegalArgumentException("ticket");
                }
                yield "CANCELLED: " + ticket;
            }
            case Ping() -> "PONG";
            case null -> throw new IllegalArgumentException("request");
        };
    }

    static void show(Request request) {
        try {
            System.out.println(handle(request));
        } catch (IllegalArgumentException ex) {
            System.out.println("ERROR: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        show(new Register(" Lan ", 20));
        show(new Register("   ", 20));
        show(new Register("Minh", 16));
        show(new Cancel("T-01"));
        show(new Cancel(null));
        show(new Ping());
        show(null);
        show(new Register(null, 20));
    }
}
~~~

Biên dịch và chạy với **JDK 21+**:

~~~bash
javac CaseBodyExceptionDemo.java
java CaseBodyExceptionDemo
~~~

Kết quả chính xác:

~~~text
REGISTERED: Lan
REJECTED: username
REJECTED: underage
CANCELLED: T-01
ERROR: ticket
PONG
ERROR: request
REJECTED: username
~~~

**Giải thích các đường thực thi:**

1. **Register(" Lan ", 20):** record pattern ràng buộc username và age; normalizedUser trim khoảng trắng; nhánh yield **REGISTERED: Lan**.
2. **Register("   ", 20):** normalizedUser ném checked ValidationException; catch bên trong case chuyển lỗi xác thực thành **REJECTED: username**.
3. **Register("Minh", 16):** validation username thành công, điều kiện age < 18 làm case **yield REJECTED: underage**, không có exception.
4. **Cancel("T-01"):** dữ liệu hợp lệ, block **yield CANCELLED: T-01**.
5. **Cancel(null):** kiểm tra trong case body ném **IllegalArgumentException("ticket")**; show bắt và in **ERROR: ticket**.
6. **Ping():** case body là một biểu thức String trực tiếp, trả **PONG**.
7. **request == null:** switch chọn **case null**, trực tiếp ném IllegalArgumentException("request"); show in **ERROR: request**.
8. **Register(null, 20):** pattern Register vẫn khớp record nhưng component username null. Lỗi validation phát sinh từ normalizedUser, được catch và chuyển thành **REJECTED: username**.

Kết quả trên phân biệt rõ **từ chối có kiểm soát** (yield) và **ngoại lệ lan lên caller** (throw). Các case không có default vì Request là sealed interface, cả ba kiểu con Register, Cancel, Ping đều có nhánh bao phủ. Case null xử lý riêng selector null; nếu bỏ, việc đầy đủ theo subtype không đảm bảo xử lý null như mong muốn.

## 6. Lỗi phát sinh trước case body: catch bên trong case không bắt được

Một nguyên nhân thường gây hiểu nhầm là tưởng chỉ cần đặt catch trong block của case thì mọi lỗi “liên quan đến case” sẽ được bắt. Thực tế phải xét **thời điểm lỗi xuất hiện**.

### 6.1. Biểu thức selector có thể ném lỗi

~~~java
// Minh họa: loadRequest() có thể ném IOException.
String answer = switch (loadRequest()) {
    case Ping() -> "pong";
    case Register(var name, var age) -> "register";
    case Cancel(var ticket) -> "cancel";
    case null -> "null";
};
~~~

Nếu **loadRequest()** ném IOException khi tạo selector, **không có case nào được chọn**. Catch nằm *bên trong case Register* sẽ không có cơ hội chạy. Nếu muốn quản lý lỗi truy xuất, hãy bắt quanh lời gọi tạo selector hoặc quanh toàn bộ switch, và khai báo/bắt IOException theo quy tắc checked exceptions.

Đây là **mã minh họa không độc lập**; trong dự án thật phải khai báo phương thức loadRequest và import IOException nếu dùng.

### 6.2. Guard when chạy trước body

~~~java
// Minh họa: isAllowed(name) có thể ném RuntimeException.
case Register(var name, var age) when isAllowed(name) ->
        "allowed";
~~~

Nếu pattern Register khớp nhưng **isAllowed(name)** ném exception trong quá trình đánh giá guard, case body **"allowed"** chưa chạy. Một catch đặt trong body của case đó không thể xử lý lỗi đến từ guard. Khi guard chỉ là một điều kiện đơn giản, cách viết thường dễ hiểu; với quy tắc phức tạp có nguy cơ lỗi hoặc side effect, cân nhắc chuyển kiểm tra vào block có try/catch để quản lý rõ ràng.

Guard **false** chỉ có nghĩa case đó không được chọn; chương trình thử nhánh phù hợp tiếp theo. Guard **ném lỗi** là hoàn toàn khác: switch kết thúc bất thường, không tự chuyển qua case sau như thể guard trả false.

### 6.3. Giải cấu trúc record có thể gọi accessor

Record pattern lấy component bằng accessor. Nếu một record ghi đè accessor và accessor đó ném exception khi pattern được thử, lỗi phát sinh **trong quá trình matching**, không phải trong body của case.

Theo hành vi của record pattern Java 21, khi accessor kết thúc bất thường do throwable, quá trình matching có thể ném **MatchException** với throwable gốc làm **cause**. Điều này đặc biệt quan trọng nếu người viết code ghi đè accessor với logic có side effect: catch bên trong một case mà matching chưa hoàn tất sẽ không bắt được lỗi ấy.

Với record giá trị thông thường, hãy giữ accessor đơn giản, nhất quán và không có side effect khi có thể. Nếu caller cần xử lý lỗi từ matching, đặt ranh giới catch **bao quanh switch** và phân loại exception dựa trên hợp đồng, không giả định mọi lỗi đều bắt được tại nhánh.

### 6.4. Null selector so với component null

- **Selector null:** case null có thể xử lý; nếu không có cách xử lý null phù hợp, switch trên reference null có thể ném NullPointerException.
- **Component null:** một record như Register(null, 20) vẫn có thể khớp pattern Register(var username, var age); biến username có thể là null. Code trong body phải tự kiểm tra trước khi gọi phương thức.
- **Record pattern lồng:** nếu mẫu con yêu cầu một record cụ thể, chẳng hạn Outer(Inner(...)), một component con null không khớp mẫu lồng đó; nhánh dự phòng có thể cần thiết để bảo đảm exhaustiveness.

Không nhầm **case null** với kiểm tra mọi field null trong một record.

## 7. Nên bắt exception bên trong case hay ngoài switch?

Hai cách có mục tiêu khác nhau.

**Catch bên trong case** khi lỗi và cách xử lý lỗi thuộc riêng nhánh đó:

~~~java
case Register(var username, var age) -> {
    try {
        yield normalizedUser(username);
    } catch (ValidationException ex) {
        yield "REJECTED: " + ex.getMessage();
    }
}
~~~

**Catch bao quanh switch** khi cần một chính sách lỗi chung hoặc có lỗi có thể xảy ra từ selector/guard/matching:

~~~java
// Đoạn minh họa, Request và handle được khai báo ở mục 5.
static String handleSafely(Request request) {
    try {
        return handle(request);
    } catch (IllegalArgumentException ex) {
        return "ERROR: " + ex.getMessage();
    }
}
~~~

Ví dụ handleSafely chỉ bắt **IllegalArgumentException**, không bắt mọi loại exception. Phần xử lý ở boundary có thể thay đổi tùy ứng dụng: API có thể ánh xạ thành HTTP status, CLI có thể in thông báo, job processor có thể retry hoặc đưa thông điệp vào dead-letter queue.

### Đừng biến mọi lỗi thành một kết quả thành công

Một anti-pattern nguy hiểm:

~~~java
// Không nên áp dụng mù quáng: mất nguyên nhân lỗi.
try {
    return handle(request);
} catch (Exception ex) {
    return "OK";
}
~~~

Nếu caller hiểu **OK** là đã hoàn thành, dữ liệu lỗi có thể bị xem là thành công. Với tác vụ thanh toán hoặc thay đổi trạng thái, điều này thậm chí có thể khiến transaction tiếp tục theo đường sai.

Tùy yêu cầu, có thể: để exception lan ra; ghi log và ném lại; hoặc trả về một kiểu kết quả tường minh như **Success** / **ValidationFailure** / **InfrastructureFailure**. Nếu chọn kiểu kết quả, sealed hierarchy và exhaustive switch cũng là công cụ tốt để buộc consumer xem xét mọi trường hợp.

## 8. Switch statement khác switch expression ở chỗ nào?

Với **switch expression**, các nhánh tạo ra một giá trị (hoặc ném exception). Block của nhánh trả giá trị dùng **yield**. Giá trị của toàn bộ switch có thể được return từ phương thức:

~~~java
// Minh họa trong phương thức String handle(...).
return switch (request) {
    case Ping() -> "PONG";
    case Register(var name, var age) -> "REGISTER";
    case Cancel(var ticket) -> "CANCEL";
    case null -> throw new IllegalArgumentException("request");
};
~~~

Với **switch statement**, mục tiêu là thực hiện lệnh; case body có thể gọi method, log, bắt ngoại lệ mà không yield giá trị:

~~~java
// Minh họa trong một phương thức void, dùng Request như mục 5.
switch (request) {
    case Ping() -> System.out.println("PONG");
    case Register(var name, var age) ->
            System.out.println("REGISTER:" + name);
    case Cancel(var ticket) -> {
        if (ticket == null) throw new IllegalArgumentException("ticket");
        System.out.println("CANCEL:" + ticket);
    }
    case null -> throw new IllegalArgumentException("request");
}
~~~

Khi pattern matching được dùng trong switch statement ở Java 21, trình biên dịch cũng kiểm tra exhaustiveness theo quy tắc pattern switch. **Không được suy ra** rằng mọi switch statement Java đều phải exhaustive: switch statement truyền thống chỉ dùng nhãn hằng số có những quy tắc khác và có thể thiếu default.

**yield không phải cách thoát khỏi switch statement.** Khi cần trả kết quả từ một phương thức dùng statement, có thể dùng return theo quy tắc phương thức; khi cần trả kết quả từ switch expression, dùng biểu thức case hoặc yield.

## 9. Kết hợp exception với guard, exhaustiveness và dominance

Có ba kiểm tra độc lập cần nhớ:

1. **Matching và guard:** case có pattern khớp; nếu có **when**, guard phải true mới chọn body.
2. **Exhaustiveness:** một switch expression phải bao phủ tất cả các trường hợp kiểu phù hợp (hoặc có nhánh tổng quát). Nhánh có guard tùy ý thường không bao phủ toàn bộ subtype.
3. **Dominance:** nếu một case rộng nằm trước case hẹp, case hẹp có thể không còn được chọn và gây lỗi biên dịch.

Ví dụ:

~~~java
// Đoạn minh họa: có thể là một phần của return switch (request).
case Register(var name, int age) when age >= 18 -> "ADULT";
case Register(var name, int age) -> "OTHER REGISTER";
~~~

Nhánh đầu chỉ dành cho người từ 18 tuổi, nhánh hai bao phủ Register còn lại. Nếu đặt nhánh Register **không guard** lên trước, nhánh có guard phía sau bị che.

Khi có lỗi phát sinh trong guard, lỗi **không làm guard trở thành false**. Nó lan ra theo quy tắc exception. Nếu cần chuyển một lỗi validation thành giá trị nghiệp vụ, đưa việc validation vào block có try/catch thường rõ ràng hơn.

**Throw không thay thế exhaustiveness:** chỉ viết case cho một subtype rồi ném exception trong case đó vẫn không bao phủ các subtype còn lại. Muốn switch expression biên dịch, các nhánh phải bao phủ mọi giá trị thuộc miền kiểu, kể cả những nhánh mà hành vi là throw.

Ví dụ, với Request có Register, Cancel và Ping, một switch chỉ chứa **case Register(...) -> throw ...** sẽ không exhaustive. Cần case phù hợp cho Cancel và Ping nữa hoặc một nhánh tổng quát có chủ đích.

## 10. Hạn chế lỗi trong case body bằng thiết kế rõ ràng

**Tránh case quá dài:** nếu mỗi nhánh có nhiều try/catch, vòng lặp, logging và gọi dịch vụ, switch expression có thể khó đọc hơn một phương thức chuyên trách. Tách xử lý:

~~~java
// Đoạn minh họa: registerSafely(...) là phương thức riêng.
return switch (request) {
    case Register r -> registerSafely(r);
    case Cancel c -> cancelSafely(c);
    case Ping p -> "PONG";
    case null -> throw new IllegalArgumentException("request");
};
~~~

Bằng cách này, switch chọn nhánh theo subtype còn các phương thức con quản lý lỗi chuyên biệt. Nếu muốn kiểm thử lỗi được bắt và loại lỗi để lan ra, các phương thức con là điểm đặt test thuận tiện.

**Không dùng exception làm nhánh điều khiển thông thường** khi một điều kiện boolean đủ rõ. Ví dụ age < 18 có thể được biểu diễn bằng yield kết quả từ chối mà không nhất thiết ném exception. Exception phù hợp với tình huống không thể hoàn tất bình thường hoặc khi hợp đồng API định nghĩa lỗi theo cách đó.

**Không mất stack trace:** nếu bắt rồi ném ngoại lệ mới, cân nhắc truyền cause vào constructor của loại exception mới. Đừng chỉ nối chuỗi thông báo và bỏ mọi thông tin nguyên nhân, nhất là với lỗi hệ thống.

**Đừng bắt Throwable hoặc Error một cách tùy tiện:** Error thường đại diện cho vấn đề nghiêm trọng hơn lỗi nghiệp vụ thông thường. Thông thường bắt loại checked/unchecked exception cụ thể phù hợp hơn.

**Cẩn thận khi dùng side effect:** nếu một case đã gọi dịch vụ ngoài rồi mới ném exception, caller retry có thể lặp tác dụng phụ. Quy định rõ ranh giới transaction, idempotency và cơ chế bù trừ trong ứng dụng thực tế.

## 11. Bảng kiểm thử nên có

| Tình huống | Kết quả cần xác nhận |
| --- | --- |
| Subtype hợp lệ | Case đúng chạy và yield kết quả đúng |
| Validation hợp lệ | Không vào catch, dữ liệu đã chuẩn hóa |
| Validation ném checked exception | Catch đúng loại, tạo kết quả từ chối theo hợp đồng |
| Dữ liệu vi phạm điều kiện và chủ ý throw | Exception lan ra caller và được xử lý đúng nơi |
| Null selector | Case null hoặc chính sách từ chối rõ ràng |
| Record có component null | Pattern/validation hoạt động như dự kiến |
| Guard trả false | Đi sang nhánh phù hợp tiếp theo |
| Guard ném lỗi | Lỗi lan ra, không nhầm thành false |
| Lỗi khi tạo selector hoặc khi matching | Catch trong body không được giả định sẽ chạy |
| Thêm subtype mới vào sealed hierarchy | Compiler yêu cầu cập nhật nhánh nếu switch không default |

Có thể viết kiểm thử đơn giản cho hai luồng:

~~~java
// Đoạn kiểm thử minh họa bên trong class CaseBodyExceptionDemo.
String result = handle(new Register("Lan", 20));
if (!result.equals("REGISTERED: Lan")) {
    throw new AssertionError("wrong result");
}

try {
    handle(new Cancel(null));
    throw new AssertionError("expected exception");
} catch (IllegalArgumentException ex) {
    if (!"ticket".equals(ex.getMessage())) {
        throw new AssertionError("wrong exception", ex);
    }
}
~~~

Một test cho lỗi có thể **yield thay vì throw** nên xác nhận trực tiếp kết quả từ chối. Một test cho nhánh throw nên dùng cơ chế assertThrows (nếu có test framework) hoặc try/catch như trên. Ngoài ra nên kiểm tra tác dụng phụ và tài nguyên nếu case có gọi dịch vụ ngoài.

## 12. Checklist code review

Trước khi hoàn tất một switch có logic exception, hãy tự hỏi:

- [ ] Mỗi case phù hợp có một hợp đồng rõ: **trả kết quả**, **yield kết quả từ chối** hay **throw**?
- [ ] Với switch expression, mọi đường đi bình thường trong block có cung cấp giá trị hợp lệ không?
- [ ] Checked exceptions từ lời gọi trong case đã được catch hoặc khai báo throws chưa?
- [ ] Có catch quá rộng biến lỗi hệ thống thành kết quả thành công không?
- [ ] Null selector, null component và record pattern lồng nhau đã được phân biệt chưa?
- [ ] Có lỗi có thể xuất hiện ở selector, guard hoặc matching **trước** case body không?
- [ ] Các case đã thỏa exhaustiveness và không bị dominance sai thứ tự chưa?
- [ ] Hành vi exception có ảnh hưởng transaction, retry, logging hoặc tài nguyên không?
- [ ] Đã có test cho đường yield, catch, throw và ngoại lệ lan lên caller chưa?

**Kết luận:** Trong Java Pattern Matching, case body có thể **trả giá trị**, **dùng block với yield**, **bắt lỗi cụ thể bằng try/catch** hoặc **ném ngoại lệ để kết thúc bất thường**. Thiết kế đúng là xác định ngoại lệ phát sinh **ở giai đoạn nào** và **được xử lý ở ranh giới nào**, thay vì catch tất cả trong mỗi case. Kết hợp cách đó với quy tắc exhaustiveness, null và flow scoping sẽ tạo ra mã phân nhánh vừa dễ đọc vừa giữ được hành vi lỗi dự kiến.