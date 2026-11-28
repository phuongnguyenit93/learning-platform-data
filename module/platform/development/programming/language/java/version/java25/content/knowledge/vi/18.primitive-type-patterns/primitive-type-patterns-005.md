# Phân tích tính bao phủ, thứ tự nhánh và nhánh không thể tiếp cận

## 1. Phạm vi và trạng thái của tính năng

**Primitive Types in Patterns, instanceof, and switch** mở rộng pattern matching để các kiểu nguyên thủy như byte, short, int, long, char, float, double và boolean có thể tham gia pattern. Nhờ đó, chương trình có thể kiểm tra giá trị, thử chuyển đổi an toàn và phân nhánh theo kiểu dữ liệu mà không phải viết chuỗi ép kiểu thủ công.

Cần phân biệt trạng thái theo JDK:

| Release | JEP | Trạng thái |
| --- | --- | --- |
| Java 23 | JEP 455 | Preview lần đầu |
| Java 24 | JEP 488 | Preview lần hai |
| **Java 25** | **JEP 507** | **Preview lần ba** |
| **Java 26** | **JEP 530** | **Preview lần bốn** |

Tại thời điểm biên soạn, tính năng vẫn là **preview** trong Java 26; chưa trở thành cú pháp Java ổn định. Java 25 có phiên bản preview thứ ba. Java 26 tiếp tục điều chỉnh quy tắc exact conversion và dominance, vì vậy code được chấp nhận ở Java 25 có thể bị từ chối khi biên dịch với preview Java 26. [JEP 507](https://openjdk.org/jeps/507) · [JEP 530](https://openjdk.org/jeps/530) · [Java Language Changes by Release](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-release.html)

Bài thuộc chương **Mẫu kiểu nguyên thủy** của module **JAVA_VERSION_JAVA25**, với đề bài trực tiếp **“Phân tích tính bao phủ, thứ tự nhánh và nhánh không thể tiếp cận”**. Mục tiêu là hiểu compiler xác định một switch có bao phủ đủ miền giá trị hay không, vì sao một nhánh bị nhánh trước chiếm hết, và cách sắp xếp pattern để mọi trường hợp cần xử lý đều có thể tới được.

### Sau bài này, bạn có thể

1. Giải thích pattern nguyên thủy và testing conversion.
2. Phân biệt chuyển đổi chính xác với chuyển đổi làm mất thông tin.
3. Xác định khi nào một switch expression hoặc enhanced switch statement là exhaustive.
4. Sắp xếp pattern hẹp và rộng theo thứ tự hợp lệ.
5. Nhận diện dominance và nhánh không thể tiếp cận ngay lúc biên dịch.
6. Hiểu ảnh hưởng của when, default, null và record patterns.
7. Phân biệt quy tắc preview Java 25 với thay đổi trong preview Java 26.

## 2. Pattern nguyên thủy hoạt động như thế nào?

Trong Java trước tính năng này, pattern type thường khai báo biến kiểu tham chiếu. Preview primitive patterns cho phép pattern khai báo biến kiểu nguyên thủy và cho phép instanceof/switch kiểm tra việc chuyển đổi giữa các kiểu nguyên thủy.

Ví dụ:

~~~java
int value = 42;

if (value instanceof byte small) {
    System.out.println("Giá trị nằm trong miền byte: " + small);
} else {
    System.out.println("Không thể biểu diễn chính xác bằng byte");
}
~~~

Với value bằng 42, phép chuyển đổi từ int sang byte chính xác nên pattern khớp. Nếu value bằng 1000, phép chuyển đổi làm mất thông tin nên pattern không khớp; Java không âm thầm cắt byte như một phép cast thông thường.

Điểm cốt lõi: pattern matching kiểm tra **có thể chuyển đổi chính xác hay không**, không đơn giản kiểm tra có tồn tại một phép cast cú pháp hay không.

## 3. Testing conversion và exactness

Một testing conversion là phép chuyển đổi được dùng khi so sánh giá trị với kiểu trong instanceof hoặc pattern switch. Phép chuyển đổi chỉ được xem là khớp khi kết quả không làm mất thông tin và không ném exception.

| Chuyển đổi | Ví dụ | Kết quả |
| --- | --- | --- |
| Widening chính xác | byte → int | Luôn chính xác |
| Narrowing chính xác theo giá trị | int 42 → byte | Chính xác |
| Narrowing mất miền giá trị | int 1000 → byte | Không chính xác |
| Widening có thể mất precision | int lớn → float | Có thể không chính xác |
| Unboxing từ Integer khác null | Integer → int | Có thể khớp |
| Unboxing từ Integer null | Integer → int | Không khớp |

Ví dụ với hai giá trị:

~~~java
static String byteCheck(int value) {
    if (value instanceof byte b) {
        return "byte: " + b;
    }
    return "ngoài miền byte";
}
~~~

- byteCheck(42) trả về byte: 42.
- byteCheck(1000) trả về ngoài miền byte.

Không thay pattern bằng (byte) value nếu mục đích là kiểm tra miền. Cast có thể làm mất thông tin nhưng vẫn trả về một giá trị; pattern chỉ khớp khi chuyển đổi chính xác.

### Các dạng mất thông tin

Một phép chuyển đổi có thể không chính xác do:

- Mất magnitude: giá trị sau chuyển đổi có độ lớn khác.
- Mất precision: mất các bit có nghĩa.
- Mất range: giá trị nằm ngoài miền biểu diễn của kiểu đích.
- Mất sign: giá trị đổi dấu, ví dụ chuyển char lớn sang short.

Với floating-point, cần đặc biệt chú ý việc int sang float, long sang float hoặc double có thể làm tròn. Không kết luận rằng widening luôn đồng nghĩa với exact.

## 4. Switch exhaustive nghĩa là gì?

Một switch là **exhaustive** khi tập các nhãn case không có guard đã bao phủ toàn bộ miền giá trị có thể có của selector, hoặc switch có nhãn default thích hợp.

Tính exhaustive quan trọng vì:

- switch expression phải có một kết quả cho mọi giá trị selector hợp lệ.
- Enhanced switch statement cũng phải exhaustive.
- Compiler có thể phát hiện thiếu nhánh ngay lúc biên dịch thay vì để chương trình bỏ qua trường hợp đó.

Một switch statement truyền thống chỉ dùng hằng số trên các selector kiểu cơ bản như int có thể không phải enhanced switch và vẫn giữ quy tắc tương thích cũ không bắt buộc exhaustive. Khi dùng pattern hoặc selector nguyên thủy mới, hãy áp dụng quy tắc exhaustive của enhanced switch.

### Bao phủ bằng pattern không guard

Với selector kiểu int, pattern int i bao phủ toàn bộ miền int. Pattern byte b chỉ bao phủ các giá trị int có thể chuyển chính xác sang byte.

~~~java
static String classify(int value) {
    return switch (value) {
        case byte b  -> "byte";
        case short s -> "short";
        case int i   -> "int";
    };
}
~~~

Switch trên exhaustive vì nhánh cuối case int i nhận mọi giá trị int còn lại. Hai nhánh trước xử lý các miền nhỏ hơn.

Nếu bỏ case int i, switch không exhaustive: còn nhiều giá trị int không thể chuyển chính xác sang short.

~~~java
static String incomplete(int value) {
    return switch (value) {
        case byte b  -> "byte";
        case short s -> "short";
        // Compile-time error: chưa bao phủ mọi giá trị int
    };
}
~~~

Có thể thêm default để bao phủ phần còn lại, nhưng khi selector là primitive và có pattern cùng kiểu rộng nhất, pattern đó thường diễn đạt ý định rõ hơn.

## 5. Bao phủ miền boolean

Miền boolean chỉ có hai giá trị. Một switch trên selector boolean có thể được bao phủ bằng hai hằng số true và false:

~~~java
static String describe(boolean enabled) {
    return switch (enabled) {
        case true  -> "enabled";
        case false -> "disabled";
    };
}
~~~

Hai nhánh này đã bao phủ mọi giá trị boolean; không cần default.

Có thể dùng pattern nguyên thủy boolean b để nhận toàn bộ miền selector, nhưng khi cần phân biệt hai trạng thái thì hai hằng số thể hiện ý định rõ ràng hơn.

Không thêm default thừa sau khi đã có cả true và false; đặc tả xem đó là trường hợp dư thừa và có thể báo lỗi biên dịch.

## 6. Bao phủ miền long, float và double

Primitive patterns cho phép dùng các kiểu này làm selector và pattern trong preview.

Ví dụ với long:

~~~java
static String classifyLong(long value) {
    return switch (value) {
        case int i  -> "biểu diễn chính xác bằng int";
        case long l -> "cần giữ kiểu long";
    };
}
~~~

Pattern int i chỉ khớp nếu giá trị long nằm trong miền int và chuyển đổi không mất thông tin. Pattern long l là pattern bao phủ phần còn lại, vì selector vốn đã có kiểu long.

Ví dụ với double:

~~~java
static String classifyDouble(double value) {
    return switch (value) {
        case float f  -> "biểu diễn chính xác bằng float";
        case double d -> "cần giữ kiểu double";
    };
}
~~~

double sang float có thể mất precision. Vì thế, case float f chỉ nhận các giá trị chuyển sang float chính xác. case double d bao phủ mọi giá trị double còn lại.

Đừng sắp xếp case double d trước case float f: pattern double nhận mọi giá trị selector double, nên nhánh float phía sau không còn giá trị nào có thể tới.

## 7. Thứ tự nhánh: từ miền hẹp đến miền rộng

Với selector int, các pattern byte, short và int có miền khớp lồng nhau:

- Mọi giá trị byte đều chuyển chính xác sang short.
- Mọi giá trị short đều chuyển chính xác sang int.
- Chiều ngược lại không đúng với toàn bộ miền.

Do đó, thứ tự phù hợp là **byte → short → int**.

~~~java
static String bucket(int value) {
    return switch (value) {
        case byte b  -> "nhóm byte";
        case short s -> "nhóm short";
        case int i   -> "nhóm int";
    };
}
~~~

Kết quả:

| value | Nhánh được chọn | Lý do |
| ---: | --- | --- |
| 12 | byte | Chuyển chính xác sang byte |
| 500 | short | Không thuộc byte, nhưng thuộc short |
| 100_000 | int | Không thể chuyển chính xác sang short |

Đây là cách đọc thứ tự nhánh theo miền giá trị, không chỉ theo tên kiểu. Nếu đổi thứ tự, một pattern rộng có thể chiếm toàn bộ giá trị mà pattern hẹp phía sau muốn nhận.

## 8. Dominance: khi một nhánh chiếm hết nhánh phía sau

Một switch label bị **dominated** khi mọi giá trị có thể khớp với nhãn đó đều đã khớp một nhãn không guard đứng trước. Đây là lỗi compile-time; compiler không chờ chạy chương trình mới phát hiện nhánh không thể tới.

Ví dụ với reference patterns:

~~~java
static String describe(Object value) {
    return switch (value) {
        case Object o -> "object";
        case String s -> "string"; // Compile-time error: dominated
    };
}
~~~

Mọi String không null cũng là Object, nên case Object o đứng trước đã nhận hết những giá trị mà case String s có thể nhận.

Ví dụ với primitive patterns:

~~~java
static String describe(int value) {
    return switch (value) {
        case int i  -> "int";
        case byte b -> "byte"; // Compile-time error: dominated
    };
}
~~~

case int i khớp với mọi giá trị selector int, bao gồm toàn bộ các giá trị có thể chuyển chính xác sang byte.

Một trường hợp khác:

~~~java
static String describe(int value) {
    return switch (value) {
        case short s -> "short";
        case byte b  -> "byte"; // Compile-time error: dominated
        case int i   -> "int";
    };
}
~~~

Mọi giá trị byte đều chuyển chính xác sang short. Vì vậy, nhánh short đứng trước đã nhận hết miền mà nhánh byte phía sau có thể nhận.

### Quy tắc tự kiểm tra

Trước khi thêm một pattern, hãy hỏi:

1. Mọi giá trị mà pattern mới có thể nhận có thuộc miền của một pattern trước đó không?
2. Pattern trước có không guard không?
3. Phép chuyển đổi từ kiểu selector/giá trị sang kiểu pattern có luôn chính xác cho toàn bộ miền của pattern mới không?

Nếu câu trả lời cho cả ba câu là có, nhánh mới bị dominated.

## 9. Pattern primitive và hằng số case

Hằng số và pattern có cách khớp khác nhau:

- case 42 so sánh với đúng giá trị hằng số.
- case byte b thử chuyển giá trị selector sang byte; nó có thể khớp với nhiều giá trị khác nhau nếu chuyển đổi chính xác.

Khi cần xử lý một giá trị đặc biệt, đặt hằng số trước pattern rộng:

~~~java
static String describe(int value) {
    return switch (value) {
        case 42       -> "giá trị đặc biệt";
        case byte b   -> "giá trị biểu diễn được bằng byte";
        case short s  -> "giá trị biểu diễn được bằng short";
        case int i    -> "giá trị int còn lại";
    };
}
~~~

Với value bằng 42, nhánh hằng số được chọn trước. Với các giá trị byte khác, nhánh byte xử lý. Các nhánh tiếp theo xử lý miền còn lại.

### Thay đổi đáng chú ý trong Java 26

JEP 530 bổ sung khái niệm **value-based unconditionally exact conversion** cho kiểm tra dominance. Compiler có thể biết một hằng số cụ thể chuyển đổi chính xác sang kiểu của pattern trước đó, dù chuyển đổi đó không chính xác với mọi giá trị của kiểu nguồn.

Ví dụ:

~~~java
static String classify(int value) {
    return switch (value) {
        case byte b -> "byte";
        case 42     -> "forty-two";
        case int i  -> "int";
    };
}
~~~

Với preview Java 26, case 42 bị xem là dominated: hằng số 42 chuyển chính xác sang byte, nên nó đã khớp nhánh case byte b đứng trước. Đây là ví dụ cho thấy một số switch từng được chấp nhận bởi quy tắc preview Java 25 có thể bị từ chối bởi quy tắc preview Java 26.

Khi muốn xử lý riêng 42, đặt hằng số trước pattern:

~~~java
static String classify(int value) {
    return switch (value) {
        case 42     -> "forty-two";
        case byte b -> "byte";
        case int i  -> "int";
    };
}
~~~

Không dựa vào việc compiler cũ chấp nhận một nhánh để cho rằng nhánh đó thực sự có thể chạy. Luôn biên dịch lại bằng đúng JDK preview mục tiêu.

## 10. Guard when và thứ tự của nhánh có điều kiện

Guard when bổ sung điều kiện sau khi pattern đã khớp. Guard giúp chia một miền kiểu thành các miền logic nhỏ hơn.

~~~java
static String classify(Integer value) {
    return switch (value) {
        case null -> "missing";
        case Integer n when n < 0 -> "negative";
        case Integer n when n == 0 -> "zero";
        case Integer n -> "positive";
    };
}
~~~

Thứ tự này hợp lệ vì:

- null được xử lý tường minh.
- Pattern có guard chỉ nhận các giá trị thỏa điều kiện.
- Pattern Integer n không guard đứng sau xử lý phần còn lại.

Một pattern có guard không phải lúc nào cũng dominate pattern không guard cùng kiểu, vì guard có thể trả về false. Do đó, cách đặt nhánh có điều kiện trước nhánh tổng quát là hợp lệ.

Ngược lại, nếu pattern không guard đứng trước, pattern có guard cùng kiểu ở sau sẽ bị dominated:

~~~java
switch (value) {
    case Integer n -> "integer";
    case Integer n when n < 0 -> "negative"; // Compile-time error
}
~~~

Integer n đầu tiên đã nhận mọi giá trị Integer không null; nhánh kiểm tra số âm phía sau không còn cơ hội chạy.

Một guard là constant expression true được xem như unguarded cho quy tắc này. Không dùng when true để né dominance.

### Guard không thay thế nhánh bao phủ

Các pattern có guard không hằng true không được dùng để chứng minh switch exhaustive. Guard có thể trả về false, nên phải có nhánh không guard hoặc default xử lý phần còn lại.

## 11. Record patterns có component kiểu nguyên thủy

Primitive patterns cũng có thể xuất hiện bên trong record patterns. Đây là cách kiểm tra dữ liệu có cấu trúc và đồng thời kiểm tra miền giá trị của component.

~~~java
record Measurement(int code, long ticks) {}

static String describe(Measurement measurement) {
    return switch (measurement) {
        case null -> "missing";
        case Measurement(byte code, int ticks) ->
                "compact: code=" + code + ", ticks=" + ticks;
        case Measurement(int code, long ticks) ->
                "general: code=" + code + ", ticks=" + ticks;
    };
}
~~~

Ở nhánh đầu:

- code phải chuyển chính xác từ int sang byte.
- ticks phải chuyển chính xác từ long sang int.
- Nếu một component không chuyển đổi chính xác, toàn bộ record pattern không khớp.

Nhánh sau dùng đúng kiểu component của record nên xử lý các trường hợp còn lại. case null cần thiết vì record pattern không khớp với null reference.

Không đặt Measurement(int code, long ticks) trước pattern hẹp hơn; record pattern rộng đó sẽ nhận hết các record có thể khớp với nhánh compact.

## 12. null, wrapper types và unboxing

Primitive selector không thể là null. Wrapper selector như Integer, Long, Boolean là reference type nên có thể chứa null.

Primitive pattern trên wrapper có thể cần unboxing. Nếu giá trị là null, phép unboxing không thành công và pattern nguyên thủy không khớp. Nếu ứng dụng cần xử lý null, viết nhánh rõ ràng:

~~~java
static String describe(Integer value) {
    return switch (value) {
        case null -> "null";
        case int n -> "integer: " + n;
    };
}
~~~

Không cho rằng case int n cũng nhận null chỉ vì selector có kiểu Integer. Pattern nguyên thủy không phải nhánh null.

Với wrapper type, cần kiểm tra miền bao phủ và null riêng. Một pattern bao phủ mọi giá trị không null chưa chắc đã bao phủ toàn bộ miền của reference selector.

## 13. default, case null và vị trí trong switch block

default là nhánh tổng quát, nhưng có quy tắc thứ tự khi kết hợp với pattern:

- default không được đặt trước case có pattern.
- default không được đặt trước case null.
- case null, default nếu dùng phải là nhãn cuối cùng.
- Với switch chỉ có các hằng số truyền thống, Java giữ một số cách viết default trước hằng số vì tương thích; đừng áp dụng ngoại lệ này cho pattern switch.

Cách viết dễ đọc:

~~~java
static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case String s -> "text";
        case Number n -> "number";
        default -> "other";
    };
}
~~~

