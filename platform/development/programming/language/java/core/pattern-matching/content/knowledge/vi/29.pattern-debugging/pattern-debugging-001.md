# Đọc giá trị pattern variable khi debug

**Chủ đề:** Java Core Pattern Matching — Debugging. Bài hướng dẫn cách quan sát **pattern variable** trong trình gỡ lỗi khi dùng **instanceof**, **record pattern** và **switch pattern**. Các ví dụ đầy đủ sử dụng **Java 21 trở lên** (record patterns/JEP 440 và pattern matching for switch/JEP 441 đã chính thức), không cần `--enable-preview`.

## 1. Pattern variable là gì và vì sao khó quan sát khi debug?

**Pattern variable** là biến cục bộ được tạo ra khi một pattern ràng buộc thành công một giá trị. Chẳng hạn:

~~~java
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Khi biểu thức `value instanceof String text` trả về true, biến **text** có kiểu String và được phép dùng trong nhánh if. Với **record pattern**, trình biên dịch còn có thể ràng buộc các component của record:

~~~java
record Point(int x, int y) {}

// Đoạn minh họa trong một phương thức:
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
~~~

Khi gỡ lỗi, người học thường gặp các hiện tượng: nhìn thấy biến **value** nhưng không thấy **x, y**; thêm watch cho biến pattern thì báo không tìm thấy biến; breakpoint đặt trong một nhánh case không bao giờ kích hoạt; hoặc thấy một giá trị null dù cho rằng “pattern đã khớp thì dữ liệu chắc chắn khác null”.

Để đọc đúng giá trị, phải phân biệt:

1. **Pattern đã được đánh giá và khớp hay chưa?**
2. **Luồng điều khiển đã đi tới vùng mà biến pattern nằm trong scope chưa?**
3. **Debugger đang dừng ở đúng stack frame và đúng vị trí trong source không?**
4. **Mã có thông tin debug về biến cục bộ không?**
5. **Đây là biến do pattern ràng buộc hay là một biến khác cùng tên ở nhánh khác?**

**Nguyên tắc:** pattern variable không phải field của object và không tồn tại ở mọi thời điểm của phương thức. Nó có phạm vi và thời gian tồn tại phụ thuộc cấu trúc pattern cùng luồng điều khiển; debugger chỉ có thể trình bày hợp lý khi chương trình dừng ở vị trí phù hợp.

## 2. Flow scoping: điều kiện quyết định nơi có thể đọc biến

Java dùng **flow scoping**: phạm vi của pattern variable dựa trên đường đi mà trình biên dịch biết pattern đã khớp.

### 2.1. Dùng được trong nhánh if và sau toán tử &&

~~~java
if (value instanceof String text && !text.isBlank()) {
    // Đặt breakpoint tại dòng này: text đã được ràng buộc.
    System.out.println(text.trim());
}
~~~

Nếu debugger dừng tại dòng `System.out.println`, có thể xem **text** trong danh sách local variables và đánh giá **text.length()**. Nếu `value` không phải String hoặc chuỗi blank, dòng trong nhánh không được thực thi; không có lý do để chờ breakpoint đó kích hoạt.

**&&** là toán tử short-circuit: vế phải chỉ được tính khi vế trái true. Do đó `text` khả dụng trong `!text.isBlank()`.

Ngược lại, đoạn sau không hợp lệ:

~~~java
// Không biên dịch: vế phải của || có thể chạy khi pattern không khớp.
if (value instanceof String text || text.isBlank()) {
    System.out.println("invalid");
}
~~~

Debugger không thể “xem một biến pattern ở bất cứ đâu” nếu bản thân ngôn ngữ không cho phép dùng biến đó ở vị trí ấy.

### 2.2. Sau if không tự nhiên còn scope

~~~java
if (value instanceof String text) {
    System.out.println(text);
}
// Không biên dịch: text không ở trong scope tại đây.
System.out.println(text);
~~~

Tuy nhiên, khi đường đi không khớp **kết thúc chắc chắn** (ví dụ return hoặc throw), flow scoping có thể cho phép dùng biến sau if:

