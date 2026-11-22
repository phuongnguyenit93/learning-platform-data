# Pattern variable trong switch statement group

## 1. Statement group là gì và vì sao phạm vi biến quan trọng?

Trong Java, `switch` có thể được viết bằng các nhãn dạng mũi tên (`case ... ->`) hoặc dạng dấu hai chấm (`case ... :`). Với cú pháp **dấu hai chấm**, một nhãn `case` đứng trước một chuỗi câu lệnh; chuỗi câu lệnh liên tiếp gắn với nhãn đó gọi là *switch-labeled statement group* (thường viết gọn là *switch statement group*).

Từ **Java 21**, pattern matching trong `switch` là tính năng chính thức, không cần `--enable-preview`. Nhãn như:

~~~java
case String text:
    System.out.println(text.length());
    break;
~~~

vừa kiểm tra giá trị selector có khớp kiểu `String` hay không, vừa khai báo **pattern variable** `text`. Quy tắc quan trọng là biến này được đảm bảo đã khớp (*definitely matched*) trong **các câu lệnh thuộc đúng statement group của nhãn `case String text`**. Nó không tự nhiên tồn tại trong group khác hoặc sau toàn bộ `switch`.

Bài này giúp bạn:

- Phân biệt statement group dạng `case ... :` với switch rule dạng `case ... ->`.
- Xác định chính xác nơi được dùng pattern variable khai báo tại nhãn `case` hoặc bên trong câu lệnh thuộc group.
- Hiểu tác dụng của `when`, thứ tự nhãn, `break` và `return` đối với pattern variable.
- Giải thích vì sao Java **cấm fall-through vào một `case` khai báo pattern variable**.
- Phân biệt nhóm nhiều nhãn hằng hợp lệ với nhóm nhiều nhãn chứa khai báo pattern variable không hợp lệ.
- Kiểm soát `null`, `default`, các lỗi biên dịch và cách viết mã dễ bảo trì.

## 2. Hình dạng và ranh giới của switch-labeled statement group

Xét dạng dấu hai chấm:

~~~java
switch (value) {
    case String text:
        System.out.println(text.length());
        System.out.println(text.toUpperCase());
        break;

    case Number number:
        System.out.println(number.intValue());
        break;

    default:
        System.out.println("Other");
}
~~~

Đây là **đoạn minh họa đặt trong phương thức** với `Object value`; bản thân đoạn chưa phải một chương trình độc lập. Ba group là: các câu lệnh đi sau `case String text:` đến trước nhãn kế tiếp; các câu lệnh sau `case Number number:` đến trước `default:`; và các câu lệnh của `default:`.

Khi `value` khớp `String text`, Java gắn biến `text` kiểu `String`. Cả hai lời gọi `text.length()` và `text.toUpperCase()` đều thuộc group này, nên hợp lệ. Trong group `case Number number:`, biến `number` có kiểu `Number`; biến `text` từ group trước không còn ở trong phạm vi.

**Dấu hai chấm không tự kết thúc luồng thực thi.** Nếu group không kết thúc bằng `break`, `return`, `throw` hoặc một chuyển luồng khác, chương trình có thể tiếp tục thực thi các câu lệnh của group sau (*fall-through*). Quy tắc này vừa ảnh hưởng luồng thực thi, vừa tạo giới hạn an toàn cho pattern variable.

Để so sánh, switch rule dạng mũi tên:

~~~java
switch (value) {
    case String text -> System.out.println(text.length());
    case Number number -> System.out.println(number.intValue());
    default -> System.out.println("Other");
}
~~~

không fall-through sang rule kế tiếp. Pattern variable `text` chỉ dùng trong guard (nếu có) và phần code gắn với rule tương ứng. **Trọng tâm bài này là cú pháp dấu hai chấm và các statement group**.

## 3. Quy tắc phạm vi theo Java Language Specification

JLS Java 21 `6.3.2.6 quy định hai trường hợp trực tiếp liên quan đến switch statement group:

1. **Biến do nhãn switch giới thiệu:** Một pattern variable được giới thiệu bởi nhãn `case` sẽ *definitely matched* trong **tất cả các câu lệnh của switch-labeled statement group tương ứng**.
2. **Biến do câu lệnh trong group giới thiệu:** Nếu một câu lệnh `S` bên trong group giới thiệu pattern variable, biến ấy *definitely matched* ở những câu lệnh **theo sau `S` trong chính group đó**, khi quy tắc flow scoping của `S` đáp ứng.

JLS `6.3.3 cũng quy định pattern variable khai báo trong một case pattern có phạm vi tại biểu thức guard `when` của nhãn case đó. Guard chỉ được đánh giá sau khi pattern đã khớp.

