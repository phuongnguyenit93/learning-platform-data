# Điều kiện when và phạm vi biến pattern

Pattern matching giúp kiểm tra kiểu và lấy giá trị đã khớp trong cùng một biểu thức. Với switch, mệnh đề when bổ sung điều kiện để một pattern chỉ khớp khi giá trị thỏa thêm một quy tắc nghiệp vụ. Biến pattern được khai báo trong nhãn case có phạm vi xác định: dùng được trong guard và nhánh xử lý tương ứng, nhưng không tự động tồn tại ở các nhãn khác hoặc sau câu lệnh switch.

Cần phân biệt hai phần của ngôn ngữ Java:

- Pattern matching với instanceof là tính năng chính thức từ Java 16; biến pattern tuân theo quy tắc flow scoping.
- Pattern matching với switch, bao gồm guard when, là tính năng chính thức từ Java 21. Có thể dùng với pattern kiểu tham chiếu mà không bật preview.
- Mở rộng pattern sang kiểu nguyên thủy trong JDK 26 vẫn là preview lần thứ tư theo JEP 530. Đây là phần riêng, không làm cho when hoặc pattern switch kiểu tham chiếu trở thành preview.

## 1. when dùng để làm gì?

Một guarded pattern label có dạng:

~~~java
case Pattern p when booleanExpression -> action;
~~~

Khi switch xét nhãn này, Java thực hiện theo thứ tự:

1. Kiểm tra giá trị selector có khớp với pattern hay không.
2. Nếu pattern khớp, khởi tạo các biến pattern được khai báo trong pattern.
3. Đánh giá biểu thức boolean sau when.
4. Nếu guard là true, thực hiện nhánh case.
5. Nếu guard là false, tiếp tục xét nhãn case tiếp theo.

Vì biến pattern đã được khởi tạo trước khi guard được đánh giá, guard có thể sử dụng biến đó để kiểm tra dữ liệu.

Ví dụ đơn giản:

~~~java
static String describe(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "Chuỗi rỗng";
        case String text when text.length() <= 3 -> "Chuỗi ngắn";
        case String text -> "Chuỗi: " + text;
        default -> "Giá trị khác";
    };
}
~~~

Nếu value là chuỗi "   ", pattern String text khớp và guard text.isBlank() trả về true. Nếu là "Java", guard đầu tiên trả về false, guard thứ hai cũng trả về false, rồi nhãn case String text cuối cùng xử lý giá trị.

Guard là biểu thức boolean. Nó có thể gọi phương thức, kết hợp nhiều điều kiện bằng &&, ||, !, hoặc dùng các phép so sánh. Guard không phải một khối lệnh để khai báo biến cục bộ hoặc thực hiện nhiều câu lệnh.

Từ khóa when đi sau một nhãn case có pattern. Nó không phải cú pháp để thêm điều kiện vào nhãn hằng số như case 1.

## 2. Phạm vi của biến pattern trong switch

Biến được khai báo trong pattern của nhãn case chỉ có hiệu lực tại những vị trí mà pattern đã được khớp.

### 2.1. Biến có hiệu lực trong guard

~~~java
case String text when text.length() >= 8 -> "Dài";
~~~

text có thể được dùng trong guard vì Java chỉ đánh giá guard sau khi pattern String text khớp. Không cần cast thủ công và cũng không cần kiểm tra kiểu lần thứ hai.

Với record pattern, các biến được khai báo ở thành phần lồng bên trong cũng có thể được dùng trong guard:

~~~java
record User(String name, String role) { }

static String describeUser(Object value) {
    return switch (value) {
        case User(String name, String role) when role.equals("admin") ->
            "Quản trị viên: " + name;
        case User(String name, String role) ->
            "Người dùng: " + name;
        default -> "Không phải User";
    };
}
~~~

Trong nhãn đầu tiên, name và role được khai báo bởi record pattern. Cả hai đều nằm trong phạm vi của guard và nhánh trả về kết quả. Pattern thành phần String role không khớp nếu thành phần role là null, vì vậy guard không gọi equals trên một giá trị null.

### 2.2. Biến có hiệu lực trong nhánh case tương ứng

Với switch rule dùng ->, biến pattern được dùng trong expression, block hoặc câu lệnh throw ở bên phải mũi tên:

~~~java
static String format(Object value) {
    return switch (value) {
        case String text when !text.isBlank() -> {
            String normalized = text.strip();
            yield normalized.toUpperCase();
        }
        case String text -> "(không có nội dung)";
        default -> "(không phải chuỗi)";
    };
}
~~~