~~~java
static int lengthOrReject(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("expected String");
    }
    return text.length(); // text đã chắc chắn được ràng buộc.
}
~~~

**Vị trí breakpoint phải tương ứng với luồng thực tế**, không chỉ theo vị trí gần với điều kiện trong source. Hai cách viết if trông gần giống nhau nhưng tạo scope khác nhau.

## 3. Chuẩn bị chương trình để quan sát bằng debugger

### 3.1. Biên dịch với thông tin debug cho biến cục bộ

Với một tệp Java tên **PatternVariableDebugDemo.java**:

~~~bash
javac -g PatternVariableDebugDemo.java
java PatternVariableDebugDemo
~~~

Tùy chọn **-g** yêu cầu javac đưa thông tin gỡ lỗi gồm source, số dòng và biến cục bộ vào class file. Đây là lựa chọn tốt cho bài thực hành xem pattern variable.

Cách dùng mặc định của javac thường có thông tin source/line, nhưng **không nhất thiết có tên và phạm vi của mọi biến cục bộ**. Nếu không thấy tên biến trong debugger, hãy thử biên dịch lại bằng `-g`. Có thể kiểm tra metadata debug bằng:

~~~bash
javap -l -p PatternVariableDebugDemo
~~~

Trong kết quả, tìm phần **LocalVariableTable** tại phương thức tương ứng. Việc biến được compiler biểu diễn trong bytecode không buộc mọi debugger/JVM luôn hiển thị tên biến như ở source; còn phụ thuộc phạm vi sống của local, vị trí dừng, trình biên dịch và khả năng trình gỡ lỗi.

### 3.2. Đặt breakpoint tại câu lệnh chạy sau khi khớp

Không đặt breakpoint duy nhất **ngay đầu phương thức** rồi kỳ vọng mọi biến pattern đều đã được tạo. Tại thời điểm đó, điều kiện chưa chắc được đánh giá.

Với nhánh `instanceof`, vị trí tốt là **dòng đầu tiên trong nhánh true** sau điều kiện. Với switch, vị trí tốt là **câu lệnh đầu trong case body** sau nhãn pattern và guard. Khi guard false, breakpoint trong body sẽ **không dừng**; hãy kiểm tra nhánh fallback hoặc dừng trước switch rồi step.

### 3.3. Chọn đúng stack frame

Trong IDE hoặc `jdb`, danh sách **Locals** gắn với *stack frame đang được chọn*. Nếu debugger đang dừng trong `String.trim()` hoặc một helper khác, nó không có cùng local variables với phương thức chứa pattern. Hãy quay lại frame xử lý pattern rồi quan sát giá trị.

## 4. Chương trình Java 21 hoàn chỉnh để thực hành

Ví dụ gồm ba loại thông điệp. Các vị trí có chú thích **BREAKPOINT** là điểm thuận tiện để xem biến sau khi pattern đã khớp.

Lưu toàn bộ vào **PatternVariableDebugDemo.java**:

~~~java
public class PatternVariableDebugDemo {
    sealed interface Message permits Login, Transfer, Logout {}

    record Login(String username, int attempts) implements Message {}
    record Transfer(String from, String to, long amount) implements Message {}
    record Logout(String username) implements Message {}

    static String inspect(Message message) {
        if (message instanceof Login(String username, int attempts)
                && username != null && !username.isBlank()) {
            String normalized = username.trim();
            // BREAKPOINT-IF: xem message, username, attempts, normalized.
            System.out.println("IF: username=[" + username
                    + "], attempts=" + attempts);
            return "LOGIN:" + normalized;
        }

        return switch (message) {
            case Login(var username, var attempts) ->
                    "LOGIN_REJECTED:" + attempts;

            case Transfer(String from, String to, long amount)
                    when from != null && to != null && amount > 0 -> {
                // BREAKPOINT-TRANSFER: xem from, to, amount.
                System.out.println("CASE: from=" + from
                        + ", to=" + to + ", amount=" + amount);
                yield "TRANSFER_OK:" + amount;
            }

            case Transfer(var from, var to, var amount) ->
                    "TRANSFER_REJECTED:" + amount;

            case Logout(var username) -> {
                // BREAKPOINT-LOGOUT: xem username.
                System.out.println("CASE: username=" + username);
                yield "LOGOUT:" + username;
            }

            case null -> "NO_MESSAGE";
        };
    }