Có thể ghi nhớ theo sơ đồ:

~~~text
switch (selector) {
    case String s when !s.isBlank():  <-- s dùng được trong when
        statementA(s);               <-- s dùng được
        statementB(s);               <-- s dùng được
        break;
    case Number n:                    <-- statement group MỚI
        statementC(n);               <-- n dùng được, s không có phạm vi
        break;
    default:                          <-- statement group MỚI
        statementD();                 <-- không có s hoặc n
}
                                      <-- ngoài switch không dùng s/n
~~~

`statementA(s)`, `statementB(s)` và các tên gọi ở sơ đồ chỉ minh họa vị trí; không phải API có sẵn. Cú pháp có `when` và pattern `switch` ổn định từ Java 21.

**Phạm vi (scope) là thuộc tính của mã nguồn được kiểm tra lúc biên dịch**. Việc runtime có thể đi qua nhãn tiếp theo không khiến biến của group trước được mở rộng phạm vi sang group sau.

## 4. Chương trình chạy được: khai báo và sử dụng pattern variable trong từng group

Lưu chương trình đầy đủ sau thành `SwitchGroupScopeDemo.java`:

~~~java
public class SwitchGroupScopeDemo {
    static String describe(Object value) {
        StringBuilder out = new StringBuilder();
        switch (value) {
            case null:
                out.append("NULL");
                break;
            case String s when s.isBlank():
                out.append("BLANK");
                break;
            case String s:
                int length = s.length();
                out.append("STRING length=").append(length);
                out.append(", upper=").append(s.toUpperCase());
                break;
            case Number n:
                out.append("NUMBER ").append(n.intValue());
                break;
            default:
                out.append("OTHER");
        }
        return out.toString();
    }

    static String laterStatements(Object value) {
        switch (value) {
            case CharSequence seq:
                if (!(seq instanceof String text)) {
                    return "NOT_STRING_CHAR_SEQUENCE";
                }
                String normalized = text.trim().toUpperCase();
                return "TEXT " + normalized;
            default:
                return "OTHER";
        }
    }

    static String fallthroughDefault(Object value) {
        StringBuilder out = new StringBuilder();
        switch (value) {
            case String s:
                out.append("S=").append(s).append("|");
            default:
                out.append("DEFAULT");
        }
        return out.toString();
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe("  "));
        System.out.println(describe("Java"));
        System.out.println(describe(12));
        System.out.println(describe(new Object()));
        System.out.println(laterStatements("  hi "));
        System.out.println(laterStatements(new StringBuilder("hi")));
        System.out.println(laterStatements(42));
        System.out.println(fallthroughDefault("x"));
        System.out.println(fallthroughDefault(42));
    }
}
~~~

Dùng JDK 21 trở lên, chạy từ thư mục chứa file:

~~~bash
javac --release 21 SwitchGroupScopeDemo.java
java SwitchGroupScopeDemo
~~~

Kết quả chính xác:

~~~text
NULL
BLANK
STRING length=4, upper=JAVA
NUMBER 12
OTHER
TEXT HI
NOT_STRING_CHAR_SEQUENCE
OTHER
S=x|DEFAULT
DEFAULT
~~~

Ba phương thức trong chương trình minh họa ba điểm riêng: phạm vi tại nhãn `case` có guard; phạm vi biến được giới thiệu bởi câu lệnh **nằm trong** group; và fall-through từ group có pattern sang `default`.

### 4.1. Hai case String có thể dùng lại cùng tên s

Trong `describe`:

~~~java
case String s when s.isBlank():
    out.append("BLANK");
    break;
case String s:
    int length = s.length();
    out.append("STRING length=").append(length);
    out.append(", upper=").append(s.toUpperCase());
    break;
~~~

Hai lần khai báo `s` nằm trong **hai statement group khác nhau**, nên chương trình Java 21 này biên dịch được. Mỗi `s` chỉ có phạm vi trong guard (nếu có) và group của chính nhãn tương ứng.

