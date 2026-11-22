# Pattern variable trong guard: kiểm tra điều kiện và bảo đảm phạm vi trong Java

## 1. Pattern variable và khái niệm guard

Một **pattern variable** là biến được giới thiệu khi một mẫu (**pattern**) khớp với giá trị. Ví dụ, từ Java 16, **instanceof** hỗ trợ type pattern:

~~~java
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Biểu thức **value instanceof String text** kiểm tra rằng **value** tham chiếu tới một đối tượng **String** khác **null**. Nếu đúng, **text** được gắn với đối tượng đó và có kiểu tĩnh **String**. Nếu sai, **text** chưa được gắn; compiler không cho dùng biến ở những đường thực thi chưa bảo đảm phép khớp thành công.

Trong ngữ cảnh pattern matching, từ **guard** có hai cách dùng liên quan:

- **Guard clause (mệnh đề bảo vệ)**: kiểm tra trường hợp không hợp lệ rồi thoát sớm bằng **return** hoặc **throw**. Khi guard loại bỏ toàn bộ đường đi không khớp, code phía sau có thể sử dụng pattern variable.
- **Điều kiện guard của một pattern trong switch**: từ **Java 21**, cú pháp **case Type variable when condition -> ...** chỉ chọn nhánh khi vừa khớp pattern, vừa thỏa điều kiện **when**. Biến pattern dùng được trong biểu thức **when** và phần xử lý của nhánh.

Hai cơ chế cùng dựa vào việc **biến chỉ hợp lệ ở nơi compiler đã chứng minh phép khớp**. Tuy nhiên, chúng khác nhau về cú pháp, vị trí và phiên bản Java hỗ trợ. Phần Java 17 dưới đây giải thích guard clause và các điều kiện logic; phần Java 21 giới thiệu **when** trong **switch**.

## 2. Guard clause với instanceof: trường hợp sai thì thoát

Giả sử một phương thức nhận **Object**, nhưng chỉ xử lý khi đầu vào là **String**. Cách cũ phải kiểm tra rồi cast:

~~~java
static int legacyLength(Object value) {
    if (!(value instanceof String)) {
        return -1;
    }
    String text = (String) value;
    return text.length();
}
~~~

Cách viết với pattern variable và guard clause:

~~~java
static int patternLength(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length();
}
~~~

Đọc luồng điều khiển từ trên xuống:

1. Nếu **value** không phải **String** hoặc là **null**, biểu thức **instanceof** trả về **false**, phủ định **!** thành **true**, và phương thức trả về **-1**.
2. Nếu việc thực thi đi tới **return text.length()**, nhánh thoát sớm đã không chạy. Điều đó chỉ xảy ra khi **value instanceof String text** là **true**.
3. Compiler vì thế cho phép **text** xuất hiện sau khối **if**, với kiểu tĩnh **String**; không cần ép kiểu thủ công.

Đây là lợi ích của **flow scoping**: phạm vi pattern variable phụ thuộc vào **đường đi của chương trình**, không chỉ dấu ngoặc nhọn.

Nếu bỏ **return** ở nhánh không khớp, kết luận trên không còn đúng:

~~~java
// Ví dụ cố ý SAI, không thể biên dịch như một phương thức đầy đủ.
if (!(value instanceof String text)) {
    System.out.println("Không phải chuỗi");
}
System.out.println(text.length()); // Lỗi: vẫn có đường đi chưa khớp
~~~

Guard clause chỉ tạo được bằng chứng khi trường hợp thất bại **không thể tiếp tục** tới vị trí dùng biến. **throw** cũng làm được việc đó; một lệnh **println** hoặc gán cờ trạng thái thì không.

## 3. Kết hợp guard với && và ||

Các toán tử **&&** và **||** đều đánh giá ngắn mạch từ trái sang phải:

- Với **left && right**, vế phải chỉ được đánh giá khi vế trái **true**.
- Với **left || right**, vế phải chỉ được đánh giá khi vế trái **false**.

Điều kiện bảo vệ **tích cực** thường dùng **&&**:

~~~java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
~~~

Vế phải dùng **text** an toàn vì nó chỉ chạy khi **instanceof** đã khớp. Nếu **value** là **null** hoặc kiểu khác, **text.isBlank()** hoàn toàn không được gọi.

Điều kiện bảo vệ **phủ định** thường dùng **||** kết hợp thoát sớm:

~~~java
static String normalize(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "(không có chuỗi)";
    }
    return text.strip();
}
~~~