    public static void main(String[] args) {
        Message[] samples = {
                new Login(" An ", 1),
                new Login(" ", 2),
                new Login(null, 3),
                new Transfer("A", "B", 100),
                new Transfer("A", "C", -2),
                new Transfer(null, "B", 100),
                new Logout("Binh"),
                null
        };

        for (Message message : samples) {
            System.out.println(inspect(message));
        }
    }
}
~~~

Chạy bằng JDK 21+:

~~~bash
javac -g PatternVariableDebugDemo.java
java PatternVariableDebugDemo
~~~

**Stdout chính xác** khi chạy bình thường:

~~~text
IF: username=[ An ], attempts=1
LOGIN:An
LOGIN_REJECTED:2
LOGIN_REJECTED:3
CASE: from=A, to=B, amount=100
TRANSFER_OK:100
TRANSFER_REJECTED:-2
TRANSFER_REJECTED:100
CASE: username=Binh
LOGOUT:Binh
NO_MESSAGE
~~~

Các dòng đánh dấu BREAKPOINT trong comment không tự dừng chương trình; cần mở ứng dụng bằng debugger và đặt breakpoint thật tại câu lệnh ngay sau comment. Cũng không phải mọi nhánh đều in ra biến: giá trị **LOGIN_REJECTED** và **TRANSFER_REJECTED** được tạo trực tiếp bởi switch expression.

## 5. Lần lượt quan sát giá trị ở các breakpoint

### 5.1. Breakpoint trong nhánh instanceof + record pattern

Với **new Login(" An ", 1)**, chương trình khớp pattern `Login(String username, int attempts)`; điều kiện username khác null và không blank đều true.

Khi dừng tại **BREAKPOINT-IF**, ta mong đợi:

| Biến/biểu thức | Giá trị quan sát |
| --- | --- |
| **message** | Một record `Login[username= An , attempts=1]` (hiển thị phụ thuộc debugger) |
| **username** | Chuỗi có một dấu cách ở đầu và cuối: `" An "` |
| **attempts** | `1` |
| **normalized** | `"An"` |
| **username.equals(normalized)** | `false` |

Đừng nhầm biến **username** là giá trị đã trim; **normalized** mới là biến tạo từ kết quả trim. Nếu muốn quan sát biến trước và sau phép gán, đặt hai breakpoint: tại dòng gán **normalized** và tại dòng println sau phép gán. Trước khi thực thi câu lệnh gán, biến normalized chưa có giá trị đã gán; debugger có thể không hiển thị nó như một biến khả dụng hoặc hiện giá trị chưa phù hợp để đọc.

Với **Login(" ", 2)** hoặc **Login(null, 3)**, điều kiện if không đủ điều kiện, nên không dừng tại BREAKPOINT-IF. Hãy chuyển breakpoint đến nhánh **case Login(var username, var attempts)** của switch để xem username và attempts của giá trị bị từ chối.

### 5.2. Breakpoint trong switch case có when

Với **new Transfer("A", "B", 100)**, record pattern ràng buộc ba biến **from, to, amount**. Guard **from != null && to != null && amount > 0** true, nên case body chạy.

Tại **BREAKPOINT-TRANSFER**, giá trị dự kiến:

| Biến | Giá trị |
| --- | --- |
| **message** | Record `Transfer[from=A, to=B, amount=100]` |
| **from** | `"A"` |
| **to** | `"B"` |
| **amount** | `100L` (kiểu `long`) |

Có thể thêm watch **amount > 0**; tại đây kết quả true. Breakpoint trong case body chứng minh guard đã vượt qua nhưng **không tự cho thấy toàn bộ những lần thử case trước đó**. Nếu cần hiểu vì sao case không được chọn, đặt breakpoint trước switch rồi dùng Step Over/Step Into phù hợp, hoặc quan sát nhánh fallback.

