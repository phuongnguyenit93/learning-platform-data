# Đọc thứ tự các case từ trên xuống trong Java switch pattern

## 1. Cách đọc một switch có pattern

Trong Java, **switch** nhận một biểu thức lựa chọn (**selector**) rồi xác định nhãn **case** áp dụng cho giá trị của biểu thức đó. Với **pattern matching for switch** (tính năng chính thức từ **Java 21**), một nhãn có thể kiểm tra **kiểu**, gắn **pattern variable** và thêm điều kiện phụ bằng **when**.

Để đọc một switch pattern, hãy trả lời lần lượt:

1. **Selector có giá trị gì và có phải null không?** Biểu thức selector được tính để có một giá trị dùng cho việc lựa chọn nhánh.
2. **Case nào có thể áp dụng?** Với một giá trị khác null, xét các nhãn case theo thứ tự trong khối switch; type pattern phải khớp giá trị, và guard **when** (nếu có) phải đúng.
3. **Nhãn phù hợp đầu tiên là nhãn nào?** Đó là nhãn được chọn; các nhãn phù hợp phía sau không tiếp tục được chọn.
4. **Nhãn được chọn thực thi ra sao?** Nhánh dùng **->** thực hiện phần bên phải mà không rơi qua nhánh sau; nhánh kiểu dấu hai chấm có thể có **fall-through** nếu không kết thúc đúng cách.

Ví dụ Java 21:

~~~java
static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case String text when text.isBlank() -> "blank";
        case String text -> "text:" + text.strip();
        case Integer number -> "integer:" + number;
        default -> "other";
    };
}
~~~

Khi **value = "   "**, chương trình chọn **case String text when text.isBlank()**. Với **value = " Java "**, case có guard không thỏa nên tiếp tục đến **case String text**. Với **value = 7** (được boxing thành **Integer** khi đi qua tham số **Object**), case **Integer** áp dụng. Với **null**, **case null** xử lý riêng.

**Phạm vi phiên bản:** Java 17 đã hỗ trợ **instanceof String text**, nhưng **case String text** và guard **when** trong switch chỉ là cú pháp chính thức từ **Java 21**. Các ví dụ switch pattern chạy với JDK 21+, không phải chương trình Java 17.

## 2. Nhãn nào được xem là khớp?