Biểu thức **!(value instanceof String text)** đúng khi không khớp. Nếu điều đó xảy ra, toán tử **||** dừng ngay và **text.isBlank()** không chạy. Ngược lại, vế phải của **||** chỉ được xét khi phủ định sai, nghĩa là **instanceof** đã khớp và **text** có hiệu lực.

Khi toàn bộ điều kiện guard là **false**, ta biết đồng thời:

- **value** là **String** khác **null** và **text** đã được gắn.
- **text.isBlank()** là **false**.

Vì nhánh **true** đã **return**, mã sau guard được phép dùng **text**. Đừng đánh đồng điều này với biểu thức sau:

~~~java
// SAI: khi instanceof ở vế trái false, vế phải || phải chạy
// nhưng pattern variable text chưa được gắn.
if (value instanceof String text || text.isBlank()) {
    System.out.println("...");
}
~~~

Quy tắc đúng là **xem từng đường thực thi có bảo đảm biến đã khớp hay không**, không phải ghi nhớ rằng **&&** luôn đúng và **||** luôn sai. **||** trong guard phủ định ở trên hoàn toàn hợp lệ.

Một ví dụ khác với **&&** nhiều điều kiện:

~~~java
if (value instanceof String text
        && text.startsWith("ID-")
        && text.length() > 3) {
    System.out.println("Mã: " + text.substring(3));
}
~~~

Mỗi vế bên phải được đánh giá sau khi các vế bên trái trả về **true**. Độ an toàn kiểu của **text** được giữ xuyên suốt chuỗi điều kiện. Tuy vậy, **instanceof** chỉ xác minh kiểu; quy tắc **"ID-"** và độ dài là kiểm tra nghiệp vụ cần viết riêng.

## 4. Ví dụ đầy đủ với Java 17

Lưu tệp **PatternGuardDemo.java**:

~~~java
public class PatternGuardDemo {
    static String summarize(Object value) {
        if (!(value instanceof String text)) {
            return "not a string";
        }
        if (text.isBlank()) {
            return "blank";
        }

        String normalized = text.strip();
        if (normalized.length() < 3) {
            return "too short";
        }
        return "ok: " + normalized;
    }

    static String category(Object value) {
        if (value instanceof String text && text.startsWith("ID-")) {
            return "id: " + text.substring(3);
        }
        if (value instanceof Integer count && count >= 0) {
            return "non-negative: " + count;
        }
        return "unmatched";
    }

    static String singleGuard(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "missing";
        }
        return "text: " + text.strip();
    }

    public static void main(String[] args) {
        System.out.println(summarize("  Java  "));
        System.out.println(summarize("   "));
        System.out.println(summarize(9));
        System.out.println(summarize(" A "));

        System.out.println(category("ID-42"));
        System.out.println(category(3));
        System.out.println(category(-1));
        System.out.println(category(null));

        System.out.println(singleGuard("  ok "));
        System.out.println(singleGuard("  "));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 PatternGuardDemo.java
java PatternGuardDemo
~~~

Kết quả kỳ vọng:

~~~text
ok: Java
blank
not a string
too short
id: 42
non-negative: 3
unmatched
unmatched
text: ok
missing
~~~

**Diễn giải:** Trong **summarize**, guard đầu tiên loại bỏ **Integer 9**; đầu vào gồm khoảng trắng bị chặn bởi **isBlank()**; chuỗi **" A "** sau **strip()** chỉ dài một ký tự nên bị chặn ở guard độ dài; chỉ **"  Java  "** đi đến kết quả **ok: Java**. Trong **category**, các điều kiện **&&** cho phép kiểm tra tiền tố hoặc dấu của số ngay sau khi khớp **String** hoặc **Integer**. **-1** và **null** không thỏa nhánh nào. Trong **singleGuard**, phủ định pattern đi cùng **||** bảo đảm rằng mã phía sau **return** chỉ xử lý chuỗi không blank.

Chương trình sử dụng pattern matching cho **instanceof** (chính thức từ Java 16), **String.isBlank()** và **String.strip()** (Java 11+). Không có cú pháp preview và không cần Java 21.

## 5. Khi nào biến pattern hợp lệ sau guard?

Đối chiếu các trường hợp:

| Cấu trúc | Có được dùng biến ở vị trí tương ứng? | Lý do |
| --- | --- | --- |
| **if (obj instanceof String s) { dùng s; }** | Có, trong nhánh đúng | Nhánh chỉ chạy khi khớp |
| **if (obj instanceof String s && s.length() > 0)** | Có, ở vế phải **&&** và nhánh đúng | Vế phải chỉ chạy khi **instanceof** đúng |
| **if (!(obj instanceof String s)) return; dùng s;** | Có, sau guard | Đường không khớp đã kết thúc |
| **if (!(obj instanceof String s) || s.isBlank()) return; dùng s;** | Có, ở vế phải **||** và sau guard | Vế phải chỉ chạy khi khớp; nhánh thất bại đã thoát |
| **if (!(obj instanceof String s)) println(...); dùng s;** | Không, ở câu lệnh sau **if** | Đường không khớp vẫn có thể đi tiếp |
| **if (obj instanceof String s || s.isBlank())** | Không, ở vế phải **||** | Vế phải chạy khi **instanceof** sai |

Các đoạn trong bảng là **mẫu cú pháp để so sánh**, không phải toàn bộ chương trình có thể chạy độc lập. Trong các biểu thức mẫu, **dùng s** chỉ vị trí sử dụng biến.

Một điểm dễ nhầm là **guard clause** không tự động biến pattern variable thành biến toàn cục hoặc biến có phạm vi toàn phương thức. Sau một guard có **return**, compiler cho phép biến tồn tại ở phần còn lại có thể tới được; nếu luồng điều khiển thay đổi, chẳng hạn thay **return** bằng một lệnh ghi log, phạm vi hợp lệ cũng thay đổi.

### Dùng throw khi dữ liệu không đúng kiểu

Nếu API yêu cầu tuyệt đối đầu vào là chuỗi, thay vì trả về giá trị dự phòng có thể ném ngoại lệ:

~~~java
static String requireString(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected a non-null String");
    }
    return text.strip();
}
~~~