Biến text của nhãn đầu tiên được dùng trong guard và block đầu tiên. Biến text của nhãn thứ hai là một khai báo pattern riêng, có phạm vi trong nhãn và nhánh xử lý thứ hai. Hai biến trùng tên nhưng thuộc hai nhánh độc lập nên không xung đột.

Biến pattern không có hiệu lực sau khi kết thúc nhánh case, và cũng không thể dùng ở nhãn case kế tiếp. Ví dụ sau không hợp lệ:

~~~java
switch (value) {
    case String text -> System.out.println(text);
    default -> System.out.println(text); // Lỗi: text ngoài phạm vi
}
~~~

Nếu cần dùng dữ liệu sau switch, hãy gán kết quả của switch expression vào một biến có phạm vi phù hợp, hoặc trả về giá trị từ phương thức.

Các ví dụ dùng pattern kiểu tham chiếu và when có thể biên dịch bằng JDK 21 trở lên mà không cần bật preview:

~~~sh
javac PatternGuardDemo.java
java PatternGuardDemo
~~~

### 2.3. Switch statement dùng nhãn case ... :

Java vẫn hỗ trợ switch statement dùng dấu hai chấm. Với nhãn khai báo pattern variable, biến có hiệu lực trong switch-labeled statement group tương ứng.

~~~java
static void print(Object value) {
    switch (value) {
        case String text:
            System.out.println(text.strip());
            break;
        default:
            System.out.println("Không phải chuỗi");
    }
}
~~~

Không được để luồng thực thi rơi từ statement group trước vào một nhãn khai báo pattern variable. Nếu điều đó có thể xảy ra, chương trình bị lỗi biên dịch vì biến pattern có thể chưa được khởi tạo. Với code mới, switch rule dùng -> thường dễ đọc và tránh nhầm lẫn về fall-through.

## 3. Phân biệt when trong switch và flow scoping của instanceof

Từ Java 16, instanceof có thể khai báo biến pattern trực tiếp:

~~~java
if (value instanceof String text) {
    System.out.println(text.strip());
}
~~~

Đây là pattern matching cho instanceof. Nó không dùng từ khóa when. Điều kiện bổ sung được viết bằng toán tử boolean, thường là &&.

### 3.1. Biến có hiệu lực ở nhánh chắc chắn đã khớp

~~~java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
~~~

Toán tử && đánh giá vế phải chỉ khi vế trái là true. Do đó, khi chương trình đi đến !text.isBlank(), pattern String text đã khớp và text được khởi tạo.

Flow scoping còn cho phép dùng biến sau một điều kiện phủ định nếu nhánh không khớp đã kết thúc:

~~~java
static int lengthOfText(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }

    // Đến đây, value chắc chắn đã khớp String text.
    return text.length();
}
~~~

Khi luồng thực thi đi qua câu lệnh if, điều kiện !(value instanceof String text) phải là false; vì vậy value instanceof String text là true. Compiler có thể xác định text đã được khởi tạo trên đường đi này.

### 3.2. Vì sao không thể dùng biến ở vế phải của ||?

~~~java
if (value instanceof String text || text.isBlank()) {
    // Lỗi biên dịch
}
~~~

Vế phải của || được đánh giá khi vế trái là false. Trong trường hợp đó, value instanceof String text không khớp và text chưa được khởi tạo. Compiler từ chối chương trình vì có đường đi có thể truy cập biến chưa được xác định.

Có thể viết lại tùy mục tiêu:

~~~java
if (value instanceof String text && text.isBlank()) {
    System.out.println("Chuỗi rỗng");
}
~~~

Quy tắc này cũng giải thích cách viết guard trong switch: guard chỉ được đánh giá sau khi pattern của chính nhãn đó đã khớp, nên biến pattern nằm trong phạm vi và đã được khởi tạo.

## 4. Guard sai thì chuyện gì xảy ra?

Guard false có nghĩa là nhãn hiện tại không khớp hoàn toàn. Java tiếp tục xét các nhãn sau theo thứ tự xuất hiện.

~~~java
static String classify(String text) {
    return switch (text) {
        case String s when s.length() >= 10 -> "Dài";
        case String s when s.length() >= 5 -> "Trung bình";
        case String s -> "Ngắn";
    };
}
~~~

Với chuỗi có 7 ký tự, guard đầu tiên sai, guard thứ hai đúng và nhánh "Trung bình" được chọn.