Nếu dùng case null, default, nhãn này phải ở cuối và không có nhãn nào phía sau.

Đừng dùng default để che một pattern đã bị dominated. Compiler vẫn kiểm tra dominance; nhánh tổng quát không làm nhánh bị dominated trở nên hợp lệ.

## 14. Arrow rules và fall-through trong switch dùng dấu hai chấm

Các ví dụ mới nên ưu tiên switch rules dùng mũi tên. Mỗi rule thực hiện đúng nhánh đã chọn và không tự động fall-through sang nhánh kế tiếp.

Với dạng statement group dùng dấu hai chấm, luồng thực thi có thể đi tiếp sang nhóm kế tiếp nếu không có break, return hoặc cơ chế kết thúc khác. Khi một nhánh pattern khai báo biến, fall-through có thể khiến luồng đi tới statement mà biến pattern chưa được khởi tạo; compiler sẽ từ chối cấu trúc không an toàn.

Ví dụ nên dùng:

~~~java
switch (value) {
    case Integer n -> System.out.println("integer " + n);
    case Long n -> System.out.println("long " + n);
    default -> System.out.println("other");
}
~~~

Khi đọc code cũ dạng case với dấu hai chấm, kiểm tra cả dominance lẫn luồng fall-through. Đây là hai loại lỗi khác nhau: dominance nói một nhãn không thể là nhãn đầu tiên khớp; fall-through nói luồng có thể đi vào statement mà pattern variable chưa được khởi tạo.

