# Exhaustiveness trong switch expression của Java

## 1. Exhaustiveness là gì và vì sao quan trọng?

**Exhaustiveness** (tính bao phủ đầy đủ) nghĩa là khối **switch** có đủ nhãn **case** để xử lý mọi giá trị mà kiểu tĩnh của biểu thức lựa chọn (**selector**) có thể nhận, theo quy tắc của trình biên dịch. Đối với **switch expression**—một biểu thức tính ra kết quả—đây là yêu cầu **bắt buộc khi biên dịch**: mỗi đường thực thi hợp lệ phải cho ra giá trị bằng một nhánh hoặc kết thúc bằng ngoại lệ, không được lặng lẽ “không trả gì”.

Ví dụ đơn giản với enum:

~~~java
enum Signal { RED, YELLOW, GREEN }

static String guidance(Signal signal) {
    return switch (signal) {
        case RED -> "stop";
        case YELLOW -> "slow";
        case GREEN -> "go";
    };
}
~~~

Nếu enum **Signal** tại thời điểm biên dịch chỉ có ba hằng số này, compiler biết cả ba đã được liệt kê, nên **không cần default**. Nếu bỏ **case GREEN**, switch expression sẽ không biên dịch vì chưa bao phủ hết tập giá trị hợp lệ của enum.

Ngược lại, với selector kiểu **Object**, các kiểu cụ thể có thể rất nhiều. Đoạn sau là ví dụ **cố ý sai**:

~~~java
static String incomplete(Object input) {
    return switch (input) {
        case String text -> "string";
        case Integer number -> "integer";
        // LỖI: selector Object còn rất nhiều kiểu chưa được bao phủ
    };
}
~~~

**default** hoặc một nhánh pattern tổng quát thích hợp là cách thông thường để làm exhaustive khi selector là **Object**. **Exhaustiveness được xác định chủ yếu bằng kiểu tĩnh và cấu trúc case**, không phải bằng vài giá trị đã tình cờ xuất hiện trong lúc chạy.

**Phiên bản Java:** switch expression đã chính thức từ **Java 14**; **pattern matching for switch** cùng **case Type variable**, **when** và các quy tắc sealed pattern trong bài được chuẩn hóa ở **Java 21**. Ví dụ đầy đủ dưới đây dùng **JDK 21+**, không bật preview.

## 2. Những cách khiến switch expression được xem là exhaustive

Trong Java 21, các cách phổ biến gồm:

| Kiểu selector | Cách bảo đảm exhaustiveness | Chú ý |
| --- | --- | --- |
| **enum E** | Liệt kê tất cả enum constant, hoặc thêm **default** | Có thể tận dụng compiler khi enum mở rộng |
| **Object** hay kiểu mở | Có **default**, hoặc một type pattern không guard bao phủ kiểu nguồn | Chỉ liệt kê vài subtype thường chưa đủ |
| **sealed interface/class** | Các type pattern không guard bao phủ mọi subtype được phép | Không nhất thiết cần **default** |
| Một kiểu tham chiếu cụ thể, ví dụ **String** | Có pattern không guard bao phủ mọi String khác null, hoặc **default** | Xử lý null là vấn đề riêng |
| Pattern có **when** | Cần thêm nhánh bao phủ phần giá trị mà guard có thể từ chối | Guard tùy ý không mặc nhiên bao phủ toàn bộ kiểu |

Với các kiểu sealed, compiler phân tích danh sách **permits** và quan hệ subtype để xác định các nhánh đã đầy đủ chưa. Với enum, compiler kiểm tra danh sách hằng số. Với một selector kiểu mở như **Object**, một nhánh **default** thường rõ ràng hơn việc đoán những kiểu có thể có.

Không nên hiểu bảng theo nghĩa “chỉ cần có nhiều case”. Năm case quá chuyên biệt vẫn có thể thiếu một kiểu; hai case cũng có thể đủ khi chúng bao phủ chính xác hai subtype của một sealed interface.

### Exhaustive không có nghĩa mọi nhánh luôn chạy được

Switch chọn **một nhánh áp dụng** theo quy tắc case; nó không thực hiện tất cả nhánh. Kiểm tra exhaustiveness là bảo đảm có nhánh thích hợp cho mỗi giá trị hợp lệ, còn kiểm tra **dominance** phát hiện nhãn phía sau bị nhãn phía trước che khuất. Hai phép kiểm tra là hai vấn đề khác nhau.