Nếu guard gọi phương thức ném exception, exception được truyền ra ngoài theo quy tắc thông thường. Java không xem exception như kết quả false để tự động thử nhãn kế tiếp. Vì vậy, guard nên tập trung vào điều kiện kiểm tra rõ ràng và tránh chứa thao tác có side effect khó kiểm soát.

## 5. Thứ tự nhãn và pattern dominance

Compiler kiểm tra một số trường hợp nhãn phía sau không bao giờ có cơ hội được xét vì nhãn trước đã bao phủ toàn bộ giá trị mà nó có thể khớp. Quy tắc này gọi là pattern label dominance.

Ví dụ không hợp lệ:

~~~java
static String describe(Object value) {
    return switch (value) {
        case Object obj -> "Object";
        case String text -> "String"; // Lỗi: bị nhãn Object chi phối
    };
}
~~~

Mọi String đều là Object, nên nhãn đầu tiên đã bao phủ nhãn thứ hai.

Một pattern không có guard cũng có thể chi phối pattern cùng loại có guard nếu pattern không guard xuất hiện trước:

~~~java
switch (value) {
    case String text -> System.out.println(text);
    case String text when text.isBlank() -> System.out.println("Blank"); // Lỗi
}
~~~

Đảo thứ tự để guard được xét trước:

~~~java
switch (value) {
    case String text when text.isBlank() -> System.out.println("Blank");
    case String text -> System.out.println(text);
    default -> System.out.println("Other");
}
~~~

Guarded pattern thường không được dùng để kết luận dominance với các nhãn khác vì compiler không thể chứng minh tổng quát kết quả của biểu thức guard. Tuy vậy, nên sắp xếp nhãn theo thứ tự dễ hiểu:

1. Các hằng số cụ thể.
2. Pattern có guard, từ điều kiện hẹp đến rộng.
3. Pattern không guard bao quát loại dữ liệu.
4. default nếu cần.

Một guard là constant expression có giá trị true được xem như nhãn không guard cho mục đích dominance. Không dùng when true để né quy tắc dominance.

## 6. Xử lý null trong pattern switch

Pattern kiểu tham chiếu không khớp với null. Nếu selector của switch là null và không có nhãn case null, switch statement hoặc switch expression ném NullPointerException.

~~~java
static String describe(Object value) {
    return switch (value) {
        case null -> "Không có giá trị";
        case String text when text.isBlank() -> "Chuỗi rỗng";
        case String text -> "Chuỗi có nội dung";
        default -> "Kiểu khác";
    };
}
~~~

Đặt case null khi null là một đầu vào hợp lệ cần xử lý. Không dựa vào default để bắt null. Với pattern thành phần trong record, cũng cần hiểu cách pattern lồng nhau xử lý null: type pattern cho một thành phần tham chiếu không khớp với null, nên toàn bộ record pattern có thể không khớp và nhãn sau được xét.

## 7. Phân biệt tính năng ổn định và primitive patterns preview trong Java 26

Không phải mọi cú pháp có when đều có cùng trạng thái phát hành.

| Khả năng | Trạng thái |
|---|---|
| Pattern matching với instanceof | Chính thức từ Java 16 (JEP 394) |
| Pattern matching cho switch và guard when với pattern kiểu tham chiếu | Chính thức từ Java 21 (JEP 441) |
| Record patterns | Chính thức từ Java 21 (JEP 440) |
| Pattern kiểu nguyên thủy ở top-level, primitive instanceof và primitive patterns trong record/switch | Preview lần thứ tư trong Java 26 (JEP 530) |

Ví dụ sau minh họa primitive pattern có guard. Đặt phương thức này trong file PrimitivePatternDemo.java:

~~~java
public class PrimitivePatternDemo {
    static String bucket(int value) {
        return switch (value) {
            case int n when n < 0 -> "Âm";
            case int n when n == 0 -> "Không";
            case int n -> "Dương";
        };
    }

    public static void main(String[] args) {
        System.out.println(bucket(-2));
        System.out.println(bucket(0));
        System.out.println(bucket(5));
    }
}
~~~

Trong JDK 26, cú pháp case int n với selector nguyên thủy thuộc preview JEP 530. Muốn thử đúng bản Java 26, dùng JDK 26 để biên dịch và chạy:

~~~sh
javac --enable-preview --release 26 PrimitivePatternDemo.java
java --enable-preview PrimitivePatternDemo
~~~