## 15. Phân biệt lỗi dominance, lỗi exhaustiveness và lỗi tương thích

| Loại lỗi | Dấu hiệu | Cách sửa |
| --- | --- | --- |
| Dominated label | Pattern/hằng số phía sau đã bị nhánh trước bao phủ | Đưa nhánh cụ thể lên trước hoặc bỏ nhánh dư |
| Non-exhaustive switch | Còn giá trị selector chưa có nhánh xử lý | Thêm pattern bao phủ, default hoặc trường hợp còn thiếu |
| Incompatible pattern | Không có testing conversion từ selector/component sang kiểu pattern | Chọn kiểu pattern tương thích |
| Guarded coverage thiếu | Chỉ có pattern có guard có thể trả false | Thêm nhánh không guard cho phần còn lại |
| Null chưa xử lý | Wrapper/reference selector có thể null | Thêm case null hoặc chính sách xử lý null rõ ràng |
| Preview feature disabled | Compiler/runtime từ chối cú pháp preview | Bật preview với đúng JDK release |

Một switch có thể exhaustive nhưng vẫn có nhánh dominated. Ngược lại, một switch không có nhánh dominated vẫn có thể non-exhaustive. Hai kiểm tra này giải quyết hai câu hỏi khác nhau.

## 16. Biên dịch và chạy đúng preview release