## 3. Ví dụ hoàn chỉnh Java 21: enum, sealed hierarchy và Object

Lưu tệp **ExhaustivenessDemo.java**:

~~~java
public class ExhaustivenessDemo {
    enum Signal { RED, YELLOW, GREEN }

    sealed interface Expr permits Literal, Add, Negate {}

    record Literal(int value) implements Expr {}
    record Add(Expr left, Expr right) implements Expr {}
    record Negate(Expr inner) implements Expr {}

    static String guidance(Signal signal) {
        return switch (signal) {
            case RED -> "stop";
            case YELLOW -> "slow";
            case GREEN -> "go";
        };
    }

    static int evaluate(Expr expression) {
        return switch (expression) {
            case Literal literal -> literal.value();
            case Add add ->
                    evaluate(add.left()) + evaluate(add.right());
            case Negate negate -> -evaluate(negate.inner());
        };
    }

    static String describe(Object input) {
        return switch (input) {
            case null -> "null";
            case String text when text.isBlank() -> "blank";
            case String text -> "text:" + text.strip();
            case Number number -> "number:" + number;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(guidance(Signal.RED));
        System.out.println(guidance(Signal.GREEN));

        Expr value = new Add(
                new Literal(2),
                new Negate(new Literal(5))
        );
        System.out.println(evaluate(value));

        System.out.println(describe(" hi "));
        System.out.println(describe("  "));
        System.out.println(describe(42));
        System.out.println(describe(null));
        System.out.println(describe(new Object()));
    }
}
~~~

Biên dịch và chạy bằng **JDK 21+**:

~~~bash
javac -encoding UTF-8 ExhaustivenessDemo.java
java ExhaustivenessDemo
~~~

Kết quả chính xác:

~~~text
stop
go
-3
text:hi
blank
number:42
null
other
~~~

**Phân tích:**

1. **guidance** là switch expression exhaustive vì ba hằng số **RED**, **YELLOW**, **GREEN** đã được liệt kê.
2. **Expr** là một **sealed interface** chỉ cho phép ba record **Literal**, **Add**, **Negate**. Mỗi record là một subtype cụ thể, nên ba case trong **evaluate** bao phủ những đối tượng **Expr** khác null.
3. Biểu thức **Add(Literal(2), Negate(Literal(5)))** được tính đệ quy: **2 + (-5) = -3**.
4. **describe** nhận **Object** nên ba loại case đặc biệt vẫn chưa bao phủ mọi object; **default** hoàn tất tập nhánh cho các kiểu còn lại.
5. **case String text when text.isBlank()** chọn chuỗi trắng, còn **case String text** kế tiếp bao phủ những chuỗi còn lại. **when** không tự khiến tất cả String được bao phủ.
6. **case null** xử lý giá trị null một cách tường minh để trả về chuỗi **"null"**; đây là quyết định nghiệp vụ riêng với yêu cầu exhaustive thông thường.

Lệnh **javac** trong ví dụ chỉ cần JDK 21; không cần **--enable-preview**.

## 4. Vì sao sealed type hữu ích hơn default rộng?

Với sealed hierarchy, tập subtype trực tiếp được cho phép là một hợp đồng có thể phân tích lúc biên dịch:

~~~java
sealed interface PaymentResult
        permits Accepted, Declined {}

record Accepted(String receipt) implements PaymentResult {}
record Declined(String reason) implements PaymentResult {}
~~~

Đoạn trên là **mã khai báo minh họa**, cần đặt trong tệp nguồn hợp lệ. Một switch expression cho loại kết quả này có thể không cần default:

~~~java
static String summary(PaymentResult result) {
    return switch (result) {
        case Accepted ok -> "accepted:" + ok.receipt();
        case Declined no -> "declined:" + no.reason();
    };
}
~~~

Nếu sau này mở rộng **permits** bằng subtype **Pending**, compiler sẽ chỉ ra switch chưa xử lý đầy đủ khi biên dịch lại code. Đây là lợi ích lớn cho bảo trì: chỗ cần cập nhật được phát hiện ngay khi mô hình dữ liệu thay đổi.

Nếu luôn có **default -> "unknown"**, switch vẫn exhaustive và chương trình thường biên dịch sau khi thêm subtype; nhưng nhánh mới có thể bị nuốt vào fallback mà không khiến người phát triển cân nhắc cách xử lý. Khi cần bảo đảm phải cập nhật logic lúc thêm subtype, **cân nhắc bỏ default** trên sealed hierarchy đã bao phủ đủ.

Một **permitted subtype** có thể được khai báo **final**, **sealed** hoặc **non-sealed** theo quy tắc ngôn ngữ. Khi một nhánh **case SomePermittedType x** bao phủ subtype ấy, các thể hiện thuộc những lớp con của kiểu này cũng được nhánh đó xử lý. Vì vậy kiểm tra bao phủ phụ thuộc quan hệ kiểu, không chỉ so sánh tên class dưới dạng chuỗi.

## 5. Default: giải pháp bao phủ tổng quát nhưng có thể che thiếu sót

Nếu không biết toàn bộ các subtype tại compile time, **default** là lựa chọn hợp lý:

~~~java
static String label(Object input) {
    return switch (input) {
        case String text -> "string:" + text;
        case Number number -> "number:" + number;
        default -> "other";
    };
}
~~~

Đây là **phương thức minh họa Java 21+**. Compiler biết **default** bắt những đối tượng không khớp các case trước. Nhưng hãy nhớ: **default không đồng nghĩa với case null**. Nếu selector là null và không có case xử lý null, switch thường ném **NullPointerException** thay vì trả về **"other"**.

Với enum, một **default** cũng có thể làm mất ích lợi của việc compiler nhắc người viết bổ sung xử lý một hằng số vừa được thêm vào. Hãy chọn default nếu ứng dụng thật sự có nghiệp vụ “mọi giá trị còn lại xử lý như nhau”, không dùng chỉ để che lỗi bao phủ.

## 6. Guard when và exhaustiveness: chấp nhận kiểu không có nghĩa chấp nhận mọi giá trị

Giả sử nghiệp vụ chỉ xử lý số nguyên dương:

~~~java
// Cố ý sai: chưa exhaustive cho selector Object.
static String positiveOnly(Object value) {
    return switch (value) {
        case Integer number when number > 0 -> "positive";
    };
}
~~~

Ngoài các kiểu khác **Integer**, ngay cả giá trị **0** và **-1** cũng không khớp guard. Phải thêm nhánh cho những giá trị không được guard chấp nhận, ví dụ:

~~~java
static String classifyNumber(Object value) {
    return switch (value) {
        case Integer number when number > 0 -> "positive";
        case Integer number -> "zero-or-negative";
        case null -> "missing";
        default -> "not-an-integer";
    };
}
~~~

**when** chỉ được đánh giá sau khi pattern đã khớp, vì vậy biến **number** có kiểu **Integer** an toàn trong biểu thức **number > 0**. Khi guard trả về false, switch xét các case tiếp theo.

**Thứ tự case quan trọng.** Nếu đặt **case Integer number -> ...** trước **case Integer number when number > 0 -> ...**, case tổng quát che nhánh cụ thể; compiler có thể báo lỗi **dominated case**.

### Trường hợp guard không góp phần chứng minh bao phủ kiểu

Compiler Java 21 không xem một guard **when** tùy ý là bằng chứng rằng nó luôn đúng với mọi giá trị. Khi muốn exhaustiveness dựa trên kiểu, cần một nhãn pattern không guard bao phủ các giá trị còn lại hoặc dùng **default** phù hợp.

Ví dụ **case String s when s.length() >= 0** có vẻ luôn đúng với String, nhưng không nên dùng thay cho một **case String s** không guard để chứng minh exhaustiveness. Hãy viết nhánh không guard khi muốn compiler nhìn thấy sự bao phủ trực tiếp.

## 7. Null có phải một phần của exhaustive switch expression không?

**Điểm rất dễ nhầm:** một switch expression có đủ case cho mọi giá trị **khác null** của một sealed interface hoặc enum vẫn có thể **biên dịch khi thiếu case null**. Nhưng nếu truyền **null** vào selector ở runtime, switch đó sẽ ném **NullPointerException** khi không có nhãn null áp dụng.

Ví dụ trong chương trình hoàn chỉnh phía trên:

~~~java
// Đoạn minh họa, không đặt vào main nếu không muốn ném ngoại lệ.
Expr value = null;
System.out.println(evaluate(value)); // NullPointerException
~~~

Các nhánh **Literal**, **Add**, **Negate** vẫn được compiler xem là bao phủ đầy đủ các subtype thuộc **Expr**, nhưng không có nhánh nào xử lý null.

Nếu API cho phép null và cần một kết quả bình thường, hãy thêm:

~~~java
// Đoạn trả về switch expression trong phương thức nhận Expr expression:
return switch (expression) {
    case null -> 0;
    case Literal literal -> literal.value();
    case Add add -> evaluate(add.left()) + evaluate(add.right());
    case Negate negate -> -evaluate(negate.inner());
};
~~~

Đây là mã minh họa, có thể dùng khi đặt trong cùng class với khai báo kiểu và phương thức **evaluate** ở ví dụ Java 21. Việc trả về **0** cho null chỉ là một chính sách ví dụ; nghiệp vụ thực tế có thể yêu cầu ngoại lệ hoặc giá trị khác.

Tóm lại, **exhaustiveness tại compile time không phải là lời hứa rằng mọi runtime value, nhất là null, sẽ cho ra một kết quả thường**. Hai câu hỏi cần kiểm tra riêng: *đã đủ nhánh cho các subtype?* và *null có phải đầu vào hợp lệ không?*

## 8. Switch expression và switch statement không có cùng luật lịch sử

Trên Java 21:

- **Mọi switch expression** đều phải exhaustive.
- **Enhanced switch statement** (ví dụ statement dùng pattern case, null case, hoặc selector kiểu tham chiếu ngoài nhóm switch cổ điển) cũng phải exhaustive.
- **Legacy switch statement** vốn chỉ dùng hằng số/enum theo cú pháp truyền thống không bị bắt buộc exhaustive để giữ tương thích; không tìm thấy case có thể đơn giản không làm gì.

Ví dụ legacy statement hợp lệ dù thiếu trường hợp:

~~~java
static void printSignal(Signal signal) {
    switch (signal) {
        case RED -> System.out.println("stop");
        // Không có YELLOW, GREEN: legacy statement vẫn có thể biên dịch.
    }
}
~~~

Trong khi một **switch expression** tương ứng mà thiếu **YELLOW**, **GREEN** sẽ bị compiler từ chối.

Đừng vì một switch statement cũ có thể bỏ sót nhánh mà suy ra switch expression cũng vậy. Hai dạng có các nghĩa vụ bao phủ khác nhau, đặc biệt từ Java 21 khi enhanced statement yêu cầu exhaustive.

## 9. Mọi đường đi trong một nhánh phải cho kết quả hoặc ném lỗi

Bao phủ case là **một yêu cầu**; nhánh được chọn vẫn phải tuân thủ ngữ nghĩa của switch expression.

Một nhánh mũi tên có thể trả về expression:

~~~java
static String sizeLabel(Object value) {
    return switch (value) {
        case String s -> "length:" + s.length();
        default -> "other";
    };
}
~~~

Khi nhánh cần nhiều câu lệnh, dùng **yield** để cung cấp kết quả của switch expression:

~~~java
static String normalized(Object value) {
    return switch (value) {
        case String s -> {
            String clean = s.strip();
            yield clean.isEmpty() ? "(blank)" : clean;
        }
        default -> "(other)";
    };
}
~~~

Đây đều là **phương thức minh họa Java 21+**, không phải tệp độc lập. Một block của switch expression nếu có đường đi kết thúc bình thường mà không có **yield**/throw phù hợp sẽ không biên dịch. **yield** là kết quả của nhánh switch expression, khác với **return** rời khỏi phương thức.

Với các case dấu hai chấm cũ, cũng có thể viết switch expression sử dụng **yield**, nhưng cần kiểm tra fall-through và mọi đường đi. Để dễ đọc và giảm sai sót, các ví dụ ở bài này ưu tiên **case ... ->**.

## 10. Những bẫy thường gặp

**Bẫy 1 — nghĩ default bao phủ null:** default giúp nhận những kiểu/giá trị chưa liệt kê, nhưng không thay thế **case null**. Phải xử lý null riêng nếu hợp đồng yêu cầu.

**Bẫy 2 — bỏ default ở selector Object:** chỉ kiểm tra String và Number chưa thể exhaustive đối với Object; phải có default hoặc pattern bao phủ kiểu còn lại.

**Bẫy 3 — đặt default vào sealed switch chỉ để hết lỗi:** default rộng sẽ khiến những subtype mới có thể âm thầm đi vào một hành vi chung. Hãy tận dụng compiler kiểm tra danh sách subtype khi cần cập nhật tường minh.

**Bẫy 4 — chỉ có case với when:** điều kiện guard có thể sai, nên vẫn cần case không guard cho phần còn lại hoặc nhánh khác bảo đảm bao phủ.

**Bẫy 5 — quên phạm vi của pattern variable:** biến khai báo trong **case Literal literal** chỉ được dùng nơi nhãn ấy đã khớp, không dùng tùy tiện trong case khác.

**Bẫy 6 — nhầm dominance với exhaustiveness:** một case quá tổng quát đặt sớm có thể khiến nhánh sau không đến được; ngược lại thiếu một subtype khiến switch chưa exhaustive. Cả hai đều cần được xem khi thay đổi case.

**Bẫy 7 — nghĩ switch expression luôn không thể ném lỗi:** exhaustiveness chỉ kiểm tra phủ case; code bên trong nhánh vẫn có thể ném ngoại lệ, và null không được xử lý có thể gây NPE.

**Bẫy 8 — dùng switch pattern Java 21 trên Java 17:** Java 17 có instanceof pattern và switch expression cho kiểu truyền thống, nhưng không có switch pattern **when** chuẩn Java 21.

**Bẫy 9 — nghĩ exhaustive đồng nghĩa không cần test:** compiler không xác minh mọi ràng buộc nghiệp vụ hoặc kết quả toán học. Ví dụ **Add** và **Negate** trong biểu thức có thể chứa null ở các component nếu caller cho phép; khi đó lỗi có thể xảy ra trong nhánh xử lý dù đã đầy đủ case.

## 11. Checklist biên dịch và review

Trước khi chấp nhận một switch expression, hãy kiểm tra:

1. Xác định **kiểu tĩnh selector**. Với enum/sealed, danh sách trường hợp có được xác định đầy đủ từ khai báo kiểu hiện tại không?
2. Liệt kê các **case** và kiểm tra nhóm **không guard** bao phủ kiểu nguồn; nếu là selector mở, có default hợp lý chưa?
3. Nếu có **when**, xác định những giá trị có thể trượt guard và case nào nhận chúng.
4. Kiểm tra **dominance**, đặc biệt subtype cụ thể phải đứng trước pattern cha tổng quát có thể che khuất.
5. Xác định **null** có hợp lệ hay không. Nếu có, phải có **case null** hoặc xử lý tường minh trước switch.
6. Bảo đảm mọi nhánh khi được chọn sẽ sinh ra một giá trị bằng expression/**yield** hoặc ném ngoại lệ rõ ràng.
7. Nếu dùng sealed hierarchy, cân nhắc tránh **default** để compiler báo khi bổ sung subtype mới.
8. Biên dịch bằng **javac** của JDK mục tiêu và chạy test cho từng subtype, nhánh guard đúng/sai, null và nhánh dự phòng.
9. Khi thay đổi schema hoặc version dependency, **recompile** module chứa switch để kiểm tra exhaustiveness với định nghĩa kiểu mới.
10. Phân biệt kết quả bình thường với các ngoại lệ có thể xảy ra ở runtime; không suy diễn exhaustive = không bao giờ ném lỗi.

## 12. Nguồn tham khảo chính thức

- [JLS Java SE 21 §14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): điều kiện bao phủ, enum, sealed và default.
- [JLS Java SE 21 §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): yêu cầu biểu thức cho ra giá trị và tính exhaustive.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): các case pattern, null, guard, dominance và sealed type.
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): lịch sử và ngữ nghĩa switch expression.

**Kết luận:** switch expression phải bao phủ hết các khả năng mà compiler có thể nhận diện. Với **enum** và **sealed hierarchy**, Java 21 có thể chứng minh exhaustive chỉ từ các case cụ thể mà không cần default; với kiểu mở như Object, default thường là lựa chọn phù hợp. Exhaustiveness không thay thế việc xử lý null, kiểm tra guard hay kiểm thử nghiệp vụ, nhưng nó biến một số thiếu sót phân nhánh thành lỗi biên dịch ngay từ đầu.