Với **Transfer("A", "C", -2)**, guard false vì amount âm; chương trình vào case Transfer không guard và trả **TRANSFER_REJECTED:-2**. Với **Transfer(null, "B", 100)**, guard false do from null; kết quả là **TRANSFER_REJECTED:100**. Ở cả hai trường hợp, BREAKPOINT-TRANSFER không kích hoạt.

### 5.3. Breakpoint trong nhánh Logout

Với **Logout("Binh")**, case Logout khớp và biến **username** của riêng case này mang giá trị **"Binh"**. Dù trùng tên với username trong nhánh Login, chúng là **những pattern variable khác nhau trong các scope khác nhau**. Không suy ra giá trị hay lifetime của một biến từ case khác.

### 5.4. Case null

Với **message == null**, switch chọn **case null -> "NO_MESSAGE"**. Không có các pattern variable **username**, **from** hoặc **amount** được ràng buộc. Việc watch các tên này không có nghĩa tại nhánh null; đọc trực tiếp **message** để xác nhận selector null.

## 6. Cách thao tác trong IDE và jdb

### 6.1. IDE: IntelliJ IDEA, Eclipse hoặc VS Code với Java Debugger

Các IDE có tên lệnh và giao diện hơi khác nhau, nhưng quy trình chung là:

1. Biên dịch cấu hình **Debug** hoặc dùng `javac -g`; mở đúng tệp source tương ứng class đang chạy.
2. Đặt breakpoint tại câu lệnh trong nhánh **IF**, **TRANSFER** hoặc **LOGOUT** có comment BREAKPOINT.
3. Chạy ứng dụng ở chế độ **Debug** thay vì chỉ Run.
4. Khi debugger dừng, chọn stack frame của **PatternVariableDebugDemo.inspect**.
5. Xem **Variables/Locals**, mở rộng object **message** và đọc trực tiếp những biến pattern đang trong scope.
6. Dùng **Evaluate Expression** hoặc **Watch** cho các biểu thức nhỏ, ví dụ `username.length()`, `amount > 0`, `message.getClass().getSimpleName()` khi biến tương ứng và receiver khác null.
7. Dùng **Step Over** để quan sát sự chuyển từ điều kiện sang case body hoặc từ phép gán sang dòng tiếp theo; dùng **Resume** để tới đầu vào kế tiếp.

Các biểu thức đánh giá trong debugger thực sự có thể gọi method. Đừng gọi phương thức có **side effect**, sửa object hoặc phát sinh giao dịch chỉ để xem giá trị. Với object null, biểu thức như `message.getClass()` sẽ ném NullPointerException; trong case null chỉ cần đọc message.

### 6.2. Command line: dùng jdb

Sau khi biên dịch có debug symbols:

~~~bash
javac -g PatternVariableDebugDemo.java
jdb -classpath . PatternVariableDebugDemo
~~~

Trong cửa sổ `jdb`, có thể bắt đầu bằng các lệnh:

~~~text
stop in PatternVariableDebugDemo.inspect
run
locals
next
locals
print message
where
~~~

Lệnh **stop in** đặt breakpoint tại lúc phương thức inspect bắt đầu; **run** khởi chạy chương trình, **locals** liệt kê biến cục bộ của stack frame hiện tại, **next** chuyển qua câu lệnh tiếp theo, **print** xem một biểu thức, còn **where** cho biết call stack.

Ở điểm vào phương thức, **message** có thể đã có, nhưng **username**, **attempts**, **from** hoặc **to** chưa nằm trong scope. Tiếp tục dùng **next** tới câu lệnh thực sự chạy trong nhánh đã khớp rồi thử:

~~~text
locals
print username
print attempts
cont
~~~

