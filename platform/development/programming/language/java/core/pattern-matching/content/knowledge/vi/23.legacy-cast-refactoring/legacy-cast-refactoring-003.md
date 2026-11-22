# Refactor chuỗi if-else theo subtype

**Chủ đề:** Refactor legacy cast trong Java Core Pattern Matching. Bài dùng Java 21+ cho các ví dụ về **pattern matching for switch** và **record patterns**; riêng **type pattern với instanceof** đã có từ Java 16, nên có thể áp dụng từng bước trên Java 17.

## 1. Nhận diện chuỗi if-else cần refactor

Trong mã Java cũ, một tham số kiểu cha thường được phân nhánh theo subtype bằng **instanceof**, rồi ép kiểu thủ công để lấy dữ liệu:

~~~java
// Minh họa bên trong một phương thức nhận biến command.
if (command instanceof Register) {
    Register register = (Register) command;
    // Xử lý dữ liệu Register.
} else if (command instanceof Disable) {
    Disable disable = (Disable) command;
    // Xử lý dữ liệu Disable.
} else if (command instanceof Ping) {
    // Xử lý Ping.
} else {
    // Đầu vào không khớp.
}
~~~

Cấu trúc này hợp lệ, nhưng khi số subtype tăng, phần lặp lại **kiểm tra kiểu → cast → dùng đối tượng** làm mã dài và khó nhận thấy trường hợp nào đã được xử lý. Một chỗ sửa hierarchy có thể khiến nhánh cuối âm thầm tiếp nhận kiểu mới, trong khi nghiệp vụ thực ra cần xử lý riêng.

Mục tiêu của refactor là:

- Bỏ các phép cast đã được **instanceof** bảo đảm, dùng biến pattern có kiểu đúng ngay tại điều kiện.
- Đặt logic của từng subtype trong một nhánh dễ nhận diện.
- Khi phù hợp, dùng **switch expression** cùng sealed hierarchy để compiler kiểm tra tính bao phủ của các nhánh.
- Giữ nguyên ý nghĩa của các điều kiện con, thứ tự ưu tiên, thông báo lỗi, giá trị trả về và chính sách null.

**Refactor thành công nghĩa là hành vi có chủ đích được giữ nguyên.** Code ngắn hơn chưa đủ: nếu đổi thứ tự nhánh hoặc thay ý nghĩa nhánh else, kết quả có thể khác.

## 2. Đầu tiên, cố định hợp đồng hành vi hiện tại

Trước khi sửa, hãy ghi lại những gì mỗi nhánh thực sự làm. Với một hệ lệnh có ba subtype:

~~~java
sealed interface Command permits Register, Disable, Ping {}

record Register(String username, int age) implements Command {}
record Disable(String username) implements Command {}
record Ping() implements Command {}
~~~

Giả sử hợp đồng xử lý là:

| Đầu vào | Kết quả mong muốn |
| --- | --- |
| Register có username không rỗng, age từ 18 | Trả thông báo REGISTER với tên |
| Register không đạt điều kiện | Trả INVALID REGISTER |
| Disable | Trả thông báo DISABLE với tên |
| Ping | Trả PONG |
| null | Trả NO COMMAND |

Trong hệ trên, Command là sealed interface và chỉ có ba record được phép triển khai trực tiếp. Record là kiểu final, nên không có subtype sâu hơn dưới chúng. Nếu một dự án thật có **class thường** hoặc **non-sealed subtype**, miền kiểu có thể mở hơn; khi đó kế hoạch refactor phải tính cả những kiểu chưa được liệt kê trực tiếp.

Cần xem riêng các yếu tố dễ bị thay đổi ngoài ý muốn: nhánh subtype con so với subtype cha; guard kiểm tra số/chuỗi; nhánh xử lý null; side effects như ghi log, gọi API hoặc cập nhật trạng thái; ngoại lệ và thứ tự gọi accessor. Không nên gom hoặc đổi nhánh nghiệp vụ chỉ vì có cú pháp pattern mới.

## 3. Bước an toàn nhất: thay instanceof + cast bằng type pattern