Ở group đầu, `s` được dùng trong `when s.isBlank()`. Khi guard trả về `true`, chương trình xử lý chuỗi blank và `break`. Nếu giá trị là `"Java"` thì pattern `String` khớp nhưng guard `isBlank()` sai; Java tiếp tục xét nhãn `case String s:` tiếp theo và chạy group đó.

**Thứ tự rất quan trọng:** nếu đặt `case String s:` không có guard lên trước, nó sẽ bao trùm trường hợp `String` có guard phía sau, dẫn tới lỗi *dominated case*. Đặt nhãn có điều kiện cụ thể trước nhãn chung.

### 4.2. Pattern variable có kiểu xác định trong các câu lệnh của group

Ở `case String s:`, biểu thức `s.length()` và `s.toUpperCase()` đều hợp lệ: `s` có kiểu tĩnh `String` vì pattern đã được khớp. Ở `case Number n:`, `n` có kiểu `Number` và dùng được `n.intValue()`. Java không chuyển kiểu của `n` thành `Integer` chỉ vì đầu vào minh họa là `12`.

Tương tự, `default` không giới thiệu pattern variable nào. Nếu selector không khớp các nhãn trước, group này chạy và trả về `OTHER`.

## 5. Pattern variable được giới thiệu bởi câu lệnh trong group

Một case pattern có thể tạo biến của riêng nó; các câu lệnh **bên trong group** còn có thể giới thiệu một biến pattern mới nhờ `instanceof` và flow scoping.

Phần sau được lấy từ phương thức `laterStatements` đã chạy thành công:

~~~java
case CharSequence seq:
    if (!(seq instanceof String text)) {
        return "NOT_STRING_CHAR_SEQUENCE";
    }
    String normalized = text.trim().toUpperCase();
    return "TEXT " + normalized;
~~~

Luồng lập luận:

1. `case CharSequence seq:` chỉ được chọn khi selector là một `CharSequence` không null, nên `seq` dùng được trong group.
2. `!(seq instanceof String text)` đúng nếu `seq` không phải `String`. Khi đó phương thức `return` ngay.
3. Nếu chương trình đi tới dòng khai báo `normalized` thì nhánh không khớp đã thoát. Đường còn lại **bắt buộc đã khớp `String text`**, do đó `text` dùng được trong các câu lệnh tiếp theo thuộc cùng group.
4. Với `new StringBuilder("hi")`, pattern `CharSequence seq` khớp nhưng `String text` không khớp nên trả về `NOT_STRING_CHAR_SEQUENCE`. Với `"  hi "`, kết quả là `TEXT HI`.

**Đừng nhầm** với việc mọi biến khai báo trong câu lệnh `if` đều có phạm vi ở phía dưới. Điều kiện thoát sớm (`return` ở nhánh không khớp) mới là bằng chứng cho phép `text` xuất hiện ở các câu lệnh tiếp theo.

Nếu group kết thúc và đi sang nhãn `case` khác, cả biến `seq` từ nhãn và biến `text` được giới thiệu bên trong group đều không tự được dùng trong group kế tiếp.

## 6. Fall-through: có thể chạy qua nhãn khác nhưng không mang theo phạm vi pattern variable

Dạng dấu hai chấm của `switch` có *fall-through* truyền thống: nếu code trong một group kết thúc bình thường, luồng thực thi sẽ tiếp tục vào các câu lệnh sau nhãn kế tiếp.

Ví dụ hợp lệ đã kiểm thử:

~~~java
static String fallthroughDefault(Object value) {
    StringBuilder out = new StringBuilder();
    switch (value) {
        case String s:
            out.append("S=").append(s).append("|");
        default:
            out.append("DEFAULT");
    }
    return out.toString();
}
~~~

Nếu đầu vào là `"x"`, kết quả là `S=x|DEFAULT`: Java vào `case String s`, thực thi `append` rồi tiếp tục chạy câu lệnh trong `default` vì không có `break`. Nếu đầu vào là `42` thì đi thẳng vào `default`, kết quả là `DEFAULT`.

Trong group `default`, biến `s` **không nằm trong phạm vi**. Đoạn mã sau **cố ý không biên dịch**:

~~~java
static void invalid(Object value) {
    switch (value) {
        case String s:
            System.out.println(s);
        default:
            System.out.println(s); // LỖI: s không thuộc group default
    }
}
~~~