Lệnh **print username** chỉ có ý nghĩa khi debugger đang dừng trong nhánh có biến username tương ứng. Nếu debugger báo không tìm thấy biến, kiểm tra **vị trí dừng, frame, debug symbols và đường đi thực thi** trước khi suy ra chương trình không ràng buộc pattern. Với nhánh Transfer, thử **print from**, **print to** và **print amount** khi đã dừng trong body của nhánh đó.

Có thể đặt thêm **breakpoint theo dòng nguồn** bằng lệnh `stop at ClassName:lineNumber` với số dòng thực trong tệp đang biên dịch. Số dòng không được cố định trong bài vì có thể thay đổi khi chép mã, thêm package hoặc chỉnh sửa file.

### 6.3. Khi IDE cho thấy giá trị khác với stdout

Kiểm tra lần lượt:

- Có đang chạy đúng bản build được biên dịch từ source hiện tại không?
- Có nhiều lần gọi inspect với các input khác nhau và breakpoint đang dừng ở lần gọi nào?
- Biến đang nhìn là **username gốc** hay **normalized**?
- Stack frame đang chọn thuộc inspect hay thuộc một method khác?
- Breakpoint đặt trước hay sau lệnh gán?
- Local variable còn nằm trong scope ở bytecode/debug metadata không?

Nếu cần kiểm tra đường đi nhanh, một log tạm tại nhánh phù hợp hoặc một test assertion có thể bổ trợ debugger, nhưng không nên biến việc thêm log mọi nơi thành phương pháp chính.

## 7. Null và record pattern: điểm rất dễ hiểu nhầm khi đọc biến

Cần tách hai tình huống khác nhau:

**A. Selector null trong instanceof**

~~~java
Object missing = null;
System.out.println(missing instanceof String s); // false
~~~

Không có object String nào để ràng buộc biến s, nên kết quả false.

**B. Component của record là null**

~~~java
record Wrapper(String value) {}

System.out.println(
        new Wrapper(null) instanceof Wrapper(String inner)); // true
System.out.println(
        new Wrapper(null) instanceof Wrapper(var inner));    // true
~~~

Đây là hành vi quan trọng của **unconditional component patterns**: khi component tĩnh đã là String, pattern thành phần `String inner` có thể ràng buộc cả giá trị null của component ấy. Đừng suy diễn rằng mọi nested type pattern đều khớp null: khả năng khớp phụ thuộc vào **kiểu tĩnh của component** và mẫu có unconditional ở kiểu đó hay không.

Vì vậy trong ví dụ chính, điều kiện `message instanceof Login(String username, int attempts)` **có thể khớp Login(null, 3)**, và biến username có thể chứa null. Để tránh NullPointerException, mã cố ý viết:

~~~java
if (message instanceof Login(String username, int attempts)
        && username != null && !username.isBlank()) {
    // Tới đây username chắc chắn khác null.
}
~~~

Nếu bỏ **username != null**, lời gọi **username.isBlank()** có thể ném NullPointerException **ngay trong điều kiện if**, trước khi vào thân if. Một breakpoint chỉ đặt bên trong thân if sẽ không bắt được đường lỗi đó; cần bật breakpoint cho exception hoặc dừng trước điều kiện.

Tương tự, trong switch, guard của Transfer kiểm tra **from != null && to != null** trước khi xem amount > 0. Khi component null, case có guard không được chọn, nhưng case **Transfer(var from, var to, var amount)** vẫn có thể khớp.

**Đặc biệt:** một **record pattern lồng** yêu cầu giải cấu trúc một record con, chẳng hạn `Box(Point(var x, var y))`. Nếu component Point thực sự null thì mẫu con Point(...) không khớp. Đó không phải cùng tình huống với việc ràng buộc một component tham chiếu bằng pattern unconditional.

## 8. Phân biệt “không thấy biến” và “giá trị không khớp”