Tính năng primitive patterns chưa final trong Java 25 hoặc Java 26. Phải bật preview ở cả bước biên dịch và chạy.

Với JDK 25, dùng đúng JDK 25:

~~~bash
javac --enable-preview --release 25 -Xlint:preview PrimitivePatternsDemo.java
java --enable-preview PrimitivePatternsDemo
~~~

Với JDK 26, dùng preview thứ tư của đúng JDK 26:

~~~bash
javac --enable-preview --release 26 -Xlint:preview PrimitivePatternsDemo.java
java --enable-preview PrimitivePatternsDemo
~~~

Không lấy bytecode preview được tạo bởi một release rồi chạy bằng release khác. Preview features gắn với release cụ thể; khi nâng JDK, cần biên dịch và kiểm tra lại toàn bộ code dùng preview.

Nếu triển khai ứng dụng production, cân nhắc kỹ rủi ro phụ thuộc preview: cú pháp và quy tắc có thể thay đổi ở release tiếp theo. Không đưa preview feature vào public API hoặc thư viện dùng chung nếu chưa chấp nhận chi phí nâng cấp và biên dịch lại.

## 17. Thay đổi cần chú ý khi chuyển từ Java 25 sang Java 26

Java 25 sử dụng JEP 507 (third preview). Java 26 sử dụng JEP 530 (fourth preview), trong đó:

1. Định nghĩa unconditionally exact conversion được làm rõ thành type-based và value-based.
2. Quy tắc dominance được mở rộng cho hằng số mà compiler chứng minh phép chuyển đổi sang kiểu của pattern là chính xác theo chính giá trị hằng số.
3. Một số nhánh từng được chấp nhận bởi compiler preview cũ có thể trở thành compile-time error.

Ví dụ case byte b đứng trước case 42 trong switch selector int:

- Pattern byte không bao phủ mọi int.
- Nhưng giá trị hằng 42 chuyển chính xác sang byte.
- Java 26 có thể xác định case 42 đã được nhánh case byte b nhận; nhánh hằng số phía sau bị dominated.
- Nếu cần xử lý 42 riêng, đặt case 42 trước pattern byte.

Khi nâng cấp, không chỉ kiểm tra chương trình có chạy được hay không. Hãy chạy compiler với preview đúng release để phát hiện nhánh mới bị coi là dominated hoặc thay đổi trong tính exhaustive.

## 18. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng cast để kiểm tra miền giá trị | Cast có thể làm mất thông tin nhưng vẫn trả kết quả | Dùng primitive pattern để kiểm tra exact conversion |
| Đặt case int trước case byte | Pattern int nhận mọi giá trị selector int | Đặt pattern hẹp trước pattern rộng |
| Đặt case short trước case byte | Mọi giá trị byte đều chuyển chính xác sang short | Đổi thành byte rồi short |
| Bỏ nhánh bao phủ phần còn lại | Switch expression/enhanced switch không exhaustive | Thêm pattern bao phủ hoặc default |
| Dùng guard để thay nhánh tổng quát | Guard có thể false, không bao phủ miền còn lại | Thêm pattern không guard |
| Đặt pattern không guard trước pattern có guard cùng kiểu | Pattern đầu đã nhận toàn bộ miền của pattern sau | Đưa guarded pattern lên trước |
| Quên xử lý null của wrapper | Primitive pattern không khớp null | Thêm case null |
| Cho rằng JDK 25 và 26 có cùng dominance rules | JEP 530 siết chặt phân tích hằng số | Biên dịch lại bằng đúng release |
| Bỏ --enable-preview | Tính năng chưa final | Bật preview khi compile và run |
| Dùng preview bytecode khác release | Preview không portable giữa các JDK release | Biên dịch lại với JDK mục tiêu |