Chỉ bật preview ở môi trường học tập hoặc thử nghiệm. Preview gắn với phiên bản JDK cụ thể; mã biên dịch bằng preview của JDK 26 không phải cam kết tương thích với JDK 27 hoặc JDK 28.

**Cập nhật vòng đời tính năng:** JDK 26 phát hành primitive patterns dưới dạng preview lần thứ tư. Ngày 11-11-2026, nhóm Java thông báo dừng phát triển tính năng này, rút draft JEP cho preview tiếp theo và dự kiến loại bỏ primitive-pattern preview khỏi JDK 28. Vì vậy, hãy xem cú pháp primitive pattern là nội dung cần nhận diện khi đọc hoặc thử mã nhắm đúng JDK 26; không thiết kế API hoặc code production mới phụ thuộc vào nó. Quy tắc when với pattern kiểu tham chiếu và flow scoping của instanceof vẫn là các tính năng chính thức, tiếp tục áp dụng độc lập.

## 8. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa |
|---|---|---|
| Không dùng được biến trong when | Biến chưa được khai báo bởi pattern của chính nhãn đó hoặc tên biến bị viết sai | Khai báo biến trong pattern trước when |
| Dùng biến pattern ở nhãn kế tiếp | Phạm vi biến chỉ thuộc nhãn và nhánh xử lý tương ứng | Khai báo pattern riêng trong nhãn cần dùng |
| Dùng biến ở vế phải của || trong instanceof | Vế phải có thể được đánh giá khi pattern không khớp | Dùng && hoặc cấu trúc early return |
| Nhãn bị compiler báo dominated | Nhãn trước đã bao phủ mọi giá trị của nhãn sau | Sắp xếp lại thứ tự; đặt pattern hẹp/guard trước pattern bao quát |
| Guard không chạy | Pattern không khớp nên guard không được đánh giá | Kiểm tra kiểu và cấu trúc pattern trước |
| Guard ném NullPointerException | Guard gọi phương thức trên thành phần có thể null | Dùng pattern phù hợp hoặc kiểm tra null trước khi gọi |
| Switch nhận null rồi ném NPE | Không có nhãn case null | Thêm case null nếu null là đầu vào hợp lệ |
| Primitive pattern báo preview disabled | Dùng cú pháp JEP 530 nhưng chưa bật preview của đúng JDK | Chỉ trong thử nghiệm Java 26, dùng --enable-preview --release 26 cho compile và --enable-preview cho run |

## 9. Checklist áp dụng

- [ ] Xác định pattern đang dùng là pattern kiểu tham chiếu ổn định hay primitive pattern preview.
- [ ] Dùng when cho guard trong case pattern label; dùng &&/|| cho điều kiện instanceof.
- [ ] Chỉ tham chiếu biến pattern sau khi flow đã bảo đảm pattern khớp.
- [ ] Giữ biến pattern trong guard và nhánh xử lý của đúng nhãn case.
- [ ] Đặt pattern có guard trước pattern không guard có thể bao phủ nó.
- [ ] Kiểm tra dominance khi compiler báo nhãn không thể được chọn.
- [ ] Xử lý null rõ ràng trong switch selector kiểu tham chiếu.
- [ ] Không giả định default xử lý được null.
- [ ] Không bật preview cho pattern switch kiểu tham chiếu hoặc instanceof ổn định.
- [ ] Không phụ thuộc primitive-pattern preview trong code production; nếu cần đọc mã Java 26 thử nghiệm, kiểm tra đúng JDK và cờ preview.

## Tài liệu tham khảo

- [Java SE 26 — Pattern Matching with switch](https://docs.oracle.com/en/java/javase/26/language/pattern-matching-switch.html): guard when, dominance, phạm vi biến pattern, null case labels.
- [Java SE 26 — Pattern Matching with instanceof](https://docs.oracle.com/en/java/javase/26/language/pattern-matching-instanceof.html): flow scoping và phạm vi pattern variable.
- [Java SE 26 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-release.html): phân biệt tính năng chính thức và preview theo phiên bản.
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): tính năng chính thức từ Java 16.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns chính thức từ Java 21.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): pattern switch và guarded patterns chính thức từ Java 21.
- [JEP 530 — Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530): trạng thái preview của primitive patterns trong Java 26.
- [OpenJDK: Withdrawing the Primitive Patterns Preview Feature](https://inside.java/2026/11/11/withdraw-primitive-patterns-preview/): thông báo dừng phát triển và dự kiến loại bỏ primitive-pattern preview khỏi JDK 28.