Điều này có thể gây bất ngờ: khi runtime đi từ nhãn `String` xuống `default`, đối tượng `String` thực tế vẫn có đó, nhưng **scope của tên `s` vẫn kết thúc tại ranh giới group**. Java không phân tích phạm vi theo một lần chạy cụ thể.

Khi có pattern variable, nên kết thúc các group bằng `break`, `return` hoặc `throw` rõ ràng để người đọc dễ kiểm soát luồng; cú pháp mũi tên `->` cũng là lựa chọn phù hợp khi không cần fall-through.

## 7. Java cấm fall-through VÀO một case khai báo pattern variable

Một loại lỗi nguy hiểm hơn là cho phép chương trình đi từ group trước vào group sau có nhãn khai báo biến pattern. Khi đó code trong group sau có thể đọc một biến chưa được khởi tạo từ mẫu.

Đoạn sau **cố ý không biên dịch** trên Java 21:

~~~java
static void invalid(Object value) {
    switch (value) {
        case String s:
            System.out.println("S:" + s); // thiếu break
        case Integer i:
            System.out.println("I:" + i);
            break;
        default:
            break;
    }
}
~~~

Nếu cho phép, đầu vào `"Java"` sẽ khớp `case String s` và có thể chạy tiếp vào `case Integer i`, trong khi mẫu `Integer i` **chưa từng khớp**. Vì vậy `javac --release 21` báo lỗi dạng:

~~~text
error: illegal fall-through to a pattern
(the previous case label is missing a break)
~~~

Java đặt hạn chế tại vị trí **nhãn pattern**: trong switch block dạng statement group, nếu câu lệnh ngay trước nhãn `case` khai báo pattern variable **có thể hoàn thành bình thường**, không được cho nhãn đó trở thành đích rơi vào từ group trước.

Cách sửa có chủ đích:

~~~java
case String s:
    System.out.println("S:" + s);
    break;
case Integer i:
    System.out.println("I:" + i);
    break;
~~~

Đây là hai group tách biệt; đầu vào kiểu `String` không thể vô tình thực thi code chỉ dành cho `Integer`. Đặt dấu ngoặc nhọn quanh các câu lệnh một cách tùy tiện không thay thế được việc kết thúc luồng hợp lệ trước nhãn pattern tiếp theo.

Điều cần phân biệt:

- **Fall-through từ group pattern vào `default` không khai báo biến:** có thể hợp lệ như ví dụ phần 6; nhưng `s` không có phạm vi ở `default`.
- **Fall-through vào một nhãn `case Integer i` khai báo pattern variable:** bị chặn bằng lỗi biên dịch vì `i` có thể chưa được khởi tạo.

## 8. Một statement group có nhiều nhãn: trường hợp nào hợp lệ?

Java cho phép nhiều nhãn `case` dẫn tới cùng các câu lệnh trong mô hình thông thường, miễn các nhãn tuân thủ quy tắc của ngôn ngữ.

Chương trình đầy đủ dưới đây chạy được trên Java 21:

~~~java
public class SwitchGroupConstantsDemo {
    static String status(String value) {
        switch (value) {
            case "on":
            case "enable":
                return "ENABLED";
            case "off", "disable":
                return "DISABLED";
            case null, default:
                return "UNKNOWN";
        }
    }

    public static void main(String[] args) {
        System.out.println(status("on"));
        System.out.println(status("enable"));
        System.out.println(status("disable"));
        System.out.println(status(null));
        System.out.println(status("maybe"));
    }
}
~~~

~~~bash
javac --release 21 SwitchGroupConstantsDemo.java
java SwitchGroupConstantsDemo
~~~

Kết quả:

~~~text
ENABLED
ENABLED
DISABLED
UNKNOWN
UNKNOWN
~~~

Nhãn `"on"` và `"enable"` cùng dẫn tới một group mà **không có biến pattern nào cần khởi tạo**. Cú pháp `case "off", "disable":` cũng chỉ gộp các nhãn hằng, và `case null, default:` là tổ hợp đặc biệt hợp lệ trong Java 21.

**Ngược lại, khi statement group có nhãn case pattern khai báo một hoặc nhiều biến, Java không cho một câu lệnh được gắn với hơn một switch label.** Các kiểu viết dưới đây **cố ý không biên dịch**:

~~~java
// Ví dụ A: nhiều nhãn liên tiếp cùng dẫn đến một group
switch (value) {
    case String s:
    case Integer i:
        System.out.println("mixed");
        break;
    default:
        break;
}
~~~

~~~java
// Ví dụ B: nhiều case pattern trong cùng một case label
switch (value) {
    case String s, Integer i:
        System.out.println("mixed");
        break;
    default:
        break;
}
~~~

Với `Object value`, cả hai đoạn trên đều bị `javac --release 21` từ chối, với lỗi thuộc nhóm `illegal fall-through from a pattern` / `illegal fall-through to a pattern`.

Lý do: nếu selector khớp `String` nhưng không khớp `Integer` (hoặc ngược lại), một trong những biến `s`, `i` sẽ không được khởi tạo, trong khi các câu lệnh chung không thể coi mọi biến đã *definitely matched*.

**Cách giải quyết:** tách mỗi pattern ra một group riêng và xử lý trong phạm vi tương ứng. Nếu thật sự muốn dùng chung thuật toán, hãy chuyển phần xử lý chung thành phương thức nhận tham số đã được chuyển về một kiểu chung hợp lệ:

~~~java
case String s:
    System.out.println(describeValue(s));
    break;
case Integer i:
    System.out.println(describeValue(i));
    break;
~~~

`describeValue(...)` ở đây là **phương thức minh họa phải tự định nghĩa**; đoạn trích không phải một chương trình độc lập. Cách tổ chức này chia sẻ logic mà không làm sai phạm vi pattern variable.

## 9. Group tiếp theo và ngoài switch không dùng được biến của group trước

Ngay cả khi mỗi group được kết thúc rõ ràng bằng `break`, pattern variable vẫn chỉ thuộc group khai báo nó.

Ví dụ **cố ý không biên dịch**:

~~~java
static void invalid(Object value) {
    switch (value) {
        case String s:
            System.out.println(s);
            break;
        case Number n:
            System.out.println(s); // LỖI: s không tồn tại ở group này
            break;
        default:
            break;
    }
}
~~~

`s` được khai báo và đảm bảo khớp ở group `String`; group `Number` không có `s`. Vì vậy compiler báo `cannot find symbol: variable s`.

Ngoài toàn bộ switch cũng tương tự:

~~~java
static int invalid(Object value) {
    switch (value) {
        case String s:
            System.out.println(s);
            break;
        default:
            break;
    }
    return s.length(); // LỖI: s không có scope sau switch
}
~~~

Nếu cần sử dụng kết quả ở bên ngoài `switch`, gán nó vào một biến **được khai báo trước switch** rồi chỉ đọc biến đó khi đã có giá trị hợp lệ, hoặc tách thành phương thức trả về kết quả như `describe` trong chương trình đầy đủ. Điều này tách rõ phạm vi pattern variable khỏi phạm vi biến kết quả thông thường.

Ngược lại, cùng **một tên** như `s` có thể xuất hiện trong hai group độc lập (ví dụ hai `case String s` có guard khác nhau ở phần 4). Tên giống nhau không có nghĩa đó là một biến có phạm vi xuyên qua các group.

## 10. Scope của guard when, null và các nhãn khác

### Guard được đọc sau khi mẫu khớp

Trong nhãn:

~~~java
case String s when s.length() > 3:
    System.out.println(s.toUpperCase());
    break;
~~~

`s` dùng được ngay trong `when`; guard chỉ chạy khi pattern `String s` khớp. Nếu guard không thỏa, nhãn này không được chọn và Java xem xét các nhãn tiếp theo.

Đặt pattern có guard cụ thể **trước** pattern không có guard bao quát. Ví dụ, `case String s:` đứng trước `case String s when s.length() > 3:` sẽ khiến nhãn thứ hai bị *dominated*, gây lỗi biên dịch.

### Null cần nhánh riêng

Trong `switch (value)` với selector kiểu tham chiếu, `case String s` không khớp `null`. Bạn có thể dùng `case null:` như `describe` trong ví dụ chính, hoặc `case null, default:` khi muốn gộp hai trường hợp không có pattern variable như `SwitchGroupConstantsDemo`.

Tổ hợp sau **cố ý không biên dịch** trong Java 21:

~~~java
case null, String s:
    System.out.println(s);
    break;