**throw** kết thúc đường đi không khớp, vì thế **text** hợp lệ ở lệnh **return** sau guard. Đây là một đoạn **phương thức minh họa**, không phải chương trình độc lập. Thông báo ngoại lệ nói rõ rằng **null** cũng không được chấp nhận.

## 6. Guard của switch pattern bằng when — Java 21+

Từ **Java 21**, pattern matching cho **switch** là tính năng chính thức. Có thể bổ sung điều kiện guard ngay trong nhãn **case** bằng từ khóa **when**:

~~~java
case String text when text.isBlank() -> "blank";
~~~

Ý nghĩa gồm hai bước: đầu tiên switch kiểm tra giá trị có khớp **String text** không; chỉ nếu khớp, nó mới đánh giá **text.isBlank()**. Nếu guard trả về **false**, switch tiếp tục xét các **case** tiếp theo. Biến **text** có kiểu tĩnh **String** cả trong biểu thức **when** lẫn phần xử lý của nhánh đã được chọn.

Lưu tệp **WhenGuardDemo.java**, biên dịch bằng **JDK 21+**:

~~~java
public class WhenGuardDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case String text when text.isBlank() -> "blank";
            case String text when text.length() >= 5 ->
                    "long: " + text.strip();
            case String text -> "short: " + text.strip();
            case Integer number when number >= 0 ->
                    "non-negative: " + number;
            case Integer number -> "negative: " + number;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("    "));
        System.out.println(classify("Java SE"));
        System.out.println(classify("ok"));
        System.out.println(classify(3));
        System.out.println(classify(-4));
        System.out.println(classify(null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 WhenGuardDemo.java
java WhenGuardDemo
~~~

Kết quả:

~~~text
blank
long: Java SE
short: ok
non-negative: 3
negative: -4
null
~~~

Ba nhãn **String** được sắp xếp từ điều kiện cụ thể đến nhánh không guard. Nếu **case String text -> ...** xuất hiện trước các nhãn **String ... when ...**, những nhãn phía sau sẽ bị che khuất bởi nhánh tổng quát và compiler có thể báo lỗi **dominated case**.

**case null** phải được xử lý tường minh nếu muốn trả về **"null"**: nhánh **default** không thay thế việc xử lý **null** trong switch pattern. Các biểu thức **when** cần cho ra boolean; nếu guard không thỏa, switch tìm nhánh case tiếp theo. Guard có thể gọi phương thức, nên tránh side effect khó đoán hoặc thao tác có thể ném ngoại lệ không được xử lý. Đặc biệt, **when** với pattern variable của một kiểu không chứng minh các trường bên trong đối tượng cũng khác **null**.

**Phân biệt phiên bản:** **instanceof String text** và guard clause chạy trên Java 17; cú pháp **case String text when ...** là ngôn ngữ Java 21 chính thức. Không đưa ví dụ **when** vào mã được biên dịch bằng JDK 17 vì nó sẽ không biên dịch.

## 7. Lỗi thường gặp và cách tránh

**Lỗi 1 — Dùng biến trong nhánh không khớp.** Viết **if (!(obj instanceof String s)) { System.out.println(s); }** là sai: phần thân này chạy khi phép khớp **String** thất bại. Hãy chỉ dùng **s** sau khi đã thoát khỏi nhánh thất bại, hoặc trong một nhánh được chứng minh khớp.

**Lỗi 2 — Đặt điều kiện nghiệp vụ trước kiểm tra kiểu.** Biểu thức **s.length() > 0 && obj instanceof String s** không hợp lệ vì **s** chưa được giới thiệu ở vế trái. Phải đặt **instanceof String s** trước, rồi đến **s.length() > 0**.

**Lỗi 3 — Nhầm || dương với || phủ định.** **obj instanceof String s || s.isBlank()** sai; **!(obj instanceof String s) || s.isBlank()** hợp lệ khi **s.isBlank()** chỉ cần chạy nếu phép khớp thành công. Luôn kiểm tra vế nào được đánh giá khi điều kiện trước đúng hoặc sai.

**Lỗi 4 — Chỉ ghi log trong guard rồi dùng biến phía sau.** Nếu nhánh không khớp chỉ gọi **println** rồi tiếp tục, biến chưa chắc được gắn. Dùng **return**, **throw** hoặc tách phần xử lý vào nhánh đúng.

**Lỗi 5 — Tưởng type pattern xác thực luôn dữ liệu.** **obj instanceof String s** không xác minh chuỗi không blank, đúng định dạng ID, URL hay email. Các ràng buộc ấy phải được diễn đạt bằng điều kiện guard riêng và có kiểm thử cho ranh giới.

**Lỗi 6 — Quên xử lý null.** **null instanceof String s** là **false**, nên guard clause phủ định thường bắt cả **null**. Với **switch** Java 21, nếu muốn xử lý **null** như một trạng thái nghiệp vụ, khai báo **case null**; đừng trông chờ **default** làm việc ấy.

**Lỗi 7 — Đặt case tổng quát trước case có when.** Trong switch Java 21, thứ tự pattern ảnh hưởng tới nhánh có thể được chọn và phép kiểm tra dominance. Đặt các nhánh có guard cụ thể trước pattern tổng quát cùng kiểu.

**Lỗi 8 — Dùng cú pháp when trên JDK 17.** Chỉ Java 21 mới chuẩn hóa guard của switch pattern bằng **when**. Đối với dự án Java 17, dùng **if (obj instanceof T x && condition(x))** hoặc guard clause trước khi xử lý.

## 8. Cách chọn guard phù hợp

Dùng **guard clause + return/throw** khi đầu vào sai kiểu hoặc thiếu điều kiện tiên quyết khiến toàn bộ quá trình xử lý phải dừng. Cách này giúp phần còn lại của phương thức tập trung vào trường hợp hợp lệ và tận dụng được biến pattern mà không cast.

Dùng **&&** khi điều kiện kiểm tra kiểu và một vài điều kiện phụ có thể diễn đạt gọn trong cùng **if**, không cần thông báo lỗi riêng cho mỗi lý do.

Dùng **switch ... case Type variable when condition** khi dự án dùng **Java 21+**, cần phân loại nhiều kiểu hoặc nhiều điều kiện của cùng kiểu, và mỗi nhánh trả về một kết quả rõ ràng. Sắp xếp nhánh cụ thể trước nhánh tổng quát và xử lý **null** theo đúng hợp đồng của API.

Khi kiểm tra code, nên có ca thử cho: đúng kiểu và guard đúng, đúng kiểu nhưng guard sai, sai kiểu, **null**, và thứ tự các case có thể chồng lấn (nếu dùng switch). Điều này xác nhận cả tính đúng đắn nghiệp vụ lẫn phạm vi sử dụng biến.

**Kết luận:** pattern variable chỉ được dùng khi compiler có bằng chứng phép khớp thành công. Trong Java 17, guard clause và các toán tử ngắn mạch tạo ra bằng chứng đó qua luồng điều khiển; trong Java 21, **when** thêm điều kiện bảo vệ trực tiếp vào nhãn pattern của switch. Hiểu đúng phạm vi sẽ giúp bỏ cast dư thừa mà vẫn giữ an toàn kiểu và đường xử lý rõ ràng.