Khi một breakpoint không kích hoạt hoặc debugger không đọc được tên biến, hãy đặt giả thuyết đúng:

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Breakpoint trong if không chạy | Pattern không khớp hoặc điều kiện && false | Dừng trước if, xem message và từng vế điều kiện |
| Breakpoint trong switch case có when không chạy | Pattern không khớp hoặc guard false | Dừng trước switch, theo đường đi đến case dự phòng |
| Watch báo variable not found | Ngoài flow scope hoặc sai stack frame | Dừng trong case body đúng và chọn frame inspect |
| Biến xuất hiện nhưng là null | Record component có thể là null | Xem constructor, component và guard |
| Chỉ thấy message, không thấy component variables | Dừng trước matching hoặc thiếu local-variable metadata | Step tới nhánh sau khi khớp và biên dịch -g |
| Thấy username nhưng giá trị không như dự đoán | Đang dừng ở sample khác hoặc scope khác cùng tên | Xem message hiện tại và call stack |
| Thấy dữ liệu cũ dù sửa source | Class cũ còn được chạy | Clean/rebuild và kiểm tra cấu hình chạy |
| Exception xảy ra trước case body | Guard, selector, accessor hoặc điều kiện phát sinh lỗi | Bật exception breakpoint, inspect call stack |

Khi record pattern được thử, Java có thể gọi accessor để lấy component. Nếu accessor do ứng dụng ghi đè ném lỗi, matching có thể kết thúc bất thường (trong trường hợp tương ứng, được biểu diễn bằng **MatchException** có cause). Lúc đó breakpoint trong body không được thực thi. Cần dừng tại điểm exception hoặc tại lời gọi accessor, thay vì tìm một pattern variable chưa được ràng buộc hoàn tất.

## 9. Một số quy tắc khi Evaluate Expression hoặc đặt Watch

- **Chỉ xem biến đang trong scope.** Một watch cố định của `username` có thể hợp lệ ở case Login hoặc Logout nhưng không có nghĩa tại case Transfer.
- **Kiểm tra kiểu tĩnh và giá trị runtime:** `var amount` trong record pattern Transfer ràng buộc giá trị `long`; giá trị trong debugger có thể được hiển thị là 100 hoặc 100L tùy công cụ.
- **Tránh thay đổi chương trình trong lúc quan sát.** Evaluate Expression gọi method có thể chạy logic thật, bao gồm ném lỗi hoặc thay đổi trạng thái.
- **Không gọi method trên biến null.** Với `username` có thể null, đánh giá `username.length()` trước khi kiểm tra null sẽ tạo lỗi mới từ chính debugger.
- **Để ý điều kiện guard:** debugger tại body chỉ chứng minh guard true trên lần gọi ấy; muốn nghiên cứu guard false, dùng input thử riêng và breakpoint ở điểm trước nhánh.
- **Đừng phụ thuộc vào tên biến ở bytecode khi thiếu thông tin debug.** Trình biên dịch có thể tái sử dụng slot cho những local khác nhau; tên source và scope phải được ánh xạ qua metadata tương ứng.
- **Kiểm tra thời điểm gán:** biến cục bộ được khai báo trước câu lệnh gán không nhất thiết có giá trị meaningful ở điểm dừng chưa thực thi phép gán.
- **Với lambda hoặc stream:** pattern variable khai báo bên trong một lambda không tự chuyển qua lambda tiếp theo; khi dừng debug phải chọn frame và phạm vi của đúng lambda đang được gọi.

## 10. Mẹo debug nhanh cho từng dạng pattern

### 10.1. Type pattern instanceof

~~~java
if (value instanceof String text) {
    // Breakpoint trong đây, đọc text.
    System.out.println(text);
}
~~~

Nếu value là null, không vào nhánh. Nếu value không phải String, không có biến text. Nếu value là String, text tham chiếu cùng object String đó.

### 10.2. Record pattern

~~~java
if (value instanceof Point(int x, int y)) {
    // Breakpoint sau khi matching, đọc x và y.
    System.out.println(x + y);
}
~~~

Đặt breakpoint trong nhánh để xem các component, không cần cast Point rồi gọi x()/y() chỉ để xem dữ liệu. Debugger có thể cho phép mở rộng cả value lẫn các biến x, y để đối chiếu.

### 10.3. Switch pattern có guard