~~~

Đây là *invalid case label combination*: không thể gộp `null` với type pattern khai báo `s` như vậy. `null` không tạo một đối tượng `String` để gắn vào `s`.

Nếu switch trên tham chiếu `null` mà không có nhãn xử lý `null` phù hợp, Java có thể ném `NullPointerException` trước khi chạy các group. `default` riêng lẻ không tự xử lý `null` trong pattern switch.

### Phiên bản Java

- `instanceof` type pattern đã ổn định từ Java 16 và dùng được trong Java 17.
- `case String s:` trong pattern matching for `switch` chỉ ổn định từ **Java 21**. Trong Java 17, tính năng pattern `switch` vẫn thuộc giai đoạn preview và không có đầy đủ cùng hợp đồng ngôn ngữ như Java 21.
- Tất cả chương trình đầy đủ trong bài được kiểm tra bằng `javac --release 21`, không cần `--enable-preview`. Không chạy trực tiếp những ví dụ Java 21 bằng cấu hình `--release 17`.

## 11. So sánh nhanh colon-form và arrow-form

| Tiêu chí | Switch statement group `case ... :` | Switch rule `case ... ->` |
| --- | --- | --- |
| Pattern variable được dùng ở đâu? | Các câu lệnh trong **group của nhãn**; guard nếu có | Guard và biểu thức/khối/`throw` của rule |
| Có thể thực thi tiếp code thuộc nhãn khác? | Có thể *fall-through* nếu không chặn luồng; nhưng Java cấm vào nhãn khai báo pattern variable theo điều kiện ở phần 7 | Không fall-through |
| Có cần `break`? | Thường cần nếu không muốn fall-through; `return`/`throw` cũng có thể kết thúc luồng | Không cần `break` để chặn fall-through |
| Nhiều nhãn chung code? | Hợp lệ trong những trường hợp như nhiều nhãn hằng; không được dùng nhiều nhãn khi group có nhãn khai báo pattern variable | Có quy tắc kết hợp nhãn riêng; tránh ghép mẫu khai báo biến khác nhau |
| Lúc nào nên dùng? | Khi cần phong cách statement truyền thống hoặc nhiều câu lệnh với điều khiển luồng rõ ràng | Thường dễ đọc hơn khi chỉ phân nhánh, không cần fall-through |

Điểm cần nhớ là **pattern variable phải được khởi tạo chắc chắn ở mọi đường có thể đi tới vị trí sử dụng**, nên Java không cho phép đi tắt vào statement group có khai báo biến qua một nhãn khác.

## 12. Lỗi thường gặp và cách tránh

1. **Quên `break` trước `case` khai báo pattern variable.** Có thể dẫn đến lỗi `illegal fall-through to a pattern`; kết thúc group trước bằng `break`, `return` hoặc `throw`.
2. **Tưởng biến từ group trước có thể dùng tại `default` vì runtime đã rơi xuống đó.** Scope kết thúc tại group; đọc biến ngoài scope sẽ bị từ chối.
3. **Gộp nhiều case pattern có biến khác nhau vào chung group.** Java cấm vì các biến không thể được khởi tạo chắc chắn từ tất cả nhãn.
4. **Đặt case bao quát trước case có guard.** Nhãn cụ thể có thể bị *dominated*.
5. **Đọc biến ở group khác hoặc sau switch.** Hãy trả về kết quả hoặc đưa dữ liệu ra biến kết quả có phạm vi phù hợp.
6. **Cho rằng `when` kiểm tra kiểu trước pattern.** Guard chỉ được đánh giá sau khi pattern khớp; vì vậy biến pattern mới an toàn để dùng trong guard.
7. **Lẫn cú pháp `:` và `->`.** Switch rule mũi tên không fall-through, còn statement group dấu hai chấm có hành vi rơi xuống và các hạn chế an toàn tương ứng.
8. **Quên xử lý `null`.** Type pattern không khớp null; quyết định rõ `case null` hoặc xử lý null trước switch nếu cần.
9. **Dùng JDK không đúng.** Biên dịch bằng Java 21+ để có pattern `switch` ổn định.
10. **Nhìn thấy cùng tên `s` ở hai group và tưởng đó là một biến duy nhất.** Các khai báo có scope khác nhau, dù tên giống nhau.

## 13. Bài tập tự kiểm tra