## 19. Bài thực hành: phân tích switch có nhánh bị dominated

### Bối cảnh

Một bộ giải mã nhận mã số nguyên. Nhóm muốn phân loại mã thành ba miền: biểu diễn được bằng byte, biểu diễn được bằng short, và các giá trị int còn lại. Một số mã đặc biệt cần nhánh riêng.

### Nhiệm vụ

1. Viết switch expression với các pattern byte, short, int.
2. Kiểm tra switch có exhaustive không và giải thích vì sao.
3. Thử đổi thứ tự short lên trước byte; giải thích compile-time error.
4. Đưa case 42 lên trước case byte b và xác nhận nhánh đặc biệt được chọn.
5. Thử đặt case 42 sau case byte b; so sánh kết quả compiler Java 25 preview với Java 26 preview.
6. Thêm một guarded pattern when trước pattern không guard cùng kiểu.
7. Đảo hai nhánh guarded/unguarded và quan sát dominance.
8. Viết record pattern có component int được thử chuyển sang byte.
9. Thêm case null cho selector wrapper và giải thích vì sao primitive pattern không nhận null.
10. Biên dịch bằng JDK 25 và JDK 26 với preview flags tương ứng; lưu lại khác biệt diagnostics.

### Câu hỏi tự đánh giá

1. Primitive pattern khác cast thông thường ở điểm nào?
2. Testing conversion chỉ khớp khi điều kiện nào được thỏa mãn?
3. Vì sao case byte có thể khớp một phần giá trị của selector int?
4. Pattern nào bao phủ toàn bộ miền selector int?
5. Khi nào switch statement được xem là enhanced switch?
6. Vì sao switch expression phải exhaustive?
7. Dominance khác non-exhaustiveness như thế nào?
8. Vì sao case int đứng trước case byte gây lỗi?
9. Guard when ảnh hưởng thế nào đến exhaustiveness?
10. Vì sao pattern không guard đứng trước guarded pattern cùng kiểu làm guarded pattern không thể tới?
11. Primitive pattern trên Integer có nhận null không?
12. JEP 530 thay đổi phân tích constant dominance ra sao?
13. Vì sao phải biên dịch lại preview code khi chuyển từ JDK 25 sang JDK 26?