Thay vì kiểm tra một kiểu rồi ép lại cùng kiểu, ta có thể ràng buộc biến ngay trong **instanceof**:

**Trước:**

~~~java
if (command instanceof Register) {
    Register register = (Register) command;
    return register.username();
}
~~~

**Sau:**

~~~java
if (command instanceof Register register) {
    return register.username();
}
~~~

Ở cú pháp **Register register**, trình biên dịch vừa kiểm tra kiểu, vừa giới thiệu biến register có đúng kiểu Register. Không cần cast thủ công. Nếu không khớp, nhánh if không chạy và biến register không được sử dụng ở đường đi đó.

Ví dụ với nhiều subtype:

~~~java
// Đoạn minh họa: giả định đã có ba record ở mục 2.
static String typePatternVersion(Command command) {
    if (command instanceof Register register) {
        String username = register.username();
        if (username != null && !username.isBlank()
                && register.age() >= 18) {
            return "REGISTER:" + username;
        }
        return "INVALID REGISTER";
    } else if (command instanceof Disable disable) {
        return "DISABLE:" + disable.username();
    } else if (command instanceof Ping ping) {
        return "PONG";
    }
    return "NO COMMAND";
}
~~~

Những điểm đáng chú ý:

- Ta **chỉ thay cách kiểm tra/cast**; từng hành động, thứ tự if/else, điều kiện và đường return được giữ nguyên.
- Với **instanceof**, giá trị null không khớp bất kỳ type pattern nào, nên đi tới return cuối như mã cũ.
- Mã này có thể dùng trên Java 17; không bắt buộc phải chuyển sang switch chỉ để loại bỏ cast.
- Khi một nhánh có nhiều lệnh hoặc side effects, giữ dạng if/else đôi khi trực quan hơn việc chuyển cả khối sang switch.

### Flow scoping của biến pattern

Biến do type pattern tạo ra có phạm vi phụ thuộc luồng điều khiển. Ví dụ:

~~~java
if (command instanceof Register register
        && register.age() >= 18) {
    System.out.println(register.username());
}
~~~

Vế phải của **&&** chỉ được đánh giá nếu mẫu bên trái khớp, nên register đã tồn tại. Ngược lại, dùng register ở vế phải của **||** theo kiểu dưới đây là sai:

~~~java
// Không biên dịch: khi vế trái false, register chưa được ràng buộc.
if (command instanceof Register register
        || register.age() >= 18) {
    // ...
}
~~~

Dùng dấu **&&** theo đúng logic nghiệp vụ, không thay các phép nối điều kiện chỉ để cố đưa biến pattern sang phạm vi khác.

## 4. Khi nào nên chuyển sang switch expression?

Nếu các nhánh cùng **trả về một giá trị**, lựa chọn xử lý chủ yếu dựa trên subtype và mỗi nhánh có mục đích rõ, **switch expression** giúp gom toàn bộ phân nhánh vào một biểu thức.

Với record, ta có thể lấy trực tiếp các component tại nhánh case:

~~~java
// Minh họa: dùng các record Command, Register, Disable, Ping đã khai báo.
static String switchVersion(Command command) {
    return switch (command) {
        case Register(String username, int age)
                when username != null && !username.isBlank() && age >= 18 ->
                "REGISTER:" + username;

        case Register(var username, var age) -> "INVALID REGISTER";
        case Disable(var username) -> "DISABLE:" + username;
        case Ping() -> "PONG";
        case null -> "NO COMMAND";
    };
}
~~~

Ở đây có hai cơ chế khác nhau:

1. **Subtype/record pattern** mô tả trường hợp đầu vào, ví dụ Register hoặc Disable, và có thể ràng buộc giá trị component.
2. **when** là guard của một nhánh switch: khi pattern đã khớp, guard quyết định nhánh đó có được chọn không.

Nhánh Register có guard chỉ xử lý một phần giá trị Register. Nhánh Register không guard bên dưới đảm nhiệm **tất cả Register còn lại**, vì vậy chuỗi phân nhánh không làm mất trường hợp username rỗng hoặc age nhỏ hơn 18.