Một nhãn case có thể là hằng số, type pattern, pattern có **when**, hoặc nhãn xử lý **null**/**default** phù hợp với selector. Cách kiểm tra phụ thuộc loại nhãn:

| Nhãn | Điều kiện áp dụng | Điều cần đọc |
| --- | --- | --- |
| **case "start"** (selector String) | Chuỗi bằng hằng số **"start"** | Đây là so khớp giá trị |
| **case String text** | Giá trị khác null và là **String** | Biến **text** có kiểu tĩnh **String** |
| **case String text when text.isBlank()** | Khớp **String** và guard đúng | Guard chỉ chạy sau khi pattern khớp |
| **case Number number** | Giá trị là một **Number** | Có thể bao gồm **Integer**, **Double**, ... |
| **case null** | Giá trị selector là **null** | Tách riêng trường hợp null |
| **default** | Không có nhãn thích hợp khác | Nhánh dự phòng cho giá trị không được phân loại |

Với selector **khác null**, đặc tả Java 21 mô tả việc tìm **nhãn case đầu tiên áp dụng**. Đối với **null**, quy tắc xử lý riêng xét **case null**. Trong những switch tham chiếu như các ví dụ ở đây, nếu thiếu nhãn xử lý null, **switch(null)** có thể ném **NullPointerException**; đừng mặc định **default** là một nhánh thay cho **case null**.

**Độ ưu tiên không tự suy ra từ kiểu “mạnh” hay “yếu”.** Mã nguồn và quy tắc dominance quyết định thứ tự hợp lệ. Compiler ngăn nhiều nhãn không thể đến được, nhưng người viết vẫn phải đặt guard có ý nghĩa nghiệp vụ theo thứ tự mong muốn.

## 3. Đọc case theo thứ tự bằng ví dụ Java 21 đầy đủ

Lưu mã sau thành **CaseOrderDemo.java**:

~~~java
public class CaseOrderDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String text when text.isBlank() -> "BLANK";
            case String text when text.length() >= 5 ->
                    "LONG:" + text.strip();
            case String text -> "SHORT:" + text;
            case Integer number when number >= 0 ->
                    "NONNEG:" + number;
            case Integer number -> "NEG:" + number;
            case Number number ->
                    "NUMBER:" + number.getClass().getSimpleName();
            case CharSequence chars -> "SEQUENCE:" + chars.length();
            default ->
                    "OTHER:" + value.getClass().getSimpleName();
        };
    }

    static String lengthFirst(Object value) {
        return switch (value) {
            case String text when text.length() >= 3 -> "LENGTH";
            case String text when text.isBlank() -> "BLANK";
            case String text -> "OTHER_STRING";
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    static String blankFirst(Object value) {
        return switch (value) {
            case String text when text.isBlank() -> "BLANK";
            case String text when text.length() >= 3 -> "LENGTH";
            case String text -> "OTHER_STRING";
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
                null, "   ", " Java ", "hi", 7, -3, 2.5,
                new StringBuilder("abc"), new Object()
        };
        for (Object input : inputs) {
            System.out.println(classify(input));
        }

        System.out.println("length-first:" + lengthFirst("   "));
        System.out.println("blank-first:" + blankFirst("   "));
    }
}
~~~

Biên dịch và chạy bằng **JDK 21 trở lên**:

~~~bash
javac -encoding UTF-8 CaseOrderDemo.java
java CaseOrderDemo
~~~

Đầu ra:

~~~text
NULL
BLANK
LONG:Java
SHORT:hi
NONNEG:7
NEG:-3
NUMBER:Double
SEQUENCE:3
OTHER:Object
length-first:LENGTH
blank-first:BLANK
~~~

Diễn giải **classify** theo thứ tự:

1. **null** được **case null** nhận diện. Không có type pattern nào cần kiểm tra.
2. Chuỗi gồm ba khoảng trắng khớp **String**, guard **isBlank()** đúng nên nhận **BLANK**. Không xét nhánh **length() >= 5** dù cùng là String.
3. **" Java "** khớp **String**, guard blank sai; độ dài gốc là **6**, nên case **length() >= 5** đúng. Sau đó **strip()** tạo **"Java"**, cho kết quả **LONG:Java**.
4. **"hi"** không blank và có độ dài nhỏ hơn 5, vì vậy đi tới **case String text** không có guard, trả về **SHORT:hi**.
5. **7** và **-3** là **Integer**. Case guard **number >= 0** nhận **7**, còn case **Integer** kế tiếp nhận **-3**. Cả hai được xét trước pattern rộng hơn **Number**.
6. **2.5** là **Double**: không khớp hai case **Integer** nhưng là **Number**, nên trả về **NUMBER:Double**.
7. **StringBuilder("abc")** không phải **String**, **Integer** hay **Number**, nhưng có triển khai **CharSequence**, nên trả về độ dài **SEQUENCE:3**.
8. Một đối tượng **Object** thông thường không khớp các pattern liệt kê, nên vào **default**.

Bảng truy vết này giúp tách **thứ tự kiểm tra nhãn** khỏi **thứ tự chạy nội dung nhánh**. Với mũi tên **->**, nhánh đã được chọn kết thúc phần xử lý switch của nhánh đó; không tự chạy các case bên dưới.

## 4. Nhiều guard có thể cùng đúng: case ở trên thắng

Hai phương thức **lengthFirst** và **blankFirst** trong chương trình chạy đều nhận đầu vào **"   "** (ba khoảng trắng). Giá trị này thỏa đồng thời:

- **text.length() >= 3**: đúng, vì có ba ký tự khoảng trắng.
- **text.isBlank()**: đúng, vì toàn bộ ký tự là khoảng trắng.

Trong **lengthFirst**, case độ dài xuất hiện trước nên kết quả là **LENGTH**; guard **isBlank()** ở phía sau không được chọn. Trong **blankFirst**, case blank đứng trước nên kết quả là **BLANK**.

Điểm đáng chú ý: cả hai thứ tự đều **biên dịch hợp lệ trên Java 21**. Compiler không thể xem mọi điều kiện nghiệp vụ trong **when** như những tập giá trị có quan hệ bao hàm dễ kiểm chứng. Vì vậy, thứ tự hai guard có thể làm thay đổi kết quả **mà không báo lỗi compile time**.

Quy tắc thực hành: viết case có điều kiện **ưu tiên cao nhất** trước, tiếp theo là các trường hợp ít đặc biệt hơn; cuối cùng là type pattern không guard cho phần còn lại của cùng kiểu.

Ví dụ phân loại chuỗi:

~~~java
// Các nhãn minh họa nằm trong switch Java 21:
case String text when text.isBlank() -> "blank";
case String text when text.length() >= 5 -> "long";
case String text -> "other string";
~~~

Nếu nghiệp vụ muốn **mọi chuỗi blank** được ưu tiên nhận diện trước chuỗi dài, thứ tự trên phù hợp. Trước khi đổi chỗ hai dòng đầu, hãy kiểm tra liệu có đầu vào cùng thỏa hai guard hay không.

## 5. Dominance: case tổng quát có thể che case cụ thể

**Dominance** là kiểm tra của compiler để phát hiện một nhãn case bị nhãn phía trước bao phủ hoàn toàn. Nếu không có giá trị nào có thể tới nhãn sau, mã Java 21 bị từ chối khi biên dịch.

Ví dụ **cố ý sai**:

~~~java
// Sai: CharSequence đứng trước và bao phủ mọi String.
static String wrong(Object value) {
    return switch (value) {
        case CharSequence chars -> "sequence";
        case String text -> "string"; // compile-time error
        default -> "other";
    };
}
~~~

**String** triển khai **CharSequence**. Mọi giá trị khớp **case String text** cũng khớp **case CharSequence chars** ở phía trên. Vì vậy, nhãn String bị dominance.

Cách sửa:

~~~java
// Mã minh họa Java 21+ trong một class hợp lệ.
static String corrected(Object value) {
    return switch (value) {
        case String text -> "string";
        case CharSequence chars -> "sequence";
        case null -> "null";
        default -> "other";
    };
}
~~~

**String** được nhận trước; các đối tượng **CharSequence** không phải String (ví dụ **StringBuilder**) được xử lý sau.

Một lỗi tương tự xảy ra khi đặt case **không guard** trước case cùng kiểu có **when**:

~~~java
// Sai: case String phía trước bao phủ case String có guard.
static String wrongGuard(Object value) {
    return switch (value) {
        case String text -> "any string";
        case String text when text.isBlank() -> "blank"; // compile-time error
        default -> "other";
    };
}
~~~

Cách đúng là đặt case cụ thể có guard trước:

~~~java
static String correctGuard(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "blank";
        case String text -> "other string";
        case null -> "null";
        default -> "other";
    };
}
~~~

Các phương thức trong những đoạn minh họa ở phần này không phải chương trình độc lập; chương trình chính có **main** là **CaseOrderDemo.java** ở phần 3.

**Phân biệt dominance với việc hai guard chồng lấn:** compiler có thể khẳng định **String** không guard bao phủ mọi trường hợp **String** có guard, nhưng không nhất thiết chứng minh được rằng hai điều kiện tùy ý trong **when** bao phủ nhau. Cùng biên dịch được không có nghĩa là hoán đổi hai guard mà không đổi hành vi.

## 6. Khi nào một guard được đánh giá?

Một case pattern có guard được xử lý theo hai bước:

1. Giá trị phải **khớp pattern** trước, ví dụ phải là **String** thì mới có biến **text** kiểu **String**.
2. Nếu khớp, Java mới đánh giá biểu thức **when**. Nếu guard là **true**, case được chọn. Nếu guard **false**, việc lựa chọn tiếp tục với nhãn phù hợp tiếp theo.

Điều này giúp dùng biến pattern an toàn ngay trong guard:

~~~java
// Mã minh họa nằm trong switch Java 21+:
case String text when !text.isBlank() && text.length() >= 3 ->
        "accepted:" + text;
~~~

Guard không gọi **text.isBlank()** cho đối tượng không phải String. Bên trong guard, toán tử **&&** vẫn đánh giá ngắn mạch: nếu **!text.isBlank()** sai, vế **text.length() >= 3** không cần chạy.

Nếu guard gọi phương thức ném ngoại lệ, việc chọn nhánh bị gián đoạn bởi ngoại lệ; **switch không tự coi một guard ném ngoại lệ là false** để chuyển sang case kế tiếp. Vì thế, đừng sử dụng guard có tác dụng phụ phức tạp hoặc phụ thuộc vào thay đổi trạng thái khó dự đoán.

Trong code cần debug, đọc mỗi case theo câu hỏi: **kiểu có khớp? → nếu có, when có đúng? → nếu cả hai đúng, dừng chọn nhánh**. Cách này chính xác hơn việc nhìn thấy chữ **case** rồi cho rằng mọi phần thân case sẽ được thực thi.

## 7. Thứ tự với case hằng số, case null và default

**Case hằng số** so khớp với giá trị cụ thể. Ví dụ sau sử dụng switch với selector **String** (JDK 21+):

~~~java
static String command(String value) {
    return switch (value) {
        case "start" -> "BEGIN";
        case "stop" -> "END";
        case null -> "NO_COMMAND";
        default -> "UNKNOWN";
    };
}
~~~

Đây là đoạn phương thức minh họa; các case **"start"** và **"stop"** là nhãn giá trị, không phải type pattern. Các hằng số **trùng nhau** trong cùng một switch là lỗi biên dịch; thứ tự dòng không khiến compiler chấp nhận nhãn trùng.

Với **null**, hãy đặt **case null** rõ ràng nếu đó là trạng thái đầu vào hợp lệ. Đặc tả có cách xác định nhãn null riêng, nên không nên diễn giải rằng **null** sẽ đi qua mọi type pattern từ trên xuống giống các đối tượng khác. **default** là dự phòng; nên đặt cuối khối switch để người đọc dễ theo dõi.

Lưu ý về **case Object obj** hoặc pattern tổng quát: các pattern rộng có thể khiến những nhãn về sau bị che hoặc tạo ra quy tắc chọn nhánh không mong muốn. Đừng dùng nhãn quá rộng trước khi đã xử lý hết trường hợp cụ thể.

## 8. Chọn một case khác với fall-through của switch kiểu cũ

Có hai giai đoạn riêng:

- **Selection:** xác định nhãn case được áp dụng.
- **Execution:** chạy những câu lệnh gắn với nhãn đó theo cú pháp switch đang sử dụng.

Trong cú pháp **->** hiện đại, không có việc tự động chạy tiếp phần thân case bên dưới. Với cú pháp **case ... :** truyền thống, sau khi chọn một nhãn, việc thực thi có thể **rơi xuyên (fall through)** sang những câu lệnh của case phía sau nếu thiếu **break**, **return**, **throw** hoặc điều khiển kết thúc phù hợp.

Ví dụ chạy được trên cả **Java 17**:

~~~java
public class ClassicFallThroughDemo {
    static String oldStyle(int value) {
        StringBuilder out = new StringBuilder();
        switch (value) {
            case 1:
                out.append("one");
            case 2:
                out.append("-two");
                break;
            default:
                out.append("-other");
        }
        return out.toString();
    }

    public static void main(String[] args) {
        System.out.println(oldStyle(1));
        System.out.println(oldStyle(2));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClassicFallThroughDemo.java
java ClassicFallThroughDemo
~~~

Đầu ra:

~~~text
one-two
-two
~~~

Khi **value = 1**, nhãn **case 1** được chọn. Vì không có **break**, chương trình tiếp tục chạy câu lệnh ở **case 2** mà **không kiểm tra lại** liệu số 1 có bằng số 2 hay không. Đây là **fall-through khi thực thi**, khác với việc tìm nhãn case đầu tiên phù hợp. Với **value = 2**, chỉ phần từ **case 2** đến **break** được chạy.

Khi viết pattern matching trong switch Java 21, ưu tiên nhánh **->** để tránh nhầm việc lựa chọn và việc rơi xuyên. Không nên áp dụng quy tắc “mỗi case dấu hai chấm tự dừng” vì đó là sai.

## 9. Exhaustiveness và sealed hierarchy

Nếu selector là một **sealed interface**, compiler có thể biết tập subtype được cho phép và kiểm tra switch expression đã đủ case cần thiết chưa.

Ví dụ minh họa Java 21+:

~~~java
sealed interface Result permits Success, Failure {}

record Success(String message) implements Result {}
record Failure(int code) implements Result {}

static String render(Result result) {
    return switch (result) {
        case Success success -> "OK:" + success.message();
        case Failure failure -> "ERROR:" + failure.code();
    };
}
~~~

Đoạn này cần được đặt trong một ngữ cảnh class/tệp nguồn hợp lệ; đây là ví dụ phương thức và kiểu, chưa phải chương trình có **main**. Tất cả subtype không-null đã được xử lý, nên không cần **default**. Nếu tập subtype được mở rộng, việc biên dịch lại có thể yêu cầu bổ sung case.

**Tính bao phủ không thay thế quy tắc thứ tự.** Nếu một subtype bị pattern tổng quát phía trên che, compiler vẫn có thể báo dominance; nếu thiếu một subtype bắt buộc, compiler có thể báo chưa exhaustive. Với đầu vào null, ví dụ trên không có **case null**, nên cần xử lý riêng nếu hợp đồng API cho phép null.

## 10. Checklist đọc code switch pattern khi review

Khi nhìn một switch dài, nên làm theo thứ tự:

1. Xác định kiểu tĩnh và các giá trị thực tế có thể có của **selector**. Đặc biệt kiểm tra liệu null có hợp lệ không.
2. Đọc từ trên xuống **các nhãn có pattern cụ thể và guard**. Đối với từng case, ghi chú điều kiện khớp kiểu và điều kiện **when**.
3. Xác định liệu các guard cùng kiểu có thể **chồng lấn**. Nếu có, case đứng trước quyết định mức ưu tiên nghiệp vụ.
4. Kiểm tra **dominance**: pattern tổng quát như **CharSequence** đặt trước **String**, hoặc case **String** không guard đặt trước **String ... when**, có thể làm code không biên dịch.
5. Tìm nhãn type pattern **không guard** xử lý phần còn lại và xem **default** có hợp lý không.
6. Kiểm tra **null** một cách tường minh; không gộp suy đoán của mình về null với thứ tự pattern cho đối tượng khác null.
7. Xem cú pháp nhánh là **->** hay dấu hai chấm; với dấu hai chấm, kiểm tra nguy cơ **fall-through**.
8. Nếu dùng **switch expression** trên sealed hierarchy, xác nhận compiler kiểm tra exhaustiveness và cân nhắc tránh default không cần thiết.
9. Chạy thử ít nhất một giá trị khớp case đầu, một giá trị bỏ qua guard đầu rồi khớp case sau, một giá trị có nhiều guard cùng đúng, một giá trị không khớp case cụ thể và null.
10. Biên dịch theo đúng phiên bản dự án: **Java 21+** cho switch pattern và **when**; **Java 17** dùng được pattern trong **instanceof** nhưng không dùng switch pattern chuẩn Java 21.

### Bài tập tự kiểm tra

**Tình huống A:** Có **case String s when s.length() > 2** trước **case String s when s.isBlank()**. Với **"   "**, nhánh đầu được chọn vì độ dài 3; muốn ưu tiên chuỗi blank thì đảo hai case.

**Tình huống B:** Có **case Number n** trước **case Integer i**. Kết quả? Compiler Java 21 báo nhãn Integer bị dominance, vì mọi Integer là Number. Đặt Integer trước Number.

**Tình huống C:** Có **case String s** trước **case String s when s.startsWith("ID-")**. Kết quả? Nhãn có guard phía sau không thể đến được; cần đặt case có guard trước.

**Tình huống D:** Một switch dùng **case 1:** rồi **case 2:** mà không có **break** ở case 1. Khi giá trị là 1, phần thân case 2 có thể vẫn chạy vì fall-through; điều này không có nghĩa selector đã khớp cả hai hằng số.

**Tình huống E:** Một **switch expression** trả về kết quả cho mọi subtype của sealed interface nhưng thiếu **case null**. Có tự nhận null không? Không được giả định như vậy; nếu null là đầu vào được hỗ trợ, hãy có nhánh xử lý thích hợp.

## 11. Tài liệu tham khảo

- [Java Language Specification 21, §14.11.1.2 — Determining which Switch Label Applies at Run Time](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2): cách chọn nhãn và đánh giá guard.
- [Java Language Specification 21, §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): dominance, tính hợp lệ nhãn và hành vi của switch.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): thiết kế pattern switch, null, khi nào dùng guard và thứ tự pattern.
- [Java Language Specification 21, §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): cách switch expression chọn nhánh và tạo giá trị.

**Kết luận:** Đọc switch pattern theo chiều từ trên xuống để tìm **nhãn đầu tiên áp dụng** cho một giá trị khác null, xét cả kiểu lẫn guard **when**. Các guard cùng đúng khiến **thứ tự case quyết định kết quả**; pattern rộng đặt sai chỗ có thể bị compiler báo **dominance**. Sau khi chọn nhãn, phải xem cú pháp **->** hay **:** để biết có nguy cơ **fall-through**. Xử lý **null** và **default** rõ ràng giúp nhánh được chọn đúng hợp đồng chương trình.