## 20. Checklist review switch có primitive patterns

- [ ] Đã xác nhận đúng JDK release và preview version.
- [ ] Compiler và runtime đều bật --enable-preview.
- [ ] Đã xác định chính xác kiểu selector.
- [ ] Mỗi pattern có testing conversion hợp lệ từ selector hoặc record component.
- [ ] Đã kiểm tra exactness, đặc biệt với narrowing và floating-point conversion.
- [ ] Pattern hẹp được đặt trước pattern rộng.
- [ ] Không có unguarded pattern nào dominate pattern phía sau.
- [ ] Hằng số đặc biệt được đặt trước pattern có thể nhận giá trị đó.
- [ ] Guard không được dùng làm nhánh bao phủ duy nhất.
- [ ] Switch expression và enhanced switch statement đã exhaustive.
- [ ] Wrapper/reference selector có chính sách xử lý null.
- [ ] default nằm sau pattern labels; case null, default ở cuối.
- [ ] Switch dùng dấu hai chấm đã được kiểm tra fall-through và definite assignment.
- [ ] Đã biên dịch lại với preview của release mục tiêu.
- [ ] Đã review thay đổi dominance khi chuyển từ JEP 507 sang JEP 530.

**Tiêu chí hoàn thành:** người học có thể chứng minh một switch có bao phủ toàn bộ miền selector, giải thích thứ tự pattern dựa trên testing conversion và phát hiện nhánh bị dominated. Người học cũng biết primitive patterns vẫn là preview trong Java 26, sử dụng đúng flags và kiểm tra lại các nhánh hằng số khi chuyển từ preview Java 25 sang Java 26.