**Vì sao không có default?** Kiểu selector là sealed Command; cả Register, Disable và Ping đã được bao phủ. Với switch expression, compiler đòi hỏi tính **exhaustive** (bao phủ đầy đủ). Trường hợp null được viết riêng để giữ hành vi return NO COMMAND của chuỗi if/else cũ. Nếu bỏ **case null**, một switch có thể vẫn exhaustive theo subtype nhưng sẽ ném NullPointerException khi nhận null.

Với selector kiểu **Object** hoặc một hierarchy mở hơn, các case trên không đủ bao phủ mọi subtype: phải có nhánh phù hợp cho phần còn lại, ví dụ **default** (hoặc type pattern tổng quát) tùy hợp đồng nghiệp vụ.

## 5. Ví dụ Java 21 hoàn chỉnh: so sánh trước và sau refactor

Chương trình sau chứa hai triển khai của cùng nghiệp vụ: phiên bản cũ dùng chuỗi **if-else + cast** và phiên bản mới dùng **switch + record pattern**. Cả hai được gọi trên nhiều dữ liệu, bao gồm các biên của guard và null.

Lưu tệp với tên **SubtypeRefactorDemo.java**:

~~~java
public class SubtypeRefactorDemo {
    sealed interface Command permits Register, Disable, Ping {}

    record Register(String username, int age) implements Command {}
    record Disable(String username) implements Command {}
    record Ping() implements Command {}

    static String legacy(Command command) {
        if (command instanceof Register) {
            Register register = (Register) command;
            String username = register.username();
            if (username != null && !username.isBlank() && register.age() >= 18) {
                return "REGISTER:" + username;
            }
            return "INVALID REGISTER";
        } else if (command instanceof Disable) {
            Disable disable = (Disable) command;
            return "DISABLE:" + disable.username();
        } else if (command instanceof Ping) {
            return "PONG";
        }
        return "NO COMMAND";
    }

    static String modern(Command command) {
        return switch (command) {
            case Register(String username, int age)
                    when username != null && !username.isBlank() && age >= 18 ->
                    "REGISTER:" + username;
            case Register(var username, var age) -> "INVALID REGISTER";
            case Disable(var username) -> "DISABLE:" + username;
            case Ping() -> "PONG";
            case null -> "NO COMMAND";
        };
    }

    public static void main(String[] args) {
        Command[] samples = {
                new Register("Lan", 21),
                new Register("Mai", 16),
                new Register(" ", 30),
                new Register(null, 25),
                new Disable("Nam"),
                new Ping(),
                null
        };

        for (Command command : samples) {
            String before = legacy(command);
            String after = modern(command);
            System.out.println(after + " | same=" + before.equals(after));
        }
    }
}
~~~

Biên dịch và chạy với **JDK 21+**:

~~~bash
javac SubtypeRefactorDemo.java
java SubtypeRefactorDemo
~~~

Kết quả:

~~~text
REGISTER:Lan | same=true
INVALID REGISTER | same=true
INVALID REGISTER | same=true
INVALID REGISTER | same=true
DISABLE:Nam | same=true
PONG | same=true
NO COMMAND | same=true
~~~

Kết quả **same=true** cho cả bảy trường hợp cho thấy hai cách xử lý tương đương với tập dữ liệu kiểm tra của ví dụ. Đây không phải bằng chứng hai phương thức luôn tương đương trên mọi đầu vào hoặc sau mọi thay đổi: với code thực tế, cần thêm test đúng các quy tắc và đường đi cụ thể.

**Cách đọc nhánh Register:** mẫu **Register(String username, int age)** trích hai component theo thứ tự record khai báo. Điều kiện **username != null** tránh gọi **isBlank()** trên null. Nếu username blank hoặc age chưa đủ 18, nhánh guard false và case Register thứ hai xử lý. Nhánh Disable và Ping không thay đổi ý nghĩa. Case null tái hiện đường return cuối của legacy khi đầu vào null.