~~~java
return switch (message) {
    case Transfer(var from, var to, long amount)
            when amount > 0 -> {
        // Breakpoint tại println sau đây.
        System.out.println(amount);
        yield "positive";
    }
    case Transfer(var from, var to, var amount) -> "other";
    case Login(var user, var attempts) -> "login";
    case Logout(var user) -> "logout";
    case null -> "null";
};
~~~

Đây là **đoạn minh họa** dùng các record trong chương trình chính. Khi amount âm hoặc bằng 0, nhánh đầu có guard không chạy; biến amount trong nhánh dự phòng là **một binding riêng**. Không nhầm hai biến cùng tên với một biến xuyên suốt nhiều case.

### 10.4. Mẫu lồng

Giả sử có `record Shipment(Point destination)`. Với:

~~~java
// Minh họa: Shipment và Point đã được khai báo phù hợp.
if (value instanceof Shipment(Point(int x, int y))) {
    System.out.println(x + "," + y);
}
~~~

Đặt breakpoint ở println, đọc x/y, đồng thời mở rộng object value để xem Shipment.destination. Nếu destination null, pattern lồng Point(...) không khớp và breakpoint không chạy. Muốn phân biệt “kiểu sai” với “component null”, đặt breakpoint trước điều kiện hoặc kiểm tra object record ở nhánh dự phòng.

## 11. Quy trình debug có thể lặp lại

Hãy đi theo thứ tự sau thay vì đặt watch ngẫu nhiên:

1. **Chuẩn bị đầu vào cụ thể:** ví dụ Login(" An ", 1), Login(null, 3), Transfer("A", "B", 100) và Transfer("A", "C", -2).
2. **Biên dịch có debug symbols:** `javac -g`; xác nhận chạy đúng class/source.
3. **Đặt breakpoint tại chỗ dùng biến:** sau điều kiện instanceof, tại dòng đầu case body, hoặc sau phép gán biến normalized.
4. **Kiểm tra stack frame và selector:** xem message trước, biết chính xác lần gọi nào đang được xử lý.
5. **Đọc pattern variables:** quan sát username/attempts hay from/to/amount; phân biệt biến đã ràng buộc với biến được tính tiếp theo.
6. **So sánh nhánh không khớp:** dùng Step và quan sát nhánh fallback, nhất là khi guard false hoặc component null.
7. **Bật exception breakpoint nếu cần:** lỗi trong điều kiện, accessor hoặc guard có thể xảy ra trước body.
8. **Đối chiếu bằng test/stdout:** debugger cho biết trạng thái từng bước; assertion bảo vệ hành vi khi refactor.
9. **Bỏ breakpoint và biểu thức đánh giá có side effect** trước khi kết thúc phiên gỡ lỗi.

### Checklist tự kiểm tra

- [ ] Tôi biết vị trí nào trong source thực sự nằm **sau khi pattern khớp**.
- [ ] Tôi hiểu vì sao một biến pattern nằm trong hoặc ngoài scope.
- [ ] Tôi đã chọn stack frame chứa biến cần xem.
- [ ] Tôi biên dịch có thông tin debug cho local variables.
- [ ] Tôi không nhầm nhánh guard false với lỗi phát sinh trong guard.
- [ ] Tôi đã kiểm tra selector null và component null của record riêng biệt.
- [ ] Tôi không suy diễn giá trị của biến cùng tên từ case khác.
- [ ] Tôi không chạy các phép đánh giá trong debugger có thể thay đổi hành vi ứng dụng.

**Kết luận:** Muốn đọc được pattern variable khi debug, hãy dừng chương trình **sau thời điểm matching thành công và trong đúng flow scope**. Dùng `javac -g`, chọn đúng frame và quan sát cả object selector lẫn các biến được ràng buộc. Với record patterns, đặc biệt chú ý component có thể null; với switch, chú ý guard và case fallback. Khi hiểu các ranh giới đó, việc debug pattern matching trở thành việc theo dõi luồng thực thi có thể dự đoán, thay vì tìm kiếm một biến tưởng như “biến mất”.