## 21. Tài liệu chính thức

- [JEP 507 — Primitive Types in Patterns, instanceof, and switch (Third Preview)](https://openjdk.org/jeps/507): phạm vi preview trong Java 25.
- [Java SE 25 — Primitive Types in Patterns, instanceof, and switch JLS](https://docs.oracle.com/en/java/javase/25/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html): testing conversion, switch compatibility, dominance, exhaustiveness và pattern properties của preview thứ ba.
- [JEP 530 — Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530): thay đổi exactness và dominance trong Java 26.
- [Java SE 26 — Primitive Types in Patterns, instanceof, and switch JLS](https://docs.oracle.com/en/java/javase/26/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html): quy tắc preview thứ tư và value-based unconditionally exact conversions.
- [Java SE 26 — Safe Casting with instanceof and switch](https://docs.oracle.com/en/java/javase/26/language/safe-casting-instanceof-switch.html): giải thích safe casting và exactness.
- [Java Language Changes by Release — Java SE 26](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-release.html): xác nhận tính năng vẫn preview trong Java 26.
- [Oracle — Preview Language and VM Features](https://docs.oracle.com/en/java/javase/26/language/preview-language-and-vm-features.html): cách biên dịch và chạy preview features.

Khi dùng tài liệu này cho code Java 25, áp dụng quy tắc JEP 507 và JLS preview thứ ba. Khi nâng lên Java 26, dùng JEP 530 và JLS preview thứ tư để xác minh lại dominance, exactness và exhaustiveness. Không coi preview là cú pháp ổn định trước khi một release chính thức đưa tính năng thành permanent.