Một record pattern mang các component không có nghĩa tự kiểm tra dữ liệu nghiệp vụ. Nó diễn tả kiểu và dữ liệu được trích xuất; điều kiện **age >= 18** vẫn phải được viết rõ. Khi record cho phép một component tham chiếu null, việc khớp bằng một pattern không điều kiện như **var username** không đảm bảo thành phần đó khác null.

## 6. Thứ tự subtype: chỗ dễ đổi hành vi nhất

Với hệ class có kế thừa nhiều cấp, một đối tượng subtype cũng là thể hiện của kiểu cha. Một chuỗi if/else có nhánh kiểu cha đứng trước subtype cụ thể có thể đã **che mất** nhánh phía sau.

Ví dụ khái niệm:

~~~java
// Giả sử SpecialEvent kế thừa Event và value có kiểu Object.
if (value instanceof Event) {
    return "general";
} else if (value instanceof SpecialEvent) {
    return "special"; // Không tới được với SpecialEvent.
}
~~~

Nếu chuyển một cách máy móc sang switch với **case Event e** đứng trước **case SpecialEvent s**, compiler có thể báo nhánh SpecialEvent bị **dominated** (bị case rộng hơn bao phủ). Để phân loại đúng subtype cụ thể, thường phải đặt **SpecialEvent trước Event**:

~~~java
return switch (value) {
    case SpecialEvent s -> "special";
    case Event e -> "general";
    case null -> "no event";
    default -> "other";
};
~~~

**Nhưng thay thứ tự có thể sửa một hành vi sai cũ, chứ không còn là refactor thuần túy.** Trước khi thay, phải xác định yêu cầu thực sự là giữ hành vi general cho SpecialEvent hay sửa thành special. Nếu thay đổi nghiệp vụ là cần thiết, hãy nêu rõ và có test mới. Tránh trộn một sửa lỗi nghiệp vụ khó nhận biết vào việc thay cú pháp.

Trong nhánh switch có **when**, đặt trường hợp có điều kiện cụ thể trước case tổng quát cùng subtype:

~~~java
case Register(var name, int age) when age >= 18 -> "adult";
case Register(var name, var age) -> "minor";
~~~

Nếu đặt nhánh Register không guard lên trước, nhánh có guard phía sau sẽ bị che. Cần đánh giá cả **dominance** (case phía sau có còn cơ hội chạy không) và **exhaustiveness** (có đầu vào nào chưa được case nào xử lý không).

## 7. Tính bao phủ của switch khi refactor hierarchy

**Switch expression** yêu cầu tất cả giá trị selector có nhánh xử lý, theo phân tích tĩnh của compiler. Điều này là một lợi ích khi hierarchy được mô hình hóa bằng sealed class/interface và các subtype được kiểm soát.

Với ví dụ trên, nếu về sau bổ sung:

~~~java
// Minh họa thay đổi riêng biệt, không chép cùng khai báo Command cũ.
sealed interface Command permits Register, Disable, Ping, Reset {}
record Reset() implements Command {}
~~~

mà chưa có **case Reset()** trong modern(), việc biên dịch lại switch expression sẽ báo thiếu nhánh. Trong khi đó, chuỗi if/else có thể âm thầm đi tới return NO COMMAND mà không buộc ta xem xét mục đích của Reset.

Điều này cho thấy **không có default** có thể hữu ích: compiler nhắc người viết code cập nhật hành vi theo subtype mới. Nhưng chỉ áp dụng khi kiểu tĩnh và các case thực sự đủ thông tin để compiler chứng minh; một subtype **non-sealed** có thể còn cho phép kiểu con mới phía dưới và cần một case bao phủ nhánh đó.

Nếu nghiệp vụ chủ ý có hành vi chung cho tất cả giá trị chưa biết, **default** có thể hợp lý. Tuy nhiên, default viết quá sớm sẽ che tín hiệu khi hierarchy có subtype mới mà chưa được thiết kế hành vi riêng.

Cũng cần nhớ: **case null** phục vụ null selector; **default** thông thường không phải là cách xử lý null thay thế. Với **instanceof**, null không khớp nên tự rơi về nhánh else/return cuối. Khi đổi sang switch, hãy kiểm tra hợp đồng null thay vì suy luận từ exhaustiveness.