**Bài 1 — Phạm vi trong group**

Cho `Object value = "Java";`:

~~~java
switch (value) {
    case String s:
        System.out.println(s.length());
        System.out.println(s.toUpperCase());
        break;
    default:
        System.out.println("Other");
}
~~~

Hai lời gọi `s` có hợp lệ không? In ra gì?

**Đáp án:** Cả hai hợp lệ vì cùng thuộc group của `case String s`. In `4` và `JAVA` trên hai dòng.

**Bài 2 — Thiếu break**

Cho code:

~~~java
switch (value) {
    case String s:
        System.out.println(s);
    case Integer n:
        System.out.println(n);
        break;
    default:
        break;
}
~~~

Vì sao không biên dịch?

**Đáp án:** Group đầu có thể hoàn thành bình thường và rơi vào nhãn khai báo `Integer n`, mặc dù giá trị thực tế có thể không khớp `Integer`. Java cấm `illegal fall-through to a pattern`. Thêm `break` sau `println(s)`.

**Bài 3 — Scope từ câu lệnh bên trong group**

Trong `case CharSequence seq:`, sau câu lệnh:

~~~java
if (!(seq instanceof String s)) {
    return "not string";
}
~~~

có được dùng `s.trim()` ở câu lệnh kế tiếp trong cùng group không?

**Đáp án:** Được. Nếu phép kiểm tra không khớp, phương thức đã `return`; đường còn lại chắc chắn khớp `String s`. Điều này không cho phép dùng `s` ở group khác.

**Bài 4 — Gộp nhãn**

Vì sao có thể viết:

~~~java
case "on":
case "enable":
    return "enabled";
~~~

nhưng không thể dùng `case String s:` và `case Integer i:` cùng dẫn vào một statement group?

**Đáp án:** Hai nhãn hằng không giới thiệu pattern variable. Với hai nhãn pattern, nhảy vào từ một nhãn sẽ không đảm bảo các biến được khai báo ở nhãn kia đã có giá trị; Java cấm cách ghép đó.

**Bài 5 — Fall-through sang default**

Vì sao `fallthroughDefault("x")` ở chương trình chính trả về `S=x|DEFAULT` nhưng không thể đọc `s` bên trong `default`?

**Đáp án:** Runtime tiếp tục thực thi câu lệnh sau nhãn mới khi thiếu `break`, nhưng phạm vi tên `s` chỉ thuộc statement group của `case String s`. *Flow of execution* và *lexical/flow scope* là hai vấn đề khác nhau.

## 14. Checklist khi review switch statement group

Trước khi hoàn tất một switch dạng `case ... :` có pattern variable, hãy kiểm tra:

1. Mỗi biến pattern được khai báo ở nhãn nào, có guard `when` không?
2. Vị trí đang dùng biến có nằm **trong đúng group tương ứng**, hoặc ở các câu lệnh tiếp theo của cùng group sau một phép kiểm tra pattern chắc chắn thành công, không?
3. Mỗi group có được kết thúc rõ ràng để tránh fall-through không mong muốn không?
4. Có câu lệnh nào có thể rơi từ group trước vào nhãn khai báo pattern variable không?
5. Có nhãn pattern khai báo biến nào đang bị ghép với nhãn khác trong cùng group không?
6. Các case có bị một pattern bao quát đứng trước *dominated* không?
7. `null` và các kiểu dữ liệu không khớp đã có đường xử lý phù hợp chưa?
8. Mã được biên dịch với Java 21+ nếu dùng pattern trong `switch` chưa?

**Ghi nhớ:** một nhãn `case` khai báo pattern variable tạo ra các biến đã được khớp cho **statement group của chính nhãn đó**. Java duy trì tính an toàn bằng cách giới hạn phạm vi biến và cấm các đường fall-through hoặc nhóm nhãn có thể khiến biến pattern chưa được gắn giá trị.

### Đặc tả và tài liệu tham khảo

- Java SE 21 JLS `6.3.2.6 — Scope for Pattern Variables in `switch` Statements: https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.2.6
- Java SE 21 JLS `6.3.3 — Scope for Pattern Variables in `case` Labels: https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3
- Java SE 21 JLS `14.11.1 — Switch Blocks, dominance và hạn chế fall-through: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1
- Oracle Java 21 — Pattern Matching for switch Expressions and Statements: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