## 8. Chọn type pattern hay record pattern?

| Nhu cầu của nhánh | Cách thường rõ hơn | Ví dụ |
| --- | --- | --- |
| Chỉ cần biết object thuộc subtype | Type pattern hoặc type check | **command instanceof Ping** |
| Cần tiếp tục truyền/call trên cả object | Type pattern | **command instanceof Register register** |
| Cần nhiều component của một record | Record pattern | **case Register(var name, int age)** |
| Có record lồng record và cần component bên trong | Nested record pattern ngắn | **case Outer(Inner(var id))** |
| Nhiều subtype đều trả về một giá trị | Switch expression | **return switch (command) { ... };** |
| Logic mỗi subtype dài, nhiều side effects | If/else với type pattern hoặc tách phương thức | **handleRegister(register)** |

**Record pattern chỉ dùng cho record.** Nếu subtype là một class thông thường có getter, không thể viết **case OrdinaryClass(var x)** chỉ vì class có constructor phù hợp. Dùng type pattern rồi gọi getter, hoặc thiết kế một tầng chuyển đổi có chủ đích.

Khi chưa sẵn sàng chuyển toàn bộ sang switch, dùng **instanceof pattern** để loại cast trước là một bước nhỏ, dễ review, và vẫn có giá trị. Java 17 hỗ trợ hướng này; Java 21 mới cho phép dùng record patterns và pattern switch như ví dụ chính mà không bật preview.

## 9. Giữ nguyên nhánh fallback, ngoại lệ và side effects

Refactor theo subtype có thể làm thay đổi hành vi mà chỉ nhìn kết quả ví dụ đơn giản không phát hiện:

- **Null:** Chuỗi if/else với instanceof trên null không vào nhánh nào; pattern switch cần case null nếu muốn xử lý có chủ đích như trước.
- **Thứ tự:** Nhánh kiểu cha đứng trước kiểu con có thể bao phủ kiểu con; thay thứ tự cần xét lại yêu cầu.
- **Guard:** Nếu một subtype có kiểm tra bổ sung, cần nhánh còn lại cho trường hợp guard false, không được để giá trị rơi sang nhánh không cùng nghĩa.
- **Tác dụng phụ:** Nếu mã cũ gọi accessor có side effect, ghi log, chỉnh trạng thái hoặc gọi service theo thứ tự, việc thay pattern có thể thay đổi thời điểm và số lần gọi. Đặc biệt record pattern sử dụng accessor để trích component; không nên tự mặc định mọi accessor do người viết ghi đè đều thuần túy.
- **Ngoại lệ:** Mã cũ có thể ném ngoại lệ ở một nhánh; đổi sang trả chuỗi mặc định hoặc nuốt lỗi là thay đổi nghiệp vụ.
- **Fall-through:** Chuỗi if/else có thể thiếu return ở một nhánh rồi chạy code chung phía sau. Switch expression yêu cầu mỗi nhánh tạo ra một giá trị, nên cần di chuyển code chung cẩn thận.
- **Thay đổi binary riêng lẻ:** Với sealed hierarchy, switch được biên dịch khi biết một tập subtype; triển khai class không đồng bộ có thể dẫn tới trường hợp runtime không có case tương ứng, ví dụ MatchException. Nên biên dịch và kiểm thử các thành phần phụ thuộc cùng nhau.

Đừng chuyển một block if/else đang gọi nhiều service, quản lý transaction hoặc có nhiều đường return/break thành một switch expression cực dài chỉ vì cú pháp mới. Có thể dùng switch statement hoặc các phương thức xử lý có tên, miễn là nhánh rõ và hành vi được kiểm tra.

## 10. Quy trình refactor có thể kiểm chứng

Một cách thực hiện thực tế cho dự án lớn:

1. **Chụp hành vi cũ:** Lập bảng từng subtype, điều kiện, kết quả, exception và side effects. Thêm test cho subtype đặc thù, null và giá trị biên.
2. **Bỏ cast lặp lại:** Đổi **instanceof T** rồi **(T) value** thành **instanceof T variable**; giữ nguyên thứ tự nhánh.
3. **Đánh giá chiều sâu hierarchy:** Xác định kiểu cha/con, trường hợp có thể bị nhánh rộng che, và kiểu mở rộng/non-sealed.
4. **Chọn biểu thức phân nhánh:** Nếu các nhánh chủ yếu trả kết quả, cân nhắc switch expression; nếu nhiều lệnh, dùng switch statement hoặc giữ if/else.
5. **Chuyển điều kiện:** Đưa guard đơn giản vào **when**, giữ nhánh fallback cho trường hợp guard false; không gom logic validation phức tạp vào một case dài.
6. **Quy định rõ null và default:** So sánh với hành vi cũ; với sealed hierarchy, ưu tiên không dùng default khi muốn compiler phát hiện subtype mới.
7. **Biên dịch và chạy test:** Kiểm tra exhaustiveness, dominance, hành vi trên các subtype, null, biên của guard và thứ tự side effects.
8. **Đánh giá khả năng đọc:** Nếu record pattern lồng quá sâu hoặc một case quá dài, tách phương thức theo hành vi.

Có thể tổ chức một bảng kiểm thử tối thiểu:

| Trường hợp | Mục đích |
| --- | --- |
| Mỗi subtype hợp lệ | Đảm bảo case đúng được chọn |
| Subtype với dữ liệu không hợp lệ | Đảm bảo guard false đi đúng fallback |
| Subtype con của kiểu cha chung | Kiểm tra thứ tự và dominance |
| Input null | Giữ hành vi cũ |
| Kiểu không được hỗ trợ, nếu selector cho phép | Kiểm tra default/nhánh lỗi |
| Thêm subtype mới vào sealed hierarchy | Kiểm tra compiler buộc cập nhật switch |
| Có log, exception hoặc side effects | Kiểm tra thứ tự và số lần thực thi |

## 11. Lỗi phổ biến và dấu hiệu nhận biết

**Sai 1: Chuyển cú pháp nhưng bỏ mất nhánh guard false.** Một case có when không đại diện cho toàn bộ subtype; phải có case còn lại nếu subtype đó có thể không đạt điều kiện.

**Sai 2: Quên null khi đổi instanceof chain sang switch.** Mã cũ thường rơi về nhánh cuối; mã mới có thể ném NullPointerException nếu không xử lý null.

**Sai 3: Đặt type pattern quá rộng lên trước.** Compiler có thể báo case phía sau bị dominated; khi thay thứ tự, cần xem có đang đổi hành vi cũ không.

**Sai 4: Dùng record pattern cho class không phải record.** Java không có deconstructor tùy ý áp dụng cho mọi class thông thường.

**Sai 5: Dùng default để bịt lỗi thiếu subtype.** Điều này có thể làm mất cảnh báo quan trọng khi sealed hierarchy phát triển.

**Sai 6: Tin rằng mọi component trích từ record đều non-null.** Mẫu không điều kiện có thể ràng buộc component tham chiếu null; guard phải tự kiểm tra trước khi gọi method.

**Sai 7: Kéo logic nghiệp vụ vào một switch khó đọc.** Khi điều kiện và side effects phức tạp, tách thành phương thức có tên thay vì ưu tiên ít dòng.

**Sai 8: Chỉ kiểm tra nhánh thông thường.** Những lỗi refactor hay xuất hiện ở giá trị biên, kiểu con bị che, null, exception và subtype thêm mới.

**Kết luận:** Đối với chuỗi **if-else theo subtype**, hãy bắt đầu bằng type pattern để bỏ cast, sau đó chuyển sang switch expression khi cấu trúc nhánh phù hợp. Record pattern giúp lấy dữ liệu record ngay tại case; sealed hierarchy giúp compiler xác nhận tính exhaustive. Giá trị thực của refactor là **mã rõ hơn với hành vi được bảo toàn và kiểm chứng**, không phải chỉ thay từ khóa.